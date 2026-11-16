"""Register the user brief, publication sources, and article figures in Studio."""
import json
import subprocess
import sys

from prepare import HERE, ROOT, OUT, SOURCES, FIGURES, save

DATE = SOURCES["checked_at"]
PROJECT = HERE.name
SLUG = "claude-japan-ai-usage-20261117"


def read(path):
    return path.read_text(encoding="utf-8")


def cli(operation, body=None, **options):
    command = [sys.executable, "-B", "-X", "utf8", "-m", "tools.studio.content_workspace",
               operation, "--workspace", str(ROOT)]
    for key, value in options.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    if body is not None:
        folder = OUT / "workspace-operations"
        folder.mkdir(exist_ok=True)
        path = folder / f"{body['operation_id']}.json"
        save(path, body)
        command.extend(["--input", str(path)])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def main():
    brief = read(HERE / "PROPOSAL_JA.md").split("## 依頼の反映", 1)[0]
    user_request = "\n".join(line[2:] for line in brief.splitlines() if line.startswith("> "))
    story = json.loads(read(HERE / "story-v01.json"))
    index = cli("list")["items"]
    if any(row["content_project_id"] == PROJECT for row in index):
        state = cli("get", project_id=PROJECT)
    else:
        state = cli("create", dict(operation_id="japan-ai-create-v01", content_project_id=PROJECT,
                    title="日本のClaude利用と職場｜2026年11月17日", topic=user_request, format="short_and_full"))

    def apply(action, identifier, **data):
        nonlocal state
        key = action + "-" + identifier
        receipt = OUT / "workspace-operations" / f"{key}-applied.json"
        if not receipt.exists():
            state = cli("apply", dict(operation_id=key, expected_revision=state["project"]["revision"],
                                       data=data), project_id=PROJECT, action=action)
            save(receipt, {"revision": state["project"]["revision"]})

    apply("research", "primary-v01", research_id="primary-v01", checked_at=DATE,
          sources=[dict(source_id=key, kind="official", checked_at=DATE, **item)
                   for key, item in SOURCES["sources"].items()],
          summary="公式の国別画面・世界地図、121地域の公開値、AWS別調査、実演の入力と出力を照合。")

    apply("capture", "desktop", inspection_id="desktop", status="blocked", checked_at=DATE,
          target_feature="Claude Desktopのチャット", app="Claude Desktop", login_state="画面描画を確認できず",
          feature_entry="起動済みのClaudeウィンドウ", route="Computer Useで表示を取得",
          display_result="白いウィンドウで入力欄を確認できなかった", result="Claude Codeへ切り替えた",
          save_result="Desktopの操作画像は採用せず", legibility="入力欄と出力を読み取れない", shots=[])
    apply("capture", "local-demo", inspection_id="local-demo", status="available", checked_at=DATE,
          target_feature="架空の会議メモから作業表を作る", app="Claude Code 2.1.316",
          login_state="このPCで既存接続を確認", feature_entry="一度のclaude -p実行",
          route="顧客情報のない架空メモをCLIから入力",
          display_result="Claude Haiku 5.5が決定事項と作業3件の表を返した",
          result="制作担当・11月20日、購買担当・未定、次回会議日と締切を照合",
          save_result="実行レシート・入力・応答全文を保存。動画は実際の出力表を組版",
          legibility="公開草稿はテキストと映像の拡大表で確認", shots=[])

    figures = json.loads(read(FIGURES / "manifest.json"))
    for item in figures:
        apply("asset", item["id"], asset_id=item["id"], kind="official_capture", visibility="public",
              privacy_review="passed", blog_usage_review="passed", user_approved_for_blog=False,
              path=(OUT / item["path"]).relative_to(ROOT).as_posix(), sha256=item["sha256"],
              width=item["pixels"][0], height=item["pixels"][1], source_url=item["source_url"],
              source_checked_at=DATE, alt=item["alt"], caption=item["caption"])

    editions = {"short": "v01", "full": "v02"}
    episodes = [
        dict(episode_id=f"japan-ai-{kind}", title=title, overview=overview,
             intended_message="32位はClaudeの会話量の比較。職場では定例の1作業から検証する。",
             demo_idea="架空の会議メモから担当・期限の表を作り、原文と照合する。",
             article_role="データの分母、一次出典、実演の入出力、職場で試す手順。",
             capture_inspection_id="local-demo", duration_seconds=round(
                 json.loads(read(OUT / "release" / editions[kind] / kind / "qc.json"))["duration"]))
        for (kind, title), overview in zip(story["titles"].items(),
            ("指数の意味と最初の業務例", "公式図・企業調査・実演・チームの試行"), strict=True)]
    apply("proposal", "japan-ai-v01", proposal_id="japan-ai-v01",
          count_reason="依頼で指定されたショート・フルの2本。", episodes=episodes,
          production_candidate="story-v01.json")
    apply("feedback", "request", feedback_id="request", proposal_id="japan-ai-v01", kind="comment",
          text=user_request, interpretation="既存の男女で、Anthropicの指標と職場での活用を伝える2本を作成。")

    sections = [
        ("index", "国別の指数と4区分", ["country", "map", "docs", "data"], ["country", "map", "country-full"],
         "2026年5月のClaude会話データの人口比指数で日本は32位 / 121、1.91、Upper middle。"),
        ("aws", "国内企業でのAI導入", ["aws"], ["aws-points"],
         "AWS委託調査は日本企業のAI導入54％、導入済み企業の基礎的活用60％。"),
    ]
    for identifier, _, sources, assets, note in sections:
        apply("claim", identifier, claim_id=identifier, basis="official", checked_at=DATE, text=note,
              source_ids=sources, asset_ids=assets)
    apply("article", "v01", version="v01", slug=SLUG, destination="benriworks/blog", published=False,
          draft_path=(HERE / "article-draft-v01.md").relative_to(ROOT).as_posix(),
          sections=[dict(section_id=sid, title=title, source_ids=sources, asset_ids=assets, claim_ids=[sid])
                    for sid, title, sources, assets, _ in sections] + [
                    dict(section_id="work-demo", title="架空の会議メモ実演とチームの試行",
                         source_ids=["meti"], asset_ids=[], claim_ids=[])])
    save(OUT / "workspace-state-v01.json", state)
    if not (OUT / "blog-handoff/v01").exists():
        cli("export-blog", project_id=PROJECT, handoff_version="v01")
    print(f"Studio revision {state['project']['revision']}: {state['project']['phase']}")


if __name__ == "__main__":
    main()
