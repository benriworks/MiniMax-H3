"""Opt-in original sunny loop and three short editorial cues; no external samples."""
import math
import numpy as np

PRESET_ID='sunny_guitar_loop_v1'
CUE_KINDS=frozenset({'reset','bank','improvement'})

def _tone(freq,seconds,sr,gain,decay=7):
    t=np.arange(round(seconds*sr),dtype=np.float64)/sr
    attack=np.minimum(t/.004,1);release=np.minimum((seconds-t)/.025,1)
    signal=sum(np.sin(2*np.pi*freq*k*t)*np.exp(-t*(decay+k))/(k*k) for k in range(1,6))
    return (signal*attack*release*gain).astype(np.float32)

def sunny_loop(*,sample_rate=24000):
    """124 BPM, D major, eight bars. Circular tails make repeated joins continuous."""
    sr=sample_rate;n=round(32*60/124*sr);beat=n/(32*sr)
    track=np.zeros((n,2),dtype=np.float32);rng=np.random.default_rng(20261101)
    chords=[(293.665,369.994,440.,493.883),(293.665,391.995,493.883,587.33),
            (329.628,440.,554.365,659.255),(293.665,369.994,440.,587.33)]
    roots=[73.416,97.999,110.,73.416]
    melody=[(0,587.33),(1.5,739.989),(2.5,880.),(3.5,739.989),
            (4.5,783.991),(6,739.989),(7,587.33),
            (8.5,659.255),(9.5,739.989),(11,880.),
            (12.5,739.989),(14,659.255),(15,587.33)]
    def add(at,sound,pan=0):
        start=round(at*sr)%n;stereo=sound[:,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],dtype=np.float32)
        for offset in range(0,len(sound),n):
            part=stereo[offset:offset+n];count=min(len(part),n-start)
            track[start:start+count]+=part[:count]
            if count<len(part):track[:len(part)-count]+=part[count:]
    for bar in range(8):
        chord=chords[bar%4];root=roots[bar%4]
        for stroke in [0,.75,1.5,2.75,3.5]:
            for j,freq in enumerate(chord):
                add((bar*4+stroke)*beat+j*.009,_tone(freq,.5,sr,.018 if stroke else .023,8),-.28+j*.18)
        for b in [0,1.5,2,3.25]:add((bar*4+b)*beat,_tone(root if b!=3.25 else root*1.5,.38,sr,.043,8),0)
        for b in [0,2]:
            t=np.arange(round(.18*sr))/sr
            kick=np.sin(2*np.pi*(49*t+2.7*(1-np.exp(-t*40))))*np.exp(-t*27)*.045
            add((bar*4+b)*beat,kick)
        for b in [1,3]:
            t=np.arange(round(.105*sr))/sr;noise=rng.normal(0,1,len(t))
            clap=(noise-np.convolve(noise,np.ones(8)/8,mode='same'))*np.exp(-t*48)*.009
            add((bar*4+b)*beat,clap,.1)
        for step in range(8):
            t=np.arange(round(.047*sr))/sr;noise=rng.normal(0,1,len(t))
            shaker=np.concatenate(([0],np.diff(noise)))*np.exp(-t*105)*(.0026 if step%2 else .0018)
            add((bar*4+step*.5+(0.025 if step%2 else 0))*beat,shaker,.35 if step%2 else -.35)
    for offset in [0,16]:
        for pos,freq in melody:
            add((offset+pos)*beat,_tone(freq,.72,sr,.021,5),.28 if int(pos)%2 else -.28)
    # Light stereo echoes also wrap rather than being cut at the loop boundary.
    track+=np.roll(track,round(.19*sr),axis=0)[:,::-1]*.11
    rms=float(np.sqrt(np.mean(track**2)));gain=min(.034/max(rms,1e-8),.19/max(float(np.max(np.abs(track))),1e-8))
    track*=gain
    if not np.isfinite(track).all():raise ValueError('Nonfinite music')
    seam=float(np.max(np.abs(track[0]-track[-1])))
    if seam>.025:raise ValueError('Loop boundary needs repair')
    return track,dict(id=PRESET_ID,bpm=124,key='D major',bars=8,samples=n,sample_rate=sr,seconds=n/sr,seam_jump=seam,rms=float(np.sqrt(np.mean(track**2))),original_composition=True,external_samples=False)

def editorial_cue(kind,*,sample_rate=24000):
    """Reset: click/recharge. Bank: paper/deposit. Improvement: bright two-note tick."""
    if kind not in CUE_KINDS:raise ValueError('Unknown editorial cue')
    sr=sample_rate;n=round(.52*sr);result=np.zeros(n,dtype=np.float32)
    rng=np.random.default_rng({'reset':31,'bank':41,'improvement':51}[kind])
    def add(at,sound):
        start=round(at*sr);length=min(len(sound),n-start)
        if length>0:result[start:start+length]+=sound[:length]
    if kind=='reset':
        t=np.arange(round(.075*sr))/sr;noise=rng.normal(0,1,len(t))
        add(0,(np.sin(2*np.pi*155*t)*np.exp(-t*65)+noise*.3*np.exp(-t*125))*.07)
        t=np.arange(round(.29*sr))/sr
        add(.11,np.sin(2*np.pi*(430*t+1000*t*t))*np.sin(np.pi*np.minimum(t/.018,1)/2)*np.exp(-t*13)*.043)
    elif kind=='bank':
        t=np.arange(round(.16*sr))/sr;noise=rng.normal(0,1,len(t))
        paper=noise-np.convolve(noise,np.ones(14)/14,mode='same')
        add(0,paper*np.sin(np.linspace(0,np.pi,len(t)))**2*.012)
        add(.18,_tone(310,.23,sr,.085,15));add(.21,_tone(620,.23,sr,.028,14))
    else:
        add(0,_tone(880.,.22,sr,.071,15));add(.075,_tone(1174.66,.28,sr,.056,14))
    result[:round(.002*sr)]*=np.linspace(0,1,round(.002*sr))
    result[-round(.025*sr):]*=np.linspace(1,0,round(.025*sr))
    if not np.isfinite(result).all() or np.max(np.abs(result))>.3:raise ValueError('Invalid cue headroom')
    return np.column_stack([result,result])
