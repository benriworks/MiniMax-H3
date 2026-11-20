"""Build, preflight, render and independently measure either member of the review pair."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from frames import CAPSIZE, CAPWIDTH
from incident_score import mix
from pair_edit import FULL, SHORT, cast_in, cut
from pair_frames import Edition
from produce import caption, command, digest, loudness, PROTECT, save, srt_time
from tools.studio.editorial_captions import timed_captions
from tools.studio.longform_audio import plan_dialogue

HERE=Path(__file__).resolve().parent
FPS=24

def read(path):return json.loads(path.read_text(encoding="utf-8"))

def editorial(media,edition):
    extra=read(HERE/"dialogue-pair.json")
    if edition=="short":
        story=extra[:-1]
    else:
        v2=read(HERE/"revision-v02.json")
        story=[s|({"display":v2[s["id"]]["display"]} if s["id"] in v2 else {}) for s in read(HERE/"story-v01.json")]+extra[-1:]
    chapters=[]
    for s in story:
        voice=s.get("voice_take","pair-v03") if edition=="short" or s["id"]=="keynote" else "selected-v02"
        tail=1.05 if s==story[-1] else .28
        stage=dict(id=s["id"],title=s["title"],target_seconds=0,tail_seconds=tail,turns=[dict(speaker=s["speaker"],text=s["display"])])
        c=plan_dialogue([stage],media/"voice"/voice,fps=FPS)["chapters"][0]
        if edition=="short":
            # Less empty time between short exchanges, without trimming the PCM.
            lead=.12
            voice_length=c["turns"][0]["end"]-c["turns"][0]["start"]
            c["frames"]=math.ceil((lead+voice_length+(.75 if s==story[-1] else .14))*FPS)
            c["turns"][0].update(start=lead,end=lead+voice_length)
        start=sum(old["frames"] for old in chapters)/FPS
        c["start"]=start;c["end"]=start+c["frames"]/FPS
        t=c["turns"][0];t["start"]+=start;t["end"]+=start
        c["captions"]=timed_captions(s["display"],t["start"],t["end"]-t["start"],829 if edition=="short" else CAPWIDTH,
                                   53 if edition=="short" else CAPSIZE,protected=(*PROTECT,"ナデラCEO","23時間50分"))
        chapters.append(c)
    frames=sum(c["frames"] for c in chapters)
    return story,dict(fps=FPS,frames=frames,seconds=frames/FPS,chapters=chapters)

def state(edition,scene,c,idx):
    when=idx/FPS
    cue,mode,arg=cut(edition,scene["id"],when)
    ft=max(0,idx-round(cue*FPS))
    # Begin mid-reaction at the second hero cut, instead of rewinding both figures.
    if mode=="hero" and cue:ft+=30
    pose=min(59,1+ft//2)
    cues=(SHORT if edition=="short" else FULL)[scene["id"]]
    following=next((z[0] for z in cues if z[0]>cue),c["frames"]/FPS)
    fraction=(when-cue)/max(.05,following-cue)
    phase=min(2,int(3*fraction)) if mode=="network" else min(2,int(3*idx/c["frames"]))
    if mode not in ("solo","duo","hero"):pose=1
    dyn=ft//2%24 if mode=="network" else 0
    return cue,mode,arg,pose,dyn,phase

def preflight(media,edition,story,plan,art):
    folder=media/"preflight"/("short-v01" if edition=="short" else "v03")
    folder.mkdir(exist_ok=True,parents=True)
    thumb=(216,384) if edition=="short" else (360,203)
    rows=[]
    counts=Counter()
    for i,(s,c) in enumerate(zip(story,plan["chapters"])):
        samples={}
        for j in range(c["frames"]):
            q,mode,arg,_,_,_=state(edition,s,c,j)
            for who in cast_in(mode,arg):counts[who]+=1
            samples.setdefault((q,mode,arg),j)
        for ix,(key,first) in enumerate(samples.items()):
            next_f=list(samples.values())[ix+1] if ix+1<len(samples) else c["frames"]
            f=first+min(round(2*FPS),max(0,(next_f-first)//2))
            q,mode,arg,pose,dyn,ph=state(edition,s,c,f)
            im=art.layout(i,mode,arg,pose,dyn,ph,f/FPS)
            art.subtitle(im,caption(c,c["start"]+f/FPS))
            im.save(folder/(f"{i:02d}-{ix:02d}-{s['id']}.jpg"),quality=88)
            rows.append(im.resize(thumb,Image.Resampling.LANCZOS))
        for page in c["captions"]:
            blank=Image.new("RGB",(art.w,art.h));art.subtitle(blank,page["text"])
    for k in range(0,len(rows),21 if edition=="full" else 12):
        group=rows[k:k+(21 if edition=="full" else 12)]
        cols=3 if edition=="full" else 4
        sheet=Image.new("RGB",(cols*thumb[0],math.ceil(len(group)/cols)*thumb[1]),"#496269")
        for j,tile in enumerate(group):sheet.paste(tile,((j%cols)*thumb[0],(j//cols)*thumb[1]))
        sheet.save(folder/f"board-{k:02d}.jpg",quality=90)
    counts=dict((k,round(v/FPS,3)) for k,v in counts.items())
    save(folder/"preflight.json",dict(cast_seconds=counts,checks=len(art.canvas.audit)+len(art.old.canvas.audit),cuts=len(rows)))
    print(edition,round(plan["seconds"],3),counts,len(rows),flush=True)
    return counts

def normalized(media,folder,edition,plan):
    # Stems are local working material. Rerunning a failed encode reuses the same mix.
    audio=folder/"normalized.wav";receipt=folder/"score.json"
    if audio.exists() and receipt.exists():return audio,read(receipt)
    facts=mix(plan,folder,edition)
    raw=folder/"mix-premaster.wav";meter=loudness(raw)
    spec=("loudnorm=I=-16:TP=-1.8:LRA=10:linear=true:"
          f"measured_I={meter['input_i']}:measured_TP={meter['input_tp']}:measured_LRA={meter['input_lra']}:"
          f"measured_thresh={meter['input_thresh']}:offset={meter['target_offset']}")
    command("ffmpeg","-v","error","-nostdin","-y","-i",raw,"-af",spec,"-ar","48000",audio)
    save(receipt,facts)
    return audio,facts

def render(media,edition,story,plan,art):
    version="short-v01" if edition=="short" else "v03"
    folder=media/"release"/version;folder.mkdir(exist_ok=True,parents=True)
    audio,facts=normalized(media,folder,edition,plan)
    dest=folder/("microsoft365-outage-short-v01.mp4" if edition=="short" else "microsoft365-outage-full-v03.mp4")
    if dest.exists():raise FileExistsError(dest)
    working=folder/("."+dest.name)
    # A cut may land on an odd frame. Keep the speech and subtitle clock at 24 fps throughout.
    args=["ffmpeg","-nostdin","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-video_size",f"{art.w}x{art.h}",
          "-framerate",str(FPS),"-i","pipe:0","-i",str(audio),"-map","0:v","-map","1:a","-c:v","libx264","-preset","veryfast","-crf","19","-threads","6",
          "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",str(working)]
    counts=Counter();ncut=0
    with subprocess.Popen(args,stdin=subprocess.PIPE) as enc:
        try:
            for i,(s,c) in enumerate(zip(story,plan["chapters"])):
                prev=None;previous_layout=None;wiping=None;last=None;last_base=None
                for j in range(c["frames"]):
                    cue,mode,arg,pose,dyn,phase=state(edition,s,c,j)
                    for name in cast_in(mode,arg):counts[name]+=1
                    bkey=(cue,mode,arg,pose,dyn,phase)
                    if bkey!=last_base:
                        if previous_layout!=(cue,mode,arg):
                            ncut+=1
                            wiping=prev if j else None
                            previous_layout=(cue,mode,arg)
                        base=art.layout(i,mode,arg,pose,dyn,phase,j/FPS)
                        last_base=bkey
                    point=j-round(cue*FPS)
                    active=wiping is not None and 0<=point<5
                    cap=caption(c,c["start"]+j/FPS)
                    key=(bkey,cap,point if active else -1)
                    if key!=last:
                        img=base.copy()
                        if active:
                            step=(point+1)/6
                            x=round(art.w*step*step*(3-2*step))
                            img.paste(wiping.crop((x,0,art.w,art.h)),(x,0))
                        art.subtitle(img,cap)
                        raw=img.tobytes();last=key
                    enc.stdin.write(raw)
                    prev=base
                print(edition,s["id"],round(c["end"],1),flush=True)
        finally:
            enc.stdin.close()
        if enc.wait():raise RuntimeError("FFmpeg encode failed")
    command("ffmpeg","-nostdin","-loglevel","error","-xerror","-i",working,"-f","null","-")
    probe=json.loads(command("ffprobe","-v","error","-show_format","-show_streams","-of","json",working).stdout)
    v,a=probe["streams"]
    assert (v["width"],v["height"],v["codec_name"],a["codec_name"],int(v["nb_frames"]))==(art.w,art.h,"h264","aac",plan["frames"])
    assert abs(float(a["duration"])-plan["seconds"])<.055
    m=loudness(working)
    assert -18<=float(m["input_i"])<=-14 and float(m["input_tp"])<=-1,m
    pages=[page for c in plan["chapters"] for page in c["captions"]]
    (folder/"captions.srt").write_text("\n\n".join(f"{i}\n{srt_time(page['start'])} --> {srt_time(page['end'])}\n{page['text']}" for i,page in enumerate(pages,1))+"\n",encoding="utf-8")
    for c in plan["chapters"]:
        for t in c["turns"]:t["voice_path"]=Path(t["voice_path"]).relative_to(media).as_posix()
    save(folder/"timeline.json",plan)
    working.rename(dest)
    save(folder/"verification.json",dict(file=dest.name,sha256=digest(dest),bytes=dest.stat().st_size,dimensions=[art.w,art.h],
         fps=FPS,seconds=plan["seconds"],frames=plan["frames"],captions=len(pages),cuts=ncut,cast_seconds={k:round(v/FPS,3) for k,v in counts.items()},
         loudness_lufs=float(m["input_i"]),true_peak_dbtp=float(m["input_tp"]),score=facts,full_decode=True,user_accepted=False,published=False))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["preview","render"])
    parser.add_argument("edition",choices=["full","short"])
    parser.add_argument("media",type=Path)
    args=parser.parse_args();media=args.media.resolve()
    story,plan=editorial(media,args.edition)
    art=Edition(media,story,args.edition=="short")
    if args.action=="preview":preflight(media,args.edition,story,plan,art)
    else:render(media,args.edition,story,plan,art)
