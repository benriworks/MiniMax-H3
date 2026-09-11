"""Explicit, one-shot Claude MSIX preparation. Never sends messages or terminal keys."""
from __future__ import annotations

import dataclasses
import json
import re
import secrets
import shutil
import time

from .claude_capture import _session, selection_token_digest
from .jobs import JobCancelled
from .still_library import StillLibraryError, _digest, _now
from .still_media import still_path

ACTION_ID = re.compile(r"control_[a-f0-9]{32}\Z")
HEX = re.compile(r"[A-F0-9]{64}\Z")
HELPER = "native/claude-control-helper/bin/Release/net8.0-windows/claude-control-helper.dll"
DIAGNOSTIC_COUNTS = ("inspected_nodes", "documents", "hidden_nodes", "unsupported_editors", "supported_inputs", "supported_tabs")


def public_diagnostics(value, controls):
    """Allowlisted counts only: no tree, window identity, draft, token or provider text."""
    if not isinstance(value, dict) or value.get("engine") != "uia3" or value.get("view") != "raw":
        raise ValueError("invalid diagnostic contract")
    counts = {key: value.get(key) for key in DIAGNOSTIC_COUNTS}
    if any(type(count) is not int or not 0 <= count <= 2500 for count in counts.values()):
        raise ValueError("invalid diagnostic counts")
    if counts["inspected_nodes"] < 1 or any(count > counts["inspected_nodes"] for count in counts.values()):
        raise ValueError("invalid diagnostic bounds")
    if counts["supported_inputs"] != sum(item["kind"] == "input" for item in controls) or counts["supported_tabs"] != sum(item["kind"] == "tab" for item in controls):
        raise ValueError("inconsistent diagnostic counts")
    return {"engine": "uia3", "view": "raw", **counts}


def install_schema(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS claude_control_actions (
        id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, operation TEXT NOT NULL,
        job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id), characters INTEGER NOT NULL,
        created_at TEXT NOT NULL)""")
    for operation in ("UPDATE", "DELETE"):
        connection.execute(f"""CREATE TRIGGER IF NOT EXISTS claude_control_actions_no_{operation.lower()}
            BEFORE {operation} ON claude_control_actions BEGIN
            SELECT RAISE(ABORT, 'Claude control receipts are append-only'); END""")


def identifier(value):
    if not isinstance(value, str) or not ACTION_ID.fullmatch(value):
        raise StillLibraryError("操作IDが不正です。")
    return value


def validate_request(body):
    if not isinstance(body, dict) or set(body) != {"id", "operation", "inspection_token", "target_id", "text", "allow_replace", "confirm_action"}:
        raise StillLibraryError("操作の形式が不正です。")
    identifier(body["id"])
    if body["confirm_action"] is not True or type(body["allow_replace"]) is not bool:
        raise StillLibraryError("操作内容を確認し、今回の1回を許可してください。")
    operation = body["operation"]
    if operation not in ("launch", "tab", "input"):
        raise StillLibraryError("起動・タブ切替・未送信の入力だけに対応しています。")
    if operation == "launch":
        if any(body[key] is not None for key in ("inspection_token", "target_id", "text")) or body["allow_replace"]:
            raise StillLibraryError("起動先や起動引数は指定できません。")
    else:
        selection_token_digest(body["inspection_token"])
        if not isinstance(body["target_id"], str) or not HEX.fullmatch(body["target_id"]):
            raise StillLibraryError("操作対象を確認し直してください。")
        if operation == "input":
            text = body["text"]
            try:
                valid = isinstance(text, str) and 0 < len(text.encode("utf-16-le")) // 2 <= 4000 and not any(
                    (ord(c) < 32 and c != "\n") or 127 <= ord(c) < 160 or c in "\u2028\u2029" for c in text)
            except UnicodeError:
                valid = False
            if not valid:
                raise StillLibraryError("入力は4000文字以内にしてください。改行以外の制御文字は使えません。")
        elif body["text"] is not None or body["allow_replace"]:
            raise StillLibraryError("タブ切替には入力文を指定できません。")
    return dict(body)


class NativeClaudeControl:
    def __init__(self, workspace):
        self.workspace = workspace

    def available(self):
        try:
            return bool(shutil.which("dotnet") and still_path(self.workspace, HELPER).is_file())
        except (ValueError, OSError):
            return False

    def run(self, operation, *, window=None, snapshot=None, target=None, text=None, allow_replace=False, cancel=None):
        from .windows_capture_worker import _run_contained_process
        if not self.available():
            raise StillLibraryError("Claude操作ヘルパーが未準備です。setup-studio.ps1 を実行してください。")
        request = {"operation": operation, "window": dataclasses.asdict(window) if window else None,
                   "fingerprint": snapshot["fingerprint"] if snapshot else None,
                   "target": target, "text": text, "allow_replace": allow_replace}
        # stdin only: never command-line arguments, environment, clipboard or files.
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            code, output, _ = _run_contained_process([shutil.which("dotnet"), str(still_path(self.workspace, HELPER))],
                cwd=self.workspace, timeout=15, label="claude-control", cancel_event=cancel, input_bytes=payload)
            result = json.loads(output)
            if isinstance(result, dict) and (type(result.get("protocol_version")) is not int or result["protocol_version"] != 2):
                raise StillLibraryError("Claude操作ヘルパーの更新が必要です。setup-studio.ps1 で再ビルドし、対象を確認し直してください。自動再実行はしません。")
            if code or result.get("ok") is not True:
                raise ValueError()
            if operation != "inspect":
                if type(result.get("effect_verified")) is not bool:
                    raise ValueError()
                return {"effect_verified": result["effect_verified"], "message_sent": False, "requires_capture_reselection": True}
            if not isinstance(result.get("fingerprint"), str) or not HEX.fullmatch(result["fingerprint"]) or not isinstance(result.get("controls"), list) or len(result["controls"]) > 24:
                raise ValueError()
            controls, ids = [], set()
            for entry in result["controls"]:
                if not isinstance(entry.get("id"), str) or not HEX.fullmatch(entry["id"]) or entry["id"] in ids or entry.get("kind") not in ("tab", "input") or type(entry.get("characters")) is not int or not 0 <= entry["characters"] <= 16000:
                    raise ValueError()
                ids.add(entry["id"])
                label = entry.get("label") if entry["kind"] == "tab" else "入力欄 " + str(len(controls) + 1)
                if entry["kind"] == "tab" and label not in ("Code", "Chat", "Chat / Cowork"):
                    raise ValueError()
                method = entry.get("method")
                if method not in (("value", "legacy_value") if entry["kind"] == "input" else ("selection", "invoke")):
                    raise ValueError()
                # A position hint disambiguates multiple editable controls without leaking UI text.
                position = {key: entry.get(key) for key in ("x", "y", "width", "height")}
                if any(type(v) not in (int, float) or not 0 <= v <= 20000 for v in position.values()):
                    raise ValueError()
                controls.append({"id": entry["id"], "kind": entry["kind"], "label": label, "characters": entry["characters"], "position": position, "method": method})
            return {"fingerprint": result["fingerprint"], "controls": controls, "diagnostics": public_diagnostics(result.get("diagnostics"), controls)}
        except JobCancelled:
            raise
        except StillLibraryError:
            raise
        except Exception:
            raise StillLibraryError("画面が変化したか、操作に対応していません。結果を実画面で確認し、対象を選び直してください。自動再実行はしません。") from None


class ClaudeControl:
    def __init__(self, library, adapter=None):
        self.library, self.database, self.jobs = library, library.database, library.jobs
        self.controller, self._lock = library.claude_controller, library._lock
        self.adapter = adapter or NativeClaudeControl(library.workspace)
        self._inspections = {}

    def list(self):
        with self.database.session() as connection:
            rows = connection.execute("SELECT id FROM claude_control_actions ORDER BY created_at DESC LIMIT 50").fetchall()
        return {"available": self.adapter.available(), "items": [self.get(row["id"]) for row in rows]}

    def get(self, action_id):
        with self.database.session() as connection:
            row = connection.execute("SELECT * FROM claude_control_actions WHERE id=?", (identifier(action_id),)).fetchone()
        if row is None:
            return None
        job = self.database.get_job(row["job_id"])
        result = job.get("result") or {}
        outcome = "processing" if job["status"] in ("queued", "running") else "verified" if job["status"] == "succeeded" and result.get("effect_verified") is True else "review_required"
        return {key: row[key] for key in ("id", "operation", "job_id", "characters", "created_at")} | {"status": job["status"], "outcome": outcome, "message_sent": False}

    def _idle(self):
        if self.jobs.active_job_ids_for_lane("capture") or self.database.find_active_windows_capture_job() or self.database.has_unresolved_claude_capture_cleanup():
            raise StillLibraryError("画面の撮影・操作が処理中か、収録の停止確認が必要です。終了を確認してください。", conflict=True)

    def inspect(self, body, *, session_binding):
        if not isinstance(body, dict) or set(body) != {"selection_token", "confirm_inspect"} or body["confirm_inspect"] is not True:
            raise StillLibraryError("選択したClaudeの操作対象確認を許可してください。")
        session = _session(session_binding)
        with self._lock:
            self._idle()
            window = self.controller.consume_control_selection(body["selection_token"], session_binding=session)
            now = time.monotonic()
            self._inspections = {key: value for key, value in self._inspections.items() if value["expires"] > now and value["session"] != session}
            snapshot = self.adapter.run("inspect", window=window)
            diagnostics = public_diagnostics(snapshot.get("diagnostics"), snapshot["controls"])
            token = secrets.token_urlsafe(32)
            if len(self._inspections) > 128:
                self._inspections.clear()
            self._inspections[selection_token_digest(token)] = {"window": window, "snapshot": snapshot, "expires": time.monotonic() + 60, "session": session}
            return {"inspection_token": token, "expires_in_seconds": 60, "controls": snapshot["controls"],
                    "available": bool(snapshot["controls"]), "reason": None if snapshot["controls"] else "controls_not_exposed",
                    "diagnostics": diagnostics}

    def submit(self, body, *, session_binding):
        request, session = validate_request(body), _session(session_binding)
        digest = _digest({"request": request, "session": session})
        with self._lock:
            with self.database.session() as connection:
                existing = connection.execute("SELECT request_digest FROM claude_control_actions WHERE id=?", (request["id"],)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise StillLibraryError("この操作IDは別の内容で使用済みです。", conflict=True)
                return self.get(request["id"])
            self._idle()
            claim = None
            if request["operation"] != "launch":
                key = selection_token_digest(request["inspection_token"])
                claim = self._inspections.get(key)
                if not claim or claim["session"] != session or claim["expires"] <= time.monotonic():
                    raise StillLibraryError("操作対象を確認し直してください。確認の有効期限は60秒です。", conflict=True)
                target = next((item for item in claim["snapshot"]["controls"] if item["id"] == request["target_id"] and item["kind"] == request["operation"]), None)
                if not target or (target["characters"] and request["operation"] == "input" and not request["allow_replace"]):
                    raise StillLibraryError("操作対象または既存入力の置換許可を確認してください。")
            # One admitted mutation invalidates all older UI observations and capture selections.
            self._inspections.clear()
            self.controller.invalidate_control_selections()

            def checkpoint(job):
                with self.database.transaction() as connection:
                    connection.execute("INSERT INTO claude_control_actions VALUES (?,?,?,?,?,?)", (
                        request["id"], digest, request["operation"], job["id"], len((request["text"] or "").encode("utf-16-le")) // 2, _now()))

            def execute(_job_id, cancel):
                try:
                    cancel.raise_if_cancelled()
                    if claim and claim["expires"] <= time.monotonic():
                        raise StillLibraryError("操作対象の確認が期限切れです。")
                    return self.adapter.run(request["operation"], window=claim["window"] if claim else None,
                        snapshot=claim["snapshot"] if claim else None, target=request["target_id"], text=request["text"],
                        allow_replace=request["allow_replace"], cancel=cancel)
                except JobCancelled:
                    raise
                except Exception:
                    # No exception text from app/provider adapters may reach durable job logs.
                    raise StillLibraryError("操作結果を確認できません。実画面を確認してください。自動再実行はしません。") from None
                finally:
                    self.controller.invalidate_control_selections()

            self.jobs.submit("claude_desktop_control", {"action_id": request["id"], "operation": request["operation"]}, execute, lane="capture", before_enqueue=checkpoint)
            return self.get(request["id"])
