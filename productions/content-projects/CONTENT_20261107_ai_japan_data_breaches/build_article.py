"""Package the Japanese companion draft and its attributed excerpts."""
from html import escape
import json
from pathlib import Path
import re
from shutil import copy2
from zipfile import ZipFile, ZIP_DEFLATED

import fitz
from markdown_it import MarkdownIt
from PIL import Image
from playwright.sync_api import sync_playwright

from produce import CASE, ROOT, OUT, hash_file, save
from visuals import Renderer, backdrop, TEAL, MUTED

DRAFT = CASE/'ARTICLE_DRAFT_V02_JA.md'
PACKAGE = OUT/'blog-handoff/v02'
CAPTURES = OUT/'article-v02/assets'
STYLE = """
:root{color-scheme:light;--ink:#132539;--muted:#435569;--line:#d7e3eb;--accent:#076e66}
*{box-sizing:border-box}
body{margin:0;background:#edf3f6;color:var(--ink);font:16px/1.75 'Noto Sans JP','Yu Gothic',sans-serif}
article{max-width:960px;margin:0 auto;padding:40px clamp(18px,4vw,54px) 55px;background:#fff}
header{display:flex;align-items:center;gap:12px;margin:0 0 14px;color:var(--accent);font-size:14px;font-weight:700}
header span{background:#e0f6ef;border-radius:5px;padding:4px 9px}
h1,h2,h3{line-height:1.4;letter-spacing:.012em}
h1{font-size:clamp(27px,4vw,39px);margin:0 0 14px}
h2{font-size:clamp(22px,3.3vw,27px);margin:30px 0 11px;border-top:2px solid var(--line);padding-top:15px}
h3{font-size:19px;margin:22px 0 7px}
p{margin:9px 0 13px}
a{color:#07565e;text-underline-offset:3px;overflow-wrap:anywhere}
strong{color:#084e49}
img{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:10px;background:white}
.figure{margin:16px 0 8px;break-inside:avoid}
.table-wrap{width:100%;overflow-x:auto}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;font-size:14px}
th,td{padding:9px 11px;border:1px solid var(--line);vertical-align:top;text-align:left}
th{background:#e7f3f2;color:#103d42}
tr:nth-child(2n) td{background:#f6f9fb}
.lead-figure{margin:16px 0 22px;break-inside:avoid}
footer{border-top:1px solid var(--line);margin-top:25px;padding-top:12px;color:var(--muted);font-size:13px}
@media(max-width:680px){
 body{font-size:15px}
 table,tbody,tr,td{display:block}
 thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
 tr{border:1px solid var(--line);border-radius:7px;margin:7px 0;padding:7px 9px}
 td{padding:3px 3px;border:0}
 td:first-child{color:#075e57;font-weight:750}
 tr:nth-child(2n) td{background:white}
}
@page{size:A5;margin:11mm 10mm 12mm}
@media print{
 body{background:white;font-size:12.5px;line-height:1.55}
 article{padding:0;max-width:none}
 h1{font-size:25px}h2{font-size:19px}h3{font-size:16px}
 h1,h2,h3{break-after:avoid-page}
 p{orphans:2;widows:2}
 table{font-size:11.5px}
 th,td{padding:5px 6px}
 thead{display:table-header-group;position:static;width:auto;height:auto;overflow:visible;clip-path:none}
 table{display:table}tbody{display:table-row-group}tr{display:table-row;break-inside:avoid}td{display:table-cell}
 img{border-radius:4px}
}
"""


def diagram(path):
    im = backdrop(False, True).copy()
    r = Renderer('full')
    r.tag(im, '【AI】', (42, 29, 122, 62), TEAL, 16)
    r.text(im, '2026年 日本の情報漏えい', (145, 28, 900, 62), 19, MUTED)
    r.text(im, 'まず公式の案内で、対象を確認', (42, 90, 918, 158), 43)
    r.cards(im, [('認証情報','使い回し先も変更\n多要素認証を設定'),
                 ('カード・口座','明細や入出金を確認\n不明なら正規窓口へ'),
                 ('本人確認書類','事業者の案内を読む\n本人申告を相談')], None, top=184)
    r.text(im, '出典  IPAの対処案内・日本クレジット協会', (42, 419, 918, 458), 17, MUTED)
    im.crop((0,0,1920,966)).save(path, optimize=True)


def main():
    PACKAGE.mkdir(parents=True, exist_ok=True)
    assets = PACKAGE/'assets'
    assets.mkdir(exist_ok=True)
    target = PACKAGE/'article-review-v02.pdf'
    if target.exists():
        raise FileExistsError(target)
    source = DRAFT.read_text(encoding='utf-8')
    references = re.findall(r'!\[([^\]]+)\]\((assets/[\w.-]+\.png)\)', source)
    for alt, relative in references:
        copy2(CAPTURES/Path(relative).name, PACKAGE/relative)
    lead = 'assets/article-what-to-check.png'
    diagram(PACKAGE/lead)
    html = MarkdownIt('commonmark').enable('table').render(source)
    html = html.replace('<table>', '<div class="table-wrap"><table>').replace('</table>', '</table></div>')
    html = re.sub(r'<p>(<img .+?>)</p>', r'<figure class="figure">\1</figure>', html)
    html = html.replace('</h1>', '</h1><figure class="lead-figure"><img src="'+lead+
                        '" alt="情報漏えい時に認証情報、カード・口座、本人確認書類を確認するための対処図"></figure>',1)
    title = escape(source.splitlines()[0][2:])
    doc = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{title}</title><style>{STYLE}</style></head><body><article>'
           '<header><span>関連記事のレビュー用草稿</span>2026年11月7日集計</header>'
           f'{html}<footer>公表資料と利用者向けの一般的な対処を掲載。動画・記事とも公開前の候補です。</footer>'
           '</article></body></html>')
    page_path = PACKAGE/'index.html'
    page_path.write_text(doc,encoding='utf-8')
    copy2(DRAFT, PACKAGE/'ARTICLE_DRAFT_V02_JA.md')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1.5)
        page.goto(page_path.as_uri(),wait_until='load')
        page.evaluate('() => document.fonts.ready')
        widths = {}
        for width in (1440, 390, 360):
            page.set_viewport_size({'width':width,'height':1000})
            report = page.evaluate("""() => ({
                viewport: innerWidth,
                document: document.documentElement.scrollWidth,
                images: Array.from(document.images).map(i=>[i.naturalWidth,i.naturalHeight])
            })""")
            assert report['viewport'] == report['document'] and all(w>=1400 and h>0 for w,h in report['images'])
            widths[width] = report
            if width!=390:
                page.screenshot(path=PACKAGE/f'review-{width}px.png', animations='disabled')
        page.set_viewport_size({'width':1080,'height':1000})
        page.pdf(path=target,prefer_css_page_size=True,print_background=True)
        browser.close()
    with fitz.open(target) as pdf:
        count = len(pdf)
        text = ''.join(page.get_text() for page in pdf)
        for term in ('2,726','51,628,280','本人申告','認証'):
            assert term in text
        evidence = PACKAGE/'pdf-review'
        evidence.mkdir(exist_ok=True)
        for i in sorted({0,1,count-1}):
            pdf[i].get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False).save(evidence/f'page-{i+1}.png')
        links = sum(len(page.get_links()) for page in pdf)
        assert links >= 12
    refs = references + [('漏えい項目から必要な対処を選ぶ自作図',lead)]
    manifest = []
    for alt, relative in refs:
        p = PACKAGE/relative
        with Image.open(p) as img:
            width,height = img.size
        manifest.append(dict(path=relative,alt=alt,width=width,height=height,sha256=hash_file(p),
                             bytes=p.stat().st_size,origin='own_diagram' if relative==lead else 'official_excerpt'))
    save(PACKAGE/'asset-manifest.json',manifest)
    save(PACKAGE/'qc.json',dict(pages=count,links=links,widths=widths,sha256=hash_file(target),
                               bytes=target.stat().st_size,draft=True,published=False))
    with ZipFile(PACKAGE/'article-handoff-v02.zip','x',compression=ZIP_DEFLATED) as bundle:
        for path in [PACKAGE/'ARTICLE_DRAFT_V02_JA.md',page_path,PACKAGE/'asset-manifest.json',*(PACKAGE/i['path'] for i in manifest)]:
            bundle.write(path,path.relative_to(PACKAGE))
    print(json.dumps(dict(pages=count,links=links,bytes=target.stat().st_size,assets=len(manifest)),ensure_ascii=False))


if __name__=='__main__':
    main()
