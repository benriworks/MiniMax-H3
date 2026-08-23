"""Auditable local narration generation for Studio.

The default provider is Windows SAPI (``System.Speech``) invoked through a
small PowerShell script.  The public function also accepts an injectable
synthesizer so tests and future local providers do not need a Windows voice
installation.  The worker deliberately owns only files below
``outputs/studio/runs`` and never calls a network API.
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .security import canonical_json, validate_identifier, workspace_path


NARRATION_SCHEMA_VERSION = 1
IMPLEMENTATION_VERSION = "local-sapi-v1"
MAX_SEGMENTS = 100
MAX_SEGMENT_CHARS = 4_000
MAX_TOTAL_CHARS = 100_000
MAX_PRONUNCIATIONS = 100
MAX_PRONUNCIATION_CHARS = 512
MAX_VOICE_CHARS = 128
MIN_RATE = -10
MAX_RATE = 10
SAPI_TIMEOUT_SECONDS = 120
SAPI_PREFLIGHT_TIMEOUT_SECONDS = 30
SAPI_PREFLIGHT_POLL_SECONDS = 0.1
SAPI_PROCESS_REAP_TIMEOUT_SECONDS = 5
MAX_SEGMENT_WAV_BYTES = 32 * 1024 * 1024
MAX_NARRATION_WAV_BYTES = 128 * 1024 * 1024
MAX_NARRATION_DURATION_MS = 30 * 60 * 1000

_ALLOWED_PAYLOAD_KEYS = {"segments", "voice", "rate", "pronunciations"}
_ALLOWED_SEGMENT_KEYS = {"text"}
_ALLOWED_PRONUNCIATION_KEYS = {"source", "target"}
_CONTROL_CHARS = frozenset(chr(value) for value in range(32)) | {chr(127)}


class NarrationError(ValueError):
    """Raised when narration input or a generated WAV is invalid."""

    error_code = "narration_invalid"


class NarrationPreflightError(RuntimeError):
    """Raised when the local Windows SAPI runtime cannot be used."""

    error_code = "windows_sapi_unavailable"


class NarrationSynthesisError(RuntimeError):
    """Raised when a local synthesizer does not produce a valid WAV."""

    error_code = "narration_synthesis_failed"


@dataclass(frozen=True)
class _NarrationInput:
    segments: tuple[str, ...]
    synthesis_segments: tuple[str, ...]
    voice: str | None
    rate: int
    pronunciations: tuple[dict[str, str], ...]
    payload: dict[str, Any]
    payload_digest: str


@dataclass(frozen=True)
class _WavSegment:
    frames: bytes
    frame_count: int
    channels: int
    sample_width: int
    sample_rate: int
    compression: str


_FILE_SPECS: tuple[dict[str, str], ...] = (
    {
        "filename": "narration.wav",
        "kind": "audio",
        "mime": "audio/wav",
    },
    {
        "filename": "captions.srt",
        "kind": "subtitle",
        "mime": "application/x-subrip",
    },
    {
        "filename": "timings.json",
        "kind": "document",
        "mime": "application/json",
    },
    {
        "filename": "manifest.json",
        "kind": "document",
        "mime": "application/json",
    },
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _contains_control(value: str) -> bool:
    return any(character in _CONTROL_CHARS for character in value)


def _validate_text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise NarrationError(f"{label} must be a string")
    if not value.strip():
        raise NarrationError(f"{label} must not be empty")
    if len(value) > maximum:
        raise NarrationError(f"{label} is too long")
    if _contains_control(value):
        raise NarrationError(f"{label} contains unsupported control characters")
    return value


def _validate_narration_payload(payload: dict[str, Any]) -> _NarrationInput:
    if not isinstance(payload, dict):
        raise NarrationError("payload must be an object")
    if any(not isinstance(key, str) for key in payload):
        raise NarrationError("payload keys must be strings")
    unknown = set(payload) - _ALLOWED_PAYLOAD_KEYS
    if unknown:
        raise NarrationError("payload contains unsupported fields")

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise NarrationError("segments must be a non-empty array")
    if len(raw_segments) > MAX_SEGMENTS:
        raise NarrationError("segments contains too many entries")
    segments: list[str] = []
    total_chars = 0
    for index, segment in enumerate(raw_segments, start=1):
        if not isinstance(segment, dict):
            raise NarrationError(f"segment {index} must be an object")
        if any(not isinstance(key, str) for key in segment):
            raise NarrationError(f"segment {index} has invalid keys")
        if set(segment) - _ALLOWED_SEGMENT_KEYS:
            raise NarrationError(f"segment {index} contains unsupported fields")
        text = _validate_text(
            segment.get("text"), label=f"segment {index} text", maximum=MAX_SEGMENT_CHARS
        )
        total_chars += len(text)
        if total_chars > MAX_TOTAL_CHARS:
            raise NarrationError("narration text is too long")
        segments.append(text)

    raw_voice = payload.get("voice")
    if raw_voice is None or raw_voice == "":
        voice: str | None = None
    else:
        if not isinstance(raw_voice, str):
            raise NarrationError("voice must be a string")
        if len(raw_voice) > MAX_VOICE_CHARS or _contains_control(raw_voice):
            raise NarrationError("voice is invalid")
        voice = raw_voice

    raw_rate = payload.get("rate", 0)
    if isinstance(raw_rate, bool) or not isinstance(raw_rate, int):
        raise NarrationError("rate must be an integer")
    if not MIN_RATE <= raw_rate <= MAX_RATE:
        raise NarrationError(f"rate must be between {MIN_RATE} and {MAX_RATE}")
    rate = raw_rate

    raw_pronunciations = payload.get("pronunciations", [])
    if raw_pronunciations is None:
        raw_pronunciations = []
    if not isinstance(raw_pronunciations, list):
        raise NarrationError("pronunciations must be an array")
    if len(raw_pronunciations) > MAX_PRONUNCIATIONS:
        raise NarrationError("pronunciations contains too many entries")
    pronunciations: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for index, pronunciation in enumerate(raw_pronunciations, start=1):
        if not isinstance(pronunciation, dict):
            raise NarrationError(f"pronunciation {index} must be an object")
        if any(not isinstance(key, str) for key in pronunciation):
            raise NarrationError(f"pronunciation {index} has invalid keys")
        if set(pronunciation) - _ALLOWED_PRONUNCIATION_KEYS:
            raise NarrationError(f"pronunciation {index} contains unsupported fields")
        source = _validate_text(
            pronunciation.get("source"),
            label=f"pronunciation {index} source",
            maximum=MAX_PRONUNCIATION_CHARS,
        )
        target = _validate_text(
            pronunciation.get("target"),
            label=f"pronunciation {index} target",
            maximum=MAX_PRONUNCIATION_CHARS,
        )
        if source in seen_sources:
            raise NarrationError("pronunciation sources must be unique")
        seen_sources.add(source)
        pronunciations.append({"source": source, "target": target})

    normalized_payload: dict[str, Any] = {
        "segments": [{"text": text} for text in segments],
        "voice": voice,
        "rate": rate,
        "pronunciations": pronunciations,
    }
    payload_digest = _sha256_bytes(canonical_json(normalized_payload).encode("utf-8"))
    synthesis_segments = tuple(
        _apply_pronunciations(text, pronunciations) for text in segments
    )
    if any(not text.strip() for text in synthesis_segments):
        raise NarrationError("pronunciation replacement produced empty narration text")
    return _NarrationInput(
        segments=tuple(segments),
        synthesis_segments=synthesis_segments,
        voice=voice,
        rate=rate,
        pronunciations=tuple(pronunciations),
        payload=normalized_payload,
        payload_digest=payload_digest,
    )


def _apply_pronunciations(text: str, pronunciations: list[dict[str, str]]) -> str:
    result = text
    for pronunciation in pronunciations:
        result = result.replace(pronunciation["source"], pronunciation["target"])
    return result


def _cache_key(settings: _NarrationInput) -> str:
    value = {
        "schema_version": NARRATION_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "payload": settings.payload,
    }
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _narration_root(workspace: Path, run_id: str) -> Path:
    return workspace_path(
        workspace,
        Path("outputs") / "studio" / "runs" / run_id / "narration",
    )


def _cache_directory(workspace: Path, run_id: str, cache_key: str) -> Path:
    return workspace_path(workspace, _narration_root(workspace, run_id) / cache_key)


def _safe_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_record(workspace: Path, cache_directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
    if not _safe_file(path):
        raise NarrationError(f"narration artifact is unavailable: {spec['filename']}")
    stat = path.stat()
    relative = path.relative_to(workspace.resolve(strict=True)).as_posix()
    digest = _sha256_file(path)
    mime = spec["mime"]
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": stat.st_size,
        "sha256": digest,
        "mime": mime,
        "media_type": mime,
        "origin": "studio",
        "version": IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _manifest_self_digest(manifest_without_digest: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(manifest_without_digest).encode("utf-8"))


def _validate_manifest(
    workspace: Path,
    cache_directory: Path,
    manifest: Any,
    *,
    settings: _NarrationInput,
    production_id: str,
    run_id: str,
    cache_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not isinstance(manifest, dict):
        return None
    manifest_digest = manifest.get("manifest_sha256")
    if not isinstance(manifest_digest, str):
        return None
    manifest_without_digest = dict(manifest)
    manifest_without_digest.pop("manifest_sha256", None)
    if _manifest_self_digest(manifest_without_digest) != manifest_digest.upper():
        return None
    if manifest.get("schema_version") != NARRATION_SCHEMA_VERSION:
        return None
    if manifest.get("implementation_version") != IMPLEMENTATION_VERSION:
        return None
    if manifest.get("production_id") != production_id or manifest.get("run_id") != run_id:
        return None
    if manifest.get("cache_key") != cache_key or manifest.get("payload_digest") != settings.payload_digest:
        return None
    if manifest.get("provider") != "windows_sapi":
        return None
    files = manifest.get("files")
    if not isinstance(files, dict):
        return None
    expected_names = {spec["filename"] for spec in _FILE_SPECS if spec["filename"] != "manifest.json"}
    if set(files) != expected_names:
        return None
    for spec in _FILE_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        entry = files.get(spec["filename"])
        path = cache_directory / spec["filename"]
        if not isinstance(entry, dict) or not _safe_file(path):
            return None
        if entry.get("path") != spec["filename"]:
            return None
        if entry.get("kind") != spec["kind"] or entry.get("mime") != spec["mime"]:
            return None
        expected_bytes = entry.get("bytes")
        expected_sha = entry.get("sha256")
        if (
            isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
            or expected_bytes < 0
            or not isinstance(expected_sha, str)
            or len(expected_sha) != 64
        ):
            return None
        if path.stat().st_size != expected_bytes or _sha256_file(path) != expected_sha.upper():
            return None
    duration_ms = manifest.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        return None
    segments = manifest.get("segments")
    if not isinstance(segments, list) or len(segments) != len(settings.segments):
        return None
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            return None
        if segment.get("index") != index or segment.get("text") != settings.segments[index]:
            return None
    try:
        artifacts = [
            _artifact_record(workspace, cache_directory, spec) for spec in _FILE_SPECS
        ]
    except (OSError, ValueError):
        return None
    return manifest, artifacts


def _load_valid_cache(
    workspace: Path,
    cache_directory: Path,
    *,
    settings: _NarrationInput,
    production_id: str,
    run_id: str,
    cache_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    manifest_path = cache_directory / "manifest.json"
    if not cache_directory.is_dir() or cache_directory.is_symlink() or not _safe_file(manifest_path):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return _validate_manifest(
        workspace,
        cache_directory,
        manifest,
        settings=settings,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
    )


def _format_srt_time(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _read_wav(data: bytes, *, label: str) -> _WavSegment:
    if len(data) > MAX_SEGMENT_WAV_BYTES:
        raise NarrationSynthesisError(f"{label} WAV is too large")
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            compression = handle.getcomptype()
            frame_count = handle.getnframes()
            frames = handle.readframes(frame_count)
    except (EOFError, wave.Error, ValueError) as exc:
        raise NarrationSynthesisError(f"{label} did not produce a valid WAV") from exc
    if (
        channels <= 0
        or sample_width <= 0
        or sample_rate <= 0
        or compression != "NONE"
        or frame_count <= 0
        or frame_count * channels * sample_width > MAX_SEGMENT_WAV_BYTES
        or len(frames) != frame_count * channels * sample_width
    ):
        raise NarrationSynthesisError(f"{label} produced an unsupported WAV format")
    return _WavSegment(
        frames=frames,
        frame_count=frame_count,
        channels=channels,
        sample_width=sample_width,
        sample_rate=sample_rate,
        compression=compression,
    )


def _join_wav(segments: list[_WavSegment]) -> tuple[bytes, list[dict[str, int]], int]:
    if not segments:
        raise NarrationSynthesisError("narration has no audio segments")
    first = segments[0]
    for segment in segments[1:]:
        if (
            segment.channels,
            segment.sample_width,
            segment.sample_rate,
            segment.compression,
        ) != (
            first.channels,
            first.sample_width,
            first.sample_rate,
            first.compression,
        ):
            raise NarrationSynthesisError("all narration WAV segments must share one format")
    total_frame_bytes = sum(len(segment.frames) for segment in segments)
    total_frames = sum(segment.frame_count for segment in segments)
    duration_ms = (total_frames * 1_000) // first.sample_rate
    if total_frame_bytes > MAX_NARRATION_WAV_BYTES:
        raise NarrationSynthesisError("narration WAV is too large")
    if duration_ms > MAX_NARRATION_DURATION_MS:
        raise NarrationSynthesisError("narration duration is too long")
    frames = b"".join(segment.frames for segment in segments)
    output = io.BytesIO()
    try:
        with wave.open(output, "wb") as handle:
            handle.setnchannels(first.channels)
            handle.setsampwidth(first.sample_width)
            handle.setframerate(first.sample_rate)
            handle.setcomptype("NONE", "not compressed")
            handle.writeframes(frames)
    except (wave.Error, ValueError) as exc:
        raise NarrationSynthesisError("could not create narration WAV") from exc
    frame_cursor = 0
    timings: list[dict[str, int]] = []
    for index, segment in enumerate(segments):
        start_ms = (frame_cursor * 1_000) // first.sample_rate
        frame_cursor += segment.frame_count
        end_ms = (frame_cursor * 1_000) // first.sample_rate
        timings.append(
            {
                "index": index,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": end_ms - start_ms,
                "frames": segment.frame_count,
            }
        )
    duration_ms = (frame_cursor * 1_000) // first.sample_rate
    return output.getvalue(), timings, duration_ms


def _build_captions(segments: tuple[str, ...], timings: list[dict[str, int]]) -> bytes:
    blocks: list[str] = []
    for index, (text, timing) in enumerate(zip(segments, timings, strict=True), start=1):
        blocks.append(
            "\n".join(
                (
                    str(index),
                    f"{_format_srt_time(timing['start_ms'])} --> {_format_srt_time(timing['end_ms'])}",
                    text,
                    "",
                )
            )
        )
    return "\n".join(blocks).encode("utf-8")


def _build_manifest(
    settings: _NarrationInput,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    duration_ms: int,
    timings: list[dict[str, int]],
    stage_directory: Path,
) -> bytes:
    files: dict[str, dict[str, Any]] = {}
    for spec in _FILE_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = stage_directory / spec["filename"]
        stat = path.stat()
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    segments: list[dict[str, Any]] = []
    for index, (original, synthesized, timing) in enumerate(
        zip(settings.segments, settings.synthesis_segments, timings, strict=True)
    ):
        segments.append(
            {
                "index": index,
                "text": original,
                "text_sha256": _sha256_bytes(original.encode("utf-8")),
                "synthesis_text_sha256": _sha256_bytes(synthesized.encode("utf-8")),
                **timing,
            }
        )
    manifest_without_digest: dict[str, Any] = {
        "schema_version": NARRATION_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "payload_digest": settings.payload_digest,
        "provider": "windows_sapi",
        "provider_task_id": None,
        "voice": settings.voice,
        "rate": settings.rate,
        "actual_cost": 0,
        "timing_source": "wav_frames",
        "sample_rate": timings[0].get("sample_rate", 0) if timings else 0,
        "duration_ms": duration_ms,
        "segments": segments,
        "pronunciations": list(settings.pronunciations),
        "files": files,
    }
    # ``sample_rate`` is part of the WAV format, not timing rows.  Keep the
    # manifest deterministic without duplicating a value that is unavailable
    # here; timings.json carries the authoritative sample rate.
    manifest_without_digest.pop("sample_rate", None)
    manifest = dict(manifest_without_digest)
    manifest["manifest_sha256"] = _manifest_self_digest(manifest_without_digest)
    return (canonical_json(manifest) + "\n").encode("utf-8")


def _find_powershell() -> str | None:
    if os.name == "nt":
        candidates: list[Path] = []
        system_root = os.environ.get("SystemRoot")
        if system_root:
            candidates.append(
                Path(system_root)
                / "System32"
                / "WindowsPowerShell"
                / "v1.0"
                / "powershell.exe"
            )
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            candidates.append(Path(program_files) / "PowerShell" / "7" / "pwsh.exe")
        for candidate in candidates:
            if candidate.is_file() and not candidate.is_symlink():
                return str(candidate.resolve(strict=True))
    for executable in ("powershell.exe", "pwsh.exe", "pwsh"):
        found = shutil.which(executable)
        if found:
            return found
    return None


def _sapi_script_path() -> Path:
    return Path(__file__).with_name("sapi_synthesize.ps1")


def _raise_if_cancelled(cancel_event: Any = None) -> None:
    if cancel_event is None:
        return
    raise_if_cancelled = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(raise_if_cancelled):
        raise_if_cancelled()
    elif callable(getattr(cancel_event, "is_set", None)) and cancel_event.is_set():
        raise NarrationSynthesisError("Windows SAPI synthesis was interrupted.")


def _terminate_sapi_process_tree(process: Any) -> None:
    """Terminate a SAPI PowerShell process and its descendants.

    ``JobExecutionContext`` owns the process registry, while ``jobs`` owns the
    platform-specific tree termination.  Keep a direct ``kill`` fallback for
    lightweight test doubles and installations where the shared helper cannot
    be imported; the public narration error never includes process details.
    """

    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0:
        try:
            from .jobs import _terminate_process_tree

            _terminate_process_tree(pid)
            return
        except (ImportError, OSError, RuntimeError, TypeError, subprocess.SubprocessError):
            pass
    kill = getattr(process, "kill", None)
    if callable(kill):
        try:
            kill()
        except (OSError, ProcessLookupError, subprocess.SubprocessError):
            pass


def _reap_sapi_process(process: Any) -> None:
    """Reap a terminated preflight process without waiting indefinitely."""

    communicate = getattr(process, "communicate", None)
    if not callable(communicate):
        return
    try:
        communicate(timeout=SAPI_PROCESS_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        kill = getattr(process, "kill", None)
        if callable(kill):
            try:
                kill()
            except (OSError, ProcessLookupError, subprocess.SubprocessError):
                pass
        try:
            communicate(timeout=1)
        except (OSError, subprocess.SubprocessError):
            pass
    except (OSError, subprocess.SubprocessError):
        pass


def preflight_local_sapi(*, cancel_event: Any = None) -> dict[str, Any]:
    """Check that the local Windows PowerShell/System.Speech runtime works.

    This intentionally returns only capability metadata.  PowerShell output is
    not copied into logs because it can contain installation-specific details.
    """

    if os.name != "nt":
        raise NarrationPreflightError("Windows SAPI is available only on Windows.")
    executable = _find_powershell()
    script = _sapi_script_path()
    if executable is None:
        raise NarrationPreflightError("Windows PowerShell was not found for SAPI.")
    if not script.is_file():
        raise NarrationPreflightError("The local SAPI helper script is missing.")
    _raise_if_cancelled(cancel_event)
    arguments = [
        executable,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Preflight",
    ]
    process: subprocess.Popen[bytes] | None = None
    registered = False
    completed = False
    try:
        # Preflight output is installation-specific and is not part of the
        # public diagnostic contract.  DEVNULL keeps that contract bounded
        # even if a broken PowerShell emits an unexpectedly large stream.
        process = subprocess.Popen(
            arguments,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        register_process = getattr(cancel_event, "register_process", None)
        if callable(register_process):
            register_process(process)
            registered = True
        _raise_if_cancelled(cancel_event)
        deadline = time.monotonic() + SAPI_PREFLIGHT_TIMEOUT_SECONDS
        while True:
            _raise_if_cancelled(cancel_event)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(arguments, SAPI_PREFLIGHT_TIMEOUT_SECONDS)
            try:
                process.communicate(timeout=min(SAPI_PREFLIGHT_POLL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        _raise_if_cancelled(cancel_event)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, arguments)
        completed = True
    except subprocess.TimeoutExpired as exc:
        raise NarrationPreflightError(
            "Windows SAPI preflight failed; install or enable System.Speech voices."
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise NarrationPreflightError(
            "Windows SAPI preflight failed; install or enable System.Speech voices."
        ) from exc
    finally:
        if process is not None:
            poll = getattr(process, "poll", None)
            try:
                running = not callable(poll) or poll() is None
            except (OSError, subprocess.SubprocessError):
                running = True
            if not completed and running:
                _terminate_sapi_process_tree(process)
                _reap_sapi_process(process)
            if registered:
                unregister_process = getattr(cancel_event, "unregister_process", None)
                if callable(unregister_process):
                    try:
                        unregister_process(process)
                    except Exception:
                        # Registry cleanup must not replace the capability
                        # result or the bounded public failure above.
                        pass
    return {"provider": "windows_sapi", "available": True}


def _synthesize_sapi(
    text: str,
    *,
    voice: str | None,
    rate: int,
    workspace: Path,
    cancel_event: Any = None,
) -> bytes:
    executable = _find_powershell()
    script = _sapi_script_path()
    if os.name != "nt" or executable is None or not script.is_file():
        # Keep the public error identical to preflight without requiring a
        # second PowerShell invocation for every segment.
        preflight_local_sapi(cancel_event=cancel_event)
        raise NarrationPreflightError("Windows SAPI is unavailable.")
    temporary_directory = Path(tempfile.mkdtemp(prefix=".sapi-", dir=str(workspace)))
    input_path = temporary_directory / "request.json"
    output_path = temporary_directory / "output.wav"
    try:
        input_path.write_text(
            json.dumps(
                {"text": text, "voice": voice, "rate": rate},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
            newline="\n",
        )
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-InputJsonPath",
                    str(input_path),
                    "-OutputWavPath",
                    str(output_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            register_process = getattr(cancel_event, "register_process", None)
            if callable(register_process):
                register_process(process)
            _raise_if_cancelled(cancel_event)
            try:
                process.communicate(timeout=SAPI_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                try:
                    process.kill()
                    process.communicate(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    pass
                raise NarrationSynthesisError("Windows SAPI synthesis failed.") from exc
            if process.returncode != 0:
                raise NarrationSynthesisError("Windows SAPI synthesis failed.")
        except (OSError, subprocess.SubprocessError) as exc:
            raise NarrationSynthesisError("Windows SAPI synthesis failed.") from exc
        finally:
            unregister_process = getattr(cancel_event, "unregister_process", None)
            if process is not None and callable(unregister_process):
                unregister_process(process)
        if not _safe_file(output_path):
            raise NarrationSynthesisError("Windows SAPI produced no WAV output.")
        if output_path.stat().st_size > MAX_SEGMENT_WAV_BYTES:
            raise NarrationSynthesisError("Windows SAPI produced an oversized WAV output.")
        return output_path.read_bytes()
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


def _call_injected_synthesizer(
    synthesizer: Any,
    text: str,
    *,
    voice: str | None,
    rate: int,
) -> bytes:
    method: Callable[..., Any]
    if hasattr(synthesizer, "synthesize") and callable(synthesizer.synthesize):
        method = synthesizer.synthesize
    elif callable(synthesizer):
        method = synthesizer
    else:
        raise NarrationError("synthesizer must be callable or expose synthesize()")
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None
    try:
        if signature is None:
            result = method(text, voice=voice, rate=rate)
        else:
            parameters = signature.parameters
            positional = [
                parameter
                for parameter in parameters.values()
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            # Keep simple test doubles and local adapters ergonomic even when
            # they call the two optional arguments ``v`` and ``r`` rather than
            # using the public names.
            named_voice = "voice" in parameters
            named_rate = "rate" in parameters
            if len(positional) >= 3 and not named_voice and not named_rate:
                result = method(text, voice, rate)
            elif len(positional) >= 2 and not named_voice and not named_rate:
                result = method(text, voice)
            else:
                kwargs: dict[str, Any] = {}
                if "voice" in parameters or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters.values()
                ):
                    kwargs["voice"] = voice
                if "rate" in parameters or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters.values()
                ):
                    kwargs["rate"] = rate
                result = method(text, **kwargs)
    except TypeError as exc:
        raise NarrationSynthesisError("injected synthesizer invocation failed.") from exc
    if isinstance(result, Mapping):
        result = result.get("wav")
    if isinstance(result, bytearray):
        result = bytes(result)
    if not isinstance(result, bytes):
        raise NarrationSynthesisError("injected synthesizer must return WAV bytes")
    return result


def _result(
    workspace: Path,
    cache_directory: Path,
    manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "provider": "windows_sapi",
        "provider_task_id": None,
        "timing_source": manifest.get("timing_source", "wav_frames"),
        "actual_cost": 0,
        "voice": manifest.get("voice"),
        "rate": manifest.get("rate", 0),
        "pronunciations": manifest.get("pronunciations", []),
    }


def generate_local_narration(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: dict[str, Any],
    synthesizer: Any = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    """Generate local narration WAV, captions, timings, and manifest.

    ``synthesizer`` is intentionally injectable.  It may be a callable or an
    object exposing ``synthesize(text, voice=..., rate=...)`` and must return
    WAV bytes.  With ``None`` the Windows SAPI subprocess adapter is used.
    """

    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    _raise_if_cancelled(cancel_event)
    workspace = workspace.resolve(strict=True)
    settings = _validate_narration_payload(payload)
    cache_key = _cache_key(settings)
    root = _narration_root(workspace, run_id)
    root.mkdir(parents=True, exist_ok=True)
    cache_directory = _cache_directory(workspace, run_id, cache_key)
    if cache_directory.exists() and not cache_directory.is_dir():
        raise NarrationError("narration cache path is not a directory")
    cached = _load_valid_cache(
        workspace,
        cache_directory,
        settings=settings,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
    )
    if cached is not None:
        manifest, artifacts = cached
        return _result(workspace, cache_directory, manifest, artifacts, cache_hit=True)

    if synthesizer is None:
        preflight_local_sapi(cancel_event=cancel_event)
    stage_directory = Path(
        tempfile.mkdtemp(prefix=f".{cache_key}.", dir=str(root))
    )
    try:
        wav_segments: list[_WavSegment] = []
        for index, text in enumerate(settings.synthesis_segments, start=1):
            _raise_if_cancelled(cancel_event)
            if synthesizer is None:
                data = _synthesize_sapi(
                    text,
                    voice=settings.voice,
                    rate=settings.rate,
                    workspace=stage_directory,
                    cancel_event=cancel_event,
                )
            else:
                data = _call_injected_synthesizer(
                    synthesizer, text, voice=settings.voice, rate=settings.rate
                )
            _raise_if_cancelled(cancel_event)
            wav_segments.append(_read_wav(data, label=f"segment {index}"))
        narration_wav, timing_rows, duration_ms = _join_wav(wav_segments)
        timing_rows = [
            {**row, "text": settings.segments[row["index"]]}
            for row in timing_rows
        ]
        timings_document = {
            "schema_version": NARRATION_SCHEMA_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
            "provider": "windows_sapi",
            "timing_source": "wav_frames",
            "sample_rate": wav_segments[0].sample_rate,
            "channels": wav_segments[0].channels,
            "sample_width": wav_segments[0].sample_width,
            "duration_ms": duration_ms,
            "segments": timing_rows,
        }
        _atomic_write(stage_directory / "narration.wav", narration_wav)
        _atomic_write(stage_directory / "captions.srt", _build_captions(settings.segments, timing_rows))
        _atomic_write(
            stage_directory / "timings.json",
            (canonical_json(timings_document) + "\n").encode("utf-8"),
        )
        _atomic_write(
            stage_directory / "manifest.json",
            _build_manifest(
                settings,
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                duration_ms=duration_ms,
                timings=timing_rows,
                stage_directory=stage_directory,
            ),
        )
        cache_directory.mkdir(parents=True, exist_ok=True)
        if cache_directory.is_symlink():
            raise NarrationError("narration cache path must not be a symlink")
        for spec in _FILE_SPECS:
            os.replace(stage_directory / spec["filename"], cache_directory / spec["filename"])
    finally:
        shutil.rmtree(stage_directory, ignore_errors=True)

    cached = _load_valid_cache(
        workspace,
        cache_directory,
        settings=settings,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
    )
    if cached is None:
        raise NarrationError("generated narration cache failed integrity verification")
    manifest, artifacts = cached
    return _result(workspace, cache_directory, manifest, artifacts, cache_hit=False)


__all__ = [
    "NarrationError",
    "NarrationPreflightError",
    "NarrationSynthesisError",
    "generate_local_narration",
    "preflight_local_sapi",
]
