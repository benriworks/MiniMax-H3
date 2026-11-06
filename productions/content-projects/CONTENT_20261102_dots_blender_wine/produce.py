"""Two character-led explainers, preserving supplied v1/v2/v3 wine CGI and evidence."""
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
from tools.studio.closing_visuals import end_screen,END_SCREEN_LAYOUT
OUT=ROOT/'outputs/content-projects'/HERE.name;SOURCE=OUT/'_private/source';EXTRACT=OUT/'_private/extracted';ASSETS=OUT/'assets';FPS=24
SCRIPT=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'));BLUE='#3878D3';WINE='#8C334D';GOLD='#D59F3C';MUTED='#5F737F'
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True);items=[]
    copies=[('v3-final',SOURCE/'final/wine_750ml_upright_v3.png'),('v2-final',SOURCE/'history/wine_bottle_upright_v2.png'),('v1-hero',SOURCE/'history/wine_hero_still_960x540.png'),('size-comparison',SOURCE/'final/wine_bottle_size_v2_v3_comparison.png')]
    for name,src in copies:
        dst=ASSETS/(name+'.png');shutil.copy2(src,dst);items.append(dict(rec(dst),kind='provided_CG',source=rec(src),original_size=list(Image.open(src).size)))
    captures=EXTRACT/'wine_blender_project_and_process/captures'
    for src in sorted(captures.glob('*.png')):
        if src.stem.startswith('00_'):continue
        im=Image.open(src).convert('RGB');dst=ASSETS/(src.stem+'.png');crop=(0,0,im.width,min(im.height,925));im.crop(crop).save(dst)
        items.append(dict(rec(dst),kind='provided_checkpoint',source=rec(src),crop_xyxy=crop,original_size=list(im.size),privacy='Blender UI only; preparation console excluded'))
    official=OUT/'_private/captures/official-computers-original.png';dst=ASSETS/'official-dots-heading.png';crop=(820,145,1390,185);Image.open(official).crop(crop).save(dst);items.append(dict(rec(dst),kind='official_excerpt',raw_sha256=sha(official),crop_xyxy=crop,quoted_words=7,source_url='https://learn.chatgpt.com/docs/dots/computers-and-apps',checked_on='2026-11-02'))
    clips={'v1':SOURCE/'history/wine_pour_5s_960x540.mp4','v2':SOURCE/'history/wine_pour_upright_v2_5s.mp4','v3':SOURCE/'final/wine_pour_750ml_v3_5s.mp4'}
    old=ROOT/'outputs/content-projects/CONTENT_20261101_tibo_28day_full/assets'
    for name in ['male-atlas.png','female-atlas.png','male-understanding.mp4','female-thinking.mp4','female-happy.mp4']:
        src=old/name;dst=ASSETS/name
        if not dst.exists():shutil.copy2(src,dst)
        assert sha(src)==sha(dst);items.append(dict(rec(dst),kind='reused_approved_duo',source=rec(src)))
        if dst.suffix=='.mp4':clips[dst.stem]=dst
    for name,src in clips.items():
        cache=OUT/'cache'/name;cache.mkdir(parents=True,exist_ok=True)
        if not list(cache.glob('*.jpg')):
            vf='fps=24' if name in ['v1','v2','v3'] else 'fps=24,scale=400:-2'
            run(['ffmpeg','-v','error','-nostdin','-i',str(src),'-vf',vf,'-q:v','2',str(cache/'%04d.jpg')])
        items.append(dict(kind='provided_CG_motion' if name in ['v1','v2','v3'] else 'existing_character_motion',name=name,source=rec(src),frames=len(list(cache.glob('*.jpg')))))
    save(OUT/'asset-manifest.json',dict(items=items,source_unchanged=True,new_character_generation=False,official_quoted_words=7,source_native_video=[960,540],process_capture_native=[1366,1024],liquid='procedural animation, not physical fluid simulation'))
    print('assets prepared',flush=True)
def timeline(kind):
    dest=OUT/'release/v01'/kind;dest.mkdir(parents=True,exist_ok=True);turns=[];cursor=0
    for key in SCRIPT[kind+'_ids']:
        t=next(x for x in SCRIPT['turns'] if x['id']==key);path=OUT/'voice/v01'/key/'voice.wav';proof=json.loads(path.with_name('verified.json').read_text(encoding='utf-8'));assert sha(path)==next(f['sha256'] for f in proof['files'] if f['path'].endswith('voice.wav'))
        samples=read_voice(path);seconds=len(samples)/SR;lead=.16;tail=.38 if kind=='short' else .6;duration=math.ceil((lead+seconds+tail)*FPS)/FPS;chunks=[]
        for sentence in t.get('display',t['text']).replace('。','。|').replace('？','？|').split('|'):
            lines=wrap(sentence,15 if kind=='short' else 27);chunks.extend('\n'.join(lines[i:i+2]) for i in range(0,len(lines),2))
        total=sum(len(x.replace('\n','')) for x in chunks);at=cursor+lead;subtitles=[]
        for caption in chunks:
            end=at+seconds*len(caption.replace('\n',''))/total;subtitles.append(dict(start=at,end=end,text=caption));at=end
        turns.append(dict(t,start=cursor,end=cursor+duration,frames=round(duration*FPS),voice_start=cursor+lead,voice_seconds=seconds,voice_path=str(path),subtitles=subtitles));cursor+=duration
    ending=1 if kind=='short' else 10;total=cursor+ending;n=round(total*SR);voice=np.zeros(n,np.float32)
    for t in turns:
        a=round(t['voice_start']*SR);v=read_voice(t['voice_path']);voice[a:a+len(v)]+=v
    loop,meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n];music=default_bgm_bed(raw,total,[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in turns]);effects=np.zeros((n,2),np.float32)
    for t in turns:
        if t['visual'] not in ['roadmap','motion_fix','size_fix','summary']:continue
        cue=editorial_cue('improvement',sample_rate=SR)*.26;a=round((t['start']+.1)*SR);effects[a:a+len(cue)]+=cue
    mix=voice[:,None]+music+effects;mix*=min(1,.94/max(float(np.abs(mix).max()),1e-8));write_pcm(dest/'narration.wav',voice);write_pcm(dest/'mix.wav',mix);write_pcm(dest/'music-loop.wav',loop)
    plan=dict(kind=kind,title=SCRIPT[kind+'_title'],width=1080 if kind=='short' else 1920,height=1920 if kind=='short' else 1080,fps=FPS,seconds=total,body_seconds=cursor,end_seconds=ending,frames=round(total*FPS),turns=turns)
    save(dest/'timeline.json',plan);save(dest/'audio-plan.json',dict(bgm=dict(DEFAULT_BGM_PROFILE),loop=meta,voices={'female':'Aoede','male':'Charon'},tts_turns=len(turns),source_CG_audio='none',cue='quiet improvement only',caption_timing='Real turn PCM, estimated sentence timings; not forced word alignment'))
    def stamp(s):
        ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{sec:02},{ms:03}'
    subtitles=[s for t in turns for s in t['subtitles']];(dest/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subtitles))+'\n',encoding='utf-8');print(kind,round(total,3),'seconds',flush=True);return plan

class Renderer:
    def __init__(self,kind):
        self.short=kind=='short';self.w,self.h=(1080,1920) if self.short else (1920,1080);self.canvas=Canvas();self.gates={};self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']};self.pics={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.name};self.clips={p.name:sorted(p.glob('*.jpg')) for p in (OUT/'cache').iterdir() if p.is_dir()}
    def text(self,*a,**kw):return self.canvas.text(*a,**kw)
    @lru_cache(maxsize=180)
    def frame(self,name,i):return Image.open(self.clips[name][min(len(self.clips[name])-1,max(0,i))]).convert('RGB')
    @lru_cache(maxsize=80)
    def face(self,s,m,o,z):return self.atlas[s].frame(m,o,z)
    def movie(self,im,name,seconds,rect):
        src=self.frame(name,round(seconds*FPS))
        if self.short and name in ['v1','v2','v3']:src=src.crop((220,0,800,540))
        fit(im,src,rect)
    def presenters(self,im,t,local,large=False):
        z=300 if self.short and large else 190 if self.short else 410 if large else 190;y=960 if self.short and large else 1150 if self.short else 410 if large else 680
        for s,x in [('male',70 if self.short else 60),('female',700 if self.short and large else 800 if self.short else 1450 if large else 1670)]:
            mood='curious' if s=='male' else 'neutral'
            if t['visual'] in ['summary','summary_question','reaction']:mood='pleased'
            if t['visual'] in ['procedural','procedural_question','clearance']:mood='serious'
            opened=False
            if s==t['speaker']:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(t['voice_path'])['gates']
                i=math.floor((local-.16)*FPS);g=self.gates[t['id']];opened=g[i] if 0<=i<len(g) else False
            box(im,(x-5,y-5,x+z+5,y+z+5),WINE if s==t['speaker'] else '#BDD0D5')
            if s!=t['speaker'] and t['visual'] in ['question','reaction','summary','summary_question','procedural_question']:
                name='male-understanding' if s=='male' else 'female-thinking';src=self.frame(name,round(min(local,4.5)*FPS));crop=(0,133,400,min(src.height,510)) if s=='male' else (0,55,400,min(src.height,518));fit(im,src.crop(crop),(x,y,x+z,y+z),cover=True)
            else:im.paste(self.face(s,mood,opened,z),(x,y))
    def checkpoints(self,im,local,duration,rect,all_steps=True):
        names=['01_table','02_glass','03_wine_geometry','04_motion_refined','05_final_geometry'] if all_steps else ['02_glass','05_final_geometry']
        index=min(len(names)-1,int(local/max(duration,.1)*len(names)));src=self.pics[names[index]]
        if local>1.7:src=src.crop((170,225,1000,720))
        fit(im,src,rect)
    def compare_size(self,im):
        src=self.pics['size-comparison']
        if not self.short:fit(im,src,(80,240,1840,850));return
        for i,(x,label) in enumerate([(0,'修正前 v2'),(960,'修正後 v3')]):
            tile=src.crop((x+280,145,x+740,590));rect=(70,425+i*470,1010,835+i*470);fit(im,tile,rect)
            box(im,(90,350+i*470,650,415+i*470),MUTED if i==0 else WINE,12);self.text(im,label,(105,359+i*470,635,407+i*470),39,'white')
    def main(self,im,t,local):
        s=self.short;v=t['visual'];duration=t['end']-t['start'];rect=(65,330,1015,1120) if s else (85,220,1835,870)
        if v in ['hero','final_play']:
            self.movie(im,'v3',min(local,4.96),rect)
            self.text(im,'完成CG（提供映像）',(95,1165,985,1220) if s else (390,870,1530,918),34,WINE)
        elif v in ['question','summary_question','procedural_question']:
            fit(im,self.pics['v3-final'],(140,330,940,860) if s else (500,235,1420,745))
            self.presenters(im,t,local,large=True)
        elif v=='roadmap':
            for i,(a,b,c) in enumerate([('初版','まず作る',MUTED),('v2','注ぎ終わり',TEAL),('v3','瓶の大きさ',WINE)]):
                x=270+i*490;box(im,(x,300,x+400,560),c);self.text(im,a,(x+15,325,x+385,400),64,'white');self.text(im,b,(x+15,445,x+385,520),43,'white')
                if i<2:arrow(im,[(x+415,430),(x+470,430)],TEAL,12)
            self.text(im,'一度の出力で終わらず、完成を見て改善',(350,640,1570,735),48);self.presenters(im,t,local)
        elif v=='cloud':
            box(im,(390,255,1530,420),TEAL);self.text(im,'dotsのクラウドPC',(410,280,1510,355),61,'white');self.text(im,'Blenderを操作する',(410,365,1510,410),39,'white')
            arrow(im,[(960,445),(960,510)],TEAL,12);self.text(im,'Pythonで、形と動きを組み立てる',(380,535,1540,615),49)
            fit(im,self.pics['official-dots-heading'],(440,650,1480,730));self.text(im,'出典：OpenAI Computers and apps',(430,760,1490,815),31,MUTED);self.presenters(im,t,local)
        elif v=='process':
            self.checkpoints(im,local,duration,rect);self.text(im,'実制作の工程記録（静止画）',(300,875,1620,920),33,TEAL)
        elif v=='materials':
            if local<duration*.45:
                fit(im,self.pics['02_glass'].crop((170,225,1000,720)),(120,235,1800,825));label='制作中の表示'
            else:fit(im,self.pics['v1-hero'],(120,235,1800,825));label='完成材質のCG'
            self.text(im,label,(430,845,1490,915),39,WINE)
        elif v=='motion_fix':
            if s:
                # Show full v2 motion; the captions state its relation to the preserved first version.
                self.movie(im,'v2',min(local,4.96),rect);self.text(im,'修正版 v2：起こしてから退避',(75,1175,1005,1240),38,WINE)
            else:
                for name,x,label in [('v1',70,'初版'),('v2',1020,'修正版 v2')]:
                    box(im,(x,240,x+830,315),MUTED if name=='v1' else WINE,12);self.text(im,label,(x+15,252,x+815,305),43,'white');self.movie(im,name,min(local,4.96),(x,335,x+830,802))
                self.text(im,'同時刻の映像で、注ぎ終わりを比較',(350,825,1570,905),42)
        elif v=='reaction':
            self.movie(im,'v2',min(3.1+local*.5,4.96),(350,215,1570,820));self.text(im,'終盤を0.5倍速で再生：直立を保って退避',(300,840,1620,905),36,TEAL);self.presenters(im,t,local)
        elif v=='size_fix':self.compare_size(im)
        elif v=='clearance':
            self.movie(im,'v3',min(2.8+local*.4,4.96),(370,210,1550,850));self.presenters(im,t,local)
            self.text(im,'高さと画角を調整／終盤を0.4倍速で確認',(280,850,1640,912),34,TEAL)
        elif v=='procedural':
            if s:
                self.movie(im,'v3',min(local,4.96),rect);self.text(im,'流体シミュレーション\nではない',(280,1160,790,1310),39,WINE)
            else:
                for i,(a,b) in enumerate([('流れ','曲線と形状'),('液面','高さを変える'),('最後の滴','タイミングを制御')]):
                    x=180+i*540;box(im,(x,260,x+480,485),'#EADFE1');self.text(im,a,(x+15,285,x+465,370),60,WINE);self.text(im,b,(x+15,410,x+465,470),35)
                self.movie(im,'v3',min(local*.6,4.96),(600,520,1320,925));self.presenters(im,t,local)
        elif v=='summary':
            for i,(a,c) in enumerate([('任せる',TEAL),('見る',BLUE),('直す',WINE),('残す',GOLD)]):
                x=340+i*320;box(im,(x,310,x+270,495),c);self.text(im,a,(x+10,350,x+260,455),60,'white')
                if i<3:arrow(im,[(x+280,405),(x+310,405)],c,10)
            self.text(im,'モデル・素材・修正の履歴を、次の制作へ',(330,590,1590,685),45);self.presenters(im,t,local,large=False)
    def render(self,t,local,caption=True):
        im=Image.new('RGB',(self.w,self.h),BG);ImageDraw.Draw(im).rectangle((0,0,self.w,14),fill=WINE);s=self.short
        hrect=(65,65,1015,240) if s else (60,35,1860,120);size=64 if s else 60;maxwidth=hrect[2]-hrect[0];heading=t['heading'] if glyph(t['heading'],size,INK).width<=maxwidth else '\n'.join(wrap(t['heading'],14 if s else 29));self.text(im,heading,hrect,size)
        sub=t['sub'] if not s or glyph(t['sub'],39,TEAL).width<=950 else '\n'.join(wrap(t['sub'],22));self.text(im,sub,(65,245,1015,345) if s else (80,140,1840,198),39,TEAL)
        self.main(im,t,local)
        if s and t['visual'] in ['hero','procedural']:self.presenters(im,t,local)
        if caption:
            current=next((x['text'] for x in t['subtitles'] if x['start']<=t['start']+local<x['end']),None)
            if current:box(im,(55,1390,1020,1660) if s else (270,924,1650,1068),INK,25);self.text(im,current,(80,1410,995,1640) if s else (300,935,1620,1065),58 if s else 47,'white')
        if s:self.text(im,'dots × Blender',(70,1730,1000,1795),35,WINE)
        return im
def preview(kind):
    plan=timeline(kind);dest=OUT/'release/v01'/kind;r=Renderer(kind);folder=dest/'qc-layout';folder.mkdir(exist_ok=True);thumbs=[]
    for t in plan['turns']:
        for tag,pct in [('early',.1),('middle',.5),('late',.9)]:
            im=r.render(t,(t['end']-t['start'])*pct);im.save(folder/(t['id']+'-'+tag+'.jpg'),quality=93)
            if tag=='middle':thumbs.append(im)
    tw,th=(270,480) if kind=='short' else (480,270);sheet=Image.new('RGB',(tw*3,th*((len(thumbs)+2)//3)),'#D8DFE2')
    for i,im in enumerate(thumbs):sheet.paste(im.resize((tw,th)),(i%3*tw,i//3*th))
    sheet.save(dest/'contact-sheet-layout.jpg',quality=93);save(dest/'text-layout-preview.json',list(r.canvas.audit.values()));print('preview',kind,flush=True)
def render(kind):
    dest=OUT/'release/v01'/kind;plan=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));r=Renderer(kind);parts=[]
    for t in plan['turns']+[dict(id='end',frames=round(plan['end_seconds']*FPS))]:
        path=OUT/'segments/v01'/kind/(t['id']+'.mp4');path.parent.mkdir(parents=True,exist_ok=True);parts.append(path)
        if path.exists():continue
        process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{r.w}x{r.h}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','6',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for i in range(t['frames']):
                if t['id']=='end':im=end_screen(i/FPS,label=lambda im,s,rect,z,c:r.text(im,s,rect,z,c)) if kind=='full' else r.render(plan['turns'][-1],plan['turns'][-1]['end']-plan['turns'][-1]['start']-.01,caption=False)
                else:im=r.render(t,i/FPS)
                process.stdin.write(im.tobytes())
            process.stdin.close();err=process.stderr.read();code=process.wait()
            if code:raise RuntimeError(err.decode('utf-8','replace'))
        except BaseException:process.kill();process.wait();path.unlink(missing_ok=True);raise
        print(kind,t['id'],'rendered',flush=True)
    concat=dest/'segments.txt';concat.write_text('\n'.join("file '"+p.as_posix()+"'" for p in parts),encoding='utf-8');final=dest/f'dots-wine-{kind}-v01.mp4'
    first=run(['ffmpeg','-hide_banner','-nostdin','-i',str(dest/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    measured=json.JSONDecoder().raw_decode(first[first.rfind('{'):])[0]
    normalizer='loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+measured['input_i']+':measured_TP='+measured['input_tp']+':measured_LRA='+measured['input_lra']+':measured_thresh='+measured['input_thresh']+':offset='+measured['target_offset']+':linear=true'
    save(dest/'normalization.json',dict(method='two pass loudnorm; AAC output remeasured',measured=measured,target_lufs=-16,target_true_peak=-1.5))
    run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(concat),'-i',str(dest/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af',normalizer,'-c:a','aac','-ar','48000','-b:a','192k','-t',str(plan['seconds']),'-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(final),'-f','null','-']);meter=run(['ffmpeg','-hide_banner','-nostdin','-i',str(final),'-af','loudnorm=I=-16:TP=-1:LRA=9:print_format=json','-f','null','-']).stderr;loudness=json.JSONDecoder().raw_decode(meter[meter.rfind('{'):])[0]
    probe=json.loads(run(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(final)]).stdout);video=next(x for x in probe['streams'] if x['codec_type']=='video');audio=next(x for x in probe['streams'] if x['codec_type']=='audio')
    assert int(video['nb_read_frames'])==plan['frames'] and abs(float(probe['format']['duration'])-plan['seconds'])<.05
    assert (video['width'],video['height'])==(r.w,r.h) and video['r_frame_rate']=='24/1' and audio['sample_rate']=='48000' and audio['channels']==2
    assert -17<float(loudness['input_i'])<-15 and float(loudness['input_tp'])<=-1
    save(dest/'qc.json',dict(file=rec(final),seconds=probe['format']['duration'],frames=video['nb_read_frames'],width=r.w,height=r.h,whole_decode='passed',loudness=loudness,audio='AAC stereo 48kHz',source_native_video=[960,540],end_screen=END_SCREEN_LAYOUT if kind=='full' else None,human_reviewed=False,user_approved=False,published=False))
    if r.canvas.audit:save(dest/'text-layout-render.json',list(r.canvas.audit.values()))
    print('COMPLETE',kind,flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','preview','render']);a.add_argument('--kind',choices=['short','full'],default='short');args=a.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='preview':preview(args.kind)
    else:render(args.kind)
