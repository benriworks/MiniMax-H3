"""Audited illustration panels -> ordinary Studio Quick Create -> delivery.

This scoped driver never renders the panels, records a window, sends Claude
messages, or synthesizes a replacement voice. It imports hash-bound silent
panels and requires the already verified Sayaka narration cache before submit.
The separate original real-capture driver and its sealed evidence are read-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import quote_from_bytes

sys.dont_write_bytecode = True
WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from tools.studio.announcement_video import validate_announcement_recipe_payload
from tools.studio.assembly import resolve_tool_identity
from tools.studio.delivery import resolve_delivery_lineage, validate_delivery_package_payload
from tools.studio.instance_lock import WorkspaceInstanceLock
from tools.studio.quick_create import run_quick_create, validate_quick_create_request
from tools.studio.security import canonical_json, workspace_path
from tools.studio.service import StudioService

OUTPUT = WORKSPACE / "outputs/studio/verification/claude-illustrated-20260906"
POLICY = "claude-illustrated-standard-driver-v1"
INPUT_POLICY = "claude-illustrated-inputs-v1"
PRODUCTION_ID = "production_18812c9ff18e4955858700ee7815f678"
CAPTURE_ID = "art_9e344d7299e339f7781c17d5832985dc"
CAPTURE_SHA = "B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362"
PLACEHOLDER = "art_" + "0" * 32
NARRATION_KEY = "3BB6FE0690E4047A3EF07E863FE9668428A66B120C4541F03D02C04B1CFF7DB7"
NARRATION_IDS = {
    "narration.wav": "art_eade71b40f630c7ad35c39d6056a8f76",
    "captions.srt": "art_55a93676465b9c71505e6e10dd0d5a62",
    "timings.json": "art_61ac030669b5e480c35a4f304d2d6a93",
    "manifest.json": "art_c224cced532f70daaa7fe58c2017e44c",
}
NARRATIONS = (
    "条件を添えて、三案まとめて依頼。",
    "候補が出たら、使う表現を選びます。",
    "最後は、日付と文字数を確認。",
)
RETAINED_LOCKS: list[Any] = []


class DriverError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def fail(code: str) -> None:
    raise DriverError(code)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_path(value: str | Path, *, exists: bool = False) -> Path:
    if not isinstance(value, (str, Path)):
        fail("invalid_local_path")
    path = Path(value)
    lexical = path if path.is_absolute() else WORKSPACE / path
    try:
        relative = lexical.relative_to(WORKSPACE)
    except ValueError:
        fail("path_outside_workspace")
    cursor = WORKSPACE
    for part in relative.parts:
        if part in {"", ".", ".."}:
            fail("unsafe_local_path")
        cursor /= part
        if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
            fail("linked_path_rejected")
    return workspace_path(WORKSPACE, lexical, must_exist=exists)


def sha(path: Path) -> str:
    with safe_path(path, exists=True).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    path = safe_path(path, exists=True)
    if not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024:
        fail("invalid_json_size")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                fail("duplicate_json_key")
            value[key] = item
        return value

    def constant(_: str) -> None:
        fail("non_finite_json")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        fail("json_object_required")
    return value


def write_bytes(path: Path, data: bytes, *, immutable: bool = False) -> None:
    path = safe_path(path)
    if not path.is_relative_to(OUTPUT) or len(data) > 2 * 1024 * 1024:
        fail("output_write_rejected")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = safe_path(path)
    if immutable and path.exists():
        if not path.is_file() or path.read_bytes() != data:
            fail("immutable_output_changed")
        return
    temporary = safe_path(path.with_name(path.name + ".writing"))
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_json(path: Path, value: Any, *, immutable: bool = False) -> None:
    write_bytes(path, (canonical_json(value) + "\n").encode("utf-8"), immutable=immutable)


def emit(event: str, **fields: Any) -> None:
    row = canonical_json({"time": now(), "event": event, **fields})
    if len(row.encode("utf-8")) > 4096:
        fail("progress_message_too_large")
    print(row, flush=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with safe_path(OUTPUT / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(row + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def file_record(value: Any, *, roles: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"role", "path", "bytes", "sha256"}:
        fail("invalid_input_file_record")
    if not isinstance(value["role"], str) or value["role"] not in roles or not isinstance(value["path"], str):
        fail("invalid_input_file_role")
    if isinstance(value["bytes"], bool) or not isinstance(value["bytes"], int) or not 0 < value["bytes"] <= 2 * 1024**3:
        fail("invalid_input_file_size")
    if not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9A-F]{64}", value["sha256"]):
        fail("invalid_input_file_digest")
    path = safe_path(value["path"], exists=True)
    if not path.is_file() or path.stat().st_size != value["bytes"] or sha(path) != value["sha256"]:
        fail("input_file_changed")
    return {**value, "path": path.relative_to(WORKSPACE).as_posix()}


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "policy", "files", "panels", "recipe", "metadata"}:
        fail("invalid_illustration_manifest")
    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1 or value["policy"] != INPUT_POLICY:
        fail("invalid_illustration_policy")
    if not isinstance(value["files"], list) or not 2 <= len(value["files"]) <= 32:
        fail("invalid_illustration_sources")
    files = [file_record(item, roles={"illustration", "renderer", "renderer_dependency"}) for item in value["files"]]
    if ([item["role"] for item in files].count("illustration") != 1
            or [item["role"] for item in files].count("renderer") != 1
            or len({item["path"] for item in files}) != len(files)):
        fail("ambiguous_illustration_sources")
    if not isinstance(value["panels"], list) or len(value["panels"]) != 2:
        fail("invalid_panels")
    panels = [file_record(item, roles={"hook", "cta"}) for item in value["panels"]]
    if {item["role"] for item in panels} != {"hook", "cta"} or len({item["path"] for item in panels}) != 2:
        fail("ambiguous_panels")
    recipe = validate_announcement_recipe_payload(value["recipe"])
    if (recipe["template_preset"] != "screen_explainer_ja_v1" or recipe.get("screen_theme") != "claude_desktop_v1"
            or recipe["voice"] != "Microsoft Sayaka" or recipe["rate"] != 0 or recipe["pronunciations"] != []
            or recipe["audio_mix_preset"] != "narration_only_v1" or recipe["include_captioned"] is not True
            or recipe["caption_style_preset"] != "shorts_ja_large_v1" or recipe["variant"] != "captioned"):
        fail("approved_recipe_settings_required")
    for index, scene in enumerate(recipe["scenes"]):
        expected_id = CAPTURE_ID if index == 1 else PLACEHOLDER
        expected_start = 15000 if index == 1 else 0
        if (scene["video_artifact_id"] != expected_id or scene["start_ms"] != expected_start
                or scene["end_ms"] != expected_start + 7000 or scene["volume_percent"] != 0
                or scene.get("visual_preset", "preserve_v1") != "preserve_v1"
                or scene["narration"] != NARRATIONS[index]
                or (index != 1 and "focus_region" in scene)):
            fail("approved_scene_sources_and_voice_required")
    validate_delivery_package_payload({"schema_version": 1, "run_id": "run_" + "0" * 32,
        "source_job_id": "job_" + "0" * 32, "metadata": value["metadata"],
        "artifacts": {role: "art_" + f"{index:032x}" for index, role in enumerate(
            ("clean_master", "captioned_master", "captions", "technical_qc", "qc_ffprobe", "qc_manifest"), 1)}})
    return {**value, "files": files, "panels": sorted(panels, key=lambda item: item["role"]), "recipe": recipe}


def validate_panel_probe(probe: Any) -> None:
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict) or streams[0].get("codec_type") != "video":
        fail("silent_single_video_panel_required")
    stream = streams[0]
    try:
        valid = (stream.get("codec_name") == "h264" and stream.get("width") == 1920 and stream.get("height") == 1080
                 and Fraction(stream["avg_frame_rate"]) == 24 and int(stream["nb_frames"]) == 168
                 and abs(float(probe["format"]["duration"]) - 7) < .001)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        valid = False
    if not valid:
        fail("panel_must_be_7s_1080p24_h264")


def probe_panel(record: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    path = safe_path(record["path"], exists=True)
    probe = subprocess.run([identity["ffprobe"]["path"], "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                           capture_output=True, check=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    result = json.loads(probe.stdout)
    validate_panel_probe(result)
    subprocess.run([identity["ffmpeg"]["path"], "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
                   capture_output=True, check=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    file_record(record, roles={"hook", "cta"})
    return {"probe": result, "full_decode_verified": True}


def sealed_capture(service: StudioService) -> dict[str, Any]:
    path = WORKSPACE / "productions/SHORT_20260906_claude_desktop_real_capture/produce.py"
    spec = importlib.util.spec_from_file_location("claude_original_capture_driver", path)
    if spec is None or spec.loader is None:
        fail("capture_driver_unavailable")
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    cp = original.checkpoint()
    if cp["phase"] != "succeeded" or cp["production_id"] != PRODUCTION_ID:
        fail("successful_original_capture_required")
    job = service.claude_capture_job(PRODUCTION_ID, cp["request_id"])
    if not isinstance(job, dict) or job.get("id") != cp.get("job_id"):
        fail("original_capture_job_changed")
    evidence = original.capture_evidence(service, cp, job)
    if original.read_json(original.OUTPUT / "capture-result.json") != evidence:
        fail("original_capture_seal_changed")
    source = next(item for item in evidence["artifacts"] if item["name"] == "claude-capture.mp4")
    if source["id"] != CAPTURE_ID or source["sha256"] != CAPTURE_SHA:
        fail("original_capture_identity_changed")
    return evidence


def narration_artifacts(result: dict[str, Any]) -> dict[str, str]:
    records = result.get("artifacts")
    if not isinstance(records, list):
        fail("narration_artifact_identity_changed")
    if any(not isinstance(item, dict) for item in records):
        fail("narration_artifact_identity_changed")
    found = {item.get("name"): item.get("id", item.get("artifact_id")) for item in records}
    if len(records) != 4 or found != NARRATION_IDS:
        fail("narration_artifact_identity_changed")
    return found


def require_voice_cache(service: StudioService) -> dict[str, Any]:
    result = service._cached_local_narration_result(NARRATION_KEY, PRODUCTION_ID)
    if not isinstance(result, dict):
        fail("existing_voice_cache_required_no_resynthesis")
    narration_artifacts(result)
    return result


def import_panel(service: StudioService, record: dict[str, Any]) -> dict[str, Any]:
    checked = file_record(record, roles={"hook", "cta"})
    path = safe_path(checked["path"], exists=True)
    with path.open("rb") as stream:
        result = service.import_production_video(PRODUCTION_ID, stream=stream,
            filename_header=quote_from_bytes(path.name.encode("utf-8"), safe="-_.!~*'()"),
            content_type="video/mp4", content_length=checked["bytes"])
    artifact = result["artifact"]
    if (artifact.get("sha256") != checked["sha256"] or artifact.get("bytes") != checked["bytes"]
            or artifact.get("production_id") != PRODUCTION_ID or file_record(record, roles={"hook", "cta"}) != checked):
        fail("imported_panel_identity_changed")
    return result


def wait_job(service: StudioService, job_id: str) -> dict[str, Any]:
    deadline, last = time.monotonic() + 600, None
    while time.monotonic() < deadline:
        job = service.job(job_id)
        if not isinstance(job, dict) or job.get("id") != job_id:
            fail("recorded_job_missing")
        status = job.get("status")
        if status != last:
            emit("job_state", job_id=job_id, status=status)
            last = status
        if status not in {"queued", "running"}:
            if status != "succeeded":
                fail("recorded_job_not_successful")
            return job
        service.jobs.wait(job_id, timeout=10)
    fail("job_wait_timeout_reconcile_before_retry")


class ProgressService:
    def __init__(self, service: StudioService, folder: Path):
        self.service, self.folder, self.seen = service, folder, set()

    def save_announcement_recipe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        result = self.service.save_announcement_recipe(*args, **kwargs)
        write_json(self.folder / "saved-recipe.json", result)
        emit("recipe_saved", recipe_id=result["id"], revision=result["revision"])
        return result

    def execute_announcement_recipe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        require_voice_cache(self.service)
        result = self.service.execute_announcement_recipe(*args, **kwargs)
        write_json(self.folder / "render-submission.json", {key: result[key] for key in ("id", "run_id", "revision_id", "request_key")})
        emit("render_start", job_id=result["id"], run_id=result["run_id"])
        return result

    def job(self, job_id: str) -> dict[str, Any] | None:
        job = self.service.job(job_id)
        run_id = job.get("payload", {}).get("run_id") if isinstance(job, dict) else None
        run = self.service.run(run_id) if isinstance(run_id, str) else None
        for attempt in (run or {}).get("stage_attempts", []):
            if attempt.get("status") == "succeeded" and attempt.get("id") not in self.seen:
                self.seen.add(attempt["id"])
                emit("stage_complete", job_id=job_id, stage=attempt["stage"], attempt_id=attempt["id"])
        return job


def render(service: StudioService, manifest_path: Path) -> None:
    manifest = validate_manifest(read_json(manifest_path))
    capture = sealed_capture(service)
    voice = require_voice_cache(service)
    identity = resolve_tool_identity()
    probes = {item["role"]: probe_panel(item, identity) for item in manifest["panels"]}
    # Include this driver's bytes in immutable identity without rewriting source manifests.
    key = hashlib.sha256(canonical_json({"manifest": manifest, "driver_sha256": sha(Path(__file__))}).encode("utf-8")).hexdigest().upper()
    folder = safe_path(OUTPUT / "renders" / key)
    write_json(folder / "input-manifest.json", manifest, immutable=True)
    write_json(folder / "source-evidence.json", {"capture": capture, "panels": probes, "tools": identity,
        "narration_cache_key": NARRATION_KEY, "narration_artifact_ids": narration_artifacts(voice)}, immutable=True)
    imported = {item["role"]: import_panel(service, item) for item in manifest["panels"]}
    # Import is content-addressed and intentionally safe to retry after an interruption.
    write_json(folder / "panel-imports.json", imported)
    recipe = json.loads(canonical_json(manifest["recipe"]))
    for scene in recipe["scenes"]:
        if scene["role"] in imported:
            scene["video_artifact_id"] = imported[scene["role"]]["artifact"]["id"]
    request = validate_quick_create_request({"schema_version": 1, "production_id": PRODUCTION_ID,
        "recipe_id": "announcement_" + key[:32].lower(), "expected_revision": 0,
        "timeout_seconds": 1800, "recipe": recipe})
    write_json(folder / "request.json", request, immutable=True)
    emit("inputs_verified", manifest_sha256=key, panel_artifact_ids={role: item["artifact"]["id"] for role, item in imported.items()})
    summary = run_quick_create(ProgressService(service, folder), request, poll_interval_seconds=10)
    write_json(folder / "render-result.json", summary)
    top = service.job(summary["job_id"])
    if not isinstance(top, dict) or top.get("status") != "succeeded":
        fail("render_not_successful")
    result = top["result"]
    children = {stage: service.job(item["job_id"]) for stage, item in result["children"].items()}
    narrated = children["narration"]["result"]
    narration_artifacts(narrated)
    if narrated.get("cache_hit") is not True:
        fail("narration_was_not_reused")
    # Recheck every source after rendering before marking this request completed.
    if validate_manifest(read_json(manifest_path)) != manifest or sealed_capture(service) != capture:
        fail("source_changed_during_render")

    def artifact(stage: str, name: str) -> str:
        matches = [item for item in children[stage]["result"]["artifacts"] if item.get("name") == name]
        if len(matches) != 1:
            fail("delivery_artifact_not_unique")
        return matches[0].get("id", matches[0].get("artifact_id"))

    delivery_request = {"schema_version": 1, "run_id": result["run_id"], "source_job_id": top["id"],
        "metadata": manifest["metadata"], "artifacts": {
            "clean_master": artifact("assembly", "master-clean.mp4"),
            "captioned_master": artifact("assembly", "master-captioned.mp4"),
            "captions": artifact("narration", "captions.srt"),
            "technical_qc": artifact("qc", "technical-qc.json"),
            "qc_ffprobe": artifact("qc", "ffprobe.json"), "qc_manifest": artifact("qc", "manifest.json")}}
    lineage = resolve_delivery_lineage(service.database, PRODUCTION_ID, delivery_request)
    write_json(folder / "delivery-request.json", delivery_request, immutable=True)
    marker = folder / "delivery-checkpoint.json"
    if marker.exists():
        known = read_json(marker)
        if known.get("request") != delivery_request or not known.get("job_id"):
            fail("delivery_submission_unknown_reconcile_before_retry")
        delivery = service.job(known["job_id"])
        if not isinstance(delivery, dict) or delivery.get("kind") != "delivery_package" or delivery.get("production_id") != PRODUCTION_ID:
            fail("delivery_checkpoint_invalid")
    else:
        write_json(marker, {"request": delivery_request, "job_id": None})
        delivery = service.create_delivery_package(PRODUCTION_ID, delivery_request)
        write_json(marker, {"request": delivery_request, "job_id": delivery["id"]})
    terminal = wait_job(service, delivery["id"])
    write_json(folder / "delivery-result.json", terminal["result"])
    metadata = manifest["metadata"]
    publication = (f"タイトル\n{metadata['title']}\n\n説明文\n{metadata['description']}\n\n"
        f"制作: {PRODUCTION_ID}\n生成Run: {result['run_id']}\n生成Job: {top['id']}\n納品Job: {delivery['id']}\n"
        f"字幕あり: {lineage['artifacts']['captioned_master']['rel_path']}\n"
        f"字幕なし: {lineage['artifacts']['clean_master']['rel_path']}\n"
        "\n生成イラストは概念図です。実UI・実際の思考内容ではありません。音声改善は保留中。\n"
        "技術QCと人による作品品質・公開判定は別です。\n")
    write_bytes(folder / "publication.txt", publication.encode("utf-8"), immutable=True)
    final = {"schema_version": 1, "policy": POLICY, "completed_at": now(), "production_id": PRODUCTION_ID,
        "capture_job_id": capture["job_id"], "input_manifest_key": key, "render": summary,
        "delivery_job_id": delivery["id"], "delivery": terminal["result"], "metadata": metadata,
        "narration_cache_hit": True, "narration_artifact_ids": NARRATION_IDS,
        "source_artifact_ids": [scene["video_artifact_id"] for scene in recipe["scenes"]],
        "publication_text": (folder / "publication.txt").relative_to(WORKSPACE).as_posix(),
        "public_quality_verified": False, "paid_api_calls_by_driver": 0, "external_chat_actions_by_driver": 0,
        "capture_actions_by_driver": 0, "image_generation_scope": "Separate prior built-in imagegen action; not performed or cost-measured by driver"}
    write_json(folder / "result.json", final)
    write_json(OUTPUT / "result.json", final)
    emit("production_complete", run_id=result["run_id"], job_id=top["id"], delivery_job_id=delivery["id"],
         result_path=(folder / "result.json").relative_to(WORKSPACE).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["render"])
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    lock, service, code = None, None, 0
    try:
        lock = WorkspaceInstanceLock(WORKSPACE)
        service = StudioService(WORKSPACE)
        render(service, args.manifest)
    except KeyboardInterrupt:
        code = 130
        print('{"error":"interrupted_reconcile_saved_checkpoint"}', file=sys.stderr)
    except Exception as exc:
        candidate = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        error = candidate if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9_.-]{1,128}", candidate) else "illustrated_driver_failed"
        print(canonical_json({"error": error}), file=sys.stderr)
        if lock is not None:
            try:
                emit("driver_failed", code=error)
            except Exception:
                pass
        code = 2
    finally:
        closed = service is None
        if service is not None:
            try:
                service.close()
                closed = True
            except Exception:
                print('{"error":"studio_shutdown_incomplete"}', file=sys.stderr)
                code = 2
        if lock is not None:
            if closed:
                lock.close()
            else:
                RETAINED_LOCKS.append(lock)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
