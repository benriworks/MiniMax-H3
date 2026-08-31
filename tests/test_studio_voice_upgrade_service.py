from __future__ import annotations

import http.client
import io
import json
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

from tests.test_studio_backend import PRODUCTION_ID, WorkspaceFixture
from tools.studio import elevenlabs
from tools.studio.server import create_server
from tools.studio.service import StudioService


TEXTS = ("フック", "メッセージ", "案内")


def _external_payload() -> dict[str, object]:
    return {
        "provider": "elevenlabs",
        "voice_id": "voice_upgrade_e2e",
        "model_id": "eleven_multilingual_v2",
        "segments": [{"text": text} for text in TEXTS],
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


def _schedule() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_duration_ms": 3_000,
        "scenes": [
            {"role": role, "start_ms": start, "text": text}
            for role, start, text in zip(
                ("HOOK", "MESSAGE", "CTA"),
                (0, 1_000, 2_000),
                TEXTS,
                strict=True,
            )
        ],
    }


def _provider_response(text: str) -> dict[str, object]:
    characters = list(text)
    return {
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": [
                index * 0.02 for index in range(len(characters))
            ],
            "character_end_times_seconds": [
                (index + 1) * 0.02 for index in range(len(characters))
            ],
        }
    }


def _wav_bytes(duration_ms: int = 1_000) -> bytes:
    frames = (duration_ms * 44_100) // 1_000
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x01\x00" * 2 * frames)
    return output.getvalue()


class VoiceUpgradeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        self.service.close()
        self.fixture.close()

    def test_paid_source_is_locally_aligned_registered_and_admitted_to_assembly(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
                "execution_profile": "elevenlabs_tts",
            },
        )
        run_id = str(created["run"]["id"])
        self.service.approve_run(
            run_id,
            {
                "approved": True,
                "max_cost": {"amount": "1.00", "currency": "USD"},
                "actor": "voice-upgrade-test",
            },
        )
        provider_calls = 0

        def fake_provider_request(
            _base_url: str,
            _api_key: str,
            payload: dict[str, object],
            **_kwargs: object,
        ) -> tuple[dict[str, object], bytes, str, int]:
            nonlocal provider_calls
            provider_calls += 1
            text = "\n".join(
                str(segment["text"])
                for segment in payload["segments"]  # type: ignore[index]
            )
            return _provider_response(text), b"mock-provider-mp3", "req-upgrade-1", 12

        def fake_ffmpeg(_arguments: object, **kwargs: object) -> bytes:
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
            ),
            mock.patch.object(elevenlabs, "_find_tool", return_value="mock-ffmpeg"),
            mock.patch.object(elevenlabs, "_bounded_process", side_effect=fake_ffmpeg),
        ):
            source = self.service.execute_external_narration(
                run_id, _external_payload()
            )
            source_job = self.service.jobs.wait(source["id"], timeout=10)
        self.assertIsNotNone(source_job)
        assert source_job is not None and isinstance(source_job.get("result"), dict)
        self.assertEqual(source_job["status"], "succeeded")
        source_attempt_id = str(source_job["result"]["stage_attempt_id"])

        # No provider/secret patch is active here.  Success therefore proves
        # the upgrade is a local-only transform of the registered source.
        queued = self.service.execute_voice_upgrade(
            run_id,
            {
                "schema_version": 1,
                "source_attempt_id": source_attempt_id,
                "schedule": _schedule(),
            },
        )
        completed = self.service.jobs.wait(queued["id"], timeout=10)
        self.assertIsNotNone(completed)
        assert completed is not None and isinstance(completed.get("result"), dict)
        self.assertEqual(completed["status"], "succeeded")
        result = completed["result"]
        self.assertEqual(result["provider"], "local_voice_upgrade")
        self.assertEqual(result["actual_cost"], 0)
        self.assertEqual(result["segment_start_ms"], [0, 1_000, 2_000])
        self.assertEqual(len(result["artifacts"]), 4)
        self.assertEqual(provider_calls, 1)
        resolve_secret.assert_called_once_with("elevenlabs")

        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        resolved = self.service._validated_assembly_inputs(
            self.service.run(run_id),
            {
                "video_artifact_id": video["id"],
                "narration_attempt_id": result["stage_attempt_id"],
            },
        )
        self.assertEqual(
            resolved["narration_attempt"]["id"], result["stage_attempt_id"]
        )
        self.assertEqual(resolved["narration_wav"].name, "narration.wav")


class VoiceUpgradeHTTPRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "voice-upgrade-session-token-at-least-32-characters"
        self.server = create_server(
            self.fixture.root,
            host="127.0.0.1",
            port=0,
            static_dir="studio/dist",
            session_token=self.token,
            initial_refresh=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.fixture.close()

    def test_route_is_bound_and_fails_closed_without_succeeded_source(self) -> None:
        created = self.server.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "script"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
                "execution_profile": "elevenlabs_tts",
            },
        )
        body = json.dumps(
            {
                "schema_version": 1,
                "source_attempt_id": "attempt_" + "0" * 32,
                "schedule": _schedule(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.connection.request(
            "POST",
            f"/api/runs/{created['run']['id']}/execute-voice-upgrade",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 422)
        self.assertEqual(payload["error"]["code"], "voice_upgrade_source_required")


if __name__ == "__main__":
    unittest.main()
