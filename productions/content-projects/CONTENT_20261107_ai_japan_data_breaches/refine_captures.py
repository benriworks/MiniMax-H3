"""Select the exact NCSC heading and Cuenote's scope table from PC captures."""
from datetime import datetime
import json

from PIL import Image
from playwright.sync_api import sync_playwright

from capture_sources import CAPTURES, EXCERPTS, SOURCES, file_info


def main():
    target = CAPTURES / 'selected-excerpts-v02.json'
    if target.exists():
        raise FileExistsError(target)
    ncsc = CAPTURES / 'ncsc-ai-2026-edge.png'
    clip = (1155, 185, 2665, 550)
    out = EXCERPTS / 'ncsc-ai-2026-excerpt.png'
    with Image.open(ncsc) as image:
        image.crop(clip).convert('RGB').save(out, optimize=True)
    selected = [{
        'source_id':'ncsc-ai-2026', 'url':SOURCES['ncsc-ai-2026']['url'],
        'raw':file_info(ncsc), 'excerpt':file_info(out), 'crop_pixels':clip,
        'scope':'章見出しのみ。ページの写真は含めない。',
    }]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1536, 'height': 1050}, device_scale_factor=3, locale='ja-JP')
        source = SOURCES['cuenote-second']['url']
        page.goto(source, wait_until='domcontentloaded', timeout=18000)
        table = page.locator('table').filter(has_text='漏洩の恐れがある件数').first
        table.wait_for(timeout=5000)
        table.scroll_into_view_if_needed()
        full = CAPTURES / 'cuenote-second-scope-edge.png'
        page.screenshot(path=full, animations='disabled')
        excerpt = EXCERPTS / 'cuenote-second-v02-excerpt.png'
        table.screenshot(path=excerpt, animations='disabled')
        selected.append({
            'source_id':'cuenote-second','url':source,'raw':file_info(full),'excerpt':file_info(excerpt),
            'locator':'table containing 漏洩の恐れがある件数',
            'scope':'表の見出し、49システム、延べ件数を合わせて引用。初回の別表切り出しは使用しない。',
        })
        browser.close()
    target.write_text(json.dumps({
        'checked_at':datetime.now().astimezone().isoformat(timespec='seconds'),'items':selected,
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for item in selected:
        print(item['source_id'],item['excerpt']['width'],item['excerpt']['height'])


if __name__ == '__main__':
    main()
