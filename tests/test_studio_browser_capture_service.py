from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.jobs import JobCancelled
from tools.studio.service import RequestValidationError, StudioService


PRODUCTION_ID = "TEST_20260825_playwright_capture"


class BrowserCaptureServiceTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def _run(self) -> str:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "screen_capture", "note": "capture UI"}],
                "estimated_cost": {"amount": 0, "currency": "JPY"},
                "execution_profile": "local_playwright",
            },
        )
        run = created["run"]
        self.assertEqual(run["execution_profile"], "local_playwright")
        self.assertEqual(
            set(run["requested_stages"]),
            {"screen_capture", "timeline"},
        )
        self.assertEqual(
            set(created["revision"]["rerun_plan"]["affected_stages"]),
            {"screen_capture", "timeline", "assembly", "qc"},
        )
        return str(run["id"])

    def _fake_worker(self, *args: object, **kwargs: object) -> dict[str, object]:
        del args
        run_id = str(kwargs["run_id"])
        capture_key = str(kwargs["capture_key"])
        payload = kwargs["payload"]
        assert isinstance(payload, dict)
        directory = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / capture_key
        )
        directory.mkdir(parents=True, exist_ok=True)
        specs = {
            "screen-capture.mp4": ("video", "video/mp4"),
            "playwright-raw.webm": ("video", "video/webm"),
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
        result = {
            "artifacts": artifacts,
            "duration_ms": payload["duration_ms"],
            "capture_key": capture_key,
            "cache_hit": False,
            "provider": "local_playwright",
            "provider_task_id": None,
            "actual_cost": 0,
            "timing_source": "ffprobe",
            "target_origin": payload["target"]["origin"],
        }
        if payload.get("viewport_preset") == "desktop_16_9":
            result["viewport_preset"] = "desktop_16_9"
            result["video_dimensions"] = {"width": 1920, "height": 1080}
        return result

    def test_desktop_capture_metadata_reaches_job_attempt_and_registered_artifacts(self) -> None:
        run_id = self._run()
        request = {"url": "http://127.0.0.1:8765/", "duration_ms": 1000,
                   "settle_ms": 0, "actions": [], "viewport_preset": "desktop_16_9"}
        with (
            mock.patch("tools.studio.browser_capture.generate_local_screen_capture", side_effect=self._fake_worker),
            mock.patch("tools.studio.browser_capture.validate_local_screen_capture_outputs", side_effect=self._fake_worker),
        ):
            queued = self.service.execute_local_screen_capture(run_id, request)
            completed = self.service.jobs.wait(queued["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["payload"]["viewport_preset"], "desktop_16_9")
        self.assertEqual(completed["payload"]["canvas"], {"width": 1920, "height": 1080})
        self.assertEqual(completed["result"]["viewport_preset"], "desktop_16_9")
        self.assertEqual(completed["result"]["video_dimensions"], {"width": 1920, "height": 1080})
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["result"]["video_dimensions"], {"width": 1920, "height": 1080})
        self.assertEqual(len(completed["result"]["artifacts"]), 7)
        for artifact in completed["result"]["artifacts"]:
            self.assertIsNotNone(self.service.database.get_artifact(artifact["id"]))

    def test_capture_job_exposes_bounded_running_progress_and_terminal_completion(self) -> None:
        job = self.service.database.create_job(
            "local_screen_capture",
            {"run_id": "run-progress", "stage": "screen_capture"},
            production_id=PRODUCTION_ID,
        )
        self.service.database.update_job(job["id"], "running")
        self.service.database.update_job_progress(job["id"], 60, "transcoding")
        running = self.service.database.get_job(job["id"])
        assert running is not None
        self.assertEqual(running["progress"], 60)
        self.assertEqual(running["progress_phase"], "transcoding")

        self.service.database.update_job(job["id"], "succeeded", result={"ok": True})
        completed = self.service.database.get_job(job["id"])
        assert completed is not None
        self.assertEqual(completed["progress"], 100)
        self.assertEqual(completed["progress_phase"], "completed")

    def test_capture_worker_progress_is_visible_while_browser_lane_is_running(self) -> None:
        run_id = self._run()
        progress_written = threading.Event()
        release_worker = threading.Event()

        def worker(*args: object, **kwargs: object) -> dict[str, object]:
            callback = kwargs.get("progress_callback")
            assert callable(callback)
            callback(60, "transcoding")
            progress_written.set()
            self.assertTrue(release_worker.wait(5))
            return self._fake_worker(*args, **kwargs)

        request = {
            "url": "http://127.0.0.1:8765/",
            "duration_ms": 1_000,
            "settle_ms": 0,
            "actions": [],
        }
        with (
            mock.patch(
                "tools.studio.browser_capture.generate_local_screen_capture",
                side_effect=worker,
            ),
            mock.patch(
                "tools.studio.browser_capture.validate_local_screen_capture_outputs",
                side_effect=self._fake_worker,
            ),
        ):
            queued = self.service.execute_local_screen_capture(run_id, request)
            self.assertTrue(progress_written.wait(5))
            running = self.service.database.get_job(queued["id"])
            assert running is not None
            self.assertEqual(running["status"], "running")
            self.assertEqual(running["progress"], 60)
            self.assertEqual(running["progress_phase"], "transcoding")
            release_worker.set()
            completed = self.service.jobs.wait(queued["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")

    def test_atomic_commit_failure_discards_unregistered_capture_directory(self) -> None:
        run_id = self._run()
        request = {
            "url": "http://127.0.0.1:8765/",
            "duration_ms": 1_000,
            "settle_ms": 0,
            "actions": [],
        }
        with (
            mock.patch(
                "tools.studio.browser_capture.generate_local_screen_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.browser_capture.validate_local_screen_capture_outputs",
                side_effect=self._fake_worker,
            ),
            mock.patch.object(
                self.service.database,
                "complete_job_with_stage_attempt",
                side_effect=sqlite3.IntegrityError("test atomic rejection"),
            ),
        ):
            queued = self.service.execute_local_screen_capture(run_id, request)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        capture_directory = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / queued["capture_key"]
        )
        self.assertFalse(capture_directory.exists())
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["status"], "failed")

    def test_cancel_after_publish_discards_unregistered_capture_directory(self) -> None:
        run_id = self._run()
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

        request = {
            "url": "http://127.0.0.1:8765/",
            "duration_ms": 1_000,
            "settle_ms": 0,
            "actions": [],
        }
        with (
            mock.patch(
                "tools.studio.browser_capture.generate_local_screen_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.browser_capture.validate_local_screen_capture_outputs",
                new=wait_for_cancel,
            ),
        ):
            queued = self.service.execute_local_screen_capture(run_id, request)
            self.assertTrue(validation_entered.wait(5))
            completed = self.service.jobs.cancel_and_wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertEqual(completed["status"], "interrupted")
        capture_directory = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / queued["capture_key"]
        )
        self.assertFalse(capture_directory.exists())
        attempt = self.service.database.get_stage_attempt(queued["stage_attempt_id"])
        assert attempt is not None
        self.assertEqual(attempt["status"], "failed")

    def test_profile_attempt_job_and_atomic_artifacts_use_sanitized_audit(self) -> None:
        run_id = self._run()
        request = {
            "url": "http://127.0.0.1:8765/private?token=must-not-persist",
            "duration_ms": 1_000,
            "settle_ms": 0,
            "actions": [
                {"type": "click", "at_ms": 100, "selector": "#secret-selector"}
            ],
        }
        with (
            mock.patch(
                "tools.studio.browser_capture.generate_local_screen_capture",
                side_effect=self._fake_worker,
            ),
            mock.patch(
                "tools.studio.browser_capture.validate_local_screen_capture_outputs",
                side_effect=self._fake_worker,
            ),
        ):
            queued = self.service.execute_local_screen_capture(run_id, request)
            completed = self.service.jobs.wait(queued["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["payload"]["stage"], "screen_capture")
        self.assertNotIn("url", completed["payload"])
        self.assertEqual(len(completed["result"]["artifacts"]), 7)
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        run = next(item for item in detail["runs"] if item["id"] == run_id)
        attempt = next(item for item in run["stage_attempts"] if item["stage"] == "screen_capture")
        self.assertEqual(attempt["status"], "succeeded")
        self.assertEqual(attempt["job_id"], queued["id"])
        persisted = self.service.database.path.read_bytes()
        mirror = self.service.database.event_mirror_path("production", PRODUCTION_ID).read_bytes()
        for secret in (b"must-not-persist", b"secret-selector"):
            self.assertNotIn(secret, persisted)
            self.assertNotIn(secret, mirror)

    def test_profile_and_public_payload_fail_closed_before_enqueue(self) -> None:
        external = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "screen_capture"}],
                "estimated_cost": {"amount": 0, "currency": "JPY"},
                "execution_profile": "external",
            },
        )
        with self.assertRaises(RequestValidationError) as profile:
            self.service.execute_local_screen_capture(
                external["run"]["id"],
                {
                    "url": "http://127.0.0.1:8765/",
                    "duration_ms": 1_000,
                    "settle_ms": 0,
                    "actions": [],
                },
            )
        self.assertEqual(profile.exception.code, "execution_profile_required")

        run_id = self._run()
        with self.assertRaises(RequestValidationError) as invalid:
            self.service.execute_local_screen_capture(
                run_id,
                {
                    "url": "https://example.com/",
                    "duration_ms": 1_000,
                    "settle_ms": 0,
                    "actions": [],
                },
            )
        self.assertEqual(invalid.exception.code, "invalid_local_screen_capture_request")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        run = next(item for item in detail["runs"] if item["id"] == run_id)
        self.assertEqual(run["stage_attempts"], [])


if __name__ == "__main__":
    unittest.main()
