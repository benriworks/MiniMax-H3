from __future__ import annotations

"""Bounded local-only orchestration for a complete Studio short-video run.

The pipeline is a control-plane worker.  It never calls ComfyUI, SAPI, or
FFmpeg directly; each stage is queued through :class:`StudioService`, so the
existing stage-attempt, cache, artifact, cancellation, and atomic-completion
contracts remain authoritative.
"""

import hashlib
import re
import time
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from .assembly_execution import (
    CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
    DEFAULT_CAPTION_STYLE_PRESET,
    LocalAssemblyValidationError,
    normalize_caption_style_preset,
    validate_local_assembly_payload,
)
from .comfyui_execution import (
    COMFYUI_WORKFLOW_PRESET,
    ComfyUIValidationError,
    validate_comfyui_payload,
)
from .execution import LocalNarrationValidationError, audit_payload, validate_local_narration_payload
from .jobs import JobCancelled, JobExecutionContext
from .qc_execution import LocalQcValidationError, validate_local_qc_payload
from .security import SecurityError, canonical_json, validate_identifier
from .timeline_execution import TimelineValidationError, validate_local_timeline_payload


LOCAL_PIPELINE_PROFILE = "local_pipeline"
LOCAL_PIPELINE_JOB_KIND = "local_pipeline"
LOCAL_PIPELINE_IMPLEMENTATION_VERSION = "local-pipeline-v1"
LOCAL_PIPELINE_STAGES = (
    "video_generation",
    "narration",
    "timeline",
    "assembly",
    "qc",
)

_PUBLIC_KEYS = {
    "workflow_preset",
    "prompt",
    "seed",
    "segments",
    "voice",
    "rate",
    "pronunciations",
    "include_captioned",
    "caption_style_preset",
    "variant",
}
_REQUIRED_KEYS = {
    "workflow_preset",
    "prompt",
    "seed",
    "segments",
    "rate",
    "include_captioned",
    "caption_style_preset",
    "variant",
}
_STAGE_TIMEOUT_SECONDS = {
    "video_generation": 6 * 60 * 60.0 + 5 * 60.0,
    "narration": 30 * 60.0,
    "timeline": 30 * 60.0,
    "assembly": 30 * 60.0,
    "qc": 30 * 60.0,
}
_TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_DURATION_MS = 30 * 60 * 1000


class LocalPipelineValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_local_pipeline_request"):
        super().__init__(message)
        self.code = code


class LocalPipelineError(RuntimeError):
    """A bounded failure that is safe at the top-level job boundary."""

    def __init__(self, message: str, *, code: str = "local_pipeline_failed"):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


def _validation_error() -> LocalPipelineValidationError:
    return LocalPipelineValidationError("The local pipeline request is invalid.")


def validate_local_pipeline_payload(body: Any) -> dict[str, Any]:
    """Validate the exact browser-facing, local-only pipeline request."""

    if not isinstance(body, dict) or any(not isinstance(key, str) for key in body):
        raise _validation_error()
    keys = set(body)
    if keys - _PUBLIC_KEYS or not _REQUIRED_KEYS.issubset(keys):
        raise _validation_error()

    try:
        video = validate_comfyui_payload(
            {
                "workflow_preset": body.get("workflow_preset"),
                "prompt": body.get("prompt"),
                "seed": body.get("seed"),
            }
        )
        narration_body = {
            "segments": body.get("segments"),
            "rate": body.get("rate"),
        }
        if "voice" in body:
            narration_body["voice"] = body.get("voice")
        if "pronunciations" in body:
            narration_body["pronunciations"] = body.get("pronunciations")
        narration = validate_local_narration_payload(narration_body)
        caption_style = normalize_caption_style_preset(body.get("caption_style_preset"))
    except (
        ComfyUIValidationError,
        LocalNarrationValidationError,
        LocalAssemblyValidationError,
        TypeError,
        ValueError,
    ):
        raise _validation_error() from None

    include_captioned = body.get("include_captioned")
    variant = body.get("variant")
    if not isinstance(include_captioned, bool):
        raise _validation_error()
    if variant not in {"clean", "captioned"}:
        raise _validation_error()
    if variant == "captioned" and not include_captioned:
        raise _validation_error()
    if (
        not include_captioned
        and caption_style["preset"] != DEFAULT_CAPTION_STYLE_PRESET
    ):
        raise _validation_error()

    return {
        **video,
        "segments": narration["segments"],
        "voice": narration["voice"],
        "rate": narration["rate"],
        "pronunciations": narration["pronunciations"],
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "variant": variant,
    }


def local_pipeline_key(payload: dict[str, Any]) -> str:
    normalized = validate_local_pipeline_payload(payload)
    identity = {
        "schema_version": 1,
        "implementation_version": LOCAL_PIPELINE_IMPLEMENTATION_VERSION,
        "payload": normalized,
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def local_pipeline_audit_payload(payload: dict[str, Any], *, pipeline_key: str) -> dict[str, Any]:
    normalized = validate_local_pipeline_payload(payload)
    if not isinstance(pipeline_key, str) or _SHA256_RE.fullmatch(pipeline_key) is None:
        raise LocalPipelineValidationError("pipeline key is invalid")
    narration = audit_payload(
        {
            "segments": normalized["segments"],
            "voice": normalized["voice"],
            "rate": normalized["rate"],
            "pronunciations": normalized["pronunciations"],
        }
    )
    prompt = normalized["prompt"]
    return {
        "pipeline_key": pipeline_key.upper(),
        "pipeline_version": LOCAL_PIPELINE_IMPLEMENTATION_VERSION,
        "execution_profile": LOCAL_PIPELINE_PROFILE,
        "workflow_preset": normalized["workflow_preset"],
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper(),
        "prompt_chars": len(prompt),
        "seed_decimal": str(normalized["seed"]),
        "segment_count": narration["segment_count"],
        "text_chars": narration["text_chars"],
        "segment_text_sha256": [value.upper() for value in narration["segment_text_sha256"]],
        "voice": narration["voice"],
        "rate": narration["rate"],
        "pronunciation_count": narration["pronunciation_count"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
        "variant": normalized["variant"],
    }


def safe_pipeline_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, LocalPipelineValidationError):
        return exc.code, "The local pipeline request is invalid."
    if isinstance(exc, LocalPipelineError):
        return exc.error_code, exc.public_message
    if isinstance(exc, JobCancelled):
        return "process_interrupted", "The Studio process stopped before the pipeline completed."
    return "local_pipeline_failed", "The local pipeline failed."


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
    if record is None:
        return None
    result = record.get("result")
    return result if isinstance(result, dict) else None


def _wait_for_stage(
    service: Any,
    stage: str,
    run_id: str,
    payload: dict[str, Any],
    pipeline_key: str,
    lineage: dict[str, Any],
    cancel_event: JobExecutionContext,
) -> dict[str, Any]:
    method = getattr(service, "_execute_local_pipeline_stage", None)
    jobs = getattr(service, "jobs", None)
    wait = getattr(jobs, "wait", None)
    cancel_and_wait = getattr(jobs, "cancel_and_wait", None)
    if not callable(method) or not callable(wait) or not callable(cancel_and_wait):
        raise LocalPipelineError(
            f"The local pipeline cannot execute {stage}.",
            code="local_pipeline_unavailable",
        )
    queued_job_id: str | None = None
    queued_attempt_id: str | None = None
    try:
        cancel_event.raise_if_cancelled()
        queued = method(
            run_id,
            stage,
            payload,
            pipeline_key=pipeline_key,
            lineage=lineage,
        )
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
            raise LocalPipelineError(
                f"The local pipeline timed out during {stage}.",
                code="local_pipeline_timeout",
            )
        if _job_id(record) != queued_job_id:
            raise LocalPipelineError(
                f"The local pipeline received mismatched {stage} provenance.",
                code="invalid_worker_result",
            )
        if record.get("status") != "succeeded":
            raise LocalPipelineError(
                f"The local pipeline stage failed: {stage}.",
                code="local_pipeline_stage_failed",
            )
        result = _result(record)
        if (
            result is None
            or _attempt_id(record) != queued_attempt_id
            or not isinstance(result.get("cache_hit"), bool)
        ):
            raise LocalPipelineError(
                f"The local pipeline received an invalid {stage} result.",
                code="invalid_worker_result",
            )
        database = getattr(service, "database", None)
        get_attempt = getattr(database, "get_stage_attempt", None)
        if not callable(get_attempt):
            raise LocalPipelineError(
                "The local pipeline provenance store is unavailable.",
                code="local_pipeline_unavailable",
            )
        attempt = get_attempt(queued_attempt_id)
        if (
            not isinstance(attempt, dict)
            or attempt.get("id") != queued_attempt_id
            or attempt.get("job_id") != queued_job_id
            or attempt.get("run_id") != run_id
            or attempt.get("stage") != stage
            or attempt.get("status") != "succeeded"
            or attempt.get("result") != {
                key: value for key, value in result.items() if key != "stage_attempt_id"
            }
        ):
            raise LocalPipelineError(
                f"The local pipeline could not verify {stage} provenance.",
                code="invalid_worker_result",
            )
        return {
            "job_id": queued_job_id,
            "stage_attempt_id": queued_attempt_id,
            "cache_hit": result["cache_hit"],
            "result": result,
        }
    except (SecurityError, TypeError, ValueError) as exc:
        if queued_job_id is not None:
            cancel_and_wait(queued_job_id, timeout=None)
        raise LocalPipelineError(
            f"The local pipeline received an invalid {stage} job.",
            code="invalid_worker_result",
        ) from exc
    except JobCancelled:
        if queued_job_id is not None:
            cancel_and_wait(queued_job_id, timeout=None)
        raise
    except Exception:
        # A top-level terminal state must never race a still-running child.
        # The manager waits for the child's worker slot, not merely its DB row.
        if queued_job_id is not None:
            cancel_and_wait(queued_job_id, timeout=None)
        raise


def _artifact(result: dict[str, Any], name: str, *, kind: str) -> dict[str, Any]:
    raw = result.get("artifacts")
    matches = (
        [item for item in raw if isinstance(item, dict) and item.get("name") == name]
        if isinstance(raw, list)
        else []
    )
    if len(matches) != 1:
        raise LocalPipelineError("A required pipeline artifact is unavailable.", code="invalid_worker_result")
    item = matches[0]
    artifact_id = item.get("id", item.get("artifact_id"))
    relative = item.get("rel_path", item.get("path"))
    media_type = item.get("media_type", item.get("mime"))
    bytes_value = item.get("bytes")
    digest = item.get("sha256")
    try:
        validate_identifier(artifact_id, label="artifact id")
    except (SecurityError, TypeError, ValueError):
        raise LocalPipelineError("A pipeline artifact identity is invalid.", code="invalid_worker_result") from None
    if (
        item.get("kind") != kind
        or not isinstance(media_type, str)
        or not media_type
        or isinstance(bytes_value, bool)
        or not isinstance(bytes_value, int)
        or not 0 < bytes_value <= _MAX_ARTIFACT_BYTES
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
        or not isinstance(relative, str)
        or not relative
        or len(relative) > 1024
        or "\x00" in relative
    ):
        raise LocalPipelineError("A pipeline artifact is invalid.", code="invalid_worker_result")
    relative = relative.replace("\\", "/")
    if (
        PurePosixPath(relative).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise LocalPipelineError("A pipeline artifact path is invalid.", code="invalid_worker_result")
    return {
        "id": artifact_id,
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "rel_path": relative,
        "bytes": bytes_value,
        "sha256": digest.upper(),
    }


def _document_artifacts(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = result.get("artifacts")
    expected = {"technical-qc.json", "ffprobe.json", "manifest.json"}
    if not isinstance(raw, list) or len(raw) != len(expected):
        raise LocalPipelineError("The pipeline QC artifacts are invalid.", code="invalid_worker_result")
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or item.get("kind") != "document":
            raise LocalPipelineError("The pipeline QC artifacts are invalid.", code="invalid_worker_result")
        name = item.get("name")
        if (
            not isinstance(name, str)
            or name not in expected
            or name in seen
            or item.get("media_type", item.get("mime")) != "application/json"
        ):
            raise LocalPipelineError("The pipeline QC artifacts are invalid.", code="invalid_worker_result")
        seen.add(name)
        documents.append(_artifact({"artifacts": [item]}, name, kind="document"))
    if seen != expected:
        raise LocalPipelineError("The pipeline QC artifacts are invalid.", code="invalid_worker_result")
    return documents


def _stage_view(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": outcome["job_id"],
        "stage_attempt_id": outcome["stage_attempt_id"],
        "cache_hit": outcome["cache_hit"],
    }


def run_local_pipeline(
    service: Any,
    *,
    production_id: str,
    run_id: str,
    revision_id: str,
    payload: dict[str, Any],
    expected_pipeline_key: str,
    cancel_event: JobExecutionContext,
) -> dict[str, Any]:
    """Execute five existing Studio stages in order on one immutable run."""

    try:
        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        validate_identifier(revision_id, label="revision id")
    except (SecurityError, TypeError, ValueError):
        raise LocalPipelineError("The local pipeline provenance is invalid.", code="invalid_provenance") from None
    normalized = validate_local_pipeline_payload(payload)
    pipeline_key = local_pipeline_key(normalized)
    if pipeline_key != expected_pipeline_key:
        raise LocalPipelineError("The local pipeline request changed before execution.", code="cache_key_mismatch")
    database = getattr(service, "database", None)
    get_run = getattr(database, "get_run", None)
    if not callable(get_run):
        raise LocalPipelineError("The local pipeline provenance store is unavailable.", code="local_pipeline_unavailable")
    run = get_run(run_id)
    estimated_cost = run.get("estimated_cost") if isinstance(run, dict) else None
    if (
        not isinstance(run, dict)
        or run.get("id") != run_id
        or run.get("production_id") != production_id
        or run.get("revision_id") != revision_id
        or run.get("execution_profile") != LOCAL_PIPELINE_PROFILE
        or run.get("pipeline_key") != pipeline_key
        or set(run.get("requested_stages", []))
        != {"narration", "captions", "video_generation", "timeline", "assembly", "qc"}
        or not isinstance(estimated_cost, dict)
        or estimated_cost.get("amount") != "0.00"
    ):
        raise LocalPipelineError("The local pipeline run provenance is invalid.", code="invalid_provenance")

    video = _wait_for_stage(
        service,
        "video_generation",
        run_id,
        {
            "workflow_preset": normalized["workflow_preset"],
            "prompt": normalized["prompt"],
            "seed": normalized["seed"],
        },
        pipeline_key,
        {},
        cancel_event,
    )
    generated = _artifact(video["result"], "generated-video.mp4", kind="video")
    duration_ms = video["result"].get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms < 50
        or duration_ms > _MAX_DURATION_MS
    ):
        raise LocalPipelineError("The generated video duration is invalid.", code="invalid_worker_result")

    narration = _wait_for_stage(
        service,
        "narration",
        run_id,
        {
            "segments": normalized["segments"],
            "voice": normalized["voice"],
            "rate": normalized["rate"],
            "pronunciations": normalized["pronunciations"],
        },
        pipeline_key,
        {"video_generation_attempt_id": video["stage_attempt_id"]},
        cancel_event,
    )
    narration_duration = narration["result"].get("duration_ms")
    if (
        isinstance(narration_duration, bool)
        or not isinstance(narration_duration, int)
        or narration_duration <= 0
        or narration_duration > _MAX_DURATION_MS
    ):
        raise LocalPipelineError("The narration duration is invalid.", code="invalid_worker_result")
    if narration_duration > duration_ms + 250:
        raise LocalPipelineError(
            "The narration is longer than the generated video.",
            code="narration_longer_than_source",
        )

    try:
        timeline_payload = validate_local_timeline_payload(
            {
                "clips": [
                    {
                        "video_artifact_id": generated["id"],
                        "start_ms": 0,
                        "end_ms": duration_ms,
                    }
                ]
            }
        )
    except (TimelineValidationError, TypeError, ValueError):
        raise LocalPipelineError("The pipeline timeline could not be prepared.", code="invalid_worker_result") from None
    timeline = _wait_for_stage(
        service,
        "timeline",
        run_id,
        timeline_payload,
        pipeline_key,
        {
            "video_generation_attempt_id": video["stage_attempt_id"],
            "narration_attempt_id": narration["stage_attempt_id"],
            "video_artifact": generated,
        },
        cancel_event,
    )
    timeline_video = _artifact(timeline["result"], "timeline-preview.mp4", kind="video")

    assembly_payload = {
        "video_artifact_id": timeline_video["id"],
        "narration_attempt_id": narration["stage_attempt_id"],
        "include_captioned": normalized["include_captioned"],
        "caption_style_preset": normalized["caption_style_preset"],
    }
    try:
        # Validate here, but pass the exact public body to the service.  The
        # normalized contract also contains an internal ``caption_style``
        # expansion that is deliberately rejected at the HTTP/service edge.
        validate_local_assembly_payload(assembly_payload)
    except (LocalAssemblyValidationError, TypeError, ValueError):
        raise LocalPipelineError("The pipeline assembly could not be prepared.", code="invalid_worker_result") from None
    assembly = _wait_for_stage(
        service,
        "assembly",
        run_id,
        assembly_payload,
        pipeline_key,
        {
            "narration_attempt_id": narration["stage_attempt_id"],
            "timeline_attempt_id": timeline["stage_attempt_id"],
            "timeline_artifact": timeline_video,
        },
        cancel_event,
    )
    master_name = (
        "master-captioned.mp4" if normalized["variant"] == "captioned" else "master-clean.mp4"
    )
    master = _artifact(assembly["result"], master_name, kind="video")

    try:
        qc_payload = validate_local_qc_payload(
            {
                "assembly_attempt_id": assembly["stage_attempt_id"],
                "variant": normalized["variant"],
            }
        )
    except (LocalQcValidationError, TypeError, ValueError):
        raise LocalPipelineError("The pipeline QC could not be prepared.", code="invalid_worker_result") from None
    qc = _wait_for_stage(
        service,
        "qc",
        run_id,
        qc_payload,
        pipeline_key,
        {
            "assembly_attempt_id": assembly["stage_attempt_id"],
            "master_artifact": master,
        },
        cancel_event,
    )
    if qc["result"].get("analysis_status") != "succeeded":
        raise LocalPipelineError("The pipeline QC result is incomplete.", code="invalid_worker_result")
    verdict = qc["result"].get("technical_verdict", qc["result"].get("verdict"))
    if verdict != "pass":
        raise LocalPipelineError("Local technical QC did not pass.", code="technical_qc_failed")
    reports = _document_artifacts(qc["result"])

    cancel_event.raise_if_cancelled()
    return {
        "production_id": production_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "pipeline_key": pipeline_key,
        "execution_profile": LOCAL_PIPELINE_PROFILE,
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_sha256": hashlib.sha256(normalized["prompt"].encode("utf-8")).hexdigest().upper(),
        "seed_decimal": str(normalized["seed"]),
        "duration_ms": duration_ms,
        "technical_verdict": "pass",
        "variant": normalized["variant"],
        "caption_style_preset": normalized["caption_style_preset"],
        "jobs": {
            "video_generation": _stage_view(video),
            "narration": _stage_view(narration),
            "timeline": _stage_view(timeline),
            "assembly": _stage_view(assembly),
            "qc": _stage_view(qc),
        },
        "video": generated,
        "timeline": timeline_video,
        "master": master,
        "qc": {"verdict": "pass", "report_artifacts": reports},
        "artifacts": [master, *reports],
    }


__all__ = [
    "CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1",
    "LOCAL_PIPELINE_IMPLEMENTATION_VERSION",
    "LOCAL_PIPELINE_JOB_KIND",
    "LOCAL_PIPELINE_PROFILE",
    "LOCAL_PIPELINE_STAGES",
    "LocalPipelineError",
    "LocalPipelineValidationError",
    "local_pipeline_audit_payload",
    "local_pipeline_key",
    "run_local_pipeline",
    "safe_pipeline_error",
    "validate_local_pipeline_payload",
]
