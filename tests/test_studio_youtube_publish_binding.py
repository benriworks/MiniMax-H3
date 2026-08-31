from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from tools.studio.youtube_publish_binding import (
    YouTubePublishBindingError,
    resolve_youtube_publish_binding,
)


PRODUCTION_ID = "production_" + "a" * 32
OTHER_PRODUCTION_ID = "production_" + "b" * 32
RUN_ID = "run_" + "c" * 32
REVISION_ID = "rev_" + "d" * 32
SOURCE_JOB_ID = "job_" + "e" * 32
DELIVERY_ID = "art_" + "1" * 32
CLEAN_VIDEO_ID = "art_" + "2" * 32
CAPTIONED_VIDEO_ID = "art_" + "3" * 32
ALT_VIDEO_ID = "art_" + "4" * 32
PACKAGE_KEY = "A" * 64


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "delivery_artifact_id": DELIVERY_ID,
        "video_artifact_id": CLEAN_VIDEO_ID,
        "title": "生成AIを仕事に活かす",
        "description": "検証済みの納品動画を限定公開します。",
        "tags": ["生成AI", "Shorts"],
        "category_id": "22",
        "privacy_status": "private",
        "made_for_kids": False,
        "contains_synthetic_media": True,
    }
    value.update(changes)
    return value


def _approved_gates() -> dict[str, object]:
    return {
        "gates": {
            name: {
                "decision": "approved",
                "review_count": 1,
                "open_count": 0,
            }
            for name in ("creative", "rights", "public_release")
        }
    }


class _Database:
    def __init__(self, artifacts: dict[str, dict[str, object]]) -> None:
        self.production: dict[str, object] = {
            "id": PRODUCTION_ID,
            "title": "YouTube binding test",
        }
        self.artifacts = artifacts
        self.gates = _approved_gates()

    def get_production(self, production_id: str) -> dict[str, object] | None:
        if production_id != PRODUCTION_ID:
            return None
        return copy.deepcopy(self.production)

    def get_artifact(self, artifact_id: str) -> dict[str, object] | None:
        value = self.artifacts.get(artifact_id)
        return copy.deepcopy(value) if value is not None else None

    def review_snapshot(self, production_id: str) -> dict[str, object]:
        if production_id != PRODUCTION_ID:
            raise KeyError(production_id)
        return copy.deepcopy(self.gates)


class YouTubePublishBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.clean_bytes = b"\x00\x00\x00\x18ftypmp42clean-master"
        self.captioned_bytes = b"\x00\x00\x00\x18ftypmp42captioned-master"
        self.clean_path = self._write_video(
            "clean", "master-clean.mp4", self.clean_bytes
        )
        self.captioned_path = self._write_video(
            "captioned", "master-captioned.mp4", self.captioned_bytes
        )
        self.manifest = self._manifest()
        self.delivery_path = (
            self.workspace
            / "outputs"
            / "studio"
            / "deliveries"
            / PRODUCTION_ID
            / PACKAGE_KEY
            / "delivery-package.zip"
        )
        self._write_archive()
        artifacts = {
            DELIVERY_ID: self._artifact_record(
                DELIVERY_ID,
                self.delivery_path,
                kind="delivery",
                media_type="application/zip",
            ),
            CLEAN_VIDEO_ID: self._artifact_record(
                CLEAN_VIDEO_ID,
                self.clean_path,
                kind="video",
                media_type="video/mp4",
            ),
            CAPTIONED_VIDEO_ID: self._artifact_record(
                CAPTIONED_VIDEO_ID,
                self.captioned_path,
                kind="video",
                media_type="video/mp4",
            ),
        }
        self.database = _Database(artifacts)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_video(self, directory: str, name: str, value: bytes) -> Path:
        path = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / RUN_ID
            / "assembly"
            / directory
            / name
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def _manifest(self) -> dict[str, object]:
        entries = [
            {
                "path": "video/master-clean.mp4",
                "bytes": len(self.clean_bytes),
                "sha256": _sha256_bytes(self.clean_bytes),
            },
            {
                "path": "video/master-captioned.mp4",
                "bytes": len(self.captioned_bytes),
                "sha256": _sha256_bytes(self.captioned_bytes),
            },
        ]
        return {
            "schema_version": 1,
            "policy": "studio-delivery-package-v1",
            "thumbnail_policy": "quarter-middle-three-v1",
            "audit_policy": "production-snapshot-v1",
            "production_id": PRODUCTION_ID,
            "run_id": RUN_ID,
            "revision_id": REVISION_ID,
            "source_job_id": SOURCE_JOB_ID,
            "duration_ms": 15_000,
            "metadata": {
                "title": "生成AIを仕事に活かす",
                "description": "検証用の納品パッケージです。",
            },
            "artifacts": {
                "clean_master": {
                    "id": CLEAN_VIDEO_ID,
                    "bytes": len(self.clean_bytes),
                    "sha256": _sha256_bytes(self.clean_bytes),
                },
                "captioned_master": {
                    "id": CAPTIONED_VIDEO_ID,
                    "bytes": len(self.captioned_bytes),
                    "sha256": _sha256_bytes(self.captioned_bytes),
                },
            },
            "children": {},
            "audit_snapshot_sha256": "B" * 64,
            "ffmpeg": {"version": "test", "sha256": "C" * 64},
            "package_key": PACKAGE_KEY,
            "thumbnail_timestamps_ms": [3_750, 7_500, 11_250],
            "archive_entries": entries,
        }

    def _write_archive(
        self,
        *,
        duplicate_clean: bool = False,
        archive_clean_bytes: bytes | None = None,
    ) -> None:
        self.delivery_path.parent.mkdir(parents=True, exist_ok=True)
        clean_bytes = (
            self.clean_bytes if archive_clean_bytes is None else archive_clean_bytes
        )
        with zipfile.ZipFile(
            self.delivery_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            archive.writestr("video/master-clean.mp4", clean_bytes)
            if duplicate_clean:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr("video/master-clean.mp4", clean_bytes)
            archive.writestr("video/master-captioned.mp4", self.captioned_bytes)
            archive.writestr(
                "delivery/manifest.json",
                json.dumps(
                    self.manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )

    def _artifact_record(
        self,
        artifact_id: str,
        path: Path,
        *,
        kind: str,
        media_type: str,
    ) -> dict[str, object]:
        stat = path.stat()
        return {
            "id": artifact_id,
            "production_id": PRODUCTION_ID,
            "rel_path": path.relative_to(self.workspace).as_posix(),
            "origin": "studio",
            "name": path.name,
            "kind": kind,
            "media_type": media_type,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256_file(path),
            "is_heavy": False,
            "available": True,
            "indexed_at": "2026-09-01T00:00:00+00:00",
        }

    def _refresh_delivery_registration(self) -> None:
        self.database.artifacts[DELIVERY_ID] = self._artifact_record(
            DELIVERY_ID,
            self.delivery_path,
            kind="delivery",
            media_type="application/zip",
        )

    def assert_binding_error(self, code: str, request: dict[str, object]) -> None:
        with self.assertRaises(YouTubePublishBindingError) as raised:
            resolve_youtube_publish_binding(
                self.workspace,
                self.database,
                PRODUCTION_ID,
                request,
            )
        self.assertEqual(raised.exception.code, code)

    def test_resolves_exact_delivery_video_and_release_gates(self) -> None:
        binding = resolve_youtube_publish_binding(
            self.workspace,
            self.database,
            PRODUCTION_ID,
            _request(),
        )

        self.assertEqual(binding.video_role, "clean_master")
        self.assertEqual(binding.delivery_path, self.delivery_path)
        self.assertEqual(binding.video_path, self.clean_path)
        self.assertEqual(binding.package_key, PACKAGE_KEY)
        self.assertEqual(binding.run_id, RUN_ID)
        self.assertEqual(binding.source_job_id, SOURCE_JOB_ID)
        summary = binding.public_summary()
        self.assertEqual(summary["production_id"], PRODUCTION_ID)
        self.assertEqual(summary["delivery_artifact_id"], DELIVERY_ID)
        self.assertEqual(summary["video_artifact_id"], CLEAN_VIDEO_ID)
        self.assertEqual(
            set(summary["release_gates"]),
            {"creative", "rights", "public_release"},
        )

    def test_rejects_production_record_and_registered_artifact_mismatch(self) -> None:
        self.database.production["id"] = OTHER_PRODUCTION_ID
        with self.assertRaises(KeyError):
            resolve_youtube_publish_binding(
                self.workspace,
                self.database,
                PRODUCTION_ID,
                _request(),
            )

        self.database.production["id"] = PRODUCTION_ID
        self.database.artifacts[DELIVERY_ID]["production_id"] = OTHER_PRODUCTION_ID
        self.assert_binding_error("youtube_artifact_invalid", _request())

    def test_rejects_video_bytes_changed_after_registration(self) -> None:
        original = self.clean_path.read_bytes()
        self.clean_path.write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])

        self.assert_binding_error("youtube_artifact_changed", _request())

    def test_rejects_pending_or_open_release_gate(self) -> None:
        gates = self.database.gates["gates"]
        assert isinstance(gates, dict)
        creative = gates["creative"]
        assert isinstance(creative, dict)
        creative["decision"] = "pending"
        self.assert_binding_error("youtube_release_gate_required", _request())

        creative["decision"] = "approved"
        creative["open_count"] = 1
        self.assert_binding_error("youtube_release_gate_required", _request())

    def test_rejects_selected_video_absent_from_delivery_manifest(self) -> None:
        alternate = copy.deepcopy(self.database.artifacts[CLEAN_VIDEO_ID])
        alternate["id"] = ALT_VIDEO_ID
        self.database.artifacts[ALT_VIDEO_ID] = alternate

        self.assert_binding_error(
            "youtube_video_not_in_delivery",
            _request(video_artifact_id=ALT_VIDEO_ID),
        )

    def test_rejects_malformed_and_duplicate_delivery_archives(self) -> None:
        self.delivery_path.write_bytes(b"this is not a ZIP archive")
        self._refresh_delivery_registration()
        self.assert_binding_error("youtube_delivery_invalid", _request())

        self._write_archive(duplicate_clean=True)
        self._refresh_delivery_registration()
        self.assert_binding_error("youtube_delivery_invalid", _request())

    def test_rejects_modified_zip_entry_even_if_outer_artifact_is_reregistered(self) -> None:
        changed = bytes([self.clean_bytes[0] ^ 0xFF]) + self.clean_bytes[1:]
        self._write_archive(archive_clean_bytes=changed)
        self._refresh_delivery_registration()

        self.assert_binding_error("youtube_delivery_invalid", _request())


if __name__ == "__main__":
    unittest.main()
