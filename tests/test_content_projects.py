import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from tools.studio.content_projects import export_blog, validate_project


class ContentProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = self.root / 'public-image.png'
        Image.new('RGB', (80, 40), 'white').save(image)
        asset = {'asset_id': 'before', 'kind': 'demonstration_capture', 'path': image.name,
                 'bytes': image.stat().st_size, 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                 'width': 80, 'height': 40, 'privacy_review': 'passed', 'fictional_materials_only': True,
                 'alt': 'Input memo', 'caption': 'Fictional demonstration', 'user_approved_for_blog': False}
        self.project = {'schema_version': 1, 'content_project_id': 'CONTENT_test',
                        'article': {'slug': 'memo-docs', 'published': False}, 'assets': [asset],
                        'issues': [{'id': 'mobile', 'status': 'open'}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_selected_copy_keeps_approval_pending_and_excludes_private_files(self):
        (self.root / '_private').mkdir()
        (self.root / '_private/account.txt').write_text('not for export')
        out = export_blog(self.project, 'v01', self.root)
        manifest = json.loads((out / 'asset-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((out / 'assets/before.png').read_bytes(), (self.root / 'public-image.png').read_bytes())
        self.assertFalse(manifest['assets'][0]['user_approved_for_blog'])
        self.assertEqual(manifest['publication_approval'], 'pending')
        self.assertFalse(list(out.rglob('account.txt')))
        self.assertIn('/images/articles/memo-docs/before.png', (out / 'figures.mdx').read_text())
        self.assertEqual(manifest['open_issues'], ['mobile'])

    def test_changed_source_rejected_before_handoff(self):
        (self.root / 'public-image.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            export_blog(self.project, 'v01', self.root)
        self.assertFalse((self.root / 'outputs').exists())

    def test_private_or_escaping_paths_rejected(self):
        for path in ['_private/secret.png', 'private/secret.png', '../secret.png']:
            with self.subTest(path=path):
                self.project['assets'][0]['path'] = path
                with self.assertRaises(ValueError):
                    validate_project(self.project, self.root)

    def test_unreviewed_and_nonfictional_images_rejected(self):
        self.project['assets'][0]['privacy_review'] = 'pending'
        with self.assertRaises(ValueError):
            validate_project(self.project, self.root)
        self.project['assets'][0].update(privacy_review='passed', fictional_materials_only=False)
        with self.assertRaises(ValueError):
            validate_project(self.project, self.root)

    def test_official_image_requires_source_and_dated_usage_review(self):
        self.project['assets'][0].update(kind='official_capture', source_url='https://support.claude.com/en/articles/example')
        with self.assertRaises(ValueError):
            validate_project(self.project, self.root)
        self.project['assets'][0].update(source_checked_at='2026-10-23', blog_usage_review='passed')
        self.assertEqual(validate_project(self.project, self.root)['assets_verified'], 1)

    def test_previous_handoff_is_preserved(self):
        out = export_blog(self.project, 'v01', self.root)
        prior = (out / 'asset-manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            export_blog(self.project, 'v01', self.root)
        self.assertEqual((out / 'asset-manifest.json').read_bytes(), prior)

    def test_duplicate_ids_and_invalid_slug_rejected(self):
        self.project['assets'].append(copy.deepcopy(self.project['assets'][0]))
        with self.assertRaises(ValueError):
            validate_project(self.project, self.root)
        self.project['assets'].pop()
        self.project['article']['slug'] = '../article'
        with self.assertRaises(ValueError):
            validate_project(self.project, self.root)


if __name__ == '__main__':
    unittest.main()
