from __future__ import annotations

import hashlib
import io
import json
import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from tools.studio.database import SCHEMA_VERSION, StudioDatabase
from tools.studio.indexer import ProductionIndexer
from tools.studio.media_metadata import (
    VIDEO_METADATA_KEYS, bound_video_metadata, normalize_video_metadata,
    parse_frame_rate, video_metadata_from_probe,
)
from tools.studio.production_intake import PRODUCTION_METADATA_FILENAME, read_production_metadata
from tools.studio.security import stable_id
from tools.studio.service import StudioService


PRODUCTION_ID = "production_" + "a" * 32
COPY_ID = "production_" + "b" * 32
VIDEO_BYTES = b"metadata-test-video"
PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
         "duration": "15.015", "avg_frame_rate": "30000/1001", "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "15.100"},
}
EXPECTED = {
    "duration_seconds": 15.015, "width": 1080, "height": 1920,
    "fps": 30000 / 1001, "has_audio": True, "video_codec": "h264",
}
UNKNOWN = {key: None for key in VIDEO_METADATA_KEYS}


class MediaMetadataParsingTests(unittest.TestCase):
    def test_rational_fps_is_not_truncated_and_invalid_rates_stay_unknown(self) -> None:
        self.assertEqual(parse_frame_rate("30000/1001"), 30000 / 1001)
        self.assertEqual(parse_frame_rate("23.976"), 23.976)
        for value in ("0/0", "1/0", "NaN", "inf", "-24", "24fps", "24/1/2",
                      "1+1", "1e2", " 24 ", "9" * 100, True, 0, math.nan, math.inf):
            with self.subTest(value=value):
                self.assertIsNone(parse_frame_rate(value))

    def test_video_stream_duration_precedes_container_and_invalid_avg_uses_real_rate(self) -> None:
        self.assertEqual(video_metadata_from_probe(PROBE), EXPECTED)
        data = {"streams": [{**PROBE["streams"][0], "avg_frame_rate": "0/0", "duration": "N/A"}],
                "format": PROBE["format"]}
        self.assertEqual(video_metadata_from_probe(data), {
            **EXPECTED, "duration_seconds": 15.1, "fps": 30.0, "has_audio": False,
        })
        data["streams"].insert(0, {"codec_type": "video", "width": 1,
                                    "disposition": {"attached_pic": 1}})
        self.assertEqual(video_metadata_from_probe(data)["width"], 1080)

    def test_malformed_probe_and_untrusted_persisted_fields_do_not_claim_facts(self) -> None:
        for value in (None, [], {"streams": None}, {"streams": []}):
            self.assertEqual(video_metadata_from_probe(value), UNKNOWN)
        data = normalize_video_metadata({
            "duration_seconds": math.inf, "width": True, "height": -1,
            "fps": math.nan, "has_audio": "yes", "video_codec": "<script>",
            "secret": "not-exported",
        })
        self.assertEqual(data, UNKNOWN)
        self.assertEqual(normalize_video_metadata({"duration_seconds": 10 ** 1000}), UNKNOWN)

    def test_bound_facts_require_digest_bytes_and_timestamp(self) -> None:
        identity = {"sha256": "A" * 64, "bytes": 100, "mtime_ns": 10}
        bound = {**identity, "metadata": EXPECTED}
        self.assertEqual(bound_video_metadata(bound, identity), EXPECTED)
        for change in ({"sha256": "B" * 64}, {"bytes": 101}, {"mtime_ns": 11},
                       {"bytes": True}, {"sha256": None}):
            self.assertEqual(bound_video_metadata(bound, {**identity, **change}), UNKNOWN)


class MediaMetadataPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.probe = mock.Mock(return_value=PROBE)
        self.patcher = mock.patch("tools.studio.production_intake._resolve_ffprobe",
                                  return_value=("ffprobe", self.probe))
        self.patcher.start()
        self.service = StudioService(self.workspace)
        self.service.create_production({"schema_version": 1, "production_id": PRODUCTION_ID,
                                        "title": "Metadata test"})

    def tearDown(self) -> None:
        self.service.close()
        self.patcher.stop()
        self.temporary.cleanup()

    def import_video(self, *, filename: str = "source.mp4") -> dict:
        return self.service.import_production_video(
            PRODUCTION_ID, stream=io.BytesIO(VIDEO_BYTES), filename_header=filename,
            content_type="video/mp4", content_length=len(VIDEO_BYTES),
        )

    def control_path(self) -> Path:
        return self.workspace / "outputs" / "productions" / PRODUCTION_ID / PRODUCTION_METADATA_FILENAME

    def test_import_restart_reindex_and_sqlite_rebuild_keep_facts_without_new_probe(self) -> None:
        artifact = self.import_video()["artifact"]
        self.assertEqual(artifact["metadata"], EXPECTED)
        self.assertEqual(self.probe.call_count, 1)
        self.service.close()
        self.service = StudioService(self.workspace)
        self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], EXPECTED)
        detail = self.service.production_detail(PRODUCTION_ID)
        self.assertEqual(detail["artifacts"][0]["metadata"], EXPECTED)
        rebuilt = StudioDatabase(self.workspace / "rebuilt.sqlite3", workspace=self.workspace)
        ProductionIndexer(self.workspace, rebuilt).refresh_production(PRODUCTION_ID)
        self.assertEqual(rebuilt.get_artifact_view(artifact["id"])["metadata"], EXPECTED)
        self.assertEqual(self.probe.call_count, 1)

    def test_changed_file_facts_are_hidden_before_and_after_reindex(self) -> None:
        artifact = self.import_video()["artifact"]
        path = self.workspace / artifact["rel_path"]
        path.write_bytes(b"x" * len(VIDEO_BYTES))
        os.utime(path, ns=(artifact["mtime_ns"] + 10_000_000, artifact["mtime_ns"] + 10_000_000))
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], UNKNOWN)
        self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], UNKNOWN)
        self.assertEqual(self.probe.call_count, 1)

    def test_missing_file_facts_are_unknown_without_a_probe(self) -> None:
        artifact = self.import_video()["artifact"]
        (self.workspace / artifact["rel_path"]).unlink()
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], UNKNOWN)
        self.assertEqual(self.probe.call_count, 1)

    def test_legacy_control_stays_usable_and_dedupe_backfills_current_facts(self) -> None:
        artifact = self.import_video()["artifact"]
        control = read_production_metadata(self.workspace, PRODUCTION_ID)
        control.pop("media_metadata")
        self.control_path().write_text(json.dumps(control), encoding="utf-8")
        self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], UNKNOWN)
        retry = self.import_video(filename="different-name.mp4")
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(retry["artifact"]["id"], artifact["id"])
        self.assertEqual(retry["artifact"]["metadata"], EXPECTED)
        self.assertEqual(self.probe.call_count, 2)

    def test_malformed_or_mismatched_control_facts_do_not_make_video_inaccessible(self) -> None:
        artifact = self.import_video()["artifact"]
        original = read_production_metadata(self.workspace, PRODUCTION_ID)
        relative = next(iter(original["imports"]))
        for bad in ("invalid", {relative: {"metadata": EXPECTED}},
                    {relative: {**original["media_metadata"][relative], "sha256": "B" * 64}},
                    {relative: {**original["media_metadata"][relative], "metadata": {"width": True}}}):
            with self.subTest(bad=bad):
                self.control_path().write_text(json.dumps({**original, "media_metadata": bad}), encoding="utf-8")
                self.service.indexer.refresh_production(PRODUCTION_ID)
                current = self.service.artifact(artifact["id"])
                self.assertTrue(current["available"])
                self.assertEqual(current["metadata"], UNKNOWN)

    def test_duplicate_rebinds_metadata_to_its_own_new_file(self) -> None:
        artifact = self.import_video()["artifact"]
        self.service.duplicate_production(PRODUCTION_ID, {
            "schema_version": 1, "operation_id": "production_library_op_" + "c" * 32,
            "production_id": COPY_ID, "title": "Copy", "include_imports": True,
        })
        detail = self.service.production_detail(COPY_ID)
        copy = next(item for item in detail["artifacts"] if item["kind"] == "video")
        self.assertNotEqual(copy["id"], artifact["id"])
        self.assertEqual(copy["metadata"], EXPECTED)
        self.assertEqual(copy["sha256"], artifact["sha256"])

    def test_database_v9_migrates_without_probe_or_fabricated_legacy_facts(self) -> None:
        artifact = self.import_video()["artifact"]
        database_path = self.service.database.path
        self.service.close()
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript(
                "ALTER TABLE artifacts DROP COLUMN media_metadata_json;"
                "UPDATE schema_meta SET value='9' WHERE key='schema_version';"
            )
        migrated = StudioDatabase(database_path, workspace=self.workspace)
        self.assertEqual(migrated.get_artifact_view(artifact["id"])["metadata"], UNKNOWN)
        with migrated.session() as connection:
            version = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
        self.assertEqual(version, str(SCHEMA_VERSION))
        self.assertEqual(self.probe.call_count, 1)

    def test_generated_registration_preserves_facts_only_for_same_identity(self) -> None:
        relative = "outputs/studio/metadata-test.mp4"
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(VIDEO_BYTES)
        stat = path.stat()
        artifact = {
            "id": stable_id("art", relative.casefold()), "rel_path": relative, "name": path.name,
            "kind": "video", "media_type": "video/mp4", "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "sha256": hashlib.sha256(VIDEO_BYTES).hexdigest().upper(),
            "is_heavy": True, "metadata": EXPECTED,
        }
        first = self.service.database.register_studio_artifact(PRODUCTION_ID, artifact)
        self.assertNotIn("metadata", first)
        self.assertNotIn("metadata", self.service.database.get_artifact(first["id"]))
        self.assertEqual(self.service.artifact(first["id"])["metadata"], EXPECTED)
        without_facts = {key: value for key, value in artifact.items() if key != "metadata"}
        same = self.service.database.register_studio_artifact(PRODUCTION_ID, without_facts)
        self.assertNotIn("metadata", same)
        self.assertEqual(self.service.artifact(same["id"])["metadata"], EXPECTED)
        rebuilt = StudioDatabase(self.service.database.path.with_name("rebuilt.sqlite3"), workspace=self.workspace)
        ProductionIndexer(self.workspace, rebuilt).refresh_production(PRODUCTION_ID)
        self.assertEqual(rebuilt.get_artifact_view(artifact["id"])["metadata"], EXPECTED)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
        changed = self.service.database.register_studio_artifact(PRODUCTION_ID, {
            **without_facts, "mtime_ns": path.stat().st_mtime_ns,
        })
        self.assertNotIn("metadata", changed)
        self.assertEqual(self.service.artifact(changed["id"])["metadata"], UNKNOWN)

    def test_generated_output_outside_imports_keeps_bound_facts_on_reindex(self) -> None:
        relative = f"outputs/productions/{PRODUCTION_ID}/generated.mp4"
        path = self.workspace / relative
        path.write_bytes(VIDEO_BYTES)
        stat = path.stat()
        digest = hashlib.sha256(VIDEO_BYTES).hexdigest().upper()
        artifact = {
            "id": stable_id("art", relative.casefold()), "rel_path": relative, "name": path.name,
            "origin": "output", "kind": "video", "media_type": "video/mp4", "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "sha256": digest, "is_heavy": True, "metadata": EXPECTED,
        }
        self.service.database.index_production({"id": PRODUCTION_ID}, [artifact])
        with mock.patch("tools.studio.indexer._manifest_data", return_value=({}, {relative.casefold(): digest})):
            self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], EXPECTED)
        with mock.patch("tools.studio.indexer._manifest_data", return_value=({}, {relative.casefold(): "B" * 64})):
            self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.artifact(artifact["id"])["metadata"], UNKNOWN)


if __name__ == "__main__":
    unittest.main()
