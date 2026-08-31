from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.job_control import (
    JOB_CONTROL_SCHEMA_VERSION,
    JobControlValidationError,
    validate_job_cancel_payload,
)
from tools.studio.jobs import JobCancelled
from tools.studio.service import RequestValidationError, StudioService
from tools.studio.server import create_server


class JobControlPayloadTests(unittest.TestCase):
    def test_accepts_only_the_supported_closed_schema(self) -> None:
        self.assertEqual(
            validate_job_cancel_payload({"schema_version": 1}),
            {"schema_version": JOB_CONTROL_SCHEMA_VERSION},
        )

        for body in (
            None,
            [],
            {},
            {"schema_version": True},
            {"schema_version": 2},
            {"schema_version": 1, "force": True},
            {"schema_version": 1, "timeout": 0},
        ):
            with self.subTest(body=body):
                with self.assertRaises(JobControlValidationError):
                    validate_job_cancel_payload(body)


class JobControlServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.service = StudioService(self.workspace)

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def test_active_job_is_interrupted_and_worker_retires(self) -> None:
        entered = threading.Event()

        def wait_for_cancel(
            _job_id: str, cancel_event: object
        ) -> dict[str, object]:
            entered.set()
            wait = getattr(cancel_event, "wait")
            self.assertTrue(wait(5))
            raise JobCancelled()

        queued = self.service.jobs.submit(
            "test_job_control", {}, wait_for_cancel
        )
        self.assertTrue(entered.wait(5))

        response = self.service.cancel_job(
            queued["id"], {"schema_version": 1}
        )
        completed = self.service.jobs.wait(queued["id"], timeout=5)

        assert completed is not None
        self.assertTrue(response["cancel_requested"])
        self.assertTrue(response["worker_retired"])
        self.assertEqual(response["schema_version"], 1)
        self.assertEqual(completed["status"], "interrupted")

    def test_terminal_job_is_an_idempotent_no_op(self) -> None:
        queued = self.service.jobs.submit(
            "test_job_control", {}, lambda _job_id, _cancel_event: {"ok": True}
        )
        completed = self.service.jobs.wait(queued["id"], timeout=5)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")

        response = self.service.cancel_job(
            queued["id"], {"schema_version": 1}
        )

        self.assertFalse(response["cancel_requested"])
        self.assertTrue(response["worker_retired"])
        self.assertEqual(response["job"]["status"], "succeeded")

    def test_non_cooperative_worker_can_be_reconciled_to_retired(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def ignore_cancel_temporarily(
            _job_id: str, _cancel_event: object
        ) -> dict[str, object]:
            entered.set()
            release.wait(5)
            return {"ok": True}

        queued = self.service.jobs.submit(
            "test_job_control", {}, ignore_cancel_temporarily
        )
        self.assertTrue(entered.wait(5))
        try:
            first = self.service.cancel_job(
                queued["id"], {"schema_version": 1}
            )
            self.assertTrue(first["cancel_requested"])
            self.assertFalse(first["worker_retired"])

            release.set()
            completed = self.service.jobs.wait(queued["id"], timeout=5)
            assert completed is not None
            self.assertEqual(completed["status"], "interrupted")

            reconciled = self.service.cancel_job(
                queued["id"], {"schema_version": 1}
            )
            self.assertFalse(reconciled["cancel_requested"])
            self.assertTrue(reconciled["worker_retired"])
            self.assertEqual(reconciled["job"]["status"], "interrupted")
        finally:
            release.set()

    def test_unknown_job_and_open_ended_body_are_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.service.cancel_job(
                "job_" + "0" * 32, {"schema_version": 1}
            )
        with self.assertRaises(RequestValidationError):
            self.service.cancel_job(
                "job_" + "0" * 32,
                {"schema_version": 1, "force": True},
            )


class JobControlHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "job-control-test-session-token-000000000000"
        self.server = create_server(
            self.workspace,
            host="127.0.0.1",
            port=0,
            session_token=self.token,
            initial_refresh=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temporary.cleanup()

    def test_authenticated_cancel_route_forwards_exact_request(self) -> None:
        job_id = "job_" + "a" * 32
        expected = {
            "schema_version": 1,
            "job": {"id": job_id, "status": "interrupted"},
            "cancel_requested": True,
            "worker_retired": False,
        }
        body = json.dumps({"schema_version": 1}).encode("utf-8")
        with mock.patch.object(
            self.server.service, "cancel_job", return_value=expected
        ) as cancel:
            self.connection.request(
                "POST",
                f"/api/jobs/{job_id}/cancel",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "X-Studio-Token": self.token,
                },
            )
            response = self.connection.getresponse()
            payload = response.read()

        self.assertEqual(response.status, 202)
        self.assertEqual(json.loads(payload), expected)
        cancel.assert_called_once_with(job_id, {"schema_version": 1})

    def test_http_cancel_reconciles_the_same_job_after_worker_retirement(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def ignore_cancel_temporarily(
            _job_id: str, _cancel_event: object
        ) -> dict[str, object]:
            entered.set()
            release.wait(5)
            return {"ok": True}

        queued = self.server.service.jobs.submit(
            "test_job_control", {}, ignore_cancel_temporarily
        )
        self.assertTrue(entered.wait(5))
        body = json.dumps({"schema_version": 1}).encode("utf-8")

        def request_cancel() -> tuple[int, dict[str, object]]:
            self.connection.request(
                "POST",
                f"/api/jobs/{queued['id']}/cancel",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "X-Studio-Token": self.token,
                },
            )
            response = self.connection.getresponse()
            payload = json.loads(response.read())
            return response.status, payload

        try:
            status, first = request_cancel()
            self.assertEqual(status, 202)
            self.assertEqual(first["job"]["id"], queued["id"])
            self.assertTrue(first["cancel_requested"])
            self.assertFalse(first["worker_retired"])

            release.set()
            completed = self.server.service.jobs.wait(queued["id"], timeout=5)
            assert completed is not None
            self.assertEqual(completed["status"], "interrupted")

            status, reconciled = request_cancel()
            self.assertEqual(status, 202)
            self.assertEqual(reconciled["job"]["id"], queued["id"])
            self.assertFalse(reconciled["cancel_requested"])
            self.assertTrue(reconciled["worker_retired"])
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
