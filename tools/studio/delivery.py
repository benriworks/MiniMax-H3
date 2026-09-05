from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .assembly import (
    AssemblyError,
    _bounded_process,
    _find_tool,
    _tool_identity,
)
from .security import (
    SecurityError,
    canonical_json,
    sensitive_artifact_path,
    stable_id,
    validate_identifier,
    workspace_path,
)


DELIVERY_PACKAGE_SCHEMA_VERSION = 1
DELIVERY_PACKAGE_JOB_KIND = "delivery_package"
DELIVERY_PACKAGE_POLICY = "studio-delivery-package-v1"
DELIVERY_THUMBNAIL_POLICY = "clean-master-25-50-75-v1"
DELIVERY_AUDIT_POLICY = "production-snapshot-with-event-lines-v1"

_REQUEST_KEYS = {
    "schema_version",
    "run_id",
    "source_job_id",
    "artifacts",
    "metadata",
}
_ARTIFACT_REQUEST_KEYS = {
    "clean_master",
    "captioned_master",
    "captions",
    "technical_qc",
    "qc_ffprobe",
    "qc_manifest",
}
_METADATA_KEYS = {"title", "description"}
_STAGES = ("narration", "timeline", "assembly", "qc")
_CHILD_KINDS = {
    "narration": "local_narration",
    "timeline": "local_remotion_timeline",
    "assembly": "local_assembly",
    "qc": "local_qc",
}
_EXPECTED_ARTIFACTS = {
    "clean_master": ("assembly", "master-clean.mp4", "video", "video/mp4"),
    "captioned_master": (
        "assembly",
        "master-captioned.mp4",
        "video",
        "video/mp4",
    ),
    "captions": (
        "narration",
        "captions.srt",
        "subtitle",
        "application/x-subrip",
    ),
    "technical_qc": (
        "qc",
        "technical-qc.json",
        "document",
        "application/json",
    ),
    "qc_ffprobe": ("qc", "ffprobe.json", "document", "application/json"),
    "qc_manifest": ("qc", "manifest.json", "document", "application/json"),
}
_ARCHIVE_PATHS = {
    "clean_master": "video/master-clean.mp4",
    "captioned_master": "video/master-captioned.mp4",
    "captions": "subtitles/captions.srt",
    "technical_qc": "qc/technical-qc.json",
    "qc_ffprobe": "qc/ffprobe.json",
    "qc_manifest": "qc/manifest.json",
}
_ID_PATTERNS = {
    "run_id": re.compile(r"^run_[0-9a-f]{32}$"),
    "source_job_id": re.compile(r"^job_[0-9a-f]{32}$"),
    "artifact_id": re.compile(r"^art_[0-9a-f]{32}$"),
}
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_FORBIDDEN_TEXT_CHARACTERS = {
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
_MAX_TITLE_CHARS = 100
_MAX_DESCRIPTION_CHARS = 5_000
_MAX_INPUT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_TEXT_ARTIFACT_BYTES = 16 * 1024 * 1024
_MAX_AUDIT_BYTES = 32 * 1024 * 1024
_MAX_THUMBNAIL_BYTES = 32 * 1024 * 1024
_MAX_DELIVERY_MANIFEST_BYTES = 1024 * 1024
_MAX_ZIP_EXPANSION_RATIO = 1_000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)

_ARCHIVE_ENTRY_LIMITS = {
    "video/master-clean.mp4": _MAX_INPUT_BYTES,
    "video/master-captioned.mp4": _MAX_INPUT_BYTES,
    "subtitles/captions.srt": _MAX_TEXT_ARTIFACT_BYTES,
    "qc/technical-qc.json": _MAX_TEXT_ARTIFACT_BYTES,
    "qc/ffprobe.json": _MAX_TEXT_ARTIFACT_BYTES,
    "qc/manifest.json": _MAX_TEXT_ARTIFACT_BYTES,
    "thumbnails/thumbnail-01.png": _MAX_THUMBNAIL_BYTES,
    "thumbnails/thumbnail-02.png": _MAX_THUMBNAIL_BYTES,
    "thumbnails/thumbnail-03.png": _MAX_THUMBNAIL_BYTES,
    "metadata/publication.json": _MAX_TEXT_ARTIFACT_BYTES,
    "audit/production-snapshot.json": _MAX_AUDIT_BYTES,
    "audit/events.jsonl": _MAX_AUDIT_BYTES,
}
_EXPECTED_ZIP_NAMES = frozenset(
    {*_ARCHIVE_ENTRY_LIMITS, "delivery/manifest.json"}
)
_MAX_ZIP_UNCOMPRESSED_BYTES = (
    sum(_ARCHIVE_ENTRY_LIMITS.values()) + _MAX_DELIVERY_MANIFEST_BYTES
)


class DeliveryPackageValidationError(ValueError):
    def __init__(
        self,
        message: str = "The delivery package request is invalid.",
        *,
        code: str = "invalid_delivery_package_request",
    ):
        super().__init__(message)
        self.code = code


class DeliveryPackageError(RuntimeError):
    def __init__(
        self,
        message: str = "The delivery package could not be created.",
        *,
        code: str = "delivery_package_failed",
    ):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


def _strict_identifier(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise DeliveryPackageValidationError(
            f"{field} is invalid", code="invalid_delivery_package_request"
        )
    return value


def _strict_text(
    value: Any,
    *,
    field: str,
    maximum: int,
    allow_newline: bool,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DeliveryPackageValidationError(f"{field} is empty or padded")
    if len(value) > maximum:
        raise DeliveryPackageValidationError(f"{field} is too long")
    for character in value:
        codepoint = ord(character)
        if (
            character in _FORBIDDEN_TEXT_CHARACTERS
            or codepoint == 0x7F
            or (codepoint < 0x20 and not (allow_newline and character == "\n"))
        ):
            raise DeliveryPackageValidationError(
                f"{field} contains unsupported control characters"
            )
    return value


def validate_delivery_package_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise DeliveryPackageValidationError(
            "delivery package request fields are invalid"
        )
    if (
        isinstance(value.get("schema_version"), bool)
        or value.get("schema_version") != DELIVERY_PACKAGE_SCHEMA_VERSION
    ):
        raise DeliveryPackageValidationError(
            "delivery package schema_version is not supported"
        )
    run_id = _strict_identifier(
        value.get("run_id"), field="run_id", pattern=_ID_PATTERNS["run_id"]
    )
    source_job_id = _strict_identifier(
        value.get("source_job_id"),
        field="source_job_id",
        pattern=_ID_PATTERNS["source_job_id"],
    )
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != _ARTIFACT_REQUEST_KEYS:
        raise DeliveryPackageValidationError(
            "delivery package artifacts are invalid"
        )
    normalized_artifacts: dict[str, str] = {}
    for field in sorted(_ARTIFACT_REQUEST_KEYS):
        normalized_artifacts[field] = _strict_identifier(
            artifacts.get(field),
            field=f"artifacts.{field}",
            pattern=_ID_PATTERNS["artifact_id"],
        )
    if len(set(normalized_artifacts.values())) != len(normalized_artifacts):
        raise DeliveryPackageValidationError(
            "delivery package artifact identities must be distinct"
        )
    metadata = value.get("metadata")
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_KEYS:
        raise DeliveryPackageValidationError("delivery package metadata is invalid")
    title = _strict_text(
        metadata.get("title"),
        field="metadata.title",
        maximum=_MAX_TITLE_CHARS,
        allow_newline=False,
    )
    description = _strict_text(
        metadata.get("description"),
        field="metadata.description",
        maximum=_MAX_DESCRIPTION_CHARS,
        allow_newline=True,
    )
    return {
        "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
        "run_id": run_id,
        "source_job_id": source_job_id,
        "artifacts": normalized_artifacts,
        "metadata": {"title": title, "description": description},
    }


def delivery_request_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_delivery_package_payload(dict(value))
    metadata_json = canonical_json(normalized["metadata"]).encode("utf-8")
    return {
        "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
        "run_id": normalized["run_id"],
        "source_job_id": normalized["source_job_id"],
        "artifact_ids": dict(normalized["artifacts"]),
        "metadata_sha256": hashlib.sha256(metadata_json).hexdigest().upper(),
        "delivery_policy": DELIVERY_PACKAGE_POLICY,
    }


def _child_job(
    database: Any,
    run: Mapping[str, Any],
    source_result: Mapping[str, Any],
    *,
    production_id: str,
    stage: str,
) -> dict[str, Any]:
    children = source_result.get("children")
    if not isinstance(children, dict) or set(children) != set(_STAGES):
        raise DeliveryPackageValidationError(
            "source job child lineage is invalid", code="invalid_delivery_lineage"
        )
    view = children.get(stage)
    if (
        not isinstance(view, dict)
        or set(view)
        != {"stage", "status", "job_id", "stage_attempt_id", "cache_hit"}
        or view.get("stage") != stage
        or view.get("status") != "succeeded"
        or not isinstance(view.get("cache_hit"), bool)
    ):
        raise DeliveryPackageValidationError(
            "source job child lineage is invalid", code="invalid_delivery_lineage"
        )
    try:
        validate_identifier(view.get("job_id"), label="child job id")
        validate_identifier(view.get("stage_attempt_id"), label="stage attempt id")
    except (SecurityError, TypeError, ValueError) as exc:
        raise DeliveryPackageValidationError(
            "source job child lineage is invalid", code="invalid_delivery_lineage"
        ) from exc
    job = database.get_job(view["job_id"])
    payload = job.get("payload") if isinstance(job, dict) else None
    result = job.get("result") if isinstance(job, dict) else None
    if (
        not isinstance(job, dict)
        or job.get("kind") != _CHILD_KINDS[stage]
        or job.get("status") != "succeeded"
        or job.get("production_id") != production_id
        or not isinstance(payload, dict)
        or payload.get("production_id") != production_id
        or payload.get("run_id") != run.get("id")
        or payload.get("stage") != stage
        or payload.get("stage_attempt_id") != view["stage_attempt_id"]
        or not isinstance(result, dict)
        or result.get("stage_attempt_id") != view["stage_attempt_id"]
        or result.get("cache_hit") is not view["cache_hit"]
    ):
        raise DeliveryPackageValidationError(
            "source job child lineage is invalid", code="invalid_delivery_lineage"
        )
    attempts = run.get("stage_attempts")
    matches = (
        [item for item in attempts if isinstance(item, dict) and item.get("id") == view["stage_attempt_id"]]
        if isinstance(attempts, list)
        else []
    )
    if len(matches) != 1:
        raise DeliveryPackageValidationError(
            "source job stage attempt is unavailable", code="invalid_delivery_lineage"
        )
    attempt = matches[0]
    if (
        attempt.get("job_id") != job["id"]
        or attempt.get("run_id") != run.get("id")
        or attempt.get("production_id") != production_id
        or attempt.get("stage") != stage
        or attempt.get("status") != "succeeded"
        or attempt.get("result")
        != {key: item for key, item in result.items() if key != "stage_attempt_id"}
    ):
        raise DeliveryPackageValidationError(
            "source job stage attempt is invalid", code="invalid_delivery_lineage"
        )
    return job


def _artifact_owner_run_id(
    database: Any,
    run: Mapping[str, Any],
    child_job: Mapping[str, Any],
    *,
    production_id: str,
    stage: str,
) -> str:
    """Resolve the immutable owner attempt for a cache-linked stage result."""

    result = child_job.get("result")
    if not isinstance(result, dict):
        raise DeliveryPackageValidationError(
            "source job stage result is invalid", code="invalid_delivery_lineage"
        )
    current_result = {key: value for key, value in result.items() if key != "stage_attempt_id"}
    current_run_id = run.get("id")
    visited: set[str] = set()
    while current_result.get("cache_source_attempt_id") is not None:
        source_attempt_id = current_result.get("cache_source_attempt_id")
        try:
            validate_identifier(source_attempt_id, label="cache source attempt id")
        except (SecurityError, TypeError, ValueError) as exc:
            raise DeliveryPackageValidationError(
                "source job cache lineage is invalid",
                code="invalid_delivery_lineage",
            ) from exc
        if source_attempt_id in visited:
            raise DeliveryPackageValidationError(
                "source job cache lineage is cyclic",
                code="invalid_delivery_lineage",
            )
        visited.add(source_attempt_id)
        getter = getattr(database, "get_stage_attempt", None)
        source_attempt = getter(source_attempt_id) if callable(getter) else None
        source_result = (
            source_attempt.get("result")
            if isinstance(source_attempt, dict)
            else None
        )
        source_run_id = (
            source_attempt.get("run_id")
            if isinstance(source_attempt, dict)
            else None
        )
        try:
            validate_identifier(source_run_id, label="cache source run id")
        except (SecurityError, TypeError, ValueError) as exc:
            raise DeliveryPackageValidationError(
                "source job cache lineage is invalid",
                code="invalid_delivery_lineage",
            ) from exc
        source_run = database.get_run(source_run_id)
        if (
            not isinstance(source_attempt, dict)
            or source_attempt.get("id") != source_attempt_id
            or source_attempt.get("production_id") != production_id
            or source_attempt.get("stage") != stage
            or source_attempt.get("status") != "succeeded"
            or not isinstance(source_run, dict)
            or source_run.get("id") != source_run_id
            or source_run.get("production_id") != production_id
            or not isinstance(source_result, dict)
            or source_result.get("artifacts") != current_result.get("artifacts")
        ):
            raise DeliveryPackageValidationError(
                "source job cache lineage is invalid",
                code="invalid_delivery_lineage",
            )
        current_run_id = source_run_id
        current_result = source_result
    if not isinstance(current_run_id, str):
        raise DeliveryPackageValidationError(
            "source job cache owner is invalid", code="invalid_delivery_lineage"
        )
    return current_run_id


def _artifact_item(
    child_job: Mapping[str, Any], *, name: str, artifact_id: str
) -> dict[str, Any]:
    result = child_job.get("result")
    raw = result.get("artifacts") if isinstance(result, dict) else None
    matches = (
        [
            item
            for item in raw
            if isinstance(item, dict)
            and item.get("name") == name
            and item.get("id", item.get("artifact_id")) == artifact_id
        ]
        if isinstance(raw, list)
        else []
    )
    if len(matches) != 1:
        raise DeliveryPackageValidationError(
            f"required source artifact is unavailable: {name}",
            code="invalid_delivery_lineage",
        )
    return matches[0]


def _registered_artifact(
    database: Any,
    item: Mapping[str, Any],
    *,
    production_id: str,
    owner_run_id: str,
    artifact_id: str,
    name: str,
    kind: str,
    media_type: str,
) -> dict[str, Any]:
    artifact = database.get_artifact(artifact_id)
    if not isinstance(artifact, dict):
        raise DeliveryPackageValidationError(
            f"registered source artifact is unavailable: {name}",
            code="invalid_delivery_lineage",
        )
    relative = artifact.get("rel_path")
    digest = artifact.get("sha256")
    byte_count = artifact.get("bytes")
    if (
        artifact.get("id") != artifact_id
        or artifact.get("production_id") != production_id
        or artifact.get("origin") != "studio"
        or artifact.get("name") != name
        or artifact.get("kind") != kind
        or artifact.get("media_type") != media_type
        or artifact.get("available") is not True
        or not isinstance(relative, str)
        or not relative.startswith(f"outputs/studio/runs/{owner_run_id}/")
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or not 0 < byte_count <= _MAX_INPUT_BYTES
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest.upper()) is None
    ):
        raise DeliveryPackageValidationError(
            f"registered source artifact is invalid: {name}",
            code="invalid_delivery_lineage",
        )
    normalized_item = {
        "id": item.get("id", item.get("artifact_id")),
        "name": item.get("name"),
        "kind": item.get("kind"),
        "media_type": item.get("media_type", item.get("mime")),
        "rel_path": item.get("rel_path", item.get("path")),
        "bytes": item.get("bytes"),
        "sha256": str(item.get("sha256") or "").upper(),
    }
    expected_item = {
        "id": artifact["id"],
        "name": artifact["name"],
        "kind": artifact["kind"],
        "media_type": artifact["media_type"],
        "rel_path": artifact["rel_path"],
        "bytes": artifact["bytes"],
        "sha256": artifact["sha256"].upper(),
    }
    if normalized_item != expected_item:
        raise DeliveryPackageValidationError(
            f"source artifact identity changed: {name}",
            code="invalid_delivery_lineage",
        )
    return expected_item


def resolve_delivery_lineage(
    database: Any,
    production_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        validate_identifier(production_id, label="production id")
    except (SecurityError, TypeError, ValueError) as exc:
        raise DeliveryPackageValidationError("production_id is invalid") from exc
    normalized = validate_delivery_package_payload(dict(payload))
    production = database.get_production(production_id)
    run = database.get_run(normalized["run_id"])
    source_job = database.get_job(normalized["source_job_id"])
    source_payload = source_job.get("payload") if isinstance(source_job, dict) else None
    source_result = source_job.get("result") if isinstance(source_job, dict) else None
    if not isinstance(production, dict):
        raise DeliveryPackageValidationError(
            "production is unavailable", code="invalid_delivery_lineage"
        )
    if (
        not isinstance(run, dict)
        or run.get("id") != normalized["run_id"]
        or run.get("production_id") != production_id
    ):
        raise DeliveryPackageValidationError(
            "run does not belong to this production", code="invalid_delivery_lineage"
        )
    if (
        not isinstance(source_job, dict)
        or source_job.get("id") != normalized["source_job_id"]
        or source_job.get("kind") != "detailed_test_video"
        or source_job.get("status") != "succeeded"
        or source_job.get("production_id") != production_id
        or not isinstance(source_payload, dict)
        or source_payload.get("production_id") != production_id
        or source_payload.get("run_id") != run["id"]
        or source_payload.get("revision_id") != run.get("revision_id")
        or not isinstance(source_result, dict)
        or source_result.get("production_id") != production_id
        or source_result.get("run_id") != run["id"]
        or source_result.get("revision_id") != run.get("revision_id")
        or source_result.get("technical_verdict") != "pass"
        or source_result.get("include_captioned") is not True
    ):
        raise DeliveryPackageValidationError(
            "source job is not an exact successful detailed render",
            code="invalid_delivery_lineage",
        )
    duration_ms = source_result.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or not 1_000 <= duration_ms <= 60_000
    ):
        raise DeliveryPackageValidationError(
            "source duration is invalid", code="invalid_delivery_lineage"
        )
    child_jobs = {
        stage: _child_job(
            database,
            run,
            source_result,
            production_id=production_id,
            stage=stage,
        )
        for stage in _STAGES
    }
    artifact_owner_runs = {
        stage: _artifact_owner_run_id(
            database,
            run,
            child_jobs[stage],
            production_id=production_id,
            stage=stage,
        )
        for stage in _STAGES
    }
    resolved_artifacts: dict[str, dict[str, Any]] = {}
    for field, (stage, name, kind, media_type) in _EXPECTED_ARTIFACTS.items():
        artifact_id = normalized["artifacts"][field]
        item = _artifact_item(child_jobs[stage], name=name, artifact_id=artifact_id)
        resolved_artifacts[field] = _registered_artifact(
            database,
            item,
            production_id=production_id,
            owner_run_id=artifact_owner_runs[stage],
            artifact_id=artifact_id,
            name=name,
            kind=kind,
            media_type=media_type,
        )
    return {
        "production_id": production_id,
        "run_id": run["id"],
        "revision_id": run.get("revision_id"),
        "source_job_id": source_job["id"],
        "duration_ms": duration_ms,
        "metadata": dict(normalized["metadata"]),
        "artifacts": resolved_artifacts,
        "children": {
            stage: {
                "job_id": child_jobs[stage]["id"],
                "stage_attempt_id": source_result["children"][stage][
                    "stage_attempt_id"
                ],
            }
            for stage in _STAGES
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    method = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(method):
        method()


def _artifact_path(
    workspace: Path,
    artifact: Mapping[str, Any],
    *,
    verify_hash: bool,
) -> Path:
    relative = artifact.get("rel_path")
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise DeliveryPackageError("A delivery input is invalid.", code="input_changed")
    normalized = relative.replace("\\", "/")
    if (
        PurePosixPath(normalized).is_absolute()
        or bool(PureWindowsPath(normalized).drive)
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or sensitive_artifact_path(normalized)
    ):
        raise DeliveryPackageError("A delivery input is invalid.", code="input_changed")
    lexical = workspace.resolve(strict=True)
    for part in normalized.split("/"):
        lexical = lexical / part
        if lexical.is_symlink():
            raise DeliveryPackageError(
                "A delivery input is invalid.", code="input_changed"
            )
    try:
        path = workspace_path(workspace, normalized, must_exist=True)
        stat = path.stat()
    except (OSError, SecurityError) as exc:
        raise DeliveryPackageError(
            "A delivery input is unavailable.", code="input_changed"
        ) from exc
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.st_size != artifact.get("bytes")
    ):
        raise DeliveryPackageError("A delivery input changed.", code="input_changed")
    if verify_hash and _sha256_file(path) != artifact.get("sha256"):
        raise DeliveryPackageError("A delivery input changed.", code="input_changed")
    return path


def _audit_identity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(snapshot))
    # The receipt records when it was read, not a change to production inputs.
    # Keep that time in the exported snapshot, but exclude it from the before /
    # after packaging identity so two reads of unchanged data compare equal.
    value.pop("snapshot_at", None)
    artifacts = value.get("artifacts")
    if isinstance(artifacts, list):
        value["artifacts"] = [
            item
            for item in artifacts
            if not (isinstance(item, dict) and item.get("kind") == "delivery")
        ]
    events = value.get("events")
    if isinstance(events, list):
        filtered = []
        for event in events:
            payload = event.get("payload") if isinstance(event, dict) else None
            artifact = payload.get("artifact") if isinstance(payload, dict) else None
            if (
                isinstance(event, dict)
                and event.get("event_type") == "artifact.created"
                and (
                    payload.get("kind") == "delivery"
                    or (isinstance(artifact, dict) and artifact.get("kind") == "delivery")
                )
            ):
                continue
            filtered.append(event)
        value["events"] = filtered
    page = value.get("artifact_page")
    if isinstance(page, dict) and isinstance(value.get("artifacts"), list):
        page["total"] = len(value["artifacts"])
        page["total_bytes"] = sum(
            item.get("bytes", 0)
            for item in value["artifacts"]
            if isinstance(item, dict) and isinstance(item.get("bytes"), int)
        )
    return value


def validate_delivery_audit_snapshot(
    snapshot: Any, lineage: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    if not isinstance(snapshot, dict):
        raise DeliveryPackageError(
            "The production audit snapshot is unavailable.", code="input_changed"
        )
    production = snapshot.get("production")
    runs = snapshot.get("runs")
    artifacts = snapshot.get("artifacts")
    events = snapshot.get("events")
    if (
        not isinstance(production, dict)
        or production.get("id") != lineage.get("production_id")
        or not isinstance(runs, list)
        or len(
            [
                item
                for item in runs
                if isinstance(item, dict) and item.get("id") == lineage.get("run_id")
            ]
        )
        != 1
        or not isinstance(artifacts, list)
        or not isinstance(events, list)
    ):
        raise DeliveryPackageError(
            "The production audit snapshot is inconsistent.", code="input_changed"
        )
    expected_ids = {item["id"] for item in lineage["artifacts"].values()}
    snapshot_ids = {
        item.get("id") for item in artifacts if isinstance(item, dict)
    }
    if not expected_ids.issubset(snapshot_ids):
        raise DeliveryPackageError(
            "The production audit snapshot is incomplete.", code="input_changed"
        )
    try:
        canonical = canonical_json(snapshot).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DeliveryPackageError(
            "The production audit snapshot is invalid.", code="input_changed"
        ) from exc
    if len(canonical) > _MAX_AUDIT_BYTES:
        raise DeliveryPackageError(
            "The production audit snapshot is too large.", code="input_changed"
        )
    identity = canonical_json(_audit_identity(snapshot)).encode("utf-8")
    return dict(snapshot), hashlib.sha256(identity).hexdigest().upper()


def _fixed_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _add_bytes(
    archive: zipfile.ZipFile,
    entries: list[dict[str, Any]],
    name: str,
    value: bytes,
) -> None:
    archive.writestr(_fixed_zip_info(name), value)
    entries.append(
        {
            "path": name,
            "bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest().upper(),
        }
    )


def _add_file(
    archive: zipfile.ZipFile,
    entries: list[dict[str, Any]],
    name: str,
    source: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
    cancel_event: Any | None,
) -> None:
    digest = hashlib.sha256()
    byte_count = 0
    with source.open("rb") as input_handle, archive.open(
        _fixed_zip_info(name), "w", force_zip64=True
    ) as output_handle:
        while chunk := input_handle.read(1024 * 1024):
            _raise_if_cancelled(cancel_event)
            output_handle.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
    digest_hex = digest.hexdigest().upper()
    if byte_count != expected_bytes or digest_hex != expected_sha256:
        raise DeliveryPackageError("A delivery input changed.", code="input_changed")
    entries.append({"path": name, "bytes": byte_count, "sha256": digest_hex})


def _validate_png(path: Path) -> None:
    deadline = time.monotonic() + 2.0
    last_error: OSError | None = None
    stat = None
    signature: bytes | None = None
    while True:
        try:
            stat = path.stat()
            with path.open("rb") as handle:
                signature = handle.read(len(_PNG_SIGNATURE))
            break
        except OSError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    if stat is None or signature is None:
        raise DeliveryPackageError(
            "A delivery thumbnail could not be created.", code="delivery_package_failed"
        ) from last_error
    if (
        path.is_symlink()
        or not path.is_file()
        or not 32 <= stat.st_size <= _MAX_THUMBNAIL_BYTES
        or signature != _PNG_SIGNATURE
    ):
        raise DeliveryPackageError(
            "A delivery thumbnail is invalid.", code="delivery_package_failed"
        )


def _generate_thumbnails(
    ffmpeg: str,
    source: Path,
    output_directory: Path,
    duration_ms: int,
    *,
    cancel_event: Any | None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, numerator in enumerate((1, 2, 3), start=1):
        timestamp_ms = max(0, min(duration_ms - 1, (duration_ms * numerator) // 4))
        # Keep private worker paths deliberately short.  On Windows, FFmpeg can
        # create a file through a long path that the Python process cannot stat
        # without the host-wide long-path policy.  The public archive name is
        # applied below and is independent from this compact staging name.
        final = output_directory / f"{index:02d}.png"
        partial = output_directory / f"{index:02d}.part.png"
        _bounded_process(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                "1",
                "-i",
                str(source),
                "-ss",
                f"{timestamp_ms / 1000:.3f}",
                "-frames:v",
                "1",
                "-an",
                "-vf",
                "scale=720:-2:flags=lanczos",
                "-map_metadata",
                "-1",
                "-compression_level",
                "9",
                "-y",
                str(partial),
            ],
            cwd=output_directory,
            timeout=120.0,
            label=f"delivery thumbnail {index}",
            cancel_event=cancel_event,
        )
        _validate_png(partial)
        os.replace(partial, final)
        _validate_png(final)
        stat = final.stat()
        output.append(
            {
                "path": final,
                "name": f"thumbnail-{index:02d}.png",
                "timestamp_ms": timestamp_ms,
                "bytes": stat.st_size,
                "sha256": _sha256_file(final),
            }
        )
    return output


def _read_bounded_zip_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    maximum_bytes: int,
) -> bytes:
    if info.file_size < 0 or info.file_size > maximum_bytes:
        raise ValueError("archive entry is too large")
    output = bytearray()
    with archive.open(info, "r") as handle:
        while chunk := handle.read(min(1024 * 1024, maximum_bytes + 1 - len(output))):
            output.extend(chunk)
            if len(output) > maximum_bytes:
                raise ValueError("archive entry is too large")
    if len(output) != info.file_size:
        raise ValueError("archive entry size mismatch")
    return bytes(output)


def _verify_zip(
    path: Path,
    *,
    package_key: str,
    expected_package_identity: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        expected_identity = dict(expected_package_identity)
        calculated_key = hashlib.sha256(
            canonical_json(expected_identity).encode("utf-8")
        ).hexdigest().upper()
        if calculated_key != package_key:
            raise ValueError("package key mismatch")
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if (
                len(infos) != len(_EXPECTED_ZIP_NAMES)
                or len(names) != len(set(names))
                or set(names) != _EXPECTED_ZIP_NAMES
            ):
                raise ValueError("invalid entry names")
            info_by_name = {item.filename: item for item in infos}
            total_uncompressed = 0
            for info in infos:
                maximum = (
                    _MAX_DELIVERY_MANIFEST_BYTES
                    if info.filename == "delivery/manifest.json"
                    else _ARCHIVE_ENTRY_LIMITS[info.filename]
                )
                if (
                    info.is_dir()
                    or info.flag_bits & 0x1
                    or info.compress_type != zipfile.ZIP_DEFLATED
                    or info.file_size < 0
                    or info.file_size > maximum
                    or info.compress_size < 0
                    or (
                        info.file_size > 0
                        and (
                            info.compress_size == 0
                            or info.file_size
                            > info.compress_size * _MAX_ZIP_EXPANSION_RATIO
                        )
                    )
                ):
                    raise ValueError("invalid archive entry")
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise ValueError("archive is too large")
            manifest_bytes = _read_bounded_zip_entry(
                archive,
                info_by_name["delivery/manifest.json"],
                maximum_bytes=_MAX_DELIVERY_MANIFEST_BYTES,
            )
            manifest = json.loads(manifest_bytes)
            if not isinstance(manifest, dict):
                raise ValueError("manifest mismatch")
            entries = manifest.get("archive_entries")
            identity_keys = set(expected_identity)
            if (
                set(manifest)
                != identity_keys
                | {"package_key", "thumbnail_timestamps_ms", "archive_entries"}
                or {key: manifest.get(key) for key in identity_keys}
                != expected_identity
                or manifest.get("package_key") != package_key
                or hashlib.sha256(
                    canonical_json(
                        {key: manifest.get(key) for key in expected_identity}
                    ).encode("utf-8")
                ).hexdigest().upper()
                != package_key
                or manifest.get("thumbnail_timestamps_ms")
                != [
                    max(
                        0,
                        min(
                            int(expected_identity["duration_ms"]) - 1,
                            (int(expected_identity["duration_ms"]) * numerator) // 4,
                        ),
                    )
                    for numerator in (1, 2, 3)
                ]
                or not isinstance(entries, list)
                or len(entries) != len(_ARCHIVE_ENTRY_LIMITS)
                or set(_ARCHIVE_ENTRY_LIMITS)
                != {item.get("path") for item in entries if isinstance(item, dict)}
            ):
                raise ValueError("manifest mismatch")
            entry_records: dict[str, dict[str, Any]] = {}
            for expected in entries:
                if not isinstance(expected, dict) or set(expected) != {
                    "path",
                    "bytes",
                    "sha256",
                }:
                    raise ValueError("invalid manifest entry")
                entry_path = expected["path"]
                maximum = _ARCHIVE_ENTRY_LIMITS.get(entry_path)
                expected_bytes = expected["bytes"]
                expected_sha256 = expected["sha256"]
                if (
                    maximum is None
                    or not isinstance(expected_bytes, int)
                    or isinstance(expected_bytes, bool)
                    or expected_bytes < 0
                    or expected_bytes > maximum
                    or not isinstance(expected_sha256, str)
                    or _SHA256_RE.fullmatch(expected_sha256) is None
                    or info_by_name[entry_path].file_size != expected_bytes
                ):
                    raise ValueError("invalid manifest entry")
                entry_records[entry_path] = expected
                digest = hashlib.sha256()
                byte_count = 0
                with archive.open(info_by_name[entry_path], "r") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
                        byte_count += len(chunk)
                        if byte_count > maximum:
                            raise ValueError("archive entry is too large")
                if (
                    byte_count != expected_bytes
                    or digest.hexdigest().upper() != expected_sha256
                ):
                    raise ValueError("archive entry mismatch")

            identity_artifacts = expected_identity.get("artifacts")
            if not isinstance(identity_artifacts, dict):
                raise ValueError("artifact identity mismatch")
            for field, archive_path in _ARCHIVE_PATHS.items():
                artifact = identity_artifacts.get(field)
                record = entry_records.get(archive_path)
                if (
                    not isinstance(artifact, dict)
                    or record is None
                    or record["bytes"] != artifact.get("bytes")
                    or record["sha256"] != artifact.get("sha256")
                ):
                    raise ValueError("artifact identity mismatch")

            publication_bytes = _read_bounded_zip_entry(
                archive,
                info_by_name["metadata/publication.json"],
                maximum_bytes=_MAX_TEXT_ARTIFACT_BYTES,
            )
            publication = json.loads(publication_bytes)
            if publication != {
                "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
                "production_id": expected_identity.get("production_id"),
                "run_id": expected_identity.get("run_id"),
                "source_job_id": expected_identity.get("source_job_id"),
                "title": expected_identity.get("metadata", {}).get("title")
                if isinstance(expected_identity.get("metadata"), dict)
                else None,
                "description": expected_identity.get("metadata", {}).get(
                    "description"
                )
                if isinstance(expected_identity.get("metadata"), dict)
                else None,
            }:
                raise ValueError("publication metadata mismatch")

            snapshot_bytes = _read_bounded_zip_entry(
                archive,
                info_by_name["audit/production-snapshot.json"],
                maximum_bytes=_MAX_AUDIT_BYTES,
            )
            snapshot = json.loads(snapshot_bytes)
            if (
                not isinstance(snapshot, dict)
                or snapshot_bytes
                != (canonical_json(snapshot) + "\n").encode("utf-8")
                or hashlib.sha256(
                    canonical_json(_audit_identity(snapshot)).encode("utf-8")
                ).hexdigest().upper()
                != expected_identity.get("audit_snapshot_sha256")
            ):
                raise ValueError("audit snapshot mismatch")
            events = snapshot.get("events")
            if not isinstance(events, list):
                raise ValueError("audit event mismatch")
            events_bytes = _read_bounded_zip_entry(
                archive,
                info_by_name["audit/events.jsonl"],
                maximum_bytes=_MAX_AUDIT_BYTES,
            )
            if events_bytes != "".join(
                canonical_json(event) + "\n" for event in events
            ).encode("utf-8"):
                raise ValueError("audit event mismatch")
            for index in (1, 2, 3):
                with archive.open(
                    info_by_name[f"thumbnails/thumbnail-{index:02d}.png"], "r"
                ) as handle:
                    if handle.read(len(_PNG_SIGNATURE)) != _PNG_SIGNATURE:
                        raise ValueError("thumbnail mismatch")
            return manifest
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise DeliveryPackageError(
            "The delivery package failed verification.", code="delivery_package_failed"
        ) from exc


def _package_record(
    workspace: Path,
    production_id: str,
    package: Path,
) -> dict[str, Any]:
    stat = package.stat()
    relative = package.relative_to(workspace.resolve(strict=True)).as_posix()
    return {
        "id": stable_id("art", relative.casefold()),
        "rel_path": relative,
        "name": package.name,
        "kind": "delivery",
        "media_type": "application/zip",
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _sha256_file(package),
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
        "production_id": production_id,
    }


def create_delivery_package(
    workspace: Path,
    *,
    production_id: str,
    job_id: str,
    lineage: Mapping[str, Any],
    audit_snapshot: Mapping[str, Any],
    cancel_event: Any | None = None,
    ffmpeg: str | Path | None = None,
) -> dict[str, Any]:
    try:
        validate_identifier(production_id, label="production id")
        validate_identifier(job_id, label="job id")
    except (SecurityError, TypeError, ValueError) as exc:
        raise DeliveryPackageError(
            "The delivery package identity is invalid.", code="invalid_worker_result"
        ) from exc
    _raise_if_cancelled(cancel_event)
    snapshot, audit_digest = validate_delivery_audit_snapshot(audit_snapshot, lineage)
    source_paths = {
        key: _artifact_path(workspace, artifact, verify_hash=True)
        for key, artifact in lineage["artifacts"].items()
    }
    try:
        ffmpeg_executable = _find_tool("ffmpeg", ffmpeg)
        raw_tool_identity = _tool_identity(
            "ffmpeg", ffmpeg_executable, cancel_event=cancel_event
        )
        ffmpeg_executable = raw_tool_identity["path"]
    except AssemblyError as exc:
        raise DeliveryPackageError(
            "The local FFmpeg tool is unavailable.", code="local_ffmpeg_failed"
        ) from exc
    tool_identity = {
        "version": raw_tool_identity["version"],
        "sha256": raw_tool_identity["sha256"],
    }
    package_identity = {
        "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
        "policy": DELIVERY_PACKAGE_POLICY,
        "thumbnail_policy": DELIVERY_THUMBNAIL_POLICY,
        "audit_policy": DELIVERY_AUDIT_POLICY,
        "production_id": production_id,
        "run_id": lineage["run_id"],
        "revision_id": lineage["revision_id"],
        "source_job_id": lineage["source_job_id"],
        "duration_ms": lineage["duration_ms"],
        "metadata": lineage["metadata"],
        "artifacts": lineage["artifacts"],
        "children": lineage["children"],
        "audit_snapshot_sha256": audit_digest,
        "ffmpeg": tool_identity,
    }
    package_key = hashlib.sha256(
        canonical_json(package_identity).encode("utf-8")
    ).hexdigest().upper()
    root = workspace_path(workspace, "outputs/studio/deliveries")
    production_root = workspace_path(workspace, root / production_id)
    destination = workspace_path(workspace, production_root / package_key)
    package = workspace_path(workspace, destination / "delivery-package.zip")
    sidecar = workspace_path(workspace, destination / "delivery-package.zip.sha256")
    for directory in (root, production_root):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise DeliveryPackageError(
                "The delivery output directory is invalid.", code="publish_failed"
            )
        directory.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise DeliveryPackageError(
                "The delivery output is invalid.", code="publish_failed"
            )
        manifest = _verify_zip(
            package,
            package_key=package_key,
            expected_package_identity=package_identity,
        )
        digest = _sha256_file(package)
        try:
            expected_sidecar = f"{digest} *{package.name}\n"
            if sidecar.read_text(encoding="ascii") != expected_sidecar:
                raise OSError("sidecar mismatch")
        except OSError as exc:
            raise DeliveryPackageError(
                "The delivery package sidecar is invalid.", code="delivery_package_failed"
            ) from exc
        return {
            "artifact_record": _package_record(workspace, production_id, package),
            "sha256_sidecar": sidecar.relative_to(workspace).as_posix(),
            "package_key": package_key,
            "files_included": len(manifest["archive_entries"]) + 1,
            "thumbnail_count": 3,
            "cache_hit": True,
            "created": False,
        }

    # A compact, collision-resistant private directory avoids MAX_PATH races
    # while retaining deterministic cleanup for one package/job invocation.
    stage_key = hashlib.sha256(f"{package_key}:{job_id}".encode("ascii")).hexdigest()[
        :24
    ]
    stage = workspace_path(workspace, production_root / f".tmp-{stage_key}")
    if stage.exists():
        raise DeliveryPackageError(
            "A private delivery stage already exists.", code="publish_failed"
        )
    stage.mkdir()
    published = False
    completed = False
    try:
        thumbnails_directory = stage / "t"
        thumbnails_directory.mkdir()
        thumbnails = _generate_thumbnails(
            ffmpeg_executable,
            source_paths["clean_master"],
            thumbnails_directory,
            lineage["duration_ms"],
            cancel_event=cancel_event,
        )
        _artifact_path(workspace, lineage["artifacts"]["clean_master"], verify_hash=True)
        audit_json = (canonical_json(snapshot) + "\n").encode("utf-8")
        event_lines = "".join(
            canonical_json(event) + "\n" for event in snapshot.get("events", [])
        ).encode("utf-8")
        publication = {
            "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
            "production_id": production_id,
            "run_id": lineage["run_id"],
            "source_job_id": lineage["source_job_id"],
            "title": lineage["metadata"]["title"],
            "description": lineage["metadata"]["description"],
        }
        temporary_zip = stage / "delivery-package.zip.partial"
        archive_entries: list[dict[str, Any]] = []
        with zipfile.ZipFile(
            temporary_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for field in (
                "clean_master",
                "captioned_master",
                "captions",
                "technical_qc",
                "qc_ffprobe",
                "qc_manifest",
            ):
                artifact = lineage["artifacts"][field]
                if field in {"captions", "technical_qc", "qc_ffprobe", "qc_manifest"}:
                    if artifact["bytes"] > _MAX_TEXT_ARTIFACT_BYTES:
                        raise DeliveryPackageError(
                            "A delivery text input is too large.", code="input_changed"
                        )
                    try:
                        source_paths[field].read_text(encoding="utf-8")
                        if field != "captions":
                            json.loads(source_paths[field].read_text(encoding="utf-8"))
                    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise DeliveryPackageError(
                            "A delivery text input is invalid.", code="input_changed"
                        ) from exc
                _add_file(
                    archive,
                    archive_entries,
                    _ARCHIVE_PATHS[field],
                    source_paths[field],
                    expected_bytes=artifact["bytes"],
                    expected_sha256=artifact["sha256"],
                    cancel_event=cancel_event,
                )
            for thumbnail in thumbnails:
                _add_file(
                    archive,
                    archive_entries,
                    f"thumbnails/{thumbnail['name']}",
                    thumbnail["path"],
                    expected_bytes=thumbnail["bytes"],
                    expected_sha256=thumbnail["sha256"],
                    cancel_event=cancel_event,
                )
            _add_bytes(
                archive,
                archive_entries,
                "metadata/publication.json",
                (canonical_json(publication) + "\n").encode("utf-8"),
            )
            _add_bytes(
                archive,
                archive_entries,
                "audit/production-snapshot.json",
                audit_json,
            )
            _add_bytes(
                archive,
                archive_entries,
                "audit/events.jsonl",
                event_lines,
            )
            manifest = {
                **package_identity,
                "package_key": package_key,
                "thumbnail_timestamps_ms": [
                    item["timestamp_ms"] for item in thumbnails
                ],
                "archive_entries": archive_entries,
            }
            archive.writestr(
                _fixed_zip_info("delivery/manifest.json"),
                (canonical_json(manifest) + "\n").encode("utf-8"),
            )
        final_zip = stage / "delivery-package.zip"
        os.replace(temporary_zip, final_zip)
        _verify_zip(
            final_zip,
            package_key=package_key,
            expected_package_identity=package_identity,
        )
        package_digest = _sha256_file(final_zip)
        sidecar_stage = stage / "delivery-package.zip.sha256.partial"
        sidecar_stage.write_text(
            f"{package_digest} *delivery-package.zip\n",
            encoding="ascii",
            newline="\n",
        )
        os.replace(sidecar_stage, stage / "delivery-package.zip.sha256")
        _raise_if_cancelled(cancel_event)
        shutil.rmtree(thumbnails_directory)
        os.replace(stage, destination)
        published = True
        manifest = _verify_zip(
            package,
            package_key=package_key,
            expected_package_identity=package_identity,
        )
        if _sha256_file(package) != package_digest:
            raise DeliveryPackageError(
                "The published delivery package changed.", code="publish_failed"
            )
        if sidecar.read_text(encoding="ascii") != (
            f"{package_digest} *delivery-package.zip\n"
        ):
            raise DeliveryPackageError(
                "The published delivery sidecar changed.", code="publish_failed"
            )
        result = {
            "artifact_record": _package_record(workspace, production_id, package),
            "sha256_sidecar": sidecar.relative_to(workspace).as_posix(),
            "package_key": package_key,
            "files_included": len(manifest["archive_entries"]) + 1,
            "thumbnail_count": len(thumbnails),
            "cache_hit": False,
            "created": True,
        }
        completed = True
        return result
    except AssemblyError as exc:
        raise DeliveryPackageError(
            "A delivery thumbnail could not be created.", code="local_ffmpeg_failed"
        ) from exc
    except DeliveryPackageError:
        raise
    except Exception as exc:
        raise DeliveryPackageError() from exc
    finally:
        if not completed:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            if published and destination.exists() and not destination.is_symlink():
                shutil.rmtree(destination, ignore_errors=True)


def remove_created_delivery_package(
    workspace: Path, result: Mapping[str, Any]
) -> None:
    if result.get("created") is not True:
        return
    artifact = result.get("artifact_record")
    relative = artifact.get("rel_path") if isinstance(artifact, dict) else None
    if not isinstance(relative, str):
        return
    try:
        package = workspace_path(workspace, relative, must_exist=True)
        destination = package.parent
        deliveries = workspace_path(workspace, "outputs/studio/deliveries")
        destination.relative_to(deliveries)
        if package.name != "delivery-package.zip" or destination.is_symlink():
            return
        shutil.rmtree(destination)
    except (OSError, SecurityError, ValueError):
        return


__all__ = [
    "DELIVERY_PACKAGE_JOB_KIND",
    "DELIVERY_PACKAGE_POLICY",
    "DELIVERY_PACKAGE_SCHEMA_VERSION",
    "DeliveryPackageError",
    "DeliveryPackageValidationError",
    "create_delivery_package",
    "delivery_request_audit",
    "remove_created_delivery_package",
    "resolve_delivery_lineage",
    "validate_delivery_audit_snapshot",
    "validate_delivery_package_payload",
]
