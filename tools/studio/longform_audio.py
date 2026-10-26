"""Sample-accurate dialogue layout and an original, ducked explanation music bed."""
import math
import wave
from pathlib import Path
import numpy as np

SR = 24000


def read_voice(path):
    with wave.open(str(path), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, SR):
            raise ValueError('Expected verified 24kHz mono PCM')
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32) / 32768


def plan_dialogue(chapters, voice_root, fps=24):
    """Keep every spoken sample and allocate only extra visual holds, never trim speech."""
    plan, offset = [], 0
    for chapter in chapters:
        voices = [read_voice(Path(voice_root) / chapter['id'] / f'turn-{i:02d}' / 'voice.wav') for i in range(len(chapter['turns']))]
        lengths = [len(v)/SR for v in voices]
        tail = chapter.get('tail_seconds', .5)
        minimum = sum(lengths) + .35 * (len(voices)-1) + .5 + tail
        frames = math.ceil(max(chapter['target_seconds'], minimum) * fps)
        seconds = frames / fps
        spare = seconds - sum(lengths) - .35 * (len(voices)-1)
        cursor = offset + .5
        turns = []
        gap_weights=[1 if chapter['turns'][i]['speaker']=='female' else 0 for i in range(len(voices)-1)]
        if chapter.get('pause_mode')!='after_answer':gap_weights=[1]*(len(voices)-1)
        for i, (turn, length) in enumerate(zip(chapter['turns'], lengths, strict=True)):
            turns.append(dict(turn, start=cursor, end=cursor+length, voice_path=str(Path(voice_root) / chapter['id'] / f'turn-{i:02d}' / 'voice.wav')))
            cursor += length + .35
            # Give longer chapters deliberate reading space between the turns.
            if i < len(voices)-1:
                cursor += max(0, spare-.5-tail)*gap_weights[i]/max(1,sum(gap_weights))
        assert turns[-1]['end'] <= offset + seconds + .00001
        plan.append(dict(id=chapter['id'], title=chapter['title'], start=offset, end=offset+seconds, frames=frames, turns=turns))
        offset += seconds
    return dict(fps=fps, seconds=offset, frames=round(offset*fps), chapters=plan, alignment='Turn boundaries from PCM samples; subtitle phrases weighted by character count.')


def write_pcm(path, samples):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((samples.shape[1] if samples.ndim==2 else 1, 2, SR, 0, 'NONE', 'not compressed'))
        stream.writeframes((np.clip(samples, -.999, .999)*32767).astype('<i2').tobytes())


def music(seconds):
    """Original 88 BPM piano-like plucks/pads; no samples or external music."""
    n = round(seconds*SR)
    result = np.zeros((n,2), dtype=np.float32)
    beat = 60/88
    chords = [(146.83,185.00,220.,277.18), (123.47,146.83,185.,220.),
              (98.,146.83,185.,246.94), (110.,164.81,220.,277.18)]
    def add(start, sound, pan=0):
        a=round(start*SR); count=min(len(sound), n-a)
        if a<0 or count<=0:return
        result[a:a+count] += sound[:count,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],dtype=np.float32)
    for bar in range(math.ceil(seconds/(beat*4))):
        chord=chords[(bar//2)%4]
        t=np.arange(round(beat*4.5*SR),dtype=np.float32)/SR
        env=np.minimum(t/.45,1)*np.minimum(np.maximum(0,beat*4.5-t)/.8,1)
        pad=sum(np.sin(2*np.pi*f*t) for f in chord)/4*env*.065
        add(bar*beat*4,pad)
        for step in range(4):
            q=np.arange(round(1.1*SR),dtype=np.float32)/SR
            freq=chord[(step+bar)%4]*2
            bell=(np.sin(2*np.pi*freq*q)+.20*np.sin(2*np.pi*freq*2*q))*np.minimum(q/.012,1)*np.exp(-q*5)*.055
            add((bar*4+step)*beat,bell,(-1 if step%2 else 1)*.35)
        q=np.arange(round(.28*SR),dtype=np.float32)/SR
        kick=np.sin(2*np.pi*(48*q+2.3*(1-np.exp(-q*35))))*np.exp(-q*24)*.045
        add(bar*beat*4,kick)
        add((bar*4+2)*beat,kick*.6)
    result *= np.minimum(np.arange(n)/SR/.8,1)[:,None]
    result *= np.minimum((n-np.arange(n))/SR/3,1)[:,None]
    return result


def music_bright(seconds):
    """Original C-major 112 BPM plucked chords, marimba-like notes and soft shaker."""
    n=round(seconds*SR);result=np.zeros((n,2),dtype=np.float32);beat=60/112
    rng=np.random.default_rng(20261026)
    chords=[(130.8128,164.8138,195.9977),(174.6141,220.,261.6256),
        (195.9977,246.9417,293.6648),(130.8128,164.8138,195.9977)]
    def add(at,sound,pan=0):
        a=round(at*SR);count=min(len(sound),n-a)
        if a<0 or count<=0:return
        result[a:a+count]+=sound[:count,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)],dtype=np.float32)
    def pluck(freq,seconds,gain):
        t=np.arange(round(seconds*SR),dtype=np.float32)/SR
        sound=sum(np.sin(2*np.pi*freq*k*t)*np.exp(-t*(4+k))/(k*k) for k in range(1,5))
        return sound*np.minimum(t/.008,1)*gain
    for bar in range(math.ceil(seconds/(beat*4))):
        chord=chords[bar%4]
        for step in range(8):
            at=(bar*4+step/2)*beat
            note=chord[step%3]*2
            add(at,pluck(note,.65,.045 if step%2==0 else .029),.2 if step%2 else -.2)
            q=np.arange(round(.065*SR),dtype=np.float32)/SR
            noise=rng.normal(0,1,len(q)).astype(np.float32)
            bright=np.concatenate([[0],np.diff(noise)])
            add(at,bright*np.exp(-q*85)*.0045,(-1 if step%2 else 1)*.35)
        add(bar*4*beat,pluck(chord[0],.7,.055))
        add((bar*4+2)*beat,pluck(chord[0]*1.5,.6,.04))
        if bar%2==0:
            for offset,freq in [(1,523.251),(2.5,659.255),(3.5,783.991)]:
                add((bar*4+offset)*beat,pluck(freq,.55,.018),.12)
    result*=np.minimum(np.arange(n)/SR/.7,1)[:,None]
    result*=np.minimum((n-np.arange(n))/SR/3,1)[:,None]
    return result


def assemble_audio(plan, out, *, music_style='calm'):
    if music_style not in {'calm','bright'}:raise ValueError('Unknown music profile')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    n=round(plan['seconds']*SR)
    narration=np.zeros(n,dtype=np.float32)
    duck=np.ones(n,dtype=np.float32)
    for chapter in plan['chapters']:
        for turn in chapter['turns']:
            samples=read_voice(turn['voice_path'])
            a=round(turn['start']*SR);b=a+len(samples)
            if b>n:raise ValueError('Speech exceeds the timeline')
            narration[a:b] += samples
            # Duck 7 dB under each voice with gentle 120 ms ramps.
            lo=max(0,a-round(.12*SR));hi=min(n,b+round(.2*SR))
            gain=.32 if music_style=='bright' else .45
            env=np.ones(hi-lo,dtype=np.float32)*gain
            if a>lo:env[:a-lo]=np.linspace(1,gain,a-lo)
            if hi>b:env[b-lo:]=np.linspace(gain,1,hi-b)
            duck[lo:hi]=np.minimum(duck[lo:hi],env)
    bgm=music_bright(plan['seconds']) if music_style=='bright' else music(plan['seconds'])
    write_pcm(out/'narration.wav',narration)
    write_pcm(out/'music-original.wav',bgm)
    # The stem remains separate; normalize the final mix with measured loudnorm.
    mixed=narration[:,None]*np.ones((1,2),dtype=np.float32)+bgm*duck[:,None]
    peak=float(np.max(np.abs(mixed)))
    if peak>.96:mixed*=.96/peak
    write_pcm(out/'mix-premaster.wav',mixed)
    return dict(original_music=True,bpm=112 if music_style=='bright' else 88,samples=n,sample_rate=SR,
        duck_gain=.32 if music_style=='bright' else .45,peak_before_normalization=peak,
        music_style=music_style,tonality='C major' if music_style=='bright' else 'original calm progression')
