"""Editorial plates for the landscape and vertical editions. Coordinates are logical pixels."""
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE=Path(__file__).resolve().parent
FONT=HERE.parents[2]/"studio/public/template-assets/NotoSansJP-Variable.ttf"
SCALE=1.5
PAPER="#F5F1E8"
WHITE="#FFFCF5"
INK="#152E3B"
GREEN="#075E5A"
MINT="#8CDFC7"
ORANGE="#FFC07A"
BRICK="#9F4135"
LINE="#CCCBC0"
MUTED="#50676C"
NAVY="#0D2839"

@lru_cache(maxsize=180)
def font(size,weight):
    f=ImageFont.truetype(str(FONT),round(size*SCALE))
    f.set_variation_by_axes([weight])
    return f

def xy(*v):
    return tuple(round(n*SCALE) for n in v)

def box(x,y,w,h):
    return xy(x,y,x+w,y+h)

class Board:
    def __init__(self,short,media):
        self.short=short
        self.w,self.h=(720,1280) if short else (1280,720)
        self.media=media
        self.fig=media/"captures/figures"
        self.im=None
        self.d=None
        self.moves=[]
        self.assets={}
        self.clips={}
    def begin(self,color):
        self.im=Image.new("RGB",xy(self.w,self.h),color)
        self.d=ImageDraw.Draw(self.im)
        self.moves=[]
    def rect(self,b,color,r=0,outline=None):
        x,y,w,h=b
        if r: self.d.rounded_rectangle(box(x,y,w,h),radius=round(r*SCALE),fill=color,outline=outline,width=2)
        else: self.d.rectangle(box(x,y,w,h),fill=color,outline=outline,width=2)
    def text(self,x,y,label,size,weight=600,col=INK,width=None):
        f=font(size,weight)
        if width and self.d.textlength(label,font=f)>width*SCALE+2:
            raise ValueError(f"Text exceeds {width} at {size}: {label}")
        self.d.text(xy(x,y),label,font=f,fill=col,anchor="lt")
    def rule(self,x,y,w,col=LINE):
        self.rect((x,y,w,1.5),col)
    def image(self,key):
        if key not in self.assets:
            path=self.fig/(key+".png")
            if key in ("visual-chart","rules-chart"):
                path=self.media/"captures/official"/(key+".webp")
            if key.startswith("cast/"):
                path=self.media/(key+".png")
            self.assets[key]=Image.open(path).convert("RGB")
        return self.assets[key]
    def picture(self,key,b,*,fill=False,area=None,focus=(.5,.35)):
        src=self.image(key)
        if area is not None:
            l,t,r,bt=area
            src=src.crop((round(l*src.width),round(t*src.height),round(r*src.width),round(bt*src.height)))
        x,y,w,h=b
        size=xy(w,h)
        im=ImageOps.fit(src,size,method=Image.Resampling.LANCZOS,centering=focus) if fill else ImageOps.contain(src,size,method=Image.Resampling.LANCZOS)
        px,py=xy(x,y)
        self.im.paste(im,(px+(size[0]-im.width)//2,py+(size[1]-im.height)//2))
    def portrait(self,who,b,pose):
        self.picture("cast/"+("winter-pair" if who=="both" else who),b,fill=True,focus=(.5,.18))
        self.moves.append((who,b,pose))
    def header(self,category,headline,dark=False):
        ink=WHITE if dark else INK
        accent=MINT if dark else GREEN
        x=44 if self.short else 52
        mark_y=76 if self.short else 34
        self.rect((x,mark_y,4,21),accent)
        self.text(x+13,mark_y,"ChatGPT",21,800,ink)
        self.text(x+113,mark_y+2,category,15,630,accent)
        if self.short:
            for i,line in enumerate(headline.split("\n")): self.text(x,137+i*58,line,46,810,ink,620)
        else:
            self.text(x,81,headline.replace("\n",""),43,810,ink,1185)
        return x
    def footer(self):
        if self.short:
            self.rect((0,940,720,340),NAVY)
            self.rule(44,1191,615,"#385362")
        else:
            self.rect((0,577,1280,143),NAVY)
            self.rule(52,685,1176,"#385362")
    def subtitle(self,text,speaker):
        if not text: return
        accent=MINT if speaker=="female" else ORANGE
        x,y=(46,982) if self.short else (58,608)
        size=29 if self.short else 26
        self.rect((x,y+1,4,27),accent)
        for i,line in enumerate(text.split("\n")):
            self.text(x+16,y+i*(size+12),line,size,660,WHITE,594 if self.short else 1150)
    def photo(self,who,b,pose,caption=None):
        self.portrait(who,b,pose)
        if caption:
            x,y,w,h=b
            self.text(x,y+h+10,caption,15,560,MUTED,w)
    def intro(self,line,phase):
        self.begin(NAVY)
        x=44 if self.short else 52
        self.header("2026.11.23  ／  Chatタブ","",True)
        if self.short:
            self.text(x,155,"GPT-6.2が",77,850,WHITE,625)
            self.text(x,252,"チャットに登場",69,820,WHITE,630)
            self.portrait("both",(44,368,605,389),"talk")
            self.rect((44,789,5,85),MINT)
            self.text(62,792,"料金表の画像から",34,700,MINT,570)
            self.text(62,844,"条件に合う宿を選べた",32,710,WHITE,576)
        else:
            self.text(52,133,"GPT-6.2が",73,850,WHITE,540)
            self.text(52,237,"チャットに登場",58,820,WHITE,547)
            self.rect((55,366,4,87),MINT)
            self.text(75,365,"料金表の画像から",27,650,MINT,470)
            self.text(75,412,"条件に合う宿を選べた",33,760,WHITE,490)
            self.portrait("both",(605,115,621,414),"talk")
        self.footer()
    def plate(self,line,phase):
        if line["scene"]=="hero":
            self.intro(line,phase)
            return self.im.copy(),list(self.moves)
        self.begin(PAPER)
        scene=line["scene"]
        category=("OpenAI 公式発表" if scene in ("official","dates","plans","rules-chart","visual-chart") else "Web版で実演")
        sep={"picker":"チャットで選ぶには？","selected":"6.2 Instant を選択","rates":"朝食込みで比べると？","question":"画像に条件を添える","answer":"どちらを選んだ？","matha":"近い宿が外れた理由","math":"決め手は朝食代","change":"徒歩5分なら？","followup":"条件を変えた結果","dates":"11月17日と23日の違い","visual-chart":"画像を読む力は？","rules-chart":"複雑な指示を守れた割合","travel":"実際の旅行で確かめること","plans":"どのプランで使える？","end":"画像と条件を一緒に","official":"チャット向けのSol"}
        self.header(category,sep[scene])
        who=line["speaker"]
        pose="question" if scene in ("rates","change","matha","dates","criteria","question") else "answer"
        if self.short:
            main=(44,242,605,642)
            if scene in ("change","followup") and not phase:
                self.portrait(who,(44,246,605,525),pose)
                self.text(48,800,"歩けるのは5分まで？" if scene=="change" else "予算も距離も守ると？",34,740,GREEN,600)
                display=True
            else:
                display=self.content(scene,phase,main,True)
            if not display:
                self.photo(who,(45,260,602,514),pose)
            self.text(47,901,self.credit(scene),15,600,MUTED,599)
        else:
            main=(52,163,784,367)
            self.content(scene,phase,main,False)
            self.photo(who,(869,157,357,379),pose)
            self.text(53,549,self.credit(scene),15,580,MUTED,1100)
        self.footer()
        return self.im.copy(),list(self.moves)
    def credit(self,scene):
        if scene in ("rules-chart","visual-chart","official","plans"):
            return "出典　OpenAI「ChatGPT release notes」2026.11.23"
        if scene=="dates": return "出典　OpenAI　2026.11.17・11.23の発表"
        if scene in ("rates","math","matha","change","travel"): return "実演用に作成した架空の宿・料金（税込）"
        if scene=="end": return "2026.11.25　ChatGPT Web版で収録"
        return "実画面　ChatGPT Web版　2026.11.25"
    def content(self,k,p,b,vertical):
        x,y,w,h=b
        self.rect(b,WHITE,14,LINE)
        def text(dx,dy,t,sz=27,c=INK,weight=700):
            self.text(x+dx,y+dy,t,sz,weight,c,w-dx-15)
        def pic(key,dx,dy,ww,hh,**kw): self.picture(key,(x+dx,y+dy,ww,hh),**kw)
        def chip(dx,dy,t,c=GREEN):
            text(dx,dy,t,20,c,720)
        if k in ("picker","selected"):
            chip(25,26,"入力欄の右端から開く" if k=="picker" else "選択後の表示")
            if vertical:
                pic("tabs",45,86,w-90,94)
                text(35,220,"モデル名をタップ",32)
                pic("picker" if k=="picker" and not p else "selected",43,292,w-86,277)
            else:
                pic("tabs",33,79,329,83)
                pic("picker" if k=="picker" and not p else "selected",367,62,385,239)
                text(34,218,"Chat  →  入力欄",32,GREEN)
                text(34,276,"モデル名を開く",26)
        elif k=="rates":
            if vertical:
                chip(26,26,"1人・1泊の料金表")
                item="雪灯り館" if p else "駅前館"
                pic("winter-rates",16,73,w-32,408,area=(.495,.27,.977,.91) if p else (.041,.27,.488,.91))
                text(30,512,item+"の朝食",26,MUTED)
                text(30,569,"1回 600円" if p else "宿泊料金に含む",40,GREEN)
            else:
                if p: pic("winter-rates",12,16,w-24,h-30,area=(.03,.26,.98,.91))
                else: pic("winter-rates",15,7,w-30,h-14)
        elif k=="question":
            chip(25,21,"実際に送った質問")
            pic("question",20,53,w-40,h-74)
        elif k in ("answer","followup"):
            chip(25,26,"ChatGPTの回答")
            if k=="answer":
                pic("answer",20,82,w-40,140 if not vertical else 170)
                label="雪灯り館"; note="朝食2回を足して予算内"
            else:
                pic("follow-question",20,77,w-40,82 if not vertical else 100)
                if p or not vertical: pic("followup",18,152 if not vertical else 223,w-36,57 if not vertical else 83)
                label="該当なし";note="値段と徒歩の両方を照合"
            text(31,385 if vertical else 222,label,51,GREEN,830)
            text(31,494 if vertical else 302,note,25)
        elif k in ("math","matha"):
            which=k=="math"
            chip(29,28,"雪灯り館  ／  徒歩12分" if which else "駅前館  ／  徒歩3分")
            text(29,131 if vertical else 91,"10,400円 ＋ 600円" if which else "11,800円 × 2泊",43,INK,800)
            text(31,217 if vertical else 154,"宿泊1泊　　  朝食1回" if which else "朝食は料金に含む",23,MUTED)
            self.rule(x+30,y+(323 if vertical else 215),w-60)
            if p or k=="matha":
                text(30,385 if vertical else 248,"22,000円" if which else "23,600円",61,GREEN if which else BRICK,840)
                text(33,502 if vertical else 326,"2泊・朝食2回の合計" if which else "予算より1,600円高い",21)
            else:
                text(32,390 if vertical else 257,"2泊・朝食2回なら？",35,GREEN)
        elif k=="change":
            chip(29,28,"同じチャットで聞き直す")
            text(28,124 if vertical else 86,"駅から歩ける時間",30)
            text(26,215 if vertical else 146,"15分  →  5分" if p else "徒歩15分以内",55,GREEN,850)
            if vertical:
                pic("follow-question",24,376,w-48,103)
            else: pic("follow-question",24,235,w-48,75)
            text(30,535 if vertical else 324,"予算と朝食の条件は同じ",21,MUTED)
        elif k in ("visual-chart","rules-chart"):
            pic(k,12,8,w-24,h-87)
            value="47.4%  →  71.7%" if k=="visual-chart" else "62.5%  →  78.1%"
            text(24,h-73,value,34,GREEN,820)
            text(330,h-61,"GPT-6  →  GPT-6.2",20)
        elif k=="official":
            pic("release",20,16,w-40,h-95)
            text(28,h-69,"GPT-6.2 Sol　日常会話向けに調整",31,GREEN)
        elif k=="dates":
            for i,(date,title,note) in enumerate([("11.17","Work・Codex・API","Astra と Sol"),("11.23","Chat タブ","会話向けの Sol")]):
                dy=35+i*161
                text(27,dy,date,38,GREEN if i else MUTED)
                text(206,dy+1,title,34)
                text(207,dy+62,note,24,MUTED)
                if i==0: self.rule(x+27,y+dy+117,w-54)
        elif k in ("travel","plans","end"):
            if k=="travel": items=[("日付と人数","同じ条件で宿を比較"),("朝食と税金","予約先の表記と照らす")]
            elif k=="plans": items=[("Plus ・ Pro","個人向けの対象"),("Business ・ Enterprise","Enterpriseは管理者設定による")]
            else: items=[("画像を添える","金額と単位を読める大きさに"),("条件を書く","予算・優先順位・選んだ理由")]
            if vertical and k=="end":
                self.portrait("both",(x+12,y+15,w-24,332),"talk")
                text(25,401,"画像 ＋ 譲れない条件",37,GREEN,820)
                text(26,493,"「選んだ理由も一言」",31)
                return True
            for i,(title,note) in enumerate(items):
                dy=(44+i*273) if vertical else (34+i*158)
                self.rect((x+27,y+dy,5,80),GREEN if i==p else LINE)
                text(48,dy+1,title,35 if k!="plans" else 32,INK)
                text(49,dy+62,note,22,MUTED)
        return True

    def clip(self,who,pose):
        specific=self.media/"motion"/(who+"-"+("explain" if who=="male" and pose=="answer" else "think" if who=="female" and pose=="question" else pose))/"source.mp4"
        if who!="both" and specific.exists(): return specific,"both"
        pair=self.media/"motion"/("winter-study" if pose=="question" else "winter-duet")/"source.mp4"
        if pair.exists(): return pair,who
        raise FileNotFoundError("Missing filmed winter two-shot")
    def motion_frame(self,plate,moves,absolute_frame):
        for who,b,pose in moves:
            path,half=self.clip(who,pose)
            key=str(path)
            if key not in self.clips:
                cap=cv2.VideoCapture(key)
                fps=cap.get(cv2.CAP_PROP_FPS)
                if not cap.isOpened() or not fps: raise OSError(path)
                self.clips[key]=(cap,fps)
            cap,fps=self.clips[key]
            n=round(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            # Long holds retain a listening shot instead of reversing spoken gestures.
            idx=min(n-1,round(absolute_frame*fps/24))
            cache_key=(key,idx)
            if getattr(self,"last_key",None)!=cache_key:
                if round(cap.get(cv2.CAP_PROP_POS_FRAMES))!=idx: cap.set(cv2.CAP_PROP_POS_FRAMES,idx)
                ok,img=cap.read()
                if not ok:raise IOError(f"Could not decode frame {idx} of {path.name}")
                self.last_key,self.last_frame=cache_key,img
            img=self.last_frame
            if half=="male": img=img[:,:img.shape[1]//2]
            if half=="female": img=img[:,img.shape[1]//2:]
            xx,yy,bw,bh=b
            destw,desth=xy(bw,bh)
            sh,sw=img.shape[:2]
            scale=max(destw/sw,desth/sh)
            cw,ch=round(destw/scale),round(desth/scale)
            ox=(sw-cw)//2; oy=round((sh-ch)*.18)
            face=cv2.resize(img[oy:oy+ch,ox:ox+cw],(destw,desth),interpolation=cv2.INTER_LINEAR)
            sx,sy=xy(xx,yy)
            plate[sy:sy+desth,sx:sx+destw]=face
