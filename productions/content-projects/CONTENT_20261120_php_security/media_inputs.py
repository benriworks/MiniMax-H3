"""Validate the selected winter motions and local score, then sample the motions for the edit."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from capture import ROOT, OUT, sha, write

WINTER="CHARACTERS_20261117_winter_duo"
MUSIC=dict(title="ハッピータイム",author="甘茶の音楽工房",original="happytime.mp3",
           sha256="04875cc4d522511497b72c25aad0f535dbd6716dbfade7b7dec1846db4ec5d94")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--library-root",type=Path,required=True,help="Workspace with the winter and local music outputs")
    args=ap.parse_args()
    source=args.library_root/"outputs/characters"/WINTER/"v01/review-v02"
    manifest=json.loads((ROOT/"productions"/WINTER/"motion-manifest-v02.json").read_text(encoding="utf-8"))
    records=[]
    for asset in manifest["clips"]:
        clip=source/asset["file"]
        if sha(clip)!=asset["sha256"]:
            raise ValueError(f"Winter clip differs: {clip.name}")
        frames=OUT/"motion"/asset["id"]
        frames.mkdir(parents=True,exist_ok=True)
        subprocess.run(["ffmpeg","-v","error","-nostdin","-y","-i",str(clip),"-an",
            "-vf","fps=12,scale=640:-2","-q:v","2",str(frames/"%03d.jpg")],check=True)
        if len(list(frames.glob("*.jpg")))!=62:
            raise ValueError("Incomplete winter sequence")
        records.append(dict(id=asset["id"],source=clip.relative_to(args.library_root).as_posix(),
            bytes=clip.stat().st_size,sha256=asset["sha256"],sample_fps=12,sample_frames=62))
    music=args.library_root/"outputs/content-projects/CONTENT_20261117_japan_ai_usage/_private"/MUSIC["original"]
    if sha(music)!=MUSIC["sha256"]:
        raise ValueError("Unexpected local music bytes")
    private=OUT/"_private"
    private.mkdir(exist_ok=True)
    shutil.copyfile(music,private/MUSIC["original"])
    font=ROOT/"studio/public/template-assets/NotoSansJP-Variable.ttf"
    write(OUT/"input-manifest.json",dict(winter=records,music=dict(MUSIC,bytes=music.stat().st_size),
         font=dict(path=font.relative_to(ROOT).as_posix(),bytes=font.stat().st_size,sha256=sha(font))))
if __name__=="__main__":
    main()
