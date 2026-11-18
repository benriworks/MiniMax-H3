"""Editorial plates, evidence crops and presenter framings for this incident."""
from functools import lru_cache
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from tools.studio.explainer_canvas import Canvas, box, fit

W, H = 1920, 1080
PAPER, INK, MUTED = "#F7F5EF", "#183438", "#466269"
TEAL, PALE, RUST, PEACH = "#086866", "#DFEDE7", "#A94130", "#F5E4D9"
RULE, WHITE, NIGHT = "#B7C6BF", "#FFFFFF", "#12373D"
DARK_LIGHT = "#D6EAE3"
SOURCES = {
    "PIR": "Microsoft「Preliminary Post Incident Report」  2026.11.15",
    "FEED": "Microsoft 365 サービス正常性通知  /  EX1550543・MO1550821",
    "MEIJI": "明治薬科大学  /  入試前の案内、11月16日更新",
    "RITS": "立命館大学エクステンションセンター  /  11月13日以降の案内",
    "LEMONDE": "Le Monde  /  2026.11.14、パリの広報担当者への取材",
}
TOPICS = {
    "opening":"障害の原因", "mail":"現場で起きたこと", "exam":"現場で起きたこと",
    "receipt":"現場で起きたこと", "paris":"現場で起きたこと", "where":"通信の仕組み",
    "gateway":"通信の仕組み","july":"3つの要因","labq":"3つの要因","lab":"3つの要因",
    "teams":"3つの要因","capacity":"3つの要因","cascade":"障害の広がり","eighty":"障害の広がり",
    "scopeq":"機能による違い","scope":"機能による違い","restoreq":"復旧の仕組み","queue":"復旧の仕組み",
    "fix":"復旧の仕組み","clock":"復旧の時刻","backlog":"復旧の時刻","end":"対応と対策",
}
QUESTIONS = {
    "question": ("受信箱を開けない", "返事を待つ人には、\n何が見えていた？"),
    "where": ("パソコンから見えるのは受信箱", "その奥で接続を受ける\nサーバーがある。"),
    "labq": ("7月から11月まで", "なぜ、負荷テストを\n通り抜けたのか？"),
    "scopeq": ("会議はできたのに…", "予定表だけが\n開けないことも？"),
    "restoreq": ("再起動した、その直後", "なぜ、すぐにまた\n応答が途切れた？"),
}
PORTRAITS = {*QUESTIONS, "end"}
FLOWS = {
    "gateway": [("Outlook","受信箱を開く"),("ゲートウェイ","接続を受け付ける"),("Exchange Online","メールを預かる")],
    "teams": [("別系統","Teamsの通信"),("自動で切り替え","約15時間前"),("共通の入口","Exchangeと合流")],
    "cascade": [("応答が止まる","1台が処理を続けられない"),("残りへ移す","通信を別のサーバーへ"),("連鎖する","引き受けた先も詰まる")],
    "fix": [("いったん外す","サーバーをグループ単位で"),("修正・再起動","接続処理を正常な状態へ"),("段階的に戻す","安定性を確かめて拡大")],
    "backlog": [("影響解消","11/14  01:10"),("配送待ちを処理","メールの配送期限を延長"),("最終通知","11/14  13:15")],
}
SUBFLOW = {
    "gateway":"接続できないと、奥にある受信箱を開けない。",
    "teams":"2系統のうち、一方が受け持つ通信の量と種類が変わった。",
    "cascade":"同じ量の通信を、より少ないサーバーで受ける状態に。",
    "fix":"日本時間11月13日 16:20、一部に修正を適用。安定を確認して拡大。",
    "backlog":"時刻は日本時間。滞留したメールの処理と監視は、影響解消後も続いた。",
}
CAPSIZE=46
CAPWIDTH=1616


class Plates:
    def __init__(self, media, story):
        self.media, self.story, self.canvas = media, story, Canvas()

    def text(self, im, text, rect, size, color=INK, center=False):
        self.canvas.text(im,text,rect,size,color,center)

    @lru_cache(maxsize=28)
    def source_tile(self, name):
        with Image.open(self.media/"captures"/(name+".png")) as img:
            return img.convert("RGB")

    def line(self,im,coords,color=RULE,width=3):
        ImageDraw.Draw(im).line(coords,fill=color,width=width)

    def common(self, scene):
        im=Image.new("RGB",(W,H),PAPER)
        draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,W,17), fill=TEAL)
        self.text(im,"Microsoft 365", (105,43,540,103),45,INK)
        self.line(im,(465,63,465,90),RULE,3)
        self.text(im,TOPICS[scene["id"]],(500,45,1170,104),34,TEAL)
        self.text(im,"2026年11月  /  障害の記録",(1370,45,1815,105),30,MUTED,True)
        self.line(im,(106,119,1814,119))
        self.text(im,scene["title"],(102,149,1810,256),65,INK)
        source=SOURCES[scene["sources"][0]]
        self.text(im,"出典  "+source,(110,816,1812,869),28,MUTED)
        return im

    def icon(self, im, x, y, idx, color):
        d=ImageDraw.Draw(im)
        if idx=="mail":
            d.rounded_rectangle((x,y+12,x+90,y+75),radius=7,outline=color,width=5)
            d.line([(x+3,y+17),(x+45,y+51),(x+87,y+17)],fill=color,width=5)
        elif idx=="server":
            for yy in (0,32,64):
                d.rounded_rectangle((x,y+yy,x+87,y+yy+24),radius=5,outline=color,width=4)
                d.ellipse((x+10,y+yy+8,x+18,y+yy+16),fill=color)
        elif idx=="stack":
            for yy in (4,27,50):
                d.line([(x,y+yy+17),(x+44,y+yy),(x+88,y+yy+17),(x+44,y+yy+36),(x,y+yy+17)],fill=color,width=5)
        else:
            for yy in (10,38,66):
                d.line((x,y+yy,x+50,y+yy),fill=color,width=5)
                d.ellipse((x+56,y+yy-6,x+68,y+yy+6),fill=color)

    def flows(self,im,kind,phase):
        for i,(head,body) in enumerate(FLOWS[kind]):
            x=109+i*584; live=i<=phase
            box(im,(x,316,x+530,667),PALE if live else "#EBEDE6",22)
            color=TEAL if live else MUTED
            self.icon(im,x+48,354, ("mail","server","stack")[i] if kind=="gateway" else ("stack","queue","server")[i],color)
            self.text(im,head,(x+42,458,x+495,555),49,INK)
            self.text(im,body,(x+43,562,x+510,633),34,MUTED)
            if i<2:
                x2=x+554
                ImageDraw.Draw(im).polygon([(x2-7,475),(x2+9,491),(x2-7,508)],fill=TEAL)
        if kind=="backlog":
            self.text(im,"“monitoring the backlog of email messages”",(112,682,1795,742),46,TEAL)
            self.text(im,"Microsoftの経過通知  ／  配送待ちのメールを監視していた、という意味。",(113,745,1795,802),32,MUTED)
        else:
            self.text(im,SUBFLOW[kind],(112,703,1800,786),40,TEAL)

    def network(self,im,kind,phase):
        box(im,(108,294,1812,792),WHITE,24,RULE,2)
        d=ImageDraw.Draw(im)
        if kind=="teams":
            self.text(im,"通信の経路",(145,304,850,367),33,MUTED)
            for y,label in [(427,"Teams"),(591,"Exchange")]:
                box(im,(145,y-51,538,y+52),NIGHT,14)
                self.text(im,label,(170,y-46,515,y+47),48,WHITE,True)
            self.text(im,"もう一方の入口",(1150,374,1764,478),46,MUTED,True)
            box(im,(1134,535,1764,645),PALE,16)
            self.text(im,"Exchangeと共通の入口",(1152,548,1743,632),43,TEAL,True)
            self.line(im,(541,590,1128,590),TEAL,10)
            if phase==0:
                self.line(im,(541,427,1126,427),TEAL,9)
                caption="通常の構成では、Teamsの通信は別系統でも受けられる。"
            else:
                self.line(im,(541,427,778,427,942,567,1127,567),RUST,10)
                d.polygon([(1108,553),(1130,567),(1108,581)],fill=RUST)
                caption=("Teamsの通信を切り替え。" if phase==1 else "同じ入口が、量も種類も変わった通信を処理することに。")
            self.text(im,caption,(153,690,1763,765),39,INK)
        else:
            self.text(im,"通信を別のサーバーへ振り分ける仕組み",(148,304,1772,375),39,MUTED)
            self.text(im,"利用者の通信",(151,482,585,580),52,INK)
            x0,x1=609,1090
            self.line(im,(541,528,x0,528),MUTED,6)
            self.line(im,(x0,415,x0,645),MUTED,5)
            states=([False,True,True],[False,True,True],[False,False,True])[phase]
            for j,live in enumerate(states):
                y=419+j*108; color=TEAL if live else RUST
                self.line(im,(x0,y,x1-16,y),color,4 if not live else (13 if phase>0 else 6))
                d.polygon([(x1-28,y-11),(x1-9,y),(x1-28,y+11)],fill=color)
                box(im,(x1,y-42,1739,y+42),PALE if live else PEACH,13)
                label="応答中" if live else "応答停止"
                self.text(im,f"サーバー {chr(65+j)}   ／   "+label,(x1+36,y-34,1710,y+34),38,color)
            note=("1台が応答を停止。","残るサーバーに、振り替えた通信も届く。","引き受けた先でも同じ不具合が発生。")[phase]
            self.text(im,note,(153,700,1755,773),40,INK)

    def hero(self,im,phase):
        rows=(("7月の更新", "接続処理の不具合"),("Teamsの通信が移動","入口の負荷が増加"),("別件で容量が減少","約14％が稼働外"))
        for i,(h,b) in enumerate(rows):
            x=108+i*578; box(im,(x,300,x+546,532), WHITE,19,RULE,2)
            self.text(im,h,(x+29,326,x+519,415),46,INK)
            self.text(im,b,(x+30,425,x+521,500),36,TEAL)
        box(im,(108,565,1812,779),NIGHT,23)
        self.text(im,"メールの入口で、応答停止が連鎖",(152,591,1776,744),68,WHITE)
        if phase:
            self.line(im,(153,736,153+phase*460,736),"#6BC4AF",6)

    def quote(self,im,kind):
        quotes={"lock":("報告書の原文   /   3ページ",["report-lock-0"],"複数の処理が、同じ資源の解放を待つ","ロック競合"),
                "rate":("報告書の原文   /   3ページ",["report-rate-0","report-rate-1"],"対象ゲートウェイのサーバーが分母","最悪時に8割超"),
                "wait":("報告書の原文   /   4ページ",["report-wait-0","report-wait-1"],"待機していた通信で、すぐ過負荷に","再び応答停止"),
                "meiji":("大学の告知から",["meiji"],"翌14日の入試に関する緊急連絡","明治薬科大学"),
                "rits":("大学の告知から",["rits"],"システムで予約を確認できれば有効","立命館大学")}
        label,files,desc,em=quotes[kind]
        box(im,(108,298,1812,782),WHITE,24,RULE,2)
        self.text(im,label,(162,329,1200,389),33,MUTED)
        imgs=[self.source_tile(x) for x in files]
        total=sum(x.width for x in imgs)+8*(len(imgs)-1)
        s=min(2.0,1470/total,123/max(x.height for x in imgs))
        x=166
        for src in imgs:
            tile=src.resize((round(src.width*s),round(src.height*s)),Image.Resampling.LANCZOS)
            im.paste(tile,(x,410+(123-tile.height)//2)); x+=tile.width+round(8*s)
        self.line(im,(164,572,1746,572),RULE,2)
        self.text(im,em,(165,593,1725,680),56,TEAL)
        self.text(im,desc,(165,685,1730,749),38,INK)

    def compare(self,im,kind,phase):
        if kind=="lab":
            cards=(("試験環境","少ないコア数","比較的非力な機種が中心"),("現場で判明","多いコア数","新しい機種ほど競合しやすい"))
            note="負荷テストで流す通信の組み合わせも、本番とは異なっていた。"
        else:
            cards=(("Teams のチャット・会議","別の入口へ","大半の時間、利用可能"),("予定表・メールボックス","Exchangeに依存","影響が残った機能"))
            note="同じサービスを使う人でも、操作や時刻によって見え方が違った。"
        for i,(tag,big,small) in enumerate(cards):
            x=108+i*865
            color=TEAL if i==0 else RUST
            box(im,(x,312,x+835,660),PALE if i==0 else PEACH,21)
            self.text(im,tag,(x+38,340,x+795,401),34,color)
            self.text(im,big,(x+38,425,x+795,531),65,INK)
            self.text(im,small,(x+40,548,x+805,616),38,INK)
        self.text(im,note,(110,696,1808,782),39,MUTED)

    def measure(self,im,phase):
        box(im,(108,309,1812,779),WHITE,23,RULE,2)
        self.text(im,"約14％",(162,340,694,536),125,RUST)
        self.text(im,"前日の別件で、稼働から外れていた容量",(680,379,1760,505),47,INK)
        x,y,w=165,583,1550
        ImageDraw.Draw(im).rectangle((x,y,x+w,y+49),fill=TEAL)
        ImageDraw.Draw(im).rectangle((x+w-round(.14*w),y,x+w,y+49),fill=RUST)
        self.text(im,"当該ゲートウェイのサーバー容量を100％とした概数",(165,656,1740,732),34,MUTED)

    def time(self,im,phase):
        box(im,(108,305,1812,778),NIGHT,22)
        self.text(im,"23時間50分",(167,337,1240,498),102,WHITE)
        self.text(im,"暫定報告の影響時間  /  日本時間",(172,507,1720,571),40,DARK_LIGHT)
        self.line(im,(184,620,1715,620),"#73B6AA",5)
        for x in (187,1710):
            ImageDraw.Draw(im).ellipse((x-12,608,x+12,632),fill="#9CE3C8")
        self.text(im,"11月13日  01:20  開始",(169,655,934,732),43,WHITE)
        self.text(im,"11月14日  01:10  影響解消",(1000,655,1756,732),43,WHITE,True)

    def paris(self,im):
        box(im,(109,304,1812,782),NIGHT,23)
        self.text(im,"パリの広報担当者、ラヤンさん",(170,342,1723,415),44,DARK_LIGHT)
        self.text(im,"“we were all in the same boat”",(166,437,1750,583),74,WHITE)
        self.text(im,"「みんな同じ境遇だった」（仮訳）",(170,601,1741,698),54,WHITE)
        self.text(im,"取引先も同じ障害を経験。仕事の一部は月曜へ。",(171,707,1734,763),32,DARK_LIGHT)

    def question(self,im,kind):
        box(im,(108,302,1812,783),NIGHT,22)
        if kind=="end":
            self.text(im,"暫定報告で完了とした対策",(792,357,1772,435),43,DARK_LIGHT)
            self.text(im,"容量を追加\n振り分けの監視と制限",(791,480,1764,685),59,WHITE)
            return
        top,copy=QUESTIONS[kind]
        self.text(im,top,(785,366,1748,458),43,DARK_LIGHT)
        self.text(im,copy,(783,477,1757,711),66,WHITE)

    @lru_cache(maxsize=85)
    def plate(self,i,phase):
        scene=self.story[i]; kind=scene["visual"]; im=self.common(scene)
        if kind=="hero": self.hero(im,phase)
        elif kind in PORTRAITS: self.question(im,kind)
        elif kind in {"teams","cascade"}: self.network(im,kind,phase)
        elif kind in FLOWS: self.flows(im,kind,phase)
        elif kind in {"lock","rate","wait","meiji","rits"}: self.quote(im,kind)
        elif kind in {"lab","scope"}: self.compare(im,kind,phase)
        elif kind=="capacity": self.measure(im,phase)
        elif kind=="time": self.time(im,phase)
        elif kind=="paris": self.paris(im)
        else: raise ValueError(kind)
        return im

    @lru_cache(maxsize=100)
    def portrait(self,motion,number):
        with Image.open(self.media/"motion"/motion/f"{number:03}.jpg") as image:
            crop = image.crop((0,155,480,642))
            return ImageOps.fit(crop,(579,454),Image.Resampling.LANCZOS,centering=(.50,.12))

    def frame(self,i,phase,motion_frame,caption):
        s=self.story[i]; im=self.plate(i,phase).copy()
        if s["visual"] in PORTRAITS:
            motion="female-understanding" if s["speaker"]=="female" else ("male-understanding" if s["visual"]=="scopeq" else "male-thinking")
            im.paste(self.portrait(motion,motion_frame),(124,316))
        elif s["visual"]=="hero":
            face=self.portrait("female-understanding",motion_frame)
            im.paste(ImageOps.fit(face,(253,181),Image.Resampling.LANCZOS,centering=(.5,.1)),(1539,581))
        if caption:
            box(im,(108,881,1812,1035),NIGHT,19)
            lines=caption.split("\n")
            y=905 if len(lines)>1 else 892
            self.text(im,caption,(145,y,1775,1024),CAPSIZE,WHITE,True)
        return im
