from __future__ import annotations

import copy
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

from tests.test_studio_backend import PRODUCTION_ID, WorkspaceFixture
from tools.studio.announcement_video import (
    AnnouncementVideoValidationError,
    announcement_narration_segment_starts,
    announcement_recipe_audit_summary,
    announcement_recipe_digest,
    announcement_recipe_to_detailed_payload,
    validate_announcement_recipe_payload,
)
from tools.studio.detailed_test_video import (
    ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY,
    detailed_test_video_audit_payload,
    detailed_test_video_key,
)
from tools.studio.narration import NarrationSynthesisError, generate_local_narration
from tools.studio.remotion_timeline_execution import (
    compile_remotion_timeline,
    frames_to_milliseconds,
)
from tools.studio.service import RequestValidationError, StudioService, build_rerun_plan
from tools.studio.server import create_server
from tools.studio.execution import narration_cache_key, validate_local_narration_payload


ARTIFACTS = [f"art_{index:032x}" for index in range(1, 4)]
RECIPE_ID = "announcement_" + "a" * 32
CLONE_ID = "announcement_" + "b" * 32


def recipe(*, name: str = "新サービス告知", cta: str = "詳しくは\nプロフィールへ") -> dict[str, object]:
    roles = ("hook", "message", "cta")
    headlines = ("その情報、\n届いていますか？", "大切なことを\nひと目で", cta)
    narrations = (
        "十五秒で、しっかり伝える。",
        "大切な情報を、ひと目で。",
        "続きはプロフィールから。",
    )
    return {
        "schema_version": 1,
        "name": name,
        "template_preset": "shorts_ja_15s_v1",
        "scenes": [
            {
                "role": role,
                "video_artifact_id": ARTIFACTS[index],
                "start_ms": 0,
                "end_ms": 5_000,
                "volume_percent": 0,
                "headline": headlines[index],
                "narration": narrations[index],
            }
            for index, role in enumerate(roles)
        ],
        "voice": None,
        "rate": 0,
        "pronunciations": [],
        "include_captioned": True,
        "caption_style_preset": "shorts_ja_large_v1",
        "audio_mix_preset": "narration_only_v1",
        "variant": "captioned",
    }


class AnnouncementContractTests(unittest.TestCase):
    def test_recipe_compiles_to_closed_detailed_contract(self) -> None:
        normalized = validate_announcement_recipe_payload(recipe())
        payload = announcement_recipe_to_detailed_payload(normalized)
        self.assertEqual([item["role"] for item in normalized["scenes"]], ["hook", "message", "cta"])
        self.assertEqual(len(payload["clips"]), 3)
        self.assertEqual(payload["clips"][0]["transition_to_next"], {"type": "fade", "duration_ms": 250})
        self.assertEqual(payload["clips"][1]["transition_to_next"], {"type": "fade", "duration_ms": 250})
        self.assertIsNone(payload["clips"][2]["transition_to_next"])
        self.assertEqual(
            [item["overlay"]["position"] for item in payload["clips"]],
            ["center", "top", "center"],
        )
        self.assertEqual([item["text"] for item in payload["segments"]], [
            "十五秒で、しっかり伝える。",
            "大切な情報を、ひと目で。",
            "続きはプロフィールから。",
        ])
        self.assertEqual(
            ["preserve_v1", "preserve_v1", "preserve_v1"],
            [item["visual_preset"] for item in payload["clips"]],
        )
        self.assertNotIn("visual_presets", announcement_recipe_audit_summary(normalized))
        self.assertEqual(set(payload), {
            "schema_version", "clips", "segments", "rate", "include_captioned",
            "caption_style_preset", "audio_mix_preset", "variant", "voice",
            "pronunciations",
        })
        starts = announcement_narration_segment_starts(normalized)
        self.assertEqual(starts, (0, 4_750, 9_500))

        sources = [
            {
                "video_artifact_id": artifact_id,
                "source_bytes": index + 1,
                "source_sha256": f"{index + 1:X}" * 64,
            }
            for index, artifact_id in enumerate(ARTIFACTS)
        ]
        remotion_key = "D" * 64
        plain_key = detailed_test_video_key(
            payload,
            source_clips=sources,
            remotion_cache_key=remotion_key,
        )
        aligned_key = detailed_test_video_key(
            payload,
            source_clips=sources,
            remotion_cache_key=remotion_key,
            narration_segment_start_ms=starts,
        )
        self.assertNotEqual(aligned_key, plain_key)
        audit = detailed_test_video_audit_payload(
            payload,
            request_key=aligned_key,
            source_clips=sources,
            remotion_cache_key=remotion_key,
            narration_segment_start_ms=starts,
        )
        self.assertEqual(
            audit["narration_alignment_policy"],
            ANNOUNCEMENT_NARRATION_ALIGNMENT_POLICY,
        )
        self.assertEqual(audit["narration_segment_start_ms"], [0, 4_750, 9_500])

    def test_narration_starts_match_compiled_remotion_frame_boundaries(self) -> None:
        cases = (
            ((4_020, 4_020, 4_020), (0, 3_750, 7_500), (0, 90, 180)),
            ((5_167, 5_167, 5_166), (0, 4_917, 9_833), (0, 118, 236)),
        )
        for durations, expected_ms, expected_frames in cases:
            with self.subTest(durations=durations):
                value = recipe()
                for scene, duration_ms in zip(
                    value["scenes"], durations, strict=True
                ):
                    scene["end_ms"] = duration_ms
                normalized = validate_announcement_recipe_payload(value)
                payload = announcement_recipe_to_detailed_payload(normalized)
                internal_clips = [
                    {
                        **clip,
                        "source_path": f"source-{index}.mp4",
                        "source_bytes": index + 1,
                        "source_sha256": f"{index + 1:X}" * 64,
                    }
                    for index, clip in enumerate(payload["clips"])
                ]
                compiled = compile_remotion_timeline(internal_clips)
                compiled_frames = tuple(
                    clip["start_frame"] for clip in compiled["clips"]
                )
                compiled_ms = tuple(
                    0 if frame == 0 else frames_to_milliseconds(frame)
                    for frame in compiled_frames
                )

                self.assertEqual(compiled_frames, expected_frames)
                self.assertEqual(compiled_ms, expected_ms)
                self.assertEqual(
                    announcement_narration_segment_starts(normalized),
                    expected_ms,
                )
                if durations == (5_167, 5_167, 5_166):
                    raw_millisecond_schedule = (0, 4_917, 9_834)
                    exact_key = detailed_test_video_key(
                        payload,
                        source_clips=internal_clips,
                        remotion_cache_key="E" * 64,
                        narration_segment_start_ms=expected_ms,
                    )
                    stale_key = detailed_test_video_key(
                        payload,
                        source_clips=internal_clips,
                        remotion_cache_key="E" * 64,
                        narration_segment_start_ms=raw_millisecond_schedule,
                    )
                    self.assertNotEqual(exact_key, stale_key)
                    narration_payload = validate_local_narration_payload(
                        {
                            "segments": payload["segments"],
                            "voice": payload["voice"],
                            "rate": payload["rate"],
                            "pronunciations": payload["pronunciations"],
                        }
                    )
                    self.assertNotEqual(
                        narration_cache_key(
                            narration_payload,
                            segment_start_ms=expected_ms,
                        ),
                        narration_cache_key(
                            narration_payload,
                            segment_start_ms=raw_millisecond_schedule,
                        ),
                    )
                    audit = detailed_test_video_audit_payload(
                        payload,
                        request_key=exact_key,
                        source_clips=internal_clips,
                        remotion_cache_key="E" * 64,
                        narration_segment_start_ms=expected_ms,
                    )
                    self.assertEqual(
                        audit["narration_segment_start_ms"],
                        [0, 4_917, 9_833],
                    )

    def test_frame_aligned_scene_boundary_drives_overlap_rejection(self) -> None:
        value = recipe()
        for scene in value["scenes"]:
            scene["end_ms"] = 4_020
        starts = announcement_narration_segment_starts(value)
        self.assertEqual(starts, (0, 3_750, 7_500))

        def synthesize(
            _text: str,
            *,
            voice: str | None,
            rate: int,
        ) -> bytes:
            del voice, rate
            output = io.BytesIO()
            with wave.open(output, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(1_000)
                handle.writeframes(b"\x00\x00" * 3_760)
            return output.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                NarrationSynthesisError,
                "overlaps the next scheduled scene",
            ):
                generate_local_narration(
                    Path(temporary),
                    production_id="PROD_TEST",
                    run_id="RUN_FRAME_OVERLAP",
                    payload={
                        "segments": [
                            {"text": "フック"},
                            {"text": "メッセージ"},
                            {"text": "案内"},
                        ],
                        "rate": 0,
                    },
                    segment_start_ms=starts,
                    synthesizer=synthesize,
                )

    def test_recipe_rejects_open_fields_roles_duration_and_unsafe_headline(self) -> None:
        invalid = recipe()
        invalid["output_path"] = "C:/unsafe.mp4"
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(invalid)

        invalid = recipe()
        invalid["scenes"][1]["role"] = "hook"
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(invalid)

        invalid = recipe()
        for scene in invalid["scenes"]:
            scene["end_ms"] = 3_000
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(invalid)

        for headline in ("あ" * 11, "one\ntwo\nthree", "unsafe\u200btext", "A" * 21):
            invalid = recipe()
            invalid["scenes"][0]["headline"] = headline
            with self.assertRaises(AnnouncementVideoValidationError):
                validate_announcement_recipe_payload(invalid)

        invalid = recipe()
        invalid["audio_mix_preset"] = "source_under_narration_v1"
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(invalid)

        invalid = recipe()
        invalid["scenes"][0]["visual_preset"] = "unsharp=1.0"
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(invalid)

        for visual_preset in ([], {}, None, 1):
            invalid = recipe()
            invalid["scenes"][0]["visual_preset"] = visual_preset
            with self.subTest(visual_preset=visual_preset), self.assertRaises(
                AnnouncementVideoValidationError
            ):
                validate_announcement_recipe_payload(invalid)

    def test_explicit_visual_preset_is_preserved_and_compiled_per_scene(self) -> None:
        value = recipe()
        value["scenes"][0]["visual_preset"] = "h3_low_res_sharp_v1"
        value["scenes"][1]["visual_preset"] = "preserve_v1"
        normalized = validate_announcement_recipe_payload(value)
        self.assertEqual(value, normalized)
        payload = announcement_recipe_to_detailed_payload(normalized)
        self.assertEqual(
            ["h3_low_res_sharp_v1", "preserve_v1", "preserve_v1"],
            [item["visual_preset"] for item in payload["clips"]],
        )
        self.assertEqual(
            ["h3_low_res_sharp_v1", "preserve_v1", "preserve_v1"],
            announcement_recipe_audit_summary(normalized)["visual_presets"],
        )


class AnnouncementPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def _save(self, value: dict[str, object], *, expected_revision: int = 0, recipe_id: str = RECIPE_ID) -> dict[str, object]:
        return self.service.save_announcement_recipe(
            PRODUCTION_ID,
            recipe_id,
            {
                "schema_version": 1,
                "expected_revision": expected_revision,
                "recipe": value,
            },
        )

    def test_exact_round_trip_revision_cas_and_restart(self) -> None:
        value = recipe(name="API_KEY=demo 告知")
        value["scenes"][0]["headline"] = "API_KEY=demo"
        value["scenes"][0]["narration"] = "Bearer abcdefgh を安全に扱う。"
        first = self._save(value)
        self.assertEqual(first["revision"], 1)
        self.assertFalse(first["deduplicated"])
        self.assertEqual(first["recipe"], validate_announcement_recipe_payload(value))

        retry = self._save(value)
        self.assertEqual(retry["version_id"], first["version_id"])
        self.assertTrue(retry["deduplicated"])

        updated = copy.deepcopy(value)
        updated["name"] = "API_KEY=demo 告知 v2"
        second = self._save(updated, expected_revision=1)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["parent_version_id"], first["version_id"])
        self.assertNotEqual(second["digest"], first["digest"])
        with self.assertRaisesRegex(RequestValidationError, "changed after"):
            self._save(recipe(name="競合"), expected_revision=1)

        restored = self._save(value, expected_revision=2)
        self.assertEqual(restored["revision"], 3)
        self.assertFalse(restored["deduplicated"])
        self.assertTrue(self._save(value, expected_revision=3)["deduplicated"])
        self.assertTrue(self._save(value, expected_revision=2)["deduplicated"])
        with self.assertRaisesRegex(RequestValidationError, "changed after"):
            self._save(value, expected_revision=0)

        self.service.close()
        self.service = StudioService(self.fixture.root)
        listed = self.service.list_announcement_recipes(PRODUCTION_ID)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["recipes"][0]["recipe"], validate_announcement_recipe_payload(value))
        self.assertEqual(listed["recipes"][0]["version_count"], 3)
        self.assertEqual(len(listed["recipe_versions"]), 3)

    def test_event_mirror_rebuild_restores_exact_recipe_versions(self) -> None:
        first_value = recipe(name="復旧する告知")
        first_value["scenes"][0]["narration"] = "イベント履歴から、正確に戻します。"
        first = self._save(first_value)
        second_value = copy.deepcopy(first_value)
        second_value["scenes"][2]["headline"] = "今すぐ\n確認する"
        second = self._save(second_value, expected_revision=1)
        database_path = self.service.database.path

        self.service.close()
        database_path.unlink()
        database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
        database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

        listed = self.service.list_announcement_recipes(PRODUCTION_ID)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(len(listed["recipe_versions"]), 2)
        self.assertEqual(
            [item["version_id"] for item in listed["recipe_versions"]],
            [first["version_id"], second["version_id"]],
        )
        self.assertEqual(
            listed["recipes"][0]["recipe"],
            validate_announcement_recipe_payload(second_value),
        )
        self.assertEqual(listed["recipes"][0]["parent_version_id"], first["version_id"])

    def test_duplicate_is_independent_and_execution_link_is_idempotent(self) -> None:
        source = self._save(recipe())
        source_record = self.service.database.get_announcement_recipe(
            PRODUCTION_ID, RECIPE_ID, revision=1
        )
        assert source_record is not None
        clone = self.service.duplicate_announcement_recipe(
            PRODUCTION_ID,
            RECIPE_ID,
            {
                "schema_version": 1,
                "source_revision": 1,
                "new_recipe_id": CLONE_ID,
                "name": "新サービス告知（コピー）",
            },
        )
        self.assertEqual(clone["clone_source_version_id"], source["version_id"])
        self.assertEqual(clone["recipe"]["name"], "新サービス告知（コピー）")
        replayed_clone = self.service.duplicate_announcement_recipe(
            PRODUCTION_ID,
            RECIPE_ID,
            {
                "schema_version": 1,
                "source_revision": 1,
                "new_recipe_id": CLONE_ID,
                "name": "新サービス告知（コピー）",
            },
        )
        self.assertTrue(replayed_clone["deduplicated"])
        self.assertEqual(replayed_clone["version_id"], clone["version_id"])
        self.assertEqual(
            self.service.database.get_announcement_recipe(PRODUCTION_ID, RECIPE_ID)["recipe"]["name"],
            "新サービス告知",
        )

        revised_source = recipe(name="新サービス告知 v2")
        self._save(revised_source, expected_revision=1)
        with self.assertRaisesRegex(RequestValidationError, "already in use"):
            self.service.duplicate_announcement_recipe(
                PRODUCTION_ID,
                RECIPE_ID,
                {
                    "schema_version": 1,
                    "source_revision": 2,
                    "new_recipe_id": CLONE_ID,
                    "name": "新サービス告知（コピー）",
                },
            )

        fake_job = {
            "id": "job_" + "1" * 32,
            "kind": "detailed_test_video",
            "status": "queued",
            "run_id": "run_" + "2" * 32,
            "revision_id": "rev_" + "3" * 32,
            "request_key": "A" * 64,
            "deduplicated": False,
        }
        fake_link = {
            "event_id": 42,
            "recipe_version_id": source["version_id"],
            "job_id": fake_job["id"],
        }
        with mock.patch.object(
            self.service,
            "execute_detailed_test_video",
            return_value=fake_job,
        ) as execute, mock.patch.object(
            self.service.database,
            "get_announcement_execution",
            return_value=fake_link,
        ):
            first = self.service.execute_announcement_recipe(
                PRODUCTION_ID,
                RECIPE_ID,
                {"schema_version": 1, "revision": 1},
            )
            second = self.service.execute_announcement_recipe(
                PRODUCTION_ID,
                RECIPE_ID,
                {"schema_version": 1, "revision": 1},
            )
        self.assertEqual(execute.call_count, 2)
        compiled = execute.call_args_list[0].args[1]
        self.assertEqual(compiled, announcement_recipe_to_detailed_payload(source["recipe"]))
        self.assertEqual(
            execute.call_args_list[0].kwargs["_announcement_recipe"], source_record
        )
        self.assertEqual(first["announcement_execution"]["event_id"], second["announcement_execution"]["event_id"])

        detail = self.service.production_detail(PRODUCTION_ID)
        self.assertEqual(len(detail["announcement_recipes"]), 2)
        self.assertEqual(len(detail["announcement_recipe_versions"]), 3)

    def test_detailed_job_and_execution_link_commit_atomically_and_dedupe_clones(self) -> None:
        source = self._save(recipe())
        source = self.service.database.get_announcement_recipe(
            PRODUCTION_ID, RECIPE_ID, revision=1
        )
        assert source is not None
        clone = self.service.duplicate_announcement_recipe(
            PRODUCTION_ID,
            RECIPE_ID,
            {
                "schema_version": 1,
                "source_revision": 1,
                "new_recipe_id": CLONE_ID,
                "name": "別名コピー",
            },
        )
        clone = self.service.database.get_announcement_recipe(
            PRODUCTION_ID, CLONE_ID, revision=1
        )
        assert clone is not None
        request_key = "D" * 64
        changes = [{"type": "script"}, {"type": "timeline"}]
        revision, run = self.service.database.create_revision_and_run(
            PRODUCTION_ID,
            changes,
            build_rerun_plan(PRODUCTION_ID, changes),
            0,
            "USD",
            execution_profile="local_sapi",
            detailed_test_video_key=request_key,
        )
        job_payload = {
            "production_id": PRODUCTION_ID,
            "run_id": run["id"],
            "revision_id": revision["id"],
            "stage": "detailed_test_video",
            "execution_profile": "local_sapi",
            "request_key": request_key,
        }
        first_job, first_created = self.service.database.create_or_get_detailed_test_video_job(
            production_id=PRODUCTION_ID,
            run_id=run["id"],
            request_key=request_key,
            payload=job_payload,
            announcement_recipe=source,
        )
        self.assertTrue(first_created)
        first_link = self.service.database.get_announcement_execution(
            PRODUCTION_ID, source["version_id"], first_job["id"]
        )
        self.assertIsNotNone(first_link)

        same_job, same_created = self.service.database.create_or_get_detailed_test_video_job(
            production_id=PRODUCTION_ID,
            run_id=run["id"],
            request_key=request_key,
            payload=job_payload,
            announcement_recipe=source,
        )
        self.assertFalse(same_created)
        self.assertEqual(same_job["id"], first_job["id"])
        self.assertEqual(
            self.service.database.get_announcement_execution(
                PRODUCTION_ID, source["version_id"], first_job["id"]
            )["event_id"],
            first_link["event_id"],
        )

        clone_job, clone_created = self.service.database.create_or_get_detailed_test_video_job(
            production_id=PRODUCTION_ID,
            run_id=run["id"],
            request_key=request_key,
            payload=job_payload,
            announcement_recipe=clone,
        )
        self.assertFalse(clone_created)
        self.assertEqual(clone_job["id"], first_job["id"])
        links = self.service.database.list_announcement_executions(PRODUCTION_ID)
        self.assertEqual(len(links), 2)
        self.assertEqual({item["recipe_version_id"] for item in links}, {
            source["version_id"], clone["version_id"]
        })

    def test_execution_link_event_failure_rolls_back_job_admission(self) -> None:
        source = self._save(recipe())
        source = self.service.database.get_announcement_recipe(
            PRODUCTION_ID, RECIPE_ID, revision=1
        )
        assert source is not None
        request_key = "E" * 64
        changes = [{"type": "script"}, {"type": "timeline"}]
        revision, run = self.service.database.create_revision_and_run(
            PRODUCTION_ID,
            changes,
            build_rerun_plan(PRODUCTION_ID, changes),
            0,
            "USD",
            execution_profile="local_sapi",
            detailed_test_video_key=request_key,
        )
        payload = {
            "production_id": PRODUCTION_ID,
            "run_id": run["id"],
            "revision_id": revision["id"],
            "stage": "detailed_test_video",
            "execution_profile": "local_sapi",
            "request_key": request_key,
        }
        with self.service.database.transaction() as connection:
            connection.execute(
                "CREATE TRIGGER reject_announcement_execution BEFORE INSERT ON events "
                "WHEN NEW.event_type='announcement.recipe.executed' "
                "BEGIN SELECT RAISE(ABORT, 'reject announcement link'); END"
            )
        with self.assertRaisesRegex(Exception, "reject announcement link"):
            self.service.database.create_or_get_detailed_test_video_job(
                production_id=PRODUCTION_ID,
                run_id=run["id"],
                request_key=request_key,
                payload=payload,
                announcement_recipe=source,
            )
        self.assertIsNone(
            self.service.database.find_latest_job_for_run(
                "detailed_test_video", PRODUCTION_ID, run["id"]
            )
        )
        claim = self.service.database.get_detailed_test_video_claim(
            PRODUCTION_ID, request_key
        )
        self.assertIsNone(claim["active_job_id"])

    def test_invalid_wire_body_and_missing_recipe_fail_closed(self) -> None:
        with self.assertRaises(RequestValidationError):
            self.service.save_announcement_recipe(
                PRODUCTION_ID,
                RECIPE_ID,
                {"schema_version": 1, "expected_revision": 0, "recipe": recipe(), "path": "unsafe"},
            )
        with self.assertRaises(KeyError):
            self.service.execute_announcement_recipe(
                PRODUCTION_ID,
                RECIPE_ID,
                {"schema_version": 1, "revision": 1},
            )

    def test_private_narration_schedule_requires_capability_and_detailed_claim(self) -> None:
        request_key = "F" * 64
        changes = [{"type": "script"}, {"type": "timeline"}]
        _revision, run = self.service.database.create_revision_and_run(
            PRODUCTION_ID,
            changes,
            build_rerun_plan(PRODUCTION_ID, changes),
            0,
            "USD",
            execution_profile="local_sapi",
            detailed_test_video_key=request_key,
        )
        body = {
            "segments": [
                {"text": "フック"},
                {"text": "メッセージ"},
                {"text": "案内"},
            ],
            "rate": 0,
        }
        schedule = [0, 4_750, 9_500]
        with self.assertRaisesRegex(RequestValidationError, "provenance"):
            self.service.execute_local_narration(
                run["id"],
                body,
                _announcement_narration_timing_capability=object(),
                _announcement_segment_start_ms=schedule,
                _announcement_detailed_test_video_key=request_key,
            )

        queued = {"id": "job_" + "7" * 32, "status": "queued"}
        with mock.patch.object(
            self.service.jobs, "submit", return_value=queued
        ) as submit:
            result = self.service.execute_local_narration(
                run["id"],
                body,
                _announcement_narration_timing_capability=(
                    self.service._announcement_narration_timing_capability
                ),
                _announcement_segment_start_ms=schedule,
                _announcement_detailed_test_video_key=request_key,
            )
        job_payload = submit.call_args.args[1]
        self.assertEqual(
            job_payload["narration_timing_policy"],
            "absolute_segment_starts_v1",
        )
        self.assertEqual(job_payload["narration_segment_start_ms"], schedule)
        self.assertNotEqual(
            result["cache_key"],
            narration_cache_key(validate_local_narration_payload(body)),
        )

    def test_digest_is_content_addressed_not_recipe_id(self) -> None:
        normalized = validate_announcement_recipe_payload(recipe())
        self.assertEqual(announcement_recipe_digest(normalized), announcement_recipe_digest(copy.deepcopy(normalized)))

    def test_tampered_recipe_summary_is_rejected(self) -> None:
        self._save(recipe())
        with self.service.database.transaction() as connection:
            connection.execute("DROP TRIGGER events_immutable_update")
            row = connection.execute(
                "SELECT id, payload_json FROM events "
                "WHERE event_type='announcement.recipe.saved'"
            ).fetchone()
            payload = json.loads(row["payload_json"])
            payload["summary"]["name"] = "改ざん"
            connection.execute(
                "UPDATE events SET payload_json=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), row["id"]),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.list_announcement_recipes(PRODUCTION_ID)


class AnnouncementHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "announcement-session-token-at-least-32-characters"
        self.server = create_server(
            self.fixture.root,
            host="127.0.0.1",
            port=0,
            static_dir="studio/dist",
            session_token=self.token,
            initial_refresh=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.fixture.close()

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"X-Studio-Token": self.token}
        if encoded is not None:
            headers.update(
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(encoded)),
                }
            )
        self.connection.request(method, path, body=encoded, headers=headers)
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_collection_route_delegates_exact_production_id(self) -> None:
        expected = {
            "schema_version": 1,
            "production_id": PRODUCTION_ID,
            "recipes": [],
            "recipe_versions": [],
            "executions": [],
            "count": 0,
        }
        with mock.patch.object(
            self.server.service,
            "list_announcement_recipes",
            return_value=expected,
        ) as listed:
            status, payload = self._request(
                "GET", f"/api/productions/{PRODUCTION_ID}/announcement-recipes"
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload, expected)
        listed.assert_called_once_with(PRODUCTION_ID)

    def test_missing_collection_returns_404(self) -> None:
        status, payload = self._request(
            "GET", "/api/productions/missing-production/announcement-recipes"
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_save_duplicate_and_execute_routes_forward_exact_body(self) -> None:
        save_body = {
            "schema_version": 1,
            "expected_revision": 0,
            "recipe": recipe(),
        }
        duplicate_body = {
            "schema_version": 1,
            "source_revision": 1,
            "new_recipe_id": CLONE_ID,
            "name": "告知コピー",
        }
        execute_body = {"schema_version": 1, "revision": 1}
        expected = {"ok": True}
        cases = (
            (
                "save",
                save_body,
                201,
                "save_announcement_recipe",
            ),
            (
                "duplicate",
                duplicate_body,
                201,
                "duplicate_announcement_recipe",
            ),
            (
                "execute",
                execute_body,
                202,
                "execute_announcement_recipe",
            ),
        )
        for suffix, body, expected_status, method_name in cases:
            with self.subTest(suffix=suffix), mock.patch.object(
                self.server.service,
                method_name,
                return_value=expected,
            ) as delegated:
                status, payload = self._request(
                    "POST",
                    f"/api/productions/{PRODUCTION_ID}/announcement-recipes/{RECIPE_ID}/{suffix}",
                    body,
                )
                self.assertEqual(status, expected_status)
                self.assertEqual(payload, expected)
                delegated.assert_called_once_with(PRODUCTION_ID, RECIPE_ID, body)


if __name__ == "__main__":
    unittest.main()
