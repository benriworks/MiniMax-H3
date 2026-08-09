from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tools import h3_api


VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42mock-mp4"


class _MockHandler(BaseHTTPRequestHandler):
    server: "_MockHTTPServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        encoded = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.posts.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "json": json.loads(body),
            }
        )
        if self.server.post_redirect_url is not None:
            self.send_response(302)
            self.send_header("Location", self.server.post_redirect_url)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.server.post_error is not None:
            self._json(
                400,
                {"error": {"message": self.server.post_error, "http_code": "400"}},
            )
            return
        self._json(200, {"task_id": "task-123"})

    def do_GET(self) -> None:
        self.server.gets.append(
            {"path": self.path, "authorization": self.headers.get("Authorization")}
        )
        if self.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(VIDEO_BYTES)))
            self.end_headers()
            self.wfile.write(VIDEO_BYTES)
            return
        if self.path.startswith("/v2/query/video_generation/"):
            index = min(self.server.query_count, len(self.server.statuses) - 1)
            status = self.server.statuses[index]
            self.server.query_count += 1
            task = {"id": "task-123", "model": "MiniMax-H3", "status": status}
            if status == "succeeded":
                task["content"] = {"url": f"{self.server.url}/video.mp4"}
                task.update({"resolution": "768P", "duration": 5, "ratio": "16:9"})
            self._json(200, {"task": task})
            return
        self._json(404, {"error": {"message": "not found"}})


class _MockHTTPServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _MockHandler)
        self.posts: list[dict[str, object]] = []
        self.gets: list[dict[str, object]] = []
        self.statuses = ["queued", "running", "succeeded"]
        self.query_count = 0
        self.post_error: str | None = None
        self.post_redirect_url: str | None = None

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


@contextlib.contextmanager
def mock_server():
    server = _MockHTTPServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class PayloadTests(unittest.TestCase):
    def test_api_base_requires_https_except_exact_loopback_hosts(self) -> None:
        self.assertEqual(h3_api.normalize_api_base("http://localhost:8188/"), "http://localhost:8188")
        self.assertEqual(h3_api.normalize_api_base("http://127.0.0.1:8188"), "http://127.0.0.1:8188")
        self.assertEqual(h3_api.normalize_api_base("http://[::1]:8188"), "http://[::1]:8188")
        self.assertEqual(h3_api.normalize_api_base("https://api.example.test"), "https://api.example.test")
        for unsafe_base in (
            "http://api.example.test",
            "http://127.0.0.2:8188",
            "http://192.168.1.10:8188",
        ):
            with self.subTest(unsafe_base=unsafe_base), self.assertRaisesRegex(
                h3_api.H3ConfigurationError, "must use HTTPS"
            ):
                h3_api.normalize_api_base(unsafe_base)

    def test_local_image_is_encoded_as_data_url_with_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "frame.PNG"
            image.write_bytes(b"mock-png")
            payload = h3_api.build_generation_payload(
                prompt="Animate this frame",
                resolution="768P",
                duration=5,
                ratio="adaptive",
                images=[("first_frame", str(image))],
            )

        item = payload["content"][1]
        self.assertEqual(item["type"], "image_url")
        self.assertEqual(item["role"], "first_frame")
        data_url = item["image_url"]["url"]
        prefix, encoded = data_url.split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        self.assertEqual(base64.b64decode(encoded), b"mock-png")
        self.assertEqual(payload["ratio"], "adaptive")

    def test_ratio_and_mode_constraints_are_checked_before_http(self) -> None:
        with self.assertRaisesRegex(h3_api.H3ValidationError, "text-to-video requires"):
            h3_api.build_generation_payload(
                prompt="A quiet lake",
                resolution="768P",
                duration=5,
                ratio="adaptive",
            )
        with self.assertRaisesRegex(h3_api.H3ValidationError, "cannot be mixed"):
            h3_api.build_generation_payload(
                prompt="Mix modes",
                resolution="2K",
                duration=6,
                ratio="adaptive",
                images=[
                    ("first_frame", "https://example.test/first.png"),
                    ("reference_image", "https://example.test/reference.png"),
                ],
            )

    def test_reference_total_and_audio_only_constraints_are_checked(self) -> None:
        with self.assertRaisesRegex(h3_api.H3ValidationError, "audio-only"):
            h3_api.build_generation_payload(
                prompt="Use this soundtrack",
                resolution="768P",
                duration=5,
                ratio="16:9",
                audios=[("reference_audio", "https://example.test/reference.wav")],
            )

        images = [
            ("reference_image", f"https://example.test/reference-{index}.png")
            for index in range(9)
        ]
        videos = [
            ("reference_video", f"https://example.test/reference-{index}.mp4")
            for index in range(3)
        ]
        with self.assertRaisesRegex(h3_api.H3ValidationError, "12 reference files"):
            h3_api.build_generation_payload(
                prompt="Too many references",
                resolution="768P",
                duration=5,
                ratio="16:9",
                images=images,
                videos=videos,
                audios=[("reference_audio", "https://example.test/reference.wav")],
            )


class HTTPTests(unittest.TestCase):
    def test_submit_uses_v2_endpoint_and_bearer_auth(self) -> None:
        with mock_server() as server:
            client = h3_api.H3Client("test-secret", server.url)
            payload = h3_api.build_generation_payload(
                prompt="A paper plane takes flight",
                resolution="2K",
                duration=7,
                ratio="16:9",
            )
            response = client.submit(payload)

        self.assertEqual(response, {"task_id": "task-123"})
        self.assertEqual(len(server.posts), 1)
        self.assertEqual(server.posts[0]["path"], "/v2/video_generation")
        self.assertEqual(server.posts[0]["authorization"], "Bearer test-secret")
        self.assertEqual(server.posts[0]["json"]["model"], "MiniMax-H3")

    def test_wait_polls_and_downloads_without_leaking_api_key_to_cdn(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock_server() as server:
            output = Path(directory) / "result.mp4"
            client = h3_api.H3Client("download-secret", server.url)
            seen_statuses: list[str] = []
            response, downloaded = h3_api.wait_for_task(
                client,
                "task-123",
                interval=0.01,
                timeout=1,
                output=output,
                on_status=lambda status, _task: seen_statuses.append(status),
                sleep=lambda _seconds: None,
            )

            self.assertEqual(response["task"]["status"], "succeeded")
            self.assertEqual(downloaded, len(VIDEO_BYTES))
            self.assertEqual(output.read_bytes(), VIDEO_BYTES)

        self.assertEqual(seen_statuses, ["queued", "running", "succeeded"])
        query_requests = [item for item in server.gets if "/v2/query/" in item["path"]]
        download_requests = [item for item in server.gets if item["path"] == "/video.mp4"]
        self.assertTrue(query_requests)
        self.assertTrue(all(item["authorization"] == "Bearer download-secret" for item in query_requests))
        self.assertEqual(download_requests[0]["authorization"], None)

    def test_api_error_redacts_key_even_if_server_echoes_it(self) -> None:
        with mock_server() as server:
            server.post_error = "invalid credential secret-value"
            client = h3_api.H3Client("secret-value", server.url)
            with self.assertRaises(h3_api.H3APIError) as raised:
                client.submit({"model": "MiniMax-H3"})
        self.assertNotIn("secret-value", str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_api_redirect_is_rejected_without_forwarding_authorization(self) -> None:
        with mock_server() as redirect_target, mock_server() as api_server:
            api_server.post_redirect_url = f"{redirect_target.url}/redirect-target"
            client = h3_api.H3Client("redirect-secret", api_server.url)

            with self.assertRaisesRegex(h3_api.H3APIError, "HTTP 302"):
                client.submit({"model": "MiniMax-H3"})

        self.assertEqual(len(api_server.posts), 1)
        self.assertEqual(api_server.posts[0]["authorization"], "Bearer redirect-secret")
        self.assertEqual(redirect_target.posts, [])
        self.assertEqual(redirect_target.gets, [])


class CLITests(unittest.TestCase):
    def test_submit_requires_billable_confirmation_before_network(self) -> None:
        with mock_server() as server, mock.patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "billable-secret", "MINIMAX_API_BASE": server.url},
            clear=False,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = h3_api.main(
                    [
                        "submit",
                        "--prompt",
                        "Do not send this request",
                        "--resolution",
                        "768P",
                        "--duration",
                        "4",
                        "--ratio",
                        "16:9",
                    ]
                )

        self.assertNotEqual(exit_code, 0)
        self.assertEqual(server.posts, [])
        self.assertEqual(server.gets, [])
        self.assertIn("--confirm-billable", stderr.getvalue())
        self.assertNotIn("billable-secret", stdout.getvalue() + stderr.getvalue())

    def test_doctor_is_local_only_and_never_prints_key(self) -> None:
        with mock_server() as server, mock.patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "doctor-secret", "MINIMAX_API_BASE": server.url},
            clear=False,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = h3_api.main(["doctor", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(server.posts, [])
        self.assertEqual(server.gets, [])
        self.assertNotIn("doctor-secret", stdout.getvalue())
        self.assertNotIn("doctor-secret", stderr.getvalue())
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["ok"])
        self.assertFalse(result["network_request_made"])


if __name__ == "__main__":
    unittest.main()
