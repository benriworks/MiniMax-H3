"""Editorial rebuild: concrete diagrams, official original figures and varied shots.

short v07 / full v05 preserve the accepted dialogue, voices and old releases.
"""
import argparse
import json
import math
import shutil
from functools import lru_cache

import numpy as np
from PIL import Image,ImageDraw,ImageOps

import produce as old
from tools.studio.explainer_canvas import Canvas,box,fit,arrow,font

old.REVISIONS={'short':'v07','full':'v05'}
ROOT,HERE,OUT,FPS=old.ROOT,old.HERE,old.OUT,old.FPS
NAVY='#132D40';TEAL='#087E82';CORAL='#B84735';GOLD='#E8B456';PAPER='#F4F2EB';PALE='#E4F0EE';GREY='#526A77'
original_cache=old.motion_cache


def cache():
    original_cache();records=[]
    for p in sorted((OUT/'motions/v04-closeups').glob('*/verification.json')):
        proof=json.loads(p.read_text(encoding='utf-8'));raw=ROOT/proof['artifact']['path']
        assert old.sha(raw).upper()==proof['artifact']['sha256']
        target=OUT/'motion-close-cache'/p.parent.name
        if not (target/'complete.json').exists():
            target.mkdir(parents=True,exist_ok=True)
            old.run(['ffmpeg','-v','error','-n','-i',str(raw),'-vf','fps=24','-q:v','2',str(target/'%04d.jpg')])
            old.save(target/'complete.json',dict(source_sha256=old.sha(raw),frames=len(list(target.glob('*.jpg')))))
        records.append(dict(job=p.parent.name,source=raw.relative_to(ROOT).as_posix(),cache=target.relative_to(ROOT).as_posix(),sha256=old.sha(raw)))
    old.save(OUT/'motion-provenance-v04.json',records)
    return records


def shots(t,kind):
    """Explicit cut schedule; diagram updates inside a shot are recorded separately."""
    key=t['id'];v=t['visual'];duration=t['end']-t['start']
    if kind=='short':
        table={'s01':[(0,'result'),(1.45,'male_close')],
               's02':[(0,'female_close'),(2.8,'branches')],
               's03':[(0,'vectors'),(2.6,'context'),(5.0,'relations'),(7.5,'official_attention')],
               's04':[(0,'male_close')],
               's05':[(0,'official_gpt_panel'),(4.8,'official_bert_panel'),(8.0,'compare')],
               's08':[(0,'gpt_example'),(6.1,'bert_example')],
               's10':[(0,'male_medium'),(2.2,'compare')],
               's09':[(0,'female_close'),(3.0,'duo')]}
        return [(at,scene) for at,scene in table[key] if at<duration]
    if key=='f01':return [(0,'result'),(1.5,'male_close')]
    if key=='f02':return [(0,'female_close'),(3.0,'result'),(7.5,'branches')]
    if key=='f08':return [(0,'female_medium'),(2.0,'context'),(7.0,'context_zoom')]
    if key=='f10':return [(0,'female_medium'),(2.0,'rnn'),(8.0,'rnn_long')]
    if key=='f18':return [(0,'male_medium'),(2.1,'pretrain')]
    if key in {'f03','f06','f09','f12','f16','f18','f21','f24','f27','f30','f33'}:
        if duration<4.8:return [(0,'male_close' if key in {'f03','f09','f16','f24','f30'} else 'male_medium')]
    table={'f04':[(0,'ngram'),(7.0,'ngram_unseen')],
           'f05':[(0,'female_medium'),(2.4,'nnlm'),(8.0,'vectors')],
           'f07':[(0,'vectors'),(6.0,'vector_features'),(11.0,'context')],
           'f08':[(0,'context'),(6.0,'context_zoom')],
           'f10':[(0,'rnn'),(7.0,'rnn_long')],
           'f11':[(0,'translation'),(6.0,'attention')],
           'f13':[(0,'attention_history'),(5.0,'relations')],
           'f14':[(0,'official_attention'),(7.0,'relations')],
           'f15':[(0,'positions'),(7.0,'relations')],
           'f17':[(0,'parallel'),(6.5,'gpt_example')],
           'f19':[(0,'pretrain'),(7.0,'tasks')],
           'f20':[(0,'context'),(5.0,'official_arch'),(10.0,'branches')],
           'f22':[(0,'official_openai'),(5.0,'gpt_example'),(10.5,'gpt_chain')],
           'f23':[(0,'tokens'),(7.5,'gpt_example')],
           'f25':[(0,'female_close'),(2.7,'not_chat'),(8.0,'tasks'),(13.0,'official_openai')],
           'f26':[(0,'official_arch'),(6.0,'official_bert_panel'),(11.0,'bert_example')],
           'f28':[(0,'official_mask'),(3.5,'bert_example'),(10.0,'bert_example_reveal')],
           'f29':[(0,'nsp'),(7.5,'nsp_compare')],
           'f31':[(0,'official_arch'),(4.8,'compare'),(11.0,'result')],
           'f32':[(0,'tasks'),(7.0,'compare')],
           'f34':[(0,'timeline'),(7.0,'branches'),(12.0,'dates')],
           'f35':[(0,'duo'),(4.5,'timeline'),(10.0,'duo')]}
    return [(at,scene) for at,scene in table.get(key,[(0,v)]) if at<duration]


class Renderer:
    def __init__(self,kind):
        self.kind=kind;self.short=kind=='short';self.w,self.h=(1080,1920) if self.short else (1920,1080);self.c=Canvas();self.dark=False
        self.body=(48,175,1032,1500) if self.short else (60,165,1860,812)
        self.framed_jobs={p.name for p in (OUT/'motion-framed-cache').glob('*') if (p/'complete.json').exists()}
        self.close={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'motion-close-cache').glob('*') if (p/'complete.json').exists()}
        self.regular={job:sorted((OUT/'motion-framed-cache'/job).glob('*.png')) for job in self.framed_jobs}
    def text(self,im,value,rect,size=52,color=NAVY,center=True):
        if self.dark and color==NAVY:color='white'
        elif self.dark and color==GREY:color='#BED2DA'
        elif self.dark and color==TEAL:color=GOLD
        self.c.text(im,value,tuple(round(v) for v in rect),size,color,center)
    def title(self,im,value):
        r=(52,22,1028,160) if self.short else (60,28,1860,135)
        if self.short:value='\n'.join(old.phrase_lines(value,976,60,protected=old.PROTECT))
        self.text(im,value,r,60 if self.short else 57)
    @lru_cache(maxsize=8)
    def background(self,dark=False):
        im=Image.new('RGB',(self.w,self.h),NAVY if dark else PAPER);d=ImageDraw.Draw(im)
        d.rectangle((0,0,14,self.h),fill=TEAL);d.rectangle((self.w-12,0,self.w,self.h),fill=CORAL)
        return im
    def note(self,im,value,color=GREY):
        r=(52,1462,1028,1540) if self.short else (60,824,1860,864)
        if self.short:value='\n'.join(old.phrase_lines(value,976,27,protected=old.PROTECT))
        self.text(im,value,r,27 if self.short else 28,color)
    def badge(self,im,label,rect,color=TEAL,size=36):
        box(im,rect,color,16);self.text(im,label,(rect[0]+12,rect[1]+9,rect[2]-12,rect[3]-9),size,'white')
    @lru_cache(maxsize=18)
    def image(self,name):
        path=next(p for p in (OUT/'official/v04').glob(name+'.*') if p.suffix.lower() in {'.png','.webp','.jpg','.gif'});src=Image.open(path).convert('RGBA')
        white=Image.new('RGBA',src.size,'white');white.alpha_composite(src);return white.convert('RGB')
    @lru_cache(maxsize=32)
    def actor_image(self,who,mode,frame,pose='thinking'):
        close=mode=='close';job=who+'-close-'+('thinking' if who=='male' else 'insight')
        if close and job in self.close:
            files=self.close[job];src=Image.open(files[min(len(files)-1,frame)]).convert('RGB').crop((0,0,480,642))
        elif close:
            src=Image.open(OUT/'characters/v04'/(who+'-close-input.png')).convert('RGB').crop((0,0,480,642))
        else:
            if who+'-'+pose not in self.regular:pose='thinking' if who=='male' else 'enjoyment'
            files=self.regular[who+'-'+pose]
            src=Image.open(files[min(len(files)-1,frame)]).convert('RGB').crop((65,8,420,410))
        return src
    def actor(self,im,who,local,rect,mode='close'):
        frame=max(0,min(123,round(local*24)))
        pose=getattr(self,'current_pose','thinking' if who=='male' else 'enjoyment') if not self.short else ('thinking' if who=='male' else 'enjoyment')
        src=self.actor_image(who,mode,frame,pose)
        box(im,rect,'white',24)
        ratio=(rect[2]-rect[0])/(rect[3]-rect[1])
        if mode=='close' and ratio>.95:src=src.crop((0,0,480,465))
        fit(im,src,(rect[0]+8,rect[1]+8,rect[2]-8,rect[3]-8),cover=mode=='close' and ratio<.85)
    def presenter(self,im,t,local,scene):
        who='male' if scene.startswith('male') else 'female';mode='medium' if scene.endswith('medium') else 'close'
        if self.short:
            rect=(315,205,1028,1440);self.actor(im,who,local,rect,mode)
            key=('何が\n違う？' if t['id']=='s01' else '何を\n練習？') if who=='male' else ('学ぶ課題\nが違う' if t['id']=='s02' else '続きは\n本編で')
            self.badge(im,'透' if who=='male' else '凛',(52,225,240,301),TEAL if who=='male' else CORAL,43)
            self.text(im,key,(52,395,405,720),61)
        else:
            self.actor(im,who,local,(1120,170,1855,812),mode)
            cues={'f01':'丸暗記だけで\n答えているの？','f03':'昔は、どうやって\n次を予測した？','f06':'単語に番号を付ける\nだけでいい？','f09':'順に読めば\n解決する？','f12':'Attentionが\n先だったんだ','f16':'全文が一瞬で\n完成するの？','f18':'用途ごとに\n最初から学ぶ？','f21':'GPTは何を\n練習した？','f24':'2018年に\nChatGPTがあった？','f27':'答えが先に\n見えてしまわない？','f30':'BERTの方が\n上なの？','f33':'工夫がつながり\n今のAIへ','f25':'研究モデルと\n会話サービスを分ける'}
            message=cues.get(t['id'],'文脈と学び方を\n一緒に見てみよう')
            self.badge(im,('透の疑問' if who=='male' else '凛の解説'),(78,200,440,280),TEAL if who=='male' else CORAL,38)
            self.text(im,message,(80,325,1090,630),76)
            trail={'gpt':'過去のトークン → 次を予測','masked':'前後の文脈 → 隠した部分を予測','rnn':'順に読む → 情報を渡す','parallel':'学習の並列化 ≠ 一度に全文生成'}.get(t['visual'],'単語の特徴 → 文脈 → 学ぶ課題')
            self.text(im,trail,(84,690,1080,780),37,GREY)
    def duo(self,im,local):
        if self.short:
            self.actor(im,'male',local,(52,270,520,1170),'close');self.actor(im,'female',local,(560,270,1028,1170),'close')
            self.text(im,'GPTとBERTの違いは\n本編でもっと詳しく',(80,1220,1000,1435),61)
        else:
            self.actor(im,'male',local,(65,170,650,812),'close');self.actor(im,'female',local,(1270,170,1855,812),'close')
            self.text(im,'何を見て\n何を予測するか',(690,275,1230,560),69)
            self.badge(im,'仕組みと原典は記事へ',(680,650,1240,746),TEAL,39)
    def token(self,im,label,rect,color=TEAL,active=True,size=58):
        box(im,rect,color if active else 'white',20,outline=color,width=4)
        self.text(im,label,(rect[0]+12,rect[1]+12,rect[2]-12,rect[3]-12),size,'white' if active else NAVY)
    def example(self,im,local,mode='gpt',compact=False,reveal=False):
        self.title(im,'GPT：文の続きを予測' if mode=='gpt' else 'BERT：隠した言葉を予測')
        if compact:return
        words=['昨日、','図書館で','本','を借りた']
        if self.short:
            self.badge(im,'2018年の学習方法の例',(70,205,1010,287),TEAL if mode=='gpt' else CORAL,39)
            if mode=='gpt':
                phase=min(2,int(local/1.8));prefix=['昨日、','昨日、図書館で','昨日、図書館で本'][phase];answer=['図書館で','本','を借りた'][phase]
                self.token(im,prefix,(75,435,1005,630),TEAL,size=55)
                arrow(im,[(540,670),(540,795)],CORAL,16)
                self.token(im,answer if local%1.8>.55 else '次は？',(185,845,895,1080),CORAL,size=76)
                self.text(im,'まだ見ていない続きを\n一つずつ予測する',(100,1195,980,1405),60)
            else:
                self.token(im,'昨日、図書館で',(72,420,1008,594),TEAL,size=57)
                self.token(im,'本' if reveal or local>2.4 else '？',(295,762,785,982),CORAL,size=100)
                self.token(im,'を借りた',(180,1165,900,1339),TEAL,size=67)
                arrow(im,[(540,620),(540,732)],CORAL,16);arrow(im,[(540,1140),(540,1011)],CORAL,16)
        else:
            y=385;positions=[(70,y,410,y+200),(460,y,860,y+200),(910,y,1190,y+200),(1240,y,1850,y+200)]
            for i,(label,r) in enumerate(zip(words,positions)):
                if mode=='gpt':
                    phase=min(3,1+int(local/2.0));self.token(im,label if i<=phase else '…',r,CORAL if i==phase else TEAL,active=i<=phase,size=61)
                else:self.token(im,('本' if reveal or local>3.0 else '？') if i==2 else label,r,CORAL if i==2 else TEAL,size=76 if i==2 else 61)
                if i<3:
                    points=[(r[2]+7,y+100),(positions[i+1][0]-10,y+100)]
                    if mode=='bert' and i==2:points=list(reversed(points))
                    arrow(im,points,CORAL,11)
            self.badge(im,'先の正解を見ずに、次を予測' if mode=='gpt' else '前後の手掛かりから、隠した元の内容を予測',(150,670,1770,774),TEAL if mode=='gpt' else CORAL,48)
        self.note(im,'学習方法を示す例。初代モデルを実行した出力ではありません。')
    def result(self,im,local):
        self.title(im,'GPTとBERT、学び方の違い')
        if self.short:
            for label,msg,y,color in [('GPT','続きを予測',215,TEAL),('BERT','隠した部分を予測',875,CORAL)]:
                self.badge(im,label,(75,y,1005,y+108),color,68)
                self.token(im,'図書館で → 本' if label=='GPT' else '図書館で ？ を借りた',(75,y+155,1005,y+360),color,False,58 if label=='GPT' else 48)
                self.text(im,msg,(75,y+405,1005,y+535),61,color)
        else:
            for x,label,msg,line,color in [(65,'GPT','続きを予測','図書館で → 本',TEAL),(1015,'BERT','隠した部分を予測','図書館で ？ を借りた',CORAL)]:
                box(im,(x,177,x+840,811),'white',26)
                self.badge(im,label,(x+24,201,x+816,310),color,72)
                self.text(im,line,(x+35,385,x+805,540),60 if label=='GPT' else 51)
                self.text(im,msg,(x+25,610,x+815,745),58,color)
        self.note(im,'初代モデルの主な学習目標を比較。用途を完全に二分する説明ではありません。')
    def bank(self,im,local,zoom=False):
        self.title(im,'bankは「銀行」？それとも「川岸」？')
        if self.short:rects=[(60,215,1020,775),(60,850,1020,1440)]
        else:rects=[(60,180,920,811),(1000,180,1860,811)]
        for i,r in enumerate(rects):
            box(im,r,'white',24);cx=(r[0]+r[2])/2;cy=r[1]+220;d=ImageDraw.Draw(im)
            if i==0:
                d.polygon([(cx-175,cy-70),(cx,cy-175),(cx+175,cy-70)],fill=CORAL)
                for n in range(4):box(im,(cx-145+n*88,cy-49,cx-97+n*88,cy+120),CORAL,3)
                box(im,(cx-185,cy+135,cx+185,cy+160),CORAL,5)
            else:
                for n in range(3):
                    points=[(cx-240+j*16,cy-80+n*75+math.sin(j/4+local*.4)*22) for j in range(31)];d.line(points,fill=TEAL,width=22)
            self.text(im,'銀行' if i==0 else '川岸',(r[0]+30,r[3]-150,r[2]-30,r[3]-42),78,CORAL if i==0 else TEAL)
        self.note(im,'同じ単語でも、周りの言葉が意味の手掛かりになる。')
    def vectors(self,im,local,features=False):
        self.title(im,'単語を、学習した数値の特徴へ')
        r=self.body;box(im,r,'white',24);d=ImageDraw.Draw(im)
        if self.short:
            pts=[(265,525,'猫',TEAL),(490,655,'犬',TEAL),(710,1070,'車',CORAL),(450,1210,'バス',CORAL)]
        else:pts=[(400,350,'猫',TEAL),(685,495,'犬',TEAL),(1440,400,'車',CORAL),(1185,670,'バス',CORAL)]
        for i,(x,y,label,color) in enumerate(pts):
            radius=25+8*old.smooth((local-i*.35)/.8);d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
            self.text(im,label,(x-100,y+45,x+100,y+125),58,color)
        if features:
            for i in range(6):box(im,(850+i*72,245,890+i*72,245+80+28*(i%3)),TEAL if i%2==0 else CORAL,4)
            self.text(im,'番号とは違い、特徴を学ぶ',(360,172,1560,258),46)
        else:
            d.line([pts[0][:2],pts[1][:2]],fill='#B8D5D2',width=8);d.line([pts[2][:2],pts[3][:2]],fill='#E9C3B5',width=8)
        self.note(im,'配置・棒の高さは説明用。単語ベクトルの実測値ではありません。')
    def relations(self,im,local,positions=False):
        self.title(im,'離れた言葉の関係も、直接参照する')
        if self.short:pts=[(295,380),(790,795),(300,1225)]
        else:pts=[(370,330),(960,690),(1550,330)]
        d=ImageDraw.Draw(im)
        for i in range(3):
            for j in range(i+1,3):
                factor=old.smooth((local-.4*(i+j))/.9);a=pts[i];b=pts[j];end=(a[0]+(b[0]-a[0])*factor,a[1]+(b[1]-a[1])*factor)
                d.line([a,end],fill=TEAL if j!=2 else CORAL,width=15)
        for i,((x,y),word) in enumerate(zip(pts,['bank','river','crossed'])):
            self.token(im,word,(x-205,y-90,x+205,y+90),TEAL if i<2 else CORAL,True,59)
            if positions:self.badge(im,str(i+1),(x-50,y-180,x+50,y-112),CORAL,38)
        self.note(im,'関係線は仕組みの説明用。Attentionの実測値ではありません。')
    def official(self,im,local,scene):
        self.title(im,'公式資料で、学び方を確かめる')
        if scene=='official_openai':
            src=self.image('openai-2018-article-image')
            if self.short:
                fit(im,src,(65,225,1015,945));self.text(im,'OpenAI\n2018年6月11日',(80,1005,1000,1360),64)
            else:
                fit(im,src,(65,188,665,788));self.badge(im,'OpenAI｜2018年6月11日',(725,191,1845,285),TEAL,42)
                self.text(im,'Improving language understanding\nwith unsupervised learning',(735,350,1830,520),43)
                self.text(im,'Transformer × 事前学習',(735,610,1830,750),60)
            self.note(im,'引用：OpenAI（2018.6.11）｜画像：Ben Barry｜openai.com')
        elif scene=='official_attention':
            src=self.image('google-attention-original')
            if self.short:
                i=0 if local<2.5 else 1
                if local<.8:fit(im,src,(65,400,1015,1110))
                else:fit(im,src.crop((i*800,0,(i+1)*800,661)),(65,235,1015,1195))
                self.text(im,'it → animal（動物）' if i==0 else 'it → street（道）',(65,1245,1015,1425),59,TEAL)
            else:
                fit(im,src,(65,210,1855,790))
            self.note(im,'引用：Google Research（2017.8.31）／research.google｜Self-Attentionの原図')
        elif scene=='official_mask':
            src=self.image('google-bert-mask-original');fit(im,src,(60,390,1860,640) if not self.short else (65,530,1015,900))
            self.text(im,'隠した元の言葉を、周りから予測',(120,200,1800,340) if not self.short else (65,250,1015,455),56)
            self.note(im,'引用：Google ResearchのBERT公開記事（2018.11.2）／原図')
        else:
            if self.short and local>=.8:
                vector=self.image('bert-paper-architecture-vector-v04')
                src=vector.crop((625,100,1180,615)) if scene.endswith('gpt_panel') else vector.crop((30,100,605,615))
                fit(im,src,(65,350,1015,1170))
                self.badge(im,'GPT｜2018年6月' if scene.endswith('gpt_panel') else 'BERT論文｜2018年10月',(65,210,1015,315),TEAL if scene.endswith('gpt_panel') else CORAL,48)
                self.text(im,'前の語 → 次を予測' if scene.endswith('gpt_panel') else '前後の文脈 → 予測',(65,1220,1015,1390),61,TEAL if scene.endswith('gpt_panel') else CORAL)
                self.note(im,'引用：BERT原論文 Fig.1／Google Research公開記事（2018.11.2）')
                return
            if not self.short and local>=.9:
                src=self.image('bert-paper-architecture-vector-v04');tid=getattr(self,'current_turn','')
                model='ELMo' if tid=='f20' else 'BERT' if scene.endswith('bert_panel') or local<2.8 else 'GPT'
                ranges={'BERT':(30,100,605,615),'GPT':(625,100,1180,615),'ELMo':(1190,100,2260,615)}
                quoted=src.crop(ranges[model]);fit(im,quoted,(65,185,930,810))
                self.badge(im,model,(1010,190,1840,300),TEAL if model!='BERT' else CORAL,66)
                message={'BERT':'前後の文脈から\n隠した内容を予測','GPT':'過去のトークンから\n次を予測','ELMo':'文脈に応じて\n表現を変える'}[model]
                self.text(im,message,(1000,390,1840,670),68)
                self.text(im,'Trm：Transformer層' if model!='ELMo' else 'LSTMによる文脈表現',(1000,710,1840,800),38,GREY)
                self.note(im,'引用：Devlinほか BERT原論文 Fig.1／Google Researchの2018年公開記事')
                return
            src=self.image('google-bert-gpt-elmo-original')
            if scene.endswith('gpt_panel'):src=src.crop((0,0,840,367)) if self.short and local<.8 else src.crop((430,0,835,300 if self.short else 367))
            elif scene.endswith('bert_panel'):src=src.crop((0,0,410,300 if self.short else 367))
            else:src=src if local<1.8 else src.crop((0,0,840,367))
            rect=(65,365,1015,1160) if self.short else (65,255,1855,791)
            fit(im,src,rect)
            if self.short:self.badge(im,'GPT｜2018年6月' if scene.endswith('gpt_panel') else 'BERT論文｜2018年10月',(65,210,1015,315),TEAL if scene.endswith('gpt_panel') else CORAL,48)
            else:self.badge(im,'BERT：前後の文脈' if scene.endswith('bert_panel') else '初代GPTとBERTの構造比較',(330,166,1590,245),TEAL,44)
            if self.short:self.text(im,'前の語 → 次を予測' if scene.endswith('gpt_panel') else '前後の文脈 → 予測',(65,1220,1015,1390),61,TEAL if scene.endswith('gpt_panel') else CORAL)
            self.note(im,'引用：Google Research（2018.11.2）｜論文初稿は2018年10月')
    def branches(self,im,local):
        self.title(im,'同じ土台から、異なる学習目標へ')
        if self.short:
            top=(90,220,990,410);bottom=[(75,715,1005,975),(75,1110,1005,1380)]
        else:top=(570,175,1350,330);bottom=[(65,500,895,805),(1025,500,1855,805)]
        self.token(im,'Transformer',top,TEAL,True,64)
        for i,r in enumerate(bottom):
            start=((top[0]+top[2])/2,top[3]+8);end=((r[0]+r[2])/2,r[1]-16)
            if self.short:arrow(im,[(150 if i==0 else 930,start[1]),(150 if i==0 else 930,end[1])],TEAL if i==0 else CORAL,14)
            else:arrow(im,[start,(start[0],410),(end[0],410),end],TEAL if i==0 else CORAL,14)
            box(im,r,'white',24);self.text(im,'GPT' if i==0 else 'BERT',(r[0]+20,r[1]+15,r[2]-20,r[1]+105),67,TEAL if i==0 else CORAL)
            self.text(im,'次を予測' if i==0 else '隠した部分を予測',(r[0]+20,r[1]+140,r[2]-20,r[3]-25),51,TEAL if i==0 else CORAL)
        self.note(im,'共通の土台。GPTとBERTを直接の親子関係にはしません。')
    def flow(self,im,local,scene):
        if not self.short and scene in {'ngram','ngram_unseen','rnn','rnn_long','pretrain','tasks','tokens','nsp','nsp_compare','parallel'}:
            return self.concrete_flow(im,local,scene)
        definitions={'nnlm':('単語の特徴と、次の確率を一緒に学ぶ',['単語','数値の特徴','次を予測']),
            'rnn':('文を順に読み、情報を受け渡す',['文の最初','情報を渡す','次の言葉']),
            'rnn_long':('長い文の手掛かりを、どう保つ？',['最初の手掛かり','長い文章','離れた言葉']),
            'attention':('予測に必要な場所を参照する',['元の文章','注目する場所','次の予測']),
            'translation':('翻訳：元の文から、次の語へ',['元の文','まとめた情報','翻訳の続き']),
            'pretrain':('先に学び、用途に合わせて調整',['大量の文章','事前学習','用途へ調整']),
            'tasks':('文章を書く以外の課題にも応用',['文章の分類','質問への回答','読解']),
            'tokens':('文字や単語の断片を、処理の単位へ',['文章','トークン','次を予測']),
            'not_chat':('2018年の研究と、今のサービスは別',['初代GPT','用途別に調整','今のChatGPT']),
            'parallel':('学習の並列化と、生成の順番は別',['学習を並列化','生成では順に予測','二つを区別']),
            'nsp':('二つの文は、もともと続いていた？',['文A','文B','続きか判断']),
            'nsp_compare':('つながる文と、別の文の組み合わせ',['図書館へ行った','本を借りた','つながりを学ぶ']),
            'elmo':('文脈に応じた表現へ',['同じ単語','異なる文脈','表現が変わる']),
            'ngram':('短い単語の並びから、次を予測',['今日は','よく続く言葉','晴れ']),
            'ngram_unseen':('初めての組み合わせには、どう答える？',['見た単語列','出現を数える','未知の並びは？']),
            'dates':('論文初稿・公式発表・公開記事を分ける',['GPT：2018年6月','BERT初稿：10月','公開記事：11月']),
            'attention_history':('Attentionの研究が先にあった',['2014年\nAttention研究','2017年\nTransformer','2018年\nGPT・BERT'])}
        title,labels=definitions[scene];self.title(im,title);active=min(2,int(local/1.5))
        if self.short:rects=[(65,235+i*400,1015,525+i*400) for i in range(3)]
        else:rects=[(65+i*615,325,595+i*615,690) for i in range(3)]
        d=ImageDraw.Draw(im)
        for i,(r,label) in enumerate(zip(rects,labels)):
            color=TEAL if i!=2 else CORAL;box(im,r,'white',24,outline=color,width=4)
            # A distinct object stands above each short label; the frame is not
            # just a long paragraph inside a colored box.
            cx=(r[0]+r[2])/2;y=r[1]+75
            if i==0:
                for n in range(3):box(im,(cx-85+n*17,y-40+n*12,cx+60+n*17,y+60+n*12),PALE,6,TEAL,3)
            elif i==1:
                for n in range(4):d.ellipse((cx-98+n*56,y-10,cx-64+n*56,y+24),fill=color)
            else:d.polygon([(cx-60,y+10),(cx-15,y+55),(cx+85,y-45),(cx+65,y-65),(cx-15,y+18),(cx-40,y-8)],fill=color)
            self.text(im,label,(r[0]+15,r[1]+170,r[2]-15,r[3]-23),48,color)
            if i<2:
                if self.short:arrow(im,[(540,r[3]+10),(540,rects[i+1][1]-16)],CORAL,14)
                else:arrow(im,[(r[2]+9,510),(rects[i+1][0]-13,510)],CORAL,14)
            if i==active:box(im,(r[0]+12,r[3]-12,r[2]-12,r[3]-5),color,3)
        self.note(im,'仕組みの説明例。実際のモデルの実行結果ではありません。')
    def concrete_flow(self,im,local,scene):
        d=ImageDraw.Draw(im)
        if scene.startswith('ngram'):
            self.title(im,'短い並びを数えて、次の候補を探す')
            self.token(im,'今日は' if scene=='ngram' else '未知の組み合わせ…',(65,300,760,595),TEAL,True,86 if scene=='ngram' else 58)
            arrow(im,[(790,445),(930,445)],CORAL,18)
            for i,(label,length) in enumerate([('晴れ',800),('雨',560),('休み',330)]):
                y=207+i*205;w=length*old.smooth((local-i*.5)/1.0);box(im,(995,y,995+max(12,w),y+120),TEAL if i==0 else '#BBD6D1',12)
                self.text(im,label if scene=='ngram' else '？',(1040,y+15,1440,y+102),63,'white' if i==0 else NAVY,False)
            self.note(im,'説明用の候補。棒の長さは実際の頻度・確率ではありません。')
        elif scene.startswith('rnn'):
            self.title(im,'言葉を順に処理し、情報を受け渡す')
            words=['昨日','図書館で','本を','借りた'];xs=[260,720,1180,1640]
            for i,(x,word) in enumerate(zip(xs,words)):
                d.ellipse((x-115,280,x+115,510),fill=TEAL if i<=int(local/.9) else '#BBD6D1')
                self.text(im,'情報',(x-100,350,x+100,430),50,'white')
                self.text(im,word,(x-195,620,x+195,730),63)
                if i<3:arrow(im,[(x+132,395),(xs[i+1]-135,395)],CORAL,14)
            if scene=='rnn_long':
                d.line([(260,240),(260,199),(1640,199),(1640,240)],fill=CORAL,width=9)
                self.text(im,'離れた手掛かりをどう保つ？',(490,155,1420,235),42,CORAL)
            self.note(im,'逐次処理の説明。長文を絶対に扱えない、という意味ではありません。')
        elif scene=='pretrain':
            self.title(im,'大量の文章で先に学び、用途へ合わせる')
            for i in range(6):
                x=90+(i%3)*135;y=235+(i//3)*235;box(im,(x,y,x+110,y+155),'white',10,TEAL,3)
                for j in range(4):d.line((x+16,y+30+j*25,x+92,y+30+j*25),fill=TEAL,width=4)
            arrow(im,[(555,460),(740,460)],CORAL,17)
            points=[(850,300),(1080,290),(790,490),(990,450),(1190,500),(1040,670)]
            for i,a in enumerate(points):
                for b in points[i+1:]:d.line([a,b],fill='#AACBC8',width=7)
            for i,(x,y) in enumerate(points):d.ellipse((x-36,y-36,x+36,y+36),fill=TEAL if i<=int(local) else '#BBD6D1')
            arrow(im,[(1250,460),(1400,460)],CORAL,17)
            for i,label in enumerate(['分類','質問応答','読解']):self.token(im,label,(1450,215+i*195,1825,350+i*195),CORAL,i<=int(local/1.5),50)
            self.note(im,'事前学習と用途別調整の関係。GPTやBERTだけの発明ではありません。')
        elif scene=='tasks':
            self.title(im,'初代GPTは、言語理解の課題にも応用')
            for i,(label,example) in enumerate([('分類','どんな内容の文章？'),('質問応答','答えはどこにある？'),('読解','文の内容を読み取る')]):
                y=180+i*210;box(im,(65,y,1365,y+187),'white',22)
                d.ellipse((95,y+35,215,y+155),fill=TEAL if i!=1 else CORAL)
                self.text(im,['類','？','文'][i],(108,y+60,202,y+132),55,'white')
                self.text(im,label,(260,y+23,1260,y+85),45,TEAL,False)
                self.text(im,example,(260,y+105,1300,y+168),47,NAVY,False)
            self.actor(im,'female',min(local,4.9),(1430,205,1855,807),'close')
            self.note(im,'出典：OpenAIの2018年6月11日発表・初代GPT論文。')
        elif scene=='tokens':
            self.title(im,'文章を、モデルが扱う「トークン」へ')
            self.token(im,'昨日、図書館で本を借りた',(160,195,1760,370),TEAL,False,70)
            arrow(im,[(960,395),(960,510)],CORAL,17)
            for i,label in enumerate(['昨日','、','図書館','で','本','を','借りた']):
                x=90+i*253;self.token(im,label,(x,555,x+224,745),TEAL if i%2==0 else CORAL,True,43 if label=='図書館' else 49)
            self.note(im,'区切り方は説明用。実際のトークン分割はモデルで異なります。')
        elif scene.startswith('nsp'):
            self.title(im,'元の文書で、二つの文は続いていた？')
            pairs=[('同じ文書の続き','図書館へ行った','本を借りた',TEAL),('別の文書から組み合わせ','図書館へ行った','チームが優勝した',CORAL)]
            for i,(label,a,b,color) in enumerate(pairs):
                y=185+i*325;box(im,(65,y,1855,y+285),'white',22)
                self.text(im,label,(100,y+18,1810,y+83),44,color)
                self.token(im,a,(100,y+120,820,y+254),color,False,52)
                arrow(im,[(850,y+185),(1030,y+185)],color,13)
                self.token(im,b,(1060,y+120,1815,y+254),color,True,51)
            self.note(im,'初代BERTの次文予測を説明する架空の文。意味だけで続きと断定しません。')
        else:
            self.title(im,'学習の並列化と、生成の順番を分ける')
            self.badge(im,'学習',(65,190,450,290),TEAL,56)
            for i in range(4):
                x=535+i*325;box(im,(x,190,x+235,390),'white',16,TEAL,3)
                for j in range(3):box(im,(x+30,230+j*40,x+195,245+j*40),TEAL,3)
            self.badge(im,'生成',(65,530,450,630),CORAL,56)
            for i,label in enumerate(['図書館で','本','を','借りた']):
                x=515+i*335;self.token(im,label if local>.6+i*.7 else '…',(x,535,x+285,725),CORAL,i<=int(local/.7),46)
                if i<3:arrow(im,[(x+291,630),(x+324,630)],CORAL,10)
            self.note(im,'GPT型の生成は基本的に、これまでのトークンから次を順に予測。')
    def timeline(self,im,local):
        self.title(im,'工夫が積み重なり、GPT・BERTへ')
        dates=['2003','2013','2017','2018'];names=['ニューラル\n言語モデル','word2vec','Transformer','GPT・BERT']
        if self.short:
            rects=[(65,205+i*315,1015,465+i*315) for i in range(4)]
        else:rects=[(60+i*465,245,465+i*465,765) for i in range(4)]
        for i,(r,date,name) in enumerate(zip(rects,dates,names)):
            box(im,r,'white',22,TEAL if i<3 else CORAL,4);self.text(im,date,(r[0]+15,r[1]+30,r[2]-15,r[1]+140),86,TEAL if i<3 else CORAL)
            self.text(im,name,(r[0]+15,r[1]+178,r[2]-15,r[3]-35),43 if i==0 else 48)
        self.note(im,'代表的な研究の年表。論文初稿と公開記事・会議掲載を区別。')
    def frame(self,t,local,absolute):
        schedule=shots(t,self.kind);at,scene=next((a,s) for a,s in reversed(schedule) if local>=a);q=local-at
        self.current_turn=t['id']
        self.current_pose={'f05':'enjoyment','f08':'frustration','f10':'sadness','f18':'frustration','f33':'joy'}.get(t['id'],t['emotion'])
        self.dark=scene in {'male_close','female_close','duo','official_openai'}
        im=self.background(self.dark).copy()
        if scene in {'male_close','male_medium','female_close','female_medium'}:
            self.title(im,'GPTとBERTが生まれるまで' if t['visual']=='hook' else old.HEADINGS.get(t['visual'],'言語AIの仕組み'));self.presenter(im,t,q,scene)
        elif scene=='duo':self.title(im,'学び方を知ると、違いが見えてくる');self.duo(im,q)
        elif scene.startswith('official_'):self.official(im,q,scene)
        elif scene in {'result','compare'}:self.result(im,q)
        elif scene in {'gpt_example','gpt_chain','bert_example','bert_example_reveal'}:self.example(im,q,'gpt' if scene.startswith('gpt') else 'bert',reveal=scene.endswith('reveal'))
        elif scene in {'context','context_zoom'}:self.bank(im,q,scene.endswith('zoom'))
        elif scene in {'vectors','vector_features'}:self.vectors(im,q,scene.endswith('features'))
        elif scene in {'relations','positions'}:self.relations(im,q,scene=='positions')
        elif scene=='branches':self.branches(im,q)
        elif scene=='timeline':self.timeline(im,q)
        else:self.flow(im,q,scene)
        cap=next((c for c in t['subtitles'] if c['start']<=absolute<c['end']),None)
        if cap:
            r=(45,1560,1035,1805) if self.short else (60,872,1860,1035);box(im,r,NAVY,20)
            self.text(im,cap['text'],(r[0]+28,r[1]+20,r[2]-28,r[3]-20),64 if self.short else 50,'white')
        if self.short:self.badge(im,'【AI】',(50,1838,235,1895),TEAL,27)
        else:self.text(im,'【AI】',(60,1044,250,1078),23,TEAL)
        return im
    def ending(self,seconds):
        self.dark=False;im=self.background().copy()
        if self.short:
            self.title(im,'学び方の違いを、本編で');self.duo(im,3.7);return im
        self.text(im,'言語AIの「なぜ？」を、一緒に。',(100,60,1820,175),69)
        box(im,(90,270,790,735),'white',26,TEAL,4);box(im,(1130,270,1830,735),'white',26,CORAL,4)
        self.text(im,'関連動画',(125,405,755,540),64,TEAL);self.text(im,'次に学ぶテーマ',(1165,405,1795,540),60,CORAL)
        ImageDraw.Draw(im).ellipse((850,385,1070,605),fill='white',outline=TEAL,width=4)
        self.text(im,'登録',(870,450,1050,535),48,TEAL)
        self.text(im,'年表・原典・細かな条件は、詳細記事へ',(150,845,1770,985),52)
        return im


def manifest(kind):
    p=old.plan(kind);rows=[]
    for t in p['turns']:
        schedule=shots(t,kind)
        for i,(at,scene) in enumerate(schedule):
            end=schedule[i+1][0] if i+1<len(schedule) else t['end']-t['start']
            rows.append(dict(turn=t['id'],scene=scene,start=t['start']+at,end=t['start']+end,
                             role='official_quotation' if scene.startswith('official_') else 'presenter_question_or_response' if scene.startswith(('male_','female_')) or scene=='duo' else 'concrete_example_or_explanation',
                             updates='Token reveal, moving connectors or sequential emphasis; source figures remain intact',
                             presenter='close/chest-up/duo according to scene; hidden on evidence and detailed diagrams'))
    old.save(old.dest(kind)/'shot-plan.json',rows)
    return p,rows


def render(kind):
    cache();assert len(list((OUT/'motions/v04-closeups').glob('*/verification.json')))==2,'Both new close reactions are required'
    manifest(kind);old.Renderer=Renderer;old.motion_cache=cache
    old.render(kind)


def stills(kind):
    p,rows=manifest(kind);r=Renderer(kind);folder=OUT/'review/v04'/kind;folder.mkdir(parents=True,exist_ok=True)
    for i,s in enumerate(rows):
        t=next(t for t in p['turns'] if t['id']==s['turn']);when=s['start']+min(.9,(s['end']-s['start'])/2)
        r.frame(t,when-t['start'],when).save(folder/f'{i:02}-{s["turn"]}-{s["scene"]}.png')
    for t in p['turns']:
        for c in t['subtitles']:
            when=(c['start']+c['end'])/2;r.frame(t,when-t['start'],when)
    r.ending(2).save(folder/'ending.png');old.save(folder/'text-audit.json',list(r.c.audit.values()))
    print(json.dumps(dict(kind=kind,shots=len(rows),caption_states=sum(len(t['subtitles']) for t in p['turns']),text_boxes=len(r.c.audit))))


if __name__=='__main__':
    if hasattr(__import__('sys').stdout,'reconfigure'):__import__('sys').stdout.reconfigure(encoding='utf-8')
    a=argparse.ArgumentParser();a.add_argument('action',choices=['plan','cache','stills','render','audio-build','audio-mux']);a.add_argument('--kind',choices=['short','full'],default='short');args=a.parse_args()
    if args.action=='plan':manifest(args.kind)
    elif args.action=='cache':cache()
    elif args.action=='stills':stills(args.kind)
    elif args.action=='render':render(args.kind)
    else:
        import audio
        audio.build(args.kind) if args.action=='audio-build' else audio.mux(args.kind)
