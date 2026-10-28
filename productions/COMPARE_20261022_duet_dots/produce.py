"""Independent 60–90 second comparison production; no legacy shorts changes.

Paid generation is explicit, sequential, cached, and never automatically retried.
Rendering and release packaging are separate, proof-gated commands.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
import time
import uuid
import wave
import zipfile
from urllib.parse import urlsplit
import numpy as np
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
ID = 'COMPARE_20261022_duet_dots'
OUT_ROOT = ROOT / 'outputs/productions' / ID
STATE = HERE / 'state.json'
FPS = 24
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import (
    check, record, read, run, load_capture, load_supplied_narration,
    narration_inputs, pcm_write, sound_design, units, finish,
)

spec = importlib.util.spec_from_file_location('comparison_gemini_speech', ROOT / 'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py')
speech = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speech)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def voice_story():
    draft = read(HERE / 'script-draft.json')
    if draft['id'] != ID or len(draft['scenes']) != 14:
        raise ValueError('Expected the approved comparison and 14 cuts')
    if ''.join(s['narration'] for s in draft['scenes']) != draft['narration']:
        raise ValueError('Narration differs from approved draft')
    return {'id': ID, 'title': draft['title'], 'voice': 'Aoede', 'rate': 'slightly_brisk',
            'pronunciations': [{'source': k, 'target': v} for k, v in draft['voice']['pronunciations'].items()],
            'scenes': [{'narration': s['narration']} for s in draft['scenes']]}


@contextmanager
def generation_lock():
    lock = HERE / '.generation.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink()


def cadence():
    path = HERE / 'api-cadence.json'
    last = read(path)['last_submission_epoch'] if path.exists() else 0
    delay = last + 22 - time.time()
    if delay > 24:
        raise ValueError('Clock changed; inspect the submission ledger')
    if delay > 0:
        time.sleep(delay)
    save(path, {'last_submission_epoch': time.time(), 'minimum_interval_seconds': 22})


def generation_folder(state):
    folder = (ROOT / state['generation']).resolve(strict=True)
    if folder.parent != OUT_ROOT / 'voice-generations':
        raise ValueError('Unexpected narration folder')
    return folder


def generate():
    story = voice_story()
    with generation_lock():
        if STATE.exists():
            state = read(STATE)
            out = generation_folder(state)
            plan = read(out / 'plan.json')
            if check(plan['draft']) != (HERE / 'script-draft.json').resolve() or plan['inputs'] != narration_inputs(story):
                raise ValueError('Frozen narration changed')
        else:
            out = OUT_ROOT / 'voice-generations' / stamp()
            out.mkdir(parents=True)
            save(out / 'plan.json', {'draft': record(HERE / 'script-draft.json'), 'inputs': narration_inputs(story),
                 'model': speech.MODEL, 'voice': 'Aoede', 'maximum_requests': 14, 'automatic_retry': False})
            state = {'generation': out.relative_to(ROOT).as_posix(), 'status': 'generating'}
            save(STATE, state)
        if (out / 'voice-source.json').exists():
            load_supplied_narration(story, out / 'voice-source.json')
            print(json.dumps({'event': 'speech_reused', 'new_requests': 0}), flush=True)
            return
        proofs, segments, samples, usage = [], [], [], []
        for index, scene in enumerate(story['scenes']):
            parent = out / f'scene-{index:02d}'
            parent.mkdir(exist_ok=True)
            target = parent / 'Aoede'
            cached = target.exists()
            text = scene['narration']
            for rule in sorted(story['pronunciations'], key=lambda x: -len(x['source'])):
                text = text.replace(rule['source'], rule['target'])
            speech.payload(text, 'Aoede')
            if not cached:
                cadence()
            proof = speech.synthesize(parent, text, 'Aoede', minimum_seconds=.2)
            source = check(next(item for item in proof['files'] if item['path'].endswith('/voice.wav')))
            with wave.open(str(source), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                    raise ValueError('Unexpected narration PCM')
                count = wav.getnframes()
                samples.append(wav.readframes(count))
            proofs.append(record(target / 'verified.json'))
            segments.append({'index': index, 'text': scene['narration'], 'frames': count, 'duration_ms': round(count / 24)})
            usage.append(proof['usage'])
            print(json.dumps({'event': 'speech_verified', 'scene': index + 1, 'seconds': round(count / 24000, 3), 'reused': cached}), flush=True)
        with wave.open(str(out / 'narration.wav'), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b''.join(samples))
        save(out / 'timings.json', {'schema_version': 1, 'provider': 'gemini', 'timing_source': 'wav_frames', 'segments': segments})
        save(out / 'voice-source.json', {'provider': 'gemini', 'model': speech.MODEL, 'voice': 'Aoede',
             'inputs': narration_inputs(story), 'timing_source': 'wav_frames', 'external_api_calls': 14,
             'automatic_retry': False, 'generation_proofs': proofs, 'usage': usage, 'actual_billing_known': False,
             'artifacts': [dict(record(out / name), name=name) for name in ['narration.wav', 'timings.json']]})
        load_supplied_narration(story, out / 'voice-source.json')
        state['status'] = 'speech_generated'
        save(STATE, state)
        print(json.dumps({'event': 'all_speech_verified', 'seconds': sum(s['frames'] for s in segments) / 24000}), flush=True)


LAYOUTS = {
    'C03': {'panels': [{'label': '予定を確認', 'detail': '灯台珈琲の打ち合わせ', 'icon': 'calendar'}, {'label': '会議資料を準備', 'detail': '判断が必要な点を整理', 'icon': 'document', 'tone': 'blue'}], 'note': '依頼の例・実行比較は未実施'},
    'C04': {'panels': [{'label': '手元のPC', 'detail': '閉じても', 'icon': 'laptop', 'motion': 'close'}, {'label': 'クラウドの仕事', 'detail': '続けられる', 'icon': 'cloud', 'tone': 'blue'}]},
    'C05': {'panels': [{'label': 'Duet', 'detail': '朝の要点まとめ', 'icon': 'message'}, {'label': '一定間隔で確認', 'detail': '常時監視ではない', 'icon': 'clock', 'tone': 'blue'}]},
    'C06': {'panels': [{'label': 'dotsの自発フォロー', 'detail': '必要なフォローを考える', 'icon': 'message'}, {'label': '定時の確認', 'detail': '予定として設定する', 'icon': 'calendar', 'tone': 'blue'}]},
    'C09': {'connection': 'local', 'panels': [{'label': 'dots → Codex', 'detail': '許可した手元のPC', 'icon': 'laptop'}, {'label': '作業を進める条件', 'detail': 'PCがオンライン', 'icon': 'handoff', 'tone': 'blue'}], 'note': '許可・オンライン・アプリ起動'},
    'C11': {'panels': [{'label': 'Duet', 'detail': 'Claudeと共通枠', 'icon': 'meter'}, {'label': '背景の確認', 'detail': '動く分も枠を使う', 'icon': 'clock', 'tone': 'blue'}]},
    'C12': {'panels': [{'label': 'dotsとの会話', 'detail': 'ChatGPT枠の対象外', 'icon': 'message'}], 'note': '実作業の利用枠とは別'},
    'C13': {'panels': [{'label': 'Workの作業', 'detail': 'Workの枠を使う', 'icon': 'document'}, {'label': 'Codexの作業', 'detail': 'Codexの枠を使う', 'icon': 'laptop', 'tone': 'blue'}]},
}
MOTION_INTERVALS = {'C01': (0, 36), 'C10': (36, 48), 'C14': (84, 40)}
MOTION_PROOF = ROOT / 'outputs/characters/explainer-motion-20261022/duet-dots-haruka/verification.json'


def allocate(sample_counts, target_seconds=None):
    """Keep every original sample, with capped cuts and small non-overlapping gaps."""
    durations = [max(30, math.ceil(count / 1000) + 6) for count in sample_counts]
    durations[9] = max(durations[9], 54)  # Entire 2-second insight interval plus breath.
    if max(durations) > 192:
        raise ValueError('Measured narration exceeds the approved 8-second cut; review before changing timing')
    target_seconds = target_seconds or max(60, math.ceil(sum(durations) / FPS + 2))
    total = max(target_seconds * FPS, math.ceil(sum(durations) / FPS) * FPS)
    if not 1440 <= total <= 2160:
        raise ValueError('Measured comparison cannot fit 60–90 seconds')
    remaining = total - sum(durations)
    while remaining:
        changed = False
        for i in range(len(durations)):
            if durations[i] < 192 and remaining:
                durations[i] += 1
                remaining -= 1
                changed = True
        if not changed:
            raise ValueError('No space remains inside the approved cut limit')
    return durations, total


def official_url(url):
    if url == 'https://learn.chatgpt.com/docs/dots':
        return True
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and
            ((parsed.netloc == 'claude.com' and parsed.path.startswith('/resources/articles/'))
             or (parsed.netloc == 'support.claude.com' and parsed.path.startswith('/en/articles/'))))


def capture_assets():
    manifest_path = HERE / 'captures/manifest.json'
    manifest = read(manifest_path)
    if manifest.get('root_visual_review_status') != 'preferred_assets_passed':
        raise ValueError('Comparison requires parent-reviewed official crops')
    reviewed = set(manifest['root_visual_review']['asset_ids'])
    assets, sources = {}, [record(manifest_path)]
    for item in manifest['public_assets']:
        if not item.get('preferred'):
            continue
        if item['id'] not in reviewed or not official_url(item['source_url']):
            raise ValueError('Official crop is not approved for this comparison')
        source, proof_path = check(item['artifact']), check(item['proof'])
        proof = read(proof_path)
        descriptor = {k: item[k] for k in ['origin', 'title', 'source_url']}
        descriptor.update(path=source.relative_to(ROOT).as_posix(), proof=proof_path.relative_to(ROOT).as_posix())
        source, bound = load_capture(descriptor)
        if proof.get('content_modified') is not False or proof.get('personal_information_excluded') is not True:
            raise ValueError('Official crop must preserve source pixels and exclude personal details')
        context = check(proof['context'])
        crop, original = proof['clip'], proof['context_clip']
        x, y = crop['x'] - original['x'], crop['y'] - original['y']
        with Image.open(source) as actual, Image.open(context) as full:
            expected = full.crop((x, y, x + crop['width'], y + crop['height']))
            if ImageChops.difference(actual.convert('RGB'), expected.convert('RGB')).getbbox():
                raise ValueError('Official image is not an exact crop of its source')
        sources.extend(bound)
        sources.append(record(check(proof['raw_metadata'])))
        assets[item['scene_id']] = (source, descriptor, item)
    if set(assets) != {'C02', 'C07', 'C08'} or any(p['total_public_quoted_words'] > 25 for p in manifest['pages']):
        raise ValueError('Expected three official scenes within each source quote budget')
    return assets, sources


def motion_asset():
    proof = read(MOTION_PROOF)
    source = check(proof['artifact'])
    if (proof.get('provider') != 'minimax' or not proof['execution']['success']
            or proof.get('review_status') != 'visual_review_passed'
            or proof.get('root_visual_review', {}).get('status') != 'passed'):
        raise ValueError('Actual reviewed MiniMax motion is required')
    meta = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-of', 'json', source, capture=True).stdout)['streams'][0]
    if (int(meta['width']), int(meta['height']), meta['avg_frame_rate'], int(meta['nb_frames'])) != (768, 1376, '24/1', 124):
        raise ValueError('Presenter video differs from its approved geometry or duration')
    run('ffmpeg', '-v', 'error', '-xerror', '-i', source, '-f', 'null', '-')
    return source, [record(MOTION_PROOF), record(source), record(check(proof['source_presenter']))]


def current_output():
    state = read(STATE)
    out = (ROOT / state['output']).resolve(strict=True)
    if out.parent != OUT_ROOT:
        raise ValueError('Output is outside this comparison')
    return out


def prepare():
    state = read(STATE)
    if state.get('output'):
        out = current_output()
        for item in read(out / 'preparation.json')['sources']:
            check(item)
        print(json.dumps({'event': 'prepared_reused', 'output': str(out)}), flush=True)
        return out
    voice_input = voice_story()
    voice, voice_sources = load_supplied_narration(voice_input, generation_folder(state) / 'voice-source.json')
    draft = read(HERE / 'script-draft.json')
    phrases = read(HERE / 'caption-phrases.json')['scenes']
    captures, sources = capture_assets()
    motion, motion_sources = motion_asset()
    sources += motion_sources + voice_sources + [record(HERE / name) for name in ['script-draft.json', 'caption-phrases.json', 'sources.json', 'produce.py']]
    sources += [record(ROOT / 'tools/studio/shorts_creator.py'), record(Path(speech.__file__))]
    files = {a['name']: check(a) for a in voice['artifacts']}
    sources += [record(p) for p in files.values()]
    timing = read(files['timings.json'])['segments']
    durations, total = allocate([s['frames'] for s in timing])
    with wave.open(str(files['narration.wav']), 'rb') as wav:
        raw = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
    out = OUT_ROOT / stamp()
    pub = out / 'public'
    pub.mkdir(parents=True)
    shutil.copyfile(motion, pub / 'media-00.mp4')
    capture_props = {}
    for index, (scene_id, (source, descriptor, item)) in enumerate(captures.items()):
        name = f'capture-{index:02d}.png'
        shutil.copyfile(source, pub / name)
        capture_props[scene_id] = {k: descriptor[k] for k in ['origin', 'title', 'source_url']} | {'image': name}
    narration = np.zeros(total * 1000, dtype='<i2')
    scenes, captions, measured = [], [], []
    cursor = offset = 0
    for index, (scene, frames, spoken) in enumerate(zip(draft['scenes'], durations, timing, strict=True)):
        start = cursor + 3
        count = spoken['frames']
        narration[start * 1000:start * 1000 + count] = raw[offset:offset + count]
        end = start + math.ceil(count / 1000)
        part = {'id': scene['id'], 'from': cursor, 'duration': frames, 'kind': scene['kind'],
                'eyebrow': 'DUET × DOTS / 比較', 'headline': scene['headline'], 'source_ids': scene['source_ids']}
        if scene['kind'] == 'comparison':
            part.update(layout=scene['layout'], **LAYOUTS[scene['id']])
        elif scene['kind'] == 'source':
            part.update(capture=capture_props[scene['id']], points=scene['on_screen_points'])
        else:
            media_start, play = MOTION_INTERVALS[scene['id']]
            part.update(role='insight' if scene['layout'] == 'midpoint' else scene['layout'], points=scene['on_screen_points'],
                        media='media-00.mp4', mediaStart=media_start, mediaPlayFrames=play, mediaDurationInFrames=124)
            if scene['id'] == 'C14':
                part['note'] = '速さ・品質の優劣は未検証'
        scenes.append(part)
        measured.append({'scene': index, 'id': scene['id'], 'start_ms': round(start * 1000 / FPS),
                         'end_ms': round((start * 1000 + count) / 24), 'duration_ms': spoken['duration_ms'], 'text': scene['narration']})
        parts = phrases[scene['id']]
        if ''.join(parts).replace('\n', '') != scene['narration'] or any(len(p.split('\n')) > 2 or any(units(line) > 12 for line in p.split('\n')) for p in parts):
            raise ValueError('Caption phrases must retain the approved narrative and fit')
        weight, used, at = sum(units(p) for p in parts), 0, start
        for j, text in enumerate(parts):
            used += units(text)
            until = end if j == len(parts) - 1 else start + round((end - start) * used / weight)
            if until - at < 10:
                raise ValueError('Caption is too brief to read')
            captions.append({'start': at, 'end': until, 'text': text})
            at = until
        cursor += frames
        offset += count
    # Preserve original PCM exactly; no speed/pitch conversion or words removed.
    with wave.open(str(out / 'narration.wav'), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(narration.tobytes())
    sound_design(out, scenes, [(s['start_ms'] / 1000, s['end_ms'] / 1000) for s in measured], total / FPS, 'bright_groove_v1')
    save(out / 'props.json', {'title': draft['title'], 'durationInFrames': total, 'mode': 'production', 'showGuides': False, 'scenes': scenes, 'captions': captions})
    save(out / 'story.json', {**voice_input, 'duration_seconds': total / FPS, 'scenes': draft['scenes'], 'information_checked_date': '2026-10-23', 'captures_date': '2026-10-22'})
    save(out / 'voice-source.json', voice)
    save(out / 'timings.json', {'policy': 'measured_unmodified_pcm_padded_cuts_v1', 'segments': measured, 'caption_timing': 'display-unit proportional within measured speech, not word forced alignment', 'source_audio_included': False})
    def timecode(frame):
        ms = round(frame * 1000 / FPS)
        return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'
    (out / 'captions.srt').write_text('\n\n'.join(f"{i+1}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}" for i, c in enumerate(captions)) + '\n', encoding='utf-8')
    sources += [record(out / name) for name in ['story.json', 'props.json', 'narration.wav', 'music.wav', 'effects.wav', 'voice-source.json', 'timings.json', 'captions.srt']]
    sources += [record(p) for p in pub.iterdir()]
    save(out / 'preparation.json', {'sources': sources, 'narration_provider': 'gemini', 'external_api_calls': 14,
         'new_generation': True, 'new_video_generation': False, 'new_video_generation_proof': record(MOTION_PROOF),
         'source_audio_included': False, 'on_screen_tool_credit': False, 'actual_comparative_benchmark': False,
         'motion_intervals': MOTION_INTERVALS, 'private_context_excluded_from_delivery': True})
    state.update(output=out.relative_to(ROOT).as_posix(), status='prepared')
    save(STATE, state)
    print(json.dumps({'event': 'prepared', 'output': str(out), 'seconds': total / FPS, 'cut_seconds': [round(x / FPS, 3) for x in durations]}), flush=True)
    return out


def validate_preparation(out):
    prep = read(out / 'preparation.json')
    for item in prep['sources']:
        check(item)
    if prep['source_audio_included'] is not False:
        raise ValueError('Source audio must be excluded')
    props = read(out / 'props.json')
    if props['mode'] != 'production' or not 1440 <= props['durationInFrames'] <= 2160 or len(props['scenes']) != 14:
        raise ValueError('Invalid comparison production props')
    return props


def render(stills_only=False):
    out = current_output()
    validate_preparation(out)
    args = ['node', ROOT / 'studio/comparison-render.mjs', out]
    if stills_only:
        args.append('--stills-only')
    run(*args)
    state = read(STATE)
    state['status'] = 'preview_ready' if stills_only else 'video_rendered'
    save(STATE, state)


def assemble():
    out = current_output()
    props = validate_preparation(out)
    finish(out)  # Common sample-preserving stereo mix / two-pass loudness / full decode.
    proof = read(out / 'verification.json')
    proof.update(composition='ProductComparison', source_audio_included=False,
                 presenter_motion_intervals=MOTION_INTERVALS, actual_comparative_benchmark=False,
                 information_checked_date='2026-10-23', captures_date='2026-10-22')
    save(out / 'verification.json', proof)
    seconds = props['durationInFrames'] / FPS
    title = read(out / 'story.json')['title']
    (out / 'title.txt').write_text(title + '\n', encoding='utf-8')
    sources = read(HERE / 'sources.json')['sources']
    description = f'''Claude Duet と ChatGPT の dots を、3つのポイントで紹介します。

・知らせ方：朝の要点まとめ・一定間隔の確認と、自発的なフォロー・定時の予定
・作業の見え方：ブラウザー確認・操作の引き継ぎ・許可した手元PC
・利用枠：会話と実作業で使う枠の違い

Duetは2026年10月21日発表。現在は米国のPro・Max向け招待待ちで、日本は対象外です。dotsも段階提供のため、利用状況や条件は公式情報をご確認ください。

情報確認：2026年10月23日。公式画面の撮影：2026年10月22日。
本動画は非公式の解説です。OpenAI、Anthropicによる制作・公認ではありません。
人物の森川遥とカフェ「灯台珈琲」は架空です。カフェの依頼は説明用の例で、両製品を使った実行比較や速度・品質の優劣検証は行っていません。
dotsの操作画面は、OpenAIが公開したインタラクティブ説明例の引用です。当方の実アカウントで行った比較実演ではありません。
利用条件・機能は変更されることがあります。

出典（公式）：
'''
    description += '\n\n'.join(s['title'] + '\n' + s['url'] for s in sources)
    description += '\n\n#ChatGPT #Claude #Codex #AI活用\n'
    (out / 'description.txt').write_text(description, encoding='utf-8')
    public_sources = {'information_checked_date': '2026-10-23', 'captures_date': '2026-10-22',
                      'sources': [{k: s[k] for k in ['id', 'title', 'publisher', 'url']} for s in sources],
                      'fictional_materials_only': True, 'actual_comparative_benchmark': False,
                      'official_interactive_illustration_not_our_execution': ['C08']}
    save(out / 'sources-public.json', public_sources)
    (out / 'README_JA.txt').write_text(f'''{title}

{seconds:g}秒 / 1080×1920 / 24fps / H.264・AAC
Aoedeナレーション14区間。元の発話PCMを保持し、間を空けて配置。
3枚の公式引用画像、架空の人物動画、上下パネルの動図を使用。
人物動画は思考・ひらめき・締めの異なる区間を各1回だけ使い、残りは自作カードへ切り替え。
生成動画の元音声は含めていません。映像内に生成ツール名の表示はありません。
情報確認2026-10-23、公式画像撮影2026-10-22。出典・公開用説明文はdescription.txt。

字幕の短句時刻は実発話区間内で文字量から配分しており、単語アラインメントではありません。
AI補助による目視・聴感確認と利用者の採否は別です。YouTubeへの投稿はしていません。
private原本・会話履歴・API設定は配布ZIPに含めません。
''', encoding='utf-8')
    (out / 'index.html').write_text(f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{margin:0;background:#f4f1eb;color:#252d31;font-family:Meiryo,sans-serif}}main{{max-width:1000px;margin:auto;padding:28px;display:flex;gap:32px;flex-wrap:wrap}}video{{width:min(100%,370px);max-height:86vh;border-radius:16px;background:#111}}section{{max-width:500px}}h1{{font-size:30px;line-height:1.5}}a{{color:#355f48}}p{{line-height:1.8}}img{{width:100%}}</style><main><video controls playsinline preload="metadata" poster="cover.png" src="shorts-creator.mp4"></video><section><h1>{title}</h1><p>{seconds:g}秒・14カット。公式引用、人物動画、図解で3つの違いを紹介します。</p><p><a href="shorts-creator.mp4" download>動画を保存</a> / <a href="comparison-delivery.zip" download>制作一式を保存</a></p><p><a href="description.txt">YouTube説明文と出典</a> / <a href="captions.srt">字幕</a></p><p>情報確認2026-10-23、画像撮影2026-10-22。非公式解説。人物とカフェは架空です。公式サイトの説明例と自作図解を使い、製品の実行性能は比較していません。</p><details><summary>場面一覧</summary><img src="contact-sheet.png" alt="14カットの場面一覧"></details></section></main></html>''', encoding='utf-8')
    state = read(STATE)
    state['status'] = 'assembled_awaiting_review'
    save(STATE, state)


def review(review_path):
    out = current_output()
    validate_preparation(out)
    evidence = read(review_path)
    preview = read(out / 'preview.json')
    if (evidence.get('all_14_scenes_visually_reviewed') is not True
            or evidence.get('narration_listened') is not True
            or evidence.get('source_images_accurate_and_legible') is not True
            or evidence.get('motion_intervals_and_summary_reviewed') is not True
            or evidence.get('no_private_content') is not True
            or evidence.get('user_approved') is not False):
        raise ValueError('Actual visual and listening review evidence is required')
    for item in preview['images']:
        check(item)
    proof = read(out / 'verification.json')
    check(proof['delivery'])
    proof.update(review_status='verified_candidate_awaiting_user_review', visual_and_listening_review=record(review_path), user_approved=False)
    save(out / 'verification.json', proof)
    state = read(STATE)
    state['status'] = 'reviewed'
    save(STATE, state)


def package():
    out = current_output()
    validate_preparation(out)
    proof = read(out / 'verification.json')
    if proof['review_status'] != 'verified_candidate_awaiting_user_review':
        raise ValueError('Review the actual delivery before packaging')
    check(proof['delivery'])
    check(proof['visual_and_listening_review'])
    delivery = out / 'delivery'
    delivery.mkdir(exist_ok=False)
    copies = {'shorts-creator.mp4': 'duet-vs-dots-3-differences.mp4', 'cover.png': 'cover.png',
              'captions.srt': 'captions.srt', 'title.txt': 'title.txt', 'description.txt': 'description.txt',
              'sources-public.json': 'sources.json', 'README_JA.txt': 'README_JA.txt'}
    for source, target in copies.items():
        shutil.copyfile(out / source, delivery / target)
    sources = read(HERE / 'captures/manifest.json')['public_assets']
    public_proofs = []
    for source in sources:
        if not source.get('preferred'):
            continue
        image_path = check(source['artifact'])
        target = delivery / 'official-captures' / image_path.name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(image_path, target)
        original = read(check(source['proof']))
        public_proofs.append({'id': source['id'], 'scene_id': source['scene_id'], 'file': target.relative_to(delivery).as_posix(),
             'sha256': source['artifact']['sha256'], 'source_url': source['source_url'], 'title': source['title'],
             'captured_at': original['captured_at'], 'quote_words': source['quoted_words'], 'content_modified': False,
             'pixel_exact_crop_verified': True, 'personal_information_excluded': True})
    save(delivery / 'official-captures/provenance.json', public_proofs)
    save(delivery / 'verification-public.json', {'review_status': proof['review_status'], 'user_approved': False,
         'ai_assisted_visual_and_listening_review': True, 'full_decode_verified': proof['full_decode_verified'],
         'width': 1080, 'height': 1920, 'fps': 24, 'seconds': read(out / 'props.json')['durationInFrames'] / FPS,
         'source_audio_included': False, 'loudness': proof['loudness'], 'private_context_excluded': True,
         's3_uploaded': False, 'youtube_uploaded': False})
    members = []
    for path in sorted(delivery.rglob('*')):
        if path.is_file():
            item = record(path)
            item['path'] = path.relative_to(delivery).as_posix()
            members.append(item)
    save(delivery / 'manifest.json', {'schema_version': 1, 'members': members, 'manifest_self_excluded': True})
    archive = out / 'comparison-delivery.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as target:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                target.write(path, path.relative_to(delivery).as_posix())
    import hashlib
    with zipfile.ZipFile(archive) as result:
        if result.testzip() is not None or set(result.namelist()) != {m['path'] for m in members} | {'manifest.json'}:
            raise ValueError('ZIP membership or CRC mismatch')
        for item in members:
            content = result.read(item['path'])
            if len(content) != item['bytes'] or hashlib.sha256(content).hexdigest().upper() != item['sha256']:
                raise ValueError('ZIP member hash mismatch')
    save(out / 'delivery-manifest.json', {'archive': record(archive), 'video': record(delivery / copies['shorts-creator.mp4']),
         'zip_member_hashes_verified': True, 'private_context_excluded': True, 's3_uploaded': False, 'youtube_uploaded': False})
    state = read(STATE)
    state['status'] = 'packaged'
    save(STATE, state)
    print(json.dumps({'event': 'packaged', 'output': str(out), 'archive': str(archive)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['generate', 'prepare', 'stills', 'render', 'assemble', 'review', 'package'])
    parser.add_argument('--review-evidence', type=Path)
    args = parser.parse_args()
    if args.command == 'generate':
        generate()
    elif args.command == 'prepare':
        prepare()
    elif args.command in ['stills', 'render']:
        render(stills_only=args.command == 'stills')
    elif args.command == 'assemble':
        assemble()
    elif args.command == 'review':
        if args.review_evidence is None:
            parser.error('--review-evidence is required')
        review(args.review_evidence.resolve(strict=True))
    elif args.command == 'package':
        package()


if __name__ == '__main__':
    main()
