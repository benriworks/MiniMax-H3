"""Photograph official notices on the local browser and keep short, traceable quotation crops."""
from datetime import datetime, timezone
from hashlib import file_digest
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
ARCHIVE = "https://www.php.net/archive/2026.php"
IPA = "https://www.ipa.go.jp/security/security-alert/2026/pre-alert20261119.html"
API = "https://api.github.com/repos/php/php-src/security-advisories"
# The locator identifies the real text. Only its measured lines enter the published image.
SHOTS = [
    ("october", ARCHIVE + "#2026-10-21-5", "a[id='2026-10-21-5']", "Critical remote code execution vulnerabilities, update now"),
    ("conditions", ARCHIVE + "#2026-11-18-1", "article", "The issues rated CRITICAL require either non-default configuration or uncommon setups."),
    ("november", ARCHIVE + "#2026-11-19-4", "a[id='2026-11-19-4']", "PHP 8.5.13 Released!"),
    ("ipa", IPA, "p.article-txt", "一般的ではないセットアップ"),
]
def sha(path):
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def capture():
    from playwright.sync_api import sync_playwright
    original, quotes = OUT/"captures/original", OUT/"captures/quotes"
    original.mkdir(parents=True, exist_ok=True)
    quotes.mkdir(parents=True, exist_ok=True)
    records = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=2, locale="ja-JP")
        for key, url, selector, phrase in SHOTS:
            page.goto("about:blank")
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response.status != 200:
                raise ValueError((key, response.status))
            node = page.locator(selector).filter(has_text=phrase).first
            node.wait_for(state="visible")
            if key == "conditions":
                node = node.locator("p").filter(has_text=phrase).first
            page.evaluate("document.fonts.ready")
            node.evaluate("e => e.scrollIntoView({block:'center',behavior:'instant'})")
            page.wait_for_function("(e) => {const r=e.getBoundingClientRect();return r.bottom>0 && r.top<innerHeight}", arg=node.element_handle())
            # Visual ranges are measured after whitespace normalization, across inline markup.
            box = node.evaluate("""(el, phrase) => {
                const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
                let text='', refs=[], prior=false;
                while(walker.nextNode()){
                    const n=walker.currentNode;
                    for(let i=0;i<n.data.length;i++){
                        const c=n.data[i],sp=/\\s/.test(c);
                        if(sp && prior)continue;
                        text+=sp?' ':c;refs.push([n,i]);prior=sp;
                    }
                }
                const i=text.indexOf(phrase);
                if(i<0) throw Error('Passage changed');
                const r=document.createRange(), first=refs[i],last=refs[i+phrase.length-1];
                r.setStart(first[0],first[1]);r.setEnd(last[0],last[1]+1);
                return Array.from(r.getClientRects()).filter(b=>b.width>0 && b.height>0)
                    .map(b=>[b.left,b.top,b.right,b.bottom]);
            }""", phrase)
            if not box or any(not (0 <= b[0] < b[2] <= 1501 and 0 <= b[1] < b[3] <= 951) for b in box):
                raise ValueError((key, "quotation outside viewport", box))
            frame = original / f"{key}.png"
            page.screenshot(path=str(frame), animations="disabled")
            with Image.open(frame) as im:
                # Individual line fragments from the real screen, preserving line order.
                # For a wrapped phrase, a rectangular crop could include unrelated adjoining prose.
                lines = []
                for x,y,r,b in sorted(box, key=lambda v:(round(v[1]/5),v[0])):
                    if lines and abs(lines[-1][1]-y)<5:
                        lines[-1] = [min(x,lines[-1][0]), min(y,lines[-1][1]), max(r,lines[-1][2]), max(b,lines[-1][3])]
                    else:
                        lines.append([x,y,r,b])
                coords = [[max(0,int(x*2)-1),max(0,int(y*2)-1),min(im.width,int(r*2)+2),min(im.height,int(b*2)+2)] for x,y,r,b in lines]
                parts=[im.crop(rect).convert("RGB") for rect in coords]
                crop=Image.new("RGB",(max(p.width for p in parts)+32,sum(p.height for p in parts)+10*(len(parts)-1)+32),"white")
                y=16
                for part in parts:
                    crop.paste(part,(16,y));y+=part.height+10
                path=quotes / f"{key}.png";crop.save(path)
                records.append(dict(id=key,url=url,page_title=page.title(),quote=phrase,
                    retrieved=datetime.now(timezone.utc).isoformat(),viewport_pixels=list(im.size),
                    raw_sha256=sha(frame),raw_bytes=frame.stat().st_size,crop_rects=coords,
                    quote_pixels=list(crop.size),quote_sha256=sha(path),quote_bytes=path.stat().st_size))
        browser.close()
    write(OUT/"captures/manifest.json",records)
    print([(r["id"],r["quote_pixels"]) for r in records])

def collect():
    import requests
    next_url=API+"?per_page=100"
    rows=[]
    while next_url:
        response=requests.get(next_url,timeout=30)
        response.raise_for_status()
        rows.extend(dict(cve=r["cve_id"],severity=r["severity"],url=r["html_url"],published=r["published_at"])
                    for r in response.json() if (r.get("published_at") or "")[:10]=="2026-11-19")
        next_url=response.links.get("next",{}).get("url")
    rows.sort(key=lambda r:r["cve"])
    if len({r["cve"] for r in rows})!=17 or sum(r["severity"]=="critical" for r in rows)!=7:
        raise ValueError("Official notice set has changed; check the figures before reuse")
    write(OUT/"captures/advisory-metadata.json",rows)
    print("November 19 UTC: 17 vendor advisories, 7 Critical")
if __name__=="__main__":
    manifest=OUT/"captures/manifest.json"
    if manifest.exists():
        for record in json.loads(manifest.read_text(encoding="utf-8")):
            key=record["id"]
            if (sha(OUT/"captures/original"/f"{key}.png")!=record["raw_sha256"] or
                    sha(OUT/"captures/quotes"/f"{key}.png")!=record["quote_sha256"]):
                raise ValueError("Frozen screenshot changed: "+key)
        print("Verified the four preserved official screenshots")
    else:
        capture()
    if not (OUT/"captures/advisory-metadata.json").exists():
        collect()
