from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .security import (
    canonical_json,
    sanitize_for_storage,
    sensitive_artifact_path,
    stable_id,
    validate_identifier,
    workspace_path,
)


SCHEMA_VERSION = 9
MAX_EVENT_LINE_BYTES = 2 * 1024 * 1024
MAX_ANNOUNCEMENT_RECIPE_BYTES = 256 * 1024
_RUN_EXECUTION_PROFILES = {
    "external",
    "local_sapi",
    "elevenlabs_tts",
    "local_comfyui",
    "local_playwright",
    "local_windows_capture",
    "local_pipeline",
}
_LOCAL_SAPI_ZERO_COST_STAGES = {
    "narration",
    "captions",
    "timeline",
    "assembly",
    "qc",
}
_ELEVENLABS_TTS_STAGES = {"narration", "captions", "assembly", "qc"}
_LOCAL_COMFYUI_ZERO_COST_STAGES = {"video_generation", "timeline", "assembly", "qc"}
_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES = {"screen_capture", "timeline", "assembly", "qc"}
_LOCAL_PLAYWRIGHT_EXECUTION_STAGES = {"screen_capture", "timeline"}
_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES = {
    "screen_capture",
    "timeline",
    "assembly",
    "qc",
}
_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES = {"screen_capture", "timeline"}
_LOCAL_PIPELINE_ZERO_COST_STAGES = {
    "narration",
    "captions",
    "video_generation",
    "timeline",
    "assembly",
    "qc",
}
_DEFAULT_INTERRUPTED_ERROR_CODE = "process_interrupted"
_DEFAULT_INTERRUPTED_ERROR_MESSAGE = "The Studio process stopped."
_MAX_RESTORED_STUDIO_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_RESTORED_STUDIO_ARTIFACT_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
_MAX_RESTORED_STUDIO_ARTIFACT_COUNT = 10_000
_PROVIDER_TASK_STATUSES = {
    "prepared",
    "submitted",
    "recovering",
    "succeeded",
    "failed",
    "ambiguous",
    "recovery_blocked",
    "cancel_requested",
}
_PROVIDER_TASK_TERMINAL_STATUSES = {"succeeded", "failed"}
_PROVIDER_TASK_DEFINITE_FAILURE_CODES = {
    "comfyui_generation_failed",
    "comfyui_request_rejected",
}
_PROVIDER_TASK_RECOVERABLE_STATUSES = {
    "prepared",
    "submitted",
    "ambiguous",
    "recovery_blocked",
    "cancel_requested",
}
_PROVIDER_TASK_NEXT_ACTION = {
    "prepared": "submit",
    "submitted": "resume",
    "recovering": "wait",
    "succeeded": "none",
    "failed": "retry",
    "ambiguous": "reconcile",
    "recovery_blocked": "retry_with_matching_request",
    "cancel_requested": "confirm_cancellation",
}
_PROVIDER_TASK_STATE_TRANSITIONS = {
    "prepared": {"ambiguous", "recovery_blocked", "cancel_requested", "failed"},
    "submitted": {
        "recovering",
        "ambiguous",
        "recovery_blocked",
        "cancel_requested",
        "failed",
    },
    "recovering": {"ambiguous", "recovery_blocked", "cancel_requested", "failed"},
    "ambiguous": {"recovery_blocked", "cancel_requested", "failed"},
    "recovery_blocked": {"ambiguous", "cancel_requested", "failed"},
    "cancel_requested": {"ambiguous", "recovery_blocked", "failed"},
    "succeeded": set(),
    "failed": set(),
}
_MAX_PROVIDER_REQUEST_CIPHERTEXT_BYTES = 2 * 1024 * 1024
_MAX_PIPELINE_REQUEST_CIPHERTEXT_BYTES = 2 * 1024 * 1024
_LOCAL_PIPELINE_CONTINUATION_STATES = {
    "unavailable",
    "active",
    "waiting_provider",
    "ready",
    "continuing",
    "succeeded",
    "recovery_blocked",
    "cancel_requested",
    "cancelled",
}
_LOCAL_PIPELINE_CONTINUATION_NEXT_ACTION = {
    "unavailable": "resubmit",
    "active": "wait",
    "waiting_provider": "wait_provider",
    "ready": "continue",
    "continuing": "wait",
    "succeeded": "none",
    "recovery_blocked": "retry",
    "cancel_requested": "confirm_cancellation",
    "cancelled": "none",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _has_symlink_component(workspace: Path, relative_path: str) -> bool:
    root = workspace.resolve(strict=True)
    lexical = root / Path(relative_path)
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return canonical_json(sanitize_for_storage(value))


def _loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def money_to_minor(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("amount must be a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a number") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000"):
        raise ValueError("amount is outside the accepted range")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money_from_minor(minor: int, currency: str) -> dict[str, object]:
    return {"amount": f"{Decimal(minor) / Decimal(100):.2f}", "currency": currency}


@dataclass(frozen=True)
class AtomicStageCompletion:
    """Internal worker-to-job-manager completion envelope.

    ``public_result`` is the stage result that must be persisted on the
    attempt.  The database derives the historical job result by adding
    ``stage_attempt_id`` to that mapping.  Optional ``artifact_records`` are
    registered in the same transaction as the job/stage success transition.
    ``failure_cleanup`` is an internal, best-effort rollback for newly
    published local files when that transaction does not commit; it is never
    persisted or invoked after a confirmed success.  The envelope itself is
    never persisted as a public job result.
    """

    stage_attempt_id: str
    public_result: dict[str, Any]
    artifact_records: tuple[dict[str, Any], ...] = ()
    provider_task_record_id: str | None = None
    failure_cleanup: Callable[[], None] | None = None


class AtomicCompletionError(ValueError):
    """A strict job/stage completion was rejected without committing it."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "atomic_completion_rejected",
        job_status: str | None = None,
        stage_status: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.committed = False
        self.job_status = job_status
        self.stage_status = stage_status


class WindowsCaptureConsentError(ValueError):
    """A Windows capture consent could not be admitted safely."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


class StudioDatabase:
    def __init__(self, path: Path, *, workspace: Path | None = None):
        self.path = path.resolve()
        self.workspace = (workspace or self.path.parent).resolve(strict=True)
        workspace_path(self.workspace, self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events_root = workspace_path(self.workspace, self.path.parent / "events")
        self._mirror_lock = threading.Lock()
        self._mirror_health_lock = threading.Lock()
        self._mirror_issues: dict[str, dict[str, str]] = {}
        self.initialize()
        self.restore_events_from_mirror()
        self.interrupt_active_work()
        self.sync_event_mirror()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def read_snapshot(self) -> Iterator[sqlite3.Connection]:
        """Hold one WAL read snapshot across every query used by an audit export."""
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
            committed = True
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        if committed:
            try:
                self.sync_event_mirror()
            except (OSError, UnicodeError, ValueError, sqlite3.Error, json.JSONDecodeError):
                # SQLite retains the event; expose the degraded audit mirror in
                # health until a later successful sync catches it up.
                self._record_mirror_issue(
                    "studio", "event_mirror", "mirror_sync_unavailable"
                )

    def event_mirror_path(self, scope_type: str, scope_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", scope_type):
            raise ValueError("invalid event scope type")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", scope_id):
            raise ValueError("invalid event scope id")
        root = workspace_path(self.workspace, self.events_root)
        candidate = workspace_path(self.workspace, root / scope_type / f"{scope_id}.jsonl")
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("event mirror path is outside the studio directory") from exc
        return candidate

    @staticmethod
    def _last_mirrored_event(path: Path) -> tuple[int, str] | None:
        if not path.is_file():
            return None
        last: str | None = None
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last = line
        if last is None:
            return None
        value = json.loads(last)
        event_id = value.get("id")
        event_hash = value.get("event_hash")
        if (
            not isinstance(event_id, int)
            or event_id < 1
            or not isinstance(event_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", event_hash)
        ):
            raise ValueError("event mirror has an invalid tail")
        return event_id, event_hash

    @staticmethod
    def _verified_mirror_events(
        path: Path, *, scope_type: str, scope_id: str
    ) -> list[dict[str, Any]]:
        if path.is_symlink() or not path.is_file():
            raise ValueError("event mirror is not a regular file")
        verified: list[dict[str, Any]] = []
        previous_hash = "0" * 64
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if len(line.encode("utf-8")) > MAX_EVENT_LINE_BYTES:
                    raise ValueError("event line is too large")
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("event must be an object")
                if event.get("scope_type") != scope_type or event.get("scope_id") != scope_id:
                    raise ValueError("event scope does not match mirror path")
                if event.get("previous_hash") != previous_hash:
                    raise ValueError("event chain is not contiguous")
                event_id = event.get("id")
                if not isinstance(event_id, int) or event_id < 1:
                    raise ValueError("event id is invalid")
                payload = event.get("payload", {})
                digest_source = canonical_json(
                    {
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "event_type": event.get("event_type"),
                        "created_at": event.get("created_at"),
                        "payload": payload,
                        "previous_hash": previous_hash,
                    }
                )
                expected = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
                if event.get("event_hash") != expected:
                    raise ValueError("event hash is invalid")
                verified.append(event)
                previous_hash = expected
        return verified

    @staticmethod
    def _mirror_issue_key(scope_type: str, scope_id: str) -> str:
        return f"{scope_type}:{scope_id}"

    def _record_mirror_issue(self, scope_type: str, scope_id: str, code: str) -> None:
        key = self._mirror_issue_key(scope_type, scope_id)
        with self._mirror_health_lock:
            self._mirror_issues[key] = {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "code": code,
                "detected_at": utc_now(),
            }

    def _clear_mirror_issue(self, scope_type: str, scope_id: str) -> None:
        key = self._mirror_issue_key(scope_type, scope_id)
        with self._mirror_health_lock:
            self._mirror_issues.pop(key, None)

    def event_mirror_health(self) -> dict[str, Any]:
        with self._mirror_health_lock:
            issues = [dict(value) for _, value in sorted(self._mirror_issues.items())]
        return {"ok": not issues, "issue_count": len(issues), "issues": issues}

    def verified_event_mirror_path(self, scope_type: str, scope_id: str) -> Path | None:
        path = self.event_mirror_path(scope_type, scope_id)
        if not path.exists():
            return None
        try:
            self._verified_mirror_events(path, scope_type=scope_type, scope_id=scope_id)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            self._record_mirror_issue(scope_type, scope_id, "mirror_verification_failed")
            return None
        return path

    def verified_event_mirror_bytes(
        self,
        scope_type: str,
        scope_id: str,
        expected_events: Sequence[dict[str, Any]],
    ) -> bytes | None:
        """Return a verified, immutable prefix matching one database read snapshot."""
        with self._mirror_lock:
            path = self.event_mirror_path(scope_type, scope_id)
            if not path.exists():
                return None
            try:
                verified = self._verified_mirror_events(
                    path, scope_type=scope_type, scope_id=scope_id
                )
                expected = [dict(event) for event in expected_events]
                def chain_value(event: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "scope_type": event.get("scope_type"),
                        "scope_id": event.get("scope_id"),
                        "event_type": event.get("event_type"),
                        "created_at": event.get("created_at"),
                        "payload": event.get("payload", {}),
                        "previous_hash": event.get("previous_hash"),
                        "event_hash": event.get("event_hash"),
                    }
                if len(verified) < len(expected) or any(
                    canonical_json(chain_value(actual))
                    != canonical_json(chain_value(snapshot_event))
                    for actual, snapshot_event in zip(verified, expected, strict=False)
                ):
                    raise ValueError("event mirror does not contain the database snapshot prefix")
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                self._record_mirror_issue(scope_type, scope_id, "mirror_snapshot_mismatch")
                return None
            self._clear_mirror_issue(scope_type, scope_id)
            return "".join(
                canonical_json(event) + "\n" for event in verified[: len(expected)]
            ).encode("utf-8")

    def sync_event_mirror(self) -> None:
        with self._mirror_lock:
            self.events_root.mkdir(parents=True, exist_ok=True)
            with self.session() as connection:
                scopes = connection.execute(
                    "SELECT DISTINCT scope_type, scope_id FROM events ORDER BY scope_type, scope_id"
                ).fetchall()
                for scope in scopes:
                    scope_type = scope["scope_type"]
                    scope_id = scope["scope_id"]
                    try:
                        path = self.event_mirror_path(scope_type, scope_id)
                        if path.exists():
                            verified = self._verified_mirror_events(
                                path, scope_type=scope_type, scope_id=scope_id
                            )
                        else:
                            verified = []
                        if not verified:
                            last_id = 0
                        else:
                            restored_tail = connection.execute(
                                "SELECT id FROM events WHERE scope_type=? AND scope_id=? AND event_hash=?",
                                (scope_type, scope_id, verified[-1]["event_hash"]),
                            ).fetchone()
                            if not restored_tail:
                                raise ValueError("event mirror tail is absent from SQLite")
                            last_id = restored_tail["id"]
                        rows = connection.execute(
                            "SELECT * FROM events WHERE scope_type=? AND scope_id=? AND id>? ORDER BY id",
                            (scope_type, scope_id, last_id),
                        ).fetchall()
                        if rows:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            with path.open("a", encoding="utf-8", newline="\n") as handle:
                                for row in rows:
                                    handle.write(canonical_json(self._event_dict(row)) + "\n")
                                handle.flush()
                                os.fsync(handle.fileno())
                        self._clear_mirror_issue(scope_type, scope_id)
                    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                        self._record_mirror_issue(
                            scope_type, scope_id, "mirror_sync_failed"
                        )
                self._clear_mirror_issue("studio", "event_mirror")

    def restore_events_from_mirror(self) -> int:
        """Restore verified append-only events when the SQLite index is rebuilt."""
        if not self.events_root.is_dir() or self.events_root.is_symlink():
            return 0
        verified: list[dict[str, Any]] = []
        for scope_directory in sorted(self.events_root.iterdir()):
            if not scope_directory.is_dir() or scope_directory.is_symlink():
                continue
            scope_type = scope_directory.name
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", scope_type):
                continue
            for path in sorted(scope_directory.glob("*.jsonl")):
                if path.is_symlink() or not path.is_file():
                    continue
                scope_id = path.stem
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", scope_id):
                    continue
                try:
                    scope_events = self._verified_mirror_events(
                        path, scope_type=scope_type, scope_id=scope_id
                    )
                    for event in scope_events:
                        verified.append(
                            {
                                "scope_type": scope_type,
                                "scope_id": scope_id,
                                "event_type": str(event.get("event_type")),
                                "created_at": str(event.get("created_at")),
                                "payload_json": canonical_json(event.get("payload", {})),
                                "previous_hash": str(event["previous_hash"]),
                                "event_hash": str(event["event_hash"]),
                            }
                        )
                    self._clear_mirror_issue(scope_type, scope_id)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                    # A damaged mirror is never partially trusted.
                    verified = [
                        event
                        for event in verified
                        if not (
                            event["scope_type"] == scope_type and event["scope_id"] == scope_id
                        )
                    ]
                    self._record_mirror_issue(
                        scope_type, scope_id, "mirror_restore_verification_failed"
                    )
                    continue
        inserted = 0
        if not verified:
            return inserted
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for event in verified:
                existing = connection.execute(
                    "SELECT 1 FROM events WHERE event_hash=?", (event["event_hash"],)
                ).fetchone()
                if existing:
                    continue
                connection.execute(
                    "INSERT INTO events(scope_type, scope_id, event_type, created_at, payload_json, previous_hash, event_hash) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        event["scope_type"],
                        event["scope_id"],
                        event["event_type"],
                        event["created_at"],
                        event["payload_json"],
                        event["previous_hash"],
                        event["event_hash"],
                    ),
                )
                inserted += 1
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return inserted

    def initialize(self) -> None:
        with self.session() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            version_row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            if version_row is not None:
                try:
                    current_version = int(version_row["value"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("Studio database schema version is invalid") from exc
                if current_version > SCHEMA_VERSION:
                    raise ValueError("Studio database schema is newer than this application")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS productions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    technical_status TEXT,
                    creative_status TEXT,
                    public_release_status TEXT,
                    source_rel TEXT,
                    output_rel TEXT,
                    discovered_at TEXT NOT NULL,
                    refreshed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    production_id TEXT NOT NULL REFERENCES productions(id),
                    rel_path TEXT NOT NULL UNIQUE,
                    origin TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL CHECK(bytes >= 0),
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT,
                    is_heavy INTEGER NOT NULL CHECK(is_heavy IN (0, 1)),
                    available INTEGER NOT NULL CHECK(available IN (0, 1)),
                    indexed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_production_idx
                    ON artifacts(production_id, available, kind, rel_path);

                CREATE TABLE IF NOT EXISTS artifact_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    observed_at TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT,
                    UNIQUE(artifact_id, bytes, mtime_ns, sha256)
                );

                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY,
                    production_id TEXT NOT NULL REFERENCES productions(id),
                    parent_revision_id TEXT REFERENCES revisions(id),
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    changes_json TEXT NOT NULL,
                    rerun_plan_json TEXT NOT NULL,
                    immutable_digest TEXT NOT NULL,
                    UNIQUE(production_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    production_id TEXT NOT NULL REFERENCES productions(id),
                    revision_id TEXT NOT NULL REFERENCES revisions(id),
                    created_at TEXT NOT NULL,
                    requested_stages_json TEXT NOT NULL,
                    estimated_cost_minor INTEGER NOT NULL CHECK(estimated_cost_minor >= 0),
                    currency TEXT NOT NULL,
                    execution_profile TEXT NOT NULL DEFAULT 'external',
                    pipeline_key TEXT,
                    immutable_digest TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS local_pipeline_claims (
                    production_id TEXT NOT NULL REFERENCES productions(id),
                    pipeline_key TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
                    revision_id TEXT NOT NULL REFERENCES revisions(id),
                    active_job_id TEXT REFERENCES jobs(id),
                    state TEXT NOT NULL CHECK(state IN (
                        'unavailable', 'active', 'waiting_provider', 'ready',
                        'continuing', 'succeeded', 'recovery_blocked',
                        'cancel_requested', 'cancelled'
                    )),
                    request_protection TEXT NOT NULL CHECK(
                        request_protection IN ('dpapi-v1', 'none')
                    ),
                    request_ciphertext BLOB,
                    continuation_job_id TEXT REFERENCES jobs(id),
                    source_job_id TEXT REFERENCES jobs(id),
                    source_stage_attempt_id TEXT REFERENCES stage_attempts(id),
                    resume_count INTEGER NOT NULL CHECK(resume_count >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    CHECK(
                        (source_job_id IS NULL AND source_stage_attempt_id IS NULL)
                        OR
                        (source_job_id IS NOT NULL AND source_stage_attempt_id IS NOT NULL)
                    ),
                    CHECK(
                        continuation_job_id IS NULL
                        OR active_job_id=continuation_job_id
                    ),
                    CHECK(
                        (request_protection='none' AND request_ciphertext IS NULL)
                        OR
                        (request_protection='dpapi-v1'
                         AND typeof(request_ciphertext)='blob'
                         AND length(request_ciphertext) BETWEEN 1 AND 2097152)
                    ),
                    PRIMARY KEY(production_id, pipeline_key)
                );

                CREATE TABLE IF NOT EXISTS run_approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
                    approved_max_minor INTEGER NOT NULL CHECK(approved_max_minor >= 0),
                    currency TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS run_approvals_run_idx
                    ON run_approvals(run_id, created_at);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS events_scope_idx
                    ON events(scope_type, scope_id, id);

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
                    production_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created_at DESC);

                CREATE TABLE IF NOT EXISTS stage_attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    production_id TEXT NOT NULL REFERENCES productions(id),
                    job_id TEXT,
                    stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL CHECK(attempt >= 1),
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'succeeded', 'failed')),
                    cache_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    UNIQUE(run_id, stage, attempt)
                );
                CREATE INDEX IF NOT EXISTS stage_attempts_run_idx
                    ON stage_attempts(run_id, stage, attempt);
                CREATE INDEX IF NOT EXISTS stage_attempts_cache_idx
                    ON stage_attempts(stage, cache_key, status, completed_at);

                CREATE TRIGGER IF NOT EXISTS revisions_immutable_update
                    BEFORE UPDATE ON revisions BEGIN
                        SELECT RAISE(ABORT, 'revisions are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS revisions_immutable_delete
                    BEFORE DELETE ON revisions BEGIN
                        SELECT RAISE(ABORT, 'revisions are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS runs_immutable_update
                    BEFORE UPDATE ON runs BEGIN
                        SELECT RAISE(ABORT, 'runs are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS runs_immutable_delete
                    BEFORE DELETE ON runs BEGIN
                        SELECT RAISE(ABORT, 'runs are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS approvals_immutable_update
                    BEFORE UPDATE ON run_approvals BEGIN
                        SELECT RAISE(ABORT, 'approvals are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS approvals_immutable_delete
                    BEFORE DELETE ON run_approvals BEGIN
                        SELECT RAISE(ABORT, 'approvals are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS events_immutable_update
                    BEFORE UPDATE ON events BEGIN
                        SELECT RAISE(ABORT, 'events are append-only');
                    END;
                CREATE TRIGGER IF NOT EXISTS events_immutable_delete
                    BEFORE DELETE ON events BEGIN
                        SELECT RAISE(ABORT, 'events are append-only');
                    END;
                CREATE TRIGGER IF NOT EXISTS stage_attempts_immutable_delete
                    BEFORE DELETE ON stage_attempts BEGIN
                        SELECT RAISE(ABORT, 'stage attempts are append-only');
                    END;
                """
            )
            # SQLite's CREATE TABLE IF NOT EXISTS does not add columns to an
            # existing database. Keep every incremental change and the schema
            # version write in one transaction so a failed migration is
            # retried instead of being advertised as complete.
            connection.execute("BEGIN IMMEDIATE")
            try:
                run_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(runs)").fetchall()
                }
                if "execution_profile" not in run_columns:
                    connection.execute(
                        "ALTER TABLE runs ADD COLUMN execution_profile TEXT NOT NULL DEFAULT 'external'"
                    )
                if "pipeline_key" not in run_columns:
                    connection.execute("ALTER TABLE runs ADD COLUMN pipeline_key TEXT")
                pipeline_claim_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(local_pipeline_claims)"
                    ).fetchall()
                }
                if "active_job_id" not in pipeline_claim_columns:
                    connection.execute(
                        "ALTER TABLE local_pipeline_claims ADD COLUMN active_job_id TEXT REFERENCES jobs(id)"
                    )
                attempt_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(stage_attempts)").fetchall()
                }
                if "job_id" not in attempt_columns:
                    connection.execute("ALTER TABLE stage_attempts ADD COLUMN job_id TEXT")

                # v6 turns the immutable run claim into a durable continuation
                # ledger. Rebuild instead of a series of ALTERs so migrated
                # rows receive the same CHECK and FK invariants as fresh DBs.
                pipeline_claim_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(local_pipeline_claims)"
                    ).fetchall()
                }
                pipeline_v6_columns = {
                    "state",
                    "request_protection",
                    "request_ciphertext",
                    "continuation_job_id",
                    "source_job_id",
                    "source_stage_attempt_id",
                    "resume_count",
                    "updated_at",
                    "error_code",
                    "error_message",
                }
                if not pipeline_v6_columns.issubset(pipeline_claim_columns):
                    connection.execute(
                        "ALTER TABLE local_pipeline_claims RENAME TO local_pipeline_claims_v5"
                    )
                    connection.execute(
                        """
                        CREATE TABLE local_pipeline_claims (
                            production_id TEXT NOT NULL REFERENCES productions(id),
                            pipeline_key TEXT NOT NULL,
                            run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
                            revision_id TEXT NOT NULL REFERENCES revisions(id),
                            active_job_id TEXT REFERENCES jobs(id),
                            state TEXT NOT NULL CHECK(state IN (
                                'unavailable', 'active', 'waiting_provider', 'ready',
                                'continuing', 'succeeded', 'recovery_blocked',
                                'cancel_requested', 'cancelled'
                            )),
                            request_protection TEXT NOT NULL CHECK(
                                request_protection IN ('dpapi-v1', 'none')
                            ),
                            request_ciphertext BLOB,
                            continuation_job_id TEXT REFERENCES jobs(id),
                            source_job_id TEXT REFERENCES jobs(id),
                            source_stage_attempt_id TEXT REFERENCES stage_attempts(id),
                            resume_count INTEGER NOT NULL CHECK(resume_count >= 0),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            error_code TEXT,
                            error_message TEXT,
                            CHECK(
                                (source_job_id IS NULL AND source_stage_attempt_id IS NULL)
                                OR
                                (source_job_id IS NOT NULL AND source_stage_attempt_id IS NOT NULL)
                            ),
                            CHECK(
                                continuation_job_id IS NULL
                                OR active_job_id=continuation_job_id
                            ),
                            CHECK(
                                (request_protection='none' AND request_ciphertext IS NULL)
                                OR
                                (request_protection='dpapi-v1'
                                 AND typeof(request_ciphertext)='blob'
                                 AND length(request_ciphertext) BETWEEN 1 AND 2097152)
                            ),
                            PRIMARY KEY(production_id, pipeline_key)
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO local_pipeline_claims(
                            production_id, pipeline_key, run_id, revision_id,
                            active_job_id, state, request_protection,
                            request_ciphertext, continuation_job_id,
                            source_job_id, source_stage_attempt_id, resume_count,
                            created_at, updated_at, error_code, error_message
                        )
                        SELECT production_id, pipeline_key, run_id, revision_id,
                               active_job_id, 'unavailable', 'none', NULL, NULL,
                               NULL, NULL, 0, created_at, created_at, NULL, NULL
                        FROM local_pipeline_claims_v5
                        """
                    )
                    connection.execute("DROP TABLE local_pipeline_claims_v5")
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS local_pipeline_claims_active_job_uq "
                    "ON local_pipeline_claims(active_job_id) WHERE active_job_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS local_pipeline_claims_continuation_job_uq "
                    "ON local_pipeline_claims(continuation_job_id) "
                    "WHERE continuation_job_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS local_pipeline_claims_source_attempt_uq "
                    "ON local_pipeline_claims(source_stage_attempt_id) "
                    "WHERE source_stage_attempt_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS local_pipeline_claims_state_idx "
                    "ON local_pipeline_claims(state, updated_at, run_id)"
                )

                # v7 adds a content-addressed claim for the local_sapi detailed
                # test-video top job. The request body itself is intentionally
                # not persisted here; only its canonical digest and immutable
                # run/revision provenance cross this boundary.
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS detailed_test_video_claims (
                        production_id TEXT NOT NULL REFERENCES productions(id),
                        request_key TEXT NOT NULL CHECK(length(request_key)=64),
                        run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
                        revision_id TEXT NOT NULL REFERENCES revisions(id),
                        active_job_id TEXT REFERENCES jobs(id),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(production_id, request_key)
                    )
                    """
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS detailed_test_video_active_job_uq "
                    "ON detailed_test_video_claims(active_job_id) "
                    "WHERE active_job_id IS NOT NULL"
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS provider_tasks (
                        id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL CHECK(provider='comfyui'),
                        production_id TEXT NOT NULL REFERENCES productions(id),
                        run_id TEXT NOT NULL REFERENCES runs(id),
                        stage TEXT NOT NULL CHECK(stage='video_generation'),
                        origin_stage_attempt_id TEXT NOT NULL REFERENCES stage_attempts(id),
                        current_stage_attempt_id TEXT REFERENCES stage_attempts(id),
                        current_job_id TEXT REFERENCES jobs(id),
                        cache_key TEXT NOT NULL CHECK(length(cache_key)=64),
                        payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
                        provider_task_id TEXT CHECK(
                            provider_task_id IS NULL OR length(provider_task_id) BETWEEN 1 AND 128
                        ),
                        status TEXT NOT NULL CHECK(status IN (
                            'prepared', 'submitted', 'recovering', 'succeeded',
                            'failed', 'ambiguous', 'recovery_blocked', 'cancel_requested'
                        )),
                        attempt_sequence INTEGER NOT NULL CHECK(attempt_sequence >= 1),
                        recovery_count INTEGER NOT NULL CHECK(recovery_count >= 0),
                        request_protection TEXT NOT NULL CHECK(
                            request_protection IN ('dpapi-v1', 'none')
                        ),
                        request_ciphertext BLOB,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        submitted_at TEXT,
                        last_observed_at TEXT,
                        completed_at TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        UNIQUE(provider, run_id, cache_key, payload_digest),
                        CHECK(
                            (current_stage_attempt_id IS NULL AND current_job_id IS NULL)
                            OR
                            (current_stage_attempt_id IS NOT NULL AND current_job_id IS NOT NULL)
                        ),
                        CHECK(
                            (request_protection='none' AND request_ciphertext IS NULL)
                            OR
                            (request_protection='dpapi-v1' AND (
                                (status IN ('succeeded', 'failed') AND request_ciphertext IS NULL)
                                OR
                                (typeof(request_ciphertext)='blob'
                                 AND length(request_ciphertext) BETWEEN 1 AND 2097152)
                            ))
                        )
                    )
                    """
                )
                provider_task_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(provider_tasks)"
                    ).fetchall()
                }
                if "last_observed_at" not in provider_task_columns:
                    connection.execute(
                        "ALTER TABLE provider_tasks ADD COLUMN last_observed_at TEXT"
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS local_video_generation_claims (
                        run_id TEXT NOT NULL REFERENCES runs(id),
                        production_id TEXT NOT NULL REFERENCES productions(id),
                        cache_key TEXT NOT NULL CHECK(length(cache_key)=64),
                        payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
                        stage_attempt_id TEXT NOT NULL UNIQUE REFERENCES stage_attempts(id),
                        active_job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(run_id, cache_key, payload_digest)
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS local_video_generation_claims_job_idx "
                    "ON local_video_generation_claims(active_job_id)"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS provider_tasks_external_id_uq "
                    "ON provider_tasks(provider, provider_task_id) "
                    "WHERE provider_task_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS provider_tasks_current_job_uq "
                    "ON provider_tasks(current_job_id) WHERE current_job_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS provider_tasks_current_attempt_uq "
                    "ON provider_tasks(current_stage_attempt_id) "
                    "WHERE current_stage_attempt_id IS NOT NULL"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS provider_tasks_status_idx "
                    "ON provider_tasks(status, updated_at, id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS provider_tasks_run_idx "
                    "ON provider_tasks(run_id, stage, created_at)"
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS provider_tasks_identity_immutable
                    BEFORE UPDATE OF provider, production_id, run_id, stage,
                        cache_key, payload_digest, created_at
                    ON provider_tasks BEGIN
                        SELECT RAISE(ABORT, 'provider task identity is immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS provider_tasks_immutable_delete
                    BEFORE DELETE ON provider_tasks BEGIN
                        SELECT RAISE(ABORT, 'provider tasks are append-only');
                    END
                    """
                )

                # v8 separates a short-lived operator consent from the
                # recording POST. Only a one-way token digest and a one-way
                # authenticated-session binding are stored. Consumption,
                # stage-attempt creation, and job admission are committed in
                # one transaction so a replay can only resolve to that exact
                # job, including after it reaches a terminal state.
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS windows_capture_consent_intents (
                        id TEXT PRIMARY KEY,
                        token_digest TEXT NOT NULL UNIQUE CHECK(length(token_digest)=64),
                        session_binding_digest TEXT NOT NULL CHECK(length(session_binding_digest)=64),
                        run_id TEXT NOT NULL REFERENCES runs(id),
                        production_id TEXT NOT NULL REFERENCES productions(id),
                        request_settings_digest TEXT NOT NULL CHECK(length(request_settings_digest)=64),
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        invalidated_at TEXT,
                        consumed_at TEXT,
                        consumed_job_id TEXT UNIQUE REFERENCES jobs(id),
                        consumed_stage_attempt_id TEXT UNIQUE REFERENCES stage_attempts(id),
                        CHECK(
                            (consumed_at IS NULL AND consumed_job_id IS NULL
                             AND consumed_stage_attempt_id IS NULL)
                            OR
                            (consumed_at IS NOT NULL AND consumed_job_id IS NOT NULL
                             AND consumed_stage_attempt_id IS NOT NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS windows_capture_consent_run_idx "
                    "ON windows_capture_consent_intents(run_id, issued_at)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS windows_capture_consent_expiry_idx "
                    "ON windows_capture_consent_intents(expires_at) "
                    "WHERE consumed_job_id IS NULL AND invalidated_at IS NULL"
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS windows_capture_consent_identity_immutable
                    BEFORE UPDATE OF token_digest, session_binding_digest, run_id,
                        production_id, request_settings_digest, issued_at, expires_at
                    ON windows_capture_consent_intents BEGIN
                        SELECT RAISE(ABORT, 'Windows capture consent identity is immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS windows_capture_consent_immutable_delete
                    BEFORE DELETE ON windows_capture_consent_intents BEGIN
                        SELECT RAISE(ABORT, 'Windows capture consents are append-only');
                    END
                    """
                )

                # v9 adds a non-destructive production library overlay.  The
                # source production, artifacts, revisions, and runs never move
                # or change identity.  Every client-issued mutation identity is
                # recorded once with the append-only audit event that accepted
                # it, making response-loss retries side-effect free.
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS production_library_states (
                        production_id TEXT PRIMARY KEY REFERENCES productions(id),
                        archived INTEGER NOT NULL DEFAULT 0
                            CHECK(archived IN (0, 1)),
                        archived_at TEXT,
                        updated_at TEXT NOT NULL,
                        CHECK(
                            (archived=0 AND archived_at IS NULL)
                            OR (archived=1 AND archived_at IS NOT NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS production_library_states_archived_idx "
                    "ON production_library_states(archived, updated_at, production_id)"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS production_library_operations (
                        operation_id TEXT PRIMARY KEY,
                        production_id TEXT NOT NULL REFERENCES productions(id),
                        action TEXT NOT NULL
                            CHECK(action IN ('rename', 'archive', 'duplicate')),
                        request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
                        event_id INTEGER NOT NULL UNIQUE REFERENCES events(id),
                        result_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS production_library_operations_production_idx "
                    "ON production_library_operations(production_id, created_at, operation_id)"
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS production_library_operations_immutable_update
                    BEFORE UPDATE ON production_library_operations BEGIN
                        SELECT RAISE(ABORT, 'production library operations are immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS production_library_operations_immutable_delete
                    BEFORE DELETE ON production_library_operations BEGIN
                        SELECT RAISE(ABORT, 'production library operations are append-only');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS production_library_states_immutable_delete
                    BEFORE DELETE ON production_library_states BEGIN
                        SELECT RAISE(ABORT, 'production library state cannot be deleted');
                    END
                    """
                )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(SCHEMA_VERSION),),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def interrupt_active_work(self) -> dict[str, int]:
        """Fail closed when a prior Studio process ended during active work."""

        timestamp = utc_now()
        counts = {
            "jobs": 0,
            "stage_attempts": 0,
            "provider_tasks": 0,
            "pipeline_claims": 0,
            "windows_capture_consents": 0,
        }
        with self.transaction() as connection:
            outstanding_consents = connection.execute(
                "SELECT id, run_id, production_id, request_settings_digest, expires_at "
                "FROM windows_capture_consent_intents "
                "WHERE consumed_job_id IS NULL AND invalidated_at IS NULL "
                "ORDER BY issued_at, rowid"
            ).fetchall()
            for consent in outstanding_consents:
                connection.execute(
                    "UPDATE windows_capture_consent_intents SET invalidated_at=? "
                    "WHERE id=? AND consumed_job_id IS NULL AND invalidated_at IS NULL",
                    (timestamp, consent["id"]),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    continue
                counts["windows_capture_consents"] += 1
                self._append_event(
                    connection,
                    "run",
                    consent["run_id"],
                    "windows_capture.consent.invalidated",
                    {
                        "consent_intent_id": consent["id"],
                        "production_id": consent["production_id"],
                        "request_settings_digest": consent[
                            "request_settings_digest"
                        ],
                        "expires_at": consent["expires_at"],
                        "invalidated_at": timestamp,
                        "reason": "process_boundary",
                    },
                    created_at=timestamp,
                )
            active_jobs = connection.execute(
                "SELECT id, kind, production_id FROM jobs "
                "WHERE status IN ('queued', 'running') ORDER BY created_at, rowid"
            ).fetchall()
            # A prior worker may have terminalized its job/stage pair but died
            # before clearing the provider owner.  Recover every nonterminal
            # provider binding, not only bindings whose local rows are still
            # active, so a restart cannot leave that operation permanently
            # hidden from the recovery scan.
            active_provider_tasks = connection.execute(
                "SELECT * FROM provider_tasks "
                "WHERE current_job_id IS NOT NULL "
                "AND current_stage_attempt_id IS NOT NULL "
                "AND status NOT IN ('succeeded', 'failed') "
                "ORDER BY created_at, rowid"
            ).fetchall()
            connection.execute(
                "UPDATE jobs SET status='interrupted', completed_at=?, "
                "error_code='process_interrupted', error_message='The previous Studio process stopped.' "
                "WHERE status IN ('queued', 'running')",
                (timestamp,),
            )
            counts["jobs"] = int(connection.execute("SELECT changes() AS count").fetchone()["count"])
            for job in active_jobs:
                self._append_event(
                    connection,
                    "job",
                    job["id"],
                    "job.interrupted",
                    {
                        "kind": job["kind"],
                        "production_id": job["production_id"],
                        "error_code": "process_interrupted",
                    },
                    created_at=timestamp,
                )
            rows = connection.execute(
                "SELECT * FROM stage_attempts WHERE status IN ('queued', 'running') "
                "ORDER BY created_at, rowid"
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE stage_attempts SET status='failed', completed_at=?, result_json=NULL, "
                    "error_code='process_interrupted', error_message='The previous Studio process stopped.' "
                    "WHERE id=? AND status IN ('queued', 'running')",
                    (timestamp, row["id"]),
                )
                changed = connection.execute(
                    "SELECT changes() AS count"
                ).fetchone()["count"]
                if changed != 1:
                    continue
                counts["stage_attempts"] += 1
                self._append_event(
                    connection,
                    "run",
                    row["run_id"],
                    "stage.attempt.failed",
                    {
                        "attempt_id": row["id"],
                        "production_id": row["production_id"],
                        "stage": row["stage"],
                        "attempt": row["attempt"],
                        "cache_key": row["cache_key"],
                        "result": None,
                        "error_code": "process_interrupted",
                        "error_message": "The previous Studio process stopped.",
                    },
                    created_at=timestamp,
                )
            for provider_task in active_provider_tasks:
                next_status = provider_task["status"]
                if next_status == "recovering":
                    next_status = (
                        "submitted" if provider_task["submitted_at"] else "prepared"
                    )
                connection.execute(
                    "UPDATE provider_tasks SET status=?, current_stage_attempt_id=NULL, "
                    "current_job_id=NULL, updated_at=? WHERE id=? "
                    "AND current_stage_attempt_id IS NOT NULL AND current_job_id IS NOT NULL",
                    (next_status, timestamp, provider_task["id"]),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    continue
                counts["provider_tasks"] += 1
                self._append_event(
                    connection,
                    "run",
                    provider_task["run_id"],
                    "video_generation.provider_recovery_pending",
                    {
                        "provider_task_record_id": provider_task["id"],
                        "production_id": provider_task["production_id"],
                        "provider_task_id": provider_task["provider_task_id"],
                        "previous_status": provider_task["status"],
                        "status": next_status,
                        "previous_attempt_id": provider_task[
                            "current_stage_attempt_id"
                        ],
                        "previous_job_id": provider_task["current_job_id"],
                        "cache_key": provider_task["cache_key"],
                        "error_code": "process_interrupted",
                    },
                    created_at=timestamp,
                )
            pipeline_claims = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE state IN "
                "('active', 'waiting_provider', 'continuing', 'cancel_requested') "
                "ORDER BY created_at, run_id"
            ).fetchall()
            for claim in pipeline_claims:
                pending_provider = connection.execute(
                    "SELECT 1 FROM provider_tasks WHERE run_id=? "
                    "AND status NOT IN ('succeeded', 'failed') LIMIT 1",
                    (claim["run_id"],),
                ).fetchone()
                if claim["state"] == "cancel_requested":
                    next_state = (
                        "cancel_requested"
                        if pending_provider is not None
                        else "cancelled"
                    )
                elif pending_provider is not None:
                    next_state = "waiting_provider"
                elif (
                    claim["state"] == "waiting_provider"
                    and claim["source_stage_attempt_id"] is None
                ):
                    next_state = (
                        "recovery_blocked"
                        if claim["request_protection"] == "dpapi-v1"
                        else "unavailable"
                    )
                else:
                    next_state = (
                        "ready"
                        if (
                            claim["request_protection"] == "dpapi-v1"
                            and claim["source_stage_attempt_id"] is not None
                        )
                        else (
                            "recovery_blocked"
                            if claim["request_protection"] == "dpapi-v1"
                            else "unavailable"
                        )
                    )
                clear_private = next_state == "cancelled"
                if (
                    next_state == claim["state"]
                    and claim["continuation_job_id"] is None
                    and not clear_private
                ):
                    continue
                connection.execute(
                    "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
                    "request_protection=CASE WHEN ? THEN 'none' ELSE request_protection END, "
                    "request_ciphertext=CASE WHEN ? THEN NULL ELSE request_ciphertext END, "
                    "updated_at=?, error_code='process_interrupted', "
                    "error_message='The previous Studio process stopped.' "
                    "WHERE production_id=? AND pipeline_key=? AND state=? AND updated_at=?",
                    (
                        next_state,
                        int(clear_private),
                        int(clear_private),
                        timestamp,
                        claim["production_id"],
                        claim["pipeline_key"],
                        claim["state"],
                        claim["updated_at"],
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    continue
                counts["pipeline_claims"] += 1
                self._append_event(
                    connection,
                    "run",
                    claim["run_id"],
                    "pipeline.continuation.interrupted",
                    {
                        "production_id": claim["production_id"],
                        "pipeline_key": claim["pipeline_key"],
                        "previous_state": claim["state"],
                        "state": next_state,
                        "error_code": "process_interrupted",
                    },
                    created_at=timestamp,
                )
        return counts

    def interrupt_job(
        self,
        job_id: str,
        *,
        cancel_provider_task: bool = False,
        provider_task_record_id: str | None = None,
        preserve_pipeline_continuation: bool = False,
    ) -> bool:
        """Atomically interrupt one active job and its explicit provider cancel.

        Studio shutdown passes the default ``cancel_provider_task=False`` so a
        long-running remote render remains recoverable after restart.  An
        operator cancellation opts in and, when this job owns a provider task,
        moves that exact task to ``cancel_requested`` in the same transaction
        as the job/stage interruption.  The protected request and durable
        marker are intentionally retained until a later GET-only cancellation
        reconciliation proves the provider outcome.
        """

        validate_identifier(job_id, label="job id")
        if not isinstance(preserve_pipeline_continuation, bool):
            raise ValueError("pipeline continuation preservation must be a boolean")
        if provider_task_record_id is not None:
            self._validate_provider_task_record_id(provider_task_record_id)
            if not cancel_provider_task:
                raise ValueError(
                    "provider task cancellation requires explicit operator intent"
                )

        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT id, kind, status, production_id, payload_json, error_code "
                "FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            # Only the claimed top job owns the pipeline cancellation state.
            # Keep this lookup exact: an internally retired child must never
            # be mistaken for an operator cancellation of its parent.
            pipeline_claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE active_job_id=? LIMIT 1",
                (job_id,),
            ).fetchone()
            if row["status"] not in {"queued", "running"}:
                # Queue admission or shutdown preservation can move this exact
                # top to a terminal failed/interrupted row with a ready claim,
                # then race an operator cancellation already published in
                # JobManager. Fence that one generation without rewriting the
                # terminal job. Shutdown preservation deliberately does not
                # take this destructive path.
                terminal_ready_cancel_identity = bool(
                    cancel_provider_task
                    and not preserve_pipeline_continuation
                    and row["kind"] == "local_pipeline"
                    and row["status"] in {"failed", "interrupted"}
                    and pipeline_claim is not None
                    and pipeline_claim["continuation_job_id"] is None
                )
                if (
                    terminal_ready_cancel_identity
                    and pipeline_claim["state"] == "cancelled"
                ):
                    return True
                terminal_ready_cancel = bool(
                    terminal_ready_cancel_identity
                    and pipeline_claim["state"] == "ready"
                )
                if not terminal_ready_cancel:
                    return False
                connection.execute(
                    "UPDATE local_pipeline_claims SET state='cancelled', "
                    "continuation_job_id=NULL, request_protection='none', "
                    "request_ciphertext=NULL, updated_at=?, "
                    "error_code='pipeline_cancelled', "
                    "error_message='The pipeline was cancelled by the operator.' "
                    "WHERE production_id=? AND pipeline_key=? AND active_job_id=? "
                    "AND state='ready' AND continuation_job_id IS NULL "
                    "AND updated_at=?",
                    (
                        timestamp,
                        pipeline_claim["production_id"],
                        pipeline_claim["pipeline_key"],
                        job_id,
                        pipeline_claim["updated_at"],
                    ),
                )
                if connection.execute(
                    "SELECT changes() AS count"
                ).fetchone()["count"] != 1:
                    return False
                self._append_event(
                    connection,
                    "run",
                    pipeline_claim["run_id"],
                    "pipeline.continuation.cancel_requested",
                    {
                        "production_id": pipeline_claim["production_id"],
                        "pipeline_key": pipeline_claim["pipeline_key"],
                        "job_id": job_id,
                        "previous_state": "ready",
                        "state": "cancelled",
                        "error_code": "pipeline_cancelled",
                    },
                    created_at=timestamp,
                )
                return True
            attempts = connection.execute(
                "SELECT * FROM stage_attempts WHERE job_id=? AND status IN ('queued', 'running') "
                "ORDER BY created_at, rowid",
                (job_id,),
            ).fetchall()
            provider_task: sqlite3.Row | None = None
            if cancel_provider_task:
                if provider_task_record_id is None:
                    provider_rows = connection.execute(
                        "SELECT * FROM provider_tasks WHERE current_job_id=? "
                        "AND status NOT IN ('succeeded', 'failed') ORDER BY rowid LIMIT 2",
                        (job_id,),
                    ).fetchall()
                else:
                    provider_rows = connection.execute(
                        "SELECT * FROM provider_tasks WHERE id=? "
                        "AND current_job_id=? AND status NOT IN ('succeeded', 'failed')",
                        (provider_task_record_id, job_id),
                    ).fetchall()
                if len(provider_rows) > 1:
                    raise sqlite3.IntegrityError(
                        "one job cannot own multiple active provider tasks"
                    )
                if provider_task_record_id is not None and not provider_rows:
                    raise AtomicCompletionError(
                        "provider cancellation ownership changed",
                        code="atomic_failure_not_active",
                        job_status="active",
                        stage_status="unknown",
                    )
                if provider_rows:
                    provider_task = provider_rows[0]
                    linked_attempts = [
                        attempt
                        for attempt in attempts
                        if attempt["id"]
                        == provider_task["current_stage_attempt_id"]
                    ]
                    if (
                        len(linked_attempts) != 1
                        or provider_task["current_job_id"] != job_id
                        or provider_task["production_id"] != row["production_id"]
                        or linked_attempts[0]["production_id"]
                        != provider_task["production_id"]
                        or linked_attempts[0]["run_id"] != provider_task["run_id"]
                        or linked_attempts[0]["stage"] != provider_task["stage"]
                        or linked_attempts[0]["cache_key"]
                        != provider_task["cache_key"]
                    ):
                        raise AtomicCompletionError(
                            "provider cancellation provenance is invalid",
                            code="atomic_failure_not_active",
                            job_status="active",
                            stage_status=(
                                linked_attempts[0]["status"]
                                if linked_attempts
                                else "unknown"
                            ),
                        )
            connection.execute(
                "UPDATE jobs SET status='interrupted', completed_at=?, "
                "error_code='process_interrupted', error_message='The Studio process stopped.' "
                "WHERE id=? AND status IN ('queued', 'running')",
                (timestamp, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                return False
            self._append_event(
                connection,
                "job",
                job_id,
                "job.interrupted",
                {
                    "kind": row["kind"],
                    "production_id": row["production_id"],
                    "error_code": "process_interrupted",
                },
                created_at=timestamp,
            )
            for attempt in attempts:
                connection.execute(
                    "UPDATE stage_attempts SET status='failed', completed_at=?, result_json=NULL, "
                    "error_code='process_interrupted', error_message='The Studio process stopped.' "
                    "WHERE id=? AND status IN ('queued', 'running')",
                    (timestamp, attempt["id"]),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] == 1:
                    self._append_event(
                        connection,
                        "run",
                        attempt["run_id"],
                        "stage.attempt.failed",
                        {
                            "attempt_id": attempt["id"],
                            "production_id": attempt["production_id"],
                            "stage": attempt["stage"],
                            "attempt": attempt["attempt"],
                            "cache_key": attempt["cache_key"],
                            "result": None,
                            "error_code": "process_interrupted",
                            "error_message": "The Studio process stopped.",
                        },
                        created_at=timestamp,
                    )
            if provider_task is not None:
                connection.execute(
                    "UPDATE provider_tasks SET status='cancel_requested', "
                    "current_stage_attempt_id=NULL, current_job_id=NULL, "
                    "updated_at=?, completed_at=NULL, "
                    "error_code='provider_cancel_requested', "
                    "error_message='Provider cancellation was requested by the operator.' "
                    "WHERE id=? AND current_stage_attempt_id=? AND current_job_id=? "
                    "AND status NOT IN ('succeeded', 'failed')",
                    (
                        timestamp,
                        provider_task["id"],
                        provider_task["current_stage_attempt_id"],
                        job_id,
                    ),
                )
                if connection.execute(
                    "SELECT changes() AS count"
                ).fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "provider changed before cancellation commit",
                        code="atomic_failure_not_active",
                        job_status="interrupted",
                        stage_status="failed",
                    )
                self._append_event(
                    connection,
                    "run",
                    provider_task["run_id"],
                    "video_generation.provider_state_changed",
                    {
                        "provider_task_record_id": provider_task["id"],
                        "production_id": provider_task["production_id"],
                        "provider": provider_task["provider"],
                        "provider_task_id": provider_task["provider_task_id"],
                        "attempt_id": provider_task["current_stage_attempt_id"],
                        "job_id": job_id,
                        "cache_key": provider_task["cache_key"],
                        "attempt_sequence": provider_task["attempt_sequence"],
                        "status": "cancel_requested",
                        "error_code": "provider_cancel_requested",
                    },
                    created_at=timestamp,
                )
            # A child can be retired internally after a timeout, provenance
            # failure, or parent wait error; treating that child interruption
            # as operator cancellation can strand the top row in ``running``.
            # The top worker subsequently commits either failure, shutdown
            # preservation, or explicit cancellation through its own ID.
            if pipeline_claim is not None and pipeline_claim["state"] not in {
                "succeeded",
                "cancelled",
            }:
                pending_provider = connection.execute(
                    "SELECT 1 FROM provider_tasks WHERE run_id=? "
                    "AND status NOT IN ('succeeded', 'failed') LIMIT 1",
                    (pipeline_claim["run_id"],),
                ).fetchone()
                if preserve_pipeline_continuation:
                    next_pipeline_state = (
                        "waiting_provider"
                        if pending_provider is not None
                        else (
                            "ready"
                            if (
                                pipeline_claim["request_protection"] == "dpapi-v1"
                                and pipeline_claim["source_stage_attempt_id"] is not None
                            )
                            else (
                                "recovery_blocked"
                                if pipeline_claim["request_protection"] == "dpapi-v1"
                                else "unavailable"
                            )
                        )
                    )
                    pipeline_error_code = "process_interrupted"
                    pipeline_error_message = "The Studio process stopped."
                    clear_private = False
                else:
                    next_pipeline_state = (
                        "cancel_requested"
                        if pending_provider is not None
                        else "cancelled"
                    )
                    pipeline_error_code = (
                        "pipeline_cancel_requested"
                        if pending_provider is not None
                        else "pipeline_cancelled"
                    )
                    pipeline_error_message = "The pipeline was cancelled by the operator."
                    clear_private = next_pipeline_state == "cancelled"
                connection.execute(
                    "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
                    "request_protection=CASE WHEN ? THEN 'none' ELSE request_protection END, "
                    "request_ciphertext=CASE WHEN ? THEN NULL ELSE request_ciphertext END, "
                    "updated_at=?, error_code=?, error_message=? "
                    "WHERE production_id=? AND pipeline_key=? AND state=? AND updated_at=?",
                    (
                        next_pipeline_state,
                        int(clear_private),
                        int(clear_private),
                        timestamp,
                        pipeline_error_code,
                        pipeline_error_message,
                        pipeline_claim["production_id"],
                        pipeline_claim["pipeline_key"],
                        pipeline_claim["state"],
                        pipeline_claim["updated_at"],
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "pipeline continuation changed before interruption",
                        code="pipeline_continuation_changed",
                        job_status="interrupted",
                        stage_status="unknown",
                    )
                self._append_event(
                    connection,
                    "run",
                    pipeline_claim["run_id"],
                    (
                        "pipeline.continuation.interrupted"
                        if preserve_pipeline_continuation
                        else "pipeline.continuation.cancel_requested"
                    ),
                    {
                        "production_id": pipeline_claim["production_id"],
                        "pipeline_key": pipeline_claim["pipeline_key"],
                        "job_id": job_id,
                        "previous_state": pipeline_claim["state"],
                        "state": next_pipeline_state,
                        "error_code": pipeline_error_code,
                    },
                    created_at=timestamp,
                )
            return True

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        scope_type: str,
        scope_id: str,
        event_type: str,
        payload: Any,
        *,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        timestamp = created_at or utc_now()
        previous = connection.execute(
            "SELECT event_hash FROM events WHERE scope_type=? AND scope_id=? ORDER BY id DESC LIMIT 1",
            (scope_type, scope_id),
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        payload_json = _json(payload)
        digest_source = canonical_json(
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "event_type": event_type,
                "created_at": timestamp,
                "payload": _loads(payload_json, {}),
                "previous_hash": previous_hash,
            }
        )
        event_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        cursor = connection.execute(
            "INSERT INTO events(scope_type, scope_id, event_type, created_at, payload_json, previous_hash, event_hash) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (scope_type, scope_id, event_type, timestamp, payload_json, previous_hash, event_hash),
        )
        return {
            "id": cursor.lastrowid,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "event_type": event_type,
            "created_at": timestamp,
            "payload": _loads(payload_json, {}),
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        }

    def append_event(self, scope_type: str, scope_id: str, event_type: str, payload: Any) -> dict[str, Any]:
        with self.transaction() as connection:
            return self._append_event(connection, scope_type, scope_id, event_type, payload)

    @staticmethod
    def _review_events_from_connection(
        connection: sqlite3.Connection, production_id: str
    ) -> list[dict[str, Any]]:
        """Load only the closed review ledger for one production.

        Reviews deliberately reuse the existing immutable, hash-chained event
        store instead of adding a mutable status table.  The public snapshot is
        reconstructed from these actions, including after event-mirror restore.
        """

        from .reviews import REVIEW_EVENT_TYPES

        placeholders = ",".join("?" for _ in REVIEW_EVENT_TYPES)
        rows = connection.execute(
            "SELECT * FROM events WHERE scope_type='production' AND scope_id=? "
            f"AND event_type IN ({placeholders}) ORDER BY id",
            (production_id, *sorted(REVIEW_EVENT_TYPES)),
        ).fetchall()
        return [StudioDatabase._event_dict(row) for row in rows]

    def review_snapshot(self, production_id: str) -> dict[str, Any]:
        from .reviews import review_snapshot

        with self.session() as connection:
            production = connection.execute(
                "SELECT 1 FROM productions WHERE id=?", (production_id,)
            ).fetchone()
            if production is None:
                raise KeyError("production not found")
            events = self._review_events_from_connection(connection, production_id)
        return review_snapshot(production_id, events)

    def validate_review_identity(
        self,
        production_id: str,
        *,
        artifact_id: str,
        revision_id: str,
        run_id: str,
    ) -> None:
        """Resolve exact review provenance without exposing local paths."""

        with self.session() as connection:
            artifact = connection.execute(
                "SELECT production_id, available FROM artifacts WHERE id=?",
                (artifact_id,),
            ).fetchone()
            revision = connection.execute(
                "SELECT production_id FROM revisions WHERE id=?", (revision_id,)
            ).fetchone()
            run = connection.execute(
                "SELECT production_id, revision_id FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        if artifact is None or not bool(artifact["available"]):
            raise KeyError("artifact not found")
        if revision is None or run is None:
            raise KeyError("review lineage not found")
        if (
            artifact["production_id"] != production_id
            or revision["production_id"] != production_id
            or run["production_id"] != production_id
            or run["revision_id"] != revision_id
        ):
            raise ValueError("review identity does not belong to the production")

    def append_review_action(
        self, production_id: str, action: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Atomically deduplicate, validate, and append one review action.

        The production-scoped idempotency key is compared inside the same
        ``BEGIN IMMEDIATE`` transaction as the event append.  A replay of the
        exact request returns its original event; key reuse with different
        content fails closed.
        """

        from .reviews import (
            ReviewValidationError,
            review_snapshot,
            validate_review_action,
            validate_review_transition,
        )

        normalized = validate_review_action(action)
        with self.transaction() as connection:
            production = connection.execute(
                "SELECT 1 FROM productions WHERE id=?", (production_id,)
            ).fetchone()
            if production is None:
                raise KeyError("production not found")
            events = self._review_events_from_connection(connection, production_id)
            for event in events:
                payload = validate_review_action(event.get("payload"))
                if payload["idempotency_key"] != normalized["idempotency_key"]:
                    continue
                if payload["request_digest"] != normalized["request_digest"]:
                    raise ReviewValidationError(
                        "idempotency_key was already used for a different review action",
                        code="review_idempotency_conflict",
                    )
                return event, False
            snapshot = review_snapshot(production_id, events)
            validate_review_transition(snapshot, normalized)
            event = self._append_event(
                connection,
                "production",
                production_id,
                f"review.{normalized['action']}",
                normalized,
            )
            return event, True

    @staticmethod
    def _announcement_recipe_record(row: sqlite3.Row) -> dict[str, Any]:
        """Decode and verify one exact recipe carried by an append-only event."""

        payload = _loads(row["payload_json"], {})
        expected_keys = {
            "schema_version",
            "recipe_id",
            "recipe_version_id",
            "revision",
            "parent_version_id",
            "clone_source_version_id",
            "recipe_digest",
            "recipe_bytes",
            "recipe_base64",
            "summary",
        }
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            raise sqlite3.IntegrityError("announcement recipe event is invalid")
        recipe_id = payload.get("recipe_id")
        version_id = payload.get("recipe_version_id")
        revision = payload.get("revision")
        parent_version_id = payload.get("parent_version_id")
        clone_source_version_id = payload.get("clone_source_version_id")
        digest = payload.get("recipe_digest")
        byte_count = payload.get("recipe_bytes")
        encoded = payload.get("recipe_base64")
        if (
            payload.get("schema_version") != 1
            or not isinstance(recipe_id, str)
            or re.fullmatch(r"announcement_[0-9a-f]{32}", recipe_id) is None
            or not isinstance(version_id, str)
            or re.fullmatch(r"annv_[0-9a-f]{32}", version_id) is None
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or (
                parent_version_id is not None
                and (
                    not isinstance(parent_version_id, str)
                    or re.fullmatch(r"annv_[0-9a-f]{32}", parent_version_id) is None
                )
            )
            or (
                clone_source_version_id is not None
                and (
                    not isinstance(clone_source_version_id, str)
                    or re.fullmatch(r"annv_[0-9a-f]{32}", clone_source_version_id)
                    is None
                )
            )
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9A-F]{64}", digest) is None
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or not 1 <= byte_count <= MAX_ANNOUNCEMENT_RECIPE_BYTES
            or not isinstance(encoded, str)
        ):
            raise sqlite3.IntegrityError("announcement recipe event is invalid")
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
            recipe = json.loads(raw.decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise sqlite3.IntegrityError("announcement recipe event is invalid") from None
        if (
            len(raw) != byte_count
            or hashlib.sha256(raw).hexdigest().upper() != digest
            or not isinstance(recipe, dict)
            or canonical_json(recipe).encode("utf-8") != raw
        ):
            raise sqlite3.IntegrityError("announcement recipe event is invalid")
        try:
            from .announcement_video import (
                announcement_recipe_audit_summary,
                validate_announcement_recipe_payload,
            )

            normalized_recipe = validate_announcement_recipe_payload(recipe)
            expected_summary = sanitize_for_storage(
                announcement_recipe_audit_summary(normalized_recipe)
            )
        except (ImportError, TypeError, ValueError):
            raise sqlite3.IntegrityError(
                "announcement recipe event is invalid"
            ) from None
        if normalized_recipe != recipe or payload.get("summary") != expected_summary:
            raise sqlite3.IntegrityError("announcement recipe event is invalid")
        return {
            "id": recipe_id,
            "version_id": version_id,
            "production_id": row["scope_id"],
            "revision": revision,
            "parent_version_id": parent_version_id,
            "clone_source_version_id": clone_source_version_id,
            "digest": digest,
            "created_at": row["created_at"],
            "recipe": recipe,
            "event_id": row["id"],
        }

    @classmethod
    def _announcement_recipe_records(
        cls, connection: sqlite3.Connection, production_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM events WHERE scope_type='production' AND scope_id=? "
            "AND event_type='announcement.recipe.saved' ORDER BY id",
            (production_id,),
        ).fetchall()
        records = [cls._announcement_recipe_record(row) for row in rows]
        seen_versions: set[str] = set()
        latest_revision: dict[str, int] = {}
        latest_version: dict[str, str] = {}
        for record in records:
            recipe_id = record["id"]
            revision = record["revision"]
            parent = record["parent_version_id"]
            clone_source = record["clone_source_version_id"]
            if (
                record["version_id"] in seen_versions
                or revision != latest_revision.get(recipe_id, 0) + 1
                or (
                    revision == 1
                    and parent is not None
                )
                or (
                    revision > 1
                    and parent != latest_version.get(recipe_id)
                )
                or (revision > 1 and clone_source is not None)
                or (
                    revision == 1
                    and clone_source is not None
                    and clone_source not in seen_versions
                )
            ):
                raise sqlite3.IntegrityError(
                    "announcement recipe event lineage is invalid"
                )
            seen_versions.add(record["version_id"])
            latest_revision[recipe_id] = revision
            latest_version[recipe_id] = record["version_id"]
        return records

    def save_announcement_recipe(
        self,
        production_id: str,
        recipe_id: str,
        *,
        expected_revision: int,
        recipe: dict[str, Any],
        summary: dict[str, Any],
        clone_source_version_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Append one exact recipe revision with CAS and lost-response dedupe."""

        validate_identifier(production_id, label="production id")
        validate_identifier(recipe_id, label="announcement recipe id")
        if (
            re.fullmatch(r"announcement_[0-9a-f]{32}", recipe_id) is None
            or isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or not 0 <= expected_revision <= 1_000_000
            or not isinstance(recipe, dict)
            or not isinstance(summary, dict)
            or (
                clone_source_version_id is not None
                and (
                    not isinstance(clone_source_version_id, str)
                    or re.fullmatch(r"annv_[0-9a-f]{32}", clone_source_version_id)
                    is None
                )
            )
        ):
            raise ValueError("announcement recipe save is invalid")
        raw = canonical_json(recipe).encode("utf-8")
        if not 1 <= len(raw) <= MAX_ANNOUNCEMENT_RECIPE_BYTES:
            raise ValueError("announcement recipe is too large")
        digest = hashlib.sha256(raw).hexdigest().upper()
        encoded = base64.b64encode(raw).decode("ascii")
        with self.transaction() as connection:
            if not connection.execute(
                "SELECT 1 FROM productions WHERE id=?", (production_id,)
            ).fetchone():
                raise KeyError("production not found")
            records = self._announcement_recipe_records(connection, production_id)
            current = next(
                (item for item in reversed(records) if item["id"] == recipe_id),
                None,
            )
            if current is not None and current["digest"] == digest:
                replay_revisions = {
                    current["revision"],
                    max(0, current["revision"] - 1),
                }
                if (
                    expected_revision in replay_revisions
                    and current["clone_source_version_id"]
                    == clone_source_version_id
                ):
                    return current, False
                raise ValueError("announcement recipe revision conflict")
            current_revision = current["revision"] if current is not None else 0
            if expected_revision != current_revision:
                raise ValueError("announcement recipe revision conflict")
            revision = current_revision + 1
            version_id = f"annv_{uuid.uuid4().hex}"
            timestamp = utc_now()
            event = self._append_event(
                connection,
                "production",
                production_id,
                "announcement.recipe.saved",
                {
                    "schema_version": 1,
                    "recipe_id": recipe_id,
                    "recipe_version_id": version_id,
                    "revision": revision,
                    "parent_version_id": (
                        current["version_id"] if current is not None else None
                    ),
                    "clone_source_version_id": clone_source_version_id,
                    "recipe_digest": digest,
                    "recipe_bytes": len(raw),
                    "recipe_base64": encoded,
                    "summary": summary,
                },
                created_at=timestamp,
            )
            return self._announcement_recipe_record(
                connection.execute(
                    "SELECT * FROM events WHERE id=?", (event["id"],)
                ).fetchone()
            ), True

    def list_announcement_recipe_versions(
        self, production_id: str
    ) -> list[dict[str, Any]]:
        validate_identifier(production_id, label="production id")
        with self.session() as connection:
            return self._announcement_recipe_records(connection, production_id)

    def list_announcement_recipes(
        self, production_id: str
    ) -> list[dict[str, Any]]:
        records = self.list_announcement_recipe_versions(production_id)
        latest: dict[str, dict[str, Any]] = {}
        counts: dict[str, int] = {}
        for record in records:
            latest[record["id"]] = record
            counts[record["id"]] = counts.get(record["id"], 0) + 1
        return sorted(
            (
                {**record, "version_count": counts[recipe_id]}
                for recipe_id, record in latest.items()
            ),
            key=lambda item: (item["created_at"], item["event_id"]),
            reverse=True,
        )

    @staticmethod
    def _validate_announcement_execution_recipe_links(
        versions: Sequence[dict[str, Any]], executions: Sequence[dict[str, Any]]
    ) -> None:
        by_version = {item["version_id"]: item for item in versions}
        for execution in executions:
            recipe = by_version.get(execution["recipe_version_id"])
            if (
                recipe is None
                or recipe["id"] != execution["recipe_id"]
                or recipe["revision"] != execution["recipe_revision"]
                or recipe["digest"] != execution["recipe_digest"]
            ):
                raise sqlite3.IntegrityError(
                    "announcement execution recipe lineage is invalid"
                )

    def announcement_snapshot(self, production_id: str) -> dict[str, Any]:
        """Read latest recipes, all versions, and links from one DB snapshot."""

        validate_identifier(production_id, label="production id")
        with self.session() as connection:
            if not connection.execute(
                "SELECT 1 FROM productions WHERE id=?", (production_id,)
            ).fetchone():
                raise KeyError("production not found")
            versions = self._announcement_recipe_records(connection, production_id)
            latest: dict[str, dict[str, Any]] = {}
            counts: dict[str, int] = {}
            for record in versions:
                latest[record["id"]] = record
                counts[record["id"]] = counts.get(record["id"], 0) + 1
            recipes = sorted(
                (
                    {**record, "version_count": counts[recipe_id]}
                    for recipe_id, record in latest.items()
                ),
                key=lambda item: (item["created_at"], item["event_id"]),
                reverse=True,
            )
            executions = list(
                reversed(
                    self._announcement_execution_records(connection, production_id)
                )
            )
            self._validate_announcement_execution_recipe_links(
                versions, executions
            )
            return {
                "recipes": recipes,
                "recipe_versions": versions,
                "executions": executions,
            }

    def get_announcement_recipe(
        self, production_id: str, recipe_id: str, *, revision: int | None = None
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        validate_identifier(recipe_id, label="announcement recipe id")
        records = self.list_announcement_recipe_versions(production_id)
        matches = [item for item in records if item["id"] == recipe_id]
        if revision is None:
            return matches[-1] if matches else None
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("announcement recipe revision is invalid")
        return next((item for item in matches if item["revision"] == revision), None)

    @staticmethod
    def _announcement_execution_records(
        connection: sqlite3.Connection, production_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM events WHERE scope_type='production' AND scope_id=? "
            "AND event_type='announcement.recipe.executed' ORDER BY id",
            (production_id,),
        ).fetchall()
        output: list[dict[str, Any]] = []
        required = {
            "schema_version",
            "link_key",
            "recipe_id",
            "recipe_version_id",
            "recipe_revision",
            "recipe_digest",
            "job_id",
            "run_id",
            "revision_id",
            "request_key",
            "deduplicated",
        }
        for row in rows:
            payload = _loads(row["payload_json"], {})
            if not isinstance(payload, dict) or set(payload) != required:
                raise sqlite3.IntegrityError(
                    "announcement execution event is invalid"
                )
            recipe_id = payload.get("recipe_id")
            recipe_version_id = payload.get("recipe_version_id")
            recipe_revision = payload.get("recipe_revision")
            recipe_digest = payload.get("recipe_digest")
            job_id = payload.get("job_id")
            run_id = payload.get("run_id")
            revision_id = payload.get("revision_id")
            request_key = payload.get("request_key")
            deduplicated = payload.get("deduplicated")
            link_key = payload.get("link_key")
            expected_link_key = (
                hashlib.sha256(
                    f"{recipe_version_id}\0{job_id}".encode("utf-8")
                ).hexdigest().upper()
                if isinstance(recipe_version_id, str) and isinstance(job_id, str)
                else None
            )
            if (
                payload.get("schema_version") != 1
                or not isinstance(recipe_id, str)
                or re.fullmatch(r"announcement_[0-9a-f]{32}", recipe_id) is None
                or not isinstance(recipe_version_id, str)
                or re.fullmatch(r"annv_[0-9a-f]{32}", recipe_version_id) is None
                or isinstance(recipe_revision, bool)
                or not isinstance(recipe_revision, int)
                or recipe_revision < 1
                or not isinstance(recipe_digest, str)
                or re.fullmatch(r"[0-9A-F]{64}", recipe_digest) is None
                or not isinstance(job_id, str)
                or re.fullmatch(r"job_[0-9a-f]{32}", job_id) is None
                or not isinstance(run_id, str)
                or re.fullmatch(r"run_[0-9a-f]{32}", run_id) is None
                or not isinstance(revision_id, str)
                or re.fullmatch(r"rev_[0-9a-f]{32}", revision_id) is None
                or not isinstance(request_key, str)
                or re.fullmatch(r"[0-9A-F]{64}", request_key) is None
                or not isinstance(deduplicated, bool)
                or link_key != expected_link_key
            ):
                raise sqlite3.IntegrityError(
                    "announcement execution event is invalid"
                )
            output.append(
                {
                    **payload,
                    "production_id": production_id,
                    "created_at": row["created_at"],
                    "event_id": row["id"],
                }
            )
        return output

    def _record_announcement_execution_in_transaction(
        self,
        connection: sqlite3.Connection,
        production_id: str,
        *,
        recipe: dict[str, Any],
        job: sqlite3.Row,
        run_id: str,
        revision_id: str,
        request_key: str,
        deduplicated: bool,
    ) -> tuple[dict[str, Any], bool]:
        """Verify and link a saved recipe to one Detailed job atomically."""

        recipe_records = self._announcement_recipe_records(connection, production_id)
        stored_recipe = next(
            (
                item
                for item in recipe_records
                if item["version_id"] == recipe.get("version_id")
            ),
            None,
        )
        job_payload = _loads(job["payload_json"], {})
        claim = connection.execute(
            "SELECT * FROM detailed_test_video_claims "
            "WHERE production_id=? AND request_key=?",
            (production_id, request_key),
        ).fetchone()
        run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if (
            stored_recipe is None
            or recipe != stored_recipe
            or job["kind"] != "detailed_test_video"
            or job["production_id"] != production_id
            or not isinstance(job_payload, dict)
            or job_payload.get("production_id") != production_id
            or job_payload.get("run_id") != run_id
            or job_payload.get("revision_id") != revision_id
            or job_payload.get("request_key") != request_key
            or job_payload.get("execution_profile") != "local_sapi"
            or job_payload.get("stage") != "detailed_test_video"
            or claim is None
            or claim["run_id"] != run_id
            or claim["revision_id"] != revision_id
            or run is None
            or run["production_id"] != production_id
            or run["revision_id"] != revision_id
            or run["execution_profile"] != "local_sapi"
            or not isinstance(deduplicated, bool)
        ):
            raise sqlite3.IntegrityError(
                "announcement execution provenance is invalid"
            )
        link_key = hashlib.sha256(
            f"{stored_recipe['version_id']}\0{job['id']}".encode("utf-8")
        ).hexdigest().upper()
        existing = next(
            (
                item
                for item in self._announcement_execution_records(
                    connection, production_id
                )
                if item.get("link_key") == link_key
            ),
            None,
        )
        if existing is not None:
            return existing, False
        payload = {
            "schema_version": 1,
            "link_key": link_key,
            "recipe_id": stored_recipe["id"],
            "recipe_version_id": stored_recipe["version_id"],
            "recipe_revision": stored_recipe["revision"],
            "recipe_digest": stored_recipe["digest"],
            "job_id": job["id"],
            "run_id": run_id,
            "revision_id": revision_id,
            "request_key": request_key,
            "deduplicated": deduplicated,
        }
        event = self._append_event(
            connection,
            "production",
            production_id,
            "announcement.recipe.executed",
            payload,
        )
        return {
            **payload,
            "production_id": production_id,
            "created_at": event["created_at"],
            "event_id": event["id"],
        }, True

    def record_announcement_execution(
        self,
        production_id: str,
        *,
        recipe: dict[str, Any],
        job_id: str,
        run_id: str,
        revision_id: str,
        request_key: str,
        deduplicated: bool,
    ) -> tuple[dict[str, Any], bool]:
        validate_identifier(production_id, label="production id")
        for label, value in (
            ("job id", job_id),
            ("run id", run_id),
            ("revision id", revision_id),
        ):
            validate_identifier(value, label=label)
        if (
            not isinstance(recipe, dict)
            or not isinstance(request_key, str)
            or re.fullmatch(r"[0-9A-F]{64}", request_key) is None
            or not isinstance(deduplicated, bool)
        ):
            raise ValueError("announcement execution link is invalid")
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise sqlite3.IntegrityError(
                    "announcement execution job is unavailable"
                )
            return self._record_announcement_execution_in_transaction(
                connection,
                production_id,
                recipe=recipe,
                job=job,
                run_id=run_id,
                revision_id=revision_id,
                request_key=request_key,
                deduplicated=deduplicated,
            )

    def get_announcement_execution(
        self, production_id: str, recipe_version_id: str, job_id: str
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        validate_identifier(recipe_version_id, label="announcement recipe version id")
        validate_identifier(job_id, label="job id")
        with self.session() as connection:
            return next(
                (
                    item
                    for item in reversed(
                        self._announcement_execution_records(connection, production_id)
                    )
                    if item["recipe_version_id"] == recipe_version_id
                    and item["job_id"] == job_id
                ),
                None,
            )

    def list_announcement_executions(
        self, production_id: str
    ) -> list[dict[str, Any]]:
        validate_identifier(production_id, label="production id")
        with self.session() as connection:
            return list(
                reversed(
                    self._announcement_execution_records(connection, production_id)
                )
            )

    def index_production(self, metadata: dict[str, Any], artifacts: Sequence[dict[str, Any]]) -> dict[str, int]:
        production_id = metadata["id"]
        timestamp = utc_now()
        inserted_versions = 0
        changed_artifacts = 0
        with self.transaction() as connection:
            prior = connection.execute("SELECT * FROM productions WHERE id=?", (production_id,)).fetchone()
            connection.execute(
                """
                INSERT INTO productions(
                    id, title, status, technical_status, creative_status,
                    public_release_status, source_rel, output_rel, discovered_at, refreshed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    technical_status=excluded.technical_status,
                    creative_status=excluded.creative_status,
                    public_release_status=excluded.public_release_status,
                    source_rel=excluded.source_rel,
                    output_rel=excluded.output_rel,
                    refreshed_at=excluded.refreshed_at
                """,
                (
                    production_id,
                    metadata.get("title") or production_id,
                    metadata.get("status") or "discovered",
                    metadata.get("technical_status"),
                    metadata.get("creative_status"),
                    metadata.get("public_release_status"),
                    metadata.get("source_rel"),
                    metadata.get("output_rel"),
                    prior["discovered_at"] if prior else timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE artifacts SET available=0, indexed_at=? "
                "WHERE production_id=? AND origin IN ('record', 'output')",
                (timestamp, production_id),
            )
            for artifact in artifacts:
                existing = connection.execute(
                    "SELECT bytes, mtime_ns, sha256, available FROM artifacts WHERE id=?",
                    (artifact["id"],),
                ).fetchone()
                changed = not existing or any(
                    (
                        existing["bytes"] != artifact["bytes"],
                        existing["mtime_ns"] != artifact["mtime_ns"],
                        (existing["sha256"] or None) != (artifact.get("sha256") or None),
                    )
                )
                changed_artifacts += int(changed)
                connection.execute(
                    """
                    INSERT INTO artifacts(
                        id, production_id, rel_path, origin, name, kind, media_type,
                        bytes, mtime_ns, sha256, is_heavy, available, indexed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        production_id=excluded.production_id,
                        rel_path=excluded.rel_path,
                        origin=excluded.origin,
                        name=excluded.name,
                        kind=excluded.kind,
                        media_type=excluded.media_type,
                        bytes=excluded.bytes,
                        mtime_ns=excluded.mtime_ns,
                        sha256=excluded.sha256,
                        is_heavy=excluded.is_heavy,
                        available=1,
                        indexed_at=excluded.indexed_at
                    """,
                    (
                        artifact["id"],
                        production_id,
                        artifact["rel_path"],
                        artifact["origin"],
                        artifact["name"],
                        artifact["kind"],
                        artifact["media_type"],
                        artifact["bytes"],
                        artifact["mtime_ns"],
                        artifact.get("sha256"),
                        int(bool(artifact["is_heavy"])),
                        timestamp,
                    ),
                )
                version_exists = connection.execute(
                    "SELECT 1 FROM artifact_versions WHERE artifact_id=? AND bytes=? AND mtime_ns=? "
                    "AND COALESCE(sha256, '')=COALESCE(?, '') LIMIT 1",
                    (
                        artifact["id"],
                        artifact["bytes"],
                        artifact["mtime_ns"],
                        artifact.get("sha256"),
                    ),
                ).fetchone()
                if not version_exists:
                    connection.execute(
                        "INSERT INTO artifact_versions(artifact_id, observed_at, bytes, mtime_ns, sha256) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (
                            artifact["id"],
                            timestamp,
                            artifact["bytes"],
                            artifact["mtime_ns"],
                            artifact.get("sha256"),
                        ),
                    )
                    inserted_versions += 1
            missing_count = connection.execute(
                "SELECT COUNT(*) AS count FROM artifacts WHERE production_id=? AND available=0",
                (production_id,),
            ).fetchone()["count"]
            event_type = "production.indexed" if not prior else "production.index_refreshed"
            self._append_event(
                connection,
                "production",
                production_id,
                event_type,
                {
                    "artifacts_seen": len(artifacts),
                    "artifacts_changed": changed_artifacts,
                    "artifacts_missing": missing_count,
                },
                created_at=timestamp,
            )
        return {
            "artifacts_seen": len(artifacts),
            "artifacts_changed": changed_artifacts,
            "artifact_versions_added": inserted_versions,
        }

    def _register_studio_artifact_in_transaction(
        self,
        connection: sqlite3.Connection,
        production_id: str,
        artifact: dict[str, Any],
        *,
        timestamp: str,
    ) -> dict[str, Any]:
        """Register one validated Studio artifact on the caller transaction."""

        connection.execute(
            """
            INSERT INTO artifacts(
                id, production_id, rel_path, origin, name, kind, media_type,
                bytes, mtime_ns, sha256, is_heavy, available, indexed_at
            ) VALUES(?, ?, ?, 'studio', ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                bytes=excluded.bytes,
                mtime_ns=excluded.mtime_ns,
                sha256=excluded.sha256,
                available=1,
                indexed_at=excluded.indexed_at
            """,
            (
                artifact["id"],
                production_id,
                artifact["rel_path"],
                artifact["name"],
                artifact["kind"],
                artifact["media_type"],
                artifact["bytes"],
                artifact["mtime_ns"],
                artifact.get("sha256"),
                int(bool(artifact["is_heavy"])),
                timestamp,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO artifact_versions(artifact_id, observed_at, bytes, mtime_ns, sha256) "
            "VALUES(?, ?, ?, ?, ?)",
            (
                artifact["id"],
                timestamp,
                artifact["bytes"],
                artifact["mtime_ns"],
                artifact.get("sha256"),
            ),
        )
        row = connection.execute(
            "SELECT * FROM artifacts WHERE id=?", (artifact["id"],)
        ).fetchone()
        if row is None or any(
            (
                row["production_id"] != production_id,
                row["rel_path"] != artifact["rel_path"],
                row["origin"] != "studio",
                row["name"] != artifact["name"],
                row["kind"] != artifact["kind"],
                row["media_type"] != artifact["media_type"],
                row["bytes"] != artifact["bytes"],
                row["mtime_ns"] != artifact["mtime_ns"],
                row["sha256"] != artifact.get("sha256"),
                bool(row["is_heavy"]) != bool(artifact["is_heavy"]),
                not bool(row["available"]),
            )
        ):
            raise ValueError("artifact registration did not preserve artifact identity")
        result = self._artifact_dict(row)
        self._append_event(
            connection,
            "production",
            production_id,
            "artifact.created",
            {
                "artifact_id": result["id"],
                "kind": result["kind"],
                "artifact": {
                    key: result[key]
                    for key in (
                        "id",
                        "production_id",
                        "rel_path",
                        "origin",
                        "name",
                        "kind",
                        "media_type",
                        "bytes",
                        "mtime_ns",
                        "sha256",
                        "is_heavy",
                        "available",
                        "indexed_at",
                    )
                },
            },
            created_at=timestamp,
        )
        return result

    def register_studio_artifact(
        self, production_id: str, artifact: dict[str, Any]
    ) -> dict[str, Any]:
        timestamp = utc_now()
        with self.transaction() as connection:
            return self._register_studio_artifact_in_transaction(
                connection,
                production_id,
                artifact,
                timestamp=timestamp,
            )

    @staticmethod
    def _production_dict(row: sqlite3.Row) -> dict[str, Any]:
        keys = set(row.keys())
        archived = bool(row["archived"]) if "archived" in keys else False
        return {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "technical_status": row["technical_status"],
            "creative_status": row["creative_status"],
            "public_release_status": row["public_release_status"],
            "source_rel": row["source_rel"],
            "output_rel": row["output_rel"],
            "discovered_at": row["discovered_at"],
            "refreshed_at": row["refreshed_at"],
            "archived": archived,
            "archived_at": row["archived_at"] if "archived_at" in keys else None,
            "library_read_only": bool(row["source_rel"]),
        }

    @staticmethod
    def _artifact_dict(row: sqlite3.Row) -> dict[str, Any]:
        file_url = f"/api/artifacts/{row['id']}/file"
        return {
            "id": row["id"],
            "production_id": row["production_id"],
            "rel_path": row["rel_path"],
            "origin": row["origin"],
            "name": row["name"],
            "kind": row["kind"],
            "media_type": row["media_type"],
            "bytes": row["bytes"],
            "mtime_ns": row["mtime_ns"],
            "sha256": row["sha256"],
            "is_heavy": bool(row["is_heavy"]),
            "available": bool(row["available"]),
            "indexed_at": row["indexed_at"],
            "file_url": file_url,
            "preview_url": file_url,
            "download_url": file_url,
        }

    def list_productions(
        self, *, include_archived: bool = False, query: str = ""
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip().casefold()
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT p.*,
                       COALESCE(ls.archived, 0) AS archived,
                       ls.archived_at AS archived_at,
                       (SELECT COUNT(*) FROM artifacts a
                        WHERE a.production_id=p.id AND a.available=1) AS artifact_count,
                       (SELECT COALESCE(SUM(a.bytes), 0) FROM artifacts a
                        WHERE a.production_id=p.id AND a.available=1) AS artifact_bytes,
                       (SELECT MAX(j.created_at) FROM jobs j
                        WHERE j.production_id=p.id) AS latest_job_at
                FROM productions p
                LEFT JOIN production_library_states ls ON ls.production_id=p.id
                WHERE (?=1 OR COALESCE(ls.archived, 0)=0)
                  AND (?='' OR instr(lower(p.title), ?) > 0 OR instr(lower(p.id), ?) > 0)
                ORDER BY p.id
                """,
                (
                    int(include_archived),
                    normalized_query,
                    normalized_query,
                    normalized_query,
                ),
            ).fetchall()
        result = []
        for row in rows:
            item = self._production_dict(row)
            item.update(
                artifact_count=row["artifact_count"],
                artifact_bytes=row["artifact_bytes"],
                latest_job_at=row["latest_job_at"],
            )
            result.append(item)
        return result

    def get_production(self, production_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT p.*, COALESCE(ls.archived, 0) AS archived, "
                "ls.archived_at AS archived_at FROM productions p "
                "LEFT JOIN production_library_states ls ON ls.production_id=p.id "
                "WHERE p.id=?",
                (production_id,),
            ).fetchone()
        return self._production_dict(row) if row else None

    @staticmethod
    def _library_operation_result(
        row: sqlite3.Row,
        *,
        production_id: str,
        action: str,
        request_digest: str,
    ) -> dict[str, Any]:
        if any(
            (
                row["production_id"] != production_id,
                row["action"] != action,
                row["request_digest"] != request_digest,
            )
        ):
            raise ValueError("production library operation conflict")
        result = _loads(row["result_json"], None)
        if not isinstance(result, dict):
            raise sqlite3.IntegrityError("production library operation result is invalid")
        return {**result, "deduplicated": True}

    def get_production_library_operation(
        self,
        operation_id: str,
        *,
        production_id: str,
        action: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        """Return one exact prior result or reject operation-ID reuse."""

        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM production_library_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._library_operation_result(
            row,
            production_id=production_id,
            action=action,
            request_digest=request_digest,
        )

    @staticmethod
    def _library_production_row(
        connection: sqlite3.Connection, production_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT p.*, COALESCE(ls.archived, 0) AS archived, "
            "ls.archived_at AS archived_at FROM productions p "
            "LEFT JOIN production_library_states ls ON ls.production_id=p.id "
            "WHERE p.id=?",
            (production_id,),
        ).fetchone()

    @staticmethod
    def _require_mutable_library_row(row: sqlite3.Row | None) -> sqlite3.Row:
        if row is None:
            raise KeyError("production not found")
        if row["source_rel"] is not None or row["output_rel"] is None:
            raise ValueError("production library is read only")
        return row

    def _record_library_operation(
        self,
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        production_id: str,
        action: str,
        request_digest: str,
        event: dict[str, Any],
        result: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        connection.execute(
            "INSERT INTO production_library_operations("
            "operation_id, production_id, action, request_digest, event_id, "
            "result_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                production_id,
                action,
                request_digest,
                event["id"],
                canonical_json(result),
                created_at,
            ),
        )
        return result

    def rename_production_library(
        self,
        production_id: str,
        *,
        operation_id: str,
        request_digest: str,
        expected_title: str,
        title: str,
        filesystem_deduplicated: bool,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        with self.transaction() as connection:
            prior_operation = connection.execute(
                "SELECT * FROM production_library_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior_operation is not None:
                return self._library_operation_result(
                    prior_operation,
                    production_id=production_id,
                    action="rename",
                    request_digest=request_digest,
                )
            row = self._require_mutable_library_row(
                self._library_production_row(connection, production_id)
            )
            if row["title"] not in {expected_title, title}:
                raise ValueError("production library revision conflict")
            connection.execute(
                "UPDATE productions SET title=?, refreshed_at=? WHERE id=?",
                (title, timestamp, production_id),
            )
            event = self._append_event(
                connection,
                "production",
                production_id,
                "production.library.renamed",
                {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_digest": request_digest,
                    "previous_title": expected_title,
                    "title": title,
                    "filesystem_deduplicated": filesystem_deduplicated,
                },
                created_at=timestamp,
            )
            updated = self._library_production_row(connection, production_id)
            assert updated is not None
            result = {
                "schema_version": 1,
                "operation_id": operation_id,
                "action": "rename",
                "production": self._production_dict(updated),
                "deduplicated": False,
            }
            return self._record_library_operation(
                connection,
                operation_id=operation_id,
                production_id=production_id,
                action="rename",
                request_digest=request_digest,
                event=event,
                result=result,
                created_at=timestamp,
            )

    def archive_production_library(
        self,
        production_id: str,
        *,
        operation_id: str,
        request_digest: str,
        expected_archived: bool,
        archived: bool,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        with self.transaction() as connection:
            prior_operation = connection.execute(
                "SELECT * FROM production_library_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior_operation is not None:
                return self._library_operation_result(
                    prior_operation,
                    production_id=production_id,
                    action="archive",
                    request_digest=request_digest,
                )
            row = self._require_mutable_library_row(
                self._library_production_row(connection, production_id)
            )
            if bool(row["archived"]) != expected_archived:
                raise ValueError("production library revision conflict")
            archived_at = timestamp if archived else None
            connection.execute(
                "INSERT INTO production_library_states("
                "production_id, archived, archived_at, updated_at) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(production_id) DO UPDATE SET "
                "archived=excluded.archived, archived_at=excluded.archived_at, "
                "updated_at=excluded.updated_at",
                (production_id, int(archived), archived_at, timestamp),
            )
            event = self._append_event(
                connection,
                "production",
                production_id,
                "production.library.archived"
                if archived
                else "production.library.unarchived",
                {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_digest": request_digest,
                    "previous_archived": expected_archived,
                    "archived": archived,
                },
                created_at=timestamp,
            )
            updated = self._library_production_row(connection, production_id)
            assert updated is not None
            result = {
                "schema_version": 1,
                "operation_id": operation_id,
                "action": "archive",
                "production": self._production_dict(updated),
                "deduplicated": False,
            }
            return self._record_library_operation(
                connection,
                operation_id=operation_id,
                production_id=production_id,
                action="archive",
                request_digest=request_digest,
                event=event,
                result=result,
                created_at=timestamp,
            )

    def record_production_duplicate(
        self,
        production_id: str,
        *,
        source_production_id: str,
        operation_id: str,
        request_digest: str,
        include_imports: bool,
        imported_artifact_count: int,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        with self.transaction() as connection:
            prior_operation = connection.execute(
                "SELECT * FROM production_library_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if prior_operation is not None:
                return self._library_operation_result(
                    prior_operation,
                    production_id=production_id,
                    action="duplicate",
                    request_digest=request_digest,
                )
            source = self._require_mutable_library_row(
                self._library_production_row(connection, source_production_id)
            )
            target = self._require_mutable_library_row(
                self._library_production_row(connection, production_id)
            )
            if source["id"] == target["id"]:
                raise ValueError("production duplicate target conflict")
            event = self._append_event(
                connection,
                "production",
                production_id,
                "production.library.duplicated",
                {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "request_digest": request_digest,
                    "source_production_id": source_production_id,
                    "include_imports": include_imports,
                    "imported_artifact_count": imported_artifact_count,
                },
                created_at=timestamp,
            )
            result = {
                "schema_version": 1,
                "operation_id": operation_id,
                "action": "duplicate",
                "source_production_id": source_production_id,
                "include_imports": include_imports,
                "imported_artifact_count": imported_artifact_count,
                "production": self._production_dict(target),
                "deduplicated": False,
            }
            return self._record_library_operation(
                connection,
                operation_id=operation_id,
                production_id=production_id,
                action="duplicate",
                request_digest=request_digest,
                event=event,
                result=result,
                created_at=timestamp,
            )

    def get_production_detail(
        self,
        production_id: str,
        *,
        artifact_limit: int = 5000,
        artifact_offset: int = 0,
    ) -> dict[str, Any] | None:
        with self.session() as connection:
            return self._production_detail_from_connection(
                connection,
                production_id,
                artifact_limit=artifact_limit,
                artifact_offset=artifact_offset,
            )

    def _production_detail_from_connection(
        self,
        connection: sqlite3.Connection,
        production_id: str,
        *,
        artifact_limit: int,
        artifact_offset: int,
    ) -> dict[str, Any] | None:
        production = connection.execute(
            "SELECT p.*, COALESCE(ls.archived, 0) AS archived, "
            "ls.archived_at AS archived_at FROM productions p "
            "LEFT JOIN production_library_states ls ON ls.production_id=p.id "
            "WHERE p.id=?",
            (production_id,),
        ).fetchone()
        if not production:
            return None
        total = connection.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(bytes), 0) AS bytes "
            "FROM artifacts WHERE production_id=? AND available=1",
            (production_id,),
        ).fetchone()
        artifacts = connection.execute(
            "SELECT * FROM artifacts WHERE production_id=? AND available=1 "
            "ORDER BY CASE "
            "WHEN kind='audit' THEN 0 "
            "WHEN lower(name) LIKE '%master%' THEN 1 "
            "WHEN rel_path LIKE '%03_assembly%' THEN 2 "
            "WHEN kind IN ('video', 'audio') THEN 3 "
            "WHEN kind='image' THEN 4 "
            "ELSE 5 END, origin, rel_path LIMIT ? OFFSET ?",
            (production_id, artifact_limit, artifact_offset),
        ).fetchall()
        revisions = connection.execute(
            "SELECT * FROM revisions WHERE production_id=? ORDER BY sequence DESC",
            (production_id,),
        ).fetchall()
        runs = connection.execute(
            "SELECT * FROM runs WHERE production_id=? ORDER BY created_at DESC",
            (production_id,),
        ).fetchall()
        events = connection.execute(
            "SELECT * FROM events WHERE scope_type='production' AND scope_id=? ORDER BY id DESC LIMIT 200",
            (production_id,),
        ).fetchall()
        approvals = connection.execute(
            "SELECT a.* FROM run_approvals a JOIN runs r ON r.id=a.run_id "
            "WHERE r.production_id=? ORDER BY a.created_at, a.rowid",
            (production_id,),
        ).fetchall()
        provider_tasks = connection.execute(
            "SELECT * FROM provider_tasks WHERE production_id=? "
            "ORDER BY created_at DESC, rowid DESC",
            (production_id,),
        ).fetchall()
        announcement_versions = self._announcement_recipe_records(
            connection, production_id
        )
        announcement_latest: dict[str, dict[str, Any]] = {}
        announcement_version_counts: dict[str, int] = {}
        for recipe_record in announcement_versions:
            recipe_id = recipe_record["id"]
            announcement_latest[recipe_id] = recipe_record
            announcement_version_counts[recipe_id] = (
                announcement_version_counts.get(recipe_id, 0) + 1
            )
        announcement_recipes = sorted(
            (
                {
                    **record,
                    "version_count": announcement_version_counts[recipe_id],
                }
                for recipe_id, record in announcement_latest.items()
            ),
            key=lambda item: (item["created_at"], item["event_id"]),
            reverse=True,
        )
        announcement_executions = list(
            reversed(
                self._announcement_execution_records(connection, production_id)
            )
        )
        self._validate_announcement_execution_recipe_links(
            announcement_versions, announcement_executions
        )
        return {
            "production": self._production_dict(production),
            "artifacts": [self._artifact_dict(row) for row in artifacts],
            "artifact_page": {
                "total": total["count"],
                "total_bytes": total["bytes"],
                "limit": artifact_limit,
                "offset": artifact_offset,
            },
            "revisions": [self._revision_dict(row) for row in revisions],
            "runs": [self._run_dict(row, connection) for row in runs],
            "provider_tasks": [
                self._provider_task_dict(row) for row in provider_tasks
            ],
            "announcement_recipes": announcement_recipes,
            "announcement_recipe_versions": announcement_versions,
            "announcement_executions": announcement_executions,
            "events": [self._event_dict(row) for row in events],
            "approvals": [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "decision": row["decision"],
                    "approved_max": money_from_minor(
                        row["approved_max_minor"], row["currency"]
                    ),
                    "actor": row["actor"],
                    "note": row["note"],
                    "created_at": row["created_at"],
                }
                for row in approvals
            ],
        }

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        return self._artifact_dict(row) if row else None

    @staticmethod
    def _revision_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "production_id": row["production_id"],
            "parent_revision_id": row["parent_revision_id"],
            "sequence": row["sequence"],
            "created_at": row["created_at"],
            "changes": _loads(row["changes_json"], []),
            "rerun_plan": _loads(row["rerun_plan_json"], {}),
            "immutable_digest": row["immutable_digest"],
        }

    def _latest_approval(self, connection: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM run_approvals WHERE run_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "decision": row["decision"],
            "approved_max": money_from_minor(row["approved_max_minor"], row["currency"]),
            "currency": row["currency"],
            "actor": row["actor"],
            "note": row["note"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _local_pipeline_continuation_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Return the safe continuation projection; protected bytes stay private."""

        state = str(row["state"])
        raw_ciphertext = row["request_ciphertext"]
        automatic_recovery_available = bool(
            isinstance(raw_ciphertext, bytes)
            and raw_ciphertext
            and state
            in {
                "active",
                "waiting_provider",
                "ready",
                "continuing",
                "recovery_blocked",
                "cancel_requested",
            }
        )
        return {
            "state": state,
            "automatic": automatic_recovery_available,
            "resume_count": int(row["resume_count"]),
            "job_id": row["continuation_job_id"] or row["active_job_id"],
            "source_job_id": row["source_job_id"],
            "source_attempt_id": row["source_stage_attempt_id"],
            "updated_at": row["updated_at"],
            "next_action": _LOCAL_PIPELINE_CONTINUATION_NEXT_ACTION[state],
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
        }

    @classmethod
    def _local_pipeline_continuation_material_dict(
        cls, row: sqlite3.Row
    ) -> dict[str, Any]:
        result = cls._local_pipeline_continuation_dict(row)
        result.update(
            {
                "production_id": row["production_id"],
                "pipeline_key": row["pipeline_key"],
                "run_id": row["run_id"],
                "revision_id": row["revision_id"],
                "active_job_id": row["active_job_id"],
                "continuation_job_id": row["continuation_job_id"],
                "source_stage_attempt_id": row["source_stage_attempt_id"],
                "created_at": row["created_at"],
                "request_protection": row["request_protection"],
                "request_ciphertext": (
                    bytes(row["request_ciphertext"])
                    if isinstance(row["request_ciphertext"], bytes)
                    else None
                ),
            }
        )
        return result

    @staticmethod
    def _validate_pipeline_request_material(
        request_protection: str | None, request_ciphertext: bytes | None
    ) -> tuple[str, bytes | None]:
        protection = request_protection or "none"
        if protection not in {"dpapi-v1", "none"}:
            raise ValueError("invalid pipeline request protection")
        if protection == "none":
            if request_ciphertext is not None:
                raise ValueError("unprotected pipeline request bytes are not accepted")
            return protection, None
        if not isinstance(request_ciphertext, bytes) or not (
            1 <= len(request_ciphertext) <= _MAX_PIPELINE_REQUEST_CIPHERTEXT_BYTES
        ):
            raise ValueError("invalid protected pipeline request")
        return protection, bytes(request_ciphertext)

    def get_local_pipeline_continuation(
        self, production_id: str, pipeline_key: str
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise ValueError("invalid pipeline key")
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
        return self._local_pipeline_continuation_dict(row) if row else None

    def get_detailed_test_video_claim(
        self, production_id: str, request_key: str
    ) -> dict[str, Any] | None:
        validate_identifier(production_id, label="production id")
        if not isinstance(request_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", request_key
        ) is None:
            raise ValueError("invalid detailed test video key")
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM detailed_test_video_claims "
                "WHERE production_id=? AND request_key=?",
                (production_id, request_key),
            ).fetchone()
        if row is None:
            return None
        return {
            "production_id": row["production_id"],
            "request_key": row["request_key"],
            "run_id": row["run_id"],
            "revision_id": row["revision_id"],
            "active_job_id": row["active_job_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_local_pipeline_continuation_material(
        self, production_id: str, pipeline_key: str
    ) -> dict[str, Any] | None:
        """Return private restart material for in-process orchestration only."""

        validate_identifier(production_id, label="production id")
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise ValueError("invalid pipeline key")
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
        if row is None:
            return None
        return self._local_pipeline_continuation_material_dict(row)

    def list_ready_local_pipeline_continuation_material(
        self, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return private material for auto-continuations that need admission."""

        safe_limit = max(1, min(int(limit), 1000))
        with self.session() as connection:
            rows = connection.execute(
                "SELECT c.* FROM local_pipeline_claims c "
                "LEFT JOIN jobs j ON j.id=c.active_job_id "
                "WHERE c.state='ready' AND c.request_protection='dpapi-v1' "
                "AND typeof(c.request_ciphertext)='blob' "
                "AND c.continuation_job_id IS NULL "
                "AND (j.id IS NULL OR j.status NOT IN ('queued', 'running')) "
                "ORDER BY c.updated_at, c.run_id LIMIT ?",
                (safe_limit,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(self._local_pipeline_continuation_material_dict(row))
        return results

    def block_local_pipeline_continuation(
        self,
        production_id: str,
        pipeline_key: str,
        *,
        expected_updated_at: str,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any] | None:
        """CAS a ready checkpoint to a safe manual-recovery state."""

        validate_identifier(production_id, label="production id")
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise ValueError("invalid pipeline key")
        if not isinstance(expected_updated_at, str) or not expected_updated_at:
            raise ValueError("expected continuation timestamp is required")
        safe_code = str(sanitize_for_storage(error_code or "pipeline_recovery_blocked"))[
            :128
        ]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        timestamp = utc_now()
        with self.transaction() as connection:
            connection.execute(
                "UPDATE local_pipeline_claims SET state='recovery_blocked', "
                "continuation_job_id=NULL, updated_at=?, error_code=?, error_message=? "
                "WHERE production_id=? AND pipeline_key=? AND state='ready' "
                "AND updated_at=? AND continuation_job_id IS NULL",
                (
                    timestamp,
                    safe_code,
                    safe_message,
                    production_id,
                    pipeline_key,
                    expected_updated_at,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                return None
            row = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
            assert row is not None
            self._append_event(
                connection,
                "run",
                row["run_id"],
                "pipeline.continuation.recovery_blocked",
                {
                    "production_id": production_id,
                    "pipeline_key": pipeline_key,
                    "state": "recovery_blocked",
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            return self._local_pipeline_continuation_dict(row)

    def _run_dict(self, row: sqlite3.Row, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
        close = connection is None
        connection = connection or self.connect()
        try:
            approval = self._latest_approval(connection, row["id"])
            estimated = row["estimated_cost_minor"]
            if approval and approval["decision"] == "approved":
                state = "approved"
            elif approval and approval["decision"] == "rejected":
                state = "rejected"
            elif estimated > 0:
                state = "awaiting_cost_approval"
            else:
                state = "ready"
            pipeline_claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE run_id=?", (row["id"],)
            ).fetchone()
            return {
                "id": row["id"],
                "production_id": row["production_id"],
                "revision_id": row["revision_id"],
                "created_at": row["created_at"],
                "requested_stages": _loads(row["requested_stages_json"], []),
                "estimated_cost": money_from_minor(estimated, row["currency"]),
                "execution_profile": row["execution_profile"] or "external",
                "pipeline_key": row["pipeline_key"],
                "pipeline_continuation": (
                    self._local_pipeline_continuation_dict(pipeline_claim)
                    if pipeline_claim is not None
                    else None
                ),
                "stage_attempts": self._stage_attempt_dicts(connection, row["id"]),
                "provider_tasks": [
                    self._provider_task_dict(provider_task)
                    for provider_task in connection.execute(
                        "SELECT * FROM provider_tasks WHERE run_id=? "
                        "ORDER BY created_at, rowid",
                        (row["id"],),
                    ).fetchall()
                ],
                "state": state,
                "latest_approval": approval,
                "immutable_digest": row["immutable_digest"],
            }
        finally:
            if close:
                connection.close()

    def create_revision_and_run(
        self,
        production_id: str,
        changes: list[Any],
        rerun_plan: dict[str, Any],
        estimated_cost_minor: int,
        currency: str,
        *,
        parent_revision_id: str | None = None,
        execution_profile: str = "external",
        pipeline_key: str | None = None,
        pipeline_request_protection: str | None = None,
        pipeline_request_ciphertext: bytes | None = None,
        rearm_pipeline_continuation: bool = False,
        detailed_test_video_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        requested_stages = (
            rerun_plan.get("requested_stages", rerun_plan.get("affected_stages"))
            if isinstance(rerun_plan, dict)
            else None
        )
        if execution_profile not in _RUN_EXECUTION_PROFILES:
            raise ValueError("execution profile is invalid")
        if not isinstance(rearm_pipeline_continuation, bool):
            raise ValueError("pipeline continuation rearm flag must be a boolean")
        if pipeline_key is not None and detailed_test_video_key is not None:
            raise ValueError("run claim keys are mutually exclusive")
        if pipeline_key is not None:
            if (
                execution_profile != "local_pipeline"
                or not isinstance(pipeline_key, str)
                or re.fullmatch(r"[0-9A-F]{64}", pipeline_key) is None
                or estimated_cost_minor != 0
                or not isinstance(requested_stages, list)
                or len(requested_stages) != len(_LOCAL_PIPELINE_ZERO_COST_STAGES)
                or set(requested_stages) != _LOCAL_PIPELINE_ZERO_COST_STAGES
            ):
                raise ValueError("pipeline key is invalid")
            pipeline_protection, pipeline_ciphertext = (
                self._validate_pipeline_request_material(
                    pipeline_request_protection, pipeline_request_ciphertext
                )
            )
        elif execution_profile == "local_pipeline":
            raise ValueError("local_pipeline runs require a pipeline key")
        else:
            if (
                pipeline_request_protection is not None
                or pipeline_request_ciphertext is not None
                or rearm_pipeline_continuation
            ):
                raise ValueError(
                    "pipeline continuation material requires a local_pipeline run"
                )
            pipeline_protection, pipeline_ciphertext = "none", None
        if detailed_test_video_key is not None:
            if (
                execution_profile != "local_sapi"
                or not isinstance(detailed_test_video_key, str)
                or re.fullmatch(r"[0-9A-F]{64}", detailed_test_video_key) is None
                or estimated_cost_minor != 0
                or not isinstance(requested_stages, list)
                or set(requested_stages) != _LOCAL_SAPI_ZERO_COST_STAGES
                or len(requested_stages) != len(_LOCAL_SAPI_ZERO_COST_STAGES)
            ):
                raise ValueError("detailed test video key is invalid")
        if execution_profile == "local_windows_capture" and (
            estimated_cost_minor != 0
            or not isinstance(requested_stages, list)
            or len(requested_stages)
            not in {
                len(_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES),
                len(_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES),
            }
            or frozenset(requested_stages)
            not in {
                frozenset(_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES),
                frozenset(_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES),
            }
        ):
            raise ValueError("local Windows capture run is invalid")
        revision_id = f"rev_{uuid.uuid4().hex}"
        run_id = f"run_{uuid.uuid4().hex}"
        timestamp = utc_now()
        safe_changes = sanitize_for_storage(changes)
        safe_plan = sanitize_for_storage(rerun_plan)
        with self.transaction() as connection:
            production = connection.execute(
                "SELECT id FROM productions WHERE id=?", (production_id,)
            ).fetchone()
            if not production:
                raise KeyError("production not found")
            if pipeline_key is not None:
                claimed = connection.execute(
                    "SELECT * FROM local_pipeline_claims "
                    "WHERE production_id=? AND pipeline_key=?",
                    (production_id, pipeline_key),
                ).fetchone()
                if claimed:
                    revision_row = connection.execute(
                        "SELECT * FROM revisions WHERE id=?", (claimed["revision_id"],)
                    ).fetchone()
                    run_row = connection.execute(
                        "SELECT * FROM runs WHERE id=?", (claimed["run_id"],)
                    ).fetchone()
                    if revision_row is None or run_row is None:
                        raise sqlite3.IntegrityError("pipeline claim provenance is missing")
                    claimed_revision = self._revision_dict(revision_row)
                    claimed_run = self._run_dict(run_row, connection)
                    if (
                        claimed_revision.get("production_id") != production_id
                        or claimed_run.get("production_id") != production_id
                        or claimed_run.get("revision_id") != claimed_revision.get("id")
                        or claimed_run.get("execution_profile") != "local_pipeline"
                        or claimed_run.get("pipeline_key") != pipeline_key
                        or claimed_run.get("estimated_cost")
                        != money_from_minor(0, claimed_run.get("estimated_cost", {}).get("currency", "USD"))
                        or set(claimed_run.get("requested_stages", []))
                        != _LOCAL_PIPELINE_ZERO_COST_STAGES
                    ):
                        raise sqlite3.IntegrityError("pipeline claim provenance is invalid")
                    if rearm_pipeline_continuation:
                        active_job = (
                            connection.execute(
                                "SELECT status FROM jobs WHERE id=?",
                                (claimed["active_job_id"],),
                            ).fetchone()
                            if claimed["active_job_id"] is not None
                            else None
                        )
                        # A duplicate HTTP request must never rewind a live
                        # provider/top owner. Explicit rearm applies only after
                        # the previous owner is terminal or absent.
                        if active_job is None or active_job["status"] not in {
                            "queued",
                            "running",
                        }:
                            next_state = (
                                "active"
                                if pipeline_protection == "dpapi-v1"
                                else "unavailable"
                            )
                            connection.execute(
                                "UPDATE local_pipeline_claims SET state=?, "
                                "request_protection=?, request_ciphertext=?, "
                                "continuation_job_id=NULL, updated_at=?, "
                                "error_code=NULL, error_message=NULL "
                                "WHERE production_id=? AND pipeline_key=? AND run_id=?",
                                (
                                    next_state,
                                    pipeline_protection,
                                    pipeline_ciphertext,
                                    timestamp,
                                    production_id,
                                    pipeline_key,
                                    claimed["run_id"],
                                ),
                            )
                            if connection.execute(
                                "SELECT changes() AS count"
                            ).fetchone()["count"] != 1:
                                raise sqlite3.IntegrityError(
                                    "pipeline continuation changed concurrently"
                                )
                            self._append_event(
                                connection,
                                "run",
                                claimed["run_id"],
                                "pipeline.continuation.armed",
                                {
                                    "production_id": production_id,
                                    "pipeline_key": pipeline_key,
                                    "state": next_state,
                                },
                                created_at=timestamp,
                            )
                            claimed_run = self._run_dict(run_row, connection)
                    return claimed_revision, claimed_run
            if detailed_test_video_key is not None:
                claimed = connection.execute(
                    "SELECT * FROM detailed_test_video_claims "
                    "WHERE production_id=? AND request_key=?",
                    (production_id, detailed_test_video_key),
                ).fetchone()
                if claimed:
                    revision_row = connection.execute(
                        "SELECT * FROM revisions WHERE id=?", (claimed["revision_id"],)
                    ).fetchone()
                    run_row = connection.execute(
                        "SELECT * FROM runs WHERE id=?", (claimed["run_id"],)
                    ).fetchone()
                    if revision_row is None or run_row is None:
                        raise sqlite3.IntegrityError(
                            "detailed test video claim provenance is missing"
                        )
                    claimed_revision = self._revision_dict(revision_row)
                    claimed_run = self._run_dict(run_row, connection)
                    if (
                        claimed_revision.get("production_id") != production_id
                        or claimed_run.get("production_id") != production_id
                        or claimed_run.get("revision_id") != claimed_revision.get("id")
                        or claimed_run.get("execution_profile") != "local_sapi"
                        or claimed_run.get("pipeline_key") is not None
                        or claimed_run.get("estimated_cost")
                        != money_from_minor(
                            0,
                            claimed_run.get("estimated_cost", {}).get(
                                "currency", "USD"
                            ),
                        )
                        or set(claimed_run.get("requested_stages", []))
                        != _LOCAL_SAPI_ZERO_COST_STAGES
                    ):
                        raise sqlite3.IntegrityError(
                            "detailed test video claim provenance is invalid"
                        )
                    return claimed_revision, claimed_run
            latest = connection.execute(
                "SELECT id, sequence FROM revisions WHERE production_id=? ORDER BY sequence DESC LIMIT 1",
                (production_id,),
            ).fetchone()
            if parent_revision_id is None and latest:
                parent_revision_id = latest["id"]
            if parent_revision_id is not None:
                parent = connection.execute(
                    "SELECT production_id FROM revisions WHERE id=?", (parent_revision_id,)
                ).fetchone()
                if not parent or parent["production_id"] != production_id:
                    raise ValueError("parent revision does not belong to production")
            sequence = (latest["sequence"] + 1) if latest else 1
            revision_payload = {
                "id": revision_id,
                "production_id": production_id,
                "parent_revision_id": parent_revision_id,
                "sequence": sequence,
                "created_at": timestamp,
                "changes": safe_changes,
                "rerun_plan": safe_plan,
            }
            revision_digest = hashlib.sha256(canonical_json(revision_payload).encode("utf-8")).hexdigest()
            connection.execute(
                "INSERT INTO revisions(id, production_id, parent_revision_id, sequence, created_at, changes_json, rerun_plan_json, immutable_digest) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    revision_id,
                    production_id,
                    parent_revision_id,
                    sequence,
                    timestamp,
                    _json(safe_changes),
                    _json(safe_plan),
                    revision_digest,
                ),
            )
            stages = safe_plan.get(
                "requested_stages", safe_plan.get("affected_stages", [])
            )
            run_payload = {
                "id": run_id,
                "production_id": production_id,
                "revision_id": revision_id,
                "created_at": timestamp,
                "requested_stages": stages,
                "estimated_cost_minor": estimated_cost_minor,
                "currency": currency,
                "execution_profile": execution_profile,
            }
            if pipeline_key is not None:
                run_payload["pipeline_key"] = pipeline_key
            run_digest = hashlib.sha256(canonical_json(run_payload).encode("utf-8")).hexdigest()
            connection.execute(
                "INSERT INTO runs(id, production_id, revision_id, created_at, requested_stages_json, estimated_cost_minor, currency, execution_profile, pipeline_key, immutable_digest) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    production_id,
                    revision_id,
                    timestamp,
                    _json(stages),
                    estimated_cost_minor,
                    currency,
                    execution_profile,
                    pipeline_key,
                    run_digest,
                ),
            )
            if pipeline_key is not None:
                connection.execute(
                    "INSERT INTO local_pipeline_claims("
                    "production_id, pipeline_key, run_id, revision_id, active_job_id, "
                    "state, request_protection, request_ciphertext, continuation_job_id, "
                    "source_job_id, source_stage_attempt_id, resume_count, created_at, "
                    "updated_at, error_code, error_message) "
                    "VALUES(?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, 0, ?, ?, NULL, NULL)",
                    (
                        production_id,
                        pipeline_key,
                        run_id,
                        revision_id,
                        (
                            "active"
                            if pipeline_protection == "dpapi-v1"
                            else "unavailable"
                        ),
                        pipeline_protection,
                        pipeline_ciphertext,
                        timestamp,
                        timestamp,
                    ),
                )
            if detailed_test_video_key is not None:
                connection.execute(
                    "INSERT INTO detailed_test_video_claims("
                    "production_id, request_key, run_id, revision_id, active_job_id, "
                    "created_at, updated_at) VALUES(?, ?, ?, ?, NULL, ?, ?)",
                    (
                        production_id,
                        detailed_test_video_key,
                        run_id,
                        revision_id,
                        timestamp,
                        timestamp,
                    ),
                )
            self._append_event(
                connection,
                "production",
                production_id,
                "revision.created",
                {
                    "revision": {**revision_payload, "immutable_digest": revision_digest},
                    "run": {
                        "id": run_id,
                        "production_id": production_id,
                        "revision_id": revision_id,
                        "created_at": timestamp,
                        "requested_stages": stages,
                        "estimated_cost": money_from_minor(estimated_cost_minor, currency),
                        "execution_profile": execution_profile,
                        "immutable_digest": run_digest,
                        **({"pipeline_key": pipeline_key} if pipeline_key is not None else {}),
                    },
                    **(
                        {
                            "detailed_test_video_claim": {
                                "schema_version": 1,
                                "production_id": production_id,
                                "request_key": detailed_test_video_key,
                                "run_id": run_id,
                                "revision_id": revision_id,
                            }
                        }
                        if detailed_test_video_key is not None
                        else {}
                    ),
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "run.created",
                {
                    "run": {
                        "id": run_id,
                        "production_id": production_id,
                        "revision_id": revision_id,
                        "created_at": timestamp,
                        "requested_stages": stages,
                        "estimated_cost": money_from_minor(estimated_cost_minor, currency),
                        "execution_profile": execution_profile,
                        "immutable_digest": run_digest,
                        **({"pipeline_key": pipeline_key} if pipeline_key is not None else {}),
                    },
                    "requires_cost_approval": estimated_cost_minor > 0,
                },
                created_at=timestamp,
            )
            revision_row = connection.execute("SELECT * FROM revisions WHERE id=?", (revision_id,)).fetchone()
            run_row = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            revision = self._revision_dict(revision_row)
            run = self._run_dict(run_row, connection)
        return revision, run

    @staticmethod
    def _stage_attempt_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "production_id": row["production_id"],
            "job_id": row["job_id"],
            "stage": row["stage"],
            "attempt": row["attempt"],
            "status": row["status"],
            "cache_key": row["cache_key"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "payload": _loads(row["payload_json"], {}),
            "result": _loads(row["result_json"], None),
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
        }

    def _stage_attempt_dicts(
        self, connection: sqlite3.Connection, run_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM stage_attempts WHERE run_id=? ORDER BY stage, attempt",
            (run_id,),
        ).fetchall()
        return [self._stage_attempt_dict(row) for row in rows]

    @staticmethod
    def _provider_task_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Return the public provider-task projection without private bytes."""

        status = row["status"]
        has_protected_request = bool(
            row["request_protection"] == "dpapi-v1"
            and isinstance(row["request_ciphertext"], bytes)
            and row["request_ciphertext"]
        )
        # A pre-issued external ID reserves one active logical submission.
        # Terminal current-state rows are intentionally retryable/resettable,
        # so they must not keep the UI or API's duplicate guard latched.
        duplicate_blocked = status not in _PROVIDER_TASK_TERMINAL_STATUSES
        resumable = status in {
            "prepared",
            "submitted",
            "recovering",
            "ambiguous",
            "recovery_blocked",
            "cancel_requested",
        }
        return {
            "id": row["id"],
            "provider": row["provider"],
            "production_id": row["production_id"],
            "run_id": row["run_id"],
            "stage": row["stage"],
            "origin_stage_attempt_id": row["origin_stage_attempt_id"],
            "current_stage_attempt_id": row["current_stage_attempt_id"],
            "current_job_id": row["current_job_id"],
            "cache_key": row["cache_key"],
            "payload_digest": row["payload_digest"],
            "provider_task_id": row["provider_task_id"],
            "status": status,
            "attempt_sequence": row["attempt_sequence"],
            "recovery_count": row["recovery_count"],
            "request_protection": row["request_protection"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "submitted_at": row["submitted_at"],
            "last_observed_at": row["last_observed_at"],
            "completed_at": row["completed_at"],
            "automatic_recovery_available": bool(
                has_protected_request
                and status
                in {
                    "prepared",
                    "submitted",
                    "recovering",
                    "ambiguous",
                    "recovery_blocked",
                    "cancel_requested",
                }
            ),
            "duplicate_submission_blocked": duplicate_blocked,
            "resumable": resumable,
            "next_action": _PROVIDER_TASK_NEXT_ACTION[status],
            "checked_at": row["last_observed_at"],
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
        }

    @staticmethod
    def _validate_provider_task_record_id(provider_task_record_id: str) -> None:
        if not isinstance(provider_task_record_id, str) or re.fullmatch(
            r"provider_task_[0-9a-f]{32}", provider_task_record_id
        ) is None:
            raise ValueError("invalid provider task record id")

    @staticmethod
    def _validate_provider_external_id(provider_task_id: str) -> None:
        if not isinstance(provider_task_id, str) or re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,128}", provider_task_id
        ) is None:
            raise ValueError("invalid provider task id")

    @staticmethod
    def _validate_provider_request_material(
        request_protection: str, request_ciphertext: bytes | None
    ) -> tuple[str, bytes | None]:
        if request_protection not in {"dpapi-v1", "none"}:
            raise ValueError("invalid provider request protection")
        if request_protection == "none":
            if request_ciphertext is not None:
                raise ValueError("unprotected provider request bytes are not accepted")
            return request_protection, None
        if not isinstance(request_ciphertext, bytes) or not (
            1 <= len(request_ciphertext) <= _MAX_PROVIDER_REQUEST_CIPHERTEXT_BYTES
        ):
            raise ValueError("invalid protected provider request")
        return request_protection, bytes(request_ciphertext)

    @staticmethod
    def _provider_execution_pair(
        connection: sqlite3.Connection,
        *,
        production_id: str,
        run_id: str,
        stage: str,
        cache_key: str,
        stage_attempt_id: str,
        job_id: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        attempt = connection.execute(
            "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
        ).fetchone()
        job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        run = connection.execute(
            "SELECT production_id FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        job_payload = _loads(job["payload_json"], {}) if job is not None else None
        if (
            attempt is None
            or job is None
            or run is None
            or run["production_id"] != production_id
            or attempt["production_id"] != production_id
            or attempt["run_id"] != run_id
            or attempt["stage"] != stage
            or attempt["cache_key"] != cache_key
            or attempt["job_id"] != job_id
            or attempt["status"] not in {"queued", "running"}
            or job["production_id"] != production_id
            or job["status"] not in {"queued", "running"}
            or not isinstance(job_payload, dict)
            or job_payload.get("run_id") != run_id
            or job_payload.get("stage") != stage
        ):
            raise ValueError("provider task execution pair is invalid")
        return attempt, job

    @staticmethod
    def _mark_pipeline_waiting_provider(
        connection: sqlite3.Connection,
        *,
        run_id: str,
        provider_job_id: str,
        timestamp: str,
    ) -> sqlite3.Row | None:
        claim = connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()
        if claim is None:
            return None
        if claim["state"] in {"succeeded", "cancel_requested", "cancelled"}:
            raise AtomicCompletionError(
                "pipeline continuation no longer accepts provider work",
                code="pipeline_continuation_not_active",
                job_status=None,
                stage_status=claim["state"],
            )
        if claim["state"] != "waiting_provider":
            connection.execute(
                "UPDATE local_pipeline_claims SET state='waiting_provider', "
                "updated_at=?, error_code=NULL, error_message=NULL "
                "WHERE production_id=? AND pipeline_key=? AND run_id=? "
                "AND state=? AND updated_at=?",
                (
                    timestamp,
                    claim["production_id"],
                    claim["pipeline_key"],
                    run_id,
                    claim["state"],
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline continuation changed before provider claim",
                    code="pipeline_continuation_changed",
                    job_status=None,
                    stage_status="unknown",
                )
            StudioDatabase._append_event(
                connection,
                "run",
                run_id,
                "pipeline.continuation.waiting_provider",
                {
                    "production_id": claim["production_id"],
                    "pipeline_key": claim["pipeline_key"],
                    "provider_job_id": provider_job_id,
                    "state": "waiting_provider",
                },
                created_at=timestamp,
            )
        return connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()

    @staticmethod
    def _checkpoint_pipeline_video_completion(
        connection: sqlite3.Connection,
        *,
        run_id: str,
        production_id: str,
        source_job_id: str,
        source_stage_attempt_id: str,
        timestamp: str,
    ) -> sqlite3.Row | None:
        claim = connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()
        if claim is None:
            return None
        if claim["production_id"] != production_id:
            raise sqlite3.IntegrityError("pipeline checkpoint production is invalid")
        top_job = (
            connection.execute(
                "SELECT * FROM jobs WHERE id=?", (claim["active_job_id"],)
            ).fetchone()
            if claim["active_job_id"] is not None
            else None
        )
        top_payload = _loads(top_job["payload_json"], {}) if top_job is not None else None
        top_is_active = bool(
            top_job is not None
            and top_job["kind"] == "local_pipeline"
            and top_job["production_id"] == production_id
            and top_job["status"] in {"queued", "running"}
            and isinstance(top_payload, dict)
            and top_payload.get("run_id") == run_id
            and top_payload.get("pipeline_key") == claim["pipeline_key"]
        )
        if claim["state"] in {"succeeded", "cancel_requested", "cancelled"}:
            next_state = claim["state"]
        elif top_is_active:
            next_state = (
                "continuing"
                if claim["continuation_job_id"] == claim["active_job_id"]
                else "active"
            )
        else:
            next_state = (
                "ready"
                if claim["request_protection"] == "dpapi-v1"
                else "unavailable"
            )
        connection.execute(
            "UPDATE local_pipeline_claims SET state=?, source_job_id=?, "
            "source_stage_attempt_id=?, updated_at=?, "
            "error_code=CASE WHEN state IN ('cancel_requested', 'cancelled') "
            "THEN error_code ELSE NULL END, "
            "error_message=CASE WHEN state IN ('cancel_requested', 'cancelled') "
            "THEN error_message ELSE NULL END "
            "WHERE production_id=? AND pipeline_key=? AND run_id=? "
            "AND state=? AND updated_at=?",
            (
                next_state,
                source_job_id,
                source_stage_attempt_id,
                timestamp,
                production_id,
                claim["pipeline_key"],
                run_id,
                claim["state"],
                claim["updated_at"],
            ),
        )
        if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
            raise AtomicCompletionError(
                "pipeline continuation changed before video checkpoint",
                code="pipeline_continuation_changed",
                job_status=(top_job["status"] if top_job is not None else None),
                stage_status="unknown",
            )
        StudioDatabase._append_event(
            connection,
            "run",
            run_id,
            "pipeline.continuation.video_checkpointed",
            {
                "production_id": production_id,
                "pipeline_key": claim["pipeline_key"],
                "source_job_id": source_job_id,
                "source_attempt_id": source_stage_attempt_id,
                "state": next_state,
            },
            created_at=timestamp,
        )
        return connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()

    @staticmethod
    def _finalize_pipeline_provider_terminal(
        connection: sqlite3.Connection,
        *,
        run_id: str,
        provider_task_record_id: str,
        provider_status: str,
        timestamp: str,
        error_code: str | None,
        error_message: str | None,
    ) -> sqlite3.Row | None:
        """Close a waiting/cancelled pipeline after a definite provider outcome."""

        if provider_status not in {"succeeded", "failed"}:
            return None
        claim = connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()
        if claim is None:
            return None
        pending_provider = connection.execute(
            "SELECT 1 FROM provider_tasks WHERE run_id=? "
            "AND status NOT IN ('succeeded', 'failed') LIMIT 1",
            (run_id,),
        ).fetchone()
        top_job = (
            connection.execute(
                "SELECT status FROM jobs WHERE id=?", (claim["active_job_id"],)
            ).fetchone()
            if claim["active_job_id"] is not None
            else None
        )
        top_is_active = bool(
            top_job is not None and top_job["status"] in {"queued", "running"}
        )
        if claim["state"] == "cancel_requested" and pending_provider is None:
            next_state = "cancelled"
            clear_private = True
        elif (
            provider_status == "failed"
            and claim["state"] == "waiting_provider"
            and pending_provider is None
            and not top_is_active
        ):
            next_state = (
                "recovery_blocked"
                if claim["request_protection"] == "dpapi-v1"
                else "unavailable"
            )
            clear_private = False
        else:
            return claim
        connection.execute(
            "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
            "request_protection=CASE WHEN ? THEN 'none' ELSE request_protection END, "
            "request_ciphertext=CASE WHEN ? THEN NULL ELSE request_ciphertext END, "
            "updated_at=?, error_code=?, error_message=? "
            "WHERE production_id=? AND pipeline_key=? AND state=? AND updated_at=?",
            (
                next_state,
                int(clear_private),
                int(clear_private),
                timestamp,
                error_code,
                error_message,
                claim["production_id"],
                claim["pipeline_key"],
                claim["state"],
                claim["updated_at"],
            ),
        )
        if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
            raise AtomicCompletionError(
                "pipeline continuation changed before provider terminal state",
                code="pipeline_continuation_changed",
                job_status=(top_job["status"] if top_job is not None else None),
                stage_status="unknown",
            )
        StudioDatabase._append_event(
            connection,
            "run",
            run_id,
            "pipeline.continuation.provider_terminal",
            {
                "production_id": claim["production_id"],
                "pipeline_key": claim["pipeline_key"],
                "state": next_state,
                "provider_task_record_id": provider_task_record_id,
                "provider_status": provider_status,
                "error_code": error_code,
            },
            created_at=timestamp,
        )
        return connection.execute(
            "SELECT * FROM local_pipeline_claims WHERE run_id=?", (run_id,)
        ).fetchone()

    def create_or_get_provider_task(
        self,
        *,
        production_id: str,
        run_id: str,
        origin_stage_attempt_id: str,
        current_stage_attempt_id: str,
        current_job_id: str,
        cache_key: str,
        payload_digest: str,
        prepared_provider_task_id: str,
        request_protection: str,
        request_ciphertext: bytes | None,
        provider: str = "comfyui",
        stage: str = "video_generation",
    ) -> tuple[dict[str, Any], bool]:
        """Create or safely rebind one logical provider operation."""

        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        validate_identifier(origin_stage_attempt_id, label="stage attempt id")
        validate_identifier(current_stage_attempt_id, label="stage attempt id")
        validate_identifier(current_job_id, label="job id")
        if provider != "comfyui" or stage != "video_generation":
            raise ValueError("unsupported provider task")
        if not isinstance(cache_key, str) or re.fullmatch(r"[0-9A-F]{64}", cache_key) is None:
            raise ValueError("invalid provider task cache key")
        if not isinstance(payload_digest, str) or re.fullmatch(
            r"[0-9A-F]{64}", payload_digest
        ) is None:
            raise ValueError("invalid provider task payload digest")
        self._validate_provider_external_id(prepared_provider_task_id)
        protection, ciphertext = self._validate_provider_request_material(
            request_protection, request_ciphertext
        )
        timestamp = utc_now()
        with self.transaction() as connection:
            current_attempt, _job = self._provider_execution_pair(
                connection,
                production_id=production_id,
                run_id=run_id,
                stage=stage,
                cache_key=cache_key,
                stage_attempt_id=current_stage_attempt_id,
                job_id=current_job_id,
            )
            origin_attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (origin_stage_attempt_id,)
            ).fetchone()
            if (
                origin_attempt is None
                or origin_attempt["run_id"] != run_id
                or origin_attempt["production_id"] != production_id
                or origin_attempt["stage"] != stage
                or origin_attempt["cache_key"] != cache_key
            ):
                raise ValueError("provider task origin attempt is invalid")
            existing = connection.execute(
                "SELECT * FROM provider_tasks WHERE provider=? AND run_id=? "
                "AND cache_key=? AND payload_digest=?",
                (provider, run_id, cache_key, payload_digest),
            ).fetchone()
            created = existing is None
            event_type: str
            if existing is None:
                record_id = f"provider_task_{uuid.uuid4().hex}"
                connection.execute(
                    "INSERT INTO provider_tasks("
                    "id, provider, production_id, run_id, stage, origin_stage_attempt_id, "
                    "current_stage_attempt_id, current_job_id, cache_key, payload_digest, "
                    "provider_task_id, status, attempt_sequence, recovery_count, request_protection, "
                    "request_ciphertext, created_at, updated_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', 1, 0, ?, ?, ?, ?)",
                    (
                        record_id,
                        provider,
                        production_id,
                        run_id,
                        stage,
                        origin_stage_attempt_id,
                        current_stage_attempt_id,
                        current_job_id,
                        cache_key,
                        payload_digest,
                        prepared_provider_task_id,
                        protection,
                        ciphertext,
                        timestamp,
                        timestamp,
                    ),
                )
                event_type = "video_generation.provider_task.prepared"
            else:
                record_id = existing["id"]
                if existing["production_id"] != production_id or existing["stage"] != stage:
                    raise ValueError("provider task logical identity is inconsistent")
                if existing["status"] in _PROVIDER_TASK_TERMINAL_STATUSES:
                    connection.execute(
                        "UPDATE provider_tasks SET origin_stage_attempt_id=?, "
                        "current_stage_attempt_id=?, current_job_id=?, "
                        "provider_task_id=?, status='prepared', "
                        "attempt_sequence=attempt_sequence+1, recovery_count=0, "
                        "request_protection=?, request_ciphertext=?, updated_at=?, "
                        "submitted_at=NULL, last_observed_at=NULL, completed_at=NULL, "
                        "error_code=NULL, error_message=NULL "
                        "WHERE id=? AND status IN ('succeeded', 'failed')",
                        (
                            origin_stage_attempt_id,
                            current_stage_attempt_id,
                            current_job_id,
                            prepared_provider_task_id,
                            protection,
                            ciphertext,
                            timestamp,
                            record_id,
                        ),
                    )
                    event_type = "video_generation.provider_task.reset"
                elif existing["provider_task_id"] != prepared_provider_task_id:
                    raise ValueError("prepared provider task id changed")
                elif (
                    existing["current_stage_attempt_id"] == current_stage_attempt_id
                    and existing["current_job_id"] == current_job_id
                ):
                    self._mark_pipeline_waiting_provider(
                        connection,
                        run_id=run_id,
                        provider_job_id=current_job_id,
                        timestamp=timestamp,
                    )
                    return self._provider_task_dict(existing), False
                else:
                    if (
                        existing["current_stage_attempt_id"] is not None
                        or existing["current_job_id"] is not None
                    ):
                        owner_job = connection.execute(
                            "SELECT status FROM jobs WHERE id=?",
                            (existing["current_job_id"],),
                        ).fetchone()
                        if owner_job is not None and owner_job["status"] in {
                            "queued",
                            "running",
                        }:
                            raise ValueError("provider task is already claimed")
                    next_protection = existing["request_protection"]
                    next_ciphertext = existing["request_ciphertext"]
                    if next_protection == "none" and protection == "dpapi-v1":
                        next_protection = protection
                        next_ciphertext = ciphertext
                    connection.execute(
                        "UPDATE provider_tasks SET current_stage_attempt_id=?, current_job_id=?, "
                        "request_protection=?, request_ciphertext=?, updated_at=? WHERE id=?",
                        (
                            current_stage_attempt_id,
                            current_job_id,
                            next_protection,
                            next_ciphertext,
                            timestamp,
                            record_id,
                        ),
                    )
                    event_type = "video_generation.provider_task.rebound"
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise ValueError("provider task changed concurrently")
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (record_id,)
            ).fetchone()
            assert row is not None
            self._mark_pipeline_waiting_provider(
                connection,
                run_id=run_id,
                provider_job_id=current_job_id,
                timestamp=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                event_type,
                {
                    "provider_task_record_id": record_id,
                    "provider": provider,
                    "production_id": production_id,
                    "attempt_id": current_attempt["id"],
                    "job_id": current_job_id,
                    "cache_key": cache_key,
                    "payload_digest": payload_digest,
                    "status": row["status"],
                    "attempt_sequence": row["attempt_sequence"],
                },
                created_at=timestamp,
            )
            return self._provider_task_dict(row), created

    def get_provider_task(self, provider_task_record_id: str) -> dict[str, Any] | None:
        self._validate_provider_task_record_id(provider_task_record_id)
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
        return self._provider_task_dict(row) if row else None

    def get_provider_task_recovery_material(
        self, provider_task_record_id: str
    ) -> dict[str, Any] | None:
        """Return one private recovery record for in-process service use only."""

        self._validate_provider_task_record_id(provider_task_record_id)
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
        if row is None:
            return None
        result = self._provider_task_dict(row)
        raw_ciphertext = row["request_ciphertext"]
        result["request_ciphertext"] = (
            bytes(raw_ciphertext) if isinstance(raw_ciphertext, bytes) else None
        )
        return result

    def list_provider_tasks(
        self, *, run_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if run_id is not None:
            validate_identifier(run_id, label="run id")
        safe_limit = max(1, min(int(limit), 1000))
        with self.session() as connection:
            if run_id is None:
                rows = connection.execute(
                    "SELECT * FROM provider_tasks ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM provider_tasks WHERE run_id=? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (run_id, safe_limit),
                ).fetchall()
        return [self._provider_task_dict(row) for row in rows]

    def list_recoverable_provider_tasks(self, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM provider_tasks WHERE status IN "
                "('prepared', 'submitted', 'ambiguous', 'recovery_blocked', 'cancel_requested') "
                "AND current_stage_attempt_id IS NULL AND current_job_id IS NULL "
                "ORDER BY updated_at, id LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [self._provider_task_dict(row) for row in rows]

    def record_provider_submission(
        self, provider_task_record_id: str, provider_task_id: str
    ) -> dict[str, Any]:
        self._validate_provider_task_record_id(provider_task_record_id)
        self._validate_provider_external_id(provider_task_id)
        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            if row is None:
                raise KeyError("provider task not found")
            if row["provider_task_id"] != provider_task_id:
                raise ValueError("provider task id changed")
            if (
                row["status"] in {"submitted", "recovering"}
                and row["submitted_at"] is not None
            ):
                return self._provider_task_dict(row)
            if row["status"] not in {
                "prepared",
                "submitted",
                "recovering",
                "ambiguous",
                "recovery_blocked",
            }:
                raise ValueError("provider task is not accepting a submission")
            connection.execute(
                "UPDATE provider_tasks SET status='submitted', "
                "submitted_at=COALESCE(submitted_at, ?), updated_at=?, completed_at=NULL, "
                "error_code=NULL, error_message=NULL WHERE id=? AND provider_task_id=? "
                "AND status IN ('prepared', 'submitted', 'recovering', 'ambiguous', 'recovery_blocked') "
                "AND (status!='submitted' OR submitted_at IS NULL)",
                (timestamp, timestamp, provider_task_record_id, provider_task_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise ValueError("provider task changed concurrently")
            updated = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            assert updated is not None
            # submitted_at is cleared only when a terminal current-state row
            # is reset for a new provider attempt.  A recovery transition may
            # revisit `submitted` for the same external ID, but must not append
            # a second acceptance event for that provider attempt.
            if row["submitted_at"] is None:
                self._append_event(
                    connection,
                    "run",
                    updated["run_id"],
                    "video_generation.provider_submitted",
                    {
                        "attempt_id": updated["current_stage_attempt_id"]
                        or updated["origin_stage_attempt_id"],
                        "production_id": updated["production_id"],
                        "provider": updated["provider"],
                        "provider_task_record_id": updated["id"],
                        "provider_task_id": provider_task_id,
                        "attempt_sequence": updated["attempt_sequence"],
                        "cache_key": updated["cache_key"],
                    },
                    created_at=timestamp,
                )
            return self._provider_task_dict(updated)

    def claim_provider_task_recovery(
        self,
        provider_task_record_id: str,
        *,
        expected_updated_at: str,
        current_stage_attempt_id: str,
        current_job_id: str,
    ) -> dict[str, Any] | None:
        self._validate_provider_task_record_id(provider_task_record_id)
        validate_identifier(current_stage_attempt_id, label="stage attempt id")
        validate_identifier(current_job_id, label="job id")
        if not isinstance(expected_updated_at, str) or not expected_updated_at:
            raise ValueError("expected provider task timestamp is required")
        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            if row is None:
                raise KeyError("provider task not found")
            self._provider_execution_pair(
                connection,
                production_id=row["production_id"],
                run_id=row["run_id"],
                stage=row["stage"],
                cache_key=row["cache_key"],
                stage_attempt_id=current_stage_attempt_id,
                job_id=current_job_id,
            )
            connection.execute(
                "UPDATE provider_tasks SET status='recovering', "
                "current_stage_attempt_id=?, current_job_id=?, recovery_count=recovery_count+1, "
                "updated_at=?, completed_at=NULL, error_code=NULL, error_message=NULL "
                "WHERE id=? AND updated_at=? "
                "AND status IN ('prepared', 'submitted', 'ambiguous', 'recovery_blocked') "
                "AND current_stage_attempt_id IS NULL AND current_job_id IS NULL",
                (
                    current_stage_attempt_id,
                    current_job_id,
                    timestamp,
                    provider_task_record_id,
                    expected_updated_at,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                return None
            updated = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            assert updated is not None
            self._mark_pipeline_waiting_provider(
                connection,
                run_id=updated["run_id"],
                provider_job_id=current_job_id,
                timestamp=timestamp,
            )
            self._append_event(
                connection,
                "run",
                updated["run_id"],
                "video_generation.provider_recovery_claimed",
                {
                    "provider_task_record_id": updated["id"],
                    "production_id": updated["production_id"],
                    "provider_task_id": updated["provider_task_id"],
                    "attempt_id": current_stage_attempt_id,
                    "job_id": current_job_id,
                    "cache_key": updated["cache_key"],
                    "recovery_count": updated["recovery_count"],
                },
                created_at=timestamp,
            )
            return self._provider_task_dict(updated)

    def abort_provider_task_recovery_admission(
        self,
        provider_task_record_id: str,
        *,
        current_stage_attempt_id: str,
        current_job_id: str,
        error_code: str = "job_setup_failed",
        error_message: str = "The background job could not be prepared.",
    ) -> dict[str, Any]:
        """Atomically fail a recovery pair that never entered its worker queue.

        A CAS loser owns only its queued job/attempt, while a queue insertion
        failure also owns the provider task in ``recovering`` state.  This
        transaction closes the exact queued pair in both cases and releases
        the provider only when the tuple proves ownership.  The protected
        request and external marker remain available for another exact
        reconciliation; no provider POST occurs here.
        """

        self._validate_provider_task_record_id(provider_task_record_id)
        validate_identifier(current_stage_attempt_id, label="stage attempt id")
        validate_identifier(current_job_id, label="job id")
        timestamp = utc_now()
        safe_code = str(sanitize_for_storage(error_code or "job_setup_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        with self.transaction() as connection:
            provider_task = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?",
                (provider_task_record_id,),
            ).fetchone()
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (current_job_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?",
                (current_stage_attempt_id,),
            ).fetchone()
            if provider_task is None:
                raise KeyError("provider task not found")
            if job is None:
                raise KeyError("job not found")
            if attempt is None:
                raise KeyError("stage attempt not found")
            if (
                job["kind"] != "local_video_generation"
                or job["status"] != "queued"
                or attempt["status"] != "queued"
                or attempt["job_id"] != current_job_id
                or attempt["production_id"] != provider_task["production_id"]
                or attempt["run_id"] != provider_task["run_id"]
                or attempt["stage"] != provider_task["stage"]
                or attempt["cache_key"] != provider_task["cache_key"]
                or job["production_id"] != provider_task["production_id"]
            ):
                raise AtomicCompletionError(
                    "provider recovery admission is no longer queued",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )
            owns_stage = (
                provider_task["current_stage_attempt_id"]
                == current_stage_attempt_id
            )
            owns_job = provider_task["current_job_id"] == current_job_id
            if owns_stage != owns_job:
                raise sqlite3.IntegrityError(
                    "provider recovery admission owner is incomplete"
                )
            owns_provider = owns_stage and owns_job
            if owns_provider and provider_task["status"] != "recovering":
                raise AtomicCompletionError(
                    "provider recovery admission state changed",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )

            connection.execute(
                "UPDATE stage_attempts SET status='failed', completed_at=?, "
                "result_json=NULL, error_code=?, error_message=? "
                "WHERE id=? AND status='queued'",
                (
                    timestamp,
                    safe_code,
                    safe_message,
                    current_stage_attempt_id,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "recovery attempt changed before admission abort",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status="unknown",
                )
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, current_job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "recovery job changed before admission abort",
                    code="atomic_failure_not_active",
                    job_status="unknown",
                    stage_status="failed",
                )
            if owns_provider:
                connection.execute(
                    "UPDATE provider_tasks SET status='recovery_blocked', "
                    "current_stage_attempt_id=NULL, current_job_id=NULL, "
                    "updated_at=?, completed_at=NULL, error_code=?, error_message=? "
                    "WHERE id=? AND status='recovering' "
                    "AND current_stage_attempt_id=? AND current_job_id=?",
                    (
                        timestamp,
                        safe_code,
                        safe_message,
                        provider_task_record_id,
                        current_stage_attempt_id,
                        current_job_id,
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "provider changed before admission abort",
                        code="atomic_failure_not_active",
                        job_status="failed",
                        stage_status="failed",
                    )

            self._append_event(
                connection,
                "run",
                attempt["run_id"],
                "stage.attempt.failed",
                {
                    "attempt_id": attempt["id"],
                    "production_id": attempt["production_id"],
                    "stage": attempt["stage"],
                    "attempt": attempt["attempt"],
                    "cache_key": attempt["cache_key"],
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "job",
                current_job_id,
                "job.failed",
                {
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            if owns_provider:
                self._append_event(
                    connection,
                    "run",
                    provider_task["run_id"],
                    "video_generation.provider_state_changed",
                    {
                        "provider_task_record_id": provider_task["id"],
                        "production_id": provider_task["production_id"],
                        "provider": provider_task["provider"],
                        "provider_task_id": provider_task["provider_task_id"],
                        "attempt_id": current_stage_attempt_id,
                        "job_id": current_job_id,
                        "cache_key": provider_task["cache_key"],
                        "attempt_sequence": provider_task["attempt_sequence"],
                        "status": "recovery_blocked",
                        "error_code": safe_code,
                    },
                    created_at=timestamp,
                )
            updated = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?",
                (provider_task_record_id,),
            ).fetchone()
            assert updated is not None
            return self._provider_task_dict(updated)

    def record_provider_observation(
        self, provider_task_record_id: str
    ) -> dict[str, Any]:
        """Persist the time of an actual provider GET without changing state order."""

        self._validate_provider_task_record_id(provider_task_record_id)
        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            if row is None:
                raise KeyError("provider task not found")
            connection.execute(
                "UPDATE provider_tasks SET last_observed_at=? WHERE id=?",
                (timestamp, provider_task_record_id),
            )
            updated = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            assert updated is not None
            return self._provider_task_dict(updated)

    def mark_provider_task_state(
        self,
        provider_task_record_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        self._validate_provider_task_record_id(provider_task_record_id)
        if status not in _PROVIDER_TASK_STATUSES or status == "succeeded":
            raise ValueError("unsupported provider task state")
        safe_code = str(sanitize_for_storage(error_code or ""))[:128] or None
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            if row is None:
                raise KeyError("provider task not found")
            if row["status"] == status:
                return self._provider_task_dict(row)
            if row["status"] in _PROVIDER_TASK_TERMINAL_STATUSES:
                raise ValueError("provider task is terminal")
            if status not in _PROVIDER_TASK_STATE_TRANSITIONS[row["status"]]:
                raise ValueError("provider task state transition is invalid")
            if status == "submitted" and row["provider_task_id"] is None:
                raise ValueError("submitted provider task id is absent")
            if status == "recovering" and (
                row["current_stage_attempt_id"] is None or row["current_job_id"] is None
            ):
                raise ValueError("recovering provider task owner is absent")
            terminal_at = timestamp if status == "failed" else None
            effective_code = safe_code if status in {
                "failed",
                "ambiguous",
                "recovery_blocked",
                "cancel_requested",
            } else None
            effective_message = safe_message if effective_code else None
            release_owner = status in {
                "ambiguous",
                "recovery_blocked",
                "cancel_requested",
                "failed",
            }
            connection.execute(
                "UPDATE provider_tasks SET status=?, updated_at=?, completed_at=?, "
                "error_code=?, error_message=?, "
                "current_stage_attempt_id=CASE WHEN ? THEN NULL ELSE current_stage_attempt_id END, "
                "current_job_id=CASE WHEN ? THEN NULL ELSE current_job_id END, "
                "request_ciphertext=CASE WHEN ? THEN NULL ELSE request_ciphertext END "
                "WHERE id=? AND status NOT IN ('succeeded', 'failed')",
                (
                    status,
                    timestamp,
                    terminal_at,
                    effective_code,
                    effective_message,
                    int(release_owner),
                    int(release_owner),
                    int(status == "failed"),
                    provider_task_record_id,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise ValueError("provider task changed concurrently")
            updated = connection.execute(
                "SELECT * FROM provider_tasks WHERE id=?", (provider_task_record_id,)
            ).fetchone()
            assert updated is not None
            if status == "failed":
                self._finalize_pipeline_provider_terminal(
                    connection,
                    run_id=updated["run_id"],
                    provider_task_record_id=updated["id"],
                    provider_status="failed",
                    timestamp=timestamp,
                    error_code=effective_code,
                    error_message=effective_message,
                )
            self._append_event(
                connection,
                "run",
                updated["run_id"],
                "video_generation.provider_state_changed",
                {
                    "provider_task_record_id": updated["id"],
                    "production_id": updated["production_id"],
                    "provider_task_id": updated["provider_task_id"],
                    "status": status,
                    "cache_key": updated["cache_key"],
                    "error_code": effective_code,
                    "error_message": effective_message,
                },
                created_at=timestamp,
            )
            return self._provider_task_dict(updated)

    @staticmethod
    def _windows_capture_consent_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Return consent metadata without either persisted one-way binding."""

        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "production_id": row["production_id"],
            "request_settings_digest": row["request_settings_digest"],
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "invalidated_at": row["invalidated_at"],
            "consumed_at": row["consumed_at"],
            "consumed_job_id": row["consumed_job_id"],
            "consumed_stage_attempt_id": row["consumed_stage_attempt_id"],
        }

    @staticmethod
    def _validate_windows_capture_consent_binding(
        *,
        production_id: str,
        run_id: str,
        token_digest: str,
        session_binding_digest: str,
        request_settings_digest: str,
    ) -> None:
        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        for label, value in (
            ("consent token digest", token_digest),
            ("session binding digest", session_binding_digest),
            ("request settings digest", request_settings_digest),
        ):
            if not isinstance(value, str) or re.fullmatch(r"[0-9A-F]{64}", value) is None:
                raise ValueError(f"invalid Windows capture {label}")

    def issue_windows_capture_consent_intent(
        self,
        *,
        production_id: str,
        run_id: str,
        token_digest: str,
        session_binding_digest: str,
        request_settings_digest: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        """Persist one short-lived capture intent without the bearer token."""

        self._validate_windows_capture_consent_binding(
            production_id=production_id,
            run_id=run_id,
            token_digest=token_digest,
            session_binding_digest=session_binding_digest,
            request_settings_digest=request_settings_digest,
        )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= 300
        ):
            raise ValueError("Windows capture consent TTL is invalid")
        intent_id = f"capture_consent_{uuid.uuid4().hex}"
        issued_value = datetime.now(timezone.utc)
        issued_at = issued_value.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        expires_at = (
            issued_value + timedelta(seconds=ttl_seconds)
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.transaction() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["production_id"] != production_id
                or run["execution_profile"] != "local_windows_capture"
                or "screen_capture"
                not in _loads(run["requested_stages_json"], [])
            ):
                raise ValueError("local Windows capture run is invalid")
            connection.execute(
                "INSERT INTO windows_capture_consent_intents("
                "id, token_digest, session_binding_digest, run_id, production_id, "
                "request_settings_digest, issued_at, expires_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent_id,
                    token_digest,
                    session_binding_digest,
                    run_id,
                    production_id,
                    request_settings_digest,
                    issued_at,
                    expires_at,
                ),
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "windows_capture.consent.issued",
                {
                    "consent_intent_id": intent_id,
                    "production_id": production_id,
                    "request_settings_digest": request_settings_digest,
                    "issued_at": issued_at,
                    "expires_at": expires_at,
                },
                created_at=issued_at,
            )
            row = connection.execute(
                "SELECT * FROM windows_capture_consent_intents WHERE id=?",
                (intent_id,),
            ).fetchone()
            assert row is not None
            return self._windows_capture_consent_dict(row)

    def _consumed_windows_capture_job(
        self,
        connection: sqlite3.Connection,
        consent: sqlite3.Row,
        *,
        production_id: str,
        run_id: str,
        request_settings_digest: str,
    ) -> dict[str, Any]:
        job = connection.execute(
            "SELECT * FROM jobs WHERE id=?", (consent["consumed_job_id"],)
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM stage_attempts WHERE id=?",
            (consent["consumed_stage_attempt_id"],),
        ).fetchone()
        if job is None or attempt is None:
            raise sqlite3.IntegrityError(
                "Windows capture consent is missing its admitted lineage"
            )
        job_payload = _loads(job["payload_json"], {})
        attempt_payload = _loads(attempt["payload_json"], {})
        if (
            consent["production_id"] != production_id
            or consent["run_id"] != run_id
            or consent["request_settings_digest"] != request_settings_digest
            or job["kind"] != "local_windows_capture"
            or job["production_id"] != production_id
            or not isinstance(job_payload, dict)
            or job_payload.get("run_id") != run_id
            or job_payload.get("production_id") != production_id
            or job_payload.get("stage") != "screen_capture"
            or job_payload.get("execution_profile") != "local_windows_capture"
            or job_payload.get("consent_intent_id") != consent["id"]
            or job_payload.get("request_settings_digest")
            != request_settings_digest
            or job_payload.get("stage_attempt_id") != attempt["id"]
            or attempt["job_id"] != job["id"]
            or attempt["run_id"] != run_id
            or attempt["production_id"] != production_id
            or attempt["stage"] != "screen_capture"
            or not isinstance(attempt_payload, dict)
            or attempt_payload.get("execution_profile")
            != "local_windows_capture"
            or attempt_payload.get("consent_intent_id") != consent["id"]
            or attempt_payload.get("request_settings_digest")
            != request_settings_digest
            or attempt_payload.get("capture_key") != attempt["cache_key"]
            or job_payload.get("capture_key") != attempt["cache_key"]
            or attempt_payload.get("request_digest")
            != job_payload.get("request_digest")
        ):
            raise sqlite3.IntegrityError(
                "Windows capture consent lineage is invalid"
            )
        output = self._job_dict(job)
        output["stage_attempt_id"] = attempt["id"]
        output["capture_key"] = attempt["cache_key"]
        output["request_digest"] = job_payload.get("request_digest")
        output["request_settings_digest"] = request_settings_digest
        output["consent_intent_id"] = consent["id"]
        return output

    def windows_capture_consent_state(
        self,
        *,
        production_id: str,
        run_id: str,
        token_digest: str,
        session_binding_digest: str,
        request_settings_digest: str,
    ) -> dict[str, Any]:
        """Resolve one token without consuming it or exposing stored digests."""

        self._validate_windows_capture_consent_binding(
            production_id=production_id,
            run_id=run_id,
            token_digest=token_digest,
            session_binding_digest=session_binding_digest,
            request_settings_digest=request_settings_digest,
        )
        timestamp = utc_now()
        with self.session() as connection:
            consent = connection.execute(
                "SELECT * FROM windows_capture_consent_intents WHERE token_digest=?",
                (token_digest,),
            ).fetchone()
            if (
                consent is None
                or consent["production_id"] != production_id
                or consent["run_id"] != run_id
                or consent["session_binding_digest"] != session_binding_digest
                or consent["request_settings_digest"]
                != request_settings_digest
            ):
                return {"state": "invalid"}
            if consent["consumed_job_id"] is not None:
                return {
                    "state": "consumed",
                    "consent_intent": self._windows_capture_consent_dict(consent),
                    "job": self._consumed_windows_capture_job(
                        connection,
                        consent,
                        production_id=production_id,
                        run_id=run_id,
                        request_settings_digest=request_settings_digest,
                    ),
                }
            if consent["invalidated_at"] is not None:
                return {"state": "invalid"}
            if consent["expires_at"] <= timestamp:
                return {"state": "expired"}
            return {
                "state": "ready",
                "consent_intent": self._windows_capture_consent_dict(consent),
            }

    def consume_windows_capture_consent_and_create_job(
        self,
        *,
        production_id: str,
        run_id: str,
        token_digest: str,
        session_binding_digest: str,
        request_settings_digest: str,
        capture_key: str,
        attempt_payload: Any,
        job_payload: Any,
    ) -> tuple[dict[str, Any], bool]:
        """Consume consent and create its exact attempt/job in one transaction."""

        self._validate_windows_capture_consent_binding(
            production_id=production_id,
            run_id=run_id,
            token_digest=token_digest,
            session_binding_digest=session_binding_digest,
            request_settings_digest=request_settings_digest,
        )
        if not isinstance(capture_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", capture_key
        ) is None:
            raise ValueError("invalid Windows capture key")
        safe_attempt_payload = sanitize_for_storage(attempt_payload)
        safe_job_payload = sanitize_for_storage(job_payload)
        forbidden = {"consent_token", "token_digest", "session_binding_digest"}
        if (
            not isinstance(safe_attempt_payload, dict)
            or not isinstance(safe_job_payload, dict)
            or forbidden.intersection(safe_attempt_payload)
            or forbidden.intersection(safe_job_payload)
            or safe_attempt_payload.get("execution_profile")
            != "local_windows_capture"
            or safe_attempt_payload.get("capture_key") != capture_key
            or safe_attempt_payload.get("request_settings_digest")
            != request_settings_digest
            or safe_job_payload.get("production_id") != production_id
            or safe_job_payload.get("run_id") != run_id
            or safe_job_payload.get("stage") != "screen_capture"
            or safe_job_payload.get("execution_profile")
            != "local_windows_capture"
            or safe_job_payload.get("capture_key") != capture_key
            or safe_job_payload.get("request_settings_digest")
            != request_settings_digest
            or safe_attempt_payload.get("request_digest")
            != safe_job_payload.get("request_digest")
        ):
            raise ValueError("invalid Windows capture admission payload")

        timestamp = utc_now()
        with self.transaction() as connection:
            consent = connection.execute(
                "SELECT * FROM windows_capture_consent_intents WHERE token_digest=?",
                (token_digest,),
            ).fetchone()
            if (
                consent is None
                or consent["production_id"] != production_id
                or consent["run_id"] != run_id
                or consent["session_binding_digest"] != session_binding_digest
                or consent["request_settings_digest"]
                != request_settings_digest
            ):
                raise WindowsCaptureConsentError(
                    "A fresh Windows capture consent is required.",
                    code="windows_capture_consent_invalid",
                )
            if consent["consumed_job_id"] is not None:
                return (
                    self._consumed_windows_capture_job(
                        connection,
                        consent,
                        production_id=production_id,
                        run_id=run_id,
                        request_settings_digest=request_settings_digest,
                    ),
                    False,
                )
            if consent["invalidated_at"] is not None:
                raise WindowsCaptureConsentError(
                    "A fresh Windows capture consent is required.",
                    code="windows_capture_consent_invalid",
                )
            if consent["expires_at"] <= timestamp:
                raise WindowsCaptureConsentError(
                    "The Windows capture consent expired. Confirm capture again.",
                    code="windows_capture_consent_expired",
                )
            active = connection.execute(
                "SELECT id FROM jobs WHERE kind='local_windows_capture' "
                "AND status IN ('queued', 'running') ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if active is not None:
                raise WindowsCaptureConsentError(
                    "Another Windows capture is already active.",
                    code="windows_capture_busy",
                )
            run = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["production_id"] != production_id
                or run["execution_profile"] != "local_windows_capture"
                or "screen_capture"
                not in _loads(run["requested_stages_json"], [])
            ):
                raise WindowsCaptureConsentError(
                    "This run cannot admit Windows capture.",
                    code="windows_capture_consent_invalid",
                )

            attempt_id = f"attempt_{uuid.uuid4().hex}"
            job_id = f"job_{uuid.uuid4().hex}"
            stored_attempt_payload = {
                **safe_attempt_payload,
                "consent_intent_id": consent["id"],
            }
            stored_job_payload = {
                **safe_job_payload,
                "consent_intent_id": consent["id"],
                "stage_attempt_id": attempt_id,
            }
            latest = connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS attempt FROM stage_attempts "
                "WHERE run_id=? AND stage='screen_capture'",
                (run_id,),
            ).fetchone()
            attempt_number = int(latest["attempt"]) + 1
            connection.execute(
                "INSERT INTO jobs(id, kind, status, production_id, created_at, payload_json) "
                "VALUES(?, 'local_windows_capture', 'queued', ?, ?, ?)",
                (job_id, production_id, timestamp, _json(stored_job_payload)),
            )
            connection.execute(
                "INSERT INTO stage_attempts(id, run_id, production_id, job_id, stage, "
                "attempt, status, cache_key, created_at, payload_json) "
                "VALUES(?, ?, ?, ?, 'screen_capture', ?, 'queued', ?, ?, ?)",
                (
                    attempt_id,
                    run_id,
                    production_id,
                    job_id,
                    attempt_number,
                    capture_key,
                    timestamp,
                    _json(stored_attempt_payload),
                ),
            )
            connection.execute(
                "UPDATE windows_capture_consent_intents SET consumed_at=?, "
                "consumed_job_id=?, consumed_stage_attempt_id=? WHERE id=? "
                "AND consumed_job_id IS NULL AND invalidated_at IS NULL AND expires_at>?",
                (timestamp, job_id, attempt_id, consent["id"], timestamp),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise WindowsCaptureConsentError(
                    "The Windows capture consent could not be consumed.",
                    code="windows_capture_consent_invalid",
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.queued",
                {"kind": "local_windows_capture", "production_id": production_id},
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "stage.attempt.queued",
                {
                    "attempt_id": attempt_id,
                    "production_id": production_id,
                    "stage": "screen_capture",
                    "attempt": attempt_number,
                    "cache_key": capture_key,
                    "payload": stored_attempt_payload,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "stage.attempt.job_linked",
                {
                    "attempt_id": attempt_id,
                    "production_id": production_id,
                    "stage": "screen_capture",
                    "attempt": attempt_number,
                    "cache_key": capture_key,
                    "job_id": job_id,
                    "linked_at": timestamp,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "windows_capture.consent.consumed",
                {
                    "consent_intent_id": consent["id"],
                    "production_id": production_id,
                    "request_settings_digest": request_settings_digest,
                    "job_id": job_id,
                    "stage_attempt_id": attempt_id,
                    "consumed_at": timestamp,
                },
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert row is not None
            output = self._job_dict(row)
            output["stage_attempt_id"] = attempt_id
            output["capture_key"] = capture_key
            output["request_digest"] = stored_job_payload.get("request_digest")
            output["request_settings_digest"] = request_settings_digest
            output["consent_intent_id"] = consent["id"]
            return output, True

    def abort_windows_capture_admission(
        self,
        job_id: str,
        stage_attempt_id: str,
        *,
        error_code: str = "job_setup_failed",
        error_message: str = "The background job could not be prepared.",
    ) -> dict[str, Any]:
        """Retire an already-consumed consent whose queue admission failed."""

        validate_identifier(job_id, label="job id")
        validate_identifier(stage_attempt_id, label="stage attempt id")
        timestamp = utc_now()
        safe_code = str(sanitize_for_storage(error_code or "job_setup_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            if job is None or attempt is None:
                raise KeyError("Windows capture admission is missing")
            payload = _loads(job["payload_json"], {})
            consent_id = payload.get("consent_intent_id") if isinstance(payload, dict) else None
            consent = connection.execute(
                "SELECT * FROM windows_capture_consent_intents WHERE id=?",
                (consent_id,),
            ).fetchone()
            if (
                job["kind"] != "local_windows_capture"
                or job["status"] != "queued"
                or attempt["status"] != "queued"
                or attempt["job_id"] != job_id
                or attempt["stage"] != "screen_capture"
                or consent is None
                or consent["consumed_job_id"] != job_id
                or consent["consumed_stage_attempt_id"] != stage_attempt_id
            ):
                raise AtomicCompletionError(
                    "Windows capture admission is no longer queued",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )
            connection.execute(
                "UPDATE stage_attempts SET status='failed', completed_at=?, "
                "result_json=NULL, error_code=?, error_message=? "
                "WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, stage_attempt_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError("Windows capture attempt changed")
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError("Windows capture job changed")
            self._append_event(
                connection,
                "run",
                attempt["run_id"],
                "stage.attempt.failed",
                {
                    "attempt_id": attempt["id"],
                    "production_id": attempt["production_id"],
                    "stage": attempt["stage"],
                    "attempt": attempt["attempt"],
                    "cache_key": attempt["cache_key"],
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.failed",
                {
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            updated = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert updated is not None
            output = self._job_dict(updated)
            output["stage_attempt_id"] = stage_attempt_id
            output["capture_key"] = attempt["cache_key"]
            output["request_digest"] = payload.get("request_digest")
            output["request_settings_digest"] = payload.get(
                "request_settings_digest"
            )
            output["consent_intent_id"] = consent_id
            return output

    def create_stage_attempt(
        self,
        run_id: str,
        stage: str,
        cache_key: str,
        payload: Any,
    ) -> dict[str, Any]:
        """Append a queued stage attempt; never reuse a prior attempt row."""

        attempt_id = f"attempt_{uuid.uuid4().hex}"
        timestamp = utc_now()
        safe_payload = sanitize_for_storage(payload)
        with self.transaction() as connection:
            run = connection.execute(
                "SELECT id, production_id FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if not run:
                raise KeyError("run not found")
            latest = connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS attempt FROM stage_attempts "
                "WHERE run_id=? AND stage=?",
                (run_id, stage),
            ).fetchone()
            attempt_number = int(latest["attempt"]) + 1
            connection.execute(
                "INSERT INTO stage_attempts(id, run_id, production_id, stage, attempt, status, cache_key, created_at, payload_json) "
                "VALUES(?, ?, ?, ?, ?, 'queued', ?, ?, ?)",
                (
                    attempt_id,
                    run_id,
                    run["production_id"],
                    stage,
                    attempt_number,
                    cache_key,
                    timestamp,
                    _json(safe_payload),
                ),
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "stage.attempt.queued",
                {
                    "attempt_id": attempt_id,
                    "production_id": run["production_id"],
                    "stage": stage,
                    "attempt": attempt_number,
                    "cache_key": cache_key,
                    "payload": safe_payload,
                },
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            assert row is not None
            result = self._stage_attempt_dict(row)
        return result

    def link_stage_attempt_job(self, attempt_id: str, job_id: str) -> dict[str, Any]:
        """Persist the one job that executes an already-created attempt."""

        if not re.fullmatch(r"attempt_[0-9a-f]{32}", attempt_id):
            raise ValueError("invalid stage attempt id")
        if not re.fullmatch(r"job_[0-9a-f]{32}", job_id):
            raise ValueError("invalid job id")
        timestamp = utc_now()
        with self.transaction() as connection:
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not attempt or not job:
                raise KeyError("stage attempt or job not found")
            job_payload = _loads(job["payload_json"], {})
            if (
                job["production_id"] != attempt["production_id"]
                or not isinstance(job_payload, dict)
                or job_payload.get("run_id") != attempt["run_id"]
                or job_payload.get("stage") != attempt["stage"]
            ):
                raise ValueError("job does not belong to the stage attempt")
            if attempt["job_id"] not in {None, job_id}:
                raise ValueError("stage attempt is already linked to another job")
            if attempt["job_id"] == job_id:
                return self._stage_attempt_dict(attempt)
            connection.execute(
                "UPDATE stage_attempts SET job_id=? WHERE id=? AND job_id IS NULL",
                (job_id, attempt_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise ValueError("stage attempt job link changed concurrently")
            self._append_event(
                connection,
                "run",
                attempt["run_id"],
                "stage.attempt.job_linked",
                {
                    "attempt_id": attempt_id,
                    "production_id": attempt["production_id"],
                    "stage": attempt["stage"],
                    "attempt": attempt["attempt"],
                    "cache_key": attempt["cache_key"],
                    "job_id": job_id,
                    "linked_at": timestamp,
                },
                created_at=timestamp,
            )
            updated = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            assert updated is not None
            output = self._stage_attempt_dict(updated)
        return output

    def update_stage_attempt(
        self,
        attempt_id: str,
        status: str,
        *,
        result: Any = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Advance one attempt without overwriting previous attempts."""

        if status not in {"running", "succeeded", "failed"}:
            raise ValueError("unsupported stage attempt state")
        timestamp = utc_now()
        safe_result = sanitize_for_storage(result) if result is not None else None
        safe_error = str(sanitize_for_storage(error_message or ""))[:1000] or None
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if not row:
                raise KeyError("stage attempt not found")
            current = row["status"]
            if status == "running":
                if current != "queued":
                    raise ValueError("stage attempt is not queued")
                connection.execute(
                    "UPDATE stage_attempts SET status='running', started_at=? WHERE id=? AND status='queued'",
                    (timestamp, attempt_id),
                )
            elif status == "succeeded":
                if current != "running":
                    raise ValueError("stage attempt is not running")
                connection.execute(
                    "UPDATE stage_attempts SET status='succeeded', completed_at=?, result_json=?, error_code=NULL, error_message=NULL "
                    "WHERE id=? AND status='running'",
                    (timestamp, _json(safe_result), attempt_id),
                )
            elif status == "failed":
                if current not in {"queued", "running"}:
                    raise ValueError("stage attempt is not active")
                connection.execute(
                    "UPDATE stage_attempts SET status='failed', completed_at=?, result_json=NULL, error_code=?, error_message=? "
                    "WHERE id=? AND status IN ('queued', 'running')",
                    (timestamp, error_code, safe_error, attempt_id),
                )
            changed = connection.execute("SELECT changes() AS count").fetchone()["count"]
            if changed != 1:
                raise ValueError("stage attempt state changed concurrently")
            updated = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            assert updated is not None
            self._append_event(
                connection,
                "run",
                updated["run_id"],
                f"stage.attempt.{status}",
                {
                    "attempt_id": updated["id"],
                    "production_id": updated["production_id"],
                    "stage": updated["stage"],
                    "attempt": updated["attempt"],
                    "cache_key": updated["cache_key"],
                    "result": safe_result if status == "succeeded" else None,
                    "error_code": error_code if status == "failed" else None,
                    "error_message": safe_error if status == "failed" else None,
                },
                created_at=timestamp,
            )
            output = self._stage_attempt_dict(updated)
        return output

    def find_successful_stage_attempt(
        self, production_id: str, stage: str, cache_key: str
    ) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE production_id=? AND stage=? AND cache_key=? AND status='succeeded' "
                "ORDER BY completed_at DESC, rowid DESC LIMIT 1",
                (production_id, stage, cache_key),
            ).fetchone()
        return self._stage_attempt_dict(row) if row else None

    def find_failed_stage_attempt(
        self,
        production_id: str,
        stage: str,
        cache_key: str,
        *,
        error_codes: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return the newest failed attempt matching a cache identity.

        External submissions can be accepted by a provider while the client
        loses the response.  Such an attempt is deliberately retained as a
        failed, *ambiguous* row; callers use this lookup to prevent a second
        billable submission for the same production/cache identity.
        """

        clauses = [
            "production_id=?",
            "stage=?",
            "cache_key=?",
            "status='failed'",
        ]
        parameters: list[Any] = [production_id, stage, cache_key]
        if error_codes:
            normalized = [str(code) for code in error_codes if str(code)]
            if not normalized:
                return None
            placeholders = ", ".join("?" for _ in normalized)
            clauses.append(f"error_code IN ({placeholders})")
            parameters.extend(normalized)
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE "
                + " AND ".join(clauses)
                + " ORDER BY completed_at DESC, rowid DESC LIMIT 1",
                tuple(parameters),
            ).fetchone()
        return self._stage_attempt_dict(row) if row else None

    def get_stage_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        return self._stage_attempt_dict(row) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return self._run_dict(row, connection) if row else None

    def approve_run(
        self,
        run_id: str,
        *,
        approved: bool,
        approved_max_minor: int,
        currency: str,
        actor: str,
        note: str,
    ) -> dict[str, Any]:
        approval_id = f"approval_{uuid.uuid4().hex}"
        timestamp = utc_now()
        safe_actor = str(sanitize_for_storage(actor))[:128] or "local_user"
        safe_note = str(sanitize_for_storage(note))[:2000]
        with self.transaction() as connection:
            run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise KeyError("run not found")
            if run["estimated_cost_minor"] <= 0:
                raise ValueError("cost approval is only valid for a run with a positive estimate")
            if approved and currency != run["currency"]:
                raise ValueError("approval currency must match run currency")
            if approved and approved_max_minor < run["estimated_cost_minor"]:
                raise ValueError("approval cap is below the estimated cost")
            decision = "approved" if approved else "rejected"
            connection.execute(
                "INSERT INTO run_approvals(id, run_id, decision, approved_max_minor, currency, actor, note, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval_id,
                    run_id,
                    decision,
                    approved_max_minor,
                    currency,
                    safe_actor,
                    safe_note,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                "run",
                run_id,
                f"cost.{decision}",
                {
                    "approval": {
                        "id": approval_id,
                        "run_id": run_id,
                        "decision": decision,
                        "approved_max": money_from_minor(approved_max_minor, currency),
                        "actor": safe_actor,
                        "note": safe_note,
                        "created_at": timestamp,
                    }
                },
                created_at=timestamp,
            )
            result = self._run_dict(run, connection)
        return result

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "scope_type": row["scope_type"],
            "scope_id": row["scope_id"],
            "event_type": row["event_type"],
            "created_at": row["created_at"],
            "payload": _loads(row["payload_json"], {}),
            "previous_hash": row["previous_hash"],
            "event_hash": row["event_hash"],
        }

    def production_audit_snapshot(self, production_id: str) -> dict[str, Any] | None:
        with self.read_snapshot() as connection:
            detail = self._production_detail_from_connection(
                connection,
                production_id,
                artifact_limit=1_000_000,
                artifact_offset=0,
            )
            if detail is None:
                return None
            events = connection.execute(
                "SELECT * FROM events WHERE (scope_type='production' AND scope_id=?) "
                "OR (scope_type='run' AND scope_id IN (SELECT id FROM runs WHERE production_id=?)) "
                "ORDER BY id",
                (production_id, production_id),
            ).fetchall()
            approvals = connection.execute(
                "SELECT a.* FROM run_approvals a JOIN runs r ON r.id=a.run_id "
                "WHERE r.production_id=? ORDER BY a.created_at, a.rowid",
                (production_id,),
            ).fetchall()
            detail["events"] = [self._event_dict(row) for row in events]
            detail["approvals"] = [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "decision": row["decision"],
                    "approved_max": money_from_minor(
                        row["approved_max_minor"], row["currency"]
                    ),
                    "actor": row["actor"],
                    "note": row["note"],
                    "created_at": row["created_at"],
                }
                for row in approvals
            ]
            detail["snapshot_at"] = utc_now()
            detail["schema_version"] = SCHEMA_VERSION
            return detail

    def _restore_studio_artifact_record(
        self,
        connection: sqlite3.Connection,
        production_id: str,
        value: Any,
        *,
        observed_at: str,
    ) -> int:
        """Restore one hash-verified Studio artifact without trusting event paths."""

        if not isinstance(value, dict) or value.get("production_id", production_id) != production_id:
            return 0
        artifact_id = value.get("id")
        rel_path = value.get("rel_path", value.get("path"))
        name = value.get("name")
        kind = value.get("kind")
        media_type = value.get("media_type", value.get("mime"))
        byte_count = value.get("bytes")
        digest = value.get("sha256")
        if (
            not isinstance(artifact_id, str)
            or not re.fullmatch(r"art_[0-9a-f]{32}", artifact_id)
            or not isinstance(rel_path, str)
            or not rel_path
            or len(rel_path) > 2048
            or Path(rel_path).is_absolute()
            or not isinstance(name, str)
            or not name
            or len(name) > 512
            or not isinstance(kind, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", kind)
            or not isinstance(media_type, str)
            or not media_type
            or len(media_type) > 255
            or any(character in media_type for character in "\x00\r\n")
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
            or byte_count > _MAX_RESTORED_STUDIO_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest)
            or value.get("origin", "studio") != "studio"
            or value.get("available", True) is not True
        ):
            return 0
        normalized_relative = rel_path.replace("\\", "/")
        if (
            not normalized_relative.startswith("outputs/studio/")
            or sensitive_artifact_path(normalized_relative)
            or _has_symlink_component(self.workspace, normalized_relative)
            or artifact_id != stable_id("art", normalized_relative.casefold())
        ):
            return 0
        try:
            path = workspace_path(self.workspace, normalized_relative, must_exist=True)
            canonical_relative = path.relative_to(self.workspace).as_posix()
            stat = path.stat()
        except (OSError, RuntimeError, ValueError):
            return 0
        if (
            canonical_relative != normalized_relative
            or path.is_symlink()
            or not path.is_file()
            or path.name != name
            or stat.st_size != byte_count
        ):
            return 0
        try:
            actual_digest = _sha256_file(path)
        except OSError:
            return 0
        if actual_digest != digest.upper():
            return 0
        if not connection.execute(
            "SELECT 1 FROM productions WHERE id=?", (production_id,)
        ).fetchone():
            return 0
        collisions = connection.execute(
            "SELECT * FROM artifacts WHERE id=? OR rel_path=? ORDER BY id",
            (artifact_id, normalized_relative),
        ).fetchall()
        if collisions:
            if len(collisions) != 1:
                return 0
            existing = collisions[0]
            if any(
                (
                    existing["id"] != artifact_id,
                    existing["production_id"] != production_id,
                    existing["rel_path"] != normalized_relative,
                    existing["origin"] != "studio",
                    existing["name"] != name,
                    existing["kind"] != kind,
                    existing["media_type"] != media_type,
                    existing["bytes"] != byte_count,
                    (existing["sha256"] or "").upper() != actual_digest,
                )
            ):
                return 0
            return 0
        timestamp = observed_at if isinstance(observed_at, str) and 1 <= len(observed_at) <= 64 else utc_now()
        cursor = connection.execute(
            "INSERT OR IGNORE INTO artifacts(id, production_id, rel_path, origin, name, kind, media_type, bytes, mtime_ns, sha256, is_heavy, available, indexed_at) "
            "VALUES(?, ?, ?, 'studio', ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                artifact_id,
                production_id,
                normalized_relative,
                name,
                kind,
                media_type,
                byte_count,
                stat.st_mtime_ns,
                actual_digest,
                int(byte_count > 10 * 1024 * 1024),
                timestamp,
            ),
        )
        inserted = int(cursor.rowcount == 1)
        connection.execute(
            "INSERT OR IGNORE INTO artifact_versions(artifact_id, observed_at, bytes, mtime_ns, sha256) "
            "VALUES(?, ?, ?, ?, ?)",
            (artifact_id, timestamp, byte_count, stat.st_mtime_ns, actual_digest),
        )
        return inserted

    def restore_domain_records_from_events(self) -> dict[str, int]:
        """Rebuild domain rows and hash-verified Studio artifacts from event mirrors."""
        restored = {
            "revisions": 0,
            "runs": 0,
            "detailed_test_video_claims": 0,
            "stage_attempts": 0,
            "artifacts": 0,
            "approvals": 0,
            "production_library_states": 0,
            "production_library_operations": 0,
        }
        with self.transaction() as connection:
            revision_events = connection.execute(
                "SELECT payload_json FROM events WHERE event_type='revision.created' ORDER BY id"
            ).fetchall()
            for event in revision_events:
                payload = _loads(event["payload_json"], {})
                revision = payload.get("revision") if isinstance(payload, dict) else None
                run = payload.get("run") if isinstance(payload, dict) else None
                detailed_claim = (
                    payload.get("detailed_test_video_claim")
                    if isinstance(payload, dict)
                    else None
                )
                if not isinstance(revision, dict) or not isinstance(run, dict):
                    continue
                try:
                    revision_core = {
                        "id": revision["id"],
                        "production_id": revision["production_id"],
                        "parent_revision_id": revision.get("parent_revision_id"),
                        "sequence": int(revision["sequence"]),
                        "created_at": revision["created_at"],
                        "changes": revision["changes"],
                        "rerun_plan": revision["rerun_plan"],
                    }
                    revision_digest = hashlib.sha256(
                        canonical_json(revision_core).encode("utf-8")
                    ).hexdigest()
                    if revision_digest != revision["immutable_digest"]:
                        continue
                    if not connection.execute(
                        "SELECT 1 FROM productions WHERE id=?", (revision["production_id"],)
                    ).fetchone():
                        continue
                    before = connection.total_changes
                    connection.execute(
                        "INSERT OR IGNORE INTO revisions(id, production_id, parent_revision_id, sequence, created_at, changes_json, rerun_plan_json, immutable_digest) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            revision["id"],
                            revision["production_id"],
                            revision.get("parent_revision_id"),
                            int(revision["sequence"]),
                            revision["created_at"],
                            _json(revision["changes"]),
                            _json(revision["rerun_plan"]),
                            revision_digest,
                        ),
                    )
                    restored["revisions"] += int(connection.total_changes > before)

                    if (
                        run.get("production_id") != revision_core["production_id"]
                        or run.get("revision_id") != revision_core["id"]
                    ):
                        continue
                    estimated = run["estimated_cost"]
                    estimated_minor = money_to_minor(estimated["amount"])
                    currency = str(estimated["currency"])
                    execution_profile = str(run.get("execution_profile") or "external")
                    requested_stages = run.get("requested_stages")
                    if (
                        execution_profile not in _RUN_EXECUTION_PROFILES
                        or not re.fullmatch(r"[A-Z]{3}", currency)
                        or not isinstance(requested_stages, list)
                        or not requested_stages
                        or any(
                            not isinstance(stage, str)
                            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", stage)
                            for stage in requested_stages
                        )
                    ):
                        continue
                    if execution_profile == "local_sapi" and (
                        estimated_minor != 0
                        or not set(requested_stages).issubset(
                            _LOCAL_SAPI_ZERO_COST_STAGES
                        )
                    ):
                        continue
                    if execution_profile == "elevenlabs_tts" and (
                        estimated_minor <= 0
                        or "narration" not in requested_stages
                        or not set(requested_stages).issubset(_ELEVENLABS_TTS_STAGES)
                    ):
                        continue
                    if execution_profile == "local_comfyui" and (
                        estimated_minor != 0
                        or "video_generation" not in requested_stages
                        or not set(requested_stages).issubset(
                            _LOCAL_COMFYUI_ZERO_COST_STAGES
                        )
                    ):
                        continue
                    if execution_profile == "local_playwright" and (
                        estimated_minor != 0
                        or frozenset(requested_stages)
                        not in {
                            frozenset(_LOCAL_PLAYWRIGHT_EXECUTION_STAGES),
                            frozenset(_LOCAL_PLAYWRIGHT_ZERO_COST_STAGES),
                        }
                    ):
                        continue
                    if execution_profile == "local_windows_capture" and (
                        estimated_minor != 0
                        or len(requested_stages)
                        not in {
                            len(_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES),
                            len(_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES),
                        }
                        or frozenset(requested_stages)
                        not in {
                            frozenset(_LOCAL_WINDOWS_CAPTURE_EXECUTION_STAGES),
                            frozenset(_LOCAL_WINDOWS_CAPTURE_ZERO_COST_STAGES),
                        }
                    ):
                        continue
                    pipeline_key = run.get("pipeline_key")
                    if execution_profile == "local_pipeline":
                        if (
                            estimated_minor != 0
                            or set(requested_stages) != _LOCAL_PIPELINE_ZERO_COST_STAGES
                            or not isinstance(pipeline_key, str)
                            or re.fullmatch(r"[0-9A-F]{64}", pipeline_key) is None
                        ):
                            continue
                    elif pipeline_key is not None:
                        continue
                    run_core = {
                        "id": run["id"],
                        "production_id": run["production_id"],
                        "revision_id": run["revision_id"],
                        "created_at": run["created_at"],
                        "requested_stages": requested_stages,
                        "estimated_cost_minor": estimated_minor,
                        "currency": currency,
                        "execution_profile": execution_profile,
                    }
                    if pipeline_key is not None:
                        run_core["pipeline_key"] = pipeline_key
                    run_digest = hashlib.sha256(canonical_json(run_core).encode("utf-8")).hexdigest()
                    if run_digest != run["immutable_digest"] and execution_profile == "external":
                        # v1 event payloads did not include the profile in the
                        # digest; preserve their restorability while all new
                        # runs use the v2 digest above.
                        legacy_core = dict(run_core)
                        legacy_core.pop("execution_profile")
                        legacy_digest = hashlib.sha256(
                            canonical_json(legacy_core).encode("utf-8")
                        ).hexdigest()
                        if legacy_digest == run["immutable_digest"]:
                            run_digest = legacy_digest
                    if run_digest != run["immutable_digest"]:
                        continue
                    before = connection.total_changes
                    connection.execute(
                        "INSERT OR IGNORE INTO runs(id, production_id, revision_id, created_at, requested_stages_json, estimated_cost_minor, currency, execution_profile, pipeline_key, immutable_digest) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run["id"],
                            run["production_id"],
                            run["revision_id"],
                            run["created_at"],
                            _json(requested_stages),
                            estimated_minor,
                            currency,
                            str(run.get("execution_profile") or "external"),
                            pipeline_key,
                            run_digest,
                        ),
                    )
                    restored["runs"] += int(connection.total_changes > before)
                    if pipeline_key is not None:
                        connection.execute(
                            "INSERT OR IGNORE INTO local_pipeline_claims("
                            "production_id, pipeline_key, run_id, revision_id, active_job_id, "
                            "state, request_protection, request_ciphertext, continuation_job_id, "
                            "source_job_id, source_stage_attempt_id, resume_count, created_at, "
                            "updated_at, error_code, error_message) "
                            "VALUES(?, ?, ?, ?, NULL, 'unavailable', 'none', NULL, NULL, "
                            "NULL, NULL, 0, ?, ?, NULL, NULL)",
                            (
                                run["production_id"],
                                pipeline_key,
                                run["id"],
                                run["revision_id"],
                                run["created_at"],
                                run["created_at"],
                            ),
                        )
                    if detailed_claim is not None:
                        if (
                            not isinstance(detailed_claim, dict)
                            or set(detailed_claim)
                            != {
                                "schema_version",
                                "production_id",
                                "request_key",
                                "run_id",
                                "revision_id",
                            }
                            or detailed_claim.get("schema_version") != 1
                            or detailed_claim.get("production_id")
                            != run["production_id"]
                            or detailed_claim.get("run_id") != run["id"]
                            or detailed_claim.get("revision_id")
                            != run["revision_id"]
                            or not isinstance(
                                detailed_claim.get("request_key"), str
                            )
                            or re.fullmatch(
                                r"[0-9A-F]{64}", detailed_claim["request_key"]
                            )
                            is None
                            or execution_profile != "local_sapi"
                            or estimated_minor != 0
                            or set(requested_stages)
                            != _LOCAL_SAPI_ZERO_COST_STAGES
                            or len(requested_stages)
                            != len(_LOCAL_SAPI_ZERO_COST_STAGES)
                        ):
                            continue
                        before = connection.total_changes
                        connection.execute(
                            "INSERT OR IGNORE INTO detailed_test_video_claims("
                            "production_id, request_key, run_id, revision_id, active_job_id, "
                            "created_at, updated_at) VALUES(?, ?, ?, ?, NULL, ?, ?)",
                            (
                                run["production_id"],
                                detailed_claim["request_key"],
                                run["id"],
                                run["revision_id"],
                                run["created_at"],
                                run["created_at"],
                            ),
                        )
                        restored["detailed_test_video_claims"] += int(
                            connection.total_changes > before
                        )
                except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
                    continue

            attempt_events = connection.execute(
                "SELECT scope_id, event_type, created_at, payload_json FROM events "
                "WHERE event_type IN ('stage.attempt.queued', 'stage.attempt.job_linked', "
                "'stage.attempt.running', 'stage.attempt.succeeded', 'stage.attempt.failed') ORDER BY id"
            ).fetchall()
            attempts: dict[str, dict[str, Any]] = {}
            for event in attempt_events:
                payload = _loads(event["payload_json"], {})
                if not isinstance(payload, dict):
                    continue
                attempt_id = payload.get("attempt_id")
                if not isinstance(attempt_id, str) or not re.fullmatch(
                    r"attempt_[0-9a-f]{32}", attempt_id
                ):
                    continue
                event_type = event["event_type"]
                if event_type == "stage.attempt.queued":
                    if attempt_id in attempts:
                        continue
                    stage = payload.get("stage")
                    cache_key = payload.get("cache_key")
                    attempt_number = payload.get("attempt")
                    if (
                        not isinstance(stage, str)
                        or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", stage)
                        or not isinstance(cache_key, str)
                        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", cache_key)
                        or isinstance(attempt_number, bool)
                        or not isinstance(attempt_number, int)
                        or attempt_number < 1
                    ):
                        continue
                    run = connection.execute(
                        "SELECT production_id FROM runs WHERE id=?", (event["scope_id"],)
                    ).fetchone()
                    if not run or payload.get("production_id") != run["production_id"]:
                        continue
                    attempts[attempt_id] = {
                        "id": attempt_id,
                        "run_id": event["scope_id"],
                        "production_id": run["production_id"],
                        "job_id": None,
                        "stage": stage,
                        "attempt": attempt_number,
                        "status": "queued",
                        "cache_key": cache_key,
                        "created_at": event["created_at"],
                        "started_at": None,
                        "completed_at": None,
                        "payload": sanitize_for_storage(payload.get("payload", {})),
                        "result": None,
                        "error_code": None,
                        "error_message": None,
                    }
                    continue
                attempt = attempts.get(attempt_id)
                if attempt is None or attempt["run_id"] != event["scope_id"]:
                    continue
                if event_type == "stage.attempt.job_linked":
                    job_id = payload.get("job_id")
                    if (
                        isinstance(job_id, str)
                        and re.fullmatch(r"job_[0-9a-f]{32}", job_id)
                        and attempt["job_id"] in {None, job_id}
                    ):
                        attempt["job_id"] = job_id
                    continue
                if event_type == "stage.attempt.running" and attempt["status"] == "queued":
                    attempt["status"] = "running"
                    attempt["started_at"] = event["created_at"]
                elif event_type == "stage.attempt.succeeded" and attempt["status"] == "running":
                    attempt["status"] = "succeeded"
                    attempt["completed_at"] = event["created_at"]
                    attempt["result"] = sanitize_for_storage(payload.get("result"))
                elif event_type == "stage.attempt.failed" and attempt["status"] in {
                    "queued",
                    "running",
                }:
                    attempt["status"] = "failed"
                    attempt["completed_at"] = event["created_at"]
                    code = payload.get("error_code")
                    message = payload.get("error_message")
                    attempt["error_code"] = str(code)[:128] if code else None
                    attempt["error_message"] = str(
                        sanitize_for_storage(message or "")
                    )[:1000] or None
            for attempt in attempts.values():
                try:
                    before = connection.total_changes
                    connection.execute(
                        "INSERT OR IGNORE INTO stage_attempts(id, run_id, production_id, job_id, stage, attempt, status, cache_key, created_at, started_at, completed_at, payload_json, result_json, error_code, error_message) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            attempt["id"],
                            attempt["run_id"],
                            attempt["production_id"],
                            attempt["job_id"],
                            attempt["stage"],
                            attempt["attempt"],
                            attempt["status"],
                            attempt["cache_key"],
                            attempt["created_at"],
                            attempt["started_at"],
                            attempt["completed_at"],
                            _json(attempt["payload"]),
                            _json(attempt["result"])
                            if attempt["result"] is not None
                            else None,
                            attempt["error_code"],
                            attempt["error_message"],
                        ),
                    )
                    inserted = int(connection.total_changes > before)
                    restored["stage_attempts"] += inserted
                    if inserted and attempt["status"] in {"queued", "running"}:
                        completed_at = utc_now()
                        connection.execute(
                            "UPDATE stage_attempts SET status='failed', completed_at=?, result_json=NULL, "
                            "error_code='process_interrupted', error_message='The previous Studio process stopped.' "
                            "WHERE id=? AND status IN ('queued', 'running')",
                            (completed_at, attempt["id"]),
                        )
                        self._append_event(
                            connection,
                            "run",
                            attempt["run_id"],
                            "stage.attempt.failed",
                            {
                                "attempt_id": attempt["id"],
                                "production_id": attempt["production_id"],
                                "stage": attempt["stage"],
                                "attempt": attempt["attempt"],
                                "cache_key": attempt["cache_key"],
                                "result": None,
                                "error_code": "process_interrupted",
                                "error_message": "The previous Studio process stopped.",
                            },
                            created_at=completed_at,
                        )
                except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
                    continue

            artifact_candidates: dict[str, tuple[str, dict[str, Any], str]] = {}

            def remember_artifacts(
                result: Any,
                *,
                production_id: str | None,
                observed_at: str,
            ) -> None:
                if not isinstance(result, dict):
                    return
                values: list[Any] = []
                singular = result.get("artifact")
                if isinstance(singular, dict):
                    values.append(singular)
                plural = result.get("artifacts")
                if isinstance(plural, list):
                    values.extend(plural)
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    artifact_id = item.get("id")
                    candidate_production = production_id or item.get("production_id")
                    if (
                        isinstance(artifact_id, str)
                        and isinstance(candidate_production, str)
                        and artifact_id not in artifact_candidates
                    ):
                        artifact_candidates[artifact_id] = (
                            candidate_production,
                            item,
                            observed_at,
                        )

            artifact_events = connection.execute(
                "SELECT scope_id, created_at, payload_json FROM events "
                "WHERE scope_type='production' AND event_type='artifact.created' ORDER BY id"
            ).fetchall()
            for event in artifact_events:
                payload = _loads(event["payload_json"], {})
                artifact = payload.get("artifact") if isinstance(payload, dict) else None
                if isinstance(artifact, dict):
                    remember_artifacts(
                        {"artifact": artifact},
                        production_id=event["scope_id"],
                        observed_at=event["created_at"],
                    )

            for attempt in attempts.values():
                if attempt["status"] == "succeeded":
                    remember_artifacts(
                        attempt["result"],
                        production_id=attempt["production_id"],
                        observed_at=attempt["completed_at"] or attempt["created_at"],
                    )

            job_events = connection.execute(
                "SELECT created_at, payload_json FROM events "
                "WHERE event_type='job.succeeded' ORDER BY id"
            ).fetchall()
            for event in job_events:
                payload = _loads(event["payload_json"], {})
                result = payload.get("result") if isinstance(payload, dict) else None
                remember_artifacts(
                    result,
                    production_id=None,
                    observed_at=event["created_at"],
                )

            restored_candidate_count = 0
            restored_candidate_bytes = 0
            for production_id, artifact, observed_at in artifact_candidates.values():
                byte_count = artifact.get("bytes") if isinstance(artifact, dict) else None
                if (
                    isinstance(byte_count, bool)
                    or not isinstance(byte_count, int)
                    or byte_count <= 0
                    or restored_candidate_count >= _MAX_RESTORED_STUDIO_ARTIFACT_COUNT
                    or restored_candidate_bytes + byte_count
                    > _MAX_RESTORED_STUDIO_ARTIFACT_TOTAL_BYTES
                ):
                    continue
                restored_candidate_count += 1
                restored_candidate_bytes += byte_count
                try:
                    restored["artifacts"] += self._restore_studio_artifact_record(
                        connection,
                        production_id,
                        artifact,
                        observed_at=observed_at,
                    )
                except (OSError, TypeError, ValueError, sqlite3.IntegrityError):
                    continue

            library_events = connection.execute(
                "SELECT id, scope_id, event_type, created_at, payload_json FROM events "
                "WHERE scope_type='production' AND event_type IN ("
                "'production.library.renamed', 'production.library.archived', "
                "'production.library.unarchived', 'production.library.duplicated') "
                "ORDER BY id"
            ).fetchall()
            for event in library_events:
                payload = _loads(event["payload_json"], {})
                if not isinstance(payload, dict):
                    continue
                operation_id = payload.get("operation_id")
                request_digest = payload.get("request_digest")
                production_id = event["scope_id"]
                if (
                    payload.get("schema_version") != 1
                    or not isinstance(operation_id, str)
                    or re.fullmatch(
                        r"production_library_op_[0-9a-f]{32}", operation_id
                    )
                    is None
                    or not isinstance(request_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", request_digest) is None
                    or not connection.execute(
                        "SELECT 1 FROM productions WHERE id=?", (production_id,)
                    ).fetchone()
                ):
                    continue
                try:
                    event_type = event["event_type"]
                    source_production_id: str | None = None
                    include_imports: bool | None = None
                    imported_artifact_count: int | None = None
                    if event_type == "production.library.renamed":
                        title = payload.get("title")
                        previous_title = payload.get("previous_title")
                        if (
                            not isinstance(title, str)
                            or not 1 <= len(title) <= 120
                            or title != title.strip()
                            or any(ord(character) < 32 or ord(character) == 127 for character in title)
                            or not isinstance(previous_title, str)
                        ):
                            continue
                        connection.execute(
                            "UPDATE productions SET title=? WHERE id=?",
                            (title, production_id),
                        )
                        action = "rename"
                    elif event_type in {
                        "production.library.archived",
                        "production.library.unarchived",
                    }:
                        archived = payload.get("archived")
                        previous_archived = payload.get("previous_archived")
                        if (
                            not isinstance(archived, bool)
                            or not isinstance(previous_archived, bool)
                            or archived == previous_archived
                            or archived
                            != (event_type == "production.library.archived")
                        ):
                            continue
                        archived_at = event["created_at"] if archived else None
                        state_existed = connection.execute(
                            "SELECT 1 FROM production_library_states WHERE production_id=?",
                            (production_id,),
                        ).fetchone()
                        connection.execute(
                            "INSERT INTO production_library_states("
                            "production_id, archived, archived_at, updated_at) "
                            "VALUES(?, ?, ?, ?) ON CONFLICT(production_id) DO UPDATE SET "
                            "archived=excluded.archived, archived_at=excluded.archived_at, "
                            "updated_at=excluded.updated_at",
                            (
                                production_id,
                                int(archived),
                                archived_at,
                                event["created_at"],
                            ),
                        )
                        restored["production_library_states"] += int(
                            state_existed is None
                        )
                        action = "archive"
                    else:
                        source_production_id = payload.get("source_production_id")
                        include_imports = payload.get("include_imports")
                        imported_artifact_count = payload.get(
                            "imported_artifact_count"
                        )
                        if (
                            not isinstance(source_production_id, str)
                            or not isinstance(include_imports, bool)
                            or isinstance(imported_artifact_count, bool)
                            or not isinstance(imported_artifact_count, int)
                            or imported_artifact_count < 0
                            or not connection.execute(
                                "SELECT 1 FROM productions WHERE id=?",
                                (source_production_id,),
                            ).fetchone()
                        ):
                            continue
                        action = "duplicate"
                    production = self._library_production_row(
                        connection, production_id
                    )
                    if production is None:
                        continue
                    result: dict[str, Any] = {
                        "schema_version": 1,
                        "operation_id": operation_id,
                        "action": action,
                        "production": self._production_dict(production),
                        "deduplicated": False,
                    }
                    if action == "duplicate":
                        result.update(
                            source_production_id=source_production_id,
                            include_imports=include_imports,
                            imported_artifact_count=imported_artifact_count,
                        )
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO production_library_operations("
                        "operation_id, production_id, action, request_digest, "
                        "event_id, result_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation_id,
                            production_id,
                            action,
                            request_digest,
                            event["id"],
                            canonical_json(result),
                            event["created_at"],
                        ),
                    )
                    restored["production_library_operations"] += int(
                        cursor.rowcount == 1
                    )
                except (TypeError, ValueError, sqlite3.IntegrityError):
                    continue

            approval_events = connection.execute(
                "SELECT scope_id, payload_json FROM events WHERE event_type IN ('cost.approved', 'cost.rejected') ORDER BY id"
            ).fetchall()
            for event in approval_events:
                payload = _loads(event["payload_json"], {})
                approval = payload.get("approval") if isinstance(payload, dict) else None
                if not isinstance(approval, dict) or approval.get("run_id") != event["scope_id"]:
                    continue
                try:
                    maximum = approval["approved_max"]
                    before = connection.total_changes
                    connection.execute(
                        "INSERT OR IGNORE INTO run_approvals(id, run_id, decision, approved_max_minor, currency, actor, note, created_at) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            approval["id"],
                            approval["run_id"],
                            approval["decision"],
                            money_to_minor(maximum["amount"]),
                            maximum["currency"],
                            str(approval["actor"])[:128],
                            str(approval["note"])[:2000],
                            approval["created_at"],
                        ),
                    )
                    restored["approvals"] += int(connection.total_changes > before)
                except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
                    continue
        return restored

    def create_job(self, kind: str, payload: Any, *, production_id: str | None = None) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex}"
        timestamp = utc_now()
        safe_payload = sanitize_for_storage(payload)
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO jobs(id, kind, status, production_id, created_at, payload_json) "
                "VALUES(?, ?, 'queued', ?, ?, ?)",
                (job_id, kind, production_id, timestamp, _json(safe_payload)),
            )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.queued",
                {"kind": kind, "production_id": production_id},
                created_at=timestamp,
            )
        result = self.get_job(job_id)
        assert result is not None
        return result

    def create_or_get_detailed_test_video_job(
        self,
        *,
        production_id: str,
        run_id: str,
        request_key: str,
        payload: Any,
        reuse_succeeded: bool = True,
        announcement_recipe: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically deduplicate one detailed-test-video top job."""

        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        if not isinstance(request_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", request_key
        ) is None:
            raise ValueError("invalid detailed test video key")
        if not isinstance(reuse_succeeded, bool):
            raise ValueError("reuse_succeeded must be a boolean")
        if announcement_recipe is not None and not isinstance(
            announcement_recipe, dict
        ):
            raise ValueError("announcement recipe link is invalid")
        safe_payload = sanitize_for_storage(payload)
        if (
            not isinstance(safe_payload, dict)
            or safe_payload.get("production_id") != production_id
            or safe_payload.get("run_id") != run_id
            or safe_payload.get("request_key") != request_key
            or safe_payload.get("execution_profile") != "local_sapi"
            or safe_payload.get("stage") != "detailed_test_video"
            or not isinstance(safe_payload.get("revision_id"), str)
        ):
            raise ValueError("invalid detailed test video job payload")

        timestamp = utc_now()
        with self.transaction() as connection:
            claim = connection.execute(
                "SELECT * FROM detailed_test_video_claims "
                "WHERE production_id=? AND request_key=?",
                (production_id, request_key),
            ).fetchone()
            if (
                claim is None
                or claim["run_id"] != run_id
                or safe_payload.get("revision_id") != claim["revision_id"]
            ):
                raise ValueError("detailed test video run claim is unavailable")
            run = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["production_id"] != production_id
                or run["execution_profile"] != "local_sapi"
                or run["pipeline_key"] is not None
                or run["revision_id"] != claim["revision_id"]
                or run["estimated_cost_minor"] != 0
                or set(_loads(run["requested_stages_json"], []))
                != _LOCAL_SAPI_ZERO_COST_STAGES
            ):
                raise ValueError("detailed test video run claim is invalid")

            active_job_id = claim["active_job_id"]
            if isinstance(active_job_id, str):
                existing = connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (active_job_id,)
                ).fetchone()
                if existing is None:
                    raise sqlite3.IntegrityError(
                        "detailed test video job claim is missing"
                    )
                existing_payload = _loads(existing["payload_json"], {})
                existing_result = _loads(existing["result_json"], None)
                if (
                    existing["kind"] != "detailed_test_video"
                    or existing["production_id"] != production_id
                    or existing_payload != safe_payload
                ):
                    raise sqlite3.IntegrityError(
                        "detailed test video job claim is invalid"
                    )
                if existing["status"] in {"queued", "running"} or (
                    existing["status"] == "succeeded" and reuse_succeeded
                ):
                    children = (
                        existing_result.get("children")
                        if isinstance(existing_result, dict)
                        else None
                    )
                    if existing["status"] == "succeeded" and (
                        not isinstance(existing_result, dict)
                        or existing_result.get("schema_version") != 1
                        or existing_result.get("production_id") != production_id
                        or existing_result.get("run_id") != run_id
                        or existing_result.get("revision_id") != claim["revision_id"]
                        or existing_result.get("request_key") != request_key
                        or existing_result.get("execution_profile") != "local_sapi"
                        or existing_result.get("technical_verdict") != "pass"
                        or not isinstance(children, dict)
                        or set(children) != {"narration", "timeline", "assembly", "qc"}
                    ):
                        raise sqlite3.IntegrityError(
                            "detailed test video job result provenance is invalid"
                        )
                    if announcement_recipe is not None:
                        self._record_announcement_execution_in_transaction(
                            connection,
                            production_id,
                            recipe=announcement_recipe,
                            job=existing,
                            run_id=run_id,
                            revision_id=claim["revision_id"],
                            request_key=request_key,
                            deduplicated=True,
                        )
                    return self._job_dict(existing), False

            job_id = f"job_{uuid.uuid4().hex}"
            connection.execute(
                "INSERT INTO jobs(id, kind, status, production_id, created_at, payload_json) "
                "VALUES(?, 'detailed_test_video', 'queued', ?, ?, ?)",
                (job_id, production_id, timestamp, _json(safe_payload)),
            )
            connection.execute(
                "UPDATE detailed_test_video_claims SET active_job_id=?, updated_at=? "
                "WHERE production_id=? AND request_key=? AND run_id=? "
                "AND active_job_id IS ? AND updated_at=?",
                (
                    job_id,
                    timestamp,
                    production_id,
                    request_key,
                    run_id,
                    active_job_id,
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise sqlite3.IntegrityError(
                    "detailed test video job claim changed concurrently"
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.queued",
                {"kind": "detailed_test_video", "production_id": production_id},
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert row is not None
            if announcement_recipe is not None:
                self._record_announcement_execution_in_transaction(
                    connection,
                    production_id,
                    recipe=announcement_recipe,
                    job=row,
                    run_id=run_id,
                    revision_id=claim["revision_id"],
                    request_key=request_key,
                    deduplicated=False,
                )
            return self._job_dict(row), True

    def abort_detailed_test_video_job_admission(
        self,
        job_id: str,
        *,
        error_code: str = "job_setup_failed",
        error_message: str = "The background job could not be prepared.",
    ) -> dict[str, Any]:
        """Atomically fail one detailed top job that never reached its queue."""

        validate_identifier(job_id, label="job id")
        safe_code = str(sanitize_for_storage(error_code or "job_setup_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        timestamp = utc_now()
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            claim = connection.execute(
                "SELECT * FROM detailed_test_video_claims WHERE active_job_id=?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if (
                claim is None
                or job["kind"] != "detailed_test_video"
                or job["production_id"] != claim["production_id"]
            ):
                raise ValueError("detailed test video job claim is unavailable")
            if job["status"] == "failed" and job["error_code"] == safe_code:
                return self._job_dict(job)
            if job["status"] != "queued":
                raise AtomicCompletionError(
                    "detailed test video admission is no longer queued",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status="detailed_test_video",
                )
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "detailed test video job changed before admission abort",
                    code="atomic_failure_not_active",
                    job_status="unknown",
                    stage_status="detailed_test_video",
                )
            connection.execute(
                "UPDATE detailed_test_video_claims SET updated_at=? "
                "WHERE production_id=? AND request_key=? AND active_job_id=? "
                "AND updated_at=?",
                (
                    timestamp,
                    claim["production_id"],
                    claim["request_key"],
                    job_id,
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "detailed test video claim changed before admission abort",
                    code="atomic_failure_not_active",
                    job_status="failed",
                    stage_status="unknown",
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.failed",
                {
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            updated = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert updated is not None
            return self._job_dict(updated)

    def create_or_get_local_pipeline_job(
        self,
        *,
        production_id: str,
        run_id: str,
        pipeline_key: str,
        payload: Any,
        reuse_succeeded: bool = True,
        expected_continuation_state: str | None = None,
        expected_continuation_updated_at: str | None = None,
        expected_source_job_id: str | None = None,
        expected_source_stage_attempt_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim the one top-level job for a pipeline request.

        Active and successful requests are idempotent.  A failed/interrupted
        top job may be replaced, but the immutable run claim is retained so
        completed child caches and the same-run ComfyUI marker remain usable.
        """

        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise ValueError("invalid pipeline key")
        if not isinstance(reuse_succeeded, bool):
            raise ValueError("reuse_succeeded must be a boolean")
        has_expected_checkpoint = expected_continuation_state is not None
        if has_expected_checkpoint != (expected_continuation_updated_at is not None):
            raise ValueError("continuation state and timestamp must be supplied together")
        if has_expected_checkpoint and expected_continuation_state != "ready":
            raise ValueError("only a ready continuation checkpoint can be claimed")
        if (expected_source_job_id is None) != (
            expected_source_stage_attempt_id is None
        ):
            raise ValueError("continuation source job and attempt must be supplied together")
        if expected_source_job_id is not None:
            validate_identifier(expected_source_job_id, label="source job id")
            validate_identifier(
                expected_source_stage_attempt_id or "", label="source stage attempt id"
            )
        safe_payload = sanitize_for_storage(payload)
        if (
            not isinstance(safe_payload, dict)
            or safe_payload.get("production_id") != production_id
            or safe_payload.get("run_id") != run_id
            or safe_payload.get("pipeline_key") != pipeline_key
            or safe_payload.get("execution_profile") != "local_pipeline"
            or not isinstance(safe_payload.get("revision_id"), str)
        ):
            raise ValueError("invalid pipeline job payload")

        timestamp = utc_now()
        with self.transaction() as connection:
            claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
            if (
                claim is None
                or claim["run_id"] != run_id
                or not isinstance(claim["revision_id"], str)
                or safe_payload.get("revision_id") != claim["revision_id"]
            ):
                raise ValueError("pipeline run claim is unavailable")
            run = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["production_id"] != production_id
                or run["execution_profile"] != "local_pipeline"
                or run["pipeline_key"] != pipeline_key
                or run["revision_id"] != claim["revision_id"]
                or run["estimated_cost_minor"] != 0
                or set(_loads(run["requested_stages_json"], []))
                != _LOCAL_PIPELINE_ZERO_COST_STAGES
            ):
                raise ValueError("pipeline run claim is invalid")

            active_job_id = claim["active_job_id"]
            if isinstance(active_job_id, str):
                existing = connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (active_job_id,)
                ).fetchone()
                if existing is None:
                    raise sqlite3.IntegrityError("pipeline job claim is missing")
                existing_payload = _loads(existing["payload_json"], {})
                existing_result = _loads(existing["result_json"], None)
                if (
                    existing["kind"] != "local_pipeline"
                    or existing["production_id"] != production_id
                    or existing_payload != safe_payload
                ):
                    raise sqlite3.IntegrityError("pipeline job claim is invalid")
                if existing["status"] in {"queued", "running"} or (
                    existing["status"] == "succeeded" and reuse_succeeded
                ):
                    if existing["status"] == "succeeded" and (
                        not isinstance(existing_result, dict)
                        or existing_result.get("production_id") != production_id
                        or existing_result.get("run_id") != run_id
                        or existing_result.get("revision_id") != claim["revision_id"]
                        or existing_result.get("pipeline_key") != pipeline_key
                        or existing_result.get("execution_profile") != "local_pipeline"
                        or existing_result.get("technical_verdict") != "pass"
                    ):
                        raise sqlite3.IntegrityError(
                            "pipeline job result provenance is invalid"
                        )
                    return self._job_dict(existing), False

            if has_expected_checkpoint and (
                claim["state"] != expected_continuation_state
                or claim["updated_at"] != expected_continuation_updated_at
                or claim["source_job_id"] != expected_source_job_id
                or claim["source_stage_attempt_id"]
                != expected_source_stage_attempt_id
                or claim["continuation_job_id"] is not None
            ):
                raise AtomicCompletionError(
                    "pipeline continuation checkpoint changed",
                    code="pipeline_continuation_changed",
                    job_status=(existing["status"] if active_job_id and existing else None),
                    stage_status=claim["state"],
                )
            if claim["state"] in {
                "waiting_provider",
                "continuing",
                "cancel_requested",
                "cancelled",
            }:
                raise AtomicCompletionError(
                    "pipeline continuation is not admissible",
                    code="pipeline_continuation_not_ready",
                    job_status=(existing["status"] if active_job_id and existing else None),
                    stage_status=claim["state"],
                )
            is_continuation = bool(
                claim["state"] == "ready" or has_expected_checkpoint
            )
            if is_continuation and claim["source_job_id"] is not None:
                source_job = connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (claim["source_job_id"],)
                ).fetchone()
                source_attempt = connection.execute(
                    "SELECT * FROM stage_attempts WHERE id=?",
                    (claim["source_stage_attempt_id"],),
                ).fetchone()
                source_result = (
                    _loads(source_job["result_json"], None)
                    if source_job is not None
                    else None
                )
                if (
                    source_job is None
                    or source_attempt is None
                    or source_job["kind"] != "local_video_generation"
                    or source_job["status"] != "succeeded"
                    or source_job["production_id"] != production_id
                    or source_attempt["job_id"] != source_job["id"]
                    or source_attempt["run_id"] != run_id
                    or source_attempt["production_id"] != production_id
                    or source_attempt["stage"] != "video_generation"
                    or source_attempt["status"] != "succeeded"
                    or not isinstance(source_result, dict)
                    or source_result.get("stage_attempt_id") != source_attempt["id"]
                ):
                    raise sqlite3.IntegrityError(
                        "pipeline continuation source provenance is invalid"
                    )

            job_id = f"job_{uuid.uuid4().hex}"
            connection.execute(
                "INSERT INTO jobs(id, kind, status, production_id, created_at, payload_json) "
                "VALUES(?, 'local_pipeline', 'queued', ?, ?, ?)",
                (job_id, production_id, timestamp, _json(safe_payload)),
            )
            connection.execute(
                "UPDATE local_pipeline_claims SET active_job_id=?, state=?, "
                "continuation_job_id=?, resume_count=resume_count+?, updated_at=?, "
                "error_code=NULL, error_message=NULL "
                "WHERE production_id=? AND pipeline_key=? AND run_id=? "
                "AND state=? AND updated_at=? AND source_job_id IS ? "
                "AND source_stage_attempt_id IS ? AND continuation_job_id IS ?",
                (
                    job_id,
                    (
                        "continuing"
                        if is_continuation
                        else (
                            "active"
                            if claim["request_protection"] == "dpapi-v1"
                            else "unavailable"
                        )
                    ),
                    job_id if is_continuation else None,
                    int(is_continuation),
                    timestamp,
                    production_id,
                    pipeline_key,
                    run_id,
                    claim["state"],
                    claim["updated_at"],
                    claim["source_job_id"],
                    claim["source_stage_attempt_id"],
                    claim["continuation_job_id"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise sqlite3.IntegrityError("pipeline job claim changed concurrently")
            self._append_event(
                connection,
                "job",
                job_id,
                "job.queued",
                {"kind": "local_pipeline", "production_id": production_id},
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert row is not None
            return self._job_dict(row), True

    def abort_local_pipeline_job_admission(
        self,
        job_id: str,
        *,
        error_code: str = "job_setup_failed",
        error_message: str = "The background job could not be prepared.",
    ) -> dict[str, Any]:
        """Fail one unqueued top job and atomically release its checkpoint."""

        validate_identifier(job_id, label="job id")
        safe_code = str(sanitize_for_storage(error_code or "job_setup_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        timestamp = utc_now()
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE active_job_id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if claim is None or job["kind"] != "local_pipeline":
                raise ValueError("pipeline job claim is unavailable")
            if job["status"] == "failed" and job["error_code"] == safe_code:
                return {
                    "job": self._job_dict(job),
                    "pipeline_continuation": self._local_pipeline_continuation_dict(
                        claim
                    ),
                }
            if job["status"] != "queued" or claim["state"] not in {
                "active",
                "continuing",
                "unavailable",
            }:
                raise AtomicCompletionError(
                    "pipeline admission is no longer queued",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=claim["state"],
                )
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline job changed before admission abort",
                    code="atomic_failure_not_active",
                    job_status="unknown",
                    stage_status=claim["state"],
                )
            next_state = (
                "ready"
                if claim["request_protection"] == "dpapi-v1"
                else "unavailable"
            )
            connection.execute(
                "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
                "updated_at=?, error_code=?, error_message=? "
                "WHERE production_id=? AND pipeline_key=? AND active_job_id=? "
                "AND state=? AND updated_at=?",
                (
                    next_state,
                    timestamp,
                    safe_code,
                    safe_message,
                    claim["production_id"],
                    claim["pipeline_key"],
                    job_id,
                    claim["state"],
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline continuation changed before admission abort",
                    code="pipeline_continuation_changed",
                    job_status="failed",
                    stage_status="unknown",
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.failed",
                {"result": None, "error_code": safe_code, "error_message": safe_message},
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                claim["run_id"],
                "pipeline.continuation.admission_aborted",
                {
                    "production_id": claim["production_id"],
                    "pipeline_key": claim["pipeline_key"],
                    "job_id": job_id,
                    "state": next_state,
                    "error_code": safe_code,
                },
                created_at=timestamp,
            )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (claim["production_id"], claim["pipeline_key"]),
            ).fetchone()
            assert updated_job is not None and updated_claim is not None
            return {
                "job": self._job_dict(updated_job),
                "pipeline_continuation": self._local_pipeline_continuation_dict(
                    updated_claim
                ),
            }

    def repair_orphaned_local_pipeline_continuation(
        self,
        production_id: str,
        pipeline_key: str,
        *,
        expected_updated_at: str,
    ) -> dict[str, Any] | None:
        """Repair an active ledger whose top job no longer has an owner."""

        validate_identifier(production_id, label="production id")
        if not isinstance(pipeline_key, str) or re.fullmatch(
            r"[0-9A-F]{64}", pipeline_key
        ) is None:
            raise ValueError("invalid pipeline key")
        if not isinstance(expected_updated_at, str) or not expected_updated_at:
            raise ValueError("expected continuation timestamp is required")
        timestamp = utc_now()
        with self.transaction() as connection:
            claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
            if claim is None:
                return None
            if claim["updated_at"] != expected_updated_at or claim["state"] not in {
                "active",
                "continuing",
                "waiting_provider",
            }:
                return None
            owner = (
                connection.execute(
                    "SELECT status FROM jobs WHERE id=?", (claim["active_job_id"],)
                ).fetchone()
                if claim["active_job_id"] is not None
                else None
            )
            if owner is not None and owner["status"] in {"queued", "running"}:
                return None
            provider = connection.execute(
                "SELECT 1 FROM provider_tasks WHERE run_id=? "
                "AND status NOT IN ('succeeded', 'failed') LIMIT 1",
                (claim["run_id"],),
            ).fetchone()
            if provider is not None:
                next_state = "waiting_provider"
            elif (
                claim["request_protection"] == "dpapi-v1"
                and claim["source_stage_attempt_id"] is not None
            ):
                next_state = "ready"
            elif claim["request_protection"] == "dpapi-v1":
                next_state = "recovery_blocked"
            else:
                next_state = "unavailable"
            connection.execute(
                "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
                "updated_at=?, error_code='process_interrupted', "
                "error_message='The previous Studio process stopped.' "
                "WHERE production_id=? AND pipeline_key=? AND updated_at=? AND state=?",
                (
                    next_state,
                    timestamp,
                    production_id,
                    pipeline_key,
                    expected_updated_at,
                    claim["state"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                return None
            updated = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (production_id, pipeline_key),
            ).fetchone()
            assert updated is not None
            self._append_event(
                connection,
                "run",
                claim["run_id"],
                "pipeline.continuation.orphan_repaired",
                {
                    "production_id": production_id,
                    "pipeline_key": pipeline_key,
                    "state": next_state,
                    "previous_state": claim["state"],
                    "error_code": "process_interrupted",
                },
                created_at=timestamp,
            )
            return self._local_pipeline_continuation_dict(updated)

    def complete_local_pipeline_job(
        self, job_id: str, result: Any
    ) -> dict[str, Any]:
        """Atomically publish top success and terminalize its continuation."""

        validate_identifier(job_id, label="job id")
        safe_result = sanitize_for_storage(result)
        if not isinstance(safe_result, dict):
            raise ValueError("pipeline result must be an object")
        timestamp = utc_now()
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE active_job_id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if claim is None or job["kind"] != "local_pipeline":
                raise ValueError("pipeline job claim is unavailable")
            payload = _loads(job["payload_json"], {})
            if (
                not isinstance(payload, dict)
                or payload.get("production_id") != claim["production_id"]
                or payload.get("run_id") != claim["run_id"]
                or payload.get("revision_id") != claim["revision_id"]
                or payload.get("pipeline_key") != claim["pipeline_key"]
                or safe_result.get("production_id") != claim["production_id"]
                or safe_result.get("run_id") != claim["run_id"]
                or safe_result.get("revision_id") != claim["revision_id"]
                or safe_result.get("pipeline_key") != claim["pipeline_key"]
                or safe_result.get("execution_profile") != "local_pipeline"
                or safe_result.get("technical_verdict") != "pass"
            ):
                raise ValueError("pipeline result provenance is invalid")
            if job["status"] == "succeeded" and claim["state"] == "succeeded":
                return {
                    "committed": False,
                    "job": self._job_dict(job),
                    "pipeline_continuation": self._local_pipeline_continuation_dict(
                        claim
                    ),
                }
            if job["status"] != "running" or claim["state"] not in {
                "active",
                "continuing",
                "ready",
                "unavailable",
            }:
                raise AtomicCompletionError(
                    "pipeline completion requires an active top job",
                    code="atomic_completion_not_active",
                    job_status=job["status"],
                    stage_status=claim["state"],
                )
            connection.execute(
                "UPDATE jobs SET status='succeeded', completed_at=?, result_json=?, "
                "error_code=NULL, error_message=NULL WHERE id=? AND status='running'",
                (timestamp, _json(safe_result), job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline job stopped before completion",
                    code="atomic_completion_not_active",
                    job_status="unknown",
                    stage_status=claim["state"],
                )
            connection.execute(
                "UPDATE local_pipeline_claims SET state='succeeded', "
                "request_protection='none', request_ciphertext=NULL, updated_at=?, "
                "error_code=NULL, error_message=NULL "
                "WHERE production_id=? AND pipeline_key=? AND active_job_id=? "
                "AND state=? AND updated_at=?",
                (
                    timestamp,
                    claim["production_id"],
                    claim["pipeline_key"],
                    job_id,
                    claim["state"],
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline continuation changed before completion",
                    code="pipeline_continuation_changed",
                    job_status="succeeded",
                    stage_status="unknown",
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.succeeded",
                {"result": safe_result, "error_code": None, "error_message": None},
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                claim["run_id"],
                "pipeline.continuation.succeeded",
                {
                    "production_id": claim["production_id"],
                    "pipeline_key": claim["pipeline_key"],
                    "job_id": job_id,
                    "state": "succeeded",
                },
                created_at=timestamp,
            )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (claim["production_id"], claim["pipeline_key"]),
            ).fetchone()
            assert updated_job is not None and updated_claim is not None
            return {
                "committed": True,
                "job": self._job_dict(updated_job),
                "pipeline_continuation": self._local_pipeline_continuation_dict(
                    updated_claim
                ),
            }

    def fail_local_pipeline_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any]:
        """Atomically fail a top job without losing recoverable provider work."""

        validate_identifier(job_id, label="job id")
        safe_code = str(sanitize_for_storage(error_code or "pipeline_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        timestamp = utc_now()
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE active_job_id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if claim is None or job["kind"] != "local_pipeline":
                raise ValueError("pipeline job claim is unavailable")
            if job["status"] == "failed" and job["error_code"] == safe_code:
                return {
                    "committed": False,
                    "job": self._job_dict(job),
                    "pipeline_continuation": self._local_pipeline_continuation_dict(
                        claim
                    ),
                }
            if job["status"] not in {"queued", "running"} or claim["state"] in {
                "succeeded",
                "cancelled",
            }:
                raise AtomicCompletionError(
                    "pipeline failure requires an active top job",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=claim["state"],
                )
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status IN ('queued', 'running')",
                (timestamp, safe_code, safe_message, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline job stopped before failure commit",
                    code="atomic_failure_not_active",
                    job_status="unknown",
                    stage_status=claim["state"],
                )
            provider_pending = connection.execute(
                "SELECT 1 FROM provider_tasks WHERE run_id=? "
                "AND status NOT IN ('succeeded', 'failed') LIMIT 1",
                (claim["run_id"],),
            ).fetchone()
            next_state = (
                "waiting_provider"
                if provider_pending is not None
                else (
                    "recovery_blocked"
                    if claim["request_protection"] == "dpapi-v1"
                    else "unavailable"
                )
            )
            connection.execute(
                "UPDATE local_pipeline_claims SET state=?, continuation_job_id=NULL, "
                "updated_at=?, error_code=?, error_message=? "
                "WHERE production_id=? AND pipeline_key=? AND active_job_id=? "
                "AND state=? AND updated_at=?",
                (
                    next_state,
                    timestamp,
                    safe_code,
                    safe_message,
                    claim["production_id"],
                    claim["pipeline_key"],
                    job_id,
                    claim["state"],
                    claim["updated_at"],
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "pipeline continuation changed before failure commit",
                    code="pipeline_continuation_changed",
                    job_status="failed",
                    stage_status="unknown",
                )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.failed",
                {"result": None, "error_code": safe_code, "error_message": safe_message},
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                claim["run_id"],
                "pipeline.continuation.failed",
                {
                    "production_id": claim["production_id"],
                    "pipeline_key": claim["pipeline_key"],
                    "job_id": job_id,
                    "state": next_state,
                    "error_code": safe_code,
                },
                created_at=timestamp,
            )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_claim = connection.execute(
                "SELECT * FROM local_pipeline_claims WHERE production_id=? AND pipeline_key=?",
                (claim["production_id"], claim["pipeline_key"]),
            ).fetchone()
            assert updated_job is not None and updated_claim is not None
            return {
                "committed": True,
                "job": self._job_dict(updated_job),
                "pipeline_continuation": self._local_pipeline_continuation_dict(
                    updated_claim
                ),
            }

    def create_or_get_local_video_generation_job(
        self,
        *,
        production_id: str,
        run_id: str,
        cache_key: str,
        payload_digest: str,
        attempt_payload: Any,
        job_payload: Any,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically create or reuse one active direct ComfyUI job claim."""

        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        if re.fullmatch(r"[0-9A-F]{64}", cache_key or "") is None:
            raise ValueError("invalid cache key")
        if re.fullmatch(r"[0-9A-F]{64}", payload_digest or "") is None:
            raise ValueError("invalid payload digest")
        safe_attempt_payload = sanitize_for_storage(attempt_payload)
        safe_job_payload = sanitize_for_storage(job_payload)
        if (
            not isinstance(safe_attempt_payload, dict)
            or safe_attempt_payload.get("cache_key") != cache_key
            or safe_attempt_payload.get("provider_payload_digest") != payload_digest
            or not isinstance(safe_job_payload, dict)
            or safe_job_payload.get("production_id") != production_id
            or safe_job_payload.get("run_id") != run_id
            or safe_job_payload.get("stage") != "video_generation"
            or safe_job_payload.get("cache_key") != cache_key
            or safe_job_payload.get("provider_payload_digest") != payload_digest
        ):
            raise ValueError("invalid local video generation claim payload")

        timestamp = utc_now()
        with self.transaction() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["production_id"] != production_id
                or run["execution_profile"] not in {"local_comfyui", "local_pipeline"}
                or "video_generation" not in _loads(run["requested_stages_json"], [])
            ):
                raise ValueError("local video generation run is invalid")

            claim = connection.execute(
                "SELECT * FROM local_video_generation_claims "
                "WHERE run_id=? AND cache_key=? AND payload_digest=?",
                (run_id, cache_key, payload_digest),
            ).fetchone()
            if claim is not None:
                existing_job = connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (claim["active_job_id"],)
                ).fetchone()
                existing_attempt = connection.execute(
                    "SELECT * FROM stage_attempts WHERE id=?",
                    (claim["stage_attempt_id"],),
                ).fetchone()
                if existing_job is None or existing_attempt is None:
                    raise sqlite3.IntegrityError("local video generation claim is missing")
                if (
                    claim["production_id"] != production_id
                    or existing_job["kind"] != "local_video_generation"
                    or existing_job["production_id"] != production_id
                    or existing_attempt["job_id"] != existing_job["id"]
                    or existing_attempt["run_id"] != run_id
                    or existing_attempt["stage"] != "video_generation"
                    or existing_attempt["cache_key"] != cache_key
                    or {
                        key: value
                        for key, value in _loads(existing_job["payload_json"], {}).items()
                        if key != "stage_attempt_id"
                    }
                    != safe_job_payload
                    or _loads(existing_job["payload_json"], {}).get(
                        "stage_attempt_id"
                    )
                    != existing_attempt["id"]
                    or _loads(existing_attempt["payload_json"], {}) != safe_attempt_payload
                ):
                    raise sqlite3.IntegrityError(
                        "local video generation claim provenance is invalid"
                    )
                if (
                    existing_job["status"] in {"queued", "running"}
                    and existing_attempt["status"] in {"queued", "running"}
                ):
                    output = self._job_dict(existing_job)
                    output["stage_attempt_id"] = existing_attempt["id"]
                    output["cache_key"] = cache_key
                    return output, False

            attempt_id = f"attempt_{uuid.uuid4().hex}"
            job_id = f"job_{uuid.uuid4().hex}"
            stored_job_payload = {
                **safe_job_payload,
                "stage_attempt_id": attempt_id,
            }
            latest = connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS attempt FROM stage_attempts "
                "WHERE run_id=? AND stage='video_generation'",
                (run_id,),
            ).fetchone()
            attempt_number = int(latest["attempt"]) + 1
            connection.execute(
                "INSERT INTO jobs(id, kind, status, production_id, created_at, payload_json) "
                "VALUES(?, 'local_video_generation', 'queued', ?, ?, ?)",
                (job_id, production_id, timestamp, _json(stored_job_payload)),
            )
            connection.execute(
                "INSERT INTO stage_attempts(id, run_id, production_id, job_id, stage, "
                "attempt, status, cache_key, created_at, payload_json) "
                "VALUES(?, ?, ?, ?, 'video_generation', ?, 'queued', ?, ?, ?)",
                (
                    attempt_id,
                    run_id,
                    production_id,
                    job_id,
                    attempt_number,
                    cache_key,
                    timestamp,
                    _json(safe_attempt_payload),
                ),
            )
            if claim is None:
                connection.execute(
                    "INSERT INTO local_video_generation_claims("
                    "run_id, production_id, cache_key, payload_digest, stage_attempt_id, "
                    "active_job_id, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        production_id,
                        cache_key,
                        payload_digest,
                        attempt_id,
                        job_id,
                        timestamp,
                        timestamp,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE local_video_generation_claims SET stage_attempt_id=?, "
                    "active_job_id=?, updated_at=? WHERE run_id=? AND cache_key=? "
                    "AND payload_digest=? AND active_job_id=?",
                    (
                        attempt_id,
                        job_id,
                        timestamp,
                        run_id,
                        cache_key,
                        payload_digest,
                        claim["active_job_id"],
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise sqlite3.IntegrityError(
                        "local video generation claim changed concurrently"
                    )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.queued",
                {"kind": "local_video_generation", "production_id": production_id},
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "stage.attempt.queued",
                {
                    "attempt_id": attempt_id,
                    "production_id": production_id,
                    "stage": "video_generation",
                    "attempt": attempt_number,
                    "cache_key": cache_key,
                    "payload": safe_attempt_payload,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "run",
                run_id,
                "stage.attempt.job_linked",
                {
                    "attempt_id": attempt_id,
                    "production_id": production_id,
                    "stage": "video_generation",
                    "attempt": attempt_number,
                    "cache_key": cache_key,
                    "job_id": job_id,
                    "linked_at": timestamp,
                },
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            assert row is not None
            output = self._job_dict(row)
            output["stage_attempt_id"] = attempt_id
            output["cache_key"] = cache_key
            return output, True

    def abort_local_video_generation_admission(
        self,
        job_id: str,
        stage_attempt_id: str,
        *,
        error_code: str = "job_setup_failed",
        error_message: str = "The background job could not be prepared.",
    ) -> dict[str, Any]:
        """Atomically retire a claimed pair that never reached the GPU queue.

        Direct local video admission creates the job, stage attempt, and
        durable request claim before constructing and enqueueing the callback.
        If that in-memory admission step fails, the pair is still ``queued``;
        the normal worker failure transaction intentionally requires a
        ``running`` job.  This bounded transaction handles only that earlier
        state and refuses to touch a provider task or an already-started job.
        The claim remains pointed at the failed pair as audit history, allowing
        the next identical request to replace it with fresh IDs.
        """

        timestamp = utc_now()
        safe_code = str(sanitize_for_storage(error_code or "job_setup_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if attempt is None:
                raise KeyError("stage attempt not found")
            if (
                job["kind"] != "local_video_generation"
                or job["status"] != "queued"
                or attempt["status"] != "queued"
                or attempt["job_id"] != job_id
                or attempt["stage"] != "video_generation"
                or attempt["production_id"] != job["production_id"]
            ):
                raise AtomicCompletionError(
                    "local video admission is no longer queued",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )
            job_payload = _loads(job["payload_json"], {})
            attempt_payload = _loads(attempt["payload_json"], {})
            if (
                not isinstance(job_payload, dict)
                or not isinstance(attempt_payload, dict)
                or job_payload.get("stage_attempt_id") != stage_attempt_id
                or job_payload.get("run_id") != attempt["run_id"]
                or job_payload.get("production_id") != attempt["production_id"]
                or job_payload.get("cache_key") != attempt["cache_key"]
                or attempt_payload.get("cache_key") != attempt["cache_key"]
            ):
                raise sqlite3.IntegrityError(
                    "local video admission provenance is invalid"
                )
            payload_digest = job_payload.get("provider_payload_digest")
            if (
                not isinstance(payload_digest, str)
                or attempt_payload.get("provider_payload_digest") != payload_digest
            ):
                raise sqlite3.IntegrityError(
                    "local video admission payload digest is invalid"
                )
            claim = connection.execute(
                "SELECT * FROM local_video_generation_claims "
                "WHERE run_id=? AND cache_key=? AND payload_digest=?",
                (attempt["run_id"], attempt["cache_key"], payload_digest),
            ).fetchone()
            if (
                claim is None
                or claim["production_id"] != attempt["production_id"]
                or claim["stage_attempt_id"] != stage_attempt_id
                or claim["active_job_id"] != job_id
            ):
                raise sqlite3.IntegrityError(
                    "local video admission claim is invalid"
                )
            provider_task = connection.execute(
                "SELECT id FROM provider_tasks WHERE current_stage_attempt_id=? "
                "OR current_job_id=? LIMIT 1",
                (stage_attempt_id, job_id),
            ).fetchone()
            if provider_task is not None:
                raise AtomicCompletionError(
                    "provider submission already owns this admission",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )

            connection.execute(
                "UPDATE stage_attempts SET status='failed', completed_at=?, "
                "result_json=NULL, error_code=?, error_message=? "
                "WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, stage_attempt_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "stage attempt changed before admission failure could commit",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status="unknown",
                )
            connection.execute(
                "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                "error_code=?, error_message=? WHERE id=? AND status='queued'",
                (timestamp, safe_code, safe_message, job_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "job changed before admission failure could commit",
                    code="atomic_failure_not_active",
                    job_status="unknown",
                    stage_status="failed",
                )
            connection.execute(
                "UPDATE local_video_generation_claims SET updated_at=? "
                "WHERE run_id=? AND cache_key=? AND payload_digest=? "
                "AND stage_attempt_id=? AND active_job_id=?",
                (
                    timestamp,
                    attempt["run_id"],
                    attempt["cache_key"],
                    payload_digest,
                    stage_attempt_id,
                    job_id,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise sqlite3.IntegrityError(
                    "local video admission claim changed concurrently"
                )
            self._append_event(
                connection,
                "run",
                attempt["run_id"],
                "stage.attempt.failed",
                {
                    "attempt_id": attempt["id"],
                    "production_id": attempt["production_id"],
                    "stage": attempt["stage"],
                    "attempt": attempt["attempt"],
                    "cache_key": attempt["cache_key"],
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.failed",
                {
                    "result": None,
                    "error_code": safe_code,
                    "error_message": safe_message,
                },
                created_at=timestamp,
            )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            assert updated_job is not None and updated_attempt is not None
            return {
                "job": self._job_dict(updated_job),
                "stage_attempt": self._stage_attempt_dict(updated_attempt),
            }

    def complete_job_with_stage_attempt(
        self,
        job_id: str,
        stage_attempt_id: str,
        public_result: Any,
        artifact_records: Sequence[dict[str, Any]] = (),
        provider_task_record_id: str | None = None,
    ) -> dict[str, Any]:
        """Commit a job and its linked active stage attempt together.

        This is the only success transition for a worker-backed stage.  The
        job and stage rows are validated, updated, and audited inside one
        transaction.  A shutdown that wins the race leaves both rows
        terminal and raises :class:`AtomicCompletionError`; it can never
        produce a job-success/stage-failed (or the reverse) combination.
        """

        timestamp = utc_now()
        safe_stage_result = sanitize_for_storage(public_result)
        if not isinstance(safe_stage_result, dict):
            raise ValueError("stage completion result must be an object")
        if isinstance(artifact_records, (str, bytes, bytearray)):
            raise ValueError("artifact records must be a sequence of objects")
        safe_artifact_records = sanitize_for_storage(list(artifact_records))
        if not isinstance(safe_artifact_records, list) or any(
            not isinstance(item, dict) for item in safe_artifact_records
        ):
            raise ValueError("artifact records must be a sequence of objects")
        if safe_artifact_records and safe_stage_result.get("artifacts") not in (
            None,
            [],
        ):
            raise ValueError("atomic artifact records require an empty public artifact list")
        # The linked database row is authoritative.  A worker result must not
        # be able to replace its attempt identity with an untrusted field.
        safe_stage_result.pop("stage_attempt_id", None)
        if provider_task_record_id is not None:
            self._validate_provider_task_record_id(provider_task_record_id)
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if attempt is None:
                raise KeyError("stage attempt not found")
            if attempt["job_id"] != job_id:
                raise ValueError("stage attempt is linked to another job")

            run = connection.execute(
                "SELECT production_id FROM runs WHERE id=?", (attempt["run_id"],)
            ).fetchone()
            if (
                run is None
                or job["production_id"] != attempt["production_id"]
                or attempt["production_id"] != run["production_id"]
            ):
                raise ValueError("job and stage attempt production do not match")

            if job["status"] != "running" or attempt["status"] != "running":
                raise AtomicCompletionError(
                    "atomic completion requires a running job and stage attempt",
                    code="atomic_completion_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )

            provider_task: sqlite3.Row | None = None
            bound_provider_task = connection.execute(
                "SELECT * FROM provider_tasks WHERE current_stage_attempt_id=? "
                "AND current_job_id=?",
                (stage_attempt_id, job_id),
            ).fetchone()
            if provider_task_record_id is None and bound_provider_task is not None:
                raise ValueError("bound provider task completion record is required")
            if provider_task_record_id is not None:
                provider_task = connection.execute(
                    "SELECT * FROM provider_tasks WHERE id=?",
                    (provider_task_record_id,),
                ).fetchone()
                if provider_task is None:
                    raise KeyError("provider task not found")
                result_provider_task_id = safe_stage_result.get("provider_task_id")
                if (
                    (
                        bound_provider_task is not None
                        and bound_provider_task["id"] != provider_task["id"]
                    )
                    or provider_task["status"] not in {"submitted", "recovering"}
                    or provider_task["production_id"] != attempt["production_id"]
                    or provider_task["run_id"] != attempt["run_id"]
                    or provider_task["stage"] != attempt["stage"]
                    or provider_task["cache_key"] != attempt["cache_key"]
                    or provider_task["current_stage_attempt_id"] != stage_attempt_id
                    or provider_task["current_job_id"] != job_id
                    or provider_task["provider_task_id"] is None
                    or result_provider_task_id != provider_task["provider_task_id"]
                    or safe_stage_result.get("provider") != provider_task["provider"]
                ):
                    raise ValueError("provider task completion provenance is invalid")

            if safe_artifact_records:
                safe_stage_result["artifacts"] = [
                    self._register_studio_artifact_in_transaction(
                        connection,
                        attempt["production_id"],
                        artifact,
                        timestamp=timestamp,
                    )
                    for artifact in safe_artifact_records
                ]
            safe_job_result = {
                **safe_stage_result,
                "stage_attempt_id": stage_attempt_id,
            }

            connection.execute(
                "UPDATE jobs SET status='succeeded', completed_at=?, result_json=?, "
                "error_code=NULL, error_message=NULL "
                "WHERE id=? AND status='running'",
                (
                    timestamp,
                    _json(safe_job_result),
                    job_id,
                ),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "job stopped before atomic completion could commit",
                    code="atomic_completion_not_active",
                    job_status="unknown",
                    stage_status=attempt["status"],
                )
            connection.execute(
                "UPDATE stage_attempts SET status='succeeded', completed_at=?, "
                "result_json=?, error_code=NULL, error_message=NULL "
                "WHERE id=? AND status='running'",
                (timestamp, _json(safe_stage_result), stage_attempt_id),
            )
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                raise AtomicCompletionError(
                    "stage attempt stopped before atomic completion could commit",
                    code="atomic_completion_not_active",
                    job_status="succeeded",
                    stage_status="unknown",
                )

            if provider_task is not None:
                connection.execute(
                    "UPDATE provider_tasks SET status='succeeded', updated_at=?, completed_at=?, "
                    "last_observed_at=?, request_ciphertext=NULL, error_code=NULL, error_message=NULL "
                    "WHERE id=? AND status IN ('submitted', 'recovering') "
                    "AND current_stage_attempt_id=? AND current_job_id=? "
                    "AND provider_task_id=?",
                    (
                        timestamp,
                        timestamp,
                        timestamp,
                        provider_task["id"],
                        stage_attempt_id,
                        job_id,
                        provider_task["provider_task_id"],
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "provider task changed before atomic completion could commit",
                        code="atomic_completion_not_active",
                        job_status="succeeded",
                        stage_status="succeeded",
                    )
                self._finalize_pipeline_provider_terminal(
                    connection,
                    run_id=attempt["run_id"],
                    provider_task_record_id=provider_task["id"],
                    provider_status="succeeded",
                    timestamp=timestamp,
                    error_code=None,
                    error_message=None,
                )

            if attempt["stage"] == "video_generation":
                if job["kind"] != "local_video_generation":
                    raise ValueError("pipeline video checkpoint job kind is invalid")
                self._checkpoint_pipeline_video_completion(
                    connection,
                    run_id=attempt["run_id"],
                    production_id=attempt["production_id"],
                    source_job_id=job_id,
                    source_stage_attempt_id=stage_attempt_id,
                    timestamp=timestamp,
                )

            self._append_event(
                connection,
                "run",
                attempt["run_id"],
                "stage.attempt.succeeded",
                {
                    "attempt_id": attempt["id"],
                    "production_id": attempt["production_id"],
                    "stage": attempt["stage"],
                    "attempt": attempt["attempt"],
                    "cache_key": attempt["cache_key"],
                    "job_id": job_id,
                    "result": safe_stage_result,
                    "error_code": None,
                    "error_message": None,
                },
                created_at=timestamp,
            )
            self._append_event(
                connection,
                "job",
                job_id,
                "job.succeeded",
                {
                    "result": safe_job_result,
                    "error_code": None,
                    "error_message": None,
                },
                created_at=timestamp,
            )
            if provider_task is not None:
                self._append_event(
                    connection,
                    "run",
                    attempt["run_id"],
                    "video_generation.provider_succeeded",
                    {
                        "provider_task_record_id": provider_task["id"],
                        "production_id": attempt["production_id"],
                        "provider": provider_task["provider"],
                        "provider_task_id": provider_task["provider_task_id"],
                        "attempt_id": stage_attempt_id,
                        "job_id": job_id,
                        "cache_key": attempt["cache_key"],
                        "attempt_sequence": provider_task["attempt_sequence"],
                    },
                    created_at=timestamp,
                )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            assert updated_job is not None and updated_attempt is not None
            committed = {
                "committed": True,
                "job": self._job_dict(updated_job),
                "stage_attempt": self._stage_attempt_dict(updated_attempt),
            }
            if provider_task is not None:
                updated_provider_task = connection.execute(
                    "SELECT * FROM provider_tasks WHERE id=?", (provider_task["id"],)
                ).fetchone()
                assert updated_provider_task is not None
                committed["provider_task"] = self._provider_task_dict(
                    updated_provider_task
                )
        return committed

    def fail_job_with_stage_attempt(
        self,
        job_id: str,
        stage_attempt_id: str,
        *,
        error_code: str,
        error_message: str,
        provider_task_record_id: str | None = None,
    ) -> dict[str, Any]:
        """Fail a linked job/stage and definite provider failure atomically.

        JobManager uses this when work returned an atomic completion envelope
        but final artifact registration or terminal commit was rejected.  A
        partial failure is not accepted: the linked pair either becomes
        failed together, is already terminal together, or this method raises.
        A bound ComfyUI task transitions to ``failed``, ``ambiguous``, or
        ``recovery_blocked`` from the bounded worker error code in this same
        transaction; only a definite provider failure clears recovery bytes.
        """

        timestamp = utc_now()
        safe_code = str(sanitize_for_storage(error_code or "job_failed"))[:128]
        safe_message = str(sanitize_for_storage(error_message or ""))[:1000] or None
        if provider_task_record_id is not None:
            self._validate_provider_task_record_id(provider_task_record_id)
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            if job is None:
                raise KeyError("job not found")
            if attempt is None:
                raise KeyError("stage attempt not found")
            if attempt["job_id"] != job_id:
                raise ValueError("stage attempt is linked to another job")
            run = connection.execute(
                "SELECT production_id FROM runs WHERE id=?", (attempt["run_id"],)
            ).fetchone()
            if (
                run is None
                or job["production_id"] != attempt["production_id"]
                or attempt["production_id"] != run["production_id"]
            ):
                raise ValueError("job and stage attempt production do not match")

            if provider_task_record_id is None:
                provider_task = connection.execute(
                    "SELECT * FROM provider_tasks WHERE current_stage_attempt_id=? "
                    "AND current_job_id=?",
                    (stage_attempt_id, job_id),
                ).fetchone()
            else:
                provider_task = connection.execute(
                    "SELECT * FROM provider_tasks WHERE id=?",
                    (provider_task_record_id,),
                ).fetchone()
                if (
                    provider_task is None
                    or provider_task["current_stage_attempt_id"] != stage_attempt_id
                    or provider_task["current_job_id"] != job_id
                    or provider_task["production_id"] != attempt["production_id"]
                    or provider_task["run_id"] != attempt["run_id"]
                    or provider_task["stage"] != attempt["stage"]
                    or provider_task["cache_key"] != attempt["cache_key"]
                ):
                    raise ValueError("provider task failure provenance is invalid")
            provider_failure_status = (
                "failed"
                if safe_code in _PROVIDER_TASK_DEFINITE_FAILURE_CODES
                else (
                    "ambiguous"
                    if safe_code == "comfyui_submission_unknown"
                    else "recovery_blocked"
                )
            )
            terminalize_provider = bool(
                provider_task is not None
                and provider_task["status"] not in _PROVIDER_TASK_TERMINAL_STATUSES
            )

            pair_already_terminal = (
                job["status"] in {"failed", "interrupted"}
                and attempt["status"] == "failed"
            )
            privacy_cleanup_override = bool(
                safe_code
                in {
                    "windows_capture_cleanup_failed",
                    "windows_capture_cleanup_required",
                }
                and job["kind"] == "local_windows_capture"
                and job["status"] == "interrupted"
                and job["error_code"] == "process_interrupted"
                and attempt["status"] == "failed"
                and attempt["error_code"] == "process_interrupted"
                and attempt["stage"] == "screen_capture"
            )
            if privacy_cleanup_override:
                connection.execute(
                    "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                    "error_code=?, error_message=? WHERE id=? AND status='interrupted' "
                    "AND error_code='process_interrupted'",
                    (timestamp, safe_code, safe_message, job_id),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "Windows capture cleanup failure changed concurrently",
                        code="atomic_failure_not_active",
                        job_status="interrupted",
                        stage_status="failed",
                    )
                connection.execute(
                    "UPDATE stage_attempts SET completed_at=?, result_json=NULL, "
                    "error_code=?, error_message=? WHERE id=? AND status='failed' "
                    "AND error_code='process_interrupted'",
                    (timestamp, safe_code, safe_message, stage_attempt_id),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "Windows capture cleanup attempt changed concurrently",
                        code="atomic_failure_not_active",
                        job_status="failed",
                        stage_status="failed",
                    )
                self._append_event(
                    connection,
                    "job",
                    job_id,
                    "job.failed",
                    {
                        "kind": job["kind"],
                        "production_id": job["production_id"],
                        "error_code": safe_code,
                        "error_message": safe_message,
                    },
                    created_at=timestamp,
                )
                self._append_event(
                    connection,
                    "run",
                    attempt["run_id"],
                    "stage.attempt.failed",
                    {
                        "attempt_id": attempt["id"],
                        "production_id": attempt["production_id"],
                        "stage": attempt["stage"],
                        "attempt": attempt["attempt"],
                        "cache_key": attempt["cache_key"],
                        "result": None,
                        "error_code": safe_code,
                        "error_message": safe_message,
                    },
                    created_at=timestamp,
                )
                updated_job = connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                updated_attempt = connection.execute(
                    "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
                ).fetchone()
                assert updated_job is not None and updated_attempt is not None
                return {
                    "committed": True,
                    "job": self._job_dict(updated_job),
                    "stage_attempt": self._stage_attempt_dict(updated_attempt),
                }
            if pair_already_terminal and not terminalize_provider:
                return {
                    "committed": False,
                    "job": self._job_dict(job),
                    "stage_attempt": self._stage_attempt_dict(attempt),
                }
            if not pair_already_terminal and (
                job["status"] != "running" or attempt["status"] not in {
                "queued",
                "running",
                }
            ):
                raise AtomicCompletionError(
                    "atomic failure requires a running job and active stage attempt",
                    code="atomic_failure_not_active",
                    job_status=job["status"],
                    stage_status=attempt["status"],
                )

            if not pair_already_terminal:
                connection.execute(
                    "UPDATE stage_attempts SET status='failed', completed_at=?, "
                    "result_json=NULL, error_code=?, error_message=? "
                    "WHERE id=? AND status IN ('queued', 'running')",
                    (timestamp, safe_code, safe_message, stage_attempt_id),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "stage attempt changed before atomic failure could commit",
                        code="atomic_failure_not_active",
                        job_status=job["status"],
                        stage_status="unknown",
                    )
                connection.execute(
                    "UPDATE jobs SET status='failed', completed_at=?, result_json=NULL, "
                    "error_code=?, error_message=? WHERE id=? AND status='running'",
                    (timestamp, safe_code, safe_message, job_id),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "job changed before atomic failure could commit",
                        code="atomic_failure_not_active",
                        job_status="unknown",
                        stage_status="failed",
                    )

            if terminalize_provider and provider_task is not None:
                connection.execute(
                    "UPDATE provider_tasks SET status=?, updated_at=?, completed_at=?, "
                    "last_observed_at=CASE WHEN ? THEN ? ELSE last_observed_at END, "
                    "current_stage_attempt_id=NULL, current_job_id=NULL, "
                    "request_ciphertext=CASE WHEN ? THEN NULL ELSE request_ciphertext END, "
                    "error_code=?, error_message=? "
                    "WHERE id=? AND current_stage_attempt_id=? AND current_job_id=? "
                    "AND status NOT IN ('succeeded', 'failed')",
                    (
                        provider_failure_status,
                        timestamp,
                        timestamp if provider_failure_status == "failed" else None,
                        int(provider_failure_status == "failed"),
                        timestamp,
                        int(provider_failure_status == "failed"),
                        safe_code,
                        safe_message,
                        provider_task["id"],
                        stage_attempt_id,
                        job_id,
                    ),
                )
                if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                    raise AtomicCompletionError(
                        "provider task changed before atomic failure could commit",
                        code="atomic_failure_not_active",
                        job_status="failed",
                        stage_status="failed",
                    )
                if provider_failure_status == "failed":
                    self._finalize_pipeline_provider_terminal(
                        connection,
                        run_id=attempt["run_id"],
                        provider_task_record_id=provider_task["id"],
                        provider_status="failed",
                        timestamp=timestamp,
                        error_code=safe_code,
                        error_message=safe_message,
                    )

            if not pair_already_terminal:
                self._append_event(
                    connection,
                    "run",
                    attempt["run_id"],
                    "stage.attempt.failed",
                    {
                        "attempt_id": attempt["id"],
                        "production_id": attempt["production_id"],
                        "stage": attempt["stage"],
                        "attempt": attempt["attempt"],
                        "cache_key": attempt["cache_key"],
                        "result": None,
                        "error_code": safe_code,
                        "error_message": safe_message,
                    },
                    created_at=timestamp,
                )
                self._append_event(
                    connection,
                    "job",
                    job_id,
                    "job.failed",
                    {
                        "result": None,
                        "error_code": safe_code,
                        "error_message": safe_message,
                    },
                    created_at=timestamp,
                )
            if terminalize_provider and provider_task is not None:
                self._append_event(
                    connection,
                    "run",
                    attempt["run_id"],
                    (
                        "video_generation.provider_failed"
                        if provider_failure_status == "failed"
                        else "video_generation.provider_state_changed"
                    ),
                    {
                        "provider_task_record_id": provider_task["id"],
                        "production_id": attempt["production_id"],
                        "provider": provider_task["provider"],
                        "provider_task_id": provider_task["provider_task_id"],
                        "attempt_id": stage_attempt_id,
                        "job_id": job_id,
                        "cache_key": attempt["cache_key"],
                        "attempt_sequence": provider_task["attempt_sequence"],
                        "status": provider_failure_status,
                        "error_code": safe_code,
                    },
                    created_at=timestamp,
                )
            updated_job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            updated_attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE id=?", (stage_attempt_id,)
            ).fetchone()
            assert updated_job is not None and updated_attempt is not None
            committed = {
                "committed": True,
                "job": self._job_dict(updated_job),
                "stage_attempt": self._stage_attempt_dict(updated_attempt),
            }
            if terminalize_provider and provider_task is not None:
                updated_provider = connection.execute(
                    "SELECT * FROM provider_tasks WHERE id=?", (provider_task["id"],)
                ).fetchone()
                assert updated_provider is not None
                committed["provider_task"] = self._provider_task_dict(updated_provider)
            return committed

    def update_job(
        self,
        job_id: str,
        status: str,
        *,
        result: Any = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        timestamp = utc_now()
        safe_result = sanitize_for_storage(result)
        safe_error = str(sanitize_for_storage(error_message or ""))[:1000] or None
        effective_error_code = error_code
        effective_error_message = safe_error
        if status == "interrupted":
            effective_error_code = error_code or _DEFAULT_INTERRUPTED_ERROR_CODE
            effective_error_message = (
                safe_error or _DEFAULT_INTERRUPTED_ERROR_MESSAGE
            )
        with self.transaction() as connection:
            if status == "running":
                connection.execute(
                    "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
                    (timestamp, job_id),
                )
            elif status == "succeeded":
                connection.execute(
                    "UPDATE jobs SET status=?, completed_at=?, result_json=?, error_code=?, error_message=? "
                    "WHERE id=? AND status='running'",
                    (
                        status,
                        timestamp,
                        _json(safe_result) if result is not None else None,
                        effective_error_code,
                        effective_error_message,
                        job_id,
                    ),
                )
            elif status == "failed":
                # A job can fail during setup before it reaches the worker, or
                # while running. Both are terminal and must be durable.
                connection.execute(
                    "UPDATE jobs SET status='failed', completed_at=?, result_json=?, error_code=?, error_message=? "
                    "WHERE id=? AND status IN ('queued', 'running')",
                    (
                        timestamp,
                        _json(safe_result) if result is not None else None,
                        effective_error_code,
                        effective_error_message,
                        job_id,
                    ),
                )
            elif status == "interrupted":
                connection.execute(
                    "UPDATE jobs SET status='interrupted', completed_at=?, result_json=NULL, "
                    "error_code=?, error_message=? WHERE id=? AND status IN ('queued', 'running')",
                    (
                        timestamp,
                        effective_error_code,
                        effective_error_message,
                        job_id,
                    ),
                )
            else:
                raise ValueError("unsupported job state")
            if connection.execute("SELECT changes() AS count").fetchone()["count"] != 1:
                return
            self._append_event(
                connection,
                "job",
                job_id,
                f"job.{status}",
                {
                    "result": safe_result if status == "succeeded" else None,
                    "error_code": (
                        effective_error_code
                        if status in {"failed", "interrupted"}
                        else None
                    ),
                    "error_message": (
                        effective_error_message
                        if status in {"failed", "interrupted"}
                        else None
                    ),
                },
                created_at=timestamp,
            )

    def update_job_progress(self, job_id: str, progress: int, phase: str) -> None:
        """Persist bounded, non-terminal progress for a running local job.

        Progress is deliberately kept in the replaceable running result.  The
        atomic terminal transition overwrites it with the verified stage
        result, so intermediate telemetry can never masquerade as an output.
        """

        validate_identifier(job_id, label="job id")
        if (
            isinstance(progress, bool)
            or not isinstance(progress, int)
            or not 0 <= progress <= 99
        ):
            raise ValueError("job progress must be an integer from 0 through 99")
        if (
            not isinstance(phase, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", phase) is None
        ):
            raise ValueError("job progress phase is invalid")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET result_json=? WHERE id=? AND status='running'",
                (_json({"progress": progress, "progress_phase": phase}), job_id),
            )

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = _loads(row["result_json"], None)
        output = {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "production_id": row["production_id"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "payload": _loads(row["payload_json"], {}),
            "result": result,
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"]
                else None
            ),
        }
        if row["kind"] in {"local_screen_capture", "local_windows_capture"}:
            progress = None
            phase = None
            if row["status"] == "queued":
                progress = 0
                phase = "queued"
            elif row["status"] == "running" and isinstance(result, dict):
                candidate = result.get("progress")
                candidate_phase = result.get("progress_phase")
                if isinstance(candidate, int) and not isinstance(candidate, bool):
                    progress = max(0, min(99, candidate))
                if isinstance(candidate_phase, str):
                    phase = candidate_phase
            elif row["status"] == "succeeded":
                progress = 100
                phase = "completed"
            if progress is not None:
                output["progress"] = progress
            if phase is not None:
                output["progress_phase"] = phase
        return output

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job_dict(row) if row else None

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job_dict(row) for row in rows]

    def find_active_windows_capture_job(self) -> dict[str, Any] | None:
        """Return the single active native capture admitted in this workspace.

        Native desktop/audio recording is intentionally exclusive.  The
        service serializes admission in-process, while this exact durable read
        lets an HTTP retry reuse the already-admitted operation instead of
        enqueueing a recording that could begin later without a fresh click.
        """

        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE kind='local_windows_capture' "
                "AND status IN ('queued', 'running') "
                "ORDER BY created_at, rowid LIMIT 2"
            ).fetchall()
        if len(rows) > 1:
            raise sqlite3.IntegrityError(
                "multiple active Windows capture jobs violate exclusive admission"
            )
        return self._job_dict(rows[0]) if rows else None

    def list_interrupted_windows_capture_jobs(
        self, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List bounded native captures stopped by process shutdown/restart."""

        bounded = max(1, min(int(limit), 1000))
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE kind='local_windows_capture' "
                "AND status='interrupted' AND error_code='process_interrupted' "
                "ORDER BY completed_at DESC, rowid DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self._job_dict(row) for row in rows]

    def list_windows_capture_cleanup_candidates(
        self, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List only exact native-capture lineages requiring startup cleanup.

        General failed capture jobs are intentionally excluded. A row is a
        candidate only when restart interrupted an active native capture, or
        the linked job/attempt durably records one of the two fixed privacy
        cleanup errors.
        """

        bounded = max(1, min(int(limit), 1000))
        with self.session() as connection:
            rows = connection.execute(
                "SELECT DISTINCT j.* FROM jobs j "
                "LEFT JOIN stage_attempts a ON a.job_id=j.id "
                "WHERE j.kind='local_windows_capture' AND ("
                "(j.status='interrupted' AND j.error_code='process_interrupted') "
                "OR j.error_code IN "
                "('windows_capture_cleanup_failed','windows_capture_cleanup_required') "
                "OR a.error_code IN "
                "('windows_capture_cleanup_failed','windows_capture_cleanup_required')"
                ") ORDER BY j.completed_at DESC, j.rowid DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self._job_dict(row) for row in rows]

    def find_latest_job_for_run(
        self, kind: str, production_id: str, run_id: str
    ) -> dict[str, Any] | None:
        """Return the newest job of ``kind`` durably bound to one run.

        ``run_id`` lives inside the sanitized immutable job payload, so the
        final comparison is performed after JSON decoding.  Production and
        kind predicates keep the scan bounded to the relevant audit stream.
        """

        validate_identifier(production_id, label="production id")
        validate_identifier(run_id, label="run id")
        if not isinstance(kind, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind):
            raise ValueError("invalid job kind")
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE kind=? AND production_id=? ORDER BY rowid DESC",
                (kind, production_id),
            ).fetchall()
        for row in rows:
            job = self._job_dict(row)
            payload = job.get("payload")
            if isinstance(payload, dict) and payload.get("run_id") == run_id:
                return job
        return None
