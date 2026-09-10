"""Local, non-destructive Sayaka diagnostics and matched listening copies.

This is production-specific investigation, not a Studio provider or quality gate.
Periodic speech energy is NOT automatically noise. No output replaces a cache,
registered artifact, or delivery. Fixed v3 lineage is read from SQLite read-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import wave

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/studio/verification/claude-desktop-real-20260906"
RESULT = BASE / "renders/A688F922A7712EF8050029A750EE9F17B8649037CA2021912C679E360DB7F9FC/result.json"
RUN_ID = "run_7b1ed11efe9c429aa5639a9a23140bbe"
RATE = 48000
FRAMES = 21 * RATE


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def record(path: Path) -> dict:
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    return {"path": name, "bytes": path.stat().st_size, "sha256": sha(path)}


def write_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def checked_path(row: dict) -> Path:
    rel = Path(row["rel_path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Artifact is outside the workspace")
    path = ROOT / rel
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (path, *path.parents) if p != ROOT.parent):
        raise ValueError("Linked artifact path rejected")
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("Artifact must be a regular workspace file")
    if path.stat().st_size != row["bytes"] or sha(path) != row["sha256"].upper():
        raise ValueError("Artifact bytes or hash mismatch")
    return path


def sources() -> tuple[dict, dict[str, Path], dict]:
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    if result["render"]["run_id"] != RUN_ID or result["render"]["status"] != "succeeded":
        raise ValueError("This investigation must resolve completed v3")
    prod = result["production_id"]
    paths, artifacts = {}, {}
    with sqlite3.connect((ROOT / "outputs/studio/studio.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row

        def artifact(row: dict, key: str) -> None:
            registered = db.execute("SELECT * FROM artifacts WHERE id=?", (row["id"],)).fetchone()
            if registered is None or registered["production_id"] != prod or not registered["available"]:
                raise ValueError("Unavailable or cross-production artifact")
            registered = dict(registered)
            for field in ("rel_path", "sha256", "bytes"):
                if registered[field] != row[field]:
                    raise ValueError("Job and registered artifact disagree")
            paths[key], artifacts[key] = checked_path(registered), row

        artifact(result["render"]["master"], "v3_captioned")
        narration_id = result["render"]["children"]["narration"]["job_id"]
        job = db.execute("SELECT * FROM jobs WHERE id=?", (narration_id,)).fetchone()
        if not job or job["status"] != "succeeded" or job["production_id"] != prod:
            raise ValueError("Narration child is not completed")
        payload, child = json.loads(job["payload_json"]), json.loads(job["result_json"])
        if payload["run_id"] != RUN_ID:
            raise ValueError("Narration child lineage mismatch")
        for row in child["artifacts"]:
            key = {"narration.wav": "raw_wav", "manifest.json": "narration_manifest", "timings.json": "timings"}.get(row["name"])
            if key:
                artifact(row, key)
    manifest = json.loads(paths["narration_manifest"].read_text(encoding="utf-8"))
    if manifest["voice"] != "Microsoft Sayaka" or manifest["rate"] != 0:
        raise ValueError("Unexpected voice")
    if manifest["files"]["narration.wav"]["sha256"] != sha(paths["raw_wav"]):
        raise ValueError("Narration manifest mismatch")
    lineage = {"production_id": prod, "v3_run_id": RUN_ID, "narration_job_id": narration_id,
               "narration_owner_run_id": manifest["run_id"], "cache_hit": child["cache_hit"],
               "cache_source_attempt_id": child.get("cache_source_attempt_id"), "artifacts": artifacts}
    return lineage, paths, manifest


def dbfs(value: float) -> float:
    return round(20 * math.log10(max(float(value), 1e-12)), 5)


def rms(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(a * a))) if len(a) else 0.0


def estimate_lag(reference: np.ndarray, candidate: np.ndarray, rate: int = RATE) -> int:
    size = 1 << (len(reference) + len(candidate) - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(candidate, size) * np.conj(np.fft.rfft(reference, size)), size)
    limit = rate // 10
    lags = np.arange(-limit, limit + 1)
    lag = int(lags[np.argmax(corr[lags % size])])
    if abs(lag) == limit:
        raise ValueError("Alignment reaches 100ms search boundary")
    return lag


def align(a: np.ndarray, lag: int, frames: int = FRAMES) -> np.ndarray:
    out = np.zeros(frames)
    dst, src = max(0, -lag), max(0, lag)
    count = min(frames - dst, len(a) - src)
    if count > 0:
        out[dst:dst + count] = a[src:src + count]
    return out


def residual(reference: np.ndarray, candidate: np.ndarray, rate: int = RATE) -> tuple[dict, np.ndarray]:
    lag = estimate_lag(reference, candidate, rate)
    candidate = align(candidate, lag, len(reference))
    active = np.abs(reference) > 0.005
    gain = float(np.dot(reference[active], candidate[active]) / np.dot(reference[active], reference[active]))
    if not np.isfinite(gain) or gain <= 0:
        raise ValueError("No positive finite alignment gain")
    scaled = candidate / gain
    error = scaled - reference
    return {"lag_samples": lag, "lag_ms": lag * 1000 / rate, "least_squares_candidate_gain": gain,
            "gain_db": dbfs(gain), "active_error_snr_db": dbfs(rms(reference[active]) / max(rms(error[active]), 1e-12)),
            "active_residual_rms_dbfs": dbfs(rms(error[active])), "max_absolute_residual": float(np.max(np.abs(error))),
            "correlation": float(np.corrcoef(reference[active], scaled[active])[0, 1]),
            "interpretation": "Gain/delay-aligned signal error, not a perceptual score"}, scaled


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def diagnostics(a: np.ndarray, rate: int) -> dict:
    if not np.isfinite(a).all():
        raise ValueError("Non-finite PCM")
    flanks = int(rate * .02)
    gaps = []
    for start, end in runs(np.abs(a) < 1 / 65536):
        if .002 * rate <= end - start <= .025 * rate and start >= flanks and end + flanks < len(a):
            before, after = rms(a[start-flanks:start]), rms(a[end:end+flanks])
            if min(before, after) > .01:
                gaps.append({"start_ms": round(start * 1000 / rate, 3), "duration_ms": round((end-start) * 1000 / rate, 3)})
    delta = np.abs(np.diff(a))
    # High sample derivative also occurs in normal consonants; retain as a flag.
    steps = np.flatnonzero(delta > .5)
    block = max(1, rate // 1000)
    env = np.sqrt(np.mean(a[:len(a)//block*block].reshape(-1, block) ** 2, axis=1))
    freqs, power = signal.welch(env, fs=rate / block, nperseg=min(len(env), 2048))
    region = (freqs >= 5) & (freqs <= 80)
    peaks, _ = signal.find_peaks(power[region])
    indices = np.flatnonzero(region)[peaks]
    strongest = sorted(indices, key=lambda i: power[i], reverse=True)[:5]
    return {"sample_rate": rate, "sample_count": len(a), "duration_seconds": len(a)/rate,
            "sample_peak_dbfs": dbfs(np.max(np.abs(a))), "rms_dbfs": dbfs(rms(a)),
            "full_scale_samples": int(np.count_nonzero(np.abs(a) >= 32767/32768)),
            "max_adjacent_step": float(delta.max()), "adjacent_steps_over_0_5fs": len(steps),
            "step_times_ms_first20": (steps[:20]*1000/rate).tolist(),
            "possible_short_dropouts": gaps[:60], "possible_short_dropout_count": len(gaps),
            "dropout_definition": "2-25ms nearly exact zero, with both 20ms flanks RMS above -40dBFS; heuristic, consonants possible",
            "envelope_modulation_peaks_hz": [round(float(freqs[i]), 3) for i in strongest],
            "periodicity_warning": "Speech pitch, phonemes and syllables are naturally periodic. These peaks do not establish noise."}


class Runner:
    def __init__(self, output: Path):
        self.output = output
        self.runtime = ROOT / "outputs/studio/runtime/audio-diagnostics"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.logs = []
        self.ffmpeg = str(Path(shutil.which("ffmpeg") or "missing").resolve(strict=True))

    def run(self, args: list[str], timeout: int = 90) -> bytes:
        result = subprocess.run(args, cwd=self.runtime, capture_output=True, timeout=timeout)
        self.logs.append({"arguments": args, "cwd": str(self.runtime), "returncode": result.returncode,
                          "stdout_bytes": len(result.stdout), "stderr": result.stderr.decode("utf-8", "replace")[-6000:]})
        write_json(self.output / "commands.json", self.logs)
        if result.returncode:
            raise RuntimeError(self.logs[-1]["stderr"])
        return result.stdout

    def decode(self, path: Path, filters: str = "anull") -> np.ndarray:
        data = self.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                         "-i", str(path), "-map", "0:a:0", "-vn", "-af", f"aresample={RATE},aformat=channel_layouts=mono,{filters},apad,atrim=duration=21",
                         "-ar", str(RATE), "-ac", "1", "-f", "f32le", "pipe:1"])
        a = np.frombuffer(data, dtype="<f4").astype(np.float64)
        if len(a) != FRAMES or not np.isfinite(a).all():
            raise ValueError("Decoded audio length invalid")
        return a

    def loudness(self, path: Path) -> dict:
        self.run([self.ffmpeg, "-hide_banner", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(path),
                  "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        log = self.logs[-1]["stderr"]
        return {"integrated_lufs": float(re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", log)[-1]),
                "true_peak_dbfs": float(re.findall(r"Peak:\s+(-?\d+(?:\.\d+)?) dBFS", log)[-1])}


def wav(path: Path, a: np.ndarray) -> None:
    if not np.isfinite(a).all() or np.max(np.abs(a)) >= 1:
        raise ValueError("Clipping/non-finite listening WAV rejected")
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        handle.writeframes(np.rint(a * 32767).astype("<i2").tobytes())


def format_probes(output: Path, runner: Runner, first_segment: dict, raw: np.ndarray) -> dict:
    sys.path.insert(0, str(ROOT))
    from tools.studio.narration import _find_powershell
    host = _find_powershell()
    if host is None:
        raise ValueError("No installed SAPI host")
    original = ROOT / "tools/studio/sapi_synthesize.ps1"
    script = original.read_text(encoding="utf-8")
    old = "$synthesizer.SetOutputToWaveFile($outputPath)"
    if script.count(old) != 1:
        raise ValueError("SAPI script format contract changed")
    result = {"host": record(Path(host)), "original_script": record(original),
              "hypothesis": "Explicit output format might differ from default. No claim native rate is known; SupportedAudioFormats was empty.", "probes": {}}
    request = output / "same-phrase-request.json"
    write_json(request, {"voice": "Microsoft Sayaka", "rate": 0, "text": first_segment["text"]})
    for rate in (24000, 48000):
        probe_script = output / f"sapi-explicit-{rate}.ps1"
        replacement = f"$diagnosticFormat = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({rate}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)\n    $synthesizer.SetOutputToWaveFile($outputPath, $diagnosticFormat)"
        probe_script.write_text(script.replace(old, replacement), encoding="utf-8", newline="\n")
        target = output / f"same-phrase-{rate}.wav"
        runner.run([host, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe_script),
                    "-InputJsonPath", str(request), "-OutputWavPath", str(target)], timeout=60)
        with wave.open(str(target), "rb") as handle:
            actual_rate = handle.getframerate()
            if actual_rate != rate or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                raise ValueError("Explicit SAPI format not honored")
            native = np.frombuffer(handle.readframes(handle.getnframes()), "<i2").astype(float)/32768
        decoded = runner.decode(target)
        phrase = raw.copy()
        phrase[round(first_segment["end_ms"] * RATE/1000) + RATE//50:] = 0
        comparison, _ = residual(phrase, decoded)
        result["probes"][str(rate)] = {"wav": record(target), "script": record(probe_script),
            "native_pcm": diagnostics(native, rate), "default_vs_explicit": comparison}
    return result


def extend_existing(parent: Path) -> None:
    """One approved second EQ hypothesis and analysis of existing format probes.

    This path never invokes SAPI again and never rewrites the first manifest.
    """
    parent = parent.resolve(strict=True)
    if not parent.is_relative_to(BASE / "audio-diagnostics") or parent.is_symlink():
        raise ValueError("Only this production's diagnostic directory is accepted")
    previous = json.loads((parent / "manifest.json").read_text(encoding="utf-8"))
    if previous["status"] != "succeeded" or previous["lineage"]["v3_run_id"] != RUN_ID:
        raise ValueError("Completed v3 diagnostic manifest required")
    _, paths, voice = sources()
    for key, path in paths.items():
        if record(path) != previous["sources"][key]:
            raise ValueError("Original differs from the completed diagnostic")
    output = parent / "followup-lowcut120"
    output.mkdir(exist_ok=False)
    runner = Runner(output)
    manifest = {"schema_version": 1, "status": "running", "script": record(Path(__file__)),
                "parent_manifest": record(parent / "manifest.json"), "sources": previous["sources"],
                "synthesis_calls": 0, "network_used": False, "paid_api_calls": 0,
                "subjective_quality": "awaiting_human_listening", "replaces_originals": False}
    write_json(output / "manifest.json", manifest)
    try:
        raw = runner.decode(paths["raw_wav"])
        filters = "highpass=f=120:p=2,treble=g=-2:f=3500:t=q:w=0.7"
        processed = runner.decode(paths["raw_wav"], filters)
        lag = estimate_lag(raw, processed)
        processed = align(processed, lag)
        before = output / "D_lowcut120_treble_before_gain.wav"
        wav(before, processed * .5)
        before_measurement = runner.loudness(before)
        target = previous["common_target_lufs"]
        gain = target - before_measurement["integrated_lufs"]
        samples = processed * .5 * 10**(gain/20)
        target_wav = output / "D_lowcut120_treble_hypothesis_21s.wav"
        wav(target_wav, samples)
        measured = runner.loudness(target_wav)
        if abs(measured["integrated_lufs"] - target) > .25 or measured["true_peak_dbfs"] > -1.5:
            raise ValueError("D is not loudness/headroom matched")
        control_row = previous["listening_copies"]["A_raw_control"]["wav"]
        control = checked_path({"rel_path": control_row["path"], **control_row})
        a = runner.decode(control)
        end, gap = int(4.15 * RATE), RATE // 2
        parts = [a[:end].copy(), samples[:end].copy()]
        for part in parts:
            part[:480] *= np.linspace(0, 1, 480)
            part[-480:] *= np.linspace(1, 0, 480)
        comparison = output / "comparison_A_raw_D_gentle_EQ.wav"
        wav(comparison, np.concatenate([parts[0], np.zeros(gap), parts[1]]))
        manifest.update(common_target_lufs=target, D={"wav": record(target_wav), "filter": filters,
            "alignment_lag_samples": lag, "before_gain": record(before), "before_gain_measurements": before_measurement,
            "total_gain_db": gain+dbfs(.5), "measurements": measured,
            "interpretation": "A weak bandwidth/tone hypothesis only. Not an identified periodic-noise repair."},
            comparison={"wav": record(comparison), "A_interval_seconds": [0, 4.15], "D_interval_seconds": [4.65, 8.8]})
        # Resolve the two completed one-phrase probes; no additional synthesis.
        probe_arrays = {}
        phrase_end = math.ceil(voice["segments"][0]["end_ms"] * RATE/1000) + RATE//50
        reference = raw.copy()
        reference[phrase_end:] = 0
        comparisons = {}
        for rate, probe in previous.get("format_probes", {}).get("probes", {}).items():
            row = probe["wav"]
            path = checked_path({"rel_path": row["path"], **row})
            probe_arrays[rate] = runner.decode(path)
        if {"24000", "48000"} <= probe_arrays.keys():
            comparisons["explicit_24k_vs_48k"], _ = residual(probe_arrays["24000"], probe_arrays["48000"])
            # 300ms blocks expose whether a single global delay is insufficient.
            local = []
            for start in range(int(.2*RATE), int(3.7*RATE), int(.25*RATE)):
                end_sample = start + int(.3*RATE)
                ref = reference[start:end_sample]
                if rms(ref) < .01:
                    continue
                comp = probe_arrays["48000"][start:end_sample]
                block_lag = estimate_lag(ref, comp)
                local.append({"start_ms": round(start*1000/RATE), "lag_samples": block_lag})
            comparisons["default_vs_48k_local_block_lags"] = local
            comparisons["interpretation"] = "Rate variants can include resampling/time-grid differences. Waveform disagreement is not proof of audible improvement; no repeated trial or product change."
        manifest["existing_format_probe_analysis"] = comparisons
        for key, path in paths.items():
            if record(path) != previous["sources"][key]:
                raise ValueError("Original changed")
        manifest.update(status="succeeded", originals_unchanged=True)
        write_json(output / "manifest.json", manifest)
        print(json.dumps({"output": str(output), "D": record(target_wav), "measurements": measured,
                          "format_analysis": comparisons}, ensure_ascii=False), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        write_json(output / "manifest.json", manifest)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-formats", action="store_true", help="Synthesize only the first phrase at explicit 24k and 48k, same Sayaka voice")
    parser.add_argument("--extend-existing", type=Path, help="Add the approved second gentle EQ and analyze existing format probes; no synthesis")
    args = parser.parse_args()
    if args.extend_existing:
        if args.probe_formats:
            parser.error("--extend-existing does not permit new synthesis")
        extend_existing(args.extend_existing)
        return
    lineage, paths, voice = sources()
    output = BASE / "audio-diagnostics" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    runner = Runner(output)
    manifest = {"schema_version": 1, "status": "running", "policy": "sayaka-audio-investigation-v1", "script": record(Path(__file__)),
                "source_result": record(RESULT), "lineage": lineage, "sources": {k: record(v) for k, v in paths.items()},
                "network_used": False, "paid_api_calls": 0, "studio_jobs_created": 0,
                "synthesis_calls": 0, "subjective_quality": "awaiting_human_listening", "replaces_originals": False,
                "interpretation_limits": ["Metrics are not listening acceptance.", "Periodic pitch/syllable energy is not proof of a noise source.",
                                          "Gain and global delay matching do not repair speech timing or prove a codec caused audible noise."]}
    write_json(output / "manifest.json", manifest)
    try:
        with wave.open(str(paths["raw_wav"]), "rb") as handle:
            native_rate = handle.getframerate()
            native = np.frombuffer(handle.readframes(handle.getnframes()), "<i2").astype(float)/32768
        raw, aac = runner.decode(paths["raw_wav"]), runner.decode(paths["v3_captioned"])
        comparison, aligned_aac = residual(raw, aac)
        manifest["diagnostics"] = {"original_pcm": diagnostics(native, native_rate), "decoded_aac_pcm": diagnostics(aac, RATE),
                                   "raw_vs_aac": comparison, "ffmpeg": runner.run([runner.ffmpeg, "-version"]).decode().splitlines()[0]}
        print(json.dumps({"preliminary": manifest["diagnostics"]}, ensure_ascii=False), flush=True)
        # One conservative hypothesis only. No spectral subtraction or pitch-notch.
        mild = runner.decode(paths["raw_wav"], "highpass=f=80:p=2")
        mild_lag = estimate_lag(raw, mild)
        arrays = {"A_raw_control": raw, "B_aac_control": aligned_aac, "C_lowcut80_hypothesis": align(mild, mild_lag)}
        details = {}
        for name, samples in arrays.items():
            before = output / f"{name}_before_gain.wav"
            # This measurement copy reserves fixed 6dB headroom; undone in gain accounting.
            wav(before, samples * .5)
            measured = runner.loudness(before)
            details[name] = {"before_gain": record(before), "before_gain_measurements": measured}
        target_lufs = min(-20.0, *(r["before_gain_measurements"]["integrated_lufs"] - 2 - r["before_gain_measurements"]["true_peak_dbfs"] for r in details.values()))
        for name, samples in arrays.items():
            gain_db = target_lufs - details[name]["before_gain_measurements"]["integrated_lufs"]
            arrays[name] = samples * .5 * 10**(gain_db/20)
            target = output / f"{name}_21s.wav"
            wav(target, arrays[name])
            measurement = runner.loudness(target)
            if abs(measurement["integrated_lufs"]-target_lufs) > .25 or measurement["true_peak_dbfs"] > -1.5:
                raise ValueError("Matched loudness/headroom check failed")
            details[name].update(wav=record(target), measurements=measurement, total_gain_db=gain_db+dbfs(.5))
        excerpt_end = int(4.15*RATE)
        pieces, sections, cursor = [], [], 0
        for name, samples in arrays.items():
            excerpt = samples[:excerpt_end].copy()
            excerpt[:480] *= np.linspace(0, 1, 480)
            excerpt[-480:] *= np.linspace(1, 0, 480)
            sections.append({"name": name, "start_seconds": cursor/RATE, "end_seconds": (cursor+len(excerpt))/RATE})
            pieces.extend([excerpt, np.zeros(RATE//2)])
            cursor += len(excerpt)+RATE//2
        combined = output / "comparison_A_raw_B_AAC_C_lowcut.wav"
        wav(combined, np.concatenate(pieces[:-1]))
        manifest.update(common_target_lufs=target_lufs, listening_copies=details,
                        comparison={"wav": record(combined), "sections": sections, "source_excerpt_seconds": [0, 4.15]},
                        candidate_policy={"A": "Original PCM resample + fixed gain only", "B": "Existing AAC decoded, delay/gain aligned (codec control, not enhancement)",
                                          "C": "80Hz two-pole highpass only; low-frequency plosive/rumble hypothesis, not a proven denoise fix", "C_alignment_lag_samples": mild_lag})
        if args.probe_formats:
            manifest["format_probes"] = format_probes(output, runner, voice["segments"][0], raw)
            manifest["synthesis_calls"] = 2
        for key, path in paths.items():
            if record(path) != manifest["sources"][key]:
                raise ValueError("An original changed during diagnostics")
        manifest.update(status="succeeded", originals_unchanged=True)
        write_json(output / "manifest.json", manifest)
        print(json.dumps({"output": str(output), "comparison": str(combined), "target_lufs": target_lufs}, ensure_ascii=False), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        write_json(output / "manifest.json", manifest)
        raise


if __name__ == "__main__":
    main()
