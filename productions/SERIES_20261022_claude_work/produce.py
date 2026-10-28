"""Claude work shorts: isolated orchestration over the verified dots pipeline.

The inherited module is loaded into a private namespace; its files and existing
dots state are never modified. preflight only reads local inputs. Paid speech is
submitted solely by an explicit generate command, with the existing verified
cache, 22-second cadence, frozen plan, and unknown-submission stop behavior.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import load_capture

SPEC = importlib.util.spec_from_file_location(
    'claude_work_private_production_base',
    ROOT / 'productions/SERIES_20261022_dots_finale/produce.py',
)
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
original_preserved_deliveries = base.preserved_deliveries
original_request_accounting = base.request_accounting

EPISODES = {
    1: ('docs', 'メモから企画書'),
    2: ('slides', '同じ企画からスライド'),
    3: ('design', '告知のデザインと修正'),
    4: ('edit', '文書の部分修正'),
    5: ('export', 'Word・PowerPointへの書き出し'),
}
PRESENTER = 'outputs/characters/business-guides-20261022/claude-shiori.png'
KEYFRAME = 'outputs/characters/business-guides-20261022/claude-shiori-office-keyframe.png'
CHECKED_DATE = '2026-10-22'
read, record, check, save = base.read, base.record, base.check, base.save


def request_accounting(generation, verified_requests):
    """Count explicit rejected-attempt history without enabling any retry."""
    result = original_request_accounting(generation, verified_requests)
    history = generation / 'rejected-attempts.json'
    rejected = 0
    if history.exists():
        history_data = read(history)
        for attempt in history_data['attempts']:
            submission = read(check(attempt['submission']))
            check(attempt['request'])
            if (submission.get('status') != 'rejected' or submission.get('error') != 'api_key_invalid'
                    or attempt.get('replacement_authorized') is not True):
                raise ValueError('Rejected request history does not establish an authorized replacement')
            rejected += 1
        result['rejected_attempt_history'] = record(history)
    result['previous_rejected_requests'] = rejected
    result['external_api_calls'] += rejected
    return result


def preserved_deliveries():
    """Freeze the twelve earlier videos plus final and prior dots 5–9 videos."""
    records = original_preserved_deliveries()
    finale = ROOT / 'productions/SERIES_20261022_dots_finale'
    delivery = read(finale / 'delivery.json')
    if len(delivery['episodes']) != 5:
        raise ValueError('Expected the five completed dots finale deliveries')
    records.extend(record(check(episode['video'])) for episode in delivery['episodes'])
    for number in range(5, 10):
        here = finale / f'{number:02d}'
        records.append(record(check(read(here / 'delivery.json')['video'])))
        state = read(here / 'state.json')
        seen = set()
        while state.get('visual_revision') or state.get('character_video_revision'):
            item = state.get('character_video_revision') or state['visual_revision']
            path = check(item)
            if path in seen:
                raise ValueError('Cyclic previous-revision history')
            seen.add(path)
            revision = read(path)
            if revision.get('previous_output'):
                previous = ROOT / revision['previous_output'] / 'delivery.json'
                records.append(record(check(read(previous)['video'])))
            state = read(check(revision['previous_state']))
    return list({item['path']: item for item in records}.values())


# These are private module globals, not edits to the original dots driver.
base.HERE = HERE
base.preserved_deliveries = preserved_deliveries
base.CHECKED_DATE = CHECKED_DATE
base.request_accounting = request_accounting


def selected_episodes(value):
    if value == 'all':
        return list(EPISODES)
    if value not in {str(n) for n in EPISODES} | {f'{n:02d}' for n in EPISODES}:
        raise ValueError('Select Claude episode 1-5 or all')
    return [int(value)]


class Production(base.Production):
    def __init__(self, number):
        if number not in EPISODES:
            raise ValueError('Unknown Claude work episode')
        self.number = number
        self.slug, self.topic = EPISODES[number]
        self.id = f'SHORT_20261022_claude_{number:02d}_work'
        self.here = HERE / f'{number:02d}'
        self.state_path = self.here / 'state.json'
        self.story_path = self.here / 'creator-story.json'
        self.out_root = ROOT / 'outputs/productions' / self.id
        self.video_name = f'claude-{number:02d}-{self.slug}-work.mp4'

    def story(self):
        # The common validator remains the source of truth for scene/capture
        # types. Unsupported lengths or provenance are not silently bypassed.
        story = base.validate_story(read(self.story_path))
        duration = story['duration_seconds']
        if (story['id'] != self.id or type(duration) is not int or duration != 30
                or len(story['scenes']) != 7 or story['voice'] != 'Aoede'):
            raise ValueError('Claude work requires its episode ID, 30 seconds, seven scenes, and Aoede')
        for scene in story['scenes']:
            base.speech.payload(self.spoken(story, scene), 'Aoede')
        return story

    def preflight(self):
        """Read-only local readiness check before any paid generation or prepare."""
        story = self.story()
        text_records = []
        for name in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md']:
            path = self.here / name
            if not path.read_text(encoding='utf-8').strip():
                raise ValueError('Empty publication input: ' + name)
            text_records.append(record(path))
        if not (self.here / 'youtube-title.txt').read_text(encoding='utf-8').startswith('【Claude】'):
            raise ValueError('Claude episode title must start with 【Claude】')
        captures, presenters, media_records = [], [], []
        for index, scene in enumerate(story['scenes']):
            capture = scene.get('capture')
            if capture:
                proof_path = ROOT / capture['proof']
                proof = read(proof_path)
                load_capture(capture)
                if check(proof['artifact']) != (ROOT / capture['path']).resolve():
                    raise ValueError('Capture proof differs from the selected image')
                if proof.get('review_status') != 'capture_review_passed':
                    raise ValueError('Capture requires completed visual/privacy review')
                origin = capture.get('origin')
                if origin not in ['official', 'demonstration'] or proof.get('origin') != origin:
                    raise ValueError('Claude captures require explicit, matching provenance')
                if origin == 'official' and proof.get('source_url') != capture['source_url']:
                    raise ValueError('Official source URL differs from capture proof')
                if origin == 'demonstration' and (capture.get('product') != 'Claude'
                        or proof.get('product') != 'Claude' or proof.get('phase') != capture.get('phase')):
                    raise ValueError('Actual Claude work phase differs from capture proof')
                check(proof['context'])
                captures.append({'scene': index, 'origin': origin, 'phase': capture.get('phase'),
                                 'proof': record(proof_path)})
            presenter = scene.get('presenter')
            if presenter:
                proof_path = ROOT / presenter['proof']
                proof = read(proof_path)
                asset = check(proof['artifact'])
                if (presenter['path'] != PRESENTER or asset != ROOT / PRESENTER
                        or proof.get('review_status') != 'visual_review_passed'
                        or proof.get('source_type') != 'generated_humanoid'
                        or proof.get('transparent') is not True):
                    raise ValueError('Expected the verified transparent Claude presenter')
                presenters.append(index)
            media = scene.get('media')
            if media:
                proof_path = ROOT / media['proof']
                proof = read(proof_path)
                if (check(proof['artifact']) != (ROOT / media['path']).resolve()
                        or proof.get('review_status') != 'visual_review_passed'
                        or proof.get('execution', {}).get('success') is not True):
                    raise ValueError('Character video requires a verified successful generation')
                if proof.get('provider') != 'minimax' or check(proof['source_presenter']) != ROOT / PRESENTER:
                    raise ValueError('Expected MiniMax video tied to the Claude presenter keyframe')
                if record(check(proof['source_keyframe']))['sha256'] != record(ROOT / KEYFRAME)['sha256']:
                    raise ValueError('I2VA input differs from the reviewed Claude office keyframe')
                media_records.append({'scene': index, 'proof': record(proof_path)})
        phases = {item['phase'] for item in captures if item['origin'] == 'demonstration'}
        if (not any(item['origin'] == 'official' for item in captures)
                or not phases.intersection({'before', 'first-output'})
                or not phases.intersection({'revision', 'after', 'export'})):
            raise ValueError('Prepare official citation and actual before/after screen evidence first')
        if not media_records:
            raise ValueError('Prepare the new MiniMax character video before paid speech generation')
        return {'episode': self.number, 'id': self.id, 'duration_seconds': story['duration_seconds'],
                'scenes': len(story['scenes']), 'story': record(self.story_path),
                'publication_inputs': text_records, 'captures': captures, 'presenter_scenes': presenters,
                'character_video_scenes': media_records,
                'paid_requests_submitted': 0}

    def generate(self, cadence):
        self.preflight()
        return super().generate(cadence)

    def prepare(self):
        self.preflight()
        return super().prepare()

    def refresh_prepare(self, note):
        """Explicit new renderer generation, with frozen speech and old files kept."""
        if not note or not note.strip():
            raise ValueError('A renderer revision needs a concrete reason')
        previous, out = self.video_folder()
        generation, _ = self.frozen_plan(previous)
        narration = record(generation / 'voice-source.json')
        base.load_supplied_narration(self.story(), check(narration))
        revision_dir = self.here / 'renderer-revisions' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        revision_dir.mkdir(parents=True)
        save(revision_dir / 'previous-state.json', previous)
        preserved = [record(p) for p in sorted(out.rglob('*')) if p.is_file()]
        next_state = {key: value for key, value in previous.items() if key != 'output'}
        next_state['status'] = 'speech_generated'
        save(self.state_path, next_state)
        try:
            self.prepare()
        except Exception:
            save(self.state_path, previous)
            raise
        state = read(self.state_path)
        for item in preserved:
            check(item)
        check(narration)
        revision = {'reason': note, 'original_story': record(self.story_path),
                    'previous_state': record(revision_dir / 'previous-state.json'),
                    'previous_output': out.relative_to(ROOT).as_posix(), 'output': state['output'],
                    'narration_source': narration, 'additional_tts_requests': 0,
                    'preserved_files': preserved, 'old_output_unchanged': True}
        save(revision_dir / 'revision.json', revision)
        state['renderer_revision'] = record(revision_dir / 'revision.json')
        save(self.state_path, state)

    def render(self):
        """Keep the local renderer's stderr for actionable failure diagnostics."""
        state, out = self.video_folder()
        if not (out / 'render.json').exists():
            log_path = out / ('render-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.log')
            with log_path.open('x', encoding='utf-8') as log:
                result = subprocess.run(['node', str(ROOT / 'studio/creator-render.mjs'), str(out)],
                                        stdout=log, stderr=subprocess.STDOUT,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise RuntimeError(f'Local renderer exited {result.returncode}; inspect {log_path.relative_to(ROOT).as_posix()}')
        if not (out / 'verification.json').exists():
            base.finish(out)
        if state['status'] not in ['verified_candidate_awaiting_user_review', 'packaged']:
            state['status'] = 'awaiting_visual_review'
            save(self.state_path, state)

    def package(self):
        state, out = self.video_folder()
        proof = read(out / 'verification.json')
        if proof['review_status'] != 'verified_candidate_awaiting_user_review':
            raise ValueError('Inspect the completed screen evidence before packaging')
        check(proof['delivery'])
        plan = read(self.generation(state) / 'plan.json')
        for original in plan['existing_deliveries']:
            check(original)
        story = read(out / 'story.json')
        duration = story['duration_seconds']
        props = read(out / 'props.json')
        probe = proof['probe']
        if (props['durationInFrames'] != duration * 24
                or int(probe['streams'][0]['nb_frames']) != duration * 24
                or abs(float(probe['format']['duration']) - duration) >= .002):
            raise ValueError('Completed duration does not match the frozen story')
        for item in read(out / 'preparation.json')['sources'] + read(out / 'render.json')['sources']:
            check(item)
        capture_counts = {}
        for scene in story['scenes']:
            if scene.get('capture'):
                origin = scene['capture']['origin']
                capture_counts[origin] = capture_counts.get(origin, 0) + 1
        quality = {
            'duration_seconds': duration, 'width': 1080, 'height': 1920, 'fps': 24, 'frames': duration * 24,
            'voice': 'Aoede', 'model': base.speech.MODEL, 'music_preset': story['music_preset'],
            'loudness': proof['loudness'], 'full_decode_verified': proof['full_decode_verified'],
            'review_status': proof['review_status'], 'final_listening_review': 'pending',
            'user_approved': False, 'youtube_uploaded': False, 'preserved_existing_videos': len(plan['existing_deliveries']),
            'existing_deliveries_unchanged': True, 'information_checked_date': CHECKED_DATE,
            'capture_scene_counts': capture_counts, 'source_capture_scope': 'Official references and recorded fictional-example work, distinguished by scene provenance',
            'character_presenter': any(scene.get('presenter') for scene in story['scenes']),
            'presenter_scenes': [i for i, scene in enumerate(story['scenes']) if scene.get('presenter')],
            'character_video_scenes': [i for i, scene in enumerate(story['scenes']) if scene.get('media')],
            'caption_timing': 'display-unit weighting inside measured speech, not word alignment',
        }
        if state.get('visual_revision'):
            revision = read(check(state['visual_revision']))
            reuse = proof.get('audio_reuse') or {}
            if revision['audio_method'] == 'previous_aac_stream_copy' and not reuse.get('identical_audio_verified'):
                raise ValueError('Visual revision lacks identical AAC audio proof')
            quality.update(visual_revision_additional_tts_requests=0,
                           previous_completed_video_audio_identical=bool(reuse.get('identical_audio_verified')),
                           previous_visual_delivery_preserved=True)
        release = out / 'release'
        release.mkdir(exist_ok=False)
        for source, name in [(out / 'shorts-creator.mp4', self.video_name), (out / 'cover.png', 'cover.png'),
                             (out / 'captions.srt', 'captions.srt')]:
            shutil.copyfile(source, release / name)
        for name in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md']:
            shutil.copyfile(self.here / name, release / name)
        (release / 'narration.txt').write_text('\n'.join(s['narration'] for s in story['scenes']) + '\n', encoding='utf-8')
        save(release / 'quality-report.json', quality)
        title = html.escape((release / 'youtube-title.txt').read_text(encoding='utf-8').strip())
        description = html.escape((release / 'youtube-description.txt').read_text(encoding='utf-8'))
        page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>body{margin:0;background:#171c25;color:#f5f1e8;font:18px/1.8 system-ui,"Yu Gothic UI",sans-serif}main{max-width:1050px;margin:auto;padding:28px;display:grid;grid-template-columns:minmax(240px,360px) 1fr;gap:32px}video{width:100%;max-height:85vh;border-radius:18px}h1{font-size:30px;line-height:1.5}a{color:#f7b092}pre{white-space:pre-wrap;font:inherit}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:70vh}}</style><main><video controls playsinline preload="metadata" poster="cover.png" src="__VIDEO__"></video><section><p>CLAUDE __EPISODE__ / __TOPIC__ · __SECONDS__秒</p><h1>__TITLE__</h1><p>架空素材を使った作業画面と公式資料の引用。Aoede音声・字幕・オリジナルBGM付き。</p><p><a href="__VIDEO__" download>完成MP4を保存</a> / <a href="captions.srt" download>字幕</a> / <a href="SOURCES_JA.md">出典と実証範囲</a></p><details><summary>YouTubeの見出し・説明欄</summary><pre>__TITLE__</pre><pre>__DESCRIPTION__</pre></details><p>完成画面は確認済み。実際に記録した例と公式資料の説明を区別しています。最終試聴とYouTube公開は未確認です。</p></section></main></html>'''
        for token, value in {'__TITLE__': title, '__DESCRIPTION__': description, '__VIDEO__': self.video_name,
                             '__EPISODE__': f'{self.number:02d}', '__TOPIC__': html.escape(self.topic),
                             '__SECONDS__': str(duration)}.items():
            page = page.replace(token, value)
        (release / 'index.html').write_text(page, encoding='utf-8')
        manifest = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}
                    for p in sorted(release.iterdir())}
        if len(manifest) != 9:
            raise ValueError('Unexpected public package members')
        save(release / 'manifest.json', manifest)
        archive = out / self.video_name.replace('.mp4', '.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
            for path in sorted(release.iterdir()):
                z.write(path, path.name)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None or set(z.namelist()) != set(manifest) | {'manifest.json'} or len(z.namelist()) != 10:
                raise ValueError('ZIP CRC or member set failed')
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
        print(json.dumps({'event': 'packaged', 'episode': self.number, 'video': str(release / self.video_name),
                          'bytes': delivery['video']['bytes'], 'sha256': delivery['video']['sha256']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'generate', 'prepare', 'refresh-prepare', 'revise-visuals', 'render', 'review', 'package'])
    parser.add_argument('--episode', required=True, help='1-5, 01-05, or all')
    parser.add_argument('--note', help='Concrete note after inspecting every completed scene')
    parser.add_argument('--presenter', type=Path)
    parser.add_argument('--presenter-proof', type=Path)
    args = parser.parse_args()
    productions = [Production(number) for number in selected_episodes(args.episode)]
    if args.command == 'generate':
        for production in productions:
            production.preflight()
            if production.state_path.exists():
                production.frozen_plan(read(production.state_path))
        with base.generation_lock():
            cadence = base.SubmissionCadence()
            for production in productions:
                production.generate(cadence)
    else:
        if args.command == 'review' and not args.note:
            raise ValueError('--note is required after inspecting each selected episode')
        if args.command == 'revise-visuals' and (args.presenter is None or args.presenter_proof is None):
            raise ValueError('Select presenter PNG and proof for the visual revision')
        for production in productions:
            if args.command == 'preflight':
                print(json.dumps(production.preflight(), ensure_ascii=False), flush=True)
            elif args.command == 'review':
                production.review(args.note)
            elif args.command == 'refresh-prepare':
                production.refresh_prepare(args.note)
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
                          else 'Production stopped; inspect local inputs/state without resubmitting speech.'}), flush=True)
        raise SystemExit(1)
