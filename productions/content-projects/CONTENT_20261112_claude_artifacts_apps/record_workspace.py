"""Register the original brief, source checks, and article assets in the Studio CLI."""
from pathlib import Path
import json
import subprocess
import sys

from prepare import HERE, OUT, ROOT, FIGURES, save

DATE = "2026-11-12"
PROJECT = HERE.name
SLUG = "claude-sheets-whiteboards-interactive-connectors"
SOURCE_ROWS = {
    "official-artifacts": ("Artifacts公式発表", "https://claude.com/resources/articles/sheets-whiteboards-data"),
    "official-apps": ("外部アプリの公式発表", "https://claude.com/resources/articles/interactive-connectors-full-tool"),
    "sheets-help": ("Claude Sheets公式ヘルプ", "https://support.claude.com/en/articles/18324300-get-started-with-claude-sheets"),
    "whiteboards-help": ("Claude Whiteboards公式ヘルプ", "https://support.claude.com/en/articles/18324319-get-started-with-claude-whiteboards"),
    "data-help": ("Claude Data公式ヘルプ", "https://support.claude.com/en/articles/17454700-get-started-with-claude-data"),
    "admin-help": ("Artifacts管理者ガイド", "https://support.claude.com/en/articles/16994751-artifacts-admin-guide-for-team-and-enterprise-plans"),
    "connectors-help": ("インタラクティブコネクタ公式ヘルプ", "https://support.claude.com/en/articles/13454812-use-interactive-connectors-in-claude"),
    "terms": ("コネクタの利用条件と権限", "https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities"),
    "demo": ("Your apps have moved into Claude", "https://www.youtube.com/watch?v=Gy1jSeSzAhk"),
}


def read(path):
    return path.read_text(encoding="utf-8")


def cli(command, body=None, **kwargs):
    args = [sys.executable, "-X", "utf8", "-m", "tools.studio.content_workspace", command,
            "--workspace", str(ROOT)]
    for key, value in kwargs.items():
        args.extend(["--" + key.replace("_", "-"), str(value)])
    if body:
        folder = OUT / "workspace-operations"
        folder.mkdir(exist_ok=True)
        path = folder / (body["operation_id"] + ".json")
        save(path, body)
        args.extend(["--input", str(path)])
    completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def main():
    request = "\n".join(line[2:] if line.startswith("> ") else ""
                        for line in read(HERE / "PROPOSAL_JA.md").splitlines()
                        if line == ">" or line.startswith("> "))
    story = json.loads(read(HERE / "story-v01.json"))
    manifest = json.loads(read(FIGURES / "manifest.json"))
    if any(p["content_project_id"] == PROJECT for p in cli("list")["items"]):
        state = cli("get", project_id=PROJECT)
    else:
        state = cli("create", dict(operation_id="nov10-claude-create-v01", content_project_id=PROJECT,
                    title="Claudeで企画から予算表へ。11月10日の外部アプリ新機能", topic=request,
                    format="short_and_full"))

    def apply(action, ident, **data):
        nonlocal state
        key = f"{action}-{ident}"
        receipt = OUT / "workspace-operations" / f"{key}-applied.json"
        if receipt.exists():
            return
        state = cli("apply", dict(operation_id=key, expected_revision=state["project"]["revision"], data=data),
                    project_id=PROJECT, action=action)
        save(receipt, {"revision": state["project"]["revision"]})

    sources = []
    for source_id, (title, url) in SOURCE_ROWS.items():
        source = dict(source_id=source_id, title=title, url=url, kind="official", checked_at=DATE)
        if source_id in ("official-artifacts", "official-apps"):
            source.update(published_at="2026-11-10", event_at="2026-11-10")
        sources.append(source)
    apply("research", "nov10-v01", research_id="nov10-v01", checked_at=DATE, sources=sources,
          summary="11月10日の2発表と公式ヘルプを照合。日本語Web版でボード、Sheetsの再計算と出力、コネクタ検索を確認。")

    for item in manifest:
        ident = item["id"]
        data = dict(asset_id=ident, path=(OUT / item["path"]).relative_to(ROOT).as_posix(),
                    width=item["pixels"][0], height=item["pixels"][1], sha256=item["sha256"],
                    privacy_review="passed", visibility="public", alt=item["description"],
                    user_approved_for_blog=False)
        if item["source_id"] == "claude-ui":
            data.update(kind="demonstration_capture", fictional_materials_only=True,
                        caption=f"Claude 日本語Web版、{DATE}撮影。{item['description']}。")
        else:
            source_id = "demo" if ident == "confluence" else item["source_id"]
            data.update(kind="official_capture", source_url=SOURCE_ROWS[source_id][1],
                        source_checked_at=DATE, blog_usage_review="passed",
                        caption=f"Anthropic公式資料、{DATE}確認。{item['description']}。")
        apply("asset", ident, **data)

    common = dict(checked_at=DATE, app="Google Chrome / Windows",
                  login_state="ログイン済みの日本語Web版",
                  save_result="outputs配下のcaptures/originalとfiguresに保存。切り出しは台帳で追跡。",
                  legibility="撮影原本2559px。小さい項目名と数値は字幕・本文に再掲。")
    apply("capture", "artifact-demo-v01", inspection_id="artifact-demo", target_feature="WhiteboardsとSheets",
          status="captured", route="Artifactsのホワイトボード。別の新規チャットからSheets。",
          result="7要素のボード、数量40から45、合計67,250円、残額2,750円、Excelの式と保存値を確認。",
          feature_entry="Artifactsのホワイトボード／スプレッドシート",
          display_result="予算表と式、エクスポート画面、企画ボード",
          shots=[dict(shot_id=key, asset_id=key, purpose=key) for key in
                 ("board", "sheet-before", "sheet-after", "excel-menu")], **common)
    apply("capture", "connector-demo-v01", inspection_id="connector-demo", target_feature="インタラクティブコネクタ",
          status="captured", route="カスタマイズ → コネクタ → おすすめ。既存接続Vercelをチャットで呼び出し。",
          result="Vercelの公開資料検索を1回許可。結果はテキスト。公式デモのConfluence並列表示を引用。",
          feature_entry="おすすめのインタラクティブコネクタ",
          display_result="接続一覧、検索許可画面、検索のテキスト結果",
          shots=[dict(shot_id=key, asset_id=key, purpose=key) for key in
                 ("directory", "vercel-permission", "vercel-result")], **common)
    apply("capture", "data-entry-v01", inspection_id="data-entry", target_feature="Claude Dataの入口",
          status="available", route="Artifacts → データのタイルを確認。",
          result="入口を表示。接続先でのデータ取得・可視化は未検証。",
          feature_entry="Artifactsのデータ", display_result="タイルを確認",
          shots=[], **{**common, "save_result": "接続済みダッシュボードの撮影は未取得。"})

    entries = []
    for kind, overview, duration in [
        ("short", "数量を変えた再計算、企画ボード、外部アプリを1分弱で紹介。", 55),
        ("full", "企画、表、Excel、Claude Data、組織設定、外部アプリの順に解説。", 230),
    ]:
        entries.append(dict(episode_id=f"nov10-{kind}", title=story["titles"][kind], overview=overview,
            intended_message="企画の整理と予算表、実績データの集計、既存アプリの資料に用途ごとの入口がある。",
            demo_idea="架空の試食会。Whiteboardsで工程を整理し、別チャットのSheetsで数量を編集。",
            article_role="入力値、式、公式情報、実演画像を手元で確認できるようにする。",
            duration_seconds=duration, capture_inspection_id="artifact-demo"))
    apply("proposal", "nov10-v01", proposal_id="nov10-v01", episodes=entries,
          count_reason="制作依頼に指定されたショートとフルの2本。", production_candidate="story-v01.json")
    apply("feedback", "request-v01", feedback_id="request-v01", proposal_id="nov10-v01",
          kind="comment", text=request, interpretation="制作指示としてv01へ反映。レビュー後の採用は確認待ち。")

    apply("claim", "recalculation", claim_id="recalculation", basis="tested", checked_at=DATE,
          text="B3を40から45にすると、合計64,000円から67,250円、残額6,000円から2,750円。",
          source_ids=["sheets-help"], asset_ids=["sheet-before", "sheet-after", "excel-menu"],
          test_conditions="11月12日の日本語Web版、架空イベント。Excel保存値はOOXMLと独立計算で照合。")
    apply("claim", "search-only", claim_id="search-only", basis="tested", checked_at=DATE,
          text="既存接続のVercelで公開資料検索を1回実行。結果はテキスト。",
          source_ids=["connectors-help"], asset_ids=["vercel-permission", "vercel-result"],
          test_conditions="公開資料「Preview Deployments」の検索のみ。")
    apply("claim", "separate-data", claim_id="separate-data", basis="official", checked_at=DATE,
          text="Claude Dataは別途データ接続が必要。Claude Sheetsのライブデータを直接利用する機能は非対応。",
          source_ids=["data-help", "sheets-help"], asset_ids=[])
    apply("article", "nov10-v01", version="v01", slug=SLUG, destination="benriworks/blog", published=False,
          draft_path=(HERE / "article-draft-v01.md").relative_to(ROOT).as_posix(), sections=[
              dict(section_id="overview", title="11月10日に加わった機能", source_ids=["official-artifacts", "official-apps"],
                   asset_ids=["official-artifacts", "official-apps"]),
              dict(section_id="budget", title="WhiteboardsとSheetsの実演", source_ids=["whiteboards-help", "sheets-help"],
                   claim_ids=["recalculation"], asset_ids=["board", "sheet-before", "sheet-after", "excel-menu"]),
              dict(section_id="data", title="Claude Dataのデータ接続", source_ids=["data-help", "admin-help"],
                   claim_ids=["separate-data"]),
              dict(section_id="apps", title="Claudeの横で対応アプリを開く", source_ids=["official-apps", "connectors-help", "demo", "terms"],
                   claim_ids=["search-only"], asset_ids=["confluence", "directory", "vercel-permission", "vercel-result"]),
          ])
    save(OUT / "workspace-state-v01.json", state)
    handoff = OUT / "blog-handoff/v01"
    if not handoff.exists():
        cli("export-blog", project_id=PROJECT, handoff_version="v01")
    print(f"{PROJECT}: revision {state['project']['revision']}, blog assets exported")


if __name__ == "__main__":
    main()
