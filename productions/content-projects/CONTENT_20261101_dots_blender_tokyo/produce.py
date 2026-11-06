"""Re-edit supplied, immutable Blender footage into captioned short and full cuts."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,shutil,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_avatar import SpriteAtlas,voice_gate
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
from tools.studio.text_layout import visible_glyph_bbox
from tools.studio.closing_visuals import end_screen,END_SCREEN_LAYOUT
OUT=ROOT/'outputs/content-projects'/HERE.name;ASSETS=OUT/'assets'
SOURCE=Path('C:/Users/mono_/Videos/安全ムービー動画ライブラリ/00_Blender')
SCRIPT=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
FPS=24;BG='#F5F3ED';INK='#152E3F';TEAL='#087F83';BLUE='#3878D3';AUDIT={}
FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
@lru_cache(maxsize=40)
def font(z):
    f=ImageFont.truetype(str(FONT),z);f.set_variation_by_axes([650]);return f
@lru_cache(maxsize=3000)
def glyph(s,z,c):
    b=visible_glyph_bbox(s,font(z));im=Image.new('RGBA',(b[2]-b[0]+2,b[3]-b[1]+2));ImageDraw.Draw(im).text((-b[0],-b[1]),s,font=font(z),fill=c);return im
def wrap(s,n):
    a=[]
    while len(s)>n:
        cut=n
        for mark in '、。？！':
            k=s.rfind(mark,max(4,n//2),n+1)
            if k>=max(4,n//2):cut=k+1;break
        a.append(s[:cut]);s=s[cut:]
    return a+([s] if s else [])
def text(im,s,rect,z=48,c=INK,center=True):
    lines=s.split('\n');tiles=[glyph(x,z,c) for x in lines];height=sum(g.height for g in tiles)+round(z*.27)*(len(tiles)-1)
    if max(g.width for g in tiles)>rect[2]-rect[0] or height>rect[3]-rect[1]:raise ValueError(f'Text does not fit: {s} {rect} {z}')
    y=rect[1]+((rect[3]-rect[1]-height)/2 if len(lines)==1 else 8)
    for g in tiles:
        x=rect[0]+(rect[2]-rect[0]-g.width)/2 if center else rect[0]
        im.paste(g,(round(x),round(y)),g);y+=g.height+round(z*.27)
    AUDIT[(s,tuple(rect),z)]=dict(text=s,rect=rect,size=z,ink_height=height,max_width=max(g.width for g in tiles),fits=True)
def box(im,rect,c,r=24):ImageDraw.Draw(im).rounded_rectangle(rect,radius=r,fill=c)
def fit(im,src,rect,cover=False):
    size=(rect[2]-rect[0],rect[3]-rect[1]);tile=ImageOps.fit(src,size,method=Image.Resampling.BICUBIC) if cover else ImageOps.contain(src,size,Image.Resampling.BICUBIC)
    im.paste(tile,(round((rect[0]+rect[2]-tile.width)/2),round((rect[1]+rect[3]-tile.height)/2)))

def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True);manifest=[]
    for sub in ['captures','renders']:
        for src in sorted((SOURCE/'tokyo_station_03_images'/sub).glob('*')):
            if src.suffix.lower() not in ['.jpg','.png']:continue
            im=Image.open(src).convert('RGB');dst=ASSETS/(src.stem+'.jpg')
            # Remove private window path and OS dock; keep real Blender menus/UI.
            crop=(0,31,1366,925) if sub=='captures' else (0,0,im.width,im.height)
            im.crop(crop).save(dst,quality=95)
            manifest.append(dict(rec(dst),source_relative=src.relative_to(SOURCE).as_posix(),original_sha256=sha(src),crop_xyxy=crop,kind='actual_checkpoint' if sub=='captures' else 'model_render'))
    old=ROOT/'outputs/content-projects/CONTENT_20261101_tibo_28day_full/assets'
    for name in ['male-atlas.png','female-atlas.png','male-understanding.mp4','female-happy.mp4','female-thinking.mp4']:
        dst=ASSETS/name
        if not dst.exists():shutil.copy2(old/name,dst)
        assert sha(old/name)==sha(dst);manifest.append(dict(rec(dst),kind='reused_approved_duo',source=rec(old/name)))
    raw=OUT/'_private/captures/dots-computer-official.png'
    if raw.exists():
        Image.open(raw).crop((281,144,850,184)).save(ASSETS/'official-dots-heading.png')
        manifest.append(dict(rec(ASSETS/'official-dots-heading.png'),kind='official_excerpt',url='https://learn.chatgpt.com/docs/dots/computers-and-apps',quoted_words=7,crop_xyxy=[281,144,850,184],checked_at='2026-11-01'))
    for axis in ['h','v']:
        for name in ['wide','dome','brick']:
            src=SOURCE/'tokyo_station_01_videos/drone'/f'{axis}_{name}.mp4';cache=OUT/'cache'/f'{axis}_{name}';cache.mkdir(parents=True,exist_ok=True)
            crop='crop=1600:900:160:90,scale=1600:900' if axis=='h' else 'crop=720:910:0:220,scale=900:-2'
            if not list(cache.glob('*.jpg')):run(['ffmpeg','-v','error','-nostdin','-i',str(src),'-vf',f'{crop},fps={FPS}','-q:v','2',str(cache/'%04d.jpg')])
            manifest.append(dict(source_relative=src.relative_to(SOURCE).as_posix(),original_sha256=sha(src),kind='provided_CG_camera_motion',source_fps=30,render_fps=24,removed_burned_titles=True,disclosure_replaced_in_composition=True))
    for name in ['male-understanding','female-happy','female-thinking']:
        cache=OUT/'cache'/name;cache.mkdir(parents=True,exist_ok=True)
        if not list(cache.glob('*.jpg')):run(['ffmpeg','-v','error','-nostdin','-i',str(ASSETS/(name+'.mp4')),'-vf',f'fps={FPS},scale=400:-2','-q:v','3',str(cache/'%04d.jpg')])
    save(OUT/'asset-manifest.json',dict(items=manifest,source_unchanged=True,source_native_screenshots=[1366,1024],article_note='Native 1366px checkpoint; public crop 1366x894. No claim of new 1400px capture or higher source resolution.'))
    print('assets prepared',flush=True)

def timeline(kind):
    dest=OUT/'release/v01'/kind;dest.mkdir(parents=True,exist_ok=True);turns=[];cursor=0
    for key in SCRIPT[kind+'_ids']:
        t=next(x for x in SCRIPT['turns'] if x['id']==key);path=OUT/'voice/v01'/key/'voice.wav'
        proof=json.loads(path.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(path)==next(x['sha256'] for x in proof['files'] if x['path'].endswith('voice.wav'))
        seconds=len(read_voice(path))/SR;lead=.18;tail=.45 if kind=='short' else .72
        duration=math.ceil((lead+seconds+tail)*FPS)/FPS;subs=[]
        chunks=[]
        for sentence in t['text'].replace('。','。|').replace('？','？|').split('|'):
            lines=wrap(sentence,17 if kind=='short' else 27)
            chunks.extend('\n'.join(lines[i:i+2]) for i in range(0,len(lines),2))
        at=cursor+lead;total=sum(len(s.replace('\n','')) for s in chunks)
        for s in chunks:
            stop=at+seconds*len(s.replace('\n',''))/total;subs.append(dict(start=at,end=stop,text=s));at=stop
        turns.append(dict(t,start=cursor,end=cursor+duration,frames=round(duration*FPS),voice_start=cursor+lead,voice_seconds=seconds,voice_path=str(path),subtitles=subs));cursor+=duration
    end_seconds=10 if kind=='full' else 1.4;total=cursor+end_seconds;n=round(total*SR)
    voice=np.zeros(n,np.float32)
    for t in turns:
        samples=read_voice(t['voice_path']);a=round(t['voice_start']*SR);voice[a:a+len(samples)]+=samples
    loop,meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    spans=[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in turns];music=default_bgm_bed(raw,total,spans)
    fx=np.zeros((n,2),np.float32)
    for t in turns:
        if t['visual'] not in ['build','windows','ornament','result']:continue
        a=round((t['start']+.08)*SR);cue=editorial_cue('improvement',sample_rate=SR)*.32;fx[a:a+len(cue)]+=cue
    mix=voice[:,None]+music+fx;mix*=min(1,.94/max(float(np.abs(mix).max()),1e-8))
    write_pcm(dest/'narration.wav',voice);write_pcm(dest/'mix.wav',mix);write_pcm(dest/'music-loop.wav',loop)
    data=dict(kind=kind,title=SCRIPT[kind+'_title'],width=1080 if kind=='short' else 1920,height=1920 if kind=='short' else 1080,fps=FPS,seconds=total,body_seconds=cursor,end_seconds=end_seconds,turns=turns)
    save(dest/'timeline.json',data);save(dest/'audio-plan.json',dict(profile=dict(DEFAULT_BGM_PROFILE),loop=meta,voices={'male':'Charon','female':'Aoede'},tts_model='gemini-2.5-flash-preview-tts',voice_seconds=sum(t['voice_seconds'] for t in turns),sound_effect='subtle improvement cue only'))
    def stamp(s):
        ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{sec:02},{ms:03}'
    subs=[s for t in turns for s in t['subtitles']]
    (dest/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subs))+'\n',encoding='utf-8')
    print(kind,round(total,2),'seconds',flush=True);return data

class Renderer:
    def __init__(self,kind):
        self.kind=kind;self.short=kind=='short';self.w,self.h=(1080,1920) if self.short else (1920,1080)
        self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']}
        self.sprites={(s,m,o,z):self.atlas[s].frame(m,o,z) for s in ['male','female'] for m in ['neutral','curious','serious','pleased'] for o in [False,True] for z in [190,220,320]}
        self.gates={};self.pics={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.jpg')}
        self.clips={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'cache').iterdir() if p.is_dir()}
    @lru_cache(maxsize=180)
    def frame_image(self,key,i):return Image.open(self.clips[key][min(i,len(self.clips[key])-1)]).convert('RGB')
    def motion(self,im,name,local,rect):fit(im,self.frame_image(name,round(local*FPS)),rect,cover=not self.short)
    def pip(self,im,t,local,large=False):
        z=220 if self.short else (320 if large else 190);y=1120 if self.short else (525 if large else 680)
        for s,x in [('male',65 if self.short else 55),('female',775 if self.short else 1545 if large else 1675)]:
            opened=False
            if s==t['speaker']:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(t['voice_path'])['gates']
                k=math.floor((local-.18)*FPS);g=self.gates[t['id']];opened=g[k] if 0<=k<len(g) else False
            mood='curious' if s=='male' else 'neutral'
            if t['visual'] in ['result','hero']:mood='pleased'
            if t['visual']=='limits':mood='serious'
            box(im,(x-5,y-5,x+z+5,y+z+5),TEAL if s==t['speaker'] else '#C3D2D5')
            motion='male-understanding' if s=='male' else 'female-thinking' if t['visual'] in ['question','request'] else 'female-happy'
            if s!=t['speaker'] and t['visual'] in ['question','result','cloud']:
                src=self.frame_image(motion,round(min(local,4.5)*FPS))
                crop=(0,133,400,min(src.height,510)) if s=='male' else (0,55,400,min(src.height,518))
                fit(im,src.crop(crop),(x,y,x+z,y+z),cover=True)
            else:im.paste(self.sprites[(s,mood,opened,z)],(x,y))
    def checkpoint(self,im,names,local,duration,rect):
        index=min(len(names)-1,int(local/max(.1,duration)*len(names)));src=self.pics[names[index]]
        # First establish a real application window, then show its own viewport larger.
        if local>min(1.5,duration*.2):
            src=src.crop((175,245,1000,710))
        if self.short and src.width>1000:src=src.crop((175,245,1000,710))
        fit(im,src,rect)
    def main(self,im,t,local):
        s=self.short;rect=(65,315,985,1100) if s else (85,225,1835,860);v=t['visual'];dur=t['end']-t['start']
        if v in ['hero','detail','result']:
            sequence=['dome','wide','brick'] if v=='hero' and s else ['wide','dome','brick'] if v=='hero' else ['dome','brick','wide'] if v=='detail' else ['brick','wide','dome']
            block=int(local/4);name=sequence[min(2,block)];start=min(local-block*4,3.95)
            self.motion(im,('v_' if s else 'h_')+name,start,rect)
            if s:text(im,'東京駅を題材にした簡略模型', (70,1050,980,1100),34,'#FFFFF2')
            else:text(im,'東京駅を題材にした簡略模型・CGカメラ映像',(300,865,1620,914),34,TEAL)
        elif v in ['build','windows','ornament','fix']:
            groups={'build':['01_site_generated','02_brick_massing','03_domes_roofs'],'windows':['04_stonework','05_windows_arches'],'ornament':['06_roof_ornament','08_finished_model'],'fix':['09_side_elevations','10_brick_coordinate_fix']}
            self.checkpoint(im,groups[v],local,dur,rect)
            text(im,'工程の実画面（静止画）',(90,1165,980,1220) if s else (300,865,1620,914),34,TEAL)
            if v=='fix' and local>dur*.65:
                fit(im,self.pics['dome_detail'],(180,650,900,1090) if s else (1040,450,1790,860))
                box(im,(240,610,840,665) if s else (1080,400,1760,457),TEAL,12)
                text(im,'仕上がりは完成CGで確認',(250,615,830,660) if s else (1090,405,1750,452),31,'white')
        elif v=='cloud':
            y=380 if s else 285
            box(im,(130,y,950,y+190) if s else (380,y,1540,y+150),TEAL)
            text(im,'dotsのクラウドPC',(150,y+10,930,y+85) if s else (400,y+10,1520,y+78),52,'white')
            text(im,'Blenderを操作',(150,y+100,930,y+170) if s else (400,y+80,1520,y+140),46,'white')
            ImageDraw.Draw(im).line((self.w//2,y+200,self.w//2,y+260),fill=TEAL,width=12)
            text(im,'依頼 → 制作 → 確認・修正',(80,y+280,1000,y+350) if s else (380,y+210,1540,y+275),44)
            if not s:
                q=Image.open(ASSETS/'official-dots-heading.png').convert('RGB');fit(im,q,(430,650,1490,755))
                text(im,'出典：OpenAI「Computers and apps」',(430,775,1490,835),29,TEAL)
        elif v=='request':
            box(im,(390,260,1530,690), '#E0EFED')
            text(im,'依頼例',(440,285,1480,350),42,TEAL)
            text(im,'東京駅の赤レンガと\nドーム屋根が分かる\n簡略模型を作って',(460,375,1460,620),56)
            text(im,'対象・特徴・用途を、先にそろえる',(400,735,1520,810),40)
        elif v=='question':
            fit(im,self.pics['hero_final'],(440,260,1480,720))
            text(im,'画像だけ？ それとも3D？',(450,750,1470,825),50)
        elif v=='limits':
            fit(im,self.pics['front_elevation'],(400,240,1520,560))
            for j,value in enumerate(['用途に合っている？','別の角度でも大丈夫？','保存したモデルも確認']):
                box(im,(500,580+j*90,1420,655+j*90),'#DDEBE8',15);text(im,value,(520,587+j*90,1400,647+j*90),42)
    def render(self,t,local):
        im=Image.new('RGB',(self.w,self.h),BG);s=self.short
        ImageDraw.Draw(im).rectangle((0,0,self.w,16),fill=TEAL)
        heading='\n'.join(wrap(t['heading'],15)) if s else t['heading']
        text(im,heading,(65,65,990,235) if s else (55,45,1865,128),64 if s else 61)
        sub='\n'.join(wrap(t['sub'],24)) if s else t['sub']
        text(im,sub,(70,235,990,310) if s else (90,145,1830,205),35 if s else 40,TEAL)
        self.main(im,t,local)
        if t['visual'] in ['cloud','question','request','limits','result'] or (s and t['visual']=='hero'):self.pip(im,t,local,large=not s and t['visual'] in ['question','request'])
        caption=next((a['text'] for a in t['subtitles'] if a['start']<=t['start']+local<a['end']),None)
        if caption:
            box(im,(55,1370,1010,1600) if s else (280,930,1640,1060),'#102C3C')
            text(im,caption,(80,1390,985,1580) if s else (310,945,1610,1050),49 if s else 45,'white')
        if s:text(im,'dots × Blender',(70,1690,985,1750),35,TEAL)
        # A short fade in/out within each cut softens transitions without mixing evidence frames.
        return im

def previews(kind):
    data=timeline(kind);dest=OUT/'release/v01'/kind;r=Renderer(kind);folder=dest/'qc';folder.mkdir(exist_ok=True)
    for t in data['turns']:
        for tag,pct in [('start',.1),('middle',.5),('late',.85)]:
            local=(t['end']-t['start'])*pct;im=r.render(t,local);im.save(folder/f"{t['id']}-{tag}.jpg",quality=90)
    save(dest/'text-layout.json',list(AUDIT.values()))
    thumbs=[Image.open(p).convert('RGB') for p in sorted(folder.glob('*-middle.jpg'))]
    tw,th=(270,480) if kind=='short' else (480,270);cols=3;contact=Image.new('RGB',(tw*cols,th*math.ceil(len(thumbs)/cols)),'#CDD4D5')
    for i,im in enumerate(thumbs):contact.paste(im.resize((tw,th)),(i%cols*tw,i//cols*th))
    contact.save(dest/'contact-sheet.jpg',quality=92);print('preview',kind,flush=True)

def render(kind):
    dest=OUT/'release/v01'/kind;data=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));r=Renderer(kind);parts=[]
    for t in data['turns']+([dict(id='end',frames=round(data['end_seconds']*FPS))]):
        path=OUT/'segments/v01'/kind/(t['id']+'.mp4');path.parent.mkdir(parents=True,exist_ok=True);parts.append(path)
        if path.exists():continue
        args=['ffmpeg','-y','-v','error','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s',f'{r.w}x{r.h}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','6',str(path)]
        process=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for i in range(t['frames']):
                if t['id']=='end':
                    if kind=='full':im=end_screen(i/FPS,label=lambda im,s,rect,z,c:text(im,s,rect,z,c))
                    else:
                        im=r.render(data['turns'][-1],data['turns'][-1]['end']-data['turns'][-1]['start']-.01)
                else:im=r.render(t,i/FPS)
                process.stdin.write(im.tobytes())
            process.stdin.close();err=process.stderr.read();code=process.wait()
            if code:raise RuntimeError(err.decode('utf-8','replace'))
        except BaseException:
            process.kill();process.wait();path.unlink(missing_ok=True);raise
        print(kind,t['id'],'rendered',flush=True)
    concat=dest/'segments.txt';concat.write_text('\n'.join("file '"+p.as_posix()+"'" for p in parts),encoding='utf-8')
    final=dest/('dots-blender-'+kind+'-v01.mp4')
    run(['ffmpeg','-y','-v','error','-nostdin','-f','concat','-safe','0','-i',str(concat),'-i',str(dest/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af','loudnorm=I=-16:TP=-1:LRA=9','-c:a','aac','-b:a','192k','-ar','48000','-t',str(data['seconds']),'-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(final),'-f','null','-'])
    met=run(['ffmpeg','-hide_banner','-nostdin','-i',str(final),'-af','loudnorm=I=-16:TP=-1:LRA=9:print_format=json','-f','null','-']).stderr
    loud=json.JSONDecoder().raw_decode(met[met.rfind('{'):])[0];probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]).stdout)
    save(dest/'qc.json',dict(status='technical_checks_complete_human_review_pending',file=rec(final),seconds=probe['format']['duration'],width=r.w,height=r.h,whole_decode='passed',loudness=loud,tts_user_approved=False,final_user_approved=False,published=False,end_screen=END_SCREEN_LAYOUT if kind=='full' else None))
    if AUDIT:save(dest/'text-layout.json',list(AUDIT.values()))
    print('COMPLETE',kind,final,flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','preview','render']);ap.add_argument('--kind',choices=['short','full'],default='short');a=ap.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='preview':previews(a.kind)
    else:render(a.kind)
