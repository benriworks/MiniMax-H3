"""Draw the data, the observed demo, and the established two presenters."""
from functools import lru_cache

from PIL import Image, ImageDraw, ImageOps

from prepare import FIGURES, HERE, MOTION, SOURCES
from tools.studio.editorial_captions import PROTECTED
from tools.studio.explainer_canvas import Canvas, box, fit, glyph

PAPER, WHITE, INK, SOFT = "#F5F2E9", "#FFFFFF", "#172C2C", "#4E6761"
TEAL, MINT, RED, PEACH = "#17685B", "#E1ECE4", "#A94323", "#F8E4D9"
LINE, DARK = "#D7D4C8", "#172D2B"
PROTECT = (*PROTECTED, "Upper middle", "Claude Code", "Anthropic", "1.91倍", "121の国・地域",
           "6.40", "3.87", "3.78", "2026年5月", "11月20日", "6月26日", "AWS", "54％", "60％",
           "提案書テンプレート", "青葉製作所", "日報集計", "エージェント", "見積金額")
AEI = "出典　Anthropic Economic Index｜2026年5月"
AWS = "出典　AWS 日本企業調査｜2026年11月12日"
LIVE = "Claude Code 実行結果｜架空の会議メモ"
NOTES = {
    "s-aws": "会社での導入状況は？", "s-demo": "最初に試す仕事は？",
    "f-map": "データは2026年5月", "f-bars": "差はどれくらい？",
    "f-reading": "何を数えている？", "f-aws": "職場ではどう使う？",
    "f-input": "会議の次の作業を出す", "f-pilot": "続けて使うには？",
}
TABLE = [tuple(part.strip() for part in line.strip("|").split("|"))
         for line in (HERE / "demo-result-v01.md").read_text(encoding="utf-8").splitlines()
         if line.startswith("| ")][1:]


@lru_cache(maxsize=256)
def portrait(clip, frame, width, height):
    path = MOTION / clip / f"{frame+1:03d}.jpg"
    with Image.open(path) as picture:
        shot = picture.crop((16, 200, 464, 678))
        cropped = ImageOps.fit(shot, (width, height), Image.Resampling.LANCZOS, centering=(.5, .37))
    mask = Image.new("L", cropped.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=24, fill=255)
    return cropped, mask


class Editor:
    def __init__(self, kind, *, show_role_labels=True):
        self.short = kind == "short"
        self.show_role_labels = show_role_labels
        self.w, self.h = (1080, 1920) if self.short else (1920, 1080)
        self.x, self.r = (67, 945) if self.short else (77, 1843)
        self.y, self.b = (340, 1373) if self.short else (193, 850)
        self.caption = (51, 1432, 969, 1642) if self.short else (75, 911, 1845, 1045)
        self.size = 49 if self.short else 44
        self.canvas = Canvas()
        self.photos = {}
        self.short_closing = ("1つの仕事から", "下書き → 確認 → チームで共有")

    def text(self, im, value, rect, size, color=INK, center=False):
        self.canvas.text(im, value, rect, size, color, center=center)

    def photo(self, im, name, rect):
        if name not in self.photos:
            with Image.open(FIGURES / (name + ".webp")) as opened:
                self.photos[name] = opened.convert("RGB")
        x, y, r, b = rect
        box(im, rect, WHITE, outline=LINE, width=2)
        fit(im, self.photos[name], (x+12, y+12, r-12, b-12))

    def cards(self, im, rows, rect, active=0, numerals=False):
        x, y, r, b = rect
        gap = 15
        step = (b - y + gap) // len(rows)
        for i, (head, label) in enumerate(rows):
            top, bottom = y + i*step, y + (i+1)*step - gap
            on = i == active
            middle = (top+bottom)//2
            box(im, (x, top, r, bottom), MINT if on else WHITE, outline=LINE, width=2)
            size = (87 if self.short else 72) if numerals else (51 if self.short else 45)
            self.text(im, head, (x+28, top+10, r-25, middle+15), size, TEAL if on else INK)
            self.text(im, label, (x+28, middle-2, r-25, bottom-15), 34 if self.short else 35, SOFT)

    def duo(self, im, chapter, speaker, motion):
        x, y, r, b = self.x, self.y, self.r, self.b
        hook = chapter.endswith("hook")
        ending = chapter.endswith("end")
        word, detail = ("32位", "121の国・地域｜Claude利用指数") if hook else self.short_closing
        if self.short:
            box(im, (x, y, r, y+297), MINT if hook else PEACH, radius=30)
            self.text(im, word, (x+20, y+23, r-20, y+198), 136 if hook else 81, TEAL if hook else RED, True)
            self.text(im, detail, (x+20, y+205, r-20, y+275), 36, SOFT, True)
            y += 327
            center = (x+r)//2
            rects = [(x, y, center-11, b-48), (center+11, y, r, b-48)]
        else:
            width = 575
            rects = [(x, y, x+width, b-47), (x+width+22, y, x+2*width+22, b-47)]
            edge = x+2*width+48
            box(im, (edge, y+85, r, b-119), MINT if hook else PEACH, radius=30)
            self.text(im, word if hook else "1つの仕事", (edge+20, y+110, r-20, y+340),
                      142 if hook else 74, TEAL if hook else RED, True)
            text = "121の国・地域" if hook else "下書き・確認・共有"
            self.text(im, text, (edge+25, y+350, r-25, b-150), 42, SOFT, True)
        for person, rect in zip(("male", "female"), rects, strict=True):
            clip = ("male-happy" if ending else "male-thinking") if person == "male" else (
                "female-happy" if ending else "female-understanding")
            self.person(im, clip, motion if person == speaker else 0, rect)
            if person == speaker:
                ImageDraw.Draw(im).rounded_rectangle(rect, radius=24, outline=TEAL, width=5)
            if self.show_role_labels:
                left, _, right, bottom = rect
                self.text(im, "聞き役" if person == "male" else "実務役",
                          (left, bottom+10, right, bottom+48), 28, SOFT, True)
        return AEI if hook else None

    @staticmethod
    def person(im, clip, frame, rect):
        x, y, r, b = rect
        picture, mask = portrait(clip, frame, r-x, b-y)
        im.paste(picture, (x, y), mask)

    def presenter(self, im, chapter, speaker, motion):
        x, y, r, b = self.x, self.y, self.r, self.b
        clip = "male-thinking" if speaker == "male" else "female-understanding"
        label = NOTES[chapter]
        if self.short:
            self.person(im, clip, motion, (x+74, y, r-74, b-207))
            box(im, (x, b-180, r, b), MINT)
            self.text(im, label, (x+24, b-167, r-24, b-10), 53, TEAL, True)
        else:
            self.person(im, clip, motion, (x, y, x+731, b))
            box(im, (x+762, y+97, r, b-98), MINT)
            self.text(im, label, (x+784, y+107, r-25, b-111), 66, TEAL, True)

    def score(self, im, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        rows = [("32位 / 121の国・地域", "日本は上から2番目の区分"),
                ("利用指数 1.91", "人口比と同じなら 1.0")]
        if self.short:
            self.photo(im, "country", (x, y, r, y+414))
            self.cards(im, rows, (x, y+445, r, b), min(phase, 1))
        else:
            self.photo(im, "country", (x, y, x+1070, b))
            self.cards(im, rows, (x+1100, y, r, b), min(phase, 1))
        return AEI

    def map(self, im):
        x, y, r, b = self.x, self.y, self.r, self.b
        # The original map and its English legend stay together.
        self.photo(im, "map", (x, y, x+1130, b))
        rows = [("Leading", "上位4分の1"),
                ("Upper middle", "日本はここ"),
                ("Lower middle", "下から2番目の層"),
                ("Emerging", "下位4分の1")]
        self.cards(im, rows, (x+1160, y, r, b+14), 1)
        return AEI

    def bars(self, im):
        x, y, r, b = self.x, self.y, self.r, self.b
        box(im, (x, y, r, b), WHITE, outline=LINE, width=2)
        left, right = x+(205 if self.short else 279), r-(143 if self.short else 208)
        top, bottom = y+86, b-133
        line = ImageDraw.Draw(im)
        baseline = round(left+(right-left)/7)
        line.line((baseline, top+14, baseline, bottom+17), fill=RED, width=3)
        self.text(im, "1.0", (baseline-34, bottom+25, baseline+34, bottom+70), 34, RED, True)
        self.text(im, "人口比どおり", (left+10, bottom+75, right, bottom+117), 29, SOFT)
        line.line((left, bottom+17, right, bottom+17), fill=LINE, width=2)
        for i, (_, label, value) in enumerate(SOURCES["data"]["indices"]):
            center = round(top + (bottom-top)*(i+.5)/4)
            tint = TEAL if label == "日本" else "#82AC9D"
            tip = round(left + (right-left)*value/7)
            line.rounded_rectangle((left, center-27, tip, center+27), radius=11, fill=tint)
            self.text(im, label, (x+33, center-35, left-10, center+35), 45, TEAL if label == "日本" else INK)
            self.text(im, f"{value:.2f}", (tip+15, center-35, r-20, center+35), 41,
                      TEAL if label == "日本" else SOFT)
        return AEI

    def method(self, im, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        rows = [("日本の会話の割合", "Claude全体の会話のうち 3.28％"),
                ("÷ 働く年齢の人口の割合", "15〜64歳の世界人口に占める割合"),
                ("利用指数 1.91", "個人向けチャット・Coworkの会話量")]
        self.cards(im, rows, (x, y, r, b), phase)
        return AEI

    def work(self, im, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        self.cards(im, [("日本の会話　47.0％", "Claudeの会話のうち仕事向け"),
                        ("世界の会話　43.4％", "世界全体でも会話が分母")], (x, y, r, b), phase % 2)
        return AEI

    def aws(self, im, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        if self.short:
            self.cards(im, [("43％ → 54％", "日本企業のAI導入率"),
                            ("60％", "導入済み企業のうち、基礎的な活用が中心")],
                       (x, y, r, b), min(phase, 1), numerals=True)
        else:
            self.photo(im, "aws-points", (x, y, r, y+382))
            center = (x+r)//2
            self.cards(im, [("43％ → 54％", "日本企業のAI導入率")],
                       (x, y+401, center-12, b), 0 if phase == 0 else -1, numerals=True)
            self.cards(im, [("60％", "基礎的な活用が中心｜導入済み企業")],
                       (center+12, y+401, r, b), 0 if phase else -1, numerals=True)
        return AWS

    def input(self, im, prompt, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        rows = [("決定", "配布資料はA4片面"),
                ("原稿案", "制作担当・11月20日まで"),
                ("印刷見積もり", "購買担当・期限は未定")]
        if prompt:
            rows = [("決定事項を抜き出す", "次の作業とは分けて表示"),
                    ("作業・担当・期限の表に", "メモにない項目は「未定」"),
                    ("会議の日付を流用しない", "11月24日は次回の打ち合わせ日")]
        self.cards(im, rows, (x, y, r, b), phase)
        return "実演の入力｜架空の会議メモ"

    def output(self, im, compare, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        if self.short:
            rows = [("原稿案を出す", "制作担当　11月20日"),
                    ("印刷の見積もりを取る", "購買担当　期限は未定")]
            self.cards(im, rows, (x, y, r, b-164), min(phase, 1))
            self.text(im, "担当と期限は元のメモで確認", (x, b-137, r, b), 40, TEAL, True)
        elif not compare:
            box(im, (x, y, r, b), WHITE, outline=LINE, width=2)
            self.text(im, "決定事項　配布する資料はA4片面", (x+34, y+24, r-32, y+127), 56)
            cols = (x+34, x+715, x+1110, r-27)
            top, height = y+152, 111
            data = [("作業", "担当", "期限"), *TABLE]
            for i, row in enumerate(data):
                hi = i == 2
                start = top+i*height
                box(im, (cols[0], start, cols[-1], start+94), PEACH if hi else MINT if i == 0 else PAPER,
                    radius=14)
                for j, value in enumerate(row):
                    self.text(im, value, (cols[j]+18, start+8, cols[j+1]-13, start+87),
                              39 if i else 35, RED if hi and j == 2 else INK)
        else:
            mid = (x+r)//2
            self.cards(im, [("元のメモ", "見積もりの期限は決まっていない"),
                            ("次回の会議日", "11月24日")], (x, y, mid-13, b), min(phase, 1))
            self.cards(im, [("表の「期限」", "見積もりの欄は「未定」"),
                            ("人が確認して共有", "担当や期限は原文に戻って見る")],
                       (mid+13, y, r, b), min(phase, 1))
        return LIVE

    def pilot(self, im, measure, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        rows = [("1チーム・2週間", "会社が認めたツールを使う"),
                ("入力できる情報を決める", "機密・顧客情報を外したメモで開始"),
                ("原文の確認を担当に割り当てる", "そのまま共有せず、内容を照合")]
        if measure:
            rows = [("普段のやり方", "作成と確認が終わるまで計る"),
                    ("AIで下書きするやり方", "入力・確認・修正を含めて計る"),
                    ("時間と修正箇所を比べる", "効果があった手順をチームで共有")]
        self.cards(im, rows, (x, y, r, b), phase)
        return "チームで試す手順の例"

    def proposal(self, im, view, phase):
        x, y, r, b = self.x, self.y, self.r, self.b
        if view == "proposal-input":
            self.cards(im, [
                ("自社の提案書テンプレート", "課題・提案内容・導入計画・見積と納期"),
                ("お客様の要件", "青葉製作所・3拠点の日報集計"),
                ("自社が提示できる条件", "まず1拠点で試行。金額と納期は要確認"),
            ], (x, y, r, b), phase)
            return "Claude Codeのエージェントが読む3資料｜架空例"
        if view == "proposal-review":
            self.cards(im, [
                ("見積金額", "根拠のある見積になっているか"),
                ("納期", "お客様と調整した日程になっているか"),
                ("約束する範囲", "試行は1拠点・全拠点展開は試行結果から判断"),
            ], (x, y, r, b), phase)
            return "提出前に人が確認"

        box(im, (x, y, r, b), WHITE, radius=30, outline=LINE, width=2)
        left, right = x+37, r-36
        self.text(im, "提案書の下書き", (left, y+28, right, y+86), 37, TEAL)
        self.text(im, "青葉製作所様", (left, y+103, right, y+187), 65)
        self.text(im, "日報集計の標準化", (left, y+190, right, y+270), 61)
        rows = [
            ("お客様の課題", "3拠点で様式が異なり、集計に週6時間"),
            ("提案内容", "Excelの日報を共通様式にそろえる"),
            ("導入計画", "1拠点で試し、集計時間と入力漏れを比較"),
            ("見積・納期", "要確認"),
        ]
        for i, (heading, detail) in enumerate(rows):
            top = y+301+i*168
            fill = PEACH if i == 3 else MINT if i == phase else PAPER
            color = RED if i == 3 else TEAL
            box(im, (left, top, right, top+146), fill, radius=16)
            self.text(im, heading, (left+20, top+15, right-20, top+67), 38, color)
            self.text(im, detail, (left+20, top+74, right-20, top+131), 34, INK)
        return "Claude Codeの提案書初稿を要約｜架空例"

    def frame(self, chapter, view, speaker, phase, motion, caption):
        im = Image.new("RGB", (self.w, self.h), PAPER)
        draw = ImageDraw.Draw(im)
        draw.rectangle((0, 0, self.w, 8), fill=TEAL)
        x, r = self.x, self.r
        self.text(im, "AI活用の現在地　2026年11月17日", (x, 62 if self.short else 30, r,
                  130 if self.short else 80), 32 if self.short else 29, RED)
        line_y = 147 if self.short else 88
        draw.line((x, line_y, r, line_y), fill=LINE, width=2)
        title = chapter["title"]
        self.text(im, title, (x, 163 if self.short else 103, r, 302 if self.short else 177),
                  59 if self.short else 58)
        key = chapter["id"]
        visuals = {
            "duo": lambda: self.duo(im, key, speaker, motion),
            "presenter": lambda: self.presenter(im, key, speaker, motion),
            "score": lambda: self.score(im, phase), "map": lambda: self.map(im),
            "bars": lambda: self.bars(im), "method": lambda: self.method(im, phase),
            "work": lambda: self.work(im, phase), "aws": lambda: self.aws(im, phase),
            "demo-in": lambda: self.input(im, False, phase), "prompt": lambda: self.input(im, True, phase),
            "demo-out": lambda: self.output(im, False, phase), "compare": lambda: self.output(im, True, phase),
            "pilot": lambda: self.pilot(im, False, phase), "measure": lambda: self.pilot(im, True, phase),
            "proposal-input": lambda: self.proposal(im, view, phase),
            "proposal-output": lambda: self.proposal(im, view, phase),
            "proposal-review": lambda: self.proposal(im, view, phase),
        }
        credit = visuals[view]()
        if credit:
            self.text(im, credit, (x, self.b+7, r, self.b+48), 27, SOFT)
        if caption:
            x0, y0, x1, y1 = self.caption
            box(im, self.caption, DARK, radius=25)
            tiles = [glyph(line, self.size, WHITE) for line in caption.split("\n")]
            gap = round(self.size*.25)
            height = sum(tile.height for tile in tiles) + gap*(len(tiles)-1)
            if height > y1-y0-22 or max(tile.width for tile in tiles) > x1-x0-55:
                raise ValueError(f"Caption cannot fit: {caption}")
            top = (y0+y1-height)//2
            for tile in tiles:
                im.paste(tile, ((x0+x1-tile.width)//2, top), tile)
                top += tile.height+gap
        return im
