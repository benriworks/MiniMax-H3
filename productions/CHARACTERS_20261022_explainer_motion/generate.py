"""Local-only H3 I2VA, isolated output, durable identity and pressure monitoring."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

PRODUCTION = Path(__file__).resolve().parent
ROOT = PRODUCTION.parents[1]
OUT = ROOT / 'outputs/characters/explainer-motion-20261022'
INPUT = ROOT / 'runtime/ComfyUI/input/explainer-motion-20261022'
URL = 'http://127.0.0.1:8189'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
GIB = 1024 ** 3

def now():
    return datetime.now(timezone.utc).isoformat()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

def record(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': digest.hexdigest().upper()}

def request(route, data=None):
    body = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(URL + route, data=body,
        headers={'Content-Type': 'application/json'}, method='GET' if data is None else 'POST')
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def ensure_runtime():
    stats = request('/system_stats')
    args = stats.get('system', {}).get('argv', [])
    if '--port' not in args or args[args.index('--port')+1] != '8189' or str(OUT) not in args:
        raise RuntimeError('Server is not the dedicated isolated runtime')
    return stats

def ready_resources(sample):
    return sample['ram_available_bytes'] >= 12*GIB and sample['commit_available_bytes'] >= 24*GIB and sample['disk_free_bytes'] >= 20*GIB

class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
        ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
        ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
        ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
        ('avail_extended', ctypes.c_ulonglong)]

def resources():
    mem = MemoryStatus()
    mem.length = ctypes.sizeof(mem)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
        raise RuntimeError('Cannot inspect memory pressure')
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.total,memory.used,utilization.gpu',
        '--format=csv,noheader,nounits'], creationflags=FLAGS, text=True, timeout=10).strip()
    return {'at': now(), 'ram_available_bytes': mem.avail_phys,
        'commit_available_bytes': mem.avail_page, 'commit_limit_bytes': mem.total_page,
        'disk_free_bytes': shutil.disk_usage(OUT).free, 'gpu_mib_mib_percent': gpu}

def prompt(spec):
    return ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        "integrated_multimodal_description: [Shot 1] A single continuous five-second vertical shot. Preserve the exact visual style, identity, age, face, hairstyle, clothes, body proportions, chair, desk, laptop, room, composition and lighting of Picture 1. "
        f"The only person is {spec['identity']}. "
        "From 0.0 to 0.8 seconds the subject calmly settles and blinks naturally. From 0.8 to 3.5 seconds: "
        f"{spec['motion']} "
        "From 3.5 to 5.0 seconds the subject holds a relaxed attentive pose with a subtle warm smile and quiet breathing. "
        "Keep the motion small, slow, deliberate and professional. The camera is completely fixed. Keep the original face and upper body fully visible throughout, with exactly two coherent arms and natural hands. Preserve the uncluttered background area. "
        "No speaking or lip-sync, no game reward, no magic crystal, no confetti, no dramatic fist pumping, no floating interface, no added characters, no new props, no cuts, no generated words, letters, logos or watermarks.\n\n"
        "overall_soundscape: Very quiet room tone and subtle fabric movement. No speech, vocalization, music or dramatic sound effects.\n\n"
        "non_diegetic_music: N/A\n")

def prepare(job, spec):
    destination = OUT / job
    destination.mkdir(parents=True, exist_ok=True)
    source = (ROOT / spec['source']).resolve()
    if not source.is_relative_to(ROOT) or not source.is_file():
        raise RuntimeError('Source must be an existing workspace file')
    frame = INPUT / job / 'keyframe.png'
    frame.parent.mkdir(parents=True, exist_ok=True)
    if frame.exists():
        if record(source)['sha256'] != record(frame)['sha256']:
            raise RuntimeError('Input copy differs; do not overwrite')
    else:
        with source.open('rb') as src, frame.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    p = destination / 'prompt.txt'
    expected_prompt = prompt(spec)
    if p.exists():
        if p.read_text(encoding='utf-8') != expected_prompt:
            raise RuntimeError('Prepared prompt differs; use a separate revision')
    else:
        with p.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(expected_prompt)
    graph = read(ROOT / 'outputs/claude-acquired-20260919/graph.json')
    graph['105:104']['inputs']['prompt'] = expected_prompt.strip()
    graph['105:104']['inputs']['first_frame'] = ['keyframe', 0]
    graph['keyframe'] = {'class_type': 'LoadImage', 'inputs': {'image': frame.relative_to(INPUT.parent).as_posix()}}
    graph['105:15']['inputs']['noise_seed'] = spec['seed']
    graph['92']['inputs']['filename_prefix'] = job + '/MiniMax_H3_' + job.replace('-', '_')
    if (destination / 'graph.json').exists():
        if read(destination / 'graph.json') != graph:
            raise RuntimeError('Prepared graph differs; use a separate revision')
    else:
        save(destination / 'graph.json', graph)
    return destination, graph, source, frame

def video_entries(obj):
    if isinstance(obj, dict):
        if str(obj.get('filename', '')).endswith('.mp4'):
            yield obj
        for value in obj.values():
            yield from video_entries(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from video_entries(value)

def verify(job, spec, destination, graph, source, frame, history, task_id):
    entry = history[task_id]
    if not (destination / 'history.json').exists():
        save(destination / 'history.json', history)
    if entry['status'].get('status_str') != 'success' or entry['status'].get('completed') is not True:
        raise RuntimeError('Generation did not succeed; inspect history.json')
    if entry['prompt'][2] != graph:
        raise RuntimeError('Execution graph identity does not match')
    found = list(video_entries(entry['outputs']['92']))
    if len(found) != 1:
        raise RuntimeError('Unexpected output count')
    raw = (OUT / found[0]['subfolder'] / found[0]['filename']).resolve()
    if not raw.is_relative_to(destination):
        raise RuntimeError('Output outside its dedicated job directory')
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(raw)], creationflags=FLAGS))
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    if (stream['width'], stream['height'], stream['avg_frame_rate'], int(stream['nb_frames'])) != (768, 1376, '24/1', 124):
        raise RuntimeError('Unexpected video dimensions, frame rate or length')
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(raw), '-f', 'null', '-'], check=True, creationflags=FLAGS)
    for sec in (0, 1, 2, 3, 4):
        image = destination / f'frame-{sec}.png'
        if not image.exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-ss', str(sec), '-i', str(raw), '-frames:v', '1', str(image)], check=True, creationflags=FLAGS)
    sheet = destination / 'contact-sheet.jpg'
    if not sheet.exists():
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(raw), '-vf', 'fps=1,scale=256:-1,tile=5x1', '-frames:v', '1', '-q:v', '2', str(sheet)], check=True, creationflags=FLAGS)
    messages = entry['status']['messages']
    begin = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_start')
    end = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_success')
    proof = {'schema_version': 1, 'verified_at': now(), 'provider': 'minimax',
        'generation_context': 'generated_for_this_revision', 'generated_context': 'New local MiniMax H3 I2VA explanatory gesture, not a reused prior video',
        'production_id': PRODUCTION.name, 'job': job, 'mode': 'I2VA', 'profile': 'official_q4', 'runtime_mode': 'dynamic_vram',
        'source_presenter': record(ROOT / spec.get('source_presenter', spec['source'])), 'source_keyframe': record(frame),
        'execution': {'prompt_id': task_id, 'elapsed_seconds': (end-begin)/1000, 'success': True},
        'settings': {'seed': spec['seed'], 'steps': 20, 'sampler': 'res_multistep', 'scheduler': 'simple', 'width': 768, 'height': 1376, 'fps': 24, 'frames': 124, 'requested_duration_seconds': 5, 'turbo': False, 'save_crf': 14, 'reserve_vram_gb': 2.0},
        'inputs': [record(path) for path in [destination/'graph.json', destination/'request.json', destination/'submission.json', destination/'history.json', destination/'prompt.txt']],
        'artifact': {**record(raw), 'full_decode_verified': True, 'probe': probe}, 'contact_sheet': record(sheet),
        'review_status': 'awaiting_visual_review', 'userApproved': False, 'paid_api_calls': 0,
        'paid_api_calls_scope': 'MiniMax video API calls; this generation is entirely local'}
    if not (destination / 'verification.json').exists():
        save(destination / 'verification.json', proof)
    print(json.dumps({'event': 'generation_verified', 'job': job, 'artifact': record(raw), 'provenance': str(destination/'verification.json'), 'contact_sheet': str(sheet), 'elapsed_seconds': (end-begin)/1000}), flush=True)

def generate(job, spec, prepare_only):
    destination, graph, source, frame = prepare(job, spec)
    if prepare_only:
        print(json.dumps({'event': 'prepared', 'job': job, 'source': record(source)}), flush=True)
        return
    if (destination / 'verification.json').exists():
        proof = read(destination / 'verification.json')
        if record(ROOT / proof['artifact']['path'])['sha256'] != proof['artifact']['sha256']:
            raise RuntimeError('Previously verified output changed')
        print(json.dumps({'event': 'already_verified', 'job': job}), flush=True)
        return
    stats = ensure_runtime()
    if (destination / 'submission.json').exists():
        submission = read(destination / 'submission.json')
    elif (destination / 'request.json').exists():
        saved = read(destination / 'request.json')
        task_id = saved['prompt_id']
        history = request('/history/' + task_id)
        queue = request('/queue')
        known = task_id in history or any(x[1] == task_id for x in queue['queue_running'] + queue['queue_pending'])
        if not known:
            raise RuntimeError('Uncertain prior submission. Do not resubmit; inspect saved prompt_id.')
        submission = {'submitted_at': now(), 'prompt_id': task_id, 'client_id': saved['client_id'], 'recovered_without_resubmission': True}
        save(destination / 'submission.json', submission)
    else:
        queue = request('/queue')
        if queue['queue_running'] or queue['queue_pending']:
            raise RuntimeError('Dedicated ComfyUI queue is not empty; do not disturb existing jobs')
        resource = resources()
        if not ready_resources(resource):
            # Empty, dedicated queue only: release this service's cached models.
            req = urllib.request.Request(URL + '/free', data=b'{"unload_models":true,"free_memory":true}', headers={'Content-Type':'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=30):
                pass
            for _ in range(30):
                time.sleep(2)
                resource = resources()
                if ready_resources(resource):
                    break
        preflight = destination / 'preflight.json'
        if preflight.exists():
            preflight = destination / ('preflight-' + datetime.now(timezone.utc).strftime('%H%M%S') + '.json')
        save(preflight, resource)
        if not ready_resources(resource):
            raise RuntimeError('Insufficient available memory/disk; no job submitted')
        if not (destination / 'system-stats.json').exists():
            save(destination / 'system-stats.json', stats)
        task_id, client = str(uuid.uuid4()), str(uuid.uuid4())
        payload = {'prompt': graph, 'prompt_id': task_id, 'client_id': client}
        save(destination / 'request.json', payload)
        result = request('/prompt', payload)
        if result.get('prompt_id') != task_id:
            save(destination / 'unexpected-response.json', result)
            raise RuntimeError('Unexpected prompt identity; do not retry')
        submission = {'submitted_at': now(), 'client_id': client, **result}
        save(destination / 'submission.json', submission)
        print(json.dumps({'event': 'submitted', 'job': job, **submission}), flush=True)
    task_id = submission['prompt_id']
    started = time.monotonic()
    pressure_count = 0
    while True:
        history = request('/history/' + task_id)
        if task_id in history:
            break
        queue = request('/queue')
        if not any(x[1] == task_id for x in queue['queue_running'] + queue['queue_pending']):
            raise RuntimeError('Saved job absent from both history and queue; no automatic resubmission')
        sample = resources()
        with (destination / 'resources.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(sample) + '\n')
        pressure_count = pressure_count + 1 if sample['ram_available_bytes'] < GIB or sample['commit_available_bytes'] < 3*GIB or sample['disk_free_bytes'] < 5*GIB else 0
        if pressure_count >= 3:
            # Interrupt only the proven active job on our dedicated service.
            active = queue['queue_running']
            if len(active) == 1 and active[0][1] == task_id:
                req = urllib.request.Request(URL + '/interrupt', data=b'{}', headers={'Content-Type':'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=30):
                    pass
            save(destination / 'pressure-stop.json', sample)
            raise RuntimeError('Own generation interrupted after persistent critical resource pressure')
        if time.monotonic() - started > 7200:
            raise RuntimeError('Job still pending after two hours; resume same identity, do not resubmit')
        time.sleep(20)
    verify(job, spec, destination, graph, source, frame, history, task_id)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('jobs', nargs='+')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--after', help='Wait for a prior configured job proof without submitting anything')
    args = parser.parse_args()
    specs = read(PRODUCTION/'jobs.json')['jobs']
    if args.after:
        if args.after not in specs or args.after in args.jobs:
            raise ValueError('Invalid prerequisite job')
        deadline = time.monotonic() + 4*60*60
        prior = OUT / args.after
        while True:
            if (prior/'verification.json').exists():
                try:
                    proof = read(prior/'verification.json')
                except json.JSONDecodeError:
                    time.sleep(2)
                    continue
                if not proof['execution']['success'] or not proof['artifact']['full_decode_verified']:
                    raise RuntimeError('Prerequisite artifact did not pass technical verification')
                if record(ROOT/proof['artifact']['path'])['sha256'] != proof['artifact']['sha256']:
                    raise RuntimeError('Prerequisite artifact changed')
                print(json.dumps({'event': 'prerequisite_verified', 'job': args.after}), flush=True)
                break
            if (prior/'pressure-stop.json').exists():
                raise RuntimeError('Prerequisite job stopped under resource pressure')
            if time.monotonic() > deadline:
                raise RuntimeError('Prerequisite remains incomplete after four hours; no submission made')
            time.sleep(30)
    for job in args.jobs:
        if job not in specs:
            raise ValueError('Unknown configured job: ' + job)
        generate(job, specs[job], args.prepare_only)

if __name__ == '__main__':
    main()
