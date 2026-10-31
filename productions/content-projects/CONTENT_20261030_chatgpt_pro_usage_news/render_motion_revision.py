"""Add six newly generated H3 reactions; preserve the prior 48-second AAC stream."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess
from PIL import Image,ImageOps,ImageDraw

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('pro_news_base',HERE/'produce.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
OUT=base.OUT;MOTIONS=OUT/'motions/v01';RELEASE=OUT/'release/v03';CACHE=OUT/'motion-cache/v03'
JOBS=json.loads((HERE/'motion-jobs-v01.json').read_text(encoding='utf-8'))['jobs']
ACTIVE_SCENE=0

def checked_sources():
 result={}
 for job in JOBS:
  proof=MOTIONS/job/'verification.json'
  if not proof.exists():raise RuntimeError('New MiniMax pose not yet generated: '+job)
  value=json.loads(proof.read_text(encoding='utf-8'));item=value['artifact'];p=ROOT/item['path']
  if not value['execution']['success'] or not item['full_decode_verified'] or base.sha(p).upper()!=item['sha256']:raise RuntimeError('Motion identity/technical proof mismatch: '+job)
  result[job]=dict(video=p,proof=proof,sha256=item['sha256'],frames=value['settings']['frames'])
 return result

def cache_sources(sources):
 for name,item in sources.items():
  d=CACHE/name;d.mkdir(parents=True,exist_ok=True)
  files=list(d.glob('*.jpg'))
  if files and len(files)!=item['frames']:raise RuntimeError('Incomplete pose cache: '+name)
  if not files:base.cmd(['ffmpeg','-v','error','-nostdin','-i',str(item['video']),'-vf','scale=540:968','-q:v','3',str(d/'%04d.jpg')])
  if len(list(d.glob('*.jpg')))!=item['frames']:raise RuntimeError('Unexpected pose frame count')

def selection(scene,who,t):
 # Play each purposeful action once. Never loop the same palm-up gesture.
 if scene==0:return who+'-happy',max(0,t)*.82
 if scene==1:return who+'-understanding',max(0,t)*.72
 if scene==2:
  return (who+'-thinking',max(0,t)*.82) if t<6 else (who+'-understanding',(t-6)*.82)
 if scene==3:return who+'-happy',max(0,t)*.62
 return who+'-understanding',max(0,t)*.82

def new_photo(im,who,xy,wh,t):
 name,source_t=selection(ACTIVE_SCENE,who,t);index=min(123,int(source_t*24))+1
 with Image.open(CACHE/name/f'{index:04d}.jpg') as src:
  pic=ImageOps.fit(src,wh,method=Image.Resampling.LANCZOS)
  mask=Image.new('L',wh);ImageDraw.Draw(mask).rounded_rectangle((0,0,*wh),radius=34,fill=255)
  im.paste(pic,xy,mask)

base.photo=new_photo
def new_frame(i,t,duration,global_t,voice_seconds=None):
 global ACTIVE_SCENE
 ACTIVE_SCENE=i
 im=base.frame(i,t,duration,global_t,voice_seconds)
 if i==2:
  ImageDraw.Draw(im).rectangle((385,402,980,814),fill=base.BG)
  base.txt(im,'自分は\nどっち？',(418,480),52,base.TEAL)
  new_photo(im,'female',(680,405),(296,400),t)
 return im

def review_gallery(sources):
 target=MOTIONS/'pose-gallery.jpg'
 gallery=Image.new('RGB',(1440,750),'#F4F1E8')
 for i,(job,item) in enumerate(sources.items()):
  x=(i%3)*480;y=(i//3)*375
  base.txt(gallery,job,(x+15,y+15),30,base.INK)
  for j,n in enumerate((25,65,109)):
   with Image.open(CACHE/job/f'{n:04d}.jpg') as pic:
    gallery.paste(ImageOps.contain(pic,(154,286),method=Image.Resampling.LANCZOS),(x+j*160,y+70))
 gallery.save(target)

def render():
 sources=checked_sources();cache_sources(sources);review_gallery(sources)
 RELEASE.mkdir(parents=True,exist_ok=True);target=RELEASE/'chatgpt-pro-usage-v03.mp4'
 if target.exists():raise RuntimeError('Do not overwrite v03; choose another revision')
 timeline=json.loads((OUT/'release/v02/timeline.json').read_text(encoding='utf-8'))
 original=OUT/'release/v02/chatgpt-pro-usage-v02.mp4'
 proc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x1920','-framerate','24','-i','pipe:0','-i',str(original),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart','-t','48',str(target)],stdin=subprocess.PIPE)
 for s in timeline:
  i=s['index'];print(json.dumps(dict(event='render_pose_revision',scene=i)),flush=True)
  for n in range(s['frames']):
   im=new_frame(i,n/24,s['end']-s['start'],s['start']+n/24,s['voice_seconds'])
   if n in (48,min(s['frames']-1,168)):im.save(RELEASE/f'scene-{i:02d}-frame-{n:03d}.jpg')
   proc.stdin.write(im.tobytes())
 proc.stdin.close()
 if proc.wait()!=0:raise RuntimeError('Render failed')
 base.save(RELEASE/'timeline.json',timeline)
 base.save(RELEASE/'motion-provenance.json',{name:dict(path=item['video'].relative_to(ROOT).as_posix(),proof=item['proof'].relative_to(ROOT).as_posix(),sha256=item['sha256'],context='new MiniMax H3 generation for this revision') for name,item in sources.items()})
 base.save(RELEASE/'delivery.json',dict(path=target.relative_to(ROOT).as_posix(),bytes=target.stat().st_size,sha256=base.sha(target),seconds=48,width=1080,height=1920,fps=24,audio='AAC stream copied from v02',new_h3_poses=6,new_tts_requests=0,technical_qc=False,ai_visual_review=False,user_approved=False,published=False))
 print(str(target),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['render','gallery']);args=p.parse_args()
 if args.command=='render':render()
 else:
  sources=checked_sources();cache_sources(sources);review_gallery(sources)
