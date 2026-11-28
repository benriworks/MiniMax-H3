"""Keep private captures intact and export only specified public areas."""
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

CROPS = {
    "tabs": ("01-chat-home", (681,121,937,180)),
    "picker": ("02-model-list",(886,462,1143,613)),
    "selected": ("03-selected",(886,461,1145,541)),
    "composer": ("04-temporary",(418,400,1204,483)),
    "question": ("05-demo-input",(424,306,1198,578)),
    "answer": ("06-demo-result",(415,286,1021,380)),
    "followup": ("07-followup",(416,593,1186,642)),
    "follow-question": ("07-followup",(683,514,1199,563)),
    "release": ("08-official-head",(114,337,621,612)),
    "visual-chart": ("10-official-chart",(147,251,750,635)),
    "rules-chart": ("12-instruction-chart",(147,273,747,651)),
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    media, plate = map(Path, sys.argv[1:3])
    cast = media / "cast"
    cast.mkdir(exist_ok=True)
    art=Image.open(plate).convert("RGB")
    if not (cast/"winter-pair.png").exists(): art.save(cast/"winter-pair.png")
    motion_reference = cast / "winter-pair-motion-ref.jpg"
    if not motion_reference.exists():
        art.resize((1152, 768)).save(motion_reference, quality=86, optimize=True)
    w,h=art.size
    for who,x in (("male",0),("female",w//2)):
        art.crop((x,0,x+w//2,h)).save(cast/f"{who}.png")
    figs=media/"captures/figures"
    figs.mkdir(parents=True,exist_ok=True)
    entries={}
    for key,(source,box) in CROPS.items():
        src = media/"captures/original"/(source+".png")
        dst = figs/(key+".png")
        im=Image.open(src).convert("RGB")
        im.crop(box).save(dst)
        entries[key]=dict(source=src.name,source_sha256=sha(src),rectangle=box,public_sha256=sha(dst),size=Image.open(dst).size)
    (figs/"manifest.json").write_text(json.dumps(entries, indent=2),encoding="utf-8")

if __name__ == "__main__":
    main()
