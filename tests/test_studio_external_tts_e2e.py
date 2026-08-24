from __future__ import annotations

import io
import unittest
import wave
from pathlib import Path
from unittest import mock

from tests.test_studio_backend import PRODUCTION_ID, WorkspaceFixture
from tools.studio import elevenlabs
from tools.studio.service import StudioService


def _payload() -> dict[str, object]:
    return {
        "provider": "elevenlabs",
        "voice_id": "voice_e2e_test",
        "model_id": "eleven_multilingual_v2",
        "segments": [{"text": "External Studio E2E narration"}],
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
        "seed": 17,
        "confirm_billable": True,
    }


def _provider_response(text: str) -> dict[str, object]:
    characters = list(text)
    starts = [index * 0.02 for index in range(len(characters))]
    ends = [(index + 1) * 0.02 for index in range(len(characters))]
    return {
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        }
    }


def _wav_bytes(duration_ms: int = 1_000) -> bytes:
    frames = (duration_ms * 44_100) // 1_000
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 2 * frames)
    return output.getvalue()


class ExternalTTSE2ETests(unittest.TestCase):
    """Exercise the billable Studio path without contacting ElevenLabs."""

    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def test_approved_external_narration_succeeds_registers_and_reuses_cache(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                # ``script`` expands to narration -> captions -> assembly -> qc,
                # so the resulting run also admits the downstream assembly gate.
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": "1.25", "currency": "USD"},
                "execution_profile": "elevenlabs_tts",
            },
        )
        run = created["run"]
        run_id = str(run["id"])
        self.assertEqual(run["execution_profile"], "elevenlabs_tts")
        self.assertEqual(run["estimated_cost"], {"amount": "1.25", "currency": "USD"})
        self.assertEqual(
            run["requested_stages"], ["narration", "captions", "assembly", "qc"]
        )

        approved = self.service.approve_run(
            run_id,
            {
                "approved": True,
                "max_cost": {"amount": "1.25", "currency": "USD"},
                "actor": "e2e-test",
            },
        )
        self.assertEqual(approved["latest_approval"]["decision"], "approved")
        self.assertEqual(
            approved["latest_approval"]["approved_max"],
            {"amount": "1.25", "currency": "USD"},
        )

        provider_calls: list[dict[str, object]] = []

        def fake_provider_request(
            _base_url: str,
            api_key: str,
            payload: dict[str, object],
            **_kwargs: object,
        ) -> tuple[dict[str, object], bytes, str, int]:
            # This seam replaces the provider transport itself.  No HTTP
            # client, socket, or paid ElevenLabs request is exercised.
            provider_calls.append({"api_key": api_key, "payload": payload})
            text = "\n".join(
                str(segment["text"])
                for segment in payload["segments"]  # type: ignore[index]
            )
            return _provider_response(text), b"mock-provider-mp3", "req-e2e-001", 28

        def fake_ffmpeg(_arguments: object, **kwargs: object) -> bytes:
            # ``generate_external_tts`` still performs its media and artifact
            # validation; only the process boundary is replaced.
            cwd = kwargs["cwd"]
            assert isinstance(cwd, Path)
            (cwd / ".narration.wav").write_bytes(_wav_bytes())
            return b""

        with (
            mock.patch.object(
                self.service.secret_store, "resolve", return_value="mock-api-key"
            ) as resolve_secret,
            mock.patch.object(
                elevenlabs, "_provider_request", side_effect=fake_provider_request
            ) as provider_request,
            mock.patch.object(elevenlabs, "_find_tool", return_value="mock-ffmpeg"),
            mock.patch.object(elevenlabs, "_bounded_process", side_effect=fake_ffmpeg),
        ):
            first_queued = self.service.execute_external_narration(run_id, _payload())
            first_job = self.service.jobs.wait(first_queued["id"], timeout=10)
            self.assertIsNotNone(first_job)
            assert first_job is not None

            self.assertEqual(first_job["status"], "succeeded")
            self.assertIsNone(first_job["error"])
            first_result = first_job["result"]
            self.assertIsInstance(first_result, dict)
            assert isinstance(first_result, dict)
            first_attempt_id = str(first_result["stage_attempt_id"])
            first_attempt = self.service.database.get_stage_attempt(first_attempt_id)
            self.assertIsNotNone(first_attempt)
            assert first_attempt is not None
            self.assertEqual(first_attempt["status"], "succeeded")
            self.assertEqual(first_attempt["job_id"], first_job["id"])

            # Re-submit the exact approved identity.  The service-level cache
            # must return the byte-verified result without another provider
            # call or another credential lookup.
            second_queued = self.service.execute_external_narration(run_id, _payload())
            second_job = self.service.jobs.wait(second_queued["id"], timeout=10)
            self.assertIsNotNone(second_job)
            assert second_job is not None
            self.assertEqual(second_job["status"], "succeeded")
            second_result = second_job["result"]
            self.assertIsInstance(second_result, dict)
            assert isinstance(second_result, dict)

        self.assertEqual(provider_request.call_count, 1)
        resolve_secret.assert_called_once_with("elevenlabs")
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(provider_calls[0]["api_key"], "mock-api-key")

        self.assertIsInstance(first_attempt["result"], dict)
        assert isinstance(first_attempt["result"], dict)
        self.assertEqual(first_attempt["result"]["provider_task_id"], "req-e2e-001")
        self.assertEqual(first_attempt["result"]["request_id"], "req-e2e-001")
        self.assertEqual(first_attempt["result"]["character_cost"], 28)
        self.assertIsNone(first_attempt["result"]["actual_cost"])
        self.assertEqual(first_attempt["result"]["timing_source"], "elevenlabs_alignment")

        for result in (first_result, second_result):
            self.assertEqual(result["provider"], "elevenlabs")
            self.assertEqual(result["provider_task_id"], "req-e2e-001")
            self.assertEqual(result["request_id"], "req-e2e-001")
            self.assertEqual(result["character_cost"], 28)
            self.assertIsNone(result["actual_cost"])
            self.assertEqual(result["timing_source"], "elevenlabs_alignment")
            self.assertEqual(len(result["artifacts"]), 4)

        first_artifacts = first_result["artifacts"]
        second_artifacts = second_result["artifacts"]
        self.assertIsInstance(first_artifacts, list)
        self.assertIsInstance(second_artifacts, list)
        assert isinstance(first_artifacts, list)
        assert isinstance(second_artifacts, list)
        expected_names = {"narration.wav", "captions.srt", "timings.json", "manifest.json"}
        self.assertEqual({item["name"] for item in first_artifacts}, expected_names)
        self.assertEqual(
            {item["id"] for item in second_artifacts},
            {item["id"] for item in first_artifacts},
        )
        self.assertTrue(second_result["cache_hit"])
        self.assertEqual(second_result["cache_source_attempt_id"], first_attempt_id)

        for item in first_artifacts:
            registered = self.service.artifact(str(item["id"]))
            self.assertIsNotNone(registered)
            assert registered is not None
            self.assertTrue(registered["available"])
            self.assertEqual(registered["origin"], "studio")
            self.assertEqual(registered["name"], item["name"])
            self.assertTrue(
                (self.fixture.root / registered["rel_path"]).is_file(),
                registered["rel_path"],
            )

        # The same approved run can now resolve its external narration as a
        # valid local-assembly input.  This is the downstream eligibility
        # boundary; no assembly process is needed to prove it here.
        detail = self.service.production_detail(PRODUCTION_ID)
        self.assertIsNotNone(detail)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        resolved_inputs = self.service._validated_assembly_inputs(
            self.service.run(run_id),
            {
                "video_artifact_id": video["id"],
                "narration_attempt_id": first_attempt_id,
            },
        )
        self.assertEqual(resolved_inputs["narration_wav"].name, "narration.wav")
        self.assertEqual(resolved_inputs["captions_srt"].name, "captions.srt")
        self.assertEqual(resolved_inputs["narration_attempt"]["id"], first_attempt_id)


if __name__ == "__main__":
    unittest.main()
