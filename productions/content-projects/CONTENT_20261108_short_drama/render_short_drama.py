"""Assemble the 30-second drama from the saved originals. No provider calls."""
import argparse
import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.studio.editorial_captions import phrase_lines
from tools.studio.music_mix import default_bgm_bed

FPS = 24
RATE = 48000
DURATION = 30
NORMALIZE = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"
TITLE = "日曜、海に行かない？"
DIALOGUE = {
    "v01": (
        ("d01-maho", 19.61, "highpass=f=70,atempo=.97", -17.4, None, None,
         "お父さん。\n日曜、海行かない？", (1.66, 4.10)),
        ("d02-father", 22.99, "highpass=f=265,lowpass=f=3500,atempo=.93", -18.1, None, None,
         "じゃあ、\nおにぎり作っとくか。", (.39, 2.72)),
    ),
    "v03": (
        ("d01-maho", 19.36, "highpass=f=70", -17.4, .20, 2.98,
         "お父さん。\n日曜、海に行かない？", (1.38, 4.31)),
        ("d02-father", 23.20, "highpass=f=220,lowpass=f=3800", -18.1, .18, 2.22,
         "じゃあ、\nおにぎりを作っておくよ。", (.48, 2.82)),
    ),
}


def run(*args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=capture)


def ffmpeg(*args, cwd=None, capture=False):
    return run("ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-filter_threads", "2", "-filter_complex_threads", "2", *args, cwd=cwd, capture=capture)


def load_pcm(path, filters=None, start=None, duration=None):
    args = ["-i", str(path)]
    if start is not None:
        args = ["-ss", str(start), *args]
    if duration is not None:
        args.extend(("-t", str(duration)))
    if filters:
        args.extend(("-af", filters))
    result = ffmpeg(*args, "-vn", "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-", capture=True)
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def fit_level(samples, rms_db, peak_db=-3):
    rms = np.sqrt(np.mean(np.square(samples, dtype=np.float64)))
    peak = np.max(np.abs(samples))
    if not peak:
        return samples
    return samples * min(10 ** (rms_db / 20) / rms, 10 ** (peak_db / 20) / peak)


def fade(samples, seconds):
    size = min(round(seconds * RATE), len(samples) // 2)
    ramp = np.linspace(0, 1, size, endpoint=False, dtype=np.float32)
    samples[:size] *= ramp
    samples[-size:] *= ramp[::-1]
    return samples


def place(track, mono, start, pan=0.):
    offset = round(start * RATE)
    mono = mono[:len(track) - offset]
    track[offset:offset + len(mono)] += mono[:, None] * (1. - pan, 1. + pan)


def write_wave(path, samples):
    with wave.open(str(path), "wb") as target:
        target.setparams((2, 2, RATE, 0, "NONE", "not compressed"))
        target.writeframes((np.clip(samples, -1., 1.) * 32767).astype("<i2").tobytes())


def piano(midi, seconds=3.8):
    t = np.arange(round(seconds * RATE), dtype=np.float32) / RATE
    fundamental = 440. * 2 ** ((midi - 69) / 12)
    values = np.zeros(len(t), dtype=np.float32)
    for number, weight, decay in ((1,.82,1.05), (2,.27,.53), (3,.11,.32), (4,.06,.21), (5,.025,.13)):
        f = fundamental * number * np.sqrt(1 + number * number * .00022)
        beat = .78 * np.sin(2 * np.pi * f * t) + .22 * np.sin(2 * np.pi * (f + .38) * t)
        values += weight * beat * np.exp(-t / decay)
    return fade(values * (1 - np.exp(-t / .006)), .11)


def tone(seconds, frequencies):
    t = np.arange(round(seconds * RATE), dtype=np.float32) / RATE
    return fade(sum(np.sin(2 * np.pi * f * t) for f in frequencies) / len(frequencies), .025)


def build_audio(base, pilot, directory, voice_version):
    tts = base / "audio" / voice_version / "tts"
    beds = {name: np.zeros((RATE * DURATION, 2), dtype=np.float32)
            for name in ("room-and-effects", "piano", "dialogue")}
    effects = beds["room-and-effects"]
    rng = np.random.default_rng(20261108)
    # Continuous rain bed with slow variation and small randomized drops.
    hiss = rng.normal(0., 1., RATE * DURATION).astype(np.float32)
    rain = np.convolve(hiss, np.hanning(19).astype(np.float32), mode="same")
    rain *= .89 + .11 * np.sin(np.arange(len(rain)) / RATE * 2 * np.pi / 5.1)
    place(effects, fade(fit_level(rain, -38, -27), .38), 0)
    for when in (.17, 1.21):
        place(effects, .100 * tone(.24, (157, 231)), when)
    paper = load_pcm(pilot, "highpass=f=125,lowpass=f=5000", start=.70, duration=3.50)
    place(effects, fade(fit_level(paper, -31, -19), .16), 6.50)
    flip = rng.normal(0, 1, round(RATE * .23)).astype(np.float32)
    place(effects, fade(fit_level(np.convolve(flip, [1, .65, -.45], mode="same"), -32, -21), .065), 9.96)
    for when in (17.89, 18.53):
        place(effects, .047 * tone(.29, (440, 480)), when)
    place(effects, .019 * tone(.075, (550,)), 19.08)

    # Original piano cue. Separate from the environment and voices for review revisions.
    music = beds["piano"]
    for when, midi, gain, pan in (
        (13.05, 62, .021, -.12), (13.84, 69, .016, .13), (15.23, 66, .016, .08),
        (16.59, 71, .014, .13), (18.00, 57, .012, -.17), (18.71, 64, .010, .08),
        (21.50, 62, .008, -.08), (24.17, 69, .008, .08), (26.35, 62, .018, -.14),
        (26.59, 66, .014, .12), (26.93, 69, .015, .09), (27.80, 74, .011, .08),
    ):
        place(music, gain * piano(midi), when, pan)
    speech_span = {"v01": (19.68, 25.43), "v03": (19.36, 25.50)}[voice_version]
    music = default_bgm_bed(music, DURATION, [speech_span], sample_rate=RATE)
    music[-RATE:] *= np.linspace(1., 0., RATE, dtype=np.float32)[:, None]
    beds["piano"] = music

    for name, placement, filters, target_level, trim_start, trim_length, _, _ in DIALOGUE[voice_version]:
        voice = load_pcm(tts / name / "voice.wav", filters, start=trim_start, duration=trim_length)
        line = fit_level(voice, target_level, -3.4)
        place(beds["dialogue"], fade(line, .035), placement)
    mix = sum(beds.values())
    peak_gain = min(1., .82 / np.max(np.abs(mix)))
    for name, stem in beds.items():
        write_wave(directory / (name + ".wav"), stem)
    write_wave(directory / "mix.wav", mix * peak_gain)


def make_caption(path, value):
    lines = phrase_lines(value, 842, 64)
    if len(lines) > 2:
        raise ValueError("Dialogue exceeds two lines.")
    font = ImageFont.truetype(r"C:\Windows\Fonts\YuGothB.ttc", 64)
    canvas = Image.new("RGBA", (1080, 180))
    painter = ImageDraw.Draw(canvas)
    for row, line in enumerate(lines):
        left, top, right, bottom = painter.textbbox((0, 0), line, font=font, stroke_width=3)
        if right - left > 842:
            raise ValueError("Actual rendered dialogue does not fit.")
        y = 8 + (2 - len(lines)) * 36 + row * 78
        pos = ((1080 - right - left) // 2, y - top)
        painter.text((pos[0], pos[1] + 4), line, font=font, fill=(11, 13, 16, 225),
                     stroke_width=5, stroke_fill=(11, 13, 16, 210))
        painter.text(pos, line, font=font, fill=(255, 252, 244, 255),
                     stroke_width=2, stroke_fill=(14, 16, 19, 235))
    canvas.save(path)


def make_shot(output, source, frames, *, start=0., still_crop=None, reframing=None,
              caption=None, caption_window=None, end_fade=False):
    if still_crop is not None:
        # Sample the still at 2x resolution to keep the camera move subpixel-smooth.
        z = f"1+0.035*on/{frames-1}"
        crop = f"crop={still_crop}," if still_crop else ""
        video = (crop + "scale=2160:3840:force_original_aspect_ratio=increase:flags=lanczos,"
                 "crop=2160:3840,zoompan="
                 f"z='{z}':x='iw/2-iw/(2*zoom)':y='ih/2-ih/(2*zoom)':d={frames}:s=1080x1920:fps=24,setsar=1")
    else:
        video = (reframing + "," if reframing else "") + NORMALIZE + ",fps=24"
    if end_fade:
        video += f",fade=t=out:st={(frames-11)/FPS}:d={11/FPS}"
    args = ["-ss", str(start), "-i", str(source)]
    if caption:
        args.extend(("-i", str(caption), "-filter_complex",
                     f"[0:v]{video}[shot];[shot][1:v]overlay=0:1448:enable='between(t,{caption_window[0]},{caption_window[1]})'[v]",
                     "-map", "[v]"))
    else:
        args.extend(("-map", "0:v:0", "-vf", video))
    ffmpeg(*args, "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "16", "-pix_fmt", "yuv420p", "-threads", "4", str(output))


def probe(path):
    result = run("ffprobe", "-v", "error", "-show_entries",
                 "format=size,duration:stream=codec_name,codec_type,width,height,nb_frames,avg_frame_rate",
                 "-of", "json", str(path), capture=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("--version", default="v01")
    parser.add_argument("--master-gain-db", type=float, default=0.)
    parser.add_argument("--voice-version", choices=DIALOGUE, default="v01")
    args = parser.parse_args()
    base, pilot = args.base.resolve(), args.pilot.resolve()
    scratch = base / "edit" / args.version
    review = base / "review" / args.version
    final = review / f"nichiyou-umi-short-{args.version}.mp4"
    if final.exists():
        raise FileExistsError(final)
    scratch.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)
    c1, c2 = (scratch / "d01-caption.png"), (scratch / "d02-caption.png")
    first, second = DIALOGUE[args.voice_version]
    make_caption(c1, first[-2])
    make_caption(c2, second[-2])
    plates = base / "plates/v01"
    motion = base / "shots/v01"
    shots = (
        ("01-incoming", plates / "01-incoming.png", 66, {"still_crop": "747:1328:59:344"}),
        ("02-envelope-look", motion / "02-envelope-look/source.mp4", 90, {}),
        ("03-pilot-photo", pilot, 84, {"start": .70}),
        ("04-photo-back", plates / "04-photo-back.png", 72, {"still_crop": ""}),
        ("05-decision", motion / "05-decision/source.mp4", 120,
         {"start": .64, "reframing": "crop=540:960:(iw-ow)/2:32"}),
        ("06-shoulder", motion / "06-shoulder/source.mp4", 114,
         {"start": .10, "caption": c1, "caption_window": first[-1]}),
        ("07-listening", motion / "07-listening/source.mp4", 174,
         {"start": .25, "caption": c2, "caption_window": second[-1], "end_fade": True}),
    )
    assert sum(shot[2] for shot in shots) == DURATION * FPS
    offset = 0
    index = []
    for name, original, frames, settings in shots:
        make_shot(scratch / f"{name}.mp4", original, frames, **settings)
        index.append({"shot": name, "start": offset / FPS, "end": (offset + frames) / FPS,
                      "frames": frames, "source_start": settings.get("start", 0),
                      "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest()})
        offset += frames
        print(f"{name}: {frames} frames", flush=True)
    (scratch / "concat.txt").write_text("".join(f"file '{name}.mp4'\n" for name, *_ in shots), encoding="ascii")
    build_audio(base, pilot, scratch, args.voice_version)
    temporary = review / "pending.mp4"
    master = []
    if args.master_gain_db:
        master = ["-af", f"volume={args.master_gain_db}dB,alimiter=limit=.84:level=false:latency=true:attack=4:release=50"]
    ffmpeg("-f", "concat", "-safe", "1", "-i", str(scratch / "concat.txt"), "-i", str(scratch / "mix.wav"),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *master, "-c:a", "aac", "-b:a", "192k",
           "-t", str(DURATION), "-movflags", "+faststart", str(temporary))
    evidence = probe(temporary)
    video = evidence["streams"][0]
    assert (video["width"], video["height"], int(video["nb_frames"])) == (1080, 1920, 720), evidence
    assert abs(float(evidence["format"]["duration"]) - DURATION) < .01, evidence
    ffmpeg("-xerror", "-i", str(temporary), "-map", "0:v", "-map", "0:a", "-f", "null", "-")
    temporary.rename(final)
    evidence.update(title=TITLE, decode="passed", timeline=index, master_gain_db=args.master_gain_db,
                    voice_version=args.voice_version,
                    sha256=hashlib.sha256(final.read_bytes()).hexdigest())
    (review / "render.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {final}", flush=True)


if __name__ == "__main__":
    main()
