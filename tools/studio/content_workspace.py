"""Chat-first editorial workspace. No network calls, generation, or publication.

Research and natural-language interpretation are performed by the chat assistant.
This service durably records those results and enforces their evidence boundaries.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import sys
from typing import Any
from urllib.parse import urlsplit, parse_qsl
import uuid

from PIL import Image

from .database import StudioDatabase
from .security import sensitive_artifact_path, workspace_path, sanitize_for_storage

PROJECT_RE = r"CONTENT_[A-Za-z0-9_-]{1,120}"
ENTITY_RE = r"[a-z][a-z0-9_-]{0,79}"
MAX_DOCUMENT_BYTES = 900_000
ACTION_NAMES = {"research", "proposal", "feedback", "accept", "capture", "claim",
                "asset", "character", "approve-character", "storyboard", "reconcile",
                "article", "archive", "link-production"}


class ContentError(ValueError):
    def __init__(self, message: str, *, code="invalid_content_request", status=422):
        super().__init__(message)
        self.code, self.status = code, status


def install_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS content_projects (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document_json TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS content_project_revisions (
        project_id TEXT NOT NULL REFERENCES content_projects(id), revision INTEGER NOT NULL,
        operation_id TEXT NOT NULL, request_digest TEXT NOT NULL, action TEXT NOT NULL,
        document_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(project_id, revision), UNIQUE(project_id, operation_id))""")
    for action in ("UPDATE", "DELETE"):
        connection.execute(f"""CREATE TRIGGER IF NOT EXISTS content_revisions_no_{action.lower()}
            BEFORE {action} ON content_project_revisions BEGIN
            SELECT RAISE(ABORT, 'content revisions are immutable'); END""")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def text(value: Any, name: str, maximum=12_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContentError(f"{name}を入力してください（最大{maximum}文字）。")
    return value.strip()


def identity(value: Any, name="id", pattern=ENTITY_RE) -> str:
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ContentError(f"{name}の形式が不正です。")
    return value


def dated(value: Any, name="checked_at") -> str:
    value = text(value, name, 60)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContentError(f"{name}はISO形式の日付・日時にしてください。") from exc
    return value


def source_url(value: Any) -> str:
    value = text(value, "source_url", 3000)
    parsed = urlsplit(value)
    forbidden = {"token", "key", "api_key", "access_token", "signature", "sig"}
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or any(k.lower().startswith("x-amz-") or k.lower() in forbidden
                   for k, _ in parse_qsl(parsed.query))):
        raise ContentError("出典は認証情報を含まないHTTPS URLにしてください。")
    return value


def records(value: Any, name: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
        raise ContentError(f"{name}はオブジェクトの配列にしてください。")
    return value


def references(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value) or len(value) != len(set(value)):
        raise ContentError(f"{name}は重複しないIDの配列にしてください。")
    return value


def bounded_body(body: Any) -> None:
    if not isinstance(body, dict):
        raise ContentError("操作はJSONオブジェクトで指定してください。")
    try:
        size = len(encoded(body).encode())
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContentError("有限値だけを含むJSONで指定してください。") from exc
    if size > MAX_DOCUMENT_BYTES:
        raise ContentError("操作が大きすぎます。長い原本はファイル参照にしてください。")


def find(items: list[dict], key: str, value: str) -> dict:
    for item in items:
        if item.get(key) == value:
            return item
    raise ContentError(f"参照先が見つかりません: {key}={value}")


def upsert(items: list[dict], key: str, value: dict) -> dict | None:
    old = next((i for i in items if i.get(key) == value[key]), None)
    if old is not None:
        items[items.index(old)] = value
    else:
        items.append(value)
    return old


def invalidate(project: dict, kind: str, item_id: str, reason: str) -> None:
    """Only dependent cuts/sections are stale. Assets/audio are never regenerated."""
    field = f"{kind}_ids"
    for episode in project["episodes"]:
        for scene in episode.get("storyboard", []):
            if item_id in scene.get(field, []):
                scene["needs_review"] = True
                scene["review_reasons"] = sorted(set(scene.get("review_reasons", []) + [reason]))
    for section in project["article"].get("sections", []):
        if item_id in section.get(field, []):
            section["needs_review"] = True
            section["review_reasons"] = sorted(set(section.get("review_reasons", []) + [reason]))


class ContentWorkspace:
    def __init__(self, workspace: Path, database: StudioDatabase):
        self.workspace, self.database = workspace.resolve(), database

    def _path(self, relative: Any, *, public=False) -> Path:
        relative = text(relative, "path", 1000)
        if PureWindowsPath(relative).drive or Path(relative).is_absolute() or ".." in Path(relative.replace("\\", "/")).parts:
            raise ContentError("素材はワークスペース内の相対パスで指定してください。")
        try:
            result = workspace_path(self.workspace, relative).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ContentError("素材をワークスペース内で開けません。") from exc
        if not result.is_relative_to(self.workspace) or not result.is_file() or sensitive_artifact_path(result):
            raise ContentError("この素材パスは登録できません。")
        if public and any(p.lower() in {"private", "_private"} for p in result.relative_to(self.workspace).parts):
            raise ContentError("非公開原本は公開用素材として登録できません。")
        return result

    def _asset(self, value: dict, project: dict) -> dict:
        value = deepcopy(value)
        identity(value.get("asset_id"), "asset_id")
        kind = value.get("kind")
        if kind not in {"demonstration_capture", "official_capture", "generated_still", "generated_video", "audio", "original"}:
            raise ContentError("素材のkindが不正です。")
        if value.get("visibility") not in {"private", "public"}:
            raise ContentError("素材の公開範囲を明示してください。")
        path = self._path(value.get("path"), public=value["visibility"] == "public")
        value["path"] = path.relative_to(self.workspace).as_posix()
        sha = self._hash(path)
        if value.get("sha256") and value["sha256"].upper() != sha:
            raise ContentError("素材のハッシュが一致しません。")
        if value.get("bytes") is not None and value["bytes"] != path.stat().st_size:
            raise ContentError("素材の容量が一致しません。")
        value.update(sha256=sha, bytes=path.stat().st_size, registered_at=now())
        old = next((a for a in project["assets"] if a["asset_id"] == value["asset_id"]), None)
        if old and old["path"] == value["path"] and old["sha256"] != sha:
            raise ContentError("旧原本を上書きせず、新しい素材パスで改訂してください。")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            with Image.open(path) as image:
                if (value.get("width") is not None and value["width"] != image.width
                        or value.get("height") is not None and value["height"] != image.height):
                    raise ContentError("素材の寸法が記録と一致しません。")
                value.update(width=image.width, height=image.height)
                image.verify()
        elif kind in {"demonstration_capture", "official_capture", "generated_still"}:
            raise ContentError("画面・静止画はPNG/JPEG/WebPで登録してください。")
        if value.get("parent_asset_id"):
            if value["parent_asset_id"] == value["asset_id"]:
                raise ContentError("素材は自分自身を派生元にできません。")
            find(project["assets"], "asset_id", value["parent_asset_id"])
        if kind == "official_capture":
            value["source_url"] = source_url(value.get("source_url"))
            dated(value.get("source_checked_at"))
        if kind == "demonstration_capture" and value.get("fictional_materials_only") is not True:
            raise ContentError("実演には架空素材だけを使用してください。")
        if value["visibility"] == "public" and value.get("privacy_review") != "passed":
            raise ContentError("公開用素材には個人情報の確認が必要です。")
        if kind == "generated_video":
            character = find(project["characters"], "character_id", value.get("character_id"))
            reference = find(project["assets"], "asset_id", character["reference_asset_id"])
            self._verify_asset(reference)
            if (not character.get("approval") or character["version"] != value.get("character_version")
                    or reference["sha256"] != character["reference_sha256"]):
                raise ContentError("確認済みの人物と版を指定してください。")
            if path.suffix.lower() != ".mp4" or value.get("provider") != "minimax":
                raise ContentError("人物動画にはMiniMaxのMP4と生成記録を指定してください。")
            text(value.get("generation_record"), "generation_record")
            # Registration proves bytes/identity, not motion quality or human review.
            value["technical_status"] = "unverified"
        value["version"] = next((i["version"] + 1 for i in project["assets"] if i["asset_id"] == value["asset_id"]), 1)
        return value

    @staticmethod
    def _hash(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest().upper()

    def list(self) -> dict:
        with self.database.session() as connection:
            rows = connection.execute("SELECT document_json FROM content_projects ORDER BY updated_at DESC, id").fetchall()
        return {"items": [{k: p[k] for k in ("content_project_id", "title", "revision", "phase", "archived", "updated_at")}
                          for p in (json.loads(row[0]) for row in rows)]}

    def get(self, project_id: str, revision: int | None = None) -> dict:
        identity(project_id, pattern=PROJECT_RE)
        with self.database.session() as connection:
            if revision is None:
                row = connection.execute("SELECT document_json FROM content_projects WHERE id=?", (project_id,)).fetchone()
            else:
                row = connection.execute("SELECT document_json FROM content_project_revisions WHERE project_id=? AND revision=?", (project_id, revision)).fetchone()
            if row is None:
                raise KeyError(project_id)
            project = json.loads(row[0])
            history = connection.execute("SELECT revision, action, created_at FROM content_project_revisions WHERE project_id=? ORDER BY revision DESC", (project_id,)).fetchall()
        return {"project": project, "history": [dict(i) for i in history], "checks": self.checks(project)}

    def create(self, body: dict) -> dict:
        bounded_body(body)
        project_id = identity(body.get("content_project_id"), pattern=PROJECT_RE)
        operation = identity(body.get("operation_id"), "operation_id")
        legacy = body.get("legacy_project")
        if legacy is not None and (not isinstance(legacy, dict) or legacy.get("schema_version") != 1 or legacy.get("content_project_id") != project_id):
            raise ContentError("schema1の企画IDを維持して取り込んでください。")
        title = text(body.get("title") or (legacy or {}).get("title"), "title", 250)
        project = dict(schema_version=2, content_project_id=project_id, title=title,
                       revision=1, phase="researching", archived=False, updated_at=now(),
                       request={"topic": text(body.get("topic") or title, "topic"),
                                "audience": text(body.get("audience") or (legacy or {}).get("audience") or "仕事でAIを使いたい人", "audience", 1000),
                                "format": body.get("format", "shorts_first")},
                       research=[], proposals=[], feedback=[], accepted_proposal=None, capture_inspections=[],
                       episodes=[], retired_episodes=[], claims=[], assets=[], characters=[],
                       article={"sections": []}, legacy_refs=[], production_links=[])
        if legacy:
            records(legacy.get("assets", []), "legacy.assets")
            project["legacy_project"] = deepcopy(legacy)
            project["legacy_refs"] = deepcopy(legacy.get("videos", []))
            project["article"] = {**deepcopy(legacy.get("article", {})), "sections": []}
            # Old approvals and incomplete capture states remain in the original,
            # never elevated to new proposal/character decisions.
            for asset in legacy.get("assets", []):
                try:
                    project["assets"].append(self._asset({**asset, "visibility": "public"}, project))
                except (ValueError, OSError, KeyError) as exc:
                    project.setdefault("import_issues", []).append({"asset_id": asset.get("asset_id"), "message": str(exc)})
        digest = hashlib.sha256(encoded(body).encode()).hexdigest()
        with self.database.transaction() as connection:
            existing = connection.execute("SELECT request_digest, document_json FROM content_project_revisions WHERE project_id=? AND operation_id=?", (project_id, operation)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ContentError("同じ操作IDが異なる内容に使われています。", status=409)
                return self._response(json.loads(existing[1]))
            if connection.execute("SELECT 1 FROM content_projects WHERE id=?", (project_id,)).fetchone():
                raise ContentError("企画IDは既に存在します。", status=409)
            raw = encoded(project)
            connection.execute("INSERT INTO content_projects VALUES(?,?,?,?)", (project_id, 1, raw, project["updated_at"]))
            connection.execute("INSERT INTO content_project_revisions VALUES(?,?,?,?,?,?,?)", (project_id, 1, operation, digest, "create", raw, project["updated_at"]))
        return self.get(project_id)

    def _response(self, project: dict) -> dict:
        return {"project": project, "checks": self.checks(project)}

    def apply(self, project_id: str, action: str, body: dict) -> dict:
        bounded_body(body)
        identity(project_id, pattern=PROJECT_RE)
        if action not in ACTION_NAMES:
            raise ContentError("未対応の企画操作です。")
        operation = identity(body.get("operation_id"), "operation_id")
        expected = body.get("expected_revision")
        if type(expected) is not int or expected < 1 or not isinstance(body.get("data"), dict):
            raise ContentError("expected_revisionとdataを指定してください。")
        digest = hashlib.sha256(encoded({"action": action, **body}).encode()).hexdigest()
        with self.database.transaction() as connection:
            existing = connection.execute("SELECT request_digest, document_json FROM content_project_revisions WHERE project_id=? AND operation_id=?", (project_id, operation)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ContentError("操作IDの内容が一致しません。", status=409)
                return self._response(json.loads(existing[1]))
            row = connection.execute("SELECT document_json FROM content_projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(project_id)
            project = json.loads(row[0])
            if project["revision"] != expected:
                raise ContentError("企画が更新されています。最新版を取得してください。", code="content_revision_conflict", status=409)
            if project["archived"] and action != "archive":
                raise ContentError("再開してから編集してください。", status=409)
            try:
                self._change(project, action, deepcopy(body["data"]))
            except ContentError:
                raise
            except (TypeError, AttributeError, KeyError, OverflowError, ValueError, OSError) as exc:
                raise ContentError("項目の型・必須項目・参照IDを確認してください。") from exc
            project.update(revision=expected + 1, updated_at=now())
            raw = encoded(project)
            if len(raw.encode()) > MAX_DOCUMENT_BYTES:
                raise ContentError("企画が大きすぎます。原本・長いログはファイル参照にしてください。")
            connection.execute("UPDATE content_projects SET revision=?,document_json=?,updated_at=? WHERE id=?", (project["revision"], raw, project["updated_at"], project_id))
            connection.execute("INSERT INTO content_project_revisions VALUES(?,?,?,?,?,?,?)", (project_id, project["revision"], operation, digest, action, raw, project["updated_at"]))
        return self.get(project_id)

    def _change(self, p: dict, action: str, d: dict) -> None:
        p.setdefault("capture_inspections", [])
        if action == "research":
            identity(d.get("research_id"), "research_id")
            if any(r["research_id"] == d["research_id"] for r in p["research"]):
                raise ContentError("調査は新しいresearch_idで追記してください。")
            text(d.get("summary"), "summary")
            dated(d.get("checked_at"))
            sources = records(d.get("sources"), "sources")
            if not sources:
                raise ContentError("出典を1件以上登録してください。")
            ids = set()
            for source in sources:
                sid = identity(source.get("source_id"), "source_id")
                if sid in ids:
                    raise ContentError("source_idが重複しています。")
                ids.add(sid)
                source["url"] = source_url(source.get("url"))
                text(source.get("title"), "source.title")
                dated(source.get("checked_at"))
                if source.get("kind") not in {"official", "first_hand", "secondary"}:
                    raise ContentError("出典の種類を指定してください。")
                for key in ("published_at", "event_at"):
                    if source.get(key):
                        dated(source[key], key)
                for episode in p["episodes"]:
                    for scene in episode.get("storyboard", []):
                        if sid in scene.get("source_ids", []):
                            scene["needs_review"] = True
                if any(s.get("source_id") == sid for r in p["research"] for s in r["sources"]):
                    for claim in p["claims"]:
                        if sid in claim.get("source_ids", []):
                            claim["needs_review"] = True
                            invalidate(p, "claim", claim["claim_id"], "出典が更新されました")
                    invalidate(p, "source", sid, "出典が更新されました")
            p["research"].append(d)
        elif action == "proposal":
            identity(d.get("proposal_id"), "proposal_id")
            if not p["research"] or any(x["proposal_id"] == d["proposal_id"] for x in p["proposals"]):
                raise ContentError("調査後に新しいproposal_idで提案してください。")
            text(d.get("count_reason"), "count_reason")
            episodes = records(d.get("episodes"), "episodes")
            if not episodes or len(episodes) > 50:
                raise ContentError("動画案は1〜50本で提案してください。")
            if len({identity(e.get("episode_id"), "episode_id") for e in episodes}) != len(episodes):
                raise ContentError("episode_idが重複しています。")
            for episode in episodes:
                for key in ("title", "overview", "intended_message", "demo_idea", "article_role"):
                    text(episode.get(key), key)
                if type(episode.get("duration_seconds")) not in (int, float) or not 1 <= episode["duration_seconds"] <= 3600:
                    raise ContentError("想定尺を1〜3600秒で指定してください。")
                # Proposal inputs cannot inject downstream evidence or reviewed cuts.
                for key in ("capture_plan", "storyboard"):
                    episode.pop(key, None)
                if episode.get("capture_inspection_id"):
                    find(p["capture_inspections"], "inspection_id", episode["capture_inspection_id"])
            d["based_on_research"] = [r["research_id"] for r in p["research"]]
            d["based_on_feedback"] = [f["feedback_id"] for f in p["feedback"]]
            d["created_at"] = now()
            p["proposals"].append(d)
            p["phase"] = "awaiting_feedback"
        elif action == "feedback":
            identity(d.get("feedback_id"), "feedback_id")
            find(p["proposals"], "proposal_id", d.get("proposal_id"))
            text(d.get("text"), "ユーザーの返答")
            text(d.get("interpretation"), "反映する内容")
            if d.get("kind", "revision_request") not in {"revision_request", "comment", "acceptance"}:
                raise ContentError("返答のkindが不正です。")
            d.setdefault("kind", "revision_request")
            if any(f["feedback_id"] == d["feedback_id"] for f in p["feedback"]):
                raise ContentError("feedback_idが重複しています。")
            d["created_at"] = now()
            p["feedback"].append(d)
        elif action == "accept":
            proposal = find(p["proposals"], "proposal_id", d.get("proposal_id"))
            if proposal is not p["proposals"][-1]:
                raise ContentError("最新の提案を確認してください。")
            feedback = find(p["feedback"], "feedback_id", d.get("feedback_id"))
            if feedback["proposal_id"] != proposal["proposal_id"] or d.get("confirm_acceptance") is not True:
                raise ContentError("この提案への明示的な採用返答が必要です。")
            pending = [f for f in p["feedback"] if f["kind"] == "revision_request"
                       and f["feedback_id"] not in proposal.get("based_on_feedback", [])
                       and f["feedback_id"] != feedback["feedback_id"]]
            if pending:
                raise ContentError("修正の相談を企画案へ反映してから採用してください。")
            episodes = []
            for entry in proposal["episodes"]:
                old = next((e for e in p["episodes"] if e["episode_id"] == entry["episode_id"]), {})
                episode = {**deepcopy(old), **deepcopy(entry)}
                inspection = next((i for i in p["capture_inspections"] if i["inspection_id"] == entry.get("capture_inspection_id")), None)
                episode.setdefault("capture_plan", deepcopy(inspection) if inspection else {"status": "uninspected", "shots": []})
                episode.setdefault("storyboard", [])
                if old and any(old.get(k) != entry.get(k) for k in ("intended_message", "overview", "demo_idea")):
                    for scene in episode["storyboard"]:
                        scene.update(needs_review=True, review_reasons=["企画の意図が変更されました"])
                    invalidate(p, "episode", entry["episode_id"], "企画の意図が変更されました")
                    if old.get("demo_idea") != entry.get("demo_idea"):
                        episode["capture_plan"] = {"status": "uninspected", "shots": [], "previous_check_revision": p["revision"]}
                episodes.append(episode)
            kept = {e["episode_id"] for e in episodes}
            for old in p["episodes"]:
                if old["episode_id"] not in kept:
                    invalidate(p, "episode", old["episode_id"], "動画構成が統合・変更されました")
            p["retired_episodes"].extend(e for e in p["episodes"] if e["episode_id"] not in kept)
            p.update(episodes=episodes, accepted_proposal={"proposal_id": proposal["proposal_id"], "feedback_id": feedback["feedback_id"], "accepted_at": now()}, phase="capture_planning")
        elif action == "capture":
            episode_id = d.pop("episode_id", None)
            episode = find(p["episodes"], "episode_id", episode_id) if episode_id else None
            if episode is None:
                identity(d.get("inspection_id"), "inspection_id")
                text(d.get("target_feature"), "対象機能")
            if d.get("status") not in {"uninspected", "available", "blocked", "captured"}:
                raise ContentError("撮影の確認状態が不正です。")
            if d["status"] != "uninspected":
                dated(d.get("checked_at"))
                text(d.get("route"), "試した経路")
                text(d.get("result"), "確認結果")
                for key in ("app", "login_state", "feature_entry", "display_result", "save_result", "legibility"):
                    text(d.get(key), key)
            shots = records(d.get("shots", []), "shots")
            if len({s.get("shot_id") for s in shots}) != len(shots):
                raise ContentError("shot_idが重複しています。")
            for shot in shots:
                identity(shot.get("shot_id"), "shot_id")
                text(shot.get("purpose"), "shot.purpose")
                if shot.get("asset_id"):
                    asset = find(p["assets"], "asset_id", shot["asset_id"])
                    if asset["kind"] != "demonstration_capture":
                        raise ContentError("実演ショットには実画面を指定してください。")
                    self._verify_asset(asset)
            if d["status"] == "captured" and not any(s.get("asset_id") for s in shots):
                raise ContentError("撮影済みには保存した実画面が必要です。")
            if episode is None:
                upsert(p["capture_inspections"], "inspection_id", d)
            else:
                episode["capture_plan"] = d
        elif action == "claim":
            identity(d.get("claim_id"), "claim_id")
            text(d.get("text"), "claim.text")
            dated(d.get("checked_at"))
            if d.get("basis") not in {"official", "tested", "hypothesis"}:
                raise ContentError("主張の根拠を指定してください。")
            sources = {s["source_id"]: s for r in p["research"] for s in r["sources"]}
            refs = references(d.get("source_ids", []), "source_ids")
            if any(i not in sources for i in refs):
                raise ContentError("主張の出典が登録されていません。")
            if d["basis"] == "official" and not any(sources[i]["kind"] == "official" for i in refs):
                raise ContentError("公式情報には公式出典が必要です。")
            assets = references(d.get("asset_ids", []), "asset_ids")
            for aid in assets:
                asset = find(p["assets"], "asset_id", aid)
                self._verify_asset(asset)
            if d["basis"] == "tested" and (not assets or any(find(p["assets"], "asset_id", a)["kind"] != "demonstration_capture" for a in assets) or not d.get("test_conditions")):
                raise ContentError("実機確認には実画面と検証条件が必要です。")
            if d["basis"] == "tested":
                text(d.get("test_conditions"), "test_conditions")
            d["needs_review"] = False
            old = upsert(p["claims"], "claim_id", d)
            if old != d and old is not None:
                invalidate(p, "claim", d["claim_id"], "主張・条件・根拠が変更されました")
        elif action == "asset":
            asset = self._asset(d, p)
            old = upsert(p["assets"], "asset_id", asset)
            if old:
                invalidate(p, "asset", asset["asset_id"], "素材の版が更新されました")
                for claim in p["claims"]:
                    if asset["asset_id"] in claim.get("asset_ids", []):
                        claim["needs_review"] = True
                        invalidate(p, "claim", claim["claim_id"], "実演素材が更新されました")
        elif action == "character":
            identity(d.get("character_id"), "character_id")
            if d.get("fictional_adult") is not True:
                raise ContentError("架空の成人として人物を設定してください。")
            for key in ("name", "persona", "role", "clothing", "voice", "continuity"):
                text(d.get(key), key)
            asset = find(p["assets"], "asset_id", d.get("reference_asset_id"))
            if asset["kind"] != "generated_still":
                raise ContentError("人物の参照画像を指定してください。")
            d.update(reference_sha256=asset["sha256"], version=next((c["version"] + 1 for c in p["characters"] if c["character_id"] == d["character_id"]), 1), approval=None)
            old = upsert(p["characters"], "character_id", d)
            if old:
                invalidate(p, "character", d["character_id"], "人物設定が変更されました")
        elif action == "approve-character":
            character = find(p["characters"], "character_id", d.get("character_id"))
            reference = find(p["assets"], "asset_id", character["reference_asset_id"])
            self._verify_asset(reference)
            if d.get("version") != character["version"] or d.get("confirm_acceptance") is not True or reference["sha256"] != character["reference_sha256"]:
                raise ContentError("現在の人物版と参照画像への確認が必要です。")
            character["approval"] = {"user_response": text(d.get("user_response"), "ユーザーの返答"), "scope": text(d.get("scope"), "採用範囲"), "accepted_at": now()}
        elif action == "storyboard":
            episode = find(p["episodes"], "episode_id", d.get("episode_id"))
            if episode["capture_plan"]["status"] == "uninspected":
                raise ContentError("台本を固める前に実画面の撮影可否を確認してください。")
            scenes = records(d.get("scenes"), "scenes")
            if not scenes or len({identity(s.get("scene_id"), "scene_id") for s in scenes}) != len(scenes):
                raise ContentError("重複しないscene_idを設定してください。")
            for scene in scenes:
                for key in ("purpose", "narration", "visual"):
                    text(scene.get(key), key)
                if type(scene.get("duration_seconds")) not in (int, float) or not 0 < scene["duration_seconds"] <= 600:
                    raise ContentError("場面尺が不正です。")
                if scene.get("beat", "evidence") not in {"problem", "try", "insight", "action", "evidence", "transition"}:
                    raise ContentError("場面の物語上の役割が不正です。")
                for kind, target in (("claim", p["claims"]), ("asset", p["assets"]), ("character", p["characters"])):
                    for value in references(scene.get(kind + "_ids", []), kind + "_ids"):
                        find(target, kind + "_id", value)
                known_sources = {s["source_id"] for r in p["research"] for s in r["sources"]}
                if any(sid not in known_sources for sid in references(scene.get("source_ids", []), "source_ids")):
                    raise ContentError("場面の出典が登録されていません。")
                for char_id in scene.get("character_ids", []):
                    character = find(p["characters"], "character_id", char_id)
                    text(scene.get("character_action"), "人物の動き")
                    if scene.get("presenter_layout") != "fullscreen" or scene.get("face_caption_separated") is not True:
                        raise ContentError("人物は全面表示と顔・字幕の分離を設計してください。")
                scene.update(needs_review=False, review_reasons=[])
            episode["storyboard"] = scenes
            p["phase"] = "storyboard_ready" if all(e.get("storyboard") for e in p["episodes"]) else "capture_planning"
        elif action == "article":
            sections = records(d.get("sections", []), "sections")
            if len({s.get("section_id") for s in sections}) != len(sections):
                raise ContentError("section_idが重複しています。")
            for section in sections:
                identity(section.get("section_id"), "section_id")
                text(section.get("title"), "section.title")
                for kind in ("claim", "asset", "character"):
                    for value in references(section.get(kind + "_ids", []), kind + "_ids"):
                        find(p[kind + "s"], kind + "_id", value)
                for value in references(section.get("episode_ids", []), "episode_ids"):
                    find(p["episodes"], "episode_id", value)
                known_sources = {s["source_id"] for r in p["research"] for s in r["sources"]}
                if any(sid not in known_sources for sid in references(section.get("source_ids", []), "source_ids")):
                    raise ContentError("記事節の出典が登録されていません。")
                section["needs_review"] = False
            p["article"] = d
        elif action == "reconcile":
            scope = d.get("scope")
            if scope not in {"scene", "section"}:
                raise ContentError("再確認のscopeはsceneまたはsectionです。")
            target = (find(find(p["episodes"], "episode_id", d.get("episode_id"))["storyboard"], "scene_id", d.get("scene_id")) if scope == "scene"
                      else find(p["article"].get("sections", []), "section_id", d.get("section_id")))
            text(d.get("reason"), "再確認の結果")
            target.update(needs_review=False, review_reasons=[], last_review={"reason": d["reason"], "checked_at": now()})
        elif action == "archive":
            if type(d.get("archived")) is not bool:
                raise ContentError("archivedは真偽値にしてください。")
            p["archived"] = d["archived"]
        elif action == "link-production":
            identity(d.get("production_id"), "production_id", r"production_[a-f0-9]{32}")
            find(p["episodes"], "episode_id", d.get("episode_id"))
            upsert(p["production_links"], "episode_id", d)

    def _verify_asset(self, asset: dict) -> None:
        path = self._path(asset["path"], public=asset.get("visibility") == "public")
        if path.stat().st_size != asset["bytes"] or self._hash(path) != asset["sha256"]:
            raise ContentError(f"素材が登録時から変わっています: {asset['asset_id']}")

    def public_image(self, project_id: str, asset_id: str, version: int | None = None) -> tuple[bytes, str]:
        identity(project_id, pattern=PROJECT_RE)
        with self.database.session() as connection:
            row = connection.execute("SELECT document_json FROM content_projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        asset = find(json.loads(row[0])["assets"], "asset_id", asset_id)
        if version is not None and asset["version"] != version:
            candidate = None
            with self.database.session() as connection:
                for historical in connection.execute("SELECT document_json FROM content_project_revisions WHERE project_id=? ORDER BY revision DESC", (project_id,)):
                    candidate = next((a for a in json.loads(historical[0])["assets"] if a["asset_id"] == asset_id and a["version"] == version), None)
                    if candidate:
                        break
            if candidate is None:
                raise KeyError(asset_id)
            # Historical material that has since been made private stays private.
            if asset["visibility"] != "public":
                raise ContentError("この素材は非公開です。", status=403)
            asset = candidate
        if asset.get("visibility") != "public" or asset.get("privacy_review") != "passed":
            raise ContentError("非公開原本は表示できません。", status=403)
        path = self._path(asset["path"], public=True)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or path.stat().st_size > 20 * 1024 * 1024:
            raise ContentError("プレビューは20MiB以下の画像に対応しています。")
        # Hash the exact bytes returned, not a preceding filesystem read.
        data = path.read_bytes()
        if len(data) != asset["bytes"] or hashlib.sha256(data).hexdigest().upper() != asset["sha256"]:
            raise ContentError("素材が登録時から変わっています。")
        return data, {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]

    def checks(self, p: dict) -> dict:
        blockers, warnings = [], []
        if not p["accepted_proposal"] or (p["proposals"] and p["accepted_proposal"]["proposal_id"] != p["proposals"][-1]["proposal_id"]):
            blockers.append("最新の企画が未採用です")
        if p["proposals"]:
            used = p["proposals"][-1].get("based_on_feedback", [])
            accepted_feedback = (p["accepted_proposal"] or {}).get("feedback_id")
            if any(f.get("kind") == "revision_request" and f["feedback_id"] not in used and f["feedback_id"] != accepted_feedback for f in p["feedback"]):
                blockers.append("修正の相談を企画案へ反映する必要があります")
        used_characters = {cid for e in p["episodes"] for scene in e.get("storyboard", []) for cid in scene.get("character_ids", [])}
        for c in p["characters"]:
            ref = next((a for a in p["assets"] if a["asset_id"] == c["reference_asset_id"]), None)
            if not c.get("approval") or not ref or ref["sha256"] != c["reference_sha256"]:
                (blockers if c["character_id"] in used_characters else warnings).append(f"人物の確認が必要: {c['character_id']}")
        for asset in p["assets"]:
            try:
                self._verify_asset(asset)
            except (ContentError, OSError, ValueError) as exc:
                blockers.append(str(exc))
        for claim in p["claims"]:
            if claim.get("needs_review"):
                blockers.append(f"根拠の再確認: {claim['claim_id']}")
            if claim["basis"] == "hypothesis":
                warnings.append(f"推測・未検証: {claim['claim_id']}")
        for e in p["episodes"]:
            if e["capture_plan"]["status"] == "uninspected":
                blockers.append(f"撮影可否が未確認: {e['episode_id']}")
            if not e.get("storyboard"):
                blockers.append(f"絵コンテが未作成: {e['episode_id']}")
            for scene in e.get("storyboard", []):
                if scene.get("needs_review"):
                    blockers.append(f"場面の再確認: {e['episode_id']}/{scene['scene_id']}")
                if not scene.get("asset_ids"):
                    warnings.append(f"素材の割当待ち: {e['episode_id']}/{scene['scene_id']}")
                for cid in scene.get("character_ids", []):
                    current = find(p["characters"], "character_id", cid)
                    if not any(a["asset_id"] in scene.get("asset_ids", []) and a.get("kind") == "generated_video"
                               and a.get("character_id") == cid and a.get("character_version") == current["version"] for a in p["assets"]):
                        warnings.append(f"現在の人物版のMiniMax動画を準備: {e['episode_id']}/{scene['scene_id']}")
            if any(s.get("character_ids") for s in e.get("storyboard", [])):
                beats = {s.get("beat") for s in e["storyboard"]}
                if not {"problem", "try", "insight", "action"}.issubset(beats):
                    warnings.append(f"人物の課題・試行・気づき・行動を構成で確認: {e['episode_id']}")
            if e.get("storyboard") and abs(sum(s["duration_seconds"] for s in e["storyboard"]) - e["duration_seconds"]) > 1:
                warnings.append(f"想定尺と場面尺の合計を調整: {e['episode_id']}")
        for s in p["article"].get("sections", []):
            if s.get("needs_review"):
                warnings.append(f"記事節の再確認: {s['section_id']}")
        return {"ready_for_production": not blockers and not p["archived"], "blockers": blockers, "warnings": warnings,
                "technical_verified": False, "human_reviewed": False, "published": False}

    def export_blog(self, project_id: str, revision: str) -> Path:
        from .content_projects import export_blog
        project = self.get(project_id)["project"]
        if any(s.get("needs_review") for s in project["article"].get("sections", [])):
            raise ContentError("記事の再確認が必要な節を確認してから書き出してください。")
        assets = []
        used = {aid for section in project["article"].get("sections", []) for aid in section.get("asset_ids", [])}
        for asset in project["assets"]:
            if asset["asset_id"] in used and asset["visibility"] == "public":
                if asset.get("kind") in {"demonstration_capture", "official_capture", "generated_still"}:
                    assets.append(asset)
        try:
            return export_blog({"schema_version": 1, "content_project_id": project_id, "article": project["article"], "assets": assets}, revision, self.workspace)
        except FileExistsError as exc:
            raise ContentError("同じ受け渡し版が既にあります。新しい版を指定してください。", status=409) from exc
        except (ValueError, KeyError, OSError) as exc:
            raise ContentError("記事slug・公開用画像・出典・掲載確認・寸法を確認してください。") from exc

    def export_snapshot(self, project_id: str, *, expected_revision: int, confirm_public_review: bool) -> Path:
        """Local review handoff, never an upload. Explicitly reviewed, redacted data only."""
        result = self.get(project_id)
        p = result["project"]
        if p["revision"] != expected_revision or confirm_public_review is not True:
            raise ContentError("最新版の公開用記録を確認してから書き出してください。", status=409)
        public = deepcopy(p)
        public.pop("legacy_project", None)
        public.pop("legacy_refs", None)
        public.pop("feedback", None)
        public.pop("retired_episodes", None)
        public["assets"] = [a for a in public["assets"] if a["visibility"] == "public"]
        for episode in public["episodes"]:
            episode["capture_plan"] = {k: v for k, v in episode["capture_plan"].items() if k not in {"route", "private_path", "receipt_path"}}
        # No private file refs, signed URLs, or raw user responses in Git-oriented snapshots.
        def clean(value):
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items() if k not in {"user_response", "private_path", "receipt_path"}}
            if isinstance(value, list):
                return [clean(v) for v in value]
            if isinstance(value, str):
                return re.sub(r"(?i)(?:[A-Z]:[\\/][^\s\"<>]+|\S*[/\\]_?private[/\\]\S*|\b_?private[/\\]\S*|https?://\S*[?&](?:X-Amz-[^\s]*|token=[^\s]*))", "[非公開情報を省略]", value)
            return value
        destination = workspace_path(self.workspace, Path("outputs/content-projects") / project_id / "editorial" / f"v{p['revision']:04d}")
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ContentError("この版は書き出し済みです。旧版を保持します。", status=409) from exc
        (destination / "content-project.public.json").write_text(json.dumps(sanitize_for_storage(clean(public)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (destination / "readiness.json").write_text(json.dumps(result["checks"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return destination


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "import", "list", "get", "apply", "export", "export-blog", "brief"])
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--database", default="outputs/studio/studio.sqlite3")
    parser.add_argument("--project-id")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--action", choices=sorted(ACTION_NAMES))
    parser.add_argument("--revision", type=int)
    parser.add_argument("--handoff-version", default="v01")
    parser.add_argument("--confirm-public-review", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    db = StudioDatabase(workspace_path(workspace, args.database), workspace=workspace, recover=False)
    service = ContentWorkspace(workspace, db)
    body = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input else {}
    try:
        if args.command == "list":
            result = service.list()
        elif args.command == "create":
            body.setdefault("operation_id", "op_" + uuid.uuid4().hex)
            result = service.create(body)
        elif args.command == "import":
            result = service.create({"content_project_id": body["content_project_id"], "title": body.get("title") or body.get("article", {}).get("title") or body["content_project_id"], "legacy_project": body, "operation_id": "op_" + uuid.uuid4().hex})
        elif args.command == "apply":
            body.setdefault("operation_id", "op_" + uuid.uuid4().hex)
            result = service.apply(args.project_id, args.action, body)
        elif args.command == "export":
            result = {"destination": str(service.export_snapshot(args.project_id, expected_revision=args.revision, confirm_public_review=args.confirm_public_review))}
        elif args.command == "export-blog":
            result = {"destination": str(service.export_blog(args.project_id, args.handoff_version))}
        else:
            result = service.get(args.project_id, args.revision)
            if args.command == "brief":
                p = result["project"]
                result = {"content_project_id": p["content_project_id"], "revision": p["revision"], "request": p["request"], "research": p["research"], "latest_proposal": p["proposals"][-1] if p["proposals"] else None, "feedback": p["feedback"], "accepted_proposal": p["accepted_proposal"], "capture_inspections": p.get("capture_inspections", []), "legacy_refs": p["legacy_refs"], "library": service.list()["items"], "checks": result["checks"], "instruction": "公式・一次情報を優先して幅広く調査。発表日/確認日/利用条件/不一致を区別し、1本1結論で推奨本数と理由、各回の見出し・概要・尺・実演・ブログの役割を提案。ユーザーの意図を反映し、採用前に量産しない。"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ContentError, KeyError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
