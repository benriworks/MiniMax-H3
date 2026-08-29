from __future__ import annotations

"""Auditable local FFmpeg/ffprobe technical QC for Studio assembly masters.

The worker accepts one already-registered assembly master and never contacts a
provider or launches a shell.  Media is copied to a fixed name in a private
stage directory before any subprocess sees it.  A QC result is useful even
when the media fails a technical rule: malformed media facts become a
``technical_verdict=fail`` result after analysis has completed.  Only inability
to run the local tools, a timeout, unsafe input/output, or failed publication
is raised as a worker error.
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .security import SecurityError, canonical_json, validate_identifier, workspace_path

from .qc_execution import (
    LocalQcError,
    LocalQcValidationError,
    MAX_DURATION_MS,
    MAX_INPUT_BYTES,
    MIN_DURATION_MS,
)


QC_SCHEMA_VERSION = 2
IMPLEMENTATION_VERSION = "local-ffmpeg-qc-v2"
PROVIDER = "local_ffmpeg_qc"
TIMING_SOURCE = "ffprobe"

# Keep the names simple so tests and an operator can shorten them for a
# deterministic timeout check.  The public behaviour remains bounded even
# when a media tool emits a large diagnostic stream.
FFPROBE_TIMEOUT_SECONDS = 30
FFMPEG_TIMEOUT_SECONDS = 5 * 60
CANCEL_POLL_SECONDS = 0.1
MAX_PROCESS_OUTPUT_BYTES = 256 * 1024
_PROCESS_CLEANUP_TIMEOUT_SECONDS = 1.0
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = MAX_METADATA_BYTES
SILENCE_NOISE_DB = "-50dB"
SILENCE_DURATION_SECONDS = 0.25
SILENCE_DURATION_MS = 250
SILENCE_MIN_WINDOW_SECONDS = 0.001
SILENCE_COVERAGE_TOLERANCE_SECONDS = 0.001
DURATION_TOLERANCE_MS = 250
MAX_CACHE_KEY_CHARS = 256
LOUDNESS_MIN_LUFS = -24.0
LOUDNESS_MAX_LUFS = -10.0
TRUE_PEAK_MAX_DBFS = -1.0
BLACK_MIN_DURATION_SECONDS = 0.5
BLACK_PIXEL_THRESHOLD = 0.10
BLACK_PICTURE_THRESHOLD = 0.98
LONG_STATIC_MIN_DURATION_SECONDS = 1.0
LONG_STATIC_NOISE_DB = "-60dB"

_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_VARIANTS = {"clean", "captioned"}
_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
_SILENCE_END_RE = re.compile(
    r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*silence_duration:\s*([0-9]+(?:\.[0-9]+)?)"
)
_METRIC_NUMBER_PATTERN = r"([+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)|inf|nan))"
_LOUDNESS_I_RE = re.compile(
    rf"^\s*I:\s*{_METRIC_NUMBER_PATTERN}\s+LUFS\s*$", re.IGNORECASE | re.MULTILINE
)
_LOUDNESS_LRA_RE = re.compile(
    rf"^\s*LRA:\s*{_METRIC_NUMBER_PATTERN}\s+LU\s*$", re.IGNORECASE | re.MULTILINE
)
_TRUE_PEAK_RE = re.compile(
    rf"^\s*Peak:\s*{_METRIC_NUMBER_PATTERN}\s+dBFS\s*$", re.IGNORECASE | re.MULTILINE
)
_BLACK_START_RE = re.compile(r"black_start:\s*([0-9]+(?:\.[0-9]+)?)")
_BLACK_END_RE = re.compile(
    r"black_end:\s*([0-9]+(?:\.[0-9]+)?)\s+black_duration:\s*([0-9]+(?:\.[0-9]+)?)"
)
_FREEZE_START_RE = re.compile(
    r"(?:lavfi\.freezedetect\.)?freeze_start:\s*([0-9]+(?:\.[0-9]+)?)"
)
_FREEZE_DURATION_RE = re.compile(
    r"(?:lavfi\.freezedetect\.)?freeze_duration:\s*([0-9]+(?:\.[0-9]+)?)"
)
_FREEZE_END_RE = re.compile(
    r"(?:lavfi\.freezedetect\.)?freeze_end:\s*([0-9]+(?:\.[0-9]+)?)"
)
_FILE_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "technical-qc.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)
_QC_CHECK_KEYS = frozenset(
    {
        "probe_success",
        "container_mp4",
        "streams_exact",
        "video_codec",
        "video_pixel_format",
        "audio_codec",
        "audio_format",
        "duration",
        "full_decode",
        "audio_not_silent",
        "audio_loudness",
        "audio_true_peak",
        "black_frames",
    }
)
_TOOL_IDENTITY_LOCK = threading.Lock()
_TOOL_IDENTITY_CACHE: dict[tuple[str, int, int], dict[str, str]] = {}


class QcError(LocalQcError):
    """Safe, bounded errors raised by the local technical QC worker."""

    def __init__(self, message: str, *, code: str = "local_qc_failed"):
        super().__init__(message, code=code)
        self.error_code = code
        self.public_message = message


class QcValidationError(QcError):
    """An invalid worker argument or a provenance/boundary mismatch."""


class QcToolError(QcError):
    """A local ffmpeg/ffprobe executable or process failure."""


@dataclass(frozen=True)
class _ProcessResult:
    return_code: int
    stdout: bytes
    stderr: bytes


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise QcError("QC input or output could not be read", code="io_error") from exc
    return digest.hexdigest().upper()


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _strict_hash(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise QcValidationError(f"{label} must be a SHA-256 digest", code="invalid_provenance")
    return value.upper()


def _strict_cache_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_CACHE_KEY_CHARS
        or _CACHE_KEY_RE.fullmatch(value) is None
    ):
        raise QcValidationError("cache_key is invalid", code="invalid_cache_key")
    return value


def _strict_id(value: Any, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise QcValidationError(f"{label} is invalid", code="invalid_provenance")
    return value


def _strict_variant(value: Any) -> str:
    if not isinstance(value, str) or value not in _VARIANTS:
        raise QcValidationError("variant must be clean or captioned")
    return value


def _strict_duration(value: Any, *, label: str = "expected_duration_ms") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_DURATION_MS
        or value > MAX_DURATION_MS
    ):
        raise QcValidationError(
            f"{label} must be an integer between {MIN_DURATION_MS} and {MAX_DURATION_MS}"
        )
    return value


def _strict_bytes(value: Any, *, label: str = "input_bytes") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > MAX_INPUT_BYTES
    ):
        raise QcValidationError(f"{label} is invalid")
    return value


def _find_tool(name: str, explicit: str | Path | None = None) -> str:
    if explicit is not None:
        candidate = Path(explicit)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable") from exc
        if not resolved.is_file() or resolved.is_dir():
            raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable")
        return str(resolved)
    found = shutil.which(name)
    if not found:
        raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable")
    try:
        resolved = Path(found).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable") from exc
    if not resolved.is_file() or resolved.is_dir():
        raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable")
    return str(resolved)


def _cancelled(cancel_event: Any | None) -> bool:
    checker = getattr(cancel_event, "is_set", None)
    return bool(callable(checker) and checker())


def _register_process(cancel_event: Any | None, process: subprocess.Popen[bytes]) -> bool:
    if cancel_event is None:
        return False
    register = getattr(cancel_event, "register_process", None)
    if not callable(register):
        return False
    register(process)
    return True


def _unregister_process(cancel_event: Any | None, process: subprocess.Popen[bytes]) -> None:
    if cancel_event is None:
        return
    unregister = getattr(cancel_event, "unregister_process", None)
    if callable(unregister):
        try:
            unregister(process)
        except Exception:
            # Registry cleanup must not mask the media result/error.
            pass


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    raiser = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(raiser):
        raiser()
    elif _cancelled(cancel_event):
        raise QcError(
            "The Studio process stopped before QC completed.",
            code="process_interrupted",
        )


def _tool_identity(
    name: str,
    explicit: str | Path | None = None,
    *,
    cancel_event: Any | None = None,
) -> dict[str, str]:
    _raise_if_cancelled(cancel_event)
    executable = _find_tool(name, explicit)
    resolved = Path(executable).resolve(strict=True)
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise QcToolError(f"{name} executable is unavailable", code="local_ffmpeg_unavailable") from exc
    cache_key = (str(resolved), stat.st_size, stat.st_mtime_ns)
    # Size and mtime are only a lookup hint.  Hash before accepting a cached
    # identity so an in-place, same-size/same-mtime executable replacement
    # cannot inherit the previous binary identity.
    _raise_if_cancelled(cancel_event)
    digest = _sha256_file(resolved)
    # Read the digest again to avoid accepting a partially replaced binary
    # when the filesystem preserves size and mtime.  A stable replacement will
    # produce a different digest and therefore miss the old cache entry.
    if _sha256_file(resolved) != digest:
        raise QcToolError(f"{name} executable changed during identity check", code="local_ffmpeg_unavailable")
    _raise_if_cancelled(cancel_event)
    with _TOOL_IDENTITY_LOCK:
        cached = _TOOL_IDENTITY_CACHE.get(cache_key)
    if cached is not None and cached.get("sha256") == digest:
        return dict(cached)
    version_result = _bounded_process(
        [str(resolved), "-version"],
        cwd=Path.cwd(),
        timeout=FFPROBE_TIMEOUT_SECONDS,
        label=f"{name} version",
        cancel_event=cancel_event,
    )
    if version_result.return_code != 0:
        raise QcToolError(f"{name} version could not be determined", code="local_ffmpeg_unavailable")
    try:
        version = version_result.stdout.decode("utf-8", errors="replace").splitlines()[0].strip()
    except IndexError as exc:
        raise QcToolError(f"{name} version could not be determined", code="local_ffmpeg_unavailable") from exc
    if not version or len(version) > 512:
        raise QcToolError(f"{name} version could not be determined", code="local_ffmpeg_unavailable")
    identity = {
        "path": str(resolved),
        "version": version,
        "sha256": digest,
    }
    with _TOOL_IDENTITY_LOCK:
        _TOOL_IDENTITY_CACHE[cache_key] = dict(identity)
    return identity


def resolve_tool_identity(
    *,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, dict[str, str]]:
    """Return executable path, version, and binary hash used by QC."""

    return {
        "ffmpeg": _tool_identity("ffmpeg", ffmpeg, cancel_event=cancel_event),
        "ffprobe": _tool_identity("ffprobe", ffprobe, cancel_event=cancel_event),
    }


def _normalize_tool_identity(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise QcValidationError(f"{label} is invalid", code="invalid_tool_identity")
    path, version, digest = value.get("path"), value.get("version"), value.get("sha256")
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise QcValidationError(f"{label}.path is invalid", code="invalid_tool_identity")
    if not isinstance(version, str) or not version or len(version) > 512:
        raise QcValidationError(f"{label}.version is invalid", code="invalid_tool_identity")
    return {"path": path, "version": version, "sha256": _strict_hash(digest, label=f"{label}.sha256")}


def _qc_policy() -> dict[str, Any]:
    return {
        "policy_version": "technical-qc-mp4-v2",
        "container": "mp4",
        "stream_layout": "exactly_one_video_and_one_audio_no_extra_streams",
        "video_codec": "h264",
        "video_pixel_format": "yuv420p",
        "audio_codec": "aac",
        "audio_sample_rate": 48_000,
        "audio_channels": 2,
        "duration_tolerance_ms": DURATION_TOLERANCE_MS,
        "full_decode": "ffmpeg_map_all_to_null",
        "silence_detection": {
            "noise_db": SILENCE_NOISE_DB,
            "maximum_window_seconds": SILENCE_DURATION_SECONDS,
            "minimum_window_seconds": SILENCE_MIN_WINDOW_SECONDS,
            "short_media_rule": "min(maximum_window,media_duration/2)",
            "gap_tolerance_seconds": SILENCE_COVERAGE_TOLERANCE_SECONDS,
        },
        "audio_loudness": {
            "filter": "ebur128_peak_true_framelog_quiet",
            "integrated_lufs_min": LOUDNESS_MIN_LUFS,
            "integrated_lufs_max": LOUDNESS_MAX_LUFS,
            "true_peak_max_dbfs": TRUE_PEAK_MAX_DBFS,
        },
        "black_frames": {
            "minimum_duration_seconds": BLACK_MIN_DURATION_SECONDS,
            "pixel_threshold": BLACK_PIXEL_THRESHOLD,
            "picture_threshold": BLACK_PICTURE_THRESHOLD,
            "verdict": "hard_fail",
        },
        "long_static": {
            "minimum_duration_seconds": LONG_STATIC_MIN_DURATION_SECONDS,
            "noise_db": LONG_STATIC_NOISE_DB,
            "verdict": "advisory_only",
        },
    }


def qc_cache_key(
    *,
    production_id: str,
    run_id: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    tool_identity: Mapping[str, Mapping[str, Any]] | None = None,
    cancel_event: Any | None = None,
) -> str:
    """Derive a run-local cache key from immutable assembly provenance."""

    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    _strict_id(assembly_attempt_id, label="assembly_attempt_id", pattern=_ATTEMPT_ID_RE)
    _strict_id(assembly_artifact_id, label="assembly_artifact_id", pattern=_ARTIFACT_ID_RE)
    variant = _strict_variant(variant)
    input_sha256 = _strict_hash(input_sha256, label="input_sha256")
    if (
        isinstance(input_bytes, bool)
        or not isinstance(input_bytes, int)
        or input_bytes <= 0
        or input_bytes > MAX_INPUT_BYTES
    ):
        raise QcValidationError("input_bytes is invalid")
    expected_duration_ms = _strict_duration(expected_duration_ms)
    if tool_identity is None:
        resolved_identity = resolve_tool_identity(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            cancel_event=cancel_event,
        )
    else:
        if ffmpeg is not None or ffprobe is not None:
            raise QcValidationError("tool identity was provided twice", code="invalid_tool_identity")
        if not isinstance(tool_identity, Mapping):
            raise QcValidationError("tool_identity is invalid", code="invalid_tool_identity")
        resolved_identity = {
            "ffmpeg": _normalize_tool_identity(tool_identity.get("ffmpeg"), label="ffmpeg_identity"),
            "ffprobe": _normalize_tool_identity(tool_identity.get("ffprobe"), label="ffprobe_identity"),
        }
    identity = {
        "schema_version": QC_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "assembly_attempt_id": assembly_attempt_id,
        "assembly_artifact_id": assembly_artifact_id,
        "variant": variant,
        "input": {"sha256": input_sha256, "bytes": input_bytes},
        "expected_duration_ms": expected_duration_ms,
        "policy": _qc_policy(),
        "tool_identity": resolved_identity,
    }
    return _sha256_bytes(canonical_json(identity).encode("utf-8"))


def _has_symlink_component(workspace: Path, candidate: str | Path) -> bool:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    lexical = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input_file(workspace: Path, value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise QcValidationError("input_path must be a workspace path", code="invalid_input_path")
    supplied = Path(value)
    lexical = supplied if supplied.is_absolute() else workspace / supplied
    if _has_symlink_component(workspace, lexical):
        raise QcValidationError("input_path must not contain symlinks", code="unsafe_input_path")
    try:
        path = workspace_path(workspace, lexical, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise QcValidationError("input_path is outside the workspace", code="unsafe_input_path") from exc
    if path.is_symlink() or not path.is_file():
        raise QcValidationError("input_path must be a regular file", code="invalid_input_path")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise QcValidationError("input_path is unavailable", code="invalid_input_path") from exc
    if size <= 0 or size > MAX_INPUT_BYTES:
        raise QcValidationError("input_path has an unsupported size", code="invalid_input_path")
    return path


def _safe_qc_root(workspace: Path, run_id: str, cache_key: str) -> Path:
    root = workspace.resolve(strict=True)
    lexical_root = root / "outputs" / "studio" / "runs"
    lexical_run = lexical_root / run_id
    lexical_qc = lexical_run / "qc"
    lexical_cache = lexical_qc / cache_key
    if any(
        _has_symlink_component(root, candidate)
        for candidate in (lexical_root, lexical_run, lexical_qc, lexical_cache)
    ):
        raise QcValidationError("QC output path must not contain symlinks", code="unsafe_output_path")
    try:
        output_root = workspace_path(root, lexical_root, must_exist=False)
        run_root = workspace_path(root, lexical_run, must_exist=False)
        qc_root = workspace_path(root, lexical_qc, must_exist=False)
        cache_root = workspace_path(root, lexical_cache, must_exist=False)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise QcValidationError("QC output path is outside the workspace", code="unsafe_output_path") from exc
    for directory in (output_root, run_root, qc_root):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise QcValidationError("QC output path is not a directory", code="unsafe_output_path")
    if cache_root.exists() and (cache_root.is_symlink() or not cache_root.is_dir()):
        raise QcValidationError("QC cache path is unsafe", code="unsafe_output_path")
    return cache_root


def _terminate_process_tree(
    process: subprocess.Popen[bytes], *, deadline: float | None = None
) -> None:
    """Use the jobs process-tree terminator without changing worker callers."""

    pid = getattr(process, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return
    try:
        if process.poll() is not None:
            return
    except Exception:
        # A broken process adapter should not prevent the PID-based fallback
        # from making a best-effort shutdown attempt.
        pass
    try:
        from .jobs import _terminate_process_tree as terminate_process_tree

        terminate_process_tree(pid, deadline=deadline)
    except Exception:
        # Preserve the original worker error even if teardown itself fails.
        pass


def _bounded_process(
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    label: str,
    cancel_event: Any | None = None,
) -> _ProcessResult:
    """Run one local tool with shell disabled and bounded diagnostics.

    Both pipes are drained concurrently while the process is alive.  This is
    important for ffmpeg diagnostics: waiting for a child before reading its
    pipes can deadlock once either OS pipe reaches capacity.  A cancellation
    context may register the exact process so Studio shutdown can terminate it
    immediately rather than waiting for the media timeout.
    """

    _raise_if_cancelled(cancel_event)
    process_options: dict[str, Any] = {}
    if os.name == "nt":
        process_options["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        process_options["start_new_session"] = True
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    reader_failures: list[BaseException] = []
    reader_failed = threading.Event()

    def raise_reader_failure() -> None:
        if reader_failures:
            raise reader_failures[0]

    def drain(stream: Any, buffer: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                remaining = MAX_PROCESS_OUTPUT_BYTES + 1 - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
        except (OSError, ValueError):
            # Teardown may close a pipe while the reader wakes up.  The
            # process result/error remains authoritative.
            return
        except BaseException as exc:
            # Do not leave a child blocked on a full pipe when a reader dies.
            reader_failures.append(exc)
            reader_failed.set()
            return

    process: subprocess.Popen[bytes] | None = None
    readers: list[threading.Thread] = []
    registered = False
    return_code = -1
    shutdown_deadline: float | None = None

    def terminate_active_process() -> None:
        nonlocal shutdown_deadline
        if process is None:
            return
        if shutdown_deadline is None:
            shutdown_deadline = time.monotonic() + _PROCESS_CLEANUP_TIMEOUT_SECONDS
        _terminate_process_tree(process, deadline=shutdown_deadline)

    try:
        process = subprocess.Popen(
            list(arguments),
            cwd=str(cwd),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **process_options,
        )
        registered = _register_process(cancel_event, process)
        # A shutdown can race with Popen.  Register first and check again so
        # the exact process is killed instead of becoming an orphan.
        _raise_if_cancelled(cancel_event)
        if process.stdout is None or process.stderr is None:
            terminate_active_process()
            raise QcToolError(f"{label} did not expose output pipes", code="local_ffmpeg_failed")
        readers = [
            threading.Thread(
                target=drain,
                args=(process.stdout, stdout_buffer),
                name=f"qc-{label}-stdout",
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, stderr_buffer),
                name=f"qc-{label}-stderr",
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + timeout
        try:
            while True:
                _raise_if_cancelled(cancel_event)
                if reader_failed.is_set():
                    raise_reader_failure()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    terminate_active_process()
                    raise QcToolError(
                        f"{label} timed out", code="local_ffmpeg_qc_timeout"
                    )
                try:
                    return_code = process.wait(timeout=min(CANCEL_POLL_SECONDS, remaining))
                    if reader_failed.is_set():
                        raise_reader_failure()
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            terminate_active_process()
            raise
        finally:
            # Give both readers one shared, short budget.  Per-reader 10-second
            # joins could exceed the worker shutdown bound before termination.
            reader_deadline = shutdown_deadline
            if reader_deadline is None:
                reader_deadline = time.monotonic() + _PROCESS_CLEANUP_TIMEOUT_SECONDS
            for reader in readers:
                join_remaining = reader_deadline - time.monotonic()
                if join_remaining <= 0:
                    break
                reader.join(timeout=join_remaining)
            if any(reader.is_alive() for reader in readers):
                terminate_active_process()
                for reader in readers:
                    join_remaining = reader_deadline - time.monotonic()
                    if join_remaining <= 0:
                        break
                    reader.join(timeout=join_remaining)
    except FileNotFoundError as exc:
        raise QcToolError(
            f"{label} executable is unavailable", code="local_ffmpeg_unavailable"
        ) from exc
    except QcError:
        terminate_active_process()
        raise
    except OSError as exc:
        raise QcToolError(f"{label} could not be started", code="local_ffmpeg_failed") from exc
    except BaseException:
        terminate_active_process()
        raise
    finally:
        if process is not None:
            # Covers failures before the polling loop (reader construction or
            # thread start) and keeps unexpected exceptions fail-closed.
            terminate_active_process()
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if registered:
                _unregister_process(cancel_event, process)
    stdout = bytes(stdout_buffer)
    stderr = bytes(stderr_buffer)
    if len(stdout) > MAX_PROCESS_OUTPUT_BYTES or len(stderr) > MAX_PROCESS_OUTPUT_BYTES:
        raise QcToolError(f"{label} produced excessive diagnostics", code="local_ffmpeg_failed")
    # A nonzero media-tool result is data for technical verdict construction;
    # only inability to run, timeout, cancellation, or unsafe I/O is a worker
    # error.  This preserves analysis-success/technical-fail separation.
    return _ProcessResult(return_code=return_code, stdout=stdout, stderr=stderr)


def _probe_argv(input_name: str) -> list[str]:
    return [
        "{ffprobe}",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-show_entries",
        "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration",
        "-of",
        "json",
        input_name,
    ]


def _run_probe(
    ffprobe: str,
    *,
    cwd: Path,
    cancel_event: Any | None = None,
) -> tuple[dict[str, Any], _ProcessResult, str | None]:
    _raise_if_cancelled(cancel_event)
    argv = _probe_argv("assembly-master.mp4")
    argv[0] = ffprobe
    result = _bounded_process(
        argv,
        cwd=cwd,
        timeout=FFPROBE_TIMEOUT_SECONDS,
        label="ffprobe",
        cancel_event=cancel_event,
    )
    try:
        decoded = result.stdout.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, result, "ffprobe_returned_invalid_json"
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        return {}, result, "ffprobe_returned_invalid_media_description"
    return value, result, None if result.return_code == 0 else "ffprobe_failed"


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _duration_seconds(probe: Mapping[str, Any]) -> float | None:
    format_data = probe.get("format")
    if isinstance(format_data, Mapping):
        duration = _finite_float(format_data.get("duration"))
        if duration is not None and duration > 0:
            return duration
    streams = probe.get("streams")
    if isinstance(streams, list):
        durations = [
            _finite_float(item.get("duration"))
            for item in streams
            if isinstance(item, Mapping)
        ]
        valid = [value for value in durations if value is not None and value > 0]
        if valid:
            return max(valid)
    return None


def _duration_ms(probe: Mapping[str, Any]) -> int | None:
    duration = _duration_seconds(probe)
    if duration is None:
        return None
    return int(round(duration * 1000))


def _duration_ms_value(value: Any) -> int | None:
    duration = _finite_float(value)
    if duration is None or duration <= 0:
        return None
    return int(round(duration * 1000))


def _duration_components_ms(
    probe: Mapping[str, Any],
    streams: Sequence[Mapping[str, Any]],
) -> tuple[int | None, dict[str, int | None]]:
    format_data = probe.get("format")
    container_duration = (
        _duration_ms_value(format_data.get("duration"))
        if isinstance(format_data, Mapping)
        else None
    )
    video_duration = next(
        (
            _duration_ms_value(stream.get("duration"))
            for stream in streams
            if stream.get("codec_type") == "video"
        ),
        None,
    )
    audio_duration = next(
        (
            _duration_ms_value(stream.get("duration"))
            for stream in streams
            if stream.get("codec_type") == "audio"
        ),
        None,
    )
    components: dict[str, int | None] = {
        "container": container_duration,
        "video": video_duration,
        "audio": audio_duration,
    }
    available = [value for value in components.values() if isinstance(value, int)]
    measured = container_duration if container_duration is not None else max(available, default=None)
    return measured, components


def _streams(probe: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = probe.get("streams")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _first_stream(streams: Sequence[Mapping[str, Any]], codec_type: str) -> Mapping[str, Any] | None:
    return next((item for item in streams if item.get("codec_type") == codec_type), None)


def _stream_fact(stream: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "index",
        "codec_type",
        "codec_name",
        "width",
        "height",
        "pix_fmt",
        "sample_rate",
        "channels",
        "duration",
    )
    return {field: stream.get(field) for field in fields if field in stream}


def _check(
    passed: bool,
    *,
    expected: Any = None,
    observed: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"passed": bool(passed), "status": "pass" if passed else "fail"}
    if expected is not None:
        value["expected"] = expected
    if observed is not None:
        value["observed"] = observed
    if reason is not None:
        value["reason"] = reason
    return value


def _technical_verdict(checks: Mapping[str, Any]) -> str:
    return "pass" if set(checks) == set(_QC_CHECK_KEYS) and all(
        isinstance(value, Mapping) and value.get("passed") is True
        for value in checks.values()
    ) else "fail"


def _decode_argv(output_name: str) -> list[str]:
    return [
        "{ffmpeg}",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-xerror",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "assembly-master.mp4",
        "-map",
        "0",
        "-f",
        "null",
        output_name,
    ]


def _silence_argv(
    output_name: str,
    *,
    window_seconds: float = SILENCE_DURATION_SECONDS,
) -> list[str]:
    window_seconds = max(
        SILENCE_MIN_WINDOW_SECONDS,
        min(SILENCE_DURATION_SECONDS, float(window_seconds)),
    )
    return [
        "{ffmpeg}",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "assembly-master.mp4",
        "-map",
        "0:a:0",
        "-af",
        f"silencedetect=n={SILENCE_NOISE_DB}:d={window_seconds:g}",
        "-f",
        "null",
        output_name,
    ]


def _loudness_argv(output_name: str) -> list[str]:
    return [
        "{ffmpeg}",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "assembly-master.mp4",
        "-map",
        "0:a:0",
        "-af",
        "ebur128=peak=true:framelog=quiet",
        "-f",
        "null",
        output_name,
    ]


def _blackdetect_argv(output_name: str) -> list[str]:
    return [
        "{ffmpeg}",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "assembly-master.mp4",
        "-map",
        "0:v:0",
        "-vf",
        (
            f"blackdetect=d={BLACK_MIN_DURATION_SECONDS:g}:"
            f"pic_th={BLACK_PICTURE_THRESHOLD:g}:pix_th={BLACK_PIXEL_THRESHOLD:g}"
        ),
        "-an",
        "-f",
        "null",
        output_name,
    ]


def _freezedetect_argv(output_name: str) -> list[str]:
    return [
        "{ffmpeg}",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        "assembly-master.mp4",
        "-map",
        "0:v:0",
        "-vf",
        f"freezedetect=n={LONG_STATIC_NOISE_DB}:d={LONG_STATIC_MIN_DURATION_SECONDS:g}",
        "-an",
        "-f",
        "null",
        output_name,
    ]


def _run_ffmpeg(
    ffmpeg: str,
    argv_template: list[str],
    *,
    cwd: Path,
    label: str,
    cancel_event: Any | None = None,
) -> _ProcessResult:
    _raise_if_cancelled(cancel_event)
    output_name = "NUL" if os.name == "nt" else os.devnull
    argv = [ffmpeg if value == "{ffmpeg}" else output_name if value == "{output}" else value for value in argv_template]
    return _bounded_process(
        argv,
        cwd=cwd,
        timeout=FFMPEG_TIMEOUT_SECONDS,
        label=label,
        cancel_event=cancel_event,
    )


def _silence_window_seconds(duration_ms: int | None) -> float:
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return SILENCE_DURATION_SECONDS
    return max(
        SILENCE_MIN_WINDOW_SECONDS,
        min(SILENCE_DURATION_SECONDS, duration_ms / 1000 / 2),
    )


def _silence_facts(
    result: _ProcessResult,
    *,
    duration_ms: int | None,
    window_seconds: float | None = None,
) -> dict[str, Any]:
    text = result.stderr.decode("utf-8", errors="replace")
    starts = [float(match.group(1)) for match in _SILENCE_START_RE.finditer(text)]
    ends = [
        {"end_seconds": float(match.group(1)), "duration_seconds": float(match.group(2))}
        for match in _SILENCE_END_RE.finditer(text)
    ]
    duration_seconds = duration_ms / 1000 if duration_ms is not None else None
    window_seconds = (
        _silence_window_seconds(duration_ms)
        if window_seconds is None
        else max(
            SILENCE_MIN_WINDOW_SECONDS,
            min(SILENCE_DURATION_SECONDS, float(window_seconds)),
        )
    )
    intervals: list[tuple[float, float]] = []
    if duration_seconds is not None:
        # silencedetect reports a start event and then an end event whose
        # duration lets us reconstruct the exact interval.  Do not infer
        # whole-track silence merely from the first start and last end: a
        # spoken interval between leading and trailing silence must remain a
        # gap in the coverage calculation.
        for index, event in enumerate(ends):
            inferred_start = max(0.0, event["end_seconds"] - event["duration_seconds"])
            start = starts[index] if index < len(starts) else inferred_start
            intervals.append((max(0.0, min(start, event["end_seconds"])), event["end_seconds"]))
        if len(starts) > len(ends):
            # A final silence can remain open at EOF, so close each unmatched
            # start at the measured media duration.
            intervals.extend(
                (max(0.0, start), duration_seconds) for start in starts[len(ends) :]
            )
        clipped = [
            (max(0.0, start), min(duration_seconds, end))
            for start, end in intervals
            if end > start
        ]
        clipped.sort()
        merged: list[list[float]] = []
        for start, end in clipped:
            if not merged or start > merged[-1][1] + SILENCE_COVERAGE_TOLERANCE_SECONDS:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        intervals = [(start, end) for start, end in merged]
        covers_full_duration = (
            bool(intervals)
            and intervals[0][0] <= SILENCE_COVERAGE_TOLERANCE_SECONDS
            and intervals[-1][1] >= duration_seconds - SILENCE_COVERAGE_TOLERANCE_SECONDS
        )
        if covers_full_duration:
            covers_full_duration = all(
                next_start <= current_end + SILENCE_COVERAGE_TOLERANCE_SECONDS
                for (_, current_end), (next_start, _) in zip(intervals, intervals[1:])
            )
    else:
        covers_full_duration = False
    all_silent = bool(result.return_code == 0 and covers_full_duration)
    return {
        "noise_db": SILENCE_NOISE_DB,
        "duration_seconds": round(window_seconds, 6),
        "return_code": result.return_code,
        "silence_start_seconds": starts,
        "silence_end_events": ends,
        "silence_intervals_seconds": [
            {"start": start, "end": end} for start, end in intervals
        ],
        "covers_full_duration": covers_full_duration,
        "all_silent": all_silent,
        "stderr_line_count": len(text.splitlines()),
    }


def _last_finite_metric(
    pattern: re.Pattern[str], text: str
) -> tuple[float | None, str | None]:
    matches = pattern.findall(text)
    if not matches:
        return None, None
    raw = matches[-1]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, raw
    return (round(value, 3), raw) if math.isfinite(value) else (None, raw)


def _loudness_facts(result: _ProcessResult) -> dict[str, Any]:
    text = result.stderr.decode("utf-8", errors="replace")
    integrated_lufs, integrated_raw = _last_finite_metric(_LOUDNESS_I_RE, text)
    loudness_range_lu, range_raw = _last_finite_metric(_LOUDNESS_LRA_RE, text)
    true_peak_dbfs, peak_raw = _last_finite_metric(_TRUE_PEAK_RE, text)
    measurements_present = all(
        value is not None for value in (integrated_raw, range_raw, peak_raw)
    )
    finite_measurements = all(
        value is not None
        for value in (integrated_lufs, loudness_range_lu, true_peak_dbfs)
    )
    return {
        "filter": "ebur128",
        "return_code": result.return_code,
        "analysis_complete": bool(result.return_code == 0 and measurements_present),
        "finite_measurements": finite_measurements,
        "integrated_lufs": integrated_lufs,
        "integrated_lufs_raw": integrated_raw,
        "loudness_range_lu": loudness_range_lu,
        "loudness_range_lu_raw": range_raw,
        "true_peak_dbfs": true_peak_dbfs,
        "true_peak_dbfs_raw": peak_raw,
        "stderr_line_count": len(text.splitlines()),
    }


def _black_facts(
    result: _ProcessResult,
    *,
    duration_ms: int | None,
) -> dict[str, Any]:
    text = result.stderr.decode("utf-8", errors="replace")
    starts = [float(match.group(1)) for match in _BLACK_START_RE.finditer(text)]
    ends = [
        {"end": float(match.group(1)), "duration": float(match.group(2))}
        for match in _BLACK_END_RE.finditer(text)
    ]
    duration_seconds = duration_ms / 1000 if isinstance(duration_ms, int) else None
    unresolved_open_interval = bool(len(starts) > len(ends) and duration_seconds is None)
    intervals: list[tuple[float, float]] = []
    for index, event in enumerate(ends):
        inferred_start = max(0.0, event["end"] - event["duration"])
        start = starts[index] if index < len(starts) else inferred_start
        intervals.append((max(0.0, min(start, event["end"])), event["end"]))
    if duration_seconds is not None and len(starts) > len(ends):
        intervals.extend(
            (max(0.0, start), duration_seconds) for start in starts[len(ends) :]
        )
    normalized: list[dict[str, float]] = []
    for start, end in sorted(intervals):
        if duration_seconds is not None:
            end = min(end, duration_seconds)
        if end <= start:
            continue
        normalized.append(
            {
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(end - start, 6),
            }
        )
    detected = bool(
        result.return_code == 0
        and (
            unresolved_open_interval
            or any(
                item["duration"] + SILENCE_COVERAGE_TOLERANCE_SECONDS
                >= BLACK_MIN_DURATION_SECONDS
                for item in normalized
            )
        )
    )
    return {
        "filter": "blackdetect",
        "return_code": result.return_code,
        "analysis_complete": bool(result.return_code == 0 and not unresolved_open_interval),
        "unresolved_open_interval": unresolved_open_interval,
        "minimum_duration_seconds": BLACK_MIN_DURATION_SECONDS,
        "pixel_threshold": BLACK_PIXEL_THRESHOLD,
        "picture_threshold": BLACK_PICTURE_THRESHOLD,
        "intervals_seconds": normalized,
        "interval_count": len(normalized),
        "max_duration_seconds": max(
            (item["duration"] for item in normalized), default=0.0
        ),
        "detected": detected,
        "stderr_line_count": len(text.splitlines()),
    }


def _long_static_facts(
    result: _ProcessResult,
    *,
    duration_ms: int | None,
) -> dict[str, Any]:
    text = result.stderr.decode("utf-8", errors="replace")
    starts = [float(match.group(1)) for match in _FREEZE_START_RE.finditer(text)]
    durations = [float(match.group(1)) for match in _FREEZE_DURATION_RE.finditer(text)]
    ends = [float(match.group(1)) for match in _FREEZE_END_RE.finditer(text)]
    duration_seconds = duration_ms / 1000 if isinstance(duration_ms, int) else None
    unresolved_open_interval = bool(len(starts) > len(ends) and duration_seconds is None)
    intervals: list[tuple[float, float]] = []
    for index, end in enumerate(ends):
        event_duration = durations[index] if index < len(durations) else None
        inferred_start = max(0.0, end - event_duration) if event_duration is not None else end
        start = starts[index] if index < len(starts) else inferred_start
        intervals.append((max(0.0, min(start, end)), end))
    if duration_seconds is not None and len(starts) > len(ends):
        intervals.extend(
            (max(0.0, start), duration_seconds) for start in starts[len(ends) :]
        )
    normalized: list[dict[str, float]] = []
    for start, end in sorted(intervals):
        if duration_seconds is not None:
            end = min(end, duration_seconds)
        if end <= start:
            continue
        normalized.append(
            {
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(end - start, 6),
            }
        )
    warning = bool(
        result.return_code == 0
        and (
            unresolved_open_interval
            or any(
                item["duration"] + SILENCE_COVERAGE_TOLERANCE_SECONDS
                >= LONG_STATIC_MIN_DURATION_SECONDS
                for item in normalized
            )
        )
    )
    return {
        "filter": "freezedetect",
        "return_code": result.return_code,
        "analysis_complete": bool(result.return_code == 0 and not unresolved_open_interval),
        "unresolved_open_interval": unresolved_open_interval,
        "minimum_duration_seconds": LONG_STATIC_MIN_DURATION_SECONDS,
        "noise_db": LONG_STATIC_NOISE_DB,
        "advisory_only": True,
        "warning": warning,
        "warning_reason": "long_static_interval_detected" if warning else None,
        "intervals_seconds": normalized,
        "interval_count": len(normalized),
        "max_duration_seconds": max(
            (item["duration"] for item in normalized), default=0.0
        ),
        "stderr_line_count": len(text.splitlines()),
    }


def _analyse(
    ffmpeg: str,
    ffprobe: str,
    *,
    stage: Path,
    cancel_event: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run probe/decode plus silence, level, black, and static analysis."""

    _raise_if_cancelled(cancel_event)
    probe, probe_result, probe_error = _run_probe(
        ffprobe,
        cwd=stage,
        cancel_event=cancel_event,
    )
    streams = _streams(probe)
    video = _first_stream(streams, "video")
    audio = _first_stream(streams, "audio")
    format_data = probe.get("format") if isinstance(probe.get("format"), Mapping) else {}
    format_name = format_data.get("format_name") if isinstance(format_data, Mapping) else None
    duration_ms, duration_components_ms = _duration_components_ms(probe, streams)
    stream_types = [stream.get("codec_type") for stream in streams]
    exact_stream_layout = (
        len(streams) == 2
        and stream_types.count("video") == 1
        and stream_types.count("audio") == 1
        and all(value in {"video", "audio"} for value in stream_types)
    )
    container_ok = isinstance(format_name, str) and "mp4" in {
        item.strip().casefold() for item in format_name.split(",")
    }
    video_codec = video.get("codec_name") if video else None
    video_pix_fmt = video.get("pix_fmt") if video else None
    audio_codec = audio.get("codec_name") if audio else None
    try:
        sample_rate = int(audio.get("sample_rate")) if audio else None
    except (TypeError, ValueError):
        sample_rate = None
    try:
        channels = int(audio.get("channels")) if audio else None
    except (TypeError, ValueError):
        channels = None

    decode_result = _run_ffmpeg(
        ffmpeg,
        _decode_argv("{output}"),
        cwd=stage,
        label="ffmpeg full decode",
        cancel_event=cancel_event,
    )
    if audio is not None:
        silence_window_seconds = _silence_window_seconds(duration_ms)
        silence_result = _run_ffmpeg(
            ffmpeg,
            _silence_argv("{output}", window_seconds=silence_window_seconds),
            cwd=stage,
            label="ffmpeg silence detection",
            cancel_event=cancel_event,
        )
        silence = _silence_facts(
            silence_result,
            duration_ms=duration_ms,
            window_seconds=silence_window_seconds,
        )
        loudness_result = _run_ffmpeg(
            ffmpeg,
            _loudness_argv("{output}"),
            cwd=stage,
            label="ffmpeg loudness analysis",
            cancel_event=cancel_event,
        )
        loudness = _loudness_facts(loudness_result)
    else:
        silence = {
            "noise_db": SILENCE_NOISE_DB,
            "duration_seconds": _silence_window_seconds(duration_ms),
            "return_code": None,
            "silence_start_seconds": [],
            "silence_end_events": [],
            "all_silent": False,
            "stderr_line_count": 0,
            "reason": "audio_stream_missing",
        }
        loudness = {
            "filter": "ebur128",
            "return_code": None,
            "analysis_complete": False,
            "finite_measurements": False,
            "integrated_lufs": None,
            "integrated_lufs_raw": None,
            "loudness_range_lu": None,
            "loudness_range_lu_raw": None,
            "true_peak_dbfs": None,
            "true_peak_dbfs_raw": None,
            "stderr_line_count": 0,
            "reason": "audio_stream_missing",
        }

    if video is not None:
        black_result = _run_ffmpeg(
            ffmpeg,
            _blackdetect_argv("{output}"),
            cwd=stage,
            label="ffmpeg black frame detection",
            cancel_event=cancel_event,
        )
        black_frames = _black_facts(black_result, duration_ms=duration_ms)
        static_result = _run_ffmpeg(
            ffmpeg,
            _freezedetect_argv("{output}"),
            cwd=stage,
            label="ffmpeg long static detection",
            cancel_event=cancel_event,
        )
        long_static = _long_static_facts(static_result, duration_ms=duration_ms)
    else:
        black_frames = {
            "filter": "blackdetect",
            "return_code": None,
            "analysis_complete": False,
            "unresolved_open_interval": False,
            "minimum_duration_seconds": BLACK_MIN_DURATION_SECONDS,
            "pixel_threshold": BLACK_PIXEL_THRESHOLD,
            "picture_threshold": BLACK_PICTURE_THRESHOLD,
            "intervals_seconds": [],
            "interval_count": 0,
            "max_duration_seconds": 0.0,
            "detected": False,
            "stderr_line_count": 0,
            "reason": "video_stream_missing",
        }
        long_static = {
            "filter": "freezedetect",
            "return_code": None,
            "analysis_complete": False,
            "unresolved_open_interval": False,
            "minimum_duration_seconds": LONG_STATIC_MIN_DURATION_SECONDS,
            "noise_db": LONG_STATIC_NOISE_DB,
            "advisory_only": True,
            "warning": False,
            "warning_reason": None,
            "intervals_seconds": [],
            "interval_count": 0,
            "max_duration_seconds": 0.0,
            "stderr_line_count": 0,
            "reason": "video_stream_missing",
        }

    facts: dict[str, Any] = {
        "container": {
            "format_name": format_name,
            "format": dict(format_data) if isinstance(format_data, Mapping) else None,
        },
        "format_name": format_name,
        "duration_ms": duration_ms,
        "durations_ms": duration_components_ms,
        "stream_count": len(streams),
        "stream_types": stream_types,
        "streams": [_stream_fact(stream) for stream in streams],
        "video": _stream_fact(video) if video is not None else None,
        "audio": _stream_fact(audio) if audio is not None else None,
        "video_codec": video_codec,
        "video_pixel_format": video_pix_fmt,
        "audio_codec": audio_codec,
        "audio_sample_rate": sample_rate,
        "audio_channels": channels,
        "full_decode_return_code": decode_result.return_code,
        "silence": silence,
        "loudness": loudness,
        "black_frames": black_frames,
        "long_static": long_static,
        "probe_return_code": probe_result.return_code,
        "probe_error": probe_error,
    }
    integrated_lufs = loudness.get("integrated_lufs")
    true_peak_dbfs = loudness.get("true_peak_dbfs")
    loudness_ok = bool(
        audio is not None
        and loudness.get("analysis_complete") is True
        and isinstance(integrated_lufs, (int, float))
        and LOUDNESS_MIN_LUFS <= integrated_lufs <= LOUDNESS_MAX_LUFS
    )
    true_peak_ok = bool(
        audio is not None
        and loudness.get("analysis_complete") is True
        and isinstance(true_peak_dbfs, (int, float))
        and true_peak_dbfs <= TRUE_PEAK_MAX_DBFS
    )
    black_frames_ok = bool(
        video is not None
        and black_frames.get("return_code") == 0
        and black_frames.get("analysis_complete") is True
        and black_frames.get("detected") is False
    )
    probe_success = probe_error is None and probe_result.return_code == 0
    checks: dict[str, Any] = {
        "probe_success": _check(
            probe_success,
            expected="return_code=0_and_valid_json",
            observed={"return_code": probe_result.return_code, "error": probe_error},
            reason=None if probe_success else "ffprobe_failed_or_invalid_json",
        ),
        "container_mp4": _check(
            container_ok,
            expected="mp4",
            observed=format_name,
            reason=None if container_ok else "container_is_not_mp4",
        ),
        "streams_exact": _check(
            exact_stream_layout,
            expected="exactly_one_video_one_audio_no_extra",
            observed=stream_types,
            reason=None if exact_stream_layout else "stream_layout_mismatch",
        ),
        "video_codec": _check(
            video_codec == "h264",
            expected="h264",
            observed=video_codec,
            reason=None if video_codec == "h264" else "video_codec_mismatch",
        ),
        "video_pixel_format": _check(
            video_pix_fmt == "yuv420p",
            expected="yuv420p",
            observed=video_pix_fmt,
            reason=None if video_pix_fmt == "yuv420p" else "video_pixel_format_mismatch",
        ),
        "audio_codec": _check(
            audio_codec == "aac",
            expected="aac",
            observed=audio_codec,
            reason=None if audio_codec == "aac" else "audio_codec_mismatch",
        ),
        "audio_format": _check(
            sample_rate == 48_000 and channels == 2,
            expected={"sample_rate": 48_000, "channels": 2},
            observed={"sample_rate": sample_rate, "channels": channels},
            reason=None if sample_rate == 48_000 and channels == 2 else "audio_format_mismatch",
        ),
        "duration": _check(
            False,
            expected={"tolerance_ms": DURATION_TOLERANCE_MS},
            observed=duration_ms,
            reason="duration_not_checked",
        ),
        "full_decode": _check(
            decode_result.return_code == 0,
            expected="return_code=0",
            observed=decode_result.return_code,
            reason=None if decode_result.return_code == 0 else "full_decode_failed",
        ),
        "audio_not_silent": _check(
            audio is not None
            and silence.get("return_code") == 0
            and not bool(silence.get("all_silent")),
            expected={
                "noise_db": SILENCE_NOISE_DB,
                "duration_seconds": silence.get("duration_seconds"),
            },
            observed={
                "audio_stream_present": audio is not None,
                "return_code": silence.get("return_code"),
                "all_silent": silence.get("all_silent"),
            },
            reason=(
                None
                if audio is not None
                and silence.get("return_code") == 0
                and not bool(silence.get("all_silent"))
                else "audio_silence_analysis_failed_or_audio_is_silent"
            ),
        ),
        "audio_loudness": _check(
            loudness_ok,
            expected={
                "integrated_lufs_min": LOUDNESS_MIN_LUFS,
                "integrated_lufs_max": LOUDNESS_MAX_LUFS,
            },
            observed={
                "analysis_complete": loudness.get("analysis_complete"),
                "integrated_lufs": integrated_lufs,
                "integrated_lufs_raw": loudness.get("integrated_lufs_raw"),
            },
            reason=None if loudness_ok else "integrated_loudness_out_of_range_or_unavailable",
        ),
        "audio_true_peak": _check(
            true_peak_ok,
            expected={"true_peak_max_dbfs": TRUE_PEAK_MAX_DBFS},
            observed={
                "analysis_complete": loudness.get("analysis_complete"),
                "true_peak_dbfs": true_peak_dbfs,
                "true_peak_dbfs_raw": loudness.get("true_peak_dbfs_raw"),
            },
            reason=None if true_peak_ok else "true_peak_too_high_or_unavailable",
        ),
        "black_frames": _check(
            black_frames_ok,
            expected={
                "maximum_interval_count": 0,
                "minimum_duration_seconds": BLACK_MIN_DURATION_SECONDS,
                "pixel_threshold": BLACK_PIXEL_THRESHOLD,
                "picture_threshold": BLACK_PICTURE_THRESHOLD,
            },
            observed={
                "video_stream_present": video is not None,
                "return_code": black_frames.get("return_code"),
                "analysis_complete": black_frames.get("analysis_complete"),
                "unresolved_open_interval": black_frames.get("unresolved_open_interval"),
                "interval_count": black_frames.get("interval_count"),
                "max_duration_seconds": black_frames.get("max_duration_seconds"),
            },
            reason=None if black_frames_ok else "black_interval_detected_or_analysis_unavailable",
        ),
    }
    return facts, checks, probe


def _finalize_checks(
    facts: Mapping[str, Any], checks: dict[str, Any], expected_duration_ms: int
) -> dict[str, Any]:
    """Add the request-specific duration comparison to generic media checks."""

    duration_ms = facts.get("duration_ms")
    raw_components = facts.get("durations_ms")
    components = (
        {
            key: raw_components.get(key)
            for key in ("container", "video", "audio")
        }
        if isinstance(raw_components, Mapping)
        else None
    )
    component_values = (
        list(components.values()) if components is not None else []
    )
    numeric_components = [value for value in component_values if isinstance(value, int)]
    duration_pass = bool(
        components is not None
        and all(isinstance(value, int) for value in component_values)
        and all(
            abs(value - expected_duration_ms) <= DURATION_TOLERANCE_MS
            for value in component_values
            if isinstance(value, int)
        )
        and max(numeric_components, default=0) - min(numeric_components, default=0)
        <= DURATION_TOLERANCE_MS
    )
    checks["duration"] = _check(
        duration_pass,
        expected={
            "container_duration_ms": expected_duration_ms,
            "video_duration_ms": expected_duration_ms,
            "audio_duration_ms": expected_duration_ms,
            "tolerance_ms": DURATION_TOLERANCE_MS,
        },
        observed=components if components is not None else duration_ms,
        reason=None if duration_pass else "duration_mismatch_or_unavailable",
    )
    return checks


def _artifact_record(workspace: Path, cache_directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
    if path.is_symlink() or not path.is_file():
        raise QcError(
            f"QC artifact is unavailable: {spec['filename']}", code="invalid_cache"
        )
    try:
        stat = path.stat()
        relative = path.relative_to(workspace.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise QcError("QC artifact could not be inspected", code="invalid_cache") from exc
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
        "version": IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": False,
    }


def _write_atomic(path: Path, data: bytes) -> None:
    if len(data) > MAX_METADATA_BYTES:
        raise QcError("QC metadata is too large", code="metadata_too_large")
    temporary = path.with_name(f".{path.name}.partial")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise QcError("QC metadata could not be published", code="publish_failed") from exc


def _json_document(path: Path, *, maximum: int = MAX_METADATA_BYTES) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_manifest(path: Path) -> dict[str, Any] | None:
    value = _json_document(path)
    if value is None or not isinstance(value.get("manifest_sha256"), str):
        return None
    body = dict(value)
    digest = body.pop("manifest_sha256")
    if _manifest_digest(body) != digest.upper():
        return None
    return value


def _expected_files() -> tuple[dict[str, str], ...]:
    return _FILE_SPECS


def _manifest_file_records(directory: Path) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _expected_files():
        if spec["filename"] == "manifest.json":
            continue
        path = directory / spec["filename"]
        try:
            stat = path.stat()
        except OSError as exc:
            raise QcError(
                f"QC staged artifact is unavailable: {spec['filename']}",
                code="invalid_cache",
            ) from exc
        if path.is_symlink() or not path.is_file():
            raise QcError(
                f"QC staged artifact is unavailable: {spec['filename']}",
                code="invalid_cache",
            )
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    return files


def _technical_document(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    facts: Mapping[str, Any],
    checks: Mapping[str, Any],
) -> dict[str, Any]:
    duration_ms = facts.get("duration_ms")
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "analysis_status": "succeeded",
        "technical_verdict": _technical_verdict(checks),
        "duration_ms": duration_ms if isinstance(duration_ms, int) else 0,
        "assembly_attempt_id": assembly_attempt_id,
        "assembly_artifact_id": assembly_artifact_id,
        "variant": variant,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "expected_duration_ms": expected_duration_ms,
        "checks": dict(checks),
        "media_facts": dict(facts),
        "tool_identity": dict(tool_identity),
        "policy": _qc_policy(),
    }


def _ffprobe_document(
    *,
    input_sha256: str,
    input_bytes: int,
    probe: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "timing_source": TIMING_SOURCE,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "format": probe.get("format"),
        "streams": probe.get("streams"),
        "probe": dict(probe),
    }


def _manifest_body(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    technical: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "assembly_attempt_id": assembly_attempt_id,
        "assembly_artifact_id": assembly_artifact_id,
        "variant": variant,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "expected_duration_ms": expected_duration_ms,
        "tool_identity": dict(tool_identity),
        "policy": _qc_policy(),
        "analysis_status": technical["analysis_status"],
        "technical_verdict": technical["technical_verdict"],
        "duration_ms": technical["duration_ms"],
        "checks": technical["checks"],
        "media_facts": technical["media_facts"],
        "files": {name: dict(record) for name, record in files.items()},
    }


def _canonical_document_matches(path: Path, value: Mapping[str, Any]) -> bool:
    try:
        return path.read_bytes() == (canonical_json(value) + "\n").encode("utf-8")
    except OSError:
        return False


def _validate_cached_output(
    workspace: Path,
    cache_directory: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    ffmpeg: str,
    ffprobe: str,
    input_path: Path,
    cancel_event: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not cache_directory.is_dir() or cache_directory.is_symlink():
        return None
    try:
        expected_directory_names = {item["filename"] for item in _expected_files()}
        if {item.name for item in cache_directory.iterdir()} != expected_directory_names:
            return None
    except OSError:
        return None
    manifest = _read_manifest(cache_directory / "manifest.json")
    if manifest is None:
        return None
    expected_base = {
        "schema_version": QC_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "assembly_attempt_id": assembly_attempt_id,
        "assembly_artifact_id": assembly_artifact_id,
        "variant": variant,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "expected_duration_ms": expected_duration_ms,
        "tool_identity": dict(tool_identity),
        "policy": _qc_policy(),
    }
    if any(manifest.get(key) != value for key, value in expected_base.items()):
        return None
    files = manifest.get("files")
    if not isinstance(files, dict):
        return None
    try:
        actual_files = _manifest_file_records(cache_directory)
    except QcError:
        return None
    if files != actual_files:
        return None
    technical = _json_document(cache_directory / "technical-qc.json")
    ffprobe_document = _json_document(cache_directory / "ffprobe.json")
    if technical is None or ffprobe_document is None:
        return None
    try:
        # A fresh analysis guards against a swapped master whose replacement
        # happens to retain an old JSON sidecar.  Keep the registered assembly
        # master out of the published cache and expose it to the tools under
        # the same fixed basename used by the generation path.
        verify_stage = Path(
            tempfile.mkdtemp(prefix=".verify-", dir=str(cache_directory.parent))
        )
        try:
            staged_input = verify_stage / "assembly-master.mp4"
            _raise_if_cancelled(cancel_event)
            shutil.copyfile(input_path, staged_input)
            if _sha256_file(staged_input) != input_sha256 or staged_input.stat().st_size != input_bytes:
                return None
            facts, checks, probe = _analyse(
                ffmpeg,
                ffprobe,
                stage=verify_stage,
                cancel_event=cancel_event,
            )
            _finalize_checks(facts, checks, expected_duration_ms)
        finally:
            shutil.rmtree(verify_stage, ignore_errors=True)
    except (QcToolError, QcValidationError):
        raise
    except (OSError, shutil.Error):
        return None
    expected_technical = _technical_document(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        facts=facts,
        checks=checks,
    )
    expected_ffprobe = _ffprobe_document(
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        probe=probe,
    )
    expected_manifest_body = _manifest_body(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        technical=expected_technical,
        files=actual_files,
    )
    expected_manifest = dict(expected_manifest_body)
    expected_manifest["manifest_sha256"] = _manifest_digest(expected_manifest_body)
    if (
        technical != expected_technical
        or ffprobe_document != expected_ffprobe
        or manifest != expected_manifest
        or not _canonical_document_matches(cache_directory / "technical-qc.json", expected_technical)
        or not _canonical_document_matches(cache_directory / "ffprobe.json", expected_ffprobe)
        or not _canonical_document_matches(cache_directory / "manifest.json", expected_manifest)
    ):
        return None
    try:
        artifacts = [_artifact_record(workspace, cache_directory, spec) for spec in _expected_files()]
    except QcError:
        return None
    return manifest, artifacts


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    technical: Mapping[str, Any],
    stage: Path,
) -> bytes:
    # Manifest excludes itself from ``files`` while retaining its hash as the
    # final self-integrity field.  The technical JSON is a deliberately
    # duplicated, standalone result so audit consumers need not interpret the
    # manifest schema.
    try:
        files = _manifest_file_records(stage)
    except QcError as exc:
        raise QcError("QC staged artifact is unavailable", code="publish_failed") from exc
    body = _manifest_body(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        technical=technical,
        files=files,
    )
    manifest = dict(body)
    manifest["manifest_sha256"] = _manifest_digest(body)
    return (canonical_json(manifest) + "\n").encode("utf-8")


def _publish(stage: Path, cache_directory: Path) -> None:
    try:
        cache_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise QcError("QC cache directory could not be created", code="publish_failed") from exc
    if cache_directory.is_symlink() or not cache_directory.is_dir():
        raise QcError("QC cache path is unsafe", code="unsafe_output_path")
    try:
        expected_names = {item["filename"] for item in _expected_files()}
        if {item.name for item in cache_directory.iterdir()} - expected_names:
            raise QcError("QC cache contains unexpected files", code="invalid_cache")
    except OSError as exc:
        raise QcError("QC cache directory could not be inspected", code="publish_failed") from exc
    # JSON sidecars are replaced one at a time and manifest is last; no reader
    # can treat a partial set as a valid cache because manifest/files hashes are
    # checked before reuse.
    try:
        for spec in _expected_files():
            os.replace(stage / spec["filename"], cache_directory / spec["filename"])
    except OSError as exc:
        raise QcError("QC output could not be published", code="publish_failed") from exc


def _result(
    workspace: Path,
    cache_directory: Path,
    manifest: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "analysis_status": manifest["analysis_status"],
        "technical_verdict": manifest["technical_verdict"],
        "cache_hit": cache_hit,
        "duration_ms": manifest["duration_ms"],
        "assembly_attempt_id": manifest["assembly_attempt_id"],
        "assembly_artifact_id": manifest["assembly_artifact_id"],
        "variant": manifest["variant"],
        "input_sha256": manifest["input_sha256"],
        "input_bytes": manifest["input_bytes"],
        "expected_duration_ms": manifest["expected_duration_ms"],
        "checks": manifest["checks"],
        "media_facts": manifest["media_facts"],
        "artifacts": artifacts,
        "cache_key": manifest["cache_key"],
        "output_directory": cache_directory.relative_to(workspace.resolve(strict=True)).as_posix(),
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
    }


def _validate_common(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_path: str | Path,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None = None,
) -> tuple[Path, Path, str, str, str, dict[str, str], Path]:
    _raise_if_cancelled(cancel_event)
    try:
        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
    except SecurityError as exc:
        raise QcValidationError(str(exc), code="invalid_identifier") from exc
    _strict_cache_key(cache_key)
    _strict_id(assembly_attempt_id, label="assembly_attempt_id", pattern=_ATTEMPT_ID_RE)
    _strict_id(assembly_artifact_id, label="assembly_artifact_id", pattern=_ARTIFACT_ID_RE)
    _strict_variant(variant)
    input_sha256 = _strict_hash(input_sha256, label="input_sha256")
    input_bytes = _strict_bytes(input_bytes)
    expected_duration_ms = _strict_duration(expected_duration_ms)
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    try:
        workspace = workspace.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise QcValidationError("workspace is unavailable", code="invalid_workspace") from exc
    source_path = _safe_input_file(workspace, input_path)
    try:
        stat = source_path.stat()
    except OSError as exc:
        raise QcValidationError("input_path is unavailable", code="invalid_input_path") from exc
    if stat.st_size != input_bytes or _sha256_file(source_path) != input_sha256:
        raise QcValidationError(
            "input artifact hash or byte count does not match the request",
            code="input_hash_mismatch",
        )
    ffmpeg_executable = _find_tool("ffmpeg", ffmpeg)
    ffprobe_executable = _find_tool("ffprobe", ffprobe)
    # Resolve and retain the executable path after identity calculation so the
    # process argv cannot drift between cache-key computation and analysis.
    identity = resolve_tool_identity(
        ffmpeg=ffmpeg_executable,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    expected_cache_key = qc_cache_key(
        production_id=production_id,
        run_id=run_id,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=identity,
    )
    if cache_key != expected_cache_key:
        raise QcValidationError(
            "cache_key does not match current QC inputs or local media tools",
            code="cache_key_mismatch",
        )
    output_directory = _safe_qc_root(workspace, run_id, cache_key)
    return (
        workspace,
        source_path,
        ffmpeg_executable,
        ffprobe_executable,
        input_sha256,
        identity,
        output_directory,
    )


def _assert_input_unchanged(path: Path, *, expected_sha256: str, expected_bytes: int) -> None:
    try:
        stat = path.stat()
        digest = _sha256_file(path)
    except OSError as exc:
        raise QcError("assembly master changed during QC", code="input_changed") from exc
    if stat.st_size != expected_bytes or digest != expected_sha256:
        raise QcError("assembly master changed during QC", code="input_changed")


def generate_local_qc(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_path: str | Path,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Analyze an existing assembly master and publish a run-local QC record."""

    _raise_if_cancelled(cancel_event)
    (
        workspace,
        source_path,
        ffmpeg_executable,
        ffprobe_executable,
        input_sha256,
        tool_identity,
        output_directory,
    ) = _validate_common(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_path=input_path,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    cached = _validate_cached_output(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        ffmpeg=ffmpeg_executable,
        ffprobe=ffprobe_executable,
        input_path=source_path,
        cancel_event=cancel_event,
    )
    if cached is not None:
        manifest, artifacts = cached
        return _result(workspace, output_directory, manifest, artifacts, cache_hit=True)

    qc_root = output_directory.parent
    try:
        qc_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise QcError("QC output root could not be created", code="publish_failed") from exc
    if _has_symlink_component(workspace, qc_root) or qc_root.is_symlink() or not qc_root.is_dir():
        raise QcError("QC output root is unsafe", code="unsafe_output_path")
    try:
        stage = Path(tempfile.mkdtemp(prefix=f".{cache_key[:16]}-", dir=str(qc_root)))
    except OSError as exc:
        raise QcError("QC staging directory could not be created", code="publish_failed") from exc
    try:
        staged_input = stage / "assembly-master.mp4"
        _raise_if_cancelled(cancel_event)
        try:
            shutil.copyfile(source_path, staged_input)
        except (OSError, shutil.Error) as exc:
            raise QcError("assembly master could not be staged", code="input_changed") from exc
        _assert_input_unchanged(source_path, expected_sha256=input_sha256, expected_bytes=input_bytes)
        if _sha256_file(staged_input) != input_sha256 or staged_input.stat().st_size != input_bytes:
            raise QcError("assembly master changed during staging", code="input_changed")

        facts, checks, probe = _analyse(
            ffmpeg_executable,
            ffprobe_executable,
            stage=stage,
            cancel_event=cancel_event,
        )
        _finalize_checks(facts, checks, expected_duration_ms)
        technical = _technical_document(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            assembly_attempt_id=assembly_attempt_id,
            assembly_artifact_id=assembly_artifact_id,
            variant=variant,
            input_sha256=input_sha256,
            input_bytes=input_bytes,
            expected_duration_ms=expected_duration_ms,
            tool_identity=tool_identity,
            facts=facts,
            checks=checks,
        )
        ffprobe_document = _ffprobe_document(
            input_sha256=input_sha256,
            input_bytes=input_bytes,
            probe=probe,
        )
        _assert_input_unchanged(source_path, expected_sha256=input_sha256, expected_bytes=input_bytes)
        _write_atomic(stage / "technical-qc.json", (canonical_json(technical) + "\n").encode("utf-8"))
        _write_atomic(stage / "ffprobe.json", (canonical_json(ffprobe_document) + "\n").encode("utf-8"))
        _write_atomic(
            stage / "manifest.json",
            _build_manifest(
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                assembly_attempt_id=assembly_attempt_id,
                assembly_artifact_id=assembly_artifact_id,
                variant=variant,
                input_sha256=input_sha256,
                input_bytes=input_bytes,
                expected_duration_ms=expected_duration_ms,
                tool_identity=tool_identity,
                technical=technical,
                stage=stage,
            ),
        )
        _publish(stage, output_directory)
    except QcError:
        raise
    except (OSError, shutil.Error) as exc:
        raise QcError("QC output could not be published", code="publish_failed") from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    cached = _validate_cached_output(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        ffmpeg=ffmpeg_executable,
        ffprobe=ffprobe_executable,
        input_path=source_path,
        cancel_event=cancel_event,
    )
    if cached is None:
        raise QcError("generated QC cache failed integrity verification", code="invalid_cache")
    manifest, artifacts = cached
    return _result(workspace, output_directory, manifest, artifacts, cache_hit=False)


def validate_local_qc_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_path: str | Path,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Revalidate an already-published QC cache before artifact registration."""

    _raise_if_cancelled(cancel_event)
    (
        workspace,
        source_path,
        ffmpeg_executable,
        ffprobe_executable,
        input_sha256,
        tool_identity,
        output_directory,
    ) = _validate_common(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_path=input_path,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    cached = _validate_cached_output(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        tool_identity=tool_identity,
        ffmpeg=ffmpeg_executable,
        ffprobe=ffprobe_executable,
        input_path=source_path,
        cancel_event=cancel_event,
    )
    if cached is None:
        raise QcError("published QC cache failed integrity verification", code="invalid_cache")
    manifest, artifacts = cached
    result = _result(workspace, output_directory, manifest, artifacts, cache_hit=True)
    result["manifest"] = manifest
    result["tool_identity"] = tool_identity
    return result


# Stage-oriented alias, matching the local narration and assembly workers.
generate_local_technical_qc = generate_local_qc


__all__ = [
    "DURATION_TOLERANCE_MS",
    "FFMPEG_TIMEOUT_SECONDS",
    "FFPROBE_TIMEOUT_SECONDS",
    "IMPLEMENTATION_VERSION",
    "LocalQcError",
    "LocalQcValidationError",
    "QcError",
    "QcToolError",
    "QcValidationError",
    "PROVIDER",
    "QC_SCHEMA_VERSION",
    "TIMING_SOURCE",
    "generate_local_qc",
    "generate_local_technical_qc",
    "qc_cache_key",
    "resolve_tool_identity",
    "validate_local_qc_outputs",
]
