import base64
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import wave

SCRIPT = Path(__file__).resolve().parents[1] / 'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py'
spec = importlib.util.spec_from_file_location('gemini_voice_trial', SCRIPT)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def response(pcm=None, mime='audio/L16;codec=pcm;rate=24000'):
    pcm = pcm if pcm is not None else b'\x01\x02' * 60000
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
        {'inlineData': {'mimeType': mime, 'data': base64.b64encode(pcm).decode()}}]}}]}


class GeminiVoiceTrialTests(unittest.TestCase):
    def test_fixed_voice_only_request_and_trial_size_limit(self):
        request = trial.payload('ドッツの声を試します。', 'Kore')
        self.assertEqual(request['generationConfig']['responseModalities'], ['AUDIO'])
        self.assertEqual(request['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'], 'Kore')
        self.assertNotIn('key', json.dumps(request).lower())
        for text, voice in [('', 'Kore'), ('文' * 301, 'Kore'), ('文', 'custom_voice')]:
            with self.assertRaises(ValueError):
                trial.payload(text, voice)

    def test_pcm_is_wrapped_as_real_24khz_mono_wav(self):
        data, seconds = trial.decode_audio(response())
        with wave.open(io.BytesIO(data), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
            self.assertEqual(wav.getnframes(), 60000)
        self.assertEqual(seconds, 2.5)

    def test_incomplete_wrong_format_and_broken_audio_are_rejected(self):
        for bad in [response(b'x'), response(b'\x00\x00'), response(mime='audio/mp3'),
                    {'candidates': []}, {'candidates': [{'finishReason': 'MAX_TOKENS'}]}]:
            with self.assertRaises(ValueError):
                trial.decode_audio(bad)

    def test_short_scene_speech_requires_explicit_duration_policy(self):
        short=response(b'\x01\x02'*24000)
        with self.assertRaises(ValueError):trial.decode_audio(short)
        data,seconds=trial.decode_audio(short,minimum_seconds=.2)
        self.assertEqual(seconds,1)
        self.assertGreater(len(data),48000)
        with self.assertRaises(ValueError):trial.decode_audio(short,minimum_seconds=0)

    def test_auth_error_never_leaks_secret_and_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(trial, 'ROOT', Path(temp)):
            out = Path(temp) / 'trial';out.mkdir()
            secret = 'mock-private-key-not-for-logs'
            body = json.dumps({'error': {'message': secret, 'details': [{'reason': 'API_KEY_INVALID'}]}}).encode()
            failure = urllib.error.HTTPError(trial.API, 400, secret, {}, io.BytesIO(body))
            opener = MagicMock();opener.open.side_effect = failure
            with patch.dict('os.environ', {'GEMINI_API_KEY': secret}), patch.object(trial.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(RuntimeError, 'api_key_invalid'):
                    trial.synthesize(out, '試聴です。', 'Kore')
                with self.assertRaisesRegex(RuntimeError, 'do not automatically'):
                    trial.synthesize(out, '試聴です。', 'Kore')
            self.assertEqual(opener.open.call_count, 1)
            for file in (out / 'Kore').glob('*.json'):
                self.assertNotIn(secret, file.read_text(encoding='utf-8'))
            self.assertFalse((out / 'Kore/verified.json').exists())

    def test_verified_audio_reuses_only_matching_transcript_and_bytes(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(trial, 'ROOT', Path(temp)):
            out = Path(temp) / 'trial';out.mkdir()
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(response()).encode()
            with patch.dict('os.environ', {'GEMINI_API_KEY': 'mock-private-key'}), patch.object(trial.urllib.request, 'build_opener', return_value=opener), patch.object(trial.subprocess, 'run'):
                first = trial.synthesize(out, '声を試します。', 'Aoede')
                self.assertEqual(first, trial.synthesize(out, '声を試します。', 'Aoede'))
                self.assertEqual(opener.open.call_count, 1)
                with self.assertRaisesRegex(ValueError, 'transcript changed'):
                    trial.synthesize(out, '違う原稿。', 'Aoede')
                (out / 'Aoede/voice.wav').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    trial.synthesize(out, '声を試します。', 'Aoede')


if __name__ == '__main__':
    unittest.main()
