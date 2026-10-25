"""Prepare article derivatives; never publish or copy private desktop originals."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from PIL import Image
from markdown_it import MarkdownIt
from tools.studio.shorts_creator import record


def build():
    target = OUT / 'blog-handoff/v02'
    if target.exists():
        raise ValueError('Keep previous handoff; create a new version')
    assets = target / 'assets'
    assets.mkdir(parents=True)
    cloud = OUT / 'cloud/v01/dots-desktop-pilot-20261025'
    entries = []
    for name, source, purpose in [
        ('invitation-initial.jpg', cloud / 'screenshots/01_invitation_initial.jpg', '案内文の初回出力'),
        ('invitation-reopened.jpg', cloud / 'screenshots/03_invitation_reopened.jpg', '見出し修正と再表示'),
        ('dorayaki-initial.png', cloud / 'blender/dorayaki_initial.png', 'Blenderの完成レンダー初回版'),
        ('dorayaki-thicker-anko.png', cloud / 'blender/dorayaki_thicker_anko.png', 'あんこ1.30倍の同視点レンダー'),
        ('blender-viewport.jpg', cloud / 'screenshots/21_blender_rotated_gui.jpg', '実際のBlender GUIでの回転後'),
        ('xlsx-opened.jpg', cloud / 'screenshots/11_xlsx_opened.jpg', '実.xlsxを開いた専用ビューア'),
        ('case-confirmation.jpg', cloud / 'screenshots/13_case001_confirmation.jpg', '登録前の確認画面'),
        ('cases-completed.jpg', cloud / 'screenshots/26_cases_complete_full.jpg', '全3件の登録後一覧'),
    ]:
        dest = assets / name
        shutil.copyfile(source, dest)
        with Image.open(dest) as image:
            width, height = image.size
            kind = image.format
        entries.append(dict(asset_id=name.rsplit('.', 1)[0], artifact=record(dest), derived_from=record(source),
            width=width, height=height, format=kind, article_use=purpose,
            private_information_excluded=True, content_modified=False, generated_render='dorayaki-' in name,
            native_resolution_preserved=True, user_approved_for_blog=False))
    source = OUT / 'captures/official/computers-apps-cloud-original.png'
    dest = assets / 'official-control-sentence.png'
    box = (570, 260, 914, 283)
    with Image.open(source) as image:
        image.crop(box).save(dest)
        with Image.open(dest) as crop:
            assert crop.tobytes() == image.crop(box).tobytes()
    entries.append(dict(asset_id='official-control-sentence', artifact=record(dest), derived_from=record(source),
        width=344, height=23, format='PNG', article_use='閲覧と操作を区別する公式の一文だけを引用',
        source_url='https://learn.chatgpt.com/docs/dots/computers-and-apps#use-the-cloud-computer',
        source_checked_at='2026-10-25', crop=list(box), pixel_exact_crop_verified=True,
        publication_rights_review='pending_final_editorial_review', user_approved_for_blog=False))
    article = (HERE / 'article-draft-v03.md').read_text(encoding='utf-8')
    (target / 'article-draft-v03.md').write_text(article, encoding='utf-8')
    body = MarkdownIt('commonmark', {'html': False}).render(article)
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>dotsクラウドPCの記事草稿v03</title><style>
body{margin:0;background:#f3f1eb;color:#20342e;font-family:Meiryo,sans-serif}main{max-width:760px;margin:auto;padding:32px 22px}h1{font-size:32px;line-height:1.5}h2{margin-top:52px;font-size:25px}p,li{font-size:17px;line-height:2}a{color:#21634f}img{display:block;max-width:100%;height:auto;margin:22px auto;background:white}p:has(img){background:#fff;padding:14px;border-radius:12px}a img{cursor:zoom-in}hr{border:0;border-top:1px solid #b9c9bf;margin-top:45px}@media(max-width:500px){main{padding:20px 16px}h1{font-size:26px}p,li{font-size:16px}}
</style><main>''' + body + '</main></html>'
    (target / 'index.html').write_text(page, encoding='utf-8')
    (target / 'asset-manifest.json').write_text(json.dumps(dict(schema_version=1, content_project_id=HERE.name,
        created_at=datetime.now(timezone.utc).isoformat(), article_version=3, assets=entries,
        private_originals_included=False, published=False,
        resolution_note='App native originals are 1165/1180px wide; rendered images are 1400px. No upscale is called a higher resolution original. Inspect detailed tables by opening the original; mobile body text supplies context.'),
        ensure_ascii=False, indent=2), encoding='utf-8')
    package = target / 'dots-desktop-article-v03-review.zip'
    members = [target / 'article-draft-v03.md', target / 'index.html', target / 'asset-manifest.json', *sorted(assets.iterdir())]
    checks = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in members}
    with zipfile.ZipFile(package, 'x', zipfile.ZIP_DEFLATED) as archive:
        for p in members:
            archive.write(p, p.relative_to(target).as_posix())
        archive.writestr('manifest-sha256.json', json.dumps(checks, indent=2))
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in checks.items())
    print(target)


if __name__ == '__main__':
    build()
