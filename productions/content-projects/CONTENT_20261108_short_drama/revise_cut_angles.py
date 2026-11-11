"""Replace two look-alike cut-ins in Maho v05, preserving the edited audio."""
import argparse
import json
import re
from pathlib import Path

from render_short_drama import DURATION, FPS, TITLE, ffmpeg, make_shot, probe
from replace_decision_shot import retained_hashes, sha256

REPLACEMENTS = {
    "00-childhood-received": (33, 72),
    "04-photo-back": (240, 312),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("--version", default="v06")
    args = parser.parse_args()
    if not re.fullmatch(r"v06(?:-[a-z0-9-]+)?", args.version):
        parser.error("Use v06 or a distinct v06-* review version.")

    base = args.base.resolve()
    previous = base / "review/v05/nichiyou-umi-short-v05.mp4"
    previous_render = json.loads(previous.with_name("render.json").read_text(encoding="utf-8"))
    if sha256(previous) != previous_render["sha256"]:
        raise ValueError("The saved v05 does not match its record.")
    timeline = previous_render["timeline"]
    replacements = {entry["shot"]: (round(entry["start"] * FPS), round(entry["end"] * FPS))
                    for entry in timeline if entry["shot"] in REPLACEMENTS}
    if replacements != REPLACEMENTS:
        raise ValueError("The two cut-ins do not occupy the expected frame intervals.")

    scratch = base / "edit" / args.version
    review = base / "review" / args.version
    scratch.mkdir(parents=True, exist_ok=False)
    review.mkdir(parents=True, exist_ok=False)
    clips = []
    for entry in timeline:
        name = entry["shot"]
        if name in REPLACEMENTS:
            plate = base / "plates/v06" / f"{name}.png"
            make_shot(scratch / f"{name}.mp4", plate, entry["frames"], still_crop="")
            entry.update(source_start=0, source_sha256=sha256(plate), source_kind="reframed_still")
            folder = "."
        elif name == "05-decision":
            folder = "../v05"
        else:
            folder = "../v04" if entry["start"] < 10 else "../v03"
        clips.append(f"file '{folder}/{name}.mp4'\n")

    concat = scratch / "concat.txt"
    concat.write_text("".join(clips), encoding="ascii")
    temporary = review / "pending.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(previous),
           "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-t", str(DURATION),
           "-movflags", "+faststart", str(temporary))
    evidence = probe(temporary)
    video = evidence["streams"][0]
    if (video["width"], video["height"], int(video["nb_frames"]), video["avg_frame_rate"]) != (
            1080, 1920, DURATION * FPS, "24/1") or float(evidence["format"]["duration"]) != DURATION:
        raise ValueError(evidence)
    ffmpeg("-xerror", "-i", str(temporary), "-map", "0:v", "-map", "0:a", "-f", "null", "-")
    received, letter = REPLACEMENTS.values()
    keep = f"lt(n,{received[0]})+between(n,{received[1]},{letter[0] - 1})+gte(n,{letter[1]})"
    hashes = retained_hashes(temporary, video_selection=keep)
    if hashes != retained_hashes(previous, video_selection=keep):
        raise ValueError("Frames outside the two cut-ins or the AAC audio changed.")

    final = review / f"nichiyou-umi-short-{args.version}.mp4"
    temporary.rename(final)
    evidence.update(title=TITLE, decode="passed", version=args.version, sha256=sha256(final),
                    original_sha256=previous_render["sha256"], retained_hashes=hashes,
                    retained_frame_count=DURATION * FPS - sum(end - start for start, end in REPLACEMENTS.values()),
                    timeline=timeline)
    (review / "render.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {final}", flush=True)


if __name__ == "__main__":
    main()
