from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.studio.youtube_publish import YouTubePublishError, youtube_confirmation_summary
from tools.studio.youtube_publish_state import YouTubePublishLedger


PRODUCTION_ID = "production_" + "1" * 32
CHANNEL_ID = "UC" + "A" * 22


def _summary() -> dict[str, object]:
    return youtube_confirmation_summary(
        {
            "schema_version": 1,
            "delivery_artifact_id": "art_" + "2" * 32,
            "video_artifact_id": "art_" + "3" * 32,
            "title": "private upload",
            "description": "",
            "tags": [],
            "category_id": "22",
            "privacy_status": "private",
            "made_for_kids": False,
            "contains_synthetic_media": True,
        },
        {"id": CHANNEL_ID, "title": "個人チャンネル"},
        delivery_sha256="A" * 64,
        video_sha256="B" * 64,
        video_bytes=1_000,
    )


class YouTubePublishLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.protected_values: list[bytes] = []

        def protect(value: bytes, **_kwargs: object) -> bytes:
            self.protected_values.append(value)
            return bytes(item ^ 0xA5 for item in value)

        def unprotect(value: bytes) -> bytes:
            return bytes(item ^ 0xA5 for item in value)

        self.ledger = YouTubePublishLedger(
            self.workspace, protect=protect, unprotect=unprotect
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prepare_is_deterministic_and_public_state_has_no_session(self) -> None:
        first = self.ledger.prepare(PRODUCTION_ID, _summary())
        second = self.ledger.prepare(PRODUCTION_ID, _summary())
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "prepared")
        self.assertNotIn("session", first)
        raw = (self.workspace / "outputs" / "studio" / "youtube" / first["publish_id"] / "state.json").read_text()
        self.assertNotIn("upload_id", raw)
        self.assertNotIn("refresh", raw)

    def test_session_is_encrypted_and_success_removes_it(self) -> None:
        state = self.ledger.prepare(PRODUCTION_ID, _summary())
        publish_id = str(state["publish_id"])
        active = self.ledger.store_session(
            publish_id,
            "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque",
        )
        self.assertEqual(active["status"], "session_active")
        self.assertEqual(
            self.ledger.session(publish_id),
            "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque",
        )
        session_path = self.workspace / "outputs" / "studio" / "youtube" / publish_id / "session.dpapi"
        self.assertNotIn(b"upload_id=opaque", session_path.read_bytes())
        uploading = self.ledger.transition(
            publish_id, "uploading", acknowledged_bytes=500
        )
        self.assertEqual(uploading["acknowledged_bytes"], 500)
        succeeded = self.ledger.transition(
            publish_id,
            "succeeded",
            acknowledged_bytes=1_000,
            video_id="AbCdEf123_-",
            video_url="https://youtu.be/AbCdEf123_-",
        )
        self.assertEqual(succeeded["status"], "succeeded")
        self.assertFalse(session_path.exists())

    def test_prepared_ambiguity_cannot_be_reinitiated(self) -> None:
        state = self.ledger.prepare(PRODUCTION_ID, _summary())
        publish_id = str(state["publish_id"])
        blocked = self.ledger.transition(
            publish_id, "ambiguous", error_code="youtube_upload_session_unknown"
        )
        self.assertEqual(blocked["status"], "ambiguous")
        with self.assertRaises(YouTubePublishError):
            self.ledger.store_session(
                publish_id,
                "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=new",
            )

    def test_offset_is_monotonic_and_terminal_state_is_immutable(self) -> None:
        state = self.ledger.prepare(PRODUCTION_ID, _summary())
        publish_id = str(state["publish_id"])
        self.ledger.store_session(
            publish_id,
            "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque",
        )
        self.ledger.transition(publish_id, "uploading", acknowledged_bytes=700)
        with self.assertRaises(YouTubePublishError):
            self.ledger.transition(publish_id, "uploading", acknowledged_bytes=600)
        self.ledger.transition(
            publish_id,
            "succeeded",
            acknowledged_bytes=1_000,
            video_id="AbCdEf123_-",
            video_url="https://youtu.be/AbCdEf123_-",
        )
        with self.assertRaises(YouTubePublishError):
            self.ledger.transition(publish_id, "uploading", acknowledged_bytes=1_000)

    def test_tampered_state_fails_closed(self) -> None:
        state = self.ledger.prepare(PRODUCTION_ID, _summary())
        path = self.workspace / "outputs" / "studio" / "youtube" / str(state["publish_id"]) / "state.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"private"', '"unlisted"'), encoding="utf-8")
        with self.assertRaises(YouTubePublishError) as raised:
            self.ledger.read(str(state["publish_id"]))
        self.assertEqual(raised.exception.code, "youtube_publish_state_invalid")


if __name__ == "__main__":
    unittest.main()
