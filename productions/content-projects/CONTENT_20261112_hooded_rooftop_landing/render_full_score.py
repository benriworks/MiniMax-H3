"""Render the 180-second non-looping film score from preserved Lyria sources.

This offline edit never submits an API request and never overwrites a delivery.
Use the matching score_full_v01.json and the media root recorded in the project.
"""

import argparse
import hashlib
import json
import math
import platform
import subprocess
import warnings
from pathlib import Path

import numpy as np
import scipy
from scipy.interpolate import CubicHermiteSpline
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt


RATE = 48000


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(samples):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-f", "f64le", "-ar", str(RATE),
         "-ac", "2", "-i", "pipe:0", "-af",
         "loudnorm=I=-23:TP=-2:LRA=16:print_format=json", "-f", "null", "-"],
        input=samples.astype("<f8", copy=False).tobytes(), capture_output=True, check=True,
    )
    start = result.stderr.rfind(b"{")
    end = result.stderr.find(b"}", start) + 1
    return json.loads(result.stderr[start:end])


def load_source(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"Source hash differs: {path}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", wavfile.WavFileWarning)
        rate, pcm = wavfile.read(path)
    if rate != RATE or pcm.dtype != np.int16 or pcm.ndim != 2 or pcm.shape[1] != 2:
        raise ValueError(f"Expected preserved 48 kHz, 16-bit stereo source: {path}")
    source = pcm.astype(np.float64) / 32768
    repaired = source.copy()
    clipped = (pcm == 32767) | (pcm == -32768)
    repaired_samples = 0
    for channel in range(2):
        spans = np.flatnonzero(np.diff(np.r_[False, clipped[:, channel], False])).reshape(-1, 2)
        values = source[:, channel]
        for first, end in spans:
            left, right = first - 1, end
            if left < 7 or right + 7 >= len(values):
                continue
            before, after = np.arange(-7, 0), np.arange(1, 8)
            before = before[~clipped[left + before, channel]]
            after = after[~clipped[right + after, channel]]
            left_slope = np.dot(before, values[left + before] - values[left]) / max(1, np.dot(before, before))
            right_slope = np.dot(after, values[right + after] - values[right]) / max(1, np.dot(after, after))
            curve = CubicHermiteSpline([left, right], values[[left, right]], [left_slope, right_slope])
            repaired[first:end, channel] = curve(np.arange(first, end))
            repaired_samples += end - first
    # Same restrained sub-bass treatment as the earlier atmosphere approved in tone.
    repaired = sosfiltfilt(butter(2, 24, fs=RATE, btype="highpass", output="sos"), repaired, axis=0)
    low = sosfiltfilt(butter(2, 105, fs=RATE, output="sos"), repaired, axis=0)
    repaired -= (1 - 10 ** (-3 / 20)) * low
    return repaired, {"bytes": path.stat().st_size, "sha256": expected,
                      "duration_seconds": len(pcm) / RATE,
                      "source_full_scale_channel_samples": int(clipped.sum()),
                      "interpolated_channel_samples": int(repaired_samples)}


def envelope(points, frames):
    """Cosine interpolation in amplitude, with flat derivatives at edit boundaries."""
    result = np.empty(frames, dtype=np.float64)
    if points[0][0] != 0 or round(points[-1][0] * RATE) != frames:
        raise ValueError("Envelope must cover the entire cue")
    for (start, left), (end, right) in zip(points, points[1:]):
        a, b = round(start * RATE), round(end * RATE)
        if b <= a or left < 0 or right < 0:
            raise ValueError("Envelope times must increase and gains must be nonnegative")
        weight = (1 - np.cos(np.linspace(0, math.pi, b - a, endpoint=False))) / 2
        result[a:b] = left + (right - left) * weight
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("score_full_v01.json"))
    args = parser.parse_args()
    output = args.output.resolve()
    record_path = output.with_suffix(".render.json")
    if output.exists() or record_path.exists():
        raise SystemExit("Choose a new output name; existing work is preserved")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    sources, source_records = {}, {}
    for name, spec in config["sources"].items():
        sources[name], source_records[name] = load_source(args.media_root / spec["path"], spec["sha256"])
    score = np.zeros((round(config["duration_seconds"] * RATE), 2), dtype=np.float64)
    cues = []
    for cue in config["cues"]:
        a, b = (round(t * RATE) for t in cue["source_seconds"])
        source = sources[cue["source"]]
        if not 0 <= a < b <= len(source):
            raise ValueError(f"Invalid source interval: {cue['id']}")
        segment = source[a:b].copy()
        loudness = measure(segment)
        gain_db = cue["target_lufs"] - float(loudness["input_i"])
        segment *= 10 ** (gain_db / 20)
        segment *= envelope(cue["envelope"], len(segment))[:, None]
        start = round(cue["start_seconds"] * RATE)
        if start < 0 or start + len(segment) > len(score):
            raise ValueError(f"Cue extends outside the film: {cue['id']}")
        score[start:start + len(segment)] += segment
        cues.append({**cue, "source_start_sample": a, "source_end_sample_exclusive": b,
                     "output_start_sample": start, "gain_db": gain_db,
                     "source_segment_loudness": loudness})
    if not np.isfinite(score).all():
        raise ValueError("Non-finite PCM")
    before = measure(score)
    gain_db = min(config["master_lufs"] - float(before["input_i"]),
                  config["maximum_true_peak_dbtp"] - float(before["input_tp"]))
    score *= 10 ** (gain_db / 20)
    if np.max(np.abs(score)) >= 1:
        raise ValueError("Output exceeds PCM full scale")
    for start, end in config["required_silence_seconds"]:
        if np.any(score[round(start * RATE):round(end * RATE)] != 0):
            raise ValueError(f"Music intrudes into required silence: {start}-{end}")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-n", "-f", "f64le", "-ar", str(RATE), "-ac", "2",
         "-i", "pipe:0", "-c:a", "pcm_s24le", "-bitexact", str(output)],
        input=score.astype("<f8", copy=False).tobytes(), check=True,
    )
    record = {
        "file": output.name, "bytes": output.stat().st_size, "sha256": sha256(output),
        "sample_rate": RATE, "channels": 2, "bits_per_sample": 24,
        "samples_per_channel": len(score), "duration_seconds": len(score) / RATE,
        "non_looping": True, "pitch_or_tempo_changes": False,
        "script_sha256": sha256(Path(__file__)), "config_sha256": sha256(args.config),
        "sources": source_records, "cues": cues, "master_gain_db": gain_db,
        "before_master": before, "after_master": measure(score),
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scipy": scipy.__version__, "platform": platform.platform(),
                        "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]},
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("file", "bytes", "sha256", "duration_seconds", "after_master")}, indent=2))


if __name__ == "__main__":
    main()
