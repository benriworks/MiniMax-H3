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
    validate_windows_capture_execution_payload,
    validate_windows_capture_payload,
    windows_capture_audit_payload,
    windows_capture_consent_token_digest,
    windows_capture_session_binding_digest,
    windows_capture_settings_digest,
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

    def test_execution_token_is_separate_and_digests_bind_settings_and_session(self) -> None:
        body = {
            "schema_version": 1,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cursor_mode": "hidden",
            "duration_ms": 5_000,
            "confirm_capture": True,
            "confirm_system_audio": True,
        }
        token = "A" * 43
        payload, returned_token = validate_windows_capture_execution_payload(
            {**body, "consent_token": token}
        )
        self.assertEqual(payload, body)
        self.assertEqual(returned_token, token)
        self.assertRegex(windows_capture_settings_digest(payload), r"^[0-9A-F]{64}$")
        self.assertRegex(windows_capture_consent_token_digest(token), r"^[0-9A-F]{64}$")
        self.assertRegex(
            windows_capture_session_binding_digest("S" * 32),
            r"^[0-9A-F]{64}$",
        )
        with self.assertRaises(WindowsCaptureValidationError):
            validate_windows_capture_execution_payload(body)
        with self.assertRaises(WindowsCaptureValidationError):
            validate_windows_capture_execution_payload(
                {**body, "consent_token": "too-short"}
            )


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
            ffprobe = root / "ffprobe.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            ffprobe.write_bytes(b"ffprobe")
            doctor = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "captureAvailable": True,
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
                "display": {
                    "target": "primary_display",
                    "width": 2560,
                    "height": 1440,
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
                    ffprobe=ffprobe,
                )
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["foundation_ready"])
        self.assertTrue(result["screen_capture_ready"])
        self.assertTrue(result["system_audio_loopback_ready"])
        self.assertTrue(result["capture_execution_enabled"])
        self.assertFalse(result["actual_capture_performed"])
        self.assertTrue(result["helper"]["capture_command_available"])
        self.assertTrue(result["ffmpeg"]["ffprobe_available"])
        self.assertEqual(
            result["display"],
            {"target": "primary_display", "width": 2560, "height": 1440},
        )
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
            ffprobe = root / "ffprobe.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            ffprobe.write_bytes(b"ffprobe")
            unsafe = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "captureAvailable": True,
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
                "display": {
                    "target": "primary_display",
                    "width": 2560,
                    "height": 1440,
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
                    ffprobe=ffprobe,
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
            ffprobe = root / "ffprobe.exe"
            dotnet.write_bytes(b"dotnet")
            ffmpeg.write_bytes(b"ffmpeg")
            ffprobe.write_bytes(b"ffprobe")
            doctor = {
                "schemaVersion": 1,
                "operation": "doctor",
                "ok": True,
                "captureAvailable": True,
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
                "display": {
                    "target": "primary_display",
                    "width": 2560,
                    "height": 1440,
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
                    ffprobe=ffprobe,
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
