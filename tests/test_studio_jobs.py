from __future__ import annotations

import subprocess
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
        self.assertEqual(self.manager.wait(default_job["id"], timeout=1)["status"], "interrupted")
        self.assertEqual(self.manager.wait(gpu_job["id"], timeout=1)["status"], "interrupted")

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
