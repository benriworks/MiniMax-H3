"""Portrait/landscape AI-history explainers: actual voices, local motion, diagrams."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,fit,arrow
from tools.studio.editorial_captions import timed_captions,phrase_lines,PROTECTED
from tools.studio.longform_audio import SR,read_voice,write_pcm
from frame_presenters import prepare as prepare_framed_cache

OUT=ROOT/'outputs/content-projects'/HERE.name;FPS=24
INK='#173246';TEAL='#087E82';CORAL='#B84735';BG='#FFFFFF';PALE='#EDF4F4';GOLD='#D69B3E';GREY='#6C7B85'
PROTECT=PROTECTED+('BERT','GPT','Transformer','word2vec','Self-Attention','Attention','Masked LM','ELMo','RNN','LSTM','2018年6月','2018年10月','2017年')
HEADINGS={'hook':'GPTとBERTは、学び方が違う','ngram':'次に続く言葉を、数える','nnlm':'単語の特徴と、続く確率を学ぶ','vectors':'単語を、数値の特徴へ','context':'同じ言葉でも、文脈が違う','rnn':'文を順に、情報を受け渡す','attention':'今、必要な場所へ重みを付ける','transformer':'2017年、Transformerへ','positions':'言葉の関係と、位置の情報','parallel':'学習の並列化と、生成は別','pretrain':'先に学び、用途へ合わせる','elmo':'文脈に応じた表現を学ぶ','gpt':'2018年6月、初代GPT','tokens':'処理の単位は「トークン」','not_chat':'初代GPTは、今の会話サービスと違う','bert':'2018年10月、BERT論文','masked':'前後の文から、隠した部分を予測','nsp':'文が続いていたかも、学習する','compare':'見る範囲と、学習目標を比べる','gpt_bert':'次の予測と、隠した部分の予測','example':'同じ一文で、学び方を比べる','timeline':'いくつもの工夫が、つながった','closing':'詳しい仕組みは、本編へ'}
CHAPTERS={'intro':'今日の疑問','words':'言葉を数値で表す','context':'文脈を扱う','attention':'Attention','transformer':'Transformer','pretraining':'事前学習','gpt':'初代GPT','bert':'BERT','compare':'違いを整理','closing':'まとめ','short':'BERT・GPT誕生史'}

def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
REVISIONS={'short':'v03','full':'v02'}
def dest(kind):return OUT/'release'/REVISIONS[kind]/kind
def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)

def plan(kind):
    if not (HERE/'adoption-v01.json').is_file():raise RuntimeError('Outline acceptance missing')
    script=HERE/(kind+'-dialogue-'+('v04' if kind=='short' else 'v01')+'.json')
    rows=json.loads(script.read_text(encoding='utf-8'))['turns'];turns=[];cursor=0
    w,h=(1080,1920) if kind=='short' else (1920,1080)
    for row in rows:
        p=OUT/'voice/v01'/row['id']/'voice.wav';proof=json.loads(p.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(p).upper()==next(x['sha256'] for x in proof['files'] if x['path'].endswith('voice.wav'))
        seconds=len(read_voice(p))/SR;lead=.13;tail=.32 if row['speaker']=='male' else .65
        if row['visual'] in ['transformer','attention','gpt','bert','example','compare']:tail+=.35
        if row['visual']=='closing':tail+=.9
        frames=math.ceil((lead+seconds+tail)*FPS)
        item=dict(row,start=cursor,end=cursor+frames/FPS,frames=frames,voice_start=cursor+lead,voice_seconds=seconds,voice_path=p.relative_to(ROOT).as_posix())
        item['subtitles']=timed_captions(item['display'],item['voice_start'],seconds,932 if kind=='short' else 1700,64 if kind=='short' else 50,protected=PROTECT)
        assert ''.join(s['text'].replace('\n','') for s in item['subtitles'])==item['display']
        turns.append(item);cursor=item['end']
    ending=10 if kind=='full' else 1.0
    d=dict(video_id='ai-bert-gpt-history-'+kind,revision=REVISIONS[kind],kind=kind,width=w,height=h,fps=FPS,seconds=cursor+ending,frames=round((cursor+ending)*FPS),body_seconds=cursor,ending_seconds=ending,turns=turns,source_script_sha256=sha(script))
    folder=dest(kind);folder.mkdir(parents=True,exist_ok=True);save(folder/'timeline.json',d)
    def stamp(t):
        ms=round(t*1000);hh,ms=divmod(ms,3600000);mm,ms=divmod(ms,60000);ss,ms=divmod(ms,1000);return f'{hh:02}:{mm:02}:{ss:02},{ms:03}'
    caps=[c for t in turns for c in t['subtitles']]
    (folder/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i,c in enumerate(caps))+'\n',encoding='utf-8')
    print(json.dumps(dict(kind=kind,seconds=d['seconds'],turns=len(turns),caption_states=len(caps))),flush=True)
    return d

def motion_cache():
    source=OUT/'motions/v03-q2';items=[]
    for p in source.glob('*/verification.json'):
        proof=json.loads(p.read_text(encoding='utf-8'));raw=ROOT/proof['artifact']['path'];assert sha(raw).upper()==proof['artifact']['sha256']
        cache=OUT/'motion-cache'/p.parent.name
        receipt=cache/'complete.json'
        if not receipt.exists():
            cache.mkdir(parents=True,exist_ok=True);run(['ffmpeg','-v','error','-n','-i',str(raw),'-vf','fps=24','-q:v','2',str(cache/'%04d.jpg')]);save(receipt,dict(sha256=sha(raw),frames=len(list(cache.glob('*.jpg')))))
        framed=OUT/'motion-framed-cache'/p.parent.name;framing=prepare_framed_cache(cache,framed,sha(raw))
        items.append(dict(job=p.parent.name,path=raw.relative_to(ROOT).as_posix(),sha256=sha(raw),cache=cache.relative_to(ROOT).as_posix(),framed_cache=framed.relative_to(ROOT).as_posix(),framing_applied=framing['applied'],framing_scale_range=framing['scale_range'],proof=p.relative_to(ROOT).as_posix()))
    save(OUT/'motion-provenance-v01.json',items);return items

class Renderer:
    def __init__(self,kind):
        self.kind=kind;self.short=kind=='short';self.w,self.h=(1080,1920) if self.short else (1920,1080);self.c=Canvas()
        self.body=(60,400,1020,1370) if self.short else (100,310,1820,790)
        self.motions={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'motion-cache').glob('*') if p.is_dir()}
        self.framed_jobs={p.name for p in (OUT/'motion-framed-cache').glob('*') if (p/'complete.json').exists()}
        self.motions.update({job:sorted((OUT/'motion-framed-cache'/job).glob('*.png')) for job in self.framed_jobs})
        self.refs={who:Image.open(OUT/'characters/v02'/(who+'-reference-input-v02.png')).convert('RGB') for who in ['male','female']}
    def text(self,im,s,r,size=54,color=INK,center=True):self.c.text(im,s,r,size,color,center)
    def lines(self,s,width,size):return '\n'.join(phrase_lines(s,width,size,protected=PROTECT))
    @lru_cache(maxsize=14)
    def base(self,visual,chapter):
        im=Image.new('RGB',(self.w,self.h),BG);d=ImageDraw.Draw(im)
        # Restrained scientific grid; each dot is decoration, not measured data.
        for x in range(24,self.w,48):
            for y in range(24,self.h,48):d.ellipse((x,y,x+2,y+2),fill='#EAF0F1')
        r=(48,42,1032,122) if self.short else (55,36,1865,100);box(im,r,TEAL,18)
        self.text(im,'【AI】'+CHAPTERS[chapter],(r[0]+18,r[1]+8,r[2]-18,r[3]-8),36 if self.short else 33,'white')
        title=('仕組みを知ると、見方が変わる' if visual=='closing' and not self.short else HEADINGS[visual]);r=(70,170,1010,355) if self.short else (100,130,1820,281)
        self.text(im,self.lines(title,r[2]-r[0],64 if self.short else 60),r,64 if self.short else 60)
        return im
    def card(self,im,title,value,r,color=TEAL,size=48):
        box(im,r,PALE,22,outline=color,width=3);height=80 if self.short else 64
        self.text(im,title,(r[0]+14,r[1]+16,r[2]-14,r[1]+height),36 if self.short else 32,color)
        self.text(im,value,(r[0]+18,r[1]+height+18,r[2]-18,r[3]-18),size)
    def source(self,im,s):
        r=(60,1400,1020,1500) if self.short else (100,803,1820,851)
        self.text(im,self.lines(s,r[2]-r[0],28 if self.short else 26),r,28 if self.short else 26,GREY)
    def flow(self,im,labels,local,footer=None):
        x0,y0,x1,y1=self.body;n=len(labels);p=min(n-1,int(local/1.1));d=ImageDraw.Draw(im)
        if self.short:
            gap=62;hh=min(230,((y1-y0)-gap*(n-1))//n)
            for i,label in enumerate(labels):
                yy=y0+i*(hh+gap);r=(x0+80,yy,x1-80,yy+hh);box(im,r,TEAL if i<=p else PALE,20);self.text(im,label,(r[0]+18,r[1]+18,r[2]-18,r[3]-18),52,'white' if i<=p else INK)
                if i<n-1:arrow(im,[(540,yy+hh+8),(540,yy+hh+gap-12)],CORAL,8)
        else:
            gap=55;ww=((x1-x0)-gap*(n-1))//n;yy=y0+70;hh=230
            for i,label in enumerate(labels):
                xx=x0+i*(ww+gap);r=(xx,yy,xx+ww,yy+hh);box(im,r,TEAL if i<=p else PALE,20);self.text(im,label,(xx+14,yy+18,xx+ww-14,yy+hh-18),44,'white' if i<=p else INK)
                if i<n-1:arrow(im,[(xx+ww+7,yy+hh//2),(xx+ww+gap-10,yy+hh//2)],CORAL,8)
        if footer:self.source(im,footer)
    @lru_cache(maxsize=30)
    def person_frame(self,job,index):return Image.open(self.motions[job][index]).convert('RGB')
    def person(self,im,who,emotion,local,rect):
        job=who+'-'+emotion;fallback=who+'-joy' if who=='male' else who+'-thinking'
        if job not in self.motions:job=fallback
        if job in self.motions:
            files=self.motions[job];index=min(len(files)-1,max(0,int(local*FPS)));src=self.person_frame(job,index)
        else:src=self.refs[who]
        # A consistent head/upper-body crop keeps both faces comparable in size.
        src=src.crop((0,0,480,620))
        if job=='female-thinking' and job not in self.framed_jobs:
            # Preserve the raw video. Compensate the observed push-in only in
            # the edit, keeping head size/eye level near the male reference.
            factor=1-.30*smooth((local-.4)/1.4)
            tile=src.resize((round(src.width*factor),round(src.height*factor)),Image.Resampling.LANCZOS)
            stable=Image.new('RGB',src.size,'white');stable.paste(tile,(round((src.width-tile.width)/2),round((1-factor)*110)));src=stable
        fit(im,src,rect)
    def pair(self,im,who,emotion,local,visual='hook',left=None,right=None):
        left=left or (emotion if who=='male' else 'thinking');right=right or (emotion if who=='female' else 'thinking')
        if self.short:
            self.person(im,'male',left,local,(55,425,520,1235));self.person(im,'female',right,local,(560,425,1025,1235))
            self.text(im,'透',(80,1260,490,1330),44,TEAL);self.text(im,'凛',(590,1260,1000,1330),44,CORAL)
        else:
            self.person(im,'male',left,local,(80,280,670,840));self.person(im,'female',right,local,(1250,280,1840,840))
            message={'hook':'前から次を予測\n前後から穴埋め','not_chat':'初代GPT\n≠\n今のChatGPT','closing':'積み重ねで\n生まれた\n言語AI','ngram':'短い並びから\n次を予測','context':'同じ言葉でも\n文脈で意味が\n変わる','parallel':'学習の並列化と\n順番に生成','compare':'前から次を予測\n前後から穴埋め'}.get(visual,CHAPTERS.get(visual,'言葉を学ぶ仕組み'))
            self.text(im,message,(730,390,1190,710),50)
    def quote(self,im,sid,year):
        p=OUT/'article/v01/assets'/(sid+'-paper-title-quote.png');src=Image.open(p).convert('RGB')
        r=(70,470,1010,850) if self.short else (170,360,1750,640);box(im,r,PALE,20,TEAL,3);fit(im,src,(r[0]+18,r[1]+24,r[2]-18,r[3]-24))
        rr=(120,950,960,1110) if self.short else (350,670,1570,755);self.text(im,year,rr,68 if self.short else 56,TEAL)
    def bank_context(self,im):
        d=ImageDraw.Draw(im)
        if self.short:centers=[(540,655),(540,1110)];self.text(im,'bank',(100,415,980,515),78)
        else:centers=[(550,565),(1370,565)];self.text(im,'bank',(750,315,1170,398),74)
        x,y=centers[0];d.polygon([(x-155,y-90),(x,y-175),(x+155,y-90)],fill=CORAL)
        for k in range(4):box(im,(x-130+k*78,y-76,x-94+k*78,y+84),CORAL,4)
        box(im,(x-165,y+90,x+165,y+120),CORAL,5);self.text(im,'銀行',(x-180,y+145,x+180,y+205),48)
        x,y=centers[1]
        for k in range(3):
            points=[(x-210+i*15,y-70+k*55+math.sin(i/4)*18) for i in range(29)];d.line(points,fill=TEAL,width=19)
        self.text(im,'川岸',(x-180,y+145,x+180,y+205),48)
        self.source(im,'文脈で意味が変わる例。単語の表現にも、周りの文が必要。')
    def vectors(self,im,local):
        x0,y0,x1,y1=self.body;d=ImageDraw.Draw(im);r=(x0+65,y0+65,x1-65,y1-100);box(im,r,PALE,22)
        points=[(.2,.2,'猫',TEAL),(.36,.36,'犬',TEAL),(.68,.65,'バス',CORAL),(.8,.46,'車',CORAL)]
        for i,(xx,yy,label,color) in enumerate(points):
            x=r[0]+xx*(r[2]-r[0]);y=r[1]+yy*(r[3]-r[1]);rad=18+6*smooth((local-i*.4)/.8);d.ellipse((x-rad,y-rad,x+rad,y+rad),fill=color);self.text(im,label,(int(x)-105,int(y)+35,int(x)+105,int(y)+100),42,color)
        self.source(im,'配置は仕組みを説明するための例。実際の単語ベクトルの計測値ではありません。')
    def relations(self,im,local,positions=False):
        x0,y0,x1,y1=self.body;d=ImageDraw.Draw(im)
        pts=[(x0+150,y0+160),(x1-150,y0+160),((x0+x1)//2,y1-150)] if self.short else [(390,535),(960,660),(1530,535)]
        labels=['bank','river','crossed']
        for i,a in enumerate(pts):
            for j,b in enumerate(pts):
                if i<j:d.line([a,b],fill=TEAL if local>.7*(i+j) else '#CCDADD',width=10)
        for i,((x,y),label) in enumerate(zip(pts,labels)):
            r=(int(x)-140,int(y)-65,int(x)+140,int(y)+65);box(im,r,'white',18,TEAL,3);self.text(im,label,(r[0]+12,r[1]+10,r[2]-12,r[3]-10),48)
            if positions:self.text(im,str(i+1),(int(x)-45,int(y)-145,int(x)+45,int(y)-80),42,CORAL)
        self.source(im,'説明用の関係線。Attentionの実測値・判断理由を取り出した図ではありません。')
    def model_example(self,im,local,mode):
        if mode=='both':
            if local<6.2:mode='gpt'
            else:mode='bert';local-=6.2
        if self.short:
            self.text(im,'昨日、図書館で本を借りた',(70,420,1010,545),56)
            ys=[620,840,1060];rs=[(100,y,980,y+150) for y in ys]
        else:
            self.text(im,'昨日、図書館で本を借りた',(200,310,1720,402),56);rs=[(170+i*550,490,650+i*550,655) for i in range(3)]
        labels=['昨日、図書館で','本','を借りた']
        if mode=='gpt':
            phase=min(2,int(local/3.6));labels=[['昨日、図書館で','昨日、図書館で本','昨日、図書館で本を'][phase],['本','を','借りた'][phase] if local%3.6>1.3 else '次は？','先は見ない']
        else:labels[1]='本' if local>(2.0 if self.short else 6.0) else '[MASK]'
        for i,(r,label) in enumerate(zip(rs,labels)):
            color=CORAL if i==1 else TEAL;box(im,r,PALE,20,color,3);self.text(im,label,(r[0]+18,r[1]+14,r[2]-18,r[3]-14),52 if self.short else 48,color)
        if self.short:
            arrow(im,[(540,785),(540,825)],CORAL,9)
            if mode=='bert':arrow(im,[(540,1045),(540,1003)],CORAL,9)
            self.text(im,'次の予測' if mode=='gpt' else '前後から予測',(130,1250,950,1340),50,CORAL)
        else:
            arrow(im,[(675,575),(705,575)],CORAL,10)
            if mode=='bert':arrow(im,[(1250,575),(1220,575)],CORAL,10)
            self.text(im,'GPT：先の正解は見ない' if mode=='gpt' else 'BERT：隠した元の内容を予測',(200,710,1720,790),48,CORAL)
        self.source(im,'学習方法の説明例。初代モデルを実行した出力ではありません。')
    def compare(self,im,local):
        if self.short:
            self.card(im,'GPT／2018年6月','前から次を予測',(100,440,980,780),TEAL,56)
            self.card(im,'BERT論文／2018年10月','前後から隠した部分を予測',(100,940,980,1300),CORAL,47)
            self.text(im,'学ぶ課題が違う',(120,810,960,905),47,GREY)
        else:
            self.card(im,'GPT／2018年6月','前のトークンから\n次を予測',(110,350,890,750),TEAL,55)
            self.card(im,'BERT論文／2018年10月','前後の文脈から\n隠した部分を予測',(1030,350,1810,750),CORAL,55)
        self.source(im,'初代モデルの主な学習目標を比較。BERTの次文予測は本編・記事で補足。')
    def branches(self,im,local):
        if self.short:
            top=(240,440,840,640);bottom=[(65,960,515,1295),(565,960,1015,1295)]
        else:
            top=(690,315,1230,460);bottom=[(110,575,890,765),(1030,575,1810,765)]
        box(im,top,TEAL,20);self.text(im,'Transformer',(top[0]+15,top[1]+20,top[2]-15,top[3]-20),54,'white')
        for i,r in enumerate(bottom):
            cx=(r[0]+r[2])//2;start=((top[0]+top[2])//2,top[3]+8)
            arrow(im,[start,(start[0],start[1]+70),(cx,start[1]+70),(cx,r[1]-14)],TEAL if i==0 else CORAL,8)
            box(im,r,PALE,20,TEAL if i==0 else CORAL,3)
            self.text(im,'GPT' if i==0 else 'BERT',(r[0]+12,r[1]+15,r[2]-12,r[1]+85),52,TEAL if i==0 else CORAL)
            text=('次を予測\n2018年6月' if i==0 else '前後から予測\n2018年10月') if self.short else ('次を予測／2018年6月' if i==0 else '前後から予測／2018年10月')
            self.text(im,text,(r[0]+12,r[1]+105,r[2]-12,r[3]-12),43)
        self.source(im,'共通の土台から、見られる文脈と学習目標が異なる二つの研究へ。')
    def history_timeline(self,im,local):
        labels=['2003年\nニューラル\n言語モデル','2013年\nword2vec','2017年\nTransformer','2018年\nGPT・BERT']
        self.flow(im,labels,local,'代表的な研究の年表。論文初稿・公式発表・会議掲載は分けて確認。')
    def frame(self,t,local,absolute):
        im=self.base(t['visual'],t['chapter']).copy();v=t['visual']
        reactions={'f04':('sadness','frustration'),'f08':('thinking','sadness'),'f18':('frustration','thinking'),'f33':('joy','enjoyment'),'f35':('enjoyment','enjoyment')}
        reaction=reactions.get(t['id']) if not self.short else None
        if reaction and local<2.6:
            self.pair(im,t['speaker'],t['emotion'],local,v,*reaction)
        elif self.short and t['id'] in ['s05','s06'] and local<1.6:
            self.pair(im,t['speaker'],t['emotion'],local,v)
        elif v=='closing' and self.short:
            self.pair(im,t['speaker'],t['emotion'],local,v);self.text(im,'続きは本編で',(120,1380,960,1480),48,TEAL)
        elif v in ['hook','closing','not_chat'] and local<4.6:
            self.pair(im,t['speaker'],t['emotion'],local,v)
        elif v=='hook':self.branches(im,local)
        elif v=='closing':self.flow(im,['単語の表現','言葉の関係','学ぶ課題'],local)
        elif v=='not_chat':self.flow(im,['2018年の研究','用途別に調整','今の会話サービス\nとは区別する'],local)
        elif v=='context':self.bank_context(im)
        elif v=='vectors':self.vectors(im,local)
        elif v in ['attention','transformer','positions']:
            if v=='transformer' and local<1.7:self.quote(im,'transformer-2017','2017年6月／論文初稿')
            else:self.relations(im,local,v=='positions')
        elif v in ['gpt','bert']:
            if local<1.7:self.quote(im,'gpt-2018' if v=='gpt' else 'bert-2018','2018年6月11日／発表' if v=='gpt' else '2018年10月11日／論文初稿')
            else:self.model_example(im,local-1.7,v)
        elif v=='gpt_bert':self.branches(im,local)
        elif v=='compare':self.compare(im,local)
        elif v in ['masked','example']:self.model_example(im,local,'bert' if v=='masked' else 'both')
        elif v=='ngram':self.flow(im,['短い並びを集計','よく続く候補','初めての組合せは？'],local)
        elif v=='nnlm':self.flow(im,['単語の特徴','単語列の確率','一緒に学ぶ'],local,'出典：Bengioほか（2003）。言語モデルの起源をこの年だけに限定しない。')
        elif v=='rnn':self.flow(im,['文の最初','情報を渡す','次の言葉へ'],local,'RNN・LSTMの逐次処理を説明した模式図。長文が絶対に扱えないという意味ではない。')
        elif v=='parallel':self.flow(im,['学習は並列化へ','生成では順に予測','二つを区別する'],local)
        elif v=='pretrain':self.flow(im,['大量の文章','事前学習','用途へ調整'],local)
        elif v=='elmo':self.flow(im,['同じ単語','文脈で変わる表現','別の課題へ利用'],local,'出典：Petersほか（2018）ELMo。文脈表現の研究も並行して進んでいた。')
        elif v=='tokens':self.flow(im,['文章','処理する単位','トークン'],local,'日本語の単語と、トークンは常に一対一ではありません。')
        elif v=='nsp':self.flow(im,['二つの文','元は続いていた？','別の文との組合せ？'],local,'初代BERTの次文予測。実際のデータのつながりを区別する学習。')
        elif v=='timeline':self.history_timeline(im,local)
        else:raise ValueError(v)
        cap=next((c for c in t['subtitles'] if c['start']<=absolute<c['end']),None)
        if cap:
            r=(50,1545,1030,1790) if self.short else (80,875,1840,1035);box(im,r,INK,20);self.text(im,cap['text'],(r[0]+24,r[1]+22,r[2]-24,r[3]-22),64 if self.short else 50,'white')
        bar=(50,1840,1030,1850) if self.short else (80,1060,1840,1067);box(im,bar,'#D7E5E8',4)
        return im
    def ending(self,seconds):
        im=Image.new('RGB',(self.w,self.h),BG)
        if self.short:
            im=self.base('closing','short').copy();self.pair(im,'female','enjoyment',4.9,'closing');self.text(im,'続きは本編で',(120,1380,960,1480),48,TEAL);return im
        self.text(im,'言語AIの仕組みを、一緒に。',(180,125,1740,245),64)
        box(im,(120,350,800,760),PALE,24,TEAL,3);box(im,(1120,350,1800,760),PALE,24,CORAL,3)
        self.text(im,'関連動画',(160,475,760,590),54,TEAL);self.text(im,'次に学ぶテーマ',(1160,475,1760,590),54,CORAL)
        ImageDraw.Draw(im).ellipse((855,430,1065,640),fill=PALE,outline=TEAL,width=4)
        self.text(im,'登録',(865,500,1055,566),44,TEAL);self.text(im,'年表・一次資料・補足は記事へ',(280,865,1640,965),46)
        return im

def render(kind,limit=None):
    p=plan(kind);motion_cache();r=Renderer(kind);folder=dest(kind);target=folder/'video-only.mp4'
    required=({'male-joy','male-thinking','female-joy','female-thinking','female-enjoyment'} if kind=='short' else {who+'-'+pose for who in ['male','female'] for pose in ['joy','frustration','sadness','enjoyment','thinking']})
    if limit is None and required-set(r.framed_jobs):raise RuntimeError('Local motion assets not ready: '+','.join(sorted(required-set(r.framed_jobs))))
    if target.exists():raise RuntimeError('Do not overwrite a completed video-only stream')
    if limit is not None:target=folder/'preview-motion-pilot.mp4'
    frames=p['frames'] if limit is None else min(p['frames'],round(limit*FPS))
    log=(folder/('encode.log' if limit is None else 'preview-encode.log')).open('w',encoding='utf-8')
    cmd=['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24','-video_size',f"{p['width']}x{p['height']}",'-framerate',str(FPS),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','19','-threads','3','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));idx=0
    try:
        for f in range(frames):
            now=f/FPS
            while idx+1<len(p['turns']) and now>=p['turns'][idx]['end']:idx+=1
            im=r.ending(now-p['body_seconds']) if now>=p['body_seconds'] else r.frame(p['turns'][idx],now-p['turns'][idx]['start'],now)
            proc.stdin.write(im.tobytes())
            if f%(FPS*30)==0:print(json.dumps(dict(event='render',kind=kind,frame=f,total=frames)),flush=True)
        proc.stdin.close();code=proc.wait();assert code==0,'Inspect encode log'
    except BaseException:
        proc.kill();proc.wait();raise
    finally:log.close()
    save(folder/('text-audit.json' if limit is None else 'preview-text-audit.json'),list(r.c.audit.values()));print('Rendered',target,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','render','stills','cache']);p.add_argument('--kind',choices=['short','full'],default='short');p.add_argument('--limit',type=float);a=p.parse_args()
    if a.action=='plan':plan(a.kind)
    elif a.action=='cache':motion_cache()
    elif a.action=='render':render(a.kind,a.limit)
    else:
        d=plan(a.kind);r=Renderer(a.kind);folder=OUT/'review/v01'/a.kind;folder.mkdir(parents=True,exist_ok=True)
        for t in d['turns']:r.frame(t,min(2.8,t['end']-t['start']-.1),t['start']+min(2.8,t['end']-t['start']-.1)).save(folder/(t['id']+'-'+t['visual']+'.png'))
        save(folder/'text-audit.json',list(r.c.audit.values()));print('Representative stills rendered',len(d['turns']))
