"""Verify final encoded media and extract evidence, without synthesizing speech."""
from pathlib import Path
import json,sys,subprocess,hashlib
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v01'
video=OUT/'gpt61-terra-short-v01-subtitle-bgm.mp4'
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
v=next(x for x in probe['streams'] if x['codec_type']=='video');a=next(x for x in probe['streams'] if x['codec_type']=='audio')
assert (v['width'],v['height'],v['r_frame_rate'],v['pix_fmt'],v['codec_name'])==(1080,1920,'24/1','yuv420p','h264')
assert int(v['nb_frames'])==1200 and abs(float(probe['format']['duration'])-50)<.05
assert a['codec_name']=='aac' and a['sample_rate']=='48000' and a['channels']==2
subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(video),'-f','null','-'],check=True,capture_output=True)
data=video.read_bytes();assert data.find(b'moov')<data.find(b'mdat')
plan=json.loads((OUT/'timing-subtitle-draft.json').read_text(encoding='utf-8'))
review=OUT/'review';frames=[]
sheet=Image.new('RGB',(1440,1280),'white')
for i,s in enumerate(plan['scenes']):
    path=review/f'encoded-scene-{i+1:02}.png'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-ss',str(s['start']+min(2,(s['end']-s['start'])/2)),'-i',str(video),'-frames:v','1','-y',str(path)],check=True,capture_output=True)
    thumb=Image.open(path).resize((360,640),Image.Resampling.LANCZOS)
    thumb.save(review/f'mobile-scene-{i+1:02}.png');sheet.paste(thumb,((i%4)*360,(i//4)*640));frames.append(rec(path))
sheet.save(review/'encoded-mobile-contact.png')
Image.open(review/'encoded-scene-02.png').save(OUT/'thumbnail-v01.jpg',quality=93)
proof={'status':'media_verified_visual_review_pending','video':rec(video),'duration_seconds':50,'width':1080,'height':1920,'fps':24,'frames':1200,'audio':'AAC 48kHz stereo; original BGM only; no narration','full_decode':'passed','faststart':'passed','frame_evidence':frames,'human_listening':'pending','smartphone_device_playback':'pending','user_adoption':False,'published':False,'api_demo':{'response_model':'gpt-6.1-terra','calls':1,'pc_operation_calls':0,'after_image_reinference':False},'narration':'Aoede rejected HTTP402 quota_exhausted; alternative approval pending'}
(OUT/'verification-v01.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'duration':50,'video':rec(video),'full_decode':'passed','frames':1200}))
