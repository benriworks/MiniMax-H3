from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .database import SCHEMA_VERSION, StudioDatabase, money_to_minor, utc_now
from .indexer import ProductionIndexer
from .jobs import AuditExporter, JobManager
from .secrets import SecretStore, dpapi_available
from .security import sanitize_for_storage, validate_identifier, workspace_path


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
        if plan["billable_stages"] and amount_minor <= 0:
            raise RequestValidationError(
                "A positive estimated_cost is required when billable stages are affected.",
                code="cost_estimate_required",
            )
        currency = str(cost.get("currency", "USD")).upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise RequestValidationError("currency must be a three-letter code")
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
