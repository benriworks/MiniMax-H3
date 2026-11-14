"""Overlay time-jump titles (e.g. 「3日前」「現在」) on an assembled cut. Video only; audio is copied.

Usage: add_titles.py <input.mp4> <output.mp4> --title <seconds> <text> [--title <seconds> <text> ...]
Each title fades in over 0.4 s, holds, and fades out, 2.6 s in total, in the lower left of the 1080x1920 frame.
"""
import argparse, json, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--title", nargs=2, action="append", required=True, metavar=("SECONDS", "TEXT"))
a = p.parse_args()
if a.output.exists():
    raise SystemExit(f"{a.output} already exists")
work = a.output.parent / (a.output.stem + "-titles")
work.mkdir(parents=True, exist_ok=True)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\yumindb.ttf", 76)
HOLD = 2.6

def title_png(text, path):
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y = 90, 1500
    w = d.textlength(text, font=FONT)
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x, y), text, font=FONT, fill=(0, 0, 0, 200))
    im = Image.alpha_composite(im, shadow.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.text((x, y), text, font=FONT, fill=(245, 245, 240, 255))
    d.line([(x, y + 104), (x + w, y + 104)], fill=(245, 245, 240, 220), width=3)
    im.save(path)

cmd = ["ffmpeg", "-v", "error", "-i", str(a.input)]
graph, prev = [], "0:v"
for i, (sec, text) in enumerate(a.title):
    png = work / f"title-{i}.png"
    title_png(text, png)
    cmd += ["-loop", "1", "-t", str(HOLD), "-i", str(png)]
    t0 = float(sec)
    graph.append(f"[{i + 1}:v]format=rgba,fade=t=in:st=0:d=0.4:alpha=1,fade=t=out:st={HOLD - 0.5}:d=0.5:alpha=1,"
                 f"setpts=PTS-STARTPTS+{t0}/TB[t{i}];[{prev}][t{i}]overlay=0:0:eof_action=pass[v{i}]")
    prev = f"v{i}"
cmd += ["-filter_complex", ";".join(graph), "-map", f"[{prev}]", "-map", "0:a", "-c:v", "libx264", "-crf", "16",
        "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(a.output)]
subprocess.run(cmd, check=True)
(work / "titles.json").write_text(json.dumps([{"seconds": float(s), "text": t} for s, t in a.title], ensure_ascii=False,
                                             indent=2) + "\n", encoding="utf-8")
print("OK", a.output)
