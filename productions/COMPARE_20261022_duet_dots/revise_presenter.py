"""Visual-only comparison revision. Keeps the prior PCM, caption/cut timing and AAC."""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('comparison_revision_base', HERE / 'produce.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
STATE = HERE / 'presenter-revision-state.json'
PRIOR = p.OUT_ROOT / '20261022T160906439023Z'


def current():
    value = p.read(STATE)
    out = (p.ROOT / value['output']).resolve(strict=True)
    if out.parent != p.OUT_ROOT:
        raise ValueError('Unexpected comparison revision output')
    return out


def prepare(refresh_common=False):
    if STATE.exists() and not refresh_common:
        out = current()
        for item in p.read(out / 'preparation.json')['sources']:
            p.check(item)
        return out
    previous_preparation = p.read(PRIOR / 'preparation.json')
    historical_code = []
    for item in previous_preparation['sources']:
        if Path(item['path']).suffix == '.py':
            historical_code.append(item)
        else:
            p.check(item)
    # Historical source code may evolve for another production. Its recorded
    # versions stay historical; the actual data and finished AAC must still match.
    prior = p.read(PRIOR / 'props.json')
    voice = p.read(PRIOR / 'voice-source.json')
    for artifact in voice['artifacts']:
        p.check(artifact)
    verification = p.read(PRIOR / 'verification.json')
    delivery = p.check(verification['delivery'])
    if verification['review_status'] != 'technical_and_visual_passed_listening_pending':
        raise ValueError('Expected the previously checked comparison')
    out = p.OUT_ROOT / (p.stamp() + '-immersive')
    out.mkdir()
    shutil.copytree(PRIOR / 'public', out / 'public')
    copied = ['story.json', 'narration.wav', 'music.wav', 'effects.wav', 'voice-source.json', 'timings.json', 'captions.srt', 'title.txt', 'description.txt', 'sources-public.json']
    for name in copied:
        shutil.copyfile(PRIOR / name, out / name)
        if p.record(PRIOR / name)['sha256'] != p.record(out / name)['sha256']:
            raise ValueError('Visual-only copy changed: ' + name)
    props = dict(prior, presenterTreatment='immersive')
    p.save(out / 'props.json', props)
    if {k: v for k, v in props.items() if k != 'presenterTreatment'} != prior:
        raise ValueError('Only presenter treatment may change')
    sources = [item for item in previous_preparation['sources'] if Path(item['path']).suffix != '.py']
    sources += [p.record(PRIOR / name) for name in ['preparation.json', 'verification.json', 'render.json']]
    sources += [p.record(delivery), p.record(Path(__file__)), p.record(Path(p.__file__)), p.record(p.ROOT / 'tools/studio/shorts_creator.py')]
    sources += [p.record(out / name) for name in copied + ['props.json']]
    sources += [p.record(path) for path in (out / 'public').rglob('*') if path.is_file()]
    p.save(out / 'preparation.json', {'sources': sources, 'narration_provider': 'gemini', 'external_api_calls': 0,
        'new_generation': False, 'new_video_generation': False, 'source_audio_included': False, 'on_screen_tool_credit': False,
        'visual_revision': 'immersive presenter, existing original intervals and measured 75-second timing',
        'audio_reuse': {'source_delivery': p.record(delivery), 'method': 'aac_stream_copy'},
        'previous_preparation': p.record(PRIOR / 'preparation.json'), 'motion_intervals': p.MOTION_INTERVALS,
        'historical_source_versions': historical_code,
        'private_context_excluded_from_delivery': True, 'narration_listened': False})
    if STATE.exists():
        p.save(HERE / 'presenter-revision-history' / (p.stamp() + '.json'), p.read(STATE))
    p.save(STATE, {'output': out.relative_to(p.ROOT).as_posix(), 'prior': PRIOR.relative_to(p.ROOT).as_posix(), 'status': 'prepared', 'tts_requests': 0})
    print(json.dumps({'event': 'visual_revision_prepared', 'output': str(out), 'seconds': props['durationInFrames'] / 24, 'tts_requests': 0}), flush=True)
    return out


def render(stills_only):
    out = current()
    args = ['node', p.ROOT / 'studio/comparison-render.mjs', out]
    if stills_only:
        args.append('--stills-only')
    p.run(*args)
    state = p.read(STATE)
    state['status'] = 'preview_ready' if stills_only else 'video_rendered'
    p.save(STATE, state)


def assemble():
    out = current()
    p.finish(out)
    proof = p.read(out / 'verification.json')
    if proof.get('audio_reuse', {}).get('identical_audio_verified') is not True:
        raise ValueError('Revision AAC must exactly match the prior delivery')
    proof.update(composition='ProductComparison', source_audio_included=False, narration_listened=False,
                 presenter_treatment='immersive', presenter_motion_intervals=p.MOTION_INTERVALS,
                 actual_comparative_benchmark=False, information_checked_date='2026-10-23', captures_date='2026-10-22')
    p.save(out / 'verification.json', proof)
    # Restore the comparison-specific preview copy overwritten by common finish.
    for name in ['index.html', 'README_JA.txt']:
        shutil.copyfile(PRIOR / name, out / name)
    state = p.read(STATE)
    state['status'] = 'assembled_awaiting_visual_review'
    p.save(STATE, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'stills', 'render', 'assemble'])
    parser.add_argument('--refresh-common', action='store_true', help='Create a new revision after shared implementation changes; preserve prior candidates')
    args = parser.parse_args()
    command = args.command
    if command == 'prepare':
        prepare(args.refresh_common)
    elif command == 'assemble':
        assemble()
    else:
        render(command == 'stills')


if __name__ == '__main__':
    main()
