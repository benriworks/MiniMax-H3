"""Review encoded pixels from each caption state plus the actual first and last frame."""
import hashlib
import json
import math
import sys
from pathlib import Path
import cv2
from PIL import Image

from render import make_plan,save

def check(media,kind):
    target=media/"release/v01"/kind
    plan=make_plan(media,kind)
    movie=next(target.glob("chatgpt62-chat-*.mp4"))
    cap=cv2.VideoCapture(str(movie))
    folder=target/"encoded-review";folder.mkdir(exist_ok=True)
    ids={0,plan["frames"]-1}
    for c in plan["chapters"]:
        ids.update(round((p["start"]+p["end"])*12) for p in c["captions"])
        ids.add(round(c["start"]*24)+c["cut"])
    thumb=(159,282) if kind=="short" else (284,160)
    images=[]
    for f in sorted(ids):
        cap.set(cv2.CAP_PROP_POS_FRAMES,f)
        ok,img=cap.read()
        if not ok:raise RuntimeError(f)
        tile=Image.fromarray(cv2.cvtColor(img,cv2.COLOR_BGR2RGB))
        if f==0: tile.save(folder/"opening.jpg",quality=90)
        tile.thumbnail(thumb,Image.Resampling.LANCZOS)
        images.append(tile)
    cap.release()
    for a in range(0,len(images),16):
        batch=images[a:a+16]
        sheet=Image.new("RGB",(thumb[0]*4,thumb[1]*math.ceil(len(batch)/4)),"#152E3B")
        for i,pic in enumerate(batch): sheet.paste(pic,(i%4*thumb[0],i//4*thumb[1]))
        sheet.save(folder/f"frames-{a//16+1}.jpg",quality=91)
    save(folder/"sampling.json",dict(frames=sorted(ids),covered_caption_states=sum(len(c["captions"]) for c in plan["chapters"])))
    return len(images)

if __name__=="__main__":
    media=Path(sys.argv[1])
    print({k:check(media,k) for k in ("short","full")})
