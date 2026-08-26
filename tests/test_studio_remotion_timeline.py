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
    _clean_environment,
    _recheck_runtime_attestation,
    _runtime_attestation_identity,
    discard_remotion_timeline_outputs,
    generate_remotion_timeline,
    validate_remotion_timeline_outputs,
)
from tools.studio.remotion_timeline_execution import (
    RemotionTimelineError,
    RemotionTimelineValidationError,
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
                "color=c=blue:s=64x64:r=24:d=1",
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
        self.render_script = tools / "remotion_render.mjs"
        self.browser = tools / "chrome.exe"
        for path in (
            self.entry,
            self.composition,
            self.model,
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
                "render_script": self.render_script,
            },
        }
        self.cache_key = remotion_timeline_cache_key(
            self.clips, tool_identity=self.tool_identity
        )
        self.node_calls = 0

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
        request_path = Path(arguments[2])
        result_path = Path(arguments[3])
        request = json.loads(request_path.read_text(encoding="utf-8"))
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
        probe = json.loads((output / "ffprobe.json").read_text(encoding="utf-8"))
        streams = probe["remotion_preview"]["streams"]
        self.assertEqual(["video", "audio"], [stream["codec_type"] for stream in streams])
        self.assertEqual("48000", streams[1]["sample_rate"])
        self.assertEqual(2, streams[1]["channels"])

    def test_tampered_report_is_discarded_and_regenerated(self) -> None:
        first_patch, second_patch = self._patch_worker()
        with first_patch, second_patch:
            first = self._generate()
            output = self.workspace / first["output_directory"]
            (output / "render-report.json").write_text("{}\n", encoding="utf-8")
            second = self._generate()
        self.assertFalse(second["cache_hit"])
        self.assertEqual(2, self.node_calls)

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
