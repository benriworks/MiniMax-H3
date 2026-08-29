from __future__ import annotations

"""Closed control-plane contract for the local Remotion timeline worker.

The public request contains registered artifact IDs and a small allowlist of
editing controls.  Paths, URLs, React components, CSS, fonts, browser flags,
and arbitrary Remotion props are deliberately absent from this boundary.
"""

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .security import canonical_json


SCHEMA_VERSION = 1
IMPLEMENTATION_VERSION = "local-remotion-timeline-v2"
PROVIDER = "local_remotion_timeline"
TIMING_SOURCE = "remotion_frames"
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
FRAME_RATE = 24
MAX_CLIPS = 16
MAX_TIMELINE_DURATION_MS = 60_000
MIN_CLIP_DURATION_MS = 50
MIN_TRANSITION_DURATION_MS = 50
MAX_TRANSITION_DURATION_MS = 2_000
MIN_OVERLAY_DURATION_MS = 50
MAX_OVERLAY_CHARS = 200
MAX_OVERLAY_LINES = 4
OUTPUT_POLICY_VERSION = "remotion-source-fidelity-v2"
SOURCE_ENHANCEMENT_POLICY_VERSION = "lanczos-cover-luma-unsharp-v1"
DEFAULT_VISUAL_PRESET = "preserve_v1"
VISUAL_PRESETS = frozenset({DEFAULT_VISUAL_PRESET, "h3_low_res_sharp_v1"})
REMOTION_FRAME_IMAGE_FORMAT = "png"
REMOTION_VIDEO_CRF = 16
REMOTION_SCRATCH_POLICY_VERSION = "png-frame-scratch-v1"
REMOTION_SCRATCH_RGBA_BYTES_PER_PIXEL = 4
REMOTION_SCRATCH_HEADROOM_NUMERATOR = 5
REMOTION_SCRATCH_HEADROOM_DENOMINATOR = 4
REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES = 2 * 1024 * 1024 * 1024
REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES = 2 * 1024 * 1024 * 1024
REMOTION_SCRATCH_SAFETY_MARGIN_BYTES = 1024 * 1024 * 1024
REMOTION_SCRATCH_SHARP_STAGING_RESERVE_BYTES = 2 * 1024 * 1024 * 1024
SHARP_SOURCE_MIN_DIMENSION = 64
SHARP_SOURCE_MIN_ASPECT_RATIO = 0.50
SHARP_SOURCE_MAX_ASPECT_RATIO = 0.625
SHARP_SOURCE_MAX_SCALED_PIXELS = 3_000_000

_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_PUBLIC_KEYS = {"schema_version", "clips"}
_CLIP_REQUIRED_KEYS = {
    "video_artifact_id",
    "start_ms",
    "end_ms",
    "volume_percent",
    "transition_to_next",
    "overlay",
}
_CLIP_KEYS = _CLIP_REQUIRED_KEYS | {"visual_preset"}
_TRANSITION_KEYS = {"type", "duration_ms"}
_OVERLAY_KEYS = {"text", "start_ms", "end_ms", "position", "style_preset"}
_INTERNAL_EXTRA_KEYS = {"source_path", "source_bytes", "source_sha256"}
_POSITIONS = {"top", "center", "bottom"}
_STYLE_PRESETS = {"shorts_ja_large_v1"}


class RemotionTimelineError(RuntimeError):
    error_code = "local_remotion_timeline_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = str(message)


class RemotionTimelineValidationError(RemotionTimelineError):
    error_code = "invalid_remotion_timeline_request"


class RemotionTimelineToolError(RemotionTimelineError):
    error_code = "local_remotion_render_failed"


def _integer(value: Any, *, label: str, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemotionTimelineValidationError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise RemotionTimelineValidationError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise RemotionTimelineValidationError(f"{label} must be at most {maximum}")
    return value


def milliseconds_to_frames(milliseconds: int) -> int:
    """Convert positive milliseconds with language-independent half-up rounding."""

    value = _integer(milliseconds, label="milliseconds", minimum=0)
    return max(1, (value * FRAME_RATE + 500) // 1000)


def frames_to_milliseconds(frames: int) -> int:
    value = _integer(frames, label="frames", minimum=1)
    return (value * 1000 + FRAME_RATE // 2) // FRAME_RATE


def _transition(value: Any, *, index: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _TRANSITION_KEYS:
        raise RemotionTimelineValidationError(
            f"clips[{index}].transition_to_next must be null or contain only type and duration_ms"
        )
    if value.get("type") != "fade":
        raise RemotionTimelineValidationError(
            f"clips[{index}].transition_to_next.type must be fade"
        )
    duration_ms = _integer(
        value.get("duration_ms"),
        label=f"clips[{index}].transition_to_next.duration_ms",
        minimum=MIN_TRANSITION_DURATION_MS,
        maximum=MAX_TRANSITION_DURATION_MS,
    )
    return {"type": "fade", "duration_ms": duration_ms}


def _overlay(value: Any, *, index: int, clip_duration_ms: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _OVERLAY_KEYS:
        raise RemotionTimelineValidationError(
            f"clips[{index}].overlay must be null or contain only text, start_ms, end_ms, position, and style_preset"
        )
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RemotionTimelineValidationError(f"clips[{index}].overlay.text must not be empty")
    if len(text) > MAX_OVERLAY_CHARS:
        raise RemotionTimelineValidationError(f"clips[{index}].overlay.text is too long")
    if _CONTROL_RE.search(text):
        raise RemotionTimelineValidationError(
            f"clips[{index}].overlay.text contains unsupported control characters"
        )
    if len(text.splitlines()) > MAX_OVERLAY_LINES:
        raise RemotionTimelineValidationError(
            f"clips[{index}].overlay.text contains too many lines"
        )
    start_ms = _integer(value.get("start_ms"), label=f"clips[{index}].overlay.start_ms", minimum=0)
    end_ms = _integer(value.get("end_ms"), label=f"clips[{index}].overlay.end_ms", minimum=0)
    if end_ms <= start_ms or end_ms - start_ms < MIN_OVERLAY_DURATION_MS:
        raise RemotionTimelineValidationError(
            f"clips[{index}].overlay duration must be at least {MIN_OVERLAY_DURATION_MS}ms"
        )
    if end_ms > clip_duration_ms:
        raise RemotionTimelineValidationError(
            f"clips[{index}].overlay must stay inside the trimmed clip"
        )
    position = value.get("position")
    if position not in _POSITIONS:
        raise RemotionTimelineValidationError(f"clips[{index}].overlay.position is invalid")
    style_preset = value.get("style_preset")
    if style_preset not in _STYLE_PRESETS:
        raise RemotionTimelineValidationError(f"clips[{index}].overlay.style_preset is invalid")
    return {
        "text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "position": position,
        "style_preset": style_preset,
    }


def _public_clip(value: Any, *, index: int) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not _CLIP_REQUIRED_KEYS.issubset(value)
        or not set(value).issubset(_CLIP_KEYS)
    ):
        raise RemotionTimelineValidationError(
            f"clips[{index}] must contain only the supported Remotion timeline fields"
        )
    artifact_id = value.get("video_artifact_id")
    if not isinstance(artifact_id, str) or not _ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise RemotionTimelineValidationError(f"clips[{index}].video_artifact_id is invalid")
    start_ms = _integer(value.get("start_ms"), label=f"clips[{index}].start_ms", minimum=0)
    end_ms = _integer(value.get("end_ms"), label=f"clips[{index}].end_ms", minimum=0)
    if end_ms <= start_ms or end_ms - start_ms < MIN_CLIP_DURATION_MS:
        raise RemotionTimelineValidationError(
            f"clips[{index}] duration must be at least {MIN_CLIP_DURATION_MS}ms"
        )
    if end_ms > MAX_TIMELINE_DURATION_MS:
        raise RemotionTimelineValidationError(f"clips[{index}].end_ms is too large")
    volume_percent = _integer(
        value.get("volume_percent"),
        label=f"clips[{index}].volume_percent",
        minimum=0,
        maximum=100,
    )
    visual_preset = value.get("visual_preset", DEFAULT_VISUAL_PRESET)
    if not isinstance(visual_preset, str) or visual_preset not in VISUAL_PRESETS:
        raise RemotionTimelineValidationError(
            f"clips[{index}].visual_preset is invalid"
        )
    duration_ms = end_ms - start_ms
    return {
        "video_artifact_id": artifact_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "volume_percent": volume_percent,
        "visual_preset": visual_preset,
        "transition_to_next": _transition(value.get("transition_to_next"), index=index),
        "overlay": _overlay(value.get("overlay"), index=index, clip_duration_ms=duration_ms),
    }


def _validate_sequence(clips: list[dict[str, Any]]) -> None:
    if clips[-1]["transition_to_next"] is not None:
        raise RemotionTimelineValidationError("the final clip must not define a transition_to_next")
    total_frames = sum(milliseconds_to_frames(item["end_ms"] - item["start_ms"]) for item in clips)
    for index, item in enumerate(clips[:-1]):
        transition = item["transition_to_next"]
        if transition is None:
            continue
        transition_frames = milliseconds_to_frames(transition["duration_ms"])
        current_frames = milliseconds_to_frames(item["end_ms"] - item["start_ms"])
        next_item = clips[index + 1]
        next_frames = milliseconds_to_frames(next_item["end_ms"] - next_item["start_ms"])
        if transition_frames >= current_frames or transition_frames >= next_frames:
            raise RemotionTimelineValidationError(
                f"clips[{index}].transition_to_next must be shorter than both adjacent clips"
            )
        total_frames -= transition_frames
    if total_frames <= 0 or frames_to_milliseconds(total_frames) > MAX_TIMELINE_DURATION_MS:
        raise RemotionTimelineValidationError("timeline duration exceeds the Remotion local limit")


def validate_remotion_timeline_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != _PUBLIC_KEYS:
        raise RemotionTimelineValidationError("request body must contain only schema_version and clips")
    if body.get("schema_version") != SCHEMA_VERSION:
        raise RemotionTimelineValidationError("schema_version is unsupported")
    raw_clips = body.get("clips")
    if not isinstance(raw_clips, list) or not 1 <= len(raw_clips) <= MAX_CLIPS:
        raise RemotionTimelineValidationError(f"clips must contain between 1 and {MAX_CLIPS} entries")
    clips = [_public_clip(item, index=index) for index, item in enumerate(raw_clips)]
    _validate_sequence(clips)
    return {"schema_version": SCHEMA_VERSION, "clips": clips}


def normalize_internal_clips(clips: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(clips, (list, tuple)) or not 1 <= len(clips) <= MAX_CLIPS:
        raise RemotionTimelineValidationError(f"clips must contain between 1 and {MAX_CLIPS} entries")
    public_values: list[dict[str, Any]] = []
    for index, value in enumerate(clips):
        if not isinstance(value, Mapping) or set(value) != _CLIP_KEYS | _INTERNAL_EXTRA_KEYS:
            raise RemotionTimelineValidationError(f"clips[{index}] contains unsupported internal fields")
        public_values.append({key: value[key] for key in _CLIP_KEYS})
    normalized_public = validate_remotion_timeline_payload(
        {"schema_version": SCHEMA_VERSION, "clips": public_values}
    )["clips"]
    normalized: list[dict[str, Any]] = []
    for index, (public, value) in enumerate(zip(normalized_public, clips, strict=True)):
        source_path = value.get("source_path")
        if not isinstance(source_path, (str, Path)) or not str(source_path) or len(str(source_path)) > 1024:
            raise RemotionTimelineValidationError(f"clips[{index}].source_path is invalid")
        source_bytes = _integer(value.get("source_bytes"), label=f"clips[{index}].source_bytes", minimum=1)
        source_sha256 = value.get("source_sha256")
        if not isinstance(source_sha256, str) or not _SHA256_RE.fullmatch(source_sha256):
            raise RemotionTimelineValidationError(f"clips[{index}].source_sha256 is invalid")
        normalized.append(
            {
                **public,
                "source_path": str(source_path).replace("\\", "/"),
                "source_bytes": source_bytes,
                "source_sha256": source_sha256.upper(),
            }
        )
    return normalized


def compile_remotion_timeline(clips: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = normalize_internal_clips(clips)
    compiled: list[dict[str, Any]] = []
    cursor = 0
    for index, item in enumerate(normalized):
        duration_frames = milliseconds_to_frames(item["end_ms"] - item["start_ms"])
        transition = item["transition_to_next"]
        transition_frames = (
            milliseconds_to_frames(transition["duration_ms"]) if transition is not None else 0
        )
        overlay = item["overlay"]
        compiled_overlay = None
        if overlay is not None:
            overlay_start = min(duration_frames - 1, (overlay["start_ms"] * FRAME_RATE + 500) // 1000)
            overlay_end = min(duration_frames, max(overlay_start + 1, (overlay["end_ms"] * FRAME_RATE + 500) // 1000))
            compiled_overlay = {
                **overlay,
                "start_frame": overlay_start,
                "duration_in_frames": overlay_end - overlay_start,
            }
        compiled.append(
            {
                "index": index,
                "start_frame": cursor,
                "duration_in_frames": duration_frames,
                "trim_before_frame": (item["start_ms"] * FRAME_RATE + 500) // 1000,
                "trim_after_frame": (item["end_ms"] * FRAME_RATE + 500) // 1000,
                "volume_percent": item["volume_percent"],
                "transition_to_next": None
                if transition is None
                else {**transition, "duration_in_frames": transition_frames},
                "overlay": compiled_overlay,
            }
        )
        cursor += duration_frames - transition_frames
    return {
        "schema_version": SCHEMA_VERSION,
        "frame_rate": FRAME_RATE,
        "duration_in_frames": cursor,
        "duration_ms": frames_to_milliseconds(cursor),
        "clips": compiled,
    }


def _normalize_tool_identity(tool_identity: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    if not isinstance(tool_identity, Mapping) or not tool_identity:
        raise RemotionTimelineValidationError("tool_identity is invalid")
    normalized: dict[str, dict[str, str]] = {}
    for name, raw in sorted(tool_identity.items()):
        if not isinstance(name, str) or not name or not isinstance(raw, Mapping):
            raise RemotionTimelineValidationError("tool_identity is invalid")
        version = raw.get("version")
        digest = raw.get("sha256")
        if (
            not isinstance(version, str)
            or not version
            or len(version) > 512
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            raise RemotionTimelineValidationError(f"tool_identity.{name} is invalid")
        normalized[name] = {"version": version, "sha256": digest.upper()}
    return normalized


def remotion_timeline_cache_key(
    clips: Sequence[Mapping[str, Any]], *, tool_identity: Mapping[str, Any]
) -> str:
    normalized = normalize_internal_clips(clips)
    identity_clips = []
    for item in normalized:
        public = {key: item[key] for key in _CLIP_KEYS}
        identity_clips.append(
            {
                **public,
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
            }
        )
    identity = {
        "schema_version": SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "provider": PROVIDER,
        "recipe": {"schema_version": SCHEMA_VERSION, "clips": identity_clips},
        "compiled": compile_remotion_timeline(normalized),
        "output_policy": remotion_output_policy(),
        "tool_identity": _normalize_tool_identity(tool_identity),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def remotion_timeline_audit_payload(
    clips: Sequence[Mapping[str, Any]], *, cache_key: str
) -> dict[str, Any]:
    if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
        raise RemotionTimelineValidationError("cache_key is invalid")
    normalized = normalize_internal_clips(clips)
    compiled = compile_remotion_timeline(normalized)
    audit_clips: list[dict[str, Any]] = []
    for item in normalized:
        overlay = item["overlay"]
        audit_clips.append(
            {
                "video_artifact_id": item["video_artifact_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "volume_percent": item["volume_percent"],
                "visual_preset": item["visual_preset"],
                "transition_to_next": item["transition_to_next"],
                "overlay": None
                if overlay is None
                else {
                    "text_sha256": hashlib.sha256(overlay["text"].encode("utf-8")).hexdigest().upper(),
                    "text_chars": len(overlay["text"]),
                    "line_count": len(overlay["text"].splitlines()),
                    "start_ms": overlay["start_ms"],
                    "end_ms": overlay["end_ms"],
                    "position": overlay["position"],
                    "style_preset": overlay["style_preset"],
                },
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "cache_key": cache_key,
        "clip_count": len(audit_clips),
        "clips": audit_clips,
        "duration_ms": compiled["duration_ms"],
        "duration_in_frames": compiled["duration_in_frames"],
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "audio": "source_mix_with_silent_aac_fallback",
        "output_policy": remotion_output_policy(),
        "source_enhancement_policy": remotion_output_policy()["source_enhancement"],
    }


def remotion_output_policy() -> dict[str, Any]:
    """Return the fixed renderer and pre-overlay source-fidelity policy.

    The public API selects only one of two closed visual presets.  It never
    accepts filter text, sharpening strength, CRF, or renderer frame format.
    Keeping these values in the cache identity prevents a policy update from
    reusing media produced by an older quality path.
    """

    return {
        "policy_version": OUTPUT_POLICY_VERSION,
        "container": "mp4",
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "frame_rate": FRAME_RATE,
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "video_crf": REMOTION_VIDEO_CRF,
        "x264_preset": "medium",
        "render_frame_image_format": REMOTION_FRAME_IMAGE_FORMAT,
        "audio_codec": "aac",
        "sample_rate": 48_000,
        "channels": 2,
        "audio": "aac_48000_stereo",
        "silent_audio_fallback": True,
        "render_scratch": {
            "policy_version": REMOTION_SCRATCH_POLICY_VERSION,
            "temporary_directory_scope": "stage_work_directory",
            "temporary_environment": ["TEMP", "TMP", "TMPDIR"],
            "cleanup": "recursive_on_all_exit_paths",
            "disk_space_preflight": True,
            "preflight_phases": [
                "before_source_staging",
                "after_source_staging_before_node",
            ],
            "node_containment_attestation": True,
            "scratch_directory_must_be_empty": True,
            "rgba_bytes_per_pixel": REMOTION_SCRATCH_RGBA_BYTES_PER_PIXEL,
            "png_headroom_ratio": [
                REMOTION_SCRATCH_HEADROOM_NUMERATOR,
                REMOTION_SCRATCH_HEADROOM_DENOMINATOR,
            ],
            "raw_output_reserve_bytes": REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES,
            "normalized_output_reserve_bytes": REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES,
            "safety_margin_bytes": REMOTION_SCRATCH_SAFETY_MARGIN_BYTES,
            "sharp_staging_reserve_bytes_per_clip": REMOTION_SCRATCH_SHARP_STAGING_RESERVE_BYTES,
        },
        "source_enhancement": {
            "policy_version": SOURCE_ENHANCEMENT_POLICY_VERSION,
            "available_presets": sorted(VISUAL_PRESETS),
            "default_preset": DEFAULT_VISUAL_PRESET,
            "sharp_preset": {
                "id": "h3_low_res_sharp_v1",
                "stage": "before_overlays",
                "fit": "cover",
                "scaler": "lanczos",
                "luma_unsharp_matrix": "5x5",
                "luma_unsharp_amount": 0.25,
                "chroma_unsharp_amount": 0,
                "trim_to_used_frames": True,
                "portrait_upscale_only": True,
                "minimum_source_dimension": SHARP_SOURCE_MIN_DIMENSION,
                "source_aspect_ratio_range": [
                    SHARP_SOURCE_MIN_ASPECT_RATIO,
                    SHARP_SOURCE_MAX_ASPECT_RATIO,
                ],
                "maximum_scaled_pixels": SHARP_SOURCE_MAX_SCALED_PIXELS,
            },
        },
    }


def remotion_timeline_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    expected_duration_ms: int,
    cache_hit: bool,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RemotionTimelineError("The Remotion worker returned an invalid result.", code="invalid_worker_result")
    duration_ms = raw.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms <= 0:
        raise RemotionTimelineError("The Remotion worker returned invalid timing.", code="invalid_worker_result")
    if abs(duration_ms - expected_duration_ms) > frames_to_milliseconds(1):
        raise RemotionTimelineError("The Remotion worker returned mismatched timing.", code="invalid_worker_result")
    if raw.get("provider") != PROVIDER or raw.get("timing_source") != TIMING_SOURCE:
        raise RemotionTimelineError("The Remotion worker returned invalid metadata.", code="invalid_worker_result")
    if raw.get("cache_key") != expected_cache_key or raw.get("cache_hit") is not cache_hit:
        raise RemotionTimelineError("The Remotion worker returned invalid cache metadata.", code="invalid_worker_result")
    if raw.get("provider_task_id") is not None or raw.get("actual_cost") != 0:
        raise RemotionTimelineError("The Remotion worker returned invalid cost metadata.", code="invalid_worker_result")
    if raw.get("has_audio") is not True:
        raise RemotionTimelineError("The Remotion worker returned invalid audio metadata.", code="invalid_worker_result")
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": expected_cache_key,
        "cache_hit": cache_hit,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "has_audio": True,
        "video_dimensions": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "output_policy": remotion_output_policy(),
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_remotion_timeline_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, RemotionTimelineError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_remotion_timeline_failed", "The local Remotion timeline job failed."


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "FRAME_RATE",
    "IMPLEMENTATION_VERSION",
    "MAX_CLIPS",
    "MAX_TIMELINE_DURATION_MS",
    "OUTPUT_POLICY_VERSION",
    "DEFAULT_VISUAL_PRESET",
    "REMOTION_FRAME_IMAGE_FORMAT",
    "REMOTION_SCRATCH_HEADROOM_DENOMINATOR",
    "REMOTION_SCRATCH_HEADROOM_NUMERATOR",
    "REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES",
    "REMOTION_SCRATCH_POLICY_VERSION",
    "REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES",
    "REMOTION_SCRATCH_RGBA_BYTES_PER_PIXEL",
    "REMOTION_SCRATCH_SAFETY_MARGIN_BYTES",
    "REMOTION_SCRATCH_SHARP_STAGING_RESERVE_BYTES",
    "REMOTION_VIDEO_CRF",
    "SOURCE_ENHANCEMENT_POLICY_VERSION",
    "SHARP_SOURCE_MAX_ASPECT_RATIO",
    "SHARP_SOURCE_MAX_SCALED_PIXELS",
    "SHARP_SOURCE_MIN_ASPECT_RATIO",
    "SHARP_SOURCE_MIN_DIMENSION",
    "VISUAL_PRESETS",
    "PROVIDER",
    "RemotionTimelineError",
    "RemotionTimelineToolError",
    "RemotionTimelineValidationError",
    "SCHEMA_VERSION",
    "TIMING_SOURCE",
    "compile_remotion_timeline",
    "frames_to_milliseconds",
    "milliseconds_to_frames",
    "normalize_internal_clips",
    "remotion_timeline_audit_payload",
    "remotion_timeline_cache_key",
    "remotion_timeline_public_result",
    "remotion_output_policy",
    "safe_remotion_timeline_error",
    "validate_remotion_timeline_payload",
]
