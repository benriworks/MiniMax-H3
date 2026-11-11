"""Capture public notices in Edge and prepare bounded citation excerpts."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CASE = Path(__file__).resolve().parent
ROOT = CASE.parents[2]
OUT = ROOT / 'outputs/content-projects' / CASE.name
CAPTURES = OUT / 'research/captures-v01'
EXCERPTS = OUT / 'article-v02/assets'
SOURCES = {
    s['source_id']: s for s in json.loads((CASE / 'sources-v01.json').read_text(encoding='utf-8'))['sources']
}

HTML_TARGETS = [
    ('arara-third', 'https://www.arara.com/news/info/20261106_arara', r'81[,\uff0c]?329[,\uff0c]?467|第3報'),
    ('cuenote-second', None, r'51[,\uff0c]?628[,\uff0c]?280'),
    ('muji-second', None, r'2[,\uff0c]?726'),
    ('muji-card', None, r'34[.\uff0e]5|MUJI\s*Card'),
    ('sagawa-fifth', None, r'5[,\uff0c]?323\s*万|53[,\uff0c]?230[,\uff0c]?000'),
    ('epark-second', None, r'2[,\uff0c]?218\s*万'),
    ('estore-final', None, r'23[,\uff0c]?356[,\uff0c]?000'),
    ('sourcenext-first', None, r'22[,\uff0c]?519[,\uff0c]?960'),
    ('skyticket-first', None, r'1[,\uff0c]?464\s*万'),
    ('skyticket-third', None, r'訂正|複製'),
    ('kddi-cpi-final', None, r'パスワード'),
    ('times-fifth', None, r'外部送信|不正アクセス'),
    ('ncsc-ai-2026', None, r'The impact of AI on cyber threat'),
    ('ipa-response', None, r'信用情報機関.{0,15}本人申告'),
]
HTML_EXCERPTS = {'cuenote-second', 'epark-second', 'ncsc-ai-2026', 'ipa-response', 'sourcenext-first'}
PDF_TARGETS = [
    ('arara-third', '81,329,467'),
    ('muji-second-pdf', '2,726'),
    ('kddi-isp', '12,231,954'),
    ('burger-king', '1,118'),
]

FIND = r'''pattern => {
    const match = new RegExp(pattern, 'iu');
    const choices = Array.from(document.querySelectorAll('h1,h2,h3,h4,p,li,th,td,dt,dd,span,strong'))
        .filter(e => {
            const s = e.innerText?.trim() || '';
            const r = e.getBoundingClientRect();
            return s.length && s.length < 420 && match.test(s) && r.height > 0 && r.width > 8;
        });
    const selected = choices.find(e => e.matches('h1,h2,h3,h4,p,th,td,li'))
        || choices[0];
    if (!selected) return null;
    selected.scrollIntoView({block:'center'});
    const range = document.createRange();
    range.selectNodeContents(selected);
    const rect = range.getBoundingClientRect();
    return {
        x: rect.x, y: rect.y, width: rect.width, height: rect.height,
        tag: selected.tagName, text: selected.innerText.trim().slice(0, 420)
    };
}'''


def file_info(path):
    with Image.open(path) as img:
        width, height = img.size
    return {
        'path': path.relative_to(ROOT).as_posix(),
        'bytes': path.stat().st_size,
        'sha256': sha256(path.read_bytes()).hexdigest(),
        'width': width,
        'height': height,
    }


def capture_html(page, source_id, alternate_url, pattern):
    source = SOURCES[source_id]
    url = alternate_url or source['url']
    report = {'source_id': source_id, 'url': url, 'published_at': source.get('published_at')}
    try:
        response = page.goto(url, wait_until='domcontentloaded', timeout=16000)
        page.locator('body').wait_for(timeout=5000)
        # Wait for document fonts and allow a short bounded wait for a CMS body.
        try:
            page.wait_for_function(
                '(pattern) => new RegExp(pattern, "iu").test(document.body.innerText)',
                arg=pattern, timeout=3800,
            )
        except PlaywrightTimeout:
            pass
        page.evaluate('() => document.fonts.ready')
        report.update({'final_url': page.url, 'title': page.title(), 'status_code': response.status if response else None})
        text = page.locator('body').inner_text(timeout=4000)
        if not response or response.status >= 400 or len(text) < 90:
            return report | {'state': 'response_not_citable'}
        target = page.evaluate(FIND, pattern)
        page.wait_for_timeout(300)
        original = CAPTURES / (source_id + '-edge.png')
        page.screenshot(path=original, timeout=6500, animations='disabled')
        report.update({'state': 'target_visible' if target else 'page_only', 'raw': file_info(original)})
        if target:
            report['target_tag'] = target['tag']
        if target and source_id in HTML_EXCERPTS:
            # Preserve the natural browser rendering. The crop is centered on the selected
            # heading or row and includes only the citation context needed in the article.
            x, y = target['x'], target['y']
            w, h = target['width'], target['height']
            left = max(0, round(x - 18))
            right = min(1536, max(left + 704, round(x + w + 18)))
            left = max(0, min(left, right - 704))
            top = max(0, round(y - 11))
            bottom = min(1050, round(y + h + 12))
            if right - left >= 700 and 20 <= bottom - top <= 142:
                coords = [left * 2, top * 2, right * 2, bottom * 2]
                excerpt = EXCERPTS / (source_id + '-excerpt.png')
                with Image.open(original) as img:
                    img.crop(tuple(coords)).convert('RGB').save(excerpt, optimize=True)
                report['excerpt'] = file_info(excerpt) | {'crop_pixels': coords, 'mode': 'edge_crop'}
        return report
    except Exception as e:
        return report | {'state': 'capture_failed', 'reason': str(e).splitlines()[0]}


def capture_pdf(source_id, needle):
    source = SOURCES[source_id]
    path = ROOT / source['local_original']
    with fitz.open(path) as doc:
        for page in doc:
            hits = page.search_for(needle)
            if not hits:
                continue
            hit = hits[0]
            # Preserve the entire relevant line and a small neighboring area.
            crop = fitz.Rect(page.rect.x0 + 32, max(0, hit.y0 - 13), page.rect.x1 - 30, min(page.rect.y1, hit.y1 + 17))
            if source_id == 'muji-second-pdf':
                # Show the row and the labels to its left, with no press contact details.
                crop.y0 = max(0, hit.y0 - 25)
                crop.y1 = min(page.rect.y1, hit.y1 + 22)
            original = CAPTURES / f'{source_id}-pdf-page-{page.number + 1}.png'
            page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).save(original)
            excerpt = EXCERPTS / f'{source_id}-excerpt.png'
            scale = 1600 / crop.width
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=crop, alpha=False).save(excerpt)
            return {
                'source_id': source_id, 'url': source['url'], 'published_at': source.get('published_at'),
                'state': 'pdf_raster', 'page': page.number + 1, 'raw': file_info(original),
                'excerpt': file_info(excerpt) | {'crop_pdf_points': list(crop), 'mode': 'pdf_crop'},
            }
    return {'source_id': source_id, 'url': source['url'], 'state': 'pdf_target_missing'}


def main():
    CAPTURES.mkdir(parents=True, exist_ok=True)
    EXCERPTS.mkdir(parents=True, exist_ok=True)
    output = CAPTURES / 'capture-manifest.json'
    if output.exists():
        raise FileExistsError(output)
    reports = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1536, 'height': 1050}, device_scale_factor=2, locale='ja-JP')
        page = context.new_page()
        for source_id, url, pattern in HTML_TARGETS:
            report = capture_html(page, source_id, url, pattern)
            reports.append(report)
            print(source_id, report['state'], 'excerpt' in report, flush=True)
        browser.close()
    for source_id, needle in PDF_TARGETS:
        report = capture_pdf(source_id, needle)
        reports.append(report)
        print(source_id, report['state'], 'excerpt' in report, flush=True)
    output.write_text(json.dumps({
        'captured_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'browser': 'Microsoft Edge / isolated Playwright context',
        'public_sources_only': True, 'viewport_css_px': [1536, 1050],
        'device_scale_factor': 2, 'captures': reports,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
