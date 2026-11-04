"""Accepted model-race short/full: explicit evidence, moving diagrams and dialogue."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,os,shutil,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,fit,arrow
from tools.studio.editorial_captions import timed_captions,phrase_lines,PROTECTED
from tools.studio.editorial_presenters import equalized_face
from tools.studio.dialogue_avatar import SpriteAtlas,voice_gate
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
from tools.studio.closing_visuals import end_screen

OUT=ROOT/'outputs/content-projects'/HERE.name;ASSETS=OUT/'assets';FPS=24
REVISIONS={'short':'v01','full':'v02'}
SCRIPTS={'short':'v03','full':'v04'}
NAVY='#10283D';TEAL='#087E82';COPPER='#BA684E';GOLD='#C79739';PURPLE='#7158A9';PAPER='#F7F5F0';MUTED='#A8C4CE'
PROTECT=PROTECTED+('GPT-6.1 Sol','GPT-6 Astra','GPT-6.1 Astra','GPT-6.2 Astra','Fable 5.1','Fable 5.5','Fable 5','Opus 5.5','Opus 5','5分の1','100万トークン','コンピューター操作','エージェント型コーディング')
CHAPTERS={'01':'AI競争、何が変わった？','02':'6月｜Fable 5の登場','03':'7月｜Opus 5を日常業務へ','04':'9月｜コンピューター操作へ','05':'9月後半｜性能とAPI単価','06':'自分の仕事で、どう比べる？','07':'自律性と、権限を守ること','08':'次世代の報道と噂を確かめる','09':'次のモデルを、どう見る？'}
# Every camera/diagram change has a semantic role; captions update independently.
FULL_VISUAL=['hero','duo_question','roadmap','fable_source','pipeline_question','pipeline','access','cost_question','opus5','workloads','september_question','fable51_source','dates','computer','computer_result','layers','opus55_source','sol_source','price_question','price_scope','prices','cost_result','cost_drivers','timeline_summary','benchmark_question','benchmark','fair_test','scope_question','scope','safety','future_question','certainty','fable55','cadence','sources','astra61','report_result','astra62','identifier','source_question','checklist','closing_hope','audience','related']
SHORT_VISUAL=['hero','duo_question','short_timeline','short_prices','future_question','short_rumors','short_closing']
HEADINGS={
 'hero':'Fable 5からGPT-6へ、何が変わった？','duo_question':'結局、何が変わった？','roadmap':'Fable 5からGPT-6.1 Solへ',
 'fable_source':'複雑なタスクを、長時間・自律実行','pipeline_question':'不具合を直して、テストまで？','pipeline':'読む → 直す → テスト → 報告','access':'発表日と、利用できた期間は別',
 'cost_question':'毎日の業務でも、使えるコスト？','opus5':'コーディング・ナレッジワークを強化','workloads':'同じモデルを、同じ設定で使う？',
 'september_question':'9月の2モデル、何が違う？','fable51_source':'コーディングや長時間の問題解決を強化','dates':'Fable 5.1は「9月」として整理',
 'computer':'ブラウザやアプリを操作して、タスクを完了','computer_result':'答えるだけでなく、操作して進める','layers':'モデル ＋ ツール ＋ 権限 ＋ 確認',
 'opus55_source':'多くの業務でFable 5.1と同水準','sol_source':'Astraに迫る性能を、5分の1のAPI単価で','price_question':'月額も、5分の1になる？',
 'price_scope':'標準の入出力トークン単価の比較','prices':'100万トークンあたりの標準API単価','cost_result':'単価 × 使用量。やり直しも含めて見る','cost_drivers':'成果までの費用と時間で選ぶ',
 'timeline_summary':'公式発表の言葉で、転機を振り返る','benchmark_question':'点数が一番高いモデルなら、安心？','benchmark':'問題・道具・予算が違えば、数字も違う','fair_test':'同じ入力・道具・完了条件で比べる',
 'scope_question':'賢くなるほど、やりすぎない？','scope':'下書きの依頼 ≠ 顧客への送信','safety':'ユーザーの意図・作業範囲・正確な報告',
 'future_question':'次のモデルは、もう決まっている？','certainty':'公式発表・報道・未確認を分ける','fable55':'Fable 5.5？ 名称・時期は未確認','cadence':'Opus 5.5の次が、Fable 5.5とは限らない','sources':'正式なモデル一覧と、報道を分ける',
 'astra61':'GPT-6.1 Astraは、公開見送りの報道','report_result':'番号が進んでも、必ず公開されるとは限らない','astra62':'GPT-6.2 Astra？ 投稿画像の出所に注意','identifier':'名前の表示だけで、製品の実態は分からない',
 'source_question':'何が分かり、何がまだ分からない？','checklist':'次の公式発表で、4つを確かめる','closing_hope':'任せられるタスクが、どう変わる？','audience':'次のモデルに、何を任せたい？','related':'実際のアプリ操作も、関連動画で',
 'short_timeline':'長時間の自律タスク → コンピューター操作','short_prices':'Astraに迫る性能。標準API単価は5分の1','short_rumors':'次世代の噂は、確度を分けて','short_closing':'成果・コスト・権限の確認を見る'}

def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dest(kind):return OUT/'release'/REVISIONS[kind]/kind
def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)

def prepare_motion():
    for name in ['male-thinking','male-happy','female-understanding']:
        source=next((ROOT/'outputs/content-projects/CONTENT_20261030_chatgpt_pro_usage_news/motions/v01'/name).glob('MiniMax*.mp4'))
        target=ASSETS/(name+'.mp4')
        if not target.exists():shutil.copy2(source,target)
        assert sha(source)==sha(target)
    records=[]
    for name in ['male-thinking','male-happy','male-understanding','female-thinking','female-happy','female-understanding']:
        target=ASSETS/(name+'.mp4');cache=OUT/'motion-cache'/name
        probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]).stdout)
        if not (cache/'complete.json').exists():
            cache.mkdir(parents=True,exist_ok=True)
            run(['ffmpeg','-v','error','-nostdin','-n','-i',str(target),'-vf',"fps=24,scale=w='min(700,iw)':h=-2",'-q:v','2',str(cache/'%04d.jpg')])
            save(cache/'complete.json',dict(sha256=sha(target),frames=len(list(cache.glob('*.jpg')))))
        records.append(dict(name=name,path=target.relative_to(ROOT).as_posix(),sha256=sha(target),probe=probe))
    save(OUT/'motion-provenance.json',records)
    tiles=[]
    for x in records:
        files=sorted((OUT/'motion-cache'/x['name']).glob('*.jpg'));im=Image.open(files[len(files)//2]);tile=Image.new('RGB',(320,400),NAVY);fit(tile,im,(0,35,320,400));Canvas().text(tile,x['name'],(5,4,315,32),20,'white');tiles.append(tile)
    sheet=Image.new('RGB',(320*3,800),NAVY)
    for i,tile in enumerate(tiles):sheet.paste(tile,(i%3*320,i//3*400))
    sheet.save(OUT/'work/motions-contact.jpg')

def make_plan(kind):
    folder=dest(kind);folder.mkdir(parents=True,exist_ok=True)
    script_file=HERE/f'{kind}-dialogue-{SCRIPTS[kind]}.json'
    script=json.loads(script_file.read_text(encoding='utf-8'));visuals=SHORT_VISUAL if kind=='short' else FULL_VISUAL
    turns=[];cursor=0;chapters=[]
    for t,visual in zip(script['turns'],visuals,strict=True):
        voice=OUT/('voice/v02' if t['id']=='f02' and kind=='full' else 'voice/v01')/t['id']/'voice.wav'
        if not voice.exists():raise RuntimeError('Voice not ready: '+t['id'])
        proof=json.loads(voice.with_name('verified.json').read_text(encoding='utf-8'));assert sha(voice).upper()==next(x['sha256'] for x in proof['files'] if x['path'].endswith('voice.wav'))
        seconds=len(read_voice(voice))/SR;lead=.15;tail=.35 if t['speaker']=='male' else .5
        if visual in ['prices','access','dates','astra62']:tail+=.65
        if kind=='short' and visual=='short_closing':tail+=1.1
        frames=math.ceil((lead+seconds+tail)*FPS);end=cursor+frames/FPS
        turn=dict(t,visual=visual,heading=HEADINGS[visual],start=cursor,end=end,frames=frames,voice_start=cursor+lead,voice_seconds=seconds,voice_path=voice.relative_to(ROOT).as_posix())
        turn['subtitles']=timed_captions(t['display'],turn['voice_start'],seconds,930 if kind=='short' else 1580,56 if kind=='short' else 50,protected=PROTECT)
        turns.append(turn)
        if not chapters or chapters[-1]['id']!=t['chapter']:chapters.append(dict(id=t['chapter'],title=CHAPTERS[t['chapter']],start=cursor))
        cursor=end
    ending=10 if kind=='full' else 0
    plan=dict(kind=kind,revision=REVISIONS[kind],script_revision=SCRIPTS[kind],width=1080 if kind=='short' else 1920,height=1920 if kind=='short' else 1080,fps=FPS,seconds=cursor+ending,body_seconds=cursor,end_seconds=ending,frames=round((cursor+ending)*FPS),turns=turns,chapters=chapters,source_script_sha256=sha(script_file))
    save(folder/'timeline.json',plan)
    def stamp(x):
        n=round(x*1000);h,n=divmod(n,3600000);m,n=divmod(n,60000);s,n=divmod(n,1000);return f'{h:02}:{m:02}:{s:02},{n:03}'
    subs=[s for t in turns for s in t['subtitles']]
    (folder/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subs))+'\n',encoding='utf-8')
    print(kind,'seconds',round(plan['seconds'],3),'captions',len(subs),flush=True);return plan

class Renderer:
    def __init__(self,kind,layout_only=False):
        self.layout_only=layout_only
        self.short=kind=='short';self.w,self.h=(1080,1920) if self.short else (1920,1080)
        self.canvas=Canvas();self.gates={};self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']}
        self.pictures={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.name}
        self.motion_files={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'motion-cache').iterdir() if p.is_dir()}
        self.wording={x['id']:x['display'] for x in json.loads((HERE/'wording-v03.json').read_text(encoding='utf-8'))['entries']}
    def text(self,im,value,rect,size=44,color='white',center=True):self.canvas.text(im,value,rect,size,color,center)
    def multiline(self,value,width,size):return '\n'.join(phrase_lines(value,width,size,protected=PROTECT))
    @lru_cache(maxsize=80)
    def tile(self,name,width,height):return ImageOps.contain(self.pictures[name],(width,height),Image.Resampling.LANCZOS)
    def picture(self,im,name,rect):
        tile=self.tile(name,rect[2]-rect[0],rect[3]-rect[1]);im.paste(tile,(round((rect[0]+rect[2]-tile.width)/2),round((rect[1]+rect[3]-tile.height)/2)))
    @lru_cache(maxsize=48)
    def motion_tile(self,name,index,width,height):
        source=Image.open(self.motion_files[name][index]).convert('RGB');w,h=source.size
        crop=(0,round(h*.08),w,round(h*.85)) if name=='male-understanding' else (round(w*.06),round(h*.28),round(w*.94),round(h*.76))
        return ImageOps.fit(source.crop(crop),(width,height),method=Image.Resampling.LANCZOS,centering=(.5,.42))
    def motion(self,im,name,local,rect):
        # Play once, then hold. Do not loop the same gesture through a long explanation.
        index=min(len(self.motion_files[name])-1,max(0,int(local*FPS)))
        im.paste(self.motion_tile(name,index,rect[2]-rect[0],rect[3]-rect[1]),(rect[0],rect[1]))
    @lru_cache(maxsize=240)
    def face(self,who,mood,opened,size):return equalized_face(self.atlas[who],who,mood,opened,size)
    def presenters(self,im,t,local,large=False):
        size=(310 if large else 190) if not self.short else (330 if large else 210)
        y=(355 if large else 655) if not self.short else (690 if large else 1110)
        xx=(70,self.w-70-size) if not self.short else (55,self.w-55-size)
        for who,x in zip(['male','female'],xx):
            active=who==t['speaker'];opened=False
            if active and not self.layout_only:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(ROOT/t['voice_path'])['gates']
                i=math.floor((t['start']+local-t['voice_start'])*FPS);g=self.gates[t['id']];opened=g[i] if 0<=i<len(g) else False
            mood='curious' if 'question' in t['visual'] else 'pleased' if any(x in t['visual'] for x in ['result','closing','audience','related']) else 'serious' if t['chapter'] in ['07','08'] else 'neutral'
            if not active and mood=='curious':mood='serious'
            box(im,(x-5,y-5,x+size+5,y+size+5),TEAL if active else '#496275',24)
            im.paste(self.face(who,mood,opened,size),(x,y))
    def card(self,im,title,body,rect,color=TEAL,size=42):
        x,y,x2,y2=rect;box(im,rect,'#FFFFFF',22,outline=color,width=3)
        self.text(im,title,(x+20,y+15,x2-20,y+80),size,color)
        if body:self.text(im,body,(x+22,y+98,x2-22,y2-20),size-4,NAVY)
    def dashed(self,im,rect,color=GOLD):
        d=ImageDraw.Draw(im);x,y,x2,y2=rect
        for a,b in [((x,y),(x2,y)),((x,y2),(x2,y2))]:
            for q in range(round(a[0]),round(b[0]),32):d.line((q,a[1],min(q+18,b[0]),b[1]),fill=color,width=4)
        for xx in [x,x2]:
            for q in range(round(y),round(y2),32):d.line((xx,q,xx,min(q+18,y2)),fill=color,width=4)
    @lru_cache(maxsize=90)
    def stage(self,chapter,visual,heading):
        warm=visual in ['fable_source','fable51_source','opus5','opus55_source'];bg=PAPER if warm else NAVY
        im=Image.new('RGB',(self.w,self.h),bg);d=ImageDraw.Draw(im)
        if self.short:
            box(im,(45,45,1035,108),TEAL,16);self.text(im,'ChatGPT × Claude  |  2026',(60,52,1020,99),30)
            self.text(im,self.multiline(heading,960,54),(60,145,1020,315),54,NAVY if warm else 'white')
        else:
            self.text(im,'AI MODEL RACE 2026',(55,25,665,67),30,COPPER if warm else '#86D7DC',False)
            self.text(im,CHAPTERS[chapter],(800,25,1660,67),30,NAVY if warm else MUTED,False)
            self.text(im,chapter+' / 09',(1700,24,1860,67),29,NAVY if warm else MUTED)
            self.text(im,heading,(55,96,1865,161),46,NAVY if warm else 'white',False)
            d.line((55,185,1865,185),fill='#D3C9BE' if warm else '#2D526A',width=2)
        return im
    def source(self,im,value):
        y=1755 if self.short else 876
        color=NAVY if im.getpixel((0,0))==Image.new('RGB',(1,1),PAPER).getpixel((0,0)) else MUTED
        self.text(im,value,(55,y,self.w-55,y+49),28,color,False)
    def frame(self,t,local,caption=True):
        im=self.stage(t['chapter'],t['visual'],t['heading']).copy()
        if self.short:self.short_body(im,t,local)
        else:self.full_body(im,t,local)
        if caption:
            current=next((s['text'] for s in t['subtitles'] if s['start']<=t['start']+local<s['end']),None)
            if current:
                rect=(35,1440,1045,1695) if self.short else (60,922,1860,1080)
                box(im,rect,'#0A1928',22)
                self.text(im,current,(70,1462,1010,1673) if self.short else (160,935,1800,1075),56 if self.short else 50)
        return im

    def timeline(self,im,local,seconds):
        items=[('6月9日','Fable 5','複雑なタスクを\n長時間、自律実行',COPPER),('9月3日','GPT-6 Astra','コンピューター操作で\nタスクを完了',TEAL),('9月29日','GPT-6.1 Sol','Astraに迫る性能を\n低いAPI単価で',TEAL)]
        phase=min(2,int(local/max(seconds,.1)*3));d=ImageDraw.Draw(im)
        for i,(date,name,body,color) in enumerate(items):
            x=100+i*590;y=355
            d.line((x+250,280,x+250,y),fill=color,width=5)
            self.text(im,date,(x,215,x+500,277),38,'#CCE5E8')
            self.card(im,name,body,(x,y,x+500,665),color,45)
            if i==phase:d.rounded_rectangle((x-7,y-7,x+507,672),radius=24,outline='#F5D387',width=5)
            if i<2:arrow(im,[(x+515,510),(x+575,510)],TEAL,7)
        self.text(im,'その間にOpus 5、Fable 5.1、Opus 5.5も登場',(200,735,1720,800),36,MUTED)
        self.source(im,'出典：Anthropic・OpenAI公式発表／OpenAI API更新履歴。横幅は日数・性能を表さない。')

    @lru_cache(maxsize=5)
    def fable_art(self):
        # Crop only official product art. Source heading/date remain in the preserved parent.
        return self.pictures['fable5'].crop((0,120,1140,760))

    def source_hero(self,im,local):
        fit(im,self.fable_art(),(70,220,900,795));self.picture(im,'astra',(1020,220,1850,795))
        self.text(im,'Fable 5',(100,805,870,861),48,'#F1C5B3')
        self.text(im,'GPT-6 Astra',(1050,805,1820,861),48,'#9CE0DC')
        arrow(im,[(935,490),(985,490)],GOLD,9)
        self.source(im,'出典：Anthropic・OpenAIの公式発表ビジュアル。モデルの性能順位を表す図ではない。')

    def flow(self,im,local,seconds,labels,sub=None,connector='arrow'):
        n=len(labels);width=(1660-(n-1)*38)/n;phase=min(n-1,int(local/max(seconds,.1)*n))
        for i,value in enumerate(labels):
            x=130+i*(width+38);y=360
            self.card(im,f'{i+1:02}',value,(x,y,x+width,y+255),TEAL if i<=phase else '#78909C',43)
            if i<n-1:
                if connector=='plus':self.text(im,'＋',(x+width+3,y+95,x+width+35,y+154),30,MUTED)
                else:arrow(im,[(x+width+7,y+130),(x+width+31,y+130)],TEAL,7)
                if i==phase and connector=='arrow':
                    q=(local*1.15)%1;cx=x+width+7+24*q;ImageDraw.Draw(im).ellipse((cx-6,y+124,cx+6,y+136),fill='#F5D387')
        if sub:self.text(im,sub,(130,695,1790,808),41,MUTED)

    def quote(self,im,name,title,note):
        self.picture(im,name,(110,235,1810,817))
        # The quotation is an official excerpt; the explanation is our paraphrase.
        self.source(im,note)

    def full_body(self,im,t,local):
        v=t['visual'];seconds=t['end']-t['start'];phase=local/max(seconds,.01)
        if v in ['hero','roadmap','timeline_summary']:
            if v=='hero' and local<4.0:self.source_hero(im,local)
            else:self.timeline(im,local,seconds)
            if v=='hero' and local>=4.0:
                self.text(im,'自律タスク  ×  コスト  ×  ユーザーの意図',(230,815,1690,871),37,'#F2D69D')
        elif v.endswith('question') or v in ['cost_question','september_question','price_question','benchmark_question','scope_question','future_question','source_question']:
            self.presenters(im,t,local,large=True)
            question={
              'duo_question':'次々に出るけど、\n結局どこが変わった？','pipeline_question':'直して、\nテストする所まで？','cost_question':'毎日の業務で\n使い続けられる？','september_question':'Fable 5.1とAstra、\n何を比べる？','price_question':'月額料金まで\n5分の1になる？','benchmark_question':'点数が一番なら\n間違いない？','scope_question':'勝手にやりすぎる\nことはない？','future_question':'Fable 5.5？\nAstra 6.1・6.2？','source_question':'何が確かめられて、\n何がまだ分からない？'}[v]
            self.text(im,question,(430,370,1490,590),54)
        elif v=='fable_source':self.quote(im,'fable5',t['heading'],'出典：Anthropic「Claude Fable 5 and Claude Mythos 5」／2026年6月9日発表')
        elif v=='fable51_source':
            self.picture(im,'fable51',(170,245,1750,625))
            self.text(im,'コーディング  ・  ナレッジワーク  ・  長時間の問題解決',(200,710,1720,806),39,NAVY)
            self.source(im,'出典：Anthropic「Claude Fable 5.1 and Mythos 5.1」／2026年9月')
        elif v=='opus55_source':
            self.quote(im,'opus55',t['heading'],'出典：Anthropic「Claude Opus 5.5」／2026年9月22日発表。性能の位置づけは提供元の説明。')
            self.text(im,'Opus 5.5  ／  GPT-6 Sol・Luna',(200,751,1720,822),40,NAVY)
        elif v=='sol_source':
            self.picture(im,'sol61',(170,280,1750,570))
            self.text(im,'エージェント型コーディング\nコンピューター操作・専門業務',(230,640,1690,797),47)
            self.source(im,'出典：OpenAI「GPT-6.1 Sol のご紹介」／API更新履歴：2026年9月29日')
        elif v=='pipeline':self.flow(im,local,seconds,['コードを読む','原因を調べる','修正する','テストで確認'],'一問への回答から、複数ステップのタスクへ')
        elif v=='access':
            self.flow(im,local,seconds,['6月9日\n発表','6月12日\nアクセス停止','7月1日\n再開'],'発表から、連続して利用できたわけではない')
            self.source(im,'出典：Anthropic「Redeploying Claude Fable 5」／7月1日の更新')
        elif v=='opus5':
            self.motion(im,'male-thinking',local,(100,225,760,840))
            self.card(im,'Claude Opus 5','コーディング・\nナレッジワークを強化',(850,310,1790,700),COPPER,54)
            self.source(im,'出典：Anthropic「Introducing Claude Opus 5」／2026年7月24日')
        elif v=='workloads':
            self.card(im,'毎日のコードレビュー','変更を確認\nテスト・指摘を整理',(130,300,870,728),TEAL,49)
            self.card(im,'数日にわたる調査','情報を集める\n仮説を比較・検証',(1050,300,1790,728),COPPER,49)
            self.text(im,'例：タスクに合わせ、モデルや設定を選ぶ',(150,775,1770,840),40,MUTED)
        elif v=='dates':
            self.card(im,'Fable 5.1','発表ページ：9月\n製品ページ：9月1日\nニュース一覧：9月15日',(130,265,1030,754),COPPER,44)
            self.card(im,'動画での表記','「9月」\n先後を無理に断定しない',(1130,350,1790,710),TEAL,43)
            self.source(im,'出典：Anthropicの発表ページ・Fable製品ページ・モデルニュース一覧／2026年11月3日確認')
        elif v=='computer_result':
            self.motion(im,'male-happy',local,(75,220,820,850))
            self.text(im,'ブラウザやアプリを操作し、\nタスクを完了する力へ',(915,388,1820,588),48)
            self.text(im,'入力  →  更新  →  資料の下書き',(900,720,1830,791),36,MUTED)
            self.source(im,'出典：OpenAI「GPT-6 Astra」日本語公式発表。モデル・ツール・権限の条件は別に確認。')
        elif v=='computer':
            self.desktop_examples(im,local,seconds)
            self.source(im,'出典：OpenAI「GPT-6 Astra」日本語公式発表。例の図解であり、この動画での実演ではない。')
        elif v=='layers':self.flow(im,local,seconds,['モデル','ツール・アプリ','権限','人の確認'],'モデル名だけで、使える機能のすべては決まらない',connector='plus')
        elif v in ['price_scope','prices','short_prices']:self.price_chart(im,local,seconds)
        elif v in ['cost_result','cost_drivers']:
            self.text(im,'単価  ×  使用量',(300,215,1620,325),75,'#9FE0DD')
            self.flow(im,local,seconds,['入力・出力','キャッシュ','ツール','再試行'],'成果までのコストと時間を、同じ条件で確かめる',connector='plus')
            self.source(im,'料金条件はOpenAI公式のモデル仕様を参照。仕事の総額を一律に5分の1とはしない。')
        elif v in ['benchmark','fair_test']:
            self.flow(im,local,seconds,['同じ入力','同じ道具','同じ予算','同じ完了条件'],'今回は同条件の独自性能対決を実演していない',connector='plus')
        elif v=='scope':
            self.scope_diagram(im,local)
        elif v=='safety':
            self.flow(im,local,seconds,['ユーザーの\n意図を理解','作業範囲・\n権限を守る','実行内容を\n正確に報告'],'進める力と、止まるべき所で止まる力')
            self.source(im,'出典：OpenAI「GPT-6 Astra」公式発表。提供元の評価・方針を紹介。')
        elif v in ['certainty','fable55','cadence','sources','astra61','report_result','astra62','identifier']:self.rumor(im,t,local)
        elif v=='checklist':
            self.flow(im,local,seconds,['モデル名・\n対象ユーザー','任せられる\nタスク','コストの\n条件','権限・\n人の確認'],'公式発表と、自分のアカウントの利用可否は別に確認')
        elif v in ['closing_hope','audience','related']:
            name='female-happy' if v=='closing_hope' else 'male-happy' if v=='audience' else 'female-understanding'
            self.motion(im,name,local,(70,215,850,860))
            text='次は、何を\n任せたい？' if v=='audience' else '任せられるタスクの\n変化を、一緒に。' if v=='closing_hope' else 'アプリの実演\n確認・修正の流れも'
            self.text(im,text,(930,370,1800,620),62)
            self.text(im,'コード  ／  資料  ／  コンピューター操作',(910,730,1820,802),35,MUTED)
        else:raise ValueError('Unknown visual '+v)

    def desktop_examples(self,im,local,seconds):
        d=ImageDraw.Draw(im);phase=min(2,int(local/max(seconds,.1)*3));q=(local/max(seconds,.1)*3)%1
        box(im,(130,275,1790,815),'#E8F0F3',24)
        box(im,(130,275,1790,347),'#315A70',24)
        for i,name in enumerate(['フォームへ入力','顧客情報を更新','調査・資料の下書き']):
            x=170+i*520;box(im,(x,286,x+490,337),TEAL if i==phase else '#426B7F',10);self.text(im,name,(x+10,291,x+480,331),31)
        self.text(im,'公式発表の用途例',(190,374,1740,426),30,NAVY,False)
        if phase<2:
            titles=['案件名','担当'] if phase==0 else ['顧客名','対応状況']
            values=['デモ案件','デモ担当'] if phase==0 else ['デモ顧客','確認済み']
            for i,(title,value) in enumerate(zip(titles,values)):
                y=470+i*120;self.text(im,title,(200,y,530,y+65),40,NAVY,False);box(im,(560,y-3,1685,y+77),'white',12,outline='#AFC2CA',width=2)
                if q>.18+i*.23:self.text(im,value,(595,y+3,1635,y+66),41,NAVY,False)
            status='入力中' if q<.6 else '入力完了' if phase==0 else '更新完了'
            box(im,(1250,724,1678,781),TEAL,13);self.text(im,status,(1260,729,1668,775),31)
        else:
            box(im,(205,455,895,755),'white',14);box(im,(1000,455,1675,755),'white',14)
            self.text(im,'リサーチ',(235,476,860,535),39,NAVY)
            self.text(im,'要点の下書き',(1030,476,1645,535),39,NAVY)
            for i in range(4):
                d.line((250,575+i*40,830-(i%2)*85,575+i*40),fill='#92AAB5',width=8)
                if q>(i+1)*.17:d.line((1050,575+i*40,1615-(i%2)*90,575+i*40),fill='#3E9294',width=8)
            arrow(im,[(920,615),(970,615)],TEAL,8)
        cx=1400+90*math.sin(local*.7);cy=535+60*math.cos(local*.8)
        d.polygon([(cx,cy),(cx+9,cy+43),(cx+20,cy+28),(cx+37,cy+27)],fill=NAVY,outline='white',width=2)

    def scope_diagram(self,im,local):
        d=ImageDraw.Draw(im);box(im,(170,300,790,755),'white',22)
        self.text(im,'下書きを作る',(205,330,755,405),47,TEAL)
        for i in range(5):d.line((235,470+i*45,720-(i%2)*110,470+i*45),fill='#88A1AD',width=9)
        arrow(im,[(820,535),(960,535)],TEAL,10)
        d.line((1000,315,1000,770),fill=GOLD,width=9)
        box(im,(890,230,1110,300),GOLD,13);self.text(im,'人が確認',(900,237,1100,291),35,NAVY)
        box(im,(1150,380,1760,680),'#294657',23,outline='#6D8390')
        self.text(im,'顧客へ送信',(1180,410,1730,482),48,MUTED)
        self.text(im,'別の判断',(1190,548,1720,617),47,'#E7CA89')
        self.text(im,'下書きの依頼だけで、送信まで許可されたとは限らない',(170,799,1760,865),39,'#E7CA89')

    def price_chart(self,im,local,seconds):
        self.text(im,'100万トークンあたり・USD',(180,224,1740,285),36,'#9DDCD9')
        d=ImageDraw.Draw(im);grow=smooth(local/1.3)
        for x,title,values,maximum in [(120,'入力',[10,2],10),(1010,'出力',[50,10],50)]:
            box(im,(x,310,x+790,743),'#193B50',24)
            self.text(im,title,(x+35,330,x+755,389),46)
            for i,(name,value,color) in enumerate(zip(['Astra','6.1 Sol'],values,[COPPER,'#4CBDB6'])):
                y=435+i*135
                self.text(im,name,(x+30,y-8,x+250,y+48),38,'white',False)
                xx=x+270;length=350*value/maximum*grow
                if length>1:box(im,(xx,y,xx+length,y+43),color,8)
                self.text(im,f'${value}',(x+285+350*value/maximum,y-8,x+775,y+51),40,color,False)
            d.line((x+270,420,x+270,642),fill='#A5BBC4',width=2)
            self.text(im,'0',(x+255,662,x+290,703),27,MUTED)
        self.text(im,'月額の値下げや、仕事の総額が5分の1という意味ではない',(140,779,1780,845),38,'#F3D594')
        self.source(im,'出典：OpenAI「GPT-6.1 Sol」公式発表・モデル仕様／標準の入出力API単価／2026年11月3日確認')

    def rumor(self,im,t,local):
        v=t['visual'];seconds=t['end']-t['start']
        self.text(im,'2026年11月3日時点',(1320,211,1810,265),30,'#E9C986')
        if v=='certainty':
            for i,(title,body,color) in enumerate([('公式発表','提供元が示した\nモデル・条件',TEAL),('報道','取材・公開見出し\n確認範囲を限定',PURPLE),('未確認情報','名称の目撃・予測\n事実と分ける',GOLD)]):
                x=100+i*590;self.card(im,title,body,(x,340,x+500,734),color,49)
                if i==2:self.dashed(im,(x-7,333,x+507,741),color)
        elif v=='cadence':
            self.motion(im,'female-thinking',local,(75,250,820,850))
            self.text(im,'Opus 5.5の発表だけで\nFable 5.5の予定は決めない',(910,380,1820,601),45,'#EBD4A0')
            self.source(im,'出典：Anthropic公式発表一覧／同じ世代番号でも、未発表モデルの予定は推定しない。')
        elif v in ['fable55','sources']:
            self.card(im,'Fable 5.5？','名称・公開日・価格\n正式発表は未確認',(100,340,930,735),GOLD,58)
            self.dashed(im,(90,330,940,745))
            body='Opus 5.5の発表だけで\nFableの次を決めない' if v=='cadence' else '次期モデルの報道と\n正式なモデル一覧は別' if v=='sources' else '次期モデル準備の報道\n名称は確認されていない'
            self.text(im,body,(1030,420,1810,625),44,'#EBD4A0')
            self.source(im,'出典：Anthropic製品・発表一覧／The Information（10月19日）の公開見出しまで確認')
        elif v=='report_result':
            self.motion(im,'male-understanding',local,(75,230,820,850))
            self.text(im,'番号が進むことと\n公開できることは別',(915,390,1820,620),51)
            self.source(im,'出典：WSJのGPT-6.1 Astra公開見送りの報道／モデル番号から公開予定を推定しない。')
        elif v=='astra61':
            self.card(im,'GPT-6.1 Astra','WSJが9月に\n公開見送りを報道',(170,320,1750,735),PURPLE,64)
            self.text(im,'近日登場の予定として並べない',(300,782,1620,840),42,'#D6BCEB')
            self.source(im,'出典：The Wall Street Journal「OpenAI Scraps Release of New AI Model Over Safety Concerns」')
        elif v=='astra62':
            box(im,(160,280,1760,830),'#1A3449',24)
            self.text(im,'一般ユーザーの投稿。OpenAIの正式発表ではない',(220,291,1700,352),35,'#EBD4A0')
            self.picture(im,'astra62-post-author',(440,370,1480,460))
            self.picture(im,'astra62-usage-image',(440,487,1480,785))
            self.text(im,'利用量の内訳とされる画像。性能スコアではない。',(230,825,1690,875),32,'#EBD4A0')
            self.source(im,'出典：@TokenGremlin（11月1日）と補足。投稿者は他者提供・元画像の出所不明と説明。')
        else:
            self.text(im,'gpt-6.2-astra',(250,365,1670,485),84,'#EBD4A0')
            self.text(im,'投稿の名称  ≠  正式な製品仕様',(250,535,1670,620),51)
            self.text(im,'一般提供？  性能？  公開日？',(250,700,1670,780),48,MUTED)

    def short_body(self,im,t,local):
        v=t['visual'];seconds=t['end']-t['start']
        if v=='hero':
            if local<2.5:
                fit(im,self.fable_art(),(65,460,1015,870));self.picture(im,'astra',(200,900,880,1370))
                self.text(im,'Fable 5  →  GPT-6 Astra',(60,350,1020,418),50,'#F1D7B1')
                self.source(im,'出典：Anthropic・OpenAIの公式発表ビジュアル')
                return
            for i,(title,body,color) in enumerate([('タスクを自律実行','複雑な作業を、続けて進める',COPPER),('コストを下げる','性能だけでなく、API単価も',TEAL),('人の意図に沿って動く','任せた範囲と、権限を守る',PURPLE)]):
                y=390+i*300;self.card(im,title,body,(65,y,1015,y+235),color,49)
                if min(2,int(local/max(seconds,.1)*3))==i:ImageDraw.Draw(im).rounded_rectangle((59,y-6,1021,y+241),radius=25,outline='#F5D387',width=5)
        elif v in ['duo_question','future_question']:
            self.presenters(im,t,local,large=True)
            text='Fable 5 → GPT-6' if v=='duo_question' else 'Fable 5.5？\nAstra 6.1・6.2？'
            self.text(im,text,(60,380,1020,600),64)
            self.text(im,'どこが変わった？' if v=='duo_question' else '次は、もう決まっている？',(80,1110,1000,1260),55)
        elif v=='short_timeline':
            first=local<seconds*.48
            self.text(im,'Fable 5' if first else 'GPT-6 Astra',(70,365,1010,450),69,'#F1C5B3' if first else '#9CE0DC')
            if first:fit(im,self.fable_art(),(65,505,1015,1190))
            else:self.picture(im,'astra',(140,475,940,1240))
            self.text(im,'複雑なタスクを、長時間・自律実行' if first else 'ブラウザやアプリを操作して進める',(60,1260,1020,1360),43,'white')
            self.source(im,'出典：Anthropic・OpenAI公式発表')
        elif v=='short_prices':
            self.text(im,'標準API・100万トークンあたり',(65,370,1015,455),44,'#A2DEDA')
            d=ImageDraw.Draw(im);grow=smooth(local/1.3)
            for y,label,a,b in [(510,'入力',10,2),(900,'出力',50,10)]:
                self.text(im,f'{label}  ${a} → ${b}',(70,y,1010,y+90),66,'#F5D387')
                for k,(name,amount,color) in enumerate([('Astra',1,COPPER),('6.1 Sol',.2,'#4CBDB6')]):
                    yy=y+135+k*90;self.text(im,name,(80,yy-10,330,yy+50),43,'white',False)
                    if grow>0:box(im,(350,yy,350+610*amount*grow,yy+45),color,9)
                d.line((350,y+125,350,y+280),fill='#C4D4D9',width=2)
            self.text(im,'月額・仕事の総額の比較ではない',(65,1305,1015,1395),40,'#F5D387')
            self.source(im,'出典：OpenAI「GPT-6.1 Sol」公式発表')
        elif v=='short_rumors':
            for i,(name,status,color) in enumerate([('Fable 5.5？','名称・公開日：未確認',GOLD),('GPT-6.1 Astra','公開見送りの報道',PURPLE),('GPT-6.2 Astra？','投稿画像の出所は不明',GOLD)]):
                y=385+i*298;self.card(im,name,status,(70,y,1010,y+245),color,50)
                if i!=1:self.dashed(im,(63,y-7,1017,y+252),color)
            self.text(im,'2026年11月3日時点',(80,1325,1000,1390),34,'#E9CD91')
            self.source(im,'出典：各社公式・WSJ・投稿者の補足')
        elif v=='short_closing':
            self.motion(im,'female-understanding',local,(70,355,1010,1115))
            self.text(im,'転機と噂の根拠は\nフル動画で詳しく',(70,1160,1010,1350),53)
        else:raise ValueError('Unknown short visual '+v)

    def ending(self,local):
        def label(im,value,rect,size,color):
            if value=='Codex・ChatGPTを、毎日の仕事へ。':value='ChatGPT・Claudeを、毎日の仕事へ。'
            elif value=='これからの改善も、一緒に楽しみましょう。':value='次のモデルも、一緒に確かめていこう。'
            self.text(im,value,rect,size,color)
        return end_screen(local,label=label)

def preview(kind):
    plan=make_plan(kind);r=Renderer(kind);folder=dest(kind)/'layout';folder.mkdir(parents=True,exist_ok=True);thumbs=[]
    for t in plan['turns']:
        for i,s in enumerate(t['subtitles']):r.frame(t,(s['start']+s['end'])/2-t['start']).save(folder/(t['id']+f'-caption-{i:02}.jpg'),quality=91)
        for frac in [.08,.5,.92]:
            im=r.frame(t,(t['end']-t['start'])*frac);im.save(folder/(t['id']+f'-{frac}.jpg'),quality=91)
            if frac==.5:thumbs.append(im)
    width,height=(270,480) if kind=='short' else (480,270);cols=3 if kind=='short' else 4
    sheet=Image.new('RGB',(width*cols,height*math.ceil(len(thumbs)/cols)),NAVY)
    for i,im in enumerate(thumbs):sheet.paste(im.resize((width,height)),(i%cols*width,i//cols*height))
    sheet.save(folder/'contact-sheet.jpg',quality=94)
    for row in r.canvas.audit.values():
        x,y,x2,y2=row['rect'];assert 0<=x<x2<=r.w and 0<=y<y2<=r.h
    save(folder/'text-layout-audit.json',list(r.canvas.audit.values()))
    print('LAYOUT PASSED',kind,len(r.canvas.audit),flush=True)

def preflight(kind):
    """Only text/asset framing. Estimated timings and closed mouths are not AV QC."""
    script=json.loads((HERE/f'{kind}-dialogue-v03.json').read_text(encoding='utf-8'));visuals=SHORT_VISUAL if kind=='short' else FULL_VISUAL
    r=Renderer(kind,layout_only=True);folder=OUT/'work'/(kind+'-layout-preflight');folder.mkdir(parents=True,exist_ok=True);thumbs=[]
    for original,visual in zip(script['turns'],visuals,strict=True):
        seconds=max(3,len(original['reading'])/7.5)
        t=dict(original,visual=visual,heading=HEADINGS[visual],start=0,end=seconds,voice_start=.15,voice_seconds=seconds-.15,voice_path='layout-only-no-voice',subtitles=[])
        t['subtitles']=timed_captions(t['display'],.15,seconds-.15,930 if kind=='short' else 1580,56 if kind=='short' else 50,protected=PROTECT)
        for frac in [.08,.5,.92]:
            im=r.frame(t,seconds*frac);im.save(folder/(t['id']+f'-{frac}.jpg'),quality=91)
            if frac==.5:thumbs.append(im)
    w,h=(270,480) if kind=='short' else (480,270);cols=3 if kind=='short' else 4
    sheet=Image.new('RGB',(w*cols,h*math.ceil(len(thumbs)/cols)),NAVY)
    for i,im in enumerate(thumbs):sheet.paste(im.resize((w,h)),(i%cols*w,i//cols*h))
    sheet.save(folder/'contact-sheet.jpg',quality=94)
    save(folder/'preflight.json',dict(estimated_timing=True,audio_checked=False,text_boxes=list(r.canvas.audit.values())))
    print('STATIC PREFLIGHT PASSED',kind,len(r.canvas.audit),flush=True)

def audio_mix(plan):
    folder=dest(plan['kind']);n=round(plan['seconds']*SR);voice=np.zeros(n,np.float32);gains=[]
    for t in plan['turns']:
        samples=read_voice(ROOT/t['voice_path']);active=samples[np.abs(samples)>.018]
        rms=float(np.sqrt(np.mean(active**2))) if len(active) else .12
        gain=max(.70,min(1.6,.12/max(rms,.001)));gain=min(gain,.88/max(float(np.abs(samples).max()),.001))
        samples=samples*gain;a=round(t['voice_start']*SR);voice[a:a+len(samples)]+=samples
        gains.append(dict(id=t['id'],speaker=t['speaker'],active_rms=rms,gain=gain,original_sha256=sha(ROOT/t['voice_path'])))
    loop,loop_meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    spans=[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in plan['turns']]
    music=default_bgm_bed(raw,plan['seconds'],spans);mix=voice[:,None]+music
    effects=[]
    for t in plan['turns']:
        if t['visual'] in ['hero','sol_source','closing_hope','short_closing']:
            cue=editorial_cue('improvement',sample_rate=SR)*.20;a=round((t['start']+.06)*SR);b=min(n,a+len(cue));mix[a:b]+=cue[:b-a];effects.append(dict(kind='improvement',time=t['start']+.06))
    peak=float(np.abs(mix).max());mix*=min(1,.94/max(peak,.001))
    write_pcm(folder/'narration.wav',voice);write_pcm(folder/'mix.wav',mix);write_pcm(folder/'music-loop.wav',loop)
    save(folder/'audio-plan.json',dict(bgm=dict(DEFAULT_BGM_PROFILE),loop=loop_meta,voices=gains,level_method='Bounded active-RMS gain on derived mix only; raw voice unchanged. Perceived loudness reviewed separately.',effects=effects))
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(folder/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    meter=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0];save(folder/'mix-meter.json',meter)
    return 'loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+meter['input_i']+':measured_TP='+meter['input_tp']+':measured_LRA='+meter['input_lra']+':measured_thresh='+meter['input_thresh']+':offset='+meter['target_offset']+':linear=true'

def render(kind):
    folder=dest(kind);plan=json.loads((folder/'timeline.json').read_text(encoding='utf-8'));target=folder/f"ai-model-race-{kind}-{plan['revision']}.mp4"
    if target.exists():
        proof=json.loads((folder/'qc.json').read_text(encoding='utf-8'));assert proof['sha256']==sha(target);print('VERIFIED EXISTING RELEASE',kind,flush=True);return
    r=Renderer(kind);parts=[];code_hash=sha(Path(__file__))
    for t in plan['turns']:
        path=folder/'segments'/(t['id']+'.mp4');path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            proof=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'));assert proof['code_sha256']==code_hash and proof['sha256']==sha(path)
        else:
            proc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s',f'{r.w}x{r.h}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','4',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for i in range(t['frames']):proc.stdin.write(r.frame(t,i/FPS).tobytes())
                proc.stdin.close();error=proc.stderr.read();code=proc.wait()
                if code:raise RuntimeError(error.decode(errors='replace'))
            except BaseException:
                proc.kill();proc.wait()
                if path.exists():path.rename(path.with_suffix('.failed.mp4'))
                raise
            save(path.with_suffix('.json'),dict(sha256=sha(path),code_sha256=code_hash,frames=t['frames']))
        parts.append(path);print(kind,t['id'],'ready',flush=True)
    if kind=='full':
        end=folder/'end.mp4'
        if not end.exists():
            still=folder/'end.png';r.ending(0).save(still)
            run(['ffmpeg','-v','error','-nostdin','-n','-loop','1','-i',str(still),'-t','10','-r','24','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','4',str(end)])
        parts.append(end)
    listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+p.as_posix()+"'" for p in parts),encoding='utf-8')
    normalizer=audio_mix(plan);temp=target.with_name(target.stem+'-assembling.mp4')
    run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-i',str(folder/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af',normalizer,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(plan['seconds']),'-movflags','+faststart',str(temp)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(temp),'-f','null','-'])
    probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(temp)]).stdout);v=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert int(v['nb_frames'])==plan['frames'] and abs(float(probe['format']['duration'])-plan['seconds'])<.1
    meter=run(['ffmpeg','-hide_banner','-nostdin','-i',str(temp),'-af','loudnorm=print_format=json','-f','null','-']).stderr;loudness=json.JSONDecoder().raw_decode(meter[meter.rfind('{'):])[0]
    assert -18<float(loudness['input_i'])<-14 and float(loudness['input_tp'])<=-1,loudness
    temp.rename(target)
    save(folder/'qc.json',dict(path=target.relative_to(ROOT).as_posix(),sha256=sha(target),bytes=target.stat().st_size,seconds=plan['seconds'],frames=plan['frames'],width=r.w,height=r.h,full_decode=True,loudness=loudness,human_reviewed=False,user_approved=False,published=False))
    print('COMPLETE',kind,plan['seconds'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare-motion','plan','preflight','preview','render']);parser.add_argument('--video',choices=['short','full'],default='short');args=parser.parse_args()
    if args.action=='prepare-motion':prepare_motion()
    elif args.action=='plan':make_plan(args.video)
    elif args.action=='preflight':preflight(args.video)
    elif args.action=='preview':preview(args.video)
    else:render(args.video)
