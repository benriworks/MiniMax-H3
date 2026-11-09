"""Replace the decision shot using the saved FL2VA clip and the v04 edit."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from render_short_drama import DURATION, FPS, TITLE, ffmpeg, make_shot, probe

SHOT = "05-decision"
FIRST = 13 * FPS
AFTER = 18 * FPS
FRAME_COUNT = AFTER - FIRST


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained_hashes(path):
    video = ffmpeg(
        "-i", str(path), "-map", "0:v:0",
        "-vf", f"select='lt(n,{FIRST})+gte(n,{AFTER})'",
        "-fps_mode", "passthrough", "-threads", "2", "-f", "hash", "-hash", "sha256", "-",
        capture=True,
    ).stdout.decode().strip()
    audio = ffmpeg(
        "-i", str(path), "-map", "0:a:0", "-c:a", "copy",
        "-f", "hash", "-hash", "sha256", "-", capture=True,
    ).stdout.decode().strip()
    return {"decoded_frames_outside_shot": video, "aac_packets": audio}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("--version", default="v05")
    args = parser.parse_args()
    if not re.fullmatch(r"v05(?:-[a-z0-9-]+)?", args.version):
        parser.error("Use v05 or a distinct v05-* review version.")

    base = args.base.resolve()
    original = base / "review/v04/nichiyou-umi-short-v04.mp4"
    original_render = json.loads(original.with_name("render.json").read_text(encoding="utf-8"))
    if sha256(original) != original_render["sha256"]:
        raise ValueError("The saved v04 does not match its record.")
    timeline = original_render["timeline"]
    decision, = (item for item in timeline if item["shot"] == SHOT)
    if (decision["start"], decision["end"], decision["frames"]) != (FIRST / FPS, AFTER / FPS, FRAME_COUNT):
        raise ValueError("The comparison edit has a different decision-shot interval.")

    source = base / "shots/v05/05-decision-fl2va/source.mp4"
    generation = json.loads(source.with_name("generation.json").read_text(encoding="utf-8"))
    if generation["state"] != "saved" or sha256(source) != generation["output_sha256"]:
        raise ValueError("The FL2VA source does not match its saved record.")
    source_info = probe(source)
    source_video = next(stream for stream in source_info["streams"] if stream["codec_type"] == "video")
    source_frames = int(source_video["nb_frames"])
    if source_frames < FRAME_COUNT:
        raise ValueError("The source has fewer frames than the 5-second edit.")
    # Sample evenly over the entire shot, retaining both generated endpoints.
    ratio = f"{FRAME_COUNT - 1}/{source_frames - 1}"
    sample = f"select='eq(n,0)+gt(floor(n*{ratio}),floor((n-1)*{ratio}))',setpts=N/({FPS}*TB)"

    scratch = base / "edit" / args.version
    review = base / "review" / args.version
    scratch.mkdir(parents=True, exist_ok=False)
    review.mkdir(parents=True, exist_ok=False)
    make_shot(scratch / f"{SHOT}.mp4", source, FRAME_COUNT, reframing=sample)

    clips = []
    for shot in timeline:
        name = shot["shot"]
        folder = "." if name == SHOT else ("../v04" if shot["start"] < 10 else "../v03")
        clips.append(f"file '{folder}/{name}.mp4'\n")
    concat = scratch / "concat.txt"
    concat.write_text("".join(clips), encoding="ascii")
    temporary = review / "pending.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(original),
           "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-t", str(DURATION),
           "-movflags", "+faststart", str(temporary))
    evidence = probe(temporary)
    video = evidence["streams"][0]
    if (video["width"], video["height"], int(video["nb_frames"]), video["avg_frame_rate"]) != (
            1080, 1920, DURATION * FPS, "24/1") or float(evidence["format"]["duration"]) != DURATION:
        raise ValueError(evidence)
    ffmpeg("-xerror", "-i", str(temporary), "-map", "0:v", "-map", "0:a", "-f", "null", "-")
    hashes = retained_hashes(temporary)
    if hashes != retained_hashes(original):
        raise ValueError("Frames outside the replacement or the AAC audio changed.")

    decision.update(source_start=0, source_end_frame=source_frames - 1,
                    source_sha256=generation["output_sha256"], generation_mode="FL2VA")
    final = review / f"nichiyou-umi-short-{args.version}.mp4"
    temporary.rename(final)
    evidence.update(title=TITLE, decode="passed", version=args.version, sha256=sha256(final),
                    original_sha256=original_render["sha256"], retained_hashes=hashes,
                    source=source_info, timeline=timeline)
    (review / "render.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {final}", flush=True)


if __name__ == "__main__":
    main()
