from __future__ import annotations

import io
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.youtube_publish import (
    YouTubeHttpResponse,
    YouTubeOAuthCredential,
    YouTubePublishError,
    YouTubePublishValidationError,
    YouTubeResumableTransport,
    validate_youtube_completion,
    validate_youtube_execute_payload,
    validate_youtube_preview_payload,
    youtube_confirmation_summary,
    youtube_publish_request_digest,
)


DELIVERY_ID = "art_" + "1" * 32
VIDEO_ID = "art_" + "2" * 32
CHANNEL_ID = "UC" + "A" * 22
DELIVERY_SHA = "A" * 64
VIDEO_SHA = "B" * 64


def _preview(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "delivery_artifact_id": DELIVERY_ID,
        "video_artifact_id": VIDEO_ID,
        "title": "生成AIを学ぶ15秒",
        "description": "安全なprivate uploadのテストです。",
        "tags": ["生成AI", "Shorts"],
        "category_id": "22",
        "privacy_status": "private",
        "made_for_kids": False,
        "contains_synthetic_media": True,
    }
    value.update(changes)
    return value


class _Response:
    def __init__(self, status: int, value: object, headers: dict[str, str] | None = None):
        self.status = status
        self.headers = headers or {}
        self._body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]


class YouTubePublishContractTests(unittest.TestCase):
    def test_provider_errors_preserve_allowlisted_background_job_contract(self) -> None:
        error = YouTubePublishError(
            "The YouTube upload response is unknown.",
            code="youtube_upload_ambiguous",
        )
        self.assertEqual(error.code, "youtube_upload_ambiguous")
        self.assertEqual(error.error_code, "youtube_upload_ambiguous")
        self.assertEqual(
            error.public_message, "The YouTube upload response is unknown."
        )

    def test_preview_is_closed_and_public_is_impossible(self) -> None:
        self.assertEqual(validate_youtube_preview_payload(_preview())["privacy_status"], "private")
        self.assertEqual(
            validate_youtube_preview_payload(_preview(privacy_status="unlisted"))["privacy_status"],
            "unlisted",
        )
        with self.assertRaises(YouTubePublishValidationError) as raised:
            validate_youtube_preview_payload(_preview(privacy_status="public"))
        self.assertEqual(raised.exception.code, "youtube_public_privacy_not_supported")
        with self.assertRaises(YouTubePublishValidationError):
            validate_youtube_preview_payload({**_preview(), "publish_at": "2026-09-01"})

    def test_preview_limits_and_digest_are_deterministic(self) -> None:
        normalized = validate_youtube_preview_payload(_preview())
        self.assertEqual(normalized["title"], "生成AIを学ぶ15秒")
        self.assertEqual(
            youtube_publish_request_digest(normalized),
            youtube_publish_request_digest(_preview()),
        )
        with self.assertRaises(YouTubePublishValidationError):
            validate_youtube_preview_payload(_preview(title="x" * 101))
        with self.assertRaises(YouTubePublishValidationError):
            validate_youtube_preview_payload(_preview(tags=["same", "SAME"]))

    def test_confirmation_binds_channel_metadata_and_artifact_hashes(self) -> None:
        channel = {"id": CHANNEL_ID, "title": "個人チャンネル"}
        summary = youtube_confirmation_summary(
            _preview(),
            channel,
            delivery_sha256=DELIVERY_SHA,
            video_sha256=VIDEO_SHA,
            video_bytes=1234,
        )
        execute = {
            "schema_version": 1,
            "request": _preview(),
            "expected_channel_id": CHANNEL_ID,
            "expected_channel_title": "個人チャンネル",
            "confirmation_digest": summary["confirmation_digest"],
            "certify_community_guidelines": True,
            "confirm_upload": True,
        }
        validated = validate_youtube_execute_payload(
            execute,
            expected_preview=_preview(),
            expected_channel=channel,
            delivery_sha256=DELIVERY_SHA,
            video_sha256=VIDEO_SHA,
        )
        self.assertTrue(validated["confirm_upload"])
        self.assertFalse(summary["public_upload_supported"])
        for change in (
            {"certify_community_guidelines": False},
            {"confirm_upload": False},
            {"expected_channel_title": "別チャンネル"},
        ):
            with self.assertRaises(YouTubePublishValidationError):
                validate_youtube_execute_payload(
                    {**execute, **change},
                    expected_preview=_preview(),
                    expected_channel=channel,
                    delivery_sha256=DELIVERY_SHA,
                    video_sha256=VIDEO_SHA,
                )

    def test_oauth_credential_accepts_only_exact_bounded_json(self) -> None:
        credential = YouTubeOAuthCredential.parse(
            json.dumps(
                {
                    "client_id": "client.apps.googleusercontent.com",
                    "client_secret": "secret",
                    "refresh_token": "refresh",
                }
            )
        )
        self.assertEqual(credential.refresh_token, "refresh")
        with self.assertRaises(YouTubePublishError):
            YouTubeOAuthCredential.parse('{"client_id":"x"}')
        with self.assertRaises(YouTubePublishError):
            YouTubeOAuthCredential.parse(
                json.dumps(
                    {
                        "client_id": "x",
                        "client_secret": "secret\nleak",
                        "refresh_token": "refresh",
                    }
                )
            )

    def test_token_channel_and_session_start_use_fixed_google_endpoints(self) -> None:
        calls: list[object] = []
        responses = iter(
            [
                _Response(200, {"access_token": "access", "expires_in": 3600}),
                _Response(
                    200,
                    {"items": [{"id": CHANNEL_ID, "snippet": {"title": "個人チャンネル"}}]},
                ),
                _Response(
                    200,
                    {},
                    {
                        "Location": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=opaque"
                    },
                ),
            ]
        )

        def opener(request: object, **_kwargs: object) -> _Response:
            calls.append(request)
            return next(responses)

        transport = YouTubeResumableTransport(
            YouTubeOAuthCredential("client", "secret", "refresh"), urlopen=opener
        )
        token = transport.access_token()
        channel = transport.channel(token)
        session = transport.begin(token, _preview(), video_bytes=500)
        self.assertEqual(channel, {"id": CHANNEL_ID, "title": "個人チャンネル"})
        self.assertIn("upload_id=opaque", session)
        self.assertEqual(len(calls), 3)
        request_text = "\n".join(str(getattr(item, "full_url", "")) for item in calls)
        self.assertNotIn("access", request_text)
        self.assertNotIn("refresh", request_text)

    def test_session_host_is_fail_closed(self) -> None:
        transport = YouTubeResumableTransport(
            YouTubeOAuthCredential("client", "secret", "refresh"),
            urlopen=lambda *_args, **_kwargs: _Response(200, {}),
        )
        with self.assertRaises(YouTubePublishError):
            transport.query(
                "access",
                "https://evil.example/upload/youtube/v3/videos?upload_id=leak",
                video_bytes=100,
            )

    def test_credential_bearing_requests_reject_redirects(self) -> None:
        transport = YouTubeResumableTransport(
            YouTubeOAuthCredential("client", "secret", "refresh"),
            urlopen=lambda *_args, **_kwargs: _Response(
                302,
                {},
                {"Location": "https://evil.example/token"},
            ),
        )
        with self.assertRaises(YouTubePublishError) as raised:
            transport.access_token()
        self.assertEqual(raised.exception.code, "youtube_redirect_rejected")

    def test_completion_whitelists_channel_and_private_status(self) -> None:
        body = {
            "id": "AbCdEf123_-",
            "snippet": {"channelId": CHANNEL_ID},
            "status": {"privacyStatus": "private"},
        }
        result = validate_youtube_completion(
            YouTubeHttpResponse(201, {}, json.dumps(body).encode("utf-8")),
            expected_channel_id=CHANNEL_ID,
            expected_privacy_status="private",
        )
        self.assertEqual(result["url"], "https://youtu.be/AbCdEf123_-")
        with self.assertRaises(YouTubePublishError):
            validate_youtube_completion(
                YouTubeHttpResponse(
                    201,
                    {},
                    json.dumps({**body, "status": {"privacyStatus": "public"}}).encode("utf-8"),
                ),
                expected_channel_id=CHANNEL_ID,
                expected_privacy_status="private",
            )

    def test_streaming_upload_does_not_read_the_whole_video_into_memory(self) -> None:
        sent: list[int] = []

        class FakeUploadResponse:
            status = 201
            headers: dict[str, str] = {}

            def read(self, size: int = -1) -> bytes:
                self.assert_size = size
                return b'{"id":"AbCdEf123_-","snippet":{"channelId":"' + CHANNEL_ID.encode() + b'"},"status":{"privacyStatus":"private"}}'

        class FakeConnection:
            def __init__(self, *_args: object, **_kwargs: object):
                pass

            def putrequest(self, *_args: object, **_kwargs: object) -> None:
                pass

            def putheader(self, *_args: object, **_kwargs: object) -> None:
                pass

            def endheaders(self) -> None:
                pass

            def send(self, data: bytes) -> None:
                sent.append(len(data))

            def getresponse(self) -> FakeUploadResponse:
                return FakeUploadResponse()

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video_bytes = b"x" * (2 * 1024 * 1024 + 17)
            video.write_bytes(video_bytes)
            transport = YouTubeResumableTransport(
                YouTubeOAuthCredential("client", "secret", "refresh")
            )
            with mock.patch(
                "tools.studio.youtube_publish.http.client.HTTPSConnection",
                FakeConnection,
            ):
                with video.open("rb") as video_handle:
                    response = transport.upload(
                        "access",
                        "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque",
                        video_handle,
                        expected_bytes=len(video_bytes),
                        expected_sha256=hashlib.sha256(video_bytes).hexdigest().upper(),
                    )
        self.assertEqual(response.status, 201)
        self.assertEqual(sent, [1024 * 1024, 1024 * 1024, 17])


if __name__ == "__main__":
    unittest.main()
