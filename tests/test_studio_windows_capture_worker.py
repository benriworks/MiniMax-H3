from __future__ import annotations

import json
import io
import ctypes
import threading
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.studio import windows_capture_worker as capture_worker
from tools.studio.windows_capture import (
    WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
    WindowsCaptureError,
    WindowsCaptureValidationError,
    windows_capture_key,
    windows_capture_public_result,
    windows_capture_request_digest,
)
from tools.studio.windows_capture_worker import (
    _JobObjectExtendedLimitInformation,
    _ThreadEntry32,
    _WindowsKillOnCloseJob,
    _capture_to_master,
    _clean_environment,
    _complete_synchronization_record,
    _final_mp4_timing,
    _parse_helper_events,
    _popen_options,
    _run_contained_process,
    _synchronization_matches_final_probe,
    _synchronization_record_is_valid,
    _validate_master_synchronization,
    _validate_png,
    _validate_probe_set,
    cleanup_stale_windows_capture_partials,
    discard_windows_capture_outputs,
    generate_windows_capture,
)


REQUEST = {
    "schema_version": 1,
    "target": "primary_display",
    "audio_mode": "default_render_loopback",
    "cursor_mode": "hidden",
    "duration_ms": 1_000,
    "confirm_capture": True,
    "confirm_system_audio": True,
}
DIGEST = "A" * 64


def _helper_events(duration_ms: int = 1_000) -> bytes:
    audio_format = {
        "encoding": "s16le",
        "samplesPerSecond": 48_000,
        "channels": 2,
        "bitsPerSample": 16,
        "bytesPerFrame": 4,
    }
    common = {
        "schemaVersion": 1,
        "operation": "capture_loopback",
        "ok": True,
        "durationMs": duration_ms,
        "format": audio_format,
        "recordingStarted": True,
    }
    ready = {**common, "event": "ready", "recordingStarted": False}
    started = {**common, "event": "started"}
    completed = {
        **common,
        "event": "completed",
        "framesWritten": duration_ms * 48,
        "bytesWritten": duration_ms * 192,
        "paddedFrames": 0,
        "silentFrames": 0,
        "discontinuityCount": 0,
        "timestampErrorCount": 0,
        "firstPacketOffsetFrames": 0,
        "gapFrames": 0,
        "tailPaddedFrames": 0,
        "firstPacketQpcOffset100ns": 100_000,
        "qpcSpan100ns": 9_800_000,
        "maxQpcDrift100ns": 10_000,
        "startCallDuration100ns": 5_000,
    }
    return (
        json.dumps(ready, separators=(",", ":"))
        + "\n"
        + json.dumps(started, separators=(",", ":"))
        + "\n"
        + json.dumps(completed, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _video_stream() -> dict[str, object]:
    return {
        "codec_type": "video",
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "24/1",
        "avg_frame_rate": "24/1",
        "start_time": "0.000",
        "duration": "1.000",
        "duration_ts": "24000",
        "time_base": "1/24000",
        "nb_read_frames": "24",
    }


def _audio_stream(codec: str) -> dict[str, object]:
    return {
        "codec_type": "audio",
        "codec_name": codec,
        "sample_rate": "48000",
        "channels": 2,
        "start_time": "0.000",
        "duration": "1.000",
        "duration_ts": "48000",
        "time_base": "1/48000",
        "nb_read_frames": "48",
    }


class WindowsCaptureWorkerContractTests(unittest.TestCase):
    def test_frame_validation_rejects_non_png_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"\xff\xd8\xff\xe0not-png")
            with self.assertRaises(WindowsCaptureError):
                _validate_png(frame)
            frame.write_bytes(b"\x89PNG\r\n\x1a\n")
            _validate_png(frame)

    def test_windows_popen_options_include_documented_suspended_flag(self) -> None:
        with mock.patch(
            "tools.studio.windows_capture_worker.os.name", "nt"
        ), mock.patch(
            "tools.studio.windows_capture_worker.subprocess.CREATE_NEW_PROCESS_GROUP",
            0x200,
            create=True,
        ):
            self.assertEqual(
                _popen_options(suspended=True), {"creationflags": 0x204}
            )

    def test_request_identity_includes_tool_and_nonce(self) -> None:
        request_digest = windows_capture_request_digest(
            REQUEST, tool_identity_digest=DIGEST
        )
        first = windows_capture_key(
            REQUEST, "0" * 32, tool_identity_digest=DIGEST
        )
        second = windows_capture_key(
            REQUEST, "1" * 32, tool_identity_digest=DIGEST
        )
        self.assertRegex(request_digest, r"^[0-9A-F]{64}$")
        self.assertNotEqual(first, second)

    def test_helper_events_require_exact_fixed_pcm_and_sample_count(self) -> None:
        events = _parse_helper_events(_helper_events(), 1_000)
        self.assertEqual(events[-1]["framesWritten"], 48_000)

        lines = _helper_events().decode("utf-8").splitlines()
        changed = json.loads(lines[2])
        changed["deviceId"] = "must-not-be-accepted"
        with self.assertRaises(WindowsCaptureError):
            _parse_helper_events(
                ("\n".join([lines[0], lines[1], json.dumps(changed)]) + "\n").encode(
                    "utf-8"
                ),
                1_000,
            )

        initial_discontinuity = json.loads(lines[2])
        initial_discontinuity["discontinuityCount"] = 1
        parsed = _parse_helper_events(
            (
                "\n".join(
                    [lines[0], lines[1], json.dumps(initial_discontinuity)]
                )
                + "\n"
            ).encode("utf-8"),
            1_000,
        )
        self.assertEqual(parsed[-1]["discontinuityCount"], 1)

        for counter, unsafe_value in (
            ("timestampErrorCount", 1),
            ("discontinuityCount", 2),
        ):
            unsafe = json.loads(lines[2])
            unsafe[counter] = unsafe_value
            with self.subTest(counter=counter), self.assertRaises(
                WindowsCaptureError
            ):
                _parse_helper_events(
                    (
                        "\n".join([lines[0], lines[1], json.dumps(unsafe)]) + "\n"
                    ).encode("utf-8"),
                    1_000,
                )

    def test_probe_contract_requires_h264_aac_and_separate_pcm(self) -> None:
        combined = {
            "streams": [_video_stream(), _audio_stream("aac")],
            "format": {
                "format_name": "mov,mp4",
                "duration": "1.000",
                "start_time": "0.000",
            },
        }
        video = {
            "streams": [_video_stream()],
            "format": {"format_name": "mov,mp4", "duration": "1.000"},
        }
        audio = {
            "streams": [_audio_stream("pcm_s16le")],
            "format": {"format_name": "wav", "duration": "1.000"},
        }
        self.assertEqual(
            _validate_probe_set(
                screen_capture=combined,
                screen_video=video,
                system_audio=audio,
                expected_duration_ms=1_000,
            ),
            1_000,
        )
        with self.assertRaises(WindowsCaptureError):
            _validate_probe_set(
                screen_capture=video,
                screen_video=video,
                system_audio=audio,
                expected_duration_ms=1_000,
            )

        short_combined = json.loads(json.dumps(combined))
        short_video = json.loads(json.dumps(video))
        short_audio = json.loads(json.dumps(audio))
        short_combined["streams"][0]["nb_read_frames"] = "18"
        short_combined["streams"][1]["duration_ts"] = "36000"
        short_video["streams"][0]["nb_read_frames"] = "18"
        short_audio["streams"][0]["duration_ts"] = "36000"
        with self.assertRaises(WindowsCaptureError) as rejected:
            _validate_probe_set(
                screen_capture=short_combined,
                screen_video=short_video,
                system_audio=short_audio,
                expected_duration_ms=1_000,
            )
        self.assertEqual(rejected.exception.error_code, "invalid_output_media")

    def test_master_sync_requires_wallclock_pts_within_fifty_ms(self) -> None:
        completed = json.loads(_helper_events().decode("utf-8").splitlines()[2])
        probe = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "start_time": "0.000",
                    "duration": "1.000",
                    "time_base": "1/1000",
                    "nb_read_frames": "24",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "start_time": "0.020",
                    "duration": "0.980",
                    "time_base": "1/1000",
                },
            ],
            "packets": [
                *[
                    {
                        "stream_index": 0,
                        "pts": index * 41,
                        "duration": 41,
                    }
                    for index in range(24)
                ],
                {
                    "stream_index": 1,
                    "pts": 20,
                    "duration": 1000,
                    "size": 192_000,
                },
            ],
            "format": {
                "format_name": "matroska,webm",
                "duration": "1.000",
                "start_time": "0.000",
            },
        }
        result = _validate_master_synchronization(
            probe, completed_event=completed, expected_duration_ms=1_000
        )
        self.assertNotIn("verified", result)
        self.assertFalse(result["source_clock_correlation_verified"])
        self.assertEqual(result["master_start_skew_ms"], 20.0)

        absolute_container_duration = json.loads(json.dumps(probe))
        absolute_container_duration["format"]["duration"] = "1788070089.613"
        packet_timed = _validate_master_synchronization(
            absolute_container_duration,
            completed_event=completed,
            expected_duration_ms=1_000,
        )
        self.assertEqual(packet_timed["master_duration_ms"], 1020.0)

        final_probe = {
            "streams": [_video_stream(), _audio_stream("aac")],
            "format": {
                "format_name": "mov,mp4",
                "duration": "1.000",
                "start_time": "0.000",
            },
        }
        synchronization = _complete_synchronization_record(
            result, final_probe, expected_duration_ms=1_000
        )
        self.assertTrue(synchronization["structural_timing_verified"])
        self.assertTrue(synchronization["container_timestamps_verified"])
        self.assertTrue(synchronization["wasapi_packet_timing_verified"])
        self.assertFalse(synchronization["content_sync_verified"])
        self.assertTrue(synchronization["live_validation_required"])
        self.assertFalse(synchronization["source_clock_correlation_verified"])
        self.assertEqual(
            synchronization["validation_scope"],
            WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
        )
        self.assertTrue(
            _synchronization_record_is_valid(
                synchronization, expected_duration_ms=1_000
            )
        )
        self.assertTrue(
            _synchronization_matches_final_probe(
                synchronization, final_probe, expected_duration_ms=1_000
            )
        )
        self.assertFalse(
            _synchronization_record_is_valid(
                {**synchronization, "content_sync_verified": True},
                expected_duration_ms=1_000,
            )
        )
        self.assertFalse(
            _synchronization_matches_final_probe(
                {**synchronization, "final_mp4_audio_duration_ms": 999.0},
                final_probe,
                expected_duration_ms=1_000,
            )
        )

        missing_final_timestamp = json.loads(json.dumps(final_probe))
        missing_final_timestamp["streams"][1].pop("start_time")
        with self.assertRaises(WindowsCaptureError):
            _final_mp4_timing(
                missing_final_timestamp, expected_duration_ms=1_000
            )

        excessive_final_skew = json.loads(json.dumps(final_probe))
        excessive_final_skew["streams"][1]["start_time"] = "0.080"
        with self.assertRaises(WindowsCaptureError):
            _final_mp4_timing(excessive_final_skew, expected_duration_ms=1_000)

        truncated_final_stream = json.loads(json.dumps(final_probe))
        truncated_final_stream["streams"][1]["duration"] = "0.700"
        with self.assertRaises(WindowsCaptureError):
            _final_mp4_timing(
                truncated_final_stream, expected_duration_ms=1_000
            )

        missing_timestamp = json.loads(json.dumps(probe))
        missing_timestamp["streams"][1].pop("start_time")
        with self.assertRaises(WindowsCaptureError):
            _validate_master_synchronization(
                missing_timestamp,
                completed_event=completed,
                expected_duration_ms=1_000,
            )

        excessive_skew = json.loads(json.dumps(probe))
        excessive_skew["streams"][1]["start_time"] = "0.080"
        with self.assertRaises(WindowsCaptureError):
            _validate_master_synchronization(
                excessive_skew,
                completed_event=completed,
                expected_duration_ms=1_000,
            )

        truncated_pcm = json.loads(json.dumps(probe))
        truncated_pcm["packets"][-1]["size"] -= 4
        with self.assertRaises(WindowsCaptureError):
            _validate_master_synchronization(
                truncated_pcm,
                completed_event=completed,
                expected_duration_ms=1_000,
            )

        short_master = json.loads(json.dumps(probe))
        short_master["streams"][0]["nb_read_frames"] = "18"
        short_master["packets"] = [
            *short_master["packets"][:18],
            {
                "stream_index": 1,
                "pts": 20,
                "duration": 750,
                "size": 144_000,
            },
        ]
        with self.assertRaises(WindowsCaptureError):
            _validate_master_synchronization(
                short_master,
                completed_event=completed,
                expected_duration_ms=1_000,
            )

    def test_capture_children_are_contained_before_start_gate(self) -> None:
        events: list[str] = []
        gate_sent = threading.Event()

        class RecordingPipe(io.BytesIO):
            def __init__(self) -> None:
                super().__init__()
                self.written = bytearray()

            def write(self, value: bytes) -> int:
                self.written.extend(value)
                events.append("gate")
                gate_sent.set()
                return super().write(value)

        gate = RecordingPipe()

        class StagedHelperStderr:
            def __init__(self) -> None:
                lines = _helper_events().splitlines(keepends=True)
                self.ready = lines[0]
                self.remaining = b"".join(lines[1:])
                self.ready_returned = False
                self.remaining_returned = False

            def readline(self, _limit: int) -> bytes:
                self.ready_returned = True
                return self.ready

            def read1(self, _size: int) -> bytes:
                if self.remaining_returned:
                    return b""
                if not gate_sent.wait(timeout=1.0):
                    raise AssertionError("helper metadata drain blocked the start gate")
                self.remaining_returned = True
                return self.remaining

            def close(self) -> None:
                return None

        class FakeProcess:
            def __init__(self, role: str) -> None:
                self.role = role
                self.pid = 100 if role == "helper" else 200
                self._handle = self.pid + 1
                self.returncode = 0
                self.stdin = gate if role == "helper" else None
                self.stdout = (
                    io.BytesIO(b"pcm") if role == "helper" else io.BytesIO()
                )
                self.stderr = (
                    StagedHelperStderr() if role == "helper" else io.BytesIO()
                )

            def poll(self) -> int | None:
                if self.role == "helper" and not gate.written:
                    return None
                return 0

        processes = [FakeProcess("helper"), FakeProcess("ffmpeg")]

        class FakeContainment:
            def assign(self, process: FakeProcess) -> None:
                events.append(f"assign:{process.role}")

            def resume(self, process: FakeProcess) -> None:
                events.append(f"resume:{process.role}")

            def close(self) -> None:
                events.append("close")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tools.studio.windows_capture_worker._WindowsKillOnCloseJob",
            return_value=FakeContainment(),
        ), mock.patch(
            "tools.studio.windows_capture_worker.subprocess.Popen",
            side_effect=processes,
        ) as popen, mock.patch(
            "tools.studio.windows_capture_worker._assembly._register_process",
            return_value=False,
        ), mock.patch(
            "tools.studio.windows_capture_worker._popen_options",
            return_value={"creationflags": 516},
        ) as popen_options:
            result = _capture_to_master(
                dotnet="dotnet.exe",
                helper=Path("helper.dll"),
                ffmpeg="ffmpeg.exe",
                duration_ms=1_000,
                display_width=1920,
                display_height=1080,
                output=Path(directory) / "master.mkv",
                cwd=Path(directory),
                cancel_event=None,
            )

        self.assertEqual(result[-1]["event"], "completed")
        self.assertEqual(gate.written, b"S")
        self.assertLess(events.index("assign:helper"), events.index("resume:helper"))
        self.assertLess(events.index("assign:ffmpeg"), events.index("resume:ffmpeg"))
        self.assertLess(events.index("resume:ffmpeg"), events.index("gate"))
        self.assertEqual(events[-1], "close")
        self.assertEqual(
            popen_options.call_args_list,
            [mock.call(suspended=True), mock.call(suspended=True)],
        )
        helper_arguments = popen.call_args_list[0].args[0]
        ffmpeg_arguments = popen.call_args_list[1].args[0]
        self.assertEqual(
            helper_arguments[-3:], ["--duration-ms", "1000", "--start-gated"]
        )
        self.assertEqual(ffmpeg_arguments.count("-use_wallclock_as_timestamps"), 1)
        self.assertNotIn("-isync", ffmpeg_arguments)
        self.assertIn("-copyts", ffmpeg_arguments)
        self.assertIn("-start_at_zero", ffmpeg_arguments)
        self.assertNotIn("-shortest", ffmpeg_arguments)
        self.assertLess(
            ffmpeg_arguments.index("-t"), ffmpeg_arguments.index("desktop")
        )
        self.assertTrue(popen.call_args_list[0].kwargs["close_fds"])
        self.assertTrue(popen.call_args_list[1].kwargs["close_fds"])

    def test_job_object_is_kill_on_close_for_parent_exit(self) -> None:
        configured_flags: list[int] = []
        closed_handles: list[int] = []
        api_order: list[str] = []

        class FakeFunction:
            def __init__(self, callback):
                self.callback = callback
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.callback(*args)

        class FakeKernel32:
            def __init__(self) -> None:
                self.CreateJobObjectW = FakeFunction(lambda *_: 123)

                def set_information(_handle, _kind, pointer, _size):
                    value = ctypes.cast(
                        pointer,
                        ctypes.POINTER(_JobObjectExtendedLimitInformation),
                    ).contents
                    configured_flags.append(
                        int(value.BasicLimitInformation.LimitFlags)
                    )
                    return 1

                self.SetInformationJobObject = FakeFunction(set_information)
                self.AssignProcessToJobObject = FakeFunction(
                    lambda *_: api_order.append("assign") or 1
                )
                self.CloseHandle = FakeFunction(
                    lambda handle: closed_handles.append(int(handle.value)) or 1
                )
                self.CreateToolhelp32Snapshot = FakeFunction(lambda *_: 456)

                def first_thread(_snapshot, pointer):
                    entry = ctypes.cast(
                        pointer, ctypes.POINTER(_ThreadEntry32)
                    ).contents
                    entry.th32ThreadID = 321
                    entry.th32OwnerProcessID = 999
                    return 1

                self.Thread32First = FakeFunction(first_thread)
                self.Thread32Next = FakeFunction(lambda *_: 0)
                self.OpenThread = FakeFunction(lambda *_: 789)
                self.ResumeThread = FakeFunction(
                    lambda *_: api_order.append("resume") or 1
                )

        kernel32 = FakeKernel32()
        with mock.patch(
            "tools.studio.windows_capture_worker.os.name", "nt"
        ), mock.patch(
            "tools.studio.windows_capture_worker.ctypes.WinDLL",
            return_value=kernel32,
            create=True,
        ):
            job = _WindowsKillOnCloseJob()
            process = mock.Mock(pid=999, _handle=998)
            process.poll.return_value = None
            job.assign(process)
            job.resume(process)
            job.close()

        self.assertEqual(configured_flags, [0x00002000])
        self.assertEqual(api_order, ["assign", "resume"])
        self.assertEqual(closed_handles, [456, 789, 123])

    def test_every_bounded_media_child_is_assigned_before_resume(self) -> None:
        events: list[str] = []

        class FakeProcess:
            pid = 777
            _handle = 778
            returncode = 0

            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"")
                self.stderr = io.BytesIO(b"")
                self.resumed = False

            def poll(self) -> int | None:
                return 0 if self.resumed else None

            def wait(self, timeout: float | None = None) -> int:
                events.append("wait")
                self.returncode = 0
                return 0

            def kill(self) -> None:
                events.append("kill")
                self.returncode = -9

        process = FakeProcess()

        class FakeContainment:
            def assign(self, candidate: FakeProcess) -> None:
                if candidate is not process:
                    raise AssertionError("unexpected process")
                events.append("assign")

            def resume(self, candidate: FakeProcess) -> None:
                if candidate is not process:
                    raise AssertionError("unexpected process")
                events.append("resume")
                candidate.resumed = True

            def close(self) -> None:
                events.append("close")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tools.studio.windows_capture_worker._WindowsKillOnCloseJob",
            return_value=FakeContainment(),
        ), mock.patch(
            "tools.studio.windows_capture_worker.subprocess.Popen",
            return_value=process,
        ) as popen, mock.patch(
            "tools.studio.windows_capture_worker._assembly._register_process",
            return_value=False,
        ), mock.patch(
            "tools.studio.windows_capture_worker._popen_options",
            return_value={"creationflags": 516},
        ) as options:
            result = _run_contained_process(
                ["ffprobe.exe", "-version"],
                cwd=Path(directory),
                timeout=1,
                label="test probe",
                cancel_event=None,
            )

        self.assertEqual(result, (0, b"", b""))
        self.assertLess(events.index("assign"), events.index("resume"))
        self.assertIn("wait", events)
        self.assertEqual(options.call_args_list, [mock.call(suspended=True)])
        self.assertTrue(popen.call_args.kwargs["close_fds"])

    def test_unassigned_suspended_child_never_runs_and_is_reaped(self) -> None:
        events: list[str] = []

        class FakeProcess:
            pid = 888
            _handle = 889
            returncode: int | None = None

            def __init__(self) -> None:
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.resumed = False

            def poll(self) -> int | None:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                events.append("wait")
                return int(self.returncode or 0)

            def kill(self) -> None:
                events.append("kill")
                self.returncode = -9

        process = FakeProcess()

        class RejectingContainment:
            def assign(self, candidate: FakeProcess) -> None:
                events.append("assign")
                raise WindowsCaptureError(
                    "containment failed", code="windows_capture_failed"
                )

            def resume(self, candidate: FakeProcess) -> None:
                candidate.resumed = True
                events.append("resume")

            def close(self) -> None:
                events.append("close")

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tools.studio.windows_capture_worker._WindowsKillOnCloseJob",
            return_value=RejectingContainment(),
        ), mock.patch(
            "tools.studio.windows_capture_worker.subprocess.Popen",
            return_value=process,
        ), mock.patch(
            "tools.studio.windows_capture_worker._popen_options",
            return_value={"creationflags": 516},
        ):
            with self.assertRaises(WindowsCaptureError):
                _run_contained_process(
                    ["ffprobe.exe", "-version"],
                    cwd=Path(directory),
                    timeout=1,
                    label="test probe",
                    cancel_event=None,
                )

        self.assertFalse(process.resumed)
        self.assertNotIn("resume", events)
        self.assertEqual(events[:2], ["assign", "close"])
        self.assertIn("kill", events)
        self.assertIn("wait", events)

    def test_missing_confirmation_stops_before_tool_resolution(self) -> None:
        rejected = {**REQUEST, "confirm_system_audio": False}
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tools.studio.windows_capture_worker._resolve_tools"
        ) as resolver:
            with self.assertRaises(WindowsCaptureValidationError):
                generate_windows_capture(
                    Path(directory),
                    production_id="TEST_windows_capture",
                    run_id="run_" + "a" * 32,
                    capture_key="B" * 64,
                    payload=rejected,
                    expected_tool_identity_digest=DIGEST,
                )
        resolver.assert_not_called()

    def test_public_result_rejects_any_cache_reuse_claim(self) -> None:
        raw = {
            "duration_ms": 1_000,
            "provider": "local_windows_capture",
            "timing_source": "ffprobe",
            "capture_key": "B" * 64,
            "tool_identity_digest": DIGEST,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cache_hit": True,
            "provider_task_id": None,
            "actual_cost": 0,
            "actual_capture_performed": True,
            "structural_timing_verified": True,
            "content_sync_verified": False,
            "live_validation_required": True,
            "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
            "public_release_ready": False,
            "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        }
        with self.assertRaises(WindowsCaptureError):
            windows_capture_public_result(
                raw,
                expected_capture_key="B" * 64,
                expected_duration_ms=1_000,
                expected_tool_identity_digest=DIGEST,
                artifacts=[],
            )

    def test_public_result_preserves_unverified_content_sync_gate(self) -> None:
        raw = {
            "duration_ms": 1_000,
            "provider": "local_windows_capture",
            "timing_source": "ffprobe",
            "capture_key": "B" * 64,
            "tool_identity_digest": DIGEST,
            "target": "primary_display",
            "audio_mode": "default_render_loopback",
            "cache_hit": False,
            "provider_task_id": None,
            "actual_cost": 0,
            "actual_capture_performed": True,
            "structural_timing_verified": True,
            "content_sync_verified": False,
            "live_validation_required": True,
            "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
            "public_release_ready": False,
            "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        }
        result = windows_capture_public_result(
            raw,
            expected_capture_key="B" * 64,
            expected_duration_ms=1_000,
            expected_tool_identity_digest=DIGEST,
            artifacts=[],
        )
        self.assertTrue(result["structural_timing_verified"])
        self.assertFalse(result["content_sync_verified"])
        self.assertTrue(result["live_validation_required"])
        self.assertFalse(result["public_release_ready"])
        self.assertEqual(
            result["public_release_gate"], WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE
        )

        false_claim = {**raw, "content_sync_verified": True}
        with self.assertRaises(WindowsCaptureError):
            windows_capture_public_result(
                false_claim,
                expected_capture_key="B" * 64,
                expected_duration_ms=1_000,
                expected_tool_identity_digest=DIGEST,
                artifacts=[],
            )

    def test_discard_targets_only_the_exact_capture_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "run_" + "a" * 32
            key = "B" * 64
            stage = root / "outputs" / "studio" / "runs" / run_id / "screen_capture"
            target = stage / key
            sibling = stage / ("C" * 64)
            target.mkdir(parents=True)
            sibling.mkdir()
            (target / "partial.tmp").write_bytes(b"private")
            discard_windows_capture_outputs(root, run_id=run_id, capture_key=key)
            self.assertFalse(target.exists())
            self.assertTrue(sibling.is_dir())

    def test_cleanup_failure_is_audited_blocks_capture_and_startup_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "run_" + "a" * 32
            key = "B" * 64
            stage = root / "outputs" / "studio" / "runs" / run_id / "screen_capture"
            target = stage / key
            target.mkdir(parents=True)
            (target / "private.mp4").write_bytes(b"private")

            with mock.patch(
                "tools.studio.windows_capture_worker.shutil.rmtree",
                side_effect=OSError("locked"),
            ), mock.patch("tools.studio.windows_capture_worker.time.sleep"):
                with self.assertRaises(WindowsCaptureError) as failed:
                    discard_windows_capture_outputs(
                        root, run_id=run_id, capture_key=key
                    )
            self.assertEqual(
                failed.exception.error_code, "windows_capture_cleanup_failed"
            )
            marker = stage / ".windows-capture-cleanup-required.json"
            marker_value = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(
                marker_value["targets"],
                [{"target_kind": "published", "target_name": key}],
            )

            with mock.patch(
                "tools.studio.windows_capture_worker._resolve_tools"
            ) as resolver:
                with self.assertRaises(WindowsCaptureError) as blocked:
                    generate_windows_capture(
                        root,
                        production_id="TEST_windows_capture",
                        run_id="run_" + "c" * 32,
                        capture_key="D" * 64,
                        payload=REQUEST,
                        expected_tool_identity_digest=DIGEST,
                    )
            self.assertEqual(
                blocked.exception.error_code, "windows_capture_cleanup_required"
            )
            resolver.assert_not_called()

            result = cleanup_stale_windows_capture_partials(root)
            self.assertEqual(result, {"removed": 1, "failed": 0})
            self.assertFalse(target.exists())
            self.assertFalse(marker.exists())

    def test_marker_write_denied_uses_fallback_ledger_and_restart_cleans_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = "run_" + "a" * 32
            key = "B" * 64
            stage = root / "outputs" / "studio" / "runs" / run_id / "screen_capture"
            target = stage / key
            target.mkdir(parents=True)
            (target / "private.mp4").write_bytes(b"private")

            with mock.patch(
                "tools.studio.windows_capture_worker.shutil.rmtree",
                side_effect=OSError("locked"),
            ), mock.patch(
                "tools.studio.windows_capture_worker._mark_cleanup_failure",
                return_value=False,
            ), mock.patch("tools.studio.windows_capture_worker.time.sleep"):
                with self.assertRaises(WindowsCaptureError) as failed:
                    discard_windows_capture_outputs(
                        root, run_id=run_id, capture_key=key
                    )
            self.assertEqual(
                failed.exception.error_code, "windows_capture_cleanup_failed"
            )
            self.assertFalse(
                (stage / ".windows-capture-cleanup-required.json").exists()
            )
            ledger = root / "outputs" / "studio" / "windows-capture-cleanup-ledger.json"
            ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(
                ledger_value,
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "run_id": run_id,
                            "capture_key": key,
                            "target_kind": "published",
                        }
                    ],
                },
            )
            serialized = ledger.read_text(encoding="utf-8")
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("private.mp4", serialized)

            # Model a fresh Studio process: only the durable fallback ledger
            # remains. It must block recording until startup cleanup succeeds.
            with capture_worker._CLEANUP_BLOCKED_STAGES_LOCK:
                capture_worker._CLEANUP_BLOCKED_STAGES.clear()
                capture_worker._CLEANUP_BLOCKED_WORKSPACES.clear()
            with mock.patch(
                "tools.studio.windows_capture_worker._resolve_tools"
            ) as resolver:
                with self.assertRaises(WindowsCaptureError) as blocked:
                    generate_windows_capture(
                        root,
                        production_id="TEST_windows_capture",
                        run_id="run_" + "c" * 32,
                        capture_key="D" * 64,
                        payload=REQUEST,
                        expected_tool_identity_digest=DIGEST,
                    )
            self.assertEqual(
                blocked.exception.error_code, "windows_capture_cleanup_required"
            )
            resolver.assert_not_called()

            with mock.patch(
                "tools.studio.windows_capture_worker.shutil.rmtree",
                side_effect=OSError("still locked"),
            ), mock.patch("tools.studio.windows_capture_worker.time.sleep"):
                with self.assertRaises(WindowsCaptureError) as cleanup_failed:
                    cleanup_stale_windows_capture_partials(root)
            self.assertEqual(
                cleanup_failed.exception.error_code,
                "windows_capture_cleanup_failed",
            )
            self.assertTrue(target.is_dir())
            self.assertEqual(
                len(json.loads(ledger.read_text(encoding="utf-8"))["entries"]),
                1,
            )

            result = cleanup_stale_windows_capture_partials(root)
            self.assertEqual(result, {"removed": 1, "failed": 0})
            self.assertFalse(target.exists())
            self.assertEqual(
                json.loads(ledger.read_text(encoding="utf-8"))["entries"], []
            )

    def test_invalid_fallback_ledger_fails_closed_before_capture_or_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            studio = root / "outputs" / "studio"
            studio.mkdir(parents=True)
            ledger = studio / "windows-capture-cleanup-ledger.json"
            ledger.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "entries": [
                            {
                                "run_id": "not-an-exact-run-id",
                                "capture_key": "B" * 64,
                                "target_kind": "published",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch(
                "tools.studio.windows_capture_worker._resolve_tools"
            ) as resolver:
                with self.assertRaises(WindowsCaptureError) as blocked:
                    generate_windows_capture(
                        root,
                        production_id="TEST_windows_capture",
                        run_id="run_" + "c" * 32,
                        capture_key="D" * 64,
                        payload=REQUEST,
                        expected_tool_identity_digest=DIGEST,
                    )
            self.assertEqual(
                blocked.exception.error_code, "windows_capture_cleanup_required"
            )
            resolver.assert_not_called()

            with self.assertRaises(WindowsCaptureError) as cleanup_failed:
                cleanup_stale_windows_capture_partials(root)
            self.assertEqual(
                cleanup_failed.exception.error_code,
                "windows_capture_cleanup_failed",
            )
            self.assertTrue(ledger.is_file())

    def test_both_cleanup_ledgers_denied_latches_workspace_in_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = "run_" + "a" * 32
            key = "B" * 64
            target = (
                root
                / "outputs"
                / "studio"
                / "runs"
                / run_id
                / "screen_capture"
                / key
            )
            target.mkdir(parents=True)
            (target / "private.mp4").write_bytes(b"private")
            with mock.patch(
                "tools.studio.windows_capture_worker.shutil.rmtree",
                side_effect=OSError("locked"),
            ), mock.patch(
                "tools.studio.windows_capture_worker._mark_cleanup_failure",
                return_value=False,
            ), mock.patch(
                "tools.studio.windows_capture_worker._write_fallback_cleanup_ledger",
                side_effect=WindowsCaptureError(
                    "ledger denied", code="windows_capture_cleanup_failed"
                ),
            ), mock.patch("tools.studio.windows_capture_worker.time.sleep"):
                with self.assertRaises(WindowsCaptureError):
                    discard_windows_capture_outputs(
                        root, run_id=run_id, capture_key=key
                    )

            with mock.patch(
                "tools.studio.windows_capture_worker._resolve_tools"
            ) as resolver:
                with self.assertRaises(WindowsCaptureError) as blocked:
                    generate_windows_capture(
                        root,
                        production_id="TEST_windows_capture",
                        run_id="run_" + "c" * 32,
                        capture_key="D" * 64,
                        payload=REQUEST,
                        expected_tool_identity_digest=DIGEST,
                    )
            self.assertEqual(
                blocked.exception.error_code, "windows_capture_cleanup_required"
            )
            resolver.assert_not_called()

    def test_capture_child_environment_is_allowlisted(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "SystemRoot": r"C:\\Windows",
                "PATH": r"C:\\tools",
                "TEMP": r"C:\\Temp",
                "STUDIO_SESSION_TOKEN": "must-not-leak",
                "OPENAI_API_KEY": "must-not-leak",
                "CUSTOM_PROVIDER_SECRET": "must-not-leak",
            },
            clear=True,
        ):
            environment = _clean_environment()
        folded = {key.casefold(): value for key, value in environment.items()}
        self.assertEqual(folded["systemroot"], r"C:\\Windows")
        self.assertEqual(folded["path"], r"C:\\tools")
        self.assertNotIn("studio_session_token", folded)
        self.assertNotIn("openai_api_key", folded)
        self.assertNotIn("custom_provider_secret", folded)
        self.assertEqual(environment["DOTNET_CLI_TELEMETRY_OPTOUT"], "1")

    def test_startup_cleanup_removes_only_exact_capture_partials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = (
                root
                / "outputs"
                / "studio"
                / "runs"
                / ("run_" + "a" * 32)
                / "screen_capture"
            )
            partial = stage / ("." + "B" * 64 + ".partial")
            published = stage / ("C" * 64)
            unrelated = stage / ".keep-me"
            partial.mkdir(parents=True)
            published.mkdir()
            unrelated.mkdir()
            (partial / "capture-master.mkv").write_bytes(b"private")

            result = cleanup_stale_windows_capture_partials(root)

            self.assertEqual(result, {"removed": 1, "failed": 0})
            self.assertFalse(partial.exists())
            self.assertTrue(published.is_dir())
            self.assertTrue(unrelated.is_dir())


if __name__ == "__main__":
    unittest.main()
