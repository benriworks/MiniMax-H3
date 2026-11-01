"""Change only the two celebration cuts and append a music-only 10-second end slate."""
from pathlib import Path
import argparse,json,math,shutil,subprocess,wave
import numpy as np
from PIL import Image,ImageDraw,ImageOps
import produce as p
from tools.studio.closing_visuals import celebration_layer,end_screen,END_SCREEN_LAYOUT
OLD=p.DEST;DEST=p.OUT/'release/v02';FPS=24
SOURCE_SHA='CCA199A94CA662F2B490415E7F874751630075AA38092B4FDA70689C75122733'
PLAN=json.loads((OLD/'timeline.json').read_text(encoding='utf-8'))
START=next(t['start'] for t in PLAN['turns'] if t['visual']=='applause')
NEW_SECONDS=PLAN['seconds']+10;NEW_FRAMES=PLAN['frames']+240

class RevisedRenderer(p.Renderer):
    def draw(self,t,local):
        if t['visual'] not in ['applause','closing']:return super().draw(t,local)
        im=self.stage(t);d=ImageDraw.Draw(im)
        p.label(im,t['caption'],(330,180,1590,265),42,p.TEAL)
        source=Image.new('RGB',(1250,590),'#0D1C35') if local<4.8 else self.pair.frame(t['speaker'] if self.state(t,local,t['speaker']) else None)
        tile=Image.new('RGB',(1250,555),'#0D1C35');fitted=ImageOps.contain(source,(1250,555),method=Image.Resampling.LANCZOS)
        tile.paste(fitted,((1250-fitted.width)//2,(555-fitted.height)//2));im.paste(tile,(335,282))
        if local<4.8:
            for name,x in [('male-understanding',365),('female-happy',1135)]:
                raw=self.motion(name,min(len(self.motions[name])-1,int(local*FPS)))
                raw=raw.crop((0,180,540,688)) if name=='male-understanding' else raw.crop((0,75,540,min(raw.height,700)))
                shot=ImageOps.fit(raw,(420,430),method=Image.Resampling.LANCZOS,centering=(.5,.55));im.paste(shot,(x,390))
            faces=[(390,385,765,745),(1160,385,1530,745)]
        else:faces=[(665,282,985,565),(1000,365,1320,675)]
        overlay=celebration_layer(t['start']+local-START,faces=faces)
        im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB')
        p.text(im,'出典：Tibo @thsottiaux / OpenAI公式　確認：2026/11/1 JST',(48,846),24,'#536B76')
        sub=next((s['text'] for s in t['subtitles'] if s['start']<=t['start']+local<s['end']),None)
        if sub:
            lines=sub.splitlines();top=906 if len(lines)>1 else 934
            for k,line in enumerate(lines):p.label(im,line,(145,top+k*57,1775,top+54+k*57),43,'#FFFFFF')
            p.box(im,(45,927,112,995),p.BLUE if t['speaker']=='male' else p.PURPLE,13);p.label(im,'男' if t['speaker']=='male' else '女',(45,927,112,995),35,'#FFFFFF')
        group=[s for s in p.SCRIPT['turns'] if s['chapter']==t['chapter']];pos=next(i for i,s in enumerate(group) if s['id']==t['id'])
        progress=(int(t['chapter'])-1+(pos+local/(t['end']-t['start']))/len(group))/9
        ImageDraw.Draw(im).rectangle((0,1071,round(progress*1920),1079),fill='#59CBCE')
        if t['visual']=='closing':
            cross=p.ease((local-(t['end']-t['start']-.6))/.6)
            if cross:im=Image.blend(im,end_screen(0,label=p.label),cross)
        return im

def encode(target,frames,draw):
    if target.exists():
        proof=target.with_suffix('.json')
        if not proof.exists() or json.loads(proof.read_text())['sha256']!=p.sha(target):raise RuntimeError('Unverified prior cut; preserve it')
        return
    args=['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart',str(target)]
    with target.with_suffix('.log').open('wb') as log:
        proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for frame in range(frames):proc.stdin.write(draw(frame/FPS).tobytes())
        finally:proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('Cut encoding failed')
    probe=json.loads(p.run(['ffprobe','-v','error','-show_streams','-of','json',str(target)]).stdout)['streams'][0]
    assert int(probe['nb_frames'])==frames
    p.save(target.with_suffix('.json'),dict(p.record(target),frames=frames,revision_code_sha256=p.sha(Path(__file__)),effects_code_sha256=p.sha(p.ROOT/'tools/studio/closing_visuals.py')))

def audio():
    n=round(NEW_SECONDS*p.SR);oldn=round(PLAN['seconds']*p.SR)
    voice=np.zeros(n,np.float32)
    for turn in PLAN['turns']:
        source=p.read_voice(turn['voice_path']);start=round(turn['voice_start']*p.SR)
        voice[start:start+len(source)]+=source
    loop,meta=p.sunny_loop(sample_rate=p.SR);raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    spans=[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in PLAN['turns']]
    music=p.default_bgm_bed(raw,NEW_SECONDS,spans);fx=np.zeros((n,2),np.float32)
    fade=round(1.2*p.SR);music[-fade:]*=np.cos(np.linspace(0,math.pi/2,fade))[:,None]
    events=json.loads((OLD/'audio-plan.json').read_text(encoding='utf-8'))['events']
    for e in events:
        cue=p.editorial_cue(e['kind'],sample_rate=p.SR)*.63;a=round(e['start']*p.SR);b=min(n,a+len(cue));fx[a:b]+=cue[:b-a]
    oldaudio=json.loads((OLD/'audio-plan.json').read_text(encoding='utf-8'));gain=min(1,.94/oldaudio['mix_peak'])
    mix=(voice[:,None]+music+fx)*gain;assert np.max(np.abs(mix))<.999
    p.write_pcm(DEST/'mix.wav',mix);p.write_pcm(DEST/'narration-padded.wav',voice)
    stable_samples=round((PLAN['seconds']-p.DEFAULT_BGM_PROFILE['outro_seconds'])*p.SR)
    with wave.open(str(OLD/'mix.wav'),'rb') as a,wave.open(str(DEST/'mix.wav'),'rb') as b:
        assert a.readframes(stable_samples)==b.readframes(stable_samples)
    with wave.open(str(OLD/'narration.wav'),'rb') as a,wave.open(str(DEST/'narration-padded.wav'),'rb') as b:
        assert a.readframes(oldn)==b.readframes(oldn)
    p.save(DEST/'audio-plan.json',dict(loop=meta,bgm_settings=dict(p.DEFAULT_BGM_PROFILE),end_screen_additional_fade_seconds=1.2,speech_unchanged=True,new_tts_requests=0,tail_music_only_seconds=10,source_narration=p.record(OLD/'narration.wav'),unchanged_pcm_mix_prefix_seconds=stable_samples/p.SR,master_gain=gain,original_events=events))

def samples():
    DEST.mkdir(parents=True,exist_ok=True);qc=DEST/'design-review';qc.mkdir(exist_ok=True)
    r=RevisedRenderer();r.plan=PLAN
    for t in PLAN['turns'][-2:]:
        for frac in [.15,.6,.88]:r.draw(t,(t['end']-t['start'])*frac).save(qc/(t['id']+f'-{frac}.png'))
    for s in [0,5,9.75]:end_screen(s,label=p.label).save(qc/f'end-{s}.png')
    guide=end_screen(5,label=p.label);d=ImageDraw.Draw(guide)
    for i,item in enumerate(END_SCREEN_LAYOUT['videos']):p.label(guide,f'関連動画 {i+1}',item['rect'],48,'#FFFFFF')
    p.label(guide,'登録',(840,500,1080,680),48,'#FFFFFF');guide.save(qc/'placement-guide.png')
    p.save(DEST/'end-screen-layout.json',dict(END_SCREEN_LAYOUT,start=PLAN['seconds'],end=NEW_SECONDS,official_help='https://support.google.com/youtube/answer/6388789?hl=ja',checked_at='2026-11-01'))

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    if p.sha(OLD/'tibo-28day-full-v01.mp4')!=SOURCE_SHA:raise ValueError('Original changed')
    samples();audio();r=RevisedRenderer();r.plan=PLAN
    segments=[]
    for t in PLAN['turns']:
        if t['visual'] in ['applause','closing']:
            target=DEST/(t['id']+'.mp4');encode(target,t['frames'],lambda s,t=t:r.draw(t,s))
        else:
            target=OLD/'shots'/(t['id']+'.mp4');proof=json.loads(target.with_suffix('.json').read_text());assert p.sha(target)==proof['sha256']
        segments.append(target)
    target=DEST/'end-screen.mp4';encode(target,240,lambda s:end_screen(s,label=p.label));segments.append(target)
    listing=DEST/'concat.txt';listing.write_text('\n'.join("file '"+s.as_posix()+"'" for s in segments),encoding='utf-8')
    raw=DEST/'picture.mp4'
    if not raw.exists():p.run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)])
    measured=p.run(['ffmpeg','-hide_banner','-nostdin','-i',str(DEST/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);filt=f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={meter['input_i']}:measured_TP={meter['input_tp']}:measured_LRA={meter['input_lra']}:measured_thresh={meter['input_thresh']}:offset={meter['target_offset']}:linear=true"
    video=DEST/'tibo-28day-full-v02.mp4'
    if not video.exists():p.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(raw),'-i',str(DEST/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filt,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(NEW_SECONDS),'-movflags','+faststart',str(video)])
    p.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(video),'-f','null','-'])
    probe=json.loads(p.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]).stdout);stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (stream['width'],stream['height'],stream['avg_frame_rate'],int(stream['nb_frames']))==(1920,1080,'24/1',NEW_FRAMES)
    def prefix_hash(path):return p.run(['ffmpeg','-v','error','-nostdin','-i',str(path),'-map','0:v:0','-frames:v',str(round(START*FPS)),'-c','copy','-f','hash','-hash','sha256','-']).stdout.strip()
    stable=prefix_hash(video);assert stable==prefix_hash(OLD/'tibo-28day-full-v01.mp4')
    measured=p.run(['ffmpeg','-hide_banner','-nostdin','-i',str(video),'-af','loudnorm=print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);assert -18<float(meter['input_i'])<-14 and float(meter['input_tp'])<=-1
    p.save(DEST/'verification.json',dict(p.record(video),seconds=NEW_SECONDS,width=1920,height=1080,fps=24,frames=NEW_FRAMES,full_decode=True,loudness=meter,source_video_sha256=SOURCE_SHA,unchanged_video_prefix_seconds=START,unchanged_video_prefix_hash=stable,new_tts_requests=0,new_minimax_requests=0,end_screen_seconds=10,human_listening=False,user_approved=False,mobile_playback=False,published=False))
    p.save(DEST/'timeline.json',dict(PLAN,seconds=NEW_SECONDS,frames=NEW_FRAMES,end_screen=dict(start=PLAN['seconds'],end=NEW_SECONDS,voice=False),revision='v02'))
    shutil.copy2(OLD/'captions.srt',DEST/'captions.srt');shutil.copy2(Path(__file__),DEST/'revision-snapshot.py');shutil.copy2(p.ROOT/'tools/studio/closing_visuals.py',DEST/'closing-visuals-snapshot.py')
    print(json.dumps(dict(p.record(video),seconds=NEW_SECONDS,frames=NEW_FRAMES,loudness=meter['input_i'],true_peak=meter['input_tp'])),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--samples-only',action='store_true');a=parser.parse_args()
    if a.samples_only:samples()
    else:main()
