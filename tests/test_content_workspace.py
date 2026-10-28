"""Workflow tests use fictional input and isolated databases, never provider APIs."""
from copy import deepcopy
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

from PIL import Image

from tools.studio.content_workspace import ContentWorkspace, ContentError
from tools.studio.database import StudioDatabase, SCHEMA_VERSION
from tools.studio.server import create_server


def source():
    return {"source_id": "docs", "title": "Fictional documentation", "url": "https://example.com/docs", "kind": "official", "checked_at": "2026-10-24", "published_at": "2026-10-23", "event_at": "2026-10-22"}


def episode(eid="one"):
    return {"episode_id": eid, "title": "【Claude】架空メモから文書へ", "overview": "共同で修正する仕組み", "intended_message": "人とAIで仕上げる", "duration_seconds": 45, "demo_idea": "架空の会議メモを編集", "article_role": "入力と修正例を詳しく掲載"}


def capture(status="available"):
    return dict(status=status, checked_at="2026-10-24", route="架空アプリの文書画面", result="撮影可能", app="テストアプリ", login_state="テスト用", feature_entry="文書", display_result="表示確認", save_result="保存可能", legibility="文字判読可", shots=[{"shot_id": "input", "purpose": "架空メモの入力"}, {"shot_id": "first", "purpose": "初回出力"}, {"shot_id": "revision", "purpose": "修正指示"}, {"shot_id": "after", "purpose": "修正後"}])


class ContentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.db = StudioDatabase(self.root / "studio.sqlite3", workspace=self.root, recover=False)
        self.service = ContentWorkspace(self.root, self.db)
        self.result = self.service.create({"content_project_id": "CONTENT_test", "operation_id": "op_create", "title": "架空のDocs調査"})

    @property
    def project(self):
        return self.result["project"]

    def apply(self, action, data):
        self.result = self.service.apply("CONTENT_test", action, {"operation_id": "op_" + uuid.uuid4().hex, "expected_revision": self.project["revision"], "data": data})
        return self.result

    def research(self, rid="research_one", sources=None):
        return self.apply("research", {"research_id": rid, "summary": "架空資料による試験。製品の事実を主張しない。", "checked_at": "2026-10-24", "sources": sources or [source()]})

    def propose(self, pid="proposal_one", episodes=None):
        return self.apply("proposal", {"proposal_id": pid, "count_reason": "各回を独立した結論に分けるため", "episodes": episodes or [episode()]})

    def accept(self, pid="proposal_one", fid="feedback_one"):
        self.apply("feedback", {"feedback_id": fid, "proposal_id": pid, "text": "この案で進めてください", "interpretation": "企画案を採用"})
        return self.apply("accept", {"proposal_id": pid, "feedback_id": fid, "confirm_acceptance": True})

    def prepared(self, episodes=None):
        self.research(); self.propose(episodes=episodes); self.accept()

    def image(self, aid="screen", kind="demonstration_capture", path="screen.png", **extra):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (140, 80), "white").save(target)
        data = {"asset_id": aid, "kind": kind, "path": path, "visibility": "public", "privacy_review": "passed", "fictional_materials_only": True, "alt": "架空画面", "caption": "架空素材の実演", **extra}
        self.apply("asset", data)
        return data

    def claim(self, cid="joint", **extra):
        return self.apply("claim", {"claim_id": cid, "text": "架空の説明", "basis": "official", "checked_at": "2026-10-24", "source_ids": ["docs"], **extra})

    def storyboard(self, eid="one", **extra):
        return self.apply("storyboard", {"episode_id": eid, "scenes": [{"scene_id": "intro", "purpose": "課題", "narration": "架空のメモを一緒に編集します", "visual": "実画面", "duration_seconds": 5, "claim_ids": ["joint"], "asset_ids": ["screen"], **extra}]})

    def test_pip_storyboard_requires_side_policy_and_keeps_legacy_fullscreen(self):
        self.prepared();self.claim();self.image();self.apply('capture',dict(capture(),episode_id='one'))
        self.image('person',kind='generated_still',path='person.png')
        self.apply('character',dict(character_id='aki',fictional_adult=True,name='架空のアキ',persona='仕事を説明する成人',
            role='進行役',clothing='紺の上着',voice='落ち着いた声',continuity='同じ企画を担当',reference_asset_id='person'))
        extras=dict(character_ids=['aki'],character_action='発話中に口を動かす',face_caption_separated=True)
        with self.assertRaises(ContentError):self.storyboard(**extras,presenter_layout='pip')
        policy=dict(trigger='emphasis',positions={'aki':'left'},avoid_gui_controls=True,caption_safe=True,
            speech_mode='audio_envelope',listener_mouth='closed')
        self.storyboard(**extras,presenter_layout='pip',pip_policy=policy)
        self.assertEqual(self.project['episodes'][0]['storyboard'][0]['presenter_layout'],'pip')
        with self.assertRaises(ContentError):
            self.storyboard(**extras,presenter_layout='pip',pip_policy={**policy,'avoid_gui_controls':False})
        with self.assertRaises(ContentError):
            self.storyboard(**extras,presenter_layout='pip',pip_policy={**policy,'positions':{'aki':[]}})
        with self.assertRaises(ContentError):
            self.storyboard(**extras,presenter_layout='pip',pip_policy={**policy,'trigger':[]})
        self.storyboard(**extras,presenter_layout='fullscreen')
        self.assertEqual(self.project['episodes'][0]['storyboard'][0]['presenter_layout'],'fullscreen')

    def test_draft_without_assets_and_reopen_shared_database(self):
        self.assertEqual(self.project["assets"], [])
        self.assertEqual(self.project["request"]["format"], "shorts_first")
        reopened = ContentWorkspace(self.root, StudioDatabase(self.root / "studio.sqlite3", workspace=self.root, recover=False))
        self.assertEqual(reopened.get("CONTENT_test")["project"], self.project)
        self.assertEqual(reopened.list()["items"][0]["revision"], 1)
        self.assertEqual(SCHEMA_VERSION, 15)

    def test_proposal_count_is_not_fixed_and_natural_feedback_does_not_accept(self):
        self.research(); self.propose(episodes=[episode(strid) for strid in ("one", "two", "three", "four", "five", "six")])
        self.apply("feedback", {"feedback_id": "comment", "proposal_id": "proposal_one", "text": "2と3をまとめたい", "interpretation": "次版で統合する"})
        self.assertEqual(len(self.project["proposals"][-1]["episodes"]), 6)
        self.assertIsNone(self.project["accepted_proposal"])
        self.assertFalse(self.result["checks"]["ready_for_production"])

    def test_accept_requires_explicit_response_to_current_proposal(self):
        self.research(); self.propose()
        with self.assertRaises(ContentError):
            self.apply("accept", {"proposal_id": "proposal_one", "feedback_id": "missing", "confirm_acceptance": True})
        self.accept()
        self.propose("proposal_two")
        with self.assertRaises(ContentError):
            self.apply("accept", {"proposal_id": "proposal_one", "feedback_id": "feedback_one", "confirm_acceptance": True})
        self.assertFalse(self.result["checks"]["ready_for_production"])

    def test_capture_inspection_and_save_are_separate_and_board_cannot_skip_inspection(self):
        self.prepared(); self.image(); self.claim()
        with self.assertRaises(ContentError):
            self.storyboard()
        with self.assertRaises(ContentError):
            self.apply("capture", {"episode_id": "one", **capture("captured")})
        self.apply("capture", {"episode_id": "one", **capture()})
        self.assertEqual(self.project["episodes"][0]["capture_plan"]["status"], "available")
        self.storyboard()
        self.assertTrue(self.result["checks"]["ready_for_production"])
        self.assertFalse(self.result["checks"]["technical_verified"])
        self.assertFalse(self.result["checks"]["human_reviewed"])
        self.assertFalse(self.result["checks"]["published"])

    def test_capture_feasibility_can_be_recorded_before_proposal_and_linked_after_adoption(self):
        self.apply("capture", {"inspection_id": "preflight", "target_feature": "架空文書の共同編集", **capture()})
        self.assertEqual(self.project["capture_inspections"][0]["status"], "available")
        self.research()
        self.propose(episodes=[{**episode(), "capture_inspection_id": "preflight"}])
        self.accept()
        self.assertEqual(self.project["episodes"][0]["capture_plan"]["inspection_id"], "preflight")

    def test_source_update_marks_only_dependent_scene_and_article_section(self):
        self.prepared([episode("one"), episode("two")]); self.image(); self.claim()
        for eid in ("one", "two"):
            self.apply("capture", {"episode_id": eid, **capture()})
            self.storyboard(eid, claim_ids=["joint"] if eid == "one" else [])
        self.apply("article", {"slug": "fictional-docs", "sections": [{"section_id": "uses", "title": "共同編集", "claim_ids": ["joint"], "asset_ids": ["screen"]}, {"section_id": "other", "title": "ほかの話"}]})
        updated = source(); updated["checked_at"] = "2026-10-25"
        self.research("research_two", [updated])
        self.assertTrue(self.project["episodes"][0]["storyboard"][0]["needs_review"])
        self.assertFalse(self.project["episodes"][1]["storyboard"][0]["needs_review"])
        self.assertTrue(self.project["article"]["sections"][0]["needs_review"])
        self.assertFalse(self.project["article"]["sections"][1]["needs_review"])
        self.assertTrue(self.project["claims"][0]["needs_review"])

    def test_asset_version_keeps_original_and_stales_dependent_cut(self):
        self.prepared(); original = self.image(); self.claim()
        self.apply("capture", {"episode_id": "one", **capture()}); self.storyboard()
        prior = self.project["revision"]
        self.image(path="screen-v2.png")
        self.assertEqual(self.project["assets"][0]["version"], 2)
        self.assertTrue((self.root / original["path"]).exists())
        self.assertTrue(self.project["episodes"][0]["storyboard"][0]["needs_review"])
        self.assertEqual(self.service.get("CONTENT_test", prior)["project"]["assets"][0]["path"], "screen.png")

    def test_changed_file_blocked_and_overwrite_registration_rejected(self):
        self.image()
        Image.new("RGB", (100, 100), "blue").save(self.root / "screen.png")
        data = {**self.project["assets"][0]}; data.pop("sha256"); data.pop("bytes")
        with self.assertRaises(ContentError):
            self.apply("asset", data)
        self.assertTrue(self.service.get("CONTENT_test")["checks"]["blockers"])
        with self.assertRaises(ContentError):
            self.service.public_image("CONTENT_test", "screen")

    def test_character_approval_is_bound_to_reference_and_version(self):
        self.image("person", "generated_still", "person.png")
        char = {"character_id": "aki", "fictional_adult": True, "name": "架空のアキ", "persona": "知的な会社員", "role": "試す人", "clothing": "紺のスーツ", "voice": "落ち着いて話す", "continuity": "同じ架空企画を担当", "reference_asset_id": "person"}
        self.apply("character", char)
        movie = self.root / "motion.mp4"; movie.write_bytes(b"fake movie not production evidence")
        media = {"asset_id": "motion", "kind": "generated_video", "path": "motion.mp4", "visibility": "private", "character_id": "aki", "character_version": 1, "provider": "minimax", "generation_record": "fictional test receipt"}
        with self.assertRaises(ContentError):
            self.apply("asset", media)

        self.apply("approve-character", {"character_id": "aki", "version": 1, "confirm_acceptance": True, "user_response": "この人物でお願いします", "scope": "架空テストシリーズ"})
        self.apply("asset", media)
        self.assertEqual(self.project["assets"][-1]["technical_status"], "unverified")
        self.apply("character", {**char, "clothing": "明るいジャケット"})
        self.assertIsNone(self.project["characters"][0]["approval"])
        with self.assertRaises(ContentError):
            self.apply("asset", media)

    def test_tested_claim_requires_real_capture_kind_and_written_conditions(self):
        self.prepared()
        self.image("concept", "generated_still", "concept.png")
        with self.assertRaises(ContentError):
            self.claim("tested", basis="tested", asset_ids=["concept"], test_conditions="架空テスト条件")
        self.image()
        with self.assertRaises(ContentError):
            self.claim("tested", basis="tested", asset_ids=["screen"], test_conditions=True)
        self.claim("tested", basis="tested", asset_ids=["screen"], test_conditions="架空素材による保存処理のソフトウェア試験。実製品の検証ではない。")
        self.assertEqual(self.project["claims"][-1]["basis"], "tested")

    def test_import_schema_one_preserves_original_unknowns_and_published_state(self):
        legacy = {"schema_version": 1, "content_project_id": "CONTENT_legacy", "article": {"slug": "old", "published": True}, "assets": [], "videos": [{"production_id": "SHORT_old"}], "issues": [{"id": "capture", "status": "pending"}], "custom": {"approval": False}}
        out = self.service.create({"content_project_id": "CONTENT_legacy", "operation_id": "op_legacy", "title": "旧企画", "legacy_project": legacy})["project"]
        self.assertEqual(out["legacy_project"], legacy)
        self.assertEqual(out["legacy_refs"][0]["production_id"], "SHORT_old")
        self.assertIsNone(out["accepted_proposal"])
        self.assertTrue(out["article"]["published"])

    def test_conflict_idempotence_and_immutable_history(self):
        body = {"operation_id": "op_retry", "expected_revision": 1, "data": {"archived": True}}
        first = self.service.apply("CONTENT_test", "archive", body)
        repeated = self.service.apply("CONTENT_test", "archive", body)
        self.assertEqual(first["project"], repeated["project"])
        with self.assertRaises(ContentError) as conflict:
            self.service.apply("CONTENT_test", "archive", {**body, "operation_id": "op_other"})
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(ContentError):
            self.service.apply("CONTENT_test", "archive", {**body, "data": {"archived": False}})
        with self.db.session() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM content_project_revisions")

    def test_private_traversal_symlink_and_signed_sources_rejected(self):
        self.image("private", path="_private/original.png", visibility="private")
        with self.assertRaises(ContentError):
            self.apply("asset", {"asset_id": "escape", "kind": "generated_still", "visibility": "public", "path": "../out.png"})
        with self.assertRaises(ContentError):
            self.apply("asset", {"asset_id": "leak", "kind": "generated_still", "visibility": "public", "privacy_review": "passed", "path": "_private/original.png"})
        with self.assertRaises(ContentError):
            self.service.public_image("CONTENT_test", "private")
        signed = source(); signed["url"] += "?X-Amz-Signature=secret"
        with self.assertRaises(ContentError):
            self.research(sources=[signed])
        try:
            (self.root / "alias.png").symlink_to(self.root / "_private/original.png")
        except OSError:
            return  # Windows may require symlink privilege; traversal checks still run.
        with self.assertRaises(ContentError):
            self.apply("asset", {"asset_id": "alias", "kind": "generated_still", "visibility": "public", "privacy_review": "passed", "path": "alias.png"})

    def test_public_snapshot_and_blog_export_are_separate_and_do_not_publish(self):
        self.image(); self.image("private", path="_private/original.png", visibility="private")
        self.apply("article", {"slug": "fictional-docs", "published": False, "sections": [{"section_id": "example", "title": "画面", "asset_ids": ["screen"]}]})
        snapshot = self.service.export_snapshot("CONTENT_test", expected_revision=self.project["revision"], confirm_public_review=True)
        data = json.loads((snapshot / "content-project.public.json").read_text(encoding="utf-8"))
        self.assertEqual([a["asset_id"] for a in data["assets"]], ["screen"])
        self.assertNotIn("_private", (snapshot / "content-project.public.json").read_text(encoding="utf-8"))
        out = self.service.export_blog("CONTENT_test", "v01")
        manifest = json.loads((out / "asset-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["publication_approval"], "pending")
        self.assertFalse(manifest["article_published"])
        self.assertEqual((out / "assets/screen.png").read_bytes(), (self.root / "screen.png").read_bytes())
        with self.assertRaises(ContentError):
            self.service.export_blog("CONTENT_test", "v01")

    def test_bad_payloads_are_validation_errors_and_rollback(self):
        self.prepared(); previous = deepcopy(self.project)
        for action, data in [("claim", {"source_ids": "docs"}), ("capture", {"episode_id": "one", "status": "unknown"}), ("article", {"sections": "bad"}), ("reconcile", {"scope": "other"})]:
            with self.subTest(action=action), self.assertRaises(ContentError):
                self.apply(action, data)
        self.assertEqual(self.service.get("CONTENT_test")["project"], previous)

    def test_pending_revision_request_requires_new_proposal_before_adoption(self):
        self.research(); self.propose()
        self.apply("feedback", {"feedback_id": "changes", "proposal_id": "proposal_one", "text": "2本へ分けたい", "interpretation": "次案で分割"})
        self.apply("feedback", {"feedback_id": "approve", "proposal_id": "proposal_one", "text": "この案で", "interpretation": "採用", "kind": "acceptance"})
        with self.assertRaises(ContentError):
            self.apply("accept", {"proposal_id": "proposal_one", "feedback_id": "approve", "confirm_acceptance": True})
        self.propose("proposal_two", [episode("one"), episode("two")])
        self.accept("proposal_two", "approve_new")
        self.assertEqual(len(self.project["episodes"]), 2)
        self.assertIn("changes", self.project["proposals"][-1]["based_on_feedback"])

    def test_merge_preserves_retired_episode_and_only_changed_message_is_stale(self):
        self.prepared([episode("one"), episode("two")]); self.image(); self.claim()
        for eid in ("one", "two"):
            self.apply("capture", {"episode_id": eid, **capture()}); self.storyboard(eid)
        self.apply("article", {"sections": [{"section_id": "detail", "title": "詳しい手順", "episode_ids": ["two"]}]})
        self.propose("proposal_two", [{**episode(), "intended_message": "一つにまとめた説明"}])
        self.accept("proposal_two", "approve_two")
        self.assertEqual(len(self.project["retired_episodes"]), 1)
        self.assertTrue(self.project["episodes"][0]["storyboard"][0]["needs_review"])
        self.assertTrue(self.project["article"]["sections"][0]["needs_review"])
        self.assertEqual(self.project["episodes"][0]["capture_plan"]["status"], "available")

    def test_historical_public_preview_uses_exact_asset_version(self):
        self.image(); original = (self.root / "screen.png").read_bytes()
        self.image(path="screen-v2.png")
        self.assertEqual(self.service.public_image("CONTENT_test", "screen", 1)[0], original)
        with self.assertRaises(KeyError):
            self.service.public_image("CONTENT_test", "screen", 99)

    def test_cli_connection_does_not_run_worker_recovery(self):
        from unittest.mock import patch
        with patch.object(StudioDatabase, "interrupt_active_work") as recovery:
            StudioDatabase(self.root / "studio.sqlite3", workspace=self.root, recover=False)
        recovery.assert_not_called()

    def test_cli_shares_state_without_recovery_or_provider_calls(self):
        result = subprocess.run([sys.executable, "-m", "tools.studio.content_workspace", "get", "--workspace", str(self.root), "--database", "studio.sqlite3", "--project-id", "CONTENT_test"], capture_output=True, text=True, encoding="utf-8", env={**__import__('os').environ, "PYTHONIOENCODING": "utf-8"}, check=True)
        self.assertEqual(json.loads(result.stdout)["project"], self.project)


class ContentWorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        static = self.root / "static"; static.mkdir(); (static / "index.html").write_text("<!doctype html><title>Test</title>")
        self.server = create_server(self.root, port=0, static_dir="static", initial_refresh=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(5)

    def request(self, method, path, body=None, authorized=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["X-Studio-Token"] = self.server.session_token
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse(); status = response.status; data = response.read(); connection.close()
        return status, json.loads(data) if data else None

    def test_same_contract_and_authentication_and_conflicts(self):
        self.assertEqual(self.request("GET", "/api/content-projects", authorized=False)[0], 403)
        body = {"content_project_id": "CONTENT_http", "operation_id": "op_create", "title": "架空企画"}
        self.assertEqual(self.request("POST", "/api/content-projects", body, authorized=False)[0], 403)
        status, created = self.request("POST", "/api/content-projects", body)
        self.assertEqual(status, 201)
        status, loaded = self.request("GET", "/api/content-projects/CONTENT_http")
        self.assertEqual(status, 200); self.assertEqual(created["project"], loaded["project"])
        mutation = {"operation_id": "op_archive", "expected_revision": 1, "data": {"archived": True}}
        self.assertEqual(self.request("POST", "/api/content-projects/CONTENT_http/archive", mutation)[0], 200)
        mutation["operation_id"] = "op_conflict"
        self.assertEqual(self.request("POST", "/api/content-projects/CONTENT_http/archive", mutation)[0], 409)
        self.assertEqual(self.request("GET", "/api/content-projects/CONTENT_http?revision=1")[1]["project"]["revision"], 1)
        self.assertEqual(self.request("GET", "/api/content-projects/CONTENT_http?revision=no")[0], 422)
        self.assertEqual(self.request("GET", "/api/content-projects/CONTENT_missing")[0], 404)


if __name__ == "__main__":
    unittest.main()
