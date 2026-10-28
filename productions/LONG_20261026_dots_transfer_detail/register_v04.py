"""Record the three human-requested visual changes without adopting the new final."""
from pathlib import Path
from copy import deepcopy
import json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v04';ID='CONTENT_20261026_dots_transfer_detail'
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
REQUEST='直したい2点\n1．2:07付近：120,000円の先頭「1」にカーソルが重なっています。金額の誤りではありませんが、ここは確認の見せ場。数字が隠れていない実フレームに替えるか、カーソルを余白へ移した確認画面を撮るとよいです。数字自体を画像編集で書き直す必要はありません。\n2．0:44付近：右の説明が「専用ビューアで表／示」と折り返されています。「実物のXLSX」「専用ビューアで表示」「Excel本体ではない」のように意味ごとに改行すると整います。\n3.冒頭0〜5秒の待ち合わせ場面に「Excelの3件を案件管理へ」と短い見出しを出すと、初見でも題材が分かるようにしたい。'


def main():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def project():return service.get(ID)['project']
    def apply(action,data,op):
        body=dict(operation_id=op,expected_revision=project()['revision'],data=data)
        folder=OUT/'workspace-inputs';folder.mkdir(exist_ok=True)
        (folder/(op+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
        return service.apply(ID,action,body)
    pid='transfer_detail_visual_v04';fid='transfer_detail_visual_user_v04'
    if not any(x['proposal_id']==pid for x in project()['proposals']):
        apply('proposal',dict(proposal_id=pid,count_reason='採用済みの詳細1本を維持。指定3か所の視覚修正だけを対象にし、声・BGM・尺・実証結果を変えない。',
            episodes=deepcopy(project()['episodes']),production_version='v04',user_directed_scope='今回の修正制作の採用範囲。完成v04の最終採用や公開は別確認。'),'transfer_v04_proposal')
    if not any(x['feedback_id']==fid for x in project()['feedback']):
        apply('feedback',dict(feedback_id=fid,proposal_id=pid,kind='acceptance',text=REQUEST,
            interpretation='本人の指定した3か所を直す制作指示。読める実フレームの選択・意味ごとの改行・冒頭の見出し。完成v04の最終採用、記事採用、公開の承認ではない。'),'transfer_v04_direction')
    if project()['accepted_proposal']['proposal_id']!=pid:
        apply('accept',dict(proposal_id=pid,feedback_id=fid,confirm_acceptance=True),'transfer_v04_scope_accept')
    aid='v04_entry_complete_actual_frame'
    if not any(x['asset_id']==aid for x in project()['assets']):
        apply('asset',dict(asset_id=aid,kind='demonstration_capture',path=(OUT/'captures/original/entry-complete-15.1.png').relative_to(ROOT).as_posix(),
            visibility='private',privacy_review='passed',fictional_materials_only=True,caption='既存の実録15.1秒から入力完了のフレームを抽出。数字を修正せず、金額120000が読める。確認画面ではなく登録前の入力画面。',
            source_record='outputs/productions/LONG_20261026_dots_transfer_detail/v04/visual-revision.json'),'transfer_v04_actual_frame')
    scenes=deepcopy(project()['episodes'][0]['storyboard']);cursor=0
    for scene in scenes:
        start=cursor;cursor+=scene['duration_seconds']
        scene['scene_id']=scene['scene_id'].replace('v03_','v04_',1)
        if start<5:scene['visual']+=' 冒頭0〜5秒は顔・手を避けた左上に「Excelの3件を／案件管理へ」。'
        if max(start,32.1666667)<min(cursor,50.1666667)-1e-5:scene['visual']+=' 右の編集説明は実物のXLSX／専用ビューアで表示／Excel本体ではないの3行。'
        if max(start,127.125)<min(cursor,131.125)-1e-5:
            scene.update(visual='同じ実録の入力完了フレームを静止して5項目を確認。数字の書き直しなし。入力完了時の実画面と明示し、確認画面とは呼び替えない。')
            scene['asset_ids']=list(dict.fromkeys([*scene['asset_ids'],aid]))
    if not any(x['scene_id']=='v04_opening' for x in project()['episodes'][0]['storyboard']):
        apply('storyboard',dict(episode_id='transfer_detail_01',scenes=scenes),'transfer_v04_storyboard')
    article=deepcopy(project()['article']);article['draft_path']=(HERE/'article-draft-v04.md').relative_to(ROOT).as_posix()
    for section in article.get('sections',[]):
        section['asset_ids']=[aid if x in ['transfer_entry','transfer_confirmation'] else x for x in section.get('asset_ids',[])]
        section['asset_ids']=list(dict.fromkeys(section['asset_ids']))
    if project()['article'].get('draft_path')!=article['draft_path']:apply('article',article,'transfer_v04_article')
    original=OUT/'cut-map.json';baseline=OUT/'baseline-cut-map-v03.json'
    if not baseline.exists():shutil.copy2(original,baseline)
    cuts=json.loads(baseline.read_text(encoding='utf-8'))
    for cut in cuts:
        if cut['kind']=='confirmation-native':
            cut.update(kind='entry-complete-review-still',source='outputs/productions/LONG_20261026_dots_transfer_detail/v04/captures/original/entry-complete-15.1.png',
                source_seconds=15.1,real_recording=False,origin='still_from_existing_real_recording')
            cut['original']=dict(path=cut['source'],note='未登録の入力内容。入力完了時の実画面を静止して確認。',origin='still_from_existing_real_recording')
    original.write_text(json.dumps(cuts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    state=service.get(ID);(OUT/'workspace-state-v04.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT.parent/'latest-review.json').write_text(json.dumps(dict(version='v04',video=(OUT/'dots-transfer-detail-v04.mp4').relative_to(ROOT).as_posix(),
        user_adopted_version='v03',v04_user_final_adoption=False,published=False),indent=2),encoding='utf-8')
    print('Recorded visual v04; ContentWorkspace revision',state['project']['revision'],state['checks'],flush=True)


if __name__=='__main__':main()
