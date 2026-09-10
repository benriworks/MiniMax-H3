"""Terminal adapter acceptance at a synthetic native boundary, never user pixels."""
import io
import http.client
import json
import tempfile
import threading
import unittest
import uuid
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

from PIL import Image
from tools.studio import claude_capture as capture
from tools.studio.terminal_capture import TerminalStillController, TerminalWindows, terminal_package_binding, FAMILY
from tools.studio.service import StudioService
from tools.studio.server import create_server
from tools.studio.still_library import StillLibraryError, validate_source
from tests.test_studio_claude_capture import FakeSystem, SESSION, OTHER_SESSION, WINDOW


class TerminalStillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.service = StudioService(self.root)
        self.addCleanup(self.service.close)
        self.library = self.service.stills
        self.controller = self.library.terminal_controller
        self.system = FakeSystem()
        self.system.current = replace(WINDOW, process_path='c:\\private\\WindowsTerminal.exe', window_class=TerminalWindows.window_class)
        self.engine = self.root / 'ffmpeg.exe'
        self.engine.write_bytes(b'test engine')
        for name, value in [('_system', self.system), ('_resolve_tools', {'ffmpeg': str(self.engine), 'ffmpeg_sha256': capture._sha(self.engine)})]:
            patch = mock.patch.object(self.controller, name, return_value=value)
            patch.start(); self.addCleanup(patch.stop)

    def body(self, **changes):
        inspected = self.library.inspect_terminal({}, session_binding=SESSION)
        token = inspected['selections'][0]['selection_token']
        return {'id': 'still_' + uuid.uuid4().hex, 'title': 'CLI の回答', 'memo': '記事用', 'parent_id': None,
                'source': {'kind': 'terminal', 'selection_token': token}, 'confirm_capture': True, **changes}

    def fake_process(self, args, **kwargs):
        self.assertIn('gfxcapture=hwnd=', args[args.index('-filter_complex') + 1])
        self.assertNotIn('scale=', args[args.index('-filter_complex') + 1])
        self.assertEqual(args[args.index('-frames:v') + 1], '1')
        Image.new('RGB', (1100, 700), '#142434').save(args[-1])
        return 0, b'', b''

    def complete(self, body):
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=self.fake_process):
            item = self.library.submit(body, session_binding=SESSION)
            job = self.service.jobs.wait(item['job_id'], timeout=10)
        self.assertEqual(job['status'], 'succeeded', job)
        return self.library.get(item['id'])

    def test_package_identity_rejects_wrong_family_path_and_preview(self):
        root = r'C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_1.24.11911.0_x64__8wekyb3d8bbwe'
        args = [root + r'\WindowsTerminal.exe', FAMILY, 'Microsoft.WindowsTerminal_1.24.11911.0_x64__8wekyb3d8bbwe', FAMILY + '!App', root]
        self.assertTrue(terminal_package_binding(*args))
        for index, value in [(0, r'C:\fake\WindowsTerminal.exe'), (0, root + r'\..\WindowsTerminal.exe'), (1, 'Claude_pzs8sxrjxfjjc'), (2, 'Microsoft.WindowsTerminalPreview_1.24.0.0_x64__8wekyb3d8bbwe'), (3, FAMILY + '!Other'), (4, 'relative')]:
            changed = args.copy(); changed[index] = value
            self.assertFalse(terminal_package_binding(*changed))

    def test_inspect_has_no_pixels_titles_or_claimed_cli_identity(self):
        with mock.patch.object(capture.native, '_run_contained_process') as runner:
            result = self.library.inspect_terminal({}, session_binding=SESSION)
        runner.assert_not_called()
        self.assertEqual(result['selections'][0]['label'], 'Windows Terminal 1')
        self.assertFalse(result['actual_capture_performed']); self.assertFalse(result['cli_content_verified'])
        self.assertNotIn('private', json.dumps(result)); self.assertNotIn('hwnd', json.dumps(result))
        with self.assertRaises(StillLibraryError): self.library.inspect_terminal({'command': 'claude'}, session_binding=SESSION)

    def test_source_rejects_commands_handles_and_paths(self):
        source = self.body()['source']
        self.assertEqual(validate_source(source), source)
        for key in ('command', 'hwnd', 'path', 'tab'):
            with self.assertRaises(StillLibraryError): validate_source({**source, key: 'bad'})
        with self.assertRaises(capture.ClaudeCaptureError): validate_source({'kind': 'terminal', 'selection_token': 'bad'})

    def test_tokens_isolated_session_bound_expiring_and_one_use(self):
        body = self.body()
        with self.assertRaises(capture.ClaudeCaptureError): self.library.submit(body, session_binding=OTHER_SESSION)
        with self.assertRaises(capture.ClaudeCaptureError): self.library.submit({**body, 'source': {**body['source'], 'kind': 'claude'}}, session_binding=SESSION)
        item = self.complete(body)
        self.assertEqual(self.library.submit(body, session_binding=SESSION)['job_id'], item['job_id'])
        with self.assertRaises(capture.ClaudeCaptureError): self.library.submit({**body, 'id': 'still_' + uuid.uuid4().hex}, session_binding=SESSION)
        body = self.body()
        with mock.patch.object(capture.time, 'monotonic', return_value=1e20), self.assertRaises(capture.ClaudeCaptureError):
            self.library.submit(body, session_binding=SESSION)

    def test_png_retake_edit_export_and_private_metadata(self):
        body = self.body(); item = self.complete(body)
        self.assertEqual(item['source'], {'kind': 'terminal'})
        original = self.library.image(item['id'])
        report = json.loads((self.root / f"outputs/studio/stills/{item['id']}/capture-report.json").read_text())
        self.assertEqual(report['target'], 'selected_windows_terminal_window')
        self.assertFalse(report['command_execution_performed']); self.assertFalse(report['cli_content_verified'])
        self.assertFalse(report['resized']); self.assertFalse(report['video_capture_performed'])
        retake = self.complete(self.body(parent_id=item['id']))
        self.assertEqual(retake['parent_id'], item['id']); self.assertEqual(self.library.image(item['id']), original)
        edited = self.library.edit(item['id'], {'expected_revision': 1, 'operation_id': 'edit_' + uuid.uuid4().hex, 'title': '記事素材', 'memo': '説明'})
        self.assertEqual(len(edited['history']), 2)
        data = self.library.export(item['id'], {'expected_revision': 2, 'confirm_privacy_review': True})
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            self.assertEqual(bundle.read('image.png'), original)
            self.assertIn('terminal', bundle.read('README.md').decode())
        with self.service.database.session() as connection:
            stored = ' '.join(str(tuple(row)) for table in ('still_images', 'jobs') for row in connection.execute('SELECT * FROM ' + table))
            self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
        self.assertNotIn(body['source']['selection_token'], stored); self.assertNotIn('private', stored)

    def test_target_change_fails_without_publishing(self):
        def changed(args, **kwargs):
            result = self.fake_process(args, **kwargs); self.system.current = None; return result
        body = self.body()
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=changed):
            item = self.library.submit(body, session_binding=SESSION)
            job = self.service.jobs.wait(item['job_id'], timeout=10)
        self.assertEqual(job['status'], 'failed')
        self.assertFalse(self.library.get(item['id'])['ready'])
        self.assertFalse((self.root / f"outputs/studio/stills/{item['id']}/image.png").exists())
        with self.assertRaises(StillLibraryError): self.library.image(item['id'])

    def test_capture_lane_blocks_and_video_is_unsupported(self):
        body = self.body()
        with mock.patch.object(self.service.jobs, 'active_job_ids_for_lane', return_value=['busy']), self.assertRaises(StillLibraryError):
            self.library.submit(body, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError): self.controller.claim({}, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError): self.controller.capture(None)

    def test_live_fixture_report_never_claims_actual_capture(self):
        from tests.terminal_still_live_server import fixture_capture_still
        with mock.patch.object(TerminalStillController, 'capture_still', fixture_capture_still):
            item = self.complete(self.body())
        report = json.loads((self.root / f"outputs/studio/stills/{item['id']}/capture-report.json").read_text())
        self.assertFalse(report['actual_capture_performed'])
        self.assertTrue(report['synthetic_fixture'])
        self.assertEqual(report['engine'], 'synthetic_terminal_fixture')

    def test_inspect_http_requires_authentication_and_empty_body(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(Path(directory), port=0, session_token='s' * 40, initial_refresh=False)
            server.service.stills.terminal_controller = self.controller
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            def request(body, auth):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
                headers = {'Content-Type': 'application/json'}
                if auth: headers['X-Studio-Token'] = 's' * 40
                connection.request('POST', '/api/stills/terminal/inspect', json.dumps(body), headers)
                response = connection.getresponse(); data = response.read(); connection.close()
                return response.status, json.loads(data)
            try:
                self.assertEqual(request({}, False)[0], 403)
                self.assertEqual(request({'command': 'claude'}, True)[0], 422)
                status, result = request({}, True)
                self.assertEqual(status, 200)
                self.assertEqual(result['provider'], 'local_windows_terminal_still')
                self.assertFalse(result['actual_capture_performed'])
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()


if __name__ == '__main__': unittest.main()
