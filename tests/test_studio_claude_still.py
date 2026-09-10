"""Synthetic native boundary tests; no real desktop pixels are acquired here."""
from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest import mock

from PIL import Image
from tools.studio import claude_capture as capture
from tools.studio.service import StudioService
from tools.studio.still_library import StillLibraryError
from tests.test_studio_claude_capture import FakeSystem, SESSION, OTHER_SESSION, WINDOW


class ClaudeStillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.controller = capture.ClaudeCaptureController(self.workspace)
        self.system = FakeSystem()
        self.tools = {}
        for name in ('ffmpeg', 'ffprobe'):
            path = self.workspace / (name + '.exe'); path.write_bytes(b'test engine ' + name.encode())
            self.tools[name] = str(path); self.tools[name + '_sha256'] = capture._sha(path)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.controller, '_system', return_value=self.system).start()
        mock.patch.object(self.controller, '_resolve_tools', return_value=self.tools).start()
        self.image = self.workspace / ('outputs/studio/stills/still_' + uuid.uuid4().hex + '/image.png')
        self.image.parent.mkdir(parents=True)

    def request(self):
        token = self.controller.inspect(session_binding=SESSION)['selections'][0]['selection_token']
        return {'selection_token': token, 'confirm_capture': True}

    def fake_process(self, args, **kwargs):
        self.assertEqual(args[args.index('-frames:v') + 1], '1')
        self.assertIn('-an', args)
        self.assertNotIn('libx264', args)
        self.assertNotIn('scale=', args[args.index('-filter_complex') + 1])
        self.assertEqual(kwargs['timeout'], 20)
        self.assertEqual(Path(kwargs['cwd']), self.workspace / 'outputs/studio/runtime/claude-window-capture')
        Image.new('RGB', (1400, 1000), '#abc8bd').save(args[-1])
        return 0, b'', b''

    def test_single_png_without_video_or_sensitive_identity(self):
        request = self.request()
        claim = self.controller.claim_still(request, session_binding=SESSION)
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=self.fake_process) as runner:
            report = self.controller.capture_still(claim, output=self.image)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(report['media']['width'], 1400)
        self.assertFalse(report['resized'])
        self.assertFalse(report['video_capture_performed'])
        self.assertFalse(report['audio_capture_performed'])
        self.assertEqual([path.name for path in self.image.parent.iterdir()], ['image.png'])
        for value in [request['selection_token'], str(WINDOW.hwnd), 'private', 'process_path']:
            self.assertNotIn(value, json.dumps(report))

    def test_expired_wrong_session_reused_and_forged_claims_fail(self):
        request = self.request()
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim_still(request, session_binding=OTHER_SESSION)
        claim = self.controller.claim_still(request, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim_still(request, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture_still(replace(claim), output=self.image)
        request = self.request()
        with mock.patch.object(capture.time, 'monotonic', return_value=1e20), self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim_still(request, session_binding=SESSION)

    def test_video_contract_not_weakened_or_interchangeable(self):
        request = self.request()
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim({**request, 'duration_ms': 1}, session_binding=SESSION)
        claim = self.controller.claim_still(request, session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture(claim, capture_root=self.image.parent)
        with self.assertRaises(capture.ClaudeCaptureError):
            self.controller.claim_still({**self.request(), 'duration_ms': 15000}, session_binding=SESSION)

    def test_target_changes_remove_private_partial_and_never_fallback(self):
        def changed(args, **kwargs):
            result = self.fake_process(args, **kwargs)
            self.system.current = None
            return result
        claim = self.controller.claim_still(self.request(), session_binding=SESSION)
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=changed) as runner, self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture_still(claim, output=self.image)
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(self.image.exists())
        self.assertFalse(self.controller._active.locked())

    def test_engine_error_changed_tool_and_existing_file_fail_closed(self):
        self.image.write_bytes(b'existing user-owned image')
        claim = self.controller.claim_still(self.request(), session_binding=SESSION)
        with self.assertRaises(capture.ClaudeCaptureError): self.controller.capture_still(claim, output=self.image)
        self.assertEqual(self.image.read_bytes(), b'existing user-owned image')
        self.image.unlink()
        claim = self.controller.claim_still(self.request(), session_binding=SESSION)
        Path(self.tools['ffmpeg']).write_bytes(b'changed tool')
        with mock.patch.object(capture.native, '_run_contained_process') as runner, self.assertRaises(capture.ClaudeCaptureError):
            self.controller.capture_still(claim, output=self.image)
        runner.assert_not_called()

    def test_oversized_or_corrupt_png_not_published(self):
        def corrupt(args, **kwargs):
            Path(args[-1]).write_bytes(b'not PNG'); return 0, b'', b''
        claim = self.controller.claim_still(self.request(), session_binding=SESSION)
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=corrupt), self.assertRaises(StillLibraryError):
            self.controller.capture_still(claim, output=self.image)
        self.assertFalse(self.image.exists())
        self.system.current = replace(WINDOW, width=12000, height=12000)
        with self.assertRaises(capture.ClaudeCaptureError): self.controller.claim_still(self.request(), session_binding=SESSION)

    def test_library_uses_volatile_claim_and_shared_lane_no_run(self):
        service = StudioService(self.workspace)
        self.addCleanup(service.close)
        service.stills.claude_controller = self.controller
        request = self.request()
        body = {'id': 'still_' + uuid.uuid4().hex, 'title': 'Claude PNG', 'memo': '', 'parent_id': None,
                'source': {'kind': 'claude', 'selection_token': request['selection_token']}, 'confirm_capture': True}
        with mock.patch.object(capture.native, '_run_contained_process', side_effect=self.fake_process):
            item = service.stills.submit(body, session_binding=SESSION)
            job = service.jobs.wait(item['job_id'], timeout=10)
        self.assertEqual(job['status'], 'succeeded', job)
        item = service.stills.get(item['id'])
        self.assertTrue(item['ready']); self.assertEqual(item['source'], {'kind': 'claude'})
        self.assertEqual(service.stills.submit(body, session_binding=SESSION)['job_id'], item['job_id'])
        with self.assertRaises(StillLibraryError): service.stills.submit(body, session_binding=OTHER_SESSION)
        with service.database.session() as connection:
            stored = ' '.join(str(tuple(row)) for row in connection.execute('SELECT * FROM still_images'))
            stored += ' '.join(str(tuple(row)) for row in connection.execute('SELECT * FROM jobs'))
            self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
        self.assertNotIn(request['selection_token'], stored)
        self.assertNotIn('private', stored)
        with mock.patch.object(service.jobs, 'active_job_ids_for_lane', return_value=['retiring-job']), self.assertRaises(StillLibraryError):
            service.stills.submit({**body, 'id': 'still_' + uuid.uuid4().hex, 'source': {'kind': 'claude', **{'selection_token': self.request()['selection_token']}}}, session_binding=SESSION)


if __name__ == '__main__': unittest.main()
