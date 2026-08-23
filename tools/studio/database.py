from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterator, Sequence

from .security import canonical_json, sanitize_for_storage, workspace_path


SCHEMA_VERSION = 3
MAX_EVENT_LINE_BYTES = 2 * 1024 * 1024
_RUN_EXECUTION_PROFILES = {"external", "local_sapi"}
_LOCAL_SAPI_ZERO_COST_STAGES = {"narration", "captions", "assembly", "qc"}
_DEFAULT_INTERRUPTED_ERROR_CODE = "process_interrupted"
_DEFAULT_INTERRUPTED_ERROR_MESSAGE = "The Studio process stopped."


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
    ``stage_attempt_id`` to that mapping; the envelope itself is never
    persisted as a public job result.
    """

    stage_attempt_id: str
    public_result: dict[str, Any]


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
                    immutable_digest TEXT NOT NULL
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
            # existing database.  Keep this migration idempotent for the v1
            # Studio databases already created by the MVP.
            run_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "execution_profile" not in run_columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN execution_profile TEXT NOT NULL DEFAULT 'external'"
                )
            attempt_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(stage_attempts)").fetchall()
            }
            if "job_id" not in attempt_columns:
                connection.execute("ALTER TABLE stage_attempts ADD COLUMN job_id TEXT")
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def interrupt_active_work(self) -> dict[str, int]:
        """Fail closed when a prior Studio process ended during active work."""

        timestamp = utc_now()
        counts = {"jobs": 0, "stage_attempts": 0}
        with self.transaction() as connection:
            active_jobs = connection.execute(
                "SELECT id, kind, production_id FROM jobs "
                "WHERE status IN ('queued', 'running') ORDER BY created_at, rowid"
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
        return counts

    def interrupt_job(self, job_id: str) -> bool:
        """Atomically interrupt one active job and append its audit event."""

        timestamp = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT id, kind, production_id FROM jobs "
                "WHERE id=? AND status IN ('queued', 'running')",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
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
            attempts = connection.execute(
                "SELECT * FROM stage_attempts WHERE job_id=? AND status IN ('queued', 'running') "
                "ORDER BY created_at, rowid",
                (job_id,),
            ).fetchall()
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

    def register_studio_artifact(self, production_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
        timestamp = utc_now()
        with self.transaction() as connection:
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
            self._append_event(
                connection,
                "production",
                production_id,
                "artifact.created",
                {"artifact_id": artifact["id"], "kind": artifact["kind"]},
                created_at=timestamp,
            )
        result = self.get_artifact(artifact["id"])
        assert result is not None
        return result

    @staticmethod
    def _production_dict(row: sqlite3.Row) -> dict[str, Any]:
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

    def list_productions(self) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT p.*,
                       (SELECT COUNT(*) FROM artifacts a
                        WHERE a.production_id=p.id AND a.available=1) AS artifact_count,
                       (SELECT COALESCE(SUM(a.bytes), 0) FROM artifacts a
                        WHERE a.production_id=p.id AND a.available=1) AS artifact_bytes,
                       (SELECT MAX(j.created_at) FROM jobs j
                        WHERE j.production_id=p.id) AS latest_job_at
                FROM productions p
                ORDER BY p.id
                """
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
            row = connection.execute("SELECT * FROM productions WHERE id=?", (production_id,)).fetchone()
        return self._production_dict(row) if row else None

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
            "SELECT * FROM productions WHERE id=?", (production_id,)
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
            return {
                "id": row["id"],
                "production_id": row["production_id"],
                "revision_id": row["revision_id"],
                "created_at": row["created_at"],
                "requested_stages": _loads(row["requested_stages_json"], []),
                "estimated_cost": money_from_minor(estimated, row["currency"]),
                "execution_profile": row["execution_profile"] or "external",
                "stage_attempts": self._stage_attempt_dicts(connection, row["id"]),
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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
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
            stages = safe_plan.get("affected_stages", [])
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
            run_digest = hashlib.sha256(canonical_json(run_payload).encode("utf-8")).hexdigest()
            connection.execute(
                "INSERT INTO runs(id, production_id, revision_id, created_at, requested_stages_json, estimated_cost_minor, currency, execution_profile, immutable_digest) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    production_id,
                    revision_id,
                    timestamp,
                    _json(stages),
                    estimated_cost_minor,
                    currency,
                    execution_profile,
                    run_digest,
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
                    },
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

    def restore_domain_records_from_events(self) -> dict[str, int]:
        """Rebuild revisions, runs, stage attempts, and approvals from verified mirrors."""
        restored = {"revisions": 0, "runs": 0, "stage_attempts": 0, "approvals": 0}
        with self.transaction() as connection:
            revision_events = connection.execute(
                "SELECT payload_json FROM events WHERE event_type='revision.created' ORDER BY id"
            ).fetchall()
            for event in revision_events:
                payload = _loads(event["payload_json"], {})
                revision = payload.get("revision") if isinstance(payload, dict) else None
                run = payload.get("run") if isinstance(payload, dict) else None
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
                        "INSERT OR IGNORE INTO runs(id, production_id, revision_id, created_at, requested_stages_json, estimated_cost_minor, currency, execution_profile, immutable_digest) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run["id"],
                            run["production_id"],
                            run["revision_id"],
                            run["created_at"],
                            _json(requested_stages),
                            estimated_minor,
                            currency,
                            str(run.get("execution_profile") or "external"),
                            run_digest,
                        ),
                    )
                    restored["runs"] += int(connection.total_changes > before)
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

    def complete_job_with_stage_attempt(
        self,
        job_id: str,
        stage_attempt_id: str,
        public_result: Any,
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
        # The linked database row is authoritative.  A worker result must not
        # be able to replace its attempt identity with an untrusted field.
        safe_stage_result.pop("stage_attempt_id", None)
        safe_job_result = {**safe_stage_result, "stage_attempt_id": stage_attempt_id}
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

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "production_id": row["production_id"],
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
