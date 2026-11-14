"""Join the overhead and first-person takes into the 10.000 s review cut (240 frames, 24 fps, 1080x1920)."""
import argparse, hashlib, json, subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("media", type=Path)
p.add_argument("--version", required=True)
p.add_argument("--overhead", default="shots/v01/01-overhead-t2")
p.add_argument("--pov", default="shots/v01/02-pov-t3")
a = p.parse_args()
out_dir = a.media / "review" / a.version
out_dir.mkdir(parents=True, exist_ok=False)
out = out_dir / f"hooded-rooftop-landing-{a.version}.mp4"
def cut_dir(name):
    """Accept a catalogue id such as v03-pov-t4 or a path under the media root."""
    if "/" in name or "\\" in name:
        return name
    cuts = {c["id"]: c["path"] for c in json.loads((a.media / "cuts-catalog.json").read_text(encoding="utf-8"))["cuts"]}
    if name not in cuts:
        raise SystemExit(f"unknown cut id {name}; see CUTS_CATALOG_JA.md")
    return str(Path(cuts[name]).parent).replace("\\", "/")


src = [a.media / cut_dir(a.overhead) / "source.mp4", a.media / cut_dir(a.pov) / "source.mp4"]
video = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1,trim=end_frame=120,setpts=PTS-STARTPTS"
graph = (
    f"[0:v]{video}[v0];[1:v]{video}[v1];[v0][v1]concat=n=2:v=1:a=0[v];"
    "[0:a]atrim=0:5.06,asetpts=PTS-STARTPTS[a0];[1:a]atrim=0:5.06,asetpts=PTS-STARTPTS[a1];"
    "[a0][a1]acrossfade=d=0.12:c1=tri:c2=tri,loudnorm=I=-14:TP=-1.5:LRA=11,"
    "afade=t=in:d=0.05,afade=t=out:st=9.7:d=0.3,atrim=0:10,aresample=48000[a]"
)
subprocess.run(["ffmpeg", "-v", "error", "-i", str(src[0]), "-i", str(src[1]), "-filter_complex", graph,
                "-map", "[v]", "-map", "[a]", "-r", "24", "-frames:v", "240", "-c:v", "libx264", "-crf", "16",
                "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", "10",
                "-movflags", "+faststart", str(out)], check=True)
record = {"output": out.name, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "bytes": out.stat().st_size,
          "inputs": [{"path": str(s.relative_to(a.media)).replace("\\", "/"),
                      "sha256": hashlib.sha256(s.read_bytes()).hexdigest()} for s in src],
          "cut_frame": 120, "frames": 240, "fps": 24}
(out_dir / "render.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(out)
