"""Capture live Microsoft/University pages and the excerpt from the CEO's PDF."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw
import requests
from playwright.sync_api import sync_playwright

PAGES = {
    "status": "https://status.cloud.microsoft/",
    "news": "https://news.microsoft.com/events/ignite/2026/",
    "meiji": "https://www.my-pharm.ac.jp/news/detail/513/?target=candidates",
    "learn": "https://learn.microsoft.com/ja-jp/microsoft-365/enterprise/view-service-health?view=o365-worldwide",
}
PDF = "https://news.microsoft.com/events/wp-content/uploads/2026/11/Nadella_TRANSCRIPT_Ignite-Keynote_Nov-2026.pdf"
SCALE = 1.5
# Values are logical viewport pixels. The uncropped screenshot remains in the private folder.
CROPS = {
    "status": (302, 14, 1132, 284),
    "news": (0, 0, 1440, 860),
    "meiji": (120, 48, 1338, 593),
    "learn": (368, 407, 1160, 672),
}

def capture(media, reuse=False):
    raw = media / "_private/revision-03/official"
    public = media / "captures/revision-03"
    raw.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "sources.json"
    meta = json.loads(manifest_path.read_text(encoding="utf-8")) if reuse else {}
    if not reuse:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport=dict(width=1440,height=900), device_scale_factor=SCALE,locale="ja-JP",timezone_id="Asia/Tokyo")
            for key,url in PAGES.items():
                page = ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                if not resp or not resp.ok:
                    raise RuntimeError(f"{key}: {resp.status if resp else 'no response'}")
                page.locator("body").wait_for()
                if key=="status":
                    page.get_by_text("Microsoft 365",exact=False).first.wait_for(timeout=35000)
                page.evaluate("document.fonts.ready")
                page.wait_for_timeout(1500)
                # Close a displayed consent prompt with the site's own button.
                for label in ["すべて拒否", "Reject all", "Decline", "拒否"]:
                    btn=page.get_by_role("button",name=label,exact=True)
                    if btn.count() and btn.first.is_visible():
                        btn.first.click()
                        break
                page.screenshot(path=str(raw/(key+".png")),animations="disabled")
                (raw/(key+".txt")).write_text(page.locator("body").inner_text(),encoding="utf-8")
                meta[key]={"url":page.url,"title":page.title(),"http_status":resp.status,
                           "captured_utc":datetime.now(timezone.utc).isoformat(),"viewport":[1440,900],"dpr":SCALE}
                print(key,resp.status,flush=True)
                page.close()
            browser.close()
        pdf=requests.get(PDF,timeout=45)
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF"): raise ValueError("Expected a Microsoft-hosted PDF")
        (raw/"keynote.pdf").write_bytes(pdf.content)
        meta["keynote"]={"url":pdf.url,"captured_utc":datetime.now(timezone.utc).isoformat(),"page":1}
    for key,box in CROPS.items():
        src=raw/(key+".png")
        pixels=[round(q*SCALE) for q in box]
        Image.open(src).crop(pixels).save(public/(key+".png"))
        meta[key].update(raw_sha256=sha256(src.read_bytes()).hexdigest(),crop_px=pixels)
    with fitz.open(raw/"keynote.pdf") as doc:
        page=doc[0]
        for name,phrase in [("keynote-quote","we have work to do"),("keynote-date","Tuesday, November 17, 2026")]:
            hit=page.search_for(phrase)[0]
            clip=fitz.Rect(hit.x0-1,hit.y0,hit.x1+1,hit.y1)
            page.get_pixmap(matrix=fitz.Matrix(6,6),clip=clip).save(public/(name+".png"))
            meta["keynote"][name]={"phrase":phrase,"rect_pt":list(clip)}
    meta["keynote"]["raw_sha256"]=sha256((raw/"keynote.pdf").read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    board=Image.new("RGB",(1000,666),"#b9c6bf")
    for i,key in enumerate(PAGES):
        shot=Image.open(raw/(key+".png")); shot.thumbnail((500,310))
        x,y=(i%2)*500,(i//2)*333
        board.paste(shot,(x,y+19)); ImageDraw.Draw(board).text((x+7,y+3),key,fill="black")
    board.save(raw/"contact.jpg",quality=92)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("media",type=Path)
    parser.add_argument("--recrop",action="store_true")
    a=parser.parse_args();capture(a.media,a.recrop)
