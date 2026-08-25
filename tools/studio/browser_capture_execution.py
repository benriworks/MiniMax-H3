from __future__ import annotations

"""Closed control-plane contract for the local Playwright screen recorder.

Only loopback HTTP pages are accepted.  The public request cannot provide
credentials, browser flags, headers, cookies, JavaScript, executable paths, or
output paths.  URL and selector text are hashed before they enter durable
Studio audit records.
"""

import hashlib
import re
import urllib.parse
from typing import Any, Mapping

from .security import canonical_json


BROWSER_CAPTURE_SCHEMA_VERSION = 1
IMPLEMENTATION_VERSION = "local-playwright-screen-capture-v1"
PROVIDER = "local_playwright"
TIMING_SOURCE = "ffprobe"
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
FRAME_RATE = 24
MIN_DURATION_MS = 1_000
MAX_DURATION_MS = 30_000
MAX_SETTLE_MS = 10_000
MAX_ACTIONS = 16
MAX_SELECTOR_CHARS = 256
MAX_URL_CHARS = 2_048
OUTPUT_POLICY_VERSION = "h264-yuv420p-1080x1920-24fps-video-only-v1"

_PUBLIC_KEYS = {"url", "duration_ms", "settle_ms", "actions"}
_ACTION_KEYS = {
    "scroll": {"type", "at_ms", "delta_y"},
    "click": {"type", "at_ms", "selector"},
    "press": {"type", "at_ms", "selector", "key"},
}
_PRESS_KEYS = {
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "ArrowUp",
    "End",
    "Enter",
    "Escape",
    "Home",
    "PageDown",
    "PageUp",
    "Space",
    "Tab",
}
_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")


class BrowserCaptureError(RuntimeError):
    error_code = "local_screen_capture_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = str(message)


class BrowserCaptureValidationError(BrowserCaptureError):
    error_code = "invalid_local_screen_capture_request"


class BrowserCaptureToolError(BrowserCaptureError):
    error_code = "local_playwright_failed"


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BrowserCaptureValidationError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise BrowserCaptureValidationError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return value


def _loopback_url(value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, str) or not value or len(value) > MAX_URL_CHARS:
        raise BrowserCaptureValidationError("url is invalid")
    if "\\" in value or any(ord(character) < 0x20 for character in value):
        raise BrowserCaptureValidationError("url is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise BrowserCaptureValidationError("url is invalid") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port is None
        or port < 1
        or port > 65_535
    ):
        raise BrowserCaptureValidationError(
            "url must be an explicit http://127.0.0.1:<port>/ address without credentials or a fragment"
        )
    if parsed.netloc != f"127.0.0.1:{port}":
        raise BrowserCaptureValidationError("url authority is not canonical")
    path = parsed.path or "/"
    normalized = urllib.parse.urlunsplit(
        ("http", f"127.0.0.1:{port}", path, parsed.query, "")
    )
    if normalized != value:
        raise BrowserCaptureValidationError("url must use its canonical loopback form")
    return normalized, {
        "origin": f"http://127.0.0.1:{port}",
        "url_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper(),
        "path_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest().upper(),
        "query_present": bool(parsed.query),
    }


def _selector(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_SELECTOR_CHARS
        or any(ord(character) < 0x20 for character in value)
    ):
        raise BrowserCaptureValidationError(f"{label} is invalid")
    return value


def _action(value: Any, *, index: int, duration_ms: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BrowserCaptureValidationError(f"actions[{index}] must be an object")
    action_type = value.get("type")
    if action_type not in _ACTION_KEYS or set(value) != _ACTION_KEYS[action_type]:
        raise BrowserCaptureValidationError(f"actions[{index}] has unsupported fields")
    at_ms = _integer(
        value.get("at_ms"),
        label=f"actions[{index}].at_ms",
        minimum=0,
        maximum=duration_ms - 1,
    )
    if action_type == "scroll":
        delta_y = _integer(
            value.get("delta_y"),
            label=f"actions[{index}].delta_y",
            minimum=-4_000,
            maximum=4_000,
        )
        if delta_y == 0:
            raise BrowserCaptureValidationError(
                f"actions[{index}].delta_y must not be zero"
            )
        return {"type": action_type, "at_ms": at_ms, "delta_y": delta_y}
    selector = _selector(value.get("selector"), label=f"actions[{index}].selector")
    if action_type == "click":
        return {"type": action_type, "at_ms": at_ms, "selector": selector}
    key = value.get("key")
    if key not in _PRESS_KEYS:
        raise BrowserCaptureValidationError(f"actions[{index}].key is not allowed")
    return {
        "type": action_type,
        "at_ms": at_ms,
        "selector": selector,
        "key": key,
    }


def validate_browser_capture_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != _PUBLIC_KEYS:
        raise BrowserCaptureValidationError(
            "request body must contain only url, duration_ms, settle_ms, and actions"
        )
    url, target = _loopback_url(body.get("url"))
    duration_ms = _integer(
        body.get("duration_ms"),
        label="duration_ms",
        minimum=MIN_DURATION_MS,
        maximum=MAX_DURATION_MS,
    )
    settle_ms = _integer(
        body.get("settle_ms"),
        label="settle_ms",
        minimum=0,
        maximum=MAX_SETTLE_MS,
    )
    actions = body.get("actions")
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise BrowserCaptureValidationError(
            f"actions must be an array with at most {MAX_ACTIONS} entries"
        )
    normalized_actions = [
        _action(item, index=index, duration_ms=duration_ms)
        for index, item in enumerate(actions)
    ]
    if any(
        normalized_actions[index]["at_ms"] < normalized_actions[index - 1]["at_ms"]
        for index in range(1, len(normalized_actions))
    ):
        raise BrowserCaptureValidationError("actions must be ordered by at_ms")
    return {
        "url": url,
        "duration_ms": duration_ms,
        "settle_ms": settle_ms,
        "actions": normalized_actions,
        "target": target,
    }


def browser_capture_audit_payload(
    payload: Mapping[str, Any], *, capture_key: str
) -> dict[str, Any]:
    if not _CACHE_KEY_RE.fullmatch(capture_key):
        raise BrowserCaptureValidationError("capture_key is invalid")
    target = payload.get("target")
    actions = payload.get("actions")
    if not isinstance(target, Mapping) or not isinstance(actions, list):
        raise BrowserCaptureValidationError("capture payload is invalid")
    audited_actions: list[dict[str, Any]] = []
    for action in actions:
        item = {"type": action["type"], "at_ms": action["at_ms"]}
        if action["type"] == "scroll":
            item["delta_y"] = action["delta_y"]
        else:
            item["selector_sha256"] = hashlib.sha256(
                action["selector"].encode("utf-8")
            ).hexdigest().upper()
            if action["type"] == "press":
                item["key"] = action["key"]
        audited_actions.append(item)
    return {
        "capture_key": capture_key,
        "target": dict(target),
        "duration_ms": payload["duration_ms"],
        "settle_ms": payload["settle_ms"],
        "actions": audited_actions,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "audio": "omitted",
    }


def browser_capture_key(payload: Mapping[str, Any], nonce: str) -> str:
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise BrowserCaptureValidationError("capture nonce is invalid")
    identity = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "nonce": nonce,
        "url_sha256": payload["target"]["url_sha256"],
        "duration_ms": payload["duration_ms"],
        "settle_ms": payload["settle_ms"],
        "actions": payload["actions"],
        "output_policy_version": OUTPUT_POLICY_VERSION,
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def browser_capture_public_result(
    raw: Any,
    *,
    expected_capture_key: str,
    expected_duration_ms: int,
    expected_origin: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BrowserCaptureError(
            "The local screen capture worker returned an invalid result.",
            code="invalid_worker_result",
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or abs(duration_ms - expected_duration_ms) > 250
    ):
        raise BrowserCaptureError(
            "The local screen capture worker returned invalid timing.",
            code="invalid_worker_result",
        )
    if (
        raw.get("provider") != PROVIDER
        or raw.get("timing_source") != TIMING_SOURCE
        or raw.get("capture_key") != expected_capture_key
        or raw.get("target_origin") != expected_origin
        or raw.get("cache_hit") is not False
        or raw.get("provider_task_id") is not None
        or raw.get("actual_cost") != 0
    ):
        raise BrowserCaptureError(
            "The local screen capture worker returned invalid metadata.",
            code="invalid_worker_result",
        )
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "capture_key": expected_capture_key,
        "cache_hit": False,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "target_origin": expected_origin,
        "video_dimensions": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "output_policy": {
            "policy_version": OUTPUT_POLICY_VERSION,
            "audio": "omitted",
        },
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_browser_capture_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, BrowserCaptureError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    return "local_screen_capture_failed", "The local screen capture job failed."


__all__ = [
    "BROWSER_CAPTURE_SCHEMA_VERSION",
    "BrowserCaptureError",
    "BrowserCaptureToolError",
    "BrowserCaptureValidationError",
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "FRAME_RATE",
    "IMPLEMENTATION_VERSION",
    "MAX_ACTIONS",
    "MAX_DURATION_MS",
    "MAX_SETTLE_MS",
    "MIN_DURATION_MS",
    "OUTPUT_POLICY_VERSION",
    "PROVIDER",
    "TIMING_SOURCE",
    "browser_capture_audit_payload",
    "browser_capture_key",
    "browser_capture_public_result",
    "safe_browser_capture_error",
    "validate_browser_capture_payload",
]
