from __future__ import annotations

"""Structurally verified native Windows desktop and loopback capture.

The worker deliberately exposes one closed operation: capture the physical
primary display without the mouse cursor and the default render endpoint's
system mix for at most 30 seconds.  Callers cannot supply paths, device IDs,
window handles, microphone inputs, executables, or media-tool arguments.
Container timing validation is not represented as proof of content A/V sync.
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import ctypes
from ctypes import wintypes
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import assembly as _assembly
from .assembly import AssemblyError, _sha256_file, _streams
from .jobs import JobCancelled
from .security import canonical_json, relative_workspace_path, validate_identifier, workspace_path
from .windows_capture import (
    WINDOWS_CAPTURE_FRAME_RATE,
    WINDOWS_CAPTURE_HELPER_RELATIVE_PATH,
    WINDOWS_CAPTURE_OUTPUT_HEIGHT,
    WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
    WINDOWS_CAPTURE_OUTPUT_WIDTH,
    WINDOWS_CAPTURE_PROVIDER,
    WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
    WINDOWS_CAPTURE_SCHEMA_VERSION,
    WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
    WINDOWS_CAPTURE_TIMING_SOURCE,
    WindowsCaptureError,
    WindowsCaptureToolError,
    WindowsCaptureValidationError,
    inspect_windows_capture_capability,
    validate_windows_capture_payload,
    windows_capture_audit_payload,
    windows_capture_request_digest,
)


MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_AUDIO_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_DIAGNOSTICS_BYTES = 1024 * 1024
CAPTURE_BASE_TIMEOUT_SECONDS = 60
FFMPEG_TIMEOUT_SECONDS = 5 * 60
FFMPEG_THREADS = 2
SAMPLE_RATE = 48_000
CHANNELS = 2
BYTES_PER_FRAME = 4
HELPER_READY_TIMEOUT_SECONDS = 15
MAX_AV_START_SKEW_MS = 50
MAX_WASAPI_START_OFFSET_100NS = 5_000_000
MAX_WASAPI_QPC_DRIFT_100NS = 250_000
MAX_WASAPI_INITIAL_DISCONTINUITIES = 1
WINDOWS_CREATE_SUSPENDED = 0x00000004
# Duration policy is expressed at codec boundaries, never as a broad wall-clock
# percentage.  One 24 fps video frame is the only tolerated video rounding;
# PCM must retain the exact helper sample count and AAC may differ by one
# 1024-sample encoder frame.
MAX_VIDEO_BOUNDARY_ERROR_FRAMES = 1
MAX_AAC_BOUNDARY_ERROR_SAMPLES = 1_024
_PRIVACY_CLEANUP_MARKER = ".windows-capture-cleanup-required.json"
_FALLBACK_CLEANUP_LEDGER = "windows-capture-cleanup-ledger.json"
_FALLBACK_CLEANUP_LEDGER_PARTIAL = ".windows-capture-cleanup-ledger.json.partial"
_MAX_CLEANUP_LEDGER_BYTES = 256 * 1024
_MAX_CLEANUP_LEDGER_ENTRIES = 1000
_PROCESS_REAP_TIMEOUT_SECONDS = 5.0

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{32}$")
_PARTIAL_CAPTURE_RE = re.compile(r"^\.[0-9A-F]{64}\.partial$")
_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "screen-capture.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "screen-video.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "system-audio.wav", "kind": "audio", "mime": "audio/wav"},
    {"filename": "first-frame.png", "kind": "image", "mime": "image/png"},
    {"filename": "last-frame.png", "kind": "image", "mime": "image/png"},
    {"filename": "capture-report.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)
_MAXIMUM_BYTES = {
    "screen-capture.mp4": MAX_VIDEO_BYTES,
    "screen-video.mp4": MAX_VIDEO_BYTES,
    "system-audio.wav": MAX_AUDIO_BYTES,
    "first-frame.png": MAX_IMAGE_BYTES,
    "last-frame.png": MAX_IMAGE_BYTES,
    "capture-report.json": MAX_METADATA_BYTES,
    "ffprobe.json": MAX_METADATA_BYTES,
    "manifest.json": MAX_METADATA_BYTES,
}

ProgressCallback = Callable[[int, str], None]
_CLEANUP_BLOCKED_STAGES: set[str] = set()
_CLEANUP_BLOCKED_WORKSPACES: set[str] = set()
_CLEANUP_BLOCKED_STAGES_LOCK = threading.Lock()


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


class _WindowsKillOnCloseJob:
    """Own child capture processes and kill them if Studio disappears."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _TH32CS_SNAPTHREAD = 0x00000004
    _THREAD_SUSPEND_RESUME = 0x0002
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self) -> None:
        if os.name != "nt":
            raise WindowsCaptureToolError(
                "Windows process containment is unavailable.",
                code="windows_capture_unavailable",
            )
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Thread32First.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise WindowsCaptureToolError(
                "Windows process containment could not be created.",
                code="windows_capture_unavailable",
            )
        self._kernel32 = kernel32
        self._handle: int | None = int(handle)
        information = _JobObjectExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        if not kernel32.SetInformationJobObject(
            wintypes.HANDLE(self._handle),
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            self.close()
            raise WindowsCaptureToolError(
                "Windows process containment could not be configured.",
                code="windows_capture_unavailable",
            )

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if self._handle is None or process.poll() is not None:
            raise WindowsCaptureToolError(
                "A capture process could not be contained.",
                code="windows_capture_failed",
            )
        process_handle = getattr(process, "_handle", None)
        if process_handle is None or not self._kernel32.AssignProcessToJobObject(
            wintypes.HANDLE(self._handle), wintypes.HANDLE(int(process_handle))
        ):
            raise WindowsCaptureToolError(
                "A capture process could not be contained.",
                code="windows_capture_failed",
            )

    def resume(self, process: subprocess.Popen[bytes]) -> None:
        """Resume a process created suspended only after job assignment.

        ``subprocess.Popen`` closes the primary-thread handle before returning,
        so use the documented Tool Help APIs to locate the sole suspended
        primary thread.  Because no application code can run before this call,
        the process cannot create additional threads or begin capture before it
        belongs to the kill-on-close job.
        """

        if self._handle is None or process.poll() is not None:
            raise WindowsCaptureToolError(
                "A contained capture process could not be resumed.",
                code="windows_capture_failed",
            )
        snapshot = self._kernel32.CreateToolhelp32Snapshot(
            self._TH32CS_SNAPTHREAD, 0
        )
        if not snapshot or int(snapshot) == self._INVALID_HANDLE_VALUE:
            raise WindowsCaptureToolError(
                "A contained capture process could not be resumed.",
                code="windows_capture_failed",
            )
        thread_handles: list[int] = []
        try:
            try:
                entry = _ThreadEntry32()
                entry.dwSize = ctypes.sizeof(_ThreadEntry32)
                available = bool(
                    self._kernel32.Thread32First(
                        wintypes.HANDLE(snapshot), ctypes.byref(entry)
                    )
                )
                while available:
                    if int(entry.th32OwnerProcessID) == int(process.pid):
                        thread = self._kernel32.OpenThread(
                            self._THREAD_SUSPEND_RESUME,
                            False,
                            entry.th32ThreadID,
                        )
                        if not thread:
                            raise WindowsCaptureToolError(
                                "A contained capture process could not be resumed.",
                                code="windows_capture_failed",
                            )
                        thread_handles.append(int(thread))
                    entry.dwSize = ctypes.sizeof(_ThreadEntry32)
                    available = bool(
                        self._kernel32.Thread32Next(
                            wintypes.HANDLE(snapshot), ctypes.byref(entry)
                        )
                    )
            finally:
                self._kernel32.CloseHandle(wintypes.HANDLE(snapshot))
        except BaseException:
            for thread in thread_handles:
                self._kernel32.CloseHandle(wintypes.HANDLE(thread))
            raise
        if len(thread_handles) != 1:
            for thread in thread_handles:
                self._kernel32.CloseHandle(wintypes.HANDLE(thread))
            raise WindowsCaptureToolError(
                "A contained capture process had an invalid suspended state.",
                code="windows_capture_failed",
            )
        thread = thread_handles[0]
        try:
            previous_count = int(
                self._kernel32.ResumeThread(wintypes.HANDLE(thread))
            )
            if previous_count != 1:
                raise WindowsCaptureToolError(
                    "A contained capture process could not be resumed.",
                    code="windows_capture_failed",
                )
        finally:
            self._kernel32.CloseHandle(wintypes.HANDLE(thread))

    def close(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._handle = None
        self._kernel32.CloseHandle(wintypes.HANDLE(handle))


def _cancel(cancel_event: Any | None) -> None:
    _assembly._raise_if_cancelled(cancel_event)


def _report_progress(
    callback: ProgressCallback | None, progress: int, phase: str
) -> None:
    if callback is None:
        return
    try:
        callback(progress, phase)
    except Exception:
        # Progress is advisory; verified media and the atomic DB transition are
        # authoritative.
        return


def _clean_environment() -> dict[str, str]:
    # Capture children never need Studio's session token or provider keys.
    # Build an allowlist instead of trying to enumerate every possible secret
    # variable that a future integration might add.
    allowed_names = {
        "comspec",
        "path",
        "pathext",
        "systemroot",
        "temp",
        "tmp",
        "windir",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.casefold() in allowed_names
    }
    environment.update(
        {
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_MULTILEVEL_LOOKUP": "0",
            "DOTNET_NOLOGO": "1",
        }
    )
    return environment


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(callable(is_junction) and is_junction())


def _has_symlink_component(workspace: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(workspace)
    except ValueError:
        return True
    current = workspace
    for part in relative.parts:
        current = current / part
        if _is_link_like(current):
            return True
    return False


def _safe_capture_root(workspace: Path, run_id: str, capture_key: str) -> Path:
    validate_identifier(run_id, label="run id")
    if not isinstance(capture_key, str) or _SHA256_RE.fullmatch(capture_key) is None:
        raise WindowsCaptureValidationError(
            "capture_key is invalid", code="invalid_cache_key"
        )
    lexical_root = workspace / "outputs" / "studio" / "runs"
    lexical_run = lexical_root / run_id
    lexical_stage = lexical_run / "screen_capture"
    lexical_capture = lexical_stage / capture_key
    if any(
        _has_symlink_component(workspace, candidate)
        for candidate in (lexical_root, lexical_run, lexical_stage, lexical_capture)
    ):
        raise WindowsCaptureValidationError(
            "Windows capture output path must not contain symlinks",
            code="unsafe_output_path",
        )
    root = workspace_path(workspace, lexical_root, must_exist=False)
    run_directory = workspace_path(workspace, lexical_run, must_exist=False)
    stage_directory = workspace_path(workspace, lexical_stage, must_exist=False)
    capture_directory = workspace_path(
        workspace, lexical_capture, must_exist=False
    )
    for directory in (root, run_directory, stage_directory):
        if directory.exists() and (_is_link_like(directory) or not directory.is_dir()):
            raise WindowsCaptureValidationError(
                "Windows capture output path is unsafe", code="unsafe_output_path"
            )
        directory.mkdir(parents=True, exist_ok=True)
    if capture_directory.exists() and (
        _is_link_like(capture_directory) or not capture_directory.is_dir()
    ):
        raise WindowsCaptureValidationError(
            "Windows capture output path is unsafe", code="unsafe_output_path"
        )
    return capture_directory


def _remove_private_capture_directory(directory: Path) -> None:
    """Remove one exact raw-capture staging directory or fail visibly."""

    if _PARTIAL_CAPTURE_RE.fullmatch(directory.name) is None:
        raise WindowsCaptureValidationError(
            "Windows capture staging path is invalid", code="unsafe_output_path"
        )
    if not directory.exists() and not _is_link_like(directory):
        return
    if _is_link_like(directory) or not directory.is_dir():
        raise WindowsCaptureError(
            "Windows capture staging path is unsafe.",
            code="windows_capture_cleanup_failed",
        )
    last_error: OSError | None = None
    for retry in range(3):
        try:
            shutil.rmtree(directory)
            if directory.exists() or _is_link_like(directory):
                raise OSError("capture staging directory still exists")
            return
        except OSError as exc:
            last_error = exc
            if retry < 2:
                time.sleep(0.05 * (retry + 1))
    raise WindowsCaptureError(
        "Private Windows capture staging data could not be removed.",
        code="windows_capture_cleanup_failed",
    ) from last_error


def _cleanup_marker_path(stage_directory: Path) -> Path:
    return stage_directory / _PRIVACY_CLEANUP_MARKER


def _cleanup_marker_partial_path(stage_directory: Path) -> Path:
    marker = _cleanup_marker_path(stage_directory)
    return marker.with_name(f".{marker.name}.partial")


def _mark_cleanup_failure(
    stage_directory: Path, *, target_name: str, target_kind: str
) -> bool:
    """Persist one stage-local residual and verify it can be read back."""

    if target_kind == "partial":
        valid = _PARTIAL_CAPTURE_RE.fullmatch(target_name) is not None
    else:
        valid = target_kind == "published" and _SHA256_RE.fullmatch(target_name) is not None
    if not valid or _is_link_like(stage_directory) or not stage_directory.is_dir():
        return False
    marker = _cleanup_marker_path(stage_directory)
    if _is_link_like(marker):
        return False
    target = {"target_kind": target_kind, "target_name": target_name}
    existing = _read_cleanup_marker(stage_directory) if marker.exists() else None
    if marker.exists() and existing is None:
        return False
    targets = list(existing["targets"]) if existing is not None else []
    if target not in targets:
        targets.append(target)
    if len(targets) > 8:
        return False
    payload = {
        "schema_version": 1,
        "error_code": "windows_capture_cleanup_failed",
        "targets": targets,
    }
    partial = _cleanup_marker_partial_path(stage_directory)
    try:
        if partial.exists() or _is_link_like(partial):
            return False
        with partial.open("xb") as handle:
            handle.write((canonical_json(payload) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, marker)
        persisted = _read_cleanup_marker(stage_directory)
        return persisted is not None and target in persisted["targets"]
    except OSError:
        # Do not erase an incomplete marker: its fixed filename is itself a
        # startup fail-closed signal. The independent fallback ledger below
        # remains the authoritative recovery path when this write fails.
        return False


def _read_cleanup_marker_file(marker: Path) -> dict[str, Any] | None:
    try:
        if _is_link_like(marker) or not marker.is_file() or marker.stat().st_size > 4096:
            return None
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "error_code",
        "targets",
    }:
        return None
    if (
        value.get("schema_version") != 1
        or value.get("error_code") != "windows_capture_cleanup_failed"
        or not isinstance(value.get("targets"), list)
        or not 1 <= len(value["targets"]) <= 8
    ):
        return None
    seen: set[tuple[str, str]] = set()
    for target in value["targets"]:
        if not isinstance(target, dict) or set(target) != {
            "target_kind",
            "target_name",
        }:
            return None
        kind = target.get("target_kind")
        name = target.get("target_name")
        if (
            not isinstance(name, str)
            or kind not in {"partial", "published"}
            or (
                kind == "partial"
                and _PARTIAL_CAPTURE_RE.fullmatch(name) is None
            )
            or (
                kind == "published"
                and _SHA256_RE.fullmatch(name) is None
            )
            or (kind, name) in seen
        ):
            return None
        seen.add((kind, name))
    return value


def _read_cleanup_marker(stage_directory: Path) -> dict[str, Any] | None:
    return _read_cleanup_marker_file(_cleanup_marker_path(stage_directory))


def _cleanup_ledger_paths(
    workspace: Path, *, create_parent: bool
) -> tuple[Path, Path]:
    root = Path(workspace).resolve(strict=True)
    outputs = root / "outputs"
    studio = outputs / "studio"
    if _has_symlink_component(root, studio):
        raise WindowsCaptureError(
            "Windows capture fallback cleanup storage is unsafe.",
            code="windows_capture_cleanup_failed",
        )
    try:
        if create_parent:
            outputs.mkdir(exist_ok=True)
            studio.mkdir(exist_ok=True)
        if studio.exists() and (_is_link_like(studio) or not studio.is_dir()):
            raise OSError("fallback cleanup storage is not a directory")
        safe_studio = workspace_path(root, studio, must_exist=False)
    except (OSError, ValueError) as exc:
        raise WindowsCaptureError(
            "Windows capture fallback cleanup storage is unavailable.",
            code="windows_capture_cleanup_failed",
        ) from exc
    ledger = safe_studio / _FALLBACK_CLEANUP_LEDGER
    partial = safe_studio / _FALLBACK_CLEANUP_LEDGER_PARTIAL
    if _is_link_like(ledger) or _is_link_like(partial):
        raise WindowsCaptureError(
            "Windows capture fallback cleanup storage is unsafe.",
            code="windows_capture_cleanup_failed",
        )
    return ledger, partial


def _normalize_cleanup_ledger_entry(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict) or set(value) != {
        "run_id",
        "capture_key",
        "target_kind",
    }:
        return None
    run_id = value.get("run_id")
    capture_key = value.get("capture_key")
    target_kind = value.get("target_kind")
    if (
        not isinstance(run_id, str)
        or _RUN_ID_RE.fullmatch(run_id) is None
        or not isinstance(capture_key, str)
        or _SHA256_RE.fullmatch(capture_key) is None
        or target_kind not in {"partial", "published"}
    ):
        return None
    return {
        "run_id": run_id,
        "capture_key": capture_key,
        "target_kind": target_kind,
    }


def _read_cleanup_ledger_file(path: Path) -> list[dict[str, str]]:
    try:
        if (
            _is_link_like(path)
            or not path.is_file()
            or path.stat().st_size <= 0
            or path.stat().st_size > _MAX_CLEANUP_LEDGER_BYTES
        ):
            raise OSError("fallback cleanup ledger file is invalid")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger is unreadable.",
            code="windows_capture_cleanup_failed",
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "entries"}
        or value.get("schema_version") != 1
        or not isinstance(value.get("entries"), list)
        or len(value["entries"]) > _MAX_CLEANUP_LEDGER_ENTRIES
    ):
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger is invalid.",
            code="windows_capture_cleanup_failed",
        )
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in value["entries"]:
        entry = _normalize_cleanup_ledger_entry(raw)
        if entry is None:
            raise WindowsCaptureError(
                "Windows capture fallback cleanup ledger is invalid.",
                code="windows_capture_cleanup_failed",
            )
        identity = (
            entry["run_id"],
            entry["capture_key"],
            entry["target_kind"],
        )
        if identity in seen:
            raise WindowsCaptureError(
                "Windows capture fallback cleanup ledger contains duplicates.",
                code="windows_capture_cleanup_failed",
            )
        seen.add(identity)
        entries.append(entry)
    return entries


def _read_fallback_cleanup_ledger(workspace: Path) -> list[dict[str, str]]:
    ledger, partial = _cleanup_ledger_paths(workspace, create_parent=False)
    if partial.exists() or _is_link_like(partial):
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger has an incomplete update.",
            code="windows_capture_cleanup_failed",
        )
    if not ledger.exists():
        return []
    return _read_cleanup_ledger_file(ledger)


def _write_fallback_cleanup_ledger(
    workspace: Path, entries: Sequence[Mapping[str, str]]
) -> None:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in entries:
        entry = _normalize_cleanup_ledger_entry(dict(raw))
        if entry is None:
            raise WindowsCaptureError(
                "Windows capture fallback cleanup entry is invalid.",
                code="windows_capture_cleanup_failed",
            )
        identity = (
            entry["run_id"],
            entry["capture_key"],
            entry["target_kind"],
        )
        if identity not in seen:
            normalized.append(entry)
            seen.add(identity)
    if len(normalized) > _MAX_CLEANUP_LEDGER_ENTRIES:
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger is full.",
            code="windows_capture_cleanup_failed",
        )
    data = (
        canonical_json({"schema_version": 1, "entries": normalized}) + "\n"
    ).encode("utf-8")
    if len(data) > _MAX_CLEANUP_LEDGER_BYTES:
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger is too large.",
            code="windows_capture_cleanup_failed",
        )
    ledger, partial = _cleanup_ledger_paths(workspace, create_parent=True)
    try:
        if partial.exists() or _is_link_like(partial):
            raise OSError("fallback cleanup ledger update already exists")
        with partial.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, ledger)
        if _read_cleanup_ledger_file(ledger) != normalized:
            raise OSError("fallback cleanup ledger verification failed")
    except (OSError, WindowsCaptureError) as exc:
        if isinstance(exc, WindowsCaptureError):
            raise
        raise WindowsCaptureError(
            "Windows capture fallback cleanup ledger could not be persisted.",
            code="windows_capture_cleanup_failed",
        ) from exc


def _persist_cleanup_residual(
    workspace: Path,
    *,
    run_id: str,
    capture_key: str,
    target_kind: str,
    stage_directory: Path,
) -> None:
    validate_identifier(run_id, label="run id")
    if (
        _RUN_ID_RE.fullmatch(run_id) is None
        or not isinstance(capture_key, str)
        or _SHA256_RE.fullmatch(capture_key) is None
        or target_kind not in {
            "partial",
            "published",
        }
    ):
        raise WindowsCaptureValidationError(
            "Windows capture cleanup identity is invalid.",
            code="windows_capture_cleanup_failed",
        )
    root = Path(workspace).resolve(strict=True)
    stage_key = str(stage_directory.resolve(strict=False))
    root_key = str(root)
    with _CLEANUP_BLOCKED_STAGES_LOCK:
        _CLEANUP_BLOCKED_STAGES.add(stage_key)
        _CLEANUP_BLOCKED_WORKSPACES.add(root_key)
    target_name = (
        f".{capture_key}.partial" if target_kind == "partial" else capture_key
    )
    if _mark_cleanup_failure(
        stage_directory,
        target_name=target_name,
        target_kind=target_kind,
    ):
        return
    try:
        entries = _read_fallback_cleanup_ledger(root)
        entry = {
            "run_id": run_id,
            "capture_key": capture_key,
            "target_kind": target_kind,
        }
        if entry not in entries:
            entries.append(entry)
        _write_fallback_cleanup_ledger(root, entries)
    except WindowsCaptureError:
        # Neither durable cleanup location is trustworthy. The process-local
        # workspace latch remains set and every later capture fails preflight.
        raise


def _remove_published_capture_directory(directory: Path) -> None:
    if _SHA256_RE.fullmatch(directory.name) is None:
        raise WindowsCaptureValidationError(
            "Windows capture output path is invalid", code="unsafe_output_path"
        )
    if not directory.exists() and not _is_link_like(directory):
        return
    if _is_link_like(directory) or not directory.is_dir():
        raise WindowsCaptureError(
            "Windows capture output path is unsafe.",
            code="windows_capture_cleanup_failed",
        )
    last_error: OSError | None = None
    for retry in range(3):
        try:
            shutil.rmtree(directory)
            if directory.exists() or _is_link_like(directory):
                raise OSError("capture directory still exists")
            return
        except OSError as exc:
            last_error = exc
            if retry < 2:
                time.sleep(0.05 * (retry + 1))
    raise WindowsCaptureError(
        "Published Windows capture data could not be removed.",
        code="windows_capture_cleanup_failed",
    ) from last_error


def _assert_no_windows_capture_privacy_residual(workspace: Path) -> None:
    root_key = str(Path(workspace).resolve(strict=True))
    with _CLEANUP_BLOCKED_STAGES_LOCK:
        workspace_latched = root_key in _CLEANUP_BLOCKED_WORKSPACES
    if workspace_latched:
        raise WindowsCaptureError(
            "Windows capture privacy cleanup is required before recording.",
            code="windows_capture_cleanup_required",
        )
    try:
        if _read_fallback_cleanup_ledger(Path(workspace)):
            raise WindowsCaptureError(
                "Windows capture fallback cleanup is required before recording.",
                code="windows_capture_cleanup_required",
            )
    except WindowsCaptureError as exc:
        if exc.error_code == "windows_capture_cleanup_required":
            raise
        raise WindowsCaptureError(
            "Windows capture fallback cleanup state is unavailable.",
            code="windows_capture_cleanup_required",
        ) from exc
    runs_root = workspace / "outputs" / "studio" / "runs"
    if not runs_root.exists():
        return
    if _is_link_like(runs_root) or not runs_root.is_dir():
        raise WindowsCaptureError(
            "Windows capture cleanup state is unsafe.",
            code="windows_capture_cleanup_required",
        )
    try:
        for run_directory in runs_root.iterdir():
            if (
                _RUN_ID_RE.fullmatch(run_directory.name) is None
                or _is_link_like(run_directory)
                or not run_directory.is_dir()
            ):
                continue
            stage = run_directory / "screen_capture"
            if not stage.exists():
                continue
            if _is_link_like(stage) or not stage.is_dir():
                raise OSError("unsafe screen capture stage")
            with _CLEANUP_BLOCKED_STAGES_LOCK:
                latched = str(stage.resolve(strict=False)) in _CLEANUP_BLOCKED_STAGES
            marker = _cleanup_marker_path(stage)
            marker_partial = _cleanup_marker_partial_path(stage)
            if (
                latched
                or marker.exists()
                or _is_link_like(marker)
                or marker_partial.exists()
                or _is_link_like(marker_partial)
                or any(
                    _PARTIAL_CAPTURE_RE.fullmatch(child.name) is not None
                    for child in stage.iterdir()
                )
            ):
                raise WindowsCaptureError(
                    "Windows capture privacy cleanup is required before recording.",
                    code="windows_capture_cleanup_required",
                )
    except WindowsCaptureError:
        raise
    except OSError as exc:
        raise WindowsCaptureError(
            "Windows capture cleanup state could not be verified.",
            code="windows_capture_cleanup_required",
        ) from exc


def _cleanup_fallback_ledger(workspace: Path) -> int:
    ledger, _partial = _cleanup_ledger_paths(workspace, create_parent=False)
    entries = _read_fallback_cleanup_ledger(workspace)
    if not entries:
        return 0
    removed = 0
    for entry in entries:
        run_id = entry["run_id"]
        capture_key = entry["capture_key"]
        stage = (
            workspace
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
        )
        target_name = (
            f".{capture_key}.partial"
            if entry["target_kind"] == "partial"
            else capture_key
        )
        lexical_target = stage / target_name
        if _has_symlink_component(workspace, stage) or _has_symlink_component(
            workspace, lexical_target
        ):
            raise WindowsCaptureError(
                "Windows capture fallback cleanup target is unsafe.",
                code="windows_capture_cleanup_failed",
            )
        try:
            safe_stage = workspace_path(workspace, stage, must_exist=False)
            target = workspace_path(workspace, lexical_target, must_exist=False)
        except (OSError, ValueError) as exc:
            raise WindowsCaptureError(
                "Windows capture fallback cleanup target is unavailable.",
                code="windows_capture_cleanup_failed",
            ) from exc
        if safe_stage.exists() and (
            _is_link_like(safe_stage) or not safe_stage.is_dir()
        ):
            raise WindowsCaptureError(
                "Windows capture fallback cleanup target is unsafe.",
                code="windows_capture_cleanup_failed",
            )
        existed = target.exists() or _is_link_like(target)
        if entry["target_kind"] == "partial":
            _remove_private_capture_directory(target)
        else:
            _remove_published_capture_directory(target)
        if existed:
            removed += 1
    # Keep a valid empty ledger instead of unlinking it. Replacing a fully
    # fsynced empty document makes resolution atomic and independently auditable.
    if ledger.exists():
        _write_fallback_cleanup_ledger(workspace, [])
    return removed


def cleanup_stale_windows_capture_partials(workspace: Path) -> dict[str, int]:
    """Remove deterministic, unpublished native-capture staging directories.

    This is intended for Studio startup after durable jobs have been marked
    interrupted. It touches exact ``.<capture_key>.partial`` children and
    exact marker-authorized unpublished outputs under known ``screen_capture``
    stage directories, and never follows symlinks.
    """

    workspace = workspace.resolve(strict=True)
    removed = _cleanup_fallback_ledger(workspace)
    runs_root = workspace_path(
        workspace, workspace / "outputs" / "studio" / "runs", must_exist=False
    )
    if not runs_root.exists():
        with _CLEANUP_BLOCKED_STAGES_LOCK:
            _CLEANUP_BLOCKED_WORKSPACES.discard(str(workspace))
        return {"removed": removed, "failed": 0}
    if _is_link_like(runs_root) or not runs_root.is_dir():
        raise WindowsCaptureError(
            "Windows capture run storage is unsafe.",
            code="windows_capture_cleanup_failed",
        )
    failed = 0
    for run_directory in runs_root.iterdir():
        if (
            _RUN_ID_RE.fullmatch(run_directory.name) is None
            or _is_link_like(run_directory)
            or not run_directory.is_dir()
        ):
            continue
        stage_directory = run_directory / "screen_capture"
        if not stage_directory.exists():
            continue
        if _is_link_like(stage_directory) or not stage_directory.is_dir():
            failed += 1
            continue
        stage_failed = False
        marker = _cleanup_marker_path(stage_directory)
        marker_partial = _cleanup_marker_partial_path(stage_directory)
        if not marker.exists() and (
            marker_partial.exists() or _is_link_like(marker_partial)
        ):
            if _read_cleanup_marker_file(marker_partial) is None:
                failed += 1
                stage_failed = True
                continue
            try:
                os.replace(marker_partial, marker)
            except OSError:
                failed += 1
                stage_failed = True
                continue
        elif marker.exists() and (
            marker_partial.exists() or _is_link_like(marker_partial)
        ):
            if _is_link_like(marker_partial):
                failed += 1
                stage_failed = True
                continue
            try:
                marker_partial.unlink()
            except OSError:
                failed += 1
                stage_failed = True
                continue
        if marker.exists() or _is_link_like(marker):
            marker_value = _read_cleanup_marker(stage_directory)
            if marker_value is None:
                failed += 1
                stage_failed = True
                continue
            try:
                for marker_target in marker_value["targets"]:
                    target = stage_directory / marker_target["target_name"]
                    if marker_target["target_kind"] == "partial":
                        _remove_private_capture_directory(target)
                    else:
                        _remove_published_capture_directory(target)
                marker.unlink()
                removed += 1
            except (OSError, WindowsCaptureError):
                failed += 1
                stage_failed = True
                continue
        for candidate in stage_directory.iterdir():
            if _PARTIAL_CAPTURE_RE.fullmatch(candidate.name) is None:
                continue
            try:
                _remove_private_capture_directory(candidate)
                removed += 1
            except WindowsCaptureError:
                capture_key = candidate.name[1 : -len(".partial")]
                _persist_cleanup_residual(
                    workspace,
                    run_id=run_directory.name,
                    capture_key=capture_key,
                    target_kind="partial",
                    stage_directory=stage_directory,
                )
                failed += 1
                stage_failed = True
        if not stage_failed:
            with _CLEANUP_BLOCKED_STAGES_LOCK:
                _CLEANUP_BLOCKED_STAGES.discard(
                    str(stage_directory.resolve(strict=False))
                )
    if failed:
        raise WindowsCaptureError(
            "One or more private Windows capture staging directories could not be removed.",
            code="windows_capture_cleanup_failed",
        )
    with _CLEANUP_BLOCKED_STAGES_LOCK:
        _CLEANUP_BLOCKED_WORKSPACES.discard(str(workspace))
    return {"removed": removed, "failed": 0}


def _resolve_tools(
    workspace: Path,
    *,
    expected_tool_identity_digest: str,
    dotnet: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
) -> tuple[str, str, str, Path, int, int]:
    _cancel(cancel_event)
    if (
        not isinstance(expected_tool_identity_digest, str)
        or _SHA256_RE.fullmatch(expected_tool_identity_digest) is None
    ):
        raise WindowsCaptureValidationError("tool identity digest is invalid")
    try:
        dotnet_executable = _assembly._find_tool("dotnet", dotnet)
        ffmpeg_executable = _assembly._find_tool("ffmpeg", ffmpeg)
        ffprobe_executable = _assembly._find_tool("ffprobe", ffprobe)
        helper = workspace_path(
            workspace, WINDOWS_CAPTURE_HELPER_RELATIVE_PATH, must_exist=True
        )
    except (AssemblyError, OSError, ValueError) as exc:
        raise WindowsCaptureToolError(
            "The local Windows capture tools are unavailable.",
            code="windows_capture_unavailable",
        ) from exc
    def contained_capability_runner(
        arguments: list[str], runner_cwd: Path
    ) -> tuple[int, bytes, bytes]:
        return _run_contained_process(
            arguments,
            cwd=runner_cwd,
            timeout=HELPER_READY_TIMEOUT_SECONDS,
            label="Windows capture capability probe",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )

    capability = inspect_windows_capture_capability(
        workspace,
        dotnet=dotnet_executable,
        ffmpeg=ffmpeg_executable,
        ffprobe=ffprobe_executable,
        _process_runner=contained_capability_runner,
    )
    display = capability.get("display")
    width = display.get("width") if isinstance(display, dict) else None
    height = display.get("height") if isinstance(display, dict) else None
    if (
        capability.get("status") != "ready"
        or capability.get("capture_execution_enabled") is not True
        or capability.get("actual_capture_performed") is not False
        or capability.get("tool_identity_digest") != expected_tool_identity_digest
        or not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
    ):
        raise WindowsCaptureToolError(
            "The Windows capture capability changed after confirmation.",
            code="windows_capture_unavailable",
        )
    return (
        dotnet_executable,
        ffmpeg_executable,
        ffprobe_executable,
        helper,
        width,
        height,
    )


def _popen_options(*, suspended: bool = False) -> dict[str, Any]:
    if os.name == "nt":
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if suspended:
            # CPython exposes CREATE_NEW_PROCESS_GROUP but not consistently
            # CREATE_SUSPENDED. 0x4 is the documented CreateProcess flag.
            flags |= WINDOWS_CREATE_SUSPENDED
        return {"creationflags": flags}
    return {"start_new_session": True}


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    """Retire and reap one exact child, including an unassigned suspended child."""

    if process is None:
        return
    try:
        running = process.poll() is None
    except Exception:
        running = True
    if running:
        # A process may exist in the narrow Popen -> AssignProcessToJobObject
        # window. CREATE_SUSPENDED guarantees that no application code (and
        # therefore no capture/file write) can run there, while direct kill is
        # still required because the process is not yet owned by the Job.
        try:
            process.kill()
        except (OSError, AttributeError):
            _assembly._terminate_process_tree(
                process, deadline=time.monotonic() + _PROCESS_REAP_TIMEOUT_SECONDS
            )
    try:
        process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError, AttributeError):
        _assembly._terminate_process_tree(
            process, deadline=time.monotonic() + _PROCESS_REAP_TIMEOUT_SECONDS
        )
        try:
            process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
        except (subprocess.TimeoutExpired, OSError, AttributeError):
            return


def _run_contained_process(
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    label: str,
    cancel_event: Any | None,
    environment: Mapping[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    """Run one bounded child suspended, assigned, then resumed and reaped.

    Every FFmpeg, FFprobe, helper doctor, and capability probe launched from
    the capture worker uses this boundary.  The only unavoidable interval is
    between ``Popen`` and Job assignment; the primary thread remains suspended
    throughout it, so an orphan in that interval cannot record or write media.
    Startup deliberately does not kill processes by executable name because
    that could terminate an unrelated user process.
    """

    _cancel(cancel_event)
    containment: _WindowsKillOnCloseJob | None = None
    process: subprocess.Popen[bytes] | None = None
    registered = False
    readers: list[threading.Thread] = []
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    reader_failures: list[BaseException] = []
    excessive = threading.Event()
    limit = MAX_CAPTURE_DIAGNOSTICS_BYTES

    def drain(stream: Any, destination: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                remaining = limit + 1 - len(destination)
                if remaining > 0:
                    destination.extend(chunk[:remaining])
                if len(destination) > limit:
                    excessive.set()
        except (OSError, ValueError):
            return
        except BaseException as exc:
            reader_failures.append(exc)

    try:
        containment = _WindowsKillOnCloseJob()
        process = subprocess.Popen(
            list(arguments),
            cwd=str(cwd),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env=dict(environment or _clean_environment()),
            **_popen_options(suspended=True),
        )
        # No reader, media output, or application instruction is permitted
        # before this exact process has joined the kill-on-close Job Object.
        containment.assign(process)
        registered = _assembly._register_process(cancel_event, process)
        _cancel(cancel_event)
        if process.stdout is None or process.stderr is None:
            raise WindowsCaptureToolError(
                f"{label} did not expose bounded diagnostic pipes.",
                code="windows_capture_failed",
            )
        readers = [
            threading.Thread(
                target=drain,
                args=(process.stdout, stdout_buffer),
                name=f"windows-capture-{label}-stdout",
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, stderr_buffer),
                name=f"windows-capture-{label}-stderr",
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        containment.resume(process)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            _cancel(cancel_event)
            if excessive.is_set() or reader_failures:
                raise WindowsCaptureToolError(
                    f"{label} produced invalid diagnostics.",
                    code="windows_capture_failed",
                )
            if time.monotonic() >= deadline:
                raise WindowsCaptureToolError(
                    f"{label} timed out.", code="windows_capture_timeout"
                )
            time.sleep(0.02)
        for reader in readers:
            reader.join(timeout=2.0)
        if any(reader.is_alive() for reader in readers) or reader_failures:
            raise WindowsCaptureToolError(
                f"{label} diagnostics did not retire.",
                code="windows_capture_failed",
            )
        if excessive.is_set():
            raise WindowsCaptureToolError(
                f"{label} produced excessive diagnostics.",
                code="windows_capture_failed",
            )
        return int(process.returncode), bytes(stdout_buffer), bytes(stderr_buffer)
    except JobCancelled:
        raise
    except WindowsCaptureError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise WindowsCaptureToolError(
            f"{label} could not be started.", code="windows_capture_failed"
        ) from exc
    finally:
        if containment is not None:
            containment.close()
        _stop_process(process)
        for stream in (
            getattr(process, "stdout", None),
            getattr(process, "stderr", None),
        ):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for reader in readers:
            reader.join(timeout=0.25)
        if registered and process is not None:
            _assembly._unregister_process(cancel_event, process)


def _audio_format() -> dict[str, Any]:
    return {
        "encoding": "s16le",
        "samplesPerSecond": SAMPLE_RATE,
        "channels": CHANNELS,
        "bitsPerSample": 16,
        "bytesPerFrame": BYTES_PER_FRAME,
    }


def _ready_event_is_exact(line: bytes, duration_ms: int) -> bool:
    try:
        event = json.loads(line.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    expected = {
        "schemaVersion": 1,
        "operation": "capture_loopback",
        "event": "ready",
        "ok": True,
        "durationMs": duration_ms,
        "format": _audio_format(),
        "recordingStarted": False,
    }
    return event == expected


def _capture_to_master(
    *,
    dotnet: str,
    helper: Path,
    ffmpeg: str,
    duration_ms: int,
    display_width: int,
    display_height: int,
    output: Path,
    cwd: Path,
    cancel_event: Any | None,
) -> list[dict[str, Any]]:
    """Pipe fixed PCM loopback into one FFmpeg process recording gdigrab."""

    _cancel(cancel_event)
    duration_seconds = duration_ms / 1000
    helper_arguments = [
        dotnet,
        str(helper),
        "capture-loopback",
        "--duration-ms",
        str(duration_ms),
        "--start-gated",
    ]
    scale_filter = (
        f"scale={WINDOWS_CAPTURE_OUTPUT_WIDTH}:{WINDOWS_CAPTURE_OUTPUT_HEIGHT}:"
        "force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WINDOWS_CAPTURE_OUTPUT_WIDTH}:{WINDOWS_CAPTURE_OUTPUT_HEIGHT}:"
        "(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={WINDOWS_CAPTURE_FRAME_RATE}"
    )
    ffmpeg_arguments = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "gdigrab",
        "-draw_mouse",
        "0",
        "-framerate",
        str(WINDOWS_CAPTURE_FRAME_RATE),
        "-offset_x",
        "0",
        "-offset_y",
        "0",
        "-video_size",
        f"{display_width}x{display_height}",
        # Limit only the live desktop input. The PCM input retires on its exact
        # helper sample count, so an output-level -t cannot silently truncate
        # a later-starting audio stream.
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        "desktop",
        "-f",
        "s16le",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-i",
        "pipe:0",
        "-copyts",
        "-start_at_zero",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-sn",
        "-dn",
        "-vf",
        scale_filter,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        str(FFMPEG_THREADS),
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-fs",
        str(MAX_VIDEO_BYTES + MAX_AUDIO_BYTES),
        "-f",
        "matroska",
        str(output),
    ]
    environment = _clean_environment()
    containment: _WindowsKillOnCloseJob | None = None
    helper_process: subprocess.Popen[bytes] | None = None
    ffmpeg_process: subprocess.Popen[bytes] | None = None
    registered: list[subprocess.Popen[bytes]] = []
    readers: list[threading.Thread] = []
    buffers = {
        "helper_stderr": bytearray(),
        "ffmpeg_stdout": bytearray(),
        "ffmpeg_stderr": bytearray(),
    }
    excessive = threading.Event()
    helper_ready = threading.Event()
    helper_ready_invalid = threading.Event()
    reader_failures: list[BaseException] = []
    buffer_lock = threading.Lock()

    def drain(stream: Any, buffer: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                with buffer_lock:
                    remaining = MAX_CAPTURE_DIAGNOSTICS_BYTES + 1 - len(buffer)
                    if remaining > 0:
                        buffer.extend(chunk[:remaining])
                    if len(buffer) > MAX_CAPTURE_DIAGNOSTICS_BYTES:
                        excessive.set()
        except (OSError, ValueError):
            return
        except BaseException as exc:
            reader_failures.append(exc)

    def drain_helper(stream: Any, buffer: bytearray) -> None:
        try:
            # BufferedReader.read(size) on a pipe may wait for ``size`` bytes or
            # EOF. The helper deliberately remains alive waiting for the gate,
            # so consume the first bounded NDJSON line with readline instead.
            line = stream.readline(MAX_CAPTURE_DIAGNOSTICS_BYTES + 2)
            with buffer_lock:
                remaining = MAX_CAPTURE_DIAGNOSTICS_BYTES + 1 - len(buffer)
                if remaining > 0:
                    buffer.extend(line[:remaining])
                if (
                    len(buffer) > MAX_CAPTURE_DIAGNOSTICS_BYTES
                    or not line.endswith(b"\n")
                    or not _ready_event_is_exact(line.rstrip(b"\r\n"), duration_ms)
                ):
                    helper_ready_invalid.set()
                    return
                helper_ready.set()

            read_available = getattr(stream, "read1", None)
            if not callable(read_available):
                read_available = stream.read
            while True:
                chunk = read_available(64 * 1024)
                if not chunk:
                    return
                with buffer_lock:
                    remaining = MAX_CAPTURE_DIAGNOSTICS_BYTES + 1 - len(buffer)
                    if remaining > 0:
                        buffer.extend(chunk[:remaining])
                    if len(buffer) > MAX_CAPTURE_DIAGNOSTICS_BYTES:
                        excessive.set()
        except (OSError, ValueError):
            return
        except BaseException as exc:
            reader_failures.append(exc)

    try:
        # Both native children are created suspended.  They are assigned to a
        # kill-on-close Job Object before their primary threads are resumed, so
        # neither can touch the screen/audio device outside containment.
        containment = _WindowsKillOnCloseJob()
        helper_process = subprocess.Popen(
            helper_arguments,
            cwd=str(cwd),
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env=environment,
            **_popen_options(suspended=True),
        )
        containment.assign(helper_process)
        if _assembly._register_process(cancel_event, helper_process):
            registered.append(helper_process)
        if (
            helper_process.stdin is None
            or helper_process.stdout is None
            or helper_process.stderr is None
        ):
            raise WindowsCaptureToolError(
                "The Windows audio helper did not expose fixed pipes.",
                code="windows_capture_failed",
            )
        containment.resume(helper_process)
        helper_reader = threading.Thread(
            target=drain_helper,
            args=(helper_process.stderr, buffers["helper_stderr"]),
            name="windows-capture-helper_stderr",
            daemon=True,
        )
        readers.append(helper_reader)
        helper_reader.start()

        ready_deadline = time.monotonic() + HELPER_READY_TIMEOUT_SECONDS
        while not helper_ready.is_set():
            _cancel(cancel_event)
            if (
                helper_ready_invalid.is_set()
                or excessive.is_set()
                or reader_failures
                or helper_process.poll() is not None
            ):
                raise WindowsCaptureToolError(
                    "The Windows audio helper did not become safely ready.",
                    code="invalid_worker_result",
                )
            if time.monotonic() >= ready_deadline:
                raise WindowsCaptureToolError(
                    "The Windows audio helper readiness timed out.",
                    code="windows_capture_timeout",
                )
            time.sleep(0.01)

        ffmpeg_process = subprocess.Popen(
            ffmpeg_arguments,
            cwd=str(cwd),
            shell=False,
            stdin=helper_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env=environment,
            **_popen_options(suspended=True),
        )
        containment.assign(ffmpeg_process)
        if _assembly._register_process(cancel_event, ffmpeg_process):
            registered.append(ffmpeg_process)
        # FFmpeg now owns the read end. Closing the parent's duplicate is
        # required for EOF to propagate when the helper exits.
        helper_process.stdout.close()
        if ffmpeg_process.stdout is None or ffmpeg_process.stderr is None:
            raise WindowsCaptureToolError(
                "The Windows capture process did not expose diagnostic pipes.",
                code="windows_capture_failed",
            )
        for name, stream in (
            ("ffmpeg_stdout", ffmpeg_process.stdout),
            ("ffmpeg_stderr", ffmpeg_process.stderr),
        ):
            reader = threading.Thread(
                target=drain,
                args=(stream, buffers[name]),
                name=f"windows-capture-{name}",
                daemon=True,
            )
            readers.append(reader)
            reader.start()
        containment.resume(ffmpeg_process)
        _cancel(cancel_event)
        # Exactly one byte followed by EOF is the helper's start capability.
        # It is sent only after both capture processes are contained and the
        # helper has proved initialization without calling IAudioClient.Start.
        helper_process.stdin.write(b"S")
        helper_process.stdin.flush()
        helper_process.stdin.close()

        deadline = time.monotonic() + CAPTURE_BASE_TIMEOUT_SECONDS + duration_seconds
        while True:
            _cancel(cancel_event)
            if excessive.is_set() or reader_failures:
                raise WindowsCaptureToolError(
                    "The Windows capture tools produced invalid diagnostics.",
                    code="windows_capture_failed",
                )
            helper_code = helper_process.poll()
            ffmpeg_code = ffmpeg_process.poll()
            if helper_code is not None and ffmpeg_code is not None:
                break
            if ffmpeg_code is not None and helper_code is None:
                raise WindowsCaptureToolError(
                    "The screen recorder stopped before the audio helper.",
                    code="windows_capture_failed",
                )
            if time.monotonic() >= deadline:
                raise WindowsCaptureToolError(
                    "The Windows capture timed out.", code="windows_capture_timeout"
                )
            time.sleep(0.05)
        for reader in readers:
            reader.join(timeout=2.0)
        if any(reader.is_alive() for reader in readers) or reader_failures:
            raise WindowsCaptureToolError(
                "The Windows capture diagnostics did not retire.",
                code="windows_capture_failed",
            )
        if excessive.is_set():
            raise WindowsCaptureToolError(
                "The Windows capture tools produced excessive diagnostics.",
                code="windows_capture_failed",
            )
        if helper_process.returncode != 0 or ffmpeg_process.returncode != 0:
            raise WindowsCaptureToolError(
                "The local Windows capture failed.", code="windows_capture_failed"
            )
        if buffers["ffmpeg_stdout"] or buffers["ffmpeg_stderr"]:
            raise WindowsCaptureToolError(
                "The screen recorder returned unexpected diagnostics.",
                code="windows_capture_failed",
            )
        with buffer_lock:
            helper_metadata = bytes(buffers["helper_stderr"])
        return _parse_helper_events(helper_metadata, duration_ms)
    except JobCancelled:
        raise
    except WindowsCaptureError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise WindowsCaptureToolError(
            "The local Windows capture could not be started.",
            code="windows_capture_failed",
        ) from exc
    finally:
        if containment is not None:
            # Closing the only Job Object handle atomically terminates any
            # descendant that did not retire normally. The OS performs the
            # same close automatically if Studio itself crashes.
            containment.close()
        _stop_process(ffmpeg_process)
        _stop_process(helper_process)
        for process in reversed(registered):
            _assembly._unregister_process(cancel_event, process)
        for process in (helper_process, ffmpeg_process):
            if process is None:
                continue
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        for reader in readers:
            reader.join(timeout=0.25)


def _parse_helper_events(data: bytes, duration_ms: int) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
        lines = [line for line in text.splitlines() if line]
        events = [json.loads(line) for line in lines]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WindowsCaptureToolError(
            "The Windows audio helper returned invalid metadata.",
            code="invalid_worker_result",
        ) from exc
    if len(events) != 3 or any(not isinstance(item, dict) for item in events):
        raise WindowsCaptureToolError(
            "The Windows audio helper returned an invalid event sequence.",
            code="invalid_worker_result",
        )
    ready, started, completed = events
    audio_format = _audio_format()
    started_keys = {
        "schemaVersion",
        "operation",
        "event",
        "ok",
        "durationMs",
        "format",
        "recordingStarted",
    }
    completed_keys = started_keys | {
        "framesWritten",
        "bytesWritten",
        "paddedFrames",
        "silentFrames",
        "discontinuityCount",
        "timestampErrorCount",
        "firstPacketOffsetFrames",
        "gapFrames",
        "tailPaddedFrames",
        "firstPacketQpcOffset100ns",
        "qpcSpan100ns",
        "maxQpcDrift100ns",
        "startCallDuration100ns",
    }
    common = {
        "schemaVersion": 1,
        "operation": "capture_loopback",
        "ok": True,
        "durationMs": duration_ms,
        "format": audio_format,
        "recordingStarted": True,
    }
    if (
        set(ready) != started_keys
        or ready
        != {
            **{key: value for key, value in common.items() if key != "recordingStarted"},
            "event": "ready",
            "recordingStarted": False,
        }
        or set(started) != started_keys
        or {key: started.get(key) for key in common} != common
        or started.get("event") != "started"
        or set(completed) != completed_keys
        or {key: completed.get(key) for key in common} != common
        or completed.get("event") != "completed"
    ):
        raise WindowsCaptureToolError(
            "The Windows audio helper returned invalid event metadata.",
            code="invalid_worker_result",
        )
    expected_frames = duration_ms * 48
    expected_bytes = expected_frames * BYTES_PER_FRAME
    counters = (
        "paddedFrames",
        "silentFrames",
        "discontinuityCount",
        "timestampErrorCount",
        "firstPacketOffsetFrames",
        "gapFrames",
        "tailPaddedFrames",
        "firstPacketQpcOffset100ns",
        "qpcSpan100ns",
        "maxQpcDrift100ns",
        "startCallDuration100ns",
    )
    if (
        completed.get("framesWritten") != expected_frames
        or completed.get("bytesWritten") != expected_bytes
        or any(
            isinstance(completed.get(key), bool)
            or not isinstance(completed.get(key), int)
            or completed.get(key) < 0
            for key in counters
        )
        or completed.get("discontinuityCount")
        > MAX_WASAPI_INITIAL_DISCONTINUITIES
        or completed.get("timestampErrorCount") != 0
        or completed.get("paddedFrames")
        != completed.get("gapFrames") + completed.get("tailPaddedFrames")
        or completed.get("firstPacketOffsetFrames")
        > completed.get("gapFrames")
        or completed.get("firstPacketQpcOffset100ns")
        > MAX_WASAPI_START_OFFSET_100NS
        or completed.get("qpcSpan100ns") <= 0
        or completed.get("qpcSpan100ns") > duration_ms * 10_000 + 2_500_000
        or completed.get("maxQpcDrift100ns") > MAX_WASAPI_QPC_DRIFT_100NS
        or completed.get("startCallDuration100ns")
        > MAX_WASAPI_START_OFFSET_100NS
        or completed.get("paddedFrames") > expected_frames
        or completed.get("silentFrames") > expected_frames
    ):
        raise WindowsCaptureToolError(
            "The Windows audio helper returned invalid sample counts.",
            code="invalid_worker_result",
        )
    return [ready, started, completed]


def _fraction(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        result = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _format_names(probe: Mapping[str, Any]) -> set[str]:
    value = probe.get("format")
    raw = value.get("format_name") if isinstance(value, dict) else None
    if not isinstance(raw, str):
        return set()
    return {item.strip().casefold() for item in raw.split(",") if item.strip()}


def _finite_time_ms(value: Any) -> float | None:
    try:
        result = float(value) * 1000.0
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if str(parsed) != str(value).strip() or parsed < minimum:
        return None
    return parsed


def _stream_time_base(stream: Mapping[str, Any]) -> Fraction | None:
    raw = stream.get("time_base")
    if not isinstance(raw, str):
        return None
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def _expected_video_frames(duration_ms: int) -> int:
    target = Fraction(duration_ms * WINDOWS_CAPTURE_FRAME_RATE, 1000)
    return max(1, math.ceil(target))


def _validated_video_frame_count(
    stream: Mapping[str, Any], *, expected_duration_ms: int
) -> int:
    frames = _integer(stream.get("nb_read_frames"), minimum=1)
    expected = _expected_video_frames(expected_duration_ms)
    if (
        frames is None
        or abs(frames - expected) > MAX_VIDEO_BOUNDARY_ERROR_FRAMES
    ):
        raise WindowsCaptureError(
            "Windows capture video frame boundary is invalid.",
            code="invalid_output_media",
        )
    return frames


def _duration_samples(stream: Mapping[str, Any]) -> int | None:
    duration_ts = _integer(stream.get("duration_ts"), minimum=1)
    time_base = _stream_time_base(stream)
    if duration_ts is None or time_base is None:
        return None
    samples = Fraction(duration_ts) * time_base * SAMPLE_RATE
    return int(samples) if samples.denominator == 1 else None


def _validated_audio_sample_count(
    stream: Mapping[str, Any],
    *,
    expected_duration_ms: int,
    tolerance_samples: int,
) -> int:
    samples = _duration_samples(stream)
    expected = expected_duration_ms * SAMPLE_RATE // 1000
    if samples is None or abs(samples - expected) > tolerance_samples:
        raise WindowsCaptureError(
            "Windows capture audio sample boundary is invalid.",
            code="invalid_output_media",
        )
    return samples


def _master_packet_boundaries(
    probe: Mapping[str, Any],
    *,
    streams: Sequence[Mapping[str, Any]],
    expected_duration_ms: int,
) -> tuple[int, int, float]:
    packets = probe.get("packets")
    if not isinstance(packets, list) or any(
        not isinstance(packet, dict) for packet in packets
    ):
        raise WindowsCaptureError(
            "Windows capture packet boundaries are unavailable.",
            code="invalid_output_media",
        )
    by_index: dict[int, list[Mapping[str, Any]]] = {}
    for packet in packets:
        index = _integer(packet.get("stream_index"), minimum=0)
        pts = _integer(packet.get("pts"), minimum=-2**63)
        duration = _integer(packet.get("duration"), minimum=1)
        if index is None or pts is None or duration is None:
            raise WindowsCaptureError(
                "Windows capture packet boundary is invalid.",
                code="invalid_output_media",
            )
        by_index.setdefault(index, []).append(packet)

    stream_indexes = [_integer(stream.get("index"), minimum=0) for stream in streams]
    if any(index is None for index in stream_indexes) or set(by_index) != set(
        stream_indexes
    ):
        raise WindowsCaptureError(
            "Windows capture packet streams are invalid.",
            code="invalid_output_media",
        )
    video_index = int(stream_indexes[0])
    audio_index = int(stream_indexes[1])
    video_packets = by_index[video_index]
    audio_packets = by_index[audio_index]
    expected_video_frames = _expected_video_frames(expected_duration_ms)
    if abs(len(video_packets) - expected_video_frames) > MAX_VIDEO_BOUNDARY_ERROR_FRAMES:
        raise WindowsCaptureError(
            "Windows capture master video frame boundary is invalid.",
            code="invalid_output_media",
        )

    expected_samples = expected_duration_ms * SAMPLE_RATE // 1000
    audio_packet_bytes = [
        _integer(packet.get("size"), minimum=1) for packet in audio_packets
    ]
    if any(value is None for value in audio_packet_bytes) or sum(
        int(value) for value in audio_packet_bytes
    ) != expected_samples * BYTES_PER_FRAME:
        raise WindowsCaptureError(
            "Windows capture master audio sample boundary is invalid.",
            code="invalid_output_media",
        )
    stream_time_bases = {
        int(index): _stream_time_base(stream)
        for index, stream in zip(stream_indexes, streams, strict=True)
    }
    if any(value is None for value in stream_time_bases.values()):
        raise WindowsCaptureError(
            "Windows capture master packet time base is invalid.",
            code="invalid_output_media",
        )
    packet_starts: list[Fraction] = []
    packet_ends: list[Fraction] = []
    for index, stream_packets in by_index.items():
        time_base = stream_time_bases[index]
        if time_base is None:
            raise WindowsCaptureError(
                "Windows capture master packet time base is invalid.",
                code="invalid_output_media",
            )
        for packet in stream_packets:
            start = Fraction(int(packet["pts"])) * time_base
            end = Fraction(
                int(packet["pts"]) + int(packet["duration"])
            ) * time_base
            packet_starts.append(start)
            packet_ends.append(end)
    packet_span_ms = float(
        (max(packet_ends) - min(packet_starts)) * 1000
    )
    return len(video_packets), expected_samples, packet_span_ms


def _capture_timing_probe(
    ffprobe: str,
    path: Path,
    *,
    cwd: Path,
    cancel_event: Any | None,
) -> dict[str, Any]:
    try:
        return_code, output, diagnostics = _run_contained_process(
            [
                ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-count_frames",
                "-show_packets",
                "-show_entries",
                "format=format_name,duration,size,start_time:"
                "stream=index,codec_type,codec_name,start_time,duration,duration_ts,"
                "time_base,nb_read_frames,r_frame_rate,avg_frame_rate,sample_rate:"
                "packet=stream_index,pts,duration,size",
                "-of",
                "json",
                str(path),
            ],
            cwd=cwd,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            label="Windows capture timing probe",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
        if return_code != 0 or diagnostics:
            raise WindowsCaptureToolError(
                "Windows capture timing probe failed.",
                code="invalid_output_media",
            )
        value = json.loads(output.decode("utf-8"))
    except JobCancelled:
        raise
    except WindowsCaptureError:
        raise
    except (AssemblyError, UnicodeError, json.JSONDecodeError) as exc:
        raise WindowsCaptureToolError(
            "Windows capture timing metadata is unavailable.",
            code="invalid_output_media",
        ) from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("streams"), list)
        or not isinstance(value.get("packets"), list)
    ):
        raise WindowsCaptureToolError(
            "Windows capture timing metadata is invalid.",
            code="invalid_output_media",
        )
    return value


def _capture_json_probe(
    ffprobe: str,
    path: Path,
    *,
    cwd: Path,
    cancel_event: Any | None,
) -> dict[str, Any]:
    """Probe published media through the same contained process boundary."""

    return_code, output, diagnostics = _run_contained_process(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-count_frames",
            "-show_entries",
            "format=format_name,duration,size,start_time:"
            "stream=index,codec_type,codec_name,width,height,pix_fmt,start_time,"
            "r_frame_rate,avg_frame_rate,sample_rate,channels,bits_per_sample,"
            "codec_tag_string,duration,duration_ts,time_base,nb_frames,"
            "nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        cwd=cwd,
        timeout=FFMPEG_TIMEOUT_SECONDS,
        label="Windows capture media probe",
        cancel_event=cancel_event,
        environment=_clean_environment(),
    )
    if return_code != 0 or diagnostics:
        raise WindowsCaptureToolError(
            "Windows capture media probe failed.", code="invalid_output_media"
        )
    try:
        value = json.loads(output.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WindowsCaptureToolError(
            "Windows capture media probe returned invalid metadata.",
            code="invalid_output_media",
        ) from exc
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        raise WindowsCaptureToolError(
            "Windows capture media metadata is invalid.",
            code="invalid_output_media",
        )
    return value


def _validate_master_synchronization(
    probe: Mapping[str, Any],
    *,
    completed_event: Mapping[str, Any],
    expected_duration_ms: int,
) -> dict[str, Any]:
    streams = probe.get("streams")
    if (
        not isinstance(streams, list)
        or len(streams) != 2
        or any(not isinstance(item, dict) for item in streams)
        or [item.get("codec_type") for item in streams] != ["video", "audio"]
        or "matroska" not in _format_names(probe)
    ):
        raise WindowsCaptureError(
            "Windows capture synchronization streams are invalid.",
            code="invalid_output_media",
        )
    video_frames, audio_samples, master_duration_ms = _master_packet_boundaries(
        probe,
        streams=streams,
        expected_duration_ms=expected_duration_ms,
    )
    declared_video_frames = _integer(streams[0].get("nb_read_frames"), minimum=1)
    if declared_video_frames is None or declared_video_frames != video_frames:
        raise WindowsCaptureError(
            "Windows capture master frame count is inconsistent.",
            code="invalid_output_media",
        )
    video_start_ms = _finite_time_ms(streams[0].get("start_time"))
    audio_start_ms = _finite_time_ms(streams[1].get("start_time"))
    time_bases = (
        _fraction(streams[0].get("time_base")),
        _fraction(streams[1].get("time_base")),
    )
    if (
        video_start_ms is None
        or audio_start_ms is None
        or any(value is None for value in time_bases)
        or abs(master_duration_ms - expected_duration_ms)
        > math.ceil(1000 / WINDOWS_CAPTURE_FRAME_RATE)
    ):
        raise WindowsCaptureError(
            "Windows capture synchronization timestamps are unavailable.",
            code="invalid_output_media",
        )
    earliest_start_ms = min(video_start_ms, audio_start_ms)
    start_skew_ms = abs(video_start_ms - audio_start_ms)
    if (
        earliest_start_ms < -1.0
        or earliest_start_ms > MAX_AV_START_SKEW_MS
        or start_skew_ms > MAX_AV_START_SKEW_MS
    ):
        raise WindowsCaptureError(
            "Windows capture A/V start synchronization is outside policy.",
            code="invalid_output_media",
        )
    required_helper_values = {
        "firstPacketOffsetFrames",
        "gapFrames",
        "tailPaddedFrames",
        "firstPacketQpcOffset100ns",
        "qpcSpan100ns",
        "maxQpcDrift100ns",
        "startCallDuration100ns",
    }
    if any(
        isinstance(completed_event.get(key), bool)
        or not isinstance(completed_event.get(key), int)
        or completed_event.get(key) < 0
        for key in required_helper_values
    ):
        raise WindowsCaptureError(
            "Windows audio synchronization metadata is invalid.",
            code="invalid_worker_result",
        )
    return {
        "method": "ffprobe_container_timestamps_wasapi_qpc_v2",
        "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
        # WASAPI's packet QPC and FFmpeg's container timestamps are checked
        # independently.  gdigrab's first visible frame is not observed on the
        # WASAPI QPC clock, so neither this function nor mock tests can prove
        # synchronization of audible and visible events in the actual content.
        "source_clock_correlation_verified": False,
        "max_start_skew_ms": MAX_AV_START_SKEW_MS,
        "master_video_start_ms": round(video_start_ms, 3),
        "master_audio_start_ms": round(audio_start_ms, 3),
        "master_start_skew_ms": round(start_skew_ms, 3),
        "master_duration_ms": round(master_duration_ms, 3),
        "wasapi_first_packet_offset_frames": completed_event[
            "firstPacketOffsetFrames"
        ],
        "wasapi_gap_frames": completed_event["gapFrames"],
        "wasapi_tail_padded_frames": completed_event["tailPaddedFrames"],
        "wasapi_first_packet_qpc_offset_100ns": completed_event[
            "firstPacketQpcOffset100ns"
        ],
        "wasapi_qpc_span_100ns": completed_event["qpcSpan100ns"],
        "wasapi_max_qpc_drift_100ns": completed_event["maxQpcDrift100ns"],
        "wasapi_start_call_duration_100ns": completed_event[
            "startCallDuration100ns"
        ],
        "master_video_frames": video_frames,
        "master_audio_samples": audio_samples,
    }


def _final_mp4_timing(
    probe: Mapping[str, Any], *, expected_duration_ms: int
) -> dict[str, float]:
    """Validate final MP4 timestamps without claiming content synchronization."""

    streams = probe.get("streams")
    if (
        not isinstance(streams, list)
        or len(streams) != 2
        or any(not isinstance(item, dict) for item in streams)
        or [item.get("codec_type") for item in streams] != ["video", "audio"]
        or "mp4" not in _format_names(probe)
    ):
        raise WindowsCaptureError(
            "Windows capture final MP4 synchronization streams are invalid.",
            code="invalid_output_media",
        )
    video_start_ms = _finite_time_ms(streams[0].get("start_time"))
    audio_start_ms = _finite_time_ms(streams[1].get("start_time"))
    video_duration_ms = _finite_time_ms(streams[0].get("duration"))
    audio_duration_ms = _finite_time_ms(streams[1].get("duration"))
    format_value = probe.get("format")
    format_duration_ms = _finite_time_ms(
        format_value.get("duration") if isinstance(format_value, dict) else None
    )
    timing_values = (
        video_start_ms,
        audio_start_ms,
        video_duration_ms,
        audio_duration_ms,
        format_duration_ms,
    )
    duration_tolerance_ms = math.ceil(1000 / WINDOWS_CAPTURE_FRAME_RATE)
    if (
        any(value is None for value in timing_values)
        or any(
            abs(float(value) - expected_duration_ms) > duration_tolerance_ms
            for value in (video_duration_ms, audio_duration_ms, format_duration_ms)
        )
    ):
        raise WindowsCaptureError(
            "Windows capture final MP4 timestamps or durations are unavailable.",
            code="invalid_output_media",
        )
    assert video_start_ms is not None
    assert audio_start_ms is not None
    assert video_duration_ms is not None
    assert audio_duration_ms is not None
    assert format_duration_ms is not None
    earliest_start_ms = min(video_start_ms, audio_start_ms)
    start_skew_ms = abs(video_start_ms - audio_start_ms)
    if (
        earliest_start_ms < -1.0
        or earliest_start_ms > MAX_AV_START_SKEW_MS
        or start_skew_ms > MAX_AV_START_SKEW_MS
    ):
        raise WindowsCaptureError(
            "Windows capture final MP4 A/V timestamps are outside policy.",
            code="invalid_output_media",
        )
    return {
        "final_mp4_video_start_ms": round(video_start_ms, 3),
        "final_mp4_audio_start_ms": round(audio_start_ms, 3),
        "final_mp4_start_skew_ms": round(start_skew_ms, 3),
        "final_mp4_video_duration_ms": round(video_duration_ms, 3),
        "final_mp4_audio_duration_ms": round(audio_duration_ms, 3),
        "final_mp4_duration_ms": round(format_duration_ms, 3),
    }


def _complete_synchronization_record(
    master: Mapping[str, Any],
    final_mp4_probe: Mapping[str, Any],
    *,
    expected_duration_ms: int,
) -> dict[str, Any]:
    return {
        **dict(master),
        **_final_mp4_timing(
            final_mp4_probe, expected_duration_ms=expected_duration_ms
        ),
        "structural_timing_verified": True,
        "container_timestamps_verified": True,
        "wasapi_packet_timing_verified": True,
        "content_sync_verified": False,
        "live_validation_required": True,
    }


def _validate_video_stream(stream: Mapping[str, Any]) -> None:
    rates = (
        _fraction(stream.get("r_frame_rate")),
        _fraction(stream.get("avg_frame_rate")),
    )
    if (
        stream.get("codec_type") != "video"
        or stream.get("codec_name") != "h264"
        or stream.get("pix_fmt") != "yuv420p"
        or stream.get("width") != WINDOWS_CAPTURE_OUTPUT_WIDTH
        or stream.get("height") != WINDOWS_CAPTURE_OUTPUT_HEIGHT
        or any(
            rate is None or abs(rate - WINDOWS_CAPTURE_FRAME_RATE) > 0.01
            for rate in rates
        )
    ):
        raise WindowsCaptureError(
            "Windows capture video format is invalid.", code="invalid_output_media"
        )


def _validate_audio_stream(stream: Mapping[str, Any], *, codec: str) -> None:
    try:
        sample_rate = int(stream.get("sample_rate"))
    except (TypeError, ValueError):
        sample_rate = -1
    if (
        stream.get("codec_type") != "audio"
        or stream.get("codec_name") != codec
        or sample_rate != SAMPLE_RATE
        or stream.get("channels") != CHANNELS
    ):
        raise WindowsCaptureError(
            "Windows capture audio format is invalid.", code="invalid_output_media"
        )


def _validate_probe_set(
    *,
    screen_capture: Mapping[str, Any],
    screen_video: Mapping[str, Any],
    system_audio: Mapping[str, Any],
    expected_duration_ms: int,
) -> int:
    if "mp4" not in _format_names(screen_capture) or "mp4" not in _format_names(
        screen_video
    ):
        raise WindowsCaptureError(
            "Windows capture video container is invalid.", code="invalid_output_media"
        )
    if "wav" not in _format_names(system_audio):
        raise WindowsCaptureError(
            "Windows capture audio container is invalid.", code="invalid_output_media"
        )
    try:
        combined_streams = _streams(screen_capture)
        video_streams = _streams(screen_video)
        audio_streams = _streams(system_audio)
    except AssemblyError as exc:
        raise WindowsCaptureError(
            "Windows capture streams are invalid.", code="invalid_output_media"
        ) from exc
    if (
        len(combined_streams) != 2
        or [item.get("codec_type") for item in combined_streams] != ["video", "audio"]
        or len(video_streams) != 1
        or len(audio_streams) != 1
    ):
        raise WindowsCaptureError(
            "Windows capture stream counts are invalid.", code="invalid_output_media"
        )
    _validate_video_stream(combined_streams[0])
    _validate_audio_stream(combined_streams[1], codec="aac")
    _validate_video_stream(video_streams[0])
    _validate_audio_stream(audio_streams[0], codec="pcm_s16le")
    video_frame_counts = (
        _validated_video_frame_count(
            combined_streams[0], expected_duration_ms=expected_duration_ms
        ),
        _validated_video_frame_count(
            video_streams[0], expected_duration_ms=expected_duration_ms
        ),
    )
    if video_frame_counts[0] != video_frame_counts[1]:
        raise WindowsCaptureError(
            "Windows capture video frame boundaries are inconsistent.",
            code="invalid_output_media",
        )
    _validated_audio_sample_count(
        combined_streams[1],
        expected_duration_ms=expected_duration_ms,
        tolerance_samples=MAX_AAC_BOUNDARY_ERROR_SAMPLES,
    )
    _validated_audio_sample_count(
        audio_streams[0],
        expected_duration_ms=expected_duration_ms,
        tolerance_samples=0,
    )
    return int(
        round(Fraction(video_frame_counts[0] * 1000, WINDOWS_CAPTURE_FRAME_RATE))
    )


def _validate_png(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise WindowsCaptureError(
            "Windows capture frame is unavailable.", code="invalid_output_media"
        )
    size = path.stat().st_size
    if (
        size < 8
        or size > MAX_IMAGE_BYTES
        or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"
    ):
        raise WindowsCaptureError(
            "Windows capture frame is invalid.", code="invalid_output_media"
        )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise WindowsCaptureError(
            "Windows capture metadata is too large.", code="metadata_too_large"
        )
    partial = path.with_name(f".{path.name}.partial")
    partial.write_bytes(data)
    os.replace(partial, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size <= 0
            or path.stat().st_size > MAX_METADATA_BYTES
        ):
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def _read_manifest(path: Path) -> dict[str, Any] | None:
    value = _read_json(path)
    if value is None or not isinstance(value.get("manifest_sha256"), str):
        return None
    digest = value["manifest_sha256"]
    body = dict(value)
    body.pop("manifest_sha256", None)
    return value if _manifest_digest(body) == digest.upper() else None


def _artifact_record(
    workspace: Path, directory: Path, spec: Mapping[str, str]
) -> dict[str, Any]:
    path = directory / spec["filename"]
    stat = path.stat()
    relative = relative_workspace_path(workspace, path)
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": stat.st_size,
        "sha256": _sha256_file(path),
        "mime": spec["mime"],
        "media_type": spec["mime"],
        "origin": "studio",
        "version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _output_policy() -> dict[str, Any]:
    return {
        "policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
        "width": WINDOWS_CAPTURE_OUTPUT_WIDTH,
        "height": WINDOWS_CAPTURE_OUTPUT_HEIGHT,
        "frame_rate": WINDOWS_CAPTURE_FRAME_RATE,
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "audio_codec": "aac",
        "audio_sample_rate": SAMPLE_RATE,
        "audio_channels": CHANNELS,
        "screen_target": "primary_display",
        "audio_target": "default_render_loopback",
        "cursor": "hidden",
    }


def _synchronization_record_is_valid(
    value: Any, *, expected_duration_ms: int
) -> bool:
    expected_keys = {
        "method",
        "validation_scope",
        "structural_timing_verified",
        "container_timestamps_verified",
        "wasapi_packet_timing_verified",
        "source_clock_correlation_verified",
        "content_sync_verified",
        "live_validation_required",
        "max_start_skew_ms",
        "master_video_start_ms",
        "master_audio_start_ms",
        "master_start_skew_ms",
        "master_duration_ms",
        "final_mp4_video_start_ms",
        "final_mp4_audio_start_ms",
        "final_mp4_start_skew_ms",
        "final_mp4_video_duration_ms",
        "final_mp4_audio_duration_ms",
        "final_mp4_duration_ms",
        "wasapi_first_packet_offset_frames",
        "wasapi_gap_frames",
        "wasapi_tail_padded_frames",
        "wasapi_first_packet_qpc_offset_100ns",
        "wasapi_qpc_span_100ns",
        "wasapi_max_qpc_drift_100ns",
        "wasapi_start_call_duration_100ns",
        "master_video_frames",
        "master_audio_samples",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("method")
        != "ffprobe_container_timestamps_wasapi_qpc_v2"
        or value.get("validation_scope")
        != WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE
        or value.get("structural_timing_verified") is not True
        or value.get("container_timestamps_verified") is not True
        or value.get("wasapi_packet_timing_verified") is not True
        or value.get("source_clock_correlation_verified") is not False
        or value.get("content_sync_verified") is not False
        or value.get("live_validation_required") is not True
        or value.get("max_start_skew_ms") != MAX_AV_START_SKEW_MS
    ):
        return False
    timing_keys = {
        "master_video_start_ms",
        "master_audio_start_ms",
        "master_start_skew_ms",
        "master_duration_ms",
        "final_mp4_video_start_ms",
        "final_mp4_audio_start_ms",
        "final_mp4_start_skew_ms",
        "final_mp4_video_duration_ms",
        "final_mp4_audio_duration_ms",
        "final_mp4_duration_ms",
    }
    timing_values = tuple(value.get(key) for key in timing_keys)
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in timing_values
    ):
        return False
    for prefix in ("master", "final_mp4"):
        video_start_ms = float(value[f"{prefix}_video_start_ms"])
        audio_start_ms = float(value[f"{prefix}_audio_start_ms"])
        start_skew_ms = float(value[f"{prefix}_start_skew_ms"])
        if (
            min(video_start_ms, audio_start_ms) < -1.0
            or min(video_start_ms, audio_start_ms) > MAX_AV_START_SKEW_MS
            or start_skew_ms < 0
            or start_skew_ms > MAX_AV_START_SKEW_MS
            or abs(start_skew_ms - abs(video_start_ms - audio_start_ms)) > 0.002
        ):
            return False
    duration_tolerance_ms = math.ceil(1000 / WINDOWS_CAPTURE_FRAME_RATE)
    if any(
        abs(float(value[key]) - expected_duration_ms) > duration_tolerance_ms
        for key in {
            "master_duration_ms",
            "final_mp4_video_duration_ms",
            "final_mp4_audio_duration_ms",
            "final_mp4_duration_ms",
        }
    ):
        return False
    integer_keys = {
        "max_start_skew_ms",
        "wasapi_first_packet_offset_frames",
        "wasapi_gap_frames",
        "wasapi_tail_padded_frames",
        "wasapi_first_packet_qpc_offset_100ns",
        "wasapi_qpc_span_100ns",
        "wasapi_max_qpc_drift_100ns",
        "wasapi_start_call_duration_100ns",
        "master_video_frames",
        "master_audio_samples",
    }
    if any(
        isinstance(value.get(key), bool)
        or not isinstance(value.get(key), int)
        or value.get(key) < 0
        for key in integer_keys
    ):
        return False
    return bool(
        value["wasapi_first_packet_offset_frames"]
        <= value["wasapi_gap_frames"]
        <= expected_duration_ms * 48
        and value["wasapi_tail_padded_frames"] <= expected_duration_ms * 48
        and value["wasapi_first_packet_qpc_offset_100ns"]
        <= MAX_WASAPI_START_OFFSET_100NS
        and 0 < value["wasapi_qpc_span_100ns"]
        <= expected_duration_ms * 10_000 + 2_500_000
        and value["wasapi_max_qpc_drift_100ns"]
        <= MAX_WASAPI_QPC_DRIFT_100NS
        and value["wasapi_start_call_duration_100ns"]
        <= MAX_WASAPI_START_OFFSET_100NS
        and abs(
            value["master_video_frames"]
            - _expected_video_frames(expected_duration_ms)
        )
        <= MAX_VIDEO_BOUNDARY_ERROR_FRAMES
        and value["master_audio_samples"]
        == expected_duration_ms * SAMPLE_RATE // 1000
    )


def _synchronization_matches_final_probe(
    value: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    expected_duration_ms: int,
) -> bool:
    expected = _final_mp4_timing(
        probe, expected_duration_ms=expected_duration_ms
    )
    return all(value.get(key) == item for key, item in expected.items())


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    request_digest: str,
    tool_identity_digest: str,
    audit: Mapping[str, Any],
    display_width: int,
    display_height: int,
    duration_ms: int,
    synchronization: Mapping[str, Any],
    probes: Mapping[str, Mapping[str, Any]],
    directory: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _ARTIFACT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = directory / spec["filename"]
        stat = path.stat()
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    body: dict[str, Any] = {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "capture_key": capture_key,
        "request_digest": request_digest,
        "tool_identity_digest": tool_identity_digest,
        "provider": WINDOWS_CAPTURE_PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": WINDOWS_CAPTURE_TIMING_SOURCE,
        "public_release_ready": False,
        "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        "requested_duration_ms": audit["duration_ms"],
        "duration_ms": duration_ms,
        "synchronization": dict(synchronization),
        "capture": dict(audit),
        "display": {
            "target": "primary_display",
            "physical_width": display_width,
            "physical_height": display_height,
        },
        "output_policy": _output_policy(),
        "network_policy": "offline-local-tools-only",
        "media": {key: dict(value) for key, value in probes.items()},
        "files": files,
    }
    body["manifest_sha256"] = _manifest_digest(body)
    return body


def _result(
    *,
    capture_key: str,
    tool_identity_digest: str,
    duration_ms: int,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "capture_key": capture_key,
        "tool_identity_digest": tool_identity_digest,
        "cache_hit": False,
        "provider": WINDOWS_CAPTURE_PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": WINDOWS_CAPTURE_TIMING_SOURCE,
        "target": "primary_display",
        "audio_mode": "default_render_loopback",
        "actual_capture_performed": True,
        "structural_timing_verified": True,
        "content_sync_verified": False,
        "live_validation_required": True,
        "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
        "public_release_ready": False,
        "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    }


def _validate_capture(
    workspace: Path,
    directory: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
    expected_tool_identity_digest: str,
    display_width: int,
    display_height: int,
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _cancel(cancel_event)
    if not directory.is_dir() or directory.is_symlink():
        return None
    normalized = validate_windows_capture_payload(dict(payload))
    request_digest = windows_capture_request_digest(
        normalized, tool_identity_digest=expected_tool_identity_digest
    )
    audit = windows_capture_audit_payload(
        normalized,
        capture_key=capture_key,
        request_digest=request_digest,
        tool_identity_digest=expected_tool_identity_digest,
    )
    manifest = _read_manifest(directory / "manifest.json")
    if manifest is None:
        return None
    if (
        manifest.get("schema_version") != WINDOWS_CAPTURE_SCHEMA_VERSION
        or manifest.get("implementation_version")
        != WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("capture_key") != capture_key
        or manifest.get("request_digest") != request_digest
        or manifest.get("tool_identity_digest") != expected_tool_identity_digest
        or manifest.get("provider") != WINDOWS_CAPTURE_PROVIDER
        or manifest.get("provider_task_id") is not None
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != WINDOWS_CAPTURE_TIMING_SOURCE
        or manifest.get("public_release_ready") is not False
        or manifest.get("public_release_gate")
        != WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE
        or not _synchronization_record_is_valid(
            manifest.get("synchronization"),
            expected_duration_ms=normalized["duration_ms"],
        )
        or manifest.get("requested_duration_ms") != normalized["duration_ms"]
        or manifest.get("capture") != audit
        or manifest.get("display")
        != {
            "target": "primary_display",
            "physical_width": display_width,
            "physical_height": display_height,
        }
        or manifest.get("output_policy") != _output_policy()
        or manifest.get("network_policy") != "offline-local-tools-only"
    ):
        return None
    expected_names = {spec["filename"] for spec in _ARTIFACT_SPECS}
    try:
        if {child.name for child in directory.iterdir()} != expected_names:
            return None
    except OSError:
        return None
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != expected_names - {"manifest.json"}:
        return None
    try:
        for spec in _ARTIFACT_SPECS:
            path = directory / spec["filename"]
            if path.is_symlink() or not path.is_file():
                return None
            size = path.stat().st_size
            if size <= 0 or size > _MAXIMUM_BYTES[spec["filename"]]:
                return None
            if spec["filename"] == "manifest.json":
                continue
            entry = files.get(spec["filename"])
            if (
                not isinstance(entry, dict)
                or entry.get("path") != spec["filename"]
                or entry.get("kind") != spec["kind"]
                or entry.get("mime") != spec["mime"]
                or entry.get("bytes") != size
                or entry.get("sha256") != _sha256_file(path)
            ):
                return None
        _validate_png(directory / "first-frame.png")
        _validate_png(directory / "last-frame.png")
        report = _read_json(directory / "capture-report.json")
        probe_document = _read_json(directory / "ffprobe.json")
        if report is None or probe_document is None:
            return None
        probes = {
            "screen_capture": _capture_json_probe(
                ffprobe,
                Path("screen-capture.mp4"),
                cwd=directory,
                cancel_event=cancel_event,
            ),
            "screen_video": _capture_json_probe(
                ffprobe,
                Path("screen-video.mp4"),
                cwd=directory,
                cancel_event=cancel_event,
            ),
            "system_audio": _capture_json_probe(
                ffprobe,
                Path("system-audio.wav"),
                cwd=directory,
                cancel_event=cancel_event,
            ),
        }
        duration_ms = _validate_probe_set(
            screen_capture=probes["screen_capture"],
            screen_video=probes["screen_video"],
            system_audio=probes["system_audio"],
            expected_duration_ms=normalized["duration_ms"],
        )
        manifest_synchronization = manifest.get("synchronization")
        if not isinstance(
            manifest_synchronization, dict
        ) or not _synchronization_matches_final_probe(
            manifest_synchronization,
            probes["screen_capture"],
            expected_duration_ms=normalized["duration_ms"],
        ):
            return None
    except JobCancelled:
        raise
    except (AssemblyError, WindowsCaptureError, OSError, ValueError, TypeError):
        return None
    audio_capture = report.get("audio_capture")
    synchronization = report.get("synchronization")
    fixed_audio_format = {
        "encoding": "s16le",
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "bits_per_sample": 16,
        "bytes_per_frame": BYTES_PER_FRAME,
    }
    audio_counter_keys = (
        "padded_frames",
        "silent_frames",
        "discontinuity_count",
        "timestamp_error_count",
    )
    expected_frames = normalized["duration_ms"] * 48
    if (
        not isinstance(audio_capture, dict)
        or set(audio_capture)
        != {
            "format",
            "recording_started",
            "frames_written",
            "bytes_written",
            *audio_counter_keys,
        }
        or audio_capture.get("format") != fixed_audio_format
        or audio_capture.get("recording_started") is not True
        or audio_capture.get("frames_written") != expected_frames
        or audio_capture.get("bytes_written") != expected_frames * BYTES_PER_FRAME
        or any(
            isinstance(audio_capture.get(key), bool)
            or not isinstance(audio_capture.get(key), int)
            or audio_capture.get(key) < 0
            for key in audio_counter_keys
        )
        or audio_capture.get("padded_frames") > expected_frames
        or audio_capture.get("silent_frames") > expected_frames
        or audio_capture.get("discontinuity_count")
        > MAX_WASAPI_INITIAL_DISCONTINUITIES
        or audio_capture.get("timestamp_error_count") != 0
        or not _synchronization_record_is_valid(
            synchronization, expected_duration_ms=normalized["duration_ms"]
        )
    ):
        return None
    expected_report = {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "provider": WINDOWS_CAPTURE_PROVIDER,
        "capture": audit,
        "actual_capture_performed": True,
        "public_release_ready": False,
        "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        "external_network_used": False,
        "microphone_captured": False,
        "display": {
            "target": "primary_display",
            "physical_width": display_width,
            "physical_height": display_height,
        },
        "audio_capture": audio_capture,
        "synchronization": synchronization,
    }
    expected_probe_document = {
        "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
        "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
        "timing_source": WINDOWS_CAPTURE_TIMING_SOURCE,
        **probes,
    }
    if (
        report != expected_report
        or probe_document != expected_probe_document
        or manifest.get("media") != probes
        or manifest.get("synchronization") != synchronization
        or manifest.get("duration_ms") != duration_ms
    ):
        return None
    try:
        artifacts = [
            _artifact_record(workspace, directory, spec) for spec in _ARTIFACT_SPECS
        ]
    except (OSError, ValueError):
        return None
    return manifest, artifacts


def _run_media_command(
    arguments: Sequence[str],
    *,
    cwd: Path,
    label: str,
    cancel_event: Any | None,
) -> None:
    try:
        return_code, output, diagnostics = _run_contained_process(
            list(arguments),
            cwd=cwd,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            label=label,
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
    except JobCancelled:
        raise
    except AssemblyError as exc:
        raise WindowsCaptureToolError(
            "The local Windows capture media conversion failed.",
            code="windows_capture_failed",
        ) from exc
    if return_code != 0 or output or diagnostics:
        raise WindowsCaptureToolError(
            "The local media tool returned unexpected output.",
            code="windows_capture_failed",
        )


def _generate_or_validate(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
    expected_tool_identity_digest: str,
    dotnet: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
    progress_callback: ProgressCallback | None,
    generate: bool,
) -> dict[str, Any]:
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    workspace = Path(workspace).resolve(strict=True)
    normalized = validate_windows_capture_payload(dict(payload))
    if generate:
        _assert_no_windows_capture_privacy_residual(workspace)
    _report_progress(progress_callback, 2, "preflight")
    (
        dotnet_executable,
        ffmpeg_executable,
        ffprobe_executable,
        helper,
        display_width,
        display_height,
    ) = _resolve_tools(
        workspace,
        expected_tool_identity_digest=expected_tool_identity_digest,
        dotnet=dotnet,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    request_digest = windows_capture_request_digest(
        normalized, tool_identity_digest=expected_tool_identity_digest
    )
    audit = windows_capture_audit_payload(
        normalized,
        capture_key=capture_key,
        request_digest=request_digest,
        tool_identity_digest=expected_tool_identity_digest,
    )
    capture_directory = _safe_capture_root(workspace, run_id, capture_key)
    existing = _validate_capture(
        workspace,
        capture_directory,
        production_id=production_id,
        run_id=run_id,
        capture_key=capture_key,
        payload=normalized,
        expected_tool_identity_digest=expected_tool_identity_digest,
        display_width=display_width,
        display_height=display_height,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    if existing is not None:
        if generate:
            # Native capture requests are nonce-derived and never reuse a
            # successful recording as a cache hit.
            raise WindowsCaptureError(
                "Windows capture destination already exists.", code="publish_failed"
            )
        manifest, artifacts = existing
        return _result(
            capture_key=capture_key,
            tool_identity_digest=expected_tool_identity_digest,
            duration_ms=manifest["duration_ms"],
            artifacts=artifacts,
        )
    if not generate:
        raise WindowsCaptureError(
            "Windows capture output failed integrity verification.",
            code="cache_integrity_failed",
        )
    if capture_directory.exists():
        raise WindowsCaptureError(
            "Windows capture destination already exists.", code="publish_failed"
        )

    parent = capture_directory.parent
    temporary_root = parent / f".{capture_key}.partial"
    if temporary_root.exists() or temporary_root.is_symlink():
        raise WindowsCaptureError(
            "Private Windows capture staging data requires cleanup before recording.",
            code="windows_capture_cleanup_required",
        )
    temporary_root.mkdir()
    work_directory = temporary_root / "work"
    publish_directory = temporary_root / "publish"
    work_directory.mkdir()
    publish_directory.mkdir()
    master = work_directory / "capture-master.mkv"
    published = False
    cleanup_failure: WindowsCaptureError | None = None
    try:
        _report_progress(progress_callback, 12, "recording")
        helper_events = _capture_to_master(
            dotnet=dotnet_executable,
            helper=helper,
            ffmpeg=ffmpeg_executable,
            duration_ms=normalized["duration_ms"],
            display_width=display_width,
            display_height=display_height,
            output=master,
            cwd=work_directory,
            cancel_event=cancel_event,
        )
        if (
            not master.is_file()
            or master.is_symlink()
            or master.stat().st_size <= 0
            or master.stat().st_size > MAX_VIDEO_BYTES + MAX_AUDIO_BYTES
        ):
            raise WindowsCaptureToolError(
                "The Windows capture produced invalid temporary media.",
                code="invalid_output_media",
            )
        completed_event = helper_events[-1]
        master_timing_probe = _capture_timing_probe(
            ffprobe_executable,
            master,
            cwd=work_directory,
            cancel_event=cancel_event,
        )
        synchronization = _validate_master_synchronization(
            master_timing_probe,
            completed_event=completed_event,
            expected_duration_ms=normalized["duration_ms"],
        )
        _cancel(cancel_event)
        _report_progress(progress_callback, 58, "transcoding")
        video_partial = publish_directory / "screen-video.mp4.partial"
        _run_media_command(
            [
                ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(master),
                "-map",
                "0:v:0",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-an",
                "-sn",
                "-dn",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                str(video_partial),
            ],
            cwd=work_directory,
            label="Windows capture video extraction",
            cancel_event=cancel_event,
        )
        os.replace(video_partial, publish_directory / "screen-video.mp4")
        audio_partial = publish_directory / "system-audio.wav.partial"
        _run_media_command(
            [
                ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(master),
                "-map",
                "0:a:0",
                "-map_metadata",
                "-1",
                "-vn",
                "-sn",
                "-dn",
                "-c:a",
                "pcm_s16le",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                str(CHANNELS),
                "-f",
                "wav",
                str(audio_partial),
            ],
            cwd=work_directory,
            label="Windows capture audio extraction",
            cancel_event=cancel_event,
        )
        os.replace(audio_partial, publish_directory / "system-audio.wav")
        capture_partial = publish_directory / "screen-capture.mp4.partial"
        _run_media_command(
            [
                ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(master),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-sn",
                "-dn",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                str(CHANNELS),
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                str(capture_partial),
            ],
            cwd=work_directory,
            label="Windows capture mux",
            cancel_event=cancel_event,
        )
        os.replace(capture_partial, publish_directory / "screen-capture.mp4")
        for filename, seek_arguments in (
            ("first-frame.png", []),
            ("last-frame.png", ["-sseof", "-0.050"]),
        ):
            partial = publish_directory / f"{filename}.partial"
            _run_media_command(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    *seek_arguments,
                    "-i",
                    str(publish_directory / "screen-video.mp4"),
                    "-map",
                    "0:v:0",
                    "-c:v",
                    "png",
                    "-frames:v",
                    "1",
                    "-f",
                    "image2",
                    str(partial),
                ],
                cwd=work_directory,
                label=f"Windows capture {filename}",
                cancel_event=cancel_event,
            )
            os.replace(partial, publish_directory / filename)
        _report_progress(progress_callback, 76, "verification")
        _run_media_command(
            [
                ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(publish_directory / "screen-capture.mp4"),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            cwd=work_directory,
            label="Windows capture full decode",
            cancel_event=cancel_event,
        )
        probes = {
            "screen_capture": _capture_json_probe(
                ffprobe_executable,
                publish_directory / "screen-capture.mp4",
                cwd=work_directory,
                cancel_event=cancel_event,
            ),
            "screen_video": _capture_json_probe(
                ffprobe_executable,
                publish_directory / "screen-video.mp4",
                cwd=work_directory,
                cancel_event=cancel_event,
            ),
            "system_audio": _capture_json_probe(
                ffprobe_executable,
                publish_directory / "system-audio.wav",
                cwd=work_directory,
                cancel_event=cancel_event,
            ),
        }
        duration_ms = _validate_probe_set(
            screen_capture=probes["screen_capture"],
            screen_video=probes["screen_video"],
            system_audio=probes["system_audio"],
            expected_duration_ms=normalized["duration_ms"],
        )
        synchronization = _complete_synchronization_record(
            synchronization,
            probes["screen_capture"],
            expected_duration_ms=normalized["duration_ms"],
        )
        _validate_png(publish_directory / "first-frame.png")
        _validate_png(publish_directory / "last-frame.png")
        report = {
            "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
            "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
            "provider": WINDOWS_CAPTURE_PROVIDER,
            "capture": audit,
            "actual_capture_performed": True,
            "public_release_ready": False,
            "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
            "external_network_used": False,
            "microphone_captured": False,
            "display": {
                "target": "primary_display",
                "physical_width": display_width,
                "physical_height": display_height,
            },
            "audio_capture": {
                "format": {
                    "encoding": "s16le",
                    "sample_rate": SAMPLE_RATE,
                    "channels": CHANNELS,
                    "bits_per_sample": 16,
                    "bytes_per_frame": BYTES_PER_FRAME,
                },
                "recording_started": True,
                "frames_written": completed_event["framesWritten"],
                "bytes_written": completed_event["bytesWritten"],
                "padded_frames": completed_event["paddedFrames"],
                "silent_frames": completed_event["silentFrames"],
                "discontinuity_count": completed_event["discontinuityCount"],
                "timestamp_error_count": completed_event["timestampErrorCount"],
            },
            "synchronization": synchronization,
        }
        if completed_event["framesWritten"] != normalized["duration_ms"] * 48:
            raise WindowsCaptureToolError(
                "The Windows audio helper sample count changed.",
                code="invalid_worker_result",
            )
        _write_json(publish_directory / "capture-report.json", report)
        _write_json(
            publish_directory / "ffprobe.json",
            {
                "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
                "implementation_version": WINDOWS_CAPTURE_REQUEST_IMPLEMENTATION_VERSION,
                "timing_source": WINDOWS_CAPTURE_TIMING_SOURCE,
                **probes,
            },
        )
        manifest = _build_manifest(
            production_id=production_id,
            run_id=run_id,
            capture_key=capture_key,
            request_digest=request_digest,
            tool_identity_digest=expected_tool_identity_digest,
            audit=audit,
            display_width=display_width,
            display_height=display_height,
            duration_ms=duration_ms,
            synchronization=synchronization,
            probes=probes,
            directory=publish_directory,
        )
        _write_json(publish_directory / "manifest.json", manifest)
        _cancel(cancel_event)
        _report_progress(progress_callback, 90, "publishing")
        os.replace(publish_directory, capture_directory)
        published = True
    except JobCancelled:
        raise
    except WindowsCaptureError:
        raise
    except (AssemblyError, OSError, ValueError, TypeError) as exc:
        raise WindowsCaptureToolError(
            "The Windows capture could not be published.", code="publish_failed"
        ) from exc
    finally:
        try:
            _remove_private_capture_directory(temporary_root)
        except WindowsCaptureError as exc:
            _persist_cleanup_residual(
                workspace,
                run_id=run_id,
                capture_key=capture_key,
                target_kind="partial",
                stage_directory=temporary_root.parent,
            )
            if not published:
                raise
            cleanup_failure = exc

    if cleanup_failure is not None:
        if published:
            try:
                discard_windows_capture_outputs(
                    workspace, run_id=run_id, capture_key=capture_key
                )
            except WindowsCaptureError:
                # Preserve the first privacy-cleanup failure. Startup cleanup
                # will retry the exact deterministic capture directory.
                pass
        raise cleanup_failure

    try:
        validated = _validate_capture(
            workspace,
            capture_directory,
            production_id=production_id,
            run_id=run_id,
            capture_key=capture_key,
            payload=normalized,
            expected_tool_identity_digest=expected_tool_identity_digest,
            display_width=display_width,
            display_height=display_height,
            ffprobe=ffprobe_executable,
            cancel_event=cancel_event,
        )
        _cancel(cancel_event)
    except BaseException:
        if published:
            discard_windows_capture_outputs(
                workspace, run_id=run_id, capture_key=capture_key
            )
        raise
    if validated is None:
        if published:
            discard_windows_capture_outputs(
                workspace, run_id=run_id, capture_key=capture_key
            )
        raise WindowsCaptureError(
            "Published Windows capture failed integrity verification.",
            code="integrity_verification_failed",
        )
    manifest, artifacts = validated
    _report_progress(progress_callback, 96, "registration")
    return _result(
        capture_key=capture_key,
        tool_identity_digest=expected_tool_identity_digest,
        duration_ms=manifest["duration_ms"],
        artifacts=artifacts,
    )


def generate_windows_capture(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
    expected_tool_identity_digest: str,
    dotnet: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        capture_key=capture_key,
        payload=payload,
        expected_tool_identity_digest=expected_tool_identity_digest,
        dotnet=dotnet,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=True,
    )


def validate_windows_capture_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
    expected_tool_identity_digest: str,
    dotnet: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        capture_key=capture_key,
        payload=payload,
        expected_tool_identity_digest=expected_tool_identity_digest,
        dotnet=dotnet,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=False,
    )


def discard_windows_capture_outputs(
    workspace: Path, *, run_id: str, capture_key: str
) -> None:
    """Idempotently remove one exact output, or raise a fixed cleanup error."""

    validate_identifier(run_id, label="run id")
    if not isinstance(capture_key, str) or _SHA256_RE.fullmatch(capture_key) is None:
        raise WindowsCaptureValidationError(
            "capture_key is invalid", code="invalid_cache_key"
        )
    root = Path(workspace).resolve(strict=True)
    stage = (
        root
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "screen_capture"
    )
    safe_stage: Path | None = None
    try:
        candidate = stage / capture_key
        if _has_symlink_component(root, stage) or _has_symlink_component(
            root, candidate
        ):
            raise WindowsCaptureError(
                "Windows capture cleanup path is unsafe.",
                code="windows_capture_cleanup_failed",
            )
        safe_stage = workspace_path(root, stage, must_exist=False)
        target = workspace_path(root, candidate, must_exist=False)
        if safe_stage.exists() and (
            _is_link_like(safe_stage) or not safe_stage.is_dir()
        ):
            raise WindowsCaptureError(
                "Windows capture cleanup path is unsafe.",
                code="windows_capture_cleanup_failed",
            )
        _remove_published_capture_directory(target)
    except WindowsCaptureError:
        _persist_cleanup_residual(
            root,
            run_id=run_id,
            capture_key=capture_key,
            target_kind="published",
            stage_directory=safe_stage or stage,
        )
        raise
    except (OSError, ValueError) as exc:
        _persist_cleanup_residual(
            root,
            run_id=run_id,
            capture_key=capture_key,
            target_kind="published",
            stage_directory=safe_stage or stage,
        )
        raise WindowsCaptureError(
            "Published Windows capture data could not be removed.",
            code="windows_capture_cleanup_failed",
        ) from exc


__all__ = [
    "discard_windows_capture_outputs",
    "generate_windows_capture",
    "validate_windows_capture_outputs",
]
