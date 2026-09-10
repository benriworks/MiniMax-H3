from __future__ import annotations

import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.studio.claude_capture import ClaudeCaptureError
from tools.studio.claude_capture_service import SPECS, capture_root, cleanup_interrupted_claude_captures
from tools.studio.service import RequestValidationError, StudioService
from tools.studio.server import create_server


PRODUCTION = "TEST_claude_window"
REQUEST = "claude_capture_" + "a" * 32
TOKEN = "b" * 43
SESSION = "C" * 64


class ClaudeCaptureServiceTests(unittest.TestCase):
    """Fake native media tests: these do not claim real Claude capture quality."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        source = self.workspace / "productions" / PRODUCTION
        (source / "manifests").mkdir(parents=True)
        (source / "PRODUCTION_RECORD_JA.md").write_text("# Capture fixture\n", encoding="utf-8")
        (source / "manifests" / "source-hashes.json").write_text(json.dumps({"production_id": PRODUCTION, "status": "draft"}), encoding="utf-8")
        self.service = StudioService(self.workspace)
        self.service.indexer.refresh()
        self.initial_artifacts = self.service.database.get_production_detail(PRODUCTION)["artifacts"]
        self.controller = mock.Mock()
        self.controller.claim.return_value = SimpleNamespace(duration_ms=15000)
        self.controller.capture.side_effect = self.media
        self.service._claude_capture.controller = self.controller
        self.body = {"request_id": REQUEST, "selection_token": TOKEN, "duration_ms": 15000, "confirm_capture": True}

    def tearDown(self):
        self.service.close()
        self.temporary.cleanup()

    def media(self, claim, *, capture_root, cancel_event):
        capture_root.mkdir(parents=True)
        artifacts = []
        for name, (kind, mime) in SPECS.items():
            path = capture_root / name
            content = f"MOCK MEDIA ONLY: {name}".encode()
            path.write_bytes(content)
            artifacts.append({"name": name, "kind": kind, "media_type": mime,
                              "rel_path": path.relative_to(self.workspace).as_posix(),
                              "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest().upper()})
        return {"duration_ms": claim.duration_ms, "audio_mode": "none", "audio_streams": 0,
                "actual_capture_performed": True, "structural_video_verified": True,
                "full_decode_verified": True, "artifacts": artifacts}

    def execute(self, body=None, session=SESSION):
        return self.service.execute_claude_capture(PRODUCTION, self.body if body is None else body, session_binding_digest=session)

    def finished(self):
        queued = self.execute()
        return self.service.jobs.wait(queued["id"], timeout=5)

    def test_success_registers_six_source_artifacts_without_run(self):
        done = self.finished()
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(len(done["result"]["artifacts"]), 6)
        self.assertTrue(done["result"]["capture_only"])
        self.assertFalse(done["result"]["public_release_ready"])
        self.assertFalse(done["result"]["content_quality_verified"])
        self.assertEqual(done["result"]["audio_mode"], "none")
        self.assertEqual(done["payload"]["requester_digest"], SESSION)
        self.assertNotIn(TOKEN, json.dumps(done))
        for artifact in done["result"]["artifacts"]:
            self.assertIsNotNone(self.service.database.get_artifact(artifact["id"]))
        with self.service.database.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stage_attempts").fetchone()[0], 0)
        self.assertEqual(self.service.claude_capture_job(PRODUCTION, REQUEST)["id"], done["id"])

    def test_same_request_reconciles_without_another_claim_or_capture(self):
        done = self.finished()
        duplicate = self.execute()
        self.assertEqual(duplicate["id"], done["id"])
        self.assertTrue(duplicate["deduplicated"])
        self.controller.claim.assert_called_once()
        self.controller.capture.assert_called_once()
        for body, session in (({**self.body, "duration_ms": 16000}, SESSION), (self.body, "D" * 64), ({**self.body, "selection_token": "e" * 43}, SESSION)):
            with self.assertRaises(RequestValidationError):
                self.execute(body, session)

    def test_invalid_requests_never_start_native_capture(self):
        bad = [{**self.body, "confirm_capture": False}, {**self.body, "duration_ms": True},
               {**self.body, "duration_ms": 14999}, {**self.body, "duration_ms": 30001},
               {**self.body, "hwnd": 123}, {**self.body, "request_id": "../../unsafe"},
               {**self.body, "selection_token": "invalid"}]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(RequestValidationError):
                self.execute(body)
        self.controller.claim.assert_not_called()
        self.controller.capture.assert_not_called()

    def test_selection_failure_keeps_safe_error_code(self):
        self.controller.claim.side_effect = ClaudeCaptureError("Inspect again.", code="claude_capture_selection_invalid")
        with self.assertRaises(RequestValidationError) as error:
            self.execute()
        self.assertEqual(error.exception.code, "claude_capture_selection_invalid")

    def test_unknown_checkpoint_is_not_restarted(self):
        self.assertIsNone(self.service.claude_capture_job(PRODUCTION, REQUEST))
        self.controller.capture.assert_not_called()

    def test_capture_lane_busy_blocks_admission(self):
        with mock.patch.object(self.service.jobs, "active_job_ids_for_lane", return_value={"busy"}):
            with self.assertRaises(RequestValidationError):
                self.execute()
        self.controller.claim.assert_not_called()

    def test_tampered_media_fails_and_removes_only_owned_output(self):
        def tampered(*args, **kwargs):
            raw = self.media(*args, **kwargs)
            raw["artifacts"][0]["sha256"] = "F" * 64
            return raw
        self.controller.capture.side_effect = tampered
        done = self.finished()
        self.assertEqual(done["status"], "failed", done)
        self.assertFalse(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(self.service.database.get_production_detail(PRODUCTION)["artifacts"], self.initial_artifacts)

    def test_failed_registration_rolls_back_every_artifact_and_media(self):
        original = self.service.database._register_studio_artifact_in_transaction
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("private failure must not leak")
            return original(*args, **kwargs)
        with mock.patch.object(self.service.database, "_register_studio_artifact_in_transaction", side_effect=fail_second):
            done = self.finished()
        self.assertEqual(done["status"], "failed", done)
        self.assertNotIn("private failure", json.dumps(done))
        self.assertFalse(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(self.service.database.get_production_detail(PRODUCTION)["artifacts"], self.initial_artifacts)

    def test_cancel_before_commit_cleans_native_output(self):
        started = threading.Event()
        def waiting(*args, **kwargs):
            raw = self.media(*args, **kwargs)
            started.set()
            kwargs["cancel_event"].wait(5)
            kwargs["cancel_event"].raise_if_cancelled()
            return raw
        self.controller.capture.side_effect = waiting
        queued = self.execute()
        self.assertTrue(started.wait(3))
        done = self.service.jobs.cancel_and_wait(queued["id"], timeout=5)
        self.assertEqual(done["status"], "interrupted", done)
        self.assertFalse(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(self.service.database.get_production_detail(PRODUCTION)["artifacts"], self.initial_artifacts)

    def test_native_target_changed_has_specific_public_failure(self):
        self.controller.capture.side_effect = ClaudeCaptureError("The selected window changed.", code="claude_capture_target_changed")
        done = self.finished()
        self.assertEqual(done["error"]["code"], "claude_capture_target_changed", done)

    def test_cancel_cleanup_failure_is_visible_and_blocks_another_recording(self):
        ready = threading.Event()
        def waiting(*args, **kwargs):
            raw = self.media(*args, **kwargs)
            ready.set()
            kwargs["cancel_event"].wait(5)
            kwargs["cancel_event"].raise_if_cancelled()
            return raw
        self.controller.capture.side_effect = waiting
        with mock.patch("tools.studio.claude_capture_service.cleanup_capture_root", side_effect=PermissionError("private path must not leak")):
            queued = self.execute()
            self.assertTrue(ready.wait(3))
            done = self.service.jobs.cancel_and_wait(queued["id"], timeout=5)
        self.assertEqual(done["status"], "failed", done)
        self.assertEqual(done["error"]["code"], "claude_capture_cleanup_failed", done)
        self.assertNotIn("private path", json.dumps(done))
        self.assertTrue(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertTrue(self.service.database.has_unresolved_claude_capture_cleanup())
        self.assertFalse(self.service.jobs.active_job_ids_for_lane("capture"))
        self.assertEqual(self.execute()["id"], queued["id"])
        with self.assertRaises(RequestValidationError) as error:
            self.execute({**self.body, "request_id": "claude_capture_" + "f" * 32})
        self.assertEqual(error.exception.code, "claude_capture_cleanup_failed")
        self.controller.claim.assert_called_once()
        self.assertEqual(self.service.database.get_production_detail(PRODUCTION)["artifacts"], self.initial_artifacts)

    def test_cleanup_recovery_unblocks_new_capture_without_changing_failed_outcome(self):
        job = self.service.database.create_job("claude_window_capture", {"capture_request_id": REQUEST}, production_id=PRODUCTION)
        root = capture_root(self.workspace, PRODUCTION, REQUEST)
        root.mkdir(parents=True)
        (root / "claude-capture.mp4").write_bytes(b"private partial")
        self.service.database.update_job(job["id"], "interrupted")
        self.assertTrue(self.service.database.fail_claude_capture_cleanup(job["id"]))
        self.assertTrue(self.service.database.has_unresolved_claude_capture_cleanup())
        cleanup_interrupted_claude_captures(self.workspace, self.service.database)
        self.assertFalse(root.exists())
        self.assertFalse(self.service.database.has_unresolved_claude_capture_cleanup())
        after = self.service.database.get_job(job["id"])
        self.assertEqual(after["status"], "failed")
        self.assertEqual(after["error"]["code"], "claude_capture_cleanup_failed")
        self.assertEqual(after["result"], {"privacy_cleanup_completed": True})
        queued = self.execute({**self.body, "request_id": "claude_capture_" + "f" * 32})
        self.assertEqual(self.service.jobs.wait(queued["id"], timeout=5)["status"], "succeeded")

    def test_cleanup_failure_transition_never_rewrites_success_or_unrelated_job(self):
        done = self.finished()
        other = self.service.database.create_job("local_windows_capture", {}, production_id=PRODUCTION)
        self.service.database.update_job(other["id"], "interrupted")
        for job in (done, other):
            self.assertFalse(self.service.database.fail_claude_capture_cleanup(job["id"]))
        self.assertEqual(self.service.database.get_job(done["id"])["status"], "succeeded")
        self.assertEqual(self.service.database.get_job(other["id"])["status"], "interrupted")
        self.assertFalse(self.service.database.has_unresolved_claude_capture_cleanup())

    def test_completion_response_loss_preserves_committed_sources(self):
        original = self.service.database.complete_claude_capture_job
        def commit_then_raise(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("simulated response lost after commit")
        with mock.patch.object(self.service.database, "complete_claude_capture_job", side_effect=commit_then_raise):
            done = self.finished()
        self.assertEqual(done["status"], "succeeded", done)
        self.assertTrue(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(len(done["result"]["artifacts"]), 6)
        for artifact in done["result"]["artifacts"]:
            self.assertTrue((self.workspace / artifact["rel_path"]).is_file())
        self.assertFalse(self.service.database.has_unresolved_claude_capture_cleanup())
        self.assertEqual(self.execute()["id"], done["id"])
        self.controller.capture.assert_called_once()

    def test_cancellation_winning_before_registration_never_publishes_artifacts(self):
        original = self.service.database.complete_claude_capture_job
        def cancel_then_commit(job_id, *args, **kwargs):
            self.service.database.interrupt_job(job_id)
            return original(job_id, *args, **kwargs)
        with mock.patch.object(self.service.database, "complete_claude_capture_job", side_effect=cancel_then_commit):
            done = self.finished()
        self.assertEqual(done["status"], "interrupted", done)
        self.assertFalse(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(self.service.database.get_production_detail(PRODUCTION)["artifacts"], self.initial_artifacts)

    def test_restart_cleanup_scoped_to_incomplete_requests_in_this_database(self):
        complete = self.finished()
        request = "claude_capture_" + "d" * 32
        self.service.database.create_job("claude_window_capture", {"capture_request_id": request}, production_id=PRODUCTION)
        pending_root = capture_root(self.workspace, PRODUCTION, request)
        pending_root.mkdir(parents=True)
        (pending_root / "claude-capture.mp4").write_bytes(b"partial")
        unrelated = capture_root(self.workspace, PRODUCTION, "claude_capture_" + "e" * 32)
        unrelated.mkdir()
        (unrelated / "claude-capture.mp4").write_bytes(b"another database")
        cleanup_interrupted_claude_captures(self.workspace, self.service.database)
        self.assertFalse(pending_root.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(capture_root(self.workspace, PRODUCTION, REQUEST).exists())
        self.assertEqual(self.service.database.get_job(complete["id"])["status"], "succeeded")


class ClaudeCleanupWindowsAdmissionTests(unittest.TestCase):
    def test_unresolved_claude_cleanup_also_blocks_existing_windows_capture(self):
        from tests.test_studio_windows_capture_service import PRODUCTION_ID as WINDOWS_PRODUCTION, WindowsCaptureServiceTests
        fixture = WindowsCaptureServiceTests()
        fixture.setUp()
        try:
            with mock.patch("tools.studio.service.inspect_windows_capture_capability_environment", return_value=fixture.capability), mock.patch("tools.studio.windows_capture_worker.generate_windows_capture") as generate:
                run_id = fixture._run()
                body, _ = fixture._consented_body(run_id)
                job = fixture.service.database.create_job("claude_window_capture", {"capture_request_id": REQUEST}, production_id=WINDOWS_PRODUCTION)
                self.assertTrue(fixture.service.database.fail_claude_capture_cleanup(job["id"]))
                with self.assertRaises(RequestValidationError) as error:
                    fixture._execute(run_id, body)
                self.assertEqual(error.exception.code, "claude_capture_cleanup_failed")
                generate.assert_not_called()
                self.assertIsNone(fixture.service.database.find_active_windows_capture_job())
        finally:
            fixture.tearDown()


class ClaudeCaptureHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.token = "claude-http-fixture-session-0000000000"
        self.server = create_server(Path(self.temporary.name), host="127.0.0.1", port=0, session_token=self.token, initial_refresh=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temporary.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None,
                               headers={"Content-Type": "application/json", **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_inspection_requires_same_origin_auth_and_does_not_record(self):
        route = "/api/capabilities/claude-capture/inspect"
        with mock.patch.object(self.server.service, "inspect_claude_capture", return_value={"actual_capture_performed": False}) as inspect:
            self.assertEqual(self.request("POST", route, {})[0], 403)
            self.assertEqual(self.request("POST", route, {}, {"X-Studio-Token": self.token, "Origin": "https://evil.example"})[0], 403)
            self.assertEqual(self.request("POST", route, {}, {"X-Studio-Token": self.token}), (200, {"actual_capture_performed": False}))
            inspect.assert_called_once()
            self.assertEqual(len(inspect.call_args.kwargs["session_binding_digest"]), 64)

    def test_source_post_and_lookup_are_exact_routes(self):
        route = f"/api/productions/{PRODUCTION}/claude-captures"
        body = {"request_id": REQUEST, "selection_token": TOKEN, "duration_ms": 15000, "confirm_capture": True}
        expected = {"id": "job_test", "kind": "claude_window_capture"}
        with mock.patch.object(self.server.service, "execute_claude_capture", return_value=expected) as execute:
            self.assertEqual(self.request("POST", route, body, {"X-Studio-Token": self.token}), (202, expected))
            self.assertEqual(execute.call_args.args, (PRODUCTION, body))
        with mock.patch.object(self.server.service, "claude_capture_job", return_value=expected) as lookup:
            self.assertEqual(self.request("GET", route + "/" + REQUEST, headers={"X-Studio-Token": self.token}), (200, expected))
            lookup.assert_called_once_with(PRODUCTION, REQUEST)
        with mock.patch.object(self.server.service, "claude_capture_job", return_value=None):
            self.assertEqual(self.request("GET", route + "/" + REQUEST, headers={"X-Studio-Token": self.token})[0], 404)


if __name__ == "__main__":
    unittest.main()
