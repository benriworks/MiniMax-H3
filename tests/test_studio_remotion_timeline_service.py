from __future__ import annotations

import hashlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.test_studio_backend import PRODUCTION_ID, WorkspaceFixture
from tools.studio.service import RequestValidationError, StudioService


def _fake_artifacts(
    workspace: Path, *, run_id: str, cache_key: str
) -> list[dict[str, object]]:
    output = (
        workspace
        / "outputs"
        / "studio"
        / "runs"
        / run_id
        / "remotion_timeline"
        / cache_key
    )
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "remotion-preview.mp4": ("video", "video/mp4", b"remotion-preview"),
        "remotion-timeline.json": ("document", "application/json", b"{}\n"),
        "render-report.json": ("document", "application/json", b"{}\n"),
        "ffprobe.json": ("document", "application/json", b"{}\n"),
        "manifest.json": ("document", "application/json", b"{}\n"),
    }
    artifacts: list[dict[str, object]] = []
    for name, (kind, media_type, content) in files.items():
        path = output / name
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


def _fake_result(
    workspace: Path,
    *,
    run_id: str,
    cache_key: str,
    cache_hit: bool,
) -> dict[str, object]:
    return {
        "artifacts": _fake_artifacts(workspace, run_id=run_id, cache_key=cache_key),
        "duration_ms": 3_000,
        "cache_key": cache_key,
        "cache_hit": cache_hit,
        "provider": "local_remotion_timeline",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "remotion_frames",
        "has_audio": True,
    }


class RemotionTimelineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def module(self) -> types.ModuleType:
        module = types.ModuleType("tools.studio.remotion_timeline")
        module.resolve_remotion_tool_identity = lambda *_args, **_kwargs: {
            "remotion": {"version": "4.0.517", "sha256": "A" * 64},
            "chromium": {"version": "151.0.7922.34", "sha256": "B" * 64},
        }

        def generate(
            workspace: Path,
            *,
            run_id: str,
            cache_key: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            return _fake_result(
                workspace, run_id=run_id, cache_key=cache_key, cache_hit=False
            )

        def validate(
            workspace: Path,
            *,
            run_id: str,
            cache_key: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            return _fake_result(
                workspace, run_id=run_id, cache_key=cache_key, cache_hit=True
            )

        module.generate_remotion_timeline = generate
        module.validate_remotion_timeline_outputs = validate
        module.discard_remotion_timeline_outputs = lambda *_args, **_kwargs: True
        return module

    def payload(self, video_artifact_id: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "clips": [
                {
                    "video_artifact_id": video_artifact_id,
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "volume_percent": 75,
                    "transition_to_next": {"type": "fade", "duration_ms": 500},
                    "overlay": {
                        "text": "監査ログには生テキストを残さない",
                        "start_ms": 250,
                        "end_ms": 1_750,
                        "position": "bottom",
                        "style_preset": "shorts_ja_large_v1",
                    },
                },
                {
                    "video_artifact_id": video_artifact_id,
                    "start_ms": 0,
                    "end_ms": 1_500,
                    "volume_percent": 0,
                    "transition_to_next": None,
                    "overlay": None,
                },
            ],
        }

    def test_queues_browser_lane_and_atomically_registers_closed_outputs(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "timeline"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        payload = self.payload(video["id"])
        module = self.module()
        with (
            mock.patch.dict(sys.modules, {"tools.studio.remotion_timeline": module}),
            mock.patch("tools.studio.remotion_timeline", module, create=True),
        ):
            queued = self.service.execute_remotion_timeline(run_id, payload)
            completed = self.service.jobs.wait(queued["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["kind"], "local_remotion_timeline")
        self.assertEqual(completed["result"]["duration_ms"], 3_000)
        self.assertEqual(
            {item["name"] for item in completed["result"]["artifacts"]},
            {
                "remotion-preview.mp4",
                "remotion-timeline.json",
                "render-report.json",
                "ffprobe.json",
                "manifest.json",
            },
        )
        run = self.service.run(run_id)
        assert run is not None
        attempt = next(item for item in run["stage_attempts"] if item["id"] == queued["stage_attempt_id"])
        self.assertEqual(attempt["status"], "succeeded")
        persisted = json.dumps(
            {"job": completed, "attempt": attempt}, ensure_ascii=False
        )
        self.assertNotIn("監査ログには生テキストを残さない", persisted)
        self.assertIn("text_sha256", persisted)

    def test_rejects_unregistered_inputs_and_extra_recipe_fields(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {"changes": [{"type": "timeline"}], "execution_profile": "local_sapi"},
        )
        run_id = created["run"]["id"]
        module = self.module()
        with (
            mock.patch.dict(sys.modules, {"tools.studio.remotion_timeline": module}),
            mock.patch("tools.studio.remotion_timeline", module, create=True),
        ):
            with self.assertRaises(RequestValidationError):
                self.service.execute_remotion_timeline(
                    run_id,
                    self.payload("art_ffffffffffffffffffffffffffffffff"),
                )
            detail = self.service.production_detail(PRODUCTION_ID)
            assert detail is not None
            video = next(item for item in detail["artifacts"] if item["kind"] == "video")
            with self.assertRaises(RequestValidationError):
                self.service.execute_remotion_timeline(
                    run_id,
                    {**self.payload(video["id"]), "component": "Arbitrary"},
                )


if __name__ == "__main__":
    unittest.main()
