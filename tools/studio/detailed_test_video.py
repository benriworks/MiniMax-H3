from __future__ import annotations

"""Closed local orchestration for one auditable Remotion test video.

The top worker owns no media implementation.  It queues the existing Windows
SAPI, Remotion, FFmpeg assembly, and technical-QC stages on their normal lanes
and verifies each linked job/attempt before passing its registered artifact to
the next stage.
"""

import hashlib
import re
import time
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .assembly_execution import (
    DEFAULT_CAPTION_STYLE_PRESET,
    LocalAssemblyValidationError,
    normalize_audio_mix_preset,
    normalize_caption_style_preset,
    validate_local_assembly_payload,
)
from .execution import (
    LocalNarrationValidationError,
    audit_payload as narration_audit_payload,
    narration_timing_identity,
    validate_local_narration_payload,
)
from .jobs import JobCancelled, JobExecutionContext
from .qc_execution import LocalQcValidationError, validate_local_qc_payload
from .remotion_timeline_execution import (
    RemotionTimelineValidationError,
    validate_remotion_timeline_payload,
)
from .security import SecurityError, canonical_json, validate_identifier


DETAILED_TEST_VIDEO_SCHEMA_VERSION = 1
DETAILED_TEST_VIDEO_IMPLEMENTATION_VERSION = "detailed-test-video-v2"
DETAILED_TEST_VIDEO_JOB_KIND = "detailed_test_video"
DETAILED_TEST_VIDEO_PROFILE = "local_sapi"
DETAILED_TEST_VIDEO_STAGES = ("narration", "timeline", "assembly", "qc")
SHORTS_JA_CAPTION_PREFLIGHT_POLICY = "shorts_ja_large_preflight_v1"
ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY = "announcement_scene_starts_v1"

_PUBLIC_KEYS = {
    "schema_version",
    "clips",
    "segments",
    "voice",
    "rate",
    "pronunciations",
    "include_captioned",
    "caption_style_preset",
    "audio_mix_preset",
    "variant",
}
_REQUIRED_KEYS = {
    "schema_version",
    "clips",
    "segments",
    "include_captioned",
    "caption_style_preset",
    "audio_mix_preset",
    "variant",
}
_STAGE_METHODS = {
    "narration": "execute_local_narration",
    "timeline": "execute_remotion_timeline",
    "assembly": "execute_local_assembly",
    "qc": "execute_local_qc",
}
_STAGE_JOB_KINDS = {
    "narration": "local_narration",
    "timeline": "local_remotion_timeline",
    "assembly": "local_assembly",
    "qc": "local_qc",
}
_STAGE_TIMEOUT_SECONDS = {stage: 30 * 60.0 for stage in DETAILED_TEST_VIDEO_STAGES}
_TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_FORBIDDEN_CAPTION_CHARACTERS = {
    "\u00a0",  # no-break space
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u202a",  # bidi embedding/override controls
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2060",  # word joiner
    "\u2066",  # bidi isolates
    "\u2067",
    "\u2068",
    "\u2069",
    "\ufeff",  # zero width no-break space / BOM
}
_ASCII_TOKEN_RE = re.compile(r"[!-~]+")


class DetailedTestVideoValidationError(ValueError):
    def __init__(
        self,
        message: str = "The detailed test video request is invalid.",
        *,
        code: str = "invalid_detailed_test_video_request",
    ):
        super().__init__(message)
        self.code = code


class DetailedTestVideoError(RuntimeError):
    """A bounded top-level failure safe for job/event publication."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "detailed_test_video_failed",
    ):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


def _validation_error() -> DetailedTestVideoValidationError:
    return DetailedTestVideoValidationError()


def _caption_display_units(text: str) -> int:
    return sum(
        1 if 0x20 <= ord(char) <= 0x7E or 0xFF61 <= ord(char) <= 0xFF9F else 2
        for char in text
    )


def _validate_shorts_ja_caption_preflight(segments: Sequence[Mapping[str, str]]) -> None:
    if not 1 <= len(segments) <= 6:
        raise _validation_error()
    for segment in segments:
        text = segment["text"]
        if any(char in _FORBIDDEN_CAPTION_CHARACTERS for char in text):
            raise _validation_error()
        if _caption_display_units(text) > 38:
            raise _validation_error()
        if any(len(token) > 20 for token in _ASCII_TOKEN_RE.findall(text)):
            raise _validation_error()


def _caption_preflight_policy(payload: Mapping[str, Any]) -> str | None:
    """Return derived policy metadata without widening the public request schema."""

    if (
        payload.get("include_captioned") is True
        and payload.get("caption_style_preset") == "shorts_ja_large_v1"
    ):
        return SHORTS_JA_CAPTION_PREFLIGHT_POLICY
    return None


def validate_detailed_test_video_payload(body: Any) -> dict[str, Any]:
    """Normalize the exact public schema-v1 request and reject extra knobs."""

    if not isinstance(body, dict) or any(not isinstance(key, str) for key in body):
        raise _validation_error()
    keys = set(body)
    if keys - _PUBLIC_KEYS or not _REQUIRED_KEYS.issubset(keys):
        raise _validation_error()
    if body.get("schema_version") != DETAILED_TEST_VIDEO_SCHEMA_VERSION:
        raise _validation_error()

    narration_body: dict[str, Any] = {"segments": body.get("segments")}
    for field in ("voice", "rate", "pronunciations"):
        if field in body:
            narration_body[field] = body.get(field)
    try:
        timeline = validate_remotion_timeline_payload(
            {
                "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
                "clips": body.get("clips"),
            }
        )
        narration = validate_local_narration_payload(narration_body)
        caption_style = normalize_caption_style_preset(body.get("caption_style_preset"))
        audio_mix = normalize_audio_mix_preset(body.get("audio_mix_preset"))
    except (
        RemotionTimelineValidationError,
        LocalNarrationValidationError,
        LocalAssemblyValidationError,
        TypeError,
        ValueError,
    ):
        raise _validation_error() from None

    include_captioned = body.get("include_captioned")
    variant = body.get("variant")
    if not isinstance(include_captioned, bool) or variant not in {"clean", "captioned"}:
        raise _validation_error()
    if variant == "captioned" and not include_captioned:
        raise _validation_error()
    if (
        not include_captioned
        and caption_style["preset"] != DEFAULT_CAPTION_STYLE_PRESET
    ):
        raise _validation_error()
    if include_captioned and caption_style["preset"] == "shorts_ja_large_v1":
        _validate_shorts_ja_caption_preflight(narration["segments"])

    return {
        "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
        "clips": timeline["clips"],
        "segments": narration["segments"],
        "voice": narration["voice"],
        "rate": narration["rate"],
        "pronunciations": narration["pronunciations"],
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "audio_mix_preset": audio_mix["preset"],
        "variant": variant,
    }


def _source_identity(source_clips: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_clips, (list, tuple)) or not source_clips:
        raise DetailedTestVideoValidationError("source clip identity is invalid")
    normalized: list[dict[str, Any]] = []
    for item in source_clips:
        if not isinstance(item, Mapping):
            raise DetailedTestVideoValidationError("source clip identity is invalid")
        artifact_id = item.get("video_artifact_id")
        source_bytes = item.get("source_bytes")
        source_sha256 = item.get("source_sha256")
        try:
            validate_identifier(artifact_id, label="video artifact id")
        except (SecurityError, TypeError, ValueError):
            raise DetailedTestVideoValidationError("source clip identity is invalid") from None
        if (
            isinstance(source_bytes, bool)
            or not isinstance(source_bytes, int)
            or source_bytes <= 0
            or source_bytes > _MAX_ARTIFACT_BYTES
            or not isinstance(source_sha256, str)
            or _SHA256_RE.fullmatch(source_sha256.upper()) is None
        ):
            raise DetailedTestVideoValidationError("source clip identity is invalid")
        normalized.append(
            {
                "video_artifact_id": artifact_id,
                "source_bytes": source_bytes,
                "source_sha256": source_sha256.upper(),
            }
        )
    return normalized


def _announcement_narration_alignment(
    segment_start_ms: Sequence[int],
    *,
    segment_count: int,
) -> dict[str, Any]:
    try:
        timing = narration_timing_identity(
            segment_start_ms,
            segment_count=segment_count,
        )
    except LocalNarrationValidationError:
        raise DetailedTestVideoValidationError(
            "narration alignment is invalid"
        ) from None
    return {
        "policy": ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY,
        "segment_start_ms": timing["segment_start_ms"],
    }


def detailed_test_video_key(
    payload: dict[str, Any],
    *,
    source_clips: Sequence[Mapping[str, Any]],
    remotion_cache_key: str,
    narration_segment_start_ms: Sequence[int] | None = None,
) -> str:
    normalized = validate_detailed_test_video_payload(payload)
    if not isinstance(remotion_cache_key, str) or _SHA256_RE.fullmatch(
        remotion_cache_key
    ) is None:
        raise DetailedTestVideoValidationError("Remotion cache key is invalid")
    identity = {
        "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
        "implementation_version": DETAILED_TEST_VIDEO_IMPLEMENTATION_VERSION,
        "payload": normalized,
        "caption_preflight_policy": _caption_preflight_policy(normalized),
        "sources": _source_identity(source_clips),
        "remotion_cache_key": remotion_cache_key,
    }
    if narration_segment_start_ms is not None:
        alignment = _announcement_narration_alignment(
            narration_segment_start_ms,
            segment_count=len(normalized["segments"]),
        )
        identity["narration_alignment"] = alignment
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def detailed_test_video_audit_payload(
    payload: dict[str, Any],
    *,
    request_key: str,
    source_clips: Sequence[Mapping[str, Any]],
    remotion_cache_key: str,
    narration_segment_start_ms: Sequence[int] | None = None,
) -> dict[str, Any]:
    normalized = validate_detailed_test_video_payload(payload)
    sources = _source_identity(source_clips)
    if (
        not isinstance(request_key, str)
        or _SHA256_RE.fullmatch(request_key) is None
        or not isinstance(remotion_cache_key, str)
        or _SHA256_RE.fullmatch(remotion_cache_key) is None
    ):
        raise DetailedTestVideoValidationError("request key is invalid")
    narration = narration_audit_payload(
        {
            "segments": normalized["segments"],
            "voice": normalized["voice"],
            "rate": normalized["rate"],
            "pronunciations": normalized["pronunciations"],
        },
        segment_start_ms=narration_segment_start_ms,
    )
    request_payload_sha256 = hashlib.sha256(
        canonical_json(normalized).encode("utf-8")
    ).hexdigest().upper()
    clip_audit: list[dict[str, Any]] = []
    for clip, source in zip(normalized["clips"], sources, strict=True):
        overlay = clip["overlay"]
        clip_audit.append(
            {
                "video_artifact_id": clip["video_artifact_id"],
                "source_bytes": source["source_bytes"],
                "source_sha256": source["source_sha256"],
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
                "volume_percent": clip["volume_percent"],
                "transition_to_next": clip["transition_to_next"],
                "overlay": None
                if overlay is None
                else {
                    "text_sha256": hashlib.sha256(
                        overlay["text"].encode("utf-8")
                    ).hexdigest().upper(),
                    "text_chars": len(overlay["text"]),
                    "start_ms": overlay["start_ms"],
                    "end_ms": overlay["end_ms"],
                    "position": overlay["position"],
                    "style_preset": overlay["style_preset"],
                },
            }
        )
    audit = {
        "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
        "request_key": request_key,
        "request_payload_sha256": request_payload_sha256,
        "implementation_version": DETAILED_TEST_VIDEO_IMPLEMENTATION_VERSION,
        "remotion_cache_key": remotion_cache_key,
        "execution_profile": DETAILED_TEST_VIDEO_PROFILE,
        "clip_count": len(clip_audit),
        "clips": clip_audit,
        "segment_count": narration["segment_count"],
        "text_chars": narration["text_chars"],
        "segment_text_sha256": list(narration["segment_text_sha256"]),
        "voice": narration["voice"],
        "rate": narration["rate"],
        "pronunciation_count": narration["pronunciation_count"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "caption_preflight_policy": _caption_preflight_policy(normalized),
        "audio_mix_preset": normalized["audio_mix_preset"],
        "variant": normalized["variant"],
    }
    if narration_segment_start_ms is not None:
        alignment = _announcement_narration_alignment(
            narration_segment_start_ms,
            segment_count=len(normalized["segments"]),
        )
        audit["narration_alignment_policy"] = (
            alignment["policy"]
        )
        audit["narration_timing_policy"] = narration[
            "narration_timing_policy"
        ]
        audit["narration_segment_start_ms"] = alignment["segment_start_ms"]
    return audit


def safe_detailed_test_video_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, DetailedTestVideoValidationError):
        return exc.code, "The detailed test video request is invalid."
    if isinstance(exc, DetailedTestVideoError):
        return exc.error_code, exc.public_message
    if isinstance(exc, JobCancelled):
        return (
            "process_interrupted",
            "The Studio process stopped before the detailed test video completed.",
        )
    return "detailed_test_video_failed", "The detailed test video failed."


def _job_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("job")
    return nested if isinstance(nested, dict) else value


def _job_id(value: Any) -> str | None:
    record = _job_record(value)
    if record is None:
        return None
    candidate = record.get("id", record.get("job_id"))
    return candidate if isinstance(candidate, str) else None


def _attempt_id(value: Any) -> str | None:
    record = _job_record(value)
    if record is None:
        return None
    candidate = record.get("stage_attempt_id")
    if not isinstance(candidate, str):
        result = record.get("result")
        candidate = result.get("stage_attempt_id") if isinstance(result, dict) else None
    return candidate if isinstance(candidate, str) else None


def _result(value: Any) -> dict[str, Any] | None:
    record = _job_record(value)
    result = record.get("result") if isinstance(record, dict) else None
    return result if isinstance(result, dict) else None


def _wait_for_stage(
    service: Any,
    stage: str,
    production_id: str,
    run_id: str,
    payload: dict[str, Any],
    cancel_event: JobExecutionContext,
    *,
    narration_segment_start_ms: Sequence[int] | None = None,
    narration_request_key: str | None = None,
) -> dict[str, Any]:
    if (narration_segment_start_ms is None) != (narration_request_key is None):
        raise DetailedTestVideoError(
            "Narration alignment provenance is incomplete.",
            code="invalid_provenance",
        )
    method = getattr(service, _STAGE_METHODS[stage], None)
    jobs = getattr(service, "jobs", None)
    wait = getattr(jobs, "wait", None)
    cancel_and_wait = getattr(jobs, "cancel_and_wait", None)
    database = getattr(service, "database", None)
    get_attempt = getattr(database, "get_stage_attempt", None)
    if not all(callable(item) for item in (method, wait, cancel_and_wait, get_attempt)):
        raise DetailedTestVideoError(
            f"The detailed test video cannot execute {stage}.",
            code="detailed_test_video_unavailable",
        )

    queued_job_id: str | None = None
    queued_attempt_id: str | None = None

    def retire_child() -> None:
        if queued_job_id is not None:
            preserve = bool(
                cancel_event.is_set()
                and getattr(cancel_event, "preserve_provider_task", False)
            )
            cancel_and_wait(
                queued_job_id,
                timeout=None,
                preserve_provider_task=preserve,
            )

    try:
        cancel_event.raise_if_cancelled()
        if narration_segment_start_ms is not None:
            if stage != "narration":
                raise DetailedTestVideoError(
                    "Narration alignment was attached to the wrong stage.",
                    code="invalid_provenance",
                )
            capability = getattr(
                service, "_announcement_narration_timing_capability", None
            )
            if capability is None:
                raise DetailedTestVideoError(
                    "Announcement narration alignment is unavailable.",
                    code="detailed_test_video_unavailable",
                )
            queued = method(
                run_id,
                payload,
                _announcement_narration_timing_capability=capability,
                _announcement_segment_start_ms=list(narration_segment_start_ms),
                _announcement_detailed_test_video_key=narration_request_key,
            )
        else:
            queued = method(run_id, payload)
        queued_job_id = _job_id(queued)
        queued_attempt_id = _attempt_id(queued)
        validate_identifier(queued_job_id, label="job id")
        validate_identifier(queued_attempt_id, label="stage attempt id")
        deadline = time.monotonic() + _STAGE_TIMEOUT_SECONDS[stage]
        record: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            cancel_event.raise_if_cancelled()
            remaining = max(0.0, deadline - time.monotonic())
            completed = wait(queued_job_id, timeout=min(0.5, remaining))
            record = _job_record(completed)
            if record is not None and record.get("status") in _TERMINAL_STATUSES:
                break
        if record is None or record.get("status") not in _TERMINAL_STATUSES:
            raise DetailedTestVideoError(
                f"The detailed test video timed out during {stage}.",
                code="detailed_test_video_timeout",
            )
        if (
            _job_id(record) != queued_job_id
            or record.get("kind") != _STAGE_JOB_KINDS[stage]
            or record.get("production_id") != production_id
        ):
            raise DetailedTestVideoError(
                f"The detailed test video received mismatched {stage} provenance.",
                code="invalid_worker_result",
            )
        if record.get("status") != "succeeded":
            raise DetailedTestVideoError(
                f"The detailed test video stage failed: {stage}.",
                code="detailed_test_video_stage_failed",
            )
        result = _result(record)
        if (
            result is None
            or _attempt_id(record) != queued_attempt_id
            or not isinstance(result.get("cache_hit"), bool)
        ):
            raise DetailedTestVideoError(
                f"The detailed test video received an invalid {stage} result.",
                code="invalid_worker_result",
            )
        attempt = get_attempt(queued_attempt_id)
        job_payload = record.get("payload")
        if (
            not isinstance(attempt, dict)
            or attempt.get("id") != queued_attempt_id
            or attempt.get("job_id") != queued_job_id
            or attempt.get("run_id") != run_id
            or attempt.get("production_id") != production_id
            or attempt.get("stage") != stage
            or attempt.get("status") != "succeeded"
            or (
                stage == "timeline"
                and (
                    attempt.get("cache_key") != result.get("cache_key")
                    or job_payload.get("cache_key") != result.get("cache_key")
                )
            )
            or attempt.get("result")
            != {key: value for key, value in result.items() if key != "stage_attempt_id"}
            or not isinstance(job_payload, dict)
            or job_payload.get("production_id") != production_id
            or job_payload.get("run_id") != run_id
            or job_payload.get("stage") != stage
            or job_payload.get("stage_attempt_id") != queued_attempt_id
            or job_payload.get("execution_profile") != DETAILED_TEST_VIDEO_PROFILE
        ):
            raise DetailedTestVideoError(
                f"The detailed test video could not verify {stage} provenance.",
                code="invalid_worker_result",
            )
        return {
            "job_id": queued_job_id,
            "stage_attempt_id": queued_attempt_id,
            "cache_hit": result["cache_hit"],
            "result": result,
        }
    except (SecurityError, TypeError, ValueError) as exc:
        retire_child()
        raise DetailedTestVideoError(
            f"The detailed test video received an invalid {stage} job.",
            code="invalid_worker_result",
        ) from exc
    except JobCancelled:
        retire_child()
        raise
    except Exception:
        retire_child()
        raise


def _artifact(result: Mapping[str, Any], name: str, *, kind: str) -> dict[str, Any]:
    raw = result.get("artifacts")
    matches = (
        [item for item in raw if isinstance(item, dict) and item.get("name") == name]
        if isinstance(raw, list)
        else []
    )
    if len(matches) != 1:
        raise DetailedTestVideoError(
            "A required detailed test video artifact is unavailable.",
            code="invalid_worker_result",
        )
    item = matches[0]
    artifact_id = item.get("id", item.get("artifact_id"))
    relative = item.get("rel_path", item.get("path"))
    media_type = item.get("media_type", item.get("mime"))
    bytes_value = item.get("bytes")
    digest = item.get("sha256")
    try:
        validate_identifier(artifact_id, label="artifact id")
    except (SecurityError, TypeError, ValueError):
        raise DetailedTestVideoError(
            "A detailed test video artifact identity is invalid.",
            code="invalid_worker_result",
        ) from None
    if (
        item.get("kind") != kind
        or not isinstance(media_type, str)
        or not media_type
        or isinstance(bytes_value, bool)
        or not isinstance(bytes_value, int)
        or not 0 < bytes_value <= _MAX_ARTIFACT_BYTES
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest.upper()) is None
        or not isinstance(relative, str)
        or not relative
        or len(relative) > 1024
        or "\x00" in relative
    ):
        raise DetailedTestVideoError(
            "A detailed test video artifact is invalid.",
            code="invalid_worker_result",
        )
    relative = relative.replace("\\", "/")
    if (
        PurePosixPath(relative).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise DetailedTestVideoError(
            "A detailed test video artifact path is invalid.",
            code="invalid_worker_result",
        )
    return {
        "id": artifact_id,
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "rel_path": relative,
        "bytes": bytes_value,
        "sha256": digest.upper(),
    }


def _document_artifacts(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = {"technical-qc.json", "ffprobe.json", "manifest.json"}
    raw = result.get("artifacts")
    if not isinstance(raw, list) or len(raw) != len(expected):
        raise DetailedTestVideoError(
            "The detailed test video QC artifacts are invalid.",
            code="invalid_worker_result",
        )
    documents = [_artifact({"artifacts": raw}, name, kind="document") for name in sorted(expected)]
    if {item["name"] for item in documents} != expected:
        raise DetailedTestVideoError(
            "The detailed test video QC artifacts are invalid.",
            code="invalid_worker_result",
        )
    return documents


def _stage_view(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": outcome["result"].get("stage", ""),
        "status": "succeeded",
        "job_id": outcome["job_id"],
        "stage_attempt_id": outcome["stage_attempt_id"],
        "cache_hit": outcome["cache_hit"],
    }


def detailed_test_video_public_result(
    raw: Any,
    *,
    production_id: str,
    run_id: str,
    revision_id: str,
    request_key: str,
    payload: dict[str, Any],
    narration_segment_start_ms: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Whitelist the completed top result before it reaches jobs/events."""

    normalized = validate_detailed_test_video_payload(payload)
    expected_keys = {
        "schema_version",
        "production_id",
        "run_id",
        "revision_id",
        "request_key",
        "execution_profile",
        "duration_ms",
        "technical_verdict",
        "variant",
        "include_captioned",
        "caption_style_preset",
        "caption_preflight_policy",
        "audio_mix_preset",
        "children",
        "timeline",
        "master",
        "qc",
        "artifacts",
    }
    alignment: dict[str, Any] | None = None
    if narration_segment_start_ms is not None:
        try:
            timing = narration_timing_identity(
                narration_segment_start_ms,
                segment_count=len(normalized["segments"]),
            )
        except LocalNarrationValidationError as exc:
            raise DetailedTestVideoError(
                "The detailed test video narration alignment is invalid.",
                code="invalid_provenance",
            ) from exc
        alignment = {
            "policy": ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY,
            "segment_start_ms": timing["segment_start_ms"],
        }
        expected_keys.update(
            {"narration_alignment_policy", "narration_segment_start_ms"}
        )
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise DetailedTestVideoError(
            "The detailed test video returned an invalid result.",
            code="invalid_worker_result",
        )
    if (
        raw.get("schema_version") != DETAILED_TEST_VIDEO_SCHEMA_VERSION
        or raw.get("production_id") != production_id
        or raw.get("run_id") != run_id
        or raw.get("revision_id") != revision_id
        or raw.get("request_key") != request_key
        or raw.get("execution_profile") != DETAILED_TEST_VIDEO_PROFILE
        or raw.get("technical_verdict") != "pass"
        or raw.get("variant") != normalized["variant"]
        or raw.get("include_captioned") != normalized["include_captioned"]
        or raw.get("caption_style_preset") != normalized["caption_style_preset"]
        or raw.get("caption_preflight_policy")
        != _caption_preflight_policy(normalized)
        or raw.get("audio_mix_preset") != normalized["audio_mix_preset"]
        or (
            alignment is not None
            and (
                raw.get("narration_alignment_policy") != alignment["policy"]
                or raw.get("narration_segment_start_ms")
                != alignment["segment_start_ms"]
            )
        )
        or isinstance(raw.get("duration_ms"), bool)
        or not isinstance(raw.get("duration_ms"), int)
        or not 50 <= raw["duration_ms"] <= 60_000
    ):
        raise DetailedTestVideoError(
            "The detailed test video returned mismatched provenance.",
            code="invalid_worker_result",
        )
    children = raw.get("children")
    if not isinstance(children, dict) or set(children) != set(DETAILED_TEST_VIDEO_STAGES):
        raise DetailedTestVideoError(
            "The detailed test video returned invalid child lineage.",
            code="invalid_worker_result",
        )
    clean_children: dict[str, dict[str, Any]] = {}
    for stage in DETAILED_TEST_VIDEO_STAGES:
        child = children.get(stage)
        if not isinstance(child, dict) or set(child) != {
            "stage",
            "status",
            "job_id",
            "stage_attempt_id",
            "cache_hit",
        }:
            raise DetailedTestVideoError(
                "The detailed test video returned invalid child lineage.",
                code="invalid_worker_result",
            )
        if child.get("stage") != stage or child.get("status") != "succeeded":
            raise DetailedTestVideoError(
                "The detailed test video returned invalid child lineage.",
                code="invalid_worker_result",
            )
        try:
            validate_identifier(child.get("job_id"), label="child job id")
            validate_identifier(
                child.get("stage_attempt_id"), label="child stage attempt id"
            )
        except (SecurityError, TypeError, ValueError):
            raise DetailedTestVideoError(
                "The detailed test video returned invalid child lineage.",
                code="invalid_worker_result",
            ) from None
        if not isinstance(child.get("cache_hit"), bool):
            raise DetailedTestVideoError(
                "The detailed test video returned invalid child lineage.",
                code="invalid_worker_result",
            )
        clean_children[stage] = dict(child)

    timeline = _artifact(
        {"artifacts": [raw.get("timeline")]}, "remotion-preview.mp4", kind="video"
    )
    master_name = (
        "master-captioned.mp4"
        if normalized["variant"] == "captioned"
        else "master-clean.mp4"
    )
    master = _artifact(
        {"artifacts": [raw.get("master")]}, master_name, kind="video"
    )
    qc = raw.get("qc")
    if not isinstance(qc, dict) or set(qc) != {"verdict", "report_artifacts"}:
        raise DetailedTestVideoError(
            "The detailed test video returned invalid QC metadata.",
            code="invalid_worker_result",
        )
    reports = _document_artifacts({"artifacts": qc.get("report_artifacts")})
    if qc.get("verdict") != "pass" or raw.get("artifacts") != [master, *reports]:
        raise DetailedTestVideoError(
            "The detailed test video returned invalid artifact lineage.",
            code="invalid_worker_result",
        )
    result = {
        "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "request_key": request_key,
        "execution_profile": DETAILED_TEST_VIDEO_PROFILE,
        "duration_ms": raw["duration_ms"],
        "technical_verdict": "pass",
        "variant": normalized["variant"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "caption_preflight_policy": _caption_preflight_policy(normalized),
        "audio_mix_preset": normalized["audio_mix_preset"],
        "children": clean_children,
        "timeline": timeline,
        "master": master,
        "qc": {"verdict": "pass", "report_artifacts": reports},
        "artifacts": [master, *reports],
    }
    if alignment is not None:
        result["narration_alignment_policy"] = alignment["policy"]
        result["narration_segment_start_ms"] = alignment[
            "segment_start_ms"
        ]
    return result


def run_detailed_test_video(
    service: Any,
    *,
    production_id: str,
    run_id: str,
    revision_id: str,
    payload: dict[str, Any],
    source_clips: Sequence[Mapping[str, Any]],
    expected_remotion_cache_key: str,
    expected_request_key: str,
    expected_duration_ms: int,
    cancel_event: JobExecutionContext,
    narration_segment_start_ms: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Execute narration -> Remotion -> assembly -> QC on one immutable run."""

    try:
        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        validate_identifier(revision_id, label="revision id")
    except (SecurityError, TypeError, ValueError):
        raise DetailedTestVideoError(
            "The detailed test video provenance is invalid.",
            code="invalid_provenance",
        ) from None
    normalized = validate_detailed_test_video_payload(payload)
    request_key = detailed_test_video_key(
        normalized,
        source_clips=source_clips,
        remotion_cache_key=expected_remotion_cache_key,
        narration_segment_start_ms=narration_segment_start_ms,
    )
    if request_key != expected_request_key:
        raise DetailedTestVideoError(
            "The detailed test video request changed before execution.",
            code="cache_key_mismatch",
        )
    if (
        isinstance(expected_duration_ms, bool)
        or not isinstance(expected_duration_ms, int)
        or expected_duration_ms < 50
        or expected_duration_ms > 60_000
    ):
        raise DetailedTestVideoError(
            "The detailed test video duration is invalid.",
            code="invalid_provenance",
        )
    database = getattr(service, "database", None)
    get_run = getattr(database, "get_run", None)
    get_claim = getattr(database, "get_detailed_test_video_claim", None)
    if not callable(get_run) or not callable(get_claim):
        raise DetailedTestVideoError(
            "The detailed test video provenance store is unavailable.",
            code="detailed_test_video_unavailable",
        )
    run = get_run(run_id)
    claim = get_claim(production_id, request_key)
    estimated_cost = run.get("estimated_cost") if isinstance(run, dict) else None
    if (
        not isinstance(run, dict)
        or run.get("production_id") != production_id
        or run.get("revision_id") != revision_id
        or run.get("execution_profile") != DETAILED_TEST_VIDEO_PROFILE
        or set(run.get("requested_stages", []))
        != {"narration", "captions", "timeline", "assembly", "qc"}
        or not isinstance(estimated_cost, dict)
        or estimated_cost.get("amount") != "0.00"
        or not isinstance(claim, dict)
        or claim.get("run_id") != run_id
        or claim.get("revision_id") != revision_id
        or claim.get("request_key") != request_key
    ):
        raise DetailedTestVideoError(
            "The detailed test video run provenance is invalid.",
            code="invalid_provenance",
        )

    update_progress = getattr(database, "update_job_progress", None)

    def report_progress(progress: int, phase: str) -> None:
        cancel_event.raise_if_cancelled()
        if callable(update_progress):
            try:
                update_progress(cancel_event.job_id, progress, phase)
            except Exception:
                # Progress is advisory. Child/job/attempt terminal truth remains
                # authoritative if telemetry storage is briefly unavailable.
                pass

    report_progress(1, "narration")
    narration = _wait_for_stage(
        service,
        "narration",
        production_id,
        run_id,
        {
            "segments": normalized["segments"],
            "voice": normalized["voice"],
            "rate": normalized["rate"],
            "pronunciations": normalized["pronunciations"],
        },
        cancel_event,
        narration_segment_start_ms=narration_segment_start_ms,
        narration_request_key=(
            expected_request_key
            if narration_segment_start_ms is not None
            else None
        ),
    )
    report_progress(24, "narration")
    narration_duration = narration["result"].get("duration_ms")
    if (
        isinstance(narration_duration, bool)
        or not isinstance(narration_duration, int)
        or narration_duration <= 0
        or narration_duration > expected_duration_ms + 250
    ):
        raise DetailedTestVideoError(
            "The narration is longer than the detailed timeline.",
            code="narration_longer_than_source",
        )

    report_progress(25, "timeline")
    timeline = _wait_for_stage(
        service,
        "timeline",
        production_id,
        run_id,
        {"schema_version": normalized["schema_version"], "clips": normalized["clips"]},
        cancel_event,
    )
    report_progress(49, "timeline")
    if (
        timeline["result"].get("duration_ms") != expected_duration_ms
        or timeline["result"].get("cache_key") != expected_remotion_cache_key
    ):
        raise DetailedTestVideoError(
            "The detailed timeline returned mismatched timing or provenance.",
            code="invalid_worker_result",
        )
    timeline_video = _artifact(
        timeline["result"], "remotion-preview.mp4", kind="video"
    )

    assembly_body = {
        "video_artifact_id": timeline_video["id"],
        "narration_attempt_id": narration["stage_attempt_id"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "audio_mix_preset": normalized["audio_mix_preset"],
    }
    try:
        validate_local_assembly_payload(assembly_body)
    except (LocalAssemblyValidationError, TypeError, ValueError):
        raise DetailedTestVideoError(
            "The detailed test video assembly request could not be prepared.",
            code="invalid_worker_result",
        ) from None
    report_progress(50, "assembly")
    assembly = _wait_for_stage(
        service, "assembly", production_id, run_id, assembly_body, cancel_event
    )
    report_progress(74, "assembly")
    if assembly["result"].get("duration_ms") != expected_duration_ms:
        raise DetailedTestVideoError(
            "The detailed test video assembly returned mismatched timing.",
            code="invalid_worker_result",
        )
    master_name = (
        "master-captioned.mp4"
        if normalized["variant"] == "captioned"
        else "master-clean.mp4"
    )
    master = _artifact(assembly["result"], master_name, kind="video")

    try:
        qc_body = validate_local_qc_payload(
            {
                "assembly_attempt_id": assembly["stage_attempt_id"],
                "variant": normalized["variant"],
            }
        )
    except (LocalQcValidationError, TypeError, ValueError):
        raise DetailedTestVideoError(
            "The detailed test video QC request could not be prepared.",
            code="invalid_worker_result",
        ) from None
    report_progress(75, "qc")
    qc = _wait_for_stage(
        service, "qc", production_id, run_id, qc_body, cancel_event
    )
    report_progress(95, "qc")
    verdict = qc["result"].get(
        "technical_verdict", qc["result"].get("verdict")
    )
    if (
        qc["result"].get("analysis_status") != "succeeded"
        or verdict != "pass"
        or qc["result"].get("duration_ms") != expected_duration_ms
        or qc["result"].get("expected_duration_ms") != expected_duration_ms
    ):
        raise DetailedTestVideoError(
            "Local technical QC did not pass.", code="technical_qc_failed"
        )
    reports = _document_artifacts(qc["result"])

    report_progress(99, "finalizing")
    cancel_event.raise_if_cancelled()
    children = {
        stage: {
            **_stage_view(outcome),
            "stage": stage,
        }
        for stage, outcome in (
            ("narration", narration),
            ("timeline", timeline),
            ("assembly", assembly),
            ("qc", qc),
        )
    }
    result = {
        "schema_version": DETAILED_TEST_VIDEO_SCHEMA_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "request_key": request_key,
        "execution_profile": DETAILED_TEST_VIDEO_PROFILE,
        "duration_ms": expected_duration_ms,
        "technical_verdict": "pass",
        "variant": normalized["variant"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "caption_preflight_policy": _caption_preflight_policy(normalized),
        "audio_mix_preset": normalized["audio_mix_preset"],
        "children": children,
        "timeline": timeline_video,
        "master": master,
        "qc": {"verdict": "pass", "report_artifacts": reports},
        "artifacts": [master, *reports],
    }
    if narration_segment_start_ms is not None:
        timing = narration_timing_identity(
            narration_segment_start_ms,
            segment_count=len(normalized["segments"]),
        )
        result["narration_alignment_policy"] = (
            ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY
        )
        result["narration_segment_start_ms"] = timing["segment_start_ms"]
    return result


__all__ = [
    "DETAILED_TEST_VIDEO_IMPLEMENTATION_VERSION",
    "DETAILED_TEST_VIDEO_JOB_KIND",
    "DETAILED_TEST_VIDEO_PROFILE",
    "DETAILED_TEST_VIDEO_SCHEMA_VERSION",
    "DETAILED_TEST_VIDEO_STAGES",
    "ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY",
    "SHORTS_JA_CAPTION_PREFLIGHT_POLICY",
    "DetailedTestVideoError",
    "DetailedTestVideoValidationError",
    "detailed_test_video_audit_payload",
    "detailed_test_video_key",
    "detailed_test_video_public_result",
    "run_detailed_test_video",
    "safe_detailed_test_video_error",
    "validate_detailed_test_video_payload",
]
