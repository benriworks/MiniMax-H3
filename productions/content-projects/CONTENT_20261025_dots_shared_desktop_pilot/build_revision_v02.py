"""Editorial revision requested after the first three pilot videos."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import read, record, validate_story
from produce import save


def update(scene, narration, captions, headline, eyebrow):
    scene.update(narration=narration, captions=captions, headline=headline, eyebrow=eyebrow)


def build():
    cap = ROOT / 'outputs/productions/SHORT_20261025_dots_desktop_01/captures'
    story = read(HERE / '01/creator-story-v01.json')
    story['pronunciations'] = [dict(source='dots', target='ドッツ')]
    story['scenes'][0].update(headline='dotsとあなたの\n共有デスクトップ', capture=dict(
        origin='demonstration', product='ChatGPT', phase='after', title='dotsのクラウドPC',
        path=record(cap / 'desktop-v02.png')['path'], proof=record(cap / 'desktop-v02-proof.json')['path']))
    story['scenes'][1].update(narration='dotsが用意した下書きを、同じ作業画面で確認。',
        captions=['dotsが用意した\n下書きを、', '同じ作業画面で確認。'])
    story['scenes'][3]['capture'].update(title='操作をdotsへ戻す', path=record(cap / 'return-v02.png')['path'],
        proof=record(cap / 'return-v02-proof.json')['path'])
    for scene in story['scenes']:
        if scene.get('eyebrow'):
            scene['eyebrow'] = scene['eyebrow'].replace('DOTS', 'dots')
    save(HERE / '01/creator-story-v02.json', validate_story(story))
    story = read(HERE / '02/creator-story-v01.json')
    update(story['scenes'][1], 'この共同作業領域には、Blenderが入っています。',
        ['この共同作業領域には、', 'Blenderが入っています。'], '共同作業領域に\nBlenderを用意', 'クラウドにインストール')
    update(story['scenes'][2], 'dotsに頼めば、ここでモデリングしてくれます。',
        ['dotsに頼めば、', 'ここでモデリング\nしてくれます。'], '依頼すれば\nモデリング', 'dotsがアプリを操作')
    save(HERE / '02/creator-story-v02.json', validate_story(story))
    story = read(HERE / '03/creator-story-v01.json')
    story['title'] = '【ChatGPT】表計算からシステムへ自動転記！dotsのクラウドPC'
    story['pronunciations'] += [dict(source='表計算', target='ひょうけいさん'),
        dict(source='表を', target='ひょうを'), dict(source='表と', target='ひょうと')]
    edits = [
        ('Webブラウザーと表計算が使えるので、自動転記できます。', ['Webブラウザーと', '表計算が使えるので、', '自動転記できます。'], 'システムへ\n自動転記', 'ブラウザーと表計算'),
        ('Excelの表を、クラウドで開きます。', ['Excelの表を、', 'クラウドで開きます。'], 'Excelの表を\nクラウドで開く', '転記するデータを用意'),
        ('dotsが入力欄に合わせて、データを転記。', ['dotsが入力欄に\n合わせて、', 'データを転記。'], '入力欄に合わせ\n自動で転記', '案件・納期・金額'),
        ('登録前に内容を確認。結果も一覧で確かめます。', ['登録前に内容を確認。', '結果も一覧で\n確かめます。'], '登録前も\n入力後も確認', '入力して終わりにしない'),
        ('元の表と照合。3件、25万円が一致。', ['元の表と照合。', '3件、25万円が一致。'], '元の表と照合\n3件が一致', '件数と金額を確認'),
        ('画面は模擬システム。実運用には、権限が必要です。', ['画面は模擬システム。', '実運用には、\n権限が必要です。'], '実システムの\n利用権限が必要', '今回の画面は模擬環境'),
        ('データ入力を任せて、人は内容の確認へ。', ['データ入力を任せて、', '人は内容の確認へ。'], '転記を任せて\n人は確認へ', 'dots / 自動転記'),
    ]
    for scene, edit in zip(story['scenes'], edits, strict=True):
        update(scene, *edit)
    story['scenes'][-1].update(body='入力後まで確認', action='内容を確かめる')
    save(HERE / '03/creator-story-v02.json', validate_story(story))
    print('Three v02 stories validated; previous stories preserved')


if __name__ == '__main__':
    build()
