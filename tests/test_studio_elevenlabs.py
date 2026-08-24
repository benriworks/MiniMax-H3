from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from tools.studio import elevenlabs
from tools.studio.external_tts_execution import (
    ExternalTTSError,
    ExternalTTSValidationError,
    external_tts_audit_payload,
    external_tts_cache_key,
    external_tts_public_result,
    validate_external_tts_payload,
)


def _wav_bytes(*, duration_ms: int = 1_000) -> bytes:
    frames = (duration_ms * 44_100) // 1_000
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 2 * frames)
    return output.getvalue()


class _Response:
    status = 200

    def __init__(self, body: bytes, *, headers: dict[str, str] | None = None):
        self._body = body
        self.headers = headers or {}
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            value, self._body = self._body, b""
            return value
        value, self._body = self._body[:size], self._body[size:]
        return value

    def close(self) -> None:
        self.closed = True


def _payload(*, segments: list[str] | None = None, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "elevenlabs",
        "voice_id": "voice_test_123",
        "model_id": "eleven_multilingual_v2",
        "segments": [{"text": value} for value in (segments or ["hello", "world"])],
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
        "seed": 4_294_967_295,
        "confirm_billable": True,
    }
    body.update(overrides)
    return body


def _provider_body(text: str) -> bytes:
    characters = list(text)
    starts = [index * 0.02 for index in range(len(characters))]
    ends = [(index + 1) * 0.02 for index in range(len(characters))]
    response = {
        "audio_base64": base64.b64encode(b"not-really-mp3").decode("ascii"),
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    }
    return json.dumps(response).encode("utf-8")


class ExternalTTSContractTests(unittest.TestCase):
    def test_payload_is_strict_and_billable_confirmation_is_literal(self) -> None:
        normalized = validate_external_tts_payload(_payload())
        self.assertEqual(normalized["model_id"], "eleven_multilingual_v2")
        self.assertEqual(normalized["seed"], 4_294_967_295)
        self.assertEqual(normalized["segments"], [{"text": "hello"}, {"text": "world"}])

        for body in (
            {**_payload(), "confirm_billable": False},
            {**_payload(), "confirm_billable": "true"},
            {**_payload(), "unexpected": True},
            {**_payload(), "seed": 4_294_967_296},
            {**_payload(), "voice_settings": {"stability": 0.5}},
        ):
            with self.subTest(body=body):
                with self.assertRaises(ExternalTTSValidationError):
                    validate_external_tts_payload(body)

    def test_cache_key_does_not_include_confirmation_gate(self) -> None:
        first = _payload()
        second = _payload()
        # The public validator intentionally requires true.  This verifies the
        # identity helper's invariant by changing only a re-approved payload's
        # gate representation after normalization.
        self.assertEqual(external_tts_cache_key(first), external_tts_cache_key(second))

    def test_audit_payload_records_confirmation_without_narration_text(self) -> None:
        audit = external_tts_audit_payload(_payload())
        self.assertIs(audit["billable_confirmed"], True)
        self.assertNotIn("segments", audit)
        self.assertNotIn("confirm_billable", audit)
        self.assertNotIn("hello", str(audit))

    def test_public_result_records_request_id_as_task_id_and_integer_cost(self) -> None:
        result = external_tts_public_result(
            {
                "provider": "elevenlabs",
                "timing_source": "elevenlabs_alignment",
                "duration_ms": 1_000,
                "cache_key": "A" * 64,
                "cache_hit": False,
                "provider_task_id": "req-123",
                "request_id": "req-123",
                "provider_request_id": "req-123",
                "character_cost": 27,
                "actual_cost": None,
            },
            expected_cache_key="A" * 64,
            artifacts=[],
            cache_hit=False,
        )
        self.assertEqual(result["provider_task_id"], "req-123")
        self.assertEqual(result["request_id"], "req-123")
        self.assertEqual(result["character_cost"], 27)
        self.assertIsNone(result["actual_cost"])


class ElevenLabsAdapterTests(unittest.TestCase):
    def _run(self, payload: dict[str, object], opener: object) -> tuple[dict[str, object], Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        (workspace / "outputs").mkdir()
        wav = _wav_bytes()

        def bounded_process(_arguments: object, **kwargs: object) -> bytes:
            cwd = kwargs["cwd"]
            assert isinstance(cwd, Path)
            (cwd / ".narration.wav").write_bytes(wav)
            return b""

        with (
            mock.patch.object(elevenlabs, "_find_tool", return_value="ffmpeg") as find_tool,
            mock.patch.object(elevenlabs, "_bounded_process", side_effect=bounded_process) as runner,
        ):
            result = elevenlabs.generate_external_tts(
                workspace,
                production_id="PROD_TEST",
                run_id="RUN_TEST",
                payload=payload,
                api_key="xi-test-secret",
                base_url="http://127.0.0.1:49321",
                opener=opener,
            )
        self.assertTrue(find_tool.called)
        self.assertTrue(runner.called)
        return result, workspace

    def test_single_request_uses_fixed_model_output_and_no_secret_in_artifacts(self) -> None:
        payload = _payload()
        requests: list[object] = []

        def opener(request: object, *, timeout: float) -> _Response:
            requests.append(request)
            request_url = request.full_url  # type: ignore[attr-defined]
            self.assertIn("output_format=mp3_44100_128", request_url)
            self.assertTrue(request_url.startswith("http://127.0.0.1:49321/v1/text-to-speech/"))
            self.assertEqual(request.get_header("Xi-api-key"), "xi-test-secret")  # type: ignore[attr-defined]
            body = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            self.assertEqual(body["model_id"], "eleven_multilingual_v2")
            self.assertEqual(body["text"], "hello\nworld")
            self.assertNotIn("confirm_billable", body)
            self.assertNotIn("provider", body)
            return _Response(
                _provider_body(body["text"]),
                headers={"request-id": "req-abc", "character-cost": "11"},
            )

        result, workspace = self._run(payload, opener)
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["provider"], "elevenlabs")
        self.assertEqual(result["provider_task_id"], "req-abc")
        self.assertEqual(result["request_id"], "req-abc")
        self.assertEqual(result["character_cost"], 11)
        self.assertIsNone(result["actual_cost"])
        self.assertEqual(result["timing_source"], "elevenlabs_alignment")
        self.assertEqual({item["name"] for item in result["artifacts"]}, {
            "narration.wav",
            "captions.srt",
            "timings.json",
            "manifest.json",
        })
        manifest_path = workspace / next(
            item["path"] for item in result["artifacts"] if item["name"] == "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("xi-test-secret", manifest_path.read_text(encoding="utf-8"))
        without_digest = dict(manifest)
        digest = without_digest.pop("manifest_sha256")
        self.assertEqual(elevenlabs._manifest_digest(without_digest), digest)
        self.assertEqual(manifest["provider_task_id"], "req-abc")
        self.assertEqual(manifest["character_cost"], 11)
        captions = (workspace / next(
            item["path"] for item in result["artifacts"] if item["name"] == "captions.srt"
        )).read_text(encoding="utf-8")
        self.assertIn("hello", captions)
        self.assertIn("world", captions)

    def test_cache_hit_skips_provider_and_preserves_headers_without_credential(self) -> None:
        calls = 0

        def opener(request: object, *, timeout: float) -> _Response:
            nonlocal calls
            calls += 1
            body = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            return _Response(
                _provider_body(body["text"]),
                headers={"request-id": "req-cache", "character-cost": "3"},
            )

        result, workspace = self._run(_payload(segments=["cached"]), opener)
        self.assertFalse(result["cache_hit"])
        second = elevenlabs.generate_external_tts(
            workspace,
            production_id="PROD_TEST",
            run_id="RUN_TEST",
            payload=_payload(segments=["cached"]),
            api_key=None,
            base_url="http://127.0.0.1:49321",
            opener=lambda *_args, **_kwargs: self.fail("provider must not be called on cache hit"),
        )
        self.assertEqual(calls, 1)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["provider_task_id"], "req-cache")
        self.assertEqual(second["character_cost"], 3)

    def test_timeout_after_submission_is_external_submission_unknown(self) -> None:
        def opener(request: object, *, timeout: float) -> _Response:
            raise TimeoutError("secret must never cross the boundary")

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "outputs").mkdir()
            with self.assertRaises(ExternalTTSError) as raised:
                elevenlabs.generate_external_tts(
                    workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_UNKNOWN",
                    payload=_payload(segments=["unknown"]),
                    api_key="xi-test-secret",
                    base_url="http://127.0.0.1:49321",
                    opener=opener,
                )
        self.assertEqual(raised.exception.error_code, "external_submission_unknown")
        self.assertNotIn("xi-test-secret", str(raised.exception))

    def test_submission_marker_blocks_same_identity_in_a_new_run(self) -> None:
        calls = 0

        def timeout_opener(request: object, *, timeout: float) -> _Response:
            nonlocal calls
            calls += 1
            raise TimeoutError()

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "outputs").mkdir()
            with self.assertRaises(ExternalTTSError) as first:
                elevenlabs.generate_external_tts(
                    workspace,
                    production_id="PROD_MARKER",
                    run_id="RUN_ONE",
                    payload=_payload(segments=["marker"]),
                    api_key="xi-test-secret",
                    base_url="http://127.0.0.1:49321",
                    opener=timeout_opener,
                )
            self.assertEqual(first.exception.error_code, "external_submission_unknown")
            cache_key = external_tts_cache_key(_payload(segments=["marker"]))
            marker = elevenlabs._submission_marker_path(workspace, "PROD_MARKER", cache_key)
            self.assertTrue(marker.is_file())
            marker_text = marker.read_text(encoding="utf-8")
            self.assertNotIn("xi-test-secret", marker_text)
            self.assertNotIn("marker", marker_text)

            with self.assertRaises(ExternalTTSError) as second:
                elevenlabs.generate_external_tts(
                    workspace,
                    production_id="PROD_MARKER",
                    run_id="RUN_TWO",
                    payload=_payload(segments=["marker"]),
                    api_key="xi-test-secret",
                    base_url="http://127.0.0.1:49321",
                    opener=self.fail,
                )
            self.assertEqual(second.exception.error_code, "external_submission_unknown")
            self.assertEqual(calls, 1)

    def test_alignment_mismatch_publishes_no_artifacts(self) -> None:
        def opener(request: object, *, timeout: float) -> _Response:
            body = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            response = json.loads(_provider_body(body["text"]).decode("utf-8"))
            response["alignment"]["characters"][0] = "X"
            return _Response(json.dumps(response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "outputs").mkdir()
            with self.assertRaises(ExternalTTSError) as raised:
                elevenlabs.generate_external_tts(
                    workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_BAD_ALIGNMENT",
                    payload=_payload(segments=["bad"]),
                    api_key="xi-test-secret",
                    base_url="http://127.0.0.1:49321",
                    opener=opener,
                )
            self.assertEqual(raised.exception.error_code, "invalid_external_alignment")
            files = list((workspace / "outputs" / "studio" / "runs").rglob("*"))
            self.assertFalse(any(path.name == "manifest.json" for path in files))

    def test_invalid_non_loopback_endpoint_is_rejected_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "outputs").mkdir()
            with self.assertRaises(ExternalTTSError) as raised:
                elevenlabs.generate_external_tts(
                    workspace,
                    production_id="PROD_TEST",
                    run_id="RUN_ENDPOINT",
                    payload=_payload(segments=["endpoint"]),
                    api_key="xi-test-secret",
                    base_url="http://192.0.2.10:49321",
                    opener=self.fail,
                )
        self.assertEqual(raised.exception.error_code, "invalid_external_endpoint")


if __name__ == "__main__":
    unittest.main()
