"""Register real provenance and actual-duration storyboards; never publish."""
import json
from pathlib import Path
from editorial_record import event,USER_RESPONSE
from workspace_record import cli
from produce import ROOT,HERE,OUT,ASSETS,save,dest

def record():
    for who,voice,clothes,role in [('male','Charon','黒いパーカー、水色のシャツ','視聴者の疑問を言う'),('female','Aoede','アイボリーのパーカー、水色のシャツ','相手へやわらかく返し、公式根拠と具体例へ案内する')]:
        event('asset','production_atlas_'+who+'_v01',dict(asset_id=who+'-atlas',kind='generated_still',path=(ASSETS/(who+'-atlas.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',character_id=who,character_version=1,provenance='既存採用済みの表情アトラスを同一hashで再利用。新しい顔の生成なし。'))
        event('character','production_character_'+who+'_v01',dict(character_id=who,fictional_adult=True,name='既存シリーズの'+('男性' if who=='male' else '女性'),persona='AIを仕事に使う架空の成人。モデルの名前だけでなく具体的なタスクと条件を確かめる。',role=role,clothing=clothes,voice='Gemini '+voice+' / conversational_v3',continuity='既存の顔、服装、声、男性左・女性右を継続。新規人物への変更なし。',reference_asset_id=who+'-atlas'))
        event('approve-character','production_reuse_'+who+'_v01',dict(character_id=who,version=1,confirm_acceptance=True,user_response='既存の男女を継続します。今回の企画への返答：'+USER_RESPONSE,scope='過去に採用済みの二人と動作を今回へ再利用。新しい顔の採用や動画完成品の採用、公開許可には広げない。'))
    for name in ['male-thinking','male-happy','male-understanding','female-thinking','female-happy','female-understanding']:
        who=name.split('-')[0]
        event('asset','production_motion_'+name+'_v01',dict(asset_id=name,kind='generated_video',path=(ASSETS/(name+'.mp4')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',character_id=who,character_version=1,provider='minimax',generation_record='outputs/content-projects/CONTENT_20261103_model_race/motion-provenance.json / source records in asset-manifest-v03.json',reuse=True))
    for kind in ['timeline','prices','rumors']:
        event('asset','production_figure_'+kind+'_v03',dict(asset_id=kind+'-figure-v03',kind='original',path=(OUT/'research-figures'/(kind+'-v03.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed'))
    claims=[
      ('fable-autonomy','Fable 5は6月9日発表。長く複雑なタスクを自律的に進めるという公式説明。','official',['fable5']),
      ('availability','Fable 5等は6月12日アクセス停止、7月1日再開。','official',['redeploy']),
      ('opus-cost','Opus 5と5.5は能力と費用の両立を提供元が説明。','official',['opus5','opus55']),
      ('fable51-date','Fable 5.1は公式ページ間の日付差から9月までを採用。厳密な先後を断定しない。','official',['fable51','fable-product','claude-news']),
      ('astra-use','GPT-6 Astraの公式用途はコンピューター操作、フォーム入力、顧客情報の更新等。独自実演ではない。','official',['astra-ja','astra-safety']),
      ('sol-price','GPT-6.1 SolはAstraに迫る性能を5分の1の標準API単価でと訴求。入力10→2、出力50→10USD/100万トークン。月額や仕事総額ではない。','official',['sol61-ja','sol61-model','api-changelog']),
      ('rumor-classification','次期モデル報道とFable 5.5の名称は別。6.1 Astraは公開見送り報道。6.2の画像は元の出所不明。一般提供・性能・日付は未確認。','hypothesis',['fable-next-report','astra61-wsj','astra62-post','astra62-clarification','astra62-provenance'])]
    for cid,value,basis,sources in claims:
        event('claim','production_claim_'+cid+'_v01',dict(claim_id=cid,text=value,basis=basis,checked_at='2026-11-03',source_ids=sources,asset_ids=[],uncertainty='報道や目撃情報の記録で、仮説を事実として採用する意味ではない。' if basis=='hypothesis' else '提供元の説明。今回は独自の同条件性能比較は未実演。'))
    motions={'opus5':'male-thinking','computer_result':'male-happy','cadence':'female-thinking','report_result':'male-understanding','closing_hope':'female-happy','audience':'male-happy','related':'female-understanding','short_closing':'female-understanding'}
    figures={}
    for kind in ['short','full']:
        plan=json.loads((dest(kind)/'timeline.json').read_text(encoding='utf-8'));scenes=[]
        for t in plan['turns']:
            v=t['visual'];question=v.endswith('question');motion=motions.get(v)
            chars=['male','female'] if question else [motion.split('-')[0]] if motion else []
            ids=[motion] if motion else ['male-atlas','female-atlas'] if question else []
            for sid in t['source_ids']:
                if sid in ['fable5','astra','fable51','opus55','sol61']:ids.append(sid)
            if not chars:
                # Register the exact rendered keyframe as the diagram/quote assignment.
                aid='frame-'+t['id'];path=dest(kind)/'layout'/(t['id']+'-0.5.jpg')
                event('asset','production_'+aid+'_'+plan['revision'],dict(asset_id=aid,kind='original',path=path.relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',context='本案件で描画した絵コンテ代表フレーム。実演を証明するキャプチャではない。'))
                ids.append(aid)
            claim_ids=[c[0] for c in claims if set(c[3])&set(t['source_ids'])]
            if v=='hero':claim_ids=['fable-autonomy','astra-use','sol-price']
            scene=dict(scene_id=t['id'],purpose=t['heading'],narration=t['display'],reading=t['reading'],visual=v,duration_seconds=t['frames']/24,start_seconds=t['start'],source_ids=t['source_ids'],asset_ids=list(dict.fromkeys(ids)),claim_ids=claim_ids,character_ids=chars,beat='problem' if question else 'insight' if 'result' in v or 'closing' in v else 'action' if v in ['audience','related','short_closing'] else 'try' if v in ['pipeline','short_timeline'] else 'evidence')
            if chars:
                scene.update(character_action='台詞の疑問・注視・納得に合う表情。' + ('既存MiniMaxの動作を一度再生して保持。' if motion else '発話者のみ音量連動の簡易口パク、聞き手は閉口。'),face_caption_separated=True,presenter_layout='fullscreen' if motion else 'pip')
                if not motion:scene['pip_policy']=dict(positions=dict(male='left',female='right'),trigger='caution' if t['chapter']=='08' else 'emphasis',avoid_gui_controls=True,caption_safe=True,speech_mode='audio_envelope',listener_mouth='closed')
            scenes.append(scene)
        if plan['end_seconds']:
            scenes.append(dict(scene_id='end-screen',purpose='関連動画とチャンネル登録のための余韻',narration='ナレーションなし。既定BGMのフェード。',visual='固定した終了画面。架空の動画リンクを焼き込まない。',duration_seconds=plan['end_seconds'],source_ids=[],asset_ids=['timeline-figure-v03'],claim_ids=[],character_ids=[],beat='transition'))
        event('storyboard','production_storyboard_'+kind+'_'+plan['revision'],dict(episode_id='model-race-'+kind,scenes=scenes))
    sections=[dict(section_id='timeline',title='モデル発表の時系列',source_ids=['fable5','redeploy','opus5','fable51','astra-safety','opus55','api-changelog'],asset_ids=['timeline-figure-v03'],claim_ids=['fable-autonomy','availability','fable51-date'],character_ids=[],episode_ids=['model-race-short','model-race-full']),dict(section_id='use-and-price',title='コンピューター操作と標準API単価',source_ids=['astra-ja','sol61-ja','sol61-model'],asset_ids=['astra','prices-figure-v03'],claim_ids=['astra-use','sol-price'],character_ids=[],episode_ids=['model-race-short','model-race-full']),dict(section_id='rumors',title='次世代モデルの報道と名称目撃',source_ids=['fable-next-report','astra61-wsj','astra62-post','astra62-clarification','astra62-provenance'],asset_ids=['rumors-figure-v03'],claim_ids=['rumor-classification'],character_ids=[],episode_ids=['model-race-short','model-race-full'])]
    event('article','production_article_v03_full_v02',dict(revision='v03',target='blog',draft_path=(HERE/'ARTICLE_DRAFT_V03_JA.md').relative_to(ROOT).as_posix(),sections=sections,published=False))
    state=cli('get',project_id=HERE.name)
    save(OUT/'work/production-workspace-current.json',state)
    print(json.dumps(dict(revision=state['project']['revision'],phase=state['project']['phase'],checks=state['checks']),ensure_ascii=False),flush=True)

if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    record()
