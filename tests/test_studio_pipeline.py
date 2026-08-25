from __future__ import annotations

import hashlib
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tools.studio.assembly_execution import (
    CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
)
from tools.studio.comfyui_execution import COMFYUI_WORKFLOW_PRESET
from tools.studio.comfyui_execution import (
    COMFYUI_WORKFLOW_FILE_BYTES,
    COMFYUI_WORKFLOW_FILE_SHA256,
    COMFYUI_WORKFLOW_GRAPH_SHA256,
    COMFYUI_WORKFLOW_RELATIVE_PATH,
    MODEL_SPECS as COMFYUI_MODEL_SPECS,
    RUNTIME_FILE_SPECS as COMFYUI_RUNTIME_FILE_SPECS,
    RUNTIME_REPOSITORY_SPECS as COMFYUI_RUNTIME_REPOSITORY_SPECS,
)
from tools.studio.database import AtomicStageCompletion
from tools.studio.jobs import JobCancelled, JobExecutionContext
from tools.studio.pipeline import (
    LocalPipelineError,
    local_pipeline_audit_payload,
    local_pipeline_key,
    run_local_pipeline,
    validate_local_pipeline_payload,
)
from tools.studio.service import RequestValidationError, StudioService

from tests.test_studio_backend import (
    PRODUCTION_ID as FIXTURE_PRODUCTION_ID,
    VIDEO_BYTES,
    WorkspaceFixture,
    fake_local_assembly_result,
    fake_local_narration_result,
    fake_local_qc_result,
    fake_local_timeline_result,
    fake_validate_local_assembly_outputs,
    fake_validate_local_qc_outputs,
    fake_validate_local_timeline_outputs,
)


PRODUCTION_ID = "PIPELINE_20260825_short"
RUN_ID = "run_" + "1" * 32
REVISION_ID = "rev_" + "2" * 32
PIPELINE_COMFY_CACHE_KEY = "9" * 64


def _payload(*, seed: int = 2**63 - 1) -> dict[str, Any]:
    return {
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt": "A private photoreal Japanese presenter prompt.",
        "seed": seed,
        "segments": [{"text": "一括生成の短いテストです。"}],
        "rate": 0,
        "include_captioned": True,
        "caption_style_preset": CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
        "variant": "captioned",
    }


def _artifact(index: int, name: str, kind: str, media_type: str) -> dict[str, Any]:
    return {
        "id": f"art_{index:032x}",
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "rel_path": f"outputs/studio/fake/{index}/{name}",
        "bytes": index + 10,
        "sha256": hashlib.sha256(name.encode("utf-8")).hexdigest().upper(),
    }


def _comfyui_inputs() -> dict[str, Any]:
    workflow_record = {
        "path": COMFYUI_WORKFLOW_RELATIVE_PATH,
        "bytes": COMFYUI_WORKFLOW_FILE_BYTES,
        "sha256": COMFYUI_WORKFLOW_FILE_SHA256,
        "graph_sha256": COMFYUI_WORKFLOW_GRAPH_SHA256,
    }
    model_files = {
        role: {
            "path": spec["relative_path"],
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }
        for role, spec in COMFYUI_MODEL_SPECS.items()
    }
    runtime_identity: dict[str, Any] = {
        role: {
            "path": spec["relative_path"],
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }
        for role, spec in COMFYUI_RUNTIME_FILE_SPECS.items()
    }
    runtime_identity["repositories"] = {
        role: {
            "path": spec["relative_path"],
            "revision": spec["revision"],
            "tracked_clean": True,
        }
        for role, spec in COMFYUI_RUNTIME_REPOSITORY_SPECS.items()
    }
    return {
        "workflow": {"test": True},
        "workflow_source_path": COMFYUI_WORKFLOW_RELATIVE_PATH,
        "workflow_source_bytes": COMFYUI_WORKFLOW_FILE_BYTES,
        "workflow_source_sha256": COMFYUI_WORKFLOW_FILE_SHA256,
        "workflow_record": workflow_record,
        "model_files": model_files,
        "runtime_identity": runtime_identity,
        "ffprobe_identity": {
            "path": "ffprobe",
            "version": "test",
            "sha256": "F" * 64,
        },
        "cache_key": PIPELINE_COMFY_CACHE_KEY,
        "output_roots": ["outputs"],
    }


_FAKE_COMFY_PROVIDER_IDS: dict[tuple[str, str, str], str] = {}


def _fake_local_comfyui_result(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    del production_id
    expected_cache_key = kwargs.get("expected_cache_key")
    if expected_cache_key is not None and expected_cache_key != PIPELINE_COMFY_CACHE_KEY:
        raise AssertionError("pipeline ComfyUI cache identity changed")
    callback = kwargs.get("on_provider_task_id")
    identity_key = (
        str(workspace.resolve()),
        run_id,
        str(expected_cache_key or PIPELINE_COMFY_CACHE_KEY),
    )
    prompt_id = kwargs.get("prepared_prompt_id") or kwargs.get("resume_prompt_id")
    if isinstance(prompt_id, str):
        _FAKE_COMFY_PROVIDER_IDS[identity_key] = prompt_id
    else:
        prompt_id = _FAKE_COMFY_PROVIDER_IDS.get(
            identity_key, "11111111-1111-4111-8111-111111111111"
        )
    if callable(callback):
        callback(prompt_id)
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "video_generation"
        / PIPELINE_COMFY_CACHE_KEY
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "generated-video.mp4": ("video", "video/mp4", VIDEO_BYTES),
        "workflow.json": ("document", "application/json", b"{}\n"),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    artifacts = []
    for name, (kind, media_type, content) in files.items():
        path = output_directory / name
        path.write_bytes(content)
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
    return {
        "artifacts": artifacts,
        "duration_ms": 5_167,
        "cache_key": PIPELINE_COMFY_CACHE_KEY,
        "cache_hit": False,
        "provider": "comfyui",
        "provider_task_id": prompt_id,
        "prompt_id": prompt_id,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_sha256": hashlib.sha256(
            payload["prompt"].encode("utf-8")
        ).hexdigest().upper(),
        "seed": payload["seed"],
    }


class _FakeDatabase:
    def __init__(self, pipeline_key: str) -> None:
        self.pipeline_key = pipeline_key
        self.attempts: dict[str, dict[str, Any]] = {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        if run_id != RUN_ID:
            return None
        return {
            "id": RUN_ID,
            "production_id": PRODUCTION_ID,
            "revision_id": REVISION_ID,
            "execution_profile": "local_pipeline",
            "pipeline_key": self.pipeline_key,
            "requested_stages": [
                "narration",
                "captions",
                "video_generation",
                "timeline",
                "assembly",
                "qc",
            ],
            "estimated_cost": {"amount": "0.00", "currency": "USD"},
        }

    def get_stage_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        return self.attempts.get(attempt_id)


class _FakeJobs:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.cancelled: list[str] = []
        self.cancel_preserve: list[bool] = []

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        del timeout
        return self.records.get(job_id)

    def cancel_and_wait(
        self,
        job_id: str,
        *,
        timeout: float | None = None,
        preserve_provider_task: bool = False,
    ) -> dict[str, Any] | None:
        del timeout
        self.cancelled.append(job_id)
        self.cancel_preserve.append(preserve_provider_task)
        return self.records.get(job_id)


class _FakeService:
    def __init__(self, payload: dict[str, Any], *, narration_duration: int = 1_000) -> None:
        self.key = local_pipeline_key(payload)
        self.database = _FakeDatabase(self.key)
        self.jobs = _FakeJobs()
        self.order: list[str] = []
        self.lineages: dict[str, dict[str, Any]] = {}
        self.narration_duration = narration_duration

    def _execute_local_pipeline_stage(
        self,
        run_id: str,
        stage: str,
        payload: dict[str, Any],
        *,
        pipeline_key: str,
        lineage: dict[str, Any],
    ) -> dict[str, Any]:
        del payload
        if run_id != RUN_ID or pipeline_key != self.key:
            raise AssertionError("pipeline provenance changed")
        self.order.append(stage)
        self.lineages[stage] = lineage
        index = len(self.order)
        job_id = f"job_{index:032x}"
        attempt_id = f"attempt_{index:032x}"
        result: dict[str, Any] = {"cache_hit": False, "artifacts": []}
        if stage == "narration":
            result["duration_ms"] = self.narration_duration
        elif stage == "video_generation":
            result.update(
                {
                    "duration_ms": 5_167,
                    "artifacts": [
                        _artifact(1, "generated-video.mp4", "video", "video/mp4")
                    ],
                }
            )
        elif stage == "timeline":
            result.update(
                {
                    "duration_ms": 5_167,
                    "artifacts": [
                        _artifact(2, "timeline-preview.mp4", "video", "video/mp4")
                    ],
                }
            )
        elif stage == "assembly":
            result.update(
                {
                    "duration_ms": 5_167,
                    "artifacts": [
                        _artifact(3, "master-clean.mp4", "video", "video/mp4"),
                        _artifact(4, "master-captioned.mp4", "video", "video/mp4"),
                    ],
                }
            )
        elif stage == "qc":
            result.update(
                {
                    "analysis_status": "succeeded",
                    "technical_verdict": "pass",
                    "artifacts": [
                        _artifact(5, "technical-qc.json", "document", "application/json"),
                        _artifact(6, "ffprobe.json", "document", "application/json"),
                        _artifact(7, "manifest.json", "document", "application/json"),
                    ],
                }
            )
        public_result = {"stage_attempt_id": attempt_id, **result}
        record = {
            "id": job_id,
            "status": "succeeded",
            "result": public_result,
        }
        self.jobs.records[job_id] = record
        self.database.attempts[attempt_id] = {
            "id": attempt_id,
            "job_id": job_id,
            "run_id": RUN_ID,
            "stage": stage,
            "status": "succeeded",
            "result": result,
        }
        return {**record, "stage_attempt_id": attempt_id}


class LocalPipelineContractTests(unittest.TestCase):
    def test_validation_and_audit_keep_int64_seed_and_omit_private_text(self) -> None:
        payload = _payload()
        normalized = validate_local_pipeline_payload(payload)
        self.assertEqual(normalized["seed"], 2**63 - 1)
        key = local_pipeline_key(normalized)
        audit = local_pipeline_audit_payload(normalized, pipeline_key=key)
        self.assertEqual(audit["seed_decimal"], str(2**63 - 1))
        serialized = repr(audit)
        self.assertNotIn(payload["prompt"], serialized)
        self.assertNotIn(payload["segments"][0]["text"], serialized)

    def test_complete_pipeline_preserves_exact_stage_lineage(self) -> None:
        payload = _payload(seed=42)
        service = _FakeService(payload)
        context = JobExecutionContext("job_" + "f" * 32)
        result = run_local_pipeline(
            service,
            production_id=PRODUCTION_ID,
            run_id=RUN_ID,
            revision_id=REVISION_ID,
            payload=payload,
            expected_pipeline_key=service.key,
            cancel_event=context,
        )
        self.assertEqual(
            service.order,
            ["video_generation", "narration", "timeline", "assembly", "qc"],
        )
        self.assertEqual(
            service.lineages["timeline"]["video_artifact"]["id"],
            result["video"]["id"],
        )
        self.assertEqual(
            service.lineages["assembly"]["timeline_artifact"]["id"],
            result["timeline"]["id"],
        )
        self.assertEqual(
            service.lineages["qc"]["master_artifact"]["id"],
            result["master"]["id"],
        )
        self.assertEqual(result["technical_verdict"], "pass")
        self.assertEqual(len(result["artifacts"]), 4)

    def test_shutdown_intent_is_propagated_to_current_child(self) -> None:
        payload = _payload(seed=421)
        service = _FakeService(payload)
        context = JobExecutionContext("job_" + "d" * 32)
        original_wait = service.jobs.wait

        def interrupting_wait(
            job_id: str, timeout: float = 30.0
        ) -> dict[str, Any] | None:
            record = original_wait(job_id, timeout)
            context.set_for_shutdown()
            return {**record, "status": "running"} if record is not None else None

        service.jobs.wait = interrupting_wait
        with self.assertRaises(JobCancelled):
            run_local_pipeline(
                service,
                production_id=PRODUCTION_ID,
                run_id=RUN_ID,
                revision_id=REVISION_ID,
                payload=payload,
                expected_pipeline_key=service.key,
                cancel_event=context,
            )
        self.assertEqual(service.jobs.cancel_preserve, [True])

    def test_long_narration_stops_before_timeline(self) -> None:
        payload = _payload(seed=43)
        service = _FakeService(payload, narration_duration=5_500)
        with self.assertRaises(LocalPipelineError) as raised:
            run_local_pipeline(
                service,
                production_id=PRODUCTION_ID,
                run_id=RUN_ID,
                revision_id=REVISION_ID,
                payload=payload,
                expected_pipeline_key=service.key,
                cancel_event=JobExecutionContext("job_" + "e" * 32),
            )
        self.assertEqual(raised.exception.error_code, "narration_longer_than_source")
        self.assertEqual(service.order, ["video_generation", "narration"])


class LocalPipelineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    @staticmethod
    def _request(*, prompt: str, script: str, seed: int = 7) -> dict[str, Any]:
        return {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": prompt,
            "seed": seed,
            "segments": [{"text": script}],
            "rate": 0,
            "include_captioned": True,
            "caption_style_preset": CAPTION_STYLE_PRESET_SHORTS_JA_LARGE_V1,
            "variant": "captioned",
        }

    def _registered_pipeline_artifact(
        self,
        *,
        run_id: str,
        pipeline_key: str,
        stage: str,
        cache_key: str,
        name: str,
        kind: str,
        media_type: str,
    ) -> dict[str, Any]:
        relative = f"outputs/studio/runs/{run_id}/{stage}/{cache_key}/{name}"
        path = self.fixture.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"pipeline-test:{run_id}:{pipeline_key}:{stage}:{cache_key}:{name}\n"
        ).encode("utf-8")
        path.write_bytes(content)
        stat = path.stat()
        record = self.service.database.register_studio_artifact(
            FIXTURE_PRODUCTION_ID,
            {
                "id": "art_" + hashlib.sha256(relative.casefold().encode()).hexdigest()[:32],
                "rel_path": relative,
                "name": name,
                "kind": kind,
                "media_type": media_type,
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": hashlib.sha256(content).hexdigest().upper(),
                "is_heavy": False,
            },
        )
        return {
            key: record[key]
            for key in (
                "id",
                "name",
                "kind",
                "media_type",
                "rel_path",
                "bytes",
                "sha256",
            )
        }

    def _registered_pipeline_child(
        self,
        *,
        run_id: str,
        pipeline_key: str,
        stage: str,
        kind: str,
        cache_key: str,
        artifacts: list[dict[str, Any]],
        lineage: dict[str, Any],
        result_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt = self.service.database.create_stage_attempt(
            run_id,
            stage,
            cache_key,
            {
                "execution_profile": "local_pipeline",
                "pipeline_key": pipeline_key,
                "test_fixture": True,
            },
        )
        job = self.service.database.create_job(
            kind,
            {
                "run_id": run_id,
                "production_id": FIXTURE_PRODUCTION_ID,
                "stage": stage,
                "execution_profile": "local_pipeline",
                "pipeline_key": pipeline_key,
                "pipeline_lineage": lineage,
                "stage_attempt_id": attempt["id"],
            },
            production_id=FIXTURE_PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(attempt["id"], job["id"])
        self.service.database.update_job(job["id"], "running")
        self.service.database.update_stage_attempt(attempt["id"], "running")
        self.service.database.complete_job_with_stage_attempt(
            job["id"],
            attempt["id"],
            {
                "cache_hit": False,
                "artifacts": artifacts,
                **(result_fields or {}),
            },
        )
        return {
            "job_id": job["id"],
            "stage_attempt_id": attempt["id"],
            "cache_hit": False,
        }

    def _success(self, **kwargs: Any) -> dict[str, Any]:
        qc_child_verdict = kwargs.pop("_qc_child_verdict", "pass")
        payload = kwargs["payload"]
        run_id = kwargs["run_id"]
        pipeline_key = kwargs["expected_pipeline_key"]
        cache_keys = {
            "video_generation": "1" * 64,
            "narration": "2" * 64,
            "timeline": "3" * 64,
            "assembly": "4" * 64,
            "qc": "5" * 64,
        }
        artifact_specs = {
            "video_generation": (
                ("generated-video.mp4", "video", "video/mp4"),
                ("workflow.json", "document", "application/json"),
                ("ffprobe.json", "document", "application/json"),
                ("manifest.json", "document", "application/json"),
            ),
            "narration": (
                ("narration.wav", "audio", "audio/wav"),
                ("captions.srt", "subtitle", "application/x-subrip"),
                ("timings.json", "document", "application/json"),
                ("manifest.json", "document", "application/json"),
            ),
            "timeline": (
                ("timeline-preview.mp4", "video", "video/mp4"),
                ("timeline.json", "document", "application/json"),
                ("ffprobe.json", "document", "application/json"),
                ("manifest.json", "document", "application/json"),
            ),
            "assembly": (
                ("master-clean.mp4", "video", "video/mp4"),
                ("master-captioned.mp4", "video", "video/mp4"),
                ("ffprobe.json", "document", "application/json"),
                ("manifest.json", "document", "application/json"),
            ),
            "qc": (
                ("technical-qc.json", "document", "application/json"),
                ("ffprobe.json", "document", "application/json"),
                ("manifest.json", "document", "application/json"),
            ),
        }
        stage_artifacts = {
            stage: [
                self._registered_pipeline_artifact(
                    run_id=run_id,
                    pipeline_key=pipeline_key,
                    stage=stage,
                    cache_key=cache_keys[stage],
                    name=name,
                    kind=kind,
                    media_type=media_type,
                )
                for name, kind, media_type in specs
            ]
            for stage, specs in artifact_specs.items()
        }
        video = next(
            item
            for item in stage_artifacts["video_generation"]
            if item["name"] == "generated-video.mp4"
        )
        timeline = next(
            item
            for item in stage_artifacts["timeline"]
            if item["name"] == "timeline-preview.mp4"
        )
        master_name = (
            "master-captioned.mp4"
            if payload["variant"] == "captioned"
            else "master-clean.mp4"
        )
        master = next(
            item
            for item in stage_artifacts["assembly"]
            if item["name"] == master_name
        )
        reports = list(stage_artifacts["qc"])
        video_job = self._registered_pipeline_child(
            run_id=run_id,
            pipeline_key=pipeline_key,
            stage="video_generation",
            kind="local_video_generation",
            cache_key=cache_keys["video_generation"],
            artifacts=stage_artifacts["video_generation"],
            lineage={},
            result_fields={"duration_ms": 5_167},
        )
        narration_job = self._registered_pipeline_child(
            run_id=run_id,
            pipeline_key=pipeline_key,
            stage="narration",
            kind="local_narration",
            cache_key=cache_keys["narration"],
            artifacts=stage_artifacts["narration"],
            lineage={
                "video_generation_attempt_id": video_job["stage_attempt_id"]
            },
        )
        timeline_job = self._registered_pipeline_child(
            run_id=run_id,
            pipeline_key=pipeline_key,
            stage="timeline",
            kind="local_timeline",
            cache_key=cache_keys["timeline"],
            artifacts=stage_artifacts["timeline"],
            lineage={
                "video_generation_attempt_id": video_job["stage_attempt_id"],
                "narration_attempt_id": narration_job["stage_attempt_id"],
                "video_artifact_id": video["id"],
                "video_artifact_sha256": video["sha256"],
            },
        )
        assembly_job = self._registered_pipeline_child(
            run_id=run_id,
            pipeline_key=pipeline_key,
            stage="assembly",
            kind="local_assembly",
            cache_key=cache_keys["assembly"],
            artifacts=stage_artifacts["assembly"],
            lineage={
                "narration_attempt_id": narration_job["stage_attempt_id"],
                "timeline_attempt_id": timeline_job["stage_attempt_id"],
                "timeline_artifact_id": timeline["id"],
                "timeline_artifact_sha256": timeline["sha256"],
            },
        )
        qc_job = self._registered_pipeline_child(
            run_id=run_id,
            pipeline_key=pipeline_key,
            stage="qc",
            kind="local_qc",
            cache_key=cache_keys["qc"],
            artifacts=stage_artifacts["qc"],
            lineage={
                "assembly_attempt_id": assembly_job["stage_attempt_id"],
                "master_artifact_id": master["id"],
                "master_artifact_sha256": master["sha256"],
            },
            result_fields={
                "analysis_status": "succeeded",
                "technical_verdict": qc_child_verdict,
            },
        )
        jobs = {
            "video_generation": video_job,
            "narration": narration_job,
            "timeline": timeline_job,
            "assembly": assembly_job,
            "qc": qc_job,
        }
        return {
            "production_id": kwargs["production_id"],
            "run_id": run_id,
            "revision_id": kwargs["revision_id"],
            "pipeline_key": pipeline_key,
            "execution_profile": "local_pipeline",
            "workflow_preset": payload["workflow_preset"],
            "prompt_sha256": hashlib.sha256(
                payload["prompt"].encode("utf-8")
            ).hexdigest().upper(),
            "seed_decimal": str(payload["seed"]),
            "duration_ms": 5_167,
            "technical_verdict": "pass",
            "variant": payload["variant"],
            "caption_style_preset": payload["caption_style_preset"],
            "jobs": jobs,
            "video": video,
            "timeline": timeline,
            "master": master,
            "qc": {"verdict": "pass", "report_artifacts": reports},
            "artifacts": [master, *reports],
        }

    def test_concurrent_submission_claims_one_run_and_one_top_job_without_text(self) -> None:
        prompt = "CANARY_PIPELINE_PROMPT_9f30b4"
        script = "CANARY_PIPELINE_SCRIPT_128ab7"
        body = self._request(prompt=prompt, script=script, seed=2**63 - 1)
        started = threading.Event()
        release = threading.Event()
        responses: list[dict[str, Any]] = []
        errors: list[BaseException] = []

        def worker(_service: StudioService, **kwargs: Any) -> dict[str, Any]:
            started.set()
            release.wait(5)
            return self._success(**kwargs)

        def submit() -> None:
            try:
                responses.append(
                    self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        with mock.patch("tools.studio.service.run_local_pipeline", side_effect=worker):
            threads = [threading.Thread(target=submit) for _ in range(16)]
            for thread in threads:
                thread.start()
            self.assertTrue(started.wait(2))
            for thread in threads:
                thread.join(timeout=3)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(len(responses), 16)
            self.assertEqual(len({item["id"] for item in responses}), 1)
            self.assertEqual(len({item["run_id"] for item in responses}), 1)

            run_id = responses[0]["run_id"]
            job_id = responses[0]["id"]
            detail = self.service.production_detail(FIXTURE_PRODUCTION_ID)
            assert detail is not None
            pipeline_runs = [
                run
                for run in detail["runs"]
                if run.get("execution_profile") == "local_pipeline"
            ]
            self.assertEqual(len(pipeline_runs), 1)
            self.assertEqual(pipeline_runs[0]["id"], run_id)
            top_jobs = [
                job
                for job in self.service.database.list_jobs(limit=100)
                if job.get("kind") == "local_pipeline"
            ]
            self.assertEqual([job["id"] for job in top_jobs], [job_id])
            self.assertEqual(
                pipeline_runs[0]["estimated_cost"],
                {"amount": "0.00", "currency": "USD"},
            )
            persisted = self.service.database.path.read_bytes()
            event_text = "".join(
                path.read_text(encoding="utf-8")
                for path in (
                    self.fixture.root / "outputs" / "studio" / "events"
                ).rglob("*.jsonl")
            )
            self.assertNotIn(prompt.encode("utf-8"), persisted)
            self.assertNotIn(script.encode("utf-8"), persisted)
            self.assertNotIn(prompt, event_text)
            self.assertNotIn(script, event_text)

            release.set()
            completed = self.service.jobs.wait(job_id, timeout=15)
            assert completed is not None
            self.assertEqual(completed["status"], "succeeded")
            self.assertEqual(
                {item["name"] for item in completed["result"]["artifacts"]},
                {
                    "master-captioned.mp4",
                    "technical-qc.json",
                    "ffprobe.json",
                    "manifest.json",
                },
            )
            self.assertEqual(len(completed["result"]["artifacts"]), 4)
            for artifact in completed["result"]["artifacts"]:
                registered = self.service.database.get_artifact(artifact["id"])
                self.assertIsNotNone(registered)
                self.assertEqual(registered["sha256"], artifact["sha256"])
                path = self.fixture.root / artifact["rel_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, artifact["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest().upper(),
                    artifact["sha256"],
                )
            duplicate = self.service.execute_local_pipeline(
                FIXTURE_PRODUCTION_ID, body
            )
            self.assertEqual(duplicate["id"], job_id)
            self.assertTrue(duplicate["deduplicated"])

    def test_missing_or_tampered_final_artifact_retries_same_run(self) -> None:
        body = self._request(
            prompt="repairable pipeline portrait",
            script="成果物を検証して再試行します。",
        )
        calls: list[str] = []

        def succeed(_service: StudioService, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs["run_id"])
            return self._success(**kwargs)

        with mock.patch(
            "tools.studio.service.run_local_pipeline", side_effect=succeed
        ):
            first = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            first_done = self.service.jobs.wait(first["id"], timeout=15)
            assert first_done is not None
            self.assertEqual(first_done["status"], "succeeded", first_done)

            missing = next(
                item
                for item in first_done["result"]["artifacts"]
                if item["name"] == "technical-qc.json"
            )
            (self.fixture.root / missing["rel_path"]).unlink()
            second = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            second_done = self.service.jobs.wait(second["id"], timeout=15)
            assert second_done is not None
            self.assertEqual(second_done["status"], "succeeded", second_done)
            self.assertEqual(second["run_id"], first["run_id"])
            self.assertNotEqual(second["id"], first["id"])
            self.assertFalse(second["deduplicated"])

            tampered = next(
                item
                for item in second_done["result"]["artifacts"]
                if item["name"] == "master-captioned.mp4"
            )
            (self.fixture.root / tampered["rel_path"]).write_bytes(
                b"tampered pipeline master"
            )
            third = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            third_done = self.service.jobs.wait(third["id"], timeout=15)
            assert third_done is not None
            self.assertEqual(third_done["status"], "succeeded", third_done)
            self.assertEqual(third["run_id"], first["run_id"])
            self.assertNotEqual(third["id"], second["id"])
            self.assertFalse(third["deduplicated"])

            narration_attempt = self.service.database.get_stage_attempt(
                third_done["result"]["jobs"]["narration"]["stage_attempt_id"]
            )
            assert narration_attempt is not None
            captions = next(
                item
                for item in narration_attempt["result"]["artifacts"]
                if item["name"] == "captions.srt"
            )
            (self.fixture.root / captions["rel_path"]).write_bytes(
                b"tampered intermediate captions"
            )
            fourth = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            fourth_done = self.service.jobs.wait(fourth["id"], timeout=15)
            assert fourth_done is not None
            self.assertEqual(fourth_done["status"], "succeeded", fourth_done)
            self.assertEqual(fourth["run_id"], first["run_id"])
            self.assertNotEqual(fourth["id"], third["id"])
            self.assertFalse(fourth["deduplicated"])

            with mock.patch(
                "tools.studio.service._sha256_file",
                side_effect=OSError("simulated stat-to-hash race"),
            ):
                raced = self.service.execute_local_pipeline(
                    FIXTURE_PRODUCTION_ID, body
                )
            raced_done = self.service.jobs.wait(raced["id"], timeout=15)
            assert raced_done is not None
            self.assertEqual(raced_done["status"], "succeeded", raced_done)
            self.assertEqual(raced["run_id"], first["run_id"])
            self.assertNotEqual(raced["id"], fourth["id"])
            self.assertFalse(raced["deduplicated"])

            valid_duplicate = self.service.execute_local_pipeline(
                FIXTURE_PRODUCTION_ID, body
            )
            self.assertEqual(valid_duplicate["id"], raced["id"])
            self.assertTrue(valid_duplicate["deduplicated"])

        self.assertEqual(
            calls,
            [
                first["run_id"],
                first["run_id"],
                first["run_id"],
                first["run_id"],
                first["run_id"],
            ],
        )

    def test_full_fake_backed_pipeline_runs_all_five_child_stages(self) -> None:
        prompt = "PRIVATE_FULL_PIPELINE_PROMPT_81baf0"
        script = "外部音声APIを使わず、字幕付き動画まで一括生成します。"
        body = self._request(prompt=prompt, script=script, seed=73)
        stage_order: list[str] = []
        original_stage_executor = self.service._execute_local_pipeline_stage

        def recording_stage_executor(
            run_id: str,
            stage: str,
            stage_body: dict[str, Any],
            *,
            pipeline_key: str,
            lineage: dict[str, Any],
        ) -> dict[str, Any]:
            stage_order.append(stage)
            return original_stage_executor(
                run_id,
                stage,
                stage_body,
                pipeline_key=pipeline_key,
                lineage=lineage,
            )

        def assembly_result(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = fake_local_assembly_result(*args, **kwargs)
            result["duration_ms"] = 5_167
            return result

        def validate_assembly(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = fake_validate_local_assembly_outputs(*args, **kwargs)
            result["duration_ms"] = 5_167
            return result

        with (
            mock.patch.object(
                self.service,
                "_resolve_comfyui_execution_inputs",
                return_value=_comfyui_inputs(),
            ),
            mock.patch.object(
                self.service,
                "_execute_local_pipeline_stage",
                side_effect=recording_stage_executor,
            ),
            mock.patch(
                "tools.studio.comfyui.recover_comfyui_prompt_id", return_value=None
            ),
            mock.patch(
                "tools.studio.comfyui.generate_comfyui_video",
                side_effect=_fake_local_comfyui_result,
            ),
            mock.patch(
                "tools.studio.comfyui.validate_comfyui_outputs",
                side_effect=_fake_local_comfyui_result,
            ),
            mock.patch(
                "tools.studio.narration.generate_local_narration",
                side_effect=fake_local_narration_result,
            ),
            mock.patch(
                "tools.studio.service._load_external_tts_contract",
                side_effect=AssertionError(
                    "local_pipeline must not load an external TTS provider"
                ),
            ),
            mock.patch(
                "tools.studio.timeline.timeline_cache_key", return_value="B" * 64
            ),
            mock.patch(
                "tools.studio.timeline.generate_local_timeline",
                side_effect=fake_local_timeline_result,
            ),
            mock.patch(
                "tools.studio.timeline.validate_local_timeline_outputs",
                side_effect=fake_validate_local_timeline_outputs,
            ),
            mock.patch(
                "tools.studio.assembly.assembly_cache_key", return_value="A" * 64
            ),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=assembly_result,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=validate_assembly,
            ),
            mock.patch("tools.studio.qc.qc_cache_key", return_value="E" * 64),
            mock.patch(
                "tools.studio.qc.generate_local_qc", side_effect=fake_local_qc_result
            ),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=fake_validate_local_qc_outputs,
            ),
        ):
            top = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            completed = self.service.jobs.wait(top["id"], timeout=15)

        assert completed is not None
        self.assertEqual(
            completed["status"],
            "succeeded",
            (
                completed,
                stage_order,
                self.service.database.get_run(top["run_id"]),
            ),
        )
        self.assertEqual(
            stage_order,
            ["video_generation", "narration", "timeline", "assembly", "qc"],
        )
        result = completed["result"]
        self.assertEqual(result["technical_verdict"], "pass")
        self.assertEqual(result["variant"], "captioned")
        self.assertEqual(result["master"]["name"], "master-captioned.mp4")
        self.assertEqual(
            set(result["jobs"]),
            {"video_generation", "narration", "timeline", "assembly", "qc"},
        )
        self.assertTrue(
            all(not item["cache_hit"] for item in result["jobs"].values())
        )
        self.assertEqual(
            [item["name"] for item in result["artifacts"]],
            [
                "master-captioned.mp4",
                "technical-qc.json",
                "ffprobe.json",
                "manifest.json",
            ],
        )
        self.assertEqual(
            {item["name"] for item in result["qc"]["report_artifacts"]},
            {"technical-qc.json", "ffprobe.json", "manifest.json"},
        )

        run = self.service.database.get_run(top["run_id"])
        assert run is not None
        attempts = run["stage_attempts"]
        self.assertEqual(len(attempts), 5)
        self.assertEqual(
            {item["stage"] for item in attempts},
            {"video_generation", "narration", "timeline", "assembly", "qc"},
        )
        self.assertTrue(all(item["status"] == "succeeded" for item in attempts))
        child_jobs = [
            job
            for job in self.service.database.list_jobs(limit=100)
            if job["kind"] != "local_pipeline"
        ]
        self.assertEqual(len(child_jobs), 5)
        self.assertEqual(
            {job["kind"] for job in child_jobs},
            {
                "local_video_generation",
                "local_narration",
                "local_timeline",
                "local_assembly",
                "local_qc",
            },
        )
        for stage, stage_view in result["jobs"].items():
            job = self.service.database.get_job(stage_view["job_id"])
            attempt = self.service.database.get_stage_attempt(
                stage_view["stage_attempt_id"]
            )
            assert job is not None and attempt is not None
            with self.subTest(stage=stage):
                self.assertEqual(job["status"], "succeeded")
                self.assertEqual(attempt["status"], "succeeded")
                self.assertEqual(job["payload"]["stage_attempt_id"], attempt["id"])
                self.assertEqual(job["payload"]["pipeline_key"], top["pipeline_key"])

        narration_attempt = next(
            item for item in attempts if item["stage"] == "narration"
        )
        self.assertEqual(narration_attempt["result"]["provider"], "windows_sapi")
        self.assertEqual(narration_attempt["result"]["actual_cost"], 0)
        for artifact in result["artifacts"]:
            registered = self.service.database.get_artifact(artifact["id"])
            self.assertIsNotNone(registered)
            path = self.fixture.root / artifact["rel_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
                artifact["sha256"],
            )
        self.assertNotIn(prompt.encode("utf-8"), self.service.database.path.read_bytes())
        self.assertNotIn(script.encode("utf-8"), self.service.database.path.read_bytes())

    def test_incomplete_top_result_fails_closed(self) -> None:
        mutations = {
            "missing_child_job": lambda result: result["jobs"].pop("qc"),
            "missing_final_artifact": lambda result: result["artifacts"].pop(),
        }
        for index, (name, mutate) in enumerate(mutations.items(), start=1):
            with self.subTest(case=name):
                body = self._request(
                    prompt=f"invalid top result {name}",
                    script="不完全な結果は成功扱いにしません。",
                    seed=80 + index,
                )

                def incomplete(
                    _service: StudioService, **kwargs: Any
                ) -> dict[str, Any]:
                    result = self._success(**kwargs)
                    mutate(result)
                    return result

                with mock.patch(
                    "tools.studio.service.run_local_pipeline",
                    side_effect=incomplete,
                ):
                    top = self.service.execute_local_pipeline(
                        FIXTURE_PRODUCTION_ID, body
                    )
                    completed = self.service.jobs.wait(top["id"], timeout=15)
                assert completed is not None
                self.assertEqual(completed["status"], "failed")
                self.assertEqual(
                    completed["error"]["code"], "invalid_worker_result"
                )
                self.assertIsNone(completed["result"])

    def test_qc_child_fail_cannot_be_overridden_by_top_pass(self) -> None:
        body = self._request(
            prompt="qc mismatch portrait",
            script="品質検査の判定を上書きできません。",
        )

        def mismatched(_service: StudioService, **kwargs: Any) -> dict[str, Any]:
            return self._success(_qc_child_verdict="fail", **kwargs)

        with mock.patch(
            "tools.studio.service.run_local_pipeline", side_effect=mismatched
        ):
            top = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            completed = self.service.jobs.wait(top["id"], timeout=15)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "invalid_worker_result")

    def test_failed_request_retries_same_run_with_new_top_job(self) -> None:
        body = self._request(prompt="retry portrait", script="再試行します。")

        def fail(_service: StudioService, **_kwargs: Any) -> dict[str, Any]:
            raise LocalPipelineError(
                "The local pipeline stage failed: video_generation.",
                code="local_pipeline_stage_failed",
            )

        with mock.patch("tools.studio.service.run_local_pipeline", side_effect=fail):
            first = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            first_done = self.service.jobs.wait(first["id"], timeout=15)
        assert first_done is not None
        self.assertEqual(first_done["status"], "failed")

        with mock.patch(
            "tools.studio.service.run_local_pipeline",
            side_effect=lambda _service, **kwargs: self._success(**kwargs),
        ):
            second = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            second_done = self.service.jobs.wait(second["id"], timeout=15)
        assert second_done is not None
        self.assertEqual(second_done["status"], "succeeded")
        self.assertEqual(second["run_id"], first["run_id"])
        self.assertNotEqual(second["id"], first["id"])
        self.assertFalse(second["deduplicated"])

    def test_changed_request_gets_new_run_and_public_child_route_is_blocked(self) -> None:
        with mock.patch(
            "tools.studio.service.run_local_pipeline",
            side_effect=lambda _service, **kwargs: self._success(**kwargs),
        ):
            first = self.service.execute_local_pipeline(
                FIXTURE_PRODUCTION_ID,
                self._request(prompt="portrait one", script="一つ目です。", seed=1),
            )
            self.service.jobs.wait(first["id"], timeout=15)
            second = self.service.execute_local_pipeline(
                FIXTURE_PRODUCTION_ID,
                self._request(prompt="portrait two", script="二つ目です。", seed=2),
            )
            self.service.jobs.wait(second["id"], timeout=15)
        self.assertNotEqual(first["run_id"], second["run_id"])
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_narration(
                second["run_id"], {"segments": [{"text": "blocked"}], "rate": 0}
            )
        self.assertEqual(raised.exception.code, "execution_profile_required")

    def test_top_cancellation_retires_current_child_before_terminal(self) -> None:
        body = self._request(prompt="cancel portrait", script="中断します。")
        child_started = threading.Event()
        child_ids: list[str] = []

        def queue_child(
            run_id: str,
            stage: str,
            _body: dict[str, Any],
            *,
            pipeline_key: str,
            lineage: dict[str, Any],
        ) -> dict[str, Any]:
            self.assertEqual(stage, "video_generation")
            self.assertEqual(lineage, {})
            attempt = self.service.database.create_stage_attempt(
                run_id,
                stage,
                "C" * 64,
                {
                    "execution_profile": "local_pipeline",
                    "pipeline_key": pipeline_key,
                },
            )

            def child(
                _job_id: str, context: JobExecutionContext
            ) -> AtomicStageCompletion:
                self.service.database.update_stage_attempt(attempt["id"], "running")
                child_started.set()
                context.wait(5)
                context.raise_if_cancelled()
                return AtomicStageCompletion(attempt["id"], {"cache_hit": False})

            job = self.service.jobs.submit(
                "local_video_generation",
                {
                    "run_id": run_id,
                    "production_id": FIXTURE_PRODUCTION_ID,
                    "stage": stage,
                    "execution_profile": "local_pipeline",
                    "pipeline_key": pipeline_key,
                    "stage_attempt_id": attempt["id"],
                },
                child,
                production_id=FIXTURE_PRODUCTION_ID,
                before_enqueue=lambda created: self.service.database.link_stage_attempt_job(
                    attempt["id"], created["id"]
                ),
                lane="gpu",
            )
            child_ids.append(job["id"])
            return {**job, "stage_attempt_id": attempt["id"]}

        with mock.patch.object(
            self.service, "_execute_local_pipeline_stage", side_effect=queue_child
        ):
            top = self.service.execute_local_pipeline(FIXTURE_PRODUCTION_ID, body)
            self.assertTrue(child_started.wait(2))
            completed = self.service.jobs.cancel_and_wait(top["id"], timeout=4)
        assert completed is not None
        self.assertEqual(completed["status"], "interrupted")
        self.assertEqual(len(child_ids), 1)
        child = self.service.database.get_job(child_ids[0])
        assert child is not None
        self.assertEqual(child["status"], "interrupted")
        self.assertTrue(self.service.jobs._finished[child_ids[0]].is_set())
        run = self.service.database.get_run(top["run_id"])
        assert run is not None
        self.assertEqual(
            [(attempt["stage"], attempt["status"]) for attempt in run["stage_attempts"]],
            [("video_generation", "failed")],
        )


if __name__ == "__main__":
    unittest.main()
