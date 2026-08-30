from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.jobs import JobCancelled
from tools.studio.service import RequestValidationError, StudioService
from tools.studio.windows_capture import (
    WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
    WindowsCaptureError,
)


PRODUCTION_ID = "TEST_20260830_windows_capture"
TOOL_IDENTITY_DIGEST = "A" * 64
SESSION_BINDING_DIGEST = "B" * 64


class WindowsCaptureServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        source = self.workspace / "productions" / PRODUCTION_ID
        output = self.workspace / "outputs" / "productions" / PRODUCTION_ID
        (source / "manifests").mkdir(parents=True)
        output.mkdir(parents=True)
        (source / "PRODUCTION_RECORD_JA.md").write_text(
            f"# {PRODUCTION_ID}\n", encoding="utf-8"
        )
        (source / "manifests" / "source-hashes.json").write_text(
            json.dumps(
                {
                    "production_id": PRODUCTION_ID,
                    "status": "draft",
                    "technical_status": "pending",
                    "creative_status": "pending",
                    "public_release_status": "blocked",
                }
            ),
            encoding="utf-8",
        )
        self.service = StudioService(self.workspace)
        self.service.indexer.refresh()
        self.capability = {
            "status": "ready",
            "foundation_ready": True,
            "capture_execution_enabled": True,
            "actual_capture_performed": False,
            "helper": {"recording_started": False},
            "tool_identity_digest": TOOL_IDENTITY_DIGEST,
        }
        self.request = {
            "schema_version": 1,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cursor_mode": "hidden",
            "duration_ms": 1_000,
            "confirm_capture": True,
            "confirm_system_audio": True,
        }

    def _consented_body(
        self, run_id: str, request: dict[str, object] | None = None
    ) -> tuple[dict[str, object], dict[str, object]]:
        capture_request = dict(request or self.request)
        consent = self.service.issue_windows_capture_consent(
            run_id,
            capture_request,
            session_binding_digest=SESSION_BINDING_DIGEST,
        )
        return {**capture_request, "consent_token": consent["consent_token"]}, consent

    def _execute(
        self, run_id: str, body: dict[str, object]
    ) -> dict[str, object]:
        return self.service.execute_windows_capture(
            run_id,
            body,
            session_binding_digest=SESSION_BINDING_DIGEST,
        )

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def _run(self) -> str:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "screen_capture", "note": "native app"}],
                "estimated_cost": {"amount": 0, "currency": "JPY"},
                "execution_profile": "local_windows_capture",
            },
        )
        run = created["run"]
        self.assertEqual(run["execution_profile"], "local_windows_capture")
        self.assertEqual(
            set(run["requested_stages"]), {"screen_capture", "timeline"}
        )
        self.assertEqual(
            set(created["revision"]["rerun_plan"]["affected_stages"]),
            {"screen_capture", "timeline", "assembly", "qc"},
        )
        return str(run["id"])

    def _capture_directory(self, run_id: str, capture_key: str) -> Path:
        return (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / capture_key
        )

    def _fake_worker(self, *args: object, **kwargs: object) -> dict[str, object]:
        del args
        run_id = str(kwargs["run_id"])
        capture_key = str(kwargs["capture_key"])
        payload = kwargs["payload"]
        assert isinstance(payload, dict)
        tool_digest = str(kwargs["expected_tool_identity_digest"])
        directory = self._capture_directory(run_id, capture_key)
        directory.mkdir(parents=True, exist_ok=True)
        specs = {
            "screen-capture.mp4": ("video", "video/mp4"),
            "screen-video.mp4": ("video", "video/mp4"),
            "system-audio.wav": ("audio", "audio/wav"),
            "first-frame.png": ("image", "image/png"),
            "last-frame.png": ("image", "image/png"),
            "capture-report.json": ("document", "application/json"),
            "ffprobe.json": ("document", "application/json"),
            "manifest.json": ("document", "application/json"),
        }
        artifacts: list[dict[str, object]] = []
        for name, (kind, media_type) in specs.items():
            content = f"verified-{name}".encode("utf-8")
            path = directory / name
            if not path.exists():
                path.write_bytes(content)
            actual = path.read_bytes()
            artifacts.append(
                {
                    "name": name,
                    "rel_path": path.relative_to(self.workspace).as_posix(),
                    "kind": kind,
                    "media_type": media_type,
                    "bytes": len(actual),
                    "sha256": hashlib.sha256(actual).hexdigest().upper(),
                }
            )
        return {
            "artifacts": artifacts,
            "duration_ms": payload["duration_ms"],
            "capture_key": capture_key,
            "cache_hit": False,
            "provider": "local_windows_capture",
            "provider_task_id": None,
            "actual_cost": 0,
            "timing_source": "ffprobe",
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "actual_capture_performed": True,
            "structural_timing_verified": True,
            "content_sync_verified": False,
            "live_validation_required": True,
            "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
            "public_release_ready": False,
            "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
            "tool_identity_digest": tool_digest,
        }

    def _discard(self, *args: object, **kwargs: object) -> bool:
        del args
        directory = self._capture_directory(
            str(kwargs["run_id"]), str(kwargs["capture_key"])
        )
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)
            return True
        return False

    def _worker_patches(self) -> tuple[mock._patch, ...]:
        return (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.validate_windows_capture_outputs",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=self._discard,
            ),
        )

    def test_profile_job_lineage_and_exact_artifacts_commit_atomically(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        capability, generate, validate, discard = self._worker_patches()
        with (
            capability,
            generate as generate_mock,
            validate as validate_mock,
            discard as discard_mock,
        ):
            queued = self._execute(run_id, execution_body)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertFalse(queued["deduplicated"])
        self.assertEqual(completed["kind"], "local_windows_capture")
        self.assertEqual(completed["payload"]["stage"], "screen_capture")
        self.assertEqual(
            completed["payload"]["request_digest"], queued["request_digest"]
        )
        self.assertEqual(
            completed["payload"]["tool_identity_digest"], TOOL_IDENTITY_DIGEST
        )
        self.assertEqual(len(completed["result"]["artifacts"]), 8)
        self.assertTrue(completed["result"]["structural_timing_verified"])
        self.assertFalse(completed["result"]["content_sync_verified"])
        self.assertTrue(completed["result"]["live_validation_required"])
        self.assertFalse(completed["result"]["public_release_ready"])
        self.assertEqual(
            {item["name"] for item in completed["result"]["artifacts"]},
            {
                "screen-capture.mp4",
                "screen-video.mp4",
                "system-audio.wav",
                "first-frame.png",
                "last-frame.png",
                "capture-report.json",
                "ffprobe.json",
                "manifest.json",
            },
        )
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["status"], "succeeded")
        self.assertEqual(attempt["job_id"], queued["id"])
        job_result = dict(completed["result"])
        self.assertEqual(job_result.pop("stage_attempt_id"), attempt["id"])
        self.assertEqual(attempt["result"], job_result)
        self.assertEqual(completed["progress"], 100)
        self.assertEqual(completed["progress_phase"], "completed")
        generate_mock.assert_called_once()
        validate_mock.assert_called_once()
        discard_mock.assert_not_called()

    def test_active_same_request_deduplicates_but_different_request_is_conflict(
        self,
    ) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        entered = threading.Event()
        release = threading.Event()

        def blocked_generate(*args: object, **kwargs: object) -> dict[str, object]:
            entered.set()
            self.assertTrue(release.wait(5))
            return self._fake_worker(*args, **kwargs)

        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=blocked_generate,
            ) as generate,
            mock.patch(
                "tools.studio.windows_capture_worker.validate_windows_capture_outputs",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=self._discard,
            ),
        ):
            first = self._execute(run_id, execution_body)
            self.assertTrue(entered.wait(5))
            duplicate = self._execute(run_id, execution_body)
            self.assertEqual(duplicate["id"], first["id"])
            self.assertEqual(
                duplicate["stage_attempt_id"], first["stage_attempt_id"]
            )
            self.assertTrue(duplicate["deduplicated"])

            changed = dict(self.request)
            changed["duration_ms"] = 1_500
            changed_body, _changed_consent = self._consented_body(run_id, changed)
            with self.assertRaises(RequestValidationError) as busy:
                self._execute(run_id, changed_body)
            self.assertEqual(busy.exception.code, "windows_capture_busy")
            detail = self.service.run(run_id)
            assert detail is not None
            self.assertEqual(len(detail["stage_attempts"]), 1)
            self.assertEqual(
                self.service.jobs.active_job_ids_for_lane("capture"),
                (first["id"],),
            )
            release.set()
            completed = self.service.jobs.wait(first["id"], timeout=10)

        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(generate.call_count, 1)

    def test_terminal_replay_returns_original_job_and_fresh_token_records_again(
        self,
    ) -> None:
        run_id = self._run()
        first_body, first_consent = self._consented_body(run_id)
        capability, generate, validate, discard = self._worker_patches()
        with capability, generate as generate_mock, validate, discard:
            first = self._execute(run_id, first_body)
            first_completed = self.service.jobs.wait(first["id"], timeout=10)
        assert first_completed is not None
        self.assertEqual(first_completed["status"], "succeeded")

        # A terminal replay must not even re-inspect tools, much less enqueue
        # another worker. It resolves only through the consumed DB lineage.
        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                side_effect=AssertionError("terminal replay inspected tools"),
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=AssertionError("terminal replay recorded again"),
            ),
        ):
            replay = self._execute(run_id, first_body)
        self.assertEqual(replay["id"], first["id"])
        self.assertEqual(replay["status"], "succeeded")
        self.assertTrue(replay["deduplicated"])
        self.assertEqual(generate_mock.call_count, 1)
        self.assertEqual(len(self.service.run(run_id)["stage_attempts"]), 1)

        second_body, second_consent = self._consented_body(run_id)
        self.assertNotEqual(
            second_consent["consent_token"], first_consent["consent_token"]
        )
        capability, generate, validate, discard = self._worker_patches()
        with capability, generate, validate, discard:
            second = self._execute(run_id, second_body)
            second_completed = self.service.jobs.wait(second["id"], timeout=10)
        assert second_completed is not None
        self.assertEqual(second_completed["status"], "succeeded")
        self.assertNotEqual(second["id"], first["id"])
        self.assertFalse(second["deduplicated"])
        self.assertEqual(len(self.service.run(run_id)["stage_attempts"]), 2)

    def test_consent_is_session_run_and_settings_bound_and_raw_token_is_not_stored(
        self,
    ) -> None:
        run_id = self._run()
        body, consent = self._consented_body(run_id)
        raw_token = str(consent["consent_token"])
        self.assertNotIn(raw_token.encode("ascii"), self.service.database.path.read_bytes())
        mirror = self.service.database.event_mirror_path("run", run_id)
        self.assertNotIn(raw_token.encode("ascii"), mirror.read_bytes())

        with self.assertRaises(RequestValidationError) as wrong_session:
            self.service.execute_windows_capture(
                run_id,
                body,
                session_binding_digest="C" * 64,
            )
        self.assertEqual(
            wrong_session.exception.code, "windows_capture_consent_invalid"
        )

        changed = dict(body)
        changed["duration_ms"] = 1_500
        with self.assertRaises(RequestValidationError) as wrong_settings:
            self._execute(run_id, changed)
        self.assertEqual(
            wrong_settings.exception.code, "windows_capture_consent_invalid"
        )

        other_run = self._run()
        with self.assertRaises(RequestValidationError) as wrong_run:
            self._execute(other_run, body)
        self.assertEqual(wrong_run.exception.code, "windows_capture_consent_invalid")
        self.assertEqual(self.service.run(run_id)["stage_attempts"], [])
        self.assertEqual(self.service.run(other_run)["stage_attempts"], [])

    def test_process_boundary_invalidates_unconsumed_consent(self) -> None:
        run_id = self._run()
        body, _consent = self._consented_body(run_id)
        counts = self.service.database.interrupt_active_work()
        self.assertEqual(counts["windows_capture_consents"], 1)
        with mock.patch(
            "tools.studio.service.inspect_windows_capture_capability_environment",
            side_effect=AssertionError("invalidated consent inspected tools"),
        ):
            with self.assertRaises(RequestValidationError) as rejected:
                self._execute(run_id, body)
        self.assertEqual(rejected.exception.code, "windows_capture_consent_invalid")
        self.assertEqual(self.service.run(run_id)["stage_attempts"], [])

    def test_expired_consent_is_rejected_before_tool_inspection(self) -> None:
        run_id = self._run()
        body, _consent = self._consented_body(run_id)
        with (
            mock.patch(
                "tools.studio.database.utc_now",
                return_value="9999-12-31T23:59:59.999Z",
            ),
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                side_effect=AssertionError("expired consent inspected tools"),
            ),
        ):
            with self.assertRaises(RequestValidationError) as rejected:
                self._execute(run_id, body)
        self.assertEqual(rejected.exception.code, "windows_capture_consent_expired")
        self.assertEqual(self.service.run(run_id)["stage_attempts"], [])

    def test_startup_fails_closed_when_stale_partial_cleanup_fails(self) -> None:
        alternate_database = (
            self.workspace / "outputs" / "studio" / "cleanup-blocked.sqlite3"
        )
        with mock.patch(
            "tools.studio.windows_capture_worker.cleanup_stale_windows_capture_partials",
            side_effect=WindowsCaptureError(
                "Stale Windows capture cleanup failed.",
                code="windows_capture_cleanup_failed",
            ),
        ):
            with self.assertRaises(WindowsCaptureError) as blocked:
                StudioService(self.workspace, database_path=alternate_database)
        self.assertEqual(blocked.exception.error_code, "windows_capture_cleanup_failed")

    def test_startup_fails_closed_when_cleanup_database_query_fails(self) -> None:
        alternate_database = (
            self.workspace / "outputs" / "studio" / "cleanup-query-blocked.sqlite3"
        )
        with mock.patch(
            "tools.studio.database.StudioDatabase.list_windows_capture_cleanup_candidates",
            side_effect=sqlite3.OperationalError("query denied"),
        ):
            with self.assertRaises(WindowsCaptureError) as blocked:
                StudioService(self.workspace, database_path=alternate_database)
        self.assertEqual(blocked.exception.error_code, "windows_capture_cleanup_failed")

    def test_restart_cleans_fallback_ledger_after_stage_marker_write_denied(
        self,
    ) -> None:
        from tools.studio import windows_capture_worker

        run_id = self._run()
        capture_key = "B" * 64
        target = self._capture_directory(run_id, capture_key)
        target.mkdir(parents=True)
        (target / "private.mp4").write_bytes(b"private")

        with (
            mock.patch(
                "tools.studio.windows_capture_worker.shutil.rmtree",
                side_effect=OSError("locked"),
            ),
            mock.patch(
                "tools.studio.windows_capture_worker._mark_cleanup_failure",
                return_value=False,
            ),
            mock.patch("tools.studio.windows_capture_worker.time.sleep"),
        ):
            with self.assertRaises(WindowsCaptureError) as failed:
                windows_capture_worker.discard_windows_capture_outputs(
                    self.workspace,
                    run_id=run_id,
                    capture_key=capture_key,
                )
        self.assertEqual(failed.exception.error_code, "windows_capture_cleanup_failed")
        ledger = (
            self.workspace
            / "outputs"
            / "studio"
            / "windows-capture-cleanup-ledger.json"
        )
        self.assertTrue(target.is_dir())
        self.assertEqual(len(json.loads(ledger.read_text(encoding="utf-8"))["entries"]), 1)

        # A restart loses only the in-memory latch. Studio startup must recover
        # the exact ledger target before it creates any worker infrastructure.
        self.service.close()
        with windows_capture_worker._CLEANUP_BLOCKED_STAGES_LOCK:
            windows_capture_worker._CLEANUP_BLOCKED_STAGES.clear()
            windows_capture_worker._CLEANUP_BLOCKED_WORKSPACES.clear()
        self.service = StudioService(self.workspace)

        self.assertFalse(target.exists())
        self.assertEqual(
            json.loads(ledger.read_text(encoding="utf-8"))["entries"], []
        )

    def test_queue_admission_failure_consumes_token_and_replay_returns_failed_job(
        self,
    ) -> None:
        run_id = self._run()
        body, _consent = self._consented_body(run_id)
        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch.object(
                self.service.jobs._queues["capture"],
                "put",
                side_effect=RuntimeError("test queue rejection"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                self._execute(run_id, body)
        detail = self.service.run(run_id)
        assert detail is not None
        self.assertEqual(len(detail["stage_attempts"]), 1)
        attempt = detail["stage_attempts"][0]
        self.assertEqual(attempt["status"], "failed")
        job_id = attempt["job_id"]

        with mock.patch(
            "tools.studio.service.inspect_windows_capture_capability_environment",
            side_effect=AssertionError("failed admission replay inspected tools"),
        ):
            replay = self._execute(run_id, body)
        self.assertEqual(replay["id"], job_id)
        self.assertEqual(replay["status"], "failed")
        self.assertTrue(replay["deduplicated"])
        self.assertEqual(len(self.service.run(run_id)["stage_attempts"]), 1)

    def test_cancel_endpoint_retires_only_native_job_and_discards_output(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        validation_entered = threading.Event()

        def wait_for_cancel(
            *args: object,
            cancel_event: threading.Event | None = None,
            **kwargs: object,
        ) -> dict[str, object]:
            del args, kwargs
            assert cancel_event is not None
            validation_entered.set()
            self.assertTrue(cancel_event.wait(5))
            raise JobCancelled()

        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.validate_windows_capture_outputs",
                new=wait_for_cancel,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=self._discard,
            ) as discard,
        ):
            queued = self._execute(run_id, execution_body)
            self.assertTrue(validation_entered.wait(5))
            response = self.service.cancel_windows_capture_job(queued["id"], {})
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertTrue(response["cancel_requested"])
        self.assertEqual(completed["status"], "interrupted")
        self.assertFalse(
            self._capture_directory(run_id, queued["capture_key"]).exists()
        )
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["status"], "failed")
        self.assertGreaterEqual(discard.call_count, 1)

        ordinary = self.service.database.create_job("index_refresh", {})
        with self.assertRaises(RequestValidationError) as wrong_kind:
            self.service.cancel_windows_capture_job(ordinary["id"], {})
        self.assertEqual(
            wrong_kind.exception.code, "windows_capture_job_required"
        )
        with self.assertRaises(RequestValidationError):
            self.service.cancel_windows_capture_job(queued["id"], {"force": True})

    def test_cancel_cleanup_failure_is_durable_and_not_reported_as_interrupted(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        validation_entered = threading.Event()

        def wait_for_cancel(
            *args: object,
            cancel_event: threading.Event | None = None,
            **kwargs: object,
        ) -> dict[str, object]:
            del args, kwargs
            assert cancel_event is not None
            validation_entered.set()
            self.assertTrue(cancel_event.wait(5))
            raise JobCancelled()

        cleanup_error = WindowsCaptureError(
            "Private Windows capture data could not be removed.",
            code="windows_capture_cleanup_failed",
        )
        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.validate_windows_capture_outputs",
                new=wait_for_cancel,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=cleanup_error,
            ),
        ):
            queued = self._execute(run_id, execution_body)
            self.assertTrue(validation_entered.wait(5))
            self.service.cancel_windows_capture_job(queued["id"], {})
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(
            completed["error"]["code"], "windows_capture_cleanup_failed"
        )
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["error"], completed["error"])

    def test_atomic_commit_failure_discards_unregistered_capture_directory(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        capability, generate, validate, discard = self._worker_patches()
        with (
            capability,
            generate,
            validate,
            discard as discard_mock,
            mock.patch.object(
                self.service.database,
                "complete_job_with_stage_attempt",
                side_effect=sqlite3.IntegrityError("test atomic rejection"),
            ),
        ):
            queued = self._execute(run_id, execution_body)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertFalse(
            self._capture_directory(run_id, queued["capture_key"]).exists()
        )
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["status"], "failed")
        discard_mock.assert_called_once()

    def test_atomic_commit_cleanup_failure_replaces_generic_database_error(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        capability, generate, validate, _discard = self._worker_patches()
        cleanup_error = WindowsCaptureError(
            "Published Windows capture data could not be removed.",
            code="windows_capture_cleanup_failed",
        )
        with (
            capability,
            generate,
            validate,
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=cleanup_error,
            ),
            mock.patch.object(
                self.service.database,
                "complete_job_with_stage_attempt",
                side_effect=sqlite3.IntegrityError("test atomic rejection"),
            ),
        ):
            queued = self._execute(run_id, execution_body)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(
            completed["error"]["code"], "windows_capture_cleanup_failed"
        )
        self.assertEqual(attempt["error"], completed["error"])

    def test_invalid_request_or_unavailable_capability_creates_no_attempt(self) -> None:
        run_id = self._run()
        invalid = dict(self.request)
        invalid["confirm_system_audio"] = False
        invalid["consent_token"] = "A" * 43
        with self.assertRaises(RequestValidationError) as rejected:
            self._execute(run_id, invalid)
        self.assertEqual(
            rejected.exception.code, "invalid_windows_capture_request"
        )

        blocked = dict(self.capability)
        blocked["capture_execution_enabled"] = False
        execution_body, _consent = self._consented_body(run_id)
        with mock.patch(
            "tools.studio.service.inspect_windows_capture_capability_environment",
            return_value=blocked,
        ):
            with self.assertRaises(RequestValidationError) as unavailable:
                self._execute(run_id, execution_body)
        self.assertEqual(unavailable.exception.code, "windows_capture_unavailable")
        detail = self.service.run(run_id)
        assert detail is not None
        self.assertEqual(detail["stage_attempts"], [])

    def test_unknown_worker_failure_is_redacted_and_fails_job_attempt_pair(self) -> None:
        run_id = self._run()
        execution_body, _consent = self._consented_body(run_id)
        secret = "C:\\private\\capture\\SECRET-INTERNAL-COMMAND"
        with (
            mock.patch(
                "tools.studio.service.inspect_windows_capture_capability_environment",
                return_value=self.capability,
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.generate_windows_capture",
                side_effect=RuntimeError(secret),
            ),
        ):
            queued = self._execute(run_id, execution_body)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(completed["error"]["code"], "windows_capture_failed")
        self.assertEqual(attempt["error"], completed["error"])
        self.assertNotIn(secret, completed["error"]["message"])
        self.assertNotIn(secret.encode("utf-8"), self.service.database.path.read_bytes())
        mirror = self.service.database.event_mirror_path(
            "production", PRODUCTION_ID
        )
        self.assertNotIn(secret.encode("utf-8"), mirror.read_bytes())

    def test_restart_cleans_only_database_lineage_with_cleanup_error(self) -> None:
        run_id = self._run()

        def failed_capture(capture_key: str, error_code: str) -> tuple[str, str]:
            attempt = self.service.database.create_stage_attempt(
                run_id,
                "screen_capture",
                capture_key,
                {
                    "execution_profile": "local_windows_capture",
                    "capture_key": capture_key,
                },
            )
            job = self.service.database.create_job(
                "local_windows_capture",
                {
                    "run_id": run_id,
                    "production_id": PRODUCTION_ID,
                    "stage": "screen_capture",
                    "execution_profile": "local_windows_capture",
                    "capture_key": capture_key,
                    "stage_attempt_id": attempt["id"],
                },
                production_id=PRODUCTION_ID,
            )
            self.service.database.link_stage_attempt_job(attempt["id"], job["id"])
            self.service.database.update_job(job["id"], "running")
            self.service.database.update_stage_attempt(attempt["id"], "running")
            self.service.database.fail_job_with_stage_attempt(
                job["id"],
                attempt["id"],
                error_code=error_code,
                error_message="Fixed public failure.",
            )
            return job["id"], attempt["id"]

        cleanup_key = "B" * 64
        general_key = "C" * 64
        failed_capture(cleanup_key, "windows_capture_cleanup_failed")
        failed_capture(general_key, "windows_capture_failed")
        cleanup_target = self._capture_directory(run_id, cleanup_key)
        general_target = self._capture_directory(run_id, general_key)
        cleanup_target.mkdir(parents=True)
        general_target.mkdir(parents=True)
        (cleanup_target / "private.mp4").write_bytes(b"private cleanup residual")
        (general_target / "keep.mp4").write_bytes(b"general failed job")

        self.service.close()
        self.service = StudioService(self.workspace)

        self.assertFalse(cleanup_target.exists())
        self.assertTrue(general_target.is_dir())
        self.assertTrue((general_target / "keep.mp4").is_file())

    def test_interrupted_startup_cleanup_fails_closed_before_any_ambiguous_lineage(
        self,
    ) -> None:
        run_id = self._run()
        capture_key = "B" * 64
        attempt = self.service.database.create_stage_attempt(
            run_id,
            "screen_capture",
            capture_key,
            {
                "execution_profile": "local_windows_capture",
                "capture_key": capture_key,
            },
        )
        job = self.service.database.create_job(
            "local_windows_capture",
            {
                "run_id": run_id,
                "production_id": PRODUCTION_ID,
                "stage": "screen_capture",
                "execution_profile": "local_windows_capture",
                "capture_key": capture_key,
                "stage_attempt_id": attempt["id"],
            },
            production_id=PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(attempt["id"], job["id"])
        self.service.database.update_job(job["id"], "running")
        self.service.database.update_stage_attempt(attempt["id"], "running")
        self.assertTrue(self.service.database.interrupt_job(job["id"]))
        directory = self._capture_directory(run_id, capture_key)
        directory.mkdir(parents=True)
        (directory / "partial.tmp").write_bytes(b"private partial capture")

        victim_key = "C" * 64
        mismatched_attempt = self.service.database.create_stage_attempt(
            run_id,
            "screen_capture",
            "D" * 64,
            {
                "execution_profile": "local_windows_capture",
                "capture_key": "D" * 64,
            },
        )
        mismatched_job = self.service.database.create_job(
            "local_windows_capture",
            {
                "run_id": run_id,
                "production_id": PRODUCTION_ID,
                "stage": "screen_capture",
                "execution_profile": "local_windows_capture",
                "capture_key": victim_key,
                "stage_attempt_id": mismatched_attempt["id"],
            },
            production_id=PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(
            mismatched_attempt["id"], mismatched_job["id"]
        )
        self.service.database.update_job(mismatched_job["id"], "running")
        self.service.database.update_stage_attempt(
            mismatched_attempt["id"], "running"
        )
        self.assertTrue(
            self.service.database.interrupt_job(mismatched_job["id"])
        )
        victim = self._capture_directory(run_id, victim_key)
        victim.mkdir(parents=True)
        (victim / "keep.tmp").write_bytes(b"must survive ambiguous lineage")

        exact_candidate = self.service.database.get_job(job["id"])
        ambiguous_candidate = self.service.database.get_job(mismatched_job["id"])
        assert exact_candidate is not None
        assert ambiguous_candidate is not None
        with (
            mock.patch.object(
                self.service.database,
                "list_windows_capture_cleanup_candidates",
                return_value=[exact_candidate, ambiguous_candidate],
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=self._discard,
            ) as discard,
        ):
            with self.assertRaises(WindowsCaptureError) as blocked:
                self.service._cleanup_interrupted_windows_capture_outputs()

        self.assertEqual(
            blocked.exception.error_code, "windows_capture_cleanup_failed"
        )
        discard.assert_not_called()
        self.assertTrue(directory.is_dir())
        self.assertTrue((directory / "partial.tmp").is_file())
        self.assertTrue(victim.is_dir())
        self.assertTrue((victim / "keep.tmp").is_file())

    def test_process_interrupted_cleanup_preserves_any_registered_artifact_truth(
        self,
    ) -> None:
        run_id = self._run()
        capture_key = "B" * 64
        attempt = self.service.database.create_stage_attempt(
            run_id,
            "screen_capture",
            capture_key,
            {
                "execution_profile": "local_windows_capture",
                "capture_key": capture_key,
            },
        )
        job = self.service.database.create_job(
            "local_windows_capture",
            {
                "run_id": run_id,
                "production_id": PRODUCTION_ID,
                "stage": "screen_capture",
                "execution_profile": "local_windows_capture",
                "capture_key": capture_key,
                "stage_attempt_id": attempt["id"],
            },
            production_id=PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(attempt["id"], job["id"])
        self.service.database.update_job(job["id"], "running")
        self.service.database.update_stage_attempt(attempt["id"], "running")
        self.assertTrue(self.service.database.interrupt_job(job["id"]))
        directory = self._capture_directory(run_id, capture_key)
        directory.mkdir(parents=True)
        (directory / "partial.tmp").write_bytes(b"preserve registered truth")

        # Even an unavailable registry row proves this target is not cleanly
        # unregistered; its publication history cannot be guessed at startup.
        with (
            mock.patch.object(
                self.service.database,
                "get_artifact",
                return_value={"available": False},
            ),
            mock.patch(
                "tools.studio.windows_capture_worker.discard_windows_capture_outputs",
                side_effect=self._discard,
            ) as discard,
        ):
            with self.assertRaises(WindowsCaptureError) as blocked:
                self.service._cleanup_interrupted_windows_capture_outputs()

        self.assertEqual(
            blocked.exception.error_code, "windows_capture_cleanup_failed"
        )
        discard.assert_not_called()
        self.assertTrue(directory.is_dir())
        self.assertTrue((directory / "partial.tmp").is_file())


if __name__ == "__main__":
    unittest.main()
