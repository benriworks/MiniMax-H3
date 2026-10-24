"""Small, opt-in Gemini TTS audition. No credential values are persisted."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MODEL = 'gemini-2.5-flash-preview-tts'
VOICES = ('Kore', 'Aoede')
API = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL + ':generateContent'
TRIAL_ROOT = ROOT / 'outputs/productions/SHORT_20261021_dots_cloud_benefits/gemini-trials'
STYLE = ('Read only the supplied transcript, in natural standard Japanese. '
         'Use a clear, friendly professional explainer voice, slightly brisk but easy to follow. '
         'No music, introductions, sound effects or extra words.\nTranscript:\n')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def payload(text, voice):
    if voice not in VOICES or not isinstance(text, str) or not 1 <= len(text) <= 300:
        raise ValueError('Use an allowed trial voice and at most 300 text characters')
    return {'contents': [{'parts': [{'text': STYLE + text}]}],
            'generationConfig': {'responseModalities': ['AUDIO'],
                                 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}}}


def decode_audio(response, *, minimum_seconds=2):
    if minimum_seconds not in (.2, 2):
        raise ValueError('Use the audition or short-segment duration policy')
    candidates = response.get('candidates', [])
    if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
        raise ValueError('Expected one complete speech candidate')
    chunks = []
    for part in candidates[0].get('content', {}).get('parts', []):
        item = part.get('inlineData')
        if not item:
            continue
        mime = item.get('mimeType', '').lower()
        if not re.fullmatch(r'audio/(?:l16|pcm);(?:codec=pcm;)?rate=24000', mime):
            raise ValueError('Unexpected PCM audio format')
        chunk = base64.b64decode(item.get('data', ''), validate=True)
        if not chunk or len(chunk) % 2:
            raise ValueError('Malformed PCM samples')
        chunks.append(chunk)
    pcm = b''.join(chunks)
    if not minimum_seconds * 24000 * 2 <= len(pcm) <= 40 * 24000 * 2:
        raise ValueError('Speech duration is outside the selected duration policy')
    result = io.BytesIO()
    with wave.open(result, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return result.getvalue(), len(pcm) / 48000


def known_error(body):
    # Only controlled classifications escape this function; never provider text or headers.
    error = body.get('error', {})
    reasons = [d.get('reason') for d in error.get('details', []) if isinstance(d, dict)]
    if 'API_KEY_INVALID' in reasons:
        return 'api_key_invalid'
    return {'PERMISSION_DENIED': 'permission_denied', 'RESOURCE_EXHAUSTED': 'quota_exhausted',
            'NOT_FOUND': 'model_unavailable', 'INVALID_ARGUMENT': 'invalid_request'}.get(error.get('status'), 'provider_error')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Speech endpoint redirect refused')


def synthesize(out, text, voice, *, minimum_seconds=2):
    target = out / voice
    if target.exists():
        proof = target / 'verified.json'
        if proof.is_file():
            data = json.loads(proof.read_text(encoding='utf-8'))
            if json.loads((target / 'request.json').read_text(encoding='utf-8')) != payload(text, voice):
                raise ValueError('Audition transcript changed; create a new prepared trial')
            for item in data['files']:
                if record(ROOT / item['path']) != item:
                    raise ValueError('Verified speech changed')
            return data
        raise RuntimeError('Previous submission is incomplete; do not automatically submit it again')
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('Gemini API key is not configured')
    target.mkdir()
    request_body = payload(text, voice)
    save(target / 'request.json', request_body)
    save(target / 'submission.json', {'status': 'submitted', 'automatic_retry': False, 'model': MODEL, 'voice': voice})
    request = urllib.request.Request(API, data=json.dumps(request_body).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=120) as response:
            raw = response.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError('Speech response exceeds trial limit')
        data = json.loads(raw)
    except urllib.error.HTTPError as error:
        try:
            classification = known_error(json.loads(error.read(32768)))
        except Exception:
            classification = 'provider_error'
        save(target / 'submission.json', {'status': 'rejected', 'http_status': error.code,
                                          'error': classification, 'automatic_retry': False})
        raise RuntimeError('Gemini request rejected: ' + classification) from None
    except Exception:
        save(target / 'submission.json', {'status': 'unknown', 'automatic_retry': False})
        raise RuntimeError('Gemini submission result is unknown; do not automatically retry') from None
    wav_bytes, duration = decode_audio(data, minimum_seconds=minimum_seconds)
    (target / 'voice.wav').write_bytes(wav_bytes)
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-i', str(target / 'voice.wav'),
                    '-f', 'null', '-'], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    usage = {k: v for k, v in data.get('usageMetadata', {}).items()
             if k in ['promptTokenCount', 'candidatesTokenCount', 'totalTokenCount'] and isinstance(v, int)}
    result = {'status': 'technically_verified_listening_pending', 'model': MODEL, 'voice': voice,
              'duration_seconds': duration, 'sample_rate': 24000, 'channels': 1, 'sample_width': 2,
              'usage': usage, 'minimum_seconds': minimum_seconds, 'user_approved': False,
              'files': [record(target / 'voice.wav'), record(target / 'request.json')]}
    save(target / 'verified.json', result)
    save(target / 'submission.json', {'status': 'received_and_verified', 'automatic_retry': False})
    return result


def prepare():
    from tools.studio.narration import generate_local_narration
    from tools.studio.shorts_creator import check
    story = json.loads((Path(__file__).parent / 'creator-story.json').read_text(encoding='utf-8'))
    transcript = ''.join(s['narration'] for s in story['scenes'][:3])
    spoken = transcript
    for item in sorted(story['pronunciations'], key=lambda p: -len(p['source'])):
        spoken = spoken.replace(item['source'], item['target'])
    for voice in VOICES:
        payload(spoken, voice)
    out = TRIAL_ROOT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    plan = {'status': 'prepared_waiting_for_valid_api_key', 'model': MODEL, 'voices': list(VOICES),
            'transcript': transcript, 'spoken_transcript': spoken, 'automatic_retry': False,
            'output': out.relative_to(ROOT).as_posix(), 'maximum_requests': 2,
            'prompt': 'Clear, friendly standard Japanese; slightly brisk; voice only.', 'user_approved': False}
    save(out / 'plan.json', plan)
    token = uuid.uuid4().hex
    original = generate_local_narration(ROOT, production_id='production_' + token, run_id='run_' + token,
                                       payload={'voice': story['voice'], 'rate': story['rate'],
                                                'pronunciations': story['pronunciations'], 'segments': [{'text': transcript}]})
    for artifact in original['artifacts']:
        if artifact['name'] == 'narration.wav':
            (out / 'windows-sayaka.wav').write_bytes(check(artifact).read_bytes())
    print(json.dumps({'status': plan['status'], 'output': str(out), 'transcript_characters': len(transcript),
                      'maximum_requests': 2}, ensure_ascii=True))


def generate(out):
    out = out.resolve(strict=True)
    if out.parent != TRIAL_ROOT:
        raise ValueError('Trial output is outside the prepared production')
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    if plan['model'] != MODEL or plan['voices'] != list(VOICES):
        raise ValueError('Prepared trial does not match the fixed model and voices')
    results = [synthesize(out, plan['spoken_transcript'], voice) for voice in VOICES]
    save(out / 'results.json', {'status': 'listening_review_pending', 'voices': results, 'user_approved': False})
    print(json.dumps({'status': 'listening_review_pending', 'output': str(out),
                      'durations': {r['voice']: r['duration_seconds'] for r in results}}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'generate'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare()
        elif args.output is None:
            parser.error('--output is required')
        else:
            generate(args.output)
    except Exception as error:
        # No traceback carrying request objects or headers in the command output.
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, (ValueError, RuntimeError)) else 'Trial failed; inspect local status.'}, ensure_ascii=True))
        raise SystemExit(1)
