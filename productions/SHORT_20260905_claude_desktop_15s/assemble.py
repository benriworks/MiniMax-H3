"""Assemble the Claude Code desktop introduction with measured local narration.

This is production-specific orchestration, not Quick Create. Existing workers
render, assemble and QC actual media. Studio receives real imports and an
explicit custom event, never a fabricated ordinary pipeline Run or Job.
The hero image was generated separately using the built-in imagegen tool:
network/cost assertions here apply only to this local assembly operation.
"""

from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import quote_from_bytes
from uuid import NAMESPACE_URL, uuid5
import wave

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from tools.studio.assembly import assemble_local_video, assembly_cache_key, resolve_tool_identity
from tools.studio.instance_lock import WorkspaceInstanceLock
from tools.studio.narration import generate_local_narration
from tools.studio.qc import generate_local_qc, qc_cache_key
from tools.studio.remotion_timeline import generate_remotion_timeline, resolve_remotion_tool_identity
from tools.studio.remotion_timeline_execution import compile_remotion_timeline, remotion_timeline_cache_key
from tools.studio.security import canonical_json, stable_id
from tools.studio.service import StudioService

PRODUCTION_NAME = "SHORT_20260905_claude_desktop_15s"
DEFAULT_PRODUCTION_ID = "production_" + uuid5(NAMESPACE_URL, f"MiniMaxH3/{PRODUCTION_NAME}").hex
DEFAULT_OUTPUT = WORKSPACE / "outputs" / "productions" / PRODUCTION_NAME
SEGMENTS = ["Claude Codeは、", "アプリでも使える。", "フォルダを選んで、", "やりたいことを入力。", "変更を見て、確認。", "まずは小さな修正から。"]
DEFAULT_STARTS = [450, 1590, 5450, 6690, 10250, 12320]
VOICE = "Microsoft Haruka Desktop"
POLICY = "claude-desktop-short-scheduled-local-workers-v1"
TRIM_POLICY = {"implementation": "production-sapi-trailing-quiet-v1", "window_ms": 10,
               "threshold_dbfs": -45, "retained_tail_ms": 120, "minimum_quiet_ms": 250,
               "leading_audio": "unchanged", "speech_detection": "RMS heuristic, not word alignment"}
LOCAL_EXECUTION = {"scope": "This local narration/render/assembly/QC/import operation only",
                   "network_used": False, "billable": False,
                   "excludes": "Prior built-in imagegen hero generation and source asset preparation"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def in_workspace(path: Path, *, must_exist: bool = True) -> Path:
    lexical = path if path.is_absolute() else WORKSPACE / path
    relative = lexical.absolute().relative_to(WORKSPACE)
    cursor = WORKSPACE
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("Symlinked production paths are not supported")
    resolved = lexical.resolve(strict=must_exist)
    resolved.relative_to(WORKSPACE)
    return resolved


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def file_record(path: Path, *, name: str | None = None) -> dict:
    checked = in_workspace(path)
    return {"path": checked.relative_to(WORKSPACE).as_posix(), "name": name or checked.name,
            "bytes": checked.stat().st_size, "sha256": digest_file(checked)}


def named(result: dict, name: str) -> dict:
    matches = [artifact for artifact in result["artifacts"] if artifact["name"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"Missing unique worker output: {name}")
    return matches[0]


def narration_payload(rate: int) -> dict:
    return {"segments": [{"text": text} for text in SEGMENTS], "voice": VOICE, "rate": rate,
            "pronunciations": [{"source": "Claude Code", "target": "クロードコード"}]}


def encode_wav(frames: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return output.getvalue()


def trim_trailing_quiet(frames: bytes, sample_rate: int) -> tuple[bytes, dict]:
    """Remove only a measured long quiet tail; preserve onset and 120ms release."""
    if not frames or len(frames) % 2 or sample_rate <= 0:
        raise ValueError("Expected nonempty PCM16 mono audio")
    samples = array("h", frames)
    if sys.byteorder != "little":
        samples.byteswap()
    block = max(1, round(sample_rate * TRIM_POLICY["window_ms"] / 1000))
    threshold_squared = (32768 * 10 ** (TRIM_POLICY["threshold_dbfs"] / 20)) ** 2
    active = []
    for start in range(0, len(samples), block):
        chunk = samples[start:start + block]
        if sum(value * value for value in chunk) / len(chunk) > threshold_squared:
            active.append(start)
    if not active:
        raise ValueError("No speech-level samples found; refusing to trim a silent segment")
    onset_frame = active[0]
    speech_end_frame = min(len(samples), active[-1] + block)
    quiet_frames = len(samples) - speech_end_frame
    retained = (sample_rate * TRIM_POLICY["retained_tail_ms"] + 999) // 1000
    trim_allowed = quiet_frames * 1000 >= TRIM_POLICY["minimum_quiet_ms"] * sample_rate
    output_frames = min(len(samples), speech_end_frame + retained) if trim_allowed else len(samples)
    result = frames[:output_frames * 2]
    discarded = samples[output_frames:]
    discarded_peak = max((abs(value) for value in discarded), default=0)
    # The heuristic must not remove audible samples. Keep the full raw release
    # if the proposed discarded tail has any sample above -55dBFS.
    if discarded_peak > 32768 * 10 ** (-55 / 20):
        raise ValueError("Proposed quiet-tail trim includes non-negligible samples; refusing to cut speech")
    report = {"raw_frames": len(samples), "trimmed_frames": output_frames,
              "raw_duration_ms": round(len(samples) * 1000 / sample_rate, 3),
              "trimmed_duration_ms": round(output_frames * 1000 / sample_rate, 3),
              "detected_onset_ms": round(onset_frame * 1000 / sample_rate, 3),
              "detected_speech_end_ms": round(speech_end_frame * 1000 / sample_rate, 3),
              "raw_quiet_tail_ms": round(quiet_frames * 1000 / sample_rate, 3),
              "removed_frames": len(samples) - output_frames,
              "discarded_peak_pcm16": discarded_peak,
              "discarded_samples_below_dbfs": -55,
              "original_onset_and_retained_pcm_unchanged": result == frames[:output_frames * 2],
              "retained_after_detected_speech_ms": round((output_frames - speech_end_frame) * 1000 / sample_rate, 3),
              "raw_pcm_sha256": hashlib.sha256(frames).hexdigest().upper(),
              "trimmed_pcm_sha256": hashlib.sha256(result).hexdigest().upper()}
    return result, report


def prepare_voice(production_id: str, rate: int, output_root: Path) -> tuple[dict, object]:
    """Keep authentic raw SAPI and measured preprocessing as durable provenance."""
    raw = generate_local_narration(WORKSPACE, production_id=production_id,
        run_id=f"claude_desktop_voice_probe_20260905_r{rate}", payload=narration_payload(rate))
    raw_wav = in_workspace(WORKSPACE / named(raw, "narration.wav")["rel_path"])
    raw_timings = in_workspace(WORKSPACE / named(raw, "timings.json")["rel_path"])
    timings = json.loads(raw_timings.read_text(encoding="utf-8"))
    if [row["text"] for row in timings["segments"]] != SEGMENTS:
        raise RuntimeError("Raw SAPI timing text differs from this production")
    with wave.open(str(raw_wav), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getcomptype()) != (1, 2, "NONE"):
            raise ValueError("Tail preparation supports only uncompressed PCM16 mono SAPI")
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    cursor = 0
    prepared = []
    measurements = []
    for row in timings["segments"]:
        length = row["frames"] * 2
        segment, measurement = trim_trailing_quiet(frames[cursor:cursor + length], sample_rate)
        cursor += length
        prepared.append(encode_wav(segment, sample_rate))
        measurements.append({"index": row["index"], "text": row["text"], **measurement})
    if cursor != len(frames):
        raise RuntimeError("Raw SAPI frame lengths do not match the timing document")
    identity = {"provider": "windows_sapi", "voice": VOICE, "rate": rate,
                "raw_wav": file_record(raw_wav), "raw_timings": file_record(raw_timings),
                "preprocessing": TRIM_POLICY, "sample_rate": sample_rate, "segments": measurements}
    key = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()
    prepared_root = in_workspace(output_root / "voice-preflight" / key, must_exist=False)
    prepared_root.mkdir(parents=True, exist_ok=True)
    for index, data in enumerate(prepared, start=1):
        target = prepared_root / f"segment-{index:02}.wav"
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError("Existing prepared voice bytes differ; preserving them")
        if not target.exists():
            target.write_bytes(data)
        measurements[index - 1]["prepared_wav"] = file_record(target)
    identity["preparation_key"] = key
    # cache_hit is an execution observation, not part of audio provenance or
    # request identity; omitting it keeps repeat runs on the same cache key.
    identity["raw_worker_result"] = {key: value for key, value in raw.items() if key != "cache_hit"}
    identity["directory"] = prepared_root.relative_to(WORKSPACE).as_posix()
    write_json(prepared_root / "preparation.json", identity)
    lookup = {text.replace("Claude Code", "クロードコード"): data
              for text, data in zip(SEGMENTS, prepared, strict=True)}

    def actual_prepared_sapi(text: str, *, voice: str, rate: int) -> bytes:
        if voice != identity["voice"] or rate != identity["rate"] or text not in lookup:
            raise ValueError("Prepared real SAPI voice does not match the requested synthesis")
        return lookup[text]

    return identity, actual_prepared_sapi


def validate_schedule(starts: list[int], voice: dict) -> list[dict]:
    sample_rate = voice["sample_rate"]
    rows = []
    for index, (start, segment) in enumerate(zip(starts, voice["segments"], strict=True)):
        first_frame = (start * sample_rate + 999) // 1000
        last_frame = first_frame + segment["trimmed_frames"]
        slot_start = (index // 2) * 5000
        slot_end = slot_start + 5000
        if start < slot_start or last_frame * 1000 > slot_end * sample_rate:
            raise ValueError(f"Narration segment {index + 1} does not fit its 5-second cut")
        if index < len(starts) - 1 and last_frame > (starts[index + 1] * sample_rate + 999) // 1000:
            raise ValueError(f"Narration segment {index + 1} overlaps the next segment")
        rows.append({"index": index, "text": SEGMENTS[index], "start_ms": start,
                     "end_ms": (last_frame * 1000) // sample_rate,
                     "detected_speech_start_ms": round(start + segment["detected_onset_ms"], 3),
                     "detected_speech_end_ms": round(start + segment["detected_speech_end_ms"], 3),
                     "cut_interval_ms": [slot_start, slot_end]})
    return rows


def import_video(service: StudioService, production_id: str, path: Path) -> dict:
    checked = in_workspace(path)
    before = file_record(checked)
    with checked.open("rb") as handle:
        result = service.import_production_video(production_id, stream=handle,
            filename_header=quote_from_bytes(checked.name.encode("utf-8"), safe="-_.!~*'()"),
            content_type="application/octet-stream", content_length=before["bytes"])
    artifact = result["artifact"]
    if before != file_record(checked) or artifact["sha256"] != before["sha256"] or artifact["bytes"] != before["bytes"]:
        raise RuntimeError("Video changed during import")
    return artifact


def register_artifacts(service: StudioService, production_id: str, result: dict) -> list[dict]:
    registered = []
    for artifact in result["artifacts"]:
        path = in_workspace(WORKSPACE / artifact["rel_path"])
        actual = file_record(path)
        if actual["bytes"] != artifact["bytes"] or actual["sha256"] != artifact["sha256"]:
            raise RuntimeError("Worker artifact failed physical verification")
        relative = actual["path"]
        registered.append(service.database.register_studio_artifact(production_id, {
            "id": stable_id("art", relative.casefold()), "rel_path": relative,
            "name": path.name, "kind": artifact["kind"],
            "media_type": artifact.get("media_type", artifact.get("mime")),
            "bytes": actual["bytes"], "mtime_ns": path.stat().st_mtime_ns,
            "sha256": actual["sha256"], "is_heavy": actual["bytes"] > 10 * 1024 * 1024}))
    return registered


def parse_starts(value: str) -> list[int]:
    try:
        values = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use six comma-separated milliseconds") from exc
    if len(values) != 6 or values != sorted(set(values)) or values[0] < 0 or values[-1] >= 15000:
        raise argparse.ArgumentTypeError("Six strictly increasing starts below 15000ms are required")
    return values


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-dir", type=Path, default=DEFAULT_OUTPUT / "sources")
    parser.add_argument("--hero-image", type=Path, default=DEFAULT_OUTPUT / "assets" / "desktop-hero.png")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--production-id", default=DEFAULT_PRODUCTION_ID)
    parser.add_argument("--title", default="Claude Code｜アプリで始める、小さな修正。")
    parser.add_argument("--rate", type=int, choices=(0, 1), default=0)
    parser.add_argument("--starts-ms", type=parse_starts, default=DEFAULT_STARTS)
    parser.add_argument("--probe-voice", action="store_true",
                        help="Generate and verify local narration only; do not render or touch Studio DB")
    args = parser.parse_args()
    if not re.fullmatch(r"production_[0-9a-f]{32}", args.production_id):
        parser.error("--production-id must be production_ plus 32 lowercase hex digits")
    output_root = in_workspace(args.output_dir, must_exist=False)
    if not args.probe_voice:
        sources_dir = in_workspace(args.sources_dir)
        sources = [in_workspace(sources_dir / name) for name in
                   ("cut_01_desktop.mp4", "cut_02_folder.mp4", "cut_03_review.mp4")]
        hero = file_record(in_workspace(args.hero_image))
    voice, synthesizer = prepare_voice(args.production_id, args.rate, output_root)
    schedule = validate_schedule(args.starts_ms, voice)
    if args.probe_voice:
        probe_key = hashlib.sha256(canonical_json({"voice": voice["preparation_key"],
            "starts": args.starts_ms}).encode("utf-8")).hexdigest().lower()
        result = generate_local_narration(WORKSPACE, production_id=args.production_id,
            run_id="run_" + probe_key[:32], payload=narration_payload(args.rate),
            segment_start_ms=args.starts_ms, synthesizer=synthesizer)
        report = {"local_execution": LOCAL_EXECUTION, "studio_run_id": None,
                  "voice_preparation": voice, "schedule": schedule, "scheduled_worker_result": result}
        report_path = WORKSPACE / voice["directory"] / f"scheduled-{probe_key}.json"
        write_json(report_path, report)
        print(json.dumps({"report": file_record(report_path), "schedule": schedule,
                          "duration_ms": result["duration_ms"]}, ensure_ascii=False), flush=True)
        return 0
    request = {"policy": POLICY, "production_id": args.production_id,
        "sources": [file_record(path) for path in sources], "source_trim_ms": [5250, 5250, 5000],
        "source_provenance": {"generated_image": {**hero, "generator": "builtin_imagegen",
            "generation_scope": "Created separately before this local assembly execution",
            "generation_network_and_cost": "Not asserted or measured by this assembly script"},
            "motion_sources": "Production-specific Remotion UI illustrations, not application screen captures"},
        "transition_ms": 250, "overlay": None, "narration": narration_payload(args.rate),
        "voice_preparation": voice, "narration_segment_start_ms": args.starts_ms,
        "measured_schedule": schedule, "script_sha256": digest_file(Path(__file__)),
        "caption_style_preset": "shorts_ja_large_v1", "audio_mix_preset": "narration_only_v1"}
    execution_key = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest().upper()
    worker_run_id = "run_" + execution_key[:32].lower()
    attempt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = in_workspace(output_root / "executions" / execution_key / attempt_stamp, must_exist=False)
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def log(phase: str, **fields: object) -> None:
        event = {"at": utc_now(), "elapsed_seconds": round(time.monotonic() - started, 3),
                 "phase": phase, **fields}
        with (output / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps(event, ensure_ascii=False), flush=True)

    manifest = {"schema_version": 1, "policy": POLICY, "status": "running",
        "execution_key": execution_key, "started_at": utc_now(), "request": request,
        "production_id": args.production_id, "studio_run_id": None, "studio_top_job_id": None,
        "worker_cache_run_id": worker_run_id, "local_execution": LOCAL_EXECUTION,
        "orchestration": "Production-specific direct existing worker adapters; not Quick Create or Detailed Test Video",
        "qc_attempt_id_scope": "Deterministic standalone assembly operation identity, not a Studio DB stage attempt",
        "stages": {}}
    write_json(output / "request.json", request)
    write_json(output / "manifest.json", manifest)
    lock = None
    service = None
    try:
        lock = WorkspaceInstanceLock(WORKSPACE)
        service = StudioService(WORKSPACE)
        service.create_production({"schema_version": 1, "production_id": args.production_id, "title": args.title})
        log("import_sources")
        imported = [import_video(service, args.production_id, path) for path in sources]
        manifest["source_imports"] = imported
        log("narration", preprocessing=TRIM_POLICY["implementation"])
        narration = generate_local_narration(WORKSPACE, production_id=args.production_id,
            run_id=worker_run_id, payload=narration_payload(args.rate),
            segment_start_ms=args.starts_ms, synthesizer=synthesizer)
        if narration["duration_ms"] > 15000:
            raise RuntimeError("Scheduled narration exceeds the 15-second timeline")
        manifest["stages"]["narration"] = narration
        register_artifacts(service, args.production_id, narration)
        write_json(output / "narration-result.json", narration)
        write_json(output / "manifest.json", manifest)
        log("narration_complete", duration_ms=narration["duration_ms"], cache_hit=narration["cache_hit"])
        clips = [{"video_artifact_id": artifact["id"], "source_path": artifact["rel_path"],
                  "source_bytes": artifact["bytes"], "source_sha256": artifact["sha256"],
                  "start_ms": 0, "end_ms": duration, "volume_percent": 0,
                  "visual_preset": "preserve_v1", "overlay": None,
                  "transition_to_next": {"type": "fade", "duration_ms": 250} if index < 2 else None}
                 for index, (artifact, duration) in enumerate(zip(imported, (5250, 5250, 5000), strict=True))]
        compiled = compile_remotion_timeline(clips)
        if compiled["duration_ms"] != 15000:
            raise RuntimeError("Timeline is not exactly 15 seconds")
        timeline_key = remotion_timeline_cache_key(clips, tool_identity=resolve_remotion_tool_identity(WORKSPACE))
        last_progress = [None]

        def progress(percent: int, phase: str) -> None:
            marker = (phase, int(percent) // 20)
            if marker != last_progress[0]:
                last_progress[0] = marker
                log("timeline", percent=percent, step=phase)

        timeline = generate_remotion_timeline(WORKSPACE, production_id=args.production_id,
            run_id=worker_run_id, cache_key=timeline_key, clips=clips, progress_callback=progress)
        manifest["stages"]["timeline"] = timeline
        register_artifacts(service, args.production_id, timeline)
        write_json(output / "timeline-result.json", timeline)
        write_json(output / "manifest.json", manifest)
        source = named(timeline, "remotion-preview.mp4")
        wav = named(narration, "narration.wav")
        captions = named(narration, "captions.srt")
        key = assembly_cache_key(source["sha256"], wav["sha256"], captions["sha256"], True,
            caption_style_preset="shorts_ja_large_v1", audio_mix_preset="narration_only_v1",
            tool_identity=resolve_tool_identity())
        log("assembly")
        assembly = assemble_local_video(WORKSPACE, production_id=args.production_id,
            run_id=worker_run_id, cache_key=key, source_video=source["rel_path"],
            narration_wav=wav["rel_path"], captions_srt=captions["rel_path"],
            include_captioned=True, caption_style_preset="shorts_ja_large_v1", audio_mix_preset="narration_only_v1")
        manifest["stages"]["assembly"] = assembly
        registered_masters = register_artifacts(service, args.production_id, assembly)
        write_json(output / "assembly-result.json", assembly)
        write_json(output / "manifest.json", manifest)
        operation_id = stable_id("attempt", f"{POLICY}:{execution_key}:assembly:{key}")
        manifest["standalone_assembly_operation_id"] = operation_id
        qc_results = {}
        final_imports = {}
        exports = []
        for variant in ("clean", "captioned"):
            master = next(item for item in registered_masters if item["name"] == f"master-{variant}.mp4")
            log("qc", variant=variant)
            qc_args = {"production_id": args.production_id, "run_id": worker_run_id,
                "assembly_attempt_id": operation_id, "assembly_artifact_id": master["id"],
                "variant": variant, "input_sha256": master["sha256"], "input_bytes": master["bytes"],
                "expected_duration_ms": 15000}
            qc_result = generate_local_qc(WORKSPACE, cache_key=qc_cache_key(**qc_args),
                input_path=master["rel_path"], **qc_args)
            qc_results[variant] = qc_result
            register_artifacts(service, args.production_id, qc_result)
            write_json(output / f"qc-{variant}.json", qc_result)
            manifest["stages"]["qc"] = qc_results
            write_json(output / "manifest.json", manifest)
            if qc_result["analysis_status"] != "succeeded" or qc_result["technical_verdict"] != "pass":
                raise RuntimeError(f"Technical QC did not pass for {variant}; see the retained report")
            exported = output / master["name"]
            shutil.copyfile(WORKSPACE / master["rel_path"], exported)
            exports.append(file_record(exported))
            final_imports[variant] = import_video(service, args.production_id, exported)
        for item in (wav, captions, named(narration, "timings.json")):
            exported = output / item["name"]
            shutil.copyfile(WORKSPACE / item["rel_path"], exported)
            exports.append(file_record(exported))
        manifest.update(status="succeeded", completed_at=utc_now(), exports=exports,
            final_imports=final_imports, technical_verdict="pass",
            elapsed_seconds=round(time.monotonic() - started, 3))
        write_json(output / "manifest.json", manifest)
        service.database.append_event("production", args.production_id, "production.custom_short_completed", {
            "schema_version": 1, "policy": POLICY, "execution_key": execution_key,
            "studio_run_id": None, "worker_cache_run_id": worker_run_id,
            "manifest": file_record(output / "manifest.json"),
            "master_artifact_ids": {variant: item["id"] for variant, item in final_imports.items()},
            "technical_verdict": "pass", "local_execution": LOCAL_EXECUTION,
            "source_provenance": request["source_provenance"]})
        log("completed", production_id=args.production_id, manifest=str((output / "manifest.json").relative_to(WORKSPACE)))
        return 0
    except BaseException as exc:
        manifest.update(status="failed", failed_at=utc_now(), error_type=type(exc).__name__, error=str(exc))
        write_json(output / "manifest.json", manifest)
        log("failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        if service is not None:
            service.close()
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
