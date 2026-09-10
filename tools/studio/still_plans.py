"""Versioned, non-executable capture checklists. Images remain in StillLibrary."""
import json
import re

from .still_library import StillLibraryError, _digest, _identifier, _json, _now, _text, validate_source

PLAN_ID = re.compile(r"plan_[a-f0-9]{32}\Z")
STEP_ID = re.compile(r"step_[a-f0-9]{32}\Z")
OP_ID = re.compile(r"planedit_[a-f0-9]{32}\Z")


def install_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS still_plan_versions (
        plan_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1),
        operation_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(plan_id,revision))''')
    for action in ('UPDATE', 'DELETE'):
        connection.execute(f'''CREATE TRIGGER IF NOT EXISTS still_plan_versions_no_{action.lower()}
            BEFORE {action} ON still_plan_versions BEGIN
            SELECT RAISE(ABORT, 'capture plans are append-only'); END''')


def _id(value, pattern=PLAN_ID):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise StillLibraryError('撮影手順のIDが不正です。')
    return value


def recipe_source(source):
    if isinstance(source, dict) and source.get('kind') in ('claude', 'terminal'):
        if set(source) != {'kind'}:
            raise StillLibraryError('ウィンドウ選択・許可は手順に保存できません。撮影ごとに選択してください。')
        return dict(source)
    return validate_source(source)


class StillPlans:
    def __init__(self, library):
        self.library, self.database = library, library.database

    def _record(self, row):
        return {'id': row['plan_id'], 'revision': row['revision'], 'created_at': row['created_at'], **json.loads(row['payload_json'])}

    def list(self):
        with self.database.session() as connection:
            rows = connection.execute('''SELECT p.* FROM still_plan_versions p
                WHERE revision=(SELECT MAX(revision) FROM still_plan_versions WHERE plan_id=p.plan_id)
                ORDER BY created_at DESC,plan_id LIMIT 200''').fetchall()
        return {'items': [{'id': r['plan_id'], 'revision': r['revision'], 'title': json.loads(r['payload_json'])['title']} for r in rows]}

    def get(self, plan_id):
        _id(plan_id)
        with self.database.session() as connection:
            rows = connection.execute('SELECT * FROM still_plan_versions WHERE plan_id=? ORDER BY revision DESC', (plan_id,)).fetchall()
        if not rows:
            raise KeyError(plan_id)
        item = self._record(rows[0])
        item['history'] = [{'revision': row['revision'], 'created_at': row['created_at'], 'title': json.loads(row['payload_json'])['title']} for row in rows]
        return item

    def save(self, plan_id, body):
        _id(plan_id)
        if not isinstance(body, dict) or set(body) != {'operation_id', 'expected_revision', 'title', 'steps'}:
            raise StillLibraryError('撮影手順の保存形式が不正です。')
        _id(body['operation_id'], OP_ID)
        if type(body['expected_revision']) is not int or body['expected_revision'] < 0:
            raise StillLibraryError('撮影手順の版を確認してください。')
        if not isinstance(body['steps'], list) or not 1 <= len(body['steps']) <= 12:
            raise StillLibraryError('撮影手順は1〜12場面で作成してください。')
        steps, seen = [], set()
        for step in body['steps']:
            if not isinstance(step, dict) or set(step) != {'id', 'title', 'memo', 'source', 'image'}:
                raise StillLibraryError('場面の形式が不正です。')
            step_id = _id(step['id'], STEP_ID)
            if step_id in seen:
                raise StillLibraryError('同じ場面IDを重複して使用できません。')
            seen.add(step_id)
            image = step['image']
            if image is not None:
                if not isinstance(image, dict) or set(image) != {'id', 'revision'} or type(image['revision']) is not int or image['revision'] < 1:
                    raise StillLibraryError('保存画像の版を指定してください。')
                _identifier(image['id'])
            steps.append({'id': step_id, 'title': _text(step['title'], 120), 'memo': _text(step['memo'], 2000, empty=True),
                          'source': recipe_source(step['source']), 'image': image})
        payload = {'title': _text(body['title'], 120), 'steps': steps}
        digest = _digest({'plan_id': plan_id, **body, **payload})
        with self.database.transaction() as connection:
            previous = connection.execute('SELECT request_digest FROM still_plan_versions WHERE operation_id=?', (body['operation_id'],)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise StillLibraryError('保存IDが別の変更に使われています。', conflict=True)
            else:
                current = connection.execute('SELECT COALESCE(MAX(revision),0) FROM still_plan_versions WHERE plan_id=?', (plan_id,)).fetchone()[0]
                if current != body['expected_revision']:
                    raise StillLibraryError('別の編集があります。保存済み手順を読み直してください。', conflict=True)
                # Validate image revisions under the same write lock as the plan.
                for step in steps:
                    if step['image'] is not None:
                        row = connection.execute('''SELECT s.revision,j.status FROM still_images s JOIN jobs j ON j.id=s.job_id WHERE s.id=? AND s.media_json IS NOT NULL''', (step['image']['id'],)).fetchone()
                        if row is None or row['status'] != 'succeeded' or row['revision'] != step['image']['revision']:
                            raise StillLibraryError('画像が未完成、またはメモ版が変わりました。画像を選び直してください。', conflict=True)
                connection.execute('INSERT INTO still_plan_versions VALUES (?,?,?,?,?,?)', (plan_id, current + 1, body['operation_id'], digest, _json(payload), _now()))
        return self.get(plan_id)
