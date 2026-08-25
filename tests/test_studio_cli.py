from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.studio import cli
from tools.studio.test_video import TestVideoError


class StudioCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _argv(self, *extra: str) -> list[str]:
        return [
            "--workspace",
            str(self.workspace),
            "test-video",
            "--production-id",
            "production-1",
            "--video-artifact-id",
            "artifact-1",
            "--segment",
            "one",
            "--segment",
            "two",
            "--end-ms",
            "1500",
            *extra,
        ]

    def _mock_runtime(self) -> tuple[mock.Mock, mock.Mock, mock.Mock]:
        lock = mock.Mock()
        service = mock.Mock()
        service.refresh_index.return_value = {"id": "refresh-1"}
        service.jobs.wait.return_value = {"id": "refresh-1", "status": "succeeded"}
        runner = mock.Mock(return_value={"status": "succeeded", "technical_verdict": "pass"})
        return lock, service, runner

    def test_success_waits_for_refresh_and_passes_bounded_request(self) -> None:
        lock, service, runner = self._mock_runtime()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock) as lock_factory,
            mock.patch.object(cli, "StudioService", return_value=service) as service_factory,
            mock.patch.object(cli, "run_test_video", runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                self._argv(
                    "--voice",
                    "Voice",
                    "--rate",
                    "2",
                    "--pronunciation",
                    "H3=エイチスリー",
                    "--start-ms",
                    "100",
                    "--variant",
                    "clean",
                    "--timeout-seconds",
                    "7",
                )
            )

        self.assertEqual(exit_code, 0)
        lock_factory.assert_called_once_with(self.workspace)
        service_factory.assert_called_once_with(self.workspace)
        service.refresh_index.assert_called_once_with()
        service.jobs.wait.assert_called_once_with("refresh-1", timeout=7)
        request = runner.call_args.args[1]
        self.assertEqual(request["production_id"], "production-1")
        self.assertEqual(request["video_artifact_id"], "artifact-1")
        self.assertEqual(request["segments"], [{"text": "one"}, {"text": "two"}])
        self.assertEqual(request["voice"], "Voice")
        self.assertEqual(request["rate"], 2)
        self.assertEqual(
            request["pronunciations"], [{"source": "H3", "target": "エイチスリー"}]
        )
        self.assertEqual(request["start_ms"], 100)
        self.assertEqual(request["end_ms"], 1500)
        self.assertEqual(request["variant"], "clean")
        self.assertEqual(request["timeout_seconds"], 7)
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(stdout.getvalue())["technical_verdict"], "pass")

    def test_defaults_and_required_arguments_are_argparse_contract(self) -> None:
        parsed = cli.build_parser().parse_args(
            self._argv()[2:]
        )
        self.assertEqual(parsed.voice, "Microsoft Haruka Desktop")
        self.assertEqual(parsed.rate, 0)
        self.assertEqual(parsed.start_ms, 0)
        self.assertEqual(parsed.variant, "captioned")
        self.assertEqual(parsed.timeout_seconds, 600)

        missing_end = self._argv()[:-2]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(missing_end)
        self.assertEqual(raised.exception.code, 2)

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli.build_parser().parse_args(
                self._argv("--api-key", "raw-secret", "--path", "C:\\private")
            )
        self.assertEqual(raised.exception.code, 2)

    def test_lock_conflict_is_fixed_and_does_not_create_service(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        secret_path = "C:\\private\\secret-token"
        with (
            mock.patch.object(
                cli,
                "WorkspaceInstanceLock",
                side_effect=cli.StudioInstanceLockError(secret_path),
            ),
            mock.patch.object(cli, "StudioService") as service_factory,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(secret_path, stderr.getvalue())
        self.assertIn("workspace is already in use", stderr.getvalue())
        service_factory.assert_not_called()

    def test_validation_failure_is_redacted_and_cleanup_runs(self) -> None:
        lock, service, runner = self._mock_runtime()
        secret_path = "C:\\private\\source.mp4"
        runner.side_effect = TestVideoError("invalid_test_video_request", secret_path)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_test_video", runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn(secret_path, stderr.getvalue())
        error = json.loads(stderr.getvalue())
        self.assertEqual(error["error"]["code"], "invalid_test_video_request")
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_refresh_failure_skips_runner_and_cleans_up(self) -> None:
        lock, service, runner = self._mock_runtime()
        service.jobs.wait.return_value = {"id": "refresh-1", "status": "failed"}
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_test_video", runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 2)
        runner.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "index_refresh_failed")
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_technical_qc_failure_returns_three_with_bounded_result(self) -> None:
        lock, service, _runner = self._mock_runtime()
        runner = mock.Mock(
            return_value={
                "status": "succeeded",
                "technical_verdict": "fail",
                "artifacts": [{"name": "master-captioned.mp4"}],
            }
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_test_video", runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "technical_qc_failed")
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_keyboard_interrupt_returns_130_and_cleans_up(self) -> None:
        lock, service, runner = self._mock_runtime()
        runner.side_effect = KeyboardInterrupt()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_test_video", runner),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self._argv())

        self.assertEqual(exit_code, 130)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "process_interrupted")
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_close_failure_retains_workspace_lock_and_suppresses_success(self) -> None:
        lock, service, runner = self._mock_runtime()
        service.close.side_effect = RuntimeError("worker still draining")
        stdout = io.StringIO()
        stderr = io.StringIO()
        retained_before = list(cli._RETAINED_INSTANCE_LOCKS)
        try:
            with (
                mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
                mock.patch.object(cli, "StudioService", return_value=service),
                mock.patch.object(cli, "run_test_video", runner),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = cli.main(self._argv())

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                json.loads(stderr.getvalue())["error"]["code"],
                "process_interrupted",
            )
            service.close.assert_called_once_with()
            lock.close.assert_not_called()
            self.assertIs(cli._RETAINED_INSTANCE_LOCKS[-1], lock)
        finally:
            cli._RETAINED_INSTANCE_LOCKS[:] = retained_before

    def test_secret_status_remains_flags_only(self) -> None:
        store = mock.Mock()
        store.statuses.return_value = [
            {"id": "openai", "configured": True},
            {"id": "minimax", "configured": False},
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "SecretStore", return_value=store),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                ["--workspace", str(self.workspace), "secret", "status", "openai"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {"providers": [{"id": "openai", "configured": True}]},
        )
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
