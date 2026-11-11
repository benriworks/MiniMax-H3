"""Capture all graphs in the public launch article and preserve pixel-derived excerpts."""
import argparse
from datetime import datetime
from hashlib import sha256
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/content-projects" / Path(__file__).parent.name
CAP = OUT / "captures-v02"
LAUNCH = "https://www.anthropic.com/claude-fable-and-mythos-5-2"
DOCS = "https://platform.claude.com/docs/en/models/fable-5-2/overview"
SOL = "https://developers.openai.com/api/docs/models/gpt-6.1-sol"
FIGURES = [
    ("frontiercode", "FrontierCode 2.0", "Agentic coding: FrontierCode 2.0"),
    ("wandr", "WANDR (relaxed score)", "Agentic search: WANDR"),
    ("benchcad", "BenchCAD 2.1 (with tools)", "Hardware engineering: BenchCAD 2.1"),
    ("hle", "Humanity’s Last Exam (with tools)", "Multidisciplinary reasoning: Humanity’s Last Exam"),
    ("chartography", "Chartography (no tools)", "Visual chart recognition: Chartography"),
    ("cve", "CVE Rediscovery", None),
    ("fermat", "Fermat’s Last Theorem proof formalization", None),
    ("robodojo", "RoboDojo (average)", None),
    ("audit", "Automated behavioral audit", None),
]
DPR = 2
VIEWPORT = {"width": 1600, "height": 1050}


def record(path):
    return dict(path=path.relative_to(OUT).as_posix(), bytes=path.stat().st_size,
                sha256=sha256(path.read_bytes()).hexdigest())


def raster_record(path):
    with Image.open(path) as image:
        width, height = image.size
    return dict(record(path), width=width, height=height)


def save_figure(page, locator, slug, title, checked_at, url):
    locator.scroll_into_view_if_needed()
    if slug in {item[0] for item in FIGURES}:
        locator.locator("svg[aria-label]").wait_for()
    page.evaluate("document.fonts.ready")
    raw = CAP / "original" / f"{slug}.png"
    locator.screenshot(path=raw, animations="disabled", timeout=20_000)
    copied = CAP / "quotes" / raw.name
    result = dict(id=slug, title=title, url=url, checked_at=checked_at, kind="official_capture",
                  original=raster_record(raw), viewport=VIEWPORT, device_scale_factor=DPR)
    if slug in {item[0] for item in FIGURES}:
        outer = locator.bounding_box()
        plot = locator.locator('[class*="_panel"]').bounding_box()
        left = round((plot["x"]-outer["x"])*DPR)
        top = round((plot["y"]-outer["y"])*DPR)
        with Image.open(raw) as src:
            crop = (max(0, left), max(0, top), min(src.width, left+round(plot["width"]*DPR)),
                    min(src.height, top+round(plot["height"]*DPR)))
            src.crop(crop).save(copied)
        result.update(crop_xyxy=crop, transform="crop to official panel, excluding body caption")
    else:
        copied.write_bytes(raw.read_bytes())
        result["transform"] = "element capture, byte-identical excerpt"
    result["excerpt"] = raster_record(copied)
    return result


def capture_comparison(page, checked_at):
    # Make the site's sticky column headers part of the same stationary capture.
    style = page.add_style_tag(content="body *{visibility:hidden !important;} "
                               "main figure table, main figure table *{visibility:visible !important;} "
                               "main figure table thead, main figure table thead th "
                               "{position:static !important;top:auto !important;}")
    fig = page.locator("main figure table")
    result = save_figure(page, fig, "benchmark-table", "Performance comparison table", checked_at, LAUNCH)
    base = fig.bounding_box()
    head = fig.locator("thead")
    rows = fig.locator('tbody tr[class*="_under-label"]')
    texts = rows.all_text_contents()
    if len(texts) != 14:
        raise ValueError(f"Expected 14 visible benchmarks, got {len(texts)}")
    result["benchmark_rows"] = texts
    result["visible_table_text"] = fig.inner_text()
    result["columns"] = head.locator("th[scope=col]").all_text_contents()
    result["transform"] = "isolated published table; header and numeric cells use original page pixels"
    with Image.open(CAP / "original/benchmark-table.png") as src:
        def bottom(bounds):
            return round((bounds["y"] + bounds["height"] - base["y"]) * DPR)
        head_end = bottom(head.bounding_box())
        for idx, (start, end) in enumerate([(0, 4), (4, 8), (8, 14)], 1):
            def row_top(index):
                return round((rows.nth(index).bounding_box()["y"] - base["y"]) * DPR)
            top = head_end if not start else row_top(start)
            end_y = row_top(end) if end < len(texts) else src.height
            width = src.width
            piece = Image.new("RGB", (width, head_end + end_y - top), "white")
            piece.paste(src.crop((0, 0, width, head_end)), (0, 0))
            piece.paste(src.crop((0, top, width, end_y)), (0, head_end))
            path = CAP / "quotes" / f"benchmark-table-{idx}.png"
            piece.save(path)
            result.setdefault("slices", []).append(dict(raster_record(path), header=(0, 0, width, head_end),
                                                       body=(0, top, width, end_y), visible_rows=(start+1, end)))
    style.evaluate("node => node.remove()")
    return result


def open_page(page, url, name, ready="main h1"):
    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if response is None or response.status != 200 or not page.url.startswith(url):
        raise RuntimeError(f"Official page failed to load: {url}")
    page.locator(ready).first.wait_for(timeout=12_000)
    (CAP / "source" / f"{name}-rendered.html").write_text(page.content(), encoding="utf-8")


def main():
    for area in ("source", "original", "quotes"):
        (CAP / area).mkdir(parents=True, exist_ok=True)
    if (CAP / "manifest.json").exists():
        raise FileExistsError("Preserve the existing capture version before recapturing")
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=DPR, reduced_motion="reduce")
        open_page(page, LAUNCH, "launch")
        matches = page.locator('main [data-type="chart"] figure svg[aria-label]')
        labels = matches.evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-label'))")
        if labels != [item[1] for item in FIGURES]:
            raise ValueError(f"Launch chart set changed: {labels!r}")
        assets = []
        for slug, title, tab in FIGURES:
            if tab:
                control = page.get_by_role("tab", name=tab, exact=True)
                if control.count():
                    control.click(timeout=20_000)
                else:
                    page.get_by_role("button", name="More views", exact=True).first.click(timeout=20_000)
                    page.get_by_role("menuitem", name=tab, exact=True).click(timeout=20_000)
            plot = page.locator('main [data-type="chart"] figure').filter(
                has=page.locator(f'svg[aria-label="{title}"]'))
            page.mouse.move(10, 10)
            assets.append(save_figure(page, plot, slug, title, checked_at, LAUNCH))
            print(f"{slug}: {assets[-1]['excerpt']['width']} × {assets[-1]['excerpt']['height']}", flush=True)
        assets.append(capture_comparison(page, checked_at))
        assets.append(save_figure(page, page.locator("main h1").first.locator(".."), "release-header",
                                  "Claude Fable 5.2 and Mythos 5.2", checked_at, LAUNCH))
        open_page(page, DOCS, "claude-docs")
        assets.append(save_figure(page, page.locator("main h1").first.locator(".."), "fable-docs",
                                  "Claude Platform Docs", checked_at, DOCS))
        sol_intro = "Near-Astra performance for complex work at a lower cost."
        open_page(page, SOL, "openai-sol", f"text={sol_intro}")
        summary = page.get_by_text(sol_intro, exact=True).filter(visible=True).first.locator("..").locator("..")
        assets.append(save_figure(page, summary, "sol-docs", "GPT-6.1 Sol API model", checked_at, SOL))
        browser.close()
    manifest = dict(checked_at=checked_at, launch_url=LAUNCH, graph_count=len(labels), assets=assets,
                    source_snapshots=[record(path) for path in sorted((CAP / "source").glob("*.html"))])
    (CAP / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def repair_table():
    manifest_path = CAP/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous = CAP/"previous-table"
    previous.mkdir()
    shutil.copyfile(manifest_path, previous/"manifest.json")
    shutil.copyfile(CAP/"original/benchmark-table.png", previous/"original.png")
    for path in (CAP/"quotes").glob("benchmark-table*.png"):
        shutil.copyfile(path, previous/path.name)
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=DPR)
        response = page.goto(LAUNCH, wait_until="domcontentloaded", timeout=60_000)
        if response is None or response.status != 200:
            raise RuntimeError("Launch page did not load")
        result = capture_comparison(page, checked_at)
        browser.close()
    manifest["assets"] = [result if asset["id"] == "benchmark-table" else asset
                          for asset in manifest["assets"]]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(result["columns"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-table", action="store_true")
    args = parser.parse_args()
    repair_table() if args.repair_table else main()
