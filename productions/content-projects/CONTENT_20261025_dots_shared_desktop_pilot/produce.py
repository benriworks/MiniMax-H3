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


def spoken_text(story, scene):
    spoken = scene['narration']
    for rule in sorted(story.get('pronunciations', []), key=lambda x: -len(x['source'])):
        spoken = spoken.replace(rule['source'], rule['target'])
    return spoken


def voice(episode, version='v01'):
    story = validate_story(read(HERE / f'{episode:02d}/creator-story-{version}.json'))
    destination = OUT / f'voice/{episode:02d}/{version}'
    destination.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('dots_pilot_voice', ROOT / 'productions/SERIES_20261022_dots_finale/produce.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    speech = shared.speech
    reusable = {}
    if version == 'v02':
        prior = read(HERE / f'{episode:02d}/creator-story-v01.json')
        old_manifest = ROOT / f'outputs/productions/SHORT_20261025_dots_desktop_{episode:02d}/voice-source-v01.json'
        old_voice, _ = load_supplied_narration(prior, old_manifest)
        for index, scene in enumerate(story['scenes']):
            if index < len(prior['scenes']) and spoken_text(story, scene) == spoken_text(prior, prior['scenes'][index]):
                reusable[index] = old_voice['generation_proofs'][index]
    plan = dict(inputs=narration_inputs(story), maximum_requests=len(story['scenes'])-len(reusable),
        voice='Aoede', model=speech.MODEL, automatic_retry=False)
    if version != 'v01':
        plan['reusable_scene_indices'] = sorted(reusable)
    save(destination / 'plan.json', plan)
    manifest = ROOT / f'outputs/productions/SHORT_20261025_dots_desktop_{episode:02d}/voice-source-{version}.json'
    legacy_manifest = destination / 'voice-source.json'
    if version == 'v01' and not manifest.exists() and legacy_manifest.exists():
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
            spoken = spoken_text(story, scene)
            if index in reusable:
                proof_path = check(reusable[index])
                proof = read(proof_path)
            else:
                if not (parent / 'Aoede').exists():
                    cadence.before_submission()
                proof = speech.synthesize(parent, spoken, 'Aoede', minimum_seconds=.2)
                proof_path = parent / 'Aoede/verified.json'
            source = check(next(f for f in proof['files'] if f['path'].endswith('/voice.wav')))
            with wave.open(str(source), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                    raise ValueError('Unexpected speech PCM')
                frames = wav.getnframes()
                chunks.append(wav.readframes(frames))
            segments.append(dict(index=index, text=scene['narration'], frames=frames, duration_ms=round(frames / 24)))
            proofs.append(record(proof_path))
            usage.append(proof['usage'])
            print(json.dumps(dict(event='speech_verified', episode=episode, scene=index, seconds=frames / 24000)), flush=True)
    cuts = allocate_scenes([s['duration_ms'] for s in segments], story['duration_seconds'] * 24)
    with wave.open(str(destination / 'narration.wav'), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b''.join(chunks))
    save(destination / 'timings.json', dict(schema_version=1, provider='gemini', timing_source='wav_frames', segments=segments))
    save(manifest, dict(provider='gemini', model=speech.MODEL, voice='Aoede', inputs=narration_inputs(story),
        timing_source='wav_frames', external_api_calls=len(proofs)-len(reusable), verified_requests=len(proofs),
        reused_verified_requests=len(reusable),
        unknown_previous_requests=0, generation_proofs=proofs, usage=usage,
        artifacts=[dict(record(destination / name), name=name) for name in ('narration.wav', 'timings.json')],
        actual_billing_known=False, voice_selection='User selected Aoede; human final listening pending'))
    load_supplied_narration(story, manifest)
    print(json.dumps(dict(event='voice_complete', episode=episode, scene_seconds=[c / 24 for c in cuts])), flush=True)


def prepare_episode(episode, version='v01'):
    state = OUT / f'render-state-{episode:02d}-{version}.json'
    if state.exists():
        destination = ROOT / read(state)['output']
        for item in read(destination / 'preparation.json')['sources']:
            check(item)
        print(destination)
        return
    destination = prepare(HERE / f'{episode:02d}/creator-story-{version}.json',
        narration_source=ROOT / f'outputs/productions/SHORT_20261025_dots_desktop_{episode:02d}/voice-source-{version}.json')
    save(state, dict(output=destination.relative_to(ROOT).as_posix(), user_approved=False))
    print(destination)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['voice', 'prepare'])
    parser.add_argument('--episode', type=int, choices=[1, 2, 3], required=True)
    parser.add_argument('--version', choices=['v01', 'v02'], default='v01')
    args = parser.parse_args()
    (voice if args.command == 'voice' else prepare_episode)(args.episode, args.version)
