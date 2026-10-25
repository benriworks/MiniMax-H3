"""Native editorial graphics, kept separate from real application captures."""
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
BG='#f3f1eb';INK='#183e35';MUTED='#62736d';LIME='#d7ed78';BLUE='#376cb3';WHITE='#ffffff'
W,H=1920,1080


def font(n):
    value=ImageFont.truetype(str(FONT),n)
    value.set_variation_by_axes([600])
    return value
def text(d,xy,s,size=40,fill=INK):d.text(xy,s,font=font(size),fill=fill,spacing=12)
def box(d,coords,fill=WHITE,outline=None,r=20):d.rounded_rectangle(coords,radius=r,fill=fill,outline=outline,width=2)
def wrap(s,n):return '\n'.join(s[i:i+n] for i in range(0,len(s),n))


def note_lines(s):
    result=[]
    for paragraph in s.splitlines():
        line=''
        for token in re.findall(r'[A-Za-z0-9_,.-]+|.',paragraph):
            if line and font(42).getlength(line+token)>375 and token not in '。、？！':
                result.append(line);line=''
            line+=token
        if line:result.append(line)
    return '\n'.join(result)


def base(chapter,title):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,14),fill=INK)
    text(d,(70,40),'dots  /  実演でわかる自動転記',28,MUTED)
    box(d,(1490,40,1850,93),LIME,r=25);text(d,(1513,48),'架空データ・デモ環境',28)
    box(d,(70,106,142,174),INK,r=15);text(d,(85,110),f'{chapter:02d}',40,WHITE)
    text(d,(164,101),title,54)
    for i in range(11):
        x=70+i*162
        d.rectangle((x,886,x+148,892),fill=INK if i<chapter else '#d4dcd5')
    return im


def editorial(chapter,title,kind,rows=None,active=-1):
    im=base(chapter,title);d=ImageDraw.Draw(im)
    if kind=='mapping':
        text(d,(110,200),'元のExcelファイル',40)
        text(d,(1070,200),'システムの入力欄',40)
        fields=['案件ID','顧客名','案件名','納期','金額']
        samples=['DEMO-001','デモ顧客A','架空展示会LP','2026-11-10','120,000円']
        for i,(f,v) in enumerate(zip(fields,samples)):
            y=280+i*105
            color=LIME if i==active else WHITE
            box(d,(110,y,830,y+85),color)
            text(d,(140,y+16),f,34);text(d,(390,y+16),v,34)
            d.line((870,y+42,1020,y+42),fill=INK,width=6)
            d.polygon([(1020,y+42),(999,y+30),(999,y+54)],fill=INK)
            box(d,(1070,y,1790,y+85),color)
            text(d,(1100,y+16),f,34);text(d,(1360,y+16),v,34)
        text(d,(110,820),'3件 × 5項目 ＝ 15項目　／　列と入力欄の対応をそろえる',37)
    elif kind=='scope':
        cards=[('01 対象を決める','DEMO-001〜003の3件のみ'),('02 保存先を決める','クラウドPCの撮影用フォーム'),('03 止める条件を決める','不明な値・重複・想定外の画面')]
        for i,(a,b) in enumerate(cards):
            y=245+i*170
            box(d,(110,y,1810,y+140),LIME if i==active else WHITE)
            text(d,(150,y+18),a,42);text(d,(800,y+24),b,38)
        text(d,(130,800),'元の表は変更しない　／　最初の登録前に人の確認を待つ',40)
    elif kind=='approval':
        box(d,(110,225,1810,755),WHITE)
        text(d,(155,260),'人の確認待ち → 本人の返答 → 再開',48)
        text(d,(155,370),'「この3件を撮影用コピーへ登録してよい」',48)
        text(d,(155,490),'対象：DEMO-001・002・003　合計250,000円',39)
        text(d,(155,560),'保存先：クラウドPC内の撮影用コピー（ポート8766）',35)
        text(d,(155,650),'本人の実返答を制作チャットで取得し、dotsへ転送',32,MUTED)
        text(d,(145,800),'確認しているのは「内容」と「どこへ保存するか」',42)
    elif kind=='compare':
        keys=['案件ID','顧客名','案件名','納期','金額円']
        values=rows or [['DEMO-001','デモ顧客A','架空展示会LP','2026-11-10',120000],['DEMO-002','デモ顧客B','架空チラシ','2026-11-12',80000],['DEMO-003','デモ顧客C','架空セミナー申込','2026-11-14',50000]]
        xs=[140,420,740,1200,1550,1780]
        for y,label in [(215,'元の表'),(530,'保存後の結果')]:
            text(d,(115,y),label,35)
            box(d,(110,y+62,1810,y+292),WHITE)
            if active>=0:d.rectangle((xs[active]-15,y+63,xs[active+1]-25,y+290),fill='#e8f3b9')
            for j,k in enumerate(keys):text(d,(xs[j],y+72),k,31)
            for i,row in enumerate(values):
                for j,v in enumerate(row):
                    s=f'{v:,}' if isinstance(v,int) else str(v)
                    text(d,(xs[j],y+119+i*51),s,34)
        text(d,(1190,825),'3件 ／ 合計250,000円',36)
    elif kind=='flow':
        items=[('範囲を指定','対象・保存先・停止条件'),('人が承認','登録前に内容を確認'),('入力・確認・登録','各件の値を確かめる'),('保存後に照合','15項目・件数・合計')]
        for i,(a,b) in enumerate(items):
            x=100+i*450
            box(d,(x,300,x+400,680),LIME if i==active else WHITE)
            text(d,(x+25,330),f'{i+1:02d}',56)
            text(d,(x+25,440),wrap(a,7),39)
            text(d,(x+25,575),wrap(b,10),31,MUTED)
            if i<3:
                d.line((x+409,488,x+440,488),fill=INK,width=5)
                d.polygon([(x+440,488),(x+427,478),(x+427,498)],fill=INK)
        text(d,(120,780),'まずは架空データで、小さな範囲から。',50)
    elif kind=='boundary':
        box(d,(115,260,900,720),WHITE);box(d,(1020,260,1805,720),LIME)
        text(d,(160,300),'内容を確認',56)
        text(d,(160,420),'5項目を照合する',43)
        text(d,(160,555),'まだ保存されない',43,BLUE)
        text(d,(1060,300),'デモ登録',56)
        text(d,(1060,420),'確認済みの内容を記録',43)
        text(d,(1060,555),'ここで保存される',43)
        text(d,(130,800),'今回の保存先はクラウドPC内。通知・会計処理はなし。',38)
    elif kind=='caution':
        for i,(a,b) in enumerate([('同じID','重複登録を拒否'),('2026-02-30','存在しない日付を拒否'),('-1円','負の金額を拒否')]):
            x=110+i*580
            box(d,(x,270,x+540,695),WHITE)
            text(d,(x+30,310),a,44);text(d,(x+30,440),wrap(b,8),42)
        text(d,(130,790),'このデモで確認した制御です。すべてのミスを防ぐ保証ではありません。',34)
    elif kind=='place':
        box(d,(150,240,1770,730),WHITE)
        text(d,(220,275),'dotsのクラウドPC',58)
        text(d,(260,435),'Excelファイル',46)
        text(d,(260,520),'専用XLSXビューア',36,MUTED)
        d.line((850,500,1020,500),fill=INK,width=8)
        d.polygon([(1020,500),(990,480),(990,520)],fill=INK)
        text(d,(1110,435),'Webシステム',46)
        text(d,(1110,520),'撮影用の案件管理',36,MUTED)
        text(d,(220,640),'手元PCとは別のファイル・ソフト・ログイン状態',35)
        text(d,(160,790),'公式：learn.chatgpt.com/docs/dots/computers-and-apps',30,MUTED)
    return im


def plate(chapter,title,note):
    im=base(chapter,title).convert('RGBA');d=ImageDraw.Draw(im)
    # A wide stage for real GUI footage; editorial notes remain outside values/buttons.
    d.rectangle((70,200,1350,850),fill=(0,0,0,0))
    box(d,(1400,220,1850,825),WHITE)
    text(d,(1435,260),'この場面のポイント',30,MUTED)
    text(d,(1435,350),note_lines(note),42)
    text(d,(1435,710),'入力 → 確認 → 保存',27,MUTED)
    return im
