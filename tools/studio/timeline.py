from __future__ import annotations

"""Deterministic, video-only local FFmpeg timeline rendering.

The worker deliberately does not know about HTTP, SQLite, or arbitrary user
paths.  The service resolves registered video artifacts into ``clips`` with
bytes and SHA-256 provenance.  This module then revalidates those inputs,
copies them to fixed names in a private temporary directory, and runs one
bounded FFmpeg filter graph with hard cuts.
"""

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import assembly as _assembly
from .assembly import (
    AssemblyError,
    AssemblyToolError,
    _bounded_process,
    _first_stream,
    _json_probe,
    _probe_duration,
    _sha256_file,
    _streams,
    _tool_identity,
)
from .jobs import JobCancelled
from .security import (
    SecurityError,
    canonical_json,
    relative_workspace_path,
    validate_identifier,
    workspace_path,
)
from .timeline_execution import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    FRAME_RATE,
    IMPLEMENTATION_VERSION,
    MAX_TIMELINE_DURATION_MS,
    OUTPUT_POLICY_VERSION,
    PROVIDER,
    TIMELINE_SCHEMA_VERSION,
    TIMING_SOURCE,
    TimelineError,
    TimelineToolError,
    TimelineValidationError,
    normalize_internal_clips,
    timeline_cache_key as _control_timeline_cache_key,
)


MAX_SOURCE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_PROCESS_OUTPUT_BYTES = 256 * 1024
FFMPEG_TIMEOUT_SECONDS = 5 * 60
FFPROBE_TIMEOUT_SECONDS = 30
FFMPEG_THREADS = 2
_PROCESS_CLEANUP_TIMEOUT_SECONDS = 1.0

_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "timeline-preview.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "timeline.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)
_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")


def timeline_cache_key(
    clips: Sequence[Mapping[str, Any]],
    *,
    ffmpeg_identity: Mapping[str, Any] | None = None,
    ffprobe_identity: Mapping[str, Any] | None = None,
    tool_identity: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Return a cache key that includes this worker's media policy version.

    ``timeline_execution.timeline_cache_key`` owns the control-plane lineage
    and tool identity normalization.  The renderer adds its own implementation
    and output-policy identities so a changed FFmpeg graph cannot reuse an
    older cache merely because the public clip request is unchanged.
    """

    control_key = _control_timeline_cache_key(
        clips,
        ffmpeg_identity=ffmpeg_identity,
        ffprobe_identity=ffprobe_identity,
        tool_identity=tool_identity,
    )
    identity = {
        "control_cache_key": control_key,
        "implementation_version": IMPLEMENTATION_VERSION,
        "output_policy_version": OUTPUT_POLICY_VERSION,
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def _cancel(cancel_event: Any | None) -> None:
    _assembly._raise_if_cancelled(cancel_event)


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def _safe_error(exc: BaseException, *, code: str = "local_ffmpeg_timeline_failed") -> TimelineError:
    if isinstance(exc, TimelineError):
        return exc
    if isinstance(exc, JobCancelled):
        raise exc
    if isinstance(exc, AssemblyError):
        return TimelineToolError(
            str(getattr(exc, "public_message", str(exc))),
            code=str(getattr(exc, "error_code", code)),
        )
    return TimelineError("The local timeline worker failed.", code=code)


def _run_probe(
    executable: str,
    path: Path,
    *,
    cwd: Path,
    cancel_event: Any | None,
) -> dict[str, Any]:
    try:
        return _json_probe(executable, path, cwd=cwd, cancel_event=cancel_event)
    except JobCancelled:
        raise
    except AssemblyToolError as exc:
        raise TimelineToolError(
            "ffprobe could not inspect the timeline media.",
            code=str(getattr(exc, "error_code", "local_ffprobe_failed")),
        ) from exc
    except AssemblyError as exc:
        raise TimelineValidationError(
            str(getattr(exc, "public_message", str(exc))),
            code=str(getattr(exc, "error_code", "invalid_media")),
        ) from exc


def _resolve_tools(
    *,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
) -> tuple[str, str, dict[str, dict[str, str]]]:
    _cancel(cancel_event)
    try:
        ffmpeg_executable = _assembly._find_tool("ffmpeg", ffmpeg)
        ffprobe_executable = _assembly._find_tool("ffprobe", ffprobe)
        identities = {
            "ffmpeg": _tool_identity("ffmpeg", ffmpeg_executable, cancel_event=cancel_event),
            "ffprobe": _tool_identity("ffprobe", ffprobe_executable, cancel_event=cancel_event),
        }
    except JobCancelled:
        raise
    except AssemblyError as exc:
        raise TimelineToolError(
            "The local FFmpeg tools are unavailable.",
            code=str(getattr(exc, "error_code", "local_ffmpeg_unavailable")),
        ) from exc
    return ffmpeg_executable, ffprobe_executable, identities


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


def _safe_timeline_root(workspace: Path, run_id: str, cache_key: str) -> Path:
    validate_identifier(run_id, label="run id")
    if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
        raise TimelineValidationError("cache_key is invalid", code="invalid_cache_key")
    lexical_root = workspace / "outputs" / "studio" / "runs"
    lexical_run = lexical_root / run_id
    lexical_timeline = lexical_run / "timeline"
    lexical_cache = lexical_timeline / cache_key
    if any(
        _has_symlink_component(workspace, candidate)
        for candidate in (lexical_root, lexical_run, lexical_timeline, lexical_cache)
    ):
        raise TimelineValidationError("timeline output path must not contain symlinks", code="unsafe_output_path")
    root = workspace_path(workspace, lexical_root, must_exist=False)
    run_directory = workspace_path(workspace, lexical_run, must_exist=False)
    timeline_directory = workspace_path(workspace, lexical_timeline, must_exist=False)
    cache_directory = workspace_path(workspace, lexical_cache, must_exist=False)
    for directory in (root, run_directory, timeline_directory):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise TimelineValidationError("timeline output path is not a directory", code="unsafe_output_path")
        directory.mkdir(parents=True, exist_ok=True)
    if cache_directory.exists() and cache_directory.is_symlink():
        raise TimelineValidationError("timeline cache path must not be a symlink", code="unsafe_output_path")
    return cache_directory


def _safe_source(workspace: Path, value: str | Path, *, label: str) -> Path:
    try:
        lexical = Path(value)
        path = workspace_path(workspace, lexical, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise TimelineValidationError(f"{label} is unavailable", code="source_not_available") from exc
    if (
        _has_symlink_component(workspace, lexical)
        or path.is_symlink()
        or not path.is_file()
    ):
        raise TimelineValidationError(f"{label} is not a safe regular file", code="source_not_available")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TimelineValidationError(f"{label} is unavailable", code="source_not_available") from exc
    if size <= 0 or size > MAX_SOURCE_VIDEO_BYTES:
        raise TimelineValidationError(f"{label} size is unsupported", code="source_size_invalid")
    return path


def _video_duration_ms(probe: Mapping[str, Any], *, label: str) -> int:
    try:
        streams = _streams(probe)
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        if len(video_streams) != 1 or any(
            stream.get("codec_type") not in {"video", "audio"} for stream in streams
        ):
            raise TimelineValidationError(
                f"{label} must contain exactly one video stream", code="invalid_source_media"
            )
        video = _first_stream(probe, "video")
        width, height = video.get("width"), video.get("height")
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or width <= 0
            or isinstance(height, bool)
            or not isinstance(height, int)
            or height <= 0
            or width > 16_384
            or height > 16_384
            or width * height > 64 * 1024 * 1024
        ):
            raise TimelineValidationError(
                f"{label} dimensions are invalid", code="invalid_source_media"
            )
        duration = _probe_duration(probe, stream_type="video")
    except TimelineError:
        raise
    except AssemblyError as exc:
        raise TimelineValidationError(
            f"{label} duration is unavailable", code="invalid_source_media"
        ) from exc
    duration_ms = int(round(duration * 1000))
    if duration_ms < 50 or duration_ms > MAX_TIMELINE_DURATION_MS:
        raise TimelineValidationError(
            f"{label} duration is unsupported", code="invalid_source_media"
        )
    return duration_ms


def _frame_rate(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    result = float(fraction)
    return result if math.isfinite(result) and result > 0 else None


def _validate_output_probe(probe: Mapping[str, Any], *, target_duration_ms: int) -> int:
    format_data = probe.get("format")
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if not isinstance(format_name, str) or "mp4" not in {
        part.strip().casefold() for part in format_name.split(",")
    }:
        raise TimelineError("timeline output is not an MP4 container", code="invalid_output_media")
    try:
        streams = _streams(probe)
    except AssemblyError as exc:
        raise TimelineError("timeline output stream metadata is invalid", code="invalid_output_media") from exc
    if len(streams) != 1 or streams[0].get("codec_type") != "video":
        raise TimelineError("timeline output must contain video only", code="invalid_output_media")
    video = streams[0]
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise TimelineError("timeline output codec is unsupported", code="invalid_output_media")
    if video.get("width") != CANVAS_WIDTH or video.get("height") != CANVAS_HEIGHT:
        raise TimelineError("timeline output dimensions are unsupported", code="invalid_output_media")
    rates = [_frame_rate(video.get("r_frame_rate")), _frame_rate(video.get("avg_frame_rate"))]
    if any(rate is None or abs(rate - FRAME_RATE) > 0.01 for rate in rates):
        raise TimelineError("timeline output frame rate is unsupported", code="invalid_output_media")
    try:
        duration = _probe_duration(probe, stream_type="video")
    except AssemblyError as exc:
        raise TimelineError("timeline output duration is unavailable", code="invalid_output_media") from exc
    duration_ms = int(round(duration * 1000))
    if duration_ms < 50 or duration_ms > MAX_TIMELINE_DURATION_MS or abs(duration_ms - target_duration_ms) > 250:
        raise TimelineError("timeline output duration does not match the timeline", code="invalid_output_media")
    return duration_ms


def _input_record(workspace: Path, path: Path, *, source_bytes: int, source_sha256: str) -> dict[str, Any]:
    return {
        "path": relative_workspace_path(workspace, path),
        "bytes": source_bytes,
        "sha256": source_sha256.upper(),
    }


def _assert_source_matches(path: Path, *, source_bytes: int, source_sha256: str, label: str) -> None:
    try:
        stat = path.stat()
        digest = _sha256_file(path)
    except OSError as exc:
        raise TimelineError(f"{label} changed during timeline preparation", code="input_changed") from exc
    if stat.st_size != source_bytes or digest != source_sha256.upper():
        raise TimelineError(f"{label} changed during timeline preparation", code="input_changed")


def _prepare_clips(
    workspace: Path,
    clips: Sequence[Mapping[str, Any]],
    *,
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    normalized = normalize_internal_clips(clips)
    prepared: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []
    total_duration_ms = 0
    for index, item in enumerate(normalized):
        _cancel(cancel_event)
        path = _safe_source(workspace, item["source_path"], label=f"clips[{index}].source_path")
        try:
            stat = path.stat()
            digest = _sha256_file(path)
        except OSError as exc:
            raise TimelineValidationError(
                f"clips[{index}] source is unavailable", code="source_not_available"
            ) from exc
        if stat.st_size != item["source_bytes"] or digest != item["source_sha256"]:
            raise TimelineValidationError(
                f"clips[{index}] source hash does not match its record", code="source_changed"
            )
        probe = _run_probe(ffprobe, path, cwd=workspace, cancel_event=cancel_event)
        duration_ms = _video_duration_ms(probe, label=f"clips[{index}]")
        if item["end_ms"] > duration_ms:
            raise TimelineValidationError(
                f"clips[{index}] end_ms exceeds source duration", code="trim_out_of_range"
            )
        relative = relative_workspace_path(workspace, path)
        prepared_item = dict(item)
        prepared_item["source_path"] = relative
        prepared_item["source_bytes"] = stat.st_size
        prepared_item["source_sha256"] = digest.upper()
        prepared_item["source_duration_ms"] = duration_ms
        prepared.append(prepared_item)
        probes.append(probe)
        total_duration_ms += item["end_ms"] - item["start_ms"]
    if total_duration_ms <= 0 or total_duration_ms > MAX_TIMELINE_DURATION_MS:
        raise TimelineValidationError("timeline duration is unsupported", code="timeline_duration_invalid")
    return prepared, probes, total_duration_ms


def _artifact_record(workspace: Path, cache_directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
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
        "version": IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_manifest(path: Path) -> dict[str, Any] | None:
    value = _read_json(path)
    if value is None or not isinstance(value.get("manifest_sha256"), str):
        return None
    digest = value["manifest_sha256"]
    body = dict(value)
    body.pop("manifest_sha256", None)
    if _manifest_digest(body) != digest.upper():
        return None
    return value


def _timeline_document(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "duration_ms": duration_ms,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "transition": "hard_cut",
        "audio": "video_only",
        "clips": [
            {
                "index": index,
                "video_artifact_id": item["video_artifact_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "duration_ms": item["end_ms"] - item["start_ms"],
                "source_path": item["source_path"],
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
                "source_duration_ms": item["source_duration_ms"],
            }
            for index, item in enumerate(clips)
        ],
    }


def _output_policy() -> dict[str, Any]:
    return {
        "policy_version": OUTPUT_POLICY_VERSION,
        "container": "mp4",
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "frame_rate": FRAME_RATE,
        "audio": "omitted",
        "transitions": "hard_cut_only",
    }


def _resource_policy() -> dict[str, int]:
    return {
        "ffmpeg_threads": FFMPEG_THREADS,
        "max_clips": 32,
        "max_duration_ms": MAX_TIMELINE_DURATION_MS,
        "max_source_bytes": MAX_SOURCE_VIDEO_BYTES,
        "max_output_bytes": MAX_OUTPUT_BYTES,
    }


def _clip_frame_counts(clips: Sequence[Mapping[str, Any]]) -> list[int]:
    """Allocate the rounded total 24fps budget without per-cut drift."""

    counts: list[int] = []
    cumulative_ms = 0
    allocated_frames = 0
    for item in clips:
        cumulative_ms += item["end_ms"] - item["start_ms"]
        cumulative_frames = (cumulative_ms * FRAME_RATE + 500) // 1000
        frame_count = cumulative_frames - allocated_frames
        if frame_count < 1:
            raise TimelineValidationError(
                "timeline clip is shorter than the output frame budget",
                code="timeline_duration_invalid",
            )
        counts.append(frame_count)
        allocated_frames = cumulative_frames
    return counts


def _build_filter(clips: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    labels: list[str] = []
    frame_counts = _clip_frame_counts(clips)
    for index, (item, frame_count) in enumerate(zip(clips, frame_counts, strict=True)):
        start = item["start_ms"] / 1000
        end = item["end_ms"] / 1000
        label = f"v{index}"
        labels.append(f"[{label}]")
        parts.append(
            f"[{index}:v]trim=start={start:.3f}:end={end:.3f},"
            "setpts=PTS-STARTPTS,"
            f"scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=decrease,"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            f"pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={FRAME_RATE},"
            "tpad=stop_mode=clone:stop_duration=1,"
            # Keep exactly the allocated frames per segment.  Giving concat an
            # extra boundary frame makes it count that frame as part of the
            # preceding segment, which duplicates every boundary and causes a
            # global trim to discard the tail of later clips.
            f"trim=end_frame={frame_count},setpts=N/({FRAME_RATE}*TB),"
            f"format=yuv420p[{label}]"
        )
    parts.append(f"{''.join(labels)}concat=n={len(clips)}:v=1:a=0[joined]")
    # Each segment is already normalized to the output time base.  A second
    # global fps/trim pass would hide a boundary error by dropping frames from
    # the final clips, so only normalize the joined PTS here.
    parts.append(f"[joined]setpts=N/({FRAME_RATE}*TB),format=yuv420p[outv]")
    return ";".join(parts)


def _copy_sources(
    workspace: Path,
    work_directory: Path,
    clips: Sequence[Mapping[str, Any]],
    *,
    cancel_event: Any | None,
) -> list[str]:
    names: list[str] = []
    for index, item in enumerate(clips):
        _cancel(cancel_event)
        source = _safe_source(workspace, item["source_path"], label=f"clips[{index}].source_path")
        name = f"clip-{index:02d}.mp4"
        destination = work_directory / name
        try:
            shutil.copyfile(source, destination)
            _assert_source_matches(
                source,
                source_bytes=item["source_bytes"],
                source_sha256=item["source_sha256"],
                label=f"clips[{index}]",
            )
            if destination.stat().st_size != item["source_bytes"] or _sha256_file(destination) != item["source_sha256"]:
                raise TimelineError(f"clips[{index}] copy failed integrity verification", code="input_changed")
        except JobCancelled:
            raise
        except TimelineError:
            raise
        except OSError as exc:
            raise TimelineToolError("timeline input could not be staged", code="input_stage_failed") from exc
        names.append(name)
    return names


def _write_metadata(path: Path, value: Mapping[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise TimelineError("timeline metadata is too large", code="metadata_too_large")
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _publish(stage: Path, cache_directory: Path) -> None:
    cache_directory.mkdir(parents=True, exist_ok=True)
    if cache_directory.is_symlink() or not cache_directory.is_dir():
        raise TimelineError("timeline cache path is unsafe", code="unsafe_output_path")
    expected = {spec["filename"] for spec in _ARTIFACT_SPECS}
    # Remove only stale regular files from this exact generated cache.  No
    # recursive deletion is used, and unexpected directories remain a fail-
    # closed cache condition.
    for child in cache_directory.iterdir():
        if child.name not in expected and child.is_file() and not child.is_symlink():
            child.unlink()
    for spec in _ARTIFACT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        os.replace(stage / spec["filename"], cache_directory / spec["filename"])
    os.replace(stage / "manifest.json", cache_directory / "manifest.json")


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    output_probe: Mapping[str, Any],
    stage: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _ARTIFACT_SPECS:
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
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "duration_ms": duration_ms,
        "tool_identity": dict(tool_identity),
        "output_policy": _output_policy(),
        "resource_policy": _resource_policy(),
        "clips": [dict(item) for item in clips],
        "media": {"timeline_preview": dict(output_probe)},
        "files": files,
    }
    body["manifest_sha256"] = _manifest_digest(body)
    return body


def _result(workspace: Path, cache_directory: Path, manifest: Mapping[str, Any], artifacts: list[dict[str, Any]], *, cache_hit: bool) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "video_dimensions": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "output_directory": cache_directory.relative_to(workspace.resolve(strict=True)).as_posix(),
        "clips": manifest["clips"],
    }


def _validate_cache(
    workspace: Path,
    cache_directory: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _cancel(cancel_event)
    if not cache_directory.is_dir() or cache_directory.is_symlink():
        return None
    manifest = _read_manifest(cache_directory / "manifest.json")
    if manifest is None:
        return None
    expected_timeline = _timeline_document(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        duration_ms=duration_ms,
    )
    if (
        manifest.get("schema_version") != TIMELINE_SCHEMA_VERSION
        or manifest.get("implementation_version") != IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("cache_key") != cache_key
        or manifest.get("provider") != PROVIDER
        or manifest.get("provider_task_id") is not None
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != TIMING_SOURCE
        or manifest.get("duration_ms") != duration_ms
        or manifest.get("tool_identity") != dict(tool_identity)
        or manifest.get("output_policy") != _output_policy()
        or manifest.get("resource_policy") != _resource_policy()
        or manifest.get("clips") != list(clips)
    ):
        return None
    timeline = _read_json(cache_directory / "timeline.json")
    if timeline != expected_timeline:
        return None
    files = manifest.get("files")
    expected_names = {spec["filename"] for spec in _ARTIFACT_SPECS if spec["filename"] != "manifest.json"}
    if not isinstance(files, dict) or set(files) != expected_names:
        return None
    try:
        physical_names = {child.name for child in cache_directory.iterdir()}
    except OSError:
        return None
    if physical_names != {spec["filename"] for spec in _ARTIFACT_SPECS}:
        return None
    for spec in _ARTIFACT_SPECS:
        path = cache_directory / spec["filename"]
        if path.is_symlink() or not path.is_file():
            return None
        if spec["filename"] == "manifest.json":
            continue
        entry = files.get(spec["filename"])
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if spec["filename"] == "timeline-preview.mp4" and size > MAX_OUTPUT_BYTES:
            return None
        if (
            not isinstance(entry, dict)
            or entry.get("path") != spec["filename"]
            or entry.get("kind") != spec["kind"]
            or entry.get("mime") != spec["mime"]
            or entry.get("bytes") != size
            or entry.get("sha256") != _sha256_file(path)
        ):
            return None
    probe_document = _read_json(cache_directory / "ffprobe.json")
    if (
        probe_document is None
        or probe_document.get("schema_version") != TIMELINE_SCHEMA_VERSION
        or probe_document.get("implementation_version") != IMPLEMENTATION_VERSION
        or probe_document.get("timing_source") != TIMING_SOURCE
        or probe_document.get("timeline_preview") != manifest.get("media", {}).get("timeline_preview")
    ):
        return None
    try:
        fresh_probe = _run_probe(
            ffprobe,
            Path("timeline-preview.mp4"),
            cwd=cache_directory,
            cancel_event=cancel_event,
        )
        fresh_duration = _validate_output_probe(fresh_probe, target_duration_ms=duration_ms)
    except JobCancelled:
        raise
    except TimelineError:
        return None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if fresh_duration != int(probe_document["timeline_preview"].get("duration_ms", fresh_duration)):
        # ffprobe stream duration is represented as seconds in the raw
        # document, so the comparison below is intentionally only against the
        # expected timeline duration; metadata equality is checked by the
        # probe document itself above.
        if abs(fresh_duration - duration_ms) > 250:
            return None
    try:
        artifacts = [_artifact_record(workspace, cache_directory, spec) for spec in _ARTIFACT_SPECS]
    except (OSError, ValueError):
        return None
    return manifest, artifacts


def _generate_or_validate(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
    generate: bool,
) -> dict[str, Any]:
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    workspace = workspace.resolve(strict=True)
    normalized_input = normalize_internal_clips(clips)
    ffmpeg_executable, ffprobe_executable, tool_identity = _resolve_tools(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    prepared, source_probes, duration_ms = _prepare_clips(
        workspace,
        normalized_input,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    expected_key = timeline_cache_key(prepared, tool_identity=tool_identity)
    if cache_key != expected_key:
        raise TimelineValidationError("cache_key does not match timeline inputs", code="invalid_cache_key")
    cache_directory = _safe_timeline_root(workspace, run_id, cache_key)
    cached = _validate_cache(
        workspace,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=prepared,
        duration_ms=duration_ms,
        tool_identity=tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    if cached is not None:
        manifest, artifacts = cached
        return _result(workspace, cache_directory, manifest, artifacts, cache_hit=True)
    if not generate:
        raise TimelineError("timeline cache failed integrity verification", code="cache_integrity_failed")

    timeline = _timeline_document(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=prepared,
        duration_ms=duration_ms,
    )
    parent = cache_directory.parent
    stage_root = Path(tempfile.mkdtemp(prefix=".timeline-", dir=str(parent)))
    work_directory = stage_root / "work"
    publish_directory = stage_root / "publish"
    work_directory.mkdir()
    publish_directory.mkdir()
    try:
        fixed_names = _copy_sources(workspace, work_directory, prepared, cancel_event=cancel_event)
        _cancel(cancel_event)
        filter_graph = _build_filter(prepared)
        output_partial = publish_directory / "timeline-preview.mp4.partial"
        ffmpeg_args: list[str] = [
            ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        for name in fixed_names:
            ffmpeg_args.extend(["-i", name])
        ffmpeg_args.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[outv]",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-an",
                "-sn",
                "-dn",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-r",
                str(FRAME_RATE),
                "-vsync",
                "cfr",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                str(FFMPEG_THREADS),
                "-movflags",
                "+faststart",
                "-fs",
                str(MAX_OUTPUT_BYTES),
                "-f",
                "mp4",
                "timeline-preview.mp4.partial",
            ]
        )
        # The media command runs in the fixed-name work directory and writes
        # through a relative path in the sibling publish directory.  Do not
        # put the registered source paths into an argv element.
        relative_output = Path("..") / "publish" / output_partial.name
        ffmpeg_args[-1] = relative_output.as_posix()
        try:
            _bounded_process(
                ffmpeg_args,
                cwd=work_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="timeline ffmpeg",
                cancel_event=cancel_event,
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise TimelineToolError(
                "local timeline FFmpeg failed.",
                code=str(getattr(exc, "error_code", "local_ffmpeg_failed")),
            ) from exc
        if not output_partial.is_file():
            raise TimelineToolError("local timeline FFmpeg produced no output", code="invalid_worker_result")
        os.replace(output_partial, publish_directory / "timeline-preview.mp4")
        _cancel(cancel_event)
        # A decode-only pass catches truncated MP4s before publication while
        # still keeping the output video-only.
        try:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "timeline-preview.mp4",
                    "-map",
                    "0:v:0",
                    "-f",
                    "null",
                    "-",
                ],
                cwd=publish_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="timeline full decode",
                cancel_event=cancel_event,
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise TimelineToolError("timeline output did not fully decode", code="invalid_output_media") from exc
        output_probe = _run_probe(
            ffprobe_executable,
            Path("timeline-preview.mp4"),
            cwd=publish_directory,
            cancel_event=cancel_event,
        )
        _validate_output_probe(output_probe, target_duration_ms=duration_ms)
        _write_metadata(
            publish_directory / "timeline.json",
            timeline,
        )
        _write_metadata(
            publish_directory / "ffprobe.json",
            {
                "schema_version": TIMELINE_SCHEMA_VERSION,
                "implementation_version": IMPLEMENTATION_VERSION,
                "timing_source": TIMING_SOURCE,
                "timeline_preview": output_probe,
            },
        )
        manifest = _build_manifest(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            clips=prepared,
            duration_ms=duration_ms,
            tool_identity=tool_identity,
            output_probe=output_probe,
            stage=publish_directory,
        )
        _write_metadata(publish_directory / "manifest.json", manifest)
        _publish(publish_directory, cache_directory)
    except JobCancelled:
        raise
    except TimelineError:
        raise
    except (OSError, ValueError, SecurityError) as exc:
        raise TimelineToolError("local timeline publication failed", code="publish_failed") from exc
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)

    validated = _validate_cache(
        workspace,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=prepared,
        duration_ms=duration_ms,
        tool_identity=tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    if validated is None:
        raise TimelineError("published timeline failed integrity verification", code="integrity_verification_failed")
    validated_manifest, artifacts = validated
    return _result(workspace, cache_directory, validated_manifest, artifacts, cache_hit=False)


def generate_local_timeline(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Generate or reuse a verified local timeline preview."""

    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        generate=True,
    )


def validate_local_timeline_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Revalidate an existing timeline cache without rendering it."""

    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        generate=False,
    )


__all__ = [
    "FFMPEG_TIMEOUT_SECONDS",
    "MAX_METADATA_BYTES",
    "MAX_OUTPUT_BYTES",
    "MAX_PROCESS_OUTPUT_BYTES",
    "MAX_SOURCE_VIDEO_BYTES",
    "generate_local_timeline",
    "validate_local_timeline_outputs",
]
