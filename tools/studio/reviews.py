from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .security import canonical_json, sanitize_for_storage, stable_id


REVIEW_SCHEMA_VERSION = 1
REVIEW_EVENT_TYPES = frozenset(
    {
        "review.created",
        "review.resolved",
        "review.decision_set",
        "review.revision_plan_created",
    }
)
REVIEW_CATEGORIES = frozenset({"creative", "rights", "public_release"})
REVIEW_DECISIONS = frozenset(
    {"pending", "approved", "changes_required", "not_applicable"}
)
REVIEW_ACTION_TYPES = frozenset(
    {"created", "resolved", "decision_set", "revision_plan_created"}
)
REVIEW_CREATE_KEYS = frozenset(
    {
        "schema_version",
        "idempotency_key",
        "artifact_id",
        "revision_id",
        "run_id",
        "cut_id",
        "timecode_ms",
        "category",
        "body",
        "actor",
    }
)
REVIEW_RESOLVE_KEYS = frozenset(
    {"schema_version", "idempotency_key", "actor", "note"}
)
REVIEW_DECISION_KEYS = frozenset(
    {"schema_version", "idempotency_key", "actor", "decision", "note"}
)
REVIEW_PLAN_KEYS = frozenset(
    {"schema_version", "idempotency_key", "actor"}
)

_IDEMPOTENCY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_ARTIFACT_RE = re.compile(r"art_[0-9a-f]{32}")
_REVISION_RE = re.compile(r"rev_[0-9a-f]{32}")
_RUN_RE = re.compile(r"run_[0-9a-f]{32}")
_CUT_RE = re.compile(r"cut_[0-9a-f]{32}")
_REVIEW_RE = re.compile(r"review_[0-9a-f]{32}")
_ACTION_RE = re.compile(r"review_action_[0-9a-f]{32}")
_PLAN_RE = re.compile(r"review_plan_[0-9a-f]{32}")
_SHA256_RE = re.compile(r"[0-9A-F]{64}")


class ReviewValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_review_request"):
        super().__init__(message)
        self.code = code


def _exact_object(value: Any, keys: frozenset[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewValidationError(f"{label} must contain exactly {sorted(keys)}")
    if value.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ReviewValidationError("schema_version must be 1")
    return value


def _bounded_text(
    value: Any,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ReviewValidationError(f"{label} must be canonical text")
    if not minimum <= len(value) <= maximum:
        raise ReviewValidationError(
            f"{label} must contain between {minimum} and {maximum} characters"
        )
    safe = sanitize_for_storage(value)
    if not isinstance(safe, str):
        raise ReviewValidationError(f"{label} is invalid")
    return safe


def _identifier(value: Any, pattern: re.Pattern[str], *, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ReviewValidationError(f"{label} is invalid")
    return value


def _idempotency_key(value: Any) -> str:
    return _identifier(value, _IDEMPOTENCY_RE, label="idempotency_key")


def validate_review_create_payload(value: Any) -> dict[str, Any]:
    body = _exact_object(value, REVIEW_CREATE_KEYS, label="review request")
    timecode = body.get("timecode_ms")
    if (
        isinstance(timecode, bool)
        or not isinstance(timecode, int)
        or not 0 <= timecode <= 86_400_000
    ):
        raise ReviewValidationError("timecode_ms must be an integer from 0 to 86400000")
    category = body.get("category")
    if category not in REVIEW_CATEGORIES:
        raise ReviewValidationError("category is invalid")
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "idempotency_key": _idempotency_key(body.get("idempotency_key")),
        "artifact_id": _identifier(body.get("artifact_id"), _ARTIFACT_RE, label="artifact_id"),
        "revision_id": _identifier(body.get("revision_id"), _REVISION_RE, label="revision_id"),
        "run_id": _identifier(body.get("run_id"), _RUN_RE, label="run_id"),
        "cut_id": _identifier(body.get("cut_id"), _CUT_RE, label="cut_id"),
        "timecode_ms": timecode,
        "category": category,
        "body": _bounded_text(body.get("body"), label="body", minimum=1, maximum=2_000),
        "actor": _bounded_text(body.get("actor"), label="actor", minimum=1, maximum=80),
    }


def validate_review_resolve_payload(value: Any) -> dict[str, Any]:
    body = _exact_object(value, REVIEW_RESOLVE_KEYS, label="review resolution")
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "idempotency_key": _idempotency_key(body.get("idempotency_key")),
        "actor": _bounded_text(body.get("actor"), label="actor", minimum=1, maximum=80),
        "note": _bounded_text(body.get("note"), label="note", minimum=0, maximum=1_000),
    }


def validate_review_decision_payload(value: Any) -> dict[str, Any]:
    body = _exact_object(value, REVIEW_DECISION_KEYS, label="review decision")
    decision = body.get("decision")
    if decision not in REVIEW_DECISIONS - {"pending"}:
        raise ReviewValidationError("decision is invalid")
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "idempotency_key": _idempotency_key(body.get("idempotency_key")),
        "actor": _bounded_text(body.get("actor"), label="actor", minimum=1, maximum=80),
        "decision": decision,
        "note": _bounded_text(body.get("note"), label="note", minimum=0, maximum=1_000),
    }


def validate_review_plan_payload(value: Any) -> dict[str, Any]:
    body = _exact_object(value, REVIEW_PLAN_KEYS, label="review revision plan")
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "idempotency_key": _idempotency_key(body.get("idempotency_key")),
        "actor": _bounded_text(body.get("actor"), label="actor", minimum=1, maximum=80),
    }


def _request_digest(operation: str, value: dict[str, Any]) -> str:
    encoded = canonical_json({"operation": operation, "request": value}).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _action_identity(thread: dict[str, Any]) -> dict[str, Any]:
    identity = thread.get("identity")
    if not isinstance(identity, dict):
        raise ReviewValidationError("review identity is unavailable", code="review_integrity_error")
    return dict(identity)


def build_review_create_action(production_id: str, request: dict[str, Any]) -> dict[str, Any]:
    review_id = stable_id(
        "review", f"{production_id}\0{request['idempotency_key']}\0created"
    )
    action_id = stable_id(
        "review_action", f"{production_id}\0{request['idempotency_key']}\0created"
    )
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "action_id": action_id,
        "review_id": review_id,
        "action": "created",
        "idempotency_key": request["idempotency_key"],
        "request_digest": _request_digest("created", request),
        "actor": request["actor"],
        "identity": {
            "artifact_id": request["artifact_id"],
            "revision_id": request["revision_id"],
            "run_id": request["run_id"],
            "cut_id": request["cut_id"],
            "timecode_ms": request["timecode_ms"],
        },
        "category": request["category"],
        "decision": "pending",
        "body": request["body"],
        "note": "",
        "revision_plan": None,
    }


def build_review_resolve_action(
    production_id: str, thread: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "action_id": stable_id(
            "review_action", f"{production_id}\0{request['idempotency_key']}\0resolved"
        ),
        "review_id": thread["id"],
        "action": "resolved",
        "idempotency_key": request["idempotency_key"],
        "request_digest": _request_digest("resolved", request),
        "actor": request["actor"],
        "identity": _action_identity(thread),
        "category": thread["category"],
        "decision": thread["decision"],
        "body": thread["body"],
        "note": request["note"],
        "revision_plan": None,
    }


def build_review_decision_action(
    production_id: str, thread: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "action_id": stable_id(
            "review_action", f"{production_id}\0{request['idempotency_key']}\0decision_set"
        ),
        "review_id": thread["id"],
        "action": "decision_set",
        "idempotency_key": request["idempotency_key"],
        "request_digest": _request_digest("decision_set", request),
        "actor": request["actor"],
        "identity": _action_identity(thread),
        "category": thread["category"],
        "decision": request["decision"],
        "body": thread["body"],
        "note": request["note"],
        "revision_plan": None,
    }


def build_review_revision_plan_action(
    production_id: str, thread: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    identity = _action_identity(thread)
    plan_id = stable_id(
        "review_plan", f"{production_id}\0{request['idempotency_key']}\0{thread['id']}"
    )
    identity_digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()
    revision_plan = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "id": plan_id,
        "status": "planned_not_executed",
        "render_status": "not_started",
        "exact_cut_identity": identity,
        "identity_digest": identity_digest,
        "affected_stages": ["video_generation", "timeline", "assembly", "qc"],
        "reuse_policy": "reuse_all_other_exact_cut_artifacts",
        "execution": {
            "adapter": "m4_cut_revision_job_v1",
            "connected": False,
            "status": "not_connected",
            "job_id": None,
            "endpoint_template": "/api/productions/{production_id}/cuts/{cut_id}/reruns",
            "request": {
                "schema_version": REVIEW_SCHEMA_VERSION,
                "revision_plan_id": plan_id,
                "production_id": production_id,
                "review_id": thread["id"],
                "revision_id": identity["revision_id"],
                "source_run_id": identity["run_id"],
                "source_artifact_id": identity["artifact_id"],
                "cut_id": identity["cut_id"],
                "timecode_ms": identity["timecode_ms"],
                "identity_digest": identity_digest,
            },
        },
    }
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "action_id": stable_id(
            "review_action", f"{production_id}\0{request['idempotency_key']}\0revision_plan_created"
        ),
        "review_id": thread["id"],
        "action": "revision_plan_created",
        "idempotency_key": request["idempotency_key"],
        "request_digest": _request_digest("revision_plan_created", request),
        "actor": request["actor"],
        "identity": identity,
        "category": thread["category"],
        "decision": thread["decision"],
        "body": thread["body"],
        "note": "",
        "revision_plan": revision_plan,
    }


def validate_review_action(value: Any) -> dict[str, Any]:
    keys = {
        "schema_version",
        "action_id",
        "review_id",
        "action",
        "idempotency_key",
        "request_digest",
        "actor",
        "identity",
        "category",
        "decision",
        "body",
        "note",
        "revision_plan",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewValidationError("review action has an invalid shape", code="review_integrity_error")
    action = value.get("action")
    identity = value.get("identity")
    if (
        value.get("schema_version") != REVIEW_SCHEMA_VERSION
        or not isinstance(action, str)
        or action not in REVIEW_ACTION_TYPES
        or not isinstance(identity, dict)
        or set(identity) != {"artifact_id", "revision_id", "run_id", "cut_id", "timecode_ms"}
        or value.get("category") not in REVIEW_CATEGORIES
        or value.get("decision") not in REVIEW_DECISIONS
    ):
        raise ReviewValidationError("review action is invalid", code="review_integrity_error")
    normalized = dict(value)
    _identifier(normalized.get("action_id"), _ACTION_RE, label="action_id")
    _identifier(normalized.get("review_id"), _REVIEW_RE, label="review_id")
    _idempotency_key(normalized.get("idempotency_key"))
    _identifier(normalized.get("request_digest"), _SHA256_RE, label="request_digest")
    _bounded_text(normalized.get("actor"), label="actor", minimum=1, maximum=80)
    _identifier(identity.get("artifact_id"), _ARTIFACT_RE, label="artifact_id")
    _identifier(identity.get("revision_id"), _REVISION_RE, label="revision_id")
    _identifier(identity.get("run_id"), _RUN_RE, label="run_id")
    _identifier(identity.get("cut_id"), _CUT_RE, label="cut_id")
    timecode = identity.get("timecode_ms")
    if isinstance(timecode, bool) or not isinstance(timecode, int) or not 0 <= timecode <= 86_400_000:
        raise ReviewValidationError("review timecode is invalid", code="review_integrity_error")
    _bounded_text(normalized.get("body"), label="body", minimum=1, maximum=2_000)
    _bounded_text(normalized.get("note"), label="note", minimum=0, maximum=1_000)
    plan = normalized.get("revision_plan")
    if action == "revision_plan_created":
        if not isinstance(plan, dict) or plan.get("status") != "planned_not_executed":
            raise ReviewValidationError("revision plan is invalid", code="review_integrity_error")
        _identifier(plan.get("id"), _PLAN_RE, label="revision_plan.id")
    elif plan is not None:
        raise ReviewValidationError("unexpected revision plan", code="review_integrity_error")
    return normalized


def public_review_action(action: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": action["action_id"],
        "type": action["action"],
        "actor": action["actor"],
        "decision": action["decision"],
        "note": action["note"],
        "created_at": event["created_at"],
        "event_id": event["id"],
        "event_hash": event["event_hash"],
        "revision_plan": action["revision_plan"],
    }


def _validate_revision_plan_contract(
    plan: Any,
    *,
    production_id: str,
    review_id: str,
    identity: dict[str, Any],
) -> None:
    plan_keys = {
        "schema_version",
        "id",
        "status",
        "render_status",
        "exact_cut_identity",
        "identity_digest",
        "affected_stages",
        "reuse_policy",
        "execution",
    }
    execution_keys = {
        "adapter",
        "connected",
        "status",
        "job_id",
        "endpoint_template",
        "request",
    }
    request_keys = {
        "schema_version",
        "revision_plan_id",
        "production_id",
        "review_id",
        "revision_id",
        "source_run_id",
        "source_artifact_id",
        "cut_id",
        "timecode_ms",
        "identity_digest",
    }
    if not isinstance(plan, dict) or set(plan) != plan_keys:
        raise ReviewValidationError("revision plan shape is invalid", code="review_integrity_error")
    execution = plan.get("execution")
    request = execution.get("request") if isinstance(execution, dict) else None
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()
    if (
        plan.get("schema_version") != REVIEW_SCHEMA_VERSION
        or plan.get("status") != "planned_not_executed"
        or plan.get("render_status") != "not_started"
        or plan.get("exact_cut_identity") != identity
        or plan.get("identity_digest") != digest
        or plan.get("affected_stages")
        != ["video_generation", "timeline", "assembly", "qc"]
        or plan.get("reuse_policy") != "reuse_all_other_exact_cut_artifacts"
        or not isinstance(execution, dict)
        or set(execution) != execution_keys
        or execution.get("adapter") != "m4_cut_revision_job_v1"
        or execution.get("connected") is not False
        or execution.get("status") != "not_connected"
        or execution.get("job_id") is not None
        or execution.get("endpoint_template")
        != "/api/productions/{production_id}/cuts/{cut_id}/reruns"
        or not isinstance(request, dict)
        or set(request) != request_keys
        or request.get("schema_version") != REVIEW_SCHEMA_VERSION
        or request.get("revision_plan_id") != plan.get("id")
        or request.get("production_id") != production_id
        or request.get("review_id") != review_id
        or request.get("revision_id") != identity["revision_id"]
        or request.get("source_run_id") != identity["run_id"]
        or request.get("source_artifact_id") != identity["artifact_id"]
        or request.get("cut_id") != identity["cut_id"]
        or request.get("timecode_ms") != identity["timecode_ms"]
        or request.get("identity_digest") != digest
    ):
        raise ReviewValidationError("revision plan is invalid", code="review_integrity_error")
    _identifier(plan.get("id"), _PLAN_RE, label="revision_plan.id")


def _validate_action_derivation(production_id: str, action: dict[str, Any]) -> None:
    action_type = action["action"]
    idempotency_key = action["idempotency_key"]
    expected_action_id = stable_id(
        "review_action", f"{production_id}\0{idempotency_key}\0{action_type}"
    )
    if action["action_id"] != expected_action_id:
        raise ReviewValidationError("review action identity is invalid", code="review_integrity_error")
    if action_type == "created":
        expected_review_id = stable_id(
            "review", f"{production_id}\0{idempotency_key}\0created"
        )
        request = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "idempotency_key": idempotency_key,
            **action["identity"],
            "category": action["category"],
            "body": action["body"],
            "actor": action["actor"],
        }
    elif action_type == "resolved":
        expected_review_id = action["review_id"]
        request = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "idempotency_key": idempotency_key,
            "actor": action["actor"],
            "note": action["note"],
        }
    elif action_type == "decision_set":
        expected_review_id = action["review_id"]
        request = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "idempotency_key": idempotency_key,
            "actor": action["actor"],
            "decision": action["decision"],
            "note": action["note"],
        }
    else:
        expected_review_id = action["review_id"]
        request = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "idempotency_key": idempotency_key,
            "actor": action["actor"],
        }
    if (
        action["review_id"] != expected_review_id
        or action["request_digest"] != _request_digest(action_type, request)
    ):
        raise ReviewValidationError("review action digest is invalid", code="review_integrity_error")


def review_snapshot(production_id: str, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    threads: dict[str, dict[str, Any]] = {}
    ordered_events = sorted(events, key=lambda item: int(item["id"]))
    for event in ordered_events:
        if event.get("event_type") not in REVIEW_EVENT_TYPES:
            continue
        action = validate_review_action(event.get("payload"))
        _validate_action_derivation(production_id, action)
        expected_event = f"review.{action['action']}"
        if event.get("event_type") != expected_event:
            raise ReviewValidationError("review event/action mismatch", code="review_integrity_error")
        review_id = action["review_id"]
        current = threads.get(review_id)
        if action["action"] == "created":
            if current is not None:
                raise ReviewValidationError("duplicate review creation", code="review_integrity_error")
            threads[review_id] = {
                "id": review_id,
                "status": "open",
                "category": action["category"],
                "decision": action["decision"],
                "body": action["body"],
                "actor": action["actor"],
                "created_at": event["created_at"],
                "updated_at": event["created_at"],
                "identity": action["identity"],
                "actions": [public_review_action(action, event)],
                "revision_plans": [],
            }
            continue
        if current is None:
            raise ReviewValidationError("review action has no creation", code="review_integrity_error")
        if (
            action["identity"] != current["identity"]
            or action["category"] != current["category"]
            or action["body"] != current["body"]
        ):
            raise ReviewValidationError("review action identity changed", code="review_integrity_error")
        if action["action"] == "resolved":
            if current["status"] != "open":
                raise ReviewValidationError("review is already resolved", code="review_already_resolved")
            current["status"] = "resolved"
        elif action["action"] == "decision_set":
            current["decision"] = action["decision"]
        elif action["action"] == "revision_plan_created":
            if current["status"] != "open":
                raise ReviewValidationError("resolved review cannot create a plan", code="review_already_resolved")
            _validate_revision_plan_contract(
                action["revision_plan"],
                production_id=production_id,
                review_id=review_id,
                identity=current["identity"],
            )
            current["revision_plans"].append(action["revision_plan"])
        current["updated_at"] = event["created_at"]
        current["actions"].append(public_review_action(action, event))

    reviews = sorted(
        threads.values(),
        key=lambda item: (item["created_at"], item["id"]),
        reverse=True,
    )
    gates: dict[str, dict[str, Any]] = {}
    for category in sorted(REVIEW_CATEGORIES):
        scoped = [item for item in reviews if item["category"] == category]
        decisions = [item["decision"] for item in scoped]
        if "changes_required" in decisions:
            decision = "changes_required"
        elif scoped and all(value == "not_applicable" for value in decisions):
            decision = "not_applicable"
        elif scoped and all(value in {"approved", "not_applicable"} for value in decisions):
            decision = "approved"
        else:
            decision = "pending"
        gates[category] = {
            "decision": decision,
            "review_count": len(scoped),
            "open_count": sum(item["status"] == "open" for item in scoped),
            "resolved_count": sum(item["status"] == "resolved" for item in scoped),
        }
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "production_id": production_id,
        "reviews": reviews,
        "gates": gates,
        "count": len(reviews),
        "open_count": sum(item["status"] == "open" for item in reviews),
    }


def review_by_id(snapshot: dict[str, Any], review_id: str) -> dict[str, Any]:
    _identifier(review_id, _REVIEW_RE, label="review_id")
    for review in snapshot.get("reviews", []):
        if review.get("id") == review_id:
            return review
    raise KeyError("review not found")


def validate_review_transition(snapshot: dict[str, Any], action: dict[str, Any]) -> None:
    normalized = validate_review_action(action)
    if normalized["action"] == "created":
        if any(item.get("id") == normalized["review_id"] for item in snapshot.get("reviews", [])):
            raise ReviewValidationError("review already exists", code="review_idempotency_conflict")
        return
    thread = review_by_id(snapshot, normalized["review_id"])
    if normalized["identity"] != thread["identity"] or normalized["category"] != thread["category"]:
        raise ReviewValidationError("review identity changed", code="review_integrity_error")
    if normalized["action"] in {"resolved", "revision_plan_created"} and thread["status"] != "open":
        raise ReviewValidationError("review is already resolved", code="review_already_resolved")


__all__ = [
    "REVIEW_EVENT_TYPES",
    "REVIEW_SCHEMA_VERSION",
    "ReviewValidationError",
    "build_review_create_action",
    "build_review_decision_action",
    "build_review_resolve_action",
    "build_review_revision_plan_action",
    "public_review_action",
    "review_by_id",
    "review_snapshot",
    "validate_review_action",
    "validate_review_create_payload",
    "validate_review_decision_payload",
    "validate_review_plan_payload",
    "validate_review_resolve_payload",
    "validate_review_transition",
]
