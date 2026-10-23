"""Assemble only verified renders into a versioned review collection."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import read,record,check
OUT=ROOT/'outputs/productions/SERIES_20261023_editorial_revision'
OUT.mkdir(parents=True,exist_ok=True)
descriptions={
1:'Claude Docsで、資料を踏まえた下書きから、人の編集とClaudeへの相談へ。同じ文書を仕上げる使い方を紹介します。\n実演は架空店舗の初回文書とコメント修正。複数資料の参照と直接編集は公式機能の説明です。記事案はレビュー中で、公開URLとプロフィールの導線は公開前に設定します。\n出典：https://support.claude.com/en/articles/16923645-get-started-with-claude-docs\n確認日：2026-10-23',
8:'dotsの「先回り提案」。読める権限のあるメールや予定などを仕事の文脈と結びつけ、次にすることを提案します。毎回、個別に調査を頼む必要がない点に注目しました。\n会議が前倒しになった例は架空です。接続するだけで任意のイベント監視が予約されるという説明ではありません。\n出典：https://learn.chatgpt.com/docs/dots/tasks-and-memory\n出典：https://learn.chatgpt.com/docs/dots/controls\n確認日：2026-10-23',
9:'dotsから承認を求められたら、宛先と内容を見て、実行するか、修正するか、中止するかを判断しましょう。メール送信前の確認をルールで指定する例を紹介します。\n事前の許可や設定、自動レビューにより確認なしで進む場合もあり、すべての操作で毎回確認される保証ではありません。画面の選択肢は判断の例です。\n出典：https://learn.chatgpt.com/docs/dots/controls\n確認日：2026-10-23',
7:'dotsとの会話で「毎朝9時に予定を教えて」と定期実行を依頼する例。時刻と時間帯、期限、通知先を具体的にし、保存結果を確認します。\n会話で一覧、変更、解除を依頼でき、Scheduled画面から確認、無効化、削除もできます。Pauseによる現在の作業停止と予約解除は別です。第8回予告を「先回り提案」に統一しました。\n出典：https://learn.chatgpt.com/docs/dots/tasks-and-memory\n出典：https://learn.chatgpt.com/docs/dots/controls\n確認日：2026-10-23',
}
entries=[]; headings=[]
for n in [1,8,9,7]:
    state=read(HERE/f'{n:02d}'/('final-state.json' if n==1 else 'state.json'))
    source=ROOT/state['output']
    verification=read(source/'verification.json')
    video=check(verification['delivery'])
    story=read(source/'story.json')
    folder=OUT/('claude-docs-v02' if n==1 else f'dots-{n:02d}-v02')
    folder.mkdir(exist_ok=True)
    for name in ['shorts-creator.mp4','captions.srt','cover.png','verification.json']:
        dest=folder/name
        if dest.exists() and dest.read_bytes()!=(source/name).read_bytes():raise ValueError('Preserve existing review package')
        if not dest.exists():shutil.copy2(source/name,dest)
    for name,text in [('youtube-title.txt',story['title']),('youtube-description.txt',descriptions[n]),('narration.txt','\n\n'.join(s['narration'] for s in story['scenes']))]:
        (folder/name).write_text(text+'\n',encoding='utf-8')
    entries.append({'episode':n,'title':story['title'],'video':record(folder/'shorts-creator.mp4'),
        'source_render':source.relative_to(ROOT).as_posix(),'verification':record(folder/'verification.json'),
        'duration_seconds':story['duration_seconds'],'voice':'Gemini Aoede','human_listening':'pending','user_approved':False})
    headings.append(story['title']+'\n\n'+descriptions[n])
(OUT/'YouTube見出しと説明欄_v02.txt').write_text('\n\n--------------------\n\n'.join(headings)+'\n',encoding='utf-8')
(OUT/'delivery.json').write_text(json.dumps({'revision':'v02','entries':entries,'mobile_playback':'pending','publication':'not_performed'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'packaged':len(entries),'directory':str(OUT)}))
