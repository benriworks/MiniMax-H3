from __future__ import annotations

import copy
import ctypes
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tools.studio import claude_capture as capture


SESSION = "A" * 64
OTHER_SESSION = "B" * 64
WINDOW = capture._Window(12345, 678, 999000, "c:\\private\\claude.exe", "Chrome_WidgetWin_1", 1400, 1000)


def probe(requested_ms: int = 15000) -> dict:
    frames = (requested_ms * 24 + 999) // 1000
    duration = f"{frames / 24:.6f}"
    return {"format": {"duration": duration}, "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "start_time": "0.000000", "duration": duration, "avg_frame_rate": "24/1", "nb_read_frames": str(frames)}]}


class FakeGuard:
    def __init__(self, system, window):
        self.system, self.window, self.checks = system, window, 0

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *_args):
        pass

    def check(self):
        self.checks += 1
        if self.system.snapshot(self.window.hwnd) != self.window:
            raise capture.ClaudeCaptureError("changed", code="claude_capture_target_changed")


class FakeSystem:
    def __init__(self):
        self.current = WINDOW

    def windows(self):
        return [self.current] if self.current else []

    def snapshot(self, _hwnd):
        return self.current

    def guard(self, window):
        return FakeGuard(self, window)


class ClaudeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.output = self.workspace / "outputs/studio/claude-captures/production_test/request_test"
        self.controller = capture.ClaudeCaptureController(self.workspace)
        self.system = FakeSystem()
        self.tools = {}
        for name in ("ffmpeg", "ffprobe"):
            path = self.workspace / (name + ".exe")
            path.write_bytes(b"fake local engine " + name.encode())
            self.tools[name] = str(path)
            self.tools[name + "_sha256"] = capture._sha(path)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.controller, "_system", return_value=self.system).start()
        mock.patch.object(self.controller, "_resolve_tools", return_value=self.tools).start()

    def request(self):
        selected = self.controller.inspect(session_binding=SESSION)["selections"][0]
        return {"selection_token": selected["selection_token"], "duration_ms": 15000, "confirm_capture": True}

    def claim(self):
        return self.controller.claim(self.request(), session_binding=SESSION)

    def fake_process(self, args, **kwargs):
        context = kwargs.get("cancel_event")
        if context is not None:
            capture.assembly._raise_if_cancelled(context)
        if "-filter_complex" in args:
            Path(args[-1]).write_bytes(b"test-mocked-video-not-real")
        elif "-count_frames" in args:
            return 0, json.dumps(probe()).encode(), b""
        elif args[-1].endswith(".png"):
            Path(args[-1]).write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1920, 1080))
        return 0, b"", b""

    def test_inspection_is_anonymous_and_does_not_run_capture(self):
        with mock.patch.object(capture.native, "_run_contained_process") as runner:
            result = self.controller.inspect(session_binding=SESSION)
        runner.assert_not_called()
        self.assertFalse(result["actual_capture_performed"])
        self.assertEqual(set(result["selections"][0]), {"selection_token", "label", "width", "height", "available", "expires_in_seconds"})
        encoded = json.dumps(result)
        for forbidden in ("12345", "999000", "private", "Chrome_WidgetWin", "process_path", "title"):
            self.assertNotIn(forbidden, encoded)

    def test_driver_cwd_cache_is_outside_successful_media_bundle(self):
        def driver_process(args, **kwargs):
            cwd = Path(kwargs["cwd"])
            self.assertEqual(cwd, self.workspace / "outputs/studio/runtime/claude-window-capture")
            (cwd / "NVIDIA Corporation/umdlogs").mkdir(parents=True, exist_ok=True)
            if args[-1].endswith((".mp4", ".png")):
                self.assertTrue(Path(args[-1]).is_absolute())
                self.assertNotIn(cwd, Path(args[-1]).parents)
            return self.fake_process(args, **kwargs)
        with mock.patch.object(capture.native, "_run_contained_process", side_effect=driver_process):
            result = self.controller.capture(self.claim(), capture_root=self.output)
        self.assertEqual(len(list(self.output.iterdir())), 6)
        self.assertEqual(result["runtime_directory_policy"], "isolated_local_driver_cache_v1")
        capture.cleanup_capture_root(self.output, workspace=self.workspace)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.workspace / "outputs/studio/runtime/claude-window-capture/NVIDIA Corporation/umdlogs").is_dir())

    def test_driver_cache_does_not_block_failed_capture_cleanup(self):
        def driver_failure(args, **kwargs):
            (Path(kwargs["cwd"]) / "NVIDIA Corporation/umdlogs").mkdir(parents=True, exist_ok=True)
            Path(args[-1]).write_bytes(b"private partial")
            return 1, b"", b""
        with mock.patch.object(capture.native, "_run_contained_process", side_effect=driver_failure), self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(self.claim(), capture_root=self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_inspection_without_claude_does_not_claim_readiness(self):
        self.system.current = None
        result = self.controller.inspect(session_binding=SESSION)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "claude_window_not_available")

    def test_official_package_binding_rejects_renamed_executable_or_other_app(self):
        good = {
            "process_path": r"C:\Program Files\WindowsApps\Claude_1.46388.4.0_x64__pzs8sxrjxfjjc\app\Claude.exe",
            "family": "Claude_pzs8sxrjxfjjc",
            "full_name": "Claude_1.46388.4.0_x64__pzs8sxrjxfjjc",
            "application_id": "Claude_pzs8sxrjxfjjc!Claude",
            "package_root": r"C:\Program Files\WindowsApps\Claude_1.46388.4.0_x64__pzs8sxrjxfjjc",
        }
        self.assertTrue(capture._official_package_binding(**good))
        for field, bad in (("family", "Claude_fakepublisher"), ("full_name", "Claude_1.0_x64__pzs8sxrjxfjjc"),
                           ("application_id", "Claude_pzs8sxrjxfjjc!Another"), ("package_root", ""),
                           ("process_path", r"C:\Users\someone\claude.exe"), ("process_path", r"C:\Program Files\WindowsApps\Claude_1.46388.4.0_x64__pzs8sxrjxfjjc\..\Claude.exe")):
            with self.subTest(field=field, value=bad):
                self.assertFalse(capture._official_package_binding(**{**good, field: bad}))

    def test_capability_failure_is_safe(self):
        with mock.patch.object(self.controller, "_resolve_tools", side_effect=RuntimeError("private path")):
            result = self.controller.inspect(session_binding=SESSION)
        self.assertFalse(result["available"])
        self.assertNotIn("private", json.dumps(result))

    def test_request_is_closed_and_requires_explicit_confirmation(self):
        body = self.request()
        for key in ("hwnd", "path", "window_title", "command", "audio_mode", "request_id"):
            with self.subTest(key=key), self.assertRaises(capture.ClaudeCaptureError):
                capture.validate_capture_request({**body, key: "untrusted"})
        for bad in (False, 1, "true", None):
            with self.subTest(confirm=bad), self.assertRaises(capture.ClaudeCaptureError):
                capture.validate_capture_request({**body, "confirm_capture": bad})
        for bad in (True, 14999, 30001, 15000.0, "15000", None):
            with self.subTest(duration=bad), self.assertRaises(capture.ClaudeCaptureError):
                capture.validate_capture_request({**body, "duration_ms": bad})
        self.assertEqual(capture.validate_capture_request({**body, "duration_ms": 30000})["duration_ms"], 30000)

    def test_claim_is_session_bound_and_single_use(self):
        body = self.request()
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim(body, session_binding=OTHER_SESSION)
        claim = self.controller.claim(body, session_binding=SESSION)
        self.assertEqual(claim.selection_digest, capture.selection_token_digest(body["selection_token"]))
        self.assertNotIn("private", repr(claim))
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim(body, session_binding=SESSION)

    def test_selection_expires_and_refresh_retires_previous_selection(self):
        with mock.patch.object(capture.time, "monotonic", return_value=100):
            body = self.request()
        with mock.patch.object(capture.time, "monotonic", return_value=160), self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim(body, session_binding=SESSION)
        body = self.request()
        self.controller.inspect(session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim(body, session_binding=SESSION)

    def test_invalid_session_and_token_are_rejected(self):
        for bad in ("", "session", None, [], "Z" * 64):
            with self.subTest(session=bad), self.assertRaises(capture.ClaudeCaptureError):
                self.controller.inspect(session_binding=bad)
        for bad in ("", "x", None, [], "x" * 44):
            with self.subTest(token=bad), self.assertRaises(capture.ClaudeCaptureError):
                capture.selection_token_digest(bad)

    def test_command_has_exact_window_no_audio_no_external_protocols(self):
        command = capture._command("ffmpeg", WINDOW, 15000, self.output / "claude-capture.mp4")
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("gfxcapture=hwnd=12345:", graph)
        self.assertIn("capture_cursor=0:display_border=1", graph)
        self.assertIn("hwdownload,format=bgra", graph)
        self.assertIn("-an", command)
        self.assertIn("file,pipe", command)
        for forbidden in ("desktop", "window_exe", "window_title", "hmonitor", "default_render", "capture-loopback", "http:"):
            self.assertNotIn(forbidden, " ".join(command))
        with self.assertRaises(capture.ClaudeCaptureError):
            capture._command("ffmpeg", replace(WINDOW, hwnd=0), 15000, self.output)

    def test_probe_rejects_audio_truncation_wrong_codec_and_nonfinite(self):
        self.assertEqual(capture._validate_probe(probe(), 15000)["frame_count"], 360)
        bad_values = []
        value = probe(); value["streams"].append({"codec_type": "audio"}); bad_values.append(value)
        for key, bad in (("codec_name", "vp9"), ("nb_read_frames", "350"), ("width", 1080), ("duration", "14.0"), ("avg_frame_rate", "0/0"), ("start_time", "nan")):
            value = probe(); value["streams"][0][key] = bad; bad_values.append(value)
        value = probe(); value["format"]["duration"] = "nan"; bad_values.append(value)
        for bad in bad_values:
            with self.subTest(probe=bad), self.assertRaises(capture.ClaudeCaptureError):
                capture._validate_probe(bad, 15000)

    def test_arbitrary_millisecond_duration_rounds_up_to_complete_frame(self):
        for requested in (15000, 15001, 15100, 15124, 15125, 15126, 29999, 30000):
            with self.subTest(duration=requested):
                command = capture._command("ffmpeg", WINDOW, requested, self.output)
                frames = (requested * 24 + 999) // 1000
                self.assertEqual(command[command.index("-frames:v") + 1], str(frames))
                self.assertNotIn("-t", command)
                measured = capture._validate_probe(probe(requested), requested)
                self.assertGreaterEqual(measured["duration_ms"], requested)
                self.assertLess(measured["duration_ms"] - requested, 1000 / 24)
                self.assertEqual(measured["frame_count"], frames)
        with self.assertRaises(capture.ClaudeCaptureError):
            capture._validate_probe(probe(15000), 15001)

    def test_claim_cannot_be_forged_or_executed_twice(self):
        claim = self.claim()
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(copy.copy(claim), capture_root=self.output)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(claim, capture_root=self.output)

    def test_expired_claim_never_starts_capture(self):
        with mock.patch.object(capture.time, "monotonic", return_value=100):
            claim = self.claim()
        with mock.patch.object(capture.time, "monotonic", return_value=161), mock.patch.object(capture.native, "_run_contained_process") as runner, self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(claim, capture_root=self.output)
        runner.assert_not_called()

    def test_cancel_before_capture_never_creates_media(self):
        event = mock.Mock()
        event.raise_if_cancelled.side_effect = RuntimeError("cancelled")
        with mock.patch.object(capture.native, "_run_contained_process") as runner, self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.controller.capture(self.claim(), capture_root=self.output, cancel_event=event)
        runner.assert_not_called()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(ctypes, "WINFUNCTYPE"), "Win32 callback ABI is Windows only")
    def test_native_guard_latches_transient_events_and_releases_hooks(self):
        for event_code in (0x16, 0x8001, 0x8003, 0x800B):
            user = mock.Mock()
            user.SetWinEventHook.side_effect = [11, 22]
            user.PeekMessageW.return_value = False
            system = mock.Mock(user=user)
            system.snapshot.return_value = WINDOW
            with self.subTest(event=event_code):
                guard = capture._WindowGuard(system, WINDOW)
                with guard:
                    guard.callback(11, event_code, WINDOW.hwnd, 0, 0, 0, 0)
                    # The current snapshot is unchanged: the event alone must
                    # reject a minimize/restore or resize/back race.
                    with self.assertRaises(capture.ClaudeCaptureError):
                        guard.check()
                self.assertEqual(user.UnhookWinEvent.call_args_list, [mock.call(11), mock.call(22)])

    @unittest.skipUnless(hasattr(ctypes, "WINFUNCTYPE"), "Win32 callback ABI is Windows only")
    def test_native_guard_hook_failure_is_closed(self):
        user = mock.Mock()
        user.SetWinEventHook.side_effect = [11, 0]
        with self.assertRaises(capture.ClaudeCaptureError):
            with capture._WindowGuard(mock.Mock(user=user), WINDOW):
                self.fail("guard should not become ready")
        user.UnhookWinEvent.assert_called_once_with(11)

    def test_changed_tool_fails_before_recording(self):
        claim = self.claim()
        Path(self.tools["ffmpeg"]).write_bytes(b"changed")
        with mock.patch.object(capture.native, "_run_contained_process") as runner, self.assertRaises(capture.ClaudeCaptureError) as raised:
            self.controller.capture(claim, capture_root=self.output)
        self.assertEqual(raised.exception.error_code, "claude_capture_tool_changed")
        runner.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_target_before_start_never_records(self):
        for changed in (None, replace(WINDOW, pid=111), replace(WINDOW, process_started=222), replace(WINDOW, width=1600), replace(WINDOW, process_path="c:\\another\\claude.exe")):
            self.system.current = WINDOW
            claim = self.claim()
            self.system.current = changed
            with self.subTest(target=changed), mock.patch.object(capture.native, "_run_contained_process") as runner, self.assertRaises(capture.ClaudeCaptureError):
                self.controller.capture(claim, capture_root=self.output)
            runner.assert_not_called()
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_target_changed_during_capture_does_not_publish(self):
        claim = self.claim()
        def record_then_change(args, **kwargs):
            self.fake_process(args, **kwargs)
            self.system.current = None
            kwargs["cancel_event"].raise_if_cancelled()
        with mock.patch.object(capture.native, "_run_contained_process", side_effect=record_then_change), self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(claim, capture_root=self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_mocked_success_outputs_silent_provenance_and_six_artifacts(self):
        claim = self.claim()
        with mock.patch.object(capture.native, "_run_contained_process", side_effect=self.fake_process):
            result = self.controller.capture(claim, capture_root=self.output)
        self.assertEqual(len(result["artifacts"]), 6)
        self.assertEqual(result["audio_mode"], "none")
        self.assertFalse(result["audio_capture_performed"])
        self.assertFalse(result["content_quality_verified"])
        self.assertFalse(result["public_release_ready"])
        self.assertTrue(result["structural_video_verified"])
        report = json.loads((self.output / "capture-report.json").read_text())
        for forbidden in (WINDOW.process_path, "hwnd", "window_class", "process_started", "selection_token"):
            self.assertNotIn(forbidden, json.dumps(report))
        for artifact in result["artifacts"]:
            self.assertEqual(artifact["sha256"], capture._sha(Path(artifact["path"])))
        capture.cleanup_capture_root(self.output, workspace=self.workspace)
        self.assertFalse(self.output.exists())

    def test_probe_failure_and_decode_failure_remove_all_outputs(self):
        for fail_arg in ("-count_frames", "-xerror"):
            claim = self.claim()
            def runner(args, **kwargs):
                return (1, b"private info", b"private info") if fail_arg in args else self.fake_process(args, **kwargs)
            with self.subTest(stage=fail_arg), mock.patch.object(capture.native, "_run_contained_process", side_effect=runner), self.assertRaises(capture.ClaudeCaptureError):
                self.controller.capture(claim, capture_root=self.output)
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_capture_refuses_existing_or_broad_output_path(self):
        for path in (self.workspace, self.workspace / "outputs", self.output.parent, self.output / "nested"):
            claim = self.claim()
            with self.subTest(path=path), mock.patch.object(capture.native, "_run_contained_process") as runner, self.assertRaises((capture.ClaudeCaptureError, ValueError)):
                self.controller.capture(claim, capture_root=path)
            runner.assert_not_called()
        self.output.mkdir(parents=True)
        (self.output / "user.txt").write_text("preserve")
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(self.claim(), capture_root=self.output)
        self.assertEqual((self.output / "user.txt").read_text(), "preserve")

    def test_cleanup_is_exact_and_unknown_files_block_all_deletion(self):
        partial = self.output.with_name(".request_test." + "a" * 32 + ".partial")
        unrelated = self.output.with_name(".request_other." + "a" * 32 + ".partial")
        for directory in (self.output, partial, unrelated):
            directory.mkdir(parents=True)
            (directory / "claude-capture.mp4").write_bytes(b"owned")
        (partial / "user.txt").write_text("preserve")
        with self.assertRaises(capture.ClaudeCaptureError):
            capture.cleanup_capture_root(self.output, workspace=self.workspace)
        self.assertTrue((self.output / "claude-capture.mp4").exists())
        (partial / "user.txt").unlink()
        capture.cleanup_capture_root(self.output, workspace=self.workspace)
        self.assertFalse(self.output.exists())
        self.assertFalse(partial.exists())
        self.assertTrue(unrelated.exists())

    def test_cleanup_refuses_directories_links_and_broad_roots(self):
        self.output.mkdir(parents=True)
        (self.output / "claude-capture.mp4").mkdir()
        with self.assertRaises(capture.ClaudeCaptureError):
            capture.cleanup_capture_root(self.output, workspace=self.workspace)
        with self.assertRaises(capture.ClaudeCaptureError):
            capture.cleanup_capture_root(self.output.parent, workspace=self.workspace)
        with mock.patch.object(capture.native, "_has_symlink_component", return_value=True), self.assertRaises(capture.ClaudeCaptureError):
            capture.cleanup_capture_root(self.output, workspace=self.workspace)

    def test_capability_only_uses_version_and_filter_help(self):
        controller = capture.ClaudeCaptureController(self.workspace)
        calls = []
        def runner(args, **_kwargs):
            calls.append(args)
            return (0, b"gfxcapture hwnd capture_cursor max_framerate", b"") if "-h" in args else (0, b"version", b"")
        with mock.patch.object(capture.os, "name", "nt"), mock.patch.object(capture.assembly, "_find_tool", side_effect=lambda name: self.tools[name]), mock.patch.object(capture.native, "_run_contained_process", side_effect=runner):
            tools = controller._resolve_tools()
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("-version" in call or "-h" in call for call in calls))
        self.assertNotIn("-filter_complex", str(calls))
        self.assertEqual(tools["ffmpeg_sha256"], self.tools["ffmpeg_sha256"])


if __name__ == "__main__":
    unittest.main()
