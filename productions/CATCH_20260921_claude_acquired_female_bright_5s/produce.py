"""Create the female game reward catch using the original narration and chimes."""
from __future__ import annotations

import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import wave

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
sys.path.insert(0, str(ROOT))
from tools.studio.narration import generate_local_narration

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def check(item):
    path = (ROOT / item.get('path', item.get('rel_path'))).resolve(strict=True)
    if not path.is_relative_to(ROOT) or record(path)['sha256'] != item['sha256'] or path.stat().st_size != item['bytes']:
        raise ValueError('Source artifact changed')
    return path


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-n', *map(str, args)], check=True, creationflags=FLAGS)


def chime(path):
    """Original synthesized ascending major chord; no sampled game soundtrack."""
    rate = 48000
    samples = array.array('h')
    notes = [(0.94, 523.251, 0.9), (1.07, 659.255, 0.9), (1.20, 783.991, 1.2), (1.33, 1046.502, 1.25)]
    for index in range(5 * rate):
        time = index / rate
        value = 0.0
        for start, frequency, duration in notes:
            t = time - start
            if 0 <= t < duration:
                envelope = min(1.0, t / .008) * math.exp(-t * 5.5) * min(1.0, (duration - t) / .03)
                value += .10 * envelope * (math.sin(2 * math.pi * frequency * t) + .22 * math.sin(2 * math.pi * frequency * 2 * t))
        samples.append(round(value * 32767))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as handle:
        handle.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        handle.writeframes(samples.tobytes())


def prepare():
    story = read(FOLDER / 'story.json')
    output = ROOT / 'outputs/productions' / FOLDER.name / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    key = uuid.uuid4().hex
    reuse_sources = []
    prior = None
    if story.get('audio_source_folder'):
        prior = (ROOT / story['audio_source_folder']).resolve(strict=True)
        if not prior.is_relative_to(ROOT / 'outputs'):
            raise ValueError('Audio source must be a workspace output')
        previous = read(prior / 'preparation.json')
        verified = read(prior / 'verification.json')
        for field in ('voice', 'rate', 'pronunciations', 'narration', 'narration_start_ms'):
            if previous['story'][field] != story[field]:
                raise ValueError('Narration setting changed: ' + field)
        originals = {Path(r['path']).name: r for r in previous['sources']}
        artifacts = []
        for name in ('narration.wav', 'captions.srt', 'timings.json', 'manifest.json', 'reward-chime.wav'):
            path = check(originals[name])
            if path != prior / name:
                raise ValueError('Unexpected previous narration path')
            reuse_sources.append(record(path))
            if name != 'reward-chime.wav':
                artifacts.append({'name': name, **record(path)})
        for delivery in verified['deliveries']:
            check(delivery)
            if delivery['full_decode_verified'] is not True:
                raise ValueError('Prior delivery lacks decode verification')
        reuse_sources.extend([record(prior / 'preparation.json'), record(prior / 'verification.json')])
        narration = {'provider': 'verified_previous_local_sapi', 'artifacts': artifacts, 'new_synthesis': False}
    else:
        narration = generate_local_narration(ROOT, production_id='production_' + key, run_id='run_' + key,
            payload={'voice': story['voice'], 'rate': story['rate'], 'pronunciations': story['pronunciations'], 'segments': [{'text': story['narration']}]},
            segment_start_ms=[story['narration_start_ms']])
    save(output / 'narration-result.json', narration)
    files = {a['name']: check(a) for a in narration['artifacts']}
    timings = read(files['timings.json'])
    segment = timings['segments'][0]
    if segment['start_ms'] != story['narration_start_ms'] or segment['end_ms'] > 4900:
        raise ValueError(f'Narration exceeds five-second slot: {segment}; retained: {output}')
    for name, path in files.items():
        shutil.copyfile(path, output / name)
    if prior is not None:
        shutil.copyfile(prior / 'reward-chime.wav', output / 'reward-chime.wav')
    else:
        chime(output / 'reward-chime.wav')
    sources = [record(FOLDER / 'story.json'), record(FOLDER / 'produce.py'), record(ROOT / 'tools/studio/narration.py'),
               *[record(output / name) for name in files], record(output / 'reward-chime.wav'), *reuse_sources]
    save(output / 'preparation.json', {'story': story, 'sources': sources, 'timings': timings, 'narration_reused': prior is not None})
    print(json.dumps({'event': 'prepared', 'output': str(output), 'speech_start_ms': segment['start_ms'], 'speech_end_ms': segment['end_ms']}, ensure_ascii=False), flush=True)


def verify_video(path):
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], creationflags=FLAGS))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    if len(probe['streams']) != 2 or (video['width'], video['height'], video['avg_frame_rate'], int(video['nb_frames']), video['codec_name'], audio['codec_name'], audio['sample_rate']) != (1080, 1920, '24/1', 120, 'h264', 'aac', '48000') or abs(float(probe['format']['duration']) - 5) > .002:
        raise ValueError('Delivery format mismatch')
    ffmpeg('-xerror', '-i', path, '-f', 'null', '-')
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-f', 'f32le', '-ac', '1', '-'], creationflags=FLAGS)
    samples = array.array('f', pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    peak = max(abs(v) for v in samples)
    if not .005 < peak < .99:
        raise ValueError(f'Audio silence/clipping check failed: {peak}')
    packets = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], creationflags=FLAGS).decode().strip()
    return {**record(path), 'probe': probe, 'full_decode_verified': True, 'audio_sample_peak': peak, 'video_packet_hash': packets}


def finish(output):
    output = output.resolve(strict=True)
    if not output.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Expected workspace output')
    prep, render = read(output / 'preparation.json'), read(output / 'render.json')
    for item in [*prep['sources'], *render['sources']]:
        check(item)
    timeline = check(render['timeline'])
    ffmpeg('-i', output / 'narration.wav', '-i', output / 'reward-chime.wav', '-filter_complex',
           '[0:a]apad,atrim=duration=5,volume=1.15[voice];[voice][1:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.92:level=false:latency=true[a]',
           '-map', '[a]', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', '-t', '5', output / 'mix.wav')
    deliveries = []
    for name, audio in [('claude-acquired-female-bright.mp4', 'mix.wav'), ('claude-acquired-female-bright-sfx-only.mp4', 'reward-chime.wav')]:
        path = output / name
        ffmpeg('-i', timeline, '-i', output / audio, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-t', '5', '-movflags', '+faststart', path)
        deliveries.append(verify_video(path))
    if deliveries[0]['video_packet_hash'] != deliveries[1]['video_packet_hash']:
        raise ValueError('Alternate version video changed')
    for t in (0, 1, 2, 3, 4):
        ffmpeg('-ss', t, '-i', output / 'claude-acquired-female-bright.mp4', '-frames:v', '1', '-vf', 'scale=360:640:flags=lanczos', output / f'preview-{t}.png')
    save(output / 'verification.json', {'verified_at': datetime.now(timezone.utc).isoformat(), 'deliveries': deliveries, 'sources': render['sources'], 'typography': render['typography'], 'timings': prep['timings'], 'narration_reused': prep['narration_reused'], 'user_approved': False, 'review_status': 'awaiting_final_visual_review'})
    print(json.dumps({'event': 'assembled', 'output': str(output), 'deliveries': [{'path': d['path'], 'audio_peak': d['audio_sample_peak']} for d in deliveries]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == 'finish':
        finish(Path(sys.argv[2]))
    else:
        raise SystemExit('Usage: produce.py prepare | finish OUTPUT')
