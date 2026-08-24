from __future__ import annotations

"""Fail-closed request and result contracts for local FFmpeg assembly."""

import re
from typing import Any


MAX_ASSEMBLY_DURATION_MS = 30 * 60 * 1000
MAX_CACHE_KEY_CHARS = 256
CAPTION_STYLE_PRESET_STUDIO_DEFAULT_V1 = "studio_default_v1"
CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1 = "shorts_ja_large_v1"
DEFAULT_CAPTION_STYLE_PRESET = CAPTION_STYLE_PRESET_STUDIO_DEFAULT_V1
CAPTION_STYLE_PRESETS = (
    CAPTION_STYLE_PRESET_STUDIO_DEFAULT_V1,
    CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
)
_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_ALLOWED_BODY_KEYS = {
    "video_artifact_id",
    "narration_attempt_id",
    "include_captioned",
    "caption_style_preset",
}

_CAPTION_STYLE_FIELDS = {
    "preset",
    "ass_style_name",
    "font_name",
    "font_size",
    "primary_color",
    "secondary_color",
    "outline_color",
    "back_color",
    "back_alpha",
    "bold",
    "italic",
    "underline",
    "strike_out",
    "scale_x",
    "scale_y",
    "spacing",
    "angle",
    "border_style",
    "outline_width",
    "shadow_depth",
    "alignment",
    "margin_left",
    "margin_right",
    "margin_vertical",
    "encoding",
    "wrap_style",
}

# These are renderer inputs, not caller-provided ASS fragments.  Every value is
# selected by a closed preset enum so neither a font path nor filter/override
# syntax can cross the public request boundary.
_CAPTION_STYLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    CAPTION_STYLE_PRESET_STUDIO_DEFAULT_V1: {
        "preset": CAPTION_STYLE_PRESET_STUDIO_DEFAULT_V1,
        "ass_style_name": "StudioDefault",
        "font_name": "Arial",
        "font_size": 42,
        "primary_color": "#FFFFFF",
        "secondary_color": "#FFFFFF",
        "outline_color": "#101010",
        "back_color": "#000000",
        "back_alpha": 144,
        "bold": False,
        "italic": False,
        "underline": False,
        "strike_out": False,
        "scale_x": 100,
        "scale_y": 100,
        "spacing": 0,
        "angle": 0,
        "border_style": 1,
        "outline_width": 2,
        "shadow_depth": 1,
        "alignment": 2,
        "margin_left": 48,
        "margin_right": 48,
        "margin_vertical": 48,
        "encoding": 1,
        "wrap_style": 2,
    },
    CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1: {
        "preset": CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
        "ass_style_name": "ShortsJaLarge",
        # A fixed family name is part of the preset.  The API never accepts a
        # font name or path; deployments that need byte-identical glyphs can
        # later map this preset to a pinned, hash-verified font asset.
        "font_name": "Yu Gothic UI",
        "font_size": 80,
        "primary_color": "#FFFFFF",
        "secondary_color": "#FFFFFF",
        "outline_color": "#101010",
        "back_color": "#000000",
        "back_alpha": 144,
        "bold": True,
        "italic": False,
        "underline": False,
        "strike_out": False,
        "scale_x": 100,
        "scale_y": 100,
        "spacing": 0,
        "angle": 0,
        "border_style": 1,
        "outline_width": 5,
        "shadow_depth": 1,
        "alignment": 2,
        "margin_left": 96,
        "margin_right": 96,
        "margin_vertical": 300,
        "encoding": 1,
        "wrap_style": 0,
    },
}


class LocalAssemblyError(RuntimeError):
    """A bounded public error that may cross the background-job boundary."""

    def __init__(self, message: str, *, code: str = "local_assembly_failed"):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


class LocalAssemblyValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_local_assembly_request"):
        super().__init__(message)
        self.code = code


def normalize_caption_style_preset(value: Any = DEFAULT_CAPTION_STYLE_PRESET) -> dict[str, Any]:
    """Resolve one closed preset into the exact ASS-safe renderer style."""

    if not isinstance(value, str) or value not in _CAPTION_STYLE_DEFINITIONS:
        raise LocalAssemblyValidationError("caption_style_preset is not supported")
    return dict(_CAPTION_STYLE_DEFINITIONS[value])


def validate_normalized_caption_style(value: Any) -> dict[str, Any]:
    """Accept only a byte-for-byte canonical style produced by this module."""

    if not isinstance(value, dict) or set(value) != _CAPTION_STYLE_FIELDS:
        raise LocalAssemblyValidationError("caption_style is invalid")
    canonical = normalize_caption_style_preset(value.get("preset"))
    if value != canonical:
        raise LocalAssemblyValidationError("caption_style is not canonical")
    return canonical


def validate_local_assembly_payload(body: Any) -> dict[str, Any]:
    """Normalize the public assembly request without accepting extra fields."""

    if not isinstance(body, dict):
        raise LocalAssemblyValidationError("request body must be an object")
    if set(body) - _ALLOWED_BODY_KEYS:
        raise LocalAssemblyValidationError("request body contains unsupported fields")
    video_artifact_id = body.get("video_artifact_id")
    narration_attempt_id = body.get("narration_attempt_id")
    include_captioned = body.get("include_captioned", True)
    if not isinstance(video_artifact_id, str) or not _ARTIFACT_ID_RE.fullmatch(
        video_artifact_id
    ):
        raise LocalAssemblyValidationError("video_artifact_id is invalid")
    if not isinstance(narration_attempt_id, str) or not _ATTEMPT_ID_RE.fullmatch(
        narration_attempt_id
    ):
        raise LocalAssemblyValidationError("narration_attempt_id is invalid")
    if not isinstance(include_captioned, bool):
        raise LocalAssemblyValidationError("include_captioned must be a boolean")
    caption_style = normalize_caption_style_preset(
        body.get("caption_style_preset", DEFAULT_CAPTION_STYLE_PRESET)
    )
    if not include_captioned and caption_style["preset"] != DEFAULT_CAPTION_STYLE_PRESET:
        raise LocalAssemblyValidationError(
            "caption_style_preset requires include_captioned=true"
        )
    return {
        "video_artifact_id": video_artifact_id,
        "narration_attempt_id": narration_attempt_id,
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "caption_style": caption_style,
    }


def assembly_audit_payload(
    payload: dict[str, Any],
    *,
    source_video_sha256: str,
    narration_wav_sha256: str,
    captions_sha256: str,
) -> dict[str, Any]:
    return {
        "video_artifact_id": payload["video_artifact_id"],
        "narration_attempt_id": payload["narration_attempt_id"],
        "include_captioned": payload["include_captioned"],
        "caption_style_preset": payload["caption_style_preset"],
        "caption_style": validate_normalized_caption_style(payload["caption_style"]),
        "source_video_sha256": source_video_sha256,
        "narration_wav_sha256": narration_wav_sha256,
        "captions_sha256": captions_sha256,
    }


def assembly_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    expected_hashes: dict[str, str],
    expected_include_captioned: bool,
    expected_caption_style: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]],
    cache_hit: bool,
) -> dict[str, Any]:
    """Allow only verified local-FFmpeg metadata into Studio records."""

    if not isinstance(raw, dict):
        raise LocalAssemblyError(
            "The local assembly worker returned an invalid result.",
            code="invalid_worker_result",
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms <= 0
        or duration_ms > MAX_ASSEMBLY_DURATION_MS
    ):
        raise LocalAssemblyError(
            "The local assembly worker returned invalid timing.",
            code="invalid_worker_result",
        )
    if raw.get("provider") != "local_ffmpeg" or raw.get("timing_source") != "ffprobe":
        raise LocalAssemblyError(
            "The local assembly worker returned invalid metadata.",
            code="invalid_worker_result",
        )
    actual_cost = raw.get("actual_cost")
    if (
        "provider_task_id" not in raw
        or raw.get("provider_task_id") is not None
        or isinstance(actual_cost, bool)
        or not isinstance(actual_cost, int)
        or actual_cost != 0
    ):
        raise LocalAssemblyError(
            "The local assembly worker returned invalid cost metadata.",
            code="invalid_worker_result",
        )
    returned_key = raw.get("cache_key")
    if (
        not isinstance(returned_key, str)
        or len(returned_key) > MAX_CACHE_KEY_CHARS
        or not _CACHE_KEY_RE.fullmatch(returned_key)
        or returned_key != expected_cache_key
    ):
        raise LocalAssemblyError(
            "The local assembly worker returned an invalid cache key.",
            code="invalid_worker_result",
        )
    raw_cache_hit = raw.get("cache_hit")
    if (
        "cache_hit" not in raw
        or not isinstance(raw_cache_hit, bool)
        or raw_cache_hit != cache_hit
    ):
        raise LocalAssemblyError(
            "The local assembly worker returned invalid cache metadata.",
            code="invalid_worker_result",
        )
    include_captioned = raw.get("include_captioned")
    if not isinstance(include_captioned, bool) or include_captioned != expected_include_captioned:
        raise LocalAssemblyError(
            "The local assembly worker returned invalid output metadata.",
            code="invalid_worker_result",
        )
    try:
        canonical_style = (
            normalize_caption_style_preset()
            if expected_caption_style is None
            else validate_normalized_caption_style(expected_caption_style)
        )
    except LocalAssemblyValidationError as exc:
        raise LocalAssemblyError(
            "The expected caption style is invalid.",
            code="invalid_worker_result",
        ) from exc
    if (
        raw.get("caption_style_preset") != canonical_style["preset"]
        or raw.get("caption_style") != canonical_style
    ):
        raise LocalAssemblyError(
            "The local assembly worker returned invalid caption style metadata.",
            code="invalid_worker_result",
        )
    verified_hashes: dict[str, str] = {}
    for field in ("source_video_sha256", "narration_wav_sha256", "captions_sha256"):
        value = raw.get(field)
        if (
            not isinstance(value, str)
            or not _SHA256_RE.fullmatch(value)
            or value != expected_hashes[field]
        ):
            raise LocalAssemblyError(
                "The local assembly worker returned mismatched provenance.",
                code="invalid_worker_result",
            )
        verified_hashes[field] = value
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": returned_key,
        "request_cache_key": expected_cache_key,
        "cache_hit": cache_hit,
        "provider": "local_ffmpeg",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "include_captioned": include_captioned,
        "caption_style_preset": canonical_style["preset"],
        "caption_style": canonical_style,
        **verified_hashes,
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_assembly_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, LocalAssemblyError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_assembly_failed", "The local assembly job failed."
