"""One future-policy news short; diagrams never masquerade as a live usage experiment."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,shutil,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,fit,arrow,wrap,glyph,INK,TEAL,BG
from tools.studio.dialogue_avatar import SpriteAtlas,voice_gate
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
OUT=ROOT/'outputs/content-projects'/HERE.name;ASSETS=OUT/'assets';DEST=OUT/'release/v01'
SCRIPT=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));FPS=24;W=1080;H=1920
BLUE='#3878D3';GREEN='#238368';GOLD='#D29324';MUTED='#566C78'
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True);items=[];raw=OUT/'_private/captures'
    crops=[('official-heading','official-usage-original.png',(750,290,1370,379),6,'official'),('official-instant','official-usage-original.png',(1025,617,1338,640),8,'official'),('usage-navigation','current-usage-original.png',(58,635,333,673),0,'current_settings_observation'),('usage-heading','current-usage-original.png',(1075,25,1200,65),0,'current_settings_observation')]
    for name,filename,rect,words,kind in crops:
        src=raw/filename;dst=ASSETS/(name+'.png');im=Image.open(src);im.crop(rect).save(dst)
        items.append(dict(rec(dst),raw_sha256=sha(src),original_size=list(im.size),crop_xyxy=rect,quoted_words=words,kind=kind,source_url=SCRIPT['source_url'] if kind=='official' else 'https://chatgpt.com/settings/usage?tab=overview',checked_on='2026-11-02',privacy='Public excerpt only; account, balances, reset dates, history and conversation names excluded'))
    old=ROOT/'outputs/content-projects/CONTENT_20261101_tibo_28day_full/assets'
    for name in ['male-atlas.png','female-atlas.png','male-understanding.mp4','female-thinking.mp4','female-happy.mp4']:
        src=old/name;dst=ASSETS/name
        if not dst.exists():shutil.copy2(src,dst)
        assert sha(src)==sha(dst);items.append(dict(rec(dst),kind='reused_approved_duo',source=rec(src)))
        if dst.suffix=='.mp4':
            folder=OUT/'motion-cache'/dst.stem;folder.mkdir(parents=True,exist_ok=True)
            if not list(folder.glob('*.jpg')):run(['ffmpeg','-v','error','-nostdin','-i',str(dst),'-vf',f'fps={FPS},scale=400:-2','-q:v','3',str(folder/'%04d.jpg')])
    save(OUT/'asset-manifest.json',dict(items=items,official_quoted_words=14,private_originals_included=False,new_person_generation=False));print('assets prepared',flush=True)
def timeline():
    DEST.mkdir(parents=True,exist_ok=True);cursor=0;turns=[]
    for item in SCRIPT['turns']:
        path=OUT/'voice/v01'/item['id']/'voice.wav';proof=json.loads(path.with_name('verified.json').read_text(encoding='utf-8'));assert sha(path)==next(f['sha256'] for f in proof['files'] if f['path'].endswith('voice.wav'))
        seconds=len(read_voice(path))/SR;duration=math.ceil((.15+seconds+.3)*FPS)/FPS;subs=[];chunks=[]
        displayed=item.get('display',item['text'])
        if item.get('captions'):chunks=list(item['captions'])
        else:
            for sentence in displayed.replace('。','。|').replace('？','？|').split('|'):
                lines=wrap(sentence,15);chunks.extend('\n'.join(lines[k:k+2]) for k in range(0,len(lines),2))
        total=sum(len(x.replace('\n','')) for x in chunks);at=cursor+.15
        for x in chunks:
            end=at+seconds*len(x.replace('\n',''))/total;subs.append(dict(start=at,end=end,text=x));at=end
        turns.append(dict(item,start=cursor,end=cursor+duration,frames=round(duration*FPS),voice_start=cursor+.15,voice_seconds=seconds,voice_path=str(path),subtitles=subs));cursor+=duration
    total=(round(cursor*FPS)+24)/FPS;n=round(total*SR);voice=np.zeros(n,np.float32)
    for t in turns:
        a=round(t['voice_start']*SR);v=read_voice(t['voice_path']);voice[a:a+len(v)]+=v
    loop,meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n];spans=[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in turns];music=default_bgm_bed(raw,total,spans);effects=np.zeros((n,2),np.float32)
    for t in turns:
        if t['visual'] not in ['merge','instant','usage']:continue
        cue=editorial_cue('improvement',sample_rate=SR)*.3;a=round((t['start']+.08)*SR);effects[a:a+len(cue)]+=cue
    mix=voice[:,None]+music+effects;mix*=min(1,.94/max(float(np.abs(mix).max()),1e-8))
    write_pcm(DEST/'narration.wav',voice);write_pcm(DEST/'music-loop.wav',loop);write_pcm(DEST/'mix.wav',mix)
    data=dict(title=SCRIPT['title'],width=W,height=H,fps=FPS,seconds=total,frames=round(total*FPS),body_seconds=cursor,end_seconds=1,turns=turns,caption_timing='Real PCM turn boundaries; sentence timing estimated by character weight, not forced word alignment')
    save(DEST/'timeline.json',data);save(DEST/'audio-plan.json',dict(bgm=dict(DEFAULT_BGM_PROFILE),loop=meta,voices={'female':'Aoede','male':'Charon'},tts_turns=len(turns),sound_effect='soft improvement cue',new_video_generation_calls=0))
    def stamp(s):
        ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    subtitles=[s for t in turns for s in t['subtitles']];(DEST/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subtitles))+'\n',encoding='utf-8');print('seconds',total,flush=True);return data
class Renderer:
    def __init__(self):
        self.canvas=Canvas();self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']};self.gates={};self.pics={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.name};self.motions={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'motion-cache').iterdir()}
    def text(self,*args,**kwargs):self.canvas.text(*args,**kwargs)
    @lru_cache(maxsize=80)
    def face(self,s,m,o,z):return self.atlas[s].frame(m,o,z)
    @lru_cache(maxsize=100)
    def motion(self,name,index):return Image.open(self.motions[name][min(index,len(self.motions[name])-1)]).convert('RGB')
    def presenter(self,im,t,local,large=False):
        size=350 if large else 190;y=860 if large else 1150
        for s,x in [('male',65),('female',650 if large else 795)]:
            mood='curious' if s=='male' else 'neutral'
            if t['visual']=='question2':mood='worried' if s=='male' else 'serious'
            if t['visual']=='unknown':mood='pleased' if s=='male' else 'serious'
            opened=False
            if s==t['speaker']:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(t['voice_path'])['gates']
                i=math.floor((local-.15)*FPS);g=self.gates[t['id']];opened=g[i] if 0<=i<len(g) else False
            box(im,(x-5,y-5,x+size+5,y+size+5),TEAL if s==t['speaker'] else '#B8CED4')
            if s!=t['speaker'] and t['visual'] in ['question','question2','unknown']:
                name='male-understanding' if s=='male' else 'female-thinking';frame=self.motion(name,round(min(local,4.2)*FPS));crop=(0,133,400,min(frame.height,510)) if s=='male' else (0,55,400,min(frame.height,518));fit(im,frame.crop(crop),(x,y,x+size,y+size),cover=True)
            else:im.paste(self.face(s,mood,opened,size),(x,y))
    def pool(self,im,local,top=790):
        box(im,(240,top,840,top+270),'#E3EFF4',30,BLUE,5)
        # Wave is purely pictorial, with no scale, numbers, or measured usage ratio.
        points=[(245,top+265),(245,top+145)]+[(x,top+145+9*math.sin(x/50+local*2)) for x in range(245,837,10)]+[(835,top+265)]
        ImageDraw.Draw(im).polygon(points,fill='#94C5E1');self.text(im,'利用枠（共通）',(260,top+35,820,top+115),62,INK)
    def diagram(self,im,t,local):
        v=t['visual'];d=ImageDraw.Draw(im)
        if v in ['merge','question']:
            for x,name,c in [(65,'ChatGPT',TEAL),(590,'Codex',BLUE)]:box(im,(x,465,x+425,600),c);self.text(im,name,(x+12,480,x+413,580),61,'white')
            self.pool(im,local,790)
            for x,c in [(277,TEAL),(802,BLUE)]:
                arrow(im,[(x,620),(x,690),(540,760)],c,12)
                phase=(local*.65+(0 if x<500 else .5))%1;px=x+(540-x)*phase;py=645+95*phase;d.ellipse((px-11,py-11,px+11,py+11),fill=c)
            if v=='question':self.presenter(im,t,local)
        elif v=='plans':
            for i,(name,c) in enumerate([('Plus',TEAL),('Pro',BLUE),('Business','#7556AB')]):
                x=65+i*325;box(im,(x,455,x+300,575),c);self.text(im,name,(x+10,470,x+290,560),48,'white')
            box(im,(110,660,970,790),'#E2ECEA');self.text(im,'Workのエージェント機能',(130,685,950,765),46)
            arrow(im,[(540,810),(540,900)],TEAL,13)
            box(im,(110,935,970,1080),TEAL);self.text(im,'メインのChatGPTへ',(130,960,950,1050),56,'white');self.presenter(im,t,local)
        elif v=='tokens':
            for i,value in enumerate(['選ぶモデル','作業の複雑さ']):
                box(im,(130,465+i*180,950,600+i*180),TEAL if i==0 else BLUE);self.text(im,value,(150,490+i*180,930,570+i*180),60,'white')
            arrow(im,[(540,820),(540,900)],TEAL,13)
            self.text(im,'トークンで計測',(120,940,960,1040),67,INK)
            self.text(im,'固定の回数・比率ではない',(95,1085,985,1140),38,MUTED)
            for j in range(6):
                x=250+j*110;y=870+math.sin(local*3+j)*11;d.ellipse((x-9,y-9,x+9,y+9),fill=BLUE)
            self.presenter(im,t,local)
        elif v=='instant':
            box(im,(120,465,960,590),GREEN);self.text(im,'Instant chat',(140,485,940,565),66,'white');self.pool(im,local,760)
            arrow(im,[(160,615),(100,670),(100,1050),(220,1110)],GREEN,15)
            self.text(im,'この枠を消費しない',(260,1060,980,1130),55,GREEN)
            fit(im,self.pics['official-instant'],(120,1200,960,1270));self.text(im,'OpenAI公式の説明（抜粋）',(130,1280,950,1325),31,MUTED)
        elif v=='usage':
            for i,(name,symbol) in enumerate([('残量','clock'),('リセット時刻','clock')]):
                x=80+i*490;box(im,(x,475,x+440,735),'#E0EEEC' if i==0 else '#E3EDF7')
                if i==0:
                    for j in range(3):box(im,(x+110+j*77,520,x+160+j*77,600),TEAL,10)
                else:
                    d.ellipse((x+160,505,x+280,625),outline=BLUE,width=8);d.line((x+220,525,x+220,565,x+255,580),fill=BLUE,width=8)
                self.text(im,name,(x+15,650,x+425,715),48)
            self.text(im,'設定 → 使用状況',(85,790,995,875),65,INK)
            box(im,(130,915,950,1050),'white');fit(im,self.pics['usage-navigation'],(160,935,920,1030))
            self.text(im,'現在の実画面：確認先の入口',(85,1080,995,1140),37,MUTED);self.presenter(im,t,local)
        elif v=='question2':
            box(im,(100,460,980,700),'#F8EBD3');self.text(im,'まだ、断定できない',(130,510,950,650),65,INK);self.presenter(im,t,local,large=True)
        elif v=='unknown':
            for i,(title,answer,c) in enumerate([('提供時期','12月予定',TEAL),('開始日・具体枠','未記載',GOLD),('値上げ・実質削減','断定不可',MUTED)]):
                y=450+i*205;box(im,(80,y,1000,y+175),'white');self.text(im,title,(105,y+13,975,y+78),47,INK);self.text(im,answer,(105,y+93,975,y+161),57,c)
            self.presenter(im,t,local)
    def render(self,t,local,caption=True):
        im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);d.rectangle((0,0,W,14),fill=TEAL)
        self.text(im,'11/2確認  |  12月からの予定',(65,48,1010,110),37,TEAL)
        heading=t['heading'] if glyph(t['heading'],65,INK).width<=945 else '\n'.join(wrap(t['heading'],15))
        self.text(im,heading,(65,140,1010,308),65,INK)
        self.text(im,'\n'.join(wrap(t['sub'],22)),(65,320,1010,425),40,TEAL)
        self.diagram(im,t,local)
        if t['visual']=='merge':
            fit(im,self.pics['official-heading'],(90,1110,990,1250));self.text(im,'出典：OpenAI公式ヘルプ',(90,1260,990,1310),34,MUTED)
        if caption:
            sub=next((s['text'] for s in t['subtitles'] if s['start']<=t['start']+local<s['end']),None)
            if sub:
                box(im,(55,1390,1020,1660),INK,30);self.text(im,sub,(80,1410,995,1640),58,'white')
        self.text(im,'予定の解説／変更後の消費は未実演',(70,1710,1000,1780),35,MUTED)
        return im
def previews():
    plan=timeline();r=Renderer();folder=DEST/'qc-layout';folder.mkdir(exist_ok=True);thumbs=[]
    for t in plan['turns']:
        for tag,pct in [('early',.08),('middle',.5),('late',.92)]:
            im=r.render(t,(t['end']-t['start'])*pct);im.save(folder/(t['id']+'-'+tag+'.jpg'),quality=93)
            if tag=='middle':thumbs.append(im)
    contact=Image.new('RGB',(810,480*math.ceil(len(thumbs)/3)),'#D2DDE0')
    for i,im in enumerate(thumbs):contact.paste(im.resize((270,480)),(i%3*270,i//3*480))
    contact.save(DEST/'contact-sheet-layout.jpg',quality=94);save(DEST/'text-layout-preview.json',list(r.canvas.audit.values()));print('preview ready',flush=True)
def render():
    plan=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));r=Renderer();parts=[]
    for t in plan['turns']+[dict(id='end',frames=24)]:
        path=OUT/'segments/v01'/(t['id']+'.mp4');path.parent.mkdir(parents=True,exist_ok=True);parts.append(path)
        if path.exists():continue
        process=subprocess.Popen(['ffmpeg','-v','error','-y','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','6',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for i in range(t['frames']):
                if t['id']=='end':im=r.render(plan['turns'][-1],plan['turns'][-1]['end']-plan['turns'][-1]['start']-.01,caption=False)
                else:im=r.render(t,i/FPS)
                process.stdin.write(im.tobytes())
            process.stdin.close();err=process.stderr.read();code=process.wait()
            if code:raise RuntimeError(err.decode('utf-8','replace'))
        except BaseException:process.kill();process.wait();path.unlink(missing_ok=True);raise
        print(t['id'],'rendered',flush=True)
    concat=DEST/'segments.txt';concat.write_text('\n'.join("file '"+p.as_posix()+"'" for p in parts),encoding='utf-8');final=DEST/'chatgpt-codex-shared-usage-v01.mp4'
    run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(concat),'-i',str(DEST/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af','loudnorm=I=-16:TP=-1:LRA=9','-c:a','aac','-ar','48000','-b:a','192k','-t',str(plan['seconds']),'-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(final),'-f','null','-']);met=run(['ffmpeg','-hide_banner','-nostdin','-i',str(final),'-af','loudnorm=I=-16:TP=-1:LRA=9:print_format=json','-f','null','-']).stderr;data=json.JSONDecoder().raw_decode(met[met.rfind('{'):])[0]
    probe=json.loads(run(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(final)]).stdout);vs=next(s for s in probe['streams'] if s['codec_type']=='video');audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert int(vs['nb_read_frames'])==plan['frames'] and abs(float(probe['format']['duration'])-plan['seconds'])<.05
    assert vs['width']==W and vs['height']==H and vs['r_frame_rate']=='24/1' and audio['channels']==2 and audio['sample_rate']=='48000'
    assert -17<float(data['input_i'])<-15 and float(data['input_tp'])<=-1
    save(DEST/'qc.json',dict(file=rec(final),seconds=probe['format']['duration'],frames=vs['nb_read_frames'],whole_decode='passed',loudness=data,width=W,height=H,audio='AAC stereo 48kHz',future_change_demonstrated=False,human_reviewed=False,user_approved=False,published=False))
    if r.canvas.audit:save(DEST/'text-layout-render.json',list(r.canvas.audit.values()))
    print('COMPLETE',final,flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','preview','render']);args=a.parse_args();{'prepare':prepare,'preview':previews,'render':render}[args.action]()
