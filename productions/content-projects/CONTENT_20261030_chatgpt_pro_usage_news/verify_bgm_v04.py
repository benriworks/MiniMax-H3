"""Compare voice components to the preserved old mix and measure the actual AAC."""
from pathlib import Path
import hashlib,json,subprocess,sys,wave
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.studio.longform_audio import music_bright,read_voice,SR,write_pcm
OUT=ROOT/'outputs/content-projects'/Path(__file__).parent.name;D=OUT/'release/v04'

def main():
    plan=json.loads((D/'timeline.json').read_text(encoding='utf-8'));n=48*SR
    voice=np.zeros(n,dtype=np.float32);old_duck=np.ones(n,dtype=np.float32)
    for scene in plan:
        v=read_voice(OUT/f"voice/v01/scene-{scene['index']:02d}/Aoede/voice.wav")
        v=v/max(.01,np.max(np.abs(v)))*.82
        a=round(scene['voice_start']*SR);voice[a:a+len(v)]+=v
        old_duck[max(0,a-2400):min(n,a+len(v)+4800)]=.2
    old_music=music_bright(48)*old_duck[:,None]*1.3
    write_pcm(D/'old-mix-reconstructed.wav',voice[:,None]*np.array([1,1])+old_music)
    assert (D/'old-mix-reconstructed.wav').read_bytes()==(OUT/'release/v02/audio-mix.wav').read_bytes()
    with wave.open(str(D/'narration-preserved.wav'),'rb') as f:present=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
    assert np.array_equal(present,(np.clip(voice,-.999,.999)*32767).astype('<i2'))
    with wave.open(str(D/'music-v04.wav'),'rb') as f:music=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,2).astype(np.float32)/32768
    def rms(x):return float(np.sqrt(np.mean(x*x)))
    regions={}
    for name,a,b in [('intro',0,1.4),('body',2,45),('outro',45.8,48)]:
        a=round(a*SR);b=round(b*SR);regions[name]=20*np.log10(rms(music[a:b])/rms(old_music[a:b]))
    video=D/'chatgpt-pro-usage-v04.mp4'
    process=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(video),'-vn','-af','loudnorm=print_format=json','-f','null','-'],check=True,capture_output=True,text=True)
    raw=process.stderr;measure=json.loads(raw[raw.rfind('{'):raw.rfind('}')+1])
    integrated=float(measure['input_i']);peak=float(measure['input_tp'])
    assert -18<=integrated<=-14 and peak<=-1
    p=D/'verification.json';data=json.loads(p.read_text(encoding='utf-8'))
    assert hashlib.sha256(video.read_bytes()).hexdigest()==data['sha256']
    data.update(old_mix_reconstructed_exactly=True,narration_pcm_preserved=True,measured_music_rms_increase_db=regions,
                integrated_lufs=integrated,true_peak_dbtp=peak,loudness_check='within project range; human listening pending')
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(narration_pcm_preserved=True,music_rms_increase_db=regions,integrated_lufs=integrated,true_peak_dbtp=peak)))
if __name__=='__main__':main()
