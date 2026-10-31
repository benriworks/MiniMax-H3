"""Save the supplied two-topic brief, evidence bounds and reusable public assets."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace

def main():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    pid=HERE.name;plan=json.loads((HERE/'plan.json').read_text(encoding='utf-8'))
    try:service.get(pid)
    except KeyError:service.create(dict(content_project_id=pid,operation_id='op_ai_news_create',title='Claude UltraとChatGPTスマホ2アカウント',topic='ユーザー指定の2026-10-31ニュース2本',audience='ClaudeやChatGPTを仕事と個人で使う人'))
    def current():return service.get(pid)['project']
    def apply(action,data,token):
        # Only issue a new operation once; do not relabel old evidence on restart.
        operation='op_ai_news_'+token
        if any(h['operation_id']==operation for h in history()):return
        service.apply(pid,action,dict(operation_id=operation,expected_revision=current()['revision'],data=data))
    def history():
        with service.database.session() as c:
            return [dict(row) for row in c.execute('SELECT operation_id FROM content_project_revisions WHERE project_id=?',(pid,)).fetchall()]
    urls=[('ultra_help',plan['episodes'][0]['source_url'],'What is the Ultra plan?'),('ultra_price','https://claude.com/pricing','Claude Pricing'),
          ('account_release','https://help.openai.com/en/articles/6825453-chatgpt-release-notes','ChatGPT release notes'),('account_help',plan['episodes'][1]['source_url'],'Using multiple ChatGPT accounts on web and mobile')]
    apply('research',dict(research_id='research_news_v01',checked_at='2026-10-31',summary='公式本文4ページと実画面を照合。個別Ultra反映とスマホ実機切替は未実証。旧slugのモバイル未対応情報は新本文とリリースノートで解消。',sources=[dict(source_id=i,url=u,title=t,kind='official',checked_at='2026-10-31') for i,u,t in urls]),'research')
    for i,ep in enumerate(plan['episodes']):
        apply('capture',dict(inspection_id='inspection_'+ep['id'],target_feature='Ultra認証状態の実演' if i==0 else 'ChatGPTスマホ2アカウントの切替実演',status='blocked',checked_at='2026-10-31',
            route='Claude DesktopとChromeのclaude.ai/settings/usage' if i==0 else 'Computer Useのアプリ一覧とAndroid SDK adb devices',
            result='使用量画面は撮影できたがMax表示。Ultraの認証・反映は実証できない。公式条件の引用と図解を使用。' if i==0 else '接続スマホ0、端末ミラーなし。公式掲載の画面例と設定手順を使用。',
            app='Claude Desktop / Chrome' if i==0 else 'Android SDK / Windows',login_state='ログイン済みWebを観察' if i==0 else 'スマホの接続なし',
            feature_entry='設定→使用量' if i==0 else '公式の設定→Switch accountを確認',display_result='Maxと現在のセッション欄を観察' if i==0 else '実機の表示は未確認',
            save_result='原本は_private/capturesへ保存。私的残量は非公開。' if i==0 else '公式例の引用原本をcapturesへ保存。実機原本は未取得。',legibility='公式原本は約1240px幅、引用の必要範囲を切出し。',shots=[]),'capture_'+str(i))
    episodes=[]
    for ep in plan['episodes']:
        episodes.append(dict(episode_id=ep['id'],title=ep['title'],overview=ep['conclusion'],intended_message=ep['conclusion'],duration_seconds=45,
            demo_idea='公式画面と説明図。個別の反映完了や実機切替を実証したとはしない。',article_role='契約条件、確認手順、今回の実機確認の範囲を補足',capture_inspection_id='inspection_'+ep['id']))
    apply('proposal',dict(proposal_id='proposal_news_v01',count_reason='ユーザー指定の独立した2ニュースを1本1結論で2本にする。',episodes=episodes),'proposal')
    apply('feedback',dict(feedback_id='feedback_news_user_brief',proposal_id='proposal_news_v01',kind='acceptance',
        text='以下のテーマで動画を二本作成して下さい。\n公式サイトを引用するなどして、分かりやすく作って下さい。',
        interpretation='ユーザーが提示したUltraの認証条件と週上限、スマホ2アカウントの切替と分離を二本で制作する依頼。二題材の制作を採用範囲とし、助手の45秒目安、個別原稿、完成動画、公開までを承認されたとは扱わない。'),'brief')
    apply('accept',dict(proposal_id='proposal_news_v01',feedback_id='feedback_news_user_brief',confirm_acceptance=True),'accept_topics')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items']
    for item in manifest:
        if item['kind']!='official_capture':continue
        aid=Path(item['path']).stem.replace('-','_')
        data={k:v for k,v in item.items() if k not in {'original','example_is_official_not_own_device'}}
        data.update(asset_id=aid,visibility='public',blog_usage_review='passed')
        apply('asset',data,'asset_'+aid)
    for ep in plan['episodes']:
        sid='ultra_help' if ep['id']=='claude-ultra' else 'account_help'
        for i,scene in enumerate(ep['scenes']):
            sources=['account_release'] if scene['kind']=='rollout' else [sid]
            apply('claim',dict(claim_id=ep['id'].replace('-','_')+'_'+str(i),text=scene['text'],basis='official',checked_at='2026-10-31',source_ids=sources,asset_ids=[]),'claim_'+ep['id']+'_'+str(i))
        apply('storyboard',dict(episode_id=ep['id'],scenes=[dict(scene_id='scene_'+str(i),purpose=s['headline'],narration=s['text'],visual=s['kind']+' / 既存人物または自作図と公式抜粋',duration_seconds=s['seconds'],source_ids=[sid],claim_ids=[ep['id'].replace('-','_')+'_'+str(i)],asset_ids=[],character_ids=[],beat='evidence') for i,s in enumerate(ep['scenes'])]),'story_'+ep['id'])
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_'+str(i),title=ep['title'],episode_ids=[ep['id']],source_ids=['ultra_help','ultra_price'] if i==0 else ['account_help','account_release'],draft_path=(HERE/('article-'+ep['id']+'.md')).relative_to(ROOT).as_posix()) for i,ep in enumerate(plan['episodes'])]),'articles')
    result=service.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=result['project']['revision'],episodes=len(result['project']['episodes']),claims=len(result['project']['claims']),assets=len(result['project']['assets']),accepted_scope='two user-supplied topics; final media review remains pending')))

if __name__=='__main__':main()
