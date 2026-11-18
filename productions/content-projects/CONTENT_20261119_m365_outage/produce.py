"""Render the full review, verify the exported streams and preserve the time-coded edit."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from PIL import Image

from frames import CAPSIZE, CAPWIDTH, FLOWS, PORTRAITS, Plates, W, H
from tools.studio.editorial_captions import PROTECTED, timed_captions
from tools.studio.longform_audio import assemble_audio, plan_dialogue

HERE=Path(__file__).resolve().parent
FPS=24
PROTECT=(*PROTECTED,"Microsoft","Microsoft 365","Teams","Exchange Online","Exchange","Outlook","エクステンションセンター",
         "23時間50分","午前1時20分","午前1時10分","午後1時15分","明治薬科大学","立命館大学","8割超","約14％","ロック競合")
MOTIONS={"male-thinking":"b284c50afa0eb95cb81d9786f47d6ae4bd9670a27da60b56d6107af8eb1f7799",
         "female-understanding":"df4967a3ab73e2eb598e020fd8959ed7756fdb5e4a24a64424dabd1f42897126",
         "male-understanding":"336f23df42622d7c56d158b293a785d31b373ce0aabbf9294fab8b0a6ae70351"}


def save(path,val):
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(val,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def digest(path):
    with path.open("rb") as stream:
        return sha256(stream.read()).hexdigest()


def command(*args):
    return subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding="utf-8",check=True)


def motion(media,source):
    info={}
    for name, expected in MOTIONS.items():
        clip=source/(name+".mp4")
        if digest(clip)!=expected:
            raise ValueError("Unexpected cast asset: "+name)
        folder=media/"motion"/name
        folder.mkdir(parents=True,exist_ok=True)
        if not list(folder.glob("*.jpg")):
            command("ffmpeg","-nostdin","-v","error","-n","-i",clip,"-an","-vf","fps=12,scale=480:-2","-q:v",3,folder/"%03d.jpg")
        frames=len(list(folder.glob("*.jpg")))
        if frames!=62:
            raise ValueError(f"{name}: {frames} frames")
        info[name]={"sha256":expected,"bytes":clip.stat().st_size,"frames":frames}
    save(media/"motion/manifest.json",info)


def timeline(story,media,version):
    stages=[dict(id=s["id"],title=s["title"],target_seconds=0,tail_seconds=(1.1 if s["id"]=="end" else .28),
                 turns=[dict(speaker=s["speaker"],text=s["display"])]) for s in story]
    voice="selected" if version=="v01" else f"selected-{version}"
    plan=plan_dialogue(stages,media/"voice"/voice,fps=FPS)
    for s,c in zip(story,plan["chapters"],strict=True):
        t=c["turns"][0]
        c["captions"]=timed_captions(s["display"],t["start"],t["end"]-t["start"],CAPWIDTH,CAPSIZE,protected=PROTECT)
    return plan


def caption(c,when):
    return next((t["text"] for t in c["captions"] if t["start"]<=when<t["end"]),"")


def frame_key(scene,c,frame):
    kind=scene["visual"]
    tick=min(2,int(3*frame/c["frames"])) if kind in FLOWS or kind=="hero" else 0
    pose=min(62,1+frame//2) if kind in PORTRAITS or kind=="hero" else 1
    return tick,pose,caption(c,c["start"]+frame/FPS)


def preview(media,plates,story,plan,version):
    folder=media/"preflight"/version
    folder.mkdir(parents=True,exist_ok=True)
    sheet=Image.new("RGB",(1200,((len(story)+2)//3)*225),"#354649")
    for i,(s,c) in enumerate(zip(story,plan["chapters"],strict=True)):
        for page in c["captions"]:
            frame=min(c["frames"]-1,int((((page["start"]+page["end"])*.5)-c["start"])*FPS))
            plates.frame(i,*frame_key(s,c,frame))
        for name,fraction in [("middle",.55),("last",.85)]:
            frame=int(fraction*c["frames"]); im=plates.frame(i,*frame_key(s,c,frame))
            im.save(folder/f'{s["id"]}-{name}.jpg',quality=90)
            if name=="middle": sheet.paste(im.resize((400,225),Image.Resampling.LANCZOS),(i%3*400,i//3*225))
    sheet.save(folder/"storyboard.jpg",quality=93)
    save(folder/"text-bounds.json",list(plates.canvas.audit.values()))
    print("Preview",len(story),len(plates.canvas.audit),round(plan["seconds"],3),flush=True)


def loudness(path):
    measured=command("ffmpeg","-nostdin","-hide_banner","-i",path,"-vn","-af","loudnorm=I=-16:TP=-1.7:LRA=10:print_format=json","-f","null","-")
    return json.loads(re.findall(r"\{[^{}]+\}",measured.stderr)[-1])


def srt_time(seconds):
    n=round(1000*seconds);q,z=divmod(n,1000);q,s=divmod(q,60);h,m=divmod(q,60)
    return f"{h:02}:{m:02}:{s:02},{z:03}"


def render(media,plates,story,plan,version):
    folder=media/"release"/version
    folder.mkdir(parents=True,exist_ok=False)
    bed=assemble_audio(plan,folder,music_style="calm")
    src=folder/"mix-premaster.wav"; meter=loudness(src)
    spec=("loudnorm=I=-16:TP=-1.7:LRA=10:linear=true:"
          f"measured_I={meter['input_i']}:measured_TP={meter['input_tp']}:measured_LRA={meter['input_lra']}:"
          f"measured_thresh={meter['input_thresh']}:offset={meter['target_offset']}")
    audio=folder/"normalized.wav"
    command("ffmpeg","-v","error","-nostdin","-n","-i",src,"-af",spec,"-ar","48000",audio)
    video=folder/f"microsoft365-outage-full-{version}.mp4"
    pending=folder/("."+video.name)
    cmd=["ffmpeg","-nostdin","-v","error","-n","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}",
         "-r",str(FPS),"-i","pipe:0","-i",str(audio),"-c:v","libx264","-preset","veryfast","-crf","19",
         "-threads","6","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-movflags","+faststart",str(pending)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as enc:
        try:
            for i,(s,c) in enumerate(zip(story,plan["chapters"],strict=True)):
                last=None
                for frame in range(c["frames"]):
                    key=frame_key(s,c,frame)
                    if key!=last:
                        raw=plates.frame(i,*key).tobytes();last=key
                    enc.stdin.write(raw)
                print(s["id"],round(c["end"],1),flush=True)
        finally:
            enc.stdin.close()
        if enc.wait(): raise RuntimeError("Encoding failed")
    command("ffmpeg","-nostdin","-v","error","-xerror","-i",pending,"-f","null","-")
    probe=json.loads(command("ffprobe","-v","error","-show_streams","-show_format","-of","json",pending).stdout)
    v,a=probe["streams"]
    assert (v["width"],v["height"],v["codec_name"],a["codec_name"])==(W,H,"h264","aac")
    assert int(v["nb_frames"])==plan["frames"] and abs(float(probe["format"]["duration"])-plan["seconds"])<.06
    levels=loudness(pending)
    assert -18<=float(levels["input_i"])<=-14 and float(levels["input_tp"])<=-1
    pending.rename(video)
    pages=[p for c in plan["chapters"] for p in c["captions"]]
    (folder/"captions.srt").write_text("\n\n".join(f"{i}\n{srt_time(p['start'])} --> {srt_time(p['end'])}\n{p['text']}" for i,p in enumerate(pages,1))+"\n",encoding="utf-8")
    for c in plan["chapters"]:
        for t in c["turns"]:
            t["voice_path"]=Path(t["voice_path"]).relative_to(media).as_posix()
    save(folder/"timeline.json",plan)
    save(folder/"verification.json",dict(version=version,file=video.name,frames=plan["frames"],seconds=plan["seconds"],
         width=W,height=H,fps=FPS,codec="H.264/AAC",bytes=video.stat().st_size,sha256=digest(video),decode=True,captions=len(pages),
         final_lufs=levels["input_i"],final_dbtp=levels["input_tp"],bgm=bed["bgm_mix_profile"],user_approved=False,published=False))
    print(video,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=["motion","preview","render"])
    ap.add_argument("media",type=Path)
    ap.add_argument("--motion-source",type=Path)
    ap.add_argument("--version",default="v01")
    args=ap.parse_args(); media=args.media.resolve()
    if args.mode=="motion":
        motion(media,args.motion_source)
    else:
        story=json.loads((HERE/"story-v01.json").read_text(encoding="utf-8"))
        if args.version!="v01":
            changes=json.loads((HERE/f"revision-{args.version}.json").read_text(encoding="utf-8"))
            story=[(s|{"display":changes[s["id"]]["display"]}) if s["id"] in changes else s for s in story]
        plates=Plates(media,story)
        plan=timeline(story,media,args.version)
        if args.mode=="preview": preview(media,plates,story,plan,args.version)
        else: render(media,plates,story,plan,args.version)
