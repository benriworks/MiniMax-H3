"""One paired-video draft: reuse six verified Aoede segments, generate the CTA once."""
from pathlib import Path
import importlib.util
import json
import sys
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import check, load_supplied_narration, narration_inputs, prepare, record, validate_story

HERE = Path(__file__).parent
OUT = ROOT / 'outputs/productions/SHORT_20261023_claude_docs_blog'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('pilot_gemini', ROOT / 'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py')
    speech = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(speech)
    story = validate_story(read(HERE / 'creator-story.json'))
    old_state = read(ROOT / 'productions/SERIES_20261022_claude_work/01/state.json')
    old_story = read(ROOT / 'productions/SERIES_20261022_claude_work/01/creator-story.json')
    old_voice = ROOT / old_state['generation'] / 'voice-source.json'
    prior, _ = load_supplied_narration(old_story, old_voice)
    voice_dir = OUT / 'voice-generations/pilot-v01'
    voice_dir.mkdir(parents=True, exist_ok=True)
    state_path = HERE / 'pilot-state.json'
    if state_path.exists():
        state = read(state_path)
        if check(state['story']) != HERE / 'creator-story.json':
            raise ValueError('Story changed after prepare')
        print(json.dumps(state)); return
    proofs, segments, pcm, usage = [], [], [], []
    for index, scene in enumerate(story['scenes']):
        if index < 6:
            if scene['narration'] != old_story['scenes'][index]['narration']:
                raise ValueError('Only the closing may change in this pilot')
            proof_record = prior['generation_proofs'][index]
            proof = read(check(proof_record))
        else:
            proof = speech.synthesize(voice_dir, scene['narration'], 'Aoede', minimum_seconds=.2)
            proof_record = record(voice_dir / 'Aoede/verified.json')
        source = check(next(a for a in proof['files'] if a['path'].endswith('/voice.wav')))
        with wave.open(str(source), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                raise ValueError('Unexpected speech PCM')
            frames = wav.getnframes(); pcm.append(wav.readframes(frames))
        segments.append({'index': index, 'text': scene['narration'], 'frames': frames, 'duration_ms': round(frames / 24)})
        proofs.append(proof_record); usage.append(proof['usage'])
    with wave.open(str(voice_dir / 'narration.wav'), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); wav.writeframes(b''.join(pcm))
    save(voice_dir / 'timings.json', {'schema_version': 1, 'segments': segments, 'timing_source': 'wav_frames'})
    voice = {'provider': 'gemini', 'model': speech.MODEL, 'voice': 'Aoede', 'inputs': narration_inputs(story),
             'generation_proofs': proofs, 'usage': usage, 'new_requests': 1, 'reused_segments': 6,
             'artifacts': [dict(record(voice_dir / n), name=n) for n in ['narration.wav', 'timings.json']],
             'actual_billing_known': False, 'user_approved': False}
    save(voice_dir / 'voice-source.json', voice)
    load_supplied_narration(story, voice_dir / 'voice-source.json')
    output = prepare(HERE / 'creator-story.json', narration_source=voice_dir / 'voice-source.json')
    state = {'story': record(HERE / 'creator-story.json'), 'output': output.relative_to(ROOT).as_posix(),
             'voice_source': record(voice_dir / 'voice-source.json'), 'status': 'prepared', 'user_approved': False}
    save(state_path, state)
    print(json.dumps(state))


if __name__ == '__main__':
    main()
