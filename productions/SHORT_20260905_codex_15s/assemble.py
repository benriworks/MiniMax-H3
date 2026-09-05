"""Assemble this original Codex short with scheduled local SAPI narration.

This is production-specific orchestration, not a Quick Create execution.
The existing worker adapters own rendering, assembly, cache validation and QC.
Studio receives actual source/final imports, intermediate artifacts and an
explicit production event; no ordinary pipeline Job or queued Run is invented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote_from_bytes
from uuid import NAMESPACE_URL, uuid5

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

PRODUCTION_NAME = "SHORT_20260905_codex_15s"
DEFAULT_PRODUCTION_ID = "production_" + uuid5(NAMESPACE_URL, f"MiniMaxH3/{PRODUCTION_NAME}").hex
SEGMENTS = ["作りたいものを、", "言葉で伝える。", "Codexが、", "実装やテストを手伝う。", "成果を確かめて、", "次の一歩へ。"]
DEFAULT_STARTS = [200, 2100, 5100, 6950, 10200, 12350]
POLICY = "codex-short-scheduled-local-workers-v1"


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
    info = checked.stat()
    return {"path": checked.relative_to(WORKSPACE).as_posix(), "name": name or checked.name,
            "bytes": info.st_size, "sha256": digest_file(checked)}


def import_video(service: StudioService, production_id: str, path: Path) -> dict:
    checked = in_workspace(path)
    before = file_record(checked)
    with checked.open("rb") as handle:
        result = service.import_production_video(production_id, stream=handle,
            filename_header=quote_from_bytes(checked.name.encode("utf-8"), safe="-_.!~*'()"),
            content_type="application/octet-stream", content_length=before["bytes"])
    after = file_record(checked)
    artifact = result["artifact"]
    if before != after or artifact["sha256"] != before["sha256"] or artifact["bytes"] != before["bytes"]:
        raise RuntimeError("Source changed during import")
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
            "sha256": actual["sha256"], "is_heavy": actual["bytes"] > 10 * 1024 * 1024,
        }))
    return registered


def named(result: dict, name: str) -> dict:
    matches = [artifact for artifact in result["artifacts"] if artifact["name"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"Missing unique worker output: {name}")
    return matches[0]


def parse_starts(value: str) -> list[int]:
    try:
        values = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use six comma-separated milliseconds") from exc
    if len(values) != 6 or values != sorted(set(values)) or values[0] < 0 or values[-1] >= 15000:
        raise argparse.ArgumentTypeError("Six strictly increasing starts below 15000ms are required")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-dir", type=Path,
        default=WORKSPACE / "outputs" / "productions" / PRODUCTION_NAME / "sources")
    parser.add_argument("--output-dir", type=Path,
        default=WORKSPACE / "outputs" / "productions" / PRODUCTION_NAME)
    parser.add_argument("--production-id", default=DEFAULT_PRODUCTION_ID)
    parser.add_argument("--title", default="Codex｜作りたいを、次の一歩へ。")
    parser.add_argument("--rate", type=int, choices=range(-10, 11), default=0)
    parser.add_argument("--starts-ms", type=parse_starts, default=DEFAULT_STARTS)
    args = parser.parse_args()
    if not re.fullmatch(r"production_[0-9a-f]{32}", args.production_id):
        parser.error("--production-id must be production_ plus 32 lowercase hex digits")
    sources_dir = in_workspace(args.sources_dir)
    sources = [in_workspace(sources_dir / name) for name in
        ("cut_01_prompt.mp4", "cut_02_build.mp4", "cut_03_review.mp4")]
    source_records = [file_record(path) for path in sources]
    narration_payload = {"segments": [{"text": text} for text in SEGMENTS],
        "voice": "Microsoft Haruka Desktop", "rate": args.rate,
        "pronunciations": [{"source": "Codex", "target": "コーデックス"}]}
    request = {"policy": POLICY, "production_id": args.production_id,
        "sources": source_records, "source_trim_ms": [5250, 5250, 5000],
        "transition_ms": 250, "overlay": None, "narration": narration_payload,
        "narration_segment_start_ms": args.starts_ms, "script_sha256": digest_file(Path(__file__)),
        "caption_style_preset": "shorts_ja_large_v1", "audio_mix_preset": "narration_only_v1"}
    execution_key = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest().upper()
    worker_run_id = "run_" + execution_key[:32].lower()
    output_root = in_workspace(args.output_dir, must_exist=False)
    attempt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = in_workspace(output_root / "executions" / execution_key / attempt_stamp, must_exist=False)
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "events.jsonl"
    started = time.monotonic()

    def log(phase: str, **fields: object) -> None:
        event = {"at": utc_now(), "elapsed_seconds": round(time.monotonic() - started, 3),
                 "phase": phase, **fields}
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps(event, ensure_ascii=False), flush=True)

    manifest = {"schema_version": 1, "policy": POLICY, "status": "running",
        "execution_key": execution_key, "started_at": utc_now(), "request": request,
        "production_id": args.production_id, "studio_run_id": None, "studio_top_job_id": None,
        "worker_cache_run_id": worker_run_id, "network_used": False, "billable": False,
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
        log("narration")
        narration = generate_local_narration(WORKSPACE, production_id=args.production_id,
            run_id=worker_run_id, payload=narration_payload, segment_start_ms=args.starts_ms)
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
            "technical_verdict": "pass", "network_used": False, "billable": False})
        log("completed", production_id=args.production_id, manifest=str((output / "manifest.json").relative_to(WORKSPACE)))
        return 0
    except BaseException as exc:
        manifest.update(status="failed", failed_at=utc_now(), error_type=type(exc).__name__, error=str(exc))
        write_json(output / "manifest.json", manifest)
        log("failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        # Release the single-writer lock only after the real service drains.
        if service is not None:
            service.close()
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
