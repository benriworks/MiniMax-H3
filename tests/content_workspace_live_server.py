"""Isolated UI fixture; preserves an actual Docs project copy without adopting it.

All new research, proposals, responses, and demonstration claims are fictional
software test inputs. This is not a product investigation or a user approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import uuid

from PIL import Image

from tools.studio.server import create_server
from tests.test_content_workspace import source, episode, capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--stay-open', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = (args.workspace or repo / 'studio/output/playwright' / ('content-' + uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(repo / 'studio/dist', root / 'ui')
    server = create_server(root, port=0, static_dir='ui', initial_refresh=False)
    service = server.service.content_workspace
    project = service.create({'content_project_id': 'CONTENT_live', 'operation_id': 'op_create', 'title': '検証用：架空メモから文書へ'})['project']

    def apply(action, data):
        nonlocal project
        project = service.apply(project['content_project_id'], action, {'operation_id': 'op_' + uuid.uuid4().hex, 'expected_revision': project['revision'], 'data': data})['project']

    apply('research', {'research_id': 'research_one', 'summary': 'ソフトウェア検証用の架空調査。実際の製品仕様を示すものではありません。', 'checked_at': '2026-10-24', 'sources': [source()], 'unknowns': ['実製品の調査・PCでの新規撮影はこのテストの対象外']})
    apply('proposal', {'proposal_id': 'proposal_one', 'count_reason': '概要と修正方法を別々に理解できるよう2本に分ける検証案です。', 'episodes': [episode('one'), {**episode('two'), 'title': '【Claude】修正の伝え方を試す'}]})
    # A separate complete fixture exercises all five panels without inventing
    # adoption of either the real Docs project or the live proposal above.
    saved = project
    project = service.create({'content_project_id': 'CONTENT_complete', 'operation_id': 'op_complete', 'title': '検証用：撮影・根拠・絵コンテの見本'})['project']
    apply('research', {'research_id': 'research_one', 'summary': '架空の検証資料', 'checked_at': '2026-10-24', 'sources': [source()]})
    apply('proposal', {'proposal_id': 'proposal_one', 'count_reason': '一つの結論を伝える検証案', 'episodes': [episode()]})
    apply('feedback', {'feedback_id': 'feedback_test', 'proposal_id': 'proposal_one', 'text': '自動テストの架空返答です。実ユーザーの採用ではありません。', 'interpretation': '検証環境だけで構成採用の処理を試す'})
    apply('accept', {'proposal_id': 'proposal_one', 'feedback_id': 'feedback_test', 'confirm_acceptance': True})
    Image.new('RGB', (700, 400), '#d7e9e5').save(root / 'screen.png')
    apply('asset', {'asset_id': 'screen', 'kind': 'demonstration_capture', 'path': 'screen.png', 'visibility': 'public', 'privacy_review': 'passed', 'fictional_materials_only': True, 'alt': 'ソフトウェア検証用の合成画像', 'caption': '実製品のキャプチャではありません。'})
    apply('capture', {'episode_id': 'one', **capture('captured'), 'shots': [{'shot_id': 'input', 'purpose': '架空素材を保存する処理のテスト', 'asset_id': 'screen'}]})
    apply('claim', {'claim_id': 'claim_one', 'text': '検証用の合成素材を読み込めること', 'basis': 'hypothesis', 'checked_at': '2026-10-24', 'source_ids': []})
    apply('storyboard', {'episode_id': 'one', 'scenes': [{'scene_id': 'intro', 'purpose': '困りごとを示す', 'narration': '架空メモを一緒に整理する流れです。', 'visual': '検証用画像を大きく表示', 'duration_seconds': 5, 'claim_ids': ['claim_one'], 'asset_ids': ['screen']}]})
    copied = None
    original = repo / 'productions/content-projects/CONTENT_20261023_claude_docs_reuse/content-project.public.json'
    if original.is_file():
        original_digest = hashlib.sha256(original.read_bytes()).hexdigest()
        legacy = json.loads(original.read_text(encoding='utf-8'))
        preserved = []
        for asset in legacy.get('assets', []):
            source_path = (repo / asset['path']).resolve(strict=True)
            if not source_path.is_relative_to(repo) or any(p.lower() in {'private', '_private'} for p in source_path.relative_to(repo).parts):
                raise ValueError('The pilot must contain public derivatives only')
            target = root / asset['path']; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
            preserved.append(hashlib.sha256(source_path.read_bytes()).hexdigest().upper() == asset['sha256'].upper() == hashlib.sha256(target.read_bytes()).hexdigest().upper())
        copied = service.create({'content_project_id': legacy['content_project_id'], 'operation_id': 'op_docs_copy', 'title': '検証用コピー：' + legacy['title'], 'legacy_project': legacy})
        receipt = {'original_unchanged': original_digest == hashlib.sha256(original.read_bytes()).hexdigest() and all(preserved), 'original_manifest_sha256': original_digest, 'copied_assets': len(copied['project']['assets']), 'asset_hashes_match': all(preserved), 'import_issues': copied['project'].get('import_issues', []), 'accepted_proposal': copied['project']['accepted_proposal'], 'article_published': copied['project']['article'].get('published'), 'new_capture_performed': False, 'new_user_approval': False}
        (root / 'docs-copy-verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'workspace': str(root), 'initial_project': saved['content_project_id'], 'docs_copied': copied is not None}), flush=True)
    try:
        if args.stay_open:
            threading.Event().wait()
        else:
            sys.stdin.readline()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown(); server.server_close(); thread.join(5)


if __name__ == '__main__':
    main()
