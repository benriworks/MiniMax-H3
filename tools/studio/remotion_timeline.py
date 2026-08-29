from __future__ import annotations

"""Verified, atomic local Remotion timeline rendering.

The HTTP/service layer resolves registered artifact IDs to immutable local
files.  This worker repeats the provenance checks, stages fixed filenames in a
private directory, invokes the pinned Remotion renderer through a bounded Node
process, normalizes audio with FFmpeg, and publishes exactly five artifacts.
"""

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import assembly as _assembly
from .assembly import (
    AssemblyError,
    AssemblyToolError,
    _bounded_process,
    _json_probe,
    _probe_duration,
    _sha256_file,
    _streams,
)
from .jobs import JobCancelled
from .remotion_timeline_execution import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    FRAME_RATE,
    IMPLEMENTATION_VERSION,
    PROVIDER,
    REMOTION_FRAME_IMAGE_FORMAT,
    REMOTION_SCRATCH_HEADROOM_DENOMINATOR,
    REMOTION_SCRATCH_HEADROOM_NUMERATOR,
    REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES,
    REMOTION_SCRATCH_POLICY_VERSION,
    REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES,
    REMOTION_SCRATCH_RGBA_BYTES_PER_PIXEL,
    REMOTION_SCRATCH_SAFETY_MARGIN_BYTES,
    REMOTION_SCRATCH_SHARP_STAGING_RESERVE_BYTES,
    REMOTION_VIDEO_CRF,
    SCHEMA_VERSION,
    SHARP_SOURCE_MAX_ASPECT_RATIO,
    SHARP_SOURCE_MAX_SCALED_PIXELS,
    SHARP_SOURCE_MIN_ASPECT_RATIO,
    SHARP_SOURCE_MIN_DIMENSION,
    SOURCE_ENHANCEMENT_POLICY_VERSION,
    TIMING_SOURCE,
    RemotionTimelineError,
    RemotionTimelineToolError,
    RemotionTimelineValidationError,
    compile_remotion_timeline,
    normalize_internal_clips,
    remotion_output_policy,
    remotion_timeline_audit_payload,
    remotion_timeline_cache_key,
)
from .security import (
    SecurityError,
    canonical_json,
    relative_workspace_path,
    validate_identifier,
    workspace_path,
)


PINNED_REMOTION_VERSION = "4.0.517"
COMPOSITION_ID = "MiniMaxH3DetailedTimelineV1"
MAX_SOURCE_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_AGGREGATE_SOURCE_BYTES = 4 * 1024 * 1024 * 1024
MAX_RAW_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
NODE_TIMEOUT_SECONDS = 30 * 60
FFMPEG_TIMEOUT_SECONDS = 10 * 60
_REMOTION_STAGE_CLEANUP_ATTEMPTS = 4
# Four attempts provide a bounded ~1.05 s retry window (0.15 + 0.30 + 0.60)
# for transient Windows sharing violations without delaying a normal cleanup.
_REMOTION_STAGE_CLEANUP_DELAY_SECONDS = 0.15
_SHARP_VISUAL_PRESET = "h3_low_res_sharp_v1"
_SOURCE_ENHANCEMENT_FILTER = (
    "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos:"
    "in_range=auto:out_range=tv,"
    "crop=1080:1920:(in_w-out_w)/2:(in_h-out_h)/2,"
    "setsar=1,unsharp=5:5:0.25:3:3:0,format=yuv420p"
)
_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_REMOTION_PACKAGES = (
    "remotion",
    "@remotion/player",
    "@remotion/renderer",
    "@remotion/bundler",
    "@remotion/transitions",
)
_RUNTIME_ATTESTATION_ALGORITHM = "sha256-node-dependency-closure-v1"
_RUNTIME_ROOT_PACKAGES = tuple(sorted((*_REMOTION_PACKAGES, "playwright")))
_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "remotion-preview.mp4", "kind": "video", "mime": "video/mp4"},
    {
        "filename": "remotion-timeline.json",
        "kind": "document",
        "mime": "application/json",
    },
    {"filename": "render-report.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)

ProgressCallback = Callable[[int, str], None]


def _cancel(cancel_event: Any | None) -> None:
    _assembly._raise_if_cancelled(cancel_event)


def _progress(callback: ProgressCallback | None, value: int, phase: str) -> None:
    if callback is None:
        return
    try:
        callback(value, phase)
    except Exception:
        return


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def _clean_environment() -> dict[str, str]:
    """Pass only OS/process essentials to Node and never renderer/API secrets."""

    allowed = {
        "appdata",
        "comspec",
        "home",
        "homedrive",
        "homepath",
        "lang",
        "localappdata",
        "path",
        "pathext",
        "programdata",
        "programfiles",
        "programfiles(x86)",
        "systemdrive",
        "systemroot",
        "temp",
        "tmp",
        "userprofile",
        "windir",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key.casefold() in allowed and not key.casefold().startswith("remotion_")
    }


def _render_environment(scratch_directory: Path, work_directory: Path) -> dict[str, str]:
    """Confine Remotion and Chromium temporary files to the atomic stage tree."""

    supplied_scratch = Path(scratch_directory)
    work = Path(work_directory).resolve(strict=True)
    if supplied_scratch.is_symlink():
        raise RemotionTimelineToolError(
            "The Remotion scratch directory is unavailable", code="local_remotion_render_failed"
        )
    scratch = supplied_scratch.resolve(strict=True)
    try:
        scratch.relative_to(work)
    except ValueError as exc:
        raise RemotionTimelineToolError(
            "The Remotion scratch directory is unavailable", code="local_remotion_render_failed"
        ) from exc
    if not scratch.is_dir() or any(scratch.iterdir()):
        raise RemotionTimelineToolError(
            "The Remotion scratch directory is unavailable", code="local_remotion_render_failed"
        )
    environment = {
        key: value
        for key, value in _clean_environment().items()
        if key.casefold() not in {"temp", "tmp", "tmpdir"}
    }
    scratch_value = str(scratch)
    environment["TEMP"] = scratch_value
    environment["TMP"] = scratch_value
    environment["TMPDIR"] = scratch_value
    return environment


def _rmtree_onerror(function: Callable[..., Any], path: str, _exc_info: Any) -> None:
    """Retry a read-only Windows file or directory removal after chmod."""

    try:
        # Windows' read-only attribute is cleared by granting owner write
        # access.  The removal function is called again so shutil can finish
        # its normal bottom-up traversal without following the path itself.
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass
    function(path)


def _cleanup_stage_root(stage_root: Path) -> None:
    """Remove a private Remotion stage with bounded retries and residual checks.

    Chromium/FFmpeg can briefly retain a handle to a PNG, raw MP4, or request
    file on Windows after the worker process exits.  ``ignore_errors=True``
    would make that leak invisible, so retry a bounded number of times and
    fail closed if the stage path still exists.  A symlink or non-directory at
    the expected stage path is also treated as a residual rather than removed.
    """

    candidate = Path(stage_root)
    last_error: OSError | None = None
    for attempt in range(_REMOTION_STAGE_CLEANUP_ATTEMPTS):
        # lexists also sees a broken symlink, which must not be mistaken for a
        # successfully removed stage.
        if not os.path.lexists(os.fspath(candidate)):
            return
        try:
            if candidate.is_symlink() or not candidate.is_dir():
                raise OSError("unexpected Remotion stage path")
            shutil.rmtree(candidate, onerror=_rmtree_onerror)
        except (OSError, ValueError) as exc:
            last_error = exc if isinstance(exc, OSError) else OSError(str(exc))
        if not os.path.lexists(os.fspath(candidate)):
            return
        if attempt + 1 < _REMOTION_STAGE_CLEANUP_ATTEMPTS:
            time.sleep(_REMOTION_STAGE_CLEANUP_DELAY_SECONDS * (2**attempt))

    if os.path.lexists(os.fspath(candidate)):
        raise RemotionTimelineToolError(
            "Remotion temporary files could not be cleaned up",
            code="remotion_stage_cleanup_failed",
        ) from last_error


def _scratch_requirement(audit: Mapping[str, Any]) -> dict[str, Any]:
    frames = audit.get("duration_in_frames")
    clips = audit.get("clips")
    if (
        isinstance(frames, bool)
        or not isinstance(frames, int)
        or frames < 1
        or not isinstance(clips, list)
    ):
        raise RemotionTimelineToolError(
            "The Remotion scratch estimate is invalid", code="invalid_worker_result"
        )
    try:
        source_staging_estimate_bytes = sum(
            REMOTION_SCRATCH_SHARP_STAGING_RESERVE_BYTES
            if item.get("visual_preset") == _SHARP_VISUAL_PRESET
            else int(item["source_bytes"])
            for item in clips
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RemotionTimelineToolError(
            "The Remotion scratch estimate is invalid", code="invalid_worker_result"
        ) from exc
    if (
        source_staging_estimate_bytes < 1
        or source_staging_estimate_bytes > MAX_SOURCE_VIDEO_BYTES * len(clips)
    ):
        raise RemotionTimelineToolError(
            "The Remotion scratch estimate is invalid", code="invalid_worker_result"
        )
    rgba_frame_bytes = (
        frames
        * CANVAS_WIDTH
        * CANVAS_HEIGHT
        * REMOTION_SCRATCH_RGBA_BYTES_PER_PIXEL
    )
    png_frame_upper_bound_bytes = (
        rgba_frame_bytes * REMOTION_SCRATCH_HEADROOM_NUMERATOR
        + REMOTION_SCRATCH_HEADROOM_DENOMINATOR
        - 1
    ) // REMOTION_SCRATCH_HEADROOM_DENOMINATOR
    post_stage_required_free_bytes = (
        png_frame_upper_bound_bytes
        + REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES
        + REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES
        + REMOTION_SCRATCH_SAFETY_MARGIN_BYTES
    )
    initial_required_free_bytes = (
        post_stage_required_free_bytes + source_staging_estimate_bytes
    )
    return {
        "policy_version": REMOTION_SCRATCH_POLICY_VERSION,
        "duration_in_frames": frames,
        "png_frame_upper_bound_bytes": png_frame_upper_bound_bytes,
        "source_staging_estimate_bytes": source_staging_estimate_bytes,
        "raw_output_reserve_bytes": REMOTION_SCRATCH_RAW_OUTPUT_RESERVE_BYTES,
        "normalized_output_reserve_bytes": REMOTION_SCRATCH_NORMALIZED_OUTPUT_RESERVE_BYTES,
        "safety_margin_bytes": REMOTION_SCRATCH_SAFETY_MARGIN_BYTES,
        "initial_required_free_bytes": initial_required_free_bytes,
        "post_stage_required_free_bytes": post_stage_required_free_bytes,
        "temporary_directory_scope": "stage_work_directory",
        "cleanup": "recursive_on_all_exit_paths",
    }


def _scratch_space_preflight(directory: Path, audit: Mapping[str, Any]) -> dict[str, Any]:
    requirement = _scratch_requirement(audit)
    try:
        observed_free_bytes = int(shutil.disk_usage(directory).free)
    except (OSError, TypeError, ValueError) as exc:
        raise RemotionTimelineToolError(
            "Remotion scratch space could not be measured",
            code="insufficient_scratch_space",
        ) from exc
    passed = observed_free_bytes >= requirement["initial_required_free_bytes"]
    record = {
        **requirement,
        "initial_observed_free_bytes": observed_free_bytes,
        "initial_passed": passed,
    }
    if not passed:
        required_gib = requirement["initial_required_free_bytes"] / (1024**3)
        observed_gib = observed_free_bytes / (1024**3)
        raise RemotionTimelineToolError(
            f"Remotion PNG rendering requires {required_gib:.2f} GiB free; "
            f"{observed_gib:.2f} GiB is available",
            code="insufficient_scratch_space",
        )
    return record


def _complete_scratch_space_preflight(
    directory: Path,
    audit: Mapping[str, Any],
    initial_record: Mapping[str, Any],
    staged_sources: Path,
) -> dict[str, Any]:
    requirement = _scratch_requirement(audit)
    expected_initial_keys = set(requirement) | {
        "initial_observed_free_bytes",
        "initial_passed",
    }
    if not isinstance(initial_record, Mapping) or set(initial_record) != expected_initial_keys:
        raise RemotionTimelineToolError(
            "The Remotion scratch record is invalid", code="invalid_worker_result"
        )
    try:
        expected_names = {
            f"clip-{index:02d}.mp4" for index in range(int(audit["clip_count"]))
        }
        children = list(staged_sources.iterdir())
        if {child.name for child in children} != expected_names:
            raise OSError("unexpected staged source set")
        actual_staged_source_bytes = 0
        for child in children:
            if child.is_symlink() or not child.is_file():
                raise OSError("invalid staged source")
            actual_staged_source_bytes += child.stat().st_size
        post_stage_observed_free_bytes = int(shutil.disk_usage(directory).free)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise RemotionTimelineToolError(
            "Remotion staged scratch space could not be measured",
            code="insufficient_scratch_space",
        ) from exc
    passed = post_stage_observed_free_bytes >= requirement["post_stage_required_free_bytes"]
    record = {
        **dict(initial_record),
        "actual_staged_source_bytes": actual_staged_source_bytes,
        "post_stage_observed_free_bytes": post_stage_observed_free_bytes,
        "post_stage_passed": passed,
    }
    if not passed:
        required_gib = requirement["post_stage_required_free_bytes"] / (1024**3)
        observed_gib = post_stage_observed_free_bytes / (1024**3)
        raise RemotionTimelineToolError(
            f"Remotion PNG rendering requires {required_gib:.2f} GiB free after staging; "
            f"{observed_gib:.2f} GiB is available",
            code="insufficient_scratch_space",
        )
    return record


def _validated_scratch_record(
    value: Any, audit: Mapping[str, Any]
) -> dict[str, Any]:
    requirement = _scratch_requirement(audit)
    expected_keys = set(requirement) | {
        "initial_observed_free_bytes",
        "initial_passed",
        "actual_staged_source_bytes",
        "post_stage_observed_free_bytes",
        "post_stage_passed",
        "node_containment_attested",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise RemotionTimelineToolError(
            "The Remotion scratch record is invalid", code="invalid_worker_result"
        )
    initial_observed = value.get("initial_observed_free_bytes")
    actual_staged = value.get("actual_staged_source_bytes")
    post_stage_observed = value.get("post_stage_observed_free_bytes")
    if (
        any(value.get(key) != expected for key, expected in requirement.items())
        or isinstance(initial_observed, bool)
        or not isinstance(initial_observed, int)
        or initial_observed < requirement["initial_required_free_bytes"]
        or value.get("initial_passed") is not True
        or isinstance(actual_staged, bool)
        or not isinstance(actual_staged, int)
        or not 0 < actual_staged <= MAX_SOURCE_VIDEO_BYTES * len(audit["clips"])
        or isinstance(post_stage_observed, bool)
        or not isinstance(post_stage_observed, int)
        or post_stage_observed < requirement["post_stage_required_free_bytes"]
        or value.get("post_stage_passed") is not True
        or value.get("node_containment_attested") is not True
    ):
        raise RemotionTimelineToolError(
            "The Remotion scratch record is invalid", code="invalid_worker_result"
        )
    return dict(value)


def _has_symlink_component(workspace: Path, candidate: str | Path) -> bool:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    lexical = supplied if supplied.is_absolute() else root / supplied
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


def _tree_contains_symlink(directory: Path) -> bool:
    try:
        return any(path.is_symlink() for path in directory.rglob("*"))
    except OSError:
        return True


def _safe_output_root(workspace: Path, run_id: str, cache_key: str) -> Path:
    validate_identifier(run_id, label="run id")
    if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
        raise RemotionTimelineValidationError("cache_key is invalid", code="invalid_cache_key")
    lexical_stage = workspace / "outputs" / "studio" / "runs" / run_id / "remotion_timeline"
    lexical_cache = lexical_stage / cache_key
    if _has_symlink_component(workspace, lexical_stage) or _has_symlink_component(
        workspace, lexical_cache
    ):
        raise RemotionTimelineValidationError(
            "Remotion output path must not contain symlinks", code="unsafe_output_path"
        )
    stage = workspace_path(workspace, lexical_stage, must_exist=False)
    cache = workspace_path(workspace, lexical_cache, must_exist=False)
    if stage.exists() and (stage.is_symlink() or not stage.is_dir()):
        raise RemotionTimelineValidationError(
            "Remotion output path is unsafe", code="unsafe_output_path"
        )
    stage.mkdir(parents=True, exist_ok=True)
    if cache.exists() and (cache.is_symlink() or not cache.is_dir()):
        raise RemotionTimelineValidationError(
            "Remotion cache path is unsafe", code="unsafe_output_path"
        )
    return cache


def _safe_source(workspace: Path, value: str | Path, *, label: str) -> Path:
    try:
        path = workspace_path(workspace, value, must_exist=True)
    except (SecurityError, OSError, RuntimeError) as exc:
        raise RemotionTimelineValidationError(
            f"{label} is unavailable", code="source_not_available"
        ) from exc
    if _has_symlink_component(workspace, value) or path.is_symlink() or not path.is_file():
        raise RemotionTimelineValidationError(
            f"{label} is not a safe local file", code="source_not_available"
        )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RemotionTimelineValidationError(
            f"{label} is unavailable", code="source_not_available"
        ) from exc
    if size < 1 or size > MAX_SOURCE_VIDEO_BYTES:
        raise RemotionTimelineValidationError(
            f"{label} size is unsupported", code="source_size_invalid"
        )
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise RemotionTimelineError("Remotion metadata is too large", code="metadata_too_large")
    partial = path.with_name(f".{path.name}.partial")
    partial.write_bytes(data)
    os.replace(partial, path)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    value = _read_json(path)
    if value is None or not isinstance(value.get("manifest_sha256"), str):
        return None
    body = dict(value)
    digest = body.pop("manifest_sha256")
    if not isinstance(digest, str) or _manifest_digest(body) != digest.upper():
        return None
    return value


def _public_identity(value: Mapping[str, Any], *, label: str) -> dict[str, str]:
    version, digest = value.get("version"), value.get("sha256")
    if (
        not isinstance(version, str)
        or not version
        or len(version) > 512
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest)
    ):
        raise RemotionTimelineToolError(
            f"{label} identity is invalid", code="local_worker_unavailable"
        )
    return {"version": version, "sha256": digest.upper()}


def _file_identity(path: Path, *, version: str) -> dict[str, str]:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        return {"version": version, "sha256": _sha256_file(path)}
    except OSError as exc:
        raise RemotionTimelineToolError(
            "A pinned Remotion file is unavailable", code="local_worker_unavailable"
        ) from exc


def _node_identity(executable: str, *, cancel_event: Any | None) -> dict[str, str]:
    resolved = Path(executable).resolve(strict=True)
    try:
        output = _bounded_process(
            [str(resolved), "--version"],
            cwd=resolved.parent,
            timeout=30,
            label="Node.js version",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
    except AssemblyError as exc:
        raise RemotionTimelineToolError(
            "Node.js identity is unavailable", code="local_worker_unavailable"
        ) from exc
    version = output.decode("utf-8", errors="replace").splitlines()[0].strip()
    if not version or len(version) > 512:
        raise RemotionTimelineToolError(
            "Node.js identity is unavailable", code="local_worker_unavailable"
        )
    return {"version": version, "sha256": _sha256_file(resolved)}


def _package_path(workspace: Path, name: str) -> Path:
    return workspace_path(
        workspace,
        Path("studio/node_modules") / Path(*name.split("/")) / "package.json",
        must_exist=True,
    )


def _runtime_attestation_identity(doctor: Any) -> dict[str, str]:
    attestation = doctor.get("runtime_attestation") if isinstance(doctor, dict) else None
    expected_keys = {
        "schema_version",
        "algorithm",
        "root_packages",
        "closure_package_count",
        "file_count",
        "total_bytes",
        "tree_sha256",
    }
    if (
        not isinstance(attestation, dict)
        or set(attestation) != expected_keys
        or attestation.get("schema_version") != 1
        or attestation.get("algorithm") != _RUNTIME_ATTESTATION_ALGORITHM
        or attestation.get("root_packages") != list(_RUNTIME_ROOT_PACKAGES)
        or type(attestation.get("closure_package_count")) is not int
        or not len(_RUNTIME_ROOT_PACKAGES)
        <= attestation["closure_package_count"]
        <= 10_000
        or type(attestation.get("file_count")) is not int
        or not len(_RUNTIME_ROOT_PACKAGES) <= attestation["file_count"] <= 1_000_000
        or type(attestation.get("total_bytes")) is not int
        or not 1 <= attestation["total_bytes"] <= 16 * 1024 * 1024 * 1024
        or not isinstance(attestation.get("tree_sha256"), str)
        or not _SHA256_RE.fullmatch(attestation["tree_sha256"])
    ):
        raise RemotionTimelineToolError(
            "Pinned Remotion runtime attestation is invalid", code="local_worker_unavailable"
        )
    version = (
        f"{_RUNTIME_ATTESTATION_ALGORITHM};"
        f"packages={attestation['closure_package_count']};"
        f"files={attestation['file_count']};bytes={attestation['total_bytes']}"
    )
    return {"version": version, "sha256": attestation["tree_sha256"]}


def _resolve_runtime(
    workspace: Path,
    *,
    node: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
) -> tuple[str, str, str, Path, Path, dict[str, Any], dict[str, dict[str, str]]]:
    _cancel(cancel_event)
    try:
        node_executable = _assembly._find_tool("node", node)
        ffmpeg_executable = _assembly._find_tool("ffmpeg", ffmpeg)
        ffprobe_executable = _assembly._find_tool("ffprobe", ffprobe)
        render_script = workspace_path(workspace, "tools/studio/remotion_render.mjs", must_exist=True)
        doctor_script = workspace_path(workspace, "tools/studio/remotion_doctor.mjs", must_exist=True)
        entry_point = workspace_path(workspace, "studio/src/remotion/entry.tsx", must_exist=True)
        composition_source = workspace_path(
            workspace, "studio/src/remotion/TimelineComposition.tsx", must_exist=True
        )
        model_source = workspace_path(workspace, "studio/src/remotion/model.ts", must_exist=True)
        package_lock = workspace_path(workspace, "studio/package-lock.json", must_exist=True)
        studio_package = workspace_path(workspace, "studio/package.json", must_exist=True)
    except (AssemblyError, SecurityError, OSError) as exc:
        raise RemotionTimelineToolError(
            "The local Remotion runtime is unavailable", code="local_worker_unavailable"
        ) from exc
    try:
        output = _bounded_process(
            [node_executable, str(doctor_script)],
            cwd=workspace,
            timeout=60,
            label="Remotion doctor",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
        doctor = json.loads(output.decode("utf-8"))
    except JobCancelled:
        raise
    except (AssemblyError, UnicodeError, json.JSONDecodeError) as exc:
        raise RemotionTimelineToolError(
            "Pinned Remotion and Playwright Chromium are unavailable. Run setup-studio.ps1.",
            code="local_worker_unavailable",
        ) from exc
    runtime_attestation_identity = _runtime_attestation_identity(doctor)
    packages = doctor.get("remotion_packages") if isinstance(doctor, dict) else None
    browser_value = doctor.get("chromium_executable_path") if isinstance(doctor, dict) else None
    browser_version = doctor.get("chromium_version") if isinstance(doctor, dict) else None
    playwright_version = doctor.get("playwright_version") if isinstance(doctor, dict) else None
    if (
        doctor.get("schema_version") != 1
        or not isinstance(packages, dict)
        or set(packages) != set(_REMOTION_PACKAGES)
        or any(packages.get(name) != PINNED_REMOTION_VERSION for name in _REMOTION_PACKAGES)
        or not isinstance(browser_value, str)
        or not isinstance(browser_version, str)
        or not browser_version
        or not isinstance(playwright_version, str)
        or not playwright_version
    ):
        raise RemotionTimelineToolError(
            "Pinned Remotion runtime identity is invalid", code="local_worker_unavailable"
        )
    try:
        browser = Path(browser_value).resolve(strict=True)
        if browser.is_symlink() or not browser.is_file():
            raise OSError
        ffmpeg_identity = _public_identity(
            _assembly._tool_identity("ffmpeg", ffmpeg_executable, cancel_event=cancel_event),
            label="ffmpeg",
        )
        ffprobe_identity = _public_identity(
            _assembly._tool_identity("ffprobe", ffprobe_executable, cancel_event=cancel_event),
            label="ffprobe",
        )
        identity: dict[str, dict[str, str]] = {
            "node": _node_identity(node_executable, cancel_event=cancel_event),
            "ffmpeg": ffmpeg_identity,
            "ffprobe": ffprobe_identity,
            "chromium": _file_identity(browser, version=browser_version),
            "playwright": _file_identity(
                workspace_path(workspace, "studio/node_modules/playwright/package.json", must_exist=True),
                version=playwright_version,
            ),
            "studio_package": _file_identity(studio_package, version=IMPLEMENTATION_VERSION),
            "package_lock": _file_identity(package_lock, version=IMPLEMENTATION_VERSION),
            "entry_point": _file_identity(entry_point, version=IMPLEMENTATION_VERSION),
            "composition_source": _file_identity(
                composition_source, version=IMPLEMENTATION_VERSION
            ),
            "model_source": _file_identity(model_source, version=IMPLEMENTATION_VERSION),
            "render_script": _file_identity(render_script, version=IMPLEMENTATION_VERSION),
            "doctor_script": _file_identity(doctor_script, version=IMPLEMENTATION_VERSION),
            "runtime_dependency_closure": runtime_attestation_identity,
        }
        for name in _REMOTION_PACKAGES:
            identity[f"package:{name}"] = _file_identity(
                _package_path(workspace, name), version=PINNED_REMOTION_VERSION
            )
    except (AssemblyError, SecurityError, OSError) as exc:
        raise RemotionTimelineToolError(
            "The local Remotion tool identity is unavailable", code="local_worker_unavailable"
        ) from exc
    return (
        node_executable,
        ffmpeg_executable,
        ffprobe_executable,
        render_script,
        entry_point,
        {
            "browser": browser,
            "doctor": doctor,
            "doctor_script": doctor_script,
            "runtime_attestation_identity": runtime_attestation_identity,
            "source_files": {
                "entry_point": entry_point,
                "composition_source": composition_source,
                "model_source": model_source,
                "render_script": render_script,
                "doctor_script": doctor_script,
            },
        },
        identity,
    )


def _recheck_runtime_attestation(
    workspace: Path,
    *,
    node_executable: str,
    doctor_script: Path,
    expected_identity: Mapping[str, str],
    cancel_event: Any | None,
) -> None:
    try:
        output = _bounded_process(
            [node_executable, str(doctor_script), "--verify-attestation-only"],
            cwd=workspace,
            timeout=60,
            label="Remotion runtime attestation",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
        doctor = json.loads(output.decode("utf-8"))
        identity = _runtime_attestation_identity(doctor)
    except JobCancelled:
        raise
    except (AssemblyError, UnicodeError, json.JSONDecodeError, RemotionTimelineToolError) as exc:
        raise RemotionTimelineError(
            "The Remotion runtime changed during rendering", code="tool_changed"
        ) from exc
    if identity != dict(expected_identity):
        raise RemotionTimelineError(
            "The Remotion runtime changed during rendering", code="tool_changed"
        )


def resolve_remotion_tool_identity(
    workspace: Path,
    *,
    node: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
) -> dict[str, dict[str, str]]:
    root = Path(workspace).resolve(strict=True)
    return _resolve_runtime(
        root,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )[-1]


def _source_duration_ms(probe: Mapping[str, Any], *, label: str) -> int:
    try:
        streams = _streams(probe)
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        if len(videos) != 1 or any(
            stream.get("codec_type") not in {"video", "audio"} for stream in streams
        ):
            raise RemotionTimelineValidationError(
                f"{label} must contain exactly one video stream", code="invalid_source_media"
            )
        video = videos[0]
        width, height = video.get("width"), video.get("height")
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or width < 1
            or isinstance(height, bool)
            or not isinstance(height, int)
            or height < 1
            or width > 16384
            or height > 16384
            or width * height > 64 * 1024 * 1024
        ):
            raise RemotionTimelineValidationError(
                f"{label} dimensions are unsupported", code="invalid_source_media"
            )
        return int(round(_probe_duration(probe, stream_type="video") * 1000))
    except RemotionTimelineError:
        raise
    except AssemblyError as exc:
        raise RemotionTimelineValidationError(
            f"{label} duration is unavailable", code="invalid_source_media"
        ) from exc


def _prepare_clips(
    workspace: Path,
    clips: Sequence[Mapping[str, Any]],
    *,
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = normalize_internal_clips(clips)
    prepared: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []
    aggregate = 0
    for index, item in enumerate(normalized):
        _cancel(cancel_event)
        source = _safe_source(workspace, item["source_path"], label=f"clips[{index}].source_path")
        stat = source.stat()
        digest = _sha256_file(source)
        if stat.st_size != item["source_bytes"] or digest != item["source_sha256"]:
            raise RemotionTimelineValidationError(
                f"clips[{index}] source hash does not match its record", code="source_changed"
            )
        aggregate += stat.st_size
        if aggregate > MAX_AGGREGATE_SOURCE_BYTES:
            raise RemotionTimelineValidationError(
                "aggregate source size is unsupported", code="source_size_invalid"
            )
        try:
            probe = _json_probe(ffprobe, source, cwd=workspace, cancel_event=cancel_event)
        except AssemblyError as exc:
            raise RemotionTimelineValidationError(
                f"clips[{index}] could not be inspected", code="invalid_source_media"
            ) from exc
        source_duration_ms = _source_duration_ms(probe, label=f"clips[{index}]")
        if item["end_ms"] > source_duration_ms:
            raise RemotionTimelineValidationError(
                f"clips[{index}].end_ms exceeds source duration", code="trim_out_of_range"
            )
        prepared.append(
            {
                **item,
                "source_path": relative_workspace_path(workspace, source),
                "source_bytes": stat.st_size,
                "source_sha256": digest,
            }
        )
        probes.append(probe)
    return prepared, probes


def _assert_source_unchanged(workspace: Path, item: Mapping[str, Any], *, label: str) -> Path:
    source = _safe_source(workspace, str(item["source_path"]), label=label)
    if source.stat().st_size != item["source_bytes"] or _sha256_file(source) != item["source_sha256"]:
        raise RemotionTimelineError(f"{label} changed during rendering", code="input_changed")
    return source


def _source_enhancement_plans(
    clips: Sequence[Mapping[str, Any]],
    probes: Sequence[Mapping[str, Any]],
    compiled: Mapping[str, Any],
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for index, (item, probe, resolved) in enumerate(
        zip(clips, probes, compiled["clips"], strict=True)
    ):
        try:
            videos = [stream for stream in _streams(probe) if stream.get("codec_type") == "video"]
        except AssemblyError as exc:
            raise RemotionTimelineValidationError(
                f"clips[{index}] media streams are invalid", code="invalid_source_media"
            ) from exc
        if len(videos) != 1:
            raise RemotionTimelineValidationError(
                f"clips[{index}] must contain exactly one video stream",
                code="invalid_source_media",
            )
        width = videos[0].get("width")
        height = videos[0].get("height")
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or isinstance(height, bool)
            or not isinstance(height, int)
        ):
            raise RemotionTimelineValidationError(
                f"clips[{index}] dimensions are invalid", code="invalid_source_media"
            )
        preset = item["visual_preset"]
        enhanced = preset == _SHARP_VISUAL_PRESET
        aspect_ratio = width / height
        scale_factor = max(CANVAS_WIDTH / width, CANVAS_HEIGHT / height)
        scaled_width = math.ceil(width * scale_factor)
        scaled_height = math.ceil(height * scale_factor)
        if enhanced and (
            width >= CANVAS_WIDTH
            or height >= CANVAS_HEIGHT
            or width < SHARP_SOURCE_MIN_DIMENSION
            or height < SHARP_SOURCE_MIN_DIMENSION
            or aspect_ratio < SHARP_SOURCE_MIN_ASPECT_RATIO
            or aspect_ratio > SHARP_SOURCE_MAX_ASPECT_RATIO
            or scaled_width * scaled_height > SHARP_SOURCE_MAX_SCALED_PIXELS
        ):
            raise RemotionTimelineValidationError(
                f"clips[{index}].visual_preset requires a low-resolution portrait source",
                code="visual_preset_incompatible",
            )
        plans.append(
            {
                "clip_index": index,
                "visual_preset": preset,
                "policy_version": SOURCE_ENHANCEMENT_POLICY_VERSION,
                "mode": (
                    "lanczos_cover_luma_unsharp"
                    if enhanced
                    else "source_preserved"
                ),
                "source_width": width,
                "source_height": height,
                "planned_scaled_width": scaled_width if enhanced else None,
                "planned_scaled_height": scaled_height if enhanced else None,
                "trimmed_to_used_frames": enhanced,
                "trim_before_frame": resolved["trim_before_frame"],
                "duration_in_frames": resolved["duration_in_frames"],
            }
        )
    return plans


def _validate_enhanced_source_probe(
    probe: Mapping[str, Any], *, expected_frames: int, label: str
) -> None:
    try:
        streams = _streams(probe)
    except AssemblyError as exc:
        raise RemotionTimelineToolError(
            f"{label} produced invalid media", code="invalid_staged_media"
        ) from exc
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) > 1 or len(streams) != len(videos) + len(audios):
        raise RemotionTimelineToolError(
            f"{label} produced invalid streams", code="invalid_staged_media"
        )
    video = videos[0]
    if (
        video.get("codec_name") != "h264"
        or video.get("pix_fmt") != "yuv420p"
        or video.get("width") != CANVAS_WIDTH
        or video.get("height") != CANVAS_HEIGHT
        or any(
            rate is None or abs(rate - FRAME_RATE) > 0.01
            for rate in (
                _fraction(video.get("r_frame_rate")),
                _fraction(video.get("avg_frame_rate")),
            )
        )
    ):
        raise RemotionTimelineToolError(
            f"{label} does not match the fixed video policy",
            code="invalid_staged_media",
        )
    if audios and (
        audios[0].get("codec_name") != "aac"
        or str(audios[0].get("sample_rate")) != "48000"
        or audios[0].get("channels") != 2
    ):
        raise RemotionTimelineToolError(
            f"{label} does not match the fixed audio policy",
            code="invalid_staged_media",
        )
    try:
        duration_ms = int(round(_probe_duration(probe, stream_type="video") * 1000))
    except AssemblyError as exc:
        raise RemotionTimelineToolError(
            f"{label} duration is unavailable", code="invalid_staged_media"
        ) from exc
    expected_ms = expected_frames * 1000 / FRAME_RATE
    if abs(duration_ms - expected_ms) > (1000 / FRAME_RATE) + 2:
        raise RemotionTimelineToolError(
            f"{label} duration is invalid", code="invalid_staged_media"
        )


def _stage_sources(
    workspace: Path,
    public_directory: Path,
    clips: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
    *,
    ffmpeg: str,
    ffprobe: str,
    cancel_event: Any | None,
) -> None:
    for index, (item, plan) in enumerate(zip(clips, plans, strict=True)):
        _cancel(cancel_event)
        source = _assert_source_unchanged(workspace, item, label=f"clips[{index}]")
        destination = public_directory / f"clip-{index:02d}.mp4"
        if plan["mode"] == "source_preserved":
            shutil.copyfile(source, destination)
            _assert_source_unchanged(workspace, item, label=f"clips[{index}]")
            if (
                destination.stat().st_size != item["source_bytes"]
                or _sha256_file(destination) != item["source_sha256"]
            ):
                raise RemotionTimelineError(
                    f"clips[{index}] staging failed integrity verification",
                    code="input_changed",
                )
            continue

        partial = destination.with_name(f"{destination.name}.partial")
        trim_start_seconds = plan["trim_before_frame"] / FRAME_RATE
        duration_seconds = plan["duration_in_frames"] / FRAME_RATE
        source_filter = (
            f"setpts=PTS-STARTPTS,{_SOURCE_ENHANCEMENT_FILTER},"
            f"fps={FRAME_RATE},tpad=stop_mode=clone:stop_duration=1,"
            f"trim=end_frame={plan['duration_in_frames']},"
            f"setpts=N/({FRAME_RATE}*TB)"
        )
        try:
            _bounded_process(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{trim_start_seconds:.6f}",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                    "-sn",
                    "-dn",
                    "-vf",
                    source_filter,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(REMOTION_VIDEO_CRF),
                    "-threads",
                    "2",
                    "-r",
                    str(FRAME_RATE),
                    "-fps_mode",
                    "cfr",
                    "-frames:v",
                    str(plan["duration_in_frames"]),
                    "-pix_fmt",
                    "yuv420p",
                    "-color_range",
                    "tv",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-t",
                    f"{duration_seconds:.6f}",
                    "-movflags",
                    "+faststart",
                    "-fs",
                    str(MAX_SOURCE_VIDEO_BYTES),
                    "-f",
                    "mp4",
                    partial.name,
                ],
                cwd=public_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="Remotion source enhancement",
                cancel_event=cancel_event,
                environment=_clean_environment(),
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise RemotionTimelineToolError(
                "The fixed Remotion source enhancement failed",
                code="local_ffmpeg_failed",
            ) from exc
        _assert_source_unchanged(workspace, item, label=f"clips[{index}]")
        if (
            partial.is_symlink()
            or not partial.is_file()
            or not 0 < partial.stat().st_size <= MAX_SOURCE_VIDEO_BYTES
        ):
            raise RemotionTimelineToolError(
                "Source enhancement produced invalid media",
                code="invalid_staged_media",
            )
        try:
            staged_probe = _json_probe(
                ffprobe, partial, cwd=public_directory, cancel_event=cancel_event
            )
        except AssemblyError as exc:
            raise RemotionTimelineToolError(
                "Source enhancement could not be inspected",
                code="invalid_staged_media",
            ) from exc
        _validate_enhanced_source_probe(
            staged_probe,
            expected_frames=plan["duration_in_frames"],
            label=f"clips[{index}] source enhancement",
        )
        os.replace(partial, destination)
        if destination.is_symlink() or not destination.is_file():
            raise RemotionTimelineError(
                f"clips[{index}] staging failed integrity verification",
                code="invalid_staged_media",
            )


def _input_props(
    clips: Sequence[Mapping[str, Any]],
    compiled: Mapping[str, Any],
    plans: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for index, (source, resolved, plan) in enumerate(
        zip(clips, compiled["clips"], plans, strict=True)
    ):
        transition = resolved["transition_to_next"]
        overlay = resolved["overlay"]
        staged = plan["trimmed_to_used_frames"]
        values.append(
            {
                "src": f"clip-{index:02d}.mp4",
                "startMs": 0 if staged else source["start_ms"],
                "endMs": (
                    source["end_ms"] - source["start_ms"]
                    if staged
                    else source["end_ms"]
                ),
                "trimBeforeFrame": 0 if staged else resolved["trim_before_frame"],
                "trimAfterFrame": (
                    resolved["duration_in_frames"]
                    if staged
                    else resolved["trim_after_frame"]
                ),
                "durationInFrames": resolved["duration_in_frames"],
                "volumePercent": resolved["volume_percent"],
                "transitionToNext": None
                if transition is None
                else {
                    "type": "fade",
                    "durationMs": transition["duration_ms"],
                    "durationInFrames": transition["duration_in_frames"],
                },
                "overlay": None
                if overlay is None
                else {
                    "text": overlay["text"],
                    "startMs": overlay["start_ms"],
                    "endMs": overlay["end_ms"],
                    "startFrame": overlay["start_frame"],
                    "endFrame": overlay["start_frame"] + overlay["duration_in_frames"],
                    "position": overlay["position"],
                    "stylePreset": overlay["style_preset"],
                },
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "fps": FRAME_RATE,
        "durationInFrames": compiled["duration_in_frames"],
        "clips": values,
    }


def _fraction(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        result = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _validate_output_probe(probe: Mapping[str, Any], *, expected_frames: int) -> int:
    format_data = probe.get("format")
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if not isinstance(format_name, str) or "mp4" not in {
        part.strip().casefold() for part in format_name.split(",")
    }:
        raise RemotionTimelineError("Remotion output is not MP4", code="invalid_output_media")
    try:
        streams = _streams(probe)
    except AssemblyError as exc:
        raise RemotionTimelineError("Remotion output streams are invalid", code="invalid_output_media") from exc
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(streams) != 2 or len(videos) != 1 or len(audios) != 1:
        raise RemotionTimelineError(
            "Remotion output must contain one video and one audio stream", code="invalid_output_media"
        )
    video, audio = videos[0], audios[0]
    if (
        video.get("codec_name") != "h264"
        or video.get("pix_fmt") != "yuv420p"
        or video.get("width") != CANVAS_WIDTH
        or video.get("height") != CANVAS_HEIGHT
        or any(
            rate is None or abs(rate - FRAME_RATE) > 0.01
            for rate in (_fraction(video.get("r_frame_rate")), _fraction(video.get("avg_frame_rate")))
        )
        or audio.get("codec_name") != "aac"
        or str(audio.get("sample_rate")) != "48000"
        or audio.get("channels") != 2
    ):
        raise RemotionTimelineError(
            "Remotion output media policy is invalid", code="invalid_output_media"
        )
    try:
        duration_ms = int(round(_probe_duration(probe, stream_type="video") * 1000))
    except AssemblyError as exc:
        raise RemotionTimelineError(
            "Remotion output duration is unavailable", code="invalid_output_media"
        ) from exc
    expected_ms = expected_frames * 1000 / FRAME_RATE
    if abs(duration_ms - expected_ms) > (1000 / FRAME_RATE) + 2:
        raise RemotionTimelineError(
            "Remotion output duration is invalid", code="invalid_output_media"
        )
    return duration_ms


def _output_policy() -> dict[str, Any]:
    return remotion_output_policy()


def _resource_policy() -> dict[str, Any]:
    return {
        "render_concurrency": 1,
        "disallow_parallel_encoding": True,
        "max_source_bytes": MAX_SOURCE_VIDEO_BYTES,
        "max_aggregate_source_bytes": MAX_AGGREGATE_SOURCE_BYTES,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
        "render_scratch": _output_policy()["render_scratch"],
    }


def _timeline_document(
    *, production_id: str, run_id: str, cache_key: str, clips: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    public_clips = []
    for item in clips:
        public_clips.append(
            {
                "video_artifact_id": item["video_artifact_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "volume_percent": item["volume_percent"],
                "visual_preset": item["visual_preset"],
                "transition_to_next": item["transition_to_next"],
                "overlay": item["overlay"],
                "source_bytes": item["source_bytes"],
                "source_sha256": item["source_sha256"],
            }
        )
    compiled = compile_remotion_timeline(clips)
    return {
        "schema_version": SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "composition_id": COMPOSITION_ID,
        "recipe": {"schema_version": SCHEMA_VERSION, "clips": public_clips},
        "compiled": compiled,
        "output_policy": _output_policy(),
        "content_policy": {
            "recipe_contains_overlay_text": any(
                item["overlay"] is not None for item in public_clips
            ),
            "source_paths_recorded": False,
        },
    }


def _render_report(
    *,
    audit: Mapping[str, Any],
    node_result: Mapping[str, Any],
    scratch_space: Mapping[str, Any],
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "composition_id",
        "duration_in_frames",
        "clip_count",
        "transition_count",
        "overlay_count",
        "remotion_packages",
        "concurrency",
        "disallow_parallel_encoding",
        "silent_audio_fallback",
        "image_format",
        "video_crf",
        "x264_preset",
        "scratch_directory_attested",
        "max_progress_percent",
    }
    if set(node_result) != expected_keys:
        raise RemotionTimelineToolError(
            "The Remotion renderer returned invalid metadata", code="invalid_worker_result"
        )
    packages = node_result.get("remotion_packages")
    if (
        node_result.get("schema_version") != 1
        or node_result.get("composition_id") != COMPOSITION_ID
        or node_result.get("duration_in_frames") != audit["duration_in_frames"]
        or node_result.get("clip_count") != audit["clip_count"]
        or node_result.get("concurrency") != 1
        or node_result.get("disallow_parallel_encoding") is not True
        or node_result.get("silent_audio_fallback") is not True
        or node_result.get("image_format") != REMOTION_FRAME_IMAGE_FORMAT
        or node_result.get("video_crf") != REMOTION_VIDEO_CRF
        or node_result.get("x264_preset") != "medium"
        or node_result.get("scratch_directory_attested") is not True
        or not isinstance(node_result.get("max_progress_percent"), int)
        or not 0 <= node_result["max_progress_percent"] <= 100
        or not isinstance(packages, dict)
        or set(packages) != set(_REMOTION_PACKAGES)
        or any(packages.get(name) != PINNED_REMOTION_VERSION for name in _REMOTION_PACKAGES)
    ):
        raise RemotionTimelineToolError(
            "The Remotion renderer returned invalid metadata", code="invalid_worker_result"
        )
    transition_count = sum(
        item.get("transition_to_next") is not None for item in audit["clips"]
    )
    overlay_count = sum(item.get("overlay") is not None for item in audit["clips"])
    if node_result.get("transition_count") != transition_count or node_result.get(
        "overlay_count"
    ) != overlay_count:
        raise RemotionTimelineToolError(
            "The Remotion renderer returned mismatched metadata", code="invalid_worker_result"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "provider": PROVIDER,
        "render": dict(audit),
        "renderer": dict(node_result),
        "content_policy": {
            "raw_overlay_text_in_report": False,
            "source_paths_in_report": False,
            "recipe_contains_overlay_text": overlay_count > 0,
        },
        "output_policy": _output_policy(),
        "resource_policy": _resource_policy(),
        "scratch_space": _validated_scratch_record(scratch_space, audit),
    }


def _artifact_record(
    workspace: Path, directory: Path, spec: Mapping[str, str]
) -> dict[str, Any]:
    path = directory / spec["filename"]
    stat = path.stat()
    relative = relative_workspace_path(workspace, path)
    return {
        "kind": spec["kind"],
        "path": relative,
        "rel_path": relative,
        "name": spec["filename"],
        "bytes": stat.st_size,
        "sha256": _sha256_file(path),
        "mime": spec["mime"],
        "media_type": spec["mime"],
        "origin": "studio",
        "version": IMPLEMENTATION_VERSION,
        "available": True,
        "is_heavy": stat.st_size > 10 * 1024 * 1024,
    }


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    audit: Mapping[str, Any],
    duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    output_probe: Mapping[str, Any],
    scratch_space: Mapping[str, Any],
    stage: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _ARTIFACT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = stage / spec["filename"]
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "cache_key": cache_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "duration_ms": duration_ms,
        "has_audio": True,
        "render": dict(audit),
        "tool_identity": {key: dict(value) for key, value in tool_identity.items()},
        "output_policy": _output_policy(),
        "resource_policy": _resource_policy(),
        "scratch_space": _validated_scratch_record(scratch_space, audit),
        "media": {"remotion_preview": dict(output_probe)},
        "files": files,
    }
    body["manifest_sha256"] = _manifest_digest(body)
    return body


def _result(
    workspace: Path,
    directory: Path,
    manifest: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "cache_key": manifest["cache_key"],
        "cache_hit": cache_hit,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "has_audio": True,
        "output_directory": relative_workspace_path(workspace, directory),
    }


def _validate_cache(
    workspace: Path,
    directory: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
    tool_identity: Mapping[str, Mapping[str, str]],
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _cancel(cancel_event)
    if not directory.is_dir() or directory.is_symlink() or _tree_contains_symlink(directory):
        return None
    manifest = _read_manifest(directory / "manifest.json")
    timeline = _read_json(directory / "remotion-timeline.json")
    report = _read_json(directory / "render-report.json")
    probe_document = _read_json(directory / "ffprobe.json")
    expected_timeline = _timeline_document(
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
    )
    if manifest is None or timeline != expected_timeline or report is None or probe_document is None:
        return None
    expected_manifest_keys = {
        "schema_version",
        "implementation_version",
        "production_id",
        "run_id",
        "cache_key",
        "provider",
        "provider_task_id",
        "actual_cost",
        "timing_source",
        "duration_ms",
        "has_audio",
        "render",
        "tool_identity",
        "output_policy",
        "resource_policy",
        "scratch_space",
        "media",
        "files",
        "manifest_sha256",
    }
    expected_probe_keys = {
        "schema_version",
        "implementation_version",
        "timing_source",
        "remotion_preview",
    }
    try:
        expected_report = _render_report(
            audit=audit,
            node_result=report.get("renderer") if isinstance(report.get("renderer"), dict) else {},
            scratch_space=report.get("scratch_space"),
        )
    except RemotionTimelineError:
        return None
    if (
        set(manifest) != expected_manifest_keys
        or set(probe_document) != expected_probe_keys
        or report != expected_report
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("implementation_version") != IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("cache_key") != cache_key
        or manifest.get("provider") != PROVIDER
        or manifest.get("provider_task_id") is not None
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != TIMING_SOURCE
        or manifest.get("has_audio") is not True
        or manifest.get("render") != dict(audit)
        or manifest.get("tool_identity") != {
            key: dict(value) for key, value in tool_identity.items()
        }
        or manifest.get("output_policy") != _output_policy()
        or manifest.get("resource_policy") != _resource_policy()
        or manifest.get("scratch_space") != report.get("scratch_space")
        or report.get("render") != dict(audit)
        or report.get("content_policy")
        != {
            "raw_overlay_text_in_report": False,
            "source_paths_in_report": False,
            "recipe_contains_overlay_text": any(
                item.get("overlay") is not None for item in audit["clips"]
            ),
        }
        or probe_document.get("schema_version") != SCHEMA_VERSION
        or probe_document.get("implementation_version") != IMPLEMENTATION_VERSION
        or probe_document.get("timing_source") != TIMING_SOURCE
    ):
        return None
    expected_names = {spec["filename"] for spec in _ARTIFACT_SPECS}
    try:
        if {child.name for child in directory.iterdir()} != expected_names:
            return None
    except OSError:
        return None
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != expected_names - {"manifest.json"}:
        return None
    try:
        for spec in _ARTIFACT_SPECS:
            path = directory / spec["filename"]
            if path.is_symlink() or not path.is_file():
                return None
            if spec["filename"] == "manifest.json":
                continue
            entry = files.get(spec["filename"])
            size = path.stat().st_size
            maximum = MAX_OUTPUT_BYTES if spec["filename"] == "remotion-preview.mp4" else MAX_METADATA_BYTES
            if (
                size < 1
                or size > maximum
                or not isinstance(entry, dict)
                or set(entry) != {"path", "kind", "mime", "bytes", "sha256"}
                or entry.get("path") != spec["filename"]
                or entry.get("kind") != spec["kind"]
                or entry.get("mime") != spec["mime"]
                or entry.get("bytes") != size
                or entry.get("sha256") != _sha256_file(path)
            ):
                return None
        fresh_probe = _json_probe(
            ffprobe,
            Path("remotion-preview.mp4"),
            cwd=directory,
            cancel_event=cancel_event,
        )
        duration_ms = _validate_output_probe(
            fresh_probe, expected_frames=int(audit["duration_in_frames"])
        )
    except JobCancelled:
        raise
    except (AssemblyError, RemotionTimelineError, OSError, TypeError, ValueError):
        return None
    if (
        probe_document.get("remotion_preview") != fresh_probe
        or manifest.get("media") != {"remotion_preview": fresh_probe}
        or manifest.get("duration_ms") != duration_ms
    ):
        return None
    try:
        artifacts = [_artifact_record(workspace, directory, spec) for spec in _ARTIFACT_SPECS]
    except (OSError, ValueError):
        return None
    return manifest, artifacts


def discard_remotion_timeline_outputs(
    workspace: Path, *, run_id: str, cache_key: str
) -> bool:
    """Remove exactly one generated cache, rejecting unsafe/symlinked trees."""

    try:
        validate_identifier(run_id, label="run id")
        if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
            return False
        root = Path(workspace).resolve(strict=True)
        target = root / "outputs" / "studio" / "runs" / run_id / "remotion_timeline" / cache_key
        if _has_symlink_component(root, target):
            return False
        resolved = workspace_path(root, target, must_exist=False)
        if (
            not resolved.exists()
            or resolved.is_symlink()
            or not resolved.is_dir()
            or _tree_contains_symlink(resolved)
        ):
            return False
        shutil.rmtree(resolved)
        return not resolved.exists()
    except (OSError, ValueError, SecurityError):
        return False


def _generate_or_validate(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    node: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
    progress_callback: ProgressCallback | None,
    generate: bool,
) -> dict[str, Any]:
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    root = Path(workspace).resolve(strict=True)
    _progress(progress_callback, 2, "preflight")
    (
        node_executable,
        ffmpeg_executable,
        ffprobe_executable,
        render_script,
        entry_point,
        runtime,
        tool_identity,
    ) = _resolve_runtime(
        root,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    prepared, probes = _prepare_clips(
        root, clips, ffprobe=ffprobe_executable, cancel_event=cancel_event
    )
    compiled = compile_remotion_timeline(prepared)
    enhancement_plans = _source_enhancement_plans(prepared, probes, compiled)
    expected_key = remotion_timeline_cache_key(prepared, tool_identity=tool_identity)
    if cache_key != expected_key:
        raise RemotionTimelineValidationError(
            "cache_key does not match Remotion inputs", code="invalid_cache_key"
        )
    audit = {
        **remotion_timeline_audit_payload(prepared, cache_key=cache_key),
        "source_enhancement_results": enhancement_plans,
    }
    cache_directory = _safe_output_root(root, run_id, cache_key)
    _progress(progress_callback, 12, "cache_validation")
    cached = _validate_cache(
        root,
        cache_directory,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=prepared,
        audit=audit,
        tool_identity=tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    if cached is not None:
        manifest, artifacts = cached
        _progress(progress_callback, 100, "completed")
        return _result(root, cache_directory, manifest, artifacts, cache_hit=True)
    if not generate:
        raise RemotionTimelineError(
            "Remotion cache failed integrity verification", code="cache_integrity_failed"
        )
    if cache_directory.exists() and not discard_remotion_timeline_outputs(
        root, run_id=run_id, cache_key=cache_key
    ):
        raise RemotionTimelineError(
            "Invalid Remotion cache could not be discarded", code="cache_integrity_failed"
        )

    _progress(progress_callback, 14, "scratch_preflight")
    scratch_space = _scratch_space_preflight(cache_directory.parent, audit)
    stage_root = Path(tempfile.mkdtemp(prefix=".remotion-", dir=str(cache_directory.parent)))
    work_directory = stage_root / "work"
    public_directory = work_directory / "public"
    scratch_directory = work_directory / "scratch"
    publish_directory = stage_root / "publish"
    published = False
    try:
        work_directory.mkdir()
        public_directory.mkdir()
        scratch_directory.mkdir()
        publish_directory.mkdir()
        _progress(progress_callback, 18, "staging")
        _stage_sources(
            root,
            public_directory,
            prepared,
            enhancement_plans,
            ffmpeg=ffmpeg_executable,
            ffprobe=ffprobe_executable,
            cancel_event=cancel_event,
        )
        _progress(progress_callback, 22, "scratch_recheck")
        scratch_space = _complete_scratch_space_preflight(
            cache_directory.parent,
            audit,
            scratch_space,
            public_directory,
        )
        input_props = _input_props(prepared, compiled, enhancement_plans)
        request_path = work_directory / "render-request.json"
        result_path = work_directory / "render-result.json"
        raw_output = work_directory / "remotion-raw.mp4"
        _write_json(
            request_path,
            {
                "schema_version": SCHEMA_VERSION,
                "composition_id": COMPOSITION_ID,
                "entry_point": str(entry_point),
                "public_dir": str(public_directory),
                "browser_executable": str(runtime["browser"]),
                "output_path": str(raw_output),
                "scratch_directory": str(scratch_directory),
                "input_props": input_props,
            },
        )
        _progress(progress_callback, 25, "rendering")
        try:
            _bounded_process(
                [node_executable, str(render_script), str(request_path), str(result_path)],
                cwd=work_directory,
                timeout=NODE_TIMEOUT_SECONDS,
                label="Remotion render",
                cancel_event=cancel_event,
                environment=_render_environment(scratch_directory, work_directory),
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise RemotionTimelineToolError(
                "The local Remotion render failed", code="local_remotion_render_failed"
            ) from exc
        node_result = _read_json(result_path)
        if node_result is None:
            raise RemotionTimelineToolError(
                "The Remotion renderer returned invalid metadata", code="invalid_worker_result"
            )
        scratch_space = {
            **scratch_space,
            "node_containment_attested": node_result.get("scratch_directory_attested") is True,
        }
        report = _render_report(
            audit=audit,
            node_result=node_result,
            scratch_space=scratch_space,
        )
        if (
            raw_output.is_symlink()
            or not raw_output.is_file()
            or not 0 < raw_output.stat().st_size <= MAX_RAW_VIDEO_BYTES
        ):
            raise RemotionTimelineToolError(
                "The Remotion renderer returned invalid media", code="invalid_output_media"
            )
        if "runtime_attestation_identity" in runtime:
            _recheck_runtime_attestation(
                root,
                node_executable=node_executable,
                doctor_script=runtime["doctor_script"],
                expected_identity=runtime["runtime_attestation_identity"],
                cancel_event=cancel_event,
            )
        # The composition and scripts were hashed into the cache identity.
        # Recheck them after Node exits to close an in-place replacement race.
        for name, path in runtime["source_files"].items():
            if _sha256_file(path) != tool_identity[name]["sha256"]:
                raise RemotionTimelineError(
                    "The Remotion runtime changed during rendering", code="tool_changed"
                )
        for index, item in enumerate(prepared):
            _assert_source_unchanged(root, item, label=f"clips[{index}]")
        _cancel(cancel_event)
        _progress(progress_callback, 72, "media_normalization")
        partial = publish_directory / "remotion-preview.mp4.partial"
        try:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    "remotion-raw.mp4",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                    "-sn",
                    "-dn",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(REMOTION_VIDEO_CRF),
                    "-vf",
                    "scale=in_range=auto:out_range=tv,format=yuv420p",
                    "-r",
                    str(FRAME_RATE),
                    "-fps_mode",
                    "cfr",
                    "-pix_fmt",
                    "yuv420p",
                    "-color_range",
                    "tv",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-t",
                    f"{compiled['duration_in_frames'] / FRAME_RATE:.6f}",
                    "-movflags",
                    "+faststart",
                    "-fs",
                    str(MAX_OUTPUT_BYTES),
                    "-f",
                    "mp4",
                    (Path("..") / "publish" / partial.name).as_posix(),
                ],
                cwd=work_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="Remotion media normalization",
                cancel_event=cancel_event,
                environment=_clean_environment(),
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise RemotionTimelineToolError(
                "The Remotion media normalization failed", code="local_ffmpeg_failed"
            ) from exc
        if partial.is_symlink() or not partial.is_file() or not 0 < partial.stat().st_size <= MAX_OUTPUT_BYTES:
            raise RemotionTimelineToolError(
                "Media normalization produced invalid media", code="invalid_output_media"
            )
        os.replace(partial, publish_directory / "remotion-preview.mp4")
        _progress(progress_callback, 84, "verification")
        try:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "remotion-preview.mp4",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-f",
                    "null",
                    "-",
                ],
                cwd=publish_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="Remotion full decode",
                cancel_event=cancel_event,
                environment=_clean_environment(),
            )
            output_probe = _json_probe(
                ffprobe_executable,
                Path("remotion-preview.mp4"),
                cwd=publish_directory,
                cancel_event=cancel_event,
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise RemotionTimelineToolError(
                "The Remotion output could not be verified", code="invalid_output_media"
            ) from exc
        duration_ms = _validate_output_probe(
            output_probe, expected_frames=compiled["duration_in_frames"]
        )
        timeline = _timeline_document(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            clips=prepared,
        )
        _write_json(publish_directory / "remotion-timeline.json", timeline)
        _write_json(publish_directory / "render-report.json", report)
        _write_json(
            publish_directory / "ffprobe.json",
            {
                "schema_version": SCHEMA_VERSION,
                "implementation_version": IMPLEMENTATION_VERSION,
                "timing_source": TIMING_SOURCE,
                "remotion_preview": output_probe,
            },
        )
        manifest = _build_manifest(
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            audit=audit,
            duration_ms=duration_ms,
            tool_identity=tool_identity,
            output_probe=output_probe,
            scratch_space=scratch_space,
            stage=publish_directory,
        )
        _write_json(publish_directory / "manifest.json", manifest)
        if {child.name for child in publish_directory.iterdir()} != {
            spec["filename"] for spec in _ARTIFACT_SPECS
        }:
            raise RemotionTimelineError(
                "Remotion publish set is invalid", code="publish_failed"
            )
        _cancel(cancel_event)
        _progress(progress_callback, 94, "publishing")
        os.replace(publish_directory, cache_directory)
        published = True
    except JobCancelled:
        raise
    except RemotionTimelineError:
        raise
    except (AssemblyError, OSError, SecurityError, TypeError, ValueError) as exc:
        raise RemotionTimelineToolError(
            "The Remotion output could not be published", code="publish_failed"
        ) from exc
    finally:
        _cleanup_stage_root(stage_root)

    try:
        validated = _validate_cache(
            root,
            cache_directory,
            production_id=production_id,
            run_id=run_id,
            cache_key=cache_key,
            clips=prepared,
            audit=audit,
            tool_identity=tool_identity,
            ffprobe=ffprobe_executable,
            cancel_event=cancel_event,
        )
    except BaseException:
        if published:
            discard_remotion_timeline_outputs(root, run_id=run_id, cache_key=cache_key)
        raise
    if validated is None:
        if published:
            discard_remotion_timeline_outputs(root, run_id=run_id, cache_key=cache_key)
        raise RemotionTimelineError(
            "Published Remotion output failed integrity verification",
            code="integrity_verification_failed",
        )
    manifest, artifacts = validated
    _progress(progress_callback, 100, "completed")
    return _result(root, cache_directory, manifest, artifacts, cache_hit=False)


def generate_remotion_timeline(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    node: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=True,
    )


def validate_remotion_timeline_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    cache_key: str,
    clips: Sequence[Mapping[str, Any]],
    node: str | Path | None = None,
    ffmpeg: str | Path | None = None,
    ffprobe: str | Path | None = None,
    cancel_event: Any | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    return _generate_or_validate(
        workspace,
        production_id=production_id,
        run_id=run_id,
        cache_key=cache_key,
        clips=clips,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=False,
    )


__all__ = [
    "discard_remotion_timeline_outputs",
    "generate_remotion_timeline",
    "resolve_remotion_tool_identity",
    "validate_remotion_timeline_outputs",
]
