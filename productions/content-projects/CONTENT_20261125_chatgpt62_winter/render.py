"""Plan, preflight, render and decode a winter episode in each aspect ratio."""
import argparse
import bisect
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from art import Board, NAVY, WHITE, xy
from tools.studio.editorial_captions import PROTECTED,timed_captions
from tools.studio.longform_audio import assemble_audio,read_voice

FPS=24
KEEP=PROTECTED+("GPT-6.2 Sol","GPT-6.2","GPT-6","6.2 Instant","22,000円","23,600円","11,800円","10,400円","1,600円","600円","雪灯り館","駅前館","47.4%","71.7%","62.5%","78.1%","OpenAI","Enterprise","Business","Instant")
def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def probe(*args):
    return subprocess.check_output([str(v) for v in args],stderr=subprocess.STDOUT,encoding="utf-8",errors="replace")
def meter(path):
    result=probe("ffmpeg","-nostdin","-hide_banner","-i",path,"-vn","-af","loudnorm=I=-16:LRA=10:TP=-1.8:print_format=json","-f","null","-")
    return json.loads(result[result.rfind("{"):result.rfind("}")+1])

def stamp(seconds):
    v=round(seconds*1000)
    return f"{v//3600000:02}:{v//60000%60:02}:{v//1000%60:02},{v%1000:03}"

def make_plan(media,kind):
    short=kind=="short"
    story=json.loads((HERE/"dialogue.json").read_text(encoding="utf-8"))
    facts={r["id"]:r for r in story["lines"]}
    chapters=[]
    frame=0
    for index,key in enumerate(story[kind]):
        src=facts[key]
        path=media/"voice"/src.get("voice_take",key)/"turn-00/voice.wav"
        wav=read_voice(path)
        seconds=len(wav)/24000
        lead=.1 if short else .18
        tail=.9 if key==story[kind][-1] else (.18 if short else .37)
        n=math.ceil((seconds+lead+tail)*FPS)
        start=frame/FPS
        turn=dict(speaker=src["speaker"],text=src["display"],start=start+lead,end=start+lead+seconds,voice_path=str(path))
        c=dict(src,start=start,end=(frame+n)/FPS,frames=n,turns=[turn])
        c["captions"]=timed_captions(src["display"],turn["start"],seconds,round(552*1.5) if short else round(1067*1.5),44 if short else 39,protected=KEEP)
        c["cut"]=round(n*(.43 if key in ("s5","s4","checkb") else .51))
        chapters.append(c)
        frame+=n
    return dict(fps=FPS,seconds=frame/FPS,frames=frame,chapters=chapters)

def stage(media,kind):
    d=media/"release/v01"/kind
    d.mkdir(parents=True,exist_ok=True)
    board=Board(kind=="short",media)
    return d,board,make_plan(media,kind)

def compose(board,c,phase,cap):
    base,moves=board.plate(c,phase)
    board.im=base
    board.d=ImageDraw.Draw(base)
    board.subtitle(cap,c["speaker"])
    return cv2.cvtColor(np.asarray(base),cv2.COLOR_RGB2BGR),moves

def preflight(media,kind):
    target,board,plan=stage(media,kind)
    output=target/"preflight"
    output.mkdir(exist_ok=True)
    previews=[]
    for c in plan["chapters"]:
        for phase in (0,1):
            part=c["captions"][0 if not phase else -1]
            frame,moves=compose(board,c,phase,part["text"])
            board.motion_frame(frame,moves,16 if not phase else c["cut"])
            im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            thumb=(155,275) if kind=="short" else (280,158)
            previews.append(im.resize(thumb,Image.Resampling.LANCZOS))
        for page in c["captions"]:
            board.subtitle(page["text"],c["speaker"])
    cols=4
    for page,a in enumerate(range(0,len(previews),16)):
        items=previews[a:a+16]
        canvas=Image.new("RGB",(thumb[0]*cols,thumb[1]*math.ceil(len(items)/cols)),NAVY)
        for i,im in enumerate(items): canvas.paste(im,(i%cols*thumb[0],i//cols*thumb[1]))
        canvas.save(output/f"montage-{page}.jpg",quality=92)
    return target,board,plan

def deliver(media,kind):
    target,board,plan=preflight(media,kind)
    dest=target/f"chatgpt62-chat-{kind}-v01.mp4"
    if dest.exists(): raise FileExistsError(dest)
    save(target/"timeline.json",plan)
    pages=[p for c in plan["chapters"] for p in c["captions"]]
    (target/"captions.srt").write_text("\n\n".join(f"{i+1}\n{stamp(p['start'])} --> {stamp(p['end'])}\n{p['text']}" for i,p in enumerate(pages))+"\n",encoding="utf-8-sig")
    audio=target/"mix-48k.wav"
    if not audio.exists():
        profile=assemble_audio(plan,target,music_style="bright" if kind=="short" else "calm",bgm_mix_profile="explanation_v1")
        raw=target/"mix-premaster.wav"
        measurements=meter(raw)
        filt=("loudnorm=I=-16:TP=-1.8:LRA=10:linear=true:"
          f"measured_I={measurements['input_i']}:measured_TP={measurements['input_tp']}:measured_LRA={measurements['input_lra']}:"
          f"measured_thresh={measurements['input_thresh']}:offset={measurements['target_offset']}")
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-i",str(raw),"-af",filt,"-ar","48000",str(audio)],check=True)
        save(target/"music.json",profile)
    work=target/("working-"+dest.name)
    width,height=xy(board.w,board.h)
    cmd=["ffmpeg","-nostdin","-v","error","-y","-f","rawvideo","-pix_fmt","bgr24","-s",f"{width}x{height}","-r",str(FPS),"-i","pipe:0","-i",str(audio),"-map","0:v","-map","1:a","-c:v","libx264","-preset","veryfast","-crf","18","-threads","5","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",str(work)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
        for c in plan["chapters"]:
            prev=None
            ends=[p["end"] for p in c["captions"]]
            for f in range(c["frames"]):
                time=c["start"]+f/FPS
                idx=bisect.bisect_right(ends,time)
                if idx>=len(ends) or time<c["captions"][idx]["start"]: idx=-1
                phase=int(f>=c["cut"])
                if (phase,idx)!=prev:
                    caption=c["captions"][idx]["text"] if idx>=0 else ""
                    static,moves=compose(board,c,phase,caption)
                    prev=phase,idx
                frame=static.copy()
                board.motion_frame(frame,moves,f)
                proc.stdin.write(frame.tobytes())
            print(kind,c["id"],flush=True)
        proc.stdin.close()
        if proc.wait(): raise RuntimeError("Video encoding failed")
    subprocess.run(["ffmpeg","-v","error","-xerror","-nostdin","-i",str(work),"-map","0:v","-map","0:a","-f","null","-"],check=True)
    streams=json.loads(probe("ffprobe","-v","error","-show_streams","-show_format","-of","json",work))
    video=next(s for s in streams["streams"] if s["codec_type"]=="video")
    track=next(s for s in streams["streams"] if s["codec_type"]=="audio")
    measured=meter(work)
    assert (video["width"],video["height"],int(video["nb_frames"]))==(width,height,plan["frames"])
    assert track["codec_name"]=="aac" and track["channels"]==2
    assert abs(float(measured["input_i"])+16)<=1 and float(measured["input_tp"]) <= -1
    work.replace(dest)
    receipt=dict(file=dest.name,bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),width=width,height=height,
      fps=FPS,frames=plan["frames"],seconds=plan["seconds"],decoded="video and audio",level_lufs=float(measured["input_i"]),true_peak_dbtp=float(measured["input_tp"]),captions=len(pages),
      voices={speaker:sum(c["speaker"]==speaker for c in plan["chapters"]) for speaker in ("male","female")},model="gemini-3.8-flash-tts")
    save(target/"verification.json",receipt)
    print(json.dumps(receipt),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("media",type=Path)
    ap.add_argument("kind",choices=["short","full"])
    ap.add_argument("--render",action="store_true")
    args=ap.parse_args()
    if args.render: deliver(args.media,args.kind)
    else:
        _,_,plan=preflight(args.media,args.kind)
        print(args.kind,plan["seconds"],plan["frames"])
