"""Sample encoded images, confirm sources/voices, and make the optional vertical cover."""
import argparse
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess

import cv2
import fitz
from PIL import Image, ImageDraw

from frames import HERE
from pair_frames import Edition
from render_pair import editorial

CASES={"full":[0,2,19,32.5,37,83,112,160.3,166.5,179,260,278,305,310.7,316],
       "short":[0,2,11.5,16,20,24,29.5,32,36,39.8,43.5,45.7]}

def item(path):
    return dict(bytes=path.stat().st_size,sha256=sha256(path.read_bytes()).hexdigest())

def inspect(media,edition):
    short=edition=="short"
    directory=media/"release"/("short-v01" if short else "v03")
    evidence=json.loads((directory/"verification.json").read_text(encoding="utf-8"))
    mp4=directory/evidence["file"]
    assert evidence["sha256"]==item(mp4)["sha256"]
    cap=cv2.VideoCapture(str(mp4))
    thumb=(216,384) if short else (358,201)
    col=4 if short else 3
    board=Image.new("RGB",(thumb[0]*col,(thumb[1]+20)*((len(CASES[edition])+col-1)//col)),"#192E31")
    draw=ImageDraw.Draw(board)
    for i,t in enumerate(CASES[edition]):
        cap.set(cv2.CAP_PROP_POS_FRAMES,int(t*24));ok,frame=cap.read()
        assert ok and frame.std()>23,(edition,t)
        im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));im.thumbnail(thumb,Image.Resampling.LANCZOS)
        x,y=(i%col)*thumb[0],(i//col)*(thumb[1]+20)
        board.paste(im,(x,y));draw.text((x+6,y+thumb[1]+1),f"{t:06.1f} s",fill="#D1EADF")
    cap.release();board.save(directory/"encoded-review-frames.jpg",quality=91)
    evidence["sampled_encoded_seconds"]=CASES[edition]
    timeline=json.loads((directory/"timeline.json").read_text(encoding="utf-8"))
    evidence["voices"]=[dict(id=c["id"],speaker=c["turns"][0]["speaker"],file=c["turns"][0]["voice_path"],
                             **item(media/c["turns"][0]["voice_path"])) for c in timeline["chapters"]]
    evidence["standalone_score"]=item(directory/"music-original.wav")
    return evidence

def verify(media):
    q={k:inspect(media,k) for k in CASES}
    folder=media/"release/short-v01"
    story,_=editorial(media,"short")
    editor=Edition(media,story,True)
    cover=editor.backing(True).copy()
    editor.mast(cover,"",True)
    editor.t(cover,"Outlookが",(64,240,1000,433),143,"#FFFEF6")
    editor.t(cover,"止まった",(62,435,1000,652),168,"#FFFEF6")
    editor.t(cover,"3つの理由",(63,665,1010,878),157,"#B0EBD2")
    editor.faces(cover,[("M-surprise",(66,930,531,1498)),("F-surprise",(543,930,1007,1498))],25)
    editor.t(cover,"Microsoft 暫定報告",(69,1568,1005,1683),58,"#B0EBD2")
    ImageDraw.Draw(cover).line((70,1725,1005,1725),fill="#80A69D",width=3)
    cover.save(folder/"microsoft365-outage-short-cover.jpg",quality=95)
    q["short"]["cover"]=item(folder/"microsoft365-outage-short-cover.jpg")
    pdf=media/"article/v02/microsoft365-outage-article.pdf"
    q["article"]=item(pdf)
    with fitz.open(pdf) as doc:
        assert len(doc)==4 and len(doc[-1].get_links())>=3 and "サービス" in doc[-1].get_text()
        q["article"].update(pages=len(doc),links=sum(len(pg.get_links()) for pg in doc))
    legacy=json.loads((media/"release/v02/timeline.json").read_text(encoding="utf-8"))
    q["previous_full_male_seconds"]=round(sum(x["frames"] for x in legacy["chapters"] if x["id"] in {"mail","where","labq","scopeq","restoreq"})/24,3)
    q["cast_inputs"]=json.loads((media/"motion/pair/inputs.json").read_text(encoding="utf-8"))
    for sex in ["male","female"]:
        p=media/"motion"/f"revision-03-{sex}-surprise"/"generation.json"
        ln=json.loads(p.read_text(encoding="utf-8"));q["cast_inputs"][sex+"-surprise"].update({k:ln[k] for k in ["input_image","input_sha256","model","seconds","resolution","provider_seconds","usage"]})
    manifest=json.loads((media/"_private/revision-03/official/sources.json").read_text(encoding="utf-8"))
    for name in ["status","news","meiji","learn","keynote-date","keynote-quote"]:
        entry=manifest.setdefault("keynote" if name.startswith("keynote") else name,{})
        entry.setdefault("derivatives",{})[name]=item(media/"captures/revision-03"/(name+".png"))
    q["captures"]=manifest
    q["environment"]=dict(python=platform.python_version(),pillow=version("pillow"),scipy=version("scipy"),
                          ffmpeg=subprocess.check_output(["ffmpeg","-version"],encoding="utf-8").splitlines()[0],
                          font=item(HERE.parents[2]/"studio/public/template-assets/NotoSansJP-Variable.ttf"))
    (media/"release/verification-pair.json").write_text(json.dumps(q,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Verified full, short, cover, four PDF pages and",q["article"]["links"],"links.")

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("media",type=Path)
    verify(ap.parse_args().media.resolve())
