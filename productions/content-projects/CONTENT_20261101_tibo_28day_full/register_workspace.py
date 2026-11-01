"""Record accepted scope, claims, sources and review candidates without publication."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
def main():
    db=StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False);service=ContentWorkspace(ROOT,db);pid=HERE.name
    script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));plan=json.loads((OUT/'release/v01/timeline.json').read_text(encoding='utf-8'))
    try:service.get(pid)
    except KeyError:service.create(dict(content_project_id=pid,operation_id='op_tibo_full_create',title='Tiboの28日間チャレンジ・フル動画',topic='Codex/Workの改善とリセットを使い方の視点から振り返る',audience='ChatGPTとCodexを使う日本語の視聴者'))
    def apply(action,data,token):
        op='op_tibo_full_'+token
        with db.session() as c:
            if c.execute('SELECT 1 FROM content_project_revisions WHERE project_id=? AND operation_id=?',(pid,op)).fetchone():return
        service.apply(pid,action,dict(operation_id=op,expected_revision=service.get(pid)['project']['revision'],data=data))
    ids=dict(promise='2106845241357824205',day1='2107158998495748264',day3='2108040921044639779',day4='2108275041276420573',day5='2108645667451318747',day7='2109430343346581527',day9='2110151780478927344',day11='2110750421367287996',day12='2111244596131111253',day14='2111990254408434095',day16='2112712984644784534',day18='2113492502355562875',day19='2113770573994299544',day20='2114200291319124163',day26='2116405414921384099',day27='2116692529970311254')
    urls={k:'https://x.com/thsottiaux/status/'+v for k,v in ids.items()}
    urls.update(resets='https://help.openai.com/en/articles/20001498-how-resets-work-in-codex',pro='https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers',release='https://help.openai.com/en/articles/6825453-chatgpt-release-notes')
    apply('research',dict(research_id='research_full_v01',checked_at='2026-11-01',summary='ショートの根拠を継承し公式Helpを再照合。Day27 Banked 1/2を本人の画面で確認・撮影。Day28は未発表。予告と個別反映を区別する。',sources=[dict(source_id=k,url=u,title=k,kind='official',checked_at='2026-11-01') for k,u in urls.items()]),'research')
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items']
    for name in ['usage-navigation','usage-reset-description-current']:
        item=next(x for x in manifest if Path(x['path']).stem==name);aid=name.replace('-','_')
        from PIL import Image
        im=Image.open(ROOT/item['path'])
        apply('asset',dict(asset_id=aid,kind='demonstration_capture',path=item['path'],bytes=item['bytes'],sha256=item['sha256'],width=im.width,height=im.height,visibility='public',privacy_review='passed',blog_usage_review='passed',fictional_materials_only=True,source_checked_at='2026-11-01'),'asset_'+aid)
    apply('capture',dict(inspection_id='inspection_full_usage',target_feature='ChatGPT Webの設定・使用状況・リセット欄',status='captured',checked_at='2026-11-01',route='ChromeのCodex→プロフィール→設定→使用状況。直接の旧URLはホームへ転送されたため画面から辿る。',result='リセット欄と履歴入口を確認・撮影。汎用説明だけ公開し、個人の残量・保有数・期限を除外。使用・購入・設定変更はなし。顧客などの実業務データは扱わない。',app='Chrome / ChatGPT Web',login_state='ログイン済み',feature_entry='プロフィール→設定→使用状況',display_result='利用上限のリセット欄を観察',save_result='原本_private/captures、短い公開用assets',legibility='通常のブラウザ幅約1240px。原寸1400pxと称して拡大していない。自作図は1920px。',shots=[dict(shot_id='usage_description',purpose='場所と汎用説明。個別受領の実証ではない。',asset_id='usage_reset_description_current')]),'capture')
    apply('proposal',dict(proposal_id='proposal_full_v01',count_reason='ユーザーが既存ショートのフル版1本を指定。新規の横長掛け合いを9章で作り、条件・比較・確認方法を詳しく説明する。',episodes=[dict(episode_id='tibo-full',title=script['title'],overview='速さ、続けやすさ、利用枠を日別の発表から理解する',intended_message='リセット2種類、枠拡大の対象条件、確認画面を区別して使う。ここまでの継続を称賛。',duration_seconds=round(plan['seconds']),demo_idea='公式抜粋・実画面の汎用切り出し・CPU図解・既存MiniMax人物。新規H3は失敗を保存し不採用。',article_role='日別の原投稿と対象条件を詳述し、図と撮影素材を共用する',capture_inspection_id='inspection_full_usage')]),'proposal')
    apply('feedback',dict(feedback_id='feedback_full_request',proposal_id='proposal_full_v01',kind='acceptance',text='これのフル動画版も作成してください。必要に応じてローカルで動画生成しつつ、ナレーションも尺に合わせて作り直してください。',interpretation='既存Tiboショートのフル動画1本の制作と新規音声を採用範囲とする。既存男女、中央揃え、明るいループ、3種SE、称賛の締めを継承。完成物の採用や公開、mainマージとは別。'),'feedback')
    apply('accept',dict(proposal_id='proposal_full_v01',feedback_id='feedback_full_request',confirm_acceptance=True),'accept')
    source_map={'01':['promise','resets'],'02':['promise','day27','day26'],'03':['resets'],'04':['day1','day4','day5','day7'],'05':['day9','day11','day12','day14','day16'],'06':['day19','pro','release'],'07':['day3','day18','day20','day26','day27'],'08':['resets'],'09':['promise']}
    for t in plan['turns']:
        if t['speaker']=='male' or t['chapter']=='09':continue
        apply('claim',dict(claim_id='claim_'+t['id'].replace('-','_'),text=t['text'],basis='official',source_ids=source_map[t['chapter']],asset_ids=[],checked_at='2026-11-01'),'claim_'+t['id'])
    for t in plan['turns']:
        path=OUT/'release/v01/shots'/(t['id']+'.mp4');proof=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        apply('asset',dict(asset_id='cut_'+t['id'].replace('-','_'),kind='original',path=proof['path'],bytes=proof['bytes'],sha256=proof['sha256'],width=1920,height=1080,visibility='public',privacy_review='passed',blog_usage_review='passed',description='CPUで描画した編集済みカット。新規AI人物動画という登録ではない。'),'cut_'+t['id'])
    apply('storyboard',dict(episode_id='tibo-full',scenes=[dict(scene_id='scene_'+t['id'].replace('-','_'),purpose=t['caption'],narration=t['text'],visual=t['visual']+' / 横長図解・引用・左右人物・PCM口パク・明るい音楽と3種SE',duration_seconds=t['end']-t['start'],source_ids=source_map[t['chapter']],claim_ids=[] if t['speaker']=='male' or t['chapter']=='09' else ['claim_'+t['id'].replace('-','_')],asset_ids=['cut_'+t['id'].replace('-','_')],character_ids=[],beat='evidence') for t in plan['turns']]),'storyboard_rendered_v01')
    apply('article',dict(status='draft',published=False,sections=[dict(section_id='article_full',title='Tiboの28日間チャレンジで何が変わった？',episode_ids=['tibo-full'],source_ids=list(urls),draft_path=(HERE/'article-draft.md').relative_to(ROOT).as_posix())]),'article_rendered_v01')
    current=service.get(pid);(OUT/'content-workspace-current.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=current['project']['revision'],episodes=len(current['project']['episodes']),claims=len(current['project']['claims']),final_approval=False)))
if __name__=='__main__':main()
