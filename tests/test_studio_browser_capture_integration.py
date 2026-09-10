from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

from tools.studio import browser_capture
from tools.studio.browser_capture_execution import (
    BrowserCaptureError,
    browser_capture_key,
    validate_browser_capture_payload,
)
from tools.studio.jobs import JobCancelled


REPO_ROOT = Path(__file__).resolve().parents[1]
_NO_FAILURE = object()


def _http_server(body: bytes, requests: list[str]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server._capture_thread = thread  # type: ignore[attr-defined]
    return server


class BrowserCaptureCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_discard_removes_only_capture_directory(self) -> None:
        run_id = "cleanup-run"
        capture_key = "A" * 64
        capture = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / capture_key
        )
        capture.mkdir(parents=True)
        (capture / "screen-capture.mp4").write_bytes(b"owned")
        parent = capture.parent

        self.assertTrue(
            browser_capture.discard_local_screen_capture_outputs(
                self.workspace, run_id=run_id, capture_key=capture_key
            )
        )
        self.assertFalse(capture.exists())
        self.assertTrue(parent.is_dir())

    def test_discard_fails_closed_for_symlink_capture_path(self) -> None:
        run_id = "symlink-run"
        capture_key = "B" * 64
        parent = (
            self.workspace / "outputs" / "studio" / "runs" / run_id / "screen_capture"
        )
        parent.mkdir(parents=True)
        outside = Path(self.temporary.name).resolve() / "outside"
        outside.mkdir()
        (outside / "marker").write_text("keep", encoding="utf-8")
        capture = parent / capture_key
        try:
            capture.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"directory symlinks are unavailable: {exc}")

        self.assertFalse(
            browser_capture.discard_local_screen_capture_outputs(
                self.workspace, run_id=run_id, capture_key=capture_key
            )
        )
        self.assertTrue(capture.is_symlink())
        self.assertTrue((outside / "marker").is_file())


class BrowserCaptureWorkerIntegrationTests(unittest.TestCase):
    """Run the Python worker through Node Playwright, Chromium and FFmpeg."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        cls.ffmpeg = shutil.which("ffmpeg")
        cls.ffprobe = shutil.which("ffprobe")
        if cls.node is None or cls.ffmpeg is None or cls.ffprobe is None:
            raise unittest.SkipTest("node, ffmpeg and ffprobe are required")
        package = REPO_ROOT / "studio" / "node_modules" / "playwright" / "package.json"
        if not package.is_file():
            raise unittest.SkipTest("studio/node_modules/playwright is not installed")
        probe = subprocess.run(
            [
                cls.node,
                "-e",
                "const { chromium } = require('./studio/node_modules/playwright'); process.stdout.write(chromium.executablePath());",
            ],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
        chromium = Path(probe.stdout.strip())
        if probe.returncode != 0 or not chromium.is_file():
            raise unittest.SkipTest("Playwright Chromium is not installed")

    def setUp(self) -> None:
        self.owned_capture_directories: list[Path] = []

    def tearDown(self) -> None:
        for capture in self.owned_capture_directories:
            if capture.is_dir() and not capture.is_symlink():
                shutil.rmtree(capture, ignore_errors=True)
            run_root = capture.parents[1]
            expected_runs = REPO_ROOT / "outputs" / "studio" / "runs"
            if (
                run_root.parent == expected_runs
                and run_root.name.startswith("test-browser-capture-")
                and run_root.is_dir()
                and not run_root.is_symlink()
            ):
                shutil.rmtree(run_root, ignore_errors=True)

    def _capture(
        self,
        run_id: str,
        *,
        validate_failure: object = _NO_FAILURE,
        viewport_preset: str | None = None,
    ) -> dict[str, Any]:
        progress_updates: list[tuple[int, str]] = []
        forbidden_requests: list[str] = []
        forbidden = _http_server(b"blocked", forbidden_requests)
        target_requests: list[str] = []
        forbidden_port = forbidden.server_address[1]
        page = f"""
<!doctype html>
<html><body>
<button id="capture-button" onclick="document.body.dataset.clicked='yes'">Capture</button>
<script>
  fetch('http://127.0.0.1:{forbidden_port}/secret?token=must-not-persist').catch(() => {{}});
</script>
</body></html>
""".encode("utf-8")
        target = _http_server(page, target_requests)
        target_port = target.server_address[1]
        request = {
            "url": f"http://127.0.0.1:{target_port}/?token=must-not-persist",
            "duration_ms": 1_200,
            "settle_ms": 100,
            "actions": [
                {"type": "click", "at_ms": 500, "selector": "#capture-button"}
            ],
        }
        if viewport_preset is not None:
            request["viewport_preset"] = viewport_preset
        payload = validate_browser_capture_payload(request)
        capture_key = browser_capture_key(payload, "c" * 32)
        capture_directory = (
            REPO_ROOT
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / capture_key
        )
        self.owned_capture_directories.append(capture_directory)
        try:
            if validate_failure is _NO_FAILURE:
                result = browser_capture.generate_local_screen_capture(
                    REPO_ROOT,
                    production_id="TEST_BROWSER_CAPTURE_INTEGRATION",
                    run_id=run_id,
                    capture_key=capture_key,
                    payload=payload,
                    node=self.node,
                    ffmpeg=self.ffmpeg,
                    ffprobe=self.ffprobe,
                    progress_callback=lambda progress, phase: progress_updates.append(
                        (progress, phase)
                    ),
                )
            else:
                with mock.patch.object(
                    browser_capture,
                    "_validate_capture",
                    side_effect=[None, validate_failure],
                ):
                    result = browser_capture.generate_local_screen_capture(
                        REPO_ROOT,
                        production_id="TEST_BROWSER_CAPTURE_INTEGRATION",
                        run_id=run_id,
                        capture_key=capture_key,
                        payload=payload,
                        node=self.node,
                        ffmpeg=self.ffmpeg,
                        ffprobe=self.ffprobe,
                        progress_callback=lambda progress, phase: progress_updates.append(
                            (progress, phase)
                        ),
                    )
        finally:
            target.shutdown()
            target.server_close()
            target._capture_thread.join(timeout=5)  # type: ignore[attr-defined]
            forbidden.shutdown()
            forbidden.server_close()
            forbidden._capture_thread.join(timeout=5)  # type: ignore[attr-defined]
        return {
            "result": result,
            "payload": payload,
            "capture_key": capture_key,
            "capture_directory": capture_directory,
            "forbidden_requests": forbidden_requests,
            "target_requests": target_requests,
            "progress_updates": progress_updates,
        }

    def test_real_worker_records_sanitized_manifest_and_blocks_other_loopback_port(self) -> None:
        run_id = f"test-browser-capture-{uuid.uuid4().hex}"
        captured = self._capture(run_id)
        result = captured["result"]
        manifest_path = captured["capture_directory"] / "manifest.json"
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        self.assertEqual(result["provider"], "local_playwright")
        self.assertEqual(result["cache_hit"], False)
        self.assertEqual(set(manifest["output_policy"]), {
            "policy_version",
            "width",
            "height",
            "frame_rate",
            "video_codec",
            "pixel_format",
            "audio",
        })
        for identity in manifest["tool_identity"].values():
            self.assertNotIn("path", identity)
        self.assertNotIn(str(REPO_ROOT).casefold(), manifest_text.casefold())
        self.assertNotIn("must-not-persist", manifest_text)
        self.assertEqual(captured["forbidden_requests"], [])
        self.assertGreaterEqual(len(captured["target_requests"]), 1)
        self.assertEqual(
            [phase for _progress, phase in captured["progress_updates"]],
            [
                "preflight",
                "preflight",
                "recording",
                "transcoding",
                "verification",
                "publishing",
                "registration",
            ],
        )
        self.assertEqual(
            [progress for progress, _phase in captured["progress_updates"]],
            sorted(progress for progress, _phase in captured["progress_updates"]),
        )

    def test_tampered_output_policy_is_rejected_even_with_recomputed_manifest_hash(self) -> None:
        run_id = f"test-browser-capture-tamper-{uuid.uuid4().hex}"
        captured = self._capture(run_id)
        manifest_path = captured["capture_directory"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["output_policy"]["video_codec"] = "vp9"
        body = dict(manifest)
        body.pop("manifest_sha256", None)
        manifest["manifest_sha256"] = browser_capture._manifest_digest(body)
        manifest_path.write_text(
            browser_capture.canonical_json(manifest) + "\n", encoding="utf-8"
        )

        with self.assertRaises(BrowserCaptureError) as raised:
            browser_capture.validate_local_screen_capture_outputs(
                REPO_ROOT,
                production_id="TEST_BROWSER_CAPTURE_INTEGRATION",
                run_id=run_id,
                capture_key=captured["capture_key"],
                payload=captured["payload"],
                node=self.node,
                ffmpeg=self.ffmpeg,
                ffprobe=self.ffprobe,
            )
        self.assertEqual(raised.exception.error_code, "cache_integrity_failed")

    def test_desktop_worker_records_matching_viewport_media_and_screenshots(self) -> None:
        run_id = f"test-browser-capture-desktop-{uuid.uuid4().hex}"
        captured = self._capture(run_id, viewport_preset="desktop_16_9")
        directory = captured["capture_directory"]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        report = json.loads((directory / "capture-report.json").read_text(encoding="utf-8"))
        expected = {"width": 1920, "height": 1080}
        self.assertEqual(captured["result"]["viewport_preset"], "desktop_16_9")
        self.assertEqual(captured["result"]["video_dimensions"], expected)
        self.assertEqual(manifest["capture"]["canvas"], expected)
        self.assertEqual(manifest["capture"]["viewport_preset"], "desktop_16_9")
        self.assertEqual(report["recording"]["viewport"], expected)
        self.assertEqual(report["recording"]["viewport_preset"], "desktop_16_9")
        self.assertEqual(manifest["output_policy"]["width"], 1920)
        self.assertEqual(manifest["output_policy"]["height"], 1080)
        self.assertEqual(manifest["output_policy"]["policy_version"], "h264-yuv420p-1920x1080-24fps-video-only-v1")
        self.assertEqual(manifest["network_policy"], "same-explicit-loopback-origin-only")
        self.assertEqual(captured["forbidden_requests"], [])
        for name in ("first-frame.png", "last-frame.png"):
            header = (directory / name).read_bytes()[:24]
            self.assertEqual(int.from_bytes(header[16:20], "big"), 1920)
            self.assertEqual(int.from_bytes(header[20:24], "big"), 1080)
            browser_capture._validate_png(directory / name, viewport_preset="desktop_16_9")
        for name in ("playwright_raw", "screen_capture"):
            video = manifest["media"][name]["streams"][0]
            self.assertEqual({"width": video["width"], "height": video["height"]}, expected)
        validated = browser_capture.validate_local_screen_capture_outputs(
            REPO_ROOT, production_id="TEST_BROWSER_CAPTURE_INTEGRATION", run_id=run_id,
            capture_key=captured["capture_key"], payload=captured["payload"],
            node=self.node, ffmpeg=self.ffmpeg, ffprobe=self.ffprobe,
        )
        self.assertEqual(validated["video_dimensions"], expected)
        with self.assertRaises(BrowserCaptureError):
            browser_capture._validate_mp4_probe(manifest["media"]["screen_capture"], expected_duration_ms=1200)
        with self.assertRaises(BrowserCaptureError):
            browser_capture._validate_raw_probe(manifest["media"]["playwright_raw"])

    def test_post_publish_validation_failure_removes_published_capture(self) -> None:
        run_id = f"test-browser-capture-cleanup-{uuid.uuid4().hex}"
        with self.assertRaises(BrowserCaptureError) as raised:
            captured = self._capture(run_id, validate_failure=None)
        self.assertEqual(raised.exception.error_code, "integrity_verification_failed")
        owned = self.owned_capture_directories[-1]
        self.assertFalse(owned.exists())

    def test_post_publish_cancel_removes_published_capture(self) -> None:
        run_id = f"test-browser-capture-cancel-{uuid.uuid4().hex}"
        with self.assertRaises(JobCancelled):
            self._capture(run_id, validate_failure=JobCancelled())
        owned = self.owned_capture_directories[-1]
        self.assertFalse(owned.exists())


if __name__ == "__main__":
    unittest.main()
