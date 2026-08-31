from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.studio import assembly
from tools.studio.jobs import JobCancelled
from tools.studio.remotion_timeline import (
    COMPOSITION_ID,
    PINNED_REMOTION_VERSION,
    _FIRST_PARTY_SOURCE_PATHS,
    _clean_environment,
    _cleanup_stage_root,
    _REMOTION_STAGE_CLEANUP_ATTEMPTS,
    _recheck_runtime_attestation,
    _render_environment,
    _scratch_requirement,
    _runtime_attestation_identity,
    _source_enhancement_plans,
    discard_remotion_timeline_outputs,
    generate_remotion_timeline,
    validate_remotion_timeline_outputs,
)
from tools.studio.remotion_timeline_execution import (
    RemotionTimelineError,
    RemotionTimelineValidationError,
    compile_remotion_timeline,
    remotion_timeline_cache_key,
)
from tools.studio.security import canonical_json


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RemotionTimelineWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.ffmpeg = str(Path(shutil.which("ffmpeg") or "").resolve())
        self.ffprobe = str(Path(shutil.which("ffprobe") or "").resolve())
        self.run_id = "run-remotion-test"
        self.production_id = "production-remotion-test"
        self.source = self.workspace / "registered" / "source.mp4"
        self.source.parent.mkdir(parents=True)
        subprocess.run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x114:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=1",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(self.source),
            ],
            check=True,
        )
        self.source_digest = _sha256(self.source)
        self.clips = [
            {
                "video_artifact_id": "art_0123456789abcdef0123456789abcdef",
                "start_ms": 0,
                "end_ms": 500,
                "volume_percent": 35,
                "visual_preset": "preserve_v1",
                "transition_to_next": None,
                "overlay": {
                    "text": "秘密のテロップ",
                    "start_ms": 20,
                    "end_ms": 250,
                    "position": "bottom",
                    "style_preset": "shorts_ja_large_v1",
                },
                "source_path": "registered/source.mp4",
                "source_bytes": self.source.stat().st_size,
                "source_sha256": self.source_digest,
            }
        ]
        tools = self.workspace / "mock-tools"
        tools.mkdir()
        self.entry = tools / "entry.tsx"
        self.composition = tools / "TimelineComposition.tsx"
        self.model = tools / "model.ts"
        self.api = tools / "api.ts"
        self.status = tools / "status.ts"
        self.types = tools / "types.ts"
        self.render_script = tools / "remotion_render.mjs"
        self.browser = tools / "chrome.exe"
        for path in (
            self.entry,
            self.composition,
            self.model,
            self.api,
            self.status,
            self.types,
            self.render_script,
            self.browser,
        ):
            path.write_text(path.name, encoding="utf-8")
        self.tool_identity = {
            "node": {"version": "mock-node-v1", "sha256": "1" * 64},
            "ffmpeg": {"version": "mock-ffmpeg-v1", "sha256": "2" * 64},
            "ffprobe": {"version": "mock-ffprobe-v1", "sha256": "3" * 64},
            "chromium": {"version": "mock-chromium-v1", "sha256": _sha256(self.browser)},
            "playwright": {"version": "1.62.1", "sha256": "4" * 64},
            "studio_package": {"version": "local-remotion-timeline-v1", "sha256": "5" * 64},
            "package_lock": {"version": "local-remotion-timeline-v1", "sha256": "6" * 64},
            "entry_point": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.entry),
            },
            "composition_source": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.composition),
            },
            "model_source": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.model),
            },
            "api_source": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.api),
            },
            "status_source": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.status),
            },
            "types_source": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.types),
            },
            "render_script": {
                "version": "local-remotion-timeline-v1",
                "sha256": _sha256(self.render_script),
            },
            "doctor_script": {"version": "local-remotion-timeline-v1", "sha256": "7" * 64},
            "runtime_dependency_closure": {
                "version": "sha256-node-dependency-closure-v1;packages=6;files=6;bytes=6",
                "sha256": "8" * 64,
            },
        }
        for name in (
            "remotion",
            "@remotion/player",
            "@remotion/renderer",
            "@remotion/bundler",
            "@remotion/transitions",
        ):
            self.tool_identity[f"package:{name}"] = {
                "version": PINNED_REMOTION_VERSION,
                "sha256": hashlib.sha256(name.encode("utf-8")).hexdigest().upper(),
            }
        self.runtime = {
            "browser": self.browser,
            "doctor": {},
            "source_files": {
                "entry_point": self.entry,
                "composition_source": self.composition,
                "model_source": self.model,
                "api_source": self.api,
                "status_source": self.status,
                "types_source": self.types,
                "render_script": self.render_script,
            },
        }
        self.cache_key = remotion_timeline_cache_key(
            self.clips, tool_identity=self.tool_identity
        )
        self.node_calls = 0
        self.node_scratch_directory = None
        self.node_staged_source_bytes = None

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _runtime(self, *_args, **_kwargs):
        return (
            "mock-node",
            self.ffmpeg,
            self.ffprobe,
            self.render_script,
            self.entry,
            self.runtime,
            self.tool_identity,
        )

    def _bounded(self, arguments, **kwargs):
        if arguments[0] != "mock-node":
            return self.original_bounded(arguments, **kwargs)
        self.node_calls += 1
        environment = kwargs.get("environment")
        self.assertIsInstance(environment, dict)
        self.assertEqual(environment.get("TEMP"), environment.get("TMP"))
        self.assertEqual(environment.get("TEMP"), environment.get("TMPDIR"))
        self.node_scratch_directory = Path(environment["TEMP"])
        self.assertTrue(self.node_scratch_directory.is_dir())
        request_path = Path(arguments[2])
        result_path = Path(arguments[3])
        request = json.loads(request_path.read_text(encoding="utf-8"))
        self.node_staged_source_bytes = sum(
            path.stat().st_size
            for path in Path(request["public_dir"]).glob("clip-*.mp4")
        )
        props = request["input_props"]
        duration = props["durationInFrames"] / 24
        subprocess.run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s=1080x1920:r=24:d={duration}",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=48000:cl=stereo:d={duration}",
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                request["output_path"],
            ],
            check=True,
        )
        result_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "composition_id": COMPOSITION_ID,
                    "duration_in_frames": props["durationInFrames"],
                    "clip_count": len(props["clips"]),
                    "transition_count": sum(
                        clip["transitionToNext"] is not None for clip in props["clips"]
                    ),
                    "overlay_count": sum(clip["overlay"] is not None for clip in props["clips"]),
                    "remotion_packages": {
                        name: PINNED_REMOTION_VERSION
                        for name in (
                            "remotion",
                            "@remotion/player",
                            "@remotion/renderer",
                            "@remotion/bundler",
                            "@remotion/transitions",
                        )
                    },
                    "concurrency": 1,
                    "disallow_parallel_encoding": True,
                    "silent_audio_fallback": True,
                    "image_format": "png",
                    "video_crf": 16,
                    "x264_preset": "medium",
                    "scratch_directory_attested": True,
                    "max_progress_percent": 100,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return b""

    def _patch_worker(self):
        self.original_bounded = assembly._bounded_process
        return (
            mock.patch("tools.studio.remotion_timeline._resolve_runtime", self._runtime),
            mock.patch("tools.studio.remotion_timeline._bounded_process", self._bounded),
        )

    def _generate(self):
        return generate_remotion_timeline(
            self.workspace,
            production_id=self.production_id,
            run_id=self.run_id,
            cache_key=self.cache_key,
            clips=self.clips,
        )

    def test_mocked_node_generation_publishes_exact_verified_set_and_hits_cache(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            first = self._generate()
            second = self._generate()
            validated = validate_remotion_timeline_outputs(
                self.workspace,
                production_id=self.production_id,
                run_id=self.run_id,
                cache_key=self.cache_key,
                clips=self.clips,
            )
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertTrue(validated["cache_hit"])
        self.assertTrue(first["has_audio"])
        self.assertEqual(1, self.node_calls)
        output = self.workspace / first["output_directory"]
        self.assertEqual(
            {
                "remotion-preview.mp4",
                "remotion-timeline.json",
                "render-report.json",
                "ffprobe.json",
                "manifest.json",
            },
            {path.name for path in output.iterdir()},
        )
        report_text = (output / "render-report.json").read_text(encoding="utf-8")
        timeline_text = (output / "remotion-timeline.json").read_text(encoding="utf-8")
        manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("秘密のテロップ", report_text)
        self.assertNotIn("秘密のテロップ", manifest_text)
        self.assertIn("秘密のテロップ", timeline_text)
        report = json.loads(report_text)
        timeline = json.loads(timeline_text)
        manifest = json.loads(manifest_text)
        self.assertEqual(
            {
                "raw_overlay_text_in_report": False,
                "source_paths_in_report": False,
                "recipe_contains_overlay_text": True,
            },
            report["content_policy"],
        )
        self.assertEqual(
            {"recipe_contains_overlay_text": True, "source_paths_recorded": False},
            timeline["content_policy"],
        )
        self.assertNotIn(str(self.workspace), report_text)
        self.assertNotIn(str(self.workspace), manifest_text)
        self.assertEqual("png", report["renderer"]["image_format"])
        self.assertEqual(16, report["renderer"]["video_crf"])
        scratch = report["scratch_space"]
        self.assertTrue(scratch["initial_passed"])
        self.assertTrue(scratch["post_stage_passed"])
        self.assertTrue(scratch["node_containment_attested"])
        self.assertGreaterEqual(
            scratch["initial_observed_free_bytes"],
            scratch["initial_required_free_bytes"],
        )
        self.assertGreaterEqual(
            scratch["post_stage_observed_free_bytes"],
            scratch["post_stage_required_free_bytes"],
        )
        self.assertEqual("png-frame-scratch-v1", scratch["policy_version"])
        self.assertEqual(scratch, manifest["scratch_space"])
        self.assertEqual(self.node_staged_source_bytes, scratch["actual_staged_source_bytes"])
        self.assertIsNotNone(self.node_scratch_directory)
        self.assertFalse(self.node_scratch_directory.exists())
        self.assertEqual("remotion-source-fidelity-v2", manifest["output_policy"]["policy_version"])
        self.assertEqual(
            "preserve_v1",
            report["render"]["source_enhancement_results"][0]["visual_preset"],
        )
        probe = json.loads((output / "ffprobe.json").read_text(encoding="utf-8"))
        streams = probe["remotion_preview"]["streams"]
        self.assertEqual(["video", "audio"], [stream["codec_type"] for stream in streams])
        self.assertEqual("48000", streams[1]["sample_rate"])
        self.assertEqual(2, streams[1]["channels"])

    def test_h3_sharp_preset_preprocesses_before_renderer_and_is_audited(self) -> None:
        clips = [dict(self.clips[0])]
        clips[0]["visual_preset"] = "h3_low_res_sharp_v1"
        key = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity)
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            result = generate_remotion_timeline(
                self.workspace,
                production_id=self.production_id,
                run_id=self.run_id,
                cache_key=key,
                clips=clips,
            )
        report = json.loads(
            (self.workspace / result["output_directory"] / "render-report.json").read_text(
                encoding="utf-8"
            )
        )
        source_result = report["render"]["source_enhancement_results"][0]
        self.assertEqual("h3_low_res_sharp_v1", source_result["visual_preset"])
        self.assertEqual("lanczos_cover_luma_unsharp", source_result["mode"])
        self.assertEqual(64, source_result["source_width"])
        self.assertEqual(114, source_result["source_height"])
        self.assertTrue(source_result["trimmed_to_used_frames"])
        self.assertEqual(
            self.node_staged_source_bytes,
            report["scratch_space"]["actual_staged_source_bytes"],
        )

    def test_h3_sharp_preset_rejects_extreme_portrait_before_ffmpeg(self) -> None:
        clips = [dict(self.clips[0])]
        clips[0]["visual_preset"] = "h3_low_res_sharp_v1"
        compiled = compile_remotion_timeline(clips)
        probe = {
            "streams": [
                {"codec_type": "video", "width": 64, "height": 1900}
            ]
        }
        with self.assertRaises(RemotionTimelineValidationError) as raised:
            _source_enhancement_plans(clips, [probe], compiled)
        self.assertEqual("visual_preset_incompatible", raised.exception.error_code)

    def test_png_scratch_requirement_is_bounded_and_low_space_fails_before_node(self) -> None:
        audit = {
            "duration_in_frames": 360,
            "clips": [{"source_bytes": 10 * 1024 * 1024}],
        }
        requirement = _scratch_requirement(audit)
        expected_png = (360 * 1080 * 1920 * 4 * 5 + 3) // 4
        self.assertEqual(expected_png, requirement["png_frame_upper_bound_bytes"])
        self.assertEqual(
            expected_png + 10 * 1024 * 1024 + 5 * 1024 * 1024 * 1024,
            requirement["initial_required_free_bytes"],
        )
        self.assertEqual(
            expected_png + 5 * 1024 * 1024 * 1024,
            requirement["post_stage_required_free_bytes"],
        )
        maximum = _scratch_requirement(
            {
                "duration_in_frames": 1440,
                "clips": [
                    {
                        "source_bytes": 1,
                        "visual_preset": "h3_low_res_sharp_v1",
                    },
                    {
                        "source_bytes": 1,
                        "visual_preset": "h3_low_res_sharp_v1",
                    },
                ],
            }
        )
        self.assertEqual(14_929_920_000, maximum["png_frame_upper_bound_bytes"])
        self.assertEqual(4 * 1024 * 1024 * 1024, maximum["source_staging_estimate_bytes"])
        self.assertEqual(20_298_629_120, maximum["post_stage_required_free_bytes"])

        actual_requirement = _scratch_requirement(
            {
                "duration_in_frames": 12,
                "clips": [{"source_bytes": self.source.stat().st_size}],
            }
        )
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch, mock.patch(
            "tools.studio.remotion_timeline.shutil.disk_usage",
            return_value=mock.Mock(
                free=actual_requirement["initial_required_free_bytes"] - 1
            ),
        ):
            with self.assertRaises(RemotionTimelineError) as raised:
                self._generate()
        self.assertEqual("insufficient_scratch_space", raised.exception.error_code)
        self.assertEqual(0, self.node_calls)
        stage_parent = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / self.run_id
            / "remotion_timeline"
        )
        self.assertFalse(any(path.name.startswith(".remotion-") for path in stage_parent.iterdir()))

    def test_cache_hit_does_not_require_new_scratch_preflight(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            first = self._generate()
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch, mock.patch(
            "tools.studio.remotion_timeline.shutil.disk_usage",
            side_effect=AssertionError("cache validation must not inspect scratch capacity"),
        ):
            second = self._generate()
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])

    def test_post_staging_low_space_fails_before_node_and_cleans_stage(self) -> None:
        requirement = _scratch_requirement(
            {
                "duration_in_frames": 12,
                "clips": [
                    {
                        "source_bytes": self.source.stat().st_size,
                        "visual_preset": "preserve_v1",
                    }
                ],
            }
        )
        disk_results = [
            mock.Mock(free=requirement["initial_required_free_bytes"]),
            mock.Mock(free=requirement["post_stage_required_free_bytes"] - 1),
        ]
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch, mock.patch(
            "tools.studio.remotion_timeline.shutil.disk_usage",
            side_effect=disk_results,
        ):
            with self.assertRaises(RemotionTimelineError) as raised:
                self._generate()
        self.assertEqual("insufficient_scratch_space", raised.exception.error_code)
        self.assertEqual(0, self.node_calls)
        stage_parent = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / self.run_id
            / "remotion_timeline"
        )
        self.assertFalse(any(path.name.startswith(".remotion-") for path in stage_parent.iterdir()))

    def test_render_failure_cleans_the_contained_scratch_tree(self) -> None:
        self.original_bounded = assembly._bounded_process
        observed_scratch = None

        def fail_node(arguments, **kwargs):
            nonlocal observed_scratch
            if arguments[0] == "mock-node":
                observed_scratch = Path(kwargs["environment"]["TEMP"])
                self.assertTrue(observed_scratch.is_dir())
                raise assembly.AssemblyError("synthetic render failure")
            return self.original_bounded(arguments, **kwargs)

        with mock.patch(
            "tools.studio.remotion_timeline._resolve_runtime", self._runtime
        ), mock.patch("tools.studio.remotion_timeline._bounded_process", fail_node):
            with self.assertRaises(RemotionTimelineError) as raised:
                self._generate()
        self.assertEqual("local_remotion_render_failed", raised.exception.error_code)
        self.assertIsNotNone(observed_scratch)
        self.assertFalse(observed_scratch.exists())

    def test_stage_cleanup_retries_transient_windows_lock_and_removes_work_tree(self) -> None:
        stage = self.workspace / ".remotion-retry"
        work = stage / "work"
        (work / "public").mkdir(parents=True)
        (work / "public" / "clip-00.mp4").write_bytes(b"source")
        (work / "scratch").mkdir()
        (work / "scratch" / "frame-000001.png").write_bytes(b"png")
        (work / "render-request.json").write_text("{}", encoding="utf-8")
        (work / "remotion-raw.mp4").write_bytes(b"raw")
        real_rmtree = shutil.rmtree
        attempts: list[Path] = []

        def flaky_rmtree(path, *args, **kwargs):
            attempts.append(Path(path))
            if len(attempts) < 3:
                raise PermissionError("synthetic Windows sharing violation")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch(
            "tools.studio.remotion_timeline.shutil.rmtree", side_effect=flaky_rmtree
        ), mock.patch("tools.studio.remotion_timeline.time.sleep") as sleep:
            _cleanup_stage_root(stage)

        self.assertFalse(os.path.lexists(stage))
        self.assertEqual([stage, stage, stage], attempts)
        self.assertEqual([mock.call(0.15), mock.call(0.3)], sleep.call_args_list)

    def test_stage_cleanup_fails_closed_when_residual_cannot_be_removed(self) -> None:
        stage = self.workspace / ".remotion-residual"
        (stage / "work" / "scratch").mkdir(parents=True)
        (stage / "work" / "scratch" / "frame-000001.png").write_bytes(b"png")

        with mock.patch(
            "tools.studio.remotion_timeline.shutil.rmtree",
            side_effect=PermissionError("synthetic Windows sharing violation"),
        ) as remove, mock.patch("tools.studio.remotion_timeline.time.sleep") as sleep:
            with self.assertRaises(RemotionTimelineError) as raised:
                _cleanup_stage_root(stage)

        self.assertEqual("remotion_stage_cleanup_failed", raised.exception.error_code)
        self.assertTrue(os.path.lexists(stage))
        self.assertEqual(_REMOTION_STAGE_CLEANUP_ATTEMPTS, remove.call_count)
        self.assertEqual(_REMOTION_STAGE_CLEANUP_ATTEMPTS - 1, sleep.call_count)

    def test_stage_cleanup_covers_directory_setup_failure(self) -> None:
        real_mkdir = Path.mkdir

        def fail_public_directory(path, *args, **kwargs):
            candidate = Path(path)
            if candidate.name == "public" and candidate.parent.name == "work":
                raise PermissionError("synthetic staging setup failure")
            return real_mkdir(candidate, *args, **kwargs)

        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch, mock.patch(
            "pathlib.Path.mkdir", new=fail_public_directory
        ):
            with self.assertRaises(RemotionTimelineError) as raised:
                self._generate()

        self.assertEqual("publish_failed", raised.exception.error_code)
        stage_parent = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / self.run_id
            / "remotion_timeline"
        )
        self.assertFalse(any(path.name.startswith(".remotion-") for path in stage_parent.iterdir()))

    def test_publish_retains_complete_cache_when_stage_cleanup_reports_failure(self) -> None:
        first_patch, second_patch = self._patch_worker()
        cleanup_error = RemotionTimelineError(
            "synthetic stage cleanup failure", code="remotion_stage_cleanup_failed"
        )
        with first_patch, second_patch, mock.patch(
            "tools.studio.remotion_timeline._cleanup_stage_root",
            side_effect=cleanup_error,
        ):
            with self.assertRaises(RemotionTimelineError) as raised:
                self._generate()

        self.assertEqual("remotion_stage_cleanup_failed", raised.exception.error_code)
        output = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / self.run_id
            / "remotion_timeline"
            / self.cache_key
        )
        self.assertTrue(output.is_dir())
        stage_parent = output.parent
        self.assertTrue(any(path.name.startswith(".remotion-") for path in stage_parent.iterdir()))

        # The complete atomic cache is deliberately retained for a later
        # integrity-validated cache hit; the surfaced cleanup error prevents
        # this invocation from claiming success while the transient stage is
        # still present.
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            retry = self._generate()
        self.assertTrue(retry["cache_hit"])
        self.assertEqual(1, self.node_calls)

    def test_render_environment_is_exactly_contained_and_scrubs_aliases(self) -> None:
        work = self.workspace / "render-environment"
        scratch = work / "scratch"
        scratch.mkdir(parents=True)
        values = {
            "PATH": os.environ.get("PATH", ""),
            "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
            "Temp": "C:\\unsafe-temp",
            "tmp": "C:\\unsafe-tmp",
            "TMPDIR": "C:\\unsafe-tmpdir",
        }
        with mock.patch.dict(os.environ, values, clear=True):
            environment = _render_environment(scratch, work)
        temp_entries = {
            key: value
            for key, value in environment.items()
            if key.casefold() in {"temp", "tmp", "tmpdir"}
        }
        self.assertEqual(
            {"TEMP": str(scratch), "TMP": str(scratch), "TMPDIR": str(scratch)},
            temp_entries,
        )

        outside = self.workspace / "outside-scratch"
        outside.mkdir()
        with self.assertRaises(RemotionTimelineError):
            _render_environment(outside, work)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_node_renderer_rejects_uncontained_or_unattested_scratch_before_bundle(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        node = str(Path(shutil.which("node") or "").resolve())
        render_script = repository / "tools" / "studio" / "remotion_render.mjs"
        browser_lookup = subprocess.run(
            [
                node,
                "-e",
                "process.stdout.write(require('./studio/node_modules/playwright').chromium.executablePath())",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if browser_lookup.returncode != 0:
            self.skipTest("Pinned Playwright Chromium is unavailable")
        browser = Path(browser_lookup.stdout).resolve()
        if not browser.is_file():
            self.skipTest("Pinned Playwright Chromium is unavailable")

        base_environment = {
            key: value
            for key, value in os.environ.items()
            if key.casefold() not in {"temp", "tmp", "tmpdir"}
        }
        cases = (
            ("missing", "scratch environment is invalid"),
            ("mismatch", "scratch environment is invalid"),
            ("external", "request paths do not match"),
            ("nonempty", "scratch directory is invalid"),
            ("symlink", "scratch directory is invalid"),
        )
        executed = 0
        for label, expected_error in cases:
            with self.subTest(label=label):
                work = self.workspace / f"node-scratch-{label}"
                public = work / "public"
                scratch = work / "scratch"
                outside = self.workspace / f"node-scratch-{label}-outside"
                public.mkdir(parents=True)
                scratch.mkdir()
                outside.mkdir()
                (public / "clip-00.mp4").write_bytes(b"registered-source")
                if label == "nonempty":
                    (scratch / "unexpected.tmp").write_bytes(b"x")
                if label == "symlink":
                    scratch.rmdir()
                    try:
                        scratch.symlink_to(outside, target_is_directory=True)
                    except OSError:
                        continue
                request = {
                    "schema_version": 1,
                    "composition_id": COMPOSITION_ID,
                    "entry_point": str(repository / "studio" / "src" / "remotion" / "entry.tsx"),
                    "public_dir": str(public),
                    "browser_executable": str(browser),
                    "output_path": str(work / "remotion-raw.mp4"),
                    "scratch_directory": str(outside if label == "external" else scratch),
                    "input_props": {
                        "schemaVersion": 1,
                        "width": 1080,
                        "height": 1920,
                        "fps": 24,
                        "durationInFrames": 2,
                        "clips": [
                            {
                                "src": "clip-00.mp4",
                                "startMs": 0,
                                "endMs": 100,
                                "trimBeforeFrame": 0,
                                "trimAfterFrame": 2,
                                "durationInFrames": 2,
                                "volumePercent": 0,
                                "transitionToNext": None,
                                "overlay": None,
                            }
                        ],
                    },
                }
                request_path = work / "render-request.json"
                result_path = work / "render-result.json"
                request_path.write_text(json.dumps(request), encoding="utf-8")
                environment = {
                    **base_environment,
                    "TEMP": str(scratch),
                    "TMP": str(scratch),
                    "TMPDIR": str(scratch),
                }
                if label == "missing":
                    environment.pop("TMPDIR")
                elif label == "mismatch":
                    environment["TMPDIR"] = str(outside)
                completed = subprocess.run(
                    [node, str(render_script), str(request_path), str(result_path)],
                    cwd=work,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                executed += 1
                self.assertNotEqual(0, completed.returncode)
                self.assertIn(expected_error, completed.stderr)
                self.assertFalse((work / "bundle").exists())
                self.assertFalse(result_path.exists())
        self.assertGreaterEqual(executed, 4)

    def test_tampered_report_is_discarded_and_regenerated(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            first = self._generate()
            output = self.workspace / first["output_directory"]
            (output / "render-report.json").write_text("{}\n", encoding="utf-8")
            second = self._generate()
        self.assertFalse(second["cache_hit"])
        self.assertEqual(2, self.node_calls)

    def test_transitive_api_change_during_render_fails_closed(self) -> None:
        self.original_bounded = assembly._bounded_process

        def changing_bounded(arguments, **kwargs):
            result = self._bounded(arguments, **kwargs)
            if arguments[0] == "mock-node":
                self.api.write_text("changed api source", encoding="utf-8")
            return result

        with (
            mock.patch("tools.studio.remotion_timeline._resolve_runtime", self._runtime),
            mock.patch(
                "tools.studio.remotion_timeline._bounded_process",
                changing_bounded,
            ),
            self.assertRaises(RemotionTimelineError) as raised,
        ):
            self._generate()
        self.assertEqual("tool_changed", raised.exception.error_code)
        self.assertFalse(
            (
                self.workspace
                / "outputs"
                / "studio"
                / "runs"
                / self.run_id
                / "remotion_timeline"
                / self.cache_key
            ).exists()
        )

    def test_first_party_build_closure_changes_cache_identity(self) -> None:
        self.assertEqual(
            {
                "entry_point",
                "composition_source",
                "model_source",
                "api_source",
                "status_source",
                "types_source",
            },
            set(_FIRST_PARTY_SOURCE_PATHS),
        )
        for name in ("api_source", "status_source", "types_source"):
            with self.subTest(name=name):
                changed_identity = {
                    key: dict(value) for key, value in self.tool_identity.items()
                }
                changed_identity[name]["sha256"] = "F" * 64
                self.assertNotEqual(
                    self.cache_key,
                    remotion_timeline_cache_key(
                        self.clips,
                        tool_identity=changed_identity,
                    ),
                )

    def test_forged_report_with_updated_hashes_is_rejected(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            result = self._generate()
            output = self.workspace / result["output_directory"]
            report_path = output / "render-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["source_path"] = str(self.source)
            report["text"] = "秘密のテロップ"
            report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["render-report.json"]["bytes"] = report_path.stat().st_size
            manifest["files"]["render-report.json"]["sha256"] = _sha256(report_path)
            manifest.pop("manifest_sha256")
            manifest["manifest_sha256"] = hashlib.sha256(
                canonical_json(manifest).encode("utf-8")
            ).hexdigest().upper()
            manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
            with self.assertRaises(RemotionTimelineError) as raised:
                validate_remotion_timeline_outputs(
                    self.workspace,
                    production_id=self.production_id,
                    run_id=self.run_id,
                    cache_key=self.cache_key,
                    clips=self.clips,
                )
        self.assertEqual("cache_integrity_failed", raised.exception.error_code)

    def test_source_bytes_and_hash_are_revalidated(self) -> None:
        clips = [dict(self.clips[0])]
        clips[0]["source_bytes"] += 1
        key = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity)
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            with self.assertRaises(RemotionTimelineValidationError) as raised:
                generate_remotion_timeline(
                    self.workspace,
                    production_id=self.production_id,
                    run_id=self.run_id,
                    cache_key=key,
                    clips=clips,
                )
        self.assertEqual("source_changed", raised.exception.error_code)
        self.assertEqual(0, self.node_calls)

    def test_source_symlink_is_rejected_when_supported(self) -> None:
        alias = self.source.with_name("alias.mp4")
        try:
            alias.symlink_to(self.source)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        clips = [dict(self.clips[0])]
        clips[0]["source_path"] = "registered/alias.mp4"
        key = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity)
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            with self.assertRaises(RemotionTimelineValidationError) as raised:
                generate_remotion_timeline(
                    self.workspace,
                    production_id=self.production_id,
                    run_id=self.run_id,
                    cache_key=key,
                    clips=clips,
                )
        self.assertEqual("source_not_available", raised.exception.error_code)
        self.assertEqual(0, self.node_calls)

    def test_node_environment_is_allowlisted_and_strips_renderer_injection(self) -> None:
        values = {
            "PATH": os.environ.get("PATH", ""),
            "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
            "OPENAI_API_KEY": "secret",
            "NODE_OPTIONS": "--require attacker.js",
            "REMOTION_CHROME_FLAGS": "--unsafe",
            "HTTPS_PROXY": "http://proxy.invalid",
        }
        with mock.patch.dict(os.environ, values, clear=True):
            cleaned = _clean_environment()
        names = {name.casefold() for name in cleaned}
        self.assertIn("path", names)
        self.assertIn("systemroot", names)
        self.assertNotIn("openai_api_key", names)
        self.assertNotIn("node_options", names)
        self.assertNotIn("remotion_chrome_flags", names)
        self.assertNotIn("https_proxy", names)

    def test_pre_cancel_leaves_no_published_directory(self) -> None:
        class Cancelled:
            @staticmethod
            def is_set() -> bool:
                return True

            @staticmethod
            def raise_if_cancelled() -> None:
                raise JobCancelled()

        cancel = Cancelled()
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            with self.assertRaises(JobCancelled):
                generate_remotion_timeline(
                    self.workspace,
                    production_id=self.production_id,
                    run_id=self.run_id,
                    cache_key=self.cache_key,
                    clips=self.clips,
                    cancel_event=cancel,
                )
        output = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / self.run_id
            / "remotion_timeline"
            / self.cache_key
        )
        self.assertFalse(output.exists())

    def test_discard_is_exact_idempotent_and_rejects_invalid_key(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            result = self._generate()
        output = self.workspace / result["output_directory"]
        sibling = output.parent / ("F" * 64)
        sibling.mkdir()
        self.assertFalse(
            discard_remotion_timeline_outputs(
                self.workspace, run_id=self.run_id, cache_key="../unsafe"
            )
        )
        self.assertTrue(
            discard_remotion_timeline_outputs(
                self.workspace, run_id=self.run_id, cache_key=self.cache_key
            )
        )
        self.assertFalse(output.exists())
        self.assertTrue(sibling.exists())
        self.assertFalse(
            discard_remotion_timeline_outputs(
                self.workspace, run_id=self.run_id, cache_key=self.cache_key
            )
        )


@unittest.skipUnless(shutil.which("node"), "Node.js is required")
class RemotionRuntimeAttestationTests(unittest.TestCase):
    ROOT_PACKAGES = (
        "remotion",
        "@remotion/player",
        "@remotion/renderer",
        "@remotion/bundler",
        "@remotion/transitions",
        "playwright",
    )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.studio = self.root / "studio"
        self.modules = self.studio / "node_modules"
        self.modules.mkdir(parents=True)
        self.doctor = (
            Path(__file__).resolve().parents[1] / "tools" / "studio" / "remotion_doctor.mjs"
        )
        self.helper = self.root / "attestation-helper.mjs"
        self.helper.write_text(
            "\n".join(
                (
                    f"import {{writeRuntimeAttestation, verifyRuntimeAttestation}} from {json.dumps(self.doctor.as_uri())};",
                    "const studioRoot = process.argv[2];",
                    "const action = process.argv[3];",
                    "try {",
                    "  const value = action === 'write'",
                    "    ? await writeRuntimeAttestation({studioRoot})",
                    "    : await verifyRuntimeAttestation({studioRoot});",
                    "  process.stdout.write(`${JSON.stringify(value)}\\n`);",
                    "} catch (error) {",
                    "  process.stderr.write(`${error.message}\\n`);",
                    "  process.exitCode = 1;",
                    "}",
                )
            ),
            encoding="utf-8",
        )
        for name in self.ROOT_PACKAGES:
            dependencies = {"dep-a": "1.0.0"} if name == "@remotion/bundler" else None
            self._package(name, dependencies=dependencies)
        self._package(
            "dep-a",
            dependencies={"dep-b": "1.0.0"},
            optional_dependencies={"optional-a": "1.0.0"},
            peer_dependencies={"peer-a": "1.0.0"},
        )
        self._package("dep-b")
        self._package("optional-a")
        self._package("peer-a")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _package(
        self,
        name: str,
        *,
        dependencies: dict[str, str] | None = None,
        optional_dependencies: dict[str, str] | None = None,
        peer_dependencies: dict[str, str] | None = None,
    ) -> Path:
        directory = self.modules.joinpath(*name.split("/"))
        directory.mkdir(parents=True, exist_ok=True)
        package = {"name": name, "version": "1.0.0"}
        if dependencies:
            package["dependencies"] = dependencies
        if optional_dependencies:
            package["optionalDependencies"] = optional_dependencies
        if peer_dependencies:
            package["peerDependencies"] = peer_dependencies
        (directory / "package.json").write_text(json.dumps(package), encoding="utf-8")
        (directory / "index.js").write_text(f"export const packageName = {name!r};\n", encoding="utf-8")
        return directory

    def _run(self, action: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [shutil.which("node") or "node", str(self.helper), str(self.studio), action],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_transitive_runtime_tree_is_attested_and_mutation_fails_closed(self) -> None:
        written = self._run("write")
        self.assertEqual(0, written.returncode, written.stderr)
        attestation = json.loads(written.stdout)
        self.assertEqual(10, attestation["closure_package_count"])
        self.assertGreaterEqual(attestation["file_count"], 20)
        verified = self._run("verify")
        self.assertEqual(0, verified.returncode, verified.stderr)
        self.assertEqual(attestation, json.loads(verified.stdout))
        rewritten = self._run("write")
        self.assertEqual(0, rewritten.returncode, rewritten.stderr)
        self.assertEqual(attestation, json.loads(rewritten.stdout))
        self.assertFalse(any(".partial" in path.name for path in self.modules.iterdir()))
        self.assertFalse(any(".backup" in path.name for path in self.modules.iterdir()))

        (self.modules / "dep-b" / "index.js").write_text("export const changed = true;\n", encoding="utf-8")
        rejected = self._run("verify")
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("does not match installed files", rejected.stderr)
        self.assertNotIn(str(self.root), rejected.stderr)

    def test_symlinked_runtime_file_is_rejected_when_supported(self) -> None:
        target = self.modules / "dep-b" / "index.js"
        alias = target.with_name("alias.js")
        try:
            alias.symlink_to(target)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        rejected = self._run("write")
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("symbolic link", rejected.stderr)
        self.assertNotIn(str(self.root), rejected.stderr)

    def test_attestation_identity_is_cache_safe_and_path_free(self) -> None:
        raw = {
            "schema_version": 1,
            "algorithm": "sha256-node-dependency-closure-v1",
            "root_packages": sorted(self.ROOT_PACKAGES),
            "closure_package_count": 10,
            "file_count": 20,
            "total_bytes": 1234,
            "tree_sha256": "A" * 64,
        }
        identity = _runtime_attestation_identity({"runtime_attestation": raw})
        self.assertEqual("A" * 64, identity["sha256"])
        self.assertIn("packages=10;files=20;bytes=1234", identity["version"])
        self.assertNotIn(str(self.root), json.dumps(identity))

    def test_post_render_attestation_mismatch_fails_closed(self) -> None:
        attestation = {
            "schema_version": 1,
            "algorithm": "sha256-node-dependency-closure-v1",
            "root_packages": sorted(self.ROOT_PACKAGES),
            "closure_package_count": 10,
            "file_count": 20,
            "total_bytes": 1234,
            "tree_sha256": "B" * 64,
        }
        output = json.dumps(
            {"schema_version": 1, "runtime_attestation": attestation}
        ).encode("utf-8")
        with mock.patch(
            "tools.studio.remotion_timeline._bounded_process", return_value=output
        ):
            with self.assertRaises(RemotionTimelineError) as raised:
                _recheck_runtime_attestation(
                    self.root,
                    node_executable="node",
                    doctor_script=self.doctor,
                    expected_identity={
                        "version": "sha256-node-dependency-closure-v1;packages=10;files=20;bytes=1234",
                        "sha256": "A" * 64,
                    },
                    cancel_event=None,
                )
        self.assertEqual("tool_changed", raised.exception.error_code)


if __name__ == "__main__":
    unittest.main()
