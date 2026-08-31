from __future__ import annotations

"""Closed YouTube publication contracts and a resumable HTTPS adapter.

The module deliberately separates validation/confirmation from the external
side effect.  Studio callers must show :func:`youtube_confirmation_summary`
to the user, bind the returned digest to the verified channel, and only then
call the transport.  ``public`` is not a supported privacy value.
"""

import hashlib
import http.client
import json
import math
import os
import re
import ssl
import stat as stat_module
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, BinaryIO, Callable, Mapping

from .security import canonical_json


YOUTUBE_PUBLISH_SCHEMA_VERSION = 1
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNEL_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_ALLOWED_PRIVACY = frozenset({"private", "unlisted"})
YOUTUBE_MAX_TITLE_CHARS = 100
YOUTUBE_MAX_DESCRIPTION_CHARS = 5_000
YOUTUBE_MAX_TAGS = 30
YOUTUBE_MAX_TAG_CHARS = 100
YOUTUBE_MAX_TAG_TOTAL_CHARS = 500
YOUTUBE_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,30}$")
_CATEGORY_ID_RE = re.compile(r"^[1-9][0-9]{0,2}$")
_DIGEST_RE = re.compile(r"^[0-9A-F]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class YouTubePublishValidationError(ValueError):
    """A bounded validation failure safe to expose to a local Studio user."""

    def __init__(self, message: str, *, code: str = "invalid_youtube_publish_request"):
        super().__init__(message)
        self.code = code


class YouTubePublishError(RuntimeError):
    """A bounded provider failure that never includes tokens or session URLs."""

    def __init__(self, message: str, *, code: str = "youtube_publish_failed"):
        super().__init__(message)
        self.code = code
        # JobManager deliberately trusts only this allowlisted attribute and a
        # bounded public_message.  Keep ``code`` as the synchronous service
        # contract while exposing the same safe value to background Jobs.
        self.error_code = code
        self.public_message = message


def _validation(message: str, code: str = "invalid_youtube_publish_request") -> YouTubePublishValidationError:
    return YouTubePublishValidationError(message, code=code)


def _clean_text(value: Any, *, label: str, maximum: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise _validation(f"{label} must be a string")
    clean = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if (not clean and not allow_empty) or len(clean) > maximum or _CONTROL_RE.search(clean):
        raise _validation(f"{label} is outside the supported limits")
    return clean


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > YOUTUBE_MAX_TAGS:
        raise _validation("tags must be a bounded array")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        tag = _clean_text(
            raw,
            label="tag",
            maximum=YOUTUBE_MAX_TAG_CHARS,
            allow_empty=False,
        )
        folded = tag.casefold()
        if folded in seen:
            raise _validation("tags must not contain duplicates")
        seen.add(folded)
        result.append(tag)
    if sum(len(item) for item in result) > YOUTUBE_MAX_TAG_TOTAL_CHARS:
        raise _validation("tags exceed the supported total length")
    return result


def validate_youtube_preview_payload(value: Any) -> dict[str, Any]:
    """Validate metadata before resolving the authenticated channel.

    The exact schema intentionally excludes any confirmation fields.  A
    confirmation is meaningful only after the channel identity is known.
    """

    expected = {
        "schema_version",
        "delivery_artifact_id",
        "video_artifact_id",
        "title",
        "description",
        "tags",
        "category_id",
        "privacy_status",
        "made_for_kids",
        "contains_synthetic_media",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise _validation("YouTube preview fields do not match the closed schema")
    if value.get("schema_version") != YOUTUBE_PUBLISH_SCHEMA_VERSION or isinstance(
        value.get("schema_version"), bool
    ):
        raise _validation("YouTube publish schema_version is not supported")
    delivery_id = value.get("delivery_artifact_id")
    video_id = value.get("video_artifact_id")
    if not isinstance(delivery_id, str) or _ARTIFACT_ID_RE.fullmatch(delivery_id) is None:
        raise _validation("delivery_artifact_id is invalid")
    if not isinstance(video_id, str) or _ARTIFACT_ID_RE.fullmatch(video_id) is None:
        raise _validation("video_artifact_id is invalid")
    privacy = value.get("privacy_status")
    if privacy not in YOUTUBE_ALLOWED_PRIVACY:
        raise _validation(
            "privacy_status must be private or unlisted",
            "youtube_public_privacy_not_supported",
        )
    category_id = value.get("category_id")
    if not isinstance(category_id, str) or _CATEGORY_ID_RE.fullmatch(category_id) is None:
        raise _validation("category_id is invalid")
    for field in ("made_for_kids", "contains_synthetic_media"):
        if not isinstance(value.get(field), bool):
            raise _validation(f"{field} must be a boolean")
    return {
        "schema_version": YOUTUBE_PUBLISH_SCHEMA_VERSION,
        "delivery_artifact_id": delivery_id,
        "video_artifact_id": video_id,
        "title": _clean_text(
            value.get("title"),
            label="title",
            maximum=YOUTUBE_MAX_TITLE_CHARS,
            allow_empty=False,
        ),
        "description": _clean_text(
            value.get("description"),
            label="description",
            maximum=YOUTUBE_MAX_DESCRIPTION_CHARS,
            allow_empty=True,
        ),
        "tags": _tags(value.get("tags")),
        "category_id": category_id,
        "privacy_status": privacy,
        "made_for_kids": value["made_for_kids"],
        "contains_synthetic_media": value["contains_synthetic_media"],
    }


def validate_youtube_channel(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"id", "title"}:
        raise _validation("YouTube channel identity is invalid", "invalid_youtube_channel")
    channel_id = value.get("id")
    if not isinstance(channel_id, str) or _CHANNEL_ID_RE.fullmatch(channel_id) is None:
        raise _validation("YouTube channel ID is invalid", "invalid_youtube_channel")
    title = _clean_text(
        value.get("title"), label="channel title", maximum=200, allow_empty=False
    )
    return {"id": channel_id, "title": title}


def youtube_publish_request_digest(preview: Mapping[str, Any]) -> str:
    normalized = validate_youtube_preview_payload(dict(preview))
    return hashlib.sha256(
        canonical_json(
            {"contract": "youtube-private-unlisted-v1", "request": normalized}
        ).encode("utf-8")
    ).hexdigest().upper()


def youtube_confirmation_digest(
    preview: Mapping[str, Any],
    channel: Mapping[str, Any],
    *,
    delivery_sha256: str,
    video_sha256: str,
) -> str:
    normalized = validate_youtube_preview_payload(dict(preview))
    normalized_channel = validate_youtube_channel(dict(channel))
    for label, digest in (
        ("delivery", delivery_sha256),
        ("video", video_sha256),
    ):
        if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest.upper()) is None:
            raise _validation(f"{label} SHA-256 is invalid")
    return hashlib.sha256(
        canonical_json(
            {
                "contract": "youtube-explicit-upload-confirmation-v1",
                "request": normalized,
                "channel": normalized_channel,
                "delivery_sha256": delivery_sha256.upper(),
                "video_sha256": video_sha256.upper(),
            }
        ).encode("utf-8")
    ).hexdigest().upper()


def youtube_confirmation_summary(
    preview: Mapping[str, Any],
    channel: Mapping[str, Any],
    *,
    delivery_sha256: str,
    video_sha256: str,
    video_bytes: int,
) -> dict[str, Any]:
    normalized = validate_youtube_preview_payload(dict(preview))
    normalized_channel = validate_youtube_channel(dict(channel))
    if isinstance(video_bytes, bool) or not isinstance(video_bytes, int) or video_bytes <= 0:
        raise _validation("video byte count is invalid")
    return {
        "schema_version": YOUTUBE_PUBLISH_SCHEMA_VERSION,
        "provider": "youtube",
        "channel": normalized_channel,
        "request": normalized,
        "video_bytes": video_bytes,
        "delivery_sha256": delivery_sha256.upper(),
        "video_sha256": video_sha256.upper(),
        "confirmation_digest": youtube_confirmation_digest(
            normalized,
            normalized_channel,
            delivery_sha256=delivery_sha256,
            video_sha256=video_sha256,
        ),
        "public_upload_supported": False,
        "explicit_confirmation_required": True,
        "community_guidelines_certification_required": True,
    }


def validate_youtube_execute_payload(
    value: Any,
    *,
    expected_preview: Mapping[str, Any],
    expected_channel: Mapping[str, Any],
    delivery_sha256: str,
    video_sha256: str,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "request",
        "expected_channel_id",
        "expected_channel_title",
        "confirmation_digest",
        "certify_community_guidelines",
        "confirm_upload",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise _validation("YouTube execute fields do not match the closed schema")
    if value.get("schema_version") != YOUTUBE_PUBLISH_SCHEMA_VERSION or isinstance(
        value.get("schema_version"), bool
    ):
        raise _validation("YouTube publish schema_version is not supported")
    preview = validate_youtube_preview_payload(value.get("request"))
    normalized_expected = validate_youtube_preview_payload(dict(expected_preview))
    if preview != normalized_expected:
        raise _validation("YouTube metadata changed after confirmation", "youtube_confirmation_changed")
    channel = validate_youtube_channel(dict(expected_channel))
    if (
        value.get("expected_channel_id") != channel["id"]
        or value.get("expected_channel_title") != channel["title"]
    ):
        raise _validation("YouTube channel changed after confirmation", "youtube_channel_changed")
    digest = youtube_confirmation_digest(
        preview,
        channel,
        delivery_sha256=delivery_sha256,
        video_sha256=video_sha256,
    )
    if value.get("confirmation_digest") != digest:
        raise _validation("YouTube confirmation digest is invalid", "youtube_confirmation_changed")
    if value.get("certify_community_guidelines") is not True:
        raise _validation(
            "Community Guidelines certification is required",
            "youtube_guidelines_certification_required",
        )
    if value.get("confirm_upload") is not True:
        raise _validation("Explicit YouTube upload confirmation is required", "youtube_confirmation_required")
    return {
        "schema_version": YOUTUBE_PUBLISH_SCHEMA_VERSION,
        "request": preview,
        "expected_channel_id": channel["id"],
        "expected_channel_title": channel["title"],
        "confirmation_digest": digest,
        "certify_community_guidelines": True,
        "confirm_upload": True,
    }


@dataclass(frozen=True)
class YouTubeOAuthCredential:
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def parse(cls, value: str) -> "YouTubeOAuthCredential":
        try:
            raw = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise YouTubePublishError(
                "The YouTube OAuth credential is invalid.",
                code="youtube_oauth_credential_invalid",
            ) from exc
        if not isinstance(raw, dict) or set(raw) != {
            "client_id",
            "client_secret",
            "refresh_token",
        }:
            raise YouTubePublishError(
                "The YouTube OAuth credential is invalid.",
                code="youtube_oauth_credential_invalid",
            )
        fields: list[str] = []
        for key in ("client_id", "client_secret", "refresh_token"):
            item = raw.get(key)
            if (
                not isinstance(item, str)
                or not item
                or len(item) > 4096
                or "\x00" in item
                or "\r" in item
                or "\n" in item
            ):
                raise YouTubePublishError(
                    "The YouTube OAuth credential is invalid.",
                    code="youtube_oauth_credential_invalid",
                )
            fields.append(item)
        return cls(*fields)


@dataclass(frozen=True)
class YouTubeHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


UrlOpen = Callable[..., Any]


class _YouTubeRedirectRejected(YouTubePublishError):
    def __init__(self) -> None:
        super().__init__(
            "The YouTube endpoint attempted a redirect, which is rejected.",
            code="youtube_redirect_rejected",
        )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> urllib.request.Request:
        raise _YouTubeRedirectRejected()


def _open_request(
    request: urllib.request.Request,
    *,
    timeout: float,
    context: ssl.SSLContext,
) -> Any:
    """Open one fixed Google request without following credential-bearing redirects."""

    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _NoRedirectHandler(),
    )
    return opener.open(request, timeout=timeout)


def _bounded_body(handle: BinaryIO) -> bytes:
    data = handle.read(YOUTUBE_MAX_RESPONSE_BYTES + 1)
    if len(data) > YOUTUBE_MAX_RESPONSE_BYTES:
        raise YouTubePublishError(
            "The YouTube response was too large.", code="youtube_response_too_large"
        )
    return data


def _json_response(response: YouTubeHttpResponse) -> dict[str, Any]:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise YouTubePublishError(
            "YouTube returned an invalid response.", code="invalid_youtube_response"
        ) from exc
    if not isinstance(value, dict):
        raise YouTubePublishError(
            "YouTube returned an invalid response.", code="invalid_youtube_response"
        )
    return value


def _safe_session_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as exc:
        raise YouTubePublishError(
            "YouTube returned an invalid upload session.",
            code="invalid_youtube_upload_session",
        ) from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.googleapis.com"
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/upload/youtube/v3/videos")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise YouTubePublishError(
            "YouTube returned an invalid upload session.",
            code="invalid_youtube_upload_session",
        )
    return urllib.parse.urlunsplit(parsed)


class YouTubeResumableTransport:
    """Minimal YouTube Data API adapter with bounded responses.

    Access tokens live only in local variables.  The caller owns durable,
    DPAPI-protected persistence of the resumable session URL and must never
    place that URL in jobs, events, logs, or public responses.
    """

    def __init__(
        self,
        credential: YouTubeOAuthCredential,
        *,
        urlopen: UrlOpen = _open_request,
        timeout_seconds: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
    ):
        if not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 120:
            raise ValueError("timeout_seconds is invalid")
        self.credential = credential
        self.urlopen = urlopen
        self.timeout_seconds = float(timeout_seconds)
        self.ssl_context = ssl_context or ssl.create_default_context()

    def _open(self, request: urllib.request.Request) -> YouTubeHttpResponse:
        try:
            with self.urlopen(
                request, timeout=self.timeout_seconds, context=self.ssl_context
            ) as response:
                result = YouTubeHttpResponse(
                    int(response.status),
                    {str(key).lower(): str(value) for key, value in response.headers.items()},
                    _bounded_body(response),
                )
                if result.status in {301, 302, 303, 307, 308}:
                    raise _YouTubeRedirectRejected()
                return result
        except _YouTubeRedirectRejected:
            raise
        except urllib.error.HTTPError as exc:
            if int(exc.code) in {301, 302, 303, 307, 308}:
                raise _YouTubeRedirectRejected() from exc
            body = _bounded_body(exc)
            return YouTubeHttpResponse(
                int(exc.code),
                {str(key).lower(): str(value) for key, value in exc.headers.items()},
                body,
            )
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise YouTubePublishError(
                "The YouTube network request did not complete.",
                code="youtube_network_failed",
            ) from exc

    def access_token(self) -> str:
        body = urllib.parse.urlencode(
            {
                "client_id": self.credential.client_id,
                "client_secret": self.credential.client_secret,
                "refresh_token": self.credential.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("ascii")
        response = self._open(
            urllib.request.Request(
                YOUTUBE_TOKEN_ENDPOINT,
                data=body,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )
        if response.status != 200:
            raise YouTubePublishError(
                "YouTube OAuth authorization failed.", code="youtube_oauth_failed"
            )
        value = _json_response(response)
        token = value.get("access_token")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or any(character in token for character in "\x00\r\n")
        ):
            raise YouTubePublishError(
                "YouTube OAuth authorization failed.", code="youtube_oauth_failed"
            )
        return token

    def channel(self, access_token: str) -> dict[str, str]:
        query = urllib.parse.urlencode(
            {"part": "id,snippet", "mine": "true", "maxResults": "1"}
        )
        response = self._open(
            urllib.request.Request(
                f"{YOUTUBE_CHANNEL_ENDPOINT}?{query}",
                method="GET",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        )
        if response.status != 200:
            raise YouTubePublishError(
                "The authenticated YouTube channel could not be resolved.",
                code="youtube_channel_lookup_failed",
            )
        value = _json_response(response)
        items = value.get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise YouTubePublishError(
                "The authenticated YouTube channel could not be resolved.",
                code="youtube_channel_lookup_failed",
            )
        snippet = items[0].get("snippet")
        if not isinstance(snippet, dict):
            raise YouTubePublishError(
                "The authenticated YouTube channel could not be resolved.",
                code="youtube_channel_lookup_failed",
            )
        try:
            return validate_youtube_channel(
                {"id": items[0].get("id"), "title": snippet.get("title")}
            )
        except YouTubePublishValidationError as exc:
            raise YouTubePublishError(
                "The authenticated YouTube channel could not be resolved.",
                code="youtube_channel_lookup_failed",
            ) from exc

    def begin(
        self,
        access_token: str,
        request: Mapping[str, Any],
        *,
        video_bytes: int,
        content_type: str = "video/mp4",
    ) -> str:
        normalized = validate_youtube_preview_payload(dict(request))
        if isinstance(video_bytes, bool) or not isinstance(video_bytes, int) or video_bytes <= 0:
            raise YouTubePublishError(
                "The YouTube source video is invalid.", code="youtube_source_invalid"
            )
        metadata = {
            "snippet": {
                "title": normalized["title"],
                "description": normalized["description"],
                "tags": normalized["tags"],
                "categoryId": normalized["category_id"],
            },
            "status": {
                "privacyStatus": normalized["privacy_status"],
                "selfDeclaredMadeForKids": normalized["made_for_kids"],
                "containsSyntheticMedia": normalized["contains_synthetic_media"],
            },
        }
        body = canonical_json(metadata).encode("utf-8")
        query = urllib.parse.urlencode(
            {"uploadType": "resumable", "part": "snippet,status"}
        )
        response = self._open(
            urllib.request.Request(
                f"{YOUTUBE_UPLOAD_ENDPOINT}?{query}",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(video_bytes),
                    "X-Upload-Content-Type": content_type,
                },
            )
        )
        location = response.headers.get("location")
        if response.status not in {200, 201} or not isinstance(location, str):
            raise YouTubePublishError(
                "The YouTube upload session was not created.",
                code="youtube_upload_session_failed",
            )
        return _safe_session_url(location)

    def query(self, access_token: str, session_url: str, *, video_bytes: int) -> YouTubeHttpResponse:
        safe_url = _safe_session_url(session_url)
        if isinstance(video_bytes, bool) or not isinstance(video_bytes, int) or video_bytes <= 0:
            raise YouTubePublishError(
                "The YouTube source video is invalid.", code="youtube_source_invalid"
            )
        return self._open(
            urllib.request.Request(
                safe_url,
                data=b"",
                method="PUT",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{video_bytes}",
                },
            )
        )

    @staticmethod
    def acknowledged_bytes(response: YouTubeHttpResponse) -> int:
        if response.status != 308:
            return 0
        value = response.headers.get("range", "")
        match = re.fullmatch(r"bytes=0-([0-9]+)", value)
        return int(match.group(1)) + 1 if match else 0

    def upload(
        self,
        access_token: str,
        session_url: str,
        video_handle: BinaryIO,
        *,
        expected_bytes: int,
        expected_sha256: str,
        start_byte: int = 0,
        content_type: str = "video/mp4",
        progress: Callable[[int, int], None] | None = None,
    ) -> YouTubeHttpResponse:
        safe_url = _safe_session_url(session_url)
        if (
            isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
            or expected_bytes <= 0
            or not isinstance(expected_sha256, str)
            or _DIGEST_RE.fullmatch(expected_sha256.upper()) is None
        ):
            raise YouTubePublishError(
                "The YouTube source video is unavailable.", code="youtube_source_invalid"
            )
        total = expected_bytes
        if (
            isinstance(start_byte, bool)
            or not isinstance(start_byte, int)
            or start_byte < 0
            or start_byte >= total
        ):
            raise YouTubePublishError(
                "The YouTube resume offset is invalid.", code="youtube_resume_offset_invalid"
            )
        digest = hashlib.sha256()
        try:
            if not video_handle.readable() or not video_handle.seekable():
                raise OSError("source handle is not readable and seekable")
            stat = os.fstat(video_handle.fileno())
            if not stat_module.S_ISREG(stat.st_mode) or stat.st_size != total:
                raise OSError("source handle size changed")
            video_handle.seek(0)
            remaining_prefix = start_byte
            while remaining_prefix:
                chunk = video_handle.read(min(1024 * 1024, remaining_prefix))
                if not chunk:
                    raise OSError("source handle ended before resume offset")
                digest.update(chunk)
                remaining_prefix -= len(chunk)
        except (AttributeError, OSError, ValueError) as exc:
            raise YouTubePublishError(
                "The YouTube source video is unavailable.", code="youtube_source_invalid"
            ) from exc
        parsed = urllib.parse.urlsplit(safe_url)
        target = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=self.timeout_seconds,
            context=self.ssl_context,
        )
        try:
            connection.putrequest("PUT", target, skip_accept_encoding=True)
            connection.putheader("Authorization", f"Bearer {access_token}")
            connection.putheader("Content-Type", content_type)
            connection.putheader("Content-Length", str(total - start_byte))
            if start_byte:
                connection.putheader(
                    "Content-Range", f"bytes {start_byte}-{total - 1}/{total}"
                )
            connection.endheaders()
            sent = start_byte
            remaining = total - start_byte
            while remaining:
                chunk = video_handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise YouTubePublishError(
                        "The verified YouTube source changed during upload.",
                        code="youtube_source_changed",
                    )
                connection.send(chunk)
                digest.update(chunk)
                sent += len(chunk)
                remaining -= len(chunk)
                if progress is not None:
                    progress(sent, total)
            if (
                video_handle.read(1)
                or sent != total
                or digest.hexdigest().upper() != expected_sha256.upper()
            ):
                raise YouTubePublishError(
                    "The verified YouTube source changed during upload.",
                    code="youtube_source_changed",
                )
            response = connection.getresponse()
            body = _bounded_body(response)
            return YouTubeHttpResponse(
                int(response.status),
                {str(key).lower(): str(value) for key, value in response.headers.items()},
                body,
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise YouTubePublishError(
                "The YouTube upload response is unknown.",
                code="youtube_upload_ambiguous",
            ) from exc
        finally:
            connection.close()


def validate_youtube_completion(
    response: YouTubeHttpResponse,
    *,
    expected_channel_id: str,
    expected_privacy_status: str,
) -> dict[str, str]:
    """Whitelist the final ``videos.insert`` response."""

    if response.status not in {200, 201}:
        raise YouTubePublishError(
            "The YouTube upload did not complete.", code="youtube_upload_incomplete"
        )
    value = _json_response(response)
    video_id = value.get("id")
    snippet = value.get("snippet")
    status = value.get("status")
    if (
        not isinstance(video_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", video_id)
        or not isinstance(snippet, dict)
        or snippet.get("channelId") != expected_channel_id
        or not isinstance(status, dict)
        or status.get("privacyStatus") != expected_privacy_status
    ):
        raise YouTubePublishError(
            "YouTube returned mismatched publication metadata.",
            code="invalid_youtube_response",
        )
    return {
        "video_id": video_id,
        "channel_id": expected_channel_id,
        "privacy_status": expected_privacy_status,
        "url": f"https://youtu.be/{video_id}",
    }


__all__ = [
    "YOUTUBE_ALLOWED_PRIVACY",
    "YOUTUBE_PUBLISH_SCHEMA_VERSION",
    "YOUTUBE_UPLOAD_SCOPE",
    "YouTubeHttpResponse",
    "YouTubeOAuthCredential",
    "YouTubePublishError",
    "YouTubePublishValidationError",
    "YouTubeResumableTransport",
    "validate_youtube_channel",
    "validate_youtube_completion",
    "validate_youtube_execute_payload",
    "validate_youtube_preview_payload",
    "youtube_confirmation_digest",
    "youtube_confirmation_summary",
    "youtube_publish_request_digest",
]
