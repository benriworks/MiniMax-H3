from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

from tools.studio.instance_lock import StudioInstanceLockError
from tools.studio.secrets import SecretStore, dpapi_available
from tools.studio.security import (
    SecurityError,
    UnsafeTextArtifactError,
    redact_artifact_text,
    workspace_path,
)
from tools.studio.server import create_server
from tools.studio.service import RequestValidationError, StudioService, build_rerun_plan


PRODUCTION_ID = "TEST_20260823_auditable_short"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42studio-video-payload"
RAW_LOG_SECRET = "audit-log-secret-123456"
RAW_JSON_SECRET = "plainprovidercredential123"
RAW_CONFIG_SECRET = "structured-config-secret-123456"
RAW_UNKNOWN_SECRET = "unknown-format-secret-123456"


class WorkspaceFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        source = self.root / "productions" / PRODUCTION_ID
        output = self.root / "outputs" / "productions" / PRODUCTION_ID
        (source / "manifests").mkdir(parents=True)
        (source / "prompts").mkdir()
        (output / "02_cuts" / "CUT01").mkdir(parents=True)
        (output / "logs").mkdir()
        (self.root / "studio" / "dist").mkdir(parents=True)
        (source / "PRODUCTION_RECORD_JA.md").write_text(
            f"# 制作記録 — {PRODUCTION_ID}\n\ntechnical / creative / public gates\n",
            encoding="utf-8",
        )
        (source / "prompts" / "CUT01_H3.md").write_text("safe prompt\n", encoding="utf-8")
        (source / ".env").write_text("OPENAI_API_KEY=must-never-be-indexed\n", encoding="utf-8")
        (source / "app.env").write_text(
            "OPENAI_API_KEY=must-also-never-be-indexed\n", encoding="utf-8"
        )
        (source / "unsafe.conf").write_text(
            f"api_key: |\n  {RAW_CONFIG_SECRET}\n", encoding="utf-8"
        )
        (source / "settings.properties").write_text(
            f"api_key={RAW_UNKNOWN_SECRET}\n", encoding="utf-8"
        )
        (source / "unsafe.html").write_text(
            "<script>fetch('/api/index/refresh',{method:'POST'})</script>",
            encoding="utf-8",
        )
        self.video = output / "02_cuts" / "CUT01" / "clip.mp4"
        self.video.write_bytes(VIDEO_BYTES)
        (output / "logs" / "render.jsonl").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "authorization": f"Bearer {RAW_LOG_SECRET}",
                    "api_key": RAW_JSON_SECRET,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(VIDEO_BYTES).hexdigest().upper()
        manifest = {
            "production_id": PRODUCTION_ID,
            "status": "complete_independently_reviewed",
            "technical_status": "master_pass",
            "creative_status": "review_pass",
            "public_release_status": "blocked_pending_rights_review",
            "artifact": {
                "path": self.video.relative_to(self.root).as_posix(),
                "bytes": len(VIDEO_BYTES),
                "sha256": digest,
            },
        }
        (source / "manifests" / "source-hashes.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.root / "studio" / "dist" / "index.html").write_text(
            "<!doctype html><title>Studio</title>", encoding="utf-8"
        )

    def close(self) -> None:
        self.temporary.cleanup()


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.service: StudioService | None = StudioService(self.fixture.root)
        self.service.indexer.refresh()

    def tearDown(self) -> None:
        if self.service is not None:
            self.service.close()
        self.fixture.close()

    def test_index_imports_records_and_heavy_artifacts_by_reference(self) -> None:
        listing = self.service.list_productions()
        self.assertEqual(listing["count"], 1)
        production = listing["productions"][0]
        self.assertEqual(production["id"], PRODUCTION_ID)
        self.assertEqual(production["technical_status"], "master_pass")
        detail = self.service.production_detail(PRODUCTION_ID, artifact_limit=100)
        self.assertIsNotNone(detail)
        assert detail is not None
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        self.assertFalse(
            any(Path(item["rel_path"]).suffix.casefold() == ".env" for item in detail["artifacts"])
        )
        self.assertEqual(video["bytes"], len(VIDEO_BYTES))
        self.assertEqual(video["sha256"], hashlib.sha256(VIDEO_BYTES).hexdigest().upper())
        self.assertEqual(video["preview_url"], f"/api/artifacts/{video['id']}/file")

        database_bytes = self.service.database.path.read_bytes()
        self.assertNotIn(VIDEO_BYTES, database_bytes)
        mirror = self.service.database.event_mirror_path("production", PRODUCTION_ID)
        events = [json.loads(line) for line in mirror.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1]["event_hash"], events[-1]["event_hash"].lower())
        self.assertEqual(len(events[-1]["event_hash"]), 64)

    def test_partial_rerun_creates_immutable_revision_run_and_append_only_approval(self) -> None:
        plan = build_rerun_plan(PRODUCTION_ID, [{"type": "caption", "target": "CUT03"}])
        self.assertEqual(plan["affected_stages"], ["captions", "assembly", "qc"])
        self.assertIn("video_generation", plan["reused_stages"])

        secret = "never-store-this-credential"
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [
                    {"type": "caption", "api_key": secret, "note": f"token={secret}"}
                ],
                "estimated_cost": {"amount": "1.25", "currency": "USD"},
            },
        )
        run_id = created["run"]["id"]
        self.assertEqual(created["run"]["state"], "awaiting_cost_approval")
        with self.assertRaises(RequestValidationError):
            self.service.approve_run(
                run_id,
                {
                    "approved": True,
                    "max_cost": {"amount": "1.00", "currency": "USD"},
                },
            )
        rejected = self.service.approve_run(
            run_id,
            {
                "approved": False,
                "note": "needs a lower estimate",
            },
        )
        self.assertEqual(rejected["state"], "rejected")
        approved = self.service.approve_run(
            run_id,
            {
                "approved": True,
                "max_cost": {"amount": "2.00", "currency": "USD"},
                "actor": "owner",
                "note": f"authorization={secret}",
            },
        )
        self.assertEqual(approved["state"], "approved")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["runs"][0]["estimated_cost"]["amount"], "1.25")
        self.assertEqual(detail["runs"][0]["latest_approval"]["decision"], "approved")
        self.assertEqual(
            [approval["decision"] for approval in detail["approvals"]],
            ["rejected", "approved"],
        )

        with closing(self.service.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE revisions SET changes_json='[]' WHERE id=?",
                    (created["revision"]["id"],),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM runs WHERE id=?", (run_id,))

        persisted = self.service.database.path.read_bytes()
        self.assertNotIn(secret.encode("utf-8"), persisted)
        event_files = list((self.fixture.root / "outputs" / "studio" / "events").rglob("*.jsonl"))
        self.assertTrue(event_files)
        self.assertNotIn(secret, "".join(path.read_text(encoding="utf-8") for path in event_files))

    def test_billable_rerun_fails_closed_without_positive_estimate(self) -> None:
        assert self.service is not None
        with self.assertRaises(RequestValidationError) as raised:
            self.service.create_run(
                PRODUCTION_ID,
                {
                    "changes": [{"type": "script"}],
                    "estimated_cost": {"amount": 0, "currency": "USD"},
                },
            )
        self.assertEqual(raised.exception.code, "cost_estimate_required")
        detail = self.service.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["runs"], [])

    def test_zero_cost_run_rejects_cost_approval(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "local overlay only"}],
                "estimated_cost": {"amount": 0, "currency": "USD"},
            },
        )
        with self.assertRaises(RequestValidationError) as raised:
            self.service.approve_run(
                created["run"]["id"],
                {
                    "approved": True,
                    "max_cost": {"amount": 0, "currency": "USD"},
                },
            )
        self.assertEqual(raised.exception.code, "cost_approval_not_required")

    def test_audit_snapshot_uses_one_database_read_transaction(self) -> None:
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "snapshot test"}],
                "estimated_cost": {"amount": "1.00", "currency": "USD"},
            },
        )
        snapshot_ready = threading.Event()
        resume_snapshot = threading.Event()
        captured: list[dict[str, object] | None] = []
        original = self.service.database._production_detail_from_connection

        def paused_detail(*args: object, **kwargs: object) -> dict[str, object] | None:
            detail = original(*args, **kwargs)
            snapshot_ready.set()
            self.assertTrue(resume_snapshot.wait(10))
            return detail

        with mock.patch.object(
            self.service.database,
            "_production_detail_from_connection",
            side_effect=paused_detail,
        ):
            thread = threading.Thread(
                target=lambda: captured.append(
                    self.service.database.production_audit_snapshot(PRODUCTION_ID)
                )
            )
            thread.start()
            self.assertTrue(snapshot_ready.wait(10))
            self.service.approve_run(
                created["run"]["id"],
                {
                    "approved": True,
                    "max_cost": {"amount": "1.00", "currency": "USD"},
                },
            )
            resume_snapshot.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        snapshot = captured[0]
        assert snapshot is not None
        self.assertIsNone(snapshot["runs"][0]["latest_approval"])
        self.assertEqual(snapshot["approvals"], [])
        self.assertFalse(any(event["event_type"] == "cost.approved" for event in snapshot["events"]))

    def test_workspace_escape_and_non_loopback_bind_are_rejected(self) -> None:
        with self.assertRaises(SecurityError):
            workspace_path(self.fixture.root, "../outside-artifact.mp4")
        with self.assertRaises(ValueError):
            create_server(
                self.fixture.root,
                host="0.0.0.0",
                port=0,
                initial_refresh=False,
            )
        with self.assertRaises(ValueError):
            create_server(
                self.fixture.root,
                port=0,
                allowed_origins=["https://attacker.example"],
                initial_refresh=False,
            )

    def test_structured_and_header_secrets_are_redacted(self) -> None:
        source = json.dumps(
            {
                "api_key": "plainprovidercredential123",
                "password": "hunter2longvalue",
                "authorization": "Basic dXNlcjpwYXNzd29yZA==",
                "cookie": "StudioSession=private-session-value",
                "safe": "retained",
            }
        )
        redacted = redact_artifact_text(source, suffix=".json")
        for secret in (
            "plainprovidercredential123",
            "hunter2longvalue",
            "dXNlcjpwYXNzd29yZA==",
            "private-session-value",
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn("retained", redacted)
        headers = redact_artifact_text(
            "Authorization: Basic dXNlcjpwYXNzd29yZA==\n"
            "Proxy-Authorization: Custom opaque-auth-value\n"
            "Cookie: session=private-session-value\n"
            "url=https://example.invalid/file?X-Amz-Signature=signed-value\n"
        )
        self.assertNotIn("dXNlcjpwYXNzd29yZA==", headers)
        self.assertNotIn("opaque-auth-value", headers)
        self.assertNotIn("private-session-value", headers)
        self.assertNotIn("signed-value", headers)

        quoted = redact_artifact_text(
            'password: "correct horse battery staple"\n'
            "api_key='another multi word secret'\n",
            suffix=".log",
        )
        self.assertNotIn("correct horse battery staple", quoted)
        self.assertNotIn("another multi word secret", quoted)
        self.assertIn('password: "[REDACTED]"', quoted)

        environment = redact_artifact_text(
            "MINIMAX_API_KEY=MINIMAXTOPSECRET123456\n"
            'OPENAI_API_KEY="OPENAITOPSECRET123456"\n'
            "AZURE_SPEECH_KEY: AZURETOPSECRET123456\n"
            "export ELEVENLABS_API_KEY=ELEVENLABSTOPSECRET123456\n"
            "set CUSTOM_API_TOKEN=WINDOWSTOPSECRET123456\n"
            "$env:CUSTOM_API_SECRET='POWERSHELLTOPSECRET123456'\n"
            "SAFE_SETTING=retained\n",
            suffix=".log",
        )
        for secret in (
            "MINIMAXTOPSECRET123456",
            "OPENAITOPSECRET123456",
            "AZURETOPSECRET123456",
            "ELEVENLABSTOPSECRET123456",
            "WINDOWSTOPSECRET123456",
            "POWERSHELLTOPSECRET123456",
        ):
            self.assertNotIn(secret, environment)
        self.assertIn("SAFE_SETTING=retained", environment)

    def test_unsafe_structured_text_artifacts_fail_closed(self) -> None:
        samples = {
            ".yaml": "api_key: |\n  top-secret-value\n",
            ".ini": 'password: "correct horse battery staple"\n',
            ".xml": "<authorization>top-secret-value</authorization>\n",
            ".html": "<authorization>top-secret-value</authorization>\n",
            ".svg": "<authorization>top-secret-value</authorization>\n",
            ".csv": "api_key,name\ntop-secret-value,demo\n",
            ".tsv": "api_key\tname\ntop-secret-value\tdemo\n",
        }
        for suffix, source in samples.items():
            with self.subTest(suffix=suffix):
                with self.assertRaises(UnsafeTextArtifactError):
                    redact_artifact_text(source, suffix=suffix)
        with self.assertRaises(UnsafeTextArtifactError):
            redact_artifact_text('{"api_key":"unterminated', suffix=".json")
        with self.assertRaises(UnsafeTextArtifactError):
            redact_artifact_text('{"status":"ok"}\nnot-json\n', suffix=".jsonl")

    def test_background_refresh_and_audit_export_are_inspectable(self) -> None:
        refresh = self.service.refresh_index()
        completed_refresh = self.service.jobs.wait(refresh["id"], timeout=10)
        assert completed_refresh is not None
        self.assertEqual(completed_refresh["status"], "succeeded")
        self.assertEqual(completed_refresh["result"]["productions"], 1)

        audit = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = self.service.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        artifact = completed["result"]["artifact"]
        archive_path = self.fixture.root / artifact["rel_path"]
        sidecar_path = self.fixture.root / completed["result"]["sha256_sidecar"]
        self.assertTrue(archive_path.is_file())
        self.assertTrue(sidecar_path.is_file())
        self.assertTrue(
            sidecar_path.read_text(encoding="ascii").startswith(artifact["sha256"])
        )
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertIn("audit/production-snapshot.json", names)
            self.assertIn("audit/events.jsonl", names)
            self.assertIn(f"studio-events/production/{PRODUCTION_ID}.jsonl", names)
            self.assertIn(
                f"workspace/productions/{PRODUCTION_ID}/PRODUCTION_RECORD_JA.md", names
            )
            archived_log = archive.read(
                f"workspace/outputs/productions/{PRODUCTION_ID}/logs/render.jsonl"
            ).decode("utf-8")
            self.assertNotIn(RAW_LOG_SECRET, archived_log)
            self.assertNotIn(RAW_JSON_SECRET, archived_log)
            package_manifest = json.loads(archive.read("audit/package-manifest.json"))
            self.assertIn(
                f"outputs/productions/{PRODUCTION_ID}/logs/render.jsonl",
                package_manifest["redacted_text_files"],
            )
            skipped = {
                entry["path"]: entry["reason"]
                for entry in package_manifest["skipped"]
            }
            for relative in (
                f"productions/{PRODUCTION_ID}/unsafe.conf",
                f"productions/{PRODUCTION_ID}/unsafe.html",
            ):
                self.assertEqual(
                    skipped[relative], "structured_text_requires_local_review"
                )
                self.assertNotIn(f"workspace/{relative}", names)
            unknown_relative = f"productions/{PRODUCTION_ID}/settings.properties"
            self.assertEqual(
                skipped[unknown_relative], "unsupported_artifact_kind"
            )
            self.assertNotIn(f"workspace/{unknown_relative}", names)
            for name in names:
                self.assertNotIn(RAW_UNKNOWN_SECRET.encode("utf-8"), archive.read(name))
            self.assertIn(f"production:{PRODUCTION_ID}", package_manifest["event_chain_tails"])
            for entry in package_manifest["archive_entries"]:
                payload = archive.read(entry["path"])
                self.assertEqual(len(payload), entry["bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest().upper(), entry["sha256"])
            self.assertNotIn(
                f"workspace/outputs/productions/{PRODUCTION_ID}/02_cuts/CUT01/clip.mp4",
                names,
            )

    def test_corrupt_event_mirror_is_degraded_and_excluded_from_audit(self) -> None:
        assert self.service is not None
        mirror = self.service.database.event_mirror_path("production", PRODUCTION_ID)
        with mirror.open("a", encoding="utf-8") as handle:
            handle.write('{"corrupt":true}\n')
        self.service.database.append_event(
            "run", "healthy_scope", "run.test", {"status": "ok"}
        )
        health = self.service.health()
        self.assertTrue(health["ok"])
        self.assertTrue(health["degraded"])
        self.assertGreater(health["event_mirror"]["issue_count"], 0)
        healthy_mirror = self.service.database.event_mirror_path("run", "healthy_scope")
        self.assertTrue(healthy_mirror.is_file())

        audit = self.service.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = self.service.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        archive_path = self.fixture.root / completed["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertNotIn(
                f"studio-events/production/{PRODUCTION_ID}.jsonl", names
            )
            package_manifest = json.loads(archive.read("audit/package-manifest.json"))
            skipped_scopes = {
                entry["scope"] for entry in package_manifest["skipped_event_mirrors"]
            }
            self.assertIn(f"production:{PRODUCTION_ID}", skipped_scopes)

    def test_sqlite_index_rebuild_restores_run_and_approval_from_event_mirror(self) -> None:
        assert self.service is not None
        created = self.service.create_run(
            PRODUCTION_ID,
            {
                "changes": [{"type": "caption", "note": "rebuild proof"}],
                "estimated_cost": {"amount": "0.50", "currency": "USD"},
            },
        )
        self.service.approve_run(
            created["run"]["id"],
            {
                "approved": True,
                "max_cost": {"amount": "1.00", "currency": "USD"},
                "note": "approved before rebuild",
            },
        )
        database_path = self.service.database.path
        self.service.close()
        self.service = None
        database_path.unlink()
        database_path.with_name(database_path.name + "-wal").unlink(missing_ok=True)
        database_path.with_name(database_path.name + "-shm").unlink(missing_ok=True)

        rebuilt = StudioService(self.fixture.root)
        self.service = rebuilt
        result = rebuilt.indexer.refresh()
        self.assertEqual(result["domain_records_restored"]["revisions"], 1)
        self.assertEqual(result["domain_records_restored"]["runs"], 1)
        self.assertEqual(result["domain_records_restored"]["approvals"], 1)
        detail = rebuilt.production_detail(PRODUCTION_ID)
        assert detail is not None
        self.assertEqual(detail["runs"][0]["id"], created["run"]["id"])
        self.assertEqual(detail["runs"][0]["latest_approval"]["decision"], "approved")
        audit = rebuilt.audit_export(PRODUCTION_ID, {"include_media": False})
        completed = rebuilt.jobs.wait(audit["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        archive_path = self.fixture.root / completed["result"]["artifact"]["rel_path"]
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertIn(
                f"studio-events/production/{PRODUCTION_ID}.jsonl", names
            )
            self.assertIn(
                f"studio-events/run/{created['run']['id']}.jsonl", names
            )


class HTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WorkspaceFixture()
        self.token = "test-session-token-with-at-least-thirty-two-characters"
        self.server = create_server(
            self.fixture.root,
            host="127.0.0.1",
            port=0,
            static_dir="studio/dist",
            session_token=self.token,
            initial_refresh=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
        )
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.fixture.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = dict(headers or {})
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("Content-Length", str(len(data)))
        self.connection.request(method, path, body=data, headers=request_headers)
        response = self.connection.getresponse()
        payload = response.read()
        return response.status, {key.casefold(): value for key, value in response.getheaders()}, payload

    def test_static_cookie_auth_origin_and_health_do_not_expose_token(self) -> None:
        status, headers, _body = self.request("GET", "/")
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        status, health_headers, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertNotIn(self.token.encode(), body)
        self.assertNotIn(self.token, json.dumps(health_headers))

        status, _headers, _body = self.request(
            "POST", "/api/index/refresh", body={}
        )
        self.assertEqual(status, 403)
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie},
        )
        self.assertEqual(status, 403)
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie, "Origin": "https://attacker.example"},
        )
        self.assertEqual(status, 403)
        status, _headers, body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"Cookie": cookie, "Origin": self.origin},
        )
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["kind"], "index_refresh")
        status, _headers, _body = self.request(
            "POST",
            "/api/index/refresh",
            body={},
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(status, 202)

    def test_workspace_allows_only_one_studio_server(self) -> None:
        with self.assertRaises(StudioInstanceLockError):
            create_server(
                self.fixture.root,
                host="127.0.0.1",
                port=0,
                session_token="second-session-token-with-thirty-two-characters",
                initial_refresh=False,
            )

    def test_artifact_file_supports_head_range_and_content_alias(self) -> None:
        status, _headers, body = self.request("GET", f"/api/productions/{PRODUCTION_ID}")
        self.assertEqual(status, 200)
        detail = json.loads(body)
        video = next(item for item in detail["artifacts"] if item["kind"] == "video")
        for endpoint in ("file", "content"):
            status, headers, body = self.request(
                "GET",
                f"/api/artifacts/{video['id']}/{endpoint}",
                headers={"Range": "bytes=2-7"},
            )
            self.assertEqual(status, 206)
            self.assertEqual(body, VIDEO_BYTES[2:8])
            self.assertEqual(headers["content-range"], f"bytes 2-7/{len(VIDEO_BYTES)}")
        status, headers, body = self.request(
            "HEAD", f"/api/artifacts/{video['id']}/file"
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["content-length"]), len(VIDEO_BYTES))
        status, headers, _body = self.request(
            "GET",
            f"/api/artifacts/{video['id']}/file",
            headers={"Range": "bytes=999-1000"},
        )
        self.assertEqual(status, 416)
        self.assertEqual(headers["content-range"], f"bytes */{len(VIDEO_BYTES)}")

    def test_text_artifacts_are_redacted_and_active_content_is_sandboxed(self) -> None:
        status, _headers, body = self.request("GET", f"/api/productions/{PRODUCTION_ID}")
        self.assertEqual(status, 200)
        artifacts = json.loads(body)["artifacts"]
        log = next(item for item in artifacts if item["name"] == "render.jsonl")
        status, headers, body = self.request("GET", log["file_url"])
        self.assertEqual(status, 200)
        self.assertEqual(headers["x-studio-content-redacted"], "true")
        self.assertTrue(headers["content-disposition"].startswith("attachment;"))
        self.assertIn("sandbox", headers["content-security-policy"])
        self.assertNotIn(RAW_LOG_SECRET.encode("utf-8"), body)
        self.assertNotIn(RAW_JSON_SECRET.encode("utf-8"), body)
        self.assertIn(b"[REDACTED]", body)

        unsafe_config = next(item for item in artifacts if item["name"] == "unsafe.conf")
        status, _headers, body = self.request("GET", unsafe_config["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(RAW_CONFIG_SECRET.encode("utf-8"), body)
        self.assertEqual(
            json.loads(body)["error"]["code"],
            "artifact_format_requires_local_review",
        )

        html = next(item for item in artifacts if item["name"] == "unsafe.html")
        status, _headers, body = self.request("GET", html["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(b"fetch('/api/index/refresh'", body)

        unknown = next(item for item in artifacts if item["name"] == "settings.properties")
        status, _headers, body = self.request("GET", unknown["file_url"])
        self.assertEqual(status, 415)
        self.assertNotIn(RAW_UNKNOWN_SECRET.encode("utf-8"), body)

    def test_provider_status_returns_flags_only(self) -> None:
        secret = "provider-value-that-must-never-be-returned"
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": secret}, clear=False):
            status, _headers, body = self.request("GET", "/api/providers/status")
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertNotIn(secret, body.decode("utf-8"))
        for provider in value["providers"]:
            self.assertEqual(set(provider), {"id", "configured"})
        elevenlabs = next(item for item in value["providers"] if item["id"] == "elevenlabs")
        self.assertTrue(elevenlabs["configured"])

    def test_studio_generated_audit_zip_remains_downloadable(self) -> None:
        job = self.server.service.audit_export(
            PRODUCTION_ID, {"include_media": False}
        )
        completed = self.server.service.jobs.wait(job["id"], timeout=10)
        assert completed is not None
        self.assertEqual(completed["status"], "succeeded")
        artifact = completed["result"]["artifact"]
        status, headers, body = self.request("GET", artifact["file_url"])
        self.assertEqual(status, 200)
        self.assertIn("zip", headers["content-type"])
        self.assertTrue(body.startswith(b"PK"))


@unittest.skipUnless(dpapi_available(), "Windows DPAPI is required")
class SecretStoreTests(unittest.TestCase):
    def test_dpapi_file_never_contains_plaintext(self) -> None:
        fixture = WorkspaceFixture()
        try:
            secret = "dpapi-secret-value-123456789"
            store = SecretStore(fixture.root)
            store.set("openai", secret)
            encrypted = (fixture.root / "outputs" / "studio" / "secrets" / "openai.dpapi").read_bytes()
            self.assertNotIn(secret.encode("utf-8"), encrypted)
            self.assertEqual(store.get("openai"), secret)
            status = store.statuses()
            self.assertNotIn(secret, json.dumps(status))
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
