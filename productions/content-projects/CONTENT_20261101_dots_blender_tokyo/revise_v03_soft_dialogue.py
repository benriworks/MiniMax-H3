"""Tokyo full v03: gentle reciprocal dialogue, preserving the latest visual policy."""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,json,math,os,subprocess,sys,time
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('editorial_v02',HERE.parent/'CONTENT_20261103_editorial_revision/revise.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
from tools.studio.editorial_captions import speech_text,timed_captions
from tools.studio.dialogue_narration import synthesize
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.audio_motifs import sunny_loop,editorial_cue
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
OUT=e.tokyo.OUT;DEST=OUT/'release/v03/full';OLD=e.OUT/'release/v02/tokyo-full';SCRIPT=json.loads((HERE/'script-v03-soft-dialogue.json').read_text(encoding='utf-8'));FPS=24

def terms(s):return s.replace('立体','3D').replace('模型','モデル')
def spoken(s):return speech_text(s).replace('3D','スリーディー').replace('PC','パソコン').replace('CG','シージー')
original_text=e.tokyo.text
def display_labels(im,value,*a,**kw):return original_text(im,terms(value),*a,**kw)
e.tokyo.text=display_labels

def voices():
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    for turn in SCRIPT['turns']:
        target=OUT/'voice/v03'/turn['id'];cached=(target/'verified.json').exists();proof=synthesize(target,spoken(turn['display']),'female',profile=SCRIPT['voice_profile'])
        print(turn['id'],round(proof['seconds'],2),'cached' if cached else 'new',flush=True)
        if not cached:time.sleep(22)

def timeline():
    DEST.mkdir(parents=True,exist_ok=True);p=copy.deepcopy(json.loads((OLD/'timeline.json').read_text(encoding='utf-8')));overrides={x['id']:x for x in SCRIPT['turns']};cursor=0
    for t in p['turns']:
        t['heading']=terms(t['heading']);t['sub']=terms(t['sub'])
        if t['id'] in overrides:
            t['display']=overrides[t['id']]['display'];t['text']=spoken(t['display']);t['voice_path']=str(OUT/'voice/v03'/t['id']/'voice.wav')
            proof=json.loads(Path(t['voice_path']).with_name('verified.json').read_text(encoding='utf-8'));assert e.sha(Path(t['voice_path']))==next(f['sha256'] for f in proof['files'] if f['path'].endswith('voice.wav'))
        else:t['display']=terms(t['display'])
        t['voice_seconds']=len(read_voice(t['voice_path']))/SR;lead=.18;tail=.65;t['frames']=math.ceil((lead+t['voice_seconds']+tail)*FPS);t['start']=cursor;t['end']=cursor+t['frames']/FPS;t['voice_start']=cursor+lead;cursor=t['end']
        t['subtitles']=timed_captions(t['display'],t['voice_start'],t['voice_seconds'],1560,48)
        assert '模型' not in t['display'] and '立体' not in t['display']
    p.update(title=SCRIPT['title'],body_seconds=cursor,end_seconds=10,seconds=cursor+10,frames=round((cursor+10)*FPS),revision='v03',source_plan_sha256=e.sha(OLD/'timeline.json'))
    e.save(DEST/'timeline.json',p);e.save(DEST/'script-display-and-spoken.json',[dict(id=t['id'],speaker=t['speaker'],display=t['display'],spoken=t['text'],voice_reused=t['speaker']=='male') for t in p['turns']])
    def stamp(s):
        ms=round(s*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{sec:02},{ms:03}'
    subs=[x for t in p['turns'] for x in t['subtitles']];(DEST/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(x['start'])} --> {stamp(x['end'])}\n{x['text']}" for i,x in enumerate(subs))+'\n',encoding='utf-8')
    return p

def preview():
    p=timeline();r=e.TokyoRenderer('full');dest=DEST/'layout';dest.mkdir(exist_ok=True);thumbs=[]
    for t in p['turns']:
        for i,c in enumerate(t['subtitles']):r.render(t,(c['start']+c['end'])/2-t['start']).save(dest/f"{t['id']}-sub-{i}.jpg",quality=92)
        im=r.render(t,(t['end']-t['start'])/2);im.save(dest/(t['id']+'.jpg'),quality=92);thumbs.append(im)
    sheet=Image.new('RGB',(1440,270*math.ceil(len(thumbs)/3)),e.BG)
    for i,im in enumerate(thumbs):sheet.paste(im.resize((480,270)),(i%3*480,i//3*270))
    sheet.save(dest/'contact-sheet.jpg',quality=94);print('PREVIEW',round(p['seconds'],3),flush=True)

def render():
    p=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));r=e.TokyoRenderer('full');parts=[];final=DEST/'dots-blender-tokyo-full-v03.mp4'
    if final.exists():raise RuntimeError('Preserve completed v03; use a new output version for changes')
    for t in p['turns']:
        target=DEST/'segments'/(t['id']+'.mp4');target.parent.mkdir(exist_ok=True)
        if not target.exists():
            process=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','4',str(target)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for frame in range(t['frames']):process.stdin.write(r.render(t,frame/FPS).tobytes())
                process.stdin.close();err=process.stderr.read();code=process.wait()
                if code:raise RuntimeError(err.decode(errors='replace'))
            except BaseException:process.kill();process.wait();target.unlink(missing_ok=True);raise
            e.save(target.with_suffix('.json'),dict(sha256=e.sha(target),code_sha256=e.sha(Path(__file__)),frames=t['frames']))
        else:
            proof=json.loads(target.with_suffix('.json').read_text());assert proof['sha256']==e.sha(target) and proof['code_sha256']==e.sha(Path(__file__))
        parts.append(target);print(t['id'],'ready',flush=True)
    # Exact picture segment from the preceding 10-second end slate.
    parts.append(OLD/'end.mp4');concat=DEST/'concat.txt';concat.write_text('\n'.join("file '"+x.as_posix()+"'" for x in parts),encoding='utf-8')
    n=round(p['seconds']*SR);voice=np.zeros(n,np.float32)
    for t in p['turns']:
        samples=read_voice(t['voice_path']);at=round(t['voice_start']*SR);voice[at:at+len(samples)]+=samples
    loop,meta=sunny_loop(sample_rate=SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n];music=default_bgm_bed(raw,p['seconds'],[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in p['turns']]);mix=voice[:,None]+music
    for t in p['turns']:
        if t['visual'] in ['build','fix','result']:
            cue=editorial_cue('improvement',sample_rate=SR)*.26;at=round((t['start']+.1)*SR);mix[at:at+len(cue)]+=cue
    mix*=min(1,.94/max(float(np.abs(mix).max()),1e-8));write_pcm(DEST/'mix.wav',mix);write_pcm(DEST/'narration.wav',voice)
    e.save(DEST/'audio-plan.json',dict(bgm=dict(DEFAULT_BGM_PROFILE),loop=meta,new_female_turns=10,reused_male_turns=5,voice_profile=SCRIPT['voice_profile'],voices={'female':'Aoede','male':'Charon'}))
    measured=e.run(['ffmpeg','-hide_banner','-nostdin','-i',str(DEST/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr;m=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0];filt='loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+m['input_i']+':measured_TP='+m['input_tp']+':measured_LRA='+m['input_lra']+':measured_thresh='+m['input_thresh']+':offset='+m['target_offset']+':linear=true'
    e.run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(concat),'-i',str(DEST/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af',filt,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(p['seconds']),'-movflags','+faststart',str(final)])
    e.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(final),'-f','null','-']);probe=json.loads(e.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]).stdout);v=next(x for x in probe['streams'] if x['codec_type']=='video');assert int(v['nb_frames'])==p['frames'] and abs(float(probe['format']['duration'])-p['seconds'])<.05
    measured=e.run(['ffmpeg','-hide_banner','-nostdin','-i',str(final),'-af','loudnorm=print_format=json','-f','null','-']).stderr;meter=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0];assert -17<float(meter['input_i'])<-15 and float(meter['input_tp'])<=-1
    e.save(DEST/'qc.json',dict(path=final.relative_to(ROOT).as_posix(),sha256=e.sha(final),bytes=final.stat().st_size,seconds=p['seconds'],frames=p['frames'],full_decode=True,loudness=meter,new_female_turns=10,reused_male_turns=5,human_reviewed=False,user_approved=False,published=False))
    print('COMPLETE',round(p['seconds'],3),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['voices','preview','render']);args=a.parse_args();globals()[args.action]()
