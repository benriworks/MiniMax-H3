"""Record the brief, verified sources, and six article figures through the Studio CLI."""
from pathlib import Path
import json
import subprocess
import sys

from prepare import HERE, ROOT, OUT, SOURCES, FIGURES, save

DATE = SOURCES["checked_at"]
PROJECT = HERE.name
SLUG = "claude-meetings-code-mode-20261113"


def read(path):
    return path.read_text(encoding="utf-8")


def cli(operation, body=None, **options):
    command = [sys.executable, "-B", "-X", "utf8", "-m", "tools.studio.content_workspace", operation,
               "--workspace", str(ROOT)]
    for key, value in options.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    if body is not None:
        operations = OUT / "workspace-operations"
        operations.mkdir(exist_ok=True)
        path = operations / f"{body['operation_id']}.json"
        save(path, body)
        command.extend(["--input", str(path)])
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        raise RuntimeError(done.stderr.strip() or done.stdout.strip())
    return json.loads(done.stdout)


def main():
    proposal = read(HERE / "PROPOSAL_JA.md")
    original, additional = proposal.split("## 制作依頼の原文\n", 1)[1].split("## 追加指定の原文\n")
    decode_quote = lambda text: "\n".join(line[2:] if line.startswith("> ") else ""
                                      for line in text.splitlines() if line == ">" or line.startswith("> "))
    story = json.loads(read(HERE / "story-v01.json"))
    figures = json.loads(read(FIGURES / "manifest.json"))
    if any(row["content_project_id"] == PROJECT for row in cli("list")["items"]):
        state = cli("get", project_id=PROJECT)
    else:
        state = cli("create", dict(operation_id="meetings-news-create-v01",
                    content_project_id=PROJECT, title="Claude MeetingsとCode Mode｜AIニュース11月13日",
                    topic=decode_quote(original), format="short_and_full"))

    def apply(action, identifier, **data):
        nonlocal state
        key = action + "-" + identifier
        receipt = OUT / "workspace-operations" / f"{key}-applied.json"
        if not receipt.exists():
            state = cli("apply", dict(operation_id=key, expected_revision=state["project"]["revision"],
                                       data=data), project_id=PROJECT, action=action)
            save(receipt, {"revision": state["project"]["revision"]})

    apply("research", "primary-v01", research_id="primary-v01", checked_at=DATE, sources=[
        dict(source_id=key, kind="official", checked_at=DATE, **data)
        for key, data in SOURCES["sources"].items()],
          summary="Claude Meetingsの公式画像3点とヘルプ、Code Modeのモデル・環境要件、同日のOpenAI発表を照合。")

    for ident, feature, route, result in [
        ("meetings-pc", "日本語PCでClaude Meetingsを確認", "Claude Desktopを確認。Chromeで公式ヘルプの会議入口。",
         "Desktopは描画が黒く確認できず、Chromeセッションは現在URLを確定できずに停止。"),
        ("code-local", "Claude CodeのCode Mode", "このPCでclaude --versionを実行。",
         "現在の2.1.316は公式要件2.1.323以降を満たさない。")]:
        apply("capture", ident, inspection_id=ident, target_feature=feature, status="blocked",
              checked_at=DATE, app="Windows / Claude", login_state="機能へのアクセス未確認",
              feature_entry=feature, display_result=result, save_result="実演原本なし。公式の引用素材を別途保存。",
              legibility="公式の原画像は1920〜3840px幅。公式ページの撮影は1600px幅。",
              route=route, result=result, shots=[])

    for item in figures:
        apply("asset", item["id"], asset_id=item["id"], kind="official_capture", visibility="public",
              privacy_review="passed", blog_usage_review="passed", user_approved_for_blog=False,
              path=(OUT / item["path"]).relative_to(ROOT).as_posix(), sha256=item["sha256"],
              width=item["pixels"][0], height=item["pixels"][1], source_url=item["source_url"],
              source_checked_at=DATE, alt=item["alt"], caption=item["caption"])

    episodes = [
        dict(episode_id=f"news-{kind}", title=story["titles"][kind], overview=summary,
             intended_message="会議中に資料を作り、議事録と同じ場所から次の作業につなげる。",
             demo_idea="イベント会議の公式3画面と、Code Modeの操作模式図で説明。",
             article_role="設定、共有、料金、モデル条件と、模擬会議の検証手順を補足。",
             capture_inspection_id="meetings-pc", duration_seconds=seconds)
        for kind, summary, seconds in [
            ("short", "会議中のホワイトボード、議事録、Code Modeの要点。", 68),
            ("full", "会議前・中・後、組織設定とCode Modeの比較、OpenAIの同日更新。", 295)]]
    apply("proposal", "news-v01", proposal_id="news-v01", count_reason="依頼で指定されたショートとフル。",
          episodes=episodes, production_candidate="story-v01.json")
    for key, response, interpretation in [
        ("original-request", decode_quote(original), "Meetingsを主題に、Code Modeを補足にする2本を制作。"),
        ("local-bgm", decode_quote(additional), "ローカル曲庫の明るいハッピータイムを縦横のレビュー候補で使用。")]:
        apply("feedback", key, feedback_id=key, proposal_id="news-v01", kind="comment",
              text=response, interpretation=interpretation)

    sections = [
        ("meeting", "会議への参加・ボード・会議後の資料", ["launch", "help"],
         ["participant", "meeting-plan", "meeting-page", "launch-screen", "help-screen"],
         "Claude Meetingsは会議参加中にボードを作り、終了後は文字起こし、要約と資料が会議ページに残る。"),
        ("code", "Code Modeの仕組みと条件", ["code-guide", "code-release"], ["code-screen"],
         "既定無効の実験機能。v2.1.323以降の対応する対話型ターミナルで複数ツールをJavaScriptから呼ぶ。"),
        ("other", "OpenAIの同日更新", ["wallet", "codex"], [],
         "ChatGPT Walletは米国の対象Pro。Codex CLI 0.169.0も11月13日付で更新。"),
    ]
    for sid, title, sources, assets, claim in sections:
        apply("claim", sid, claim_id=sid, basis="official", checked_at=DATE, text=claim,
              source_ids=sources, asset_ids=assets)
    apply("article", "v01", version="v01", slug=SLUG, destination="benriworks/blog", published=False,
          draft_path=(HERE / "article-draft-v01.md").relative_to(ROOT).as_posix(), sections=[
              dict(section_id=sid,title=title,source_ids=sources,asset_ids=assets,claim_ids=[sid])
              for sid,title,sources,assets,_ in sections])

    save(OUT / "workspace-state-v01.json", state)
    if not (OUT / "blog-handoff/v01").exists():
        cli("export-blog", project_id=PROJECT, handoff_version="v01")
    print(f"Studio revision {state['project']['revision']}. Exported six figures.")


if __name__ == "__main__":
    main()
