from __future__ import annotations

"""Playwright viewport capture worker with verified, atomic publication."""

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping

from . import assembly as _assembly
from .assembly import (
    AssemblyError,
    _bounded_process,
    _json_probe,
    _probe_duration,
    _sha256_file,
    _streams,
)
from .browser_capture_execution import (
    BROWSER_CAPTURE_SCHEMA_VERSION,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    FRAME_RATE,
    IMPLEMENTATION_VERSION,
    OUTPUT_POLICY_VERSION,
    PROVIDER,
    TIMING_SOURCE,
    BrowserCaptureError,
    BrowserCaptureToolError,
    BrowserCaptureValidationError,
    browser_capture_audit_payload,
)
from .jobs import JobCancelled
from .security import canonical_json, relative_workspace_path, validate_identifier, workspace_path


MAX_RAW_VIDEO_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = 5 * 60
FFPROBE_TIMEOUT_SECONDS = 30
NODE_BASE_TIMEOUT_SECONDS = 60
FFMPEG_THREADS = 2

_CACHE_KEY_RE = re.compile(r"^[0-9A-F]{64}$")
_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {"filename": "screen-capture.mp4", "kind": "video", "mime": "video/mp4"},
    {"filename": "playwright-raw.webm", "kind": "video", "mime": "video/webm"},
    {"filename": "first-frame.png", "kind": "image", "mime": "image/png"},
    {"filename": "last-frame.png", "kind": "image", "mime": "image/png"},
    {"filename": "capture-report.json", "kind": "document", "mime": "application/json"},
    {"filename": "ffprobe.json", "kind": "document", "mime": "application/json"},
    {"filename": "manifest.json", "kind": "document", "mime": "application/json"},
)


def _cancel(cancel_event: Any | None) -> None:
    _assembly._raise_if_cancelled(cancel_event)


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def _clean_environment() -> dict[str, str]:
    blocked = {
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "node_options",
        "node_path",
        "no_proxy",
        "npm_config_proxy",
        "npm_config_https_proxy",
        "playwright_browsers_path",
    }
    return {key: value for key, value in os.environ.items() if key.casefold() not in blocked}


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


def _safe_capture_root(workspace: Path, run_id: str, capture_key: str) -> Path:
    validate_identifier(run_id, label="run id")
    if not isinstance(capture_key, str) or not _CACHE_KEY_RE.fullmatch(capture_key):
        raise BrowserCaptureValidationError("capture_key is invalid", code="invalid_cache_key")
    lexical_root = workspace / "outputs" / "studio" / "runs"
    lexical_run = lexical_root / run_id
    lexical_stage = lexical_run / "screen_capture"
    lexical_capture = lexical_stage / capture_key
    if any(
        _has_symlink_component(workspace, candidate)
        for candidate in (lexical_root, lexical_run, lexical_stage, lexical_capture)
    ):
        raise BrowserCaptureValidationError(
            "screen capture output path must not contain symlinks",
            code="unsafe_output_path",
        )
    root = workspace_path(workspace, lexical_root, must_exist=False)
    run_directory = workspace_path(workspace, lexical_run, must_exist=False)
    stage_directory = workspace_path(workspace, lexical_stage, must_exist=False)
    capture_directory = workspace_path(workspace, lexical_capture, must_exist=False)
    for directory in (root, run_directory, stage_directory):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise BrowserCaptureValidationError(
                "screen capture output path is unsafe", code="unsafe_output_path"
            )
        directory.mkdir(parents=True, exist_ok=True)
    if capture_directory.exists() and capture_directory.is_symlink():
        raise BrowserCaptureValidationError(
            "screen capture output path is unsafe", code="unsafe_output_path"
        )
    return capture_directory


def _tool_file_identity(path: Path, *, version: str) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise BrowserCaptureToolError("A pinned Playwright tool file is unavailable.", code="playwright_unavailable")
    return {
        "version": version,
        "sha256": _sha256_file(resolved),
    }


def _executable_identity(
    name: str,
    executable: str,
    *,
    version_argument: str,
    cancel_event: Any | None,
) -> dict[str, str]:
    resolved = Path(executable).resolve(strict=True)
    output = _bounded_process(
        [str(resolved), version_argument],
        cwd=resolved.parent,
        timeout=FFPROBE_TIMEOUT_SECONDS,
        label=f"{name} version",
        cancel_event=cancel_event,
        environment=_clean_environment(),
    )
    version = output.decode("utf-8", errors="replace").splitlines()[0].strip()
    if not version or len(version) > 512:
        raise BrowserCaptureToolError(f"{name} version is unavailable", code="playwright_unavailable")
    return {"version": version, "sha256": _sha256_file(resolved)}


def _public_tool_identity(identity: Mapping[str, Any], *, label: str) -> dict[str, str]:
    """Keep durable tool provenance free of host-specific filesystem paths."""

    version = identity.get("version")
    digest = identity.get("sha256")
    if (
        not isinstance(version, str)
        or not version
        or len(version) > 512
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest)
    ):
        raise BrowserCaptureToolError(
            f"{label} tool identity is invalid.", code="local_worker_unavailable"
        )
    return {"version": version, "sha256": digest.upper()}


def _resolve_tools(
    workspace: Path,
    *,
    node: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
) -> tuple[str, str, str, Path, dict[str, dict[str, str]]]:
    _cancel(cancel_event)
    try:
        node_executable = _assembly._find_tool("node", node)
        ffmpeg_executable = _assembly._find_tool("ffmpeg", ffmpeg)
        ffprobe_executable = _assembly._find_tool("ffprobe", ffprobe)
    except AssemblyError as exc:
        raise BrowserCaptureToolError(
            "Node.js or the local FFmpeg tools are unavailable.",
            code="local_worker_unavailable",
        ) from exc
    capture_script = workspace_path(
        workspace, "tools/studio/playwright_capture.mjs", must_exist=True
    )
    doctor_script = workspace_path(
        workspace, "tools/studio/playwright_doctor.mjs", must_exist=True
    )
    package_path = workspace_path(
        workspace, "studio/node_modules/playwright/package.json", must_exist=True
    )
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BrowserCaptureToolError(
            "The pinned Playwright package is unavailable.", code="playwright_unavailable"
        ) from exc
    package_version = package.get("version") if isinstance(package, dict) else None
    if not isinstance(package_version, str) or not package_version:
        raise BrowserCaptureToolError(
            "The pinned Playwright package is invalid.", code="playwright_unavailable"
        )
    try:
        doctor_output = _bounded_process(
            [node_executable, str(doctor_script)],
            cwd=workspace,
            timeout=NODE_BASE_TIMEOUT_SECONDS,
            label="Playwright doctor",
            cancel_event=cancel_event,
            environment=_clean_environment(),
        )
        doctor = json.loads(doctor_output.decode("utf-8"))
    except JobCancelled:
        raise
    except (AssemblyError, UnicodeError, json.JSONDecodeError) as exc:
        raise BrowserCaptureToolError(
            "Pinned Playwright Chromium is unavailable. Run setup-studio.ps1.",
            code="playwright_unavailable",
        ) from exc
    chromium_path_value = doctor.get("chromium_executable_path") if isinstance(doctor, dict) else None
    chromium_version = doctor.get("chromium_version") if isinstance(doctor, dict) else None
    if (
        doctor.get("playwright_version") != package_version
        or not isinstance(chromium_path_value, str)
        or not isinstance(chromium_version, str)
        or not chromium_version
    ):
        raise BrowserCaptureToolError(
            "Pinned Playwright Chromium identity is invalid.", code="playwright_unavailable"
        )
    chromium_path = Path(chromium_path_value).resolve(strict=True)
    if not chromium_path.is_file():
        raise BrowserCaptureToolError(
            "Pinned Playwright Chromium is unavailable.", code="playwright_unavailable"
        )
    try:
        tool_identity = {
            "node": _executable_identity(
                "node",
                node_executable,
                version_argument="--version",
                cancel_event=cancel_event,
            ),
            "playwright": _tool_file_identity(package_path, version=package_version),
            "chromium": _tool_file_identity(chromium_path, version=chromium_version),
            "capture_script": _tool_file_identity(
                capture_script, version=IMPLEMENTATION_VERSION
            ),
            "doctor_script": _tool_file_identity(
                doctor_script, version=IMPLEMENTATION_VERSION
            ),
            "ffmpeg": _public_tool_identity(
                _assembly._tool_identity(
                    "ffmpeg", ffmpeg_executable, cancel_event=cancel_event
                ),
                label="ffmpeg",
            ),
            "ffprobe": _public_tool_identity(
                _assembly._tool_identity(
                    "ffprobe", ffprobe_executable, cancel_event=cancel_event
                ),
                label="ffprobe",
            ),
        }
    except (AssemblyError, OSError) as exc:
        raise BrowserCaptureToolError(
            "The local screen capture tool identity is unavailable.",
            code="local_worker_unavailable",
        ) from exc
    return node_executable, ffmpeg_executable, ffprobe_executable, capture_script, tool_identity


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    if len(data) > MAX_METADATA_BYTES:
        raise BrowserCaptureError("screen capture metadata is too large", code="metadata_too_large")
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _fraction(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        result = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _validate_mp4_probe(probe: Mapping[str, Any], *, expected_duration_ms: int) -> int:
    format_data = probe.get("format")
    format_name = format_data.get("format_name") if isinstance(format_data, dict) else None
    if not isinstance(format_name, str) or "mp4" not in {
        item.strip().casefold() for item in format_name.split(",")
    }:
        raise BrowserCaptureError("screen capture output is not MP4", code="invalid_output_media")
    try:
        streams = _streams(probe)
    except AssemblyError as exc:
        raise BrowserCaptureError("screen capture streams are invalid", code="invalid_output_media") from exc
    if len(streams) != 1 or streams[0].get("codec_type") != "video":
        raise BrowserCaptureError("screen capture must contain video only", code="invalid_output_media")
    video = streams[0]
    if (
        video.get("codec_name") != "h264"
        or video.get("pix_fmt") != "yuv420p"
        or video.get("width") != CANVAS_WIDTH
        or video.get("height") != CANVAS_HEIGHT
    ):
        raise BrowserCaptureError("screen capture video format is unsupported", code="invalid_output_media")
    rates = (_fraction(video.get("r_frame_rate")), _fraction(video.get("avg_frame_rate")))
    if any(rate is None or abs(rate - FRAME_RATE) > 0.01 for rate in rates):
        raise BrowserCaptureError("screen capture frame rate is unsupported", code="invalid_output_media")
    try:
        duration_ms = int(round(_probe_duration(probe, stream_type="video") * 1000))
    except AssemblyError as exc:
        raise BrowserCaptureError("screen capture duration is unavailable", code="invalid_output_media") from exc
    if abs(duration_ms - expected_duration_ms) > 250:
        raise BrowserCaptureError("screen capture duration is invalid", code="invalid_output_media")
    return duration_ms


def _validate_raw_probe(probe: Mapping[str, Any]) -> None:
    try:
        streams = _streams(probe)
    except AssemblyError as exc:
        raise BrowserCaptureError("raw Playwright media is invalid", code="invalid_output_media") from exc
    if len(streams) != 1 or streams[0].get("codec_type") != "video":
        raise BrowserCaptureError("raw Playwright media must contain video only", code="invalid_output_media")
    video = streams[0]
    if (
        video.get("codec_name") not in {"vp8", "vp9", "av1"}
        or video.get("width") != CANVAS_WIDTH
        or video.get("height") != CANVAS_HEIGHT
    ):
        raise BrowserCaptureError("raw Playwright media format is unsupported", code="invalid_output_media")


def _validate_png(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BrowserCaptureError("capture frame is unavailable", code="invalid_worker_result")
    size = path.stat().st_size
    if size < 8 or size > MAX_IMAGE_BYTES or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise BrowserCaptureError("capture frame is invalid", code="invalid_worker_result")


def _artifact_record(workspace: Path, directory: Path, spec: Mapping[str, str]) -> dict[str, Any]:
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


def _output_policy() -> dict[str, Any]:
    """Return the exact media policy that is enforced by ffmpeg/ffprobe."""

    return {
        "policy_version": OUTPUT_POLICY_VERSION,
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "frame_rate": FRAME_RATE,
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "audio": "omitted",
    }


def _build_manifest(
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    audit: Mapping[str, Any],
    duration_ms: int,
    tool_identity: Mapping[str, Mapping[str, str]],
    raw_probe: Mapping[str, Any],
    output_probe: Mapping[str, Any],
    stage: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for spec in _ARTIFACT_SPECS:
        if spec["filename"] == "manifest.json":
            continue
        path = stage / spec["filename"]
        stat = path.stat()
        files[spec["filename"]] = {
            "path": spec["filename"],
            "kind": spec["kind"],
            "mime": spec["mime"],
            "bytes": stat.st_size,
            "sha256": _sha256_file(path),
        }
    body: dict[str, Any] = {
        "schema_version": BROWSER_CAPTURE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "production_id": production_id,
        "run_id": run_id,
        "capture_key": capture_key,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "requested_duration_ms": audit["duration_ms"],
        "duration_ms": duration_ms,
        "capture": dict(audit),
        "tool_identity": {key: dict(value) for key, value in tool_identity.items()},
        "output_policy": _output_policy(),
        "network_policy": "same-explicit-loopback-origin-only",
        "media": {"playwright_raw": dict(raw_probe), "screen_capture": dict(output_probe)},
        "files": files,
    }
    body["manifest_sha256"] = _manifest_digest(body)
    return body


def _read_manifest(path: Path) -> dict[str, Any] | None:
    value = _read_json(path)
    if value is None or not isinstance(value.get("manifest_sha256"), str):
        return None
    digest = value["manifest_sha256"]
    body = dict(value)
    body.pop("manifest_sha256", None)
    return value if _manifest_digest(body) == digest.upper() else None


def _validate_capture(
    workspace: Path,
    directory: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    audit: Mapping[str, Any],
    tool_identity: Mapping[str, Mapping[str, str]],
    ffprobe: str,
    cancel_event: Any | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    _cancel(cancel_event)
    if not directory.is_dir() or directory.is_symlink():
        return None
    manifest = _read_manifest(directory / "manifest.json")
    if manifest is None:
        return None
    if (
        manifest.get("schema_version") != BROWSER_CAPTURE_SCHEMA_VERSION
        or manifest.get("implementation_version") != IMPLEMENTATION_VERSION
        or manifest.get("production_id") != production_id
        or manifest.get("run_id") != run_id
        or manifest.get("capture_key") != capture_key
        or manifest.get("provider") != PROVIDER
        or manifest.get("provider_task_id") is not None
        or manifest.get("actual_cost") != 0
        or manifest.get("timing_source") != TIMING_SOURCE
        or manifest.get("requested_duration_ms") != audit.get("duration_ms")
        or manifest.get("capture") != dict(audit)
        or manifest.get("tool_identity") != {
            key: dict(value) for key, value in tool_identity.items()
        }
        or manifest.get("output_policy") != _output_policy()
        or manifest.get("network_policy") != "same-explicit-loopback-origin-only"
    ):
        return None
    expected_names = {spec["filename"] for spec in _ARTIFACT_SPECS}
    try:
        if {child.name for child in directory.iterdir()} != expected_names:
            return None
    except OSError:
        return None
    files = manifest.get("files")
    expected_file_names = expected_names - {"manifest.json"}
    if not isinstance(files, dict) or set(files) != expected_file_names:
        return None
    try:
        for spec in _ARTIFACT_SPECS:
            path = directory / spec["filename"]
            if path.is_symlink() or not path.is_file():
                return None
            if spec["filename"] == "manifest.json":
                continue
            size = path.stat().st_size
            entry = files.get(spec["filename"])
            if (
                not isinstance(entry, dict)
                or entry.get("path") != spec["filename"]
                or entry.get("kind") != spec["kind"]
                or entry.get("mime") != spec["mime"]
                or entry.get("bytes") != size
                or entry.get("sha256") != _sha256_file(path)
            ):
                return None
        if (directory / "screen-capture.mp4").stat().st_size > MAX_OUTPUT_BYTES:
            return None
        if (directory / "playwright-raw.webm").stat().st_size > MAX_RAW_VIDEO_BYTES:
            return None
        _validate_png(directory / "first-frame.png")
        _validate_png(directory / "last-frame.png")
        report = _read_json(directory / "capture-report.json")
        probe_document = _read_json(directory / "ffprobe.json")
        if report is None or probe_document is None:
            return None
        raw_probe = _json_probe(
            ffprobe,
            Path("playwright-raw.webm"),
            cwd=directory,
            cancel_event=cancel_event,
        )
        output_probe = _json_probe(
            ffprobe,
            Path("screen-capture.mp4"),
            cwd=directory,
            cancel_event=cancel_event,
        )
        _validate_raw_probe(raw_probe)
        duration_ms = _validate_mp4_probe(
            output_probe, expected_duration_ms=int(audit["duration_ms"])
        )
    except JobCancelled:
        raise
    except (AssemblyError, BrowserCaptureError, OSError, ValueError, TypeError):
        return None
    if (
        probe_document.get("schema_version") != BROWSER_CAPTURE_SCHEMA_VERSION
        or probe_document.get("implementation_version") != IMPLEMENTATION_VERSION
        or probe_document.get("timing_source") != TIMING_SOURCE
        or probe_document.get("playwright_raw") != raw_probe
        or probe_document.get("screen_capture") != output_probe
        or manifest.get("media") != {
            "playwright_raw": raw_probe,
            "screen_capture": output_probe,
        }
        or manifest.get("duration_ms") != duration_ms
        or report.get("capture") != dict(audit)
        or report.get("raw_url_recorded") is not False
    ):
        return None
    try:
        artifacts = [_artifact_record(workspace, directory, spec) for spec in _ARTIFACT_SPECS]
    except (OSError, ValueError):
        return None
    return manifest, artifacts


def _result(
    workspace: Path,
    directory: Path,
    manifest: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifacts": artifacts,
        "duration_ms": manifest["duration_ms"],
        "capture_key": manifest["capture_key"],
        "cache_hit": False,
        "provider": PROVIDER,
        "provider_task_id": None,
        "actual_cost": 0,
        "timing_source": TIMING_SOURCE,
        "target_origin": manifest["capture"]["target"]["origin"],
        "video_dimensions": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "frame_rate": FRAME_RATE,
        "output_directory": directory.relative_to(workspace.resolve(strict=True)).as_posix(),
    }


def discard_local_screen_capture_outputs(
    workspace: Path,
    *,
    run_id: str,
    capture_key: str,
) -> bool:
    """Remove only one capture directory, failing closed on unsafe paths.

    This helper is intentionally idempotent and returns ``False`` when the
    requested path is invalid, absent, non-directory, or contains a symlink.
    It never removes the run/stage parents, so callers can use it while
    unwinding a failed atomic stage completion.
    """

    try:
        validate_identifier(run_id, label="run id")
        if not isinstance(capture_key, str) or not _CACHE_KEY_RE.fullmatch(capture_key):
            return False
        root = Path(workspace).resolve(strict=True)
        candidate = (
            root
            / "outputs"
            / "studio"
            / "runs"
            / run_id
            / "screen_capture"
            / capture_key
        )
        if _has_symlink_component(root, candidate):
            return False
        target = workspace_path(root, candidate, must_exist=False)
        if not target.exists() or target.is_symlink() or not target.is_dir():
            return False
        shutil.rmtree(target)
        return not target.exists()
    except (OSError, ValueError):
        return False


ProgressCallback = Callable[[int, str], None]


def _report_progress(
    callback: ProgressCallback | None, progress: int, phase: str
) -> None:
    """Publish optional UI telemetry without weakening the media boundary."""

    if callback is None:
        return
    try:
        callback(progress, phase)
    except Exception:
        # Progress is advisory. Capture validation and atomic completion remain
        # authoritative even if an intermediate SQLite update is unavailable.
        return


def _generate_or_validate(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
    node: str | Path | None,
    ffmpeg: str | Path | None,
    ffprobe: str | Path | None,
    cancel_event: Any | None,
    progress_callback: ProgressCallback | None,
    generate: bool,
) -> dict[str, Any]:
    validate_identifier(production_id, label="production id")
    validate_identifier(run_id, label="run id")
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    workspace = workspace.resolve(strict=True)
    _report_progress(progress_callback, 2, "preflight")
    audit = browser_capture_audit_payload(payload, capture_key=capture_key)
    (
        node_executable,
        ffmpeg_executable,
        ffprobe_executable,
        capture_script,
        tool_identity,
    ) = _resolve_tools(
        workspace,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
    )
    _report_progress(progress_callback, 10, "preflight")
    capture_directory = _safe_capture_root(workspace, run_id, capture_key)
    cached = _validate_capture(
        workspace,
        capture_directory,
        production_id=production_id,
        run_id=run_id,
        capture_key=capture_key,
        audit=audit,
        tool_identity=tool_identity,
        ffprobe=ffprobe_executable,
        cancel_event=cancel_event,
    )
    if cached is not None:
        _report_progress(progress_callback, 96, "verification")
        manifest, artifacts = cached
        return _result(workspace, capture_directory, manifest, artifacts)
    if not generate:
        raise BrowserCaptureError(
            "screen capture output failed integrity verification",
            code="cache_integrity_failed",
        )
    if capture_directory.exists():
        raise BrowserCaptureError(
            "screen capture destination already exists",
            code="publish_failed",
        )

    parent = capture_directory.parent
    temporary_root = Path(tempfile.mkdtemp(prefix=".screen-capture-", dir=str(parent)))
    work_directory = temporary_root / "work"
    publish_directory = temporary_root / "publish"
    work_directory.mkdir()
    publish_directory.mkdir()
    published = False
    try:
        request_path = work_directory / "capture-request.json"
        result_path = work_directory / "capture-result.json"
        browser_output = work_directory / "browser-output"
        request_document = {
            "url": payload["url"],
            "duration_ms": payload["duration_ms"],
            "settle_ms": payload["settle_ms"],
            "actions": payload["actions"],
            "output_dir": str(browser_output),
        }
        request_path.write_text(canonical_json(request_document) + "\n", encoding="utf-8")
        timeout = (
            NODE_BASE_TIMEOUT_SECONDS
            + float(payload["duration_ms"]) / 1000
            + float(payload["settle_ms"]) / 1000
            + len(payload["actions"]) * 2
        )
        _report_progress(progress_callback, 20, "recording")
        try:
            _bounded_process(
                [node_executable, str(capture_script), str(request_path), str(result_path)],
                cwd=workspace,
                timeout=timeout,
                label="Playwright screen capture",
                cancel_event=cancel_event,
                environment=_clean_environment(),
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise BrowserCaptureToolError(
                "The local Playwright capture failed.", code="local_playwright_failed"
            ) from exc
        node_result = _read_json(result_path)
        if (
            node_result is None
            or node_result.get("schema_version") != BROWSER_CAPTURE_SCHEMA_VERSION
            or "error_code" in node_result
            or not isinstance(node_result.get("trim_start_ms"), int)
            or node_result.get("requested_duration_ms") != payload["duration_ms"]
            or node_result.get("playwright_version")
            != tool_identity["playwright"]["version"]
            or node_result.get("browser_version")
            != tool_identity["chromium"]["version"]
            or not isinstance(node_result.get("diagnostic_hashes"), list)
        ):
            raise BrowserCaptureToolError(
                "The local Playwright worker returned invalid metadata.",
                code="invalid_worker_result",
            )
        expected_browser_files = {
            "playwright-raw.webm",
            "first-frame.png",
            "last-frame.png",
        }
        if (
            not browser_output.is_dir()
            or browser_output.is_symlink()
            or {child.name for child in browser_output.iterdir()} != expected_browser_files
        ):
            raise BrowserCaptureToolError(
                "The local Playwright worker returned an invalid file set.",
                code="invalid_worker_result",
            )
        raw_source = browser_output / "playwright-raw.webm"
        first_source = browser_output / "first-frame.png"
        last_source = browser_output / "last-frame.png"
        if (
            raw_source.is_symlink()
            or not raw_source.is_file()
            or raw_source.stat().st_size < 1
            or raw_source.stat().st_size > MAX_RAW_VIDEO_BYTES
        ):
            raise BrowserCaptureToolError("Playwright raw video is invalid", code="invalid_output_media")
        _validate_png(first_source)
        _validate_png(last_source)
        os.replace(raw_source, publish_directory / "playwright-raw.webm")
        os.replace(first_source, publish_directory / "first-frame.png")
        os.replace(last_source, publish_directory / "last-frame.png")
        _cancel(cancel_event)

        trim_seconds = node_result["trim_start_ms"] / 1000
        duration_seconds = payload["duration_ms"] / 1000
        output_partial = publish_directory / "screen-capture.mp4.partial"
        _report_progress(progress_callback, 60, "transcoding")
        try:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    "playwright-raw.webm",
                    "-ss",
                    f"{trim_seconds:.3f}",
                    "-t",
                    f"{duration_seconds:.3f}",
                    "-map",
                    "0:v:0",
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                    "-an",
                    "-sn",
                    "-dn",
                    "-vf",
                    f"scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=decrease,pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,fps={FRAME_RATE}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    str(FFMPEG_THREADS),
                    "-movflags",
                    "+faststart",
                    "-fs",
                    str(MAX_OUTPUT_BYTES),
                    "-f",
                    "mp4",
                    output_partial.name,
                ],
                cwd=publish_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="screen capture ffmpeg",
                cancel_event=cancel_event,
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise BrowserCaptureToolError(
                "The local screen capture conversion failed.", code="local_ffmpeg_failed"
            ) from exc
        if not output_partial.is_file():
            raise BrowserCaptureToolError("screen capture conversion produced no output", code="invalid_worker_result")
        os.replace(output_partial, publish_directory / "screen-capture.mp4")
        _report_progress(progress_callback, 78, "verification")
        try:
            _bounded_process(
                [
                    ffmpeg_executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "screen-capture.mp4",
                    "-map",
                    "0:v:0",
                    "-f",
                    "null",
                    "-",
                ],
                cwd=publish_directory,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                label="screen capture full decode",
                cancel_event=cancel_event,
            )
        except JobCancelled:
            raise
        except AssemblyError as exc:
            raise BrowserCaptureToolError(
                "The local screen capture did not fully decode.", code="invalid_output_media"
            ) from exc
        raw_probe = _json_probe(
            ffprobe_executable,
            Path("playwright-raw.webm"),
            cwd=publish_directory,
            cancel_event=cancel_event,
        )
        output_probe = _json_probe(
            ffprobe_executable,
            Path("screen-capture.mp4"),
            cwd=publish_directory,
            cancel_event=cancel_event,
        )
        _validate_raw_probe(raw_probe)
        duration_ms = _validate_mp4_probe(
            output_probe, expected_duration_ms=int(payload["duration_ms"])
        )
        report = {
            "schema_version": BROWSER_CAPTURE_SCHEMA_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
            "provider": PROVIDER,
            "capture": dict(audit),
            "raw_url_recorded": False,
            "recording": {
                "playwright_version": node_result["playwright_version"],
                "browser_version": node_result["browser_version"],
                "trim_start_ms": node_result["trim_start_ms"],
                "diagnostic_count": node_result.get("diagnostic_count", 0),
                "diagnostic_hashes": node_result["diagnostic_hashes"],
            },
        }
        _write_json(publish_directory / "capture-report.json", report)
        _write_json(
            publish_directory / "ffprobe.json",
            {
                "schema_version": BROWSER_CAPTURE_SCHEMA_VERSION,
                "implementation_version": IMPLEMENTATION_VERSION,
                "timing_source": TIMING_SOURCE,
                "playwright_raw": raw_probe,
                "screen_capture": output_probe,
            },
        )
        manifest = _build_manifest(
            production_id=production_id,
            run_id=run_id,
            capture_key=capture_key,
            audit=audit,
            duration_ms=duration_ms,
            tool_identity=tool_identity,
            raw_probe=raw_probe,
            output_probe=output_probe,
            stage=publish_directory,
        )
        _write_json(publish_directory / "manifest.json", manifest)
        _cancel(cancel_event)
        _report_progress(progress_callback, 90, "publishing")
        os.replace(publish_directory, capture_directory)
        published = True
    except JobCancelled:
        raise
    except BrowserCaptureError:
        raise
    except (AssemblyError, OSError, ValueError, TypeError) as exc:
        raise BrowserCaptureToolError(
            "The local screen capture could not be published.", code="publish_failed"
        ) from exc
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    try:
        validated = _validate_capture(
            workspace,
            capture_directory,
            production_id=production_id,
            run_id=run_id,
            capture_key=capture_key,
            audit=audit,
            tool_identity=tool_identity,
            ffprobe=ffprobe_executable,
            cancel_event=cancel_event,
        )
        _cancel(cancel_event)
    except BaseException:
        if published:
            discard_local_screen_capture_outputs(
                workspace, run_id=run_id, capture_key=capture_key
            )
        raise
    if validated is None:
        if published:
            discard_local_screen_capture_outputs(
                workspace, run_id=run_id, capture_key=capture_key
            )
        raise BrowserCaptureError(
            "published screen capture failed integrity verification",
            code="integrity_verification_failed",
        )
    manifest, artifacts = validated
    _report_progress(progress_callback, 96, "registration")
    return _result(workspace, capture_directory, manifest, artifacts)


def generate_local_screen_capture(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
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
        capture_key=capture_key,
        payload=payload,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=True,
    )


def validate_local_screen_capture_outputs(
    workspace: Path,
    *,
    production_id: str,
    run_id: str,
    capture_key: str,
    payload: Mapping[str, Any],
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
        capture_key=capture_key,
        payload=payload,
        node=node,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        generate=False,
    )


__all__ = [
    "discard_local_screen_capture_outputs",
    "generate_local_screen_capture",
    "validate_local_screen_capture_outputs",
]
