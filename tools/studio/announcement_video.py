from __future__ import annotations

"""Closed HOOK -> MESSAGE -> CTA announcement-video recipe contract.

The announcement layer owns only a small, editable product recipe.  It does
not render media itself: a validated recipe compiles to the existing Detailed
Test Video v1 contract so narration, Remotion, assembly, caching, and QC keep
their established provenance and retry semantics.
"""

import hashlib
import re
from typing import Any, Mapping, Sequence

from .detailed_test_video import (
    DetailedTestVideoValidationError,
    validate_detailed_test_video_payload,
)
from .remotion_timeline_execution import (
    DEFAULT_VISUAL_PRESET,
    VISUAL_PRESETS,
    SCREEN_THEMES,
    RemotionTimelineValidationError,
    frames_to_milliseconds,
    milliseconds_to_frames,
    validate_focus_region,
)
from .security import SecurityError, canonical_json, validate_identifier


ANNOUNCEMENT_VIDEO_SCHEMA_VERSION = 1
ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET = "shorts_ja_15s_v1"
SCREEN_EXPLAINER_TEMPLATE_PRESET = "screen_explainer_ja_v1"
CREATOR_TEMPLATE_PRESET = "shorts_creator_ja_v1"
ANNOUNCEMENT_VIDEO_ROLES = ("hook", "message", "cta")
ANNOUNCEMENT_VIDEO_TRANSITION_MS = 250
ANNOUNCEMENT_VIDEO_MIN_DURATION_MS = 10_000
ANNOUNCEMENT_VIDEO_MAX_DURATION_MS = 20_000
ANNOUNCEMENT_VIDEO_OVERLAY_POLICY = "shorts_safe_headline_v1"

_RECIPE_KEYS = {
    "schema_version",
    "name",
    "template_preset",
    "scenes",
    "voice",
    "rate",
    "pronunciations",
    "include_captioned",
    "caption_style_preset",
    "audio_mix_preset",
    "variant",
}
_SCENE_REQUIRED_KEYS = {
    "role",
    "video_artifact_id",
    "start_ms",
    "end_ms",
    "volume_percent",
    "headline",
    "narration",
}
_SCENE_KEYS = _SCENE_REQUIRED_KEYS | {"visual_preset", "focus_region"}
_PRONUNCIATION_KEYS = {"source", "target"}
_RECIPE_ID_RE = re.compile(r"^announcement_[0-9a-f]{32}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_ASCII_TOKEN_RE = re.compile(r"[!-~]+")
_FORBIDDEN_VISIBLE_TEXT_CHARACTERS = {
    "\u00a0",
    "\u200b",
    "\u200c",
    "\u200d",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2060",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
    "\ufeff",
}
_ROLE_OVERLAY_POSITIONS = {
    "hook": "center",
    "message": "top",
    "cta": "center",
}


class AnnouncementVideoValidationError(ValueError):
    def __init__(
        self,
        message: str = "The announcement video recipe is invalid.",
        *,
        code: str = "invalid_announcement_video_recipe",
    ):
        super().__init__(message)
        self.code = code


class AnnouncementRecipeConflict(AnnouncementVideoValidationError):
    def __init__(self) -> None:
        super().__init__(
            "The announcement recipe changed after it was loaded.",
            code="announcement_recipe_conflict",
        )


def validate_announcement_recipe_id(value: Any) -> str:
    try:
        validate_identifier(value, label="announcement recipe id")
    except (SecurityError, TypeError, ValueError):
        raise AnnouncementVideoValidationError() from None
    if _RECIPE_ID_RE.fullmatch(value) is None:
        raise AnnouncementVideoValidationError()
    return value


def _integer(
    value: Any,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnnouncementVideoValidationError()
    if value < minimum or value > maximum:
        raise AnnouncementVideoValidationError()
    return value


def _text(value: Any, *, maximum: int, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise AnnouncementVideoValidationError()
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized or len(normalized) > maximum or _CONTROL_RE.search(normalized):
        raise AnnouncementVideoValidationError()
    if not multiline and "\n" in normalized:
        raise AnnouncementVideoValidationError()
    return normalized


def _display_units(value: str) -> int:
    return sum(
        1 if 0x20 <= ord(char) <= 0x7E or 0xFF61 <= ord(char) <= 0xFF9F else 2
        for char in value
    )


def _headline(value: Any) -> str:
    headline = _text(value, maximum=80, multiline=True)
    lines = headline.splitlines()
    if (
        not 1 <= len(lines) <= 2
        or any(not line.strip() for line in lines)
        or any(char in _FORBIDDEN_VISIBLE_TEXT_CHARACTERS for char in headline)
        or any(_display_units(line) > 20 for line in lines)
        or any(len(token) > 20 for token in _ASCII_TOKEN_RE.findall(headline))
    ):
        raise AnnouncementVideoValidationError()
    return "\n".join(line.strip() for line in lines)


def _scene(value: Any, *, expected_role: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not _SCENE_REQUIRED_KEYS.issubset(value)
        or not set(value).issubset(_SCENE_KEYS)
    ):
        raise AnnouncementVideoValidationError()
    if value.get("role") != expected_role:
        raise AnnouncementVideoValidationError()
    try:
        artifact_id = validate_identifier(
            value.get("video_artifact_id"), label="video artifact id"
        )
    except (SecurityError, TypeError, ValueError):
        raise AnnouncementVideoValidationError() from None
    if re.fullmatch(r"art_[0-9a-f]{32}", artifact_id) is None:
        raise AnnouncementVideoValidationError()
    start_ms = _integer(value.get("start_ms"), minimum=0, maximum=60_000)
    end_ms = _integer(value.get("end_ms"), minimum=0, maximum=60_000)
    if end_ms - start_ms < 1_000 or end_ms - start_ms > 10_000:
        raise AnnouncementVideoValidationError()
    normalized = {
        "role": expected_role,
        "video_artifact_id": artifact_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "volume_percent": _integer(
            value.get("volume_percent"), minimum=0, maximum=100
        ),
        "headline": _headline(value.get("headline")),
        "narration": _text(value.get("narration"), maximum=200, multiline=False),
    }
    if "visual_preset" in value:
        visual_preset = value.get("visual_preset")
        if not isinstance(visual_preset, str) or visual_preset not in VISUAL_PRESETS:
            raise AnnouncementVideoValidationError()
        normalized["visual_preset"] = visual_preset
    if "focus_region" in value:
        try:
            normalized["focus_region"] = validate_focus_region(value["focus_region"])
        except RemotionTimelineValidationError:
            raise AnnouncementVideoValidationError() from None
    return normalized


def _pronunciations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 100:
        raise AnnouncementVideoValidationError()
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != _PRONUNCIATION_KEYS:
            raise AnnouncementVideoValidationError()
        source = _text(item.get("source"), maximum=512)
        target = _text(item.get("target"), maximum=512)
        if source in seen:
            raise AnnouncementVideoValidationError()
        seen.add(source)
        output.append({"source": source, "target": target})
    return output


def announcement_recipe_to_detailed_payload(
    recipe: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile one normalized announcement recipe to exact Detailed v1."""

    scenes = recipe["scenes"]
    screen_explainer = recipe["template_preset"] == SCREEN_EXPLAINER_TEMPLATE_PRESET
    creator = recipe["template_preset"] == CREATOR_TEMPLATE_PRESET
    clips: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        duration_ms = scene["end_ms"] - scene["start_ms"]
        clips.append(
            {
                "video_artifact_id": scene["video_artifact_id"],
                "start_ms": scene["start_ms"],
                "end_ms": scene["end_ms"],
                "volume_percent": scene["volume_percent"],
                "visual_preset": scene.get(
                    "visual_preset", DEFAULT_VISUAL_PRESET
                ),
                "transition_to_next": (
                    None
                    if screen_explainer or creator or index == len(scenes) - 1
                    else {
                        "type": "fade",
                        "duration_ms": ANNOUNCEMENT_VIDEO_TRANSITION_MS,
                    }
                ),
                "overlay": {
                    "text": scene["headline"],
                    "start_ms": 0 if creator else 125,
                    "end_ms": duration_ms - 125,
                    "position": "top" if screen_explainer or creator else _ROLE_OVERLAY_POSITIONS[scene["role"]],
                    "style_preset": "shorts_creator_v1" if creator else "shorts_ja_large_v1",
                },
            }
        )
        if screen_explainer:
            clips[-1]["layout_preset"] = "screen_explainer_v1"
            if "screen_theme" in recipe:
                clips[-1]["screen_theme"] = recipe["screen_theme"]
        if "focus_region" in scene:
            # The detailed validator rejects focus on the legacy layout even
            # when a caller bypasses the outer announcement normalizer.
            clips[-1]["focus_region"] = scene["focus_region"]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "clips": clips,
        "segments": [{"text": scene["narration"]} for scene in scenes],
        "rate": recipe["rate"],
        "include_captioned": recipe["include_captioned"],
        "caption_style_preset": recipe["caption_style_preset"],
        "audio_mix_preset": recipe["audio_mix_preset"],
        "variant": recipe["variant"],
    }
    if recipe["voice"] is not None:
        payload["voice"] = recipe["voice"]
    if recipe["pronunciations"]:
        payload["pronunciations"] = recipe["pronunciations"]
    return validate_detailed_test_video_payload(payload)


def announcement_narration_segment_starts(
    recipe: Mapping[str, Any],
) -> tuple[int, ...]:
    """Return output-timeline starts for HOOK, MESSAGE, and CTA narration.

    Remotion overlaps adjacent clips during the fixed fade.  Narration must
    therefore start at each clip's compiled output position rather than at
    the sum of the raw source trims.
    """

    normalized = validate_announcement_recipe_payload(dict(recipe))
    clips = announcement_recipe_to_detailed_payload(normalized)["clips"]
    starts: list[int] = []
    cursor_frames = 0
    for clip in clips:
        starts.append(
            0
            if cursor_frames == 0
            else frames_to_milliseconds(cursor_frames)
        )
        cursor_frames += milliseconds_to_frames(
            clip["end_ms"] - clip["start_ms"]
        )
        transition = clip["transition_to_next"]
        if transition is not None:
            cursor_frames -= milliseconds_to_frames(transition["duration_ms"])
    return tuple(starts)


def validate_announcement_recipe_payload(body: Any) -> dict[str, Any]:
    """Normalize an exact v1 editable recipe and prove its compiled contract."""

    if not isinstance(body, dict) or not _RECIPE_KEYS.issubset(body) or not set(body).issubset(_RECIPE_KEYS | {"screen_theme"}):
        raise AnnouncementVideoValidationError()
    if (
        body.get("schema_version") != ANNOUNCEMENT_VIDEO_SCHEMA_VERSION
        or not isinstance(body.get("template_preset"), str)
        or body.get("template_preset") not in {
            ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET, SCREEN_EXPLAINER_TEMPLATE_PRESET, CREATOR_TEMPLATE_PRESET
        }
    ):
        raise AnnouncementVideoValidationError()
    raw_scenes = body.get("scenes")
    if not isinstance(raw_scenes, list) or len(raw_scenes) != len(
        ANNOUNCEMENT_VIDEO_ROLES
    ):
        raise AnnouncementVideoValidationError()
    scenes = [
        _scene(item, expected_role=role)
        for item, role in zip(raw_scenes, ANNOUNCEMENT_VIDEO_ROLES, strict=True)
    ]
    screen_explainer = body["template_preset"] == SCREEN_EXPLAINER_TEMPLATE_PRESET
    if "screen_theme" in body and (
        not screen_explainer
        or not isinstance(body["screen_theme"], str)
        or body["screen_theme"] not in SCREEN_THEMES
    ):
        raise AnnouncementVideoValidationError()
    if not screen_explainer and any("focus_region" in scene for scene in scenes):
        raise AnnouncementVideoValidationError()
    creator = body["template_preset"] == CREATOR_TEMPLATE_PRESET
    transition_ms = 0 if screen_explainer or creator else ANNOUNCEMENT_VIDEO_TRANSITION_MS
    total_duration_ms = (
        sum(item["end_ms"] - item["start_ms"] for item in scenes)
        - transition_ms * (len(scenes) - 1)
    )
    minimum_ms = 15_000 if screen_explainer else ANNOUNCEMENT_VIDEO_MIN_DURATION_MS
    maximum_ms = 30_000 if screen_explainer or creator else ANNOUNCEMENT_VIDEO_MAX_DURATION_MS
    if not minimum_ms <= total_duration_ms <= maximum_ms:
        raise AnnouncementVideoValidationError()

    voice_value = body.get("voice")
    voice = None if voice_value is None or voice_value == "" else _text(
        voice_value, maximum=128
    )
    rate = _integer(body.get("rate"), minimum=-10, maximum=10)
    include_captioned = body.get("include_captioned")
    if not isinstance(include_captioned, bool):
        raise AnnouncementVideoValidationError()
    caption_style_preset = body.get("caption_style_preset")
    audio_mix_preset = body.get("audio_mix_preset")
    variant = body.get("variant")
    if caption_style_preset not in {"studio_default_v1", "shorts_ja_large_v1", "shorts_ja_phrase_v1"}:
        raise AnnouncementVideoValidationError()
    if audio_mix_preset not in {
        "narration_only_v1",
        "source_under_narration_v1",
    }:
        raise AnnouncementVideoValidationError()
    if (
        audio_mix_preset == "source_under_narration_v1"
        and not any(scene["volume_percent"] > 0 for scene in scenes)
    ):
        raise AnnouncementVideoValidationError()
    if variant not in {"clean", "captioned"}:
        raise AnnouncementVideoValidationError()

    normalized = {
        "schema_version": ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
        "name": _text(body.get("name"), maximum=120),
        "template_preset": body["template_preset"],
        "scenes": scenes,
        "voice": voice,
        "rate": rate,
        "pronunciations": _pronunciations(body.get("pronunciations")),
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style_preset,
        "audio_mix_preset": audio_mix_preset,
        "variant": variant,
    }
    if "screen_theme" in body:
        normalized["screen_theme"] = body["screen_theme"]
    try:
        announcement_recipe_to_detailed_payload(normalized)
    except DetailedTestVideoValidationError:
        raise AnnouncementVideoValidationError() from None
    return normalized


def announcement_recipe_digest(recipe: Mapping[str, Any]) -> str:
    normalized = validate_announcement_recipe_payload(dict(recipe))
    return hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest().upper()


def validate_announcement_save_payload(body: Any) -> tuple[int, dict[str, Any]]:
    if not isinstance(body, dict) or set(body) != {
        "schema_version",
        "expected_revision",
        "recipe",
    }:
        raise AnnouncementVideoValidationError()
    if body.get("schema_version") != ANNOUNCEMENT_VIDEO_SCHEMA_VERSION:
        raise AnnouncementVideoValidationError()
    expected_revision = _integer(
        body.get("expected_revision"), minimum=0, maximum=1_000_000
    )
    return expected_revision, validate_announcement_recipe_payload(body.get("recipe"))


def validate_announcement_duplicate_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != {
        "schema_version",
        "source_revision",
        "new_recipe_id",
        "name",
    }:
        raise AnnouncementVideoValidationError()
    if body.get("schema_version") != ANNOUNCEMENT_VIDEO_SCHEMA_VERSION:
        raise AnnouncementVideoValidationError()
    return {
        "source_revision": _integer(
            body.get("source_revision"), minimum=1, maximum=1_000_000
        ),
        "new_recipe_id": validate_announcement_recipe_id(body.get("new_recipe_id")),
        "name": _text(body.get("name"), maximum=120),
    }


def validate_announcement_execute_payload(body: Any) -> int:
    if not isinstance(body, dict) or set(body) != {"schema_version", "revision"}:
        raise AnnouncementVideoValidationError()
    if body.get("schema_version") != ANNOUNCEMENT_VIDEO_SCHEMA_VERSION:
        raise AnnouncementVideoValidationError()
    return _integer(body.get("revision"), minimum=1, maximum=1_000_000)


def announcement_recipe_audit_summary(recipe: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_announcement_recipe_payload(dict(recipe))
    summary = {
        "schema_version": ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
        "name": normalized["name"],
        "template_preset": normalized["template_preset"],
        "roles": [item["role"] for item in normalized["scenes"]],
        "scene_count": len(normalized["scenes"]),
        "headline_chars": [len(item["headline"]) for item in normalized["scenes"]],
        "narration_chars": [len(item["narration"]) for item in normalized["scenes"]],
        "overlay_policy": (
            "shorts_creator_safe_motion_v1" if normalized["template_preset"] == CREATOR_TEMPLATE_PRESET else "screen_explainer_safe_header_v1"
            if normalized["template_preset"] == SCREEN_EXPLAINER_TEMPLATE_PRESET
            else ANNOUNCEMENT_VIDEO_OVERLAY_POLICY
        ),
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "audio_mix_preset": normalized["audio_mix_preset"],
        "variant": normalized["variant"],
    }
    # Legacy announcement events are append-only canonical JSON.  Preserve
    # their historical summary shape unless a new recipe revision explicitly
    # selected a visual preset.
    if any("visual_preset" in item for item in normalized["scenes"]):
        summary["visual_presets"] = [
            item.get("visual_preset", DEFAULT_VISUAL_PRESET)
            for item in normalized["scenes"]
        ]
    if any("focus_region" in item for item in normalized["scenes"]):
        summary["focus_regions"] = [item.get("focus_region") for item in normalized["scenes"]]
    if "screen_theme" in normalized:
        summary["screen_theme"] = normalized["screen_theme"]
    return summary


__all__ = [
    "ANNOUNCEMENT_VIDEO_MAX_DURATION_MS",
    "ANNOUNCEMENT_VIDEO_MIN_DURATION_MS",
    "ANNOUNCEMENT_VIDEO_OVERLAY_POLICY",
    "ANNOUNCEMENT_VIDEO_ROLES",
    "ANNOUNCEMENT_VIDEO_SCHEMA_VERSION",
    "ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET",
    "SCREEN_EXPLAINER_TEMPLATE_PRESET",
    "ANNOUNCEMENT_VIDEO_TRANSITION_MS",
    "AnnouncementRecipeConflict",
    "AnnouncementVideoValidationError",
    "announcement_narration_segment_starts",
    "announcement_recipe_audit_summary",
    "announcement_recipe_digest",
    "announcement_recipe_to_detailed_payload",
    "validate_announcement_duplicate_payload",
    "validate_announcement_execute_payload",
    "validate_announcement_recipe_id",
    "validate_announcement_recipe_payload",
    "validate_announcement_save_payload",
]
