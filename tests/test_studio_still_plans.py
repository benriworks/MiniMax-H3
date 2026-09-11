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
from contextlib import closing
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

    def guided(self, *, original=False):
        before = self.complete() if original else None
        body = self.plan_body()
        body['steps'][0]['source'] = {'kind': 'artifact', 'artifact_id': self.artifact}
        body['steps'][1]['source'] = dict(body['steps'][0]['source'])
        if before: body['steps'][0]['image'] = {'id': before['id'], 'revision': before['revision']}
        plan = self.library.plans.save(ident('plan'), body)
        request = {'id': ident('still'), 'expected_revision': 1, 'selection_token': None, 'confirm_capture': True}
        image = self.library.plans.capture(plan['id'], plan['steps'][0]['id'], request, session_binding=None)
        job = self.service.jobs.wait(image['job_id'], timeout=10)
        self.assertEqual(job['status'], 'succeeded', job)
        return plan, request, self.library.get(image['id']), before

    def adoption(self, plan, image):
        comparison = self.library.plans.comparison(plan['id'], image['id'])
        return {'operation_id': ident('planedit'), 'expected_revision': plan['revision'], 'review_digest': comparison['review_digest'], 'confirm_adoption': True}

    def test_guided_capture_binding_is_durable_without_auto_adoption(self):
        plan, request, image, before = self.guided(original=True)
        self.assertEqual(image['plan_capture'], {'plan_id': plan['id'], 'plan_revision': 1, 'step_id': plan['steps'][0]['id']})
        self.assertEqual(image['parent_id'], before['id'])
        self.assertEqual(image['title'], plan['steps'][0]['title'])
        self.assertEqual(self.library.plans.get(plan['id']), plan)
        self.assertEqual(self.library.plans.capture(plan['id'], plan['steps'][0]['id'], request, session_binding=None)['job_id'], image['job_id'])
        with self.assertRaises(StillLibraryError): self.library.plans.capture(plan['id'], plan['steps'][1]['id'], request, session_binding=None)
        with self.service.database.session() as connection:
            with self.assertRaises(sqlite3.IntegrityError): connection.execute('DELETE FROM still_plan_captures')
            with self.assertRaises(sqlite3.IntegrityError): connection.execute("UPDATE still_plan_captures SET step_id='wrong'")
        manifest = json.loads((self.root / f"outputs/studio/stills/{image['id']}/manifest.json").read_text())
        self.assertEqual(manifest['plan_capture'], image['plan_capture'])
        self.service.close(); self.service = StudioService(self.root); self.library = self.service.stills
        self.assertEqual(self.library.get(image['id'])['plan_capture'], image['plan_capture'])

    def test_guided_stale_admission_rolls_back_binding_and_never_captures(self):
        plan, request, image, _ = self.guided()
        self.library.plans.save(plan['id'], {key: value for key, value in {**plan, 'operation_id': ident('planedit'), 'expected_revision': 1, 'title': '新版'}.items() if key in ('operation_id', 'expected_revision', 'title', 'steps')})
        with mock.patch.object(self.library, '_capture') as worker:
            with self.assertRaises(StillLibraryError): self.library.plans.capture(plan['id'], plan['steps'][0]['id'], {**request, 'id': ident('still')}, session_binding=None)
        worker.assert_not_called()
        self.assertEqual(self.library.list()['total'], 1)
        with self.service.database.session() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM still_plan_captures').fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0], 0)
        # A retry of the already admitted request still resolves to its one job.
        self.assertEqual(self.library.plans.capture(plan['id'], plan['steps'][0]['id'], request, session_binding=None)['job_id'], image['job_id'])

    def test_guided_rejects_unconfirmed_overrides_and_bad_step(self):
        plan, request, image, _ = self.guided()
        for patch in ({'confirm_capture': False}, {'expected_revision': True}, {'source': {'kind': 'terminal'}}, {'selection_token': 'secret'}):
            with self.assertRaises(StillLibraryError): self.library.plans.capture(plan['id'], plan['steps'][0]['id'], {**request, **patch}, session_binding=None)
        with self.assertRaises(StillLibraryError): self.library.plans.capture(plan['id'], ident('step'), request, session_binding=None)
        with self.assertRaises(StillLibraryError): self.library.plans.comparison(ident('plan'), image['id'])
        unbound = self.complete()
        with self.assertRaises(StillLibraryError): self.library.plans.comparison(plan['id'], unbound['id'])

    def test_compare_pins_old_notes_and_adopt_changes_only_one_step(self):
        plan, request, image, before = self.guided(original=True)
        self.library.edit(before['id'], {'operation_id': ident('edit'), 'expected_revision': 1, 'title': '最新メモ', 'memo': 'not the pinned note'})
        comparison = self.library.plans.comparison(plan['id'], image['id'])
        self.assertEqual(comparison['snapshot']['before']['memo'], before['memo'])
        self.assertTrue(comparison['ready'])
        for secret in ('artifact_id', 'selection_token', str(self.root)):
            self.assertNotIn(secret, json.dumps(comparison))
        body = self.adoption(plan, image)
        adopted = self.library.plans.adopt(plan['id'], image['id'], body)
        self.assertEqual(adopted['revision'], 2)
        self.assertEqual(adopted['steps'][0]['image'], {'id': image['id'], 'revision': 1})
        self.assertEqual(adopted['steps'][1], plan['steps'][1])
        self.assertEqual(self.library.plans.version(plan['id'], 1)['steps'], plan['steps'])
        self.assertEqual(self.library.image(before['id']), self.original.read_bytes())
        self.assertEqual(self.library.plans.adopt(plan['id'], image['id'], body)['revision'], 2)
        with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], image['id'], {**body, 'review_digest': 'a' * 64})
        self.assertTrue(self.library.plans.comparison(plan['id'], image['id'])['adopted'])

    def test_adopt_refuses_stale_plan_changed_notes_corruption_and_missing_consent(self):
        plan, _, image, _ = self.guided()
        self.assertIsNone(self.library.plans.comparison(plan['id'], image['id'])['snapshot']['before'])
        body = self.adoption(plan, image)
        for patch in ({'confirm_adoption': False}, {'expected_revision': True}, {'review_digest': 'a' * 64}, {'extra': 1}):
            with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], image['id'], {**body, **patch})
        path = self.root / f"outputs/studio/stills/{image['id']}/image.png"
        data = path.read_bytes(); path.write_bytes(b'corrupted')
        with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], image['id'], body)
        path.write_bytes(data)
        self.library.edit(image['id'], {'operation_id': ident('edit'), 'expected_revision': 1, 'title': '変わった', 'memo': '変更あり'})
        with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], image['id'], body)
        new_body = self.adoption(plan, image)
        self.library.plans.save(plan['id'], {'operation_id': ident('planedit'), 'expected_revision': 1, 'title': '別の編集', 'steps': plan['steps']})
        with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], image['id'], new_body)
        self.assertEqual(self.library.plans.get(plan['id'])['steps'][0]['image'], None)

    def test_two_concurrent_adoptions_have_only_one_winner(self):
        plan, _, first, _ = self.guided()
        second = self.library.plans.capture(plan['id'], plan['steps'][0]['id'], {'id': ident('still'), 'expected_revision': 1, 'selection_token': None, 'confirm_capture': True}, session_binding=None)
        self.service.jobs.wait(second['job_id'], timeout=10)
        requests = [(item['id'], self.adoption(plan, item)) for item in (first, second)]
        barrier = threading.Barrier(2); outcomes = []
        def run(image_id, body):
            barrier.wait()
            try: outcomes.append(self.library.plans.adopt(plan['id'], image_id, body)['revision'])
            except StillLibraryError: outcomes.append('conflict')
        threads = [threading.Thread(target=run, args=args) for args in requests]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertCountEqual(outcomes, [2, 'conflict'])
        self.assertEqual(len(self.library.plans.get(plan['id'])['history']), 2)

    def test_failed_guided_capture_keeps_binding_but_cannot_be_adopted(self):
        plan, _, _, _ = self.guided()
        with mock.patch.object(self.library, '_capture', side_effect=RuntimeError('fixture failure')):
            item = self.library.plans.capture(plan['id'], plan['steps'][0]['id'], {'id': ident('still'), 'expected_revision': 1, 'selection_token': None, 'confirm_capture': True}, session_binding=None)
            self.assertEqual(self.service.jobs.wait(item['job_id'], timeout=10)['status'], 'failed')
        self.assertEqual(self.library.get(item['id'])['plan_capture']['plan_id'], plan['id'])
        comparison = self.library.plans.comparison(plan['id'], item['id'])
        self.assertFalse(comparison['ready']); self.assertIsNone(comparison['snapshot']['after'])
        with self.assertRaises(StillLibraryError): self.library.plans.adopt(plan['id'], item['id'], self.adoption(plan, item))
        self.assertEqual(self.library.plans.get(plan['id'])['revision'], 1)

    def test_schema12_upgrade_preserves_saved_plans_images_and_notes(self):
        image = self.complete()
        plan = self.library.plans.save(ident('plan'), self.plan_body())
        self.service.close()
        # Simulate the immediately preceding schema only in this test workspace.
        with closing(sqlite3.connect(self.root / 'outputs/studio/studio.sqlite3')) as connection:
            connection.execute('DROP TABLE still_plan_captures')
            connection.execute("UPDATE schema_meta SET value='12' WHERE key='schema_version'")
            connection.commit()
        self.service = StudioService(self.root); self.library = self.service.stills
        self.assertEqual(self.library.plans.get(plan['id']), plan)
        self.assertEqual(self.library.get(image['id'])['history'], image['history'])
        self.assertEqual(self.library.image(image['id']), self.original.read_bytes())
        with self.service.database.session() as connection:
            self.assertEqual(connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], '14')
            self.assertEqual(connection.execute('SELECT count(*) FROM still_plan_captures').fetchone()[0], 0)

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
                self.assertEqual(request('POST', path + '/steps/' + ident('step') + '/capture', {})[0], 403)
                self.assertEqual(request('GET', path + '/captures/' + ident('still'))[0], 403)
                self.assertEqual(request('POST', path + '/captures/' + ident('still') + '/adopt', {})[0], 403)
                self.assertEqual(request('POST', path, self.plan_body(), True)[0], 200)
                self.assertEqual(request('GET', path, auth=True)[0], 200)
                self.assertFalse(request('GET', path + '/preview', auth=True)[1]['ready'])
                self.assertEqual(request('POST', path + '/export', {}, True)[0], 422)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()


if __name__ == '__main__': unittest.main()
