"""Tibo retrospective: source excerpts, daily motion, private originals kept separate.

Reuses the previous production's verified typography/audio/encoding helpers.
The new button and banked-token shots are authored 2D motion, not a real reset.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,shutil,sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
spec=importlib.util.spec_from_file_location('news_helpers',HERE.parent/'CONTENT_20261031_ai_news_ultra_accounts/produce.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
PLAN=json.loads((HERE/'plan.json').read_text(encoding='utf-8'));EP=PLAN['episodes'][0]
b.OUT=OUT;b.PLAN=PLAN
FPS=24;W,H=1080,1920
BG='#F5F2EA';INK='#172F3E';TEAL='#087E82';RED='#D94848';PURPLE='#7954B4';GRAY='#526777'
text=b.text;box=b.box;fit=b.fit;font=b.font;sha=b.sha;save=b.save
STATIC={}

def prepare():
    assets=OUT/'assets';assets.mkdir(parents=True,exist_ok=True)
    old=ROOT/'outputs/content-projects/CONTENT_20261030_chatgpt_pro_usage_news'
    manifest=[]
    for name in ['male-understanding','female-happy','female-thinking']:
        folder=old/'motions/v01'/name
        proof=json.loads((folder/('public-derivative.json' if (folder/'public-derivative.json').exists() else 'verification.json')).read_text(encoding='utf-8'))
        original=proof if 'path' in proof else proof['artifact']
        source=ROOT/original['path'];target=assets/f'{name}.mp4'
        assert sha(source)==original['sha256']
        if not target.exists():shutil.copy2(source,target)
        assert sha(target)==original['sha256']
        manifest.append(dict(b.record(target),kind='reused_minimax_video',source=original))
        cache=OUT/'motion-cache'/name
        if not list(cache.glob('*.jpg')):
            cache.mkdir(parents=True,exist_ok=True)
            b.run(['ffmpeg','-v','error','-nostdin','-i',str(target),'-vf','scale=540:-2','-q:v','2',str(cache/'%04d.jpg')])
    crop_specs=[
      ('tibo-author','tibo-promise.png',(181,63,378,108),'promise',0),
      ('tibo-promise-excerpt','tibo-promise.png',(181,170,741,215),'promise',19),
      ('tibo-reset-excerpt','tibo-day2.png',(181,270,741,294),'day2',10),
      ('tibo-forecast-excerpt','tibo-day26.png',(181,170,741,215),'day26',22),
      ('official-reset-heading','reset-help.png',(107,295,538,332),'resets',7),
      ('official-banked-heading','reset-help.png',(107,914,570,947),'resets',7),
      ('usage-reset-description','usage-settings.png',(425,961,1152,1008),'own_ui',0)
    ]
    for name,original,rect,sid,words in crop_specs:
        src=OUT/'_private/captures'/original;target=assets/f'{name}.png'
        with Image.open(src) as im:crop=im.convert('RGB').crop(rect);crop.save(target)
        with Image.open(target) as im:assert np.array_equal(np.asarray(crop),np.asarray(im))
        manifest.append(dict(b.record(target),kind='source_excerpt',source_id=sid,original=b.record(src),crop_xyxy=rect,width=crop.width,height=crop.height,quoted_words=words,privacy_review='passed: no viewer profile, usage balance, engagement or replies'))
    save(OUT/'asset-manifest.json',dict(items=manifest,new_minimax_requests=0,new_image_requests=0,new_motion='authored deterministic button press and banked-token animation'))

def ease(x):
    x=max(0,min(1,x));return x*x*(3-2*x)

def reset_motion(im,t,y=670,scale=1):
    """One press, visible contact/compression, then eligible allowance recovery."""
    d=ImageDraw.Draw(im)
    p=ease(t/.48);release=ease((t-.9)/.32)
    down=p*(1-release);compression=24*min(1,max(0,(t-.42)/.12))*(1-release)
    # Base plate and dimensional cap.
    d.ellipse((260,y+260,820,y+410),fill='#D9D9D3')
    box(im,(245,y+214,835,y+355),INK,radius=45)
    d.ellipse((245,y+160,835,y+300),fill='#344958')
    d.rectangle((310,y+95+compression,770,y+228),fill='#9F2634')
    d.ellipse((310,y+160,770,y+290),fill='#9F2634')
    d.ellipse((310,y+30+compression,770,y+215+compression),fill=RED,outline='#E97874',width=6)
    text(im,'RESET',(540,y+90+compression),60,'#FFFFFF',True)
    # Enter from the right, below the title. Contact precedes recovery.
    shift=(1-ease(t/.45))*490+ease((t-.95)/.4)*490
    fy=y+50+down*24
    d.polygon([(shift+726,fy-110),(shift+1080,fy-125),(shift+1080,fy-35),(shift+700,fy-20)],fill='#F0BB94')
    d.rounded_rectangle((shift+634,fy-130,shift+753,fy-18),radius=45,fill='#F4C5A2',outline='#D69C75',width=3)
    d.rounded_rectangle((shift+605,fy-99,shift+652,fy+50),radius=23,fill='#F4C5A2',outline='#D69C75',width=3)
    d.ellipse((shift+612,fy+12,shift+644,fy+36),fill='#F8D5BE')
    if .47<t<1.1:
        for a in [0,.5,1,2.3,2.8,3.2]:
            x=540+math.cos(a)*300;yy=y+120+math.sin(a)*140
            d.line((x,yy,x+math.cos(a)*35,yy+math.sin(a)*25),fill='#FFBA55',width=9)
    # No absolute capacity, numerical scale or permanent doubling is implied.
    amount=.12+.88*ease((t-.52)/.6)
    box(im,(210,y+455,870,y+525),'#DFE6E3',radius=28)
    box(im,(218,y+463,218+max(12,644*amount),y+517),TEAL,radius=24)
    text(im,'対象の利用枠が回復',(540,y+555),49,TEAL,True)

def bank_motion(im,t,y=620,forecast=False):
    """Receive/store only. Never refill a usage gauge merely on receipt."""
    d=ImageDraw.Draw(im);p=ease(t/.9);ticket_y=y+20+p*350
    # Back of a safe/wallet, then the ticket, then front occlusion: a visible deposit.
    box(im,(240,y+265,840,y+625),'#5F408D',radius=36)
    d.ellipse((300,y+230,780,y+308),fill='#382C53')
    box(im,(355,ticket_y,725,ticket_y+235),'#FFE9AC',PURPLE,radius=23)
    text(im,'RESET',(540,ticket_y+22),55,PURPLE,True)
    text(im,'1回分',(540,ticket_y+112),58,INK,True)
    box(im,(240,y+345,840,y+625),PURPLE,radius=36)
    d.ellipse((465,y+415,615,y+565),outline='#D7C8EF',width=7)
    d.line((540,y+443,540,y+493,578,y+515),fill='#D7C8EF',width=8)
    text(im,'後で使う',(540,y+650),59,PURPLE,True)
    if forecast:
        box(im,(380,y+276,700,y+358),INK,radius=18)
        text(im,'予告',(540,y+280),51,'#FFFFFF',True)
    else:text(im,'受取だけでは枠は回復しない',(540,y+743),41,GRAY,True)

def source_panel(im,name,y,label='Tibo @thsottiaux の原投稿・抜粋'):
    box(im,(65,y,1015,y+210),'#FFFFFF',radius=22)
    text(im,label,(88,y+9),31,GRAY)
    fit(im,OUT/'assets'/f'{name}.png',(90,y+72,990,y+180))

def day_for(s,t,duration):
    days=s['days']
    if s['kind']=='final_days':
        weights=[1.3,1.1,1.4,4.5,1.8]
        value=t/duration*sum(weights);cursor=0
        for day,w in zip(days,weights):
            if value<cursor+w:return day,(value-cursor)/w
            cursor+=w
        return days[-1],1
    p=min(len(days)-1e-6,t/duration*len(days));return days[int(p)],p%1

def grid(im,current=None):
    d=ImageDraw.Draw(im)
    for v in PLAN['days']:
        n=v['day'];x=79+((n-1)%14)*67;y=1374+((n-1)//14)*63
        col=RED if v['type']=='reset' else PURPLE if v['type'] in ('bank','forecast') else TEAL
        box(im,(x,y,x+53,y+49),col if n==current else '#FFFFFF',col,radius=9)
        text(im,str(n),(x+26,y+1),29,'#FFFFFF' if n==current else col,True)
        if v['type']=='forecast':d.line((x+4,y+43,x+49,y+43),fill=col,width=2)

def improved(im,day,t):
    d=ImageDraw.Draw(im)
    if day==1:
        for i in range(5):
            x=200+i*145
            height=150+130*ease(t*1.5-i*.1)
            box(im,(x,950-height,x+96,1000),TEAL,radius=15)
            d.line((x-25,710+i*38,x+30+180*ease(t),710+i*38),fill='#A4D4D0',width=12)
        text(im,'テキスト生成の速度改善',(540,1080),50,TEAL,True)
        text(im,'作業全体が同率で速まる意味ではない',(540,1190),39,GRAY,True)
    elif day==25:
        for j,(heading,lines) in enumerate([
          ('Pro 100 / 500',['Work・Codex枠','2倍']),
          ('Pro 200',['低い枠は2倍','従来の高い枠は据置'])]):
            yy=590+j*315;box(im,(85,yy,995,yy+285),'#FFFFFF',TEAL)
            text(im,heading,(540,yy+20),60,TEAL,True)
            for k,line in enumerate(lines):text(im,line,(540,yy+111+k*75),50,INK,True)
        text(im,'Chat側のメッセージ枠は別',(540,1250),47,GRAY,True)
    elif day==22:
        box(im,(125,670,955,1040),INK);text(im,'GPT-6.1',(540,710),70,'#FFFFFF',True)
        text(im,'Terra',(540,835),126,'#88DBCC',True)
        text(im,'モデル選択肢へ復帰',(540,1140),54,TEAL,True)
    elif day in (16,19):
        for j,label in enumerate(['前の処理','キャッシュ','次の処理']):
            x=80+j*325;box(im,(x,710,x+275,1040),'#FFFFFF',TEAL)
            text(im,label,(x+137,830),43,TEAL,True)
            if j<2:b.arrow(im,(x+275,875),(x+324,875),TEAL)
        text(im,'再利用しやすく改善',(540,1160),57,TEAL,True)
    elif day in (24,26):
        b.phone(im,(325,570,755,1200),TEAL)
        if day==26:
            for j,word in enumerate(['仕事用','個人用']):
                yy=760+j*190;box(im,(235,yy,845,yy+135),TEAL if j==0 else PURPLE)
                text(im,word,(540,yy+22),61,'#FFFFFF',True)
        else:
            box(im,(220,750,860,940),TEAL);text(im,'dotsに依頼',(540,805),60,'#FFFFFF',True)
            text(im,'米国Pro向けプレビュー',(540,1250),46,GRAY,True)
    else:
        box(im,(140,650,940,1090),'#FFFFFF',TEAL)
        # A concrete document/code/cache motif, not a static title-only scene.
        labels={4:['依頼','方向を修正','続行'],5:['入力中','次の候補','依頼へ'],7:['資料','大きな文脈','回答'],9:['アプリ','容量を削減','軽く'],11:['混雑','エラーを改善','再開'],12:['前の作業','再利用','次の作業'],14:['前のメッセージ','編集','やり直し']}
        words=labels.get(day,['改善','作業','次へ'])
        for j,word in enumerate(words):
            yy=690+j*118;box(im,(200,yy,880,yy+92),TEAL if int(t*2)%3==j else '#E8F2F0')
            text(im,word,(540,yy+10),45,'#FFFFFF' if int(t*2)%3==j else INK,True)
        text(im,'作業を続けやすく',(540,1190),55,TEAL,True)

def frame(ep,index,t,duration,global_t,total,voice_seconds):
    s=ep['scenes'][index];kind=s['kind'];day=None;phase=0
    if 'days' in s:day,phase=day_for(s,t,duration)
    caps=s['captions'];capidx=min(len(caps)-1,int(max(0,t-.15)/max(.1,voice_seconds)*len(caps)))
    key=(index,day,capidx)
    if key not in STATIC:
        im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
        d.rectangle((0,0,W,18),fill=TEAL)
        text(im,'CODEX / TIBO’S 28 DAYS',(65,68),33,TEAL)
        text(im,s['headline'],(540,146),67,INK,True)
        if day:
            obj=PLAN['days'][day-1];col=RED if obj['type']=='reset' else PURPLE if obj['type']=='bank' else TEAL
            box(im,(390,345,690,445),col);text(im,f'DAY {day:02}',(540,358),57,'#FFFFFF',True)
            text(im,obj['label'],(540,479),62,INK,True)
        elif kind=='promise':
            text(im,'Codex・ChatGPTを率いる',(540,360),46,GRAY,True)
            fit(im,OUT/'assets/tibo-author.png',(210,455,870,605))
            source_panel(im,'tibo-promise-excerpt',660)
            text(im,'改善を届ける',(540,950),83,TEAL,True)
            text(im,'または',(540,1073),45,GRAY,True)
            text(im,'利用枠をリセット',(540,1170),77,RED,True)
        elif kind=='forecast':
            text(im,'Day 26投稿「次の2日間」',(540,345),49,PURPLE,True)
            source_panel(im,'tibo-forecast-excerpt',1090)
            text(im,'配布確認前 / Day 28は未来',(540,1317),42,GRAY,True)
        elif kind=='types':
            text(im,'受取 ≠ 回復 / 有効期限あり',(540,1298),45,GRAY,True)
        elif kind=='closing':
            text(im,'設定 → 使用状況',(540,1080),58,TEAL,True)
            box(im,(65,1180,1015,1350),'#FFFFFF')
            text(im,'OpenAI公式：バンクリセットの確認方法',(88,1192),31,GRAY)
            fit(im,OUT/'assets/official-banked-heading.png',(90,1247,990,1325))
        grid(im,day)
        box(im,(55,1542,1025,1777),INK)
        cap=caps[capidx]
        if len(cap)>18:
            split=cap.rfind('・',7,19)
            if split<0:split=18
            cap=cap[:split]+'\n'+cap[split:]
        text(im,cap,(540,1577),56,'#FFFFFF',True)
        text(im,'Tibo @thsottiaux / OpenAI公式 / 日別照合：Codex Resets',(65,1804),27,GRAY)
        text(im,'11/1 JST早朝確認：Day 26まで＋Day 27・28の予告',(65,1845),28,GRAY)
        STATIC[key]=im
    im=STATIC[key].copy();d=ImageDraw.Draw(im)
    if day:
        obj=PLAN['days'][day-1]
        if obj['type']=='reset':
            reset_motion(im,phase*1.8,y=620)
            if day in (18,20):
                text(im,'翌日朝までの予告' if day==18 else '当日深夜までの予告',(540,1280),44,GRAY,True)
            else:text(im,'リセットに関する発表',(540,1280),42,GRAY,True)
        elif obj['type']=='bank':bank_motion(im,phase*1.8,y=550)
        else:improved(im,day,phase*1.8)
    elif kind=='hero':
        # People bookend the summary; the button press itself leads the first seconds.
        if t<2.6:reset_motion(im,t,y=520)
        else:
            b.picture(im,'female-happy',t-2.6,(65,410,1015,1300))
            box(im,(100,1160,980,1325),INK)
            text(im,'改善と回復の28日間',(540,1195),58,'#FFFFFF',True)
    elif kind=='forecast':bank_motion(im,min(t,2.8),y=330,forecast=True)
    elif kind=='types':
        bank_at=.15+voice_seconds/len(caps)
        label='通常：対象枠をその場で回復' if t<bank_at else 'バンク：後で使う1回分'
        box(im,(70,380,1010,550),'#FFFFFF',TEAL if t<bank_at else PURPLE)
        text(im,label,(540,430),51,TEAL if t<bank_at else PURPLE,True)
        if t<bank_at:reset_motion(im,t,y=570)
        else:bank_motion(im,min(2.8,t-bank_at),y=490)
    elif kind=='closing':
        idx=min(124,max(1,round(min(t,4.95)*FPS)+1))
        src=b.load(OUT/f'motion-cache/male-understanding/{idx:04d}.jpg').crop((0,180,540,688))
        im.paste(ImageOps.fit(src,(820,690),centering=(.5,.55)),(130,360))
        if t>4.95:
            box(im,(130,360,950,1050),'#FFFFFF',TEAL)
            text(im,'実画面で確認',(540,425),58,TEAL,True)
            fit(im,OUT/'assets/usage-reset-description.png',(165,660,915,855))
            text(im,'対象の枠と期限を確認',(540,940),46,INK,True)
    # Persistent day strip remains unobscured by the motion scenes.
    grid(im,day)
    d.rectangle((65,1890,1015,1898),fill='#D4DAD8');d.rectangle((65,1890,65+950*global_t/total,1898),fill=TEAL)
    return im

def preview():
    prepare();dest=OUT/'review/visual-v01';dest.mkdir(parents=True,exist_ok=True)
    for i,s in enumerate(EP['scenes']):
        t=1 if 'days' not in s else s['seconds']*.5
        frame(EP,i,t,s['seconds'],t,90,8).save(dest/f'scene-{i:02}.png')
    for day in [2,3,25]:
        i=next(i for i,s in enumerate(EP['scenes']) if day in s.get('days',[]));s=EP['scenes'][i]
        if day==25:t=s['seconds']*(1.7+1.7+1.8+2)/12.9
        else:t=(s['days'].index(day)+.55)/len(s['days'])*s['seconds']
        frame(EP,i,t,s['seconds'],t,90,8).save(dest/f'day-{day:02}.png')
    pictures=sorted(dest.glob('*.png'));sheet=Image.new('RGB',(720,math.ceil(len(pictures)/4)*320),'#DDDDDD')
    for k,p in enumerate(pictures):sheet.paste(Image.open(p).resize((180,320)),((k%4)*180,(k//4)*320))
    sheet.save(dest/'contact-sheet.jpg')

def clips():
    prepare();dest=OUT/'motion-graphics/v02';dest.mkdir(parents=True,exist_ok=True)
    import subprocess
    for name,func in [('reset-button-press',reset_motion),('banked-reset-store',bank_motion)]:
        path=dest/(name+'.mp4')
        if path.exists():continue
        args=['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x1080','-framerate','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
        proc=subprocess.Popen(args,stdin=subprocess.PIPE)
        for n in range(72):
            im=Image.new('RGB',(1080,1920),BG);func(im,n/FPS,y=220)
            proc.stdin.write(im.crop((0,100,1080,1180)).tobytes())
        proc.stdin.close();assert proc.wait()==0
        b.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'])
        save(path.with_suffix('.json'),dict(b.record(path),type='authored_2d_motion',seconds=3,fps=24,real_account_action=False))

def voice_path(i):
    return OUT/'tibo-recap'/f"voice/{EP['scenes'][i].get('voice_version','v01')}/scene-{i:02d}/Aoede/voice.wav"

def schedule(ep):
    timeline=[];offset=0
    for i,s in enumerate(ep['scenes']):
        p=voice_path(i);proof=json.loads(p.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(p)==next(f['sha256'] for f in proof['files'] if f['path'].endswith('/voice.wav'))
        duration=len(b.read_voice(p))/b.SR
        frames=max(round(s['seconds']*FPS),math.ceil((duration+.45)*FPS))
        timeline.append(dict(index=i,start=offset/FPS,end=(offset+frames)/FPS,frames=frames,voice_start=offset/FPS+.15,voice_seconds=duration))
        offset+=frames
    return timeline

def audio(ep,timeline,dest):
    seconds=timeline[-1]['end'];voice=np.zeros(round(seconds*b.SR),dtype=np.float32);spans=[];sources=[]
    for s in timeline:
        p=voice_path(s['index']);v=b.read_voice(p);v=v/max(.01,float(np.max(np.abs(v))))*.82
        a=round(s['voice_start']*b.SR);stop=a+len(v);assert stop<=len(voice)
        voice[a:stop]+=v;spans.append((a/b.SR,stop/b.SR));sources.append(b.record(p))
    raw=b.music_bright(seconds,fade_in_seconds=0,fade_out_seconds=0)
    music=b.default_bgm_bed(raw,seconds,spans);mix=voice[:,None]*np.ones((1,2),dtype=np.float32)+music
    assert np.max(np.abs(mix))<.98
    b.write_pcm(dest/'narration.wav',voice);b.write_pcm(dest/'music.wav',music);b.write_pcm(dest/'mix.wav',mix)
    save(dest/'audio-plan.json',dict(bgm_settings=dict(b.DEFAULT_BGM_PROFILE),voice='Aoede',sources=sources,peak=float(np.max(np.abs(mix)))))

def render(version):
    b.prepare=prepare;b.frame=frame;b.schedule=schedule;b.audio=audio
    b.render(EP,version)
    dest=OUT/'tibo-recap/release'/version
    proof=json.loads((dest/'verification.json').read_text(encoding='utf-8'))
    proof.pop('own_mobile_demo',None);proof.pop('own_ultra_verified_demo',None)
    proof.update(snapshot=PLAN['as_of'],day27_28='forecast_only',real_reset_used=False,banked_receipt_refills_usage=False,reset_days=[v['day'] for v in PLAN['days'] if v['type']=='reset'],bank_days=[3],forecast_days=[27,28],new_motion='authored_2d',official_source_excerpts=True)
    save(dest/'verification.json',proof)
    save(dest/'plan-snapshot.json',PLAN)
    shutil.copy2(HERE/'produce.py',dest/'produce-snapshot.py')
    save(dest/'render-inputs.json',dict(plan=b.record(dest/'plan-snapshot.json'),renderer=b.record(dest/'produce-snapshot.py'),helper=b.record(HERE.parent/'CONTENT_20261031_ai_news_ultra_accounts/produce.py'),audio_helpers=[b.record(ROOT/'tools/studio/music_mix.py'),b.record(ROOT/'tools/studio/longform_audio.py')]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','preview','clips','render']);p.add_argument('--version',default='v01');a=p.parse_args()
    if a.command=='render':render(a.version)
    else:globals()[a.command]()
