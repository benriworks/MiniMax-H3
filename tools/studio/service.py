from __future__ import annotations

import hashlib
import importlib
import inspect
import mimetypes
import re
from pathlib import Path
from typing import Any

from .assembly_execution import (
    LocalAssemblyError,
    LocalAssemblyValidationError,
    assembly_audit_payload,
    assembly_public_result,
    safe_assembly_error,
    validate_local_assembly_payload,
)
from .database import (
    SCHEMA_VERSION,
    AtomicStageCompletion,
    StudioDatabase,
    money_to_minor,
    utc_now,
)
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
from .jobs import AuditExporter, JobCancelled, JobExecutionContext, JobManager
from .qc_execution import (
    LocalQcError,
    LocalQcValidationError,
    qc_audit_payload,
    qc_public_result,
    safe_qc_error,
    validate_local_qc_payload,
)
from .timeline_execution import (
    TimelineError as LocalTimelineError,
    TimelineValidationError as LocalTimelineValidationError,
    safe_timeline_error,
    timeline_audit_payload,
    timeline_public_result,
    validate_local_timeline_payload,
)
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
    "timeline",
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
    "timeline": {"timeline"},
    "sequence": {"timeline"},
    "cut": {"timeline"},
    "cut_plan": {"timeline"},
    "screen": {"screen_capture"},
    "capture": {"screen_capture"},
    "browser_capture": {"screen_capture"},
    "screen_capture": {"screen_capture"},
    "qc": {"qc"},
}

_DEPENDENTS: dict[str, set[str]] = {
    "keyframes": {"video_generation"},
    "screen_capture": {"timeline"},
    "narration": {"captions", "assembly"},
    "captions": {"assembly"},
    "video_generation": {"timeline"},
    "timeline": {"assembly"},
    "assembly": {"qc"},
    "qc": set(),
}

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_EXECUTION_PROFILES = {"external", "local_sapi", "elevenlabs_tts"}
_LOCAL_SAPI_ZERO_COST_STAGES = {"narration", "captions", "timeline", "assembly", "qc"}
_ELEVENLABS_TTS_STAGES = {"narration", "captions", "assembly", "qc"}
_LOCAL_DOWNSTREAM_PROFILES = {"local_sapi", "elevenlabs_tts"}
_LOCAL_NARRATION_STAGE = "narration"
_LOCAL_TIMELINE_STAGE = "timeline"
_LOCAL_ASSEMBLY_STAGE = "assembly"
_LOCAL_QC_STAGE = "qc"
_LOCAL_ARTIFACT_KINDS = {"audio", "subtitle", "document", "log"}
_LOCAL_NARRATION_ARTIFACTS = {
    "narration.wav": ("audio", "audio/wav"),
    "captions.srt": ("subtitle", "application/x-subrip"),
    "timings.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_ASSEMBLY_ARTIFACTS = {
    "master-clean.mp4": ("video", "video/mp4"),
    "master-captioned.mp4": ("video", "video/mp4"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_QC_ARTIFACTS = {
    "technical-qc.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_TIMELINE_ARTIFACTS = {
    "timeline-preview.mp4": ("video", "video/mp4"),
    "timeline.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_MAX_LOCAL_TIMELINE_CLIPS = 32
_MAX_LOCAL_TIMELINE_INPUT_BYTES = 4 * 1024 * 1024 * 1024
_MAX_LOCAL_TIMELINE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
_EXTERNAL_NARRATION_STAGE = "narration"
_EXTERNAL_NARRATION_PROVIDER = "elevenlabs"
_EXTERNAL_AMBIGUOUS_ERROR_CODES = frozenset(
    {
        "ambiguous_submission",
        "external_tts_ambiguous_submission",
        "external_submission_ambiguous",
        "external_submission_unknown",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _raise_if_cancelled(cancel_event: JobExecutionContext | None) -> None:
    if cancel_event is None:
        return
    cancel_event.raise_if_cancelled()


def _call_local_worker(
    worker: Any,
    *args: Any,
    cancel_event: JobExecutionContext | None = None,
    **kwargs: Any,
) -> Any:
    """Pass the cooperative token only to workers that implement it.

    This keeps the service compatible with older local worker adapters while
    allowing assembly/QC/narration implementations to register and stop their
    own subprocess trees.
    """

    if cancel_event is not None:
        try:
            signature = inspect.signature(worker)
            # Mocks and legacy adapters often expose ``**kwargs`` even though
            # their side-effect implementation does not accept a token. Only
            # an explicit cancellation parameter is an opt-in contract.
            if "cancel_event" in signature.parameters:
                kwargs["cancel_event"] = cancel_event
        except (TypeError, ValueError):
            pass
    return worker(*args, **kwargs)


def _load_external_tts_contract() -> Any:
    """Load the external-TTS request/result contract only after gating.

    Keeping this import out of module initialization is intentional: an
    unapproved request must not import the provider adapter (or any of its
    HTTP dependencies) as a side effect.
    """

    try:
        return importlib.import_module("tools.studio.external_tts_execution")
    except (ImportError, AttributeError) as exc:
        raise RequestValidationError(
            "The external narration contract is not installed.",
            code="external_worker_unavailable",
        ) from exc


def _external_contract_function(module: Any, *names: str) -> Any:
    for name in names:
        function = getattr(module, name, None)
        if callable(function):
            return function
    raise RequestValidationError(
        "The external narration contract is not installed.",
        code="external_worker_unavailable",
    )


def _external_error_pair(exc: BaseException) -> tuple[str, str]:
    """Return a bounded provider error without crossing secrets or paths."""

    code = getattr(exc, "error_code", None)
    message = getattr(exc, "public_message", None)
    if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_.-]{1,128}", code):
        code = "external_narration_failed"
    if code not in {
        "ambiguous_submission",
        "external_tts_ambiguous_submission",
        "external_submission_ambiguous",
        "external_submission_unknown",
        "external_tts_failed",
        "external_narration_failed",
        "external_tts_secret_unavailable",
        "invalid_worker_result",
        "invalid_external_narration_request",
        "external_worker_unavailable",
        "external_provider_error",
        "external_tts_media_failed",
        "external_redirect_rejected",
        "external_tts_network_failed",
        "invalid_external_provider_metadata",
        "invalid_external_alignment",
        "external_request_invalid",
        "cache_integrity_failed",
        "publish_failed",
    }:
        code = "external_narration_failed"
    if not isinstance(message, str) or not message:
        message = "The external narration job failed."
    # Provider exception strings are not trusted; use only explicitly public
    # messages and keep the persisted audit value bounded.
    return code, message[:1000]


def _external_worker_function(module: Any) -> Any:
    names = (
        "generate_external_tts",
        "generate_external_narration",
        "generate_elevenlabs_narration",
        "synthesize_elevenlabs",
    )
    candidates = [
        getattr(module, name, None)
        for name in names
        if callable(getattr(module, name, None))
    ]
    if not candidates:
        raise RequestValidationError(
            "The external narration worker is not installed.",
            code="external_worker_unavailable",
        )
    # The provider module exposes compatibility aliases.  Tests and callers
    # may patch any one of them; select the lone identity that differs from
    # the untouched alias group so a patched seam is never bypassed.
    counts: dict[int, int] = {}
    for candidate in candidates:
        counts[id(candidate)] = counts.get(id(candidate), 0) + 1
    distinct = [candidate for candidate in candidates if counts[id(candidate)] == 1]
    return distinct[0] if len(distinct) == 1 else candidates[0]


def _stage_completion_result(
    attempt_id: str,
    result: dict[str, Any],
    cancel_event: JobExecutionContext | None,
) -> dict[str, Any] | AtomicStageCompletion:
    """Return a public result or the internal atomic-completion envelope.

    Existing direct helper callers continue to receive the historical public
    mapping (including ``stage_attempt_id``).  A JobManager invocation passes
    a cancellation context and receives the envelope instead; only the
    manager unwraps it and asks the database to derive the public job result
    after the atomic job/stage transition succeeds.  The stage result itself
    never gains the internal attempt-id field.
    """

    public_result = {"stage_attempt_id": attempt_id, **result}
    if cancel_event is None:
        return public_result
    return AtomicStageCompletion(attempt_id, result)


def _has_symlink_component(workspace: Path, candidate: str | Path) -> bool:
    """Reject lexical workspace paths that traverse a symlink component."""

    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    lexical = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


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
                "local_sapi zero-cost runs may only affect narration, captions, timeline, assembly, or qc.",
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
                    "local_sapi zero-cost runs may only affect narration, captions, timeline, assembly, or qc.",
                    code="local_profile_stage_not_allowed",
                )
        if execution_profile == "elevenlabs_tts":
            if (
                _EXTERNAL_NARRATION_STAGE not in affected_stages
                or not affected_stages.issubset(_ELEVENLABS_TTS_STAGES)
            ):
                raise RequestValidationError(
                    "elevenlabs_tts runs require narration and may only affect narration, captions, assembly, or qc.",
                    code="external_profile_stage_not_allowed",
                )
            if amount_minor <= 0:
                raise RequestValidationError(
                    "elevenlabs_tts runs require a positive estimated_cost.",
                    code="cost_estimate_required",
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
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        self.database.update_stage_attempt(attempt_id, "running")
        try:
            _raise_if_cancelled(cancel_event)
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
                    raw = _call_local_worker(
                        narration.generate_local_narration,
                        self.workspace,
                        production_id=production_id,
                        run_id=run_id,
                        payload=payload,
                        cancel_event=cancel_event,
                    )
                except LocalNarrationError:
                    raise
                except Exception as exc:
                    raise LocalNarrationError(
                        "The local narration worker failed.",
                        code="local_narration_failed",
                    ) from exc
                _raise_if_cancelled(cancel_event)
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
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(attempt_id, result, cancel_event)
        except JobCancelled as exc:
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.public_message,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    self.database.update_stage_attempt(
                        attempt_id,
                        "failed",
                        error_code=JobCancelled.error_code,
                        error_message=JobCancelled.public_message,
                    )
                except Exception:
                    pass
                raise JobCancelled() from exc
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
                lambda _job_id, cancel_event: self._execute_local_narration(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    cancel_event,
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

    def _validate_external_narration_payload(
        self, body: dict[str, Any]
    ) -> tuple[Any, dict[str, Any]]:
        """Validate an ElevenLabs request through the external contract.

        ``confirm_billable`` is a control-plane acknowledgement.  The
        external contract validates the literal alongside the provider fields;
        its cache-key implementation is responsible for excluding the flag
        from the provider identity.
        """

        contract = _load_external_tts_contract()
        validator = _external_contract_function(
            contract,
            "validate_external_tts_payload",
            "validate_elevenlabs_payload",
        )
        try:
            payload = validator(dict(body))
        except RequestValidationError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None) or getattr(
                exc, "error_code", "invalid_external_narration_request"
            )
            raise RequestValidationError(str(exc), code=str(code)[:128]) from exc
        if not isinstance(payload, dict):
            raise RequestValidationError(
                "The external narration contract returned an invalid payload.",
                code="invalid_external_narration_request",
            )
        return contract, payload

    @staticmethod
    def _external_cache_key(contract: Any, payload: dict[str, Any]) -> str:
        function = _external_contract_function(
            contract,
            "external_tts_cache_key",
            "elevenlabs_cache_key",
            "narration_cache_key",
        )
        try:
            cache_key = function(payload)
        except Exception as exc:
            code = getattr(exc, "error_code", "invalid_external_narration_request")
            raise RequestValidationError(str(exc), code=str(code)[:128]) from exc
        if not isinstance(cache_key, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", cache_key):
            raise RequestValidationError(
                "The external narration contract returned an invalid cache key.",
                code="invalid_worker_result",
            )
        return cache_key.upper()

    @staticmethod
    def _external_audit_payload(
        contract: Any, payload: dict[str, Any], *, cache_key: str
    ) -> dict[str, Any]:
        function = getattr(contract, "external_tts_audit_payload", None)
        if not callable(function):
            function = getattr(contract, "audit_payload", None)
        if callable(function):
            try:
                value = function(payload, cache_key=cache_key)
            except TypeError:
                value = function(payload)
            if isinstance(value, dict):
                return sanitize_for_storage(value)
        segments = payload.get("segments", [])
        return {
            "segment_count": len(segments) if isinstance(segments, list) else 0,
            "text_chars": sum(
                len(item.get("text", ""))
                for item in segments
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ),
            "segment_text_sha256": [
                hashlib.sha256(item.get("text", "").encode("utf-8")).hexdigest()
                for item in segments
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ],
            "voice_id": payload.get("voice_id"),
            "model_id": payload.get("model_id"),
            "cache_key": cache_key,
        }

    @staticmethod
    def _external_public_result(
        contract: Any,
        raw: Any,
        *,
        expected_cache_key: str,
        artifacts: list[dict[str, Any]],
        cache_hit: bool,
    ) -> dict[str, Any]:
        function = getattr(contract, "external_tts_public_result", None)
        if not callable(function):
            function = getattr(contract, "public_result", None)
        if callable(function):
            try:
                value = function(
                    raw,
                    expected_cache_key=expected_cache_key,
                    artifacts=artifacts,
                    cache_hit=cache_hit,
                )
            except TypeError:
                # A compact worker contract may not accept ``artifacts``;
                # preserve its validation while attaching the server-verified
                # artifact records below.
                value = function(
                    raw,
                    expected_cache_key=expected_cache_key,
                    cache_hit=cache_hit,
                )
            if not isinstance(value, dict):
                raise ValueError("external narration worker returned an invalid result")
            result = dict(value)
            result["artifacts"] = artifacts
            result.setdefault("request_cache_key", expected_cache_key)
            result["cache_hit"] = cache_hit
            return sanitize_for_storage(result)

        if not isinstance(raw, dict):
            raise ValueError("external narration worker returned an invalid result")
        returned_key = raw.get("cache_key")
        if returned_key != expected_cache_key:
            raise ValueError("external narration worker returned a mismatched cache key")
        if raw.get("provider") != _EXTERNAL_NARRATION_PROVIDER:
            raise ValueError("external narration worker returned an invalid provider")
        if not isinstance(raw.get("cache_hit"), bool) or raw["cache_hit"] != cache_hit:
            raise ValueError("external narration worker returned invalid cache metadata")
        duration_ms = raw.get("duration_ms")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms <= 0:
            raise ValueError("external narration worker returned invalid timing")
        task_id = raw.get("provider_task_id", raw.get("request_id"))
        if task_id is not None and (
            not isinstance(task_id, str) or not task_id or len(task_id) > 256
        ):
            raise ValueError("external narration worker returned invalid task metadata")
        actual_cost = raw.get("actual_cost")
        if actual_cost is not None:
            raise ValueError("external narration worker returned invalid cost metadata")
        character_cost = raw.get("character_cost")
        if (
            isinstance(character_cost, bool)
            or not isinstance(character_cost, int)
            or character_cost < 0
        ):
            raise ValueError("external narration worker returned invalid character usage")
        result = {
            "artifacts": artifacts,
            "duration_ms": duration_ms,
            "cache_key": expected_cache_key,
            "request_cache_key": expected_cache_key,
            "cache_hit": cache_hit,
            "provider": _EXTERNAL_NARRATION_PROVIDER,
            "provider_task_id": task_id,
            "request_id": raw.get("request_id", task_id),
            "actual_cost": actual_cost,
            "timing_source": raw.get("timing_source", "provider_timestamps"),
            "character_cost": character_cost,
        }
        for key in ("character_count", "usage", "cost"):
            if key in raw:
                result[key] = sanitize_for_storage(raw[key])
        return result

    def _cached_external_narration_result(
        self,
        contract: Any,
        cache_key: str,
        production_id: str,
    ) -> dict[str, Any] | None:
        previous = self.database.find_successful_stage_attempt(
            production_id, _EXTERNAL_NARRATION_STAGE, cache_key
        )
        if not previous or not isinstance(previous.get("result"), dict):
            return None
        prior_result = previous["result"]
        prior_artifacts = prior_result.get("artifacts")
        if not isinstance(prior_artifacts, list) or len(prior_artifacts) != len(
            _LOCAL_NARRATION_ARTIFACTS
        ):
            return None
        source_root = (
            f"outputs/studio/runs/{previous['run_id']}/narration/{cache_key}/"
        )
        verified: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if (
                artifact is None
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("name") not in _LOCAL_NARRATION_ARTIFACTS
                or artifact.get("name") in seen_names
                or artifact.get("kind") != _LOCAL_NARRATION_ARTIFACTS[artifact["name"]][0]
                or artifact.get("media_type") != _LOCAL_NARRATION_ARTIFACTS[artifact["name"]][1]
                or artifact.get("rel_path") != f"{source_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
            ):
                return None
            try:
                path = workspace_path(self.workspace, artifact["rel_path"], must_exist=True)
            except (SecurityError, OSError):
                return None
            if (
                _has_symlink_component(self.workspace, artifact["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(artifact["rel_path"])
            ):
                return None
            stat = path.stat()
            if (
                stat.st_size != artifact.get("bytes")
                or not isinstance(artifact.get("sha256"), str)
                or _sha256_file(path) != artifact["sha256"]
            ):
                return None
            seen_names.add(artifact["name"])
            verified.append(artifact)
        if seen_names != set(_LOCAL_NARRATION_ARTIFACTS):
            return None
        cached = self._external_public_result(
            contract,
            {**prior_result, "cache_hit": True},
            expected_cache_key=cache_key,
            artifacts=verified,
            cache_hit=True,
        )
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_external_narration(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        cache_key: str,
        contract: Any,
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        self.database.update_stage_attempt(attempt_id, "running")
        try:
            cached = self._cached_external_narration_result(
                contract, cache_key, production_id
            )
            if cached is not None:
                result = cached
            else:
                _raise_if_cancelled(cancel_event)
                # A second request may already have been admitted while the
                # first request was in flight.  Re-check immediately before
                # resolving the credential/provider so an ambiguous first
                # submission cannot turn that queued request into a duplicate
                # billable POST.
                if self.database.find_failed_stage_attempt(
                    production_id,
                    _EXTERNAL_NARRATION_STAGE,
                    cache_key,
                    error_codes=tuple(_EXTERNAL_AMBIGUOUS_ERROR_CODES),
                ):
                    error = RuntimeError("external submission outcome is unknown")
                    setattr(error, "error_code", "external_submission_unknown")
                    setattr(
                        error,
                        "public_message",
                        "The previous external submission may have been accepted; do not retry automatically.",
                    )
                    raise error
                # The credential is read only after the approval gate and only
                # on a cache miss, immediately before importing/calling the
                # provider adapter.  It never enters a job payload/result.
                try:
                    resolve_secret = getattr(self.secret_store, "resolve", None)
                    if callable(resolve_secret):
                        api_key = resolve_secret("elevenlabs")
                    else:
                        # Backward-compatible with the current SecretStore;
                        # newer stores resolve env/.env/DPAPI through resolve.
                        api_key = self.secret_store.get("elevenlabs")
                except Exception as exc:
                    error = RuntimeError("external provider secret unavailable")
                    setattr(error, "error_code", "external_tts_secret_unavailable")
                    setattr(error, "public_message", "The ElevenLabs credential is not configured.")
                    raise error from exc
                if not isinstance(api_key, str) or not api_key:
                    error = RuntimeError("external provider secret unavailable")
                    setattr(error, "error_code", "external_tts_secret_unavailable")
                    setattr(error, "public_message", "The ElevenLabs credential is not configured.")
                    raise error
                try:
                    provider_module = importlib.import_module("tools.studio.elevenlabs")
                    worker = _external_worker_function(provider_module)
                except (ImportError, AttributeError) as exc:
                    error = RuntimeError("external provider worker unavailable")
                    setattr(error, "error_code", "external_worker_unavailable")
                    setattr(error, "public_message", "The ElevenLabs worker is not installed.")
                    raise error from exc
                worker_kwargs: dict[str, Any] = {
                    "production_id": production_id,
                    "run_id": run_id,
                    "payload": payload,
                    "api_key": api_key,
                }
                try:
                    signature = inspect.signature(worker)
                    if "api_key" not in signature.parameters and "secret" in signature.parameters:
                        worker_kwargs["secret"] = worker_kwargs.pop("api_key")
                except (TypeError, ValueError):
                    pass
                raw = _call_local_worker(
                    worker,
                    self.workspace,
                    cancel_event=cancel_event,
                    **worker_kwargs,
                )
                _raise_if_cancelled(cancel_event)
                result = self._external_public_result(
                    contract,
                    raw,
                    expected_cache_key=cache_key,
                    artifacts=[],
                    cache_hit=False,
                )
                artifacts = self._register_local_narration_artifacts(
                    production_id,
                    run_id,
                    cache_key,
                    raw.get("artifacts") if isinstance(raw, dict) else None,
                )
                result["artifacts"] = artifacts
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(attempt_id, result, cancel_event)
        except JobCancelled as exc:
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.public_message,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    self.database.update_stage_attempt(
                        attempt_id,
                        "failed",
                        error_code=JobCancelled.error_code,
                        error_message=JobCancelled.public_message,
                    )
                except Exception:
                    pass
                raise JobCancelled() from exc
            error_code, error_message = _external_error_pair(exc)
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

    def execute_external_narration(
        self, run_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Queue an approved, billable ElevenLabs narration attempt."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "elevenlabs_tts":
            raise RequestValidationError(
                "This run is not configured for ElevenLabs narration.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if not isinstance(requested_stages, list) or _EXTERNAL_NARRATION_STAGE not in requested_stages:
            raise RequestValidationError(
                "The narration stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            estimate_minor = money_to_minor(run["estimated_cost"]["amount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RequestValidationError(
                "The run does not contain a valid external narration estimate.",
                code="cost_estimate_required",
            ) from exc
        if estimate_minor <= 0:
            raise RequestValidationError(
                "External narration requires a positive estimated cost.",
                code="cost_estimate_required",
            )
        # This is deliberately a literal second confirmation in the public
        # request.  The UI presents the exact payload character count and the
        # approved run cap before setting it, preventing an accidental spend
        # caused by a stale approval click.
        if not isinstance(body, dict) or body.get("confirm_billable") is not True:
            raise RequestValidationError(
                "confirm_billable must be true for external narration.",
                code="billable_confirmation_required",
            )
        approval = run.get("latest_approval")
        if not isinstance(approval, dict) or approval.get("decision") != "approved":
            raise RequestValidationError(
                "The run requires an approved cost gate before external narration.",
                code="approval_required",
            )
        try:
            approved_minor = money_to_minor(approval["approved_max"]["amount"])
            approved_currency = str(approval["approved_max"]["currency"]).upper()
            estimate_currency = str(run["estimated_cost"]["currency"]).upper()
        except (KeyError, TypeError, ValueError) as exc:
            raise RequestValidationError(
                "The run approval is invalid.", code="approval_rejected"
            ) from exc
        if approved_currency != estimate_currency or approved_minor < estimate_minor:
            raise RequestValidationError(
                "The approved cost cap is below the external narration estimate.",
                code="approval_rejected",
            )

        # No external module, worker, or secret is touched before every gate
        # above has passed.
        contract, payload = self._validate_external_narration_payload(body)
        cache_key = self._external_cache_key(contract, payload)
        if self.database.find_failed_stage_attempt(
            run["production_id"],
            _EXTERNAL_NARRATION_STAGE,
            cache_key,
            error_codes=tuple(_EXTERNAL_AMBIGUOUS_ERROR_CODES),
        ):
            raise RequestValidationError(
                "The previous external submission may have been accepted; resubmission is blocked.",
                code="ambiguous_submission",
            )
        attempt_payload = {
            "execution_profile": "elevenlabs_tts",
            "provider": _EXTERNAL_NARRATION_PROVIDER,
            "cache_key": cache_key,
            "estimated_cost": run["estimated_cost"],
            **self._external_audit_payload(contract, payload, cache_key=cache_key),
        }
        attempt = self.database.create_stage_attempt(
            run_id, _EXTERNAL_NARRATION_STAGE, cache_key, attempt_payload
        )
        try:
            job = self.jobs.submit(
                "external_narration",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _EXTERNAL_NARRATION_STAGE,
                    "execution_profile": "elevenlabs_tts",
                    "provider": _EXTERNAL_NARRATION_PROVIDER,
                    "cache_key": cache_key,
                    **self._external_audit_payload(contract, payload, cache_key=cache_key),
                },
                lambda _job_id, cancel_event: self._execute_external_narration(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    contract,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
            )
        except Exception as exc:
            error_code, error_message = _external_error_pair(exc)
            self.database.update_stage_attempt(
                attempt["id"], "failed", error_code=error_code, error_message=error_message
            )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["cache_key"] = cache_key
        return job

    def _validated_timeline_inputs(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve timeline clip IDs to immutable, workspace-local inputs.

        The browser is never allowed to provide paths, hashes, or media facts.
        Those values are derived from the registered artifact row and checked
        again immediately before the worker is queued.  The worker receives
        only these verified records, not the original request body.
        """

        production_id = run["production_id"]
        raw_clips = payload.get("clips")
        if not isinstance(raw_clips, list) or not raw_clips:
            raise RequestValidationError(
                "The timeline must contain at least one clip.",
                code="timeline_clips_invalid",
            )
        if len(raw_clips) > _MAX_LOCAL_TIMELINE_CLIPS:
            raise RequestValidationError(
                "The timeline contains too many clips.",
                code="timeline_clips_limit",
            )

        clips: list[dict[str, Any]] = []
        cache_clips: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for index, item in enumerate(raw_clips):
            if not isinstance(item, dict):
                raise RequestValidationError(
                    f"clips[{index}] is invalid.", code="timeline_clip_invalid"
                )
            artifact_id = item.get("video_artifact_id")
            start_ms = item.get("start_ms")
            end_ms = item.get("end_ms")
            if (
                not isinstance(start_ms, int)
                or isinstance(start_ms, bool)
                or not isinstance(end_ms, int)
                or isinstance(end_ms, bool)
                or start_ms < 0
                or end_ms <= start_ms
            ):
                raise RequestValidationError(
                    f"clips[{index}] timing is invalid.",
                    code="timeline_clip_timing_invalid",
                )
            artifact = self.database.get_artifact(artifact_id) if isinstance(artifact_id, str) else None
            if (
                artifact is None
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("kind") != "video"
                or not isinstance(artifact.get("rel_path"), str)
                or not isinstance(artifact.get("media_type"), str)
                or not artifact["media_type"].startswith("video/")
            ):
                raise RequestValidationError(
                    "The timeline clip is not an available video artifact for this production.",
                    code="timeline_video_not_available",
                )
            relative = artifact["rel_path"]
            try:
                path = workspace_path(self.workspace, relative, must_exist=True)
            except (SecurityError, OSError):
                raise RequestValidationError(
                    "The timeline clip path is not available.",
                    code="timeline_video_not_available",
                ) from None
            if (
                _has_symlink_component(self.workspace, relative)
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(relative)
            ):
                raise RequestValidationError(
                    "The timeline clip path is not safe.",
                    code="timeline_video_not_available",
                )
            try:
                stat = path.stat()
            except OSError:
                raise RequestValidationError(
                    "The timeline clip path is not available.",
                    code="timeline_video_not_available",
                ) from None
            if (
                stat.st_size <= 0
                or stat.st_size > _MAX_LOCAL_TIMELINE_VIDEO_BYTES
            ):
                raise RequestValidationError(
                    "The timeline clip size is outside the local limit.",
                    code="timeline_video_size_invalid",
                )
            aggregate_bytes += stat.st_size
            if aggregate_bytes > _MAX_LOCAL_TIMELINE_INPUT_BYTES:
                raise RequestValidationError(
                    "The timeline input size exceeds the local aggregate limit.",
                    code="timeline_input_size_invalid",
                )
            digest = _sha256_file(path)
            recorded_digest = artifact.get("sha256")
            if artifact.get("bytes") != stat.st_size:
                raise RequestValidationError(
                    "The timeline clip changed after it was indexed.",
                    code="timeline_video_changed",
                )
            if recorded_digest is not None and recorded_digest != digest:
                raise RequestValidationError(
                    "The timeline clip hash no longer matches its artifact record.",
                    code="timeline_video_changed",
                )
            normalized = {
                "video_artifact_id": artifact["id"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "source_path": path,
                "source_bytes": stat.st_size,
                "source_sha256": digest,
            }
            clips.append(normalized)
            cache_clips.append(
                {
                    "video_artifact_id": artifact["id"],
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    # Keep audit/cache-validation records workspace-relative.
                    # The worker resolves this path against the trusted
                    # workspace while the generation call receives the
                    # already-verified absolute Path above.
                    "source_path": relative_workspace_path(self.workspace, path),
                    "source_bytes": stat.st_size,
                    "source_sha256": digest,
                }
            )
        return {
            "clips": clips,
            "cache_clips": cache_clips,
            "aggregate_bytes": aggregate_bytes,
        }

    def _register_local_timeline_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_TIMELINE_ARTIFACTS
        ):
            raise LocalTimelineError(
                "The local timeline worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/timeline/{cache_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise LocalTimelineError(
                    "The local timeline worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise LocalTimelineError(
                    "The local timeline worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_TIMELINE_ARTIFACTS.get(path.name)
            if (
                expected is None
                or path.name in seen_names
                or relative != f"{expected_root}{path.name}"
                or _has_symlink_component(self.workspace, item["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(relative)
                or item.get("kind") != expected[0]
                or item.get("media_type", item.get("mime")) != expected[1]
                or item.get("name") != path.name
            ):
                raise LocalTimelineError(
                    "The local timeline worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise LocalTimelineError(
                    "The local timeline worker returned mismatched artifact metadata.",
                    code="invalid_worker_result",
                )
            seen_names.add(path.name)
            validated.append(
                {
                    "id": stable_id("art", relative.casefold()),
                    "rel_path": relative,
                    "name": path.name,
                    "kind": expected[0],
                    "media_type": expected[1],
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": digest,
                    "is_heavy": stat.st_size > 10 * 1024 * 1024,
                }
            )
        if seen_names != set(_LOCAL_TIMELINE_ARTIFACTS):
            raise LocalTimelineError(
                "The local timeline worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in validated
        ]

    def _cached_local_timeline_result(
        self,
        cache_key: str,
        production_id: str,
        expected_clips: list[dict[str, Any]],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | None:
        previous = self.database.find_successful_stage_attempt(
            production_id, _LOCAL_TIMELINE_STAGE, cache_key
        )
        if not previous or not isinstance(previous.get("result"), dict):
            return None
        prior_result = previous["result"]
        expected_duration_ms = sum(
            item["end_ms"] - item["start_ms"] for item in expected_clips
        )

        # A cache hit may point to the physical files owned by an older run.
        # Resolve that immutable chain before asking the worker to validate a
        # run-local output directory.  Without this, a third run would inspect
        # the second run's empty directory and needlessly re-render the same
        # content.
        source_attempt = previous
        source_result = prior_result
        visited_attempt_ids = {previous["id"]}

        def artifact_signature(result: dict[str, Any]) -> tuple[tuple[Any, ...], ...] | None:
            raw = result.get("artifacts")
            if not isinstance(raw, list):
                return None
            entries: list[tuple[Any, ...]] = []
            for item in raw:
                if not isinstance(item, dict):
                    return None
                entries.append(
                    tuple(
                        item.get(field)
                        for field in ("name", "id", "rel_path", "bytes", "sha256")
                    )
                )
            return tuple(sorted(entries, key=lambda item: str(item[0])))

        while source_result.get("cache_source_attempt_id") is not None:
            source_id = source_result.get("cache_source_attempt_id")
            if (
                not isinstance(source_id, str)
                or source_id in visited_attempt_ids
                or len(visited_attempt_ids) >= 128
                or source_result.get("cache_hit") is not True
            ):
                return None
            linked = self.database.get_stage_attempt(source_id)
            if (
                linked is None
                or linked.get("production_id") != production_id
                or linked.get("stage") != _LOCAL_TIMELINE_STAGE
                or linked.get("status") != "succeeded"
                or linked.get("cache_key") != cache_key
                or not isinstance(linked.get("result"), dict)
            ):
                return None
            linked_result = linked["result"]
            linked_cache_hit = linked_result.get("cache_hit")
            if not isinstance(linked_cache_hit, bool):
                return None
            try:
                timeline_public_result(
                    source_result,
                    expected_cache_key=cache_key,
                    expected_duration_ms=expected_duration_ms,
                    artifacts=[],
                    cache_hit=True,
                )
                timeline_public_result(
                    linked_result,
                    expected_cache_key=cache_key,
                    expected_duration_ms=expected_duration_ms,
                    artifacts=[],
                    cache_hit=linked_cache_hit,
                )
            except LocalTimelineError:
                return None
            if artifact_signature(source_result) != artifact_signature(linked_result):
                return None
            visited_attempt_ids.add(source_id)
            source_attempt = linked
            source_result = linked_result
        try:
            from . import timeline

            physical_result = _call_local_worker(
                timeline.validate_local_timeline_outputs,
                self.workspace,
                production_id=production_id,
                run_id=source_attempt["run_id"],
                cache_key=cache_key,
                clips=expected_clips,
                cancel_event=cancel_event,
            )
        except (ImportError, AttributeError, LocalTimelineError, OSError):
            return None
        physical_artifacts = physical_result.get("artifacts")
        if (
            not isinstance(physical_artifacts, list)
            or len(physical_artifacts) != len(_LOCAL_TIMELINE_ARTIFACTS)
            or {
                item.get("name")
                for item in physical_artifacts
                if isinstance(item, dict)
            }
            != set(_LOCAL_TIMELINE_ARTIFACTS)
        ):
            return None
        physical_by_name = {
            item.get("name"): item
            for item in physical_artifacts
            if isinstance(item, dict)
        }
        prior_artifacts = prior_result.get("artifacts")
        if not isinstance(prior_artifacts, list) or len(prior_artifacts) != len(
            _LOCAL_TIMELINE_ARTIFACTS
        ):
            return None
        source_root = (
            f"outputs/studio/runs/{source_attempt['run_id']}/timeline/{cache_key}/"
        )
        verified: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if artifact is None or artifact["name"] in seen_names:
                return None
            expected = _LOCAL_TIMELINE_ARTIFACTS.get(artifact["name"])
            physical = physical_by_name.get(artifact["name"])
            if (
                expected is None
                or not isinstance(physical, dict)
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("kind") != expected[0]
                or artifact.get("media_type") != expected[1]
                or artifact.get("rel_path") != f"{source_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
                or physical.get("bytes") != artifact.get("bytes")
                or physical.get("sha256") != artifact.get("sha256")
            ):
                return None
            try:
                path = workspace_path(self.workspace, artifact["rel_path"], must_exist=True)
            except (SecurityError, OSError):
                return None
            try:
                stat = path.stat()
            except OSError:
                return None
            if (
                _has_symlink_component(self.workspace, artifact["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(artifact["rel_path"])
                or stat.st_size != artifact.get("bytes")
                or not isinstance(artifact.get("sha256"), str)
                or _sha256_file(path) != artifact["sha256"]
            ):
                return None
            seen_names.add(artifact["name"])
            verified.append(artifact)
        if seen_names != set(_LOCAL_TIMELINE_ARTIFACTS):
            return None
        try:
            prior_cache_hit = prior_result.get("cache_hit")
            if not isinstance(prior_cache_hit, bool):
                return None
            prior_public = timeline_public_result(
                prior_result,
                expected_cache_key=cache_key,
                expected_duration_ms=expected_duration_ms,
                artifacts=verified,
                cache_hit=prior_cache_hit,
            )
            physical_for_public = dict(physical_result)
            physical_for_public["cache_hit"] = True
            cached = timeline_public_result(
                physical_for_public,
                expected_cache_key=cache_key,
                expected_duration_ms=expected_duration_ms,
                artifacts=verified,
                cache_hit=True,
            )
        except LocalTimelineError:
            return None
        if prior_public.get("duration_ms") != cached.get("duration_ms"):
            return None
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_local_timeline(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        cache_key: str,
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        self.database.update_stage_attempt(attempt_id, "running")
        expected_clips = inputs["cache_clips"]
        expected_duration_ms = sum(
            item["end_ms"] - item["start_ms"] for item in expected_clips
        )
        try:
            _raise_if_cancelled(cancel_event)
            cached = self._cached_local_timeline_result(
                cache_key, production_id, expected_clips, cancel_event
            )
            if cached is not None:
                result = cached
            else:
                try:
                    from . import timeline
                except (ImportError, AttributeError) as exc:
                    raise LocalTimelineError(
                        "The local timeline worker is not installed.",
                        code="local_worker_unavailable",
                    ) from exc
                try:
                    raw = _call_local_worker(
                        timeline.generate_local_timeline,
                        self.workspace,
                        production_id=production_id,
                        run_id=run_id,
                        cache_key=cache_key,
                        clips=inputs["clips"],
                        cancel_event=cancel_event,
                    )
                except LocalTimelineError:
                    raise
                except Exception as exc:
                    raise LocalTimelineError(
                        "The local timeline worker failed.",
                        code="local_timeline_failed",
                    ) from exc
                _raise_if_cancelled(cancel_event)
                raw_cache_hit = raw.get("cache_hit", False) if isinstance(raw, dict) else False
                result = timeline_public_result(
                    raw,
                    expected_cache_key=cache_key,
                    expected_duration_ms=expected_duration_ms,
                    artifacts=[],
                    cache_hit=raw_cache_hit if isinstance(raw_cache_hit, bool) else False,
                )
                physical_result = _call_local_worker(
                    timeline.validate_local_timeline_outputs,
                    self.workspace,
                    production_id=production_id,
                    run_id=run_id,
                    cache_key=cache_key,
                    clips=inputs["clips"],
                    cancel_event=cancel_event,
                )
                physical_for_public = dict(physical_result)
                physical_for_public["cache_hit"] = raw_cache_hit
                physical_public = timeline_public_result(
                    physical_for_public,
                    expected_cache_key=cache_key,
                    expected_duration_ms=expected_duration_ms,
                    artifacts=[],
                    cache_hit=raw_cache_hit,
                )
                if result.get("duration_ms") != physical_public.get("duration_ms"):
                    raise LocalTimelineError(
                        "The local timeline worker returned mismatched timing.",
                        code="invalid_worker_result",
                    )
                physical_artifacts = physical_result.get("artifacts")
                raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
                if (
                    not isinstance(physical_artifacts, list)
                    or not isinstance(raw_artifacts, list)
                    or len(physical_artifacts) != len(_LOCAL_TIMELINE_ARTIFACTS)
                    or {
                        item.get("name")
                        for item in physical_artifacts
                        if isinstance(item, dict)
                    }
                    != set(_LOCAL_TIMELINE_ARTIFACTS)
                ):
                    raise LocalTimelineError(
                        "The local timeline worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                physical_by_name = {
                    item.get("name"): item
                    for item in physical_artifacts
                    if isinstance(item, dict)
                }
                for item in raw_artifacts:
                    if not isinstance(item, dict):
                        raise LocalTimelineError(
                            "The local timeline worker returned invalid artifacts.",
                            code="invalid_worker_result",
                        )
                    name = Path(str(item.get("rel_path") or "")).name
                    physical = physical_by_name.get(name)
                    if (
                        not isinstance(physical, dict)
                        or item.get("bytes") != physical.get("bytes")
                        or item.get("sha256") != physical.get("sha256")
                    ):
                        raise LocalTimelineError(
                            "The local timeline worker returned mismatched artifacts.",
                            code="invalid_worker_result",
                        )
                artifacts = self._register_local_timeline_artifacts(
                    production_id,
                    run_id,
                    cache_key,
                    raw_artifacts,
                )
                result = physical_public
                result["artifacts"] = artifacts
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(attempt_id, result, cancel_event)
        except JobCancelled as exc:
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.public_message,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    self.database.update_stage_attempt(
                        attempt_id,
                        "failed",
                        error_code=JobCancelled.error_code,
                        error_message=JobCancelled.public_message,
                    )
                except Exception:
                    pass
                raise JobCancelled() from exc
            error_code, error_message = safe_timeline_error(exc)
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

    def execute_local_timeline(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Queue a zero-cost local hard-cut timeline composition attempt."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "local_sapi":
            raise RequestValidationError(
                "This run is not configured for local timeline composition.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if not isinstance(requested_stages, list) or _LOCAL_TIMELINE_STAGE not in requested_stages:
            raise RequestValidationError(
                "The timeline stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_local_timeline_payload(body)
        except LocalTimelineValidationError as exc:
            code = getattr(exc, "code", None) or getattr(
                exc, "error_code", "invalid_local_timeline_request"
            )
            raise RequestValidationError(str(exc), code=str(code)) from exc
        inputs = self._validated_timeline_inputs(run, payload)
        try:
            from . import timeline

            cache_key = timeline.timeline_cache_key(inputs["cache_clips"])
        except (ImportError, AttributeError) as exc:
            raise RequestValidationError(
                "The local timeline worker is not installed.",
                code="local_worker_unavailable",
            ) from exc
        except LocalTimelineError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9A-F]{64}", cache_key):
            raise RequestValidationError(
                "The local timeline worker returned an invalid cache key.",
                code="invalid_worker_result",
            )
        audit = timeline_audit_payload(inputs["cache_clips"], cache_key=cache_key)
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_TIMELINE_STAGE,
            cache_key,
            {"execution_profile": "local_sapi", **audit},
        )
        try:
            job = self.jobs.submit(
                "local_timeline",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_TIMELINE_STAGE,
                    "execution_profile": "local_sapi",
                    **audit,
                },
                lambda _job_id, cancel_event: self._execute_local_timeline(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    inputs,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
            )
        except Exception as exc:
            error_code, error_message = safe_timeline_error(exc)
            self.database.update_stage_attempt(
                attempt["id"],
                "failed",
                error_code=error_code,
                error_message=error_message,
            )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["cache_key"] = cache_key
        return job

    def _validated_assembly_inputs(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve registered media without trusting request-supplied paths."""

        production_id = run["production_id"]
        video = self.database.get_artifact(payload["video_artifact_id"])
        if (
            video is None
            or video.get("production_id") != production_id
            or not video.get("available")
            or video.get("kind") != "video"
            or not isinstance(video.get("rel_path"), str)
            or not isinstance(video.get("media_type"), str)
            or not video["media_type"].startswith("video/")
        ):
            raise RequestValidationError(
                "The source video is not an available artifact for this production.",
                code="assembly_video_not_available",
            )
        try:
            video_path = workspace_path(self.workspace, video["rel_path"], must_exist=True)
        except (SecurityError, OSError):
            raise RequestValidationError(
                "The source video path is not available.",
                code="assembly_video_not_available",
            ) from None
        if (
            _has_symlink_component(self.workspace, video["rel_path"])
            or video_path.is_symlink()
            or not video_path.is_file()
            or sensitive_artifact_path(video["rel_path"])
        ):
            raise RequestValidationError(
                "The source video path is not safe.",
                code="assembly_video_not_available",
            )
        video_stat = video_path.stat()
        if video_stat.st_size <= 0 or video_stat.st_size > 2 * 1024 * 1024 * 1024:
            raise RequestValidationError(
                "The source video size is outside the local assembly limit.",
                code="assembly_video_size_invalid",
            )
        if video.get("bytes") != video_stat.st_size:
            raise RequestValidationError(
                "The source video changed after it was indexed.",
                code="assembly_video_changed",
            )
        source_video_sha256 = _sha256_file(video_path)
        recorded_video_hash = video.get("sha256")
        if recorded_video_hash is not None and recorded_video_hash != source_video_sha256:
            raise RequestValidationError(
                "The source video hash no longer matches its artifact record.",
                code="assembly_video_changed",
            )

        narration_attempt = self.database.get_stage_attempt(
            payload["narration_attempt_id"]
        )
        if (
            narration_attempt is None
            or narration_attempt.get("run_id") != run["id"]
            or narration_attempt.get("production_id") != production_id
            or narration_attempt.get("stage") != _LOCAL_NARRATION_STAGE
            or narration_attempt.get("status") != "succeeded"
            or not isinstance(narration_attempt.get("result"), dict)
        ):
            raise RequestValidationError(
                "The narration attempt is not a succeeded attempt for this run.",
                code="assembly_narration_not_available",
            )
        narration_result = narration_attempt["result"]
        raw_artifacts = narration_result.get("artifacts")
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_NARRATION_ARTIFACTS
        ):
            raise RequestValidationError(
                "The narration attempt has an incomplete artifact set.",
                code="assembly_narration_not_available",
            )
        cache_hit = narration_result.get("cache_hit")
        if not isinstance(cache_hit, bool):
            raise RequestValidationError(
                "The narration attempt metadata is not valid.",
                code="assembly_narration_not_available",
            )
        # A successful cache hit may point at a physical narration owned by a
        # prior run in the same production.  Follow the immutable source chain
        # to that owner before checking paths; accepting the current run ID
        # here would either reject valid reuse or tempt the worker to copy an
        # unverified file.
        narration_owner_attempt = narration_attempt
        narration_owner_result = narration_result
        visited_narration_attempts = {narration_attempt["id"]}
        while narration_owner_result.get("cache_source_attempt_id") is not None:
            source_id = narration_owner_result.get("cache_source_attempt_id")
            if (
                not isinstance(source_id, str)
                or source_id in visited_narration_attempts
                or narration_owner_result.get("cache_hit") is not True
                or len(visited_narration_attempts) >= 128
            ):
                raise RequestValidationError(
                    "The narration cache lineage is not valid.",
                    code="assembly_narration_not_available",
                )
            source_attempt = self.database.get_stage_attempt(source_id)
            if (
                source_attempt is None
                or source_attempt.get("production_id") != production_id
                or source_attempt.get("stage") != _LOCAL_NARRATION_STAGE
                or source_attempt.get("status") != "succeeded"
                or source_attempt.get("cache_key") != narration_attempt.get("cache_key")
                or not isinstance(source_attempt.get("result"), dict)
            ):
                raise RequestValidationError(
                    "The narration cache lineage is not valid.",
                    code="assembly_narration_not_available",
                )
            narration_owner_attempt = source_attempt
            narration_owner_result = source_attempt["result"]
            visited_narration_attempts.add(source_id)
        narration_root = (
            f"outputs/studio/runs/{narration_owner_attempt['run_id']}/narration/"
            f"{narration_attempt['cache_key']}/"
        )
        owner_artifacts_by_name: dict[str, dict[str, Any]] = {}
        if narration_owner_attempt["id"] != narration_attempt["id"]:
            owner_raw_artifacts = narration_owner_result.get("artifacts")
            if not isinstance(owner_raw_artifacts, list):
                raise RequestValidationError(
                    "The narration cache lineage is incomplete.",
                    code="assembly_narration_not_available",
                )
            owner_artifacts_by_name = {
                item.get("name"): item
                for item in owner_raw_artifacts
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
        narration_artifacts: list[dict[str, Any]] = []
        narration_paths: dict[str, Path] = {}
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise RequestValidationError(
                    "The narration attempt has invalid artifact metadata.",
                    code="assembly_narration_not_available",
                )
            artifact = self.database.get_artifact(item["id"])
            if artifact is None or artifact["name"] in seen_names:
                raise RequestValidationError(
                    "The narration attempt artifact is unavailable.",
                    code="assembly_narration_not_available",
                )
            expected = _LOCAL_NARRATION_ARTIFACTS.get(artifact["name"])
            owner_item = owner_artifacts_by_name.get(artifact["name"])
            if (
                expected is None
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("kind") != expected[0]
                or artifact.get("media_type") != expected[1]
                or artifact.get("rel_path") != f"{narration_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
                or (
                    owner_item is not None
                    and any(
                        owner_item.get(field) != item.get(field)
                        for field in ("id", "rel_path", "bytes", "sha256")
                    )
                )
            ):
                raise RequestValidationError(
                    "The narration attempt artifact does not match its record.",
                    code="assembly_narration_not_available",
                )
            try:
                path = workspace_path(
                    self.workspace, artifact["rel_path"], must_exist=True
                )
            except (SecurityError, OSError):
                raise RequestValidationError(
                    "The narration attempt artifact is unavailable.",
                    code="assembly_narration_not_available",
                ) from None
            stat = path.stat()
            if (
                _has_symlink_component(self.workspace, artifact["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(artifact["rel_path"])
                or stat.st_size != artifact.get("bytes")
                or not isinstance(artifact.get("sha256"), str)
                or _sha256_file(path) != artifact["sha256"]
            ):
                raise RequestValidationError(
                    "The narration attempt artifact changed after generation.",
                    code="assembly_narration_changed",
                )
            seen_names.add(artifact["name"])
            narration_artifacts.append(artifact)
            narration_paths[artifact["name"]] = path
        if seen_names != set(_LOCAL_NARRATION_ARTIFACTS):
            raise RequestValidationError(
                "The narration attempt has an incomplete artifact set.",
                code="assembly_narration_not_available",
            )
        try:
            if run.get("execution_profile") == "elevenlabs_tts":
                contract = _load_external_tts_contract()
                self._external_public_result(
                    contract,
                    narration_result,
                    expected_cache_key=narration_attempt["cache_key"],
                    artifacts=narration_artifacts,
                    cache_hit=cache_hit,
                )
            elif run.get("execution_profile") == "local_sapi":
                public_result(
                    narration_result,
                    expected_cache_key=narration_attempt["cache_key"],
                    artifacts=narration_artifacts,
                    cache_hit=cache_hit,
                )
            else:
                raise ValueError("unknown narration execution profile")
        except Exception:
            raise RequestValidationError(
                "The narration attempt metadata is not valid.",
                code="assembly_narration_not_available",
            ) from None
        return {
            "video": video,
            "video_path": video_path,
            "source_video_sha256": source_video_sha256,
            "narration_attempt": narration_attempt,
            "narration_wav": narration_paths["narration.wav"],
            "narration_wav_sha256": next(
                item["sha256"]
                for item in narration_artifacts
                if item["name"] == "narration.wav"
            ),
            "captions_srt": narration_paths["captions.srt"],
            "captions_sha256": next(
                item["sha256"]
                for item in narration_artifacts
                if item["name"] == "captions.srt"
            ),
        }

    def _register_local_assembly_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        include_captioned: bool,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        expected_artifacts = dict(_LOCAL_ASSEMBLY_ARTIFACTS)
        if not include_captioned:
            expected_artifacts.pop("master-captioned.mp4")
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            expected_artifacts
        ):
            raise LocalAssemblyError(
                "The local assembly worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/assembly/{cache_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise LocalAssemblyError(
                    "The local assembly worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise LocalAssemblyError(
                    "The local assembly worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = expected_artifacts.get(path.name)
            if (
                expected is None
                or path.name in seen_names
                or relative != f"{expected_root}{path.name}"
                or _has_symlink_component(self.workspace, item["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(relative)
                or item.get("kind") != expected[0]
                or item.get("media_type", item.get("mime")) != expected[1]
            ):
                raise LocalAssemblyError(
                    "The local assembly worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise LocalAssemblyError(
                    "The local assembly worker returned mismatched artifact metadata.",
                    code="invalid_worker_result",
                )
            seen_names.add(path.name)
            validated.append(
                {
                    "id": stable_id("art", relative.casefold()),
                    "rel_path": relative,
                    "name": path.name,
                    "kind": expected[0],
                    "media_type": expected[1],
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": digest,
                    "is_heavy": stat.st_size > 10 * 1024 * 1024,
                }
            )
        if seen_names != set(expected_artifacts):
            raise LocalAssemblyError(
                "The local assembly worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in validated
        ]

    def _cached_local_assembly_result(
        self,
        cache_key: str,
        production_id: str,
        expected_hashes: dict[str, str],
        include_captioned: bool,
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | None:
        previous = self.database.find_successful_stage_attempt(
            production_id, _LOCAL_ASSEMBLY_STAGE, cache_key
        )
        if not previous or not isinstance(previous.get("result"), dict):
            return None
        try:
            from . import assembly

            physical_result = _call_local_worker(
                assembly.validate_local_assembly_outputs,
                self.workspace,
                production_id=production_id,
                run_id=previous["run_id"],
                cache_key=cache_key,
                source_video=inputs["video_path"],
                narration_wav=inputs["narration_wav"],
                captions_srt=inputs["captions_srt"],
                include_captioned=include_captioned,
                cancel_event=cancel_event,
            )
        except (ImportError, AttributeError, LocalAssemblyError, OSError):
            return None
        physical_artifacts = physical_result.get("artifacts")
        if not isinstance(physical_artifacts, list):
            return None
        physical_by_name = {
            item.get("name"): item for item in physical_artifacts if isinstance(item, dict)
        }
        prior_result = previous["result"]
        expected_artifacts = dict(_LOCAL_ASSEMBLY_ARTIFACTS)
        if not include_captioned:
            expected_artifacts.pop("master-captioned.mp4")
        prior_artifacts = prior_result.get("artifacts")
        if not isinstance(prior_artifacts, list) or len(prior_artifacts) != len(
            expected_artifacts
        ):
            return None
        source_root = (
            f"outputs/studio/runs/{previous['run_id']}/assembly/{cache_key}/"
        )
        verified: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if artifact is None or artifact["name"] in seen_names:
                return None
            expected = expected_artifacts.get(artifact["name"])
            physical = physical_by_name.get(artifact["name"])
            if (
                expected is None
                or not isinstance(physical, dict)
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("kind") != expected[0]
                or artifact.get("media_type") != expected[1]
                or artifact.get("rel_path") != f"{source_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
                or physical.get("bytes") != artifact.get("bytes")
                or physical.get("sha256") != artifact.get("sha256")
            ):
                return None
            try:
                path = workspace_path(
                    self.workspace, artifact["rel_path"], must_exist=True
                )
            except (SecurityError, OSError):
                return None
            stat = path.stat()
            if (
                _has_symlink_component(self.workspace, artifact["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(artifact["rel_path"])
                or stat.st_size != artifact.get("bytes")
                or not isinstance(artifact.get("sha256"), str)
                or _sha256_file(path) != artifact["sha256"]
            ):
                return None
            seen_names.add(artifact["name"])
            verified.append(artifact)
        if seen_names != set(expected_artifacts):
            return None
        cached_raw = dict(prior_result)
        cached_raw["cache_hit"] = True
        try:
            prior_public = assembly_public_result(
                cached_raw,
                expected_cache_key=cache_key,
                expected_hashes=expected_hashes,
                expected_include_captioned=include_captioned,
                artifacts=verified,
                cache_hit=True,
            )
            physical_for_public = dict(physical_result)
            physical_for_public["cache_hit"] = True
            cached = assembly_public_result(
                physical_for_public,
                expected_cache_key=cache_key,
                expected_hashes=expected_hashes,
                expected_include_captioned=include_captioned,
                artifacts=verified,
                cache_hit=True,
            )
        except LocalAssemblyError:
            return None
        if prior_public.get("duration_ms") != cached.get("duration_ms"):
            return None
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_local_assembly(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        cache_key: str,
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        self.database.update_stage_attempt(attempt_id, "running")
        expected_hashes = {
            "source_video_sha256": inputs["source_video_sha256"],
            "narration_wav_sha256": inputs["narration_wav_sha256"],
            "captions_sha256": inputs["captions_sha256"],
        }
        try:
            _raise_if_cancelled(cancel_event)
            cached = self._cached_local_assembly_result(
                cache_key,
                production_id,
                expected_hashes,
                payload["include_captioned"],
                inputs,
                cancel_event,
            )
            if cached is not None:
                result = cached
            else:
                try:
                    from . import assembly
                except (ImportError, AttributeError) as exc:
                    raise LocalAssemblyError(
                        "The local assembly worker is not installed.",
                        code="local_worker_unavailable",
                    ) from exc
                try:
                    raw = _call_local_worker(
                        assembly.generate_local_assembly,
                        self.workspace,
                        production_id=production_id,
                        run_id=run_id,
                        cache_key=cache_key,
                        source_video=inputs["video_path"],
                        narration_wav=inputs["narration_wav"],
                        captions_srt=inputs["captions_srt"],
                        include_captioned=payload["include_captioned"],
                        cancel_event=cancel_event,
                    )
                except LocalAssemblyError:
                    raise
                except Exception as exc:
                    raise LocalAssemblyError(
                        "The local assembly worker failed.",
                        code="local_assembly_failed",
                    ) from exc
                _raise_if_cancelled(cancel_event)
                raw_cache_hit = (
                    raw.get("cache_hit", False) if isinstance(raw, dict) else False
                )
                result = assembly_public_result(
                    raw,
                    expected_cache_key=cache_key,
                    expected_hashes=expected_hashes,
                    expected_include_captioned=payload["include_captioned"],
                    artifacts=[],
                    cache_hit=raw_cache_hit
                    if isinstance(raw_cache_hit, bool)
                    else False,
                )
                physical_result = _call_local_worker(
                    assembly.validate_local_assembly_outputs,
                    self.workspace,
                    production_id=production_id,
                    run_id=run_id,
                    cache_key=cache_key,
                    source_video=inputs["video_path"],
                    narration_wav=inputs["narration_wav"],
                    captions_srt=inputs["captions_srt"],
                    include_captioned=payload["include_captioned"],
                    cancel_event=cancel_event,
                )
                physical_for_public = dict(physical_result)
                physical_for_public["cache_hit"] = raw_cache_hit
                physical_public = assembly_public_result(
                    physical_for_public,
                    expected_cache_key=cache_key,
                    expected_hashes=expected_hashes,
                    expected_include_captioned=payload["include_captioned"],
                    artifacts=[],
                    cache_hit=raw_cache_hit,
                )
                if result.get("duration_ms") != physical_public.get("duration_ms"):
                    raise LocalAssemblyError(
                        "The local assembly worker returned mismatched timing.",
                        code="invalid_worker_result",
                    )
                physical_artifacts = physical_result.get("artifacts")
                raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
                if not isinstance(physical_artifacts, list) or not isinstance(
                    raw_artifacts, list
                ):
                    raise LocalAssemblyError(
                        "The local assembly worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                physical_by_name = {
                    item.get("name"): item
                    for item in physical_artifacts
                    if isinstance(item, dict)
                }
                for item in raw_artifacts:
                    if not isinstance(item, dict):
                        raise LocalAssemblyError(
                            "The local assembly worker returned invalid artifacts.",
                            code="invalid_worker_result",
                        )
                    name = Path(str(item.get("rel_path") or "")).name
                    physical = physical_by_name.get(name)
                    if (
                        not isinstance(physical, dict)
                        or item.get("bytes") != physical.get("bytes")
                        or item.get("sha256") != physical.get("sha256")
                    ):
                        raise LocalAssemblyError(
                            "The local assembly worker returned mismatched artifacts.",
                            code="invalid_worker_result",
                        )
                artifacts = self._register_local_assembly_artifacts(
                    production_id,
                    run_id,
                    cache_key,
                    payload["include_captioned"],
                    raw.get("artifacts") if isinstance(raw, dict) else None,
                )
                result = physical_public
                result["artifacts"] = artifacts
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(attempt_id, result, cancel_event)
        except JobCancelled as exc:
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.public_message,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    self.database.update_stage_attempt(
                        attempt_id,
                        "failed",
                        error_code=JobCancelled.error_code,
                        error_message=JobCancelled.public_message,
                    )
                except Exception:
                    pass
                raise JobCancelled() from exc
            error_code, error_message = safe_assembly_error(exc)
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

    def execute_local_assembly(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Queue a zero-cost local FFmpeg assembly attempt."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in _LOCAL_DOWNSTREAM_PROFILES:
            raise RequestValidationError(
                "This run is not configured for local assembly.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        required_stages = {_LOCAL_NARRATION_STAGE, _LOCAL_ASSEMBLY_STAGE}
        if not isinstance(requested_stages, list) or not required_stages.issubset(requested_stages):
            raise RequestValidationError(
                "The narration and assembly stages were not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_local_assembly_payload(body)
        except LocalAssemblyValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        inputs = self._validated_assembly_inputs(run, payload)
        try:
            from . import assembly

            cache_key = assembly.assembly_cache_key(
                inputs["source_video_sha256"],
                inputs["narration_wav_sha256"],
                inputs["captions_sha256"],
                payload["include_captioned"],
            )
        except (ImportError, AttributeError) as exc:
            raise RequestValidationError(
                "The local assembly worker is not installed.",
                code="local_worker_unavailable",
            ) from exc
        except LocalAssemblyError as exc:
            raise RequestValidationError(
                str(exc.public_message),
                code=str(exc.error_code)[:128],
            ) from exc
        if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9A-F]{64}", cache_key):
            raise RequestValidationError(
                "The local assembly worker returned an invalid cache key.",
                code="invalid_worker_result",
            )
        expected_hashes = {
            "source_video_sha256": inputs["source_video_sha256"],
            "narration_wav_sha256": inputs["narration_wav_sha256"],
            "captions_sha256": inputs["captions_sha256"],
        }
        audit = assembly_audit_payload(payload, **expected_hashes)
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_ASSEMBLY_STAGE,
            cache_key,
            {
                "execution_profile": run["execution_profile"],
                "cache_key": cache_key,
                **audit,
            },
        )
        try:
            job = self.jobs.submit(
                "local_assembly",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_ASSEMBLY_STAGE,
                    "execution_profile": run["execution_profile"],
                    "cache_key": cache_key,
                    **audit,
                },
                lambda _job_id, cancel_event: self._execute_local_assembly(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    inputs,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
            )
        except Exception as exc:
            error_code, error_message = safe_assembly_error(exc)
            self.database.update_stage_attempt(
                attempt["id"],
                "failed",
                error_code=error_code,
                error_message=error_message,
            )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["cache_key"] = cache_key
        return job

    def _validated_qc_inputs(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve one succeeded assembly master from immutable Studio records."""

        production_id = run["production_id"]
        assembly_attempt = self.database.get_stage_attempt(
            payload["assembly_attempt_id"]
        )
        if (
            assembly_attempt is None
            or assembly_attempt.get("run_id") != run["id"]
            or assembly_attempt.get("production_id") != production_id
            or assembly_attempt.get("stage") != _LOCAL_ASSEMBLY_STAGE
            or assembly_attempt.get("status") != "succeeded"
            or not isinstance(assembly_attempt.get("result"), dict)
        ):
            raise RequestValidationError(
                "The assembly attempt is not a succeeded attempt for this run.",
                code="qc_assembly_not_available",
            )
        assembly_result = assembly_attempt["result"]
        include_captioned = assembly_result.get("include_captioned")
        cache_hit = assembly_result.get("cache_hit")
        expected_hashes = {
            field: assembly_result.get(field)
            for field in (
                "source_video_sha256",
                "narration_wav_sha256",
                "captions_sha256",
            )
        }
        if not isinstance(include_captioned, bool) or not isinstance(cache_hit, bool):
            raise RequestValidationError(
                "The assembly attempt metadata is not valid.",
                code="qc_assembly_not_available",
            )
        try:
            assembly_public_result(
                assembly_result,
                expected_cache_key=assembly_attempt["cache_key"],
                expected_hashes=expected_hashes,
                expected_include_captioned=include_captioned,
                artifacts=[],
                cache_hit=cache_hit,
            )
        except LocalAssemblyError:
            raise RequestValidationError(
                "The assembly attempt metadata is not valid.",
                code="qc_assembly_not_available",
            ) from None

        expected_name = (
            "master-clean.mp4"
            if payload["variant"] == "clean"
            else "master-captioned.mp4"
        )
        if expected_name == "master-captioned.mp4" and not include_captioned:
            raise RequestValidationError(
                "The selected assembly attempt has no captioned master.",
                code="qc_variant_not_available",
            )
        raw_artifacts = assembly_result.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise RequestValidationError(
                "The assembly attempt artifact is not available.",
                code="qc_assembly_not_available",
            )
        selected = [
            item
            for item in raw_artifacts
            if isinstance(item, dict) and item.get("name") == expected_name
        ]
        if len(selected) != 1 or not isinstance(selected[0].get("id"), str):
            raise RequestValidationError(
                "The selected assembly master is not available.",
                code="qc_variant_not_available",
            )
        result_artifact = selected[0]
        artifact = self.database.get_artifact(result_artifact["id"])
        if (
            artifact is None
            or artifact.get("production_id") != production_id
            or not artifact.get("available")
            or artifact.get("origin") != "studio"
            or artifact.get("name") != expected_name
            or artifact.get("kind") != "video"
            or artifact.get("media_type") != "video/mp4"
            or result_artifact.get("bytes") != artifact.get("bytes")
            or result_artifact.get("sha256") != artifact.get("sha256")
            or not isinstance(artifact.get("rel_path"), str)
        ):
            raise RequestValidationError(
                "The selected assembly master is not available.",
                code="qc_variant_not_available",
            )

        # A cache hit may intentionally reuse a content-addressed assembly from
        # an earlier run in the same production.  Follow the immutable source
        # chain to its physical owner, rejecting cycles, cross-production
        # links, changed provenance, or an artifact that is not present in
        # every linked attempt result.
        source_attempt = assembly_attempt
        source_result = assembly_result
        visited_attempt_ids = {assembly_attempt["id"]}
        while source_result.get("cache_source_attempt_id") is not None:
            cache_source_attempt_id = source_result.get("cache_source_attempt_id")
            if (
                not isinstance(cache_source_attempt_id, str)
                or cache_source_attempt_id in visited_attempt_ids
                or len(visited_attempt_ids) >= 128
                or source_result.get("cache_hit") is not True
            ):
                raise RequestValidationError(
                    "The assembly cache lineage is not valid.",
                    code="qc_assembly_not_available",
                )
            linked_attempt = self.database.get_stage_attempt(cache_source_attempt_id)
            if (
                linked_attempt is None
                or linked_attempt.get("production_id") != production_id
                or linked_attempt.get("stage") != _LOCAL_ASSEMBLY_STAGE
                or linked_attempt.get("status") != "succeeded"
                or linked_attempt.get("cache_key") != assembly_attempt.get("cache_key")
                or not isinstance(linked_attempt.get("result"), dict)
            ):
                raise RequestValidationError(
                    "The assembly cache lineage is not valid.",
                    code="qc_assembly_not_available",
                )
            linked_result = linked_attempt["result"]
            linked_cache_hit = linked_result.get("cache_hit")
            if not isinstance(linked_cache_hit, bool):
                raise RequestValidationError(
                    "The assembly cache lineage is not valid.",
                    code="qc_assembly_not_available",
                )
            try:
                assembly_public_result(
                    linked_result,
                    expected_cache_key=assembly_attempt["cache_key"],
                    expected_hashes=expected_hashes,
                    expected_include_captioned=include_captioned,
                    artifacts=[],
                    cache_hit=linked_cache_hit,
                )
            except LocalAssemblyError:
                raise RequestValidationError(
                    "The assembly cache lineage is not valid.",
                    code="qc_assembly_not_available",
                ) from None
            linked_artifacts = linked_result.get("artifacts")
            linked_selected = [
                item
                for item in linked_artifacts
                if isinstance(item, dict) and item.get("name") == expected_name
            ] if isinstance(linked_artifacts, list) else []
            if len(linked_selected) != 1 or any(
                linked_selected[0].get(field) != result_artifact.get(field)
                for field in ("id", "rel_path", "bytes", "sha256")
            ):
                raise RequestValidationError(
                    "The assembly cache lineage is not valid.",
                    code="qc_assembly_not_available",
                )
            visited_attempt_ids.add(cache_source_attempt_id)
            source_attempt = linked_attempt
            source_result = linked_result
        expected_relative = (
            f"outputs/studio/runs/{source_attempt['run_id']}/assembly/"
            f"{assembly_attempt['cache_key']}/{expected_name}"
        )
        if artifact["rel_path"] != expected_relative:
            raise RequestValidationError(
                "The selected assembly master has invalid lineage.",
                code="qc_assembly_not_available",
            )
        try:
            path = workspace_path(
                self.workspace, artifact["rel_path"], must_exist=True
            )
        except (SecurityError, OSError):
            raise RequestValidationError(
                "The selected assembly master path is not available.",
                code="qc_variant_not_available",
            ) from None
        if (
            _has_symlink_component(self.workspace, artifact["rel_path"])
            or path.is_symlink()
            or not path.is_file()
            or sensitive_artifact_path(artifact["rel_path"])
        ):
            raise RequestValidationError(
                "The selected assembly master path is not safe.",
                code="qc_variant_not_available",
            )
        stat = path.stat()
        if (
            isinstance(artifact.get("bytes"), bool)
            or not isinstance(artifact.get("bytes"), int)
            or artifact["bytes"] <= 0
            or artifact["bytes"] > 2 * 1024 * 1024 * 1024
            or stat.st_size != artifact["bytes"]
            or not isinstance(artifact.get("sha256"), str)
            or _sha256_file(path) != artifact["sha256"]
        ):
            raise RequestValidationError(
                "The selected assembly master changed after registration.",
                code="qc_assembly_changed",
            )
        expected_duration_ms = assembly_result.get("duration_ms")
        if (
            isinstance(expected_duration_ms, bool)
            or not isinstance(expected_duration_ms, int)
            or expected_duration_ms <= 0
            or expected_duration_ms > 30 * 60 * 1000
        ):
            raise RequestValidationError(
                "The assembly duration is not valid.",
                code="qc_assembly_not_available",
            )
        return {
            "assembly_attempt": assembly_attempt,
            "assembly_artifact": artifact,
            "input_path": path,
            "input_sha256": artifact["sha256"],
            "input_bytes": artifact["bytes"],
            "expected_duration_ms": expected_duration_ms,
        }

    def _register_local_qc_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_QC_ARTIFACTS
        ):
            raise LocalQcError(
                "The local QC worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/qc/{cache_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise LocalQcError(
                    "The local QC worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise LocalQcError(
                    "The local QC worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_QC_ARTIFACTS.get(path.name)
            if (
                expected is None
                or path.name in seen_names
                or relative != f"{expected_root}{path.name}"
                or _has_symlink_component(self.workspace, item["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(relative)
                or item.get("kind") != expected[0]
                or item.get("media_type", item.get("mime")) != expected[1]
            ):
                raise LocalQcError(
                    "The local QC worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise LocalQcError(
                    "The local QC worker returned mismatched artifact metadata.",
                    code="invalid_worker_result",
                )
            seen_names.add(path.name)
            validated.append(
                {
                    "id": stable_id("art", relative.casefold()),
                    "rel_path": relative,
                    "name": path.name,
                    "kind": expected[0],
                    "media_type": expected[1],
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": digest,
                    "is_heavy": False,
                }
            )
        if seen_names != set(_LOCAL_QC_ARTIFACTS):
            raise LocalQcError(
                "The local QC worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in validated
        ]

    @staticmethod
    def _qc_public_kwargs(
        cache_key: str,
        payload: dict[str, Any],
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "expected_cache_key": cache_key,
            "expected_assembly_attempt_id": payload["assembly_attempt_id"],
            "expected_assembly_artifact_id": inputs["assembly_artifact"]["id"],
            "expected_variant": payload["variant"],
            "expected_input_sha256": inputs["input_sha256"],
            "expected_input_bytes": inputs["input_bytes"],
            "expected_duration_ms": inputs["expected_duration_ms"],
        }

    def _cached_local_qc_result(
        self,
        run_id: str,
        production_id: str,
        cache_key: str,
        payload: dict[str, Any],
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | None:
        previous = self.database.find_successful_stage_attempt(
            production_id, _LOCAL_QC_STAGE, cache_key
        )
        if (
            previous is None
            or previous.get("run_id") != run_id
            or not isinstance(previous.get("result"), dict)
        ):
            return None
        try:
            from . import qc

            physical = _call_local_worker(
                qc.validate_local_qc_outputs,
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                assembly_attempt_id=payload["assembly_attempt_id"],
                assembly_artifact_id=inputs["assembly_artifact"]["id"],
                variant=payload["variant"],
                input_path=inputs["input_path"],
                input_sha256=inputs["input_sha256"],
                input_bytes=inputs["input_bytes"],
                expected_duration_ms=inputs["expected_duration_ms"],
                cancel_event=cancel_event,
            )
        except (ImportError, AttributeError, LocalQcError, OSError):
            return None
        physical_artifacts = physical.get("artifacts")
        prior_artifacts = previous["result"].get("artifacts")
        if not isinstance(physical_artifacts, list) or not isinstance(
            prior_artifacts, list
        ):
            return None
        physical_by_name = {
            item.get("name"): item
            for item in physical_artifacts
            if isinstance(item, dict)
        }
        expected_root = f"outputs/studio/runs/{run_id}/qc/{cache_key}/"
        verified: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if artifact is None or artifact.get("name") in seen_names:
                return None
            expected = _LOCAL_QC_ARTIFACTS.get(artifact["name"])
            physical_item = physical_by_name.get(artifact["name"])
            if (
                expected is None
                or not isinstance(physical_item, dict)
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("kind") != expected[0]
                or artifact.get("media_type") != expected[1]
                or artifact.get("rel_path") != f"{expected_root}{artifact['name']}"
                or item.get("bytes") != artifact.get("bytes")
                or item.get("sha256") != artifact.get("sha256")
                or physical_item.get("bytes") != artifact.get("bytes")
                or physical_item.get("sha256") != artifact.get("sha256")
            ):
                return None
            try:
                path = workspace_path(
                    self.workspace, artifact["rel_path"], must_exist=True
                )
            except (SecurityError, OSError):
                return None
            if (
                _has_symlink_component(self.workspace, artifact["rel_path"])
                or path.is_symlink()
                or not path.is_file()
                or sensitive_artifact_path(artifact["rel_path"])
                or path.stat().st_size != artifact.get("bytes")
                or _sha256_file(path) != artifact.get("sha256")
            ):
                return None
            seen_names.add(artifact["name"])
            verified.append(artifact)
        if seen_names != set(_LOCAL_QC_ARTIFACTS):
            return None
        public_kwargs = self._qc_public_kwargs(cache_key, payload, inputs)
        try:
            prior_cache_hit = previous["result"].get("cache_hit")
            if not isinstance(prior_cache_hit, bool):
                return None
            prior_public = qc_public_result(
                previous["result"],
                **public_kwargs,
                artifacts=verified,
                cache_hit=prior_cache_hit,
            )
            physical_for_public = dict(physical)
            physical_for_public["cache_hit"] = True
            cached = qc_public_result(
                physical_for_public,
                **public_kwargs,
                artifacts=verified,
                cache_hit=True,
            )
        except LocalQcError:
            return None
        for field in (
            "technical_verdict",
            "duration_ms",
            "checks",
            "media_facts",
        ):
            if prior_public.get(field) != cached.get(field):
                return None
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_local_qc(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        cache_key: str,
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        self.database.update_stage_attempt(attempt_id, "running")
        try:
            _raise_if_cancelled(cancel_event)
            cached = self._cached_local_qc_result(
                run_id,
                production_id,
                cache_key,
                payload,
                inputs,
                cancel_event,
            )
            if cached is not None:
                result = cached
            else:
                try:
                    from . import qc
                except (ImportError, AttributeError) as exc:
                    raise LocalQcError(
                        "The local QC worker is not installed.",
                        code="local_qc_unavailable",
                    ) from exc
                worker_kwargs = {
                    "production_id": production_id,
                    "run_id": run_id,
                    "cache_key": cache_key,
                    "assembly_attempt_id": payload["assembly_attempt_id"],
                    "assembly_artifact_id": inputs["assembly_artifact"]["id"],
                    "variant": payload["variant"],
                    "input_path": inputs["input_path"],
                    "input_sha256": inputs["input_sha256"],
                    "input_bytes": inputs["input_bytes"],
                    "expected_duration_ms": inputs["expected_duration_ms"],
                }
                try:
                    raw = _call_local_worker(
                        qc.generate_local_qc,
                        self.workspace,
                        cancel_event=cancel_event,
                        **worker_kwargs,
                    )
                except LocalQcError:
                    raise
                except Exception as exc:
                    raise LocalQcError(
                        "The local QC worker failed.", code="local_qc_failed"
                    ) from exc
                _raise_if_cancelled(cancel_event)
                raw_cache_hit = (
                    raw.get("cache_hit", False) if isinstance(raw, dict) else False
                )
                if not isinstance(raw_cache_hit, bool):
                    raw_cache_hit = False
                public_kwargs = self._qc_public_kwargs(cache_key, payload, inputs)
                raw_public = qc_public_result(
                    raw,
                    **public_kwargs,
                    artifacts=[],
                    cache_hit=raw_cache_hit,
                )
                physical = _call_local_worker(
                    qc.validate_local_qc_outputs,
                    self.workspace,
                    cancel_event=cancel_event,
                    **worker_kwargs,
                )
                physical_for_public = dict(physical)
                physical_for_public["cache_hit"] = raw_cache_hit
                physical_public = qc_public_result(
                    physical_for_public,
                    **public_kwargs,
                    artifacts=[],
                    cache_hit=raw_cache_hit,
                )
                for field in (
                    "technical_verdict",
                    "duration_ms",
                    "checks",
                    "media_facts",
                ):
                    if raw_public.get(field) != physical_public.get(field):
                        raise LocalQcError(
                            "The local QC worker returned mismatched analysis.",
                            code="invalid_worker_result",
                        )
                raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
                physical_artifacts = physical.get("artifacts")
                if not isinstance(raw_artifacts, list) or not isinstance(
                    physical_artifacts, list
                ):
                    raise LocalQcError(
                        "The local QC worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                physical_by_name = {
                    item.get("name"): item
                    for item in physical_artifacts
                    if isinstance(item, dict)
                }
                for item in raw_artifacts:
                    if not isinstance(item, dict):
                        raise LocalQcError(
                            "The local QC worker returned invalid artifacts.",
                            code="invalid_worker_result",
                        )
                    name = Path(str(item.get("rel_path") or "")).name
                    physical_item = physical_by_name.get(name)
                    if (
                        not isinstance(physical_item, dict)
                        or item.get("bytes") != physical_item.get("bytes")
                        or item.get("sha256") != physical_item.get("sha256")
                    ):
                        raise LocalQcError(
                            "The local QC worker returned mismatched artifacts.",
                            code="invalid_worker_result",
                        )
                artifacts = self._register_local_qc_artifacts(
                    production_id, run_id, cache_key, physical_artifacts
                )
                result = dict(physical_public)
                result["artifacts"] = artifacts
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(attempt_id, result, cancel_event)
        except JobCancelled as exc:
            try:
                self.database.update_stage_attempt(
                    attempt_id,
                    "failed",
                    error_code=exc.error_code,
                    error_message=exc.public_message,
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    self.database.update_stage_attempt(
                        attempt_id,
                        "failed",
                        error_code=JobCancelled.error_code,
                        error_message=JobCancelled.public_message,
                    )
                except Exception:
                    pass
                raise JobCancelled() from exc
            error_code, error_message = safe_qc_error(exc)
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

    def execute_local_qc(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Queue a zero-cost local technical QC attempt."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in _LOCAL_DOWNSTREAM_PROFILES:
            raise RequestValidationError(
                "This run is not configured for local technical QC.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        required_stages = {_LOCAL_ASSEMBLY_STAGE, _LOCAL_QC_STAGE}
        if not isinstance(requested_stages, list) or not required_stages.issubset(
            requested_stages
        ):
            raise RequestValidationError(
                "The assembly and qc stages were not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_local_qc_payload(body)
        except LocalQcValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        inputs = self._validated_qc_inputs(run, payload)
        try:
            from . import qc

            cache_key = qc.qc_cache_key(
                production_id=run["production_id"],
                run_id=run_id,
                assembly_attempt_id=payload["assembly_attempt_id"],
                assembly_artifact_id=inputs["assembly_artifact"]["id"],
                variant=payload["variant"],
                input_sha256=inputs["input_sha256"],
                input_bytes=inputs["input_bytes"],
                expected_duration_ms=inputs["expected_duration_ms"],
            )
        except (ImportError, AttributeError) as exc:
            raise RequestValidationError(
                "The local QC worker is not installed.",
                code="local_qc_unavailable",
            ) from exc
        except LocalQcError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9A-F]{64}", cache_key):
            raise RequestValidationError(
                "The local QC worker returned an invalid cache key.",
                code="invalid_worker_result",
            )
        audit = qc_audit_payload(
            payload,
            assembly_artifact_id=inputs["assembly_artifact"]["id"],
            input_sha256=inputs["input_sha256"],
            input_bytes=inputs["input_bytes"],
            expected_duration_ms=inputs["expected_duration_ms"],
            cache_key=cache_key,
        )
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_QC_STAGE,
            cache_key,
            {"execution_profile": run["execution_profile"], **audit},
        )
        try:
            job = self.jobs.submit(
                "local_qc",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_QC_STAGE,
                    "execution_profile": run["execution_profile"],
                    **audit,
                },
                lambda _job_id, cancel_event: self._execute_local_qc(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    inputs,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
            )
        except Exception as exc:
            error_code, error_message = safe_qc_error(exc)
            self.database.update_stage_attempt(
                attempt["id"],
                "failed",
                error_code=error_code,
                error_message=error_message,
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
