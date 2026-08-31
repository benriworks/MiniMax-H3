from __future__ import annotations

"""Closed, local-only production creation and video import primitives."""

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable
from urllib.parse import quote_from_bytes, unquote_to_bytes

from .security import (
    SecurityError,
    canonical_json,
    relative_workspace_path,
    stable_id,
    workspace_path,
)


PRODUCTION_SCHEMA_VERSION = 1
PRODUCTION_ID_RE = re.compile(r"^production_[0-9a-f]{32}$")
PRODUCTION_METADATA_FILENAME = ".studio-production.json"
PRODUCTION_METADATA_MAX_BYTES = 64 * 1024
PRODUCTION_TITLE_MAX_CHARS = 120

VIDEO_IMPORT_FILENAME_HEADER = "X-Studio-Filename-Encoded"
MAX_VIDEO_IMPORT_BYTES = 2 * 1024 * 1024 * 1024
MAX_VIDEO_IMPORT_FILENAME_BYTES = 512
VIDEO_IMPORTS_DIRNAME = "imports"
VIDEO_IMPORT_PARTIALS_DIRNAME = ".studio-video-import-partials"
VIDEO_IMPORT_SHA_PREFIX_LENGTH = 16
VIDEO_IMPORT_PARTIAL_NAME_RE = re.compile(r"^[0-9a-f]{32}\.part$")
_METADATA_PARTIAL_RE = re.compile(r"^\.studio-production\.[0-9a-f]{32}\.partial$")
_SHA_RE = re.compile(r"^[0-9A-F]{64}$")
_SHA_PREFIX_RE = re.compile(r"^[0-9a-f]{16}_.+$")

_VIDEO_MIME_TYPES: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"video/mp4", "application/mp4"}),
    ".m4v": frozenset({"video/mp4", "video/x-m4v"}),
    ".mov": frozenset({"video/quicktime", "video/mp4"}),
    ".mkv": frozenset({"video/x-matroska", "video/matroska"}),
    ".webm": frozenset({"video/webm"}),
    ".avi": frozenset({"video/x-msvideo", "video/avi"}),
}
_CANONICAL_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
}
_VIDEO_CONTAINERS: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"mp4", "m4v", "mov"}),
    ".m4v": frozenset({"mp4", "m4v", "mov"}),
    ".mov": frozenset({"mov", "mp4"}),
    ".mkv": frozenset({"matroska", "webm"}),
    ".webm": frozenset({"matroska", "webm"}),
    ".avi": frozenset({"avi"}),
}
_CONTROL_CHARACTERS = frozenset(chr(value) for value in range(32)) | {chr(127)}
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)


class ProductionIntakeError(ValueError):
    """A bounded, public-safe intake failure."""

    def __init__(self, message: str, *, code: str = "invalid_production_intake"):
        super().__init__(message)
        self.code = code


class ProductionConflictError(ProductionIntakeError):
    def __init__(self, message: str = "the production identity is already in use"):
        super().__init__(message, code="production_id_conflict")


@dataclass(frozen=True)
class VideoImportResult:
    artifact: dict[str, Any]
    deduplicated: bool
    destination_created: bool


def _error(message: str, code: str) -> ProductionIntakeError:
    return ProductionIntakeError(message, code=code)


def validate_production_id(value: Any) -> str:
    if not isinstance(value, str) or PRODUCTION_ID_RE.fullmatch(value) is None:
        raise _error(
            "production_id must match production_ followed by 32 lowercase hexadecimal characters",
            "invalid_production_id",
        )
    return value


def _bounded_title(value: Any) -> str:
    if not isinstance(value, str):
        raise _error("title must be a string", "invalid_production_title")
    if value != value.strip() or not value or len(value) > PRODUCTION_TITLE_MAX_CHARS:
        raise _error("title is empty, padded, or too long", "invalid_production_title")
    if any(character in _CONTROL_CHARACTERS for character in value):
        raise _error("title contains control characters", "invalid_production_title")
    return value


def validate_production_create_payload(value: Any) -> dict[str, Any]:
    required = {"schema_version", "production_id", "title"}
    if not isinstance(value, dict) or set(value) != required:
        raise _error(
            "production creation requires exactly schema_version, production_id, and title",
            "invalid_production_create_request",
        )
    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1:
        raise _error(
            "production creation schema_version is not supported",
            "unsupported_production_schema",
        )
    return {
        "schema_version": PRODUCTION_SCHEMA_VERSION,
        "production_id": validate_production_id(value["production_id"]),
        "title": _bounded_title(value["title"]),
    }


def _has_symlink_component(workspace: Path, candidate: Path) -> bool:
    root = workspace.resolve(strict=True)
    lexical = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _directory(workspace: Path, relative: str, *, create: bool, code: str) -> Path | None:
    root = workspace.resolve(strict=True)
    lexical = root / Path(relative)
    if _has_symlink_component(root, lexical):
        raise _error("the controlled intake path contains a symlink", code)
    try:
        path = workspace_path(root, lexical, must_exist=False)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise _error("the controlled intake path is invalid", code) from exc
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise _error("the controlled intake path is not a directory", code)
        return path
    if not create:
        return None
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _error("the controlled intake directory could not be created", code) from exc
    if _has_symlink_component(root, path) or path.is_symlink() or not path.is_dir():
        raise _error("the controlled intake directory changed unsafely", code)
    return path


def _output_root(workspace: Path, *, create: bool) -> Path | None:
    return _directory(
        workspace,
        "outputs/productions",
        create=create,
        code="unsafe_production_path",
    )


def _production_directory(workspace: Path, production_id: str, *, create: bool) -> Path | None:
    validate_production_id(production_id)
    return _directory(
        workspace,
        f"outputs/productions/{production_id}",
        create=create,
        code="unsafe_production_path",
    )


def _control_path(workspace: Path, production_id: str, *, create_parent: bool) -> Path | None:
    directory = _production_directory(workspace, production_id, create=create_parent)
    if directory is None:
        return None
    path = directory / PRODUCTION_METADATA_FILENAME
    if path.is_symlink():
        raise _error("production metadata must not be a symlink", "unsafe_production_metadata")
    return path


def _valid_import_relative(value: str) -> bool:
    path = PurePosixPath(value)
    name = path.name
    return bool(
        value == path.as_posix()
        and len(path.parts) == 2
        and path.parts[0] == VIDEO_IMPORTS_DIRNAME
        and _SHA_PREFIX_RE.fullmatch(name)
        and path.suffix.casefold() in _VIDEO_MIME_TYPES
        and len(name.encode("utf-8")) <= 255
        and not any(character in name for character in '<>:"/\\|?*')
        and name.rstrip(" .") == name
        and not any(character in _CONTROL_CHARACTERS for character in value)
    )


def validate_production_metadata(value: Any, *, production_id: str) -> dict[str, Any]:
    required = {"schema_version", "production_id", "title", "imports"}
    if not isinstance(value, dict) or set(value) != required:
        raise _error("production metadata is not a supported document", "invalid_production_metadata")
    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1:
        raise _error("production metadata schema_version is not supported", "unsupported_production_schema")
    if value["production_id"] != production_id:
        raise _error("production metadata identity does not match its directory", "invalid_production_metadata")
    imports = value["imports"]
    if not isinstance(imports, dict) or len(imports) > 1024:
        raise _error("production import hashes are invalid", "invalid_production_metadata")
    normalized_imports: dict[str, str] = {}
    seen_hashes: set[str] = set()
    for relative, digest in imports.items():
        if (
            not isinstance(relative, str)
            or not _valid_import_relative(relative)
            or not isinstance(digest, str)
            or _SHA_RE.fullmatch(digest) is None
            or digest in seen_hashes
        ):
            raise _error("production import hashes are invalid", "invalid_production_metadata")
        normalized_imports[relative] = digest
        seen_hashes.add(digest)
    return {
        "schema_version": PRODUCTION_SCHEMA_VERSION,
        "production_id": production_id,
        "title": _bounded_title(value["title"]),
        "imports": dict(sorted(normalized_imports.items())),
    }


def read_production_metadata(workspace: Path, production_id: str) -> dict[str, Any] | None:
    validate_production_id(production_id)
    path = _control_path(workspace, production_id, create_parent=False)
    if path is None or not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise _error("production metadata is not a regular file", "unsafe_production_metadata")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("production metadata could not be read", "invalid_production_metadata") from exc
    if not 1 <= len(raw) <= PRODUCTION_METADATA_MAX_BYTES:
        raise _error("production metadata is too large", "invalid_production_metadata")
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate production metadata key")
            result[key] = item
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite production metadata value")

    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _error("production metadata is not valid UTF-8 JSON", "invalid_production_metadata") from exc
    return validate_production_metadata(parsed, production_id=production_id)


def _replace_metadata(workspace: Path, production_id: str, metadata: dict[str, Any]) -> None:
    normalized = validate_production_metadata(metadata, production_id=production_id)
    path = _control_path(workspace, production_id, create_parent=True)
    assert path is not None
    partial = path.with_name(f".studio-production.{uuid.uuid4().hex}.partial")
    encoded = (canonical_json(normalized) + "\n").encode("utf-8")
    if len(encoded) > PRODUCTION_METADATA_MAX_BYTES:
        raise _error("production metadata is too large", "production_metadata_write_failed")
    try:
        with partial.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if _has_symlink_component(workspace, partial):
            raise OSError("metadata partial path changed")
        os.replace(partial, path)
    except OSError as exc:
        try:
            if partial.exists() and not partial.is_symlink():
                partial.unlink()
        except OSError:
            pass
        raise _error("production metadata could not be written", "production_metadata_write_failed") from exc


def create_production_files(
    workspace: Path, request: dict[str, Any]
) -> tuple[dict[str, Any], bool, bool]:
    """Return ``(metadata, deduplicated, created_by_this_call)``."""

    normalized = validate_production_create_payload(request)
    production_id = normalized["production_id"]
    root = workspace.resolve(strict=True)
    source = root / "productions" / production_id
    if _has_symlink_component(root, source) or source.exists():
        raise ProductionConflictError()
    directory = _production_directory(root, production_id, create=True)
    assert directory is not None
    existing = read_production_metadata(root, production_id)
    if existing is not None:
        if existing["title"] != normalized["title"]:
            raise ProductionConflictError()
        return existing, True, False
    try:
        if tuple(directory.iterdir()):
            raise ProductionConflictError()
    except OSError as exc:
        raise _error("production output directory could not be inspected", "unsafe_production_path") from exc
    metadata = {
        "schema_version": PRODUCTION_SCHEMA_VERSION,
        "production_id": production_id,
        "title": normalized["title"],
        "imports": {},
    }
    _replace_metadata(root, production_id, metadata)
    return metadata, False, True


def _partial_directory(workspace: Path, production_id: str, *, create: bool) -> Path | None:
    return _directory(
        workspace,
        f"outputs/productions/{production_id}/{VIDEO_IMPORT_PARTIALS_DIRNAME}",
        create=create,
        code="unsafe_video_import_staging",
    )


def cleanup_stale_video_import_partials(workspace: Path) -> int:
    """Remove only closed-schema intake partials below valid productions."""

    root = _output_root(workspace, create=False)
    if root is None:
        return 0
    removed = 0
    for production in tuple(root.iterdir()):
        if production.is_symlink() or not production.is_dir() or PRODUCTION_ID_RE.fullmatch(production.name) is None:
            continue
        partials = production / VIDEO_IMPORT_PARTIALS_DIRNAME
        # ``Path.exists()`` is false for a broken symlink. Check the link
        # identity first so a stale/tampered staging alias cannot be silently
        # ignored at startup and later become live when its target appears.
        partials_is_symlink = partials.is_symlink()
        if partials_is_symlink or partials.exists():
            if partials_is_symlink or not partials.is_dir():
                raise _error("video import staging is unsafe", "unsafe_video_import_staging")
            for entry in tuple(partials.iterdir()):
                if entry.is_symlink() or not entry.is_file() or VIDEO_IMPORT_PARTIAL_NAME_RE.fullmatch(entry.name) is None:
                    raise _error("video import staging contains an unsafe entry", "unsafe_video_import_staging")
                try:
                    entry.unlink()
                except OSError as exc:
                    raise _error("stale video import staging could not be removed", "video_import_cleanup_failed") from exc
                removed += 1
            try:
                partials.rmdir()
            except OSError:
                pass
        for entry in tuple(production.iterdir()):
            if _METADATA_PARTIAL_RE.fullmatch(entry.name):
                if entry.is_symlink() or not entry.is_file():
                    raise _error("production metadata staging is unsafe", "unsafe_video_import_staging")
                try:
                    entry.unlink()
                except OSError as exc:
                    raise _error("stale production metadata staging could not be removed", "video_import_cleanup_failed") from exc
                removed += 1
    return removed


def _new_partial(workspace: Path, production_id: str) -> tuple[Path, BinaryIO]:
    root = _partial_directory(workspace, production_id, create=True)
    assert root is not None
    for _ in range(3):
        path = root / f"{uuid.uuid4().hex}.part"
        try:
            return path, path.open("xb")
        except FileExistsError:
            continue
        except OSError as exc:
            raise _error("video import staging could not be created", "video_import_staging_failed") from exc
    raise _error("video import staging identity collided", "video_import_staging_failed")


def _discard_partial(workspace: Path, production_id: str, path: Path) -> None:
    root = _partial_directory(workspace, production_id, create=False)
    if root is None:
        return
    if path.parent != root or VIDEO_IMPORT_PARTIAL_NAME_RE.fullmatch(path.name) is None or path.is_symlink():
        raise _error("video import partial path is unsafe", "video_import_cleanup_failed")
    try:
        if path.exists():
            if not path.is_file():
                raise OSError("partial is not a file")
            path.unlink()
        try:
            root.rmdir()
        except OSError:
            pass
    except OSError as exc:
        raise _error("video import partial could not be removed", "video_import_cleanup_failed") from exc


def _decode_filename(header: Any) -> tuple[str, str, str]:
    if not isinstance(header, str) or not header or len(header) > MAX_VIDEO_IMPORT_FILENAME_BYTES * 3:
        raise _error("X-Studio-Filename-Encoded is invalid", "invalid_video_filename")
    try:
        raw_header = header.encode("ascii")
    except UnicodeEncodeError as exc:
        raise _error("video filename header must be ASCII percent-encoded", "invalid_video_filename") from exc
    if re.search(r"%(?![0-9A-Fa-f]{2})", header):
        raise _error("video filename percent encoding is invalid", "invalid_video_filename")
    try:
        raw = unquote_to_bytes(raw_header)
        name = raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise _error("video filename is not valid UTF-8", "invalid_video_filename") from exc
    if not 1 <= len(raw) <= MAX_VIDEO_IMPORT_FILENAME_BYTES:
        raise _error("video filename is too long", "invalid_video_filename")
    if quote_from_bytes(raw, safe="-_.!~*'()") != header:
        raise _error("video filename must use canonical percent encoding", "invalid_video_filename")
    if (
        name in {".", ".."}
        or any(character in name for character in ("/", "\\", ":"))
        or any(character in _CONTROL_CHARACTERS for character in name)
        or name.startswith(".")
        or name.rstrip(" .") != name
    ):
        raise _error("video filename is not a regular local filename", "invalid_video_filename")
    extension = Path(name).suffix.casefold()
    if extension not in _VIDEO_MIME_TYPES:
        raise _error("video filename extension is not supported", "unsupported_video_extension")
    stem = name[: -len(extension)]
    safe_stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip(" ._-") or "video"
    if safe_stem.casefold() in _WINDOWS_RESERVED_NAMES:
        safe_stem = f"{safe_stem}_video"
    while len((safe_stem + extension).encode("utf-8")) > 180 and safe_stem:
        safe_stem = safe_stem[:-1]
    if not safe_stem:
        safe_stem = "video"
    return name, extension, f"{safe_stem}{extension}"


def validate_video_import_headers(
    filename_header: Any, content_type: Any, content_length: Any
) -> tuple[str, str, int, str, str]:
    original_name, extension, safe_name = _decode_filename(filename_header)
    if not isinstance(content_type, str) or not content_type or ";" in content_type:
        raise _error("Content-Type must be one supported video MIME type", "unsupported_media_type")
    mime = content_type.strip().casefold()
    if mime != "application/octet-stream" and mime not in _VIDEO_MIME_TYPES[extension]:
        raise _error("Content-Type does not match the video extension", "unsupported_media_type")
    if isinstance(content_length, bool) or not isinstance(content_length, int):
        raise _error("Content-Length is required for video import", "invalid_content_length")
    if content_length <= 0:
        raise _error("Content-Length must be positive", "invalid_content_length")
    if content_length > MAX_VIDEO_IMPORT_BYTES:
        raise _error("video import is larger than the 2 GiB limit", "request_too_large")
    return original_name, extension, content_length, safe_name, _CANONICAL_VIDEO_MIME[extension]


def _resolve_ffprobe() -> tuple[str, Callable[..., dict[str, Any]]]:
    try:
        from .assembly import _find_tool, _json_probe

        return _find_tool("ffprobe"), _json_probe
    except Exception as exc:
        raise _error("ffprobe is unavailable for video verification", "ffprobe_unavailable") from exc


def _verify_video(
    ffprobe: str,
    json_probe: Callable[..., dict[str, Any]],
    path: Path,
    *,
    expected_extension: str,
) -> None:
    try:
        probe = json_probe(ffprobe, path, cwd=path.parent)
    except Exception as exc:
        raise _error("ffprobe could not verify the uploaded video", "invalid_video_media") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        raise _error("the uploaded file does not contain a video stream", "invalid_video_media")
    format_data = probe.get("format") if isinstance(probe, dict) else None
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if not isinstance(format_name, str) or not format_name:
        raise _error("ffprobe did not report a video container", "invalid_video_media")
    containers = {token.strip().casefold() for token in format_name.split(",") if token.strip()}
    if not containers.intersection(_VIDEO_CONTAINERS[expected_extension]):
        raise _error("the video container does not match its extension", "invalid_video_media")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise _error("video import destination could not be verified", "video_destination_conflict") from exc
    return digest.hexdigest().upper()


def _import_path(workspace: Path, production_id: str, relative: str, *, create_parent: bool) -> Path:
    if not _valid_import_relative(relative):
        raise _error("video import destination is invalid", "unsafe_video_import_destination")
    imports = _directory(
        workspace,
        f"outputs/productions/{production_id}/{VIDEO_IMPORTS_DIRNAME}",
        create=create_parent,
        code="unsafe_video_import_destination",
    )
    if imports is None:
        return workspace_path(workspace, f"outputs/productions/{production_id}/{relative}", must_exist=False)
    path = imports / PurePosixPath(relative).name
    if _has_symlink_component(workspace, path):
        raise _error("video import destination contains a symlink", "unsafe_video_import_destination")
    return path


def _artifact(workspace: Path, production_id: str, destination: Path, digest: str) -> dict[str, Any]:
    try:
        stat = destination.stat()
        relative = relative_workspace_path(workspace, destination)
    except (OSError, SecurityError, ValueError) as exc:
        raise _error("video import destination could not be indexed", "video_import_failed") from exc
    return {
        "id": stable_id("art", relative.casefold()),
        "production_id": production_id,
        "rel_path": relative,
        "origin": "output",
        "name": destination.name,
        "kind": "video",
        "media_type": _CANONICAL_VIDEO_MIME[destination.suffix.casefold()],
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest,
        "is_heavy": True,
    }


def _publish_partial(partial: Path, destination: Path, *, length: int, digest: str) -> bool:
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise _error("video import destination is not a regular file", "unsafe_video_import_destination")
        if destination.stat().st_size != length or _hash_file(destination) != digest:
            raise _error("content-addressed video destination conflicts with its digest", "video_destination_conflict")
        return False
    try:
        os.link(partial, destination)
        return True
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file():
            raise _error("video import destination is not a regular file", "unsafe_video_import_destination")
        if destination.stat().st_size != length or _hash_file(destination) != digest:
            raise _error("content-addressed video destination conflicts with its digest", "video_destination_conflict")
        return False
    except OSError as exc:
        raise _error("video could not be atomically published", "video_publish_failed") from exc


def stream_video_import(
    workspace: Path,
    production_id: str,
    *,
    stream: BinaryIO,
    filename_header: Any,
    content_type: Any,
    content_length: Any,
) -> VideoImportResult:
    """Consume exactly Content-Length bytes and publish a verified output artifact."""

    production_id = validate_production_id(production_id)
    _original_name, extension, length, safe_name, _mime = validate_video_import_headers(
        filename_header, content_type, content_length
    )
    metadata = read_production_metadata(workspace, production_id)
    if metadata is None:
        raise _error("production was not found", "production_not_found")
    ffprobe, json_probe = _resolve_ffprobe()
    partial: Path | None = None
    destination: Path | None = None
    destination_created = False
    metadata_replaced = False
    try:
        partial, handle = _new_partial(workspace, production_id)
        digest_builder = hashlib.sha256()
        received = 0
        try:
            while received < length:
                remaining = length - received
                try:
                    chunk = stream.read(min(1024 * 1024, remaining))
                except Exception as exc:
                    raise _error("video upload could not be read", "video_upload_read_failed") from exc
                if not isinstance(chunk, (bytes, bytearray)) or not chunk or len(chunk) > remaining:
                    raise _error("video upload ended before Content-Length", "video_upload_truncated")
                data = bytes(chunk)
                handle.write(data)
                digest_builder.update(data)
                received += len(data)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        digest = digest_builder.hexdigest().upper()
        _verify_video(ffprobe, json_probe, partial, expected_extension=extension)

        existing_relative = next(
            (relative for relative, known in metadata["imports"].items() if known == digest),
            None,
        )
        if existing_relative is not None:
            destination = _import_path(
                workspace, production_id, existing_relative, create_parent=True
            )
            # The incoming name/container was already verified above.  When
            # a prior metadata entry uses another compatible extension, also
            # verify that exact extension even if its destination exists.
            # Otherwise a locally tampered control document could relabel
            # bytes as (for example) MP4 and make a later same-hash import
            # publish the wrong MIME type without another container check.
            if destination.suffix.casefold() != extension:
                _verify_video(
                    ffprobe,
                    json_probe,
                    partial,
                    expected_extension=destination.suffix.casefold(),
                )
            destination_created = _publish_partial(
                partial, destination, length=length, digest=digest
            )
            _discard_partial(workspace, production_id, partial)
            partial = None
            return VideoImportResult(
                artifact=_artifact(workspace, production_id, destination, digest),
                deduplicated=True,
                destination_created=destination_created,
            )

        physical_name = f"{digest.lower()[:VIDEO_IMPORT_SHA_PREFIX_LENGTH]}_{safe_name}"
        relative = f"{VIDEO_IMPORTS_DIRNAME}/{physical_name}"
        destination = _import_path(workspace, production_id, relative, create_parent=True)
        destination_created = _publish_partial(
            partial, destination, length=length, digest=digest
        )
        updated = {
            **metadata,
            "imports": {**metadata["imports"], relative: digest},
        }
        _replace_metadata(workspace, production_id, updated)
        metadata_replaced = True
        _discard_partial(workspace, production_id, partial)
        partial = None
        return VideoImportResult(
            artifact=_artifact(workspace, production_id, destination, digest),
            deduplicated=not destination_created,
            destination_created=destination_created,
        )
    except ProductionIntakeError:
        if destination_created and destination is not None and not metadata_replaced:
            try:
                if destination.exists() and not destination.is_symlink() and destination.is_file():
                    destination.unlink()
            except OSError:
                pass
        if partial is not None:
            _discard_partial(workspace, production_id, partial)
        raise
    except (OSError, SecurityError, ValueError) as exc:
        if destination_created and destination is not None and not metadata_replaced:
            try:
                if destination.exists() and not destination.is_symlink() and destination.is_file():
                    destination.unlink()
            except OSError:
                pass
        if partial is not None:
            _discard_partial(workspace, production_id, partial)
        raise _error("video import could not be completed", "video_import_failed") from exc
