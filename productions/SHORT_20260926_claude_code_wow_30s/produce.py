"""Thirty-second editorial video: SAPI narration, original score, verified assembly."""
from pathlib import Path
from datetime import datetime, timezone
import array, hashlib, json, shutil, subprocess, sys, uuid, wave, zipfile
import numpy as np

PROD = Path(__file__).resolve().parent
ROOT = PROD.parents[1]
sys.path.insert(0, str(ROOT))
from tools.studio.narration import generate_local_narration
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def record(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}

def check(r):
    p = (ROOT / r.get('path', r.get('rel_path'))).resolve(strict=True)
    assert p.is_relative_to(ROOT) and record(p)['sha256'] == r['sha256'] and p.stat().st_size == r['bytes']
    return p

def save(p, data):
    with p.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

def ffmpeg(*args):
    subprocess.run(['ffmpeg','-v','error','-nostdin','-n',*map(str,args)], check=True, creationflags=FLAGS)

def score(path, segments):
    sr = 48000
    total = 30*sr
    track = np.zeros((total,2), np.float64)
    rng = np.random.default_rng(20260926)
    def add(start, duration, freq, amp, decay=2.8, pan=0, pad=False):
        offset = round(start*sr)
        count = min(round(duration*sr),total-offset)
        if count <= 0: return
        t = np.arange(count)/sr
        attack = np.minimum(t/(.12 if pad else .012),1)
        tail = np.minimum((count/sr-t)/.12,1)
        env = attack*tail*(np.exp(-t*decay) if not pad else np.ones(count))
        tone = (np.sin(2*np.pi*freq*t)+.22*np.sin(2*np.pi*freq*2*t)) * env * amp
        track[offset:offset+count,0] += tone*np.sqrt((1-pan)/2)
        track[offset:offset+count,1] += tone*np.sqrt((1+pan)/2)
    beat = 60/112
    chords = [(130.813,164.814,195.998,293.665),(110,130.813,164.814,246.942),
              (87.307,130.813,174.614,220),(97.999,146.832,195.998,246.942)]
    for bar in range(14):
        start = bar*4*beat
        chord = chords[bar%4]
        for i,note in enumerate(chord): add(start,4*beat,note,.018,pan=(-.5 if i%2 else .5),pad=True)
        for eighth in range(8):
            add(start+eighth*beat/2,.65,chord[[0,2,1,3,2,1,3,2][eighth]]*2,.045,decay=6,pan=(-.35 if eighth%2 else .35))
        for b in range(4):
            at=start+b*beat
            add(at,.19,62,.055,decay=22)
            offset=round((at+beat/2)*sr); n=min(2400,total-offset)
            if n>0:
                noise=rng.normal(0,1,n); noise=np.r_[0,np.diff(noise)]
                hat=noise*np.exp(-np.arange(n)/450)*.009
                track[offset:offset+n] += hat[:,None]
    for start in [0,5,10,15,20,25]:
        for i,note in enumerate([523.251,659.255,783.991]): add(start+i*.075,.5,note,.065,decay=7,pan=0)
    times=np.arange(total)/sr
    duck=np.ones(total)
    for segment in segments:
        a,b=segment['start_ms']/1000,segment['end_ms']/1000
        duck=np.minimum(duck,1-.42*np.clip((times-a+.10)/.10,0,1)*np.clip((b+.18-times)/.18,0,1))
    track *= (duck*np.minimum(times/.12,1)*np.clip((30-times)/.75,0,1))[:,None]
    assert np.max(np.abs(track)) < .8
    with wave.open(str(path),'wb') as f:
        f.setparams((2,2,sr,0,'NONE','not compressed'))
        f.writeframes((track*32767).astype('<i2').tobytes())

def prepare(reuse_audio=None):
    story = read(PROD/'story.json')
    assert story['duration_ms']==30000 and len(story['segments'])==6
    out = ROOT/'outputs/productions'/PROD.name/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    sources=[record(PROD/name) for name in ['story.json','SOURCES_JA.md','Wow.tsx','render.mjs','produce.py']]
    for item in story['visuals'].values():
        proof=read(ROOT/item['proof'])
        assert proof['execution']['success'] is True and proof['review_status']=='visual_review_passed'
        assert check(proof['artifact']) == (ROOT/item['path']).resolve()
        sources.extend([record(ROOT/item['proof']),proof['artifact']])
    audio_reuse=None
    if reuse_audio is not None:
        prior=reuse_audio.resolve(strict=True)
        assert prior.is_relative_to(ROOT/'outputs/productions'/PROD.name)
        old=read(prior/'preparation.json'); proof=read(prior/'verification.json')
        assert proof['review_status']=='verified_candidate_awaiting_user_review'
        for key in ['duration_ms','voice','rate','pronunciations','segments','music']:
            assert old['story'][key]==story[key], 'Audio input changed: '+key
        source_delivery=check(proof['delivery'])
        assert source_delivery==prior/'claude-code-wow-30s.mp4'
        files={}
        for name in ['narration.wav','captions.srt','timings.json','manifest.json','original-score.wav']:
            item=next(r for r in old['sources'] if (ROOT/r['path']).resolve()==prior/name)
            files[name]=check(item)
        sources.extend([record(prior/'preparation.json'),record(prior/'verification.json'),record(source_delivery)])
        audio_reuse={'source_delivery':record(source_delivery),'method':'aac_stream_copy'}
    else:
        token=uuid.uuid4().hex
        narration=generate_local_narration(ROOT,production_id='production_'+token,run_id='run_'+token,
            payload={'voice':story['voice'],'rate':story['rate'],'pronunciations':story['pronunciations'],
                     'segments':[{'text':s['text']} for s in story['segments']]},
            segment_start_ms=[s['start_ms'] for s in story['segments']])
        save(out/'narration-result.json',narration)
        files={a['name']:check(a) for a in narration['artifacts']}
    timings=read(files['timings.json'])
    for i,s in enumerate(timings['segments']):
        if s['start_ms']!=story['segments'][i]['start_ms'] or s['end_ms']>(i+1)*5000-100:
            raise ValueError('Narration slot overflow: '+str(s)+'; retained '+str(out))
    for name,p in files.items(): shutil.copyfile(p,out/name)
    if audio_reuse is None:score(out/'original-score.wav',timings['segments'])
    sources.extend(record(out/name) for name in dict.fromkeys([*files,'original-score.wav']))
    sources.append(record(ROOT/'tools/studio/narration.py'))
    save(out/'preparation.json',{'story':story,'sources':sources,'timings':timings,'audio_reuse':audio_reuse,'new_video_generation':False,'external_api_calls':0})
    print(json.dumps({'event':'prepared','output':str(out),'speech_intervals':[[s['start_ms'],s['end_ms']] for s in timings['segments']]},ensure_ascii=False),flush=True)

def verify(path):
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],creationflags=FLAGS))
    v=next(s for s in probe['streams'] if s['codec_type']=='video'); a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert len(probe['streams'])==2 and (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']),v['codec_name'],a['codec_name'],a['sample_rate'])==(1080,1920,'24/1',720,'h264','aac','48000')
    assert abs(float(probe['format']['duration'])-30)<.002
    ffmpeg('-xerror','-i',path,'-f','null','-')
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vn','-f','f32le','-ac','1','-'],creationflags=FLAGS)
    values=np.frombuffer(pcm,dtype='<f4'); peak=float(np.max(np.abs(values)))
    assert .01<peak<.99
    return {**record(path),'probe':probe,'audio_sample_peak':peak,'full_decode_verified':True}

def finish(out):
    out=out.resolve(strict=True)
    assert out.is_relative_to(ROOT/'outputs/productions'/PROD.name)
    prep=read(out/'preparation.json'); rendered=read(out/'render.json')
    for r in [*prep['sources'],*rendered['sources']]:check(r)
    video=check(rendered['timeline'])
    delivery=out/'claude-code-wow-30s.mp4'
    audio_reuse=prep.get('audio_reuse')
    if audio_reuse:
        prior=check(audio_reuse['source_delivery'])
        ffmpeg('-i',video,'-i',prior,'-map','0:v:0','-map','1:a:0','-c','copy','-t','30','-movflags','+faststart',delivery)
        def audio_hash(p):
            return subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-'],creationflags=FLAGS,text=True).strip()
        original_hash=audio_hash(prior)
        assert original_hash==audio_hash(delivery), 'Audio stream changed'
        audio_reuse={**audio_reuse,'packet_hash':original_hash,'identical_audio_verified':True}
    else:
        ffmpeg('-i',out/'narration.wav','-i',out/'original-score.wav','-filter_complex',
            '[0:a]apad,atrim=duration=30,volume=1.05[v];[1:a]volume=0.62[b];[v][b]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.92:level=false:latency=true[a]',
            '-map','[a]','-ar','48000','-ac','2','-c:a','pcm_s16le','-t','30',out/'mix.wav')
        ffmpeg('-i',video,'-i',out/'mix.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t','30','-movflags','+faststart',delivery)
    result=verify(delivery)
    for second in [0,3,8,13,18,23,28,29]:
        ffmpeg('-ss',second,'-i',delivery,'-frames:v','1','-vf','scale=360:640:flags=lanczos',out/f'preview-{second}.png')
    ffmpeg('-i',delivery,'-vf','fps=1,scale=216:384,tile=6x5','-frames:v','1',out/'contact-sheet.png')
    save(out/'verification.json',{'verified_at':datetime.now(timezone.utc).isoformat(),'delivery':result,'sources':rendered['sources'],
        'typography':rendered['typography'],'timings':prep['timings'],'audio_reuse':audio_reuse,'review_status':'awaiting_visual_review','user_approved':False})
    print(json.dumps({'event':'assembled','artifact':record(delivery),'peak':result['audio_sample_peak']}),flush=True)

if __name__=='__main__':
    if sys.argv[1:]==['prepare']:prepare()
    elif len(sys.argv)==4 and sys.argv[1:3]==['prepare','--reuse-audio']:prepare(Path(sys.argv[3]))
    elif len(sys.argv)==3 and sys.argv[1]=='finish':finish(Path(sys.argv[2]))
    else:raise SystemExit('prepare [--reuse-audio PRIOR_OUTPUT] | finish OUTPUT')
