from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

from tools.studio.instance_lock import StudioInstanceLockError
from tools.studio.assembly_execution import (
    DEFAULT_CAPTION_STYLE_PRESET,
    LocalAssemblyError,
    normalize_caption_style_preset,
)
from tools.studio.comfyui_execution import (
    COMFYUI_WORKFLOW_FILE_BYTES,
    COMFYUI_WORKFLOW_FILE_SHA256,
    COMFYUI_WORKFLOW_GRAPH_SHA256,
    COMFYUI_WORKFLOW_PRESET,
    COMFYUI_WORKFLOW_RELATIVE_PATH,
    MODEL_SPECS as COMFYUI_MODEL_SPECS,
    RUNTIME_FILE_SPECS as COMFYUI_RUNTIME_FILE_SPECS,
    RUNTIME_REPOSITORY_SPECS as COMFYUI_RUNTIME_REPOSITORY_SPECS,
)
from tools.studio.qc_execution import LocalQcError
from tools.studio.database import (
    SCHEMA_VERSION,
    AtomicCompletionError,
    AtomicStageCompletion,
    StudioDatabase,
)
from tools.studio.secrets import SecretStore, dpapi_available
from tools.studio.security import (
    SecurityError,
    UnsafeTextArtifactError,
    redact_artifact_text,
    workspace_path,
)
from tools.studio.server import create_server
from tools.studio.execution import narration_cache_key
from tools.studio.service import RequestValidationError, StudioService, build_rerun_plan


PRODUCTION_ID = "TEST_20260823_auditable_short"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42studio-video-payload"
RAW_LOG_SECRET = "audit-log-secret-123456"
RAW_JSON_SECRET = "plainprovidercredential123"
RAW_CONFIG_SECRET = "structured-config-secret-123456"
RAW_UNKNOWN_SECRET = "unknown-format-secret-123456"


def fake_local_narration_result(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    del production_id
    cache_key = narration_cache_key(payload)
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "narration"
        / cache_key
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "narration.wav": ("audio", "audio/wav", b"local-audio"),
        "captions.srt": (
            "subtitle",
            "application/x-subrip",
            b"1\n00:00:00,000 --> 00:00:00,125\nhello local narration\n",
        ),
        "timings.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    artifacts = []
    for name, (kind, media_type, content) in files.items():
        output = output_directory / name
        output.write_bytes(content)
        artifacts.append(
            {
                "rel_path": output.relative_to(workspace).as_posix(),
                "kind": kind,
                "media_type": media_type,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    return {
        "artifacts": artifacts,
        "duration_ms": 125,
        "cache_key": cache_key,
        "cache_hit": False,
        "provider": "windows_sapi",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "wav_frames",
    }


def fake_local_assembly_result(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    source_video: Path,
    narration_wav: Path,
    captions_srt: Path,
    include_captioned: bool,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
) -> dict[str, object]:
    del production_id
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "assembly"
        / cache_key
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    files: dict[str, tuple[str, str, bytes]] = {
        "master-clean.mp4": ("video", "video/mp4", b"local-clean-master"),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    if include_captioned:
        files["master-captioned.mp4"] = (
            "video",
            "video/mp4",
            b"local-captioned-master",
        )
    artifacts = []
    for name, (kind, media_type, content) in files.items():
        output = output_directory / name
        output.write_bytes(content)
        artifacts.append(
            {
                "rel_path": output.relative_to(workspace).as_posix(),
                "kind": kind,
                "media_type": media_type,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    caption_style = normalize_caption_style_preset(caption_style_preset)
    return {
        "artifacts": artifacts,
        "duration_ms": 125,
        "cache_key": cache_key,
        "cache_hit": False,
        "provider": "local_ffmpeg",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "caption_style": caption_style,
        "source_video_sha256": hashlib.sha256(source_video.read_bytes()).hexdigest().upper(),
        "narration_wav_sha256": hashlib.sha256(narration_wav.read_bytes()).hexdigest().upper(),
        "captions_sha256": hashlib.sha256(captions_srt.read_bytes()).hexdigest().upper(),
    }


def fake_validate_local_assembly_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    source_video: Path,
    narration_wav: Path,
    captions_srt: Path,
    include_captioned: bool,
    caption_style_preset: str = DEFAULT_CAPTION_STYLE_PRESET,
) -> dict[str, object]:
    del production_id
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "assembly"
        / cache_key
    )
    names = ["master-clean.mp4", "ffprobe.json", "manifest.json"]
    if include_captioned:
        names.insert(1, "master-captioned.mp4")
    artifacts = []
    for name in names:
        path = output_directory / name
        content = path.read_bytes()
        artifacts.append(
            {
                "name": name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    caption_style = normalize_caption_style_preset(caption_style_preset)
    return {
        "artifacts": artifacts,
        "duration_ms": 125,
        "cache_key": cache_key,
        "cache_hit": True,
        "provider": "local_ffmpeg",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "caption_style": caption_style,
        "source_video_sha256": hashlib.sha256(source_video.read_bytes()).hexdigest().upper(),
        "narration_wav_sha256": hashlib.sha256(narration_wav.read_bytes()).hexdigest().upper(),
        "captions_sha256": hashlib.sha256(captions_srt.read_bytes()).hexdigest().upper(),
    }


def _fake_timeline_artifacts(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
) -> list[dict[str, object]]:
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "timeline"
        / cache_key
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "timeline-preview.mp4": ("video", "video/mp4", b"local-timeline-video"),
        "timeline.json": ("document", "application/json", b"{}\n"),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    artifacts: list[dict[str, object]] = []
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
    return artifacts


def fake_local_timeline_result(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: list[dict[str, object]],
    **_kwargs: object,
) -> dict[str, object]:
    del production_id
    return {
        "artifacts": _fake_timeline_artifacts(
            workspace, run_id=run_id, cache_key=cache_key
        ),
        "duration_ms": sum(
            int(item["end_ms"]) - int(item["start_ms"]) for item in clips
        ),
        "cache_key": cache_key,
        "cache_hit": False,
        "provider": "local_ffmpeg_timeline",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
    }


def fake_validate_local_timeline_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: list[dict[str, object]],
    **_kwargs: object,
) -> dict[str, object]:
    del production_id
    artifacts = []
    output_directory = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "timeline"
        / cache_key
    )
    for name in ("timeline-preview.mp4", "timeline.json", "ffprobe.json", "manifest.json"):
        path = output_directory / name
        artifacts.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            }
        )
    return {
        "artifacts": artifacts,
        "duration_ms": sum(
            int(item["end_ms"]) - int(item["start_ms"]) for item in clips
        ),
        "cache_key": cache_key,
        "cache_hit": True,
        "provider": "local_ffmpeg_timeline",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
    }


def _fake_local_qc_metadata(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
    cache_hit: bool,
    technical_verdict: str = "pass",
) -> dict[str, object]:
    output_directory = (
        workspace / "outputs" / "studio" / "runs" / run_id / "qc" / cache_key
    )
    artifacts = []
    for name in ("technical-qc.json", "ffprobe.json", "manifest.json"):
        path = output_directory / name
        content = path.read_bytes()
        relative = path.relative_to(workspace).as_posix()
        artifacts.append(
            {
                "rel_path": relative,
                "path": relative,
                "name": name,
                "kind": "document",
                "media_type": "application/json",
                "mime": "application/json",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    return {
        "analysis_status": "succeeded",
        "technical_verdict": technical_verdict,
        "cache_hit": cache_hit,
        "duration_ms": expected_duration_ms,
        "assembly_attempt_id": assembly_attempt_id,
        "assembly_artifact_id": assembly_artifact_id,
        "variant": variant,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "expected_duration_ms": expected_duration_ms,
        "checks": {
            "container_mp4": {"status": "pass"},
            "full_decode": {"status": "pass"},
            "audio_not_silent": {"status": technical_verdict},
        },
        "media_facts": {
            "duration_ms": expected_duration_ms,
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "artifacts": artifacts,
        "cache_key": cache_key,
        "provider": "local_ffmpeg_qc",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
    }


def fake_local_qc_result(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_path: Path,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
) -> dict[str, object]:
    del production_id, input_path
    output_directory = (
        workspace / "outputs" / "studio" / "runs" / run_id / "qc" / cache_key
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    for name in ("technical-qc.json", "ffprobe.json", "manifest.json"):
        (output_directory / name).write_text(
            json.dumps({"name": name, "cache_key": cache_key}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return _fake_local_qc_metadata(
        workspace,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        cache_hit=False,
    )


def fake_validate_local_qc_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    assembly_attempt_id: str,
    assembly_artifact_id: str,
    variant: str,
    input_path: Path,
    input_sha256: str,
    input_bytes: int,
    expected_duration_ms: int,
) -> dict[str, object]:
    del production_id, input_path
    return _fake_local_qc_metadata(
        workspace,
        run_id=run_id,
        cache_key=cache_key,
        assembly_attempt_id=assembly_attempt_id,
        assembly_artifact_id=assembly_artifact_id,
        variant=variant,
        input_sha256=input_sha256,
        input_bytes=input_bytes,
        expected_duration_ms=expected_duration_ms,
        cache_hit=True,
    )


def create_succeeded_assembly_attempt(
    service: StudioService,
    run_id: str,
    *,
    include_captioned: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    cache_key = "D" * 64
    root = (
        service.workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "assembly"
        / cache_key
    )
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, tuple[str, str, bytes]] = {
        "master-clean.mp4": ("video", "video/mp4", VIDEO_BYTES),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    if include_captioned:
        files["master-captioned.mp4"] = (
            "video",
            "video/mp4",
            VIDEO_BYTES + b"captioned",
        )
    raw_artifacts = []
    for name, (kind, media_type, content) in files.items():
        path = root / name
        path.write_bytes(content)
        raw_artifacts.append(
            {
                "rel_path": path.relative_to(service.workspace).as_posix(),
                "kind": kind,
                "media_type": media_type,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    registered = service._register_local_assembly_artifacts(
        PRODUCTION_ID, run_id, cache_key, include_captioned, raw_artifacts
    )
    caption_style = normalize_caption_style_preset()
    attempt = service.database.create_stage_attempt(
        run_id, "assembly", cache_key, {"test_fixture": True}
    )
    service.database.update_stage_attempt(attempt["id"], "running")
    result = {
        "artifacts": registered,
        "duration_ms": 1_000,
        "cache_key": cache_key,
        "request_cache_key": cache_key,
        "cache_hit": False,
        "provider": "local_ffmpeg",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "include_captioned": include_captioned,
        "caption_style_preset": caption_style["preset"],
        "caption_style": caption_style,
        "source_video_sha256": "A" * 64,
        "narration_wav_sha256": "B" * 64,
        "captions_sha256": "C" * 64,
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }
    succeeded = service.database.update_stage_attempt(
        attempt["id"], "succeeded", result=result
    )
    selected_name = (
        "master-captioned.mp4" if include_captioned else "master-clean.mp4"
    )
    selected = next(item for item in registered if item["name"] == selected_name)
    return succeeded, selected


class WorkspaceFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        source = self.root / "productions" / PRODUCTION_ID
        output = self.root / "outputs" / "productions" / PRODUCTION_ID
        (source / "manifests").mkdir(parents=True)
        (source / "prompts").mkdir()
        (output / "02_cuts" / "CUT01").mkdir(parents=True)
        (output / "logs").mkdir()
        (self.root / "studio" / "dist").mkdir(parents=True)
        (source / "PRODUCTION_RECORD_JA.md").write_text(
            f"# 制作記録 — {PRODUCTION_ID}\n\ntechnical / creative / public gates\n",
            encoding="utf-8",
        )
        (source / "prompts" / "CUT01_H3.md").write_text("safe prompt\n", encoding="utf-8")
        (source / ".env").write_text("OPENAI_API_KEY=must-never-be-indexed\n", encoding="utf-8")
        (source / "app.env").write_text(
            "OPENAI_API_KEY=must-also-never-be-indexed\n", encoding="utf-8"
        )
        (source / "unsafe.conf").write_text(
            f"api_key: |\n  {RAW_CONFIG_SECRET}\n", encoding="utf-8"
        )
        (source / "settings.properties").write_text(
            f"api_key={RAW_UNKNOWN_SECRET}\n", encoding="utf-8"
        )
        (source / "unsafe.html").write_text(
            "<script>fetch('/api/index/refresh',{method:'POST'})</script>",
            encoding="utf-8",
        )
        self.video = output / "02_cuts" / "CUT01" / "clip.mp4"
        self.video.write_bytes(VIDEO_BYTES)
        (output / "logs" / "render.jsonl").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "authorization": f"Bearer {RAW_LOG_SECRET}",
                    "api_key": RAW_JSON_SECRET,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(VIDEO_BYTES).hexdigest().upper()
        manifest = {
            "production_id": PRODUCTION_ID,
            "status": "complete_independently_reviewed",
            "technical_status": "master_pass",
            "creative_status": "review_pass",
            "public_release_status": "blocked_pending_rights_review",
            "artifact": {
                "path": self.video.relative_to(self.root).as_posix(),
                "bytes": len(VIDEO_BYTES),
                "sha256": digest,
            },
        }
        (source / "manifests" / "source-hashes.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.root / "studio" / "dist" / "index.html").write_text(
            "<!doctype html><title>Studio</title>", encoding="utf-8"
        )

    def close(self) -> None:
        self.temporary.cleanup()


class DatabaseMigrationTests(unittest.TestCase):
    def test_v1_database_migrates_runs_and_stage_attempt_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            database_path = workspace / "outputs" / "studio" / "studio.sqlite3"
            database_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE schema_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    INSERT INTO schema_meta(key, value) VALUES('schema_version', '1');
                    CREATE TABLE runs (
                        id TEXT PRIMARY KEY,
                        production_id TEXT NOT NULL,
                        revision_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        requested_stages_json TEXT NOT NULL,
                        estimated_cost_minor INTEGER NOT NULL CHECK(estimated_cost_minor >= 0),
                        currency TEXT NOT NULL,
                        immutable_digest TEXT NOT NULL
                    );
                    """
                )

            database = StudioDatabase(database_path, workspace=workspace)
            with database.session() as connection:
                run_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(runs)")
                }
                schema_version = connection.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()["value"]
                stage_attempts = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='stage_attempts'"
                ).fetchone()
                stage_attempt_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(stage_attempts)")
                }

            self.assertIn("execution_profile", run_columns)
            self.assertEqual(schema_version, str(SCHEMA_VERSION))
            self.assertIsNotNone(stage_attempts)
            self.assertIn("job_id", stage_attempt_columns)


class AtomicCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def _active_pair(self) -> tuple[dict[str, object], dict[str, object]]:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        attempt = self.service.database.create_stage_attempt(
            run_id, "narration", "A" * 64, {"test": True}
        )
        job = self.service.database.create_job(
            "local_narration",
            {"run_id": run_id, "stage": "narration"},
            production_id=PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(str(attempt["id"]), str(job["id"]))
        self.service.database.update_job(str(job["id"]), "running")
        self.service.database.update_stage_attempt(str(attempt["id"]), "running")
        return job, attempt

    def _artifact_record(self, name: str) -> dict[str, object]:
        path = self.fixture.root / "outputs" / "studio" / "atomic" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = b"atomic-studio-artifact"
        path.write_bytes(payload)
        stat = path.stat()
        return {
            "id": f"art_atomic_{hashlib.sha256(name.encode()).hexdigest()[:16]}",
            "rel_path": path.relative_to(self.fixture.root).as_posix(),
            "name": name,
            "kind": "video",
            "media_type": "video/mp4",
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
            "is_heavy": False,
        }

    def test_atomic_completion_commits_job_and_stage_with_split_results(self) -> None:
        job, attempt = self._active_pair()
        job_id = str(job["id"])
        attempt_id = str(attempt["id"])
        stage_result = {
            "cache_hit": False,
            "artifacts": [],
            "duration_ms": 7,
            "stage_attempt_id": "attempt_untrusted",
        }

        committed = self.service.database.complete_job_with_stage_attempt(
            job_id, attempt_id, stage_result
        )

        self.assertTrue(committed["committed"])
        self.assertEqual(committed["job"]["status"], "succeeded")
        self.assertEqual(committed["stage_attempt"]["status"], "succeeded")
        self.assertEqual(committed["job"]["result"]["stage_attempt_id"], attempt_id)
        self.assertEqual(committed["job"]["result"]["cache_hit"], False)
        expected_stage_result = {
            "cache_hit": False,
            "artifacts": [],
            "duration_ms": 7,
        }
        self.assertEqual(committed["stage_attempt"]["result"], expected_stage_result)
        self.assertNotIn("stage_attempt_id", committed["stage_attempt"]["result"])

        with closing(self.service.database.connect()) as connection:
            events = connection.execute(
                "SELECT event_type, scope_type, scope_id, payload_json "
                "FROM events WHERE scope_id IN (?, ?) ORDER BY id",
                (job_id, str(attempt["run_id"])),
            ).fetchall()
        completion_events = [
            row for row in events if row["event_type"] in {
                "stage.attempt.succeeded", "job.succeeded"
            }
        ]
        self.assertEqual(
            [row["event_type"] for row in completion_events],
            ["stage.attempt.succeeded", "job.succeeded"],
        )
        stage_event = json.loads(completion_events[0]["payload_json"])
        job_event = json.loads(completion_events[1]["payload_json"])
        self.assertEqual(stage_event["result"], expected_stage_result)
        self.assertEqual(job_event["result"]["stage_attempt_id"], attempt_id)

    def test_interrupt_first_rejects_atomic_completion_without_forbidden_pair(self) -> None:
        job, attempt = self._active_pair()
        job_id = str(job["id"])
        attempt_id = str(attempt["id"])

        self.assertTrue(self.service.database.interrupt_job(job_id))
        with self.assertRaises(AtomicCompletionError) as raised:
            self.service.database.complete_job_with_stage_attempt(
                job_id, attempt_id, {"cache_hit": False}
            )
        self.assertEqual(raised.exception.code, "atomic_completion_not_active")
        self.assertFalse(raised.exception.committed)
        self.assertEqual(self.service.database.get_job(job_id)["status"], "interrupted")
        self.assertEqual(self.service.database.get_stage_attempt(attempt_id)["status"], "failed")

        with closing(self.service.database.connect()) as connection:
            event_types = [
                row["event_type"]
                for row in connection.execute(
                    "SELECT event_type FROM events WHERE scope_id IN (?, ?) ORDER BY id",
                    (job_id, str(attempt["run_id"])),
                ).fetchall()
            ]
        self.assertNotIn("job.succeeded", event_types)
        self.assertNotIn("stage.attempt.succeeded", event_types)

    def test_atomic_completion_commits_artifact_and_terminal_truth_together(self) -> None:
        job, attempt = self._active_pair()
        job_id = str(job["id"])
        attempt_id = str(attempt["id"])
        artifact = self._artifact_record("generated.mp4")

        committed = self.service.database.complete_job_with_stage_attempt(
            job_id,
            attempt_id,
            {"cache_hit": False, "artifacts": []},
            [artifact],
        )

        registered = committed["stage_attempt"]["result"]["artifacts"]
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered[0]["id"], artifact["id"])
        self.assertEqual(
            committed["job"]["result"]["artifacts"],
            registered,
        )
        self.assertIsNotNone(self.service.database.get_artifact(str(artifact["id"])))
        with closing(self.service.database.connect()) as connection:
            rows = connection.execute(
                "SELECT id, event_type FROM events "
                "WHERE event_type IN ('artifact.created', 'stage.attempt.succeeded', 'job.succeeded') "
                "AND (scope_id=? OR scope_id=? OR scope_id=?) ORDER BY id",
                (PRODUCTION_ID, str(attempt["run_id"]), job_id),
            ).fetchall()
        self.assertEqual(
            [row["event_type"] for row in rows],
            ["artifact.created", "stage.attempt.succeeded", "job.succeeded"],
        )

    def test_atomic_completion_rolls_back_artifact_when_success_update_fails(self) -> None:
        job, attempt = self._active_pair()
        job_id = str(job["id"])
        attempt_id = str(attempt["id"])
        artifact = self._artifact_record("rollback.mp4")
        with closing(self.service.database.connect()) as connection:
            connection.execute(
                "CREATE TRIGGER reject_test_atomic_success "
                "BEFORE UPDATE OF status ON jobs "
                f"WHEN NEW.id='{job_id}' AND NEW.status='succeeded' "
                "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.service.database.complete_job_with_stage_attempt(
                job_id,
                attempt_id,
                {"cache_hit": False, "artifacts": []},
                [artifact],
            )

        self.assertIsNone(self.service.database.get_artifact(str(artifact["id"])))
        self.assertEqual(self.service.database.get_job(job_id)["status"], "running")
        self.assertEqual(
            self.service.database.get_stage_attempt(attempt_id)["status"],
            "running",
        )
        with closing(self.service.database.connect()) as connection:
            version_count = connection.execute(
                "SELECT COUNT(*) AS count FROM artifact_versions WHERE artifact_id=?",
                (artifact["id"],),
            ).fetchone()["count"]
            event_count = connection.execute(
                "SELECT COUNT(*) AS count FROM events "
                "WHERE event_type='artifact.created' "
                "AND json_extract(payload_json, '$.artifact_id')=?",
                (artifact["id"],),
            ).fetchone()["count"]
        self.assertEqual(version_count, 0)
        self.assertEqual(event_count, 0)

    def test_job_manager_shutdown_wins_completion_boundary_without_split_truth(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        attempt = self.service.database.create_stage_attempt(
            run_id, "narration", "C" * 64, {"test": True}
        )
        attempt_id = str(attempt["id"])
        completion_entered = threading.Event()
        release_completion = threading.Event()
        interruption_committed = threading.Event()
        original_complete = self.service.database.complete_job_with_stage_attempt
        original_interrupt = self.service.database.interrupt_active_work

        def callback(_job_id: str, _context: threading.Event) -> AtomicStageCompletion:
            self.service.database.update_stage_attempt(attempt_id, "running")
            return AtomicStageCompletion(attempt_id, {"cache_hit": False, "artifacts": []})

        def blocked_complete(*args: object, **kwargs: object) -> dict[str, object]:
            completion_entered.set()
            self.assertTrue(release_completion.wait(2))
            return original_complete(*args, **kwargs)

        def tracked_interrupt() -> dict[str, int]:
            result = original_interrupt()
            interruption_committed.set()
            return result

        with (
            mock.patch.object(
                self.service.database,
                "complete_job_with_stage_attempt",
                side_effect=blocked_complete,
            ),
            mock.patch.object(
                self.service.database,
                "interrupt_active_work",
                side_effect=tracked_interrupt,
            ),
        ):
            job = self.service.jobs.submit(
                "local_narration",
                {"run_id": run_id, "stage": "narration"},
                callback,
                production_id=PRODUCTION_ID,
                before_enqueue=lambda created_job: self.service.database.link_stage_attempt_job(
                    attempt_id, str(created_job["id"])
                ),
            )
            self.assertTrue(completion_entered.wait(2))
            shutdown = threading.Thread(
                target=self.service.jobs.shutdown,
                kwargs={"timeout": 1.0},
                daemon=True,
            )
            shutdown.start()
            self.assertTrue(interruption_committed.wait(2))
            release_completion.set()
            shutdown.join(timeout=2)
            self.assertFalse(shutdown.is_alive())
            completed = self.service.jobs.wait(str(job["id"]), timeout=2)

        self.assertIsNotNone(completed)
        assert completed is not None
        final_attempt = self.service.database.get_stage_attempt(attempt_id)
        assert final_attempt is not None
        self.assertEqual(completed["status"], "interrupted")
        self.assertEqual(final_attempt["status"], "failed")
        self.assertNotEqual(
            (completed["status"], final_attempt["status"]),
            ("interrupted", "succeeded"),
        )

    def test_job_manager_atomically_fails_pair_when_completion_commit_raises(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        attempt = self.service.database.create_stage_attempt(
            run_id, "narration", "D" * 64, {"test": True}
        )
        attempt_id = str(attempt["id"])

        def callback(_job_id: str, _context: threading.Event) -> AtomicStageCompletion:
            self.service.database.update_stage_attempt(attempt_id, "running")
            return AtomicStageCompletion(
                attempt_id,
                {"cache_hit": False, "artifacts": []},
            )

        with mock.patch.object(
            self.service.database,
            "complete_job_with_stage_attempt",
            side_effect=sqlite3.IntegrityError("test completion failure"),
        ):
            job = self.service.jobs.submit(
                "local_narration",
                {"run_id": run_id, "stage": "narration"},
                callback,
                production_id=PRODUCTION_ID,
                before_enqueue=lambda created_job: self.service.database.link_stage_attempt_job(
                    attempt_id, str(created_job["id"])
                ),
            )
            completed = self.service.jobs.wait(str(job["id"]), timeout=2)

        self.assertIsNotNone(completed)
        assert completed is not None
        final_attempt = self.service.database.get_stage_attempt(attempt_id)
        assert final_attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(final_attempt["status"], "failed")
        self.assertEqual(completed["error"]["code"], "job_failed")
        self.assertEqual(final_attempt["error"]["code"], "job_failed")
        with closing(self.service.database.connect()) as connection:
            terminal_events = connection.execute(
                "SELECT event_type FROM events "
                "WHERE scope_id IN (?, ?) "
                "AND event_type IN ('stage.attempt.failed', 'job.failed') ORDER BY id",
                (run_id, str(job["id"])),
            ).fetchall()
        self.assertEqual(
            [row["event_type"] for row in terminal_events],
            ["stage.attempt.failed", "job.failed"],
        )

    def test_job_manager_atomically_fails_payload_linked_queued_stage(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        attempt = self.service.database.create_stage_attempt(
            run_id, "narration", "E" * 64, {"test": True}
        )
        attempt_id = str(attempt["id"])

        class SafeComfyFailure(RuntimeError):
            error_code = "comfyui_failed"
            public_message = "The local ComfyUI job failed."

        def callback(_job_id: str, _context: threading.Event) -> dict[str, object]:
            # Deliberately fail before the callback can mark the stage running.
            raise SafeComfyFailure()

        atomic_failure = self.service.database.fail_job_with_stage_attempt
        with mock.patch.object(
            self.service.database,
            "fail_job_with_stage_attempt",
            wraps=atomic_failure,
        ) as fail_pair:
            job = self.service.jobs.submit(
                "local_video_generation",
                {
                    "run_id": run_id,
                    "stage": "narration",
                    "stage_attempt_id": attempt_id,
                },
                callback,
                production_id=PRODUCTION_ID,
                before_enqueue=lambda created_job: self.service.database.link_stage_attempt_job(
                    attempt_id, str(created_job["id"])
                ),
                lane="gpu",
            )
            completed = self.service.jobs.wait(str(job["id"]), timeout=2)

        assert completed is not None
        final_attempt = self.service.database.get_stage_attempt(attempt_id)
        assert final_attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(final_attempt["status"], "failed")
        self.assertEqual(completed["error"]["code"], "comfyui_failed")
        self.assertEqual(final_attempt["error"], completed["error"])
        self.assertEqual(final_attempt["started_at"], None)
        self.assertEqual(final_attempt["completed_at"], completed["completed_at"])
        fail_pair.assert_called_once()
        self.assertEqual(fail_pair.call_args.args[:2], (job["id"], attempt_id))

    def test_payload_link_rejects_mismatched_completion_envelope(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        linked = self.service.database.create_stage_attempt(
            run_id, "narration", "6" * 64, {"test": "linked"}
        )
        unrelated = self.service.database.create_stage_attempt(
            run_id, "assembly", "5" * 64, {"test": "unrelated"}
        )
        linked_id = str(linked["id"])

        def callback(
            _job_id: str, _context: threading.Event
        ) -> AtomicStageCompletion:
            self.service.database.update_stage_attempt(linked_id, "running")
            return AtomicStageCompletion(
                str(unrelated["id"]), {"cache_hit": False, "artifacts": []}
            )

        with mock.patch.object(
            self.service.database,
            "complete_job_with_stage_attempt",
            wraps=self.service.database.complete_job_with_stage_attempt,
        ) as complete_pair:
            job = self.service.jobs.submit(
                "local_video_generation",
                {
                    "run_id": run_id,
                    "stage": "narration",
                    "stage_attempt_id": linked_id,
                },
                callback,
                production_id=PRODUCTION_ID,
                before_enqueue=lambda created_job: self.service.database.link_stage_attempt_job(
                    linked_id, str(created_job["id"])
                ),
                lane="gpu",
            )
            completed = self.service.jobs.wait(str(job["id"]), timeout=2)

        assert completed is not None
        linked_after = self.service.database.get_stage_attempt(linked_id)
        unrelated_after = self.service.database.get_stage_attempt(str(unrelated["id"]))
        assert linked_after is not None and unrelated_after is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "invalid_worker_result")
        self.assertEqual(linked_after["status"], "failed")
        self.assertEqual(unrelated_after["status"], "queued")
        complete_pair.assert_not_called()

    def test_payload_link_rejects_plain_completion_result(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = str(created["run"]["id"])
        attempt = self.service.database.create_stage_attempt(
            run_id, "narration", "4" * 64, {"test": "plain-result"}
        )
        attempt_id = str(attempt["id"])

        def callback(
            _job_id: str, _context: threading.Event
        ) -> dict[str, object]:
            self.service.database.update_stage_attempt(attempt_id, "running")
            return {"cache_hit": False, "artifacts": []}

        job = self.service.jobs.submit(
            "local_video_generation",
            {
                "run_id": run_id,
                "stage": "narration",
                "stage_attempt_id": attempt_id,
            },
            callback,
            production_id=PRODUCTION_ID,
            before_enqueue=lambda created_job: self.service.database.link_stage_attempt_job(
                attempt_id, str(created_job["id"])
            ),
            lane="gpu",
        )
        completed = self.service.jobs.wait(str(job["id"]), timeout=2)

        assert completed is not None
        final_attempt = self.service.database.get_stage_attempt(attempt_id)
        assert final_attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "invalid_worker_result")
        self.assertEqual(final_attempt["status"], "failed")
        self.assertEqual(final_attempt["error"], completed["error"])
        self.assertEqual(final_attempt["completed_at"], completed["completed_at"])

    def test_atomic_completion_rejects_wrong_link_and_non_running_state(self) -> None:
        job, attempt = self._active_pair()
        wrong_job = self.service.database.create_job(
            "local_narration",
            {"run_id": str(attempt["run_id"]), "stage": "narration"},
            production_id=PRODUCTION_ID,
        )
        with self.assertRaises(ValueError):
            self.service.database.complete_job_with_stage_attempt(
                str(wrong_job["id"]), str(attempt["id"]), {"ok": True}
            )

        queued = self.service.database.create_stage_attempt(
            str(attempt["run_id"]), "narration", "B" * 64, {"test": True}
        )
        queued_job = self.service.database.create_job(
            "local_narration",
            {"run_id": str(attempt["run_id"]), "stage": "narration"},
            production_id=PRODUCTION_ID,
        )
        self.service.database.link_stage_attempt_job(
            str(queued["id"]), str(queued_job["id"])
        )
        with self.assertRaises(AtomicCompletionError):
            self.service.database.complete_job_with_stage_attempt(
                str(queued_job["id"]), str(queued["id"]), {"ok": True}
            )

    def test_default_interrupted_event_uses_effective_error_metadata(self) -> None:
        job, _attempt = self._active_pair()
        job_id = str(job["id"])
        # Return the stage to a fresh queued-only job so update_job owns the
        # interruption transition and its event payload.
        self.service.database.update_stage_attempt(
            str(_attempt["id"]), "failed", error_code="test", error_message="test"
        )
        self.service.database.update_job(job_id, "interrupted")
        interrupted = self.service.database.get_job(job_id)
        self.assertEqual(interrupted["error"]["code"], "process_interrupted")
        self.assertEqual(interrupted["error"]["message"], "The Studio process stopped.")
        with closing(self.service.database.connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM events "
                "WHERE scope_type='job' AND scope_id=? AND event_type='job.interrupted' "
                "ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["error_code"], interrupted["error"]["code"])
        self.assertEqual(payload["error_message"], interrupted["error"]["message"])


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service: StudioService | None = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        if self.service is not None:
            self.service.close()
        self.fixture.close()

    def test_index_imports_records_and_heavy_artifacts_by_reference(self) -> None:
        listing = self.service.list_productions()
        self.assertEqual(listing["count"], 1)
        production = listing["productions"][0]
        self.assertEqual(production["id"], PRODUCTION_ID)
        self.assertEqual(production["technical_status"], "master_pass")
        detail = self.service.production_detail(PRODUCTION_ID, artifact_limit=100)
        self.assertIsNotNone(detail)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        self.assertFalse(
            any(Path(item["rel_path"]).suffix.casefold() == ".env" for item in detail["artifacts"])
        )
        self.assertEqual(video["bytes"], len(VIDEO_BYTES))
        self.assertEqual(video["sha256"], hashlib.sha256(VIDEO_BYTES).hexdigest().upper())
        self.assertEqual(video["preview_url"], f"/api/artifacts/{video['id']}/file")

        database_bytes = self.service.database.path.read_bytes()
        self.assertNotIn(VIDEO_BYTES, database_bytes)
        mirror = self.service.database.event_mirror_path("production", PRODUCTION_ID)
        events = [json.loads(line) for line in mirror.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1]["event_hash"], events[-1]["event_hash"].lower())
        self.assertEqual(len(events[-1]["event_hash"]), 64)

    def test_partial_rerun_creates_immutable_revision_run_and_append_only_approval(self) -> None:
        plan = build_rerun_plan(PRODUCTION_ID, [{"type": "caption", "target": "CUT03"}])
        self.assertEqual(plan["affected_stages"], ["captions", "assembly", "qc"])
        self.assertIn("video_generation", plan["reused_stages"])

        secret = "never-store-this-credential"
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [
                    {"type": "caption", "api_key": secret, "note": f"token={secret}"}
                ],
                "estimated_cost": {"amount": "1.25", "currency": "USD"},
            },
        )
        run_id = created["run"]["id"]
        self.assertEqual(created["run"]["state"], "awaiting_cost_approval")
        with self.assertRaises(RequestValidationError):
            self.service.approve_run(
                run_id,
                {
                    "approved": True,
                    "max_cost": {"amount": "1.00", "currency": "USD"},
                },
            )
        rejected = self.service.approve_run(
            run_id,
            {
                "approved": False,
                "note": "needs a lower estimate",
            },
        )
        self.assertEqual(rejected["state"], "rejected")
        approved = self.service.approve_run(
            run_id,
            {
                "approved": True,
                "max_cost": {"amount": "2.00", "currency": "USD"},
                "actor": "owner",
                "note": f"authorization={secret}",
            },
        )
        self.assertEqual(approved["state"], "approved")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["runs"][0]["estimated_cost"]["amount"], "1.25")
        self.assertEqual(detail["runs"][0]["latest_approval"]["decision"], "approved")
        self.assertEqual(
            [approval["decision"] for approval in detail["approvals"]],
            ["rejected", "approved"],
        )

        with closing(self.service.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE revisions SET changes_json='[]' WHERE id=?",
                    (created["revision"]["id"],),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM runs WHERE id=?", (run_id,))

        persisted = self.service.database.path.read_bytes()
        self.assertNotIn(secret.encode("utf-8"), persisted)
        event_files = list((self.fixture.root / "outputs" / "studio" / "events").rglob("*.jsonl"))
        self.assertTrue(event_files)
        self.assertNotIn(secret, "".join(path.read_text(encoding="utf-8") for path in event_files))

    def test_billable_rerun_fails_closed_without_positive_estimate(self) -> None:
        assert self.service is not None
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "script"}],
                    "estimated_cost": {"amount": 0, "currency": "USD"},
                },
            )
        self.assertEqual(raised.exception.code, "cost_estimate_required")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["runs"], [])

    def test_local_comfyui_profile_is_zero_cost_and_video_only(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "video"}],
                "execution_profile": "local_comfyui",
            },
        )
        self.assertEqual(created["run"]["execution_profile"], "local_comfyui")
        self.assertEqual(created["run"]["estimated_cost"]["amount"], "0.00")
        self.assertIn("video_generation", created["run"]["requested_stages"])

        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "script"}],
                    "execution_profile": "local_comfyui",
                },
            )
        self.assertEqual(raised.exception.code, "local_profile_stage_not_allowed")

        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "video"}],
                    "execution_profile": "local_comfyui",
                    "estimated_cost": {"amount": "0.01", "currency": "USD"},
                },
            )
        self.assertEqual(raised.exception.code, "local_profile_cost_not_allowed")

    def test_local_comfyui_generation_uses_gpu_lane_and_persists_safe_lineage(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "video"}],
                "execution_profile": "local_comfyui",
            },
        )
        run_id = created["run"]["id"]
        cache_key = "9" * 64
        prompt_id = "11111111-1111-4111-8111-111111111111"
        prompt = "A private Japanese presenter prompt that must not enter job payloads."
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
        runtime_identity = {
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
        resolved = {
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
            "cache_key": cache_key,
            "output_roots": ["outputs"],
        }

        def worker_result(
            workspace: Path,
            *,
            production_id: str,
            run_id: str,
            payload: dict[str, object],
            **kwargs: object,
        ) -> dict[str, object]:
            del production_id
            if "output_roots" in kwargs:
                self.assertEqual(kwargs.get("expected_cache_key"), cache_key)
            callback = kwargs.get("on_provider_task_id")
            if callable(callback):
                callback(prompt_id)
            output_directory = (
                workspace
                / "outputs"
                / "studio"
                / "runs"
                / run_id
                / "video_generation"
                / cache_key
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
                "cache_key": cache_key,
                "cache_hit": False,
                "provider": "comfyui",
                "provider_task_id": prompt_id,
                "prompt_id": prompt_id,
                "actual_cost": 0,
                "timing_source": "ffprobe",
                "workflow_preset": COMFYUI_WORKFLOW_PRESET,
                "prompt_sha256": hashlib.sha256(
                    str(payload["prompt"]).encode("utf-8")
                ).hexdigest().upper(),
                "seed": payload["seed"],
            }

        def validate_result(*args: object, **kwargs: object) -> dict[str, object]:
            result = worker_result(*args, **kwargs)
            result["cache_hit"] = True
            return result

        original_submit = self.service.jobs.submit
        submitted_lanes: list[str] = []

        def recording_submit(*args: object, **kwargs: object) -> dict[str, object]:
            submitted_lanes.append(str(kwargs.get("lane", "default")))
            return original_submit(*args, **kwargs)

        request = {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": prompt,
            "seed": 42,
        }
        with (
            mock.patch.object(
                self.service,
                "_resolve_comfyui_execution_inputs",
                return_value=resolved,
            ),
            mock.patch.object(self.service.jobs, "submit", side_effect=recording_submit),
            mock.patch(
                "tools.studio.comfyui.recover_comfyui_prompt_id", return_value=None
            ),
            mock.patch(
                "tools.studio.comfyui.generate_comfyui_video",
                side_effect=worker_result,
            ),
            mock.patch(
                "tools.studio.comfyui.validate_comfyui_outputs",
                side_effect=validate_result,
            ),
        ):
            queued = self.service.execute_local_video_generation(run_id, request)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        self.assertEqual(submitted_lanes, ["gpu"])
        self.assertEqual(queued["payload"]["stage_attempt_id"], queued["stage_attempt_id"])
        persisted_job = self.service.database.get_job(queued["id"])
        assert persisted_job is not None
        self.assertEqual(
            persisted_job["payload"]["stage_attempt_id"], queued["stage_attempt_id"]
        )
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["result"]["provider_task_id"], prompt_id)
        self.assertEqual(completed["result"]["prompt_sha256"], hashlib.sha256(prompt.encode()).hexdigest().upper())
        self.assertEqual(len(completed["result"]["artifacts"]), 4)
        self.assertNotIn(prompt, json.dumps(completed, ensure_ascii=False))
        persisted = self.service.database.path.read_bytes()
        self.assertNotIn(prompt.encode("utf-8"), persisted)

        run = self.service.run(run_id)
        assert run is not None
        attempt = next(
            item for item in run["stage_attempts"] if item["stage"] == "video_generation"
        )
        self.assertEqual(attempt["job_id"], queued["id"])
        self.assertEqual(attempt["status"], "succeeded")
        self.assertEqual(attempt["result"]["prompt_sha256"], completed["result"]["prompt_sha256"])
        snapshot = self.service.database.production_audit_snapshot(PRODUCTION_ID)
        assert snapshot is not None
        events = snapshot["events"]
        provider_events = [
            event
            for event in events
            if event["event_type"] == "video_generation.provider_submitted"
        ]
        self.assertEqual(len(provider_events), 1)
        self.assertEqual(provider_events[0]["payload"]["provider_task_id"], prompt_id)

        prior_attempt_id = attempt["id"]
        for _index in range(2):
            cached_run = self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "video"}],
                    "execution_profile": "local_comfyui",
                },
            )["run"]["id"]
            with (
                mock.patch.object(
                    self.service,
                    "_resolve_comfyui_execution_inputs",
                    return_value=resolved,
                ),
                mock.patch(
                    "tools.studio.comfyui.validate_comfyui_outputs",
                    side_effect=validate_result,
                ),
                mock.patch(
                    "tools.studio.comfyui.recover_comfyui_prompt_id",
                    side_effect=AssertionError("cache reuse must precede marker recovery"),
                ),
                mock.patch(
                    "tools.studio.comfyui.generate_comfyui_video",
                    side_effect=AssertionError("cache reuse must not submit ComfyUI"),
                ),
            ):
                cached_job = self.service.execute_local_video_generation(
                    cached_run, request
                )
                cached_completed = self.service.jobs.wait(
                    cached_job["id"], timeout=10
                )
            assert cached_completed is not None
            self.assertEqual(cached_completed["status"], "succeeded", cached_completed)
            self.assertTrue(cached_completed["result"]["cache_hit"])
            self.assertEqual(
                cached_completed["result"]["cache_source_attempt_id"],
                prior_attempt_id,
            )
            self.assertEqual(
                {
                    item["id"]
                    for item in cached_completed["result"]["artifacts"]
                },
                {item["id"] for item in completed["result"]["artifacts"]},
            )
            prior_attempt_id = cached_completed["result"]["stage_attempt_id"]

    def test_local_comfyui_worker_failure_atomically_fails_job_and_stage(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "video"}],
                "execution_profile": "local_comfyui",
            },
        )
        run_id = created["run"]["id"]
        cache_key = "7" * 64
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
        runtime_identity = {
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
        resolved = {
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
            "cache_key": cache_key,
            "output_roots": ["outputs"],
        }
        request = {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": "private prompt must not leak from an unknown worker failure",
            "seed": 43,
        }
        secret = "SECRET_INTERNAL_COMFY_PATH"
        atomic_failure = self.service.database.fail_job_with_stage_attempt
        with (
            mock.patch.object(
                self.service,
                "_resolve_comfyui_execution_inputs",
                return_value=resolved,
            ),
            mock.patch(
                "tools.studio.comfyui.recover_comfyui_prompt_id", return_value=None
            ),
            mock.patch(
                "tools.studio.comfyui.generate_comfyui_video",
                side_effect=RuntimeError(secret),
            ),
            mock.patch.object(
                self.service.database,
                "fail_job_with_stage_attempt",
                wraps=atomic_failure,
            ) as fail_pair,
        ):
            queued = self.service.execute_local_video_generation(run_id, request)
            completed = self.service.jobs.wait(queued["id"], timeout=10)

        assert completed is not None
        attempt_id = queued["stage_attempt_id"]
        attempt = self.service.database.get_stage_attempt(attempt_id)
        assert attempt is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(completed["error"]["code"], "comfyui_failed")
        self.assertEqual(attempt["error"], completed["error"])
        self.assertEqual(completed["completed_at"], attempt["completed_at"])
        self.assertEqual(completed["payload"]["stage_attempt_id"], attempt_id)
        fail_pair.assert_called_once()
        self.assertEqual(fail_pair.call_args.args[:2], (queued["id"], attempt_id))

        with closing(self.service.database.connect()) as connection:
            terminal_events = connection.execute(
                "SELECT event_type, created_at FROM events "
                "WHERE scope_id IN (?, ?) "
                "AND event_type IN ('stage.attempt.failed', 'job.failed') ORDER BY id",
                (run_id, queued["id"]),
            ).fetchall()
        self.assertEqual(
            [row["event_type"] for row in terminal_events],
            ["stage.attempt.failed", "job.failed"],
        )
        self.assertEqual(
            {row["created_at"] for row in terminal_events},
            {completed["completed_at"]},
        )
        self.assertNotIn(secret.encode("utf-8"), self.service.database.path.read_bytes())

    def test_zero_cost_run_rejects_cost_approval(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "local overlay only"}],
                "estimated_cost": {"amount": 0, "currency": "USD"},
            },
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.approve_run(
                created["run"]["id"],
                {
                    "approved": True,
                    "max_cost": {"amount": 0, "currency": "USD"},
                },
            )
        self.assertEqual(raised.exception.code, "cost_approval_not_required")

    def test_local_timeline_records_linked_attempt_reuses_cache_and_detects_tamper(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "timeline"}],
                "execution_profile": "local_sapi",
            },
        )
        run_id = created["run"]["id"]
        self.assertIn("timeline", created["run"]["requested_stages"])
        self.assertIn("assembly", created["run"]["requested_stages"])
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        request = {
            "clips": [
                {
                    "video_artifact_id": video["id"],
                    "start_ms": 0,
                    "end_ms": 125,
                }
            ]
        }
        module = types.ModuleType("tools.studio.timeline")
        module.timeline_cache_key = lambda _clips: "F" * 64
        module.generate_local_timeline = fake_local_timeline_result
        module.validate_local_timeline_outputs = fake_validate_local_timeline_outputs
        with (
            mock.patch.dict(sys.modules, {"tools.studio.timeline": module}),
            mock.patch("tools.studio.timeline", module, create=True),
        ):
            first_job = self.service.execute_local_timeline(run_id, request)
            self.assertEqual(first_job["kind"], "local_timeline")
            self.assertIsNotNone(first_job["stage_attempt_id"])
            queued_run = self.service.run(run_id)
            assert queued_run is not None
            queued_attempt = next(
                item
                for item in queued_run["stage_attempts"]
                if item["stage"] == "timeline"
            )
            self.assertEqual(queued_attempt["job_id"], first_job["id"])
            first = self.service.jobs.wait(first_job["id"], timeout=10)
            assert first is not None
            self.assertEqual(first["status"], "succeeded", first)
            self.assertFalse(first["result"]["cache_hit"])
            self.assertEqual(
                {item["name"] for item in first["result"]["artifacts"]},
                {"timeline-preview.mp4", "timeline.json", "ffprobe.json", "manifest.json"},
            )

            second_job = self.service.execute_local_timeline(run_id, request)
            second = self.service.jobs.wait(second_job["id"], timeout=10)
            assert second is not None
            self.assertEqual(second["status"], "succeeded", second)
            self.assertTrue(second["result"]["cache_hit"])
            self.assertEqual(
                second["result"]["cache_source_attempt_id"],
                first["result"]["stage_attempt_id"],
            )

            timeline_artifact = next(
                item
                for item in first["result"]["artifacts"]
                if item["name"] == "timeline-preview.mp4"
            )
            (self.fixture.root / timeline_artifact["rel_path"]).write_bytes(b"tampered")
            third_job = self.service.execute_local_timeline(run_id, request)
            third = self.service.jobs.wait(third_job["id"], timeout=10)
            assert third is not None
            self.assertEqual(third["status"], "succeeded", third)
            self.assertFalse(third["result"]["cache_hit"])

        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertTrue(
            any(
                item["kind"] == "video" and item["name"] == "timeline-preview.mp4"
                for item in detail["artifacts"]
            )
        )

    def test_local_timeline_rejects_foreign_artifact_and_unknown_fields(self) -> None:
        other_id = "OTHER_20260824_timeline"
        other_path = self.fixture.root / "outputs" / "productions" / other_id / "clip.mp4"
        other_path.parent.mkdir(parents=True, exist_ok=True)
        other_path.write_bytes(VIDEO_BYTES)
        other_artifact = self.service.indexer._artifact(other_id, other_path, "output", {})
        assert other_artifact is not None
        self.service.database.index_production(
            {
                "id": other_id,
                "title": other_id,
                "status": "discovered",
                "technical_status": None,
                "creative_status": None,
                "public_release_status": None,
                "source_rel": None,
                "output_rel": f"outputs/productions/{other_id}",
            },
            [other_artifact],
        )
        other_detail = self.service.production_detail(other_id)
        assert other_detail is not None
        foreign_video = next(item for item in other_detail["artifacts"] if item["kind"] == "video")
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "timeline"}], "execution_profile": "local_sapi"},
        )
        with self.assertRaises(RequestValidationError) as foreign:
            self.service.execute_local_timeline(
                created["run"]["id"],
                {
                    "clips": [
                        {
                            "video_artifact_id": foreign_video["id"],
                            "start_ms": 0,
                            "end_ms": 125,
                        }
                    ]
                },
            )
        self.assertEqual(foreign.exception.code, "timeline_video_not_available")
        with self.assertRaises(RequestValidationError) as unknown:
            self.service.execute_local_timeline(
                created["run"]["id"],
                {
                    "clips": [],
                    "unexpected": True,
                },
            )
        self.assertEqual(unknown.exception.code, "invalid_local_timeline_request")

    def test_local_timeline_cache_chain_reuses_physical_owner_across_three_runs(self) -> None:
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        request = {
            "clips": [
                {
                    "video_artifact_id": video["id"],
                    "start_ms": 0,
                    "end_ms": 125,
                }
            ]
        }
        generated_runs: list[str] = []

        def generate(*args: object, **kwargs: object) -> dict[str, object]:
            generated_runs.append(str(kwargs["run_id"]))
            return fake_local_timeline_result(*args, **kwargs)

        module = types.ModuleType("tools.studio.timeline")
        module.timeline_cache_key = lambda _clips: "D" * 64
        module.generate_local_timeline = generate
        module.validate_local_timeline_outputs = fake_validate_local_timeline_outputs
        completed: list[dict[str, object]] = []
        with (
            mock.patch.dict(sys.modules, {"tools.studio.timeline": module}),
            mock.patch("tools.studio.timeline", module, create=True),
        ):
            for _ in range(3):
                created = self.service.create_run(
                    PRODUCTION_ID,
                    {
                        "changes": [{"type": "timeline"}],
                        "execution_profile": "local_sapi",
                    },
                )
                job = self.service.execute_local_timeline(created["run"]["id"], request)
                terminal = self.service.jobs.wait(job["id"], timeout=10)
                assert terminal is not None
                self.assertEqual(terminal["status"], "succeeded", terminal)
                completed.append(terminal)

        self.assertEqual([item["result"]["cache_hit"] for item in completed], [False, True, True])
        self.assertEqual(len(generated_runs), 1)
        self.assertEqual(
            completed[2]["result"]["cache_source_attempt_id"],
            completed[1]["result"]["stage_attempt_id"],
        )

    def test_timeline_artifact_is_accepted_as_existing_assembly_source(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "timeline"}, {"type": "script"}],
                "execution_profile": "local_sapi",
            },
        )
        run_id = created["run"]["id"]
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        source_video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        timeline_module = types.ModuleType("tools.studio.timeline")
        timeline_module.timeline_cache_key = lambda _clips: "B" * 64
        timeline_module.generate_local_timeline = fake_local_timeline_result
        timeline_module.validate_local_timeline_outputs = fake_validate_local_timeline_outputs
        with (
            mock.patch.dict(sys.modules, {"tools.studio.timeline": timeline_module}),
            mock.patch("tools.studio.timeline", timeline_module, create=True),
            mock.patch(
                "tools.studio.narration.generate_local_narration",
                side_effect=fake_local_narration_result,
            ),
        ):
            timeline_job = self.service.execute_local_timeline(
                run_id,
                {
                    "clips": [
                        {
                            "video_artifact_id": source_video["id"],
                            "start_ms": 0,
                            "end_ms": 125,
                        }
                    ]
                },
            )
            timeline = self.service.jobs.wait(timeline_job["id"], timeout=10)
            assert timeline is not None
            self.assertEqual(timeline["status"], "succeeded", timeline)
            timeline_video = next(
                item
                for item in timeline["result"]["artifacts"]
                if item["name"] == "timeline-preview.mp4"
            )
            narration_job = self.service.execute_local_narration(
                run_id, {"segments": [{"text": "timeline assembly"}]}
            )
            narration = self.service.jobs.wait(narration_job["id"], timeout=10)
            assert narration is not None
            self.assertEqual(narration["status"], "succeeded", narration)
            assembly_request = {
                "video_artifact_id": timeline_video["id"],
                "narration_attempt_id": narration["result"]["stage_attempt_id"],
                "include_captioned": False,
            }
            with (
                mock.patch("tools.studio.assembly.assembly_cache_key", return_value="A" * 64),
                mock.patch(
                    "tools.studio.assembly.generate_local_assembly",
                    side_effect=fake_local_assembly_result,
                ),
                mock.patch(
                    "tools.studio.assembly.validate_local_assembly_outputs",
                    side_effect=fake_validate_local_assembly_outputs,
                ),
            ):
                assembly_job = self.service.execute_local_assembly(run_id, assembly_request)
                assembly = self.service.jobs.wait(assembly_job["id"], timeout=10)
        assert assembly is not None
        self.assertEqual(assembly["status"], "succeeded", assembly)

    def test_local_sapi_run_records_stage_attempt_and_reuses_success(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_generate(
            workspace: Path,
            *,
            production_id: str,
            run_id: str,
            payload: dict[str, object],
        ) -> dict[str, object]:
            calls.append((run_id, payload))
            running = self.service.run(run_id)
            assert running is not None
            self.assertIsNotNone(running["stage_attempts"][-1]["job_id"])
            return fake_local_narration_result(
                workspace,
                production_id=production_id,
                run_id=run_id,
                payload=payload,
            )

        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        self.assertEqual(created["run"]["execution_profile"], "local_sapi")
        body = {"segments": [{"text": "hello local narration"}], "rate": 0}
        with mock.patch("tools.studio.narration.generate_local_narration", side_effect=fake_generate):
            first = self.service.execute_local_narration(created["run"]["id"], body)
            completed_first = self.service.jobs.wait(first["id"], timeout=10)
            self.assertIsNotNone(completed_first)
            self.assertEqual(completed_first["status"], "succeeded")
            self.assertFalse(completed_first["result"]["cache_hit"])

            second = self.service.execute_local_narration(created["run"]["id"], body)
            completed_second = self.service.jobs.wait(second["id"], timeout=10)
            self.assertIsNotNone(completed_second)
            self.assertEqual(completed_second["status"], "succeeded")
            self.assertTrue(completed_second["result"]["cache_hit"])

            audio = next(
                artifact
                for artifact in completed_first["result"]["artifacts"]
                if artifact["name"] == "narration.wav"
            )
            (self.fixture.root / audio["rel_path"]).write_bytes(b"tampered")
            third = self.service.execute_local_narration(created["run"]["id"], body)
            completed_third = self.service.jobs.wait(third["id"], timeout=10)
            self.assertIsNotNone(completed_third)
            self.assertEqual(completed_third["status"], "succeeded")
            self.assertFalse(completed_third["result"]["cache_hit"])

            with closing(self.service.database.connect()) as connection:
                corrupted = dict(completed_third["result"])
                corrupted["provider"] = "unexpected_provider"
                connection.execute(
                    "UPDATE stage_attempts SET result_json=? WHERE id=?",
                    (
                        json.dumps(corrupted, ensure_ascii=False),
                        completed_third["result"]["stage_attempt_id"],
                    ),
                )
            fourth = self.service.execute_local_narration(created["run"]["id"], body)
            completed_fourth = self.service.jobs.wait(fourth["id"], timeout=10)
            self.assertIsNotNone(completed_fourth)
            self.assertEqual(completed_fourth["status"], "succeeded")
            self.assertFalse(completed_fourth["result"]["cache_hit"])

        self.assertEqual(len(calls), 3)
        detail = self.service.run(created["run"]["id"])
        assert detail is not None
        self.assertEqual(
            [attempt["status"] for attempt in detail["stage_attempts"]],
            ["succeeded", "succeeded", "succeeded", "succeeded"],
        )
        self.assertEqual(
            [attempt["attempt"] for attempt in detail["stage_attempts"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            [attempt["job_id"] for attempt in detail["stage_attempts"]],
            [first["id"], second["id"], third["id"], fourth["id"]],
        )
        first_attempt = detail["stage_attempts"][0]
        with closing(self.service.database.connect()) as connection:
            linked_events_before = connection.execute(
                "SELECT COUNT(*) AS count FROM events WHERE event_type='stage.attempt.job_linked'"
            ).fetchone()["count"]
        linked_again = self.service.database.link_stage_attempt_job(
            first_attempt["id"], first["id"]
        )
        with closing(self.service.database.connect()) as connection:
            linked_events_after = connection.execute(
                "SELECT COUNT(*) AS count FROM events WHERE event_type='stage.attempt.job_linked'"
            ).fetchone()["count"]
        self.assertEqual(linked_again["job_id"], first["id"])
        self.assertEqual(linked_events_after, linked_events_before)
        audit = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        completed_audit = self.service.jobs.wait(audit["id"], timeout=10)
        assert completed_audit is not None
        self.assertEqual(completed_audit["status"], "succeeded")
        archive_path = self.fixture.root / completed_audit["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            narration_root = (
                f"workspace/outputs/studio/runs/{created['run']['id']}/narration/"
                f"{completed_first['result']['cache_key']}/"
            )
            self.assertIn(f"{narration_root}captions.srt", names)
            self.assertIn(f"{narration_root}timings.json", names)
            self.assertIn(f"{narration_root}manifest.json", names)
            self.assertNotIn(f"{narration_root}narration.wav", names)

    def test_local_assembly_records_lineage_reuses_cache_and_detects_tampering(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        self.assertIn("narration", created["run"]["requested_stages"])
        self.assertIn("assembly", created["run"]["requested_stages"])
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            narration_job = self.service.execute_local_narration(
                run_id, {"segments": [{"text": "hello local assembly"}], "rate": 0}
            )
            narration = self.service.jobs.wait(narration_job["id"], timeout=10)
        assert narration is not None
        self.assertEqual(narration["status"], "succeeded")
        narration_attempt_id = narration["result"]["stage_attempt_id"]
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        request = {
            "video_artifact_id": video["id"],
            "narration_attempt_id": narration_attempt_id,
            "include_captioned": True,
            "caption_style_preset": "shorts_ja_large_v1",
        }
        calls: list[str] = []
        generation_errors: list[str] = []

        def fake_generate(*args: object, **kwargs: object) -> dict[str, object]:
            try:
                calls.append(str(kwargs["run_id"]))
                running = self.service.run(run_id)
                assert running is not None
                current = [
                    attempt
                    for attempt in running["stage_attempts"]
                    if attempt["stage"] == "assembly"
                ][-1]
                self.assertIsNotNone(current["job_id"])
                return fake_local_assembly_result(*args, **kwargs)
            except Exception as exc:
                generation_errors.append(repr(exc))
                raise

        cache_key = "A" * 64
        with (
            mock.patch("tools.studio.assembly.assembly_cache_key", return_value=cache_key),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=fake_generate,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=fake_validate_local_assembly_outputs,
            ),
        ):
            first_job = self.service.execute_local_assembly(run_id, request)
            first = self.service.jobs.wait(first_job["id"], timeout=10)
            assert first is not None
            self.assertEqual(first["status"], "succeeded", (first, generation_errors))
            self.assertFalse(first["result"]["cache_hit"])
            self.assertEqual(first["result"]["provider"], "local_ffmpeg")
            self.assertEqual(first["result"]["actual_cost"], 0)
            self.assertEqual(
                first["result"]["caption_style_preset"], "shorts_ja_large_v1"
            )
            self.assertEqual(len(first["result"]["artifacts"]), 4)

            second_job = self.service.execute_local_assembly(run_id, request)
            second = self.service.jobs.wait(second_job["id"], timeout=10)
            assert second is not None
            self.assertEqual(second["status"], "succeeded")
            self.assertTrue(second["result"]["cache_hit"])
            self.assertEqual(
                second["result"]["cache_source_attempt_id"],
                first["result"]["stage_attempt_id"],
            )

            clean = next(
                item
                for item in first["result"]["artifacts"]
                if item["name"] == "master-clean.mp4"
            )
            (self.fixture.root / clean["rel_path"]).write_bytes(b"tampered-master")
            third_job = self.service.execute_local_assembly(run_id, request)
            third = self.service.jobs.wait(third_job["id"], timeout=10)
            assert third is not None
            self.assertEqual(third["status"], "succeeded")
            self.assertFalse(third["result"]["cache_hit"])

        self.assertEqual(calls, [run_id, run_id])
        run = self.service.run(run_id)
        assert run is not None
        assembly_attempts = [
            attempt for attempt in run["stage_attempts"] if attempt["stage"] == "assembly"
        ]
        self.assertEqual([attempt["attempt"] for attempt in assembly_attempts], [1, 2, 3])
        self.assertEqual(
            [attempt["job_id"] for attempt in assembly_attempts],
            [first_job["id"], second_job["id"], third_job["id"]],
        )

        audit_job = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        audit = self.service.jobs.wait(audit_job["id"], timeout=10)
        assert audit is not None
        archive_path = self.fixture.root / audit["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            assembly_root = f"workspace/outputs/studio/runs/{run_id}/assembly/{cache_key}/"
            self.assertIn(f"{assembly_root}ffprobe.json", names)
            self.assertIn(f"{assembly_root}manifest.json", names)
            self.assertNotIn(f"{assembly_root}master-clean.mp4", names)

    def test_local_assembly_physical_validation_failure_registers_no_artifacts(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            narration_job = self.service.execute_local_narration(
                run_id, {"segments": [{"text": "physical validation"}]}
            )
            narration = self.service.jobs.wait(narration_job["id"], timeout=10)
        assert narration is not None
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        request = {
            "video_artifact_id": video["id"],
            "narration_attempt_id": narration["result"]["stage_attempt_id"],
            "include_captioned": False,
        }
        with (
            mock.patch("tools.studio.assembly.assembly_cache_key", return_value="C" * 64),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=fake_local_assembly_result,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=LocalAssemblyError(
                    "The generated master is not a valid MP4.",
                    code="invalid_cache",
                ),
            ),
        ):
            job = self.service.execute_local_assembly(run_id, request)
            completed = self.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "invalid_cache")
        after = self.service.production_detail(PRODUCTION_ID)
        assert after is not None
        self.assertFalse(
            any(
                item["origin"] == "studio" and item["name"] == "master-clean.mp4"
                for item in after["artifacts"]
            )
        )

        def mismatched_duration(*args: object, **kwargs: object) -> dict[str, object]:
            result = fake_validate_local_assembly_outputs(*args, **kwargs)
            result["duration_ms"] = 126
            return result

        with (
            mock.patch("tools.studio.assembly.assembly_cache_key", return_value="C" * 64),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=fake_local_assembly_result,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=mismatched_duration,
            ),
        ):
            mismatch_job = self.service.execute_local_assembly(run_id, request)
            mismatch = self.service.jobs.wait(mismatch_job["id"], timeout=10)
        assert mismatch is not None
        self.assertEqual(mismatch["status"], "failed")
        self.assertEqual(mismatch["error"]["code"], "invalid_worker_result")

    def test_local_assembly_request_and_run_contract_fail_closed(self) -> None:
        local = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        with self.assertRaises(RequestValidationError):
            self.service.execute_local_assembly(
                local["run"]["id"],
                {
                    "video_artifact_id": "art_" + "0" * 32,
                    "narration_attempt_id": "attempt_" + "0" * 32,
                    "include_captioned": True,
                    "unexpected": True,
                },
            )

        assembly_only = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_assembly(
                assembly_only["run"]["id"],
                {
                    "video_artifact_id": "art_" + "0" * 32,
                    "narration_attempt_id": "attempt_" + "0" * 32,
                    "include_captioned": False,
                },
            )
        self.assertEqual(raised.exception.code, "stage_not_requested")

        external = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": 1, "currency": "USD"},
            },
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_assembly(
                external["run"]["id"],
                {
                    "video_artifact_id": "art_" + "0" * 32,
                    "narration_attempt_id": "attempt_" + "0" * 32,
                    "include_captioned": False,
                },
            )
        self.assertEqual(raised.exception.code, "execution_profile_required")

    def test_local_qc_records_lineage_reuses_cache_and_detects_tampering(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        assembly_attempt, _master = create_succeeded_assembly_attempt(
            self.service, run_id
        )
        request = {
            "assembly_attempt_id": assembly_attempt["id"],
            "variant": "clean",
        }
        cache_key = "E" * 64
        calls: list[str] = []

        def fake_generate(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(str(kwargs["run_id"]))
            return fake_local_qc_result(*args, **kwargs)

        with (
            mock.patch("tools.studio.qc.qc_cache_key", return_value=cache_key),
            mock.patch("tools.studio.qc.generate_local_qc", side_effect=fake_generate),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=fake_validate_local_qc_outputs,
            ),
        ):
            first_job = self.service.execute_local_qc(run_id, request)
            first = self.service.jobs.wait(first_job["id"], timeout=10)
            assert first is not None
            self.assertEqual(first["status"], "succeeded", first)
            self.assertEqual(first["result"]["analysis_status"], "succeeded")
            self.assertEqual(first["result"]["technical_verdict"], "pass")
            self.assertFalse(first["result"]["cache_hit"])
            self.assertEqual(first["result"]["provider"], "local_ffmpeg_qc")
            self.assertEqual(first["result"]["actual_cost"], 0)
            self.assertEqual(len(first["result"]["artifacts"]), 3)

            second_job = self.service.execute_local_qc(run_id, request)
            second = self.service.jobs.wait(second_job["id"], timeout=10)
            assert second is not None
            self.assertEqual(second["status"], "succeeded", second)
            self.assertTrue(second["result"]["cache_hit"])
            self.assertEqual(
                second["result"]["cache_source_attempt_id"],
                first["result"]["stage_attempt_id"],
            )

            report = next(
                item
                for item in first["result"]["artifacts"]
                if item["name"] == "technical-qc.json"
            )
            (self.fixture.root / report["rel_path"]).write_text(
                "{\"tampered\":true}\n", encoding="utf-8"
            )
            third_job = self.service.execute_local_qc(run_id, request)
            third = self.service.jobs.wait(third_job["id"], timeout=10)
            assert third is not None
            self.assertEqual(third["status"], "succeeded", third)
            self.assertFalse(third["result"]["cache_hit"])

        self.assertEqual(calls, [run_id, run_id])
        run = self.service.run(run_id)
        assert run is not None
        attempts = [
            item for item in run["stage_attempts"] if item["stage"] == "qc"
        ]
        self.assertEqual([item["attempt"] for item in attempts], [1, 2, 3])
        audit_job = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        audit = self.service.jobs.wait(audit_job["id"], timeout=10)
        assert audit is not None
        with zipfile.ZipFile(self.fixture.root / audit["result"]["artifact"]["rel_path"]) as archive:
            names = set(archive.namelist())
            qc_root = f"workspace/outputs/studio/runs/{run_id}/qc/{cache_key}/"
            self.assertIn(f"{qc_root}technical-qc.json", names)
            self.assertIn(f"{qc_root}ffprobe.json", names)
            self.assertIn(f"{qc_root}manifest.json", names)

    def test_local_qc_fail_verdict_succeeds_without_changing_production_gates(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        assembly_attempt, _master = create_succeeded_assembly_attempt(
            self.service, run_id
        )
        request = {
            "assembly_attempt_id": assembly_attempt["id"],
            "variant": "clean",
        }

        def failing_generate(*args: object, **kwargs: object) -> dict[str, object]:
            result = fake_local_qc_result(*args, **kwargs)
            result["technical_verdict"] = "fail"
            result["checks"] = {
                **result["checks"],
                "audio_not_silent": {"status": "fail"},
            }
            return result

        def failing_validate(*args: object, **kwargs: object) -> dict[str, object]:
            result = fake_validate_local_qc_outputs(*args, **kwargs)
            result["technical_verdict"] = "fail"
            result["checks"] = {
                **result["checks"],
                "audio_not_silent": {"status": "fail"},
            }
            return result

        with (
            mock.patch("tools.studio.qc.qc_cache_key", return_value="F" * 64),
            mock.patch("tools.studio.qc.generate_local_qc", side_effect=failing_generate),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=failing_validate,
            ),
        ):
            job = self.service.execute_local_qc(run_id, request)
            completed = self.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["result"]["analysis_status"], "succeeded")
        self.assertEqual(completed["result"]["technical_verdict"], "fail")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["production"]["technical_status"], "master_pass")
        self.assertEqual(detail["production"]["creative_status"], "review_pass")
        self.assertEqual(
            detail["production"]["public_release_status"],
            "blocked_pending_rights_review",
        )

    def test_local_qc_physical_validation_failure_registers_no_artifacts(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        assembly_attempt, _master = create_succeeded_assembly_attempt(
            self.service, run_id
        )
        with (
            mock.patch("tools.studio.qc.qc_cache_key", return_value="8" * 64),
            mock.patch(
                "tools.studio.qc.generate_local_qc", side_effect=fake_local_qc_result
            ),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=LocalQcError(
                    "The generated QC cache is invalid.", code="invalid_cache"
                ),
            ),
        ):
            job = self.service.execute_local_qc(
                run_id,
                {
                    "assembly_attempt_id": assembly_attempt["id"],
                    "variant": "clean",
                },
            )
            completed = self.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error"]["code"], "invalid_cache")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertFalse(
            any(
                item["origin"] == "studio" and item["name"] == "technical-qc.json"
                for item in detail["artifacts"]
            )
        )

    def test_local_qc_request_run_and_lineage_contract_fail_closed(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        assembly_attempt, _master = create_succeeded_assembly_attempt(
            self.service, run_id
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_qc(
                run_id,
                {
                    "assembly_attempt_id": assembly_attempt["id"],
                    "variant": "clean",
                    "assembly_artifact_id": "art_" + "0" * 32,
                },
            )
        self.assertEqual(raised.exception.code, "invalid_local_qc_request")

        qc_only = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "qc"}], "execution_profile": "local_sapi"},
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_qc(
                qc_only["run"]["id"],
                {"assembly_attempt_id": assembly_attempt["id"], "variant": "clean"},
            )
        self.assertEqual(raised.exception.code, "stage_not_requested")

        external = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "estimated_cost": {"amount": 1, "currency": "USD"}},
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_qc(
                external["run"]["id"],
                {"assembly_attempt_id": assembly_attempt["id"], "variant": "clean"},
            )
        self.assertEqual(raised.exception.code, "execution_profile_required")

        another = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_qc(
                another["run"]["id"],
                {"assembly_attempt_id": assembly_attempt["id"], "variant": "clean"},
            )
        self.assertEqual(raised.exception.code, "qc_assembly_not_available")

    def test_local_qc_accepts_only_verified_cross_run_assembly_cache_lineage(self) -> None:
        source_created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        source_attempt, source_master = create_succeeded_assembly_attempt(
            self.service, source_created["run"]["id"]
        )
        cached_created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        cached_run_id = cached_created["run"]["id"]
        cached_attempt = self.service.database.create_stage_attempt(
            cached_run_id, "assembly", source_attempt["cache_key"], {"test_fixture": True}
        )
        self.service.database.update_stage_attempt(cached_attempt["id"], "running")
        cached_result = dict(source_attempt["result"])
        cached_result["cache_hit"] = True
        cached_result["cache_source_attempt_id"] = source_attempt["id"]
        cached_attempt = self.service.database.update_stage_attempt(
            cached_attempt["id"], "succeeded", result=cached_result
        )
        cached_run = self.service.run(cached_run_id)
        assert cached_run is not None
        resolved = self.service._validated_qc_inputs(
            cached_run,
            {"assembly_attempt_id": cached_attempt["id"], "variant": "clean"},
        )
        self.assertEqual(resolved["assembly_artifact"]["id"], source_master["id"])
        self.assertIn(
            f"outputs/studio/runs/{source_created['run']['id']}/assembly/",
            resolved["assembly_artifact"]["rel_path"],
        )

        bad_source = self.service.database.create_stage_attempt(
            source_created["run"]["id"],
            "assembly",
            source_attempt["cache_key"],
            {"test_fixture": True},
        )
        self.service.database.update_stage_attempt(bad_source["id"], "running")
        bad_source_result = dict(source_attempt["result"])
        bad_source_result["artifacts"] = [
            item
            for item in bad_source_result["artifacts"]
            if item["name"] != "master-clean.mp4"
        ]
        bad_source = self.service.database.update_stage_attempt(
            bad_source["id"], "succeeded", result=bad_source_result
        )
        forged_attempt = self.service.database.create_stage_attempt(
            cached_run_id, "assembly", source_attempt["cache_key"], {"test_fixture": True}
        )
        self.service.database.update_stage_attempt(forged_attempt["id"], "running")
        forged_result = dict(source_attempt["result"])
        forged_result["cache_hit"] = True
        forged_result["cache_source_attempt_id"] = bad_source["id"]
        forged_attempt = self.service.database.update_stage_attempt(
            forged_attempt["id"], "succeeded", result=forged_result
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service._validated_qc_inputs(
                cached_run,
                {"assembly_attempt_id": forged_attempt["id"], "variant": "clean"},
            )
        self.assertEqual(raised.exception.code, "qc_assembly_not_available")

    def test_invalid_worker_metadata_fails_before_artifact_registration(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        before = self.service.production_detail(PRODUCTION_ID)
        assert before is not None
        before_ids = {artifact["id"] for artifact in before["artifacts"]}

        invalid_overrides = (
            {"provider": "unexpected_provider"},
            {"provider_task_id": "invented-task"},
            {"actual_cost": False},
            {"timing_source": "unverified"},
        )
        for override in invalid_overrides:
            with self.subTest(override=override):
                def invalid_result(*args: object, **kwargs: object) -> dict[str, object]:
                    result = fake_local_narration_result(*args, **kwargs)
                    result.update(override)
                    return result

                with mock.patch(
                    "tools.studio.narration.generate_local_narration", side_effect=invalid_result
                ):
                    job = self.service.execute_local_narration(
                        created["run"]["id"], {"segments": [{"text": f"must fail {override}"}]}
                    )
                    completed = self.service.jobs.wait(job["id"], timeout=10)
                assert completed is not None
                self.assertEqual(completed["status"], "failed")
        run = self.service.run(created["run"]["id"])
        assert run is not None
        self.assertTrue(all(attempt["status"] == "failed" for attempt in run["stage_attempts"]))
        after = self.service.production_detail(PRODUCTION_ID)
        assert after is not None
        self.assertEqual({artifact["id"] for artifact in after["artifacts"]}, before_ids)

    def test_active_attempt_is_failed_on_database_reopen(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        attempt = self.service.database.create_stage_attempt(
            created["run"]["id"], "narration", "a" * 64, {"segment_count": 1}
        )
        self.service.database.update_stage_attempt(attempt["id"], "running")
        self.service.close()
        self.service = StudioService(self.fixture.root)

        recovered = self.service.database.get_stage_attempt(attempt["id"])
        assert recovered is not None
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["error"]["code"], "process_interrupted")
        mirror = self.service.database.event_mirror_path("run", created["run"]["id"])
        events = [
            json.loads(line)
            for line in mirror.read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(events[-1]["event_type"], "stage.attempt.failed")

    def test_local_sapi_rejects_external_profile_and_disallowed_zero_cost_stage(self) -> None:
        external = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "estimated_cost": {"amount": 1, "currency": "USD"}},
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.execute_local_narration(
                external["run"]["id"], {"segments": [{"text": "no"}]}
            )
        self.assertEqual(raised.exception.code, "execution_profile_required")

        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "video"}],
                    "execution_profile": "local_sapi",
                },
            )
        self.assertEqual(raised.exception.code, "local_profile_stage_not_allowed")

    def test_local_narration_payload_limits_and_unknown_fields_fail_closed(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "script"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        with self.assertRaises(RequestValidationError):
            self.service.execute_local_narration(
                run_id, {"segments": [{"text": "ok"}], "unexpected": True}
            )
        with self.assertRaises(RequestValidationError):
            self.service.execute_local_narration(
                run_id, {"segments": [{"text": "ok"}], "rate": 11}
            )
        with self.assertRaises(RequestValidationError):
            self.service.execute_local_narration(
                run_id,
                {
                    "segments": [{"text": "ok"}],
                    "pronunciations": [{"source": "x", "target": "y"}, {"source": "x", "target": "z"}],
                },
            )

    def test_audit_snapshot_uses_one_database_read_transaction(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "snapshot test"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
            },
        )
        snapshot_ready = threading.Event()
        resume_snapshot = threading.Event()
        captured: list[dict[str, object] | None] = []
        original = self.service.database._production_detail_from_connection

        def paused_detail(*args: object, **kwargs: object) -> dict[str, object] | None:
            detail = original(*args, **kwargs)
            snapshot_ready.set()
            self.assertTrue(resume_snapshot.wait(10))
            return detail

        with mock.patch.object(
            self.service.database,
            "_production_detail_from_connection",
            side_effect=paused_detail,
        ):
            thread = threading.Thread(
                target=lambda: captured.append(
                    self.service.database.production_audit_snapshot(PRODUCTION_ID)
                )
            )
            thread.start()
            self.assertTrue(snapshot_ready.wait(10))
            self.service.approve_run(
                created["run"]["id"],
                {
                    "approved": True,
                    "max_cost": {"amount": "1.00", "currency": "USD"},
                },
            )
            resume_snapshot.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        snapshot = captured[0]
        assert snapshot is not None
        self.assertIsNone(snapshot["runs"][0]["latest_approval"])
        self.assertEqual(snapshot["approvals"], [])
        self.assertFalse(any(event["event_type"] == "cost.approved" for event in snapshot["events"]))

    def test_workspace_escape_and_non_loopback_bind_are_rejected(self) -> None:
        with self.assertRaises(SecurityError):
            workspace_path(self.fixture.root, "../outside-artifact.mp4")
        with self.assertRaises(ValueError):
            create_server(
                self.fixture.root,
                host="0.0.0.0",
                port=0,
                initial_refresh=False,
            )
        with self.assertRaises(ValueError):
            create_server(
                self.fixture.root,
                port=0,
                allowed_origins=["https://attacker.example"],
                initial_refresh=False,
            )

    def test_structured_and_header_secrets_are_redacted(self) -> None:
        source = json.dumps(
            {
                "api_key": "plainprovidercredential123",
                "password": "hunter2longvalue",
                "authorization": "Basic dXNlcjpwYXNzd29yZA==",
                "cookie": "StudioSession=private-session-value",
                "safe": "retained",
            }
        )
        redacted = redact_artifact_text(source, suffix=".json")
        for secret in (
            "plainprovidercredential123",
            "hunter2longvalue",
            "dXNlcjpwYXNzd29yZA==",
            "private-session-value",
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn("retained", redacted)
        headers = redact_artifact_text(
            "Authorization: Basic dXNlcjpwYXNzd29yZA==\n"
            "Proxy-Authorization: Custom opaque-auth-value\n"
            "Cookie: session=private-session-value\n"
            "url=https://example.invalid/file?X-Amz-Signature=signed-value\n"
        )
        self.assertNotIn("dXNlcjpwYXNzd29yZA==", headers)
        self.assertNotIn("opaque-auth-value", headers)
        self.assertNotIn("private-session-value", headers)
        self.assertNotIn("signed-value", headers)

        quoted = redact_artifact_text(
            'password: "correct horse battery staple"\n'
            "api_key='another multi word secret'\n",
            suffix=".log",
        )
        self.assertNotIn("correct horse battery staple", quoted)
        self.assertNotIn("another multi word secret", quoted)
        self.assertIn('password: "[REDACTED]"', quoted)

        environment = redact_artifact_text(
            "MINIMAX_API_KEY=MINIMAXTOPSECRET123456\n"
            'OPENAI_API_KEY="OPENAITOPSECRET123456"\n'
            "AZURE_SPEECH_KEY: AZURETOPSECRET123456\n"
            "export ELEVENLABS_API_KEY=ELEVENLABSTOPSECRET123456\n"
            "set CUSTOM_API_TOKEN=WINDOWSTOPSECRET123456\n"
            "$env:CUSTOM_API_SECRET='POWERSHELLTOPSECRET123456'\n"
            "SAFE_SETTING=retained\n",
            suffix=".log",
        )
        for secret in (
            "MINIMAXTOPSECRET123456",
            "OPENAITOPSECRET123456",
            "AZURETOPSECRET123456",
            "ELEVENLABSTOPSECRET123456",
            "WINDOWSTOPSECRET123456",
            "POWERSHELLTOPSECRET123456",
        ):
            self.assertNotIn(secret, environment)
        self.assertIn("SAFE_SETTING=retained", environment)

    def test_unsafe_structured_text_artifacts_fail_closed(self) -> None:
        samples = {
            ".yaml": "api_key: |\n  top-secret-value\n",
            ".ini": 'password: "correct horse battery staple"\n',
            ".xml": "<authorization>top-secret-value</authorization>\n",
            ".html": "<authorization>top-secret-value</authorization>\n",
            ".svg": "<authorization>top-secret-value</authorization>\n",
            ".csv": "api_key,name\ntop-secret-value,demo\n",
            ".tsv": "api_key\tname\ntop-secret-value\tdemo\n",
        }
        for suffix, source in samples.items():
            with self.subTest(suffix=suffix):
                with self.assertRaises(UnsafeTextArtifactError):
                    redact_artifact_text(source, suffix=suffix)
        with self.assertRaises(UnsafeTextArtifactError):
            redact_artifact_text('{"api_key":"unterminated', suffix=".json")
        with self.assertRaises(UnsafeTextArtifactError):
            redact_artifact_text('{"status":"ok"}\nnot-json\n', suffix=".jsonl")

    def test_background_refresh_and_audit_export_are_inspectable(self) -> None:
        refresh = self.service.refresh_index()
        completed_refresh = self.service.jobs.wait(refresh["id"], timeout=10)
        assert completed_refresh is not None
        self.assertEqual(completed_refresh["status"], "succeeded")
        self.assertEqual(completed_refresh["result"]["productions"], 1)

        audit = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = self.service.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        artifact = completed["result"]["artifact"]
        archive_path = self.fixture.root / artifact["rel_path"]
        sidecar_path = self.fixture.root / completed["result"]["sha256_sidecar"]
        self.assertTrue(archive_path.is_file())
        self.assertTrue(sidecar_path.is_file())
        self.assertTrue(
            sidecar_path.read_text(encoding="ascii").startswith(artifact["sha256"])
        )
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertIn("audit/production-snapshot.json", names)
            self.assertIn("audit/events.jsonl", names)
            self.assertIn(f"studio-events/production/{PRODUCTION_ID}.jsonl", names)
            self.assertIn(
                f"workspace/productions/{PRODUCTION_ID}/PRODUCTION_RECORD_JA.md", names
            )
            archived_log = archive.read(
                f"workspace/outputs/productions/{PRODUCTION_ID}/logs/render.jsonl"
            ).decode("utf-8")
            self.assertNotIn(RAW_LOG_SECRET, archived_log)
            self.assertNotIn(RAW_JSON_SECRET, archived_log)
            package_manifest = json.loads(archive.read("audit/package-manifest.json"))
            self.assertIn(
                f"outputs/productions/{PRODUCTION_ID}/logs/render.jsonl",
                package_manifest["redacted_text_files"],
            )
            skipped = {
                entry["path"]: entry["reason"]
                for entry in package_manifest["skipped"]
            }
            for relative in (
                f"productions/{PRODUCTION_ID}/unsafe.conf",
                f"productions/{PRODUCTION_ID}/unsafe.html",
            ):
                self.assertEqual(
                    skipped[relative], "structured_text_requires_local_review"
                )
                self.assertNotIn(f"workspace/{relative}", names)
            unknown_relative = f"productions/{PRODUCTION_ID}/settings.properties"
            self.assertEqual(
                skipped[unknown_relative], "unsupported_artifact_kind"
            )
            self.assertNotIn(f"workspace/{unknown_relative}", names)
            for name in names:
                self.assertNotIn(RAW_UNKNOWN_SECRET.encode("utf-8"), archive.read(name))
            self.assertIn(f"production:{PRODUCTION_ID}", package_manifest["event_chain_tails"])
            for entry in package_manifest["archive_entries"]:
                payload = archive.read(entry["path"])
                self.assertEqual(len(payload), entry["bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest().upper(), entry["sha256"])
            self.assertNotIn(
                f"workspace/outputs/productions/{PRODUCTION_ID}/02_cuts/CUT01/clip.mp4",
                names,
            )

    def test_corrupt_event_mirror_is_degraded_and_excluded_from_audit(self) -> None:
        assert self.service is not None
        mirror = self.service.database.event_mirror_path("production", PRODUCTION_ID)
        with mirror.open("a", encoding="utf-8") as handle:
            handle.write('{"corrupt":true}\n')
        self.service.database.append_event(
            "run", "healthy_scope", "run.test", {"status": "ok"}
        )
        health = self.service.health()
        self.assertTrue(health["ok"])
        self.assertTrue(health["degraded"])
        self.assertGreater(health["event_mirror"]["issue_count"], 0)
        healthy_mirror = self.service.database.event_mirror_path("run", "healthy_scope")
        self.assertTrue(healthy_mirror.is_file())

        audit = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = self.service.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        archive_path = self.fixture.root / completed["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertNotIn(
                f"studio-events/production/{PRODUCTION_ID}.jsonl", names
            )
            package_manifest = json.loads(archive.read("audit/package-manifest.json"))
            skipped_scopes = {
                entry["scope"] for entry in package_manifest["skipped_event_mirrors"]
            }
            self.assertIn(f"production:{PRODUCTION_ID}", skipped_scopes)

    def test_sqlite_index_rebuild_restores_run_and_approval_from_event_mirror(self) -> None:
        assert self.service is not None
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "rebuild proof"}],
                "estimated_cost": {"amount": "0.50", "currency": "USD"},
            },
        )
        self.service.approve_run(
            created["run"]["id"],
            {
                "approved": True,
                "max_cost": {"amount": "1.00", "currency": "USD"},
                "note": "approved before rebuild",
            },
        )
        local = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script", "note": "local restore proof"}],
                "execution_profile": "local_sapi",
            },
        )
        local_timeline = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "timeline", "note": "timeline restore proof"}],
                "execution_profile": "local_sapi",
            },
        )
        local_comfyui = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "video", "note": "comfy restore proof"}],
                "execution_profile": "local_comfyui",
            },
        )
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            local_job = self.service.execute_local_narration(
                local["run"]["id"], {"segments": [{"text": "restore proof"}]}
            )
            completed_local = self.service.jobs.wait(local_job["id"], timeout=10)
        assert completed_local is not None
        self.assertEqual(completed_local["status"], "succeeded")
        restored_artifact_ids = {
            item["id"] for item in completed_local["result"]["artifacts"]
        }
        self.assertEqual(len(restored_artifact_ids), 4)
        database_path = self.service.database.path
        self.service.close()
        self.service = None
        database_path.unlink()
        database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
        database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)

        rebuilt = StudioService(self.fixture.root)
        self.service = rebuilt
        result = rebuilt.indexer.refresh()
        self.assertEqual(result["domain_records_restored"]["revisions"], 4)
        self.assertEqual(result["domain_records_restored"]["runs"], 4)
        self.assertEqual(result["domain_records_restored"]["stage_attempts"], 1)
        self.assertEqual(result["domain_records_restored"]["artifacts"], 4)
        self.assertEqual(result["domain_records_restored"]["approvals"], 1)
        detail = rebuilt.production_detail(PRODUCTION_ID)
        assert detail is not None
        restored_external = next(
            run for run in detail["runs"] if run["id"] == created["run"]["id"]
        )
        self.assertEqual(restored_external["latest_approval"]["decision"], "approved")
        restored_local = next(run for run in detail["runs"] if run["id"] == local["run"]["id"])
        self.assertEqual(restored_local["execution_profile"], "local_sapi")
        self.assertEqual(restored_local["stage_attempts"][0]["status"], "succeeded")
        self.assertEqual(restored_local["stage_attempts"][0]["job_id"], local_job["id"])
        self.assertTrue(
            restored_artifact_ids.issubset({artifact["id"] for artifact in detail["artifacts"]})
        )
        restored_timeline = next(
            run for run in detail["runs"] if run["id"] == local_timeline["run"]["id"]
        )
        self.assertEqual(restored_timeline["execution_profile"], "local_sapi")
        self.assertIn("timeline", restored_timeline["requested_stages"])
        restored_comfyui = next(
            run for run in detail["runs"] if run["id"] == local_comfyui["run"]["id"]
        )
        self.assertEqual(restored_comfyui["execution_profile"], "local_comfyui")
        self.assertIn("video_generation", restored_comfyui["requested_stages"])
        audit = rebuilt.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = rebuilt.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        archive_path = self.fixture.root / completed["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            narration_root = (
                f"workspace/outputs/studio/runs/{local['run']['id']}/narration/"
                f"{completed_local['result']['cache_key']}/"
            )
            self.assertIn(f"{narration_root}captions.srt", names)
            self.assertIn(f"{narration_root}timings.json", names)
            self.assertIn(f"{narration_root}manifest.json", names)
            self.assertNotIn(f"{narration_root}narration.wav", names)
            self.assertIn(
                f"studio-events/production/{PRODUCTION_ID}.jsonl", names
            )
            self.assertIn(
                f"studio-events/run/{created['run']['id']}.jsonl", names
            )

    def test_sqlite_rebuild_skips_hash_mismatched_studio_artifact(self) -> None:
        assert self.service is not None
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script", "note": "tamper restore proof"}],
                "execution_profile": "local_sapi",
            },
        )
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            job = self.service.execute_local_narration(
                created["run"]["id"], {"segments": [{"text": "restore tamper"}]}
            )
            completed = self.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        artifacts = completed["result"]["artifacts"]
        tampered = next(item for item in artifacts if item["name"] == "narration.wav")
        tampered_path = self.fixture.root / tampered["rel_path"]
        original_size = tampered_path.stat().st_size
        tampered_path.write_bytes(b"X" * original_size)

        database_path = self.service.database.path
        self.service.close()
        self.service = None
        database_path.unlink()
        database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
        database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)

        rebuilt = StudioService(self.fixture.root)
        self.service = rebuilt
        result = rebuilt.indexer.refresh()
        self.assertEqual(result["domain_records_restored"]["artifacts"], 3)
        detail = rebuilt.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertNotIn(tampered["id"], {item["id"] for item in detail["artifacts"]})

    def test_sqlite_rebuild_safely_skips_legacy_incomplete_artifact_event(self) -> None:
        assert self.service is not None
        legacy_id = "art_" + "1" * 32
        legacy_path = self.fixture.root / "outputs" / "studio" / "legacy" / "orphan.txt"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("legacy artifact without restorable metadata\n", encoding="utf-8")
        with self.service.database.transaction() as connection:
            self.service.database._append_event(
                connection,
                "production",
                PRODUCTION_ID,
                "artifact.created",
                {"artifact_id": legacy_id, "kind": "document"},
            )

        database_path = self.service.database.path
        self.service.close()
        self.service = None
        database_path.unlink()
        database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
        database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)

        rebuilt = StudioService(self.fixture.root)
        self.service = rebuilt
        result = rebuilt.indexer.refresh()
        self.assertEqual(result["domain_records_restored"]["artifacts"], 0)
        self.assertIsNone(rebuilt.database.get_artifact(legacy_id))


class HTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "test-session-token-with-at-least-thirty-two-characters"
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
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.fixture.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = dict(headers or {})
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("Content-Length", str(len(data)))
        self.connection.request(method, path, body=data, headers=request_headers)
        response = self.connection.getresponse()
        payload = response.read()
        return response.status, {key.casefold(): value for key, value in response.getheaders()}, payload

    def test_static_cookie_auth_origin_and_health_do_not_expose_token(self) -> None:
        status, headers, _body = self.request("GET", "/")
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        status, health_headers, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertNotIn(self.token.encode(), body)
        self.assertNotIn(self.token, json.dumps(health_headers))

        status, _headers, _body = self.request(
            "POST", "/api/index/refresh", body={}
        )
        self.assertEqual(status, 403)
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie},
        )
        self.assertEqual(status, 403)
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie, "Origin": "https://attacker.example"},
        )
        self.assertEqual(status, 403)
        status, _headers, body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie, "Origin": self.origin},
        )
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["kind"], "index_refresh")
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 202)

    def test_local_narration_http_endpoint_records_attempt_and_run_detail(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "execution_profile": "local_sapi",
            },
        )
        run_id = created["run"]["id"]
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            status, _headers, body = self.request(
                "POST",
                f"/api/runs/{run_id}/execute-local-narration",
                body={"segments": [{"text": "hello local narration"}], "rate": 0},
                headers={"X-Studio-Token": self.token},
            )
            self.assertEqual(status, 202)
            job_id = json.loads(body)["id"]
            completed = self.server.service.jobs.wait(job_id, timeout=10)
            assert completed is not None
            self.assertEqual(completed["status"], "succeeded")

        status, _headers, body = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        run = json.loads(body)
        self.assertEqual(run["execution_profile"], "local_sapi")
        self.assertEqual(run["stage_attempts"][0]["status"], "succeeded")
        self.assertEqual(run["stage_attempts"][0]["job_id"], job_id)

        external = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": 1, "currency": "USD"},
            },
        )
        status, _headers, body = self.request(
            "POST",
            f"/api/runs/{external['run']['id']}/execute-local-narration",
            body={"segments": [{"text": "must fail closed"}]},
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "execution_profile_required")

    def test_local_comfyui_video_generation_http_route_forwards_exact_body(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "video"}],
                "execution_profile": "local_comfyui",
            },
        )
        run_id = created["run"]["id"]
        request_body = {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": "A presenter turns toward the camera.",
            "seed": 9_223_372_036_854_775_807,
        }
        queued = {
            "id": "job_" + "a" * 32,
            "kind": "local_video_generation",
            "status": "queued",
        }
        with mock.patch.object(
            self.server.service,
            "execute_local_video_generation",
            return_value=queued,
        ) as execute:
            status, _headers, body = self.request(
                "POST",
                f"/api/runs/{run_id}/execute-local-video-generation",
                body=request_body,
                headers={"X-Studio-Token": self.token},
            )
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body), queued)
        execute.assert_called_once_with(run_id, request_body)

    def test_local_timeline_http_endpoint_records_attempt_and_artifacts(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "timeline"}],
                "execution_profile": "local_sapi",
            },
        )
        run_id = created["run"]["id"]
        detail = self.server.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        module = types.ModuleType("tools.studio.timeline")
        module.timeline_cache_key = lambda _clips: "C" * 64
        module.generate_local_timeline = fake_local_timeline_result
        module.validate_local_timeline_outputs = fake_validate_local_timeline_outputs
        with (
            mock.patch.dict(sys.modules, {"tools.studio.timeline": module}),
            mock.patch("tools.studio.timeline", module, create=True),
        ):
            status, _headers, body = self.request(
                "POST",
                f"/api/runs/{run_id}/execute-local-timeline",
                body={
                    "clips": [
                        {
                            "video_artifact_id": video["id"],
                            "start_ms": 0,
                            "end_ms": 125,
                        }
                    ]
                },
                headers={"X-Studio-Token": self.token},
            )
            self.assertEqual(status, 202)
            job_id = json.loads(body)["id"]
            completed = self.server.service.jobs.wait(job_id, timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(len(completed["result"]["artifacts"]), 4)
        status, _headers, response = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        run = json.loads(response)
        timeline_attempt = next(
            attempt for attempt in run["stage_attempts"] if attempt["stage"] == "timeline"
        )
        self.assertEqual(timeline_attempt["status"], "succeeded")
        self.assertEqual(timeline_attempt["job_id"], job_id)
        status, _headers, response = self.request(
            "POST",
            f"/api/runs/{run_id}/execute-local-timeline",
            body={
                "clips": [
                    {
                        "video_artifact_id": video["id"],
                        "start_ms": 0,
                        "end_ms": 125,
                    }
                ],
                "unexpected": True,
            },
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 422)
        self.assertEqual(
            json.loads(response)["error"]["code"],
            "invalid_local_timeline_request",
        )

    def test_local_assembly_http_endpoint_records_attempt_and_artifacts(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "execution_profile": "local_sapi",
            },
        )
        run_id = created["run"]["id"]
        with mock.patch(
            "tools.studio.narration.generate_local_narration",
            side_effect=fake_local_narration_result,
        ):
            narration_job = self.server.service.execute_local_narration(
                run_id, {"segments": [{"text": "assembly endpoint"}]}
            )
            narration = self.server.service.jobs.wait(narration_job["id"], timeout=10)
        assert narration is not None
        detail = self.server.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        request_body = {
            "video_artifact_id": video["id"],
            "narration_attempt_id": narration["result"]["stage_attempt_id"],
            "include_captioned": False,
        }
        cache_key = "B" * 64
        with (
            mock.patch("tools.studio.assembly.assembly_cache_key", return_value=cache_key),
            mock.patch(
                "tools.studio.assembly.generate_local_assembly",
                side_effect=fake_local_assembly_result,
            ),
            mock.patch(
                "tools.studio.assembly.validate_local_assembly_outputs",
                side_effect=fake_validate_local_assembly_outputs,
            ),
        ):
            status, _headers, body = self.request(
                "POST",
                f"/api/runs/{run_id}/execute-local-assembly",
                body=request_body,
                headers={"X-Studio-Token": self.token},
            )
            self.assertEqual(status, 202)
            job_id = json.loads(body)["id"]
            completed = self.server.service.jobs.wait(job_id, timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(len(completed["result"]["artifacts"]), 3)
        self.assertFalse(
            any(
                artifact["name"] == "master-captioned.mp4"
                for artifact in completed["result"]["artifacts"]
            )
        )

        status, _headers, body = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        run = json.loads(body)
        assembly_attempt = next(
            attempt for attempt in run["stage_attempts"] if attempt["stage"] == "assembly"
        )
        self.assertEqual(assembly_attempt["status"], "succeeded")
        self.assertEqual(assembly_attempt["job_id"], job_id)

        invalid_body = dict(request_body)
        invalid_body["unexpected"] = True
        status, _headers, body = self.request(
            "POST",
            f"/api/runs/{run_id}/execute-local-assembly",
            body=invalid_body,
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 422)
        self.assertEqual(
            json.loads(body)["error"]["code"], "invalid_local_assembly_request"
        )

    def test_local_qc_http_endpoint_records_analysis_and_verdict(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "assembly"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        assembly_attempt, _master = create_succeeded_assembly_attempt(
            self.server.service, run_id
        )
        body = {
            "assembly_attempt_id": assembly_attempt["id"],
            "variant": "clean",
        }
        with (
            mock.patch("tools.studio.qc.qc_cache_key", return_value="9" * 64),
            mock.patch(
                "tools.studio.qc.generate_local_qc", side_effect=fake_local_qc_result
            ),
            mock.patch(
                "tools.studio.qc.validate_local_qc_outputs",
                side_effect=fake_validate_local_qc_outputs,
            ),
        ):
            status, _headers, response = self.request(
                "POST",
                f"/api/runs/{run_id}/execute-local-qc",
                body=body,
                headers={"X-Studio-Token": self.token},
            )
            self.assertEqual(status, 202)
            job_id = json.loads(response)["id"]
            completed = self.server.service.jobs.wait(job_id, timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["result"]["analysis_status"], "succeeded")
        self.assertEqual(completed["result"]["technical_verdict"], "pass")
        self.assertEqual(len(completed["result"]["artifacts"]), 3)

        status, _headers, response = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        run = json.loads(response)
        qc_attempt = next(
            attempt for attempt in run["stage_attempts"] if attempt["stage"] == "qc"
        )
        self.assertEqual(qc_attempt["status"], "succeeded")
        self.assertEqual(qc_attempt["job_id"], job_id)

        status, _headers, response = self.request(
            "POST",
            f"/api/runs/{run_id}/execute-local-qc",
            body={**body, "expected_duration_ms": 1_000},
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(response)["error"]["code"], "invalid_local_qc_request")

    def test_workspace_allows_only_one_studio_server(self) -> None:
        with self.assertRaises(StudioInstanceLockError):
            create_server(
                self.fixture.root,
                host="127.0.0.1",
                port=0,
                session_token="second-session-token-with-thirty-two-characters",
                initial_refresh=False,
            )

    def test_artifact_file_supports_head_range_and_content_alias(self) -> None:
        status, _headers, body = self.request("GET", f"/api/productions/{PRODUCTION_ID}")
        self.assertEqual(status, 200)
        detail = json.loads(body)
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        for endpoint in ("file", "content"):
            status, headers, body = self.request(
                "GET",
                f"/api/artifacts/{video['id']}/{endpoint}",
                headers={"Range": "bytes=2-7"},
            )
            self.assertEqual(status, 206)
            self.assertEqual(body, VIDEO_BYTES[2:8])
            self.assertEqual(headers["content-range"], f"bytes 2-7/{len(VIDEO_BYTES)}")
        status, headers, body = self.request(
            "HEAD", f"/api/artifacts/{video['id']}/file"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["content-length"]), len(VIDEO_BYTES))
        status, headers, _body = self.request(
            "GET",
            f"/api/artifacts/{video['id']}/file",
            headers={"Range": "bytes=999-1000"},
        )
        self.assertEqual(status, 416)
        self.assertEqual(headers["content-range"], f"bytes */{len(VIDEO_BYTES)}")

    def test_text_artifacts_are_redacted_and_active_content_is_sandboxed(self) -> None:
        status, _headers, body = self.request("GET", f"/api/productions/{PRODUCTION_ID}")
        self.assertEqual(status, 200)
        artifacts = json.loads(body)["artifacts"]
        log = next(item for item in artifacts if item["name"] == "render.jsonl")
        status, headers, body = self.request("GET", log["file_url"])
        self.assertEqual(status, 200)
        self.assertEqual(headers["x-studio-content-redacted"], "true")
        self.assertTrue(headers["content-disposition"].startswith("attachment;"))
        self.assertIn("sandbox", headers["content-security-policy"])
        self.assertNotIn(RAW_LOG_SECRET.encode("utf-8"), body)
        self.assertNotIn(RAW_JSON_SECRET.encode("utf-8"), body)
        self.assertIn(b"[REDACTED]", body)

        unsafe_config = next(item for item in artifacts if item["name"] == "unsafe.conf")
        status, _headers, body = self.request("GET", unsafe_config["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(RAW_CONFIG_SECRET.encode("utf-8"), body)
        self.assertEqual(
            json.loads(body)["error"]["code"],
            "artifact_format_requires_local_review",
        )

        html = next(item for item in artifacts if item["name"] == "unsafe.html")
        status, _headers, body = self.request("GET", html["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(b"fetch('/api/index/refresh'", body)

        unknown = next(item for item in artifacts if item["name"] == "settings.properties")
        status, _headers, body = self.request("GET", unknown["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(RAW_UNKNOWN_SECRET.encode("utf-8"), body)

    def test_provider_status_returns_flags_only(self) -> None:
        secret = "provider-value-that-must-never-be-returned"
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": secret}, clear=False):
            status, _headers, body = self.request("GET", "/api/providers/status")
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertNotIn(secret, body.decode("utf-8"))
        for provider in value["providers"]:
            self.assertEqual(set(provider), {"id", "configured"})
        elevenlabs = next(item for item in value["providers"] if item["id"] == "elevenlabs")
        self.assertTrue(elevenlabs["configured"])

    def test_studio_generated_audit_zip_remains_downloadable(self) -> None:
        job = self.server.service.audit_export(
            PRODUCTION_ID, {"include_media": False}
        )
        completed = self.server.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        artifact = completed["result"]["artifact"]
        status, headers, body = self.request("GET", artifact["file_url"])
        self.assertEqual(status, 200)
        self.assertIn("zip", headers["content-type"])
        self.assertTrue(body.startswith(b"PK"))


@unittest.skipUnless(dpapi_available(), "Windows DPAPI is required")
class SecretStoreTests(unittest.TestCase):
    def test_dpapi_file_never_contains_plaintext(self) -> None:
        fixture = WorkspaceFixture()
        try:
            secret = "dpapi-secret-value-123456789"
            store = SecretStore(fixture.root)
            store.set("openai", secret)
            encrypted = (fixture.root / "outputs" / "studio" / "secrets" / "openai.dpapi").read_bytes()
            self.assertNotIn(secret.encode("utf-8"), encrypted)
            self.assertEqual(store.get("openai"), secret)
            status = store.statuses()
            self.assertNotIn(secret, json.dumps(status))
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
