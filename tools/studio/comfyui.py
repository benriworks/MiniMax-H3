from __future__ import annotations

"""Auditable adapter for an already-running, loopback-only ComfyUI server.

The adapter never starts or stops ComfyUI.  It submits one pinned MiniMax H3
API workflow, polls the matching history entry, verifies the returned MP4
inside an allowlisted workspace output root, and atomically publishes a copy
under ``outputs/studio``.  A durable production/cache marker prevents an
ambiguous POST, timeout, cancellation, or crash from becoming a duplicate
GPU submission.
"""

import copy
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import comfyui_execution as _execution
from .assembly import AssemblyError, _bounded_process, _tool_identity
from .comfyui_execution import (
    COMFYUI_IMPLEMENTATION_VERSION,
    COMFYUI_PROVIDER,
    COMFYUI_SCHEMA_VERSION,
    COMFYUI_TIMING_SOURCE,
    COMFYUI_WORKFLOW_FILE_BYTES,
    COMFYUI_WORKFLOW_FILE_SHA256,
    COMFYUI_WORKFLOW_GRAPH_SHA256,
    COMFYUI_WORKFLOW_PRESET,
    COMFYUI_WORKFLOW_RELATIVE_PATH,
    OUTPUT_POLICY,
    RUNTIME_FILE_SPECS,
    RUNTIME_REPOSITORY_SPECS,
    ComfyUIError,
    ComfyUIMediaError,
    ComfyUIProviderError,
    ComfyUISubmissionUnknown,
    ComfyUIValidationError,
    comfyui_cache_key,
    comfyui_payload_digest,
    normalize_model_records,
    normalize_runtime_identity,
    normalize_tool_identity,
    normalize_workflow_record,
    validate_comfyui_payload,
)
from .jobs import JobCancelled
from .security import SecurityError, canonical_json, validate_identifier, workspace_path


DEFAULT_BASE_URL = "http://127.0.0.1:8188"
PROMPT_ENDPOINT = "/prompt"
HISTORY_ENDPOINT = "/history/{prompt_id}"
QUEUE_ENDPOINT = "/queue"
SYSTEM_STATS_ENDPOINT = "/system_stats"
SUBMISSION_MARKER_FILENAME = ".submission-unknown.json"

REQUEST_TIMEOUT_SECONDS = 30.0
GENERATION_TIMEOUT_SECONDS = 6 * 60 * 60.0
POLL_INTERVAL_SECONDS = 2.0
MAX_HTTP_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_QUEUE_RESPONSE_BYTES = 64 * 1024
MAX_SYSTEM_STATS_RESPONSE_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 512 * 1024
MAX_WORKFLOW_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
MAX_MODEL_HASH_CACHE_ENTRIES = 32

# Non-Windows Studio processes verify each pinned model before their first new
# POST and use a stat-keyed cache to avoid re-reading roughly 40 GB for every
# subsequent job.  Windows intentionally never reads or writes this cache:
# NT creation/change metadata can be restored or remain unchanged after an
# in-place rewrite, so every new POST hashes four share-deny read handles.
_MODEL_HASH_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class _PhysicalFileIdentity:
    source: str
    size: int
    modified_time: int
    change_time: int
    volume_id: int
    file_id: int | bytes


class _WinFileBasicInfo(ctypes.Structure):
    _fields_ = (
        ("CreationTime", ctypes.c_int64),
        ("LastAccessTime", ctypes.c_int64),
        ("LastWriteTime", ctypes.c_int64),
        ("ChangeTime", ctypes.c_int64),
        ("FileAttributes", ctypes.c_uint32),
    )


class _WinFileId128(ctypes.Structure):
    _fields_ = (("Identifier", ctypes.c_ubyte * 16),)


class _WinFileIdInfo(ctypes.Structure):
    _fields_ = (
        ("VolumeSerialNumber", ctypes.c_uint64),
        ("FileId", _WinFileId128),
    )


@dataclass
class _WinModelGuard:
    role: str
    path: Path
    handle: int
    identity: _PhysicalFileIdentity
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        _close_win32_handle(self.handle)
        self.closed = True


class _ModelVerification:
    """Own Windows share-deny handles for one new provider submission."""

    def __init__(self) -> None:
        self.guards: dict[str, _WinModelGuard] = {}

    def close(self) -> None:
        first_error: OSError | None = None
        for guard in reversed(tuple(self.guards.values())):
            try:
                guard.close()
            except OSError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


_MODEL_HASH_CACHE: dict[tuple[str, _PhysicalFileIdentity], str] = {}

_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")
_OUTPUT_PREFIX_RE = re.compile(r"^[A-Za-z0-9_./-]{1,512}$")
_PROMPT_SENTINEL = "__STUDIO_PROMPT__"
_OUTPUT_PREFIX_SENTINEL = "__STUDIO_OUTPUT_PREFIX__"
_EXPECTED_COMFYUI_VERSION = "0.31.0"
_EXPECTED_PYTORCH_VERSION = "2.13.0+cu130"
_EXPECTED_PYTHON_PREFIX = "3.12"
_EXPECTED_CUSTOM_NODE_WHITELIST = ("ComfyUI-GGUF",)
_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "generated-video.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "workflow.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)


class _RedirectRejected(Exception):
    pass


class _HTTPStatusError(Exception):
    def __init__(self, status: int):
        super().__init__(str(status))
        self.status = status


class _HTTPTransportError(Exception):
    pass


class _HTTPResponseError(Exception):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        # Returning None makes urllib surface an HTTPError without following
        # the redirect.  _http_request closes that response before mapping it
        # to the adapter's safe redirect error.
        return None


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    method = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(method):
        method()
        return
    is_set = getattr(cancel_event, "is_set", None)
    if callable(is_set) and is_set():
        raise ComfyUIError("The ComfyUI job was cancelled.", code="process_interrupted")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path, *, cancel_event: Any | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            _raise_if_cancelled(cancel_event)
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    _raise_if_cancelled(cancel_event)
    return digest.hexdigest().upper()


def _win32_kernel32() -> tuple[Any, Callable[[], int]]:
    win_dll = getattr(ctypes, "WinDLL", None)
    get_last_error = getattr(ctypes, "get_last_error", None)
    if win_dll is None or get_last_error is None:
        raise OSError("Win32 file APIs are unavailable")
    kernel32 = win_dll("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    get_information.restype = ctypes.c_int
    get_size = kernel32.GetFileSizeEx
    get_size.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))
    get_size.restype = ctypes.c_int
    read_file = kernel32.ReadFile
    read_file.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    )
    read_file.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    return kernel32, get_last_error


def _query_win32_handle_identity(handle: int) -> _PhysicalFileIdentity:
    kernel32, get_last_error = _win32_kernel32()
    basic = _WinFileBasicInfo()
    file_id = _WinFileIdInfo()
    size = ctypes.c_int64()
    if not kernel32.GetFileInformationByHandleEx(
        handle, 0, ctypes.byref(basic), ctypes.sizeof(basic)
    ):
        error = int(get_last_error())
        raise OSError(error, "FileBasicInfo query failed")
    if not kernel32.GetFileInformationByHandleEx(
        handle, 18, ctypes.byref(file_id), ctypes.sizeof(file_id)
    ):
        error = int(get_last_error())
        raise OSError(error, "FileIdInfo query failed")
    if not kernel32.GetFileSizeEx(handle, ctypes.byref(size)):
        error = int(get_last_error())
        raise OSError(error, "GetFileSizeEx failed")
    if size.value <= 0:
        raise OSError("Win32 model file size is invalid")
    return _PhysicalFileIdentity(
        source="win32",
        size=int(size.value),
        modified_time=int(basic.LastWriteTime),
        change_time=int(basic.ChangeTime),
        volume_id=int(file_id.VolumeSerialNumber),
        file_id=bytes(file_id.FileId.Identifier),
    )


def _close_win32_handle(handle: int) -> None:
    kernel32, get_last_error = _win32_kernel32()
    if not kernel32.CloseHandle(handle):
        error = int(get_last_error())
        raise OSError(error, "CloseHandle failed for model guard")


def _open_win32_handle(path: Path, *, guarded_read: bool) -> int:
    kernel32, get_last_error = _win32_kernel32()
    desired_access = 0x80000000 if guarded_read else 0x0080  # GENERIC_READ / attributes
    share_mode = 0x0001 if guarded_read else 0x0001 | 0x0002 | 0x0004
    flags = 0x0080 | (0x08000000 if guarded_read else 0)
    handle = kernel32.CreateFileW(
        str(path),
        desired_access,
        share_mode,
        None,
        3,  # OPEN_EXISTING
        flags,  # FILE_ATTRIBUTE_NORMAL | optional FILE_FLAG_SEQUENTIAL_SCAN
        None,
    )
    if handle in {None, ctypes.c_void_p(-1).value}:
        error = int(get_last_error())
        raise OSError(error, "CreateFileW failed for model file")
    return int(handle)


def _win32_file_identity(path: Path) -> _PhysicalFileIdentity:
    """Query one physical identity through a short-lived metadata handle."""

    handle = _open_win32_handle(path, guarded_read=False)
    try:
        return _query_win32_handle_identity(handle)
    finally:
        _close_win32_handle(handle)


def _open_win32_model_guard(role: str, path: Path) -> _WinModelGuard:
    """Open one immutable-for-this-job model read handle on Windows."""

    handle = _open_win32_handle(path, guarded_read=True)
    try:
        identity = _query_win32_handle_identity(handle)
    except BaseException:
        _close_win32_handle(handle)
        raise
    return _WinModelGuard(role=role, path=path, handle=handle, identity=identity)


def _sha256_win32_model_guard(
    guard: _WinModelGuard, *, cancel_event: Any | None
) -> str:
    """Hash the exact guarded handle rather than reopening its pathname."""

    if guard.closed:
        raise OSError("model guard is closed")
    kernel32, get_last_error = _win32_kernel32()
    digest = hashlib.sha256()
    buffer = ctypes.create_string_buffer(HASH_CHUNK_BYTES)
    read = ctypes.c_uint32()
    total = 0
    while True:
        _raise_if_cancelled(cancel_event)
        if not kernel32.ReadFile(
            guard.handle,
            buffer,
            HASH_CHUNK_BYTES,
            ctypes.byref(read),
            None,
        ):
            error = int(get_last_error())
            raise OSError(error, "ReadFile failed for model guard")
        count = int(read.value)
        if count == 0:
            break
        digest.update(buffer.raw[:count])
        total += count
    _raise_if_cancelled(cancel_event)
    if total != guard.identity.size:
        raise OSError("model size changed while guarded")
    return digest.hexdigest().upper()


def _physical_file_identity(path: Path) -> _PhysicalFileIdentity:
    """Return one platform-correct, stable physical file identity."""

    if os.name == "nt":
        return _win32_file_identity(path)
    value = path.stat()
    return _PhysicalFileIdentity(
        source="stat",
        size=int(value.st_size),
        modified_time=int(value.st_mtime_ns),
        change_time=int(value.st_ctime_ns),
        volume_id=int(value.st_dev),
        file_id=int(value.st_ino),
    )


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _strict_cache_key(value: Any) -> str:
    if not isinstance(value, str) or not _CACHE_KEY_RE.fullmatch(value.upper()):
        raise ComfyUIValidationError("cache_key is invalid")
    return value.upper()


def _strict_prompt_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ComfyUIProviderError(
            "ComfyUI returned invalid task metadata.", code="invalid_comfyui_response"
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ComfyUIProviderError(
            "ComfyUI returned invalid task metadata.", code="invalid_comfyui_response"
        ) from exc
    canonical = str(parsed)
    if value.casefold() != canonical:
        raise ComfyUIProviderError(
            "ComfyUI returned invalid task metadata.", code="invalid_comfyui_response"
        )
    return canonical


def _has_symlink_component(workspace: Path, candidate: str | Path) -> bool:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    lexical = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return True
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _ensure_safe_directory(workspace: Path, relative: Path) -> Path:
    root = workspace.resolve(strict=True)
    if relative.is_absolute() or ".." in relative.parts:
        raise ComfyUIError("The ComfyUI output path is unsafe.", code="unsafe_output_path")
    cursor = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink() or not cursor.is_dir():
                raise ComfyUIError(
                    "The ComfyUI output path is unsafe.", code="unsafe_output_path"
                )
        else:
            try:
                cursor.mkdir()
            except FileExistsError:
                if cursor.is_symlink() or not cursor.is_dir():
                    raise ComfyUIError(
                        "The ComfyUI output path is unsafe.", code="unsafe_output_path"
                    )
    return cursor


def _safe_exact_file(
    workspace: Path,
    candidate: str | Path,
    *,
    expected_relative: str,
    label: str,
    expected_bytes: int | None = None,
) -> Path:
    root = workspace.resolve(strict=True)
    expected_lexical = root / Path(expected_relative)
    if _has_symlink_component(root, expected_lexical) or _has_symlink_component(root, candidate):
        raise ComfyUIValidationError(f"{label} must not contain symlinks")
    try:
        expected = workspace_path(root, expected_lexical, must_exist=True)
        actual = workspace_path(root, candidate, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise ComfyUIValidationError(f"{label} is unavailable") from exc
    if actual != expected or actual.is_symlink() or not actual.is_file():
        raise ComfyUIValidationError(f"{label} is not the allowlisted file")
    try:
        size = actual.stat().st_size
    except OSError as exc:
        raise ComfyUIValidationError(f"{label} is unavailable") from exc
    if size <= 0 or (expected_bytes is not None and size != expected_bytes):
        raise ComfyUIValidationError(f"{label} size is invalid")
    return actual


def _workflow_record(
    workspace: Path,
    workflow: Mapping[str, Any],
    *,
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(workflow, Mapping):
        raise ComfyUIValidationError("workflow must be an object")
    source = _safe_exact_file(
        workspace,
        workflow_source_path,
        expected_relative=COMFYUI_WORKFLOW_RELATIVE_PATH,
        expected_bytes=COMFYUI_WORKFLOW_FILE_BYTES,
        label="workflow source",
    )
    if source.stat().st_size > MAX_WORKFLOW_BYTES:
        raise ComfyUIValidationError("workflow source is too large")
    try:
        raw = source.read_bytes()
        parsed = json.loads(raw.decode("utf-8"))
        supplied = json.loads(canonical_json(workflow))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ComfyUIValidationError("workflow source is invalid") from exc
    _raise_if_cancelled(cancel_event)
    file_digest = _sha256_bytes(raw)
    graph_digest = _sha256_bytes(canonical_json(parsed).encode("utf-8"))
    if (
        workflow_source_bytes != len(raw)
        or not isinstance(workflow_source_bytes, int)
        or isinstance(workflow_source_bytes, bool)
        or not isinstance(workflow_source_sha256, str)
        or workflow_source_sha256.upper() != file_digest
        or file_digest != COMFYUI_WORKFLOW_FILE_SHA256
        or graph_digest != COMFYUI_WORKFLOW_GRAPH_SHA256
        or supplied != parsed
    ):
        raise ComfyUIValidationError("workflow source provenance does not match")
    try:
        if (
            parsed["105:104"]["inputs"]["prompt"] != _PROMPT_SENTINEL
            or parsed["105:15"]["inputs"]["noise_seed"] != 0
            or parsed["92"]["inputs"]["filename_prefix"]
            != _OUTPUT_PREFIX_SENTINEL
        ):
            raise KeyError("sentinel")
    except (KeyError, TypeError) as exc:
        raise ComfyUIValidationError("workflow source sentinels are invalid") from exc
    relative = source.relative_to(workspace.resolve(strict=True)).as_posix()
    record = normalize_workflow_record(
        {
            "path": relative,
            "bytes": len(raw),
            "sha256": file_digest,
            "graph_sha256": graph_digest,
        }
    )
    return supplied, record


def _verified_model_records(
    workspace: Path,
    model_files: Mapping[str, Any],
    *,
    cancel_event: Any | None,
) -> dict[str, dict[str, Any]]:
    normalized = normalize_model_records(model_files)
    verified: dict[str, dict[str, Any]] = {}
    root = workspace.resolve(strict=True)
    for role, spec in _execution.MODEL_SPECS.items():
        record = normalized[role]
        path = _safe_exact_file(
            root,
            record["path"],
            expected_relative=str(spec["relative_path"]),
            expected_bytes=int(spec["bytes"]),
            label=f"model {role}",
        )
        _raise_if_cancelled(cancel_event)
        stat = path.stat()
        # The fixed SHA-256 values are supplied by the tracked model manifest
        # and validated by normalize_model_records.  Re-reading roughly 40 GB
        # for every queue operation would dominate local control-plane time;
        # verify the exact allowlisted path and byte size here, while retaining
        # the pinned digest in cache and manifest provenance.
        if stat.st_size != spec["bytes"] or record["sha256"] != spec["sha256"]:
            raise ComfyUIValidationError(f"model {role} provenance does not match")
        verified[role] = {
            "path": path.relative_to(root).as_posix(),
            "bytes": stat.st_size,
            "sha256": record["sha256"],
        }
    return normalize_model_records(verified)


def _verify_model_digests(
    workspace: Path,
    model_records: Mapping[str, Any],
    *,
    cancel_event: Any | None,
    guard_owner: list[_ModelVerification],
) -> dict[str, tuple[Path, _PhysicalFileIdentity]]:
    """Verify all four physical model digests before a new provider POST.

    Published cache validation and marker-linked resume do not execute a new
    graph, so they deliberately skip this expensive process-local preflight.
    """

    normalized = normalize_model_records(model_records)
    root = workspace.resolve(strict=True)
    snapshots: dict[str, tuple[Path, _PhysicalFileIdentity]] = {}
    verification = _ModelVerification()
    guard_owner.append(verification)

    # Snapshot every input before hashing any one of them.  On Windows, acquire
    # all four GENERIC_READ / FILE_SHARE_READ-only handles first.  This both
    # rejects an already-open writer/delete handle and prevents any new write,
    # delete, or replacement until the whole provider job has completed.
    for role, spec in _execution.MODEL_SPECS.items():
        record = normalized[role]
        path = _safe_exact_file(
            root,
            record["path"],
            expected_relative=str(spec["relative_path"]),
            expected_bytes=int(spec["bytes"]),
            label=f"model {role}",
        )
        _raise_if_cancelled(cancel_event)
        try:
            if os.name == "nt":
                guard = _open_win32_model_guard(role, path)
                verification.guards[role] = guard
                before = guard.identity
            else:
                before = _physical_file_identity(path)
        except OSError as exc:
            raise ComfyUIValidationError(
                f"model {role} is unavailable"
            ) from exc
        if before.size != spec["bytes"]:
            raise ComfyUIValidationError(f"model {role} size is invalid")
        snapshots[role] = (path, before)

    for role, spec in _execution.MODEL_SPECS.items():
        record = normalized[role]
        path, initial_identity = snapshots[role]
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            raise ComfyUIValidationError(
                f"model {role} changed during verification",
                code="input_changed",
            ) from exc
        key = (str(resolved_path), initial_identity)
        if os.name == "nt":
            try:
                digest = _sha256_win32_model_guard(
                    verification.guards[role], cancel_event=cancel_event
                )
                after = _query_win32_handle_identity(
                    verification.guards[role].handle
                )
            except OSError as exc:
                raise ComfyUIValidationError(
                    f"model {role} changed during verification",
                    code="input_changed",
                ) from exc
            if after != initial_identity:
                raise ComfyUIValidationError(
                    f"model {role} changed during verification",
                    code="input_changed",
                )
        else:
            with _MODEL_HASH_CACHE_LOCK:
                cached = _MODEL_HASH_CACHE.get(key)
                if cached is not None:
                    digest = cached
                else:
                    try:
                        digest = _sha256_file(path, cancel_event=cancel_event)
                    except OSError as exc:
                        raise ComfyUIValidationError(
                            f"model {role} changed during verification",
                            code="input_changed",
                        ) from exc
                    try:
                        after = _physical_file_identity(path)
                    except OSError as exc:
                        raise ComfyUIValidationError(
                            f"model {role} changed during verification",
                            code="input_changed",
                        ) from exc
                    if after != initial_identity:
                        raise ComfyUIValidationError(
                            f"model {role} changed during verification",
                            code="input_changed",
                        )
                    # Discard stale identities for this resolved path before
                    # bounding the small process-local cache.
                    for stale in [
                        item for item in _MODEL_HASH_CACHE if item[0] == key[0]
                    ]:
                        _MODEL_HASH_CACHE.pop(stale, None)
                    while len(_MODEL_HASH_CACHE) >= MAX_MODEL_HASH_CACHE_ENTRIES:
                        _MODEL_HASH_CACHE.pop(next(iter(_MODEL_HASH_CACHE)))
                    _MODEL_HASH_CACHE[key] = digest
        if digest != record["sha256"]:
            raise ComfyUIValidationError(
                f"model {role} digest does not match pinned provenance"
            )
        try:
            current = _physical_file_identity(path)
        except OSError as exc:
            raise ComfyUIValidationError(
                f"model {role} changed during verification",
                code="input_changed",
            ) from exc
        if current != initial_identity:
            raise ComfyUIValidationError(
                f"model {role} changed during verification",
                code="input_changed",
            )
        _raise_if_cancelled(cancel_event)

    _revalidate_model_snapshots(
        root,
        normalized,
        snapshots,
        cancel_event=cancel_event,
    )
    return snapshots


def _revalidate_model_snapshots(
    workspace: Path,
    model_records: Mapping[str, Any],
    snapshots: Mapping[str, tuple[Path, _PhysicalFileIdentity]],
    *,
    cancel_event: Any | None,
) -> None:
    """Re-resolve all model identities after hashing and just before POST."""

    normalized = normalize_model_records(model_records)
    root = workspace.resolve(strict=True)
    if set(snapshots) != set(_execution.MODEL_SPECS):
        raise ComfyUIValidationError(
            "model verification snapshot is invalid",
            code="input_changed",
        )
    for role, spec in _execution.MODEL_SPECS.items():
        record = normalized[role]
        original_path, initial_identity = snapshots[role]
        try:
            current_path = _safe_exact_file(
                root,
                record["path"],
                expected_relative=str(spec["relative_path"]),
                expected_bytes=int(spec["bytes"]),
                label=f"model {role}",
            )
            current_identity = _physical_file_identity(current_path)
        except (OSError, ComfyUIValidationError) as exc:
            raise ComfyUIValidationError(
                f"model {role} changed during verification",
                code="input_changed",
            ) from exc
        if current_path != original_path or current_identity != initial_identity:
            raise ComfyUIValidationError(
                f"model {role} changed during verification",
                code="input_changed",
            )
        _raise_if_cancelled(cancel_event)


def _normalized_model_records(model_files: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize trusted records for cache lookup without reading huge models."""

    return normalize_model_records(model_files)


def prepare_comfyui_workflow(
    workflow: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    output_prefix: str,
) -> dict[str, Any]:
    """Inject exactly the three variable fields into the hash-pinned graph."""

    normalized = validate_comfyui_payload(dict(payload))
    try:
        plain = json.loads(canonical_json(workflow))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ComfyUIValidationError("workflow is invalid") from exc
    digest = _sha256_bytes(canonical_json(plain).encode("utf-8"))
    if digest != COMFYUI_WORKFLOW_GRAPH_SHA256:
        raise ComfyUIValidationError("workflow graph is not allowlisted")
    if (
        not isinstance(output_prefix, str)
        or not _OUTPUT_PREFIX_RE.fullmatch(output_prefix)
        or output_prefix.startswith(('/', '\\'))
        or ".." in output_prefix.replace("\\", "/").split("/")
    ):
        raise ComfyUIValidationError("output prefix is invalid")
    result = copy.deepcopy(plain)
    try:
        result["105:104"]["inputs"]["prompt"] = normalized["prompt"]
        result["105:15"]["inputs"]["noise_seed"] = normalized["seed"]
        result["92"]["inputs"]["filename_prefix"] = output_prefix
    except (KeyError, TypeError) as exc:  # hash validation makes this defensive
        raise ComfyUIValidationError("workflow graph is invalid") from exc
    return result


def resolve_comfyui_tool_identity(
    *,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, str]:
    """Resolve and hash the exact ffprobe executable used by this adapter."""

    try:
        return normalize_tool_identity(
            _tool_identity("ffprobe", ffprobe, cancel_event=cancel_event)
        )
    except JobCancelled:
        raise
    except (AssemblyError, ComfyUIValidationError) as exc:
        raise ComfyUIError(
            "The local ffprobe tool is unavailable.", code="local_ffprobe_unavailable"
        ) from exc


def resolve_comfyui_runtime_identity(
    workspace: Path,
    *,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Verify the two tracked locks and three runtime repository revisions."""

    root = workspace.resolve(strict=True)
    extra_model_paths = root / "runtime" / "ComfyUI" / "extra_model_paths.yaml"
    try:
        os.lstat(extra_model_paths)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ComfyUIValidationError(
            "runtime extra model paths configuration could not be verified"
        ) from exc
    else:
        # ComfyUI automatically consumes this ignored file.  Both a regular
        # file and a (possibly dangling) symlink would redirect the pinned
        # workflow away from the model paths covered by Studio provenance.
        raise ComfyUIValidationError(
            "runtime extra model paths configuration is not allowed"
        )
    file_records: dict[str, dict[str, Any]] = {}
    lock_document: dict[str, Any] | None = None
    for role, spec in RUNTIME_FILE_SPECS.items():
        path = _safe_exact_file(
            root,
            spec["relative_path"],
            expected_relative=str(spec["relative_path"]),
            expected_bytes=int(spec["bytes"]),
            label=f"runtime file {role}",
        )
        if path.stat().st_size > MAX_WORKFLOW_BYTES:
            raise ComfyUIValidationError(f"runtime file {role} is too large")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ComfyUIValidationError(
                f"runtime file {role} is unavailable"
            ) from exc
        _raise_if_cancelled(cancel_event)
        digest = _sha256_bytes(raw)
        if digest != spec["sha256"]:
            raise ComfyUIValidationError(
                f"runtime file {role} does not match the lock"
            )
        file_records[role] = {
            "path": path.relative_to(root).as_posix(),
            "bytes": len(raw),
            "sha256": digest,
        }
        if role == "runtime_lock":
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ComfyUIValidationError("runtime lock is invalid") from exc
            if not isinstance(parsed, dict):
                raise ComfyUIValidationError("runtime lock is invalid")
            lock_document = parsed

    if lock_document is None:
        raise ComfyUIValidationError("runtime lock is unavailable")
    locked_repositories = lock_document.get("repositories")
    if not isinstance(locked_repositories, dict):
        raise ComfyUIValidationError("runtime lock repositories are invalid")
    if lock_document.get("requirements_file") != RUNTIME_FILE_SPECS[
        "requirements_lock"
    ]["relative_path"]:
        raise ComfyUIValidationError("runtime requirements lock is invalid")
    for role, spec in RUNTIME_REPOSITORY_SPECS.items():
        record = locked_repositories.get(role)
        if not isinstance(record, dict) or record.get("revision") != spec["revision"]:
            raise ComfyUIValidationError(
                f"runtime lock repository {role} is invalid"
            )

    git = shutil.which("git")
    if not git:
        raise ComfyUIValidationError("git is unavailable for runtime verification")
    repositories: dict[str, dict[str, Any]] = {}
    for role, spec in RUNTIME_REPOSITORY_SPECS.items():
        lexical = root / Path(spec["relative_path"])
        if _has_symlink_component(root, lexical):
            raise ComfyUIValidationError(f"runtime repository {role} is unsafe")
        try:
            repository = workspace_path(root, lexical, must_exist=True)
        except (SecurityError, OSError, RuntimeError) as exc:
            raise ComfyUIValidationError(
                f"runtime repository {role} is unavailable"
            ) from exc
        git_metadata = repository / ".git"
        if (
            repository.is_symlink()
            or not repository.is_dir()
            or git_metadata.is_symlink()
            or not git_metadata.is_dir()
        ):
            raise ComfyUIValidationError(f"runtime repository {role} is unsafe")
        try:
            revision_raw = _bounded_process(
                [git, "-C", str(repository), "rev-parse", "--verify", "HEAD"],
                cwd=root,
                timeout=30.0,
                label="ComfyUI runtime revision",
                cancel_event=cancel_event,
            )
            status_raw = _bounded_process(
                [
                    git,
                    "-C",
                    str(repository),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=normal",
                ],
                cwd=root,
                timeout=30.0,
                label="ComfyUI runtime status",
                cancel_event=cancel_event,
            )
            revision = revision_raw.decode("ascii").strip()
        except JobCancelled:
            raise
        except (AssemblyError, UnicodeError) as exc:
            raise ComfyUIValidationError(
                f"runtime repository {role} could not be verified"
            ) from exc
        if revision != spec["revision"] or status_raw.strip():
            raise ComfyUIValidationError(
                f"runtime repository {role} does not match the lock"
            )
        repositories[role] = {
            "path": repository.relative_to(root).as_posix(),
            "revision": revision,
            "tracked_clean": True,
        }
        _raise_if_cancelled(cancel_event)

    return normalize_runtime_identity(
        {
            **file_records,
            "repositories": repositories,
        }
    )


def _normalize_base_url(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ComfyUIValidationError("ComfyUI endpoint is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ComfyUIValidationError("ComfyUI endpoint is invalid") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port is None
        or not 1 <= port <= 65535
    ):
        raise ComfyUIValidationError("ComfyUI endpoint must be loopback HTTP")
    host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    return f"http://{host}:{port}"


def _bounded_seconds(
    value: Any, *, label: str, minimum: float, maximum: float
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComfyUIValidationError(f"{label} is invalid")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ComfyUIValidationError(f"{label} is invalid")
    return result


def _open_request(request: urllib.request.Request, *, timeout: float) -> Any:
    # Explicitly suppress environment/Windows proxy discovery.  Even though
    # the endpoint contract is loopback-only, a default ProxyHandler could
    # otherwise disclose the private prompt to a configured HTTP proxy.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirectHandler()
    )
    return opener.open(request, timeout=timeout)


def _read_bounded_response(
    response: Any,
    *,
    maximum_bytes: int,
    deadline: float,
    allow_empty: bool = False,
) -> bytes:
    headers = getattr(response, "headers", None)
    content_length: Any = None
    if headers is not None:
        getter = getattr(headers, "get", None)
        if callable(getter):
            content_length = getter("Content-Length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except (TypeError, ValueError) as exc:
            raise _HTTPResponseError() from exc
        if parsed_length < 0 or parsed_length > maximum_bytes:
            raise _HTTPResponseError()
    result = bytearray()
    while True:
        if time.monotonic() >= deadline:
            raise _HTTPTransportError()
        try:
            chunk = response.read(min(64 * 1024, maximum_bytes + 1 - len(result)))
        except (TimeoutError, socket.timeout, OSError) as exc:
            raise _HTTPTransportError() from exc
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise _HTTPResponseError()
        result.extend(chunk)
        if len(result) > maximum_bytes:
            raise _HTTPResponseError()
    if not result and not allow_empty:
        raise _HTTPResponseError()
    return bytes(result)


def _http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    body: Mapping[str, Any] | None,
    timeout: float,
    maximum_bytes: int,
    allow_empty: bool = False,
    opener: Callable[..., Any] | None = None,
) -> bytes:
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ComfyUIValidationError("ComfyUI request path is invalid")
    data: bytes | None = None
    headers = {"Accept": "application/json", "Connection": "close"}
    if body is not None:
        try:
            data = (canonical_json(body) + "\n").encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ComfyUIValidationError("ComfyUI request payload is invalid") from exc
        if len(data) > MAX_REQUEST_BYTES:
            raise ComfyUIValidationError("ComfyUI request payload is too large")
        headers["Content-Type"] = "application/json"
    url = f"{base_url}{path}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    response: Any = None
    try:
        response = (opener or _open_request)(request, timeout=timeout)
        status = getattr(response, "status", None)
        if not isinstance(status, int) or status != 200:
            raise _HTTPStatusError(status if isinstance(status, int) else 0)
        final_url = getattr(response, "geturl", lambda: url)()
        if final_url != url:
            raise _RedirectRejected()
        return _read_bounded_response(
            response,
            maximum_bytes=maximum_bytes,
            deadline=time.monotonic() + timeout,
            allow_empty=allow_empty,
        )
    except _RedirectRejected:
        raise
    except _HTTPStatusError:
        raise
    except urllib.error.HTTPError as exc:
        try:
            if exc.code in {301, 302, 303, 307, 308}:
                raise _RedirectRejected() from exc
            raise _HTTPStatusError(int(exc.code)) from exc
        finally:
            try:
                exc.close()
            except Exception:
                pass
    except (_HTTPResponseError, _HTTPTransportError):
        raise
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
        raise _HTTPTransportError() from exc
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


def _json_response(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _HTTPResponseError() from exc
    if not isinstance(value, dict):
        raise _HTTPResponseError()
    return value


def _strict_studio_runtime_argv(
    argv: Sequence[str], *, expected_port: int
) -> tuple[str, str]:
    """Accept only the canonical ``run-local.ps1 -Profile official_q4`` argv."""

    browser_modes = {
        "--auto-launch": "auto_launch",
        "--disable-auto-launch": "disabled",
    }
    if (
        len(argv) != 15
        or argv[1:4] != ["--listen", "127.0.0.1", "--port"]
        or argv[4] != str(expected_port)
        or argv[5:9]
        != [
            "--preview-method",
            "none",
            "--disable-pinned-memory",
            "--output-directory",
        ]
        or argv[10:14]
        != [
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            _EXPECTED_CUSTOM_NODE_WHITELIST[0],
            "--enable-dynamic-vram",
        ]
        or argv[14] not in browser_modes
    ):
        # Exact positions intentionally reject argparse abbreviations, all
        # ``--flag=value`` forms, duplicates, model-root redirects, emergency
        # VRAM modes, and any future semantic flag until explicitly reviewed.
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    return argv[9], browser_modes[argv[14]]


def _live_runtime_path(
    workspace: Path,
    raw: str,
    *,
    expected_relative: str,
) -> str:
    expected_lexical = workspace / Path(expected_relative)
    if _has_symlink_component(workspace, raw) or _has_symlink_component(
        workspace, expected_lexical
    ):
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    try:
        actual = workspace_path(workspace, raw, must_exist=True)
        expected = workspace_path(workspace, expected_lexical, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        ) from exc
    if actual != expected or actual.is_symlink():
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    return expected_relative


def _validate_live_comfyui_runtime(
    workspace: Path,
    base_url: str,
    *,
    timeout: float,
    opener: Callable[..., Any] | None,
) -> dict[str, Any]:
    """Attest the attached loopback process before touching its queue."""

    try:
        raw = _http_request(
            base_url,
            SYSTEM_STATS_ENDPOINT,
            method="GET",
            body=None,
            timeout=timeout,
            maximum_bytes=MAX_SYSTEM_STATS_RESPONSE_BYTES,
            opener=opener,
        )
        response = _json_response(raw)
    except (
        _RedirectRejected,
        _HTTPStatusError,
        _HTTPTransportError,
        _HTTPResponseError,
    ) as exc:
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime could not be verified.",
            code="invalid_comfyui_runtime",
        ) from exc

    system = response.get("system")
    devices = response.get("devices")
    if not isinstance(system, dict) or not isinstance(devices, list):
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    argv = system.get("argv")
    if (
        not isinstance(argv, list)
        or len(argv) != 15
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 2048
            or "\x00" in item
            for item in argv
        )
        or sum(len(item) for item in argv) > 32 * 1024
    ):
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    parsed_base = urllib.parse.urlsplit(base_url)
    expected_port = parsed_base.port
    if expected_port is None:  # normalized base URLs always carry a port
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    output_raw, browser_mode = _strict_studio_runtime_argv(
        argv, expected_port=expected_port
    )
    python_version = system.get("python_version")
    if (
        system.get("comfyui_version") != _EXPECTED_COMFYUI_VERSION
        or system.get("pytorch_version") != _EXPECTED_PYTORCH_VERSION
        or not isinstance(python_version, str)
        or not re.match(rf"^{re.escape(_EXPECTED_PYTHON_PREFIX)}(?:\.|\s)", python_version)
    ):
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    root = workspace.resolve(strict=True)
    main_relative = _live_runtime_path(
        root, argv[0], expected_relative="runtime/ComfyUI/main.py"
    )
    output_relative = _live_runtime_path(
        root, output_raw, expected_relative="outputs"
    )
    if not (root / main_relative).is_file() or not (root / output_relative).is_dir():
        raise ComfyUIProviderError(
            "The attached ComfyUI runtime is invalid.",
            code="invalid_comfyui_runtime",
        )
    return {
        "comfyui_version": _EXPECTED_COMFYUI_VERSION,
        "pytorch_version": _EXPECTED_PYTORCH_VERSION,
        "python_series": _EXPECTED_PYTHON_PREFIX,
        "argv": {
            "main": main_relative,
            "listen": "127.0.0.1",
            "port": expected_port,
            "output_directory": output_relative,
            "disable_all_custom_nodes": True,
            "whitelist_custom_nodes": list(_EXPECTED_CUSTOM_NODE_WHITELIST),
            "vram_mode": "dynamic",
            "browser_mode": browser_mode,
        },
    }


def _normalize_recorded_live_runtime(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "comfyui_version",
        "pytorch_version",
        "python_series",
        "argv",
    }:
        return None
    argv = value.get("argv")
    if (
        value.get("comfyui_version") != _EXPECTED_COMFYUI_VERSION
        or value.get("pytorch_version") != _EXPECTED_PYTORCH_VERSION
        or value.get("python_series") != _EXPECTED_PYTHON_PREFIX
        or not isinstance(argv, Mapping)
        or set(argv)
        != {
            "main",
            "listen",
            "port",
            "output_directory",
            "disable_all_custom_nodes",
            "whitelist_custom_nodes",
            "vram_mode",
            "browser_mode",
        }
        or argv.get("main") != "runtime/ComfyUI/main.py"
        or argv.get("listen") != "127.0.0.1"
        or isinstance(argv.get("port"), bool)
        or not isinstance(argv.get("port"), int)
        or not 1 <= argv["port"] <= 65535
        or argv.get("output_directory") != "outputs"
        or argv.get("disable_all_custom_nodes") is not True
        or argv.get("whitelist_custom_nodes") != list(_EXPECTED_CUSTOM_NODE_WHITELIST)
        or argv.get("vram_mode") != "dynamic"
        or argv.get("browser_mode") not in {"auto_launch", "disabled"}
    ):
        return None
    return {
        "comfyui_version": _EXPECTED_COMFYUI_VERSION,
        "pytorch_version": _EXPECTED_PYTORCH_VERSION,
        "python_series": _EXPECTED_PYTHON_PREFIX,
        "argv": dict(argv),
    }


def _output_prefix(production_id: str, run_id: str, cache_key: str) -> str:
    return (
        f"studio/comfyui/{production_id}/{run_id}/"
        f"{cache_key[:16]}/generated"
    )


def _submission_marker_path(workspace: Path, production_id: str, cache_key: str) -> Path:
    relative = (
        Path("outputs")
        / "studio"
        / "external-submissions"
        / COMFYUI_PROVIDER
        / production_id
        / cache_key
    )
    parent = _ensure_safe_directory(workspace, relative)
    marker = parent / SUBMISSION_MARKER_FILENAME
    if marker.is_symlink():
        raise ComfyUIError("The ComfyUI submission marker is unsafe.", code="unsafe_output_path")
    return marker


def _read_marker(marker: Path) -> dict[str, Any] | None:
    if not marker.exists() and not marker.is_symlink():
        return None
    if marker.is_symlink() or not marker.is_file():
        raise ComfyUIError("The ComfyUI submission marker is unsafe.", code="unsafe_output_path")
    try:
        if marker.stat().st_size <= 0 or marker.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError("size")
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ComfyUISubmissionUnknown() from exc
    if not isinstance(value, dict):
        raise ComfyUISubmissionUnknown()
    return value


def _marker_body(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload_digest: str,
    prompt_id: str | None = None,
    queue_number: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": COMFYUI_SCHEMA_VERSION,
        "implementation_version": COMFYUI_IMPLEMENTATION_VERSION,
        "provider": COMFYUI_PROVIDER,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "payload_digest": payload_digest,
    }
    if prompt_id is not None:
        result["prompt_id"] = prompt_id
        result["queue_number"] = queue_number
    return result


def _create_marker(marker: Path, body: Mapping[str, Any]) -> None:
    data = (canonical_json(body) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise ComfyUIError("The ComfyUI submission marker is too large.", code="metadata_too_large")
    try:
        with marker.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ComfyUISubmissionUnknown() from exc
    except OSError as exc:
        raise ComfyUIError(
            "The ComfyUI submission marker could not be created.", code="publish_failed"
        ) from exc


def _replace_marker(marker: Path, body: Mapping[str, Any]) -> None:
    if marker.is_symlink() or not marker.is_file():
        raise ComfyUISubmissionUnknown()
    data = (canonical_json(body) + "\n").encode("utf-8")
    temporary = marker.with_name(f".{marker.name}.partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if marker.is_symlink() or not marker.is_file():
            raise ComfyUISubmissionUnknown()
        os.replace(temporary, marker)
    except FileExistsError as exc:
        raise ComfyUISubmissionUnknown() from exc
    except ComfyUIError:
        raise
    except OSError as exc:
        raise ComfyUISubmissionUnknown() from exc
    finally:
        temporary.unlink(missing_ok=True)


def _remove_marker(marker: Path) -> None:
    if not marker.exists() and not marker.is_symlink():
        return
    if marker.is_symlink() or not marker.is_file():
        raise ComfyUIError("The ComfyUI submission marker is unsafe.", code="unsafe_output_path")
    try:
        marker.unlink()
    except OSError as exc:
        raise ComfyUISubmissionUnknown() from exc


def _marker_matches(
    marker: Mapping[str, Any],
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload_digest: str,
    prompt_id: str,
) -> bool:
    expected = _marker_body(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        payload_digest=payload_digest,
        prompt_id=prompt_id,
        queue_number=marker.get("queue_number"),
    )
    return dict(marker) == expected and (
        marker.get("queue_number") is None
        or (
            isinstance(marker.get("queue_number"), int)
            and not isinstance(marker.get("queue_number"), bool)
            and marker["queue_number"] >= 0
        )
    )


def recover_comfyui_prompt_id(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload_digest: str,
) -> str | None:
    """Recover a callback-gap prompt ID from one exact durable marker.

    A missing marker returns ``None``.  A present marker without a fully
    validated prompt ID is ambiguous and fails closed instead of inviting a
    new POST.
    """

    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    cache_key = _strict_cache_key(cache_key)
    if (
        not isinstance(payload_digest, str)
        or not re.fullmatch(r"[0-9A-Fa-f]{64}", payload_digest)
    ):
        raise ComfyUIValidationError("payload_digest is invalid")
    root = workspace.resolve(strict=True)
    marker = _submission_marker_path(root, production_id, cache_key)
    value = _read_marker(marker)
    if value is None:
        return None
    raw_prompt_id = value.get("prompt_id")
    if raw_prompt_id is None:
        raise ComfyUISubmissionUnknown()
    prompt_id = _strict_prompt_id(raw_prompt_id)
    if not _marker_matches(
        value,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        payload_digest=payload_digest.upper(),
        prompt_id=prompt_id,
    ):
        raise ComfyUISubmissionUnknown()
    return prompt_id


def _submit_prompt(
    base_url: str,
    submitted_graph: Mapping[str, Any],
    *,
    timeout: float,
    opener: Callable[..., Any] | None,
) -> tuple[str, int | None]:
    try:
        raw = _http_request(
            base_url,
            PROMPT_ENDPOINT,
            method="POST",
            body={"prompt": submitted_graph},
            timeout=timeout,
            maximum_bytes=MAX_HTTP_RESPONSE_BYTES,
            opener=opener,
        )
        response = _json_response(raw)
    except _HTTPStatusError as exc:
        if 400 <= exc.status < 500 and exc.status not in {408, 429}:
            raise ComfyUIProviderError(
                "ComfyUI rejected the workflow.", code="comfyui_request_rejected"
            ) from exc
        raise ComfyUISubmissionUnknown() from exc
    except (_RedirectRejected, _HTTPTransportError, _HTTPResponseError) as exc:
        raise ComfyUISubmissionUnknown() from exc
    try:
        prompt_id = _strict_prompt_id(response.get("prompt_id"))
    except ComfyUIProviderError as exc:
        # A syntactically successful POST response can still correspond to an
        # accepted queue item.  An unusable ID is therefore ambiguous.
        raise ComfyUISubmissionUnknown() from exc
    node_errors = response.get("node_errors", {})
    if not isinstance(node_errors, dict) or node_errors:
        # A valid prompt_id means work may already be queued even if unexpected
        # metadata accompanies it.  Preserve the marker and fail closed.
        raise ComfyUISubmissionUnknown()
    number = response.get("number")
    if number is not None and (
        isinstance(number, bool) or not isinstance(number, int) or number < 0
    ):
        raise ComfyUISubmissionUnknown()
    return prompt_id, number


def _history_entry(
    base_url: str,
    prompt_id: str,
    *,
    timeout: float,
    opener: Callable[..., Any] | None,
) -> dict[str, Any] | None:
    path = HISTORY_ENDPOINT.format(prompt_id=urllib.parse.quote(prompt_id, safe="-"))
    try:
        raw = _http_request(
            base_url,
            path,
            method="GET",
            body=None,
            timeout=timeout,
            maximum_bytes=MAX_HTTP_RESPONSE_BYTES,
            opener=opener,
        )
        response = _json_response(raw)
    except (_RedirectRejected, _HTTPStatusError, _HTTPTransportError, _HTTPResponseError) as exc:
        raise ComfyUISubmissionUnknown() from exc
    if not response:
        return None
    if set(response) != {prompt_id} or not isinstance(response.get(prompt_id), dict):
        raise ComfyUISubmissionUnknown()
    return response[prompt_id]


def _terminal_history(
    entry: Mapping[str, Any],
    *,
    prompt_id: str,
    submitted_graph: Mapping[str, Any],
) -> dict[str, Any] | None:
    history_prompt = entry.get("prompt")
    if (
        not isinstance(history_prompt, list)
        or len(history_prompt) < 3
        or history_prompt[1] != prompt_id
        or history_prompt[2] != submitted_graph
    ):
        raise ComfyUISubmissionUnknown()
    status = entry.get("status")
    if not isinstance(status, dict):
        raise ComfyUISubmissionUnknown()
    status_str = status.get("status_str")
    completed = status.get("completed")
    if status_str == "error":
        return {"state": "error"}
    if status_str == "success" and completed is True:
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict) or set(outputs) != {"92"}:
            raise ComfyUISubmissionUnknown()
        node = outputs.get("92")
        if (
            not isinstance(node, dict)
            or "images" not in node
            or set(node) - {"images", "animated"}
            or not isinstance(node.get("images"), list)
            or len(node["images"]) != 1
        ):
            raise ComfyUISubmissionUnknown()
        output = node["images"][0]
        if not isinstance(output, dict) or set(output) != {"filename", "subfolder", "type"}:
            raise ComfyUISubmissionUnknown()
        return {"state": "success", "output": dict(output)}
    if completed in {False, None} and status_str in {"queued", "running", None}:
        return None
    raise ComfyUISubmissionUnknown()


def _best_effort_queue_cancel(
    base_url: str,
    prompt_id: str,
    *,
    timeout: float,
    opener: Callable[..., Any] | None,
) -> None:
    try:
        _http_request(
            base_url,
            QUEUE_ENDPOINT,
            method="POST",
            body={"delete": [prompt_id]},
            timeout=min(timeout, 10.0),
            maximum_bytes=MAX_QUEUE_RESPONSE_BYTES,
            allow_empty=True,
            opener=opener,
        )
    except BaseException:
        # Cancellation is advisory.  The durable marker remains the safety
        # boundary regardless of whether this best-effort request succeeds.
        return


def _poll_history(
    base_url: str,
    prompt_id: str,
    submitted_graph: Mapping[str, Any],
    *,
    request_timeout: float,
    generation_timeout: float,
    poll_interval: float,
    cancel_event: Any | None,
    opener: Callable[..., Any] | None,
) -> dict[str, Any]:
    deadline = time.monotonic() + generation_timeout
    while True:
        _raise_if_cancelled(cancel_event)
        if time.monotonic() >= deadline:
            raise ComfyUIError("ComfyUI generation timed out.", code="comfyui_timeout")
        entry = _history_entry(
            base_url, prompt_id, timeout=request_timeout, opener=opener
        )
        if entry is not None:
            terminal = _terminal_history(
                entry, prompt_id=prompt_id, submitted_graph=submitted_graph
            )
            if terminal is not None:
                return terminal
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ComfyUIError("ComfyUI generation timed out.", code="comfyui_timeout")
        sleep_for = min(poll_interval, remaining)
        # Keep cancellation responsive without one long blocking sleep.
        sleep_deadline = time.monotonic() + sleep_for
        while time.monotonic() < sleep_deadline:
            _raise_if_cancelled(cancel_event)
            time.sleep(min(0.1, sleep_deadline - time.monotonic()))


def _safe_output_roots(
    workspace: Path, output_roots: Sequence[str | Path]
) -> list[Path]:
    if not isinstance(output_roots, (list, tuple)) or not 1 <= len(output_roots) <= 8:
        raise ComfyUIValidationError("output_roots is invalid")
    root = workspace.resolve(strict=True)
    result: list[Path] = []
    for index, raw in enumerate(output_roots):
        if not isinstance(raw, (str, Path)) or not str(raw) or len(str(raw)) > 1024:
            raise ComfyUIValidationError(f"output_roots[{index}] is invalid")
        if _has_symlink_component(root, raw):
            raise ComfyUIValidationError(f"output_roots[{index}] is unsafe")
        try:
            path = workspace_path(root, raw, must_exist=True)
        except (SecurityError, OSError, RuntimeError) as exc:
            raise ComfyUIValidationError(f"output_roots[{index}] is unavailable") from exc
        if path.is_symlink() or not path.is_dir():
            raise ComfyUIValidationError(f"output_roots[{index}] is unsafe")
        if path not in result:
            result.append(path)
    return result


def _source_output(
    workspace: Path,
    metadata: Mapping[str, Any],
    *,
    output_roots: Sequence[str | Path],
    expected_output_prefix: str,
) -> tuple[Path, dict[str, str]]:
    filename = metadata.get("filename")
    subfolder = metadata.get("subfolder")
    output_type = metadata.get("type")
    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > 255
        or filename != Path(filename).name
        or "/" in filename
        or "\\" in filename
        or Path(filename).suffix.casefold() != ".mp4"
        or not isinstance(subfolder, str)
        or len(subfolder) > 1024
        or output_type != "output"
    ):
        raise ComfyUIMediaError(
            "ComfyUI returned an unsafe output path.", code="unsafe_provider_output"
        )
    normalized_subfolder = subfolder.replace("\\", "/")
    subpath = Path(normalized_subfolder)
    if subpath.is_absolute() or ".." in subpath.parts or subpath.drive:
        raise ComfyUIMediaError(
            "ComfyUI returned an unsafe output path.", code="unsafe_provider_output"
        )
    normalized_prefix = expected_output_prefix.replace("\\", "/")
    prefix_path = Path(normalized_prefix)
    expected_subfolder = prefix_path.parent.as_posix()
    expected_stem = prefix_path.name
    if (
        not _OUTPUT_PREFIX_RE.fullmatch(normalized_prefix)
        or prefix_path.is_absolute()
        or ".." in prefix_path.parts
        or normalized_subfolder != expected_subfolder
        or re.fullmatch(
            rf"{re.escape(expected_stem)}_[0-9]{{5,10}}_\.mp4", filename
        )
        is None
    ):
        raise ComfyUIMediaError(
            "ComfyUI returned output outside the submitted prefix.",
            code="mismatched_provider_output",
        )
    candidates: list[Path] = []
    for root in _safe_output_roots(workspace, output_roots):
        lexical = root / subpath / filename
        if _has_symlink_component(workspace, lexical):
            continue
        try:
            candidate = lexical.resolve(strict=True)
            candidate.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        candidates.append(candidate)
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1:
        raise ComfyUIMediaError(
            "The ComfyUI output is unavailable or ambiguous.", code="invalid_comfyui_output"
        )
    path = unique[0]
    size = path.stat().st_size
    if size <= 0 or size > MAX_OUTPUT_BYTES:
        raise ComfyUIMediaError(
            "The ComfyUI output size is unsupported.", code="invalid_comfyui_output"
        )
    return path, {
        "filename": filename,
        "subfolder": normalized_subfolder,
        "type": "output",
    }


def _finite_duration(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _rate(value: Any) -> float | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        result = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _validate_probe(probe: Mapping[str, Any], *, expected_bytes: int) -> tuple[int, dict[str, Any]]:
    streams = probe.get("streams")
    format_data = probe.get("format")
    if not isinstance(streams, list) or not isinstance(format_data, dict):
        raise ComfyUIMediaError("ffprobe returned invalid media metadata.", code="invalid_media")
    videos = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"]
    audios = [item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1 or len(streams) != 2:
        raise ComfyUIMediaError("ComfyUI output streams are invalid.", code="invalid_media")
    video, audio = videos[0], audios[0]
    frame_rate = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    frame_count_raw = video.get("nb_frames")
    try:
        frame_count = int(frame_count_raw)
    except (TypeError, ValueError):
        frame_count = -1
    if (
        video.get("codec_name") != OUTPUT_POLICY["video_codec"]
        or video.get("pix_fmt") != OUTPUT_POLICY["pixel_format"]
        or video.get("width") != OUTPUT_POLICY["width"]
        or video.get("height") != OUTPUT_POLICY["height"]
        or frame_rate is None
        or abs(frame_rate - OUTPUT_POLICY["frame_rate"]) > 0.001
        or frame_count != OUTPUT_POLICY["expected_frames"]
        or audio.get("codec_name") != OUTPUT_POLICY["audio_codec"]
        or str(audio.get("sample_rate")) != str(OUTPUT_POLICY["audio_sample_rate"])
        or audio.get("channels") != OUTPUT_POLICY["audio_channels"]
    ):
        raise ComfyUIMediaError("ComfyUI output media policy does not match.", code="invalid_media")
    format_name = format_data.get("format_name")
    if not isinstance(format_name, str) or "mp4" not in format_name.split(","):
        raise ComfyUIMediaError("ComfyUI output container is invalid.", code="invalid_media")
    reported_size = format_data.get("size")
    if reported_size is not None:
        try:
            if int(reported_size) != expected_bytes:
                raise ValueError("size")
        except (TypeError, ValueError) as exc:
            raise ComfyUIMediaError("ComfyUI output size metadata is invalid.", code="invalid_media") from exc
    duration = (
        _finite_duration(video.get("duration"))
        or _finite_duration(format_data.get("duration"))
    )
    if duration is None:
        raise ComfyUIMediaError("ComfyUI output duration is unavailable.", code="invalid_media")
    duration_ms = int(round(duration * 1000))
    if abs(duration_ms - OUTPUT_POLICY["expected_duration_ms"]) > OUTPUT_POLICY["duration_tolerance_ms"]:
        raise ComfyUIMediaError("ComfyUI output duration is invalid.", code="invalid_media")
    audio_duration = _finite_duration(audio.get("duration"))
    if (
        audio_duration is None
        or abs(int(round(audio_duration * 1000)) - duration_ms)
        > OUTPUT_POLICY["duration_tolerance_ms"]
    ):
        raise ComfyUIMediaError(
            "ComfyUI output audio duration is invalid.", code="invalid_media"
        )
    summary = {
        "container": "mp4",
        "duration_ms": duration_ms,
        "bytes": expected_bytes,
        "video": {
            "codec": video["codec_name"],
            "pixel_format": video["pix_fmt"],
            "width": video["width"],
            "height": video["height"],
            "frame_rate": frame_rate,
            "frames": frame_count,
        },
        "audio": {
            "codec": audio["codec_name"],
            "sample_rate": int(audio["sample_rate"]),
            "channels": audio["channels"],
            "duration_ms": int(round(audio_duration * 1000)),
        },
    }
    return duration_ms, summary


def _probe_media(
    ffprobe: str,
    path: Path,
    *,
    cwd: Path,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    try:
        output = _bounded_process(
            [
                ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                (
                    "format=format_name,duration,size:"
                    "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                    "r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames"
                ),
                "-of",
                "json",
                str(path),
            ],
            cwd=cwd,
            timeout=30.0,
            label="ComfyUI ffprobe",
            cancel_event=cancel_event,
        )
        raw = json.loads(output.decode("utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("streams"), list):
            raise ValueError("invalid probe")
    except JobCancelled:
        raise
    except (AssemblyError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ComfyUIMediaError(
            "ffprobe could not inspect the ComfyUI output.", code="local_ffprobe_failed"
        ) from exc
    size = (cwd / path).stat().st_size if not path.is_absolute() else path.stat().st_size
    duration_ms, summary = _validate_probe(raw, expected_bytes=size)
    return raw, duration_ms, summary


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise ComfyUIError("ComfyUI metadata is too large.", code="metadata_too_large")
    temporary = path.with_name(f".{path.name}.partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_record(
    workspace: Path, cache_directory: Path, spec: Mapping[str, str]
) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
    if path.is_symlink() or not path.is_file():
        raise ComfyUIError("A ComfyUI artifact is unavailable.", code="invalid_cache")
    size = path.stat().st_size
    relative = path.relative_to(workspace.resolve(strict=True)).as_posix()
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": size,
        "sha256": _sha256_file(path),
        "mime": spec["mime"],
        "media_type": spec["mime"],
        "origin": "studio",
        "version": COMFYUI_IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": size > 10 * 1024 * 1024,
    }


def _cache_directory(workspace: Path, run_id: str, cache_key: str) -> Path:
    validate_identifier(run_id, label="run id")
    cache_key = _strict_cache_key(cache_key)
    relative_parent = Path("outputs") / "studio" / "runs" / run_id / "video_generation"
    parent = _ensure_safe_directory(workspace, relative_parent)
    cache = parent / cache_key
    if cache.is_symlink():
        raise ComfyUIError("The ComfyUI cache path is unsafe.", code="unsafe_output_path")
    return cache


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload: Mapping[str, Any],
    workflow_record: Mapping[str, Any],
    model_records: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    provider_runtime: Mapping[str, Any],
    ffprobe_identity: Mapping[str, Any],
    prompt_id: str,
    queue_number: int | None,
    output_metadata: Mapping[str, Any],
    source_output: Path,
    source_output_sha256: str,
    duration_ms: int,
    media_summary: Mapping[str, Any],
    submitted_payload_sha256: str,
    stage: Path,
    workspace: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _ARTIFACT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = stage / spec["filename"]
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    prompt_sha256 = _sha256_bytes(str(payload["prompt"]).encode("utf-8"))
    body: dict[str, Any] = {
        "schema_version": COMFYUI_SCHEMA_VERSION,
        "implementation_version": COMFYUI_IMPLEMENTATION_VERSION,
        "provider": COMFYUI_PROVIDER,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider_task_id": prompt_id,
        "prompt_id": prompt_id,
        "queue_number": queue_number,
        "actual_cost": 0,
        "timing_source": COMFYUI_TIMING_SOURCE,
        "duration_ms": duration_ms,
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_sha256": prompt_sha256,
        "seed": payload["seed"],
        "seed_decimal": str(payload["seed"]),
        "payload_digest": comfyui_payload_digest(payload),
        "submitted_payload_sha256": submitted_payload_sha256,
        "workflow": dict(workflow_record),
        "models": {role: dict(record) for role, record in model_records.items()},
        "runtime_identity": copy.deepcopy(dict(runtime_identity)),
        "provider_runtime": copy.deepcopy(dict(provider_runtime)),
        "ffprobe_identity": dict(ffprobe_identity),
        "output_policy": dict(OUTPUT_POLICY),
        "provider_status": {"status_str": "success", "completed": True},
        "provider_output": dict(output_metadata),
        "source_output": {
            "path": source_output.relative_to(workspace.resolve(strict=True)).as_posix(),
            "bytes": source_output.stat().st_size,
            "sha256": source_output_sha256,
        },
        "media": dict(media_summary),
        "files": files,
    }
    body["manifest_sha256"] = _manifest_digest(body)
    return body


def _publish(stage: Path, cache_directory: Path) -> None:
    if (
        stage.is_symlink()
        or not stage.is_dir()
        or stage.parent != cache_directory.parent
        or cache_directory.parent.is_symlink()
        or not cache_directory.parent.is_dir()
        or stage.resolve(strict=True).parent
        != cache_directory.parent.resolve(strict=True)
    ):
        raise ComfyUIError(
            "The ComfyUI publish path is unsafe.", code="unsafe_output_path"
        )
    if cache_directory.exists() or cache_directory.is_symlink():
        raise ComfyUIError(
            "The ComfyUI cache path already exists and was not reused.",
            code="cache_integrity_failed",
        )
    try:
        os.replace(stage, cache_directory)
    except OSError as exc:
        raise ComfyUIError("ComfyUI artifacts could not be published.", code="publish_failed") from exc


def _result(
    workspace: Path,
    cache_directory: Path,
    manifest: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "provider": COMFYUI_PROVIDER,
        "provider_task_id": manifest["prompt_id"],
        "prompt_id": manifest["prompt_id"],
        "actual_cost": 0,
        "timing_source": COMFYUI_TIMING_SOURCE,
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_sha256": manifest["prompt_sha256"],
        "seed": manifest["seed"],
        "output_directory": cache_directory.relative_to(workspace.resolve(strict=True)).as_posix(),
    }


def _validate_cache(
    workspace: Path,
    cache_directory: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload: Mapping[str, Any],
    workflow_record: Mapping[str, Any],
    model_records: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    provider_runtime: Mapping[str, Any] | None,
    ffprobe_identity: Mapping[str, Any],
    submitted_graph: Mapping[str, Any],
    output_prefix: str,
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _raise_if_cancelled(cancel_event)
    if not cache_directory.is_dir() or cache_directory.is_symlink():
        return None
    expected_names = {spec["filename"] for spec in _ARTIFACT_SPECS}
    try:
        if {child.name for child in cache_directory.iterdir()} != expected_names:
            return None
    except OSError:
        return None
    manifest = _read_json(cache_directory / "manifest.json")
    if manifest is None:
        return None
    self_hash = manifest.get("manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    prompt_sha256 = _sha256_bytes(str(payload["prompt"]).encode("utf-8"))
    recorded_provider_runtime = _normalize_recorded_live_runtime(
        manifest.get("provider_runtime")
    )
    if (
        not isinstance(self_hash, str)
        or self_hash != _manifest_digest(unsigned)
        or manifest.get("schema_version") != COMFYUI_SCHEMA_VERSION
        or manifest.get("implementation_version") != COMFYUI_IMPLEMENTATION_VERSION
        or manifest.get("provider") != COMFYUI_PROVIDER
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("cache_key") != cache_key
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != COMFYUI_TIMING_SOURCE
        or manifest.get("workflow_preset") != COMFYUI_WORKFLOW_PRESET
        or manifest.get("prompt_sha256") != prompt_sha256
        or manifest.get("seed") != payload["seed"]
        or manifest.get("seed_decimal") != str(payload["seed"])
        or manifest.get("payload_digest") != comfyui_payload_digest(payload)
        or manifest.get("workflow") != dict(workflow_record)
        or manifest.get("models") != {role: dict(record) for role, record in model_records.items()}
        or manifest.get("runtime_identity") != dict(runtime_identity)
        or recorded_provider_runtime is None
        or (
            provider_runtime is not None
            and recorded_provider_runtime != dict(provider_runtime)
        )
        or manifest.get("ffprobe_identity") != dict(ffprobe_identity)
        or manifest.get("output_policy") != dict(OUTPUT_POLICY)
        or manifest.get("provider_status") != {"status_str": "success", "completed": True}
    ):
        return None
    try:
        prompt_id = _strict_prompt_id(manifest.get("prompt_id"))
    except ComfyUIError:
        return None
    if manifest.get("provider_task_id") != prompt_id:
        return None
    workflow_document = _read_json(cache_directory / "workflow.json")
    expected_request = {"prompt": submitted_graph}
    expected_request_sha = _sha256_bytes(canonical_json(expected_request).encode("utf-8"))
    if (
        workflow_document is None
        or workflow_document.get("schema_version") != COMFYUI_SCHEMA_VERSION
        or workflow_document.get("implementation_version") != COMFYUI_IMPLEMENTATION_VERSION
        or workflow_document.get("workflow_preset") != COMFYUI_WORKFLOW_PRESET
        or workflow_document.get("prompt_sha256") != prompt_sha256
        or workflow_document.get("seed") != payload["seed"]
        or workflow_document.get("seed_decimal") != str(payload["seed"])
        or workflow_document.get("output_prefix") != output_prefix
        or workflow_document.get("request_body") != expected_request
        or workflow_document.get("submitted_payload_sha256") != expected_request_sha
        or manifest.get("submitted_payload_sha256") != expected_request_sha
    ):
        return None
    files = manifest.get("files")
    expected_file_names = expected_names - {"manifest.json"}
    if not isinstance(files, dict) or set(files) != expected_file_names:
        return None
    for spec in _ARTIFACT_SPECS:
        path = cache_directory / spec["filename"]
        if path.is_symlink() or not path.is_file():
            return None
        if spec["filename"] == "manifest.json":
            continue
        entry = files.get(spec["filename"])
        size = path.stat().st_size
        if (
            not isinstance(entry, dict)
            or entry.get("path") != spec["filename"]
            or entry.get("kind") != spec["kind"]
            or entry.get("mime") != spec["mime"]
            or entry.get("bytes") != size
            or entry.get("sha256") != _sha256_file(path, cancel_event=cancel_event)
            or (spec["filename"] == "generated-video.mp4" and not 0 < size <= MAX_OUTPUT_BYTES)
        ):
            return None
    ffprobe_document = _read_json(cache_directory / "ffprobe.json")
    if (
        ffprobe_document is None
        or ffprobe_document.get("schema_version") != COMFYUI_SCHEMA_VERSION
        or ffprobe_document.get("implementation_version") != COMFYUI_IMPLEMENTATION_VERSION
        or ffprobe_document.get("timing_source") != COMFYUI_TIMING_SOURCE
        or not isinstance(ffprobe_document.get("raw"), dict)
        or ffprobe_document.get("summary") != manifest.get("media")
    ):
        return None
    try:
        fresh_raw, fresh_duration, fresh_summary = _probe_media(
            ffprobe,
            Path("generated-video.mp4"),
            cwd=cache_directory,
            cancel_event=cancel_event,
        )
    except (ComfyUIError, OSError):
        return None
    if (
        fresh_duration != manifest.get("duration_ms")
        or fresh_summary != manifest.get("media")
        or fresh_raw != ffprobe_document.get("raw")
    ):
        return None
    try:
        artifacts = [
            _artifact_record(workspace, cache_directory, spec)
            for spec in _ARTIFACT_SPECS
        ]
    except (OSError, ComfyUIError):
        return None
    return manifest, artifacts


def _preflight(
    workspace: Path,
    *,
    expected_cache_key: str | None = None,
    production_id: str,
    run_id: str,
    payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    model_files: Mapping[str, Any],
    ffprobe: str | Path | None,
    cancel_event: Any | None,
) -> dict[str, Any]:
    if expected_cache_key is not None and (
        not isinstance(expected_cache_key, str)
        or _CACHE_KEY_RE.fullmatch(expected_cache_key) is None
    ):
        raise ComfyUIValidationError(
            "The queued ComfyUI cache identity is invalid.",
            code="cache_key_mismatch",
        )
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    normalized_payload = validate_comfyui_payload(dict(payload))
    workspace = workspace.resolve(strict=True)
    graph, workflow_record = _workflow_record(
        workspace,
        workflow,
        workflow_source_path=workflow_source_path,
        workflow_source_bytes=workflow_source_bytes,
        workflow_source_sha256=workflow_source_sha256,
        cancel_event=cancel_event,
    )
    model_records = _verified_model_records(
        workspace, model_files, cancel_event=cancel_event
    )
    runtime_identity = resolve_comfyui_runtime_identity(
        workspace, cancel_event=cancel_event
    )
    ffprobe_identity = resolve_comfyui_tool_identity(
        ffprobe=ffprobe, cancel_event=cancel_event
    )
    cache_key = comfyui_cache_key(
        normalized_payload,
        workflow=workflow_record,
        models=model_records,
        runtime_identity=runtime_identity,
        ffprobe_identity=ffprobe_identity,
    )
    # The service persists this identity before the GPU-lane enqueue.  Resolve
    # all mutable workflow/runtime/tool inputs again in the worker, then bind
    # execution to that queued identity before inspecting caches or markers,
    # attesting the live provider, hashing large models, or issuing HTTP.
    if expected_cache_key is not None and cache_key != expected_cache_key:
        raise ComfyUIValidationError(
            "The queued ComfyUI inputs or local runtime changed before execution.",
            code="cache_key_mismatch",
        )
    prefix = _output_prefix(production_id, run_id, cache_key)
    submitted_graph = prepare_comfyui_workflow(
        graph, normalized_payload, output_prefix=prefix
    )
    return {
        "workspace": workspace,
        "payload": normalized_payload,
        "graph": graph,
        "workflow_record": workflow_record,
        "model_records": model_records,
        "runtime_identity": runtime_identity,
        "ffprobe_identity": ffprobe_identity,
        # Invoke the exact executable whose path/version/hash participates in
        # cache and manifest identity; do not resolve PATH a second time.
        "ffprobe": ffprobe_identity["path"],
        "cache_key": cache_key,
        "output_prefix": prefix,
        "submitted_graph": submitted_graph,
    }


def _revalidate_pre_submit_identity(
    prepared: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    model_files: Mapping[str, Any],
    cancel_event: Any | None,
) -> None:
    """Rebind lightweight filesystem/tool identity after model hashing."""

    root = Path(prepared["workspace"])
    graph, workflow_record = _workflow_record(
        root,
        workflow,
        workflow_source_path=workflow_source_path,
        workflow_source_bytes=workflow_source_bytes,
        workflow_source_sha256=workflow_source_sha256,
        cancel_event=cancel_event,
    )
    model_records = _verified_model_records(
        root, model_files, cancel_event=cancel_event
    )
    runtime_identity = resolve_comfyui_runtime_identity(
        root, cancel_event=cancel_event
    )
    ffprobe_identity = resolve_comfyui_tool_identity(
        ffprobe=prepared["ffprobe"], cancel_event=cancel_event
    )
    cache_key = comfyui_cache_key(
        prepared["payload"],
        workflow=workflow_record,
        models=model_records,
        runtime_identity=runtime_identity,
        ffprobe_identity=ffprobe_identity,
    )
    _raise_if_cancelled(cancel_event)
    if (
        graph != prepared["graph"]
        or workflow_record != prepared["workflow_record"]
        or model_records != prepared["model_records"]
        or runtime_identity != prepared["runtime_identity"]
        or ffprobe_identity != prepared["ffprobe_identity"]
        or cache_key != prepared["cache_key"]
    ):
        raise ComfyUIValidationError(
            "The queued ComfyUI inputs or local runtime changed before submission.",
            code="cache_key_mismatch",
        )


def _generate_comfyui_video_impl(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    model_files: Mapping[str, Any],
    output_roots: Sequence[str | Path],
    expected_cache_key: str,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    base_url: str = DEFAULT_BASE_URL,
    request_timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    generation_timeout_seconds: float = GENERATION_TIMEOUT_SECONDS,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    opener: Callable[..., Any] | None = None,
    resume_prompt_id: str | None = None,
    on_provider_task_id: Callable[[str], None] | None = None,
    _model_guard_owner: list[_ModelVerification],
) -> dict[str, Any]:
    """Submit or resume the pinned workflow and publish verified artifacts.

    ``on_provider_task_id`` runs exactly once for a new submission, after the
    prompt ID is durably added to the ambiguity marker and before polling.
    A callback failure leaves that marker intact and is surfaced as an unknown
    submission so a caller cannot automatically submit the expensive job a
    second time.  Resumes never invoke the callback again.
    """

    _raise_if_cancelled(cancel_event)
    base_url = _normalize_base_url(base_url)
    request_timeout = _bounded_seconds(
        request_timeout_seconds,
        label="request_timeout_seconds",
        minimum=0.1,
        maximum=120.0,
    )
    generation_timeout = _bounded_seconds(
        generation_timeout_seconds,
        label="generation_timeout_seconds",
        minimum=0.1,
        maximum=12 * 60 * 60.0,
    )
    poll_interval = _bounded_seconds(
        poll_interval_seconds,
        label="poll_interval_seconds",
        minimum=0.0,
        maximum=60.0,
    )
    if on_provider_task_id is not None and not callable(on_provider_task_id):
        raise ComfyUIValidationError("on_provider_task_id must be callable")
    if opener is not None and not callable(opener):
        raise ComfyUIValidationError("opener must be callable")
    prepared = _preflight(
        workspace,
        expected_cache_key=expected_cache_key,
        production_id=production_id,
        run_id=run_id,
        payload=payload,
        workflow=workflow,
        workflow_source_path=workflow_source_path,
        workflow_source_bytes=workflow_source_bytes,
        workflow_source_sha256=workflow_source_sha256,
        model_files=model_files,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    root: Path = prepared["workspace"]
    cache_key: str = prepared["cache_key"]
    cache_directory = _cache_directory(root, run_id, cache_key)
    cached = _validate_cache(
        root,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        payload=prepared["payload"],
        workflow_record=prepared["workflow_record"],
        model_records=prepared["model_records"],
        runtime_identity=prepared["runtime_identity"],
        provider_runtime=None,
        ffprobe_identity=prepared["ffprobe_identity"],
        submitted_graph=prepared["submitted_graph"],
        output_prefix=prepared["output_prefix"],
        ffprobe=prepared["ffprobe"],
        cancel_event=cancel_event,
    )
    marker = _submission_marker_path(root, production_id, cache_key)
    if cached is not None:
        _remove_marker(marker)
        manifest, artifacts = cached
        return _result(root, cache_directory, manifest, artifacts, cache_hit=True)
    if cache_directory.exists() or cache_directory.is_symlink():
        raise ComfyUIError(
            "The existing ComfyUI cache failed integrity verification.",
            code="cache_integrity_failed",
        )

    payload_digest = comfyui_payload_digest(prepared["payload"])
    existing_marker = _read_marker(marker)
    prompt_id: str
    queue_number: int | None = None
    is_resume = resume_prompt_id is not None
    if is_resume:
        prompt_id = _strict_prompt_id(resume_prompt_id)
        if existing_marker is None or not _marker_matches(
            existing_marker,
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            payload_digest=payload_digest,
            prompt_id=prompt_id,
        ):
            raise ComfyUISubmissionUnknown()
        raw_queue_number = existing_marker.get("queue_number")
        queue_number = raw_queue_number if isinstance(raw_queue_number, int) else None
        _raise_if_cancelled(cancel_event)
        provider_runtime = _validate_live_comfyui_runtime(
            root, base_url, timeout=request_timeout, opener=opener
        )
        _raise_if_cancelled(cancel_event)
    else:
        if existing_marker is not None:
            raise ComfyUISubmissionUnknown()
        _raise_if_cancelled(cancel_event)
        provider_runtime = _validate_live_comfyui_runtime(
            root, base_url, timeout=request_timeout, opener=opener
        )
        _raise_if_cancelled(cancel_event)
        # This is the only branch that can issue a new expensive POST.  Verify
        # the physical model bytes here, after cache/marker checks avoid work
        # for cache hits and crash-safe resumes, and before creating the
        # ambiguity marker or touching ComfyUI.
        model_snapshots = _verify_model_digests(
            root,
            prepared["model_records"],
            cancel_event=cancel_event,
            guard_owner=_model_guard_owner,
        )
        _revalidate_pre_submit_identity(
            prepared,
            workflow=workflow,
            workflow_source_path=workflow_source_path,
            workflow_source_bytes=workflow_source_bytes,
            workflow_source_sha256=workflow_source_sha256,
            model_files=model_files,
            cancel_event=cancel_event,
        )
        # The initial live check protects the long model-hash phase from an
        # untrusted listener.  Re-attest after that phase as well so the POST
        # cannot target a process that restarted with different arguments.
        provider_runtime = _validate_live_comfyui_runtime(
            root, base_url, timeout=request_timeout, opener=opener
        )
        _raise_if_cancelled(cancel_event)
        _revalidate_model_snapshots(
            root,
            prepared["model_records"],
            model_snapshots,
            cancel_event=cancel_event,
        )
        marker_body = _marker_body(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            payload_digest=payload_digest,
        )
        _create_marker(marker, marker_body)
        try:
            prompt_id, queue_number = _submit_prompt(
                base_url,
                prepared["submitted_graph"],
                timeout=request_timeout,
                opener=opener,
            )
        except ComfyUIProviderError:
            # A concrete non-retryable 4xx response proves the graph was not
            # queued, so this marker may be safely removed.
            _remove_marker(marker)
            raise
        _replace_marker(
            marker,
            _marker_body(
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                payload_digest=payload_digest,
                prompt_id=prompt_id,
                queue_number=queue_number,
            ),
        )
        if on_provider_task_id is not None:
            try:
                on_provider_task_id(prompt_id)
            except BaseException as exc:
                raise ComfyUISubmissionUnknown() from exc

    try:
        terminal = _poll_history(
            base_url,
            prompt_id,
            prepared["submitted_graph"],
            request_timeout=request_timeout,
            generation_timeout=generation_timeout,
            poll_interval=poll_interval,
            cancel_event=cancel_event,
            opener=opener,
        )
    except JobCancelled:
        _best_effort_queue_cancel(
            base_url, prompt_id, timeout=request_timeout, opener=opener
        )
        raise
    except ComfyUIError as exc:
        if exc.error_code in {"process_interrupted", "comfyui_timeout"}:
            _best_effort_queue_cancel(
                base_url, prompt_id, timeout=request_timeout, opener=opener
            )
        raise
    if terminal.get("state") == "error":
        _remove_marker(marker)
        raise ComfyUIProviderError(
            "ComfyUI reported a terminal workflow error.", code="comfyui_generation_failed"
        )
    output_metadata = terminal.get("output")
    if not isinstance(output_metadata, dict):
        raise ComfyUISubmissionUnknown()

    source_output, normalized_output_metadata = _source_output(
        root,
        output_metadata,
        output_roots=output_roots,
        expected_output_prefix=prepared["output_prefix"],
    )
    source_stat_before = source_output.stat()
    source_sha256 = _sha256_file(source_output, cancel_event=cancel_event)
    source_stat_after = source_output.stat()
    if (
        source_stat_before.st_size != source_stat_after.st_size
        or source_stat_before.st_mtime_ns != source_stat_after.st_mtime_ns
    ):
        raise ComfyUIMediaError(
            "The ComfyUI output changed during verification.", code="input_changed"
        )
    raw_probe, duration_ms, media_summary = _probe_media(
        prepared["ffprobe"],
        source_output,
        cwd=root,
        cancel_event=cancel_event,
    )
    _raise_if_cancelled(cancel_event)
    cache_directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{cache_key[:16]}-", dir=str(cache_directory.parent))
    )
    published = False
    try:
        shutil.copyfile(source_output, stage / "generated-video.mp4")
        if (
            (stage / "generated-video.mp4").stat().st_size != source_stat_after.st_size
            or _sha256_file(stage / "generated-video.mp4", cancel_event=cancel_event)
            != source_sha256
        ):
            raise ComfyUIMediaError(
                "The ComfyUI output copy failed integrity verification.", code="input_changed"
            )
        request_body = {"prompt": prepared["submitted_graph"]}
        submitted_payload_sha256 = _sha256_bytes(
            canonical_json(request_body).encode("utf-8")
        )
        workflow_document = {
            "schema_version": COMFYUI_SCHEMA_VERSION,
            "implementation_version": COMFYUI_IMPLEMENTATION_VERSION,
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt_sha256": _sha256_bytes(
                prepared["payload"]["prompt"].encode("utf-8")
            ),
            "seed": prepared["payload"]["seed"],
            "seed_decimal": str(prepared["payload"]["seed"]),
            "output_prefix": prepared["output_prefix"],
            "submitted_payload_sha256": submitted_payload_sha256,
            "request_body": request_body,
        }
        _write_json(stage / "workflow.json", workflow_document)
        ffprobe_document = {
            "schema_version": COMFYUI_SCHEMA_VERSION,
            "implementation_version": COMFYUI_IMPLEMENTATION_VERSION,
            "timing_source": COMFYUI_TIMING_SOURCE,
            "raw": raw_probe,
            "summary": media_summary,
        }
        _write_json(stage / "ffprobe.json", ffprobe_document)
        manifest = _build_manifest(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            payload=prepared["payload"],
            workflow_record=prepared["workflow_record"],
            model_records=prepared["model_records"],
            runtime_identity=prepared["runtime_identity"],
            provider_runtime=provider_runtime,
            ffprobe_identity=prepared["ffprobe_identity"],
            prompt_id=prompt_id,
            queue_number=queue_number,
            output_metadata=normalized_output_metadata,
            source_output=source_output,
            source_output_sha256=source_sha256,
            duration_ms=duration_ms,
            media_summary=media_summary,
            submitted_payload_sha256=submitted_payload_sha256,
            stage=stage,
            workspace=root,
        )
        _write_json(stage / "manifest.json", manifest)
        _raise_if_cancelled(cancel_event)
        _publish(stage, cache_directory)
        published = True
    except (JobCancelled, ComfyUIError):
        raise
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise ComfyUIError(
            "ComfyUI artifacts could not be published.", code="publish_failed"
        ) from exc
    finally:
        if not published and stage.exists():
            # This exact directory was freshly created beneath one validated
            # run/cache parent; no caller-controlled path reaches rmtree.
            shutil.rmtree(stage, ignore_errors=True)

    validated = _validate_cache(
        root,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        payload=prepared["payload"],
        workflow_record=prepared["workflow_record"],
        model_records=prepared["model_records"],
        runtime_identity=prepared["runtime_identity"],
        provider_runtime=provider_runtime,
        ffprobe_identity=prepared["ffprobe_identity"],
        submitted_graph=prepared["submitted_graph"],
        output_prefix=prepared["output_prefix"],
        ffprobe=prepared["ffprobe"],
        cancel_event=cancel_event,
    )
    if validated is None:
        raise ComfyUIError(
            "Published ComfyUI artifacts failed integrity verification.",
            code="cache_integrity_failed",
        )
    _remove_marker(marker)
    manifest, artifacts = validated
    return _result(root, cache_directory, manifest, artifacts, cache_hit=False)


def generate_comfyui_video(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    model_files: Mapping[str, Any],
    output_roots: Sequence[str | Path],
    expected_cache_key: str,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    base_url: str = DEFAULT_BASE_URL,
    request_timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    generation_timeout_seconds: float = GENERATION_TIMEOUT_SECONDS,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    opener: Callable[..., Any] | None = None,
    resume_prompt_id: str | None = None,
    on_provider_task_id: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run one adapter call while retaining Windows model guards to completion."""

    model_guard_owner: list[_ModelVerification] = []
    try:
        result = _generate_comfyui_video_impl(
            workspace,
            production_id=production_id,
            run_id=run_id,
            payload=payload,
            workflow=workflow,
            workflow_source_path=workflow_source_path,
            workflow_source_bytes=workflow_source_bytes,
            workflow_source_sha256=workflow_source_sha256,
            model_files=model_files,
            output_roots=output_roots,
            expected_cache_key=expected_cache_key,
            ffprobe=ffprobe,
            cancel_event=cancel_event,
            base_url=base_url,
            request_timeout_seconds=request_timeout_seconds,
            generation_timeout_seconds=generation_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            opener=opener,
            resume_prompt_id=resume_prompt_id,
            on_provider_task_id=on_provider_task_id,
            _model_guard_owner=model_guard_owner,
        )
    except BaseException:
        # Always attempt every release, but never replace the primary job error
        # with a cleanup diagnostic.
        for verification in reversed(model_guard_owner):
            try:
                verification.close()
            except OSError:
                pass
        raise
    try:
        for verification in reversed(model_guard_owner):
            verification.close()
    except OSError as exc:
        raise ComfyUIValidationError(
            "The verified model handles could not be released.",
            code="input_changed",
        ) from exc
    return result


def resume_comfyui_video(
    workspace: Path,
    *,
    provider_task_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Resume one marker-linked prompt without submitting another workflow."""

    if "resume_prompt_id" in kwargs:
        raise ComfyUIValidationError("resume_prompt_id was provided twice")
    return generate_comfyui_video(
        workspace,
        resume_prompt_id=provider_task_id,
        **kwargs,
    )


def validate_comfyui_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_source_path: str | Path,
    workflow_source_bytes: int,
    workflow_source_sha256: str,
    model_files: Mapping[str, Any],
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Revalidate a published ComfyUI cache without HTTP or model rehashing."""

    prepared = _preflight(
        workspace,
        production_id=production_id,
        run_id=run_id,
        payload=payload,
        workflow=workflow,
        workflow_source_path=workflow_source_path,
        workflow_source_bytes=workflow_source_bytes,
        workflow_source_sha256=workflow_source_sha256,
        model_files=model_files,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    root: Path = prepared["workspace"]
    cache_directory = _cache_directory(root, run_id, prepared["cache_key"])
    validated = _validate_cache(
        root,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=prepared["cache_key"],
        payload=prepared["payload"],
        workflow_record=prepared["workflow_record"],
        model_records=prepared["model_records"],
        runtime_identity=prepared["runtime_identity"],
        provider_runtime=None,
        ffprobe_identity=prepared["ffprobe_identity"],
        submitted_graph=prepared["submitted_graph"],
        output_prefix=prepared["output_prefix"],
        ffprobe=prepared["ffprobe"],
        cancel_event=cancel_event,
    )
    if validated is None:
        raise ComfyUIError(
            "The ComfyUI cache failed integrity verification.",
            code="cache_integrity_failed",
        )
    manifest, artifacts = validated
    return _result(root, cache_directory, manifest, artifacts, cache_hit=True)


# Service-friendly aliases.
generate_local_comfyui_video = generate_comfyui_video
validate_local_comfyui_outputs = validate_comfyui_outputs


__all__ = [
    "DEFAULT_BASE_URL",
    "GENERATION_TIMEOUT_SECONDS",
    "MAX_HTTP_RESPONSE_BYTES",
    "MAX_OUTPUT_BYTES",
    "POLL_INTERVAL_SECONDS",
    "PROMPT_ENDPOINT",
    "QUEUE_ENDPOINT",
    "REQUEST_TIMEOUT_SECONDS",
    "SUBMISSION_MARKER_FILENAME",
    "generate_comfyui_video",
    "generate_local_comfyui_video",
    "prepare_comfyui_workflow",
    "recover_comfyui_prompt_id",
    "resolve_comfyui_runtime_identity",
    "resolve_comfyui_tool_identity",
    "resume_comfyui_video",
    "validate_comfyui_outputs",
    "validate_local_comfyui_outputs",
]
