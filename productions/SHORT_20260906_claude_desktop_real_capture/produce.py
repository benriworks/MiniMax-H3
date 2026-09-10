"""Approved Claude demo: ordinary Studio capture -> recipe -> render -> delivery.

This driver never operates Claude, sends chat messages, starts an HTTP server,
or calls a paid provider. ``capture`` is the explicit start of the previously
approved single-window recording. ``render`` uses the supplied normal recipe;
it does not quietly generate a replacement script, voice, or visual source.
Only workflow outputs under outputs/studio/verification are written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any
from uuid import uuid4

sys.dont_write_bytecode = True
WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from tools.studio.delivery import resolve_delivery_lineage, validate_delivery_package_payload
from tools.studio.instance_lock import StudioInstanceLockError, WorkspaceInstanceLock
from tools.studio.quick_create import run_quick_create, validate_quick_create_request
from tools.studio.security import canonical_json, workspace_path
from tools.studio.service import StudioService

OUTPUT = WORKSPACE / "outputs/studio/verification/claude-desktop-real-20260906"
POLICY = "claude-desktop-real-standard-driver-v1"
CAPTURE_FILES = {"claude-capture.mp4", "first-frame.png", "last-frame.png",
                 "capture-report.json", "ffprobe.json", "manifest.json"}
ACTIVE = {"queued", "running"}
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
    candidate = Path(value)
    lexical = candidate if candidate.is_absolute() else WORKSPACE / candidate
    try:
        parts = lexical.relative_to(WORKSPACE).parts
    except ValueError:
        fail("path_outside_workspace")
    cursor = WORKSPACE
    for part in parts:
        if part in {"", ".", ".."}:
            fail("unsafe_path")
        cursor /= part
        if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
            fail("linked_path_rejected")
    return workspace_path(WORKSPACE, lexical, must_exist=exists)


def read_json(path: Path, maximum: int = 1024 * 1024) -> dict[str, Any]:
    path = safe_path(path, exists=True)
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        fail("json_size_invalid")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> None:
        fail("non_finite_json")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                       parse_constant=invalid_constant)
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
    # A interrupted write is not silently replaced or deleted on the next run.
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_json(path: Path, value: Any, *, immutable: bool = False) -> None:
    write_bytes(path, (canonical_json(value) + "\n").encode("utf-8"), immutable=immutable)


def emit(event: str, **fields: Any) -> None:
    row = {"time": now(), "event": event, **fields}
    line = canonical_json(row)
    if len(line.encode("utf-8")) > 4096:
        fail("progress_message_too_large")
    print(line, flush=True)
    output = safe_path(OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    log = safe_path(output / "events.jsonl")
    with log.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def sha(path: Path) -> str:
    with safe_path(path, exists=True).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def checkpoint() -> dict[str, Any]:
    value = read_json(OUTPUT / "checkpoint.json")
    required = {"schema_version", "policy", "production_id", "request_id",
                "title", "duration_ms", "phase"}
    if (not required <= value.keys() or set(value) - required - {"job_id", "capture_evidence"}
            or value["schema_version"] != 1 or value["policy"] != POLICY
            or not re.fullmatch(r"production_[0-9a-f]{32}", str(value["production_id"]))
            or not re.fullmatch(r"claude_capture_[0-9a-f]{32}", str(value["request_id"]))
            or isinstance(value["duration_ms"], bool) or not isinstance(value["duration_ms"], int)
            or not 15000 <= value["duration_ms"] <= 30000
            or value["phase"] not in {"planned", "prepared", "submitting", "accepted", "succeeded"}):
        fail("capture_checkpoint_invalid")
    if "job_id" in value and not re.fullmatch(r"job_[0-9a-f]{32}", str(value["job_id"])):
        fail("capture_checkpoint_invalid")
    return value


def save_checkpoint(value: dict[str, Any]) -> None:
    write_json(OUTPUT / "checkpoint.json", value)


def wait_job(service: StudioService, job_id: str, *, timeout: float) -> dict[str, Any]:
    deadline, last = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        job = service.job(job_id)
        if not isinstance(job, dict) or job.get("id") != job_id:
            fail("job_checkpoint_missing")
        status = job.get("status")
        if status != last:
            emit("job_state", job_id=job_id, status=status)
            last = status
        if status not in ACTIVE:
            if status != "succeeded":
                fail("recorded_job_not_successful")
            return job
        service.jobs.wait(job_id, timeout=min(10.0, max(0.0, deadline - time.monotonic())))
    fail("job_wait_timeout_reconcile_before_retry")


def capture_evidence(service: StudioService, cp: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    payload, result = job.get("payload", {}), job.get("result", {})
    if (job.get("kind") != "claude_window_capture" or job.get("status") != "succeeded"
            or job.get("production_id") != cp["production_id"]
            or payload.get("capture_request_id") != cp["request_id"]
            or payload.get("duration_ms") != cp["duration_ms"]
            or result.get("provider") != "local_claude_window_capture"
            or result.get("capture_request_id") != cp["request_id"]
            or result.get("audio_mode") != "none" or result.get("capture_only") is not True
            or result.get("actual_capture_performed") is not True
            or result.get("content_quality_verified") is not False
            or result.get("public_release_ready") is not False):
        fail("capture_evidence_invalid")
    actual = result.get("duration_ms")
    if isinstance(actual, bool) or not isinstance(actual, int) or not cp["duration_ms"] <= actual < cp["duration_ms"] + 1000 / 24:
        fail("capture_duration_invalid")
    records = result.get("artifacts")
    if not isinstance(records, list) or len(records) != 6:
        fail("capture_artifacts_invalid")
    root = safe_path(WORKSPACE / "outputs/studio/claude-captures" / cp["production_id"] / cp["request_id"], exists=True)
    evidence, names = [], set()
    for item in records:
        registered = service.database.get_artifact(item.get("id", ""))
        if not isinstance(registered, dict) or registered.get("production_id") != cp["production_id"] or not registered.get("available"):
            fail("capture_artifact_not_registered")
        name = registered.get("name")
        if name not in CAPTURE_FILES or name in names:
            fail("capture_artifact_set_changed")
        names.add(name)
        path = safe_path(registered["rel_path"], exists=True)
        if path != root / name or path.stat().st_size != registered["bytes"] or sha(path) != registered["sha256"]:
            fail("capture_artifact_changed")
        if any(item.get(key) != registered.get(key) for key in ("id", "name", "rel_path", "bytes", "sha256")):
            fail("capture_artifact_registration_mismatch")
        evidence.append({key: registered[key] for key in ("id", "name", "rel_path", "bytes", "sha256")})
    report = read_json(root / "capture-report.json")
    if report.get("full_decode_verified") is not True or report.get("audio_streams") != 0:
        fail("capture_decode_evidence_missing")
    return {
        "schema_version": 1, "policy": POLICY, "production_id": cp["production_id"],
        "request_id": cp["request_id"], "job_id": job["id"], "control_run_id": None,
        "duration_ms": actual, "requested_duration_ms": cp["duration_ms"],
        "audio_mode": "none", "content_quality_verified": False, "public_release_ready": False,
        "artifacts": sorted(evidence, key=lambda item: item["name"]),
        "capture_report": report, "capture_manifest": read_json(root / "manifest.json"),
        "scope": "local Studio recording only; Claude preparation and chat are outside this driver",
    }


def capture(service: StudioService, args: argparse.Namespace) -> None:
    path = OUTPUT / "checkpoint.json"
    if path.exists():
        cp = checkpoint()
        if cp["duration_ms"] != args.duration_ms:
            fail("capture_duration_changed_use_original_checkpoint")
    else:
        cp = {"schema_version": 1, "policy": POLICY, "production_id": "production_" + uuid4().hex,
              "request_id": "claude_capture_" + uuid4().hex,
              "title": "Claude Desktop 実画面解説：架空カフェ", "duration_ms": args.duration_ms,
              "phase": "planned"}
        save_checkpoint(cp)
    if cp["phase"] == "planned":
        service.create_production({"schema_version": 1, "production_id": cp["production_id"], "title": cp["title"]})
        cp["phase"] = "prepared"
        save_checkpoint(cp)
    job = service.claude_capture_job(cp["production_id"], cp["request_id"])
    if job is None:
        if cp["phase"] != "prepared":
            fail("capture_submission_unknown_no_automatic_resend")
        binding = hashlib.sha256(secrets.token_bytes(32)).hexdigest().upper()
        inspected = service.inspect_claude_capture({}, session_binding_digest=binding)
        selections = inspected.get("selections")
        if inspected.get("available") is not True or not isinstance(selections, list) or len(selections) != 1:
            fail("exactly_one_verified_claude_window_required")
        token = selections[0].get("selection_token")
        # Persist before submit. Neither token nor native window identity is written.
        cp["phase"] = "submitting"
        save_checkpoint(cp)
        emit("capture_start", production_id=cp["production_id"], request_id=cp["request_id"], duration_ms=cp["duration_ms"])
        job = service.execute_claude_capture(cp["production_id"], {
            "request_id": cp["request_id"], "selection_token": token,
            "duration_ms": cp["duration_ms"], "confirm_capture": True,
        }, session_binding_digest=binding)
        del token, selections, inspected, binding
    if cp.get("job_id") not in (None, job["id"]):
        fail("capture_job_checkpoint_changed")
    cp.update(job_id=job["id"], phase="accepted")
    save_checkpoint(cp)
    terminal = wait_job(service, job["id"], timeout=args.duration_ms / 1000 + 180)
    evidence = capture_evidence(service, cp, terminal)
    write_json(OUTPUT / "capture-result.json", evidence, immutable=True)
    cp.update(phase="succeeded", capture_evidence="capture-result.json")
    save_checkpoint(cp)
    video = next(item for item in evidence["artifacts"] if item["name"] == "claude-capture.mp4")
    emit("capture_complete", production_id=cp["production_id"], job_id=job["id"],
         video_artifact_id=video["id"], duration_ms=evidence["duration_ms"], sha256=video["sha256"])


class ProgressService:
    """Expose the existing Quick Create interface and retain exact execution IDs."""
    def __init__(self, service: StudioService, folder: Path):
        self.service, self.folder = service, folder
        self.seen: set[str] = set()

    def save_announcement_recipe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        result = self.service.save_announcement_recipe(*args, **kwargs)
        write_json(self.folder / "saved-recipe.json", result)
        emit("recipe_saved", recipe_id=result["id"], revision=result["revision"])
        return result

    def execute_announcement_recipe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
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


def render(service: StudioService, args: argparse.Namespace) -> None:
    cp = checkpoint()
    if cp["phase"] != "succeeded":
        fail("successful_capture_checkpoint_required")
    capture_job = service.claude_capture_job(cp["production_id"], cp["request_id"])
    if not isinstance(capture_job, dict) or capture_job.get("id") != cp.get("job_id"):
        fail("capture_job_checkpoint_changed")
    evidence = capture_evidence(service, cp, capture_job)
    if read_json(OUTPUT / "capture-result.json") != evidence:
        fail("sealed_capture_evidence_changed")
    source = next(item for item in evidence["artifacts"] if item["name"] == "claude-capture.mp4")
    body = read_json(args.request, maximum=256 * 1024)
    metadata = body.pop("metadata", None)
    request = validate_quick_create_request(body)
    recipe = request["recipe"]
    if (request["production_id"] != cp["production_id"]
            or recipe["template_preset"] != "screen_explainer_ja_v1"
            or recipe["audio_mix_preset"] != "narration_only_v1"
            or recipe["include_captioned"] is not True or recipe["variant"] != "captioned"
            or not recipe["voice"]):
        fail("approved_local_recipe_required")
    for scene in recipe["scenes"]:
        if scene["video_artifact_id"] != source["id"] or scene["volume_percent"] != 0 or scene["end_ms"] > evidence["duration_ms"]:
            fail("recipe_must_use_verified_silent_capture")
    # Apply the real metadata contract before generating any speech.
    validate_delivery_package_payload({"schema_version": 1, "run_id": "run_" + "0" * 32,
        "source_job_id": "job_" + "0" * 32, "metadata": metadata,
        "artifacts": {role: "art_" + f"{i:032x}" for i, role in enumerate(
            ("clean_master", "captioned_master", "captions", "technical_qc", "qc_ffprobe", "qc_manifest"), 1)}})
    normalized = {**request, "metadata": metadata}
    key = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest().upper()
    folder = safe_path(OUTPUT / "renders" / key)
    write_json(folder / "request.json", normalized, immutable=True)
    # Existing ordinary workers own all Run, child Job, cache and QC semantics.
    summary = run_quick_create(ProgressService(service, folder), request, poll_interval_seconds=10)
    write_json(folder / "render-result.json", summary)
    top = service.job(summary["job_id"])
    if not isinstance(top, dict) or top.get("status") != "succeeded":
        fail("render_not_successful")
    result = top["result"]
    children = {stage: service.job(item["job_id"]) for stage, item in result["children"].items()}

    def artifact(stage: str, name: str) -> str:
        child = children[stage]
        matches = [item for item in child["result"]["artifacts"] if item.get("name") == name]
        if len(matches) != 1:
            fail("delivery_artifact_not_unique")
        return matches[0].get("id", matches[0].get("artifact_id"))

    delivery_request = {"schema_version": 1, "run_id": result["run_id"], "source_job_id": top["id"],
        "metadata": metadata, "artifacts": {
            "clean_master": artifact("assembly", "master-clean.mp4"),
            "captioned_master": artifact("assembly", "master-captioned.mp4"),
            "captions": artifact("narration", "captions.srt"),
            "technical_qc": artifact("qc", "technical-qc.json"),
            "qc_ffprobe": artifact("qc", "ffprobe.json"),
            "qc_manifest": artifact("qc", "manifest.json"),
        }}
    lineage = resolve_delivery_lineage(service.database, cp["production_id"], delivery_request)
    write_json(folder / "delivery-request.json", delivery_request)
    marker = folder / "delivery-checkpoint.json"
    if marker.exists():
        known = read_json(marker)
        if known.get("request") != delivery_request or not known.get("job_id"):
            fail("delivery_submission_unknown_reconcile_before_retry")
        delivery = service.job(known["job_id"])
        if not isinstance(delivery, dict) or delivery.get("kind") != "delivery_package" or delivery.get("production_id") != cp["production_id"]:
            fail("delivery_checkpoint_invalid")
    else:
        write_json(marker, {"request": delivery_request, "job_id": None})
        delivery = service.create_delivery_package(cp["production_id"], delivery_request)
        write_json(marker, {"request": delivery_request, "job_id": delivery["id"]})
    terminal = wait_job(service, delivery["id"], timeout=600)
    write_json(folder / "delivery-result.json", terminal["result"])
    publication = (f"タイトル\n{metadata['title']}\n\n説明文\n{metadata['description']}\n\n"
        f"制作: {cp['production_id']}\n収録Job: {cp['job_id']}\n生成Run: {result['run_id']}\n"
        f"生成Job: {top['id']}\n納品Job: {delivery['id']}\n"
        f"字幕あり: {lineage['artifacts']['captioned_master']['rel_path']}\n"
        f"字幕なし: {lineage['artifacts']['clean_master']['rel_path']}\n"
        f"字幕ありSHA-256: {lineage['artifacts']['captioned_master']['sha256']}\n"
        "\n技術QCと公開品質は別です。SAPIの音質・発音と画面の可読性は公開前に確認してください。\n")
    write_bytes(folder / "publication.txt", publication.encode("utf-8"), immutable=True)
    final = {"schema_version": 1, "policy": POLICY, "completed_at": now(),
        "production_id": cp["production_id"], "capture_job_id": cp["job_id"],
        "render": summary, "delivery_job_id": delivery["id"], "delivery": terminal["result"],
        "metadata": metadata, "request_sha256": key,
        "publication_text": (folder / "publication.txt").relative_to(WORKSPACE).as_posix(),
        "public_quality_verified": False, "paid_api_calls_by_driver": 0,
        "external_chat_actions_by_driver": 0}
    write_json(folder / "result.json", final)
    write_json(OUTPUT / "result.json", final)
    emit("production_complete", production_id=cp["production_id"], run_id=result["run_id"],
         render_job_id=top["id"], delivery_job_id=delivery["id"],
         result_path=(folder / "result.json").relative_to(WORKSPACE).as_posix())


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    record = commands.add_parser("capture", help="Explicitly start or reconcile the approved single-Claude-window silent capture")
    record.add_argument("--duration-ms", type=int, default=21000, help="15000..30000 ms; default 21000")
    produce = commands.add_parser("render", help="Run a normal screen-explainer Quick Create request plus metadata")
    produce.add_argument("request", type=Path, help="UTF-8 JSON: normal Quick Create fields plus metadata {title, description}")
    return value


def main() -> int:
    args = parser().parse_args()
    if args.command == "capture" and not 15000 <= args.duration_ms <= 30000:
        print('{"error":"duration_ms_must_be_15000_to_30000"}', file=sys.stderr)
        return 2
    lock, service, exit_code = None, None, 0
    try:
        # Fail before touching workflow files if an existing Studio owns the DB.
        lock = WorkspaceInstanceLock(WORKSPACE)
        service = StudioService(WORKSPACE)  # default DB, no HTTP server
        if args.command == "capture":
            capture(service, args)
        else:
            render(service, args)
    except StudioInstanceLockError:
        print('{"error":"workspace_in_use_stop_existing_studio_first"}', file=sys.stderr)
        exit_code = 2
    except KeyboardInterrupt:
        print('{"error":"interrupted_reconcile_saved_checkpoint"}', file=sys.stderr)
        exit_code = 130
    except Exception as exc:
        candidate = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        code = candidate if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9_.-]{1,128}", candidate) else "production_driver_failed"
        print(canonical_json({"error": code}), file=sys.stderr)
        if lock is not None:
            try:
                emit("driver_failed", code=code)
            except Exception:
                pass
        exit_code = 2
    finally:
        closed = service is None
        if service is not None:
            try:
                service.close()
                closed = True
            except Exception:
                print('{"error":"studio_shutdown_incomplete"}', file=sys.stderr)
                exit_code = 2
        if lock is not None:
            if closed:
                lock.close()
            else:
                RETAINED_LOCKS.append(lock)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
