from __future__ import annotations

"""Closed capability contract for future Windows desktop capture.

The public inspector never records a screen or audio sample. It only executes
the repository-owned native doctor and checks whether the pinned local FFmpeg
build exposes ``gdigrab``. The capture request validator is intentionally kept
separate from execution so an API cannot accidentally turn a diagnostic call
into a recording operation.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .security import canonical_json, workspace_path


WINDOWS_CAPTURE_SCHEMA_VERSION = 1
WINDOWS_CAPTURE_IMPLEMENTATION_VERSION = "windows-capture-capability-v1"
WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION = (
    "windows-native-primary-display-loopback-v1"
)
WINDOWS_CAPTURE_HELPER_RELATIVE_PATH = (
    "native/windows-capture-helper/bin/Release/net8.0-windows/"
    "windows-capture-helper.dll"
)
WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS = (
    "native/windows-capture-helper/Program.cs",
    "native/windows-capture-helper/windows-capture-helper.csproj",
)
MIN_DURATION_MS = 1_000
MAX_DURATION_MS = 30_000

_REQUEST_KEYS = {
    "schema_version",
    "target",
    "audio_mode",
    "cursor_mode",
    "duration_ms",
    "confirm_capture",
    "confirm_system_audio",
}
_EXPECTED_TARGET = "primary_display"
_EXPECTED_AUDIO_MODE = "default_render_loopback"
_EXPECTED_CURSOR_MODE = "hidden"
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_GDI_DEVICE_RE = re.compile(r"(?m)^\s*D\s+gdigrab(?:\s|$)")
_MAX_PROCESS_OUTPUT_BYTES = 64 * 1024
_PROCESS_TIMEOUT_SECONDS = 10


class WindowsCaptureValidationError(ValueError):
    """A future capture request escaped the fixed v1 contract."""


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WindowsCaptureValidationError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise WindowsCaptureValidationError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return value


def validate_windows_capture_payload(body: Any) -> dict[str, Any]:
    """Validate the not-yet-executable native capture request.

    The schema deliberately has no path, HWND, title, device identifier,
    microphone option, executable, or arbitrary FFmpeg argument.
    """

    if not isinstance(body, dict) or set(body) != _REQUEST_KEYS:
        raise WindowsCaptureValidationError(
            "request body must contain only the fixed Windows capture fields"
        )
    if body.get("schema_version") != WINDOWS_CAPTURE_SCHEMA_VERSION:
        raise WindowsCaptureValidationError("schema_version is not supported")
    if body.get("target") != _EXPECTED_TARGET:
        raise WindowsCaptureValidationError("target must be primary_display")
    if body.get("audio_mode") != _EXPECTED_AUDIO_MODE:
        raise WindowsCaptureValidationError(
            "audio_mode must be default_render_loopback"
        )
    if body.get("cursor_mode") != _EXPECTED_CURSOR_MODE:
        raise WindowsCaptureValidationError("cursor_mode must be hidden")
    if body.get("confirm_capture") is not True:
        raise WindowsCaptureValidationError("confirm_capture must be true")
    if body.get("confirm_system_audio") is not True:
        raise WindowsCaptureValidationError("confirm_system_audio must be true")
    duration_ms = _integer(
        body.get("duration_ms"),
        label="duration_ms",
        minimum=MIN_DURATION_MS,
        maximum=MAX_DURATION_MS,
    )
    return {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "target": _EXPECTED_TARGET,
        "audio_mode": _EXPECTED_AUDIO_MODE,
        "cursor_mode": _EXPECTED_CURSOR_MODE,
        "duration_ms": duration_ms,
        "confirm_capture": True,
        "confirm_system_audio": True,
    }


def windows_capture_audit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_windows_capture_payload(dict(payload))
    return {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "target": normalized["target"],
        "audio_mode": normalized["audio_mode"],
        "cursor_mode": normalized["cursor_mode"],
        "duration_ms": normalized["duration_ms"],
        "explicit_capture_confirmation": True,
        "explicit_system_audio_confirmation": True,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _clean_environment() -> dict[str, str]:
    """Retain basic Windows process plumbing while removing host injection."""

    allowed = {
        "comspec",
        "localappdata",
        "path",
        "pathext",
        "programdata",
        "programfiles",
        "programfiles(x86)",
        "systemdrive",
        "systemroot",
        "temp",
        "tmp",
        "windir",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key.casefold() in allowed
    }


def _resolve_executable(name: str, supplied: str | Path | None) -> Path | None:
    candidate = str(supplied) if supplied is not None else shutil.which(name)
    if not candidate:
        return None
    try:
        resolved = Path(candidate).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if resolved.is_file() and not resolved.is_symlink() else None


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        from .jobs import _terminate_process_tree

        _terminate_process_tree(process.pid, deadline=time.monotonic() + 2.0)
    except Exception:
        try:
            process.kill()
        except OSError:
            pass


def _run_bounded(command: list[str], *, cwd: Path) -> tuple[int, bytes, bytes]:
    """Run a fixed probe while retaining at most 64 KiB across both pipes."""

    process_options: dict[str, Any] = {}
    if os.name == "nt":
        process_options["creationflags"] = int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        ) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        process_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=_clean_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        **process_options,
    )
    if process.stdout is None or process.stderr is None:
        _terminate_process(process)
        raise ValueError("process did not expose bounded output pipes")

    stdout = bytearray()
    stderr = bytearray()
    retained = 0
    lock = threading.Lock()
    excessive = threading.Event()
    reader_error = threading.Event()

    def drain(stream: Any, destination: bytearray) -> None:
        nonlocal retained
        try:
            while chunk := stream.read(8 * 1024):
                with lock:
                    remaining = _MAX_PROCESS_OUTPUT_BYTES + 1 - retained
                    if remaining > 0:
                        piece = chunk[:remaining]
                        destination.extend(piece)
                        retained += len(piece)
                    if len(chunk) > remaining or retained > _MAX_PROCESS_OUTPUT_BYTES:
                        excessive.set()
        except (OSError, ValueError):
            return
        except BaseException:
            reader_error.set()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, stdout), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + _PROCESS_TIMEOUT_SECONDS
    try:
        while process.poll() is None:
            if excessive.is_set() or reader_error.is_set():
                _terminate_process(process)
                raise ValueError("process output exceeded the capability limit")
            if time.monotonic() >= deadline:
                _terminate_process(process)
                raise subprocess.TimeoutExpired(command, _PROCESS_TIMEOUT_SECONDS)
            time.sleep(0.05)
        for reader in readers:
            reader.join(timeout=max(0.0, min(2.0, deadline - time.monotonic())))
        if any(reader.is_alive() for reader in readers) or reader_error.is_set():
            _terminate_process(process)
            raise ValueError("process output reader did not retire")
        if excessive.is_set() or retained > _MAX_PROCESS_OUTPUT_BYTES:
            raise ValueError("process output exceeded the capability limit")
        return int(process.returncode), bytes(stdout), bytes(stderr)
    finally:
        _terminate_process(process)
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        for reader in readers:
            reader.join(timeout=0.25)


def _doctor_contract(value: Any) -> tuple[bool, bool, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("native doctor output is not an object")
    if (
        value.get("schemaVersion") != 1
        or value.get("operation") != "doctor"
        or not isinstance(value.get("ok"), bool)
    ):
        raise ValueError("native doctor envelope is invalid")
    platform = value.get("platform")
    if not isinstance(platform, dict) or set(platform) != {
        "windows",
        "targetFramework",
        "architecture",
    }:
        raise ValueError("native doctor platform contract is invalid")
    if (
        platform.get("windows") is not True
        or platform.get("targetFramework") != "net8.0-windows"
        or not isinstance(platform.get("architecture"), str)
        or not platform.get("architecture")
    ):
        raise ValueError("native doctor platform result is invalid")

    endpoint = value.get("endpoint")
    if not isinstance(endpoint, dict):
        if value.get("ok") is True:
            raise ValueError("native doctor omitted a successful endpoint")
        return False, False, {
            "doctor_ok": False,
            "endpoint_active": False,
            "loopback_initialized": False,
            "recording_started": False,
        }
    loopback = endpoint.get("loopback")
    if not isinstance(loopback, dict):
        if value.get("ok") is True:
            raise ValueError("native doctor omitted successful loopback state")
        loopback = {}
    recording_started = endpoint.get("recordingStarted") is True or loopback.get(
        "recordingStarted"
    ) is True
    if recording_started:
        raise ValueError("native doctor unexpectedly reported active recording")
    if endpoint.get("flow") != "render" or endpoint.get("role") != "console":
        raise ValueError("native doctor endpoint role is invalid")
    endpoint_active = endpoint.get("state") == "active"
    loopback_ready = (
        loopback.get("supported") is True
        and loopback.get("initialized") is True
        and not recording_started
    )
    doctor_ok = value.get("ok") is True
    if doctor_ok != (endpoint_active and loopback_ready):
        raise ValueError("native doctor result is internally inconsistent")
    return doctor_ok, loopback_ready, {
        "doctor_ok": doctor_ok,
        "endpoint_active": endpoint_active,
        "loopback_initialized": loopback_ready,
        "recording_started": False,
    }


def _base_result() -> dict[str, Any]:
    return {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_IMPLEMENTATION_VERSION,
        "status": "blocked",
        "foundation_ready": False,
        "capture_execution_enabled": False,
        "screen_capture_ready": False,
        "system_audio_loopback_ready": False,
        "explicit_confirmation_required": True,
        "actual_capture_performed": False,
        "reasons": [],
        "helper": {
            "available": False,
            "doctor_ok": False,
            "endpoint_active": False,
            "loopback_initialized": False,
            "recording_started": False,
        },
        "ffmpeg": {"available": False, "gdigrab_available": False},
        "tool_identity_digest": None,
    }


def inspect_windows_capture_capability(
    workspace: Path,
    *,
    platform_name: str | None = None,
    dotnet: str | Path | None = None,
    ffmpeg: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect fixed local tooling without starting capture or persisting data."""

    root = workspace.resolve(strict=True)
    result = _base_result()
    reasons: list[str] = result["reasons"]
    if (platform_name or sys.platform) != "win32":
        reasons.append("unsupported_platform")
        return result

    try:
        helper_paths = (
            WINDOWS_CAPTURE_HELPER_RELATIVE_PATH,
            *WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS,
        )
        if any(_has_symlink_component(root, relative) for relative in helper_paths):
            raise OSError
        helper = workspace_path(
            root, WINDOWS_CAPTURE_HELPER_RELATIVE_PATH, must_exist=True
        )
        helper_sources = [
            workspace_path(root, relative, must_exist=True)
            for relative in WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS
        ]
        if (
            not helper.is_file()
            or helper.is_symlink()
            or any(not source.is_file() or source.is_symlink() for source in helper_sources)
            or helper.stat().st_mtime_ns
            < max(source.stat().st_mtime_ns for source in helper_sources)
        ):
            raise OSError
    except (OSError, RuntimeError, ValueError):
        reasons.append("native_helper_not_built")
        helper = None

    dotnet_path = _resolve_executable("dotnet", dotnet)
    if dotnet_path is None:
        reasons.append("dotnet_unavailable")
    ffmpeg_path = _resolve_executable("ffmpeg", ffmpeg)
    if ffmpeg_path is None:
        reasons.append("ffmpeg_unavailable")

    identities: dict[str, dict[str, str]] = {}
    if helper is not None:
        try:
            helper_hash = _sha256_file(helper)
            source_hashes = {
                Path(relative).name: _sha256_file(source)
                for relative, source in zip(
                    WINDOWS_CAPTURE_HELPER_SOURCE_RELATIVE_PATHS,
                    helper_sources,
                    strict=True,
                )
            }
        except OSError:
            reasons.append("helper_contract_invalid")
            helper = None
        else:
            result["helper"]["available"] = True
            result["helper"]["sha256"] = helper_hash
            identities["helper"] = {"sha256": helper_hash}
            identities["helper_source"] = source_hashes

    if dotnet_path is not None:
        try:
            identities["dotnet"] = {"sha256": _sha256_file(dotnet_path)}
        except OSError:
            reasons.append("dotnet_unavailable")
            dotnet_path = None

    if ffmpeg_path is not None:
        try:
            identities["ffmpeg"] = {"sha256": _sha256_file(ffmpeg_path)}
        except OSError:
            reasons.append("ffmpeg_unavailable")
            ffmpeg_path = None

    if helper is not None and dotnet_path is not None:
        try:
            return_code, output, diagnostics = _run_bounded(
                [str(dotnet_path), str(helper), "doctor", "--json"], cwd=root
            )
            if diagnostics:
                raise ValueError("native doctor emitted diagnostics")
            doctor = json.loads(output.decode("utf-8"))
            doctor_ok, loopback_ready, public_helper = _doctor_contract(doctor)
            result["helper"].update(public_helper)
            result["system_audio_loopback_ready"] = (
                return_code == 0 and doctor_ok and loopback_ready
            )
            if not result["system_audio_loopback_ready"]:
                reasons.extend(["helper_doctor_failed", "wasapi_loopback_unavailable"])
        except (
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            subprocess.SubprocessError,
        ):
            reasons.append("helper_contract_invalid")

    if ffmpeg_path is not None:
        result["ffmpeg"]["available"] = True
        try:
            return_code, stdout, stderr = _run_bounded(
                [str(ffmpeg_path), "-hide_banner", "-devices"], cwd=root
            )
            output = stdout + b"\n" + stderr
            gdigrab = return_code == 0 and _GDI_DEVICE_RE.search(
                output.decode("utf-8", errors="replace")
            ) is not None
            result["ffmpeg"]["gdigrab_available"] = gdigrab
            result["screen_capture_ready"] = gdigrab
            if not gdigrab:
                reasons.append("gdigrab_unavailable")
        except (OSError, ValueError, subprocess.SubprocessError):
            reasons.append("gdigrab_unavailable")

    result["reasons"] = list(dict.fromkeys(reasons))
    if identities:
        digest = hashlib.sha256(canonical_json(identities).encode("utf-8")).hexdigest().upper()
        if not _SHA256_RE.fullmatch(digest):  # defensive contract assertion
            raise AssertionError("tool identity digest is invalid")
        result["tool_identity_digest"] = digest
    result["foundation_ready"] = bool(
        result["screen_capture_ready"]
        and result["system_audio_loopback_ready"]
        and not result["reasons"]
    )
    result["status"] = "foundation_ready" if result["foundation_ready"] else "blocked"
    return result
