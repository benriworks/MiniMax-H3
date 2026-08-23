from __future__ import annotations

"""Fail-closed control-plane contracts for the local technical QC worker.

The media implementation lives in :mod:`tools.studio.qc`.  Keeping these
helpers free of media imports makes it possible for the Studio service to
validate a worker result before registering any of its files.
"""

import re
from typing import Any, Mapping


MAX_DURATION_MS = 30 * 60 * 1000
MIN_DURATION_MS = 50
MAX_CACHE_KEY_CHARS = 256
MAX_INPUT_BYTES = 2 * 1024 * 1024 * 1024

_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_ALLOWED_VARIANTS = {"clean", "captioned"}
# The browser may select the assembly attempt and the master variant only.
# Artifact ID, input hash/bytes, and expected duration are derived by the
# service from the immutable assembly attempt and registered artifact.
_ALLOWED_BODY_KEYS = {"assembly_attempt_id", "variant"}


class LocalQcError(RuntimeError):
    """A bounded error safe to pass over the background-job boundary."""

    def __init__(self, message: str, *, code: str = "local_qc_failed"):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


class LocalQcValidationError(ValueError):
    """A malformed public QC request."""

    def __init__(self, message: str, *, code: str = "invalid_local_qc_request"):
        super().__init__(message)
        self.code = code


def _strict_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise LocalQcValidationError(f"{label} must be a SHA-256 digest")
    return value.upper()


def _strict_duration(value: Any, *, label: str = "expected_duration_ms") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_DURATION_MS
        or value > MAX_DURATION_MS
    ):
        raise LocalQcValidationError(
            f"{label} must be an integer between {MIN_DURATION_MS} and {MAX_DURATION_MS}"
        )
    return value


def _strict_bytes(value: Any, *, label: str = "input_bytes") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > MAX_INPUT_BYTES
    ):
        raise LocalQcValidationError(f"{label} is invalid")
    return value


def _strict_id(value: Any, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise LocalQcValidationError(f"{label} is invalid")
    return value


def validate_local_qc_payload(body: Any) -> dict[str, Any]:
    """Validate and normalize the public local QC request.

    Artifact paths and hashes are deliberately not accepted from the browser.
    The service resolves the registered assembly artifact and passes those
    values to the worker after it has checked the database record.
    """

    if not isinstance(body, dict):
        raise LocalQcValidationError("request body must be an object")
    if set(body) - _ALLOWED_BODY_KEYS:
        raise LocalQcValidationError("request body contains unsupported fields")
    assembly_attempt_id = _strict_id(
        body.get("assembly_attempt_id"),
        label="assembly_attempt_id",
        pattern=_ATTEMPT_ID_RE,
    )
    variant = body.get("variant")
    if not isinstance(variant, str) or variant not in _ALLOWED_VARIANTS:
        raise LocalQcValidationError("variant must be clean or captioned")
    return {
        "assembly_attempt_id": assembly_attempt_id,
        "variant": variant,
    }


def qc_audit_payload(
    payload: Mapping[str, Any],
    *,
    assembly_artifact_id: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    cache_key: str | None = None,
) -> dict[str, Any]:
    """Return a bounded, non-secret request summary for audit/event records."""

    if not isinstance(payload, Mapping):
        raise LocalQcValidationError("payload must be an object")
    normalized_attempt = _strict_id(
        payload.get("assembly_attempt_id"),
        label="assembly_attempt_id",
        pattern=_ATTEMPT_ID_RE,
    )
    normalized_artifact = _strict_id(
        assembly_artifact_id,
        label="assembly_artifact_id",
        pattern=_ARTIFACT_ID_RE,
    )
    variant = payload.get("variant")
    if not isinstance(variant, str) or variant not in _ALLOWED_VARIANTS:
        raise LocalQcValidationError("variant must be clean or captioned")
    duration = _strict_duration(expected_duration_ms)
    result: dict[str, Any] = {
        "assembly_attempt_id": normalized_attempt,
        "assembly_artifact_id": normalized_artifact,
        "variant": variant,
        "expected_duration_ms": duration,
        "input_sha256": _strict_sha256(input_sha256, label="input_sha256"),
        "input_bytes": _strict_bytes(input_bytes),
    }
    if cache_key is not None:
        if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
            raise LocalQcValidationError("cache_key is invalid")
        result["cache_key"] = cache_key
    return result


def _safe_cache_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_CACHE_KEY_CHARS
        or _CACHE_KEY_RE.fullmatch(value) is None
    ):
        raise LocalQcError(
            "The local QC worker returned an invalid cache key.",
            code="invalid_worker_result",
        )
    return value


def _result_id(value: Any, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise LocalQcError(
            "The local QC worker returned invalid provenance.",
            code="invalid_worker_result",
        )
    return value


def qc_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    expected_assembly_attempt_id: str,
    expected_assembly_artifact_id: str,
    expected_variant: str,
    expected_input_sha256: str,
    expected_input_bytes: int,
    expected_duration_ms: int,
    artifacts: list[dict[str, Any]],
    cache_hit: bool,
) -> dict[str, Any]:
    """Allow only verified local-QC metadata into Studio records."""

    if not isinstance(raw, dict):
        raise LocalQcError(
            "The local QC worker returned an invalid result.",
            code="invalid_worker_result",
        )
    if not isinstance(expected_cache_key, str) or _CACHE_KEY_RE.fullmatch(expected_cache_key) is None:
        raise LocalQcError("The expected QC cache key is invalid.", code="invalid_worker_result")
    expected_attempt = _result_id(
        expected_assembly_attempt_id,
        label="assembly_attempt_id",
        pattern=_ATTEMPT_ID_RE,
    )
    expected_artifact = _result_id(
        expected_assembly_artifact_id,
        label="assembly_artifact_id",
        pattern=_ARTIFACT_ID_RE,
    )
    if not isinstance(expected_variant, str) or expected_variant not in _ALLOWED_VARIANTS:
        raise LocalQcError("The expected QC variant is invalid.", code="invalid_worker_result")
    try:
        expected_sha = _strict_sha256(expected_input_sha256, label="input_sha256")
        expected_bytes = _strict_bytes(expected_input_bytes)
        expected_duration = _strict_duration(expected_duration_ms)
    except LocalQcValidationError as exc:
        raise LocalQcError(
            "The expected QC provenance is invalid.", code="invalid_worker_result"
        ) from exc

    if raw.get("provider") != "local_ffmpeg_qc" or raw.get("timing_source") != "ffprobe":
        raise LocalQcError(
            "The local QC worker returned invalid metadata.",
            code="invalid_worker_result",
        )
    if (
        "provider_task_id" not in raw
        or raw.get("provider_task_id") is not None
        or isinstance(raw.get("actual_cost"), bool)
        or raw.get("actual_cost") != 0
    ):
        raise LocalQcError(
            "The local QC worker returned invalid cost metadata.",
            code="invalid_worker_result",
        )
    returned_key = _safe_cache_key(raw.get("cache_key"))
    if returned_key != expected_cache_key:
        raise LocalQcError(
            "The local QC worker returned a mismatched cache key.",
            code="invalid_worker_result",
        )
    raw_cache_hit = raw.get("cache_hit")
    if not isinstance(raw_cache_hit, bool) or raw_cache_hit != cache_hit:
        raise LocalQcError(
            "The local QC worker returned invalid cache metadata.",
            code="invalid_worker_result",
        )
    if raw.get("analysis_status") != "succeeded":
        raise LocalQcError(
            "The local QC worker did not complete analysis.",
            code="invalid_worker_result",
        )
    raw_verdict = raw.get("technical_verdict")
    if not isinstance(raw_verdict, str) or raw_verdict not in {"pass", "fail"}:
        raise LocalQcError(
            "The local QC worker returned an invalid technical verdict.",
            code="invalid_worker_result",
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms < 0
        or duration_ms > MAX_DURATION_MS
    ):
        raise LocalQcError(
            "The local QC worker returned invalid timing.",
            code="invalid_worker_result",
        )
    if (
        raw.get("assembly_attempt_id") != expected_attempt
        or raw.get("assembly_artifact_id") != expected_artifact
        or raw.get("variant") != expected_variant
        or raw.get("input_sha256") != expected_sha
        or raw.get("input_bytes") != expected_bytes
        or raw.get("expected_duration_ms") != expected_duration
    ):
        raise LocalQcError(
            "The local QC worker returned mismatched provenance.",
            code="invalid_worker_result",
        )
    checks = raw.get("checks")
    media_facts = raw.get("media_facts")
    if not isinstance(checks, dict) or not isinstance(media_facts, dict):
        raise LocalQcError(
            "The local QC worker returned invalid analysis facts.",
            code="invalid_worker_result",
        )
    if not isinstance(artifacts, list):
        raise LocalQcError(
            "The local QC worker returned invalid artifacts.",
            code="invalid_worker_result",
        )
    return {
        "analysis_status": "succeeded",
        "technical_verdict": raw["technical_verdict"],
        "cache_hit": cache_hit,
        "duration_ms": duration_ms,
        "assembly_attempt_id": expected_attempt,
        "assembly_artifact_id": expected_artifact,
        "variant": expected_variant,
        "input_sha256": expected_sha,
        "input_bytes": expected_bytes,
        "expected_duration_ms": expected_duration,
        "checks": checks,
        "media_facts": media_facts,
        "artifacts": artifacts,
        "cache_key": expected_cache_key,
        "provider": "local_ffmpeg_qc",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_qc_error(exc: BaseException) -> tuple[str, str]:
    """Convert arbitrary worker failures into stable public error metadata."""

    if isinstance(exc, LocalQcError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_qc_failed", "The local QC job failed."


__all__ = [
    "LocalQcError",
    "LocalQcValidationError",
    "MAX_DURATION_MS",
    "MAX_INPUT_BYTES",
    "MIN_DURATION_MS",
    "qc_audit_payload",
    "qc_public_result",
    "safe_qc_error",
    "validate_local_qc_payload",
]
