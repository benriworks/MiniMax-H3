"""Record actual human direction; keep technical proof and final adoption separate."""
from pathlib import Path
from copy import deepcopy
import json,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v03';ID='CONTENT_20261026_dots_transfer_detail'
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
REQUEST='ナレーションを再構築してほしい。やりたいことを男の子が女の子に聞いて、女の子が答えたり、女の子が喋りながら進めていく、というイメージ。\nあと、音楽が暗いので明るくして。'


def main():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def project():return service.get(ID)['project']
    def apply(action,data,op):
        body=dict(operation_id=op,expected_revision=project()['revision'],data=data)
        folder=OUT/'workspace-inputs';folder.mkdir(exist_ok=True)
        (folder/(op+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
        return service.apply(ID,action,body)
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'));config=json.loads((OUT/'render-config.json').read_text(encoding='utf-8'))
    proposal='transfer_detail_conversation_v03';feedback='transfer_detail_conversation_user_v03'
    if not any(x['proposal_id']==proposal for x in project()['proposals']):
        entry=deepcopy(project()['episodes'][0]);entry['duration_seconds']=plan['seconds']
        apply('proposal',dict(proposal_id=proposal,count_reason='詳細1本を継続し、本人が指定した質問・返答・女性の実演案内と明るいBGMへ改訂。新しい製品事実や人物を追加しない。',
            episodes=[entry],production_version='v03',user_directed_scope='制作方向の採用。逐語原稿・音声・完成物採用と公開は別確認。'),'transfer_v03_proposal')
    if not any(x['feedback_id']==feedback for x in project()['feedback']):
        apply('feedback',dict(feedback_id=feedback,proposal_id=proposal,kind='acceptance',text=REQUEST,
            interpretation='本人の実際の依頼に従って44台詞を再構築しBGMを明るくする。新台詞の逐語承認・完成動画の採用・公開を推定しない。'),'transfer_v03_direction')
    if project()['accepted_proposal']['proposal_id']!=proposal:
        apply('accept',dict(proposal_id=proposal,feedback_id=feedback,confirm_acceptance=True),'transfer_v03_scope_accept')
    scenes=[];chars=['dots_pilot_male','dots_pilot_female'];arrival=['v02_male_arrival','v02_female_arrival']
    for sid,duration,narration,assets,beat in [
        ('v03_arrival',plan['arrival_seconds'],'（右から走り込み、隣で止まる）',arrival,'transition'),
        ('v03_opening',plan['conversation_seconds'],' '.join(t['text'] for t in plan['chapters'][0]['turns']),['v02_pair_dialogue',*arrival],'problem')]:
        scenes.append(dict(scene_id=sid,purpose='目的を聞き、本人役がやりたい作業を答える',narration=narration,duration_seconds=duration,
            visual='同じ2人。採用済みMiniMax走り込みから、女が進行する中景の会話へ。',beat=beat,character_ids=chars,asset_ids=assets,
            source_ids=[],claim_ids=[],character_action='男がやりたいことを尋ね、女がExcelの三件をシステムへ移す目的を答える。',
            presenter_layout='fullscreen',face_caption_separated=True))
    offset=plan['main_offset'];cuts=json.loads((OUT/'cut-map.json').read_text(encoding='utf-8'));windows=config['windows_in_main_seconds']
    points=sorted(set([0,round((plan['seconds']-offset)*24)/24,*[v for c in cuts for v in (c['start'],c['end'])],*[v for w in windows for v in (w['start'],w['end'])]]))
    for i,(a,b) in enumerate(zip(points,points[1:])):
        c=next(c for c in plan['chapters'][1:] if c['start']-offset-1e-6<=a<c['end']-offset-1e-6)
        w=next((w for w in windows if w['start']<=a<w['end']),None)
        narration=' '.join(t['text'] for t in c['turns'] if max(t['start'],offset+a)<min(t['end'],offset+b)) or '（作業画面を確認する間）'
        scene=dict(scene_id=f'v03_main_{i:02d}',purpose=c['title'],duration_seconds=b-a,narration=narration,
            narration_timing_ref='v03/timeline.json',visual='同じ原録画を通常速度で使用。静止説明と図の尺を会話へ合わせる。',
            beat='action' if c['id']=='chapter-11' else 'insight' if c['id'] in ['chapter-09','chapter-10'] else 'try',
            asset_ids=['transfer_source_table','transfer_saved_list'],character_ids=[],source_ids=['computers'],claim_ids=[])
        if w:
            scene.update(visual='左右の人物・中央の要点・下部字幕を分離。実操作中に重ねない。',character_ids=chars,
                character_action='男の疑問に女が答え、女が作業を案内する。話者だけ口を開閉、聞き手は閉口。',presenter_layout='pip',face_caption_separated=True,
                pip_policy=dict(trigger='before_demonstration' if w['kind']=='before' else w['kind'],positions={'dots_pilot_male':'left','dots_pilot_female':'right'},
                    avoid_gui_controls=True,caption_safe=True,speech_mode='audio_envelope',listener_mouth='closed'))
            scene['asset_ids']+=['v02_male_atlas','v02_female_atlas']
        scenes.append(scene)
    if not any(s['scene_id']=='v03_opening' for s in project()['episodes'][0]['storyboard']):
        apply('storyboard',dict(episode_id='transfer_detail_01',scenes=scenes),'transfer_v03_storyboard')
    article=deepcopy(project()['article']);article['draft_path']=(HERE/'article-draft-v03.md').relative_to(ROOT).as_posix()
    if project()['article'].get('draft_path')!=article['draft_path']:apply('article',article,'transfer_v03_article')
    state=service.get(ID);(OUT/'workspace-state-v03.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ContentWorkspace',state['project']['revision'],state['checks'],flush=True)


if __name__=='__main__':main()
