"""Retain the public originals added for the count-only revision."""
from datetime import datetime
import json

import fitz
import requests
from playwright.sync_api import sync_playwright

from capture_sources import OUT, file_info
from rank_volume import POPULATIONS

RAW = OUT/'research/captures-v03'
EXCERPTS = OUT/'article-v03/assets'
DAIICHI_FIRST = 'https://www.dkkaraoke.co.jp/news/newsletter/261008_2.html'
DAIICHI_FINAL = 'https://www.dkkaraoke.co.jp/news/newsletter/261106_1.html'
SAGAWA = 'https://www2.sagawa-exp.co.jp/information/detail/430/'

HTML_TARGETS = (
    ('daiichi-first', DAIICHI_FIRST, 'table', '8,724,000', True),
    ('daiichi-final', DAIICHI_FINAL, 'p', '実際に外部へ送信された情報', False),
    ('sagawa-fifth', SAGAWA, 'p,li,div', '現時点で最大約5,323万件', False),
    ('population-yokohama', 'https://www.city.yokohama.lg.jp/city-info/yokohamashi/tokei-chosa/portal/jinko/maitsuki/saishin-news.html',
     'table', '3,753,462', True),
    ('population-osaka', POPULATIONS['osaka']['url'], 'table', '2,814,191', True),
    ('population-tokyo', POPULATIONS['tokyo']['url'], 'tr', '14,288,867', False),
)


def capture(page, source_id, url, tag, anchor, excerpt):
    info = dict(source_id=source_id,url=url)
    try:
        res = page.goto(url,wait_until='domcontentloaded',timeout=15000)
        info.update(final_url=page.url,http_status=res.status if res else None)
        raw = RAW/f'{source_id}-edge.png'
        box = page.locator(tag).filter(has_text=anchor).last
        try:
            box.wait_for(state='visible',timeout=5500)
            box.scroll_into_view_if_needed(timeout=4000)
            state='target_visible'
        except Exception:
            state='page_only'
        page.screenshot(path=raw,animations='disabled',timeout=7000)
        info.update(state=state,raw=file_info(raw),title=page.title())
        if state=='target_visible' and excerpt:
            target = EXCERPTS/f'{source_id}-v03-excerpt.png'
            box.screenshot(path=target,animations='disabled',timeout=7000)
            info['excerpt']=file_info(target)|{'locator':tag,'matched':anchor}
    except Exception as error:
        info.update(state='capture_failed',reason=str(error).splitlines()[0])
    return info


def main():
    RAW.mkdir(parents=True,exist_ok=True)
    EXCERPTS.mkdir(parents=True,exist_ok=True)
    manifest=RAW/'manifest.json'
    if manifest.exists():
        raise FileExistsError(manifest)
    notes=[]
    with sync_playwright() as engine:
        browser=engine.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1536,'height':1050},device_scale_factor=2.5,locale='ja-JP')
        for item in HTML_TARGETS:
            note=capture(page,*item)
            notes.append(note)
            print(note['source_id'],note['state'],note.get('excerpt',{}).get('width'),flush=True)
        browser.close()
    url=POPULATIONS['japan']['url']
    resp=requests.get(url,timeout=18)
    resp.raise_for_status()
    source=RAW/'population-japan-202610.pdf'
    source.write_bytes(resp.content)
    with fitz.open(source) as document:
        page=document[0]
        assert '12269' in page.get_text().replace(',','')
        full=RAW/'population-japan-pdf-p1.png'
        page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(full)
        # Keep only the dated population headline and the latest national row.
        hit=page.search_for('12269')[0]
        crop=fitz.Rect(35,33,page.rect.width-29,min(page.rect.height,hit.y1+11))
        target=EXCERPTS/'population-japan-v03-excerpt.png'
        scale=1600/crop.width
        page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=crop,alpha=False).save(target)
        notes.append(dict(source_id='population-japan',url=url,state='pdf_raster',raw=file_info(full),
                          excerpt=file_info(target)|{'crop_pdf_points':list(crop)}))
    manifest.write_text(json.dumps(dict(checked_at=datetime.now().astimezone().isoformat(timespec='seconds'),
        entries=notes),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('population-japan','pdf_raster',flush=True)


if __name__=='__main__':
    main()
