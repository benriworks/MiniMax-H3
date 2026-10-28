"""Author the five remaining editorial episodes, without external API calls."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import validate_story

def scene(layout,headline,narration,captions,**fields):
    return dict(kind='editorial',editorial_layout=layout,headline=headline,narration=narration,captions=captions,**fields)

def source(slug,page,title,headline,narration,captions):
    return dict(kind='source',headline=headline,narration=narration,captions=captions,
                capture=dict(slug=slug,page=page,title=title))

def items(*pairs):
    return [dict(label=a,detail=b) for a,b in pairs]

EPISODES=[
dict(number=5,topic='記憶と好み',slug='memory',title='【ChatGPT】毎回の説明を減らす！dotsの「記憶」はどこまで？',
sources=['tasks-and-memory'],notes='ChatGPTのメモリとdot自身のノートは別。全会話の完全な記録ではありません。設定の変更がdotの既存ノートにも必ず反映されるとは説明していません。好みの例は架空の依頼例です。',scenes=[
scene('contrast','その好み、\nまた説明してる？','毎回、好みを説明し直していませんか？',['毎回、好みを','説明し直して','いませんか？'],body='仕事の始め方',items=items(('毎回説明','結論からお願い'),('次の仕事へ','好みを生かす'))),
scene('memory','会話とメモを、\n次の仕事へ。','dotsは会話やメモを、次の仕事にも生かします。',['dotsは会話やメモを、','次の仕事にも','生かします。'],body='引き継ぐ手がかり',items=items(('好み','文章の調子'),('決めたこと','方針と優先順位'),('進めている仕事','次にやること'))),
source('official-memory','tasks-and-memory','Tasks and memory','メモリとノートは、\n別のしくみ。','公式では、ChatGPTのメモリと、dot自身のノートを区別。',['公式では、','ChatGPTのメモリと、','dot自身のノートを区別。']),
scene('statement','好みは、\n具体的に伝える。','たとえば、要点は三つ、結論から。',['たとえば、','要点は三つ、','結論から。'],body='要点は3つ。\n結論から。',action='依頼の例'),
scene('contrast','何もかも、\n覚えるわけではない。','ただし、全会話を丸ごと覚えるわけではありません。',['ただし、全会話を','丸ごと覚える','わけではありません。'],body='記憶の範囲',items=items(('使う情報','好み・決定・作業'),('保証されない','全会話の完全保存'))),
scene('memory','好みが変わったら、\nその場で伝える。','変えたい好みは、その都度伝えましょう。',['変えたい好みは、','その都度','伝えましょう。'],body='方針を更新',items=items(('これまで','詳しく説明'),('これから','短く要点だけ')),action='変更を言葉にする'),
scene('recap','伝えるほど、\n任せやすく。','好みを伝えて、仕事をスムーズに。次は通話。',['好みを伝えて、','仕事をスムーズに。','次は通話。'],body='好み・方針・進行中',items=items(('好み','具体的に伝える'),('変更','その都度伝える')),action='次回：会話と通話')]),
dict(number=6,topic='会話と通話',slug='channels',title='【ChatGPT】声でも頼める！dotsは通話を切った後も仕事が続く',
sources=['channels','tasks-and-memory'],notes='ChatGPTアプリとデスクトップブラウザーから通話。モバイルWebは非対応。Slack/Teamsは利用可能な連絡方法を接続して使います。通話は選択された文脈を使用し、すべての作業文脈が必ず共有されるわけではありません。dot側からの発信やSMSは現在利用可能とは説明していません。',scenes=[
scene('channels','声で相談。\nそのまま仕事へ。','声で相談して、そのまま仕事を任せたい。',['声で相談して、','そのまま仕事を','任せたい。'],stat='dot',body='話す → 頼む',items=items(('相談','声で伝える'),('依頼','進める作業'))),
scene('statement','文字だけでなく、\n通話でも。','dotsとは、ChatGPTから通話もできます。',['dotsとは、','ChatGPTから','通話もできます。'],body='相談を、\n声で。',action='アプリから通話'),
source('official-call','channels','Message your dot','通話しながら、\n文字も送れる。','公式の画面例では、通話しながら文字も送れます。',['公式の画面例では、','通話しながら','文字も送れます。']),
scene('channels','連絡する場所を、\n選べる。','SlackやTeamsでも、同じ相棒に連絡できます。',['SlackやTeamsでも、','同じ相棒に','連絡できます。'],stat='dot',body='使う連絡方法を接続',items=items(('ChatGPT','相談と更新'),('Slack','メッセージ'),('Teams','メッセージ'))),
scene('contrast','同じ相棒。\n履歴は別々。','ただし、会話の履歴が全部コピーされるわけではありません。',['ただし、会話の履歴が','全部コピーされる','わけではありません。'],body='引き継ぎと表示の違い',items=items(('引き継ぐ','関連する文脈'),('表示される履歴','それぞれの会話'))),
scene('permissions','通話終了と、\n作業停止は別。','通話を終えても、依頼した仕事は続けられます。',['通話を終えても、','依頼した仕事は','続けられます。'],body='依頼済みの仕事',items=[dict(label='音声の会話',detail='終了',done=False),dict(label='依頼した作業',detail='継続できる',done=True)]),
scene('recap','スマホなら、\nアプリから。','スマホはアプリで。次は、定期実行。',['スマホはアプリで。','次は、定期実行。'],body='話す場所を選ぼう',items=items(('声で相談','ChatGPT'),('文字で連絡','接続した連絡先')),action='次回：定期実行')]),
dict(number=7,topic='定期実行',slug='schedule',title='【ChatGPT】毎朝の確認を任せる！dotsの定期実行は「保存」が大事',
sources=['tasks-and-memory','controls'],notes='固定時刻の繰り返しには保存したスケジュールが必要。何を・いつ・どの変化を通知・どこへ届けるかを明示し、保存内容を確認します。日付や時刻は架空の依頼例で、この動画によって実際のスケジュールは登録されていません。イベント監視は対応サービスのみで、接続だけでは設定されません。',scenes=[
scene('calendar','毎朝の確認、\nまた頼んでる？','毎朝の確認、また同じことを頼んでいませんか？',['毎朝の確認、','また同じことを','頼んでいませんか？'],stat='9:00',body='繰り返す仕事',items=items(('朝の確認','今日の変更点'))),
source('official-recurring','tasks-and-memory','Tasks and memory','繰り返す仕事は、\n保存して動かす。','繰り返す仕事は、スケジュールとして保存します。',['繰り返す仕事は、','スケジュールとして','保存します。']),
scene('calendar','平日の朝9時に、\n予定の変更を確認。','たとえば、平日の朝九時に、予定の変更を確認。',['たとえば、','平日の朝九時に、','予定の変更を確認。'],stat='9:00',body='依頼の例',items=items(('対象','接続した予定表'),('条件','変更時だけ'))),
scene('recap','いつ・どこへ、\nを具体的に。','日本時間、期限、通知先まで具体的に。',['日本時間、期限、','通知先まで具体的に。'],body='依頼に加える条件',items=items(('時間帯','日本時間'),('終了日','今月末まで'),('通知先','ChatGPTへ'))),
scene('statement','保存した内容を、\n確認しよう。','保存した内容は、確認してもらいましょう。',['保存した内容は、','確認して','もらいましょう。'],body='何を・いつ\nどこへ届ける？',action='保存内容を確認'),
scene('contrast','止めるときも、\n予約を確認。','作業の一時停止と、予約の解除は別です。',['作業の一時停止と、','予約の解除は別です。'],body='停止の違い',items=items(('現在の作業','一時停止'),('今後の定期実行','無効化・削除'))),
scene('recap','毎日のひと手間を、\n任せるしくみに。','何を、いつ、どこへ。次は、先回り調査。',['何を、いつ、どこへ。','次は、先回り調査。'],body='任せ方を具体的に',items=items(('内容と時刻','はっきり伝える'),('保存結果','必ず確認')),action='次回：先回り調査')]),
dict(number=8,topic='先回り調査',slug='research',title='【ChatGPT】頼む前に気づく？dotsの「先回り調査」でできること',
sources=['tasks-and-memory','controls'],notes='先回り調査は読める権限のある接続情報を調べ、非公開ノートを使って提案につなげるしくみです。この調査自体はメッセージ送信、アプリの変更、ブラウザー/PC操作をしません。別途依頼した定期実行とは権限とスケジュールが別。動画の会議・締切・確認依頼は架空例で実行を実証した録画ではありません。',scenes=[
scene('research','頼む前に、\n気づいてくれる？','その変更、気づくのが遅れそう。そんなとき。',['その変更、','気づくのが遅れそう。','そんなとき。'],body='見落としやすい変化',items=items(('新しい予定','時間が変更'),('以前のメモ','締切は同じ'))),
source('official-research','tasks-and-memory','Tasks and memory','公式の機能、\n先回り調査。','dotsには、先回りで情報を調べるしくみがあります。',['dotsには、','先回りで情報を調べる','しくみがあります。']),
scene('research','読める情報を、\nつなげて考える。','読める権限のある情報を調べ、前の話とつなげます。',['読める権限のある','情報を調べ、','前の話とつなげます。'],body='許可された情報から',items=items(('接続した情報','新しい変更'),('以前の話','決めていた方針')),action='関連する気づきへ'),
scene('contrast','予定の変更と、\n締切のずれに注目。','たとえば、会議の変更と締切のずれに気づく。',['たとえば、','会議の変更と','締切のずれに気づく。'],body='架空の例',items=items(('新しい会議','金曜日に変更'),('締切のメモ','木曜日のまま'))),
scene('permissions','調べることと、\n実行することは別。','この調査自体は、送信やアプリの変更をしません。',['この調査自体は、','送信やアプリの変更を','しません。'],body='先回り調査の範囲',items=[dict(label='情報を調べる',detail='読む権限の範囲',done=True),dict(label='送信・変更',detail='調査自体はしない',done=False)]),
scene('statement','気づきをもとに、\n次の一手を決める。','提案を受けて、次の行動を決められます。',['提案を受けて、','次の行動を','決められます。'],body='締切の確認を\nお願いしよう。',action='次の依頼の例'),
scene('recap','気づく相棒を、\nどう使う？','気づきから、次の行動へ。最後は、権限と停止。',['気づきから、','次の行動へ。','最後は、権限と停止。'],body='読む → 気づく → 相談',items=items(('調査','許可された情報'),('行動','必要な権限で')),action='次回：権限と停止')]),
dict(number=9,topic='権限と停止',slug='controls',title='【ChatGPT】任せる前に知りたい！dotsの権限と「止め方」3つ',
sources=['controls'],notes='カスタムルールは追加の境界で、既存アプリ権限や組み込みの安全要件を上書きしません。Pauseは現在の主作業、Activityから委任作業、Scheduledから定期実行をそれぞれ停止・解除します。停止はすでに完了した操作を取り消しません。これらは公式解説を要約したもので、動画撮影中にユーザーのアカウント設定は変更していません。',scenes=[
scene('permissions','任せる範囲と、\n止め方を知ろう。','便利だからこそ、任せる範囲を決めましょう。',['便利だからこそ、','任せる範囲を','決めましょう。'],body='任せる前の確認',items=[dict(label='調査と下書き',detail='依頼の範囲で',done=True),dict(label='送信や変更',detail='権限を確認',done=False)]),
scene('contrast','下書きの依頼は、\n送信の許可ではない。','下書きを作って、だけでは送信の許可になりません。',['下書きを作って、','だけでは送信の','許可になりません。'],body='依頼の範囲',items=items(('依頼したこと','下書きを作る'),('別に判断すること','実際に送信する'))),
source('official-rules','controls','Control your dot','確認する境界を、\nルールに。','公式には、実行前に確認するルールもあります。',['公式には、','実行前に確認する','ルールもあります。']),
scene('statement','ルールを加えても、\n権限は飛び越えない。','追加ルールも、アプリの権限や安全要件は変えません。',['追加ルールも、','アプリの権限や','安全要件は変えません。'],body='許可の範囲で\n任せる。',action='アプリの権限も確認'),
scene('permissions','今の作業と、\n委任した作業。','今の作業は一時停止。委任した作業は個別に停止。',['今の作業は一時停止。','委任した作業は','個別に停止。'],body='止め方を使い分ける',items=[dict(label='現在の主作業',detail='Pause',done=False),dict(label='委任した作業',detail='Activityから',done=False)]),
scene('calendar','定期実行も、\n別に解除する。','定期実行は、予約の無効化や削除が必要です。',['定期実行は、','予約の無効化や','削除が必要です。'],stat='停止',body='Scheduledで確認',items=items(('今後の予約','無効化・削除')),action='実行済みの操作は戻らない'),
scene('recap','小さな仕事から、\n任せてみよう。','任せる範囲を決め、結果を確認。dots入門、完結です。',['任せる範囲を決め、','結果を確認。','dots入門、完結です。'],body='dots入門 全9回',items=items(('依頼','範囲を決める'),('結果','中身を確認'),('停止','作業と予約を確認')),action='ご視聴ありがとう')])]

def main():
    base=json.loads((ROOT/'productions/SHORT_20261022_dots_04_editorial/creator-story.json').read_text(encoding='utf-8'))
    index=[]
    for ep in EPISODES:
        number=ep['number'];eid=f'SHORT_20261022_dots_{number:02d}_editorial';folder=HERE/f'{number:02d}'
        if (folder/'state.json').exists():raise ValueError('Do not rewrite a submitted production')
        folder.mkdir(parents=True,exist_ok=True)
        for shot in ep['scenes']:
            shot['eyebrow']=f"DOTS {number:02d} / {ep['topic']}";shot['source_ids']=ep['sources']
            if 'capture' in shot:
                cap=shot['capture'];slug=cap.pop('slug');page=cap.pop('page')
                cap.update(path=f'outputs/productions/{eid}/captures/{slug}.png',proof=f'outputs/productions/{eid}/captures/{slug}.json',source_url=f'https://learn.chatgpt.com/docs/dots/{page}')
        story={k:base[k] for k in ['schema_version','voice','rate','pronunciations','duration_seconds','music_preset']}
        story.update(id=eid,title=ep['title'],scenes=ep['scenes'],editorial=dict(checked_date='2026-10-22',series_episode=number,official_source_ids=ep['sources'],availability_note=ep['notes'],user_approved=False,visuals='One short excerpt captured from official documentation plus original editorial explanatory graphics; fictional examples are labelled. Not a live product test.'))
        validate_story(story)
        (folder/'creator-story.json').write_text(json.dumps(story,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (folder/'youtube-title.txt').write_text(ep['title']+'\n',encoding='utf-8')
        urls='\n'.join(f'https://learn.chatgpt.com/docs/dots/{page}' for page in ep['sources'])
        description=f"{ep['title']}\n\ndots入門 第{number}回：{ep['topic']}。公式資料の該当箇所を引用し、30秒で解説します。\n\n{ep['notes']}\n\n公式出典（2026年10月22日確認・撮影）\n{urls}\n\n引用画面は公式資料内の説明・UI例です。日本語の作業例とアニメーションは制作者による解説で、実際のアカウントで動作を検証した録画ではありません。利用可能な機能はプラン・地域・設定・段階的な提供により異なる場合があります。\n\n#ChatGPT #dots #AI活用 #Shorts\n"
        (folder/'youtube-description.txt').write_text(description,encoding='utf-8')
        sources=f"# dots第{number}弾：公式出典と引用\n\n確認・撮影日：2026年10月22日。\n\n"+'\n'.join(f'- [{page}](https://learn.chatgpt.com/docs/dots/{page})' for page in ep['sources'])+f"\n\n{ep['notes']}\n\n引用は本文の短い見出し・UIの必要箇所に限定。画像中の内容を改変せず、画面の拡大と切出しのみ実施。引用場面では出典ドメインと引用表示を併記し、この文書とYouTube説明欄に元URLを記載。撮影原本と座標・SHA-256は非公開の制作記録へ保存し、公開ZIPには含めない。\n"
        (folder/'SOURCES_JA.md').write_text(sources,encoding='utf-8')
        index.append(dict(number=number,topic=ep['topic'],id=eid,slug=ep['slug'],title=ep['title'],story=(folder/'creator-story.json').relative_to(ROOT).as_posix()))
    (HERE/'series.json').write_text(json.dumps(dict(id=HERE.name,title='dots入門 完結編 第5〜9弾',checked_date='2026-10-22',episodes=index,youtube_uploaded=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'authored_episodes':len(index),'scenes':sum(len(e['scenes']) for e in EPISODES)},ensure_ascii=False))

if __name__=='__main__':main()
