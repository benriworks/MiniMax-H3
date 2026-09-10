"""Non-destructive, local Haruka denoise listening candidates; not a Studio preset.

The input is uncompressed narration, not previously compressed AAC. Filter
settings are hypotheses, not a measured noise profile. Acoustic improvement
requires listening; bandwidth reduction and successful decoding do not prove it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/productions/SHORT_20260905_claude_desktop_15s"
EXECUTION = BASE / "executions/0A7434AB8A1623781F69BAFAE604A22868C02F91844E705A9CB3287E727B8605/20260905T060424918871Z"
SOURCE_WAV = EXECUTION / "narration.wav"
SOURCE_VIDEO = BASE / "ClaudeCode_desktop_15s_captioned.mp4"
EXPECTED = {
    SOURCE_WAV: "1F8A708E5296BC529CD0FB192D282069329B72726A9341E49321709836A83707",
    SOURCE_VIDEO: "639567BAE52A1219B7664C347CA4026E3C4D543DC9234DEEDC5FFF9FFD42E2EF",
}
RATE = 48000
FRAMES = RATE * 15
FILTERS = {
    "control": "anull",
    "mild": "highpass=f=60,afftdn=nr=6:nf=-45:tn=0:gs=8,treble=g=-2:f=3500:t=q:w=0.7",
    "strong": "highpass=f=60,afftdn=nr=10:nf=-38:tn=0:gs=12,treble=g=-4:f=3000:t=q:w=0.7,lowpass=f=6500:p=2",
}


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def record(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}


def command(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-5000:])
    return result


def save_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def wav(path: Path, samples: np.ndarray) -> None:
    if not np.isfinite(samples).all() or np.max(np.abs(samples)) >= 1:
        raise ValueError("Non-finite or clipping PCM rejected")
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        handle.writeframes(np.rint(samples * 32767).astype("<i2").tobytes())


def measure(path: Path) -> dict:
    result = command(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn",
                      "-af", "ebur128=peak=true", "-f", "null", "-"])
    log = result.stderr.decode("utf-8", "replace")
    lufs = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", log)
    peaks = re.findall(r"Peak:\s+(-?\d+(?:\.\d+)?) dBFS", log)
    if not lufs or not peaks:
        raise ValueError("Missing finite loudness/true peak measurements")
    return {"integrated_lufs": float(lufs[-1]), "true_peak_dbfs": float(peaks[-1])}


def delay(reference: np.ndarray, candidate: np.ndarray) -> int:
    """Estimate a fixed filter delay only, not words or perceptual quality."""
    size = 1 << (2 * len(reference) - 1).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(candidate, size) * np.conj(np.fft.rfft(reference, size)), size)
    limit = RATE // 10
    lags = np.arange(-limit, limit + 1)
    result = int(lags[np.argmax(correlation[lags % size])])
    if abs(result) == limit:
        raise ValueError("Filter alignment reached the search boundary")
    return result


def align(samples: np.ndarray, lag: int) -> np.ndarray:
    result = np.zeros(FRAMES, dtype=np.float64)
    if lag > 0:
        result[:-lag] = samples[lag:]
    elif lag < 0:
        result[-lag:] = samples[:lag]
    else:
        result[:] = samples
    return result


def video_payload_hash(path: Path) -> str:
    return command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
                    "-map", "0:v:0", "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-"]).stdout.decode().strip()


def spectral_bands(samples: np.ndarray, reference: np.ndarray) -> dict:
    size, hop = 2048, 512
    window = np.hanning(size)
    bins = np.fft.rfftfreq(size, 1 / RATE)
    total = np.zeros(len(bins))
    active = 0
    for start in range(0, len(samples) - size + 1, hop):
        ref = reference[start:start + size]
        if np.mean(ref * ref) < 10 ** (-38 / 10):
            continue
        total += np.abs(np.fft.rfft(samples[start:start + size] * window)) ** 2
        active += 1
    return {"reference_active_windows": active,
            "band_energy": {f"{lo}-{hi}Hz": float(total[(bins >= lo) & (bins < hi)].sum())
                            for lo, hi in [(80, 1000), (1000, 4000), (4000, 8000)]},
            "interpretation": "Speech and noise together; NOT a measured noise reduction or quality score"}


def main() -> None:
    for path, expected in EXPECTED.items():
        if digest(path) != expected:
            raise ValueError(f"Original changed: {path.name}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = BASE / "denoise" / stamp
    output.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    manifest = {"schema_version": 1, "status": "running", "policy": "haruka-denoise-listening-candidates-v1",
                "sources": [record(path) for path in EXPECTED], "script": record(Path(__file__)),
                "ffmpeg": command(["ffmpeg", "-version"]).stdout.decode().splitlines()[0],
                "network_used": False, "new_synthesis": False, "studio_run_id": None, "studio_job_id": None,
                "filters": FILTERS, "candidates": {}, "subjective_quality": "awaiting_user_listening",
                "scope": "Standalone experimental copies, not replacements or Studio default presets"}
    save_json(output / "manifest.json", manifest)
    try:
        arrays, pre = {}, {}
        for name, filters in FILTERS.items():
            print(f"Preparing {name}", flush=True)
            chain = f"aresample={RATE},aformat=sample_fmts=fltp:channel_layouts=mono,apad=whole_dur=15,atrim=duration=15,{filters}"
            result = command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(SOURCE_WAV),
                              "-af", chain, "-ar", str(RATE), "-ac", "1", "-f", "f32le", "-"])
            samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)
            if len(samples) < FRAMES - RATE // 10 or not np.isfinite(samples).all():
                raise ValueError("Unexpected filtered audio length or non-finite samples")
            actual_length = len(samples)
            samples = np.pad(samples[:FRAMES], (0, max(0, FRAMES - len(samples))))
            lag = 0 if name == "control" else delay(arrays["control"], samples)
            arrays[name] = align(samples, lag)
            before = output / f"narration_{name}_before_gain.wav"
            wav(before, arrays[name])
            pre[name] = measure(before)
            manifest["candidates"][name] = {"filter": filters, "filter_output_samples": actual_length,
                "alignment_delay_samples": lag, "alignment_delay_ms": lag * 1000 / RATE,
                "alignment_method": "global PCM cross-correlation within +/-100ms, not word alignment",
                "before_gain": record(before), "before_gain_measurements": pre[name]}
        # Equal integrated loudness with common headroom, no dynamic compressor.
        target = min(-18.0, *(row["integrated_lufs"] - 1.5 - row["true_peak_dbfs"] for row in pre.values()))
        manifest["common_target_lufs"] = target
        source_hash = video_payload_hash(SOURCE_VIDEO)
        manifest["original_video_payload_hash"] = source_hash
        for name in FILTERS:
            gain_db = target - pre[name]["integrated_lufs"]
            samples = arrays[name] * 10 ** (gain_db / 20)
            arrays[name] = samples
            candidate_wav = output / f"narration_{name}.wav"
            wav(candidate_wav, samples)
            candidate_video = output / f"ClaudeCode_desktop_15s_{name}.mp4"
            command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                     "-i", str(SOURCE_VIDEO), "-i", str(candidate_wav), "-map", "0:v:0", "-map", "1:a:0",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", "2",
                     "-t", "15", "-map_metadata", "-1", "-movflags", "+faststart", str(candidate_video)])
            payload_hash = video_payload_hash(candidate_video)
            if payload_hash != source_hash:
                raise ValueError("Video payload changed")
            command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(candidate_video), "-f", "null", "-"])
            facts = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(candidate_video)]).stdout)
            video = next(s for s in facts["streams"] if s["codec_type"] == "video")
            audio = next(s for s in facts["streams"] if s["codec_type"] == "audio")
            if len(facts["streams"]) != 2 or video["width"] != 1080 or video["height"] != 1920 or video["nb_frames"] != "360" or abs(float(facts["format"]["duration"]) - 15) > .001 or audio["codec_name"] != "aac":
                raise ValueError("Candidate media contract mismatch")
            measurement = measure(candidate_video)
            if measurement["true_peak_dbfs"] > -1.0 or abs(measurement["integrated_lufs"] - target) > .3:
                raise ValueError("Loudness matching or peak check failed")
            manifest["candidates"][name].update(gain_db=gain_db, wav=record(candidate_wav),
                mp4=record(candidate_video), encoded_audio_measurements=measurement, video_payload_hash=payload_hash,
                technical_check="pass", spectral=spectral_bands(samples, arrays["control"]))
            save_json(output / f"probe-{name}.json", facts)
            save_json(output / "manifest.json", manifest)
            print(f"Verified {name}: {measurement}", flush=True)
        # Same two closing sentences, same loudness, with a 350ms gap.
        clips, rows, cursor = [], [], 0
        for name in FILTERS:
            excerpt = arrays[name][int(10.2 * RATE):int(14.5 * RATE)].copy()
            fade = int(.01 * RATE)
            excerpt[:fade] *= np.linspace(0, 1, fade)
            excerpt[-fade:] *= np.linspace(1, 0, fade)
            rows.append({"variant": name, "start_seconds": cursor / RATE, "end_seconds": (cursor + len(excerpt)) / RATE,
                         "source_interval_seconds": [10.2, 14.5]})
            clips.append(excerpt)
            cursor += len(excerpt)
            if name != "strong":
                clips.append(np.zeros(int(.35 * RATE)))
                cursor += int(.35 * RATE)
        comparison = output / "comparison_original_mild_strong.wav"
        wav(comparison, np.concatenate(clips))
        manifest["comparison"] = {"audio": record(comparison), "sections": rows, "note": "control = original voice resampled and loudness matched; no denoise"}
        for path, expected in EXPECTED.items():
            if digest(path) != expected:
                raise ValueError("Original changed during processing")
        manifest.update(status="succeeded", elapsed_seconds=round(time.monotonic() - began, 3), originals_unchanged=True)
        save_json(output / "manifest.json", manifest)
        print(json.dumps({"output": str(output), "elapsed_seconds": manifest["elapsed_seconds"], "target_lufs": target}), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        save_json(output / "manifest.json", manifest)
        raise


if __name__ == "__main__":
    main()
