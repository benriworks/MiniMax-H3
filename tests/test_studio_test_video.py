from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.studio.test_video import TestVideoError, run_test_video


PRODUCTION_ID = "TEST_TEST_VIDEO"
SOURCE_ID = "art_" + "a" * 32
TIMELINE_ID = "art_" + "b" * 32
MASTER_CLEAN_ID = "art_" + "c" * 32
MASTER_CAPTIONED_ID = "art_" + "d" * 32
ATTEMPTS = {
    "narration": "attempt_" + "1" * 32,
    "timeline": "attempt_" + "2" * 32,
    "assembly": "attempt_" + "3" * 32,
    "qc": "attempt_" + "4" * 32,
}
JOBS = {
    "narration": "job_" + "1" * 32,
    "timeline": "job_" + "2" * 32,
    "assembly": "job_" + "3" * 32,
    "qc": "job_" + "4" * 32,
}


class FakeStudioService:
    def __init__(self, workspace: Path, *, qc_verdict: str = "pass") -> None:
        self.workspace = workspace
        self.qc_verdict = qc_verdict
        self.calls: list[tuple[str, Any]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        source_path = workspace / "productions" / PRODUCTION_ID / "source.mp4"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"fake source video")
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
        self.source = {
            "id": SOURCE_ID,
            "production_id": PRODUCTION_ID,
            "available": True,
            "kind": "video",
            "media_type": "video/mp4",
            "name": "source.mp4",
            "rel_path": source_path.relative_to(workspace).as_posix(),
            "bytes": source_path.stat().st_size,
            "sha256": source_hash,
        }
        self._artifacts = {SOURCE_ID: self.source}

    def production_detail(self, production_id: str) -> dict[str, Any] | None:
        self.calls.append(("production_detail", production_id))
        return {"id": production_id, "artifacts": list(self._artifacts.values())}

    def artifact(self, artifact_id: str) -> dict[str, Any] | None:
        self.calls.append(("artifact", artifact_id))
        return self._artifacts.get(artifact_id)

    def create_run(self, production_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_run", (production_id, body)))
        return {
            "revision": {"id": "revision_" + "1" * 32},
            "run": {
                "id": "run_" + "1" * 32,
                "production_id": production_id,
                "execution_profile": "local_sapi",
            },
        }

    @staticmethod
    def _artifact(
        artifact_id: str,
        name: str,
        kind: str,
        media_type: str,
    ) -> dict[str, Any]:
        return {
            "id": artifact_id,
            "name": name,
            "kind": kind,
            "media_type": media_type,
            "rel_path": f"outputs/studio/test/{name}",
            "bytes": 1,
            "sha256": "0" * 64,
        }

    def _queue(self, stage: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((stage, (run_id, payload)))
        job_id = JOBS[stage]
        result: dict[str, Any] = {"cache_hit": stage == "timeline"}
        if stage == "narration":
            result["artifacts"] = []
        elif stage == "timeline":
            result["artifacts"] = [
                self._artifact(TIMELINE_ID, "timeline-preview.mp4", "video", "video/mp4")
            ]
        elif stage == "assembly":
            result["artifacts"] = [
                self._artifact(MASTER_CLEAN_ID, "master-clean.mp4", "video", "video/mp4"),
                self._artifact(
                    MASTER_CAPTIONED_ID,
                    "master-captioned.mp4",
                    "video",
                    "video/mp4",
                ),
            ]
        elif stage == "qc":
            result.update(
                {
                    "analysis_status": "succeeded",
                    "technical_verdict": self.qc_verdict,
                    "artifacts": [
                        self._artifact(
                            "art_" + "e" * 32,
                            "technical-qc.json",
                            "document",
                            "application/json",
                        ),
                        self._artifact(
                            "art_" + "f" * 32,
                            "ffprobe.json",
                            "document",
                            "application/json",
                        ),
                        self._artifact(
                            "art_" + "0" * 32,
                            "manifest.json",
                            "document",
                            "application/json",
                        ),
                    ],
                }
            )
        job = {
            "id": job_id,
            "status": "succeeded",
            "stage_attempt_id": ATTEMPTS[stage],
            "result": result,
        }
        self.jobs[job_id] = job
        return {"id": job_id, "status": "queued", "stage_attempt_id": ATTEMPTS[stage]}

    def execute_local_narration(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._queue("narration", run_id, payload)

    def execute_local_timeline(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._queue("timeline", run_id, payload)

    def execute_local_assembly(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._queue("assembly", run_id, payload)

    def execute_local_qc(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._queue("qc", run_id, payload)

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
        del timeout
        self.calls.append(("wait", job_id))
        return self.jobs[job_id]


class TestVideoOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, **overrides: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "production_id": PRODUCTION_ID,
            "source_artifact_id": SOURCE_ID,
            "segments": [{"text": "one local test"}],
            "voice": None,
            "rate": 0,
            "pronunciations": [],
            "end_ms": 1_000,
            "timeout": 30,
            "include_captioned": True,
            "variant": "clean",
        }
        result.update(overrides)
        return result

    def test_happy_path_is_ordered_and_uses_timeline_artifact_for_assembly(self) -> None:
        service = FakeStudioService(self.workspace)
        result = run_test_video(service, self.request())

        self.assertEqual(result["production_id"], PRODUCTION_ID)
        self.assertEqual(result["run_id"], "run_" + "1" * 32)
        self.assertEqual(result["revision_id"], "revision_" + "1" * 32)
        self.assertEqual(result["timeline"]["id"], TIMELINE_ID)
        self.assertEqual(result["master"]["id"], MASTER_CLEAN_ID)
        self.assertEqual(result["qc"]["verdict"], "pass")
        self.assertEqual(
            [name for name, _value in service.calls if name in {"narration", "timeline", "assembly", "qc"}],
            ["narration", "timeline", "assembly", "qc"],
        )
        assembly_call = next(value for name, value in service.calls if name == "assembly")
        self.assertEqual(assembly_call[1]["video_artifact_id"], TIMELINE_ID)
        self.assertEqual(assembly_call[1]["narration_attempt_id"], ATTEMPTS["narration"])
        self.assertEqual(result["jobs"]["timeline"]["cache_hit"], True)
        json.dumps(result)

    def test_optional_start_ms_is_forwarded_to_the_single_timeline_clip(self) -> None:
        service = FakeStudioService(self.workspace)
        run_test_video(service, self.request(start_ms=100, end_ms=1_100))
        timeline_call = next(value for name, value in service.calls if name == "timeline")
        self.assertEqual(timeline_call[1]["clips"][0]["start_ms"], 100)
        self.assertEqual(timeline_call[1]["clips"][0]["end_ms"], 1_100)

    def test_failed_stage_is_public_and_does_not_leak_worker_text(self) -> None:
        service = FakeStudioService(self.workspace)
        original = service.execute_local_timeline

        def fail(_run_id: str, _payload: dict[str, Any]) -> dict[str, Any]:
            queued = original(_run_id, _payload)
            service.jobs[queued["id"]]["status"] = "failed"
            service.jobs[queued["id"]]["error"] = {
                "message": f"C:\\secret\\token=do-not-leak\\{self.workspace}"
            }
            return queued

        service.execute_local_timeline = fail  # type: ignore[method-assign]
        with self.assertRaises(TestVideoError) as raised:
            run_test_video(service, self.request())
        self.assertEqual(raised.exception.error_code, "stage_failed")
        self.assertNotIn("do-not-leak", raised.exception.public_message)
        self.assertNotIn(str(self.workspace), raised.exception.public_message)

    def test_timeout_is_public_and_does_not_start_later_stages(self) -> None:
        service = FakeStudioService(self.workspace)

        def timeout(_job_id: str, _timeout: float = 30.0) -> dict[str, Any]:
            raise TimeoutError("C:\\secret\\timeout-token")

        service.wait = timeout  # type: ignore[method-assign]
        with self.assertRaises(TestVideoError) as raised:
            run_test_video(service, self.request(timeout=1))
        self.assertEqual(raised.exception.error_code, "timeout")
        self.assertNotIn("timeout-token", raised.exception.public_message)
        self.assertNotIn("assembly", [name for name, _value in service.calls])

    def test_wrong_source_artifact_is_rejected_before_run_creation(self) -> None:
        service = FakeStudioService(self.workspace)
        service.source["production_id"] = "OTHER_PRODUCTION"
        with self.assertRaises(TestVideoError) as raised:
            run_test_video(service, self.request())
        self.assertEqual(raised.exception.error_code, "source_artifact_not_available")
        self.assertNotIn("create_run", [name for name, _value in service.calls])

    def test_qc_fail_is_not_a_successful_test_video(self) -> None:
        service = FakeStudioService(self.workspace, qc_verdict="fail")
        with self.assertRaises(TestVideoError) as raised:
            run_test_video(service, self.request(variant="captioned"))
        self.assertEqual(raised.exception.error_code, "technical_qc_failed")
        self.assertEqual(raised.exception.public_message, "Local technical QC did not pass.")

    def test_embedded_artifact_path_traversal_stops_before_assembly(self) -> None:
        service = FakeStudioService(self.workspace)
        original = service.execute_local_timeline

        def return_traversal(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            queued = original(run_id, payload)
            artifact = service.jobs[queued["id"]]["result"]["artifacts"][0]
            artifact["rel_path"] = "outputs/studio/ok/../../outside.mp4"
            return queued

        service.execute_local_timeline = return_traversal  # type: ignore[method-assign]
        with self.assertRaises(TestVideoError) as raised:
            run_test_video(service, self.request())

        self.assertEqual(raised.exception.error_code, "invalid_worker_result")
        self.assertNotIn("assembly", [name for name, _value in service.calls])


if __name__ == "__main__":
    unittest.main()
