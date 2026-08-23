from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.qc import (
    QcError,
    QcValidationError,
    generate_local_qc,
    qc_cache_key,
    validate_local_qc_outputs,
)
from tools.studio import qc as qc_module
from tools.studio.jobs import JobCancelled, JobExecutionContext
from tools.studio.qc_execution import (
    LocalQcError,
    LocalQcValidationError,
    qc_audit_payload,
    qc_public_result,
    safe_qc_error,
    validate_local_qc_payload,
)


ATTEMPT_ID = "attempt_" + "a" * 32
ARTIFACT_ID = "art_" + "b" * 32


def _tool(name: str) -> str | None:
    return shutil.which(name)


@unittest.skipUnless(_tool("ffmpeg") and _tool("ffprobe"), "ffmpeg/ffprobe are required")
class LocalQcMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.input_path = self.workspace / "assembly-master.mp4"
        self._make_mp4(self.input_path, "sine=frequency=800:duration=1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _make_mp4(self, path: Path, audio: str, *, duration: str = "1") -> None:
        ffmpeg = _tool("ffmpeg")
        assert ffmpeg is not None
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=160x96:r=24",
                "-f",
                "lavfi",
                "-i",
                audio,
                "-t",
                duration,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-y",
                str(path),
            ],
            shell=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0:
            self.skipTest("installed ffmpeg cannot encode the test MP4")

    def _request(
        self,
        *,
        variant: str = "clean",
        expected_duration_ms: int = 1_000,
    ) -> tuple[str, dict[str, object]]:
        digest = hashlib.sha256(self.input_path.read_bytes()).hexdigest().upper()
        size = self.input_path.stat().st_size
        key = qc_cache_key(
            production_id="PROD_TEST",
            run_id="RUN_QC",
            assembly_attempt_id=ATTEMPT_ID,
            assembly_artifact_id=ARTIFACT_ID,
            variant=variant,
            input_sha256=digest,
            input_bytes=size,
            expected_duration_ms=expected_duration_ms,
        )
        result = generate_local_qc(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_QC",
            cache_key=key,
            assembly_attempt_id=ATTEMPT_ID,
            assembly_artifact_id=ARTIFACT_ID,
            variant=variant,
            input_path=self.input_path,
            input_sha256=digest,
            input_bytes=size,
            expected_duration_ms=expected_duration_ms,
        )
        return key, result

    def _rewrite_manifest(self, output: Path, manifest: dict[str, object]) -> None:
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest().upper()
        manifest_path = output / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    def _validate_current_cache(self, key: str) -> None:
        digest = hashlib.sha256(self.input_path.read_bytes()).hexdigest().upper()
        with self.assertRaises(QcError):
            validate_local_qc_outputs(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_QC",
                cache_key=key,
                assembly_attempt_id=ATTEMPT_ID,
                assembly_artifact_id=ARTIFACT_ID,
                variant="clean",
                input_path=self.input_path,
                input_sha256=digest,
                input_bytes=self.input_path.stat().st_size,
                expected_duration_ms=1_000,
            )

    def test_real_mp4_passes_and_reuses_cache(self) -> None:
        key, first = self._request()
        self.assertEqual(first["analysis_status"], "succeeded")
        self.assertEqual(first["technical_verdict"], "pass")
        self.assertFalse(first["cache_hit"])
        self.assertEqual(first["provider"], "local_ffmpeg_qc")
        self.assertIsNone(first["provider_task_id"])
        self.assertEqual(first["actual_cost"], 0)
        self.assertEqual(first["timing_source"], "ffprobe")
        self.assertEqual(
            {item["name"] for item in first["artifacts"]},
            {"technical-qc.json", "ffprobe.json", "manifest.json"},
        )
        output = self.workspace / first["output_directory"]
        self.assertEqual(output, self.workspace / "outputs/studio/runs/RUN_QC/qc" / key)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["manifest_sha256"],
            hashlib.sha256(
                json.dumps(
                    {k: v for k, v in manifest.items() if k != "manifest_sha256"},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest().upper(),
        )
        _, second = self._request()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["technical_verdict"], "pass")

    def test_silent_audio_is_fail_not_worker_exception(self) -> None:
        self._make_mp4(self.input_path, "anullsrc=r=48000:cl=stereo")
        _, result = self._request()
        self.assertEqual(result["analysis_status"], "succeeded")
        self.assertEqual(result["technical_verdict"], "fail")
        self.assertFalse(result["checks"]["audio_not_silent"]["passed"])

    def test_short_all_silent_audio_is_detected_and_fails(self) -> None:
        self._make_mp4(
            self.input_path,
            "anullsrc=r=48000:cl=stereo",
            duration="0.05",
        )
        _, result = self._request(expected_duration_ms=50)
        self.assertEqual(result["analysis_status"], "succeeded")
        self.assertEqual(result["technical_verdict"], "fail")
        silence = result["media_facts"]["silence"]
        self.assertTrue(silence["all_silent"])
        self.assertFalse(result["checks"]["audio_not_silent"]["passed"])
        self.assertLessEqual(silence["duration_seconds"], 0.025)

    def test_silence_window_and_gap_tolerance_are_media_bounded(self) -> None:
        self.assertAlmostEqual(qc_module._silence_window_seconds(50), 0.025)
        self.assertAlmostEqual(qc_module._silence_window_seconds(1), 0.001)
        argv = qc_module._silence_argv("{output}", window_seconds=0.0001)
        self.assertIn("silencedetect=n=-50dB:d=0.001", argv)

        five_ms_gap = qc_module._ProcessResult(
            return_code=0,
            stdout=b"",
            stderr=(
                b"silence_start: 0\n"
                b"silence_end: 0.300 | silence_duration: 0.300\n"
                b"silence_start: 0.305\n"
                b"silence_end: 1.000 | silence_duration: 0.695\n"
            ),
        )
        facts = qc_module._silence_facts(five_ms_gap, duration_ms=1_000)
        self.assertFalse(facts["all_silent"])
        self.assertEqual(len(facts["silence_intervals_seconds"]), 2)

    def test_duration_requires_container_video_and_audio_durations(self) -> None:
        probe = {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "1.000"},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                    "duration": "1.000",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "duration": "1.300",
                },
            ],
        }
        successful = qc_module._ProcessResult(return_code=0, stdout=b"{}", stderr=b"")
        with (
            mock.patch.object(
                qc_module,
                "_run_probe",
                return_value=(probe, successful, None),
            ),
            mock.patch.object(qc_module, "_run_ffmpeg", return_value=successful),
        ):
            facts, checks, _ = qc_module._analyse(
                "ffmpeg",
                "ffprobe",
                stage=self.workspace,
            )
        qc_module._finalize_checks(facts, checks, 1_000)
        self.assertEqual(
            facts["durations_ms"],
            {"container": 1_000, "video": 1_000, "audio": 1_300},
        )
        self.assertFalse(checks["duration"]["passed"])

    def test_leading_and_trailing_silence_with_speech_is_not_all_silent(self) -> None:
        self._make_mp4(
            self.input_path,
            "aevalsrc=if(between(t\\,0.4\\,0.6)\\,0.2*sin(2*PI*800*t)\\,0):s=48000:d=1",
        )
        _, result = self._request()
        self.assertEqual(result["analysis_status"], "succeeded")
        self.assertEqual(result["technical_verdict"], "pass")
        self.assertFalse(result["media_facts"]["silence"]["all_silent"])

    def test_unreadable_media_is_analysis_success_with_fail_verdict(self) -> None:
        self.input_path.write_bytes(b"not an MP4")
        _, result = self._request()
        self.assertEqual(result["analysis_status"], "succeeded")
        self.assertEqual(result["technical_verdict"], "fail")
        self.assertFalse(result["checks"]["container_mp4"]["passed"])

    def test_cache_tamper_is_rebuilt_and_validate_rejects_tamper(self) -> None:
        key, first = self._request()
        output = self.workspace / first["output_directory"]
        manifest_path = output / "manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        digest = hashlib.sha256(self.input_path.read_bytes()).hexdigest().upper()
        size = self.input_path.stat().st_size
        with self.assertRaises(QcError):
            validate_local_qc_outputs(
                self.workspace,
                production_id="PROD_TEST",
                run_id="RUN_QC",
                cache_key=key,
                assembly_attempt_id=ATTEMPT_ID,
                assembly_artifact_id=ARTIFACT_ID,
                variant="clean",
                input_path=self.input_path,
                input_sha256=digest,
                input_bytes=size,
                expected_duration_ms=1_000,
            )
        rebuilt = generate_local_qc(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_QC",
            cache_key=key,
            assembly_attempt_id=ATTEMPT_ID,
            assembly_artifact_id=ARTIFACT_ID,
            variant="clean",
            input_path=self.input_path,
            input_sha256=digest,
            input_bytes=size,
            expected_duration_ms=1_000,
        )
        self.assertFalse(rebuilt["cache_hit"])

    def test_manifest_verdict_tamper_with_recomputed_self_hash_is_rejected(self) -> None:
        self._make_mp4(self.input_path, "anullsrc=r=48000:cl=stereo")
        key, first = self._request()
        output = self.workspace / first["output_directory"]
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["technical_verdict"] = "pass"
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest().upper()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        _, rebuilt = self._request()
        self.assertFalse(rebuilt["cache_hit"])
        self.assertEqual(rebuilt["technical_verdict"], "fail")

    def test_recomputed_manifest_unknown_field_is_rejected(self) -> None:
        key, first = self._request()
        output = self.workspace / first["output_directory"]
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["unexpected_field"] = "tampered"
        self._rewrite_manifest(output, manifest)
        self._validate_current_cache(key)

    def test_recomputed_manifest_cannot_hide_sidecar_metadata_tamper(self) -> None:
        key, first = self._request()
        output = self.workspace / first["output_directory"]
        technical_path = output / "technical-qc.json"
        technical = json.loads(technical_path.read_text(encoding="utf-8"))
        technical["provider"] = "tampered-provider"
        technical_path.write_text(
            json.dumps(technical, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["technical-qc.json"]["bytes"] = technical_path.stat().st_size
        manifest["files"]["technical-qc.json"]["sha256"] = hashlib.sha256(
            technical_path.read_bytes()
        ).hexdigest().upper()
        self._rewrite_manifest(output, manifest)
        self._validate_current_cache(key)

    def test_recomputed_manifest_cannot_hide_ffprobe_metadata_tamper(self) -> None:
        key, first = self._request()
        output = self.workspace / first["output_directory"]
        ffprobe_path = output / "ffprobe.json"
        ffprobe = json.loads(ffprobe_path.read_text(encoding="utf-8"))
        ffprobe["format"] = {"tampered": True}
        ffprobe_path.write_text(
            json.dumps(ffprobe, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["ffprobe.json"]["bytes"] = ffprobe_path.stat().st_size
        manifest["files"]["ffprobe.json"]["sha256"] = hashlib.sha256(
            ffprobe_path.read_bytes()
        ).hexdigest().upper()
        self._rewrite_manifest(output, manifest)
        self._validate_current_cache(key)


class LocalQcContractTests(unittest.TestCase):
    def test_public_body_is_exactly_two_fields(self) -> None:
        valid = {"assembly_attempt_id": ATTEMPT_ID, "variant": "captioned"}
        self.assertEqual(validate_local_qc_payload(valid), valid)
        for body in (
            {"assembly_attempt_id": ATTEMPT_ID, "variant": "clean", "assembly_artifact_id": ARTIFACT_ID},
            {"assembly_attempt_id": ATTEMPT_ID, "variant": "clean", "expected_duration_ms": 1000},
            {"assembly_attempt_id": ATTEMPT_ID},
            {"assembly_attempt_id": ATTEMPT_ID, "variant": "other"},
        ):
            with self.subTest(body=body), self.assertRaises(LocalQcValidationError):
                validate_local_qc_payload(body)

    def test_audit_and_public_result_keep_provenance(self) -> None:
        payload = {"assembly_attempt_id": ATTEMPT_ID, "variant": "clean"}
        digest = "A" * 64
        audit = qc_audit_payload(
            payload,
            assembly_artifact_id=ARTIFACT_ID,
            input_sha256=digest,
            input_bytes=12,
            expected_duration_ms=1_000,
            cache_key="A" * 64,
        )
        self.assertEqual(audit["assembly_artifact_id"], ARTIFACT_ID)
        raw = {
            "analysis_status": "succeeded",
            "technical_verdict": "fail",
            "cache_hit": False,
            "duration_ms": 1_000,
            "assembly_attempt_id": ATTEMPT_ID,
            "assembly_artifact_id": ARTIFACT_ID,
            "variant": "clean",
            "input_sha256": digest,
            "input_bytes": 12,
            "expected_duration_ms": 1_000,
            "checks": {"audio_not_silent": {"passed": False}},
            "media_facts": {"duration_ms": 1_000},
            "cache_key": "A" * 64,
            "provider": "local_ffmpeg_qc",
            "provider_task_id": None,
            "actual_cost": 0,
            "timing_source": "ffprobe",
        }
        result = qc_public_result(
            raw,
            expected_cache_key="A" * 64,
            expected_assembly_attempt_id=ATTEMPT_ID,
            expected_assembly_artifact_id=ARTIFACT_ID,
            expected_variant="clean",
            expected_input_sha256=digest,
            expected_input_bytes=12,
            expected_duration_ms=1_000,
            artifacts=[],
            cache_hit=False,
        )
        self.assertEqual(result["technical_verdict"], "fail")
        self.assertEqual(result["provider"], "local_ffmpeg_qc")

    def test_safe_error_is_bounded(self) -> None:
        error = LocalQcError("private path", code="local_ffmpeg_qc_timeout")
        self.assertEqual(safe_qc_error(error), ("local_ffmpeg_qc_timeout", "private path"))
        self.assertEqual(safe_qc_error(RuntimeError("secret"))[0], "local_qc_failed")

    def test_timeout_raises_bounded_tool_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(QcError) as raised:
                qc_module._bounded_process(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=Path(temporary),
                    timeout=0.05,
                    label="test timeout",
                )
        self.assertEqual(raised.exception.error_code, "local_ffmpeg_qc_timeout")

    def test_bounded_process_drains_both_noisy_pipes_without_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(qc_module, "MAX_PROCESS_OUTPUT_BYTES", 32):
                with self.assertRaisesRegex(QcError, "excessive diagnostics"):
                    qc_module._bounded_process(
                        [
                            sys.executable,
                            "-c",
                            "import sys; sys.stdout.write('x' * 1000000); sys.stderr.write('y' * 1000000)",
                        ],
                        cwd=Path(temporary),
                        timeout=10,
                        label="noisy process",
                    )

    def test_bounded_process_reader_failure_terminates_and_unregisters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cancel_event = JobExecutionContext("QC_READER_FAILURE_TEST")
            terminate_calls: list[tuple[int, float | None]] = []
            real_terminate = qc_module._terminate_process_tree

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
                mock.patch.object(qc_module.threading, "Thread", SynchronousFailingThread),
                mock.patch.object(qc_module, "_terminate_process_tree", side_effect=terminate),
                self.assertRaisesRegex(RuntimeError, "unexpected reader failure"),
            ):
                qc_module._bounded_process(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=Path(temporary),
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
        with tempfile.TemporaryDirectory() as temporary:
            cancel_event = JobExecutionContext("QC_TIMEOUT_TEST")
            started = time.monotonic()
            with self.assertRaisesRegex(QcError, "timed out"):
                qc_module._bounded_process(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=Path(temporary),
                    timeout=0.05,
                    label="bounded timeout",
                    cancel_event=cancel_event,
                )
            elapsed = time.monotonic() - started
            self.assertEqual(cancel_event.process_pids(), set())
            self.assertLess(
                elapsed,
                0.05 + qc_module._PROCESS_CLEANUP_TIMEOUT_SECONDS + 1.0,
            )

    def test_bounded_process_cancellation_kills_child_and_unregisters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cancel_event = JobExecutionContext("QC_CANCEL_TEST")
            errors: list[BaseException] = []

            def run() -> None:
                try:
                    qc_module._bounded_process(
                        [sys.executable, "-c", "import time; time.sleep(60)"],
                        cwd=Path(temporary),
                        timeout=30,
                        label="cancellable process",
                        cancel_event=cancel_event,
                    )
                except BaseException as exc:
                    errors.append(exc)

            worker = threading.Thread(target=run)
            worker.start()
            deadline = time.monotonic() + 5
            while not cancel_event.process_pids() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(cancel_event.process_pids(), "child must be registered while active")
            cancel_event.set()
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive(), "cancellation must not wait for media timeout")
            self.assertEqual(cancel_event.process_pids(), set())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], JobCancelled)

    def test_bounded_process_preserves_nonzero_result_for_technical_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = qc_module._bounded_process(
                [sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(7)"],
                cwd=Path(temporary),
                timeout=10,
                label="nonzero process",
            )
        self.assertEqual(result.return_code, 7)
        self.assertEqual(result.stderr, b"bad")

    def test_tool_identity_detects_same_size_same_mtime_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "tool"
            executable.write_bytes(b"tool-a")
            fixed_ns = 1_700_000_000_000_000_000
            os.utime(executable, ns=(fixed_ns, fixed_ns))
            previous_cache = dict(qc_module._TOOL_IDENTITY_CACHE)
            try:
                qc_module._TOOL_IDENTITY_CACHE.clear()
                version_result = qc_module._ProcessResult(
                    return_code=0,
                    stdout=b"tool version\n",
                    stderr=b"",
                )
                with (
                    mock.patch.object(qc_module, "_find_tool", return_value=str(executable)),
                    mock.patch.object(
                        qc_module,
                        "_bounded_process",
                        return_value=version_result,
                    ) as bounded,
                ):
                    first = qc_module._tool_identity("test-tool", executable)
                    executable.write_bytes(b"tool-b")
                    os.utime(executable, ns=(fixed_ns, fixed_ns))
                    second = qc_module._tool_identity("test-tool", executable)
                self.assertNotEqual(first["sha256"], second["sha256"])
                self.assertEqual(bounded.call_count, 2)
            finally:
                qc_module._TOOL_IDENTITY_CACHE.clear()
                qc_module._TOOL_IDENTITY_CACHE.update(previous_cache)

    def test_boundary_and_input_hash_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            input_path = workspace / "master.mp4"
            input_path.write_bytes(b"not a media file")
            with self.assertRaises(QcValidationError):
                generate_local_qc(
                    workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_QC",
                    cache_key="A" * 64,
                    assembly_attempt_id=ATTEMPT_ID,
                    assembly_artifact_id=ARTIFACT_ID,
                    variant="clean",
                    input_path=input_path,
                    input_sha256="B" * 64,
                    input_bytes=input_path.stat().st_size,
                    expected_duration_ms=1_000,
                )
            with self.assertRaises(QcValidationError):
                generate_local_qc(
                    workspace,
                    production_id="../outside",
                    run_id="RUN_QC",
                    cache_key="A" * 64,
                    assembly_attempt_id=ATTEMPT_ID,
                    assembly_artifact_id=ARTIFACT_ID,
                    variant="clean",
                    input_path=input_path,
                    input_sha256="A" * 64,
                    input_bytes=input_path.stat().st_size,
                    expected_duration_ms=1_000,
                )


if __name__ == "__main__":
    unittest.main()
