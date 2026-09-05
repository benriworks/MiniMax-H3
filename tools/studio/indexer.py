from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Iterator

from .database import StudioDatabase
from .media_metadata import bound_video_metadata
from .production_intake import (
    PRODUCTION_METADATA_FILENAME,
    PRODUCTION_ID_RE,
    VIDEO_IMPORT_PARTIALS_DIRNAME,
    VIDEO_IMPORTS_DIRNAME,
    read_production_metadata,
)
from .security import (
    IDENTIFIER_RE,
    relative_workspace_path,
    sensitive_artifact_path,
    stable_id,
    workspace_path,
)


_MEDIA_EXTENSIONS = {
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".webm": "video",
    ".avi": "video",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
}
_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt"}
_LOG_EXTENSIONS = {".log", ".jsonl"}
_DOCUMENT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".bat",
    ".cfg",
    ".cmd",
    ".conf",
    ".css",
    ".html",
    ".htm",
    ".ini",
    ".js",
    ".jsx",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".xhtml",
}
_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _kind(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in _MEDIA_EXTENSIONS:
        return _MEDIA_EXTENSIONS[extension]
    if extension in _SUBTITLE_EXTENSIONS:
        return "subtitle"
    if extension in _LOG_EXTENSIONS:
        return "log"
    if extension in _DOCUMENT_EXTENSIONS:
        return "document"
    if extension == ".zip":
        return "audit"
    return "other"


def _iter_files(root: Path) -> Iterator[Path]:
    if not root.is_dir() or root.is_symlink():
        return
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directory_names[:] = [
            name
            for name in directory_names
            if name != VIDEO_IMPORT_PARTIALS_DIRNAME
            and not (directory_path / name).is_symlink()
            and not sensitive_artifact_path(name)
        ]
        for name in file_names:
            if (
                name == PRODUCTION_METADATA_FILENAME
                or (name.startswith(".studio-production.") and name.endswith(".partial"))
                or sensitive_artifact_path(name)
            ):
                continue
            path = directory_path / name
            if path.is_symlink():
                continue
            try:
                if path.is_file():
                    yield path
            except OSError:
                continue


def _walk_hash_records(value: Any) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        path = value.get("path")
        sha = value.get("sha256")
        if isinstance(path, str) and isinstance(sha, str) and _SHA_RE.fullmatch(sha):
            yield path.replace("\\", "/"), sha.upper()
        for child in value.values():
            yield from _walk_hash_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_hash_records(child)


def _manifest_data(source_directory: Path | None) -> tuple[dict[str, Any], dict[str, str]]:
    if source_directory is None:
        return {}, {}
    candidates = sorted((source_directory / "manifests").glob("*.json")) if (source_directory / "manifests").is_dir() else []
    metadata: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for candidate in candidates:
        try:
            if candidate.stat().st_size > 16 * 1024 * 1024:
                continue
            parsed = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            for key in (
                "status",
                "technical_status",
                "creative_status",
                "public_release_status",
            ):
                if key in parsed and isinstance(parsed[key], str):
                    metadata[key] = parsed[key][:256]
        for path, digest in _walk_hash_records(parsed):
            hashes[path.casefold()] = digest
    return metadata, hashes


def _title(source_directory: Path | None, production_id: str) -> str:
    if source_directory is None:
        return production_id
    for name in ("PRODUCTION_RECORD_JA.md", "CUT_PLAN_JA.md"):
        candidate = source_directory / name
        try:
            with candidate.open("r", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    if line.startswith("#"):
                        title = line.lstrip("#").strip()
                        title = re.sub(r"^制作記録\s*[—-]\s*", "", title)
                        return title[:256] or production_id
        except OSError:
            continue
    return production_id


class ProductionIndexer:
    def __init__(self, workspace: Path, database: StudioDatabase):
        self.workspace = workspace.resolve(strict=True)
        self.database = database
        self.records_root = workspace_path(self.workspace, "productions")
        self.outputs_root = workspace_path(self.workspace, "outputs/productions")

    def _production_ids(self) -> list[str]:
        identifiers: set[str] = set()
        for root in (self.records_root, self.outputs_root):
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if child.is_dir() and not child.is_symlink() and IDENTIFIER_RE.fullmatch(child.name):
                    identifiers.add(child.name)
        return sorted(identifiers)

    def _artifact(
        self,
        production_id: str,
        path: Path,
        origin: str,
        known_hashes: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            relative = relative_workspace_path(self.workspace, path)
            stat = path.stat()
        except (OSError, ValueError):
            return None
        kind = _kind(path)
        digest = known_hashes.get(relative.casefold())
        # Hash small sidecars eagerly. Large media is indexed by path and metadata;
        # existing production manifests remain the preferred digest source.
        if digest is None and stat.st_size <= 4 * 1024 * 1024 and kind not in {"video", "audio"}:
            try:
                digest = _sha256(path)
            except OSError:
                digest = None
        media_type = (
            _VIDEO_MEDIA_TYPES.get(path.suffix.casefold())
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )
        is_heavy = kind in {"video", "audio", "image"} or stat.st_size > 10 * 1024 * 1024
        return {
            "id": stable_id("art", relative.casefold()),
            "production_id": production_id,
            "rel_path": relative,
            "origin": origin,
            "name": path.name,
            "kind": kind,
            "media_type": media_type,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
            "is_heavy": is_heavy,
        }

    def _refresh_ids(self, production_ids: list[str]) -> dict[str, Any]:
        totals = {
            "productions": 0,
            "artifacts_seen": 0,
            "artifacts_changed": 0,
            "artifact_versions_added": 0,
            "skipped_files": 0,
        }
        for production_id in production_ids:
            source_directory = self.records_root / production_id
            output_directory = self.outputs_root / production_id
            source = source_directory if source_directory.is_dir() else None
            output = output_directory if output_directory.is_dir() else None
            manifest, known_hashes = _manifest_data(source)
            control = (
                read_production_metadata(self.workspace, production_id)
                if PRODUCTION_ID_RE.fullmatch(production_id)
                else None
            )
            controlled_imports: set[str] | None = None
            if control is not None:
                controlled_imports = set(control["imports"])
                for relative, digest in control["imports"].items():
                    workspace_relative = (
                        f"outputs/productions/{production_id}/{relative}"
                    )
                    known_hashes[workspace_relative.casefold()] = digest
            artifacts: list[dict[str, Any]] = []
            for origin, directory in (("record", source), ("output", output)):
                if directory is None:
                    continue
                for path in _iter_files(directory):
                    if origin == "output" and controlled_imports is not None:
                        try:
                            output_relative = path.relative_to(directory).as_posix()
                        except ValueError:
                            totals["skipped_files"] += 1
                            continue
                        if (
                            output_relative.startswith(f"{VIDEO_IMPORTS_DIRNAME}/")
                            and output_relative not in controlled_imports
                        ):
                            totals["skipped_files"] += 1
                            continue
                    artifact = self._artifact(production_id, path, origin, known_hashes)
                    if artifact is None:
                        totals["skipped_files"] += 1
                    else:
                        if control is not None and origin == "output" and artifact["kind"] == "video":
                            output_relative = path.relative_to(directory).as_posix()
                            if output_relative in control["imports"]:
                                artifact["metadata"] = bound_video_metadata(
                                    control.get("media_metadata", {}).get(output_relative), artifact,
                                )
                        artifacts.append(artifact)
            metadata = {
                "id": production_id,
                "title": (
                    control["title"]
                    if control is not None
                    else _title(source, production_id)
                ),
                "status": manifest.get("status", "discovered"),
                "technical_status": manifest.get("technical_status"),
                "creative_status": manifest.get("creative_status"),
                "public_release_status": manifest.get("public_release_status"),
                "source_rel": (
                    relative_workspace_path(self.workspace, source) if source is not None else None
                ),
                "output_rel": (
                    relative_workspace_path(self.workspace, output) if output is not None else None
                ),
            }
            result = self.database.index_production(metadata, artifacts)
            totals["productions"] += 1
            for key in ("artifacts_seen", "artifacts_changed", "artifact_versions_added"):
                totals[key] += result[key]
        totals["domain_records_restored"] = self.database.restore_domain_records_from_events()
        self.database.append_event("studio", "index", "index.refresh.completed", totals)
        return totals

    def refresh_production(self, production_id: str) -> dict[str, Any]:
        """Refresh one already-validated production without unrelated failure coupling."""

        if not isinstance(production_id, str) or IDENTIFIER_RE.fullmatch(production_id) is None:
            raise ValueError("invalid production id")
        return self._refresh_ids([production_id])

    def refresh(self) -> dict[str, Any]:
        return self._refresh_ids(self._production_ids())
