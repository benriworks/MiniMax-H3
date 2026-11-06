"""Approved news short: relative allowance charts, reused MiniMax motion, Aoede."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, subprocess, sys, time, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
RELEASE=OUT/'release/v02'
FPS=24
W,H=1080,1920
sys.path.insert(0,str(ROOT))
from tools.studio.longform_audio import music_bright,write_pcm,read_voice

SCENES=[
 dict(seconds=6,headline='使える枠が、\n拡大。',text='ChatGPT Proの作業枠が増えました。でも、全員が2倍ではありません。',captions=['ChatGPT Proの作業枠が拡大','でも、全員が2倍ではありません']),
 dict(seconds=7,headline='Pro 100・500\n従来の2倍',text='Pro100と500は、WorkとCodexの枠が2倍。',captions=['Pro 100と500は','Work・Codexの枠が2倍']),
 dict(seconds=12,headline='Pro 200は\n条件で分かれる',text='Pro200は、低い枠だった人だけ2倍。すでに高い枠なら据え置き。予定されていた削減は撤回です。',captions=['低い枠だった人は2倍','すでに高い枠なら据え置き','予定されていた削減は撤回']),
 dict(seconds=8,headline='追加料金なし\n更新待ちもなし',text='追加料金なし。契約更新を待たず自動適用されます。Plusは変更なし。',captions=['追加料金なし・既存契約も自動適用','Plusは今回の変更なし']),
 dict(seconds=9,headline='枠が2倍でも\n仕事数は条件次第',text='グラフは従来比で、具体的な回数ではありません。Chatの枠とは別で、仕事数2倍の保証でもありません。',captions=['グラフは従来比・具体的な回数ではない','Chatの枠とは別','仕事数2倍を保証するものではない']),
 dict(seconds=6,headline='自分のプランと\n使用状況を確認',text='設定で、自分のプランと使用状況を確認しましょう。',captions=['設定でプランと使用状況を確認しましょう'])
]
PRONUNCIATIONS=[('ChatGPT','チャットジーピーティー'),('Codex','コーデックス'),('Work','ワーク'),('Pro100','プロひゃく'),('Pro200','プロにひゃく'),('500','ごひゃく'),('Pro','プロ'),('Plus','プラス'),('Chat','チャット')]

def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cmd(args):subprocess.run(args,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def voice():
 spec=importlib.util.spec_from_file_location('news_speech',ROOT/'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py')
 speech=importlib.util.module_from_spec(spec);spec.loader.exec_module(speech)
 save(OUT/'voice/v01/plan.json',dict(model=speech.MODEL,voice='Aoede',maximum_requests=6,automatic_retry=False,scenes=SCENES,pronunciations=PRONUNCIATIONS))
 last=0
 for i,s in enumerate(SCENES):
  parent=OUT/f'voice/v01/scene-{i:02d}';parent.mkdir(parents=True,exist_ok=True)
  spoken=s['text']
  for a,b in PRONUNCIATIONS:spoken=spoken.replace(a,b)
  if not (parent/'Aoede').exists():
   wait=max(0,22-(time.monotonic()-last))
   if wait:time.sleep(wait)
   last=time.monotonic()
  proof=speech.synthesize(parent,spoken,'Aoede',minimum_seconds=.2)
  print(json.dumps(dict(scene=i,seconds=proof['duration_seconds'],status=proof['status'])),flush=True)

def schedule():
 durations=[]
 for i,s in enumerate(SCENES):
  wav=OUT/f'voice/v01/scene-{i:02d}/Aoede/voice.wav'
  if not wav.exists():raise RuntimeError('Aoede narration incomplete; do not label the video complete')
  proof=json.loads(wav.with_name('verified.json').read_text(encoding='utf-8'))
  assert sha(wav).upper()==next(f['sha256'] for f in proof['files'] if f['path'].endswith('/voice.wav'))
  v=read_voice(wav);durations.append(len(v)/24000)
 # Preserve every spoken sample; add reading holds and maintain ~48s where possible.
 minimum=[math.ceil((d+.40)*FPS) for d in durations]
 targets=[s['seconds']*FPS for s in SCENES]
 if sum(minimum)<=48*FPS:
  extra=48*FPS-sum(minimum);weights=[max(1,t-m) for t,m in zip(targets,minimum)]
  add=[int(extra*w/sum(weights)) for w in weights]
  for i in range(extra-sum(add)):add[i%6]+=1
  counts=[m+a for m,a in zip(minimum,add)]
 else:counts=minimum
 cursor=0;result=[]
 for i,(count,d) in enumerate(zip(counts,durations)):
  result.append(dict(index=i,start=cursor/FPS,end=(cursor+count)/FPS,frames=count,voice_start=cursor/FPS+.15,voice_seconds=d))
  cursor+=count
 return result

def cache():
 for who in ['male','female']:
  d=OUT/'motion-cache'/who;d.mkdir(parents=True,exist_ok=True)
  if len(list(d.glob('*.jpg')))==124:continue
  source=OUT/f'characters/dots-{who}-motion.mp4'
  cmd(['ffmpeg','-v','error','-nostdin','-i',str(source),'-vf','scale=540:968','-q:v','3',str(d/'%04d.jpg')])

FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
INK='#172E3B';MUTED='#536B77';TEAL='#087E82';ORANGE='#B45135';BG='#F4F1E8'
fonts={}
def font(n):
 if n not in fonts:
  f=ImageFont.truetype(str(FONT),n)
  try:f.set_variation_by_axes([650])
  except (OSError,ValueError):pass
  fonts[n]=f
 return fonts[n]
def txt(im,text,xy,size=56,fill=INK,anchor=None):
 d=ImageDraw.Draw(im);x,y=xy
 for line in text.split('\n'):
  d.text((x,y),line,font=font(size),fill=fill,anchor=anchor,stroke_width=0)
  y+=round(size*1.25)
def box(im,xy,fill='white',outline=None,r=28):ImageDraw.Draw(im).rounded_rectangle(xy,radius=r,fill=fill,outline=outline,width=3)
def photo(im,who,xy,wh,t):
 # Existing verified motion; muted, no synthetic lip-sync claim.
 idx=int(t*FPS)%124+1
 with Image.open(OUT/f'motion-cache/{who}/{idx:04d}.jpg') as src:
  v=ImageOps.fit(src,wh,method=Image.Resampling.LANCZOS)
  mask=Image.new('L',wh);ImageDraw.Draw(mask).rounded_rectangle((0,0,wh[0],wh[1]),radius=34,fill=255)
  im.paste(v,xy,mask)
def ease(t):return 1-(1-max(0,min(1,t)))**3
def bars(im,y,label,p,width=820):
 txt(im,label,(76,y),44)
 left=92;base=y+355
 # Zero baseline; each plan's OWN previous allowance = 1. Never compare absolute plans.
 ImageDraw.Draw(im).line((left,base,left+width,base),fill='#CAD5D5',width=4)
 for j,(h,col,word) in enumerate([(105,'#92A7AA','以前'),(105*(1+ease(p)),TEAL,'変更後')]):
  x=left+130+j*350
  box(im,(x,base-h,x+200,base),col,r=16)
  txt(im,('1' if j==0 else f'{1+ease(p):.1f}').replace('2.0','2'),(x+100,base-h-72),58,col,anchor='mt')
  txt(im,word,(x+100,base+15),42,MUTED,anchor='mt')
def fitted(im,path,rect):
 with Image.open(path) as src:
  scaled=ImageOps.contain(src,(rect[2]-rect[0],rect[3]-rect[1]),Image.Resampling.LANCZOS)
  im.paste(scaled,(rect[0],rect[1]+(rect[3]-rect[1]-scaled.height)//2))

def frame(i,t,duration,global_t,voice_seconds=None):
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 d.rectangle((0,0,W,16),fill=TEAL)
 txt(im,'ChatGPT  /  PRO NEWS',(72,77),36,TEAL)
 txt(im,SCENES[i]['headline'],(72,164),76)
 if i==0:
  photo(im,'male',(72,402),(440,650),t)
  photo(im,'female',(536,402),(440,650),t+.5)
  box(im,(72,980,976,1460),'white')
  bars(im,1010,'Pro 100・500：各プランの従来比', (t-.4)/1.8)
  txt(im,'全員が2倍ではありません',(74,1470),48,ORANGE)
 elif i==1:
  photo(im,'female',(670,405),(306,390),t)
  txt(im,'Work ＋ Codex',(76,454),58,TEAL)
  txt(im,'共有する利用枠',(76,544),44)
  box(im,(72,805,976,1430),'white')
  bars(im,858,'Pro 100  /  Pro 500',(t-.5)/2)
  txt(im,'各プランの以前を1とした相対表示',(76,1325),40,MUTED)
  txt(im,'プラン同士の絶対量の比較ではありません',(76,1455),36,MUTED)
 elif i==2:
  photo(im,'male',(72,405),(296,400),t)
  txt(im,'自分は、どっち？',(400,495),48,TEAL)
  box(im,(72,845,976,1120),'white')
  txt(im,'低い枠だった人',(104,875),48)
  txt(im,'従来比',(104,984),40,MUTED)
  progress=ease((t-.5)/1.8)
  d.rounded_rectangle((370,990,370+int(510*(.5+.5*progress)),1060),radius=20,fill=TEAL)
  txt(im,'2倍',(885,894),68,TEAL,anchor='rt')
  box(im,(72,1150,976,1400),'white')
  txt(im,'高い枠だった人',(104,1180),48)
  txt(im,'据え置き',(875,1265),64,ORANGE,anchor='rt')
  txt(im,'予定されていた削減を撤回',(76,1460),50,ORANGE)
 elif i==3:
  photo(im,'female',(546,425),(430,1050),t)
  for j,(a,b) in enumerate([('追加料金','なし'),('既存契約も','自動適用'),('Plus','変更なし')]):
   y=460+j*345;box(im,(72,y,515,y+285),'white')
   txt(im,a,(104,y+32),43)
   txt(im,b,(104,y+132),62,TEAL if j<2 else ORANGE)
 elif i==4:
  box(im,(72,440,976,1045),'white')
  txt(im,'グラフは従来比',(106,470),54,TEAL)
  bars(im,565,'各プランの以前 = 1',1)
  txt(im,'絶対量や具体的な回数を\n示すグラフではありません',(76,1080),43,ORANGE)
  txt(im,'Chatの週間枠とは別',(76,1210),51)
  fitted(im,OUT/'captures/openai-allowance-short-quote-v02.png',(86,1300,960,1420))
  txt(im,'引用：OpenAI Pro公式ヘルプ',(86,1450),36,MUTED)
 elif i==5:
  box(im,(72,420,976,900),'white')
  txt(im,'設定 → 使用状況',(104,457),58,TEAL)
  fitted(im,OUT/'captures/chatgpt-usage-header.png',(104,555,944,795))
  txt(im,'確認する場所を紹介しています',(104,820),36,MUTED)
  photo(im,'male',(72,950),(440,565),t)
  photo(im,'female',(536,950),(440,565),t+.5)
 # Full-size meaning-based captions: fixed minimum size, never over faces/UI.
 display_caps=[
  ['ChatGPT Proの\n作業枠が拡大','でも、全員が2倍では\nありません'],
  ['Pro 100と500は','Work・Codexの枠が\n2倍'],
  ['低い枠だった人は2倍','すでに高い枠なら\n据え置き','予定されていた削減は\n撤回'],
  ['追加料金なし\n既存契約も自動適用','Plusは今回の変更なし'],
  ['グラフは従来比\n具体的な回数ではない','Chatの枠とは別','仕事数2倍を\n保証するものではない'],
  ['設定で自分のプランと\n使用状況を確認しましょう']]
 caps=display_caps[i];speech_time=voice_seconds if voice_seconds is not None else duration
 cap=caps[min(len(caps)-1,int(max(0,t-.15)/max(.1,speech_time)*len(caps)))]
 box(im,(58,1560,982,1768),INK)
 txt(im,cap,(520,1585),60,'white',anchor='mt')
 txt(im,'2026.10.29発表  /  出典：OpenAI公式ヘルプ',(72,1800),30,MUTED)
 d.rectangle((72,1860,976,1868),fill='#CFD8D7')
 d.rectangle((72,1860,72+904*min(1,global_t/48),1868),fill=TEAL)
 return im

def audio(plan):
 seconds=plan[-1]['end'];music=music_bright(seconds);env=np.ones(len(music),dtype=np.float32)
 voice_track=np.zeros(len(music),dtype=np.float32)
 for s in plan:
  v=read_voice(OUT/f"voice/v01/scene-{s['index']:02d}/Aoede/voice.wav")
  v=v/(max(.01,np.max(np.abs(v))))*.82
  start=round(s['voice_start']*24000);voice_track[start:start+len(v)]+=v
  env[max(0,start-2400):min(len(env),start+len(v)+4800)]=.20
 mix=music*env[:,None]*1.3+voice_track[:,None]*np.array([1,1])
 assert np.max(np.abs(mix))<1
 write_pcm(RELEASE/'audio-mix.wav',mix)
 save(RELEASE/'audio-measurement.json',dict(peak=float(np.max(np.abs(mix))),bgm='original C-major 112BPM; shared bright music generator',ducking_gain=.2,voice='Aoede',human_listening=False))

def render():
 RELEASE.mkdir(parents=True,exist_ok=True)
 plan=schedule();save(RELEASE/'timeline.json',plan);cache();audio(plan)
 target=RELEASE/'chatgpt-pro-usage-v02.mp4'
 if target.exists():raise RuntimeError('Do not overwrite a rendered review; create v02')
 process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0','-i',str(RELEASE/'audio-mix.wav'),'-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-shortest',str(target)],stdin=subprocess.PIPE)
 for s in plan:
  i=s['index'];print(json.dumps(dict(event='render_scene',index=i,frames=s['frames'])),flush=True)
  for n in range(s['frames']):
   im=frame(i,n/FPS,s['end']-s['start'],s['start']+n/FPS,s['voice_seconds'])
   if n==min(48,s['frames']//2):im.save(RELEASE/f'scene-{i:02d}-review.png')
   process.stdin.write(im.tobytes())
 process.stdin.close()
 if process.wait()!=0:raise RuntimeError('FFmpeg render failed')
 save(RELEASE/'delivery.json',dict(path=target.relative_to(ROOT).as_posix(),bytes=target.stat().st_size,sha256=sha(target),seconds=plan[-1]['end'],width=W,height=H,fps=FPS,technical_qc=False,user_approved=False,published=False,character_motion='reused MiniMax; not newly generated',voice='Aoede',model='gemini-2.5-flash-preview-tts',chart='Each plan previous allowance=1; relative not absolute or measured use'))
 print(str(target),flush=True)

def preview():
 cache();d=OUT/'visual-tests/v01';d.mkdir(parents=True,exist_ok=True)
 for i,s in enumerate(SCENES):frame(i,2,s['seconds'],sum(x['seconds'] for x in SCENES[:i])+2).save(d/f'scene-{i:02d}.png')
 grid=Image.new('RGB',(1080,1280),'#DDD')
 for i in range(6):
  with Image.open(d/f'scene-{i:02d}.png') as im:grid.paste(im.resize((360,640)),((i%3)*360,(i//3)*640))
 grid.save(d/'contact-sheet.jpg')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['voice','preview','render']);a=p.parse_args()
 {'voice':voice,'preview':preview,'render':render}[a.command]()
