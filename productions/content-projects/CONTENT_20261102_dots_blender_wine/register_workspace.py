"""Record the explicitly requested two cuts, observed source material and draft article."""
from pathlib import Path
import hashlib,json,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    db=StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False);s=ContentWorkspace(ROOT,db);pid=HERE.name
    try:s.get(pid)
    except KeyError:s.create(dict(content_project_id=pid,operation_id='op_blender_wine_create',title='dotsによるBlender操作：ワインCG',topic='既存の制作記録からショートとフルを作る',audience='AIでアプリを使った制作を始めたい日本語の視聴者'))
    def apply(action,data,token):
        op='op_blender_wine_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        s.apply(pid,action,dict(operation_id=op,expected_revision=s.get(pid)['project']['revision'],data=data))
    script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));plans={k:json.loads((OUT/'release/v01'/k/'timeline.json').read_text(encoding='utf-8')) for k in ['short','full']}
    apply('research',dict(research_id='research_blender_v01',checked_at='2026-11-02',summary='Driveの該当フォルダーとREADMEを照合し12ファイルとZIP展開64ファイルを検査。Blender PythonによるワインCG、注ぎ終わりと瓶の比率の修正を確認。工程は静止画、液体は手続き型表現。',sources=[dict(source_id='dots_computer',url='https://learn.chatgpt.com/docs/dots/computers-and-apps',title='Computers and apps',kind='official',checked_at='2026-11-02'),dict(source_id='bottle_dimensions',url='https://www.saverglass.com/en/our-products/catalog-still-wine/ancienne-75-cl-plate-unique',title='Reference bottle dimensions',kind='official',checked_at='2026-11-02'),dict(source_id='glass_dimensions',url='https://www.zwiesel-glas.com/en/shop/wine-glasses/red-wine-glasses/burgundy-red-wine-goblet-classico',title='Reference glass dimensions',kind='official',checked_at='2026-11-02')]),'research')
    apply('capture',dict(inspection_id='inspection_cloud_blender',target_feature='ワインCGの制作環境と追加撮影',status='blocked',checked_at='2026-11-02',route='Blender MCPで読取のみの接続・版確認。',result='ローカルはBlender5.1.2の別の未保存シーン。提供素材の4.3.2クラウド制作環境と異なり、現在の作業を変更せず工程キャプチャとCGを使用。',app='Blender MCP / cloud material',login_state='クラウド制作画面への現在の接続は未確認',feature_entry='既存クラウド制作の追加撮影経路は未取得',display_result='現在のPC側はCubeを含む3オブジェクトの別シーン',save_result='提供原本を保持して公開用切り出しを別保存',legibility='元1366px幅の実画面。高解像度の新規撮影と称さない',shots=[]),'capture')
    apply('proposal',dict(proposal_id='proposal_blender_v01',count_reason='ユーザーがショートとフルの2本を明示指定。完成と2段階の修正を用途別の尺で見せる。',episodes=[dict(episode_id=k,title=script[k+'_title'],overview='ワインCGをdotsとBlenderで制作する例',intended_message='完成物を見て動きと比率を修正する',duration_seconds=round(plans[k]['seconds']),demo_idea='提供された実画面静止画と初版・v2・v3のCGを比較',article_role='方法・証拠の範囲・修正記録とモデルの用途を詳述',capture_inspection_id='inspection_cloud_blender') for k in ['short','full']]),'proposal')
    apply('feedback',dict(feedback_id='feedback_blender_request',proposal_id='proposal_blender_v01',kind='acceptance',text='ここにdotsによるワインのモデリング動画を作るための素材を格納しました。これをもとに、YouTubeショート、フル動画の作成をお願いします。ナレーションをつけて下さい。',interpretation='既存素材を使う2本の制作が依頼範囲。完成品の採用・公開は別。'),'feedback')
    apply('accept',dict(proposal_id='proposal_blender_v01',feedback_id='feedback_blender_request',confirm_acceptance=True),'accept')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items'];aids=[]
    for item in manifest:
        if item.get('kind') not in ['provided_checkpoint','provided_CG','official_excerpt']:continue
        path=ROOT/item['path'];aid='asset_'+path.stem.replace('-','_');im=Image.open(path);aids.append(aid)
        apply('asset',dict(asset_id=aid,kind='original',path=item['path'],bytes=item['bytes'],sha256=item['sha256'],width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='提供素材の観察・公開用切り出し、または短い公式引用。新たな架空入力の実演として登録しない。',source_checked_at='2026-11-02'),'asset_'+aid)
    apply('claim',dict(claim_id='claim_cloud_pc',text='dotsはクラウドのコンピューターとブラウザーを使える。すべてのアカウントでBlenderの同一環境が保証されるとは言わない。',basis='official',source_ids=['dots_computer'],asset_ids=['asset_official_dots_heading'],checked_at='2026-11-02'),'claim')
    for kind,plan in plans.items():
        ending=OUT/'release/v01'/kind/'qc-actual/end.jpg';im=Image.open(ending);end_id='asset_ending_'+kind
        apply('asset',dict(asset_id=end_id,kind='original',path=ending.relative_to(ROOT).as_posix(),bytes=ending.stat().st_size,sha256=hashlib.sha256(ending.read_bytes()).hexdigest().upper(),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='最終MP4から取り出した終了画面の実フレーム'),'ending_'+kind)
        scenes=[dict(scene_id=t['id'],purpose=t['heading'],narration=t['text'],visual=t['visual']+' / 実画面静止画・完成CG・既存男女・PCM口パク・明るい音楽',duration_seconds=t['end']-t['start'],source_ids=['dots_computer'] if t['visual']=='cloud' else [],claim_ids=['claim_cloud_pc'] if t['visual']=='cloud' else [],asset_ids=aids,character_ids=[],beat='evidence') for t in plan['turns']]
        scenes.append(dict(scene_id=kind+'_end',purpose='終了後の余韻と関連動画への導線',narration='発話なし。BGMのみ。',visual='10秒の終了画面' if kind=='full' else '1秒の最終画面保持',duration_seconds=plan['end_seconds'],source_ids=[],claim_ids=[],asset_ids=[end_id],character_ids=[],beat='transition'))
        apply('storyboard',dict(episode_id=kind,scenes=scenes),'storyboard_ending_asset_'+kind)
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_main',title='dotsとBlenderでワインCGを制作・修正',episode_ids=['short','full'],source_ids=['dots_computer','bottle_dimensions','glass_dimensions'],asset_ids=aids,draft_path=(HERE/'article-draft.md').relative_to(ROOT).as_posix())]),'article')
    current=s.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(revision=current['project']['revision'],checks=current['checks']),ensure_ascii=False))
if __name__=='__main__':main()
