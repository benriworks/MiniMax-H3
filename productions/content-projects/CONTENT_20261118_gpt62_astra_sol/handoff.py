"""Register the brief and article images in Studio and package the draft for review."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
PROJECT = HERE.name
DATE = "2026-11-18"
SLUG = "gpt-62-astra-sol"
SOURCES = {
    "launch": ("OpenAI公式発表", "https://openai.com/index/introducing-gpt-6-2-astra-sol/"),
    "work": ("ChatGPT Learnの利用ガイド", "https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol"),
    "astra": ("GPT-6.2 Astraモデル資料", "https://developers.openai.com/api/docs/models/gpt-6.2-astra"),
    "sol": ("GPT-6.2 Solモデル資料", "https://developers.openai.com/api/docs/models/gpt-6.2-sol"),
}
CAPTIONS = {
    "app-model-picker": "Codexの実際のモデルメニュー。上からGPT-6.2 Sol、GPT-6.2 Astra。",
    "app-composer": "Codexの新規入力欄と、入力欄の右側から開いたモデルメニュー。",
    "slide-template": "OpenAIの公式作例にある、取引先の進捗をまとめるための見本。",
    "slide-comparison": "OpenAIの公式作例。左が旧GPT-6 Astra、右がGPT-6.2 Astra。",
    "slide-astra-detail": "GPT-6.2 Astraの出力。2店舗の試験導入と、次の作業の担当者・日付。",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record(media, figures):
    workspace = media.parents[2]
    operations = media / "workspace-operations"
    operations.mkdir(exist_ok=True)

    def cli(operation, body=None, **flags):
        cmd = [sys.executable, "-X", "utf8", "-m", "tools.studio.content_workspace",
               operation, "--workspace", str(workspace)]
        for key, value in flags.items():
            cmd.extend(["--" + key.replace("_", "-"), value])
        if body:
            file = operations / (body["operation_id"] + ".json")
            write_json(file, body)
            cmd.extend(["--input", str(file)])
        result = subprocess.run(cmd, cwd=workspace, capture_output=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stdout or result.stderr)
        return json.loads(result.stdout)

    request = next(line[2:] for line in (HERE / "REQUEST_JA.md").read_text(encoding="utf-8").splitlines()
                   if line.startswith("> "))
    story = read_json(HERE / "story-v01.json")
    if any(row["content_project_id"] == PROJECT for row in cli("list")["items"]):
        state = cli("get", project_id=PROJECT)
    else:
        state = cli("create", dict(operation_id="gpt62-create-v01", content_project_id=PROJECT,
                    title="GPT-6.2 AstraとSolの使い分け", topic=request, format="short_and_full"))

    def apply(action, item, **data):
        nonlocal state
        key = f"gpt62-{action}-{item}"
        receipt = operations / (key + "-applied.json")
        if receipt.exists():
            return
        pending = operations / (key + ".json")
        body = (read_json(pending) if pending.exists() else
                dict(operation_id=key, expected_revision=state["project"]["revision"], data=data))
        state = cli("apply", body, project_id=PROJECT, action=action)
        write_json(receipt, {"revision": state["project"]["revision"]})

    apply("research", "v01", research_id="launch-v01", checked_at=DATE,
          summary="GPT-6.2の公式発表、WorkとCodex、標準API料金、公式作例を照合。",
          sources=[dict(source_id=key, title=title, url=url, kind="official", checked_at=DATE)
                   for key, (title, url) in SOURCES.items()])
    for figure in figures:
        asset = figure["asset"]
        is_app = asset.startswith("app-")
        data = dict(fictional_materials_only=True) if is_app else dict(
            source_url=SOURCES["launch"][1] + "#slideshows", source_checked_at=DATE)
        apply("asset", asset, asset_id=asset, path=(media / figure["path"]).relative_to(workspace).as_posix(),
              kind="demonstration_capture" if is_app else "official_capture", visibility="public",
              privacy_review="passed", blog_usage_review="passed", user_approved_for_blog=False,
              sha256=figure["sha256"], width=figure["pixels"][0], height=figure["pixels"][1],
              alt=CAPTIONS[asset], caption=CAPTIONS[asset], **data)
    apply("capture", "picker", inspection_id="picker", target_feature="CodexでGPT-6.2を選ぶ",
          status="captured", checked_at=DATE, app="Windows / Chrome / Codex", login_state="ログイン済み",
          route="Codexの新規入力欄→思考量→モデルを選択", feature_entry="入力欄のモデルメニュー",
          display_result="GPT-6.2 AstraとSolの選択肢", result="両モデル名を選択肢で確認",
          save_result="PNG原本とWebPの切り出しを保存", legibility="全体とモデルメニューの詳細を用意",
          asset_ids=["app-model-picker", "app-composer"],
          shots=[{"shot_id":"picker", "asset_id":"app-model-picker", "purpose":"両モデルを確認"}])

    episodes = [dict(episode_id=kind, title=story["titles"][kind], overview=overview,
                     intended_message="ふだんの仕事はSol。難しい仕事はAstra。",
                     demo_idea="Codexのモデル選択実画面と、予約アプリの架空の作業例。",
                     article_role="提供条件、標準API単価と公式スライド作例の出典を補う。",
                     capture_inspection_id="picker", duration_seconds=seconds)
                for kind, seconds, overview in (
                    ("short", 46, "用途、短い会話、両モデルの選択画面"),
                    ("full", 148, "用途、予約アプリの架空例、資料作例、API単価と選択画面"))]
    apply("proposal", "v01", proposal_id="gpt62-v01", count_reason="ユーザーがショートとフルの2本を依頼。",
          episodes=episodes)
    apply("feedback", "request", feedback_id="request", proposal_id="gpt62-v01", kind="comment",
          text=request, interpretation="既存男女を継続し、結論で始まるショートとフルを制作。")
    sections = [
        ("usage", "変更箇所が分かっているときはSol", "work", [],
         "OpenAIは日常の修正・レビューにSol、複数サービスを追う調査にAstraを例示。"),
        ("slides", "公式のスライド作例で見るAstra", "launch",
         ["slide-template", "slide-comparison", "slide-astra-detail"],
         "OpenAIは旧Astraと新Astraで同じ見本を使ったスライド出力例を公開。"),
        ("picker", "ChatGPT WorkとCodexのモデル選択", "work",
         ["app-composer", "app-model-picker"], "CodexとWorkのモデル選択で両モデルを提供。"),
        ("price", "APIの標準単価", "launch", [],
         "標準APIは100万トークンあたりSolが入力2ドル・出力10ドル、Astraは入力8ドル・出力40ドル。"),
    ]
    for key, title, source, assets, claim in sections:
        apply("claim", key, claim_id=key, basis="official", checked_at=DATE, text=claim,
              source_ids=[source], asset_ids=assets)
    apply("article", "v01", version="v01", slug=SLUG, destination="benriworks/blog", published=False,
          sections=[dict(section_id=key,title=title,source_ids=[source],asset_ids=assets,claim_ids=[key])
                    for key, title, source, assets, claim in sections])
    write_json(media / "workspace-state-v01.json", state)
    print(f"Studio revision {state['project']['revision']}")


def package(media, figures):
    folder = media / "release/v02/article"
    assets = folder / "figures"
    assets.mkdir(parents=True, exist_ok=True)
    images = {figure["asset"]: figure for figure in figures}
    manuscript = (HERE / "article-draft-v01.md").read_text(encoding="utf-8")
    mdx = manuscript.split("\n", 2)[2].lstrip()
    for key, item in images.items():
        shutil.copyfile(media / item["path"], assets / (key + ".webp"))
        width, height = item["pixels"]
        alt = CAPTIONS[key]
        tag = (f'<Figure src="/images/articles/{SLUG}/{key}.webp" width={{{width}}} height={{{height}}} '
               f'alt="{alt}" caption="{alt}" zoom />')
        mdx = mdx.replace(f"<!-- figure:{key} -->", tag)
    mdx = ('---\nslug: gpt-62-astra-sol\ntitle: GPT-6.2 AstraとSolの違い。Codexでどちらを選ぶ？\n'
           'contentType: guide\npublishedAt: 2026-11-18\nupdatedAt: 2026-11-18\n'
           'draft: true\ntopics: [ai-development]\n---\n\n' + mdx)
    (folder / (SLUG + ".mdx")).write_text(mdx, encoding="utf-8")

    def figure(match):
        key = match[1]
        width, height = images[key]["pixels"]
        caption = escape(CAPTIONS[key])
        return (f'<figure><a href="figures/{key}.webp"><img src="figures/{key}.webp" width="{width}" '
                f'height="{height}" alt="{caption}"></a><figcaption>{caption}</figcaption></figure>')

    document = MarkdownIt("commonmark", {"html": True}).enable("table").render(
        re.sub(r"<!-- figure:([\w-]+) -->", figure, manuscript))
    css = """
    *{box-sizing:border-box} body{margin:0;background:#f7f8f9;color:#172635;font:17px/1.8 system-ui,sans-serif}
    article{max-width:840px;margin:auto;padding:36px 23px 64px} h1{font-size:clamp(1.8rem,5vw,3rem);line-height:1.28}
    h2{font-size:1.38rem;margin-top:2.2rem} a{color:#08695f} figure{margin:1rem 0}
    img{max-width:100%;height:auto;display:block;border-radius:7px} figcaption{font-size:.82rem;color:#3b4e60;margin-top:.45rem}
    table{width:100%;border-collapse:collapse;font-size:clamp(.73rem,2.8vw,1rem)} td,th{border-bottom:1px solid #b5c7d2;padding:5px}
    """
    (folder / "preview.html").write_text('<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>GPT-6.2 AstraとSolの違い</title><style>' + css + '</style><article>' + document + '</article>',
        encoding="utf-8")
    for name in ("article-draft-v01.md", "SOURCES_JA.md"):
        shutil.copyfile(HERE / name, folder / name)
    write_json(folder / "asset-manifest.json", list(images.values()))
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    sums = {p.relative_to(folder).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files}
    (folder / "SHA256SUMS.txt").write_text("".join(f"{value}  {name}\n" for name, value in sums.items()),
                                         encoding="utf-8")
    output = folder.parent / "gpt62-astra-sol-article-v02.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipped:
        for entry in [*files, folder / "SHA256SUMS.txt"]:
            zipped.write(entry, entry.relative_to(folder))
    with zipfile.ZipFile(output) as zipped:
        assert zipped.testzip() is None
        assert all(sha256(zipped.read(name)).hexdigest() == value for name, value in sums.items())
        print(output, len(zipped.namelist()), "members")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("record", "package"))
    parser.add_argument("--media", type=Path, required=True)
    args = parser.parse_args()
    media = args.media.resolve()
    figures = read_json(media / "captures/figures/manifest.json")
    for figure in figures:
        assert sha256((media / figure["path"]).read_bytes()).hexdigest() == figure["sha256"]
    {"record": record, "package": package}[args.action](media, figures)


if __name__ == "__main__":
    main()
