from __future__ import annotations

"""One-command, local-only Studio test-video orchestration.

The orchestration layer intentionally contains no media implementation.  It
only validates the source boundary, creates an immutable zero-cost
``local_sapi`` run, and drives the four existing service execution contracts
in dependency order.  This makes the flow useful in a CLI and straightforward
to test with a service double without starting SAPI, FFmpeg, or a Studio
server.
"""

import hashlib
import inspect
import math
import re
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .assembly_execution import LocalAssemblyValidationError, validate_local_assembly_payload
from .execution import LocalNarrationValidationError, validate_local_narration_payload
from .qc_execution import LocalQcValidationError, validate_local_qc_payload
from .security import (
    SecurityError,
    relative_workspace_path,
    sensitive_artifact_path,
    validate_identifier,
    workspace_path,
)
from .timeline_execution import TimelineValidationError, validate_local_timeline_payload


_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-fA-F]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_TIMELINE_DURATION_MS = 30 * 60 * 1000
_MIN_TIMELINE_DURATION_MS = 50
_DEFAULT_TIMEOUT_SECONDS = 300.0
_MAX_RESULT_ARTIFACTS = 16
_MAX_RESULT_STRING = 512

_STAGE_METHODS = {
    "narration": "execute_local_narration",
    "timeline": "execute_local_timeline",
    "assembly": "execute_local_assembly",
    "qc": "execute_local_qc",
}


class TestVideoError(RuntimeError):
    """A bounded public error for the one-command test-video flow."""

    def __init__(self, error_code: str, public_message: str):
        if not isinstance(error_code, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]{0,127}", error_code
        ):
            error_code = "test_video_failed"
        if not isinstance(public_message, str) or not public_message:
            public_message = "The test video could not be rendered."
        # The orchestrator only supplies fixed messages.  Keep this class
        # bounded as well so callers cannot accidentally turn an arbitrary
        # provider exception into a public diagnostic.
        public_message = public_message.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
        public_message = public_message[:1000]
        self.error_code = error_code
        self.public_message = public_message
        super().__init__(public_message)


class _StageOutcome:
    __slots__ = ("stage", "job_id", "stage_attempt_id", "cache_hit", "result")

    def __init__(
        self,
        stage: str,
        job_id: str,
        stage_attempt_id: str,
        cache_hit: bool,
        result: dict[str, Any],
    ) -> None:
        self.stage = stage
        self.job_id = job_id
        self.stage_attempt_id = stage_attempt_id
        self.cache_hit = cache_hit
        self.result = result


def _failure(stage: str, reason: str = "failed") -> TestVideoError:
    labels = {
        "narration": "narration",
        "timeline": "timeline",
        "assembly": "assembly",
        "qc": "QC",
    }
    label = labels.get(stage, "test video")
    if reason == "timeout":
        return TestVideoError("timeout", f"The local {label} job timed out.")
    if reason == "interrupted":
        return TestVideoError("stage_interrupted", f"The local {label} job was interrupted.")
    if reason == "invalid":
        return TestVideoError("invalid_worker_result", f"The local {label} job returned an invalid result.")
    return TestVideoError("stage_failed", f"The local {label} job failed.")


def _request_error(message: str = "The test-video request is invalid.") -> TestVideoError:
    return TestVideoError("invalid_request", message)


def _safe_id(value: Any, *, label: str, artifact: bool = False) -> str:
    if not isinstance(value, str):
        raise _request_error()
    try:
        validate_identifier(value, label=label)
    except (SecurityError, ValueError):
        raise _request_error() from None
    if artifact and _ARTIFACT_ID_RE.fullmatch(value) is None:
        raise _request_error()
    return value


def _workspace(service: Any) -> Path:
    value = getattr(service, "workspace", None)
    if not isinstance(value, (str, Path)):
        raise TestVideoError("service_invalid", "The Studio service is not configured for a workspace.")
    try:
        return Path(value).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise TestVideoError("service_invalid", "The Studio service workspace is unavailable.") from None


def _has_symlink_component(workspace: Path, candidate: str | Path) -> bool:
    try:
        root = workspace.resolve(strict=True)
        supplied = Path(candidate)
        lexical = supplied if supplied.is_absolute() else root / supplied
        relative = lexical.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return True
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _lookup_production(service: Any, production_id: str) -> dict[str, Any] | None:
    for name in ("production_detail", "get_production"):
        method = getattr(service, name, None)
        if not callable(method):
            continue
        try:
            value = method(production_id)
        except Exception:
            return None
        if isinstance(value, dict):
            return value
    database = getattr(service, "database", None)
    method = getattr(database, "get_production", None)
    if callable(method):
        try:
            value = method(production_id)
        except Exception:
            return None
        return value if isinstance(value, dict) else None
    return None


def _lookup_artifact(
    service: Any, production: dict[str, Any], artifact_id: str
) -> dict[str, Any] | None:
    method = getattr(service, "artifact", None)
    if callable(method):
        try:
            value = method(artifact_id)
        except Exception:
            return None
        if isinstance(value, dict):
            return value
    database = getattr(service, "database", None)
    method = getattr(database, "get_artifact", None)
    if callable(method):
        try:
            value = method(artifact_id)
        except Exception:
            return None
        if isinstance(value, dict):
            return value
    artifacts = production.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict) and item.get("id") == artifact_id:
                return item
    return None


def _validate_source(
    service: Any,
    production_id: str,
    artifact_id: str,
    production: dict[str, Any],
) -> tuple[dict[str, Any], Path, str]:
    artifact = _lookup_artifact(service, production, artifact_id)
    if not isinstance(artifact, dict):
        raise TestVideoError(
            "source_artifact_not_available",
            "The source video artifact is not available.",
        )
    if (
        artifact.get("id", artifact_id) != artifact_id
        or artifact.get("production_id") != production_id
        or artifact.get("available") is not True
        or artifact.get("kind") != "video"
        or not isinstance(artifact.get("media_type"), str)
        or not artifact["media_type"].startswith("video/")
    ):
        raise TestVideoError(
            "source_artifact_not_available",
            "The source video artifact is not available for this production.",
        )

    candidate = artifact.get("rel_path")
    if candidate is None:
        candidate = artifact.get("path")
    if not isinstance(candidate, (str, Path)) or not str(candidate):
        raise TestVideoError("source_artifact_not_available", "The source video path is not available.")
    workspace = _workspace(service)
    try:
        path = workspace_path(workspace, candidate, must_exist=True)
        relative = relative_workspace_path(workspace, path)
    except (SecurityError, OSError, ValueError):
        raise TestVideoError("source_artifact_not_available", "The source video path is not available.") from None
    if (
        _has_symlink_component(workspace, candidate)
        or path.is_symlink()
        or not path.is_file()
        or sensitive_artifact_path(relative)
    ):
        raise TestVideoError("source_artifact_not_available", "The source video path is not safe.")
    try:
        stat = path.stat()
    except OSError:
        raise TestVideoError("source_artifact_not_available", "The source video path is not available.") from None
    recorded_bytes = artifact.get("bytes")
    recorded_hash = artifact.get("sha256")
    if (
        isinstance(recorded_bytes, bool)
        or not isinstance(recorded_bytes, int)
        or recorded_bytes <= 0
        or recorded_bytes > _MAX_ARTIFACT_BYTES
        or stat.st_size != recorded_bytes
        or not isinstance(recorded_hash, str)
        or _SHA256_RE.fullmatch(recorded_hash) is None
    ):
        raise TestVideoError("source_artifact_changed", "The source video artifact metadata is invalid.")
    try:
        actual_hash = _sha256_file(path)
    except OSError:
        raise TestVideoError("source_artifact_changed", "The source video artifact could not be verified.") from None
    if actual_hash != recorded_hash.upper():
        raise TestVideoError("source_artifact_changed", "The source video artifact changed after registration.")

    # Return a private copy with a normalized relative path.  Never pass the
    # caller's absolute path onward or expose it in the final JSON.
    normalized = dict(artifact)
    normalized["id"] = artifact_id
    normalized["rel_path"] = relative
    normalized["bytes"] = stat.st_size
    normalized["sha256"] = actual_hash
    return normalized, path, relative


def _normalize_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise _request_error()
    allowed = {
        "production_id",
        "source_artifact_id",
        "source_video_artifact_id",
        "video_artifact_id",
        "segments",
        "voice",
        "rate",
        "pronunciations",
        "start_ms",
        "end_ms",
        "timeout",
        "timeout_seconds",
        "include_captioned",
        "variant",
    }
    if set(request) - allowed:
        raise _request_error()
    production_id = _safe_id(request.get("production_id"), label="production id")

    source_values = [
        request[name]
        for name in ("source_artifact_id", "source_video_artifact_id", "video_artifact_id")
        if name in request
    ]
    if not source_values or any(value != source_values[0] for value in source_values):
        raise _request_error()
    source_artifact_id = _safe_id(source_values[0], label="source artifact id", artifact=True)

    narration_body = {
        key: request[key]
        for key in ("segments", "voice", "rate", "pronunciations")
        if key in request
    }
    try:
        narration = validate_local_narration_payload(narration_body)
    except (LocalNarrationValidationError, ValueError, TypeError):
        raise _request_error() from None

    start_ms = request.get("start_ms", 0)
    if (
        isinstance(start_ms, bool)
        or not isinstance(start_ms, int)
        or start_ms < 0
        or start_ms > _MAX_TIMELINE_DURATION_MS
    ):
        raise _request_error()
    end_ms = request.get("end_ms")
    if (
        isinstance(end_ms, bool)
        or not isinstance(end_ms, int)
        or end_ms <= start_ms
        or end_ms - start_ms < _MIN_TIMELINE_DURATION_MS
        or end_ms > _MAX_TIMELINE_DURATION_MS
    ):
        raise _request_error()

    timeout_values = [request[name] for name in ("timeout", "timeout_seconds") if name in request]
    if len(timeout_values) > 1 and timeout_values[0] != timeout_values[1]:
        raise _request_error()
    timeout = timeout_values[0] if timeout_values else _DEFAULT_TIMEOUT_SECONDS
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise _request_error()
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout < 1 or timeout > 3600:
        raise _request_error()

    variant = request.get("variant")
    if variant not in {"clean", "captioned"}:
        raise _request_error()
    include_captioned = request.get("include_captioned", True)
    if not isinstance(include_captioned, bool):
        raise _request_error()
    if variant == "captioned" and not include_captioned:
        raise _request_error()

    timeline = {
        "clips": [
            {
                "video_artifact_id": source_artifact_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        ]
    }
    try:
        # Validate the exact public payload that will be passed to the service.
        timeline = validate_local_timeline_payload(timeline)
    except (TimelineValidationError, ValueError, TypeError):
        raise _request_error() from None
    return {
        "production_id": production_id,
        "source_artifact_id": source_artifact_id,
        "narration": narration,
        "timeline": timeline,
        "include_captioned": include_captioned,
        "variant": variant,
        "timeout": timeout,
    }


def _create_run(service: Any, production_id: str) -> tuple[str, str]:
    method = getattr(service, "create_run", None)
    if not callable(method):
        raise TestVideoError("service_invalid", "The Studio service cannot create a run.")
    body = {
        "changes": ["narration", "timeline"],
        "execution_profile": "local_sapi",
        "estimated_cost": {"amount": 0, "currency": "USD"},
    }
    try:
        created = method(production_id, body)
    except TestVideoError:
        raise
    except Exception:
        raise TestVideoError("run_creation_failed", "The local test-video run could not be created.") from None
    if not isinstance(created, dict):
        raise TestVideoError("run_creation_failed", "The local test-video run could not be created.")
    run = created.get("run") if isinstance(created.get("run"), dict) else created
    revision = created.get("revision") if isinstance(created.get("revision"), dict) else {}
    run_id = run.get("id", run.get("run_id")) if isinstance(run, dict) else None
    revision_id = revision.get("id") if isinstance(revision, dict) else None
    revision_id = created.get("revision_id", revision_id)
    if isinstance(run, dict):
        revision_id = run.get("revision_id", revision_id)
    try:
        run_id = _safe_id(run_id, label="run id")
        revision_id = _safe_id(revision_id, label="revision id")
    except TestVideoError:
        raise TestVideoError("run_creation_failed", "The local test-video run returned an invalid identity.") from None
    if isinstance(run, dict):
        if run.get("production_id", production_id) != production_id:
            raise TestVideoError("run_creation_failed", "The local test-video run returned invalid provenance.")
        if run.get("execution_profile") not in {None, "local_sapi"}:
            raise TestVideoError("run_creation_failed", "The local test-video run returned an invalid profile.")
    return run_id, revision_id


def _waiter(service: Any) -> Callable[..., Any] | None:
    direct = getattr(service, "wait", None)
    if callable(direct):
        return direct
    jobs = getattr(service, "jobs", None)
    nested = getattr(jobs, "wait", None)
    return nested if callable(nested) else None


def _invoke_wait(wait: Callable[..., Any], job_id: str, timeout: float) -> Any:
    try:
        signature = inspect.signature(wait)
    except (TypeError, ValueError):
        return wait(job_id, timeout)
    parameters = signature.parameters
    if "timeout" in parameters or any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    ):
        return wait(job_id, timeout=timeout)
    positional = [
        item
        for item in parameters.values()
        if item.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return wait(job_id, timeout) if len(positional) >= 2 else wait(job_id)


def _job_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("job")
    if isinstance(nested, dict):
        return nested
    return value


def _job_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get("id", value.get("job_id"))
    return candidate if isinstance(candidate, str) else None


def _attempt_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get("stage_attempt_id")
    if isinstance(candidate, str):
        return candidate
    result = value.get("result")
    if isinstance(result, dict) and isinstance(result.get("stage_attempt_id"), str):
        return result["stage_attempt_id"]
    stage_attempt = value.get("stage_attempt")
    if isinstance(stage_attempt, dict) and isinstance(stage_attempt.get("id"), str):
        return stage_attempt["id"]
    return None


def _result_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if isinstance(result, dict):
        return result
    # A small service double may return a terminal job result directly.
    if "status" in value and any(key in value for key in ("artifacts", "cache_hit", "technical_verdict")):
        return value
    return None


def _queue_and_wait(
    service: Any,
    stage: str,
    run_id: str,
    payload: dict[str, Any],
    deadline: float,
) -> _StageOutcome:
    method_name = _STAGE_METHODS[stage]
    method = getattr(service, method_name, None)
    if not callable(method):
        raise TestVideoError("service_invalid", f"The Studio service cannot execute local {stage}.")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _failure(stage, "timeout")
    try:
        queued = method(run_id, payload)
    except TimeoutError:
        raise _failure(stage, "timeout") from None
    except TestVideoError:
        raise
    except Exception:
        raise _failure(stage) from None
    if not isinstance(queued, dict):
        raise _failure(stage, "invalid")
    queued_job_id = _job_id(queued)
    if not isinstance(queued_job_id, str):
        raise _failure(stage, "invalid")
    try:
        validate_identifier(queued_job_id, label="job id")
    except (SecurityError, ValueError):
        raise _failure(stage, "invalid") from None
    waiter = _waiter(service)
    completed: Any = queued
    if waiter is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _failure(stage, "timeout")
        try:
            completed = _invoke_wait(waiter, queued_job_id, remaining)
        except (TimeoutError,) :
            raise _failure(stage, "timeout") from None
        except TestVideoError:
            raise
        except Exception:
            raise _failure(stage) from None
    record = _job_record(completed)
    if record is None:
        # ``JobManager.wait`` always returns a row, but a small adapter may
        # use ``None`` to mean that its bounded wait expired.  Treat that as
        # timeout rather than surfacing an implementation detail.
        raise _failure(stage, "timeout")
    status = record.get("status")
    completed_job_id = _job_id(record)
    if completed_job_id is not None and completed_job_id != queued_job_id:
        raise _failure(stage, "invalid")
    if status != "succeeded":
        if status == "interrupted":
            raise _failure(stage, "interrupted")
        if status in {"queued", "running", None}:
            raise _failure(stage, "timeout")
        raise _failure(stage)
    result = _result_dict(record)
    if result is None:
        raise _failure(stage, "invalid")
    completed_attempt_id = _attempt_id(record)
    queued_attempt_id = _attempt_id(queued)
    if (
        completed_attempt_id is not None
        and queued_attempt_id is not None
        and completed_attempt_id != queued_attempt_id
    ):
        raise _failure(stage, "invalid")
    attempt_id = completed_attempt_id or queued_attempt_id
    if not isinstance(attempt_id, str):
        raise _failure(stage, "invalid")
    try:
        validate_identifier(attempt_id, label="stage attempt id")
    except (SecurityError, ValueError):
        raise _failure(stage, "invalid") from None
    cache_hit = result.get("cache_hit")
    if not isinstance(cache_hit, bool):
        raise _failure(stage, "invalid")
    return _StageOutcome(stage, queued_job_id, attempt_id, cache_hit, result)


def _raw_artifact_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get("id", value.get("artifact_id"))
    return candidate if isinstance(candidate, str) else None


def _find_artifact(result: dict[str, Any], name: str) -> dict[str, Any]:
    raw = result.get("artifacts")
    if isinstance(raw, list):
        matches = [item for item in raw if isinstance(item, dict) and item.get("name") == name]
        if len(matches) == 1:
            return matches[0]
    direct = result.get("timeline_artifact") if name == "timeline-preview.mp4" else None
    if isinstance(direct, dict):
        return direct
    direct = result.get("master_artifact") if name.startswith("master-") else None
    if isinstance(direct, dict):
        return direct
    raise TestVideoError("invalid_worker_result", "A required test-video artifact was not returned.")


def _artifact_view(raw: Any, *, expected_kind: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    artifact_id = _raw_artifact_id(raw)
    if not isinstance(artifact_id, str):
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    try:
        validate_identifier(artifact_id, label="artifact id")
    except (SecurityError, ValueError):
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.") from None
    name = raw.get("name")
    if not isinstance(name, str) or not name or len(name) > _MAX_RESULT_STRING:
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    kind = raw.get("kind")
    media_type = raw.get("media_type", raw.get("mime"))
    if not isinstance(kind, str) or not isinstance(media_type, str):
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    if expected_kind is not None and kind != expected_kind:
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    bytes_value = raw.get("bytes")
    if isinstance(bytes_value, bool) or not isinstance(bytes_value, int) or bytes_value < 0 or bytes_value > _MAX_ARTIFACT_BYTES:
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    sha = raw.get("sha256")
    if not isinstance(sha, str) or _SHA256_RE.fullmatch(sha) is None:
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    rel = raw.get("rel_path")
    if rel is None:
        rel = raw.get("path")
    if not isinstance(rel, str) or not rel or len(rel) > 1024 or "\x00" in rel:
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    rel = rel.replace("\\", "/")
    # Treat the value as both POSIX and Windows syntax.  The public result may
    # only contain a canonical workspace-relative path: no drive/UNC root,
    # empty or dot component, or traversal hidden inside an otherwise benign
    # prefix.
    if (
        PurePosixPath(rel).is_absolute()
        or bool(PureWindowsPath(rel).drive)
        or any(part in {"", ".", ".."} for part in rel.split("/"))
    ):
        raise TestVideoError("invalid_worker_result", "A required test-video artifact was invalid.")
    return {
        "id": artifact_id,
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "rel_path": rel,
        "bytes": bytes_value,
        "sha256": sha.upper(),
    }


def _job_view(outcome: _StageOutcome) -> dict[str, Any]:
    return {
        "job_id": outcome.job_id,
        "stage_attempt_id": outcome.stage_attempt_id,
        "cache_hit": outcome.cache_hit,
    }


def run_test_video(service: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Render one local test video through the existing Studio service.

    The function never opens a lock and never closes ``service``.  Callers
    own the service lifetime.  All four worker-backed stages are queued and
    waited in order, with one bounded overall deadline.
    """

    normalized = _normalize_request(request)
    production_id = normalized["production_id"]
    production = _lookup_production(service, production_id)
    if production is None or production.get("id", production_id) != production_id:
        raise TestVideoError("production_not_found", "The production is not available.")
    source, _source_path, _source_relative = _validate_source(
        service, production_id, normalized["source_artifact_id"], production
    )

    run_id, revision_id = _create_run(service, production_id)
    deadline = time.monotonic() + normalized["timeout"]

    narration = _queue_and_wait(
        service, "narration", run_id, normalized["narration"], deadline
    )
    timeline_payload = normalized["timeline"]
    timeline = _queue_and_wait(service, "timeline", run_id, timeline_payload, deadline)
    timeline_raw = _find_artifact(timeline.result, "timeline-preview.mp4")
    timeline_artifact_id = _raw_artifact_id(timeline_raw)
    if not isinstance(timeline_artifact_id, str):
        raise TestVideoError("invalid_worker_result", "The timeline job did not return a usable artifact.")
    try:
        validate_identifier(timeline_artifact_id, label="timeline artifact id")
    except (SecurityError, ValueError):
        raise TestVideoError("invalid_worker_result", "The timeline job did not return a usable artifact.") from None
    timeline_artifact = _artifact_view(timeline_raw, expected_kind="video")

    narration_attempt_id = narration.stage_attempt_id
    assembly_payload = {
        "video_artifact_id": timeline_artifact_id,
        "narration_attempt_id": narration_attempt_id,
        "include_captioned": normalized["include_captioned"],
    }
    try:
        assembly_payload = validate_local_assembly_payload(assembly_payload)
    except (LocalAssemblyValidationError, ValueError, TypeError):
        raise TestVideoError("invalid_worker_result", "The assembly request could not be prepared.") from None
    assembly = _queue_and_wait(service, "assembly", run_id, assembly_payload, deadline)
    master_name = "master-captioned.mp4" if normalized["variant"] == "captioned" else "master-clean.mp4"
    master_raw = _find_artifact(assembly.result, master_name)
    master_artifact = _artifact_view(master_raw, expected_kind="video")
    master_artifact_id = _raw_artifact_id(master_raw)
    if not isinstance(master_artifact_id, str):
        raise TestVideoError("invalid_worker_result", "The assembly job did not return a usable master artifact.")

    qc_payload = {"assembly_attempt_id": assembly.stage_attempt_id, "variant": normalized["variant"]}
    try:
        qc_payload = validate_local_qc_payload(qc_payload)
    except (LocalQcValidationError, ValueError, TypeError):
        raise TestVideoError("invalid_worker_result", "The QC request could not be prepared.") from None
    qc = _queue_and_wait(service, "qc", run_id, qc_payload, deadline)
    if qc.result.get("analysis_status") != "succeeded":
        raise TestVideoError("invalid_worker_result", "The local QC job returned an invalid result.")
    verdict = qc.result.get("technical_verdict", qc.result.get("verdict"))
    if verdict != "pass":
        raise TestVideoError("technical_qc_failed", "Local technical QC did not pass.")
    raw_reports = qc.result.get("artifacts")
    if not isinstance(raw_reports, list) or len(raw_reports) > _MAX_RESULT_ARTIFACTS:
        raise TestVideoError("invalid_worker_result", "The QC job returned invalid report artifacts.")
    report_artifacts = [_artifact_view(item, expected_kind="document") for item in raw_reports]

    source_view = _artifact_view(source, expected_kind="video")
    return {
        "production_id": production_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "jobs": {
            "narration": _job_view(narration),
            "timeline": _job_view(timeline),
            "assembly": _job_view(assembly),
            "qc": _job_view(qc),
        },
        "source": source_view,
        "timeline": timeline_artifact,
        "master": master_artifact,
        "qc": {
            "verdict": "pass",
            "report_artifacts": report_artifacts,
        },
    }


__all__ = ["TestVideoError", "run_test_video"]
