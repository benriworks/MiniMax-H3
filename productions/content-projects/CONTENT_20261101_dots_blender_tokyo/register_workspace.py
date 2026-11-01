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
    except KeyError:s.create(dict(content_project_id=pid,operation_id='op_blender_tokyo_create',title='dotsによるBlender操作：東京駅の模型',topic='既存の制作記録からショートとフルを作る',audience='AIでアプリを使った制作を始めたい日本語の視聴者'))
    def apply(action,data,token):
        op='op_blender_tokyo_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        s.apply(pid,action,dict(operation_id=op,expected_revision=s.get(pid)['project']['revision'],data=data))
    script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));plans={k:json.loads((OUT/'release/v01'/k/'timeline.json').read_text(encoding='utf-8')) for k in ['short','full']}
    apply('research',dict(research_id='research_blender_v01',checked_at='2026-11-01',summary='ユーザー提供の38ファイルを検査。Blender Pythonでの段階制作、側面の窓とレンガ投影の修正をコードとログで確認。連続操作や依頼原文の記録ではない。公式はクラウドPCと追加指示の前提の根拠。',sources=[dict(source_id='dots_computer',url='https://learn.chatgpt.com/docs/dots/computers-and-apps',title='Computers and apps',kind='official',checked_at='2026-11-01'),dict(source_id='dots_controls',url='https://learn.chatgpt.com/docs/dots/controls',title='Controls',kind='official',checked_at='2026-11-01')]),'research')
    apply('capture',dict(inspection_id='inspection_cloud_blender',target_feature='東京駅模型の制作環境と追加撮影',status='blocked',checked_at='2026-11-01',route='PCのウィンドウ一覧とBlender MCPの読取。接続先の場面と版を照合。',result='当該クラウド制作画面は開いていない。ローカルはBlender5.1.2の別の未保存シーン。現在の作業を変更せず、提供済み工程キャプチャとCGを使用。',app='Blender MCP / Windows / cloud material',login_state='クラウド制作画面への現在の接続は未確認',feature_entry='既存クラウド制作の追加撮影経路は未取得',display_result='現在のPC側はCubeを含む3オブジェクトの別シーン',save_result='提供原本を保持して公開用切り出しを別保存',legibility='元1366px幅の実画面。高解像度の新規撮影と称さない',shots=[]),'capture')
    apply('proposal',dict(proposal_id='proposal_blender_v01',count_reason='ユーザーが既存素材からショートとフルの2本の制作を明示指定。完成像と制作・確認・修正を用途別の尺で見せる。',episodes=[dict(episode_id=k,title=script[k+'_title'],overview='東京駅の簡略模型をdotsとBlenderで制作する例',intended_message='画像だけではなくアプリと保存モデルで制作し、人が確認・修正を重ねる',duration_seconds=round(plans[k]['seconds']),demo_idea='提供された実画面の静止画と完成CGを再編集。実際の依頼原文の代わりは依頼例と表示',article_role='方法・証拠の範囲・修正記録とモデルの用途を詳述',capture_inspection_id='inspection_cloud_blender') for k in ['short','full']]),'proposal')
    apply('feedback',dict(feedback_id='feedback_blender_request',proposal_id='proposal_blender_v01',kind='acceptance',text='つぎは 、dotsによるBlender自動操作のショートとフルを作りたい。この中に動画素材はできているので、これを上手く使って、ナレーションやテロップ、BGMをつけて整えてほしい。',interpretation='既存素材を使うショートとフルの制作を採用範囲とする。任意の重点質問に返答がないことを追加の採用と扱わない。完成品の採用・公開は別。'),'feedback')
    apply('accept',dict(proposal_id='proposal_blender_v01',feedback_id='feedback_blender_request',confirm_acceptance=True),'accept')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items'];aids=[]
    for item in manifest:
        if item.get('kind') not in ['actual_checkpoint','model_render','official_excerpt']:continue
        path=ROOT/item['path'];aid='asset_'+path.stem.replace('-','_');im=Image.open(path);aids.append(aid)
        apply('asset',dict(asset_id=aid,kind='original',path=item['path'],bytes=item['bytes'],sha256=item['sha256'],width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='提供素材の観察・公開用切り出し、または短い公式引用。新たな架空入力の実演として登録しない。',source_checked_at='2026-11-01'),'asset_'+aid)
    apply('claim',dict(claim_id='claim_cloud_pc',text='dotsはクラウドのコンピューターとブラウザーを使える。すべてのアカウントでBlenderの同一環境が保証されるとは言わない。',basis='official',source_ids=['dots_computer'],asset_ids=['asset_official_dots_heading'],checked_at='2026-11-01'),'claim')
    for kind,plan in plans.items():
        ending=OUT/'release/v01'/kind/'qc-actual/end.jpg';im=Image.open(ending);end_id='asset_ending_'+kind
        apply('asset',dict(asset_id=end_id,kind='original',path=ending.relative_to(ROOT).as_posix(),bytes=ending.stat().st_size,sha256=hashlib.sha256(ending.read_bytes()).hexdigest().upper(),width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',description='最終MP4から取り出した終了画面の実フレーム'),'ending_'+kind)
        scenes=[dict(scene_id=t['id'],purpose=t['heading'],narration=t['text'],visual=t['visual']+' / 実画面静止画・完成CG・既存男女・PCM口パク・明るい音楽',duration_seconds=t['end']-t['start'],source_ids=['dots_computer'] if t['visual']=='cloud' else [],claim_ids=['claim_cloud_pc'] if t['visual']=='cloud' else [],asset_ids=aids,character_ids=[],beat='evidence') for t in plan['turns']]
        scenes.append(dict(scene_id=kind+'_end',purpose='終了後の余韻と関連動画への導線',narration='発話なし。BGMのみ。',visual='10秒の終了画面' if kind=='full' else '1.4秒の最終画面保持',duration_seconds=plan['end_seconds'],source_ids=[],claim_ids=[],asset_ids=[end_id],character_ids=[],beat='transition'))
        apply('storyboard',dict(episode_id=kind,scenes=scenes),'storyboard_ending_asset_'+kind)
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_main',title='dotsとBlenderで東京駅の簡略模型を制作・修正',episode_ids=['short','full'],source_ids=['dots_computer','dots_controls'],asset_ids=aids,draft_path=(HERE/'article-draft.md').relative_to(ROOT).as_posix())]),'article')
    current=s.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(revision=current['project']['revision'],checks=current['checks']),ensure_ascii=False))
if __name__=='__main__':main()
