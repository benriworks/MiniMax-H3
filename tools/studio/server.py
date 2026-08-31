from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.cookies
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO

from .instance_lock import StudioInstanceLockError, WorkspaceInstanceLock
from .security import (
    SecurityError,
    UnsafeTextArtifactError,
    redact_artifact_text,
    tokens_equal,
    unsafe_structured_text_suffix,
    workspace_path,
)
from .service import RequestValidationError, StudioService
from .production_intake import (
    MAX_VIDEO_IMPORT_BYTES,
    VIDEO_IMPORT_FILENAME_HEADER,
)
from .windows_capture import windows_capture_session_binding_digest


SESSION_COOKIE = "StudioSession"
MAX_JSON_BODY = 1024 * 1024
MAX_REDACTED_TEXT_BYTES = 16 * 1024 * 1024
# Windows does not reliably wake an already-blocked ``makefile().readline()``
# when another thread shuts down the accepted socket.  Keep the timeout short
# from the moment the handler is created so a partial request retires within
# the server-close drain budget even on that platform.  This is an inactivity
# timeout, not a limit on a parsed service operation.
REQUEST_SOCKET_TIMEOUT_SECONDS = 1.0
_SAFE_INLINE_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
_PRODUCTION_DETAIL_RE = re.compile(r"^/api/productions/([^/]+)$")
_PRODUCTION_IMPORT_VIDEO_RE = re.compile(
    r"^/api/productions/([^/]+)/artifacts/import-video$"
)
_PRODUCTION_RENAME_RE = re.compile(r"^/api/productions/([^/]+)/library/rename$")
_PRODUCTION_ARCHIVE_RE = re.compile(r"^/api/productions/([^/]+)/library/archive$")
_PRODUCTION_DUPLICATE_RE = re.compile(r"^/api/productions/([^/]+)/library/duplicate$")
_ARTIFACT_FILE_RE = re.compile(r"^/api/artifacts/([^/]+)/(?:file|content)$")
_JOB_DETAIL_RE = re.compile(r"^/api/jobs/([^/]+)$")
_JOB_CANCEL_RE = re.compile(r"^/api/jobs/([^/]+)/cancel$")
_RUN_DETAIL_RE = re.compile(r"^/api/runs/([^/]+)$")
_RERUN_PLAN_RE = re.compile(r"^/api/productions/([^/]+)/rerun-plan$")
_LOCAL_PIPELINE_RE = re.compile(
    r"^/api/productions/([^/]+)/execute-local-pipeline$"
)
_DETAILED_TEST_VIDEO_RE = re.compile(
    r"^/api/productions/([^/]+)/execute-detailed-test-video$"
)
_ANNOUNCEMENT_RECIPES_RE = re.compile(
    r"^/api/productions/([^/]+)/announcement-recipes$"
)
_ANNOUNCEMENT_RECIPE_SAVE_RE = re.compile(
    r"^/api/productions/([^/]+)/announcement-recipes/([^/]+)/save$"
)
_ANNOUNCEMENT_RECIPE_DUPLICATE_RE = re.compile(
    r"^/api/productions/([^/]+)/announcement-recipes/([^/]+)/duplicate$"
)
_ANNOUNCEMENT_RECIPE_EXECUTE_RE = re.compile(
    r"^/api/productions/([^/]+)/announcement-recipes/([^/]+)/execute$"
)
_REVIEWS_RE = re.compile(r"^/api/productions/([^/]+)/reviews$")
_REVIEW_RESOLVE_RE = re.compile(
    r"^/api/productions/([^/]+)/reviews/([^/]+)/resolve$"
)
_REVIEW_DECISION_RE = re.compile(
    r"^/api/productions/([^/]+)/reviews/([^/]+)/decision$"
)
_REVIEW_REVISION_PLAN_RE = re.compile(
    r"^/api/productions/([^/]+)/reviews/([^/]+)/revision-plan$"
)
_RUN_CREATE_RE = re.compile(r"^/api/productions/([^/]+)/runs$")
_RUN_APPROVE_RE = re.compile(r"^/api/runs/([^/]+)/approve$")
_RUN_LOCAL_NARRATION_RE = re.compile(r"^/api/runs/([^/]+)/execute-local-narration$")
_RUN_EXTERNAL_NARRATION_RE = re.compile(r"^/api/runs/([^/]+)/execute-external-narration$")
_RUN_VOICE_UPGRADE_RE = re.compile(r"^/api/runs/([^/]+)/execute-voice-upgrade$")
_RUN_LOCAL_VIDEO_GENERATION_RE = re.compile(
    r"^/api/runs/([^/]+)/execute-local-video-generation$"
)
_RUN_LOCAL_SCREEN_CAPTURE_RE = re.compile(
    r"^/api/runs/([^/]+)/execute-local-screen-capture$"
)
_RUN_WINDOWS_CAPTURE_RE = re.compile(
    r"^/api/runs/([^/]+)/execute-windows-capture$"
)
_RUN_WINDOWS_CAPTURE_CONSENT_RE = re.compile(
    r"^/api/runs/([^/]+)/windows-capture-consent-intents$"
)
_RUN_WINDOWS_CAPTURE_ACCEPTANCE_RE = re.compile(
    r"^/api/runs/([^/]+)/windows-capture-acceptance$"
)
_WINDOWS_CAPTURE_CANCEL_RE = re.compile(
    r"^/api/jobs/([^/]+)/cancel-windows-capture$"
)
_PROVIDER_TASK_RESUME_RE = re.compile(r"^/api/provider-tasks/([^/]+)/resume$")
_RUN_LOCAL_TIMELINE_RE = re.compile(r"^/api/runs/([^/]+)/execute-local-timeline$")
_RUN_REMOTION_TIMELINE_RE = re.compile(
    r"^/api/runs/([^/]+)/execute-remotion-timeline$"
)
_RUN_LOCAL_ASSEMBLY_RE = re.compile(r"^/api/runs/([^/]+)/execute-local-assembly$")
_RUN_LOCAL_QC_RE = re.compile(r"^/api/runs/([^/]+)/execute-local-qc$")
_AUDIT_EXPORT_RE = re.compile(r"^/api/productions/([^/]+)/audit-export$")
_DELIVERY_PACKAGE_RE = re.compile(
    r"^/api/productions/([^/]+)/delivery-packages$"
)
_YOUTUBE_PUBLISH_PREVIEW_RE = re.compile(
    r"^/api/productions/([^/]+)/youtube-publish-preview$"
)
_YOUTUBE_PUBLISH_RE = re.compile(
    r"^/api/productions/([^/]+)/youtube-publish$"
)


def _textual_artifact(artifact: dict[str, Any], path: Path) -> bool:
    media_type = str(artifact.get("media_type", "")).casefold()
    return bool(
        artifact.get("kind") in {"document", "log", "subtitle"}
        or media_type.startswith("text/")
        or any(marker in media_type for marker in ("json", "javascript", "xml", "yaml"))
        or unsafe_structured_text_suffix(path.suffix)
        or path.suffix.casefold() in {".ass", ".csv", ".json", ".jsonl", ".log", ".md", ".srt", ".tsv", ".txt", ".vtt", ".yaml", ".yml"}
    )


def _safe_inline_artifact(artifact: dict[str, Any], path: Path) -> bool:
    kind = artifact.get("kind")
    return bool(
        kind in {"audio", "video"}
        or (kind == "image" and path.suffix.casefold() in _SAFE_INLINE_IMAGE_SUFFIXES)
    )


def _studio_audit_download(artifact: dict[str, Any], path: Path) -> bool:
    relative = str(artifact.get("rel_path", "")).replace("\\", "/").casefold()
    return bool(
        artifact.get("origin") == "studio"
        and path.suffix.casefold() == ".zip"
        and (
            (
                artifact.get("kind") == "audit"
                and relative.startswith("outputs/studio/audits/")
            )
            or (
                artifact.get("kind") == "delivery"
                and relative.startswith("outputs/studio/deliveries/")
            )
        )
    )


def _open_download_handle(path: Path, *, deny_mutation: bool) -> BinaryIO:
    """Open one read handle; Windows integrity-bound downloads deny write/delete."""

    if os.name != "nt" or not deny_mutation:
        return path.open("rb")
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    raw_handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001,  # FILE_SHARE_READ only: deny concurrent write/delete
        None,
        3,  # OPEN_EXISTING
        0x00000080 | 0x08000000,  # NORMAL | SEQUENTIAL_SCAN
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if raw_handle in {None, invalid}:
        error = int(ctypes.get_last_error())
        raise OSError(error, "CreateFileW failed for artifact download")
    try:
        descriptor = msvcrt.open_osfhandle(
            int(raw_handle), os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
    except BaseException:
        close_handle(raw_handle)
        raise
    return os.fdopen(descriptor, "rb", closefd=True)


def _verify_registered_download(
    handle: BinaryIO,
    artifact: dict[str, Any],
) -> int:
    """Bind an archive download to the registered bytes, mtime and SHA-256."""

    expected_bytes = artifact.get("bytes")
    expected_mtime_ns = artifact.get("mtime_ns")
    expected_sha256 = artifact.get("sha256")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or not isinstance(expected_mtime_ns, int)
        or isinstance(expected_mtime_ns, bool)
        or expected_mtime_ns <= 0
        or not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9A-F]{64}", expected_sha256) is None
    ):
        raise OSError("registered artifact identity is invalid")
    stat = os.fstat(handle.fileno())
    if stat.st_size != expected_bytes or stat.st_mtime_ns != expected_mtime_ns:
        raise OSError("registered artifact metadata changed")
    digest = hashlib.sha256()
    handle.seek(0)
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    if digest.hexdigest().upper() != expected_sha256:
        raise OSError("registered artifact content changed")
    if os.fstat(handle.fileno()).st_size != expected_bytes:
        raise OSError("registered artifact size changed")
    handle.seek(0)
    return expected_bytes


def _loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _parse_authority(authority: str, *, default_port: int) -> tuple[str, int] | None:
    try:
        parsed = urllib.parse.urlsplit(f"//{authority}")
        if not parsed.hostname:
            return None
        return parsed.hostname.casefold(), parsed.port or default_port
    except ValueError:
        return None


def _normalized_origin(origin: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{parsed.scheme}://{parsed.hostname.casefold()}:{port}"
    except ValueError:
        return None


class StudioHTTPServer(ThreadingHTTPServer):
    # Request threads must drain before the workspace lock is released.  A
    # daemon handler can otherwise outlive server_close(), keep mutating the
    # SQLite ledger, and overlap a newly started Studio process that acquired
    # the same workspace lock.  block_on_close is explicit for clarity across
    # Python maintenance releases.
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: StudioService,
        *,
        session_token: str,
        static_dir: Path | None,
        allowed_origins: set[str],
        instance_lock: WorkspaceInstanceLock,
    ):
        self.service = service
        self.session_token = session_token
        self.static_dir = static_dir
        self.allowed_origins = allowed_origins
        self.instance_lock = instance_lock
        self._service_closed = False
        self._server_closed = False
        self._close_lock = threading.Lock()
        self._request_sockets_lock = threading.Lock()
        # False means request-line/headers/body parsing; True means a fully
        # parsed request is executing a service operation and must drain.
        self._request_sockets: dict[socket.socket, bool] = {}
        self._closing = False
        super().__init__(server_address, StudioRequestHandler)

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        """Track handler sockets so shutdown can interrupt partial requests."""

        with self._request_sockets_lock:
            if self._closing:
                try:
                    request.close()
                except OSError:
                    pass
                return
            self._request_sockets[request] = False
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._request_sockets_lock:
                self._request_sockets.pop(request, None)

    def server_close(self) -> None:
        # ThreadingMixIn.server_close() first closes the listening socket and
        # then joins every non-daemon request handler.  Only after that drain is
        # it safe to stop the shared service and release the system-wide
        # workspace lock.  If draining or service shutdown fails, retain the
        # lock so a second Studio cannot overlap still-live work in this
        # process; process exit remains the final OS-level release boundary.
        with self._close_lock:
            if self._server_closed:
                return
            with self._request_sockets_lock:
                self._closing = True
                request_sockets = tuple(
                    request
                    for request, active in self._request_sockets.items()
                    if not active
                )
            # A socket inactivity timeout alone can be defeated by a partial
            # loopback request that drips bytes.  Interrupt every accepted
            # connection before ThreadingMixIn joins handlers; already-running
            # service calls still drain normally and keep the lock held.
            for request in request_sockets:
                try:
                    request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    request.close()
                except OSError:
                    pass
            super().server_close()
            if not self._service_closed:
                self.service.close()
                self._service_closed = True
            self.instance_lock.close()
            self._server_closed = True

    def handle_error(self, _request: object, _client_address: object) -> None:
        # Client disconnects must not dump request context or stack traces into
        # the operator terminal. Endpoint errors are returned as bounded JSON.
        return


class StudioRequestHandler(BaseHTTPRequestHandler):
    server: StudioHTTPServer
    protocol_version = "HTTP/1.1"
    # Non-daemon handlers must not wait forever on an abandoned keep-alive
    # connection or partial loopback request during shutdown.
    timeout = REQUEST_SOCKET_TIMEOUT_SECONDS

    def log_message(self, _format: str, *_args: object) -> None:
        # Request bodies, query values and credentials must not become logs.
        return

    def _mark_request_active(self) -> None:
        """Protect a parsed service call from shutdown socket interruption."""

        with self.server._request_sockets_lock:
            if self.connection in self.server._request_sockets:
                self.server._request_sockets[self.connection] = True

    def _host_is_allowed(self) -> bool:
        authority = self.headers.get("Host", "")
        parsed = _parse_authority(authority, default_port=self.server.server_port)
        return bool(parsed and _loopback_host(parsed[0]))

    def _origin_is_allowed(self, origin: str) -> bool:
        normalized = _normalized_origin(origin)
        if normalized is None:
            return False
        if normalized in self.server.allowed_origins:
            return True
        parsed_origin = urllib.parse.urlsplit(normalized)
        host = _parse_authority(
            self.headers.get("Host", ""), default_port=self.server.server_port
        )
        return bool(
            host
            and parsed_origin.scheme == "http"
            and parsed_origin.hostname.casefold() == host[0]
            and parsed_origin.port == host[1]
        )

    def _cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(raw)
        except http.cookies.CookieError:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _post_is_authorized(self) -> bool:
        origin = self.headers.get("Origin")
        header_token = self.headers.get("X-Studio-Token")
        if tokens_equal(self.server.session_token, header_token):
            return origin is None or self._origin_is_allowed(origin)
        cookie_token = self._cookie_token()
        return bool(
            origin
            and self._origin_is_allowed(origin)
            and tokens_equal(self.server.session_token, cookie_token)
        )

    def _common_headers(self) -> None:
        # Bound every request thread to one response.  The Studio UI already
        # polls with independent fetches, and keeping HTTP/1.1 sockets alive
        # would let a continuously active client prevent ThreadingMixIn from
        # draining handlers during shutdown.  Per-response close therefore
        # preserves the handler -> service -> workspace-lock teardown order.
        self.close_connection = True
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")

    def _send_json(self, status: int, value: Any, *, send_body: bool = True) -> None:
        body = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _error(self, status: int, code: str, message: str, *, send_body: bool = True) -> None:
        self._send_json(
            status,
            {"error": {"code": code, "message": message}},
            send_body=send_body,
        )

    def _decoded_request(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlsplit(self.path)
        try:
            path = urllib.parse.unquote(parsed.path, errors="strict")
        except UnicodeDecodeError as exc:
            raise RequestValidationError("request path is invalid") from exc
        return path, urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    def _read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().casefold() != "application/json":
            raise RequestValidationError("Content-Type must be application/json", code="unsupported_media_type")
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise RequestValidationError("Content-Length is invalid") from exc
        if length < 0 or length > MAX_JSON_BODY:
            raise RequestValidationError("request body is too large", code="request_too_large")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestValidationError("request body is not valid JSON") from exc
        if not isinstance(value, dict):
            raise RequestValidationError("request body must be an object")
        return value

    def _video_import_content_length(self) -> int:
        if self.headers.get_all("Transfer-Encoding"):
            raise RequestValidationError(
                "Transfer-Encoding is not supported for video import",
                code="invalid_content_length",
            )
        values = self.headers.get_all("Content-Length") or []
        raw = values[0] if len(values) == 1 else None
        if raw is None or re.fullmatch(r"[0-9]+", raw) is None:
            raise RequestValidationError(
                "Content-Length is required for video import",
                code="invalid_content_length",
            )
        length = int(raw)
        if length <= 0:
            raise RequestValidationError(
                "Content-Length must be positive",
                code="invalid_content_length",
            )
        if length > MAX_VIDEO_IMPORT_BYTES:
            raise RequestValidationError(
                "video import is larger than the 2 GiB limit",
                code="request_too_large",
            )
        return length

    def _video_import_header(self, name: str, *, code: str, message: str) -> str:
        """Return one unambiguous upload header.

        The raw lane already rejects duplicate Content-Length fields. Apply
        the same closed framing rule to the media type and filename so two
        HTTP parsers cannot select different upload identities.
        """

        values = self.headers.get_all(name) or []
        if len(values) != 1 or not values[0]:
            raise RequestValidationError(message, code=code)
        return values[0]

    def _discard_bounded_request_body(self) -> None:
        """Drain a small unauthorized POST body before closing its socket.

        Closing a Windows TCP connection while unread request bytes remain can
        emit a reset instead of the intended HTTP 403 response.  Only the same
        bounded Content-Length accepted by the JSON parser is drained; invalid,
        chunked, or oversized bodies still fail closed without unbounded reads.
        """

        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            return
        if length < 0 or length > MAX_JSON_BODY:
            return
        remaining = length
        while remaining:
            chunk = self.rfile.read(min(64 * 1024, remaining))
            if not chunk:
                return
            remaining -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        self._mark_request_active()
        self._dispatch_get(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._mark_request_active()
        self._dispatch_get(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_is_allowed():
            self._discard_bounded_request_body()
            self.close_connection = True
            self._error(403, "forbidden_host", "The Host header is not allowed.")
            return
        if not self._post_is_authorized():
            self._discard_bounded_request_body()
            self.close_connection = True
            self._error(403, "forbidden", "A valid Studio session is required.")
            return
        raw_video_request = False
        try:
            path, _query = self._decoded_request()
            import_match = _PRODUCTION_IMPORT_VIDEO_RE.fullmatch(path)
            if import_match:
                raw_video_request = True
                length = self._video_import_content_length()
                filename_header = self._video_import_header(
                    VIDEO_IMPORT_FILENAME_HEADER,
                    code="invalid_video_filename",
                    message="X-Studio-Filename-Encoded is required exactly once",
                )
                content_type = self._video_import_header(
                    "Content-Type",
                    code="unsupported_media_type",
                    message="Content-Type is required exactly once",
                )
                self._mark_request_active()
                self._send_json(
                    201,
                    self.server.service.import_production_video(
                        import_match.group(1),
                        stream=self.rfile,
                        filename_header=filename_header,
                        content_type=content_type,
                        content_length=length,
                    ),
                )
                return
            body = self._read_json()
            self._mark_request_active()
            self._dispatch_post(path, body)
        except SecurityError:
            self._error(400, "invalid_path", "The requested path is invalid.")
        except RequestValidationError as exc:
            if raw_video_request:
                # A failed verifier may not have consumed the declared body.
                # Closing prevents it from becoming a second request.
                self.close_connection = True
            status = (
                415
                if exc.code == "unsupported_media_type"
                else 413
                if exc.code == "request_too_large"
                else 409
                if exc.code in {
                    "production_id_conflict",
                    "production_library_operation_conflict",
                    "production_library_revision_conflict",
                    "production_library_duplicate_conflict",
                    "review_already_resolved",
                    "review_idempotency_conflict",
                    "windows_capture_busy",
                    "windows_capture_unavailable",
                    "windows_capture_consent_expired",
                }
                else 422
            )
            self._error(status, exc.code, str(exc))
        except KeyError:
            if raw_video_request:
                self.close_connection = True
            self._error(404, "not_found", "The requested resource was not found.")
        except Exception:
            if raw_video_request:
                self.close_connection = True
            self._error(500, "internal_error", "The request could not be completed.")

    def do_OPTIONS(self) -> None:  # noqa: N802
        # Deliberately no CORS negotiation; the production UI is same-origin.
        self._mark_request_active()
        self._error(405, "method_not_allowed", "CORS is not enabled.")

    def _method_not_allowed(self) -> None:
        self.close_connection = True
        self._error(405, "method_not_allowed", "The HTTP method is not supported.")

    def do_DELETE(self) -> None:  # noqa: N802
        self._mark_request_active()
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._mark_request_active()
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._mark_request_active()
        self._method_not_allowed()

    def _dispatch_get(self, *, send_body: bool) -> None:
        if not self._host_is_allowed():
            self._error(403, "forbidden_host", "The Host header is not allowed.", send_body=send_body)
            return
        try:
            path, query = self._decoded_request()
            if path.startswith("/api/"):
                self._get_api(path, query, send_body=send_body)
            else:
                self._serve_static(path, send_body=send_body)
        except SecurityError:
            self._error(400, "invalid_path", "The requested path is invalid.", send_body=send_body)
        except RequestValidationError as exc:
            self._error(422, exc.code, str(exc), send_body=send_body)
        except KeyError:
            self._error(
                404,
                "not_found",
                "The requested resource was not found.",
                send_body=send_body,
            )
        except Exception:
            self._error(500, "internal_error", "The request could not be completed.", send_body=send_body)

    @staticmethod
    def _query_integer(
        query: dict[str, list[str]], name: str, default: int, *, minimum: int, maximum: int
    ) -> int:
        raw = query.get(name, [str(default)])[0]
        try:
            value = int(raw)
        except ValueError as exc:
            raise RequestValidationError(f"{name} must be an integer") from exc
        return max(minimum, min(value, maximum))

    @staticmethod
    def _query_boolean(
        query: dict[str, list[str]], name: str, default: bool
    ) -> bool:
        values = query.get(name)
        if values is None:
            return default
        if len(values) != 1 or values[0] not in {"true", "false"}:
            raise RequestValidationError(
                f"{name} must be true or false",
                code="invalid_production_library_query",
            )
        return values[0] == "true"

    @staticmethod
    def _query_text(
        query: dict[str, list[str]], name: str, default: str, *, maximum: int
    ) -> str:
        values = query.get(name)
        if values is None:
            return default
        if len(values) != 1 or len(values[0]) > maximum:
            raise RequestValidationError(
                f"{name} is invalid or too long",
                code="invalid_production_library_query",
            )
        return values[0]

    def _get_api(
        self, path: str, query: dict[str, list[str]], *, send_body: bool
    ) -> None:
        service = self.server.service
        if path == "/api/health":
            self._send_json(200, service.health(), send_body=send_body)
            return
        if path == "/api/productions":
            self._send_json(
                200,
                service.list_productions(
                    include_archived=self._query_boolean(
                        query, "include_archived", False
                    ),
                    query=self._query_text(query, "q", "", maximum=120),
                ),
                send_body=send_body,
            )
            return
        if path == "/api/jobs":
            limit = self._query_integer(query, "limit", 100, minimum=1, maximum=500)
            self._send_json(200, service.list_jobs(limit=limit), send_body=send_body)
            return
        if path == "/api/providers/status":
            self._send_json(200, service.providers_status(), send_body=send_body)
            return
        match = _ANNOUNCEMENT_RECIPES_RE.fullmatch(path)
        if match:
            self._send_json(
                200,
                service.list_announcement_recipes(match.group(1)),
                send_body=send_body,
            )
            return
        match = _REVIEWS_RE.fullmatch(path)
        if match:
            self._send_json(
                200,
                service.list_reviews(match.group(1)),
                send_body=send_body,
            )
            return
        match = _PRODUCTION_DETAIL_RE.fullmatch(path)
        if match:
            limit = self._query_integer(query, "artifact_limit", 5000, minimum=1, maximum=10_000)
            offset = self._query_integer(
                query, "artifact_offset", 0, minimum=0, maximum=100_000_000
            )
            detail = service.production_detail(
                match.group(1), artifact_limit=limit, artifact_offset=offset
            )
            if detail is None:
                self._error(404, "not_found", "The production was not found.", send_body=send_body)
            else:
                self._send_json(200, detail, send_body=send_body)
            return
        match = _JOB_DETAIL_RE.fullmatch(path)
        if match:
            job = service.job(match.group(1))
            if job is None:
                self._error(404, "not_found", "The job was not found.", send_body=send_body)
            else:
                self._send_json(200, job, send_body=send_body)
            return
        match = _RUN_DETAIL_RE.fullmatch(path)
        if match:
            run = service.run(match.group(1))
            if run is None:
                self._error(404, "not_found", "The run was not found.", send_body=send_body)
            else:
                self._send_json(200, run, send_body=send_body)
            return
        match = _ARTIFACT_FILE_RE.fullmatch(path)
        if match:
            self._serve_artifact(match.group(1), send_body=send_body)
            return
        self._error(404, "not_found", "The API endpoint was not found.", send_body=send_body)

    def _dispatch_post(self, path: str, body: dict[str, Any]) -> None:
        service = self.server.service
        session_binding_digest = windows_capture_session_binding_digest(
            self.server.session_token
        )
        if path == "/api/productions":
            self._send_json(201, service.create_production(body))
            return
        match = _PRODUCTION_RENAME_RE.fullmatch(path)
        if match:
            self._send_json(200, service.rename_production(match.group(1), body))
            return
        match = _PRODUCTION_ARCHIVE_RE.fullmatch(path)
        if match:
            self._send_json(200, service.archive_production(match.group(1), body))
            return
        match = _PRODUCTION_DUPLICATE_RE.fullmatch(path)
        if match:
            self._send_json(201, service.duplicate_production(match.group(1), body))
            return
        if path == "/api/capabilities/windows-capture/inspect":
            self._send_json(200, service.inspect_windows_capture_capability(body))
            return
        if path == "/api/index/refresh":
            self._send_json(202, service.refresh_index())
            return
        match = _JOB_CANCEL_RE.fullmatch(path)
        if match:
            self._send_json(202, service.cancel_job(match.group(1), body))
            return
        match = _RERUN_PLAN_RE.fullmatch(path)
        if match:
            self._send_json(200, service.rerun_plan(match.group(1), body.get("changes")))
            return
        match = _LOCAL_PIPELINE_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_local_pipeline(match.group(1), body))
            return
        match = _DETAILED_TEST_VIDEO_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.execute_detailed_test_video(match.group(1), body)
            )
            return
        match = _REVIEWS_RE.fullmatch(path)
        if match:
            self._send_json(201, service.create_review(match.group(1), body))
            return
        match = _REVIEW_RESOLVE_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.resolve_review(match.group(1), match.group(2), body),
            )
            return
        match = _REVIEW_DECISION_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.set_review_decision(match.group(1), match.group(2), body),
            )
            return
        match = _REVIEW_REVISION_PLAN_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.create_review_revision_plan(
                    match.group(1), match.group(2), body
                ),
            )
            return
        match = _ANNOUNCEMENT_RECIPE_SAVE_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.save_announcement_recipe(
                    match.group(1), match.group(2), body
                ),
            )
            return
        match = _ANNOUNCEMENT_RECIPE_DUPLICATE_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.duplicate_announcement_recipe(
                    match.group(1), match.group(2), body
                ),
            )
            return
        match = _ANNOUNCEMENT_RECIPE_EXECUTE_RE.fullmatch(path)
        if match:
            self._send_json(
                202,
                service.execute_announcement_recipe(
                    match.group(1), match.group(2), body
                ),
            )
            return
        match = _RUN_CREATE_RE.fullmatch(path)
        if match:
            self._send_json(201, service.create_run(match.group(1), body))
            return
        match = _RUN_APPROVE_RE.fullmatch(path)
        if match:
            self._send_json(200, service.approve_run(match.group(1), body))
            return
        match = _RUN_LOCAL_NARRATION_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_local_narration(match.group(1), body))
            return
        match = _RUN_EXTERNAL_NARRATION_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_external_narration(match.group(1), body))
            return
        match = _RUN_VOICE_UPGRADE_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_voice_upgrade(match.group(1), body))
            return
        match = _RUN_LOCAL_VIDEO_GENERATION_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.execute_local_video_generation(match.group(1), body)
            )
            return
        match = _RUN_LOCAL_SCREEN_CAPTURE_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.execute_local_screen_capture(match.group(1), body)
            )
            return
        match = _RUN_WINDOWS_CAPTURE_RE.fullmatch(path)
        if match:
            self._send_json(
                202,
                service.execute_windows_capture(
                    match.group(1),
                    body,
                    session_binding_digest=session_binding_digest,
                ),
            )
            return
        match = _RUN_WINDOWS_CAPTURE_CONSENT_RE.fullmatch(path)
        if match:
            self._send_json(
                201,
                service.issue_windows_capture_consent(
                    match.group(1),
                    body,
                    session_binding_digest=session_binding_digest,
                ),
            )
            return
        match = _RUN_WINDOWS_CAPTURE_ACCEPTANCE_RE.fullmatch(path)
        if match:
            recorded = service.record_windows_capture_acceptance(
                match.group(1), body
            )
            self._send_json(201 if recorded["created"] else 200, recorded)
            return
        match = _WINDOWS_CAPTURE_CANCEL_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.cancel_windows_capture_job(match.group(1), body)
            )
            return
        match = _PROVIDER_TASK_RESUME_RE.fullmatch(path)
        if match:
            if body:
                raise RequestValidationError(
                    "provider task resume body must be an empty object"
                )
            self._send_json(202, service.resume_provider_task(match.group(1)))
            return
        match = _RUN_LOCAL_TIMELINE_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_local_timeline(match.group(1), body))
            return
        match = _RUN_REMOTION_TIMELINE_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_remotion_timeline(match.group(1), body))
            return
        match = _RUN_LOCAL_ASSEMBLY_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_local_assembly(match.group(1), body))
            return
        match = _RUN_LOCAL_QC_RE.fullmatch(path)
        if match:
            self._send_json(202, service.execute_local_qc(match.group(1), body))
            return
        match = _AUDIT_EXPORT_RE.fullmatch(path)
        if match:
            self._send_json(202, service.audit_export(match.group(1), body))
            return
        match = _DELIVERY_PACKAGE_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.create_delivery_package(match.group(1), body)
            )
            return
        match = _YOUTUBE_PUBLISH_PREVIEW_RE.fullmatch(path)
        if match:
            self._send_json(
                200, service.youtube_publish_preview(match.group(1), body)
            )
            return
        match = _YOUTUBE_PUBLISH_RE.fullmatch(path)
        if match:
            self._send_json(
                202, service.execute_youtube_publish(match.group(1), body)
            )
            return
        self._error(404, "not_found", "The API endpoint was not found.")

    @staticmethod
    def _range(value: str | None, size: int) -> tuple[int, int] | None:
        if value is None:
            return None
        if not value.startswith("bytes=") or "," in value:
            raise RequestValidationError("Only one byte range is supported", code="invalid_range")
        specification = value[6:].strip()
        if "-" not in specification:
            raise RequestValidationError("The byte range is invalid", code="invalid_range")
        start_raw, end_raw = specification.split("-", 1)
        try:
            if start_raw:
                start = int(start_raw)
                end = int(end_raw) if end_raw else size - 1
            else:
                suffix = int(end_raw)
                if suffix <= 0:
                    raise ValueError
                start = max(0, size - suffix)
                end = size - 1
        except ValueError as exc:
            raise RequestValidationError("The byte range is invalid", code="invalid_range") from exc
        if start < 0 or start >= size or end < start:
            raise RequestValidationError("The byte range is unsatisfiable", code="invalid_range")
        return start, min(end, size - 1)

    def _serve_artifact(self, artifact_id: str, *, send_body: bool) -> None:
        try:
            artifact = self.server.service.artifact(artifact_id)
        except SecurityError:
            artifact = None
        if artifact is None or not artifact["available"]:
            self._error(404, "not_found", "The artifact was not found.", send_body=send_body)
            return
        try:
            path = workspace_path(
                self.server.service.workspace, artifact["rel_path"], must_exist=True
            )
            if not path.is_file() or path.is_symlink():
                raise OSError
            raw_size = path.stat().st_size
        except (OSError, SecurityError):
            self._error(404, "not_found", "The artifact file is unavailable.", send_body=send_body)
            return
        textual = _textual_artifact(artifact, path)
        archive_download = _studio_audit_download(artifact, path)
        if not textual and not _safe_inline_artifact(artifact, path) and not archive_download:
            self._error(
                415,
                "artifact_format_requires_local_review",
                "This artifact format is not exposed by the browser endpoint.",
                send_body=send_body,
            )
            return
        payload: bytes | None = None
        download_handle: BinaryIO | None = None
        if archive_download:
            try:
                download_handle = _open_download_handle(path, deny_mutation=True)
                raw_size = _verify_registered_download(download_handle, artifact)
            except OSError:
                if download_handle is not None:
                    download_handle.close()
                self._error(
                    404,
                    "not_found",
                    "The registered artifact file failed integrity verification.",
                    send_body=send_body,
                )
                return
        if textual:
            if raw_size > MAX_REDACTED_TEXT_BYTES:
                self._error(
                    413,
                    "artifact_too_large_for_safe_preview",
                    "The text artifact is too large for a redacted browser preview.",
                    send_body=send_body,
                )
                return
            try:
                original = path.read_text(encoding="utf-8-sig", errors="replace")
                payload = redact_artifact_text(original, suffix=path.suffix).encode("utf-8")
            except UnsafeTextArtifactError:
                self._error(
                    415,
                    "artifact_format_requires_local_review",
                    "This structured text format is not exposed because safe redaction is unavailable.",
                    send_body=send_body,
                )
                return
            except OSError:
                self._error(404, "not_found", "The artifact file is unavailable.", send_body=send_body)
                return
        try:
            size = len(payload) if payload is not None else raw_size
            try:
                byte_range = self._range(self.headers.get("Range"), size)
            except RequestValidationError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self._common_headers()
                self.end_headers()
                return
            start, end = byte_range if byte_range is not None else (0, size - 1)
            length = max(0, end - start + 1)
            self.send_response(206 if byte_range is not None else 200)
            content_type = artifact["media_type"]
            if textual and "charset=" not in content_type.casefold():
                content_type = f"{content_type}; charset=utf-8"
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            quoted_name = urllib.parse.quote(path.name, safe="")
            inline = _safe_inline_artifact(artifact, path) and not textual
            disposition = "inline" if inline else "attachment"
            self.send_header(
                "Content-Disposition",
                f"{disposition}; filename*=UTF-8''{quoted_name}",
            )
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            if textual:
                self.send_header("X-Studio-Content-Redacted", "true")
            if not inline:
                self.send_header(
                    "Content-Security-Policy",
                    "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'",
                )
            if byte_range is not None:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self._common_headers()
            self.end_headers()
            if not send_body or length == 0:
                return
            if payload is not None:
                self.wfile.write(payload[start : end + 1])
            elif download_handle is not None:
                download_handle.seek(start)
                remaining = length
                while remaining:
                    chunk = download_handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            else:
                with path.open("rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining:
                        chunk = handle.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        finally:
            if download_handle is not None:
                download_handle.close()

    def _serve_static(self, request_path: str, *, send_body: bool) -> None:
        static_root = self.server.static_dir
        if static_root is None or not static_root.is_dir():
            self._error(404, "not_found", "The Studio frontend is not installed.", send_body=send_body)
            return
        relative = request_path.lstrip("/") or "index.html"
        candidate = workspace_path(
            self.server.service.workspace, static_root / relative
        )
        try:
            candidate.relative_to(static_root)
        except ValueError as exc:
            raise SecurityError("static path is outside static directory") from exc
        if not candidate.is_file() and "." not in Path(relative).name:
            candidate = static_root / "index.html"
        if not candidate.is_file() or candidate.is_symlink():
            self._error(404, "not_found", "The frontend resource was not found.", send_body=send_body)
            return
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(candidate.name)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(content)))
        if candidate.name.casefold() == "index.html":
            fetch_site = self.headers.get("Sec-Fetch-Site", "none").casefold()
            if fetch_site in {"none", "same-origin", "same-site", ""}:
                cookie = http.cookies.SimpleCookie()
                cookie[SESSION_COOKIE] = self.server.session_token
                cookie[SESSION_COOKIE]["path"] = "/"
                cookie[SESSION_COOKIE]["httponly"] = True
                cookie[SESSION_COOKIE]["samesite"] = "Strict"
                self.send_header("Set-Cookie", cookie.output(header="").strip())
        self._common_headers()
        self.end_headers()
        if send_body:
            self.wfile.write(content)


def create_server(
    workspace: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | Path | None = None,
    session_token: str | None = None,
    allowed_origins: list[str] | tuple[str, ...] = (),
    initial_refresh: bool = True,
    database_path: Path | None = None,
) -> StudioHTTPServer:
    if not _loopback_host(host):
        raise ValueError("Studio only binds to a loopback host")
    workspace = workspace.resolve(strict=True)
    resolved_static: Path | None = None
    if static_dir is not None:
        resolved_static = workspace_path(workspace, static_dir)
    token = session_token or secrets.token_urlsafe(32)
    if len(token) < 32:
        raise ValueError("session token must contain at least 32 characters")
    normalized_origins: set[str] = set()
    for origin in allowed_origins:
        normalized = _normalized_origin(origin)
        if normalized is None:
            raise ValueError("allowed origin is invalid")
        origin_host = urllib.parse.urlsplit(normalized).hostname
        if origin_host is None or not _loopback_host(origin_host):
            raise ValueError("allowed origin must use a loopback host")
        normalized_origins.add(normalized)
    instance_lock = WorkspaceInstanceLock(workspace)
    service: StudioService | None = None
    try:
        service = StudioService(workspace, database_path=database_path)
        if initial_refresh:
            service.indexer.refresh()
        return StudioHTTPServer(
            (host, port),
            service,
            session_token=token,
            static_dir=resolved_static,
            allowed_origins=normalized_origins,
            instance_lock=instance_lock,
        )
    except BaseException:
        if service is not None:
            service.close()
        instance_lock.close()
        raise


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local MiniMaxH3 Studio backend")
    parser.add_argument("--workspace", type=Path, default=_default_workspace())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument("--allowed-origin", action="append", default=[])
    parser.add_argument("--no-initial-refresh", action="store_true")
    parser.add_argument("--open", action="store_true", help="Open the same-origin Studio UI")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    token = os.environ.get("MINIMAXH3_STUDIO_SESSION_TOKEN") or None
    try:
        server = create_server(
            arguments.workspace,
            host=arguments.host,
            port=arguments.port,
            static_dir=arguments.static_dir,
            session_token=token,
            allowed_origins=arguments.allowed_origin,
            initial_refresh=not arguments.no_initial_refresh,
        )
    except (OSError, ValueError, SecurityError, StudioInstanceLockError) as exc:
        print(f"Studio server could not start: {exc}", file=sys.stderr)
        return 2
    url = f"http://{arguments.host}:{server.server_port}/"
    print(f"MiniMaxH3 Studio listening on {url}")
    print("POST protection is active; the browser receives an HttpOnly same-site session cookie.")
    if arguments.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
