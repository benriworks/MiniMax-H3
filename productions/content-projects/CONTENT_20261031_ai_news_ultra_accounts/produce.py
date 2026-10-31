"""Two scoped news shorts: real official excerpts, explanatory motion, reused people."""
from pathlib import Path
import argparse,hashlib,json,math,shutil,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.longform_audio import music_bright,read_voice,write_pcm,SR
from tools.studio.music_mix import DEFAULT_BGM_PROFILE,default_bgm_bed
PLAN=json.loads((HERE/'plan.json').read_text(encoding='utf-8'))
FPS=24;W,H=1080,1920
FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
INK='#172F3E';GRAY='#526777';BG='#F5F2EA';WHITE='#FFFFFF'
FONTS={};IMAGES={}

def save(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def record(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def font(size):
    if size not in FONTS:
        FONTS[size]=ImageFont.truetype(str(FONT),size)
        try:FONTS[size].set_variation_by_axes([650])
        except (ValueError,OSError):pass
    return FONTS[size]
def text(im,value,xy,size=56,fill=INK,center=False):
    d=ImageDraw.Draw(im);x,y=xy
    for line in value.split('\n'):
        if d.textlength(line,font=font(size))>960:raise ValueError('Text exceeds content width: '+line)
        d.text((x,y),line,font=font(size),fill=fill,anchor='mt' if center else None)
        y+=round(size*1.30)
def box(im,rect,fill=WHITE,outline=None,radius=30):
    ImageDraw.Draw(im).rounded_rectangle(rect,radius=radius,fill=fill,outline=outline,width=4)
def load(path):
    key=str(path)
    if key not in IMAGES:
        with Image.open(path) as src:IMAGES[key]=src.convert('RGB').copy()
    return IMAGES[key]
def fit(im,path,rect,contain=True):
    x,y,x2,y2=rect;src=load(path);wh=(x2-x,y2-y)
    pic=ImageOps.contain(src,wh) if contain else ImageOps.fit(src,wh)
    im.paste(pic,(x+(wh[0]-pic.width)//2,y+(wh[1]-pic.height)//2))
def arrow(im,start,end,color,width=10):
    d=ImageDraw.Draw(im);d.line((*start,*end),fill=color,width=width)
    x,y=end;angle=math.atan2(y-start[1],x-start[0]);length=28
    pts=[end,(x-length*math.cos(angle-.6),y-length*math.sin(angle-.6)),(x-length*math.cos(angle+.6),y-length*math.sin(angle+.6))]
    d.polygon(pts,fill=color)
def check(im,x,y,color,scale=1):
    ImageDraw.Draw(im).line([(x-20*scale,y),(x-4*scale,y+15*scale),(x+27*scale,y-23*scale)],fill=color,width=round(9*scale))
def clock(im,x,y,r,color,t):
    d=ImageDraw.Draw(im);d.ellipse((x-r,y-r,x+r,y+r),outline=color,width=12)
    a=t*.7-1.57;d.line((x,y,x+math.cos(a)*r*.72,y+math.sin(a)*r*.72),fill=color,width=10)
    d.line((x,y,x-r*.35,y-r*.3),fill=color,width=10)
def calendar(im,rect,color):
    x,y,x2,y2=rect;box(im,rect,WHITE,color,18);d=ImageDraw.Draw(im)
    d.line((x,y+50,x2,y+50),fill=color,width=7)
    for i in range(7):
        xx=x+30+i*(x2-x-60)/6;d.ellipse((xx-6,y+90,xx+6,y+102),fill=color)
def phone(im,rect,color):
    box(im,rect,WHITE,INK,50);x,y,x2,y2=rect;d=ImageDraw.Draw(im)
    d.rounded_rectangle((x+105,y+18,x2-105,y+31),radius=7,fill=INK)
    d.rounded_rectangle((x+110,y2-28,x2-110,y2-20),radius=4,fill=color)

def prepare():
    assets=OUT/'assets';assets.mkdir(parents=True,exist_ok=True);items=[]
    registry=json.loads((ROOT/'productions/characters/motion-registry-20261022.json').read_text(encoding='utf-8'))
    source=Path('C:/Users/mono_/MiniMaxH3')/registry['clips']['claude-shiori']['video']['path']
    expected=registry['clips']['claude-shiori']['video']['sha256']
    if sha(source)!=expected:raise ValueError('Shiori source changed')
    target=assets/'shiori.mp4'
    if not target.exists():shutil.copy2(source,target)
    if sha(target)!=expected:raise ValueError('Shiori copy changed')
    items.append(dict(record(target),kind='reused_minimax_video',source=registry['clips']['claude-shiori']['video'],character='佐伯栞'))
    old=ROOT/'outputs/content-projects/CONTENT_20261030_chatgpt_pro_usage_news'
    for name in ['female-happy','female-thinking','male-understanding']:
        d=old/'motions/v01'/name;proof=json.loads((d/'verification.json').read_text(encoding='utf-8'))
        original=json.loads((d/'public-derivative.json').read_text(encoding='utf-8')) if (d/'public-derivative.json').exists() else proof['artifact']
        source=ROOT/original['path'];target=assets/f'{name}.mp4'
        if sha(source)!=original['sha256']:raise ValueError('Motion source changed')
        if not target.exists():shutil.copy2(source,target)
        if sha(target)!=original['sha256']:raise ValueError('Motion copy changed')
        items.append(dict(record(target),kind='reused_minimax_video',source=original))
    # Exact observed screenshot coordinates. Originals remain untouched.
    crops=[('ultra-condition','claude-ultra-benefits-official.png',(341,154,634,179)),
           ('ultra-price','claude-ultra-plan-official.png',(317,293,640,320)),
           ('ultra-verification-heading','claude-ultra-verified-official.png',(316,102,679,135)),
           ('account-example','chatgpt-switch-official.png',(105,137,775,634)),
           ('account-steps','chatgpt-mobile-steps-official.png',(113,111,280,180))]
    for name,original,rect in crops:
        source=OUT/'captures'/original;target=assets/f'{name}.png'
        with Image.open(source) as src:
            crop=src.convert('RGB').crop(rect);crop.save(target)
        with Image.open(target) as saved:assert np.array_equal(np.asarray(crop),np.asarray(saved))
        ep=PLAN['episodes'][0 if name.startswith('ultra') else 1]
        items.append(dict(record(target),kind='official_capture',source_url=ep['source_url'],source_checked_at='2026-10-31',
                          crop_xyxy=rect,original=record(source),width=crop.width,height=crop.height,privacy_review='passed',
                          example_is_official_not_own_device=name.startswith('account')))
    save(OUT/'asset-manifest.json',dict(items=items,new_minimax_requests=0,new_image_requests=0))
    for name in ['shiori','female-happy','female-thinking','male-understanding']:
        folder=OUT/'motion-cache'/name
        if folder.exists() and len(list(folder.glob('*.jpg')))==124:continue
        folder.mkdir(parents=True,exist_ok=True)
        run(['ffmpeg','-v','error','-nostdin','-i',str(assets/f'{name}.mp4'),'-vf','scale=540:-2','-q:v','2',str(folder/'%04d.jpg')])

def schedule(ep):
    actual=[]
    for i,s in enumerate(ep['scenes']):
        wav=OUT/ep['id']/f'voice/v01/scene-{i:02d}/Aoede/voice.wav'
        proof=json.loads(wav.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(wav)==next(f['sha256'] for f in proof['files'] if f['path'].endswith('/voice.wav'))
        actual.append(len(read_voice(wav))/SR)
    frames=[max(round(s['seconds']*FPS),math.ceil((d+.45)*FPS)) for s,d in zip(ep['scenes'],actual)]
    offset=0;timeline=[]
    for i,(n,d) in enumerate(zip(frames,actual)):
        timeline.append(dict(index=i,start=offset/FPS,end=(offset+n)/FPS,frames=n,voice_start=offset/FPS+.15,voice_seconds=d))
        offset+=n
    return timeline

def picture(im,name,t,rect):
    idx=min(124,max(1,round(t*FPS)+1))
    x,y,x2,y2=rect
    src=load(OUT/f'motion-cache/{name}/{idx:04d}.jpg')
    if name=='male-understanding':src=src.crop((0,130,src.width,src.height))
    center_y=.55 if name.startswith('female') else .08
    pic=ImageOps.fit(src,(x2-x,y2-y),centering=(.5,center_y))
    im.paste(pic,(x,y))

def quote(im,name,y,label,color):
    box(im,(65,y,1015,y+190),WHITE,color,22)
    text(im,label,(90,y+12),36,color)
    fit(im,OUT/f'assets/{name}.png',(91,y+74,989,y+165))

def frame(ep,index,t,duration,global_t,total,voice_seconds):
    is_claude=ep['id']=='claude-ultra';color='#AA543C' if is_claude else '#087E82'
    s=ep['scenes'][index];kind=s['kind'];im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,18),fill=color)
    text(im,'CLAUDE  /  PLAN UPDATE' if is_claude else 'CHATGPT  /  MOBILE UPDATE',(68,70),32,color)
    text(im,s['headline'],(540,158),68,INK,True)
    assets=OUT/'assets'
    if kind in {'hero','closing'} and t<4.9:
        picture(im,s['pose'],t,(66,380,1014,1475))
        box(im,(95,1200,985,1430),INK)
        text(im,'認証済みUltraが対象\n週上限は残る' if is_claude else '最大2アカウント\n今使うのは1アカウント',(540,1229),60,WHITE,True)
    elif is_claude:
        if kind=='price':
            box(im,(76,412,1004,850))
            text(im,'Max 20x',(170,470),70,GRAY);arrow(im,(360,622),(706,622),color)
            d.ellipse((360+346*min(1,t/1.8)-10,612,380+346*min(1,t/1.8)-10,632),fill=color)
            text(im,'Ultra',(540,703),100,color,True)
            text(im,'$200 / 月',(540,925),105,color,True)
            text(im,'Web価格・既存契約は自動移行',(540,1087),45,GRAY,True)
            quote(im,'ultra-price',1200,'公式ヘルプの価格説明',color)
        elif kind=='verify':
            for j,(label,note) in enumerate([('利用履歴','アカウントの履歴'),('支払い履歴','決済の履歴など')]):
                x=70+j*490;box(im,(x,430,x+450,700));text(im,label,(x+225,477),61,color,True);text(im,note,(x+225,594),39,GRAY,True)
            arrow(im,(300,741),(500,870),color);arrow(im,(780,741),(580,870),color)
            box(im,(210,880,870,1075),color);text(im,'自動で確認',(540,928),72,WHITE,True)
            text(im,'未認証 → 一時的な制限あり',(540,1130),47,INK,True)
            quote(im,'ultra-verification-heading',1230,'公式：認証済みアカウントの説明',color)
        elif kind=='usage':
            for j,label in enumerate(['設定','使用量','Current session']):
                y=415+j*225;box(im,(130,y,950,y+160),WHITE,color)
                text(im,label,(540,y+39),58,color,True)
                if j<2:arrow(im,(540,y+165),(540,y+215),color)
            box(im,(90,1140,990,1430),INK)
            text(im,'Ultraでバーがなければ\n認証済みの目安\n週使用量も確認',(540,1172),53,WHITE,True)
        else:
            box(im,(65,415,1015,900));clock(im,290,600,113,color,t)
            text(im,'5時間枠',(675,486),62,INK,True);text(im,'なし',(675,622),100,color,True)
            text(im,'認証済みUltraの場合',(540,785),46,GRAY,True)
            box(im,(65,947,1015,1250),INK);calendar(im,(114,1002,415,1180),color)
            check(im,265,1142,'#FFCD85',1+min(1,t/2)*.3)
            text(im,'週の上限',(690,990),61,WHITE,True);text(im,'残る',(690,1098),83,'#FFCD85',True)
            quote(im,'ultra-condition',1290,'公式ヘルプの対象条件',color)
    else:
        if kind=='official':
            box(im,(65,405,1015,1365));fit(im,assets/'account-example.png',(90,530,990,1240))
            text(im,'公式掲載の画面例',(540,440),43,color,True)
            text(im,'✓ が付いたアカウントを使用',(540,1280),43,GRAY,True)
        elif kind=='steps':
            for j,label in enumerate(['設定','Switch account','アカウントを選択']):
                y=425+j*220;box(im,(104,y,976,y+155),WHITE,color)
                text(im,label,(540,y+40),57,color,True)
                if j<2:arrow(im,(540,y+161),(540,y+211),color)
            text(im,'初回追加は Add account',(540,1142),48,INK,True)
            quote(im,'account-steps',1230,'公式の設定手順（一部）',color)
        elif kind=='separate':
            for j,(label,col) in enumerate([('仕事用',color),('個人用','#B56537')]):
                x=65+j*490;box(im,(x,420,x+450,1240),WHITE,col)
                text(im,label,(x+225,463),67,col,True)
                for k,word in enumerate(['会話','メモリ','ファイル','契約']):
                    y=632+k*131;box(im,(x+33,y,x+417,y+100),BG)
                    if t>=k*.38:text(im,word,(x+225,y+17),49,INK,True)
            # Separate containers stay visually separated; no connecting arrows.
            text(im,'自動移動・プラン共有はしません',(540,1320),45,INK,True)
        elif kind=='rollout':
            text(im,'10月30日 発表',(540,450),58,color,True)
            for j,label in enumerate(['iOS','Android']):
                x=105+j*490;phone(im,(x,585,x+380,1080),color)
                text(im,label,(x+190,748),59,color,True);check(im,x+190,945,color,1.6)
            box(im,(90,1170,990,1420),INK)
            text(im,'順次提供\n項目がなければ未提供の可能性',(540,1207),49,WHITE,True)
        else:
            phone(im,(330,425,750,1235),color)
            for j,(label,col) in enumerate([('仕事用',color),('個人用','#B56537')]):
                y=665+j*265;box(im,(150,y,930,y+170),col)
                text(im,label,(540,y+40),70,WHITE,True)
                if j==int(t/1.6)%2:check(im,855,y+88,WHITE,1)
            arrow(im,(200,825),(200,900),color);arrow(im,(880,930),(880,830),'#B56537')
            text(im,'会話・メモリ・ファイル・契約は別',(540,1320),44,GRAY,True)
    caps=s['captions'];active=min(len(caps)-1,int(max(0,t-.15)/max(.1,voice_seconds)*len(caps)))
    cap=caps[active]
    # Explicit editorial line breaks; never shrink the subtitle to unreadable size.
    if len(cap)>19:
        split=cap.rfind('・',7,20)
        if split<0:split=cap.rfind('→',7,20)
        if split<0:split=18
        cap=cap[:split]+'\n'+cap[split:]
    box(im,(55,1542,1025,1777),INK)
    text(im,cap,(540,1580),56,WHITE,True)
    text(im,ep['source_label'],(70,1808),30,GRAY)
    d.rectangle((70,1865,1010,1873),fill='#D4DAD8')
    d.rectangle((70,1865,70+940*global_t/total,1873),fill=color)
    return im

def audio(ep,timeline,dest):
    seconds=timeline[-1]['end'];voice=np.zeros(round(seconds*SR),dtype=np.float32);spans=[];sources=[]
    for s in timeline:
        p=OUT/ep['id']/f"voice/v01/scene-{s['index']:02d}/Aoede/voice.wav"
        v=read_voice(p);v=v/max(.01,float(np.max(np.abs(v))))*.82
        a=round(s['voice_start']*SR);b=a+len(v);assert b<=len(voice)
        voice[a:b]+=v;spans.append((a/SR,b/SR));sources.append(record(p))
    raw=music_bright(seconds,fade_in_seconds=0,fade_out_seconds=0)
    music=default_bgm_bed(raw,seconds,spans);mix=voice[:,None]*np.ones((1,2),dtype=np.float32)+music
    if np.max(np.abs(mix))>=.98:raise ValueError('Revise mix headroom before delivery')
    write_pcm(dest/'narration.wav',voice);write_pcm(dest/'music.wav',music);write_pcm(dest/'mix.wav',mix)
    save(dest/'audio-plan.json',dict(bgm_settings=dict(DEFAULT_BGM_PROFILE),voice='Aoede',sources=sources,peak=float(np.max(np.abs(mix)))))

def preview():
    prepare();folder=OUT/'review/visual-v01';folder.mkdir(parents=True,exist_ok=True)
    grid=Image.new('RGB',(1080,1280),'#DDDDDD')
    for k,ep in enumerate(PLAN['episodes']):
        for i,s in enumerate(ep['scenes']):
            im=frame(ep,i,2,s['seconds'],sum(v['seconds'] for v in ep['scenes'][:i])+2,45,s['seconds'])
            im.save(folder/f"{ep['id']}-{i:02d}.png")
            grid.paste(im.resize((180,320)),(i*180,k*640))
            # Detail view of main content in the second row for each episode.
            grid.paste(im.crop((30,360,1050,1475)).resize((180,197)),(i*180,k*640+335))
    grid.save(folder/'contact-sheet.jpg')

def render(ep,version='v01'):
    prepare();dest=OUT/ep['id']/'release'/version;dest.mkdir(parents=True,exist_ok=True)
    target=dest/(ep['id']+'-'+version+'.mp4')
    if target.exists():raise RuntimeError('Preserve finished output; create a new version')
    timeline=schedule(ep);seconds=timeline[-1]['end'];save(dest/'timeline.json',timeline);audio(ep,timeline,dest)
    # Normalize only when the premaster falls outside the accepted range.
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(dest/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    measurement=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);save(dest/'premaster-loudness.json',measurement)
    extra=[]
    if not (-18<=float(measurement['input_i'])<=-14 and float(measurement['input_tp'])<=-1):
        extra=['-af',f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={measurement['input_i']}:measured_TP={measurement['input_tp']}:measured_LRA={measurement['input_lra']}:measured_thresh={measurement['input_thresh']}:offset={measurement['target_offset']}:linear=true"]
    process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0','-i',str(dest/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-threads','6','-preset','fast','-crf','19','-pix_fmt','yuv420p',*extra,'-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-t',str(seconds),str(target)],stdin=subprocess.PIPE)
    try:
        for s in timeline:
            i=s['index'];print(json.dumps(dict(event='render',episode=ep['id'],scene=i,frames=s['frames'])),flush=True)
            for n in range(s['frames']):
                im=frame(ep,i,n/FPS,s['end']-s['start'],s['start']+n/FPS,seconds,s['voice_seconds'])
                if n==min(48,s['frames']//2):im.save(dest/f'scene-{i:02d}.png')
                process.stdin.write(im.tobytes())
    finally:process.stdin.close()
    if process.wait()!=0:raise RuntimeError('Video encoding failed')
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(target),'-f','null','-'])
    stats=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]).stdout)
    v=next(x for x in stats['streams'] if x['codec_type']=='video')
    assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))==(W,H,'24/1',sum(s['frames'] for s in timeline))
    assert abs(float(stats['format']['duration'])-seconds)<.1
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(target),'-af','loudnorm=print_format=json','-f','null','-']).stderr
    measurement=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1])
    assert -18<=float(measurement['input_i'])<=-14 and float(measurement['input_tp'])<=-1
    save(dest/'verification.json',dict(record(target),seconds=seconds,width=W,height=H,fps=FPS,frames=int(v['nb_frames']),full_decode='passed',loudness=measurement,
        bgm_settings=dict(DEFAULT_BGM_PROFILE),narration='Gemini Aoede',new_minimax_requests=0,own_mobile_demo=False,own_ultra_verified_demo=False,
        user_approved=False,human_listening=False,mobile_playback=False,published=False))
    print(json.dumps(dict(event='verified',episode=ep['id'],seconds=seconds,bytes=target.stat().st_size)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','preview','render']);p.add_argument('--episode',choices=[e['id'] for e in PLAN['episodes']]);p.add_argument('--version',choices=['v01','v02'],default='v01');a=p.parse_args()
    if a.command=='prepare':prepare()
    elif a.command=='preview':preview()
    else:
        for ep in PLAN['episodes']:
            if not a.episode or ep['id']==a.episode:render(ep,a.version)
