"""Bounded editorial revisions of dots 05/07 and verified delivery of 05–09.

Uses the existing Gemini adapter and Shorts renderer. Preserves previous edits,
and reuses only scene audio whose exact pronunciation-adjusted transcript matches.
"""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import math
import re
import shutil
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('dots_previous', ROOT / 'productions/SERIES_20261022_dots_finale/produce.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
from tools.studio.shorts_creator import (
    allocate_scenes, check, finish, load_supplied_narration, narration_inputs,
    prepare, read, record, run, units, validate_story,
)
save = old.save


def original(number):
    folder = ROOT / f'productions/SERIES_20261022_dots_finale/{number:02d}'
    state = read(folder / 'state.json')
    story = read(check(state['render_story']))
    voice = ROOT / state['generation'] / 'voice-source.json'
    load_supplied_narration(story, voice)
    delivery = read(folder / 'delivery.json')
    check(delivery['video'])
    return story, voice, delivery


def captions(text):
    tokens = re.findall(r'[A-Za-z0-9]+|.', text)
    count = max(1, math.ceil(units(text) / 20))
    groups, current = [], ''
    target = units(text) / count
    for token in tokens:
        if current and units(current + token) > target + 1 and len(groups) < count - 1:
            groups.append(current)
            current = ''
        current += token
    groups.append(current)
    result = []
    for group in groups:
        lines, line = [], ''
        for token in re.findall(r'[A-Za-z0-9]+|.', group):
            if units(line + token) > 12:
                lines.append(line)
                line = ''
            line += token
        result.append('\n'.join(lines + [line]))
    return result


def scene(layout, headline, narration, body='', items=None, action=None):
    item = {'kind': 'editorial', 'editorial_layout': layout, 'headline': headline,
            'narration': narration, 'captions': captions(narration), 'body': body}
    if items:
        item['items'] = [{'label': a, 'detail': b} for a, b in items]
    if action:
        item['action'] = action
    return item


def build(number):
    baseline, voice_path, delivery = original(number)
    story = copy.deepcopy(baseline)
    story['id'] = f'SHORT_20261023_dots_{number:02d}_final'
    if number == 5:
        story['title'] = '【ChatGPT】dotsは前の話を引き継ぐ？記憶とコンテキストの違い'
        story['duration_seconds'] = 30
        scenes = [
            scene('contrast', '前の話を、\n続きから。', '前の話を引き継ぐ相棒、dots。', '会話をまたぐ文脈', [('前の会話', '好みと決めたこと'), ('次の仕事', '文脈を引き継ぐ')]),
            scene('memory', '好み・決定・仕事を、\nノートに残す。', '好みや決定事項を、会話をまたいでノートに残します。', 'dot独自のノート', [('好み', '文章の調子'), ('決めたこと', '方針と優先順位'), ('進行中の仕事', '次にやること')]),
            copy.deepcopy(baseline['scenes'][2]),
            scene('research', '過去の会話も、\n必要なときに探す。', '必要に応じて、過去の会話も探して使います。', '使う情報を選ぶ', [('現在の会話', 'いまの依頼'), ('過去の会話', '必要な情報を検索')]),
            scene('contrast', '全会話の永久保存、\nとは異なります。', '全会話が、毎回そのまま渡るわけではありません。', '保持と参照の違い', [('ノート', '後の会話へ引き継ぐ'), ('毎回の入力', '必要な文脈を選ぶ')]),
            scene('statement', 'メモリOFFでも、\n消えるとは限らない。', 'メモリをオフにしても、dotの記録は残る場合があります。', 'ChatGPTメモリと\ndotの記録は別', action='保持の範囲を確認'),
            scene('recap', '話が変わっても、\n仕事の続きへ。', '次の会話でも、仕事の続きへ。', '文脈を生かす相棒', [('引き継ぐ', '好み・決定・仕事'), ('使うとき', '必要な情報を選ぶ')], '次回：会話と通話'),
        ]
        note = '会話をまたぐ独自ノート・文脈保持を説明。全会話が毎回そのまま入力されることや永久の完全保存を保証しない。ChatGPT Memoryをオフにしても既存のdotの記録は消えない場合がある。'
    elif number == 7:
        story['title'] = '【ChatGPT】dotsに「毎朝9時に教えて」！定期実行の設定・確認・解除'
        story['duration_seconds'] = 45
        source = copy.deepcopy(baseline['scenes'][1])
        source.update(headline='一覧は会話でも、\nScheduledでも。', narration='確認は会話で「定期実行の一覧を見せて」。画面ならScheduledです。')
        source['captions'] = captions(source['narration'])
        scenes = [
            scene('calendar', '毎朝の確認は、\n会話で頼める。', '毎朝の予定確認。dotsとの会話で頼めます。', '会話から定期実行', [('内容', '今日の予定'), ('時刻', '毎朝9時')]),
            scene('statement', '「毎朝9時に、\n予定を教えて」', '「毎朝九時に、今日の予定を教えて」と依頼。', '毎朝9時に、\n今日の予定を教えて', action='依頼の例'),
            scene('recap', '時刻と期限、\n通知先も伝える。', '日本時間、期限、通知先まで具体的に。', '例：今月末まで', [('時間帯', '日本時間'), ('通知先', 'ChatGPTへ'), ('繰り返し', '毎朝9時')]),
            scene('calendar', '予定表を接続。\n保存結果も確認。', '接続した予定表を対象に、保存した内容も確認してもらいます。', '保存内容を教えて', [('対象', '接続した予定表'), ('確認', '内容と日時')]),
            source,
            scene('contrast', '変更も解除も、\n会話で頼める。', '変更も解除も会話で。「朝八時に変えて」「この定期実行をやめて」。', '依頼の例', [('変更する', '朝8時に変えて'), ('解除する', 'この定期実行をやめて')]),
            scene('permissions', 'Scheduledで、\n無効化・削除も。', 'Scheduled画面から、無効化や削除もできます。', '予約を一覧で管理', [('無効化', '今後の実行を止める'), ('削除', '予約を取り除く')]),
            copy.deepcopy(baseline['scenes'][5]),
            scene('recap', '最後に、\n予約一覧を確認。', '変更や解除の後も、予約一覧を確認しましょう。次は、先回り調査。', '会話でも画面でも', [('設定・変更・解除', '会話で頼める'), ('確認・無効化・削除', 'Scheduledから')], '次回：先回り調査'),
        ]
        note = '会話での登録例、接続した予定表、時刻・期限・通知先、保存結果確認、会話での一覧・変更・解除、Scheduledでの確認・無効化・削除を紹介。Pauseは将来の予約解除ではない。会話例は架空であり実際の定期実行は登録していない。'
    else:
        raise ValueError('Only episodes 5 and 7 need new edits')
    for index, item in enumerate(scenes):
        item['eyebrow'] = baseline['scenes'][0]['eyebrow']
        item['source_ids'] = baseline['scenes'][0]['source_ids']
        if index in [0, len(scenes) - 1]:
            item['media'] = copy.deepcopy(baseline['scenes'][0 if index == 0 else -1]['media'])
            item['mediaStart'] = 0
    story['scenes'] = scenes
    story['editorial'].update(checked_date='2026-10-23', availability_note=note, user_approved=False)
    validate_story(story)
    folder = HERE / f'{number:02d}'
    folder.mkdir(exist_ok=True)
    path = folder / 'creator-story.json'
    if path.exists() and read(path) != story:
        raise ValueError('Frozen story changed; create another revision')
    if not path.exists():
        save(path, story)
        save(folder / 'baseline.json', {'voice_source': record(voice_path), 'video': delivery['video']})
    print(json.dumps({'event': 'story_validated', 'episode': number, 'scenes': len(scenes), 'seconds': story['duration_seconds']}), flush=True)
    return path, story


def generate(number, cadence):
    path, story = build(number)
    baseline = read(HERE / f'{number:02d}/baseline.json')
    previous_voice = read(check(baseline['voice_source']))
    cached = {}
    for entry in previous_voice['generation_proofs']:
        proof = read(check(entry))
        request = read(check(next(a for a in proof['files'] if a['path'].endswith('/request.json'))))
        cached[request['contents'][0]['parts'][0]['text'].split('Transcript:\n', 1)[1]] = entry
    out = ROOT / f'outputs/productions/{story["id"]}/voice-generations/v01'
    out.mkdir(parents=True, exist_ok=True)
    plan = {'story': record(path), 'maximum_requests': sum(old.Production.spoken(story,s) not in cached for s in story['scenes']),
            'model': old.speech.MODEL, 'voice': 'Aoede', 'automatic_retry': False, 'preserved_video': baseline['video']}
    if (out / 'plan.json').exists() and read(out / 'plan.json') != plan:
        raise ValueError('Frozen generation plan changed')
    if not (out / 'plan.json').exists():
        save(out / 'plan.json', plan)
    if (out / 'voice-source.json').exists():
        load_supplied_narration(story, out / 'voice-source.json')
        return
    proofs, samples, segments, usage = [], [], [], []
    for index, item in enumerate(story['scenes']):
        spoken = old.Production.spoken(story, item)
        if spoken in cached:
            entry = cached[spoken]
            proof = read(check(entry))
            reused = True
        else:
            parent = out / f'scene-{index:02d}'
            parent.mkdir(exist_ok=True)
            if not (parent / 'Aoede').exists():
                cadence.before_submission()
            proof = old.speech.synthesize(parent, spoken, 'Aoede', minimum_seconds=.2)
            entry = record(parent / 'Aoede/verified.json')
            reused = False
        wav_path = check(next(a for a in proof['files'] if a['path'].endswith('/voice.wav')))
        with wave.open(str(wav_path),'rb') as wav:
            if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()) != (24000,1,2):
                raise ValueError('Unexpected PCM format')
            frames = wav.getnframes()
            samples.append(wav.readframes(frames))
        proofs.append(entry)
        usage.append(proof['usage'])
        segments.append({'index':index,'text':item['narration'],'frames':frames,'duration_ms':round(frames/24)})
        print(json.dumps({'event':'scene_verified','episode':number,'scene':index,'reused':reused,'seconds':round(frames/24000,3)}),flush=True)
    allocate_scenes([s['duration_ms'] for s in segments], story['duration_seconds'] * 24)
    with wave.open(str(out / 'narration.wav'),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(b''.join(samples))
    save(out / 'timings.json', {'schema_version':1,'provider':'gemini','timing_source':'wav_frames','segments':segments})
    save(out / 'voice-source.json', {'provider':'gemini','model':old.speech.MODEL,'voice':'Aoede','inputs':narration_inputs(story),
         'timing_source':'wav_frames','generation_proofs':proofs,'usage':usage,'external_api_calls':plan['maximum_requests'],
         'artifacts':[dict(record(out/name),name=name) for name in ['narration.wav','timings.json']],
         'actual_billing_known':False,'final_human_listening':'pending'})
    load_supplied_narration(story,out / 'voice-source.json')
    save(HERE / f'{number:02d}/state.json', {'generation':out.relative_to(ROOT).as_posix(),'status':'speech_verified'})


FINAL_CAPTIONS = {
    5: [
        ['前の話を引き継ぐ', '相棒、dots。'],
        ['好みや決定事項を、', '会話をまたいで', 'ノートに残します。'],
        ['公式では、', 'ChatGPTのメモリと、', 'dot自身のノートを区別。'],
        ['必要に応じて、', '過去の会話も', '探して使います。'],
        ['全会話が、毎回', 'そのまま渡る', 'わけではありません。'],
        ['メモリをオフにしても、', 'dotの記録は', '残る場合があります。'],
        ['次の会話でも、', '仕事の続きへ。'],
    ],
    7: [
        ['毎朝の予定確認。', 'dotsとの会話で', '頼めます。'],
        ['「毎朝九時に、', '今日の予定を教えて」', 'と依頼。'],
        ['日本時間、期限、', '通知先まで具体的に。'],
        ['接続した予定表を対象に、', '保存した内容も', '確認してもらいます。'],
        ['確認は会話で', '「定期実行の一覧を\n見せて」。', '画面ならScheduledです。'],
        ['変更も解除も会話で。', '「朝八時に変えて」', '「この定期実行を\nやめて」。'],
        ['Scheduled画面から、', '無効化や削除も\nできます。'],
        ['作業の一時停止と、', '予約の解除は別です。'],
        ['変更や解除の後も、', '予約一覧を', '確認しましょう。', '次は、先回り調査。'],
    ],
}


def render(number, refined=False):
    story_path, story = build(number)
    state_path = HERE / f'{number:02d}/' / ('final-state.json' if refined else 'state.json')
    state = read(state_path) if state_path.exists() else {
        'generation': read(HERE / f'{number:02d}/state.json')['generation'], 'status':'speech_verified'}
    source = ROOT / state['generation'] / 'voice-source.json'
    # Keep the paid speech plan immutable; shortened visual labels get their own
    # revision and use exactly the same narration inputs and measured PCM.
    visual = copy.deepcopy(story)
    if number == 5:
        visual['scenes'][0]['items'][0]['detail'] = '好みと方針'
    if number == 7:
        visual['scenes'][-1]['items'][0]['label'] = '設定・変更'
        visual['scenes'][-1]['items'][1]['label'] = '確認・解除'
    if narration_inputs(visual) != narration_inputs(story):
        raise ValueError('Visual fitting must not change frozen speech')
    if refined:
        for item, parts in zip(visual['scenes'], FINAL_CAPTIONS[number], strict=True):
            item['captions'] = parts
    visual_path = HERE / f'{number:02d}/' / ('visual-v03' if refined else 'visual-v02') / 'creator-story.json'
    visual_path.parent.mkdir(exist_ok=True)
    if visual_path.exists() and read(visual_path) != visual:
        raise ValueError('Visual revision changed')
    if not visual_path.exists():
        save(visual_path, validate_story(visual))
    if 'output' in state and not state.get('visual_revision'):
        prior = ROOT / state['output']
        if (prior / 'render.json').exists() or (prior / 'timeline.mp4').exists():
            raise ValueError('Previous render requires explicit preservation before another revision')
        save(HERE / f'{number:02d}/visual-v02/failed-preparation-v01.json', state)
        state.pop('output')
    if 'output' not in state:
        out = prepare(visual_path,narration_source=source)
        state.update(output=out.relative_to(ROOT).as_posix(),status='prepared',visual_revision=record(visual_path))
        save(state_path,state)
    out = ROOT / state['output']
    if not (out / 'render.json').exists():
        run('node', ROOT / 'studio/creator-render.mjs',out)
    if not (out / 'verification.json').exists():
        finish(out)
    check(read(out / 'verification.json')['delivery'])
    state['status'] = 'rendered_awaiting_visual_review'
    save(state_path,state)
    print(json.dumps({'event':'rendered','episode':number,'output':state['output']}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','generate','render','final-render'])
    parser.add_argument('--episode',choices=['5','7','all'],default='all')
    args = parser.parse_args()
    numbers = [5,7] if args.episode == 'all' else [int(args.episode)]
    try:
        if args.command == 'generate':
            for number in numbers:
                build(number)
            with old.generation_lock():
                cadence = old.SubmissionCadence()
                for number in numbers:
                    generate(number,cadence)
        else:
            for number in numbers:
                build(number) if args.command == 'build' else render(number, refined=args.command=='final-render')
    except Exception as error:
        print(json.dumps({'status':'error','type':type(error).__name__,
              'message':str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Stopped; inspect saved state without retrying submitted requests.'}),flush=True)
        raise SystemExit(1)
