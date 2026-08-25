from __future__ import annotations

import hashlib
import inspect
import json
import mimetypes
import os
import queue
import re
import signal
import subprocess
import threading
import time
import zipfile
from bisect import bisect_right
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .database import AtomicStageCompletion, StudioDatabase
from .security import (
    UnsafeTextArtifactError,
    canonical_json,
    redact_artifact_text,
    sensitive_artifact_path,
    stable_id,
    unsafe_structured_text_suffix,
    validate_identifier,
    workspace_path,
)


JobCallable = Callable[..., dict[str, Any] | AtomicStageCompletion]


# Job records are part of the public Studio API.  Keep this list deliberately
# explicit: an arbitrary exception attribute must never become a persisted
# error code (it may contain a path, command line, or secret).
_PUBLIC_ERROR_CODES = frozenset(
    {
        "approval_rejected",
        "approval_required",
        "billable_confirmation_required",
        "external_narration_failed",
        "external_tts_failed",
        "external_tts_ambiguous_submission",
        "external_tts_secret_unavailable",
        "external_submission_unknown",
        "external_provider_error",
        "external_tts_media_failed",
        "external_redirect_rejected",
        "external_tts_network_failed",
        "invalid_external_provider_metadata",
        "invalid_external_alignment",
        "external_request_invalid",
        "cache_integrity_failed",
        "publish_failed",
        "external_worker_unavailable",
        "ambiguous_submission",
        "assembly_narration_changed",
        "assembly_narration_not_available",
        "assembly_video_changed",
        "assembly_video_not_available",
        "assembly_video_size_invalid",
        "audit_export_failed",
        "cache_key_mismatch",
        "cache_integrity_failed",
        "caption_timing_out_of_range",
        "comfyui_failed",
        "comfyui_generation_failed",
        "comfyui_request_rejected",
        "comfyui_submission_persistence_failed",
        "comfyui_submission_unknown",
        "comfyui_timeout",
        "cost_approval_not_required",
        "cost_estimate_required",
        "execution_profile_required",
        "input_changed",
        "input_hash_mismatch",
        "input_stage_failed",
        "invalid_cache",
        "invalid_cache_key",
        "invalid_captions",
        "invalid_comfyui_output",
        "invalid_comfyui_request",
        "invalid_comfyui_response",
        "invalid_comfyui_runtime",
        "invalid_ffprobe_result",
        "invalid_identifier",
        "invalid_input_path",
        "invalid_local_assembly_request",
        "invalid_local_narration_request",
        "invalid_local_pipeline_request",
        "invalid_external_narration_request",
        "invalid_external_tts_request",
        "invalid_local_qc_request",
        "invalid_local_timeline_request",
        "invalid_range",
        "invalid_media",
        "invalid_output_media",
        "invalid_provenance",
        "invalid_source_media",
        "invalid_tool_identity",
        "invalid_worker_result",
        "invalid_workspace",
        "io_error",
        "job_failed",
        "job_setup_failed",
        "local_assembly_failed",
        "local_ffmpeg_failed",
        "local_ffprobe_failed",
        "local_ffprobe_unavailable",
        "local_ffmpeg_qc_timeout",
        "local_ffmpeg_timeline_failed",
        "local_ffmpeg_timeout",
        "local_ffmpeg_unavailable",
        "local_narration_failed",
        "local_pipeline_failed",
        "pipeline_recovered_video_unavailable",
        "local_pipeline_stage_failed",
        "local_pipeline_timeout",
        "local_pipeline_unavailable",
        "local_profile_cost_not_allowed",
        "local_profile_stage_not_allowed",
        "local_qc_failed",
        "local_qc_unavailable",
        "local_timeline_failed",
        "local_worker_unavailable",
        "metadata_too_large",
        "mismatched_provider_output",
        "narration_invalid",
        "narration_longer_than_source",
        "narration_synthesis_failed",
        "process_interrupted",
        "publish_failed",
        "qc_assembly_changed",
        "qc_assembly_not_available",
        "qc_variant_not_available",
        "request_too_large",
        "source_changed",
        "source_not_available",
        "source_size_invalid",
        "stage_not_requested",
        "timeline_duration_invalid",
        "technical_qc_failed",
        "trim_out_of_range",
        "integrity_verification_failed",
        "unsupported_media_type",
        "unsafe_input_path",
        "unsafe_output_path",
        "unsafe_provider_output",
        "unsafe_worker_artifact",
        "windows_sapi_unavailable",
    }
)

_PROCESS_TERMINATION_TIMEOUT = 2.0
_PROCESS_WAIT_TIMEOUT = 0.2
_FINAL_SWEEP_COUNT = 3
_FINAL_SWEEP_DELAY = 0.01


def _public_error_code(exc: BaseException) -> str:
    candidate = getattr(exc, "error_code", None)
    if isinstance(candidate, str) and candidate in _PUBLIC_ERROR_CODES:
        return candidate
    return "job_failed"


def _public_error_message(exc: BaseException, code: str) -> str:
    # An unknown exception is not trusted merely because it exposes a
    # ``public_message`` attribute.  Keep the fallback fully fixed so paths,
    # command lines, and secrets cannot cross the job-record boundary.
    if code == "job_failed":
        return "The background job failed."
    candidate = getattr(exc, "public_message", None)
    if isinstance(candidate, str):
        return candidate[:1000]
    return "The background job failed."


class JobManagerClosed(RuntimeError):
    """Raised when a request races with Studio shutdown."""


class PipelineContinuationFenced(RuntimeError):
    """Raised when an exact operator cancel blocks continuation admission."""


class JobCancelled(RuntimeError):
    """Raised by a cooperative worker after the Studio shutdown signal."""

    error_code = "process_interrupted"
    public_message = "The Studio process stopped before the job completed."


class JobExecutionContext(threading.Event):
    """Cancellation token and process registry for one background job.

    The class deliberately subclasses :class:`threading.Event`, so existing
    workers can use ``is_set()``/``wait()`` directly while newer workers can
    register subprocesses for a reliable process-tree shutdown.
    """

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self._process_lock = threading.Lock()
        self._processes: dict[int, object] = {}
        self._baseline_processes: set[int] = set()
        self._preserve_provider_task = False
        self._operator_cancel_requested = False
        self._provider_task_record_id: str | None = None

    def set(self) -> None:
        """Publish cancellation under the same lock as process admission.

        A worker can create a child and call ``register_process`` at exactly
        the same time as shutdown.  Serialising both operations means the
        child is either visible to the shutdown sweep or is rejected and
        killed by ``register_process`` after the lock is released.
        """

        with self._process_lock:
            # An explicit cancellation supersedes a prior shutdown/suspend
            # request if both race.  Provider adapters may therefore issue
            # their best-effort remote cancellation only for this path.
            self._preserve_provider_task = False
            self._operator_cancel_requested = True
            super().set()

    def set_for_shutdown(self) -> None:
        """Stop local polling while leaving a durable provider task alive.

        Studio shutdown is not an operator request to discard a multi-hour
        ComfyUI render.  The next process can bind a new job/attempt to the
        persisted provider task and resume history polling without another
        expensive POST.
        """

        with self._process_lock:
            # Explicit operator cancellation is monotonic. A later Studio
            # shutdown must never turn destructive intent back into provider
            # preservation and automatic continuation.
            if not self._operator_cancel_requested:
                self._preserve_provider_task = True
            super().set()

    @property
    def preserve_provider_task(self) -> bool:
        with self._process_lock:
            return self._preserve_provider_task

    def set_provider_task_record_id(self, provider_task_record_id: str) -> None:
        validate_identifier(provider_task_record_id, label="provider task record id")
        with self._process_lock:
            if self._provider_task_record_id not in {None, provider_task_record_id}:
                raise ValueError("provider task record changed")
            self._provider_task_record_id = provider_task_record_id

    @property
    def provider_task_record_id(self) -> str | None:
        with self._process_lock:
            return self._provider_task_record_id

    def clear(self) -> None:
        # Event.clear() is not used by JobManager, but keeping it lock-safe
        # preserves the Event contract for existing callers.
        with self._process_lock:
            self._preserve_provider_task = False
            self._operator_cancel_requested = False
            super().clear()

    def raise_if_cancelled(self) -> None:
        if self.is_set():
            raise JobCancelled()

    def register_process(self, process: object) -> None:
        pid = getattr(process, "pid", None)
        valid_pid = isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
        with self._process_lock:
            cancelled = self.is_set()
            if not cancelled and valid_pid:
                self._processes[pid] = process
        if cancelled:
            # close() raced with Popen: fail closed and stop the process
            # before exposing it to any later stage of the worker.  Do this
            # outside the registry lock so a slow OS operation cannot reopen
            # the shutdown/registration window.
            if valid_pid:
                _terminate_process_tree(pid)
            raise JobCancelled()

    def unregister_process(self, process: object) -> None:
        pid = getattr(process, "pid", None)
        if isinstance(pid, int):
            with self._process_lock:
                self._processes.pop(pid, None)

    def process_pids(self) -> set[int]:
        with self._process_lock:
            return set(self._processes)

    def set_baseline_processes(self, pids: set[int]) -> None:
        with self._process_lock:
            self._baseline_processes = set(pids)

    def baseline_processes(self) -> set[int]:
        with self._process_lock:
            return set(self._baseline_processes)


@dataclass(frozen=True)
class _QueuedJob:
    job_id: str
    callback: JobCallable
    context: JobExecutionContext


def _child_process_ids() -> set[int]:
    """Return this server's descendant PIDs when psutil is available.

    psutil is optional: registered ``Popen`` objects still get a direct
    ``taskkill``/process-group fallback on installations without it.
    """

    try:
        import psutil  # type: ignore[import-not-found]

        children = psutil.Process(os.getpid()).children(recursive=True)
    except Exception:
        return set()

    result: set[int] = set()
    try:
        children = list(children)
    except Exception:
        return set()
    for child in children:
        try:
            if child.is_running():
                result.add(int(child.pid))
        except Exception:
            # One disappearing/inaccessible child must not hide the rest of
            # the process tree from the shutdown sweep.
            continue
    return result


def _terminate_with_psutil(pid: int, *, deadline: float | None = None) -> bool:
    """Best-effort tree termination through psutil.

    The helper intentionally catches psutil's whole exception family around
    each operation.  Processes can disappear between enumeration, kill, and
    wait; an exception for one target must not prevent attempts on the rest.
    """

    try:
        import psutil  # type: ignore[import-not-found]
    except Exception:
        return False

    try:
        root = psutil.Process(pid)
    except Exception:
        return False

    try:
        children = list(root.children(recursive=True))
    except Exception:
        children = []

    targets = list(reversed(children)) + [root]
    for process in targets:
        try:
            process.kill()
        except Exception:
            # NoSuchProcess, AccessDenied, ZombieProcess, and platform-specific
            # psutil errors are all non-fatal to the remaining targets.
            continue

    wait_timeout = _PROCESS_WAIT_TIMEOUT
    if deadline is not None:
        wait_timeout = min(wait_timeout, max(0.0, deadline - time.monotonic()))
    try:
        _gone, alive = psutil.wait_procs(targets, timeout=wait_timeout)
    except Exception:
        alive = targets
    for process in alive or []:
        try:
            process.kill()
        except Exception:
            continue
    return True


def _force_kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        # The process may have exited, or the platform may reject a direct
        # kill after taskkill/psutil already handled it.
        pass


class _AtomicStageLinkError(RuntimeError):
    """A fixed public error for an invalid worker/stage completion link."""

    error_code = "invalid_worker_result"
    public_message = "The background worker returned inconsistent stage metadata."


def _payload_stage_attempt_id(job: dict[str, Any]) -> str | None:
    """Read an opt-in atomic failure link from the durable job payload.

    Existing workers do not persist this field and retain their historical
    behavior.  Worker-backed jobs that do include it can be failed atomically
    even when their callback raises before returning a completion envelope.
    """

    payload = job.get("payload")
    if not isinstance(payload, dict) or "stage_attempt_id" not in payload:
        return None
    value = payload.get("stage_attempt_id")
    if not isinstance(value, str) or re.fullmatch(r"attempt_[0-9a-f]{32}", value) is None:
        raise _AtomicStageLinkError()
    return value


def _is_claimed_local_pipeline_top(job: dict[str, Any]) -> bool:
    """Recognize the durable top contract, not merely a lane-test job kind."""

    payload = job.get("payload")
    return bool(
        job.get("kind") == "local_pipeline"
        and isinstance(payload, dict)
        and payload.get("stage") == "pipeline"
        and payload.get("execution_profile") == "local_pipeline"
        and isinstance(payload.get("production_id"), str)
        and isinstance(payload.get("run_id"), str)
        and isinstance(payload.get("revision_id"), str)
        and isinstance(payload.get("pipeline_key"), str)
        and re.fullmatch(r"[0-9A-F]{64}", payload["pipeline_key"]) is not None
    )


def _terminate_process_tree(pid: int, *, deadline: float | None = None) -> None:
    """Stop one subprocess and all descendants, bounded but not join-only."""

    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return
    if os.name == "nt":
        try:
            command_timeout = _PROCESS_TERMINATION_TIMEOUT
            if deadline is not None:
                command_timeout = min(
                    command_timeout, max(0.0, deadline - time.monotonic())
                )
                if command_timeout <= 0:
                    _force_kill_pid(pid)
                    return
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=command_timeout,
            )
            # A taskkill invocation can start successfully while reporting a
            # non-zero target/result status.  Only a zero exit status is a
            # successful tree termination; otherwise continue to fallback.
            if getattr(result, "returncode", None) == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    # ``taskkill`` is the strongest Windows tree operation.  This fallback
    # also covers non-zero taskkill results, test doubles, and Unix process
    # groups without psutil.  Keep the direct kill after psutil so an
    # inaccessible/disappearing psutil child cannot stop the remaining root
    # attempt.
    _terminate_with_psutil(pid, deadline=deadline)
    _force_kill_pid(pid)


def _terminate_context_processes(
    context: JobExecutionContext, *, deadline: float | None = None
) -> None:
    try:
        baseline = context.baseline_processes()
    except Exception:
        baseline = set()
    try:
        pids = context.process_pids()
    except Exception:
        pids = set()
    try:
        descendants = _child_process_ids()
    except Exception:
        descendants = set()
    for pid in sorted((pids | descendants) - baseline):
        try:
            _terminate_process_tree(pid, deadline=deadline)
        except Exception:
            # A broken process adapter or psutil implementation must not
            # prevent later registered/descendant processes from being tried.
            continue


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


class JobManager:
    _LANES = ("default", "gpu", "pipeline")

    def __init__(self, database: StudioDatabase):
        self.database = database
        # Keep one FIFO queue and one worker per execution lane.  The default
        # lane remains the compatibility surface for existing callers that
        # inspect ``_queue``/``_thread`` in tests and diagnostics; GPU work is
        # deliberately serialized on its own worker so a long ComfyUI job
        # cannot occupy the narration/FFmpeg lane.
        self._queues: dict[str, queue.Queue[_QueuedJob | None]] = {
            lane: queue.Queue() for lane in self._LANES
        }
        self._queue = self._queues["default"]
        self._finished: dict[str, threading.Event] = {}
        self._active: dict[str, JobExecutionContext] = {}
        # Exact top jobs whose queue admission and immediate DB compensation
        # both failed.  Retrying only these IDs avoids guessing whether an
        # unrelated durable queued job belongs to a live worker.
        self._pending_local_pipeline_admission_aborts: set[str] = set()
        # Explicit operator cancellation must outlive the in-memory worker
        # context. A transient SQLite failure can otherwise let the worker
        # retire first and leave generic shutdown recovery free to re-arm the
        # exact pipeline generation that the operator already cancelled.
        self._pending_operator_cancel_job_ids: set[str] = set()
        self._operator_cancel_retry_cursor: str | None = None
        # A worker records dequeue ownership under the same lock used by
        # submission and admission repair.  ``_repairing`` lets a repair win
        # safely when it reaches an ambiguous queued item first.
        self._dequeued_job_ids: set[str] = set()
        self._repairing_local_pipeline_admissions: set[str] = set()
        self._lock = threading.Lock()
        self._closed = False
        self._shutdown_enqueued = False
        self._shutdown_interrupt_started = False
        self._shutdown_interrupt_thread: threading.Thread | None = None
        self._shutdown_interrupt_thread_has_started = False
        self._shutdown_operator_cancel_blocked = False
        self._shutdown_complete = False
        self._threads: dict[str, threading.Thread] = {
            lane: threading.Thread(
                target=self._worker,
                args=(lane,),
                name=("studio-job-worker" if lane == "default" else f"studio-job-worker-{lane}"),
                daemon=True,
            )
            for lane in self._LANES
        }
        # ``_thread`` is an existing private compatibility hook.  Keep it as
        # the default worker, and expose the GPU worker for diagnostics/tests.
        self._thread = self._threads["default"]
        self._gpu_thread = self._threads["gpu"]
        self._pipeline_thread = self._threads["pipeline"]
        for thread in self._threads.values():
            thread.start()

    def submit(
        self,
        kind: str,
        payload: Any,
        callback: JobCallable,
        *,
        production_id: str | None = None,
        before_enqueue: Callable[[dict[str, Any]], None] | None = None,
        admission_failure: Callable[[dict[str, Any]], None] | None = None,
        lane: str = "default",
    ) -> dict[str, Any]:
        # Validate before acquiring the admission lock or creating a durable
        # row.  Callers can safely reject a typo without leaving an orphaned
        # public job record behind.
        if lane not in self._LANES:
            raise ValueError(f"Unsupported job lane: {lane!r}")
        work_queue = self._queues[lane]
        with self._lock:
            if self._closed:
                raise JobManagerClosed("Studio background jobs are closed.")
            # Keep creation, stage-attempt linking, and queue insertion under
            # one admission lock. close() cannot interrupt between a durable
            # queued row and its in-memory queue item.
            job = self.database.create_job(kind, payload, production_id=production_id)
            context = JobExecutionContext(job["id"])
            self._finished[job["id"]] = threading.Event()
            self._active[job["id"]] = context
            try:
                if before_enqueue is not None:
                    before_enqueue(job)
                work_queue.put(_QueuedJob(job["id"], callback, context))
            except Exception:
                # Persist setup failure and never expose an unlinked queued
                # worker. Provider recovery callers supply one exact atomic
                # compensation for provider/job/attempt; ordinary jobs retain
                # the historical job-only setup failure behavior.
                try:
                    if admission_failure is not None:
                        admission_failure(job)
                    else:
                        self.database.update_job(
                            job["id"],
                            "failed",
                            error_code="job_setup_failed",
                            error_message="The background job could not be prepared.",
                        )
                except Exception:
                    pass
                self._active.pop(job["id"], None)
                event = self._finished.get(job["id"])
                if event:
                    event.set()
                raise
            return job

    def is_admitted(self, job_id: str) -> bool:
        """Return whether this manager still owns an in-memory queue/context."""

        validate_identifier(job_id, label="job id")
        with self._lock:
            return job_id in self._active

    def repair_local_pipeline_admissions(self) -> int:
        """Retry exact failed queue-admission compensations, without guessing."""

        repaired = 0
        with self._lock:
            pending = tuple(self._pending_local_pipeline_admission_aborts)[:100]
        for job_id in pending:
            with self._lock:
                if job_id not in self._pending_local_pipeline_admission_aborts:
                    continue
                context = self._active.get(job_id)
                operator_cancel = bool(
                    job_id in self._pending_operator_cancel_job_ids
                    or (
                        context is not None
                        and context.is_set()
                        and not context.preserve_provider_task
                    )
                )
                if job_id in self._dequeued_job_ids:
                    # ``put`` enqueued before raising and the worker won the
                    # handshake. Its finally block owns active/event cleanup.
                    self._pending_local_pipeline_admission_aborts.discard(job_id)
                    continue
                if job_id in self._repairing_local_pipeline_admissions:
                    continue
                self._repairing_local_pipeline_admissions.add(job_id)
            retire_context = False
            discard_pending = False
            admission_aborted = False
            if operator_cancel:
                # Cooperate with (or complete after) cancel_and_wait. This
                # transaction interrupts an active top or fences the exact
                # admission-aborted ready generation; it never turns operator
                # intent back into an automatic continuation.
                try:
                    cancelled = self.database.interrupt_job(
                        job_id,
                        cancel_provider_task=True,
                        preserve_pipeline_continuation=False,
                    )
                except Exception:
                    cancelled = False
                    cancel_failed = True
                else:
                    cancel_failed = False
                if not cancel_failed:
                    try:
                        current = self.database.get_job(job_id)
                    except Exception:
                        current = "read_failed"
                    current_status = (
                        current.get("status")
                        if isinstance(current, dict)
                        else None
                    )
                    if cancelled or current is None or current_status in {
                        "failed",
                        "interrupted",
                        "succeeded",
                    }:
                        discard_pending = True
                        retire_context = True
                with self._lock:
                    self._repairing_local_pipeline_admissions.discard(job_id)
                    if discard_pending:
                        self._pending_local_pipeline_admission_aborts.discard(
                            job_id
                        )
                        self._pending_operator_cancel_job_ids.discard(job_id)
                    if retire_context:
                        self._active.pop(job_id, None)
                        event = self._finished.get(job_id)
                        if event:
                            event.set()
                continue
            try:
                job = self.database.get_job(job_id)
            except Exception:
                # A transient read failure is retried on the next scan.
                job = "read_failed"
            status = job.get("status") if isinstance(job, dict) else None
            if job is None or status in {"failed", "interrupted", "succeeded"}:
                discard_pending = True
                retire_context = True
                admission_aborted = bool(
                    isinstance(job, dict)
                    and status == "failed"
                    and (job.get("error") or {}).get("code")
                    == "job_setup_failed"
                )
            elif status == "running":
                # An enqueue-after-raise worker owns this row. Preserve its
                # context/event and let the worker finally block retire them.
                discard_pending = True
            elif status == "queued":
                try:
                    self.database.abort_local_pipeline_job_admission(
                        job_id,
                        error_code="job_setup_failed",
                        error_message="The background job could not be prepared.",
                    )
                except Exception:
                    # The transaction may have committed before an adapter
                    # raised. Re-read and settle only a proven-safe state.
                    try:
                        current = self.database.get_job(job_id)
                    except Exception:
                        current = "read_failed"
                    current_status = (
                        current.get("status")
                        if isinstance(current, dict)
                        else None
                    )
                    if current is None or current_status in {
                        "failed",
                        "interrupted",
                        "succeeded",
                    }:
                        discard_pending = True
                        retire_context = True
                        admission_aborted = bool(
                            isinstance(current, dict)
                            and current_status == "failed"
                            and (current.get("error") or {}).get("code")
                            == "job_setup_failed"
                        )
                    elif current_status == "running":
                        discard_pending = True
                else:
                    discard_pending = True
                    retire_context = True
                    admission_aborted = True
                    repaired += 1
            # read failures, unknown states, and a still-queued abort failure
            # retain both the exact pending ID and its context for next scan.
            late_operator_cancel = False
            with self._lock:
                current_context = self._active.get(job_id)
                late_operator_cancel = bool(
                    admission_aborted
                    and (
                        job_id in self._pending_operator_cancel_job_ids
                        or (
                            current_context is not None
                            and current_context.is_set()
                            and not current_context.preserve_provider_task
                        )
                    )
                )
                if not late_operator_cancel:
                    self._repairing_local_pipeline_admissions.discard(job_id)
                    if discard_pending:
                        self._pending_local_pipeline_admission_aborts.discard(job_id)
                    if retire_context:
                        self._active.pop(job_id, None)
                        event = self._finished.get(job_id)
                        if event:
                            event.set()
            if late_operator_cancel:
                try:
                    fenced = self.database.interrupt_job(
                        job_id,
                        cancel_provider_task=True,
                        preserve_pipeline_continuation=False,
                    )
                except Exception:
                    fenced = False
                with self._lock:
                    self._repairing_local_pipeline_admissions.discard(job_id)
                    if fenced:
                        self._pending_local_pipeline_admission_aborts.discard(
                            job_id
                        )
                        self._pending_operator_cancel_job_ids.discard(job_id)
                        self._active.pop(job_id, None)
                        event = self._finished.get(job_id)
                        if event:
                            event.set()
        return repaired

    def has_pending_local_pipeline_operator_cancellation(self) -> bool:
        """Return whether automatic continuation is fenced by operator intent."""

        with self._lock:
            # Promote any directly-published context intent as a defensive
            # compatibility path. Normal operator calls add the exact ID in
            # cancel_and_wait before the worker can retire its context.
            for job_id in self._pending_local_pipeline_admission_aborts:
                context = self._active.get(job_id)
                if (
                    context is not None
                    and context.is_set()
                    and not context.preserve_provider_task
                ):
                    self._pending_operator_cancel_job_ids.add(job_id)
            return bool(self._pending_operator_cancel_job_ids)

    def _settle_operator_cancellation_persistence(
        self,
        job_id: str,
        interrupted: bool,
    ) -> bool:
        """Clear one process-local fence only after durable state is settled."""

        if interrupted:
            with self._lock:
                self._pending_operator_cancel_job_ids.discard(job_id)
            return True
        try:
            current = self.database.get_job(job_id)
        except Exception:
            return False
        if current is not None and current.get("status") in {"queued", "running"}:
            return False
        # A missing or already-terminal row has no live generation left for
        # this manager to re-arm. The admission-aborted local-pipeline case is
        # handled idempotently by interrupt_job before reaching this branch.
        with self._lock:
            self._pending_operator_cancel_job_ids.discard(job_id)
        return True

    def retry_pending_operator_cancellations(self, *, limit: int = 100) -> int:
        """Retry exact durable cancel fences fairly during normal operation."""

        safe_limit = max(1, min(int(limit), 1000))
        with self._lock:
            pending = sorted(self._pending_operator_cancel_job_ids)
            if not pending:
                self._operator_cancel_retry_cursor = None
                return 0
            start = (
                bisect_right(pending, self._operator_cancel_retry_cursor)
                if self._operator_cancel_retry_cursor is not None
                else 0
            )
            ordered = pending[start:] + pending[:start]
            targets = tuple(ordered[:safe_limit])
            self._operator_cancel_retry_cursor = targets[-1]

        settled = 0
        for job_id in targets:
            try:
                interrupted = self.database.interrupt_job(
                    job_id,
                    cancel_provider_task=True,
                    preserve_pipeline_continuation=False,
                )
            except Exception:
                continue
            if self._settle_operator_cancellation_persistence(
                job_id, interrupted
            ):
                settled += 1
        return settled

    def submit_local_pipeline_once(
        self,
        *,
        production_id: str,
        run_id: str,
        pipeline_key: str,
        payload: Any,
        callback: JobCallable,
        reuse_succeeded: bool = True,
        expected_continuation_state: str | None = None,
        expected_continuation_updated_at: str | None = None,
        expected_source_job_id: str | None = None,
        expected_source_stage_attempt_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically deduplicate and admit one top-level pipeline worker."""

        work_queue = self._queues["pipeline"]
        with self._lock:
            if self._closed:
                raise JobManagerClosed("Studio background jobs are closed.")
            if (
                expected_continuation_state is not None
                and self._pending_operator_cancel_job_ids
            ):
                # The coordinator's earlier ready scan is only advisory. This
                # manager-lock check linearizes the actual DB CAS admission
                # against cancel_and_wait publishing an exact operator fence.
                raise PipelineContinuationFenced(
                    "Automatic pipeline continuation is fenced by operator cancellation."
                )
            job, created = self.database.create_or_get_local_pipeline_job(
                production_id=production_id,
                run_id=run_id,
                pipeline_key=pipeline_key,
                payload=payload,
                reuse_succeeded=reuse_succeeded,
                expected_continuation_state=expected_continuation_state,
                expected_continuation_updated_at=expected_continuation_updated_at,
                expected_source_job_id=expected_source_job_id,
                expected_source_stage_attempt_id=expected_source_stage_attempt_id,
            )
            if not created:
                # Cross-process ownership is never inferred from this
                # manager's private map. Startup DB interruption handles
                # prior-process rows; exact same-process admission failures
                # are recorded and repaired by the coordinator.
                return job, False
            context = JobExecutionContext(job["id"])
            self._finished[job["id"]] = threading.Event()
            self._active[job["id"]] = context
            try:
                work_queue.put(_QueuedJob(job["id"], callback, context))
            except Exception:
                admission_aborted = False
                try:
                    self.database.abort_local_pipeline_job_admission(
                        job["id"],
                        error_code="job_setup_failed",
                        error_message="The background job could not be prepared.",
                    )
                    admission_aborted = True
                except Exception:
                    self._pending_local_pipeline_admission_aborts.add(job["id"])
                if admission_aborted:
                    self._active.pop(job["id"], None)
                    event = self._finished.get(job["id"])
                    if event:
                        event.set()
                raise
            return job, True

    def submit_local_video_generation_once(
        self,
        *,
        production_id: str,
        run_id: str,
        cache_key: str,
        payload_digest: str,
        attempt_payload: Any,
        job_payload: Any,
        callback_factory: Callable[[str], JobCallable],
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim and admit one active direct ComfyUI request."""

        work_queue = self._queues["gpu"]
        with self._lock:
            if self._closed:
                raise JobManagerClosed("Studio background jobs are closed.")
            job, created = self.database.create_or_get_local_video_generation_job(
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                payload_digest=payload_digest,
                attempt_payload=attempt_payload,
                job_payload=job_payload,
            )
            if not created:
                existing_attempt_id = job.get("stage_attempt_id")
                # A prior callback/queue admission can fail after its durable
                # claim was created.  If the compensating transaction also
                # encountered a transient SQLite failure, that queued row has
                # no in-memory queue owner.  Never return such an orphan as a
                # successful dedupe: retire the exact pair and obtain fresh
                # IDs inside this same manager admission lock.
                if (
                    job.get("status") == "queued"
                    and job["id"] not in self._active
                    and isinstance(existing_attempt_id, str)
                ):
                    self.database.abort_local_video_generation_admission(
                        job["id"],
                        existing_attempt_id,
                        error_code="job_setup_failed",
                        error_message="The background job could not be prepared.",
                    )
                    job, created = self.database.create_or_get_local_video_generation_job(
                        production_id=production_id,
                        run_id=run_id,
                        cache_key=cache_key,
                        payload_digest=payload_digest,
                        attempt_payload=attempt_payload,
                        job_payload=job_payload,
                    )
                if not created:
                    return job, False
            attempt_id = job.get("stage_attempt_id")
            if not isinstance(attempt_id, str):
                raise ValueError("local video generation attempt is unavailable")
            context = JobExecutionContext(job["id"])
            self._finished[job["id"]] = threading.Event()
            self._active[job["id"]] = context
            try:
                callback = callback_factory(attempt_id)
                work_queue.put(_QueuedJob(job["id"], callback, context))
            except Exception:
                try:
                    self.database.abort_local_video_generation_admission(
                        job["id"],
                        attempt_id,
                        error_code="job_setup_failed",
                        error_message="The background job could not be prepared.",
                    )
                except Exception:
                    pass
                self._active.pop(job["id"], None)
                event = self._finished.get(job["id"])
                if event:
                    event.set()
                raise
            return job, True

    @staticmethod
    def _invoke(
        callback: JobCallable, job_id: str, context: JobExecutionContext
    ) -> dict[str, Any] | AtomicStageCompletion:
        """Call old one-argument workers and new cooperative workers safely."""

        try:
            signature = inspect.signature(callback)
        except (TypeError, ValueError):
            return callback(job_id)
        parameters = list(signature.parameters.values())
        if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
            return callback(job_id, context)
        positional = [
            parameter
            for parameter in parameters
            if parameter.kind
            in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        if len(positional) >= 2:
            return callback(job_id, context)
        for parameter in parameters:
            if parameter.kind == inspect.Parameter.KEYWORD_ONLY and parameter.name in {
                "cancel_event",
                "context",
            }:
                return callback(job_id, **{parameter.name: context})
        return callback(job_id)

    def _worker(self, lane: str = "default") -> None:
        work_queue = self._queues[lane]
        while True:
            item = work_queue.get()
            if item is None:
                work_queue.task_done()
                return
            job_id, callback, context = item.job_id, item.callback, item.context
            with self._lock:
                if (
                    self._active.get(job_id) is not context
                    or job_id in self._repairing_local_pipeline_admissions
                ):
                    # Submission compensation or its coordinator retry owns
                    # this queued item. It will retire the context/event.
                    work_queue.task_done()
                    continue
                self._dequeued_job_ids.add(job_id)
                self._pending_local_pipeline_admission_aborts.discard(job_id)
            atomic_stage_attempt_id: str | None = None
            is_local_pipeline = False
            try:
                context.raise_if_cancelled()
                job = self.database.get_job(job_id)
                if job is None or job.get("status") != "queued":
                    # shutdown() has already moved this queued row to the
                    # terminal interrupted state. Never run it afterwards.
                    continue
                is_local_pipeline = _is_claimed_local_pipeline_top(job)
                self.database.update_job(job_id, "running")
                atomic_stage_attempt_id = _payload_stage_attempt_id(job)
                if atomic_stage_attempt_id is not None:
                    linked_attempt = self.database.get_stage_attempt(
                        atomic_stage_attempt_id
                    )
                    if (
                        linked_attempt is None
                        or linked_attempt.get("job_id") != job_id
                    ):
                        raise _AtomicStageLinkError()
                context.raise_if_cancelled()
                context.set_baseline_processes(_child_process_ids())
                # Shutdown may have started while the descendant baseline was
                # collected.  Re-check immediately before invoking a queued
                # callback so it cannot begin after cancellation is published.
                context.raise_if_cancelled()
                result = self._invoke(callback, job_id, context)
                context.raise_if_cancelled()
                if isinstance(result, AtomicStageCompletion):
                    # Worker-backed stages have two durable terminal records.
                    # Commit both rows and both audit events in one SQLite
                    # transaction so shutdown can win or lose the race, but
                    # can never leave stage/job truth split across outcomes.
                    if (
                        atomic_stage_attempt_id is not None
                        and result.stage_attempt_id != atomic_stage_attempt_id
                    ):
                        raise _AtomicStageLinkError()
                    atomic_stage_attempt_id = result.stage_attempt_id
                    self.database.complete_job_with_stage_attempt(
                        job_id,
                        result.stage_attempt_id,
                        result.public_result,
                        result.artifact_records,
                        provider_task_record_id=result.provider_task_record_id,
                    )
                else:
                    if atomic_stage_attempt_id is not None:
                        # A durable stage link opts this job into paired
                        # terminal truth.  A plain mapping cannot safely
                        # commit only the job row and strand its stage.
                        raise _AtomicStageLinkError()
                    current = self.database.get_job(job_id)
                    if current is not None and current.get("status") == "running":
                        if is_local_pipeline:
                            self.database.complete_local_pipeline_job(job_id, result)
                        else:
                            self.database.update_job(job_id, "succeeded", result=result)
            except JobCancelled:
                try:
                    preserve_provider_task = context.preserve_provider_task
                    interrupted = self.database.interrupt_job(
                        job_id,
                        cancel_provider_task=not preserve_provider_task,
                        provider_task_record_id=(
                            None
                            if preserve_provider_task
                            else context.provider_task_record_id
                        ),
                        preserve_pipeline_continuation=preserve_provider_task,
                    )
                except Exception:
                    pass
                else:
                    if not preserve_provider_task:
                        self._settle_operator_cancellation_persistence(
                            job_id, interrupted
                        )
            except Exception as exc:  # The worker boundary must keep later jobs alive.
                try:
                    if context.is_set():
                        preserve_provider_task = context.preserve_provider_task
                        interrupted = self.database.interrupt_job(
                            job_id,
                            cancel_provider_task=not preserve_provider_task,
                            provider_task_record_id=(
                                None
                                if preserve_provider_task
                                else context.provider_task_record_id
                            ),
                            preserve_pipeline_continuation=preserve_provider_task,
                        )
                        if not preserve_provider_task:
                            self._settle_operator_cancellation_persistence(
                                job_id, interrupted
                            )
                    else:
                        # Do not persist repr/traceback/request values; only a
                        # bounded, redacted public description from explicitly
                        # safe exceptions.
                        error_code = _public_error_code(exc)
                        error_message = _public_error_message(exc, error_code)
                        if atomic_stage_attempt_id is not None:
                            self.database.fail_job_with_stage_attempt(
                                job_id,
                                atomic_stage_attempt_id,
                                error_code=error_code,
                                error_message=error_message,
                                provider_task_record_id=context.provider_task_record_id,
                            )
                        elif is_local_pipeline:
                            self.database.fail_local_pipeline_job(
                                job_id,
                                error_code=error_code,
                                error_message=error_message,
                            )
                        else:
                            self.database.update_job(
                                job_id,
                                "failed",
                                error_code=error_code,
                                error_message=error_message,
                            )
                except Exception:
                    pass
            finally:
                if context.is_set():
                    _terminate_context_processes(context)
                with self._lock:
                    self._active.pop(job_id, None)
                    self._dequeued_job_ids.discard(job_id)
                    self._pending_local_pipeline_admission_aborts.discard(job_id)
                    event = self._finished.get(job_id)
                    if event:
                        event.set()
                work_queue.task_done()

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        with self._lock:
            event = self._finished.get(job_id)
        if event:
            event.wait(timeout)
        return self.database.get_job(job_id)

    def cancel_and_wait(
        self,
        job_id: str,
        *,
        timeout: float | None = None,
        preserve_provider_task: bool = False,
    ) -> dict[str, Any] | None:
        """Cancel one admitted job and wait for its worker slot to retire.

        A terminal database row alone is insufficient for orchestration: its
        Python callback or registered subprocess could still be active.  This
        method publishes cancellation, interrupts the linked job/stage pair,
        repeatedly terminates descendants, and only returns after the worker
        has left its ``finally`` block (or an explicit caller timeout elapses).
        Parent-pipeline shutdown may preserve a durable remote provider task;
        operator cancellation keeps the default destructive intent.
        """

        validate_identifier(job_id, label="job id")
        with self._lock:
            if not preserve_provider_task and self._shutdown_complete:
                # Completion is published under this same lock. A caller that
                # arrives later cannot mutate a workspace already released by
                # StudioService.close().
                raise JobManagerClosed("Studio background jobs are closed.")
            if not preserve_provider_task and self._closed:
                # A destructive request that began while shutdown is still in
                # progress is accepted, but forces this close attempt to fail.
                # Its exact ID is persisted by the next shutdown writer before
                # the workspace boundary can be released.
                self._shutdown_operator_cancel_blocked = True
            context = self._active.get(job_id)
            event = self._finished.get(job_id)
            if not preserve_provider_task:
                # Publish the exact ID under the manager lock before the
                # worker can remove its context in finally. The ID survives
                # that retirement until SQLite confirms the cancellation.
                self._pending_operator_cancel_job_ids.add(job_id)
            if context is not None:
                # Linearize cancellation intent with dequeue/admission repair
                # before either path can commit a contradictory ownership
                # decision.
                if preserve_provider_task:
                    context.set_for_shutdown()
                else:
                    context.set()
        if context is not None:
            _terminate_context_processes(context)
        try:
            interrupted = self.database.interrupt_job(
                job_id,
                cancel_provider_task=not preserve_provider_task,
                provider_task_record_id=(
                    context.provider_task_record_id
                    if context is not None and not preserve_provider_task
                    else None
                ),
                preserve_pipeline_continuation=preserve_provider_task,
            )
        except Exception:
            # Cancellation remains published even if SQLite is temporarily
            # unavailable; the worker boundary performs its own best-effort
            # terminal transition.
            pass
        else:
            if not preserve_provider_task:
                self._settle_operator_cancellation_persistence(job_id, interrupted)
        if event is None:
            return self.database.get_job(job_id)

        deadline = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        while not event.is_set():
            if context is not None:
                _terminate_context_processes(context, deadline=deadline)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                event.wait(min(0.1, remaining))
            else:
                event.wait(0.1)
        return self.database.get_job(job_id)

    def shutdown(self, timeout: float = 5.0) -> bool:
        """Cancel active work, terminate child trees, then drain the worker.

        ``join(timeout)`` alone leaves FFmpeg/SAPI descendants alive. The
        cancellation token is published before the DB transition, active
        process trees are repeatedly terminated while the worker winds down,
        and queued work is skipped after it has been durably interrupted.
        """

        with self._lock:
            if self._shutdown_complete:
                return True
            if (
                self._shutdown_operator_cancel_blocked
                and self._shutdown_interrupt_thread is not None
                and not self._shutdown_interrupt_thread.is_alive()
            ):
                # A prior shutdown deliberately retained the workspace after
                # an operator-cancel fence could not be persisted. A retry is
                # allowed to start one new DB writer for the same exact IDs.
                self._shutdown_interrupt_started = False
                self._shutdown_interrupt_thread = None
                self._shutdown_interrupt_thread_has_started = False
            if not self._closed:
                self._closed = True
                contexts = list(self._active.values())
                for context in contexts:
                    context.set_for_shutdown()
            else:
                contexts = list(self._active.values())
            enqueue_sentinel = not self._shutdown_enqueued
            self._shutdown_enqueued = True
            interrupt_active_work = not self._shutdown_interrupt_started
            self._shutdown_interrupt_started = True
            if interrupt_active_work:
                self._shutdown_operator_cancel_blocked = False
                self._shutdown_interrupt_thread = threading.Thread(
                    target=self._interrupt_active_work_best_effort,
                    name="studio-job-shutdown-db",
                    daemon=True,
                )
                # Publish the thread identity before starting it so a
                # concurrent/retried shutdown can never lose the DB writer
                # that must drain before the workspace lock is released.
            interrupt_thread = self._shutdown_interrupt_thread

        wait_seconds = max(0.0, float(timeout))
        deadline = time.monotonic() + wait_seconds
        # Start a process sweep before touching SQLite.  A busy DB must never
        # postpone the first kill attempt.  The interrupt runs in parallel so
        # repeated sweeps can continue while SQLite waits on another writer.
        for context in contexts:
            initial_deadline = deadline
            if wait_seconds <= 0:
                # timeout=0 still gets one short, bounded kill attempt.
                initial_deadline = time.monotonic() + _PROCESS_WAIT_TIMEOUT
            _terminate_context_processes(context, deadline=initial_deadline)

        # Process termination always precedes a potentially blocked SQLite
        # writer.  The thread object was already published above; concurrent
        # shutdown callers treat its not-yet-started state as undrained rather
        # than releasing the workspace boundary early.
        if interrupt_active_work and interrupt_thread is not None:
            try:
                interrupt_thread.start()
            except BaseException:
                with self._lock:
                    self._shutdown_interrupt_started = False
                    self._shutdown_interrupt_thread = None
                    self._shutdown_interrupt_thread_has_started = False
                    if enqueue_sentinel:
                        self._shutdown_enqueued = False
                raise
            with self._lock:
                self._shutdown_interrupt_thread_has_started = True

        if enqueue_sentinel:
            for work_queue in self._queues.values():
                work_queue.put(None)

        threads = tuple(self._threads.values())
        while any(thread.is_alive() for thread in threads):
            for context in contexts:
                _terminate_context_processes(context, deadline=deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            for thread in threads:
                if thread.is_alive():
                    thread.join(min(0.1, remaining))
        # A callback that ignores cancellation cannot be killed as a Python
        # thread, but its registered/descendant subprocesses must still be
        # gone before close returns.
        final_deadline = max(deadline, time.monotonic()) + _PROCESS_WAIT_TIMEOUT
        for context in contexts:
            for sweep in range(_FINAL_SWEEP_COUNT):
                _terminate_context_processes(context, deadline=final_deadline)
                if sweep + 1 < _FINAL_SWEEP_COUNT:
                    time.sleep(_FINAL_SWEEP_DELAY)
        # Do not let a database busy timeout extend shutdown indefinitely. The
        # writer receives only the caller's remaining deadline; if it is still
        # blocked afterwards the workspace boundary remains deliberately held.
        if interrupt_thread is not None and interrupt_thread.is_alive():
            # The worker lanes often retire immediately, but the SQLite
            # interruption transaction can still be syncing its durable event
            # mirror. Give that writer the caller's remaining shutdown budget
            # instead of an unrelated 100 ms slice. A blocked writer remains
            # bounded by the original deadline and therefore still keeps the
            # workspace lock held through the False result below.
            interrupt_thread.join(timeout=max(0.0, deadline - time.monotonic()))
        # A bounded direct caller may choose to retry later.  StudioService
        # treats False as a hard close failure and therefore retains the
        # system-wide workspace lock until every Python worker and the SQLite
        # interruption writer have actually retired.
        with self._lock:
            interrupt_thread_started = self._shutdown_interrupt_thread_has_started
            operator_cancel_blocked = self._shutdown_operator_cancel_blocked
            operator_cancel_pending = bool(self._pending_operator_cancel_job_ids)
            completed = bool(
                not any(thread.is_alive() for thread in threads)
                and not operator_cancel_blocked
                and not operator_cancel_pending
                and (
                    interrupt_thread is None
                    or (
                        interrupt_thread_started
                        and not interrupt_thread.is_alive()
                    )
                )
            )
            # Linearize the release boundary with cancel_and_wait. Once True,
            # a later destructive caller is rejected before publishing an ID.
            self._shutdown_complete = completed
        return completed

    def _interrupt_active_work_best_effort(self) -> None:
        """Persist the shutdown interruption without blocking process kills."""

        if not self._persist_operator_cancellation_fences():
            # Do not let generic process interruption convert an explicit
            # cancel back into a recoverable/ready continuation. shutdown()
            # returns False and a later close retry starts a fresh DB writer.
            with self._lock:
                self._shutdown_operator_cancel_blocked = True
            return
        try:
            self.database.interrupt_active_work()
        except Exception:
            # The worker still receives cancellation and attempts a best-effort
            # terminal update below; never leave a process tree running merely
            # because the audit mirror/database is temporarily unavailable.
            pass

    def _persist_operator_cancellation_fences(self) -> bool:
        """Persist every sticky operator intent before generic shutdown work."""

        try:
            self.repair_local_pipeline_admissions()
        except Exception:
            pass
        with self._lock:
            active_operator_targets = {
                job_id
                for job_id, context in self._active.items()
                if context.is_set() and not context.preserve_provider_task
            }
            # Promote direct context intent and retain the IDs even if their
            # workers retire while this writer is blocked in SQLite.
            self._pending_operator_cancel_job_ids.update(active_operator_targets)
            targets = tuple(self._pending_operator_cancel_job_ids)
        persisted = True
        for job_id in targets:
            try:
                interrupted = self.database.interrupt_job(
                    job_id,
                    cancel_provider_task=True,
                    preserve_pipeline_continuation=False,
                )
            except Exception:
                persisted = False
                continue
            if not self._settle_operator_cancellation_persistence(
                job_id, interrupted
            ):
                persisted = False
        try:
            self.repair_local_pipeline_admissions()
        except Exception:
            persisted = False
        return bool(
            persisted
            and not self.has_pending_local_pipeline_operator_cancellation()
        )


class AuditExportError(RuntimeError):
    error_code = "audit_export_failed"
    public_message = "The audit package could not be created."


class AuditExporter:
    def __init__(self, workspace: Path, database: StudioDatabase):
        self.workspace = workspace.resolve(strict=True)
        self.database = database
        self.audit_root = workspace_path(self.workspace, "outputs/studio/audits")

    @staticmethod
    def _allowed_sidecar(artifact: dict[str, Any], include_media: bool) -> bool:
        if artifact["kind"] in {"video", "audio", "image"}:
            return include_media
        return artifact["kind"] in {"document", "log", "subtitle"}

    @staticmethod
    def _sensitive_path(relative: str) -> bool:
        return sensitive_artifact_path(relative)

    def export(self, production_id: str, job_id: str, *, include_media: bool) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        validate_identifier(job_id, label="job id")
        snapshot = self.database.production_audit_snapshot(production_id)
        if snapshot is None:
            raise AuditExportError()
        destination_directory = workspace_path(self.workspace, self.audit_root / production_id)
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = workspace_path(self.workspace, destination_directory / f"{job_id}.zip")
        temporary = workspace_path(self.workspace, destination.with_suffix(".zip.partial"))
        sidecar = workspace_path(self.workspace, destination.with_suffix(".zip.sha256"))
        sidecar_temporary = workspace_path(
            self.workspace, destination.with_suffix(".zip.sha256.partial")
        )
        included: list[str] = []
        skipped: list[dict[str, str]] = []
        redacted: list[str] = []
        archive_entries: list[dict[str, object]] = []
        skipped_event_mirrors: list[dict[str, str]] = []
        event_chain_tails: dict[str, str] = {}
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                def add_bytes(archive_name: str, data: bytes) -> None:
                    archive.writestr(archive_name, data)
                    archive_entries.append(
                        {
                            "path": archive_name,
                            "bytes": len(data),
                            "sha256": _sha256_bytes(data),
                        }
                    )

                def add_file(archive_name: str, source: Path) -> None:
                    digest = hashlib.sha256()
                    written = 0
                    with source.open("rb") as input_handle, archive.open(
                        archive_name, "w", force_zip64=True
                    ) as output_handle:
                        while chunk := input_handle.read(1024 * 1024):
                            output_handle.write(chunk)
                            digest.update(chunk)
                            written += len(chunk)
                    archive_entries.append(
                        {
                            "path": archive_name,
                            "bytes": written,
                            "sha256": digest.hexdigest().upper(),
                        }
                    )

                production_json = canonical_json(snapshot) + "\n"
                add_bytes("audit/production-snapshot.json", production_json.encode("utf-8"))
                event_lines = "".join(
                    canonical_json(event) + "\n" for event in snapshot.get("events", [])
                )
                add_bytes("audit/events.jsonl", event_lines.encode("utf-8"))
                mirrored_scopes = sorted(
                    {
                        (event["scope_type"], event["scope_id"])
                        for event in snapshot.get("events", [])
                    }
                )
                for scope_type, scope_id in mirrored_scopes:
                    scope_events = [
                        event
                        for event in snapshot.get("events", [])
                        if event["scope_type"] == scope_type and event["scope_id"] == scope_id
                    ]
                    if scope_events:
                        event_chain_tails[f"{scope_type}:{scope_id}"] = scope_events[-1][
                            "event_hash"
                        ]
                    try:
                        mirror_bytes = self.database.verified_event_mirror_bytes(
                            scope_type, scope_id, scope_events
                        )
                        if mirror_bytes is not None:
                            add_bytes(
                                f"studio-events/{scope_type}/{scope_id}.jsonl",
                                mirror_bytes,
                            )
                        else:
                            skipped_event_mirrors.append(
                                {
                                    "scope": f"{scope_type}:{scope_id}",
                                    "reason": "missing_or_failed_verification",
                                }
                            )
                    except (OSError, ValueError):
                        skipped_event_mirrors.append(
                            {
                                "scope": f"{scope_type}:{scope_id}",
                                "reason": "unavailable",
                            }
                        )
                for artifact in snapshot.get("artifacts", []):
                    relative = artifact["rel_path"]
                    if not self._allowed_sidecar(artifact, include_media):
                        reason = (
                            "media_not_requested"
                            if artifact["kind"] in {"video", "audio", "image"}
                            and not include_media
                            else "unsupported_artifact_kind"
                        )
                        skipped.append({"path": relative, "reason": reason})
                        continue
                    if self._sensitive_path(relative):
                        skipped.append({"path": relative, "reason": "sensitive_path"})
                        continue
                    try:
                        source = workspace_path(self.workspace, relative, must_exist=True)
                        if not source.is_file() or source.is_symlink():
                            raise OSError("not a regular file")
                        if unsafe_structured_text_suffix(source.suffix):
                            skipped.append(
                                {
                                    "path": relative,
                                    "reason": "structured_text_requires_local_review",
                                }
                            )
                            continue
                        archive_name = f"workspace/{relative}"
                        if artifact["kind"] in {"document", "log", "subtitle"}:
                            if source.stat().st_size > 16 * 1024 * 1024:
                                skipped.append({"path": relative, "reason": "text_sidecar_too_large"})
                                continue
                            original = source.read_text(encoding="utf-8-sig", errors="replace")
                            try:
                                safe_text = redact_artifact_text(original, suffix=source.suffix)
                            except UnsafeTextArtifactError:
                                skipped.append(
                                    {
                                        "path": relative,
                                        "reason": "structured_text_requires_local_review",
                                    }
                                )
                                continue
                            add_bytes(archive_name, safe_text.encode("utf-8"))
                            if safe_text != original:
                                redacted.append(relative)
                        else:
                            add_file(archive_name, source)
                        included.append(relative)
                    except (OSError, ValueError):
                        skipped.append({"path": relative, "reason": "unavailable"})
                package_manifest = {
                    "production_id": production_id,
                    "job_id": job_id,
                    "include_media": include_media,
                    "included": included,
                    "skipped": skipped,
                    "redacted_text_files": redacted,
                    "event_chain_tails": event_chain_tails,
                    "skipped_event_mirrors": skipped_event_mirrors,
                    "archive_entries": archive_entries,
                }
                archive.writestr(
                    "audit/package-manifest.json",
                    (canonical_json(package_manifest) + "\n").encode("utf-8"),
                )
            with zipfile.ZipFile(temporary, "r") as verification_archive:
                expected_names = {
                    entry["path"] for entry in archive_entries
                } | {"audit/package-manifest.json"}
                actual_names = {entry.filename for entry in verification_archive.infolist()}
                if actual_names != expected_names:
                    raise ValueError("audit archive entry set changed during export")
                stored_manifest = json.loads(
                    verification_archive.read("audit/package-manifest.json")
                )
                if stored_manifest.get("archive_entries") != archive_entries:
                    raise ValueError("audit package manifest does not match written entries")
                for expected in archive_entries:
                    digest = hashlib.sha256()
                    counted = 0
                    with verification_archive.open(str(expected["path"]), "r") as handle:
                        while chunk := handle.read(1024 * 1024):
                            digest.update(chunk)
                            counted += len(chunk)
                    if counted != expected["bytes"] or digest.hexdigest().upper() != expected["sha256"]:
                        raise ValueError("audit archive entry failed post-write verification")
            os.replace(temporary, destination)
        except Exception as exc:
            try:
                temporary.unlink(missing_ok=True)
                sidecar_temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AuditExportError() from exc

        try:
            digest_hex = _sha256_file(destination)
            sidecar_temporary.write_text(
                f"{digest_hex} *{destination.name}\n", encoding="ascii", newline="\n"
            )
            os.replace(sidecar_temporary, sidecar)
        except OSError as exc:
            sidecar_temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise AuditExportError() from exc
        stat = destination.stat()
        relative = destination.relative_to(self.workspace).as_posix()
        artifact = self.database.register_studio_artifact(
            production_id,
            {
                "id": stable_id("art", relative.casefold()),
                "rel_path": relative,
                "name": destination.name,
                "kind": "audit",
                "media_type": mimetypes.guess_type(destination.name)[0] or "application/zip",
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": digest_hex,
                "is_heavy": stat.st_size > 10 * 1024 * 1024,
            },
        )
        return {
            "artifact": artifact,
            "sha256_sidecar": sidecar.relative_to(self.workspace).as_posix(),
            "files_included": len(included),
            "files_skipped": len(skipped),
            "include_media": include_media,
        }
