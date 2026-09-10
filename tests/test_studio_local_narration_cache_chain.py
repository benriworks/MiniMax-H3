"""Local SAPI cache lineage regression tests; temporary workspaces only."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

from tests.test_studio_backend import (
    PRODUCTION_ID,
    WorkspaceFixture,
    fake_local_narration_result,
)
from tools.studio.service import StudioService


class LocalNarrationCacheChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def _three_runs(self) -> tuple[list[dict], int]:
        attempts = []
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ) as worker:
            for _ in range(3):
                run_id = self.service.create_run(
                    PRODUCTION_ID,
                    {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
                )["run"]["id"]
                job = self.service.execute_local_narration(
                    run_id,
                    {"segments": [{"text": "same local narration"}], "voice": "Microsoft Sayaka", "rate": 0},
                )
                completed = self.service.jobs.wait(job["id"], timeout=10)
                self.assertIsNotNone(completed)
                self.assertEqual(completed["status"], "succeeded", completed)
                attempts.append(self.service.database.get_stage_attempt(job["stage_attempt_id"]))
            return attempts, worker.call_count

    def _lookup(self, attempts: list[dict]) -> dict | None:
        by_id = {item["id"]: item for item in attempts}
        with (
            mock.patch.object(self.service.database, "find_successful_stage_attempt", return_value=attempts[-1]),
            mock.patch.object(self.service.database, "get_stage_attempt", side_effect=by_id.get),
        ):
            return self.service._cached_local_narration_result(attempts[0]["cache_key"], PRODUCTION_ID)

    def test_three_runs_reuse_one_worker_and_the_same_four_artifacts(self) -> None:
        attempts, calls = self._three_runs()
        self.assertEqual(calls, 1)
        self.assertEqual([item["result"]["cache_hit"] for item in attempts], [False, True, True])
        self.assertEqual(attempts[2]["result"]["cache_source_attempt_id"], attempts[1]["id"])
        self.assertEqual(attempts[1]["result"]["cache_source_attempt_id"], attempts[0]["id"])
        for attempt in attempts[1:]:
            self.assertEqual(attempt["result"]["artifacts"], attempts[0]["result"]["artifacts"])
            self.assertFalse((self.fixture.root / "outputs/studio/runs" / attempt["run_id"] / "narration").exists())
        self.assertIsNotNone(self._lookup(attempts))

    def test_every_link_must_be_same_production_stage_key_and_successful(self) -> None:
        attempts, _ = self._three_runs()
        for index in range(3):
            for field, invalid in (
                ("production_id", "OTHER_PRODUCTION"),
                ("stage", "external_narration"),
                ("cache_key", "F" * 64),
                ("status", "failed"),
                ("run_id", "../escape"),
            ):
                with self.subTest(link=index, field=field):
                    altered = copy.deepcopy(attempts)
                    altered[index][field] = invalid
                    self.assertIsNone(self._lookup(altered))

    def test_missing_invalid_and_cyclic_source_links_are_rejected(self) -> None:
        attempts, _ = self._three_runs()
        for invalid in (None, "", 7, {}, "../bad", "attempt_missing", attempts[-1]["id"]):
            with self.subTest(source=invalid):
                altered = copy.deepcopy(attempts)
                altered[-1]["result"]["cache_source_attempt_id"] = invalid
                self.assertIsNone(self._lookup(altered))
        altered = copy.deepcopy(attempts)
        altered[1]["result"]["cache_source_attempt_id"] = altered[2]["id"]
        self.assertIsNone(self._lookup(altered))
        altered = copy.deepcopy(attempts)
        altered[2]["result"]["cache_hit"] = False
        self.assertIsNone(self._lookup(altered))

    def test_every_link_artifact_identity_must_match(self) -> None:
        attempts, _ = self._three_runs()
        for index in range(3):
            for field, invalid in (
                ("id", "art_unknown"),
                ("bytes", 999),
                ("sha256", "F" * 64),
                ("rel_path", "outputs/unrelated/narration.wav"),
                ("name", "wrong.wav"),
            ):
                with self.subTest(link=index, field=field):
                    altered = copy.deepcopy(attempts)
                    altered[index]["result"]["artifacts"][0][field] = invalid
                    self.assertIsNone(self._lookup(altered))
            with self.subTest(link=index, field="duplicate"):
                altered = copy.deepcopy(attempts)
                altered[index]["result"]["artifacts"][1] = copy.deepcopy(altered[index]["result"]["artifacts"][0])
                self.assertIsNone(self._lookup(altered))

    def test_every_link_result_metadata_is_validated(self) -> None:
        attempts, _ = self._three_runs()
        for index in range(3):
            for field, invalid in (
                ("provider", "external_tts"),
                ("cache_key", "F" * 64),
                ("cache_hit", "true"),
                ("duration_ms", True),
                ("actual_cost", 1),
                ("provider_task_id", "external_task"),
            ):
                with self.subTest(link=index, field=field):
                    altered = copy.deepcopy(attempts)
                    altered[index]["result"][field] = invalid
                    self.assertIsNone(self._lookup(altered))

    def test_physical_file_hash_is_rechecked_even_when_size_is_unchanged(self) -> None:
        attempts, _ = self._three_runs()
        artifact = attempts[0]["result"]["artifacts"][0]
        path = self.fixture.root / artifact["rel_path"]
        path.write_bytes(b"X" * artifact["bytes"])
        self.assertIsNone(self._lookup(attempts))

    def test_only_final_owner_root_is_accepted(self) -> None:
        attempts, _ = self._three_runs()
        altered = copy.deepcopy(attempts)
        altered[0]["run_id"] = altered[1]["run_id"]
        self.assertIsNone(self._lookup(altered))

    def test_foreign_registry_artifact_is_rejected(self) -> None:
        attempts, _ = self._three_runs()
        get_artifact = self.service.database.get_artifact

        def foreign(artifact_id: str) -> dict:
            record = get_artifact(artifact_id)
            record["production_id"] = "OTHER_PRODUCTION"
            return record

        with mock.patch.object(self.service.database, "get_artifact", side_effect=foreign):
            self.assertIsNone(self._lookup(attempts))

    def test_owner_path_rejects_a_symlink_component(self) -> None:
        attempts, _ = self._three_runs()
        with mock.patch("tools.studio.service._has_symlink_component", return_value=True) as check:
            self.assertIsNone(self._lookup(attempts))
            check.assert_called_once_with(self.fixture.root, attempts[0]["result"]["artifacts"][0]["rel_path"])


if __name__ == "__main__":
    unittest.main()
