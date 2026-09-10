"""Pair matched listening WAVs with the verified overview-first v4 video.

Experimental review copies only: no Studio Job, default voice change, paid call,
or original overwrite. Audio is encoded from PCM once for both variants.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import wave
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/studio/verification/claude-desktop-real-20260906"
RESULT = BASE / "renders/29F7B09A4D60A0DE6746C95684C0C6DE5D6BD4787F2288B680B36BB361C5D119/result.json"
EXPECTED_RUN = "run_d9058b3baf6f4b12991ab1e1cd32c5a9"
RUNTIME = ROOT / "outputs/studio/runtime/claude-window-capture"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def record(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": digest(path)}


def regular(path: Path) -> Path:
    lexical = path if path.is_absolute() else ROOT / path
    resolved = lexical.resolve(strict=True)
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise ValueError("Expected regular file inside this workspace")
    for parent in (lexical, *lexical.parents):
        if parent == ROOT.parent:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("Linked input rejected")
    return resolved


def checked(row: dict) -> Path:
    path = regular(Path(row.get("rel_path", row.get("path", ""))))
    if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
        raise ValueError("Input no longer matches its recorded bytes/hash")
    return path


def run(args: list[str]) -> bytes:
    process = subprocess.run(args, cwd=RUNTIME, capture_output=True, timeout=120)
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", "replace")[-3000:])
    return process.stdout


def video_payload(path: Path) -> str:
    return run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
                "-map", "0:v:0", "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-"]).decode().strip()


def validate_pcm(path: Path) -> None:
    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate(), handle.getnframes(),
                handle.getcomptype()) != (1, 2, 48000, 21 * 48000, "NONE"):
            raise ValueError("Listening copy must be 21s/48kHz/mono/PCM16")


def loudness(path: Path) -> dict:
    measured = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn",
                               "-af", "ebur128=peak=true", "-f", "null", "-"],
                              cwd=RUNTIME, capture_output=True, timeout=120)
    if measured.returncode:
        raise RuntimeError("Encoded audio measurement failed")
    log = measured.stderr.decode("utf-8", "replace")
    levels = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", log)
    peaks = re.findall(r"Peak:\s+(-?\d+(?:\.\d+)?) dBFS", log)
    if not levels or not peaks:
        raise ValueError("Encoded audio has no finite loudness/peak result")
    return {"integrated_lufs": float(levels[-1]), "true_peak_dbfs": float(peaks[-1])}


def save(path: Path, data: dict) -> None:
    # New review directory only. Failed attempts retain their manifest.
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,80}", args.candidate) or args.candidate == "A_raw_control":
        raise ValueError("Choose a distinct measured candidate")
    report_path = regular(args.diagnostics)
    audio = json.loads(report_path.read_text(encoding="utf-8"))
    result = json.loads(regular(RESULT).read_text(encoding="utf-8"))
    if (result["render"]["run_id"] != EXPECTED_RUN or result["render"]["status"] != "succeeded"
            or result["render"]["technical_verdict"] != "pass" or audio["status"] != "succeeded"):
        raise ValueError("Inputs are not the completed audited revision")
    parent_report = None
    if "parent_manifest" in audio:
        parent_report = checked(audio["parent_manifest"])
        parent_audio = json.loads(parent_report.read_text(encoding="utf-8"))
        if (parent_audio["status"] != "succeeded" or args.candidate != "D_lowcut120_treble_hypothesis"
                or audio["sources"] != parent_audio["sources"]):
            raise ValueError("Follow-up audio must retain the same verified sources")
        listening = {"A_raw_control": parent_audio["listening_copies"]["A_raw_control"],
                     args.candidate: audio["D"]}
    else:
        listening = audio["listening_copies"]
    video = checked(result["render"]["master"])
    paths = {name: checked(listening[name]["wav"])
             for name in ("A_raw_control", args.candidate)}
    measurements = [listening[name]["measurements"] for name in paths]
    if (max(item["integrated_lufs"] for item in measurements)
            - min(item["integrated_lufs"] for item in measurements) > 0.2
            or any(item["true_peak_dbfs"] > -1.8 for item in measurements)):
        raise ValueError("Listening WAVs must have matched loudness and safe headroom")
    for path in paths.values():
        validate_pcm(path)
    source_payload = video_payload(video)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    output = BASE / "audio-video-review" / stamp
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "policy": "matched-sayaka-v4-review-v1", "status": "running",
                "video": record(video), "source_result": record(RESULT), "script": record(Path(__file__)),
                "audio_report": record(report_path), "audio_inputs": {k: record(v) for k, v in paths.items()},
                "parent_audio_report": record(parent_report) if parent_report else None,
                "audio_measurements": dict(zip(paths, measurements)), "video_payload_sha256": source_payload,
                "audio_encoding": {"codec": "aac", "bitrate": "256k", "sample_rate": 48000, "channels": 1,
                                   "source": "matched PCM once; no additional filtering/normalization"},
                "outputs": {}, "paid_api_calls": 0, "new_synthesis": False, "studio_jobs_created": 0,
                "public_quality_verified": False, "originals_unchanged": None}
    save(output / "manifest.json", manifest)
    try:
        for name, pcm in paths.items():
            destination = output / f"{name}.mp4"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(video),
                 "-i", str(pcm), "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "-1",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "1",
                 "-t", "21", "-movflags", "+faststart", str(destination)])
            probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(destination)]))
            streams = probe["streams"]
            vs = [item for item in streams if item["codec_type"] == "video"]
            aus = [item for item in streams if item["codec_type"] == "audio"]
            if (len(vs) != 1 or len(aus) != 1 or vs[0]["width"] != 1080 or vs[0]["height"] != 1920
                    or vs[0]["r_frame_rate"] != "24/1" or int(vs[0]["nb_frames"]) != 504
                    or aus[0]["sample_rate"] != "48000" or aus[0]["channels"] != 1
                    or abs(float(probe["format"]["duration"]) - 21) > 0.001
                    or video_payload(destination) != source_payload):
                raise ValueError("Review movie timing or video identity mismatch")
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-nostdin", "-i", str(destination),
                 "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
            encoded_measurements = loudness(destination)
            if (abs(encoded_measurements["integrated_lufs"] - manifest["audio_measurements"][name]["integrated_lufs"]) > 0.2
                    or encoded_measurements["true_peak_dbfs"] > -1.5):
                raise ValueError("Encoding changed loudness or consumed safe headroom")
            manifest["outputs"][name] = {**record(destination), "full_decode_verified": True,
                                         "video_payload_unchanged": True, "measurements": encoded_measurements}
            save(output / f"{name}.ffprobe.json", probe)
        if (digest(video) != manifest["video"]["sha256"] or digest(report_path) != manifest["audio_report"]["sha256"]
                or (parent_report is not None and digest(parent_report) != manifest["parent_audio_report"]["sha256"])
                or any(digest(path) != manifest["audio_inputs"][name]["sha256"] for name, path in paths.items())):
            raise ValueError("Inputs changed during assembly")
        manifest.update(status="succeeded", originals_unchanged=True)
    except Exception:
        manifest["status"] = "failed"
        raise
    finally:
        save(output / "manifest.json", manifest)
    print(json.dumps({"manifest": str(output / "manifest.json"), "outputs": manifest["outputs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
