from __future__ import annotations

"""Source-only Claude capture orchestration; no fake render Run or TTS job."""

import hashlib
import re
from pathlib import Path
from typing import Any

from .claude_capture import ClaudeCaptureController, ClaudeCaptureError, cleanup_capture_root, selection_token_digest
from .security import stable_id, validate_identifier, workspace_path

REQUEST_ID = re.compile(r"^claude_capture_[0-9a-f]{32}$")
SPECS = {
    "claude-capture.mp4": ("video", "video/mp4"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}


def capture_root(workspace: Path, production_id: str, request_id: str) -> Path:
    validate_identifier(production_id, label="production id")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("Claude capture request ID is invalid")
    return workspace_path(workspace, f"outputs/studio/claude-captures/{production_id}/{request_id}")


def cleanup_interrupted_claude_captures(workspace: Path, database: Any) -> None:
    # Only this database's admitted requests are owned here. An alternate
    # verification database must not delete another database's valid media.
    for job in database.list_incomplete_claude_captures():
        request_id = job["payload"].get("capture_request_id")
        root = capture_root(workspace, job["production_id"], request_id)
        cleanup_capture_root(root, workspace=workspace)
        database.resolve_claude_capture_cleanup(job["id"])


class ClaudeCaptureService:
    def __init__(self, workspace: Path, database: Any, jobs: Any, submit_lock: Any):
        self.workspace, self.database, self.jobs, self.submit_lock = workspace, database, jobs, submit_lock
        self.controller = ClaudeCaptureController(workspace)

    def inspect(self, body: Any, *, session_binding: str) -> dict[str, Any]:
        if not isinstance(body, dict) or body:
            raise ValueError("Claude inspection requires an empty body")
        return self.controller.inspect(session_binding=session_binding)

    def lookup(self, production_id: str, request_id: str) -> dict[str, Any] | None:
        capture_root(self.workspace, production_id, request_id)
        if self.database.get_production_detail(production_id) is None:
            raise KeyError("production not found")
        return self.database.find_claude_capture_job(production_id, request_id)

    def execute(self, production_id: str, body: Any, *, session_binding: str) -> dict[str, Any]:
        if not isinstance(body, dict) or set(body) != {"request_id", "selection_token", "duration_ms", "confirm_capture"}:
            raise ValueError("Claude capture request fields are invalid")
        duration = body["duration_ms"]
        if isinstance(duration, bool) or not isinstance(duration, int) or not 15000 <= duration <= 30000 or body["confirm_capture"] is not True:
            raise ValueError("Claude capture requires 15-30 seconds and explicit confirmation")
        request_id = body["request_id"]
        root = capture_root(self.workspace, production_id, request_id)
        digest = selection_token_digest(body["selection_token"])
        if not isinstance(session_binding, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", session_binding):
            raise ValueError("Claude capture session binding is invalid")
        with self.submit_lock:
            previous = self.lookup(production_id, request_id)
            if previous is not None:
                audit = previous["payload"]
                if audit.get("duration_ms") != duration or audit.get("selection_digest") != digest or audit.get("requester_digest") != session_binding.upper():
                    raise ValueError("Claude capture request ID was already used with different settings")
                return {**previous, "deduplicated": True}
            if self.database.has_unresolved_claude_capture_cleanup():
                raise ClaudeCaptureError(
                    "A prior capture still requires private-media cleanup. Restart Studio after resolving the cleanup error.",
                    code="claude_capture_cleanup_failed",
                )
            if self.jobs.active_job_ids_for_lane("capture") or self.database.find_active_windows_capture_job() is not None:
                raise ValueError("Another capture is running or retiring")
            claim = self.controller.claim({key: value for key, value in body.items() if key != "request_id"}, session_binding=session_binding)
            # No handle, title, executable, session cookie, or raw selection
            # token may enter a durable job, audit event, or result.
            payload = {
                "production_id": production_id, "capture_request_id": request_id,
                "duration_ms": duration, "selection_digest": digest,
                "requester_digest": session_binding.upper(), "target": "claude_window",
                "audio_mode": "none", "explicit_capture_confirmation": True,
            }
            return self.jobs.submit(
                "claude_window_capture", payload,
                lambda job_id, cancel_event: self._capture(job_id, production_id, request_id, root, claim, cancel_event),
                production_id=production_id, lane="capture",
            )

    def _capture(self, job_id: str, production_id: str, request_id: str, root: Path, claim: Any, cancel_event: Any) -> dict[str, Any]:
        committed = False
        try:
            cancel_event.raise_if_cancelled()
            self.database.update_job_progress(job_id, 5, "recording")
            raw = self.controller.capture(claim, capture_root=root, cancel_event=cancel_event)
            cancel_event.raise_if_cancelled()
            self.database.update_job_progress(job_id, 90, "verifying")
            if (not isinstance(raw, dict) or raw.get("audio_mode") != "none"
                    or raw.get("actual_capture_performed") is not True
                    or raw.get("structural_video_verified") is not True
                    or raw.get("full_decode_verified") is not True
                    or raw.get("audio_streams") != 0
                    or isinstance(raw.get("duration_ms"), bool)
                    or not isinstance(raw.get("duration_ms"), int)
                    or not claim.duration_ms <= raw["duration_ms"] < claim.duration_ms + 1000 / 24):
                raise ValueError("Claude capture returned invalid media evidence")
            records = self._records(root, raw.get("artifacts"))
            public = {
                "schema_version": 1, "provider": "local_claude_window_capture",
                "production_id": production_id, "capture_request_id": request_id,
                "duration_ms": raw["duration_ms"], "requested_duration_ms": claim.duration_ms, "audio_mode": "none",
                "actual_capture_performed": True, "capture_only": True,
                "content_review_required": True, "content_quality_verified": False,
                "public_release_ready": False, "actual_cost": 0,
                "frame_rate": 24,
            }
            cancel_event.raise_if_cancelled()
            result = self.database.complete_claude_capture_job(job_id, production_id, public, records)
            committed = True
            return result
        finally:
            if not committed:
                # A completion response may fail after SQLite has committed.
                # Never delete source files already registered by durable success.
                try:
                    current = self.database.get_job(job_id)
                except Exception:
                    current = None
                if current is None:
                    raise ClaudeCaptureError(
                        "Capture completion could not be checked; private media was retained for recovery.",
                        code="claude_capture_cleanup_failed",
                    ) from None
                if current.get("status") != "succeeded":
                    try:
                        cleanup_capture_root(root, workspace=self.workspace)
                    except Exception:
                        raise ClaudeCaptureError(
                            "Capture cleanup failed. Private media may remain; another recording is blocked until cleanup succeeds.",
                            code="claude_capture_cleanup_failed",
                        ) from None

    def _records(self, root: Path, artifacts: Any) -> list[dict[str, Any]]:
        if not isinstance(artifacts, list) or len(artifacts) != len(SPECS):
            raise ValueError("Claude capture artifact set is invalid")
        records, seen = [], set()
        for item in artifacts:
            if not isinstance(item, dict):
                raise ValueError("Claude capture artifact is invalid")
            name = item.get("name") or Path(str(item.get("path", item.get("rel_path", "")))).name
            if name not in SPECS or name in seen:
                raise ValueError("Claude capture artifact name is invalid")
            seen.add(name)
            path = workspace_path(self.workspace, item.get("rel_path", item.get("path", "")))
            expected = root / name
            if path != expected or not path.is_file() or path.is_symlink():
                raise ValueError("Claude capture artifact escaped its request directory")
            info = path.stat()
            if info.st_size <= 0 or info.st_size > 512 * 1024 * 1024:
                raise ValueError("Claude capture artifact size is invalid")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
            if item.get("bytes") != info.st_size or item.get("sha256") != digest:
                raise ValueError("Claude capture artifact changed")
            relative = path.relative_to(self.workspace).as_posix()
            kind, media_type = SPECS[name]
            records.append({
                "id": stable_id("art", relative.casefold()), "rel_path": relative,
                "name": name, "kind": kind, "media_type": media_type,
                "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                "sha256": digest, "is_heavy": info.st_size > 10 * 1024 * 1024,
            })
        return records
