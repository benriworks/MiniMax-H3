"""Persist real research and a pending one-short proposal; never infer acceptance."""
from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
USER_REQUEST='ショート動画のみでいいので、アンソロピックからキーマンの退社発表が相次いでいることに対する考察動画にしてください'

def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def cli(command,body=None,**kwargs):
    args=[sys.executable,'-m','tools.studio.content_workspace',command,'--workspace',str(ROOT)]
    for k,v in kwargs.items():args+=['--'+k.replace('_','-'),str(v)]
    if body is not None:
        p=OUT/'work/workspace-operations'/(body['operation_id']+'.json');save(p,body);args+=['--input',str(p)]
    r=subprocess.run(args,check=False,capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
    if r.returncode:raise RuntimeError(r.stderr)
    return json.loads(r.stdout)
def event(action,op,data):
    log=OUT/'work/workspace-operations'/(op+'-result.json')
    if log.exists():return json.loads(log.read_text(encoding='utf-8'))
    state=cli('get',project_id=HERE.name)
    result=cli('apply',dict(operation_id=op,expected_revision=state['project']['revision'],data=data),project_id=HERE.name,action=action)
    save(log,result);return result
def record():
    if not any(x['content_project_id']==HERE.name for x in cli('list')['items']):
        cli('create',dict(operation_id='create_departures_v01',content_project_id=HERE.name,title='Claude Code関係者の退社と今後の観察点',topic=USER_REQUEST,format='short_only'))
    sources=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']
    event('research','research_departures_v01',dict(research_id='departures-v01',checked_at='2026-11-04',summary='直近のClaude Code関係者3人を本人投稿で確認。JSTの発表日で10/24、10/24、11/4。本人投稿・会社公式の役割説明・取材報道を分ける。退社の共通原因や影響は未確認。前のモデル競争動画とは別にショート1本だけを企画。',sources=[dict(source_id=s['source_id'],kind=s['kind'],title=s['title'],url=s['url'],checked_at='2026-11-04') for s in sources]))
    event('capture','capture_news_sources_v01',dict(inspection_id='news-sources',target_feature='退社発表と製品責任者の役割を裏付ける公開一次資料',status='available',checked_at='2026-11-04',app='Chrome / X / Claude公式サイト',login_state='Xは既存ログインで読取。会社公式記事は公開ページ。投稿・反応・フォローを変更しない。',feature_entry='本人の3投稿と公式PM記事の既知URL',route='検索取得の403後、本人投稿の既知URLをユーザーPCのChromeで開いた。公開本文と日時を読んで撮影。',result='3人の本人投稿と公式PM記事の原本を保存。人事発表のニュースなので、アプリ操作で退社を証明する実演は該当しない。',display_result='発表の本文、JSTの日付、役割説明を確認。原因や今後の品質は未確認。',save_result='outputs/content-projects/CONTENT_20261104_anthropic_departures/_private/captures/ に原本、assets/ に短い引用。',legibility='原本2545×1264。X本文の切り出しは582px幅で、本文幅1400px達成とはしない。大きい日本語要約を併用。',shots=[]))
    for aid in ['thariq-quote','anthony-quote','cat-quote','official-role']:
        sid={'thariq-quote':'thariq-post','anthony-quote':'anthony-post','cat-quote':'cat-post','official-role':'cat-official-role'}[aid]
        source=next(s for s in sources if s['source_id']==sid)
        event('asset','asset_'+aid+'_v01',dict(asset_id=aid,kind='official_capture' if aid=='official-role' else 'original',path=(OUT/'assets'/(aid+'.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',source_url=source['url'],source_checked_at='2026-11-04',context='会社公式の役割説明' if aid=='official-role' else '本人の公開投稿。会社公式発表と分類しない。'))
    event('proposal','proposal_departures_v01',dict(proposal_id='proposal-v01',count_reason='ユーザー指定によりショート1本。直近3人の事実と製品作りの知見の継承という一つの考察に絞る。',episodes=[dict(episode_id='anthropic-departures-short',title='【Claude】Claude Codeのキーマンが相次ぎ退社。これから何を見る？',overview='本人投稿で3人の退社を確認→役割→製品作りの知見の継承→機能改善・使い勝手・安定性という今後の観察点。',intended_message='退社の共通原因や悪化を決め付けず、使いやすい製品に仕上げる人材と引き継ぎへ注目する。',duration_seconds=58,demo_idea='取得した本人投稿3件と公式の役割説明を引用。依頼・確認・修正を動く図で示す。人事をアプリ操作で証明する実演はしない。',article_role='投稿日時と最終勤務日の違い、担当、原文、確認できない因果、考察の限界を詳しく残す。',capture_inspection_id='news-sources')]))
    event('feedback','request_scope_departures_v01',dict(feedback_id='original-request',proposal_id='proposal-v01',text=USER_REQUEST,kind='comment',interpretation='題材変更とショート1本の明示依頼。後から作った構成の採用や本番生成許可をこの返答から捏造しない。確認質問を提示し、返答待ち。'))
    state=cli('get',project_id=HERE.name);save(OUT/'work/workspace-current.json',state)
    print(json.dumps(dict(revision=state['project']['revision'],phase=state['project']['phase'],accepted=state['project']['accepted_proposal']),ensure_ascii=False))

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    record()
