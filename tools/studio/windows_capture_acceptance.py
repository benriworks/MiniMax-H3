from __future__ import annotations

"""Deterministic live-acceptance policy for registered Windows captures.

This module is deliberately pure.  It does not capture pixels, inspect a
window, read an artifact, or call a network service.  The caller supplies a
successful, atomically registered ``local_windows_capture`` result and a raw
calibration/operator report.  The report is bound to the capture key and to
every registered artifact SHA-256 before any observation is recorded.

The report itself is still request-provided evidence.  A claimed calibration
tool digest or operator attestation is not proof that a registered calibration
Job ran, nor that a calibration evidence artifact was produced by that tool.
Consequently this v1 policy can preserve the report and calculate its claimed
thresholds, but it must never promote the capture to content-sync-verified or
public-release-ready.  A future policy needs a separately registered Job and
an evidence artifact whose bytes, hash, and tool lineage are re-read by the
service before a passing gate can exist.

Only hashes are accepted for device, operator, and logged-in window identity.
Window titles, device identifiers, credentials, and arbitrary notes therefore
cannot cross this boundary.
"""

import hashlib
import math
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from .security import canonical_json
from .windows_capture import (
    WINDOWS_CAPTURE_FRAME_RATE,
    WINDOWS_CAPTURE_OUTPUT_HEIGHT,
    WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
    WINDOWS_CAPTURE_OUTPUT_WIDTH,
    WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    WINDOWS_CAPTURE_PROVIDER,
    WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
    WINDOWS_CAPTURE_TIMING_SOURCE,
)


WINDOWS_CAPTURE_ACCEPTANCE_SCHEMA_VERSION = 1
WINDOWS_CAPTURE_ACCEPTANCE_POLICY_VERSION = "windows-capture-live-acceptance-v1"
WINDOWS_CAPTURE_ACCEPTANCE_EVENT_TYPE = "windows_capture.acceptance.recorded"
WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE = "blocked_windows_capture_live_acceptance_v1"
WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS = "blocked_unverified_calibration_lineage"
WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE = "request_self_reported_unverified"
WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK = (
    "evidence.registered_calibration_job_and_artifact_lineage"
)

MAX_VISIBLE_AUDIBLE_OFFSET_MS = 50.0
MIN_INTEGRATED_LOUDNESS_LUFS = -24.0
MAX_INTEGRATED_LOUDNESS_LUFS = -10.0
MAX_TRUE_PEAK_DBFS = -1.0

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{32}$")
_PRODUCTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_CAPTURE_RESULT_KEYS = frozenset(
    {
        "artifacts",
        "duration_ms",
        "capture_key",
        "cache_hit",
        "provider",
        "provider_task_id",
        "actual_cost",
        "timing_source",
        "target",
        "audio_mode",
        "actual_capture_performed",
        "structural_timing_verified",
        "content_sync_verified",
        "live_validation_required",
        "validation_scope",
        "public_release_ready",
        "public_release_gate",
        "tool_identity_digest",
        "video_dimensions",
        "frame_rate",
        "output_policy",
        "cost",
        "stage_attempt_id",
    }
)
_REGISTERED_ARTIFACT_KEYS = frozenset(
    {
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
        "file_url",
        "preview_url",
        "download_url",
    }
)
_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "capture_key",
        "artifact_sha256",
        "artifact_set_digest",
        "automated_facts",
        "operator_attestations",
    }
)
_AUTOMATED_FACT_KEYS = frozenset(
    {
        "av_visible_audible_offsets_ms",
        "integrated_lufs",
        "true_peak_dbfs",
        "default_device_before_id_sha256",
        "default_device_after_id_sha256",
        "default_device_switch_detected",
        "default_device_switch_outcome",
        "post_switch_capture_succeeded",
        "parent_forced_exit_exercised",
        "child_processes_terminated",
        "partial_outputs_removed",
        "forced_exit_published_artifact_count",
        "calibration_tool_identity_digest",
    }
)
_OPERATOR_ATTESTATION_KEYS = frozenset(
    {
        "operator_identity_sha256",
        "reviewed_complete_capture",
        "visible_audible_alignment_observed",
        "cursor_absence_observed",
        "logged_in_app_window_observed",
        "logged_in_app_window_identity_sha256",
        "sensitive_content_absence_observed",
    }
)

_ARTIFACT_SPECS: dict[str, tuple[str, str]] = {
    "screen-capture.mp4": ("video", "video/mp4"),
    "screen-video.mp4": ("video", "video/mp4"),
    "system-audio.wav": ("audio", "audio/wav"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}
_DEVICE_SWITCH_OUTCOMES = frozenset(
    {"failed_closed_no_publish", "switched_without_fail_closed", "not_exercised"}
)


class WindowsCaptureAcceptanceValidationError(ValueError):
    """A malformed or unbound acceptance input."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_windows_capture_acceptance",
    ):
        super().__init__(message)
        self.code = code


def _invalid(
    message: str,
    *,
    code: str = "invalid_windows_capture_acceptance",
) -> WindowsCaptureAcceptanceValidationError:
    return WindowsCaptureAcceptanceValidationError(message, code=code)


def _exact_object(value: Any, keys: frozenset[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid(f"{label} does not match the closed schema")
    return value


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise _invalid(f"{label} must be an uppercase SHA-256")
    return value


def _boolean(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(f"{label} must be a boolean")
    return value


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _invalid(f"{label} is outside the supported integer range")
    return value


def _number(value: Any, *, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise _invalid(f"{label} is outside the supported numeric range")
    if number == 0:
        number = 0.0
    return round(number, 3)


def _validate_registered_artifact(
    value: Any,
    *,
    capture_key: str,
) -> dict[str, Any]:
    artifact = _exact_object(value, _REGISTERED_ARTIFACT_KEYS, label="registered artifact")
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, str) or _ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
        raise _invalid("registered artifact ID is invalid")
    production_id = artifact.get("production_id")
    if (
        not isinstance(production_id, str)
        or _PRODUCTION_ID_RE.fullmatch(production_id) is None
    ):
        raise _invalid("registered artifact production ID is invalid")
    name = artifact.get("name")
    if not isinstance(name, str) or name not in _ARTIFACT_SPECS:
        raise _invalid("registered artifact name is invalid")
    expected_kind, expected_media_type = _ARTIFACT_SPECS[name]
    if (
        artifact.get("origin") != "studio"
        or artifact.get("kind") != expected_kind
        or artifact.get("media_type") != expected_media_type
        or artifact.get("available") is not True
    ):
        raise _invalid("registered artifact metadata is invalid")

    rel_path = artifact.get("rel_path")
    if not isinstance(rel_path, str) or "\\" in rel_path or rel_path.startswith("/"):
        raise _invalid("registered artifact path is invalid")
    path = PurePosixPath(rel_path)
    parts = path.parts
    if (
        path.as_posix() != rel_path
        or len(parts) != 7
        or parts[:3] != ("outputs", "studio", "runs")
        or _RUN_ID_RE.fullmatch(parts[3]) is None
        or parts[4] != "screen_capture"
        or parts[5] != capture_key
        or parts[6] != name
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise _invalid("registered artifact path is invalid")

    size = _integer(
        artifact.get("bytes"),
        label="registered artifact byte count",
        minimum=1,
        maximum=20 * 1024 * 1024 * 1024,
    )
    mtime_ns = _integer(
        artifact.get("mtime_ns"),
        label="registered artifact mtime",
        minimum=1,
        maximum=2**63 - 1,
    )
    digest = _sha256(artifact.get("sha256"), label="registered artifact SHA-256")
    is_heavy = _boolean(artifact.get("is_heavy"), label="registered artifact is_heavy")
    if is_heavy != (size > 10 * 1024 * 1024):
        raise _invalid("registered artifact size class is invalid")
    indexed_at = artifact.get("indexed_at")
    if (
        not isinstance(indexed_at, str)
        or not indexed_at
        or len(indexed_at) > 64
        or any(character in indexed_at for character in "\x00\r\n")
    ):
        raise _invalid("registered artifact index timestamp is invalid")
    expected_url = f"/api/artifacts/{artifact_id}/file"
    if any(
        artifact.get(key) != expected_url
        for key in ("file_url", "preview_url", "download_url")
    ):
        raise _invalid("registered artifact URL is invalid")
    return {
        "id": artifact_id,
        "production_id": production_id,
        "name": name,
        "kind": expected_kind,
        "media_type": expected_media_type,
        "bytes": size,
        "mtime_ns": mtime_ns,
        "sha256": digest,
    }


def _validate_registered_capture_result(value: Any) -> dict[str, Any]:
    result = _exact_object(value, _CAPTURE_RESULT_KEYS, label="registered capture result")
    capture_key = _sha256(result.get("capture_key"), label="capture key")
    tool_identity_digest = _sha256(
        result.get("tool_identity_digest"), label="capture tool identity"
    )
    stage_attempt_id = result.get("stage_attempt_id")
    if (
        not isinstance(stage_attempt_id, str)
        or _ATTEMPT_ID_RE.fullmatch(stage_attempt_id) is None
    ):
        raise _invalid("capture stage attempt ID is invalid")
    duration_ms = _integer(
        result.get("duration_ms"),
        label="capture duration",
        minimum=1_000,
        maximum=30_000,
    )
    if (
        result.get("cache_hit") is not False
        or result.get("provider") != WINDOWS_CAPTURE_PROVIDER
        or result.get("provider_task_id") is not None
        or isinstance(result.get("actual_cost"), bool)
        or result.get("actual_cost") != 0
        or result.get("timing_source") != WINDOWS_CAPTURE_TIMING_SOURCE
        or result.get("target") != "primary_display"
        or result.get("audio_mode") != "default_render_loopback"
        or result.get("actual_capture_performed") is not True
        or result.get("structural_timing_verified") is not True
        or result.get("content_sync_verified") is not False
        or result.get("live_validation_required") is not True
        or result.get("validation_scope") != WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE
        or result.get("public_release_ready") is not False
        or result.get("public_release_gate") != WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE
        or result.get("video_dimensions")
        != {
            "width": WINDOWS_CAPTURE_OUTPUT_WIDTH,
            "height": WINDOWS_CAPTURE_OUTPUT_HEIGHT,
        }
        or result.get("frame_rate") != WINDOWS_CAPTURE_FRAME_RATE
        or result.get("output_policy")
        != {
            "policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
            "audio": "default_render_loopback",
        }
        or result.get("cost")
        != {"amount": "0.00", "currency": "USD", "source": "local"}
    ):
        raise _invalid("registered capture result metadata is invalid")

    raw_artifacts = result.get("artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(_ARTIFACT_SPECS):
        raise _invalid("registered capture artifact set is incomplete")
    artifacts = [
        _validate_registered_artifact(item, capture_key=capture_key)
        for item in raw_artifacts
    ]
    names = [item["name"] for item in artifacts]
    ids = [item["id"] for item in artifacts]
    production_ids = {item["production_id"] for item in artifacts}
    if (
        set(names) != set(_ARTIFACT_SPECS)
        or len(names) != len(set(names))
        or len(ids) != len(set(ids))
        or len(production_ids) != 1
    ):
        raise _invalid("registered capture artifact identities are invalid")
    artifacts.sort(key=lambda item: item["name"])
    return {
        "capture_key": capture_key,
        "tool_identity_digest": tool_identity_digest,
        "stage_attempt_id": stage_attempt_id,
        "duration_ms": duration_ms,
        "production_id": next(iter(production_ids)),
        "artifacts": artifacts,
    }


def _artifact_binding(normalized_capture: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = [
        {
            key: artifact[key]
            for key in ("id", "name", "kind", "media_type", "bytes", "sha256")
        }
        for artifact in normalized_capture["artifacts"]
    ]
    artifact_sha256 = {item["name"]: item["sha256"] for item in artifacts}
    artifact_set_digest = hashlib.sha256(
        canonical_json(
            {
                "contract": "registered-windows-capture-artifact-set-v1",
                "capture_key": normalized_capture["capture_key"],
                "artifacts": artifacts,
            }
        ).encode("utf-8")
    ).hexdigest().upper()
    return {
        "capture_key": normalized_capture["capture_key"],
        "artifact_sha256": artifact_sha256,
        "artifact_set_digest": artifact_set_digest,
    }


def windows_capture_acceptance_binding(capture_result: Any) -> dict[str, Any]:
    """Return the path-free binding a calibration report must repeat."""

    return _artifact_binding(_validate_registered_capture_result(capture_result))


def _validate_report(
    value: Any,
    *,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    report = _exact_object(value, _REPORT_KEYS, label="acceptance report")
    if (
        isinstance(report.get("schema_version"), bool)
        or report.get("schema_version")
        != WINDOWS_CAPTURE_ACCEPTANCE_SCHEMA_VERSION
    ):
        raise _invalid("acceptance report schema_version is not supported")
    if report.get("capture_key") != binding["capture_key"]:
        raise _invalid(
            "acceptance report capture binding is invalid",
            code="windows_capture_acceptance_binding_mismatch",
        )
    artifact_sha256 = report.get("artifact_sha256")
    if (
        not isinstance(artifact_sha256, dict)
        or set(artifact_sha256) != set(_ARTIFACT_SPECS)
        or any(
            _SHA256_RE.fullmatch(value) is None
            for value in artifact_sha256.values()
            if isinstance(value, str)
        )
        or any(not isinstance(value, str) for value in artifact_sha256.values())
        or artifact_sha256 != binding["artifact_sha256"]
        or report.get("artifact_set_digest") != binding["artifact_set_digest"]
    ):
        raise _invalid(
            "acceptance report artifact binding is invalid",
            code="windows_capture_acceptance_binding_mismatch",
        )

    facts = _exact_object(
        report.get("automated_facts"),
        _AUTOMATED_FACT_KEYS,
        label="automated facts",
    )
    offsets = facts.get("av_visible_audible_offsets_ms")
    if not isinstance(offsets, list) or not 3 <= len(offsets) <= 20:
        raise _invalid("A/V calibration must contain 3 to 20 marker offsets")
    normalized_offsets = [
        _number(item, label="A/V marker offset", minimum=-10_000, maximum=10_000)
        for item in offsets
    ]
    switch_outcome = facts.get("default_device_switch_outcome")
    if switch_outcome not in _DEVICE_SWITCH_OUTCOMES:
        raise _invalid("default device switch outcome is invalid")
    automated_facts = {
        "av_visible_audible_offsets_ms": normalized_offsets,
        "integrated_lufs": _number(
            facts.get("integrated_lufs"),
            label="integrated loudness",
            minimum=-100,
            maximum=10,
        ),
        "true_peak_dbfs": _number(
            facts.get("true_peak_dbfs"),
            label="true peak",
            minimum=-100,
            maximum=10,
        ),
        "default_device_before_id_sha256": _sha256(
            facts.get("default_device_before_id_sha256"),
            label="default device before identity",
        ),
        "default_device_after_id_sha256": _sha256(
            facts.get("default_device_after_id_sha256"),
            label="default device after identity",
        ),
        "default_device_switch_detected": _boolean(
            facts.get("default_device_switch_detected"),
            label="default device switch detected",
        ),
        "default_device_switch_outcome": switch_outcome,
        "post_switch_capture_succeeded": _boolean(
            facts.get("post_switch_capture_succeeded"),
            label="post-switch capture succeeded",
        ),
        "parent_forced_exit_exercised": _boolean(
            facts.get("parent_forced_exit_exercised"),
            label="parent forced exit exercised",
        ),
        "child_processes_terminated": _boolean(
            facts.get("child_processes_terminated"),
            label="child processes terminated",
        ),
        "partial_outputs_removed": _boolean(
            facts.get("partial_outputs_removed"),
            label="partial outputs removed",
        ),
        "forced_exit_published_artifact_count": _integer(
            facts.get("forced_exit_published_artifact_count"),
            label="forced-exit published artifact count",
            minimum=0,
            maximum=100,
        ),
        "calibration_tool_identity_digest": _sha256(
            facts.get("calibration_tool_identity_digest"),
            label="calibration tool identity",
        ),
    }

    attestations = _exact_object(
        report.get("operator_attestations"),
        _OPERATOR_ATTESTATION_KEYS,
        label="operator attestations",
    )
    operator_attestations = {
        "operator_identity_sha256": _sha256(
            attestations.get("operator_identity_sha256"),
            label="operator identity",
        ),
        "reviewed_complete_capture": _boolean(
            attestations.get("reviewed_complete_capture"),
            label="complete capture review",
        ),
        "visible_audible_alignment_observed": _boolean(
            attestations.get("visible_audible_alignment_observed"),
            label="visible/audible alignment observation",
        ),
        "cursor_absence_observed": _boolean(
            attestations.get("cursor_absence_observed"),
            label="cursor absence observation",
        ),
        "logged_in_app_window_observed": _boolean(
            attestations.get("logged_in_app_window_observed"),
            label="logged-in app/window observation",
        ),
        "logged_in_app_window_identity_sha256": _sha256(
            attestations.get("logged_in_app_window_identity_sha256"),
            label="logged-in app/window identity",
        ),
        "sensitive_content_absence_observed": _boolean(
            attestations.get("sensitive_content_absence_observed"),
            label="sensitive content absence observation",
        ),
    }
    return {
        "automated_facts": automated_facts,
        "operator_attestations": operator_attestations,
    }


def evaluate_windows_capture_acceptance(
    capture_result: Any,
    report: Any,
) -> dict[str, Any]:
    """Evaluate one bound report without performing capture or I/O.

    Malformed or mismatched evidence raises a validation error.  Well-formed
    evidence that fails a quality or attestation threshold returns a blocked
    deterministic result, which keeps expected live-test failures auditable.
    """

    capture = _validate_registered_capture_result(capture_result)
    binding = _artifact_binding(capture)
    evidence = _validate_report(report, binding=binding)
    facts = evidence["automated_facts"]
    attestations = evidence["operator_attestations"]

    max_abs_offset = round(
        max(abs(value) for value in facts["av_visible_audible_offsets_ms"]), 3
    )
    automated_checks = {
        "artifact_binding": {
            "passed": True,
            "artifact_count": len(_ARTIFACT_SPECS),
        },
        "structural_timing": {"passed": True},
        "av_visible_audible_offset": {
            "passed": max_abs_offset <= MAX_VISIBLE_AUDIBLE_OFFSET_MS,
            "sample_count": len(facts["av_visible_audible_offsets_ms"]),
            "max_abs_offset_ms": max_abs_offset,
            "maximum_ms": MAX_VISIBLE_AUDIBLE_OFFSET_MS,
        },
        "integrated_loudness": {
            "passed": MIN_INTEGRATED_LOUDNESS_LUFS
            <= facts["integrated_lufs"]
            <= MAX_INTEGRATED_LOUDNESS_LUFS,
            "integrated_lufs": facts["integrated_lufs"],
            "minimum_lufs": MIN_INTEGRATED_LOUDNESS_LUFS,
            "maximum_lufs": MAX_INTEGRATED_LOUDNESS_LUFS,
        },
        "true_peak": {
            "passed": facts["true_peak_dbfs"] <= MAX_TRUE_PEAK_DBFS,
            "true_peak_dbfs": facts["true_peak_dbfs"],
            "maximum_dbfs": MAX_TRUE_PEAK_DBFS,
        },
        "default_device_switch": {
            "passed": facts["default_device_before_id_sha256"]
            != facts["default_device_after_id_sha256"]
            and facts["default_device_switch_detected"]
            and facts["default_device_switch_outcome"]
            == "failed_closed_no_publish"
            and facts["post_switch_capture_succeeded"],
            "identity_changed": facts["default_device_before_id_sha256"]
            != facts["default_device_after_id_sha256"],
            "switch_detected": facts["default_device_switch_detected"],
            "outcome": facts["default_device_switch_outcome"],
            "post_switch_capture_succeeded": facts["post_switch_capture_succeeded"],
        },
        "parent_forced_exit_cleanup": {
            "passed": facts["parent_forced_exit_exercised"]
            and facts["child_processes_terminated"]
            and facts["partial_outputs_removed"]
            and facts["forced_exit_published_artifact_count"] == 0,
            "forced_exit_exercised": facts["parent_forced_exit_exercised"],
            "child_processes_terminated": facts["child_processes_terminated"],
            "partial_outputs_removed": facts["partial_outputs_removed"],
            "published_artifact_count": facts[
                "forced_exit_published_artifact_count"
            ],
        },
    }
    operator_checks = {
        "reviewed_complete_capture": {
            "passed": attestations["reviewed_complete_capture"]
        },
        "visible_audible_alignment_observed": {
            "passed": attestations["visible_audible_alignment_observed"]
        },
        "cursor_absence_observed": {
            "passed": attestations["cursor_absence_observed"]
        },
        "logged_in_app_window_observed": {
            "passed": attestations["logged_in_app_window_observed"]
        },
        "sensitive_content_absence_observed": {
            "passed": attestations["sensitive_content_absence_observed"]
        },
    }
    self_reported_failed_checks = [
        f"automated.{name}"
        for name, check in automated_checks.items()
        if check["passed"] is not True
    ] + [
        f"operator.{name}"
        for name, check in operator_checks.items()
        if check["passed"] is not True
    ]
    # Every value above came from the request body.  Even a perfectly formed
    # report whose claimed values meet every threshold is not independently
    # verified calibration evidence.  Keep the claimed threshold result for
    # audit, but add the non-bypassable lineage blocker until the service can
    # resolve and re-read a dedicated calibration Job and evidence artifact.
    failed_checks = [
        *self_reported_failed_checks,
        WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK,
    ]
    body: dict[str, Any] = {
        "schema_version": WINDOWS_CAPTURE_ACCEPTANCE_SCHEMA_VERSION,
        "policy_version": WINDOWS_CAPTURE_ACCEPTANCE_POLICY_VERSION,
        "status": WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS,
        "evidence_provenance": WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE,
        "production_id": capture["production_id"],
        "stage_attempt_id": capture["stage_attempt_id"],
        "capture_key": capture["capture_key"],
        "tool_identity_digest": capture["tool_identity_digest"],
        "duration_ms": capture["duration_ms"],
        "artifact_sha256": binding["artifact_sha256"],
        "artifact_set_digest": binding["artifact_set_digest"],
        "automated_facts": facts,
        "operator_attestations": attestations,
        "automated_checks": automated_checks,
        "operator_attestation_checks": operator_checks,
        "self_reported_thresholds_met": not self_reported_failed_checks,
        "failed_checks": failed_checks,
        "content_sync_verified": False,
        "public_release_ready": False,
        "live_validation_required": True,
        "public_release_gate": WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE,
    }
    body["acceptance_digest"] = hashlib.sha256(
        canonical_json(body).encode("utf-8")
    ).hexdigest().upper()
    return body


__all__ = [
    "MAX_INTEGRATED_LOUDNESS_LUFS",
    "MAX_TRUE_PEAK_DBFS",
    "MAX_VISIBLE_AUDIBLE_OFFSET_MS",
    "MIN_INTEGRATED_LOUDNESS_LUFS",
    "WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE",
    "WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS",
    "WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE",
    "WINDOWS_CAPTURE_ACCEPTANCE_EVENT_TYPE",
    "WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK",
    "WINDOWS_CAPTURE_ACCEPTANCE_POLICY_VERSION",
    "WINDOWS_CAPTURE_ACCEPTANCE_SCHEMA_VERSION",
    "WindowsCaptureAcceptanceValidationError",
    "evaluate_windows_capture_acceptance",
    "windows_capture_acceptance_binding",
]
