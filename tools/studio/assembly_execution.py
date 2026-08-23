from __future__ import annotations

"""Fail-closed request and result contracts for local FFmpeg assembly."""

import re
from typing import Any


MAX_ASSEMBLY_DURATION_MS = 30 * 60 * 1000
MAX_CACHE_KEY_CHARS = 256
_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_ALLOWED_BODY_KEYS = {
    "video_artifact_id",
    "narration_attempt_id",
    "include_captioned",
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
    return {
        "video_artifact_id": video_artifact_id,
        "narration_attempt_id": narration_attempt_id,
        "include_captioned": include_captioned,
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
        **verified_hashes,
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_assembly_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, LocalAssemblyError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_assembly_failed", "The local assembly job failed."
