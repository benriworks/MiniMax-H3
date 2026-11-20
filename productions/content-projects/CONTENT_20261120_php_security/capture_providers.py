"""Capture the published Red Hat photograph and short excerpts on the two distribution sites."""
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image
from playwright.sync_api import sync_playwright

from capture import OUT, sha, write

ROOT = OUT / "captures/providers-v01"
RED_HAT = "https://access.redhat.com/security/vulnerabilities/RHSB-2026-020"
REMI = "https://blog.remirepo.net/post/2026/11/19/PHP-version-8.2.36-8.3.37-8.4.28-8.5.13"
HAT = "https://www.redhat.com/en/about/brand/standards/the-hat"
PHOTO_ALT = "A display at Red Hat Summit features dozens of fedoras hanging above the Red Hat Cool Stuff Store booth."
EXCERPTS = [
    ("redhat-notice", RED_HAT, "h1", "RHSB-2026-020 Multiple vulnerabilities - PHP"),
    ("redhat-products", RED_HAT, "p", "The following two flaws do not affect PHP versions shipped in Red Hat Enterprise Linux"),
    ("remi-notice", REMI, "h2", "PHP version 8.2.36, 8.3.37, 8.4.28 and 8.5.13"),
]
# Find glyphs in the browser's real text, including text split between inline elements.
RANGE = """(node, target) => {
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let text = '', offsets = [];
    while (walker.nextNode()) {
        const n = walker.currentNode;
        for (let i=0; i<n.length; i++) {text += n.data[i]; offsets.push([n,i]);}
    }
    const start = text.indexOf(target);
    if (start < 0) throw Error('Quoted passage changed');
    const range = document.createRange();
    range.setStart(...offsets[start]);
    const [last, end] = offsets[start + target.length - 1]; range.setEnd(last, end + 1);
    return [...range.getClientRects()].filter(r=>r.width>0 && r.height>0)
        .map(r=>[r.left,r.top,r.right,r.bottom]);
}"""

def record(path):
    with Image.open(path) as im:
        im.load()
        return dict(path=path.relative_to(OUT).as_posix(), pixels=list(im.size), bytes=path.stat().st_size, sha256=sha(path))

def prepare(page, url):
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if not resp or resp.status != 200:
        raise RuntimeError(f"Could not open {url}")
    page.evaluate("document.fonts.ready")
    # Dismiss consent using the site's own controls when a banner obscures the citation.
    for selector in ("#onetrust-reject-all-handler", "#truste-consent-required", "#onetrust-accept-btn-handler"):
        dismiss = page.locator(selector).first
        if dismiss.count() and dismiss.is_visible():
            dismiss.click(timeout=2500)
            break

def main():
    raw, quotes = ROOT/"original", ROOT/"quotes"
    if (ROOT/"manifest.json").exists(): raise FileExistsError(ROOT/"manifest.json")
    raw.mkdir(parents=True, exist_ok=True)
    quotes.mkdir(parents=True, exist_ok=True)
    assets = {}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width":1550, "height":1020}, device_scale_factor=2, locale="en-US")
        for key, url, selector, passage in EXCERPTS:
            prepare(page, url)
            loc = page.locator(selector).filter(has_text=passage).first
            loc.wait_for(state="visible", timeout=18000)
            loc.evaluate("e => e.scrollIntoView({block:'center',behavior:'instant'})")
            rects = loc.evaluate(RANGE, passage)
            origin = raw / (key+".png")
            page.screenshot(path=str(origin), animations="disabled")
            coords = []
            for left,top,right,bottom in rects:
                rect = (int(left*2),int(top*2),int(right*2+1),int(bottom*2+1))
                if min(rect)<0 or rect[2]>3100 or rect[3]>2040: raise ValueError((key,rect))
                if coords and abs(rect[1]-coords[-1][1])<8:
                    a,b,c,d = coords[-1]
                    coords[-1] = (min(a,rect[0]),min(b,rect[1]),max(c,rect[2]),max(d,rect[3]))
                else: coords.append(rect)
            with Image.open(origin) as original:
                parts=[original.crop(rect).convert("RGB") for rect in coords]
                excerpt=Image.new("RGB",(max(piece.width for piece in parts)+36,sum(piece.height+8 for piece in parts)+24),"white")
                y=14
                for piece in parts: excerpt.paste(piece,(18,y)); y += piece.height+8
                target=quotes/(key+".png")
                excerpt.save(target)
            assets[key]=dict(url=url,title=page.title(),passage=passage,crop_pixels=coords,original=record(origin),quote=record(target))
        prepare(page, HAT)
        element=page.get_by_alt_text(PHOTO_ALT, exact=True)
        element.scroll_into_view_if_needed()
        element.evaluate("e=>e.decode()")
        element.evaluate("e=>e.scrollIntoView({block:'center',behavior:'instant'})")
        photo_url=element.evaluate("e=>e.currentSrc")
        response=page.request.get(photo_url, timeout=45000)
        if not response.ok: raise ValueError(response.status)
        data=response.body()
        with Image.open(BytesIO(data)) as im:
            if im.format!="JPEG" or im.width<600: raise ValueError(im.size)
        source=quotes/"redhat-photo.jpg"; source.write_bytes(data)
        origin=raw/"redhat-photo.png"; page.screenshot(path=str(origin), animations="disabled")
        assets["redhat-photo"]=dict(url=HAT,title=page.title(),photo_url=photo_url,description=PHOTO_ALT,
            credit="写真引用　Red Hat「The hat」／Red Hat Summit",placement="会場に並ぶ実物の赤い帽子から、Red Hatが配るPHPの告知へつなぐ。",original=record(origin),quote=record(source))
        browser.close()
    write(ROOT/"manifest.json",dict(captured_utc=datetime.now(timezone.utc).isoformat(),viewport=[1550,1020],scale=2,assets=assets))
    print({key:asset["quote"]["pixels"] for key,asset in assets.items()})

if __name__=="__main__": main()
