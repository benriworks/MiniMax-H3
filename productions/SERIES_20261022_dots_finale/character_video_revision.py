"""Independent dots character-video revisions with zero speech-generation calls.

prepare changes only first/last visual media, reusing the current completed AAC.
render -> inspect frames -> review --note ... -> package completes each revision.
The existing source stories, voice plans, audio generations, and earlier output
directories remain unchanged. This module has no generate command.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('dots_character_video_private_base', HERE / 'produce.py')
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
read, record, check, save = base.read, base.record, base.check, base.save
ESTABLISHED_CHARACTERS = {
    'outputs/claude-acquired-20260919/raw-0.png': 'male',
    'outputs/characters/programmer-duo-20260920/male-base-start.png': 'male',
    'outputs/characters/programmer-duo-20260920/male-base-victory.png': 'male',
    'outputs/claude-acquired-female-silhouette-20260930/female-keyframe.png': 'female',
}


def verified_clip(media_path, proof_path, start):
    asset = Path(media_path).resolve(strict=True)
    evidence = Path(proof_path).resolve(strict=True)
    if not asset.is_relative_to(ROOT / 'outputs') or not evidence.is_relative_to(ROOT):
        raise ValueError('Character video and proof must stay in this workspace')
    if asset.suffix.lower() != '.mp4' or evidence.suffix.lower() != '.json' or type(start) is not int or start < 0:
        raise ValueError('Expected an MP4, JSON proof, and nonnegative start frame')
    proof = read(evidence)
    if (check(proof['artifact']) != asset or proof.get('review_status') != 'visual_review_passed'
            or proof.get('execution', {}).get('success') is not True or proof.get('provider') != 'minimax'):
        raise ValueError('A reviewed, successful MiniMax character video is required')
    presenter = check(proof['source_presenter'])
    identity = ESTABLISHED_CHARACTERS.get(presenter.relative_to(ROOT).as_posix())
    if identity is None:
        raise ValueError('Use the established episode-one programmer characters')
    keyframe=check(proof['source_keyframe'])
    if record(keyframe)['sha256']!=record(presenter)['sha256']:
        raise ValueError('The I2VA input differs from the established dots character image')
    return {'media': {'path': asset.relative_to(ROOT).as_posix(), 'proof': evidence.relative_to(ROOT).as_posix()},
            'start': start, 'artifact': record(asset), 'proof': record(evidence), 'presenter': record(presenter),
            'keyframe': record(keyframe), 'character': identity}


def replacement_story(original, clips):
    story = copy.deepcopy(original)
    for index, clip in [(0, clips[0]), (len(story['scenes']) - 1, clips[1])]:
        scene = story['scenes'][index]
        if scene['kind'] != 'editorial' or any(key in scene for key in ['media', 'presenter', 'capture']):
            raise ValueError('Expected unmodified editorial opening and closing source scenes')
        scene['media'] = clip['media']
        scene['mediaStart'] = clip['start']
    stripped = copy.deepcopy(story)
    for index in [0, len(story['scenes']) - 1]:
        stripped['scenes'][index].pop('media')
        stripped['scenes'][index].pop('mediaStart')
    if (stripped != original or base.audio_signature(story) != base.audio_signature(original)
            or base.narration_inputs(story) != base.narration_inputs(original)):
        raise ValueError('Character-video revision changed frozen narrative/audio inputs')
    return base.validate_story(story)


class Production(base.Production):
    def video_folder(self):
        state, out = super().video_folder()
        if state.get('character_video_revision'):
            receipt = read(check(state['character_video_revision']))
            if (receipt['output'] != state['output']
                    or check(receipt['render_story']) != check(state['render_story'])
                    or record(out / 'story.json')['sha256'] != state['render_story']['sha256']):
                raise ValueError('Active character-video revision and rendered story disagree')
            for key in ['original_story', 'previous_state', 'previous_delivery', 'narration_source']:
                check(receipt[key])
            for item in receipt['preserved_files']:
                check(item)
            for clip in receipt['clips']:
                for key in ['artifact', 'proof', 'presenter', 'keyframe']:
                    check(clip[key])
        return state, out

    def prepare_revision(self, clips):
        original = self.story()
        state, prior = self.video_folder()
        if state['status'] != 'packaged':
            raise ValueError('Finish the current reviewed package before starting its video revision')
        generation, plan = self.frozen_plan(state)
        base.load_supplied_narration(original, generation / 'voice-source.json')
        for item in plan['existing_deliveries']:
            check(item)
        previous_delivery_path = prior / 'delivery.json'
        if not previous_delivery_path.exists():
            previous_delivery_path = self.here / 'delivery.json'
        previous_delivery = read(previous_delivery_path)
        if not check(previous_delivery['video']).is_relative_to(prior):
            raise ValueError('Previous publication belongs to another output')
        previous_proof = read(prior / 'verification.json')
        if previous_proof['review_status'] != 'verified_candidate_awaiting_user_review':
            raise ValueError('Previous completed video lacks its visual review')
        visual_story = replacement_story(original, clips)
        previous_props = read(prior / 'props.json')
        for index, clip in [(0, clips[0]), (len(original['scenes']) - 1, clips[1])]:
            probe = json.loads(base.run('ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                       '-show_entries', 'stream=width,height,duration', '-of', 'json',
                                       check(clip['artifact']), capture=True).stdout)['streams'][0]
            if (int(probe['width']) < 768 or int(probe['height']) < 1344
                    or float(probe['duration']) + 1 / 24 < (previous_props['scenes'][index]['duration'] + clip['start']) / 24):
                raise ValueError('Character clip cannot cover its unchanged scene duration')
        folder = self.here / 'character-video-revisions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        save(folder / 'previous-state.json', state)
        save(folder / 'previous-delivery.json', previous_delivery)
        render_story = folder / 'creator-story.json'
        save(render_story, visual_story)
        out = base.prepare(render_story, reuse_audio=prior)
        prep = read(out / 'preparation.json')
        if (prep.get('audio_reuse') or {}).get('method') != 'aac_stream_copy':
            raise ValueError('The prepared revision does not reuse the previous completed AAC')
        prepared = {(ROOT / item['path']).resolve() for item in prep['sources']}
        for clip in clips:
            if not {check(clip['artifact']), check(clip['proof'])}.issubset(prepared):
                raise ValueError('The prepared render omits its character-video proof')
        preserved = [record(check(previous_proof['delivery']))]
        preserved.extend(record(check(previous_delivery[key])) for key in ['video', 'archive'])
        receipt = {
            'kind': 'character_video_revision', 'original_story': record(self.story_path),
            'render_story': record(render_story), 'previous_state': record(folder / 'previous-state.json'),
            'previous_delivery': record(folder / 'previous-delivery.json'),
            'previous_output': state['output'], 'preserved_files': preserved,
            'output': out.relative_to(ROOT).as_posix(), 'clips': clips,
            'narration_source': record(generation / 'voice-source.json'),
            'narration_inputs_unchanged': True, 'audio_signature_unchanged': True,
            'middle_scenes_unchanged': True, 'official_source_scenes_unchanged': True,
            'audio_method': 'previous_aac_stream_copy', 'additional_tts_requests': 0,
            'additional_tts_characters': 0, 'character_video_scenes': [0, len(original['scenes']) - 1],
        }
        save(folder / 'revision.json', receipt)
        next_state = copy.deepcopy(state)
        for key in ['visual_revision', 'character_video_revision']:
            if next_state.get(key):
                next_state.setdefault('previous_visual_revisions', []).append(next_state.pop(key))
        next_state.update(output=out.relative_to(ROOT).as_posix(), status='prepared',
                          render_story=record(render_story), character_video_revision=record(folder / 'revision.json'))
        save(self.state_path, next_state)
        print(json.dumps({'event': 'character_video_revision_prepared', 'episode': self.number,
                          'output': str(out), 'additional_tts_requests': 0}), flush=True)

    def package(self):
        state, out = self.video_folder()
        if not state.get('character_video_revision'):
            raise ValueError('This command packages only a new character-video revision')
        receipt = read(check(state['character_video_revision']))
        proof = read(out / 'verification.json')
        reuse = proof.get('audio_reuse') or {}
        if (proof['review_status'] != 'verified_candidate_awaiting_user_review'
                or not reuse.get('identical_audio_verified') or reuse.get('method') != 'aac_stream_copy'):
            raise ValueError('Completed visual review and identical previous AAC audio are required')
        current = check(proof['delivery'])
        previous = read(check(receipt['previous_delivery']))
        prior_release = ROOT / previous['release']
        if check(reuse['source_delivery']) != ROOT / receipt['previous_output'] / 'shorts-creator.mp4':
            raise ValueError('Audio was not copied from the saved previous revision')
        original = read(check(receipt['original_story']))
        expected = replacement_story(original, receipt['clips'])
        if read(out / 'story.json') != expected or read(out / 'props.json')['durationInFrames'] != 720:
            raise ValueError('Final revision differs from the two permitted visual changes')
        for item in read(self.generation(state) / 'plan.json')['existing_deliveries']:
            check(item)
        for item in read(out / 'preparation.json')['sources'] + read(out / 'render.json')['sources']:
            check(item)
        release = out / 'release'
        release.mkdir(exist_ok=False)
        for source, name in [(current, self.video_name), (out / 'cover.png', 'cover.png'), (out / 'captions.srt', 'captions.srt')]:
            shutil.copyfile(source, release / name)
        for name in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md', 'narration.txt', 'index.html']:
            shutil.copyfile(prior_release / name, release / name)
        quality = copy.deepcopy(previous['quality'])
        quality.update(loudness=proof['loudness'], full_decode_verified=proof['full_decode_verified'],
                       review_status=proof['review_status'], character_presenter=False, presenter_scenes=[],
                       character_video=True, character_video_scenes=receipt['character_video_scenes'],
                       visual_revision_additional_tts_requests=0, visual_revision_additional_tts_characters=0,
                       previous_completed_video_audio_identical=True, previous_visual_delivery_preserved=True,
                       middle_scenes_unchanged=True, official_source_scenes_unchanged=True,
                       user_approved=False, final_listening_review='pending', youtube_uploaded=False)
        save(release / 'quality-report.json', quality)
        manifest = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}
                    for p in sorted(release.iterdir())}
        if len(manifest) != 9:
            raise ValueError('Unexpected public package contents')
        save(release / 'manifest.json', manifest)
        archive = out / self.video_name.replace('.mp4', '.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
            for path in sorted(release.iterdir()):
                z.write(path, path.name)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None or len(z.namelist()) != 10 or set(z.namelist()) != set(manifest) | {'manifest.json'}:
                raise ValueError('ZIP CRC or member set differs')
            for name, item in manifest.items():
                blob = z.read(name)
                if len(blob) != item['bytes'] or hashlib.sha256(blob).hexdigest().upper() != item['sha256']:
                    raise ValueError('ZIP member size or hash differs')
        delivery = {'episode': self.number, 'release': release.relative_to(ROOT).as_posix(),
                    'video': record(release / self.video_name), 'archive': record(archive),
                    'crc_and_all_member_hashes_verified': True, 'members': 10, 'quality': quality}
        save(out / 'delivery.json', delivery)
        save(self.here / 'delivery.json', delivery)
        state['status'] = 'packaged'
        save(self.state_path, state)
        print(json.dumps({'event': 'character_video_packaged', 'episode': self.number,
                          'video': str(release / self.video_name), 'additional_tts_requests': 0}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'render', 'review', 'package'])
    parser.add_argument('--episode', required=True, help='5-9 or all')
    parser.add_argument('--hook-media', type=Path)
    parser.add_argument('--hook-proof', type=Path)
    parser.add_argument('--hook-start-frame', type=int, default=0)
    parser.add_argument('--closing-media', type=Path)
    parser.add_argument('--closing-proof', type=Path)
    parser.add_argument('--closing-start-frame', type=int, default=0)
    parser.add_argument('--note')
    args = parser.parse_args()
    productions = [Production(n) for n in base.selected_episodes(args.episode)]
    if args.command == 'prepare':
        if not all([args.hook_media, args.hook_proof, args.closing_media, args.closing_proof]):
            raise ValueError('Choose both character videos and their verification proofs')
        clips = [verified_clip(args.hook_media, args.hook_proof, args.hook_start_frame),
                 verified_clip(args.closing_media, args.closing_proof, args.closing_start_frame)]
        if {clip['character'] for clip in clips} != {'male', 'female'}:
            raise ValueError('Use both the original male and female character videos')
        for production in productions:
            production.prepare_revision(clips)
    elif args.command == 'review':
        if not args.note:
            raise ValueError('Inspect all completed frames before supplying a concrete review note')
        for production in productions:
            production.review(args.note)
    else:
        for production in productions:
            getattr(production, args.command)()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, (ValueError, RuntimeError))
                          else 'Visual revision stopped; inspect the local records.'}), flush=True)
        raise SystemExit(1)
