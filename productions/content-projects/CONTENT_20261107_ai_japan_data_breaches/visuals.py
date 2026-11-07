"""Vertical and landscape editorial graphics for the Japan breaches case."""
from functools import lru_cache
import json

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from generate_voices import CASE, ROOT, OUT
from tools.studio.editorial_captions import PROTECTED
from tools.studio.explainer_canvas import Canvas

EXCERPTS = OUT / 'article-v02/assets'
PRIOR = ROOT / 'outputs/content-projects/CONTENT_20261106_ai_bert_gpt_history'
PROTECTED_TERMS = (*PROTECTED, 'Cuenote', 'PeakManager', 'EPARK', 'skyticket', 'NCSC',
    'KDDI', 'バーガーキング', 'ショップサーブ', 'ソースネクスト', 'アララ メッセージ',
    '無印良品', 'MUJI Card', '多要素認証', '本人確認書類', '約8,133万', '最大約2,726万件',
    '約1,464万件', '約2,218万レコード', '約1,118万件', '最大約5,323万件', '信用情報機関')
WHITE, MUTED, TEAL, AMBER, LILAC = '#f5f7ff', '#bfcee4', '#76ecd4', '#ffd48e', '#bab5ff'
PANEL, EDGE, DARK = '#17283f', '#3a5572', '#0b1729'
TITLES = {
    'full': '【AI】2026年 日本の情報漏えいTop10｜何が漏れた？被害を減らす対策',
    'short': '【AI】個人情報が漏れたら？2026年 日本の漏えい事例から考える3つの対策',
}

# A formatted primary quantity, its unit/certainty, three scope labels, and the case's
# cause and attribution. Additional collections stay outside the ranking count.
RANK = {
    'r10': ('バーガーキング', '1,118万', '件（約）', '漏えい確認',
            ('会員情報', '氏名・電話番号', '注文履歴の有無'),
            '詳細な侵入経路は調査中', 'ビーケー・ジャパン 10/15', 'burger-king'),
    'r09': ('KDDIのISP向けメール基盤', '12,231,954', '名（公式表記）', '漏えい確認',
            ('メールアドレス', 'パスワード情報は内数', '別設備のメールは対象外'),
            '第三者製ソフトウェアの脆弱性', 'KDDI 7/21訂正版', 'kddi-isp'),
    'r08': ('skyticket', '1,464万', '件（約・初報）', '確認と可能性を含む',
            ('氏名・連絡先', '一部にパスワード', '別保管データは別区分'),
            '不要なDB複製に認証情報を悪用', 'アドベンチャー 初報・10/30第3報', None),
    'r07': ('ソースネクスト', '22,519,960', '件', '流出の可能性',
            ('会員情報', 'メール・パスワード', '保存形式は未確認'),
            '会員情報取得APIの不正利用', 'ソースネクスト 10/15', None),
    'r06': ('Eストアー ショップサーブ', '2,335.6万', '人（約・名寄せ後）', '持ち出し確認',
            ('会員情報', '暗号化パスワード', '一部にカード部分番号等'),
            'アプリの脆弱性から不正プログラムを設置', 'Eストアー 10/16最終報', None),
    'r05': ('EPARK PeakManager', '2,218万', 'レコード（約）', '外部取得・削除を確認',
            ('予約・連絡先', '一部の備考に健康情報', '精査後の値'),
            '詳細な侵入経路は非公表', 'EPARKリラク＆エステ 9/24第2報', 'epark-second'),
    'r04': ('佐川急便', '5,323万', '件（最大約・重複あり）', '流出の可能性',
            ('送り状・会員情報', '氏名・住所・電話', 'カード・パスワードは対象外'),
            '詳細な侵入経路は第5報で非公表', '佐川急便 10/23第5報', None),
    'r03': ('無印良品', '2,726万', '件（最大約）', '流出の可能性',
            ('アプリ・ネットストア', '会員データ', 'カードは別区分'),
            '詳細な侵入経路は未確認', '良品計画 11/4第2報', 'muji-second-pdf'),
    'r02': ('Cuenote', '51,628,280', '件（延べ）', '漏えいのおそれ',
            ('メール配信の情報', '49システムに出力の痕跡', '件数調査中の環境あり'),
            '脆弱性と盗まれた認証情報を悪用', 'ユミルリンク 第2報', 'cuenote-second-v02'),
    'r01': ('アララ メッセージ', '81,329,467', 'メールアドレス', '持ち出し確認',
            ('重複を除いた値', '一部に属性情報', '項目は利用企業ごとに異なる'),
            '侵入経路は環境別に公表', 'ペイクラウドHD 11/6第3報', 'arara-third'),
}
PEOPLE = {
    'f01': ('male-close-thinking', 'female-thinking'),
    'f02': ('male-thinking', 'female-close-insight'),
    'f06': ('male-close-thinking', 'female-thinking'),
    'f10': ('male-frustration', 'female-thinking'),
    'f26': ('male-close-thinking', 'female-thinking'),
    'f33': ('male-close-thinking', 'female-sadness'),
    'f36': ('male-frustration', 'female-close-insight'),
    'f41': ('male-enjoyment', 'female-thinking'),
    'f42': ('male-thinking', 'female-close-insight'),
    's01': ('male-close-thinking', 'female-thinking'),
    's02': ('male-thinking', 'female-close-insight'),
    's08': ('male-thinking', 'female-close-insight'),
}
SCORES = {entry['proposed_rank']: entry for entry in
          json.loads((CASE/'ranking-v01.json').read_text(encoding='utf-8'))['ranking']}


def scaled(values):
    return tuple(round(x*2) for x in values)


@lru_cache(maxsize=4)
def backdrop(short, rank):
    width, height = (1080, 1920) if short else (1920, 1080)
    y, x = np.ogrid[:height, :width]
    glow = np.exp(-((x/width-(.7 if rank else .25))**2 + (y/height-.22)**2)*5.8)
    rgb = np.stack([10+12*glow, 20+20*glow, 35+36*glow], axis=2).astype(np.uint8)
    im = Image.fromarray(rgb)
    draw = ImageDraw.Draw(im)
    for u in range(0, width, 96):
        draw.line((u, 0, u, height), fill='#23354c', width=1)
    for v in range(0, height, 96):
        draw.line((0, v, width, v), fill='#23354c', width=1)
    return im


@lru_cache(maxsize=14)
def actor_files(job):
    close = '-close-' in job
    root = PRIOR / ('motion-close-cache' if close else 'motion-framed-cache') / job
    files = sorted(root.glob('*.jpg' if close else '*.png'))
    meta = json.loads((root / 'complete.json').read_text(encoding='utf-8'))
    if len(files) != 124 or meta['frames'] != len(files):
        raise ValueError(f'Incomplete MiniMax input {job}')
    return files


class Renderer:
    def __init__(self, kind, focused_quotes=True):
        self.short = kind == 'short'
        self.focused_quotes = focused_quotes
        self.canvas = Canvas()
        self.l, self.r = (26, 490) if self.short else (42, 918)

    def text(self, im, value, rect, size, color=WHITE, center=False):
        self.canvas.text(im, value, scaled(rect), round(size*2), color=color, center=center)

    def box(self, im, rect, fill=PANEL, stroke=None, radius=16):
        ImageDraw.Draw(im).rounded_rectangle(scaled(rect), round(radius*2), fill=fill, outline=stroke, width=2)

    def tag(self, im, value, rect, color=TEAL, size=17):
        self.box(im, rect, color, radius=10)
        self.text(im, value, rect, size, DARK, True)

    def credit(self, im, value):
        y = 639 if self.short else 421
        self.text(im, value, (self.l, y, self.r, y+22), 13, MUTED)

    def icon(self, im, x, y, mode, color, size=30):
        draw = ImageDraw.Draw(im)

        def line(points):
            draw.line([scaled((x+u*size, y+v*size)) for u,v in points],
                      fill=color, width=4, joint='curve')

        if mode == 'document':
            line(((.18,.12),(.72,.12),(.86,.27),(.86,.91),(.18,.91),(.18,.12)))
            line(((.31,.43),(.72,.43)))
            line(((.31,.63),(.66,.63)))
        elif mode == 'scope':
            draw.ellipse(scaled((x+.12*size,y+.08*size,x+.72*size,y+.68*size)),outline=color,width=4)
            line(((.67,.64),(.95,.94)))
        elif mode == 'key':
            draw.ellipse(scaled((x+.08*size,y+.21*size,x+.50*size,y+.63*size)),outline=color,width=4)
            line(((.5,.42),(.92,.42),(.92,.63)))
            line(((.73,.42),(.73,.56)))
        elif mode == 'card':
            self.box(im,(x,y+.15*size,x+size,y+.86*size),PANEL,color,4)
            line(((.1,.39),(.89,.39)))
            line(((.13,.65),(.42,.65)))
        else:
            line(((.09,.51),(.37,.77),(.88,.22)))

    def header(self, im, chapter, progress):
        self.tag(im, '【AI】', (self.l, 27, self.l+74, 58), TEAL, 16)
        self.text(im, chapter, (self.l+88, 27, self.r-100, 58), 16, MUTED)
        self.text(im, '2026.11.07', (self.r-95, 27, self.r, 58), 14, MUTED, True)
        draw = ImageDraw.Draw(im)
        draw.line(scaled((self.l, 67, self.r, 67)), fill=EDGE, width=3)
        draw.line(scaled((self.l, 67, self.l+(self.r-self.l)*progress, 67)), fill=TEAL, width=4)

    def title(self, im, value, size=None):
        self.text(im, value, (self.l, 83, self.r, 183 if self.short else 140),
                  size or (37 if self.short else 36))

    def picture(self, im, source, rect, cover=False):
        x1, y1, x2, y2 = scaled(rect)
        size = (x2-x1, y2-y1)
        if cover:
            tile = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(.5, .14))
            mask = Image.new('L', size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0]-1, size[1]-1), 25, fill=255)
            im.paste(tile, (x1, y1), mask)
        else:
            tile = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
            im.paste(tile, (x1+(size[0]-tile.width)//2, y1+(size[1]-tile.height)//2))

    def actor(self, im, job, local, rect):
        files = actor_files(job)
        frame = min(112, 4 + max(0, round(local*24)))
        with Image.open(files[frame]) as base:
            crop = (0, 0, 480, 578) if '-close-' in job else (53, 5, 434, 399)
            self.picture(im, base.convert('RGB').crop(crop), rect, cover=True)

    def caption(self, im, row, at):
        page = next((c['text'] for c in row['captions'] if c['start'] <= at < c['end']), None)
        if not page:
            return
        y1, y2 = (690, 790) if self.short else (455, 527)
        self.box(im, (self.l, y1, self.r, y2), '#0c182c', EDGE, 15)
        role = '透' if row['speaker'] == 'male' else '凛'
        color = TEAL if role == '透' else LILAC
        if self.short:
            self.tag(im, role, (self.l+11, y1-24, self.l+46, y1+4), color, 14)
            rect = (self.l+14, y1+11, self.r-14, y2-9)
        else:
            self.tag(im, role, (self.l+11, y1+17, self.l+53, y1+53), color, 19)
            rect = (self.l+61, y1+3, self.r-10, y2-3)
        self.text(im, page, rect, 27 if self.short else 25, WHITE, True)

    def presenters(self, im, row, local, message):
        pair = PEOPLE[row['id']]
        if self.short:
            index = int(row['speaker'] == 'female')
            self.title(im, message, 31)
            self.actor(im, pair[index], local, (57, 205, 459, 625))
            name = ('朝倉 透','篠宮 凛')[index]
            self.tag(im, name, (68, 579, 193, 612), (TEAL,LILAC)[index], 17)
            return
        for i, rect in enumerate(((42, 150, 307, 407), (653, 150, 918, 407))):
            self.actor(im, pair[i], local, rect)
            x = rect[0]
            self.tag(im, ('朝倉 透','篠宮 凛')[i], (x+10, 365, x+113, 398), (TEAL,LILAC)[i], 16)
        self.text(im, message, (321, 212, 639, 354), 28, WHITE, True)

    def cards(self, im, items, active, top=None):
        if self.short:
            top = 200 if top is None else top
            rects = [(self.l, top+i*139, self.r, top+i*139+113) for i in range(3)]
        else:
            top = 169 if top is None else top
            rects = [(self.l+i*296, top, self.l+i*296+284, top+210) for i in range(3)]
        for i, ((key, detail), (x,y,r,b)) in enumerate(zip(items, rects, strict=True)):
            color = (TEAL, LILAC, AMBER)[i]
            self.box(im, (x,y,r,b), PANEL, color if active is None or i<=active else EDGE)
            if self.short:
                self.tag(im, str(i+1), (x+14,y+17,x+48,y+51), color, 18)
                self.text(im, key, (x+62,y+15,r-10,y+56), 25)
                self.text(im, detail, (x+62,y+61,r-10,b-8), 18, MUTED)
            else:
                self.tag(im, f'0{i+1}', (x+19,y+18,x+66,y+55), color, 19)
                self.icon(im, r-60, y+21, ('document','scope','check')[i], color, 31)
                self.text(im, key, (x+19,y+72,r-10,y+121), 25)
                self.text(im, detail, (x+19,y+127,r-11,b-13), 18, MUTED)

    def quote(self, im, source_id, rect, source, crop=None):
        path = EXCERPTS / f'{source_id}-excerpt.png'
        if not path.is_file():
            return False
        self.box(im, rect, '#f4f5f7', radius=10)
        x,y,r,b = rect
        with Image.open(path) as photo:
            image = photo.convert('RGB')
            if crop is not None:
                image = image.crop(crop)
            self.picture(im, image, (x+5,y+5,r-5,b-5))
        self.credit(im, '引用  '+source)
        return True

    def rank(self, im, key, row, local, active):
        name,count,unit,state,fields,cause,source,excerpt = RANK[key]
        number = int(key[1:])
        color = AMBER if any(k in state for k in ('可能性','おそれ')) else TEAL
        visual = row['visual']
        if self.short:
            self.title(im, name, 34)
            self.tag(im, state, (self.l, 190, self.r, 237), color, 23)
            value = count if number == 1 else '最大約2,726万件'
            self.text(im, value, (self.l, 254, self.r, 365), 72 if number==1 else 47)
            self.text(im, unit if number==1 else 'アプリ・ネットストアの会員データ',
                      (self.l, 371, self.r, 432), 36 if number==1 else 22, color)
            self.box(im, (self.l, 446, self.r, 525), PANEL, EDGE)
            message = '項目は配信元ごとに異なる' if number==1 else 'MUJI Card は別区分'
            self.text(im, message, (self.l+12, 454, self.r-12, 517), 28, WHITE, True)
            if local >= 2.4 and self.quote(im, excerpt, (self.l, 548, self.r, 624), source):
                return
            self.credit(im, '出典  '+source)
            return
        self.title(im, f'{number}位   {name}', 35)
        if visual == 'question':
            message = '注文した商品まで\n分かる？' if number==10 else '全会員の\nカード番号？'
            self.presenters(im, row, local, message)
        elif visual == 'split':
            self.split_arara(im)
        elif number == 3 and visual == 'evidence':
            self.muji(im)
            if self.quote(im, excerpt, (self.l, 329, self.r, 411), source):
                return
        elif number == 2 and local>=5 and self.focused_quotes:
            # Preserve both original column headings and rows. The left two
            # columns remain available in the wide quotation and the article.
            if self.quote(im, excerpt, (42, 149, 552, 407), source, (938, 0, 1974, 540)):
                self.box(im, (570, 149, self.r, 407), PANEL, AMBER)
                self.text(im, '49システム', (586, 166, self.r-12, 216), 32, TEAL)
                self.text(im, '漏えいの痕跡を確認', (586, 218, self.r-12, 259), 22)
                self.text(im, '51,628,280件', (586, 275, self.r-12, 333), 31, AMBER)
                self.text(im, '漏えいのおそれがある延べ件数', (586, 340, self.r-12, 394), 19)
                return
            self.evidence(im, number, row, cause, color, active)
        elif visual == 'rank':
            self.box(im, (self.l, 148, 562, 406), PANEL, EDGE)
            self.tag(im, state, (self.l+19, 165, 354, 206), color, 20)
            self.text(im, count, (self.l+21, 219, 549, 322), 78)
            self.text(im, unit, (self.l+21, 326, 549, 385), 28, color)
            for i, line in enumerate(fields):
                y = 149+i*88
                self.box(im, (585, y, self.r, y+76), PANEL, color if i==active else EDGE, 13)
                self.icon(im, 602, y+25, ('document','scope','check')[i], color if i==active else MUTED, 24)
                self.text(im, line, (637, y+7, self.r-9, y+67), 19, WHITE if i<=active else MUTED)
            score = SCORES[number]
            self.text(im, f"影響 I={score['impact']}  ／  {score['score']/10000:,.0f}万点",
                      (584, 422, self.r, 443), 14, color, True)
        else:
            self.evidence(im, number, row, cause, color, active)
            if excerpt and self.quote(im, excerpt, (self.l, 326, self.r, 411), source):
                return
            self.text(im, state+'  ／  '+fields[2], (self.l, 334, self.r, 399), 24, color)
        self.credit(im, '出典  '+source)

    def evidence(self, im, number, row, cause, color, active):
        facts = {
            10: ('モバイル注文歴の有無','カード番号は保有せず','パスワード漏えい未確認'),
            9: ('12,231,954名','内数 7,616,173名','パスワード情報'),
            8: ('初報の主なサーバー','別保管のカード記録','返金口座・保険申込等'),
            7: ('会員情報取得API','第三者が不正利用','連絡先・認証情報'),
            6: ('暗号化パスワード','一部にカード部分番号等','全桁とCVCは保有せず'),
            5: ('予約情報','一部の備考','健康状態など'),
            4: ('送り状・会員情報','氏名・住所・電話','配達を装う連絡に注意'),
            2: ('ソフトウェアの脆弱性','認証情報の窃取','複数環境へ侵入'),
            1: ('Webサーバーの脆弱性','管理画面へ不正ログイン','別環境で認証情報を悪用'),
        }
        if number == 8 and row['visual'] == 'related':
            cause = '第3報で特典サービスの認証情報に関する記載を訂正'
        self.box(im, (self.l, 146, self.r, 204), PANEL, color)
        self.text(im, cause, (self.l+16, 149, self.r-16, 200), 23)
        for i, label in enumerate(facts[number]):
            x = self.l+i*296
            self.box(im, (x, 220, x+284, 304), PANEL, LILAC if i==active else EDGE, 12)
            self.text(im, label, (x+9, 231, x+275, 293), 19, WHITE, True)

    def split_arara(self, im):
        self.box(im, (self.l, 151, self.r, 405), PANEL, EDGE)
        left, right = self.l+23, self.r-23
        split = left+(right-left)*34_285_087/81_329_467
        self.text(im, '重複を除いたメールアドレスの内訳', (left, 160, right, 204), 22, MUTED)
        self.box(im, (left, 213, right, 257), LILAC, radius=10)
        self.box(im, (left, 213, split, 257), TEAL, radius=10)
        self.text(im, '34,285,087', (left, 267, split-10, 326), 36, TEAL)
        self.text(im, '47,044,380', (split+16, 267, right, 326), 36, LILAC)
        self.text(im, 'メールアドレスのみ', (left, 333, split-10, 374), 21)
        self.text(im, 'メール＋企業ごとの属性', (split+16, 333, right, 374), 21)

    def muji(self, im):
        for i,(name,count,note) in enumerate((
            ('アプリ・ネットストア','最大約2,726万件','会員データ'),
            ('別区分  MUJI Card','約109万件','うち有効約34.5万件（公表時点）'),
        )):
            x = self.l+i*444
            color = AMBER if i==0 else LILAC
            self.box(im, (x, 149, x+431, 313), PANEL, color)
            self.text(im, name, (x+16, 161, x+414, 199), 22, color)
            self.text(im, count, (x+16, 206, x+414, 265), 41)
            self.text(im, note, (x+16, 272, x+414, 305), 20, MUTED)

    def opening(self, im, row, local):
        if row['visual'] == 'notice':
            if self.short:
                self.title(im, '「情報が漏れた」\nまず、どうする？', 32)
                rect = (self.l, 211, self.r, 452)
                self.actor(im, PEOPLE[row['id']][0], local, (210, 471, 489, 663))
            else:
                self.title(im, '情報漏えいの通知が来た', 37)
                rect = (self.l, 161, 593, 387)
                self.actor(im, PEOPLE[row['id']][0], local, (621, 149, self.r, 406))
            x,y,r,b = rect
            self.box(im, rect, '#edf4ff', radius=24)
            self.tag(im, '架空の通知', (x+21,y+20,x+160,y+62), AMBER, 20)
            self.text(im, 'あなたの情報が\n漏えいした可能性があります', (x+22,y+90,r-15,b-10),
                      27 if self.short else 31, DARK)
        elif self.short and local >= 2.4:
            self.title(im, '公式アプリから\n対象を確認', 34)
            self.cards(im, [('公式を開く','いつも使うアプリやサイト'), ('対象を見る','自分の何が漏れたか'),
                            ('対処を選ぶ','パスワード・カードなど')], 1)
        else:
            self.presenters(im, row, local, '自分の何が\n対象かを確認')
            if not self.short:
                self.title(im, '2026年  日本の情報漏えい Top10', 37)

    def method(self, im, visual, active):
        if visual == 'formula':
            self.title(im, '公表規模 × 情報のインパクト')
            self.cards(im, [('公表規模 N','公表された数値'), ('情報の影響 I','情報の種類で1〜5'),
                            ('この動画の順位','11月7日までの主な国内事案')], active)
        elif visual == 'units':
            self.title(im, '公表値は、単位と確度をセットで')
            self.cards(im, [('人数','名・人'), ('アドレス数','重複を除く場合も'),
                            ('レコード数','重複を含む場合も')], active)
            self.credit(im, '各事例に「確認」「可能性」など、公表された確度を表示')
        elif active < 2:
            self.title(im, '大きな件数の中に、異なる情報')
            self.cards(im, [('主たる公表規模','例  会員データ全体'),
                            ('一部の情報','例  連絡先がある記録'),
                            ('別の対象区分','例  カード番号を含む記録')], active)
            self.credit(im, 'インパクトは編集上の目安。実害や事業者の責任を測る指標とは別')
        else:
            self.title(im, '掛け算で順位が変わる例')
            for i, (name, value, score) in enumerate((
                ('無印良品','約2,726万件 × I=4','約10,904万点'),
                ('佐川急便','約5,323万件 × I=2','約10,646万点'),
            )):
                y = 151+i*126
                color = (LILAC, AMBER)[i]
                self.box(im, (self.l,y,self.r,y+108), PANEL, color)
                self.text(im, name, (self.l+17,y+10,265,y+52), 27)
                self.text(im, value, (self.l+17,y+55,483,y+99), 24, MUTED)
                self.text(im, score, (540,y+14,self.r-15,y+92), 37, color, True)
            self.credit(im, '公表規模と情報の種類から算出。採点の根拠は関連記事へ')

    def ai(self, im, row, local, active):
        visual = row['visual']
        if visual == 'think':
            self.title(im, 'AIが変える、攻撃の速度と規模')
            self.presenters(im, row, local, '攻撃する側の\n何が変わる？')
        elif visual == 'ai-source':
            self.title(im, '英国NCSCの2026年次報告')
            if not self.quote(im, 'ncsc-ai-2026', (self.l, 151, self.r, 250), '英国NCSC  2026年次報告'):
                self.credit(im, '出典  英国NCSC  2026年次報告')
            self.box(im, (self.l, 266, self.r, 400), PANEL, TEAL)
            self.text(im, '攻撃の速度・規模・効率が上がると評価', (self.l+17, 277, self.r-16, 335), 29)
            self.text(im, '個別事件でAIが使われたかは、公表資料で確認', (self.l+17, 340, self.r-16, 392), 22, MUTED)
        else:
            self.title(im, '調べる → 作る → 試す')
            self.cards(im, [('公開情報の調査','対象を調べる'), ('コードの作成','作業の一部を支援'),
                            ('試行の反復','結果を見て次を試す')], active)
            self.credit(im, '出典  英国NCSC  2026年次報告')

    def identity(self, im, row, local, active):
        self.title(im, '本人確認書類は、順位と別に確認')
        if row['visual'] == 'think':
            self.presenters(im, row, local, '免許証の画像が\n対象だったら？')
        elif row['visual'] == 'identity-source':
            self.cards(im, [('暗号化画像','復号・悪用の有無は\n件数からは分からない'),
                            ('事業者の案内','対象書類と通知を確認'),
                            ('本人申告','国内の信用情報機関に相談')], active, top=148)
            self.quote(im, 'ipa-response', (self.l, 369, self.r, 413), 'IPA 10/26  本人確認書類に関する案内')
        else:
            self.cards(im, [('1,464,800件','外部送信の痕跡あり'),
                            ('891,602件','アクセスあり\n送信の痕跡は未確認'),
                            ('対象の単位','暗号化された\n本人確認書類の画像')], active)
            self.credit(im, '出典  パーク24 10/23第5報')

    def actions(self, im, row, local, active):
        visual = row['visual']
        if visual == 'ask-action':
            self.title(im, '漏れた情報ごとに、必要な対処を')
            self.presenters(im, row, local, '通知を受けたら\nどんな順番？')
            return
        number = int(visual[-1])
        steps = (
            ('公式で対象を確認', 'いつものアプリ・サイト', '通知のリンクで入力しない', '対象項目を確認'),
            ('使い回し先も変更', 'パスワードが対象なら', '多要素認証・パスキー', '同じ鍵を使った先も'),
            ('カード・口座を確認', '明細や入出金を確認', '身に覚えのない取引', '公式窓口へ相談'),
            ('便乗詐欺に注意', '配送や返金を装う連絡', '認証コードは教えない', '日時と画面を記録'),
        )
        title, first, second, third = steps[number-1]
        if self.short and number == 3:
            title, first = 'カード明細を確認', 'カード番号が対象なら'
        self.title(im, title, 37)
        if self.short:
            self.tag(im, f'対処 {number} / 3', (self.l, 165, self.r, 220), TEAL, 25)
            rects = [(self.l, 250+i*122, self.r, 354+i*122) for i in range(3)]
        else:
            self.tag(im, f'対処 {number}', (self.l, 148, self.l+122, 190), TEAL, 22)
            rects = [(self.l+i*296, 217, self.l+i*296+284, 382) for i in range(3)]
        for i, ((x,y,r,b), text) in enumerate(zip(rects, (first,second,third), strict=True)):
            self.box(im, (x,y,r,b), PANEL, TEAL if i==active else EDGE)
            mode = ('scope','key','card','document')[number-1] if i==0 else ('scope' if i==1 else 'check')
            if self.short:
                self.icon(im, x+19, y+33, mode, TEAL, 34)
                self.text(im, text, (x+67,y+8,r-11,b-8), 25, WHITE, True)
            else:
                self.icon(im, (x+r)/2-25, y+27, mode, TEAL, 50)
                self.text(im, text, (x+8,y+84,r-8,b-11), 21, WHITE, True)
        self.credit(im, '出典  IPAの案内・事業者の公表資料')

    def ending(self, im, row, local):
        if row is not None and (not self.short or local<2.4):
            if not self.short:
                self.title(im, '自分の情報に合わせて対処する')
            self.presenters(im, row, local, '対象を確認\n必要な対処へ')
        elif self.short:
            self.title(im, '漏れた情報に\n合わせて動こう', 35)
            self.cards(im, [('公式で確認','何が対象かを確かめる'), ('認証を守る','使い回しを見直す'),
                            ('取引を確認','不明な請求は正規窓口へ')], None)
            self.credit(im, '10事例と出典は本編・概要欄へ')
        else:
            self.title(im, 'ご視聴ありがとうございました', 33)
            self.text(im, '何が対象かを確認\n情報に合わせて対処', (self.l, 169, 509, 312), 37, TEAL)
            self.text(im, '公表資料・関連記事は概要欄へ', (self.l, 345, 518, 401), 22, MUTED)
            self.box(im, (554, 154, self.r, 358), '#16263b', EDGE, 21)
            ImageDraw.Draw(im).ellipse(scaled((692, 391, 783, 482)), outline=EDGE, width=3)

    def frame(self, row, local, at, progress):
        chapter = row['chapter'] if row else 'ending'
        im = backdrop(self.short, chapter in RANK).copy()
        label = {
            'opening':'2026年 日本の情報漏えい', 'method':'ランキングの読み方',
            'ai':'攻撃の背景', 'identity':'本人確認書類', 'actions':'漏えい後の対処',
            'ending':'今回のまとめ', 'examples':'公表事例から考える',
        }.get(chapter, '2026年 日本の情報漏えい Top10')
        self.header(im, label, progress)
        active = 0 if local<2.0 else 1 if local<5.0 else 2
        if chapter in RANK or chapter == 'examples':
            key = chapter if chapter in RANK else ('r01' if row['id']=='s03' else 'r03')
            self.rank(im, key, row, local, active)
        elif chapter == 'opening':
            self.opening(im, row, local)
        elif chapter == 'method':
            self.method(im, row['visual'], active)
        elif chapter == 'ai':
            self.ai(im, row, local, active)
        elif chapter == 'identity':
            self.identity(im, row, local, active)
        elif chapter == 'actions':
            self.actions(im, row, local, active)
        else:
            self.ending(im, row, local)
        if row:
            self.caption(im, row, at)
        return im
