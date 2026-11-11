"""Bundle the review draft and approved-for-review derivatives, verifying every ZIP member."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import html
import json
import re

from markdown_it import MarkdownIt

from prepare import HERE, OUT, FIGURES, RAW, save

CSS = """
:root{color-scheme:light;font:17px/1.75 system-ui,'Yu Gothic',sans-serif;color:#1f2a28;background:#f6f2e9}
body{max-width:760px;margin:0 auto;padding:36px 20px 72px}
h1,h2,h3{line-height:1.35;text-wrap:balance}
h1{font-size:clamp(1.8rem,5vw,2.55rem);margin-top:.5em}
h2{margin-top:2.3em;border-top:1px solid #dbd4c6;padding-top:.8em}
img{display:block;width:auto;height:auto;max-width:100%;margin-inline:auto;border-radius:8px}
a{color:#075b4a;text-underline-offset:3px;overflow-wrap:anywhere}
table{display:block;overflow:auto;border-collapse:collapse;background:#fff}
td,th{padding:8px 12px;border:1px solid #ded7c9;text-align:left}
code{background:#eae5da;padding:.1em .22em}
"""


def main():
    article = (HERE / "article-draft-v01.md").read_text(encoding="utf-8")
    title = article.splitlines()[0].removeprefix("# ")
    handoff = OUT / "blog-handoff/v01"
    source_manifest = json.loads((handoff / "asset-manifest.json").read_text(encoding="utf-8"))
    files = {
        "記事草稿.md": article.encode("utf-8"),
        "出典と撮影記録.md": (HERE / "SOURCES_JA.md").read_bytes(),
        "asset-manifest.json": (handoff / "asset-manifest.json").read_bytes(),
        "figures.mdx": (handoff / "figures.mdx").read_bytes(),
        "captures.json": (FIGURES / "manifest.json").read_bytes(),
        "xlsx-verification.json": (FIGURES / "xlsx-verification.json").read_bytes(),
        "試食会-予算検証.xlsx": (RAW / "tasting-budget.xlsx").read_bytes(),
    }
    for item in source_manifest["assets"]:
        name = Path(item["handoff_path"]).name
        blob = (handoff / item["handoff_path"]).read_bytes()
        assert sha256(blob).hexdigest() == item["sha256"].lower()
        files["images/" + name] = blob
    for image in re.findall(r"\]\((images/[^)]+)\)", article):
        assert image in files
    body = MarkdownIt("commonmark").enable("table").render(article)
    files["記事プレビュー.html"] = (
        '<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style><main>{body}</main></html>\n"
    ).encode("utf-8")
    hashes = {name: sha256(blob).hexdigest() for name, blob in files.items()}
    folder = OUT / "release/v01/article"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "claude-nov10-article-v01.zip"
    with ZipFile(path, "x", compression=ZIP_DEFLATED, compresslevel=6) as zf:
        for name, blob in sorted(files.items()):
            zf.writestr(name, blob)
        zf.writestr("SHA256SUMS.json", json.dumps(hashes, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(path) as zf:
        assert zf.testzip() is None
        assert set(zf.namelist()) == set(hashes) | {"SHA256SUMS.json"}
        assert all(sha256(zf.read(name)).hexdigest() == digest for name, digest in hashes.items())
    save(folder / "qc.json", dict(path=path.name, sha256=sha256(path.read_bytes()).hexdigest(),
         bytes=path.stat().st_size, members=len(hashes)+1, verified=True, user_adoption="未確認", publication="未公開"))
    print(f"{path.name}: verified {len(hashes)} files and checksum manifest")


if __name__ == "__main__":
    main()
