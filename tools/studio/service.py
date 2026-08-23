from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any

from .database import SCHEMA_VERSION, StudioDatabase, money_to_minor, utc_now
from .execution import (
    LocalNarrationError,
    LocalNarrationValidationError,
    audit_payload,
    narration_cache_key,
    public_result,
    safe_error,
    validate_local_narration_payload,
)
from .indexer import ProductionIndexer
from .jobs import AuditExporter, JobManager
from .secrets import SecretStore, dpapi_available
from .security import (
    SecurityError,
    relative_workspace_path,
    sanitize_for_storage,
    sensitive_artifact_path,
    stable_id,
    validate_identifier,
    workspace_path,
)


STAGE_ORDER = (
    "keyframes",
    "screen_capture",
    "narration",
    "captions",
    "video_generation",
    "assembly",
    "qc",
)

_DIRECT_STAGES: dict[str, set[str]] = {
    "script": {"narration"},
    "copy": {"narration"},
    "narration": {"narration"},
    "voice": {"narration"},
    "pronunciation": {"narration"},
    "caption": {"captions"},
    "captions": {"captions"},
    "subtitle": {"captions"},
    "subtitles": {"captions"},
    "telop": {"assembly"},
    "overlay": {"assembly"},
    "layout": {"assembly"},
    "timing": {"assembly"},
    "transition": {"assembly"},
    "assembly": {"assembly"},
    "keyframe": {"keyframes"},
    "image": {"keyframes"},
    "source_image": {"keyframes"},
    "visual_prompt": {"keyframes"},
    "prompt": {"keyframes"},
    "video": {"video_generation"},
    "clip": {"video_generation"},
    "generation": {"video_generation"},
    "screen": {"screen_capture"},
    "capture": {"screen_capture"},
    "browser_capture": {"screen_capture"},
    "screen_capture": {"screen_capture"},
    "qc": {"qc"},
}

_DEPENDENTS: dict[str, set[str]] = {
    "keyframes": {"video_generation"},
    "screen_capture": {"assembly"},
    "narration": {"captions", "assembly"},
    "captions": {"assembly"},
    "video_generation": {"assembly"},
    "assembly": {"qc"},
    "qc": set(),
}

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_EXECUTION_PROFILES = {"external", "local_sapi"}
_LOCAL_SAPI_ZERO_COST_STAGES = {"narration", "captions", "assembly", "qc"}
_LOCAL_NARRATION_STAGE = "narration"
_LOCAL_ARTIFACT_KINDS = {"audio", "subtitle", "document", "log"}
_LOCAL_NARRATION_ARTIFACTS = {
    "narration.wav": ("audio", "audio/wav"),
    "captions.srt": ("subtitle", "application/x-subrip"),
    "timings.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


class RequestValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_request"):
        super().__init__(message)
        self.code = code


def _change_type(change: Any) -> str:
    if isinstance(change, str):
        value = change
    elif isinstance(change, dict):
        value = str(change.get("type") or change.get("kind") or change.get("target") or "unknown")
    else:
        value = "unknown"
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "unknown"


def build_rerun_plan(production_id: str, changes: list[Any]) -> dict[str, Any]:
    if not isinstance(changes, list) or not changes:
        raise RequestValidationError("changes must be a non-empty array")
    if len(changes) > 100:
        raise RequestValidationError("changes contains too many entries")
    safe_changes = sanitize_for_storage(changes)
    direct: set[str] = set()
    causes: list[dict[str, Any]] = []
    for change in safe_changes:
        kind = _change_type(change)
        matched = _DIRECT_STAGES.get(kind)
        if matched is None:
            matched = set(STAGE_ORDER)
            reason = "unknown_change_uses_conservative_full_rerun"
        else:
            reason = "mapped_change"
        direct.update(matched)
        causes.append({"change_type": kind, "direct_stages": sorted(matched), "reason": reason})

    affected = set(direct)
    pending = list(direct)
    while pending:
        stage = pending.pop()
        for dependent in _DEPENDENTS.get(stage, set()):
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    affected_ordered = [stage for stage in STAGE_ORDER if stage in affected]
    reused = [stage for stage in STAGE_ORDER if stage not in affected]
    billable = [stage for stage in affected_ordered if stage in {"narration", "video_generation"}]
    return {
        "production_id": production_id,
        "changes": safe_changes,
        "affected_stages": affected_ordered,
        "reused_stages": reused,
        "billable_stages": billable,
        "requires_cost_estimate": bool(billable),
        "causes": causes,
    }


class StudioService:
    def __init__(self, workspace: Path, *, database_path: Path | None = None):
        self.workspace = workspace.resolve(strict=True)
        path = database_path or workspace_path(self.workspace, "outputs/studio/studio.sqlite3")
        path = workspace_path(self.workspace, path)
        self.database = StudioDatabase(path, workspace=self.workspace)
        self.indexer = ProductionIndexer(self.workspace, self.database)
        self.secret_store = SecretStore(self.workspace)
        self.jobs = JobManager(self.database)
        self.audit_exporter = AuditExporter(self.workspace, self.database)

    def close(self) -> None:
        self.jobs.shutdown()

    def health(self) -> dict[str, Any]:
        mirror = self.database.event_mirror_health()
        return {
            "ok": True,
            "degraded": not mirror["ok"],
            "message": (
                "The audit event mirror requires attention."
                if not mirror["ok"]
                else "Studio is ready."
            ),
            "service": "minimaxh3-studio",
            "schema_version": SCHEMA_VERSION,
            "time": utc_now(),
            "event_mirror": mirror,
        }

    def providers_status(self) -> dict[str, Any]:
        return {
            "providers": self.secret_store.statuses(),
            "secure_persistence_available": dpapi_available(),
        }

    def list_productions(self) -> dict[str, Any]:
        productions = self.database.list_productions()
        return {"productions": productions, "count": len(productions)}

    def production_detail(
        self, production_id: str, *, artifact_limit: int = 5000, artifact_offset: int = 0
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        return self.database.get_production_detail(
            production_id,
            artifact_limit=max(1, min(int(artifact_limit), 10_000)),
            artifact_offset=max(0, int(artifact_offset)),
        )

    def artifact(self, artifact_id: str) -> dict[str, Any] | None:
        validate_identifier(artifact_id, label="artifact id")
        return self.database.get_artifact(artifact_id)

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        jobs = self.database.list_jobs(limit=max(1, min(int(limit), 500)))
        return {"jobs": jobs, "count": len(jobs)}

    def job(self, job_id: str) -> dict[str, Any] | None:
        validate_identifier(job_id, label="job id")
        return self.database.get_job(job_id)

    def run(self, run_id: str) -> dict[str, Any] | None:
        validate_identifier(run_id, label="run id")
        return self.database.get_run(run_id)

    def refresh_index(self) -> dict[str, Any]:
        return self.jobs.submit(
            "index_refresh",
            {},
            lambda _job_id: self.indexer.refresh(),
        )

    def rerun_plan(self, production_id: str, changes: list[Any], *, record_event: bool = True) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        plan = build_rerun_plan(production_id, changes)
        if record_event:
            self.database.append_event(
                "production",
                production_id,
                "rerun.plan.requested",
                {
                    "changes": plan["changes"],
                    "affected_stages": plan["affected_stages"],
                    "reused_stages": plan["reused_stages"],
                },
            )
        return plan

    def create_run(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        if not isinstance(body, dict):
            raise RequestValidationError("request body must be an object")
        changes = body.get("changes")
        plan = self.rerun_plan(production_id, changes, record_event=False)
        cost = body.get("estimated_cost", {"amount": 0, "currency": "USD"})
        if not isinstance(cost, dict):
            raise RequestValidationError("estimated_cost must be an object")
        try:
            amount_minor = money_to_minor(cost.get("amount", 0))
        except ValueError as exc:
            raise RequestValidationError(str(exc)) from exc
        currency = str(cost.get("currency", "USD")).upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise RequestValidationError("currency must be a three-letter code")
        execution_profile = body.get("execution_profile", "external")
        if not isinstance(execution_profile, str) or execution_profile not in _EXECUTION_PROFILES:
            raise RequestValidationError("execution_profile is not supported")
        affected_stages = set(plan["affected_stages"])
        local_zero_cost_plan = (
            execution_profile == "local_sapi"
            and bool(affected_stages)
            and affected_stages.issubset(_LOCAL_SAPI_ZERO_COST_STAGES)
        )
        if (
            execution_profile == "local_sapi"
            and amount_minor == 0
            and (not affected_stages or not affected_stages.issubset(_LOCAL_SAPI_ZERO_COST_STAGES))
        ):
            raise RequestValidationError(
                "local_sapi zero-cost runs may only affect narration, captions, assembly, or qc.",
                code="local_profile_stage_not_allowed",
            )
        if plan["billable_stages"] and amount_minor <= 0 and not local_zero_cost_plan:
            raise RequestValidationError(
                "A positive estimated_cost is required when billable stages are affected.",
                code="cost_estimate_required",
            )
        if execution_profile == "local_sapi":
            if amount_minor != 0:
                raise RequestValidationError(
                    "local_sapi runs must use a zero-cost estimate.",
                    code="local_profile_cost_not_allowed",
                )
            if not affected_stages or not affected_stages.issubset(_LOCAL_SAPI_ZERO_COST_STAGES):
                raise RequestValidationError(
                    "local_sapi zero-cost runs may only affect narration, captions, assembly, or qc.",
                    code="local_profile_stage_not_allowed",
                )
        parent_revision_id = body.get("parent_revision_id")
        if parent_revision_id is not None:
            validate_identifier(parent_revision_id, label="parent revision id")
        revision, run = self.database.create_revision_and_run(
            production_id,
            plan["changes"],
            plan,
            amount_minor,
            currency,
            parent_revision_id=parent_revision_id,
            execution_profile=execution_profile,
        )
        return {"revision": revision, "run": run}

    def approve_run(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        validate_identifier(run_id, label="run id")
        if not isinstance(body, dict) or not isinstance(body.get("approved"), bool):
            raise RequestValidationError("approved must be a boolean")
        existing = self.database.get_run(run_id)
        if existing is None:
            raise KeyError("run not found")
        if money_to_minor(existing["estimated_cost"]["amount"]) <= 0:
            raise RequestValidationError(
                "Cost approval is only valid for a run with a positive estimate.",
                code="cost_approval_not_required",
            )
        approved = body["approved"]
        maximum = body.get("max_cost")
        if maximum is None and not approved:
            maximum = {"amount": 0, "currency": existing["estimated_cost"]["currency"]}
        if maximum is None and approved:
            raise RequestValidationError("max_cost is required for approval")
        if not isinstance(maximum, dict):
            raise RequestValidationError("max_cost must be an object")
        try:
            maximum_minor = money_to_minor(maximum.get("amount", 0))
        except ValueError as exc:
            raise RequestValidationError(str(exc)) from exc
        currency = str(maximum.get("currency", existing["estimated_cost"]["currency"])).upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise RequestValidationError("currency must be a three-letter code")
        actor = str(body.get("actor", "local_user"))
        note = str(body.get("note", ""))
        try:
            return self.database.approve_run(
                run_id,
                approved=approved,
                approved_max_minor=maximum_minor,
                currency=currency,
                actor=actor,
                note=note,
            )
        except ValueError as exc:
            raise RequestValidationError(str(exc), code="approval_rejected") from exc

    def _register_local_narration_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(raw_artifacts, list)
            or len(raw_artifacts) != len(_LOCAL_NARRATION_ARTIFACTS)
        ):
            raise LocalNarrationError(
                "The local narration worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/narration/{cache_key}/"
        validated: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise LocalNarrationError(
                    "The local narration worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise LocalNarrationError(
                    "The local narration worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            if (
                not relative.startswith(expected_root)
                or sensitive_artifact_path(relative)
                or path.is_symlink()
                or not path.is_file()
            ):
                raise LocalNarrationError(
                    "The local narration worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                )
            if relative in seen_paths:
                raise LocalNarrationError(
                    "The local narration worker returned duplicate artifacts.",
                    code="invalid_worker_result",
                )
            seen_paths.add(relative)
            expected = _LOCAL_NARRATION_ARTIFACTS.get(path.name)
            if expected is None or relative != f"{expected_root}{path.name}" or path.name in seen_names:
                raise LocalNarrationError(
                    "The local narration worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            seen_names.add(path.name)
            kind = item.get("kind")
            if not isinstance(kind, str) or kind not in _LOCAL_ARTIFACT_KINDS or kind != expected[0]:
                raise LocalNarrationError(
                    "The local narration worker returned an unsupported artifact kind.",
                    code="invalid_worker_result",
                )
            media_type = item.get("media_type", item.get("mime"))
            if not isinstance(media_type, str) or not media_type or len(media_type) > 128:
                media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if any(ord(char) < 0x20 or ord(char) == 0x7F for char in media_type):
                raise LocalNarrationError(
                    "The local narration worker returned invalid media metadata.",
                    code="invalid_worker_result",
                )
            if "/" not in media_type or any(char in media_type for char in '";'):
                raise LocalNarrationError(
                    "The local narration worker returned invalid media metadata.",
                    code="invalid_worker_result",
                )
            if media_type != expected[1]:
                raise LocalNarrationError(
                    "The local narration worker returned unexpected media metadata.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise LocalNarrationError(
                    "The local narration worker returned mismatched artifact metadata.",
                    code="invalid_worker_result",
                )
            validated.append(
                {
                    "id": stable_id("art", relative.casefold()),
                    "rel_path": relative,
                    "name": path.name,
                    "kind": kind,
                    "media_type": media_type,
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": digest,
                    "is_heavy": stat.st_size > 10 * 1024 * 1024,
                }
            )
        if seen_names != set(_LOCAL_NARRATION_ARTIFACTS):
            raise LocalNarrationError(
                "The local narration worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        registered: list[dict[str, Any]] = []
        for artifact_data in validated:
            artifact = self.database.register_studio_artifact(
                production_id,
                artifact_data,
            )
            registered.append(artifact)
        return registered

    def _cached_local_narration_result(
        self, cache_key: str, production_id: str
    ) -> dict[str, Any] | None:
        previous = self.database.find_successful_stage_attempt(
            production_id, "narration", cache_key
        )
        if not previous or not isinstance(previous.get("result"), dict):
            return None
        prior_result = previous["result"]
        prior_artifacts = prior_result.get("artifacts")
        if (
            not isinstance(prior_artifacts, list)
            or len(prior_artifacts) != len(_LOCAL_NARRATION_ARTIFACTS)
        ):
            return None
        verified: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        source_root = (
            f"outputs/studio/runs/{previous['run_id']}/narration/{cache_key}/"
        )
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if (
                artifact is None
                or artifact["production_id"] != production_id
                or not artifact["available"]
                or artifact["name"] not in _LOCAL_NARRATION_ARTIFACTS
                or artifact["name"] in seen_names
                or artifact.get("origin") != "studio"
                or artifact.get("kind")
                != _LOCAL_NARRATION_ARTIFACTS[artifact["name"]][0]
                or artifact.get("media_type")
                != _LOCAL_NARRATION_ARTIFACTS[artifact["name"]][1]
                or artifact.get("rel_path")
                != f"{source_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
            ):
                return None
            seen_names.add(artifact["name"])
            try:
                path = workspace_path(self.workspace, artifact["rel_path"], must_exist=True)
            except (SecurityError, OSError):
                return None
            if path.is_symlink() or not path.is_file() or sensitive_artifact_path(artifact["rel_path"]):
                return None
            stat = path.stat()
            if (
                artifact.get("bytes") != stat.st_size
                or not isinstance(artifact.get("sha256"), str)
                or _sha256_file(path) != artifact["sha256"]
            ):
                return None
            verified.append(artifact)
        if seen_names != set(_LOCAL_NARRATION_ARTIFACTS):
            return None
        cached_raw = dict(prior_result)
        cached_raw["cache_hit"] = True
        try:
            cached = public_result(
                cached_raw,
                expected_cache_key=cache_key,
                artifacts=verified,
                cache_hit=True,
            )
        except LocalNarrationError:
            return None
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_local_narration(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        cache_key: str,
    ) -> dict[str, Any]:
        self.database.update_stage_attempt(attempt_id, "running")
        try:
            cached = self._cached_local_narration_result(cache_key, production_id)
            if cached is not None:
                result = cached
            else:
                try:
                    from . import narration
                except (ImportError, AttributeError) as exc:
                    raise LocalNarrationError(
                        "The local narration worker is not installed.",
                        code="local_worker_unavailable",
                    ) from exc
                try:
                    raw = narration.generate_local_narration(
                        self.workspace,
                        production_id=production_id,
                        run_id=run_id,
                        payload=payload,
                    )
                except LocalNarrationError:
                    raise
                except Exception as exc:
                    raise LocalNarrationError(
                        "The local narration worker failed.",
                        code="local_narration_failed",
                    ) from exc
                # Validate provider, cost, timing, cache identity, and the
                # strict cache_hit type before persisting any worker artifact.
                # A malformed adapter result must not enter production/audit
                # records merely because its files look valid.
                result = public_result(
                    raw,
                    expected_cache_key=cache_key,
                    artifacts=[],
                    cache_hit=bool(raw.get("cache_hit", False))
                    if isinstance(raw, dict)
                    else False,
                )
                artifacts = self._register_local_narration_artifacts(
                    production_id,
                    run_id,
                    cache_key,
                    raw.get("artifacts") if isinstance(raw, dict) else None,
                )
                result["artifacts"] = artifacts
            self.database.update_stage_attempt(attempt_id, "succeeded", result=result)
            return {"stage_attempt_id": attempt_id, **result}
        except Exception as exc:
            error_code, error_message = safe_error(exc)
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=error_code,
                    error_message=error_message,
                )
            except Exception:
                pass
            raise

    def execute_local_narration(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Queue a zero-cost local narration attempt for a local_sapi run."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "local_sapi":
            raise RequestValidationError(
                "This run is not configured for local narration.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if not isinstance(requested_stages, list) or _LOCAL_NARRATION_STAGE not in requested_stages:
            raise RequestValidationError(
                "The narration stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_local_narration_payload(body)
        except LocalNarrationValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        cache_key = narration_cache_key(payload)
        attempt_payload = {
            "execution_profile": "local_sapi",
            "cache_key": cache_key,
            **audit_payload(payload),
        }
        attempt = self.database.create_stage_attempt(
            run_id, _LOCAL_NARRATION_STAGE, cache_key, attempt_payload
        )
        try:
            job = self.jobs.submit(
                "local_narration",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_NARRATION_STAGE,
                    "execution_profile": "local_sapi",
                    "cache_key": cache_key,
                    **audit_payload(payload),
                },
                lambda _job_id: self._execute_local_narration(
                    attempt["id"], run_id, run["production_id"], payload, cache_key
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
            )
        except Exception as exc:
            error_code, error_message = safe_error(exc)
            self.database.update_stage_attempt(
                attempt["id"], "failed", error_code=error_code, error_message=error_message
            )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["cache_key"] = cache_key
        return job

    def audit_export(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        if not isinstance(body, dict):
            raise RequestValidationError("request body must be an object")
        include_media = body.get("include_media", False)
        if not isinstance(include_media, bool):
            raise RequestValidationError("include_media must be a boolean")
        return self.jobs.submit(
            "audit_export",
            {"include_media": include_media},
            lambda job_id: self.audit_exporter.export(
                production_id, job_id, include_media=include_media
            ),
            production_id=production_id,
        )
