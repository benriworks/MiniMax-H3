"""Prepare quoted evidence and a measurable, unapproved visual draft; no paid calls."""
from pathlib import Path
import hashlib,json,shutil,sys
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,arrow,fit
from tools.studio.editorial_captions import phrase_lines,PROTECTED
from tools.studio.dialogue_avatar import SpriteAtlas
from tools.studio.editorial_presenters import equalized_face
OUT=ROOT/'outputs/content-projects'/HERE.name;ASSETS=OUT/'assets';RAW=OUT/'_private/captures'
PARENT=ROOT/'outputs/content-projects/CONTENT_20261103_model_race'
NAVY='#10283D';TEAL='#087E82';GOLD='#D3A447';MUTED='#BDD0D8';PAPER='#F7F5F0'
PROTECT=PROTECTED+('Claude Code','Anthropic','Thariq Shihipar','Anthony Morris','Cat Wu','Thariq','Anthony')
PEOPLE=[dict(id='thariq',name='Thariq Shihipar',date='10/24 発表',role='Claude Codeの開発',sid='thariq-post'),dict(id='anthony',name='Anthony Morris',date='10/24 発表',role='デスクトップ版を開発',sid='anthony-post'),dict(id='cat',name='Cat Wu',date='11/4 発表',role='Claude Codeの製品責任者',sid='cat-post')]

def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True);records=[]
    for name,original,rect,sid in [('thariq-quote','thariq-original.png',(915,57,1497,190),'thariq-post'),('anthony-quote','anthony-original.png',(915,57,1497,178),'anthony-post'),('cat-quote','cat-wu-original.png',(915,57,1497,178),'cat-post'),('official-role','cat-official-role.png',(905,458,1670,645),'cat-official-role')]:
        p=RAW/original;im=Image.open(p).convert('RGB');assert im.size==(2545,1264),(p.name,im.size)
        q=ASSETS/(name+'.png');im.crop(rect).save(q)
        records.append(dict(asset_id=name,path=q.relative_to(ROOT).as_posix(),sha256=sha(q),bytes=q.stat().st_size,source_id=sid,parent_sha256=sha(p),parent_dimensions=im.size,crop_xyxy=rect,privacy_review='Public author and short excerpt only. Account sidebar, reply editor, reactions and replies excluded.',checked_at='2026-11-04'))
    for name in ['male-atlas.png','female-atlas.png','male-thinking.mp4','female-thinking.mp4']:
        p=PARENT/'assets'/name;q=ASSETS/name
        if not q.exists():shutil.copy2(p,q)
        assert sha(p)==sha(q)
        records.append(dict(asset_id=q.stem,path=q.relative_to(ROOT).as_posix(),sha256=sha(q),source=p.relative_to(ROOT).as_posix(),reuse=True))
    save(OUT/'asset-manifest-v01.json',dict(items=records,native_source_width=2545,source_column_note='Xの本文切り出し幅582px。ページ全幅と本文幅を混同しない。拡大キーの試行は画質改善の根拠としない。原寸切り出しと日本語の要約を併用。'))

class Draft:
    def __init__(self):
        self.c=Canvas();self.images={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.stem}
        self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']}
    def text(self,im,v,r,size=54,color='white',center=True):self.c.text(im,v,r,size,color,center)
    def wrap(self,v,width=950,size=54):return '\n'.join(phrase_lines(v,width,size,protected=PROTECT))
    def base(self,label,headline):
        im=Image.new('RGB',(1080,1920),NAVY);box(im,(45,45,1035,116),GOLD if label=='考察' else TEAL,18)
        self.text(im,label,(60,51,1020,108),38,NAVY if label=='考察' else 'white')
        self.text(im,self.wrap(headline),(60,165,1020,330),54)
        return im
    def caption(self,im,text):
        lines=phrase_lines(text,930,56,protected=PROTECT)[:2];box(im,(35,1470,1045,1700),'#081B2A',20);self.text(im,'\n'.join(lines),(70,1485,1010,1680),56)
    def source(self,im,value):self.text(im,value,(60,1760,1020,1845),28,MUTED,False)
    def face(self,im,who,rect,mood='curious',opened=False):
        tile=equalized_face(self.atlas[who],who,mood,opened,rect[2]-rect[0]);im.paste(tile,(rect[0],rect[1]))
    def motion_poster(self,im,who,rect):
        p=sorted((PARENT/'motion-cache'/(who+'-thinking')).glob('*.jpg'))[65]
        source=Image.open(p);w,h=source.size;source=source.crop((round(w*.06),round(h*.28),round(w*.94),round(h*.76)))
        im.paste(ImageOps.fit(source,(rect[2]-rect[0],rect[3]-rect[1]),method=Image.Resampling.LANCZOS,centering=(.5,.42)),rect[:2])
    def frame(self,visual,caption='',person=0):
        if visual=='hook':
            im=self.base('Claude Code｜退社発表','キーマン3人が退社')
            self.text(im,'改善を続けられるか？',(60,350,1020,435),56,GOLD)
            self.motion_poster(im,'male',(45,540,445,1300))
            for i,p in enumerate(PEOPLE):
                y=510+i*255;box(im,(475,y,1030,y+220),'#1D4156',18)
                self.text(im,p['name'],(485,y+20,1020,y+84),36)
                self.text(im,p['date']+'（JST）',(485,y+98,1020,y+155),36,GOLD)
            self.source(im,'出典：各氏の本人投稿。2026年11月4日確認。')
        elif visual in ['question','impact-question']:
            question='どんな人たちが離れた？' if visual=='question' else '開発への影響は？'
            im=self.base('視聴者の疑問',question)
            self.face(im,'male',(65,620,465,1020),'curious',False);self.face(im,'female',(615,620,1015,1020),'serious',False)
            self.text(im,'本人発表と考察を分けて見る',(60,1150,1020,1230),44,MUTED)
        elif visual=='evidence':
            p=PEOPLE[person];im=self.base('本人の発表',p['name'])
            self.text(im,p['date']+'（日本時間）',(70,355,1010,435),48,GOLD)
            self.text(im,self.wrap(p['role'],950,48),(65,495,1015,665),48)
            box(im,(45,750,1035,1120),'#000000',18);fit(im,self.images[p['id']+'-quote'],(65,770,1015,1090))
            self.text(im,'退社を発表',(90,1190,990,1290),60,'#91D5D4')
            self.source(im,'引用：'+p['name']+' 本人のX投稿\n発表日と最終勤務日は別。2026年11月4日確認。')
        elif visual=='analysis':
            im=self.base('考察','使いやすさを作る知見を、引き継げるか')
            fit(im,self.images['official-role'],(55,360,1025,650))
            box(im,(65,740,1015,1310),PAPER,24)
            self.text(im,'モデル ＋ 製品の仕組み',(90,765,990,850),48,TEAL)
            steps=['コードの修正を頼む','変更を確かめる','必要な所を直す']
            for i,v in enumerate(steps):
                y=890+i*132;box(im,(130,y,950,y+90),'#DCE9EC',16);self.text(im,v,(150,y+12,930,y+78),46,NAVY)
                if i<2:arrow(im,[(540,y+92),(540,y+128)],TEAL,6)
            self.source(im,'引用：Claude公式 Cat Wu氏のPM記事（2026年3月）\n退社の影響を実測した図ではない。')
        else:
            im=self.base('今後、見るところ','機能改善・使い勝手・安定性')
            self.motion_poster(im,'female',(45,440,495,1220))
            for i,v in enumerate(['機能が改善されるか','操作で迷わないか','安心して使えるか']):
                y=510+i*225;box(im,(535,y,1035,y+170),'#1D4156',18);self.text(im,v,(550,y+35,1020,y+135),40)
            self.text(im,self.wrap('共通原因・開発への影響は未確認',950,48),(60,1280,1020,1430),48,GOLD)
            self.source(im,'考察は今後の観察点。将来の品質を断定しない。')
        if caption:self.caption(im,caption)
        return im

def preview():
    script=json.loads((HERE/'short-dialogue-v01-draft.json').read_text(encoding='utf-8'));d=Draft();out=OUT/'review/v01';out.mkdir(parents=True,exist_ok=True)
    shots=[('s01','hook',0),('s02','question',0),('s03a','evidence',0),('s03b','evidence',1),('s03c','evidence',2),('s04','impact-question',0),('s05','analysis',0),('s06','closing',0)]
    tiles=[]
    for sid,visual,person in shots:
        turn=next(t for t in script['turns'] if t['id']==sid[:3]);im=d.frame(visual,turn['display'],person);im.save(out/(sid+'.jpg'),quality=93);tiles.append(ImageOps.contain(im,(270,480)))
    sheet=Image.new('RGB',(270*4,480*2),NAVY)
    for i,im in enumerate(tiles):sheet.paste(im,(i%4*270,i//4*480))
    sheet.save(out/'storyboard-v01-draft.jpg',quality=93);save(out/'text-layout.json',list(d.c.audit.values()))
    print('Draft images',len(tiles),'measured text boxes',len(d.c.audit))

def article_figures():
    c=Canvas();out=OUT/'article/v01/assets';out.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(1920,1080),PAPER)
    c.text(im,'本人投稿で確認した3人の退社発表',(70,70,1850,180),62,NAVY,False)
    for i,p in enumerate(PEOPLE):
        x=60+i*620;box(im,(x,300,x+560,760),'white',24,outline=TEAL)
        c.text(im,p['name'],(x+15,330,x+545,410),43,TEAL)
        c.text(im,p['date']+'（JST）',(x+15,450,x+545,525),44,NAVY)
        c.text(im,'\n'.join(phrase_lines(p['role'],500,43,protected=PROTECT)),(x+25,570,x+535,720),43,NAVY)
    c.text(im,'発表日と最終勤務日は別。2026年11月4日確認。',(70,850,1850,925),38,NAVY,False)
    c.text(im,'出典：Thariq Shihipar、Anthony Morris、Cat Wu 各氏の本人投稿／Cat Wu氏の役割はClaude公式記事。',(70,970,1850,1035),28,NAVY,False)
    im.save(out/'departures-timeline.png')
    im=Image.new('RGB',(1920,1080),PAPER)
    c.text(im,'コードを直すときの使いやすさを磨く',(70,70,1850,180),62,NAVY,False)
    c.text(im,'製品作りの知見を、チームが引き継げるか（考察）',(70,200,1850,280),44,TEAL,False)
    for i,(head,body) in enumerate([('依頼する','このコードを\n直してほしい'),('変更を見る','どこを変えたか\n確かめる'),('必要なら直す','気になる所を\nもう一度伝える')]):
        x=70+i*620;box(im,(x,370,x+540,775),'white',24,outline=TEAL)
        c.text(im,head,(x+20,405,x+520,485),50,TEAL)
        c.text(im,body,(x+25,540,x+515,715),45,NAVY)
        if i<2:arrow(im,[(x+550,570),(x+600,570)],TEAL,9)
    c.text(im,'今後の観察点：機能改善、使い勝手、安定性',(70,865,1850,950),42,NAVY,False)
    c.text(im,'自作の説明例。退社の共通原因や、実際の開発・品質への影響を確認した図ではない。',(70,980,1850,1040),30,NAVY,False)
    im.save(out/'product-handoff-observation.png');save(OUT/'article/v01/figure-layout.json',list(c.audit.values()))

if __name__=='__main__':prepare();preview();article_figures()
