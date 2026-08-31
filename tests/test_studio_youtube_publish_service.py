from __future__ import annotations

import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO
from unittest import mock

from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService
from tools.studio.youtube_publish import (
    YouTubeHttpResponse,
    YouTubePublishError,
    validate_youtube_preview_payload,
    youtube_confirmation_summary,
)
from tools.studio.youtube_publish_binding import (
    YouTubePublishBinding,
    YouTubePublishBindingError,
)
from tools.studio.youtube_publish_state import YouTubePublishLedger


PRODUCTION_ID = "production_" + "a" * 32
DELIVERY_ID = "art_" + "1" * 32
VIDEO_ID = "art_" + "2" * 32
RUN_ID = "run_" + "3" * 32
SOURCE_JOB_ID = "job_" + "4" * 32
CHANNEL = {"id": "UC" + "A" * 22, "title": "個人チャンネル"}
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=opaque"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _preview(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "delivery_artifact_id": DELIVERY_ID,
        "video_artifact_id": VIDEO_ID,
        "title": "生成AIを仕事に活かす",
        "description": "検証済みの納品動画です。",
        "tags": ["生成AI", "Shorts"],
        "category_id": "22",
        "privacy_status": "private",
        "made_for_kids": False,
        "contains_synthetic_media": True,
    }
    value.update(changes)
    return value


def _execute_body(binding: YouTubePublishBinding) -> dict[str, object]:
    summary = youtube_confirmation_summary(
        binding.request,
        CHANNEL,
        delivery_sha256=str(binding.delivery_artifact["sha256"]),
        video_sha256=str(binding.video_artifact["sha256"]),
        video_bytes=int(binding.video_artifact["bytes"]),
    )
    return {
        "schema_version": 1,
        "request": copy.deepcopy(binding.request),
        "expected_channel_id": CHANNEL["id"],
        "expected_channel_title": CHANNEL["title"],
        "confirmation_digest": summary["confirmation_digest"],
        "certify_community_guidelines": True,
        "confirm_upload": True,
    }


class _Context:
    def __init__(self) -> None:
        self.checks = 0

    def raise_if_cancelled(self) -> None:
        self.checks += 1


class _DeferredJobs:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []

    def submit(
        self,
        kind: str,
        payload: dict[str, object],
        callback: object,
        *,
        production_id: str,
    ) -> dict[str, object]:
        index = len(self.submissions) + 1
        job = {
            "id": f"job_{index:032x}",
            "kind": kind,
            "status": "queued",
            "production_id": production_id,
            "payload": copy.deepcopy(payload),
        }
        self.submissions.append({"job": job, "callback": callback})
        return copy.deepcopy(job)

    def run(self, index: int = 0) -> dict[str, object]:
        submission = self.submissions[index]
        callback = submission["callback"]
        assert callable(callback)
        job = submission["job"]
        assert isinstance(job, dict)
        return callback(job["id"], _Context())


class _MissingSecrets:
    def resolve(self, _provider: str) -> str:
        raise KeyError("not configured")


class _Transport:
    def __init__(self) -> None:
        self.access_token_calls = 0
        self.channel_calls = 0
        self.begin_calls = 0
        self.query_calls = 0
        self.upload_calls = 0

    def access_token(self) -> str:
        self.access_token_calls += 1
        return "access-token"

    def channel(self, _token: str) -> dict[str, str]:
        self.channel_calls += 1
        return dict(CHANNEL)

    def begin(
        self, _token: str, _request: object, *, video_bytes: int
    ) -> str:
        self.begin_calls += 1
        self.video_bytes = video_bytes
        return SESSION

    def query(
        self, _token: str, _session: str, *, video_bytes: int
    ) -> YouTubeHttpResponse:
        self.query_calls += 1
        self.video_bytes = video_bytes
        return YouTubeHttpResponse(308, {}, b"")

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
        self.upload_calls += 1
        self.upload_start_byte = start_byte
        video_handle.seek(0)
        content = video_handle.read()
        assert len(content) == expected_bytes
        assert _sha(content) == expected_sha256
        if callable(progress):
            progress(expected_bytes, expected_bytes)
        return YouTubeHttpResponse(
            201,
            {},
            json.dumps(
                {
                    "id": "AbCdEf123_-",
                    "snippet": {"channelId": CHANNEL["id"]},
                    "status": {"privacyStatus": "private"},
                }
            ).encode("utf-8"),
        )


class YouTubePublishServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.video_bytes = b"verified-youtube-master" * 20
        self.video_path = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / RUN_ID
            / "assembly"
            / "cache"
            / "master-clean.mp4"
        )
        self.video_path.parent.mkdir(parents=True)
        self.video_path.write_bytes(self.video_bytes)
        delivery_path = (
            self.workspace
            / "outputs"
            / "studio"
            / "deliveries"
            / PRODUCTION_ID
            / ("A" * 64)
            / "delivery-package.zip"
        )
        delivery_path.parent.mkdir(parents=True)
        delivery_path.write_bytes(b"verified-delivery")
        request = validate_youtube_preview_payload(_preview())
        gates = {
            name: {"decision": "approved", "review_count": 1, "open_count": 0}
            for name in ("creative", "rights", "public_release")
        }
        self.binding = YouTubePublishBinding(
            request=request,
            delivery_artifact={
                "id": DELIVERY_ID,
                "production_id": PRODUCTION_ID,
                "sha256": _sha(b"verified-delivery"),
                "bytes": len(b"verified-delivery"),
            },
            video_artifact={
                "id": VIDEO_ID,
                "production_id": PRODUCTION_ID,
                "sha256": _sha(self.video_bytes),
                "bytes": len(self.video_bytes),
            },
            delivery_path=delivery_path,
            video_path=self.video_path,
            package_key="A" * 64,
            run_id=RUN_ID,
            source_job_id=SOURCE_JOB_ID,
            video_role="clean_master",
            release_gates=gates,
        )
        self.transport = _Transport()
        self.jobs = _DeferredJobs()
        self.service = object.__new__(StudioService)
        self.service.workspace = self.workspace
        self.service.database = object()
        self.service.secret_store = _MissingSecrets()
        self.service.jobs = self.jobs
        self.service.youtube_publish_ledger = YouTubePublishLedger(
            self.workspace,
            protect=lambda value, **_kwargs: bytes(item ^ 0xA5 for item in value),
            unprotect=lambda value: bytes(item ^ 0xA5 for item in value),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _resolver(
        self,
        _workspace: Path,
        _database: object,
        production_id: str,
        request: object,
    ) -> YouTubePublishBinding:
        self.assertEqual(production_id, PRODUCTION_ID)
        normalized = validate_youtube_preview_payload(request)
        return replace(self.binding, request=normalized)

    def test_preview_only_looks_up_channel_and_never_begins_upload(self) -> None:
        with (
            mock.patch(
                "tools.studio.service.resolve_youtube_publish_binding",
                side_effect=self._resolver,
            ),
            mock.patch.object(
                self.service, "_youtube_transport", return_value=self.transport
            ),
        ):
            result = self.service.youtube_publish_preview(PRODUCTION_ID, _preview())

        self.assertTrue(result["network_used"])
        self.assertFalse(result["upload_started"])
        self.assertEqual(result["confirmation"]["channel"], CHANNEL)
        self.assertEqual(self.transport.access_token_calls, 1)
        self.assertEqual(self.transport.channel_calls, 1)
        self.assertEqual(self.transport.begin_calls, 0)
        self.assertEqual(self.transport.query_calls, 0)
        self.assertEqual(self.transport.upload_calls, 0)

    def test_preview_fails_closed_when_oauth_is_not_configured(self) -> None:
        with mock.patch(
            "tools.studio.service.resolve_youtube_publish_binding",
            side_effect=self._resolver,
        ):
            with self.assertRaises(RequestValidationError) as raised:
                self.service.youtube_publish_preview(PRODUCTION_ID, _preview())

        self.assertEqual(raised.exception.code, "youtube_oauth_credential_invalid")

    def test_execute_requires_strict_confirmation_and_only_private_or_unlisted(self) -> None:
        body = _execute_body(self.binding)
        invalid = {**body, "certify_community_guidelines": False}
        with (
            mock.patch(
                "tools.studio.service.resolve_youtube_publish_binding",
                side_effect=self._resolver,
            ),
            mock.patch.object(
                self.service, "_youtube_transport", return_value=self.transport
            ),
        ):
            with self.assertRaises(RequestValidationError) as raised:
                self.service.execute_youtube_publish(PRODUCTION_ID, invalid)
            self.assertEqual(
                raised.exception.code,
                "youtube_guidelines_certification_required",
            )

            with self.assertRaises(RequestValidationError) as raised:
                self.service.youtube_publish_preview(
                    PRODUCTION_ID, _preview(privacy_status="public")
                )
            self.assertEqual(
                raised.exception.code,
                "youtube_public_privacy_not_supported",
            )

            unlisted = self.service.youtube_publish_preview(
                PRODUCTION_ID, _preview(privacy_status="unlisted")
            )
            self.assertEqual(
                unlisted["confirmation"]["request"]["privacy_status"],
                "unlisted",
            )
        self.assertEqual(len(self.jobs.submissions), 0)

    def test_execute_queues_then_worker_revalidates_binding_and_succeeds(self) -> None:
        body = _execute_body(self.binding)
        uploaded = {
            "schema_version": 1,
            "status": "succeeded",
            "video_id": "AbCdEf123_-",
        }
        resolver = mock.Mock(side_effect=self._resolver)
        with (
            mock.patch(
                "tools.studio.service.resolve_youtube_publish_binding", resolver
            ),
            mock.patch.object(
                self.service, "_youtube_transport", return_value=self.transport
            ),
            mock.patch(
                "tools.studio.service.execute_youtube_publish_upload",
                return_value=uploaded,
            ) as execute_upload,
        ):
            queued = self.service.execute_youtube_publish(PRODUCTION_ID, body)
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(resolver.call_count, 1)
            result = self.jobs.run()

        self.assertEqual(result, uploaded)
        self.assertEqual(resolver.call_count, 2)
        execute_upload.assert_called_once()
        worker_binding = execute_upload.call_args.kwargs
        self.assertEqual(worker_binding["video_path"], self.video_path)
        self.assertIs(worker_binding["ledger"], self.service.youtube_publish_ledger)
        payload = self.jobs.submissions[0]["job"]["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["channel_id"], CHANNEL["id"])
        self.assertNotIn("access-token", json.dumps(payload))
        self.assertNotIn("upload_id", json.dumps(payload))

    def test_worker_fails_if_source_or_release_gate_changes_after_queue(self) -> None:
        body = _execute_body(self.binding)
        changed = replace(
            self.binding,
            video_artifact={
                **self.binding.video_artifact,
                "sha256": "F" * 64,
            },
        )
        for second, expected_code in (
            (changed, "youtube_source_changed"),
            (
                YouTubePublishBindingError(
                    "release approval changed",
                    code="youtube_release_gate_required",
                ),
                "youtube_release_gate_required",
            ),
        ):
            with self.subTest(expected_code=expected_code):
                jobs = _DeferredJobs()
                self.service.jobs = jobs
                resolver = mock.Mock(side_effect=[self.binding, second])
                with (
                    mock.patch(
                        "tools.studio.service.resolve_youtube_publish_binding",
                        resolver,
                    ),
                    mock.patch.object(
                        self.service,
                        "_youtube_transport",
                        return_value=self.transport,
                    ),
                    mock.patch(
                        "tools.studio.service.execute_youtube_publish_upload"
                    ) as execute_upload,
                ):
                    self.service.execute_youtube_publish(PRODUCTION_ID, body)
                    with self.assertRaises(YouTubePublishError) as raised:
                        jobs.run()
                self.assertEqual(raised.exception.code, expected_code)
                execute_upload.assert_not_called()

    def test_terminal_ledger_retry_never_begins_a_second_upload_session(self) -> None:
        body = _execute_body(self.binding)
        with (
            mock.patch(
                "tools.studio.service.resolve_youtube_publish_binding",
                side_effect=self._resolver,
            ),
            mock.patch.object(
                self.service, "_youtube_transport", return_value=self.transport
            ),
        ):
            self.service.execute_youtube_publish(PRODUCTION_ID, body)
            first = self.jobs.run(0)
            self.service.execute_youtube_publish(PRODUCTION_ID, body)
            second = self.jobs.run(1)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(self.transport.begin_calls, 1)
        self.assertEqual(self.transport.upload_calls, 1)


class YouTubePublishRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "youtube-route-session-token-at-least-32-characters"
        self.server = create_server(
            self.workspace,
            host="127.0.0.1",
            port=0,
            session_token=self.token,
            initial_refresh=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temporary.cleanup()

    def _post(self, path: str) -> tuple[int, dict[str, object]]:
        body = json.dumps({"schema_version": 1}).encode("utf-8")
        self.connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        value = json.loads(response.read())
        return response.status, value

    def test_preview_and_execute_routes_return_200_and_202(self) -> None:
        preview = {"schema_version": 1, "upload_started": False}
        queued = {"id": "job_" + "1" * 32, "status": "queued"}
        self.server.service.youtube_publish_preview = mock.Mock(return_value=preview)
        self.server.service.execute_youtube_publish = mock.Mock(return_value=queued)

        status, value = self._post(
            f"/api/productions/{PRODUCTION_ID}/youtube-publish-preview"
        )
        self.assertEqual(status, 200)
        self.assertEqual(value, preview)
        status, value = self._post(
            f"/api/productions/{PRODUCTION_ID}/youtube-publish"
        )
        self.assertEqual(status, 202)
        self.assertEqual(value, queued)
        self.server.service.youtube_publish_preview.assert_called_once_with(
            PRODUCTION_ID, {"schema_version": 1}
        )
        self.server.service.execute_youtube_publish.assert_called_once_with(
            PRODUCTION_ID, {"schema_version": 1}
        )


if __name__ == "__main__":
    unittest.main()
