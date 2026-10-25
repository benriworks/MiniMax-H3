"""Resumable pilot speech and rendering; capture proofs are required at prepare."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import wave

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import (
    allocate_scenes, check, load_supplied_narration, narration_inputs,
    prepare, read, record, validate_story,
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError('Frozen input changed; create a new version: ' + str(path))
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def voice(episode):
    story = validate_story(read(HERE / f'{episode:02d}/creator-story-v01.json'))
    destination = OUT / f'voice/{episode:02d}/v01'
    destination.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('dots_pilot_voice', ROOT / 'productions/SERIES_20261022_dots_finale/produce.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    speech = shared.speech
    save(destination / 'plan.json', dict(inputs=narration_inputs(story), maximum_requests=len(story['scenes']),
        voice='Aoede', model=speech.MODEL, automatic_retry=False))
    manifest = ROOT / f'outputs/productions/SHORT_20261025_dots_desktop_{episode:02d}/voice-source-v01.json'
    legacy_manifest = destination / 'voice-source.json'
    if not manifest.exists() and legacy_manifest.exists():
        save(manifest, read(legacy_manifest))
    if manifest.exists():
        load_supplied_narration(story, manifest)
        print(json.dumps(dict(event='verified_voice_reused', episode=episode, new_requests=0)), flush=True)
        return
    chunks, segments, proofs, usage = [], [], [], []
    with shared.generation_lock():
        cadence = shared.SubmissionCadence()
        for index, scene in enumerate(story['scenes']):
            parent = destination / f'scene-{index:02d}'
            parent.mkdir(exist_ok=True)
            spoken = scene['narration']
            for rule in sorted(story.get('pronunciations', []), key=lambda x: -len(x['source'])):
                spoken = spoken.replace(rule['source'], rule['target'])
            if not (parent / 'Aoede').exists():
                cadence.before_submission()
            proof = speech.synthesize(parent, spoken, 'Aoede', minimum_seconds=.2)
            source = check(next(f for f in proof['files'] if f['path'].endswith('/voice.wav')))
            with wave.open(str(source), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                    raise ValueError('Unexpected speech PCM')
                frames = wav.getnframes()
                chunks.append(wav.readframes(frames))
            segments.append(dict(index=index, text=scene['narration'], frames=frames, duration_ms=round(frames / 24)))
            proofs.append(record(parent / 'Aoede/verified.json'))
            usage.append(proof['usage'])
            print(json.dumps(dict(event='speech_verified', episode=episode, scene=index, seconds=frames / 24000)), flush=True)
    cuts = allocate_scenes([s['duration_ms'] for s in segments], story['duration_seconds'] * 24)
    with wave.open(str(destination / 'narration.wav'), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b''.join(chunks))
    save(destination / 'timings.json', dict(schema_version=1, provider='gemini', timing_source='wav_frames', segments=segments))
    save(manifest, dict(provider='gemini', model=speech.MODEL, voice='Aoede', inputs=narration_inputs(story),
        timing_source='wav_frames', external_api_calls=len(proofs), verified_requests=len(proofs),
        unknown_previous_requests=0, generation_proofs=proofs, usage=usage,
        artifacts=[dict(record(destination / name), name=name) for name in ('narration.wav', 'timings.json')],
        actual_billing_known=False, voice_selection='User selected Aoede; human final listening pending'))
    load_supplied_narration(story, manifest)
    print(json.dumps(dict(event='voice_complete', episode=episode, scene_seconds=[c / 24 for c in cuts])), flush=True)


def prepare_episode(episode):
    state = OUT / f'render-state-{episode:02d}-v01.json'
    if state.exists():
        destination = ROOT / read(state)['output']
        for item in read(destination / 'preparation.json')['sources']:
            check(item)
        print(destination)
        return
    destination = prepare(HERE / f'{episode:02d}/creator-story-v01.json',
        narration_source=ROOT / f'outputs/productions/SHORT_20261025_dots_desktop_{episode:02d}/voice-source-v01.json')
    save(state, dict(output=destination.relative_to(ROOT).as_posix(), user_approved=False))
    print(destination)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['voice', 'prepare'])
    parser.add_argument('--episode', type=int, choices=[1, 2, 3], required=True)
    args = parser.parse_args()
    (voice if args.command == 'voice' else prepare_episode)(args.episode)
