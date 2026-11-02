"""Opt-in four-video revision. Preserve published media, reuse verified source PCM."""
from pathlib import Path
from functools import lru_cache
import argparse,copy,hashlib,importlib.util,json,math,os,subprocess,sys,time
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.editorial_captions import display_text,timed_captions
from tools.studio.editorial_presenters import equalized_face,intent_mood
from tools.studio.explainer_canvas import Canvas,box,fit,BG,INK
from tools.studio.dialogue_avatar import voice_gate
from tools.studio.dialogue_narration import synthesize
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed
from tools.studio.closing_visuals import end_screen

def load(name,folder,file='produce.py'):
    path=ROOT/'productions/content-projects'/folder/file;spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
wine=load('wine_original','CONTENT_20261102_dots_blender_wine');tokyo=load('tokyo_original','CONTENT_20261101_dots_blender_tokyo');tibo=load('tibo_original','CONTENT_20261101_tibo_28day_full')
sys.modules['produce']=tibo;tv2=load('tibo_v02','CONTENT_20261101_tibo_28day_full','revise_v02.py');sys.modules.pop('produce',None)
CASES={
 'wine-short':dict(module=wine,kind='short',old=wine.OUT/'release/v01/short',name='dots-wine-short-v02.mp4',version='v02'),
 'wine-full':dict(module=wine,kind='full',old=wine.OUT/'release/v01/full',name='dots-wine-full-v02.mp4',version='v02'),
 'tokyo-full':dict(module=tokyo,kind='full',old=tokyo.OUT/'release/v01/full',name='dots-blender-tokyo-full-v02.mp4',version='v02'),
 'tibo-full':dict(module=tibo,kind='full',old=tibo.OUT/'release/v02',name='tibo-28day-full-v03.mp4',version='v03')}
NEW_VOICES={
 'wine-size-question':dict(speaker='male',text='瓶、小さくない？グラスと比べると気になるね。',display='瓶、小さくない？グラスと比べると気になるね。'),
 'wine-size-answer':dict(speaker='female',text='そう。グラスに対して瓶が小さく見えたので、参考寸法の比率をもとに、瓶とラベルをまとめて約一点九倍に拡大しました。',display='そう。グラスに対して瓶が小さく見えたので、参考寸法の比率をもとに、瓶とラベルをまとめて約1.9倍に拡大しました。'),
 'short-size-question-v02':dict(speaker='male',text='あれ、瓶が小さくない？',display='あれ、瓶が小さくない？'),
 'short-size-answer':dict(speaker='female',text='そう。瓶とラベルを約一点九倍に拡大。グラスとの比率を見直しました。',display='そう。瓶とラベルを約1.9倍に拡大。グラスとの比率を見直しました。')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def save(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def voices():
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    for key,t in NEW_VOICES.items():
        folder=OUT/'voice/v01'/key;cached=(folder/'verified.json').exists()
        p=synthesize(folder,t['text'],t['speaker'],profile='conversational_v3');print(key,round(p['seconds'],2),'cached' if cached else 'new',flush=True)
        if not cached:time.sleep(22)

def plan(key):
    cfg=CASES[key];dest=OUT/'release'/cfg['version']/key;dest.mkdir(parents=True,exist_ok=True)
    previous=json.loads((cfg['old']/'timeline.json').read_text(encoding='utf-8'));p=copy.deepcopy(previous);turns=p['turns'];short=cfg['kind']=='short'
    if key=='wine-short':
        q=copy.deepcopy(next(t for t in turns if t['id']=='s02'));q.update(id='s03q',visual='size_question',heading='瓶、小さくない？',sub='グラスとの比率を、同じ位置で比較',**NEW_VOICES['short-size-question-v02']);q['voice_path']=str(OUT/'voice/v01/short-size-question-v02/voice.wav');turns.insert(3,q)
    cursor=0
    for t in turns:
        new_id=({'f10':'wine-size-question','f11':'wine-size-answer'} if key=='wine-full' else {'s04':'short-size-answer'} if key=='wine-short' else {}).get(t['id'])
        if new_id:
            t.update(NEW_VOICES[new_id]);t['voice_path']=str(OUT/'voice/v01'/new_id/'voice.wav')
            if t['id']=='f10':t.update(visual='size_question',heading='瓶、小さくない？',sub='グラスとの比率を見てみよう')
            if t['id']=='f11':t['sub']='瓶とラベルを一様に約1.9倍へ'
        t['display']=display_text(t['text'],t.get('display'));t['intent']=t['visual']
        if 'wine-' in key:
            old_lead=t['voice_start']-t['start'];lead=.16;tail=.38 if short else .6
            t['voice_seconds']=len(read_voice(t['voice_path']))/SR;t['frames']=math.ceil((lead+t['voice_seconds']+tail)*24);t['start']=cursor;t['end']=cursor+t['frames']/24;t['voice_start']=cursor+lead;cursor=t['end']
        t['subtitles']=timed_captions(t['display'],t['voice_start'],t['voice_seconds'],910 if short else 1560,56 if short else 48)
    if 'wine-' in key:p.update(seconds=cursor+p['end_seconds'],body_seconds=cursor,frames=round((cursor+p['end_seconds'])*24))
    if key=='tokyo-full':p['end_seconds']=p.get('end_seconds',10)
    p.setdefault('frames',round(p['seconds']*24))
    p['revision']=cfg['version'];p['source_plan_sha256']=sha(cfg['old']/'timeline.json');p['caption_method']='BudouX phrases, protected words and measured fixed font; sentence time weighted from real turn PCM'
    save(dest/'timeline.json',p)
    def stamp(s):
        ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    subs=[s for t in turns for s in t['subtitles']];(dest/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(subs))+'\n',encoding='utf-8')
    save(dest/'script-display-and-spoken.json',[dict(id=t['id'],speaker=t['speaker'],spoken=t['text'],display=t['display'],intent=t['intent']) for t in turns])
    print(key,round(p['seconds'],3),'seconds',flush=True);return p

class FaceMixin:
    @lru_cache(maxsize=300)
    def face_tile(self,speaker,mood,opened,size):return equalized_face(self.atlas[speaker],speaker,mood,opened,size)
    def equal_presenters(self,im,t,local,large=False):
        size=310 if large else 190;short=getattr(self,'short',False);size=230 if short else size;y=1050 if short else 360 if large else 630;xvalues=(45,805) if short else (45,1920-45-size)
        for speaker,x in zip(['male','female'],xvalues):
            opened=False
            if speaker==t['speaker']:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(t['voice_path'])['gates']
                i=math.floor((t['start']+local-t['voice_start'])*24);g=self.gates[t['id']];opened=g[i] if 0<=i<len(g) else False
            mood=intent_mood(t.get('intent',t['visual']),speaker,speaker==t['speaker']);box(im,(x-4,y-4,x+size+4,y+size+4),'#8C334D' if speaker==t['speaker'] else '#BDD0D5')
            im.paste(self.face_tile(speaker,mood,opened,size),(x,y))

class WineRenderer(FaceMixin,wine.Renderer):
    def presenters(self,im,t,local,large=False):
        if t['visual'] in ['hero','final_play','motion_fix','size_fix','clearance','materials','process','size_question']:return
        self.equal_presenters(im,t,local,large)
    def main(self,im,t,local):
        v=t['visual'];duration=t['end']-t['start'];s=self.short
        if s and v in ['size_fix','size_question']:
            # Identical camera, crop and output box. No independent autoscaling or stacked images.
            after=v=='size_fix' and local>=1.6;x=960 if after else 0
            src=self.pics['size-comparison'].crop((x+250,95,x+750,590));fit(im,src,(0,245,1080,1380),cover=True)
            box(im,(55,150,1025,230),'#8C334D' if after else '#5F737F',15);self.text(im,'修正後：約1.9倍' if after else '修正前：瓶が小さめ',(75,163,1005,215),46,'white');return
        if s and v in ['hero','motion_fix','procedural']:
            self.movie(im,'v2' if v=='motion_fix' else 'v3',min(local,4.96),(0,245,1080,1315))
            note='修正版：起こしてから退避' if v=='motion_fix' else '液体は形を変える演出' if v=='procedural' else '完成した5秒のCG'
            self.text(im,note,(45,1320,1035,1400),39,'white');return
        if not s and v in ['hero','final_play','question','summary_question','procedural_question','size_question','clearance','reaction']:
            name='v2' if v=='reaction' else 'v3';at=3.1+local*.5 if v=='reaction' else 2.8+local*.4 if v=='clearance' else local
            if v=='size_question':fit(im,self.pics['v2-final'],(0,145,1920,920))
            else:self.movie(im,name,min(at,4.96),(0,145,1920,920))
            note='終盤を0.5倍速で確認' if v=='reaction' else '終盤を0.4倍速で確認' if v=='clearance' else '完成CG（提供映像）'
            self.text(im,note,(360,880,1560,925),30,'#FFFFFF')
            if v in ['question','summary_question','procedural_question'] and local<1.0:self.equal_presenters(im,t,local)
            return
        super().main(im,t,local)
    def render(self,t,local,caption=True):
        im=Image.new('RGB',(self.w,self.h),BG);s=self.short
        featured=(not s and t['visual'] in ['hero','final_play','question','summary_question','procedural_question','size_question','clearance','reaction']) or (s and t['visual'] in ['size_fix','size_question','hero','motion_fix','procedural'])
        if featured:
            im.paste(Image.new('RGB',(self.w,self.h),'#102126'));self.main(im,t,local)
            self.text(im,t['heading'],(45,30,self.w-45,125),48 if not s else 55,'white')
        else:
            clean=dict(t,subtitles=[]);im=super().render(clean,local,caption=False)
        current=next((a['text'] for a in t['subtitles'] if a['start']<=t['start']+local<a['end']),None)
        if current:
            box(im,(35,1430,1045,1675) if s else (110,930,1810,1068),INK,22)
            self.text(im,current,(65,1450,1015,1655) if s else (160,942,1760,1060),56 if s else 48,'white')
        return im

class TokyoRenderer(FaceMixin,tokyo.Renderer):
    def pip(self,im,t,local,large=False):
        if t['visual'] in ['hero','detail','result','fix','windows','build','ornament']:return
        self.equal_presenters(im,t,local,large)
    def main(self,im,t,local):
        if t['visual']=='fix':
            # Source checkpoint, then focus the right wing/end wall. No reconstructed pixels.
            name='09_side_elevations' if local<(t['end']-t['start'])*.5 else '10_brick_coordinate_fix';src=self.pics[name]
            if local<1.0:fit(im,src,(10,190,1910,920))
            else:
                crop=(620,395,920,615);fit(im,src.crop(crop),(100,195,1820,895))
            tokyo.text(im,'側面の窓とレンガを拡大（工程の静止画）',(170,865,1750,920),34,tokyo.TEAL);return
        if t['visual']=='question':
            fit(im,self.pics['hero_final'],(0,200,1920,920));return
        super().main(im,t,local)
    def render(self,t,local):
        im=super().render(dict(t,subtitles=[]),local)
        current=next((a['text'] for a in t['subtitles'] if a['start']<=t['start']+local<a['end']),None)
        if current:box(im,(110,930,1810,1068),INK);tokyo.text(im,current,(160,942,1760,1060),48,'white')
        return im

class TiboRenderer(FaceMixin,tv2.RevisedRenderer):
    def __init__(self):
        super().__init__();self.short=False
        # Original renderer calls these attributes differently.
        self.atlas={s:__import__('tools.studio.dialogue_avatar',fromlist=['SpriteAtlas']).SpriteAtlas(tibo.ASSETS/(s+'-atlas.png'),s) for s in ['male','female']}
    def presenter(self,im,t,local,large=False):
        if t['visual'] not in ['hero','question','bankq','understand','limits','check','summary','benefits']:return
        self.equal_presenters(im,t,local,large=large)
    def draw(self,t,local):
        im=super().draw(dict(t,subtitles=[]),local)
        # Keep the v02 light treatment, but rebuild only the subtitle band.
        ImageDraw.Draw(im).rectangle((0,875,1920,1068),fill=tibo.INK)
        current=next((a['text'] for a in t['subtitles'] if a['start']<=t['start']+local<a['end']),None)
        if current:
            Canvas().text(im,current,(155,901,1765,1048),48,'white');box(im,(45,930,112,998),tibo.BLUE if t['speaker']=='male' else tibo.PURPLE,13);tibo.label(im,'男' if t['speaker']=='male' else '女',(45,930,112,998),35,'white')
        return im

def renderer(key):return WineRenderer(CASES[key]['kind']) if key.startswith('wine') else TokyoRenderer('full') if key.startswith('tokyo') else TiboRenderer()
def image_at(r,t,local):return r.draw(t,local) if isinstance(r,TiboRenderer) else r.render(t,local)

def preview(key):
    p=plan(key);r=renderer(key);r.plan=p;dest=OUT/'release'/CASES[key]['version']/key/'layout';dest.mkdir(exist_ok=True);thumbs=[]
    for t in p['turns']:
        # Check every caption state, not just one convenient representative image.
        for i,c in enumerate(t['subtitles']):image_at(r,t,(c['start']+c['end'])/2-t['start']).save(dest/f"{t['id']}-sub-{i}.jpg",quality=90)
        for pct in [.08,.5,.92]:
            im=image_at(r,t,(t['end']-t['start'])*pct);im.save(dest/f"{t['id']}-{pct}.jpg",quality=90)
            if pct==.5:thumbs.append(im)
    w,h=(270,480) if CASES[key]['kind']=='short' else (480,270);sheet=Image.new('RGB',(w*3,h*((len(thumbs)+2)//3)),BG)
    for i,im in enumerate(thumbs):sheet.paste(im.resize((w,h)),(i%3*w,i//3*h))
    sheet.save(dest/'contact-sheet.jpg',quality=93);print('layout passed',key,flush=True)

def render(key):
    cfg=CASES[key];dest=OUT/'release'/cfg['version']/key;p=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));r=renderer(key);r.plan=p;parts=[]
    # Completed releases are immutable. Code changes require an explicitly new output version.
    final=dest/cfg['name']
    if final.exists() and (dest/'qc.json').exists():
        assert json.loads((dest/'qc.json').read_text(encoding='utf-8'))['sha256']==sha(final)
        print('VERIFIED EXISTING RELEASE; use a new version for changes',key,flush=True)
        return
    for t in p['turns']:
        path=dest/'segments'/(t['id']+'.mp4');path.parent.mkdir(exist_ok=True)
        if not path.exists():
            proc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s',f"{p['width']}x{p['height']}",'-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','4',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for i in range(t['frames']):proc.stdin.write(image_at(r,t,i/24).tobytes())
                proc.stdin.close();err=proc.stderr.read();code=proc.wait()
                if code:raise RuntimeError(err.decode(errors='replace'))
            except BaseException:proc.kill();proc.wait();path.unlink(missing_ok=True);raise
            save(path.with_suffix('.json'),dict(sha256=sha(path),code_sha256=sha(Path(__file__)),frames=t['frames']))
        else:
            proof=json.loads(path.with_suffix('.json').read_text());assert proof['sha256']==sha(path) and proof['code_sha256']==sha(Path(__file__))
        parts.append(path);print(key,t['id'],'ready',flush=True)
    # Ending is unchanged footage from each preceding release; wine short uses a fresh hold.
    ending=dest/'end.mp4';seconds=p['seconds']-p['turns'][-1]['end']
    if not ending.exists():
        if key=='wine-short':
            im=image_at(r,p['turns'][-1],p['turns'][-1]['end']-p['turns'][-1]['start']-.01);still=dest/'end.png';im.save(still);run(['ffmpeg','-v','error','-nostdin','-n','-loop','1','-i',str(still),'-t',str(seconds),'-r','24','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p',str(ending)])
        else:
            oldvideo=next(cfg['old'].glob('*full-v*.mp4'));start=float(json.loads((cfg['old']/'timeline.json').read_text(encoding='utf-8'))['seconds'])-seconds
            run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(start),'-i',str(oldvideo),'-t',str(seconds),'-an','-c:v','libx264','-preset','veryfast','-crf','19','-r','24','-pix_fmt','yuv420p',str(ending)])
    parts.append(ending);listing=dest/'concat.txt';listing.write_text('\n'.join("file '"+x.as_posix()+"'" for x in parts),encoding='utf-8');final=dest/cfg['name']
    if key.startswith('wine'):
        n=round(p['seconds']*SR);voice=np.zeros(n,np.float32)
        for t in p['turns']:
            v=read_voice(t['voice_path']);a=round(t['voice_start']*SR);voice[a:a+len(v)]+=v
        loop,_=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n];music=default_bgm_bed(raw,p['seconds'],[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in p['turns']]);mix=voice[:,None]+music
        for t in p['turns']:
            if t['visual'] in ['motion_fix','size_fix','summary']:
                cue=editorial_cue('improvement',sample_rate=SR)*.26;a=round((t['start']+.1)*SR);mix[a:a+len(cue)]+=cue
        mix*=min(1,.94/max(float(np.abs(mix).max()),1e-8));write_pcm(dest/'mix.wav',mix);write_pcm(dest/'narration.wav',voice)
        measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(dest/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr;meter=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0]
        normalizer='loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+meter['input_i']+':measured_TP='+meter['input_tp']+':measured_LRA='+meter['input_lra']+':measured_thresh='+meter['input_thresh']+':offset='+meter['target_offset']+':linear=true'
        args=['-i',str(dest/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af',normalizer,'-c:a','aac','-b:a','192k','-ar','48000']
    else:
        oldvideo=next(cfg['old'].glob('*full-v*.mp4'));args=['-i',str(oldvideo),'-map','0:v','-map','1:a','-c','copy']
    if not final.exists():run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(listing)]+args+['-t',str(p['seconds']),'-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(final),'-f','null','-']);probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]).stdout);v=next(s for s in probe['streams'] if s['codec_type']=='video');assert int(v['nb_frames'])==p['frames'] and abs(float(probe['format']['duration'])-p['seconds'])<.1
    meter=run(['ffmpeg','-hide_banner','-nostdin','-i',str(final),'-af','loudnorm=print_format=json','-f','null','-']).stderr;loudness=json.JSONDecoder().raw_decode(meter[meter.rfind('{'):])[0]
    assert -17<float(loudness['input_i'])<-15 and float(loudness['input_tp'])<=-1
    save(dest/'qc.json',dict(path=final.relative_to(ROOT).as_posix(),sha256=sha(final),bytes=final.stat().st_size,seconds=p['seconds'],frames=p['frames'],full_decode=True,loudness=loudness,human_reviewed=False,user_approved=False,published=False))
    print('COMPLETE',key,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['voices','preview','render']);a.add_argument('--video',choices=list(CASES),default='wine-short');args=a.parse_args()
    if args.action=='voices':voices()
    elif args.action=='preview':preview(args.video)
    else:render(args.video)
