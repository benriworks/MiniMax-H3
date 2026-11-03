"""Prepare preserved official excerpts, reused approved assets and research figures.

No paid calls, no model benchmarking, no implied editorial acceptance.
"""
from pathlib import Path
import hashlib,json,shutil,sys
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,fit,arrow

OUT=ROOT/'outputs/content-projects'/HERE.name
ASSETS=OUT/'assets'
INK='#10283D';PAPER='#F7F5F0';TEAL='#117E85';COPPER='#BA684E';GOLD='#9D6C16';PURPLE='#7259A6'

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True)
    raw=OUT/'_private/captures'
    crops=[
      ('fable5','fable-launch.png',(40,180,1180,1050),'fable5','Launch heading, product art and published date; 14 English words'),
      ('astra','astra-launch.png',(20,85,1205,1140),'astra','Official product art and model lettering; 3 English words'),
      ('fable51','fable51-heading.png',(190,430,1060,660),'fable51','September and model heading only; 11 English words'),
      ('sol61','sol61-launch.png',(220,685,1015,820),'sol61','Short Japanese official headline only; no body paragraph'),
      ('opus55','opus55-heading.png',(205,480,1020,670),'opus55','Date and model heading only; 8 English words')]
    manifest=[]
    for name,source,rect,sid,note in crops:
        path=raw/source
        image=Image.open(path).convert('RGB')
        assert image.width>=1200 and max(rect[::2])<=image.width and max(rect[1::2])<=image.height
        dest=ASSETS/(name+'.png')
        image.crop(rect).save(dest)
        manifest.append(dict(record(dest),kind='official_excerpt',source_id=sid,raw=record(path),crop_xyxy=rect,note=note,original_dimensions=image.size,privacy_review='passed: public page only',checked_at='2026-11-03'))
    for name,rect,note in [('astra62-post-author',(180,58,745,112),'Public author attribution only'),('astra62-usage-image',(182,330,743,526),'Only the posted usage image. Authenticity unverified; percentages are not benchmark scores.')]:
        path=raw/'astra62-post-browser.png';image=Image.open(path).convert('RGB');dest=ASSETS/(name+'.png');image.crop(rect).save(dest)
        manifest.append(dict(record(dest),kind='social_excerpt',source_id='astra62-post',raw=record(path),crop_xyxy=rect,note=note,original_dimensions=image.size,privacy_review='passed: account sidebar, unrelated replies and engagement excluded',checked_at='2026-11-03'))
    old=ROOT/'outputs/content-projects/CONTENT_20261101_tibo_28day_full/assets'
    for name in ['male-atlas.png','female-atlas.png','intro-atlas.png','male-understanding.mp4','female-thinking.mp4','female-happy.mp4']:
        dest=ASSETS/name
        if not dest.exists():shutil.copy2(old/name,dest)
        assert record(dest)['sha256']==record(old/name)['sha256']
        manifest.append(dict(record(dest),kind='reused_approved_character' if name.endswith('.png') else 'reused_minimax_motion',source=record(old/name)))
    save(OUT/'asset-manifest.json',dict(checked_at='2026-11-03',items=manifest,private_originals_excluded_from_git=True,native_capture_width=1237,article_note='Native website captures below 1400px target; no upscaled-source claim. Research diagrams exported at 1920px.'))
    return manifest

def diagram(kind):
    c=Canvas();im=Image.new('RGB',(1920,1080),PAPER);d=ImageDraw.Draw(im)
    wording={x['id']:x['display'] for x in json.loads((HERE/'wording-v03.json').read_text(encoding='utf-8'))['entries']}
    c.text(im,'AI MODEL RACE 2026',(60,25,1860,85),34,TEAL,False)
    if kind=='timeline':
        c.text(im,'2社の競争を、主要な転機で見る',(60,100,1860,185),62,INK,False)
        positions=[370,690,1130,1590]
        for x,head in zip(positions,['6月','7月','9月','9月後半']):
            c.text(im,head,(x-150,235,x+150,290),34,INK)
            d.line((x,310,x,855),fill='#E0E2E1',width=3)
        for y,color,name in [(425,COPPER,'Anthropic'),(735,TEAL,'OpenAI')]:
            c.text(im,name,(60,y-28,310,y+28),36,color,False)
            d.line((330,y,1800,y),fill=color,width=8)
        for x,y,head,body,color in [(370,425,'6/9  Fable 5',wording['fable5'],COPPER),(690,425,'7/24  Opus 5',wording['opus5'],COPPER),(1130,425,'9月  Fable 5.1',wording['fable51'],COPPER),(1590,425,'9/22  Opus 5.5',wording['opus55'],COPPER),(1130,735,'9/3  GPT-6 Astra',wording['astra'],TEAL),(1590,735,'9/29  GPT-6.1 Sol',wording['sol61'],TEAL)]:
            w=395 if x>800 else 300
            d.ellipse((x-12,y-12,x+12,y+12),fill=color)
            box(im,(x-w/2,y+33,x+w/2,y+185),'white',17,outline=color)
            c.text(im,head,(x-w/2+10,y+44,x+w/2-10,y+96),28,color)
            c.text(im,body,(x-w/2+10,y+103,x+w/2-10,y+175),28,INK)
        c.text(im,'Fable 5は6/12停止→7/1再開。Fable 5.1は日付表記差のため月まで。',(60,945,1860,1000),30,INK,False)
        c.text(im,'主要な転機の整理。横幅は日数・性能を表さない。出典：各社公式発表／API更新履歴。2026-11-03確認。',(60,1015,1860,1055),25,'#4D6272',False)
    elif kind=='prices':
        c.text(im,'「5分の1」は、標準APIの単価',(60,105,1860,190),64,INK,False)
        c.text(im,'100万トークンあたり／USD／2026-11-03確認',(60,220,1860,280),36,TEAL,False)
        for top,title,values,maximum in [(345,'入力',[10,2],10),(620,'出力',[50,10],50)]:
            c.text(im,title,(65,top,315,top+65),44,INK,False)
            for i,(name,value,color) in enumerate(zip(['GPT-6 Astra','GPT-6.1 Sol'],values,[COPPER,TEAL])):
                y=top+78+i*80
                c.text(im,name,(80,y,440,y+55),34,INK,False)
                box(im,(470,y+7,470+1100*value/maximum,y+51),color,8)
                c.text(im,f'${value}',(500+1100*value/maximum,y,650+1100*value/maximum,y+55),40,color,False)
        c.text(im,'月額料金や、仕事の総額が5分の1という意味ではない。',(60,935,1860,995),38,INK,False)
        c.text(im,'入力と出力は別の軸。長い入力・キャッシュ・ツール等は条件が異なる。出典：OpenAI公式Sol発表・モデル仕様。',(60,1015,1860,1055),25,'#4D6272',False)
    else:
        c.text(im,'次世代情報は、根拠を分ける',(60,105,1860,190),64,INK,False)
        for top,name,status,detail,color in [(305,'Fable 5.5','名称は未確認','次期モデルの報道と、呼び名の噂は別',GOLD),(510,'GPT-6.1 Astra','公開見送りの報道','近日登場の予定として紹介しない',PURPLE),(715,'GPT-6.2 Astra','投稿の画像は出所不明','投稿者が他者提供・元の出所不明と補足',GOLD)]:
            box(im,(60,top,1860,top+170),'white',20,outline=color)
            c.text(im,name,(90,top+20,680,top+83),48,INK,False)
            c.text(im,status,(720,top+20,1790,top+83),44,color,False)
            c.text(im,detail,(90,top+100,1790,top+147),35,INK,False)
        c.text(im,'2026-11-03時点。正式発表・一般提供・自分の利用可能状態は、それぞれ別。',(60,945,1860,1002),34,INK,False)
        c.text(im,'出典：The Information公開見出し／WSJ公開導入／TokenGremlinの原投稿と補足。一般提供・性能・日付は未確認。',(60,1015,1860,1055),25,'#4D6272',False)
    save(OUT/'research-figures'/(kind+'-v03-layout.json'),list(c.audit.values()))
    dest=OUT/'research-figures'/(kind+'-v03.png');dest.parent.mkdir(parents=True,exist_ok=True);im.save(dest)
    return dest

def review_texts():
    dest=OUT/'review/v03';dest.mkdir(parents=True,exist_ok=True)
    for source,name in [('PROPOSAL_JA.md','01_企画v01_回答反映.txt'),('ARTICLE_DRAFT_V03_JA.md','07_記事草稿v03.txt')]:
        (dest/name).write_text((HERE/source).read_text(encoding='utf-8'),encoding='utf-8')
    for kind,name in [('short','05_ショート会話草稿.txt'),('full','06_フル会話草稿.txt')]:
        script=json.loads((HERE/f'{kind}-dialogue-v03.json').read_text(encoding='utf-8'))
        text='会話原稿v03／企画v01の大筋をユーザー確認。公式表現に基づく見出しと原稿へ修正。完成動画の採用・公開は別。\n\n'
        for t in script['turns']:
            text+=f"{t['id']}／第{t['chapter']}章／{'男性' if t['speaker']=='male' else '女性'}\n{t['display']}\n\n"
        (dest/name).write_text(text,encoding='utf-8')

if __name__=='__main__':
    prepare()
    for kind in ['timeline','prices','rumors']:print(diagram(kind))
    review_texts()
