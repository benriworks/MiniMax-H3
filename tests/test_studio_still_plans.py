import copy
import json
import sqlite3
import unittest
import uuid

from tests import test_studio_still_library as fixtures
from tools.studio.still_library import StillLibraryError
from tools.studio.service import StudioService


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


if __name__ == '__main__': unittest.main()
