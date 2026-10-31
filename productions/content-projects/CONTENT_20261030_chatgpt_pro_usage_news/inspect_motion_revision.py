"""Inspect generated pose assets or the final revision; no model requests."""
from pathlib import Path
import argparse,hashlib,json,subprocess
from PIL import Image,ImageChops,ImageStat,ImageDraw

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=ROOT/'outputs/content-projects'/HERE.name
def command(args):return subprocess.run(args,check=True,capture_output=True,text=True).stdout
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inspect_pose(job):
 dest=OUT/'motions/v01'/job;proof=json.loads((dest/'verification.json').read_text(encoding='utf-8'))
 raw=ROOT/proof['artifact']['path']
 if digest(raw).upper()!=proof['artifact']['sha256']:raise RuntimeError('Raw video changed')
 command(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(raw),'-f','null','-'])
 # This measures visible change only; semantic pose and identity still require visual review.
 pictures=[]
 for i,t in enumerate([.2+i*.5 for i in range(10)]+[5.1]):
  p=dest/f'inspect-{i:02d}.jpg'
  if not p.exists():command(['ffmpeg','-v','error','-nostdin','-ss',str(t),'-i',str(raw),'-frames:v','1','-q:v','2',str(p)])
  with Image.open(p) as im:pictures.append(im.convert('L').resize((96,172)))
 differences=[ImageStat.Stat(ImageChops.difference(a,b)).mean[0] for a,b in zip(pictures,pictures[1:])]
 result=dict(job=job,raw_sha256=digest(raw),full_decode=True,half_second_grayscale_differences=differences,metric_scope='Pixel-change diagnostic; not a semantic action or identity score',ai_visual_review=False,user_approved=False)
 (dest/'inspection.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result),flush=True)

def inspect_final():
 dest=OUT/'release/v03';p=dest/'chatgpt-pro-usage-v03.mp4';old=OUT/'release/v02/chatgpt-pro-usage-v02.mp4'
 meta=json.loads(command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
 v=next(x for x in meta['streams'] if x['codec_type']=='video');a=next(x for x in meta['streams'] if x['codec_type']=='audio')
 if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1080,1920,'24/1',1152):raise RuntimeError('Unexpected video geometry')
 if abs(float(meta['format']['duration'])-48)>.1:raise RuntimeError('Timing changed')
 command(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(p),'-f','null','-'])
 def audio_hash(path):return command(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c:a','copy','-f','hash','-hash','sha256','-']).strip()
 if audio_hash(p)!=audio_hash(old):raise RuntimeError('AAC bitstream changed')
 q=dest/'qc';q.mkdir(exist_ok=True);times=[.2,2.8,5.8,8.8,13.2,16.5,19.2,23,27.5,33.2,41.8,44.8,47.8]
 sheet=Image.new('RGB',(1080,((len(times)+2)//3)*665),'#ddd')
 for i,t in enumerate(times):
  frame=q/f'frame-{i:02d}.jpg'
  if not frame.exists():command(['ffmpeg','-v','error','-nostdin','-ss',str(t),'-i',str(p),'-frames:v','1','-q:v','2',str(frame)])
  x=i%3*360;y=i//3*665;ImageDraw.Draw(sheet).text((x+10,y+5),f'{t:.1f}s',fill='black')
  with Image.open(frame) as im:sheet.paste(im.resize((360,640)),(x,y+25))
 sheet.save(q/'actual-video-contact-sheet.jpg')
 result=dict(width=v['width'],height=v['height'],frames=v['nb_frames'],seconds=meta['format']['duration'],fps=v['avg_frame_rate'],audio_rate=a['sample_rate'],audio_channels=a['channels'],full_decode='passed',aac_bitstream_equal_to_v02=True,sha256=digest(p),bytes=p.stat().st_size,new_h3_clips=6,new_tts_requests=0,ai_visual_review=False,human_listening=False,mobile_playback=False,user_approved=False,published=False)
 (dest/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--job');p.add_argument('--final',action='store_true');a=p.parse_args()
 if a.final:inspect_final()
 else:
  jobs=json.loads((HERE/'motion-jobs-v01.json').read_text(encoding='utf-8'))['jobs']
  for job in ([a.job] if a.job else list(jobs)):inspect_pose(job)
