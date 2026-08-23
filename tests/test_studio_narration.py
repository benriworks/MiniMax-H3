from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from tools.studio.narration import (
    NarrationError,
    NarrationPreflightError,
    NarrationSynthesisError,
    generate_local_narration,
    preflight_local_sapi,
)
from tools.studio import narration as narration_module
from tools.studio.security import SecurityError


def wav_bytes(*, frames: int, sample_rate: int = 1_000, value: int = 0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((int(value).to_bytes(2, "little", signed=True)) * frames)
    return output.getvalue()


class FakeSynthesizer:
    def __init__(self, durations: list[int] | None = None) -> None:
        self.calls: list[tuple[str, str | None, int]] = []
        self.durations = durations or [500, 750]

    def synthesize(self, text: str, *, voice: str | None, rate: int) -> bytes:
        self.calls.append((text, voice, rate))
        return wav_bytes(frames=self.durations[len(self.calls) - 1])


class NarrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_generates_concatenated_wav_captions_timings_and_manifest(self) -> None:
        fake = FakeSynthesizer()
        result = generate_local_narration(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            payload={
                "segments": [{"text": "CLAUDE.mdを確認"}, {"text": "次に実行します"}],
                "voice": "Test Voice",
                "rate": 2,
                "pronunciations": [{"source": "CLAUDE.md", "target": "クロード エムディー"}],
            },
            synthesizer=fake,
        )
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["provider"], "windows_sapi")
        self.assertIsNone(result["provider_task_id"])
        self.assertEqual(result["actual_cost"], 0)
        self.assertEqual(result["duration_ms"], 1_250)
        self.assertEqual([call[0] for call in fake.calls], ["クロード エムディーを確認", "次に実行します"])
        self.assertEqual(len(result["artifacts"]), 4)
        artifact_paths = {artifact["name"]: self.workspace / artifact["path"] for artifact in result["artifacts"]}
        with wave.open(str(artifact_paths["narration.wav"]), "rb") as handle:
            self.assertEqual(handle.getnframes(), 1_250)
            self.assertEqual(handle.getframerate(), 1_000)
        captions = artifact_paths["captions.srt"].read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:00,500", captions)
        self.assertIn("00:00:00,500 --> 00:00:01,250", captions)
        self.assertIn("CLAUDE.mdを確認", captions)
        timings = json.loads(artifact_paths["timings.json"].read_text(encoding="utf-8"))
        self.assertEqual(timings["segments"][1]["start_ms"], 500)
        manifest = json.loads(artifact_paths["manifest.json"].read_text(encoding="utf-8"))
        self.assertEqual(manifest["pronunciations"][0]["source"], "CLAUDE.md")
        self.assertEqual(manifest["pronunciations"][0]["target"], "クロード エムディー")
        self.assertEqual(manifest["manifest_sha256"], hashlib.sha256(
            (json.dumps({key: value for key, value in manifest.items() if key != "manifest_sha256"}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode("utf-8")
        ).hexdigest().upper())

    def test_cache_hit_revalidates_all_hashes(self) -> None:
        first_fake = FakeSynthesizer()
        first = generate_local_narration(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_CACHE",
            payload={"segments": [{"text": "一つ"}, {"text": "二つ"}]},
            synthesizer=first_fake,
        )
        second_fake = FakeSynthesizer([100, 100])
        second = generate_local_narration(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_CACHE",
            payload={"segments": [{"text": "一つ"}, {"text": "二つ"}]},
            synthesizer=second_fake,
        )
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second_fake.calls, [])
        narration = next(item for item in first["artifacts"] if item["name"] == "narration.wav")
        (self.workspace / narration["path"]).write_bytes(b"tampered")
        third_fake = FakeSynthesizer([200, 300])
        third = generate_local_narration(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_CACHE",
            payload={"segments": [{"text": "一つ"}, {"text": "二つ"}]},
            synthesizer=third_fake,
        )
        self.assertFalse(third["cache_hit"])
        self.assertEqual(len(third_fake.calls), 2)
        manifest_path = self.workspace / next(
            item for item in third["artifacts"] if item["name"] == "manifest.json"
        )["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["duration_ms"] += 1
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        fourth_fake = FakeSynthesizer([300, 300])
        fourth = generate_local_narration(
            self.workspace,
            production_id="PROD_TEST",
            run_id="RUN_CACHE",
            payload={"segments": [{"text": "一つ"}, {"text": "二つ"}]},
            synthesizer=fourth_fake,
        )
        self.assertFalse(fourth["cache_hit"])
        self.assertEqual(len(fourth_fake.calls), 2)

    def test_validation_is_fail_closed(self) -> None:
        invalid_payloads = (
            {"segments": []},
            {"segments": [{"text": "ok\nnot allowed"}]},
            {"segments": [{"text": "ok"}], "rate": 11},
            {"segments": [{"text": "ok"}], "voice": "bad\nvoice"},
            {"segments": [{"text": "ok"}], "pronunciations": [{"source": "x", "target": "y"}, {"source": "x", "target": "z"}]},
            {"segments": [{"text": "ok"}], "unexpected": True},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(NarrationError):
                generate_local_narration(
                    self.workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_VALIDATION",
                    payload=payload,
                    synthesizer=FakeSynthesizer(),
                )
        with self.assertRaises(SecurityError):
            generate_local_narration(
                self.workspace,
                production_id="../outside",
                run_id="RUN_VALIDATION",
                payload={"segments": [{"text": "ok"}]},
                synthesizer=FakeSynthesizer(),
            )

    def test_oversized_or_overlong_wav_is_rejected_before_publish(self) -> None:
        generated = wav_bytes(frames=200)
        with mock.patch.object(
            narration_module, "MAX_SEGMENT_WAV_BYTES", len(generated) - 1
        ):
            with self.assertRaisesRegex(NarrationSynthesisError, "too large"):
                generate_local_narration(
                    self.workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_OVERSIZED",
                    payload={"segments": [{"text": "oversized"}]},
                    synthesizer=lambda *_args, **_kwargs: generated,
                )

        with mock.patch.object(narration_module, "MAX_NARRATION_DURATION_MS", 100):
            with self.assertRaisesRegex(NarrationSynthesisError, "duration"):
                generate_local_narration(
                    self.workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_OVERLONG",
                    payload={"segments": [{"text": "overlong"}]},
                    synthesizer=lambda *_args, **_kwargs: generated,
                )

    def test_preflight_has_clear_non_windows_error(self) -> None:
        with mock.patch("tools.studio.narration.os.name", "posix"):
            with self.assertRaisesRegex(NarrationPreflightError, "Windows SAPI"):
                preflight_local_sapi()


if __name__ == "__main__":
    unittest.main()
