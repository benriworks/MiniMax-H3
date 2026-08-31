from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import BinaryIO

from tools.studio.youtube_publish import YouTubeHttpResponse, YouTubePublishError, youtube_confirmation_summary
from tools.studio.youtube_publish_execution import execute_youtube_publish
from tools.studio.youtube_publish_state import YouTubePublishLedger


PRODUCTION_ID = "production_" + "1" * 32
CHANNEL_ID = "UC" + "A" * 22
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _summary(data: bytes) -> dict[str, object]:
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
        video_sha256=_sha(data),
        video_bytes=len(data),
    )


def _complete() -> YouTubeHttpResponse:
    return YouTubeHttpResponse(
        201,
        {},
        json.dumps(
            {
                "id": "AbCdEf123_-",
                "snippet": {"channelId": CHANNEL_ID},
                "status": {"privacyStatus": "private"},
            }
        ).encode("utf-8"),
    )


class _Transport:
    def __init__(self) -> None:
        self.begin_calls = 0
        self.query_responses = [YouTubeHttpResponse(308, {}, b"")]
        self.upload_response = _complete()
        self.upload_start_bytes: list[int] = []
        self.upload_payloads: list[bytes] = []

    def access_token(self) -> str:
        return "access"

    def channel(self, _token: str) -> dict[str, str]:
        return {"id": CHANNEL_ID, "title": "個人チャンネル"}

    def begin(self, _token: str, _request: object, *, video_bytes: int) -> str:
        self.begin_calls += 1
        self.video_bytes = video_bytes
        return SESSION

    def query(self, _token: str, _session: str, *, video_bytes: int) -> YouTubeHttpResponse:
        self.video_bytes = video_bytes
        return self.query_responses.pop(0)

    @staticmethod
    def acknowledged_bytes(response: YouTubeHttpResponse) -> int:
        value = response.headers.get("range", "")
        return int(value.rsplit("-", 1)[-1]) + 1 if value else 0

    def upload(
        self,
        _token: str,
        _session: str,
        video_handle: BinaryIO,
        *,
        expected_bytes: int,
        expected_sha256: str,
        start_byte: int,
        progress: object,
    ) -> YouTubeHttpResponse:
        self.upload_start_bytes.append(start_byte)
        video_handle.seek(0)
        content = video_handle.read()
        assert len(content) == expected_bytes
        assert _sha(content) == expected_sha256
        video_handle.seek(start_byte)
        payload = video_handle.read()
        assert len(payload) == expected_bytes - start_byte
        self.upload_payloads.append(payload)
        if callable(progress):
            progress(expected_bytes, expected_bytes)
        return self.upload_response


class YouTubePublishExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.data = b"verified-video" * 100
        self.video = self.workspace / "master.mp4"
        self.video.write_bytes(self.data)
        self.ledger = YouTubePublishLedger(
            self.workspace,
            protect=lambda value, **_kwargs: bytes(item ^ 0xA5 for item in value),
            unprotect=lambda value: bytes(item ^ 0xA5 for item in value),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_upload_succeeds_once_and_terminal_retry_does_not_resubmit(self) -> None:
        transport = _Transport()
        first = execute_youtube_publish(
            production_id=PRODUCTION_ID,
            confirmation_summary=_summary(self.data),
            video_path=self.video,
            transport=transport,  # type: ignore[arg-type]
            ledger=self.ledger,
        )
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(first["privacy_status"], "private")
        self.assertFalse(first["public_upload_supported"])
        second = execute_youtube_publish(
            production_id=PRODUCTION_ID,
            confirmation_summary=_summary(self.data),
            video_path=self.video,
            transport=transport,  # type: ignore[arg-type]
            ledger=self.ledger,
        )
        self.assertEqual(second, first)
        self.assertEqual(transport.begin_calls, 1)
        self.assertEqual(transport.upload_start_bytes, [0])

    def test_existing_session_resumes_from_provider_acknowledged_byte(self) -> None:
        summary = _summary(self.data)
        prepared = self.ledger.prepare(PRODUCTION_ID, summary)
        self.ledger.store_session(str(prepared["publish_id"]), SESSION)
        transport = _Transport()
        transport.query_responses = [
            YouTubeHttpResponse(308, {"range": "bytes=0-499"}, b"")
        ]
        result = execute_youtube_publish(
            production_id=PRODUCTION_ID,
            confirmation_summary=summary,
            video_path=self.video,
            transport=transport,  # type: ignore[arg-type]
            ledger=self.ledger,
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(transport.begin_calls, 0)
        self.assertEqual(transport.upload_start_bytes, [500])
        self.assertEqual(transport.upload_payloads, [self.data[500:]])

    def test_definite_begin_failure_is_terminal_and_never_reinitiated(self) -> None:
        summary = _summary(self.data)

        class BeginFailureTransport(_Transport):
            def begin(
                self, _token: str, _request: object, *, video_bytes: int
            ) -> str:
                self.begin_calls += 1
                self.video_bytes = video_bytes
                raise YouTubePublishError(
                    "YouTube rejected session creation.",
                    code="youtube_upload_session_failed",
                )

        transport = BeginFailureTransport()
        with self.assertRaises(YouTubePublishError) as raised:
            execute_youtube_publish(
                production_id=PRODUCTION_ID,
                confirmation_summary=summary,
                video_path=self.video,
                transport=transport,  # type: ignore[arg-type]
                ledger=self.ledger,
            )
        self.assertEqual(raised.exception.code, "youtube_upload_session_failed")
        publish_id = self.ledger.publish_id(
            PRODUCTION_ID, str(summary["confirmation_digest"])
        )
        state = self.ledger.read(publish_id)
        assert state is not None
        self.assertEqual(state["status"], "recovery_blocked")
        self.assertEqual(state["error_code"], "youtube_upload_session_failed")
        self.assertEqual(transport.begin_calls, 1)

        with self.assertRaises(YouTubePublishError) as retry:
            execute_youtube_publish(
                production_id=PRODUCTION_ID,
                confirmation_summary=summary,
                video_path=self.video,
                transport=transport,  # type: ignore[arg-type]
                ledger=self.ledger,
            )
        self.assertEqual(retry.exception.code, "youtube_publish_recovery_blocked")
        self.assertEqual(transport.begin_calls, 1)

    def test_expired_session_never_starts_a_new_upload(self) -> None:
        summary = _summary(self.data)
        prepared = self.ledger.prepare(PRODUCTION_ID, summary)
        self.ledger.store_session(str(prepared["publish_id"]), SESSION)
        transport = _Transport()
        transport.query_responses = [YouTubeHttpResponse(404, {}, b"")]
        with self.assertRaises(YouTubePublishError) as raised:
            execute_youtube_publish(
                production_id=PRODUCTION_ID,
                confirmation_summary=summary,
                video_path=self.video,
                transport=transport,  # type: ignore[arg-type]
                ledger=self.ledger,
            )
        self.assertEqual(raised.exception.code, "youtube_upload_session_expired")
        self.assertEqual(transport.begin_calls, 0)
        self.assertEqual(
            self.ledger.read(str(prepared["publish_id"]))["status"],  # type: ignore[index]
            "recovery_blocked",
        )

    def test_changed_source_fails_before_oauth_or_network(self) -> None:
        summary = _summary(self.data)
        self.video.write_bytes(self.data + b"tamper")
        transport = _Transport()
        with self.assertRaises(YouTubePublishError) as raised:
            execute_youtube_publish(
                production_id=PRODUCTION_ID,
                confirmation_summary=summary,
                video_path=self.video,
                transport=transport,  # type: ignore[arg-type]
                ledger=self.ledger,
            )
        self.assertEqual(raised.exception.code, "youtube_source_changed")
        self.assertEqual(transport.begin_calls, 0)

    def test_channel_change_fails_before_session_creation(self) -> None:
        transport = _Transport()
        transport.channel = lambda _token: {"id": "UC" + "B" * 22, "title": "別チャンネル"}  # type: ignore[method-assign]
        with self.assertRaises(YouTubePublishError) as raised:
            execute_youtube_publish(
                production_id=PRODUCTION_ID,
                confirmation_summary=_summary(self.data),
                video_path=self.video,
                transport=transport,  # type: ignore[arg-type]
                ledger=self.ledger,
            )
        self.assertEqual(raised.exception.code, "youtube_channel_changed")
        self.assertEqual(transport.begin_calls, 0)

    def test_staged_path_swap_cannot_change_bytes_read_from_bound_handle(self) -> None:
        summary = _summary(self.data)
        publish_id = self.ledger.publish_id(
            PRODUCTION_ID, str(summary["confirmation_digest"])
        )
        staged = self.ledger.root / publish_id / "source.mp4"

        class SwappingTransport(_Transport):
            def __init__(self) -> None:
                super().__init__()
                self.swap_succeeded = False
                self.swap_blocked = False
                self.write_blocked = False
                self.observed = b""

            def upload(
                self,
                token: str,
                session: str,
                video_handle: BinaryIO,
                *,
                expected_bytes: int,
                expected_sha256: str,
                start_byte: int,
                progress: object,
            ) -> YouTubeHttpResponse:
                if os.name == "nt":
                    try:
                        with staged.open("r+b") as mutator:
                            mutator.write(b"X")
                    except OSError:
                        self.write_blocked = True
                replacement = staged.with_name("replacement.mp4")
                replacement.write_bytes(b"X" * expected_bytes)
                try:
                    os.replace(replacement, staged)
                    self.swap_succeeded = True
                except OSError:
                    self.swap_blocked = True
                    replacement.unlink(missing_ok=True)
                video_handle.seek(0)
                self.observed = video_handle.read()
                return super().upload(
                    token,
                    session,
                    video_handle,
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                    start_byte=start_byte,
                    progress=progress,
                )

        transport = SwappingTransport()
        result = execute_youtube_publish(
            production_id=PRODUCTION_ID,
            confirmation_summary=summary,
            video_path=self.video,
            transport=transport,  # type: ignore[arg-type]
            ledger=self.ledger,
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(transport.observed, self.data)
        self.assertTrue(transport.swap_succeeded or transport.swap_blocked)
        if os.name == "nt":
            self.assertTrue(transport.write_blocked)
            self.assertTrue(transport.swap_blocked)
            self.assertFalse(staged.exists())


if __name__ == "__main__":
    unittest.main()
