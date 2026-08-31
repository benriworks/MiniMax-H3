from __future__ import annotations

import hashlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from tools.studio.database import SCHEMA_VERSION, StudioDatabase
from tools.studio.production_intake import read_production_metadata
from tools.studio.production_library import (
    ProductionLibraryValidationError,
    validate_production_archive_payload,
    validate_production_duplicate_payload,
    validate_production_rename_payload,
)
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService


PRODUCTION_ID = "production_" + "1" * 32
SECOND_PRODUCTION_ID = "production_" + "2" * 32
THIRD_PRODUCTION_ID = "production_" + "3" * 32
OPERATION_ONE = "production_library_op_" + "a" * 32
OPERATION_TWO = "production_library_op_" + "b" * 32
OPERATION_THREE = "production_library_op_" + "c" * 32
VIDEO = b"fake-production-library-video"


def _create(production_id: str, title: str) -> dict[str, object]:
    return {"schema_version": 1, "production_id": production_id, "title": title}


def _rename(operation_id: str, expected_title: str, title: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "expected_title": expected_title,
        "title": title,
    }


def _archive(operation_id: str, expected: bool, archived: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "expected_archived": expected,
        "archived": archived,
    }


def _duplicate(
    operation_id: str,
    production_id: str,
    title: str,
    *,
    include_imports: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "production_id": production_id,
        "title": title,
        "include_imports": include_imports,
    }


def _probe(_tool: str, _path: Path, *, cwd: Path) -> dict[str, object]:
    del cwd
    return {
        "streams": [{"codec_type": "video", "codec_name": "h264"}],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    }


class ProductionLibraryContractTests(unittest.TestCase):
    def test_closed_requests_reject_extra_fields_and_noop_transitions(self) -> None:
        self.assertEqual(
            validate_production_rename_payload(
                _rename(OPERATION_ONE, "Before", "After")
            )["title"],
            "After",
        )
        self.assertTrue(
            validate_production_archive_payload(
                _archive(OPERATION_ONE, False, True)
            )["archived"]
        )
        self.assertEqual(
            validate_production_duplicate_payload(
                _duplicate(OPERATION_ONE, SECOND_PRODUCTION_ID, "Copy")
            )["production_id"],
            SECOND_PRODUCTION_ID,
        )
        for body, validator in (
            ({**_rename(OPERATION_ONE, "Before", "After"), "extra": True}, validate_production_rename_payload),
            (_rename(OPERATION_ONE, "Same", "Same"), validate_production_rename_payload),
            (_archive(OPERATION_ONE, False, False), validate_production_archive_payload),
            ({**_duplicate(OPERATION_ONE, SECOND_PRODUCTION_ID, "Copy"), "include_imports": 1}, validate_production_duplicate_payload),
        ):
            with self.subTest(body=body):
                with self.assertRaises(ProductionLibraryValidationError):
                    validator(body)


class ProductionLibraryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.service = StudioService(self.workspace)
        self.service.create_production(_create(PRODUCTION_ID, "Original"))

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def _events(self, production_id: str, event_type: str) -> list[dict[str, object]]:
        detail = self.service.production_detail(production_id)
        assert detail is not None
        return [
            event for event in detail["events"] if event["event_type"] == event_type
        ]

    def test_rename_retry_is_idempotent_and_survives_reindex(self) -> None:
        first = self.service.rename_production(
            PRODUCTION_ID, _rename(OPERATION_ONE, "Original", "Display name")
        )
        retry = self.service.rename_production(
            PRODUCTION_ID, _rename(OPERATION_ONE, "Original", "Display name")
        )
        self.assertFalse(first["deduplicated"])
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(first["production"]["id"], PRODUCTION_ID)
        self.assertEqual(retry["production"]["title"], "Display name")
        self.assertEqual(
            read_production_metadata(self.workspace, PRODUCTION_ID)["title"],
            "Display name",
        )
        self.service.indexer.refresh_production(PRODUCTION_ID)
        self.assertEqual(self.service.production_detail(PRODUCTION_ID)["production"]["title"], "Display name")
        self.assertEqual(
            len(self._events(PRODUCTION_ID, "production.library.renamed")), 1
        )

        with self.assertRaises(RequestValidationError) as raised:
            self.service.rename_production(
                PRODUCTION_ID,
                _rename(OPERATION_ONE, "Display name", "Operation collision"),
            )
        self.assertEqual(
            raised.exception.code, "production_library_operation_conflict"
        )
        self.assertEqual(
            len(self._events(PRODUCTION_ID, "production.library.renamed")), 1
        )

    def test_archive_hides_by_default_and_never_removes_artifacts(self) -> None:
        marker = (
            self.workspace
            / "outputs"
            / "productions"
            / PRODUCTION_ID
            / "operator-note.txt"
        )
        marker.write_text("preserve", encoding="utf-8")
        self.service.indexer.refresh_production(PRODUCTION_ID)

        first = self.service.archive_production(
            PRODUCTION_ID, _archive(OPERATION_ONE, False, True)
        )
        retry = self.service.archive_production(
            PRODUCTION_ID, _archive(OPERATION_ONE, False, True)
        )
        self.assertTrue(first["production"]["archived"])
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(self.service.list_productions()["count"], 0)
        archived = self.service.list_productions(include_archived=True)["productions"]
        self.assertEqual([item["id"] for item in archived], [PRODUCTION_ID])
        self.assertTrue(marker.is_file())
        self.assertEqual(
            len(self._events(PRODUCTION_ID, "production.library.archived")), 1
        )

        unarchived = self.service.archive_production(
            PRODUCTION_ID, _archive(OPERATION_TWO, True, False)
        )
        self.assertFalse(unarchived["production"]["archived"])
        self.assertEqual(self.service.list_productions()["count"], 1)
        self.assertTrue(marker.is_file())

    def test_library_state_and_operation_ledger_restore_from_audit_events(self) -> None:
        body = _archive(OPERATION_ONE, False, True)
        self.service.archive_production(PRODUCTION_ID, body)
        with closing(sqlite3.connect(self.service.database.path)) as connection:
            connection.executescript(
                """
                DROP TRIGGER production_library_states_immutable_delete;
                DROP TRIGGER production_library_operations_immutable_delete;
                DROP TRIGGER production_library_operations_immutable_update;
                DROP TABLE production_library_operations;
                DROP TABLE production_library_states;
                """
            )
        self.service.database.initialize()
        restored = self.service.database.restore_domain_records_from_events()
        self.assertEqual(restored["production_library_states"], 1)
        self.assertEqual(restored["production_library_operations"], 1)
        retry = self.service.archive_production(PRODUCTION_ID, body)
        self.assertTrue(retry["deduplicated"])
        self.assertTrue(retry["production"]["archived"])
        self.assertEqual(
            len(self._events(PRODUCTION_ID, "production.library.archived")), 1
        )

    @mock.patch(
        "tools.studio.production_intake._resolve_ffprobe",
        return_value=("ffprobe", _probe),
    )
    def test_duplicate_reuses_imports_without_changing_source_identity(
        self, _resolve: mock.Mock
    ) -> None:
        imported = self.service.import_production_video(
            PRODUCTION_ID,
            stream=io.BytesIO(VIDEO),
            filename_header="source.mp4",
            content_type="video/mp4",
            content_length=len(VIDEO),
        )
        source_artifact_id = imported["artifact"]["id"]
        body = _duplicate(
            OPERATION_THREE, SECOND_PRODUCTION_ID, "Reusable copy"
        )
        first = self.service.duplicate_production(PRODUCTION_ID, body)
        retry = self.service.duplicate_production(PRODUCTION_ID, body)

        self.assertFalse(first["deduplicated"])
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(first["production"]["id"], SECOND_PRODUCTION_ID)
        self.assertEqual(first["imported_artifact_count"], 1)
        source = self.service.production_detail(PRODUCTION_ID)
        target = self.service.production_detail(SECOND_PRODUCTION_ID)
        assert source is not None and target is not None
        self.assertTrue(any(item["id"] == source_artifact_id for item in source["artifacts"]))
        self.assertFalse(any(item["id"] == source_artifact_id for item in target["artifacts"]))
        target_video = next(item for item in target["artifacts"] if item["kind"] == "video")
        self.assertEqual(target_video["sha256"], hashlib.sha256(VIDEO).hexdigest().upper())
        self.assertEqual(
            len(self._events(SECOND_PRODUCTION_ID, "production.library.duplicated")),
            1,
        )

    def test_tracked_production_is_explicitly_read_only(self) -> None:
        tracked_id = "TRACKED_LIBRARY_TEST"
        tracked = self.workspace / "productions" / tracked_id
        tracked.mkdir(parents=True)
        (tracked / "PRODUCTION_RECORD_JA.md").write_text(
            "# Tracked title\n", encoding="utf-8"
        )
        self.service.indexer.refresh_production(tracked_id)
        listed = self.service.list_productions(include_archived=True)["productions"]
        tracked_record = next(item for item in listed if item["id"] == tracked_id)
        self.assertTrue(tracked_record["library_read_only"])

        with self.assertRaises(RequestValidationError) as raised:
            self.service.archive_production(
                tracked_id, _archive(OPERATION_ONE, False, True)
            )
        self.assertEqual(raised.exception.code, "production_library_read_only")

    def test_server_side_search_is_case_insensitive(self) -> None:
        self.service.create_production(_create(SECOND_PRODUCTION_ID, "Campaign Beta"))
        self.service.create_production(_create(THIRD_PRODUCTION_ID, "Another"))
        found = self.service.list_productions(query="campaign")
        self.assertEqual([item["id"] for item in found["productions"]], [SECOND_PRODUCTION_ID])


class ProductionLibraryMigrationTests(unittest.TestCase):
    def test_v8_database_adds_library_ledger_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            path = workspace / "studio.sqlite3"
            StudioDatabase(path, workspace=workspace)
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript(
                    """
                    DROP TRIGGER production_library_states_immutable_delete;
                    DROP TRIGGER production_library_operations_immutable_delete;
                    DROP TRIGGER production_library_operations_immutable_update;
                    DROP TABLE production_library_operations;
                    DROP TABLE production_library_states;
                    UPDATE schema_meta SET value='8' WHERE key='schema_version';
                    """
                )

            StudioDatabase(path, workspace=workspace)
            with closing(sqlite3.connect(path)) as connection:
                version = connection.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                indexes = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA index_list(production_library_operations)"
                    )
                }
            self.assertEqual(version, str(SCHEMA_VERSION))
            self.assertIn("production_library_states", tables)
            self.assertIn("production_library_operations", tables)
            self.assertIn("production_library_operations_production_idx", indexes)


class ProductionLibraryHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "library-session-token-0123456789abcdef"
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

    def _post(self, path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
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

    def _get(self, path: str) -> tuple[int, dict[str, object]]:
        self.connection.request("GET", path)
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_library_endpoints_and_archived_listing_contract(self) -> None:
        self.assertEqual(self._post("/api/productions", _create(PRODUCTION_ID, "HTTP Original"))[0], 201)
        rename_status, renamed = self._post(
            f"/api/productions/{PRODUCTION_ID}/library/rename",
            _rename(OPERATION_ONE, "HTTP Original", "HTTP Renamed"),
        )
        self.assertEqual(rename_status, 200)
        self.assertEqual(renamed["production"]["title"], "HTTP Renamed")

        archive_status, archived = self._post(
            f"/api/productions/{PRODUCTION_ID}/library/archive",
            _archive(OPERATION_TWO, False, True),
        )
        self.assertEqual(archive_status, 200)
        self.assertTrue(archived["production"]["archived"])
        self.assertEqual(self._get("/api/productions?q=HTTP")[1]["count"], 0)
        visible = self._get("/api/productions?include_archived=true&q=renamed")[1]
        self.assertEqual(visible["count"], 1)

        duplicate_status, duplicated = self._post(
            f"/api/productions/{PRODUCTION_ID}/library/duplicate",
            _duplicate(
                OPERATION_THREE,
                SECOND_PRODUCTION_ID,
                "HTTP Copy",
                include_imports=False,
            ),
        )
        self.assertEqual(duplicate_status, 201)
        self.assertEqual(duplicated["production"]["id"], SECOND_PRODUCTION_ID)


if __name__ == "__main__":
    unittest.main()
