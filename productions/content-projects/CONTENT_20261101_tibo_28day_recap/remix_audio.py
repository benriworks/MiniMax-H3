"""v07: sunny eight-bar loop, three visual-synchronized cues, unchanged v06 video."""
from pathlib import Path
import importlib.util,json,math,shutil,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.audio_motifs import sunny_loop,editorial_cue,PRESET_ID
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.music_mix import default_bgm_bed,DEFAULT_BGM_PROFILE
spec=importlib.util.spec_from_file_location('tibo_render',HERE/'produce.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def streamhash(path,kind):
    return p.b.run(['ffmpeg','-v','error','-nostdin','-i',str(path),'-map','0:'+kind+':0','-c','copy','-f','hash','-hash','sha256','-']).stdout.strip()

def main():
    old=OUT/'tibo-recap/release/v06';dest=OUT/'tibo-recap/release/v07';target=dest/'tibo-recap-v07.mp4'
    if dest.exists():raise RuntimeError('Preserve previous audio attempt; use a new version')
    dest.mkdir(parents=True)
    timeline=json.loads((old/'timeline.json').read_text(encoding='utf-8'));seconds=timeline[-1]['end'];n=round(seconds*SR)
    assert p.sha(old/'tibo-recap-v06.mp4')=='13F13DF6C02F62B28CB5F221D496E05F1FA895A8FA52F75922439D7968DD2629'
    voice=read_voice(old/'narration.wav');assert len(voice)==n
    spans=[(s['voice_start'],s['voice_start']+s['voice_seconds']) for s in timeline]
    loop,loop_meta=sunny_loop(sample_rate=SR)
    raw=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    music=default_bgm_bed(raw,seconds,spans)
    events=[]
    def event(kind,at,day=None,context='day',gain=1):
        events.append(dict(kind=kind,start=at,day=day,context=context,gain=gain))
    for scene,part in zip(p.EP['scenes'],timeline):
        kind=scene['kind'];start=part['start'];duration=part['end']-start
        if 'days' in scene:
            for day in scene['days']:
                frames=[k for k in range(part['frames']) if p.day_for(scene,k/24,duration)[0]==day]
                day_start=start+frames[0]/24;day_seconds=len(frames)/24
                typ=p.PLAN['days'][day-1]['type']
                if typ=='reset':event('reset',day_start+day_seconds*.48/1.8,day)
                elif typ=='bank':event('bank',day_start+day_seconds*.32,day)
                else:event('improvement',day_start+.10,day)
        elif kind=='hero':event('reset',start+.48,context='opening_button')
        elif kind=='types':
            event('reset',start+.48,context='type_explanation')
            event('bank',start+.15+part['voice_seconds']/len(scene['captions'])+.7,context='type_explanation')
        elif kind=='forecast':event('bank',start+.7,context='forecast_only',gain=.55)
    effects=np.zeros((n,2),dtype=np.float32)
    for kind in ['reset','bank','improvement']:write_pcm(dest/f'cue-{kind}.wav',editorial_cue(kind,sample_rate=SR))
    for item in events:
        cue=editorial_cue(item['kind'],sample_rate=SR);at=round(item['start']*SR);stop=min(n,at+len(cue))
        local=np.ones(stop-at,dtype=np.float32)
        for begin,end in spans:
            left=max(at,round(begin*SR));right=min(stop,round(end*SR))
            if right>left:local[left-at:right-at]=.63
        effects[at:stop]+=cue[:stop-at]*local[:,None]*item['gain']
    mix=voice[:,None]+music+effects;peak=float(np.max(np.abs(mix)));gain=min(1,.95/max(peak,1e-8));mix*=gain
    write_pcm(dest/'music-loop.wav',loop);write_pcm(dest/'music.wav',music);write_pcm(dest/'effects.wav',effects);write_pcm(dest/'mix.wav',mix)
    shutil.copy2(old/'narration.wav',dest/'narration.wav');shutil.copy2(old/'timeline.json',dest/'timeline.json')
    assert p.sha(dest/'narration.wav')==p.sha(old/'narration.wav')
    measured=p.b.run(['ffmpeg','-hide_banner','-nostdin','-i',str(dest/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);extra=[]
    if not(-18<=float(meter['input_i'])<=-14 and float(meter['input_tp'])<=-1):
        extra=['-af',f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={meter['input_i']}:measured_TP={meter['input_tp']}:measured_LRA={meter['input_lra']}:measured_thresh={meter['input_thresh']}:offset={meter['target_offset']}:linear=true"]
    p.b.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(old/'tibo-recap-v06.mp4'),'-i',str(dest/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy',*extra,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(seconds),'-movflags','+faststart',str(target)])
    p.b.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(target),'-f','null','-'])
    vhash=streamhash(target,'v');assert vhash==streamhash(old/'tibo-recap-v06.mp4','v')
    measured=p.b.run(['ffmpeg','-hide_banner','-nostdin','-i',str(target),'-af','loudnorm=print_format=json','-f','null','-']).stderr
    meter=json.loads(measured[measured.rfind('{'):measured.rfind('}')+1]);assert -18<=float(meter['input_i'])<=-14 and float(meter['input_tp'])<=-1
    meta=json.loads(p.b.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]).stdout)
    v=next(s for s in meta['streams'] if s['codec_type']=='video');assert v['width']==1080 and v['height']==1920 and v['avg_frame_rate']=='24/1' and int(v['nb_frames'])==2019
    assert abs(float(meta['format']['duration'])-seconds)<.1
    p.save(dest/'audio-plan.json',dict(loop=loop_meta,bgm_settings=dict(DEFAULT_BGM_PROFILE),effects=events,effect_counts={k:sum(e['kind']==k for e in events) for k in ['reset','bank','improvement']},effects_voice_gain=.63,mix_peak_before=peak,premaster_gain=gain,narration_unchanged=True,source_narration=p.b.record(old/'narration.wav'),new_tts_requests=0))
    p.save(dest/'verification.json',dict(p.b.record(target),seconds=seconds,width=1080,height=1920,fps=24,frames=2019,full_decode='passed',loudness=meter,video_stream_unchanged=True,video_stream_sha256=vhash,narration_unchanged=True,music_preset=PRESET_ID,bgm_settings=dict(DEFAULT_BGM_PROFILE),cue_kinds=['reset','bank','improvement'],new_tts_requests=0,human_listening=False,user_approved=False,mobile_playback=False,published=False))
    p.save(dest/'loop-check.json',loop_meta)
    shutil.copy2(HERE/'remix_audio.py',dest/'remix-snapshot.py');shutil.copy2(ROOT/'tools/studio/audio_motifs.py',dest/'audio-motifs-snapshot.py')
    print(json.dumps(dict(verified=True,seconds=seconds,bytes=target.stat().st_size,music=loop_meta,events=len(events),loudness=meter['input_i'],true_peak=meter['input_tp'])))

if __name__=='__main__':main()
