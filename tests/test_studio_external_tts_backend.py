from __future__ import annotations

import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio import elevenlabs
from tools.studio.elevenlabs import ExternalTTSSubmissionUnknown
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService

from tests.test_studio_backend import PRODUCTION_ID, WorkspaceFixture


def _payload(*, confirm_billable: object = True) -> dict[str, object]:
    return {
        "provider": "elevenlabs",
        "voice_id": "voice_test_123",
        "model_id": "eleven_multilingual_v2",
        "segments": [{"text": "external backend regression"}],
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
        "seed": 17,
        "confirm_billable": confirm_billable,
    }


class _Response:
    def __init__(self, *, status: int):
        self.status = status
        self.headers: dict[str, str] = {}
        self.closed = False

    def read(self, _size: int = -1) -> bytes:
        raise AssertionError("a non-success response must not be read as media")

    def close(self) -> None:
        self.closed = True


class ExternalTTSAdapterBoundsTests(unittest.TestCase):
    def test_provider_5xx_response_is_treated_as_ambiguous(self) -> None:
        response = _Response(status=503)
        with self.assertRaises(ExternalTTSSubmissionUnknown) as raised:
            elevenlabs._provider_request(
                "http://127.0.0.1:49321",
                "xi-test-secret",
                _payload(),
                timeout=1.0,
                opener=lambda *_args, **_kwargs: response,
            )
        self.assertEqual(raised.exception.error_code, "external_submission_unknown")
        self.assertTrue(response.closed)
        self.assertNotIn("xi-test-secret", str(raised.exception))

    def test_response_body_deadline_applies_to_slow_drip_completion(self) -> None:
        class EmptyResponse:
            headers: dict[str, str] = {}

            def read(self, _size: int = -1) -> bytes:
                return b""

        # The first monotonic read admits the operation; the second represents
        # a provider body that only completes after the total request deadline.
        with mock.patch.object(elevenlabs.time, "monotonic", side_effect=[0.0, 2.0]):
            with self.assertRaises(ExternalTTSSubmissionUnknown):
                elevenlabs._read_bounded_response(
                    EmptyResponse(), deadline=1.0
                )


class ExternalTTSServiceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def _run(self) -> str:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
                "execution_profile": "elevenlabs_tts",
            },
        )
        return str(created["run"]["id"])

    def test_external_profile_requires_narration_at_run_creation(self) -> None:
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "assembly"}],
                    "estimated_cost": {"amount": "1.00", "currency": "USD"},
                    "execution_profile": "elevenlabs_tts",
                },
            )
        self.assertEqual(raised.exception.code, "external_profile_stage_not_allowed")

    def test_unapproved_request_does_not_load_external_contract_or_secret(self) -> None:
        run_id = self._run()
        with (
            mock.patch(
                "tools.studio.service.importlib.import_module",
                side_effect=AssertionError("contract loaded before approval"),
            ),
            mock.patch.object(
                self.service.secret_store,
                "resolve",
                side_effect=AssertionError("secret resolved before approval"),
            ),
        ):
            with self.assertRaises(RequestValidationError) as raised:
                self.service.execute_external_narration(run_id, _payload())
        self.assertEqual(raised.exception.code, "approval_required")

    def test_external_profile_is_admitted_to_local_assembly_and_qc_gates(self) -> None:
        run_id = self._run()
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")

        with self.assertRaises(RequestValidationError) as assembly_error:
            self.service.execute_local_assembly(
                run_id,
                {
                    "video_artifact_id": video["id"],
                    "narration_attempt_id": "attempt_00000000000000000000000000000000",
                    "include_captioned": False,
                },
            )
        self.assertEqual(assembly_error.exception.code, "assembly_narration_not_available")

        with self.assertRaises(RequestValidationError) as qc_error:
            self.service.execute_local_qc(
                run_id,
                {
                    "assembly_attempt_id": "attempt_00000000000000000000000000000000",
                    "variant": "clean",
                },
            )
        self.assertEqual(qc_error.exception.code, "qc_assembly_not_available")

    def test_ambiguous_first_job_blocks_second_provider_call(self) -> None:
        run_id = self._run()
        self.service.approve_run(
            run_id,
            {"approved": True, "max_cost": {"amount": "1.00", "currency": "USD"}},
        )
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def ambiguous_worker(
            _workspace: Path,
            **_kwargs: object,
        ) -> dict[str, object]:
            nonlocal calls
            calls += 1
            entered.set()
            self.assertTrue(release.wait(5))
            raise ExternalTTSSubmissionUnknown()

        with (
            mock.patch.object(self.service.secret_store, "resolve", return_value="xi-test-secret"),
            mock.patch("tools.studio.elevenlabs.generate_external_tts", side_effect=ambiguous_worker),
        ):
            first = self.service.execute_external_narration(run_id, _payload())
            self.assertTrue(entered.wait(5))
            second = self.service.execute_external_narration(run_id, _payload())
            release.set()
            first_done = self.service.jobs.wait(first["id"], timeout=10)
            second_done = self.service.jobs.wait(second["id"], timeout=10)

        self.assertIsNotNone(first_done)
        self.assertIsNotNone(second_done)
        assert first_done is not None and second_done is not None
        self.assertEqual(calls, 1)
        self.assertEqual(first_done["error"]["code"], "external_submission_unknown")
        self.assertEqual(second_done["error"]["code"], "external_submission_unknown")


class ExternalTTSHTTPRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "test-session-token-with-at-least-thirty-two-characters"
        self.server = create_server(
            self.fixture.root,
            host="127.0.0.1",
            port=0,
            static_dir="studio/dist",
            session_token=self.token,
            initial_refresh=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.fixture.close()

    def test_external_narration_route_enforces_approval_gate(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
                "execution_profile": "elevenlabs_tts",
            },
        )
        body = json.dumps(_payload()).encode("utf-8")
        self.connection.request(
            "POST",
            f"/api/runs/{created['run']['id']}/execute-external-narration",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        response_body = json.loads(response.read())
        self.assertEqual(response.status, 422)
        self.assertEqual(response_body["error"]["code"], "approval_required")


if __name__ == "__main__":
    unittest.main()
