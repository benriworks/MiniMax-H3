from __future__ import annotations

import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.test_studio_backend import (
    PRODUCTION_ID,
    WorkspaceFixture,
    fake_local_assembly_result,
    fake_local_narration_result,
    fake_local_qc_result,
    fake_validate_local_assembly_outputs,
    fake_validate_local_qc_outputs,
)
from tools.studio.database import SCHEMA_VERSION, StudioDatabase
from tools.studio.detailed_test_video import (
    SHORTS_JA_CAPTION_PREFLIGHT_POLICY,
    DetailedTestVideoError,
    DetailedTestVideoValidationError,
    detailed_test_video_audit_payload,
    detailed_test_video_key,
    detailed_test_video_public_result,
    run_detailed_test_video,
    validate_detailed_test_video_payload,
)
from tools.studio.jobs import JobCancelled, JobExecutionContext, JobManager
from tools.studio import detailed_test_video as detailed_module
from tools.studio.remotion_timeline_execution import compile_remotion_timeline
from tools.studio.security import canonical_json
from tools.studio.service import StudioService
from tools.studio.server import create_server


ARTIFACT_ID = "art_" + "1" * 32
REQUEST_KEY = "A" * 64
REMOTION_KEY = "B" * 64


def _payload(
    text: str = "短い字幕です。",
    *,
    artifact_id: str = ARTIFACT_ID,
    segments: list[dict[str, str]] | None = None,
    include_captioned: bool = True,
    caption_style_preset: str = "shorts_ja_large_v1",
    variant: str = "captioned",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "clips": [
            {
                "video_artifact_id": artifact_id,
                "start_ms": 0,
                "end_ms": 125,
                "volume_percent": 75,
                "transition_to_next": None,
                "overlay": None,
            }
        ],
        "segments": segments if segments is not None else [{"text": text}],
        "rate": 0,
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style_preset,
        "audio_mix_preset": "narration_only_v1",
        "variant": variant,
    }


def _source_identity() -> list[dict[str, object]]:
    return [
        {
            "video_artifact_id": ARTIFACT_ID,
            "source_bytes": 123,
            "source_sha256": "C" * 64,
        }
    ]


def _artifact(index: int, name: str, kind: str, media_type: str) -> dict[str, object]:
    return {
        "id": f"art_{index:032x}",
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "rel_path": f"outputs/studio/fake/{index}/{name}",
        "bytes": index + 10,
        "sha256": hashlib.sha256(name.encode("utf-8")).hexdigest().upper(),
    }


def _run_plan() -> tuple[list[dict[str, str]], dict[str, object]]:
    changes = [{"type": "script"}, {"type": "timeline"}]
    stages = ["narration", "captions", "timeline", "assembly", "qc"]
    return changes, {
        "changes": changes,
        "affected_stages": stages,
        "requested_stages": stages,
    }


def _index_empty_production(database: StudioDatabase) -> None:
    database.index_production(
        {
            "id": PRODUCTION_ID,
            "title": "Detailed test video",
            "status": "test",
            "technical_status": None,
            "creative_status": None,
            "public_release_status": None,
            "source_rel": None,
            "output_rel": None,
        },
        [],
    )


def _fake_remotion_artifacts(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    create: bool,
) -> list[dict[str, object]]:
    root = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "remotion_timeline"
        / cache_key
    )
    if create:
        root.mkdir(parents=True, exist_ok=True)
    files = {
        "remotion-preview.mp4": ("video", "video/mp4", b"remotion-video"),
        "remotion-timeline.json": ("document", "application/json", b"{}\n"),
        "render-report.json": ("document", "application/json", b"{}\n"),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    artifacts: list[dict[str, object]] = []
    for name, (kind, media_type, expected) in files.items():
        path = root / name
        if create:
            path.write_bytes(expected)
        content = path.read_bytes()
        artifacts.append(
            {
                "name": name,
                "rel_path": path.relative_to(workspace).as_posix(),
                "kind": kind,
                "media_type": media_type,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    return artifacts


def _fake_remotion_result(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    clips: list[dict[str, object]],
    create: bool,
    cache_hit: bool,
) -> dict[str, object]:
    return {
        "artifacts": _fake_remotion_artifacts(
            workspace, run_id=run_id, cache_key=cache_key, create=create
        ),
        "duration_ms": compile_remotion_timeline(clips)["duration_ms"],
        "cache_key": cache_key,
        "cache_hit": cache_hit,
        "provider": "local_remotion_timeline",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "remotion_frames",
        "has_audio": True,
    }


def _fake_generate_remotion(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    clips: list[dict[str, object]],
    **_kwargs: object,
) -> dict[str, object]:
    return _fake_remotion_result(
        workspace,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        create=True,
        cache_hit=False,
    )


def _fake_validate_remotion(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    clips: list[dict[str, object]],
    **_kwargs: object,
) -> dict[str, object]:
    return _fake_remotion_result(
        workspace,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        create=False,
        cache_hit=True,
    )


class _FakeDetailedDatabase:
    def __init__(self, run_id: str, revision_id: str, request_key: str):
        self.run = {
            "id": run_id,
            "production_id": PRODUCTION_ID,
            "revision_id": revision_id,
            "execution_profile": "local_sapi",
            "requested_stages": [
                "narration",
                "captions",
                "timeline",
                "assembly",
                "qc",
            ],
            "estimated_cost": {"amount": "0.00", "currency": "USD"},
        }
        self.claim = {
            "production_id": PRODUCTION_ID,
            "request_key": request_key,
            "run_id": run_id,
            "revision_id": revision_id,
        }
        self.attempts: dict[str, dict[str, object]] = {}
        self.progress: list[tuple[int, str]] = []

    def get_run(self, run_id: str) -> dict[str, object] | None:
        return self.run if run_id == self.run["id"] else None

    def get_detailed_test_video_claim(
        self, production_id: str, request_key: str
    ) -> dict[str, object] | None:
        if production_id == PRODUCTION_ID and request_key == self.claim["request_key"]:
            return self.claim
        return None

    def get_stage_attempt(self, attempt_id: str) -> dict[str, object] | None:
        return self.attempts.get(attempt_id)

    def update_job_progress(self, _job_id: str, progress: int, phase: str) -> None:
        self.progress.append((progress, phase))


class _FakeDetailedJobs:
    def __init__(self, service: "_FakeDetailedService"):
        self.service = service
        self.cancel_calls: list[bool] = []

    def wait(self, job_id: str, timeout: float) -> dict[str, object] | None:
        del timeout
        return self.service.jobs_by_id.get(job_id)

    def cancel_and_wait(
        self,
        _job_id: str,
        *,
        timeout: float | None,
        preserve_provider_task: bool,
    ) -> None:
        del timeout
        self.cancel_calls.append(preserve_provider_task)


class _FakeDetailedService:
    def __init__(
        self,
        run_id: str,
        revision_id: str,
        request_key: str,
        *,
        timeline_cache_key: str,
    ):
        self.database = _FakeDetailedDatabase(run_id, revision_id, request_key)
        self.jobs = _FakeDetailedJobs(self)
        self.jobs_by_id: dict[str, dict[str, object]] = {}
        self.order: list[str] = []
        self.timeline_cache_key = timeline_cache_key
        self._announcement_narration_timing_capability = object()
        self.narration_private_args: dict[str, object] | None = None

    def _execute(self, stage: str, run_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.order.append(stage)
        index = len(self.order)
        job_id = f"job_{index:032x}"
        attempt_id = f"attempt_{index:032x}"
        result: dict[str, object] = {"cache_hit": False}
        if stage == "narration":
            result["duration_ms"] = 125
            result["artifacts"] = []
        elif stage == "timeline":
            result.update(
                {
                    "duration_ms": 125,
                    "cache_key": self.timeline_cache_key,
                    "artifacts": [
                        _artifact(20, "remotion-preview.mp4", "video", "video/mp4")
                    ],
                }
            )
        elif stage == "assembly":
            result.update(
                {
                    "duration_ms": 125,
                    "artifacts": [
                        _artifact(21, "master-captioned.mp4", "video", "video/mp4")
                    ],
                }
            )
        else:
            result.update(
                {
                    "analysis_status": "succeeded",
                    "technical_verdict": "pass",
                    "duration_ms": 125,
                    "expected_duration_ms": 125,
                    "artifacts": [
                        _artifact(22, "technical-qc.json", "document", "application/json"),
                        _artifact(23, "ffprobe.json", "document", "application/json"),
                        _artifact(24, "manifest.json", "document", "application/json"),
                    ],
                }
            )
        job_result = {**result, "stage_attempt_id": attempt_id}
        record = {
            "id": job_id,
            "kind": {
                "narration": "local_narration",
                "timeline": "local_remotion_timeline",
                "assembly": "local_assembly",
                "qc": "local_qc",
            }[stage],
            "status": "succeeded",
            "production_id": PRODUCTION_ID,
            "payload": {
                "run_id": run_id,
                "production_id": PRODUCTION_ID,
                "stage": stage,
                "stage_attempt_id": attempt_id,
                "execution_profile": "local_sapi",
                **(
                    {"cache_key": self.timeline_cache_key}
                    if stage == "timeline"
                    else {}
                ),
            },
            "result": job_result,
        }
        self.jobs_by_id[job_id] = record
        self.database.attempts[attempt_id] = {
            "id": attempt_id,
            "job_id": job_id,
            "run_id": run_id,
            "production_id": PRODUCTION_ID,
            "stage": stage,
            "status": "succeeded",
            "cache_key": result.get("cache_key", "D" * 64),
            "result": result,
        }
        return {**record, "stage_attempt_id": attempt_id}

    def execute_local_narration(
        self,
        run_id: str,
        payload: dict[str, object],
        *,
        _announcement_narration_timing_capability: object | None = None,
        _announcement_segment_start_ms: list[int] | None = None,
        _announcement_detailed_test_video_key: str | None = None,
    ) -> dict[str, object]:
        if _announcement_segment_start_ms is not None:
            self.narration_private_args = {
                "capability": _announcement_narration_timing_capability,
                "segment_start_ms": _announcement_segment_start_ms,
                "request_key": _announcement_detailed_test_video_key,
            }
        return self._execute("narration", run_id, payload)

    def execute_remotion_timeline(self, run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return self._execute("timeline", run_id, payload)

    def execute_local_assembly(self, run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return self._execute("assembly", run_id, payload)

    def execute_local_qc(self, run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return self._execute("qc", run_id, payload)


class DetailedTestVideoContractTests(unittest.TestCase):
    def test_visual_preset_is_closed_and_defaults_to_preserve(self) -> None:
        normalized = validate_detailed_test_video_payload(_payload())
        self.assertEqual(
            "preserve_v1", normalized["clips"][0]["visual_preset"]
        )
        sharpened = _payload()
        sharpened["clips"][0]["visual_preset"] = "h3_low_res_sharp_v1"
        self.assertEqual(
            "h3_low_res_sharp_v1",
            validate_detailed_test_video_payload(sharpened)["clips"][0][
                "visual_preset"
            ],
        )
        injected = _payload()
        injected["clips"][0]["visual_preset"] = "unsharp=1.0"
        with self.assertRaises(DetailedTestVideoValidationError):
            validate_detailed_test_video_payload(injected)

    def test_request_payload_digest_matches_frontend_vectors_with_optional_fields_present_or_omitted(self) -> None:
        artifact_id = "art_" + "a" * 32
        payload = {
            "schema_version": 1,
            "clips": [
                {
                    "video_artifact_id": artifact_id,
                    "start_ms": 100,
                    "end_ms": 2_100,
                    "volume_percent": 80,
                    "transition_to_next": None,
                    "overlay": None,
                }
            ],
            "segments": [{"text": "one"}, {"text": "two"}],
            "rate": 1,
            "include_captioned": True,
            "caption_style_preset": "shorts_ja_large_v1",
            "audio_mix_preset": "source_under_narration_v1",
            "variant": "captioned",
        }
        sources = [
            {
                "video_artifact_id": artifact_id,
                "source_bytes": 123,
                "source_sha256": "C" * 64,
            }
        ]
        cases = (
            (
                payload,
                "14204AF12EE99E320788268F716CF3D2990AB4BC5F64000E9CB45A78C5EA9A6A",
            ),
            (
                {
                    **payload,
                    "voice": "Voice",
                    "pronunciations": [{"source": "AI", "target": "A I"}],
                },
                "728040BC2E6ABD4B5BE6576467120A6830AC7F600E590A114B96C16E082464B3",
            ),
        )
        for request, expected in cases:
            with self.subTest(expected=expected):
                normalized = validate_detailed_test_video_payload(request)
                audit = detailed_test_video_audit_payload(
                    normalized,
                    request_key=REQUEST_KEY,
                    source_clips=sources,
                    remotion_cache_key=REMOTION_KEY,
                )
                self.assertEqual(audit["request_payload_sha256"], expected)

    def test_shorts_caption_preflight_boundaries_and_policy_audit(self) -> None:
        valid_cases = ["あ" * 19, "A" * 20]
        for text in valid_cases:
            with self.subTest(valid=text):
                normalized = validate_detailed_test_video_payload(_payload(text))
                self.assertNotIn("caption_preflight_policy", normalized)
        invalid_cases = ["あ" * 19 + "A", "A" * 21, "禁止\u00a0空白", "禁止\u200b文字"]
        for text in invalid_cases:
            with self.subTest(invalid=text):
                with self.assertRaises(DetailedTestVideoValidationError):
                    validate_detailed_test_video_payload(_payload(text))
        with self.assertRaises(DetailedTestVideoValidationError):
            validate_detailed_test_video_payload(
                _payload(segments=[{"text": str(index)} for index in range(7)])
            )

        normalized = validate_detailed_test_video_payload(_payload("あ" * 19))
        request_key = detailed_test_video_key(
            normalized,
            source_clips=_source_identity(),
            remotion_cache_key=REMOTION_KEY,
        )
        audit = detailed_test_video_audit_payload(
            normalized,
            request_key=request_key,
            source_clips=_source_identity(),
            remotion_cache_key=REMOTION_KEY,
        )
        self.assertEqual(
            audit["caption_preflight_policy"],
            SHORTS_JA_CAPTION_PREFLIGHT_POLICY,
        )
        self.assertEqual(
            audit["request_payload_sha256"],
            hashlib.sha256(canonical_json(normalized).encode("utf-8"))
            .hexdigest()
            .upper(),
        )
        self.assertEqual(audit["implementation_version"], "detailed-test-video-v3")
        self.assertNotIn("あ" * 19, repr(audit))

    def test_preflight_is_scoped_and_public_result_has_exact_safe_child_fields(self) -> None:
        unscoped = _payload(
            "A" * 21,
            include_captioned=True,
            caption_style_preset="studio_default_v1",
            variant="captioned",
        )
        validate_detailed_test_video_payload(unscoped)
        for forbidden in (
            {**_payload(), "source_path": "C:/secret.mp4"},
            {**_payload(), "source_url": "https://example.test/video.mp4"},
            {**_payload(), "narration_gain": 9.0},
        ):
            with self.subTest(forbidden=set(forbidden) - set(_payload())):
                with self.assertRaises(DetailedTestVideoValidationError):
                    validate_detailed_test_video_payload(forbidden)
        clip_url = _payload()
        clip_url["clips"] = [
            {**clip_url["clips"][0], "url": "https://example.test/video.mp4"}
        ]
        with self.assertRaises(DetailedTestVideoValidationError):
            validate_detailed_test_video_payload(clip_url)

        timeline = _artifact(1, "remotion-preview.mp4", "video", "video/mp4")
        master = _artifact(2, "master-captioned.mp4", "video", "video/mp4")
        reports = [
            _artifact(3, "ffprobe.json", "document", "application/json"),
            _artifact(4, "manifest.json", "document", "application/json"),
            _artifact(5, "technical-qc.json", "document", "application/json"),
        ]
        children = {
            stage: {
                "stage": stage,
                "status": "succeeded",
                "job_id": f"job_{index:032x}",
                "stage_attempt_id": f"attempt_{index:032x}",
                "cache_hit": False,
            }
            for index, stage in enumerate(
                ("narration", "timeline", "assembly", "qc"), start=1
            )
        }
        raw = {
            "schema_version": 1,
            "production_id": PRODUCTION_ID,
            "run_id": "run_" + "2" * 32,
            "revision_id": "rev_" + "3" * 32,
            "request_key": REQUEST_KEY,
            "execution_profile": "local_sapi",
            "duration_ms": 125,
            "technical_verdict": "pass",
            "variant": "captioned",
            "include_captioned": True,
            "caption_style_preset": "shorts_ja_large_v1",
            "caption_preflight_policy": SHORTS_JA_CAPTION_PREFLIGHT_POLICY,
            "audio_mix_preset": "narration_only_v1",
            "children": children,
            "timeline": timeline,
            "master": master,
            "qc": {"verdict": "pass", "report_artifacts": reports},
            "artifacts": [master, *reports],
        }
        public = detailed_test_video_public_result(
            raw,
            production_id=PRODUCTION_ID,
            run_id=raw["run_id"],
            revision_id=raw["revision_id"],
            request_key=REQUEST_KEY,
            payload=_payload(),
        )
        self.assertEqual(set(public["children"]), {"narration", "timeline", "assembly", "qc"})
        self.assertEqual(
            set(public["children"]["timeline"]),
            {"stage", "status", "job_id", "stage_attempt_id", "cache_hit"},
        )


class DetailedTestVideoOrchestratorTests(unittest.TestCase):
    def _identity(self) -> tuple[dict[str, object], list[dict[str, object]], str]:
        payload = validate_detailed_test_video_payload(_payload())
        sources = _source_identity()
        request_key = detailed_test_video_key(
            payload,
            source_clips=sources,
            remotion_cache_key=REMOTION_KEY,
        )
        return payload, sources, request_key

    def test_runs_four_stages_in_order_and_reports_safe_progress(self) -> None:
        payload, sources, request_key = self._identity()
        run_id = "run_" + "4" * 32
        revision_id = "rev_" + "5" * 32
        service = _FakeDetailedService(
            run_id,
            revision_id,
            request_key,
            timeline_cache_key=REMOTION_KEY,
        )
        context = JobExecutionContext("job_" + "9" * 32)
        result = run_detailed_test_video(
            service,
            production_id=PRODUCTION_ID,
            run_id=run_id,
            revision_id=revision_id,
            payload=payload,
            source_clips=sources,
            expected_remotion_cache_key=REMOTION_KEY,
            expected_request_key=request_key,
            expected_duration_ms=125,
            cancel_event=context,
        )
        self.assertEqual(service.order, ["narration", "timeline", "assembly", "qc"])
        self.assertEqual(set(result["children"]), set(service.order))
        self.assertTrue(
            all(
                set(child)
                == {"stage", "status", "job_id", "stage_attempt_id", "cache_hit"}
                for child in result["children"].values()
            )
        )
        progress = service.database.progress
        self.assertEqual([value for value, _phase in progress], sorted(value for value, _phase in progress))
        self.assertEqual(
            {phase for _value, phase in progress},
            {"narration", "timeline", "assembly", "qc", "finalizing"},
        )

    def test_private_announcement_schedule_reaches_only_narration_child(self) -> None:
        payload = validate_detailed_test_video_payload(_payload())
        sources = _source_identity()
        schedule = (0,)
        request_key = detailed_test_video_key(
            payload,
            source_clips=sources,
            remotion_cache_key=REMOTION_KEY,
            narration_segment_start_ms=schedule,
        )
        run_id = "run_" + "d" * 32
        revision_id = "rev_" + "e" * 32
        service = _FakeDetailedService(
            run_id,
            revision_id,
            request_key,
            timeline_cache_key=REMOTION_KEY,
        )
        result = run_detailed_test_video(
            service,
            production_id=PRODUCTION_ID,
            run_id=run_id,
            revision_id=revision_id,
            payload=payload,
            source_clips=sources,
            expected_remotion_cache_key=REMOTION_KEY,
            expected_request_key=request_key,
            expected_duration_ms=125,
            cancel_event=JobExecutionContext("job_" + "f" * 32),
            narration_segment_start_ms=schedule,
        )
        assert service.narration_private_args is not None
        self.assertIs(
            service.narration_private_args["capability"],
            service._announcement_narration_timing_capability,
        )
        self.assertEqual(service.narration_private_args["segment_start_ms"], [0])
        self.assertEqual(service.narration_private_args["request_key"], request_key)
        self.assertEqual(
            result["narration_alignment_policy"],
            "announcement_scene_starts_v1",
        )
        self.assertEqual(result["narration_segment_start_ms"], [0])

    def test_rejects_timeline_child_cache_identity_race(self) -> None:
        payload, sources, request_key = self._identity()
        run_id = "run_" + "6" * 32
        revision_id = "rev_" + "7" * 32
        service = _FakeDetailedService(
            run_id,
            revision_id,
            request_key,
            timeline_cache_key="D" * 64,
        )
        with self.assertRaisesRegex(DetailedTestVideoError, "provenance"):
            run_detailed_test_video(
                service,
                production_id=PRODUCTION_ID,
                run_id=run_id,
                revision_id=revision_id,
                payload=payload,
                source_clips=sources,
                expected_remotion_cache_key=REMOTION_KEY,
                expected_request_key=request_key,
                expected_duration_ms=125,
                cancel_event=JobExecutionContext("job_" + "8" * 32),
            )

    def test_shutdown_cancellation_preserves_parent_intent_for_child(self) -> None:
        payload, _sources, request_key = self._identity()
        run_id = "run_" + "a" * 32
        revision_id = "rev_" + "b" * 32
        service = _FakeDetailedService(
            run_id,
            revision_id,
            request_key,
            timeline_cache_key=REMOTION_KEY,
        )
        context = JobExecutionContext("job_" + "c" * 32)

        def stop_for_shutdown(_job_id: str, timeout: float) -> None:
            del timeout
            context.set_for_shutdown()
            return None

        with mock.patch.object(service.jobs, "wait", side_effect=stop_for_shutdown):
            with self.assertRaises(JobCancelled):
                detailed_module._wait_for_stage(
                    service,
                    "narration",
                    PRODUCTION_ID,
                    run_id,
                    {
                        "segments": payload["segments"],
                        "voice": payload["voice"],
                        "rate": payload["rate"],
                        "pronunciations": payload["pronunciations"],
                    },
                    context,
                )
        self.assertEqual(service.jobs.cancel_calls, [True])


class DetailedTestVideoDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.database = StudioDatabase(
            self.workspace / "studio.sqlite3", workspace=self.workspace
        )
        _index_empty_production(self.database)
        changes, plan = _run_plan()
        self.revision, self.run = self.database.create_revision_and_run(
            PRODUCTION_ID,
            changes,
            plan,
            0,
            "USD",
            execution_profile="local_sapi",
            detailed_test_video_key=REQUEST_KEY,
        )
        self.job_payload = {
            "production_id": PRODUCTION_ID,
            "run_id": self.run["id"],
            "revision_id": self.revision["id"],
            "request_key": REQUEST_KEY,
            "execution_profile": "local_sapi",
            "stage": "detailed_test_video",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_schema_v6_migrates_to_v7_claim_table(self) -> None:
        with self.database.transaction() as connection:
            connection.execute("DROP TABLE detailed_test_video_claims")
            connection.execute(
                "UPDATE schema_meta SET value='6' WHERE key='schema_version'"
            )
        migrated = StudioDatabase(
            self.workspace / "studio.sqlite3", workspace=self.workspace
        )
        with migrated.session() as connection:
            version = connection.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='detailed_test_video_claims'"
            ).fetchone()
        self.assertEqual(version, str(SCHEMA_VERSION))
        self.assertIsNotNone(table)

    def test_failed_and_interrupted_top_retry_on_same_immutable_run(self) -> None:
        prior_id = None
        for status in ("failed", "interrupted"):
            job, created = self.database.create_or_get_detailed_test_video_job(
                production_id=PRODUCTION_ID,
                run_id=self.run["id"],
                request_key=REQUEST_KEY,
                payload=self.job_payload,
                reuse_succeeded=False,
            )
            self.assertTrue(created)
            self.assertNotEqual(job["id"], prior_id)
            self.database.update_job(job["id"], status)
            prior_id = job["id"]
        retried, created = self.database.create_or_get_detailed_test_video_job(
            production_id=PRODUCTION_ID,
            run_id=self.run["id"],
            request_key=REQUEST_KEY,
            payload=self.job_payload,
            reuse_succeeded=False,
        )
        self.assertTrue(created)
        self.assertNotEqual(retried["id"], prior_id)
        claim = self.database.get_detailed_test_video_claim(PRODUCTION_ID, REQUEST_KEY)
        assert claim is not None
        self.assertEqual(claim["run_id"], self.run["id"])
        self.assertEqual(claim["revision_id"], self.revision["id"])

    def test_claim_is_restored_from_hash_verified_revision_event(self) -> None:
        self.database.sync_event_mirror()
        rebuilt = StudioDatabase(
            self.workspace / "rebuilt.sqlite3", workspace=self.workspace
        )
        _index_empty_production(rebuilt)
        restored = rebuilt.restore_domain_records_from_events()
        claim = rebuilt.get_detailed_test_video_claim(PRODUCTION_ID, REQUEST_KEY)
        assert claim is not None
        self.assertEqual(claim["run_id"], self.run["id"])
        self.assertEqual(claim["revision_id"], self.revision["id"])
        self.assertGreaterEqual(restored["detailed_test_video_claims"], 1)

    def test_queue_admission_failure_is_retired_and_explicit_retry_is_admitted(self) -> None:
        manager = JobManager(self.database)
        try:
            queue = manager._queues["pipeline"]
            with mock.patch.object(queue, "put", side_effect=RuntimeError("queue closed")):
                with self.assertRaisesRegex(RuntimeError, "queue closed"):
                    manager.submit_detailed_test_video_once(
                        production_id=PRODUCTION_ID,
                        run_id=self.run["id"],
                        request_key=REQUEST_KEY,
                        payload=self.job_payload,
                        callback=lambda _job_id, _cancel: {"ok": True},
                        reuse_succeeded=False,
                    )
            failed = self.database.find_latest_job_for_run(
                "detailed_test_video", PRODUCTION_ID, self.run["id"]
            )
            assert failed is not None
            self.assertEqual(failed["status"], "failed")
            retried, created = manager.submit_detailed_test_video_once(
                production_id=PRODUCTION_ID,
                run_id=self.run["id"],
                request_key=REQUEST_KEY,
                payload=self.job_payload,
                callback=lambda _job_id, _cancel: {"ok": True},
                reuse_succeeded=False,
            )
            self.assertTrue(created)
            completed = manager.wait(retried["id"], timeout=5)
            assert completed is not None
            self.assertEqual(completed["status"], "succeeded")
        finally:
            manager.shutdown(timeout=2)


class DetailedTestVideoServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    @staticmethod
    def _tool_identity(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "remotion": {"version": "4.0.517", "sha256": "E" * 64},
            "chromium": {"version": "151.0.7922.34", "sha256": "F" * 64},
        }

    def test_one_click_success_dedupe_and_tamper_self_repair_on_same_run(self) -> None:
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        source = next(item for item in detail["artifacts"] if item["kind"] == "video")
        body = _payload(artifact_id=source["id"])
        with (
            mock.patch(
                "tools.studio.remotion_timeline.resolve_remotion_tool_identity",
                side_effect=self._tool_identity,
            ),
            mock.patch(
                "tools.studio.remotion_timeline.generate_remotion_timeline",
                side_effect=_fake_generate_remotion,
            ),
            mock.patch(
                "tools.studio.remotion_timeline.validate_remotion_timeline_outputs",
                side_effect=_fake_validate_remotion,
            ),
            mock.patch(
                "tools.studio.narration.generate_local_narration",
                side_effect=fake_local_narration_result,
            ),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=fake_local_assembly_result,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=fake_validate_local_assembly_outputs,
            ),
            mock.patch(
                "tools.studio.qc.generate_local_qc",
                side_effect=fake_local_qc_result,
            ),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=fake_validate_local_qc_outputs,
            ),
        ):
            first = self.service.execute_detailed_test_video(PRODUCTION_ID, body)
            completed_first = self.service.jobs.wait(first["id"], timeout=15)
            assert completed_first is not None
            self.assertEqual(completed_first["status"], "succeeded", completed_first)
            self.assertEqual(
                set(completed_first["result"]["children"]),
                {"narration", "timeline", "assembly", "qc"},
            )
            self.assertTrue(
                all(
                    child["status"] == "succeeded"
                    for child in completed_first["result"]["children"].values()
                )
            )

            second = self.service.execute_detailed_test_video(PRODUCTION_ID, body)
            self.assertTrue(second["deduplicated"])
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(second["run_id"], first["run_id"])

            master_path = self.fixture.root / completed_first["result"]["master"]["rel_path"]
            master_path.unlink()
            repaired = self.service.execute_detailed_test_video(PRODUCTION_ID, body)
            self.assertFalse(repaired["deduplicated"])
            self.assertNotEqual(repaired["id"], first["id"])
            self.assertEqual(repaired["run_id"], first["run_id"])
            completed_repair = self.service.jobs.wait(repaired["id"], timeout=15)
            assert completed_repair is not None
            self.assertEqual(completed_repair["status"], "succeeded", completed_repair)
            self.assertTrue(master_path.is_file())


class DetailedTestVideoHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "detailed-test-session-token-at-least-32-characters"
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

    def test_closed_production_endpoint_returns_202_and_delegates_exact_body(self) -> None:
        detail = self.server.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        source = next(item for item in detail["artifacts"] if item["kind"] == "video")
        body = _payload(artifact_id=source["id"])
        expected = {
            "id": "job_" + "d" * 32,
            "kind": "detailed_test_video",
            "status": "queued",
        }
        with mock.patch.object(
            self.server.service,
            "execute_detailed_test_video",
            return_value=expected,
        ) as execute:
            encoded = json.dumps(body).encode("utf-8")
            self.connection.request(
                "POST",
                f"/api/productions/{PRODUCTION_ID}/execute-detailed-test-video",
                body=encoded,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(encoded)),
                    "X-Studio-Token": self.token,
                },
            )
            response = self.connection.getresponse()
            payload = json.loads(response.read())
        self.assertEqual(response.status, 202)
        self.assertEqual(payload, expected)
        execute.assert_called_once_with(PRODUCTION_ID, body)


if __name__ == "__main__":
    unittest.main()
