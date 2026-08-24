from __future__ import annotations

"""Public contracts for the billable external Studio TTS worker.

The control-plane contract is deliberately kept separate from the ElevenLabs
HTTP/media adapter.  ``service.py`` can validate a request and a worker result
without importing an HTTP client or a local FFmpeg installation.  This module
never accepts an API key and never stores the submitted narration text in an
audit summary; the media adapter owns the actual request and artifact files.
"""

import hashlib
import math
import re
from typing import Any, Mapping

from .security import canonical_json


EXTERNAL_TTS_PROVIDER = "elevenlabs"
EXTERNAL_TTS_MODEL = "eleven_multilingual_v2"
EXTERNAL_TTS_OUTPUT_FORMAT = "mp3_44100_128"
EXTERNAL_TTS_TIMING_SOURCE = "elevenlabs_alignment"
EXTERNAL_TTS_IMPLEMENTATION_VERSION = "elevenlabs-timestamps-v1"
EXTERNAL_TTS_SCHEMA_VERSION = 1

MAX_SEGMENTS = 100
MAX_SEGMENT_CHARS = 4_000
MAX_TOTAL_CHARS = 100_000
MAX_VOICE_ID_CHARS = 128
MAX_HEADER_VALUE_CHARS = 256
MAX_CACHE_KEY_CHARS = 256
MAX_DURATION_MS = 30 * 60 * 1000
MAX_SEED = 4_294_967_295

_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_CHARACTER_COST_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_ALLOWED_BODY_KEYS = {
    "provider",
    "voice_id",
    "model_id",
    "segments",
    "voice_settings",
    "seed",
    "confirm_billable",
}
_ALLOWED_SEGMENT_KEYS = {"text"}
_ALLOWED_VOICE_SETTINGS_KEYS = {
    "stability",
    "similarity_boost",
    "style",
    "use_speaker_boost",
    "speed",
}
_CONTROL_CHARS = frozenset(chr(value) for value in range(32)) | {chr(127)}


class ExternalTTSError(RuntimeError):
    """A bounded error safe to cross the background-job boundary."""

    error_code = "external_tts_failed"

    def __init__(self, message: str, *, code: str | None = None):
        # ``message`` is always supplied by this module.  Callers must not pass
        # provider response bodies, request URLs, or exception text here.
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = message


class ExternalTTSValidationError(ValueError):
    """Raised for a malformed public external-TTS request body."""

    def __init__(self, message: str, *, code: str = "invalid_external_tts_request"):
        super().__init__(message)
        self.code = code


def _strict_text(value: Any, *, field: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ExternalTTSValidationError(f"{field} must be a string")
    if required and not value.strip():
        raise ExternalTTSValidationError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ExternalTTSValidationError(f"{field} is too long")
    if any(character in _CONTROL_CHARS for character in value):
        raise ExternalTTSValidationError(f"{field} contains unsupported control characters")
    # JSON's UTF-8 encoder rejects lone surrogates.  Rejecting them here keeps
    # malformed input from becoming an unbounded/secret-bearing exception.
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ExternalTTSValidationError(f"{field} contains invalid Unicode")
    return value


def _finite_number(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExternalTTSValidationError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ExternalTTSValidationError(f"{field} is out of range")
    return result


def validate_external_tts_payload(body: Any) -> dict[str, Any]:
    """Validate and normalize the public ``elevenlabs_tts`` request.

    The only accepted top-level keys are ``provider``, ``voice_id``,
    ``model_id``, ``segments``, ``voice_settings``, ``seed``, and the explicit
    ``confirm_billable`` gate.  ``voice_settings`` must contain all five
    supported settings so provider defaults cannot drift beneath a stable
    cache identity.  The gate must be the literal boolean ``true``;
    a truthy string is not accepted.  Endpoint, API key, timeout, FFmpeg path,
    and output policy are intentionally not public request fields.
    """

    if not isinstance(body, dict):
        raise ExternalTTSValidationError("request body must be an object")
    if any(not isinstance(key, str) for key in body):
        raise ExternalTTSValidationError("request body keys must be strings")
    if set(body) - _ALLOWED_BODY_KEYS:
        raise ExternalTTSValidationError("request body contains unsupported fields")

    if body.get("provider") != EXTERNAL_TTS_PROVIDER:
        raise ExternalTTSValidationError("provider must be elevenlabs")

    voice_id = body.get("voice_id")
    if not isinstance(voice_id, str) or not _VOICE_ID_RE.fullmatch(voice_id):
        raise ExternalTTSValidationError("voice_id is invalid")

    model_id = body.get("model_id")
    if model_id != EXTERNAL_TTS_MODEL:
        raise ExternalTTSValidationError(
            f"model_id must be {EXTERNAL_TTS_MODEL}"
        )

    raw_segments = body.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ExternalTTSValidationError("segments must be a non-empty array")
    if len(raw_segments) > MAX_SEGMENTS:
        raise ExternalTTSValidationError("segments contains too many entries")
    segments: list[dict[str, str]] = []
    total_chars = 0
    for index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict) or set(raw_segment) != _ALLOWED_SEGMENT_KEYS:
            raise ExternalTTSValidationError(
                f"segments[{index}] must contain only text"
            )
        text = _strict_text(
            raw_segment.get("text"),
            field=f"segments[{index}].text",
            maximum=MAX_SEGMENT_CHARS,
        )
        total_chars += len(text)
        if total_chars > MAX_TOTAL_CHARS:
            raise ExternalTTSValidationError("the narration text is too long")
        segments.append({"text": text})

    raw_voice_settings = body.get("voice_settings")
    if raw_voice_settings is None:
        raise ExternalTTSValidationError(
            "voice_settings must contain all supported settings"
        )
    if not isinstance(raw_voice_settings, dict):
        raise ExternalTTSValidationError("voice_settings must be an object")
    if any(not isinstance(key, str) for key in raw_voice_settings):
        raise ExternalTTSValidationError("voice_settings keys must be strings")
    if set(raw_voice_settings) != _ALLOWED_VOICE_SETTINGS_KEYS:
        raise ExternalTTSValidationError(
            "voice_settings must contain all supported settings"
        )
    voice_settings: dict[str, Any] = {}
    if "stability" in raw_voice_settings:
        voice_settings["stability"] = _finite_number(
            raw_voice_settings["stability"],
            field="voice_settings.stability",
            minimum=0.0,
            maximum=1.0,
        )
    if "similarity_boost" in raw_voice_settings:
        voice_settings["similarity_boost"] = _finite_number(
            raw_voice_settings["similarity_boost"],
            field="voice_settings.similarity_boost",
            minimum=0.0,
            maximum=1.0,
        )
    if "style" in raw_voice_settings:
        voice_settings["style"] = _finite_number(
            raw_voice_settings["style"],
            field="voice_settings.style",
            minimum=0.0,
            maximum=1.0,
        )
    if "use_speaker_boost" in raw_voice_settings:
        value = raw_voice_settings["use_speaker_boost"]
        if not isinstance(value, bool):
            raise ExternalTTSValidationError(
                "voice_settings.use_speaker_boost must be a boolean"
            )
        voice_settings["use_speaker_boost"] = value
    if "speed" in raw_voice_settings:
        voice_settings["speed"] = _finite_number(
            raw_voice_settings["speed"],
            field="voice_settings.speed",
            minimum=0.7,
            maximum=1.2,
        )

    raw_seed = body.get("seed")
    if raw_seed is None:
        seed: int | None = None
    else:
        if isinstance(raw_seed, bool) or not isinstance(raw_seed, int):
            raise ExternalTTSValidationError("seed must be an integer")
        if raw_seed < 0 or raw_seed > MAX_SEED:
            raise ExternalTTSValidationError("seed is out of range")
        seed = raw_seed

    confirm_billable = body.get("confirm_billable")
    if confirm_billable is not True or not isinstance(confirm_billable, bool):
        raise ExternalTTSValidationError(
            "confirm_billable must be true",
            code="billable_confirmation_required",
        )

    return {
        "provider": EXTERNAL_TTS_PROVIDER,
        "voice_id": voice_id,
        "model_id": EXTERNAL_TTS_MODEL,
        "segments": segments,
        "voice_settings": voice_settings,
        "seed": seed,
        "confirm_billable": True,
    }


def external_tts_request_text(payload: Mapping[str, Any]) -> str:
    """Return the one-and-only provider request text for a normalized payload."""

    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise ExternalTTSValidationError("segments must be an array")
    try:
        return "\n".join(segment["text"] for segment in segments)
    except (KeyError, TypeError) as exc:
        raise ExternalTTSValidationError("segments are invalid") from exc


def _cache_identity_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    # ``confirm_billable`` is an authorization gate, not a media identity.  It
    # is intentionally absent so a separately approved request can reuse an
    # already published, byte-verified result without creating a second cache.
    return {
        key: payload[key]
        for key in (
            "provider",
            "voice_id",
            "model_id",
            "segments",
            "voice_settings",
            "seed",
        )
        if key in payload
    }


def external_tts_cache_key(payload: Mapping[str, Any]) -> str:
    """Build a deterministic, content-addressed key for one provider call."""

    normalized = validate_external_tts_payload(dict(payload))
    identity = {
        "schema_version": EXTERNAL_TTS_SCHEMA_VERSION,
        "implementation_version": EXTERNAL_TTS_IMPLEMENTATION_VERSION,
        "output_format": EXTERNAL_TTS_OUTPUT_FORMAT,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "payload": _cache_identity_payload(normalized),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def external_tts_payload_digest(payload: Mapping[str, Any]) -> str:
    normalized = validate_external_tts_payload(dict(payload))
    return hashlib.sha256(
        canonical_json(_cache_identity_payload(normalized)).encode("utf-8")
    ).hexdigest().upper()


def external_tts_audit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded, non-secret audit summary for the request body."""

    normalized = validate_external_tts_payload(dict(payload))
    segments = normalized["segments"]
    return {
        "provider": normalized["provider"],
        "billable_confirmed": True,
        "voice_id": normalized["voice_id"],
        "model_id": normalized["model_id"],
        "segment_count": len(segments),
        "text_chars": sum(len(item["text"]) for item in segments),
        "segment_text_sha256": [
            hashlib.sha256(item["text"].encode("utf-8")).hexdigest().upper()
            for item in segments
        ],
        "voice_settings": dict(normalized["voice_settings"]),
        "seed": normalized["seed"],
        "output_format": EXTERNAL_TTS_OUTPUT_FORMAT,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
    }


def _bounded_header(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ExternalTTSError(
                "The external TTS provider returned invalid metadata.",
                code="invalid_external_provider_metadata",
            ) from exc
    if not isinstance(value, str) or not value or len(value) > MAX_HEADER_VALUE_CHARS:
        raise ExternalTTSError(
            "The external TTS provider returned invalid metadata.",
            code="invalid_external_provider_metadata",
        )
    if any(character in _CONTROL_CHARS for character in value):
        raise ExternalTTSError(
            "The external TTS provider returned invalid metadata.",
            code="invalid_external_provider_metadata",
        )
    return value


def _character_cost(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value <= 2**63 - 1:
            return value
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        )
    value = _bounded_header(value, field="character_cost")
    if value is None:
        return None
    if not _CHARACTER_COST_RE.fullmatch(value):
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        )
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        ) from exc
    # Keep the persisted integer bounded even if a provider sends an absurdly
    # long but otherwise valid decimal header.
    if parsed > 2**63 - 1:
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        )
    return parsed


def external_tts_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    artifacts: list[dict[str, Any]],
    cache_hit: bool,
) -> dict[str, Any]:
    """Validate the allowlisted worker result before DB/event persistence."""

    if not isinstance(raw, dict):
        raise ExternalTTSError(
            "The external TTS worker returned an invalid result.",
            code="invalid_worker_result",
        )
    if raw.get("provider") != EXTERNAL_TTS_PROVIDER:
        raise ExternalTTSError(
            "The external TTS worker returned invalid metadata.",
            code="invalid_worker_result",
        )
    if raw.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE:
        raise ExternalTTSError(
            "The external TTS worker returned invalid timing metadata.",
            code="invalid_worker_result",
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms <= 0
        or duration_ms > MAX_DURATION_MS
    ):
        raise ExternalTTSError(
            "The external TTS worker returned invalid timing.",
            code="invalid_worker_result",
        )
    returned_key = raw.get("cache_key")
    if (
        not isinstance(returned_key, str)
        or len(returned_key) > MAX_CACHE_KEY_CHARS
        or not _CACHE_KEY_RE.fullmatch(returned_key)
        or returned_key != expected_cache_key
    ):
        raise ExternalTTSError(
            "The external TTS worker returned an invalid cache key.",
            code="invalid_worker_result",
        )
    raw_cache_hit = raw.get("cache_hit")
    if not isinstance(raw_cache_hit, bool) or raw_cache_hit != cache_hit:
        raise ExternalTTSError(
            "The external TTS worker returned invalid cache metadata.",
            code="invalid_worker_result",
        )
    request_id = _bounded_header(raw.get("request_id"), field="request_id")
    if "provider_task_id" not in raw:
        raise ExternalTTSError(
            "The external TTS worker returned invalid task metadata.",
            code="invalid_worker_result",
        )
    provider_task_id = _bounded_header(
        raw.get("provider_task_id"), field="provider_task_id"
    )
    if provider_task_id != request_id:
        raise ExternalTTSError(
            "The external TTS worker returned inconsistent task metadata.",
            code="invalid_worker_result",
        )
    if "actual_cost" not in raw or raw.get("actual_cost") is not None:
        raise ExternalTTSError(
            "The external TTS worker returned invalid cost metadata.",
            code="invalid_worker_result",
        )
    provider_request_id = _bounded_header(
        raw.get("provider_request_id", request_id), field="provider_request_id"
    )
    if request_id != provider_request_id:
        raise ExternalTTSError(
            "The external TTS worker returned inconsistent request metadata.",
            code="invalid_worker_result",
        )
    character_cost = _character_cost(raw.get("character_cost"))
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": returned_key,
        "request_cache_key": expected_cache_key,
        "cache_hit": cache_hit,
        "provider": EXTERNAL_TTS_PROVIDER,
        "provider_task_id": provider_task_id,
        "request_id": request_id,
        "provider_request_id": provider_request_id,
        "character_cost": character_cost,
        "actual_cost": None,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "cost": {
            "amount": None,
            "currency": "USD",
            "source": "provider_unreported",
        },
    }


def safe_external_tts_error(exc: BaseException) -> tuple[str, str]:
    """Convert arbitrary adapter exceptions to a stable public pair."""

    if isinstance(exc, ExternalTTSError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    if isinstance(exc, ExternalTTSValidationError):
        return str(exc.code)[:128], str(exc)[:1000]
    return "external_tts_failed", "The external TTS job failed."


# Compatibility aliases make the control-plane boundary discoverable next to
# the similarly named local narration helpers without duplicating behavior.
validate_elevenlabs_payload = validate_external_tts_payload
elevenlabs_cache_key = external_tts_cache_key
public_result = external_tts_public_result
audit_payload = external_tts_audit_payload


__all__ = [
    "EXTERNAL_TTS_IMPLEMENTATION_VERSION",
    "EXTERNAL_TTS_MODEL",
    "EXTERNAL_TTS_OUTPUT_FORMAT",
    "EXTERNAL_TTS_PROVIDER",
    "EXTERNAL_TTS_SCHEMA_VERSION",
    "EXTERNAL_TTS_TIMING_SOURCE",
    "ExternalTTSError",
    "ExternalTTSValidationError",
    "external_tts_audit_payload",
    "external_tts_cache_key",
    "external_tts_payload_digest",
    "external_tts_public_result",
    "external_tts_request_text",
    "safe_external_tts_error",
    "validate_external_tts_payload",
    "validate_elevenlabs_payload",
    "elevenlabs_cache_key",
    "public_result",
    "audit_payload",
]
