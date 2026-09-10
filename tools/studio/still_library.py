"""Production-independent PNG library; Job success is the publication boundary."""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .security import sensitive_artifact_path
from .still_media import StillLibraryError, read_still_png, still_path

ID = re.compile(r"still_[a-f0-9]{32}\Z")
OP_ID = re.compile(r"edit_[a-f0-9]{32}\Z")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise StillLibraryError("名前・メモの長さを確認してください。")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise StillLibraryError("制御文字は使用できません。")
    return value.strip()


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise StillLibraryError("画像IDが不正です。")
    return value


def validate_source(source):
    if not isinstance(source, dict):
        raise StillLibraryError("撮影元を指定してください。")
    if source.get("kind") in ("claude", "terminal"):
        from .claude_capture import selection_token_digest
        if set(source) != {"kind", "selection_token"}:
            raise StillLibraryError("撮影ウィンドウを再確認して選択してください。")
        selection_token_digest(source["selection_token"])
        return dict(source)
    if source.get("kind") == "artifact":
        if set(source) != {"kind", "artifact_id"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(source.get("artifact_id", ""))):
            raise StillLibraryError("登録済みPNGを選択してください。")
        return dict(source)
    if source.get("kind") != "web" or set(source) != {"kind", "url", "viewport", "area", "selector"}:
        raise StillLibraryError("撮影元の形式が不正です。")
    url = source["url"]
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        valid = (parsed and len(url) <= 1000 and not any(c.isspace() for c in url)
                 and "\\" not in url and "%" not in url
                 and parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                 and parsed.port and 1024 <= parsed.port <= 65535
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise StillLibraryError("URLは http://127.0.0.1:ポート/パス の形式で指定してください。認証情報・クエリは使えません。")
    if source["viewport"] not in ("desktop", "mobile") or source["area"] not in ("viewport", "fullpage", "element"):
        raise StillLibraryError("画面サイズ・撮影範囲を選択してください。")
    selector = _text(source["selector"], 200, empty=source["area"] != "element")
    if source["area"] != "element" and selector:
        raise StillLibraryError("要素撮影以外ではセレクターは指定できません。")
    return {**source, "selector": selector}


class StillLibrary:
    def __init__(self, workspace, database, jobs, *, claude_controller=None, submit_lock=None):
        self.workspace, self.database, self.jobs = workspace, database, jobs
        self._lock = submit_lock if submit_lock is not None else threading.Lock()
        self.claude_controller = claude_controller
        from .terminal_capture import TerminalStillController
        self.terminal_controller = TerminalStillController(workspace)
        from .still_plans import StillPlans
        self.plans = StillPlans(self)

    def inspect_terminal(self, body, *, session_binding):
        if not isinstance(body, dict) or body:
            raise StillLibraryError("対象確認では追加の条件を指定できません。")
        return self.terminal_controller.inspect(session_binding=session_binding)

    def _controller(self, kind):
        return self.terminal_controller if kind == "terminal" else self.claude_controller

    def _path(self, relative, *, exists=True):
        return still_path(self.workspace, relative, exists=exists)

    def _png(self, relative, expected=None):
        return read_still_png(self.workspace, relative, expected)

    def sources(self):
        with self.database.session() as connection:
            rows = connection.execute("SELECT id,name,rel_path FROM artifacts WHERE available=1 AND kind='image' AND media_type='image/png' ORDER BY indexed_at DESC LIMIT 500").fetchall()
        return {"items": [{"id": r["id"], "name": r["name"]} for r in rows if not sensitive_artifact_path(r["rel_path"])]}

    def _record(self, row):
        item = dict(row)
        source = json.loads(item.pop("source_json"))
        # Import hash/path are internal provenance, never a client-supplied path.
        item["source"] = ({"kind": source["kind"]} if source["kind"] in ("claude", "terminal") else
                          {k: v for k, v in source.items() if k not in ("rel_path", "sha256")})
        media = json.loads(item.pop("media_json") or "null")
        item.pop("request_digest", None)
        item["ready"] = item["status"] == "succeeded" and media is not None
        item["media"] = media if item["ready"] else None
        if item["ready"]:
            item["image_url"] = f'/api/stills/{item["id"]}/file'
        return item

    def list(self, *, limit=100, offset=0):
        with self.database.session() as connection:
            rows = connection.execute("SELECT s.*, j.status FROM still_images s JOIN jobs j ON j.id=s.job_id ORDER BY s.created_at DESC, s.id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            total = connection.execute("SELECT count(*) FROM still_images").fetchone()[0]
        return {"items": [self._record(row) for row in rows], "total": total}

    def get(self, image_id):
        _identifier(image_id)
        with self.database.session() as connection:
            row = connection.execute("SELECT s.*,j.status FROM still_images s JOIN jobs j ON j.id=s.job_id WHERE s.id=?", (image_id,)).fetchone()
            if row is None:
                raise KeyError(image_id)
            edits = connection.execute("SELECT revision,title,memo,created_at FROM still_image_edits WHERE image_id=? ORDER BY revision", (image_id,)).fetchall()
        return {**self._record(row), "history": [dict(edit) for edit in edits]}

    def submit(self, body, *, session_binding=None):
        if set(body) != {"id", "title", "memo", "source", "parent_id", "confirm_capture"} or body["confirm_capture"] is not True:
            raise StillLibraryError("機密情報が写らないことを確認して、撮影・取り込みを承認してください。")
        image_id = _identifier(body["id"])
        title, memo = _text(body["title"], 120), _text(body["memo"], 4000, empty=True)
        source = validate_source(body["source"])
        token = None
        if source["kind"] in ("claude", "terminal"):
            from .claude_capture import selection_token_digest, _session
            if self._controller(source["kind"]) is None:
                raise StillLibraryError("ウィンドウ撮影はこの環境では利用できません。")
            token = source["selection_token"]
            source = {"kind": source["kind"], "selection_digest": selection_token_digest(token), "requester_digest": _session(session_binding)}
        parent = body["parent_id"]
        if parent is not None:
            if not self.get(_identifier(parent))["ready"]:
                raise StillLibraryError("撮り直し元が完成していません。")
        digest = _digest({**body, "source": source, "title": title, "memo": memo})
        with self._lock:
            with self.database.session() as connection:
                existing = connection.execute("SELECT request_digest FROM still_images WHERE id=?", (image_id,)).fetchone()
                active = connection.execute("SELECT count(*) FROM still_images s JOIN jobs j ON j.id=s.job_id WHERE j.status IN ('queued','running')").fetchone()[0]
            if existing:
                if existing[0] != digest:
                    raise StillLibraryError("同じIDで異なる撮影は開始できません。", conflict=True)
                return self.get(image_id)
            if active >= 1 or self.jobs.active_job_ids_for_lane("capture") or self.database.find_active_windows_capture_job() is not None:
                raise StillLibraryError("静止画の処理中です。完了または停止を待ってください。", conflict=True)
            if source["kind"] in ("claude", "terminal") and self.database.has_unresolved_claude_capture_cleanup():
                raise StillLibraryError("以前のClaude収録に未解決の後処理があります。Studioを再起動して確認してください。", conflict=True)
            if source["kind"] == "artifact":
                artifact = self.database.get_artifact(source["artifact_id"])
                if not artifact or not artifact["available"] or artifact["kind"] != "image" or artifact["media_type"] != "image/png" or sensitive_artifact_path(artifact["rel_path"]):
                    raise StillLibraryError("利用できる登録済みPNGを選択してください。")
                _, media = self._png(artifact["rel_path"], artifact.get("sha256"))
                source.update(rel_path=artifact["rel_path"], sha256=media["sha256"])

            def checkpoint(job):
                with self.database.transaction() as connection:
                    connection.execute("INSERT INTO still_images (id,request_digest,job_id,title,memo,parent_id,source_json,created_at) VALUES (?,?,?,?,?,?,?,?)", (image_id, digest, job["id"], title, memo, parent, _json(source), _now()))
                    connection.execute("INSERT INTO still_image_edits VALUES (?,?,?,?,?,?,?)", (image_id, 1, "initial_" + image_id, digest, title, memo, _now()))

            controller = self._controller(source["kind"])
            claim = controller.claim_still({"selection_token": token, "confirm_capture": True}, session_binding=session_binding) if token else None
            try:
                callback = (lambda job_id, cancel: self._capture(image_id, source, cancel, claude_claim=claim)) if claim else (lambda job_id, cancel: self._capture(image_id, source, cancel))
                self.jobs.submit(kind="still_image_capture", payload={"still_id": image_id, "source_kind": source["kind"]}, callback=callback, before_enqueue=checkpoint, lane="capture")
            except BaseException:
                if claim is not None:
                    controller.discard_still(claim)
                raise
            return self.get(image_id)

    def _capture(self, image_id, source, cancel, *, claude_claim=None):
        from .windows_capture_worker import _run_contained_process
        relative = f"outputs/studio/stills/{image_id}"
        directory = self._path(relative, exists=False)
        directory.mkdir(parents=True, exist_ok=False)
        cancel.raise_if_cancelled()
        if source["kind"] in ("claude", "terminal"):
            report = self._controller(source["kind"]).capture_still(claude_claim, output=directory / "image.png", cancel_event=cancel)
            (directory / "capture-report.json").write_text(_json(report), encoding="utf-8")
        elif source["kind"] == "artifact":
            data, _ = self._png(source["rel_path"], source["sha256"])
            (directory / "image.png").write_bytes(data)
        else:
            node = shutil.which("node")
            if not node:
                raise StillLibraryError("Node.jsが見つかりません。")
            request = directory / "request.json"
            request.write_text(_json(source), encoding="utf-8")
            code, _, _ = _run_contained_process([node, str(Path(__file__).with_name("playwright_still.mjs")), str(request)], cwd=directory, timeout=45, label="still-capture", cancel_event=cancel)
            if code:
                raise StillLibraryError("撮影できませんでした。ローカルページ・外部リソース・撮影範囲を確認してください。")
        cancel.raise_if_cancelled()
        _, media = self._png(f"{relative}/image.png")
        (directory / "manifest.json").write_text(_json({"schema_version": 1, "id": image_id, "source": source, "media": media}), encoding="utf-8")
        cancel.raise_if_cancelled()
        with self.database.transaction() as connection:
            connection.execute("UPDATE still_images SET media_json=? WHERE id=?", (_json(media), image_id))
        # JobManager checks cancellation once more and commits success. Until then
        # media remains inaccessible through list, preview, edit and export.
        return {"still_id": image_id, "media": media}

    def image(self, image_id):
        item = self.get(image_id)
        if not item["ready"]:
            raise StillLibraryError("完成した画像のみ取り出せます。", conflict=True)
        data, _ = self._png(f"outputs/studio/stills/{image_id}/image.png", item["media"]["sha256"])
        return data

    def edit(self, image_id, body):
        _identifier(image_id)
        if set(body) != {"operation_id", "expected_revision", "title", "memo"} or not isinstance(body["operation_id"], str) or not OP_ID.fullmatch(body["operation_id"]):
            raise StillLibraryError("編集リクエストが不正です。")
        if type(body["expected_revision"]) is not int or body["expected_revision"] < 1:
            raise StillLibraryError("編集版が不正です。")
        title, memo = _text(body["title"], 120), _text(body["memo"], 4000, empty=True)
        digest = _digest({"image_id": image_id, **body})
        with self.database.transaction() as connection:
            previous = connection.execute("SELECT request_digest FROM still_image_edits WHERE operation_id=?", (body["operation_id"],)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise StillLibraryError("編集IDが別の変更に使用されています。", conflict=True)
            else:
                row = connection.execute("SELECT s.revision,j.status,s.media_json FROM still_images s JOIN jobs j ON j.id=s.job_id WHERE s.id=?", (image_id,)).fetchone()
                if row is None:
                    raise KeyError(image_id)
                if row["revision"] != body["expected_revision"] or row["status"] != "succeeded" or not row["media_json"]:
                    raise StillLibraryError("別の編集または状態変更があります。一覧を更新してください。", conflict=True)
                revision = row["revision"] + 1
                connection.execute("UPDATE still_images SET title=?,memo=?,revision=? WHERE id=?", (title, memo, revision, image_id))
                connection.execute("INSERT INTO still_image_edits VALUES (?,?,?,?,?,?,?)", (image_id, revision, body["operation_id"], digest, title, memo, _now()))
        return self.get(image_id)

    def export(self, image_id, body):
        if set(body) != {"expected_revision", "confirm_privacy_review"} or body["confirm_privacy_review"] is not True or type(body["expected_revision"]) is not int:
            raise StillLibraryError("画像とメモに機密情報がないことを確認してください。")
        item = self.get(image_id)
        if item["revision"] != body["expected_revision"]:
            raise StillLibraryError("編集内容が変わりました。再確認してください。", conflict=True)
        data = self.image(image_id)
        # User text lives inside HTML-escaped pre blocks: no injected Markdown links,
        # scripts, remote image URLs, or accidental raw HTML in article handoff.
        notes = f'# Still image\n\n![Capture](image.png)\n\n## Title\n<pre>{html.escape(item["title"])}</pre>\n\n## Notes\n<pre>{html.escape(item["memo"])}</pre>\n\nID: {image_id}\n\nRevision: {item["revision"]}\n\nSHA-256: {item["media"]["sha256"]}\n\nSource kind: {item["source"]["kind"]}\n\nParent: {item["parent_id"] or "none"}\n'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("image.png", data)
            bundle.writestr("README.md", notes.encode("utf-8"))
            # Minimal provenance only. History stays in SQLite; intentionally omit
            # URL, local path and production identifiers from the bundle.
            bundle.writestr("manifest.json", _json({"schema_version": 1, "id": image_id, "revision": item["revision"], "media": item["media"], "parent_id": item["parent_id"]}).encode())
        return stream.getvalue()
