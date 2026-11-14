"""Overlay news captions and the anchor voice (Gemini TTS) on an assembled review cut.

Usage: add_news.py <input.mp4> <output.mp4> --start <seconds where cut 3-7 begins>
The three news cuts (3-7, 3-8, 3-9) are 5 s each, back to back. During them the clip's own audio is lowered
and the TTS line for each cut plays from 0.25 s into the cut, sped up only if it would run past 4.85 s.
"""
import argparse, json, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--start", type=float, required=True)
p.add_argument("--voice-dir", type=Path, required=True, help="folder with 3-7-trim.wav, 3-8-trim.wav, 3-9-trim.wav")
a = p.parse_args()
if a.output.exists():
    raise SystemExit(f"{a.output} already exists")

CAPTIONS = [("3-7", "市内全域で有毒ガス　汚染拡大"), ("3-8", "市境を全面封鎖"), ("3-9", "住民は全員　隔離施設へ移送")]
FONT = ImageFont.truetype(r"C:\Windows\Fonts\YuGothB.ttc", 64)
LABEL = ImageFont.truetype(r"C:\Windows\Fonts\YuGothB.ttc", 40)
work = a.output.parent / (a.output.stem + "-parts")
work.mkdir(parents=True, exist_ok=True)

def caption_png(text, path):
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = 1420  # just below the 16:9 news picture, inside the blurred fill
    d.rectangle([40, top, 300, top + 64], fill=(190, 20, 30, 235))
    d.text((60, top + 8), "臨時ニュース", font=LABEL, fill="white")
    d.rectangle([40, top + 64, 1040, top + 190], fill=(10, 20, 45, 230))
    d.text((70, top + 90), text, font=FONT, fill="white")
    im.save(path)

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)

cmd = ["ffmpeg", "-v", "error", "-i", str(a.input)]
vf, af, mix = [], [], []
for i, (cut, text) in enumerate(CAPTIONS):
    png = work / f"{cut}-caption.png"
    caption_png(text, png)
    cmd += ["-loop", "1", "-t", "5", "-i", str(png)]
for i, (cut, _) in enumerate(CAPTIONS):
    cmd += ["-i", str(a.voice_dir / f"{cut}-trim.wav")]
prev = "0:v"
for i in range(3):
    t0 = a.start + 5 * i
    vf.append(f"[{1 + i}:v]setpts=PTS-STARTPTS+{t0}/TB[c{i}];[{prev}][c{i}]overlay=0:0:enable='between(t,{t0},{t0 + 5})'[v{i}]")
    prev = f"v{i}"
lines = []
for i, (cut, _) in enumerate(CAPTIONS):
    d = duration(a.voice_dir / f"{cut}-trim.wav")
    tempo = max(1.0, d / 4.6)
    delay = int((a.start + 5 * i + 0.25) * 1000)
    af.append(f"[{4 + i}:a]aresample=48000,atempo={tempo:.3f},volume=1.6,adelay={delay}|{delay}[n{i}]")
    lines.append({"cut": cut, "seconds": round(d, 3), "tempo": round(tempo, 3)})
s, e = a.start, a.start + 15
af.append(f"[0:a]volume='if(between(t,{s},{e}),0.3,1)':eval=frame[bed]")
af.append("[bed][n0][n1][n2]amix=inputs=4:duration=first:normalize=0,alimiter=limit=0.89[a]")
cmd += ["-filter_complex", ";".join(vf + af), "-map", f"[{prev}]", "-map", "[a]", "-c:v", "libx264", "-crf", "16",
        "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(a.output)]
subprocess.run(cmd, check=True)
(work / "news.json").write_text(json.dumps({"start": a.start, "lines": lines}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("OK", a.output)
