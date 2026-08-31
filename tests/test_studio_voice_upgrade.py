from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

from tools.studio.security import canonical_json
from tools.studio.voice_upgrade import (
    VoiceUpgradeError,
    align_external_tts_to_scene_schedule,
    validate_scene_schedule,
    voice_upgrade_cache_key,
    voice_upgrade_schedule_digest,
)


TEXTS = ("フック", "メッセージ", "案内")
SOURCE_INTERVALS = ((100, 250), (300, 600), (650, 750))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _wav_bytes(*, sample_width: int = 2, duration_ms: int = 1_000) -> bytes:
    frame_count = (duration_ms * 44_100) // 1_000
    if sample_width == 2:
        frames = b"".join(
            int((index % 30_000) + 1).to_bytes(2, "little", signed=True)
            for index in range(frame_count)
        )
    else:
        frames = bytes((index % 255) + 1 for index in range(frame_count))
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(sample_width)
        handle.setframerate(44_100)
        handle.writeframes(frames)
    return output.getvalue()


def _source_timings(*, sample_width: int = 2) -> dict[str, object]:
    characters: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    rows: list[dict[str, object]] = []
    cursor = 0
    for index, (text, (segment_start, segment_end)) in enumerate(
        zip(TEXTS, SOURCE_INTERVALS, strict=True)
    ):
        step = (segment_end - segment_start) // len(text)
        for character_index, character in enumerate(text):
            start = segment_start + character_index * step
            end = segment_end if character_index == len(text) - 1 else start + step
            characters.append(character)
            starts.append(start / 1_000)
            ends.append(end / 1_000)
        rows.append(
            {
                "index": index,
                "text": text,
                "start_ms": segment_start,
                "end_ms": segment_end,
                "duration_ms": segment_end - segment_start,
                "character_start_index": cursor,
                "character_end_index": cursor + len(text),
                "character_count": len(text),
            }
        )
        cursor += len(text)
        if index < len(TEXTS) - 1:
            characters.append("\n")
            starts.append(segment_end / 1_000)
            ends.append((segment_end + 25) / 1_000)
            cursor += 1
    return {
        "schema_version": 1,
        "implementation_version": "elevenlabs-timestamps-v1",
        "provider": "elevenlabs",
        "timing_source": "elevenlabs_alignment",
        "duration_ms": 1_000,
        "sample_rate": 44_100,
        "channels": 1,
        "sample_width": sample_width,
        "segments": rows,
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    }


def _schedule(*, starts: tuple[int, int, int] = (0, 1_000, 2_000)) -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_duration_ms": 3_000,
        "scenes": [
            {"role": role, "start_ms": start, "text": text}
            for role, start, text in zip(
                ("HOOK", "MESSAGE", "CTA"), starts, TEXTS, strict=True
            )
        ],
    }


class VoiceUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.source = self.workspace / "source"
        self.source.mkdir()
        self.output_root = self.workspace / "aligned"
        self.wav_path = self.source / "narration.wav"
        self.timings_path = self.source / "timings.json"
        self._write_sources()

    def _write_sources(
        self,
        *,
        wav_bytes: bytes | None = None,
        timings: dict[str, object] | None = None,
    ) -> tuple[str, str]:
        wav_data = wav_bytes if wav_bytes is not None else _wav_bytes()
        timing_data = (
            canonical_json(timings if timings is not None else _source_timings()) + "\n"
        ).encode("utf-8")
        self.wav_path.write_bytes(wav_data)
        self.timings_path.write_bytes(timing_data)
        return _sha256(wav_data), _sha256(timing_data)

    def _align(
        self,
        *,
        schedule: dict[str, object] | None = None,
        wav_sha256: str | None = None,
        timings_sha256: str | None = None,
    ) -> dict[str, object]:
        return align_external_tts_to_scene_schedule(
            self.workspace,
            source_wav=self.wav_path,
            source_timings=self.timings_path,
            output_root=self.output_root,
            source_wav_sha256=wav_sha256 or _sha256(self.wav_path.read_bytes()),
            source_timings_sha256=timings_sha256
            or _sha256(self.timings_path.read_bytes()),
            schedule=schedule or _schedule(),
        )

    def test_aligns_provider_segments_to_exact_scenes_and_reuses_cache(self) -> None:
        expected_schedule = _schedule()
        result = self._align(schedule=expected_schedule)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["segment_start_ms"], [0, 1_000, 2_000])
        self.assertEqual(
            result["schedule_sha256"], voice_upgrade_schedule_digest(expected_schedule)
        )
        self.assertEqual(
            result["cache_key"],
            voice_upgrade_cache_key(
                expected_schedule,
                source_wav_sha256=_sha256(self.wav_path.read_bytes()),
                source_timings_sha256=_sha256(self.timings_path.read_bytes()),
            ),
        )

        artifacts = {
            item["name"]: self.workspace / item["path"]
            for item in result["artifacts"]
        }
        self.assertEqual(
            set(artifacts),
            {"narration.wav", "captions.srt", "timings.json", "manifest.json"},
        )
        with wave.open(str(artifacts["narration.wav"]), "rb") as aligned_handle:
            self.assertEqual(aligned_handle.getframerate(), 44_100)
            self.assertEqual(aligned_handle.getsampwidth(), 2)
            self.assertEqual(aligned_handle.getnframes(), 3 * 44_100)
            aligned_frames = aligned_handle.readframes(aligned_handle.getnframes())
        with wave.open(str(self.wav_path), "rb") as source_handle:
            source_frames = source_handle.readframes(source_handle.getnframes())
        source_start = (100 * 44_100 + 999) // 1_000
        source_end = (250 * 44_100 + 999) // 1_000
        self.assertEqual(
            aligned_frames[: (source_end - source_start) * 2],
            source_frames[source_start * 2 : source_end * 2],
        )
        self.assertEqual(
            aligned_frames[(source_end - source_start) * 2 : 44_100 * 2],
            b"\x00" * ((44_100 - (source_end - source_start)) * 2),
        )

        captions = artifacts["captions.srt"].read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:00,150\nフック", captions)
        self.assertIn("00:00:01,000 --> 00:00:01,300\nメッセージ", captions)
        self.assertIn("00:00:02,000 --> 00:00:02,100\n案内", captions)
        timings = json.loads(artifacts["timings.json"].read_text(encoding="utf-8"))
        self.assertEqual(
            [row["start_ms"] for row in timings["segments"]], [0, 1_000, 2_000]
        )
        self.assertEqual(
            timings["timing_policy"]["scene_start_ms"], [0, 1_000, 2_000]
        )
        for artifact in result["artifacts"]:
            path = self.workspace / artifact["path"]
            self.assertEqual(path.stat().st_size, artifact["bytes"])
            self.assertEqual(_sha256(path.read_bytes()), artifact["sha256"])

        again = self._align(schedule=expected_schedule)
        self.assertTrue(again["cache_hit"])
        self.assertEqual(again["cache_key"], result["cache_key"])
        self.assertEqual(again["schedule_sha256"], result["schedule_sha256"])

    def test_schedule_is_closed_to_hook_message_cta_and_exact_fields(self) -> None:
        for invalid in (
            {**_schedule(), "extra": True},
            {
                **_schedule(),
                "scenes": [
                    {**scene, "role": "hook" if index == 0 else scene["role"]}
                    for index, scene in enumerate(_schedule()["scenes"])
                ],
            },
            {
                **_schedule(),
                "scenes": [
                    {**scene, "start_ms": 1 if index == 0 else scene["start_ms"]}
                    for index, scene in enumerate(_schedule()["scenes"])
                ],
            },
            {
                **_schedule(),
                "scenes": [
                    {**scene, "unexpected": True} if index == 1 else scene
                    for index, scene in enumerate(_schedule()["scenes"])
                ],
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(VoiceUpgradeError) as caught:
                    validate_scene_schedule(invalid)
                self.assertEqual(caught.exception.error_code, "invalid_voice_upgrade_schedule")

    def test_rejects_text_or_alignment_metadata_mismatch(self) -> None:
        mismatched = copy.deepcopy(_schedule())
        mismatched["scenes"][1]["text"] = "別のメッセージ"
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align(schedule=mismatched)
        self.assertEqual(caught.exception.error_code, "voice_upgrade_source_mismatch")

        timings = _source_timings()
        timings["sample_rate"] = 48_000
        _, timing_hash = self._write_sources(timings=timings)
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align(timings_sha256=timing_hash)
        self.assertEqual(caught.exception.error_code, "voice_upgrade_source_mismatch")

    def test_rejects_overlap_into_next_scene_or_output_end(self) -> None:
        for starts in ((0, 100, 2_000), (0, 1_000, 2_950)):
            with self.subTest(starts=starts):
                with self.assertRaises(VoiceUpgradeError) as caught:
                    self._align(schedule=_schedule(starts=starts))
                self.assertEqual(caught.exception.error_code, "voice_upgrade_segment_overlap")

    def test_rejects_unsupported_wav_before_publication(self) -> None:
        wav_hash, timing_hash = self._write_sources(
            wav_bytes=_wav_bytes(sample_width=1),
            timings=_source_timings(sample_width=1),
        )
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align(wav_sha256=wav_hash, timings_sha256=timing_hash)
        self.assertEqual(caught.exception.error_code, "unsupported_voice_upgrade_wav")
        self.assertFalse(self.output_root.exists())

    def test_rejects_stale_source_hashes_and_tampered_cache(self) -> None:
        wav_hash = _sha256(self.wav_path.read_bytes())
        timing_hash = _sha256(self.timings_path.read_bytes())
        self.wav_path.write_bytes(self.wav_path.read_bytes() + b"altered")
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align(wav_sha256=wav_hash, timings_sha256=timing_hash)
        self.assertEqual(caught.exception.error_code, "source_hash_changed")

        self._write_sources()
        stale_timing_hash = _sha256(self.timings_path.read_bytes())
        self.timings_path.write_bytes(self.timings_path.read_bytes() + b" ")
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align(timings_sha256=stale_timing_hash)
        self.assertEqual(caught.exception.error_code, "source_hash_changed")

        self._write_sources()
        first = self._align()
        narration = next(
            self.workspace / item["path"]
            for item in first["artifacts"]
            if item["name"] == "narration.wav"
        )
        narration.write_bytes(b"tampered")
        with self.assertRaises(VoiceUpgradeError) as caught:
            self._align()
        self.assertEqual(
            caught.exception.error_code, "voice_upgrade_cache_integrity_failed"
        )


if __name__ == "__main__":
    unittest.main()
