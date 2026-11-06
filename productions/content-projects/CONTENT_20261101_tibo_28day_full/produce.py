"""Horizontal full explainer: real source excerpts, animated diagrams, voice-gated duo."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,os,shutil,subprocess,sys,wave
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.text_layout import box_text_layout,visible_glyph_bbox
from tools.studio.dialogue_avatar import SpriteAtlas,PairAtlas,voice_gate
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
OUT=ROOT/'outputs/content-projects'/HERE.name
DEST=OUT/'release/v01';ASSETS=OUT/'assets';FPS=24;W=1920;H=1080
SCRIPT=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
BG='#F5F2EA';INK='#172F3E';TEAL='#087E82';BLUE='#3878D3';PURPLE='#7954B4';GOLD='#E7AC38';RED='#D94848'
AUDIT={};FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'

def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def record(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
@lru_cache(maxsize=100)
def font(size):
    f=ImageFont.truetype(str(FONT),size);f.set_variation_by_axes([650]);return f
@lru_cache(maxsize=6000)
def ink(value,size):return visible_glyph_bbox(value,font(size))
@lru_cache(maxsize=4000)
def glyph(value,size,fill):
    b=ink(value,size);im=Image.new('RGBA',(b[2]-b[0]+2,b[3]-b[1]+2));ImageDraw.Draw(im).text((-b[0],-b[1]),value,font=font(size),fill=fill);return im
def text(im,value,xy,size=46,fill=INK):
    x,y=xy
    for line in value.split('\n'):
        a=glyph(line,size,fill);im.paste(a,(round(x),round(y)),a);y+=size*1.35
def label(im,value,rect,size=44,fill=INK):
    layout=box_text_layout(value,rect,lambda s:ink(s,size),padding=5,line_gap=15)
    for a in layout['placements']:
        b=a['ink_bounds'];g=glyph(a['text'],size,fill);im.paste(g,(round(b[0]),round(b[1])),g)
    AUDIT[(value,tuple(rect),size)]=dict(text=value,rect=rect,size=size,**layout)
def box(im,rect,fill=TEAL,radius=24,outline=None,width=3):ImageDraw.Draw(im).rounded_rectangle(tuple(round(a) for a in rect),radius=radius,fill=fill,outline=outline,width=width)
def ease(x):x=min(1,max(0,x));return x*x*(3-2*x)
def arrow(im,a,b,color=TEAL,width=12):
    d=ImageDraw.Draw(im);d.line((*a,*b),fill=color,width=width);theta=math.atan2(b[1]-a[1],b[0]-a[0]);s=25
    d.polygon([b,(b[0]-s*math.cos(theta-.6),b[1]-s*math.sin(theta-.6)),(b[0]-s*math.cos(theta+.6),b[1]-s*math.sin(theta+.6))],fill=color)
def wrap(s,width=32):
    result=[]
    while len(s)>width:
        cut=width
        for mark in ['、','。','？','！']:
            pos=s.rfind(mark,5,width+1)
            if pos>=5:cut=pos+1;break
        result.append(s[:cut]);s=s[cut:]
    if s:result.append(s)
    return result

def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True);manifest=[]
    old=ROOT/'outputs/content-projects/CONTENT_20261101_tibo_28day_recap'
    for name in ['tibo-author','tibo-promise-excerpt','tibo-reset-excerpt','tibo-forecast-excerpt','official-reset-heading','official-banked-heading','usage-reset-description']:
        src=old/'assets'/(name+'.png');dst=ASSETS/src.name
        if not dst.exists():shutil.copy2(src,dst)
        assert sha(src)==sha(dst);manifest.append(dict(record(dst),kind='reused_public_excerpt',source=record(src)))
    crops=[('tibo-day27-excerpt','tibo-day27-original.png',(177,63,490,145),2,'https://x.com/thsottiaux/status/2116692529970311254'),
        ('usage-navigation','usage-settings-original.png',(64,629,336,672),0,'https://chatgpt.com/settings/usage?tab=overview'),
        ('usage-reset-description-current','usage-settings-original.png',(424,954,1161,1011),0,'https://chatgpt.com/settings/usage?tab=overview')]
    for name,raw,rect,words,url in crops:
        src=OUT/'_private/captures'/raw;dst=ASSETS/(name+'.png')
        im=Image.open(src).convert('RGB');im.crop(rect).save(dst)
        manifest.append(dict(record(dst),kind='new_public_excerpt',raw=record(src),crop_xyxy=rect,quoted_words=words,url=url,privacy='Viewer account, balances, dates, replies and engagement excluded'))
    orig=Path('C:/Users/mono_/MiniMaxH3/outputs/productions/LONG_20261026_dots_transfer_detail/v03/avatars')
    for name in ['male-atlas.png','female-atlas.png','intro-atlas.png']:
        dst=ASSETS/name
        if not dst.exists():shutil.copy2(orig/name,dst)
        manifest.append(dict(record(dst),kind='reused_approved_character_atlas',original_path=str(orig/name),original_sha256=sha(orig/name)))
    for name in ['male-understanding','female-happy','female-thinking']:
        src=old/'assets'/(name+'.mp4');dst=ASSETS/src.name
        if not dst.exists():shutil.copy2(src,dst)
        manifest.append(dict(record(dst),kind='reused_minimax_motion',source=record(src)))
        cache=OUT/'motion-cache'/name
        if not list(cache.glob('*.jpg')):
            cache.mkdir(parents=True,exist_ok=True)
            run(['ffmpeg','-v','error','-nostdin','-i',str(dst),'-vf','scale=540:-2','-q:v','2',str(cache/'%04d.jpg')])
    save(OUT/'asset-manifest.json',dict(items=manifest,private_originals_excluded=True,original_capture_width=1251,article_resolution_note='Current viewport about 1240px; no claim of native 1400px full-screen capture. Diagrams exported at 1920px.'))

def timeline(prefix=False):
    DEST.mkdir(parents=True,exist_ok=True);turns=[];cursor=0;events=[];chapters=[]
    for index,t in enumerate(SCRIPT['turns']):
        if prefix and not (OUT/'voice/v01'/t['id']/'verified.json').exists():break
        path=OUT/'voice/v01'/t['id']/'voice.wav';proof=json.loads(path.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(path)==next(f['sha256'] for f in proof['files'] if f['path'].endswith('voice.wav'))
        voice=read_voice(path);seconds=len(voice)/SR
        lead=.20;tail=.35 if t['speaker']=='male' else .6
        if t['visual'] in ['applause','closing']:tail=1.1
        frames=math.ceil((lead+seconds+tail)*FPS);end=cursor+frames/FPS
        turn=dict(t,index=index,start=cursor,end=end,frames=frames,voice_start=cursor+lead,voice_seconds=seconds,voice_path=str(path))
        chunks=[]
        for sentence in t['text'].replace('？','？|').replace('！','！|').replace('。','。|').split('|'):
            if not sentence:continue
            lines=wrap(sentence,31)
            chunks.extend('\n'.join(lines[k:k+2]) for k in range(0,len(lines),2))
        weights=[max(2,len(s.replace('\n',''))) for s in chunks];total=sum(weights);at=cursor+lead
        turn['subtitles']=[]
        for caption,weight in zip(chunks,weights):
            stop=at+seconds*weight/total;turn['subtitles'].append(dict(start=at,end=stop,text=caption));at=stop
        turns.append(turn)
        if not chapters or chapters[-1]['id']!=t['chapter']:chapters.append(dict(id=t['chapter'],title=t['chapter_title'],start=cursor))
        if t['visual']=='reset':events.append(dict(kind='reset',start=cursor+1.1))
        elif t['visual'] in ['bank','day27']:events.append(dict(kind='bank',start=cursor+1.5))
        elif t['visual'] not in ['question','applause','closing','calendar']:events.append(dict(kind='improvement',start=cursor+.4))
        if t['visual']=='calendar':
            for k in range(4):events.append(dict(kind='reset',start=cursor+.9+k*2.0))
        cursor=end
    plan=dict(title=SCRIPT['title'],fps=FPS,width=W,height=H,seconds=cursor,frames=round(cursor*FPS),chapters=chapters,turns=turns,effects=events,caption_alignment='Within each real PCM turn, sentence timings estimated by character weight; not forced word alignment.')
    if prefix:
        save(OUT/'work/timeline-prefix.json',plan);return
    save(DEST/'timeline.json',plan)
    n=round(cursor*SR);voice=np.zeros(n,dtype=np.float32)
    for t in turns:
        a=round(t['voice_start']*SR);samples=read_voice(t['voice_path']);voice[a:a+len(samples)]+=samples
    loop,meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    spans=[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in turns]
    music=default_bgm_bed(raw,cursor,spans);fx=np.zeros((n,2),np.float32)
    for e in events:
        cue=editorial_cue(e['kind'],sample_rate=SR)*.63;a=round(e['start']*SR);b=min(n,a+len(cue));fx[a:b]+=cue[:b-a]
    mix=voice[:,None]+music+fx;peak=float(np.max(np.abs(mix)));mix*=min(1,.94/max(peak,1e-8))
    write_pcm(DEST/'narration.wav',voice);write_pcm(DEST/'music-loop.wav',loop);write_pcm(DEST/'effects.wav',fx);write_pcm(DEST/'mix.wav',mix)
    save(DEST/'audio-plan.json',dict(loop=meta,bgm_settings=dict(DEFAULT_BGM_PROFILE),voices={'female':'Aoede','male':'Charon'},events=events,tts_turns=len(turns),voice_seconds=sum(t['voice_seconds'] for t in turns),mix_peak=peak))
    def stamp(x):
        z=round(x*1000);h,z=divmod(z,3600000);m,z=divmod(z,60000);s,z=divmod(z,1000);return f'{h:02}:{m:02}:{s:02},{z:03}'
    subs=[s for t in turns for s in t['subtitles']]
    (DEST/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subs))+'\n',encoding='utf-8')
    print(json.dumps(dict(seconds=cursor,turns=len(turns),voice_seconds=sum(t['voice_seconds'] for t in turns))))

class Renderer:
    def __init__(self):
        self.atlases={s:SpriteAtlas(ASSETS/f'{s}-atlas.png',s) for s in ['male','female']}
        self.pair=PairAtlas(ASSETS/'intro-atlas.png')
        self.sprites={(s,e,o,z):self.atlases[s].frame(e,o,z) for s in ['male','female'] for e in ['neutral','curious','worried','serious','pleased'] for o in [False,True] for z in [240,320,480]}
        self.motions={};self.gates={};self.base={}
        self.pics={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.name}
        for name in ['female-happy','female-thinking','male-understanding','applause']:
            files=sorted((OUT/'motion-cache'/name).glob('*.jpg'))
            if files:self.motions[name]=files
    @lru_cache(maxsize=160)
    def motion(self,name,index):return Image.open(self.motions[name][index%len(self.motions[name])]).convert('RGB')
    def picture(self,im,name,rect):
        src=self.pics[name];tile=ImageOps.contain(src,(rect[2]-rect[0],rect[3]-rect[1]),Image.Resampling.LANCZOS)
        im.paste(tile,(round((rect[0]+rect[2]-tile.width)/2),round((rect[1]+rect[3]-tile.height)/2)))
    def state(self,t,local,speaker):
        if speaker!=t['speaker']:return False
        key=t['id']
        if key not in self.gates:self.gates[key]=voice_gate(t['voice_path'])['gates']
        frame=math.floor((local-.2)*FPS)
        return self.gates[key][frame] if 0<=frame<len(self.gates[key]) else False
    def presenter(self,im,t,local,large=False):
        size=480 if large else 240;ys=290 if large else 590
        for s,x in [('male',65 if large else 54),('female',1375 if large else 1626)]:
            mood='curious' if s=='male' else 'neutral'
            if t['visual'] in ['understand','summary','closing','applause']:mood='pleased'
            if t['visual'] in ['limits','cache','check','usage']:mood='serious'
            opened=self.state(t,local,s)
            box(im,(x-5,ys-5,x+size+5,ys+size+5),BLUE if s==t['speaker'] else '#C9D5D9',radius=25)
            image=self.sprites[(s,mood,opened,size)]
            # Silent listener reacts in genuine MiniMax footage; the speaking avatar follows PCM.
            motion=None
            if s!=t['speaker']:
                if s=='female' and t['visual'] in ['bankq','question']:motion='female-thinking'
                elif s=='female' and t['visual'] in ['hero','understand']:motion='female-happy'
                elif s=='male' and t['visual'] in ['benefits','summary','cache']:motion='male-understanding'
            if motion:
                src=self.motion(motion,min(len(self.motions[motion])-1,int(local*FPS)))
                if motion=='male-understanding':src=src.crop((0,180,540,688))
                else:src=src.crop((0,75,540,min(src.height,700)))
                image=ImageOps.fit(src,(size,size),method=Image.Resampling.LANCZOS,centering=(.5,.55))
            im.paste(image,(x,ys))
    def stage(self,t):
        key=t['id']
        if key not in self.base:
            im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
            d.rectangle((0,0,W,133),fill=INK);text(im,'TIBO 28 DAYS',(46,26),31,'#78D8DA')
            text(im,t['chapter_title'],(380,36),46,'#FFFFFF')
            label(im,t['chapter']+' / 09',(1710,30,1870,92),30,'#FFFFFF')
            box(im,(32,155,1888,852),'#FFFFFF',32)
            d.rectangle((0,875,W,H),fill=INK)
            self.base[key]=im
        return self.base[key].copy()
    def cards(self,im,items,phase=3,top=340):
        cols=len(items);gap=26;width=(1200-gap*(cols-1))/cols
        for i,(title,body,color) in enumerate(items):
            height=230 if top>=590 else 280
            x=360+i*(width+gap);box(im,(x,top,x+width,top+height),'#EAF0F0' if phase<i else color)
            text(im,title,(x+24,top+28),42,'#FFFFFF' if phase>=i else INK)
            text(im,body,(x+24,top+110),35,'#FFFFFF' if phase>=i else INK)
    def draw(self,t,local):
        im=self.stage(t);d=ImageDraw.Draw(im);v=t['visual'];duration=t['end']-t['start'];frac=local/duration;phase=min(2,int(frac*3));show_pip=True
        label(im,t['caption'],(330,180,1590,265),42,TEAL)
        if v in ['hero','question','bankq','understand','limits','check']:
            self.presenter(im,t,local,True);show_pip=False
            headlines={
              'hero':('毎日改善。','なければリセット！'),
              'bankq':('その場で回復？','あとで使う分？'),
              'understand':('キャッシュ','≠ 永久メモリ'),
              'limits':('Chatの上限は別','仕事の数も、必ず2倍ではない'),
              'check':('対象・期限・残量','自分の画面で確かめる')}
            lines=headlines.get(v,tuple(wrap(t['caption'],14)))
            for k,line in enumerate(lines):label(im,line,(550,345+k*105,1370,420+k*105),48,INK)
            for dot in range(3):
                cy=670+math.sin(local*2.8-dot*.8)*8;d.ellipse((896+dot*56,cy-10,916+dot*56,cy+10),fill=[TEAL,BLUE,PURPLE][dot])
        elif v in ['benefits','summary']:
            self.cards(im,[('01 速く','返事を待つ\n時間を減らす',TEAL),('02 続けやすく','途中から\n作業しやすい',BLUE),('03 枠に余裕','拡大・回復を\n使い分ける',PURPLE)],phase)
            label(im,'自分に関係する改善から、試していこう',(360,690,1560,770),44,INK)
        elif v=='promise':
            self.picture(im,'tibo-author',(390,300,800,400));self.picture(im,'tibo-promise-excerpt',(370,420,1550,555))
            label(im,'28日間、毎日',(420,590,1500,672),70,TEAL)
            label(im,'明確な改善  または  利用枠のリセット',(360,710,1560,785),43,INK)
        elif v=='status':
            self.cards(im,[('日本時間','11月1日\n午前10時台',TEAL),('太平洋時間','10月31日\n夕方',BLUE),('確認範囲','Day27 確認\nDay28 予告',PURPLE)],phase)
            label(im,'日付のズレで「完結」を先取りしない',(360,700,1560,785),43,INK)
        elif v=='reset':
            self.picture(im,'official-reset-heading',(650,280,1270,330))
            # A hand presses a clearly illustrative reset button; no real control is clicked.
            press=ease((local-.55)/.55)*(1-ease((local-1.45)/.35));shift=(1-ease(local/.7))*400
            d.ellipse((690,445,1230,685),fill='#C9D1D0');box(im,(700,450,1220,602),INK,55)
            d.ellipse((740,355+press*22,1180,555+press*22),fill=RED,outline='#F18F83',width=5)
            label(im,'RESET',(750,375+press*22,1170,510+press*22),65,'#FFFFFF')
            d.rounded_rectangle((1130+shift,285+press*25,1430+shift,365+press*25),radius=35,fill='#EDBE9B')
            d.rounded_rectangle((1112+shift,310+press*25,1170+shift,440+press*25),radius=26,fill='#EDBE9B')
            amount=.12+.88*ease((local-1.1)/.8);box(im,(510,690,1410,742),'#E1E8E5');box(im,(518,698,518+max(16,884*amount),734),TEAL)
            label(im,'回復のイメージ：対象枠へ自動反映',(390,780,1530,834),37,INK)
        elif v=='bank':
            self.picture(im,'official-banked-heading',(600,280,1320,335))
            box(im,(460,430,760,625),PURPLE);label(im,'RESET',(460,460,760,580),52,'#FFFFFF')
            arrow(im,(800,520),(1040,520),PURPLE)
            box(im,(1100,355,1450,655),'#EBE4F4',outline=PURPLE,width=6);label(im,'あとで使う',(1100,390,1450,480),44,PURPLE)
            move=ease((local-1.15)/1.4);x=560+630*move;y=370+120*move
            box(im,(x,y,x+100,y+70),GOLD,12);label(im,'1回',(x,y,x+100,y+70),32,INK)
            label(im,'受け取るだけでは、今の枠は回復しない',(350,715,1570,790),43,INK)
        elif v=='compare':
            self.cards(im,[('自動リセット','対象の枠へ\nその場で反映',TEAL),('バンクリセット','保存して\n必要な時に使う',PURPLE)],1)
            label(im,'どちらも、契約枠の恒久的な増量ではない',(340,710,1580,790),42,INK)
        elif v=='speed':
            label(im,'Day 1  文章生成の速度',(360,290,1560,365),51,INK)
            text(im,'従来',(390,425),38,INK);text(im,'改善後',(390,570),38,INK)
            width=600*ease(local/1.4);box(im,(650,410,650+max(5,width),490),'#A6B7BE')
            width2=900*ease(local/1.4);box(im,(650,555,650+max(5,width2),635),TEAL)
            label(im,'約50%高速化',(680,680,1500,760),60,TEAL)
            text(im,'※比較の概念。仕事全体の完了時間とは別',(470,800),31,INK)
        elif v=='steer':
            self.cards(im,[('依頼','条件を伝える',BLUE),('途中で調整','追加の指示を\n伝えやすく',TEAL),('仕上げへ','次の入力も\n支援',PURPLE)],phase)
            for x in [744,1152]:arrow(im,(x,650),(x+55,650))
            label(im,'Day4：即時ステアリング ／ Day5：次の入力提案',(340,745,1580,815),37,INK)
        elif v=='context':
            for i,(x,width,tag,col) in enumerate([(400,430,'従来 272k',BLUE),(1030,480,'拡大後 500k',TEAL)]):
                box(im,(x,340,x+width,680),'#EFF3F4',outline=col,width=5);label(im,tag,(x,355,x+width,433),48,col)
                count=4 if i==0 else 8
                for n in range(count):
                    xx=x+35+(n%4)*95;yy=470+(n//4)*90;box(im,(xx,yy,xx+65,yy+75),'#FFFFFF',6,outline=col,width=2)
                    for k in range(3):d.line((xx+12,yy+18+k*15,xx+52,yy+18+k*15),fill=col,width=3)
            arrow(im,(855,510),(995,510));label(im,'一度に参照する範囲。永久保存の話ではない',(340,730,1580,810),42,INK)
        elif v=='ux':
            self.cards(im,[('Day 9','ディスク使用量\n約60%削減',TEAL),('Day 11','混雑エラー削減\n自動再開',BLUE),('Day 14','過去メッセージ\nの編集',PURPLE)],phase)
            label(im,'軽くする・止まりにくくする・直しやすくする',(350,715,1570,795),41,INK)
        elif v=='cache':
            box(im,(425,350,1495,450),'#D8E5E5');label(im,'前の作業で処理した部分',(425,350,1495,450),45,INK)
            arrow(im,(960,490),(960,560));box(im,(425,600,1495,715),TEAL);label(im,'同じ部分を、再利用しやすく',(425,600,1495,715),50,'#FFFFFF')
            label(im,'Day12・16：キャッシュの改善 ≠ 永久メモリ',(340,770,1580,830),38,PURPLE)
        elif v=='late':
            self.cards(im,[('Day 19','CLI・dots\nの改善',TEAL),('Day 22','Terra\n追加',BLUE),('Day 24','メッセージ連絡\n米国Proの試験',PURPLE)],phase)
            label(im,'提供地域・プラン・順次反映の条件も確認',(340,715,1580,795),43,INK)
        elif v=='tiers':
            for row,(name,before,after,col) in enumerate([('Pro 100 / 500','従来','2倍',TEAL),('Pro 200：低い枠','低い枠','2倍',BLUE),('Pro 200：高い枠','高い枠','据え置き',PURPLE)]):
                y=315+row*137;text(im,name,(365,y+23),38,INK)
                width=240 if row!=2 else 480;box(im,(900,y,900+width,y+72),'#D8E1E4',12)
                if phase>=row:box(im,(900,y+76,1380,y+110),col,10)
                label(im,after,(1400,y,1580,y+110),42,col)
            label(im,'Work・Codex枠の比較。絶対量や仕事の件数ではない',(335,770,1585,830),36,INK)
        elif v=='mobile':
            for x,name,col in [(510,'仕事用',TEAL),(1100,'個人用',PURPLE)]:
                box(im,(x,310,x+270,700),INK,40);box(im,(x+14,332,x+256,677),'#EEF2F2',28)
                d.ellipse((x+90,375,x+180,465),fill=col);label(im,name,(x+20,505,x+250,580),44,col)
                label(im,'会話・記憶・契約',(x-65,730,x+335,790),31,INK)
            arrow(im,(825,450),(1050,450),BLUE);arrow(im,(1050,540),(825,540),BLUE)
            text(im,'2アカウントを切り替え。情報はそれぞれ別',(450,810),33,INK)
        elif v=='calendar':
            # Calendar deliberately distinguishes forecasts instead of claiming verified receipt counts.
            resets={2,6,8,10,13,15,17,18,20,21,23};banks={3,27,28}
            for day in range(1,29):
                col=PURPLE if day in banks else RED if day in resets else TEAL
                x=370+(day-1)%7*165;y=305+(day-1)//7*112
                box(im,(x,y,x+146,y+92),col,15);label(im,str(day),(x,y,x+146,y+92),42,'#FFFFFF')
                if day in [18,20,28]:text(im,'予告',(x+70,y+65),20,'#FFFFFF')
            text(im,'改善',(450,790),34,TEAL);text(im,'リセット関連',(720,790),34,RED);text(im,'バンク関連',(1100,790),34,PURPLE)
        elif v=='day27':
            self.picture(im,'tibo-day27-excerpt',(420,300,980,550));box(im,(1050,335,1490,540),PURPLE)
            label(im,'Day27：付与報告',(1050,345,1490,435),36,'#FFFFFF');label(im,'Banked 1/2',(1050,440,1490,520),42,'#FFFFFF')
            self.cards(im,[('本人の投稿','付与報告を確認',TEAL),('自分の口座','使用量で確認',BLUE),('Day 28','まだ未発表',PURPLE)],2,top=595)
        elif v=='usage':
            self.picture(im,'usage-navigation',(430,295,940,390));self.picture(im,'usage-reset-description-current',(360,450,1560,555))
            self.cards(im,[('1 対象','どの枠が\n回復する？',TEAL),('2 期限','いつまで\n使える？',BLUE),('3 残量','今、必要？',PURPLE)],phase,top=590)
            show_pip=False
        elif v in ['applause','closing']:
            source=Image.new('RGB',(1250,590),'#0D1C35') if local<4.8 else self.pair.frame(t['speaker'] if self.state(t,local,t['speaker']) else None)
            tile=Image.new('RGB',(1250,555),'#0D1C35')
            fitted=ImageOps.contain(source,(1250,555),method=Image.Resampling.LANCZOS)
            tile.paste(fitted,((1250-fitted.width)//2,(555-fitted.height)//2))
            im.paste(tile,(335,282));show_pip=False
            if local<4.8:
                for name,x in [('male-understanding',365),('female-happy',1135)]:
                    raw=self.motion(name,min(len(self.motions[name])-1,int(local*FPS)))
                    raw=raw.crop((0,180,540,688)) if name=='male-understanding' else raw.crop((0,75,540,min(raw.height,700)))
                    shot=ImageOps.fit(raw,(420,430),method=Image.Resampling.LANCZOS,centering=(.5,.55));im.paste(shot,(x,390))
            for k in range(32):
                a=k*2.39996;rad=180+(k%7)*70;x=960+math.cos(a+local*.3)*rad;y=535+math.sin(a+local*.3)*rad*.5
                if 650<x<925 and 285<y<535 or 1010<x<1300 and 350<y<605:continue
                r=4+8*(.5+.5*math.sin(local*4+k));d.line((x-r,y,x+r,y),fill='#FFD978',width=3);d.line((x,y-r,x,y+r),fill='#FFD978',width=3)
        else:raise ValueError(v)
        if show_pip:self.presenter(im,t,local)
        # Source-specific attribution; excerpts remain short, private originals never enter the output.
        source='出典：Tibo @thsottiaux / OpenAI公式　確認：2026/11/1 JST'
        if v in ['reset','bank','compare','usage','check']:source='出典：OpenAI「How resets work in Codex」 / 実画面の説明用切り出し'
        text(im,source,(48,846),24,'#536B76')
        sub=next((s['text'] for s in t['subtitles'] if s['start']<=t['start']+local<s['end']),None)
        if sub:
            lines=sub.splitlines();height=len(lines)*57;top=906 if len(lines)>1 else 934
            for k,line in enumerate(lines):label(im,line,(145,top+k*57,1775,top+54+k*57),43,'#FFFFFF')
            box(im,(45,927,112,995),BLUE if t['speaker']=='male' else PURPLE,13);label(im,'男' if t['speaker']=='male' else '女',(45,927,112,995),35,'#FFFFFF')
        # Persistent timeline and chapter progress.
        group=[s for s in SCRIPT['turns'] if s['chapter']==t['chapter']];position=next(i for i,s in enumerate(group) if s['id']==t['id'])
        progress=(int(t['chapter'])-1+(position+frac)/len(group))/9
        d.rectangle((0,1071,round(progress*W),1079),fill='#59CBCE')
        return im

def cache_applause():
    proof=json.loads((OUT/'motions/v03/applause/verification.json').read_text(encoding='utf-8'))
    approval=json.loads((OUT/'motions/v03/applause/visual-review.json').read_text(encoding='utf-8'))
    assert approval['usable'] and approval['video_sha256']==proof['artifact']['sha256']
    src=ROOT/proof['artifact']['path'];assert sha(src)==proof['artifact']['sha256']
    dst=ASSETS/'duo-applause-v01.mp4'
    if not dst.exists():shutil.copy2(src,dst)
    cache=OUT/'motion-cache/applause'
    if not list(cache.glob('*.jpg')):
        cache.mkdir(parents=True,exist_ok=True);run(['ffmpeg','-v','error','-nostdin','-i',str(src),'-vf','scale=1024:576','-q:v','2',str(cache/'%04d.jpg')])

def render(samples_only=False,prefix=False):
    plan=json.loads(((OUT/'work/timeline-prefix.json') if prefix else DEST/'timeline.json').read_text(encoding='utf-8'));r=Renderer();r.plan=plan
    shots=DEST/'shots';shots.mkdir(exist_ok=True);qc=DEST/'qc';qc.mkdir(exist_ok=True)
    turns=plan['turns']
    for t in turns:
        thumb=r.draw(t,(t['end']-t['start'])*.6);thumb.save(qc/(t['id']+'.jpg'),quality=92)
        if samples_only:continue
        dest=shots/(t['id']+'.mp4')
        if dest.exists():
            proof=dest.with_suffix('.json')
            if not proof.exists() or json.loads(proof.read_text())['sha256']!=sha(dest):raise RuntimeError('Unverified prior segment; preserve and inspect')
            if json.loads(proof.read_text())['renderer_sha256']!=sha(Path(__file__)):raise RuntimeError('Renderer changed; existing shots need a new release version')
            continue
        args=['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart',str(dest)]
        with dest.with_suffix('.log').open('wb') as log:
            proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for frame in range(t['frames']):proc.stdin.write(r.draw(t,frame/FPS).tobytes())
            finally:proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('Segment encoding failed')
        probe=json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',str(dest)]).stdout)['streams'][0]
        assert int(probe['nb_frames'])==t['frames'];save(dest.with_suffix('.json'),dict(record(dest),frames=t['frames'],script_sha256=sha(HERE/'script-v01.json'),renderer_sha256=sha(Path(__file__))))
        print(json.dumps(dict(rendered=t['id'],seconds=t['end']-t['start'])),flush=True)
    save(DEST/'label-layout-audit.json',list(AUDIT.values()))
    if samples_only or prefix:return
    listing=DEST/'concat.txt';listing.write_text('\n'.join("file '"+(shots/(t['id']+'.mp4')).as_posix()+"'" for t in turns),encoding='utf-8')
    raw=DEST/'picture.mp4'
    if not raw.exists():run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)])
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(DEST/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);filt=f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={meter['input_i']}:measured_TP={meter['input_tp']}:measured_LRA={meter['input_lra']}:measured_thresh={meter['input_thresh']}:offset={meter['target_offset']}:linear=true"
    video=DEST/'tibo-28day-full-v01.mp4'
    if not video.exists():run(['ffmpeg','-v','error','-nostdin','-n','-i',str(raw),'-i',str(DEST/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filt,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(plan['seconds']),'-movflags','+faststart',str(video)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(video),'-f','null','-'])
    meta=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]).stdout);stream=next(s for s in meta['streams'] if s['codec_type']=='video')
    assert (stream['width'],stream['height'],stream['avg_frame_rate'],int(stream['nb_frames']))==(W,H,'24/1',plan['frames'])
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(video),'-af','loudnorm=print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);assert -18<float(meter['input_i'])<-14 and float(meter['input_tp'])<=-1
    save(DEST/'verification.json',dict(record(video),seconds=plan['seconds'],width=W,height=H,fps=FPS,frames=plan['frames'],full_decode=True,loudness=meter,new_local_minimax_shot=False,new_h3_attempts=3,new_h3_adopted=0,reused_minimax_motion=3,cpu_authored_animation=True,tts_turns=len(turns),user_approved=False,human_listening=False,mobile_playback=False,published=False))
    print(json.dumps(dict(video=str(video),seconds=plan['seconds'],bytes=video.stat().st_size,loudness=meter['input_i'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','timeline','samples','render','render-ready','cache-applause']);a=p.parse_args()
    if a.command=='samples':render(True)
    elif a.command=='cache-applause':cache_applause()
    elif a.command=='render-ready':timeline(True);render(prefix=True)
    else:globals()[a.command]()
