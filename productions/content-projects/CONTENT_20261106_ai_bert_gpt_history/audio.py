"""Steady, low licensed BGM and equalized dialogue; shared defaults are unchanged."""
import argparse,json,math,subprocess
import numpy as np
from produce import ROOT,HERE,OUT,SR,read_voice,write_pcm,plan,dest,run,save,sha,REVISIONS

MUSIC=dict(file='yuugurenocampus.mp3',title='夕暮れのキャンパス',artist='甘茶の音楽工房',url='https://amachamusic.chagasi.com/music_yuugurenocampus.html',terms='https://amachamusic.chagasi.com/terms.html',checked_at='2026-11-06',source_sha256='19fd42bf8e542fe345e7b1209c4bcf227eaf8a572944022774fa0ff3e6a3bf66',content_id_registration=False)

def meter(p):
    text=run(['ffmpeg','-hide_banner','-nostdin','-i',str(p),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    return json.JSONDecoder().raw_decode(text[text.rfind('{'):])[0]

def source_music():
    inventory=ROOT/'outputs/content-projects/CONTENT_20261104_anthropic_departures/_private/music-library/inventory-v01.json'
    data=json.loads(inventory.read_text(encoding='utf-8'));item=next(x for x in data if x['file']==MUSIC['file'])
    from pathlib import Path
    path=Path(item['local_path'])
    if sha(path)!=MUSIC['source_sha256']:raise RuntimeError('Music source changed')
    return path

def build(kind):
    p=plan(kind);folder=dest(kind);n=round(p['seconds']*SR);voice=np.zeros(n,dtype=np.float32);levels=[]
    for t in p['turns']:
        path=ROOT/t['voice_path'];pcm=read_voice(path);active=pcm[np.abs(pcm)>.012]
        rms=float(np.sqrt(np.mean(active*active))) if len(active) else .01
        gain=min(.13/max(rms,.001),.77/max(float(np.abs(pcm).max()),.001))
        at=round(t['voice_start']*SR);voice[at:at+len(pcm)]+=pcm*gain
        levels.append(dict(turn=t['id'],speaker=t['speaker'],source_sha256=sha(path),gain=gain,active_rms_before=rms,active_rms_after=rms*gain))
    write_pcm(folder/'narration.wav',voice)
    source=source_music();music_info=meter(source)
    result=subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(source),'-ar',str(SR),'-ac','2','-f','f32le','pipe:1'],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    raw=np.frombuffer(result.stdout,dtype='<f4').reshape(-1,2).copy();raw*=10**((-31-float(music_info['input_i']))/20)
    cross=round(2.0*SR);step=len(raw)-cross;music=np.zeros((n,2),dtype=np.float32)
    for at in range(0,n,step):
        clip=raw[:min(len(raw),n-at)].copy()
        if at>0:
            count=min(cross,len(clip));clip[:count]*=np.sqrt(np.linspace(0,1,count,dtype=np.float32))[:,None]
        if at+len(raw)<n:
            count=min(cross,len(clip));clip[-count:]*=np.sqrt(np.linspace(1,0,count,dtype=np.float32))[:,None]
        music[at:at+len(clip)]+=clip
    # Constant bed: no speech envelope and no introduction/ending gain boost.
    lead=min(n,round(.3*SR));tail=min(n,round(1.2*SR))
    music[:lead]*=np.linspace(0,1,lead,dtype=np.float32)[:,None];music[-tail:]*=np.linspace(1,0,tail,dtype=np.float32)[:,None]
    mix=voice[:,None]+music;peak=float(np.max(np.abs(mix)));gain=min(1,.94/max(peak,.001));mix*=gain
    write_pcm(folder/'music-mixed.wav',music);write_pcm(folder/'mix.wav',mix)
    save(folder/'audio-provenance.json',dict(music=MUSIC,music_target_lufs=-31,source_input_lufs=float(music_info['input_i']),speech_ducking=False,edge_boost_db=0,head_fade_seconds=.3,end_fade_seconds=1.2,crossfade_seconds=2,linear_mix_gain=gain,source_unchanged=sha(source)==MUSIC['source_sha256'],narration_levels=levels,scope='case-specific steady bed; no common-default changes'))
    print(json.dumps(dict(kind=kind,seconds=p['seconds'],voice_turns=len(levels),music=MUSIC['title'],speech_ducking=False),ensure_ascii=False),flush=True)

def mux(kind):
    p=plan(kind);folder=dest(kind);target=folder/('ai-bert-gpt-history-'+kind+'-'+REVISIONS[kind]+'.mp4')
    if target.exists():raise RuntimeError('Do not overwrite a release')
    m=meter(folder/'mix.wav')
    filt='loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+m['input_i']+':measured_TP='+m['input_tp']+':measured_LRA='+m['input_lra']+':measured_thresh='+m['input_thresh']+':offset='+m['target_offset']+':linear=true'
    run(['ffmpeg','-v','error','-nostdin','-n','-i',str(folder/'video-only.mp4'),'-i',str(folder/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filt,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(p['seconds']),'-movflags','+faststart',str(target)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(target),'-f','null','-'])
    probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]).stdout);v=next(x for x in probe['streams'] if x['codec_type']=='video');loud=meter(target)
    assert (v['width'],v['height'],int(v['nb_frames']))==(p['width'],p['height'],p['frames'])
    assert abs(float(probe['format']['duration'])-p['seconds'])<.1
    assert -18<float(loud['input_i'])<-14 and float(loud['input_tp'])<=-1
    save(folder/'qc.json',dict(status='technically_verified_human_review_pending',sha256=sha(target),bytes=target.stat().st_size,seconds=p['seconds'],frames=p['frames'],full_decode=True,final_aac_loudness=loud,probe=probe,music=MUSIC,adopted_outline='proposal-v01',user_approved=False,published=False))
    run(['ffmpeg','-v','error','-nostdin','-n','-i',str(target),'-vf','scale=540:-2' if kind=='short' else 'scale=960:-2','-c:v','libx264','-preset','veryfast','-crf','26','-c:a','aac','-b:a','96k','-movflags','+faststart',str(folder/'review-proxy.mp4')])
    print(json.dumps(dict(kind=kind,file=target.name,seconds=p['seconds'],bytes=target.stat().st_size,LUFS=loud['input_i'],true_peak=loud['input_tp'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','mux']);p.add_argument('--kind',choices=['short','full'],default='short');a=p.parse_args()
    build(a.kind) if a.action=='build' else mux(a.kind)
