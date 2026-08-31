from __future__ import annotations

"""Durable, secret-safe state for one resumable YouTube upload.

The public JSON never contains an OAuth token or resumable session URI.  The
session URI is stored separately as Windows-user-scoped DPAPI ciphertext.  A
``prepared`` state that loses the session-init response becomes ``ambiguous``
and cannot be re-initiated automatically.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .database import utc_now
from .security import (
    SecurityError,
    canonical_json,
    stable_id,
    validate_identifier,
    workspace_path,
)
from .secrets import (
    SecretStorageUnavailable,
    protect_private_data,
    unprotect_private_data,
)
from .youtube_publish import YouTubePublishError, youtube_confirmation_summary


YOUTUBE_PUBLISH_STATE_SCHEMA_VERSION = 1
YOUTUBE_PUBLISH_STATES = frozenset(
    {
        "prepared",
        "session_active",
        "uploading",
        "ambiguous",
        "recovery_blocked",
        "succeeded",
    }
)
_TRANSITIONS = {
    "prepared": {"session_active", "ambiguous", "recovery_blocked"},
    "session_active": {"uploading", "ambiguous", "recovery_blocked", "succeeded"},
    "uploading": {"uploading", "ambiguous", "recovery_blocked", "succeeded"},
    "ambiguous": {"uploading", "recovery_blocked", "succeeded"},
    "recovery_blocked": set(),
    "succeeded": set(),
}


Protect = Callable[..., bytes]
Unprotect = Callable[[bytes], bytes]


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest().upper()


def _bounded_error_code(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("error code is invalid")
    return value


class YouTubePublishLedger:
    def __init__(
        self,
        workspace: Path,
        *,
        protect: Protect = protect_private_data,
        unprotect: Unprotect = unprotect_private_data,
    ):
        self.workspace = workspace.resolve(strict=True)
        self.root = workspace_path(self.workspace, "outputs/studio/youtube")
        self._protect = protect
        self._unprotect = unprotect

    @staticmethod
    def publish_id(production_id: str, confirmation_digest: str) -> str:
        validate_identifier(production_id, label="production id")
        if (
            not isinstance(confirmation_digest, str)
            or len(confirmation_digest) != 64
            or any(character not in "0123456789ABCDEF" for character in confirmation_digest.upper())
        ):
            raise ValueError("confirmation digest is invalid")
        return stable_id(
            "youtube_publish",
            f"youtube-private-unlisted-v1\x00{production_id}\x00{confirmation_digest.upper()}",
        )

    def _directory(self, publish_id: str) -> Path:
        validate_identifier(publish_id, label="YouTube publish id")
        if not publish_id.startswith("youtube_publish_"):
            raise SecurityError("invalid YouTube publish id")
        return workspace_path(self.workspace, self.root / publish_id)

    def _state_path(self, publish_id: str) -> Path:
        return workspace_path(self.workspace, self._directory(publish_id) / "state.json")

    def _session_path(self, publish_id: str) -> Path:
        return workspace_path(self.workspace, self._directory(publish_id) / "session.dpapi")

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _public_state(value: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "schema_version",
            "publish_id",
            "production_id",
            "request_digest",
            "confirmation_digest",
            "delivery_artifact_id",
            "delivery_sha256",
            "video_artifact_id",
            "video_sha256",
            "video_bytes",
            "channel_id",
            "channel_title",
            "privacy_status",
            "status",
            "acknowledged_bytes",
            "attempt_count",
            "video_id",
            "video_url",
            "error_code",
            "created_at",
            "updated_at",
            "state_digest",
        }
        if set(value) != expected:
            raise YouTubePublishError(
                "The YouTube upload ledger is invalid.", code="youtube_publish_state_invalid"
            )
        body = dict(value)
        state_digest = body.pop("state_digest", None)
        if state_digest != _digest(body):
            raise YouTubePublishError(
                "The YouTube upload ledger is invalid.", code="youtube_publish_state_invalid"
            )
        if body.get("status") not in YOUTUBE_PUBLISH_STATES:
            raise YouTubePublishError(
                "The YouTube upload ledger is invalid.", code="youtube_publish_state_invalid"
            )
        return dict(value)

    def read(self, publish_id: str) -> dict[str, Any] | None:
        path = self._state_path(publish_id)
        if not path.is_file() or path.is_symlink():
            return None
        try:
            if path.stat().st_size <= 0 or path.stat().st_size > 256 * 1024:
                raise ValueError("size")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("type")
            state = self._public_state(value)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise YouTubePublishError(
                "The YouTube upload ledger is invalid.", code="youtube_publish_state_invalid"
            ) from exc
        if state.get("publish_id") != publish_id:
            raise YouTubePublishError(
                "The YouTube upload ledger is invalid.", code="youtube_publish_state_invalid"
            )
        return state

    def _write_state(self, value: Mapping[str, Any]) -> dict[str, Any]:
        body = dict(value)
        body.pop("state_digest", None)
        body["state_digest"] = _digest(body)
        state = self._public_state(body)
        self._write_atomic(
            self._state_path(str(state["publish_id"])),
            (canonical_json(state) + "\n").encode("utf-8"),
        )
        return state

    def assert_secure_persistence(self) -> None:
        """Fail before session initiation when DPAPI round-trip is unavailable."""

        plaintext = b"minimaxh3-youtube-session-persistence-v1"
        try:
            ciphertext = self._protect(
                plaintext,
                description="MiniMaxH3 Studio YouTube upload session",
            )
            restored = self._unprotect(ciphertext)
            if restored != plaintext:
                raise ValueError("round trip")
        except (OSError, ValueError, SecretStorageUnavailable) as exc:
            raise YouTubePublishError(
                "Secure YouTube upload recovery is unavailable.",
                code="youtube_secure_persistence_unavailable",
            ) from exc

    def prepare(
        self,
        production_id: str,
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        validate_identifier(production_id, label="production id")
        try:
            normalized = youtube_confirmation_summary(
                summary["request"],
                summary["channel"],
                delivery_sha256=str(summary["delivery_sha256"]),
                video_sha256=str(summary["video_sha256"]),
                video_bytes=int(summary["video_bytes"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise YouTubePublishError(
                "The YouTube confirmation summary is invalid.",
                code="youtube_confirmation_invalid",
            ) from exc
        if normalized.get("confirmation_digest") != summary.get("confirmation_digest"):
            raise YouTubePublishError(
                "The YouTube confirmation summary is invalid.",
                code="youtube_confirmation_invalid",
            )
        publish_id = self.publish_id(production_id, normalized["confirmation_digest"])
        request = normalized["request"]
        channel = normalized["channel"]
        timestamp = utc_now()
        candidate = {
            "schema_version": YOUTUBE_PUBLISH_STATE_SCHEMA_VERSION,
            "publish_id": publish_id,
            "production_id": production_id,
            "request_digest": hashlib.sha256(
                canonical_json(request).encode("utf-8")
            ).hexdigest().upper(),
            "confirmation_digest": normalized["confirmation_digest"],
            "delivery_artifact_id": request["delivery_artifact_id"],
            "delivery_sha256": normalized["delivery_sha256"],
            "video_artifact_id": request["video_artifact_id"],
            "video_sha256": normalized["video_sha256"],
            "video_bytes": normalized["video_bytes"],
            "channel_id": channel["id"],
            "channel_title": channel["title"],
            "privacy_status": request["privacy_status"],
            "status": "prepared",
            "acknowledged_bytes": 0,
            "attempt_count": 0,
            "video_id": None,
            "video_url": None,
            "error_code": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        existing = self.read(publish_id)
        if existing is not None:
            identity = {
                key: existing[key]
                for key in (
                    "production_id",
                    "request_digest",
                    "confirmation_digest",
                    "delivery_artifact_id",
                    "delivery_sha256",
                    "video_artifact_id",
                    "video_sha256",
                    "video_bytes",
                    "channel_id",
                    "channel_title",
                    "privacy_status",
                )
            }
            if identity != {key: candidate[key] for key in identity}:
                raise YouTubePublishError(
                    "The YouTube publish identity is already used by another request.",
                    code="youtube_publish_conflict",
                )
            return existing
        self.assert_secure_persistence()
        return self._write_state(candidate)

    def store_session(self, publish_id: str, session_url: str) -> dict[str, Any]:
        state = self.read(publish_id)
        if state is None or state["status"] != "prepared":
            raise YouTubePublishError(
                "The YouTube upload session cannot be attached.",
                code="youtube_publish_state_conflict",
            )
        if not isinstance(session_url, str) or not session_url or len(session_url) > 16_384:
            raise YouTubePublishError(
                "The YouTube upload session is invalid.",
                code="invalid_youtube_upload_session",
            )
        try:
            encrypted = self._protect(
                session_url.encode("utf-8"),
                description="MiniMaxH3 Studio YouTube upload session",
            )
        except (OSError, ValueError, SecretStorageUnavailable) as exc:
            raise YouTubePublishError(
                "Secure YouTube upload recovery is unavailable.",
                code="youtube_secure_persistence_unavailable",
            ) from exc
        self._write_atomic(self._session_path(publish_id), encrypted)
        return self.transition(publish_id, "session_active", increment_attempt=True)

    def session(self, publish_id: str) -> str | None:
        state = self.read(publish_id)
        if state is None:
            return None
        path = self._session_path(publish_id)
        if not path.is_file() or path.is_symlink():
            return None
        try:
            data = path.read_bytes()
            plaintext = self._unprotect(data)
            value = plaintext.decode("utf-8")
            if not value or len(value) > 16_384 or "\x00" in value:
                raise ValueError("session")
            return value
        except (OSError, UnicodeError, ValueError, SecretStorageUnavailable) as exc:
            raise YouTubePublishError(
                "The protected YouTube upload session is unavailable.",
                code="youtube_upload_session_unavailable",
            ) from exc

    def transition(
        self,
        publish_id: str,
        status: str,
        *,
        acknowledged_bytes: int | None = None,
        increment_attempt: bool = False,
        video_id: str | None = None,
        video_url: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        state = self.read(publish_id)
        if state is None:
            raise YouTubePublishError(
                "The YouTube upload ledger is unavailable.",
                code="youtube_publish_state_invalid",
            )
        current = str(state["status"])
        if status not in _TRANSITIONS.get(current, set()):
            if status == current:
                return state
            raise YouTubePublishError(
                "The YouTube upload state transition is invalid.",
                code="youtube_publish_state_conflict",
            )
        acknowledged = (
            int(state["acknowledged_bytes"])
            if acknowledged_bytes is None
            else acknowledged_bytes
        )
        if (
            isinstance(acknowledged, bool)
            or not isinstance(acknowledged, int)
            or acknowledged < int(state["acknowledged_bytes"])
            or acknowledged > int(state["video_bytes"])
        ):
            raise YouTubePublishError(
                "The YouTube upload offset is invalid.",
                code="youtube_resume_offset_invalid",
            )
        if status == "succeeded":
            if (
                not isinstance(video_id, str)
                or not video_id
                or not isinstance(video_url, str)
                or not video_url.startswith("https://youtu.be/")
                or acknowledged != int(state["video_bytes"])
            ):
                raise YouTubePublishError(
                    "The completed YouTube upload identity is invalid.",
                    code="invalid_youtube_response",
                )
            error_code = None
        elif video_id is not None or video_url is not None:
            raise YouTubePublishError(
                "A non-terminal YouTube upload cannot have a video identity.",
                code="youtube_publish_state_conflict",
            )
        next_value = {
            **state,
            "status": status,
            "acknowledged_bytes": acknowledged,
            "attempt_count": int(state["attempt_count"]) + (1 if increment_attempt else 0),
            "video_id": video_id,
            "video_url": video_url,
            "error_code": _bounded_error_code(error_code),
            "updated_at": utc_now(),
        }
        next_value.pop("state_digest", None)
        result = self._write_state(next_value)
        if status == "succeeded":
            # A completed provider identity is sufficient for future dedupe;
            # retaining a signed session URI only expands the secret surface.
            self._session_path(publish_id).unlink(missing_ok=True)
        return result


__all__ = [
    "YOUTUBE_PUBLISH_STATE_SCHEMA_VERSION",
    "YOUTUBE_PUBLISH_STATES",
    "YouTubePublishLedger",
]
