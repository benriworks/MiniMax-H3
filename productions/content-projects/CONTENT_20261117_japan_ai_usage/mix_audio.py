"""Mix the user's verified local track with the recorded narration."""
from pathlib import Path
import json
import re
import subprocess

import numpy as np

from prepare import OUT, SOURCES, digest
from tools.studio.longform_audio import SR, read_voice, write_pcm
from tools.studio.music_mix import default_bgm_bed


def ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *args],
                          capture_output=True, check=True)


def loudness(path):
    result = ffmpeg("-i", str(path), "-vn", "-af",
                    "loudnorm=I=-15:TP=-1.5:LRA=8:print_format=json", "-f", "null", "-")
    return json.loads(re.findall(rb'\{\s*"input_i".*?\}', result.stderr, re.S)[-1])


def normalize(path, target, measurement):
    keys = ("i", "tp", "lra", "thresh")
    measured = ":".join(f"measured_{key}={measurement['input_'+key]}" for key in keys)
    af = f"loudnorm=I=-15:TP=-1.5:LRA=8:{measured}:offset={measurement['target_offset']}:linear=true"
    ffmpeg("-v", "error", "-n", "-i", str(path), "-af", af, "-ar", "48000",
           "-c:a", "pcm_s16le", str(target))


def track_for(length, source_pcm, overlap, start=0):
    if overlap < 1 or overlap * 2 >= len(source_pcm) or start + overlap >= len(source_pcm):
        raise ValueError("Invalid music seam")
    out = np.zeros((length, 2), dtype=np.float32)
    first = source_pcm[start:start + length]
    out[:len(first)] = first
    cursor = len(first)
    repeats = 0
    while cursor < length:
        left = cursor - overlap
        count = min(len(source_pcm), length - left)
        blend = np.linspace(0, 1, overlap, dtype=np.float32)[:, None]
        out[left:cursor] *= 1 - blend
        out[left:cursor] += source_pcm[:overlap] * blend
        out[cursor:left+count] = source_pcm[overlap:count]
        cursor = left + count
        repeats += 1
    return out, repeats


def mix(plan, folder):
    folder.mkdir(parents=True, exist_ok=True)
    spec = SOURCES["music"]
    path = OUT / "_private" / spec["original"]
    if digest(path) != spec["sha256"]:
        raise ValueError("Local music differs from the selected inventory copy")
    measure = loudness(path)
    gain_db = -26.0 - float(measure["input_i"])
    length = round(plan["seconds"] * SR)
    # Keep the musical intro, drop the original tail, and crossfade only when needed.
    decoded = ffmpeg("-v", "error", "-i", str(path), "-t", "99.2", "-ar", str(SR),
                     "-ac", "2", "-f", "f32le", "pipe:1")
    pcm = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    music, count = track_for(length, pcm, round(1.6 * SR))
    music *= 10 ** (gain_db / 20)
    speech = np.zeros(length, dtype=np.float32)
    spans = []
    for chapter in plan["chapters"]:
        for turn in chapter["turns"]:
            start = round(turn["start"] * SR)
            samples = read_voice(Path(turn["voice_path"]))
            stop = start + len(samples)
            if stop > length or (spans and turn["start"] < spans[-1][1]):
                raise ValueError("Dialogue overlaps or exceeds the cut")
            peak = np.quantile(np.abs(samples), .95)
            voice_gain = min(1.7, .24 / max(peak, .02))
            speech[start:stop] = samples * voice_gain
            if spans and turn["start"] - spans[-1][1] < 2.0:
                # Hold the music down through brief turn and scene gaps.
                spans[-1][1] = turn["end"]
            else:
                spans.append([turn["start"], turn["end"]])
    bed = default_bgm_bed(music, plan["seconds"], spans, sample_rate=SR)
    bed[-round(.62*SR):] *= np.linspace(1, 0, round(.62*SR))[:, None]
    mixed = speech[:, None] + bed
    peak = float(np.max(np.abs(mixed)))
    if peak > .96:
        mixed *= .96 / peak
    write_pcm(folder / "speech.wav", speech)
    write_pcm(folder / "mix-premaster.wav", mixed)
    target = folder / "mix.wav"
    normalize(folder / "mix-premaster.wav", target, loudness(folder / "mix-premaster.wav"))
    return target, dict(track=spec["title"], credit=spec["author"], sha256=spec["sha256"],
       source_lufs=float(measure["input_i"]), input_gain_db=gain_db, clip_end_seconds=99.2,
       crossfade_seconds=1.6, repeat_count=count, gain_profile="explanation_v1",
       speech_blocks_joined_under_seconds=2.0, peak_before_mix_normalization=peak)
