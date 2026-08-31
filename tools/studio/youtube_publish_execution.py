from __future__ import annotations

"""Recoverable execution of one explicitly confirmed YouTube upload."""

import hashlib
import os
import stat as stat_module
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping

from .security import workspace_path
from .youtube_publish import (
    YouTubeHttpResponse,
    YouTubePublishError,
    YouTubeResumableTransport,
    validate_youtube_channel,
    validate_youtube_completion,
    youtube_confirmation_summary,
)
from .youtube_publish_state import YouTubePublishLedger


_DEFINITE_SESSION_BEGIN_FAILURES = frozenset(
    {
        "invalid_youtube_upload_session",
        "youtube_upload_session_failed",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _open_protected_source(path: Path) -> BinaryIO:
    """Open one upload source without ever reopening it for transport.

    Windows uses a native handle that shares reads only.  While this handle is
    live, another opener cannot obtain write/delete access and the pathname
    cannot be replaced.  Other platforms retain one descriptor for both hash
    verification and upload; pathname replacement therefore cannot redirect
    the bytes consumed by the transport.
    """

    if os.name != "nt":
        return path.open("rb")

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_attribute_normal = 0x00000080
    file_flag_sequential_scan = 0x08000000
    raw_handle = create_file(
        str(path),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_attribute_normal | file_flag_sequential_scan,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if raw_handle in {None, invalid_handle}:
        error = ctypes.get_last_error()
        raise OSError(error, "The protected upload source could not be opened")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    try:
        descriptor = msvcrt.open_osfhandle(int(raw_handle), flags)
    except Exception:
        close_handle(raw_handle)
        raise
    try:
        return os.fdopen(descriptor, "rb", buffering=0)
    except Exception:
        os.close(descriptor)
        raise


def _verify_open_source(
    handle: BinaryIO,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> os.stat_result:
    try:
        stat = os.fstat(handle.fileno())
        if not stat_module.S_ISREG(stat.st_mode) or stat.st_size != expected_bytes:
            raise OSError("source size changed")
        handle.seek(0)
        digest = hashlib.sha256()
        byte_count = 0
        while chunk := handle.read(1024 * 1024):
            byte_count += len(chunk)
            if byte_count > expected_bytes:
                raise OSError("source grew")
            digest.update(chunk)
        if (
            byte_count != expected_bytes
            or digest.hexdigest().upper() != expected_sha256.upper()
        ):
            raise OSError("source digest changed")
        handle.seek(0)
        return stat
    except (AttributeError, OSError, ValueError) as exc:
        raise YouTubePublishError(
            "The verified YouTube source video changed.",
            code="youtube_source_changed",
        ) from exc


@contextmanager
def _protected_verified_source(
    path: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    try:
        handle = _open_protected_source(path)
    except (OSError, RuntimeError) as exc:
        raise YouTubePublishError(
            "The verified YouTube source video is unavailable.",
            code="youtube_source_changed",
        ) from exc
    try:
        identity = _verify_open_source(
            handle,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
        )
        yield handle, identity
    finally:
        handle.close()


def _unlink_same_source(path: Path, identity: os.stat_result) -> None:
    """Delete only the pathname that still identifies the uploaded handle."""

    try:
        current = path.stat()
        if os.path.samestat(identity, current):
            path.unlink(missing_ok=True)
    except OSError:
        return


def _raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is None:
        return
    method = getattr(cancel_event, "raise_if_cancelled", None)
    if callable(method):
        method()


def _public_result(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "publish_id": state["publish_id"],
        "production_id": state["production_id"],
        "status": state["status"],
        "delivery_artifact_id": state["delivery_artifact_id"],
        "delivery_sha256": state["delivery_sha256"],
        "video_artifact_id": state["video_artifact_id"],
        "video_sha256": state["video_sha256"],
        "video_bytes": state["video_bytes"],
        "channel": {
            "id": state["channel_id"],
            "title": state["channel_title"],
        },
        "privacy_status": state["privacy_status"],
        "acknowledged_bytes": state["acknowledged_bytes"],
        "attempt_count": state["attempt_count"],
        "video_id": state["video_id"],
        "video_url": state["video_url"],
        "error_code": state["error_code"],
        "updated_at": state["updated_at"],
        "public_upload_supported": False,
    }


def _stage_verified_source(
    ledger: YouTubePublishLedger,
    publish_id: str,
    source: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> Path:
    try:
        resolved = source.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise OSError("not a regular file")
        if resolved.stat().st_size != expected_bytes or _sha256_file(resolved) != expected_sha256:
            raise OSError("source changed")
    except (OSError, RuntimeError) as exc:
        raise YouTubePublishError(
            "The verified YouTube source video is unavailable.",
            code="youtube_source_changed",
        ) from exc
    directory = workspace_path(ledger.workspace, ledger.root / publish_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = workspace_path(ledger.workspace, directory / "source.mp4")
    if destination.is_file():
        try:
            if (
                not destination.is_symlink()
                and destination.stat().st_size == expected_bytes
                and _sha256_file(destination) == expected_sha256
            ):
                return destination
        except OSError:
            pass
        raise YouTubePublishError(
            "The staged YouTube source video does not match its confirmation.",
            code="youtube_source_changed",
        )
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        digest = hashlib.sha256()
        written = 0
        try:
            with resolved.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    temporary.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    if written != expected_bytes or digest.hexdigest().upper() != expected_sha256:
        temporary_path.unlink(missing_ok=True)
        raise YouTubePublishError(
            "The staged YouTube source video does not match its confirmation.",
            code="youtube_source_changed",
        )
    os.replace(temporary_path, destination)
    if destination.stat().st_size != expected_bytes or _sha256_file(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise YouTubePublishError(
            "The staged YouTube source video does not match its confirmation.",
            code="youtube_source_changed",
        )
    return destination


def _complete(
    ledger: YouTubePublishLedger,
    state: Mapping[str, Any],
    response: YouTubeHttpResponse,
    source_handle: BinaryIO,
) -> dict[str, Any]:
    completed = validate_youtube_completion(
        response,
        expected_channel_id=str(state["channel_id"]),
        expected_privacy_status=str(state["privacy_status"]),
    )
    try:
        _verify_open_source(
            source_handle,
            expected_bytes=int(state["video_bytes"]),
            expected_sha256=str(state["video_sha256"]),
        )
    except YouTubePublishError:
        ledger.transition(
            str(state["publish_id"]),
            "recovery_blocked",
            error_code="youtube_source_changed",
        )
        raise
    succeeded = ledger.transition(
        str(state["publish_id"]),
        "succeeded",
        acknowledged_bytes=int(state["video_bytes"]),
        video_id=completed["video_id"],
        video_url=completed["url"],
    )
    return _public_result(succeeded)


def _execute_with_bound_source(
    *,
    state: Mapping[str, Any],
    confirmation_summary: Mapping[str, Any],
    source_handle: BinaryIO,
    transport: YouTubeResumableTransport,
    ledger: YouTubePublishLedger,
    cancel_event: Any | None,
) -> dict[str, Any]:
    publish_id = str(state["publish_id"])
    _raise_if_cancelled(cancel_event)
    token = transport.access_token()
    channel = validate_youtube_channel(transport.channel(token))
    if channel != {"id": state["channel_id"], "title": state["channel_title"]}:
        raise YouTubePublishError(
            "The authenticated YouTube channel changed after confirmation.",
            code="youtube_channel_changed",
        )

    session_url = ledger.session(publish_id)
    if state["status"] == "prepared":
        if session_url is not None:
            raise YouTubePublishError(
                "The YouTube upload ledger is inconsistent.",
                code="youtube_publish_state_invalid",
            )
        try:
            session_url = transport.begin(
                token,
                confirmation_summary["request"],
                video_bytes=int(state["video_bytes"]),
            )
        except YouTubePublishError as exc:
            next_status = (
                "recovery_blocked"
                if exc.code in _DEFINITE_SESSION_BEGIN_FAILURES
                else "ambiguous"
            )
            ledger.transition(publish_id, next_status, error_code=exc.code)
            raise
        try:
            state = ledger.store_session(publish_id, session_url)
        except YouTubePublishError as exc:
            ledger.transition(publish_id, "ambiguous", error_code=exc.code)
            raise YouTubePublishError(
                "The YouTube upload session could not be retained safely.",
                code="youtube_upload_ambiguous",
            ) from exc
    elif session_url is None:
        # A response-loss state without its signed session URL cannot safely
        # determine whether a new initialization would duplicate work.
        raise YouTubePublishError(
            "The YouTube upload session is unknown; automatic retry is blocked.",
            code="youtube_upload_ambiguous",
        )

    assert session_url is not None
    _raise_if_cancelled(cancel_event)
    query = transport.query(token, session_url, video_bytes=int(state["video_bytes"]))
    if query.status in {200, 201}:
        return _complete(ledger, state, query, source_handle)
    if query.status == 404:
        ledger.transition(
            publish_id, "recovery_blocked", error_code="youtube_upload_session_expired"
        )
        raise YouTubePublishError(
            "The YouTube upload session expired; automatic re-initiation is blocked.",
            code="youtube_upload_session_expired",
        )
    if query.status != 308:
        ledger.transition(publish_id, "ambiguous", error_code="youtube_upload_status_unknown")
        raise YouTubePublishError(
            "The YouTube upload status is unknown.", code="youtube_upload_ambiguous"
        )
    acknowledged = transport.acknowledged_bytes(query)
    if acknowledged >= int(state["video_bytes"]):
        ledger.transition(publish_id, "ambiguous", error_code="youtube_upload_status_unknown")
        raise YouTubePublishError(
            "The YouTube upload completion response is unavailable.",
            code="youtube_upload_ambiguous",
        )
    state = ledger.transition(
        publish_id,
        "uploading",
        acknowledged_bytes=acknowledged,
        increment_attempt=True,
    )

    def progress(sent: int, _total: int) -> None:
        _raise_if_cancelled(cancel_event)

    try:
        response = transport.upload(
            token,
            session_url,
            source_handle,
            expected_bytes=int(state["video_bytes"]),
            expected_sha256=str(state["video_sha256"]),
            start_byte=acknowledged,
            progress=progress,
        )
    except YouTubePublishError as exc:
        ledger.transition(publish_id, "ambiguous", error_code=exc.code)
        raise
    if response.status in {200, 201}:
        return _complete(ledger, state, response, source_handle)
    if response.status == 308:
        received = transport.acknowledged_bytes(response)
        ledger.transition(
            publish_id,
            "uploading",
            acknowledged_bytes=max(acknowledged, received),
            error_code="youtube_upload_incomplete",
        )
        raise YouTubePublishError(
            "The YouTube upload is incomplete and can be resumed.",
            code="youtube_upload_incomplete",
        )
    ledger.transition(publish_id, "ambiguous", error_code="youtube_upload_status_unknown")
    raise YouTubePublishError(
        "The YouTube upload completion is unknown.", code="youtube_upload_ambiguous"
    )


def execute_youtube_publish(
    *,
    production_id: str,
    confirmation_summary: Mapping[str, Any],
    video_path: Path,
    transport: YouTubeResumableTransport,
    ledger: YouTubePublishLedger,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Execute or resume exactly one confirmed private/unlisted upload.

    A state with no protected session is never re-initiated after ambiguity.
    A state with a protected session first queries the provider and resumes
    from the acknowledged byte, avoiding a second ``videos.insert`` session.
    """

    state = ledger.prepare(production_id, confirmation_summary)
    publish_id = str(state["publish_id"])
    if state["status"] == "succeeded":
        return _public_result(state)
    if state["status"] == "recovery_blocked":
        raise YouTubePublishError(
            "The YouTube upload requires operator recovery.",
            code="youtube_publish_recovery_blocked",
        )
    staging = _stage_verified_source(
        ledger,
        publish_id,
        video_path,
        expected_bytes=int(state["video_bytes"]),
        expected_sha256=str(state["video_sha256"]),
    )
    cleanup_identity: os.stat_result | None = None
    try:
        with _protected_verified_source(
            staging,
            expected_bytes=int(state["video_bytes"]),
            expected_sha256=str(state["video_sha256"]),
        ) as (source_handle, identity):
            result = _execute_with_bound_source(
                state=state,
                confirmation_summary=confirmation_summary,
                source_handle=source_handle,
                transport=transport,
                ledger=ledger,
                cancel_event=cancel_event,
            )
            if result.get("status") == "succeeded":
                cleanup_identity = identity
            return result
    finally:
        if cleanup_identity is not None:
            _unlink_same_source(staging, cleanup_identity)


def verified_confirmation_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild and verify a summary supplied by a service boundary."""

    try:
        rebuilt = youtube_confirmation_summary(
            value["request"],
            value["channel"],
            delivery_sha256=str(value["delivery_sha256"]),
            video_sha256=str(value["video_sha256"]),
            video_bytes=int(value["video_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise YouTubePublishError(
            "The YouTube confirmation summary is invalid.",
            code="youtube_confirmation_invalid",
        ) from exc
    if rebuilt != dict(value):
        raise YouTubePublishError(
            "The YouTube confirmation summary is invalid.",
            code="youtube_confirmation_invalid",
        )
    return rebuilt


__all__ = ["execute_youtube_publish", "verified_confirmation_summary"]
