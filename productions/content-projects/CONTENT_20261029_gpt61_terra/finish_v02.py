"""Verify the rendered conversation and record this direction without inventing adoption."""
from pathlib import Path
import json,sys,hashlib,subprocess
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v02';sys.path.insert(0,str(ROOT))
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
p=json.loads((OUT/'timing.json').read_text(encoding='utf-8'));video=OUT/'terra-explained-v02.mp4'
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]));v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'],v['r_frame_rate'])==(1080,1920,'24/1');assert int(v['nb_frames'])==p['frames'];assert abs(float(probe['format']['duration'])-p['seconds'])<.06
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,capture_output=True)
sheet=Image.new('RGB',(1800,1280),'white');frames=[]
for i,t in enumerate(p['turns']):
    path=OUT/'review'/f'encoded-{i:02d}.png';subprocess.run(['ffmpeg','-v','error','-ss',str((t['scene_start']+t['scene_end'])/2),'-i',str(video),'-frames:v','1','-y',str(path)],check=True,capture_output=True)
    pic=Image.open(path).resize((360,640));sheet.paste(pic,((i%5)*360,(i//5)*640));frames.append(rec(path))
sheet.save(OUT/'review/mobile-contact.png')
def stamp(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
chunks=[];n=1
for t in p['turns']:
    cursor=t['start'];total=sum(len(c) for c in t['captions'])
    for c in t['captions']:
        end=cursor+len(c)/total*(t['end']-t['start']);chunks.append(f'{n}\n{stamp(cursor)} --> {stamp(end)}\n{c}\n');cursor=end;n+=1
(OUT/'subtitles-ja.srt').write_text('\n'.join(chunks),encoding='utf-8')
proof={'video':rec(video),'seconds':p['seconds'],'frames':p['frames'],'width':1080,'height':1920,'fps':24,'full_decode':'passed','audio':{'codec':a['codec_name'],'sample_rate':a['sample_rate'],'channels':a['channels'],'speakers':['Charon','Aoede'],'new_requests':10,'new_audio_generation_succeeded':True},'encoded_frames':frames,'character_source':'existing adopted dots v03 duo; MiniMax opening3s plus existing atlas; no new character generation','ai_visual_review':'pending','human_listening':'pending','smartphone_playback':'pending','user_approved':False,'published':False,'source_checked_at':'2026-10-31','demo_tested_at':'2026-10-29','pc_operation_tested':False}
save(OUT/'verification.json',proof);save(HERE/'verification-v02.json',{k:v for k,v in proof.items() if k!='encoded_frames'})
from tools.studio.database import StudioDatabase
from tools.studio.content_workspace import ContentWorkspace
svc=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False));PID=HERE.name
def apply(action,data):
    current=svc.get(PID)['project'];body={'operation_id':'terra_remake_'+action+'_'+str(current['revision']),'expected_revision':current['revision'],'data':data};save(OUT/'workspace-inputs'/f"{current['revision']:02d}-{action}.json",body);return svc.apply(PID,action,body)
current=svc.get(PID)['project'];episode=dict(current['episodes'][0]);episode.pop('storyboard',None);episode['title']='【ChatGPT】Terraは何が得意？画像の確認からPC操作まで';episode['overview']='既存の二人の質問と説明から、用途・API画像確認・PC操作の条件・Work/Codexを理解する会話版。';episode['intended_message']='画像を見て判断し作業につなぐモデル。画像入力とPC操作には別の条件がある。';episode['duration_seconds']=p['seconds']
if not any(x['proposal_id']=='terra_conversation_v02' for x in current['proposals']):
    apply('proposal',{'proposal_id':'terra_conversation_v02','count_reason':'前の字幕BGM版の演出不足を受け、既存人物と声を使う説明1本へ改訂。新シリーズ量産はしない。','episodes':[episode]})
    apply('feedback',{'feedback_id':'terra_remake_user','proposal_id':'terra_conversation_v02','kind':'acceptance','text':'改めてTerraを説明する動画を作成して下さい。','interpretation':'前の指摘を踏まえた説明動画の再制作依頼。人物と演出の既存採用記録を参照し会話で説明する。完成物の最終採用・公開は含めない。'})
    apply('accept',{'proposal_id':'terra_conversation_v02','feedback_id':'terra_remake_user','confirm_acceptance':True})
    apply('asset',{'asset_id':'api_recap_20261031','kind':'demonstration_capture','visibility':'public','privacy_review':'passed','fictional_materials_only':True,'path':rec(OUT/'api-evidence-recapture-20261031.png')['path']})
    apply('storyboard',{'episode_id':episode['episode_id'],'scenes':[{'scene_id':f'conversation_{i:02d}','purpose':t['kind'],'narration':t['text'],'visual':'既存人物二人の会話。比較中は人物非表示。'+t['kind'],'duration_seconds':t['scene_end']-t['scene_start'],'claim_ids':['tested_banner'] if t['kind'] in ['before','after'] else ['official_capability','official_access'],'source_ids':['official_launch'],'asset_ids':['api_recap_20261031'] if t['kind'] in ['before','after'] else [],'character_ids':[],'legacy_character_source_project':'CONTENT_20261026_dots_transfer_detail','legacy_character_source_version':'adopted v03; existing footage/atlases, no new character approvals invented'} for i,t in enumerate(p['turns'])]})
save(HERE/'workspace-state-v02.json',svc.get(PID))
review=OUT/'review/index.html';review.write_text('<!doctype html><meta charset="utf-8"><title>Terra説明動画v02</title><style>body{font:18px sans-serif;background:#f6f7ef;color:#16382c;max-width:1200px;margin:30px auto}video{width:360px;max-width:100%}img{width:100%}</style><h1>Terraは何が得意？ v02</h1><p>二人の会話・Charon/Aoede音声・明るいBGM。人の試聴とスマホ再生は未確認。</p><video src="../terra-explained-v02.mp4" controls preload="metadata"></video><p><a href="../subtitles-ja.srt">字幕</a></p><img src="mobile-contact.png">',encoding='utf-8')
print(json.dumps({'seconds':p['seconds'],'video':rec(video),'decode':'passed'}))
