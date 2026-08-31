from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tools.studio import cli
from tools.studio.shot_orchestration import (
    ShotProjectError,
    ShotProjectValidationError,
    load_shot_project_request,
    run_shot_project,
    validate_shot_project_request,
)


PRODUCTION_ID = "production_" + "a" * 32
PROJECT_ID = "shotproj_" + "b" * 32
RECIPE_ID = "announcement_" + "c" * 32


def i2va_prompt(action: str) -> str:
    return (
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        "integrated_multimodal_description: [Shot 1] Live-action, cinematic, "
        f"the person in <Picture 1> preserves identity and clothing, then {action}. "
        "The camera pushes in with small amplitude at slow speed.\n\n"
        "overall_soundscape: Quiet room tone with subtle clothing movement.\n\n"
        "non_diegetic_music: N/A"
    )


def recipe() -> dict[str, object]:
    scenes = []
    for role, index, headline, end_ms in zip(
        ("hook", "message", "cta"),
        (0, 1, 2),
        ("新しい一歩", "映像で伝える", "今すぐ確認"),
        (5_167, 5_167, 5_166),
        strict=True,
    ):
        scenes.append(
            {
                "role": role,
                "video_index": index,
                "start_ms": 0,
                "end_ms": end_ms,
                "volume_percent": 0,
                "headline": headline,
                "narration": f"{role} の案内です。",
                "visual_preset": "preserve_v1",
            }
        )
    return {
        "schema_version": 1,
        "name": "I2VA 三カット告知",
        "template_preset": "shorts_ja_15s_v1",
        "scenes": scenes,
        "voice": None,
        "rate": 0,
        "pronunciations": [],
        "include_captioned": True,
        "caption_style_preset": "shorts_ja_large_v1",
        "audio_mix_preset": "narration_only_v1",
        "variant": "captioned",
    }


def request_value(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "production": {"id": PRODUCTION_ID, "title": "三カット制作"},
        "shots": [
            {
                "shot_id": f"shot_{index}",
                "first_frame_path": f"frame-{index}.png",
                "first_frame_prompt": f"日本人の出演者、縦型CM、カット{index}の始点",
                "video_prompt": i2va_prompt(
                    ("turns toward the camera", "raises one hand", "smiles gently")[index - 1]
                ),
                "duration_seconds": 6,
                "resolution": "768P",
            }
            for index in range(1, 4)
        ],
        "recipe_id": RECIPE_ID,
        "expected_revision": 0,
        "recipe": recipe(),
        "timeout_seconds": 600,
        "confirmed_billable_task_limit": 3,
    }
    value.update(updates)
    return value


class FakeH3Client:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []
        self.status_calls: list[str] = []
        self.download_calls: list[str] = []

    def submit(self, payload: dict[str, object]) -> dict[str, str]:
        self.submissions.append(payload)
        return {"task_id": f"task-{len(self.submissions)}"}

    def status(self, task_id: str) -> dict[str, object]:
        self.status_calls.append(task_id)
        return {
            "task": {
                "id": task_id,
                "model": "MiniMax-H3",
                "status": "succeeded",
                "content": {"url": f"https://media.example/{task_id}.mp4"},
            }
        }

    def download(self, url: str, output: Path, *, overwrite: bool = False) -> int:
        self.download_calls.append(url)
        self.assert_output_available(output, overwrite)
        payload = b"\x00\x00\x00\x18ftypmp42" + url.encode("ascii")
        output.write_bytes(payload)
        return len(payload)

    @staticmethod
    def assert_output_available(output: Path, overwrite: bool) -> None:
        if output.exists() and not overwrite:
            raise AssertionError("output unexpectedly exists")


class ShotProjectValidationTests(unittest.TestCase):
    def test_exact_i2va_contract_and_three_cut_recipe_are_normalized(self) -> None:
        normalized = validate_shot_project_request(request_value())
        self.assertEqual(normalized["project_id"], PROJECT_ID)
        self.assertEqual([shot["shot_id"] for shot in normalized["shots"]], ["shot_1", "shot_2", "shot_3"])
        self.assertEqual(
            [scene["video_index"] for scene in normalized["recipe"]["scenes"]],
            [0, 1, 2],
        )

    def test_prompt_preset_billing_and_schema_drift_fail_closed(self) -> None:
        invalid: list[dict[str, object]] = []
        invalid.append({**request_value(), "extra": True})
        invalid.append(request_value(confirmed_billable_task_limit=2))
        wrong_prompt = request_value()
        wrong_prompt["shots"][0]["video_prompt"] = "Animate this image"
        invalid.append(wrong_prompt)
        wrong_duration = request_value()
        wrong_duration["shots"][1]["duration_seconds"] = 7
        invalid.append(wrong_duration)
        wrong_order = request_value()
        wrong_order["shots"][0]["shot_id"] = "shot_2"
        invalid.append(wrong_order)
        for value in invalid:
            with self.subTest(keys=tuple(value)), self.assertRaises(ShotProjectValidationError):
                validate_shot_project_request(value)

    def test_loader_rejects_duplicate_keys_without_reflecting_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private-shot-plan.json"
            encoded = json.dumps(request_value(), ensure_ascii=False, separators=(",", ":"))
            encoded = encoded.replace('"expected_revision":0', '"expected_revision":0,"expected_revision":0')
            path.write_text(encoded, encoding="utf-8")
            with self.assertRaises(ShotProjectValidationError) as raised:
                load_shot_project_request(path)
        self.assertNotIn(str(path), str(raised.exception))


class ShotProjectExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.request_parent = self.workspace / "inputs"
        self.request_parent.mkdir()
        for index in range(1, 4):
            (self.request_parent / f"frame-{index}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n" + bytes([index])
            )
        self.client = FakeH3Client()
        self.quick_requests: list[dict[str, object]] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def client_factory(self, key: str, base: str) -> FakeH3Client:
        self.assertEqual(key, "secret-key")
        self.assertEqual(base, "https://api.minimax.io")
        return self.client

    def quick_runner(
        self,
        service: object,
        value: dict[str, object],
        **kwargs: object,
    ) -> dict[str, object]:
        self.assertEqual(service, "service")
        parent = kwargs["request_parent"]
        self.assertIsInstance(parent, Path)
        self.assertTrue(all((parent / item["path"]).is_file() for item in value["videos"]))
        self.quick_requests.append(value)
        return {"schema_version": 1, "status": "succeeded"}

    def execute_project(self) -> dict[str, object]:
        return run_shot_project(
            "service",
            request_value(),
            workspace=self.workspace,
            request_parent=self.request_parent,
            api_key="secret-key",
            client_factory=self.client_factory,
            quick_create_runner=self.quick_runner,
            sleep=lambda _seconds: None,
        )

    def test_three_independent_i2va_tasks_feed_quick_create_and_resume_without_resubmit(self) -> None:
        first = self.execute_project()
        self.assertEqual(first["submitted_tasks"], 3)
        self.assertFalse(first["resumed"])
        self.assertEqual(len(self.client.submissions), 3)
        plan_path = (
            self.workspace
            / "outputs"
            / "studio"
            / "shot_projects"
            / PROJECT_ID
            / "plan.json"
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(plan["generation"]["mode"], "i2va")
        self.assertEqual(
            plan["shots"][0]["first_frame"]["sha256"],
            hashlib.sha256((self.request_parent / "frame-1.png").read_bytes())
            .hexdigest()
            .upper(),
        )
        self.assertNotIn("secret-key", plan_path.read_text(encoding="utf-8"))
        for payload in self.client.submissions:
            self.assertEqual(payload["model"], "MiniMax-H3")
            self.assertEqual(payload["duration"], 6)
            self.assertEqual(payload["resolution"], "768P")
            self.assertEqual(payload["ratio"], "adaptive")
            self.assertEqual(payload["content"][1]["role"], "first_frame")
        second = self.execute_project()
        self.assertEqual(second["submitted_tasks"], 0)
        self.assertTrue(second["resumed"])
        self.assertEqual(len(self.client.submissions), 3)
        self.assertEqual(len(self.quick_requests), 2)

    def test_changed_first_frame_conflicts_before_provider_submission(self) -> None:
        self.execute_project()
        (self.request_parent / "frame-2.png").write_bytes(
            b"\x89PNG\r\n\x1a\nchanged"
        )
        with self.assertRaisesRegex(ShotProjectError, "shot_project_request_conflict"):
            self.execute_project()
        self.assertEqual(len(self.client.submissions), 3)

    def test_missing_credential_fails_before_state_or_provider_work(self) -> None:
        with self.assertRaisesRegex(ShotProjectError, "minimax_credential_missing"):
            run_shot_project(
                "service",
                request_value(),
                workspace=self.workspace,
                request_parent=self.request_parent,
                api_key="",
                client_factory=self.client_factory,
                quick_create_runner=self.quick_runner,
            )
        self.assertFalse((self.workspace / "outputs").exists())
        self.assertEqual(self.client.submissions, [])

    def test_uncertain_submit_is_durable_and_never_retried_automatically(self) -> None:
        class UncertainClient(FakeH3Client):
            def submit(self, payload: dict[str, object]) -> dict[str, str]:
                self.submissions.append(payload)
                raise OSError("response lost")

        uncertain = UncertainClient()

        def uncertain_factory(_key: str, _base: str) -> UncertainClient:
            return uncertain

        with self.assertRaises(ShotProjectError):
            run_shot_project(
                "service",
                request_value(),
                workspace=self.workspace,
                request_parent=self.request_parent,
                api_key="secret-key",
                client_factory=uncertain_factory,
                quick_create_runner=self.quick_runner,
            )
        self.assertEqual(len(uncertain.submissions), 1)
        with self.assertRaisesRegex(ShotProjectError, "shot_submission_ambiguous"):
            run_shot_project(
                "service",
                request_value(),
                workspace=self.workspace,
                request_parent=self.request_parent,
                api_key="secret-key",
                client_factory=uncertain_factory,
                quick_create_runner=self.quick_runner,
            )
        self.assertEqual(len(uncertain.submissions), 1)


class ShotProjectCliTests(unittest.TestCase):
    def test_missing_minimax_secret_fails_without_starting_service_or_leaking_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            request_file = workspace / "private-plan.json"
            request_file.write_text("{}", encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            with (
                mock.patch.object(cli, "load_shot_project_request", return_value=request_value()),
                mock.patch.object(cli, "WorkspaceInstanceLock") as lock_type,
                mock.patch.object(cli.SecretStore, "resolve", return_value=None),
                mock.patch.object(cli, "StudioService") as service_type,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    [
                        "--workspace",
                        str(workspace),
                        "shot-project",
                        str(request_file),
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("minimax_credential_missing", stderr.getvalue())
        self.assertNotIn(str(request_file), stderr.getvalue())
        service_type.assert_not_called()
        lock_type.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
