"""Preserve an unrendered full-frame preparation while refreshing fixed renderer props.

Always reuse the protected completed MP4's AAC. No speech or media generation.
"""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import uuid

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('dots_fullframe_revision', HERE / 'character_video_revision.py')
revision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(revision)
ROOT = revision.ROOT
read, record, check, save = revision.read, revision.record, revision.check, revision.save


def refresh(number, plan):
    production = revision.Production(number)
    state, old = production.video_folder()
    if state['status'] != 'prepared' or (old / 'render.json').exists() or (old / 'shorts-creator.mp4').exists():
        raise ValueError('Only an unrendered prepared output may be superseded')
    receipt = read(check(state['character_video_revision']))
    protected = next(item for item in plan['episodes'] if item['episode'] == number)
    if receipt['previous_output'] != protected['previous_output']:
        raise ValueError('AAC must come from the protected completed edition')
    previous = ROOT / receipt['previous_output']
    old_props = read(old / 'props.json')
    frozen_story = check(receipt['render_story'])
    for clip in receipt['clips']:
        for key in ['artifact', 'proof', 'presenter', 'keyframe']:
            check(clip[key])
    folder = HERE / 'fullframe-revisions' / plan['revision_id'] / 'repreparations' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / 'superseded-state.json', state)
    out = revision.base.prepare(frozen_story, reuse_audio=previous)
    props = read(out / 'props.json')
    comparable = copy.deepcopy(props)
    for index, scene in enumerate(comparable['scenes']):
        if index in receipt['character_video_scenes']:
            if scene.get('mediaPlayFrames') != scene['duration'] or scene.get('mediaDurationInFrames') != 124:
                raise ValueError('dots character must play throughout its original unchanged scene')
            scene.pop('mediaPlayFrames')
            scene.pop('mediaDurationInFrames')
    if comparable != old_props:
        raise ValueError('Refreshing playable frames changed unrelated props or timing')
    if (out / 'captions.srt').read_bytes() != (old / 'captions.srt').read_bytes():
        raise ValueError('Captions changed')
    prep = read(out / 'preparation.json')
    if (prep.get('audio_reuse') or {}).get('method') != 'aac_stream_copy':
        raise ValueError('Expected AAC stream copy')
    for entry in prep['sources']:
        check(entry)
    updated = copy.deepcopy(receipt)
    updated.update(output=out.relative_to(ROOT).as_posix(), superseded_preparation={
        'state':record(folder / 'superseded-state.json'),
        'preparation':record(old / 'preparation.json'), 'props':record(old / 'props.json'),
        'revision':state['character_video_revision'],
        'reason':'Root fixed actual character playback window in shared renderer',
        'audio_and_timing_unchanged':True})
    save(folder / 'revision.json', updated)
    new_state = copy.deepcopy(state)
    new_state.setdefault('superseded_preparations', []).append(updated['superseded_preparation'])
    new_state.update(output=updated['output'], character_video_revision=record(folder / 'revision.json'))
    save(production.state_path, new_state)
    print(json.dumps({'event':'fullframe_reprepared','episode':number,'output':updated['output'],
                      'tts_requests':0,'timing_and_captions_unchanged':True}), flush=True)


if __name__ == '__main__':
    pointer = read(HERE / 'fullframe-revision-plan.json')
    plan_path = check(pointer['plan'])
    plan = read(plan_path)
    # The folder identity is local immutable metadata, not a renderer property.
    plan['revision_id'] = plan_path.parent.name
    for number in [5,6,7,8,9]:
        refresh(number, plan)
