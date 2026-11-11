"""Add Maho's childhood opening to the saved v03 edit, with no provider calls."""
import argparse
import hashlib
import json
import re
import wave
from pathlib import Path

import numpy as np

from render_short_drama import DURATION, FPS, RATE, TITLE, ffmpeg, fit_level, make_shot, probe

CUT_TO_PRESENT = 3.
CUT_TO_PHOTO = 7.5
LOCKED_TAIL = 10.
TAIL_SHOTS = ("04-photo-back", "05-decision", "06-shoulder", "07-listening")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crossfade(earlier, later):
    weight = np.linspace(0, 1, len(later), dtype=np.float32)[:, None]
    return earlier * (1. - weight) + later * weight


def shore_bed(duration):
    rng = np.random.default_rng(20261109)
    time = np.arange(round(duration * RATE), dtype=np.float32) / RATE
    noise = rng.normal(size=len(time)).astype(np.float32)
    swell = np.convolve(noise, np.hanning(481).astype(np.float32), mode="same")
    foam = np.convolve(noise, np.hanning(35).astype(np.float32), mode="same")
    roll = .48 + .48 * np.exp(-((time - .58) / .50) ** 2) + .38 * np.exp(-((time - 2.45) / .63) ** 2)
    shore = roll * (swell / np.std(swell) + .37 * foam / np.std(foam))

    paper = np.convolve(rng.normal(size=len(time)).astype(np.float32),
                        np.hanning(11).astype(np.float32), mode="same")
    paper *= np.exp(-((time - 1.37) / .05) ** 2)
    mono = fit_level(shore + .20 * paper, -31., -20.)
    return mono[:, None] * np.array([1., .93], dtype=np.float32)


def revised_mix(previous, output):
    with wave.open(str(previous), "rb") as reader:
        if (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(),
                reader.getnframes()) != (2, 2, RATE, RATE * DURATION):
            raise ValueError("Expected the 30-second v03 stereo PCM master.")
        raw = reader.readframes(RATE * DURATION)
    old = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
    source = old.astype(np.float32) / 32767
    present = round(CUT_TO_PRESENT * RATE)
    photo = round(CUT_TO_PHOTO * RATE)
    locked = round(LOCKED_TAIL * RATE)
    entrance_fade = round(.14 * RATE)
    seam = round(.11 * RATE)

    shore = shore_bed((present + entrance_fade) / RATE)
    shore[:entrance_fade] *= np.linspace(0, 1, entrance_fade, dtype=np.float32)[:, None]
    opening = np.empty((locked, 2), dtype=np.float32)
    opening[:present] = shore[:present]

    # Re-time the original two rings and paper rustle. Blend back before the photo flip.
    opening[present:photo] = source[:photo - present]
    photo_source_start = round(6.5 * RATE)
    opening[photo:] = source[photo_source_start:photo_source_start + locked - photo]
    opening[present:present + entrance_fade] = crossfade(shore[present:present + entrance_fade],
                                                        opening[present:present + entrance_fade])
    opening[photo:photo + seam] = crossfade(source[photo - present:photo - present + seam],
                                           opening[photo:photo + seam])
    opening[-seam:] = crossfade(opening[-seam:], source[locked - seam:locked])

    tail = old[locked:].tobytes()
    with wave.open(str(output), "wb") as target:
        target.setparams((2, 2, RATE, 0, "NONE", "not compressed"))
        target.writeframes(np.rint(opening * 32767).astype("<i2").tobytes() + tail)
    with wave.open(str(output), "rb") as check:
        check.setpos(locked)
        if check.readframes(RATE * DURATION - locked) != tail:
            raise ValueError("The locked PCM tail changed.")
    return hashlib.sha256(tail).hexdigest()


def video_tail_hash(path):
    return ffmpeg("-ss", str(LOCKED_TAIL), "-i", str(path), "-map", "0:v:0",
                  "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-", capture=True).stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("--version", default="v04")
    args = parser.parse_args()
    if not re.fullmatch(r"v04(?:-[a-z0-9-]+)?", args.version):
        parser.error("Use v04 or a distinct v04-* review version.")

    base, pilot = args.base.resolve(), args.pilot.resolve()
    previous = base / "review/v03/nichiyou-umi-short-v03.mp4"
    previous_render = json.loads(previous.with_name("render.json").read_text(encoding="utf-8"))
    if sha256(previous) != previous_render["sha256"]:
        raise ValueError("The saved v03 review does not match its record.")
    childhood = base / "plates/v04"
    cuts = (
        ("00-childhood-offer", childhood / "00-childhood.png", 33, {"still_crop": ""}),
        ("00-childhood-received", childhood / "00-childhood-received.png", 39, {"still_crop": ""}),
        ("01-incoming", base / "plates/v01/01-incoming.png", 54, {"still_crop": "747:1328:59:344"}),
        ("02-envelope-look", base / "shots/v01/02-envelope-look/source.mp4", 54, {"start": 1.5}),
        ("03-pilot-photo", pilot, 60, {"start": 1.13}),
    )
    scratch = base / "edit" / args.version
    review = base / "review" / args.version
    scratch.mkdir(parents=True, exist_ok=False)
    review.mkdir(parents=True, exist_ok=False)
    original_mix = scratch.parent / "v03/mix.wav"
    entries = []
    offset = 0
    for name, source, frames, options in cuts:
        make_shot(scratch / (name + ".mp4"), source, frames, **options)
        entries.append({"shot": name, "start": offset / FPS, "end": (offset + frames) / FPS,
                        "frames": frames, "source_start": options.get("start", 0.),
                        "source_sha256": sha256(source)})
        offset += frames
    if offset != LOCKED_TAIL * FPS or entries[-1]["start"] != CUT_TO_PHOTO:
        raise ValueError("The revised cuts do not meet the locked tail.")

    concat = scratch / "concat.txt"
    concat.write_text("".join(f"file '{name}.mp4'\n" for name, *_ in cuts) +
                      "".join(f"file '../v03/{name}.mp4'\n" for name in TAIL_SHOTS), encoding="ascii")
    mix = scratch / "mix.wav"
    pcm_hash = revised_mix(original_mix, mix)
    temporary = review / "pending.mp4"
    gain = previous_render["master_gain_db"]
    master = f"volume={gain}dB,alimiter=limit=.84:level=false:latency=true:attack=4:release=50"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(mix), "-map", "0:v:0",
           "-map", "1:a:0", "-c:v", "copy", "-af", master, "-c:a", "aac", "-b:a", "192k",
           "-t", str(DURATION), "-movflags", "+faststart", str(temporary))
    evidence = probe(temporary)
    video = evidence["streams"][0]
    if (video["width"], video["height"], int(video["nb_frames"]), video["avg_frame_rate"]) != (
            1080, 1920, DURATION * FPS, "24/1") or float(evidence["format"]["duration"]) != DURATION:
        raise ValueError(evidence)
    ffmpeg("-xerror", "-i", str(temporary), "-map", "0:v", "-map", "0:a", "-f", "null", "-")
    tail_hash = video_tail_hash(temporary)
    if tail_hash != video_tail_hash(previous):
        raise ValueError("The encoded video tail differs from v03.")

    final = review / f"nichiyou-umi-short-{args.version}.mp4"
    temporary.rename(final)
    evidence.update(title=TITLE, decode="passed", version=args.version, sha256=sha256(final),
                    voice_version=previous_render["voice_version"], master_gain_db=gain,
                    prior_review_sha256=previous_render["sha256"], prior_mix_sha256=sha256(original_mix),
                    locked_tail_start=LOCKED_TAIL, video_tail_hash=tail_hash, premaster_tail_sha256=pcm_hash,
                    timeline=entries + previous_render["timeline"][3:])
    (review / "render.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {final}", flush=True)


if __name__ == "__main__":
    main()
