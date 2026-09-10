from __future__ import annotations

import hashlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image
from tools.studio.service import StudioService
from tools.studio.server import create_server
from tools.studio.still_library import StillLibraryError, validate_source


def new_id():
    return 'still_' + uuid.uuid4().hex


class StillLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        production = self.root / 'productions/TEST_stills'
        (production / 'manifests').mkdir(parents=True)
        (production / 'PRODUCTION_RECORD_JA.md').write_text('# Still fixture', encoding='utf-8')
        (production / 'manifests/source-hashes.json').write_text(json.dumps({'production_id': 'TEST_stills', 'status': 'draft'}), encoding='utf-8')
        self.original = production / 'fixture.png'
        Image.new('RGB', (400, 260), '#e6f0ed').save(self.original)
        self.service = StudioService(self.root)
        self.service.indexer.refresh()
        self.library = self.service.stills
        self.artifact = self.library.sources()['items'][0]['id']

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def body(self, **changes):
        return {'id': new_id(), 'title': '記事用スクリーン', 'memo': '用途のメモ', 'source': {'kind': 'artifact', 'artifact_id': self.artifact}, 'parent_id': None, 'confirm_capture': True, **changes}

    def complete(self, body=None):
        item = self.library.submit(body or self.body())
        job = self.service.jobs.wait(item['job_id'], timeout=10)
        self.assertEqual(job['status'], 'succeeded', job)
        return self.library.get(item['id'])

    def test_import_preview_edit_export_no_run(self):
        item = self.complete()
        self.assertTrue(item['ready'])
        self.assertEqual(self.library.image(item['id']), self.original.read_bytes())
        edit = {'operation_id': 'edit_' + uuid.uuid4().hex, 'expected_revision': 1, 'title': '記事の回答', 'memo': '</pre><img src="https://example.com/tracker">'}
        updated = self.library.edit(item['id'], edit)
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(len(updated['history']), 2)
        self.assertEqual(self.library.edit(item['id'], edit)['revision'], 2)
        with self.assertRaises(StillLibraryError):
            self.library.edit(item['id'], {**edit, 'operation_id': 'edit_' + uuid.uuid4().hex})
        with self.assertRaises(StillLibraryError):
            self.library.export(item['id'], {'expected_revision': 1, 'confirm_privacy_review': True})
        with zipfile.ZipFile(io.BytesIO(self.library.export(item['id'], {'expected_revision': 2, 'confirm_privacy_review': True}))) as bundle:
            self.assertEqual(set(bundle.namelist()), {'image.png', 'README.md', 'manifest.json'})
            self.assertEqual(bundle.read('image.png'), self.original.read_bytes())
            notes = bundle.read('README.md').decode()
            self.assertIn('&lt;img', notes)
            self.assertNotIn('<img', notes)
            self.assertNotIn(str(self.root), notes)
        with self.service.database.session() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM runs').fetchone()[0], 0)

    def test_idempotence_conflict_retake_original_preserved(self):
        request = self.body()
        first = self.complete(request)
        replay = self.library.submit(request)
        self.assertEqual(first['job_id'], replay['job_id'])
        with self.assertRaises(StillLibraryError):
            self.library.submit({**request, 'title': 'another'})
        next_item = self.complete(self.body(parent_id=first['id']))
        self.assertEqual(next_item['parent_id'], first['id'])
        self.assertEqual(self.library.image(first['id']), self.library.image(next_item['id']))
        self.assertEqual(self.library.list()['total'], 2)

    def test_hash_change_invalid_png_and_consent(self):
        with self.assertRaises(StillLibraryError):
            self.library.submit(self.body(confirm_capture=False))
        item = self.complete()
        path = self.root / f'outputs/studio/stills/{item["id"]}/image.png'
        path.write_bytes(b'not a PNG')
        with self.assertRaises(StillLibraryError):
            self.library.image(item['id'])
        self.original.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
        with self.assertRaises(StillLibraryError):
            self.library.submit(self.body())

    def test_cancellation_after_media_does_not_publish(self):
        original = self.library._capture
        def cancel_after(image_id, source, cancel):
            result = original(image_id, source, cancel)
            cancel.set()
            return result
        with mock.patch.object(self.library, '_capture', side_effect=cancel_after):
            item = self.library.submit(self.body())
            self.service.jobs.wait(item['job_id'], timeout=10)
        current = self.library.get(item['id'])
        self.assertFalse(current['ready'])
        self.assertIsNone(current['media'])
        with self.assertRaises(StillLibraryError):
            self.library.image(item['id'])

    def test_reopen_keeps_library_and_metadata(self):
        item = self.complete()
        self.service.close()
        self.service = StudioService(self.root)
        self.library = self.service.stills
        self.assertEqual(self.library.get(item['id'])['title'], item['title'])
        self.assertEqual(self.library.image(item['id']), self.original.read_bytes())

    def test_source_validation(self):
        valid = {'kind': 'web', 'url': 'http://127.0.0.1:3000/example', 'viewport': 'desktop', 'area': 'viewport', 'selector': ''}
        self.assertEqual(validate_source(valid), valid)
        for url in ['https://example.com', 'http://localhost:3000', 'http://127.0.0.1:80', 'http://u:p@127.0.0.1:3000', 'http://127.0.0.1:3000/?token=secret', 'http://127.0.0.1:3000/#secret', 'http://127.0.0.1:bad', 'file:///etc/passwd']:
            with self.subTest(url=url), self.assertRaises(StillLibraryError):
                validate_source({**valid, 'url': url})
        with self.assertRaises(StillLibraryError):
            validate_source({**valid, 'path': '../private'})

    def test_source_and_history_are_immutable_in_database(self):
        item = self.complete()
        for statement in ["UPDATE still_images SET source_json='{}'", "UPDATE still_images SET media_json=NULL", "UPDATE still_image_edits SET title='rewrite'", "DELETE FROM still_image_edits"]:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                with self.service.database.transaction() as connection:
                    connection.execute(statement)
        self.assertEqual(self.library.get(item['id'])['history'][0]['title'], item['title'])

    def test_workspace_escape_and_symlinks_are_rejected(self):
        from tools.studio.security import SecurityError
        with self.assertRaises(SecurityError):
            self.library._path('../outside.png', exists=False)
        item = self.complete()
        image_path = self.root / f'outputs/studio/stills/{item["id"]}/image.png'
        # Mock the filesystem's link flag: no developer-mode privilege required.
        original = Path.is_symlink
        with mock.patch.object(Path, 'is_symlink', lambda path: path == image_path or original(path)):
            with self.assertRaises(SecurityError):
                self.library.image(item['id'])


class StillLibraryHTTPTests(unittest.TestCase):
    def test_authenticated_read_and_post_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(Path(directory), port=0, session_token='s' * 40, initial_refresh=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            port = server.server_address[1]
            def request(method, path, body=None, auth=False):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                headers = {'X-Studio-Token': 's' * 40} if auth else {}
                if body is not None: headers['Content-Type'] = 'application/json'
                connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
                response = connection.getresponse(); data = response.read(); connection.close()
                return response.status, data
            try:
                self.assertEqual(request('GET', '/api/stills')[0], 403)
                self.assertEqual(request('GET', '/api/stills', auth=True)[0], 200)
                self.assertEqual(request('POST', '/api/stills', {}, auth=True)[0], 422)
                self.assertEqual(request('POST', '/api/stills', {})[0], 403)
                self.assertEqual(request('GET', '/api/stills/' + new_id() + '/file', auth=True)[0], 404)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()


if __name__ == '__main__':
    unittest.main()
