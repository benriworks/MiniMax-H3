"""Static, source-bound spectral investigation. No denoise or new synthesis.

NumPy/SciPy supply the measurements; Pillow draws fixed-axis scientific figures.
An energy band is not an isolated noise source. Inserted pauses are excluded
from speech PSD and are not used as evidence of a clean synthesis noise floor.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import wave

import numpy as np
from scipy import signal
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/studio/verification/claude-desktop-real-20260906"
PARENT = BASE / "audio-diagnostics/20260906T021544623145Z/manifest.json"
FOLLOWUP = PARENT.parent / "followup-lowcut120/manifest.json"
RATE = 48000
BLUE, ORANGE = "#1263a5", "#d35e16"
FONT = "C:/Windows/Fonts/YuGothM.ttc"


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def record(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}


def checked(row: dict) -> Path:
    path = ROOT / row["path"]
    resolved = path.resolve(strict=True)
    if (not resolved.is_relative_to(ROOT) or not resolved.is_file()
            or any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                   for p in (path, *path.parents) if p != ROOT.parent)
            or resolved.stat().st_size != row["bytes"] or sha(resolved) != row["sha256"]):
        raise ValueError("Source does not match a regular recorded workspace artifact")
    return resolved


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("Expected mono PCM16")
        return np.frombuffer(handle.readframes(handle.getnframes()), "<i2").astype(float) / 32768, handle.getframerate()


def mean_speech_psd(samples: np.ndarray, rate: int, intervals: list[tuple[float, float]], nperseg: int = 8192):
    """Average unjoined utterance PSDs; no gap-splice FFT or inserted silence."""
    if not intervals or any(not 0 <= start < end <= len(samples) / rate for start, end in intervals):
        raise ValueError("Expected bounded nonempty utterance intervals")
    spectra, weights = [], []
    for start, end in intervals:
        clip = samples[round(start * rate):round(end * rate)]
        if len(clip) < nperseg:
            raise ValueError("Utterance too short for the specified resolution")
        frequencies, power = signal.welch(clip, rate, window="hann", nperseg=nperseg,
                                          noverlap=nperseg // 2, detrend=False, scaling="density")
        spectra.append(power)
        weights.append(len(clip))
    return frequencies, np.average(np.array(spectra), axis=0, weights=weights), spectra


def band_energy(frequencies, power, low: float, high: float) -> float:
    mask = (frequencies >= low) & (frequencies < high)
    return float(power[mask].sum() * (frequencies[1] - frequencies[0]))


def db(values):
    return 10 * np.log10(np.maximum(values, 1e-18))


def line_prominence(frequencies, power, center: float) -> float:
    near = power[np.abs(frequencies - center) <= 4]
    neighbors = power[(np.abs(frequencies - center) >= 8) & (np.abs(frequencies - center) <= 20)]
    return float(10 * np.log10(max(float(np.max(near)), 1e-18) / max(float(np.median(neighbors)), 1e-18)))


def quiet_summary(samples, rate, intervals):
    """Report within-utterance quiet windows, not a measured recording noise floor."""
    width = round(.02 * rate)
    values = []
    for start, end in intervals:
        clip = samples[round(start * rate):round(end * rate)]
        for position in range(0, len(clip) - width + 1, width):
            block = clip[position:position + width]
            rms = float(np.sqrt(np.mean(block * block)))
            if rms < 10 ** (-55 / 20):
                values.append(rms)
    nonzero = [value for value in values if value > 0]
    return {"duration_ms": 20, "threshold_dbfs": -55, "count": len(values),
            "exact_zero_count": len(values) - len(nonzero),
            "nonzero_rms_dbfs_min_median_max": (20 * np.log10([min(nonzero), np.median(nonzero), max(nonzero)])).tolist() if nonzero else None,
            "note": "Within-utterance digital silence/near-zero; not a microphone room-noise sample or clean reference"}


class Figure:
    def __init__(self, size, title, subtitle):
        self.image = Image.new("RGB", size, "white")
        self.draw = ImageDraw.Draw(self.image)
        self.text((32, 18), title, 31)
        self.text((32, 64), subtitle, 21, "#52606d")

    def text(self, xy, text, size=22, fill="#182936", anchor=None):
        self.draw.text(xy, text, font=ImageFont.truetype(FONT, size), fill=fill, anchor=anchor)

    def axes(self, box, xticks, yticks, xdomain, ydomain, xlabel, ylabel, logx=False):
        l, t, r, b = box
        self.draw.rectangle(box, outline="#546575", width=1)
        def xmap(v):
            a, z = xdomain
            if logx:
                return l + (np.log10(v) - np.log10(a)) / (np.log10(z) - np.log10(a)) * (r - l)
            return l + (v - a) / (z - a) * (r - l)
        def ymap(v):
            return b - (v - ydomain[0]) / (ydomain[1] - ydomain[0]) * (b - t)
        for value, label in xticks:
            x = xmap(value)
            self.draw.line((x, t, x, b), fill="#d9e0e6", width=1)
            self.text((x, b + 8), label, 19, anchor="mt")
        for value, label in yticks:
            y = ymap(value)
            self.draw.line((l, y, r, y), fill="#d9e0e6", width=1)
            self.text((l - 13, y), label, 19, anchor="rm")
        self.text(((l + r) / 2, b + 40), xlabel, 21, anchor="mt")
        self.text((l, t - 31), ylabel, 21)
        return xmap, ymap

    def lines(self, box, data, xdomain, ydomain, maps):
        xmap, ymap = maps
        layer = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), "white")
        # Keep the previously drawn grid by taking the existing plot interior.
        layer.paste(self.image.crop(box))
        draw = ImageDraw.Draw(layer)
        for xs, ys, color in data:
            mask = (xs >= xdomain[0]) & (xs <= xdomain[1])
            points = [(xmap(float(x)) - box[0], ymap(float(y)) - box[1])
                      for x, y in zip(xs[mask], ys[mask])]
            draw.line(points, fill=color, width=3)
        self.image.paste(layer, box[:2])


def heatmap(values):
    # Fixed perceptually ordered palette shared by raw and processed panels.
    anchors = np.array([[4, 4, 20], [55, 15, 99], [124, 32, 104], [187, 55, 84], [239, 111, 39], [249, 193, 62], [252, 255, 164]])
    scaled = np.clip((values + 110) / 85, 0, 1)
    channels = [np.interp(scaled, np.linspace(0, 1, len(anchors)), anchors[:, c]) for c in range(3)]
    return np.stack(channels, axis=-1).astype("uint8")


def main():
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    followup = json.loads(FOLLOWUP.read_text(encoding="utf-8"))
    if checked(followup["parent_manifest"]) != PARENT:
        raise ValueError("Parent diagnostic lineage changed")
    rows = {"original_native": parent["sources"]["raw_wav"],
            "A": parent["listening_copies"]["A_raw_control"]["wav"], "D": followup["D"]["wav"]}
    paths = {name: checked(row) for name, row in rows.items()}
    native, native_rate = load_wav(paths["original_native"])
    a, arate = load_wav(paths["A"])
    d, drate = load_wav(paths["D"])
    if arate != RATE or drate != RATE or len(a) != RATE * 21 or a.shape != d.shape:
        raise ValueError("Scheduled comparison PCM contract mismatch")
    timings = json.loads(checked(parent["sources"]["timings"]).read_text(encoding="utf-8"))
    # The original manifest gives exact start/end milliseconds for each utterance.
    voice = json.loads(checked(parent["sources"]["narration_manifest"]).read_text(encoding="utf-8"))
    intervals = [(segment["start_ms"] / 1000, segment["end_ms"] / 1000) for segment in voice["segments"]]
    output = BASE / "spectrum-review" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    nf, npower, per_utterance = mean_speech_psd(native, native_rate, intervals)
    f, apower, _ = mean_speech_psd(a, RATE, intervals)
    _, dpower, _ = mean_speech_psd(d, RATE, intervals)
    bands = [(20, 80), (80, 150), (150, 1000), (1000, 4000), (4000, 8000), (8000, native_rate / 2)]
    total = band_energy(nf, npower, 20, native_rate / 2)
    band_rows = [{"low_hz": lo, "high_hz": hi, "original_energy_percent": 100 * band_energy(nf, npower, lo, hi) / total,
                  "D_minus_A_db": float(10 * np.log10(max(band_energy(f, dpower, lo, hi), 1e-18) /
                                                        max(band_energy(f, apower, lo, hi), 1e-18)))} for lo, hi in bands]
    report = {"schema_version": 1, "status": "succeeded", "sources": {k: record(v) for k, v in paths.items()},
              "parent_manifest": record(PARENT), "followup_manifest": record(FOLLOWUP), "script": record(Path(__file__)),
              "speech_intervals_seconds": intervals, "psd": {"method": "Hann Welch per utterance, duration-weighted power average; no concatenation",
              "nperseg": 8192, "native_resolution_hz": native_rate / 8192, "comparison_resolution_hz": RATE / 8192},
              "bands": band_rows, "line_prominence_db_by_utterance": {
                  str(center): [line_prominence(nf, p, center) for p in per_utterance] for center in (50, 60)},
              "phrase_internal_quiet_windows": quiet_summary(native, native_rate, intervals),
              "original_AAC_comparison": parent["diagnostics"]["raw_vs_aac"],
              "limitations": ["Power contains both wanted speech and any artifacts; no clean reference",
                  "Harmonics and syllable periodicity do not establish a noise source",
                  "No general noise-free claim from digital silence or a spectrogram"],
              "paid_api_calls": 0, "new_synthesis": False, "new_filtering": False, "originals_unchanged": True}

    figure = Figure((1520, 1320), "Sayaka：原音と調整版の周波数比較", "同じ音量で比較 ／ 明るい色＝その周波数成分が強い ／ 冒頭の同じ発話")
    for top, values, label in ((155, a, "A 原音"), (560, d, "D 調整版：120Hz低域カット＋高域を軽く低減")):
        box = (108, top, 1420, top + 265)
        sf, st, power = signal.spectrogram(values[:round(4.15 * RATE)], RATE, window="hann", nperseg=2048,
                                          noverlap=1808, detrend=False, scaling="density", mode="psd")
        mask = sf <= 8000
        raster = Image.fromarray(heatmap(db(power[mask]))[::-1]).resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.NEAREST)
        figure.image.paste(raster, box[:2])
        figure.text((108, top - 58), label, 24)
        # Only ticks and frame over the raster; no opaque grid lines obscure data.
        figure.draw.rectangle(box, outline="#546575", width=1)
        for tick in (0, 1, 2, 3, 4):
            x = box[0] + (tick - st[0]) / (st[-1] - st[0]) * (box[2] - box[0])
            if box[0] <= x <= box[2]:
                figure.text((x, box[3] + 10), str(tick), 20, anchor="mt")
        for khz in (0, 2, 4, 6, 8):
            figure.text((92, box[3] - khz / 8 * (box[3] - box[1])), str(khz), 20, anchor="rm")
        figure.text((20, top + 102), "kHz", 20)
        figure.text((764, box[3] + 41), "時間（秒）", 21, anchor="mt")
    color_box = (1180, 92, 1400, 108)
    legend = Image.fromarray(heatmap(np.linspace(-110, -25, 220)[None, :])).resize((220, 16))
    figure.image.paste(legend, color_box[:2])
    figure.text((1170, 94), "−110", 17, anchor="rm")
    figure.text((1410, 94), "−25", 17)
    figure.text((1150, 115), "dBFS/Hz（共通尺度）", 17)
    box = (108, 970, 1420, 1210)
    maps = figure.axes(box, [(v, str(v)) for v in (30, 60, 120, 300, 1000, 4000, 10000)],
                       [(v, str(v)) for v in (-110, -90, -70, -50, -30)], (20, 11000), (-115, -25),
                       "周波数 Hz（対数軸）", "3発話の平均PSD（dBFS/Hz）", logx=True)
    figure.lines(box, [(f, db(apower), BLUE), (f, db(dpower), ORANGE)], (20, 11000), (-115, -25), maps)
    figure.text((1070, 913), "━ A 原音", 21, BLUE)
    figure.text((1240, 913), "━ D 調整", 21, ORANGE)
    figure.text((32, 1290), "帯域の強さは『声＋異音』の合計です。色やピークだけでノイズ成分とは断定できません。", 19)
    figure.image.save(output / "spectrum-overview.png")

    detail = Figure((1520, 1040), "低域の細線と声の周期性", "50/60Hz付近と短い発話を個別確認 ／ 区間間に挿入した無音は解析対象外")
    box = (112, 170, 1420, 455)
    maps = detail.axes(box, [(v, str(v)) for v in (20, 60, 120, 200, 300, 400, 500)],
                       [(v, str(v)) for v in (-110, -90, -70, -50, -30)], (20, 500), (-115, -25),
                       "周波数 Hz", "原音の発話別PSD（dBFS/Hz）")
    detail.lines(box, [(nf, db(p), color) for p, color in zip(per_utterance, (BLUE, ORANGE, "#278459"))],
                 (20, 500), (-115, -25), maps)
    detail.text((785, 120), "━ 第1発話", 21, BLUE)
    detail.text((1010, 120), "━ 第2発話", 21, ORANGE)
    detail.text((1235, 120), "━ 第3発話", 21, "#278459")
    box = (112, 650, 1420, 935)
    clip = a[:round(intervals[0][1] * RATE)]
    width, hop = 480, 192
    windows = np.lib.stride_tricks.sliding_window_view(clip, width)[::hop]
    envelope = np.sqrt(np.mean(windows * windows, axis=1))
    env_rate = RATE / hop
    ef, ep = signal.periodogram(envelope, env_rate, window="hann", detrend="linear", scaling="density")
    edb = db(ep / max(np.max(ep[(ef >= 1) & (ef <= 40)]), 1e-18))
    maps = detail.axes(box, [(v, str(v)) for v in (1, 5, 10, 15, 20, 30, 40)],
                       [(v, str(v)) for v in (-40, -30, -20, -10, 0)], (1, 40), (-45, 3),
                       "音量の変動周期 Hz（声の高さではありません）", "第1発話のRMS包絡スペクトル（最大値＝0dB）")
    detail.lines(box, [(ef, edb, BLUE)], (1, 40), (-45, 3), maps)
    detail.text((32, 1005), "数Hz〜十数Hzの変動は音節にも生じます。この山だけで『プププ』の原因とは特定できません。", 19)
    detail.image.save(output / "lowband-and-modulation.png")
    peaks, _ = signal.find_peaks(ep)
    peaks = [i for i in peaks if 1 <= ef[i] <= 40]
    report["envelope_modulation_peaks_hz"] = [float(ef[i]) for i in sorted(peaks, key=lambda i: ep[i], reverse=True)[:5]]
    report["spectrogram"] = {"window": "Hann", "nperseg": 2048, "hop_samples": 240,
                              "color_dbfs_per_hz": [-110, -25], "frequency_range_hz": [0, 8000], "excerpt_seconds": [0, 4.15]}
    report["figures"] = [record(output / name) for name in ("spectrum-overview.png", "lowband-and-modulation.png")]
    for name, path in paths.items():
        if record(path) != report["sources"][name]:
            raise ValueError("Original changed during analysis")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    np.savetxt(output / "mean-spectrum.csv", np.column_stack((f, apower, dpower, db(apower), db(dpower))), delimiter=",",
               header="frequency_hz,A_psd,D_psd,A_dbfs_per_hz,D_dbfs_per_hz", comments="")
    print(json.dumps({"output": str(output), "bands": band_rows, "hum": report["line_prominence_db_by_utterance"],
                      "quiet_windows": report["phrase_internal_quiet_windows"], "envelope_peaks": report["envelope_modulation_peaks_hz"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
