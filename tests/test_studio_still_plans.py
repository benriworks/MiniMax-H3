import copy
import json
import sqlite3
import unittest
import uuid
import io
import zipfile
import http.client
import tempfile
import threading
from pathlib import Path
from unittest import mock

from tests import test_studio_still_library as fixtures
from tools.studio.still_library import StillLibraryError
from tools.studio.service import StudioService
from tools.studio.server import create_server


def ident(prefix):
    return prefix + '_' + uuid.uuid4().hex


class StillPlansTests(fixtures.StillLibraryTests):
    # Reuse the real isolated DB and PNG import setup; inherited library tests
    # also ensure the schema addition doesn't change existing image behavior.
    def plan_body(self):
        return {'operation_id': ident('planedit'), 'expected_revision': 0, 'title': '技術記事', 'steps': [
            {'id': ident('step'), 'title': '全体像', 'memo': '何のアプリか伝える', 'source': {'kind': 'terminal'}, 'image': None},
            {'id': ident('step'), 'title': '操作の結果', 'memo': '', 'source': {'kind': 'claude'}, 'image': None}]}

    def test_plan_save_retry_cas_and_restart(self):
        plans = self.library.plans
        plan_id, body = ident('plan'), self.plan_body()
        item = plans.save(plan_id, body)
        self.assertEqual(item['revision'], 1)
        self.assertEqual(plans.save(plan_id, body)['revision'], 1)
        with self.assertRaises(StillLibraryError): plans.save(plan_id, {**body, 'title': 'different'})
        with self.assertRaises(StillLibraryError): plans.save(plan_id, {**body, 'operation_id': ident('planedit')})
        updated = plans.save(plan_id, {**body, 'operation_id': ident('planedit'), 'expected_revision': 1, 'title': '別の見出し'})
        self.assertEqual(len(updated['history']), 2)
        with self.service.database.session() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
            with self.assertRaises(sqlite3.IntegrityError): connection.execute('DELETE FROM still_plan_versions')
            with self.assertRaises(sqlite3.IntegrityError): connection.execute("UPDATE still_plan_versions SET payload_json='{}'")
        self.service.close(); self.service = StudioService(self.root); self.library = self.service.stills
        self.assertEqual(self.library.plans.get(plan_id)['title'], '別の見出し')
        self.assertEqual(self.library.plans.list()['items'][0]['id'], plan_id)

    def test_reject_executable_or_volatile_source_and_bad_images(self):
        for source in [{'kind': 'claude', 'selection_token': 'x' * 43}, {'kind': 'terminal', 'command': 'claude'}, {'kind': 'web', 'url': 'https://private.example'}]:
            body = self.plan_body(); body['steps'][0]['source'] = source
            with self.assertRaises(StillLibraryError): self.library.plans.save(ident('plan'), body)
        for image in [{'id': {}, 'revision': 1}, {'id': ident('still'), 'revision': True}, {'id': ident('still'), 'revision': 1}]:
            body = self.plan_body(); body['steps'][0]['image'] = image
            with self.assertRaises(StillLibraryError): self.library.plans.save(ident('plan'), body)
        for steps in [[], [self.plan_body()['steps'][0]] * 13]:
            with self.assertRaises(StillLibraryError): self.library.plans.save(ident('plan'), {**self.plan_body(), 'steps': steps})
        body = self.plan_body(); body['steps'][1]['id'] = body['steps'][0]['id']
        with self.assertRaises(StillLibraryError): self.library.plans.save(ident('plan'), body)

    def test_link_only_completed_current_revision_and_preserve_original(self):
        image = self.complete()
        body = self.plan_body(); body['steps'][0]['image'] = {'id': image['id'], 'revision': 1}
        plan_id = ident('plan'); first = self.library.plans.save(plan_id, body)
        self.library.edit(image['id'], {'operation_id': ident('edit'), 'expected_revision': 1, 'title': '更新', 'memo': ''})
        with self.assertRaises(StillLibraryError): self.library.plans.save(plan_id, {**body, 'operation_id': ident('planedit'), 'expected_revision': 1})
        self.assertEqual(self.library.plans.get(plan_id)['revision'], 1)
        detached = copy.deepcopy(body); detached['steps'][0]['image'] = None
        self.library.plans.save(plan_id, {**detached, 'operation_id': ident('planedit'), 'expected_revision': 1})
        self.assertEqual(self.library.image(image['id']), self.original.read_bytes())
        self.assertEqual(first['steps'][0]['image']['revision'], 1)

    def pack(self):
        image = self.complete()
        body = self.plan_body()
        for step in body['steps']: step['image'] = {'id': image['id'], 'revision': image['revision']}
        # Conditions stay local even though user-reviewed text is exported.
        body['steps'][0]['source'] = {'kind': 'web', 'url': 'http://127.0.0.1:4321/private', 'viewport': 'desktop', 'area': 'viewport', 'selector': ''}
        body['steps'][0]['memo'] = '</pre><script>alert(1)</script>'
        plan_id = ident('plan'); self.library.plans.save(plan_id, body)
        preview = self.library.plans.preview(plan_id)
        request = {'expected_revision': 1, 'review_digest': preview['review_digest'], 'confirm_privacy_review': True}
        return plan_id, body, image, preview, request

    def test_pack_order_content_hash_and_repeatability(self):
        plan_id, body, image, preview, request = self.pack()
        self.assertTrue(preview['ready'])
        data = self.library.plans.export(plan_id, request)
        self.assertEqual(data, self.library.plans.export(plan_id, request))
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            self.assertEqual(bundle.namelist(), ['images/01.png', 'images/02.png', 'ARTICLE.md', 'manifest.json', 'README.md'])
            self.assertEqual(bundle.read('images/01.png'), self.original.read_bytes())
            article = bundle.read('ARTICLE.md').decode()
            self.assertLess(article.index('全体像'), article.index('操作の結果'))
            self.assertIn('&lt;script&gt;', article); self.assertNotIn('<script>', article)
            manifest = json.loads(bundle.read('manifest.json'))
            self.assertEqual(manifest['review_digest'], preview['review_digest'])
            self.assertEqual(manifest['images'][0]['media']['sha256'], image['media']['sha256'])
            combined = article + bundle.read('manifest.json').decode()
            for secret in ('127.0.0.1', '/private', 'source_json', 'selection_token', str(self.root)):
                self.assertNotIn(secret, combined)

    def test_pack_refuses_missing_images_stale_review_or_no_consent(self):
        plan_id, body, image, preview, request = self.pack()
        for patch in [{'confirm_privacy_review': False}, {'review_digest': 'a' * 64}, {'expected_revision': 2}, {'extra': 1}]:
            with self.assertRaises(StillLibraryError): self.library.plans.export(plan_id, {**request, **patch})
        missing_id = ident('plan'); self.library.plans.save(missing_id, self.plan_body())
        self.assertFalse(self.library.plans.preview(missing_id)['ready'])
        with self.assertRaises(StillLibraryError): self.library.plans.export(missing_id, request)
        self.library.plans.save(plan_id, {**body, 'operation_id': ident('planedit'), 'expected_revision': 1, 'title': '更新後'})
        with self.assertRaises(StillLibraryError): self.library.plans.export(plan_id, request)

    def test_pack_refuses_changed_image_revision_corruption_and_size(self):
        plan_id, body, image, preview, request = self.pack()
        with mock.patch('tools.studio.still_plans.PACK_MAX_BYTES', 1):
            self.assertFalse(self.library.plans.preview(plan_id)['ready'])
            with self.assertRaises(StillLibraryError): self.library.plans.export(plan_id, request)
        path = self.root / f"outputs/studio/stills/{image['id']}/image.png"
        original = path.read_bytes(); path.write_bytes(b'corrupt')
        with self.assertRaises(StillLibraryError): self.library.plans.export(plan_id, request)
        path.write_bytes(original)
        self.library.edit(image['id'], {'operation_id': ident('edit'), 'expected_revision': 1, 'title': '秘密の新しいメモ', 'memo': 'new private memo'})
        self.assertFalse(self.library.plans.preview(plan_id)['ready'])
        with self.assertRaises(StillLibraryError): self.library.plans.export(plan_id, request)

    def test_plan_http_reads_and_mutations_require_session(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(Path(directory), port=0, session_token='s' * 40, initial_refresh=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            def request(method, path, body=None, auth=False):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
                headers = {'Content-Type': 'application/json'}
                if auth: headers['X-Studio-Token'] = 's' * 40
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse(); data = response.read(); connection.close()
                return response.status, json.loads(data)
            try:
                plan_id = ident('plan'); path = '/api/still-plans/' + plan_id
                for suffix in ('', '/preview'):
                    self.assertEqual(request('GET', path + suffix)[0], 403)
                self.assertEqual(request('GET', '/api/still-plans')[0], 403)
                self.assertEqual(request('POST', path, self.plan_body())[0], 403)
                self.assertEqual(request('POST', path + '/export', {})[0], 403)
                self.assertEqual(request('POST', path, self.plan_body(), True)[0], 200)
                self.assertEqual(request('GET', path, auth=True)[0], 200)
                self.assertFalse(request('GET', path + '/preview', auth=True)[1]['ready'])
                self.assertEqual(request('POST', path + '/export', {}, True)[0], 422)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()


if __name__ == '__main__': unittest.main()
