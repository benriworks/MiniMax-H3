from __future__ import annotations

"""One-command, machine-facing execution of a saved Quick Create recipe.

This module deliberately owns no media work.  It validates one closed JSON
request, uses the existing announcement recipe CAS and Detailed Test Video
job, then projects the durable terminal record to a small redacted summary.
"""

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .announcement_video import (
    ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    AnnouncementVideoValidationError,
    validate_announcement_recipe_id,
    validate_announcement_recipe_payload,
)
from .detailed_test_video import DETAILED_TEST_VIDEO_STAGES
from .security import SecurityError, validate_identifier


QUICK_CREATE_SCHEMA_VERSION = 1
QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS = 600
QUICK_CREATE_MIN_TIMEOUT_SECONDS = 1
QUICK_CREATE_MAX_TIMEOUT_SECONDS = 3_600
QUICK_CREATE_POLL_INTERVAL_SECONDS = 2.0
QUICK_CREATE_MAX_INPUT_BYTES = 256 * 1024

_REQUEST_REQUIRED_KEYS = {
    "schema_version",
    "production_id",
    "recipe_id",
    "expected_revision",
    "recipe",
}
_REQUEST_KEYS = _REQUEST_REQUIRED_KEYS | {"timeout_seconds"}
_ACTIVE_JOB_STATUSES = {"queued", "running"}
_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "interrupted"}
_SHA256_RE = re.compile(r"[0-9A-Fa-f]{64}")
_REQUEST_KEY_RE = re.compile(r"[0-9A-F]{64}")
_SAFE_ERROR_CODE_RE = re.compile(r"[a-z0-9_.-]{1,128}")
_QC_REPORT_NAMES = {"technical-qc.json", "ffprobe.json", "manifest.json"}


class QuickCreateError(RuntimeError):
    """A safe, machine-readable Quick Create failure."""

    def __init__(
        self,
        code: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        safe_code = (
            code
            if isinstance(code, str) and _SAFE_ERROR_CODE_RE.fullmatch(code)
            else "quick_create_failed"
        )
        super().__init__(safe_code)
        self.code = safe_code
        self.context = dict(context or {})


class QuickCreateValidationError(QuickCreateError, ValueError):
    """The versioned input document was not an exact supported request."""

    def __init__(self, code: str = "invalid_quick_create_request") -> None:
        super().__init__(code)


class QuickCreateQcNonPass(QuickCreateError):
    """The durable job reached a technical-QC non-pass outcome."""


def _invalid() -> QuickCreateValidationError:
    return QuickCreateValidationError()


def _reject_json_constant(_value: str) -> None:
    raise _invalid()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _invalid()
        value[key] = item
    return value


def validate_quick_create_request(value: Any) -> dict[str, Any]:
    """Return the normalized exact schema-v1 Quick Create request."""

    if not isinstance(value, dict) or not _REQUEST_REQUIRED_KEYS <= set(value):
        raise _invalid()
    if set(value) not in (_REQUEST_REQUIRED_KEYS, _REQUEST_KEYS):
        raise _invalid()
    if (
        isinstance(value.get("schema_version"), bool)
        or not isinstance(value.get("schema_version"), int)
        or value.get("schema_version") != QUICK_CREATE_SCHEMA_VERSION
    ):
        raise _invalid()

    production_id = value.get("production_id")
    recipe_id = value.get("recipe_id")
    try:
        validate_identifier(production_id, label="production id")
        recipe_id = validate_announcement_recipe_id(recipe_id)
        recipe = validate_announcement_recipe_payload(value.get("recipe"))
    except (
        AnnouncementVideoValidationError,
        SecurityError,
        TypeError,
        ValueError,
    ):
        raise _invalid() from None

    expected_revision = value.get("expected_revision")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or not 0 <= expected_revision <= 1_000_000
    ):
        raise _invalid()
    timeout_seconds = value.get(
        "timeout_seconds", QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS
    )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not QUICK_CREATE_MIN_TIMEOUT_SECONDS
        <= timeout_seconds
        <= QUICK_CREATE_MAX_TIMEOUT_SECONDS
    ):
        raise _invalid()

    return {
        "schema_version": QUICK_CREATE_SCHEMA_VERSION,
        "production_id": production_id,
        "recipe_id": recipe_id,
        "expected_revision": expected_revision,
        "recipe": recipe,
        "timeout_seconds": timeout_seconds,
    }


def load_quick_create_request(path: Path) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON file without exposing its path on error."""

    try:
        candidate = Path(path)
        if not candidate.is_file():
            raise OSError("input is not a regular file")
        size = candidate.stat().st_size
        if not 1 <= size <= QUICK_CREATE_MAX_INPUT_BYTES:
            raise QuickCreateValidationError("quick_create_input_too_large")
        with candidate.open("rb") as handle:
            raw = handle.read(QUICK_CREATE_MAX_INPUT_BYTES + 1)
        if len(raw) != size or len(raw) > QUICK_CREATE_MAX_INPUT_BYTES:
            raise QuickCreateValidationError("quick_create_input_changed")
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except QuickCreateValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise _invalid() from None
    return validate_quick_create_request(parsed)


def _valid_identifier(value: Any, *, label: str) -> str:
    try:
        return validate_identifier(value, label=label)
    except (SecurityError, TypeError, ValueError):
        raise QuickCreateError("invalid_quick_create_result") from None


def _valid_request_key(value: Any) -> str:
    if not isinstance(value, str) or _REQUEST_KEY_RE.fullmatch(value) is None:
        raise QuickCreateError("invalid_quick_create_result")
    return value


def _valid_revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise QuickCreateError("invalid_quick_create_result")
    return value


def _valid_deduplicated(value: Any) -> bool:
    if not isinstance(value, bool):
        raise QuickCreateError("invalid_quick_create_result")
    return value


def _safe_service_error_code(exc: BaseException, default: str) -> str:
    candidate = getattr(exc, "code", None)
    if not isinstance(candidate, str):
        candidate = getattr(exc, "error_code", None)
    if isinstance(candidate, str) and _SAFE_ERROR_CODE_RE.fullmatch(candidate):
        return candidate
    return default


def _saved_recipe_context(
    saved: Any, request: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(saved, Mapping):
        raise QuickCreateError("invalid_quick_create_result")
    if (
        saved.get("production_id") != request["production_id"]
        or saved.get("id") != request["recipe_id"]
    ):
        raise QuickCreateError("invalid_quick_create_result")
    version_id = _valid_identifier(
        saved.get("version_id"), label="announcement recipe version id"
    )
    revision = _valid_revision(saved.get("revision"))
    deduplicated = _valid_deduplicated(saved.get("deduplicated"))
    expected_revision = request["expected_revision"]
    if (
        re.fullmatch(r"annv_[0-9a-f]{32}", version_id) is None
        or saved.get("recipe") != request["recipe"]
        or (
            not deduplicated
            and revision != expected_revision + 1
        )
        or (
            deduplicated
            and revision not in {expected_revision, expected_revision + 1}
        )
    ):
        raise QuickCreateError("invalid_quick_create_result")
    return {
        "production_id": request["production_id"],
        "recipe_id": request["recipe_id"],
        "recipe_version_id": version_id,
        "recipe_revision": revision,
        "recipe_deduplicated": deduplicated,
    }


def _execution_context(
    submitted: Any,
    saved_context: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(submitted, Mapping):
        raise QuickCreateError("invalid_quick_create_result")
    if (
        submitted.get("kind") != "detailed_test_video"
        or submitted.get("status")
        not in _ACTIVE_JOB_STATUSES | _TERMINAL_JOB_STATUSES
        or submitted.get("production_id") != saved_context["production_id"]
        or submitted.get("announcement_recipe_id") != saved_context["recipe_id"]
        or submitted.get("announcement_recipe_version_id")
        != saved_context["recipe_version_id"]
        or submitted.get("announcement_recipe_revision")
        != saved_context["recipe_revision"]
    ):
        raise QuickCreateError("invalid_quick_create_result")
    job_id = _valid_identifier(submitted.get("id"), label="job id")
    run_id = _valid_identifier(submitted.get("run_id"), label="run id")
    revision_id = _valid_identifier(
        submitted.get("revision_id"), label="revision id"
    )
    request_key = _valid_request_key(submitted.get("request_key"))
    deduplicated = _valid_deduplicated(submitted.get("deduplicated"))
    link = submitted.get("announcement_execution")
    if (
        not isinstance(link, Mapping)
        or link.get("production_id") != saved_context["production_id"]
        or link.get("recipe_id") != saved_context["recipe_id"]
        or link.get("recipe_version_id") != saved_context["recipe_version_id"]
        or link.get("recipe_revision") != saved_context["recipe_revision"]
        or link.get("job_id") != job_id
        or link.get("run_id") != run_id
        or link.get("revision_id") != revision_id
        or link.get("request_key") != request_key
    ):
        raise QuickCreateError("invalid_quick_create_result")
    return {
        **saved_context,
        "job_id": job_id,
        "run_id": run_id,
        "revision_id": revision_id,
        "request_key": request_key,
        "job_deduplicated": deduplicated,
    }


def _terminal_context(
    terminal: Any, execution: Mapping[str, Any]
) -> tuple[str, Any]:
    if not isinstance(terminal, Mapping):
        raise QuickCreateError("quick_create_job_unavailable", context=execution)
    status = terminal.get("status")
    if status not in _ACTIVE_JOB_STATUSES | _TERMINAL_JOB_STATUSES:
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    payload = terminal.get("payload")
    if (
        terminal.get("id") != execution["job_id"]
        or terminal.get("kind") != "detailed_test_video"
        or terminal.get("production_id") != execution["production_id"]
        or not isinstance(payload, Mapping)
        or payload.get("production_id") != execution["production_id"]
        or payload.get("run_id") != execution["run_id"]
        or payload.get("revision_id") != execution["revision_id"]
        or payload.get("request_key") != execution["request_key"]
        or payload.get("stage") != "detailed_test_video"
    ):
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    return status, terminal.get("result")


def _relative_artifact(
    value: Any,
    *,
    run_id: str,
    stage: str,
    expected_name: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise QuickCreateError("invalid_quick_create_result")
    artifact_id = _valid_identifier(value.get("id"), label="artifact id")
    name = value.get("name")
    relative = value.get("rel_path")
    byte_count = value.get("bytes")
    digest = value.get("sha256")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 128
        or (expected_name is not None and name != expected_name)
        or not isinstance(relative, str)
        or not relative
        or len(relative) > 1_024
        or "\x00" in relative
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count <= 0
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
    ):
        raise QuickCreateError("invalid_quick_create_result")
    normalized = relative.replace("\\", "/")
    if (
        PurePosixPath(normalized).is_absolute()
        or bool(PureWindowsPath(normalized).drive)
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise QuickCreateError("invalid_quick_create_result")
    parts = normalized.split("/")
    if (
        len(parts) != 7
        or parts[:3] != ["outputs", "studio", "runs"]
        or parts[3] != run_id
        or parts[4] != stage
        or _REQUEST_KEY_RE.fullmatch(parts[5]) is None
        or parts[6] != name
    ):
        raise QuickCreateError("invalid_quick_create_result")
    return {
        "id": artifact_id,
        "name": name,
        "rel_path": normalized,
        "bytes": byte_count,
        "sha256": digest.upper(),
    }


def _child_stages(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != set(
        DETAILED_TEST_VIDEO_STAGES
    ):
        raise QuickCreateError("invalid_quick_create_result")
    result: dict[str, dict[str, Any]] = {}
    for stage in DETAILED_TEST_VIDEO_STAGES:
        child = value.get(stage)
        if (
            not isinstance(child, Mapping)
            or child.get("stage") != stage
            or child.get("status") != "succeeded"
            or not isinstance(child.get("cache_hit"), bool)
        ):
            raise QuickCreateError("invalid_quick_create_result")
        result[stage] = {
            "stage": stage,
            "status": "succeeded",
            "job_id": _valid_identifier(child.get("job_id"), label="child job id"),
            "stage_attempt_id": _valid_identifier(
                child.get("stage_attempt_id"), label="stage attempt id"
            ),
            "cache_hit": child["cache_hit"],
        }
    return result


def _success_summary(
    result: Any,
    execution: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    technical_verdict = result.get("technical_verdict")
    qc = result.get("qc")
    qc_verdict = qc.get("verdict") if isinstance(qc, Mapping) else None
    if technical_verdict != "pass" or qc_verdict != "pass":
        if (
            isinstance(technical_verdict, str)
            and technical_verdict != "pass"
        ) or (isinstance(qc_verdict, str) and qc_verdict != "pass"):
            raise QuickCreateQcNonPass(
                "technical_qc_failed",
                context={**execution, "status": "succeeded"},
            )
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    if (
        result.get("production_id") != execution["production_id"]
        or result.get("run_id") != execution["run_id"]
        or result.get("revision_id") != execution["revision_id"]
        or result.get("request_key") != execution["request_key"]
    ):
        raise QuickCreateError("invalid_quick_create_result", context=execution)

    children = _child_stages(result.get("children"))
    variant = request["recipe"]["variant"]
    master_name = (
        "master-captioned.mp4" if variant == "captioned" else "master-clean.mp4"
    )
    master = _relative_artifact(
        result.get("master"),
        run_id=execution["run_id"],
        stage="assembly",
        expected_name=master_name,
    )
    reports_value = qc.get("report_artifacts")
    if not isinstance(reports_value, list) or len(reports_value) != len(
        _QC_REPORT_NAMES
    ):
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    reports = [
        _relative_artifact(item, run_id=execution["run_id"], stage="qc")
        for item in reports_value
    ]
    if {item["name"] for item in reports} != _QC_REPORT_NAMES:
        raise QuickCreateError("invalid_quick_create_result", context=execution)
    reports.sort(key=lambda item: item["name"])

    return {
        "schema_version": QUICK_CREATE_SCHEMA_VERSION,
        **execution,
        "status": "succeeded",
        "technical_verdict": "pass",
        "children": children,
        "master": master,
        "qc": {
            "verdict": "pass",
            "report_artifacts": reports,
        },
    }


def _terminal_error_code(terminal: Mapping[str, Any]) -> str:
    error = terminal.get("error")
    if not isinstance(error, Mapping):
        return "quick_create_job_failed"
    code = error.get("code")
    if isinstance(code, str) and _SAFE_ERROR_CODE_RE.fullmatch(code):
        return code
    return "quick_create_job_failed"


def run_quick_create(
    service: Any,
    value: Any,
    *,
    poll_interval_seconds: float = QUICK_CREATE_POLL_INTERVAL_SECONDS,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Save, execute, and poll one Quick Create request to terminal truth."""

    request = validate_quick_create_request(value)
    if (
        isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, (int, float))
        or not math.isfinite(float(poll_interval_seconds))
        or poll_interval_seconds < QUICK_CREATE_POLL_INTERVAL_SECONDS
    ):
        raise ValueError("poll interval must remain low frequency")
    clock = monotonic or time.monotonic
    sleeper = sleep or time.sleep
    started_at = clock()
    request_deadline = started_at + request["timeout_seconds"]
    if deadline is None:
        effective_deadline = request_deadline
    elif (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(float(deadline))
    ):
        raise ValueError("deadline is invalid")
    else:
        # A caller may spend part of the request budget refreshing the index.
        # It may tighten, but never extend, the versioned request timeout.
        effective_deadline = min(float(deadline), request_deadline)
    if effective_deadline - started_at <= 0:
        raise QuickCreateError("quick_create_timeout")

    try:
        saved = service.save_announcement_recipe(
            request["production_id"],
            request["recipe_id"],
            {
                "schema_version": ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
                "expected_revision": request["expected_revision"],
                "recipe": request["recipe"],
            },
        )
    except Exception as exc:
        raise QuickCreateError(
            _safe_service_error_code(exc, "quick_create_save_failed")
        ) from exc
    saved_context = _saved_recipe_context(saved, request)
    if effective_deadline - clock() <= 0:
        raise QuickCreateError(
            "quick_create_timeout",
            context=saved_context,
        )

    try:
        submitted = service.execute_announcement_recipe(
            request["production_id"],
            request["recipe_id"],
            {
                "schema_version": ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
                "revision": saved_context["recipe_revision"],
            },
        )
    except Exception as exc:
        raise QuickCreateError(
            _safe_service_error_code(exc, "quick_create_execute_failed"),
            context=saved_context,
        ) from exc
    execution = _execution_context(submitted, saved_context)
    last_status = submitted["status"]

    while True:
        remaining = effective_deadline - clock()
        if remaining <= 0:
            raise QuickCreateError(
                "quick_create_timeout",
                context={**execution, "status": last_status},
            )
        try:
            terminal = service.job(execution["job_id"])
        except Exception as exc:
            raise QuickCreateError(
                _safe_service_error_code(exc, "quick_create_job_failed"),
                context=execution,
            ) from exc
        status, result = _terminal_context(terminal, execution)
        last_status = status
        if status == "succeeded":
            return _success_summary(result, execution, request)
        if status in {"failed", "interrupted"}:
            assert isinstance(terminal, Mapping)
            code = _terminal_error_code(terminal)
            context = {**execution, "status": status}
            if code == "technical_qc_failed":
                raise QuickCreateQcNonPass(code, context=context)
            raise QuickCreateError(code, context=context)

        sleeper(min(float(poll_interval_seconds), remaining))


__all__ = [
    "QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS",
    "QUICK_CREATE_MAX_INPUT_BYTES",
    "QUICK_CREATE_MAX_TIMEOUT_SECONDS",
    "QUICK_CREATE_MIN_TIMEOUT_SECONDS",
    "QUICK_CREATE_POLL_INTERVAL_SECONDS",
    "QUICK_CREATE_SCHEMA_VERSION",
    "QuickCreateError",
    "QuickCreateQcNonPass",
    "QuickCreateValidationError",
    "load_quick_create_request",
    "run_quick_create",
    "validate_quick_create_request",
]
