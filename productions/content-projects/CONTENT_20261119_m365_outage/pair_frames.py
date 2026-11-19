"""Landscape and dedicated vertical compositions for the two companion edits."""
from functools import lru_cache
from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageOps

from frames import Plates
from pair_edit import COPY
from tools.studio.explainer_canvas import Canvas, box, fit

PAPER="#F4F0E7"
INK="#153137"
DARK="#102C33"
MINT="#B0EBD2"
TEAL="#006663"
CORAL="#F8A98B"
RUST="#A33D2B"
WHITE="#FFFEF6"
GRAY="#526965"
HAIR="#B6C5B9"
SOURCE_DATA={
    "status":("Microsoft","status.cloud.microsoft","11月19日撮影","現在の稼働状況を確認するページ"),
    "news":("Microsoft Ignite","news.microsoft.com","11月17日 登壇 ／ 19日撮影","サティア・ナデラ CEO の基調講演"),
    "keynote":("Microsoft Ignite 講演録","news.microsoft.com","2026年11月17日","「まだ取り組むべきことがある」（仮訳）"),
    "meiji":("明治薬科大学","my-pharm.ac.jp","11月13日案内 ／ 16日更新","入試前日、急ぎの連絡は電話へ"),
}

class Edition:
    def __init__(self,media,story,short):
        self.media,self.short=media,short
        self.w,self.h=(1080,1920) if short else (1920,1080)
        self.story=story
        self.canvas=Canvas()
        self.old=Plates(media,story)

    def t(self,im,txt,rect,size,color=INK,center=False):
        self.canvas.text(im,txt,rect,size,color,center)

    @lru_cache(maxsize=12)
    def backing(self,dark):
        im=Image.new("RGB",(self.w,self.h),DARK if dark else PAPER)
        d=ImageDraw.Draw(im)
        if dark:
            # Soft lines echo the routing diagrams and leave a clean field behind the type.
            for i in range(7):
                x=int(self.w*(.54+i*.09))
                d.line([(x,-20),(x+int(self.h*.14),int(self.h*.28)),(x+int(self.h*.56),int(self.h*.63))],fill="#17383D",width=2)
        return im

    def mast(self,im,title,dark):
        d=ImageDraw.Draw(im); fg=WHITE if dark else INK; ac=MINT if dark else TEAL
        if self.short:
            self.t(im,"Microsoft 365",(66,119,780,185),41,fg)
            self.t(im,"2026.11",(740,124,944,182),31,ac,True)
            d.line((68,193,955,193),fill=ac,width=3)
        else:
            self.t(im,"Microsoft 365",(83,44,553,112),42,fg)
            d.line((418,60,418,100),fill=ac,width=2)
            self.t(im,title,(456,47,1342,110),30,ac)
            self.t(im,"障害の記録　2026.11",(1440,50,1853,111),29,fg,True)
            d.line((85,127,1835,127),fill=ac,width=2)

    @lru_cache(maxsize=90)
    def shot(self,tag,frame,size):
        person,pose=tag.split("-")
        person="male" if person=="M" else "female"
        fp=self.media/"motion/pair"/f"{person}-{pose}"/f"{frame:03d}.jpg"
        if not fp.exists():
            fp=sorted(fp.parent.glob("*.jpg"))[-1]
        with Image.open(fp) as photo:
            # The understanding shot of the male presenter was already a close-up.
            if tag=="M-understanding": region=(0,0,640,640)
            elif person=="female":region=(105,68,545,508)
            else:region=(89,68,551,530)
            return ImageOps.fit(photo.crop(region),size,Image.Resampling.BICUBIC,centering=(.50,.31))

    def faces(self,im,areas,frame):
        d=ImageDraw.Draw(im)
        for tag,rect in areas:
            x,y,r,b=rect
            im.paste(self.shot(tag,frame,(r-x,b-y)),(x,y))
            d.rectangle((x,b-5,r-1,b-1),fill=CORAL if tag.startswith("M-") else MINT)

    def hero(self,im,frame,elapsed):
        self.mast(im,"Exchange Online 障害",True)
        if self.short:
            self.t(im,"Outlookが止まった",(68,243,965,370),85,WHITE)
            self.t(im,"3つの理由",(68,371,955,516),110,MINT)
            areas=[("M-surprise",(70,560,489,936)),("F-thinking",(503,560,923,936))]
            self.faces(im,areas,frame)
            labels=["7月の更新の不具合","Teamsの通信の移動","サーバー容量の減少"]
            for i,copy in enumerate(labels):
                y=992+99*i
                self.t(im,f"0{i+1}",(72,y,150,y+72),43,CORAL)
                self.t(im,copy,(173,y-3,927,y+76),52,WHITE)
            self.t(im,"Microsoft・11月15日付 暫定報告",(73,1316,940,1374),32,MINT)
        else:
            self.t(im,"Outlookが止まった",(84,185,1167,311),86,WHITE)
            self.t(im,"3つの理由",(82,306,1142,454),113,MINT)
            for i,copy in enumerate(["7月の更新に含まれた不具合","Teamsの通信の移動","サーバー容量の減少"]):
                y=505+92*i
                self.t(im,f"0{i+1}",(93,y,165,y+66),37,CORAL)
                self.t(im,copy,(186,y-2,1052,y+72),52,WHITE)
            self.faces(im,[("M-surprise",(1066,246,1444,719)),("F-thinking",(1456,246,1833,719))],frame)
            self.t(im,"Microsoft・11月15日付 暫定報告",(94,807,1680,858),30,MINT)

    def people(self,im,sid,mode,arg,frame):
        h,sub=COPY[sid]
        self.mast(im,"原因と影響をたどる",True)
        tags=arg.split("/")
        if self.short:
            self.t(im,h,(68,251,952,374),74,WHITE)
            if mode=="solo":
                areas=[(tags[0],(68,426,937,1170))]
            else:
                areas=[(tags[0],(68,521,487,1045)),(tags[1],(501,521,922,1045))]
            self.faces(im,areas,frame)
            self.t(im,sub,(70,1220,952,1318),42,MINT)
        else:
            if mode=="solo":
                self.faces(im,[(tags[0],(83,198,792,821))],frame)
                tx,sz=858,64
            else:
                self.faces(im,[(tags[0],(83,247,537,769)),(tags[1],(549,247,1003,769))],frame)
                tx,sz=1051,53
            self.t(im,h,(tx,312,1841,477),sz,WHITE)
            d=ImageDraw.Draw(im);d.line((tx,510,tx+125,510),fill=CORAL,width=6)
            # Intentional editorial breaks keep the spoken subtitle from competing with the headline.
            from tools.studio.editorial_captions import phrase_lines
            widths=1814-tx
            lines=phrase_lines(sub,widths,36)
            self.t(im,"\n".join(lines),(tx,550,1826,735),36,MINT)

    @lru_cache(maxsize=24)
    def source(self,key):
        location=self.media/"captures"
        path=location/(key+".png") if key.startswith("report-") or key=="exam-excerpt" else location/"revision-03"/(key+".png")
        if key=="exam-excerpt":path=location/"meiji.png"
        with Image.open(path) as pic:return pic.convert("RGB")

    def window(self,im,key,rect,domain):
        x,y,r,b=rect
        box(im,rect,"#FFFFFF",13,HAIR,3)
        d=ImageDraw.Draw(im);d.line((x+1,y+57,r-1,y+57),fill=HAIR,width=2)
        for i,c in enumerate(("#A6B8B2","#B3C8C1","#D5E0D7")):
            d.ellipse((x+22+i*20,y+25,x+31+i*20,y+34),fill=c)
        self.t(im,domain,(x+99,y+7,r-12,y+50),26,GRAY)
        fit(im,self.source(key),(x+9,y+65,r-9,b-10))

    def evidence(self,im,sid,mode,arg):
        name,url,when,sub=SOURCE_DATA[arg]
        self.mast(im,"公式の発表を読む",False)
        if self.short:
            title="今の状態を確かめる" if arg=="status" else "入試前日、大学の案内"
            self.t(im,title,(68,260,960,394),67,INK)
            self.t(im,name,(72,421,949,513),46,TEAL)
            if mode=="site":
                # In portrait, the actual source occupies the full central width.
                self.window(im,arg,(65,563,938,1112),url)
            else:
                if arg=="meiji":
                    box(im,(66,583,936,1097),"#FFFFFF",13,HAIR,3)
                    self.t(im,"大学からの案内",(96,637,904,721),38,GRAY)
                    fit(im,self.source("exam-excerpt"),(97,765,901,907))
                else:
                    src=self.source("status");w,h=src.size
                    box(im,(66,583,936,1097),"#FFFFFF",13,HAIR,3)
                    # Same shot, tighter framing of Microsoft's own logo and status heading.
                    fit(im,src.crop((0,0,int(w*.61),int(h*.58))),(97,663,902,1003))
            self.t(im,when,(70,1150,950,1228),39,TEAL)
            self.t(im,sub,(70,1245,950,1330),42,INK)
        else:
            self.t(im,name,(84,184,1750,298),73,INK)
            self.t(im,when,(89,305,1800,369),35,TEAL)
            if mode=="site":
                self.window(im,arg,(85,395,1074,827),url)
                from tools.studio.editorial_captions import phrase_lines
                lines=phrase_lines(sub,675,51)
                self.t(im,"\n".join(lines),(1143,523,1834,755),51,INK)
            elif arg=="keynote":
                box(im,(85,386,1833,833),"#FFFFFF",16,HAIR,2)
                fit(im,self.source("keynote-date"),(144,433,939,491))
                fit(im,self.source("keynote-quote"),(143,525,999,616))
                ImageDraw.Draw(im).line((167,631,977,631),fill=TEAL,width=5)
                self.t(im,sub,(146,666,1779,783),57,INK)
            elif arg=="meiji":
                box(im,(85,409,1831,811),"#FFFFFF",18,HAIR,2)
                self.t(im,"緊急の問い合わせについて",(148,442,1780,547),46,TEAL)
                fit(im,self.source("exam-excerpt"),(153,572,1739,709))
            else:
                src=self.source("status");w,h=src.size
                box(im,(85,410,1830,817),"#FFFFFF",17,HAIR,2)
                fit(im,src.crop((0,0,int(.65*w),int(.60*h))),(127,454,991,760))
                self.t(im,"11月19日の表示",(1076,486,1802,581),51,TEAL)
                self.t(im,"現在の稼働状況を確認",(1075,601,1804,730),49,INK)

    def diagram(self,im,variant,frame,phase):
        short=self.short
        self.mast(im,"ゲートウェイの動き",True)
        heads={"cascade":"回した先も、止まる。","repair":"台数をそろえて戻す。","queue":"復帰した1台に集中。","route":"受信箱を開く、その手前。"}
        self.t(im,heads[variant],(68,244,973,384) if short else (86,172,1830,304),67 if short else 75,WHITE)
        nodes=( [(252,650),(502,850),(752,1050)] if short else [(464,561),(941,561),(1421,561)] )
        d=ImageDraw.Draw(im)
        colors=[]
        for i,(x,y) in enumerate(nodes):
            stopped=(variant in ("cascade","queue") and i<=phase)
            live=(variant!="repair" or i<=phase)
            col=CORAL if stopped else MINT if live else "#64858B"
            colors.append(col)
        for i in range(2):
            ax,ay=nodes[i];bx,by=nodes[i+1]
            x1,y1,x2,y2=ax+78,ay,bx-78,by
            col=MINT if variant=="repair" else CORAL if variant in ("queue","cascade") else MINT
            d.line((x1,y1,x2,y2),fill="#496D72",width=5)
            angle=math.atan2(y2-y1,x2-x1)
            for offset in [0,.37,.69] if variant in ("cascade","queue") else [0]:
                t=(frame/24+offset)%1
                dx=x1+(x2-x1)*t;dy=y1+(y2-y1)*t
                if i<=phase or variant=="route": d.ellipse((dx-7,dy-7,dx+7,dy+7),fill=col)
            d.polygon([(x2,y2),(x2-18*math.cos(angle-.5),y2-18*math.sin(angle-.5)),(x2-18*math.cos(angle+.5),y2-18*math.sin(angle+.5))],fill=col)
        for i,((x,y),col) in enumerate(zip(nodes,colors)):
            for row in [-1,0,1]:
                yy=y+row*30
                d.rounded_rectangle((x-76,yy-12,x+76,yy+12),radius=6,fill="#234148",outline=col,width=3)
                d.ellipse((x-61,yy-4,x-53,yy+4),fill=col)
                d.line((x-36,yy,x+49,yy),fill=col,width=2)
            name=(["利用端末","入口","メール保管"] if variant=="route" else ["サーバーA","サーバーB","サーバーC"])[i]
            self.t(im,name,(x-135,y+54,x+135,y+122),34 if short else 39,WHITE,True)
        label=({"cascade":["Aが応答停止","通信がBへ集中","Cにも同じ不具合"],"queue":["復帰した直後","待機中の要求が殺到","再び応答できない"],"repair":["一部を稼働から外す","グループごとに修正","順番に復帰"],"route":["接続を要求","ゲートウェイが受ける","メールボックスへ"]})[variant][phase]
        self.t(im,label,(73,1244,951,1355) if short else (86,721,1834,843),51 if short else 58,MINT,short)

    def stat(self,im,arg):
        self.mast(im,"公式記録",False)
        if arg=="rate":
            self.t(im,"応答できなかった",(68,247,957,368),67,INK)
            self.t(im,"8割超",(61,458,954,716),181,RUST)
            self.t(im,"最悪時の、対象ゲートウェイの\nサーバーに占める割合",(75,754,946,963),49,INK)
            fit(im,self.source("report-rate-0"),(78,1002,937,1070))
            fit(im,self.source("report-rate-1"),(78,1075,937,1141))
            self.t(im,"Microsoft・11月15日付 暫定報告",(74,1230,951,1332),34,TEAL)
        else:
            self.t(im,"公式記録の影響時間",(68,250,958,377),67,INK)
            self.t(im,"23時間",(65,429,940,630),143,TEAL)
            self.t(im,"50分",(67,622,940,818),143,TEAL)
            self.t(im,"日本時間　11月13日 01:20 開始\n　　　　　11月14日 01:10 解消",(72,932,953,1132),43,INK)
            self.t(im,"Microsoft・11月15日付 暫定報告",(73,1240,948,1335),35,TEAL)

    def layout(self,i,mode,arg,number,dyn,phase,elapsed):
        scene=self.story[i];sid=scene["id"]
        if mode=="archive":return self.old.plate(i,phase).copy()
        dark=mode in ("solo","duo","hero","network")
        im=self.backing(dark).copy()
        if mode=="hero":self.hero(im,number,elapsed)
        elif mode in ("solo","duo"):self.people(im,sid,mode,arg,number)
        elif mode in ("site","extract"):self.evidence(im,sid,mode,arg)
        elif mode=="network":self.diagram(im,arg,dyn,phase)
        elif mode=="stat":self.stat(im,arg)
        elif mode=="endcard":
            self.mast(im,"復旧後の対策",False)
            self.t(im,"Microsoftが変えたこと",(84,195,1812,334),77,INK)
            for i,s in enumerate(["対象ゲートウェイの容量を追加","通信の振り分けを監視","連鎖を防ぐ制限を導入"]):
                y=383+i*133
                self.t(im,f"0{i+1}",(94,y,206,y+94),48,RUST)
                self.t(im,s,(233,y-4,1822,y+99),64,INK)
            self.t(im,"11月15日付の暫定報告で完了とされた対策",(92,795,1823,858),32,TEAL)
        else:raise ValueError(mode)
        return im

    def subtitle(self,im,caption):
        if not caption:return
        if self.short:
            box(im,(57,1410,949,1640),"#152F36",18)
            self.t(im,caption,(86,1437,921,1622),53,WHITE,True)
        else:
            box(im,(82,879,1837,1037),"#152F36",17)
            self.t(im,caption,(131,903,1785,1024),46,WHITE,True)
