"""Independent decode, package inventory, audio identity and frame extraction.

Reads sealed results only; no Studio DB or provider actions. Screenshots are
extracted by FFmpeg, not used to rewrite generated illustration source pixels.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/studio/verification/claude-illustrated-20260906'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def local(value: str) -> Path:
    path = ROOT / value
    if '..' in path.parts or not path.resolve().is_relative_to(ROOT):
        raise ValueError('Path outside workspace')
    cursor = path
    while cursor != ROOT:
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError('Linked path rejected')
        cursor = cursor.parent
    return path


def run(*args: str) -> bytes:
    return subprocess.run(list(args), check=True, capture_output=True, timeout=120,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout


def artifact(record: dict) -> Path:
    path = local(record['rel_path'])
    if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
        raise ValueError('Registered artifact bytes changed')
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    result_path = local(str(args.result))
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if result['render']['status'] != 'succeeded' or result['render']['technical_verdict'] != 'pass' or not result['narration_cache_hit']:
        raise ValueError('Completed standard production and reused narration required')
    captioned = artifact(result['render']['master'])
    clean = captioned.with_name('master-clean.mp4')
    delivery = artifact(result['delivery']['artifact'])
    output = BASE / 'final-review' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=False)
    probes = {}
    for path in [captioned, clean]:
        probe = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)))
        videos = [s for s in probe['streams'] if s['codec_type'] == 'video']
        audio = [s for s in probe['streams'] if s['codec_type'] == 'audio']
        assert len(videos) == len(audio) == 1
        v, a = videos[0], audio[0]
        assert (v['width'], v['height'], v['avg_frame_rate'], v['nb_frames']) == (1080, 1920, '24/1', '504')
        assert float(probe['format']['duration']) == 21
        assert a['codec_name'] == 'aac' and a['sample_rate'] == '48000' and a['channels'] == 2
        run('ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-')
        probes[path.name] = {'full_decode_verified': True, 'sha256': sha(path), 'bytes': path.stat().st_size, 'ffprobe': probe}
    previous = json.loads((ROOT / 'outputs/studio/verification/claude-desktop-real-20260906/result.json').read_text(encoding='utf-8'))
    old_master = artifact(previous['render']['master'])
    def audio_hash(path: Path) -> str:
        return run('ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-').decode().strip()
    before, after = audio_hash(old_master), audio_hash(captioned)
    assert before == after, 'Narration AAC payload changed'
    with zipfile.ZipFile(delivery) as package:
        assert package.testzip() is None
        inventory = [{'path': item.filename, 'bytes': item.file_size} for item in package.infolist()]
        assert len(inventory) == result['delivery']['files_included'] == 13
    frames = []
    for seconds in [2, 10, 16.5, 20.5]:
        path = output / f'captioned-{seconds}s.png'
        run('ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(captioned), '-frames:v', '1', '-n', str(path))
        frames.append({'seconds': seconds, 'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
    with Image.open(output / 'captioned-16.5s.png') as frame:
        color = frame.convert('RGB').getpixel((80, 640))
    # Verify the flat orange area after both video encoding passes.
    assert max(abs(a-b) for a,b in zip(color, (217,119,87))) <= 6, ('Brand palette drift', color)
    report = {'source_result': result_path.relative_to(ROOT).as_posix(), 'source_result_sha256': sha(result_path),
              'run_id': result['render']['run_id'], 'probes': probes, 'zip_inventory': inventory,
              'aac_payload_identical_to_previous': True, 'aac_payload_hash': after,
              'cta_orange_rgb': list(color), 'target_orange_rgb': [217,119,87], 'frames': frames,
              'human_audio_quality_verified': False, 'public_release_ready': False}
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'run_id': report['run_id'], 'report': str(output / 'verification.json'),
                      'master': str(captioned), 'frames': frames, 'aac_payload_identical': True, 'orange_rgb': color}, ensure_ascii=False))


if __name__ == '__main__':
    main()
