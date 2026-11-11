"""Assemble the saved rooftop parkour shots into a 10-second review video."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

FPS = 24
CUT_SECONDS = 5
SHOT_FRAMES = CUT_SECONDS * FPS


def ffprobe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,avg_frame_rate,nb_frames,sample_rate,channels:format=duration,size",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shot_filters(index, frames):
    if frames < SHOT_FRAMES:
        raise ValueError("Expected at least 120 source frames for each five-second shot.")
    # Sample from the first through the last frame, including both endpoints.
    proportion = f"{SHOT_FRAMES - 1}/{frames - 1}"
    selected = (
        f"select='if(eq(n,0),1,gt(floor(n*{proportion}),floor((n-1)*{proportion})))'"
    )
    video = (
        f"[{index}:v:0]{selected},setpts=N/({FPS}*TB),"
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920,setsar=1,format=yuv420p[v{index}]"
    )
    audio = (
        f"[{index}:a:0]aresample=48000,atempo={frames / SHOT_FRAMES:.8f},"
        "aformat=channel_layouts=stereo,apad,atrim=duration=5.06,asetpts=PTS-STARTPTS"
    )
    if index == 0:
        audio += ",afade=t=in:st=0:d=0.08"
    return video, audio + f"[a{index}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_root", type=Path)
    parser.add_argument("--pov-revision", choices=("v01", "v02", "v03"), default="v01")
    parser.add_argument("--version", default="v01")
    args = parser.parse_args()
    if not re.fullmatch(r"v\d{2}(?:-[a-z0-9-]+)?", args.version):
        parser.error("Choose a review folder such as v01 or v02-reproduction.")

    inputs = []
    filters = []
    shot_records = []
    if args.pov_revision == "v03":
        shot_folders = ("v03/01-overhead", "v03/02-pov-roll-review")
    else:
        shot_folders = ("v01/01-overhead", f"{args.pov_revision}/02-pov")
    for index, shot_folder in enumerate(shot_folders):
        relative_folder = Path("shots") / shot_folder
        folder = args.media_root / relative_folder
        source = folder / "source.mp4"
        edited = index == 1 and args.pov_revision == "v03"
        ledger = "derivation.json" if edited else "generation.json"
        receipt = json.loads((folder / ledger).read_text(encoding="utf-8"))
        expected_state = "rendered" if edited else "saved"
        if receipt["state"] != expected_state or digest(source) != receipt["output_sha256"]:
            raise ValueError(f"{shot_folder} does not match its saved input record.")
        probe = ffprobe(source)
        video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
        if video["avg_frame_rate"] != "24/1":
            raise ValueError(f"Expected 24 fps for {shot_folder}.")
        frames = int(video["nb_frames"])
        inputs.extend(("-i", str(source)))
        filters.extend(shot_filters(index, frames))
        shot_records.append({
            "name": folder.name, "source": (relative_folder / "source.mp4").as_posix(),
            "sha256": receipt["output_sha256"],
            "size": int(probe["format"]["size"]), "source_duration": probe["format"]["duration"],
            "source_frames": frames, "used_source_bounds_inclusive": [0, frames - 1],
            "edit_start_frame": index * SHOT_FRAMES, "edit_frames": SHOT_FRAMES,
        })

    filters.extend((
        "[v0][v1]concat=n=2:v=1:a=0[v]",
        "[a0][a1]acrossfade=d=0.12:c1=tri:c2=tri,afade=t=out:st=9.86:d=0.14,"
        "alimiter=limit=0.89:attack=4:release=50:level=false:latency=true[a]",
    ))
    target = args.media_root / "review" / args.version
    target.mkdir(parents=True, exist_ok=False)
    pending = target / "pending.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *inputs,
        "-filter_complex_threads", "2", "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[a]", "-r", str(FPS), "-c:v", "libx264",
        "-preset", "fast", "-crf", "16", "-threads", "4", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(pending),
    ], check=True)
    evidence = ffprobe(pending)
    video = evidence["streams"][0]
    if (video["width"], video["height"], video["avg_frame_rate"], int(video["nb_frames"]),
            float(evidence["format"]["duration"])) != (1080, 1920, "24/1", 240, 10.0):
        raise ValueError(f"Unexpected review geometry or duration: {evidence}")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-xerror",
                    "-i", str(pending), "-map", "0:v", "-map", "0:a", "-f", "null", "-"], check=True)
    result = target / f"rooftop-parkour-pov-test-{args.version}.mp4"
    pending.rename(result)
    evidence.update(version=args.version, sha256=digest(result), cut_at_seconds=5.0,
                    shots=shot_records, audio_crossfade_seconds=0.12, decode="passed")
    (target / "render.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
