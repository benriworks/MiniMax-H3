from __future__ import annotations

"""Control-plane contracts for the local multi-clip timeline worker.

The public request deliberately contains only artifact references and trim
windows.  The service resolves those references to workspace files before it
calls the media worker.  The worker therefore receives a richer internal
clip record, but never accepts an arbitrary path from the HTTP boundary.
"""

import re
from pathlib import Path
from typing import Any, Mapping, Sequence


MAX_TIMELINE_CLIPS = 32
MAX_TIMELINE_DURATION_MS = 30 * 60 * 1000
MIN_CLIP_DURATION_MS = 50
MAX_CACHE_KEY_CHARS = 256
TIMELINE_SCHEMA_VERSION = 1
IMPLEMENTATION_VERSION = "local-ffmpeg-timeline-v2"
PROVIDER = "local_ffmpeg_timeline"
TIMING_SOURCE = "ffprobe"
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
FRAME_RATE = 24
OUTPUT_POLICY_VERSION = "h264-yuv420p-24fps-video-only-mp4-frame-budget-v2"

_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_PUBLIC_KEYS = {"clips"}
_CLIP_KEYS = {"video_artifact_id", "start_ms", "end_ms"}
_INTERNAL_KEYS = {
    "video_artifact_id",
    "start_ms",
    "end_ms",
    "source_path",
    "source_bytes",
    "source_sha256",
    "source_duration_ms",
}


class TimelineError(RuntimeError):
    """A bounded error suitable for the Studio job boundary."""

    error_code = "local_timeline_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = str(message)


class TimelineValidationError(TimelineError):
    error_code = "invalid_local_timeline_request"


class TimelineToolError(TimelineError):
    error_code = "local_ffmpeg_timeline_failed"


def _int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TimelineValidationError(f"{label} must be an integer")
    if value < minimum:
        raise TimelineValidationError(f"{label} must be at least {minimum}")
    return value


def _public_clip(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _CLIP_KEYS:
        raise TimelineValidationError(
            f"clips[{index}] must contain only video_artifact_id, start_ms, and end_ms"
        )
    artifact_id = value.get("video_artifact_id")
    if not isinstance(artifact_id, str) or not _ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise TimelineValidationError(f"clips[{index}].video_artifact_id is invalid")
    start_ms = _int(value.get("start_ms"), label=f"clips[{index}].start_ms")
    end_ms = _int(value.get("end_ms"), label=f"clips[{index}].end_ms")
    if end_ms <= start_ms:
        raise TimelineValidationError(f"clips[{index}] end_ms must be greater than start_ms")
    if end_ms > MAX_TIMELINE_DURATION_MS:
        raise TimelineValidationError(f"clips[{index}].end_ms is too large")
    if end_ms - start_ms < MIN_CLIP_DURATION_MS:
        raise TimelineValidationError(
            f"clips[{index}] duration must be at least {MIN_CLIP_DURATION_MS}ms"
        )
    return {
        "video_artifact_id": artifact_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


def validate_local_timeline_payload(body: Any) -> dict[str, Any]:
    """Validate the exact public timeline body.

    The worker accepts no output policy, path, caption, or free-form FFmpeg
    options from the caller.  Those choices are fixed by this adapter.
    """

    if not isinstance(body, dict) or set(body) != _PUBLIC_KEYS:
        raise TimelineValidationError("request body must contain only clips")
    clips = body.get("clips")
    if not isinstance(clips, list):
        raise TimelineValidationError("clips must be an array")
    if not 1 <= len(clips) <= MAX_TIMELINE_CLIPS:
        raise TimelineValidationError(
            f"clips must contain between 1 and {MAX_TIMELINE_CLIPS} entries"
        )
    normalized = [_public_clip(item, index=index) for index, item in enumerate(clips)]
    total = sum(item["end_ms"] - item["start_ms"] for item in normalized)
    if total > MAX_TIMELINE_DURATION_MS:
        raise TimelineValidationError("timeline duration exceeds the local limit")
    return {"clips": normalized}


def _internal_clip(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, dict) or not set(value).issuperset(_CLIP_KEYS):
        raise TimelineValidationError(f"clips[{index}] is invalid")
    public = _public_clip(
        {key: value[key] for key in _CLIP_KEYS},
        index=index,
    )
    if set(value) - _INTERNAL_KEYS:
        raise TimelineValidationError(f"clips[{index}] contains unsupported fields")
    source_path = value.get("source_path")
    if not isinstance(source_path, (str, Path)) or not str(source_path) or len(str(source_path)) > 1024:
        # Path objects are normalized by the service before entering the
        # worker.  Rejecting them here prevents a surprising repr from being
        # persisted in the audit manifest.
        raise TimelineValidationError(f"clips[{index}].source_path is invalid")
    source_bytes = _int(value.get("source_bytes"), label=f"clips[{index}].source_bytes", minimum=1)
    source_sha256 = value.get("source_sha256")
    if not isinstance(source_sha256, str) or not _SHA256_RE.fullmatch(source_sha256):
        raise TimelineValidationError(f"clips[{index}].source_sha256 is invalid")
    return {
        **public,
        "source_path": str(source_path).replace("\\", "/"),
        "source_bytes": source_bytes,
        "source_sha256": source_sha256.upper(),
    }


def normalize_internal_clips(clips: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(clips, (list, tuple)):
        raise TimelineValidationError("clips must be an array")
    if not 1 <= len(clips) <= MAX_TIMELINE_CLIPS:
        raise TimelineValidationError(
            f"clips must contain between 1 and {MAX_TIMELINE_CLIPS} entries"
        )
    normalized = [_internal_clip(item, index=index) for index, item in enumerate(clips)]
    total = sum(item["end_ms"] - item["start_ms"] for item in normalized)
    if total > MAX_TIMELINE_DURATION_MS:
        raise TimelineValidationError("timeline duration exceeds the local limit")
    return normalized


def _normalize_tool_identity(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TimelineValidationError(f"{label} is invalid")
    path = value.get("path")
    version = value.get("version")
    digest = value.get("sha256")
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise TimelineValidationError(f"{label}.path is invalid")
    if not isinstance(version, str) or not version or len(version) > 512:
        raise TimelineValidationError(f"{label}.version is invalid")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise TimelineValidationError(f"{label}.sha256 is invalid")
    return {"path": path, "version": version, "sha256": digest.upper()}


def _tool_identity_pair(
    *,
    ffmpeg_identity: Mapping[str, Any] | None,
    ffprobe_identity: Mapping[str, Any] | None,
    tool_identity: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    if tool_identity is not None:
        if ffmpeg_identity is not None or ffprobe_identity is not None:
            raise TimelineValidationError("tool identity was provided twice")
        ffmpeg_identity = tool_identity.get("ffmpeg") if isinstance(tool_identity, Mapping) else None
        ffprobe_identity = tool_identity.get("ffprobe") if isinstance(tool_identity, Mapping) else None
    if ffmpeg_identity is None or ffprobe_identity is None:
        from . import assembly

        resolved = assembly.resolve_tool_identity()
        ffmpeg_identity = ffmpeg_identity or resolved["ffmpeg"]
        ffprobe_identity = ffprobe_identity or resolved["ffprobe"]
    return {
        "ffmpeg": _normalize_tool_identity(ffmpeg_identity, label="ffmpeg_identity"),
        "ffprobe": _normalize_tool_identity(ffprobe_identity, label="ffprobe_identity"),
    }


def timeline_cache_key(
    clips: Sequence[Mapping[str, Any]],
    *,
    ffmpeg_identity: Mapping[str, Any] | None = None,
    ffprobe_identity: Mapping[str, Any] | None = None,
    tool_identity: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Derive the content-addressed key from verified clip lineage and tools."""

    normalized = normalize_internal_clips(clips)
    identity = {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "provider": PROVIDER,
        # Paths are intentionally excluded from the content key.  The service
        # may pass absolute verified Path objects while the worker canonicalizes
        # them to workspace-relative paths; artifact ID + bytes + digest is the
        # stable content lineage used for cache identity.
        "clips": [
            {
                "video_artifact_id": item["video_artifact_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
            }
            for item in normalized
        ],
        "output_policy": {
            "policy_version": OUTPUT_POLICY_VERSION,
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
            "frame_rate": FRAME_RATE,
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio": "omitted",
        },
        "tool_identity": _tool_identity_pair(
            ffmpeg_identity=ffmpeg_identity,
            ffprobe_identity=ffprobe_identity,
            tool_identity=tool_identity,
        ),
    }
    from .security import canonical_json
    import hashlib

    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def timeline_audit_payload(
    clips: Sequence[Mapping[str, Any]],
    *,
    cache_key: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_internal_clips(clips)
    payload: dict[str, Any] = {
        "clips": [
            {
                "video_artifact_id": item["video_artifact_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "source_path": item["source_path"],
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
            }
            for item in normalized
        ],
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "transition": "hard_cut",
        "audio": "video_only",
    }
    if cache_key is not None:
        if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
            raise TimelineValidationError("cache_key is invalid")
        payload["cache_key"] = cache_key
    return payload


def timeline_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    expected_duration_ms: int,
    cache_hit: bool,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TimelineError("The local timeline worker returned an invalid result.", code="invalid_worker_result")
    duration_ms = raw.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms <= 0:
        raise TimelineError("The local timeline worker returned invalid timing.", code="invalid_worker_result")
    if abs(duration_ms - expected_duration_ms) > 250:
        raise TimelineError("The local timeline worker returned mismatched timing.", code="invalid_worker_result")
    if raw.get("provider") != PROVIDER or raw.get("timing_source") != TIMING_SOURCE:
        raise TimelineError("The local timeline worker returned invalid metadata.", code="invalid_worker_result")
    actual_cost = raw.get("actual_cost")
    if (
        "provider_task_id" not in raw
        or raw.get("provider_task_id") is not None
        or "actual_cost" not in raw
        or isinstance(actual_cost, bool)
        or not isinstance(actual_cost, int)
        or actual_cost != 0
    ):
        raise TimelineError("The local timeline worker returned invalid cost metadata.", code="invalid_worker_result")
    if (
        raw.get("cache_key") != expected_cache_key
        or "cache_hit" not in raw
        or not isinstance(raw.get("cache_hit"), bool)
        or raw.get("cache_hit") is not cache_hit
    ):
        raise TimelineError("The local timeline worker returned invalid cache metadata.", code="invalid_worker_result")
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": expected_cache_key,
        "cache_hit": cache_hit,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "video_dimensions": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "output_policy": {
            "policy_version": OUTPUT_POLICY_VERSION,
            "audio": "omitted",
        },
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_timeline_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, TimelineError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_ffmpeg_timeline_failed", "The local timeline job failed."


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "FRAME_RATE",
    "IMPLEMENTATION_VERSION",
    "MAX_TIMELINE_CLIPS",
    "MAX_TIMELINE_DURATION_MS",
    "MIN_CLIP_DURATION_MS",
    "OUTPUT_POLICY_VERSION",
    "PROVIDER",
    "TIMELINE_SCHEMA_VERSION",
    "TIMING_SOURCE",
    "TimelineError",
    "TimelineToolError",
    "TimelineValidationError",
    "normalize_internal_clips",
    "safe_timeline_error",
    "timeline_audit_payload",
    "timeline_cache_key",
    "timeline_public_result",
    "validate_local_timeline_payload",
]
