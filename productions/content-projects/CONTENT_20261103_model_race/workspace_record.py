"""Persist actual research and pending proposal through the common CLI.

Acceptance is intentionally not inferred from the original production request.
"""
from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name

def cli(command,body=None,**options):
    args=[sys.executable,'-m','tools.studio.content_workspace',command,'--workspace',str(ROOT)]
    for k,v in options.items():args+=['--'+k.replace('_','-'),str(v)]
    if body is not None:
        path=OUT/'work/workspace-operations'/(body['operation_id']+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');args+=['--input',str(path)]
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    return json.loads(result.stdout)

def register():
    listing=cli('list')['items']
    if any(x['content_project_id']==HERE.name for x in listing):
        state=cli('get',project_id=HERE.name)
    else:
        state=cli('create',dict(operation_id='create_model_race_v01',content_project_id=HERE.name,title='Fable 5からGPT-6.1 Solへ：AIモデル競争と次世代情報',topic='Fable5登場からGPT6Astra、Sol6.1までのOpenAIとAnthropicの競争。Fable5.5、Astra6.1、6.2の噂も紹介するショートとフル。最大限力を入れる重点企画。',format='short_and_full'))
    def apply(action,operation_id,data):
        nonlocal state
        # Recovery must never resubmit a completed mutation with a new payload.
        log=OUT/'work/workspace-operations'/(operation_id+'-result.json')
        if log.exists():return
        body=dict(operation_id=operation_id,expected_revision=state['project']['revision'],data=data)
        state=cli('apply',body,project_id=HERE.name,action=action)
        log.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sources=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']
    apply('research','research_model_race_v01',dict(research_id='research_v01',summary='公式時系列とAPI単価を照合。Fable 5.1の日付不一致は月まで採用。Astra 6.1は公開見送りの一次報道。6.2は二次の名称目撃報告で元投稿403、一般提供・性能・公開日は未確認。',checked_at='2026-11-03',sources=[dict(source_id=s['source_id'],kind=s['kind'],title=s['title'],url=s['url'],checked_at='2026-11-03') for s in sources]))
    apply('capture','inspect_official_pages_v01',dict(inspection_id='official-pages',target_feature='過去のモデル発表を説明する公式ページの実画面引用',status='available',checked_at='2026-11-03',route='ユーザーPCのChromeで各社公式発表を開く。Fable 5.1とOpus 5.5はヒーロー読込後に再撮影。',result='Fable 5、Fable 5.1、Astra、Sol、Opus 5.5の公開ページを保存。モデル性能対決は未実演。',app='Chrome',login_state='公開ページ、認証不要',feature_entry='sources.jsonの公式発表URL',display_result='見出し・製品ビジュアル・日付を確認。未読込画像は採用しない。',save_result='outputs/content-projects/CONTENT_20261103_model_race/_private/captures/ に原本、assets/ に短い公開用切り出し。',legibility='原本幅1237px。1400px目安未達と記録。自作図は1920px。',shots=[]))
    apply('capture','inspect_claude_picker_v01',dict(inspection_id='claude-picker',target_feature='現在のClaudeモデル選択メニュー',status='blocked',checked_at='2026-11-03',route='Windows ClaudeアプリをAX確認、モデル欄操作、前面化を試行。',result='Opus 5.5のモデル欄はAXで確認。座標不整合と白い表示がありメニューの公開用撮影は未取得。',app='Claude desktop',login_state='既存ログインあり。私的な会話が表示されたため原本は公開しない。',feature_entry='既存画面のモデル欄',display_result='メニュー撮影未取得',save_result='公開用のアプリキャプチャなし',legibility='未評価。公式発表と自作図で歴史を説明する。',shots=[]))
    for sid in ['fable5','astra','fable51','sol61','opus55']:
        source=next(s for s in sources if s['source_id']==sid)
        apply('asset','asset_'+sid+'_v01',dict(asset_id=sid,kind='official_capture',path=(OUT/'assets'/(sid+'.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',source_url=source['url'],source_checked_at='2026-11-03'))
    episodes=[
       dict(episode_id='model-race-short',title='【ChatGPT・Claude】Fable 5→GPT-6！AI競争で変わった3つのこと',overview='主要な転機と競争の3軸を約1分で示す。噂は未確認として短く予告。',intended_message='長い仕事、費用、人の意図と権限の両立を見る。',duration_seconds=60,demo_idea='取得した公式キャプチャと自作の時系列・仕事の流れ。独自性能対決は未実演。',article_role='詳細な出典・日付差異・価格条件を記事へ。',capture_inspection_id='official-pages'),
       dict(episode_id='model-race-full',title='【ChatGPT・Claude】Fable 5からGPT-6.1 Solまで｜新モデル競争と次世代の噂',overview='6月〜9月の転機→費用と任せ方→次世代情報を確度別に。既存男女、約10秒エンド画面。',intended_message='新しい名前の順位だけでなく、自分の仕事で成果・費用・確認の境界を見極める。',duration_seconds=540,demo_idea='公式発表とAPI価格を引用し、具体例と動く図で説明。次世代の未発表情報は破線と明示。',article_role='全出典、価格の条件、噂の原投稿取得制約を参照可能にする。',capture_inspection_id='official-pages')]
    apply('proposal','proposal_model_race_v01',dict(proposal_id='proposal-v01',count_reason='ユーザー指定のショートとフルの2本。短い入口と背景・根拠の説明で役割を分ける。',episodes=episodes))
    followups=[s for s in sources if s['source_id'] in ['astra62-post','astra62-clarification','astra62-provenance']]
    apply('research','research_model_race_v02',dict(research_id='research_v02',summary='章立ては企画v01のまま。Astra 6.2の元投稿と後続の補足を実ブラウザで閲覧できた。投稿者が他者提供・元画像の出所不明と補足しており、画像の真正性・モデルの実態・一般提供・性能・公開日は未確認とする。初回の403と後続確認を別に記録。',checked_at='2026-11-03',sources=[dict(source_id=s['source_id'],kind=s['kind'],title=s['title'],url=s['url'],checked_at='2026-11-03') for s in followups]))
    for aid in ['astra62-post-author','astra62-usage-image']:
        apply('asset','asset_'+aid+'_v01',dict(asset_id=aid,kind='original',path=(OUT/'assets'/(aid+'.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',source_url='https://x.com/TokenGremlin/status/2116834891744600291',source_checked_at='2026-11-03',context='Public social post excerpt, not an official product announcement. Image provenance unresolved.'))
    apply('capture','inspect_rumor_post_v02',dict(inspection_id='rumor-posts',target_feature='名称目撃の原投稿と出所に関する後続補足',status='available',checked_at='2026-11-03',route='Chromeで既知の原投稿URLを開き、投稿者の補足リンクも閲覧。',result='原投稿は閲覧可能。投稿者が自分の画面ではなく他者提供、さらに元の出所をたどれなかったと補足している。',app='Chrome / X',login_state='既存ログインで読取のみ。投稿・反応・フォロー・共有変更なし。',feature_entry='原投稿とsources.jsonの補足URL',display_result='本文・画像・投稿日時・補足を確認。画像の真正性と実モデルは未検証。',save_result='原本は非公開、投稿者名と添付画像だけを別切り出しで保存。',legibility='原本1237px。短い公開用切り出し。元の画像は利用量の内訳とされ、性能比較ではない。',shots=[]))
    state=cli('get',project_id=HERE.name)
    print(json.dumps(dict(revision=state['project']['revision'],phase=state['project']['phase'],accepted_proposal=state['project']['accepted_proposal'],assets=len(state['project']['assets'])),ensure_ascii=False))

if __name__=='__main__':register()
