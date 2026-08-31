from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.studio import cli
from tools.studio.quick_create import (
    QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS,
    QUICK_CREATE_MAX_TIMEOUT_SECONDS,
    QuickCreateError,
    QuickCreateQcNonPass,
    QuickCreateValidationError,
    load_quick_create_request,
    run_quick_create,
    validate_quick_create_request,
)


PRODUCTION_ID = "production-quick-create"
RECIPE_ID = "announcement_" + "1" * 32
RECIPE_VERSION_ID = "annv_" + "2" * 32
JOB_ID = "job_" + "3" * 32
RUN_ID = "run_" + "4" * 32
REVISION_ID = "rev_" + "5" * 32
REQUEST_KEY = "A" * 64


def recipe(*, narration: str = "安全に、すばやく始められます。") -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "新サービス告知",
        "template_preset": "shorts_ja_15s_v1",
        "scenes": [
            {
                "role": "hook",
                "video_artifact_id": "art_" + "a" * 32,
                "start_ms": 0,
                "end_ms": 4_000,
                "volume_percent": 0,
                "headline": "新しい体験",
                "narration": narration,
                "visual_preset": "preserve_v1",
            },
            {
                "role": "message",
                "video_artifact_id": "art_" + "b" * 32,
                "start_ms": 0,
                "end_ms": 4_000,
                "volume_percent": 0,
                "headline": "かんたん操作",
                "narration": "三つの場面を選ぶだけです。",
                "visual_preset": "preserve_v1",
            },
            {
                "role": "cta",
                "video_artifact_id": "art_" + "c" * 32,
                "start_ms": 0,
                "end_ms": 4_000,
                "volume_percent": 0,
                "headline": "今すぐ確認",
                "narration": "完成した動画を確認してください。",
                "visual_preset": "preserve_v1",
            },
        ],
        "voice": None,
        "rate": 0,
        "pronunciations": [],
        "include_captioned": True,
        "caption_style_preset": "shorts_ja_large_v1",
        "audio_mix_preset": "narration_only_v1",
        "variant": "captioned",
    }


def request(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "production_id": PRODUCTION_ID,
        "recipe_id": RECIPE_ID,
        "expected_revision": 0,
        "recipe": recipe(),
    }
    value.update(updates)
    return value


def saved(*, deduplicated: bool = False) -> dict[str, object]:
    return {
        "id": RECIPE_ID,
        "version_id": RECIPE_VERSION_ID,
        "production_id": PRODUCTION_ID,
        "revision": 1,
        "deduplicated": deduplicated,
        "recipe": recipe(),
    }


def submitted(*, deduplicated: bool = False) -> dict[str, object]:
    link = {
        "production_id": PRODUCTION_ID,
        "recipe_id": RECIPE_ID,
        "recipe_version_id": RECIPE_VERSION_ID,
        "recipe_revision": 1,
        "job_id": JOB_ID,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_key": REQUEST_KEY,
    }
    return {
        "id": JOB_ID,
        "kind": "detailed_test_video",
        "status": "queued",
        "production_id": PRODUCTION_ID,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_key": REQUEST_KEY,
        "deduplicated": deduplicated,
        "announcement_recipe_id": RECIPE_ID,
        "announcement_recipe_version_id": RECIPE_VERSION_ID,
        "announcement_recipe_revision": 1,
        "announcement_execution": link,
    }


def artifact(index: int, name: str) -> dict[str, object]:
    stage = "assembly" if name.startswith("master-") else "qc"
    return {
        "id": f"artifact_{index:032x}",
        "name": name,
        "rel_path": (
            f"outputs/studio/runs/{RUN_ID}/{stage}/{'B' * 64}/{name}"
        ),
        "bytes": 1_000 + index,
        "sha256": f"{index:064x}".upper(),
    }


def success_result() -> dict[str, object]:
    children = {
        stage: {
            "stage": stage,
            "status": "succeeded",
            "job_id": f"job_{index:032x}",
            "stage_attempt_id": f"attempt_{index:032x}",
            "cache_hit": index % 2 == 0,
        }
        for index, stage in enumerate(
            ("narration", "timeline", "assembly", "qc"), start=10
        )
    }
    reports = [
        artifact(22, "technical-qc.json"),
        artifact(23, "ffprobe.json"),
        artifact(24, "manifest.json"),
    ]
    return {
        "schema_version": 1,
        "production_id": PRODUCTION_ID,
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "request_key": REQUEST_KEY,
        "technical_verdict": "pass",
        "children": children,
        "master": artifact(21, "master-captioned.mp4"),
        "qc": {"verdict": "pass", "report_artifacts": reports},
    }


def terminal(
    status: str,
    *,
    result: object = None,
    error: object = None,
) -> dict[str, object]:
    return {
        "id": JOB_ID,
        "kind": "detailed_test_video",
        "status": status,
        "production_id": PRODUCTION_ID,
        "payload": {
            "production_id": PRODUCTION_ID,
            "run_id": RUN_ID,
            "revision_id": REVISION_ID,
            "request_key": REQUEST_KEY,
            "stage": "detailed_test_video",
        },
        "result": result,
        "error": error,
    }


def service_with_job(*jobs: dict[str, object]) -> mock.Mock:
    service = mock.Mock()
    service.save_announcement_recipe.return_value = saved()
    service.execute_announcement_recipe.return_value = submitted()
    service.job.side_effect = list(jobs)
    return service


class QuickCreateRequestTests(unittest.TestCase):
    def test_exact_schema_normalizes_default_timeout(self) -> None:
        normalized = validate_quick_create_request(request())
        self.assertEqual(
            normalized["timeout_seconds"], QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS
        )
        self.assertEqual(normalized["recipe_id"], RECIPE_ID)
        self.assertEqual(normalized["recipe"]["scenes"][0]["role"], "hook")

    def test_schema_timeout_and_extra_fields_fail_closed(self) -> None:
        invalid_values = [
            request(schema_version=True),
            request(schema_version=1.0),
            request(schema_version=2),
            request(timeout_seconds=True),
            request(timeout_seconds=0),
            request(timeout_seconds=QUICK_CREATE_MAX_TIMEOUT_SECONDS + 1),
            request(output_path="C:\\private\\master.mp4"),
            request(recipe_id="generated-at-runtime"),
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                QuickCreateValidationError
            ):
                validate_quick_create_request(value)

    def test_loader_rejects_duplicate_keys_and_never_echoes_input(self) -> None:
        secret = "Bearer top-secret-narration"
        value = request(recipe=recipe(narration=secret))
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        encoded = encoded.replace(
            '"expected_revision":0',
            '"expected_revision":0,"expected_revision":0',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private-request.json"
            path.write_text(encoded, encoding="utf-8")
            with self.assertRaises(QuickCreateValidationError) as raised:
                load_quick_create_request(path)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(str(path), str(raised.exception))


class QuickCreateExecutionTests(unittest.TestCase):
    def test_save_execute_and_low_frequency_poll_emit_redacted_summary(self) -> None:
        secret = "秘密のナレーションです"
        value = request(recipe=recipe(narration=secret), timeout_seconds=10)
        service = service_with_job(
            terminal("running"),
            terminal("succeeded", result=success_result()),
        )
        service.save_announcement_recipe.return_value = {
            **saved(),
            "recipe": validate_quick_create_request(value)["recipe"],
        }
        sleeps: list[float] = []

        summary = run_quick_create(
            service,
            value,
            monotonic=lambda: 100.0,
            sleep=sleeps.append,
        )

        service.save_announcement_recipe.assert_called_once_with(
            PRODUCTION_ID,
            RECIPE_ID,
            {
                "schema_version": 1,
                "expected_revision": 0,
                "recipe": validate_quick_create_request(value)["recipe"],
            },
        )
        service.execute_announcement_recipe.assert_called_once_with(
            PRODUCTION_ID,
            RECIPE_ID,
            {"schema_version": 1, "revision": 1},
        )
        self.assertEqual(service.job.call_count, 2)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["technical_verdict"], "pass")
        self.assertEqual(set(summary["children"]), {"narration", "timeline", "assembly", "qc"})
        self.assertEqual(summary["master"]["name"], "master-captioned.mp4")
        self.assertEqual(summary["qc"]["verdict"], "pass")
        self.assertEqual(len(summary["qc"]["report_artifacts"]), 3)
        encoded = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("C:\\", encoded)

    def test_same_request_retry_preserves_recipe_and_job_deduplication(self) -> None:
        service = service_with_job(terminal("succeeded", result=success_result()))
        service.save_announcement_recipe.return_value = saved(deduplicated=True)
        service.execute_announcement_recipe.return_value = submitted(
            deduplicated=True
        )

        summary = run_quick_create(
            service,
            request(),
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: None,
        )

        self.assertTrue(summary["recipe_deduplicated"])
        self.assertTrue(summary["job_deduplicated"])
        self.assertEqual(summary["recipe_version_id"], RECIPE_VERSION_ID)
        self.assertEqual(summary["job_id"], JOB_ID)

    def test_non_qc_job_failure_is_safe_and_terminal(self) -> None:
        secret = "C:\\private\\worker-secret.txt"
        service = service_with_job(
            terminal(
                "failed",
                error={
                    "code": "local_remotion_render_failed",
                    "message": secret,
                },
            )
        )
        with self.assertRaises(QuickCreateError) as raised:
            run_quick_create(
                service,
                request(),
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: None,
            )
        self.assertNotIsInstance(raised.exception, QuickCreateQcNonPass)
        self.assertEqual(raised.exception.code, "local_remotion_render_failed")
        self.assertNotIn(secret, json.dumps(raised.exception.context))

    def test_qc_non_pass_has_distinct_failure(self) -> None:
        service = service_with_job(
            terminal(
                "failed",
                error={
                    "code": "technical_qc_failed",
                    "message": "C:\\private\\qc-report.json",
                },
            )
        )
        with self.assertRaises(QuickCreateQcNonPass) as raised:
            run_quick_create(
                service,
                request(),
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: None,
            )
        self.assertEqual(raised.exception.code, "technical_qc_failed")
        self.assertEqual(raised.exception.context["status"], "failed")

    def test_timeout_uses_shared_deadline_and_leaves_durable_id(self) -> None:
        service = service_with_job(terminal("running"), terminal("running"))
        now = [0.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        with self.assertRaises(QuickCreateError) as raised:
            run_quick_create(
                service,
                request(timeout_seconds=10),
                monotonic=lambda: now[0],
                sleep=sleep,
                deadline=2.0,
            )
        self.assertEqual(raised.exception.code, "quick_create_timeout")
        self.assertEqual(raised.exception.context["job_id"], JOB_ID)
        self.assertEqual(raised.exception.context["status"], "running")
        self.assertEqual(sleeps, [2.0])

    def test_missing_qc_verdict_is_malformed_job_not_qc_non_pass(self) -> None:
        result = success_result()
        result["qc"] = {"report_artifacts": result["qc"]["report_artifacts"]}
        service = service_with_job(terminal("succeeded", result=result))
        with self.assertRaises(QuickCreateError) as raised:
            run_quick_create(
                service,
                request(),
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: None,
            )
        self.assertNotIsInstance(raised.exception, QuickCreateQcNonPass)
        self.assertEqual(raised.exception.code, "invalid_quick_create_result")

    def test_absolute_artifact_path_is_rejected_without_echo(self) -> None:
        result = success_result()
        result["master"] = {
            **result["master"],
            "rel_path": "C:\\private\\master-captioned.mp4",
        }
        service = service_with_job(terminal("succeeded", result=result))
        with self.assertRaises(QuickCreateError) as raised:
            run_quick_create(
                service,
                request(),
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: None,
            )
        self.assertEqual(raised.exception.code, "invalid_quick_create_result")
        self.assertNotIn("C:\\private", json.dumps(raised.exception.context))


class QuickCreateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.input_path = self.workspace / "request.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _argv(self) -> list[str]:
        return [
            "--workspace",
            str(self.workspace),
            "quick-create",
            str(self.input_path),
        ]

    def test_parser_accepts_one_file_and_no_timeout_flag(self) -> None:
        parsed = cli.build_parser().parse_args(self._argv())
        self.assertEqual(parsed.command, "quick-create")
        self.assertEqual(parsed.request_file, self.input_path)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args([*self._argv(), "--timeout-seconds", "5"])
        self.assertEqual(raised.exception.code, 2)

    def test_lock_conflict_returns_two_without_constructing_service(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        private_path = "C:\\private\\studio.instance.lock"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(
                cli,
                "WorkspaceInstanceLock",
                side_effect=cli.StudioInstanceLockError(private_path),
            ),
            mock.patch.object(cli, "StudioService") as service_factory,
            mock.patch.object(cli.time, "monotonic", return_value=10.0),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())
        self.assertEqual(exit_code, 2)
        service_factory.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "workspace_in_use")
        self.assertNotIn(private_path, stderr.getvalue())

    def test_cold_index_refresh_precedes_save_and_consumes_timeout_budget(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-job"}
        state = {"indexed": False}

        def finish_refresh(job_id: str, *, timeout: float) -> dict[str, object]:
            self.assertEqual(job_id, "refresh-job")
            self.assertEqual(timeout, 4.0)
            state["indexed"] = True
            return {"id": job_id, "status": "succeeded"}

        service.jobs.wait.side_effect = finish_refresh
        expected = {"schema_version": 1, "status": "succeeded"}

        def runner(
            selected_service: object,
            selected_request: object,
            *,
            deadline: float,
        ) -> dict[str, object]:
            self.assertIs(selected_service, service)
            self.assertEqual(selected_request, value)
            self.assertTrue(state["indexed"], "save/execute ran against a cold index")
            self.assertEqual(deadline, 105.0)
            return expected

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_quick_create", side_effect=runner) as run,
            mock.patch.object(cli.time, "monotonic", side_effect=(100.0, 101.0)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 0)
        service.refresh_index.assert_called_once_with()
        self.assertEqual(run.call_count, 1)
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(stderr.getvalue(), "")

    def test_real_cold_database_is_indexed_before_runner(self) -> None:
        production = self.workspace / "productions" / PRODUCTION_ID
        production.mkdir(parents=True)
        (production / "PRODUCTION_RECORD_JA.md").write_text(
            f"# {PRODUCTION_ID}\n",
            encoding="utf-8",
        )
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        expected = {"schema_version": 1, "status": "succeeded"}

        def runner(
            service: object,
            selected_request: object,
            *,
            deadline: float,
        ) -> dict[str, object]:
            del deadline
            self.assertEqual(selected_request, value)
            self.assertIsNotNone(service.database.get_production(PRODUCTION_ID))
            return expected

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "run_quick_create", side_effect=runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 0)
        lock.close.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(stderr.getvalue(), "")

    def test_refresh_failure_skips_quick_create_and_returns_two(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-job"}
        service.jobs.wait.return_value = {"id": "refresh-job", "status": "failed"}
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_quick_create") as run,
            mock.patch.object(cli.time, "monotonic", side_effect=(10.0, 10.0)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())
        self.assertEqual(exit_code, 2)
        run.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            json.loads(stderr.getvalue())["error"]["code"], "index_refresh_failed"
        )
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_qc_non_pass_returns_three_with_only_safe_context(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-job"}
        service.jobs.wait.return_value = {"id": "refresh-job", "status": "succeeded"}
        error = QuickCreateQcNonPass(
            "technical_qc_failed",
            context={
                "production_id": PRODUCTION_ID,
                "job_id": JOB_ID,
                "status": "failed",
                "unsafe": "C:\\private\\narration.txt",
            },
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_quick_create", side_effect=error),
            mock.patch.object(cli.time, "monotonic", side_effect=(10.0, 10.0)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())
        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "technical_qc_failed")
        self.assertEqual(payload["job_id"], JOB_ID)
        self.assertNotIn("unsafe", payload)
        self.assertNotIn("C:\\private", stderr.getvalue())

    def test_timeout_returns_two_with_durable_job_context(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-job"}
        service.jobs.wait.return_value = {
            "id": "refresh-job",
            "status": "succeeded",
        }
        error = QuickCreateError(
            "quick_create_timeout",
            context={
                "production_id": PRODUCTION_ID,
                "job_id": JOB_ID,
                "status": "running",
                "unsafe": "C:\\private\\narration.txt",
            },
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_request", return_value=value),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_quick_create", side_effect=error),
            mock.patch.object(cli.time, "monotonic", side_effect=(10.0, 10.0)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "quick_create_timeout")
        self.assertEqual(payload["job_id"], JOB_ID)
        self.assertEqual(payload["status"], "running")
        self.assertNotIn("C:\\private", stderr.getvalue())
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_timeout_returns_two_and_close_failure_retains_workspace_lock(self) -> None:
        value = validate_quick_create_request(request(timeout_seconds=5))
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-job"}
        service.jobs.wait.return_value = {"id": "refresh-job", "status": "succeeded"}
        service.close.side_effect = RuntimeError("C:\\private\\worker")
        retained_before = list(cli._RETAINED_INSTANCE_LOCKS)
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with (
                mock.patch.object(cli, "load_quick_create_request", return_value=value),
                mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
                mock.patch.object(cli, "StudioService", return_value=service),
                mock.patch.object(
                    cli,
                    "run_quick_create",
                    side_effect=QuickCreateError(
                        "quick_create_timeout",
                        context={"job_id": JOB_ID, "status": "running"},
                    ),
                ),
                mock.patch.object(cli.time, "monotonic", side_effect=(10.0, 10.0)),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = cli.main(self._argv())
            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(stderr.getvalue())
            self.assertEqual(payload["error"]["code"], "process_interrupted")
            self.assertNotIn("C:\\private", stderr.getvalue())
            lock.close.assert_not_called()
            self.assertIs(cli._RETAINED_INSTANCE_LOCKS[-1], lock)
        finally:
            cli._RETAINED_INSTANCE_LOCKS[:] = retained_before


if __name__ == "__main__":
    unittest.main()
