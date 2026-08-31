from __future__ import annotations

"""Pure-local scene alignment for an already generated ElevenLabs result.

This module deliberately has no provider client and no public HTTP contract.  It
accepts the immutable WAV/timing artifacts produced by :mod:`elevenlabs`,
verifies their hashes and alignment lineage, and lays the three narration
segments onto a closed HOOK -> MESSAGE -> CTA schedule.
"""

import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import wave
from pathlib import Path
from typing import Any, Mapping

from .external_tts_execution import (
    EXTERNAL_TTS_IMPLEMENTATION_VERSION,
    EXTERNAL_TTS_PROVIDER,
    EXTERNAL_TTS_SCHEMA_VERSION,
    EXTERNAL_TTS_TIMING_SOURCE,
)
from .security import canonical_json


VOICE_UPGRADE_IMPLEMENTATION_VERSION = "elevenlabs-scene-alignment-v1"
VOICE_UPGRADE_SCHEDULE_POLICY = "hook_message_cta_scene_starts_v1"
VOICE_UPGRADE_SCHEMA_VERSION = 1
SCENE_ROLES = ("HOOK", "MESSAGE", "CTA")

MAX_WAV_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_DURATION_MS = 60_000
MAX_SEGMENT_CHARS = 4_000
MAX_TOTAL_CHARS = 100_000
MAX_ALIGNMENT_CHARS = 100_000

_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_CONTROL_CHARS = frozenset(chr(value) for value in range(32)) | {chr(127)}
_SCHEDULE_KEYS = {"schema_version", "total_duration_ms", "scenes"}
_SCENE_KEYS = {"role", "start_ms", "text"}
_TIMINGS_KEYS = {
    "schema_version",
    "implementation_version",
    "provider",
    "timing_source",
    "duration_ms",
    "sample_rate",
    "channels",
    "sample_width",
    "segments",
    "alignment",
}
_SOURCE_SEGMENT_KEYS = {
    "index",
    "text",
    "start_ms",
    "end_ms",
    "duration_ms",
    "character_start_index",
    "character_end_index",
    "character_count",
}
_ALIGNMENT_KEYS = {
    "characters",
    "character_start_times_seconds",
    "character_end_times_seconds",
}
_MANIFEST_KEYS = {
    "schema_version",
    "implementation_version",
    "provider",
    "timing_source",
    "timing_policy",
    "schedule_sha256",
    "cache_key",
    "duration_ms",
    "sample_rate",
    "channels",
    "sample_width",
    "source",
    "segment_start_ms",
    "segments",
    "files",
    "manifest_sha256",
}
_OUTPUT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "narration.wav", "kind": "audio", "mime": "audio/wav"},
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


class VoiceUpgradeError(RuntimeError):
    """A bounded, secret-free failure for the internal alignment stage."""

    error_code = "voice_upgrade_failed"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = message


def _raise(message: str, *, code: str) -> None:
    raise VoiceUpgradeError(message, code=code)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _normalized_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _raise(f"{label} must be a SHA-256 digest.", code="invalid_source_hash")
    return value.upper()


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        _raise(f"{label} is invalid.", code="invalid_voice_upgrade_schedule")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SEGMENT_CHARS:
        _raise(f"{label} is invalid.", code="invalid_voice_upgrade_schedule")
    if any(character in _CONTROL_CHARS for character in value) or any(
        0xD800 <= ord(character) <= 0xDFFF for character in value
    ):
        _raise(f"{label} is invalid.", code="invalid_voice_upgrade_schedule")
    return value


def validate_scene_schedule(schedule: Any) -> dict[str, Any]:
    """Return the canonical closed HOOK/MESSAGE/CTA schedule."""

    if not isinstance(schedule, dict) or set(schedule) != _SCHEDULE_KEYS:
        _raise("The voice-upgrade schedule is invalid.", code="invalid_voice_upgrade_schedule")
    if (
        type(schedule.get("schema_version")) is not int
        or schedule.get("schema_version") != VOICE_UPGRADE_SCHEMA_VERSION
    ):
        _raise("The voice-upgrade schedule version is invalid.", code="invalid_voice_upgrade_schedule")
    total_duration_ms = _integer(
        schedule.get("total_duration_ms"),
        label="total_duration_ms",
        minimum=1,
        maximum=MAX_OUTPUT_DURATION_MS,
    )
    raw_scenes = schedule.get("scenes")
    if not isinstance(raw_scenes, list) or len(raw_scenes) != len(SCENE_ROLES):
        _raise(
            "The voice-upgrade schedule must contain HOOK, MESSAGE, and CTA.",
            code="invalid_voice_upgrade_schedule",
        )
    scenes: list[dict[str, Any]] = []
    total_chars = 0
    previous_start = -1
    for index, expected_role in enumerate(SCENE_ROLES):
        raw = raw_scenes[index]
        if not isinstance(raw, dict) or set(raw) != _SCENE_KEYS:
            _raise("A voice-upgrade scene is invalid.", code="invalid_voice_upgrade_schedule")
        if raw.get("role") != expected_role:
            _raise(
                "Voice-upgrade scenes must be ordered HOOK, MESSAGE, CTA.",
                code="invalid_voice_upgrade_schedule",
            )
        start_ms = _integer(
            raw.get("start_ms"),
            label=f"{expected_role}.start_ms",
            minimum=0,
            maximum=total_duration_ms - 1,
        )
        if (index == 0 and start_ms != 0) or start_ms <= previous_start:
            _raise(
                "Voice-upgrade scene starts are invalid.",
                code="invalid_voice_upgrade_schedule",
            )
        scene_text = _text(raw.get("text"), label=f"{expected_role}.text")
        total_chars += len(scene_text)
        if total_chars > MAX_TOTAL_CHARS:
            _raise("Voice-upgrade text is too long.", code="invalid_voice_upgrade_schedule")
        scenes.append({"role": expected_role, "start_ms": start_ms, "text": scene_text})
        previous_start = start_ms
    return {
        "schema_version": VOICE_UPGRADE_SCHEMA_VERSION,
        "total_duration_ms": total_duration_ms,
        "scenes": scenes,
    }


def voice_upgrade_schedule_digest(schedule: Any) -> str:
    normalized = validate_scene_schedule(schedule)
    return _sha256_bytes(canonical_json(normalized).encode("utf-8"))


def voice_upgrade_cache_key(
    schedule: Any,
    *,
    source_wav_sha256: str,
    source_timings_sha256: str,
) -> str:
    normalized = validate_scene_schedule(schedule)
    identity = {
        "implementation_version": VOICE_UPGRADE_IMPLEMENTATION_VERSION,
        "schedule_sha256": _sha256_bytes(canonical_json(normalized).encode("utf-8")),
        "source_timings_sha256": _normalized_sha256(
            source_timings_sha256, label="source_timings_sha256"
        ),
        "source_wav_sha256": _normalized_sha256(
            source_wav_sha256, label="source_wav_sha256"
        ),
    }
    return _sha256_bytes(canonical_json(identity).encode("utf-8"))


def _workspace_path(workspace: Path, candidate: str | Path, *, must_exist: bool) -> Path:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    joined = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = joined.relative_to(root)
        cursor = root
        for part in relative.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError
        resolved = joined.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise VoiceUpgradeError(
            "The voice-upgrade path is outside the workspace.", code="unsafe_output_path"
        ) from exc
    return resolved


def _regular_source_file(workspace: Path, candidate: str | Path, *, maximum: int) -> tuple[Path, bytes]:
    path = _workspace_path(workspace, candidate, must_exist=True)
    if path.is_symlink() or not path.is_file():
        _raise("A voice-upgrade source artifact is unavailable.", code="unsafe_source_path")
    try:
        size = path.stat().st_size
        if size <= 0 or size > maximum:
            _raise("A voice-upgrade source artifact is invalid.", code="invalid_voice_upgrade_source")
        data = path.read_bytes()
    except VoiceUpgradeError:
        raise
    except OSError as exc:
        raise VoiceUpgradeError(
            "A voice-upgrade source artifact could not be read.",
            code="invalid_voice_upgrade_source",
        ) from exc
    if len(data) != size:
        _raise("A voice-upgrade source artifact changed while reading.", code="source_hash_changed")
    return path, data


def _ensure_output_root(workspace: Path, candidate: str | Path) -> Path:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    joined = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = joined.relative_to(root)
    except ValueError as exc:
        raise VoiceUpgradeError(
            "The voice-upgrade output path is outside the workspace.", code="unsafe_output_path"
        ) from exc
    cursor = root
    for part in relative.parts:
        if part in ("", "."):
            continue
        if part == "..":
            _raise("The voice-upgrade output path is unsafe.", code="unsafe_output_path")
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink() or not cursor.is_dir():
                _raise("The voice-upgrade output path is unsafe.", code="unsafe_output_path")
        else:
            try:
                cursor.mkdir()
            except OSError as exc:
                raise VoiceUpgradeError(
                    "The voice-upgrade output path could not be created.",
                    code="unsafe_output_path",
                ) from exc
    return cursor.resolve(strict=True)


def _read_source_wav(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_WAV_BYTES:
        _raise("The source WAV is too large.", code="invalid_voice_upgrade_source")
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            compression = handle.getcomptype()
            frames = handle.readframes(frame_count)
    except (EOFError, ValueError, wave.Error) as exc:
        raise VoiceUpgradeError(
            "The source WAV is invalid.", code="unsupported_voice_upgrade_wav"
        ) from exc
    frame_width = channels * sample_width
    if (
        channels <= 0
        or channels > 8
        or sample_width != 2
        or sample_rate != 44_100
        or compression != "NONE"
        or frame_count <= 0
        or frame_width <= 0
        or len(frames) != frame_count * frame_width
    ):
        _raise("The source WAV format is unsupported.", code="unsupported_voice_upgrade_wav")
    duration_ms = (frame_count * 1_000) // sample_rate
    if duration_ms <= 0 or duration_ms > MAX_OUTPUT_DURATION_MS:
        _raise("The source WAV duration is invalid.", code="unsupported_voice_upgrade_wav")
    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "frame_count": frame_count,
        "frame_width": frame_width,
        "duration_ms": duration_ms,
        "frames": frames,
    }


def _alignment_milliseconds(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise("The source alignment is invalid.", code="invalid_voice_upgrade_alignment")
    number = float(value)
    if (
        not math.isfinite(number)
        or number < 0
        or number > MAX_OUTPUT_DURATION_MS / 1_000
    ):
        _raise("The source alignment is invalid.", code="invalid_voice_upgrade_alignment")
    return int(number * 1_000.0 + 0.5)


def _parse_source_timings(
    data: bytes,
    *,
    wav: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if len(data) > MAX_METADATA_BYTES:
        _raise("The source timings are too large.", code="invalid_voice_upgrade_source")
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VoiceUpgradeError(
            "The source timings are invalid.", code="invalid_voice_upgrade_alignment"
        ) from exc
    if not isinstance(document, dict) or set(document) != _TIMINGS_KEYS:
        _raise("The source timing contract is invalid.", code="invalid_voice_upgrade_alignment")
    integer_metadata = (
        "schema_version",
        "duration_ms",
        "sample_rate",
        "channels",
        "sample_width",
    )
    if any(type(document.get(key)) is not int for key in integer_metadata) or (
        document.get("schema_version") != EXTERNAL_TTS_SCHEMA_VERSION
        or document.get("implementation_version") != EXTERNAL_TTS_IMPLEMENTATION_VERSION
        or document.get("provider") != EXTERNAL_TTS_PROVIDER
        or document.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or document.get("duration_ms") != wav["duration_ms"]
        or document.get("sample_rate") != wav["sample_rate"]
        or document.get("channels") != wav["channels"]
        or document.get("sample_width") != wav["sample_width"]
    ):
        _raise("The source timing metadata does not match the WAV.", code="voice_upgrade_source_mismatch")

    raw_rows = document.get("segments")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(SCENE_ROLES):
        _raise("The source segment count is invalid.", code="voice_upgrade_source_mismatch")
    alignment = document.get("alignment")
    if not isinstance(alignment, dict) or set(alignment) != _ALIGNMENT_KEYS:
        _raise("The source alignment contract is invalid.", code="invalid_voice_upgrade_alignment")
    characters = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")
    if (
        not isinstance(characters, list)
        or not isinstance(starts, list)
        or not isinstance(ends, list)
        or not characters
        or len(characters) != len(starts)
        or len(characters) != len(ends)
        or len(characters) > MAX_ALIGNMENT_CHARS
    ):
        _raise("The source alignment is invalid.", code="invalid_voice_upgrade_alignment")

    expected_joined_text = "\n".join(scene["text"] for scene in schedule["scenes"])
    clean_characters: list[str] = []
    start_ms: list[int] = []
    end_ms: list[int] = []
    previous_start = 0
    previous_end = 0
    for index, (character, raw_start, raw_end) in enumerate(
        zip(characters, starts, ends, strict=True)
    ):
        if (
            not isinstance(character, str)
            or len(character) != 1
            or any(item in _CONTROL_CHARS and item not in "\t\n" for item in character)
        ):
            _raise("The source alignment characters are invalid.", code="invalid_voice_upgrade_alignment")
        current_start = _alignment_milliseconds(raw_start)
        current_end = _alignment_milliseconds(raw_end)
        if (
            current_end < current_start
            or current_start < previous_start
            or current_end < previous_end
        ):
            _raise("The source alignment is non-monotonic.", code="invalid_voice_upgrade_alignment")
        clean_characters.append(character)
        start_ms.append(current_start)
        end_ms.append(current_end)
        previous_start = current_start
        previous_end = current_end
    if "".join(clean_characters) != expected_joined_text:
        _raise("The source alignment text does not match the schedule.", code="voice_upgrade_source_mismatch")

    rows: list[dict[str, Any]] = []
    cursor = 0
    previous_segment_end = 0
    for index, (raw, scene) in enumerate(zip(raw_rows, schedule["scenes"], strict=True)):
        if not isinstance(raw, dict) or set(raw) != _SOURCE_SEGMENT_KEYS:
            _raise("A source timing row is invalid.", code="invalid_voice_upgrade_alignment")
        integer_fields = (
            "index",
            "start_ms",
            "end_ms",
            "duration_ms",
            "character_start_index",
            "character_end_index",
            "character_count",
        )
        if (
            type(raw.get("text")) is not str
            or any(type(raw.get(key)) is not int for key in integer_fields)
        ):
            _raise("A source timing row is invalid.", code="invalid_voice_upgrade_alignment")
        count = len(scene["text"])
        character_end_index = cursor + count
        if character_end_index > len(characters):
            _raise("A source timing row exceeds alignment.", code="invalid_voice_upgrade_alignment")
        derived_start = min(start_ms[cursor], wav["duration_ms"])
        derived_end = min(end_ms[character_end_index - 1], wav["duration_ms"])
        if derived_end <= derived_start:
            derived_end = min(wav["duration_ms"], derived_start + 1)
        expected = {
            "index": index,
            "text": scene["text"],
            "start_ms": derived_start,
            "end_ms": derived_end,
            "duration_ms": derived_end - derived_start,
            "character_start_index": cursor,
            "character_end_index": character_end_index,
            "character_count": count,
        }
        if raw != expected or derived_end <= derived_start:
            _raise("A source timing row does not match alignment.", code="voice_upgrade_source_mismatch")
        if index and derived_start < previous_segment_end:
            _raise("Source narration segments overlap.", code="invalid_voice_upgrade_alignment")
        rows.append(expected)
        previous_segment_end = derived_end
        cursor = character_end_index + (1 if index < len(SCENE_ROLES) - 1 else 0)
    if cursor != len(characters):
        _raise("The source alignment contains unexpected characters.", code="invalid_voice_upgrade_alignment")
    return rows


def _ceil_frame(milliseconds: int, sample_rate: int) -> int:
    return (milliseconds * sample_rate + 999) // 1_000


def _format_srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _render_aligned_media(
    wav: Mapping[str, Any],
    source_rows: list[dict[str, Any]],
    schedule: Mapping[str, Any],
) -> tuple[bytes, bytes, list[dict[str, Any]]]:
    sample_rate = wav["sample_rate"]
    frame_width = wav["frame_width"]
    total_frames = _ceil_frame(schedule["total_duration_ms"], sample_rate)
    if total_frames * frame_width > MAX_WAV_BYTES:
        _raise("The aligned narration WAV is too large.", code="voice_upgrade_output_too_large")
    output_frames = bytearray(total_frames * frame_width)
    output_rows: list[dict[str, Any]] = []
    caption_blocks: list[str] = []
    for index, (source, scene) in enumerate(
        zip(source_rows, schedule["scenes"], strict=True)
    ):
        source_start_frame = _ceil_frame(source["start_ms"], sample_rate)
        source_end_frame = _ceil_frame(source["end_ms"], sample_rate)
        if (
            source_start_frame < 0
            or source_end_frame <= source_start_frame
            or source_end_frame > wav["frame_count"]
        ):
            _raise("A source segment is outside the WAV.", code="voice_upgrade_source_mismatch")
        segment_frames = source_end_frame - source_start_frame
        target_start_frame = _ceil_frame(scene["start_ms"], sample_rate)
        target_end_frame = target_start_frame + segment_frames
        boundary_ms = (
            schedule["scenes"][index + 1]["start_ms"]
            if index + 1 < len(SCENE_ROLES)
            else schedule["total_duration_ms"]
        )
        boundary_frame = _ceil_frame(boundary_ms, sample_rate)
        caption_end_ms = scene["start_ms"] + source["duration_ms"]
        if target_end_frame > boundary_frame or caption_end_ms > boundary_ms:
            _raise(
                "A narration segment overlaps the next scene or output end.",
                code="voice_upgrade_segment_overlap",
            )
        source_byte_start = source_start_frame * frame_width
        source_byte_end = source_end_frame * frame_width
        target_byte_start = target_start_frame * frame_width
        target_byte_end = target_end_frame * frame_width
        output_frames[target_byte_start:target_byte_end] = wav["frames"][
            source_byte_start:source_byte_end
        ]
        row = {
            "index": index,
            "role": scene["role"],
            "text": scene["text"],
            "text_sha256": _sha256_bytes(scene["text"].encode("utf-8")),
            "source_start_ms": source["start_ms"],
            "source_end_ms": source["end_ms"],
            "source_duration_ms": source["duration_ms"],
            "source_start_frame": source_start_frame,
            "source_end_frame": source_end_frame,
            "requested_start_ms": scene["start_ms"],
            "start_ms": scene["start_ms"],
            "end_ms": caption_end_ms,
            "duration_ms": source["duration_ms"],
            "start_frame": target_start_frame,
            "end_frame": target_end_frame,
            "frames": segment_frames,
        }
        output_rows.append(row)
        caption_blocks.append(
            "\n".join(
                (
                    str(index + 1),
                    f"{_format_srt_time(row['start_ms'])} --> {_format_srt_time(row['end_ms'])}",
                    scene["text"],
                    "",
                )
            )
        )
    output = io.BytesIO()
    try:
        with wave.open(output, "wb") as handle:
            handle.setnchannels(wav["channels"])
            handle.setsampwidth(wav["sample_width"])
            handle.setframerate(sample_rate)
            handle.setcomptype("NONE", "not compressed")
            handle.writeframes(bytes(output_frames))
    except (ValueError, wave.Error) as exc:
        raise VoiceUpgradeError(
            "The aligned narration WAV could not be created.", code="voice_upgrade_publish_failed"
        ) from exc
    return output.getvalue(), "\n".join(caption_blocks).encode("utf-8"), output_rows


def _file_entry(path: Path, *, filename: str, kind: str, mime: str) -> dict[str, Any]:
    return {
        "path": filename,
        "kind": kind,
        "mime": mime,
        "bytes": path.stat().st_size,
        "sha256": _sha256_bytes(path.read_bytes()),
    }


def _artifact_record(workspace: Path, directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = directory / spec["filename"]
    if path.is_symlink() or not path.is_file():
        _raise("A voice-upgrade cache artifact is unavailable.", code="voice_upgrade_cache_integrity_failed")
    relative = path.relative_to(workspace).as_posix()
    size = path.stat().st_size
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": size,
        "sha256": _sha256_bytes(path.read_bytes()),
        "mime": spec["mime"],
        "media_type": spec["mime"],
        "origin": "studio",
        "version": VOICE_UPGRADE_IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": size > 10 * 1024 * 1024,
    }


def _manifest_digest(body: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(body).encode("utf-8"))


def _write_stage(
    stage: Path,
    *,
    wav_bytes: bytes,
    captions: bytes,
    output_rows: list[dict[str, Any]],
    source_wav_bytes: int,
    source_timings_bytes: int,
    source_wav_sha256: str,
    source_timings_sha256: str,
    schedule: Mapping[str, Any],
    schedule_sha256: str,
    cache_key: str,
    wav: Mapping[str, Any],
) -> dict[str, Any]:
    (stage / "narration.wav").write_bytes(wav_bytes)
    (stage / "captions.srt").write_bytes(captions)
    source = {
        "narration_wav": {
            "bytes": source_wav_bytes,
            "sha256": source_wav_sha256,
        },
        "timings_json": {
            "bytes": source_timings_bytes,
            "sha256": source_timings_sha256,
        },
    }
    timings = {
        "schema_version": VOICE_UPGRADE_SCHEMA_VERSION,
        "implementation_version": VOICE_UPGRADE_IMPLEMENTATION_VERSION,
        "provider": EXTERNAL_TTS_PROVIDER,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "timing_policy": {
            "name": VOICE_UPGRADE_SCHEDULE_POLICY,
            "schedule_sha256": schedule_sha256,
            "scene_roles": list(SCENE_ROLES),
            "scene_start_ms": [scene["start_ms"] for scene in schedule["scenes"]],
            "total_duration_ms": schedule["total_duration_ms"],
        },
        "duration_ms": schedule["total_duration_ms"],
        "sample_rate": wav["sample_rate"],
        "channels": wav["channels"],
        "sample_width": wav["sample_width"],
        "source": source,
        "segments": output_rows,
    }
    timings_bytes = (canonical_json(timings) + "\n").encode("utf-8")
    if len(timings_bytes) > MAX_METADATA_BYTES:
        _raise("Voice-upgrade timings are too large.", code="voice_upgrade_output_too_large")
    (stage / "timings.json").write_bytes(timings_bytes)

    files: dict[str, Any] = {}
    for spec in _OUTPUT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        files[spec["filename"]] = _file_entry(
            stage / spec["filename"],
            filename=spec["filename"],
            kind=spec["kind"],
            mime=spec["mime"],
        )
    body = {
        "schema_version": VOICE_UPGRADE_SCHEMA_VERSION,
        "implementation_version": VOICE_UPGRADE_IMPLEMENTATION_VERSION,
        "provider": EXTERNAL_TTS_PROVIDER,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "timing_policy": VOICE_UPGRADE_SCHEDULE_POLICY,
        "schedule_sha256": schedule_sha256,
        "cache_key": cache_key,
        "duration_ms": schedule["total_duration_ms"],
        "sample_rate": wav["sample_rate"],
        "channels": wav["channels"],
        "sample_width": wav["sample_width"],
        "source": source,
        "segment_start_ms": [scene["start_ms"] for scene in schedule["scenes"]],
        "segments": output_rows,
        "files": files,
    }
    manifest = dict(body)
    manifest["manifest_sha256"] = _manifest_digest(body)
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    if len(manifest_bytes) > MAX_METADATA_BYTES:
        _raise("Voice-upgrade manifest is too large.", code="voice_upgrade_output_too_large")
    (stage / "manifest.json").write_bytes(manifest_bytes)
    return manifest


def _load_cache(
    workspace: Path,
    directory: Path,
    *,
    expected_cache_key: str,
    expected_schedule_sha256: str,
    expected_source: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not directory.exists() and not directory.is_symlink():
        return None
    if directory.is_symlink() or not directory.is_dir():
        _raise("The voice-upgrade cache path is unsafe.", code="voice_upgrade_cache_integrity_failed")
    manifest_path = directory / "manifest.json"
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError
        data = manifest_path.read_bytes()
        if len(data) > MAX_METADATA_BYTES:
            raise ValueError
        manifest = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise VoiceUpgradeError(
            "The voice-upgrade cache manifest is invalid.",
            code="voice_upgrade_cache_integrity_failed",
        ) from exc
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        _raise("The voice-upgrade cache manifest is invalid.", code="voice_upgrade_cache_integrity_failed")
    digest = manifest.get("manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if (
        not isinstance(digest, str)
        or _manifest_digest(body) != digest.upper()
        or manifest.get("schema_version") != VOICE_UPGRADE_SCHEMA_VERSION
        or manifest.get("implementation_version") != VOICE_UPGRADE_IMPLEMENTATION_VERSION
        or manifest.get("provider") != EXTERNAL_TTS_PROVIDER
        or manifest.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or manifest.get("timing_policy") != VOICE_UPGRADE_SCHEDULE_POLICY
        or manifest.get("cache_key") != expected_cache_key
        or manifest.get("schedule_sha256") != expected_schedule_sha256
        or manifest.get("source") != expected_source
    ):
        _raise("The voice-upgrade cache manifest does not match.", code="voice_upgrade_cache_integrity_failed")
    files = manifest.get("files")
    expected_names = {
        spec["filename"] for spec in _OUTPUT_SPECS if spec["filename"] != "manifest.json"
    }
    if not isinstance(files, dict) or set(files) != expected_names:
        _raise("The voice-upgrade cache file list is invalid.", code="voice_upgrade_cache_integrity_failed")
    for spec in _OUTPUT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = directory / spec["filename"]
        entry = files.get(spec["filename"])
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "kind", "mime", "bytes", "sha256"}
            or entry.get("path") != spec["filename"]
            or entry.get("kind") != spec["kind"]
            or entry.get("mime") != spec["mime"]
            or isinstance(entry.get("bytes"), bool)
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 0
            or not isinstance(entry.get("sha256"), str)
            or not _SHA256_RE.fullmatch(entry["sha256"])
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or _sha256_bytes(path.read_bytes()) != entry["sha256"].upper()
        ):
            _raise("A voice-upgrade cache artifact is invalid.", code="voice_upgrade_cache_integrity_failed")
    artifacts = [_artifact_record(workspace, directory, spec) for spec in _OUTPUT_SPECS]
    return manifest, artifacts


def _result(
    manifest: Mapping[str, Any], artifacts: list[dict[str, Any]], *, cache_hit: bool
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "duration_ms": manifest["duration_ms"],
        "provider": EXTERNAL_TTS_PROVIDER,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "timing_policy": VOICE_UPGRADE_SCHEDULE_POLICY,
        "schedule_sha256": manifest["schedule_sha256"],
        "segment_start_ms": list(manifest["segment_start_ms"]),
    }


def align_external_tts_to_scene_schedule(
    workspace: Path,
    *,
    source_wav: str | Path,
    source_timings: str | Path,
    output_root: str | Path,
    source_wav_sha256: str,
    source_timings_sha256: str,
    schedule: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify and align an immutable ElevenLabs result without a paid call."""

    workspace = workspace.resolve(strict=True)
    normalized_schedule = validate_scene_schedule(schedule)
    expected_wav_sha256 = _normalized_sha256(
        source_wav_sha256, label="source_wav_sha256"
    )
    expected_timings_sha256 = _normalized_sha256(
        source_timings_sha256, label="source_timings_sha256"
    )
    _, wav_bytes = _regular_source_file(
        workspace, source_wav, maximum=MAX_WAV_BYTES
    )
    _, timings_bytes = _regular_source_file(
        workspace, source_timings, maximum=MAX_METADATA_BYTES
    )
    if _sha256_bytes(wav_bytes) != expected_wav_sha256:
        _raise("The source WAV hash changed.", code="source_hash_changed")
    if _sha256_bytes(timings_bytes) != expected_timings_sha256:
        _raise("The source timings hash changed.", code="source_hash_changed")
    wav = _read_source_wav(wav_bytes)
    source_rows = _parse_source_timings(
        timings_bytes, wav=wav, schedule=normalized_schedule
    )
    schedule_sha256 = voice_upgrade_schedule_digest(normalized_schedule)
    cache_key = voice_upgrade_cache_key(
        normalized_schedule,
        source_wav_sha256=expected_wav_sha256,
        source_timings_sha256=expected_timings_sha256,
    )
    root = _ensure_output_root(workspace, output_root)
    cache_directory = root / cache_key
    expected_source = {
        "narration_wav": {"bytes": len(wav_bytes), "sha256": expected_wav_sha256},
        "timings_json": {
            "bytes": len(timings_bytes),
            "sha256": expected_timings_sha256,
        },
    }
    cached = _load_cache(
        workspace,
        cache_directory,
        expected_cache_key=cache_key,
        expected_schedule_sha256=schedule_sha256,
        expected_source=expected_source,
    )
    if cached is not None:
        manifest, artifacts = cached
        return _result(manifest, artifacts, cache_hit=True)

    aligned_wav, captions, output_rows = _render_aligned_media(
        wav, source_rows, normalized_schedule
    )
    stage = Path(tempfile.mkdtemp(prefix=f".{cache_key}.", dir=str(root)))
    try:
        _write_stage(
            stage,
            wav_bytes=aligned_wav,
            captions=captions,
            output_rows=output_rows,
            source_wav_bytes=len(wav_bytes),
            source_timings_bytes=len(timings_bytes),
            source_wav_sha256=expected_wav_sha256,
            source_timings_sha256=expected_timings_sha256,
            schedule=normalized_schedule,
            schedule_sha256=schedule_sha256,
            cache_key=cache_key,
            wav=wav,
        )
        try:
            os.replace(stage, cache_directory)
        except OSError as exc:
            raced = _load_cache(
                workspace,
                cache_directory,
                expected_cache_key=cache_key,
                expected_schedule_sha256=schedule_sha256,
                expected_source=expected_source,
            )
            if raced is None:
                raise VoiceUpgradeError(
                    "Voice-upgrade artifacts could not be published.",
                    code="voice_upgrade_publish_failed",
                ) from exc
        completed = _load_cache(
            workspace,
            cache_directory,
            expected_cache_key=cache_key,
            expected_schedule_sha256=schedule_sha256,
            expected_source=expected_source,
        )
        if completed is None:  # pragma: no cover - published above
            _raise("Voice-upgrade cache validation failed.", code="voice_upgrade_cache_integrity_failed")
        manifest, artifacts = completed
        return _result(manifest, artifacts, cache_hit=False)
    except VoiceUpgradeError:
        raise
    except OSError as exc:
        raise VoiceUpgradeError(
            "Voice-upgrade artifacts could not be published.",
            code="voice_upgrade_publish_failed",
        ) from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)


__all__ = [
    "SCENE_ROLES",
    "VOICE_UPGRADE_IMPLEMENTATION_VERSION",
    "VOICE_UPGRADE_SCHEDULE_POLICY",
    "VoiceUpgradeError",
    "align_external_tts_to_scene_schedule",
    "validate_scene_schedule",
    "voice_upgrade_cache_key",
    "voice_upgrade_schedule_digest",
]
