"""Save the human-directed presentation revision without claiming final adoption."""
from pathlib import Path
from copy import deepcopy
import json,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v02';ID='CONTENT_20261026_dots_transfer_detail'
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase

REQUEST='まぁ、よいかな。そのまま2人で会話をしながら、自然に本編へ入ります。\n本編では、ピクチャーインピクチャーで、左の方に男の子、右の方に女の子を映します。出し方何らかのルールに基づいて出しましょう。実演の始まる前や、強調したいシーン、最後の締めなど。\nピクチャーインピクチャー内でも口の動きや、喜怒哀楽などを感情表現を出してほしい。'


def main():
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def p():return service.get(ID)['project']
    def apply(action,data,op):
        body=dict(operation_id=op,expected_revision=p()['revision'],data=data)
        target=OUT/'workspace-inputs';target.mkdir(exist_ok=True)
        (target/(op+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
        return service.apply(ID,action,body)
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    config=json.loads((HERE/'revision-v02.json').read_text(encoding='utf-8'))
    proposal='transfer_detail_presentation_v02'
    if not any(x['proposal_id']==proposal for x in p()['proposals']):
        entry=deepcopy(p()['episodes'][0]);entry['duration_seconds']=plan['seconds']
        apply('proposal',dict(proposal_id=proposal,count_reason='既存の詳細1本を継続。人の明示した導入の会話・左右PIP・表情の改訂だけを対象にし、実演と事実を保持。',
            episodes=[entry],production_version='v02',user_directed_scope='新しい台詞の逐語採用・完成物採用・公開とは区別する。'),'transfer_v02_proposal')
    feedback='transfer_detail_presentation_user_v02'
    if not any(x['feedback_id']==feedback for x in p()['feedback']):
        apply('feedback',dict(feedback_id=feedback,proposal_id=proposal,kind='acceptance',text=REQUEST,
            interpretation='本人の実指示に基づき待ち合わせカットを冒頭に採用し、会話とルール付きPIPの制作を行う範囲。新しい台詞の逐語採用、Charonの声の採用、完成動画と記事の公開は未確認。'),'transfer_v02_user_direction')
    if p()['accepted_proposal']['proposal_id']!=proposal:
        apply('accept',dict(proposal_id=proposal,feedback_id=feedback,confirm_acceptance=True),'transfer_v02_scope_accept')
    def asset(aid,kind,path,**extra):
        if any(x['asset_id']==aid for x in p()['assets']):return
        apply('asset',dict(asset_id=aid,kind=kind,path=str(path.relative_to(ROOT)),visibility='private',privacy_review='passed',**extra),'transfer_v02_asset_'+aid)
    for speaker in ('male','female'):
        asset('v02_'+speaker+'_atlas','generated_still',OUT/'avatars'/f'{speaker}-atlas.png',
            character_id='dots_pilot_'+speaker,character_version=1,provider='imagegen',caption='同じ成人の5表情と開閉口。音声連動の簡易アニメーション用。')
        asset('v02_'+speaker+'_arrival','generated_video',ROOT/config['opening_clip'],character_id='dots_pilot_'+speaker,
            character_version=1,provider='minimax',generation_record='outputs/characters/dots-duo-opening-20261026/v01/entrance/verification.json',
            caption='同一の2人同時の待ち合わせ映像。顔・衣装・構図の継続参照にも使用。')
    asset('v02_pair_dialogue','generated_still',OUT/'avatars/intro-atlas.png',provider='imagegen',caption='待ち合わせ後の同じ2人の中景。開閉口の3状態。')
    scenes=[]
    chars=['dots_pilot_male','dots_pilot_female'];arrival=['v02_male_arrival','v02_female_arrival']
    for sid,duration,narration,assets,beat in [
        ('v02_arrival',plan['arrival_seconds'],'（台詞なし。右から走り込み、隣で止まる）',arrival,'transition'),
        ('v02_opening',plan['conversation_seconds'],' '.join(t['text'] for t in plan['chapters'][0]['turns']),['v02_pair_dialogue',*arrival],'problem')]:
        scenes.append(dict(scene_id=sid,purpose='待ち合わせから実務の困りごとへ',narration=narration,duration_seconds=duration,
            visual='採用したMiniMaxの待ち合わせから中景の会話へ。中景の口は音声連動の簡易方式。',beat=beat,
            character_ids=chars,asset_ids=assets,source_ids=[],claim_ids=[],character_action='男が質問し、女が二重入力の困りごとを話し、男がdotsの活用を提案。',
            presenter_layout='fullscreen',face_caption_separated=True))
    windows=config['windows_in_original_main_seconds'];offset=plan['main_offset']
    points=sorted(set([0,280,*[c['start']-offset for c in plan['chapters'][1:]],*[v for w in windows for v in (w['start'],w['end'])]]))
    for i,(a,b) in enumerate(zip(points,points[1:])):
        c=next(c for c in plan['chapters'][1:] if c['start']-offset<=a+.001<c['end']-offset)
        w=next((w for w in windows if w['start']<=a<w['end']),None)
        narration=' '.join(t['text'] for t in c['turns'] if max(t['start'],offset+a)<min(t['end'],offset+b)) or '（発話の間。内容を画面で確認）'
        scene=dict(scene_id=f'v02_main_{i:02d}',purpose=c['title'],duration_seconds=b-a,narration=narration,
            narration_timing_ref='v02/timeline.json',visual='実録画と編集図を継続。入力・確認・クリック・詳細表の間はPIPを出さない。',
            beat='action' if c['id']=='chapter-11' else 'insight' if c['id'] in ('chapter-09','chapter-10') else 'try',
            asset_ids=['transfer_source_table','transfer_saved_list'],character_ids=[],source_ids=['computers'],claim_ids=[])
        if w:
            scene.update(visual='要点専用画面。中央の情報、左右の顔、下部の字幕を分離。',character_ids=chars,
                character_action='話者だけ口を開閉。聞き手は口を閉じ、疑問・困り・集中・安心などの表情で反応。',
                presenter_layout='pip',face_caption_separated=True,
                pip_policy=dict(trigger='before_demonstration' if w['kind']=='before' else w['kind'],
                    positions={'dots_pilot_male':'left','dots_pilot_female':'right'},avoid_gui_controls=True,caption_safe=True,
                    speech_mode='audio_envelope',listener_mouth='closed'))
            scene['asset_ids']+=['v02_male_atlas','v02_female_atlas']
        scenes.append(scene)
    if not any(s['scene_id']=='v02_opening' for s in p()['episodes'][0]['storyboard']):
        apply('storyboard',dict(episode_id='transfer_detail_01',scenes=scenes),'transfer_v02_storyboard')
    article=deepcopy(p()['article']);article['draft_path']=(HERE/'article-draft-v02.md').relative_to(ROOT).as_posix()
    if p()['article'].get('draft_path')!=article['draft_path']:
        apply('article',article,'transfer_v02_article')
    state=service.get(ID)
    (OUT/'workspace-state-v02.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ContentWorkspace',state['project']['revision'],state['checks'],flush=True)


if __name__=='__main__':main()
