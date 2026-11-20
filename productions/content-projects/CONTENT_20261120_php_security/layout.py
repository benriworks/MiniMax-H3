"""Two native layouts for the PHP comparison. Coordinates are measured at delivery size."""
from functools import lru_cache

from PIL import Image, ImageDraw, ImageOps
from voice import OUT
from tools.studio.explainer_canvas import Canvas, box, fit, glyph

PAPER, INK, MUTED = "#F1F5F5", "#162D3D", "#435C67"
DARK, WHITE, ICE, TEAL = "#122F40", "#FFFFFF", "#DBEFEA", "#08695E"
WARM, RUST, RULE = "#F9E9D7", "#94461D", "#ADC2C7"
SOFT="#D0E3E7"
DATES = ("10月21日", "11月19日")
VERSION = [("8.2","8.2.35","8.2.36"),("8.3","8.3.36","8.3.37"),
           ("8.4","8.4.27","8.4.28"),("8.5","8.5.12","8.5.13")]
QUESTIONS = {
    "source-where":"うちのPHPは\nどこから入れた？",
    "source-remi-q":"同じOSでも\nRemiから入れたら？",
    "again":"先月更新した\nうちのサイトも？", "full-again":"先月更新したのに\nまた対応が必要？",
    "oct-question":"前回、何が\n問題だった？", "nov-q":"深刻度は同じ。\n影響も同じ？",
    "session-q":"「使い方」って\nどういうこと？", "host-q":"予約サイトの更新を\n任せている場合は？",
    "session-distinct":"同じ画面でも\n保存方法が違う", "vendor":"OSの配布元の\n番号と照合する",
}
QUOTES = {
    "october":("PHP 開発チーム","2026.10.21","Webで動くPHPに","広く緊急更新を要請"),
    "conditions":("PHP セキュリティチーム","2026.11.18 の予告","重大な問題は","設定・構成に条件"),
    "ipa":("IPA（情報処理推進機構）","2026.11.19 の事前案内","初期設定との違いや","運用構成を確認"),
    "november":("PHP 開発チーム","2026.11.19 の公開記録","11月分の修正版を公開","同じ系列の更新を確認"),
}
# Each visual answers one operational question. The short has its own vertically stacked layout.
CARDS = {
 "named-compare":("今回の違いは、影響を受ける条件",[
   ("10月21日","Webで動くPHP","広く緊急更新を呼びかけ"),
   ("11月19日","設定や利用構成に依存","重大な問題ごとに条件が異なる")],"出典　PHP 開発チーム・セキュリティチーム"),
 "save-example":("例　買い物かごの情報をどこに保存？",[
   ("あるサイト","ファイルに保存","サーバー上に状態を記録"),
   ("別のサイト","DBに保存","アプリが選んだ保存方式")],"PHPセッションの保存方法の例 ／ 該当条件は個別告知で確認"),
 "named-routes":("同じOSでも、PHPの配布元を確かめる",[
   ("Red Hat 標準","対象製品と修正情報","Red Hat Customer Portal"),
   ("Remi から導入","11月19日の配布記事","Remi’s RPM repository")],"Red Hat・Remiの公開資料 ／ 2026年11月21日確認"),
 "backport-card":("Red Hatの修正版をどう見分ける？",[
   ("バックポート","元の版に修正を追加","先頭のPHP番号が同じ場合もある"),
   ("照合するもの","リリース番号まで","自社のパッケージと告知を照合")],"出典　Red Hat「Security Backporting Practice」"),
 "compare":("運用者が最初に見るところ",[
   ("10月21日","Webで動くPHP","広い範囲に緊急更新を要請"),
   ("11月19日","設定と使い方","重大な問題ごとに条件を確認")],"出典　PHP 開発チーム・セキュリティチーム"),
 "web":("問い合わせフォームが届くまで",[
   ("閲覧者","フォームを送る","ブラウザー"),
   ("サイトの裏側","PHPが処理","サーバー"),
   ("閲覧者","結果が届く","完了画面")],"PHP 公式マニュアル ／ フォームの例"),
 "octimpact":("10月に開発元が示したリスク",[
   ("対象","Webリクエストを処理","PHPを使うWeb環境を広く含む"),
   ("影響","遠隔からコード実行","ログイン前にも可能性")],"出典　PHP 公式セキュリティ告知・10月21日"),
 "routes":("更新を担当するのは誰？",[
   ("委託・レンタル","契約先に聞く","サービス・プランを伝える"),
   ("自社で運用","配布元を確認","公式配布かOSパッケージか")],"運用例　サイトごとに担当を確認"),
 "session":("買い物かごが覚えているもの",[
   ("商品ページ","りんごを追加","1個を選ぶ"),
   ("次のページ","かごに残る","前の選択を引き継ぐ")],"仕組みの例　状態を引き継ぐ「セッション」"),
 "sessionfile":("保存が途中で途切れた場合",[
   ("ふだんの役割","状態を保存する","次の画面へ引き継ぐ"),
   ("11月の修正例","保存処理の不具合","CVE-2026-126714")],"出典　PHP 開発元の個別告知"),
 "twoshops":("同じ買い物かごでも",[
   ("表の画面","商品・個数を表示","利用者に見える部分"),
   ("サーバーの中","状態をどう保存？","管理者が構成を確認")],"保存方式・アプリにより個別の適用条件が異なる"),
 "timeline":("前回の動画の続き",[
   ("10月21日","PHP2Shell","2件の緊急修正"),
   ("10月23日","追加の告知","別のセッション問題"),
   ("11月19日","修正版を公開","別件の正式修正も収録")],"出典　PHP 公式告知・php-src"),
 "timeline2":("10月23日に予告した別件",[
   ("10月23日","条件を案内","設定とアプリの組み合わせ"),
   ("11月19日","正式に修正","CVE-2026-115560")],"出典　PHP 公式告知・php-src"),
 "linked":("10月に出た2つの告知を区別",[
   ("PHP2Shell","10月21日の2件","CVE-2026-109618・109619"),
   ("追加の別件","アップロード進捗","CVE-2026-115560")],"出典　PHP 開発チーム"),
 "oldversion":("手元の更新記録を読む",[
   ("10月の記録","PHP 8.4.27","10月21日の2件に対応"),
   ("次に照らす先","11月の公式表","同じ8.4系の行を探す")],"公式配布版での例"),
 "vendor":("OSのパッケージで使う場合",[
   ("配布元の案内","対象パッケージ","修正済みの版を確認"),
   ("自社の環境","導入済みの版","配布元の完全な番号と照合")],"配布元による修正の取り込み（バックポート）を考慮"),
 "reply":("契約先から返答を受けたら",[
   ("適用済み","適用日を控える","対象サイトとプランを照合"),
   ("適用予定","日程を控える","利用者側の作業も確認")],"問い合わせ例 ／ 実在のサービスの対応状況を表すものではありません"),
 "checks":("自社運用の予約サイトなら",[
   ("検証環境","更新して試す","ログイン・予約完了を確認"),
   ("本番環境","修正を適用","稼働する版を再確認")],"運用例　提供元の手順に従う"),
 "confirm":("更新記録に残すもの",[
   ("対象","サイトと管理先","どこを誰が管理するか"),
   ("証跡","稼働する版・適用日","更新後の動作も確認")],"運用例　予約サイト"),
}

@lru_cache(maxsize=150)
def portrait(clip, number, width, height):
    with Image.open(OUT/"motion"/clip/f"{number+1:03d}.jpg") as img:
        # The existing winter sources include large headroom. Preserve eyes, knit and hands.
        bounds=(30,158,630,892) if clip=="male-question" else (45,228,595,852)
        if clip=="male-nod": bounds=(45,249,595,873)
        tile=ImageOps.fit(img.crop(bounds),(width,height),Image.Resampling.LANCZOS,centering=(.5,.30))
    return tile
@lru_cache(maxsize=4)
def source_image(key):
    with Image.open(OUT/"captures/quotes"/f"{key}.png") as im: return im.convert("RGB")
def rule(im,xy,color=RULE,width=2):
    ImageDraw.Draw(im).line(xy,fill=color,width=width)

class Editor:
    def __init__(self,kind,*,named_sources=False):
        self.short=kind=="short"
        self.named_sources=named_sources
        self.w,self.h=(1080,1920) if self.short else (1920,1080)
        self.l,self.r=(68,938) if self.short else (84,1836)
        self.t,self.b=(337,1360) if self.short else (202,824)
        self.caption=(56,1443,959,1653) if self.short else (84,899,1836,1043)
        self.size=47 if self.short else 45
        self.canvas=Canvas()
    def tx(self,im,value,rect,size,color=INK,center=False):
        self.canvas.text(im,value,rect,size,color,center=center)
    def centered(self,im,lines,rect,size,color=INK,left=False):
        l,t,r,b=rect
        chunks=lines.split("\n")
        heights=[glyph(s,size,color).height for s in chunks]; gap=round(size*.26)
        y=round((t+b-sum(heights)-gap*(len(heights)-1))/2)
        if y<t: raise ValueError(("multiline height",lines,rect,size))
        for s,h in zip(chunks,heights):
            self.tx(im,s,(l,y,r,y+h),size,color,not left);y+=h+gap
    def frame(self,ch,view,line_key,motion,phase,caption):
        im=Image.new("RGB",(self.w,self.h),PAPER)
        l,r,t,b=self.l,self.r,self.t,self.b
        y=105 if self.short else 29
        self.tx(im,"PHP   /   セキュリティ更新",(l,y,r,y+52),32,TEAL)
        date="2026.11.19"
        tile=glyph(date,30,MUTED)
        im.paste(tile,(r-tile.width,y+14),tile)
        rule(im,(l,y+70,r,y+70))
        self.tx(im,ch["title"],(l,y+(88 if self.short else 78),r,t-9),62 if self.short else 63,INK)
        if view in ("lead","close","question","duoask","guide-person"):
            self.people(im,view,line_key,motion)
            footer="PHP公式・2026年11月19日公開分" if view!="close" else "自社運用は配布元、委託は契約先へ"
        elif view in QUOTES:
            footer=self.quote(im,view)
        elif view in PROVIDER_FIGURES:
            footer=self.provider_figure(im,view)
        elif view=="counts":
            self.counts(im);footer="PHP開発元（php-src）／11月19日UTC公表分"
        elif view in ("versions","versionsfocus"):
            self.versions(im,view=="versionsfocus");footer="PHP 公式配布版 ／ 2026年11月19日"
        elif view in ("host","named-host"):
            self.host(im,providers=view=="named-host");footer="予約サイトの管理者から契約先への問い合わせ例"
        elif view in ("web","session","twoshops","routes","checks") and not self.short:
            label,rows,footer=CARDS[view];self.diagram(im,view,label,rows,phase)
        else:
            label,rows,footer=CARDS[view];self.cards(im,label,rows,phase)
        self.tx(im,footer,(l,b+9,r,self.caption[1]-12),24 if self.short else 25,MUTED)
        a,y,e,z=self.caption
        box(im,(a,y,e,z),DARK,22)
        if caption:
            self.centered(im,caption,(a+30,y+10,e-30,z-10),self.size,WHITE)
        return im
    def people(self,im,view,key,motion):
        l,t,r,b=self.l,self.t,self.r,self.b
        question=view in ("question","duoask","guide-person")
        if self.short:
            stage=(l,t,r,t+405); faces=(l,t+428,r,b)
        else:
            stage=(l,t,l+850,b);faces=(l+880,t,r,b)
        x,y,e,z=stage
        box(im,stage,DARK,24)
        if view=="lead":
            november = "設定・使い方で差" if self.named_sources else "設定・構成で差"
            for i,(tag,words) in enumerate((("10月","広く緊急更新"),("11月",november))):
                top=y+i*(z-y)//2
                self.tx(im,tag,(x+38,top+15,e-30,top+83),36,SOFT if i==0 else "#91DCCA")
                self.tx(im,words,(x+38,top+87,e-32,top+(z-y)//2-10),69 if self.short else 85,WHITE)
                if i==0:rule(im,(x+38,y+(z-y)//2,e-38,y+(z-y)//2),"#53707B")
        else:
            eyebrow="判断のポイント" if view=="guide-person" else ("次に確認すること" if view=="close" else "運用担当者の疑問")
            label="11月分の適用日を\n管理先に確認" if view=="close" else QUESTIONS.get(key,"前回と何が違う？")
            self.tx(im,eyebrow,(x+36,y+32,e-28,y+98),34,"#91DCCA")
            self.centered(im,label,(x+36,y+102,e-28,z-27),66 if self.short else 71,WHITE,True)
        a,v,f,w=faces
        if view=="guide-person":
            self.person(im,"female-concern" if key=="session-distinct" else "female-guide",motion,faces)
        elif question and view=="question":
            # The question take moves closer; use a single frame covering chest and gesturing hand.
            self.person(im,"male-question",motion,faces)
        else:
            mid=(a+f)//2
            self.person(im,"male-nod",motion if view=="close" else min(40,motion//2),(a,v,mid-5,w))
            self.person(im,"female-concern" if view=="duoask" else "female-guide",motion if view!="close" else min(35,motion//2),(mid+5,v,f,w))
    def person(self,im,clip,motion,rect):
        x,y,r,b=rect
        im.paste(portrait(clip,motion,r-x,b-y),(x,y))
    def quote(self,im,key):
        org,date,line1,line2=QUOTES[key]
        if self.named_sources and key=="ipa":
            line1,line2="影響はPHPの設定や","利用構成に依存"
        l,t,r,b=self.l,self.t,self.r,self.b
        mid=t+round((b-t)*.53)
        box(im,(l,t,r,mid-15),WHITE,22,outline=RULE,width=2)
        self.tx(im,org,(l+33,t+20,r-30,t+92),34,TEAL)
        source=source_image(key)
        fit(im,source,(l+28,t+112,r-28,mid-38))
        box(im,(l,mid,r,b),DARK,22)
        self.tx(im,"公式発表の要点",(l+36,mid+21,r-22,mid+88),32,"#91DCCA")
        self.centered(im,line1+"\n"+line2,(l+35,mid+97,r-35,b-27),68 if self.short else 63,WHITE,True)
        return f"引用　{org}  ／  {date}"

    def provider_figure(self,im,key):
        org, heading, advice, credit = PROVIDER_FIGURES[key]
        l,t,r,b=self.l,self.t,self.r,self.b
        photo=key=="redhat-photo"
        source=provider_image(key)
        if self.short:
            middle=t+int((b-t)*.55)
            art=(l,t,r,middle-12); words=(l,middle,r,b)
        elif photo:
            split=l+int((r-l)*.51)
            art=(l,t,split-10,b); words=(split+10,t,r,b)
        else:
            middle=t+int((b-t)*.48)
            art=(l,t,r,middle-9); words=(l,middle+7,r,b)
        x,y,e,z=art
        box(im,art,WHITE,18,outline=RULE,width=2)
        if photo:
            fit(im,source,(x+8,y+8,e-8,z-8))
        else:
            self.tx(im,org,(x+27,y+12,e-25,y+80),36,TEAL)
            fit(im,source,(x+32,y+95,e-32,z-25))
        x,y,e,z=words
        box(im,words,DARK,18)
        self.tx(im,org if photo else "この告知で分かること",(x+36,y+17,e-30,y+86),35,"#91DCCA")
        self.centered(im,heading,(x+35,y+94,e-31,z-107),58 if self.short else 60,WHITE,True)
        self.tx(im,advice,(x+35,z-96,e-30,z-26),32,"#CDE7E5")
        return credit
    def cards(self,im,label,rows,phase):
        l,t,r,b=self.l,self.t,self.r,self.b
        self.tx(im,label,(l,t+2,r,t+80),42 if self.short else 46,MUTED)
        n=len(rows); gap=16; top=t+110
        for i,(tag,headline,detail) in enumerate(rows):
            if self.short:
                step=(b-top+gap)//n; x,y,e,z=l,top+i*step,r,top+(i+1)*step-gap
            else:
                step=(r-l+gap)//n;x,y,e,z=l+i*step,top,l+(i+1)*step-gap,b
            active=i==min(phase,n-1)
            box(im,(x,y,e,z),ICE if active else WHITE,22,outline=TEAL if active else RULE,width=3)
            inset=28
            self.tx(im,tag,(x+inset,y+16,e-inset,y+92),32,TEAL if active else MUTED)
            self.centered(im,headline,(x+inset,y+87,e-inset,z-81),56 if self.short else (50 if n==3 else 63),INK,True)
            self.tx(im,detail,(x+inset,z-74,e-inset,z-20),32 if self.short else (28 if n==3 else 34),MUTED)

    def diagram(self,im,view,label,rows,phase):
        l,t,r,b=self.l,self.t,self.r,self.b
        self.tx(im,label,(l,t+2,r,t+80),46,MUTED)
        symbols={"web":("form","server","done"),"session":("apple","cart"),
                 "twoshops":("cart","server"),"routes":("host","server"),"checks":("form","done")}[view]
        n=len(rows);gap=58;step=(r-l+gap)//n
        for i,((tag,headline,detail),symbol) in enumerate(zip(rows,symbols,strict=True)):
            x=l+i*step;e=l+(i+1)*step-gap;y=t+100;active=i==phase
            box(im,(x,y,e,b),ICE if active else WHITE,22,outline=TEAL if active else RULE,width=3)
            self.tx(im,tag,(x+27,y+20,e-25,y+83),34,TEAL)
            icon=make_symbol(symbol);im.paste(icon,((x+e-icon.width)//2,y+89),icon)
            self.tx(im,headline,(x+15,y+296,e-15,b-90),54,INK,True)
            self.tx(im,detail,(x+13,b-81,e-13,b-22),34,MUTED,True)
            if i<n-1 and view not in ("routes","twoshops"):
                cy=(y+b)//2
                ImageDraw.Draw(im).polygon([(e+11,cy-15),(e+41,cy),(e+11,cy+15)],fill=TEAL)
    def counts(self,im):
        l,t,r,b=self.l,self.t,self.r,self.b
        box(im,(l,t,r,b),WHITE,24,outline=RULE,width=2)
        self.tx(im,"11月19日付の開発元の告知",(l+37,t+28,r-25,t+105),41,INK)
        if self.short:
            cards=[(l+32,t+150,r-32,t+450),(l+32,t+470,r-32,t+770)]
        else:
            mid=(l+r)//2;cards=[(l+30,t+130,mid-12,t+458),(mid+12,t+130,r-30,t+458)]
        for rect,(number,label,fill,fg) in zip(cards,[("17 件","公表された告知",ICE,TEAL),("7 件","うち最高深刻度 Critical",WARM,RUST)]):
            x,y,e,z=rect;box(im,rect,fill,18)
            self.tx(im,number,(x+25,y+10,e-25,z-96),118,fg,True)
            self.tx(im,label,(x+16,z-94,e-16,z-16),38,INK,True)
        top=b-128;gap=5;left=l+38;right=r-38;step=(right-left+gap)/17
        for i in range(17):
            x=round(left+i*step);e=round(left+(i+1)*step-gap)
            box(im,(x,top,e,top+33),RUST if i<7 else TEAL if i<11 else "#8196A0",4)
        self.tx(im,"Critical 7件　／　High 4件　／　Medium 6件",(left,top+43,right,b-15),29 if self.short else 34,MUTED,True)
    def versions(self,im,focus):
        l,t,r,b=self.l,self.t,self.r,self.b
        self.tx(im,"系列ごとに見る公式修正版",(l,t+2,r,t+81),48)
        edges=[l,l+int((r-l)*.23),l+int((r-l)*.58),r]
        head=t+101; head_b=head+(100 if self.short else 74)
        box(im,(l,head,r,head_b),DARK,14)
        for i,label in enumerate(("系列","10月21日","11月19日")):
            self.tx(im,label,(edges[i]+8,head+4,edges[i+1]-8,head_b-4),35,WHITE,True)
        rh=(b-head_b-12)//4
        for j,row in enumerate(VERSION):
            y=head_b+8+j*rh;z=y+rh-5;on=j==2
            box(im,(l,y,r,z),ICE if on else WHITE,12,outline=TEAL if on else RULE,width=3 if on else 1)
            for i,value in enumerate(row):
                self.tx(im,value+("系" if i==0 else ""),(edges[i]+4,y+5,edges[i+1]-4,z-5),
                        (49 if self.short else 53) if i>0 else 41,TEAL if i==2 else INK,True)
        if focus:
            ImageDraw.Draw(im).rectangle((l,head_b+8+2*rh,l+10,head_b+8+3*rh-5),fill=TEAL)
    def host(self,im,providers=False):
        l,t,r,b=self.l,self.t,self.r,self.b
        box(im,(l,t,r,b),WHITE,22,outline=RULE,width=2)
        x=l+40;e=r-40
        self.tx(im,"問い合わせ例　／　レンタルサーバー",(x,t+24,e,t+98),36,TEAL)
        self.tx(im,"対象：予約サイト・契約プラン",(x,t+112,e,t+193),42,MUTED)
        rule(im,(x,t+216,e,t+216))
        question="PHPの配布元はどこ？\n11月分の適用日は？" if providers else "11月19日分の修正は\n適用済みですか？"
        self.centered(im,question,(x,t+226,e,b-170),67 if self.short else 75,INK,True)
        box(im,(x,b-144,e,b-35),ICE,14)
        self.tx(im,"適用日・予定日・こちらで必要な作業",(x+14,b-134,e-14,b-45),36 if self.short else 41,TEAL,True)

PROVIDER_FIGURES = {
    "redhat-photo":("Red Hat","赤い帽子の\nRed Hat","次に見るのは公式のセキュリティ告知","写真引用　Red Hat「The hat」／ Red Hat Summit 会場"),
    "redhat-notice":("Red Hat Customer Portal","Red Hatが配るPHP","告知 RHSB-2026-020 の「Affected Products」へ","画面引用　Red Hat ／ RHSB-2026-020"),
    "redhat-products":("Red Hat Enterprise Linux","7件のうち2件は対象外","Red HatがRHELで配るPHPについての判断","画面引用　Red Hat ／ RHSB-2026-020・要約"),
    "remi-notice":("Remi’s RPM repository","RemiのPHP 8.4系","10月の8.4.27 → 11月の8.4.28","画面引用　Remi’s RPM repository ／ 2026.11.19"),
}

@lru_cache(maxsize=4)
def provider_image(key):
    ext = ".jpg" if key=="redhat-photo" else ".png"
    with Image.open(OUT/"captures/providers-v01/quotes"/(key+ext)) as im: return im.convert("RGB")

@lru_cache(maxsize=8)
def make_symbol(name):
    im=Image.new("RGBA",(280,194));d=ImageDraw.Draw(im)
    if name in ("cart","apple"):
        if name=="cart":
            d.line([(35,33),(63,33),(90,128),(218,128)],fill=INK,width=8,joint="curve")
            d.polygon([(73,62),(239,62),(216,110),(89,110)],fill="#C6DCD3",outline=TEAL,width=5)
            for x in (104,200):d.ellipse((x-11,136,x+11,158),fill=INK)
            x,y,k=148,73,.52
        else:
            x,y,k=130,90,1.13
        d.ellipse((x-48*k,y-28*k,x+10*k,y+44*k),fill="#BD5A38")
        d.ellipse((x-10*k,y-28*k,x+48*k,y+44*k),fill="#C66541")
        d.line((x,y-22*k,x+9*k,y-51*k),fill=INK,width=max(3,int(5*k)))
        d.ellipse((x+8*k,y-51*k,x+33*k,y-36*k),fill=TEAL)
    elif name=="server":
        for j in range(3):
            y=20+j*49;d.rounded_rectangle((45,y,235,y+38),radius=8,fill=DARK)
            for x in (65,82):d.ellipse((x,y+14,x+9,y+23),fill="#7DD3BD")
            d.line((125,y+19,214,y+19),fill="#69818C",width=4)
    elif name=="host":
        d.rounded_rectangle((45,25,235,158),radius=10,fill=DARK)
        for y in (45,76,107):
            for x in (66,100,134,168,202):d.rectangle((x,y,x+13,y+15),fill="#B7E1DA")
        d.rectangle((120,123,156,158),fill="#F8D7B1")
    else:
        d.rounded_rectangle((36,19,244,162),radius=12,fill=WHITE,outline=INK,width=6)
        d.line((40,53,240,53),fill=INK,width=5)
        for x in (53,69,85):d.ellipse((x,33,x+8,41),fill=TEAL)
        if name=="form":
            for y in (71,96):d.rounded_rectangle((65,y,214,y+13),radius=4,fill="#D3E3E1")
            d.rounded_rectangle((143,124,214,145),radius=5,fill=TEAL)
        else:
            d.ellipse((103,65,174,136),fill=TEAL)
            d.line([(119,100),(133,113),(158,83)],fill=WHITE,width=8,joint="curve")
    return im
