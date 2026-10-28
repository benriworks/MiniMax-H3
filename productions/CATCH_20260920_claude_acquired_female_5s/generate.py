"""Submit one local I2VA job, or resume its saved identity without resubmission."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

PRODUCTION = Path(__file__).resolve().parent
ROOT = PRODUCTION.parents[1]
HEADROOM = '--headroom' in sys.argv[1:]
OUT = ROOT / ('outputs/claude-acquired-female-20260920-headroom' if HEADROOM else 'outputs/claude-acquired-female-20260920')
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def get(route):
    with urllib.request.urlopen('http://127.0.0.1:8188' + route, timeout=30) as response:
        return json.load(response)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def videos(obj):
    if isinstance(obj, dict):
        if str(obj.get('filename', '')).endswith('.mp4'):
            yield obj
        for value in obj.values():
            yield from videos(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from videos(value)


OUT.mkdir(parents=True, exist_ok=True)
keyframe = OUT / 'female-keyframe.png'
loaded_frame = ROOT / 'runtime/ComfyUI/input/claude-acquired-female-20260920/female-keyframe.png'
assert record(keyframe)['sha256'] == record(loaded_frame)['sha256']
for attempt in range(60):
    try:
        queue = get('/queue')
        break
    except OSError:
        if attempt == 59:
            raise
        time.sleep(2)

if (OUT / 'submission.json').exists():
    submission = read(OUT / 'submission.json')
    graph = read(OUT / 'graph.json')
else:
    if queue['queue_running'] or queue['queue_pending']:
        raise RuntimeError('ComfyUI is busy')
    if (OUT / 'request.json').exists():
        raise RuntimeError('Prior submission is uncertain; inspect its existing prompt_id before sending anything')
    graph = read(ROOT / 'outputs/claude-acquired-20260919/graph.json')
    graph['105:104']['inputs']['prompt'] = (PRODUCTION / 'prompts/FEMALE_H3.md').read_text(encoding='utf-8').strip()
    graph['105:104']['inputs']['first_frame'] = ['female-keyframe', 0]
    graph['female-keyframe'] = {'class_type': 'LoadImage', 'inputs': {'image': 'claude-acquired-female-20260920/female-keyframe.png'}}
    graph['105:15']['inputs']['noise_seed'] = 2026092007
    graph['92']['inputs']['filename_prefix'] = OUT.name + '/MiniMax_H3_Claude_Acquired_Female'
    save(OUT / 'graph.json', graph)
    task_id, client = str(uuid.uuid4()), str(uuid.uuid4())
    payload = {'prompt': graph, 'prompt_id': task_id, 'client_id': client}
    save(OUT / 'request.json', payload)
    request = urllib.request.Request('http://127.0.0.1:8188/prompt', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result['prompt_id'] != task_id:
        raise RuntimeError('Unexpected prompt identity; inspect response before retrying')
    submission = {'submitted_at': datetime.now(timezone.utc).isoformat(), 'client_id': client, **result}
    save(OUT / 'submission.json', submission)
    print(json.dumps({'event': 'submitted', **submission}), flush=True)

task_id = submission['prompt_id']
started = time.monotonic()
while True:
    history = get('/history/' + task_id)
    if task_id in history:
        break
    if time.monotonic() - started > 3600:
        raise RuntimeError('Existing job still pending after one hour; resume its identity, do not resubmit')
    time.sleep(20)
entry = history[task_id]
if not (OUT / 'history.json').exists():
    save(OUT / 'history.json', history)
if entry['status'].get('status_str') != 'success' or entry['status'].get('completed') is not True:
    raise RuntimeError('Generation failed: ' + json.dumps(entry['status']))
assert entry['prompt'][2] == graph
found = list(videos(entry['outputs']['92']))
assert len(found) == 1
raw = (ROOT / 'outputs' / found[0]['subfolder'] / found[0]['filename']).resolve()
assert raw.is_relative_to(OUT)
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(raw)], creationflags=FLAGS))
v = next(s for s in probe['streams'] if s['codec_type'] == 'video')
assert (v['width'], v['height'], v['avg_frame_rate'], int(v['nb_frames'])) == (768, 1376, '24/1', 124)
subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(raw), '-f', 'null', '-'], check=True, creationflags=FLAGS)
for t in (0, 1, 2, 3, 4):
    frame = OUT / f'raw-{t}.png'
    if not frame.exists():
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-ss', str(t), '-i', str(raw), '-frames:v', '1', str(frame)], check=True, creationflags=FLAGS)
messages = entry['status']['messages']
start = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_start')
end = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_success')
proof = {'schema_version': 1, 'verified_at': datetime.now(timezone.utc).isoformat(), 'generation_context': 'generated_for_this_revision',
    'production_id': PRODUCTION.name, 'profile': 'official_q4', 'runtime_mode': 'dynamic_vram', 'mode': 'I2VA',
    'execution': {'prompt_id': task_id, 'elapsed_seconds': (end - start) / 1000, 'success': True},
    'settings': {'seed': 2026092007, 'steps': 20, 'sampler': 'res_multistep', 'scheduler': 'simple', 'width': 768, 'height': 1376, 'requested_duration_seconds': 5, 'turbo': False, 'save_crf': 14, 'reserve_vram_gb': 1.5 if HEADROOM else 'ComfyUI Windows default'},
    'inputs': [record(p) for p in [OUT / 'graph.json', OUT / 'submission.json', OUT / 'history.json', PRODUCTION / 'prompts/FEMALE_H3.md', PRODUCTION / 'prompts/FEMALE_KEYFRAME.md', keyframe, loaded_frame, ROOT / 'outputs/claude-acquired-20260919/raw-0.png']],
    'keyframe_provider': 'Codex built-in image_gen, edited from the approved male opening frame',
    'artifact': {**record(raw), 'full_decode_verified': True, 'probe': probe}, 'review_status': 'awaiting_visual_review',
    'paid_api_calls': 0, 'paid_api_calls_scope': 'MiniMax video API calls only; keyframe uses the built-in image generation tool'}
if HEADROOM:
    proof['previous_attempt'] = {'prompt_id': '2681cee1-5f68-45b0-84c7-6b36ebdbd77e', 'status': 'interrupted_to_increase_vram_headroom', 'record': record(ROOT / 'outputs/claude-acquired-female-20260920/history.json')}
proof_path = ROOT / 'verification/claude-acquired-female-2026-09-20.json'
if not proof_path.exists():
    save(proof_path, proof)
print(json.dumps({'event': 'generation_verified', 'artifact': record(raw), 'provenance': record(proof_path), 'elapsed_seconds': (end - start) / 1000}), flush=True)
