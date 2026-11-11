"""Render the episode from saved H3 clips, stills and two voice WAVs."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "CONTENT_20261108_short_drama"))
from render_short_drama import (
    DURATION, FPS, RATE, default_bgm_bed, fade, ffmpeg, fit_level, load_pcm, make_caption,
    make_shot, piano, place, probe, tone, write_wave,
)

TITLE = "お父さんも、入って。"
SHUTTER_FRAME = 636
FIRST_FATHER = ("d01-father", "v01", "ほら、そこ立って。\n撮るぞ。", .38, .16, 2.84, (.46, 3.16))
FINAL_FATHER = ("d01-father", "v02", "ほら、そこに立って。\n撮るぞ。", .36, .21, 2.49, (.44, 2.80))
MAHO = ("d02-maho", "v01", "お父さんも、入って。", 18.57, .13, 2.08, (18.62, 20.58))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audio_mix(media, edit, dialogue, tap):
    shape = (RATE * DURATION, 2)
    waves, music, voices = (np.zeros(shape, dtype=np.float32) for _ in range(3))
    rng = np.random.default_rng(20261111)
    time = np.arange(shape[0], dtype=np.float32) / RATE
    swell = .62 + .21 * np.sin(2 * np.pi * time / 5.5) + .12 * np.sin(2 * np.pi * time / 8.9 + 1.4)
    for pan in (-.24, .24):
        wash = np.convolve(rng.standard_normal(shape[0], dtype=np.float32), np.hanning(51), mode="same")
        place(waves, fade(fit_level(wash * swell, -38, -28), .50), 0, pan)
    paper = rng.standard_normal(round(RATE * .27), dtype=np.float32)
    paper = np.convolve(paper, [1, .5, -.6], mode="same")
    place(waves, fade(fit_level(paper, -31, -21), .065), 7.90, -.10)
    for when, length, volume, freq in (
        (tap, .075, .022, 760), (23.50, .11, .024, 860),
        (24.50, .11, .028, 860), (25.50, .12, .030, 1050),
    ):
        place(waves, volume * tone(length, (freq,)), when)
    for delay, rms in ((0, -19.5), (.052, -25)):
        click = rng.standard_normal(round(RATE * .09), dtype=np.float32)
        click = np.convolve(click, [1, .5, .3], mode="same")
        click *= np.exp(-np.arange(len(click)) / (RATE * .014))
        place(waves, fade(fit_level(click, rms, -7), .004), SHUTTER_FRAME / FPS + delay)

    # The same sparse D-major piano timbre as the first episode.
    for when, midi, level, pan in (
        (7.85, 62, .036, -.15), (9.15, 69, .029, .10), (11.65, 66, .035, -.05),
        (13.00, 71, .026, .14), (15.50, 57, .027, -.14), (17.25, 64, .023, .08),
        (21.60, 62, .030, -.08), (23.30, 69, .024, .10), (26.58, 62, .042, -.14),
        (26.80, 66, .031, .12), (27.11, 69, .036, .08), (28.05, 74, .022, -.04),
    ):
        place(music, level * piano(midi), when, pan)
    music = default_bgm_bed(music, DURATION, [line[-1] for line in dialogue], sample_rate=RATE)
    music[-RATE:] *= np.linspace(1., 0., RATE, dtype=np.float32)[:, None]

    dialogue_sources = []
    for name, source_version, text, placement, source_start, length, caption_window in dialogue:
        path = media / "audio" / source_version / "tts" / name / "voice.wav"
        proof = json.loads(path.with_name("verified.json").read_text(encoding="utf-8"))
        if sha(path) != proof["sha256"]:
            raise ValueError(f"Speech source changed: {name}")
        samples = load_pcm(path, "highpass=f=75", start=source_start, duration=length)
        place(voices, fade(fit_level(samples, -16.5, -3.5), .035), placement)
        dialogue_sources.append({"line": name, "version": source_version,
                                 "sha256": proof["sha256"], "start": placement,
                                 "source_start": source_start, "duration": len(samples) / RATE,
                                 "caption": text, "caption_window": caption_window})
    for name, stem in (("pier-and-effects", waves), ("piano", music), ("dialogue", voices)):
        write_wave(edit / f"{name}.wav", stem)
    mix = waves + music + voices
    write_wave(edit / "mix.wav", mix * min(1., .88 / np.max(np.abs(mix))))
    return dialogue_sources


def loudness(path):
    measurement = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn",
         "-af", "loudnorm=I=-17:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    return json.JSONDecoder().raw_decode(measurement[measurement.rfind("{"):])[0]


def render(media, previous, version, initial):
    plates = media / "plates/v01"
    motion = media / "shots/v01"
    edit = media / "edit" / version
    review = media / "review" / version
    if edit.exists() or review.exists():
        raise FileExistsError("Use a new version to preserve the prior output")
    edit.mkdir(parents=True)
    review.mkdir(parents=True)
    c1, c2 = (edit / "d01-caption.png"), (edit / "d02-caption.png")
    father = FIRST_FATHER if initial else FINAL_FATHER
    dialogue = (father, MAHO)
    make_caption(c1, father[2])
    make_caption(c2, MAHO[2])
    onigiri = (plates / "02-onigiri.png", {"still_crop": ""}) if initial else (
        motion / "02-onigiri/source.mp4", {"start": .50},
    )
    shots = (
        ("01-camera", motion / "01-camera/source.mp4", 96,
         {"start": 2 / FPS, "caption": c1, "caption_window": father[-1]}),
        ("02-onigiri", onigiri[0], 96, onigiri[1]),
        ("03-note", previous / "plates/v06/04-photo-back.png", 84, {"still_crop": ""}),
        ("04-maho", motion / "04-maho/source.mp4", 120, {}),
        ("05-timer", motion / "05-timer/source.mp4", 120,
         {"caption": c2, "caption_window": tuple(t - 16.5 for t in MAHO[-1])}),
        ("06-together", motion / "06-together/source.mp4", 120, {"start": 4 / FPS}),
    )

    timeline = []
    offset = 0
    for name, source, count, settings in shots:
        make_shot(edit / f"{name}.mp4", source, count, **settings)
        timeline.append({"shot": name, "start_frame": offset, "frames": count,
                         "source_start": settings.get("start", 0), "source_sha256": sha(source)})
        offset += count
        print(f"{name}: {count} frames", flush=True)
    if offset != SHUTTER_FRAME:
        raise ValueError("Shutter timing differs from the cut list")
    # The shutter turns the last moving frame into the new photograph.
    photo = edit / "07-photograph.png"
    ffmpeg("-i", str(edit / "06-together.mp4"), "-vf", "select=eq(n\\,119)",
           "-frames:v", "1", "-update", "1", str(photo))
    hold = DURATION * FPS - offset
    make_shot(edit / "07-photograph.mp4", photo, hold,
              reframing=f"tpad=stop_mode=clone:stop_duration={hold / FPS}")
    timeline.append({"shot": "07-photograph", "start_frame": offset, "frames": hold,
                     "source_start": 0, "source_sha256": sha(photo)})
    concat = edit / "concat.txt"
    concat.write_text("".join(f"file '{shot['shot']}.mp4'\n" for shot in timeline), encoding="ascii")

    dialogue_sources = audio_mix(media, edit, dialogue, 17.08 if initial else 17.90)
    mix = edit / "mix.wav"
    input_lufs = float(loudness(mix)["input_i"])
    gain = round(max(-8., min(8., -17. - input_lufs)), 2)
    pending = review / "pending.mp4"
    master = f"volume={gain}dB,alimiter=limit=.82:level=false:latency=true:attack=4:release=55"
    ffmpeg("-f", "concat", "-safe", "1", "-i", str(concat), "-i", str(mix),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", master,
           "-c:a", "aac", "-b:a", "192k", "-t", str(DURATION), "-movflags", "+faststart", str(pending))
    metadata = probe(pending)
    video, audio = metadata["streams"]
    if (video["width"], video["height"], int(video["nb_frames"]), video["avg_frame_rate"]) != (1080, 1920, 720, "24/1"):
        raise ValueError(f"Unexpected video format: {video}")
    if abs(float(metadata["format"]["duration"]) - DURATION) >= .01 or audio["codec_name"] != "aac":
        raise ValueError(f"Unexpected duration or audio codec: {metadata}")
    ffmpeg("-xerror", "-i", str(pending), "-map", "0:v", "-map", "0:a", "-f", "null", "-")
    levels = loudness(pending)
    if not -18 <= float(levels["input_i"]) <= -14 or float(levels["input_tp"]) > -1:
        raise ValueError(f"Review audio is outside the listening targets: {levels}")
    final = review / f"otousan-mo-haitte-{version}.mp4"
    pending.rename(final)
    metadata.update(title=TITLE, timeline=timeline, dialogue=dialogue_sources, decode="passed",
                    master_gain_db=gain, loudness_lufs=float(levels["input_i"]),
                    true_peak_dbtp=float(levels["input_tp"]), sha256=sha(final))
    (review / "render.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(f"Verified {final}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("previous", type=Path)
    parser.add_argument("--version", default="v02")
    parser.add_argument("--initial", action="store_true", help="reproduce the first assembly")
    args = parser.parse_args()
    if not args.version.startswith("v") or Path(args.version).name != args.version:
        parser.error("Use a simple version name starting with v")
    render(args.media.resolve(), args.previous.resolve(), args.version, args.initial)


if __name__ == "__main__":
    main()
