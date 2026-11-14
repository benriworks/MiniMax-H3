"""Join any number of catalogued cuts, 5.000 s (120 frames) each, into one 1080x1920 24 fps review cut."""
import argparse, hashlib, json, subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("media", type=Path)
p.add_argument("--version", required=True)
p.add_argument("--cuts", nargs="+", required=True, help="catalogue ids in playing order (see CUTS_CATALOG_JA.md)")
a = p.parse_args()
catalog = {c["id"]: c["path"] for c in json.loads((a.media / "cuts-catalog.json").read_text(encoding="utf-8"))["cuts"]}
missing = [c for c in a.cuts if c not in catalog]
if missing:
    raise SystemExit(f"unknown cut ids: {missing}")
src = [a.media / catalog[c] for c in a.cuts]
out_dir = a.media / "review" / a.version
out_dir.mkdir(parents=True, exist_ok=False)
out = out_dir / f"hooded-rooftop-landing-{a.version}.mp4"
n = len(src)
video = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1,trim=end_frame=120,setpts=PTS-STARTPTS"
parts = [f"[{i}:v]{video}[v{i}];[{i}:a]atrim=0:5,asetpts=PTS-STARTPTS,afade=t=in:d=0.04,afade=t=out:st=4.94:d=0.06[a{i}]" for i in range(n)]
graph = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][ac];[ac]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
cmd = ["ffmpeg", "-v", "error"]
for s in src:
    cmd += ["-i", str(s)]
cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-r", "24", "-frames:v", str(120 * n), "-c:v", "libx264", "-crf", "16",
        "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", str(5 * n), "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True)
record = {"output": out.name, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "bytes": out.stat().st_size, "frames": 120 * n, "fps": 24,
          "cuts": [{"id": c, "path": catalog[c], "sha256": hashlib.sha256(s.read_bytes()).hexdigest()} for c, s in zip(a.cuts, src)]}
(out_dir / "render.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(out)
