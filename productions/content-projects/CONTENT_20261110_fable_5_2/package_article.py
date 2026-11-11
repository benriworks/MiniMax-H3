"""Package a versioned article draft with verified, purpose-limited image candidates."""
import html
import json
from hashlib import sha256
from pathlib import Path
import re
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

from markdown_it import MarkdownIt
from PIL import Image, ImageChops

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
CAP = OUT / "captures-v02"
DEST = OUT / "blog-handoff/v01"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    receipt = DEST / "asset-manifest.json"
    if receipt.exists():
        raise FileExistsError("Create a new article revision to change a verified package")
    (DEST/"assets").mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CAP/"manifest.json").read_text(encoding="utf-8"))
    story = json.loads((HERE/"story-v01.json").read_text(encoding="utf-8-sig"))
    article = (HERE/"article-draft-v01.md").read_text(encoding="utf-8-sig")
    keys = list(story["graphs"])+["benchmark-table"]
    sources = {item["id"]: item for item in manifest["assets"]}
    records = []
    for name in keys + ["demo-input", "demo-output"]:
        if name in sources:
            rec = sources[name]
            image = OUT / rec["excerpt"]["path"]
            source = OUT / rec["original"]["path"]
            if digest(image) != rec["excerpt"]["sha256"] or digest(source) != rec["original"]["sha256"]:
                raise ValueError(f"Capture checksum mismatch: {name}")
            with Image.open(source) as original, Image.open(image) as quote:
                if rec.get("crop_xyxy"):
                    original = original.crop(rec["crop_xyxy"])
                if ImageChops.difference(original.convert("RGB"), quote.convert("RGB")).getbbox():
                    raise ValueError(f"Quote pixels differ from source: {name}")
            context = dict(url=rec["url"], checked_at=rec["checked_at"], kind="official_excerpt",
                           title=rec["title"], original_sha256=rec["original"]["sha256"],
                           use="quoted for analysis in the review draft; publication pending")
        else:
            image = OUT/"demo"/("fixture.png" if name=="demo-input" else "output-excerpt.png")
            context = dict(kind="synthetic_input" if name=="demo-input" else "actual_cli_log_excerpt",
                           use="single synthetic-input demonstration; no desktop screenshot")
        dest = DEST/"assets"/(name+".png")
        shutil.copyfile(image, dest)
        with Image.open(dest) as copied:
            width, height = copied.size
        records.append(dict(id=name, file=dest.relative_to(DEST).as_posix(), bytes=dest.stat().st_size,
                            sha256=digest(dest), width=width, height=height, **context))
    referenced = re.findall(r"\]\((assets/[^)]+)\)", article)
    if len(referenced) != len(records) or set(referenced) != {item["file"] for item in records}:
        raise ValueError("Article figure references do not match the package")
    (DEST/"article-draft-v01.md").write_text(article, encoding="utf-8")
    shutil.copyfile(HERE/"SOURCES_JA.md", DEST/"SOURCES_JA.md")
    markup = MarkdownIt("commonmark", {"html": False}).render(article)
    markup = re.sub(r'<img src="(assets/[^"]+)" ([^>]+)>',
                    r'<a class="figure" href="\1"><img src="\1" \2></a>', markup)
    css = """body{margin:0;background:#f5f3ea;color:#163236;font:17px/1.85 system-ui,sans-serif}
main{max-width:740px;margin:auto;padding:24px 20px 80px} header{font-size:.9rem;color:#22665f;
padding-bottom:1.2rem;border-bottom:1px solid #92b0a6} h1{font-size:clamp(1.65rem,5vw,2.7rem);line-height:1.35}
h2{font-size:1.45rem;margin-top:2.5em}h3{margin-top:2em} p{margin:1.15em 0}
a{color:#095f59;overflow-wrap:anywhere}img{display:block;max-width:100%;height:auto}
.figure{display:block;border:1px solid #9ab1a8;border-radius:8px;overflow:hidden;background:white}
code{overflow-wrap:anywhere}"""
    page = (f'<!doctype html><html lang="ja"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(story["titles"]["full"])}</title><style>{css}</style>'
            f'<main><header>レビュー草稿 v01 ／ 図を開くと拡大できます</header>{markup}</main></html>')
    (DEST/"index.html").write_text(page, encoding="utf-8")
    receipt.write_text(json.dumps(dict(version="v01", graph_count=9, assets=records),
                                  ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    bundle = DEST.parent/"fable-5-2-article-review-v01.zip"
    with ZipFile(bundle, "x", compression=ZIP_DEFLATED) as archive:
        for f in sorted(p for p in DEST.rglob("*") if p.is_file()):
            archive.write(f, f.relative_to(DEST).as_posix())
    with ZipFile(bundle) as archive:
        assert archive.testzip() is None
        assert all(sha256(archive.read(item["file"])).hexdigest() == item["sha256"] for item in records)
    print(f"{len(records)} images checked; {bundle.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
