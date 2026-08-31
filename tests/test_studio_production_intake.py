from __future__ import annotations

import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.database import StudioDatabase
from tools.studio.indexer import ProductionIndexer
from tools.studio.production_intake import (
    MAX_VIDEO_IMPORT_BYTES,
    PRODUCTION_METADATA_FILENAME,
    ProductionIntakeError,
    VIDEO_IMPORT_PARTIALS_DIRNAME,
    cleanup_stale_video_import_partials,
    create_production_files,
    read_production_metadata,
    stream_video_import,
    validate_production_create_payload,
    validate_video_import_headers,
)
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService


PRODUCTION_ID = "production_" + "a" * 32
SECOND_PRODUCTION_ID = "production_" + "b" * 32
VIDEO_ONE = b"fake-video-one"
VIDEO_TWO = b"fake-video-two"


def _create_body(production_id: str = PRODUCTION_ID, title: str = "テスト制作") -> dict[str, object]:
    return {
        "schema_version": 1,
        "production_id": production_id,
        "title": title,
    }


def _probe(_tool: str, _path: Path, *, cwd: Path) -> dict[str, object]:
    del cwd
    return {
        "streams": [{"codec_type": "video", "codec_name": "h264"}],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    }


class ProductionIntakeContractTests(unittest.TestCase):
    def test_create_schema_and_title_bound_are_exact(self) -> None:
        self.assertEqual(validate_production_create_payload(_create_body()), _create_body())
        for body in (
            {},
            {**_create_body(), "extra": True},
            {**_create_body(), "schema_version": True},
            {**_create_body(), "production_id": "production_" + "A" * 32},
            {**_create_body(), "title": " padded "},
            {**_create_body(), "title": "x" * 121},
        ):
            with self.subTest(body=body):
                with self.assertRaises(ProductionIntakeError):
                    validate_production_create_payload(body)

    def test_video_headers_reject_paths_and_bounds_but_allow_browser_octet_stream(self) -> None:
        accepted = validate_video_import_headers(
            "movie.mp4", "application/octet-stream", 1
        )
        self.assertEqual(accepted[1], ".mp4")
        self.assertEqual(accepted[2], 1)
        for filename, media_type, length in (
            ("..%2Fevil.mp4", "video/mp4", 10),
            ("C%3Aevil.mp4", "video/mp4", 10),
            ("movie.txt", "video/mp4", 10),
            ("movie.mp4", "text/plain", 10),
            ("movie.mp4", "video/mp4", 0),
            ("movie.mp4", "video/mp4", MAX_VIDEO_IMPORT_BYTES + 1),
        ):
            with self.subTest(filename=filename, media_type=media_type, length=length):
                with self.assertRaises(ProductionIntakeError):
                    validate_video_import_headers(filename, media_type, length)


class ProductionIntakeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.service = StudioService(self.workspace)

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def test_create_retry_and_conflict_preserve_exact_control_title(self) -> None:
        first = self.service.create_production(_create_body())
        retry = self.service.create_production(_create_body())

        self.assertFalse(first["deduplicated"])
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(first["production"]["id"], PRODUCTION_ID)
        self.assertEqual(retry["production"]["title"], "テスト制作")
        metadata = read_production_metadata(self.workspace, PRODUCTION_ID)
        self.assertEqual(
            metadata,
            {
                "schema_version": 1,
                "production_id": PRODUCTION_ID,
                "title": "テスト制作",
                "imports": {},
            },
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_production(_create_body(title="別タイトル"))
        self.assertEqual(raised.exception.code, "production_id_conflict")

    def test_index_failure_retains_durable_control_for_same_id_retry(self) -> None:
        with mock.patch.object(
            self.service.indexer,
            "refresh_production",
            side_effect=RuntimeError("simulated index failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.create_production(_create_body())

        metadata = read_production_metadata(self.workspace, PRODUCTION_ID)
        self.assertIsNotNone(metadata)
        retry = self.service.create_production(_create_body())
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(retry["production"]["title"], "テスト制作")

    @mock.patch("tools.studio.production_intake._resolve_ffprobe", return_value=("ffprobe", _probe))
    def test_same_bytes_dedupe_across_filename_and_extension(self, _resolve: mock.Mock) -> None:
        self.service.create_production(_create_body())
        first = self.service.import_production_video(
            PRODUCTION_ID,
            stream=io.BytesIO(VIDEO_ONE),
            filename_header="first.mp4",
            content_type="video/mp4",
            content_length=len(VIDEO_ONE),
        )
        second = self.service.import_production_video(
            PRODUCTION_ID,
            stream=io.BytesIO(VIDEO_ONE),
            filename_header="renamed.mov",
            content_type="application/octet-stream",
            content_length=len(VIDEO_ONE),
        )

        self.assertFalse(first["deduplicated"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(first["artifact"]["id"], second["artifact"]["id"])
        self.assertEqual(first["artifact"]["origin"], "output")
        digest = hashlib.sha256(VIDEO_ONE).hexdigest().upper()
        self.assertEqual(first["artifact"]["sha256"], digest)
        self.assertTrue(first["artifact"]["name"].startswith(digest.lower()[:16] + "_"))
        metadata = read_production_metadata(self.workspace, PRODUCTION_ID)
        assert metadata is not None
        self.assertEqual(list(metadata["imports"].values()), [digest])
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        imported = [item for item in detail["artifacts"] if item["sha256"] == digest]
        self.assertEqual(len(imported), 1)
        self.assertFalse(any(item["name"] == PRODUCTION_METADATA_FILENAME for item in detail["artifacts"]))
        import_events = [
            event
            for event in detail["events"]
            if event["event_type"] == "production.media_imported"
        ]
        self.assertEqual(len(import_events), 2)
        self.assertTrue(import_events[0]["payload"]["deduplicated"])

    @mock.patch("tools.studio.production_intake._resolve_ffprobe")
    def test_cross_extension_dedupe_rechecks_existing_destination_container(
        self, resolve: mock.Mock
    ) -> None:
        self.service.create_production(_create_body())
        digest = hashlib.sha256(VIDEO_ONE).hexdigest().upper()
        relative = f"imports/{digest.lower()[:16]}_tampered.mp4"
        destination = self.workspace / "outputs" / "productions" / PRODUCTION_ID / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(VIDEO_ONE)
        control = destination.parent.parent / PRODUCTION_METADATA_FILENAME
        control.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "production_id": PRODUCTION_ID,
                    "title": "テスト制作",
                    "imports": {relative: digest},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        matroska_probe = mock.Mock(
            return_value={
                "streams": [{"codec_type": "video", "codec_name": "vp9"}],
                "format": {"format_name": "matroska,webm"},
            }
        )
        resolve.return_value = ("ffprobe", matroska_probe)

        with self.assertRaises(RequestValidationError) as raised:
            self.service.import_production_video(
                PRODUCTION_ID,
                stream=io.BytesIO(VIDEO_ONE),
                filename_header="same.webm",
                content_type="video/webm",
                content_length=len(VIDEO_ONE),
            )

        self.assertEqual(raised.exception.code, "invalid_video_media")
        self.assertEqual(matroska_probe.call_count, 2)
        self.assertEqual(destination.read_bytes(), VIDEO_ONE)
        self.assertFalse(
            (destination.parent.parent / VIDEO_IMPORT_PARTIALS_DIRNAME).exists()
        )

    @mock.patch("tools.studio.production_intake._resolve_ffprobe")
    def test_probe_failure_cleans_partial_and_does_not_publish(self, resolve: mock.Mock) -> None:
        def reject(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("probe failed with a private local path")

        resolve.return_value = ("ffprobe", reject)
        self.service.create_production(_create_body())
        with self.assertRaises(RequestValidationError) as raised:
            self.service.import_production_video(
                PRODUCTION_ID,
                stream=io.BytesIO(VIDEO_ONE),
                filename_header="bad.mp4",
                content_type="video/mp4",
                content_length=len(VIDEO_ONE),
            )
        self.assertEqual(raised.exception.code, "invalid_video_media")
        production = self.workspace / "outputs" / "productions" / PRODUCTION_ID
        self.assertFalse((production / VIDEO_IMPORT_PARTIALS_DIRNAME).exists())
        self.assertFalse((production / "imports").exists())
        metadata = read_production_metadata(self.workspace, PRODUCTION_ID)
        assert metadata is not None
        self.assertEqual(metadata["imports"], {})

    @mock.patch("tools.studio.production_intake._resolve_ffprobe", return_value=("ffprobe", _probe))
    def test_concurrent_imports_are_serialized_without_lost_metadata(self, _resolve: mock.Mock) -> None:
        self.service.create_production(_create_body())
        barrier = threading.Barrier(3)
        results: list[dict[str, object]] = []
        failures: list[BaseException] = []

        def upload(name: str, data: bytes) -> None:
            try:
                barrier.wait()
                results.append(
                    self.service.import_production_video(
                        PRODUCTION_ID,
                        stream=io.BytesIO(data),
                        filename_header=name,
                        content_type="video/mp4",
                        content_length=len(data),
                    )
                )
            except BaseException as exc:  # pragma: no cover - assertion reports details
                failures.append(exc)

        threads = [
            threading.Thread(target=upload, args=("one.mp4", VIDEO_ONE)),
            threading.Thread(target=upload, args=("two.mp4", VIDEO_TWO)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(10)

        self.assertFalse(failures, failures)
        self.assertEqual(len(results), 2)
        metadata = read_production_metadata(self.workspace, PRODUCTION_ID)
        assert metadata is not None
        self.assertEqual(set(metadata["imports"].values()), {
            hashlib.sha256(VIDEO_ONE).hexdigest().upper(),
            hashlib.sha256(VIDEO_TWO).hexdigest().upper(),
        })
        imports = self.workspace / "outputs" / "productions" / PRODUCTION_ID / "imports"
        self.assertEqual(len(list(imports.iterdir())), 2)


class ProductionIntakeDurabilityTests(unittest.TestCase):
    def test_metadata_duplicate_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            create_production_files(workspace, _create_body())
            control = (
                workspace
                / "outputs"
                / "productions"
                / PRODUCTION_ID
                / PRODUCTION_METADATA_FILENAME
            )
            control.write_text(
                '{"schema_version":1,"production_id":"'
                + PRODUCTION_ID
                + '","title":"first","title":"second","imports":{}}',
                encoding="utf-8",
            )

            with self.assertRaises(ProductionIntakeError) as raised:
                read_production_metadata(workspace, PRODUCTION_ID)
            self.assertEqual(raised.exception.code, "invalid_production_metadata")

    def test_startup_rejects_broken_staging_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            create_production_files(workspace, _create_body())
            production = workspace / "outputs" / "productions" / PRODUCTION_ID
            partials = production / VIDEO_IMPORT_PARTIALS_DIRNAME
            try:
                partials.symlink_to(
                    workspace / "missing-staging-target",
                    target_is_directory=True,
                )
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            with self.assertRaises(ProductionIntakeError) as raised:
                cleanup_stale_video_import_partials(workspace)
            self.assertEqual(raised.exception.code, "unsafe_video_import_staging")

    def test_startup_cleans_exact_partials_and_indexer_excludes_unregistered_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            create_production_files(workspace, _create_body())
            production = workspace / "outputs" / "productions" / PRODUCTION_ID
            partials = production / VIDEO_IMPORT_PARTIALS_DIRNAME
            partials.mkdir()
            (partials / ("c" * 32 + ".part")).write_bytes(b"stale")
            (production / (".studio-production." + "d" * 32 + ".partial")).write_bytes(b"stale")
            legitimate_part = production / "review.part"
            legitimate_part.write_bytes(b"operator-owned")

            service = StudioService(workspace)
            try:
                self.assertFalse(partials.exists())
                self.assertFalse(any(path.name.endswith(".partial") for path in production.iterdir()))
                imports = production / "imports"
                imports.mkdir()
                orphan = imports / ("e" * 16 + "_orphan.mp4")
                orphan.write_bytes(VIDEO_ONE)
                service.indexer.refresh()
                detail = service.production_detail(PRODUCTION_ID)
                assert detail is not None
                self.assertEqual(detail["production"]["title"], "テスト制作")
                self.assertFalse(any(item["name"] == orphan.name for item in detail["artifacts"]))
                self.assertTrue(any(item["name"] == legitimate_part.name for item in detail["artifacts"]))
            finally:
                service.close()

    @mock.patch("tools.studio.production_intake._resolve_ffprobe", return_value=("ffprobe", _probe))
    def test_index_refresh_and_sqlite_rebuild_keep_one_output_artifact(self, _resolve: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            service = StudioService(workspace)
            service.create_production(_create_body())
            imported = service.import_production_video(
                PRODUCTION_ID,
                stream=io.BytesIO(VIDEO_ONE),
                filename_header="source.mp4",
                content_type="video/mp4",
                content_length=len(VIDEO_ONE),
            )
            artifact_id = imported["artifact"]["id"]
            service.close()

            database_path = workspace / "outputs" / "studio" / "studio.sqlite3"
            database_path.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(database_path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            database = StudioDatabase(database_path, workspace=workspace)
            indexer = ProductionIndexer(workspace, database)
            indexer.refresh()
            indexer.refresh()
            detail = database.get_production_detail(PRODUCTION_ID)
            assert detail is not None
            self.assertEqual(detail["production"]["title"], "テスト制作")
            artifacts = [item for item in detail["artifacts"] if item["available"]]
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0]["id"], artifact_id)
            self.assertEqual(artifacts[0]["origin"], "output")


class ProductionIntakeHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "production-intake-session-token-at-least-32-chars"
        self.server = create_server(
            self.workspace,
            host="127.0.0.1",
            port=0,
            session_token=self.token,
            initial_refresh=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temporary.cleanup()

    def _json_post(self, path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        encoded = json.dumps(body).encode("utf-8")
        self.connection.request(
            "POST",
            path,
            body=encoded,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(encoded)),
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_create_endpoint_is_idempotent_and_conflict_is_409(self) -> None:
        status, first = self._json_post("/api/productions", _create_body())
        retry_status, retry = self._json_post("/api/productions", _create_body())
        conflict_status, conflict = self._json_post(
            "/api/productions", _create_body(title="別タイトル")
        )
        self.assertEqual(status, 201)
        self.assertFalse(first["deduplicated"])
        self.assertEqual(retry_status, 201)
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict["error"]["code"], "production_id_conflict")

    def test_raw_import_requires_content_length_before_service_dispatch(self) -> None:
        self.connection.putrequest(
            "POST",
            f"/api/productions/{PRODUCTION_ID}/artifacts/import-video",
        )
        self.connection.putheader("Content-Type", "video/mp4")
        self.connection.putheader("X-Studio-Filename-Encoded", "source.mp4")
        self.connection.putheader("X-Studio-Token", self.token)
        self.connection.endheaders()
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 422)
        self.assertEqual(payload["error"]["code"], "invalid_content_length")

    def test_raw_import_rejects_ambiguous_filename_headers(self) -> None:
        self.connection.putrequest(
            "POST",
            f"/api/productions/{PRODUCTION_ID}/artifacts/import-video",
        )
        self.connection.putheader("Content-Type", "video/mp4")
        self.connection.putheader("Content-Length", "1")
        self.connection.putheader("X-Studio-Filename-Encoded", "first.mp4")
        self.connection.putheader("X-Studio-Filename-Encoded", "second.mp4")
        self.connection.putheader("X-Studio-Token", self.token)
        self.connection.endheaders(b"x")
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 422)
        self.assertEqual(payload["error"]["code"], "invalid_video_filename")

    @mock.patch("tools.studio.production_intake._resolve_ffprobe", return_value=("ffprobe", _probe))
    def test_raw_import_endpoint_returns_indexed_artifact(self, _resolve: mock.Mock) -> None:
        status, _created = self._json_post("/api/productions", _create_body())
        self.assertEqual(status, 201)
        self.connection.request(
            "POST",
            f"/api/productions/{PRODUCTION_ID}/artifacts/import-video",
            body=VIDEO_ONE,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(VIDEO_ONE)),
                "X-Studio-Filename-Encoded": "browser-file.mp4",
                "X-Studio-Token": self.token,
            },
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 201)
        self.assertFalse(payload["deduplicated"])
        self.assertEqual(payload["artifact"]["origin"], "output")
        self.assertEqual(payload["artifact"]["sha256"], hashlib.sha256(VIDEO_ONE).hexdigest().upper())


if __name__ == "__main__":
    unittest.main()
