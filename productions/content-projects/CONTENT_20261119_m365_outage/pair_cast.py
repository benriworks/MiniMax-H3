"""Index, crop and sample the previously approved cast and the two incident reactions."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

def prepare(media, originals):
    root=media/"motion/pair"
    root.mkdir(exist_ok=True,parents=True)
    ledger={}
    board=Image.new("RGB",(860,6*153),"#253333")
    for row,(person,pose) in enumerate((p,k) for p in ("male","female") for k in ("thinking","surprise","understanding")):
        name=f"{person}-{pose}"
        clip=media/"motion"/("revision-03-"+name)/"source.mp4" if pose=="surprise" else originals/(name+".mp4")
        src=str(clip)
        folder=root/name
        folder.mkdir(exist_ok=True)
        vf="fps=12,scale=640:640" if pose=="surprise" else "fps=12,scale=640:-2,crop=640:640:0:210"
        subprocess.run(["ffmpeg","-v","error","-nostdin","-y","-i",src,"-an","-vf",vf,"-q:v","2",str(folder/"%03d.jpg")],check=True)
        frames=sorted(folder.glob("*.jpg"))
        for col,idx in enumerate([0,11,22,33,44,55]):
            tile=Image.open(frames[min(idx,len(frames)-1)]).resize((139,139),Image.Resampling.LANCZOS)
            board.paste(tile,(col*143,row*153+14))
        ImageDraw.Draw(board).text((4,row*153),name,fill="white")
        ledger[name]={"sha256":sha256(clip.read_bytes()).hexdigest(),"bytes":clip.stat().st_size,"jpeg_frames":len(frames),"filter":vf,
                      "source":clip.relative_to(media).as_posix() if pose=="surprise" else clip.name}
    board.save(root/"contact.jpg",quality=91)
    (root/"inputs.json").write_text(json.dumps(ledger,indent=2),encoding="utf-8")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("media",type=Path);parser.add_argument("originals",type=Path)
    a=parser.parse_args();prepare(a.media,a.originals)
