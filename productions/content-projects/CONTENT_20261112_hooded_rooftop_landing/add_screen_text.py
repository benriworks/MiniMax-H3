"""Overlay a device-screen message (green on black, like a terminal readout) on an assembled cut. Audio is copied.

Usage: add_screen_text.py <input.mp4> <output.mp4> --at <seconds> --duration <seconds> --text <message>
The readout sits in the upper middle of the 1080x1920 frame and types itself out over the first second.
"""
import argparse, json, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--at", type=float, required=True)
p.add_argument("--duration", type=float, required=True)
p.add_argument("--text", required=True)
p.add_argument("--header", default="受信")
a = p.parse_args()
if a.output.exists():
    raise SystemExit(f"{a.output} already exists")
work = a.output.parent / (a.output.stem + "-screen")
work.mkdir(parents=True, exist_ok=True)
BIG = ImageFont.truetype(r"C:\Windows\Fonts\msgothic.ttc", 72)
SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msgothic.ttc", 40)
GREEN = (120, 255, 150, 255)

steps = len(a.text)
pngs = []
for k in range(1, steps + 1):
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([120, 300, 960, 560], fill=(0, 12, 6, 215), outline=(90, 220, 120, 255), width=3)
    d.text((160, 330), f"＞ {a.header}　送信者：不明", font=SMALL, fill=GREEN)
    d.text((160, 420), a.text[:k] + ("▌" if k < steps else ""), font=BIG, fill=GREEN)
    path = work / f"screen-{k:02d}.png"
    im.save(path)
    pngs.append(path)

per = 1.0 / steps
lst = work / "frames.txt"
lines = [f"file '{p.as_posix()}'\nduration {per:.4f}\n" for p in pngs[:-1]]
lines.append(f"file '{pngs[-1].as_posix()}'\nduration {a.duration - 1.0:.4f}\nfile '{pngs[-1].as_posix()}'\n")
lst.write_text("".join(lines), encoding="utf-8")
graph = (f"[1:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st={a.duration - 0.3}:d=0.3:alpha=1,"
         f"setpts=PTS-STARTPTS+{a.at}/TB[s];[0:v][s]overlay=0:0:eof_action=pass[v]")
subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.input), "-f", "concat", "-safe", "0", "-i", str(lst),
                "-filter_complex", graph, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(a.output)], check=True)
(work / "screen.json").write_text(json.dumps({"at": a.at, "duration": a.duration, "text": a.text}, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
print("OK", a.output)
