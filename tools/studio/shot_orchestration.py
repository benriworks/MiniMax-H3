from __future__ import annotations

"""Auditable three-cut I2VA orchestration for Studio Quick Create.

The local ComfyUI preset is intentionally T2VA-only.  This module therefore
uses the existing official MiniMax H3 V2 client for first-frame generation
requests and keeps every billable submission behind an explicit task limit.
Each cut is submitted and persisted independently so a restart never silently
submits a second paid task.
"""

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from tools import h3_api

from .announcement_video import ANNOUNCEMENT_VIDEO_TRANSITION_MS
from .production_intake import validate_production_create_payload
from .quick_create_project import (
    QUICK_CREATE_PROJECT_MAX_VIDEOS,
    run_quick_create_project,
    validate_quick_create_project_request,
)
from .security import canonical_json, workspace_path


SHOT_PROJECT_SCHEMA_VERSION = 1
SHOT_PROJECT_COUNT = 3
SHOT_PROJECT_DURATION_SECONDS = 6
SHOT_PROJECT_OUTPUT_DURATION_MS = 15_000
SHOT_PROJECT_RESOLUTION = "768P"
SHOT_PROJECT_RATIO = "adaptive"
SHOT_PROJECT_POLL_INTERVAL_SECONDS = 10.0
SHOT_PROJECT_MIN_TIMEOUT_SECONDS = 60
SHOT_PROJECT_MAX_TIMEOUT_SECONDS = 24 * 60 * 60
SHOT_PROJECT_MAX_REQUEST_BYTES = 512 * 1024
SHOT_PROJECT_MAX_IMAGE_BYTES = 30 * 1024 * 1024
SHOT_PROJECT_STATE_FILENAME = "state.json"
SHOT_PROJECT_PLAN_FILENAME = "plan.json"

_PROJECT_ID_RE = re.compile(r"^shotproj_[0-9a-f]{32}$")
_SHOT_ID_RE = re.compile(r"^shot_[1-3]$")
_TASK_ID_RE = re.compile(r"^[^\x00-\x20\x7f]{1,256}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9_.-]{1,128}$")
_IMAGE_SUFFIXES = frozenset((".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"))
_REQUEST_KEYS = {
    "schema_version",
    "project_id",
    "production",
    "shots",
    "recipe_id",
    "expected_revision",
    "recipe",
    "timeout_seconds",
    "confirmed_billable_task_limit",
}
_SHOT_KEYS = {
    "shot_id",
    "first_frame_path",
    "first_frame_prompt",
    "video_prompt",
    "duration_seconds",
    "resolution",
}
_STATE_KEYS = {
    "schema_version",
    "project_id",
    "production_id",
    "request_digest",
    "created_at_ms",
    "updated_at_ms",
    "shots",
}
_STATE_SHOT_KEYS = {
    "shot_id",
    "prompt_sha256",
    "first_frame_sha256",
    "status",
    "task_id",
    "output",
}
_I2VA_PREFIX = (
    "For the target video, at 0.00 seconds into the target video, "
    "<Picture 1> (from [Shot 1]) is fully referenced."
)
_I2VA_FIELDS = (
    "integrated_multimodal_description: [Shot 1]",
    "overall_soundscape:",
    "non_diegetic_music:",
)


class ShotProjectError(RuntimeError):
    """A bounded orchestration failure safe for CLI and API projection."""

    def __init__(self, code: str):
        safe = code if isinstance(code, str) and _SAFE_CODE_RE.fullmatch(code) else "shot_project_failed"
        super().__init__(safe)
        self.code = safe


class ShotProjectValidationError(ShotProjectError, ValueError):
    pass


def _invalid(code: str = "invalid_shot_project_request") -> ShotProjectValidationError:
    return ShotProjectValidationError(code)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(handle: Any) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest().upper()


def _valid_image_signature(suffix: str, header: bytes) -> bool:
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if suffix in {".heic", ".heif"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    return False


def _valid_mp4_signature(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    return len(header) >= 12 and header[4:8] == b"ftyp"


def _now_ms(clock: Callable[[], float]) -> int:
    return int(clock() * 1000)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise _invalid()


def _relative_input_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
        raise _invalid(f"invalid_{label}")
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise _invalid(f"invalid_{label}")
    return normalized


def _has_symlink_component(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return True
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _validate_i2va_prompt(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 7000:
        raise _invalid("invalid_shot_video_prompt")
    if not value.startswith(_I2VA_PREFIX + "\n\n"):
        raise _invalid("invalid_shot_video_prompt")
    positions = [value.find(field) for field in _I2VA_FIELDS]
    if positions[0] < len(_I2VA_PREFIX) + 2 or positions != sorted(positions) or any(item < 0 for item in positions):
        raise _invalid("invalid_shot_video_prompt")
    if value.count("integrated_multimodal_description:") != 1:
        raise _invalid("invalid_shot_video_prompt")
    if value.count("overall_soundscape:") != 1 or value.count("non_diegetic_music:") != 1:
        raise _invalid("invalid_shot_video_prompt")
    if "[Shot 2]" in value or "[Shot 3]" in value:
        raise _invalid("invalid_shot_video_prompt")
    if any(ord(character) < 0x20 and character not in "\n\t" for character in value):
        raise _invalid("invalid_shot_video_prompt")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _invalid("invalid_shot_video_prompt") from None
    return value


def validate_shot_project_request(value: Any) -> dict[str, Any]:
    """Validate the exact v1 three-cut I2VA-to-Quick-Create request."""

    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise _invalid()
    if value.get("schema_version") != SHOT_PROJECT_SCHEMA_VERSION or isinstance(
        value.get("schema_version"), bool
    ):
        raise _invalid("unsupported_shot_project_schema")
    project_id = value.get("project_id")
    if not isinstance(project_id, str) or _PROJECT_ID_RE.fullmatch(project_id) is None:
        raise _invalid("invalid_shot_project_id")
    raw_production = value.get("production")
    if not isinstance(raw_production, dict) or set(raw_production) != {"id", "title"}:
        raise _invalid()
    try:
        production = validate_production_create_payload(
            {
                "schema_version": 1,
                "production_id": raw_production.get("id"),
                "title": raw_production.get("title"),
            }
        )
    except Exception:
        raise _invalid() from None

    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) != SHOT_PROJECT_COUNT:
        raise _invalid("invalid_shot_count")
    shots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_shots, start=1):
        if not isinstance(raw, dict) or set(raw) != _SHOT_KEYS:
            raise _invalid()
        shot_id = raw.get("shot_id")
        if (
            not isinstance(shot_id, str)
            or _SHOT_ID_RE.fullmatch(shot_id) is None
            or shot_id != f"shot_{index}"
            or shot_id in seen
        ):
            raise _invalid("invalid_shot_id")
        seen.add(shot_id)
        first_frame_prompt = raw.get("first_frame_prompt")
        if (
            not isinstance(first_frame_prompt, str)
            or not first_frame_prompt.strip()
            or len(first_frame_prompt) > 4000
            or any(ord(character) < 0x20 and character not in "\n\t" for character in first_frame_prompt)
        ):
            raise _invalid("invalid_first_frame_prompt")
        if (
            raw.get("duration_seconds") != SHOT_PROJECT_DURATION_SECONDS
            or isinstance(raw.get("duration_seconds"), bool)
            or raw.get("resolution") != SHOT_PROJECT_RESOLUTION
        ):
            raise _invalid("unsupported_shot_generation_preset")
        frame_path = _relative_input_path(raw.get("first_frame_path"), label="first_frame_path")
        if PurePosixPath(frame_path).suffix.casefold() not in _IMAGE_SUFFIXES:
            raise _invalid("unsupported_first_frame_extension")
        shots.append(
            {
                "shot_id": shot_id,
                "first_frame_path": frame_path,
                "first_frame_prompt": first_frame_prompt,
                "video_prompt": _validate_i2va_prompt(raw.get("video_prompt")),
                "duration_seconds": SHOT_PROJECT_DURATION_SECONDS,
                "resolution": SHOT_PROJECT_RESOLUTION,
            }
        )

    timeout_seconds = value.get("timeout_seconds")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not SHOT_PROJECT_MIN_TIMEOUT_SECONDS <= timeout_seconds <= SHOT_PROJECT_MAX_TIMEOUT_SECONDS
    ):
        raise _invalid("invalid_shot_project_timeout")
    task_limit = value.get("confirmed_billable_task_limit")
    if isinstance(task_limit, bool) or not isinstance(task_limit, int) or task_limit != len(shots):
        raise _invalid("billable_task_limit_not_confirmed")

    quick_request = {
        "schema_version": 1,
        "production": {
            "id": production["production_id"],
            "title": production["title"],
        },
        "videos": [{"path": f"{shot['shot_id']}.mp4"} for shot in shots],
        "recipe_id": value.get("recipe_id"),
        "expected_revision": value.get("expected_revision"),
        "recipe": value.get("recipe"),
        "timeout_seconds": timeout_seconds,
    }
    try:
        normalized_quick = validate_quick_create_project_request(quick_request)
    except Exception:
        raise _invalid("invalid_shot_project_recipe") from None
    if len(normalized_quick["videos"]) != QUICK_CREATE_PROJECT_MAX_VIDEOS:
        raise _invalid("invalid_shot_project_recipe")
    normalized_scenes = normalized_quick["recipe"]["scenes"]
    if [item["video_index"] for item in normalized_scenes] != [0, 1, 2]:
        raise _invalid("invalid_shot_project_recipe")
    output_duration_ms = (
        sum(item["end_ms"] - item["start_ms"] for item in normalized_scenes)
        - ANNOUNCEMENT_VIDEO_TRANSITION_MS * (len(normalized_scenes) - 1)
    )
    if output_duration_ms != SHOT_PROJECT_OUTPUT_DURATION_MS:
        raise _invalid("invalid_shot_project_duration")
    return {
        "schema_version": SHOT_PROJECT_SCHEMA_VERSION,
        "project_id": project_id,
        "production": normalized_quick["production"],
        "shots": shots,
        "recipe_id": normalized_quick["recipe_id"],
        "expected_revision": normalized_quick["expected_revision"],
        "recipe": normalized_quick["recipe"],
        "timeout_seconds": timeout_seconds,
        "confirmed_billable_task_limit": task_limit,
    }


def load_shot_project_request(path: Path) -> dict[str, Any]:
    try:
        candidate = Path(path)
        with candidate.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= SHOT_PROJECT_MAX_REQUEST_BYTES:
                raise _invalid()
            raw = handle.read(SHOT_PROJECT_MAX_REQUEST_BYTES + 1)
            after = os.fstat(handle.fileno())
        if (
            len(raw) != before.st_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise _invalid("shot_project_input_changed")
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ShotProjectValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise _invalid() from None
    return validate_shot_project_request(parsed)


def _inspect_first_frames(
    request_parent: Path, shots: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    try:
        parent = request_parent.resolve(strict=True)
    except OSError:
        raise _invalid("invalid_first_frame_path") from None
    result: list[dict[str, Any]] = []
    for shot in shots:
        candidate = parent.joinpath(*PurePosixPath(shot["first_frame_path"]).parts)
        try:
            if _has_symlink_component(parent, candidate):
                raise OSError("symlink")
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(parent)
            with resolved.open("rb") as handle:
                before = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or not 1 <= before.st_size <= SHOT_PROJECT_MAX_IMAGE_BYTES
                ):
                    raise OSError("invalid image")
                header = handle.read(16)
                if not _valid_image_signature(resolved.suffix.casefold(), header):
                    raise OSError("invalid image signature")
                handle.seek(0)
                digest = _sha256_file(handle)
                after = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise OSError("changed image")
        except (OSError, ValueError):
            raise _invalid("invalid_first_frame_path") from None
        result.append({"path": resolved, "bytes": before.st_size, "sha256": digest})
    return result


def _state_directory(workspace: Path, project_id: str) -> Path:
    workspace_root = workspace.resolve(strict=True)
    lexical_root = workspace_root / "outputs" / "studio" / "shot_projects"
    if _has_symlink_component(workspace_root, lexical_root):
        raise ShotProjectError("unsafe_shot_project_state")
    root = workspace_path(workspace_root, lexical_root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ShotProjectError("unsafe_shot_project_state")
    lexical_directory = root / project_id
    if _has_symlink_component(workspace_root, lexical_directory):
        raise ShotProjectError("unsafe_shot_project_state")
    directory = workspace_path(workspace_root, lexical_directory)
    if directory.exists() or directory.is_symlink():
        if directory.is_symlink() or not directory.is_dir():
            raise ShotProjectError("unsafe_shot_project_state")
    else:
        directory.mkdir()
    return directory


def _write_state(path: Path, value: dict[str, Any]) -> None:
    encoded = (canonical_json(value) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".state.", suffix=".partial", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink() or temporary.is_symlink():
            raise OSError("unsafe state")
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise ShotProjectError("shot_project_state_write_failed") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _ensure_plan(
    directory: Path,
    request: Mapping[str, Any],
    frames: list[dict[str, Any]],
    request_digest: str,
) -> dict[str, Any]:
    unsigned = {
        "schema_version": SHOT_PROJECT_SCHEMA_VERSION,
        "project_id": request["project_id"],
        "production": request["production"],
        "generation": {
            "provider": "minimax_h3_v2",
            "mode": "i2va",
            "resolution": SHOT_PROJECT_RESOLUTION,
            "duration_seconds": SHOT_PROJECT_DURATION_SECONDS,
            "ratio": SHOT_PROJECT_RATIO,
            "poll_interval_seconds": SHOT_PROJECT_POLL_INTERVAL_SECONDS,
        },
        "request_digest": request_digest,
        "shots": [
            {
                **shot,
                "first_frame": {
                    "relative_path": shot["first_frame_path"],
                    "bytes": frame["bytes"],
                    "sha256": frame["sha256"],
                },
            }
            for shot, frame in zip(request["shots"], frames, strict=True)
        ],
        "quick_create": {
            "recipe_id": request["recipe_id"],
            "expected_revision": request["expected_revision"],
            "recipe": request["recipe"],
        },
        "confirmed_billable_task_limit": request["confirmed_billable_task_limit"],
    }
    document = {
        **unsigned,
        "plan_sha256": _sha256_bytes(canonical_json(unsigned).encode("utf-8")),
    }
    path = directory / SHOT_PROJECT_PLAN_FILENAME
    if path.is_symlink():
        raise ShotProjectError("unsafe_shot_project_state")
    if path.exists():
        try:
            if not path.is_file() or path.stat().st_size > SHOT_PROJECT_MAX_REQUEST_BYTES * 2:
                raise OSError("invalid plan")
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ShotProjectError("invalid_shot_project_plan") from None
        if existing != document:
            raise ShotProjectError("shot_project_request_conflict")
    else:
        _write_state(path, document)
    return document


def _validate_output(value: Any, *, shot_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    expected_name = f"{shot_id}.mp4"
    if (
        not isinstance(value, dict)
        or set(value) != {"name", "bytes", "sha256"}
        or value.get("name") != expected_name
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] <= 0
        or not isinstance(value.get("sha256"), str)
        or _SHA256_RE.fullmatch(value["sha256"]) is None
    ):
        raise ShotProjectError("invalid_shot_project_state")
    return dict(value)


def _validate_state(value: Any, request: Mapping[str, Any], digest: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != _STATE_KEYS
        or value.get("schema_version") != SHOT_PROJECT_SCHEMA_VERSION
        or value.get("project_id") != request["project_id"]
        or value.get("production_id") != request["production"]["id"]
        or value.get("request_digest") != digest
        or not isinstance(value.get("created_at_ms"), int)
        or not isinstance(value.get("updated_at_ms"), int)
    ):
        raise ShotProjectError("shot_project_request_conflict")
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) != SHOT_PROJECT_COUNT:
        raise ShotProjectError("invalid_shot_project_state")
    normalized: list[dict[str, Any]] = []
    for expected, raw in zip(request["shots"], raw_shots, strict=True):
        if not isinstance(raw, dict) or set(raw) != _STATE_SHOT_KEYS:
            raise ShotProjectError("invalid_shot_project_state")
        task_id = raw.get("task_id")
        status = raw.get("status")
        if status not in {"pending", "prepared", "submitted", "succeeded", "failed"}:
            raise ShotProjectError("invalid_shot_project_state")
        if task_id is not None and (
            not isinstance(task_id, str) or _TASK_ID_RE.fullmatch(task_id) is None
        ):
            raise ShotProjectError("invalid_shot_project_state")
        if status in {"submitted", "succeeded", "failed"} and task_id is None:
            raise ShotProjectError("invalid_shot_project_state")
        if status in {"pending", "prepared"} and task_id is not None:
            raise ShotProjectError("invalid_shot_project_state")
        if (
            raw.get("shot_id") != expected["shot_id"]
            or raw.get("prompt_sha256")
            != _sha256_bytes(expected["video_prompt"].encode("utf-8"))
            or not isinstance(raw.get("first_frame_sha256"), str)
            or _SHA256_RE.fullmatch(raw["first_frame_sha256"]) is None
        ):
            raise ShotProjectError("shot_project_request_conflict")
        output = _validate_output(raw.get("output"), shot_id=expected["shot_id"])
        if (status == "succeeded") != (output is not None):
            raise ShotProjectError("invalid_shot_project_state")
        normalized.append({**raw, "output": output})
    return {**value, "shots": normalized}


def _load_or_create_state(
    directory: Path,
    request: dict[str, Any],
    frames: list[dict[str, Any]],
    digest: str,
    clock: Callable[[], float],
) -> tuple[dict[str, Any], bool]:
    path = directory / SHOT_PROJECT_STATE_FILENAME
    if path.is_symlink():
        raise ShotProjectError("unsafe_shot_project_state")
    if path.exists():
        try:
            if not path.is_file() or path.stat().st_size > 256 * 1024:
                raise OSError("invalid state")
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ShotProjectError("invalid_shot_project_state") from None
        state = _validate_state(value, request, digest)
        for item, frame in zip(state["shots"], frames, strict=True):
            if item["first_frame_sha256"] != frame["sha256"]:
                raise ShotProjectError("shot_project_request_conflict")
        return state, False
    timestamp = _now_ms(clock)
    state = {
        "schema_version": SHOT_PROJECT_SCHEMA_VERSION,
        "project_id": request["project_id"],
        "production_id": request["production"]["id"],
        "request_digest": digest,
        "created_at_ms": timestamp,
        "updated_at_ms": timestamp,
        "shots": [
            {
                "shot_id": shot["shot_id"],
                "prompt_sha256": _sha256_bytes(shot["video_prompt"].encode("utf-8")),
                "first_frame_sha256": frame["sha256"],
                "status": "pending",
                "task_id": None,
                "output": None,
            }
            for shot, frame in zip(request["shots"], frames, strict=True)
        ],
    }
    _write_state(path, state)
    return state, True


def _persist_state(
    directory: Path, state: dict[str, Any], clock: Callable[[], float]
) -> None:
    state["updated_at_ms"] = _now_ms(clock)
    _write_state(directory / SHOT_PROJECT_STATE_FILENAME, state)


def _verified_existing_output(directory: Path, state_shot: dict[str, Any]) -> bool:
    output = state_shot.get("output")
    if state_shot.get("status") != "succeeded" or not isinstance(output, dict):
        return False
    path = directory / output["name"]
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != output["bytes"]
            or not _valid_mp4_signature(path)
        ):
            return False
        with path.open("rb") as handle:
            digest = _sha256_file(handle)
    except OSError:
        return False
    return digest == output["sha256"]


def _safe_provider_code(exc: BaseException) -> str:
    if isinstance(exc, h3_api.H3TaskError):
        return "shot_provider_failed"
    if isinstance(exc, h3_api.H3ValidationError):
        return "invalid_shot_provider_request"
    if isinstance(exc, (h3_api.H3APIError, h3_api.H3ConfigurationError)):
        return "shot_provider_unavailable"
    return "shot_provider_failed"


def _quick_request(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "production": dict(request["production"]),
        "videos": [{"path": f"{shot['shot_id']}.mp4"} for shot in request["shots"]],
        "recipe_id": request["recipe_id"],
        "expected_revision": request["expected_revision"],
        "recipe": request["recipe"],
        "timeout_seconds": request["timeout_seconds"],
    }


def run_shot_project(
    service: Any,
    value: Any,
    *,
    workspace: Path,
    request_parent: Path,
    api_key: str,
    api_base: str = h3_api.DEFAULT_API_BASE,
    client_factory: Callable[[str, str], Any] | None = None,
    quick_create_runner: Callable[..., dict[str, Any]] = run_quick_create_project,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Generate three I2VA clips and feed the exact outputs to Quick Create."""

    request = validate_shot_project_request(value)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ShotProjectError("minimax_credential_missing")
    frames = _inspect_first_frames(Path(request_parent), request["shots"])
    digest_material = {
        **request,
        "confirmed_billable_task_limit": request["confirmed_billable_task_limit"],
        "first_frame_sha256": [item["sha256"] for item in frames],
    }
    request_digest = _sha256_bytes(canonical_json(digest_material).encode("utf-8"))
    directory = _state_directory(Path(workspace).resolve(strict=True), request["project_id"])
    state, created = _load_or_create_state(
        directory, request, frames, request_digest, wall_clock
    )
    plan = _ensure_plan(directory, request, frames, request_digest)
    deadline = monotonic() + request["timeout_seconds"]
    client = (
        client_factory(api_key.strip(), api_base)
        if client_factory is not None
        else h3_api.H3Client(api_key.strip(), api_base)
    )
    submitted_this_call = 0

    for index, (shot, frame) in enumerate(zip(request["shots"], frames, strict=True)):
        state_shot = state["shots"][index]
        if state_shot["status"] == "succeeded":
            if not _verified_existing_output(directory, state_shot):
                raise ShotProjectError("shot_output_integrity_failed")
            continue
        if state_shot["status"] == "failed":
            raise ShotProjectError("shot_provider_failed")
        if state_shot["status"] == "prepared" and not created:
            # Submission could have reached the paid provider before the task
            # id was durably recorded.  Automatic retry would risk charging a
            # second task, so a new project id/manual provider check is needed.
            raise ShotProjectError("shot_submission_ambiguous")
        if state_shot["status"] == "pending":
            if submitted_this_call >= request["confirmed_billable_task_limit"]:
                raise ShotProjectError("billable_task_limit_exhausted")
            state_shot["status"] = "prepared"
            _persist_state(directory, state, wall_clock)
            try:
                payload = h3_api.build_generation_payload(
                    prompt=shot["video_prompt"],
                    resolution=SHOT_PROJECT_RESOLUTION,
                    duration=SHOT_PROJECT_DURATION_SECONDS,
                    ratio=SHOT_PROJECT_RATIO,
                    images=[("first_frame", str(frame["path"]))],
                )
                submitted = client.submit(payload)
            except Exception as exc:
                # The request may have reached the provider even when no
                # response arrived.  Keep the prepared marker and block any
                # automatic paid resubmission.
                raise ShotProjectError("shot_submission_ambiguous") from exc
            task_id = submitted.get("task_id") if isinstance(submitted, Mapping) else None
            if not isinstance(task_id, str) or _TASK_ID_RE.fullmatch(task_id) is None:
                raise ShotProjectError("invalid_shot_provider_response")
            state_shot["task_id"] = task_id
            state_shot["status"] = "submitted"
            _persist_state(directory, state, wall_clock)
            submitted_this_call += 1

        if state_shot["status"] != "submitted" or not isinstance(state_shot["task_id"], str):
            raise ShotProjectError("invalid_shot_project_state")
        output_path = directory / f"{shot['shot_id']}.mp4"
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ShotProjectError("shot_project_timeout")
        try:
            response = client.status(state_shot["task_id"])
            task = h3_api.task_from_response(response)
            if task["status"] == "succeeded" and output_path.exists():
                # A prior process may have downloaded the exact submitted task
                # and crashed before state publication.  Accept only a regular,
                # non-empty file at this closed path.
                if (
                    output_path.is_symlink()
                    or not output_path.is_file()
                    or output_path.stat().st_size <= 0
                    or not _valid_mp4_signature(output_path)
                ):
                    raise ShotProjectError("shot_output_integrity_failed")
            else:
                h3_api.wait_for_task(
                    client,
                    state_shot["task_id"],
                    interval=SHOT_PROJECT_POLL_INTERVAL_SECONDS,
                    timeout=remaining,
                    output=output_path,
                    overwrite=False,
                    sleep=sleep,
                    clock=monotonic,
                )
        except ShotProjectError:
            raise
        except h3_api.H3TaskError as exc:
            # A timeout leaves the durable provider id submitted and resumable;
            # a terminal provider failure is detected by a fresh status query on
            # the next invocation.  Both avoid an automatic paid resubmit.
            if "timed out" in str(exc).casefold():
                raise ShotProjectError("shot_project_timeout") from exc
            state_shot["status"] = "failed"
            _persist_state(directory, state, wall_clock)
            raise ShotProjectError("shot_provider_failed") from exc
        except Exception as exc:
            raise ShotProjectError(_safe_provider_code(exc)) from exc
        try:
            if output_path.is_symlink() or not output_path.is_file():
                raise OSError("missing output")
            byte_count = output_path.stat().st_size
            with output_path.open("rb") as handle:
                output_digest = _sha256_file(handle)
            if byte_count <= 0 or not _valid_mp4_signature(output_path):
                raise OSError("empty output")
        except OSError as exc:
            raise ShotProjectError("shot_output_integrity_failed") from exc
        state_shot["status"] = "succeeded"
        state_shot["output"] = {
            "name": output_path.name,
            "bytes": byte_count,
            "sha256": output_digest,
        }
        _persist_state(directory, state, wall_clock)

    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ShotProjectError("shot_project_timeout")
    quick = _quick_request(request)
    quick["timeout_seconds"] = max(1, min(int(math.ceil(remaining)), quick["timeout_seconds"]))
    try:
        quick_result = quick_create_runner(
            service,
            quick,
            request_parent=directory,
            deadline=deadline,
            monotonic=monotonic,
            sleep=sleep,
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        raise ShotProjectError(
            code if isinstance(code, str) and _SAFE_CODE_RE.fullmatch(code) else "shot_quick_create_failed"
        ) from exc
    if not isinstance(quick_result, dict):
        raise ShotProjectError("invalid_shot_quick_create_result")
    return {
        "schema_version": SHOT_PROJECT_SCHEMA_VERSION,
        "project_id": request["project_id"],
        "production_id": request["production"]["id"],
        "request_digest": request_digest,
        "plan": {
            "name": SHOT_PROJECT_PLAN_FILENAME,
            "sha256": plan["plan_sha256"],
        },
        "submitted_tasks": submitted_this_call,
        "resumed": not created,
        "shots": [
            {
                "shot_id": item["shot_id"],
                "status": item["status"],
                "task_id": item["task_id"],
                "output": dict(item["output"]),
            }
            for item in state["shots"]
        ],
        "quick_create": quick_result,
    }


__all__ = [
    "SHOT_PROJECT_COUNT",
    "SHOT_PROJECT_DURATION_SECONDS",
    "SHOT_PROJECT_MAX_REQUEST_BYTES",
    "SHOT_PROJECT_OUTPUT_DURATION_MS",
    "SHOT_PROJECT_PLAN_FILENAME",
    "SHOT_PROJECT_RESOLUTION",
    "SHOT_PROJECT_SCHEMA_VERSION",
    "ShotProjectError",
    "ShotProjectValidationError",
    "load_shot_project_request",
    "run_shot_project",
    "validate_shot_project_request",
]
