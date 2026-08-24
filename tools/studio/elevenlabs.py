from __future__ import annotations

"""Synchronous ElevenLabs ``with-timestamps`` Studio adapter.

The adapter makes exactly one provider request for a normalized set of
segments, turns the returned character alignment into segment captions and
timings, and converts the returned MP3 into a fixed PCM WAV through the same
bounded FFmpeg runner used by local assembly.  It publishes the three media /
metadata files plus a self-hashed manifest under the local Studio run tree.

The production endpoint is a constant HTTPS origin.  ``base_url`` exists only
for tests and is accepted only for a loopback origin; it is not part of the
public request body and never appears in persisted audit data.  The API key is
used only in the outbound ``xi-api-key`` header and is never included in an
exception, manifest, cache key, or returned result.
"""

import base64
import binascii
import hashlib
import io
import json
import math
import os
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable, Mapping

from .assembly import _bounded_process, _find_tool
from .external_tts_execution import (
    EXTERNAL_TTS_IMPLEMENTATION_VERSION,
    EXTERNAL_TTS_MODEL,
    EXTERNAL_TTS_OUTPUT_FORMAT,
    EXTERNAL_TTS_PROVIDER,
    EXTERNAL_TTS_SCHEMA_VERSION,
    EXTERNAL_TTS_TIMING_SOURCE,
    ExternalTTSError,
    ExternalTTSValidationError,
    external_tts_cache_key,
    external_tts_payload_digest,
    external_tts_public_result,
    external_tts_request_text,
    validate_external_tts_payload,
)
from .security import canonical_json, validate_identifier, workspace_path


PRODUCTION_BASE_URL = "https://api.elevenlabs.io"
ENDPOINT_PATH = "/v1/text-to-speech/{voice_id}/with-timestamps"
REQUEST_TIMEOUT_SECONDS = 120.0
FFMPEG_TIMEOUT_SECONDS = 5 * 60
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_MP3_BYTES = 48 * 1024 * 1024
MAX_WAV_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_DURATION_MS = 30 * 60 * 1000
MAX_ALIGNMENT_CHARS = 100_000
MAX_API_KEY_CHARS = 512
SUBMISSION_MARKER_FILENAME = ".submission-unknown.json"

_FILE_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "narration.wav", "kind": "audio", "mime": "audio/wav"},
    {"filename": "captions.srt", "kind": "subtitle", "mime": "application/x-subrip"},
    {"filename": "timings.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)
_CONTROL_CHARS = frozenset(chr(value) for value in range(32)) | {chr(127)}


class ExternalTTSSubmissionUnknown(ExternalTTSError):
    """Raised when transport failure occurs after the POST was initiated."""

    error_code = "external_submission_unknown"

    def __init__(self) -> None:
        super().__init__(
            "The external TTS submission outcome is unknown; do not retry automatically.",
            code=self.error_code,
        )


class ExternalTTSProviderError(ExternalTTSError):
    """Raised for a bounded, explicit provider HTTP response failure."""

    error_code = "external_provider_error"


class ExternalTTSMediaError(ExternalTTSError):
    """Raised when MP3/alignment/media output violates the adapter contract."""

    error_code = "external_tts_media_failed"


class _RedirectRejected(ExternalTTSError):
    error_code = "external_redirect_rejected"

    def __init__(self) -> None:
        super().__init__(
            "The external TTS endpoint attempted a redirect, which is rejected.",
            code=self.error_code,
        )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _safe_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _atomic_write(path: Path, data: bytes, *, maximum: int | None = None) -> None:
    if maximum is not None and len(data) > maximum:
        raise ExternalTTSMediaError(
            "The external TTS metadata is too large.",
            code="metadata_too_large",
        )
    temporary = path.with_name(f".{path.name}.partial")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    raise_if_cancelled = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(raise_if_cancelled):
        raise_if_cancelled()
        return
    is_set = getattr(cancel_event, "is_set", None)
    if callable(is_set) and is_set():
        raise ExternalTTSError(
            "The external TTS job was cancelled.", code="process_interrupted"
        )


def _ensure_directory(path: Path) -> None:
    """Create a directory only when every existing component is non-symlink."""

    path = path.resolve(strict=False)
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise ExternalTTSError("The Studio output path is unavailable.", code="unsafe_output_path")
        cursor = parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise ExternalTTSError("The Studio output path is unsafe.", code="unsafe_output_path")
    for item in reversed(missing):
        item.mkdir()


def _assert_no_symlink_components(workspace: Path, relative_path: Path) -> None:
    root = workspace.resolve(strict=True)
    cursor = root
    for part in relative_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ExternalTTSError("The Studio output path is unsafe.", code="unsafe_output_path")
        cursor = cursor / part
        if cursor.is_symlink():
            raise ExternalTTSError("The Studio output path is unsafe.", code="unsafe_output_path")


def _narration_root(workspace: Path, run_id: str) -> Path:
    relative = Path("outputs") / "studio" / "runs" / run_id / "narration"
    _assert_no_symlink_components(workspace, relative)
    root = workspace_path(
        workspace,
        relative,
        must_exist=False,
    )
    return root


def _cache_directory(workspace: Path, run_id: str, cache_key: str) -> Path:
    relative = Path("outputs") / "studio" / "runs" / run_id / "narration" / cache_key
    _assert_no_symlink_components(workspace, relative)
    return workspace_path(workspace, relative)


def _submission_marker_path(workspace: Path, production_id: str, cache_key: str) -> Path:
    """Return the production/cache identity marker shared across all runs."""

    relative = (
        Path("outputs")
        / "studio"
        / "external-submissions"
        / EXTERNAL_TTS_PROVIDER
        / production_id
        / cache_key
        / SUBMISSION_MARKER_FILENAME
    )
    _assert_no_symlink_components(workspace, relative)
    return workspace_path(
        workspace,
        relative,
        must_exist=False,
    )


def _marker_exists(marker: Path) -> bool:
    if not marker.exists() and not marker.is_symlink():
        return False
    if marker.is_symlink() or not marker.is_file():
        raise ExternalTTSError(
            "The external TTS submission state is unsafe.", code="unsafe_output_path"
        )
    try:
        if marker.stat().st_size > MAX_METADATA_BYTES:
            raise ExternalTTSError(
                "The external TTS submission state is invalid.",
                code="external_submission_unknown",
            )
        parsed = json.loads(marker.read_text(encoding="utf-8"))
    except ExternalTTSError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalTTSError(
            "The external TTS submission state is invalid.",
            code="external_submission_unknown",
        ) from exc
    if not isinstance(parsed, dict):
        raise ExternalTTSError(
            "The external TTS submission state is invalid.",
            code="external_submission_unknown",
        )
    return True


def _create_submission_marker(
    workspace: Path,
    production_id: str,
    cache_key: str,
    payload_digest: str,
) -> Path:
    marker = _submission_marker_path(workspace, production_id, cache_key)
    parent = marker.parent
    _ensure_directory(parent)
    if marker.exists() or marker.is_symlink():
        _marker_exists(marker)
        raise ExternalTTSSubmissionUnknown()
    content = (
        canonical_json(
            {
                "schema_version": EXTERNAL_TTS_SCHEMA_VERSION,
                "implementation_version": EXTERNAL_TTS_IMPLEMENTATION_VERSION,
                "provider": EXTERNAL_TTS_PROVIDER,
                "production_id": production_id,
                "cache_key": cache_key,
                "payload_digest": payload_digest,
            }
        )
        + "\n"
    ).encode("utf-8")
    temporary = marker.with_name(f".{marker.name}.partial")
    try:
        # Exclusive creation closes the cross-run double-submission race.  A
        # second worker that observes FileExistsError must not POST.
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, marker)
        except FileExistsError as exc:
            raise ExternalTTSSubmissionUnknown() from exc
        finally:
            temporary.unlink(missing_ok=True)
    except FileExistsError as exc:
        temporary.unlink(missing_ok=True)
        raise ExternalTTSSubmissionUnknown() from exc
    except ExternalTTSError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ExternalTTSError(
            "The external TTS submission state could not be created.",
            code="publish_failed",
        ) from exc
    return marker


def _remove_submission_marker(marker: Path) -> None:
    if not marker.exists() and not marker.is_symlink():
        return
    if marker.is_symlink() or not marker.is_file():
        raise ExternalTTSError(
            "The external TTS submission state is unsafe.", code="unsafe_output_path"
        )
    try:
        marker.unlink()
    except OSError as exc:
        # Keeping the marker is safer than returning a success that would allow
        # a later run to submit the same billable identity again.
        raise ExternalTTSError(
            "The external TTS submission state could not be finalized.",
            code="external_submission_unknown",
        ) from exc


def _artifact_record(workspace: Path, cache_directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    path = cache_directory / spec["filename"]
    if not _safe_file(path):
        raise ExternalTTSMediaError(
            "The external TTS artifact is unavailable.", code="cache_integrity_failed"
        )
    stat = path.stat()
    relative = path.relative_to(workspace.resolve(strict=True)).as_posix()
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": stat.st_size,
        "sha256": _sha256_file(path),
        "mime": spec["mime"],
        "media_type": spec["mime"],
        # Studio's registry treats provider-produced files as Studio-owned
        # derived artifacts once they pass the worker allowlist.
        "origin": "studio",
        "version": EXTERNAL_TTS_IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _format_srt_time(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _seconds_to_ms(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExternalTTSMediaError(
            "The external TTS provider returned invalid alignment.",
            code="invalid_external_alignment",
        )
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > MAX_DURATION_MS / 1000:
        raise ExternalTTSMediaError(
            "The external TTS provider returned invalid alignment.",
            code="invalid_external_alignment",
        )
    # Round half up without importing decimal; alignment values are normally
    # millisecond-scale floats and this avoids banker-rounding to zero cues.
    return int(number * 1000.0 + 0.5)


def _alignment_document(
    payload: Mapping[str, Any], response: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Validate character alignment and derive one timing row per segment."""

    alignment = response.get("alignment")
    if not isinstance(alignment, dict):
        # Some API versions expose the same shape as normalized_alignment.  It
        # is still character alignment and remains auditable as such; the
        # original alignment is preferred whenever present.
        alignment = response.get("normalized_alignment")
    if not isinstance(alignment, dict):
        raise ExternalTTSMediaError(
            "The external TTS provider returned no character alignment.",
            code="invalid_external_alignment",
        )
    characters = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")
    if (
        not isinstance(characters, list)
        or not isinstance(starts, list)
        or not isinstance(ends, list)
        or not characters
        or len(characters) != len(starts)
        or len(characters) != len(ends)
        or len(characters) > MAX_ALIGNMENT_CHARS
    ):
        raise ExternalTTSMediaError(
            "The external TTS provider returned invalid character alignment.",
            code="invalid_external_alignment",
        )
    clean_characters: list[str] = []
    start_ms: list[int] = []
    end_ms: list[int] = []
    previous_start = 0
    previous_end = 0
    for index, (character, start, end) in enumerate(zip(characters, starts, ends, strict=True)):
        if not isinstance(character, str) or len(character) != 1:
            raise ExternalTTSMediaError(
                "The external TTS provider returned invalid character alignment.",
                code="invalid_external_alignment",
            )
        # ``\n`` is the single separator intentionally inserted between public
        # segments for the one-request contract.  It must remain part of the
        # alignment comparison, while all other controls are rejected.
        if any(item in _CONTROL_CHARS and item not in "\t\n" for item in character):
            raise ExternalTTSMediaError(
                "The external TTS provider returned invalid character alignment.",
                code="invalid_external_alignment",
            )
        current_start = _seconds_to_ms(start, field=f"alignment.start[{index}]")
        current_end = _seconds_to_ms(end, field=f"alignment.end[{index}]")
        if current_end < current_start or current_start < previous_start or current_end < previous_end:
            raise ExternalTTSMediaError(
                "The external TTS provider returned non-monotonic alignment.",
                code="invalid_external_alignment",
            )
        clean_characters.append(character)
        start_ms.append(current_start)
        end_ms.append(current_end)
        previous_start = current_start
        previous_end = current_end

    joined_text = external_tts_request_text(payload)
    if "".join(clean_characters) != joined_text:
        raise ExternalTTSMediaError(
            "The external TTS provider alignment does not match the submitted text.",
            code="invalid_external_alignment",
        )

    rows: list[dict[str, Any]] = []
    cursor = 0
    duration_ms = 0
    for index, segment in enumerate(payload["segments"]):
        text = segment["text"]
        count = len(text)
        segment_start = start_ms[cursor]
        segment_end = end_ms[cursor + count - 1]
        # A provider may give a zero-length timing for punctuation/whitespace.
        # SRT requires a positive interval; retain alignment start and produce
        # the smallest representable cue without moving past the next cue.
        if segment_end <= segment_start:
            segment_end = segment_start + 1
        row = {
            "index": index,
            "text": text,
            "start_ms": segment_start,
            "end_ms": segment_end,
            "duration_ms": segment_end - segment_start,
            "character_start_index": cursor,
            "character_end_index": cursor + count,
            "character_count": count,
        }
        rows.append(row)
        duration_ms = max(duration_ms, segment_end)
        cursor += count
        if index < len(payload["segments"]) - 1:
            # The request text contains one separator newline between adjacent
            # segments.  It participates in alignment but not in either cue.
            cursor += 1

    alignment_data = {
        "characters": clean_characters,
        "character_start_times_seconds": [float(value) for value in starts],
        "character_end_times_seconds": [float(value) for value in ends],
    }
    return rows, duration_ms, alignment_data


def _build_captions(rows: list[dict[str, Any]]) -> bytes:
    blocks: list[str] = []
    for index, row in enumerate(rows, start=1):
        blocks.append(
            "\n".join(
                (
                    str(index),
                    f"{_format_srt_time(row['start_ms'])} --> {_format_srt_time(row['end_ms'])}",
                    row["text"],
                    "",
                )
            )
        )
    return "\n".join(blocks).encode("utf-8")


def _read_bounded_response(response: Any, *, deadline: float | None = None) -> bytes:
    """Read a provider response under both byte and wall-clock bounds.

    ``urllib``'s socket timeout is an inactivity timeout, not a total-response
    deadline.  A provider that drips one byte before each socket timeout could
    therefore keep a billable job alive indefinitely.  The caller supplies a
    monotonic deadline that includes connection and response-body time.
    """

    headers = getattr(response, "headers", None)
    content_length = _header_value(headers, "content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except (TypeError, ValueError) as exc:
            raise ExternalTTSProviderError(
                "The external TTS provider returned invalid response metadata.",
                code="external_provider_error",
            ) from exc
        if declared < 0 or declared > MAX_RESPONSE_BYTES:
            raise ExternalTTSProviderError(
                "The external TTS provider response is too large.",
                code="external_response_too_large",
            )
    chunks: list[bytes] = []
    total = 0
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise ExternalTTSSubmissionUnknown()
        chunk = response.read(min(1024 * 1024, MAX_RESPONSE_BYTES - total + 1))
        if deadline is not None and time.monotonic() >= deadline:
            raise ExternalTTSSubmissionUnknown()
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise ExternalTTSProviderError(
                "The external TTS provider returned an invalid response.",
                code="external_provider_error",
            )
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ExternalTTSProviderError(
                "The external TTS provider response is too large.",
                code="external_response_too_large",
            )
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def _header_value(headers: Any, name: str) -> Any:
    if headers is None:
        return None
    get = getattr(headers, "get", None)
    if callable(get):
        value = get(name)
        if value is not None:
            return value
    items = getattr(headers, "items", None)
    if callable(items):
        try:
            for key, value in items():
                if isinstance(key, str) and key.casefold() == name.casefold():
                    return value
        except Exception:
            return None
    return None


def _parse_provider_response(response_body: bytes) -> tuple[dict[str, Any], bytes]:
    if len(response_body) > MAX_RESPONSE_BYTES:
        raise ExternalTTSProviderError(
            "The external TTS provider response is too large.",
            code="external_response_too_large",
        )
    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalTTSProviderError(
            "The external TTS provider returned invalid JSON.",
            code="external_response_invalid",
        ) from exc
    if not isinstance(parsed, dict):
        raise ExternalTTSProviderError(
            "The external TTS provider returned an invalid response.",
            code="external_response_invalid",
        )
    encoded = parsed.get("audio_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ExternalTTSProviderError(
            "The external TTS provider returned no audio.",
            code="external_response_invalid",
        )
    # Base64 expands by 4/3.  Check the encoded bound before allocating the
    # decoded byte string, then use validate=True to reject ignored garbage.
    if len(encoded) > ((MAX_MP3_BYTES + 2) // 3) * 4 + 4:
        raise ExternalTTSProviderError(
            "The external TTS provider audio is too large.",
            code="external_audio_too_large",
        )
    try:
        audio = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ExternalTTSProviderError(
            "The external TTS provider returned invalid audio.",
            code="external_response_invalid",
        ) from exc
    if not audio or len(audio) > MAX_MP3_BYTES:
        raise ExternalTTSProviderError(
            "The external TTS provider audio is too large.",
            code="external_audio_too_large",
        )
    return parsed, audio


def _validate_api_key(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_API_KEY_CHARS:
        raise ExternalTTSError(
            "The ElevenLabs credential is unavailable.",
            code="external_tts_credentials_missing",
        )
    if any(character in _CONTROL_CHARS for character in value):
        raise ExternalTTSError(
            "The ElevenLabs credential is unavailable.",
            code="external_tts_credentials_missing",
        )
    return value


def _validate_base_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    try:
        parsed = urllib.parse.urlsplit(value.rstrip("/"))
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ExternalTTSError(
            "The external TTS endpoint is invalid.", code="invalid_external_endpoint"
        ) from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    if not hostname:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    host = hostname.casefold()
    if value.rstrip("/") == PRODUCTION_BASE_URL:
        return PRODUCTION_BASE_URL
    # Test injection is constrained to loopback and cannot be used to proxy a
    # request to an arbitrary network host.  HTTP is accepted only here; the
    # production origin above is HTTPS-only.
    if host not in {"127.0.0.1", "::1"}:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    if port is not None and not 1 <= port <= 65535:
        raise ExternalTTSError("The external TTS endpoint is invalid.", code="invalid_external_endpoint")
    return value.rstrip("/")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> urllib.request.Request:
        raise _RedirectRejected()


def _open_request(request: urllib.request.Request, *, timeout: float) -> Any:
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def _endpoint_url(base_url: str, voice_id: str) -> str:
    escaped_voice = urllib.parse.quote(voice_id, safe="")
    path = ENDPOINT_PATH.format(voice_id=escaped_voice)
    query = urllib.parse.urlencode({"output_format": EXTERNAL_TTS_OUTPUT_FORMAT})
    return f"{base_url.rstrip('/')}{path}?{query}"


def _build_request(base_url: str, api_key: str, payload: Mapping[str, Any]) -> urllib.request.Request:
    body: dict[str, Any] = {
        "text": external_tts_request_text(payload),
        "model_id": EXTERNAL_TTS_MODEL,
        "voice_settings": dict(payload["voice_settings"]),
    }
    if payload.get("seed") is not None:
        body["seed"] = payload["seed"]
    try:
        encoded_body = (canonical_json(body) + "\n").encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as exc:
        raise ExternalTTSError(
            "The external TTS request could not be encoded.", code="external_request_invalid"
        ) from exc
    return urllib.request.Request(
        _endpoint_url(base_url, payload["voice_id"]),
        data=encoded_body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
    )


def _provider_request(
    base_url: str,
    api_key: str,
    payload: Mapping[str, Any],
    *,
    timeout: float,
    cancel_event: Any | None = None,
    opener: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], bytes, str | None, int | None]:
    _raise_if_cancelled(cancel_event)
    request = _build_request(base_url, api_key, payload)
    open_call = opener or _open_request
    submitted = False
    response: Any = None
    try:
        # Set this immediately before opener invocation.  Any timeout, reset,
        # or broken connection after this point is deliberately not retried:
        # the provider may have accepted and billed the request.
        submitted = True
        deadline = time.monotonic() + max(0.0, float(timeout))
        response = open_call(request, timeout=timeout)
        status = getattr(response, "status", None)
        if status is not None and status != 200:
            if isinstance(status, int) and status >= 500:
                raise ExternalTTSSubmissionUnknown()
            raise ExternalTTSProviderError(
                "The external TTS provider rejected the request.",
                code="external_provider_error",
            )
        response_body = _read_bounded_response(response, deadline=deadline)
        request_id = _bounded_metadata_header(_header_value(getattr(response, "headers", None), "request-id"))
        character_cost = _parse_character_cost(
            _header_value(getattr(response, "headers", None), "character-cost")
        )
        parsed, audio = _parse_provider_response(response_body)
        _raise_if_cancelled(cancel_event)
        return parsed, audio, request_id, character_cost
    except _RedirectRejected:
        raise
    except ExternalTTSError:
        raise
    except urllib.error.HTTPError as exc:
        # A concrete HTTP response is not a transport ambiguity.  Do not copy
        # the provider body into the exception because it can contain secrets.
        code = getattr(exc, "code", None)
        if code in {301, 302, 303, 307, 308}:
            raise _RedirectRejected() from exc
        if isinstance(code, int) and code >= 500:
            raise ExternalTTSError(
                "The external TTS provider returned a server error.",
                code="external_submission_unknown",
            ) from exc
        raise ExternalTTSProviderError(
            "The external TTS provider rejected the request.",
            code="external_provider_error",
        ) from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as exc:
        if submitted:
            raise ExternalTTSSubmissionUnknown() from exc
        raise ExternalTTSError(
            "The external TTS request could not be sent.",
            code="external_tts_network_failed",
        ) from exc
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


def _bounded_metadata_header(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ExternalTTSError(
                "The external TTS provider returned invalid metadata.",
                code="invalid_external_provider_metadata",
            ) from exc
    if not isinstance(value, str) or not value or len(value) > 256 or any(
        character in _CONTROL_CHARS for character in value
    ):
        raise ExternalTTSError(
            "The external TTS provider returned invalid metadata.",
            code="invalid_external_provider_metadata",
        )
    return value


def _parse_character_cost(value: Any) -> int | None:
    value = _bounded_metadata_header(value)
    if value is None:
        return None
    if not value.isascii() or not value.isdigit() or (
        len(value) > 1 and value.startswith("0")
    ):
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        )
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        ) from exc
    if parsed > 2**63 - 1:
        raise ExternalTTSError(
            "The external TTS provider returned invalid cost metadata.",
            code="invalid_external_provider_metadata",
        )
    return parsed


def _convert_mp3_to_wav(
    stage_directory: Path,
    *,
    ffmpeg: str | Path | None,
    cancel_event: Any | None,
) -> Path:
    mp3_path = stage_directory / ".provider-audio.mp3"
    output_path = stage_directory / ".narration.wav"
    try:
        executable = _find_tool("ffmpeg", ffmpeg)
        arguments = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            mp3_path.name,
            "-vn",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            output_path.name,
        ]
        _bounded_process(
            arguments,
            cwd=stage_directory,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            label="external TTS FFmpeg",
            cancel_event=cancel_event,
        )
    except ExternalTTSError:
        raise
    except Exception as exc:
        if cancel_event is not None:
            is_set = getattr(cancel_event, "is_set", None)
            if callable(is_set) and is_set():
                _raise_if_cancelled(cancel_event)
        raise ExternalTTSMediaError(
            "The external TTS audio conversion failed.",
            code="external_tts_ffmpeg_failed",
        ) from exc
    if not _safe_file(output_path):
        raise ExternalTTSMediaError(
            "The external TTS conversion produced no WAV.",
            code="external_tts_ffmpeg_failed",
        )
    try:
        size = output_path.stat().st_size
    except OSError as exc:
        raise ExternalTTSMediaError(
            "The external TTS conversion produced an invalid WAV.",
            code="external_tts_ffmpeg_failed",
        ) from exc
    if size <= 44 or size > MAX_WAV_BYTES:
        raise ExternalTTSMediaError(
            "The external TTS conversion produced an invalid WAV.",
            code="external_tts_ffmpeg_failed",
        )
    return output_path


def _validate_pcm_wav(path: Path) -> tuple[int, int, int, int]:
    try:
        with path.open("rb") as source:
            if path.stat().st_size > MAX_WAV_BYTES:
                raise ExternalTTSMediaError(
                    "The external TTS WAV is too large.", code="external_audio_too_large"
                )
            with wave.open(source) as handle:
                channels = handle.getnchannels()
                sample_width = handle.getsampwidth()
                sample_rate = handle.getframerate()
                frame_count = handle.getnframes()
                compression = handle.getcomptype()
                if (
                    channels <= 0
                    or channels > 8
                    or sample_width != 2
                    or sample_rate != 44100
                    or compression != "NONE"
                    or frame_count <= 0
                ):
                    raise ExternalTTSMediaError(
                        "The external TTS conversion produced an unsupported WAV.",
                        code="external_tts_ffmpeg_failed",
                    )
                frames = handle.readframes(frame_count)
                if len(frames) != frame_count * channels * sample_width:
                    raise ExternalTTSMediaError(
                        "The external TTS conversion produced a truncated WAV.",
                        code="external_tts_ffmpeg_failed",
                    )
                duration_ms = (frame_count * 1000) // sample_rate
    except ExternalTTSError:
        raise
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise ExternalTTSMediaError(
            "The external TTS conversion produced an invalid WAV.",
            code="external_tts_ffmpeg_failed",
        ) from exc
    if duration_ms <= 0 or duration_ms > MAX_DURATION_MS:
        raise ExternalTTSMediaError(
            "The external TTS WAV duration is invalid.", code="external_audio_too_large"
        )
    return duration_ms, channels, sample_width, sample_rate


def _build_manifest(
    payload: Mapping[str, Any],
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    payload_digest: str,
    duration_ms: int,
    timings: list[dict[str, Any]],
    alignment: Mapping[str, Any],
    request_id: str | None,
    character_cost: int | None,
    stage_directory: Path,
) -> bytes:
    files: dict[str, dict[str, Any]] = {}
    for spec in _FILE_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = stage_directory / spec["filename"]
        if not _safe_file(path):
            raise ExternalTTSMediaError(
                "The external TTS artifact is unavailable.", code="publish_failed"
            )
        stat = path.stat()
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    segments = [
        {
            "index": row["index"],
            "text": row["text"],
            "text_sha256": _sha256_bytes(row["text"].encode("utf-8")),
            "start_ms": row["start_ms"],
            "end_ms": row["end_ms"],
            "duration_ms": row["duration_ms"],
            "character_start_index": row["character_start_index"],
            "character_end_index": row["character_end_index"],
            "character_count": row["character_count"],
        }
        for row in timings
    ]
    body: dict[str, Any] = {
        "schema_version": EXTERNAL_TTS_SCHEMA_VERSION,
        "implementation_version": EXTERNAL_TTS_IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "payload_digest": payload_digest,
        "provider": EXTERNAL_TTS_PROVIDER,
        "provider_task_id": request_id,
        "request_id": request_id,
        "provider_request_id": request_id,
        "character_cost": character_cost,
        "actual_cost": None,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "voice_id": payload["voice_id"],
        "model_id": EXTERNAL_TTS_MODEL,
        "output_format": EXTERNAL_TTS_OUTPUT_FORMAT,
        "voice_settings": dict(payload["voice_settings"]),
        "seed": payload["seed"],
        "request_text": {
            "segment_count": len(payload["segments"]),
            "text_chars": len(external_tts_request_text(payload)),
            "segment_text_sha256": [
                _sha256_bytes(item["text"].encode("utf-8"))
                for item in payload["segments"]
            ],
        },
        "duration_ms": duration_ms,
        "segments": segments,
        "alignment": dict(alignment),
        "files": files,
    }
    manifest = dict(body)
    manifest["manifest_sha256"] = _manifest_digest(body)
    encoded = (canonical_json(manifest) + "\n").encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ExternalTTSMediaError("The external TTS manifest is too large.", code="metadata_too_large")
    return encoded


def _validate_cached_manifest(
    workspace: Path,
    cache_directory: Path,
    manifest: Any,
    *,
    payload: Mapping[str, Any],
    production_id: str,
    run_id: str,
    cache_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not isinstance(manifest, dict):
        return None
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str) or _manifest_digest(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    ) != digest.upper():
        return None
    if (
        manifest.get("schema_version") != EXTERNAL_TTS_SCHEMA_VERSION
        or manifest.get("implementation_version") != EXTERNAL_TTS_IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("cache_key") != cache_key
        or manifest.get("payload_digest") != external_tts_payload_digest(payload)
        or manifest.get("provider") != EXTERNAL_TTS_PROVIDER
        or manifest.get("provider_task_id") != manifest.get("request_id")
        or manifest.get("actual_cost") is not None
        or manifest.get("timing_source") != EXTERNAL_TTS_TIMING_SOURCE
        or manifest.get("voice_id") != payload["voice_id"]
        or manifest.get("model_id") != EXTERNAL_TTS_MODEL
        or manifest.get("output_format") != EXTERNAL_TTS_OUTPUT_FORMAT
        or manifest.get("voice_settings") != payload["voice_settings"]
        or manifest.get("seed") != payload["seed"]
    ):
        return None
    request_id = manifest.get("request_id")
    provider_request_id = manifest.get("provider_request_id")
    provider_task_id = manifest.get("provider_task_id")
    if (
        request_id is not None
        and (
            not isinstance(request_id, str)
            or len(request_id) > 256
            or any(character in _CONTROL_CHARS for character in request_id)
        )
    ):
        return None
    if provider_request_id != request_id or provider_task_id != request_id:
        return None
    character_cost = manifest.get("character_cost")
    if (
        character_cost is not None
        and (
            isinstance(character_cost, bool)
            or not isinstance(character_cost, int)
            or character_cost < 0
        )
    ):
        return None
    files = manifest.get("files")
    expected = {spec["filename"] for spec in _FILE_SPECS if spec["filename"] != "manifest.json"}
    if not isinstance(files, dict) or set(files) != expected:
        return None
    for spec in _FILE_SPECS:
        filename = spec["filename"]
        if filename == "manifest.json":
            continue
        path = cache_directory / filename
        entry = files.get(filename)
        if not isinstance(entry, dict) or not _safe_file(path):
            return None
        if (
            entry.get("path") != filename
            or entry.get("kind") != spec["kind"]
            or entry.get("mime") != spec["mime"]
            or isinstance(entry.get("bytes"), bool)
            or not isinstance(entry.get("bytes"), int)
            or entry.get("bytes") < 0
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
            or path.stat().st_size != entry["bytes"]
            or _sha256_file(path) != entry["sha256"].upper()
        ):
            return None
    segments = manifest.get("segments")
    if not isinstance(segments, list) or len(segments) != len(payload["segments"]):
        return None
    for index, row in enumerate(segments):
        if not isinstance(row, dict):
            return None
        expected_text = payload["segments"][index]["text"]
        required_fields = {
            "index",
            "text",
            "text_sha256",
            "start_ms",
            "end_ms",
            "duration_ms",
            "character_start_index",
            "character_end_index",
            "character_count",
        }
        if set(row) != required_fields:
            return None
        if (
            row.get("index") != index
            or row.get("text") != expected_text
            or row.get("text_sha256") != _sha256_bytes(expected_text.encode("utf-8"))
            or not isinstance(row.get("start_ms"), int)
            or not isinstance(row.get("end_ms"), int)
            or not isinstance(row.get("duration_ms"), int)
            or not isinstance(row.get("character_start_index"), int)
            or not isinstance(row.get("character_end_index"), int)
            or not isinstance(row.get("character_count"), int)
            or row.get("character_count") != len(expected_text)
            or row.get("character_end_index") - row.get("character_start_index")
            != len(expected_text)
        ):
            return None
    duration_ms = manifest.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms <= 0 or duration_ms > MAX_DURATION_MS:
        return None
    for index, row in enumerate(segments):
        if (
            row.get("index") != index
            or row["start_ms"] < 0
            or row["end_ms"] <= row["start_ms"]
            or row["end_ms"] > duration_ms
            or row["duration_ms"] != row["end_ms"] - row["start_ms"]
        ):
            return None
    try:
        artifacts = [_artifact_record(workspace, cache_directory, spec) for spec in _FILE_SPECS]
    except (OSError, ValueError, ExternalTTSError):
        return None
    return manifest, artifacts


def _load_valid_cache(
    workspace: Path,
    cache_directory: Path,
    *,
    payload: Mapping[str, Any],
    production_id: str,
    run_id: str,
    cache_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    manifest_path = cache_directory / "manifest.json"
    if (
        not cache_directory.is_dir()
        or cache_directory.is_symlink()
        or not _safe_file(manifest_path)
        or manifest_path.stat().st_size > MAX_METADATA_BYTES
    ):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return _validate_cached_manifest(
        workspace,
        cache_directory,
        manifest,
        payload=payload,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
    )


def _publish(stage_directory: Path, cache_directory: Path) -> None:
    if cache_directory.exists() and cache_directory.is_symlink():
        raise ExternalTTSError("The external TTS output path is unsafe.", code="unsafe_output_path")
    _ensure_directory(cache_directory)
    for spec in _FILE_SPECS:
        filename = spec["filename"]
        source = stage_directory / filename
        if not _safe_file(source):
            raise ExternalTTSError("The external TTS artifact is unavailable.", code="publish_failed")
        # Manifest is last: a reader seeing a partial publish can never pass
        # cache validation because the self-hash/file set is incomplete.
        if filename != "manifest.json":
            os.replace(source, cache_directory / filename)
    os.replace(stage_directory / "manifest.json", cache_directory / "manifest.json")


def _result(
    manifest: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    request_id = manifest.get("request_id")
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "provider": EXTERNAL_TTS_PROVIDER,
        "provider_task_id": request_id,
        "request_id": request_id,
        "provider_request_id": manifest.get("provider_request_id", request_id),
        "character_cost": manifest.get("character_cost"),
        "actual_cost": None,
        "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
        "cost": {
            "amount": None,
            "currency": "USD",
            "source": "provider_unreported",
        },
        "voice_id": manifest["voice_id"],
        "model_id": manifest["model_id"],
        "output_format": manifest["output_format"],
    }


def generate_external_tts(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    payload: Mapping[str, Any],
    api_key: str | None = None,
    ffmpeg: str | Path | None = None,
    cancel_event: Any | None = None,
    base_url: str = PRODUCTION_BASE_URL,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Generate external narration artifacts with one synchronous POST.

    ``base_url`` and ``opener`` are dependency-injection seams for tests.  Any
    non-production URL is accepted only when it resolves to loopback.  A cache
    hit is returned before credential validation, so a valid immutable result
    can be reused without touching a provider credential.
    """

    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    normalized = validate_external_tts_payload(dict(payload))
    cache_key = external_tts_cache_key(normalized)
    payload_digest = external_tts_payload_digest(normalized)
    workspace = workspace.resolve(strict=True)
    base_url = _validate_base_url(base_url)
    if opener is not None and urllib.parse.urlsplit(base_url).hostname not in {
        "127.0.0.1",
        "::1",
    }:
        raise ExternalTTSError(
            "Injected external transport is permitted only for loopback tests.",
            code="invalid_external_endpoint",
        )
    root = _narration_root(workspace, run_id)
    _ensure_directory(root)
    cache_directory = _cache_directory(workspace, run_id, cache_key)
    if cache_directory.exists() and not cache_directory.is_dir() and not cache_directory.is_symlink():
        raise ExternalTTSError("The external TTS cache path is unsafe.", code="unsafe_output_path")
    _raise_if_cancelled(cancel_event)
    cached = _load_valid_cache(
        workspace,
        cache_directory,
        payload=normalized,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
    )
    submission_marker = _submission_marker_path(workspace, production_id, cache_key)
    if cached is not None:
        manifest, artifacts = cached
        # A crash can happen after the final artifact publish but before marker
        # cleanup.  The byte-verified complete cache is safe to return; clear
        # only this identity's stale marker before doing so.
        _remove_submission_marker(submission_marker)
        return _result(manifest, artifacts, cache_hit=True)

    if _marker_exists(submission_marker):
        raise ExternalTTSSubmissionUnknown()
    key = _validate_api_key(api_key)
    _create_submission_marker(
        workspace,
        production_id,
        cache_key,
        payload_digest,
    )
    stage_directory = Path(tempfile.mkdtemp(prefix=f".{cache_key}.", dir=str(root)))
    completed_cache: tuple[dict[str, Any], list[dict[str, Any]]] | None = None
    try:
        _raise_if_cancelled(cancel_event)
        response, mp3_bytes, request_id, character_cost = _provider_request(
            base_url,
            key,
            normalized,
            timeout=REQUEST_TIMEOUT_SECONDS,
            cancel_event=cancel_event,
            opener=opener,
        )
        # Do not retain the API key longer than the adapter call needs to; this
        # is best-effort memory hygiene and does not affect the request object.
        key = ""
        _raise_if_cancelled(cancel_event)
        _atomic_write(stage_directory / ".provider-audio.mp3", mp3_bytes, maximum=MAX_MP3_BYTES)
        rows, alignment_duration_ms, alignment = _alignment_document(normalized, response)
        wav_source = _convert_mp3_to_wav(stage_directory, ffmpeg=ffmpeg, cancel_event=cancel_event)
        duration_ms, channels, sample_width, sample_rate = _validate_pcm_wav(wav_source)
        if alignment_duration_ms > duration_ms + 100:
            raise ExternalTTSMediaError(
                "The external TTS alignment exceeds the generated audio duration.",
                code="invalid_external_alignment",
            )
        # Clamp only a small provider rounding tail, preserving alignment as
        # the source of segment timing while ensuring captions fit the WAV.
        for row in rows:
            row["start_ms"] = min(row["start_ms"], duration_ms)
            row["end_ms"] = min(row["end_ms"], duration_ms)
            if row["end_ms"] <= row["start_ms"]:
                row["end_ms"] = min(duration_ms, row["start_ms"] + 1)
            if row["end_ms"] <= row["start_ms"]:
                raise ExternalTTSMediaError(
                    "The external TTS alignment does not fit the generated audio.",
                    code="invalid_external_alignment",
                )
            row["duration_ms"] = row["end_ms"] - row["start_ms"]
        _atomic_write(stage_directory / "narration.wav", wav_source.read_bytes(), maximum=MAX_WAV_BYTES)
        _atomic_write(stage_directory / "captions.srt", _build_captions(rows), maximum=MAX_METADATA_BYTES)
        timings_document = {
            "schema_version": EXTERNAL_TTS_SCHEMA_VERSION,
            "implementation_version": EXTERNAL_TTS_IMPLEMENTATION_VERSION,
            "provider": EXTERNAL_TTS_PROVIDER,
            "timing_source": EXTERNAL_TTS_TIMING_SOURCE,
            "duration_ms": duration_ms,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
            "segments": rows,
            "alignment": alignment,
        }
        _atomic_write(
            stage_directory / "timings.json",
            (canonical_json(timings_document) + "\n").encode("utf-8"),
            maximum=MAX_METADATA_BYTES,
        )
        _atomic_write(
            stage_directory / "manifest.json",
            _build_manifest(
                normalized,
                production_id=production_id,
                run_id=run_id,
                cache_key=cache_key,
                payload_digest=payload_digest,
                duration_ms=duration_ms,
                timings=rows,
                alignment=alignment,
                request_id=request_id,
                character_cost=character_cost,
                stage_directory=stage_directory,
            ),
            maximum=MAX_METADATA_BYTES,
        )
        _raise_if_cancelled(cancel_event)
        _publish(stage_directory, cache_directory)
        completed_cache = _load_valid_cache(
            workspace,
            cache_directory,
            payload=normalized,
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
        )
        if completed_cache is None:
            raise ExternalTTSError(
                "The external TTS cache failed integrity verification.",
                code="cache_integrity_failed",
            )
        # This is intentionally the last state transition.  If the process
        # dies before this unlink, the next run fails closed on the marker even
        # if a later artifact step happened to be partially visible.
        _remove_submission_marker(submission_marker)
    except ExternalTTSError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise ExternalTTSError(
            "The external TTS artifact publication failed.", code="publish_failed"
        ) from exc
    finally:
        # The transient MP3 and conversion output never become Studio
        # artifacts.  ``ignore_errors`` is safe because this directory is
        # freshly created below the workspace run root.
        shutil.rmtree(stage_directory, ignore_errors=True)

    if completed_cache is None:  # pragma: no cover - guarded in the try block
        raise ExternalTTSError(
            "The external TTS cache failed integrity verification.",
            code="cache_integrity_failed",
        )
    manifest, artifacts = completed_cache
    return _result(manifest, artifacts, cache_hit=False)


class ElevenLabsAdapter:
    """Small injectable adapter facade for callers that prefer an object.

    The credential is held only by this in-memory object and is never included
    in ``repr`` or delegated to the public payload.  ``base_url`` is retained
    as a test seam and is subject to the same production/loopback validation as
    the functional API.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = PRODUCTION_BASE_URL,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = _validate_api_key(api_key)
        self._base_url = _validate_base_url(base_url)
        self._opener = opener

    def __repr__(self) -> str:
        return f"{type(self).__name__}(api_key='[REDACTED]', base_url={self._base_url!r})"

    def synthesize(
        self,
        workspace: Path,
        *,
        production_id: str,
        run_id: str,
        payload: Mapping[str, Any],
        ffmpeg: str | Path | None = None,
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        return generate_external_tts(
            workspace,
            production_id=production_id,
            run_id=run_id,
            payload=payload,
            api_key=self._api_key,
            ffmpeg=ffmpeg,
            cancel_event=cancel_event,
            base_url=self._base_url,
            opener=self._opener,
        )


# Names used by callers that model the stage as narration rather than TTS.
generate_external_narration = generate_external_tts
generate_elevenlabs_narration = generate_external_tts
synthesize_elevenlabs = generate_external_tts
ElevenLabsTTSAdapter = ElevenLabsAdapter


__all__ = [
    "ENDPOINT_PATH",
    "EXTERNAL_TTS_IMPLEMENTATION_VERSION",
    "ElevenLabsAdapter",
    "ElevenLabsTTSAdapter",
    "ExternalTTSMediaError",
    "ExternalTTSProviderError",
    "ExternalTTSSubmissionUnknown",
    "ExternalTTSError",
    "ExternalTTSValidationError",
    "PRODUCTION_BASE_URL",
    "REQUEST_TIMEOUT_SECONDS",
    "generate_elevenlabs_narration",
    "generate_external_narration",
    "generate_external_tts",
    "synthesize_elevenlabs",
    "external_tts_public_result",
    "validate_external_tts_payload",
]
