"""Real service/DB with a synthetic native boundary; never operates user apps."""
import copy
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

from tools.studio import claude_capture as capture
from tools.studio.claude_control import NativeClaudeControl, HELPER, validate_request, public_diagnostics
from tools.studio.service import StudioService
from tools.studio.server import create_server
from tools.studio.database import SCHEMA_VERSION
from tools.studio.still_library import StillLibraryError
from tests.test_studio_claude_capture import FakeSystem, SESSION, OTHER_SESSION


class FakeControl:
    """Only changes in-memory fixture state; no UIA, COM, subprocess or keyboard."""
    def __init__(self):
        self.calls = []
        self.fail = False
        self.started, self.release = threading.Event(), threading.Event()
        self.release.set()
        position = {"x": 20, "y": 300, "width": 600, "height": 150}
        self.snapshot = {"fingerprint": "F" * 64, "controls": [
            {"id": "A" * 64, "kind": "tab", "label": "Code", "characters": 0, "position": position, "method": "invoke"},
            {"id": "B" * 64, "kind": "input", "label": "入力欄 1", "characters": 0, "position": position, "method": "legacy_value"}],
            "diagnostics": {"engine": "uia3", "view": "raw", "inspected_nodes": 180, "documents": 2,
                "hidden_nodes": 20, "unsupported_editors": 0, "supported_inputs": 1, "supported_tabs": 1}}

    def available(self): return True

    def run(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        if operation == "inspect": return copy.deepcopy(self.snapshot)
        self.started.set()
        while not self.release.wait(.02):
            kwargs["cancel"].raise_if_cancelled()
        if self.fail or (kwargs.get("snapshot") and kwargs["snapshot"]["fingerprint"] != self.snapshot["fingerprint"]):
            raise RuntimeError("PRIVATE provider error " + str(kwargs.get("text")))
        return {"effect_verified": operation != "launch", "message_sent": False, "requires_capture_reselection": True}


def install_fake(service):
    fake, system = FakeControl(), FakeSystem()
    service.claude_control.adapter = fake
    service.stills.claude_controller._system = lambda: system
    service.stills.claude_controller._resolve_tools = lambda: {}
    return fake, system


class ClaudeControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.service = StudioService(self.root); self.addCleanup(self.service.close)
        self.control = self.service.claude_control
        self.fake, self.system = install_fake(self.service)
        self.addCleanup(self.fake.release.set)

    def selection(self):
        return self.service.stills.claude_controller.inspect(session_binding=SESSION)["selections"][0]["selection_token"]

    def inspect(self):
        return self.control.inspect({"selection_token": self.selection(), "confirm_inspect": True}, session_binding=SESSION)

    def request(self, operation="launch", **changes):
        result = {"id": "control_" + uuid.uuid4().hex, "operation": operation, "inspection_token": None,
                  "target_id": None, "text": None, "allow_replace": False, "confirm_action": True}
        if operation != "launch":
            result.update(inspection_token=self.inspect()["inspection_token"], target_id=("B" if operation == "input" else "A") * 64,
                          text="機密テスト文章 PRIVATE" if operation == "input" else None)
        return result | changes

    def complete(self, body):
        receipt = self.control.submit(body, session_binding=SESSION)
        job = self.service.jobs.wait(receipt["job_id"], timeout=5)
        return self.control.get(body["id"]), job

    def test_no_automatic_operation_on_startup_or_list(self):
        self.assertEqual(self.control.list(), {"available": True, "items": []})
        self.assertEqual(self.fake.calls, [])

    def test_launch_is_fixed_and_not_claimed_visually_verified(self):
        body = self.request(); receipt, job = self.complete(body)
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(receipt["outcome"], "review_required")
        self.assertFalse(receipt["message_sent"])
        self.assertEqual(self.fake.calls[0][0], "launch")
        self.assertIsNone(self.fake.calls[0][1]["text"])

    def test_tab_and_input_are_verified_without_send(self):
        for operation in ("tab", "input"):
            body = self.request(operation); receipt, job = self.complete(body)
            self.assertEqual(job["status"], "succeeded", job)
            self.assertEqual(receipt["outcome"], "verified")
            self.assertFalse(receipt["message_sent"])
            self.assertEqual(self.fake.calls[-1][0], operation)
            with self.assertRaises(StillLibraryError): self.control.submit(body | {"id": "control_" + uuid.uuid4().hex}, session_binding=SESSION)

    def test_request_allowlist_rejects_launch_arguments_controls_and_surrogates(self):
        base = self.request()
        for change in ({"command": "claude"}, {"text": "x"}, {"allow_replace": True}, {"confirm_action": 1}, {"operation": "enter"}, {"operation": "shell"}, {"target_id": "A" * 64}, {"id": "../bad"}):
            with self.assertRaises((StillLibraryError, capture.ClaudeCaptureError)): validate_request(base | change)
        base = self.request("input")
        for text in ("", "x" * 4001, "\r", "\t", "\x1b", "\x85", "\u2028", "\ud800", "😀" * 2001):
            with self.assertRaises(StillLibraryError): validate_request(base | {"text": text})
        self.assertEqual(validate_request(base | {"text": "例\n次の行"})["text"], "例\n次の行")

    def test_inspection_requires_permission_session_and_exact_window(self):
        token = self.selection()
        for body in ({"selection_token": token}, {"selection_token": token, "confirm_inspect": False}, {"selection_token": token, "confirm_inspect": True, "hwnd": 123}):
            with self.assertRaises(StillLibraryError): self.control.inspect(body, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError): self.control.inspect({"selection_token": token, "confirm_inspect": True}, session_binding=OTHER_SESSION)
        self.system.current = None
        with self.assertRaises(capture.ClaudeCaptureError): self.control.inspect({"selection_token": token, "confirm_inspect": True}, session_binding=SESSION)
        self.assertEqual(self.fake.calls, [])

    def test_control_token_expiry_and_session_binding(self):
        body = self.request("input")
        with self.assertRaises(StillLibraryError): self.control.submit(body, session_binding=OTHER_SESSION)
        for item in self.control._inspections.values(): item["expires"] = 0
        with self.assertRaises(StillLibraryError): self.control.submit(body, session_binding=SESSION)
        self.assertEqual(len(self.fake.calls), 1)

    def test_unsupported_tree_stops_without_job_or_coordinate_fallback(self):
        self.fake.snapshot["controls"] = []
        self.fake.snapshot["diagnostics"].update(supported_inputs=0, supported_tabs=0)
        inspected = self.inspect()
        self.assertFalse(inspected["available"])
        body = self.request() | {"operation": "tab", "inspection_token": inspected["inspection_token"], "target_id": "A" * 64}
        with self.assertRaises(StillLibraryError): self.control.submit(body, session_binding=SESSION)
        self.assertEqual(self.control.list()["items"], [])

    def test_existing_text_requires_replace_permission(self):
        self.fake.snapshot["controls"][1]["characters"] = 10
        body = self.request("input")
        with self.assertRaises(StillLibraryError): self.control.submit(body, session_binding=SESSION)
        receipt, _ = self.complete(body | {"allow_replace": True})
        self.assertEqual(receipt["outcome"], "verified")

    def test_stale_ui_fails_and_sanitizes_provider_exception(self):
        body = self.request("input")
        self.fake.snapshot["fingerprint"] = "E" * 64
        receipt, job = self.complete(body)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(receipt["outcome"], "review_required")
        self.assertNotIn("PRIVATE", json.dumps(job))

    def test_idempotent_receipt_survives_lost_response_and_conflicting_reuse(self):
        body = self.request("input"); receipt, _ = self.complete(body)
        repeated = self.control.submit(body, session_binding=SESSION)
        self.assertEqual(receipt, repeated)
        self.assertEqual([call[0] for call in self.fake.calls], ["inspect", "input"])
        with self.assertRaises(StillLibraryError): self.control.submit(body | {"text": "another"}, session_binding=SESSION)

    def test_no_plaintext_window_path_or_tokens_in_database(self):
        body = self.request("input"); self.complete(body)
        with self.service.database.session() as connection:
            rows = list(connection.iterdump())
        dump = "\n".join(rows)
        for secret in (body["text"], body["inspection_token"], "c:\\private", "ValueDigest", "PRIVATE"):
            self.assertNotIn(secret, dump)

    def test_mutation_invalidates_previously_issued_capture_selections(self):
        body = self.request("input")
        stale = self.selection()
        self.complete(body)
        with self.assertRaises(capture.ClaudeCaptureError): self.service.stills.claude_controller.claim_still({"selection_token": stale, "confirm_capture": True}, session_binding=SESSION)

    def test_capture_lane_is_exclusive_and_cancel_never_retries(self):
        self.fake.release.clear()
        receipt = self.control.submit(self.request(), session_binding=SESSION)
        self.assertTrue(self.fake.started.wait(3))
        with self.assertRaises(StillLibraryError): self.control.submit(self.request(), session_binding=SESSION)
        with self.assertRaises(StillLibraryError): self.inspect()
        self.service.jobs.cancel_and_wait(receipt["job_id"], timeout=5)
        self.assertEqual(self.control.get(receipt["id"])["outcome"], "review_required")
        self.assertEqual([call[0] for call in self.fake.calls], ["launch"])

    def test_receipts_append_only_and_schema13_upgrades_without_losing_data(self):
        receipt, _ = self.complete(self.request())
        with self.service.database.transaction() as connection:
            with self.assertRaises(sqlite3.IntegrityError): connection.execute("DELETE FROM claude_control_actions")
            with self.assertRaises(sqlite3.IntegrityError): connection.execute("UPDATE claude_control_actions SET characters=999")
            connection.execute("UPDATE schema_meta SET value='13' WHERE key='schema_version'")
        self.service.close()
        replacement = StudioService(self.root); self.addCleanup(replacement.close)
        self.assertEqual(replacement.claude_control.get(receipt["id"]), receipt)
        with replacement.database.session() as connection:
            self.assertEqual(connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], str(SCHEMA_VERSION))

    def test_restart_marks_unfinished_receipt_for_review_without_replay(self):
        body = self.request("input")
        # Simulates an accepted action left running at process exit, without executing it.
        job = self.service.database.create_job("claude_desktop_control", {"action_id": body["id"], "operation": "input"})
        self.service.database.update_job(job["id"], "running")
        with self.service.database.transaction() as connection:
            connection.execute("INSERT INTO claude_control_actions VALUES (?,?,?,?,?,?)", (body["id"], "digest", "input", job["id"], 12, "2026-09-12T00:00:00+00:00"))
        self.service.close()
        replacement = StudioService(self.root); self.addCleanup(replacement.close)
        fake, _ = install_fake(replacement)
        receipt = replacement.claude_control.get(body["id"])
        self.assertEqual(receipt["status"], "interrupted")
        self.assertEqual(receipt["outcome"], "review_required")
        self.assertEqual(fake.calls, [])

    def test_capture_cannot_be_admitted_while_control_runs(self):
        self.fake.release.clear()
        receipt = self.control.submit(self.request(), session_binding=SESSION)
        self.assertTrue(self.fake.started.wait(3))
        token = self.selection()
        with self.assertRaises(StillLibraryError):
            self.service.stills.submit({"id": "still_" + uuid.uuid4().hex, "title": "試験", "memo": "", "parent_id": None,
                "source": {"kind": "claude", "selection_token": token}, "confirm_capture": True}, session_binding=SESSION)
        self.fake.release.set(); self.service.jobs.wait(receipt["job_id"], timeout=5)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object boundary")
    def test_real_contained_stdin_round_trip_without_app_operations(self):
        from tools.studio.windows_capture_worker import _run_contained_process
        payload = '日本語の未送信データ\n'.encode('utf-8')
        code, output, errors = _run_contained_process([sys.executable, '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
            cwd=self.root, timeout=5, label='stdin-self-test', cancel_event=None, input_bytes=payload)
        self.assertEqual((code, output, errors), (0, payload, b''))

    def test_oversized_stdin_rejected_before_process_creation(self):
        from tools.studio.windows_capture_worker import _run_contained_process
        from tools.studio.windows_capture import WindowsCaptureError
        with mock.patch('tools.studio.windows_capture_worker.subprocess.Popen') as popen:
            with self.assertRaises(WindowsCaptureError):
                _run_contained_process(['not-run'], cwd=self.root, timeout=1, label='limit-test', cancel_event=None, input_bytes=b'x' * 32769)
        popen.assert_not_called()

    def test_native_adapter_uses_bounded_stdin_only_and_public_result(self):
        helper = self.root / HELPER; helper.parent.mkdir(parents=True); helper.write_bytes(b'fixture only')
        native = NativeClaudeControl(self.root)
        result = {"ok": True, "protocol_version": 2, "effect_verified": True}
        with mock.patch("tools.studio.claude_control.shutil.which", return_value="dotnet"), mock.patch("tools.studio.windows_capture_worker._run_contained_process", return_value=(0, json.dumps(result).encode(), b"")) as runner:
            answer = native.run("input", window=self.system.current, snapshot=self.fake.snapshot, target="B" * 64, text="秘密の文")
        self.assertFalse(answer["message_sent"])
        self.assertNotIn("秘密", str(runner.call_args.args))
        self.assertEqual(json.loads(runner.call_args.kwargs["input_bytes"])["text"], "秘密の文")
        self.assertEqual(runner.call_args.kwargs["timeout"], 15)

    def test_native_inspect_strips_private_value_hashes_and_runtime_id(self):
        helper = self.root / HELPER; helper.parent.mkdir(parents=True); helper.write_bytes(b'fixture only')
        result = {"ok": True, "protocol_version": 2} | copy.deepcopy(self.fake.snapshot)
        for entry in result["controls"]: entry.update(entry.pop("position"))
        result["controls"][1].update(value_digest="PRIVATE", runtime_id=[12345])
        with mock.patch("tools.studio.claude_control.shutil.which", return_value="dotnet"), mock.patch("tools.studio.windows_capture_worker._run_contained_process", return_value=(0, json.dumps(result).encode(), b"")):
            answer = NativeClaudeControl(self.root).run("inspect", window=self.system.current)
        self.assertNotIn("PRIVATE", json.dumps(answer)); self.assertNotIn("runtime_id", json.dumps(answer))

    def native_inspection_fixture(self):
        helper = self.root / HELPER; helper.parent.mkdir(parents=True, exist_ok=True); helper.write_bytes(b'fixture only')
        result = {"ok": True, "protocol_version": 2} | copy.deepcopy(self.fake.snapshot)
        for entry in result["controls"]: entry.update(entry.pop("position"))
        return result

    def run_native_fixture(self, result, operation="inspect"):
        with mock.patch("tools.studio.claude_control.shutil.which", return_value="dotnet"), mock.patch("tools.studio.windows_capture_worker._run_contained_process", return_value=(0, json.dumps(result).encode(), b"")) as runner:
            try: return NativeClaudeControl(self.root).run(operation, window=self.system.current)
            finally: self.assertEqual(runner.call_count, 1, "No replay or compatibility fallback after dispatch")

    def test_native_protocol_requires_rebuild_not_silent_fallback(self):
        result = self.native_inspection_fixture()
        for version in (None, 1, 2.0, True, "2"):
            for operation in ("inspect", "launch"):
                with self.subTest(version=version, operation=operation), self.assertRaisesRegex(StillLibraryError, "再ビルド"):
                    self.run_native_fixture(result | {"protocol_version": version}, operation)

    def test_native_diagnostics_are_bounded_consistent_and_allowlisted(self):
        result = self.native_inspection_fixture()
        result["diagnostics"].update(window_title="PRIVATE", tree="PRIVATE", input_text="PRIVATE", inspection_token="PRIVATE")
        result["controls"][1]["native_host"] = 12345
        answer = self.run_native_fixture(result)
        self.assertNotIn("PRIVATE", json.dumps(answer)); self.assertNotIn("native_host", json.dumps(answer))
        self.assertEqual(answer["controls"][1]["method"], "legacy_value")
        for changes in ({"engine": "PRIVATE"}, {"view": "control"}, {"inspected_nodes": 0}, {"documents": -1}, {"hidden_nodes": 2501}, {"hidden_nodes": True}, {"documents": 2.5}, {"unsupported_editors": 181}, {"supported_inputs": 0}, {"supported_tabs": 24}):
            with self.subTest(changes=changes), self.assertRaises(StillLibraryError):
                self.run_native_fixture(result | {"diagnostics": result["diagnostics"] | changes})

    def test_native_rejects_unknown_or_wrong_kind_input_methods(self):
        result = self.native_inspection_fixture()
        for kind, methods in ((0, (None, "value", "legacy_value", "click")), (1, (None, "invoke", "selection", "send_keys"))):
            for method in methods:
                bad = copy.deepcopy(result); bad["controls"][kind]["method"] = method
                with self.subTest(kind=kind, method=method), self.assertRaises(StillLibraryError): self.run_native_fixture(bad)

    def test_partial_tree_returns_counts_without_authorizing_input(self):
        self.fake.snapshot["controls"] = self.fake.snapshot["controls"][:1]
        self.fake.snapshot["diagnostics"].update(supported_inputs=0, unsupported_editors=2, tree="PRIVATE")
        inspected = self.inspect()
        self.assertTrue(inspected["available"])
        self.assertEqual(inspected["diagnostics"]["unsupported_editors"], 2)
        self.assertNotIn("PRIVATE", json.dumps(inspected))
        body = self.request() | {"operation": "input", "text": "未送信", "inspection_token": inspected["inspection_token"], "target_id": "B" * 64}
        with self.assertRaises(StillLibraryError): self.control.submit(body, session_binding=SESSION)
        self.assertEqual(self.control.list()["items"], [])

    def test_diagnostic_contract_rejects_missing_counts(self):
        for value in (None, [], {}, {"engine": "uia3", "view": "raw"}):
            with self.subTest(value=value), self.assertRaises(ValueError): public_diagnostics(value, [])

    def test_http_auth_origin_and_receipt_recovery(self):
        other = self.root / "http"; other.mkdir()
        server = create_server(other, port=0, session_token="control-tests-" + "x" * 32)
        self.addCleanup(server.server_close)
        fake, _ = install_fake(server.service)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address); self.addCleanup(connection.close)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        def call(method, path, body=None, auth=True, origin=base):
            headers = {"Content-Type": "application/json", "Origin": origin}
            if auth: headers["X-Studio-Token"] = server.session_token
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse(); data = json.loads(response.read()); return response.status, data
        self.assertEqual(call("GET", "/api/claude-control", auth=False)[0], 403)
        body = self.request()
        self.assertEqual(call("POST", "/api/claude-control/actions", body, auth=False)[0], 403)
        self.assertEqual(call("POST", "/api/claude-control/actions", body, origin="http://evil.invalid")[0], 403)
        status, receipt = call("POST", "/api/claude-control/actions", body)
        self.assertEqual(status, 202, receipt)
        server.service.jobs.wait(receipt["job_id"], timeout=5)
        self.assertEqual(call("GET", "/api/claude-control/" + body["id"])[1]["outcome"], "review_required")
        self.assertEqual(call("GET", "/api/claude-control/control_" + "0" * 32)[0], 404)
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__": unittest.main()
