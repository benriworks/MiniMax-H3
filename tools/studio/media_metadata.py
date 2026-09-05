from __future__ import annotations

"""Small, bounded media facts derived from a probe that already ran.

This module never opens media or invokes ffprobe. Metadata is advisory, not a
creative-quality assessment, and unknown values remain JSON null.
"""

import math
import re
from fractions import Fraction
from typing import Any


VIDEO_METADATA_KEYS = (
    "duration_seconds", "width", "height", "fps", "has_audio", "video_codec",
)
_DECIMAL = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_RATE = re.compile(r"^[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?$")
_CODEC = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9A-Fa-f]{64}$")


def _positive_number(value: Any, *, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and 0 < number <= maximum else None


def _probe_number(value: Any, *, maximum: float) -> float | None:
    if isinstance(value, str):
        if len(value) > 64 or _DECIMAL.fullmatch(value) is None:
            return None
        value = float(value)
    return _positive_number(value, maximum=maximum)


def parse_frame_rate(value: Any) -> float | None:
    """Parse ffprobe's rational rates without eval, truncation, or zero division."""
    if isinstance(value, str):
        if len(value) > 64 or _RATE.fullmatch(value) is None:
            return None
        try:
            numerator, separator, denominator = value.partition("/")
            rate = Fraction(numerator)
            if separator:
                rate /= Fraction(denominator)
            value = float(rate)
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
    return _positive_number(value, maximum=1000)


def normalize_video_metadata(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {key: None for key in VIDEO_METADATA_KEYS}
    result["duration_seconds"] = _positive_number(
        source.get("duration_seconds"), maximum=366 * 24 * 60 * 60,
    )
    result["fps"] = _positive_number(source.get("fps"), maximum=1000)
    for dimension in ("width", "height"):
        raw = source.get(dimension)
        if isinstance(raw, int) and not isinstance(raw, bool) and 0 < raw <= 65536:
            result[dimension] = raw
    if isinstance(source.get("has_audio"), bool):
        result["has_audio"] = source["has_audio"]
    codec = source.get("video_codec")
    if isinstance(codec, str) and _CODEC.fullmatch(codec):
        result["video_codec"] = codec
    return result


def video_metadata_from_probe(probe: Any) -> dict[str, Any]:
    if not isinstance(probe, dict):
        return normalize_video_metadata(None)
    streams = probe.get("streams")
    if not isinstance(streams, list):
        return normalize_video_metadata(None)
    videos = [
        item for item in streams
        if isinstance(item, dict) and item.get("codec_type") == "video"
        and not (isinstance(item.get("disposition"), dict)
                 and item["disposition"].get("attached_pic") == 1)
    ]
    if not videos:
        return normalize_video_metadata(None)
    video = videos[0]
    container = probe.get("format")
    duration = _probe_number(video.get("duration"), maximum=366 * 24 * 60 * 60)
    if duration is None and isinstance(container, dict):
        duration = _probe_number(container.get("duration"), maximum=366 * 24 * 60 * 60)
    fps = parse_frame_rate(video.get("avg_frame_rate"))
    if fps is None:
        fps = parse_frame_rate(video.get("r_frame_rate"))
    has_audio: bool | None = None
    if any(isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams):
        has_audio = True
    elif all(isinstance(item, dict) and isinstance(item.get("codec_type"), str) for item in streams):
        has_audio = False
    return normalize_video_metadata({
        "duration_seconds": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "has_audio": has_audio,
        "video_codec": video.get("codec_name"),
    })


def media_fingerprint(value: Any) -> tuple[str, int, int] | None:
    if not isinstance(value, dict):
        return None
    digest, size, modified = value.get("sha256"), value.get("bytes"), value.get("mtime_ns")
    if (
        not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        or isinstance(size, bool) or not isinstance(size, int) or size <= 0
        or isinstance(modified, bool) or not isinstance(modified, int) or modified < 0
    ):
        return None
    return digest.upper(), size, modified


def bound_video_metadata(value: Any, identity: dict[str, Any]) -> dict[str, Any]:
    """Use cached probe facts only when digest, byte count, and mtime all agree."""
    expected = media_fingerprint(identity)
    if expected is None or media_fingerprint(value) != expected:
        return normalize_video_metadata(None)
    return normalize_video_metadata(value.get("metadata"))
