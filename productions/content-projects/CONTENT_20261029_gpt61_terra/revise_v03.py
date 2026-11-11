"""Conversation remake using the adopted adult duo, real PCM and saved evidence."""
from pathlib import Path
import json,sys,math,subprocess,time,importlib.util,shutil,hashlib
import numpy as np
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'outputs/content-projects'/HERE.name/'v03';OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('terra_base',HERE/'production.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
from tools.studio.dialogue_narration import synthesize
from tools.studio.longform_audio import read_voice,write_pcm,music_bright,SR
from tools.studio.dialogue_avatar import DialogueDriver,mouth_patch,registered_translation
TURNS=[
('male','テラって、何が得意なの？','テラって、何が得意なの？','pair','curious'),
('female','GPT-6.1 Terraは、画像や画面を見て考え、作業につなげるAIモデルだよ。','ジーピーティー、ろくてんいち、テラは、画像や画面を見て考え、作業につなげるエーアイモデルだよ。','intro','neutral'),
('male','例えば、どんな仕事に使える？','例えば、どんな仕事に使える？','pair','curious'),
('female','商品写真の照合や、図面の読み取り、画面を操作する仕事。文章を整えるのも得意と紹介されているよ。','商品写真の照合や、図面の読み取り、画面を操作する仕事。文章を整えるのも得意と紹介されているよ。','uses','neutral'),
('female','この告知画像をAPIで見せたら、見出しが右端で切れていると指摘したの。','この告知画像をエーピーアイで見せたら、見出しが右端で切れていると指摘したの。','before','serious'),
('female','位置と文字サイズの提案も返ってきた。その数値をこちらで反映すると、全文が収まったよ。','位置と文字サイズの提案も返ってきた。その数値をこちらで反映すると、全文が収まったよ。','after','pleased'),
('male','画像を渡せば、PCも全部、自動で動くの？','画像を渡せば、パソコンも全部、自動で動くの？','pair','curious'),
('female','そこは別。実際の操作には対応ツールと権限が必要。今回試したのは画像の確認と提案までだよ。','そこは別。実際の操作には対応ツールと権限が必要。今回試したのは画像の確認と提案までだよ。','boundary','serious'),
('female','使う場所はChatGPT WorkやCodex。通常のChatには出ないので、モデル一覧と利用条件を確認してね。','使う場所はチャットジーピーティー、ワークやコーデックス。通常のチャットには出ないので、モデル一覧と利用条件を確認してね。','where','neutral'),
('male','まずは一枚、確認したい点を決めて試そう。最後は人の目でも確かめるんだね。','まずは一枚、確認したい点を決めて試そう。最後は人の目でも確かめるんだね。','closing','pleased')]
CAPTIONS=[['テラって、何が得意なの？'],['GPT-6.1 Terraは、','画像や画面を見て考え、','作業につなげるAIモデルだよ。'],['例えば、どんな仕事に使える？'],['商品写真の照合や、','図面の読み取り、','画面を操作する仕事。','文章を整えるのも得意と\n紹介されているよ。'],['この告知画像をAPIで見せたら、','見出しが右端で切れていると\n指摘したの。'],['位置と文字サイズの提案も\n返ってきた。','その数値をこちらで反映すると、','全文が収まったよ。'],['画像を渡せば、','PCも全部、自動で動くの？'],['そこは別。','実際の操作には\n対応ツールと権限が必要。','今回試したのは\n画像の確認と提案までだよ。'],['使う場所は\nChatGPT WorkやCodex。','通常のChatには出ないので、','モデル一覧と利用条件を\n確認してね。'],['まずは一枚、','確認したい点を決めて試そう。','最後は人の目でも\n確かめるんだね。']]
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
def voices():
    save(OUT/'voice-plan.json',{'max_requests':10,'model':'gemini-2.5-flash-preview-tts','voices':{'male':'Charon','female':'Aoede'},'turns':TURNS,'automatic_retry':False})
    last=time.monotonic()
    for i,(speaker,text,spoken,kind,emotion) in enumerate(TURNS):
        target=OUT/'voice'/f'{i:02d}'
        if not target.exists():time.sleep(max(0,22-(time.monotonic()-last)));last=time.monotonic()
        r=synthesize(target,spoken,speaker,'conversational_v3');print(f'Turn {i+1}/10: {r["seconds"]:.2f}s',flush=True)
def setup():
    sheet=Image.open(OUT/'standing-atlas.png').convert('RGB');h=sheet.height//3
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
    return Pair(),{s:Portrait(s) for s in ['male','female']}
def plan():
    previous=ROOT/'outputs/content-projects'/HERE.name/'v02'
    p=json.loads((previous/'timing.json').read_text(encoding='utf-8'))
    shutil.copyfile(previous/'mix.wav',OUT/'mix.wav');save(OUT/'timing.json',p)
    return p
def unused_original_plan():
    turns=[];cursor=3
    for i,(speaker,text,spoken,kind,emotion) in enumerate(TURNS):
        path=OUT/'voice'/f'{i:02d}'/'voice.wav';sec=len(read_voice(path))/SR;duration=math.ceil((sec+.6)*24)/24
        turns.append(dict(speaker=speaker,text=text,spoken=spoken,captions=CAPTIONS[i],kind=kind,emotion=emotion,voice_path=str(path),start=cursor+.12,end=cursor+.12+sec,scene_start=cursor,scene_end=cursor+duration));cursor+=duration
    save(OUT/'timing.json',dict(seconds=cursor,frames=round(cursor*24),turns=turns))
    mix=np.zeros((round(cursor*SR),2),np.float32)
    for t in turns:
        v=read_voice(t['voice_path']);a=round(t['start']*SR);mix[a:a+len(v)]+=v[:,None]*.90
    mix+=music_bright(cursor)*.15
    peak=float(abs(mix).max());mix*=min(1,.94/max(peak,.001));write_pcm(OUT/'mix.wav',mix)
    return dict(seconds=cursor,frames=round(cursor*24),turns=turns)
LAYOUT={}
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
    lines=copy.split('\n');f=base.font(size);bounds=[ink_bounds(line,size,d) for line in lines]
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

def render():
    p=plan();pair,sprites=setup();driver=DialogueDriver(p['turns']);save(OUT/'mouth-gates.json',driver.gates)
    review=OUT/'review';review.mkdir(exist_ok=True)
    # Reuse the original MiniMax movement from the adopted video's opening, no loops.
    clip=OUT/'standing-atlas.png'
    headings={'pair':'Terraで、何が変わる？','intro':'画像と画面を、仕事につなぐ','uses':'見る仕事から、操作・文章まで','before':'実際に、画像を見せてみた','after':'提案を反映 → 全文が収まった','boundary':'画像の確認と、PC操作は別','where':'Work・Codexで選ぶ','closing':'身近な一枚から、試そう'}
    def frame(sec):
        turn=next((t for t in p['turns'] if t['scene_start']<=sec<t['scene_end']),None)
        kind=turn['kind'] if turn else 'pair';im=Image.new('RGB',(1080,1920),'#f6f7ef');d=ImageDraw.Draw(im)
        center(d,(65,85,1015,145),'GPT-6.1 TERRA  /  BENRIWORKS',30)
        center(d,(65,190,1015,395),'画像がわかると、\n仕事はどう変わる？',68,gap=24)
        d.rounded_rectangle((65,455,1015,532),24,fill='#d3f49b');center(d,(65,455,1015,532),headings[kind],34)
        states={s:driver.state(sec,s) for s in ['male','female']}
        opened=next((s for s in states if states[s]['opened']),None)
        if sec<3:
            pic=pair.frame(None).resize((1000,840));im.paste(pic,(40,570))
        elif kind in ['pair','closing']:
            pic=pair.frame(opened).resize((1000,840));im.paste(pic,(40,570))
        elif kind in ['before','after']:
            name='banner-before.png' if kind=='before' else 'banner-after.png';base.paste(im,name,(60,600,1020,1200));d=ImageDraw.Draw(im)
            if kind=='before':
                d.rounded_rectangle((550,728,1015,850),12,outline='#d46238',width=7);center(d,(65,1240,1015,1340),'Terra：右端で切れていると指摘',39)
            else:center(d,(65,1240,1015,1340),'x=780・60pxを、制作側で反映',39)
            center(d,(65,1360,1015,1435),'10/29のAPI実験・架空の画像1枚',29)
        else:
            if kind=='intro':
                for j,k in enumerate(['image','brain','cursor']):base.icon(d,95+j*340,680,k);center(d,(65+j*340,845,295+j*340,930),['画像','判断','操作へ'][j],44)
                center(d,(65,960,1015,1050),'速く効率よく、という公式の位置づけ',36)
            elif kind=='uses':
                for j,(title,detail) in enumerate([('写真の照合','商品写真 ↔ カタログ'),('図面・画面の理解','位置や内容を読み取る'),('操作・文章作成','対応ツールで次の作業へ')]):
                    base.icon(d,65,610+j*155,['image','brain','cursor'][j]);center(d,(275,610+j*155,1015,675+j*155),title,44);center(d,(275,680+j*155,1015,735+j*155),detail,31)
            elif kind=='boundary':
                center(d,(65,620,1015,735),'今回：画像 → 指摘・提案',48);center(d,(65,780,1015,895),'PC操作：対応ツール＋権限',48);center(d,(65,960,1015,1045),'操作の成功を検証した動画ではない',34)
            elif kind=='where':
                center(d,(65,620,1015,735),'ChatGPT Work / Codex',57);center(d,(65,765,1015,865),'モデル一覧 → Advanced → Terra',42);center(d,(65,905,1015,975),'Plus / Pro / Business / Enterprise / Edu',30);center(d,(65,985,1015,1060),'プラン・管理者設定・ツール条件を確認',33)
            for s,x in [('male',65),('female',755)]:
                st=states[s];emotion=st['emotion'] or ('curious' if s=='male' else 'neutral');im.paste(sprites[s].frame(emotion,st['opened'],260),(x,1160))
        d=ImageDraw.Draw(im);d.rounded_rectangle((45,1500,1035,1735),30,fill='#16382c')
        if turn:
            # Phrases are explicit subtitle units, timed against actual PCM length.
            parts=turn['captions'];weights=[len(x) for x in parts];at=0;current=parts[-1]
            for part,w in zip(parts,weights):
                at+=w/sum(weights)*(turn['end']-turn['start'])
                if sec-turn['start']<at:current=part;break
            lines=current.split('\n')
            center(d,(45,1500,1035,1735),current,49,fill='white',gap=22)
        else:center(d,(45,1500,1035,1735),'GPT-6.1 Terraを、二人で確認。',46,fill='white')
        center(d,(65,1780,1015,1825),'公式情報確認：2026.10.31',26);center(d,(65,1830,1015,1880),'出典：OpenAI公式資料 ／ 架空素材でのAPI確認',24)
        return im
    video=OUT/'terra-explained-v03.mp4'
    if video.exists():raise RuntimeError('Never overwrite a rendered revision')
    proc=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x1920','-framerate','24','-i','pipe:0','-i',str(OUT/'mix.wav'),'-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-t',str(p['seconds']),str(video)],stdin=subprocess.PIPE)
    for f in range(p['frames']):
        proc.stdin.write(frame(f/24).tobytes())
        if f%240==0:print('Rendered',f,'/',p['frames'],flush=True)
    proc.stdin.close();assert proc.wait()==0
    for i,t in enumerate(p['turns']):frame((t['scene_start']+t['scene_end'])/2).save(review/f'scene-{i:02d}.png')
    save(OUT/'render.json',{'video':rec(video),'seconds':p['seconds'],'speaker_animation':'existing atlas with actual PCM envelope; not phoneme lip sync','intro':rec(clip),'new_minimax_calls':0,'new_tts_calls':0,'layout_metrics':LAYOUT,'visual_method':'standing image atlas and original PCM mouth gate; original bowed intro clip removed','user_approved':False,'human_listening':'pending'})
if __name__=='__main__':{'voices':voices,'render':render}[sys.argv[1]]()
