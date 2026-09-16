"""Build a local review draft with shared narration and assembly workers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
sys.path.insert(0, str(ROOT))
from tools.studio.assembly import assemble_local_video, assembly_cache_key, resolve_tool_identity
from tools.studio.narration import generate_local_narration
from tools.studio.security import workspace_path

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest().upper()


def record(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}


def save(p, value):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def check(r):
    p = workspace_path(ROOT, r.get('path', r.get('rel_path')), must_exist=True)
    if digest(p) != r['sha256'] or p.stat().st_size != r['bytes']:
        raise ValueError('Changed artifact: ' + str(p))
    return p


def reuse_visuals(output, prior_folder):
    prior_folder = workspace_path(ROOT, prior_folder, must_exist=True)
    prior_render_path = prior_folder / 'render.json'
    prior_prep_path = prior_folder / 'preparation.json'
    prior_render, prior_prep = read(prior_render_path), read(prior_prep_path)
    prep = read(output / 'preparation.json')
    for key in ('models', 'duration_ms', 'fps'):
        if prep['story'][key] != prior_prep['story'][key]:
            raise ValueError('Visual story changed; render a new timeline')
    visual_paths = [FOLDER / 'Evolution.tsx', FOLDER / 'render.mjs',
        ROOT / 'studio/src/remotion/ScreenTypography.tsx',
        ROOT / 'studio/public/template-assets/NotoSansJP-Variable.ttf',
        ROOT / 'studio/package.json', ROOT / 'studio/package-lock.json']
    prior_sources = {r['path']: r for r in prior_render['sources']}
    for p in visual_paths:
        expected = prior_sources.get(p.relative_to(ROOT).as_posix())
        if expected is None or check(expected) != p:
            raise ValueError('Visual renderer changed; render a new timeline')
    check(prior_render['timeline'])
    if prior_render.get('full_decode_verified') is not True:
        raise ValueError('Prior timeline lacks decode verification')
    save(output / 'render.json', {'schema_version': 1,
        'sources': [*prep['sources'], *[record(p) for p in visual_paths], record(prior_render_path), record(prior_prep_path)],
        'timeline': prior_render['timeline'], 'probe': prior_render['probe'], 'full_decode_verified': True,
        'visual_reuse': {'prior_render': record(prior_render_path), 'prior_preparation': record(prior_prep_path),
                         'checked_fields': ['models', 'duration_ms', 'fps'], 'visual_source_hashes_verified': True}})


def prepare(prior_folder=None):
    story = read(FOLDER / 'story.json')
    if story['duration_ms'] != 30000 or len(story['segments']) != 6:
        raise ValueError('Expected six five-second scenes')
    expected = [('Fable 5', '2026.06.09', 42.0), ('Opus 5', '2026.07.24', 52.3), ('Fable 5.1', '2026.09.01', 55.8)]
    if [(m['name'], m['date'], m['score']) for m in story['models']] != expected:
        raise ValueError('Model facts no longer match the reviewed source table')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / 'outputs/productions/SHORT_20260916_claude_code_evolution_30s' / stamp
    output.mkdir(parents=True, exist_ok=False)
    namespace = hashlib.sha256(str(output).encode()).hexdigest()[:32]
    sources = [record(FOLDER / p) for p in ['story.json', 'SOURCES_JA.md', 'Evolution.tsx', 'render.mjs', 'produce.py']]
    starts = [s['start_ms'] for s in story['segments']]
    narration = generate_local_narration(ROOT, production_id='production_' + namespace, run_id='run_' + namespace,
        payload={'voice': story['voice'], 'rate': story['rate'], 'pronunciations': story['pronunciations'],
                 'segments': [{'text': s['text']} for s in story['segments']]}, segment_start_ms=starts)
    save(output / 'narration-result.json', narration)
    files = {a['name']: check(a) for a in narration['artifacts']}
    timings = read(files['timings.json'])
    for i, row in enumerate(timings['segments']):
        if row['text'] != story['segments'][i]['text'] or row['start_ms'] != starts[i] or row['end_ms'] > (i + 1) * 5000 - 100:
            raise ValueError(f'Speech {i + 1} exceeds its slot; shorten the script. Retained output: {output}')
    save(output / 'preparation.json', {'story': story, 'sources': sources, 'namespace': namespace, 'timings': timings})
    if prior_folder is not None:
        reuse_visuals(output, prior_folder)
    print(json.dumps({'event': 'prepared', 'output': str(output), 'speech_intervals': [[s['start_ms'], s['end_ms']] for s in timings['segments']]}, ensure_ascii=False), flush=True)


def finish(folder):
    output = workspace_path(ROOT, folder, must_exist=True)
    prep, render = read(output / 'preparation.json'), read(output / 'render.json')
    for r in [*prep['sources'], *render['sources']]:
        check(r)
    source = check(render['timeline'])
    narration = read(output / 'narration-result.json')
    files = {a['name']: check(a) for a in narration['artifacts']}
    tools = resolve_tool_identity()
    key = assembly_cache_key(digest(source), digest(files['narration.wav']), digest(files['captions.srt']), True,
        caption_style_preset='shorts_ja_large_v1', audio_mix_preset='narration_only_v1', tool_identity=tools)
    result_file = output / 'assembly-result.json'
    if result_file.exists():
        result = read(result_file)
        if result['cache_key'] != key:
            raise ValueError('Assembly input changed')
    else:
        result = assemble_local_video(ROOT, production_id='production_' + prep['namespace'], run_id='run_' + prep['namespace'],
            cache_key=key, source_video=source, narration_wav=files['narration.wav'], captions_srt=files['captions.srt'],
            include_captioned=True, caption_style_preset='shorts_ja_large_v1', audio_mix_preset='narration_only_v1')
        save(result_file, result)
    masters = {}
    for a in result['artifacts']:
        p = check(a)
        if a['name'] not in ('master-clean.mp4', 'master-captioned.mp4'):
            continue
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(p)], creationflags=FLAGS))
        v = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        if (len(probe['streams']) != 2 or v['width'] != 1080 or v['height'] != 1920 or v['avg_frame_rate'] != '24/1'
            or v['codec_name'] != 'h264' or int(v['nb_frames']) != 720 or float(probe['format']['duration']) != 30
            or audio['codec_name'] != 'aac' or int(audio['sample_rate']) != 48000):
            raise ValueError('Final media format mismatch')
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(p), '-f', 'null', '-'], check=True, creationflags=FLAGS)
        masters[a['name']] = {**record(p), 'format_verified': True, 'full_decode_verified': True}
    if len(masters) != 2:
        raise ValueError('Both masters required')
    captioned = check(masters['master-captioned.mp4'])
    for t in [2, 7, 12, 17, 22, 27]:
        preview = output / f'preview-{t:02d}.png'
        if not preview.exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-ss', str(t), '-i', str(captioned), '-frames:v', '1', '-vf', 'scale=360:640', str(preview)], check=True, creationflags=FLAGS)
    publication = output / 'publication.txt'
    if not publication.exists():
        publication.write_text(prep['story']['title'] + '\n\n' + prep['story']['description'] + '\n', encoding='utf-8')
    verification = {'masters': masters, 'timings': prep['timings'], 'studio_database_run': False, 'paid_api_calls': 0,
        'public_quality_verified': False, 'audio_quality_improved': False, 'source_claims': 'SOURCES_JA.md',
        'narration_settings': {k: prep['story'][k] for k in ['voice', 'rate', 'pronunciations']},
        'visual_reuse': render.get('visual_reuse'),
        'workflow': 'Scoped motion graphics with shared local Studio narration and assembly', 'review_status': 'first_draft'}
    verify_file = output / 'verification.json'
    if not verify_file.exists():
        save(verify_file, verification)
    package_items = {**{n: check(r) for n, r in masters.items()}, **files, 'publication.txt': publication,
        'verification.json': verify_file, 'story.json': FOLDER / 'story.json', 'SOURCES_JA.md': FOLDER / 'SOURCES_JA.md'}
    archive_path = output / 'claude-code-evolution-review.zip'
    if not archive_path.exists():
        with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for n, p in package_items.items():
                z.write(p, n)
    with zipfile.ZipFile(archive_path) as z:
        if z.testzip() or set(z.namelist()) != set(package_items):
            raise ValueError('ZIP integrity mismatch')
        for n, p in package_items.items():
            if hashlib.sha256(z.read(n)).hexdigest().upper() != digest(p):
                raise ValueError('ZIP payload mismatch')
    save(output / 'result.json', {'captioned': str(captioned), 'clean': str(check(masters['master-clean.mp4'])), 'zip': str(archive_path), 'output': str(output)})
    print(json.dumps(read(output / 'result.json'), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare' and len(sys.argv) in (2, 3):
        prepare(sys.argv[2] if len(sys.argv) == 3 else None)
    elif sys.argv[1] == 'finish' and len(sys.argv) == 3:
        finish(sys.argv[2])
    else:
        raise SystemExit('Usage: produce.py prepare [VERIFIED_PRIOR_OUTPUT] | finish OUTPUT_DIRECTORY')
