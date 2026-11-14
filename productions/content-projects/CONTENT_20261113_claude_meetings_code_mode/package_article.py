"""Package a source-attributed review article with the Studio-verified figures."""
from hashlib import sha256
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json
import re

from markdown_it import MarkdownIt

from prepare import HERE, OUT, FIGURES, save
from record_workspace import SLUG

CSS = """
:root{color-scheme:light;font:17px/1.76 'Segoe UI','Yu Gothic',system-ui,sans-serif;background:#f6f3eb;color:#18312e}
main{max-width:760px;margin:auto;padding:28px 20px 72px}h1,h2,h3{line-height:1.32;text-wrap:balance}
h1{font-size:clamp(1.9rem,4.6vw,2.65rem)}h2{border-top:1px solid #d9d4c6;padding-top:.8em;margin-top:2em}
table{border-collapse:collapse;display:block;overflow:auto;background:white}th,td{border:1px solid #d9d4c6;padding:8px 12px;text-align:left}
img{display:block;max-width:100%;height:auto;border-radius:8px;margin:auto}
figure{margin:24px 0}figcaption{color:#4c605a;font-size:.91rem}
a{color:#0b6154;text-underline-offset:3px;overflow-wrap:anywhere}
"""

IMAGE_RE = re.compile(r"!\[(.+?)\]\(images/([a-z-]+)\.webp\)")


def main():
    draft = (HERE / "article-draft-v01.md").read_text(encoding="utf-8")
    handoff = OUT / "blog-handoff/v01"
    manifest = json.loads((handoff / "asset-manifest.json").read_text(encoding="utf-8"))
    files = {"article-draft.md": draft.encode("utf-8"),
             "sources.md": (HERE / "SOURCES_JA.md").read_bytes(),
             "sources.json": (HERE / "sources.json").read_bytes(),
             "asset-manifest.json": (handoff / "asset-manifest.json").read_bytes(),
             "capture-inventory.json": (FIGURES / "manifest.json").read_bytes()}
    figures = {}
    for item in manifest["assets"]:
        identifier = item["asset_id"]
        blob = (handoff / item["handoff_path"]).read_bytes()
        assert sha256(blob).hexdigest() == item["sha256"].lower()
        files[f"images/{identifier}.webp"] = blob
        figures[identifier] = item

    def figure(match):
        alt, ident = match.groups()
        item = figures[ident]
        src = f"/images/articles/{SLUG}/{ident}.webp"
        return (f'<Figure src="{escape(src,quote=True)}" width={{{item["width"]}}} height={{{item["height"]}}} '
                f'alt="{escape(alt,quote=True)}" caption="{escape(item["caption"],quote=True)}" '
                f'sourceLabel="Claude公式資料" sourceUrl="{escape(item["source_url"],quote=True)}" zoom />')

    title = draft.splitlines()[0].removeprefix("# ")
    note = "記事草稿。blogへの取り込み時に、リポジトリのスキーマに沿ってfrontmatterを設定する。\n"
    files["blog-body.mdx"] = (IMAGE_RE.sub(figure, draft) + "\n").encode("utf-8")
    files["HANDOFF.md"] = (note + "画像のコピー先は asset-manifest.json の blog_path。"
        "動画と記事はレビュー候補。出典・撮影・加工は sources.md を参照。\n").encode("utf-8")

    def html_figure(match):
        alt, ident = match.groups()
        item = figures[ident]
        url = escape(item["source_url"],quote=True)
        src = f"images/{ident}.webp"
        return (f'<figure><a href="{src}"><img src="{src}" width="{item["width"]}" height="{item["height"]}" '
                f'alt="{escape(alt,quote=True)}"></a><figcaption>{escape(item["caption"])} '
                f'<a href="{url}">出典</a></figcaption></figure>')
    body = MarkdownIt("commonmark").enable("table").render(IMAGE_RE.sub(html_figure,draft))
    html = ('<!doctype html><html lang="ja"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style><main>{body}</main></html>\n')
    files["review.html"] = html.encode("utf-8")

    hashes = {name:sha256(blob).hexdigest() for name,blob in sorted(files.items())}
    root = OUT / "release/v01/article"
    root.mkdir(parents=True,exist_ok=True)
    path = root / "claude-1113-article-v01.zip"
    with ZipFile(path,"x",compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for name, blob in sorted(files.items()):
            archive.writestr(name,blob)
        archive.writestr("SHA256SUMS.json",json.dumps(hashes,indent=2)+"\n")
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(hashes) | {"SHA256SUMS.json"}
        assert all(sha256(archive.read(name)).hexdigest()==expected for name,expected in hashes.items())
        for name in (*[f"images/{ident}.webp" for ident in figures],"review.html"):
            dst = root / "preview" / name
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(archive.read(name))
    save(root/"qc.json",dict(file=path.name,bytes=path.stat().st_size,
         sha256=sha256(path.read_bytes()).hexdigest(),member_count=len(hashes)+1,image_count=len(figures),
         archive_check="passed",article_status="review",publication="unpublished"))
    print(f"{path.name}: {len(hashes)} verified files + manifest.")


if __name__ == "__main__":
    main()
