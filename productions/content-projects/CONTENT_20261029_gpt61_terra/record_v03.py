"""Record visual-only revision and preserve source media/adoption boundaries."""
from pathlib import Path
import json,sys,shutil,hashlib
from copy import deepcopy
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v03';sys.path.insert(0,str(ROOT))
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
v=json.loads((OUT/'verification.json').read_text(encoding='utf-8'));v['status']='technical_and_ai_visual_review_passed';v['ai_visual_review']='Full-body upright posture, both planted feet, matching identities/outfits, mutual gaze and mouth-state difference regions inspected. 10 scene contact sheet plus full-resolution frames checked.'
v['drive']={'id':'1F8Q6uGoW_FBlJid2nQDV9jK7_Mm9MQuC','url':'https://drive.google.com/file/d/1F8Q6uGoW_FBlJid2nQDV9jK7_Mm9MQuC/view','name':'GPT-6.1-Terra_説明動画_v03_直立対話・文字配置修正版.mp4','bytes':3405775,'parent':'1u6CNT7C-E1QtoSgxk-znNTI7XrZZSZBl'}
save(OUT/'verification.json',v);save(HERE/'verification-v03.json',{k:val for k,val in v.items() if k!='layout_pixel_audit'})
save(HERE/'delivery-v03.json',{'status':'review_candidate','video':v['video'],'seconds':v['seconds'],'drive':v['drive'],'pcm_and_aac_unchanged':True,'max_center_error_px':v['max_center_error_px'],'subtitle_states_checked':v['subtitle_states_checked'],'user_approved':False,'human_listening':'pending','smartphone_playback':'pending','published':False})
save(OUT/'standing-generation.json',{'method':'built-in image_gen edit','references':['outputs/productions/LONG_20261026_dots_transfer_detail/v03/avatars/intro-atlas.png','outputs/characters/dots-duo-opening-20261026/v01/keyframes/end.png'],'result':rec(OUT/'standing-atlas.png'),'prompt_summary':'Preserve adult duo faces/hair/clothes; both stand completely upright with planted feet, relaxed arms and mutual gaze. Three identical 16:9 panels, closed mouths / male speaking / female speaking.','new_character_identity':False,'user_direction':'女性の方もきちんと立って、男性と対話させて下さい。','user_adoption_of_output':False,'minimax_api_key_configured':False,'new_minimax_calls':0})
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace
svc=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False));PID=HERE.name
def apply(action,data):
    p=svc.get(PID)['project'];body={'operation_id':'terra_v03_'+action+'_'+str(p['revision']),'expected_revision':p['revision'],'data':data};save(OUT/'workspace-inputs'/f"{p['revision']:02d}-{action}.json",body);return svc.apply(PID,action,body)
p=svc.get(PID)['project']
if not any(x['feedback_id']=='terra_v03_visual_request' for x in p['feedback']):
    apply('feedback',{'feedback_id':'terra_v03_visual_request','proposal_id':p['accepted_proposal']['proposal_id'],'kind':'comment','text':'女性の方もきちんと立って、男性と対話させて下さい。また、動画の文字のセンタリングや帯の中での中央寄せなどの完成度をチェックして修正して下さい。','interpretation':'v02の人物姿勢と文字配置を直す映像改訂。音声と台詞は維持。生成結果の採用と公開は別。'})
    apply('asset',{'asset_id':'standing_duo_v03','kind':'generated_still','visibility':'public','privacy_review':'passed','path':rec(OUT/'standing-atlas.png')['path']})
    p=svc.get(PID)['project'];e=p['episodes'][0];scenes=deepcopy(e['storyboard'])
    for s in scenes:
        if s['purpose'] not in ['before','after']:s['asset_ids'].append('standing_duo_v03')
        s['visual']+=' v03: 二人の直立素材。文字は実グリフ範囲で中央配置。音声・尺を維持。'
        s['legacy_character_source_version']='v03 standing edit of existing identities; original v02 standing/leaning footage removed'
    apply('storyboard',{'episode_id':e['episode_id'],'scenes':scenes})
save(HERE/'workspace-state-v03.json',svc.get(PID))
for name in ['standing-atlas.png','standing-reference.png']:
    target=OUT/'blog-candidates'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(OUT/name,target)
save(OUT/'blog-candidates/manifest.json',{'images':[rec(OUT/'blog-candidates'/name) for name in ['standing-atlas.png','standing-reference.png']],'usage':'video character asset candidates; no blog-wide guide-character adoption, MDX placement or publication','user_approved_for_blog':False})
article=(HERE/'article-draft-v02.md').read_text(encoding='utf-8').replace('video_revision: v02','video_revision: v03');article+='\n\n## 映像v03の改訂\n\n二人とも直立して対話する姿勢に修正し、見出し・字幕・帯の文字を中央配置した。音声と実験結果はv02のまま。人物素材は動画用の姿勢修正で、ブログ全体の案内役の変更ではない。記事本文の事実・検証範囲は変えていない。\n';(HERE/'article-draft-v03.md').write_text(article,encoding='utf-8')
review=OUT/'review/index.html';review.write_text('<!doctype html><meta charset="utf-8"><title>Terra説明動画v03</title><style>body{font:18px sans-serif;background:#f6f7ef;color:#16382c;max-width:1200px;margin:30px auto}video{width:360px;max-width:100%}img{width:100%}</style><h1>Terra説明動画 v03</h1><p>二人の直立姿勢・会話。文字は左右と帯内上下中央へ修正。26字幕状態の実画素検査、中央誤差最大1px。v02の音声AACと一致。</p><video src="../terra-explained-v03.mp4" controls preload="metadata"></video><p>人の最終試聴・スマホ実機再生・完成物採用は未確認。</p><img src="mobile-contact.png">',encoding='utf-8')
print('Recorded v03 and updated blog draft')
