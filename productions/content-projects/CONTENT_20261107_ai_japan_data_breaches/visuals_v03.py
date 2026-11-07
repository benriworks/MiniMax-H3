"""Count-led charts and case detail overlays for the v03 edit."""
from PIL import Image, ImageDraw

from rank_volume import POPULATIONS, RANKS
from visuals import Renderer, backdrop, scaled, TEAL, AMBER, LILAC, MUTED, WHITE, EDGE, PANEL, DARK, EXCERPTS

NEW_EXCERPTS = EXCERPTS.parent.parent/'article-v03/assets'
HIGHLIGHT = '#ffa88d'
TRACK = '#263c56'
MAX_COUNT = RANKS['r01']['n']


class VolumeRenderer(Renderer):
    def presenters(self, im, row, local, message):
        super().presenters(im, row|{'id':row['motion_from']}, local, message)

    def line(self, im, coords, color, width=2):
        ImageDraw.Draw(im).line(scaled(coords), fill=color, width=width*2)

    def pill(self, im, value, y, color):
        self.tag(im, value, (self.l, y, self.r if self.short else self.l+324, y+39), color, 19)

    def source(self, im, text, source=None):
        y = 637 if self.short else 417
        self.text(im, text, (self.l, y, self.r, y+19), 13 if self.short else 14, MUTED)
        if source:
            self.text(im, source, (self.l, y+19, self.r, y+38), 12 if self.short else 12, MUTED)

    def ease(self, local, duration=1.1):
        progress = min(1, max(0, local/duration))
        return 1 - (1-progress)**3

    def strip(self, im, rect, width_fraction, local, color, tiles=0):
        x,y,r,b = rect
        self.box(im,rect,TRACK,radius=5)
        width = (r-x)*min(1,width_fraction)*self.ease(local)
        if width>2:
            self.box(im,(x,y,x+width,b),color,radius=5)
        if tiles:
            for i in range(1,tiles):
                pos=x+(r-x)*i/tiles
                self.line(im,(pos,y+2,pos,b-2),DARK,1)

    def sweep(self, im, local, color):
        # A single bright horizontal reveal; the real count stays visible throughout.
        progress = self.ease(local,.8)
        y = 76
        r = self.l+(self.r-self.l)*progress
        self.line(im,(self.l,y,r,y),color,2)
        if 0.02 < progress < .99:
            self.box(im,(r-5,y-3,r+5,y+3),WHITE,radius=3)

    def evidence_clip(self, im, case, rect, crop=None):
        key = case.get('quote')
        if not key:
            return False
        root = NEW_EXCERPTS if key=='daiichi-first-v03' else EXCERPTS
        path = root/f'{key}-excerpt.png'
        if not path.exists():
            return False
        self.box(im,rect,'#f4f6f8',radius=12)
        with Image.open(path) as image:
            x,y,r,b=rect
            photo=image.convert('RGB')
            if crop:
                photo=photo.crop(crop)
            self.picture(im,photo,(x+5,y+5,r-5,b-5))
        return True

    def impact(self, im, local):
        case = RANKS['r01']
        color = HIGHLIGHT
        self.sweep(im,local,color)
        if self.short:
            self.title(im,'国内の情報漏えい\n最も大きい公表値',32)
            self.pill(im,'持ち出しを確認',181,color)
            self.text(im,'8,133万',(self.l,236,self.r,363),95)
            self.text(im,'メールアドレス',(self.l,367,self.r,426),38,TEAL)
            self.box(im,(self.l,444,self.r,618),PANEL,HIGHLIGHT)
            self.text(im,'日本の総人口の約3分の2',(self.l+13,462,self.r-10,514),28)
            self.strip(im,(self.l+15,531,self.r-16,565),case['n']/POPULATIONS['japan']['number'],local,TEAL,tiles=12)
            self.text(im,'人口は規模をつかむための目安',(self.l+15,574,self.r-12,608),19,MUTED)
            self.source(im,'出典  ペイクラウドHD 11/6 第3報','総務省統計局「人口推計」2026年10月報')
        else:
            self.title(im,'持ち出されたメールアドレス',38)
            self.box(im,(self.l,155,611,398),PANEL,color)
            self.tag(im,'アララ メッセージ',(self.l+17,172,self.l+278,213),color,23)
            self.text(im,'81,329,467',(self.l+16,228,599,340),92)
            self.text(im,'アドレス（重複を除いた公表値）',(self.l+17,344,596,388),25,TEAL)
            self.actor(im,'male-close-thinking',local,(630,155,self.r,398))
            self.source(im,'出典  ペイクラウドHD 11/6 第3報')

    def population(self, im, case, local):
        key, line = case['compare']
        pop = POPULATIONS[key]
        maximum = max(case['n'], pop['number'])
        color = TEAL if case['confirmed'] else AMBER
        self.sweep(im,local,color)
        self.title(im,case['name']+'の公表値' if len(case['name'])<12 else case['name'],33)
        if self.short:
            self.pill(im,case['status'],168,color)
            metrics = [(case['count'],case['unit'],case['n'],color),(pop['label'],pop['name']+'の人口',pop['number'],LILAC)]
            for i,(count,unit,n,tint) in enumerate(metrics):
                y=224+i*141
                self.text(im,count,(self.l,y,self.r,y+64),52)
                self.text(im,unit,(self.l,y+62,self.r,y+96),21,tint)
                self.strip(im,(self.l,y+102,self.r,y+123),n/maximum,local,tint,tiles=12)
            self.text(im,line,(self.l,513,self.r,563),26,WHITE)
            self.text(im,'人口は規模をつかむための目安',(self.l,568,self.r,611),19,MUTED)
            self.source(im,'出典  '+case['credit'],pop['source'])
        else:
            self.pill(im,case['status'],144,color)
            metrics = [
                (case['name'],case['count']+' '+case['unit'],case['n'],color),
                (pop['name']+'の人口',pop['label'],pop['number'],LILAC),
            ]
            for i,(label,value,n,tint) in enumerate(metrics):
                y=196+i*82
                self.text(im,label,(self.l,y,356,y+30),19)
                self.text(im,value,(377,y,self.r,y+30),23,tint)
                self.strip(im,(self.l,y+39,self.r,y+69),n/maximum,local,tint,tiles=16)
            self.text(im,line,(self.l,357,559,409),28)
            self.text(im,'件数と人口は桁の比較',(596,364,self.r,405),22,MUTED)
            self.source(im,'出典  '+case['credit'],pop['source'])

    def rank_main(self, im, case, local):
        color=TEAL if case['confirmed'] else AMBER
        number=case['rank']
        self.sweep(im,local,color)
        self.tag(im,f'{number}位',(self.l,92,self.l+105,138),color,30)
        self.text(im,case['name'],(self.l+126,87,self.r,141),36)
        self.box(im,(self.l,153,590,374),PANEL,color)
        self.tag(im,case['status'],(self.l+15,165,self.l+326,205),color,22)
        self.text(im,case['count'],(self.l+16,217,578,323),83)
        self.text(im,case['unit'],(self.l+18,323,578,364),25,color)
        if 'compare' in case:
            key,label=case['compare']
            population=POPULATIONS[key]
            self.box(im,(609,153,self.r,374),PANEL,EDGE)
            self.text(im,population['name']+'の人口',(625,167,self.r-11,205),22)
            self.text(im,population['label'],(625,208,self.r-10,267),36,LILAC)
            self.text(im,label.replace(population['name']+'の','',1),(625,282,self.r-10,323),24)
            self.text(im,'規模をつかむための比較',(625,329,self.r-10,361),16,MUTED)
            self.source(im,'出典  '+case['credit'],population['source'])
        else:
            self.box(im,(609,153,self.r,374),PANEL,EDGE)
            self.text(im,'対象となった情報',(625,165,self.r-11,208),21,MUTED)
            for i,(name,_) in enumerate(case['fields']):
                y=219+i*46
                self.icon(im,625,y+8,('document','scope','key')[i],color,20)
                self.text(im,name,(653,y,self.r-11,y+38),21)
            self.source(im,'出典  '+case['credit'])
        self.strip(im,(self.l,385,self.r,398),case['n']/MAX_COUNT,local,color,tiles=10)
        self.text(im,'今回の最大公表値を基準に表示',(self.l,400,self.r,415),11,MUTED)

    def field_cards(self, im, case, local):
        color=TEAL if case['confirmed'] else AMBER
        if case['rank']==2:
            self.shipping(im,case,local)
            return
        if case['rank']==10 and not self.short and local>=5:
            path = NEW_EXCERPTS/'daiichi-first-v03-excerpt.png'
            if path.is_file():
                self.title(im,'10位  第一興商｜おそれがある範囲',34)
                with Image.open(path) as original:
                    w,h=original.size
                self.evidence_clip(im,case,(self.l,160,578,398),(0,round(h*.72),w,h))
                self.box(im,(595,160,self.r,398),PANEL,AMBER)
                self.text(im,'11月6日 続報',(611,178,self.r-12,221),25)
                self.text(im,'個人情報の流出は\n確認されていない',(611,245,self.r-12,365),24,AMBER)
                self.source(im,'引用  第一興商 10/8 初報／出典  11/6 調査結果')
                return
        if self.short:
            self.title(im,case['name']+'の対象',33)
            self.pill(im,case['status'],165,color)
            self.cards(im,case['fields'],0 if local<1.25 else 1 if local<3.2 else 2,top=213)
        else:
            self.title(im,f"{case['rank']}位  {case['name']}｜対象情報",33)
            self.pill(im,case['status'],145,color)
            self.cards(im,case['fields'],0 if local<1.25 else 1 if local<3.2 else 2,top=198)
        self.source(im,'出典  '+case['credit'])

    def shipping(self, im, case, local):
        if self.short:
            self.title(im,'送り状のどこが対象？',34)
            self.pill(im,'佐川急便  ／  流出の可能性',169,AMBER)
            panels=((self.l,237,self.r,359),(self.l,422,self.r,544))
            self.strip(im,(self.l+20,381,self.r-20,393),1,local,AMBER,tiles=9)
            self.text(im,'電子の送り状のデータ',(self.l,568,self.r,617),25,AMBER)
        else:
            self.title(im,'2位  佐川急便｜送り主と届け先',36)
            panels=((self.l,163,347,333),(613,163,self.r,333))
            self.strip(im,(350,240,611,251),1,local,AMBER,tiles=7)
            self.tag(im,'電子の送り状',(369,173,593,222),AMBER,20)
            self.text(im,'スマートクラブの会員情報には、メールと会員IDも',(self.l,349,self.r,380),23)
            self.text(im,'手書きの送り状・カード情報・パスワードは対象外',(self.l,382,self.r,414),18,MUTED)
        for i, ((x,y,r,b), label) in enumerate(zip(panels, ('送り主','届け先'),strict=True)):
            color=AMBER if i==0 or local>=1.25 else EDGE
            self.box(im,(x,y,r,b),PANEL,color)
            self.icon(im,x+17,y+22,'document',AMBER,29)
            self.text(im,label,(x+60,y+14,r-10,y+57),29)
            self.text(im,'氏名・住所・電話',(x+18,y+66,r-11,b-9),25,WHITE,True)
        self.source(im,'出典  '+case['credit'])

    def details(self, im, key, case, local):
        self.title(im,f"{case['rank']}位  {case['name']}｜公表の内訳",33)
        if key=='r03':
            if self.evidence_clip(im,case,(self.l,151,562,405),(938,0,1974,540)):
                self.box(im,(574,151,self.r,406),PANEL,AMBER)
                self.text(im,'49システム',(590,165,self.r-12,221),35,TEAL)
                self.text(im,'漏えいの痕跡を確認',(590,223,self.r-13,264),22)
                self.text(im,'51,628,280件',(590,274,self.r-13,335),33,AMBER)
                self.text(im,'漏えいのおそれがある延べ件数',(590,343,self.r-12,393),20)
                self.source(im,'引用  '+case['credit'])
                return
        details = {
            'r09': (('モバイル注文','注文履歴の有無'),('カード番号','アプリ側で保有せず'),('パスワード','漏えい未確認')),
            'r08': (('32,341件','返金先の銀行口座\n流出を公表'),('別の保管データ','カードの記録や\n旅行保険の申込み'),
                    ('件数は別区分','主サーバーの件数と\n分けて読む')),
            'r07': (('5件','備考にカードらしい\n記録があった'),('期限は経過','実在と正確性は\n未確認'),
                    ('原因','詳細な侵入経路は\n非公表')),
            'r06': (('カード情報','今回の対象外'),('会員情報','公式の案内で\nパスワード再設定'),('同じ組み合わせ','使い回した先も\n変更する')),
            'r05': (('約209.7万人','カード情報の一部\nを含む対象'),('番号の一部','先頭6桁と下4桁\n名義・有効期限'),('全桁・CVC','サービスでは\n保有せず')),
            'r04': (('約109万件','MUJI Cardの\n全桁番号など'),('約34.5万件','そのうち有効な番号\n公表時点'),('別の約120件','先頭6桁と下2桁\nカード名義')),
            'r03': (('49システム','漏えいの痕跡'),('51,628,280件','漏えいのおそれが\nある延べ件数'),('16システム','件数の調査が継続')),
            'r01': (('既報の環境','Webサーバーの脆弱性'),('管理画面','不正ログインを確認'),('別の環境','認証情報の悪用')),
        }
        self.cards(im,details[key],1 if local<3.2 else 2,top=150)
        if key in {'r01','r04','r09'} and self.evidence_clip(im,case,(self.l,368,self.r,413)):
            self.source(im,'引用  '+case['credit'])
        else:
            self.source(im,'出典  '+case['credit'])

    def volume_method(self, im, row, local):
        if row['visual']=='units':
            super().method(im,'units',0 if local<1.25 else 1 if local<3.2 else 2)
            return
        self.title(im,'公表件数の大きい順に並べる',37)
        self.cards(im,[('対象期間','2026年11月7日まで\n国内の公表事例'),('確認された範囲','公表の単位を併記'),
                       ('おそれの範囲','最大値・延べ件数\nも区別して表示')],0 if local<1.25 else 1 if local<3.2 else 2)
        self.source(im,'件数が大きい順  ／  何が対象かは事例ごとに確認')

    def frame(self, row, local, at, progress):
        if row is None or row['chapter'] not in ('opening','method','examples',*RANKS):
            return super().frame(row,local,at,progress)
        chapter=row['chapter']
        visual=row['visual']
        im=backdrop(self.short,chapter in RANKS or chapter=='examples').copy()
        header='2026年 国内情報漏えい' if self.short else '2026年 国内情報漏えい 公表件数Top10'
        self.header(im,header,progress)
        if visual=='impact':
            self.impact(im,local)
        elif chapter=='method':
            self.volume_method(im,row,local)
        elif chapter=='examples':
            key='r01' if visual=='arara-fields' else 'r02'
            case=RANKS[key]
            if visual=='sagawa-rank':
                self.population(im,case,local)
            else:
                self.field_cards(im,case,local)
        elif visual=='population':
            self.population(im,RANKS['r01'] if chapter=='opening' else RANKS[chapter],local)
        else:
            case=RANKS[chapter]
            if visual=='rank':
                self.rank_main(im,case,local)
            elif visual=='split':
                self.title(im,'1位  アララ｜メールアドレスの内訳')
                self.split_arara(im)
                self.source(im,'出典  '+case['credit'])
            elif visual=='fields':
                self.field_cards(im,case,local)
            else:
                self.details(im,chapter,case,local)
        self.caption(im,row,at)
        return im
