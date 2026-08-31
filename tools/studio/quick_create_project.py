from __future__ import annotations

"""Create a Production, import local videos, and run Quick Create once.

The schema intentionally refers to input videos by a small integer index.  A
validated request is compiled to the existing Announcement Video recipe only
after the output-owned artifacts have been durably imported.  No source path,
source filename, or recipe copy is included in the public result or errors.
"""

import json
import math
import os
import re
import stat
import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO
from urllib.parse import quote_from_bytes

from .announcement_video import (
    ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    AnnouncementVideoValidationError,
    validate_announcement_recipe_id,
    validate_announcement_recipe_payload,
)
from .production_intake import (
    MAX_VIDEO_IMPORT_BYTES,
    ProductionIntakeError,
    validate_production_create_payload,
)
from .quick_create import (
    QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS,
    QUICK_CREATE_MAX_INPUT_BYTES,
    QUICK_CREATE_MAX_TIMEOUT_SECONDS,
    QUICK_CREATE_MIN_TIMEOUT_SECONDS,
    QUICK_CREATE_POLL_INTERVAL_SECONDS,
    QUICK_CREATE_SCHEMA_VERSION,
    QuickCreateError,
    QuickCreateValidationError,
    run_quick_create,
)
from .security import stable_id


QUICK_CREATE_PROJECT_SCHEMA_VERSION = 1
QUICK_CREATE_PROJECT_MIN_VIDEOS = 1
QUICK_CREATE_PROJECT_MAX_VIDEOS = 3
QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_CHARS = 1_024
QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_BYTES = 4_096

_REQUEST_REQUIRED_KEYS = {
    "schema_version",
    "production",
    "videos",
    "recipe_id",
    "expected_revision",
    "recipe",
}
_REQUEST_KEYS = _REQUEST_REQUIRED_KEYS | {"timeout_seconds"}
_VIDEO_KEYS = {"path"}
_RECIPE_KEYS = {
    "schema_version",
    "name",
    "template_preset",
    "scenes",
    "voice",
    "rate",
    "pronunciations",
    "include_captioned",
    "caption_style_preset",
    "audio_mix_preset",
    "variant",
}
_SCENE_REQUIRED_KEYS = {
    "role",
    "video_index",
    "start_ms",
    "end_ms",
    "volume_percent",
    "headline",
    "narration",
}
_SCENE_KEYS = _SCENE_REQUIRED_KEYS | {"visual_preset"}
_ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_IMPORT_NAME_RE = re.compile(
    r"^[0-9a-f]{16}_.+\.(?:mp4|m4v|mov|mkv|webm|avi)$"
)
_SAFE_ERROR_CODE_RE = re.compile(r"^[a-z0-9_.-]{1,128}$")


class QuickCreateProjectValidationError(QuickCreateValidationError):
    """The project request or a selected local video was not admissible."""

    def __init__(self, code: str = "invalid_quick_create_project_request") -> None:
        super().__init__(code)


def _invalid(
    code: str = "invalid_quick_create_project_request",
) -> QuickCreateProjectValidationError:
    return QuickCreateProjectValidationError(code)


def _reject_json_constant(_value: str) -> None:
    raise _invalid()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _relative_video_path(value: Any) -> str:
    try:
        encoded = value.encode("utf-8") if isinstance(value, str) else b""
    except UnicodeError:
        raise _invalid() from None
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value) > QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_CHARS
        or len(encoded) > QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_BYTES
    ):
        raise _invalid()
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise _invalid()
    # Paths are resolved from the request document's directory.  Empty
    # components and explicit traversal are rejected so the document cannot
    # silently select an unrelated local file.
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise _invalid()
    return value


def _compile_indexed_recipe(
    value: Any,
    artifact_ids: list[str],
) -> tuple[dict[str, Any], tuple[int, ...]]:
    if not isinstance(value, dict) or set(value) != _RECIPE_KEYS:
        raise _invalid()
    raw_scenes = value.get("scenes")
    if not isinstance(raw_scenes, list) or len(raw_scenes) != 3:
        raise _invalid()
    compiled_scenes: list[dict[str, Any]] = []
    indexes: list[int] = []
    for scene in raw_scenes:
        if (
            not isinstance(scene, dict)
            or not _SCENE_REQUIRED_KEYS.issubset(scene)
            or not set(scene).issubset(_SCENE_KEYS)
        ):
            raise _invalid()
        video_index = scene.get("video_index")
        if (
            isinstance(video_index, bool)
            or not isinstance(video_index, int)
            or not 0 <= video_index < len(artifact_ids)
        ):
            raise _invalid()
        indexes.append(video_index)
        compiled_scenes.append(
            {
                **{key: item for key, item in scene.items() if key != "video_index"},
                "video_artifact_id": artifact_ids[video_index],
            }
        )
    if set(indexes) != set(range(len(artifact_ids))):
        raise _invalid()
    try:
        normalized = validate_announcement_recipe_payload(
            {**value, "scenes": compiled_scenes}
        )
    except AnnouncementVideoValidationError:
        raise _invalid() from None
    return normalized, tuple(indexes)


def _placeholder_artifact_ids(count: int) -> list[str]:
    return [f"art_{index + 1:032x}" for index in range(count)]


def validate_quick_create_project_request(value: Any) -> dict[str, Any]:
    """Normalize one exact schema-v1 project request without opening videos."""

    if not isinstance(value, dict) or not _REQUEST_REQUIRED_KEYS <= set(value):
        raise _invalid()
    if set(value) not in (_REQUEST_REQUIRED_KEYS, _REQUEST_KEYS):
        raise _invalid()
    if (
        isinstance(value.get("schema_version"), bool)
        or not isinstance(value.get("schema_version"), int)
        or value.get("schema_version") != QUICK_CREATE_PROJECT_SCHEMA_VERSION
    ):
        raise _invalid()
    raw_production = value.get("production")
    if not isinstance(raw_production, dict) or set(raw_production) != {
        "id",
        "title",
    }:
        raise _invalid()
    try:
        production = validate_production_create_payload(
            {
                "schema_version": 1,
                "production_id": raw_production.get("id"),
                "title": raw_production.get("title"),
            }
        )
        recipe_id = validate_announcement_recipe_id(value.get("recipe_id"))
    except (ProductionIntakeError, AnnouncementVideoValidationError):
        raise _invalid() from None

    raw_videos = value.get("videos")
    if (
        not isinstance(raw_videos, list)
        or not QUICK_CREATE_PROJECT_MIN_VIDEOS
        <= len(raw_videos)
        <= QUICK_CREATE_PROJECT_MAX_VIDEOS
    ):
        raise _invalid()
    videos: list[dict[str, str]] = []
    for video in raw_videos:
        if not isinstance(video, dict) or set(video) != _VIDEO_KEYS:
            raise _invalid()
        videos.append({"path": _relative_video_path(video.get("path"))})

    expected_revision = value.get("expected_revision")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or not 0 <= expected_revision <= 1_000_000
    ):
        raise _invalid()
    timeout_seconds = value.get(
        "timeout_seconds", QUICK_CREATE_DEFAULT_TIMEOUT_SECONDS
    )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not QUICK_CREATE_MIN_TIMEOUT_SECONDS
        <= timeout_seconds
        <= QUICK_CREATE_MAX_TIMEOUT_SECONDS
    ):
        raise _invalid()

    normalized_recipe, indexes = _compile_indexed_recipe(
        value.get("recipe"), _placeholder_artifact_ids(len(videos))
    )
    indexed_scenes: list[dict[str, Any]] = []
    for scene, video_index in zip(
        normalized_recipe["scenes"], indexes, strict=True
    ):
        indexed_scenes.append(
            {
                **{
                    key: item
                    for key, item in scene.items()
                    if key != "video_artifact_id"
                },
                "video_index": video_index,
            }
        )
    return {
        "schema_version": QUICK_CREATE_PROJECT_SCHEMA_VERSION,
        "production": {
            "id": production["production_id"],
            "title": production["title"],
        },
        "videos": videos,
        "recipe_id": recipe_id,
        "expected_revision": expected_revision,
        "recipe": {**normalized_recipe, "scenes": indexed_scenes},
        "timeout_seconds": timeout_seconds,
    }


def load_quick_create_project_request(path: Path) -> dict[str, Any]:
    """Load one bounded UTF-8 request without reflecting its path or content."""

    try:
        candidate = Path(path)
        with candidate.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise OSError("request is not a regular file")
            if not 1 <= before.st_size <= QUICK_CREATE_MAX_INPUT_BYTES:
                raise _invalid("quick_create_input_too_large")
            raw = handle.read(QUICK_CREATE_MAX_INPUT_BYTES + 1)
            after = os.fstat(handle.fileno())
        if (
            len(raw) != before.st_size
            or len(raw) > QUICK_CREATE_MAX_INPUT_BYTES
            or _file_identity(before) != _file_identity(after)
            or _file_content_state(before) != _file_content_state(after)
        ):
            raise _invalid("quick_create_input_changed")
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except QuickCreateProjectValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise _invalid() from None
    return validate_quick_create_project_request(parsed)


def _file_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _file_content_state(value: os.stat_result) -> tuple[int, int]:
    return (value.st_size, value.st_mtime_ns)


def _safe_service_error_code(exc: BaseException, default: str) -> str:
    code = getattr(exc, "code", None)
    if not isinstance(code, str):
        code = getattr(exc, "error_code", None)
    if isinstance(code, str) and _SAFE_ERROR_CODE_RE.fullmatch(code):
        return code
    return default


def _check_deadline(clock: Callable[[], float], deadline: float) -> None:
    if deadline - clock() <= 0:
        raise QuickCreateError("quick_create_timeout")


def _production_result(value: Any, expected: Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "production",
        "deduplicated",
    }:
        raise QuickCreateError("invalid_quick_create_project_result")
    production = value.get("production")
    deduplicated = value.get("deduplicated")
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or not isinstance(production, Mapping)
        or production.get("id") != expected["id"]
        or production.get("title") != expected["title"]
        or not isinstance(deduplicated, bool)
    ):
        raise QuickCreateError("invalid_quick_create_project_result")
    return {
        "id": expected["id"],
        "title": expected["title"],
        "deduplicated": deduplicated,
    }


def _safe_import_relative(value: Any, production_id: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 1_024 or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return False
    if any(part in {"", ".", ".."} for part in posix.parts):
        return False
    return (
        posix.parts[:4]
        == (
            "outputs",
            "productions",
            production_id,
            "imports",
        )
        and len(posix.parts) == 5
        and _IMPORT_NAME_RE.fullmatch(posix.name) is not None
    )


def _import_result(
    value: Any,
    *,
    production_id: str,
    source_index: int,
    source_size: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "artifact",
        "deduplicated",
    }:
        raise QuickCreateError("invalid_quick_create_project_result")
    artifact = value.get("artifact")
    deduplicated = value.get("deduplicated")
    if not isinstance(artifact, Mapping):
        raise QuickCreateError("invalid_quick_create_project_result")
    artifact_id = artifact.get("id")
    byte_count = artifact.get("bytes")
    digest = artifact.get("sha256")
    relative = artifact.get("rel_path")
    normalized_relative = (
        relative.replace("\\", "/") if isinstance(relative, str) else ""
    )
    physical_name = PurePosixPath(normalized_relative).name
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or not isinstance(deduplicated, bool)
        or not isinstance(artifact_id, str)
        or _ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        or artifact.get("production_id") != production_id
        or artifact.get("origin") != "output"
        or artifact.get("kind") != "video"
        or artifact.get("available") is not True
        or not _safe_import_relative(relative, production_id)
        or artifact_id != stable_id("art", normalized_relative.casefold())
        or artifact.get("name") != physical_name
        or isinstance(byte_count, bool)
        or byte_count != source_size
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
        or not physical_name.startswith(f"{digest[:16].lower()}_")
    ):
        raise QuickCreateError("invalid_quick_create_project_result")
    return {
        "source_index": source_index,
        "artifact_id": artifact_id,
        "bytes": byte_count,
        "sha256": digest,
        "deduplicated": deduplicated,
    }


def _open_video(parent: Path, relative: str) -> tuple[BinaryIO, os.stat_result]:
    try:
        candidate = parent.joinpath(*PurePosixPath(relative.replace("\\", "/")).parts)
        handle = candidate.open("rb")
        before = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or not 1 <= before.st_size <= MAX_VIDEO_IMPORT_BYTES
        ):
            handle.close()
            raise OSError("video is not an admissible regular file")
        return handle, before
    except OSError:
        raise _invalid("invalid_quick_create_project_video") from None


def _assert_video_unchanged(
    handle: BinaryIO,
    before: os.stat_result,
) -> None:
    try:
        after = os.fstat(handle.fileno())
        consumed = handle.tell()
    except (OSError, ValueError):
        raise _invalid("quick_create_project_video_changed") from None
    if (
        _file_identity(before) != _file_identity(after)
        or _file_content_state(before) != _file_content_state(after)
        or consumed != before.st_size
    ):
        raise _invalid("quick_create_project_video_changed")


def run_quick_create_project(
    service: Any,
    value: Any,
    *,
    request_parent: Path,
    deadline: float | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    poll_interval_seconds: float = QUICK_CREATE_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Create, import, compile, and execute with one monotonic deadline."""

    request = validate_quick_create_project_request(value)
    clock = monotonic or time.monotonic
    started_at = clock()
    request_deadline = started_at + request["timeout_seconds"]
    if deadline is None:
        effective_deadline = request_deadline
    elif (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(float(deadline))
    ):
        raise ValueError("deadline is invalid")
    else:
        effective_deadline = min(float(deadline), request_deadline)
    _check_deadline(clock, effective_deadline)

    production_request = {
        "schema_version": 1,
        "production_id": request["production"]["id"],
        "title": request["production"]["title"],
    }
    try:
        created = service.create_production(production_request)
    except Exception as exc:
        raise QuickCreateError(
            _safe_service_error_code(exc, "quick_create_project_create_failed")
        ) from exc
    production_summary = _production_result(created, request["production"])
    _check_deadline(clock, effective_deadline)

    imports: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    parent = Path(request_parent)
    for source_index, selected in enumerate(request["videos"]):
        _check_deadline(clock, effective_deadline)
        handle, before = _open_video(parent, selected["path"])
        try:
            encoded_name = quote_from_bytes(
                Path(selected["path"].replace("\\", "/")).name.encode("utf-8"),
                safe="-_.!~*'()",
            )
            try:
                imported = service.import_production_video(
                    request["production"]["id"],
                    stream=handle,
                    filename_header=encoded_name,
                    content_type="application/octet-stream",
                    content_length=before.st_size,
                )
            except Exception as exc:
                raise QuickCreateError(
                    _safe_service_error_code(
                        exc, "quick_create_project_import_failed"
                    )
                ) from exc
            _assert_video_unchanged(handle, before)
        finally:
            handle.close()
        summary = _import_result(
            imported,
            production_id=request["production"]["id"],
            source_index=source_index,
            source_size=before.st_size,
        )
        imports.append(summary)
        artifact_ids.append(summary["artifact_id"])
        _check_deadline(clock, effective_deadline)

    compiled_recipe, _indexes = _compile_indexed_recipe(
        request["recipe"], artifact_ids
    )
    quick_request = {
        "schema_version": QUICK_CREATE_SCHEMA_VERSION,
        "production_id": request["production"]["id"],
        "recipe_id": request["recipe_id"],
        "expected_revision": request["expected_revision"],
        "recipe": compiled_recipe,
        "timeout_seconds": request["timeout_seconds"],
    }
    _check_deadline(clock, effective_deadline)
    quick_result = run_quick_create(
        service,
        quick_request,
        poll_interval_seconds=poll_interval_seconds,
        monotonic=clock,
        sleep=sleep,
        deadline=effective_deadline,
    )
    if not isinstance(quick_result, dict):
        raise QuickCreateError("invalid_quick_create_project_result")
    return {
        "schema_version": QUICK_CREATE_PROJECT_SCHEMA_VERSION,
        "production": production_summary,
        "videos": imports,
        "quick_create": quick_result,
    }


__all__ = [
    "QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_BYTES",
    "QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_CHARS",
    "QUICK_CREATE_PROJECT_MAX_VIDEOS",
    "QUICK_CREATE_PROJECT_MIN_VIDEOS",
    "QUICK_CREATE_PROJECT_SCHEMA_VERSION",
    "QuickCreateProjectValidationError",
    "load_quick_create_project_request",
    "run_quick_create_project",
    "validate_quick_create_project_request",
]
