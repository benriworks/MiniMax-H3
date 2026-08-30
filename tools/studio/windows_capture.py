from __future__ import annotations

"""Closed capability and execution contract for Windows desktop capture.

The public inspector never records a screen or audio sample. It only executes
the repository-owned native doctor and checks whether the pinned local FFmpeg
build exposes ``gdigrab`` and ``ffprobe``. Capture is a separate operation that
requires both explicit confirmations and accepts no caller-controlled paths,
devices, windows, microphones, commands, or FFmpeg arguments.
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
from typing import Any, Callable, Mapping

from .security import canonical_json, workspace_path


WINDOWS_CAPTURE_SCHEMA_VERSION = 1
WINDOWS_CAPTURE_IMPLEMENTATION_VERSION = "windows-capture-capability-v2"
WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION = (
    "windows-native-primary-display-loopback-v4"
)
WINDOWS_CAPTURE_PROVIDER = "local_windows_capture"
WINDOWS_CAPTURE_TIMING_SOURCE = "ffprobe"
WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION = (
    "h264-aac-primary-display-loopback-1920x1080-24fps-v4"
)
WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE = (
    "container_timestamps_durations_and_wasapi_packet_clock_v1"
)
WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE = (
    "blocked_pending_live_av_sync_validation"
)
WINDOWS_CAPTURE_OUTPUT_WIDTH = 1920
WINDOWS_CAPTURE_OUTPUT_HEIGHT = 1080
WINDOWS_CAPTURE_FRAME_RATE = 24
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
WINDOWS_CAPTURE_CONSENT_TTL_SECONDS = 60

_REQUEST_KEYS = {
    "schema_version",
    "target",
    "audio_mode",
    "cursor_mode",
    "duration_ms",
    "confirm_capture",
    "confirm_system_audio",
}
_EXECUTION_REQUEST_KEYS = _REQUEST_KEYS | {"consent_token"}
_EXPECTED_TARGET = "primary_display"
_EXPECTED_AUDIO_MODE = "default_render_loopback"
_EXPECTED_CURSOR_MODE = "hidden"
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_CONSENT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_GDI_DEVICE_RE = re.compile(r"(?m)^\s*D\s+gdigrab(?:\s|$)")
_MAX_PROCESS_OUTPUT_BYTES = 64 * 1024
_PROCESS_TIMEOUT_SECONDS = 10


class WindowsCaptureError(RuntimeError):
    """A native Windows capture operation failed behind the closed contract."""

    error_code = "local_windows_capture_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = str(message)


class WindowsCaptureValidationError(ValueError):
    """A capture request escaped the fixed v1 contract."""

    error_code = "invalid_windows_capture_request"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = str(message)


class WindowsCaptureToolError(WindowsCaptureError):
    """The repository-owned local capture tools failed safely."""


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


def windows_capture_request_digest(
    payload: Mapping[str, Any], *, tool_identity_digest: str
) -> str:
    normalized = validate_windows_capture_payload(dict(payload))
    if not isinstance(tool_identity_digest, str) or not _SHA256_RE.fullmatch(
        tool_identity_digest
    ):
        raise WindowsCaptureValidationError("tool identity digest is invalid")
    identity = {
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "request": normalized,
        "tool_identity_digest": tool_identity_digest,
        "output_policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def windows_capture_key(
    payload: Mapping[str, Any],
    nonce: str,
    *,
    tool_identity_digest: str,
) -> str:
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise WindowsCaptureValidationError("capture nonce is invalid")
    request_digest = windows_capture_request_digest(
        payload, tool_identity_digest=tool_identity_digest
    )
    return hashlib.sha256(
        canonical_json(
            {
                "request_digest": request_digest,
                "nonce": nonce,
            }
        ).encode("utf-8")
    ).hexdigest().upper()


def windows_capture_audit_payload(
    payload: Mapping[str, Any],
    *,
    capture_key: str | None = None,
    request_digest: str | None = None,
    tool_identity_digest: str | None = None,
) -> dict[str, Any]:
    normalized = validate_windows_capture_payload(dict(payload))
    audit = {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "target": normalized["target"],
        "audio_mode": normalized["audio_mode"],
        "cursor_mode": normalized["cursor_mode"],
        "duration_ms": normalized["duration_ms"],
        "explicit_capture_confirmation": True,
        "explicit_system_audio_confirmation": True,
        "output_policy": {
            "policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
            "width": WINDOWS_CAPTURE_OUTPUT_WIDTH,
            "height": WINDOWS_CAPTURE_OUTPUT_HEIGHT,
            "frame_rate": WINDOWS_CAPTURE_FRAME_RATE,
            "video_codec": "h264",
            "audio_codec": "aac",
        },
    }
    optional = (capture_key, request_digest, tool_identity_digest)
    if any(value is not None for value in optional):
        if not all(
            isinstance(value, str) and _SHA256_RE.fullmatch(value)
            for value in optional
        ):
            raise WindowsCaptureValidationError("capture audit identity is invalid")
        audit.update(
            {
                "capture_key": capture_key,
                "request_digest": request_digest,
                "tool_identity_digest": tool_identity_digest,
            }
        )
    return audit


def windows_capture_public_result(
    raw: Any,
    *,
    expected_capture_key: str,
    expected_duration_ms: int,
    expected_tool_identity_digest: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or not _SHA256_RE.fullmatch(expected_capture_key)
        or not _SHA256_RE.fullmatch(expected_tool_identity_digest)
    ):
        raise WindowsCaptureError(
            "The Windows capture worker returned an invalid result.",
            code="invalid_worker_result",
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or abs(duration_ms - expected_duration_ms)
        > (1000 + WINDOWS_CAPTURE_FRAME_RATE - 1) // WINDOWS_CAPTURE_FRAME_RATE
        or raw.get("provider") != WINDOWS_CAPTURE_PROVIDER
        or raw.get("timing_source") != WINDOWS_CAPTURE_TIMING_SOURCE
        or raw.get("capture_key") != expected_capture_key
        or raw.get("tool_identity_digest") != expected_tool_identity_digest
        or raw.get("target") != _EXPECTED_TARGET
        or raw.get("audio_mode") != _EXPECTED_AUDIO_MODE
        or raw.get("cache_hit") is not False
        or raw.get("provider_task_id") is not None
        or raw.get("actual_cost") != 0
        or raw.get("actual_capture_performed") is not True
        or raw.get("structural_timing_verified") is not True
        or raw.get("content_sync_verified") is not False
        or raw.get("live_validation_required") is not True
        or raw.get("validation_scope")
        != WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE
        or raw.get("public_release_ready") is not False
        or raw.get("public_release_gate")
        != WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE
    ):
        raise WindowsCaptureError(
            "The Windows capture worker returned invalid metadata.",
            code="invalid_worker_result",
        )
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "capture_key": expected_capture_key,
        "cache_hit": False,
        "provider": WINDOWS_CAPTURE_PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": WINDOWS_CAPTURE_TIMING_SOURCE,
        "target": _EXPECTED_TARGET,
        "audio_mode": _EXPECTED_AUDIO_MODE,
        "actual_capture_performed": True,
        # This proves only media/container structure and timestamp arithmetic.
        # It deliberately does not claim that visible events and audible events
        # are aligned in the captured content.
        "structural_timing_verified": True,
        "content_sync_verified": False,
        "live_validation_required": True,
        "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
        "public_release_ready": False,
        "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        "tool_identity_digest": expected_tool_identity_digest,
        "video_dimensions": {
            "width": WINDOWS_CAPTURE_OUTPUT_WIDTH,
            "height": WINDOWS_CAPTURE_OUTPUT_HEIGHT,
        },
        "frame_rate": WINDOWS_CAPTURE_FRAME_RATE,
        "output_policy": {
            "policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
            "audio": "default_render_loopback",
        },
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def validate_windows_capture_execution_payload(
    body: Any,
) -> tuple[dict[str, Any], str]:
    """Validate one consent-token-bound execution request.

    The raw consent token is deliberately kept outside the normalized capture
    payload so it cannot be copied into stage/job audit payloads by callers.
    """

    if not isinstance(body, dict) or set(body) != _EXECUTION_REQUEST_KEYS:
        raise WindowsCaptureValidationError(
            "execution body must contain the fixed Windows capture fields and consent_token"
        )
    token = body.get("consent_token")
    if not isinstance(token, str) or _CONSENT_TOKEN_RE.fullmatch(token) is None:
        raise WindowsCaptureValidationError("consent_token is invalid")
    payload = validate_windows_capture_payload(
        {key: body[key] for key in _REQUEST_KEYS}
    )
    return payload, token


def windows_capture_settings_digest(payload: Mapping[str, Any]) -> str:
    """Bind a consent intent to the exact user-visible capture settings."""

    normalized = validate_windows_capture_payload(dict(payload))
    return hashlib.sha256(
        canonical_json(
            {
                "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
                "request": normalized,
            }
        ).encode("utf-8")
    ).hexdigest().upper()


def windows_capture_consent_token_digest(token: str) -> str:
    """Return the only representation of a consent token allowed in SQLite."""

    if not isinstance(token, str) or _CONSENT_TOKEN_RE.fullmatch(token) is None:
        raise WindowsCaptureValidationError("consent_token is invalid")
    return hashlib.sha256(
        b"minimaxh3-windows-capture-consent-v1\x00" + token.encode("ascii")
    ).hexdigest().upper()


def windows_capture_session_binding_digest(session_token: str) -> str:
    """Derive a non-reversible binding for the authenticated Studio session."""

    if not isinstance(session_token, str) or len(session_token) < 32:
        raise WindowsCaptureValidationError("Studio session binding is invalid")
    return hashlib.sha256(
        b"minimaxh3-windows-capture-session-v1\x00"
        + session_token.encode("utf-8")
    ).hexdigest().upper()


def safe_windows_capture_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, (WindowsCaptureError, WindowsCaptureValidationError)):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return (
        "local_windows_capture_failed",
        "The local Windows screen capture job failed.",
    )


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


def _doctor_contract(
    value: Any,
) -> tuple[bool, bool, dict[str, Any], dict[str, Any]]:
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
        return (
            False,
            False,
            {
                "doctor_ok": False,
                "endpoint_active": False,
                "loopback_initialized": False,
                "recording_started": False,
                "capture_command_available": False,
            },
            {"target": _EXPECTED_TARGET, "width": None, "height": None},
        )
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
    capture_available = value.get("captureAvailable") is True
    display = value.get("display")
    if not isinstance(display, dict) or set(display) != {
        "target",
        "width",
        "height",
    }:
        raise ValueError("native doctor display contract is invalid")
    display_width = display.get("width")
    display_height = display.get("height")
    display_valid = bool(
        display.get("target") == _EXPECTED_TARGET
        and isinstance(display_width, int)
        and not isinstance(display_width, bool)
        and 1 <= display_width <= 16_384
        and isinstance(display_height, int)
        and not isinstance(display_height, bool)
        and 1 <= display_height <= 16_384
    )
    if not display_valid:
        raise ValueError("native doctor display result is invalid")
    doctor_ok = value.get("ok") is True
    if doctor_ok != (
        endpoint_active and loopback_ready and capture_available and display_valid
    ):
        raise ValueError("native doctor result is internally inconsistent")
    return (
        doctor_ok,
        loopback_ready,
        {
            "doctor_ok": doctor_ok,
            "endpoint_active": endpoint_active,
            "loopback_initialized": loopback_ready,
            "recording_started": False,
            "capture_command_available": capture_available,
        },
        {
            "target": _EXPECTED_TARGET,
            "width": display_width,
            "height": display_height,
        },
    )


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
            "capture_command_available": False,
        },
        "ffmpeg": {
            "available": False,
            "gdigrab_available": False,
            "ffprobe_available": False,
        },
        "display": {"target": _EXPECTED_TARGET, "width": None, "height": None},
        "tool_identity_digest": None,
    }


def inspect_windows_capture_capability(
    workspace: Path,
    *,
    platform_name: str | None = None,
    dotnet: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    _process_runner: Callable[[list[str], Path], tuple[int, bytes, bytes]] | None = None,
) -> dict[str, Any]:
    """Inspect fixed local tooling without starting capture or persisting data."""

    root = workspace.resolve(strict=True)
    process_runner = _process_runner or (lambda command, cwd: _run_bounded(command, cwd=cwd))
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
    ffprobe_path = _resolve_executable("ffprobe", ffprobe)
    if ffprobe_path is None:
        reasons.append("ffprobe_unavailable")

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

    if ffprobe_path is not None:
        try:
            identities["ffprobe"] = {"sha256": _sha256_file(ffprobe_path)}
        except OSError:
            reasons.append("ffprobe_unavailable")
            ffprobe_path = None

    if helper is not None and dotnet_path is not None:
        try:
            return_code, output, diagnostics = process_runner(
                [str(dotnet_path), str(helper), "doctor", "--json"], root
            )
            if diagnostics:
                raise ValueError("native doctor emitted diagnostics")
            doctor = json.loads(output.decode("utf-8"))
            doctor_ok, loopback_ready, public_helper, public_display = _doctor_contract(
                doctor
            )
            result["helper"].update(public_helper)
            result["display"] = public_display
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
            return_code, stdout, stderr = process_runner(
                [str(ffmpeg_path), "-hide_banner", "-devices"], root
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

    if ffprobe_path is not None:
        result["ffmpeg"]["ffprobe_available"] = True

    result["reasons"] = list(dict.fromkeys(reasons))
    if identities:
        digest = hashlib.sha256(canonical_json(identities).encode("utf-8")).hexdigest().upper()
        if not _SHA256_RE.fullmatch(digest):  # defensive contract assertion
            raise AssertionError("tool identity digest is invalid")
        result["tool_identity_digest"] = digest
    result["foundation_ready"] = bool(
        result["screen_capture_ready"]
        and result["system_audio_loopback_ready"]
        and result["helper"]["capture_command_available"]
        and result["ffmpeg"]["ffprobe_available"]
        and result["display"]["width"] is not None
        and result["display"]["height"] is not None
        and not result["reasons"]
    )
    result["capture_execution_enabled"] = result["foundation_ready"]
    result["status"] = "ready" if result["foundation_ready"] else "blocked"
    return result
