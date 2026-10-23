"""Shared video/blog assets usable from chat without starting the Studio UI.

This module copies only explicitly reviewed public derivatives. It does not
publish articles, upload files, alter approvals, or export capture proofs.
"""
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import hashlib
import html
import json
import re
import shutil

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
KINDS = {'demonstration_capture', 'official_capture', 'generated_still'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def public_asset(root, item):
    """Resolve, hash and decode a reviewed derivative; never follow private paths."""
    relative = item['path']
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or any(p.lower() in {'private', '_private'} for p in path.parts):
        raise ValueError('Only public relative asset paths may be exported')
    source = (root / path).resolve(strict=True)
    if not source.is_relative_to(root.resolve()) or source.suffix.lower() not in {'.png', '.webp', '.jpg', '.jpeg'}:
        raise ValueError('Asset must be a workspace image')
    if any(part.lower() in {'private', '_private'} for part in source.relative_to(root.resolve()).parts):
        raise ValueError('Resolved asset points to private material')
    if item['kind'] not in KINDS or item.get('privacy_review') != 'passed':
        raise ValueError('Asset needs an explicit kind and public-image review')
    if item['kind'] == 'demonstration_capture' and item.get('fictional_materials_only') is not True:
        raise ValueError('Demonstrations must use fictional materials')
    if item['kind'] == 'official_capture':
        parsed = urlsplit(item.get('source_url', ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Official capture requires an attributed HTTPS source')
        if not item.get('source_checked_at') or item.get('blog_usage_review') != 'passed':
            raise ValueError('Official capture needs a dated blog-use review')
    if digest(source) != item['sha256'].upper() or source.stat().st_size != item['bytes']:
        raise ValueError('Asset bytes differ from the recorded source')
    with Image.open(source) as image:
        if list(image.size) != [item['width'], item['height']]:
            raise ValueError('Recorded image dimensions differ')
        image.verify()
    if not item.get('alt', '').strip() or not item.get('caption', '').strip():
        raise ValueError('Blog assets need alt text and a caption')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', item['asset_id']):
        raise ValueError('Invalid asset ID')
    return source


def validate_project(project, root=ROOT):
    if project.get('schema_version') != 1 or not re.fullmatch(r'CONTENT_[A-Za-z0-9_-]+', project.get('content_project_id', '')):
        raise ValueError('Invalid content project identity')
    slug = project['article']['slug']
    if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('An article slug is required for the handoff')
    ids = [item['asset_id'] for item in project['assets']]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Asset IDs must be nonempty and unique')
    for item in project['assets']:
        public_asset(root, item)
    return {'content_project_id': project['content_project_id'], 'assets_verified': len(ids),
            'article_published': project['article'].get('published', False),
            'open_issues': [i['id'] for i in project.get('issues', []) if i['status'] != 'resolved']}


def export_blog(project, revision, root=ROOT):
    summary = validate_project(project, root)
    if not re.fullmatch(r'v[0-9]{2,4}', revision):
        raise ValueError('Use a version such as v01')
    parent = root / 'outputs/content-projects' / project['content_project_id'] / 'blog-handoff'
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / revision
    if destination.exists():
        raise FileExistsError('Handoff version already exists; use a new revision')
    # Reserve the version before copying. No existing files or blog checkout are modified.
    destination.mkdir()
    assets = destination / 'assets'
    assets.mkdir()
    exported, snippets = [], []
    for item in project['assets']:
        source = public_asset(root, item)
        name = item['asset_id'] + source.suffix.lower()
        target = assets / name
        shutil.copyfile(source, target)
        if digest(target) != item['sha256'].upper():
            raise ValueError('Copied asset hash mismatch')
        clean = {key: item[key] for key in ['asset_id', 'kind', 'path', 'sha256', 'bytes', 'width', 'height', 'alt', 'caption']}
        clean.update(handoff_path=f'assets/{name}', blog_path=f"public/images/articles/{project['article']['slug']}/{name}",
                     user_approved_for_blog=item.get('user_approved_for_blog', False))
        if item.get('source_url'):
            clean.update(source_url=item['source_url'], source_checked_at=item['source_checked_at'])
        exported.append(clean)
        # Quote attribute text safely; the snippets contain no executable expressions.
        attr = lambda value: html.escape(str(value), quote=True).replace('{', '&#123;').replace('}', '&#125;')
        snippets.append(f'<Figure src="/images/articles/{project["article"]["slug"]}/{name}" width="{item["width"]}" height="{item["height"]}" alt="{attr(item["alt"])}" caption="{attr(item["caption"])}" />')
    manifest = {**summary, 'revision': revision, 'assets': exported, 'publication_approval': 'pending',
                'private_originals_and_proofs_exported': False}
    (destination / 'asset-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / 'figures.mdx').write_text('\n\n'.join(snippets) + '\n', encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'export-blog'])
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--revision', default='v01')
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding='utf-8'))
    result = validate_project(project) if args.command == 'validate' else {'handoff': str(export_blog(project, args.revision))}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
