from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.studio.reviews import (
    ReviewValidationError,
    review_snapshot,
    validate_review_create_payload,
    validate_review_decision_payload,
    validate_review_plan_payload,
    validate_review_resolve_payload,
)
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService


PRODUCTION_ID = "production_" + "a" * 32
SECOND_PRODUCTION_ID = "production_" + "b" * 32


class ReviewFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.service = StudioService(self.root)
        self.service.create_production(
            {
                "schema_version": 1,
                "production_id": PRODUCTION_ID,
                "title": "レビュー対象",
            }
        )
        video = (
            self.root
            / "outputs"
            / "productions"
            / PRODUCTION_ID
            / "generated"
            / "cut-01.mp4"
        )
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"review-video")
        self.service.indexer.refresh_production(PRODUCTION_ID)
        artifact = self.service.production_detail(PRODUCTION_ID)["artifacts"][0]
        revision, run = self.service.database.create_revision_and_run(
            PRODUCTION_ID,
            [{"type": "video_generation"}],
            {
                "affected_stages": [
                    "video_generation",
                    "timeline",
                    "assembly",
                    "qc",
                ]
            },
            0,
            "USD",
        )
        self.artifact_id = artifact["id"]
        self.revision_id = revision["id"]
        self.run_id = run["id"]
        self.cut_id = "cut_" + self.artifact_id.removeprefix("art_")

    def create_body(self, *, idempotency_key: str = "create-review-1") -> dict[str, object]:
        return {
            "schema_version": 1,
            "idempotency_key": idempotency_key,
            "artifact_id": self.artifact_id,
            "revision_id": self.revision_id,
            "run_id": self.run_id,
            "cut_id": self.cut_id,
            "timecode_ms": 1_250,
            "category": "creative",
            "body": "後半の動きを増やす。API_KEY=top-secret",
            "actor": "operator",
        }

    def close(self) -> None:
        self.service.close()
        self.temporary.cleanup()


class ReviewContractTests(unittest.TestCase):
    def test_closed_request_contracts_reject_unknown_fields_and_invalid_decisions(self) -> None:
        fixture = ReviewFixture()
        try:
            valid = fixture.create_body()
            normalized = validate_review_create_payload(valid)
            self.assertEqual(normalized["artifact_id"], fixture.artifact_id)
            self.assertNotIn("top-secret", normalized["body"])
            self.assertEqual(
                validate_review_resolve_payload(
                    {
                        "schema_version": 1,
                        "idempotency_key": "resolve-1",
                        "actor": "operator",
                        "note": "対応済み",
                    }
                )["note"],
                "対応済み",
            )
            self.assertEqual(
                validate_review_decision_payload(
                    {
                        "schema_version": 1,
                        "idempotency_key": "decision-1",
                        "actor": "operator",
                        "decision": "changes_required",
                        "note": "再確認",
                    }
                )["decision"],
                "changes_required",
            )
            self.assertEqual(
                validate_review_plan_payload(
                    {
                        "schema_version": 1,
                        "idempotency_key": "plan-1",
                        "actor": "operator",
                    }
                )["actor"],
                "operator",
            )
            invalid = {**valid, "path": "C:/private/file.mp4"}
            with self.assertRaises(ReviewValidationError):
                validate_review_create_payload(invalid)
            with self.assertRaises(ReviewValidationError):
                validate_review_decision_payload(
                    {
                        "schema_version": 1,
                        "idempotency_key": "decision-2",
                        "actor": "operator",
                        "decision": "released",
                        "note": "",
                    }
                )
        finally:
            fixture.close()


class ReviewPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReviewFixture()
        self.service = self.fixture.service

    def tearDown(self) -> None:
        self.fixture.close()

    def test_create_is_idempotent_scoped_and_redacted(self) -> None:
        first = self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        retry = self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        self.assertFalse(first["deduplicated"])
        self.assertTrue(retry["deduplicated"])
        self.assertEqual(first["action"]["id"], retry["action"]["id"])
        self.assertEqual(first["review"]["identity"]["artifact_id"], self.fixture.artifact_id)
        self.assertNotIn("top-secret", first["review"]["body"])
        self.assertNotIn("rel_path", json.dumps(first, ensure_ascii=False))

        changed = self.fixture.create_body()
        changed["body"] = "別の内容"
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_review(PRODUCTION_ID, changed)
        self.assertEqual(raised.exception.code, "review_idempotency_conflict")

        events = self.service.database.review_snapshot(PRODUCTION_ID)
        self.assertEqual(events["count"], 1)
        self.assertEqual(events["open_count"], 1)

    def test_concurrent_duplicate_post_commits_one_action(self) -> None:
        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []

        def submit() -> None:
            barrier.wait()
            results.append(
                self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
            )

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(bool(item["deduplicated"]) for item in results), 1)
        self.assertEqual(self.service.list_reviews(PRODUCTION_ID)["count"], 1)

    def test_decision_resolution_and_gates_remain_separate(self) -> None:
        created = self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        review_id = created["review"]["id"]
        decided = self.service.set_review_decision(
            PRODUCTION_ID,
            review_id,
            {
                "schema_version": 1,
                "idempotency_key": "decision-review-1",
                "actor": "director",
                "decision": "changes_required",
                "note": "修正が必要",
            },
        )
        self.assertEqual(decided["review"]["status"], "open")
        self.assertEqual(decided["review"]["decision"], "changes_required")
        self.assertEqual(decided["gates"]["creative"]["decision"], "changes_required")
        resolved = self.service.resolve_review(
            PRODUCTION_ID,
            review_id,
            {
                "schema_version": 1,
                "idempotency_key": "resolve-review-1",
                "actor": "director",
                "note": "修正版を確認",
            },
        )
        self.assertEqual(resolved["review"]["status"], "resolved")
        self.assertEqual(resolved["review"]["decision"], "changes_required")
        with self.assertRaises(RequestValidationError) as raised:
            self.service.resolve_review(
                PRODUCTION_ID,
                review_id,
                {
                    "schema_version": 1,
                    "idempotency_key": "resolve-review-2",
                    "actor": "director",
                    "note": "二重解決",
                },
            )
        self.assertEqual(raised.exception.code, "review_already_resolved")

    def test_revision_plan_is_cut_only_and_explicitly_not_executed(self) -> None:
        created = self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        planned = self.service.create_review_revision_plan(
            PRODUCTION_ID,
            created["review"]["id"],
            {
                "schema_version": 1,
                "idempotency_key": "plan-review-1",
                "actor": "director",
            },
        )
        plan = planned["action"]["revision_plan"]
        self.assertEqual(plan["status"], "planned_not_executed")
        self.assertEqual(plan["render_status"], "not_started")
        self.assertFalse(plan["execution"]["connected"])
        self.assertEqual(plan["execution"]["status"], "not_connected")
        self.assertIsNone(plan["execution"]["job_id"])
        self.assertEqual(plan["exact_cut_identity"]["cut_id"], self.fixture.cut_id)
        self.assertEqual(
            plan["reuse_policy"], "reuse_all_other_exact_cut_artifacts"
        )
        self.assertNotIn("path", json.dumps(plan, ensure_ascii=False).casefold())

    def test_cross_production_lineage_is_rejected_and_restart_restores_projection(self) -> None:
        self.service.create_production(
            {
                "schema_version": 1,
                "production_id": SECOND_PRODUCTION_ID,
                "title": "別制作",
            }
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_review(SECOND_PRODUCTION_ID, self.fixture.create_body())
        self.assertEqual(raised.exception.code, "invalid_review_lineage")

        created = self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        self.service.close()
        self.fixture.service = StudioService(self.fixture.root)
        self.service = self.fixture.service
        restored = self.service.list_reviews(PRODUCTION_ID)
        self.assertEqual(restored["reviews"][0]["id"], created["review"]["id"])

    def test_tampered_event_fails_closed(self) -> None:
        self.service.create_review(PRODUCTION_ID, self.fixture.create_body())
        with self.service.database.session() as connection:
            connection.execute("DROP TRIGGER events_immutable_update")
            row = connection.execute(
                "SELECT id, payload_json FROM events WHERE event_type='review.created'"
            ).fetchone()
            payload = json.loads(row["payload_json"])
            payload["identity"]["cut_id"] = "cut_invalid"
            connection.execute(
                "UPDATE events SET payload_json=? WHERE id=?",
                (json.dumps(payload), row["id"]),
            )
        with self.assertRaises(ReviewValidationError):
            self.service.list_reviews(PRODUCTION_ID)

    def test_empty_snapshot_has_all_explicit_gates(self) -> None:
        snapshot = review_snapshot(PRODUCTION_ID, [])
        self.assertEqual(
            set(snapshot["gates"]), {"creative", "rights", "public_release"}
        )
        self.assertTrue(
            all(value["decision"] == "pending" for value in snapshot["gates"].values())
        )


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.token = "review-session-token-at-least-thirty-two-characters"
        self.server = create_server(
            self.workspace,
            host="127.0.0.1",
            port=0,
            static_dir="studio/dist",
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

    def _request(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object]]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"X-Studio-Token": self.token}
        if encoded is not None:
            headers.update(
                {"Content-Type": "application/json", "Content-Length": str(len(encoded))}
            )
        self.connection.request(method, path, body=encoded, headers=headers)
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_review_routes_forward_exact_identity_and_body(self) -> None:
        review_id = "review_" + "1" * 32
        body = {"schema_version": 1}
        expected = {"ok": True}
        cases = (
            ("GET", f"/api/productions/{PRODUCTION_ID}/reviews", None, 200, "list_reviews", (PRODUCTION_ID,)),
            ("POST", f"/api/productions/{PRODUCTION_ID}/reviews", body, 201, "create_review", (PRODUCTION_ID, body)),
            ("POST", f"/api/productions/{PRODUCTION_ID}/reviews/{review_id}/resolve", body, 201, "resolve_review", (PRODUCTION_ID, review_id, body)),
            ("POST", f"/api/productions/{PRODUCTION_ID}/reviews/{review_id}/decision", body, 201, "set_review_decision", (PRODUCTION_ID, review_id, body)),
            ("POST", f"/api/productions/{PRODUCTION_ID}/reviews/{review_id}/revision-plan", body, 201, "create_review_revision_plan", (PRODUCTION_ID, review_id, body)),
        )
        for method, path, request_body, status, method_name, expected_args in cases:
            with self.subTest(path=path), mock.patch.object(
                self.server.service, method_name, return_value=expected
            ) as delegated:
                actual_status, payload = self._request(method, path, request_body)
                self.assertEqual(actual_status, status)
                self.assertEqual(payload, expected)
                delegated.assert_called_once_with(*expected_args)


if __name__ == "__main__":
    unittest.main()
