"""Auditable local FFmpeg assembly for Studio.

This module is intentionally a small, stdlib-only media adapter.  It accepts
three already-registered workspace files (a source video, a narration WAV, and
an SRT caption file), then creates one or two reviewable masters:

* ``master-clean.mp4`` replaces the source audio with narration;
* ``master-captioned.mp4`` burns the same captions into the clean master when
  ``include_captioned`` is true.

All external-process arguments are passed as a list with ``shell=False``.
Caption filtering uses a fixed filename in a fixed temporary working
directory, which avoids Windows filter-graph escaping of user-controlled
absolute paths.  Cache reads revalidate input hashes, every published output,
the media streams, and the manifest self-hash before being returned.
"""

from __future__ import annotations

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
from pathlib import Path
from typing import Any, Mapping, Sequence

from .security import SecurityError, canonical_json, validate_identifier, workspace_path

try:
    # The control-plane contract is kept separate so service.py can validate
    # worker results without importing any media implementation details.
    from .assembly_execution import (
        DEFAULT_CAPTION_STYLE_PRESET,
        LocalAssemblyError,
        LocalAssemblyValidationError,
        normalize_caption_style_preset,
        validate_normalized_caption_style,
    )
except ImportError:  # pragma: no cover - compatibility for isolated use
    from assembly_execution import (  # type: ignore[no-redef]
        DEFAULT_CAPTION_STYLE_PRESET,
        LocalAssemblyError,
        LocalAssemblyValidationError,
        normalize_caption_style_preset,
        validate_normalized_caption_style,
    )


ASSEMBLY_SCHEMA_VERSION = 2
IMPLEMENTATION_VERSION = "local-ffmpeg-v2"
PROVIDER = "local_ffmpeg"
TIMING_SOURCE = "ffprobe"

FFPROBE_TIMEOUT_SECONDS = 30
FFMPEG_TIMEOUT_SECONDS = 5 * 60
CANCEL_POLL_SECONDS = 0.1
_PROCESS_CLEANUP_TIMEOUT_SECONDS = 1.0
MAX_PROCESS_OUTPUT_BYTES = 256 * 1024
FFMPEG_THREADS = 2
MAX_SOURCE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_NARRATION_WAV_BYTES = 128 * 1024 * 1024
MAX_CAPTIONS_BYTES = 8 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_DURATION_MS = 30 * 60 * 1000
MIN_DURATION_MS = 50
MAX_CACHE_KEY_CHARS = 256
MAX_CAPTION_CUES = 2_000
MAX_CAPTION_TEXT_CHARS = 4_000
MAX_VIDEO_WIDTH = 16_384
MAX_VIDEO_HEIGHT = 16_384
MAX_VIDEO_PIXELS = 64 * 1024 * 1024
_AUDIO_POLICY_VERSION = "replace-source-audio-pad-short-reject-over-250ms-v1"
_OUTPUT_POLICY_VERSION = "h264-yuv420p-aac-mp4-caption-presets-v2"

_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ALLOWED_CAPTION_CONTROL = {"\r", "\n", "\t"}
_BASE_FILES: tuple[dict[str, str], ...] = (
    {"filename": "master-clean.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "master-captioned.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)
_TOOL_IDENTITY_LOCK = threading.Lock()
_TOOL_IDENTITY_CACHE: dict[tuple[str, int, int], dict[str, str]] = {}


def _cancel_event_is_set(cancel_event: Any | None) -> bool:
    if cancel_event is None:
        return False
    is_set = getattr(cancel_event, "is_set", None)
    if not callable(is_set):
        return False
    try:
        return bool(is_set())
    except Exception:
        return False


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    """Honor the JobExecutionContext contract without requiring its import."""

    if cancel_event is None:
        return
    raise_if_cancelled = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(raise_if_cancelled):
        raise_if_cancelled()
        return
    if _cancel_event_is_set(cancel_event):
        raise AssemblyError("local assembly was cancelled", code="process_interrupted")


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
            # Registry cleanup must not replace the media result/error.
            pass


def _expected_files(include_captioned: bool) -> tuple[dict[str, str], ...]:
    if include_captioned:
        return _BASE_FILES
    return tuple(item for item in _BASE_FILES if item["filename"] != "master-captioned.mp4")


class AssemblyError(LocalAssemblyError):
    """A safe, bounded error raised by the local assembly worker."""

    error_code = "local_assembly_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = message


class AssemblyValidationError(AssemblyError):
    error_code = "invalid_local_assembly_request"


class AssemblyToolError(AssemblyError):
    error_code = "local_ffmpeg_unavailable"


def _resolved_caption_style(
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
    *,
    include_captioned: bool = True,
) -> dict[str, Any]:
    try:
        style = normalize_caption_style_preset(caption_style_preset)
    except LocalAssemblyValidationError as exc:
        raise AssemblyValidationError(str(exc), code=exc.code) from exc
    if not include_captioned and style["preset"] != DEFAULT_CAPTION_STYLE_PRESET:
        raise AssemblyValidationError(
            "caption_style_preset requires include_captioned=true",
            code="invalid_local_assembly_request",
        )
    return style


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _strict_cache_key(value: Any) -> str:
    if not isinstance(value, str) or not _CACHE_KEY_RE.fullmatch(value):
        raise AssemblyValidationError("cache_key is invalid", code="invalid_cache_key")
    if len(value) > MAX_CACHE_KEY_CHARS:
        raise AssemblyValidationError("cache_key is too long", code="invalid_cache_key")
    return value


def _strict_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", value):
        raise AssemblyValidationError(f"{label} must be a SHA-256 digest", code="invalid_provenance")
    return value.upper()


def _tool_identity(
    name: str,
    explicit: str | Path | None = None,
    *,
    cancel_event: Any | None = None,
) -> dict[str, str]:
    _raise_if_cancelled(cancel_event)
    executable = _find_tool(name, explicit)
    resolved = str(Path(executable).resolve(strict=True))
    try:
        stat = Path(resolved).stat()
    except OSError as exc:
        raise AssemblyToolError(f"{name} executable is unavailable") from exc
    cache_key = (resolved, stat.st_size, stat.st_mtime_ns)
    # A file can be replaced in place while retaining both its size and
    # timestamp (notably on filesystems that expose coarse mtimes).  Those
    # stat fields are useful for avoiding needless cache growth, but they are
    # not an identity.  Hash before consulting the cache so a same-size,
    # same-mtime replacement cannot inherit the old executable identity.
    try:
        digest = _sha256_file(Path(resolved))
    except OSError as exc:
        raise AssemblyToolError(f"{name} executable is unavailable") from exc
    _raise_if_cancelled(cancel_event)
    with _TOOL_IDENTITY_LOCK:
        cached = _TOOL_IDENTITY_CACHE.get(cache_key)
    if cached is not None and cached.get("sha256") == digest:
        return dict(cached)
    try:
        _raise_if_cancelled(cancel_event)
        output = _bounded_process(
            [resolved, "-version"],
            cwd=Path.cwd(),
            timeout=FFPROBE_TIMEOUT_SECONDS,
            label=f"{name} version",
            cancel_event=cancel_event,
        )
    except AssemblyError as exc:
        if _cancel_event_is_set(cancel_event):
            raise
        raise AssemblyToolError(f"{name} version could not be determined") from exc
    try:
        version = output.decode("utf-8", errors="replace").splitlines()[0].strip()
    except IndexError as exc:
        raise AssemblyToolError(f"{name} version could not be determined") from exc
    if not version or len(version) > 512:
        raise AssemblyToolError(f"{name} version could not be determined")
    identity = {
        "path": resolved,
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
    """Return the executable path, version, and binary hash used by assembly."""

    return {
        "ffmpeg": _tool_identity("ffmpeg", ffmpeg, cancel_event=cancel_event),
        "ffprobe": _tool_identity("ffprobe", ffprobe, cancel_event=cancel_event),
    }


def _normalize_tool_identity(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AssemblyValidationError(f"{label} is invalid", code="invalid_tool_identity")
    path = value.get("path")
    version = value.get("version")
    digest = value.get("sha256")
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise AssemblyValidationError(f"{label} path is invalid", code="invalid_tool_identity")
    if not isinstance(version, str) or not version or len(version) > 512:
        raise AssemblyValidationError(f"{label} version is invalid", code="invalid_tool_identity")
    return {
        "path": path,
        "version": version,
        "sha256": _strict_sha256(digest, label=f"{label}.sha256"),
    }


def assembly_cache_key(
    source_video_sha256: str,
    narration_wav_sha256: str,
    captions_sha256: str,
    include_captioned: bool,
    *,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
    ffmpeg_identity: Mapping[str, Any] | None = None,
    ffprobe_identity: Mapping[str, Any] | None = None,
    tool_identity: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Derive a stable cache key from registered input provenance.

    The implementation version is part of the identity so changing codec or
    filter policy cannot accidentally reuse an older assembly.
    """

    if not isinstance(include_captioned, bool):
        raise AssemblyValidationError("include_captioned must be a boolean")
    caption_style = _resolved_caption_style(
        caption_style_preset,
        include_captioned=include_captioned,
    )
    if tool_identity is not None:
        if ffmpeg_identity is not None or ffprobe_identity is not None:
            raise AssemblyValidationError("tool identity was provided twice")
        ffmpeg_identity = tool_identity.get("ffmpeg") if isinstance(tool_identity, Mapping) else None
        ffprobe_identity = tool_identity.get("ffprobe") if isinstance(tool_identity, Mapping) else None
    if ffmpeg_identity is None:
        ffmpeg_identity = _tool_identity("ffmpeg")
    if ffprobe_identity is None:
        ffprobe_identity = _tool_identity("ffprobe")
    identity = {
        "schema_version": ASSEMBLY_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "source_video_sha256": _strict_sha256(source_video_sha256, label="source_video_sha256"),
        "narration_wav_sha256": _strict_sha256(narration_wav_sha256, label="narration_wav_sha256"),
        "captions_sha256": _strict_sha256(captions_sha256, label="captions_sha256"),
        "include_captioned": include_captioned,
        "caption_style": caption_style,
        "audio_policy": _AUDIO_POLICY_VERSION,
        "output_policy": _output_policy(include_captioned),
        "caption_policy": _caption_policy(caption_style),
        "resource_policy": _resource_policy(),
        "tool_identity": {
            "ffmpeg": _normalize_tool_identity(ffmpeg_identity, label="ffmpeg_identity"),
            "ffprobe": _normalize_tool_identity(ffprobe_identity, label="ffprobe_identity"),
        },
    }
    return _sha256_bytes(canonical_json(identity).encode("utf-8"))


def _has_symlink_component(workspace: Path, candidate: Path) -> bool:
    """Reject a path whose lexical components contain a symlink.

    ``workspace_path`` resolves links for boundary checking.  Checking the
    lexical components as well prevents a registered path that is itself a
    symlink (or lives below one) from silently changing its source after the
    registration check.
    """

    try:
        relative = candidate.relative_to(workspace)
    except ValueError:
        return True
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_file(
    workspace: Path,
    value: str | Path,
    *,
    label: str,
    maximum_bytes: int,
) -> Path:
    if not isinstance(value, (str, Path)):
        raise AssemblyValidationError(f"{label} must be a workspace path")
    supplied = Path(value)
    try:
        lexical = supplied if supplied.is_absolute() else workspace / supplied
        path = workspace_path(workspace, lexical, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise AssemblyValidationError(f"{label} is outside the workspace") from exc
    if _has_symlink_component(workspace, lexical) or path.is_symlink():
        raise AssemblyValidationError(f"{label} must not be a symlink")
    if not path.is_file():
        raise AssemblyValidationError(f"{label} must be a regular file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AssemblyValidationError(f"{label} is unavailable") from exc
    if size <= 0 or size > maximum_bytes:
        raise AssemblyValidationError(f"{label} has an unsupported size")
    return path


def _safe_output_root(workspace: Path, run_id: str, cache_key: str) -> Path:
    lexical_root = workspace / "outputs" / "studio" / "runs"
    lexical_run = lexical_root / run_id
    lexical_assembly = lexical_run / "assembly"
    lexical_cache = lexical_assembly / cache_key
    if any(
        _has_symlink_component(workspace, candidate)
        for candidate in (lexical_root, lexical_run, lexical_assembly, lexical_cache)
    ):
        raise AssemblyValidationError("assembly output path must not contain symlinks")
    root = workspace_path(workspace, lexical_root, must_exist=False)
    run_directory = workspace_path(workspace, lexical_run, must_exist=False)
    assembly_root = workspace_path(workspace, lexical_assembly, must_exist=False)
    cache_directory = workspace_path(
        workspace, lexical_cache, must_exist=False
    )
    for directory in (root, run_directory, assembly_root):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise AssemblyValidationError("assembly output path is not a directory")
    if cache_directory.exists() and cache_directory.is_symlink():
        raise AssemblyValidationError("assembly cache path must not be a symlink")
    return cache_directory


def _find_tool(name: str, explicit: str | Path | None = None) -> str:
    if explicit is not None:
        candidate = Path(explicit)
        if not candidate.is_file() or candidate.is_dir():
            raise AssemblyToolError(f"{name} executable is unavailable")
        return str(candidate.resolve(strict=True))
    found = shutil.which(name)
    if not found:
        raise AssemblyToolError(f"{name} executable is unavailable")
    return found


def _terminate_process_tree(
    process: subprocess.Popen[bytes], *, deadline: float | None = None
) -> None:
    """Use the jobs process-tree terminator without changing worker callers.

    ``JobExecutionContext`` and the local workers must use the same bounded
    process-tree policy.  Keep the worker-facing ``Popen`` adapter here so
    direct worker use remains source-compatible while the jobs helper owns the
    Windows taskkill/child fallback details.
    """

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
        # Teardown must not replace the worker's original timeout, cancellation,
        # or reader failure.  The jobs helper already contains its own
        # per-process fallback handling; this catches import/adapter failures.
        pass


def _bounded_process(
    arguments: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    label: str,
    cancel_event: Any | None = None,
    environment: Mapping[str, str] | None = None,
) -> bytes:
    """Run a local media tool without a shell and with bounded diagnostics.

    Both pipes are drained concurrently while the child runs.  Keeping the
    readers active avoids the classic ``wait``/full-pipe deadlock, while each
    reader retains at most ``MAX_PROCESS_OUTPUT_BYTES + 1`` bytes so a noisy
    local binary cannot grow a temporary file or the worker's memory without
    bound.
    """

    _raise_if_cancelled(cancel_event)
    creationflags = 0
    process_options: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        process_options["creationflags"] = creationflags
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
            # The process teardown path may close a pipe while its reader is
            # waking up.  The process result remains authoritative.
            return
        except BaseException as exc:
            # A reader failure is not safe to ignore: the child may block on a
            # full pipe forever.  Surface it to the owner thread so the whole
            # process tree is terminated through the bounded shutdown path.
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
            env=None if environment is None else dict(environment),
            **process_options,
        )
        registered = _register_process(cancel_event, process)
        # The cancellation state may change between the preflight check and
        # Popen.  Register first, then check again so shutdown can terminate
        # this exact process instead of only discovering it as an untracked
        # descendant.
        _raise_if_cancelled(cancel_event)
        if process.stdout is None or process.stderr is None:
            terminate_active_process()
            raise AssemblyToolError(f"{label} did not expose output pipes")
        readers = [
            threading.Thread(
                target=drain,
                args=(process.stdout, stdout_buffer),
                name=f"assembly-{label}-stdout",
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, stderr_buffer),
                name=f"assembly-{label}-stderr",
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        try:
            deadline = time.monotonic() + timeout
            while True:
                _raise_if_cancelled(cancel_event)
                if reader_failed.is_set():
                    raise_reader_failure()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    terminate_active_process()
                    raise AssemblyToolError(
                        f"{label} timed out", code="local_ffmpeg_timeout"
                    )
                try:
                    return_code = process.wait(
                        timeout=min(CANCEL_POLL_SECONDS, remaining)
                    )
                    if reader_failed.is_set():
                        raise_reader_failure()
                    break
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired as exc:
            # Kept for process implementations that raise a timeout without
            # honoring the bounded polling timeout above.
            terminate_active_process()
            raise AssemblyToolError(
                f"{label} timed out", code="local_ffmpeg_timeout"
            ) from exc
        except BaseException:
            terminate_active_process()
            raise
        finally:
            # Normal process exit closes the pipes.  Give readers one shared,
            # short budget; the previous per-reader 10-second joins could
            # exceed the worker's shutdown bound before tree termination.
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
        stdout = bytes(stdout_buffer)
        stderr = bytes(stderr_buffer)
    except FileNotFoundError as exc:
        raise AssemblyToolError(f"{label} executable is unavailable") from exc
    except AssemblyError:
        terminate_active_process()
        raise
    except OSError as exc:
        raise AssemblyToolError(f"{label} could not be started") from exc
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
    if len(stdout) > MAX_PROCESS_OUTPUT_BYTES or len(stderr) > MAX_PROCESS_OUTPUT_BYTES:
        raise AssemblyToolError(f"{label} produced excessive diagnostics")
    if return_code != 0:
        # Tool output is intentionally not surfaced: ffmpeg paths and local
        # installation details are not useful in the public job record.
        raise AssemblyToolError(f"{label} failed", code="local_ffmpeg_failed")
    return stdout


def _json_probe(
    ffprobe: str,
    path: Path,
    *,
    cwd: Path,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    _raise_if_cancelled(cancel_event)
    output = _bounded_process(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,bits_per_sample,codec_tag_string,duration",
            "-of",
            "json",
            str(path),
        ],
        cwd=cwd,
        timeout=FFPROBE_TIMEOUT_SECONDS,
        label="ffprobe",
        cancel_event=cancel_event,
    )
    try:
        value = json.loads(output.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssemblyToolError("ffprobe returned invalid JSON", code="invalid_ffprobe_result") from exc
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        raise AssemblyToolError("ffprobe returned an invalid media description", code="invalid_ffprobe_result")
    return value


def _finite_duration(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result <= 0:
        return None
    return result


def _probe_duration(probe: Mapping[str, Any], *, stream_type: str | None = None) -> float:
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            if stream_type is not None and stream.get("codec_type") != stream_type:
                continue
            duration = _finite_duration(stream.get("duration"))
            if duration is not None:
                return duration
    format_data = probe.get("format")
    if isinstance(format_data, dict):
        duration = _finite_duration(format_data.get("duration"))
        if duration is not None:
            return duration
    raise AssemblyValidationError("media duration is unavailable", code="invalid_media")


def _first_stream(probe: Mapping[str, Any], codec_type: str) -> dict[str, Any]:
    streams = probe.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
                return stream
    raise AssemblyValidationError(
        f"media has no {codec_type} stream", code="invalid_media"
    )


def _streams(probe: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = probe.get("streams")
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise AssemblyValidationError("media stream description is invalid", code="invalid_media")
    return [item for item in raw if isinstance(item, dict)]


def _validate_source_probe(probe: Mapping[str, Any]) -> int:
    streams = _streams(probe)
    if sum(stream.get("codec_type") == "video" for stream in streams) != 1:
        raise AssemblyValidationError("source must contain exactly one video stream", code="invalid_media")
    if any(stream.get("codec_type") not in {"video", "audio"} for stream in streams):
        raise AssemblyValidationError("source contains unsupported streams", code="invalid_media")
    video = _first_stream(probe, "video")
    width, height = video.get("width"), video.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
        or width > MAX_VIDEO_WIDTH
        or height > MAX_VIDEO_HEIGHT
        or width * height > MAX_VIDEO_PIXELS
    ):
        raise AssemblyValidationError("source video dimensions are invalid", code="invalid_media")
    duration = _probe_duration(probe, stream_type="video")
    duration_ms = int(round(duration * 1000))
    if duration_ms < MIN_DURATION_MS or duration_ms > MAX_DURATION_MS:
        raise AssemblyValidationError("source video duration is unsupported", code="invalid_media")
    return duration_ms


def _source_dimensions(probe: Mapping[str, Any]) -> tuple[int, int]:
    video = _first_stream(probe, "video")
    width, height = video.get("width"), video.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
        or width > MAX_VIDEO_WIDTH
        or height > MAX_VIDEO_HEIGHT
        or width * height > MAX_VIDEO_PIXELS
    ):
        raise AssemblyValidationError("source video dimensions are invalid", code="invalid_media")
    return width, height


def _validate_narration_probe(probe: Mapping[str, Any]) -> int:
    streams = _streams(probe)
    if len(streams) != 1 or streams[0].get("codec_type") != "audio":
        raise AssemblyValidationError("narration must contain exactly one audio stream", code="invalid_media")
    format_data = probe.get("format")
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if format_name != "wav":
        raise AssemblyValidationError("narration must use a WAV container", code="invalid_media")
    audio = _first_stream(probe, "audio")
    codec = audio.get("codec_name")
    if not isinstance(codec, str) or not codec.startswith("pcm_"):
        raise AssemblyValidationError("narration must use PCM audio", code="invalid_media")
    sample_rate = audio.get("sample_rate")
    channels = audio.get("channels")
    try:
        sample_rate_number = int(sample_rate)
        channels_number = int(channels)
    except (TypeError, ValueError) as exc:
        raise AssemblyValidationError("narration audio format is invalid", code="invalid_media") from exc
    if not 8_000 <= sample_rate_number <= 192_000 or channels_number not in {1, 2}:
        raise AssemblyValidationError("narration audio format is unsupported", code="invalid_media")
    duration = _probe_duration(probe, stream_type="audio")
    duration_ms = int(round(duration * 1000))
    if duration_ms < MIN_DURATION_MS or duration_ms > MAX_DURATION_MS:
        raise AssemblyValidationError("narration duration is unsupported", code="invalid_media")
    return duration_ms


def _validate_caption_bytes(path: Path) -> bytes:
    try:
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise AssemblyValidationError("captions.srt must be UTF-8", code="invalid_captions") from exc
    if not text.strip() or "\x00" in text:
        raise AssemblyValidationError("captions.srt is invalid", code="invalid_captions")
    if any(ord(char) < 0x20 and char not in _ALLOWED_CAPTION_CONTROL for char in text):
        raise AssemblyValidationError("captions.srt contains unsupported control characters", code="invalid_captions")
    return data


def _validate_caption_timing(data: bytes, *, source_duration_ms: int) -> None:
    cues = _parse_srt(data)
    if not cues:
        raise AssemblyValidationError("captions.srt has no cues", code="invalid_captions")
    if cues[-1][1] > source_duration_ms + 250:
        raise AssemblyValidationError(
            "caption timing extends beyond the source video",
            code="caption_timing_out_of_range",
        )


_SRT_TIME_RE = re.compile(
    r"^(?P<hours>\d{1,3}):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d),(?P<millis>\d{3})$"
)


def _srt_time_to_ms(value: str) -> int:
    match = _SRT_TIME_RE.fullmatch(value.strip())
    if match is None:
        raise AssemblyValidationError("captions.srt has an invalid timestamp", code="invalid_captions")
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))
    result = ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis
    if result > MAX_DURATION_MS:
        raise AssemblyValidationError("captions.srt timestamp is too large", code="invalid_captions")
    return result


def _escape_ass_text(value: str) -> str:
    """Escape ASS syntax so caption text cannot create override tags."""

    # Use full-width glyphs for ASCII braces and backslashes.  This preserves
    # the visible intent while making it impossible for user text such as
    # ``{\\an8}`` or ``\\pos`` to become an ASS override/control sequence.
    escaped = value.replace("\\", "＼")
    escaped = escaped.replace("{", "｛").replace("}", "｝")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    return escaped.replace("\n", r"\N")


def _ass_time(milliseconds: int) -> str:
    centiseconds_total = milliseconds // 10
    hours, remainder = divmod(centiseconds_total, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _parse_srt(data: bytes) -> list[tuple[int, int, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:  # defensive when called independently
        raise AssemblyValidationError("captions.srt must be UTF-8", code="invalid_captions") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block for block in re.split(r"\n{2,}", normalized) if block.strip()]
    if not blocks or len(blocks) > MAX_CAPTION_CUES:
        raise AssemblyValidationError("captions.srt cue count is unsupported", code="invalid_captions")
    cues: list[tuple[int, int, str]] = []
    previous_end = -1
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            raise AssemblyValidationError("captions.srt cue is incomplete", code="invalid_captions")
        index = lines[0].strip()
        if not index.isdigit():
            raise AssemblyValidationError("captions.srt cue index is invalid", code="invalid_captions")
        timing = re.fullmatch(r"\s*(\d{1,3}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{1,3}:\d{2}:\d{2},\d{3})(?:\s+.*)?", lines[1])
        if timing is None:
            raise AssemblyValidationError("captions.srt cue timing is invalid", code="invalid_captions")
        start_ms = _srt_time_to_ms(timing.group(1))
        end_ms = _srt_time_to_ms(timing.group(2))
        if start_ms >= end_ms or start_ms < previous_end:
            raise AssemblyValidationError("captions.srt cue timings overlap", code="invalid_captions")
        caption = "\n".join(lines[2:]).strip()
        if not caption or len(caption) > MAX_CAPTION_TEXT_CHARS:
            raise AssemblyValidationError("captions.srt cue text is invalid", code="invalid_captions")
        if any(ord(char) < 0x20 and char not in _ALLOWED_CAPTION_CONTROL for char in caption):
            raise AssemblyValidationError("captions.srt cue text contains control characters", code="invalid_captions")
        cues.append((start_ms, end_ms, caption))
        previous_end = end_ms
    return cues


def _ass_color(value: str, *, alpha: int = 0) -> str:
    """Convert a canonical #RRGGBB preset color into ASS AABBGGRR."""

    if not re.fullmatch(r"#[0-9A-F]{6}", value) or not 0 <= alpha <= 255:
        raise AssemblyValidationError("caption style color is invalid")
    red, green, blue = value[1:3], value[3:5], value[5:7]
    return f"&H{alpha:02X}{blue}{green}{red}"


def _build_ass(
    data: bytes,
    *,
    width: int,
    height: int,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
) -> bytes:
    cues = _parse_srt(data)
    style = _resolved_caption_style(caption_style_preset)
    ass_fields = [
        style["ass_style_name"],
        style["font_name"],
        str(style["font_size"]),
        _ass_color(style["primary_color"]),
        _ass_color(style["secondary_color"]),
        _ass_color(style["outline_color"]),
        _ass_color(style["back_color"], alpha=style["back_alpha"]),
        "-1" if style["bold"] else "0",
        "-1" if style["italic"] else "0",
        "-1" if style["underline"] else "0",
        "-1" if style["strike_out"] else "0",
        str(style["scale_x"]),
        str(style["scale_y"]),
        str(style["spacing"]),
        str(style["angle"]),
        str(style["border_style"]),
        str(style["outline_width"]),
        str(style["shadow_depth"]),
        str(style["alignment"]),
        str(style["margin_left"]),
        str(style["margin_right"]),
        str(style["margin_vertical"]),
        str(style["encoding"]),
    ]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        f"WrapStyle: {style['wrap_style']}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {','.join(ass_fields)}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Text",
    ]
    for start_ms, end_ms, caption in cues:
        lines.append(
            f"Dialogue: 0,{_ass_time(start_ms)},{_ass_time(end_ms)},{style['ass_style_name']},{_escape_ass_text(caption)}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _filter_path(path: Path) -> str:
    """Return a Windows path escaped for an FFmpeg filter script."""

    value = path.resolve(strict=True).as_posix()
    # In a filter script the drive colon is the only filter-option separator
    # that needs escaping; use one literal backslash (not shell escaping).
    return value.replace(":", "\\:").replace("'", "\\'")


def _artifact_record(workspace: Path, cache_directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
    if path.is_symlink() or not path.is_file():
        raise AssemblyError(f"assembly artifact is unavailable: {spec['filename']}", code="invalid_cache")
    stat = path.stat()
    relative = path.relative_to(workspace.resolve(strict=True)).as_posix()
    mime = spec["mime"]
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": stat.st_size,
        "sha256": _sha256_file(path),
        "mime": mime,
        "media_type": mime,
        "origin": "studio",
        "version": IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _input_record(workspace: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(workspace.resolve(strict=True)).as_posix(),
        "bytes": stat.st_size,
        "sha256": _sha256_file(path),
    }


def _assert_input_unchanged(path: Path, expected: Mapping[str, Any], *, label: str) -> None:
    try:
        stat = path.stat()
        digest = _sha256_file(path)
    except OSError as exc:
        raise AssemblyError(f"{label} changed during assembly", code="input_changed") from exc
    if stat.st_size != expected.get("bytes") or digest != expected.get("sha256"):
        raise AssemblyError(f"{label} changed during assembly", code="input_changed")


def _required_output_stream_duration(
    probe: Mapping[str, Any],
    stream_type: str,
) -> float:
    """Read one output stream's duration without falling back to format data."""

    stream = _first_stream(probe, stream_type)
    duration = _finite_duration(stream.get("duration"))
    if duration is None:
        raise AssemblyError(
            f"FFmpeg {stream_type} stream duration is unavailable",
            code="invalid_output_media",
        )
    return duration


def _validate_output_probe(
    probe: Mapping[str, Any],
    *,
    target_duration_ms: int,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> None:
    format_data = probe.get("format")
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if not isinstance(format_name, str) or "mp4" not in {part.strip().casefold() for part in format_name.split(",")}:
        raise AssemblyError("FFmpeg did not produce an MP4 container", code="invalid_output_media")
    streams = _streams(probe)
    if len(streams) != 2 or {stream.get("codec_type") for stream in streams} != {"video", "audio"}:
        raise AssemblyError("FFmpeg produced an unexpected stream layout", code="invalid_output_media")
    video = _first_stream(probe, "video")
    audio = _first_stream(probe, "audio")
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise AssemblyError("FFmpeg produced an unsupported output codec", code="invalid_output_media")
    if video.get("pix_fmt") != "yuv420p":
        raise AssemblyError("FFmpeg produced an unsupported pixel format", code="invalid_output_media")
    if expected_width is not None and video.get("width") != expected_width:
        raise AssemblyError("FFmpeg changed the output width", code="invalid_output_media")
    if expected_height is not None and video.get("height") != expected_height:
        raise AssemblyError("FFmpeg changed the output height", code="invalid_output_media")
    try:
        sample_rate = int(audio.get("sample_rate"))
        channels = int(audio.get("channels"))
    except (TypeError, ValueError) as exc:
        raise AssemblyError("FFmpeg produced invalid audio metadata", code="invalid_output_media") from exc
    if sample_rate != 48_000 or channels != 2:
        raise AssemblyError("FFmpeg produced an unsupported audio format", code="invalid_output_media")
    # Container duration is not sufficient: MP4 can retain a plausible format
    # duration while one stream ends early.  Validate each required stream so
    # a short audio or video track cannot pass the output contract.
    for stream_type in ("video", "audio"):
        duration = _required_output_stream_duration(probe, stream_type)
        duration_ms = int(round(duration * 1000))
        if abs(duration_ms - target_duration_ms) > 250:
            raise AssemblyError(
                f"FFmpeg output duration does not match the source ({stream_type} stream)",
                code="invalid_output_media",
            )
        if duration_ms < MIN_DURATION_MS or duration_ms > MAX_DURATION_MS:
            raise AssemblyError(
                f"FFmpeg output duration is unsupported ({stream_type} stream)",
                code="invalid_output_media",
            )


def _output_policy(include_captioned: bool) -> dict[str, str]:
    return {
        "policy_version": _OUTPUT_POLICY_VERSION,
        "master_clean": "required",
        "master_captioned": "required" if include_captioned else "omitted_by_request",
        "container": "mp4",
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "audio_codec": "aac",
        "audio_sample_rate": "48000",
        "audio_channels": "2",
        "frame_rate_policy": "preserve_source_timing_with_ffmpeg_reencode",
        "vfr_policy": "accept_and_validate_duration_with_ffprobe",
    }


def _audio_policy(*, source_duration_ms: int, narration_duration_ms: int) -> dict[str, Any]:
    if narration_duration_ms > source_duration_ms:
        action = "trim_to_source_duration_within_250ms_tolerance"
    elif narration_duration_ms < source_duration_ms:
        action = "pad_to_source_duration_with_apad"
    else:
        action = "exact_source_duration"
    return {
        "policy_version": _AUDIO_POLICY_VERSION,
        "source_audio": "replaced",
        "narration_duration_ms": narration_duration_ms,
        "source_duration_ms": source_duration_ms,
        "long_narration_policy": "reject_over_250ms",
        "action": action,
    }


def _caption_policy(caption_style: Mapping[str, Any]) -> dict[str, Any]:
    try:
        canonical_style = validate_normalized_caption_style(dict(caption_style))
    except LocalAssemblyValidationError as exc:
        raise AssemblyValidationError(str(exc), code=exc.code) from exc
    return {
        "policy_version": "srt-to-enum-preset-ass-v2",
        "format": "srt_to_preset_style_ass",
        "end_tolerance_ms": 250,
        "override_tags": "disabled_by_fullwidth_escape",
        "preset": canonical_style["preset"],
        "wrap_style": canonical_style["wrap_style"],
    }


def _resource_policy() -> dict[str, int]:
    return {"ffmpeg_threads": FFMPEG_THREADS}


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    digest = value.get("manifest_sha256")
    if not isinstance(digest, str):
        return None
    without_digest = dict(value)
    without_digest.pop("manifest_sha256", None)
    if _manifest_digest(without_digest) != digest.upper():
        return None
    return value


def _validate_cache(
    workspace: Path,
    cache_directory: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    inputs: Mapping[str, Mapping[str, Any]],
    target_duration_ms: int,
    include_captioned: bool,
    caption_style: Mapping[str, Any],
    narration_duration_ms: int,
    source_width: int,
    source_height: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    ffprobe: str,
    cancel_event: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _raise_if_cancelled(cancel_event)
    if not cache_directory.is_dir() or cache_directory.is_symlink():
        return None
    manifest = _read_manifest(cache_directory / "manifest.json")
    if manifest is None:
        return None
    if (
        manifest.get("schema_version") != ASSEMBLY_SCHEMA_VERSION
        or manifest.get("implementation_version") != IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("cache_key") != cache_key
        or manifest.get("provider") != PROVIDER
        or manifest.get("provider_task_id") is not None
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != TIMING_SOURCE
        or manifest.get("duration_ms") != target_duration_ms
        or manifest.get("include_captioned") is not include_captioned
        or manifest.get("caption_style_preset") != caption_style["preset"]
        or manifest.get("caption_style") != dict(caption_style)
        or manifest.get("tool_identity") != dict(tool_identity)
        or manifest.get("output_policy") != _output_policy(include_captioned)
        or manifest.get("caption_policy") != _caption_policy(caption_style)
        or manifest.get("resource_policy") != _resource_policy()
        or manifest.get("video_dimensions") != {"width": source_width, "height": source_height}
        or manifest.get("audio_policy")
        != _audio_policy(
            source_duration_ms=target_duration_ms,
            narration_duration_ms=narration_duration_ms,
        )
    ):
        return None
    if manifest.get("inputs") != dict(inputs):
        return None
    files = manifest.get("files")
    expected_files = _expected_files(include_captioned)
    expected_output_names = {item["filename"] for item in expected_files if item["filename"] != "manifest.json"}
    if not isinstance(files, dict) or set(files) != expected_output_names:
        return None
    for spec in expected_files:
        _raise_if_cancelled(cancel_event)
        if spec["filename"] == "manifest.json":
            continue
        entry = files.get(spec["filename"])
        path = cache_directory / spec["filename"]
        if not isinstance(entry, dict) or path.is_symlink() or not path.is_file():
            return None
        try:
            file_size = path.stat().st_size
        except OSError:
            return None
        if spec["mime"] == "video/mp4" and file_size > MAX_OUTPUT_BYTES:
            # Re-apply the live output limit on cache hits.  A previously
            # published (or tampered) oversized MP4 must never be reused just
            # because its manifest hash is internally consistent.
            return None
        if (
            entry.get("path") != spec["filename"]
            or entry.get("kind") != spec["kind"]
            or entry.get("mime") != spec["mime"]
            or entry.get("bytes") != file_size
            or entry.get("sha256") != _sha256_file(path)
        ):
            return None
    try:
        ffprobe_path = cache_directory / "ffprobe.json"
        if ffprobe_path.stat().st_size > MAX_METADATA_BYTES:
            return None
        ffprobe_document = json.loads(ffprobe_path.read_text(encoding="utf-8"))
        if (
            not isinstance(ffprobe_document, dict)
            or ffprobe_document.get("schema_version") != ASSEMBLY_SCHEMA_VERSION
            or ffprobe_document.get("implementation_version") != IMPLEMENTATION_VERSION
            or ffprobe_document.get("timing_source") != TIMING_SOURCE
        ):
            return None
        source_probe = ffprobe_document.get("source_video")
        narration_probe = ffprobe_document.get("narration_wav")
        clean_probe = ffprobe_document.get("master_clean")
        captioned_probe = ffprobe_document.get("master_captioned")
        if (
            not isinstance(source_probe, dict)
            or not isinstance(narration_probe, dict)
            or not isinstance(clean_probe, dict)
            or (
            include_captioned and not isinstance(captioned_probe, dict)
            )
            or (
            not include_captioned and captioned_probe is not None
            )
        ):
            return None
        if _validate_source_probe(source_probe) != target_duration_ms:
            return None
        if _validate_narration_probe(narration_probe) != narration_duration_ms:
            return None
        if _source_dimensions(source_probe) != (source_width, source_height):
            return None
        if manifest.get("media") != {
            "source_video": source_probe,
            "narration_wav": narration_probe,
            "master_clean": clean_probe,
            "master_captioned": captioned_probe,
        }:
            return None
        _validate_output_probe(
            clean_probe,
            target_duration_ms=target_duration_ms,
            expected_width=source_width,
            expected_height=source_height,
        )
        if include_captioned:
            _validate_output_probe(
                captioned_probe,
                target_duration_ms=target_duration_ms,
                expected_width=source_width,
                expected_height=source_height,
            )
        # A fresh probe catches a valid-length file that was replaced with a
        # different stream layout while retaining a copied old metadata blob.
        _validate_output_probe(
            _json_probe(
                ffprobe,
                Path("master-clean.mp4"),
                cwd=cache_directory,
                cancel_event=cancel_event,
            ),
            target_duration_ms=target_duration_ms,
            expected_width=source_width,
            expected_height=source_height,
        )
        if include_captioned:
            _validate_output_probe(
                _json_probe(
                    ffprobe,
                    Path("master-captioned.mp4"),
                    cwd=cache_directory,
                    cancel_event=cancel_event,
                ),
                target_duration_ms=target_duration_ms,
                expected_width=source_width,
                expected_height=source_height,
            )
    except AssemblyError:
        if _cancel_event_is_set(cancel_event):
            raise
        return None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    try:
        artifacts = [
            _artifact_record(workspace, cache_directory, spec) for spec in expected_files
        ]
    except (OSError, ValueError, AssemblyError):
        return None
    return manifest, artifacts


def _write_atomic(path: Path, data: bytes) -> None:
    if len(data) > MAX_METADATA_BYTES:
        raise AssemblyError("assembly metadata is too large", code="metadata_too_large")
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _publish(
    stage: Path, cache_directory: Path, *, include_captioned: bool
) -> None:
    cache_directory.mkdir(parents=True, exist_ok=True)
    if cache_directory.is_symlink() or not cache_directory.is_dir():
        raise AssemblyError("assembly cache path is unsafe", code="unsafe_output_path")
    # Publish each file atomically and put the manifest last.  A reader that
    # observes a partial publish therefore cannot pass cache validation.
    for spec in _expected_files(include_captioned):
        if spec["filename"] == "manifest.json":
            continue
        os.replace(stage / spec["filename"], cache_directory / spec["filename"])
    os.replace(stage / "manifest.json", cache_directory / "manifest.json")


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    target_duration_ms: int,
    inputs: Mapping[str, Mapping[str, Any]],
    probes: Mapping[str, Mapping[str, Any]],
    stage: Path,
    include_captioned: bool,
    caption_style: Mapping[str, Any],
    narration_duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    source_width: int,
    source_height: int,
) -> bytes:
    files: dict[str, dict[str, Any]] = {}
    for spec in _expected_files(include_captioned):
        if spec["filename"] == "manifest.json":
            continue
        path = stage / spec["filename"]
        stat = path.stat()
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    body: dict[str, Any] = {
        "schema_version": ASSEMBLY_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "duration_ms": target_duration_ms,
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "caption_style": dict(caption_style),
        "tool_identity": dict(tool_identity),
        "output_policy": _output_policy(include_captioned),
        "caption_policy": _caption_policy(caption_style),
        "resource_policy": _resource_policy(),
        "video_dimensions": {"width": source_width, "height": source_height},
        "audio_policy": _audio_policy(
            source_duration_ms=target_duration_ms,
            narration_duration_ms=narration_duration_ms,
        ),
        "inputs": dict(inputs),
        "media": {
            "source_video": probes["source_video"],
            "narration_wav": probes["narration_wav"],
            "master_clean": probes["master_clean"],
            "master_captioned": probes["master_captioned"],
        },
        "files": files,
    }
    manifest = dict(body)
    manifest["manifest_sha256"] = _manifest_digest(body)
    return (canonical_json(manifest) + "\n").encode("utf-8")


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
        "provider": PROVIDER,
        "provider_task_id": None,
        "timing_source": TIMING_SOURCE,
        "actual_cost": 0,
        "include_captioned": manifest["include_captioned"],
        "caption_style_preset": manifest["caption_style_preset"],
        "caption_style": dict(manifest["caption_style"]),
        "source_video_sha256": manifest["inputs"]["source_video"]["sha256"],
        "narration_wav_sha256": manifest["inputs"]["narration_wav"]["sha256"],
        "captions_sha256": manifest["inputs"]["captions_srt"]["sha256"],
        "output_directory": cache_directory.relative_to(workspace.resolve(strict=True)).as_posix(),
    }


def validate_local_assembly_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    source_video: str | Path,
    narration_wav: str | Path,
    captions_srt: str | Path,
    include_captioned: bool,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Revalidate an already-published assembly before artifact registration.

    This is intentionally independent from the generation path so the service
    can call it for a DB cache hit or immediately before registering artifacts.
    It rehashes all three inputs, re-probes source/narration and both output
    MP4s, verifies tool and policy identity, validates the manifest self-hash,
    and returns only exact metadata for the verified cache directory.
    """

    _raise_if_cancelled(cancel_event)
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    if not isinstance(include_captioned, bool):
        raise AssemblyValidationError("include_captioned must be a boolean")
    caption_style = _resolved_caption_style(
        caption_style_preset,
        include_captioned=include_captioned,
    )
    cache_key = _strict_cache_key(cache_key)
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    workspace = workspace.resolve(strict=True)
    source_path = _safe_file(
        workspace, source_video, label="source_video", maximum_bytes=MAX_SOURCE_VIDEO_BYTES
    )
    narration_path = _safe_file(
        workspace,
        narration_wav,
        label="narration_wav",
        maximum_bytes=MAX_NARRATION_WAV_BYTES,
    )
    captions_path = _safe_file(
        workspace,
        captions_srt,
        label="captions_srt",
        maximum_bytes=MAX_CAPTIONS_BYTES,
    )
    caption_data = _validate_caption_bytes(captions_path)
    _raise_if_cancelled(cancel_event)
    ffmpeg_executable = _find_tool("ffmpeg", ffmpeg)
    ffprobe_executable = _find_tool("ffprobe", ffprobe)
    resolved_tool_identity = {
        "ffmpeg": _tool_identity(
            "ffmpeg", ffmpeg_executable, cancel_event=cancel_event
        ),
        "ffprobe": _tool_identity(
            "ffprobe", ffprobe_executable, cancel_event=cancel_event
        ),
    }
    source_probe = _json_probe(
        ffprobe_executable, source_path, cwd=workspace, cancel_event=cancel_event
    )
    narration_probe = _json_probe(
        ffprobe_executable, narration_path, cwd=workspace, cancel_event=cancel_event
    )
    _raise_if_cancelled(cancel_event)
    target_duration_ms = _validate_source_probe(source_probe)
    source_width, source_height = _source_dimensions(source_probe)
    _validate_caption_timing(caption_data, source_duration_ms=target_duration_ms)
    narration_duration_ms = _validate_narration_probe(narration_probe)
    if narration_duration_ms > target_duration_ms + 250:
        raise AssemblyValidationError(
            "narration is longer than the source video",
            code="narration_longer_than_source",
        )
    input_records = {
        "source_video": _input_record(workspace, source_path),
        "narration_wav": _input_record(workspace, narration_path),
        "captions_srt": _input_record(workspace, captions_path),
    }
    expected_cache_key = assembly_cache_key(
        input_records["source_video"]["sha256"],
        input_records["narration_wav"]["sha256"],
        input_records["captions_srt"]["sha256"],
        include_captioned,
        caption_style_preset=caption_style["preset"],
        tool_identity=resolved_tool_identity,
    )
    _raise_if_cancelled(cancel_event)
    if cache_key != expected_cache_key:
        raise AssemblyValidationError(
            "cache_key does not match current inputs or local media tools",
            code="cache_key_mismatch",
        )
    output_directory = _safe_output_root(workspace, run_id, cache_key)
    cached = _validate_cache(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        inputs=input_records,
        target_duration_ms=target_duration_ms,
        include_captioned=include_captioned,
        caption_style=caption_style,
        narration_duration_ms=narration_duration_ms,
        source_width=source_width,
        source_height=source_height,
        tool_identity=resolved_tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    _raise_if_cancelled(cancel_event)
    if cached is None:
        raise AssemblyError(
            "published assembly cache failed integrity verification", code="invalid_cache"
        )
    manifest, artifacts = cached
    result = _result(workspace, output_directory, manifest, artifacts, cache_hit=True)
    result["manifest"] = manifest
    result["tool_identity"] = resolved_tool_identity
    return result


def assemble_local_video(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    source_video: str | Path,
    narration_wav: str | Path,
    captions_srt: str | Path,
    include_captioned: bool,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Create or reuse auditable clean and captioned local masters.

    All three media arguments may be absolute paths or paths relative to the
    resolved workspace.  They must be regular files inside that workspace;
    callers are responsible for selecting paths from their registered artifact
    records.  ``ffmpeg`` and ``ffprobe`` are optional executable overrides for
    deterministic tests and local installations.
    """

    _raise_if_cancelled(cancel_event)
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    if not isinstance(include_captioned, bool):
        raise AssemblyValidationError("include_captioned must be a boolean")
    caption_style = _resolved_caption_style(
        caption_style_preset,
        include_captioned=include_captioned,
    )
    cache_key = _strict_cache_key(cache_key)
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    workspace = workspace.resolve(strict=True)
    source_path = _safe_file(
        workspace, source_video, label="source_video", maximum_bytes=MAX_SOURCE_VIDEO_BYTES
    )
    narration_path = _safe_file(
        workspace,
        narration_wav,
        label="narration_wav",
        maximum_bytes=MAX_NARRATION_WAV_BYTES,
    )
    captions_path = _safe_file(
        workspace,
        captions_srt,
        label="captions_srt",
        maximum_bytes=MAX_CAPTIONS_BYTES,
    )
    _validate_caption_bytes(captions_path)
    _raise_if_cancelled(cancel_event)
    ffmpeg_executable = _find_tool("ffmpeg", ffmpeg)
    ffprobe_executable = _find_tool("ffprobe", ffprobe)
    resolved_tool_identity = {
        "ffmpeg": _tool_identity(
            "ffmpeg", ffmpeg_executable, cancel_event=cancel_event
        ),
        "ffprobe": _tool_identity(
            "ffprobe", ffprobe_executable, cancel_event=cancel_event
        ),
    }
    _raise_if_cancelled(cancel_event)
    output_directory = _safe_output_root(workspace, run_id, cache_key)
    # Keep ffprobe's working directory local and stable.  It also ensures the
    # subtitle filter never has to parse a Windows absolute path.
    probe_cwd = workspace
    source_probe = _json_probe(
        ffprobe_executable, source_path, cwd=probe_cwd, cancel_event=cancel_event
    )
    narration_probe = _json_probe(
        ffprobe_executable, narration_path, cwd=probe_cwd, cancel_event=cancel_event
    )
    _raise_if_cancelled(cancel_event)
    target_duration_ms = _validate_source_probe(source_probe)
    source_width, source_height = _source_dimensions(source_probe)
    caption_data = _validate_caption_bytes(captions_path)
    _validate_caption_timing(caption_data, source_duration_ms=target_duration_ms)
    narration_duration_ms = _validate_narration_probe(narration_probe)
    if narration_duration_ms > target_duration_ms + 250:
        raise AssemblyValidationError(
            "narration is longer than the source video",
            code="narration_longer_than_source",
        )
    input_records = {
        "source_video": _input_record(workspace, source_path),
        "narration_wav": _input_record(workspace, narration_path),
        "captions_srt": _input_record(workspace, captions_path),
    }
    expected_cache_key = assembly_cache_key(
        input_records["source_video"]["sha256"],
        input_records["narration_wav"]["sha256"],
        input_records["captions_srt"]["sha256"],
        include_captioned,
        caption_style_preset=caption_style["preset"],
        tool_identity=resolved_tool_identity,
    )
    _raise_if_cancelled(cancel_event)
    if cache_key != expected_cache_key:
        raise AssemblyValidationError(
            "cache_key does not match current inputs or local media tools",
            code="cache_key_mismatch",
        )
    cached = _validate_cache(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        inputs=input_records,
        target_duration_ms=target_duration_ms,
        include_captioned=include_captioned,
        caption_style=caption_style,
        narration_duration_ms=narration_duration_ms,
        source_width=source_width,
        source_height=source_height,
        tool_identity=resolved_tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    _raise_if_cancelled(cancel_event)
    if cached is not None:
        manifest, artifacts = cached
        return _result(workspace, output_directory, manifest, artifacts, cache_hit=True)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    duration_seconds = f"{target_duration_ms / 1000:.3f}"
    stage = Path(tempfile.mkdtemp(prefix=f".{cache_key[:16]}-", dir=str(output_directory.parent)))
    try:
        _raise_if_cancelled(cancel_event)
        # Fixed local names are used only for subprocess inputs.  Source and
        # narration are copied so no filter or cwd argument contains user path
        # syntax; source remains independently hash-checked above.
        shutil.copyfile(source_path, stage / "source-video.mp4")
        shutil.copyfile(narration_path, stage / "narration.wav")
        _raise_if_cancelled(cancel_event)
        _assert_input_unchanged(source_path, input_records["source_video"], label="source_video")
        _assert_input_unchanged(narration_path, input_records["narration_wav"], label="narration_wav")
        _assert_input_unchanged(captions_path, input_records["captions_srt"], label="captions_srt")
        if _sha256_file(stage / "source-video.mp4") != input_records["source_video"]["sha256"]:
            raise AssemblyError("source_video changed during staging", code="input_changed")
        if _sha256_file(stage / "narration.wav") != input_records["narration_wav"]["sha256"]:
            raise AssemblyError("narration_wav changed during staging", code="input_changed")
        stage_source_probe = _json_probe(
            ffprobe_executable,
            Path("source-video.mp4"),
            cwd=stage,
            cancel_event=cancel_event,
        )
        stage_narration_probe = _json_probe(
            ffprobe_executable,
            Path("narration.wav"),
            cwd=stage,
            cancel_event=cancel_event,
        )
        _raise_if_cancelled(cancel_event)
        if _validate_source_probe(stage_source_probe) != target_duration_ms:
            raise AssemblyError("staged source video changed", code="input_changed")
        if _validate_narration_probe(stage_narration_probe) != narration_duration_ms:
            raise AssemblyError("staged narration changed", code="input_changed")
        if _source_dimensions(stage_source_probe) != (source_width, source_height):
            raise AssemblyError("staged source dimensions changed", code="input_changed")
        if _sha256_bytes(caption_data) != input_records["captions_srt"]["sha256"]:
            raise AssemblyError("captions_srt changed during staging", code="input_changed")
        _write_atomic(
            stage / "captions.ass",
            _build_ass(
                caption_data,
                width=source_width,
                height=source_height,
                caption_style_preset=caption_style["preset"],
            ),
        )
        filter_path = stage / "filter-script.txt"
        _write_atomic(
            filter_path,
            # The filter script is evaluated with ``cwd=stage``.  Keep this a
            # fixed relative filename: an absolute Windows path containing an
            # apostrophe is parsed as filter syntax even when escaped for a
            # shell, while this name contains no user-controlled characters.
            b"subtitles='captions.ass'\n",
        )
        _raise_if_cancelled(cancel_event)
        clean_path = stage / "master-clean.mp4"
        captioned_path = stage / "master-captioned.mp4"
        _bounded_process(
            [
                ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                "source-video.mp4",
                "-i",
                "narration.wav",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-af",
                "apad",
                "-t",
                duration_seconds,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-threads",
                str(FFMPEG_THREADS),
                "-filter_threads",
                str(FFMPEG_THREADS),
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                "-fs",
                str(MAX_OUTPUT_BYTES),
                "master-clean.mp4",
            ],
            cwd=stage,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            label="ffmpeg clean assembly",
            cancel_event=cancel_event,
        )
        _raise_if_cancelled(cancel_event)
        if not clean_path.is_file() or clean_path.stat().st_size <= 0 or clean_path.stat().st_size > MAX_OUTPUT_BYTES:
            raise AssemblyError("FFmpeg clean output is unavailable", code="invalid_output_media")
        _validate_output_probe(
            _json_probe(
                ffprobe_executable,
                Path("master-clean.mp4"),
                cwd=stage,
                cancel_event=cancel_event,
            ),
            target_duration_ms=target_duration_ms,
            expected_width=source_width,
            expected_height=source_height,
        )
        _raise_if_cancelled(cancel_event)
        if include_captioned:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    "master-clean.mp4",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-filter_script:v",
                    "filter-script.txt",
                    "-t",
                    duration_seconds,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-threads",
                    str(FFMPEG_THREADS),
                    "-filter_threads",
                    str(FFMPEG_THREADS),
                    "-map_metadata",
                    "-1",
                    "-movflags",
                    "+faststart",
                    "-fs",
                    str(MAX_OUTPUT_BYTES),
                    "master-captioned.mp4",
                ],
                cwd=stage,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="ffmpeg caption assembly",
                cancel_event=cancel_event,
            )
            _raise_if_cancelled(cancel_event)
            if not captioned_path.is_file() or captioned_path.stat().st_size <= 0 or captioned_path.stat().st_size > MAX_OUTPUT_BYTES:
                raise AssemblyError("FFmpeg captioned output is unavailable", code="invalid_output_media")
        clean_probe = _json_probe(
            ffprobe_executable,
            Path("master-clean.mp4"),
            cwd=stage,
            cancel_event=cancel_event,
        )
        _validate_output_probe(
            clean_probe,
            target_duration_ms=target_duration_ms,
            expected_width=source_width,
            expected_height=source_height,
        )
        captioned_probe = None
        if include_captioned:
            captioned_probe = _json_probe(
                ffprobe_executable,
                Path("master-captioned.mp4"),
                cwd=stage,
                cancel_event=cancel_event,
            )
            _validate_output_probe(
                captioned_probe,
                target_duration_ms=target_duration_ms,
                expected_width=source_width,
                expected_height=source_height,
            )
        _raise_if_cancelled(cancel_event)
        _assert_input_unchanged(source_path, input_records["source_video"], label="source_video")
        _assert_input_unchanged(narration_path, input_records["narration_wav"], label="narration_wav")
        _assert_input_unchanged(captions_path, input_records["captions_srt"], label="captions_srt")
        _raise_if_cancelled(cancel_event)
        ffprobe_document = {
            "schema_version": ASSEMBLY_SCHEMA_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
            "timing_source": TIMING_SOURCE,
            "source_video": stage_source_probe,
            "narration_wav": stage_narration_probe,
            "master_clean": clean_probe,
            "master_captioned": captioned_probe,
        }
        _write_atomic(
            stage / "ffprobe.json",
            (canonical_json(ffprobe_document) + "\n").encode("utf-8"),
        )
        _write_atomic(
            stage / "manifest.json",
            _build_manifest(
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                target_duration_ms=target_duration_ms,
                inputs=input_records,
                probes={
                    "source_video": stage_source_probe,
                    "narration_wav": stage_narration_probe,
                    "master_clean": clean_probe,
                    "master_captioned": captioned_probe,
                },
                stage=stage,
                include_captioned=include_captioned,
                caption_style=caption_style,
                narration_duration_ms=narration_duration_ms,
                tool_identity=resolved_tool_identity,
                source_width=source_width,
                source_height=source_height,
            ),
        )
        _raise_if_cancelled(cancel_event)
        _publish(stage, output_directory, include_captioned=include_captioned)
    except AssemblyError:
        raise
    except (OSError, shutil.Error) as exc:
        raise AssemblyError("local assembly could not be published") from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    cached = _validate_cache(
        workspace,
        output_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        inputs=input_records,
        target_duration_ms=target_duration_ms,
        include_captioned=include_captioned,
        caption_style=caption_style,
        narration_duration_ms=narration_duration_ms,
        source_width=source_width,
        source_height=source_height,
        tool_identity=resolved_tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    _raise_if_cancelled(cancel_event)
    if cached is None:
        raise AssemblyError("generated assembly cache failed integrity verification", code="invalid_cache")
    manifest, artifacts = cached
    return _result(workspace, output_directory, manifest, artifacts, cache_hit=False)


# The narration worker uses the ``generate_local_*`` naming convention.  Keep
# this alias so callers can choose the stage-oriented name without wrapping the
# implementation or losing the strict result contract.
generate_local_assembly = assemble_local_video


__all__ = [
    "ASSEMBLY_SCHEMA_VERSION",
    "AssemblyError",
    "AssemblyToolError",
    "AssemblyValidationError",
    "IMPLEMENTATION_VERSION",
    "assembly_cache_key",
    "assemble_local_video",
    "generate_local_assembly",
    "resolve_tool_identity",
    "validate_local_assembly_outputs",
]
