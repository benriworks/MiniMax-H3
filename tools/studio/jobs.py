from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import queue
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .database import StudioDatabase
from .security import (
    UnsafeTextArtifactError,
    canonical_json,
    redact_artifact_text,
    sensitive_artifact_path,
    stable_id,
    unsafe_structured_text_suffix,
    validate_identifier,
    workspace_path,
)


JobCallable = Callable[[str], dict[str, Any]]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


class JobManager:
    def __init__(self, database: StudioDatabase):
        self.database = database
        self._queue: queue.Queue[tuple[str, JobCallable] | None] = queue.Queue()
        self._finished: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, name="studio-job-worker", daemon=True)
        self._thread.start()

    def submit(
        self,
        kind: str,
        payload: Any,
        callback: JobCallable,
        *,
        production_id: str | None = None,
        before_enqueue: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        job = self.database.create_job(kind, payload, production_id=production_id)
        with self._lock:
            self._finished[job["id"]] = threading.Event()
        try:
            if before_enqueue is not None:
                before_enqueue(job)
        except Exception:
            # Persist setup failure and never expose an unlinked queued worker.
            # The caller remains responsible for failing its stage attempt.
            try:
                self.database.update_job(
                    job["id"],
                    "failed",
                    error_code="job_setup_failed",
                    error_message="The background job could not be prepared.",
                )
            except Exception:
                pass
            with self._lock:
                event = self._finished.get(job["id"])
                if event:
                    event.set()
            raise
        self._queue.put((job["id"], callback))
        return job

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            job_id, callback = item
            try:
                self.database.update_job(job_id, "running")
                result = callback(job_id)
                self.database.update_job(job_id, "succeeded", result=result)
            except Exception as exc:  # The worker boundary must keep later jobs alive.
                code = getattr(exc, "error_code", "job_failed")
                # Do not persist repr/traceback/request values; only a bounded,
                # redacted public description from explicitly safe exceptions.
                public_message = getattr(exc, "public_message", "The background job failed.")
                try:
                    self.database.update_job(
                        job_id,
                        "failed",
                        error_code=str(code)[:128],
                        error_message=str(public_message)[:1000],
                    )
                except Exception:
                    pass
            finally:
                with self._lock:
                    event = self._finished.get(job_id)
                    if event:
                        event.set()
                self._queue.task_done()

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        with self._lock:
            event = self._finished.get(job_id)
        if event:
            event.wait(timeout)
        return self.database.get_job(job_id)

    def shutdown(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        self._thread.join(timeout)


class AuditExportError(RuntimeError):
    error_code = "audit_export_failed"
    public_message = "The audit package could not be created."


class AuditExporter:
    def __init__(self, workspace: Path, database: StudioDatabase):
        self.workspace = workspace.resolve(strict=True)
        self.database = database
        self.audit_root = workspace_path(self.workspace, "outputs/studio/audits")

    @staticmethod
    def _allowed_sidecar(artifact: dict[str, Any], include_media: bool) -> bool:
        if artifact["kind"] in {"video", "audio", "image"}:
            return include_media
        return artifact["kind"] in {"document", "log", "subtitle"}

    @staticmethod
    def _sensitive_path(relative: str) -> bool:
        return sensitive_artifact_path(relative)

    def export(self, production_id: str, job_id: str, *, include_media: bool) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        validate_identifier(job_id, label="job id")
        snapshot = self.database.production_audit_snapshot(production_id)
        if snapshot is None:
            raise AuditExportError()
        destination_directory = workspace_path(self.workspace, self.audit_root / production_id)
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = workspace_path(self.workspace, destination_directory / f"{job_id}.zip")
        temporary = workspace_path(self.workspace, destination.with_suffix(".zip.partial"))
        sidecar = workspace_path(self.workspace, destination.with_suffix(".zip.sha256"))
        sidecar_temporary = workspace_path(
            self.workspace, destination.with_suffix(".zip.sha256.partial")
        )
        included: list[str] = []
        skipped: list[dict[str, str]] = []
        redacted: list[str] = []
        archive_entries: list[dict[str, object]] = []
        skipped_event_mirrors: list[dict[str, str]] = []
        event_chain_tails: dict[str, str] = {}
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                def add_bytes(archive_name: str, data: bytes) -> None:
                    archive.writestr(archive_name, data)
                    archive_entries.append(
                        {
                            "path": archive_name,
                            "bytes": len(data),
                            "sha256": _sha256_bytes(data),
                        }
                    )

                def add_file(archive_name: str, source: Path) -> None:
                    digest = hashlib.sha256()
                    written = 0
                    with source.open("rb") as input_handle, archive.open(
                        archive_name, "w", force_zip64=True
                    ) as output_handle:
                        while chunk := input_handle.read(1024 * 1024):
                            output_handle.write(chunk)
                            digest.update(chunk)
                            written += len(chunk)
                    archive_entries.append(
                        {
                            "path": archive_name,
                            "bytes": written,
                            "sha256": digest.hexdigest().upper(),
                        }
                    )

                production_json = canonical_json(snapshot) + "\n"
                add_bytes("audit/production-snapshot.json", production_json.encode("utf-8"))
                event_lines = "".join(
                    canonical_json(event) + "\n" for event in snapshot.get("events", [])
                )
                add_bytes("audit/events.jsonl", event_lines.encode("utf-8"))
                mirrored_scopes = sorted(
                    {
                        (event["scope_type"], event["scope_id"])
                        for event in snapshot.get("events", [])
                    }
                )
                for scope_type, scope_id in mirrored_scopes:
                    scope_events = [
                        event
                        for event in snapshot.get("events", [])
                        if event["scope_type"] == scope_type and event["scope_id"] == scope_id
                    ]
                    if scope_events:
                        event_chain_tails[f"{scope_type}:{scope_id}"] = scope_events[-1][
                            "event_hash"
                        ]
                    try:
                        mirror_bytes = self.database.verified_event_mirror_bytes(
                            scope_type, scope_id, scope_events
                        )
                        if mirror_bytes is not None:
                            add_bytes(
                                f"studio-events/{scope_type}/{scope_id}.jsonl",
                                mirror_bytes,
                            )
                        else:
                            skipped_event_mirrors.append(
                                {
                                    "scope": f"{scope_type}:{scope_id}",
                                    "reason": "missing_or_failed_verification",
                                }
                            )
                    except (OSError, ValueError):
                        skipped_event_mirrors.append(
                            {
                                "scope": f"{scope_type}:{scope_id}",
                                "reason": "unavailable",
                            }
                        )
                for artifact in snapshot.get("artifacts", []):
                    relative = artifact["rel_path"]
                    if not self._allowed_sidecar(artifact, include_media):
                        reason = (
                            "media_not_requested"
                            if artifact["kind"] in {"video", "audio", "image"}
                            and not include_media
                            else "unsupported_artifact_kind"
                        )
                        skipped.append({"path": relative, "reason": reason})
                        continue
                    if self._sensitive_path(relative):
                        skipped.append({"path": relative, "reason": "sensitive_path"})
                        continue
                    try:
                        source = workspace_path(self.workspace, relative, must_exist=True)
                        if not source.is_file() or source.is_symlink():
                            raise OSError("not a regular file")
                        if unsafe_structured_text_suffix(source.suffix):
                            skipped.append(
                                {
                                    "path": relative,
                                    "reason": "structured_text_requires_local_review",
                                }
                            )
                            continue
                        archive_name = f"workspace/{relative}"
                        if artifact["kind"] in {"document", "log", "subtitle"}:
                            if source.stat().st_size > 16 * 1024 * 1024:
                                skipped.append({"path": relative, "reason": "text_sidecar_too_large"})
                                continue
                            original = source.read_text(encoding="utf-8-sig", errors="replace")
                            try:
                                safe_text = redact_artifact_text(original, suffix=source.suffix)
                            except UnsafeTextArtifactError:
                                skipped.append(
                                    {
                                        "path": relative,
                                        "reason": "structured_text_requires_local_review",
                                    }
                                )
                                continue
                            add_bytes(archive_name, safe_text.encode("utf-8"))
                            if safe_text != original:
                                redacted.append(relative)
                        else:
                            add_file(archive_name, source)
                        included.append(relative)
                    except (OSError, ValueError):
                        skipped.append({"path": relative, "reason": "unavailable"})
                package_manifest = {
                    "production_id": production_id,
                    "job_id": job_id,
                    "include_media": include_media,
                    "included": included,
                    "skipped": skipped,
                    "redacted_text_files": redacted,
                    "event_chain_tails": event_chain_tails,
                    "skipped_event_mirrors": skipped_event_mirrors,
                    "archive_entries": archive_entries,
                }
                archive.writestr(
                    "audit/package-manifest.json",
                    (canonical_json(package_manifest) + "\n").encode("utf-8"),
                )
            with zipfile.ZipFile(temporary, "r") as verification_archive:
                expected_names = {
                    entry["path"] for entry in archive_entries
                } | {"audit/package-manifest.json"}
                actual_names = {entry.filename for entry in verification_archive.infolist()}
                if actual_names != expected_names:
                    raise ValueError("audit archive entry set changed during export")
                stored_manifest = json.loads(
                    verification_archive.read("audit/package-manifest.json")
                )
                if stored_manifest.get("archive_entries") != archive_entries:
                    raise ValueError("audit package manifest does not match written entries")
                for expected in archive_entries:
                    digest = hashlib.sha256()
                    counted = 0
                    with verification_archive.open(str(expected["path"]), "r") as handle:
                        while chunk := handle.read(1024 * 1024):
                            digest.update(chunk)
                            counted += len(chunk)
                    if counted != expected["bytes"] or digest.hexdigest().upper() != expected["sha256"]:
                        raise ValueError("audit archive entry failed post-write verification")
            os.replace(temporary, destination)
        except Exception as exc:
            try:
                temporary.unlink(missing_ok=True)
                sidecar_temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AuditExportError() from exc

        try:
            digest_hex = _sha256_file(destination)
            sidecar_temporary.write_text(
                f"{digest_hex} *{destination.name}\n", encoding="ascii", newline="\n"
            )
            os.replace(sidecar_temporary, sidecar)
        except OSError as exc:
            sidecar_temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise AuditExportError() from exc
        stat = destination.stat()
        relative = destination.relative_to(self.workspace).as_posix()
        artifact = self.database.register_studio_artifact(
            production_id,
            {
                "id": stable_id("art", relative.casefold()),
                "rel_path": relative,
                "name": destination.name,
                "kind": "audit",
                "media_type": mimetypes.guess_type(destination.name)[0] or "application/zip",
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": digest_hex,
                "is_heavy": stat.st_size > 10 * 1024 * 1024,
            },
        )
        return {
            "artifact": artifact,
            "sha256_sidecar": sidecar.relative_to(self.workspace).as_posix(),
            "files_included": len(included),
            "files_skipped": len(skipped),
            "include_media": include_media,
        }
