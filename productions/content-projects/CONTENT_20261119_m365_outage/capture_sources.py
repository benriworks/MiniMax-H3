"""Photograph the public notices in Chromium and isolate small primary quotations."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

import fitz
import requests
from PIL import Image
from playwright.sync_api import sync_playwright, Error as BrowserError

PDF = "https://ismg-cdn.nyc3.cdn.digitaloceanspaces.com/asset_files/external/microsoft-report.pdf"
MIRROR = "https://www.365fanatic.com/wp-content/uploads/2026/11/PostIncidentReport.pdf"
PAGES = {
    "status": ("https://status.cloud.microsoft/", None),
    "admin": ("https://admin.microsoft.com/Adminportal/Home#/servicehealth/:/alerts/MO1550821", None),
    "meiji": ("https://www.my-pharm.ac.jp/news/detail/513/?target=candidates", "お電話にてご連絡ください。"),
    "rits": ("https://www.ritsumei.ac.jp/extension/news/detail/?id=32", "再度予約する必要はありません。"),
    "osaka": ("https://www.ompu.ac.jp/news/cc9f84000002dv21.html", "Outlookが復旧次第"),
}
PHRASES = {
    "report-lock": "lock contention",
    "report-rate": "more than 80% of servers were unresponsive.",
    "report-wait": "immediately overwhelmed by waiting traffic",
}
RANGE = """term => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const t = walker.currentNode;
      const start = t.textContent.indexOf(term);
      if (start < 0 || !t.parentElement.checkVisibility()) continue;
      t.parentElement.scrollIntoView({block:'center', behavior:'instant'});
      const range = new Range();
      range.setStart(t,start); range.setEnd(t,start+term.length);
      const r = range.getBoundingClientRect();
      if (r.width > 0) return {x:r.x,y:r.y,width:r.width,height:r.height};
    }
    return null;
}"""


def capture(media):
    private, figures = media / "_private/capture", media / "captures"
    private.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    manifest = {}
    response = requests.get(PDF, timeout=35)
    if response.status_code != 200 or not response.content.startswith(b"%PDF"):
        response = requests.get(MIRROR, timeout=35)
    response.raise_for_status()
    source = private / "preliminary-pir.pdf"
    source.write_bytes(response.content)
    doc = fitz.open(source)
    for name, text in PHRASES.items():
        for page in doc:
            hits = page.search_for(text)
            if not hits:
                continue
            # When a quote wraps, render the word groups individually to avoid context leakage.
            for i, rect in enumerate(hits[:1] if name == "report-lock" else hits):
                clip = fitz.Rect(rect.x0-.5, rect.y0, rect.x1+.5, rect.y1)
                png = figures / f"{name}-{i}.png"
                page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip, alpha=False).save(png)
            manifest[name] = dict(source=response.url, page=page.number+1, phrase=text,
                                  rects=[list(r) for r in hits], sha256=sha256(source.read_bytes()).hexdigest())
            break
        if name not in manifest:
            raise ValueError(text)
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width":1600,"height":1000},device_scale_factor=2,locale="ja-JP")
        for name, (url, term) in PAGES.items():
            page = ctx.new_page()
            try:
                http = page.goto(url, wait_until="domcontentloaded", timeout=28000)
                if term:
                    page.get_by_text(term, exact=False).first.wait_for(timeout=9000)
                else:
                    page.wait_for_timeout(1500)
                entry = dict(url=url, final_origin=page.url.split('/')[2], title=page.title(),
                             status=http.status if http else None)
                if name != "admin":
                    if term:
                        bounds = page.evaluate(RANGE, term)
                        if not bounds:
                            raise ValueError("No visible quote: "+name)
                        page.wait_for_timeout(450)
                        bounds = page.evaluate(RANGE, term)
                        clip = dict(x=max(0,bounds['x']-1),y=max(0,bounds['y']-2),
                                    width=bounds['width']+2,height=bounds['height']+4)
                        page.screenshot(path=str(private/(name+".png")),animations="disabled")
                        with Image.open(private/(name+".png")) as src:
                            scale = src.width / 1600
                            coords = (clip["x"],clip["y"],clip["x"]+clip["width"],clip["y"]+clip["height"])
                            src.crop(tuple(round(c*scale) for c in coords)).save(figures / (name+".png"))
                        entry.update(phrase=term, crop_css=clip)
                    else:
                        page.screenshot(path=str(private/(name+".png")),animations="disabled")
                manifest[name] = entry
            except (BrowserError, ValueError) as exc:
                manifest[name] = {"url":url,"error":str(exc).splitlines()[0]}
            finally:
                page.close()
        browser.close()
    (private/"sources.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
    for k, v in manifest.items():
        print(k, v.get("page") or v.get("title") or v.get("error"), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("media", type=Path)
    capture(ap.parse_args().media.resolve())
