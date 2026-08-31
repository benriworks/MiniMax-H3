from __future__ import annotations

import copy
import json
import unittest

from tools.studio.windows_capture import (
    WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
    WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
    WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
)
from tools.studio.windows_capture_acceptance import (
    WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE,
    WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS,
    WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE,
    WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK,
    WindowsCaptureAcceptanceValidationError,
    evaluate_windows_capture_acceptance,
    windows_capture_acceptance_binding,
)


CAPTURE_KEY = "A" * 64
TOOL_DIGEST = "B" * 64
CALIBRATION_DIGEST = "C" * 64
BEFORE_DEVICE = "D" * 64
AFTER_DEVICE = "E" * 64
OPERATOR_IDENTITY = "F" * 64
WINDOW_IDENTITY = "1" * 64
RUN_ID = "run_" + "2" * 32
PRODUCTION_ID = "production_capture_acceptance"
ATTEMPT_ID = "attempt_" + "3" * 32


ARTIFACT_SPECS = {
    "screen-capture.mp4": ("video", "video/mp4"),
    "screen-video.mp4": ("video", "video/mp4"),
    "system-audio.wav": ("audio", "audio/wav"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}


def _artifact(index: int, name: str, kind: str, media_type: str) -> dict[str, object]:
    artifact_id = f"art_{index:032x}"
    url = f"/api/artifacts/{artifact_id}/file"
    return {
        "id": artifact_id,
        "production_id": PRODUCTION_ID,
        "rel_path": (
            f"outputs/studio/runs/{RUN_ID}/screen_capture/{CAPTURE_KEY}/{name}"
        ),
        "origin": "studio",
        "name": name,
        "kind": kind,
        "media_type": media_type,
        "bytes": 1_000 + index,
        "mtime_ns": 1_800_000_000_000_000_000 + index,
        "sha256": f"{index + 10:064X}",
        "is_heavy": False,
        "available": True,
        "indexed_at": "2026-09-01T00:00:00+00:00",
        "file_url": url,
        "preview_url": url,
        "download_url": url,
    }


def _capture_result() -> dict[str, object]:
    artifacts = [
        _artifact(index, name, kind, media_type)
        for index, (name, (kind, media_type)) in enumerate(
            ARTIFACT_SPECS.items(), start=1
        )
    ]
    return {
        "artifacts": artifacts,
        "duration_ms": 6_000,
        "capture_key": CAPTURE_KEY,
        "cache_hit": False,
        "provider": "local_windows_capture",
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": "ffprobe",
        "target": "primary_display",
        "audio_mode": "default_render_loopback",
        "actual_capture_performed": True,
        "structural_timing_verified": True,
        "content_sync_verified": False,
        "live_validation_required": True,
        "validation_scope": WINDOWS_CAPTURE_SYNC_VALIDATION_SCOPE,
        "public_release_ready": False,
        "public_release_gate": WINDOWS_CAPTURE_PUBLIC_RELEASE_GATE,
        "tool_identity_digest": TOOL_DIGEST,
        "video_dimensions": {"width": 1920, "height": 1080},
        "frame_rate": 24,
        "output_policy": {
            "policy_version": WINDOWS_CAPTURE_OUTPUT_POLICY_VERSION,
            "audio": "default_render_loopback",
        },
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
        "stage_attempt_id": ATTEMPT_ID,
    }


def _passing_report(capture_result: dict[str, object]) -> dict[str, object]:
    binding = windows_capture_acceptance_binding(capture_result)
    return {
        "schema_version": 1,
        **binding,
        "automated_facts": {
            "av_visible_audible_offsets_ms": [-18.5, 12.0, 36.25],
            "integrated_lufs": -16.0,
            "true_peak_dbfs": -2.0,
            "default_device_before_id_sha256": BEFORE_DEVICE,
            "default_device_after_id_sha256": AFTER_DEVICE,
            "default_device_switch_detected": True,
            "default_device_switch_outcome": "failed_closed_no_publish",
            "post_switch_capture_succeeded": True,
            "parent_forced_exit_exercised": True,
            "child_processes_terminated": True,
            "partial_outputs_removed": True,
            "forced_exit_published_artifact_count": 0,
            "calibration_tool_identity_digest": CALIBRATION_DIGEST,
        },
        "operator_attestations": {
            "operator_identity_sha256": OPERATOR_IDENTITY,
            "reviewed_complete_capture": True,
            "visible_audible_alignment_observed": True,
            "cursor_absence_observed": True,
            "logged_in_app_window_observed": True,
            "logged_in_app_window_identity_sha256": WINDOW_IDENTITY,
            "sensitive_content_absence_observed": True,
        },
    }


class WindowsCaptureAcceptanceTests(unittest.TestCase):
    def test_self_reported_evidence_is_preserved_but_never_promotes_capture(
        self,
    ) -> None:
        capture = _capture_result()
        report = _passing_report(capture)
        accepted = evaluate_windows_capture_acceptance(capture, report)

        self.assertFalse(accepted["content_sync_verified"])
        self.assertFalse(accepted["public_release_ready"])
        self.assertTrue(accepted["live_validation_required"])
        self.assertEqual(
            accepted["public_release_gate"], WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE
        )
        self.assertEqual(
            accepted["status"], WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_STATUS
        )
        self.assertEqual(
            accepted["evidence_provenance"],
            WINDOWS_CAPTURE_ACCEPTANCE_EVIDENCE_PROVENANCE,
        )
        self.assertTrue(accepted["self_reported_thresholds_met"])
        self.assertEqual(
            accepted["failed_checks"], [WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK]
        )
        self.assertEqual(accepted["capture_key"], CAPTURE_KEY)
        self.assertRegex(accepted["artifact_set_digest"], r"^[0-9A-F]{64}$")
        self.assertRegex(accepted["acceptance_digest"], r"^[0-9A-F]{64}$")
        self.assertEqual(accepted["automated_facts"], report["automated_facts"])
        self.assertEqual(
            accepted["operator_attestations"], report["operator_attestations"]
        )

        serialized = json.dumps(accepted, sort_keys=True)
        self.assertNotIn("rel_path", serialized)
        self.assertNotIn("window_title", serialized)
        self.assertNotIn("device_id", serialized)
        self.assertNotIn("credential", serialized)

    def test_binding_and_acceptance_digest_are_artifact_order_independent(self) -> None:
        capture = _capture_result()
        report = _passing_report(capture)
        expected_binding = windows_capture_acceptance_binding(capture)
        expected = evaluate_windows_capture_acceptance(capture, report)

        reordered = copy.deepcopy(capture)
        reordered["artifacts"] = list(reversed(reordered["artifacts"]))
        self.assertEqual(
            windows_capture_acceptance_binding(reordered), expected_binding
        )
        actual = evaluate_windows_capture_acceptance(reordered, report)
        self.assertEqual(actual, expected)

    def test_quality_threshold_failures_are_valid_blocked_results(self) -> None:
        cases = {
            "offset": (
                "automated_facts",
                "av_visible_audible_offsets_ms",
                [0.0, 50.001, -1.0],
                "automated.av_visible_audible_offset",
            ),
            "too_quiet": (
                "automated_facts",
                "integrated_lufs",
                -24.001,
                "automated.integrated_loudness",
            ),
            "too_loud": (
                "automated_facts",
                "integrated_lufs",
                -9.999,
                "automated.integrated_loudness",
            ),
            "true_peak": (
                "automated_facts",
                "true_peak_dbfs",
                -0.999,
                "automated.true_peak",
            ),
        }
        for label, (section, field, value, failed_check) in cases.items():
            with self.subTest(label=label):
                capture = _capture_result()
                report = _passing_report(capture)
                report[section][field] = value
                result = evaluate_windows_capture_acceptance(capture, report)
                self.assertFalse(result["content_sync_verified"])
                self.assertFalse(result["public_release_ready"])
                self.assertTrue(result["live_validation_required"])
                self.assertFalse(result["self_reported_thresholds_met"])
                self.assertIn(failed_check, result["failed_checks"])
                self.assertIn(
                    WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK,
                    result["failed_checks"],
                )
                self.assertEqual(
                    result["public_release_gate"],
                    WINDOWS_CAPTURE_ACCEPTANCE_BLOCKED_GATE,
                )

    def test_boundary_quality_values_only_pass_self_reported_thresholds(self) -> None:
        capture = _capture_result()
        for loudness in (-24.0, -10.0):
            with self.subTest(loudness=loudness):
                report = _passing_report(capture)
                report["automated_facts"]["av_visible_audible_offsets_ms"] = [
                    -50.0,
                    0.0,
                    50.0,
                ]
                report["automated_facts"]["integrated_lufs"] = loudness
                report["automated_facts"]["true_peak_dbfs"] = -1.0
                result = evaluate_windows_capture_acceptance(capture, report)
                self.assertTrue(result["self_reported_thresholds_met"])
                self.assertTrue(
                    result["automated_checks"]["av_visible_audible_offset"][
                        "passed"
                    ]
                )
                self.assertTrue(
                    result["automated_checks"]["integrated_loudness"]["passed"]
                )
                self.assertTrue(result["automated_checks"]["true_peak"]["passed"])
                self.assertFalse(result["content_sync_verified"])
                self.assertFalse(result["public_release_ready"])
                self.assertTrue(result["live_validation_required"])
                self.assertEqual(
                    result["failed_checks"],
                    [WINDOWS_CAPTURE_ACCEPTANCE_LINEAGE_CHECK],
                )

    def test_operator_attestation_cannot_be_replaced_by_automated_measurements(self) -> None:
        capture = _capture_result()
        report = _passing_report(capture)
        report["operator_attestations"]["cursor_absence_observed"] = False
        report["operator_attestations"][
            "visible_audible_alignment_observed"
        ] = False

        result = evaluate_windows_capture_acceptance(capture, report)

        self.assertTrue(
            result["automated_checks"]["av_visible_audible_offset"]["passed"]
        )
        self.assertFalse(
            result["operator_attestation_checks"]["cursor_absence_observed"][
                "passed"
            ]
        )
        self.assertIn(
            "operator.cursor_absence_observed", result["failed_checks"]
        )
        self.assertIn(
            "operator.visible_audible_alignment_observed", result["failed_checks"]
        )
        self.assertFalse(result["public_release_ready"])

    def test_device_switch_requires_distinct_hashed_ids_fail_closed_and_retry(self) -> None:
        changes = {
            "same identity": ("default_device_after_id_sha256", BEFORE_DEVICE),
            "not detected": ("default_device_switch_detected", False),
            "unsafe outcome": (
                "default_device_switch_outcome",
                "switched_without_fail_closed",
            ),
            "retry failed": ("post_switch_capture_succeeded", False),
        }
        for label, (field, value) in changes.items():
            with self.subTest(label=label):
                capture = _capture_result()
                report = _passing_report(capture)
                report["automated_facts"][field] = value
                result = evaluate_windows_capture_acceptance(capture, report)
                self.assertIn(
                    "automated.default_device_switch", result["failed_checks"]
                )
                self.assertFalse(result["public_release_ready"])

    def test_parent_forced_exit_requires_termination_cleanup_and_no_publish(self) -> None:
        changes = {
            "not exercised": ("parent_forced_exit_exercised", False),
            "child alive": ("child_processes_terminated", False),
            "partial remains": ("partial_outputs_removed", False),
            "artifact leaked": ("forced_exit_published_artifact_count", 1),
        }
        for label, (field, value) in changes.items():
            with self.subTest(label=label):
                capture = _capture_result()
                report = _passing_report(capture)
                report["automated_facts"][field] = value
                result = evaluate_windows_capture_acceptance(capture, report)
                self.assertIn(
                    "automated.parent_forced_exit_cleanup",
                    result["failed_checks"],
                )
                self.assertFalse(result["public_release_ready"])

    def test_report_must_bind_exact_capture_key_and_all_artifact_hashes(self) -> None:
        capture = _capture_result()
        mutations = []
        wrong_key = _passing_report(capture)
        wrong_key["capture_key"] = "9" * 64
        mutations.append(wrong_key)
        wrong_hash = _passing_report(capture)
        wrong_hash["artifact_sha256"]["screen-capture.mp4"] = "8" * 64
        mutations.append(wrong_hash)
        wrong_set = _passing_report(capture)
        wrong_set["artifact_set_digest"] = "7" * 64
        mutations.append(wrong_set)

        for report in mutations:
            with self.subTest(report=report):
                with self.assertRaises(WindowsCaptureAcceptanceValidationError) as failed:
                    evaluate_windows_capture_acceptance(capture, report)
                self.assertEqual(
                    failed.exception.code,
                    "windows_capture_acceptance_binding_mismatch",
                )

    def test_raw_window_device_or_credential_fields_are_rejected(self) -> None:
        capture = _capture_result()
        mutations = []
        raw_window = _passing_report(capture)
        raw_window["operator_attestations"]["window_title"] = "Logged in account"
        mutations.append(raw_window)
        raw_device = _passing_report(capture)
        raw_device["automated_facts"]["default_device_before_id"] = "raw-device-id"
        mutations.append(raw_device)
        credential = _passing_report(capture)
        credential["operator_attestations"]["credential"] = "secret"
        mutations.append(credential)

        for report in mutations:
            with self.subTest(report=report):
                with self.assertRaises(WindowsCaptureAcceptanceValidationError):
                    evaluate_windows_capture_acceptance(capture, report)

    def test_incomplete_or_unregistered_artifact_set_is_rejected(self) -> None:
        missing = _capture_result()
        missing["artifacts"].pop()
        with self.assertRaises(WindowsCaptureAcceptanceValidationError):
            windows_capture_acceptance_binding(missing)

        unavailable = _capture_result()
        unavailable["artifacts"][0]["available"] = False
        with self.assertRaises(WindowsCaptureAcceptanceValidationError):
            windows_capture_acceptance_binding(unavailable)

        wrong_path = _capture_result()
        wrong_path["artifacts"][0]["rel_path"] = "C:/private/window-title.mp4"
        with self.assertRaises(WindowsCaptureAcceptanceValidationError):
            windows_capture_acceptance_binding(wrong_path)


if __name__ == "__main__":
    unittest.main()
