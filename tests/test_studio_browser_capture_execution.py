from __future__ import annotations

import json
import unittest

from tools.studio.browser_capture_execution import (
    BrowserCaptureError,
    BrowserCaptureValidationError,
    browser_capture_audit_payload,
    browser_capture_key,
    browser_capture_public_result,
    browser_capture_viewport,
    DESKTOP_OUTPUT_POLICY_VERSION,
    validate_browser_capture_payload,
)


class BrowserCaptureExecutionTests(unittest.TestCase):
    def payload(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "url": "http://127.0.0.1:8765/private?token=do-not-store",
            "duration_ms": 5_000,
            "settle_ms": 500,
            "actions": [
                {"type": "scroll", "at_ms": 1_000, "delta_y": 720},
                {"type": "click", "at_ms": 2_000, "selector": "#private-target"},
                {
                    "type": "press",
                    "at_ms": 3_000,
                    "selector": "#dialog",
                    "key": "Escape",
                },
            ],
        }
        value.update(overrides)
        return value

    def test_validates_exact_closed_payload(self) -> None:
        normalized = validate_browser_capture_payload(self.payload())
        self.assertEqual(normalized["target"]["origin"], "http://127.0.0.1:8765")
        self.assertTrue(normalized["target"]["query_present"])
        with self.assertRaises(BrowserCaptureValidationError):
            validate_browser_capture_payload({**self.payload(), "headers": {"x": "y"}})

    def test_legacy_payload_audit_and_key_remain_unchanged_when_preset_is_omitted(self) -> None:
        payload = validate_browser_capture_payload(self.payload())
        key = browser_capture_key(payload, "1" * 32)
        self.assertEqual(key, "FE1259FF25419CC9BCD32005312A5DD1452950E6A1D094E180111AF19E2B01E9")
        self.assertNotIn("viewport_preset", payload)
        audit = browser_capture_audit_payload(payload, capture_key=key)
        self.assertNotIn("viewport_preset", audit)
        self.assertEqual(audit["canvas"], {"width": 1080, "height": 1920})

    def test_desktop_preset_is_closed_and_changes_capture_identity(self) -> None:
        portrait = validate_browser_capture_payload(self.payload())
        desktop = validate_browser_capture_payload(self.payload(viewport_preset="desktop_16_9"))
        self.assertEqual(desktop["viewport_preset"], "desktop_16_9")
        self.assertEqual(browser_capture_viewport("desktop_16_9"), {"width": 1920, "height": 1080})
        key = browser_capture_key(desktop, "1" * 32)
        self.assertNotEqual(key, browser_capture_key(portrait, "1" * 32))
        audit = browser_capture_audit_payload(desktop, capture_key=key)
        self.assertEqual(audit["canvas"], {"width": 1920, "height": 1080})
        self.assertEqual(audit["viewport_preset"], "desktop_16_9")
        self.assertNotIn("do-not-store", json.dumps(audit))
        for value in (None, "", "portrait_9_16", "external_browser", {"width": 1920}, True):
            with self.subTest(value=value), self.assertRaises(BrowserCaptureValidationError):
                validate_browser_capture_payload(self.payload(viewport_preset=value))
        for field in ("viewport", "width", "height", "cookies", "storage_state", "session"):
            with self.subTest(field=field), self.assertRaises(BrowserCaptureValidationError):
                validate_browser_capture_payload(self.payload(viewport_preset="desktop_16_9", **{field: "not-allowed"}))
        with self.assertRaises(BrowserCaptureValidationError):
            validate_browser_capture_payload(self.payload(viewport_preset="desktop_16_9", url="https://example.com/"))

    def test_rejects_non_loopback_credentials_fragments_and_implicit_ports(self) -> None:
        invalid = (
            "https://127.0.0.1:8765/",
            "http://localhost:8765/",
            "http://127.0.0.2:8765/",
            "http://127.0.0.1/",
            "http://user:password@127.0.0.1:8765/",
            "http://127.0.0.1:8765/#secret",
            "file:///C:/secret",
            "javascript:alert(1)",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(BrowserCaptureValidationError):
                validate_browser_capture_payload(self.payload(url=url))

    def test_bounds_duration_actions_selectors_and_keys(self) -> None:
        for duration in (999, 30_001, 5.5, True):
            with self.subTest(duration=duration), self.assertRaises(BrowserCaptureValidationError):
                validate_browser_capture_payload(self.payload(duration_ms=duration))
        with self.assertRaises(BrowserCaptureValidationError):
            validate_browser_capture_payload(
                self.payload(actions=[{"type": "scroll", "at_ms": 5_000, "delta_y": 1}])
            )
        with self.assertRaises(BrowserCaptureValidationError):
            validate_browser_capture_payload(
                self.payload(
                    actions=[
                        {"type": "press", "at_ms": 0, "selector": "body", "key": "A"}
                    ]
                )
            )
        with self.assertRaises(BrowserCaptureValidationError):
            validate_browser_capture_payload(
                self.payload(actions=[{"type": "script", "at_ms": 0, "code": "alert(1)"}])
            )

    def test_audit_never_contains_raw_url_query_or_selector(self) -> None:
        payload = validate_browser_capture_payload(self.payload())
        capture_key = browser_capture_key(payload, "1" * 32)
        audit = browser_capture_audit_payload(payload, capture_key=capture_key)
        serialized = json.dumps(audit, ensure_ascii=False)
        self.assertNotIn("do-not-store", serialized)
        self.assertNotIn("private-target", serialized)
        self.assertNotIn("#dialog", serialized)
        self.assertEqual(audit["target"]["origin"], "http://127.0.0.1:8765")
        self.assertRegex(capture_key, r"^[0-9A-F]{64}$")
        self.assertNotEqual(capture_key, browser_capture_key(payload, "2" * 32))

    def test_public_result_is_closed_and_rejects_metadata_mismatch(self) -> None:
        raw = {
            "duration_ms": 5_000,
            "capture_key": "A" * 64,
            "cache_hit": False,
            "provider": "local_playwright",
            "provider_task_id": None,
            "actual_cost": 0,
            "timing_source": "ffprobe",
            "target_origin": "http://127.0.0.1:8765",
        }
        result = browser_capture_public_result(
            raw,
            expected_capture_key="A" * 64,
            expected_duration_ms=5_000,
            expected_origin="http://127.0.0.1:8765",
            artifacts=[],
        )
        self.assertEqual(result["cache_hit"], False)
        self.assertEqual(result["actual_cost"], 0)
        self.assertNotIn("viewport_preset", result)
        self.assertEqual(result["video_dimensions"], {"width": 1080, "height": 1920})
        with self.assertRaises(BrowserCaptureError):
            browser_capture_public_result(
                {**raw, "target_origin": "http://127.0.0.1:9999"},
                expected_capture_key="A" * 64,
                expected_duration_ms=5_000,
                expected_origin="http://127.0.0.1:8765",
                artifacts=[],
            )

    def test_desktop_public_result_requires_matching_preset_and_dimensions(self) -> None:
        raw = {
            "duration_ms": 5_000, "capture_key": "A" * 64, "cache_hit": False,
            "provider": "local_playwright", "provider_task_id": None, "actual_cost": 0,
            "timing_source": "ffprobe", "target_origin": "http://127.0.0.1:8765",
            "viewport_preset": "desktop_16_9", "video_dimensions": {"width": 1920, "height": 1080},
        }
        expected = {"expected_capture_key": "A" * 64, "expected_duration_ms": 5_000,
                    "expected_origin": "http://127.0.0.1:8765", "artifacts": []}
        result = browser_capture_public_result(raw, expected_viewport_preset="desktop_16_9", **expected)
        self.assertEqual(result["viewport_preset"], "desktop_16_9")
        self.assertEqual(result["video_dimensions"], {"width": 1920, "height": 1080})
        self.assertEqual(result["output_policy"]["policy_version"], DESKTOP_OUTPUT_POLICY_VERSION)
        for patch in ({"viewport_preset": None}, {"video_dimensions": {"width": 1080, "height": 1920}}, {"video_dimensions": None}):
            with self.subTest(patch=patch), self.assertRaises(BrowserCaptureError):
                browser_capture_public_result({**raw, **patch}, expected_viewport_preset="desktop_16_9", **expected)
        with self.assertRaises(BrowserCaptureError):
            browser_capture_public_result(raw, **expected)


if __name__ == "__main__":
    unittest.main()
