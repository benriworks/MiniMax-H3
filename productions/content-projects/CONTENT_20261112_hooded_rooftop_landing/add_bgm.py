"""Lay the looping score under a finished cut with a steady level and a few planned moves. Video is copied.

Usage: add_bgm.py <input.mp4> <loop.wav> <output.mp4> [--gain-db 0] [--json plan.json]
The plan (times in seconds) keeps the music at one steady level, as the user prefers over constant ducking:
  fade in at the start, lower it under the news voice, drop out for the gunshot and its silence,
  come back for the ending, and fade out with the closing door.
"""
import argparse, json, subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("input", type=Path)
p.add_argument("loop", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--gain-db", type=float, default=0.0)
a = p.parse_args()
if a.output.exists():
    raise SystemExit(f"{a.output} already exists")

dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(a.input)],
                           capture_output=True, text=True, check=True).stdout)
# (start, end, level): the level the music holds between start and end; linear ramps between neighbours.
PLAN = [
    (0.0, 0.0, 0.0), (2.0, 89.6, 1.0),        # fade in over 2 s, steady through the rooftop and the flashback
    (90.2, 104.6, 0.3),                         # under the news anchor (3-7 to 3-9)
    (105.4, 154.4, 1.0),                        # back for the night, the dawn and the plant
    (155.2, 165.0, 0.0),                        # out for the gunshot (4-8) and the silence after it (4-9)
    (167.0, 176.5, 0.8),                        # back softly for the device, the tears and the door
    (dur, dur, 0.0),                            # fade out with the closing door
]
points = []
for s, e, v in PLAN:
    points.append((s, v))
    if e > s:
        points.append((e, v))
expr = str(points[-1][1])
for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
    if t1 <= t0:
        continue
    seg = f"({v0}+({v1}-{v0})*(t-{t0})/({t1 - t0}))"
    expr = f"if(lt(t,{t1}),{seg},{expr})"
expr = f"if(lt(t,{points[0][0]}),{points[0][1]},{expr})"
g = 10 ** (a.gain_db / 20)
graph = (f"[1:a]aloop=loop=-1:size=2147483647,atrim=0:{dur},asetpts=PTS-STARTPTS,aresample=48000,"
         f"volume='{g}*({expr})':eval=frame[m];"
         f"[0:a]aresample=48000[d];[d][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.7:attack=1:release=50:level=0[a]")
subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.input), "-i", str(a.loop), "-filter_complex", graph,
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(a.output)], check=True)
plan_out = a.output.with_suffix(".bgm.json")
plan_out.write_text(json.dumps({"loop": a.loop.name, "gain_db": a.gain_db, "plan": PLAN}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
print("OK", a.output)
