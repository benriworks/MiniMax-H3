from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import mimetypes
import re
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Callable
from urllib.parse import quote_from_bytes

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
    WindowsCaptureConsentError,
    money_to_minor,
    utc_now,
)
from .comfyui_execution import (
    COMFYUI_WORKFLOW_RELATIVE_PATH,
    MODEL_SPECS as COMFYUI_MODEL_SPECS,
    ComfyUIError,
    ComfyUIValidationError,
    comfyui_audit_payload,
    comfyui_cache_key,
    comfyui_payload_digest,
    comfyui_public_result,
    comfyui_resume_payload,
    normalize_model_records,
    normalize_workflow_record,
    safe_comfyui_error,
    validate_comfyui_payload,
)
from .execution import (
    LocalNarrationError,
    LocalNarrationValidationError,
    audit_payload,
    narration_cache_key,
    public_result,
    safe_error,
    validate_internal_narration_segment_starts,
    validate_local_narration_payload,
)
from .announcement_video import (
    ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    AnnouncementVideoValidationError,
    announcement_narration_segment_starts,
    announcement_recipe_audit_summary,
    announcement_recipe_to_detailed_payload,
    validate_announcement_duplicate_payload,
    validate_announcement_execute_payload,
    validate_announcement_recipe_id,
    validate_announcement_recipe_payload,
    validate_announcement_save_payload,
)
from .detailed_test_video import (
    DETAILED_TEST_VIDEO_JOB_KIND,
    DETAILED_TEST_VIDEO_PROFILE,
    DetailedTestVideoError,
    DetailedTestVideoValidationError,
    detailed_test_video_audit_payload,
    detailed_test_video_key,
    detailed_test_video_public_result,
    run_detailed_test_video,
    validate_detailed_test_video_payload,
)
from .indexer import ProductionIndexer
from .production_intake import (
    ProductionIntakeError,
    cleanup_stale_video_import_partials,
    create_production_files,
    read_production_metadata,
    rename_production_files,
    stream_video_import,
    validate_production_id,
)
from .production_library import (
    ProductionLibraryValidationError,
    production_library_request_digest,
    validate_production_archive_payload,
    validate_production_duplicate_payload,
    validate_production_rename_payload,
)
from .job_control import (
    JOB_CONTROL_SCHEMA_VERSION,
    JobControlValidationError,
    validate_job_cancel_payload,
)
from .jobs import AuditExporter, JobCancelled, JobExecutionContext, JobManager
from .pipeline import (
    LOCAL_PIPELINE_JOB_KIND,
    LOCAL_PIPELINE_PROFILE,
    LocalPipelineError,
    LocalPipelineValidationError,
    local_pipeline_audit_payload,
    local_pipeline_key,
    run_local_pipeline,
    validate_local_pipeline_payload,
)
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
from .remotion_timeline_execution import (
    RemotionTimelineError,
    RemotionTimelineValidationError,
    compile_remotion_timeline,
    remotion_timeline_audit_payload,
    remotion_timeline_cache_key,
    remotion_timeline_public_result,
    safe_remotion_timeline_error,
    validate_remotion_timeline_payload,
)
from .secrets import (
    SecretStorageUnavailable,
    SecretStore,
    dpapi_available,
    protect_private_data,
    unprotect_private_data,
)
from .browser_capture_execution import (
    BrowserCaptureError,
    BrowserCaptureValidationError,
    browser_capture_audit_payload,
    browser_capture_key,
    browser_capture_public_result,
    safe_browser_capture_error,
    validate_browser_capture_payload,
)
from .windows_capture import (
    WINDOWS_CAPTURE_CONSENT_TTL_SECONDS,
    WINDOWS_CAPTURE_SCHEMA_VERSION,
    WindowsCaptureError,
    WindowsCaptureValidationError,
    inspect_windows_capture_capability as inspect_windows_capture_capability_environment,
    safe_windows_capture_error,
    validate_windows_capture_execution_payload,
    validate_windows_capture_payload,
    windows_capture_audit_payload,
    windows_capture_consent_token_digest,
    windows_capture_key,
    windows_capture_public_result,
    windows_capture_request_digest,
    windows_capture_settings_digest,
)
from .security import (
    SecurityError,
    canonical_json,
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
_EXECUTION_PROFILES = {
    "external",
    "local_sapi",
    "elevenlabs_tts",
    "local_comfyui",
    "local_playwright",
    "local_windows_capture",
}
_LOCAL_SAPI_ZERO_COST_STAGES = {"narration", "captions", "timeline", "assembly", "qc"}
_ELEVENLABS_TTS_STAGES = {"narration", "captions", "assembly", "qc"}
_LOCAL_COMFYUI_ZERO_COST_STAGES = {"video_generation", "timeline", "assembly", "qc"}
_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES = {"screen_capture", "timeline", "assembly", "qc"}
_LOCAL_PLAYWRIGHT_EXECUTION_STAGES = ("screen_capture", "timeline")
_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES = {
    "screen_capture",
    "timeline",
    "assembly",
    "qc",
}
_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES = ("screen_capture", "timeline")
_LOCAL_PIPELINE_ZERO_COST_STAGES = {
    "narration",
    "captions",
    "video_generation",
    "timeline",
    "assembly",
    "qc",
}
_LOCAL_DOWNSTREAM_PROFILES = {"local_sapi", "elevenlabs_tts", "local_pipeline"}
_LOCAL_NARRATION_STAGE = "narration"
_LOCAL_VIDEO_GENERATION_STAGE = "video_generation"
_LOCAL_SCREEN_CAPTURE_STAGE = "screen_capture"
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
_LOCAL_COMFYUI_ARTIFACTS = {
    "generated-video.mp4": ("video", "video/mp4"),
    "workflow.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_SCREEN_CAPTURE_ARTIFACTS = {
    "screen-capture.mp4": ("video", "video/mp4"),
    "playwright-raw.webm": ("video", "video/webm"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_WINDOWS_CAPTURE_ARTIFACTS = {
    "screen-capture.mp4": ("video", "video/mp4"),
    "screen-video.mp4": ("video", "video/mp4"),
    "system-audio.wav": ("audio", "audio/wav"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_LOCAL_WINDOWS_CAPTURE_MAX_ARTIFACT_BYTES = {
    "screen-capture.mp4": 512 * 1024 * 1024,
    "screen-video.mp4": 512 * 1024 * 1024,
    "system-audio.wav": 64 * 1024 * 1024,
    "first-frame.png": 64 * 1024 * 1024,
    "last-frame.png": 64 * 1024 * 1024,
    "capture-report.json": 16 * 1024 * 1024,
    "ffprobe.json": 16 * 1024 * 1024,
    "manifest.json": 16 * 1024 * 1024,
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
_LOCAL_REMOTION_TIMELINE_ARTIFACTS = {
    "remotion-preview.mp4": ("video", "video/mp4"),
    "remotion-timeline.json": ("document", "application/json"),
    "render-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_MAX_LOCAL_TIMELINE_CLIPS = 32
_MAX_LOCAL_TIMELINE_INPUT_BYTES = 4 * 1024 * 1024 * 1024
_MAX_LOCAL_TIMELINE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
_SERVICE_JOB_SHUTDOWN_TIMEOUT_SECONDS = 5.0
_PIPELINE_CONTINUATION_SCAN_SECONDS = 1.0
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


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    method = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(method):
        method()
        return
    is_set = getattr(cancel_event, "is_set", None)
    if callable(is_set) and is_set():
        raise JobCancelled()


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
    *,
    artifact_records: tuple[dict[str, Any], ...] = (),
    provider_task_record_id: str | None = None,
    failure_cleanup: Callable[[], None] | None = None,
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
        if (
            artifact_records
            or provider_task_record_id is not None
            or failure_cleanup is not None
        ):
            raise ValueError(
                "atomic artifact registration requires a job execution context"
            )
        return public_result
    return AtomicStageCompletion(
        attempt_id,
        result,
        artifact_records,
        provider_task_record_id=provider_task_record_id,
        failure_cleanup=failure_cleanup,
    )


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
        cleanup_stale_video_import_partials(self.workspace)
        path = database_path or workspace_path(self.workspace, "outputs/studio/studio.sqlite3")
        path = workspace_path(self.workspace, path)
        self.database = StudioDatabase(path, workspace=self.workspace)
        # Startup DB recovery invalidates every unconsumed consent first.
        # Deterministic nonce partials are then removed before any capture
        # lane exists. A cleanup error aborts Studio startup instead of
        # allowing a later recording beside unknown stale private media.
        from . import windows_capture_worker

        windows_capture_worker.cleanup_stale_windows_capture_partials(
            self.workspace
        )
        # Resolve exact durable job/attempt cleanup identities before any
        # worker lane or recovery thread exists. A fail-closed startup error
        # therefore cannot leave background infrastructure behind.
        self._cleanup_interrupted_windows_capture_outputs()
        self.indexer = ProductionIndexer(self.workspace, self.database)
        self.secret_store = SecretStore(self.workspace)
        self.jobs = JobManager(self.database)
        self.audit_exporter = AuditExporter(self.workspace, self.database)
        self._pipeline_submit_lock = threading.Lock()
        self._detailed_test_video_submit_lock = threading.Lock()
        self._local_video_submit_lock = threading.Lock()
        self._windows_capture_submit_lock = threading.Lock()
        self._production_intake_lock = threading.Lock()
        self._pipeline_capability = object()
        self._announcement_narration_timing_capability = object()
        self._provider_recovery_lock = threading.Lock()
        self._provider_cancellation_lock = threading.Lock()
        self._provider_cancellation_jobs: dict[str, str] = {}
        self._provider_recovery_state_lock = threading.Lock()
        self._provider_recovery_stop = threading.Event()
        self._provider_recovery_done = threading.Event()
        self._pipeline_continuation_stop = threading.Event()
        self._pipeline_continuation_wake = threading.Event()
        recoverable = self.database.list_recoverable_provider_tasks(limit=100)
        self._startup_provider_recovery: dict[str, Any] = {
            "found": len(recoverable),
            "queued": 0,
            "blocked": 0,
            "ambiguous": 0,
            "running": bool(recoverable),
        }
        self._provider_recovery_thread: threading.Thread | None = None
        if recoverable:
            self._provider_recovery_thread = threading.Thread(
                target=self._run_startup_provider_recovery,
                args=(recoverable,),
                name="studio-provider-recovery",
                daemon=True,
            )
            self._provider_recovery_thread.start()
        else:
            self._provider_recovery_done.set()
        # This coordinator only claims durable ``ready`` checkpoints and
        # enqueues a new top job.  It never waits for the GPU/default lanes,
        # so provider recovery and downstream execution cannot deadlock it.
        self._pipeline_continuation_thread = threading.Thread(
            target=self._run_pipeline_continuation_coordinator,
            name="studio-pipeline-continuation",
            daemon=True,
        )
        self._pipeline_continuation_thread.start()

    def _complete_local_stage(
        self,
        attempt_id: str,
        production_id: str,
        result: dict[str, Any],
        cancel_event: JobExecutionContext | None,
        *,
        artifact_records: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        failure_cleanup: Callable[[], None] | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        """Complete a local stage without publishing artifacts ahead of it.

        JobManager-backed calls pass validated artifact records to the database
        in :class:`AtomicStageCompletion`, so artifact registration and the
        linked job/stage success transition share one transaction. Historical
        direct helper calls have no manager transaction; preserve their public
        mapping behavior by registering the already-validated records here.
        """

        public = dict(result)
        records = tuple(dict(item) for item in artifact_records)
        if records:
            if public.get("artifacts") not in (None, []):
                raise ValueError(
                    "atomic artifact records require an empty public artifact list"
                )
            if cancel_event is None:
                public["artifacts"] = [
                    self.database.register_studio_artifact(production_id, item)
                    for item in records
                ]
                records = ()
            else:
                # The database replaces this placeholder with registered
                # public artifacts inside the terminal transaction.
                public["artifacts"] = []
        return _stage_completion_result(
            attempt_id,
            public,
            cancel_event,
            artifact_records=records,
            failure_cleanup=failure_cleanup,
        )

    def close(self) -> None:
        self._pipeline_continuation_stop.set()
        self._pipeline_continuation_wake.set()
        self._provider_recovery_stop.set()
        continuation_thread = self._pipeline_continuation_thread
        if (
            continuation_thread.is_alive()
            and continuation_thread is not threading.current_thread()
        ):
            continuation_thread.join()
        recovery_thread = self._provider_recovery_thread
        if (
            recovery_thread is not None
            and recovery_thread.is_alive()
            and recovery_thread is not threading.current_thread()
        ):
            # The public workspace instance lock is released only after this
            # method returns.  Do not let an old recovery daemon cross that
            # boundary and mutate the database owned by the next Studio.
            # Provider observation is bounded to one second and local checks
            # receive the stop event, so this waits for coordination only,
            # never for the multi-hour remote render itself.
            recovery_thread.join()
        if not self.jobs.shutdown(timeout=_SERVICE_JOB_SHUTDOWN_TIMEOUT_SECONDS):
            # The caller still owns the workspace instance lock.  Failing the
            # close keeps that lock held so an old Python callback or SQLite
            # interruption writer can never overlap a new Studio process.
            # server_close() may be retried after the worker finishes.
            raise RuntimeError(
                "Studio background work is still draining; workspace lock retained."
            )

    def _provider_recovery_snapshot(self) -> dict[str, Any]:
        with self._provider_recovery_state_lock:
            return dict(self._startup_provider_recovery)

    def _run_pipeline_continuation_coordinator(self) -> None:
        """Claim durable ready checkpoints without waiting on worker lanes."""

        while not self._pipeline_continuation_stop.is_set():
            # A queue adapter can fail after the durable top claim commits.
            # If its immediate DB compensation also fails transiently, retry
            # only the exact IDs recorded by this JobManager.  A successful
            # repair becomes ``ready`` and is consumed later in this cycle.
            try:
                self.jobs.repair_local_pipeline_admissions()
            except Exception:
                # A transient DB read/write error keeps the exact repair set;
                # the next coordinator scan retries it.
                pass
            try:
                self.jobs.retry_pending_operator_cancellations()
            except Exception:
                # Exact operator intent remains process-local until a later
                # scan confirms its durable cancelled/cancel_requested state.
                pass
            if self.jobs.has_pending_local_pipeline_operator_cancellation():
                # Never consume any ready generation while an exact operator
                # cancellation fence is waiting for a transient DB retry.
                pending = []
            else:
                try:
                    pending = self.database.list_ready_local_pipeline_continuation_material(
                        limit=100
                    )
                except Exception:
                    pending = []
            for material in pending:
                if self._pipeline_continuation_stop.is_set():
                    break
                try:
                    self._resume_local_pipeline_continuation(material)
                except RequestValidationError as exc:
                    # Protected material or its durable lineage is unusable.
                    # Close only the exact ready generation; never persist the
                    # decrypted request or an arbitrary exception string.
                    try:
                        self.database.block_local_pipeline_continuation(
                            str(material.get("production_id", "")),
                            str(material.get("pipeline_key", "")),
                            expected_updated_at=str(material.get("updated_at", "")),
                            error_code=exc.code,
                            error_message=(
                                "The protected pipeline continuation could not be verified."
                            ),
                        )
                    except Exception:
                        pass
                except Exception:
                    # CAS loss, a transient SQLite error, or a manager-close
                    # race is retried from durable state on the next scan.
                    pass
            self._pipeline_continuation_wake.wait(
                _PIPELINE_CONTINUATION_SCAN_SECONDS
            )
            self._pipeline_continuation_wake.clear()

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
            "provider_task_recovery": self._provider_recovery_snapshot(),
            "pipeline_continuation": {
                "automatic": dpapi_available(),
                "coordinator_running": self._pipeline_continuation_thread.is_alive(),
            },
        }

    def providers_status(self) -> dict[str, Any]:
        return {
            "providers": self.secret_store.statuses(),
            "secure_persistence_available": dpapi_available(),
            "comfyui_restart_recovery": {
                "automatic": dpapi_available(),
                **self._provider_recovery_snapshot(),
            },
            "local_pipeline_continuation": {
                "automatic": dpapi_available(),
                "coordinator_running": self._pipeline_continuation_thread.is_alive(),
                "scan_interval_seconds": _PIPELINE_CONTINUATION_SCAN_SECONDS,
            },
        }

    def inspect_windows_capture_capability(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Inspect the fixed Windows capture foundation without recording."""

        if not isinstance(body, dict) or body:
            raise RequestValidationError(
                "Windows capture capability body must be an empty object"
            )
        return inspect_windows_capture_capability_environment(self.workspace)

    def issue_windows_capture_consent(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        session_binding_digest: str,
    ) -> dict[str, Any]:
        """Issue one short-lived, session/run/settings-bound bearer token."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "local_windows_capture":
            raise RequestValidationError(
                "This run is not configured for local Windows capture.",
                code="execution_profile_required",
            )
        if (
            not isinstance(run.get("requested_stages"), list)
            or _LOCAL_SCREEN_CAPTURE_STAGE not in run["requested_stages"]
        ):
            raise RequestValidationError(
                "The screen_capture stage was not requested by this run.",
                code="stage_not_requested",
            )
        if not isinstance(session_binding_digest, str) or re.fullmatch(
            r"[0-9A-F]{64}", session_binding_digest
        ) is None:
            raise RequestValidationError(
                "The authenticated Studio session binding is invalid.",
                code="windows_capture_consent_invalid",
            )
        try:
            payload = validate_windows_capture_payload(body)
            request_settings_digest = windows_capture_settings_digest(payload)
            consent_token = secrets.token_urlsafe(32)
            token_digest = windows_capture_consent_token_digest(consent_token)
            intent = self.database.issue_windows_capture_consent_intent(
                production_id=run["production_id"],
                run_id=run_id,
                token_digest=token_digest,
                session_binding_digest=session_binding_digest,
                request_settings_digest=request_settings_digest,
                ttl_seconds=WINDOWS_CAPTURE_CONSENT_TTL_SECONDS,
            )
        except WindowsCaptureValidationError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        return {
            "schema_version": WINDOWS_CAPTURE_SCHEMA_VERSION,
            "consent_intent_id": intent["id"],
            "consent_token": consent_token,
            "run_id": run_id,
            "request_settings_digest": request_settings_digest,
            "issued_at": intent["issued_at"],
            "expires_at": intent["expires_at"],
            "expires_in_seconds": WINDOWS_CAPTURE_CONSENT_TTL_SECONDS,
        }

    def _cleanup_interrupted_windows_capture_outputs(self) -> None:
        """Discard exact unregistered output with durable cleanup lineage.

        A native recording is never resumed automatically after restart: doing
        so would replay old consent at an unexpected time.  SQLite startup has
        already terminalized active jobs/attempts before this method runs.  We
        therefore remove only the exact nonce-derived directory of a linked,
        failed attempt, and preserve it whenever durable artifact truth is
        ambiguous.
        """

        try:
            candidates = self.database.list_windows_capture_cleanup_candidates(
                limit=1000
            )
        except Exception as exc:
            raise WindowsCaptureError(
                "Windows capture cleanup records could not be queried.",
                code="windows_capture_cleanup_failed",
            ) from exc
        if len(candidates) >= 1000:
            raise WindowsCaptureError(
                "Windows capture cleanup records exceed the startup limit.",
                code="windows_capture_cleanup_failed",
            )
        if not candidates:
            return
        try:
            from . import windows_capture_worker
        except (ImportError, AttributeError) as exc:
            raise WindowsCaptureError(
                "The Windows capture cleanup worker is unavailable.",
                code="windows_capture_cleanup_failed",
            ) from exc
        cleanup_codes = {
            "windows_capture_cleanup_failed",
            "windows_capture_cleanup_required",
        }
        verified_targets: list[tuple[str, str]] = []
        verified_target_set: set[tuple[str, str]] = set()
        # Preflight the complete bounded candidate set before deleting a byte.
        # A later ambiguous row must not be able to block startup only after an
        # earlier, valid-looking capture directory has already been removed.
        for job in candidates:
            payload = job.get("payload")
            if not isinstance(payload, dict):
                raise WindowsCaptureError(
                    "A Windows capture cleanup record is invalid.",
                    code="windows_capture_cleanup_failed",
                )
            run_id = payload.get("run_id")
            capture_key = payload.get("capture_key")
            attempt_id = payload.get("stage_attempt_id")
            if (
                not isinstance(run_id, str)
                or re.fullmatch(r"run_[0-9a-f]{32}", run_id) is None
                or not isinstance(capture_key, str)
                or re.fullmatch(r"[0-9A-F]{64}", capture_key) is None
                or not isinstance(attempt_id, str)
                or re.fullmatch(r"attempt_[0-9a-f]{32}", attempt_id) is None
            ):
                raise WindowsCaptureError(
                    "A Windows capture cleanup identity is invalid.",
                    code="windows_capture_cleanup_failed",
                )
            try:
                attempt = self.database.get_stage_attempt(attempt_id)
                run = self.database.get_run(run_id)
            except Exception as exc:
                raise WindowsCaptureError(
                    "A Windows capture cleanup lineage could not be read.",
                    code="windows_capture_cleanup_failed",
                ) from exc
            job_error = job.get("error")
            attempt_error = attempt.get("error") if isinstance(attempt, dict) else None
            job_error_code = (
                job_error.get("code") if isinstance(job_error, dict) else None
            )
            attempt_error_code = (
                attempt_error.get("code")
                if isinstance(attempt_error, dict)
                else None
            )
            attempt_payload = (
                attempt.get("payload") if isinstance(attempt, dict) else None
            )
            interrupted_lineage = bool(
                job.get("status") == "interrupted"
                and job_error_code == "process_interrupted"
                and isinstance(attempt, dict)
                and attempt.get("status") == "failed"
                and attempt_error_code == "process_interrupted"
            )
            cleanup_failure_lineage = bool(
                job.get("status") == "failed"
                and job_error_code in cleanup_codes
                and isinstance(attempt, dict)
                and attempt.get("status") == "failed"
                and attempt_error_code == job_error_code
            )
            if (
                attempt is None
                or run is None
                or job.get("kind") != "local_windows_capture"
                or attempt.get("job_id") != job.get("id")
                or attempt.get("run_id") != run_id
                or attempt.get("stage") != _LOCAL_SCREEN_CAPTURE_STAGE
                or attempt.get("status") != "failed"
                or attempt.get("cache_key") != capture_key
                or not isinstance(attempt_payload, dict)
                or attempt_payload.get("execution_profile")
                != "local_windows_capture"
                or attempt_payload.get("capture_key") != capture_key
                or job.get("production_id") != attempt.get("production_id")
                or payload.get("production_id") != attempt.get("production_id")
                or payload.get("execution_profile") != "local_windows_capture"
                or payload.get("stage") != _LOCAL_SCREEN_CAPTURE_STAGE
                or run.get("production_id") != attempt.get("production_id")
                or run.get("execution_profile") != "local_windows_capture"
                or not (interrupted_lineage or cleanup_failure_lineage)
            ):
                raise WindowsCaptureError(
                    "A Windows capture cleanup lineage is inconsistent.",
                    code="windows_capture_cleanup_failed",
                )
            output_root = (
                f"outputs/studio/runs/{run_id}/screen_capture/{capture_key}/"
            )
            try:
                artifact_records = [
                    self.database.get_artifact(
                        stable_id("art", f"{output_root}{name}".casefold())
                    )
                    for name in _LOCAL_WINDOWS_CAPTURE_ARTIFACTS
                ]
            except Exception as exc:
                raise WindowsCaptureError(
                    "Windows capture artifact truth could not be read.",
                    code="windows_capture_cleanup_failed",
                ) from exc
            # Any registry row, including an unavailable/tombstoned one, means
            # the output is not provably unregistered. Preserve it and block
            # startup instead of guessing whether publication once committed.
            if any(artifact is not None for artifact in artifact_records):
                raise WindowsCaptureError(
                    "Windows capture cleanup truth conflicts with registered artifacts.",
                    code="windows_capture_cleanup_failed",
                )
            target = (run_id, capture_key)
            if target in verified_target_set:
                raise WindowsCaptureError(
                    "A Windows capture cleanup target has ambiguous lineage.",
                    code="windows_capture_cleanup_failed",
                )
            verified_target_set.add(target)
            verified_targets.append(target)

        for run_id, capture_key in verified_targets:
            try:
                windows_capture_worker.discard_windows_capture_outputs(
                    self.workspace,
                    run_id=run_id,
                    capture_key=capture_key,
                )
            except WindowsCaptureError:
                # This lineage is proven interrupted, unregistered, and exact.
                # A residual therefore blocks startup instead of being hidden
                # behind an otherwise healthy capture capability.
                raise
            except Exception as exc:
                raise WindowsCaptureError(
                    "Interrupted Windows capture data could not be removed.",
                    code="windows_capture_cleanup_failed",
                ) from exc

    def list_productions(
        self, *, include_archived: bool = False, query: str = ""
    ) -> dict[str, Any]:
        if not isinstance(include_archived, bool):
            raise RequestValidationError(
                "include_archived must be a boolean",
                code="invalid_production_library_query",
            )
        if (
            not isinstance(query, str)
            or len(query) > 120
            or any(ord(character) < 32 or ord(character) == 127 for character in query)
        ):
            raise RequestValidationError(
                "q is invalid or too long",
                code="invalid_production_library_query",
            )
        productions = self.database.list_productions(
            include_archived=include_archived,
            query=query,
        )
        return {"productions": productions, "count": len(productions)}

    def _mutable_library_production(self, production_id: str) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        production = self.database.get_production(production_id)
        if production is None:
            raise KeyError("production not found")
        # A checked-in production record remains explicitly read-only even if
        # an output directory happens to share its ID.  Only the Studio intake
        # control document authorizes a library mutation.
        try:
            control = read_production_metadata(self.workspace, production_id)
        except ProductionIntakeError:
            control = None
        if (
            production.get("library_read_only")
            or production.get("source_rel") is not None
            or control is None
        ):
            raise RequestValidationError(
                "tracked productions are read-only in the Studio library",
                code="production_library_read_only",
            )
        return production

    @staticmethod
    def _library_database_error(exc: ValueError) -> RequestValidationError:
        message = str(exc)
        if "operation conflict" in message:
            return RequestValidationError(
                "operation_id is already bound to another library request",
                code="production_library_operation_conflict",
            )
        if "revision conflict" in message:
            return RequestValidationError(
                "the production library state changed since it was loaded",
                code="production_library_revision_conflict",
            )
        if "read only" in message:
            return RequestValidationError(
                "tracked productions are read-only in the Studio library",
                code="production_library_read_only",
            )
        if "target conflict" in message:
            return RequestValidationError(
                "duplicate target conflicts with its source",
                code="production_library_duplicate_conflict",
            )
        return RequestValidationError(
            "the production library mutation could not be accepted",
            code="invalid_production_library_request",
        )

    def rename_production(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = validate_production_rename_payload(body)
        except (ProductionLibraryValidationError, ProductionIntakeError) as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        digest = production_library_request_digest("rename", payload)
        with self._production_intake_lock:
            try:
                prior = self.database.get_production_library_operation(
                    payload["operation_id"],
                    production_id=production_id,
                    action="rename",
                    request_digest=digest,
                )
                if prior is not None:
                    return prior
                self._mutable_library_production(production_id)
                _metadata, filesystem_deduplicated = rename_production_files(
                    self.workspace,
                    production_id,
                    expected_title=payload["expected_title"],
                    title=payload["title"],
                )
                return self.database.rename_production_library(
                    production_id,
                    operation_id=payload["operation_id"],
                    request_digest=digest,
                    expected_title=payload["expected_title"],
                    title=payload["title"],
                    filesystem_deduplicated=filesystem_deduplicated,
                )
            except ProductionIntakeError as exc:
                if exc.code == "production_not_found":
                    raise KeyError("production not found") from exc
                raise RequestValidationError(str(exc), code=exc.code) from exc
            except RequestValidationError:
                raise
            except ValueError as exc:
                raise self._library_database_error(exc) from exc

    def archive_production(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = validate_production_archive_payload(body)
        except ProductionLibraryValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        digest = production_library_request_digest("archive", payload)
        with self._production_intake_lock:
            try:
                prior = self.database.get_production_library_operation(
                    payload["operation_id"],
                    production_id=production_id,
                    action="archive",
                    request_digest=digest,
                )
                if prior is not None:
                    return prior
                self._mutable_library_production(production_id)
                return self.database.archive_production_library(
                    production_id,
                    operation_id=payload["operation_id"],
                    request_digest=digest,
                    expected_archived=payload["expected_archived"],
                    archived=payload["archived"],
                )
            except RequestValidationError:
                raise
            except ValueError as exc:
                raise self._library_database_error(exc) from exc

    def duplicate_production(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = validate_production_duplicate_payload(body)
        except (ProductionLibraryValidationError, ProductionIntakeError) as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        target_id = payload["production_id"]
        if target_id == production_id:
            raise RequestValidationError(
                "duplicate target must differ from its source",
                code="production_library_duplicate_conflict",
            )
        # The source production is carried by the route, not the JSON body.
        # Bind it into the durable operation identity so replaying the same
        # operation ID against another source cannot return the first source's
        # deduplicated result.
        digest = production_library_request_digest(
            "duplicate",
            {"source_production_id": production_id, "request": payload},
        )
        with self._production_intake_lock:
            try:
                prior = self.database.get_production_library_operation(
                    payload["operation_id"],
                    production_id=target_id,
                    action="duplicate",
                    request_digest=digest,
                )
                if prior is not None:
                    return prior
                self._mutable_library_production(production_id)
                source_metadata = read_production_metadata(self.workspace, production_id)
                assert source_metadata is not None
                create_production_files(
                    self.workspace,
                    {
                        "schema_version": 1,
                        "production_id": target_id,
                        "title": payload["title"],
                    },
                )
                imported_count = 0
                if payload["include_imports"]:
                    for relative in sorted(source_metadata["imports"]):
                        source_path = workspace_path(
                            self.workspace,
                            f"outputs/productions/{production_id}/{relative}",
                            must_exist=True,
                        )
                        if source_path.is_symlink() or not source_path.is_file():
                            raise RequestValidationError(
                                "a source import is unavailable",
                                code="production_library_duplicate_source_invalid",
                            )
                        size = source_path.stat().st_size
                        header = quote_from_bytes(
                            source_path.name.encode("utf-8"),
                            safe="-_.!~*'()",
                        )
                        with source_path.open("rb") as stream:
                            stream_video_import(
                                self.workspace,
                                target_id,
                                stream=stream,
                                filename_header=header,
                                content_type="application/octet-stream",
                                content_length=size,
                                expected_sha256=source_metadata["imports"][relative],
                            )
                        imported_count += 1
                self.indexer.refresh_production(target_id)
                return self.database.record_production_duplicate(
                    target_id,
                    source_production_id=production_id,
                    operation_id=payload["operation_id"],
                    request_digest=digest,
                    include_imports=payload["include_imports"],
                    imported_artifact_count=imported_count,
                )
            except ProductionIntakeError as exc:
                if exc.code == "production_not_found":
                    raise KeyError("production not found") from exc
                raise RequestValidationError(str(exc), code=exc.code) from exc
            except RequestValidationError:
                raise
            except ValueError as exc:
                raise self._library_database_error(exc) from exc

    def create_production(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create one output-owned production and immediately index it."""

        with self._production_intake_lock:
            try:
                metadata, deduplicated, _created = create_production_files(
                    self.workspace, body
                )
            except ProductionIntakeError as exc:
                raise RequestValidationError(str(exc), code=exc.code) from exc
            # The filesystem control document is the durable source of truth.
            # If indexing fails after its own DB transaction commits, deleting
            # the document would leave a phantom DB production.  Retain it so
            # the same client-issued ID can be retried and re-indexed safely.
            self.indexer.refresh_production(metadata["production_id"])
            production = self.database.get_production(metadata["production_id"])
            if production is None or production["title"] != metadata["title"]:
                raise RuntimeError("created production was not indexed")
            return {
                "schema_version": 1,
                "production": production,
                "deduplicated": deduplicated,
            }

    def import_production_video(
        self,
        production_id: str,
        *,
        stream: BinaryIO,
        filename_header: Any,
        content_type: Any,
        content_length: Any,
    ) -> dict[str, Any]:
        """Verify, publish, index, and audit one raw local video body."""

        try:
            normalized_id = validate_production_id(production_id)
        except ProductionIntakeError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        with self._production_intake_lock:
            try:
                imported = stream_video_import(
                    self.workspace,
                    normalized_id,
                    stream=stream,
                    filename_header=filename_header,
                    content_type=content_type,
                    content_length=content_length,
                )
            except ProductionIntakeError as exc:
                if exc.code == "production_not_found":
                    raise KeyError("production not found") from exc
                raise RequestValidationError(str(exc), code=exc.code) from exc
            self.indexer.refresh_production(normalized_id)
            artifact = self.database.get_artifact(imported.artifact["id"])
            if (
                artifact is None
                or not artifact["available"]
                or artifact["production_id"] != normalized_id
                or artifact["origin"] != "output"
                or artifact["rel_path"] != imported.artifact["rel_path"]
                or artifact["sha256"] != imported.artifact["sha256"]
            ):
                raise RuntimeError("imported video was not indexed consistently")
            self.database.append_event(
                "production",
                normalized_id,
                "production.media_imported",
                {
                    "artifact_id": artifact["id"],
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "deduplicated": imported.deduplicated,
                },
            )
            return {
                "schema_version": 1,
                "artifact": artifact,
                "deduplicated": imported.deduplicated,
            }

    def cancel_job(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Cancel exactly one durable Job and report worker retirement truth.

        The URL owns the only mutable identity.  The body cannot select a
        process, provider task, timeout, or force mode; those relationships are
        resolved from the admitted Job and its durable SQLite lineage.
        """

        validate_identifier(job_id, label="job id")
        try:
            validate_job_cancel_payload(body)
        except JobControlValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        job = self.database.get_job(job_id)
        if job is None:
            raise KeyError("job not found")
        was_active = bool(
            job.get("status") in {"queued", "running"}
            or self.jobs.is_admitted(job_id)
        )
        current = (
            self.jobs.cancel_and_wait(job_id, timeout=0.25)
            if was_active
            else job
        )
        if current is None:
            raise KeyError("job not found")
        return {
            "schema_version": JOB_CONTROL_SCHEMA_VERSION,
            "job": current,
            "cancel_requested": was_active,
            "worker_retired": not self.jobs.is_admitted(job_id),
        }

    def production_detail(
        self, production_id: str, *, artifact_limit: int = 5000, artifact_offset: int = 0
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        return self.database.get_production_detail(
            production_id,
            artifact_limit=max(1, min(int(artifact_limit), 10_000)),
            artifact_offset=max(0, int(artifact_offset)),
        )

    def list_announcement_recipes(self, production_id: str) -> dict[str, Any]:
        """Return editable latest recipes plus immutable version/link history."""

        validate_identifier(production_id, label="production id")
        snapshot = self.database.announcement_snapshot(production_id)
        recipes = snapshot["recipes"]
        versions = snapshot["recipe_versions"]
        executions = snapshot["executions"]
        return {
            "schema_version": ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
            "production_id": production_id,
            "recipes": recipes,
            "recipe_versions": versions,
            "executions": executions,
            "count": len(recipes),
        }

    def save_announcement_recipe(
        self, production_id: str, recipe_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or append one CAS-protected editable recipe revision."""

        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        try:
            normalized_id = validate_announcement_recipe_id(recipe_id)
            expected_revision, recipe = validate_announcement_save_payload(body)
            summary = announcement_recipe_audit_summary(recipe)
            record, created = self.database.save_announcement_recipe(
                production_id,
                normalized_id,
                expected_revision=expected_revision,
                recipe=recipe,
                summary=summary,
            )
        except AnnouncementVideoValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        except ValueError as exc:
            if str(exc) == "announcement recipe revision conflict":
                raise RequestValidationError(
                    "The announcement recipe changed after it was loaded.",
                    code="announcement_recipe_conflict",
                ) from exc
            raise
        return {**record, "deduplicated": not created}

    def duplicate_announcement_recipe(
        self, production_id: str, recipe_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Clone one immutable revision to a new editable recipe identity."""

        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        try:
            source_id = validate_announcement_recipe_id(recipe_id)
            request = validate_announcement_duplicate_payload(body)
        except AnnouncementVideoValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        source = self.database.get_announcement_recipe(
            production_id,
            source_id,
            revision=request["source_revision"],
        )
        if source is None:
            raise KeyError("announcement recipe not found")
        cloned_body = {**source["recipe"], "name": request["name"]}
        try:
            recipe = validate_announcement_recipe_payload(cloned_body)
            record, created = self.database.save_announcement_recipe(
                production_id,
                request["new_recipe_id"],
                expected_revision=0,
                recipe=recipe,
                summary=announcement_recipe_audit_summary(recipe),
                clone_source_version_id=source["version_id"],
            )
        except AnnouncementVideoValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        except ValueError as exc:
            if str(exc) == "announcement recipe revision conflict":
                raise RequestValidationError(
                    "The duplicate recipe identity is already in use.",
                    code="announcement_recipe_conflict",
                ) from exc
            raise
        return {**record, "deduplicated": not created}

    def execute_announcement_recipe(
        self, production_id: str, recipe_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Compile and execute one saved recipe on the unchanged Detailed path."""

        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        try:
            normalized_id = validate_announcement_recipe_id(recipe_id)
            recipe_revision = validate_announcement_execute_payload(body)
        except AnnouncementVideoValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        record = self.database.get_announcement_recipe(
            production_id, normalized_id, revision=recipe_revision
        )
        if record is None:
            raise KeyError("announcement recipe not found")
        try:
            recipe = validate_announcement_recipe_payload(record["recipe"])
            detailed_payload = announcement_recipe_to_detailed_payload(recipe)
        except AnnouncementVideoValidationError as exc:
            raise RequestValidationError(str(exc), code=exc.code) from exc
        submitted = self.execute_detailed_test_video(
            production_id,
            detailed_payload,
            _announcement_recipe=record,
        )
        link = self.database.get_announcement_execution(
            production_id, record["version_id"], submitted["id"]
        )
        if link is None:
            raise RuntimeError("The announcement execution link was not committed.")
        return {
            **submitted,
            "announcement_recipe_id": record["id"],
            "announcement_recipe_version_id": record["version_id"],
            "announcement_recipe_revision": record["revision"],
            "announcement_execution": link,
        }

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
        local_zero_cost_plan = bool(affected_stages) and (
            (
                execution_profile == "local_sapi"
                and affected_stages.issubset(_LOCAL_SAPI_ZERO_COST_STAGES)
            )
            or (
                execution_profile == "local_comfyui"
                and affected_stages.issubset(_LOCAL_COMFYUI_ZERO_COST_STAGES)
            )
            or (
                execution_profile == "local_playwright"
                and affected_stages.issubset(_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES)
            )
            or (
                execution_profile == "local_windows_capture"
                and affected_stages.issubset(
                    _LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES
                )
            )
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
        if (
            execution_profile == "local_comfyui"
            and amount_minor == 0
            and (
                _LOCAL_VIDEO_GENERATION_STAGE not in affected_stages
                or not affected_stages.issubset(_LOCAL_COMFYUI_ZERO_COST_STAGES)
            )
        ):
            raise RequestValidationError(
                "local_comfyui runs require video_generation and may only affect video_generation, timeline, assembly, or qc.",
                code="local_profile_stage_not_allowed",
            )
        if (
            execution_profile == "local_playwright"
            and amount_minor == 0
            and (
                _LOCAL_SCREEN_CAPTURE_STAGE not in affected_stages
                or not affected_stages.issubset(_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES)
            )
        ):
            raise RequestValidationError(
                "local_playwright runs require screen_capture and may only affect screen_capture, timeline, assembly, or qc.",
                code="local_profile_stage_not_allowed",
            )
        if (
            execution_profile == "local_windows_capture"
            and amount_minor == 0
            and (
                _LOCAL_SCREEN_CAPTURE_STAGE not in affected_stages
                or not affected_stages.issubset(
                    _LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES
                )
            )
        ):
            raise RequestValidationError(
                "local_windows_capture runs require screen_capture and may only affect screen_capture, timeline, assembly, or qc.",
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
        if execution_profile == "local_comfyui":
            if amount_minor != 0:
                raise RequestValidationError(
                    "local_comfyui runs must use a zero-cost estimate.",
                    code="local_profile_cost_not_allowed",
                )
            if (
                _LOCAL_VIDEO_GENERATION_STAGE not in affected_stages
                or not affected_stages.issubset(_LOCAL_COMFYUI_ZERO_COST_STAGES)
            ):
                raise RequestValidationError(
                    "local_comfyui runs require video_generation and may only affect video_generation, timeline, assembly, or qc.",
                    code="local_profile_stage_not_allowed",
                )
        if execution_profile == "local_playwright":
            if amount_minor != 0:
                raise RequestValidationError(
                    "local_playwright runs must use a zero-cost estimate.",
                    code="local_profile_cost_not_allowed",
                )
            if (
                _LOCAL_SCREEN_CAPTURE_STAGE not in affected_stages
                or not affected_stages.issubset(_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES)
            ):
                raise RequestValidationError(
                    "local_playwright runs require screen_capture and may only affect screen_capture, timeline, assembly, or qc.",
                    code="local_profile_stage_not_allowed",
                )
        if execution_profile == "local_windows_capture":
            if amount_minor != 0:
                raise RequestValidationError(
                    "local_windows_capture runs must use a zero-cost estimate.",
                    code="local_profile_cost_not_allowed",
                )
            if (
                _LOCAL_SCREEN_CAPTURE_STAGE not in affected_stages
                or not affected_stages.issubset(
                    _LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES
                )
            ):
                raise RequestValidationError(
                    "local_windows_capture runs require screen_capture and may only affect screen_capture, timeline, assembly, or qc.",
                    code="local_profile_stage_not_allowed",
                )
        parent_revision_id = body.get("parent_revision_id")
        if parent_revision_id is not None:
            validate_identifier(parent_revision_id, label="parent revision id")
        persisted_plan = plan
        if execution_profile in {"local_playwright", "local_windows_capture"}:
            # The generic dependency planner retains assembly/QC as impacted
            # downstream work, but this profile owns executable workers only
            # for capture and timeline. Keep that distinction durable so an
            # assembly/QC panel never treats this Run as executable.
            persisted_plan = {
                **plan,
                "requested_stages": list(
                    _LOCAL_PLAYWRIGHT_EXECUTION_STAGES
                    if execution_profile == "local_playwright"
                    else _LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES
                ),
            }
        revision, run = self.database.create_revision_and_run(
            production_id,
            persisted_plan["changes"],
            persisted_plan,
            amount_minor,
            currency,
            parent_revision_id=parent_revision_id,
            execution_profile=execution_profile,
        )
        return {"revision": revision, "run": run}

    @staticmethod
    def _pipeline_artifact_view(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        artifact_id = value.get("id", value.get("artifact_id"))
        rel_path = value.get("rel_path", value.get("path"))
        media_type = value.get("media_type", value.get("mime"))
        view = {
            "id": artifact_id,
            "name": value.get("name"),
            "kind": value.get("kind"),
            "media_type": media_type,
            "rel_path": rel_path,
            "bytes": value.get("bytes"),
            "sha256": value.get("sha256"),
        }
        if (
            not isinstance(artifact_id, str)
            or not isinstance(view["name"], str)
            or not isinstance(view["kind"], str)
            or not isinstance(media_type, str)
            or not isinstance(rel_path, str)
            or isinstance(view["bytes"], bool)
            or not isinstance(view["bytes"], int)
            or view["bytes"] <= 0
            or not isinstance(view["sha256"], str)
            or re.fullmatch(r"[0-9A-Fa-f]{64}", view["sha256"]) is None
        ):
            return None
        view["sha256"] = view["sha256"].upper()
        return view

    def _verified_pipeline_attempt(
        self,
        run: dict[str, Any],
        stage: str,
        attempt_id: Any,
        pipeline_key: str,
    ) -> dict[str, Any]:
        try:
            validate_identifier(attempt_id, label="stage attempt id")
        except (SecurityError, TypeError, ValueError):
            raise RequestValidationError(
                "The local pipeline stage lineage is invalid.",
                code="invalid_provenance",
            ) from None
        attempt = self.database.get_stage_attempt(attempt_id)
        job = (
            self.database.get_job(attempt.get("job_id"))
            if isinstance(attempt, dict) and isinstance(attempt.get("job_id"), str)
            else None
        )
        attempt_result = attempt.get("result") if isinstance(attempt, dict) else None
        job_result = job.get("result") if isinstance(job, dict) else None
        job_payload = job.get("payload") if isinstance(job, dict) else None
        if (
            not isinstance(attempt, dict)
            or attempt.get("run_id") != run["id"]
            or attempt.get("production_id") != run["production_id"]
            or attempt.get("stage") != stage
            or attempt.get("status") != "succeeded"
            or not isinstance(attempt_result, dict)
            or not isinstance(job, dict)
            or job.get("id") != attempt.get("job_id")
            or job.get("production_id") != run["production_id"]
            or job.get("status") != "succeeded"
            or not isinstance(job_payload, dict)
            or job_payload.get("run_id") != run["id"]
            or job_payload.get("stage") != stage
            or job_payload.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or job_payload.get("pipeline_key") != pipeline_key
            or job_payload.get("stage_attempt_id") != attempt_id
            or not isinstance(job_result, dict)
            or job_result.get("stage_attempt_id") != attempt_id
            or {key: value for key, value in job_result.items() if key != "stage_attempt_id"}
            != attempt_result
        ):
            raise RequestValidationError(
                "The local pipeline stage lineage could not be verified.",
                code="invalid_provenance",
            )
        return attempt

    def _verified_pipeline_video_recovery_checkpoint(
        self,
        run: dict[str, Any],
        pipeline_key: str,
        cache_key: str,
        checkpoint: Any,
    ) -> dict[str, str]:
        """Verify one successful same-run video source for cache-only replay.

        A normal pipeline video attempt is already bound by ``pipeline_key``
        and an empty video lineage.  A restart-recovery attempt predates that
        normal lineage hop, so it is accepted only when its exact provider-task
        owner is terminal-successful.  In both cases the new continuation
        creates a fresh, normally lineage-bound video child; this checkpoint is
        only the required source of its verified cache hit.
        """

        if (
            not isinstance(checkpoint, dict)
            or set(checkpoint) != {"job_id", "stage_attempt_id"}
        ):
            raise RequestValidationError(
                "The recovered video checkpoint is invalid.",
                code="invalid_provenance",
            )
        source_job_id = checkpoint.get("job_id")
        source_attempt_id = checkpoint.get("stage_attempt_id")
        try:
            validate_identifier(source_job_id, label="source job id")
            validate_identifier(
                source_attempt_id, label="source stage attempt id"
            )
        except (SecurityError, TypeError, ValueError):
            raise RequestValidationError(
                "The recovered video checkpoint is invalid.",
                code="invalid_provenance",
            ) from None

        attempt = self.database.get_stage_attempt(source_attempt_id)
        job = self.database.get_job(source_job_id)
        attempt_payload = attempt.get("payload") if isinstance(attempt, dict) else None
        attempt_result = attempt.get("result") if isinstance(attempt, dict) else None
        job_payload = job.get("payload") if isinstance(job, dict) else None
        job_result = job.get("result") if isinstance(job, dict) else None
        if (
            not isinstance(attempt, dict)
            or attempt.get("id") != source_attempt_id
            or attempt.get("job_id") != source_job_id
            or attempt.get("run_id") != run["id"]
            or attempt.get("production_id") != run["production_id"]
            or attempt.get("stage") != _LOCAL_VIDEO_GENERATION_STAGE
            or attempt.get("status") != "succeeded"
            or attempt.get("cache_key") != cache_key
            or not isinstance(attempt_payload, dict)
            or attempt_payload.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or attempt_payload.get("cache_key") != cache_key
            or not isinstance(attempt_result, dict)
            or attempt_result.get("cache_key") != cache_key
            or not isinstance(attempt_result.get("cache_hit"), bool)
            or not isinstance(job, dict)
            or job.get("id") != source_job_id
            or job.get("kind") != "local_video_generation"
            or job.get("production_id") != run["production_id"]
            or job.get("status") != "succeeded"
            or not isinstance(job_payload, dict)
            or job_payload.get("run_id") != run["id"]
            or job_payload.get("production_id") != run["production_id"]
            or job_payload.get("stage") != _LOCAL_VIDEO_GENERATION_STAGE
            or job_payload.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or job_payload.get("cache_key") != cache_key
            or job_payload.get("stage_attempt_id") != source_attempt_id
            or not isinstance(job_result, dict)
            or job_result.get("stage_attempt_id") != source_attempt_id
            or {
                key: value
                for key, value in job_result.items()
                if key != "stage_attempt_id"
            }
            != attempt_result
        ):
            raise RequestValidationError(
                "The recovered video checkpoint could not be verified.",
                code="invalid_provenance",
            )

        pipeline_bound = bool(
            attempt_payload.get("pipeline_key") == pipeline_key
            and attempt_payload.get("pipeline_lineage") == {}
            and job_payload.get("pipeline_key") == pipeline_key
            and job_payload.get("pipeline_lineage") == {}
        )
        recovery_record_id = job_payload.get("provider_task_record_id")
        restart_recovery_bound = bool(
            attempt_payload.get("restart_recovery") is True
            and job_payload.get("restart_recovery") is True
            and isinstance(recovery_record_id, str)
            and attempt_payload.get("provider_task_record_id")
            == recovery_record_id
        )
        if restart_recovery_bound:
            try:
                validate_identifier(
                    recovery_record_id, label="provider task record id"
                )
                provider_task = self.database.get_provider_task(recovery_record_id)
            except (SecurityError, TypeError, ValueError):
                provider_task = None
            restart_recovery_bound = bool(
                isinstance(provider_task, dict)
                and provider_task.get("status") == "succeeded"
                and provider_task.get("production_id") == run["production_id"]
                and provider_task.get("run_id") == run["id"]
                and provider_task.get("stage") == _LOCAL_VIDEO_GENERATION_STAGE
                and provider_task.get("cache_key") == cache_key
                and provider_task.get("current_stage_attempt_id")
                == source_attempt_id
                and provider_task.get("current_job_id") == source_job_id
                and provider_task.get("provider_task_id")
                == attempt_result.get("provider_task_id")
            )
        if not pipeline_bound and not restart_recovery_bound:
            raise RequestValidationError(
                "The recovered video checkpoint lineage is invalid.",
                code="invalid_provenance",
            )
        return {
            "job_id": source_job_id,
            "stage_attempt_id": source_attempt_id,
        }

    def _verified_pipeline_artifact(
        self,
        run: dict[str, Any],
        attempt: dict[str, Any],
        supplied: Any,
    ) -> dict[str, Any]:
        expected = self._pipeline_artifact_view(supplied)
        result = attempt.get("result")
        raw_artifacts = result.get("artifacts") if isinstance(result, dict) else None
        matches = (
            [
                self._pipeline_artifact_view(item)
                for item in raw_artifacts
                if isinstance(item, dict)
                and expected is not None
                and item.get("id", item.get("artifact_id")) == expected["id"]
            ]
            if isinstance(raw_artifacts, list)
            else []
        )
        registered = (
            self.database.get_artifact(expected["id"])
            if expected is not None
            else None
        )
        registered_view = self._pipeline_artifact_view(registered)
        if (
            expected is None
            or len(matches) != 1
            or matches[0] != expected
            or registered_view != expected
            or not isinstance(registered, dict)
            or registered.get("production_id") != run["production_id"]
            or registered.get("available") is not True
            or registered.get("origin") != "studio"
        ):
            raise RequestValidationError(
                "The local pipeline artifact lineage could not be verified.",
                code="invalid_provenance",
            )
        return expected

    def _validate_pipeline_child_lineage(
        self,
        run: dict[str, Any],
        stage: str,
        body: dict[str, Any],
        pipeline_key: str,
        lineage: Any,
    ) -> dict[str, Any]:
        if not isinstance(lineage, dict) or any(
            not isinstance(key, str) for key in lineage
        ):
            raise RequestValidationError(
                "The local pipeline lineage is invalid.", code="invalid_provenance"
            )
        expected_keys = {
            "video_generation": set(),
            "narration": {"video_generation_attempt_id"},
            "timeline": {
                "video_generation_attempt_id",
                "narration_attempt_id",
                "video_artifact",
            },
            "assembly": {
                "narration_attempt_id",
                "timeline_attempt_id",
                "timeline_artifact",
            },
            "qc": {"assembly_attempt_id", "master_artifact"},
        }
        if stage not in expected_keys or set(lineage) != expected_keys[stage]:
            raise RequestValidationError(
                "The local pipeline lineage is incomplete.", code="invalid_provenance"
            )

        verified: dict[str, Any] = {}
        if stage in {"narration", "timeline"}:
            video_attempt = self._verified_pipeline_attempt(
                run,
                "video_generation",
                lineage["video_generation_attempt_id"],
                pipeline_key,
            )
            verified["video_generation_attempt_id"] = video_attempt["id"]
        if stage in {"timeline", "assembly"}:
            narration_attempt = self._verified_pipeline_attempt(
                run,
                "narration",
                lineage["narration_attempt_id"],
                pipeline_key,
            )
            verified["narration_attempt_id"] = narration_attempt["id"]
        if stage == "timeline":
            video_artifact = self._verified_pipeline_artifact(
                run, video_attempt, lineage["video_artifact"]
            )
            clips = body.get("clips") if isinstance(body, dict) else None
            if (
                not isinstance(clips, list)
                or len(clips) != 1
                or not isinstance(clips[0], dict)
                or clips[0].get("video_artifact_id") != video_artifact["id"]
            ):
                raise RequestValidationError(
                    "The local pipeline timeline input changed.",
                    code="input_changed",
                )
            verified["video_artifact_id"] = video_artifact["id"]
            verified["video_artifact_sha256"] = video_artifact["sha256"]
        if stage == "assembly":
            timeline_attempt = self._verified_pipeline_attempt(
                run,
                "timeline",
                lineage["timeline_attempt_id"],
                pipeline_key,
            )
            timeline_artifact = self._verified_pipeline_artifact(
                run, timeline_attempt, lineage["timeline_artifact"]
            )
            if (
                body.get("narration_attempt_id") != narration_attempt["id"]
                or body.get("video_artifact_id") != timeline_artifact["id"]
            ):
                raise RequestValidationError(
                    "The local pipeline assembly input changed.", code="input_changed"
                )
            verified["timeline_attempt_id"] = timeline_attempt["id"]
            verified["timeline_artifact_id"] = timeline_artifact["id"]
            verified["timeline_artifact_sha256"] = timeline_artifact["sha256"]
        if stage == "qc":
            assembly_attempt = self._verified_pipeline_attempt(
                run,
                "assembly",
                lineage["assembly_attempt_id"],
                pipeline_key,
            )
            master = self._verified_pipeline_artifact(
                run, assembly_attempt, lineage["master_artifact"]
            )
            expected_name = (
                "master-captioned.mp4"
                if body.get("variant") == "captioned"
                else "master-clean.mp4"
            )
            if (
                body.get("assembly_attempt_id") != assembly_attempt["id"]
                or master["name"] != expected_name
            ):
                raise RequestValidationError(
                    "The local pipeline QC input changed.", code="input_changed"
                )
            verified["assembly_attempt_id"] = assembly_attempt["id"]
            verified["master_artifact_id"] = master["id"]
            verified["master_artifact_sha256"] = master["sha256"]
        return verified

    def _pipeline_run(self, run_id: str, pipeline_key: str) -> dict[str, Any]:
        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if (
            run is None
            or run.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or run.get("pipeline_key") != pipeline_key
            or set(run.get("requested_stages", []))
            != _LOCAL_PIPELINE_ZERO_COST_STAGES
            or run.get("estimated_cost", {}).get("amount") != "0.00"
        ):
            raise RequestValidationError(
                "The local pipeline run is invalid.", code="invalid_provenance"
            )
        return run

    def _pipeline_child_metadata(
        self,
        run: dict[str, Any],
        capability: object | None,
        pipeline_key: str | None,
        lineage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if run.get("execution_profile") != LOCAL_PIPELINE_PROFILE:
            if capability is not None or pipeline_key is not None or lineage is not None:
                raise RequestValidationError(
                    "Internal pipeline metadata is not accepted for this run.",
                    code="invalid_provenance",
                )
            return {}
        if (
            capability is not self._pipeline_capability
            or pipeline_key != run.get("pipeline_key")
            or not isinstance(lineage, dict)
        ):
            raise RequestValidationError(
                "Direct execution of a local pipeline child is blocked.",
                code="execution_profile_required",
            )
        return {
            "pipeline_key": pipeline_key,
            "pipeline_lineage": sanitize_for_storage(lineage),
        }

    def _pipeline_artifact_is_intact(
        self, production_id: str, value: Any
    ) -> bool:
        expected = self._pipeline_artifact_view(value)
        if expected is None:
            return False
        registered = self.database.get_artifact(expected["id"])
        if (
            self._pipeline_artifact_view(registered) != expected
            or not isinstance(registered, dict)
            or registered.get("production_id") != production_id
            or registered.get("available") is not True
            or registered.get("origin") != "studio"
            or sensitive_artifact_path(expected["rel_path"])
        ):
            return False
        try:
            if _has_symlink_component(self.workspace, expected["rel_path"]):
                return False
            path = workspace_path(
                self.workspace, expected["rel_path"], must_exist=True
            )
            stat = path.stat()
            return bool(
                not path.is_symlink()
                and path.is_file()
                and stat.st_size == expected["bytes"]
                and _sha256_file(path) == expected["sha256"]
            )
        except (SecurityError, OSError):
            return False

    def _reusable_succeeded_pipeline_job(
        self,
        job: dict[str, Any],
        run: dict[str, Any],
        revision: dict[str, Any],
        pipeline_key: str,
        payload: dict[str, Any],
    ) -> bool:
        result = job.get("result")
        if not isinstance(result, dict):
            return False
        child_jobs = result.get("jobs")
        expected_child_kinds = {
            "video_generation": "local_video_generation",
            "narration": "local_narration",
            "timeline": "local_timeline",
            "assembly": "local_assembly",
            "qc": "local_qc",
        }
        if not isinstance(child_jobs, dict) or set(child_jobs) != set(
            expected_child_kinds
        ):
            return False
        seen_job_ids: set[str] = set()
        seen_attempt_ids: set[str] = set()
        attempt_results: dict[str, dict[str, Any]] = {}
        child_payloads: dict[str, dict[str, Any]] = {}
        for stage, expected_kind in expected_child_kinds.items():
            child = child_jobs.get(stage)
            if not isinstance(child, dict) or set(child) != {
                "job_id",
                "stage_attempt_id",
                "cache_hit",
            }:
                return False
            child_job_id = child.get("job_id")
            attempt_id = child.get("stage_attempt_id")
            try:
                validate_identifier(child_job_id, label="job id")
                validate_identifier(attempt_id, label="stage attempt id")
            except (SecurityError, TypeError, ValueError):
                return False
            if (
                child_job_id in seen_job_ids
                or attempt_id in seen_attempt_ids
                or not isinstance(child.get("cache_hit"), bool)
            ):
                return False
            seen_job_ids.add(child_job_id)
            seen_attempt_ids.add(attempt_id)
            child_job = self.database.get_job(child_job_id)
            attempt = self.database.get_stage_attempt(attempt_id)
            child_payload = (
                child_job.get("payload") if isinstance(child_job, dict) else None
            )
            child_result = (
                child_job.get("result") if isinstance(child_job, dict) else None
            )
            attempt_result = (
                attempt.get("result") if isinstance(attempt, dict) else None
            )
            if (
                not isinstance(child_job, dict)
                or child_job.get("kind") != expected_kind
                or child_job.get("status") != "succeeded"
                or child_job.get("production_id") != run["production_id"]
                or not isinstance(child_payload, dict)
                or child_payload.get("run_id") != run["id"]
                or child_payload.get("production_id") != run["production_id"]
                or child_payload.get("stage") != stage
                or child_payload.get("stage_attempt_id") != attempt_id
                or child_payload.get("execution_profile") != LOCAL_PIPELINE_PROFILE
                or child_payload.get("pipeline_key") != pipeline_key
                or not isinstance(child_result, dict)
                or child_result.get("stage_attempt_id") != attempt_id
                or child_result.get("cache_hit") != child.get("cache_hit")
                or not isinstance(attempt_result, dict)
                or {
                    key: value
                    for key, value in child_result.items()
                    if key != "stage_attempt_id"
                }
                != attempt_result
                or not isinstance(attempt, dict)
                or attempt.get("id") != attempt_id
                or attempt.get("job_id") != child_job_id
                or attempt.get("run_id") != run["id"]
                or attempt.get("production_id") != run["production_id"]
                or attempt.get("stage") != stage
                or attempt.get("status") != "succeeded"
            ):
                return False
            attempt_results[stage] = attempt_result
            child_payloads[stage] = child_payload
        assembly_artifacts = dict(_LOCAL_ASSEMBLY_ARTIFACTS)
        if not payload["include_captioned"]:
            assembly_artifacts.pop("master-captioned.mp4", None)
        expected_stage_artifacts = {
            "video_generation": _LOCAL_COMFYUI_ARTIFACTS,
            "narration": _LOCAL_NARRATION_ARTIFACTS,
            "timeline": _LOCAL_TIMELINE_ARTIFACTS,
            "assembly": assembly_artifacts,
            "qc": _LOCAL_QC_ARTIFACTS,
        }
        for stage, expected_specs in expected_stage_artifacts.items():
            raw = attempt_results[stage].get("artifacts")
            if not isinstance(raw, list) or len(raw) != len(expected_specs):
                return False
            by_name: dict[str, dict[str, Any]] = {}
            for item in raw:
                view = self._pipeline_artifact_view(item)
                if view is None or view["name"] in by_name:
                    return False
                by_name[view["name"]] = view
            if set(by_name) != set(expected_specs):
                return False
            if any(
                view["kind"] != expected_specs[name][0]
                or view["media_type"] != expected_specs[name][1]
                or not self._pipeline_artifact_is_intact(
                    run["production_id"], view
                )
                for name, view in by_name.items()
            ):
                return False
        expected_master_name = (
            "master-captioned.mp4"
            if payload["variant"] == "captioned"
            else "master-clean.mp4"
        )
        artifacts = result.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 4:
            return False
        names = {
            item.get("name") for item in artifacts if isinstance(item, dict)
        }
        if names != {
            expected_master_name,
            "technical-qc.json",
            "ffprobe.json",
            "manifest.json",
        }:
            return False
        master = self._pipeline_artifact_view(result.get("master"))
        generated = self._pipeline_artifact_view(result.get("video"))
        timeline = self._pipeline_artifact_view(result.get("timeline"))
        selected = [
            self._pipeline_artifact_view(item)
            for item in artifacts
            if isinstance(item, dict) and item.get("name") == expected_master_name
        ]
        qc_result = result.get("qc")
        reports = (
            qc_result.get("report_artifacts")
            if isinstance(qc_result, dict)
            else None
        )
        report_views = (
            [self._pipeline_artifact_view(item) for item in reports]
            if isinstance(reports, list)
            else []
        )
        final_report_views = [
            self._pipeline_artifact_view(item)
            for item in artifacts
            if isinstance(item, dict) and item.get("name") != expected_master_name
        ]

        def child_artifact(stage: str, name: str) -> dict[str, Any] | None:
            raw = attempt_results.get(stage, {}).get("artifacts")
            matches = (
                [
                    self._pipeline_artifact_view(item)
                    for item in raw
                    if isinstance(item, dict) and item.get("name") == name
                ]
                if isinstance(raw, list)
                else []
            )
            return matches[0] if len(matches) == 1 else None

        report_names = {"technical-qc.json", "ffprobe.json", "manifest.json"}
        report_view_by_name = {
            item["name"]: item for item in report_views if isinstance(item, dict)
        }
        final_report_view_by_name = {
            item["name"]: item
            for item in final_report_views
            if isinstance(item, dict)
        }
        expected_lineages = {
            "video_generation": {},
            "narration": {
                "video_generation_attempt_id": child_jobs["video_generation"][
                    "stage_attempt_id"
                ]
            },
            "timeline": {
                "video_generation_attempt_id": child_jobs["video_generation"][
                    "stage_attempt_id"
                ],
                "narration_attempt_id": child_jobs["narration"][
                    "stage_attempt_id"
                ],
                "video_artifact_id": generated["id"] if generated else None,
                "video_artifact_sha256": generated["sha256"] if generated else None,
            },
            "assembly": {
                "narration_attempt_id": child_jobs["narration"][
                    "stage_attempt_id"
                ],
                "timeline_attempt_id": child_jobs["timeline"][
                    "stage_attempt_id"
                ],
                "timeline_artifact_id": timeline["id"] if timeline else None,
                "timeline_artifact_sha256": timeline["sha256"] if timeline else None,
            },
            "qc": {
                "assembly_attempt_id": child_jobs["assembly"][
                    "stage_attempt_id"
                ],
                "master_artifact_id": master["id"] if master else None,
                "master_artifact_sha256": master["sha256"] if master else None,
            },
        }
        qc_child_result = attempt_results.get("qc", {})
        qc_child_verdict = qc_child_result.get(
            "technical_verdict", qc_child_result.get("verdict")
        )
        if (
            result.get("production_id") != run["production_id"]
            or result.get("run_id") != run["id"]
            or result.get("revision_id") != revision["id"]
            or result.get("pipeline_key") != pipeline_key
            or result.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or result.get("technical_verdict") != "pass"
            or result.get("variant") != payload["variant"]
            or result.get("caption_style_preset")
            != payload["caption_style_preset"]
            or result.get("workflow_preset") != payload["workflow_preset"]
            or result.get("prompt_sha256")
            != hashlib.sha256(payload["prompt"].encode("utf-8")).hexdigest().upper()
            or result.get("seed_decimal") != str(payload["seed"])
            or isinstance(result.get("duration_ms"), bool)
            or not isinstance(result.get("duration_ms"), int)
            or result.get("duration_ms") <= 0
            or attempt_results.get("video_generation", {}).get("duration_ms")
            != result.get("duration_ms")
            or qc_child_result.get("analysis_status") != "succeeded"
            or qc_child_verdict != "pass"
            or any(
                child_payloads[stage].get("pipeline_lineage") != expected
                for stage, expected in expected_lineages.items()
            )
            or generated is None
            or generated.get("name") != "generated-video.mp4"
            or generated.get("kind") != "video"
            or generated
            != child_artifact("video_generation", "generated-video.mp4")
            or timeline is None
            or timeline.get("name") != "timeline-preview.mp4"
            or timeline.get("kind") != "video"
            or timeline != child_artifact("timeline", "timeline-preview.mp4")
            or len(selected) != 1
            or selected[0] is None
            or master != selected[0]
            or master != child_artifact("assembly", expected_master_name)
            or not isinstance(qc_result, dict)
            or qc_result.get("verdict") != "pass"
            or not isinstance(reports, list)
            or len(reports) != 3
            or any(item is None for item in report_views)
            or {
                item.get("name") for item in reports if isinstance(item, dict)
            }
            != report_names
            or set(report_view_by_name) != report_names
            or set(final_report_view_by_name) != report_names
            or report_view_by_name != final_report_view_by_name
            or any(
                view != child_artifact("qc", name)
                for name, view in report_view_by_name.items()
            )
        ):
            return False
        # Every top-level artifact is now exactly bound to a child artifact,
        # and every child artifact was physically rehashed above.
        return True

    def _reusable_succeeded_detailed_test_video_job(
        self,
        job: dict[str, Any],
        run: dict[str, Any],
        revision: dict[str, Any],
        request_key: str,
        payload: dict[str, Any],
        expected_job_payload: dict[str, Any],
        narration_segment_start_ms: tuple[int, ...] | None = None,
    ) -> bool:
        """Rehash every child artifact before reusing a succeeded top job."""

        result = job.get("result")
        if (
            job.get("kind") != DETAILED_TEST_VIDEO_JOB_KIND
            or job.get("status") != "succeeded"
            or job.get("production_id") != run.get("production_id")
            or job.get("payload") != expected_job_payload
            or not isinstance(result, dict)
        ):
            return False
        try:
            public = detailed_test_video_public_result(
                result,
                production_id=run["production_id"],
                run_id=run["id"],
                revision_id=revision["id"],
                request_key=request_key,
                payload=payload,
                narration_segment_start_ms=narration_segment_start_ms,
            )
        except (DetailedTestVideoError, DetailedTestVideoValidationError):
            return False

        expected_child_kinds = {
            "narration": "local_narration",
            "timeline": "local_remotion_timeline",
            "assembly": "local_assembly",
            "qc": "local_qc",
        }
        children = public.get("children")
        if not isinstance(children, dict) or set(children) != set(
            expected_child_kinds
        ):
            return False
        seen_jobs: set[str] = set()
        seen_attempts: set[str] = set()
        attempt_results: dict[str, dict[str, Any]] = {}
        child_payloads: dict[str, dict[str, Any]] = {}
        for stage, expected_kind in expected_child_kinds.items():
            child = children.get(stage)
            if not isinstance(child, dict):
                return False
            child_job_id = child.get("job_id")
            attempt_id = child.get("stage_attempt_id")
            try:
                validate_identifier(child_job_id, label="child job id")
                validate_identifier(attempt_id, label="child stage attempt id")
            except (SecurityError, TypeError, ValueError):
                return False
            if child_job_id in seen_jobs or attempt_id in seen_attempts:
                return False
            seen_jobs.add(child_job_id)
            seen_attempts.add(attempt_id)
            child_job = self.database.get_job(child_job_id)
            attempt = self.database.get_stage_attempt(attempt_id)
            child_payload = (
                child_job.get("payload") if isinstance(child_job, dict) else None
            )
            child_result = (
                child_job.get("result") if isinstance(child_job, dict) else None
            )
            attempt_result = (
                attempt.get("result") if isinstance(attempt, dict) else None
            )
            if (
                not isinstance(child_job, dict)
                or child_job.get("kind") != expected_kind
                or child_job.get("status") != "succeeded"
                or child_job.get("production_id") != run["production_id"]
                or not isinstance(child_payload, dict)
                or child_payload.get("run_id") != run["id"]
                or child_payload.get("production_id") != run["production_id"]
                or child_payload.get("stage") != stage
                or child_payload.get("stage_attempt_id") != attempt_id
                or child_payload.get("execution_profile")
                != DETAILED_TEST_VIDEO_PROFILE
                or not isinstance(child_result, dict)
                or child_result.get("stage_attempt_id") != attempt_id
                or child_result.get("cache_hit") != child.get("cache_hit")
                or not isinstance(attempt_result, dict)
                or {
                    key: value
                    for key, value in child_result.items()
                    if key != "stage_attempt_id"
                }
                != attempt_result
                or not isinstance(attempt, dict)
                or attempt.get("id") != attempt_id
                or attempt.get("job_id") != child_job_id
                or attempt.get("run_id") != run["id"]
                or attempt.get("production_id") != run["production_id"]
                or attempt.get("stage") != stage
                or attempt.get("status") != "succeeded"
            ):
                return False
            attempt_results[stage] = attempt_result
            child_payloads[stage] = child_payload

        assembly_artifacts = dict(_LOCAL_ASSEMBLY_ARTIFACTS)
        if not payload["include_captioned"]:
            assembly_artifacts.pop("master-captioned.mp4", None)
        expected_stage_artifacts = {
            "narration": _LOCAL_NARRATION_ARTIFACTS,
            "timeline": _LOCAL_REMOTION_TIMELINE_ARTIFACTS,
            "assembly": assembly_artifacts,
            "qc": _LOCAL_QC_ARTIFACTS,
        }
        stage_artifacts: dict[str, dict[str, dict[str, Any]]] = {}
        for stage, expected_specs in expected_stage_artifacts.items():
            raw_artifacts = attempt_results[stage].get("artifacts")
            if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
                expected_specs
            ):
                return False
            by_name: dict[str, dict[str, Any]] = {}
            for artifact in raw_artifacts:
                view = self._pipeline_artifact_view(artifact)
                if view is None or view["name"] in by_name:
                    return False
                by_name[view["name"]] = view
            if set(by_name) != set(expected_specs) or any(
                view["kind"] != expected_specs[name][0]
                or view["media_type"] != expected_specs[name][1]
                or not self._pipeline_artifact_is_intact(
                    run["production_id"], view
                )
                for name, view in by_name.items()
            ):
                return False
            stage_artifacts[stage] = by_name

        master_name = (
            "master-captioned.mp4"
            if payload["variant"] == "captioned"
            else "master-clean.mp4"
        )
        public_timeline = self._pipeline_artifact_view(public.get("timeline"))
        public_master = self._pipeline_artifact_view(public.get("master"))
        public_qc = public.get("qc")
        public_reports = (
            public_qc.get("report_artifacts")
            if isinstance(public_qc, dict)
            else None
        )
        report_views = (
            {
                view["name"]: view
                for value in public_reports
                if (view := self._pipeline_artifact_view(value)) is not None
            }
            if isinstance(public_reports, list)
            else {}
        )
        narration_payload = child_payloads["narration"]
        assembly_payload = child_payloads["assembly"]
        qc_payload = child_payloads["qc"]
        qc_child_verdict = attempt_results["qc"].get(
            "technical_verdict", attempt_results["qc"].get("verdict")
        )
        narration_fields = (
            "voice",
            "rate",
            "segment_count",
            "text_chars",
            "segment_text_sha256",
            "pronunciation_count",
            "narration_timing_policy",
            "narration_segment_start_ms",
        )
        if (
            public_timeline
            != stage_artifacts["timeline"].get("remotion-preview.mp4")
            or public_master != stage_artifacts["assembly"].get(master_name)
            or set(report_views) != set(_LOCAL_QC_ARTIFACTS)
            or report_views != stage_artifacts["qc"]
            or any(
                narration_payload.get(field) != expected_job_payload.get(field)
                for field in narration_fields
            )
            or child_payloads["timeline"].get("cache_key")
            != expected_job_payload.get("remotion_cache_key")
            or assembly_payload.get("video_artifact_id")
            != stage_artifacts["timeline"]["remotion-preview.mp4"]["id"]
            or assembly_payload.get("narration_attempt_id")
            != children["narration"]["stage_attempt_id"]
            or assembly_payload.get("include_captioned")
            != payload["include_captioned"]
            or assembly_payload.get("caption_style_preset")
            != payload["caption_style_preset"]
            or assembly_payload.get("audio_mix_preset")
            != payload["audio_mix_preset"]
            or qc_payload.get("assembly_attempt_id")
            != children["assembly"]["stage_attempt_id"]
            or qc_payload.get("assembly_artifact_id")
            != stage_artifacts["assembly"][master_name]["id"]
            or qc_payload.get("variant") != payload["variant"]
            or attempt_results["qc"].get("analysis_status") != "succeeded"
            or qc_child_verdict != "pass"
            or attempt_results["timeline"].get("duration_ms")
            != public.get("duration_ms")
            or attempt_results["assembly"].get("duration_ms")
            != public.get("duration_ms")
            or qc_payload.get("expected_duration_ms") != public.get("duration_ms")
        ):
            return False
        # The public final set is now exactly bound to physically rehashed child
        # artifacts. Every intermediate child artifact was also rehashed above.
        return True

    def _validated_local_pipeline_result(
        self,
        result: Any,
        *,
        run: dict[str, Any],
        revision: dict[str, Any],
        pipeline_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = {"result": result}
        if not self._reusable_succeeded_pipeline_job(
            candidate, run, revision, pipeline_key, payload
        ):
            raise LocalPipelineError(
                "The local pipeline returned an invalid result.",
                code="invalid_worker_result",
            )
        assert isinstance(result, dict)
        return result

    def _execute_local_pipeline_stage(
        self,
        run_id: str,
        stage: str,
        body: dict[str, Any],
        *,
        pipeline_key: str,
        lineage: dict[str, Any],
        video_recovery_checkpoint: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if video_recovery_checkpoint is not None and stage != _LOCAL_VIDEO_GENERATION_STAGE:
            raise RequestValidationError(
                "The recovered video checkpoint was attached to the wrong stage.",
                code="invalid_provenance",
            )
        run = self._pipeline_run(run_id, pipeline_key)
        lineage_audit = self._validate_pipeline_child_lineage(
            run, stage, body, pipeline_key, lineage
        )
        methods = {
            "video_generation": self.execute_local_video_generation,
            "narration": self.execute_local_narration,
            "timeline": self.execute_local_timeline,
            "assembly": self.execute_local_assembly,
            "qc": self.execute_local_qc,
        }
        method = methods.get(stage)
        if method is None:
            raise RequestValidationError(
                "The local pipeline stage is not supported.",
                code="local_profile_stage_not_allowed",
            )
        internal_kwargs: dict[str, Any] = {
            "_pipeline_capability": self._pipeline_capability,
            "_pipeline_key": pipeline_key,
            "_pipeline_lineage": lineage_audit,
        }
        if video_recovery_checkpoint is not None:
            internal_kwargs["_pipeline_video_recovery_checkpoint"] = dict(
                video_recovery_checkpoint
            )
        return method(run_id, body, **internal_kwargs)

    def _protect_local_pipeline_continuation_payload(
        self, payload: dict[str, Any], pipeline_key: str
    ) -> tuple[str, bytes | None]:
        """Protect the complete normalized request without a plaintext fallback."""

        plaintext = canonical_json(
            {
                "version": 1,
                "pipeline_key": pipeline_key,
                "payload": payload,
            }
        ).encode("utf-8")
        if not dpapi_available():
            return "none", None
        try:
            return (
                "dpapi-v1",
                protect_private_data(
                    plaintext,
                    description="MiniMaxH3 Studio local pipeline continuation",
                ),
            )
        except (OSError, ValueError, SecretStorageUnavailable):
            return "none", None
        finally:
            plaintext = b""

    def _read_local_pipeline_continuation_payload(
        self, material: dict[str, Any]
    ) -> dict[str, Any]:
        """Decrypt and bind one private continuation request to its claim."""

        ciphertext = material.get("request_ciphertext")
        if material.get("request_protection") != "dpapi-v1" or not isinstance(
            ciphertext, bytes
        ):
            raise RequestValidationError(
                "The pipeline continuation has no protected request.",
                code="pipeline_resume_payload_unavailable",
            )
        try:
            plaintext = unprotect_private_data(ciphertext)
            raw = json.loads(plaintext.decode("utf-8"))
            if (
                not isinstance(raw, dict)
                or raw.get("version") != 1
                or set(raw) != {"version", "pipeline_key", "payload"}
                or not isinstance(raw.get("payload"), dict)
            ):
                raise ValueError("payload")
            payload = validate_local_pipeline_payload(raw["payload"])
            pipeline_key = local_pipeline_key(payload)
        except (
            OSError,
            ValueError,
            UnicodeError,
            json.JSONDecodeError,
            LocalPipelineValidationError,
            SecretStorageUnavailable,
        ) as exc:
            raise RequestValidationError(
                "The protected pipeline continuation could not be verified.",
                code="pipeline_resume_payload_invalid",
            ) from exc
        finally:
            if "plaintext" in locals():
                plaintext = b""
        if (
            raw.get("pipeline_key") != pipeline_key
            or material.get("pipeline_key") != pipeline_key
        ):
            raise RequestValidationError(
                "The protected pipeline continuation does not match its run.",
                code="pipeline_resume_payload_invalid",
            )
        return payload

    @staticmethod
    def _local_pipeline_job_response(
        job: dict[str, Any],
        *,
        run_id: str,
        revision_id: str,
        pipeline_key: str,
        created: bool,
    ) -> dict[str, Any]:
        return {
            **job,
            "run_id": run_id,
            "revision_id": revision_id,
            "pipeline_key": pipeline_key,
            "deduplicated": not created,
        }

    def _submit_local_pipeline_top(
        self,
        *,
        production_id: str,
        revision: dict[str, Any],
        run: dict[str, Any],
        payload: dict[str, Any],
        pipeline_key: str,
        audit: dict[str, Any],
        reuse_succeeded: bool,
        continuation_material: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Enqueue one normal top, optionally fenced to an exact video cache."""

        checkpoint: dict[str, str] | None = None
        continuation_kwargs: dict[str, Any] = {}
        if continuation_material is not None:
            source_job_id = continuation_material.get("source_job_id")
            source_attempt_id = continuation_material.get(
                "source_stage_attempt_id"
            )
            updated_at = continuation_material.get("updated_at")
            if (
                continuation_material.get("state") != "ready"
                or not isinstance(updated_at, str)
                or (source_job_id is None) != (source_attempt_id is None)
                or (
                    source_job_id is not None
                    and not isinstance(source_job_id, str)
                )
                or (
                    source_attempt_id is not None
                    and not isinstance(source_attempt_id, str)
                )
            ):
                raise RequestValidationError(
                    "The pipeline continuation checkpoint is invalid.",
                    code="invalid_provenance",
                )
            if isinstance(source_job_id, str) and isinstance(
                source_attempt_id, str
            ):
                checkpoint = {
                    "job_id": source_job_id,
                    "stage_attempt_id": source_attempt_id,
                }
            continuation_kwargs = {
                "expected_continuation_state": "ready",
                "expected_continuation_updated_at": updated_at,
                "expected_source_job_id": source_job_id,
                "expected_source_stage_attempt_id": source_attempt_id,
            }

        job_payload = {
            "production_id": production_id,
            "run_id": run["id"],
            "revision_id": revision["id"],
            "stage": "pipeline",
            **audit,
        }

        def execute(
            _job_id: str, cancel_event: JobExecutionContext
        ) -> dict[str, Any]:
            result = run_local_pipeline(
                self,
                production_id=production_id,
                run_id=run["id"],
                revision_id=revision["id"],
                payload=payload,
                expected_pipeline_key=pipeline_key,
                cancel_event=cancel_event,
                video_recovery_checkpoint=checkpoint,
            )
            cancel_event.raise_if_cancelled()
            return self._validated_local_pipeline_result(
                result,
                run=run,
                revision=revision,
                pipeline_key=pipeline_key,
                payload=payload,
            )

        job, created = self.jobs.submit_local_pipeline_once(
            production_id=production_id,
            run_id=run["id"],
            pipeline_key=pipeline_key,
            payload=job_payload,
            callback=execute,
            reuse_succeeded=reuse_succeeded,
            **continuation_kwargs,
        )
        return self._local_pipeline_job_response(
            job,
            run_id=run["id"],
            revision_id=revision["id"],
            pipeline_key=pipeline_key,
            created=created,
        )

    def _resume_local_pipeline_continuation(
        self, observed_material: dict[str, Any]
    ) -> dict[str, Any] | None:
        """CAS one ready checkpoint into a new top job; never wait for it."""

        production_id = observed_material.get("production_id")
        pipeline_key = observed_material.get("pipeline_key")
        try:
            validate_identifier(production_id, label="production id")
        except (SecurityError, TypeError, ValueError):
            raise RequestValidationError(
                "The pipeline continuation claim is invalid.",
                code="invalid_provenance",
            ) from None
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise RequestValidationError(
                "The pipeline continuation key is invalid.",
                code="invalid_provenance",
            )
        with self._pipeline_submit_lock:
            if self._pipeline_continuation_stop.is_set():
                return None
            material = self.database.get_local_pipeline_continuation_material(
                production_id, pipeline_key
            )
            if (
                not isinstance(material, dict)
                or material.get("state") != "ready"
                or material.get("updated_at") != observed_material.get("updated_at")
            ):
                return None
            payload = self._read_local_pipeline_continuation_payload(material)
            run_id = material.get("run_id")
            revision_id = material.get("revision_id")
            try:
                validate_identifier(run_id, label="run id")
                validate_identifier(revision_id, label="revision id")
            except (SecurityError, TypeError, ValueError):
                raise RequestValidationError(
                    "The pipeline continuation provenance is invalid.",
                    code="invalid_provenance",
                ) from None
            run = self.database.get_run(run_id)
            if (
                not isinstance(run, dict)
                or run.get("production_id") != production_id
                or run.get("revision_id") != revision_id
                or run.get("execution_profile") != LOCAL_PIPELINE_PROFILE
                or run.get("pipeline_key") != pipeline_key
                or set(run.get("requested_stages", []))
                != _LOCAL_PIPELINE_ZERO_COST_STAGES
                or run.get("estimated_cost", {}).get("amount") != "0.00"
            ):
                raise RequestValidationError(
                    "The pipeline continuation run is invalid.",
                    code="invalid_provenance",
                )
            revision = {"id": revision_id}
            audit = local_pipeline_audit_payload(
                payload, pipeline_key=pipeline_key
            )
            return self._submit_local_pipeline_top(
                production_id=production_id,
                revision=revision,
                run=run,
                payload=payload,
                pipeline_key=pipeline_key,
                audit=audit,
                reuse_succeeded=False,
                continuation_material=material,
            )

    def execute_local_pipeline(
        self, production_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or resume one immutable, zero-cost local production run."""

        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        try:
            payload = validate_local_pipeline_payload(body)
            pipeline_key = local_pipeline_key(payload)
            audit = local_pipeline_audit_payload(payload, pipeline_key=pipeline_key)
        except LocalPipelineValidationError as exc:
            raise RequestValidationError(
                "The local pipeline request is invalid.", code=exc.code
            ) from exc

        changes = [{"type": "script"}, {"type": "video"}]
        plan = build_rerun_plan(production_id, changes)
        if (
            set(plan.get("affected_stages", [])) != _LOCAL_PIPELINE_ZERO_COST_STAGES
            or len(plan.get("affected_stages", []))
            != len(_LOCAL_PIPELINE_ZERO_COST_STAGES)
        ):
            raise RequestValidationError(
                "The local pipeline plan is invalid.",
                code="local_profile_stage_not_allowed",
            )
        request_protection, request_ciphertext = (
            self._protect_local_pipeline_continuation_payload(payload, pipeline_key)
        )
        with self._pipeline_submit_lock:
            revision, run = self.database.create_revision_and_run(
                production_id,
                changes,
                plan,
                0,
                "USD",
                execution_profile=LOCAL_PIPELINE_PROFILE,
                pipeline_key=pipeline_key,
                pipeline_request_protection=request_protection,
                pipeline_request_ciphertext=request_ciphertext,
            )
            latest = self.database.find_latest_job_for_run(
                LOCAL_PIPELINE_JOB_KIND, production_id, run["id"]
            )
            reusable_success = bool(
                isinstance(latest, dict)
                and latest.get("status") == "succeeded"
                and self._reusable_succeeded_pipeline_job(
                    latest, run, revision, pipeline_key, payload
                )
            )
            continuation = run.get("pipeline_continuation")
            continuation_state = (
                continuation.get("state")
                if isinstance(continuation, dict)
                else None
            )
            if continuation_state in {"waiting_provider", "cancel_requested"}:
                if not isinstance(latest, dict):
                    raise RequestValidationError(
                        "The pipeline continuation owner is unavailable.",
                        code="local_pipeline_unavailable",
                    )
                return self._local_pipeline_job_response(
                    latest,
                    run_id=run["id"],
                    revision_id=revision["id"],
                    pipeline_key=pipeline_key,
                    created=False,
                )

            continuation_material = None
            if continuation_state == "ready":
                continuation_material = (
                    self.database.get_local_pipeline_continuation_material(
                        production_id, pipeline_key
                    )
                )
            elif (
                isinstance(latest, dict)
                and latest.get("status") not in {"queued", "running"}
                and not reusable_success
            ):
                # An explicit user resubmission may re-arm a failed, blocked,
                # cancelled, or unavailable request. A ready checkpoint is
                # never rewound; it is consumed through the cache-only fence.
                revision, run = self.database.create_revision_and_run(
                    production_id,
                    changes,
                    plan,
                    0,
                    "USD",
                    execution_profile=LOCAL_PIPELINE_PROFILE,
                    pipeline_key=pipeline_key,
                    pipeline_request_protection=request_protection,
                    pipeline_request_ciphertext=request_ciphertext,
                    rearm_pipeline_continuation=True,
                )

            return self._submit_local_pipeline_top(
                production_id=production_id,
                revision=revision,
                run=run,
                payload=payload,
                pipeline_key=pipeline_key,
                audit=audit,
                reuse_succeeded=reusable_success,
                continuation_material=continuation_material,
            )

    def execute_detailed_test_video(
        self,
        production_id: str,
        body: dict[str, Any],
        *,
        _announcement_recipe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Queue one deduplicated SAPI -> Remotion -> assembly -> QC top job."""

        validate_identifier(production_id, label="production id")
        if self.database.get_production(production_id) is None:
            raise KeyError("production not found")
        try:
            payload = validate_detailed_test_video_payload(body)
            announcement_segment_start_ms: tuple[int, ...] | None = None
            if _announcement_recipe is not None:
                if not isinstance(_announcement_recipe, dict):
                    raise DetailedTestVideoValidationError(
                        "announcement recipe provenance is invalid"
                    )
                raw_recipe = _announcement_recipe.get("recipe")
                try:
                    announcement_recipe = validate_announcement_recipe_payload(
                        raw_recipe
                    )
                except AnnouncementVideoValidationError as exc:
                    raise DetailedTestVideoValidationError(
                        "announcement recipe provenance is invalid"
                    ) from exc
                if announcement_recipe_to_detailed_payload(
                    announcement_recipe
                ) != payload:
                    raise DetailedTestVideoValidationError(
                        "announcement recipe provenance is invalid"
                    )
                announcement_segment_start_ms = (
                    announcement_narration_segment_starts(announcement_recipe)
                )
            timeline_payload = {
                "schema_version": payload["schema_version"],
                "clips": payload["clips"],
            }
            source_inputs = self._validated_remotion_timeline_inputs(
                {"production_id": production_id}, timeline_payload
            )
            try:
                from . import remotion_timeline as remotion_worker
            except (ImportError, AttributeError) as exc:
                raise DetailedTestVideoError(
                    "The local Remotion worker is not installed.",
                    code="remotion_unavailable",
                ) from exc
            tool_identity = _call_local_worker(
                remotion_worker.resolve_remotion_tool_identity, self.workspace
            )
            remotion_cache_key = remotion_timeline_cache_key(
                source_inputs["cache_clips"], tool_identity=tool_identity
            )
            request_key = detailed_test_video_key(
                payload,
                source_clips=source_inputs["cache_clips"],
                remotion_cache_key=remotion_cache_key,
                narration_segment_start_ms=announcement_segment_start_ms,
            )
            audit = detailed_test_video_audit_payload(
                payload,
                request_key=request_key,
                source_clips=source_inputs["cache_clips"],
                remotion_cache_key=remotion_cache_key,
                narration_segment_start_ms=announcement_segment_start_ms,
            )
        except DetailedTestVideoValidationError as exc:
            raise RequestValidationError(
                "The detailed test video request is invalid.", code=exc.code
            ) from exc
        except RemotionTimelineValidationError as exc:
            raise RequestValidationError(
                "The detailed test video request is invalid.", code=exc.error_code
            ) from exc
        except DetailedTestVideoError as exc:
            raise RequestValidationError(
                exc.public_message, code=exc.error_code
            ) from exc
        except RemotionTimelineError as exc:
            raise RequestValidationError(
                exc.public_message, code=exc.error_code
            ) from exc

        changes = [{"type": "script"}, {"type": "timeline"}]
        plan = build_rerun_plan(production_id, changes)
        if (
            set(plan.get("affected_stages", [])) != _LOCAL_SAPI_ZERO_COST_STAGES
            or len(plan.get("affected_stages", []))
            != len(_LOCAL_SAPI_ZERO_COST_STAGES)
        ):
            raise RequestValidationError(
                "The detailed test video plan is invalid.",
                code="local_profile_stage_not_allowed",
            )

        with self._detailed_test_video_submit_lock:
            revision, run = self.database.create_revision_and_run(
                production_id,
                changes,
                plan,
                0,
                "USD",
                execution_profile=DETAILED_TEST_VIDEO_PROFILE,
                detailed_test_video_key=request_key,
            )
            job_payload = {
                "production_id": production_id,
                "run_id": run["id"],
                "revision_id": revision["id"],
                "stage": "detailed_test_video",
                **audit,
            }
            previous_top = self.database.find_latest_job_for_run(
                DETAILED_TEST_VIDEO_JOB_KIND,
                production_id,
                run["id"],
            )
            reusable_success = bool(
                isinstance(previous_top, dict)
                and self._reusable_succeeded_detailed_test_video_job(
                    previous_top,
                    run,
                    revision,
                    request_key,
                    payload,
                    job_payload,
                    announcement_segment_start_ms,
                )
            )

            def execute(
                _job_id: str, cancel_event: JobExecutionContext
            ) -> dict[str, Any]:
                cancel_event.raise_if_cancelled()
                try:
                    current_inputs = self._validated_remotion_timeline_inputs(
                        run, timeline_payload
                    )
                    current_tool_identity = _call_local_worker(
                        remotion_worker.resolve_remotion_tool_identity,
                        self.workspace,
                    )
                    current_remotion_key = remotion_timeline_cache_key(
                        current_inputs["cache_clips"],
                        tool_identity=current_tool_identity,
                    )
                except (RequestValidationError, RemotionTimelineValidationError) as exc:
                    raise DetailedTestVideoError(
                        "A detailed test video input changed before execution.",
                        code="input_changed",
                    ) from exc
                except RemotionTimelineError as exc:
                    raise DetailedTestVideoError(
                        "The Remotion tool changed before detailed test video execution.",
                        code="tool_changed",
                    ) from exc
                if current_remotion_key != remotion_cache_key:
                    raise DetailedTestVideoError(
                        "A detailed test video input or tool changed before execution.",
                        code="input_changed",
                    )
                current_request_key = detailed_test_video_key(
                    payload,
                    source_clips=current_inputs["cache_clips"],
                    remotion_cache_key=current_remotion_key,
                    narration_segment_start_ms=announcement_segment_start_ms,
                )
                if current_request_key != request_key:
                    raise DetailedTestVideoError(
                        "The detailed test video request changed before execution.",
                        code="cache_key_mismatch",
                    )
                raw = run_detailed_test_video(
                    self,
                    production_id=production_id,
                    run_id=run["id"],
                    revision_id=revision["id"],
                    payload=payload,
                    source_clips=current_inputs["cache_clips"],
                    expected_remotion_cache_key=current_remotion_key,
                    expected_request_key=request_key,
                    expected_duration_ms=current_inputs["compiled"]["duration_ms"],
                    cancel_event=cancel_event,
                    narration_segment_start_ms=announcement_segment_start_ms,
                )
                cancel_event.raise_if_cancelled()
                return detailed_test_video_public_result(
                    raw,
                    production_id=production_id,
                    run_id=run["id"],
                    revision_id=revision["id"],
                    request_key=request_key,
                    payload=payload,
                    narration_segment_start_ms=announcement_segment_start_ms,
                )

            job, created = self.jobs.submit_detailed_test_video_once(
                production_id=production_id,
                run_id=run["id"],
                request_key=request_key,
                payload=job_payload,
                callback=execute,
                reuse_succeeded=reusable_success,
                announcement_recipe=_announcement_recipe,
            )
            return {
                **job,
                "run_id": run["id"],
                "revision_id": revision["id"],
                "request_key": request_key,
                "deduplicated": not created,
            }

    def _protect_comfyui_resume_payload(
        self, payload: dict[str, Any]
    ) -> tuple[str, bytes | None]:
        """Return current-user ciphertext without persisting prompt plaintext."""

        normalized = comfyui_resume_payload(payload)
        plaintext = canonical_json(normalized).encode("utf-8")
        if not dpapi_available():
            return "none", None
        try:
            return (
                "dpapi-v1",
                protect_private_data(
                    plaintext,
                    description="MiniMaxH3 Studio ComfyUI restart payload",
                ),
            )
        except (OSError, ValueError, SecretStorageUnavailable):
            # Generation remains available on a platform/account where DPAPI
            # cannot protect this payload, but automatic restart recovery is
            # explicitly unavailable and never falls back to plaintext.
            return "none", None

    def _read_comfyui_resume_payload(
        self, provider_task_record_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        material = self.database.get_provider_task_recovery_material(
            provider_task_record_id
        )
        if material is None:
            raise KeyError("provider task not found")
        ciphertext = material.get("request_ciphertext")
        if material.get("request_protection") != "dpapi-v1" or not isinstance(
            ciphertext, bytes
        ):
            raise RequestValidationError(
                "This provider task has no protected restart payload.",
                code="resume_payload_unavailable",
            )
        try:
            plaintext = unprotect_private_data(ciphertext)
            raw = json.loads(plaintext.decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("payload")
            payload = comfyui_resume_payload(raw)
        except (
            OSError,
            ValueError,
            UnicodeError,
            json.JSONDecodeError,
            SecretStorageUnavailable,
        ) as exc:
            raise RequestValidationError(
                "The protected provider restart payload could not be verified.",
                code="resume_payload_invalid",
            ) from exc
        finally:
            if "plaintext" in locals():
                plaintext = b""
        if comfyui_payload_digest(payload) != material.get("payload_digest"):
            raise RequestValidationError(
                "The protected provider restart payload does not match its task.",
                code="resume_payload_invalid",
            )
        return payload, material

    def _reconcile_cancel_requested_provider_task(
        self,
        provider_task_record_id: str,
        *,
        observation_timeout_seconds: float,
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Reconcile one cancelled provider UUID without a generation POST."""

        _raise_if_cancelled(cancel_event)
        current_public = self.database.get_provider_task(provider_task_record_id)
        if current_public is None:
            raise KeyError("provider task not found")
        if current_public.get("status") == "failed" and (
            current_public.get("error") or {}
        ).get("code") == "provider_cancelled":
            return {
                "provider_task_record_id": provider_task_record_id,
                "provider_task_id": current_public.get("provider_task_id"),
                "state": "cancelled",
                "provider_status": "terminal",
                "duplicate_submission_blocked": False,
                "reconciliation_pending": False,
            }
        if current_public.get("status") != "cancel_requested":
            raise RequestValidationError(
                "This provider task is not awaiting cancellation reconciliation.",
                code="provider_task_manual_review_required",
            )

        payload, current = self._read_comfyui_resume_payload(
            provider_task_record_id
        )
        _raise_if_cancelled(cancel_event)
        run_id = str(current.get("run_id") or "")
        run = self.database.get_run(run_id)
        if (
            run is None
            or run.get("production_id") != current.get("production_id")
            or run.get("execution_profile")
            not in {"local_comfyui", LOCAL_PIPELINE_PROFILE}
            or _LOCAL_VIDEO_GENERATION_STAGE
            not in run.get("requested_stages", [])
            or comfyui_payload_digest(payload) != current.get("payload_digest")
        ):
            raise RequestValidationError(
                "The provider cancellation provenance is invalid.",
                code="provider_task_provenance_invalid",
            )
        provider_task_id = current.get("provider_task_id")
        if not isinstance(provider_task_id, str):
            raise RequestValidationError(
                "The provider task has no pre-issued prompt ID.",
                code="provider_task_provenance_invalid",
            )

        from . import comfyui

        try:
            marker_prompt_id = comfyui.recover_comfyui_prompt_id(
                self.workspace,
                production_id=run["production_id"],
                run_id=run_id,
                cache_key=current["cache_key"],
                payload_digest=current["payload_digest"],
            )
        except (ComfyUIError, ComfyUIValidationError, OSError) as exc:
            error_code, error_message = safe_comfyui_error(exc)
            raise ComfyUIError(error_message, code=error_code) from exc
        if marker_prompt_id is not None and marker_prompt_id != provider_task_id:
            raise ComfyUIError(
                "The durable provider task identity changed.",
                code="comfyui_submission_unknown",
            )

        # With neither an accepted-submission timestamp nor the marker that is
        # durably written before POST, this UUID was never exposed to ComfyUI.
        # It can be terminalized locally without any network request.
        if marker_prompt_id is None and current.get("submitted_at") is None:
            terminal = self.database.mark_provider_task_state(
                provider_task_record_id,
                "failed",
                error_code="provider_cancelled",
                error_message="The provider task was cancelled before submission.",
            )
            return {
                "provider_task_record_id": provider_task_record_id,
                "provider_task_id": provider_task_id,
                "state": "cancelled",
                "provider_status": "not_submitted",
                "duplicate_submission_blocked": False,
                "reconciliation_pending": False,
                "completed_at": terminal.get("completed_at"),
            }

        _raise_if_cancelled(cancel_event)
        try:
            observation = comfyui.observe_comfyui_submission(
                self.workspace,
                provider_task_id=provider_task_id,
                request_timeout_seconds=observation_timeout_seconds,
            )
        except (ComfyUIError, ComfyUIValidationError, OSError) as exc:
            _raise_if_cancelled(cancel_event)
            error_code, error_message = safe_comfyui_error(exc)
            raise ComfyUIError(error_message, code=error_code) from exc
        current = self.database.record_provider_observation(
            provider_task_record_id
        )
        _raise_if_cancelled(cancel_event)
        provider_state = observation.get("state")
        provider_status = observation.get("provider_status")
        if provider_state == "provider_running":
            cancel_accepted = False
            try:
                cancel_accepted = comfyui.request_comfyui_provider_cancel(
                    self.workspace,
                    provider_task_id=provider_task_id,
                    request_timeout_seconds=observation_timeout_seconds,
                )
            except (ComfyUIError, ComfyUIValidationError, OSError):
                # Cancellation is advisory.  Preserve cancel_requested and
                # retry the exact GET/cancel pair later; never submit prompt.
                cancel_accepted = False
            _raise_if_cancelled(cancel_event)
            return {
                "provider_task_record_id": provider_task_record_id,
                "provider_task_id": provider_task_id,
                "state": "cancel_requested",
                "provider_status": provider_status,
                "cancel_request_accepted": bool(cancel_accepted),
                "duplicate_submission_blocked": True,
                "reconciliation_pending": True,
                "last_observed_at": current.get("last_observed_at"),
            }
        if provider_state == "ambiguous":
            # A 404 can mean that a restarted ComfyUI lost volatile history.
            # Retain the durable cancellation fence and exact UUID for manual
            # review instead of assuming it is safe to submit again.
            return {
                "provider_task_record_id": provider_task_record_id,
                "provider_task_id": provider_task_id,
                "state": "cancel_requested",
                "provider_status": provider_status,
                "cancel_request_accepted": False,
                "duplicate_submission_blocked": True,
                "reconciliation_pending": True,
                "last_observed_at": current.get("last_observed_at"),
            }
        if provider_state not in {"failed", "complete_recoverable"}:
            raise ComfyUIError(
                "The ComfyUI cancellation state is unknown.",
                code="comfyui_submission_unknown",
            )

        terminal = self.database.mark_provider_task_state(
            provider_task_record_id,
            "failed",
            error_code="provider_cancelled",
            error_message="The provider task cancellation is terminal.",
        )
        marker_removed = marker_prompt_id is None
        if marker_prompt_id is not None:
            try:
                marker_removed = comfyui.cleanup_comfyui_submission_marker(
                    self.workspace,
                    production_id=run["production_id"],
                    run_id=run_id,
                    cache_key=current["cache_key"],
                    payload_digest=current["payload_digest"],
                    provider_task_id=provider_task_id,
                )
            except (ComfyUIError, ComfyUIValidationError, OSError):
                marker_removed = False
        return {
            "provider_task_record_id": provider_task_record_id,
            "provider_task_id": provider_task_id,
            "state": "cancelled",
            "provider_status": provider_status,
            "duplicate_submission_blocked": False,
            "reconciliation_pending": False,
            "marker_cleanup_pending": not marker_removed,
            "completed_at": terminal.get("completed_at"),
        }

    def _queue_provider_cancellation_reconciliation(
        self,
        provider_task: dict[str, Any],
        *,
        observation_timeout_seconds: float,
    ) -> dict[str, Any]:
        """Admit at most one local GET/cancel reconciliation per task."""

        record_id = str(provider_task.get("id") or "")
        with self._provider_cancellation_lock:
            existing_job_id = self._provider_cancellation_jobs.get(record_id)
            if existing_job_id is not None:
                existing = self.database.get_job(existing_job_id)
                if (
                    existing is not None
                    and existing.get("status") in {"queued", "running"}
                    and self.jobs.is_admitted(existing_job_id)
                ):
                    existing["provider_task_record_id"] = record_id
                    existing["deduplicated"] = True
                    return existing
                self._provider_cancellation_jobs.pop(record_id, None)

            job = self.jobs.submit(
                "provider_cancellation_reconciliation",
                {
                    "provider_task_record_id": record_id,
                    "provider_task_id": provider_task.get("provider_task_id"),
                    "production_id": provider_task.get("production_id"),
                    "run_id": provider_task.get("run_id"),
                    "provider": "comfyui",
                    "operation": "get_and_cancel_only",
                },
                lambda _job_id, cancel_event: (
                    self._reconcile_cancel_requested_provider_task(
                        record_id,
                        observation_timeout_seconds=observation_timeout_seconds,
                        cancel_event=cancel_event,
                    )
                ),
                production_id=provider_task.get("production_id"),
                lane="default",
            )
            self._provider_cancellation_jobs[record_id] = job["id"]
        job["provider_task_record_id"] = record_id
        job["provider_cancellation_reconciliation"] = True
        return job

    def _queue_comfyui_provider_recovery(
        self,
        provider_task: dict[str, Any],
        *,
        observation_timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Append one new job/attempt that owns an existing provider task."""

        _raise_if_cancelled(self._provider_recovery_stop)
        record_id = str(provider_task.get("id") or "")
        payload, current = self._read_comfyui_resume_payload(record_id)
        _raise_if_cancelled(self._provider_recovery_stop)
        run_id = str(current.get("run_id") or "")
        run = self.database.get_run(run_id)
        if (
            run is None
            or run.get("production_id") != current.get("production_id")
            or run.get("execution_profile")
            not in {"local_comfyui", LOCAL_PIPELINE_PROFILE}
            or _LOCAL_VIDEO_GENERATION_STAGE not in run.get("requested_stages", [])
        ):
            raise RequestValidationError(
                "The provider task is no longer bound to a recoverable run.",
                code="provider_task_provenance_invalid",
            )
        if current.get("status") == "cancel_requested":
            return self._queue_provider_cancellation_reconciliation(
                current,
                observation_timeout_seconds=observation_timeout_seconds,
            )
        inputs = self._resolve_comfyui_execution_inputs(
            payload, self._provider_recovery_stop
        )
        _raise_if_cancelled(self._provider_recovery_stop)
        if (
            inputs.get("cache_key") != current.get("cache_key")
            or comfyui_payload_digest(payload) != current.get("payload_digest")
        ):
            raise RequestValidationError(
                "The provider task inputs changed after submission.",
                code="cache_key_mismatch",
            )

        from . import comfyui

        provider_task_id = current.get("provider_task_id")
        if not isinstance(provider_task_id, str):
            raise RequestValidationError(
                "The provider task has no pre-issued prompt ID.",
                code="provider_task_provenance_invalid",
            )
        try:
            # A process can die after the adapter atomically published and
            # verified all cache files but before Studio committed its DB
            # success.  That success path intentionally removes the marker.
            # Revalidate this exact cache before requiring a live provider;
            # the recovery worker repeats the validation and atomically binds
            # the artifacts to this provider/job/attempt.  A missing or
            # damaged cache still follows the exact-ID observation path and
            # can never trigger a blind POST.
            cache_recovery_available = False
            cache_relative = (
                Path("outputs")
                / "studio"
                / "runs"
                / run_id
                / "video_generation"
                / inputs["cache_key"]
            )
            cache_candidate = workspace_path(self.workspace, cache_relative)
            if cache_candidate.exists() or cache_candidate.is_symlink():
                try:
                    cached = comfyui.validate_comfyui_outputs(
                        self.workspace,
                        production_id=run["production_id"],
                        run_id=run_id,
                        payload=payload,
                        workflow=inputs["workflow"],
                        workflow_source_path=inputs["workflow_source_path"],
                        workflow_source_bytes=inputs["workflow_source_bytes"],
                        workflow_source_sha256=inputs["workflow_source_sha256"],
                        model_files=inputs["model_files"],
                        cancel_event=self._provider_recovery_stop,
                    )
                except ComfyUIError as cache_error:
                    if getattr(cache_error, "error_code", None) != "cache_integrity_failed":
                        raise
                else:
                    expected_prompt_sha256 = hashlib.sha256(
                        payload["prompt"].encode("utf-8")
                    ).hexdigest().upper()
                    if (
                        not isinstance(cached, dict)
                        or cached.get("provider_task_id") != provider_task_id
                        or cached.get("cache_key") != inputs["cache_key"]
                        or cached.get("workflow_preset") != payload["workflow_preset"]
                        or cached.get("seed") != payload["seed"]
                        or cached.get("prompt_sha256") != expected_prompt_sha256
                    ):
                        raise ComfyUIError(
                            "The published cache does not match its provider task.",
                            code="cache_integrity_failed",
                        )
                    cache_recovery_available = True
            marker_prompt_id = None
            if not cache_recovery_available:
                marker_prompt_id = comfyui.recover_comfyui_prompt_id(
                    self.workspace,
                    production_id=run["production_id"],
                    run_id=run_id,
                    cache_key=inputs["cache_key"],
                    payload_digest=current["payload_digest"],
                )
            if marker_prompt_id is not None:
                if marker_prompt_id != provider_task_id:
                    raise ComfyUIError(
                        "The durable provider task identity changed.",
                        code="comfyui_submission_unknown",
                    )
                current = self.database.record_provider_submission(
                    record_id, marker_prompt_id
                )
                terminal_marker_state = comfyui.recover_comfyui_terminal_state(
                    self.workspace,
                    production_id=run["production_id"],
                    run_id=run_id,
                    cache_key=inputs["cache_key"],
                    payload_digest=current["payload_digest"],
                    provider_task_id=provider_task_id,
                )
                if terminal_marker_state == "failed":
                    self.database.mark_provider_task_state(
                        record_id,
                        "failed",
                        error_code="comfyui_generation_failed",
                        error_message="ComfyUI reports a terminal provider failure.",
                    )
                    comfyui.cleanup_comfyui_submission_marker(
                        self.workspace,
                        production_id=run["production_id"],
                        run_id=run_id,
                        cache_key=inputs["cache_key"],
                        payload_digest=current["payload_digest"],
                        provider_task_id=provider_task_id,
                    )
                    raise RequestValidationError(
                        "ComfyUI reports a terminal provider failure.",
                        code="comfyui_generation_failed",
                    )
            if (
                not cache_recovery_available
                and
                current.get("status") == "ambiguous"
                and marker_prompt_id is None
                and current.get("submitted_at") is None
            ):
                raise RequestValidationError(
                    "The ambiguous ComfyUI task has no exact durable submission evidence.",
                    code="comfyui_submission_unknown",
                )
            should_observe = marker_prompt_id is not None or (
                not cache_recovery_available
                and
                current.get("submitted_at") is not None
                and current.get("status")
                in {"submitted", "ambiguous", "recovery_blocked"}
            )
            if should_observe:
                observation = comfyui.observe_comfyui_submission(
                    self.workspace,
                    provider_task_id=provider_task_id,
                    request_timeout_seconds=observation_timeout_seconds,
                )
                current = self.database.record_provider_observation(record_id)
                _raise_if_cancelled(self._provider_recovery_stop)
                if observation.get("state") == "ambiguous":
                    self.database.mark_provider_task_state(
                        record_id,
                        "ambiguous",
                        error_code="comfyui_submission_unknown",
                        error_message=(
                            "The pre-issued ComfyUI task is not visible in the current runtime."
                        ),
                    )
                    raise RequestValidationError(
                        "The ComfyUI task requires manual review; no new prompt was submitted.",
                        code="comfyui_submission_unknown",
                    )
                if observation.get("state") == "failed":
                    self.database.mark_provider_task_state(
                        record_id,
                        "failed",
                        error_code="comfyui_generation_failed",
                        error_message="ComfyUI reports a terminal provider failure.",
                    )
                    if marker_prompt_id is not None:
                        comfyui.cleanup_comfyui_submission_marker(
                            self.workspace,
                            production_id=run["production_id"],
                            run_id=run_id,
                            cache_key=inputs["cache_key"],
                            payload_digest=current["payload_digest"],
                            provider_task_id=provider_task_id,
                        )
                    raise RequestValidationError(
                        "ComfyUI reports a terminal provider failure.",
                        code="comfyui_generation_failed",
                    )
                if marker_prompt_id is None:
                    comfyui.restore_comfyui_submission_marker(
                        self.workspace,
                        production_id=run["production_id"],
                        run_id=run_id,
                        cache_key=inputs["cache_key"],
                        payload_digest=current["payload_digest"],
                        provider_task_id=provider_task_id,
                    )
        except RequestValidationError:
            raise
        except (ComfyUIError, ComfyUIValidationError, OSError) as exc:
            error_code, error_message = safe_comfyui_error(exc)
            status = (
                "ambiguous"
                if error_code == "comfyui_submission_unknown"
                else "recovery_blocked"
            )
            latest = self.database.get_provider_task(record_id)
            if latest is not None and latest.get("status") not in {"succeeded", "failed"}:
                self.database.mark_provider_task_state(
                    record_id,
                    status,
                    error_code=error_code,
                    error_message=error_message,
                )
            raise RequestValidationError(error_message, code=error_code) from exc

        audit = comfyui_audit_payload(
            payload,
            workflow=inputs["workflow_record"],
            models=inputs["model_files"],
            runtime_identity=inputs["runtime_identity"],
            cache_key=inputs["cache_key"],
        )
        _raise_if_cancelled(self._provider_recovery_stop)
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_VIDEO_GENERATION_STAGE,
            inputs["cache_key"],
            {
                "execution_profile": run["execution_profile"],
                "cache_key": inputs["cache_key"],
                "provider_task_record_id": record_id,
                "restart_recovery": True,
                **audit,
            },
        )
        expected_updated_at = str(current["updated_at"])

        def bind_recovery(created_job: dict[str, Any]) -> None:
            self.database.link_stage_attempt_job(attempt["id"], created_job["id"])
            claimed = self.database.claim_provider_task_recovery(
                record_id,
                expected_updated_at=expected_updated_at,
                current_stage_attempt_id=attempt["id"],
                current_job_id=created_job["id"],
            )
            if claimed is None:
                raise RequestValidationError(
                    "Another worker already claimed this provider task.",
                    code="provider_task_already_claimed",
                )

        def abort_recovery(created_job: dict[str, Any]) -> None:
            self.database.abort_provider_task_recovery_admission(
                record_id,
                current_stage_attempt_id=attempt["id"],
                current_job_id=created_job["id"],
                error_code="job_setup_failed",
                error_message="The background job could not be prepared.",
            )

        try:
            _raise_if_cancelled(self._provider_recovery_stop)
            job = self.jobs.submit(
                "local_video_generation",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_VIDEO_GENERATION_STAGE,
                    "execution_profile": run["execution_profile"],
                    "cache_key": inputs["cache_key"],
                    "provider_task_record_id": record_id,
                    "restart_recovery": True,
                    **audit,
                    "stage_attempt_id": attempt["id"],
                },
                lambda _job_id, cancel_event: self._execute_local_video_generation(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    inputs,
                    cancel_event,
                    provider_task_record_id=record_id,
                ),
                production_id=run["production_id"],
                before_enqueue=bind_recovery,
                admission_failure=abort_recovery,
                lane="gpu",
            )
        except Exception as exc:
            # JobManager's admission failure hook atomically closes a linked
            # job/attempt and releases this provider claim.  If the manager
            # was already closed before it created a job, retire only the
            # still-unlinked attempt; the provider was never claimed.
            latest_attempt = self.database.get_stage_attempt(attempt["id"])
            if (
                latest_attempt is not None
                and latest_attempt.get("job_id") is None
                and latest_attempt.get("status") in {"queued", "running"}
            ):
                error_code, error_message = safe_comfyui_error(exc)
                self.database.update_stage_attempt(
                    attempt["id"],
                    "failed",
                    error_code=error_code,
                    error_message=error_message,
                )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["cache_key"] = inputs["cache_key"]
        job["provider_task_record_id"] = record_id
        job["restart_recovery"] = True
        return job

    def _run_startup_provider_recovery(
        self, tasks: list[dict[str, Any]]
    ) -> None:
        try:
            summary = self._recover_comfyui_provider_tasks(tasks)
        except Exception:
            summary = {
                "found": len(tasks),
                "queued": 0,
                "blocked": len(tasks),
                "ambiguous": 0,
            }
        with self._provider_recovery_state_lock:
            self._startup_provider_recovery = {**summary, "running": False}
        self._provider_recovery_done.set()

    def _recover_comfyui_provider_tasks(
        self, tasks: list[dict[str, Any]] | None = None
    ) -> dict[str, int]:
        pending = (
            list(tasks)
            if tasks is not None
            else self.database.list_recoverable_provider_tasks(limit=100)
        )
        summary = {
            "found": len(pending),
            "queued": 0,
            "blocked": 0,
            "ambiguous": 0,
        }
        for task in pending:
            if self._provider_recovery_stop.is_set():
                break
            try:
                self._queue_comfyui_provider_recovery(
                    task, observation_timeout_seconds=1.0
                )
                summary["queued"] += 1
            except Exception:
                if self._provider_recovery_stop.is_set():
                    break
                latest = self.database.get_provider_task(task["id"])
                if latest is not None and latest.get("status") == "ambiguous":
                    summary["ambiguous"] += 1
                else:
                    summary["blocked"] += 1
                    if latest is not None and latest.get("status") not in {
                        "failed",
                        "cancel_requested",
                        "recovery_blocked",
                    }:
                        try:
                            self.database.mark_provider_task_state(
                                task["id"],
                                "recovery_blocked",
                                error_code="provider_recovery_unavailable",
                                error_message=(
                                    "The provider task could not be resumed during Studio startup."
                                ),
                            )
                        except Exception:
                            pass
        return summary

    def resume_provider_task(self, provider_task_record_id: str) -> dict[str, Any]:
        """Manually retry a safe, protected provider-task reconciliation."""

        if not isinstance(provider_task_record_id, str) or re.fullmatch(
            r"provider_task_[0-9a-f]{32}", provider_task_record_id
        ) is None:
            raise RequestValidationError(
                "provider task id is invalid", code="invalid_provider_task_id"
            )
        with self._provider_recovery_lock:
            task = self.database.get_provider_task(provider_task_record_id)
            if task is None:
                raise KeyError("provider task not found")
            current_job_id = task.get("current_job_id")
            if isinstance(current_job_id, str):
                current_job = self.database.get_job(current_job_id)
                if current_job is not None and current_job.get("status") in {
                    "queued",
                    "running",
                }:
                    if self.jobs.is_admitted(current_job_id):
                        current_job["provider_task_record_id"] = provider_task_record_id
                        current_job["deduplicated"] = True
                        return current_job
                    current_attempt_id = task.get("current_stage_attempt_id")
                    if (
                        current_job.get("status") == "queued"
                        and isinstance(current_attempt_id, str)
                    ):
                        self.database.abort_provider_task_recovery_admission(
                            provider_task_record_id,
                            current_stage_attempt_id=current_attempt_id,
                            current_job_id=current_job_id,
                            error_code="job_setup_failed",
                            error_message="The background job could not be prepared.",
                        )
                        task = self.database.get_provider_task(
                            provider_task_record_id
                        )
                        if task is None:
                            raise KeyError("provider task not found")
            if task.get("status") not in {
                "prepared",
                "submitted",
                "ambiguous",
                "recovery_blocked",
                "cancel_requested",
            }:
                raise RequestValidationError(
                    "This provider task cannot be resumed automatically.",
                    code="provider_task_manual_review_required",
                )
            return self._queue_comfyui_provider_recovery(task)

    def _resolve_comfyui_execution_inputs(
        self,
        payload: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Resolve the one tracked graph, four pinned models, and ffprobe.

        The public request never selects paths, endpoints, models, or tools.
        Exact path/size/digest records are derived from repository constants;
        the worker independently revalidates them before touching ComfyUI.
        """

        _raise_if_cancelled(cancel_event)
        try:
            from . import comfyui
        except (ImportError, AttributeError) as exc:
            raise ComfyUIError(
                "The local ComfyUI worker is not installed.",
                code="local_worker_unavailable",
            ) from exc

        workflow_path = workspace_path(
            self.workspace, COMFYUI_WORKFLOW_RELATIVE_PATH, must_exist=True
        )
        if (
            _has_symlink_component(self.workspace, COMFYUI_WORKFLOW_RELATIVE_PATH)
            or workflow_path.is_symlink()
            or not workflow_path.is_file()
        ):
            raise ComfyUIValidationError("workflow source is unsafe")
        try:
            workflow_bytes = workflow_path.read_bytes()
            workflow = json.loads(workflow_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ComfyUIValidationError("workflow source is invalid") from exc
        if not isinstance(workflow, dict):
            raise ComfyUIValidationError("workflow source is invalid")
        workflow_record = normalize_workflow_record(
            {
                "path": COMFYUI_WORKFLOW_RELATIVE_PATH,
                "bytes": len(workflow_bytes),
                "sha256": hashlib.sha256(workflow_bytes).hexdigest().upper(),
                "graph_sha256": hashlib.sha256(
                    canonical_json(workflow).encode("utf-8")
                ).hexdigest().upper(),
            }
        )

        model_files: dict[str, dict[str, Any]] = {}
        for role, spec in COMFYUI_MODEL_SPECS.items():
            relative = str(spec["relative_path"]).replace("\\", "/")
            try:
                path = workspace_path(self.workspace, relative, must_exist=True)
                stat = path.stat()
            except (SecurityError, OSError):
                raise ComfyUIValidationError(
                    f"the pinned ComfyUI model for {role} is unavailable"
                ) from None
            if (
                _has_symlink_component(self.workspace, relative)
                or path.is_symlink()
                or not path.is_file()
                or stat.st_size != spec["bytes"]
            ):
                raise ComfyUIValidationError(
                    f"the pinned ComfyUI model for {role} is invalid"
                )
            model_files[role] = {
                "path": relative,
                "bytes": stat.st_size,
                "sha256": spec["sha256"],
            }
        # Validate the records here but keep the worker input shape path/bytes/
        # sha256 only; normalize_model_records adds the derived model name to
        # its return value, which is audit output rather than request input.
        normalize_model_records(model_files)
        _raise_if_cancelled(cancel_event)
        runtime_identity = comfyui.resolve_comfyui_runtime_identity(
            self.workspace, cancel_event=cancel_event
        )
        ffprobe_identity = comfyui.resolve_comfyui_tool_identity(
            cancel_event=cancel_event
        )
        cache_key = comfyui_cache_key(
            payload,
            workflow=workflow_record,
            models=model_files,
            runtime_identity=runtime_identity,
            ffprobe_identity=ffprobe_identity,
        )
        output_root = workspace_path(self.workspace, "outputs", must_exist=True)
        if output_root.is_symlink() or not output_root.is_dir():
            raise ComfyUIValidationError("ComfyUI output root is unavailable")
        return {
            "workflow": workflow,
            "workflow_source_path": COMFYUI_WORKFLOW_RELATIVE_PATH,
            "workflow_source_bytes": len(workflow_bytes),
            "workflow_source_sha256": workflow_record["sha256"],
            "workflow_record": workflow_record,
            "model_files": model_files,
            "runtime_identity": runtime_identity,
            "ffprobe_identity": ffprobe_identity,
            "cache_key": cache_key,
            "output_roots": ["outputs"],
        }

    def _validate_local_comfyui_artifacts(
        self,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(raw_artifacts, list)
            or len(raw_artifacts) != len(_LOCAL_COMFYUI_ARTIFACTS)
        ):
            raise ComfyUIError(
                "The ComfyUI worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = (
            f"outputs/studio/runs/{run_id}/video_generation/{cache_key}/"
        )
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise ComfyUIError(
                    "The ComfyUI worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise ComfyUIError(
                    "The ComfyUI worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_COMFYUI_ARTIFACTS.get(path.name)
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
                raise ComfyUIError(
                    "The ComfyUI worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            if (
                stat.st_size <= 0
                or (path.name == "generated-video.mp4" and stat.st_size > 2 * 1024 * 1024 * 1024)
                or (path.name != "generated-video.mp4" and stat.st_size > 16 * 1024 * 1024)
            ):
                raise ComfyUIError(
                    "The ComfyUI worker returned an invalid artifact size.",
                    code="invalid_worker_result",
                )
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise ComfyUIError(
                    "The ComfyUI worker returned mismatched artifact metadata.",
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
        if seen_names != set(_LOCAL_COMFYUI_ARTIFACTS):
            raise ComfyUIError(
                "The ComfyUI worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return validated

    def _cached_local_comfyui_result(
        self,
        production_id: str,
        payload: dict[str, Any],
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
        *,
        required_source_attempt_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Recheck a production-wide successful cache inside the GPU lane."""

        cache_key = inputs["cache_key"]
        if required_source_attempt_id is not None:
            try:
                validate_identifier(
                    required_source_attempt_id, label="source stage attempt id"
                )
            except (SecurityError, TypeError, ValueError):
                return None
        previous = self.database.find_successful_stage_attempt(
            production_id, _LOCAL_VIDEO_GENERATION_STAGE, cache_key
        )
        if not previous or not isinstance(previous.get("result"), dict):
            return None

        chain = [previous]
        source_attempt = previous
        visited_attempt_ids = {previous["id"]}
        while source_attempt["result"].get("cache_source_attempt_id") is not None:
            source_result = source_attempt["result"]
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
                or linked.get("stage") != _LOCAL_VIDEO_GENERATION_STAGE
                or linked.get("status") != "succeeded"
                or linked.get("cache_key") != cache_key
                or not isinstance(linked.get("result"), dict)
            ):
                return None
            visited_attempt_ids.add(source_id)
            chain.append(linked)
            source_attempt = linked

        if (
            required_source_attempt_id is not None
            and required_source_attempt_id not in visited_attempt_ids
        ):
            return None

        prior_result = previous["result"]
        prior_artifacts = prior_result.get("artifacts")
        if (
            not isinstance(prior_artifacts, list)
            or len(prior_artifacts) != len(_LOCAL_COMFYUI_ARTIFACTS)
        ):
            return None

        def artifact_signature(value: Any) -> dict[str, tuple[Any, ...]] | None:
            if not isinstance(value, list) or len(value) != len(_LOCAL_COMFYUI_ARTIFACTS):
                return None
            records: dict[str, tuple[Any, ...]] = {}
            for item in value:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    return None
                name = item["name"]
                if name in records:
                    return None
                records[name] = tuple(
                    item.get(field) for field in ("id", "rel_path", "bytes", "sha256")
                )
            return records if set(records) == set(_LOCAL_COMFYUI_ARTIFACTS) else None

        reference_signature = artifact_signature(prior_artifacts)
        if reference_signature is None or any(
            artifact_signature(attempt["result"].get("artifacts"))
            != reference_signature
            for attempt in chain
        ):
            return None
        try:
            from . import comfyui

            physical = comfyui.validate_comfyui_outputs(
                self.workspace,
                production_id=production_id,
                run_id=source_attempt["run_id"],
                payload=payload,
                workflow=inputs["workflow"],
                workflow_source_path=inputs["workflow_source_path"],
                workflow_source_bytes=inputs["workflow_source_bytes"],
                workflow_source_sha256=inputs["workflow_source_sha256"],
                model_files=inputs["model_files"],
                cancel_event=cancel_event,
            )
        except (ImportError, AttributeError, ComfyUIError, ComfyUIValidationError, OSError):
            return None
        physical_artifacts = physical.get("artifacts")
        if not isinstance(physical_artifacts, list):
            return None
        physical_by_name = {
            item.get("name"): item
            for item in physical_artifacts
            if isinstance(item, dict)
        }
        expected_root = (
            f"outputs/studio/runs/{source_attempt['run_id']}/video_generation/{cache_key}/"
        )
        verified_artifacts: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in prior_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            artifact = self.database.get_artifact(item["id"])
            if artifact is None or artifact.get("name") in seen_names:
                return None
            name = artifact.get("name")
            expected = _LOCAL_COMFYUI_ARTIFACTS.get(name)
            physical_item = physical_by_name.get(name)
            if (
                expected is None
                or not isinstance(physical_item, dict)
                or artifact.get("production_id") != production_id
                or not artifact.get("available")
                or artifact.get("origin") != "studio"
                or artifact.get("kind") != expected[0]
                or artifact.get("media_type") != expected[1]
                or artifact.get("rel_path") != f"{expected_root}{name}"
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
                stat = path.stat()
            except (SecurityError, OSError):
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
            seen_names.add(str(name))
            verified_artifacts.append(artifact)
        if seen_names != set(_LOCAL_COMFYUI_ARTIFACTS):
            return None

        prompt_sha256 = hashlib.sha256(payload["prompt"].encode("utf-8")).hexdigest().upper()
        physical_for_public = dict(physical)
        physical_for_public["cache_hit"] = True
        try:
            cached = comfyui_public_result(
                physical_for_public,
                expected_cache_key=cache_key,
                expected_prompt_sha256=prompt_sha256,
                expected_seed=payload["seed"],
                artifacts=verified_artifacts,
                cache_hit=True,
            )
        except (ComfyUIError, ComfyUIValidationError):
            return None
        for attempt in chain:
            attempt_result = attempt["result"]
            attempt_cache_hit = attempt_result.get("cache_hit")
            if not isinstance(attempt_cache_hit, bool):
                return None
            try:
                prior_public = comfyui_public_result(
                    attempt_result,
                    expected_cache_key=cache_key,
                    expected_prompt_sha256=prompt_sha256,
                    expected_seed=payload["seed"],
                    artifacts=verified_artifacts,
                    cache_hit=attempt_cache_hit,
                )
            except (ComfyUIError, ComfyUIValidationError):
                return None
            if any(
                prior_public.get(field) != cached.get(field)
                for field in ("duration_ms", "provider_task_id", "prompt_sha256", "seed")
            ):
                return None
        if cached.get("seed") != payload["seed"]:
            return None
        cached["cache_source_attempt_id"] = previous["id"]
        return cached

    def _execute_local_video_generation(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
        *,
        provider_task_record_id: str | None = None,
        required_cache_source_attempt_id: str | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        if (
            provider_task_record_id is not None
            and required_cache_source_attempt_id is not None
        ):
            raise ComfyUIError(
                "A provider recovery worker cannot enter pipeline cache-only mode.",
                code="invalid_provenance",
            )
        active_provider_task_record_id = provider_task_record_id
        try:
            self.database.update_stage_attempt(attempt_id, "running")
            cache_key = inputs["cache_key"]
            prompt_sha256 = hashlib.sha256(
                payload["prompt"].encode("utf-8")
            ).hexdigest().upper()
            from . import comfyui

            _raise_if_cancelled(cancel_event)
            # A normal invocation may reuse the latest verified Studio result
            # before creating any provider lineage.  A reconciliation job must
            # instead flow through the provider adapter: it validates the
            # private cache against the persisted provider identity and then
            # atomically completes that provider task with this new attempt.
            if active_provider_task_record_id is None:
                cached = self._cached_local_comfyui_result(
                    production_id,
                    payload,
                    inputs,
                    cancel_event,
                    required_source_attempt_id=required_cache_source_attempt_id,
                )
                if cached is not None:
                    return _stage_completion_result(attempt_id, cached, cancel_event)
                if required_cache_source_attempt_id is not None:
                    # Continuation is authorized to consume exactly one
                    # verified cache lineage, never to create/reset a provider
                    # task or submit a replacement prompt.  Keep this fence
                    # before payload-digest/provider/marker handling below.
                    raise ComfyUIError(
                        "The recovered video is unavailable for pipeline continuation.",
                        code="pipeline_recovered_video_unavailable",
                    )
            payload_digest = comfyui_payload_digest(payload)
            attempt = self.database.get_stage_attempt(attempt_id)
            if attempt is None or not isinstance(attempt.get("job_id"), str):
                raise ComfyUIError(
                    "The ComfyUI stage is not linked to a durable job.",
                    code="provider_task_provenance_invalid",
                )
            if active_provider_task_record_id is None:
                existing_tasks = self.database.list_provider_tasks(
                    run_id=run_id, limit=100
                )
                existing = next(
                    (
                        item
                        for item in existing_tasks
                        if item.get("cache_key") == cache_key
                        and item.get("payload_digest") == payload_digest
                    ),
                    None,
                )
                if existing is not None and existing.get("status") in {
                    "succeeded",
                    "failed",
                }:
                    old_provider_task_id = existing.get("provider_task_id")
                    if not isinstance(old_provider_task_id, str):
                        raise ComfyUIError(
                            "The terminal provider task identity is invalid.",
                            code="provider_task_provenance_invalid",
                        )
                    terminal_marker_id = comfyui.recover_comfyui_prompt_id(
                        self.workspace,
                        production_id=production_id,
                        run_id=run_id,
                        cache_key=cache_key,
                        payload_digest=payload_digest,
                    )
                    if terminal_marker_id is not None:
                        if terminal_marker_id != old_provider_task_id:
                            raise ComfyUIError(
                                "The terminal provider marker identity changed.",
                                code="comfyui_submission_unknown",
                            )
                        removed = comfyui.cleanup_comfyui_submission_marker(
                            self.workspace,
                            production_id=production_id,
                            run_id=run_id,
                            cache_key=cache_key,
                            payload_digest=payload_digest,
                            provider_task_id=old_provider_task_id,
                        )
                        if not removed:
                            raise ComfyUIError(
                                "The terminal provider marker could not be reconciled.",
                                code="comfyui_submission_unknown",
                            )
                if existing is not None and existing.get("status") not in {
                    "succeeded",
                    "failed",
                }:
                    prepared_provider_task_id = existing.get("provider_task_id")
                else:
                    prepared_provider_task_id = str(uuid.uuid4())
                if not isinstance(prepared_provider_task_id, str):
                    prepared_provider_task_id = str(uuid.uuid4())
                protection, ciphertext = self._protect_comfyui_resume_payload(payload)
                provider_task, _created = self.database.create_or_get_provider_task(
                    production_id=production_id,
                    run_id=run_id,
                    origin_stage_attempt_id=attempt_id,
                    current_stage_attempt_id=attempt_id,
                    current_job_id=attempt["job_id"],
                    cache_key=cache_key,
                    payload_digest=payload_digest,
                    prepared_provider_task_id=prepared_provider_task_id,
                    request_protection=protection,
                    request_ciphertext=ciphertext,
                )
                active_provider_task_record_id = provider_task["id"]
            else:
                provider_task = self.database.get_provider_task(
                    active_provider_task_record_id
                )
                if (
                    provider_task is None
                    or provider_task.get("production_id") != production_id
                    or provider_task.get("run_id") != run_id
                    or provider_task.get("cache_key") != cache_key
                    or provider_task.get("payload_digest") != payload_digest
                    or provider_task.get("current_stage_attempt_id") != attempt_id
                    or provider_task.get("current_job_id") != attempt["job_id"]
                ):
                    raise ComfyUIError(
                        "The provider recovery claim is invalid.",
                        code="provider_task_provenance_invalid",
                    )
            if cancel_event is not None and active_provider_task_record_id is not None:
                cancel_event.set_provider_task_record_id(
                    active_provider_task_record_id
                )
            known_provider_task_id = provider_task.get("provider_task_id")
            if not isinstance(known_provider_task_id, str):
                raise ComfyUIError(
                    "The provider task has no pre-issued prompt ID.",
                    code="provider_task_provenance_invalid",
                )
            recovered_prompt_id = comfyui.recover_comfyui_prompt_id(
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                payload_digest=payload_digest,
            )
            if recovered_prompt_id is not None:
                if recovered_prompt_id != known_provider_task_id:
                    raise ComfyUIError(
                        "The durable ComfyUI prompt ID changed.",
                        code="comfyui_submission_unknown",
                    )
                provider_task = self.database.record_provider_submission(
                    active_provider_task_record_id, recovered_prompt_id
                )
                resume_prompt_id = recovered_prompt_id
                prepared_prompt_id = None
            elif provider_task.get("status") in {"prepared", "recovering"} and (
                provider_task.get("submitted_at") is None
            ):
                resume_prompt_id = None
                prepared_prompt_id = known_provider_task_id
            else:
                # A previously accepted ID without its marker may still have a
                # fully published cache.  Passing it as resume identity lets
                # the adapter validate that cache first, then fail closed
                # before any POST when the marker/cache is absent.
                resume_prompt_id = known_provider_task_id
                prepared_prompt_id = None

            def provider_submitted(provider_task_id: str) -> None:
                if active_provider_task_record_id is None:
                    raise ComfyUIError(
                        "The provider task record is unavailable.",
                        code="provider_task_provenance_invalid",
                    )
                self.database.record_provider_submission(
                    active_provider_task_record_id, provider_task_id
                )

            raw = comfyui.generate_comfyui_video(
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                payload=payload,
                workflow=inputs["workflow"],
                workflow_source_path=inputs["workflow_source_path"],
                workflow_source_bytes=inputs["workflow_source_bytes"],
                workflow_source_sha256=inputs["workflow_source_sha256"],
                model_files=inputs["model_files"],
                output_roots=inputs["output_roots"],
                expected_cache_key=cache_key,
                cancel_event=cancel_event,
                resume_prompt_id=resume_prompt_id,
                prepared_prompt_id=prepared_prompt_id,
                on_provider_task_id=provider_submitted,
            )
            _raise_if_cancelled(cancel_event)
            raw_cache_hit = raw.get("cache_hit", False) if isinstance(raw, dict) else False
            if (
                not isinstance(raw_cache_hit, bool)
                or not isinstance(raw, dict)
                or raw.get("seed") != payload["seed"]
                or raw.get("workflow_preset") != payload["workflow_preset"]
            ):
                raise ComfyUIError(
                    "The ComfyUI worker returned invalid request metadata.",
                    code="invalid_worker_result",
                )
            provisional = comfyui_public_result(
                raw,
                expected_cache_key=cache_key,
                expected_prompt_sha256=prompt_sha256,
                expected_seed=payload["seed"],
                artifacts=[],
                cache_hit=raw_cache_hit,
            )
            physical = comfyui.validate_comfyui_outputs(
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                payload=payload,
                workflow=inputs["workflow"],
                workflow_source_path=inputs["workflow_source_path"],
                workflow_source_bytes=inputs["workflow_source_bytes"],
                workflow_source_sha256=inputs["workflow_source_sha256"],
                model_files=inputs["model_files"],
                cancel_event=cancel_event,
            )
            if (
                not isinstance(physical, dict)
                or physical.get("seed") != payload["seed"]
                or physical.get("workflow_preset") != payload["workflow_preset"]
            ):
                raise ComfyUIError(
                    "The ComfyUI worker returned invalid verified metadata.",
                    code="invalid_worker_result",
                )
            physical_for_public = dict(physical)
            physical_for_public["cache_hit"] = raw_cache_hit
            verified = comfyui_public_result(
                physical_for_public,
                expected_cache_key=cache_key,
                expected_prompt_sha256=prompt_sha256,
                expected_seed=payload["seed"],
                artifacts=[],
                cache_hit=raw_cache_hit,
            )
            if any(
                provisional.get(field) != verified.get(field)
                for field in ("duration_ms", "provider_task_id", "prompt_sha256", "seed")
            ):
                raise ComfyUIError(
                    "The ComfyUI worker returned mismatched verification metadata.",
                    code="invalid_worker_result",
                )
            raw_artifacts = raw.get("artifacts")
            physical_artifacts = physical.get("artifacts")
            if not isinstance(raw_artifacts, list) or not isinstance(physical_artifacts, list):
                raise ComfyUIError(
                    "The ComfyUI worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )
            physical_by_name = {
                item.get("name"): item
                for item in physical_artifacts
                if isinstance(item, dict)
            }
            for item in raw_artifacts:
                if not isinstance(item, dict):
                    raise ComfyUIError(
                        "The ComfyUI worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                name = Path(str(item.get("rel_path") or "")).name
                comparison = physical_by_name.get(name)
                if (
                    not isinstance(comparison, dict)
                    or item.get("bytes") != comparison.get("bytes")
                    or item.get("sha256") != comparison.get("sha256")
                ):
                    raise ComfyUIError(
                        "The ComfyUI worker returned mismatched artifacts.",
                        code="invalid_worker_result",
                    )
            artifact_records = self._validate_local_comfyui_artifacts(
                run_id, cache_key, raw_artifacts
            )
            # The database replaces this placeholder with registered public
            # artifacts inside the same transaction as job/stage success.
            verified["artifacts"] = []
            _raise_if_cancelled(cancel_event)
            return _stage_completion_result(
                attempt_id,
                verified,
                cancel_event,
                artifact_records=tuple(artifact_records),
                provider_task_record_id=active_provider_task_record_id,
            )
        except JobCancelled:
            # JobManager commits an explicit provider cancellation together
            # with the linked job/stage interruption.  Keeping this worker
            # boundary side-effect free prevents a crash or SQLite error from
            # exposing split provider/job truth.
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_comfyui_error(exc)
            if active_provider_task_record_id is not None:
                # Keep ownership intact until JobManager reaches the database
                # boundary.  The provider state (failed, ambiguous, or
                # recovery_blocked) and the linked job/stage failure then
                # commit in one transaction instead of exposing split truth.
                pass
            # JobManager owns the terminal transition for a linked ComfyUI
            # job/stage pair.  Wrap unknown exceptions at this boundary so
            # only the fixed, allowlisted ComfyUI error reaches its atomic
            # failure transaction; never fail the stage in advance.
            raise ComfyUIError(error_message, code=error_code) from exc

    def execute_local_video_generation(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        _pipeline_capability: object | None = None,
        _pipeline_key: str | None = None,
        _pipeline_lineage: dict[str, Any] | None = None,
        _pipeline_video_recovery_checkpoint: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Queue one pinned, zero-cost MiniMax H3 ComfyUI generation."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in {"local_comfyui", LOCAL_PIPELINE_PROFILE}:
            raise RequestValidationError(
                "This run is not configured for local ComfyUI generation.",
                code="execution_profile_required",
            )
        pipeline_metadata = self._pipeline_child_metadata(
            run, _pipeline_capability, _pipeline_key, _pipeline_lineage
        )
        if _pipeline_video_recovery_checkpoint is not None and (
            run.get("execution_profile") != LOCAL_PIPELINE_PROFILE
            or _pipeline_capability is not self._pipeline_capability
            or _pipeline_key != run.get("pipeline_key")
        ):
            raise RequestValidationError(
                "The recovered video checkpoint is not accepted for this run.",
                code="invalid_provenance",
            )
        requested_stages = run.get("requested_stages")
        if (
            not isinstance(requested_stages, list)
            or _LOCAL_VIDEO_GENERATION_STAGE not in requested_stages
        ):
            raise RequestValidationError(
                "The video_generation stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_comfyui_payload(body)
            inputs = self._resolve_comfyui_execution_inputs(payload)
        except (ComfyUIError, ComfyUIValidationError, OSError) as exc:
            error_code, error_message = safe_comfyui_error(exc)
            raise RequestValidationError(error_message, code=error_code) from exc
        cache_key = inputs["cache_key"]
        if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9A-F]{64}", cache_key):
            raise RequestValidationError(
                "The ComfyUI worker returned an invalid cache key.",
                code="invalid_worker_result",
            )
        verified_video_recovery_checkpoint = None
        if _pipeline_video_recovery_checkpoint is not None:
            verified_video_recovery_checkpoint = (
                self._verified_pipeline_video_recovery_checkpoint(
                    run,
                    str(_pipeline_key),
                    cache_key,
                    _pipeline_video_recovery_checkpoint,
                )
            )
        audit = comfyui_audit_payload(
            payload,
            workflow=inputs["workflow_record"],
            models=inputs["model_files"],
            runtime_identity=inputs["runtime_identity"],
            cache_key=cache_key,
        )
        payload_digest = comfyui_payload_digest(payload)
        attempt_payload = {
            "execution_profile": run["execution_profile"],
            "cache_key": cache_key,
            "provider_payload_digest": payload_digest,
            **audit,
            **pipeline_metadata,
            **(
                {"video_recovery_checkpoint": verified_video_recovery_checkpoint}
                if verified_video_recovery_checkpoint is not None
                else {}
            ),
        }
        job_payload = {
            "run_id": run_id,
            "production_id": run["production_id"],
            "stage": _LOCAL_VIDEO_GENERATION_STAGE,
            "execution_profile": run["execution_profile"],
            "cache_key": cache_key,
            "provider_payload_digest": payload_digest,
            **audit,
            **pipeline_metadata,
            **(
                {"video_recovery_checkpoint": verified_video_recovery_checkpoint}
                if verified_video_recovery_checkpoint is not None
                else {}
            ),
        }
        with self._local_video_submit_lock:
            job, created = self.jobs.submit_local_video_generation_once(
                production_id=run["production_id"],
                run_id=run_id,
                cache_key=cache_key,
                payload_digest=payload_digest,
                attempt_payload=attempt_payload,
                job_payload=job_payload,
                callback_factory=lambda attempt_id: (
                    lambda _job_id, cancel_event: self._execute_local_video_generation(
                        attempt_id,
                        run_id,
                        run["production_id"],
                        payload,
                        inputs,
                        cancel_event,
                        required_cache_source_attempt_id=(
                            verified_video_recovery_checkpoint[
                                "stage_attempt_id"
                            ]
                            if verified_video_recovery_checkpoint is not None
                            else None
                        ),
                    )
                ),
            )
        job["deduplicated"] = not created
        return job

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

    def _validate_local_narration_artifact_records(
        self,
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
        return validated

    def _register_local_narration_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for direct callers outside JobManager."""

        records = self._validate_local_narration_artifact_records(
            run_id, cache_key, raw_artifacts
        )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in records
        ]

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
        *,
        announcement_segment_start_ms: tuple[int, ...] | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        try:
            self.database.update_stage_attempt(attempt_id, "running")
            _raise_if_cancelled(cancel_event)
            artifact_records: list[dict[str, Any]] = []
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
                    worker_kwargs: dict[str, Any] = {
                        "production_id": production_id,
                        "run_id": run_id,
                        "payload": payload,
                    }
                    if announcement_segment_start_ms is not None:
                        worker_kwargs["segment_start_ms"] = (
                            announcement_segment_start_ms
                        )
                    raw = _call_local_worker(
                        narration.generate_local_narration,
                        self.workspace,
                        cancel_event=cancel_event,
                        **worker_kwargs,
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
                artifact_records = self._validate_local_narration_artifact_records(
                    run_id,
                    cache_key,
                    raw.get("artifacts") if isinstance(raw, dict) else None,
                )
            _raise_if_cancelled(cancel_event)
            return self._complete_local_stage(
                attempt_id,
                production_id,
                result,
                cancel_event,
                artifact_records=artifact_records,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_error(exc)
            if isinstance(exc, LocalNarrationError):
                raise
            raise LocalNarrationError(error_message, code=error_code) from exc

    def execute_local_narration(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        _pipeline_capability: object | None = None,
        _pipeline_key: str | None = None,
        _pipeline_lineage: dict[str, Any] | None = None,
        _announcement_narration_timing_capability: object | None = None,
        _announcement_segment_start_ms: list[int] | None = None,
        _announcement_detailed_test_video_key: str | None = None,
    ) -> dict[str, Any]:
        """Queue a zero-cost local narration attempt for a local_sapi run."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in {"local_sapi", LOCAL_PIPELINE_PROFILE}:
            raise RequestValidationError(
                "This run is not configured for local narration.",
                code="execution_profile_required",
            )
        pipeline_metadata = self._pipeline_child_metadata(
            run, _pipeline_capability, _pipeline_key, _pipeline_lineage
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
        announcement_schedule: tuple[int, ...] | None = None
        has_announcement_timing = (
            _announcement_narration_timing_capability is not None
            or _announcement_segment_start_ms is not None
            or _announcement_detailed_test_video_key is not None
        )
        if has_announcement_timing:
            claim = (
                self.database.get_detailed_test_video_claim(
                    run["production_id"],
                    _announcement_detailed_test_video_key,
                )
                if isinstance(_announcement_detailed_test_video_key, str)
                and re.fullmatch(
                    r"[0-9A-F]{64}", _announcement_detailed_test_video_key
                )
                else None
            )
            if (
                _announcement_narration_timing_capability
                is not self._announcement_narration_timing_capability
                or run.get("execution_profile") != DETAILED_TEST_VIDEO_PROFILE
                or not isinstance(claim, dict)
                or claim.get("run_id") != run_id
                or claim.get("revision_id") != run.get("revision_id")
            ):
                raise RequestValidationError(
                    "Announcement narration timing provenance is invalid.",
                    code="invalid_provenance",
                )
            try:
                announcement_schedule = validate_internal_narration_segment_starts(
                    _announcement_segment_start_ms,
                    segment_count=len(payload["segments"]),
                )
            except LocalNarrationValidationError as exc:
                raise RequestValidationError(str(exc), code=exc.code) from exc
        cache_key = narration_cache_key(
            payload,
            segment_start_ms=announcement_schedule,
        )
        narration_audit = audit_payload(
            payload,
            segment_start_ms=announcement_schedule,
        )
        attempt_payload = {
            "execution_profile": run["execution_profile"],
            "cache_key": cache_key,
            **narration_audit,
            **pipeline_metadata,
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
                    "execution_profile": run["execution_profile"],
                    "cache_key": cache_key,
                    **narration_audit,
                    **pipeline_metadata,
                    "stage_attempt_id": attempt["id"],
                },
                lambda _job_id, cancel_event: self._execute_local_narration(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    cache_key,
                    cancel_event,
                    announcement_segment_start_ms=announcement_schedule,
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

    def _validated_remotion_timeline_inputs(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve a closed Remotion recipe to immutable local media inputs."""

        base = {
            "clips": [
                {
                    "video_artifact_id": item["video_artifact_id"],
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                }
                for item in payload["clips"]
            ]
        }
        resolved = self._validated_timeline_inputs(run, base)
        clips: list[dict[str, Any]] = []
        cache_clips: list[dict[str, Any]] = []
        for public, physical, cache in zip(
            payload["clips"], resolved["clips"], resolved["cache_clips"], strict=True
        ):
            editing = {
                "volume_percent": public["volume_percent"],
                "visual_preset": public["visual_preset"],
                "transition_to_next": public["transition_to_next"],
                "overlay": public["overlay"],
            }
            clips.append({**physical, **editing})
            cache_clips.append({**cache, **editing})
        # Compile once at the trust boundary.  The worker repeats this check;
        # keeping the value here makes duration/audit decisions deterministic.
        compiled = compile_remotion_timeline(cache_clips)
        return {
            "clips": clips,
            "cache_clips": cache_clips,
            "aggregate_bytes": resolved["aggregate_bytes"],
            "compiled": compiled,
        }

    def _validate_local_timeline_artifact_records(
        self,
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
        return validated

    def _register_local_timeline_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for direct callers outside JobManager."""

        records = self._validate_local_timeline_artifact_records(
            run_id, cache_key, raw_artifacts
        )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in records
        ]

    def _validate_local_screen_capture_artifact_records(
        self,
        run_id: str,
        capture_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_SCREEN_CAPTURE_ARTIFACTS
        ):
            raise BrowserCaptureError(
                "The local screen capture worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/screen_capture/{capture_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise BrowserCaptureError(
                    "The local screen capture worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise BrowserCaptureError(
                    "The local screen capture worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_SCREEN_CAPTURE_ARTIFACTS.get(path.name)
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
                raise BrowserCaptureError(
                    "The local screen capture worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if item.get("bytes") != stat.st_size or item.get("sha256") != digest:
                raise BrowserCaptureError(
                    "The local screen capture worker returned mismatched artifact metadata.",
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
        if seen_names != set(_LOCAL_SCREEN_CAPTURE_ARTIFACTS):
            raise BrowserCaptureError(
                "The local screen capture worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return validated

    def _validate_local_windows_capture_artifact_records(
        self,
        run_id: str,
        capture_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        """Re-derive the exact native capture artifact set from disk."""

        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_WINDOWS_CAPTURE_ARTIFACTS
        ):
            raise WindowsCaptureError(
                "The Windows capture worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/screen_capture/{capture_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise WindowsCaptureError(
                    "The Windows capture worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise WindowsCaptureError(
                    "The Windows capture worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_WINDOWS_CAPTURE_ARTIFACTS.get(path.name)
            maximum = _LOCAL_WINDOWS_CAPTURE_MAX_ARTIFACT_BYTES.get(path.name)
            if (
                expected is None
                or maximum is None
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
                raise WindowsCaptureError(
                    "The Windows capture worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            digest = _sha256_file(path)
            if (
                stat.st_size <= 0
                or stat.st_size > maximum
                or item.get("bytes") != stat.st_size
                or item.get("sha256") != digest
            ):
                raise WindowsCaptureError(
                    "The Windows capture worker returned mismatched artifact metadata.",
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
        if seen_names != set(_LOCAL_WINDOWS_CAPTURE_ARTIFACTS):
            raise WindowsCaptureError(
                "The Windows capture worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return validated

    def _validate_local_remotion_timeline_artifact_records(
        self,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
            _LOCAL_REMOTION_TIMELINE_ARTIFACTS
        ):
            raise RemotionTimelineError(
                "The Remotion worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        expected_root = f"outputs/studio/runs/{run_id}/remotion_timeline/{cache_key}/"
        validated: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in raw_artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("rel_path"), str):
                raise RemotionTimelineError(
                    "The Remotion worker returned an invalid artifact.",
                    code="invalid_worker_result",
                )
            try:
                path = workspace_path(self.workspace, item["rel_path"], must_exist=True)
                relative = relative_workspace_path(self.workspace, path)
            except (SecurityError, OSError):
                raise RemotionTimelineError(
                    "The Remotion worker returned an unsafe artifact path.",
                    code="unsafe_worker_artifact",
                ) from None
            expected = _LOCAL_REMOTION_TIMELINE_ARTIFACTS.get(path.name)
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
                raise RemotionTimelineError(
                    "The Remotion worker returned an unexpected artifact.",
                    code="invalid_worker_result",
                )
            stat = path.stat()
            maximum = (
                _MAX_LOCAL_TIMELINE_VIDEO_BYTES
                if path.name == "remotion-preview.mp4"
                else 16 * 1024 * 1024
            )
            digest = _sha256_file(path)
            if (
                stat.st_size <= 0
                or stat.st_size > maximum
                or item.get("bytes") != stat.st_size
                or item.get("sha256") != digest
            ):
                raise RemotionTimelineError(
                    "The Remotion worker returned mismatched artifact metadata.",
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
        if seen_names != set(_LOCAL_REMOTION_TIMELINE_ARTIFACTS):
            raise RemotionTimelineError(
                "The Remotion worker returned an incomplete artifact set.",
                code="invalid_worker_result",
            )
        return validated

    def _execute_local_screen_capture(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        capture_key: str,
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        _raise_if_cancelled(cancel_event)
        published_output = False
        completion_handed_off = False
        browser_capture: Any = None

        def report_progress(progress: int, phase: str) -> None:
            if cancel_event is None:
                return
            try:
                self.database.update_job_progress(
                    cancel_event.job_id, progress, phase
                )
            except Exception:
                # Progress telemetry must not override verified media output
                # or the atomic stage/job terminal transition.
                pass

        try:
            self.database.update_stage_attempt(attempt_id, "running")
            report_progress(1, "preflight")
            try:
                from . import browser_capture
            except (ImportError, AttributeError) as exc:
                raise BrowserCaptureError(
                    "The local Playwright worker is not installed.",
                    code="local_worker_unavailable",
                ) from exc
            try:
                raw = _call_local_worker(
                    browser_capture.generate_local_screen_capture,
                    self.workspace,
                    production_id=production_id,
                    run_id=run_id,
                    capture_key=capture_key,
                    payload=payload,
                    cancel_event=cancel_event,
                    progress_callback=report_progress,
                )
                # The real worker returns only after atomically publishing its
                # capture directory.  From here until JobManager commits the
                # artifact records, every failure path owns compensating
                # cleanup of that exact nonce-derived directory.
                published_output = True
            except BrowserCaptureError:
                raise
            except Exception as exc:
                raise BrowserCaptureError(
                    "The local Playwright worker failed.",
                    code="local_screen_capture_failed",
                ) from exc
            result = browser_capture_public_result(
                raw,
                expected_capture_key=capture_key,
                expected_duration_ms=payload["duration_ms"],
                expected_origin=payload["target"]["origin"],
                artifacts=[],
            )
            physical = _call_local_worker(
                browser_capture.validate_local_screen_capture_outputs,
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                capture_key=capture_key,
                payload=payload,
                cancel_event=cancel_event,
            )
            physical_public = browser_capture_public_result(
                physical,
                expected_capture_key=capture_key,
                expected_duration_ms=payload["duration_ms"],
                expected_origin=payload["target"]["origin"],
                artifacts=[],
            )
            report_progress(98, "registration")
            if result != physical_public:
                raise BrowserCaptureError(
                    "The local screen capture worker returned mismatched metadata.",
                    code="invalid_worker_result",
                )
            raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
            physical_artifacts = physical.get("artifacts") if isinstance(physical, dict) else None
            if not isinstance(raw_artifacts, list) or not isinstance(physical_artifacts, list):
                raise BrowserCaptureError(
                    "The local screen capture worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )
            physical_by_name = {
                item.get("name"): item for item in physical_artifacts if isinstance(item, dict)
            }
            if set(physical_by_name) != set(_LOCAL_SCREEN_CAPTURE_ARTIFACTS):
                raise BrowserCaptureError(
                    "The local screen capture worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )
            for item in raw_artifacts:
                if not isinstance(item, dict):
                    raise BrowserCaptureError(
                        "The local screen capture worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                physical_item = physical_by_name.get(item.get("name"))
                if (
                    not isinstance(physical_item, dict)
                    or item.get("bytes") != physical_item.get("bytes")
                    or item.get("sha256") != physical_item.get("sha256")
                ):
                    raise BrowserCaptureError(
                        "The local screen capture worker returned mismatched artifacts.",
                        code="invalid_worker_result",
                    )
            artifact_records = self._validate_local_screen_capture_artifact_records(
                run_id, capture_key, raw_artifacts
            )
            _raise_if_cancelled(cancel_event)
            completion = self._complete_local_stage(
                attempt_id,
                production_id,
                physical_public,
                cancel_event,
                artifact_records=artifact_records,
                failure_cleanup=(
                    lambda: browser_capture.discard_local_screen_capture_outputs(
                        self.workspace,
                        run_id=run_id,
                        capture_key=capture_key,
                    )
                    if cancel_event is not None
                    else None
                ),
            )
            completion_handed_off = True
            return completion
        except JobCancelled:
            if published_output and not completion_handed_off and browser_capture is not None:
                try:
                    browser_capture.discard_local_screen_capture_outputs(
                        self.workspace,
                        run_id=run_id,
                        capture_key=capture_key,
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            if published_output and not completion_handed_off and browser_capture is not None:
                try:
                    browser_capture.discard_local_screen_capture_outputs(
                        self.workspace,
                        run_id=run_id,
                        capture_key=capture_key,
                    )
                except Exception:
                    pass
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_browser_capture_error(exc)
            if isinstance(exc, BrowserCaptureError):
                raise
            raise BrowserCaptureError(error_message, code=error_code) from exc

    def execute_local_screen_capture(
        self, run_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Queue one isolated, loopback-only Playwright viewport capture."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "local_playwright":
            raise RequestValidationError(
                "This run is not configured for local Playwright capture.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if (
            not isinstance(requested_stages, list)
            or _LOCAL_SCREEN_CAPTURE_STAGE not in requested_stages
        ):
            raise RequestValidationError(
                "The screen_capture stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_browser_capture_payload(body)
            capture_key = browser_capture_key(payload, uuid.uuid4().hex)
            audit = browser_capture_audit_payload(payload, capture_key=capture_key)
        except BrowserCaptureValidationError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_SCREEN_CAPTURE_STAGE,
            capture_key,
            {"execution_profile": run["execution_profile"], **audit},
        )
        try:
            job = self.jobs.submit(
                "local_screen_capture",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_SCREEN_CAPTURE_STAGE,
                    "execution_profile": run["execution_profile"],
                    **audit,
                    "stage_attempt_id": attempt["id"],
                },
                lambda _job_id, cancel_event: self._execute_local_screen_capture(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    payload,
                    capture_key,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
                lane="browser",
            )
        except Exception as exc:
            error_code, error_message = safe_browser_capture_error(exc)
            self.database.update_stage_attempt(
                attempt["id"],
                "failed",
                error_code=error_code,
                error_message=error_message,
            )
            raise
        job["stage_attempt_id"] = attempt["id"]
        job["capture_key"] = capture_key
        return job

    def _execute_windows_capture(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        payload: dict[str, Any],
        capture_key: str,
        expected_tool_identity_digest: str,
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        """Record one explicit native capture and publish it atomically."""

        _raise_if_cancelled(cancel_event)
        published_output = False
        completion_handed_off = False
        windows_capture_worker: Any = None

        def report_progress(progress: int, phase: str) -> None:
            if cancel_event is None:
                return
            try:
                self.database.update_job_progress(
                    cancel_event.job_id, progress, phase
                )
            except Exception:
                # Progress is advisory; verified media plus the paired
                # job/stage transaction remain the durable source of truth.
                pass

        def discard_published_output() -> None:
            if windows_capture_worker is None:
                return
            windows_capture_worker.discard_windows_capture_outputs(
                self.workspace,
                run_id=run_id,
                capture_key=capture_key,
            )

        try:
            self.database.update_stage_attempt(attempt_id, "running")
            report_progress(1, "preflight")
            try:
                from . import windows_capture_worker
            except (ImportError, AttributeError) as exc:
                raise WindowsCaptureError(
                    "The local Windows capture worker is not installed.",
                    code="windows_capture_unavailable",
                ) from exc
            try:
                raw = _call_local_worker(
                    windows_capture_worker.generate_windows_capture,
                    self.workspace,
                    production_id=production_id,
                    run_id=run_id,
                    capture_key=capture_key,
                    payload=payload,
                    expected_tool_identity_digest=expected_tool_identity_digest,
                    cancel_event=cancel_event,
                    progress_callback=report_progress,
                )
                # The worker owns its staging directory until this atomic
                # publication returns. From this point onward the service
                # owns exact-directory compensation until SQLite commits.
                published_output = True
            except (WindowsCaptureError, WindowsCaptureValidationError):
                raise
            except Exception as exc:
                raise WindowsCaptureError(
                    "The local Windows screen capture failed.",
                    code="windows_capture_failed",
                ) from exc

            result = windows_capture_public_result(
                raw,
                expected_capture_key=capture_key,
                expected_duration_ms=payload["duration_ms"],
                expected_tool_identity_digest=expected_tool_identity_digest,
                artifacts=[],
            )
            physical = _call_local_worker(
                windows_capture_worker.validate_windows_capture_outputs,
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                capture_key=capture_key,
                payload=payload,
                expected_tool_identity_digest=expected_tool_identity_digest,
                cancel_event=cancel_event,
                progress_callback=report_progress,
            )
            physical_public = windows_capture_public_result(
                physical,
                expected_capture_key=capture_key,
                expected_duration_ms=payload["duration_ms"],
                expected_tool_identity_digest=expected_tool_identity_digest,
                artifacts=[],
            )
            report_progress(98, "registration")
            if result != physical_public:
                raise WindowsCaptureError(
                    "The Windows capture worker returned mismatched metadata.",
                    code="invalid_worker_result",
                )

            raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
            physical_artifacts = (
                physical.get("artifacts") if isinstance(physical, dict) else None
            )
            if (
                not isinstance(raw_artifacts, list)
                or not isinstance(physical_artifacts, list)
                or len(raw_artifacts) != len(_LOCAL_WINDOWS_CAPTURE_ARTIFACTS)
                or len(physical_artifacts) != len(_LOCAL_WINDOWS_CAPTURE_ARTIFACTS)
            ):
                raise WindowsCaptureError(
                    "The Windows capture worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )

            def artifact_signature(
                artifacts: list[Any],
            ) -> dict[str, tuple[Any, Any]]:
                signature: dict[str, tuple[Any, Any]] = {}
                for item in artifacts:
                    if not isinstance(item, dict):
                        raise WindowsCaptureError(
                            "The Windows capture worker returned invalid artifacts.",
                            code="invalid_worker_result",
                        )
                    name = item.get("name")
                    if (
                        not isinstance(name, str)
                        or name in signature
                        or name not in _LOCAL_WINDOWS_CAPTURE_ARTIFACTS
                    ):
                        raise WindowsCaptureError(
                            "The Windows capture worker returned invalid artifacts.",
                            code="invalid_worker_result",
                        )
                    signature[name] = (item.get("bytes"), item.get("sha256"))
                return signature

            raw_signature = artifact_signature(raw_artifacts)
            physical_signature = artifact_signature(physical_artifacts)
            if (
                set(raw_signature) != set(_LOCAL_WINDOWS_CAPTURE_ARTIFACTS)
                or raw_signature != physical_signature
            ):
                raise WindowsCaptureError(
                    "The Windows capture worker returned mismatched artifacts.",
                    code="invalid_worker_result",
                )
            artifact_records = self._validate_local_windows_capture_artifact_records(
                run_id,
                capture_key,
                raw_artifacts,
            )
            _raise_if_cancelled(cancel_event)
            completion = self._complete_local_stage(
                attempt_id,
                production_id,
                physical_public,
                cancel_event,
                artifact_records=artifact_records,
                failure_cleanup=discard_published_output,
            )
            completion_handed_off = True
            return completion
        except JobCancelled:
            if published_output and not completion_handed_off:
                try:
                    discard_published_output()
                except WindowsCaptureError as cleanup_exc:
                    raise cleanup_exc
            raise
        except Exception as exc:
            if published_output and not completion_handed_off:
                try:
                    discard_published_output()
                except WindowsCaptureError as cleanup_exc:
                    raise cleanup_exc
            if (
                isinstance(exc, WindowsCaptureError)
                and exc.error_code
                in {"windows_capture_cleanup_failed", "windows_capture_cleanup_required"}
            ):
                raise
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_windows_capture_error(exc)
            if isinstance(exc, WindowsCaptureError):
                raise
            raise WindowsCaptureError(error_message, code=error_code) from exc

    def execute_windows_capture(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        session_binding_digest: str,
    ) -> dict[str, Any]:
        """Consume one explicit intent and admit at most one recording."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") != "local_windows_capture":
            raise RequestValidationError(
                "This run is not configured for local Windows capture.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if (
            not isinstance(requested_stages, list)
            or _LOCAL_SCREEN_CAPTURE_STAGE not in requested_stages
        ):
            raise RequestValidationError(
                "The screen_capture stage was not requested by this run.",
                code="stage_not_requested",
            )
        if not isinstance(session_binding_digest, str) or re.fullmatch(
            r"[0-9A-F]{64}", session_binding_digest
        ) is None:
            raise RequestValidationError(
                "A fresh Windows capture consent is required.",
                code="windows_capture_consent_invalid",
            )
        try:
            payload, consent_token = validate_windows_capture_execution_payload(
                body
            )
            request_settings_digest = windows_capture_settings_digest(payload)
            token_digest = windows_capture_consent_token_digest(consent_token)
        except WindowsCaptureValidationError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc

        def consent_state() -> dict[str, Any]:
            return self.database.windows_capture_consent_state(
                production_id=run["production_id"],
                run_id=run_id,
                token_digest=token_digest,
                session_binding_digest=session_binding_digest,
                request_settings_digest=request_settings_digest,
            )

        def existing_or_reject(state: dict[str, Any]) -> dict[str, Any] | None:
            if state.get("state") == "consumed":
                existing = dict(state["job"])
                existing["deduplicated"] = True
                return existing
            if state.get("state") == "expired":
                raise RequestValidationError(
                    "The Windows capture consent expired. Confirm capture again.",
                    code="windows_capture_consent_expired",
                )
            if state.get("state") != "ready":
                raise RequestValidationError(
                    "A fresh Windows capture consent is required.",
                    code="windows_capture_consent_invalid",
                )
            return None

        # Fast replay path comes before capability/lane checks. The exact same
        # token must resolve to its original job even after that job is
        # terminal or the workstation capability later changes.
        existing = existing_or_reject(consent_state())
        if existing is not None:
            return existing

        with self._windows_capture_submit_lock:
            # Linearize two HTTP retries in this process. The DB consumption
            # below independently enforces the same property transactionally.
            existing = existing_or_reject(consent_state())
            if existing is not None:
                return existing

            active = self.database.find_active_windows_capture_job()
            active_lane_ids = set(self.jobs.active_job_ids_for_lane("capture"))
            if active is not None or active_lane_ids:
                raise RequestValidationError(
                    (
                        "Another Windows capture is already active."
                        if active is not None
                        else "A prior Windows capture is still retiring."
                    ),
                    code="windows_capture_busy",
                )

            capability = inspect_windows_capture_capability_environment(
                self.workspace
            )
            tool_identity_digest = (
                capability.get("tool_identity_digest")
                if isinstance(capability, dict)
                else None
            )
            helper = (
                capability.get("helper") if isinstance(capability, dict) else None
            )
            if (
                not isinstance(capability, dict)
                or capability.get("status") != "ready"
                or capability.get("foundation_ready") is not True
                or capability.get("capture_execution_enabled") is not True
                or capability.get("actual_capture_performed") is not False
                or not isinstance(helper, dict)
                or helper.get("recording_started") is not False
                or not isinstance(tool_identity_digest, str)
                or re.fullmatch(r"[0-9A-F]{64}", tool_identity_digest) is None
            ):
                raise RequestValidationError(
                    "Local Windows capture is not ready on this workstation.",
                    code="windows_capture_unavailable",
                )
            try:
                request_digest = windows_capture_request_digest(
                    payload,
                    tool_identity_digest=tool_identity_digest,
                )
                capture_key = windows_capture_key(
                    payload,
                    uuid.uuid4().hex,
                    tool_identity_digest=tool_identity_digest,
                )
                audit = windows_capture_audit_payload(
                    payload,
                    capture_key=capture_key,
                    request_digest=request_digest,
                    tool_identity_digest=tool_identity_digest,
                )
            except WindowsCaptureValidationError as exc:
                raise RequestValidationError(
                    str(exc.public_message), code=str(exc.error_code)[:128]
                ) from exc

            attempt_payload = {
                "execution_profile": run["execution_profile"],
                "request_settings_digest": request_settings_digest,
                **audit,
            }
            job_payload = {
                "run_id": run_id,
                "production_id": run["production_id"],
                "stage": _LOCAL_SCREEN_CAPTURE_STAGE,
                "execution_profile": run["execution_profile"],
                "request_settings_digest": request_settings_digest,
                **audit,
            }
            try:
                job, created = self.jobs.submit_windows_capture_once(
                    production_id=run["production_id"],
                    run_id=run_id,
                    token_digest=token_digest,
                    session_binding_digest=session_binding_digest,
                    request_settings_digest=request_settings_digest,
                    capture_key=capture_key,
                    attempt_payload=attempt_payload,
                    job_payload=job_payload,
                    callback_factory=lambda attempt_id: (
                        lambda _job_id, cancel_event: self._execute_windows_capture(
                            attempt_id,
                            run_id,
                            run["production_id"],
                            payload,
                            capture_key,
                            tool_identity_digest,
                            cancel_event,
                        )
                    ),
                )
            except WindowsCaptureConsentError as exc:
                raise RequestValidationError(str(exc), code=exc.code) from exc
            job["deduplicated"] = not created
            return job

    def cancel_windows_capture_job(
        self, job_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Publish cancellation for exactly one native-capture job."""

        validate_identifier(job_id, label="job id")
        if not isinstance(body, dict) or body:
            raise RequestValidationError(
                "Windows capture cancellation body must be an empty object."
            )
        job = self.database.get_job(job_id)
        if job is None:
            raise KeyError("job not found")
        if job.get("kind") != "local_windows_capture":
            raise RequestValidationError(
                "Only a local Windows capture job can use this endpoint.",
                code="windows_capture_job_required",
            )
        was_active = bool(
            job.get("status") in {"queued", "running"}
            or self.jobs.is_admitted(job_id)
        )
        current = (
            self.jobs.cancel_and_wait(job_id, timeout=0.25)
            if was_active
            else job
        )
        return {
            "job": current,
            "cancel_requested": was_active,
            "worker_retired": not self.jobs.is_admitted(job_id),
        }

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
        try:
            self.database.update_stage_attempt(attempt_id, "running")
            expected_clips = inputs["cache_clips"]
            expected_duration_ms = sum(
                item["end_ms"] - item["start_ms"] for item in expected_clips
            )
            _raise_if_cancelled(cancel_event)
            artifact_records: list[dict[str, Any]] = []
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
                artifact_records = self._validate_local_timeline_artifact_records(
                    run_id,
                    cache_key,
                    raw_artifacts,
                )
                result = physical_public
            _raise_if_cancelled(cancel_event)
            return self._complete_local_stage(
                attempt_id,
                production_id,
                result,
                cancel_event,
                artifact_records=artifact_records,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_timeline_error(exc)
            if isinstance(exc, LocalTimelineError):
                raise
            raise LocalTimelineError(error_message, code=error_code) from exc

    def execute_local_timeline(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        _pipeline_capability: object | None = None,
        _pipeline_key: str | None = None,
        _pipeline_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Queue a zero-cost local hard-cut timeline composition attempt."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in {
            "local_sapi",
            "local_playwright",
            "local_windows_capture",
            LOCAL_PIPELINE_PROFILE,
        }:
            raise RequestValidationError(
                "This run is not configured for local timeline composition.",
                code="execution_profile_required",
            )
        pipeline_metadata = self._pipeline_child_metadata(
            run, _pipeline_capability, _pipeline_key, _pipeline_lineage
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
            {
                "execution_profile": run["execution_profile"],
                **audit,
                **pipeline_metadata,
            },
        )
        try:
            job = self.jobs.submit(
                "local_timeline",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_TIMELINE_STAGE,
                    "execution_profile": run["execution_profile"],
                    **audit,
                    **pipeline_metadata,
                    "stage_attempt_id": attempt["id"],
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

    def _execute_remotion_timeline(
        self,
        attempt_id: str,
        run_id: str,
        production_id: str,
        cache_key: str,
        inputs: dict[str, Any],
        cancel_event: JobExecutionContext | None = None,
    ) -> dict[str, Any] | AtomicStageCompletion:
        """Render and atomically register one closed Remotion recipe."""

        _raise_if_cancelled(cancel_event)
        remotion_worker: Any = None
        owns_published_output = False
        completion_handed_off = False

        def report_progress(progress: int, phase: str) -> None:
            if cancel_event is None:
                return
            try:
                self.database.update_job_progress(cancel_event.job_id, progress, phase)
            except Exception:
                # Rendering truth and the paired terminal transaction take
                # precedence over best-effort progress telemetry.
                pass

        try:
            self.database.update_stage_attempt(attempt_id, "running")
            report_progress(1, "preflight")
            try:
                from . import remotion_timeline as remotion_worker
            except (ImportError, AttributeError) as exc:
                raise RemotionTimelineError(
                    "The local Remotion worker is not installed.",
                    code="remotion_unavailable",
                ) from exc
            expected_duration_ms = inputs["compiled"]["duration_ms"]
            try:
                raw = _call_local_worker(
                    remotion_worker.generate_remotion_timeline,
                    self.workspace,
                    production_id=production_id,
                    run_id=run_id,
                    cache_key=cache_key,
                    clips=inputs["clips"],
                    cancel_event=cancel_event,
                    progress_callback=report_progress,
                )
            except RemotionTimelineError:
                raise
            except Exception as exc:
                raise RemotionTimelineError(
                    "The local Remotion render failed.",
                    code="local_remotion_render_failed",
                ) from exc
            _raise_if_cancelled(cancel_event)
            raw_cache_hit = raw.get("cache_hit", False) if isinstance(raw, dict) else False
            if not isinstance(raw_cache_hit, bool):
                raise RemotionTimelineError(
                    "The Remotion worker returned invalid cache metadata.",
                    code="invalid_worker_result",
                )
            # A cache hit predates this attempt and must never be removed by
            # compensation if the following database transaction fails.
            owns_published_output = not raw_cache_hit
            result = remotion_timeline_public_result(
                raw,
                expected_cache_key=cache_key,
                expected_duration_ms=expected_duration_ms,
                cache_hit=raw_cache_hit,
                artifacts=[],
            )
            physical = _call_local_worker(
                remotion_worker.validate_remotion_timeline_outputs,
                self.workspace,
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                clips=inputs["clips"],
                cancel_event=cancel_event,
            )
            physical_for_public = dict(physical) if isinstance(physical, dict) else physical
            if isinstance(physical_for_public, dict):
                physical_for_public["cache_hit"] = raw_cache_hit
            physical_public = remotion_timeline_public_result(
                physical_for_public,
                expected_cache_key=cache_key,
                expected_duration_ms=expected_duration_ms,
                cache_hit=raw_cache_hit,
                artifacts=[],
            )
            if result != physical_public:
                raise RemotionTimelineError(
                    "The Remotion worker returned mismatched metadata.",
                    code="invalid_worker_result",
                )
            raw_artifacts = raw.get("artifacts") if isinstance(raw, dict) else None
            physical_artifacts = (
                physical.get("artifacts") if isinstance(physical, dict) else None
            )
            if not isinstance(raw_artifacts, list) or not isinstance(
                physical_artifacts, list
            ):
                raise RemotionTimelineError(
                    "The Remotion worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )
            physical_by_name = {
                item.get("name"): item
                for item in physical_artifacts
                if isinstance(item, dict)
            }
            if set(physical_by_name) != set(_LOCAL_REMOTION_TIMELINE_ARTIFACTS):
                raise RemotionTimelineError(
                    "The Remotion worker returned invalid artifacts.",
                    code="invalid_worker_result",
                )
            for item in raw_artifacts:
                if not isinstance(item, dict):
                    raise RemotionTimelineError(
                        "The Remotion worker returned invalid artifacts.",
                        code="invalid_worker_result",
                    )
                physical_item = physical_by_name.get(item.get("name"))
                if (
                    not isinstance(physical_item, dict)
                    or item.get("bytes") != physical_item.get("bytes")
                    or item.get("sha256") != physical_item.get("sha256")
                    or item.get("rel_path") != physical_item.get("rel_path")
                ):
                    raise RemotionTimelineError(
                        "The Remotion worker returned mismatched artifacts.",
                        code="invalid_worker_result",
                    )
            artifact_records = self._validate_local_remotion_timeline_artifact_records(
                run_id, cache_key, raw_artifacts
            )
            report_progress(98, "registration")
            _raise_if_cancelled(cancel_event)
            completion = self._complete_local_stage(
                attempt_id,
                production_id,
                physical_public,
                cancel_event,
                artifact_records=artifact_records,
                failure_cleanup=(
                    lambda: remotion_worker.discard_remotion_timeline_outputs(
                        self.workspace,
                        run_id=run_id,
                        cache_key=cache_key,
                    )
                    if owns_published_output and cancel_event is not None
                    else None
                ),
            )
            completion_handed_off = True
            return completion
        except JobCancelled:
            if (
                owns_published_output
                and not completion_handed_off
                and remotion_worker is not None
            ):
                try:
                    remotion_worker.discard_remotion_timeline_outputs(
                        self.workspace, run_id=run_id, cache_key=cache_key
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            if (
                owns_published_output
                and not completion_handed_off
                and remotion_worker is not None
            ):
                try:
                    remotion_worker.discard_remotion_timeline_outputs(
                        self.workspace, run_id=run_id, cache_key=cache_key
                    )
                except Exception:
                    pass
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_remotion_timeline_error(exc)
            if isinstance(exc, RemotionTimelineError):
                raise
            raise RemotionTimelineError(error_message, code=error_code) from exc

    def execute_remotion_timeline(
        self, run_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Queue an allowlisted Remotion timeline on the isolated browser lane."""

        validate_identifier(run_id, label="run id")
        run = self.database.get_run(run_id)
        if run is None:
            raise KeyError("run not found")
        if run.get("execution_profile") not in {
            "local_sapi",
            "local_comfyui",
            "local_playwright",
            "local_windows_capture",
        }:
            raise RequestValidationError(
                "This run is not configured for local Remotion composition.",
                code="execution_profile_required",
            )
        requested_stages = run.get("requested_stages")
        if not isinstance(requested_stages, list) or _LOCAL_TIMELINE_STAGE not in requested_stages:
            raise RequestValidationError(
                "The timeline stage was not requested by this run.",
                code="stage_not_requested",
            )
        try:
            payload = validate_remotion_timeline_payload(body)
            inputs = self._validated_remotion_timeline_inputs(run, payload)
            try:
                from . import remotion_timeline as remotion_worker
            except (ImportError, AttributeError) as exc:
                raise RemotionTimelineError(
                    "The local Remotion worker is not installed.",
                    code="remotion_unavailable",
                ) from exc
            tool_identity = _call_local_worker(
                remotion_worker.resolve_remotion_tool_identity,
                self.workspace,
            )
            cache_key = remotion_timeline_cache_key(
                inputs["cache_clips"], tool_identity=tool_identity
            )
            audit = remotion_timeline_audit_payload(
                inputs["cache_clips"], cache_key=cache_key
            )
        except RemotionTimelineValidationError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        except RemotionTimelineError as exc:
            raise RequestValidationError(
                str(exc.public_message), code=str(exc.error_code)[:128]
            ) from exc
        attempt = self.database.create_stage_attempt(
            run_id,
            _LOCAL_TIMELINE_STAGE,
            cache_key,
            {
                "execution_profile": run["execution_profile"],
                "render_engine": "remotion_v1",
                "tool_identity": tool_identity,
                **audit,
            },
        )
        try:
            job = self.jobs.submit(
                "local_remotion_timeline",
                {
                    "run_id": run_id,
                    "production_id": run["production_id"],
                    "stage": _LOCAL_TIMELINE_STAGE,
                    "execution_profile": run["execution_profile"],
                    "render_engine": "remotion_v1",
                    "tool_identity": tool_identity,
                    **audit,
                    "stage_attempt_id": attempt["id"],
                },
                lambda _job_id, cancel_event: self._execute_remotion_timeline(
                    attempt["id"],
                    run_id,
                    run["production_id"],
                    cache_key,
                    inputs,
                    cancel_event,
                ),
                production_id=run["production_id"],
                before_enqueue=lambda created_job: self.database.link_stage_attempt_job(
                    attempt["id"], created_job["id"]
                ),
                lane="browser",
            )
        except Exception as exc:
            error_code, error_message = safe_remotion_timeline_error(exc)
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
            elif run.get("execution_profile") in {"local_sapi", LOCAL_PIPELINE_PROFILE}:
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

    def _validate_local_assembly_artifact_records(
        self,
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
        return validated

    def _register_local_assembly_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        include_captioned: bool,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for direct callers outside JobManager."""

        records = self._validate_local_assembly_artifact_records(
            run_id, cache_key, include_captioned, raw_artifacts
        )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in records
        ]

    def _cached_local_assembly_result(
        self,
        cache_key: str,
        production_id: str,
        expected_hashes: dict[str, str],
        include_captioned: bool,
        caption_style: dict[str, Any],
        audio_mix_preset: str,
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
                caption_style_preset=caption_style["preset"],
                audio_mix_preset=audio_mix_preset,
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
                expected_caption_style=caption_style,
                expected_audio_mix_preset=audio_mix_preset,
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
                expected_caption_style=caption_style,
                expected_audio_mix_preset=audio_mix_preset,
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
        try:
            self.database.update_stage_attempt(attempt_id, "running")
            expected_hashes = {
                "source_video_sha256": inputs["source_video_sha256"],
                "narration_wav_sha256": inputs["narration_wav_sha256"],
                "captions_sha256": inputs["captions_sha256"],
            }
            _raise_if_cancelled(cancel_event)
            artifact_records: list[dict[str, Any]] = []
            cached = self._cached_local_assembly_result(
                cache_key,
                production_id,
                expected_hashes,
                payload["include_captioned"],
                payload["caption_style"],
                payload["audio_mix_preset"],
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
                        caption_style_preset=payload["caption_style_preset"],
                        audio_mix_preset=payload["audio_mix_preset"],
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
                    expected_caption_style=payload["caption_style"],
                    expected_audio_mix_preset=payload["audio_mix_preset"],
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
                    caption_style_preset=payload["caption_style_preset"],
                    audio_mix_preset=payload["audio_mix_preset"],
                    cancel_event=cancel_event,
                )
                physical_for_public = dict(physical_result)
                physical_for_public["cache_hit"] = raw_cache_hit
                physical_public = assembly_public_result(
                    physical_for_public,
                    expected_cache_key=cache_key,
                    expected_hashes=expected_hashes,
                    expected_include_captioned=payload["include_captioned"],
                    expected_caption_style=payload["caption_style"],
                    expected_audio_mix_preset=payload["audio_mix_preset"],
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
                artifact_records = self._validate_local_assembly_artifact_records(
                    run_id,
                    cache_key,
                    payload["include_captioned"],
                    raw.get("artifacts") if isinstance(raw, dict) else None,
                )
                result = physical_public
            _raise_if_cancelled(cancel_event)
            return self._complete_local_stage(
                attempt_id,
                production_id,
                result,
                cancel_event,
                artifact_records=artifact_records,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_assembly_error(exc)
            if isinstance(exc, LocalAssemblyError):
                raise
            raise LocalAssemblyError(error_message, code=error_code) from exc

    def execute_local_assembly(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        _pipeline_capability: object | None = None,
        _pipeline_key: str | None = None,
        _pipeline_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        pipeline_metadata = self._pipeline_child_metadata(
            run, _pipeline_capability, _pipeline_key, _pipeline_lineage
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
                caption_style_preset=payload["caption_style_preset"],
                audio_mix_preset=payload["audio_mix_preset"],
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
                **pipeline_metadata,
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
                    **pipeline_metadata,
                    "stage_attempt_id": attempt["id"],
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
        caption_style = assembly_result.get("caption_style")
        audio_mix_preset = assembly_result.get("audio_mix_preset")
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
                expected_caption_style=caption_style,
                expected_audio_mix_preset=audio_mix_preset,
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
                    expected_caption_style=caption_style,
                    expected_audio_mix_preset=audio_mix_preset,
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

    def _validate_local_qc_artifact_records(
        self,
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
        return validated

    def _register_local_qc_artifacts(
        self,
        production_id: str,
        run_id: str,
        cache_key: str,
        raw_artifacts: Any,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for direct callers outside JobManager."""

        records = self._validate_local_qc_artifact_records(
            run_id, cache_key, raw_artifacts
        )
        return [
            self.database.register_studio_artifact(production_id, item)
            for item in records
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
        try:
            self.database.update_stage_attempt(attempt_id, "running")
            _raise_if_cancelled(cancel_event)
            artifact_records: list[dict[str, Any]] = []
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
                artifact_records = self._validate_local_qc_artifact_records(
                    run_id, cache_key, physical_artifacts
                )
                result = dict(physical_public)
            _raise_if_cancelled(cancel_event)
            return self._complete_local_stage(
                attempt_id,
                production_id,
                result,
                cancel_event,
                artifact_records=artifact_records,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled() from exc
            error_code, error_message = safe_qc_error(exc)
            if isinstance(exc, LocalQcError):
                raise
            raise LocalQcError(error_message, code=error_code) from exc

    def execute_local_qc(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        _pipeline_capability: object | None = None,
        _pipeline_key: str | None = None,
        _pipeline_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        pipeline_metadata = self._pipeline_child_metadata(
            run, _pipeline_capability, _pipeline_key, _pipeline_lineage
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
            {
                "execution_profile": run["execution_profile"],
                **audit,
                **pipeline_metadata,
            },
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
                    **pipeline_metadata,
                    "stage_attempt_id": attempt["id"],
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
