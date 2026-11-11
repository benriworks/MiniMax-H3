"""Build a frozen visual revision from v02; preserve voices and exact cut timing."""
from pathlib import Path
P=Path(__file__).resolve().parent
s=(P/'remake_v02.py').read_text(encoding='utf-8')
replacements={
"HERE.name/'v02'":"HERE.name/'v03'",
"terra-explained-v02.mp4":"terra-explained-v03.mp4",
"from tools.studio.dialogue_avatar import PairAtlas,SpriteAtlas,DialogueDriver":"from tools.studio.dialogue_avatar import DialogueDriver,mouth_patch,registered_translation",
'''    avatars=ROOT/'outputs/productions/LONG_20261026_dots_transfer_detail/v03/avatars'
    return PairAtlas(avatars/'intro-atlas.png'),{s:SpriteAtlas(avatars/(s+'-atlas.png'),s) for s in ['male','female']}''':'''    sheet=Image.open(OUT/'standing-atlas.png').convert('RGB');h=sheet.height//3
    closed=sheet.crop((0,0,sheet.width,h));variants={None:closed}
    boxes={'male':(.400,.190,.442,.240),'female':(.545,.240,.590,.300)}
    for i,speaker in enumerate(['male','female']):
        opened=sheet.crop((0,(i+1)*h,sheet.width,(i+2)*h));opened,_=registered_translation(closed,opened)
        variants[speaker]=mouth_patch(closed,opened,boxes[speaker])
    class Pair:
        def frame(self,speaker):return variants[speaker].crop((159,0,806,h))
    class Portrait:
        def __init__(self,speaker):self.speaker=speaker
        def frame(self,emotion,opened,size):
            box=(285,0,485,210) if self.speaker=='male' else (470,30,665,235)
            return variants[self.speaker if opened else None].crop(box).resize((size,size),Image.Resampling.LANCZOS)
    return Pair(),{s:Portrait(s) for s in ['male','female']}''',
'''def plan():
    turns=[];cursor=3''':'''def plan():
    previous=ROOT/'outputs/content-projects'/HERE.name/'v02'
    p=json.loads((previous/'timing.json').read_text(encoding='utf-8'))
    shutil.copyfile(previous/'mix.wav',OUT/'mix.wav');save(OUT/'timing.json',p)
    return p
def unused_original_plan():
    turns=[];cursor=3''',
'''    clip=ROOT/'outputs/characters/dots-duo-opening-20261026/v01/dots-duo-opening-v01.mp4'
    introdir=OUT/'intro';introdir.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(clip),'-t','3','-vf','fps=24,scale=1000:562','-y',str(introdir/'%03d.png')],check=True)''':"    clip=OUT/'standing-atlas.png'",
'''        base.text(d,(65,92),'GPT-6.1 TERRA  /  BENRIWORKS',30)
        base.text(d,(65,210),'画像がわかると、',68);base.text(d,(65,310),'仕事はどう変わる？',68)
        base.pill(d,(65,455,1015,532),headings[kind],size=34)''':'''        center(d,(65,85,1015,145),'GPT-6.1 TERRA  /  BENRIWORKS',30)
        center(d,(65,190,1015,395),'画像がわかると、\\n仕事はどう変わる？',68,gap=24)
        d.rounded_rectangle((65,455,1015,532),24,fill='#d3f49b');center(d,(65,455,1015,532),headings[kind],34)''',
'''            pic=Image.open(introdir/f'{min(72,int(sec*24)+1):03d}.png');im.paste(pic,(40,630));base.text(d,(65,1280),'いつもの二人と、使いどころを確認',38)''':"            pic=pair.frame(None).resize((1000,840));im.paste(pic,(40,570))",
'''            pic=pair.frame(opened).resize((1000,562));im.paste(pic,(40,650));base.text(d,(80,1250),'疑問を聞く → 実例を見る → 判断する',36)''':"            pic=pair.frame(opened).resize((1000,840));im.paste(pic,(40,570))",
'''            for j,line in enumerate(lines):base.fittext(d,(85,1540+j*75),line,49,900,fill='white')''':"            center(d,(45,1500,1035,1735),current,49,fill='white',gap=22)",
'''        else:base.text(d,(85,1570),'GPT-6.1 Terraを、二人で確認。',46,fill='white')''':"        else:center(d,(45,1500,1035,1735),'GPT-6.1 Terraを、二人で確認。',46,fill='white')",
'''        base.text(d,(65,1800),'公式情報確認：2026.10.31',26);base.text(d,(65,1845),'出典：OpenAI公式資料 ／ 架空素材でのAPI確認',24)''':"        center(d,(65,1780,1015,1825),'公式情報確認：2026.10.31',26);center(d,(65,1830,1015,1880),'出典：OpenAI公式資料 ／ 架空素材でのAPI確認',24)",
"'new_minimax_calls':0":"'new_minimax_calls':0,'new_tts_calls':0,'layout_metrics':LAYOUT,'visual_method':'standing image atlas and original PCM mouth gate; original bowed intro clip removed'"
}
for old,new in replacements.items():
    if old not in s:raise ValueError('Frozen source changed: '+old[:70])
    s=s.replace(old,new)
# Center the other single-column copy and icon labels in their own visual regions.
for old,new in [
("base.text(d,(65,1260),","center(d,(65,1240,1015,1340),"),
("base.text(d,(65,1380),","center(d,(65,1360,1015,1435),"),
("base.text(d,(65,990),","center(d,(65,960,1015,1050),"),
("base.text(d,(65,655),","center(d,(65,620,1015,735),"),
("base.text(d,(65,815),","center(d,(65,780,1015,895),"),
("base.text(d,(65,995),","center(d,(65,960,1015,1045),"),
("base.text(d,(65,650),","center(d,(65,620,1015,735),"),
("base.text(d,(65,795),","center(d,(65,765,1015,865),"),
("base.text(d,(65,940),","center(d,(65,905,1015,975),"),
("base.text(d,(65,1000),","center(d,(65,985,1015,1060),"),
("base.text(d,(100+j*340,860),","center(d,(65+j*340,845,295+j*340,930),"),
("base.text(d,(275,620+j*155),","center(d,(275,610+j*155,1015,675+j*155),"),
("base.text(d,(275,685+j*155),","center(d,(275,680+j*155,1015,735+j*155),")]:s=s.replace(old,new)
helper='''LAYOUT={}
INK_CACHE={}
def ink_bounds(line,size,d):
    key=(line,size)
    if key not in INK_CACHE:
        f=base.font(size);b=d.textbbox((0,0),line,font=f)
        mask=Image.new('L',(b[2]-b[0]+24,b[3]-b[1]+24),0)
        ImageDraw.Draw(mask).text((12-b[0],12-b[1]),line,font=f,fill=255)
        q=mask.getbbox()
        INK_CACHE[key]=(q[0]-12+b[0],q[1]-12+b[1],q[2]-12+b[0],q[3]-12+b[1])
    return INK_CACHE[key]
def center(d,box,copy,size,fill='#16382c',gap=20):
    lines=copy.split('\\n');f=base.font(size);bounds=[ink_bounds(line,size,d) for line in lines]
    heights=[b[3]-b[1] for b in bounds];total=sum(heights)+gap*(len(lines)-1)
    if total>box[3]-box[1]-12:raise ValueError('Text too tall: '+copy)
    top=(box[1]+box[3]-total)/2;rects=[]
    for line,b,h in zip(lines,bounds,heights):
        w=b[2]-b[0]
        if w>box[2]-box[0]-24:raise ValueError('Text too wide: '+line)
        left=(box[0]+box[2]-w)/2
        d.text((left-b[0],top-b[1]),line,font=f,fill=fill)
        rects.append([left,top,left+w,top+h]);top+=h+gap
    key=str(box)+copy
    LAYOUT[key]={'text':copy,'region':box,'ink_boxes':rects,'center_error_px':[abs((r[0]+r[2])/2-(box[0]+box[2])/2) for r in rects],'vertical_center_error_px':abs((rects[0][1]+rects[-1][3])/2-(box[1]+box[3])/2)}

'''
s=s.replace('def render():',helper+'def render():')
(P/'revise_v03.py').write_text(s,encoding='utf-8')
print('Built frozen v03 visual revision')
