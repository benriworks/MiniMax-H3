from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.studio import assembly as assembly_module
from tools.studio import timeline as timeline_module
from tools.studio.assembly import AssemblyToolError
from tools.studio.jobs import JobCancelled, JobExecutionContext
from tools.studio.timeline import (
    IMPLEMENTATION_VERSION,
    OUTPUT_POLICY_VERSION,
    TimelineError,
    TimelineValidationError,
    generate_local_timeline,
    timeline_cache_key,
    validate_local_timeline_outputs,
)
from tools.studio.timeline_execution import (
    timeline_cache_key as control_timeline_cache_key,
    validate_local_timeline_payload,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _dominant_frame_labels(path: Path) -> list[str]:
    """Read one RGB pixel per output frame for deterministic color ordering."""

    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            "scale=1:1,format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        stdin=subprocess.DEVNULL,
    )
    return [
        "rgb"[max(range(3), key=lambda channel: frame[channel])]
        for frame in (raw[index : index + 3] for index in range(0, len(raw), 3))
        if len(frame) == 3
    ]


class LocalTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise unittest.SkipTest("ffmpeg and ffprobe are required for timeline tests")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.registered = self.workspace / "registered"
        self.registered.mkdir(parents=True)
        self.sources: list[Path] = []
        for index, color in enumerate(("red", "green", "blue")):
            path = self.registered / f"clip-{index}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:size=64x64:rate=24",
                    "-t",
                    "1.250",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(path),
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.sources.append(path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _clips(self) -> list[dict[str, object]]:
        return [
            {
                "video_artifact_id": f"art_{index + 1:032x}",
                "start_ms": start,
                "end_ms": end,
                "source_path": path.relative_to(self.workspace).as_posix(),
                "source_bytes": path.stat().st_size,
                "source_sha256": _sha256(path),
            }
            for index, (path, start, end) in enumerate(
                zip(self.sources, (0, 100, 200), (300, 400, 500), strict=True)
            )
        ]

    def _key(self, clips: list[dict[str, object]] | None = None) -> str:
        return timeline_cache_key(clips or self._clips())

    def _run(self, clips: list[dict[str, object]] | None = None) -> dict[str, object]:
        clips = clips or self._clips()
        return generate_local_timeline(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            cache_key=self._key(clips),
            clips=clips,
        )

    def test_public_payload_is_exact_and_fail_closed(self) -> None:
        valid = {
            "clips": [
                {
                    "video_artifact_id": "art_00000000000000000000000000000001",
                    "start_ms": 0,
                    "end_ms": 50,
                }
            ]
        }
        self.assertEqual(validate_local_timeline_payload(valid), valid)
        for body in (
            {**valid, "narration_attempt_id": "attempt_" + "0" * 32},
            {"clips": [{**valid["clips"][0], "extra": 1}]},
            {"clips": [{**valid["clips"][0], "start_ms": True}]},
            {"clips": [{**valid["clips"][0], "end_ms": 49}]},
        ):
            with self.subTest(body=body), self.assertRaises(TimelineValidationError):
                validate_local_timeline_payload(body)

    def test_public_payload_bounds_clip_count_and_total_duration(self) -> None:
        clip = {
            "video_artifact_id": "art_00000000000000000000000000000001",
            "start_ms": 0,
            "end_ms": 50,
        }
        with self.assertRaises(TimelineValidationError):
            validate_local_timeline_payload({"clips": [clip] * 33})
        too_long = {
            "video_artifact_id": clip["video_artifact_id"],
            "start_ms": 0,
            "end_ms": 30 * 60 * 1000,
        }
        with self.assertRaises(TimelineValidationError):
            validate_local_timeline_payload({"clips": [too_long, too_long]})

    def test_generates_three_clip_fixed_video_only_timeline_and_cache_hit(self) -> None:
        first = self._run()
        self.assertFalse(first["cache_hit"])
        self.assertEqual(first["provider"], "local_ffmpeg_timeline")
        self.assertEqual(first["provider_task_id"], None)
        self.assertEqual(first["actual_cost"], 0)
        self.assertEqual(first["duration_ms"], 900)
        self.assertEqual(
            {item["name"] for item in first["artifacts"]},  # type: ignore[index]
            {"timeline-preview.mp4", "timeline.json", "ffprobe.json", "manifest.json"},
        )
        output_root = self.workspace / first["output_directory"]  # type: ignore[arg-type]
        timeline = json.loads((output_root / "timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [item["video_artifact_id"] for item in timeline["clips"]],
            [item["video_artifact_id"] for item in self._clips()],
        )
        self.assertEqual([item["duration_ms"] for item in timeline["clips"]], [300, 300, 300])
        manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
        digest = manifest.pop("manifest_sha256")
        self.assertEqual(_sha256_json(manifest), digest)
        self.assertEqual(manifest["implementation_version"], IMPLEMENTATION_VERSION)
        self.assertEqual(manifest["output_policy"]["policy_version"], OUTPUT_POLICY_VERSION)
        probe = json.loads((output_root / "ffprobe.json").read_text(encoding="utf-8"))
        streams = probe["timeline_preview"]["streams"]
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["codec_type"], "video")
        self.assertEqual(streams[0]["codec_name"], "h264")
        self.assertEqual(streams[0]["pix_fmt"], "yuv420p")
        self.assertEqual((streams[0]["width"], streams[0]["height"]), (1080, 1920))
        second = self._run()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["cache_key"], first["cache_key"])
        validated = validate_local_timeline_outputs(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            cache_key=self._key(),
            clips=self._clips(),
        )
        self.assertTrue(validated["cache_hit"])

    def test_minimum_duration_clips_do_not_accumulate_frame_rounding_drift(self) -> None:
        source = self.sources[0]
        clips = [
            {
                "video_artifact_id": f"art_{index + 1:032x}",
                "start_ms": 0,
                "end_ms": 50,
                "source_path": source.relative_to(self.workspace).as_posix(),
                "source_bytes": source.stat().st_size,
                "source_sha256": _sha256(source),
            }
            for index in range(32)
        ]
        result = self._run(clips)
        self.assertEqual(result["duration_ms"], 1_600)
        output_root = self.workspace / result["output_directory"]  # type: ignore[arg-type]
        probe = json.loads((output_root / "ffprobe.json").read_text(encoding="utf-8"))
        actual_ms = round(float(probe["timeline_preview"]["format"]["duration"]) * 1_000)
        self.assertLessEqual(abs(actual_ms - 1_600), 50)

    def test_frame_budget_preserves_order_and_last_clip_at_boundaries(self) -> None:
        clips = [
            {
                "video_artifact_id": f"art_{index + 1:032x}",
                "start_ms": 0,
                "end_ms": 50,
                "source_path": source.relative_to(self.workspace).as_posix(),
                "source_bytes": source.stat().st_size,
                "source_sha256": _sha256(source),
            }
            for index, source in enumerate(self.sources)
        ]
        result = self._run(clips)
        output_root = self.workspace / result["output_directory"]  # type: ignore[arg-type]
        labels = _dominant_frame_labels(output_root / "timeline-preview.mp4")
        self.assertEqual(labels, ["r", "g", "b", "b"])
        self.assertTrue(self._run(clips)["cache_hit"])

    def test_frame_budget_does_not_duplicate_long_clip_boundaries(self) -> None:
        clips = [
            {
                "video_artifact_id": f"art_{index + 1:032x}",
                "start_ms": 0,
                "end_ms": 1_000,
                "source_path": source.relative_to(self.workspace).as_posix(),
                "source_bytes": source.stat().st_size,
                "source_sha256": _sha256(source),
            }
            for index, source in enumerate(self.sources[:2])
        ]
        result = self._run(clips)
        output_root = self.workspace / result["output_directory"]  # type: ignore[arg-type]
        labels = _dominant_frame_labels(output_root / "timeline-preview.mp4")
        self.assertEqual(labels, ["r"] * 24 + ["g"] * 24)

    def test_cache_tamper_is_rejected_then_regenerated(self) -> None:
        first = self._run()
        output_root = self.workspace / first["output_directory"]  # type: ignore[arg-type]
        (output_root / "timeline-preview.mp4").write_bytes(b"tampered")
        with self.assertRaisesRegex(TimelineError, "integrity"):
            validate_local_timeline_outputs(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_TEST",
                cache_key=self._key(),
                clips=self._clips(),
            )
        regenerated = self._run()
        self.assertFalse(regenerated["cache_hit"])
        self.assertTrue(self._run()["cache_hit"])

    def test_cache_with_unexpected_file_is_not_reused(self) -> None:
        first = self._run()
        output_root = self.workspace / first["output_directory"]  # type: ignore[arg-type]
        (output_root / "unexpected.partial").write_bytes(b"partial")
        self.assertFalse(self._run()["cache_hit"])

    def test_cache_key_includes_source_lineage_and_tool_identity(self) -> None:
        clips = self._clips()
        first = self._key(clips)
        self.assertNotEqual(first, control_timeline_cache_key(clips))
        changed_source = [dict(item) for item in clips]
        changed_source[0]["source_sha256"] = "A" * 64
        self.assertNotEqual(first, self._key(changed_source))
        changed_tool = timeline_cache_key(
            clips,
            ffmpeg_identity={"path": "C:/ffmpeg.exe", "version": "v1", "sha256": "B" * 64},
            ffprobe_identity={"path": "C:/ffprobe.exe", "version": "v1", "sha256": "C" * 64},
        )
        self.assertNotEqual(first, changed_tool)

    def test_cancelled_worker_does_not_publish(self) -> None:
        cancel_event = JobExecutionContext("TIMELINE_PRE_CANCEL_TEST")
        cancel_event.set()
        with self.assertRaises(JobCancelled):
            generate_local_timeline(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_PRE_CANCEL",
                cache_key=self._key(),
                clips=self._clips(),
                cancel_event=cancel_event,
            )
        self.assertFalse((self.workspace / "outputs" / "studio" / "runs").exists())

    def test_direct_worker_rejects_unsafe_cache_key(self) -> None:
        with self.assertRaises(TimelineValidationError):
            generate_local_timeline(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_TEST",
                cache_key="../../outside",
                clips=self._clips(),
            )
        self.assertFalse((self.workspace / "outputs" / "studio" / "outside").exists())

    def test_fixed_argv_uses_staged_relative_clip_names(self) -> None:
        calls: list[list[str]] = []
        real_bounded = timeline_module._bounded_process

        def capture(arguments, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(list(arguments))
            return real_bounded(arguments, **kwargs)

        with mock.patch.object(timeline_module, "_bounded_process", side_effect=capture):
            self._run()
        ffmpeg_calls = [call for call in calls if Path(call[0]).name.casefold().startswith("ffmpeg")]
        self.assertTrue(ffmpeg_calls)
        first = ffmpeg_calls[0]
        self.assertIn("clip-00.mp4", first)
        self.assertNotIn(str(self.sources[0]), first)
        self.assertTrue(all("-i" in call for call in ffmpeg_calls))

    def test_bounded_diagnostics_remain_limited(self) -> None:
        with mock.patch.object(assembly_module, "MAX_PROCESS_OUTPUT_BYTES", 32):
            with self.assertRaisesRegex(AssemblyToolError, "excessive diagnostics"):
                timeline_module._bounded_process(
                    [
                        shutil.which("python") or "python",
                        "-c",
                        "import sys; sys.stdout.write('x' * 1000000); sys.stderr.write('y' * 1000000)",
                    ],
                    cwd=self.workspace,
                    timeout=10,
                    label="timeline noisy process",
                )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()


if __name__ == "__main__":
    unittest.main()
