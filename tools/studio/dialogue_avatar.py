"""Voice-gated sprite mouths and reserved-area presenter policy.

This is simple audio-envelope animation, not phoneme-accurate lip synchronization.
Raster mouth states are supplied by generated artwork; the original images remain intact.
"""
from pathlib import Path
import math,wave
import numpy as np
from PIL import Image,ImageDraw,ImageFilter

EMOTIONS=('neutral','curious','worried','serious','pleased')


def validate_windows(windows,duration,protected=()):
    previous=0
    for window in windows:
        start,end=window['start'],window['end']
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (start,end)):
            raise ValueError('Invalid presenter interval')
        if start<previous or not 0<=start<end<=duration:
            raise ValueError('Presenter intervals overlap or exceed video')
        if any(max(start,a)<min(end,b) for a,b in protected):
            raise ValueError('Presenter interval covers protected real operation')
        if any(window[s] not in EMOTIONS for s in ('male','female')):
            raise ValueError('Unknown emotion')
        previous=end
    return True


def voice_gate(path,fps=24):
    """Use actual PCM activity; a quiet frame and a listening person stay closed."""
    with wave.open(str(path),'rb') as f:
        if f.getsampwidth()!=2:raise ValueError('Expected PCM16 voice')
        rate=f.getframerate();channels=f.getnchannels()
        samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32).reshape(-1,channels).mean(axis=1)/32768
    if not len(samples):raise ValueError('Empty voice')
    energy=[]
    for frame in range(math.ceil(len(samples)/rate*fps)):
        a=round(frame*rate/fps);b=min(len(samples),round((frame+1)*rate/fps))
        energy.append(float(np.sqrt(np.mean(samples[a:b]**2))) if b>a else 0)
    threshold=max(.009,float(np.percentile(energy,75))*.23)
    gates=[];last=False
    for rms in energy:
        # Hysteresis reduces jitter without moving the mouth through true silence.
        last=rms>threshold*(.58 if last else 1)
        gates.append(bool(last))
    return dict(fps=fps,threshold=threshold,energy=energy,gates=gates,seconds=len(samples)/rate)


class DialogueDriver:
    def __init__(self,turns,fps=24):
        self.turns=turns;self.fps=fps
        self.gates={str(t['voice_path']):voice_gate(t['voice_path'],fps) for t in turns}
        for a,b in zip(turns,turns[1:]):
            if a['end']>b['start']+.00001:raise ValueError('Speaking turns overlap')

    def state(self,seconds,speaker):
        if speaker not in ('male','female'):raise ValueError('Unknown speaker')
        for turn in self.turns:
            if turn['start']<=seconds<turn['end'] and turn['speaker']==speaker:
                gate=self.gates[str(turn['voice_path'])]
                i=int((seconds-turn['start'])*self.fps)
                opened=gate['gates'][i] if i<len(gate['gates']) else False
                return dict(speaking=True,opened=opened,emotion=turn.get('emotion','neutral'))
        return dict(speaking=False,opened=False,emotion=None)


def registered_translation(reference,source,limit=12):
    """Integer registration only; do not warp or regenerate a face."""
    a=np.asarray(reference.convert('L'),dtype=np.float32)
    b=np.asarray(source.convert('L'),dtype=np.float32)
    fa=np.fft.fft2(a-a.mean());fb=np.fft.fft2(b-b.mean())
    product=fa*np.conj(fb);product/=np.maximum(np.abs(product),1e-8)
    y,x=np.unravel_index(np.argmax(np.abs(np.fft.ifft2(product))),product.shape)
    if y>a.shape[0]//2:y-=a.shape[0]
    if x>a.shape[1]//2:x-=a.shape[1]
    if abs(x)>limit or abs(y)>limit:return source,(0,0)
    aligned=reference.copy();aligned.paste(source,(int(x),int(y)))
    return aligned,(int(x),int(y))


def mouth_patch(closed,opened,normalized_box):
    w,h=closed.size
    box=tuple(round(v*(w if i%2==0 else h)) for i,v in enumerate(normalized_box))
    region=opened.crop(box)
    mask=Image.new('L',region.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((2,2,region.width-3,region.height-3),radius=8,fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(2))
    result=closed.copy();result.paste(region,box[:2],mask)
    return result


class SpriteAtlas:
    def __init__(self,path,speaker):
        sheet=Image.open(path).convert('RGB')
        if abs(sheet.width/2-sheet.height/5)>3:raise ValueError('Expected a two-column five-row atlas')
        self.poses={};self.registration=[]
        # Artwork-specific safe mouth region: excludes the eyes and eyebrows.
        bounds=(.47,.67,.63,.80) if speaker=='male' else (.47,.60,.625,.755)
        for row,emotion in enumerate(EMOTIONS):
            frames=[]
            for column in range(2):
                b=(round(column*sheet.width/2),round(row*sheet.height/5),round((column+1)*sheet.width/2),round((row+1)*sheet.height/5))
                frames.append(sheet.crop(b).resize((400,400),Image.Resampling.LANCZOS))
            aligned,shift=registered_translation(frames[0],frames[1],limit=32)
            self.registration.append(dict(emotion=emotion,shift=shift))
            self.poses[emotion]=(frames[0],mouth_patch(frames[0],aligned,bounds))

    def frame(self,emotion,opened,size=300):
        if emotion not in EMOTIONS:raise ValueError('Unknown emotion')
        return self.poses[emotion][bool(opened)].resize((size,size),Image.Resampling.LANCZOS)


class PairAtlas:
    def __init__(self,path):
        sheet=Image.open(path).convert('RGB')
        h=sheet.height//3
        if abs(sheet.width/h-16/9)>.01:raise ValueError('Expected three 16:9 dialogue panels')
        closed=sheet.crop((0,0,sheet.width,h))
        male=sheet.crop((0,h,sheet.width,2*h));female=sheet.crop((0,2*h,sheet.width,3*h))
        male,ms=registered_translation(closed,male)
        female,fs=registered_translation(closed,female)
        self.states={None:closed,'male':mouth_patch(closed,male,(.353,.292,.421,.367)),
            'female':mouth_patch(closed,female,(.585,.418,.655,.500))}
        self.registration=dict(male=ms,female=fs)

    def frame(self,opened_speaker):
        return self.states[opened_speaker]
