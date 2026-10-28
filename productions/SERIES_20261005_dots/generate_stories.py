"""Editorial source for nine Japanese dots Shorts; official facts checked 2026-10-05."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import validate_story

HERE=Path(__file__).parent
SOURCES={
 'launch':('OpenAI — Introducing dots','https://openai.com/index/introducing-dots/'),
 'overview':('OpenAI — Meet dots','https://learn.chatgpt.com/docs/dots'),
 'start':('OpenAI — Get started with your dot','https://learn.chatgpt.com/docs/dots/getting-started'),
 'computer':('OpenAI — Computers and apps','https://learn.chatgpt.com/docs/dots/computers-and-apps'),
 'tasks':('OpenAI — Tasks and memory','https://learn.chatgpt.com/docs/dots/tasks-and-memory'),
 'channels':('OpenAI — Message your dot','https://learn.chatgpt.com/docs/dots/channels'),
 'controls':('OpenAI — Controls','https://learn.chatgpt.com/docs/dots/controls'),
}
MALE={'path':'outputs/claude-acquired-20260919/MiniMax_H3_Claude_Acquired_00001_.mp4','proof':'verification/claude-acquired-2026-09-19.json'}
FEMALE={'path':'outputs/claude-acquired-female-silhouette-20260930/MiniMax_H3_Claude_Acquired_Female_Silhouette_00001_.mp4','proof':'verification/claude-acquired-female-silhouette-2026-09-30.json'}
PRONUNCIATIONS=[{'source':a,'target':b} for a,b in [
 ('dots','ドッツ'),('dot','ドット'),('ChatGPT','チャットジーピーティー'),('GPT-6 Astra','ジーピーティーシックス、アストラ'),
 ('OpenAI','オープンエーアイ'),('Business Premium','ビジネスプレミアム'),('Enterprise','エンタープライズ'),('Pro','プロ'),
 ('PC','ピーシー'),('Gmail','ジーメール'),('Drive','ドライブ'),('GitHub','ギットハブ'),('Slack','スラック'),('Teams','チームズ'),
 ('Activity','アクティビティ'),('Scheduled','スケジュールド'),('SMS','エスエムエス'),
]]

def scene(kind,headline,captions,source_ids,**kwargs):
    return dict(kind=kind,headline=headline,narration=''.join(captions).replace('\n',''),captions=captions,source_ids=source_ids,**kwargs)
def hero(headline,captions,source_ids,body,*,female=False):
    return scene('hero',headline,captions,source_ids,body=body,media=FEMALE if female else MALE)
def diagram(graphic,headline,captions,source_ids,labels=(),body=None,**kwargs):
    return scene('diagram',headline,captions,source_ids,graphic=graphic,items=[{'label':x} for x in labels],**({'body':body} if body else {}),**kwargs)
def steps(headline,captions,source_ids,labels,**kwargs):
    return scene('steps',headline,captions,source_ids,items=[{'label':x} for x in labels],**kwargs)
def cards(headline,captions,source_ids,rows,**kwargs):
    return scene('cards',headline,captions,source_ids,items=[{'label':a,'detail':b} for a,b in rows],**kwargs)

EPISODES=[
 ("発表日と利用対象", "ChatGPTに常駐する相棒「dots」が登場｜発表日と利用対象 #Shorts", [
  hero('ChatGPTに、\n相棒が来た。',['常駐する相棒、dots。'],['launch'],'dots / 30秒で紹介'),
  scene('stat','2026年、\n9月29日に発表。',['9月29日、発表。'],['launch'],stat='2026.09.29',body='対象プランへ順次提供',tone='light'),
  diagram('parallel','会話の外でも、\n仕事を進める。',['会話の外でも、','仕事を進めます。'],['launch','tasks'],['調査','整理','開発']),
  steps('対象プランへ、\n順次スタート。',['Proなどの対象プランへ、','順次提供。'],['overview'],['Pro','Business Premium','Enterprise']),
  cards('使える条件も、\n確認しよう。',['年齢や地域、','管理者設定も確認。'],['overview'],[('Pro','年齢・地域条件あり'),('企業','管理者設定も確認')],tone='light'),
  diagram('laptop','PCで作って、\n自分らしい相棒に。',['PCで作って、','名前や外見も選べる。'],['start'],body='名前・色・見た目を選択'),
  scene('stat','頭脳は、\nGPT-6 Astra。',['頭脳は、GPT-6 Astra。'],['launch'],stat='GPT-6 Astra',body='常駐するAIエージェント',tone='light'),
  hero('次は、\n専用のクラウドPC。',['次は、クラウドPC。'],['computer'],'全9本で、ひとつずつ。',female=True),
 ],"2026年9月29日はOpenAIの発表日で、対象ユーザーへの順次提供開始日です。全員が同日に使えるという意味ではありません。Pro 100・200・500は年齢条件（公式表記: users over 18）と地域条件があり、EEA・英国・スイスは対象外。Business Premiumは世界各地へ順次展開。Enterpriseは管理者による有効化が必要です。作成はデスクトップアプリ／PCブラウザーから。モバイルアプリは対応更新後に利用でき、モバイルWebには未対応です。"),
 ("専用クラウドPC", "PCを閉じても仕事が進む？dotsの専用クラウドPC #Shorts", [
  hero('PCを閉じても、\n仕事が進む。',['PCを閉じても、','仕事が進む。'],['overview','computer'],'dots / クラウドPC',female=True),
  diagram('cloud','dot専用の\nPCとブラウザー。',['専用のPCと\nブラウザーで、'],['computer'],body='クラウドで作業'),
  diagram('parallel','調べる。まとめる。\n分析する。',['調査、資料づくり、','データ分析。'],['computer'],['調査','資料作成','分析'],tone='light'),
  steps('作業の状態も、\n引き継げる。',['ファイルや作業の\n状態も保持。'],['computer'],['ファイルを保持','続きから作業']),
  diagram('laptop','手元のPCは、\n別に接続。',['手元のPCを使うなら、','別に接続。'],['computer'],body='ローカル作業の接続'),
  cards('ローカル作業は、\nこの条件。',['オンラインで、','アプリを開いておきます。'],['computer'],[('接続','オンライン'),('アプリ','開いたまま')],tone='light'),
  steps('画面を見て、\n自分で操作も。',['クラウドの画面を見て、','操作を引き取ることも。'],['computer'],['画面を確認','操作を引き取る']),
  hero('使い分けて、\n仕事を進めよう。',['クラウドと手元を、','使い分けよう。'],['computer'],'次は、アプリ連携。'),
 ],"dot専用のクラウドPCと、ユーザーのローカルPCへの接続は別機能です。クラウド側はユーザーのPCがオフでも作業を続けられます。ローカルPCを使う作業には、オンライン状態とChatGPTアプリの起動が必要です。クラウドブラウザーでは別途ログインが必要な場合があり、サイト側でアクセスが制限されることもあります。"),
 ("アプリ連携", "4,000以上のアプリとつながる仕組み｜dotsの連携機能 #Shorts", [
  hero('いつものアプリと、\nつながる。',['dotsは、','いつものアプリと\nつながる。'],['launch','computer'],'dots / アプリ連携'),
  scene('stat','連携の仕組みは、\n4,000以上に対応。',['連携の仕組みは、','4000以上の\nアプリに対応。'],['launch'],stat='4,000+',body='プラグインのエコシステム',tone='light'),
  diagram('apps','メールも、資料も、\nコードも。',['メール、資料、','コードの作業へ。'],['computer'],['メール','資料','コード']),
  cards('たとえば、\nこんな連携。',['GmailやDrive、','GitHubなど。'],['computer'],[('Gmail','メールを確認'),('Drive','資料を参照'),('GitHub','課題を調査')]),
  steps('必要なものを、\n自分で接続。',['使うアプリは、','自分で接続します。'],['computer'],['アプリを選ぶ','アカウントを接続'],tone='light'),
  diagram('control','読める範囲と、\nできる操作。',['読む権限と、','送る権限は別。'],['computer'],['読む','送る'],body='権限は分けて設定'),
  cards('使える連携は、\n環境で変わる。',['対応状況や、','組織の設定も確認。'],['computer'],[('対応','アカウントで確認'),('組織','有効な連携を確認')],tone='light'),
  hero('まずはひとつ、\nつないでみよう。',['まずは必要な\nアプリをひとつ。'],['start'],'次は、並行作業。',female=True),
 ],"4,000以上という数は、OpenAI発表にあるプラグインのエコシステム全体の規模です。全アプリが最初から接続済み、または全アカウントで利用可能という意味ではありません。インストール済み・有効なプラグイン、接続先アカウント、組織設定と権限によって利用範囲が変わります。Slack等の連絡先接続と、アプリやPCへのアクセス許可は別です。"),
 ("並行作業", "ひとつの会話で複数の仕事へ｜dotsの並行作業 #Shorts", [
  hero('同時に、\nいくつも頼める。',['dotsに、','いくつもの仕事を。'],['tasks'],'dots / 並行作業',female=True),
  diagram('parallel','いくつもの仕事を、\n並行して。',['調査と整理を、並行して。'],['tasks'],['調査','整理','開発']),
  steps('仕事を分けて、\n裏で進める。',['別のエージェントに、','分担もできます。'],['tasks'],['部分作業を委任','裏側で作業を進める'],tone='light'),
  diagram('chat','待っている間も、\n会話できる。',['作業中も、','会話は続けられる。'],['tasks'],body='追加の情報も伝えられる'),
  scene('quote','途中で、\n優先順位を変更。',['追加の指示や、','優先順位の変更も。'],['tasks'],body='先にこの資料を\nまとめて。',tone='light'),
  steps('Activityで\n進み具合を確認。',['結果は、\nActivityで確認。'],['controls'],['進行中の仕事を見る','結果を開く']),
  scene('checklist','完了の表示と、\n成果の確認。',['完了表示だけでなく、','成果も確認。'],['tasks'],body='受け取ったら',items=[{'label':'内容を読む'},{'label':'依頼と照らす'}],action='最後は自分で確認',tone='light'),
  hero('ひとつの会話で、\n複数の仕事へ。',['会話はひとつ。','進む仕事は、いくつも。'],['tasks'],'次は、記憶と好み。'),
 ],"dotは必要に応じて作業の一部をバックグラウンドのエージェントへ委任し、複数の仕事を並行して進められます。常にすべての仕事が同時実行される、無制限に実行できる、という保証ではありません。新しい作業には必要な文脈が渡され、会話全体が自動的にすべて共有されるわけではありません。Activityと実際の成果物を確認してください。"),
 ("記憶と好み", "好みを覚える相棒｜dotsの記憶はどこまで？ #Shorts", [
  hero('好みを覚える、\nあなたの相棒。',['dotsが、','好みを覚えていく。'],['tasks'],'dots / 記憶と好み'),
  diagram('memory','好み・決定・仕事を、\nメモに。',['好みや決定、仕事をメモ。'],['tasks'],['好み','決定','仕事']),
  cards('ChatGPTの記憶も、\n必要に応じて。',['ChatGPTの記憶も、','活用。'],['tasks'],[('記憶','関連する情報を参照')],tone='light'),
  scene('quote','覚えてほしいことを、\n言葉にしよう。',['例えば、報告は短く、','結論から。'],['tasks'],body='報告は短く、\n結論から。',tone='light'),
  diagram('chat','少しずつ、\n好みに合わせる。',['フィードバックで、','好みを伝える。'],['tasks'],body='伝える → 次の仕事へ'),
  cards('会話を全部、\n保存する仕組み？',['全会話の、','丸ごと保存では\nありません。'],['tasks'],[('メモ','要点や継続中の情報')],tone='light'),
  diagram('control','読める情報でも、\n共有の許可は別。',['情報を読む許可と、','共有する許可は別。'],['tasks'],body='アクセスと共有を分ける'),
  hero('覚えてもらって、\n育てる相棒。',['好みを伝えて、','相棒を育てよう。'],['tasks'],'次は、会話と通話。',female=True),
 ],"dotは現在の会話、関連するChatGPTの保存メモリ、自分用のメモを利用します。dotのメモはChatGPTの保存メモリとは別で、全会話の完全な書き起こしではありません。動画内の依頼文は説明用の例です。私的な情報へアクセスできることは、その情報を別の場所で共有してよいことを意味しません。"),
 ("会話と通話", "ChatGPT・Slack・Teamsで同じ相棒と｜dotsの会話と通話 #Shorts", [
  hero('場所が変わっても、\n同じ相棒。',['dotsは、','いろんな場所で話せる。'],['channels'],'dots / 会話と通話',female=True),
  diagram('chat','ChatGPT、Slack、\nTeamsから。',['ChatGPT、Slack、','Teamsから。'],['channels'],['ChatGPT','Slack','Teams']),
  diagram('memory','連絡先を変えても、\n関係は続く。',['同じdotと、','文脈を引き継げる。'],['channels','tasks'],body='同じ相棒との会話',tone='light'),
  diagram('chat','声で、\n相談できる。',['声で話すことも。'],['channels'],body='ChatGPTの通話から'),
  cards('通話中も、\n文字で補足。',['通話中に、文字で補足も。'],['channels'],[('声','話して相談'),('文字','情報を追記')],tone='light'),
  diagram('parallel','通話を終えても、\n仕事は続く。',['通話を切っても、','仕事は止まりません。'],['channels'],body='終了と停止は別の操作'),
  cards('これからの機能も、\n区別しよう。',['SMSや、dotからの通話は','今後の予定。'],['channels'],[('SMS','今後の対応予定'),('dotの発信','今後の対応予定')],tone='light'),
  hero('会話する場所を、\n選べる。',['使いやすい場所で、','同じ相棒と。'],['channels'],'次は、定期実行。'),
 ],"ChatGPT、接続したSlack／Teamsで同じdotと会話でき、関連する文脈を引き継げます。ただし各チャンネルのメッセージが自動で丸ごと複製されるわけではありません。ChatGPTのデスクトップ／Webでは通話できます。通話終了は割り当て済みの作業停止を意味しません。2026年10月5日の確認時点で、SMSとdotから発信する通話は今後の予定として案内されています。モバイルは対応アプリ更新後、モバイルWebは未対応です。"),
 ("定期実行", "毎朝の確認を任せる｜dotsの定期実行とイベント監視 #Shorts", [
  hero('毎朝の確認、\n任せられる？',['dotsに、','繰り返しの仕事を。'],['tasks'],'dots / 定期実行'),
  scene('quote','時間を決めて、\n繰り返す。',['例えば、毎朝9時に','予定を確認。'],['tasks'],body='毎朝9時に、\n予定を確認して。',tone='light'),
  steps('頼むときは、\nここを具体的に。',['時刻、タイムゾーン、','通知先も指定。'],['tasks'],['何をするか','時刻とタイムゾーン','通知先と終了日']),
  diagram('schedule','会話だけで、\n済ませない。',['予定の保存を確認。'],['tasks'],body='保存された予定を確認'),
  cards('Scheduledで\n変更・キャンセル。',['Scheduledで、','変更やキャンセル。'],['tasks','controls'],[('確認','登録された予定'),('変更','止める・直す')],tone='light'),
  diagram('research','出来事をきっかけに、\n動くことも。',['対応する連携先なら、','出来事をきっかけにも。'],['tasks'],body='対応する連携先が必要'),
  diagram('control','接続しただけでは、\n監視は始まらない。',['監視の対象と条件を指定。'],['tasks'],body='対象・条件・通知を指定',tone='light'),
  hero('繰り返す仕事を、\nひとつ任せよう。',['まずは、','毎朝ひとつの確認から。'],['tasks'],'次は、先回り調査。',female=True),
 ],"決まった時刻の定期実行には、保存されたスケジュールが必要です。会話で話しただけで設定済みと思わず、保存を確認し、Scheduledで管理します。内容・時刻・タイムゾーン・期間・通知条件・通知先を指定してください。イベント監視は連携先が対応している場合に利用でき、接続しただけでは始まりません。動画の依頼は説明用の例です。"),
 ("先回り調査", "頼む前に気づきを届ける？dotsの先回り調査 #Shorts", [
  hero('先回りして、\n調べてくれる。',['dotsが、','先回りして調べる。'],['tasks'],'dots / 先回り調査',female=True),
  diagram('research','許可した情報から、\n役立つ手がかりを。',['許可された情報を、調査。'],['tasks'],['資料','メール','メモ']),
  diagram('memory','気づいたことは、\n自分用のメモに。',['気づきを自分用のメモに。'],['tasks'],body='次の提案につなげる',tone='light'),
  cards('次の一手を、\n提案する。',['次の一手や、','気になる点を知らせる。'],['tasks'],[('提案','次に進めること'),('気づき','確認したい点')]),
  diagram('control','先回り調査は、\n読み取り中心。',['この調査では、','送信や変更はしません。'],['tasks'],body='送信や更新はしない',tone='light'),
  diagram('laptop','ブラウザーを、\n勝手に操作しない。',['ブラウザーやPCも、','操作しません。'],['tasks'],body='先回り調査の範囲'),
  steps('提案の先は、\n通常の権限で。',['実行するときは、','通常の権限と承認で。'],['tasks','controls'],['提案を確認','必要な作業を依頼'],tone='light'),
  hero('気づきをもらって、\n次の一歩へ。',['提案を確かめて、','次の一歩へ。'],['tasks'],'次は、権限と停止。'),
 ],"ここで扱うのはProactive research（先回り調査）です。利用を許可された情報の読み取りと私的なメモ作成が中心で、この機能自体は送信、アプリの変更、ブラウザーやコンピューターの操作を行いません。提案の後に依頼する実作業には、通常の権限と承認確認が適用されます。利用者が明示して任せる定期実行とは範囲が異なります。"),
 ("権限と停止", "dotsに任せる前に｜権限・確認・停止のポイント #Shorts", [
  hero('任せる範囲は、\n自分で決める。',['dotsに任せる範囲を、','決めよう。'],['controls'],'dots / 権限と停止'),
  diagram('control','接続するアプリと、\n操作の権限。',['アプリ権限と、安全確認。'],['controls'],['読む','編集','送信']),
  scene('quote','境界を、\n具体的に伝える。',['返信は下書きまで。','送信前に確認。'],['controls'],body='返信は下書きまで。\n送信前に確認。',tone='light'),
  steps('Activityで\n作業を確認。',['Activityで確認。'],['controls'],['進み具合を見る','確認待ちに答える']),
  diagram('parallel','会話の停止と、\n作業の停止は別。',['会話を止めても、','別の作業は続くことも。'],['controls'],body='委任した仕事も確認',tone='light'),
  steps('委任した仕事も、\n停止を確認。',['委任した仕事も、','個別に停止。'],['controls'],['Activityを開く','個別の作業を止める']),
  diagram('schedule','定期実行は、\n予定もキャンセル。',['定期実行の予定も、','キャンセル。'],['controls','tasks'],body='Scheduledで確認',tone='light'),
  hero('任せる。確かめる。\n上手に付き合う。',['止めても、','済んだ操作は戻りません。'],['controls'],'結果まで確認しよう。',female=True),
 ],"既存のアプリ権限、安全対策、自動レビューに加えて、必要ならカスタムルールを指定できます。下書き依頼だけで送信まで許可したことにはなりません。一方、すべての操作で毎回人の承認が必須という説明でもありません。主タスクの停止、委任した作業の停止、保存された予定のキャンセルは別々に確認します。停止は実行済みの操作を元に戻しません。"),
]

def main():
    series={'id':'SERIES_20261005_dots','title':'dotsを30秒ずつ。','checked_date':'2026-10-05','episodes':[],
            'sources':{k:{'title':v[0],'url':v[1]} for k,v in SOURCES.items()},
            'publication_status':'not_uploaded','user_approved':False,
            'shared_google_link':'https://share.google/gymVxp9R6pxOhmeGv',
            'shared_link_status':'HTTP 403; destination unverified; researched official OpenAI pages independently'}
    for n,(topic,title,scenes,note) in enumerate(EPISODES,1):
        for s in scenes:
            s['eyebrow']=f'DOTS {n:02d} / 09'
            # Keep subtitles to one readable line, leaving room for Shorts controls.
            s['captions']=[line for part in s['captions'] for line in part.split('\n')]
        story=dict(schema_version=1,id=f'SHORT_20261005_dots_{n:02d}',title=title.replace(' #Shorts',''),duration_seconds=30,
                   voice='Microsoft Sayaka',rate=1,pronunciations=PRONUNCIATIONS,scenes=scenes,
                   editorial={'checked_date':'2026-10-05','series_episode':n,'official_source_ids':sorted({x for s in scenes for x in s['source_ids']}),
                              'visuals':'Original motion graphics and reused fictional programmer characters; not recorded product UI.',
                              'availability_note':note,'user_approved':False})
        try:validate_story(story)
        except ValueError as e:
            for i,s in enumerate(scenes):
                try:validate_story({**story,'scenes':[s,s,s]})
                except ValueError as detail:print(f'EP {n} scene {i}: {detail}')
            raise e
        folder=HERE/f'{n:02d}';folder.mkdir(parents=True,exist_ok=True)
        (folder/'creator-story.json').write_text(json.dumps(story,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        source_ids=story['editorial']['official_source_ids']
        description=(f'dotsの機能を30秒ずつ紹介する全9本シリーズ、第{n}回「{topic}」。\n\n'+note+
                     '\n\n情報確認日：2026年10月5日。機能・対象プラン・提供地域は変更されることがあります。\n'+
                     'OpenAI公式資料をもとにした非公式の紹介動画です。画面は独自のモーショングラフィックスで、実機操作の録画ではありません。登場人物は架空のキャラクターです。\n\n出典（OpenAI公式）\n'+
                     '\n'.join(f'{SOURCES[k][0]}\n{SOURCES[k][1]}' for k in source_ids)+
                     '\n\n#dots #ChatGPT #OpenAI #AI活用 #Shorts\n')
        (folder/'youtube-title.txt').write_text(title+'\n',encoding='utf-8')
        (folder/'youtube-description.txt').write_text(description,encoding='utf-8')
        (folder/'narration.txt').write_text('\n'.join(s['narration'] for s in scenes)+'\n',encoding='utf-8')
        series['episodes'].append({'number':n,'topic':topic,'title':story['title'],'story':(folder/'creator-story.json').relative_to(ROOT).as_posix(),'source_ids':source_ids})
        print(n,topic,'narration_chars',sum(len(s['narration']) for s in scenes))
    (HERE/'series.json').write_text(json.dumps(series,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sources_doc='# dots紹介ショートの出典・公開条件\n\n確認日：2026年10月5日。公式資料の内容を日本語で要約した非公式の動画。全9本、各30秒。\n\n'
    sources_doc+='[OpenAIの発表](https://openai.com/index/introducing-dots/)の日付は2026年9月29日。対象プランへ順次提供開始で、全利用者への一斉公開日とは扱わない。\n\n'
    sources_doc+='## 一次資料\n\n'+'\n'.join(f'- {k}: [{v[0]}]({v[1]})' for k,v in SOURCES.items())+'\n\n'
    for n,(topic,_,scenes,note) in enumerate(EPISODES,1):
        sources_doc+=f'## {n:02d} {topic}\n\n{note}\n\n'
        sources_doc+='| 場面 | 紹介する内容 | 公式資料 |\n| --- | --- | --- |\n'
        for i,s in enumerate(scenes,1):
            links=' / '.join(f'[{k}]({SOURCES[k][1]})' for k in s['source_ids'])
            sources_doc+=f"| {i} | {s['narration']} | {links} |\n"
        sources_doc+='\n'
    sources_doc+='## 表現と公開について\n\n文字の最低サイズは1080px幅で54px。生成ツール名・「図解イメージ」の画面注釈は付けない。男女キャラクター素材は前回までの制作から再利用する。YouTubeへの投稿操作は実行せず、動画・字幕・カバー・説明欄を納品する。公式資料は要約とリンクを掲載し、調査用の原文スナップショットは公開用ZIPへ入れない。\n\n'
    sources_doc+='共有されたGoogleリンクはHTTP 403で転送先を確認できなかったため、OpenAIの公式発表とドキュメントから独立して照合した。専門担当dotの企業向けプレビュー、SMS、dotから発信する通話は一般提供済みの機能として扱わない。\n'
    (HERE/'SOURCES_JA.md').write_text(sources_doc,encoding='utf-8')

if __name__=='__main__':main()
