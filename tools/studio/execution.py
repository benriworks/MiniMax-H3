from __future__ import annotations

"""Validation and public-result helpers for local Studio execution.

This module deliberately contains no media implementation.  The worker imports
``tools.studio.narration`` at execution time so that the control plane can be
tested without installing a speech engine and so a missing engine fails closed.
"""

import hashlib
import re
from typing import Any

from .security import canonical_json


MAX_SEGMENTS = 100
MAX_SEGMENT_CHARS = 4_000
MAX_TOTAL_CHARS = 100_000
MAX_PRONUNCIATIONS = 100
MAX_PRONUNCIATION_CHARS = 512
MIN_RATE = -10
MAX_RATE = 10
MAX_VOICE_CHARS = 128
MAX_PROVIDER_CHARS = 128
MAX_CACHE_KEY_CHARS = 256
MAX_DURATION_MS = 30 * 60 * 1000
NARRATION_TIMING_POLICY_ABSOLUTE_SEGMENT_STARTS_V1 = (
    "absolute_segment_starts_v1"
)

_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ALLOWED_BODY_KEYS = {"segments", "voice", "rate", "pronunciations"}
_ALLOWED_SEGMENT_KEYS = {"text"}
_ALLOWED_PRONUNCIATION_KEYS = {"source", "target"}


class LocalNarrationError(RuntimeError):
    """A safe error that may cross the background-job boundary."""

    def __init__(self, message: str, *, code: str = "local_narration_failed"):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


class LocalNarrationValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_local_narration_request"):
        super().__init__(message)
        self.code = code


def _strict_string(value: Any, *, field: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise LocalNarrationValidationError(f"{field} must be a string")
    if "\x00" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise LocalNarrationValidationError(f"{field} contains unsupported control characters")
    if required and not value.strip():
        raise LocalNarrationValidationError(f"{field} must not be empty")
    if len(value) > maximum:
        raise LocalNarrationValidationError(f"{field} is too long")
    return value


def validate_local_narration_payload(body: Any) -> dict[str, Any]:
    """Validate and normalize the public local_sapi request body.

    Unknown keys and malformed nested values are rejected rather than silently
    ignored.  The returned object contains only the fields accepted by the
    worker contract and is safe to pass to the local media adapter.
    """

    if not isinstance(body, dict):
        raise LocalNarrationValidationError("request body must be an object")
    unknown = set(body) - _ALLOWED_BODY_KEYS
    if unknown:
        raise LocalNarrationValidationError("request body contains unsupported fields")

    segments = body.get("segments")
    if not isinstance(segments, list) or not segments:
        raise LocalNarrationValidationError("segments must be a non-empty array")
    if len(segments) > MAX_SEGMENTS:
        raise LocalNarrationValidationError("segments contains too many entries")
    normalized_segments: list[dict[str, str]] = []
    total_chars = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or set(segment) != _ALLOWED_SEGMENT_KEYS:
            raise LocalNarrationValidationError(f"segments[{index}] must contain only text")
        text = _strict_string(
            segment.get("text"), field=f"segments[{index}].text", maximum=MAX_SEGMENT_CHARS
        )
        total_chars += len(text)
        if total_chars > MAX_TOTAL_CHARS:
            raise LocalNarrationValidationError("the narration text is too long")
        normalized_segments.append({"text": text})

    normalized: dict[str, Any] = {"segments": normalized_segments}
    raw_voice = body.get("voice")
    if raw_voice is not None and raw_voice != "":
        voice = _strict_string(raw_voice, field="voice", maximum=MAX_VOICE_CHARS)
        normalized["voice"] = voice
    else:
        normalized["voice"] = None
    rate = body.get("rate", 0)
    if rate is not None:
        if isinstance(rate, bool) or not isinstance(rate, int):
            raise LocalNarrationValidationError("rate must be an integer")
        if rate < MIN_RATE or rate > MAX_RATE:
            raise LocalNarrationValidationError(
                f"rate must be between {MIN_RATE} and {MAX_RATE}"
            )
    else:
        raise LocalNarrationValidationError("rate must be an integer")
    normalized["rate"] = rate

    pronunciations = body.get("pronunciations", [])
    if pronunciations is None:
        pronunciations = []
    if not isinstance(pronunciations, list):
        raise LocalNarrationValidationError("pronunciations must be an array")
    if len(pronunciations) > MAX_PRONUNCIATIONS:
        raise LocalNarrationValidationError("pronunciations contains too many entries")
    normalized_pronunciations: list[dict[str, str]] = []
    pronunciation_chars = 0
    for index, item in enumerate(pronunciations):
        if not isinstance(item, dict) or set(item) != _ALLOWED_PRONUNCIATION_KEYS:
            raise LocalNarrationValidationError(
                f"pronunciations[{index}] must contain only source and target"
            )
        source = _strict_string(
            item.get("source"),
            field=f"pronunciations[{index}].source",
            maximum=MAX_PRONUNCIATION_CHARS,
        )
        target = _strict_string(
            item.get("target"),
            field=f"pronunciations[{index}].target",
            maximum=MAX_PRONUNCIATION_CHARS,
        )
        pronunciation_chars += len(source) + len(target)
        if pronunciation_chars > MAX_TOTAL_CHARS:
            raise LocalNarrationValidationError("pronunciation data is too long")
        normalized_pronunciations.append({"source": source, "target": target})
    seen_sources: set[str] = set()
    for pronunciation in normalized_pronunciations:
        if pronunciation["source"] in seen_sources:
            raise LocalNarrationValidationError("pronunciation sources must be unique")
        seen_sources.add(pronunciation["source"])
    normalized["pronunciations"] = normalized_pronunciations
    return normalized


def validate_internal_narration_segment_starts(
    value: Any,
    *,
    segment_count: int,
) -> tuple[int, ...]:
    """Validate the private absolute-start capability used by orchestration.

    The schedule deliberately remains outside the public local-SAPI request
    body.  Callers must possess an in-process service capability before this
    value can reach the worker.
    """

    if (
        isinstance(segment_count, bool)
        or not isinstance(segment_count, int)
        or segment_count < 1
        or segment_count > MAX_SEGMENTS
        or not isinstance(value, (list, tuple))
        or len(value) != segment_count
    ):
        raise LocalNarrationValidationError(
            "the internal narration timing schedule is invalid"
        )
    starts: list[int] = []
    for start_ms in value:
        if (
            isinstance(start_ms, bool)
            or not isinstance(start_ms, int)
            or start_ms < 0
            or start_ms > MAX_DURATION_MS
            or (starts and start_ms <= starts[-1])
        ):
            raise LocalNarrationValidationError(
                "the internal narration timing schedule is invalid"
            )
        starts.append(start_ms)
    return tuple(starts)


def narration_timing_identity(
    segment_start_ms: Any,
    *,
    segment_count: int,
) -> dict[str, Any]:
    starts = validate_internal_narration_segment_starts(
        segment_start_ms,
        segment_count=segment_count,
    )
    return {
        "policy": NARRATION_TIMING_POLICY_ABSOLUTE_SEGMENT_STARTS_V1,
        "segment_start_ms": list(starts),
    }


def narration_cache_key(
    payload: dict[str, Any],
    *,
    segment_start_ms: Any = None,
) -> str:
    """Return a deterministic request key independent of object ordering."""

    identity = {
        "schema_version": 1,
        "implementation_version": "local-sapi-v1",
        "payload": payload,
    }
    if segment_start_ms is not None:
        identity["timing_policy"] = narration_timing_identity(
            segment_start_ms,
            segment_count=len(payload.get("segments", [])),
        )
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def audit_payload(
    payload: dict[str, Any],
    *,
    segment_start_ms: Any = None,
) -> dict[str, Any]:
    """Return a bounded, non-secret request summary for SQLite/events."""

    segments = payload.get("segments", [])
    audit = {
        "segment_count": len(segments),
        "text_chars": sum(len(item.get("text", "")) for item in segments),
        "segment_text_sha256": [
            hashlib.sha256(item.get("text", "").encode("utf-8")).hexdigest()
            for item in segments
        ],
        "voice": payload.get("voice"),
        "rate": payload.get("rate"),
        "pronunciation_count": len(payload.get("pronunciations", [])),
    }
    if segment_start_ms is not None:
        timing = narration_timing_identity(
            segment_start_ms,
            segment_count=len(segments),
        )
        audit["narration_timing_policy"] = timing["policy"]
        audit["narration_segment_start_ms"] = timing["segment_start_ms"]
    return audit


def public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    artifacts: list[dict[str, Any]],
    cache_hit: bool,
) -> dict[str, Any]:
    """Keep only the media adapter fields allowed in an audit/result record."""

    if not isinstance(raw, dict):
        raise LocalNarrationError("The local narration worker returned an invalid result.", code="invalid_worker_result")
    duration_ms = raw.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
        raise LocalNarrationError("The local narration worker returned invalid timing.", code="invalid_worker_result")
    if duration_ms < 0 or duration_ms > MAX_DURATION_MS:
        raise LocalNarrationError("The local narration worker returned invalid timing.", code="invalid_worker_result")
    provider = raw.get("provider")
    timing_source = raw.get("timing_source")
    if provider != "windows_sapi":
        raise LocalNarrationError("The local narration worker returned invalid metadata.", code="invalid_worker_result")
    if timing_source != "wav_frames":
        raise LocalNarrationError("The local narration worker returned invalid metadata.", code="invalid_worker_result")
    actual_cost = raw.get("actual_cost")
    if (
        "provider_task_id" not in raw
        or raw.get("provider_task_id") is not None
        or isinstance(actual_cost, bool)
        or not isinstance(actual_cost, int)
        or actual_cost != 0
    ):
        raise LocalNarrationError("The local narration worker returned invalid cost metadata.", code="invalid_worker_result")
    returned_key = raw.get("cache_key")
    if not isinstance(returned_key, str) or len(returned_key) > MAX_CACHE_KEY_CHARS or not _CACHE_KEY_RE.fullmatch(returned_key):
        raise LocalNarrationError("The local narration worker returned an invalid cache key.", code="invalid_worker_result")
    if returned_key != expected_cache_key:
        raise LocalNarrationError("The local narration worker returned a mismatched cache key.", code="invalid_worker_result")
    raw_cache_hit = raw.get("cache_hit")
    if "cache_hit" not in raw or not isinstance(raw_cache_hit, bool) or raw_cache_hit != cache_hit:
        raise LocalNarrationError("The local narration worker returned invalid cache metadata.", code="invalid_worker_result")
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": returned_key,
        "request_cache_key": expected_cache_key,
        "cache_hit": bool(cache_hit),
        "provider": provider,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": timing_source,
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_error(exc: BaseException) -> tuple[str, str]:
    """Convert arbitrary worker exceptions to a stable public error pair."""

    if isinstance(exc, LocalNarrationError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_narration_failed", "The local narration job failed."
