"""Self-contained Terra announcement short; reuses verified voice/music modules."""
from pathlib import Path
import hashlib, json, math, subprocess, sys, time, wave
from datetime import datetime, timezone
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'outputs/content-projects'/HERE.name/'v01'
STORY=json.loads((HERE/'story-v01.json').read_text(encoding='utf-8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
def voices():
    from tools.studio.dialogue_narration import synthesize
    last=0
    for i,s in enumerate(STORY['scenes']):
        target=OUT/'voice'/s['id']
        if not target.exists():
            time.sleep(max(0,22-(time.monotonic()-last)));last=time.monotonic()
        p=synthesize(target,s['spoken'],'female')
        print(f"Voice {i+1}/8: {p['seconds']:.2f}s",flush=True)

def audio():
    from tools.studio.longform_audio import read_voice,write_pcm,music_bright,SR
    cursor=0; scenes=[];segments=[]
    for s in STORY['scenes']:
        p=OUT/'voice'/s['id']/'voice.wav';v=read_voice(p)
        frames=math.ceil((len(v)/SR+.65)*24);duration=frames/24
        scenes.append(dict(s,start=cursor,end=cursor+duration,frames=frames,voice_start=cursor+.12,voice_seconds=len(v)/SR))
        segments.append(v);cursor+=duration
    mix=np.zeros((round(cursor*SR),2),np.float32)
    for s,v in zip(scenes,segments):
        a=round(s['voice_start']*SR);mix[a:a+len(v)]+=v[:,None]*.9
    music=music_bright(cursor)*.32
    # Attenuate the original music through all spoken samples with gentle ramps.
    env=np.ones(len(mix),np.float32)
    for s,v in zip(scenes,segments):
        a=max(0,round((s['voice_start']-.10)*SR));b=min(len(env),round((s['voice_start']+len(v)/SR+.15)*SR));env[a:b]=.48
    mix+=music*env[:,None]
    peak=float(abs(mix).max())
    if peak>.95:mix*=.95/peak
    write_pcm(OUT/'mix.wav',mix)
    result=dict(fps=24,width=1080,height=1920,frames=round(cursor*24),seconds=cursor,scenes=scenes,peak=float(abs(mix).max()),alignment='PCM segment boundaries; caption phrases weighted by character count; no speech trimming')
    save(OUT/'timing.json',result);return result

FONTS={}
def font(n,bold=True):
    k=(n,bold)
    if k not in FONTS:FONTS[k]=ImageFont.truetype('C:/Windows/Fonts/YuGothB.ttc' if bold else 'C:/Windows/Fonts/YuGothM.ttc',n)
    return FONTS[k]
def text(d,xy,t,size=50,fill='#16382c',bold=True):d.text(xy,t,font=font(size,bold),fill=fill,stroke_width=0)
def fittext(d,xy,t,size,maxw,**kw):
    if d.textlength(t,font=font(size))>maxw:raise ValueError('Text exceeds deliberate width: '+t)
    text(d,xy,t,size,**kw)
def pill(d,box,label,color='#d3f49b',size=30):
    d.rounded_rectangle(box,radius=24,fill=color);text(d,(box[0]+24,box[1]+10),label,size)
ASSETS={}
def asset(name):
    if name not in ASSETS:ASSETS[name]=Image.open(OUT/name).convert('RGB')
    return ASSETS[name]
def paste(im,name,box):
    pic=asset(name);pic=pic.resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);im.paste(pic,(box[0],box[1]))
def crop_title(im,name,y,width=920):
    pic=asset(name).crop((720,200,1600,405));h=round(pic.height*width/pic.width)
    pic=pic.resize((width,h),Image.Resampling.LANCZOS);im.paste(pic,((1080-width)//2,y))
def arrow(d,x,y,color='#16382c'):
    d.line((x,y,x+90,y),fill=color,width=9);d.polygon([(x+90,y),(x+65,y-18),(x+65,y+18)],fill=color)
def icon(d,x,y,kind,active=True):
    c='#16382c';d.rounded_rectangle((x,y,x+170,y+140),24,fill='#d3f49b' if active else '#e5eae2')
    if kind=='image':
        d.rectangle((x+30,y+25,x+140,y+110),outline=c,width=6);d.ellipse((x+105,y+40,x+123,y+58),fill=c);d.polygon([(x+40,y+98),(x+75,y+57),(x+112,y+98)],fill=c)
    elif kind=='brain':
        for a,b in [(35,40),(75,32),(105,55),(45,85),(88,90)]:d.ellipse((x+a,y+b,x+a+22,y+b+22),fill=c)
        d.line((x+55,y+55,x+87,y+45,x+115,y+65,x+100,y+100,x+58,y+95,x+55,y+55),fill=c,width=5)
    else:
        d.polygon([(x+55,y+25),(x+55,y+113),(x+78,y+88),(x+95,y+120),(x+112,y+109),(x+95,y+78),(x+132,y+78)],fill=c)

def draw(scene,idx,t,overall,caption=True):
    im=Image.new('RGB',(1080,1920),'#f6f7ef');d=ImageDraw.Draw(im)
    # Quiet editorial frame with a persistent topic marker and progress.
    d.ellipse((730,-180,1250,340),fill='#e4eed9')
    text(d,(64,96),'BENRIWORKS  /  AI UPDATE',27)
    pill(d,(64,166,1016,230),scene['label'],size=29)
    y=290+int(14*(1-min(t/.35,1)))
    for line in scene['headline']:
        fittext(d,(64,y),line,78,950);y+=112
    sid=scene['id'];u=min(1,t/.65)
    if sid=='hook':
        pill(d,(64,600,300,660),'BEFORE','#f9dbc4',28);crop_title(im,'banner-before.png',688)
        pill(d,(64,1005,300,1065),'AFTER',size=28);crop_title(im,'banner-after.png',1092)
        d=ImageDraw.Draw(im);d.rounded_rectangle((935,697,1000,900),12,outline='#d46238',width=6)
        text(d,(64,1350),'今回のAPI検証・架空の告知画像',30)
    elif sid=='launch':
        text(d,(64,590),'見る。考える。操作へ。',51)
        for j,k in enumerate(['image','brain','cursor']):
            icon(d,90+j*340,780,k,t>j*.55)
            if j<2:arrow(d,290+j*340,855)
        text(d,(96,950),'画像の理解',38);text(d,(425,950),'判断',38);text(d,(755,950),'PC操作',38)
        quote=OUT/'official-heading.png'
        if quote.exists():
            p=asset('official-heading.png');w=930;h=round(p.height*w/p.width);im.paste(p.resize((w,h)),(75,1080))
        d=ImageDraw.Draw(im);text(d,(64,1280),'引用：OpenAI公式資料',30)
        text(d,(64,1330),'2026年10月29日 確認',28)
    elif sid=='before':
        paste(im,'banner-before.png',(64,600,1016,1195));d=ImageDraw.Draw(im)
        d.rounded_rectangle((555,733,1015,841),12,outline='#d46238',width=7)
        d.line((910,841,880,1240),fill='#d46238',width=5)
        text(d,(64,1250),'Terraの実際の回答',32)
        text(d,(64,1310),'「右端からはみ出し、',42)
        text(d,(90,1370),'全文を読めません。」',42)
    elif sid=='after':
        paste(im,'banner-after.png',(64,600,1016,1195));d=ImageDraw.Draw(im)
        d.rounded_rectangle((520,727,1000,813),12,outline='#3b8463',width=6)
        pill(d,(64,1250,1016,1330),'位置 x=780 ／ 文字サイズ 60px',size=37)
        text(d,(64,1370),'提案値を制作側のコードで反映',35)
    elif sid=='workflow':
        for j,(k,title,sub) in enumerate([('image','見る','画像や画面を読み取る'),('brain','判断する','問題と修正案を整理'),('cursor','行動へ','対応ツールで操作につなぐ')]):
            yy=580+j*245;icon(d,64,yy,k,t>j*.8);text(d,(282,yy+8),title,56);text(d,(282,yy+95),sub,36)
        pill(d,(64,1350,1016,1430),'画面操作には対応ツールの設定が必要',size=34)
    elif sid=='where':
        for j,(label,desc) in enumerate([('ChatGPT Work','デスクトップ・Web・モバイル'),('Codex','提供環境・管理設定を確認')]):
            yy=610+j*290;d.rounded_rectangle((64,yy,1016,yy+230),30,fill='#16382c');text(d,(104,yy+35),label,65,fill='white');text(d,(104,yy+140),desc,35,fill='#d3f49b')
        d.rounded_rectangle((64,1240,1016,1390),28,fill='#f9dbc4');text(d,(110,1270),'通常のChatでは選べません',48)
    elif sid=='select':
        for j,(a,b) in enumerate([('01','モデル一覧を開く'),('02','Advancedを開く'),('03','GPT-6.1 Terraを選ぶ')]):
            yy=590+j*210;d.rounded_rectangle((64,yy,1016,yy+155),28,fill='#e4eed9' if j!=2 else '#d3f49b');text(d,(95,yy+43),a,42);text(d,(205,yy+43),b,46)
        text(d,(64,1280),'Plus / Pro / Business /',39);text(d,(64,1345),'Enterprise / Edu',39)
        text(d,(64,1415),'利用可否はプラン・管理者設定に依存',30)
    else:
        d.ellipse((335,610,745,1020),fill='#d3f49b');d.line((435,810,515,890,665,725),fill='#16382c',width=24)
        text(d,(94,1110),'入力画像 → 提案 → 修正 → 確認',44)
        text(d,(94,1240),'最後は、人の目でも。',57)
        text(d,(94,1340),'GPT-6.1 Terra',50)
    d=ImageDraw.Draw(im)
    if caption:
        local=max(0,t-.12);ws=[len(c.replace('、','').replace('。','')) for c in scene['captions']];s=sum(ws);at=0;cap=scene['captions'][-1]
        for c,w in zip(scene['captions'],ws):
            at+=w/s*scene['voice_seconds']
            if local<at:cap=c;break
        d.rounded_rectangle((48,1520,1032,1730),30,fill='#16382c')
        # Explicit semantic line breaks; no character-level word splitting.
        mapping={'ChatGPT Workと、Codexで利用可能。':['ChatGPT Workと、','Codexで利用可能。'],'最後は、人の目でも確かめましょう。':['最後は、人の目でも','確かめましょう。'],'プランや管理者の設定も確認を。':['プランや管理者の','設定も確認を。'],'まずは、身近な画像のチェックから。':['まずは、身近な画像の','チェックから。'],'見る、判断する、修正につなげる。':['見る、判断する、','修正につなげる。'],'架空の告知画像を、APIで確認。':['架空の告知画像を、','APIで確認。'],'モデル一覧のAdvancedから、':['モデル一覧の','Advancedから、']}
        lines=mapping.get(cap,[cap])
        for j,line in enumerate(lines):
            fittext(d,(88,1555+j*72 if len(lines)>1 else 1584),line,50,910,fill='white')
    text(d,(64,1795),'GPT-6.1 TERRA',26);text(d,(900,1795),f'{idx+1:02d}/08',26)
    d.rounded_rectangle((64,1850,1016,1858),4,fill='#dce4d6');d.rounded_rectangle((64,1850,max(66,int(64+952*overall)),1858),4,fill='#64964b')
    return im

def render(preview=False,subtitle_draft=False):
    if subtitle_draft:
        from tools.studio.longform_audio import write_pcm,music_bright
        cursor=0;scenes=[]
        for s,duration in zip(STORY['scenes'],[4,7,7,6,7,7,7,5]):
            scenes.append(dict(s,start=cursor,end=cursor+duration,frames=duration*24,voice_start=cursor+.12,voice_seconds=duration-.65));cursor+=duration
        plan=dict(fps=24,width=1080,height=1920,frames=1200,seconds=50,scenes=scenes,alignment='Subtitle/BGM layout only. Narration unavailable; phrase times are editorial estimates.')
        save(OUT/'timing-subtitle-draft.json',plan);write_pcm(OUT/'mix-bgm.wav',music_bright(50)*.8)
    else:
        plan=audio() if not (OUT/'timing.json').exists() else json.loads((OUT/'timing.json').read_text(encoding='utf-8'))
    review=OUT/'review';review.mkdir(exist_ok=True)
    for i,s in enumerate(plan['scenes']):
        draw(s,i,min(2,s['end']-s['start']),s['start']/plan['seconds']).save(review/f'scene-{i+1:02d}.png')
    sheet=Image.new('RGB',(1080,960),'#eee')
    for i in range(8):sheet.paste(Image.open(review/f'scene-{i+1:02d}.png').resize((270,480)),((i%4)*270,(i//4)*480))
    sheet.save(review/'contact-sheet.png')
    if preview:return
    video=OUT/('gpt61-terra-short-v01-subtitle-bgm.mp4' if subtitle_draft else 'gpt61-terra-short-v01.mp4')
    if video.exists():raise RuntimeError('Preserve previous video; new revision required')
    cmd=['ffmpeg','-v','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x1920','-framerate','24','-i','pipe:0','-i',str(OUT/('mix-bgm.wav' if subtitle_draft else 'mix.wav')),'-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-t',str(plan['seconds']),str(video)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for i,s in enumerate(plan['scenes']):
        for frame in range(s['frames']):
            t=frame/24;proc.stdin.write(draw(s,i,t,(s['start']+t)/plan['seconds']).tobytes())
        print(f'Rendered scene {i+1}/8',flush=True)
    proc.stdin.close();err=proc.stderr.read().decode();code=proc.wait()
    if code:raise RuntimeError(err)
    # External SRT for upload/review; identical phrase boundaries to the burn-in.
    def stamp(t):
        ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    chunks=[];n=1
    for s in plan['scenes']:
        weights=[len(c.replace('、','').replace('。','')) for c in s['captions']];cursor=s['voice_start']
        for c,w in zip(s['captions'],weights):
            end=cursor+w/sum(weights)*s['voice_seconds'];chunks.append(f'{n}\n{stamp(cursor)} --> {stamp(end)}\n{c}\n');cursor=end;n+=1
    (OUT/('subtitles-ja-bgm-draft.srt' if subtitle_draft else 'subtitles-ja.srt')).write_text('\n'.join(chunks),encoding='utf-8')
    print(json.dumps(rec(video)),flush=True)
if __name__=='__main__':
    {'voices':voices,'audio':audio,'preview':lambda:render(True),'render':render,'subtitle-draft':lambda:render(subtitle_draft=True)}[sys.argv[1]]()
