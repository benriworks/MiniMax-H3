"""Produce dots episodes 5–9 with verified, resumable Aoede narration.

Each command selects --episode 5 (or 05), through 9, or all. Generation is
sequential and never retries an incomplete/unknown provider submission.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import argparse
import copy
import hashlib
import html
import importlib.util
import json
import shutil
import sys
import time
import uuid
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import (
    audio_signature, check, finish, load_supplied_narration, narration_inputs, prepare, read,
    record, run, validate_story,
)

spec = importlib.util.spec_from_file_location(
    'dots_finale_gemini_speech',
    ROOT / 'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py',
)
speech = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speech)

EPISODES = {
    5: ('memory', '記憶と好み'),
    6: ('channels', '会話と通話'),
    7: ('schedule', '定期実行'),
    8: ('research', '先回り調査'),
    9: ('controls', '権限と停止'),
}
CHECKED_DATE = '2026-10-22'
INTERVAL_SECONDS = 22


def save(path, value):
    """Replace metadata atomically; no provider headers or credentials enter it."""
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex[:8])
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def selected_episodes(value):
    if value == 'all':
        return list(EPISODES)
    if value not in {str(n) for n in EPISODES} | {f'{n:02d}' for n in EPISODES}:
        raise ValueError('Select episode 5–9 or all')
    return [int(value)]


def preserved_deliveries():
    original = ROOT / 'outputs/productions/SERIES_20261005_dots/20261005T153642158910Z/release'
    files = sorted(original.glob('*/dots-*.mp4'))
    if len(files) != 9:
        raise ValueError('Expected nine preserved original episodes')
    files.append(ROOT / 'outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/release/dots-02-extra-cloud-benefits.mp4')
    for production in ['SHORT_20261022_dots_03_aoede', 'SHORT_20261022_dots_04_editorial']:
        files.append(check(read(ROOT / 'productions' / production / 'delivery.json')['video']))
    return [record(path) for path in files]


@contextmanager
def generation_lock():
    """Prevent concurrent batches from bypassing the shared request cadence."""
    path = HERE / '.generation.lock'
    with path.open('x', encoding='utf-8') as stream:
        stream.write(datetime.now(timezone.utc).isoformat())
    try:
        yield
    finally:
        path.unlink()


class SubmissionCadence:
    def __init__(self):
        self.path = HERE / 'api-cadence.json'

    def before_submission(self):
        last = read(self.path)['last_submission_epoch'] if self.path.exists() else 0
        wait = max(0, INTERVAL_SECONDS - (time.time() - last))
        # An unusually future-dated record needs inspection instead of a long wait.
        if wait > INTERVAL_SECONDS + 2:
            raise ValueError('Submission clock moved backwards; inspect cadence record')
        if wait:
            time.sleep(wait)
        save(self.path, {'last_submission_epoch': time.time(), 'minimum_interval_seconds': INTERVAL_SECONDS})


def request_accounting(generation, verified_requests):
    """Count an explicit manual recovery without authorizing or retrying a call.

    The original request cap remains in plan.json. An unknown attempt may have
    reached the provider and is included in the total, even though it supplied
    no verified audio and its actual charge is unknown.
    """
    result = {'external_api_calls': verified_requests, 'verified_requests': verified_requests,
              'unknown_previous_requests': 0}
    recovery_path = generation / 'manual-recovery.json'
    if not recovery_path.exists():
        return result
    recovery = read(recovery_path)
    unknown = recovery.get('previous_unknown_requests')
    replacements = recovery.get('manual_replacement_requests_authorized')
    if (type(unknown) is not int or type(replacements) is not int or unknown != 1 or replacements != 1
            or not isinstance(recovery.get('reason'), str) or not recovery['reason'].strip()):
        raise ValueError('Expected one explicitly recorded unknown attempt and one authorized manual replacement')
    result.update(external_api_calls=verified_requests + unknown, unknown_previous_requests=unknown,
                  manual_recovery=record(recovery_path), manual_replacement_requests_authorized=replacements)
    return result


def presenter_story(original, presenter):
    """Add only two visual presenter annotations to the frozen spoken story."""
    story = copy.deepcopy(original)
    if any('presenter' in scene for scene in story['scenes']):
        raise ValueError('The frozen source already has presenter annotations')
    for index, role in [(0, 'hook'), (len(story['scenes']) - 1, 'recap')]:
        scene = story['scenes'][index]
        if scene['kind'] != 'editorial':
            raise ValueError('Presenters may only decorate editorial opening and closing scenes')
        scene['presenter'] = {**presenter, 'role': role}
    without_presenter = copy.deepcopy(story)
    for scene in without_presenter['scenes']:
        scene.pop('presenter', None)
    if (without_presenter != original or narration_inputs(story) != narration_inputs(original)
            or audio_signature(story) != audio_signature(original)):
        raise ValueError('Visual revision altered a frozen narrative or audio input')
    return story


class Production:
    def __init__(self, number):
        if number not in EPISODES:
            raise ValueError('Unknown finale episode')
        self.number = number
        self.slug, self.topic = EPISODES[number]
        self.id = f'SHORT_20261022_dots_{number:02d}_editorial'
        self.here = HERE / f'{number:02d}'
        self.state_path = self.here / 'state.json'
        self.story_path = self.here / 'creator-story.json'
        self.out_root = ROOT / 'outputs/productions' / self.id
        self.video_name = f'dots-{number:02d}-{self.slug}-official.mp4'

    def story(self):
        story = validate_story(read(self.story_path))
        if story['id'] != self.id or story['duration_seconds'] != 30 or story['voice'] != 'Aoede':
            raise ValueError('Finale requires the episode ID, 30 seconds, and Aoede')
        for scene in story['scenes']:
            speech.payload(self.spoken(story, scene), 'Aoede')
        return story

    @staticmethod
    def spoken(story, scene):
        text = scene['narration']
        for rule in sorted(story.get('pronunciations', []), key=lambda item: -len(item['source'])):
            text = text.replace(rule['source'], rule['target'])
        return text

    def generation(self, state):
        path = (ROOT / state['generation']).resolve(strict=True)
        if path.parent != self.out_root / 'voice-generations':
            raise ValueError('Unexpected voice generation directory')
        return path

    def frozen_plan(self, state):
        folder = self.generation(state)
        plan = read(folder / 'plan.json')
        if check(plan['story']) != self.story_path.resolve():
            raise ValueError('Unexpected frozen story')
        if plan['model'] != speech.MODEL or plan['voice'] != 'Aoede':
            raise ValueError('Frozen voice configuration changed')
        return folder, plan

    def generate(self, cadence):
        story = self.story()
        if self.state_path.exists():
            state = read(self.state_path)
            out, plan = self.frozen_plan(state)
        else:
            originals = preserved_deliveries()
            out = self.out_root / 'voice-generations' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
            out.mkdir(parents=True)
            plan = {'story': record(self.story_path), 'inputs': narration_inputs(story),
                    'maximum_requests': len(story['scenes']), 'voice': 'Aoede', 'model': speech.MODEL,
                    'automatic_retry': False, 'existing_deliveries': originals}
            save(out / 'plan.json', plan)
            state = {'generation': out.relative_to(ROOT).as_posix(), 'status': 'generating'}
            save(self.state_path, state)
        for original in plan['existing_deliveries']:
            check(original)
        accounting = request_accounting(out, len(story['scenes']))
        if (out / 'voice-source.json').exists():
            load_supplied_narration(story, out / 'voice-source.json')
            print(json.dumps({'event': 'speech_reused', 'episode': self.number, 'new_requests': 0}), flush=True)
            return
        proofs, segments, samples, usage = [], [], [], []
        new_requests = 0
        for index, scene in enumerate(story['scenes']):
            parent = out / f'scene-{index:02d}'
            parent.mkdir(exist_ok=True)
            target = parent / 'Aoede'
            cached = target.exists()
            # Existing incomplete submissions must be rejected by synthesize before
            # any new call. A completed proof is hash/transcript checked there.
            if not cached:
                cadence.before_submission()
                new_requests += 1
            proof = speech.synthesize(parent, self.spoken(story, scene), 'Aoede', minimum_seconds=.2)
            source = check(next(item for item in proof['files'] if item['path'].endswith('/voice.wav')))
            with wave.open(str(source), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                    raise ValueError('Unexpected scene speech PCM format')
                frames = wav.getnframes()
                samples.append(wav.readframes(frames))
            segments.append({'index': index, 'text': scene['narration'], 'frames': frames, 'duration_ms': round(frames / 24)})
            proofs.append(record(target / 'verified.json'))
            usage.append(proof['usage'])
            print(json.dumps({'event': 'speech_verified', 'episode': self.number, 'scene': index,
                              'seconds': round(frames / 24000, 3), 'reused': cached}), flush=True)
        with wave.open(str(out / 'narration.wav'), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b''.join(samples))
        save(out / 'timings.json', {'schema_version': 1, 'provider': 'gemini', 'timing_source': 'wav_frames', 'segments': segments})
        voice = {'provider': 'gemini', 'model': speech.MODEL, 'voice': 'Aoede', 'inputs': narration_inputs(story),
                 'timing_source': 'wav_frames', **accounting, 'generation_proofs': proofs, 'usage': usage,
                 'artifacts': [dict(record(out / name), name=name) for name in ['narration.wav', 'timings.json']],
                 'voice_selection': 'Aoede selected by user; final episode listening pending', 'actual_billing_known': False}
        save(out / 'voice-source.json', voice)
        load_supplied_narration(story, out / 'voice-source.json')
        state['status'] = 'speech_generated'
        save(self.state_path, state)
        print(json.dumps({'event': 'all_speech_verified', 'episode': self.number, 'new_requests': new_requests,
                          'source': str(out / 'voice-source.json')}), flush=True)

    def prepare(self):
        state = read(self.state_path)
        generation, _ = self.frozen_plan(state)
        if 'output' in state:
            raise ValueError('Video already prepared; reuse its recorded output')
        out = prepare(self.story_path, narration_source=generation / 'voice-source.json')
        state.update(output=out.relative_to(ROOT).as_posix(), status='prepared')
        save(self.state_path, state)

    def revise_visuals(self, presenter_path, presenter_proof):
        """Prepare a separate visual revision; never mutate a frozen voice plan."""
        original = self.story()
        state = read(self.state_path)
        generation, _ = self.frozen_plan(state)
        load_supplied_narration(original, generation / 'voice-source.json')
        if state['status'] not in ['packaged', 'verified_candidate_awaiting_user_review', 'speech_generated']:
            raise ValueError('Finish and review the current render before creating another visual revision')
        asset = Path(presenter_path).resolve(strict=True)
        proof_path = Path(presenter_proof).resolve(strict=True)
        if not asset.is_relative_to(ROOT / 'outputs') or not proof_path.is_relative_to(ROOT / 'outputs'):
            raise ValueError('Presenter image and proof must stay in workspace outputs')
        if asset.suffix.lower() != '.png' or proof_path.suffix.lower() != '.json':
            raise ValueError('Expected a PNG presenter and its JSON proof')
        if check(read(proof_path)['artifact']) != asset:
            raise ValueError('Presenter proof does not match the selected image')
        presenter = {'path': asset.relative_to(ROOT).as_posix(), 'proof': proof_path.relative_to(ROOT).as_posix()}
        visual_story = presenter_story(original, presenter)
        validate_story(visual_story)
        prior = None
        prior_delivery = None
        preserved = []
        if 'output' in state:
            _, prior = self.video_folder()
            prior_proof = read(prior / 'verification.json')
            if prior_proof['review_status'] != 'verified_candidate_awaiting_user_review':
                raise ValueError('Previous completed video needs visual review before audio reuse')
            preserved.append(record(check(prior_proof['delivery'])))
            delivery_path = prior / 'delivery.json'
            if not delivery_path.exists() and (self.here / 'delivery.json').exists():
                delivery_path = self.here / 'delivery.json'
            if delivery_path.exists():
                prior_delivery = read(delivery_path)
                if not check(prior_delivery['video']).is_relative_to(prior):
                    raise ValueError('Previous delivery pointer belongs to another render')
                preserved.extend(record(check(prior_delivery[name])) for name in ['video', 'archive'])
        revision_dir = self.here / 'visual-revisions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        revision_dir.mkdir(parents=True)
        save(revision_dir / 'previous-state.json', state)
        if prior_delivery is not None:
            save(revision_dir / 'previous-delivery.json', prior_delivery)
        render_story = revision_dir / 'creator-story.json'
        save(render_story, visual_story)
        if prior is not None:
            out = prepare(render_story, reuse_audio=prior)
        else:
            out = prepare(render_story, narration_source=generation / 'voice-source.json')
        prep = read(out / 'preparation.json')
        prepared_paths = {(ROOT / entry['path']).resolve() for entry in prep['sources']}
        if asset not in prepared_paths or proof_path not in prepared_paths:
            raise ValueError('Prepared revision did not bind the presenter image and proof')
        if prior is not None and not prep.get('audio_reuse'):
            raise ValueError('Expected existing AAC stream reuse for the completed episode')
        for previous in preserved:
            check(previous)
        receipt = {'original_story': record(self.story_path), 'render_story': record(render_story),
                   'presenter': record(asset), 'presenter_proof': record(proof_path),
                   'previous_state': record(revision_dir / 'previous-state.json'),
                   'previous_output': state.get('output'), 'preserved_files': preserved,
                   'output': out.relative_to(ROOT).as_posix(), 'narration_source': record(generation / 'voice-source.json'),
                   'narration_inputs_unchanged': True, 'audio_signature_unchanged': True,
                   'audio_method': 'previous_aac_stream_copy' if prior is not None else 'saved_verified_pcm_source',
                   'additional_tts_requests': 0, 'presenter_scenes': [0, len(original['scenes']) - 1]}
        if prior_delivery is not None:
            receipt['previous_delivery'] = record(revision_dir / 'previous-delivery.json')
        save(revision_dir / 'revision.json', receipt)
        next_state = copy.deepcopy(state)
        if state.get('visual_revision'):
            next_state.setdefault('previous_visual_revisions', []).append(state['visual_revision'])
        next_state.update(output=out.relative_to(ROOT).as_posix(), status='prepared',
                          render_story=record(render_story), visual_revision=record(revision_dir / 'revision.json'))
        save(self.state_path, next_state)
        print(json.dumps({'event': 'visual_revision_prepared', 'episode': self.number,
                          'output': str(out), 'additional_tts_requests': 0,
                          'audio_method': receipt['audio_method']}), flush=True)

    def video_folder(self):
        state = read(self.state_path)
        out = (ROOT / state['output']).resolve(strict=True)
        if out.parent != self.out_root:
            raise ValueError('Unexpected video output directory')
        self.frozen_plan(state)
        if state.get('visual_revision'):
            revision = read(check(state['visual_revision']))
            render_story = check(state['render_story'])
            if revision['output'] != state['output'] or record(out / 'story.json')['sha256'] != record(render_story)['sha256']:
                raise ValueError('Visual revision and active render disagree')
            for item in [revision['original_story'], revision['presenter'], revision['presenter_proof'],
                         revision['previous_state'], revision['narration_source'], *revision['preserved_files']]:
                check(item)
            if revision.get('previous_delivery'):
                check(revision['previous_delivery'])
        return state, out

    def render(self):
        state, out = self.video_folder()
        if not (out / 'render.json').exists():
            run('node', ROOT / 'studio/creator-render.mjs', out)
        if not (out / 'verification.json').exists():
            finish(out)
        if state['status'] not in ['verified_candidate_awaiting_user_review', 'packaged']:
            state['status'] = 'awaiting_visual_review'
            save(self.state_path, state)

    def review(self, note):
        if not note or not note.strip():
            raise ValueError('Inspect the completed frames and provide a concrete review note')
        state, out = self.video_folder()
        proof = read(out / 'verification.json')
        check(proof['delivery'])
        previews = sorted(out.glob('preview-*.png'))
        if len(previews) != len(read(out / 'story.json')['scenes']):
            raise ValueError('Every scene needs completed preview evidence')
        proof.update(review_status='verified_candidate_awaiting_user_review', user_approved=False,
                     visual_review={'method': 'AI-assisted visual inspection', 'note': note,
                                    'reviewed_at': datetime.now(timezone.utc).isoformat(),
                                    'evidence': [record(p) for p in previews] + [record(out / 'contact-sheet.png')]},
                     listening_review='Aoede selected by user in audition; final episode listening review pending.',
                     fact_review={'checked_date': CHECKED_DATE, 'sources': record(self.here / 'SOURCES_JA.md')})
        save(out / 'verification.json', proof)
        state['status'] = proof['review_status']
        save(self.state_path, state)

    def package(self):
        state, out = self.video_folder()
        proof = read(out / 'verification.json')
        if proof['review_status'] != 'verified_candidate_awaiting_user_review':
            raise ValueError('Visual review required before packaging')
        check(proof['delivery'])
        for original in read(self.generation(state) / 'plan.json')['existing_deliveries']:
            check(original)
        story = read(out / 'story.json')
        release = out / 'release'
        release.mkdir(exist_ok=False)
        for source, name in [(out / 'shorts-creator.mp4', self.video_name), (out / 'cover.png', 'cover.png'),
                             (out / 'captions.srt', 'captions.srt')]:
            shutil.copyfile(source, release / name)
        for filename in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md']:
            shutil.copyfile(self.here / filename, release / filename)
        (release / 'narration.txt').write_text('\n'.join(s['narration'] for s in story['scenes']) + '\n', encoding='utf-8')
        quality = {'duration_seconds': 30, 'width': 1080, 'height': 1920, 'fps': 24, 'frames': 720,
                   'voice': 'Aoede', 'model': speech.MODEL, 'music_preset': story['music_preset'],
                   'loudness': proof['loudness'], 'full_decode_verified': proof['full_decode_verified'],
                   'review_status': proof['review_status'], 'final_listening_review': 'pending',
                   'user_approved': False, 'youtube_uploaded': False, 'preserved_existing_videos': 12,
                   'existing_deliveries_unchanged': True, 'information_checked_date': CHECKED_DATE,
                   'official_screenshot_excerpts': sum(s['kind'] == 'source' for s in story['scenes']),
                   'source_capture_scope': 'Official documentation excerpts; not a recorded live product task',
                   'caption_timing': 'display-unit weighting inside measured speech, not word alignment'}
        if state.get('visual_revision'):
            revision = read(check(state['visual_revision']))
            audio_reuse = proof.get('audio_reuse') or {}
            if revision['audio_method'] == 'previous_aac_stream_copy' and not audio_reuse.get('identical_audio_verified'):
                raise ValueError('Revised video did not prove identical audio stream reuse')
            quality.update(character_presenter=True, presenter_scenes=revision['presenter_scenes'],
                           visual_revision_additional_tts_requests=0,
                           previous_completed_video_audio_identical=bool(audio_reuse.get('identical_audio_verified')),
                           previous_visual_delivery_preserved=True)
        save(release / 'quality-report.json', quality)
        title = html.escape((self.here / 'youtube-title.txt').read_text(encoding='utf-8').strip())
        description = html.escape((self.here / 'youtube-description.txt').read_text(encoding='utf-8'))
        page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>body{margin:0;background:#0b1120;color:#f5f1e8;font:18px/1.8 system-ui,"Yu Gothic UI",sans-serif}main{max-width:1050px;margin:auto;padding:28px;display:grid;grid-template-columns:minmax(240px,360px) 1fr;gap:32px}video{width:100%;max-height:85vh;border-radius:18px}h1{font-size:30px;line-height:1.5}a{color:#dfff78}pre{white-space:pre-wrap;font:inherit}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:70vh}}</style><main><video controls playsinline preload="metadata" poster="cover.png" src="__VIDEO__"></video><section><p>DOTS __EPISODE__ / __TOPIC__ · 30秒</p><h1>__TITLE__</h1><p>公式資料の画面引用と作業例の演出。Aoede音声・字幕・オリジナルBGM付き。</p><p><a href="__VIDEO__" download>完成MP4を保存</a> / <a href="captions.srt" download>字幕</a> / <a href="SOURCES_JA.md">公式出典</a></p><details><summary>YouTubeの見出し・説明欄</summary><pre>__TITLE__</pre><pre>__DESCRIPTION__</pre></details><p>完成画面は確認済み。公式資料の画面引用は実機での作業実証映像ではありません。最終試聴・YouTube公開は利用者確認用です。</p></section></main></html>'''
        for token, value in {'__TITLE__': title, '__DESCRIPTION__': description, '__VIDEO__': self.video_name,
                             '__EPISODE__': f'{self.number:02d}', '__TOPIC__': html.escape(self.topic)}.items():
            page = page.replace(token, value)
        (release / 'index.html').write_text(page, encoding='utf-8')
        manifest = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}
                    for p in sorted(release.iterdir())}
        if len(manifest) != 9:
            raise ValueError('Unexpected public package members')
        save(release / 'manifest.json', manifest)
        archive = out / self.video_name.replace('.mp4', '.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
            for p in sorted(release.iterdir()):
                z.write(p, p.name)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None or len(z.namelist()) != 10:
                raise ValueError('ZIP CRC or member count failed')
            for filename, item in manifest.items():
                blob = z.read(filename)
                if len(blob) != item['bytes'] or hashlib.sha256(blob).hexdigest().upper() != item['sha256']:
                    raise ValueError('ZIP size or hash mismatch')
        delivery = {'episode': self.number, 'release': release.relative_to(ROOT).as_posix(),
                    'video': record(release / self.video_name), 'archive': record(archive),
                    'crc_and_all_member_hashes_verified': True, 'members': 10, 'quality': quality}
        save(out / 'delivery.json', delivery)
        save(self.here / 'delivery.json', delivery)
        state['status'] = 'packaged'
        save(self.state_path, state)
        print(json.dumps({'event': 'packaged', 'episode': self.number, 'video': str(release / self.video_name),
                          'bytes': delivery['video']['bytes'], 'sha256': delivery['video']['sha256']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['generate', 'prepare', 'revise-visuals', 'render', 'review', 'package'])
    parser.add_argument('--episode', required=True, help='5–9, 05–09, or all')
    parser.add_argument('--note', help='Concrete note after inspecting completed frame evidence')
    parser.add_argument('--presenter', type=Path, help='Verified transparent presenter PNG in workspace outputs')
    parser.add_argument('--presenter-proof', type=Path, help='Presenter JSON proof binding the PNG artifact')
    args = parser.parse_args()
    productions = [Production(number) for number in selected_episodes(args.episode)]
    if args.command == 'generate':
        # Validate the whole selected batch before the first paid request.
        for production in productions:
            production.story()
            if production.state_path.exists():
                production.frozen_plan(read(production.state_path))
        with generation_lock():
            cadence = SubmissionCadence()
            for production in productions:
                production.generate(cadence)
    else:
        if args.command == 'review' and not args.note:
            raise ValueError('--note is required after visually inspecting each selected episode')
        if args.command == 'revise-visuals' and (args.presenter is None or args.presenter_proof is None):
            raise ValueError('--presenter and --presenter-proof are required for a visual-only revision')
        for production in productions:
            if args.command == 'review':
                production.review(args.note)
            elif args.command == 'revise-visuals':
                production.revise_visuals(args.presenter, args.presenter_proof)
            else:
                getattr(production, args.command)()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, (ValueError, RuntimeError))
                          else 'Production stopped; inspect local state without resubmitting speech.'}), flush=True)
        raise SystemExit(1)
