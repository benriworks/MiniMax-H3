from __future__ import annotations

import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.test_studio_windows_capture_acceptance import (
    PRODUCTION_ID,
    RUN_ID,
    _capture_result,
    _passing_report,
)
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService
from tools.studio.windows_capture_acceptance import (
    WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS,
    WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE,
    WINDOWS_CAPTURE_ACCEPTANCE_EVENT_TYPE,
    WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK,
)


class _AcceptanceDatabase:
    def __init__(self, capture: dict[str, object]):
        self.run = {
            "id": RUN_ID,
            "production_id": PRODUCTION_ID,
            "execution_profile": "local_windows_capture",
            "requested_stages": ["screen_capture", "timeline"],
        }
        self.job = {
            "id": "job_" + "4" * 32,
            "kind": "local_windows_capture",
            "status": "succeeded",
            "production_id": PRODUCTION_ID,
            "payload": {"run_id": RUN_ID},
            "result": capture,
        }
        self.artifacts = {
            item["id"]: copy.deepcopy(item) for item in capture["artifacts"]
        }
        self.events: list[dict[str, object]] = []

    def get_run(self, run_id: str) -> dict[str, object] | None:
        return copy.deepcopy(self.run) if run_id == RUN_ID else None

    def find_latest_job_for_run(
        self, kind: str, production_id: str, run_id: str
    ) -> dict[str, object] | None:
        if (
            kind == "local_windows_capture"
            and production_id == PRODUCTION_ID
            and run_id == RUN_ID
        ):
            return copy.deepcopy(self.job)
        return None

    def get_artifact(self, artifact_id: str) -> dict[str, object] | None:
        artifact = self.artifacts.get(artifact_id)
        return copy.deepcopy(artifact) if artifact is not None else None

    def production_audit_snapshot(
        self, production_id: str
    ) -> dict[str, object] | None:
        if production_id != PRODUCTION_ID:
            return None
        return {"events": copy.deepcopy(self.events)}

    def append_event(
        self,
        scope_type: str,
        scope_id: str,
        event_type: str,
        payload: object,
    ) -> dict[str, object]:
        event = {
            "id": len(self.events) + 1,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "event_type": event_type,
            "created_at": "2026-09-01T00:00:00+00:00",
            "payload": copy.deepcopy(payload),
            "previous_hash": "0" * 64,
            "event_hash": f"{len(self.events) + 1:064x}",
        }
        self.events.append(event)
        return copy.deepcopy(event)


class WindowsCaptureAcceptanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.capture = _capture_result()
        for artifact in self.capture["artifacts"]:
            path = self.workspace / str(artifact["rel_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            content = f"acceptance-{artifact['name']}".encode("utf-8")
            path.write_bytes(content)
            stat = path.stat()
            artifact["bytes"] = stat.st_size
            artifact["mtime_ns"] = stat.st_mtime_ns
            artifact["sha256"] = hashlib.sha256(content).hexdigest().upper()
            artifact["is_heavy"] = False
        self.database = _AcceptanceDatabase(self.capture)
        self.service = object.__new__(StudioService)
        self.service.workspace = self.workspace
        self.service.database = self.database
        self.service._windows_capture_submit_lock = threading.Lock()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_report_is_persisted_once_and_replayed_idempotently(self) -> None:
        report = _passing_report(self.capture)

        created = self.service.record_windows_capture_acceptance(RUN_ID, report)
        replayed = self.service.record_windows_capture_acceptance(RUN_ID, report)

        self.assertTrue(created["created"])
        self.assertFalse(replayed["created"])
        self.assertEqual(created["event"], replayed["event"])
        self.assertEqual(created["acceptance"], replayed["acceptance"])
        acceptance = created["acceptance"]
        self.assertFalse(acceptance["content_sync_verified"])
        self.assertFalse(acceptance["public_release_ready"])
        self.assertTrue(acceptance["live_validation_required"])
        self.assertEqual(
            acceptance["status"], WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS
        )
        self.assertEqual(
            acceptance["evidence_provenance"],
            WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE,
        )
        self.assertTrue(acceptance["self_reported_thresholds_met"])
        self.assertEqual(
            acceptance["failed_checks"],
            [WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK],
        )
        self.assertEqual(len(self.database.events), 1)
        event = self.database.events[0]
        self.assertEqual(event["scope_type"], "production")
        self.assertEqual(event["scope_id"], PRODUCTION_ID)
        self.assertEqual(event["event_type"], WINDOWS_CAPTURE_ACCEPTANCE_EVENT_TYPE)
        self.assertEqual(event["payload"]["run_id"], RUN_ID)
        self.assertEqual(event["payload"]["source_job_id"], self.database.job["id"])
        self.assertEqual(event["payload"]["acceptance"], acceptance)
        self.assertEqual(
            event["payload"]["acceptance"]["automated_facts"],
            report["automated_facts"],
        )
        self.assertEqual(
            event["payload"]["acceptance"]["operator_attestations"],
            report["operator_attestations"],
        )
        serialized = json.dumps(event, sort_keys=True)
        self.assertNotIn("rel_path", serialized)
        self.assertNotIn("window_title", serialized)
        self.assertNotIn("credential", serialized)

    def test_valid_failed_observation_is_recorded_as_blocked(self) -> None:
        report = _passing_report(self.capture)
        report["operator_attestations"]["cursor_absence_observed"] = False

        recorded = self.service.record_windows_capture_acceptance(RUN_ID, report)

        self.assertTrue(recorded["created"])
        self.assertFalse(recorded["acceptance"]["content_sync_verified"])
        self.assertFalse(recorded["acceptance"]["public_release_ready"])
        self.assertEqual(
            recorded["acceptance"]["failed_checks"],
            [
                "operator.cursor_absence_observed",
                WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK,
            ],
        )
        self.assertFalse(recorded["acceptance"]["self_reported_thresholds_met"])

    def test_missing_failed_or_cross_production_source_is_rejected(self) -> None:
        report = _passing_report(self.capture)
        with self.assertRaises(KeyError):
            self.service.record_windows_capture_acceptance(
                "run_" + "9" * 32, report
            )

        cases = (
            ("failed job", ("job", "status", "failed")),
            ("wrong job production", ("job", "production_id", "another")),
            ("wrong run profile", ("run", "execution_profile", "local_sapi")),
        )
        for label, (target, field, value) in cases:
            with self.subTest(label=label):
                original = copy.deepcopy(getattr(self.database, target))
                getattr(self.database, target)[field] = value
                try:
                    with self.assertRaises(RequestValidationError) as failed:
                        self.service.record_windows_capture_acceptance(RUN_ID, report)
                    self.assertEqual(
                        failed.exception.code,
                        "windows_capture_acceptance_source_required",
                    )
                finally:
                    setattr(self.database, target, original)
        self.assertEqual(self.database.events, [])

    def test_database_or_physical_artifact_change_fails_before_event(self) -> None:
        report = _passing_report(self.capture)
        first_artifact = self.capture["artifacts"][0]

        self.database.artifacts[first_artifact["id"]]["sha256"] = "9" * 64
        with self.assertRaises(RequestValidationError) as db_changed:
            self.service.record_windows_capture_acceptance(RUN_ID, report)
        self.assertEqual(
            db_changed.exception.code,
            "windows_capture_acceptance_source_changed",
        )

        self.database.artifacts[first_artifact["id"]] = copy.deepcopy(first_artifact)
        path = self.workspace / str(first_artifact["rel_path"])
        path.write_bytes(b"changed-after-registration")
        with self.assertRaises(RequestValidationError) as file_changed:
            self.service.record_windows_capture_acceptance(RUN_ID, report)
        self.assertEqual(
            file_changed.exception.code,
            "windows_capture_acceptance_source_changed",
        )
        self.assertEqual(self.database.events, [])

    def test_report_binding_mismatch_is_rejected_without_event(self) -> None:
        report = _passing_report(self.capture)
        report["artifact_sha256"]["screen-capture.mp4"] = "8" * 64

        with self.assertRaises(RequestValidationError) as failed:
            self.service.record_windows_capture_acceptance(RUN_ID, report)

        self.assertEqual(
            failed.exception.code, "windows_capture_acceptance_binding_mismatch"
        )
        self.assertEqual(self.database.events, [])

    def test_real_database_registered_capture_is_resolved_and_event_is_deduplicated(
        self,
    ) -> None:
        # Reuse the native-capture integration fixture without exporting its
        # TestCase class into this module's discovery namespace.
        from tests.test_studio_windows_capture_service import (
            WindowsCaptureServiceTests,
        )

        fixture = WindowsCaptureServiceTests(
            methodName="test_profile_job_lineage_and_exact_artifacts_commit_atomically"
        )
        fixture.setUp()
        try:
            run_id = fixture._run()
            execution_body, _consent = fixture._consented_body(run_id)
            capability, generate, validate, discard = fixture._worker_patches()
            with capability, generate, validate, discard:
                queued = fixture._execute(run_id, execution_body)
                completed = fixture.service.jobs.wait(queued["id"], timeout=10)
            assert completed is not None
            self.assertEqual(completed["status"], "succeeded")
            report = _passing_report(completed["result"])

            created = fixture.service.record_windows_capture_acceptance(
                run_id, report
            )
            replayed = fixture.service.record_windows_capture_acceptance(
                run_id, report
            )

            self.assertTrue(created["created"])
            self.assertFalse(replayed["created"])
            snapshot = fixture.service.database.production_audit_snapshot(
                created["production_id"]
            )
            assert snapshot is not None
            matching = [
                event
                for event in snapshot["events"]
                if event["event_type"] == WINDOWS_CAPTURE_ACCEPTANCE_EVENT_TYPE
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(
                matching[0]["payload"]["acceptance"]["acceptance_digest"],
                created["acceptance_digest"],
            )
        finally:
            fixture.tearDown()


class WindowsCaptureAcceptanceHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "capture-acceptance-session-token-000000000"
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

    def _post(self, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        encoded = json.dumps(body).encode("utf-8")
        self.connection.request(
            "POST",
            f"/api/runs/{RUN_ID}/windows-capture-acceptance",
            body=encoded,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(encoded)),
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_route_returns_201_then_200_for_idempotent_replay(self) -> None:
        body = {"schema_version": 1}
        created = {"created": True, "acceptance_digest": "A" * 64}
        replayed = {"created": False, "acceptance_digest": "A" * 64}
        with mock.patch.object(
            self.server.service,
            "record_windows_capture_acceptance",
            side_effect=(created, replayed),
        ) as delegated:
            first_status, first_body = self._post(body)
            second_status, second_body = self._post(body)

        self.assertEqual((first_status, first_body), (201, created))
        self.assertEqual((second_status, second_body), (200, replayed))
        self.assertEqual(
            delegated.call_args_list,
            [mock.call(RUN_ID, body), mock.call(RUN_ID, body)],
        )


if __name__ == "__main__":
    unittest.main()
