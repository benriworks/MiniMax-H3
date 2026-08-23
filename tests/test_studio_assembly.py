from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from tools.studio import assembly as assembly_module
from tools.studio.assembly import (
    AssemblyError,
    AssemblyToolError,
    AssemblyValidationError,
    _build_ass,
    _validate_output_probe,
    assembly_cache_key,
    generate_local_assembly,
    validate_local_assembly_outputs,
)
from tools.studio.jobs import JobCancelled, JobExecutionContext


def _gray_frame(path: Path, *, at_seconds: float) -> bytes:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _wav_bytes(duration_ms: int, *, sample_rate: int = 8_000) -> bytes:
    frames = (duration_ms * sample_rate) // 1_000
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack("<h", 0) * frames)
    return output.getvalue()


class LocalAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise unittest.SkipTest("ffmpeg and ffprobe are required for assembly integration tests")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.source = self.workspace / "registered" / "clip.mp4"
        self.narration = self.workspace / "registered" / "narration.wav"
        self.captions = self.workspace / "registered" / "captions.srt"
        self.source.parent.mkdir(parents=True)
        self.narration.write_bytes(_wav_bytes(700))
        self.captions.write_text(
            "1\n00:00:00,000 --> 00:00:00,700\nLocal assembly\n",
            encoding="utf-8",
            newline="\n",
        )
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
                "testsrc=size=160x96:rate=24",
                "-t",
                "1.000",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(self.source),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _key(self, *, include_captioned: bool = True) -> str:
        return assembly_cache_key(
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
            hashlib.sha256(self.narration.read_bytes()).hexdigest(),
            hashlib.sha256(self.captions.read_bytes()).hexdigest(),
            include_captioned,
        )

    def _run(self, *, include_captioned: bool = True) -> dict[str, object]:
        return generate_local_assembly(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            cache_key=self._key(include_captioned=include_captioned),
            source_video=self.source,
            narration_wav=self.narration,
            captions_srt=self.captions,
            include_captioned=include_captioned,
        )

    def test_generates_verified_clean_captioned_outputs_and_cache_hit(self) -> None:
        first = self._run()
        self.assertFalse(first["cache_hit"])
        self.assertEqual(first["provider"], "local_ffmpeg")
        self.assertEqual(first["timing_source"], "ffprobe")
        self.assertEqual(first["actual_cost"], 0)
        self.assertTrue(first["include_captioned"])
        self.assertEqual(first["duration_ms"], 1_000)
        names = {item["name"] for item in first["artifacts"]}  # type: ignore[index]
        self.assertEqual(
            names,
            {"master-clean.mp4", "master-captioned.mp4", "ffprobe.json", "manifest.json"},
        )
        manifest_path = self.workspace / next(
            item["path"] for item in first["artifacts"] if item["name"] == "manifest.json"  # type: ignore[index]
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = manifest.pop("manifest_sha256")
        self.assertEqual(
            hashlib.sha256(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest().upper(),
            digest,
        )
        self.assertEqual(manifest["audio_policy"]["source_audio"], "replaced")
        self.assertIn("apad", manifest["audio_policy"]["action"])
        self.assertEqual(manifest["output_policy"]["master_captioned"], "required")
        self.assertEqual(first["source_video_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest().upper())
        clean_path = self.workspace / next(
            item["path"] for item in first["artifacts"] if item["name"] == "master-clean.mp4"  # type: ignore[index]
        )
        captioned_path = self.workspace / next(
            item["path"] for item in first["artifacts"] if item["name"] == "master-captioned.mp4"  # type: ignore[index]
        )
        clean_frame = _gray_frame(clean_path, at_seconds=0.35)
        captioned_frame = _gray_frame(captioned_path, at_seconds=0.35)
        self.assertEqual(len(clean_frame), 160 * 96)
        self.assertEqual(len(captioned_frame), len(clean_frame))
        self.assertGreater(
            sum(abs(clean - captioned) >= 40 for clean, captioned in zip(clean_frame, captioned_frame)),
            20,
            "captioned master must contain a visible burn-in, not only a second encode",
        )
        second = self._run()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["cache_key"], first["cache_key"])
        validated = validate_local_assembly_outputs(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            cache_key=self._key(),
            source_video=self.source,
            narration_wav=self.narration,
            captions_srt=self.captions,
            include_captioned=True,
        )
        self.assertTrue(validated["cache_hit"])
        self.assertIn("manifest", validated)
        self.assertEqual(len(validated["artifacts"]), 4)

    def test_include_captioned_false_omits_captioned_output(self) -> None:
        result = self._run(include_captioned=False)
        self.assertFalse(result["include_captioned"])
        self.assertEqual(
            {item["name"] for item in result["artifacts"]},  # type: ignore[index]
            {"master-clean.mp4", "ffprobe.json", "manifest.json"},
        )
        self.assertFalse((self.workspace / result["output_directory"] / "master-captioned.mp4").exists())  # type: ignore[operator]

    def test_cache_tamper_is_regenerated_and_provenance_is_strict(self) -> None:
        first = self._run()
        clean = self.workspace / next(
            item["path"] for item in first["artifacts"] if item["name"] == "master-clean.mp4"  # type: ignore[index]
        )
        clean.write_bytes(b"tampered")
        with self.assertRaisesRegex(AssemblyError, "integrity verification"):
            validate_local_assembly_outputs(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_TEST",
                cache_key=self._key(),
                source_video=self.source,
                narration_wav=self.narration,
                captions_srt=self.captions,
                include_captioned=True,
            )
        second = self._run()
        self.assertFalse(second["cache_hit"])
        wrong_key = "A" * 64
        with self.assertRaisesRegex(AssemblyValidationError, "cache_key does not match"):
            generate_local_assembly(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_WRONG_KEY",
                cache_key=wrong_key,
                source_video=self.source,
                narration_wav=self.narration,
                captions_srt=self.captions,
                include_captioned=True,
            )

    def test_long_narration_is_rejected_before_publish(self) -> None:
        self.narration.write_bytes(_wav_bytes(1_500))
        key = self._key()
        with self.assertRaisesRegex(AssemblyValidationError, "longer than the source"):
            generate_local_assembly(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_LONG",
                cache_key=key,
                source_video=self.source,
                narration_wav=self.narration,
                captions_srt=self.captions,
                include_captioned=True,
            )
        self.assertFalse((self.workspace / "outputs" / "studio" / "runs" / "RUN_LONG" / "assembly").exists())

    def test_caption_timing_beyond_tolerance_is_rejected(self) -> None:
        self.captions.write_text(
            "1\n00:00:00,000 --> 00:00:01,251\nToo late\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(AssemblyValidationError, "beyond the source"):
            self._run()

    def test_output_stream_contract_rejects_extra_streams(self) -> None:
        probe = {
            "format": {"format_name": "mp4"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                    "width": 160,
                    "height": 96,
                    "duration": "1.0",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "duration": "1.0",
                },
                {"codec_type": "data", "codec_name": "bin_data", "duration": "1.0"},
            ],
        }
        with self.assertRaisesRegex(AssemblyError, "stream layout"):
            _validate_output_probe(probe, target_duration_ms=1_000, expected_width=160, expected_height=96)

    def test_output_stream_contract_rejects_a_single_short_stream(self) -> None:
        for short_stream in ("video", "audio"):
            with self.subTest(short_stream=short_stream):
                durations = {"video": "1.0", "audio": "1.0"}
                durations[short_stream] = "0.500"
                probe = {
                    "format": {"format_name": "mp4", "duration": "1.0"},
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "pix_fmt": "yuv420p",
                            "width": 160,
                            "height": 96,
                            "duration": durations["video"],
                        },
                        {
                            "codec_type": "audio",
                            "codec_name": "aac",
                            "sample_rate": "48000",
                            "channels": 2,
                            "duration": durations["audio"],
                        },
                    ],
                }
                with self.assertRaisesRegex(AssemblyError, "duration does not match"):
                    _validate_output_probe(
                        probe,
                        target_duration_ms=1_000,
                        expected_width=160,
                        expected_height=96,
                    )

    def test_generation_passes_only_fixed_relative_media_names_to_ffmpeg(self) -> None:
        with mock.patch.object(
            assembly_module, "_bounded_process", wraps=assembly_module._bounded_process
        ) as bounded:
            self._run()
        ffmpeg_calls = [
            call.args[0]
            for call in bounded.call_args_list
            if call.args
            and Path(str(call.args[0][0])).name.casefold().startswith("ffmpeg")
        ]
        self.assertEqual(len(ffmpeg_calls), 2)
        self.assertTrue(all("source-video.mp4" not in args for args in ffmpeg_calls[1:]))
        self.assertIn("source-video.mp4", ffmpeg_calls[0])
        self.assertNotIn(str(self.source), ffmpeg_calls[0])
        for args in ffmpeg_calls:
            self.assertIn("-fs", args)
            self.assertEqual(args[args.index("-fs") + 1], str(assembly_module.MAX_OUTPUT_BYTES))

    def test_caption_filter_works_when_workspace_contains_apostrophe(self) -> None:
        quoted_workspace = self.workspace / "workspace'with-apostrophe"
        quoted_registered = quoted_workspace / "registered"
        quoted_registered.mkdir(parents=True)
        quoted_source = quoted_registered / "clip.mp4"
        quoted_narration = quoted_registered / "narration.wav"
        quoted_captions = quoted_registered / "captions.srt"
        shutil.copyfile(self.source, quoted_source)
        shutil.copyfile(self.narration, quoted_narration)
        shutil.copyfile(self.captions, quoted_captions)
        key = assembly_cache_key(
            hashlib.sha256(quoted_source.read_bytes()).hexdigest(),
            hashlib.sha256(quoted_narration.read_bytes()).hexdigest(),
            hashlib.sha256(quoted_captions.read_bytes()).hexdigest(),
            True,
        )

        result = generate_local_assembly(
            quoted_workspace,
            production_id="PROD_QUOTED",
            run_id="RUN_QUOTED",
            cache_key=key,
            source_video=quoted_source,
            narration_wav=quoted_narration,
            captions_srt=quoted_captions,
            include_captioned=True,
        )
        self.assertFalse(result["cache_hit"])
        self.assertTrue(
            (quoted_workspace / result["output_directory"] / "master-captioned.mp4").is_file()  # type: ignore[operator]
        )

    def test_bounded_process_does_not_return_unbounded_diagnostics(self) -> None:
        with mock.patch.object(assembly_module, "MAX_PROCESS_OUTPUT_BYTES", 32):
            with self.assertRaisesRegex(AssemblyToolError, "excessive diagnostics"):
                assembly_module._bounded_process(
                    [sys.executable, "-c", "print('x' * 1000)"],
                    cwd=self.workspace,
                    timeout=10,
                    label="test process",
                )

    def test_bounded_process_drains_both_noisy_pipes_without_deadlock(self) -> None:
        with mock.patch.object(assembly_module, "MAX_PROCESS_OUTPUT_BYTES", 32):
            with self.assertRaisesRegex(AssemblyToolError, "excessive diagnostics"):
                assembly_module._bounded_process(
                    [
                        sys.executable,
                        "-c",
                        "import sys; sys.stdout.write('x' * 1000000); sys.stderr.write('y' * 1000000)",
                    ],
                    cwd=self.workspace,
                    timeout=10,
                    label="noisy process",
                )

    def test_bounded_process_reader_failure_terminates_and_unregisters(self) -> None:
        cancel_event = JobExecutionContext("ASSEMBLY_READER_FAILURE_TEST")
        terminate_calls: list[tuple[int, float | None]] = []
        real_terminate = assembly_module._terminate_process_tree

        class FailingStream:
            def read(self, _size: int) -> bytes:
                raise RuntimeError("unexpected reader failure")

        class SynchronousFailingThread:
            def __init__(self, *, target, args, name, daemon):
                self._target = target
                self._args = args
                self._alive = False

            def start(self) -> None:
                self._alive = True
                try:
                    self._target(FailingStream(), self._args[1])
                finally:
                    self._alive = False

            def join(self, timeout=None) -> None:
                return None

            def is_alive(self) -> bool:
                return self._alive

        def terminate(process, *, deadline=None) -> None:
            terminate_calls.append((process.pid, deadline))
            real_terminate(process, deadline=deadline)

        with (
            mock.patch.object(assembly_module.threading, "Thread", SynchronousFailingThread),
            mock.patch.object(assembly_module, "_terminate_process_tree", side_effect=terminate),
            self.assertRaisesRegex(RuntimeError, "unexpected reader failure"),
        ):
            assembly_module._bounded_process(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cwd=self.workspace,
                timeout=30,
                label="reader failure",
                cancel_event=cancel_event,
            )
        self.assertTrue(terminate_calls)
        self.assertEqual(cancel_event.process_pids(), set())
        self.assertTrue(
            all(deadline is not None for _, deadline in terminate_calls),
            "reader failure teardown must carry a bounded deadline",
        )

    def test_bounded_process_timeout_unregisters_within_cleanup_bound(self) -> None:
        cancel_event = JobExecutionContext("ASSEMBLY_TIMEOUT_TEST")
        started = time.monotonic()
        with self.assertRaisesRegex(AssemblyToolError, "timed out"):
            assembly_module._bounded_process(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cwd=self.workspace,
                timeout=0.05,
                label="bounded timeout",
                cancel_event=cancel_event,
            )
        elapsed = time.monotonic() - started
        self.assertEqual(cancel_event.process_pids(), set())
        self.assertLess(
            elapsed,
            0.05 + assembly_module._PROCESS_CLEANUP_TIMEOUT_SECONDS + 1.0,
        )

    def test_bounded_process_cancellation_kills_child_and_unregisters(self) -> None:
        cancel_event = JobExecutionContext("ASSEMBLY_CANCEL_TEST")
        errors: list[BaseException] = []

        def run() -> None:
            try:
                assembly_module._bounded_process(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=self.workspace,
                    timeout=30,
                    label="cancellable process",
                    cancel_event=cancel_event,
                )
            except BaseException as exc:  # assert the control-plane exception below
                errors.append(exc)

        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 5
        while not cancel_event.process_pids() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(cancel_event.process_pids(), "child must be registered while active")
        cancel_event.set()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "cancellation must not wait for the media timeout")
        self.assertEqual(cancel_event.process_pids(), set())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], JobCancelled)

    def test_public_workers_honor_pre_cancelled_context(self) -> None:
        cancel_event = JobExecutionContext("ASSEMBLY_PRE_CANCEL_TEST")
        cancel_event.set()
        key = self._key()
        common = {
            "workspace": self.workspace,
            "production_id": "PROD_TEST",
            "run_id": "RUN_PRE_CANCEL",
            "cache_key": key,
            "source_video": self.source,
            "narration_wav": self.narration,
            "captions_srt": self.captions,
            "include_captioned": True,
            "cancel_event": cancel_event,
        }
        with self.assertRaises(JobCancelled):
            generate_local_assembly(**common)
        with self.assertRaises(JobCancelled):
            validate_local_assembly_outputs(**common)

    def test_cache_revalidates_mp4_size_limit(self) -> None:
        first = self._run()
        clean = self.workspace / next(
            item["path"] for item in first["artifacts"] if item["name"] == "master-clean.mp4"  # type: ignore[index]
        )
        original_limit = assembly_module.MAX_OUTPUT_BYTES
        try:
            assembly_module.MAX_OUTPUT_BYTES = clean.stat().st_size - 1
            with self.assertRaisesRegex(AssemblyError, "integrity verification"):
                validate_local_assembly_outputs(
                    self.workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_TEST",
                    cache_key=self._key(),
                    source_video=self.source,
                    narration_wav=self.narration,
                    captions_srt=self.captions,
                    include_captioned=True,
                )
        finally:
            assembly_module.MAX_OUTPUT_BYTES = original_limit

    def test_srt_ass_override_text_is_escaped(self) -> None:
        raw = (
            "1\n00:00:00,000 --> 00:00:01,000\n"
            r"literal {\an8}{\pos(1,2)} and \N"
            "\n"
        ).encode("utf-8")
        ass = _build_ass(raw, width=160, height=96).decode("utf-8")
        dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
        self.assertNotIn("{\\an8}", dialogue)
        self.assertNotIn("{\\pos(1,2)}", dialogue)
        self.assertIn("｛", dialogue)
        self.assertIn("｝", dialogue)
        self.assertIn("＼N", dialogue)

    def test_cache_key_changes_with_tool_identity(self) -> None:
        kwargs = {
            "ffmpeg_identity": {"path": "C:/ffmpeg.exe", "version": "v1", "sha256": "A" * 64},
            "ffprobe_identity": {"path": "C:/ffprobe.exe", "version": "v1", "sha256": "B" * 64},
        }
        first = assembly_cache_key("A" * 64, "B" * 64, "C" * 64, True, **kwargs)
        changed = assembly_cache_key(
            "A" * 64,
            "B" * 64,
            "C" * 64,
            True,
            ffmpeg_identity={**kwargs["ffmpeg_identity"], "sha256": "D" * 64},
            ffprobe_identity=kwargs["ffprobe_identity"],
        )
        self.assertNotEqual(first, changed)

    def test_tool_identity_cache_detects_same_size_same_mtime_replacement(self) -> None:
        tool = self.workspace / "tool.bin"
        tool.write_bytes(b"A" * 32)
        original_stat = tool.stat()
        with mock.patch.object(assembly_module, "_bounded_process", return_value=b"tool version\n") as bounded:
            first = assembly_module._tool_identity("test-tool", tool)
            tool.write_bytes(b"B" * 32)
            os.utime(tool, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            second = assembly_module._tool_identity("test-tool", tool)
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(bounded.call_count, 2)


if __name__ == "__main__":
    unittest.main()
