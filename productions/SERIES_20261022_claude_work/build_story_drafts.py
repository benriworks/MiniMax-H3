"""Build review-only Claude story drafts from recorded evidence, with no API calls.

The source proposal is immutable. Missing screenshots or MiniMax video remain
explicit readiness blockers; this command does not make production stories,
speech, renders or a publication package.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import check, load_capture, units, validate_business_scene, validate_capture, validate_story

EVIDENCE = ROOT / 'outputs/evidence/claude-work-20261022'
OFFICIAL = {1: 'docs-create', 2: 'artifacts-slides', 3: 'design-refine', 4: 'artifacts-selection', 5: 'docs-export'}
# Entries are actual captured IDs, never hypothetical file names. None means
# the shot is not available in the current reviewed evidence manifest.
DEMOS = {
    1: ['01-input-numbers-native', '01-budget-first-history-native', '01-revision-budget-heading-native-v2', '01-budget-revised-history-native'],
    2: ['02-request-five-native', '02-slides-five-thumbnails', '02-slides-after-date-native', '02-slides-after-details-native'],
    3: ['03-design-request-native-excerpt-v3', '03-design-first-price-hours-native', '03-design-revision-larger-native-v2', '03-design-after-price-hours-native'],
    4: ['04-purpose-first-history-native', '04-request-short-native-v2', '04-purpose-after-history-native', '04-price-after-history-native'],
    5: ['05-ppt-export-before-native', '05-ppt-price-export-native', '05-word-budget-native', '05-word-date-native-v3'],
}
LABELS = {1: 'Docs / 企画書', 2: 'Slides / 会議資料', 3: 'Design / 告知', 4: 'Docs / 部分修正', 5: '書き出し / 最終確認'}
TITLES = {
    1: '【Claude】メモから企画書へ！Docsで下書きと修正を試す',
    2: '【Claude】同じ企画を5枚に！Slidesで会議資料を作る',
    3: '【Claude】告知デザインを見やすく！文字と余白を整える',
    4: '【Claude】この一文だけ直したい！選んだ場所から修正する',
    5: '【Claude】作った資料を持ち出す！Word・PowerPointに書き出す',
}
# Each tuple is headline + successive caption phrases. Joining the phrases
# exactly yields narration; newlines only indicate intentional display wraps.
COPY = {
  1: [
    ('メモはある。\n企画書がまだ。', ['企画担当の栞さん。', '今日は、メモを\n企画書にします。']),
    ('会話から、\nDocsへ。', ['クロードのドックスは、', '会話から\n文書を作れます。']),
    ('価格や予算も\n先に伝える', ['価格や予算など、', '元のメモの条件を\n伝えます。']),
    ('まずは\n初回の予算欄', ['初回の出力を見て、', '予算欄を\n確認します。']),
    ('見出しと金額を\n見つけやすく', ['予算の見出しを具体的に。', '金額も太字にするよう\n頼みます。']),
    ('修正後も\n元の数字と照合', ['修正後も、', '予算の数字を\n元のメモと照合します。']),
    ('下書きを任せて、\n中身は確かめる', ['下書きを任せて、\n中身は確かめる。', '次はスライドです。']),
  ],
  2: [
    ('企画書を、\n会議で伝える。', ['栞さんの次の仕事は、', '企画を短く伝える\n資料づくり。']),
    ('Slidesで\nプレゼン資料へ', ['公式のスライド機能では、', '会話の内容から\n資料を作れます。']),
    ('枚数と流れを\n先に伝える', ['五枚にして、', '目的、内容、日程などの\n流れを指定します。']),
    ('まずは\n5枚あるか確認', ['五枚できました。', 'まず枚数を確かめます。']),
    ('日付を\nもう少し見やすく', ['今回は日付を、', 'もう少し見やすく\n整えるよう頼みます。']),
    ('時間と告知方法も\n元の企画と照合', ['提供時間と告知方法も、', '元の企画と照合します。']),
    ('伝える資料へ。\n次は告知デザイン', ['栞さんは、\n伝わるかを確かめます。', '次は告知デザインです。']),
  ],
  3: [
    ('同じ企画を、\n店内の告知へ。', ['栞さん、今度は店内の\n告知を見やすくしたい。']),
    ('Designは\n会話とキャンバス', ['クロードのデザインは、', '会話しながら\n見た目を整える機能。']),
    ('用途・内容・\n色を伝える', ['使う場所と載せる内容、', '色の希望を伝えます。']),
    ('最初の案を\n読み手目線で', ['最初の案は、', '価格と時間がひと目で\n分かるか確認。']),
    ('価格と時間を\nもう一段大きく', ['価格と提供時間を、', 'もう一段大きくするよう\n頼みます。']),
    ('修正の前後を\n同じ大きさで比べる', ['修正の前後を\n同じ大きさで見比べて、', '数字も照合。']),
    ('一度で決めず、\n見て直す。', ['一度で決めず、見て直す。', '次は文書の部分修正です。']),
  ],
  4: [
    ('ここだけ、\n分かりやすくしたい。', ['栞さんが気になったのは、', '企画書のこの一文。']),
    ('選んだ部分に\n修正を頼む', ['公式には、選んだ文章に', '編集を頼む方法が\nあります。']),
    ('まず、\n修正前の一文', ['まず、修正前の文を\n確認します。']),
    ('短く、\n分かりやすく', ['店内スタッフ向けに、', '短く分かりやすくと\n伝えます。']),
    ('短くなっても\n意図を確かめる', ['短くなりましたが、', '目標の意味合いも変化。', '意図に合うか確認。']),
    ('ほかの部分も\n一度確認', ['価格など、', 'ほかの部分にも\n目を通します。']),
    ('仕上げは、\n自分で確かめる。', ['仕上げは、\n自分で確かめる。', '次はファイルへの\n書き出しです。']),
  ],
  5: [
    ('渡す前に、\nファイルでも確認。', ['栞さん、資料を渡す前に、', 'ファイルでも確認します。']),
    ('文書はWord、\nスライドはPPTXへ', ['公式の書き出しは、', '文書ならワード、', 'スライドなら\nパワーポイント。']),
    ('形式を選んで\n書き出す', ['今回は、', 'パワーポイントの形式を\n選びます。']),
    ('保存したPPTXで\n価格を確かめる', ['保存したファイルを開き、', '価格の数字を確認。']),
    ('Wordで\n予算を確認', ['ワードで開いて、', '予算の数字と\n文字を確認。']),
    ('日付と書体も\n一度確認', ['日付も照合。', '書体が変わる\n場合もあるので、', '見た目も確かめます。']),
    ('作る・直す・\n確かめる。', ['作る、直す、確かめる。', 'クロードと進める\n資料づくりでした。']),
  ],
}
SUMMARIES = {
    1: '架空のメモからDocsで企画書を作り、予算欄の見出しと金額の書式を整える過程を紹介します。',
    2: '同じ架空の企画をSlidesで5枚の会議資料にします。初回一覧では枚数を確認し、修正後の日付・提供時間・告知方法を元の条件と照合する流れを紹介します。',
    3: '架空の店内告知をDesignで作り、文字や余白を確認しながら直す流れを紹介します。',
    4: '文書の一文を選び、店内スタッフ向けに短くするよう頼みます。実際には「来店するきっかけを作る」から「来店を増やす」へ変わり、目標の意味合いも強まりました。修正後は意図に合うか、変更外の数値と合わせて確認します。',
    5: 'DocsやSlidesをWord・PowerPoint形式に書き出し、保存した実ファイルで文字や数値を確認します。今回はPowerPointのbasic fontsを選択し、明示フォントがNoto Sans JPからArialへ置き換わる案内を確認しました。アプリで開いた見た目も確認が必要です。',
}
CHANGE_NOTES = {
    1: '中央4実演枠を依頼の価格/予算→初回予算欄→修正依頼→修正後予算欄へ絞った。目的・日程など画面にない項目の確認を完了と断定しない。',
    2: '初回5枚は読みやすいとの親の実画面レビューを反映し「詰め込みすぎ」を削除。実際の初回JPEG一覧は5枚の枚数確認に限定し、細かな本文の可読性の根拠にしない。native PNGで修正後の日付拡大と時間・告知方法を示す。低解像度の修正前と同倍率比較したとは表現しない。',
    3: '実際のDesign初回と修正後を55%表示でnative PNG撮影。同じ570px横幅から価格・時間の拡大を比較する。修正依頼の実文字「もう一段大きく」を引用する。日付の折り返し解消と入力外の一文の削除は実施されたが、現動画の前後比較は価格と時間に絞る。',
    4: '実際の操作は選択後の@Claude依頼。修正前→依頼→修正後→変更外価格を順に示し、意図が保持されたと断定しない。',
    5: '実PPTX保存・PowerPoint保護ビューの3枚目650円を採用。Wordは予算の書式修正後に保存したDOCXの3万円と日付で、部分修正後の最終Docsだとは主張しない。PPTXは日程修正後の版。XML/CRCと実アプリ外観は別証拠として保存。basic fontsの書体変化を本文・説明欄で補足する。',
}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}

def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')

def stage_capture(identifier, group, production_id):
    original = EVIDENCE / group / f'{identifier}.json'
    if not original.is_file():
        return None
    proof = read(original)
    if proof.get('review_status') != 'capture_review_passed':
        return None
    source = check(proof['artifact'])
    check(proof['context'])
    destination = ROOT / 'outputs/productions' / production_id / 'captures'
    destination.mkdir(parents=True, exist_ok=True)
    image_path, proof_path = destination / source.name, destination / original.name
    if image_path.exists():
        if image_path.read_bytes() != source.read_bytes():
            raise ValueError('Existing staged image differs: ' + identifier)
    else:
        shutil.copyfile(source, image_path)
    proof['artifact'] = record(image_path)
    if proof_path.exists():
        previous = read(proof_path)
        if previous != proof:
            # Parent review metadata can advance without changing the image;
            # never overwrite an already-staged proof during review work.
            proof_path = destination / f'{identifier}-{record(original)["sha256"][:12].lower()}.json'
    if not proof_path.exists():
        save_new(proof_path, proof)
    capture = {'path': image_path.relative_to(ROOT).as_posix(),
               'proof': proof_path.relative_to(ROOT).as_posix(),
               'origin': proof['origin'], 'title': proof['title']}
    if proof['origin'] == 'official':
        capture['source_url'] = proof['source_url']
    else:
        capture.update(product=proof['product'], phase=proof['phase'])
    validate_capture(capture, 'business')
    load_capture(capture)
    return capture

def media_from_proof(path):
    if not path:
        return None
    proof_path = (ROOT / path).resolve(strict=True)
    if not proof_path.is_relative_to(ROOT):
        raise ValueError('Video proof must remain in the workspace')
    proof = read(proof_path)
    video = check(proof['artifact'])
    if (proof.get('provider') != 'minimax' or proof.get('review_status') != 'visual_review_passed'
            or proof.get('execution', {}).get('success') is not True
            or check(proof['source_presenter']) != ROOT / 'outputs/characters/business-guides-20261022/claude-shiori.png'
            or record(check(proof['source_keyframe']))['sha256'] != record(ROOT / 'outputs/characters/business-guides-20261022/claude-shiori-office-keyframe.png')['sha256']):
        raise ValueError('Expected the reviewed new Claude MiniMax video')
    return {'path': video.relative_to(ROOT).as_posix(), 'proof': proof_path.relative_to(ROOT).as_posix()}

def build_episode(episode, draft, directory, media):
    number, production_id = episode['episode'], episode['id']
    scenes, readiness = [], []
    ids = DEMOS[number][:]
    for index, (headline, captions) in enumerate(COPY[number]):
        narration = ''.join(captions).replace('\n', '')
        scene = {'kind': 'editorial' if index in (0, 6) else 'source', 'visual_style': 'business',
                 'headline': headline, 'eyebrow': f'CLAUDE {number:02d} / ' + LABELS[number].split(' / ')[0],
                 'narration': narration, 'captions': captions,
                 'source_ids': episode['scenes'][index]['source_ids']}
        item = {'scene': index + 1, 'original_scene_id': episode['scenes'][index]['id']}
        if index in (0, 6):
            scene.update(editorial_layout='hook' if index == 0 else 'closing',
                         body='企画担当の栞さん' if index == 0 else '作って、見て、直す',
                         action='架空の業務例' if index == 0 else '内容は自分で確認')
            if media:
                scene.update(media=media, mediaStart=0)
                item.update(status='asset_reviewed_root_story_review_pending', asset=media)
            else:
                item.update(status='pending_character_video', required='新しいClaude栞のMiniMax動画と検証proof')
        else:
            identifier = OFFICIAL[number] if index == 1 else ids[index - 2]
            capture = stage_capture(identifier, 'official' if index == 1 else 'demonstration', production_id) if identifier else None
            if capture:
                scene['capture'] = capture
                item.update(status='capture_reviewed_root_story_review_pending', capture_id=identifier, capture=capture)
                proof = read(ROOT / capture['proof'])
                count_only_jpeg = number == 2 and identifier == '02-slides-five-thumbnails'
                item['capture_quality'] = ('genuine_initial_jpeg_count_only_scene_review_pending' if count_only_jpeg
                                           else 'native_recapture_required' if proof.get('raw_capture_format') == 'JPEG'
                                           else 'native_png_ready_for_scene_review' if capture['origin'] == 'demonstration'
                                           else 'official_crop_reviewed')
                if count_only_jpeg:
                    item['permitted_claim'] = 'Five visible initial slide thumbnails only; not small text or detailed layout quality.'
            else:
                item.update(status='pending_capture', requested_capture_id=identifier,
                            required=episode['scenes'][index]['capture_required'])
        validate_business_scene(scene, index, 7)
        if any(len(part.split('\n')) > 2 or any(units(line) > 12 for line in part.split('\n')) for part in captions):
            raise ValueError(f'Caption does not fit: {number}/{index + 1}')
        if not 1 <= len(narration) <= 80:
            raise ValueError('Narration length is invalid')
        scenes.append(scene)
        readiness.append(item)
    story = {'schema_version': 1, 'id': production_id, 'title': TITLES[number],
             'voice': 'Aoede', 'rate': 1, 'duration_seconds': 30, 'music_preset': 'bright_groove_v1',
             'pronunciations': [{'source': a, 'target': b} for a, b in [('Claude', 'クロード'), ('Docs', 'ドックス'),
                               ('Slides', 'スライド'), ('Design', 'デザイン'), ('栞', 'しおり')]],
             'scenes': scenes, 'draft_status': 'root_review_required_do_not_generate'}
    complete_captures = all('capture' in s for s in scenes[1:6])
    if complete_captures:
        validate_story(story)
    sources = [s for s in draft['sources'] if s['id'] in set(sum((s['source_ids'] for s in episode['scenes']), []))]
    # Always retain the official source for the actual second scene.
    official_url = scenes[1]['capture']['source_url']
    sources = list({s['url']: s for s in sources + [s for s in draft['sources'] if s['url'] == official_url]}.values())
    caveat = '登場人物の佐伯栞、店舗「灯台珈琲」、企画・資料は説明用の架空設定です。'
    description = (SUMMARIES[number] + '\n\n' + caveat + '\n'
                   'Anthropicの公式・公認動画ではありません。公式資料の引用と、こちらで記録した実演を区別しています。\n'
                   '画面・機能の確認日：2026年10月22日。プランや設定、更新によって表示・利用条件が変わる場合があります。\n\n'
                   '出典\n' + '\n'.join(s['title'] + '\n' + s['url'] for s in sources) + '\n\n#Claude #仕事効率化 #Shorts\n')
    source_text = '# 出典と実演範囲\n\n確認日：2026-10-22。\n\n' + '\n'.join(f'- [{s["title"]}]({s["url"]})' for s in sources)
    source_text += ('\n\n' + caveat + '\n\n公式・公認動画ではありません。公式引用には出典を、実演には「こちらの実演・Claude」を表示します。\n\n'
                    '## 下書き時点の確認範囲\n\n' + CHANGE_NOTES[number] + '\n\n'
                    'この下書きは公開用の完成報告ではありません。未取得の画面、生成待ちの人物動画、最終動画の可読性・音声・尺の確認はreadiness.jsonを参照してください。\n'
                    '初回と修正後の比較は実際の画像を使用し、画像の文章を書き換えて再現しません。原本の私的画面は配布対象外です。\n')
    review = {'schema_version': 1, 'episode': number, 'status': 'root_review_required',
              'text_layout_validation': 'passed', 'common_story_validation': 'passed' if complete_captures else 'not_run_missing_capture',
              'narration_characters': sum(len(s['narration']) for s in scenes),
              'source_proposal': record(HERE / 'scripts-draft.json'),
              'change_note': CHANGE_NOTES[number], 'scenes': readiness,
              'paid_requests_submitted': 0, 'production_story_written': False, 'actual_30_seconds_verified': False,
              'ready_for_tts': False, 'remaining': ['親による実素材・文意レビュー', '人物MiniMax動画の確認' if not media else '最終構成の確認',
                                                   '不足する実演画面の撮影' if not complete_captures else '動画内の文字・前後比較の可読性確認',
                                                   'ナレーション確定後の音声生成と実尺測定']}
    review['native_recapture_required_scenes'] = [r['scene'] for r in readiness if r.get('capture_quality') == 'native_recapture_required']
    out = directory / f'{number:02d}'
    save_new(out / 'creator-story.draft.json', story)
    save_new(out / 'readiness.json', review)
    save_new(out / 'youtube-title.txt', TITLES[number] + '\n')
    save_new(out / 'youtube-description.txt', description)
    save_new(out / 'SOURCES_JA.md', source_text)
    save_new(out / 'narration-draft.txt', '\n'.join(f'{i + 1:02d} {s["narration"]}' for i, s in enumerate(scenes)) + '\n')
    return {'episode': number, 'story': record(out / 'creator-story.draft.json'), 'readiness': record(out / 'readiness.json'),
            'missing_capture_scenes': [r['scene'] for r in readiness if r['status'] == 'pending_capture'],
            'missing_character_scenes': [r['scene'] for r in readiness if r['status'] == 'pending_character_video']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', default='all', help='all or comma-separated 1-5')
    parser.add_argument('--media-proof', help='Workspace-relative proof of the reviewed new Claude MiniMax video')
    args = parser.parse_args()
    selected = set(range(1, 6)) if args.episodes == 'all' else {int(n) for n in args.episodes.split(',')}
    if not selected or not selected <= set(range(1, 6)):
        parser.error('Select episodes 1-5')
    original = record(HERE / 'scripts-draft.json')
    draft = read(HERE / 'scripts-draft.json')
    media = media_from_proof(args.media_proof)
    directory = HERE / 'drafts' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    outputs = [build_episode(e, draft, directory, media) for e in draft['episodes'] if e['episode'] in selected]
    if record(HERE / 'scripts-draft.json') != original:
        raise ValueError('Source proposal changed during the draft build')
    manifest = {'schema_version': 1, 'status': 'review_only_no_generation', 'source_proposal': original,
                'builder': record(Path(__file__)), 'paid_requests_submitted': 0, 'episodes': outputs}
    save_new(directory / 'manifest.json', manifest)
    print(json.dumps({'draft_directory': directory.relative_to(ROOT).as_posix(), 'episodes': outputs}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
