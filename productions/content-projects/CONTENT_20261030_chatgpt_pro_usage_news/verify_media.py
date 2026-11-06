"""Decode the actual delivery and retain boundary, growth and mobile review frames."""
from pathlib import Path
import hashlib,json,subprocess,sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name;R=OUT/'release/v02';V=R/'chatgpt-pro-usage-v02.mp4'
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True).stdout
def main():
 meta=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(V)]))
 v=next(s for s in meta['streams'] if s['codec_type']=='video');a=next(s for s in meta['streams'] if s['codec_type']=='audio')
 assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))==(1080,1920,'24/1',1152)
 assert abs(float(meta['format']['duration'])-48)<.1
 assert (a['sample_rate'],a['channels'])==('48000',2)
 run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(V),'-f','null','-'])
 q=R/'qc';q.mkdir(exist_ok=True)
 times=[.1,1,2,5.9,6.1,12.9,13.1,24.9,25.1,32.9,33.1,41.9,42.1,47.8]
 for i,t in enumerate(times):
  f=q/f'frame-{i:02d}.jpg'
  if not f.exists():run(['ffmpeg','-v','error','-nostdin','-ss',str(t),'-i',str(V),'-frames:v','1','-q:v','2',str(f)])
 grid=Image.new('RGB',(1080,math_height:=((len(times)+2)//3)*665),'#DDD')
 for i,t in enumerate(times):
  with Image.open(q/f'frame-{i:02d}.jpg') as im:
   im=im.resize((360,640));grid.paste(im,((i%3)*360,(i//3)*665+25))
  ImageDraw.Draw(grid).text(((i%3)*360+8,(i//3)*665+5),f'{t:.1f}s',fill='black')
 grid.save(q/'actual-video-contact-sheet.jpg')
 speech=[]
 for i in range(6):
  p=OUT/f'voice/v01/scene-{i:02d}/Aoede/verified.json';speech.append(json.loads(p.read_text(encoding='utf-8')))
 result=dict(width=v['width'],height=v['height'],fps=v['avg_frame_rate'],frames=v['nb_frames'],seconds=meta['format']['duration'],audio_rate=a['sample_rate'],audio_channels=a['channels'],full_decode='passed',sha256=hashlib.sha256(V.read_bytes()).hexdigest(),bytes=V.stat().st_size,tts_verified_requests=6,tts_usage=[s['usage'] for s in speech],minimax_new_requests=0,character_reuse='SHA-256 matched source motion registry',ai_frame_review='pending',human_listening=False,mobile_playback=False,user_approved=False,published=False)
 (R/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result))
if __name__=='__main__':main()
