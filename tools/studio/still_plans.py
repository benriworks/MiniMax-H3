"""Versioned, non-executable capture checklists. Images remain in StillLibrary."""
import json
import re
import html
import io
import zipfile

from .still_library import StillLibraryError, _digest, _identifier, _json, _now, _text, validate_source

PLAN_ID = re.compile(r"plan_[a-f0-9]{32}\Z")
STEP_ID = re.compile(r"step_[a-f0-9]{32}\Z")
OP_ID = re.compile(r"planedit_[a-f0-9]{32}\Z")
PACK_MAX_BYTES = 128 * 1024 * 1024


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

    def preview(self, plan_id):
        plan = self.get(plan_id)
        steps, blockers, total = [], [], 0
        for index, step in enumerate(plan['steps'], 1):
            image = None
            if step['image'] is None:
                blockers.append(f'場面{index}に画像を割り当ててください。')
            else:
                try:
                    record = self.library.get(step['image']['id'])
                except KeyError:
                    record = None
                if record is None or not record['ready'] or record['revision'] != step['image']['revision']:
                    blockers.append(f'場面{index}の画像が未完成、またはメモ版が変わりました。画像を読み直して再割り当てしてください。')
                else:
                    image = {key: record[key] for key in ('id', 'revision', 'title', 'memo', 'media')}
                    total += image['media']['bytes']
            # Only this reviewed snapshot enters the distribution bundle. Never
            # export source URLs, selectors, native claims or historical notes.
            steps.append({'id': step['id'], 'order': index, 'title': step['title'], 'memo': step['memo'], 'image': image})
        if total > PACK_MAX_BYTES:
            blockers.append('画像合計が128MiBを超えています。手順を分けてください。')
        snapshot = {'schema_version': 1, 'plan_id': plan_id, 'revision': plan['revision'], 'title': plan['title'], 'steps': steps}
        return {'snapshot': snapshot, 'review_digest': _digest(snapshot), 'ready': not blockers, 'blockers': blockers, 'total_bytes': total}

    def export(self, plan_id, body):
        if not isinstance(body, dict) or set(body) != {'expected_revision', 'review_digest', 'confirm_privacy_review'} or body['confirm_privacy_review'] is not True or type(body['expected_revision']) is not int or not isinstance(body['review_digest'], str) or not re.fullmatch(r'[a-f0-9]{64}', body['review_digest']):
            raise StillLibraryError('素材パックの全画像と説明を確認して、書き出しを許可してください。')
        preview = self.preview(plan_id)
        if not preview['ready']:
            raise StillLibraryError(' '.join(preview['blockers']), conflict=True)
        if preview['snapshot']['revision'] != body['expected_revision'] or preview['review_digest'] != body['review_digest']:
            raise StillLibraryError('確認後に内容が変わりました。素材パックを再確認してください。', conflict=True)
        snapshot = preview['snapshot']
        # User text is escaped in HTML pre blocks, never executable Markdown.
        prose = ['# 記事素材パック', f'<pre>{html.escape(snapshot["title"])}</pre>',
                 'このファイルは素材の並びと説明です。事実確認・権利確認・記事本文の仕上げは別途行ってください。']
        manifest = {'schema_version': 1, 'plan_id': plan_id, 'revision': snapshot['revision'], 'review_digest': preview['review_digest'], 'images': []}
        stream = io.BytesIO(); total = 0
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            def add(name, data):
                # Stable timestamps make repeated exports of the same snapshot
                # byte-identical. No user input is used for archive paths.
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, data)
            for step in snapshot['steps']:
                image = step['image']; path = f'images/{step["order"]:02d}.png'
                data = self.library.image(image['id'])  # full decode + hash check
                total += len(data)
                if total > PACK_MAX_BYTES:
                    raise StillLibraryError('素材パックのサイズ上限を超えました。')
                add(path, data)
                prose.extend([f'## {step["order"]:02d}', f'<pre>{html.escape(step["title"])}</pre>',
                              f'![場面{step["order"]}]({path})', f'<pre>{html.escape(step["memo"])}</pre>',
                              '### 素材の名前・メモ', f'<pre>{html.escape(image["title"])}</pre>', f'<pre>{html.escape(image["memo"])}</pre>'])
                manifest['images'].append({'path': path, 'step_id': step['id'], 'image_id': image['id'], 'image_revision': image['revision'], 'media': image['media']})
            add('ARTICLE.md', ('\n\n'.join(prose) + '\n').encode('utf-8'))
            add('manifest.json', _json(manifest).encode('utf-8'))
            add('README.md', '画像原本を場面順に同梱しています。ARTICLE.mdの説明と画像を公開前に確認してください。元URL・選択token・過去メモ・ローカルパスは自動転記しませんが、画像内や入力した説明に含まれる情報は自動匿名化されません。\n'.encode('utf-8'))
        return stream.getvalue()
