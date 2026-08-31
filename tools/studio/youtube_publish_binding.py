from __future__ import annotations

"""Bind a YouTube request to one verified delivery package and video.

This module performs no network operation.  It is the fail-closed bridge
between Studio's immutable artifacts/review ledger and the resumable YouTube
adapter.  Local paths are retained only in the private return object.
"""

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .security import SecurityError, sensitive_artifact_path, workspace_path
from .youtube_publish import (
    YouTubePublishValidationError,
    validate_youtube_preview_payload,
)


_DIGEST_RE = re.compile(r"^[0-9A-F]{64}$")
_DELIVERY_MEDIA_TYPE = "application/zip"
_VIDEO_MEDIA_TYPE = "video/mp4"
_MAX_DELIVERY_BYTES = 8 * 1024 * 1024 * 1024
_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_ARCHIVE_ENTRY_BYTES = 4 * 1024 * 1024 * 1024
_MAX_ARCHIVE_AGGREGATE_BYTES = 8 * 1024 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 256
_MANIFEST_KEYS = {
    "schema_version",
    "policy",
    "thumbnail_policy",
    "audit_policy",
    "production_id",
    "run_id",
    "revision_id",
    "source_job_id",
    "duration_ms",
    "metadata",
    "artifacts",
    "children",
    "audit_snapshot_sha256",
    "ffmpeg",
    "package_key",
    "thumbnail_timestamps_ms",
    "archive_entries",
}
_VIDEO_ROLES = {
    "clean_master": "video/master-clean.mp4",
    "captioned_master": "video/master-captioned.mp4",
}


class YouTubePublishBindingError(ValueError):
    def __init__(
        self,
        message: str = "The YouTube publication inputs are invalid.",
        *,
        code: str = "invalid_youtube_publish_binding",
    ):
        super().__init__(message)
        self.code = code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _artifact_path(
    workspace: Path,
    artifact: Mapping[str, Any],
    *,
    prefix: str,
    maximum_bytes: int,
) -> Path:
    relative = artifact.get("rel_path")
    byte_count = artifact.get("bytes")
    digest = artifact.get("sha256")
    if (
        not isinstance(relative, str)
        or not relative.startswith(prefix)
        or "\x00" in relative
        or PurePosixPath(relative.replace("\\", "/")).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or any(part in {"", ".", ".."} for part in relative.replace("\\", "/").split("/"))
        or sensitive_artifact_path(relative)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or not 0 < byte_count <= maximum_bytes
        or not isinstance(digest, str)
        or _DIGEST_RE.fullmatch(digest.upper()) is None
    ):
        raise YouTubePublishBindingError(code="youtube_artifact_invalid")
    current = workspace.resolve(strict=True)
    for part in relative.replace("\\", "/").split("/"):
        current = current / part
        if current.is_symlink():
            raise YouTubePublishBindingError(code="youtube_artifact_invalid")
    try:
        path = workspace_path(workspace, relative, must_exist=True)
        stat = path.stat()
    except (OSError, SecurityError) as exc:
        raise YouTubePublishBindingError(
            "A YouTube publication artifact is unavailable.",
            code="youtube_artifact_changed",
        ) from exc
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.st_size != byte_count
        or _sha256_file(path) != digest.upper()
    ):
        raise YouTubePublishBindingError(
            "A YouTube publication artifact changed.",
            code="youtube_artifact_changed",
        )
    return path


def _registered_artifact(
    database: Any,
    artifact_id: str,
    *,
    production_id: str,
    kind: str,
    media_type: str,
) -> dict[str, Any]:
    artifact = database.get_artifact(artifact_id)
    if (
        not isinstance(artifact, dict)
        or artifact.get("id") != artifact_id
        or artifact.get("production_id") != production_id
        or artifact.get("origin") != "studio"
        or artifact.get("kind") != kind
        or artifact.get("media_type") != media_type
        or artifact.get("available") is not True
    ):
        raise YouTubePublishBindingError(
            "The selected artifact does not belong to this production.",
            code="youtube_artifact_invalid",
        )
    return artifact


def _release_gates(database: Any, production_id: str) -> dict[str, Any]:
    try:
        snapshot = database.review_snapshot(production_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise YouTubePublishBindingError(
            "The publication review gates are unavailable.",
            code="youtube_release_gate_required",
        ) from exc
    gates = snapshot.get("gates") if isinstance(snapshot, dict) else None
    expected = {"creative", "rights", "public_release"}
    if not isinstance(gates, dict) or set(gates) != expected:
        raise YouTubePublishBindingError(
            "The publication review gates are incomplete.",
            code="youtube_release_gate_required",
        )
    public: dict[str, Any] = {}
    for name in sorted(expected):
        gate = gates.get(name)
        if not isinstance(gate, dict):
            raise YouTubePublishBindingError(
                "The publication review gates are incomplete.",
                code="youtube_release_gate_required",
            )
        decision = gate.get("decision")
        open_count = gate.get("open_count")
        review_count = gate.get("review_count")
        if (
            decision != "approved"
            or isinstance(open_count, bool)
            or not isinstance(open_count, int)
            or open_count != 0
            or isinstance(review_count, bool)
            or not isinstance(review_count, int)
            or review_count < 1
        ):
            raise YouTubePublishBindingError(
                "Creative, rights, and public-release approval are required.",
                code="youtube_release_gate_required",
            )
        public[name] = {
            "decision": "approved",
            "review_count": review_count,
            "open_count": 0,
        }
    return public


def _archive_manifest(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                len(names) > _MAX_ARCHIVE_ENTRIES + 1
                or len(names) != len(set(names))
                or "delivery/manifest.json" not in names
            ):
                raise ValueError("invalid archive names")
            for name in names:
                normalized = name.replace("\\", "/")
                if (
                    name != normalized
                    or PurePosixPath(normalized).is_absolute()
                    or any(part in {"", ".", ".."} for part in normalized.split("/"))
                ):
                    raise ValueError("unsafe archive name")
            info = archive.getinfo("delivery/manifest.json")
            if not 0 < info.file_size <= _MAX_MANIFEST_BYTES:
                raise ValueError("manifest size")
            value = json.loads(archive.read(info))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise YouTubePublishBindingError(
            "The delivery package manifest is invalid.",
            code="youtube_delivery_invalid",
        ) from exc
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise YouTubePublishBindingError(
            "The delivery package manifest is invalid.",
            code="youtube_delivery_invalid",
        )
    entries = value.get("archive_entries")
    if not isinstance(entries, list) or len(entries) > _MAX_ARCHIVE_ENTRIES:
        raise YouTubePublishBindingError(code="youtube_delivery_invalid")
    expected_names = {"delivery/manifest.json"}
    declared_total = 0
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "bytes", "sha256"}
            or not isinstance(entry.get("path"), str)
            or isinstance(entry.get("bytes"), bool)
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 0
            or entry["bytes"] > _MAX_ARCHIVE_ENTRY_BYTES
            or not isinstance(entry.get("sha256"), str)
            or _DIGEST_RE.fullmatch(entry["sha256"].upper()) is None
            or entry["path"] in expected_names
        ):
            raise YouTubePublishBindingError(code="youtube_delivery_invalid")
        expected_names.add(entry["path"])
        declared_total += entry["bytes"]
        if declared_total > _MAX_ARCHIVE_AGGREGATE_BYTES:
            raise YouTubePublishBindingError(code="youtube_delivery_invalid")
    if set(names) != expected_names:
        raise YouTubePublishBindingError(code="youtube_delivery_invalid")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for entry in entries:
                info = archive.getinfo(entry["path"])
                if info.is_dir() or info.file_size != entry["bytes"]:
                    raise ValueError("archive entry size mismatch")
                digest = hashlib.sha256()
                byte_count = 0
                with archive.open(info, "r") as handle:
                    while chunk := handle.read(1024 * 1024):
                        byte_count += len(chunk)
                        if byte_count > entry["bytes"]:
                            raise ValueError("archive entry exceeds declared size")
                        digest.update(chunk)
                if (
                    byte_count != entry["bytes"]
                    or digest.hexdigest().upper() != entry["sha256"].upper()
                ):
                    raise ValueError("archive entry digest mismatch")
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise YouTubePublishBindingError(
            "The delivery package contents are invalid.",
            code="youtube_delivery_invalid",
        ) from exc
    return value


@dataclass(frozen=True)
class YouTubePublishBinding:
    request: dict[str, Any]
    delivery_artifact: dict[str, Any]
    video_artifact: dict[str, Any]
    delivery_path: Path
    video_path: Path
    package_key: str
    run_id: str
    source_job_id: str
    video_role: str
    release_gates: dict[str, Any]

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "production_id": self.delivery_artifact["production_id"],
            "package_key": self.package_key,
            "run_id": self.run_id,
            "source_job_id": self.source_job_id,
            "video_role": self.video_role,
            "delivery_artifact_id": self.delivery_artifact["id"],
            "delivery_sha256": self.delivery_artifact["sha256"],
            "delivery_bytes": self.delivery_artifact["bytes"],
            "video_artifact_id": self.video_artifact["id"],
            "video_sha256": self.video_artifact["sha256"],
            "video_bytes": self.video_artifact["bytes"],
            "release_gates": self.release_gates,
        }


def resolve_youtube_publish_binding(
    workspace: Path,
    database: Any,
    production_id: str,
    request: Mapping[str, Any],
) -> YouTubePublishBinding:
    try:
        normalized = validate_youtube_preview_payload(dict(request))
    except YouTubePublishValidationError as exc:
        raise YouTubePublishBindingError(str(exc), code=exc.code) from exc
    production = database.get_production(production_id)
    if not isinstance(production, dict) or production.get("id") != production_id:
        raise KeyError("production not found")
    delivery = _registered_artifact(
        database,
        normalized["delivery_artifact_id"],
        production_id=production_id,
        kind="delivery",
        media_type=_DELIVERY_MEDIA_TYPE,
    )
    video = _registered_artifact(
        database,
        normalized["video_artifact_id"],
        production_id=production_id,
        kind="video",
        media_type=_VIDEO_MEDIA_TYPE,
    )
    delivery_path = _artifact_path(
        workspace,
        delivery,
        prefix=f"outputs/studio/deliveries/{production_id}/",
        maximum_bytes=_MAX_DELIVERY_BYTES,
    )
    video_path = _artifact_path(
        workspace,
        video,
        prefix="outputs/studio/runs/",
        maximum_bytes=_MAX_VIDEO_BYTES,
    )
    if delivery.get("name") != "delivery-package.zip" or video.get("name") not in {
        "master-clean.mp4",
        "master-captioned.mp4",
    }:
        raise YouTubePublishBindingError(code="youtube_artifact_invalid")
    manifest = _archive_manifest(delivery_path)
    package_key = manifest.get("package_key")
    run_id = manifest.get("run_id")
    source_job_id = manifest.get("source_job_id")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("policy") != "studio-delivery-package-v1"
        or manifest.get("production_id") != production_id
        or not isinstance(package_key, str)
        or _DIGEST_RE.fullmatch(package_key.upper()) is None
        or delivery_path.parent.name != package_key
        or not isinstance(run_id, str)
        or re.fullmatch(r"run_[0-9a-f]{32}", run_id) is None
        or not isinstance(source_job_id, str)
        or re.fullmatch(r"job_[0-9a-f]{32}", source_job_id) is None
    ):
        raise YouTubePublishBindingError(code="youtube_delivery_invalid")
    manifest_artifacts = manifest.get("artifacts")
    if not isinstance(manifest_artifacts, dict):
        raise YouTubePublishBindingError(code="youtube_delivery_invalid")
    matches: list[str] = []
    for role, archive_path in _VIDEO_ROLES.items():
        source = manifest_artifacts.get(role)
        if not isinstance(source, dict):
            raise YouTubePublishBindingError(code="youtube_delivery_invalid")
        entries = [
            item
            for item in manifest["archive_entries"]
            if isinstance(item, dict) and item.get("path") == archive_path
        ]
        if (
            len(entries) != 1
            or source.get("id") is None
            or source.get("bytes") != entries[0]["bytes"]
            or str(source.get("sha256", "")).upper() != entries[0]["sha256"].upper()
        ):
            raise YouTubePublishBindingError(code="youtube_delivery_invalid")
        if (
            source.get("id") == video["id"]
            and source.get("bytes") == video["bytes"]
            and str(source.get("sha256", "")).upper() == video["sha256"].upper()
        ):
            matches.append(role)
    if len(matches) != 1:
        raise YouTubePublishBindingError(
            "The selected video is not the verified master in this delivery package.",
            code="youtube_video_not_in_delivery",
        )
    gates = _release_gates(database, production_id)
    return YouTubePublishBinding(
        request=normalized,
        delivery_artifact=delivery,
        video_artifact=video,
        delivery_path=delivery_path,
        video_path=video_path,
        package_key=package_key,
        run_id=run_id,
        source_job_id=source_job_id,
        video_role=matches[0],
        release_gates=gates,
    )


__all__ = [
    "YouTubePublishBinding",
    "YouTubePublishBindingError",
    "resolve_youtube_publish_binding",
]
