from __future__ import annotations

"""Fail-closed execution boundary for local ElevenLabs scene alignment.

The public request selects one already-succeeded narration attempt and a
closed HOOK -> MESSAGE -> CTA schedule.  This module never calls a provider,
loads a credential, or authorizes spend.  It resolves the registered source
artifacts from the database, verifies their current workspace bytes, invokes
the pure-local alignment worker, and separates a path-free public result from
the records that may be passed to ``complete_job_with_stage_attempt``.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .external_tts_execution import (
    EXTERNAL_TTS_PROVIDER,
    EXTERNAL_TTS_TIMING_SOURCE,
)
from .security import (
    canonical_json,
    relative_workspace_path,
    sensitive_artifact_path,
    stable_id,
    workspace_path,
)
from .voice_upgrade import (
    VOICE_UPGRADE_IMPLEMENTATION_VERSION,
    VOICE_UPGRADE_SCHEDULE_POLICY,
    VoiceUpgradeError,
    align_external_tts_to_scene_schedule,
    validate_scene_schedule,
    voice_upgrade_cache_key,
    voice_upgrade_schedule_digest,
)


VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION = 1
VOICE_UPGRADE_EXECUTION_PROVIDER = "local_voice_upgrade"

MAX_SOURCE_ARTIFACTS = 16
MAX_SOURCE_WAV_BYTES = 128 * 1024 * 1024
MAX_SOURCE_METADATA_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_ARTIFACT_BYTES = 128 * 1024 * 1024

_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{32}$")
_PRODUCTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")

_REQUEST_KEYS = frozenset({"schema_version", "source_attempt_id", "schedule"})
_SOURCE_NAMES = frozenset({"narration.wav", "timings.json"})
_SOURCE_SPECS: dict[str, tuple[str, str, int]] = {
    "narration.wav": ("audio", "audio/wav", MAX_SOURCE_WAV_BYTES),
    "timings.json": (
        "document",
        "application/json",
        MAX_SOURCE_METADATA_BYTES,
    ),
}
_OUTPUT_SPECS: dict[str, tuple[str, str]] = {
    "narration.wav": ("audio", "audio/wav"),
    "captions.srt": ("subtitle", "application/x-subrip"),
    "timings.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_RESULT_ARTIFACT_STABLE_FIELDS = (
    "id",
    "production_id",
    "rel_path",
    "origin",
    "name",
    "kind",
    "media_type",
    "bytes",
    "mtime_ns",
    "sha256",
    "is_heavy",
    "available",
)
_RAW_RESULT_KEYS = frozenset(
    {
        "artifacts",
        "cache_key",
        "cache_hit",
        "duration_ms",
        "provider",
        "timing_source",
        "timing_policy",
        "schedule_sha256",
        "segment_start_ms",
    }
)
_RAW_ARTIFACT_KEYS = frozenset(
    {
        "kind",
        "path",
        "rel_path",
        "name",
        "bytes",
        "sha256",
        "mime",
        "media_type",
        "origin",
        "version",
        "available",
        "is_heavy",
    }
)
_PUBLIC_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "artifacts",
        "cache_key",
        "cache_hit",
        "duration_ms",
        "provider",
        "provider_task_id",
        "actual_cost",
        "timing_source",
        "timing_policy",
        "schedule_sha256",
        "segment_start_ms",
        "source_lineage",
        "cost",
    }
)
_SOURCE_LINEAGE_KEYS = frozenset(
    {
        "schema_version",
        "production_id",
        "run_id",
        "source_attempt_id",
        "source_cache_key",
        "source_provider",
        "source_timing_source",
        "source_artifacts",
        "source_binding_digest",
    }
)


class VoiceUpgradeExecutionError(RuntimeError):
    """A bounded failure safe to expose at a local job boundary."""

    error_code = "voice_upgrade_execution_failed"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = message


@dataclass(frozen=True)
class ResolvedVoiceUpgradeSource:
    """Verified private paths plus the path-free lineage safe to persist."""

    request: dict[str, Any]
    cache_key: str
    source_wav: Path
    source_timings: Path
    source_wav_sha256: str
    source_timings_sha256: str
    lineage: dict[str, Any]


@dataclass(frozen=True)
class VoiceUpgradeExecutionOutcome:
    """Worker output split for atomic stage/artifact completion."""

    public_result: dict[str, Any]
    artifact_records: tuple[dict[str, Any], ...]


def _raise(message: str, *, code: str) -> None:
    raise VoiceUpgradeExecutionError(message, code=code)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _raise(f"{label} is invalid.", code="voice_upgrade_source_changed")
    return value


def _valid_identifier(value: Any, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _has_symlink_component(workspace: Path, relative: str) -> bool:
    cursor = workspace.resolve(strict=True)
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts:
        return True
    for part in path.parts:
        if part in {"", ".", ".."}:
            return True
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _checked_file(
    workspace: Path,
    relative: str,
    *,
    expected_bytes: int,
    expected_mtime_ns: int,
    expected_sha256: str,
    maximum_bytes: int,
) -> Path:
    if (
        not isinstance(relative, str)
        or sensitive_artifact_path(relative)
        or _has_symlink_component(workspace, relative)
        or isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or expected_bytes > maximum_bytes
        or isinstance(expected_mtime_ns, bool)
        or not isinstance(expected_mtime_ns, int)
        or expected_mtime_ns < 0
    ):
        _raise(
            "A voice-upgrade source artifact is unsafe.",
            code="voice_upgrade_source_changed",
        )
    digest = _sha256(expected_sha256, label="source artifact SHA-256")
    try:
        path = workspace_path(workspace, relative, must_exist=True)
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular file")
        before = path.stat()
        actual_digest = _sha256_file(path)
        after = path.stat()
        if (
            before.st_size != expected_bytes
            or before.st_mtime_ns != expected_mtime_ns
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or actual_digest != digest
            or relative_workspace_path(workspace, path) != relative
        ):
            raise OSError("source changed")
    except (OSError, RuntimeError, ValueError) as exc:
        raise VoiceUpgradeExecutionError(
            "A voice-upgrade source artifact changed after registration.",
            code="voice_upgrade_source_changed",
        ) from exc
    return path


def validate_voice_upgrade_execution_request(body: Any) -> dict[str, Any]:
    """Validate the exact public, path-free request."""

    if not isinstance(body, dict) or set(body) != _REQUEST_KEYS:
        _raise(
            "The voice-upgrade execution request is invalid.",
            code="invalid_voice_upgrade_execution_request",
        )
    if (
        type(body.get("schema_version")) is not int
        or body.get("schema_version") != VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION
        or not _valid_identifier(body.get("source_attempt_id"), _ATTEMPT_ID_RE)
    ):
        _raise(
            "The voice-upgrade execution request is invalid.",
            code="invalid_voice_upgrade_execution_request",
        )
    try:
        schedule = validate_scene_schedule(body.get("schedule"))
    except VoiceUpgradeError as exc:
        raise VoiceUpgradeExecutionError(
            str(exc), code="invalid_voice_upgrade_execution_request"
        ) from exc
    return {
        "schema_version": VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION,
        "source_attempt_id": body["source_attempt_id"],
        "schedule": schedule,
    }


def _registered_source_artifacts(
    workspace: Path,
    database: Any,
    *,
    production_id: str,
    run_id: str,
    source_cache_key: str,
    raw_artifacts: Any,
) -> dict[str, dict[str, Any]]:
    if (
        not isinstance(raw_artifacts, list)
        or not 2 <= len(raw_artifacts) <= MAX_SOURCE_ARTIFACTS
    ):
        _raise(
            "The source narration artifact set is invalid.",
            code="voice_upgrade_source_changed",
        )
    expected_root = (
        f"outputs/studio/runs/{run_id}/narration/{source_cache_key}/"
    )
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    sources: dict[str, dict[str, Any]] = {}
    for item in raw_artifacts:
        if not isinstance(item, dict):
            _raise(
                "The source narration artifact set is invalid.",
                code="voice_upgrade_source_changed",
            )
        artifact_id = item.get("id")
        name = item.get("name")
        if (
            not _valid_identifier(artifact_id, _ARTIFACT_ID_RE)
            or not isinstance(name, str)
            or name in seen_names
            or artifact_id in seen_ids
        ):
            _raise(
                "The source narration artifact set is ambiguous.",
                code="voice_upgrade_source_changed",
            )
        seen_ids.add(artifact_id)
        seen_names.add(name)
        if name not in _SOURCE_NAMES:
            continue
        getter = getattr(database, "get_artifact", None)
        current = getter(artifact_id) if callable(getter) else None
        if not isinstance(current, dict) or any(
            current.get(field) != item.get(field)
            for field in _RESULT_ARTIFACT_STABLE_FIELDS
        ):
            _raise(
                "A source narration artifact no longer matches its registry record.",
                code="voice_upgrade_source_changed",
            )
        kind, media_type, maximum_bytes = _SOURCE_SPECS[name]
        expected_relative = f"{expected_root}{name}"
        recorded_bytes = current.get("bytes")
        if (
            current.get("production_id") != production_id
            or current.get("origin") != "studio"
            or current.get("name") != name
            or current.get("kind") != kind
            or current.get("media_type") != media_type
            or current.get("rel_path") != expected_relative
            or current.get("available") is not True
            or isinstance(recorded_bytes, bool)
            or not isinstance(recorded_bytes, int)
            or recorded_bytes <= 0
            or recorded_bytes > maximum_bytes
            or current.get("is_heavy")
            is not (recorded_bytes > 10 * 1024 * 1024)
        ):
            _raise(
                "A source narration artifact has invalid lineage.",
                code="voice_upgrade_source_changed",
            )
        path = _checked_file(
            workspace,
            expected_relative,
            expected_bytes=current.get("bytes"),
            expected_mtime_ns=current.get("mtime_ns"),
            expected_sha256=current.get("sha256"),
            maximum_bytes=maximum_bytes,
        )
        sources[name] = {"record": current, "path": path}
    if set(sources) != _SOURCE_NAMES:
        _raise(
            "The source narration artifact set is incomplete.",
            code="voice_upgrade_source_changed",
        )
    return sources


def resolve_voice_upgrade_source(
    workspace: Path,
    database: Any,
    production_id: str,
    run_id: str,
    request: Any,
) -> ResolvedVoiceUpgradeSource:
    """Resolve one exact succeeded external-narration attempt and its bytes."""

    workspace = workspace.resolve(strict=True)
    normalized = validate_voice_upgrade_execution_request(request)
    if (
        not _valid_identifier(production_id, _PRODUCTION_ID_RE)
        or not _valid_identifier(run_id, _RUN_ID_RE)
    ):
        _raise(
            "The voice-upgrade source identity is invalid.",
            code="voice_upgrade_source_required",
        )
    get_run = getattr(database, "get_run", None)
    get_attempt = getattr(database, "get_stage_attempt", None)
    run = get_run(run_id) if callable(get_run) else None
    attempt = (
        get_attempt(normalized["source_attempt_id"])
        if callable(get_attempt)
        else None
    )
    if (
        not isinstance(run, dict)
        or run.get("id") != run_id
        or run.get("production_id") != production_id
        or run.get("execution_profile") != "elevenlabs_tts"
        or not isinstance(run.get("requested_stages"), list)
        or "narration" not in run["requested_stages"]
        or not isinstance(attempt, dict)
        or attempt.get("id") != normalized["source_attempt_id"]
        or attempt.get("run_id") != run_id
        or attempt.get("production_id") != production_id
        or attempt.get("stage") != "narration"
        or attempt.get("status") != "succeeded"
        or not isinstance(attempt.get("result"), dict)
    ):
        _raise(
            "A succeeded ElevenLabs narration attempt is required.",
            code="voice_upgrade_source_required",
        )
    source_cache_key = attempt.get("cache_key")
    result = attempt["result"]
    if (
        not isinstance(source_cache_key, str)
        or _SHA256_RE.fullmatch(source_cache_key) is None
        or result.get("provider") != EXTERNAL_TTS_PROVIDER
        or result.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or result.get("cache_key") != source_cache_key
        or result.get("request_cache_key") != source_cache_key
        or not isinstance(result.get("cache_hit"), bool)
    ):
        _raise(
            "The source narration result has invalid lineage.",
            code="voice_upgrade_source_changed",
        )
    sources = _registered_source_artifacts(
        workspace,
        database,
        production_id=production_id,
        run_id=run_id,
        source_cache_key=source_cache_key,
        raw_artifacts=result.get("artifacts"),
    )
    wav = sources["narration.wav"]
    timings = sources["timings.json"]
    source_wav_sha256 = str(wav["record"]["sha256"])
    source_timings_sha256 = str(timings["record"]["sha256"])
    cache_key = voice_upgrade_cache_key(
        normalized["schedule"],
        source_wav_sha256=source_wav_sha256,
        source_timings_sha256=source_timings_sha256,
    )
    lineage_body = {
        "schema_version": VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "source_attempt_id": attempt["id"],
        "source_cache_key": source_cache_key,
        "source_provider": EXTERNAL_TTS_PROVIDER,
        "source_timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "source_artifacts": {
            name: {
                "artifact_id": sources[name]["record"]["id"],
                "bytes": sources[name]["record"]["bytes"],
                "sha256": sources[name]["record"]["sha256"],
            }
            for name in sorted(_SOURCE_NAMES)
        },
    }
    lineage = {
        **lineage_body,
        "source_binding_digest": hashlib.sha256(
            canonical_json(lineage_body).encode("utf-8")
        ).hexdigest().upper(),
    }
    return ResolvedVoiceUpgradeSource(
        request=normalized,
        cache_key=cache_key,
        source_wav=wav["path"],
        source_timings=timings["path"],
        source_wav_sha256=source_wav_sha256,
        source_timings_sha256=source_timings_sha256,
        lineage=lineage,
    )


def _validated_output_artifacts(
    workspace: Path,
    run_id: str,
    cache_key: str,
    value: Any,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) != len(_OUTPUT_SPECS):
        _raise(
            "The voice-upgrade worker returned an invalid artifact set.",
            code="invalid_voice_upgrade_worker_result",
        )
    expected_root = f"outputs/studio/runs/{run_id}/narration/{cache_key}/"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != _RAW_ARTIFACT_KEYS:
            _raise(
                "The voice-upgrade worker returned an invalid artifact.",
                code="invalid_voice_upgrade_worker_result",
            )
        name = item.get("name")
        if not isinstance(name, str) or name in seen or name not in _OUTPUT_SPECS:
            _raise(
                "The voice-upgrade worker returned an unexpected artifact.",
                code="invalid_voice_upgrade_worker_result",
            )
        seen.add(name)
        expected_kind, expected_media_type = _OUTPUT_SPECS[name]
        relative = f"{expected_root}{name}"
        raw_bytes = item.get("bytes")
        raw_sha256 = item.get("sha256")
        if (
            item.get("path") != relative
            or item.get("rel_path") != relative
            or item.get("kind") != expected_kind
            or item.get("mime") != expected_media_type
            or item.get("media_type") != expected_media_type
            or item.get("origin") != "studio"
            or item.get("version") != VOICE_UPGRADE_IMPLEMENTATION_VERSION
            or item.get("available") is not True
            or isinstance(raw_bytes, bool)
            or not isinstance(raw_bytes, int)
            or raw_bytes <= 0
            or raw_bytes > MAX_OUTPUT_ARTIFACT_BYTES
            or item.get("is_heavy") is not (raw_bytes > 10 * 1024 * 1024)
            or not isinstance(raw_sha256, str)
            or _SHA256_RE.fullmatch(raw_sha256) is None
            or sensitive_artifact_path(relative)
            or _has_symlink_component(workspace, relative)
        ):
            _raise(
                "The voice-upgrade worker returned invalid artifact metadata.",
                code="invalid_voice_upgrade_worker_result",
            )
        try:
            path = workspace_path(workspace, relative, must_exist=True)
            if path.is_symlink() or not path.is_file():
                raise OSError("not a regular file")
            before = path.stat()
            digest = _sha256_file(path)
            after = path.stat()
            if (
                before.st_size != raw_bytes
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or digest != raw_sha256
                or relative_workspace_path(workspace, path) != relative
            ):
                raise OSError("artifact changed")
        except (OSError, RuntimeError, ValueError) as exc:
            raise VoiceUpgradeExecutionError(
                "A voice-upgrade output artifact is invalid.",
                code="invalid_voice_upgrade_worker_result",
            ) from exc
        records.append(
            {
                "id": stable_id("art", relative.casefold()),
                "rel_path": relative,
                "name": name,
                "kind": expected_kind,
                "media_type": expected_media_type,
                "bytes": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "sha256": digest,
                "is_heavy": before.st_size > 10 * 1024 * 1024,
            }
        )
    if seen != set(_OUTPUT_SPECS):
        _raise(
            "The voice-upgrade worker returned an incomplete artifact set.",
            code="invalid_voice_upgrade_worker_result",
        )
    return tuple(sorted(records, key=lambda item: item["name"]))


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    method = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(method):
        method()
        return
    is_set = getattr(cancel_event, "is_set", None)
    if callable(is_set) and is_set():
        _raise("The voice-upgrade job was cancelled.", code="job_cancelled")


def execute_voice_upgrade(
    workspace: Path,
    database: Any,
    production_id: str,
    run_id: str,
    request: Any,
    *,
    cancel_event: Any | None = None,
) -> VoiceUpgradeExecutionOutcome:
    """Re-resolve, align locally, and return atomically registerable output."""

    _raise_if_cancelled(cancel_event)
    resolved = resolve_voice_upgrade_source(
        workspace, database, production_id, run_id, request
    )
    _raise_if_cancelled(cancel_event)
    output_root = (
        Path("outputs") / "studio" / "runs" / run_id / "narration"
    )
    try:
        raw = align_external_tts_to_scene_schedule(
            workspace,
            source_wav=resolved.source_wav,
            source_timings=resolved.source_timings,
            output_root=output_root,
            source_wav_sha256=resolved.source_wav_sha256,
            source_timings_sha256=resolved.source_timings_sha256,
            schedule=resolved.request["schedule"],
        )
    except VoiceUpgradeError as exc:
        raise VoiceUpgradeExecutionError(str(exc), code=exc.error_code) from exc
    _raise_if_cancelled(cancel_event)

    # Re-resolve after local publication as well.  A DB or source-byte race
    # may leave an unregistered content-addressed cache, but it can never
    # produce register-ready records with stale lineage.
    final_source = resolve_voice_upgrade_source(
        workspace, database, production_id, run_id, request
    )
    if (
        final_source.cache_key != resolved.cache_key
        or final_source.lineage != resolved.lineage
    ):
        _raise(
            "The voice-upgrade source changed during execution.",
            code="voice_upgrade_source_changed",
        )
    if not isinstance(raw, dict) or set(raw) != _RAW_RESULT_KEYS:
        _raise(
            "The voice-upgrade worker returned an invalid result.",
            code="invalid_voice_upgrade_worker_result",
        )
    schedule = resolved.request["schedule"]
    schedule_sha256 = voice_upgrade_schedule_digest(schedule)
    expected_starts = [scene["start_ms"] for scene in schedule["scenes"]]
    if (
        raw.get("cache_key") != resolved.cache_key
        or not isinstance(raw.get("cache_hit"), bool)
        or raw.get("duration_ms") != schedule["total_duration_ms"]
        or raw.get("provider") != EXTERNAL_TTS_PROVIDER
        or raw.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or raw.get("timing_policy") != VOICE_UPGRADE_SCHEDULE_POLICY
        or raw.get("schedule_sha256") != schedule_sha256
        or raw.get("segment_start_ms") != expected_starts
    ):
        _raise(
            "The voice-upgrade worker returned mismatched provenance.",
            code="invalid_voice_upgrade_worker_result",
        )
    artifact_records = _validated_output_artifacts(
        workspace, run_id, resolved.cache_key, raw.get("artifacts")
    )
    public_result = {
        "schema_version": VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION,
        "artifacts": [],
        "cache_key": resolved.cache_key,
        "cache_hit": raw["cache_hit"],
        "duration_ms": raw["duration_ms"],
        "provider": VOICE_UPGRADE_EXECUTION_PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": raw["timing_source"],
        "timing_policy": raw["timing_policy"],
        "schedule_sha256": schedule_sha256,
        "segment_start_ms": list(expected_starts),
        "source_lineage": resolved.lineage,
        "cost": {
            "amount": "0.00",
            "currency": "USD",
            "source": "local",
        },
    }
    return VoiceUpgradeExecutionOutcome(
        public_result=public_result,
        artifact_records=artifact_records,
    )


def validate_voice_upgrade_public_result(
    value: Any,
    *,
    expected_production_id: str,
    expected_run_id: str,
    expected_cache_key: str,
    artifacts: Any,
) -> dict[str, Any]:
    """Revalidate a registered local upgrade before downstream assembly."""

    if not isinstance(value, dict) or set(value) != _PUBLIC_RESULT_KEYS:
        _raise(
            "The voice-upgrade result is invalid.",
            code="invalid_voice_upgrade_worker_result",
        )
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION
        or value.get("cache_key") != expected_cache_key
        or not isinstance(expected_cache_key, str)
        or _SHA256_RE.fullmatch(expected_cache_key) is None
        or not isinstance(value.get("cache_hit"), bool)
        or isinstance(value.get("duration_ms"), bool)
        or not isinstance(value.get("duration_ms"), int)
        or not 1 <= value["duration_ms"] <= 60_000
        or value.get("provider") != VOICE_UPGRADE_EXECUTION_PROVIDER
        or value.get("provider_task_id") is not None
        or isinstance(value.get("actual_cost"), bool)
        or value.get("actual_cost") != 0
        or value.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or value.get("timing_policy") != VOICE_UPGRADE_SCHEDULE_POLICY
        or not isinstance(value.get("schedule_sha256"), str)
        or _SHA256_RE.fullmatch(value["schedule_sha256"]) is None
        or value.get("cost")
        != {"amount": "0.00", "currency": "USD", "source": "local"}
        or not isinstance(artifacts, list)
        or canonical_json(value.get("artifacts")) != canonical_json(artifacts)
    ):
        _raise(
            "The voice-upgrade result provenance is invalid.",
            code="invalid_voice_upgrade_worker_result",
        )
    starts = value.get("segment_start_ms")
    if (
        not isinstance(starts, list)
        or len(starts) != 3
        or any(isinstance(item, bool) or not isinstance(item, int) for item in starts)
        or starts[0] != 0
        or not (starts[0] < starts[1] < starts[2] < value["duration_ms"])
    ):
        _raise(
            "The voice-upgrade timing result is invalid.",
            code="invalid_voice_upgrade_worker_result",
        )
    lineage = value.get("source_lineage")
    if not isinstance(lineage, dict) or set(lineage) != _SOURCE_LINEAGE_KEYS:
        _raise(
            "The voice-upgrade source lineage is invalid.",
            code="invalid_voice_upgrade_worker_result",
        )
    lineage_body = {
        key: lineage[key] for key in _SOURCE_LINEAGE_KEYS if key != "source_binding_digest"
    }
    source_artifacts = lineage.get("source_artifacts")
    if (
        lineage.get("schema_version") != VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION
        or lineage.get("production_id") != expected_production_id
        or lineage.get("run_id") != expected_run_id
        or not _valid_identifier(lineage.get("source_attempt_id"), _ATTEMPT_ID_RE)
        or not isinstance(lineage.get("source_cache_key"), str)
        or _SHA256_RE.fullmatch(lineage["source_cache_key"]) is None
        or lineage.get("source_provider") != EXTERNAL_TTS_PROVIDER
        or lineage.get("source_timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or not isinstance(source_artifacts, dict)
        or set(source_artifacts) != _SOURCE_NAMES
        or not isinstance(lineage.get("source_binding_digest"), str)
        or _SHA256_RE.fullmatch(lineage["source_binding_digest"]) is None
        or hashlib.sha256(canonical_json(lineage_body).encode("utf-8")).hexdigest().upper()
        != lineage["source_binding_digest"]
    ):
        _raise(
            "The voice-upgrade source lineage is invalid.",
            code="invalid_voice_upgrade_worker_result",
        )
    for name, item in source_artifacts.items():
        maximum = _SOURCE_SPECS[name][2]
        if (
            not isinstance(item, dict)
            or set(item) != {"artifact_id", "bytes", "sha256"}
            or not _valid_identifier(item.get("artifact_id"), _ARTIFACT_ID_RE)
            or isinstance(item.get("bytes"), bool)
            or not isinstance(item.get("bytes"), int)
            or not 0 < item["bytes"] <= maximum
            or not isinstance(item.get("sha256"), str)
            or _SHA256_RE.fullmatch(item["sha256"]) is None
        ):
            _raise(
                "The voice-upgrade source lineage is invalid.",
                code="invalid_voice_upgrade_worker_result",
            )
    return dict(value)


def safe_voice_upgrade_execution_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, VoiceUpgradeExecutionError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return (
        "voice_upgrade_execution_failed",
        "The local voice-upgrade job failed.",
    )


__all__ = [
    "ResolvedVoiceUpgradeSource",
    "VOICE_UPGRADE_EXECUTION_PROVIDER",
    "VOICE_UPGRADE_EXECUTION_SCHEMA_VERSION",
    "VoiceUpgradeExecutionError",
    "VoiceUpgradeExecutionOutcome",
    "execute_voice_upgrade",
    "resolve_voice_upgrade_source",
    "safe_voice_upgrade_execution_error",
    "validate_voice_upgrade_execution_request",
    "validate_voice_upgrade_public_result",
]
