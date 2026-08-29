from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

from tools.studio.windows_capture import (
    WINDOWS_CAPTURE_HELPER_RELATIVE_PATH,
    WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS,
    WindowsCaptureValidationError,
    inspect_windows_capture_capability,
    validate_windows_capture_payload,
    windows_capture_audit_payload,
)


def _write_helper_fixture(root: Path) -> Path:
    for relative in WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS:
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(relative.encode("utf-8"))
    helper = root / WINDOWS_CAPTURE_HELPER_RELATIVE_PATH
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_bytes(b"helper")
    return helper


class WindowsCaptureContractTests(unittest.TestCase):
    def test_capture_request_is_fixed_and_requires_both_confirmations(self) -> None:
        body = {
            "schema_version": 1,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cursor_mode": "hidden",
            "duration_ms": 5_000,
            "confirm_capture": True,
            "confirm_system_audio": True,
        }
        self.assertEqual(validate_windows_capture_payload(body), body)
        audit = windows_capture_audit_payload(body)
        self.assertTrue(audit["explicit_capture_confirmation"])
        self.assertTrue(audit["explicit_system_audio_confirmation"])
        self.assertNotIn("path", json.dumps(audit).casefold())

    def test_capture_request_rejects_paths_devices_microphone_and_false_consent(self) -> None:
        base = {
            "schema_version": 1,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cursor_mode": "hidden",
            "duration_ms": 5_000,
            "confirm_capture": True,
            "confirm_system_audio": True,
        }
        for extra in (
            {"output_path": "C:/private.mp4"},
            {"device_id": "secret-device"},
            {"window_title": "password manager"},
            {"ffmpeg_args": ["-f", "dshow"]},
            {"microphone": True},
        ):
            with self.assertRaises(WindowsCaptureValidationError):
                validate_windows_capture_payload({**base, **extra})
        for key in ("confirm_capture", "confirm_system_audio"):
            with self.assertRaises(WindowsCaptureValidationError):
                validate_windows_capture_payload({**base, key: False})
        for duration in (999, 30_001, True):
            with self.assertRaises(WindowsCaptureValidationError):
                validate_windows_capture_payload({**base, "duration_ms": duration})


class WindowsCaptureCapabilityTests(unittest.TestCase):
    def test_non_windows_is_closed_without_running_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_windows_capture_capability(
                Path(directory), platform_name="linux"
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"], ["unsupported_platform"])
        self.assertFalse(result["actual_capture_performed"])
        self.assertFalse(result["capture_execution_enabled"])

    def test_doctor_and_gdigrab_create_foundation_ready_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = _write_helper_fixture(root)
            dotnet = root / "dotnet.exe"
            ffmpeg = root / "ffmpeg.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            doctor = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "platform": {
                    "windows": True,
                    "targetFramework": "net8.0-windows",
                    "architecture": "X64",
                },
                "endpoint": {
                    "flow": "render",
                    "role": "console",
                    "state": "active",
                    "loopback": {
                        "supported": True,
                        "initialized": True,
                        "recordingStarted": False,
                    },
                    "recordingStarted": False,
                },
            }
            with mock.patch(
                "tools.studio.windows_capture._run_bounded",
                side_effect=[
                    (0, json.dumps(doctor).encode("utf-8"), b""),
                    (0, b" D  gdigrab         GDI API Windows frame grabber\n", b""),
                ],
            ) as runner:
                result = inspect_windows_capture_capability(
                    root,
                    platform_name="win32",
                    dotnet=dotnet,
                    ffmpeg=ffmpeg,
                )
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result["status"], "foundation_ready")
        self.assertTrue(result["foundation_ready"])
        self.assertTrue(result["screen_capture_ready"])
        self.assertTrue(result["system_audio_loopback_ready"])
        self.assertFalse(result["capture_execution_enabled"])
        self.assertFalse(result["actual_capture_performed"])
        self.assertEqual(result["reasons"], [])
        self.assertRegex(result["helper"]["sha256"], r"^[0-9A-F]{64}$")
        self.assertRegex(result["tool_identity_digest"], r"^[0-9A-F]{64}$")
        self.assertNotIn(str(root), json.dumps(result))

    def test_recording_started_from_helper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = _write_helper_fixture(root)
            dotnet = root / "dotnet.exe"
            ffmpeg = root / "ffmpeg.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            unsafe = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "platform": {
                    "windows": True,
                    "targetFramework": "net8.0-windows",
                    "architecture": "X64",
                },
                "endpoint": {
                    "flow": "render",
                    "role": "console",
                    "state": "active",
                    "loopback": {
                        "supported": True,
                        "initialized": True,
                        "recordingStarted": True,
                    },
                    "recordingStarted": True,
                },
            }
            with mock.patch(
                "tools.studio.windows_capture._run_bounded",
                side_effect=[
                    (0, json.dumps(unsafe).encode("utf-8"), b""),
                    (0, b" D  gdigrab\n", b""),
                ],
            ):
                result = inspect_windows_capture_capability(
                    root,
                    platform_name="win32",
                    dotnet=dotnet,
                    ffmpeg=ffmpeg,
                )
        self.assertIn("helper_contract_invalid", result["reasons"])
        self.assertFalse(result["foundation_ready"])
        self.assertFalse(result["actual_capture_performed"])

    def test_nonzero_ffmpeg_probe_cannot_advertise_gdigrab(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = _write_helper_fixture(root)
            dotnet = root / "dotnet.exe"
            ffmpeg = root / "ffmpeg.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            doctor = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "platform": {
                    "windows": True,
                    "targetFramework": "net8.0-windows",
                    "architecture": "X64",
                },
                "endpoint": {
                    "flow": "render",
                    "role": "console",
                    "state": "active",
                    "loopback": {
                        "supported": True,
                        "initialized": True,
                        "recordingStarted": False,
                    },
                    "recordingStarted": False,
                },
            }
            with mock.patch(
                "tools.studio.windows_capture._run_bounded",
                side_effect=[
                    (0, json.dumps(doctor).encode("utf-8"), b""),
                    (1, b" D  gdigrab\n", b""),
                ],
            ):
                result = inspect_windows_capture_capability(
                    root,
                    platform_name="win32",
                    dotnet=dotnet,
                    ffmpeg=ffmpeg,
                )
        self.assertFalse(result["screen_capture_ready"])
        self.assertFalse(result["foundation_ready"])
        self.assertIn("gdigrab_unavailable", result["reasons"])

    def test_probe_output_is_streamed_into_a_hard_total_cap(self) -> None:
        from tools.studio.windows_capture import _run_bounded

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                _run_bounded(
                    [
                        sys.executable,
                        "-c",
                        "import sys; sys.stdout.buffer.write(b'x' * 70000)",
                    ],
                    cwd=Path(directory),
                )


if __name__ == "__main__":
    unittest.main()
