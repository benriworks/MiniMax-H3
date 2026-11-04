"""Store accepted reuse, actual timing and article dependencies without publishing."""
from pathlib import Path
import json,sys
from workspace_record import cli,event,save,OUT,HERE
ROOT=HERE.resolve().parents[2];ASSETS=OUT/'assets';DEST=OUT/'release/v01/short'

def record():
    response=json.loads((HERE/'adoption-v01.json').read_text(encoding='utf-8'))['user_response']
    for who,voice,clothing,role in [('male','Charon','黒いパーカー、水色のシャツ','視聴者の疑問を言う'),('female','Aoede','アイボリーのパーカー、水色のシャツ','本人発表と考察を分け、相手へやわらかく返す')]:
        event('asset','atlas_'+who+'_v01',dict(asset_id=who+'-atlas',kind='generated_still',path=(ASSETS/(who+'-atlas.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',character_id=who,character_version=1,provenance='既存採用済みの男女アトラスを同一hashで再利用。新しい人物の生成なし。'))
        event('character','character_'+who+'_v01',dict(character_id=who,fictional_adult=True,name='既存シリーズの'+('男性' if who=='male' else '女性'),persona='AIを仕事に使う架空の成人。ニュースの事実と考察を分けて理解する。',role=role,clothing=clothing,voice='Gemini '+voice+' / conversational_v3',continuity='既存の顔、服装、声を継続。PIPは男性左、女性右。離脱を祝う演出をしない。',reference_asset_id=who+'-atlas'))
        event('approve-character','reuse_'+who+'_v01',dict(character_id=who,version=1,confirm_acceptance=True,user_response=response,scope='提示した企画v01に記載した既存男女の継続。新しい顔、完成動画、公開の採用には広げない。'))
        event('asset','motion_'+who+'_thinking_v01',dict(asset_id=who+'-thinking',kind='generated_video',path=(ASSETS/(who+'-thinking.mp4')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',character_id=who,character_version=1,provider='minimax',generation_record='outputs/content-projects/CONTENT_20261103_model_race/motion-provenance.json / new-case motion-provenance-v01.json',reuse=True))
    for name in ['departures-timeline','product-handoff-observation']:
        event('asset','article_'+name+'_v01',dict(asset_id=name,kind='original',path=(OUT/'article/v01/assets'/(name+'.png')).relative_to(ROOT).as_posix(),visibility='public',privacy_review='passed',context='1920×1080の自作説明図。実際の退社の影響を実測した図ではない。'))
    event('claim','claim_official_role_v01',dict(claim_id='cat-role',text='2026年3月のClaude公式記事はCat Wu氏をClaude CodeのHead of Productと紹介。退社理由の資料ではない。',basis='official',checked_at='2026-11-04',source_ids=['cat-official-role'],asset_ids=['official-role']))
    event('claim','claim_editorial_focus_v01',dict(claim_id='knowledge-handoff',text='考察として、製品作りの知見をチームが引き継ぎ、改善を続けられるかに注目する。共通原因や品質の悪化を示した実測ではない。',basis='hypothesis',checked_at='2026-11-04',source_ids=['cat-official-role','thariq-post','anthony-post','cat-post'],asset_ids=['product-handoff-observation']))
    plan=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));scenes=[]
    for t in plan['turns']:
        v=t['visual'];question=v in ['question','impact-question'];motion={'hook':'male-thinking','closing':'female-thinking'}.get(v)
        chars=['male','female'] if question else [motion.split('-')[0]] if motion else []
        assets=['male-atlas','female-atlas'] if question else [motion] if motion else ['thariq-quote','anthony-quote','cat-quote'] if v=='evidence' else ['official-role','product-handoff-observation']
        scene=dict(scene_id=t['id'],purpose={'hook':'相次ぐ退社と今後を見る問い','question':'誰が離れたか','evidence':'本人の3投稿と担当','impact-question':'利用者の疑問','analysis':'製品作りの知見の継承','closing':'今後の具体的な観察点'}[v],narration=t['display'],reading=t['reading'],visual=v,duration_seconds=t['frames']/24,start_seconds=t['start'],source_ids=t['source_ids'],asset_ids=assets,claim_ids=['cat-role','knowledge-handoff'] if v=='analysis' else ['knowledge-handoff'] if v=='closing' else [],character_ids=chars,beat='problem' if question else 'evidence' if v=='evidence' else 'action' if v=='closing' else 'insight')
        if chars:
            scene.update(character_action='考えるMiniMax動画を一度再生し保持。反応映像で音素同期は主張しない。' if motion else '男性の疑問、女性の注視。発話者だけPCM音量連動の簡易口パク、聞き手は閉口。',face_caption_separated=True,presenter_layout='fullscreen' if motion else 'pip')
            if question:scene['pip_policy']=dict(positions=dict(male='left',female='right'),trigger='emphasis',avoid_gui_controls=True,caption_safe=True,speech_mode='audio_envelope',listener_mouth='closed')
        scenes.append(scene)
    event('storyboard','completed_storyboard_short_v01',dict(episode_id='anthropic-departures-short',scenes=scenes))
    sections=[dict(section_id='departures',title='本人投稿で確認した3人',episode_ids=['anthropic-departures-short'],source_ids=['thariq-post','anthony-post','cat-post','cat-official-role','cat-bi'],asset_ids=['thariq-quote','anthony-quote','cat-quote','departures-timeline'],claim_ids=['cat-role'],character_ids=[]),dict(section_id='analysis',title='製品作りの知見の継承',episode_ids=['anthropic-departures-short'],source_ids=['cat-official-role'],asset_ids=['official-role','product-handoff-observation'],claim_ids=['knowledge-handoff'],character_ids=[]),dict(section_id='limits',title='現時点の不明点と今後の観察',episode_ids=['anthropic-departures-short'],source_ids=['thariq-post','anthony-post','cat-post','coxon-context'],asset_ids=[],claim_ids=['knowledge-handoff'],character_ids=[])]
    event('article','article_draft_v02',dict(slug='claude-code-departures-product-knowledge',target='blog',draft_path=(HERE/'ARTICLE_DRAFT_V02_JA.md').relative_to(ROOT).as_posix(),sections=sections,published=False))
    state=cli('get',project_id=HERE.name);save(OUT/'work/workspace-production-v01.json',state)
    print(json.dumps(dict(revision=state['project']['revision'],phase=state['project']['phase'],checks=state['checks']),ensure_ascii=False),flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    record()
