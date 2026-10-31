"""Raise the music, emphasize the edges, and stream-copy the approved v03 video."""
from pathlib import Path
import hashlib,json,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name;DEST=OUT/'release/v04'
sys.path.insert(0,str(ROOT))
from tools.studio.longform_audio import music_bright,read_voice,write_pcm,SR
from tools.studio.music_mix import music_gain_envelope

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd):return subprocess.run(cmd,check=True,capture_output=True,text=True).stdout
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    DEST.mkdir(parents=True,exist_ok=True);target=DEST/'chatgpt-pro-usage-v04.mp4'
    if target.exists():raise RuntimeError('Preserve v04 and create a new version')
    source=OUT/'release/v03/chatgpt-pro-usage-v03.mp4'
    prior=json.loads(source.with_name('verification.json').read_text(encoding='utf-8'))
    assert sha(source)==prior['sha256']
    timeline=json.loads(source.with_name('timeline.json').read_text(encoding='utf-8'));seconds=48
    narration=np.zeros(seconds*SR,dtype=np.float32);spans=[];proofs=[]
    for scene in timeline:
        p=OUT/f"voice/v01/scene-{scene['index']:02d}/Aoede/voice.wav"
        proof=json.loads(p.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(p).upper()==next(f['sha256'] for f in proof['files'] if f['path'].endswith('/voice.wav'))
        v=read_voice(p);v=v/max(.01,np.max(np.abs(v)))*.82
        a=round(scene['voice_start']*SR);b=a+len(v);assert b<=len(narration)
        narration[a:b]+=v;spans.append((a/SR,b/SR));proofs.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    gain=1.3*10**(4/20)
    envelope=music_gain_envelope(seconds,spans,base_gain=gain,duck_gain=.2,edge_boost_db=3.)
    music=music_bright(seconds,fade_in_seconds=.08,fade_out_seconds=.25)
    music*=envelope[:,None]
    mixed=narration[:,None]*np.ones((1,2),dtype=np.float32)+music
    peak=float(np.max(np.abs(mixed)))
    if peak>=.98:raise RuntimeError('Mix has insufficient peak headroom; revise music gain before encoding')
    write_pcm(DEST/'narration-preserved.wav',narration)
    write_pcm(DEST/'music-v04.wav',music)
    write_pcm(DEST/'mix-premaster.wav',mixed)
    run(['ffmpeg','-v','error','-nostdin','-n','-i',str(source),'-i',str(DEST/'mix-premaster.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-t','48',str(target)])
    def video_hash(p):return run(['ffmpeg','-v','error','-i',str(p),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-']).strip()
    assert video_hash(target)==video_hash(source)
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(target),'-f','null','-'])
    stats=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]))
    video=next(s for s in stats['streams'] if s['codec_type']=='video')
    assert(video['width'],video['height'],int(video['nb_frames']),video['avg_frame_rate'])==(1080,1920,1152,'24/1')
    assert abs(float(stats['format']['duration'])-48)<.1
    data=dict(version='v04',path=target.relative_to(ROOT).as_posix(),bytes=target.stat().st_size,sha256=sha(target),seconds=48,
       video_bitstream_unchanged=True,video_sha256=video_hash(target),narration_sources=proofs,narration_timing_and_peak_gain_unchanged=True,
       bgm_base_increase_db=4,edge_extra_boost_db=3,intro_boost_seconds=1.4,outro_boost_seconds=2.2,
       music_fade_in_seconds=.08,music_fade_out_seconds=.25,duck_gain=.2,duck_attack_seconds=.12,duck_release_seconds=.25,
       mix_sample_peak=peak,full_decode='passed',new_tts_requests=0,new_minimax_requests=0,human_listening=False,mobile_playback=False,
       user_feedback='よいと思います。BGMはもう少し音量を高めにして、動画の最初と最後はもっと大きめにしたいですね。',
       accepted_scope='v03人物動作と映像を維持。BGM修正後v04の最終試聴・採用・公開は別。',user_approved=False,published=False)
    save(DEST/'verification.json',data);save(DEST/'timeline.json',timeline)
    print(json.dumps(data,ensure_ascii=True))
if __name__=='__main__':main()
