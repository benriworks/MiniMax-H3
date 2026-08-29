from __future__ import annotations

import subprocess
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from tools.studio import jobs as jobs_module
from tools.studio.database import StudioDatabase
from tools.studio.jobs import (
    JobCancelled,
    JobExecutionContext,
    JobManager,
    JobManagerClosed,
)


class JobManagerShutdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.database = StudioDatabase(
            self.workspace / "studio.sqlite3", workspace=self.workspace
        )
        self.manager = JobManager(self.database)

    def tearDown(self) -> None:
        self.manager.shutdown(timeout=2)
        self.database = None  # type: ignore[assignment]
        self.temporary.cleanup()

    def test_shutdown_publishes_cancel_and_rejects_late_enqueue(self) -> None:
        started = threading.Event()
        observed_cancel = threading.Event()

        def callback(_job_id: str, cancel_event: threading.Event) -> dict[str, object]:
            started.set()
            cancel_event.wait(5)
            if cancel_event.is_set():
                observed_cancel.set()
                raise JobCancelled()
            return {}

        job = self.manager.submit("local_assembly", {}, callback)
        self.assertTrue(started.wait(2))
        self.manager.shutdown(timeout=2)
        self.assertTrue(observed_cancel.is_set())
        self.assertFalse(self.manager._thread.is_alive())
        completed = self.database.get_job(job["id"])
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "interrupted")
        self.assertEqual(completed["error"]["code"], "process_interrupted")
        with self.assertRaises(JobManagerClosed):
            self.manager.submit("late", {}, lambda _job_id: {})

        # The token itself is fail-closed too: a worker cannot register a new
        # child after shutdown has begun.
        context = next(iter(self.manager._active.values()), None)
        if context is not None:
            with mock.patch.object(jobs_module, "_terminate_process_tree"):
                with self.assertRaises(JobCancelled):
                    context.register_process(type("Process", (), {"pid": 54321})())

    def test_gpu_lane_is_fifo_and_serial(self) -> None:
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        order: list[str] = []

        def first(_job_id: str) -> dict[str, object]:
            order.append("first-start")
            first_started.set()
            release_first.wait(2)
            order.append("first-end")
            return {}

        def second(_job_id: str) -> dict[str, object]:
            order.append("second-start")
            second_started.set()
            return {}

        first_job = self.manager.submit("local_video_generation", {}, first, lane="gpu")
        self.assertTrue(first_started.wait(2))
        second_job = self.manager.submit("local_video_generation", {}, second, lane="gpu")
        self.assertFalse(second_started.wait(0.1))

        release_first.set()
        self.assertEqual(self.manager.wait(first_job["id"], timeout=2)["status"], "succeeded")
        self.assertEqual(self.manager.wait(second_job["id"], timeout=2)["status"], "succeeded")
        self.assertEqual(order, ["first-start", "first-end", "second-start"])

    def test_default_and_gpu_lanes_run_in_parallel(self) -> None:
        default_started = threading.Event()
        gpu_started = threading.Event()
        release = threading.Event()

        def callback(started: threading.Event, _job_id: str) -> dict[str, object]:
            started.set()
            release.wait(2)
            return {}

        default_job = self.manager.submit(
            "local_assembly", {}, lambda job_id: callback(default_started, job_id)
        )
        gpu_job = self.manager.submit(
            "local_video_generation",
            {},
            lambda job_id: callback(gpu_started, job_id),
            lane="gpu",
        )
        self.assertTrue(default_started.wait(2))
        self.assertTrue(gpu_started.wait(2))

        release.set()
        self.assertEqual(self.manager.wait(default_job["id"], timeout=2)["status"], "succeeded")
        self.assertEqual(self.manager.wait(gpu_job["id"], timeout=2)["status"], "succeeded")

    def test_pipeline_lane_can_wait_without_blocking_child_lanes(self) -> None:
        pipeline_started = threading.Event()
        default_started = threading.Event()
        release = threading.Event()

        def pipeline(_job_id: str) -> dict[str, object]:
            pipeline_started.set()
            release.wait(2)
            return {}

        pipeline_job = self.manager.submit(
            "local_pipeline", {}, pipeline, lane="pipeline"
        )
        self.assertTrue(pipeline_started.wait(2))
        default_job = self.manager.submit(
            "local_narration",
            {},
            lambda _job_id: (default_started.set() or {}),
        )
        self.assertTrue(default_started.wait(2))
        self.assertEqual(
            self.manager.wait(default_job["id"], timeout=2)["status"], "succeeded"
        )
        release.set()
        self.assertEqual(
            self.manager.wait(pipeline_job["id"], timeout=2)["status"], "succeeded"
        )

    def test_pipeline_admission_repair_only_retries_exact_safe_queued_jobs(self) -> None:
        statuses = {
            "job_queued_success": "queued",
            "job_queued_retry": "queued",
            "job_running": "running",
            "job_failed": "failed",
            "job_interrupted": "interrupted",
            "job_succeeded": "succeeded",
            "job_unknown": "future_state",
        }
        pending = set(statuses) | {"job_missing", "job_read_error"}
        self.manager._pending_local_pipeline_admission_aborts.update(pending)

        def get_job(job_id: str) -> dict[str, str] | None:
            if job_id == "job_read_error":
                raise sqlite3.OperationalError("transient read fixture")
            status = statuses.get(job_id)
            return {"id": job_id, "status": status} if status is not None else None

        def abort(job_id: str, **_kwargs: object) -> dict[str, object]:
            if job_id == "job_queued_retry":
                raise sqlite3.OperationalError("transient abort fixture")
            return {}

        with (
            mock.patch.object(self.database, "get_job", side_effect=get_job),
            mock.patch.object(
                self.database,
                "abort_local_pipeline_job_admission",
                side_effect=abort,
            ) as abort_call,
        ):
            repaired = self.manager.repair_local_pipeline_admissions()

        self.assertEqual(repaired, 1)
        self.assertEqual(
            self.manager._pending_local_pipeline_admission_aborts,
            {"job_queued_retry", "job_unknown", "job_read_error"},
        )
        self.assertEqual(
            {call.args[0] for call in abort_call.call_args_list},
            {"job_queued_success", "job_queued_retry"},
        )

    def test_pipeline_operator_cancel_fence_retries_transient_database_failure(
        self,
    ) -> None:
        job_id = "job_operator_cancel_retry"
        context = JobExecutionContext(job_id)
        context.set()
        self.manager._active[job_id] = context
        self.manager._finished[job_id] = threading.Event()
        self.manager._pending_local_pipeline_admission_aborts.add(job_id)

        with mock.patch.object(
            self.database,
            "interrupt_job",
            side_effect=sqlite3.OperationalError("transient cancel fixture"),
        ):
            self.assertEqual(self.manager.repair_local_pipeline_admissions(), 0)

        self.assertTrue(
            self.manager.has_pending_local_pipeline_operator_cancellation()
        )
        self.assertIn(job_id, self.manager._active)
        self.assertFalse(self.manager._finished[job_id].is_set())

        with (
            mock.patch.object(self.database, "interrupt_job", return_value=True),
            mock.patch.object(
                self.database,
                "get_job",
                return_value={"id": job_id, "status": "interrupted"},
            ),
        ):
            self.assertEqual(self.manager.repair_local_pipeline_admissions(), 0)

        self.assertFalse(
            self.manager.has_pending_local_pipeline_operator_cancellation()
        )
        self.assertNotIn(job_id, self.manager._active)
        self.assertTrue(self.manager._finished[job_id].is_set())

    def test_operator_cancel_retry_batch_rotates_after_failures(self) -> None:
        pending = {"job_cancel_a", "job_cancel_b", "job_cancel_c"}
        self.manager._pending_operator_cancel_job_ids.update(pending)

        with mock.patch.object(
            self.database,
            "interrupt_job",
            side_effect=sqlite3.OperationalError("transient retry fixture"),
        ) as interrupt:
            self.assertEqual(
                self.manager.retry_pending_operator_cancellations(limit=1), 0
            )
            self.assertEqual(
                self.manager.retry_pending_operator_cancellations(limit=1), 0
            )
            self.assertEqual(
                self.manager.retry_pending_operator_cancellations(limit=1), 0
            )

        self.assertEqual(
            [call.args[0] for call in interrupt.call_args_list],
            ["job_cancel_a", "job_cancel_b", "job_cancel_c"],
        )
        self.assertEqual(self.manager._pending_operator_cancel_job_ids, pending)

    def test_shutdown_retries_before_releasing_sticky_operator_cancel(self) -> None:
        job_id = "job_shutdown_cancel_retry"
        context = JobExecutionContext(job_id)
        context.set()
        self.manager._active[job_id] = context
        self.manager._finished[job_id] = threading.Event()
        self.manager._pending_local_pipeline_admission_aborts.add(job_id)

        with mock.patch.object(
            self.database,
            "interrupt_job",
            side_effect=sqlite3.OperationalError("shutdown cancel fixture"),
        ):
            self.assertFalse(self.manager.shutdown(timeout=2))

        self.assertTrue(self.manager._shutdown_operator_cancel_blocked)
        self.assertIn(job_id, self.manager._active)
        self.assertFalse(self.manager._finished[job_id].is_set())

        with mock.patch.object(self.database, "interrupt_job", return_value=True):
            self.assertTrue(self.manager.shutdown(timeout=2))

        self.assertFalse(self.manager._shutdown_operator_cancel_blocked)
        self.assertNotIn(job_id, self.manager._active)
        self.assertTrue(self.manager._finished[job_id].is_set())

    def test_shutdown_fences_late_destructive_cancel_publication(self) -> None:
        writer_started = threading.Event()
        release_writer = threading.Event()
        shutdown_results: list[bool] = []

        def pause_writer() -> bool:
            writer_started.set()
            if not release_writer.wait(5):
                raise AssertionError("shutdown writer fixture was not released")
            return True

        shutdown_thread = threading.Thread(
            target=lambda: shutdown_results.append(self.manager.shutdown(timeout=5)),
            name="late-cancel-shutdown",
        )
        try:
            with (
                mock.patch.object(
                    self.manager,
                    "_persist_operator_cancellation_fences",
                    side_effect=pause_writer,
                ),
                mock.patch.object(
                    self.database,
                    "interrupt_job",
                    side_effect=sqlite3.OperationalError(
                        "late shutdown cancel fixture"
                    ),
                ),
            ):
                shutdown_thread.start()
                self.assertTrue(writer_started.wait(3))
                self.assertIsNone(
                    self.manager.cancel_and_wait("job_late_cancel", timeout=0)
                )
                self.assertIn(
                    "job_late_cancel",
                    self.manager._pending_operator_cancel_job_ids,
                )
                release_writer.set()
                shutdown_thread.join(timeout=5)
        finally:
            release_writer.set()
            shutdown_thread.join(timeout=5)

        self.assertFalse(shutdown_thread.is_alive())
        self.assertEqual(shutdown_results, [False])
        self.assertTrue(self.manager._shutdown_operator_cancel_blocked)
        self.assertTrue(self.manager.shutdown(timeout=2))
        self.assertEqual(self.manager._pending_operator_cancel_job_ids, set())
        with self.assertRaises(JobManagerClosed):
            self.manager.cancel_and_wait("job_after_shutdown", timeout=0)

    def test_cancel_and_wait_retires_worker_before_returning(self) -> None:
        started = threading.Event()
        callback_finished = threading.Event()

        def callback(
            _job_id: str, context: JobExecutionContext
        ) -> dict[str, object]:
            started.set()
            try:
                context.wait(5)
                context.raise_if_cancelled()
                return {}
            finally:
                callback_finished.set()

        job = self.manager.submit("local_narration", {}, callback)
        self.assertTrue(started.wait(2))
        completed = self.manager.cancel_and_wait(job["id"], timeout=2)
        self.assertTrue(callback_finished.is_set())
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "interrupted")
        self.assertTrue(self.manager._finished[job["id"]].is_set())

    def test_invalid_lane_fails_before_persistent_job_creation(self) -> None:
        with mock.patch.object(self.database, "create_job", wraps=self.database.create_job) as create_job:
            with self.assertRaises(ValueError):
                self.manager.submit("local_video_generation", {}, lambda _job_id: {}, lane="unknown")
        create_job.assert_not_called()

    def test_shutdown_stops_both_lanes_and_interrupts_all_jobs(self) -> None:
        default_started = threading.Event()
        gpu_started = threading.Event()

        def callback(started: threading.Event, _job_id: str, context: threading.Event) -> dict[str, object]:
            started.set()
            context.wait(5)
            raise JobCancelled()

        default_job = self.manager.submit(
            "local_assembly",
            {},
            lambda job_id, context: callback(default_started, job_id, context),
        )
        gpu_job = self.manager.submit(
            "local_video_generation",
            {},
            lambda job_id, context: callback(gpu_started, job_id, context),
            lane="gpu",
        )
        self.assertTrue(default_started.wait(2))
        self.assertTrue(gpu_started.wait(2))

        self.manager.shutdown(timeout=2)
        self.assertFalse(self.manager._thread.is_alive())
        self.assertFalse(self.manager._gpu_thread.is_alive())
        self.assertFalse(self.manager._pipeline_thread.is_alive())
        self.assertEqual(self.manager.wait(default_job["id"], timeout=1)["status"], "interrupted")
        self.assertEqual(self.manager.wait(gpu_job["id"], timeout=1)["status"], "interrupted")

    def test_shutdown_reports_noncooperative_worker_until_retry_drains_it(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def callback(_job_id: str) -> dict[str, object]:
            started.set()
            if not release.wait(5):
                raise AssertionError("noncooperative worker fixture was not released")
            return {}

        job = self.manager.submit("audit_export", {}, callback)
        self.assertTrue(started.wait(2))
        self.assertFalse(self.manager.shutdown(timeout=0.05))
        self.assertTrue(self.manager._thread.is_alive())
        release.set()
        self.assertTrue(self.manager._finished[job["id"]].wait(2))
        self.assertTrue(self.manager.shutdown(timeout=2))
        self.assertFalse(self.manager._thread.is_alive())

    def test_shutdown_uses_remaining_deadline_to_drain_database_writer(self) -> None:
        writer_started = threading.Event()
        release_writer = threading.Event()
        original_interrupt = self.database.interrupt_active_work

        def delayed_interrupt() -> dict[str, int]:
            writer_started.set()
            release_writer.wait(1)
            return original_interrupt()

        timer = threading.Timer(0.2, release_writer.set)
        timer.start()
        try:
            with mock.patch.object(
                self.database,
                "interrupt_active_work",
                side_effect=delayed_interrupt,
            ):
                self.assertTrue(self.manager.shutdown(timeout=1))
            self.assertTrue(writer_started.is_set())
            self.assertFalse(self.manager._shutdown_interrupt_thread.is_alive())
        finally:
            release_writer.set()
            timer.cancel()

    def test_shutdown_retains_failure_until_database_writer_drains(self) -> None:
        writer_started = threading.Event()
        release_writer = threading.Event()
        original_interrupt = self.database.interrupt_active_work

        def blocked_interrupt() -> dict[str, int]:
            writer_started.set()
            release_writer.wait(1)
            return original_interrupt()

        try:
            with mock.patch.object(
                self.database,
                "interrupt_active_work",
                side_effect=blocked_interrupt,
            ):
                self.assertFalse(self.manager.shutdown(timeout=0.05))
                self.assertTrue(writer_started.is_set())
                self.assertTrue(self.manager._shutdown_interrupt_thread.is_alive())
                release_writer.set()
                self.assertTrue(self.manager.shutdown(timeout=1))
        finally:
            release_writer.set()

    def test_shutdown_terminates_registered_process_before_worker_join(self) -> None:
        started = threading.Event()
        process_holder: dict[str, subprocess.Popen[bytes]] = {}

        def callback(_job_id: str, cancel_event: threading.Event) -> dict[str, object]:
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            process_holder["process"] = process
            # JobExecutionContext is an Event-compatible token and exposes the
            # registry used by graceful shutdown.
            register = getattr(cancel_event, "register_process")
            register(process)
            started.set()
            cancel_event.wait(60)
            raise JobCancelled()

        try:
            self.manager.submit("local_qc", {}, callback)
            self.assertTrue(started.wait(2))
            process = process_holder["process"]
            self.manager.shutdown(timeout=3)
            deadline = time.monotonic() + 3
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertIsNotNone(process.poll())
        finally:
            process = process_holder.get("process")
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=3)

    def test_event_set_and_registration_share_the_admission_lock(self) -> None:
        context = JobExecutionContext("job_race")
        process = types.SimpleNamespace(pid=54321)
        setter_done = threading.Event()

        context._process_lock.acquire()
        try:
            setter = threading.Thread(
                target=lambda: (context.set(), setter_done.set()), daemon=True
            )
            setter.start()
            self.assertFalse(setter_done.wait(0.05))
        finally:
            context._process_lock.release()
        setter.join(timeout=1)
        self.assertTrue(setter_done.is_set())
        self.assertTrue(context.is_set())

        with mock.patch.object(jobs_module, "_terminate_process_tree") as terminate:
            with self.assertRaises(JobCancelled):
                context.register_process(process)
        terminate.assert_called_once_with(54321)
        self.assertEqual(context.process_pids(), set())

    def test_operator_cancel_intent_is_sticky_across_shutdown_orderings(self) -> None:
        cancel_then_shutdown = JobExecutionContext("job_cancel_then_shutdown")
        cancel_then_shutdown.set()
        cancel_then_shutdown.set_for_shutdown()
        self.assertTrue(cancel_then_shutdown.is_set())
        self.assertFalse(cancel_then_shutdown.preserve_provider_task)

        shutdown_then_cancel = JobExecutionContext("job_shutdown_then_cancel")
        shutdown_then_cancel.set_for_shutdown()
        self.assertTrue(shutdown_then_cancel.preserve_provider_task)
        shutdown_then_cancel.set()
        self.assertFalse(shutdown_then_cancel.preserve_provider_task)

    def test_windows_taskkill_nonzero_uses_fallback(self) -> None:
        with (
            mock.patch.object(jobs_module.os, "name", "nt"),
            mock.patch.object(
                jobs_module.subprocess,
                "run",
                return_value=types.SimpleNamespace(returncode=7),
            ) as run,
            mock.patch.object(jobs_module, "_terminate_with_psutil") as psutil_fallback,
            mock.patch.object(jobs_module, "_force_kill_pid") as force_kill,
        ):
            jobs_module._terminate_process_tree(54321)

        run.assert_called_once()
        psutil_fallback.assert_called_once_with(54321, deadline=None)
        force_kill.assert_called_once_with(54321)

    def test_psutil_exception_does_not_skip_remaining_processes(self) -> None:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        class FakeProcess:
            def __init__(self, name: str, *, raises: BaseException | None = None):
                self.name = name
                self.raises = raises
                self.kill_count = 0

            def kill(self) -> None:
                self.kill_count += 1
                if self.raises is not None:
                    raise self.raises

            def children(self, recursive: bool) -> list[object]:
                self.recursive = recursive
                return children

        child_gone = FakeProcess("gone", raises=NoSuchProcess())
        child_alive = FakeProcess("alive")
        root = FakeProcess("root", raises=AccessDenied())
        children = [child_gone, child_alive]
        fake_psutil = types.SimpleNamespace(
            Process=lambda _pid: root,
            wait_procs=lambda _targets, timeout: ([], [child_alive]),
        )

        with mock.patch.dict("sys.modules", {"psutil": fake_psutil}):
            self.assertTrue(jobs_module._terminate_with_psutil(54321))
        self.assertEqual(child_gone.kill_count, 1)
        self.assertEqual(child_alive.kill_count, 2)
        self.assertEqual(root.kill_count, 1)

    def test_unknown_exception_code_is_replaced_with_public_allowlist_code(self) -> None:
        class SecretError(RuntimeError):
            error_code = "secret=/tmp/private-token"
            public_message = "internal path /tmp/private-token"

        def callback(_job_id: str) -> dict[str, object]:
            raise SecretError()

        job = self.manager.submit("local_qc", {}, callback)
        completed = self.manager.wait(job["id"], timeout=2)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "job_failed")
        self.assertEqual(completed["error"]["message"], "The background job failed.")
        self.assertNotIn("private-token", completed["error"]["code"])
        self.assertNotIn("private-token", completed["error"]["message"])

    def test_known_timeline_error_code_is_preserved_for_public_job_status(self) -> None:
        class TimelineTrimError(RuntimeError):
            error_code = "trim_out_of_range"
            public_message = "The selected cut exceeds the registered source duration."

        def callback(_job_id: str) -> dict[str, object]:
            raise TimelineTrimError()

        job = self.manager.submit("local_timeline", {}, callback)
        completed = self.manager.wait(job["id"], timeout=2)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "trim_out_of_range")
        self.assertEqual(
            completed["error"]["message"],
            "The selected cut exceeds the registered source duration.",
        )

    def test_known_visual_preset_error_is_preserved_for_public_job_status(self) -> None:
        class VisualPresetError(RuntimeError):
            error_code = "visual_preset_incompatible"
            public_message = (
                "The selected visual preset is not compatible with this source."
            )

        def callback(_job_id: str) -> dict[str, object]:
            raise VisualPresetError()

        job = self.manager.submit("local_remotion_timeline", {}, callback)
        completed = self.manager.wait(job["id"], timeout=2)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(
            completed["error"]["code"], "visual_preset_incompatible"
        )
        self.assertEqual(
            completed["error"]["message"],
            "The selected visual preset is not compatible with this source.",
        )

    def test_known_remotion_cleanup_error_is_preserved_for_public_job_status(self) -> None:
        class CleanupError(RuntimeError):
            error_code = "remotion_stage_cleanup_failed"
            public_message = "Remotion temporary files could not be cleaned up"

        def callback(_job_id: str) -> dict[str, object]:
            raise CleanupError()

        job = self.manager.submit("local_remotion_timeline", {}, callback)
        completed = self.manager.wait(job["id"], timeout=2)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(
            completed["error"]["code"], "remotion_stage_cleanup_failed"
        )
        self.assertEqual(
            completed["error"]["message"],
            "Remotion temporary files could not be cleaned up",
        )

    def test_busy_db_interrupt_does_not_delay_first_process_sweep(self) -> None:
        started = threading.Event()
        db_started = threading.Event()
        release_db = threading.Event()
        order: list[str] = []

        def callback(_job_id: str, cancel_event: threading.Event) -> dict[str, object]:
            started.set()
            cancel_event.wait(5)
            raise JobCancelled()

        def blocked_interrupt() -> None:
            db_started.set()
            release_db.wait(2)

        def sweep(_context: JobExecutionContext, *, deadline: float | None = None) -> None:
            if not db_started.is_set():
                order.append("kill_before_db")

        self.database.interrupt_active_work = blocked_interrupt  # type: ignore[method-assign]
        with mock.patch.object(jobs_module, "_terminate_context_processes", side_effect=sweep):
            self.manager.submit("local_qc", {}, callback)
            self.assertTrue(started.wait(2))
            shutdown = threading.Thread(target=self.manager.shutdown, kwargs={"timeout": 0.2})
            shutdown.start()
            self.assertTrue(db_started.wait(1))
            self.assertTrue(order)
            self.assertEqual(order[0], "kill_before_db")
            release_db.set()
            shutdown.join(timeout=2)
            self.assertFalse(shutdown.is_alive())

    def test_shutdown_between_baseline_and_callback_skips_callback(self) -> None:
        baseline_ready = threading.Event()
        release_baseline = threading.Event()
        callback_called = threading.Event()

        def callback(_job_id: str) -> dict[str, object]:
            callback_called.set()
            return {}

        original_set_baseline = JobExecutionContext.set_baseline_processes

        def blocked_set_baseline(
            context: JobExecutionContext, pids: set[int]
        ) -> None:
            original_set_baseline(context, pids)
            baseline_ready.set()
            release_baseline.wait(2)

        with mock.patch.object(
            JobExecutionContext, "set_baseline_processes", blocked_set_baseline
        ):
            job = self.manager.submit("local_qc", {}, callback)
            self.assertTrue(baseline_ready.wait(2))
            shutdown = threading.Thread(target=self.manager.shutdown, kwargs={"timeout": 0})
            shutdown.start()
            shutdown.join(timeout=2)
            self.assertFalse(shutdown.is_alive())
            release_baseline.set()
            completed = self.manager.wait(job["id"], timeout=2)

        self.assertFalse(callback_called.is_set())
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
