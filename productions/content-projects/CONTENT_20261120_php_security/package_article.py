"""Package the illustrated article and validate its mobile and desktop review pages."""
import hashlib
from html import escape
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile
from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

from capture import HERE,OUT,sha,write
from record_project import SLUG

FIGURE=re.compile(r"<!-- figure:([a-z]+) -->")
def main():
    handoff=OUT/"blog-handoff/v01"
    info=json.loads((handoff/"asset-manifest.json").read_text(encoding="utf-8"))
    assets={item["asset_id"]:item for item in info["assets"]}
    draft=(HERE/"article-draft-v01.md").read_text(encoding="utf-8")
    if set(FIGURE.findall(draft))!=set(assets):raise ValueError("Draft and official screenshots disagree")
    files={"sources.md":(HERE/"SOURCES_JA.md").read_bytes(),"asset-manifest.json":(handoff/"asset-manifest.json").read_bytes()}
    for item in assets.values():
        path=handoff/item["handoff_path"]
        if sha(path)!=item["sha256"].lower():raise ValueError(path)
        files[item["handoff_path"]]=path.read_bytes()
    def snippet(key,mode):
        a=assets[key]; src=a["handoff_path"]; alt=escape(a["alt"],quote=True); caption=escape(a["caption"],quote=True)
        url=escape(a["source_url"],quote=True)
        if mode=="html":
            return (f'<figure><a href="{src}"><img loading="eager" src="{src}" width="{a["width"]}" height="{a["height"]}" alt="{alt}"></a>'
                    f'<figcaption>{caption} <a href="{url}">公式原文</a></figcaption></figure>')
        if mode=="mdx":
            return f'<Figure src="/images/articles/{SLUG}/{Path(src).name}" width="{a["width"]}" height="{a["height"]}" alt="{alt}" caption="{caption}" sourceUrl="{url}" />'
        return f'![{a["alt"]}]({src})'
    content=MarkdownIt("commonmark",{"html":True}).enable("table").render(FIGURE.sub(lambda m:snippet(m[1],"html"),draft))
    content=content.replace("<table>","<div class=tablewrap><table>").replace("</table>","</table></div>")
    css="""*{box-sizing:border-box}body{margin:0;background:#f2f6f5;color:#162d3d;font:17px/1.85 'Yu Gothic','Meiryo',sans-serif}
main{max-width:820px;margin:auto;padding:42px clamp(16px,4vw,34px) 85px}h1{font-size:clamp(1.9rem,4vw,2.6rem);line-height:1.4}
h2{font-size:1.44rem;line-height:1.5;border-top:2px solid #aed1c7;padding-top:18px;margin-top:42px}
a{color:#08695e;overflow-wrap:anywhere}figure{margin:24px 0;padding:18px;background:white;border-left:4px solid #077162}
img{display:block;max-width:100%;height:auto}figcaption{margin-top:12px;color:#435c67;font-size:.88rem}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;background:white;width:100%}td,th{padding:9px;border:1px solid #bdcfcf;text-align:left;min-width:80px}th{background:#dbeeea}"""
    html='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PHPの11月更新と10月のPHP2Shell</title><style>'+css+"</style><main>"+content+"</main></html>"
    files["index.html"]=html.encode("utf-8")
    files["article.md"]=FIGURE.sub(lambda m:snippet(m[1],"md"),draft).encode("utf-8")
    files["blog-body.mdx"]=FIGURE.sub(lambda m:snippet(m[1],"mdx"),draft).encode("utf-8")
    review=OUT/"article-review/v01";review.mkdir(parents=True,exist_ok=True)
    for name,data in files.items():
        path=review/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    checks=[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(channel="chrome")
        for width in (390,1440):
            page=browser.new_page(viewport={"width":width,"height":900})
            page.goto((review/"index.html").as_uri(),wait_until="load")
            status=page.evaluate("""() => ({images:[...document.images].filter(i=>i.complete && i.naturalWidth>0).length,
                width:innerWidth,body:document.documentElement.scrollWidth,figures:document.querySelectorAll('figure').length})""")
            if status["images"]!=4 or status["figures"]!=4 or status["body"]>width:raise ValueError(status)
            page.screenshot(path=str(review/f"review-{width}.png"))
            checks.append(status);page.close()
        browser.close()
    sums={name:hashlib.sha256(blob).hexdigest() for name,blob in files.items()}
    files["SHA256SUMS.json"]=(json.dumps(sums,indent=2)+"\n").encode()
    output=OUT/"release/v01/article/php-security-article-v01.zip";output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,"x",compression=ZIP_DEFLATED) as z:
        for name,blob in sorted(files.items()):z.writestr(name,blob)
    with ZipFile(output) as z:
        if z.testzip() or any(hashlib.sha256(z.read(name)).hexdigest()!=hash_ for name,hash_ in sums.items()):raise ValueError("Article ZIP verification failed")
    write(output.with_suffix(".qc.json"),dict(bytes=output.stat().st_size,sha256=sha(output),entries=len(files),pages=checks,figures=4))
    print(output.name,output.stat().st_size,checks)
if __name__=="__main__":main()
