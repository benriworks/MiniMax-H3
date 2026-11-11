"""Encoded-pixel layout checks, every subtitle state, and audio preservation."""
from pathlib import Path
import json,sys,subprocess,hashlib,shutil
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'outputs/content-projects'/HERE.name/'v03';OLD=OUT.parent/'v02'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
video=OUT/'terra-explained-v03.mp4';plan=json.loads((OUT/'timing.json').read_text(encoding='utf-8'))
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]));v=next(x for x in probe['streams'] if x['codec_type']=='video')
assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_frames']))==(1080,1920,'24/1',1507)
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,capture_output=True)
review=OUT/'review';review.mkdir(exist_ok=True);audit=[];times=[.5]
for t in plan['turns']:
    cursor=t['start'];total=sum(len(c) for c in t['captions'])
    for c in t['captions']:
        duration=len(c)/total*(t['end']-t['start']);times.append(cursor+duration*.5);cursor+=duration
for i,at in enumerate(times):
    p=review/f'encoded-{i:02d}.png';subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(video),'-frames:v','1','-y',str(p)],check=True,capture_output=True)
    im=np.asarray(Image.open(p).convert('RGB'));bounds={}
    for name,box in [('caption',(60,1510,1020,1725)),('heading_band',(85,463,995,524))]:
        x0,y0,x1,y1=box;region=im[y0:y1,x0:x1]
        mask=np.all(region>190,axis=2) if name=='caption' else ((region[:,:,0]<90)&(region[:,:,1]<120)&(region[:,:,2]<110))
        yy,xx=np.where(mask)
        assert len(xx)>10
        b=[int(xx.min()+x0),int(yy.min()+y0),int(xx.max()+x0+1),int(yy.max()+y0+1)]
        dx=abs((b[0]+b[2])/2-540);dy=abs((b[1]+b[3])/2-(1617.5 if name=='caption' else 493.5))
        assert dx<=2 and dy<=2,(i,name,b,dx,dy)
        bounds[name]={'ink_bbox':b,'horizontal_center_error_px':dx,'vertical_center_error_px':dy}
    audit.append({'at':at,**bounds})
sheet=Image.new('RGB',(1800,1280),'white')
for i,t in enumerate(plan['turns']):
    sample=min(range(len(times)),key=lambda j:abs(times[j]-(t['scene_start']+t['scene_end'])/2));pic=Image.open(review/f'encoded-{sample:02d}.png').resize((360,640));sheet.paste(pic,((i%5)*360,(i//5)*640))
sheet.save(review/'mobile-contact.png')
for slug,path in [('previous',OLD/'terra-explained-v02.mp4'),('current',video)]:
    subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','adts','-y',str(OUT/(slug+'.aac'))],check=True,capture_output=True)
assert (OUT/'previous.aac').read_bytes()==(OUT/'current.aac').read_bytes()
assert (OUT/'mix.wav').read_bytes()==(OLD/'mix.wav').read_bytes()
shutil.copyfile(OLD/'subtitles-ja.srt',OUT/'subtitles-ja.srt')
save(OUT/'verification.json',{'status':'technical_verified_visual_review_pending','video':rec(video),'seconds':float(probe['format']['duration']),'frames':1507,'full_decode':'passed','original_pcm_identical':True,'encoded_aac_identical':True,'tts_calls':0,'minimax_calls':0,'layout_pixel_audit':audit,'subtitle_states_checked':len(audit),'max_center_error_px':max(max(a[k]['horizontal_center_error_px'],a[k]['vertical_center_error_px']) for a in audit for k in ['caption','heading_band']),'user_approved':False,'human_listening':'pending','smartphone_playback':'pending'})
print('Verified',len(audit),'subtitle states; AAC and PCM unchanged')
