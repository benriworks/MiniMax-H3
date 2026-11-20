"""Package the two revised thumbnails and copy-ready YouTube fields beside the reviewed videos."""
from argparse import ArgumentParser
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image

from capture import HERE, OUT, sha, write
from verify import check_cut
from voice import load_story

KINDS = {"short": ("v02", (2160, 3840), (360, 640)), "full": ("v03", (3840, 2160), (320, 180))}
MEDIA = OUT / "youtube-v02"
DELIVERY = OUT / "release/youtube-v02"
SOURCES = ("access.redhat.com", "blog.remirepo.net", "www.redhat.com", "amachamusic.chagasi.com")

def file_info(path, root):
    return dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=sha(path))

def picture_info(path, root):
    with Image.open(path) as image:
        image.load()
        return {**file_info(path, root), "pixels": list(image.size), "format": image.format}

def convert(source, target, size, *, jpeg):
    command=["ffmpeg","-v","error","-nostdin","-n","-i",str(source),"-vf",
             f"scale={size[0]}:{size[1]}:flags=lanczos,setsar=1","-frames:v","1"]
    if jpeg: command.extend(["-c:v","mjpeg","-q:v","3","-pix_fmt","yuvj444p"])
    subprocess.run([*command,"-threads","1",str(target)],check=True)

def verify_description(text, timeline, kind):
    if not 0<len(text)<=5000 or not all(site in text for site in SOURCES):
        raise ValueError("Incomplete YouTube description or incorrect length")
    if any(value in text for value in ("Content ID", "drive.google.com", "](", "構成を見る")):
        raise ValueError("Editorial notes or ambiguous wording in description")
    stamps=[60*int(m)+int(s) for m,s in re.findall(r"^(\d+):(\d{2}) ",text,re.M)]
    expected=[int(c["start"]) for c in timeline["chapters"]] if kind=="full" else []
    if stamps!=expected: raise ValueError((kind,stamps,expected))

def package():
    verification=HERE/"youtube/verification-v02.json"
    if DELIVERY.exists():
        raise FileExistsError(f"Use --check for the saved bundle {DELIVERY}")
    report={"date":"2026-11-21","cuts":{},"user_approved":False,"youtube_published":False}
    checks=MEDIA/"review"; checks.mkdir(parents=True,exist_ok=True)
    captures=json.loads((OUT/"captures/providers-v01/manifest.json").read_text(encoding="utf-8"))
    for record in captures["assets"].values():
        for key in ("original","quote"):
            if sha(OUT/record[key]["path"])!=record[key]["sha256"]: raise ValueError(record[key]["path"])
    report["official_sources"]=captures
    with TemporaryDirectory(prefix=".php-youtube-",dir=DELIVERY.parent) as temporary:
        folder=Path(temporary)/"delivery"; folder.mkdir()
        titles=[]
        for kind,(edition,size,small) in KINDS.items():
            cut=check_cut(kind,edition)
            timeline=json.loads((OUT/"release"/edition/kind/"timeline.json").read_text(encoding="utf-8"))
            title=load_story(edition)["titles"][kind]
            if not 0<len(title)<=100 or not all(name in title for name in ("Red Hat","Remi")):raise ValueError(title)
            desc=HERE/"youtube"/f"{kind}-{edition}-description.txt"
            description_text=desc.read_text(encoding="utf-8")
            verify_description(description_text,timeline,kind)
            stem=f"php-security-{kind}-{edition}"
            dest=folder/(stem+"-description.txt")
            dest.write_text(description_text,encoding="utf-8",newline="\n")
            original=MEDIA/"source"/(kind+"-art-v02.png"); thumb=folder/(stem+"-thumbnail.jpg")
            convert(original,thumb,size,jpeg=True)
            preview=checks/(kind+"-phone.png")
            if not preview.exists(): convert(thumb, preview, small, jpeg=False)
            info=picture_info(thumb,folder)
            if info["pixels"]!=list(size) or info["bytes"]>=2_000_000:raise ValueError(info)
            titles.append(("ショート" if kind=="short" else "フル")+" "+edition+"\n"+title)
            prior_edition="v01" if kind=="short" else "v02"
            previous={x["line"]:x["sha256"] for x in check_cut(kind,prior_edition)["voice_lines"]}
            reused=sum(previous.get(x["line"])==x["sha256"] for x in cut["voice_lines"])
            report["cuts"][kind]=dict(video=cut, reused_voice_lines=reused,title=title,description=file_info(dest,folder),
                thumbnail=info,art=picture_info(original,OUT),review=picture_info(preview,OUT))
        titlefile=folder/"php-security-youtube-titles-v02.txt"
        titlefile.write_text("\n\n".join(titles)+"\n",encoding="utf-8",newline="\n")
        report["titles_file"]=file_info(titlefile,folder)
        folder.rename(DELIVERY)
    write(verification,report)

def check():
    report=json.loads((HERE/"youtube/verification-v02.json").read_text(encoding="utf-8"))
    for kind,cut in report["cuts"].items():
        video=cut["video"]
        if sha(OUT/"release"/video["edition"]/kind/video["file"])!=video["sha256"]:raise ValueError(video["file"])
        canonical=(HERE/"youtube"/f"{kind}-{video['edition']}-description.txt").read_text(encoding="utf-8")
        if canonical.encode("utf-8")!=(DELIVERY/cut["description"]["path"]).read_bytes():raise ValueError("Description differs from source")
        if cut["title"]!=load_story(video["edition"])["titles"][kind]:raise ValueError("Title differs from source")
        for key in ("thumbnail","description"):
            if sha(DELIVERY/cut[key]["path"])!=cut[key]["sha256"]:raise ValueError(cut[key]["path"])
        for key in ("art","review"):
            if sha(OUT/cut[key]["path"])!=cut[key]["sha256"]:raise ValueError(cut[key]["path"])
    for asset in report["official_sources"]["assets"].values():
        for key in ("original","quote"):
            if sha(OUT/asset[key]["path"])!=asset[key]["sha256"]:raise ValueError(asset[key]["path"])
    if sha(DELIVERY/report["titles_file"]["path"])!=report["titles_file"]["sha256"]:raise ValueError("Title export changed")
    print("Verified two MP4s, two thumbnails, two descriptions, both titles and the official sources.")

if __name__=="__main__":
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    if not args.check: package()
    check()
