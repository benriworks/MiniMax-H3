"""Update only dependencies affected by the high-resolution capture; finalize draft."""
from pathlib import Path
import json,subprocess,sys,hashlib,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v01';PID=HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.content_workspace import ContentWorkspace
from tools.studio.database import StudioDatabase
service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
def apply(action,data):
    p=service.get(PID)['project'];body={'operation_id':'terra_finalize_'+action.replace('-','_')+'_'+str(p['revision']),'expected_revision':p['revision'],'data':data};save(HERE/'inputs'/f"finalize-{p['revision']:02d}-{action}.json",body);return service.apply(PID,action,body)
state=service.get(PID);old=next(a for a in state['project']['assets'] if a['asset_id']=='api_result')
if old['path'].endswith('v02.png'):
    apply('asset',{'asset_id':'api_result','kind':'demonstration_capture','visibility':'public','privacy_review':'passed','fictional_materials_only':True,'path':(OUT/'api-result-capture-v03.png').relative_to(ROOT).as_posix()})
    claim=next(c for c in service.get(PID)['project']['claims'] if c['claim_id']=='tested_banner');apply('claim',claim)
    p=service.get(PID)['project']
    for e in p['episodes']:
        for s in e['storyboard']:
            if s.get('needs_review'):apply('reconcile',{'scope':'scene','episode_id':e['episode_id'],'scene_id':s['scene_id'],'reason':'同じAPI実応答を1600px幅で再撮影。内容・回答・前後画像・意味が同じで、動画の原画像は変更していない。'})
    for s in service.get(PID)['project']['article']['sections']:
        if s.get('needs_review'):apply('reconcile',{'scope':'section','section_id':s['section_id'],'reason':'記事用キャプチャを1600px幅で再撮影。実応答と前後画像を再照合。本文の検証範囲は維持。'})
state=service.get(PID);save(HERE/'workspace-state-final-v01.json',state)
proof=json.loads((OUT/'verification-v01.json').read_text(encoding='utf-8'))
proof.update(status='media_and_ai_visual_review_passed_narration_pending',ai_visual_review={'encoded_mobile_contact':'review/encoded-mobile-contact.png','all_8_scenes':'checked','headline_and_caption':'readable_at_360px_in_saved_frames','banner_small_print':'context only; primary comparison uses a dedicated enlargement','overlap':'no headline/caption overlap observed','final_listening':'not_performed'})
save(OUT/'verification-v01.json',proof);save(HERE/'VERIFICATION_V01_JA.json',{'video':proof['video'],'duration_seconds':50,'width':1080,'height':1920,'fps':24,'frames':1200,'full_decode':'passed','faststart':'passed','ai_mobile_frame_review':'8 encoded scene frames inspected; primary message and captions readable','human_listening':'pending','smartphone_device_playback':'pending','narration':'not_recorded; Aoede402 quota_exhausted; alternative choice pending','user_adoption':False,'published':False,'content_workspace_checks':state['checks']})
manifest={'version':'v01','assets':state['project']['assets'],'official_context':rec(ROOT/'output/playwright/terra-official-context-v01.png'),'unusable_blank_capture':'api-result-capture.png is about:blank; not a demonstration asset','channels':{'video':'subtitle_bgm_draft','blog':'candidate_materials_only'}};save(OUT/'asset-manifest.json',manifest)
blog=OUT/'blog-handoff/v01/assets';blog.mkdir(parents=True,exist_ok=True)
items=[]
for name in ['banner-before.png','banner-after.png','api-result-capture-v03.png','official-heading.png']:
    target=blog/name;shutil.copyfile(OUT/name,target);assert (OUT/name).read_bytes()==target.read_bytes();items.append(rec(target))
save(blog.parent/'asset-manifest.json',{'assets':items,'copy_hashes_match':True,'status':'candidate_not_adopted_not_published','missing':['cover photo','existing blog guide character banner','MDX integration and blog build review']})
review=OUT/'review/index.html'
review.write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><title>GPT-6.1 Terra ショート初稿</title><style>body{font:18px sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;background:#f6f7ef;color:#16382c}video{width:360px;max-width:100%;background:#111}img{width:100%}a{color:#164c8c}</style><h1>GPT-6.1 Terra ショート初稿 v01</h1><p>50秒・1080×1920・24fps。字幕と自作BGM付き。ナレーションは未収録（Aoedeの利用枠超過、代替音声の回答待ち）。</p><video controls preload="metadata" src="../gpt61-terra-short-v01-subtitle-bgm.mp4"></video><p><a href="../gpt61-terra-short-v01-subtitle-bgm.mp4" download>MP4を保存</a> ／ <a href="../subtitles-ja-bgm-draft.srt">字幕</a></p><p>実APIの画像確認と提案値の反映を含みます。PC自動操作の実演は未実施。人の試聴・スマホ実機再生・最終採用・公開は未確認です。</p><h2>実動画からの8場面（各360px幅）</h2><img src="encoded-mobile-contact.png"><h2>実行結果と記事候補画像</h2><a href="../api-result-viewer.html">実API応答の自作ビューアー</a></html>''',encoding='utf-8')
save(HERE/'delivery-v01.json',{'status':'subtitle_bgm_draft_delivered_narration_pending','video':rec(OUT/'gpt61-terra-short-v01-subtitle-bgm.mp4'),'verification':rec(OUT/'verification-v01.json'),'article':rec(HERE/'article-draft-v01.md'),'review':rec(review),'drive':{'folder_id':'1u6CNT7C-E1QtoSgxk-znNTI7XrZZSZBl','file_id':'1mJKBvRulVI4CkrCLt6clfyaYgNMYi_cT','file_name':'GPT-6.1-Terra_ショート_v01_字幕BGM版_50秒.mp4','bytes':2185731,'url':'https://drive.google.com/file/d/1mJKBvRulVI4CkrCLt6clfyaYgNMYi_cT/view?usp=drivesdk','metadata_readback':'name,size,parent matched; owner-only, shared false','smartphone_playback':'not_verified'},'narration':'not_recorded','user_adoption':False,'published':False})
print('Finalized draft; content revision',state['project']['revision'])
