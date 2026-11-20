"""Original score '返事を待つ朝' in D minor, with two arrangements timed to the edit."""
from functools import lru_cache
import math
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt
from tools.studio.longform_audio import SR, read_voice, write_pcm
from tools.studio.music_mix import default_bgm_bed

TITLE = "返事を待つ朝"
PROGRESSION = [(50,(57,60,64,65)),(46,(53,57,60,62)),(53,(57,60,64,67)),(48,(55,58,62,64)),
               (50,(53,57,60,64)),(43,(53,55,58,62)),(46,(53,57,60,65)),(45,(52,55,61,64))]
MOTIF = [(0,0),(.75,2),(1.50,1),(3,3)]
ANSWER = [(.5,3),(1.50,1),(2.75,0)]

@lru_cache(maxsize=480)
def note(kind, midi, length):
    t=np.arange(round(length*SR))/SR
    f=440*2**((midi-69)/12)
    ph=2*np.pi*f*t
    if kind=="reed":
        sig=(np.sin(ph+.23*np.sin(ph*2.01))+.24*np.sin(2*ph+.08*np.sin(ph)))
        env=np.minimum(t/.085,1)*np.minimum((length-t)/.17,1)*np.exp(-.65*t)
    elif kind=="keys":
        sig=np.sin(ph+.84*np.exp(-t*6)*np.sin(2*ph))+.27*np.sin(2.003*ph)+.10*np.sin(3.997*ph)*np.exp(-3*t)
        env=np.minimum(t/.009,1)*np.exp(-3.1*t)*np.minimum((length-t)/.09,1)
    elif kind=="wood":
        sig=np.sin(ph)+.37*np.sin(2.76*ph)*np.exp(-12*t)+.16*np.sin(3.99*ph)*np.exp(-10*t)
        env=np.minimum(t/.004,1)*np.exp(-6*t)*np.minimum((length-t)/.07,1)
    elif kind=="bass":
        sig=np.tanh(1.15*(np.sin(ph)+.35*np.sin(2*ph)+.11*np.sin(3*ph)))
        env=np.minimum(t/.018,1)*np.exp(-1.3*t)*np.minimum((length-t)/.13,1)
    else: raise ValueError(kind)
    return (sig*env).astype(np.float32)

def make_score(plan, edition):
    duration=plan["seconds"]
    n=round(duration*SR)
    out=np.zeros((n,2),np.float32)
    rng=np.random.default_rng(110319 if edition=="short" else 111926)
    beat=60/(100 if edition=="short" else 92)
    marks={ch["id"]:ch["start"] for ch in plan["chapters"]}
    cascade=marks["chain" if edition=="short" else "cascade"]
    repair=marks["repair" if edition=="short" else "fix"]
    end_start=marks["time" if edition=="short" else "keynote"]
    def add(at,sample,gain,pan=0.):
        offset=round(at*SR)
        left=min(len(sample),n-offset)
        if left<=0 or offset<0:return
        out[offset:offset+left]+=sample[:left,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],np.float32)*gain
    def instrument(kind,midi,at,length,amp,pan=0):
        add(at,note(kind,midi,round(length,3)),amp,pan)
    t=np.arange(round(.24*SR))/SR
    kick=(np.sin(2*np.pi*(48*t+1.35*(1-np.exp(-27*t))))*np.exp(-23*t)*np.minimum(t/.002,1)).astype(np.float32)
    noise=sosfilt(butter(3,[1800,5400],fs=SR,btype="bandpass",output="sos"),rng.normal(size=round(.17*SR)))
    brush=(noise*np.exp(-np.arange(len(noise))/(SR*.035))).astype(np.float32)
    for bar in range(math.ceil(duration/(beat*4))):
        start=bar*4*beat
        root,chord=PROGRESSION[bar%8]
        crowded=cascade<=start<repair
        release=start>=repair
        if start>=end_start and duration-start<beat*8:
            root,chord=(50,(53,57,62,65))
        for i,pitch in enumerate(chord):
            instrument("keys",pitch,start+.025*i,1.9*beat,.053 if not crowded else .041,(i-1.5)*.33)
        instrument("bass",root-12,start,1.5*beat,.115)
        if bar%2 or crowded:instrument("bass",root-5,start+2.52*beat,.78*beat,.07,.04)
        for d,idx in (MOTIF if bar%2==0 else ANSWER):
            if not crowded and edition=="full" and bar%8 in (5,7):continue
            pitch=chord[idx]+12
            instrument("wood",pitch,start+d*beat,.63,.078 if bar%4==0 else .060,(-.23 if idx%2 else .33))
        if start>beat*4 and start<duration-beat*4:
            for d in ([0,2.5] if crowded else [0]):
                add(start+d*beat,kick,.078)
            for d in ([.5,1.5,2,2.75,3.5] if crowded else [1,3]):
                add(start+d*beat+rng.uniform(0,.012),brush,.024 if crowded else .018,.38 if d>2 else -.36)
        if release and bar%2==0:
            instrument("reed",chord[2],start+.5*beat,1.55*beat,.039,-.42)
    # A short stereo room reflection on the complete ensemble; a scored tonic at the sign-off.
    delay=round(.103*SR)
    out[delay:]+=out[:-delay,::-1]*.105
    for i,pitch in enumerate((50,57,62,65)):
        instrument("keys",pitch,duration-1.1+i*.04,.97-i*.04,.065,(i-1.5)*.24)
    fade=round(.28*SR);out[-fade:]*=np.linspace(1,0,fade)[:,None]
    rms=np.sqrt(np.mean(out**2));out*=.087/max(.001,rms)
    return out

def mix(plan, folder, edition):
    stem=make_score(plan, edition)
    write_pcm(folder/"music-original.wav",stem)
    spans=[(t["start"],t["end"]) for c in plan["chapters"] for t in c["turns"]]
    bed=default_bgm_bed(stem,plan["seconds"],spans,sample_rate=SR)
    narration=np.zeros(len(stem),np.float32)
    mask=np.zeros(len(stem),bool)
    for c in plan["chapters"]:
        for t in c["turns"]:
            source=read_voice(Path(t["voice_path"]))
            i=round(t["start"]*SR)
            narration[i:i+len(source)]=source
            mask[i:i+len(source)]=True
    ratio=20*math.log10(np.sqrt(np.mean(narration[mask]**2))/np.sqrt(np.mean(bed[mask]**2)))
    master=bed+narration[:,None]
    master*=min(1,.92/float(np.max(np.abs(master))))
    write_pcm(folder/"mix-premaster.wav",master)
    return {"title":TITLE,"arrangement":edition,"bpm":100 if edition=="short" else 92,"duck_profile":"explanation_v1",
            "new_composition":True,"external_samples":False,"speech_over_bed_rms_db":round(ratio,2)}
