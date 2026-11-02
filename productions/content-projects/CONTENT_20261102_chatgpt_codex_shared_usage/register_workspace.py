"""Persist the user's scoped news request, sources, observation and one review candidate."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    db=StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False);s=ContentWorkspace(ROOT,db);pid=HERE.name
    try:s.get(pid)
    except KeyError:s.create(dict(content_project_id=pid,operation_id='op_shared_usage_create',title='ChatGPT・Codexの12月利用枠共通化',topic='公式説明の対象と予定・Instantの例外を整理する',audience='ChatGPTとCodexを利用する日本語の視聴者'))
    def apply(action,data,token):
        op='op_shared_usage_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        s.apply(pid,action,dict(operation_id=op,expected_revision=s.get(pid)['project']['revision'],data=data))
    script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));plan=json.loads((OUT/'release/v01/timeline.json').read_text(encoding='utf-8'))
    apply('research',dict(research_id='research_v01',checked_at='2026-11-02',summary='ユーザー指定の公式本文をWebとChromeで照合。12月予定、対象3プラン、Workの機能統合、トークンと作業依存、Instant例外、設定での一括確認。具体日・枠・展開と値上げは未記載。現在の既存共通枠と将来のメインChatGPT統合を区別。',sources=[dict(source_id='shared_usage',url=script['source_url'],title='Understanding ChatGPT and Codex usage limits',kind='official',checked_at='2026-11-02')]),'research')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items'];public=[]
    article=json.loads((OUT/'blog-handoff/v01/asset-manifest.json').read_text(encoding='utf-8'))['images']
    for item in manifest:
        if item['kind'] not in ['official','current_settings_observation']:continue
        path=ROOT/item['path'];im=Image.open(path);aid='asset_'+path.stem.replace('-','_');public.append(aid)
        apply('asset',dict(asset_id=aid,kind='original',path=item['path'],bytes=item['bytes'],sha256=item['sha256'],width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='公式の短い引用、または現在の設定の汎用入口の観察。架空入力実演として登録しない。',source_checked_at='2026-11-02'),'asset_'+aid)
    for item in article:
        if not item['path'].endswith('.jpg'):continue
        path=OUT/'blog-handoff/v01'/item['path'];aid='figure_'+path.stem.replace('-','_');public.append(aid)
        apply('asset',dict(asset_id=aid,kind='original',path=path.relative_to(ROOT).as_posix(),bytes=item['bytes'],sha256=item['sha256'],width=1920,height=1080,visibility='public',privacy_review='passed',blog_usage_review='passed',description='自作の模式図。利用上限や消費比率を実測した画像ではない。'),'asset_'+aid)
    apply('capture',dict(inspection_id='inspection_usage',target_feature='現在の設定→使用状況と12月予定の照合',status='available',checked_at='2026-11-02',route='ChromeのChatGPT→プロフィール→設定→使用状況',result='入口と現在の既存共通枠を観察・保存。12月の統合やInstant不消費は未実演。個人残量や請求・リセットを除いた入口のみ公開。',app='Chrome / ChatGPT Web',login_state='ログイン済み',feature_entry='設定→使用状況',display_result='現在の設定を観察。将来の適用を実証していない。',save_result='原本は_private、公開派生とhashはasset-manifest',legibility='原本2559px幅。公開切り出しは原寸を記録し、拡大を新規高解像度撮影としない。',shots=[]),'capture')
    apply('proposal',dict(proposal_id='proposal_v01',count_reason='ユーザーが具体的なニュース1件とショート制作を指定。47秒1本で仕組み・例外・確認先・未確定を整理する。',episodes=[dict(episode_id='short',title=script['title'],overview='12月予定の共通枠とInstant chatの例外',intended_message='両方を使う共通枠を理解し、対象外と未記載条件を区別する',duration_seconds=47,demo_idea='公式の短い引用・自作の動く図・現在の設定入口。変更後の消費は未実演。',article_role='確認済みの条件と提供後の検証案を補足',capture_inspection_id='inspection_usage')]),'proposal')
    apply('feedback',dict(feedback_id='feedback_user_request',proposal_id='proposal_v01',kind='acceptance',text='以下をテーマにして、ショート動画の作成をお願いします。',interpretation='ユーザー提示の11/2ニュース「ChatGPTとCodex、12月から利用枠を共通化へ」のショート1本を制作する範囲。既存男女と声・BGMを継承。完成物採用・公開や不明条件の断定ではない。'),'feedback')
    apply('accept',dict(proposal_id='proposal_v01',feedback_id='feedback_user_request',confirm_acceptance=True),'accept')
    claim_map={}
    for t in plan['turns']:
        if t['speaker']=='male':continue
        cid='claim_'+t['id'];claim_map[t['id']]=cid
        apply('claim',dict(claim_id=cid,text=t['display'],basis='official',source_ids=['shared_usage'],asset_ids=[],checked_at='2026-11-02'),'claim_'+t['id'])
    ending=OUT/'release/v01/qc-actual/end.jpg';im=Image.open(ending);end_id='asset_end';apply('asset',dict(asset_id=end_id,kind='original',path=ending.relative_to(ROOT).as_posix(),bytes=ending.stat().st_size,sha256=hashlib.sha256(ending.read_bytes()).hexdigest().upper(),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='最終MP4の終端実フレーム'),'end_asset')
    scenes=[dict(scene_id=t['id'],purpose=t['heading'],narration=t['text'],visual=t['visual']+' / 模式図・短い公式引用・現在の入口・既存男女と反応動画',duration_seconds=t['end']-t['start'],source_ids=['shared_usage'],claim_ids=[claim_map[t['id']]] if t['id'] in claim_map else [],asset_ids=public,character_ids=[],beat='evidence') for t in plan['turns']]
    scenes.append(dict(scene_id='end',purpose='最後の要点を読む余韻',narration='発話なし・BGMのみ',visual='最終画面を1秒保持',duration_seconds=1,source_ids=[],claim_ids=[],asset_ids=[end_id],character_ids=[],beat='transition'));apply('storyboard',dict(episode_id='short',scenes=scenes),'storyboard')
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='main',title='ChatGPTとCodexの利用枠共通化',episode_ids=['short'],source_ids=['shared_usage'],asset_ids=public,draft_path=(HERE/'article-draft.md').relative_to(ROOT).as_posix())]),'article')
    result=s.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(revision=result['project']['revision'],checks=result['checks']),ensure_ascii=False))
if __name__=='__main__':main()
