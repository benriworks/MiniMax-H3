"""Record the requested scope, primary sources and frozen assets through the shared Studio CLI."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
PROJECT = HERE.name
OUT = ROOT / "outputs/content-projects" / PROJECT
DATE = "2026-11-10"

SOURCES = [
    ("launch", "Claude Fable 5.2 and Mythos 5.2", "https://www.anthropic.com/claude-fable-and-mythos-5-2"),
    ("fable-spec", "Claude Fable 5.2", "https://platform.claude.com/docs/en/models/fable-5-2/overview"),
    ("fable-previous", "Claude Fable 5.1", "https://platform.claude.com/docs/en/models/fable-5-1/overview"),
    ("system-card", "Fable 5.2 and Mythos 5.2 System Card", "https://www.anthropic.com/document/claude-fable-5-2-mythos-5-2-system-card"),
    ("briefcase", "Announcing AA-Briefcase", "https://artificialanalysis.ai/articles/aa-briefcase/"),
    ("sol-launch", "Introducing GPT-6.1 Sol", "https://openai.com/index/introducing-gpt-6-1-sol/"),
    ("sol-docs", "GPT-6.1 Sol", "https://developers.openai.com/api/docs/models/gpt-6.1-sol"),
    ("openai-models", "OpenAI API Models", "https://developers.openai.com/api/docs/models"),
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def cli(command, body=None, **options):
    args = [sys.executable, "-X", "utf8", "-m", "tools.studio.content_workspace", command,
            "--workspace", str(ROOT)]
    for name, value in options.items():
        args.extend(["--"+name.replace("_", "-"), str(value)])
    if body is not None:
        path = OUT/"workspace-operations"/(body["operation_id"]+".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, body)
        args.extend(["--input", str(path)])
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main():
    story = read(HERE/"story-v01.json")
    capture = read(OUT/"captures-v02/manifest.json")
    raw_request = "\n".join(line.removeprefix("> ") for line in
                            (HERE/"PROPOSAL_JA.md").read_text(encoding="utf-8-sig").splitlines()
                            if line.startswith("> "))
    listing = cli("list")["items"]
    if any(item["content_project_id"] == PROJECT for item in listing):
        state = cli("get", project_id=PROJECT)
    else:
        state = cli("create", dict(operation_id="create-fable52-v01", content_project_id=PROJECT,
                                  title="Claude Fable 5.2の公式9グラフとOpenAIへの期待",
                                  topic=raw_request, format="short_and_full"))

    def apply(action, identifier, data):
        nonlocal state
        key = action+"-"+identifier
        path = OUT/"workspace-operations"/(key+"-applied.json")
        if path.exists():
            return
        state = cli("apply", dict(operation_id=key, expected_revision=state["project"]["revision"],
                                  data=data), project_id=PROJECT, action=action)
        write(path, dict(revision=state["project"]["revision"]))

    apply("research", "v01", dict(research_id="research-v01", checked_at=DATE,
          summary="Anthropic共同発表本文の全9グラフを確定。Claude PlatformとOpenAIの公開モデルを照合。Sol 6.2は仮の呼称として扱う。",
          sources=[dict(source_id=key, title=title, url=url, kind="official", checked_at=DATE)
                   for key, title, url in SOURCES]))
    apply("capture", "desktop-v01", dict(inspection_id="claude-desktop", target_feature="Fable 5.2のモデル選択",
          status="blocked", checked_at=DATE, route="WindowsのClaudeとChromeをComputer Useで確認",
          result="Claudeは再サインインを表示。Chromeは現在URLの特定不可でComputer Use停止。",
          app="Claude Desktop / Chrome", login_state="デスクトップで再サインインを要求",
          feature_entry="モデル選択", display_result="モデル選択の公開用撮影は未取得",
          save_result="個人の会話を含むデスクトップ画像は保存対象外", legibility="デスクトップは未評価", shots=[]))
    apply("capture", "official-v01", dict(inspection_id="official-launch", target_feature="発表本文に掲載された性能・実験・安全評価の図",
          status="available", checked_at=DATE, route="公開URLをWindowsの分離Chromiumで取得し、各タブを表示",
          result="9図と比較表を原本と引用用に保存", app="Playwright Chromium",
          login_state="公開ページ", feature_entry=SOURCES[0][2], display_result="図の軸、凡例、タイトル、比較表を確認",
          save_result="captures-v02/manifest.json", legibility="図の引用元幅1889px。小さいラベルを記事で拡大可能。", shots=[]))
    episodes = []
    for kind, overview, role, seconds in [
        ("short", "API単価と公式9図の要点、次のSolに期待すること。", "グラフの拡大と評価条件を補う。", 82),
        ("full", "公式9図と比較表、図表読解の実演、OpenAIの現在と期待。", "再現手順、価格の計算例、出典を残す。", 330),
    ]:
        episodes.append(dict(episode_id=f"fable52-{kind}", title=story["titles"][kind], overview=overview,
            duration_seconds=seconds, intended_message="推論設定、成果、1件あたりの費用を関連づける。",
            demo_idea="架空グラフ1枚のClaude Code実行結果と、公式ベンチマークを区別。",
            article_role=role, capture_inspection_id="official-launch"))
    apply("proposal", "v01", dict(proposal_id="proposal-v01", count_reason="制作依頼で指定されたショートとフルの2本。",
          episodes=episodes, production_candidate="story-v01.json"))
    apply("feedback", "original-request", dict(feedback_id="original-request", proposal_id="proposal-v01",
          kind="comment", text=raw_request,
          interpretation="制作範囲を指定する依頼として反映。v01を制作候補とし、レビュー後の採用状態は別に保持する。"))
    for item in capture["assets"]:
        identifier = item["id"]
        operation = identifier+"-headers-v02" if identifier == "benchmark-table" and item.get("columns") else identifier
        apply("asset", operation, dict(asset_id=identifier, kind="official_capture",
              path=(OUT/item["excerpt"]["path"]).relative_to(ROOT).as_posix(),
              visibility="public", privacy_review="passed", source_url=item["url"], source_checked_at=DATE,
              context="公開元ページの引用候補。記事と動画の公開判断は別管理。"))
    for identifier, data in story["graphs"].items():
        apply("claim", identifier, dict(claim_id=identifier, basis="official", checked_at=DATE,
              source_ids=["launch"], asset_ids=[identifier], text=f"{data['label']}　{data['value']}　{data['condition']}。{data['detail']}"))
    apply("claim", "sol-hope", dict(claim_id="sol-hope", basis="hypothesis", checked_at=DATE,
          source_ids=["sol-launch", "openai-models"], asset_ids=[],
          text="Sol 6.2は次のSolを想定した呼称。完了率、時間、費用、根拠、影響のある操作前の確認に期待する。"))
    apply("article", "v01-final-figures", dict(version="v01", draft_path=(HERE/"article-draft-v01.md").relative_to(ROOT).as_posix(),
          sections=[
              dict(section_id="graphs", title="公式9図の読み方", source_ids=["launch","system-card","briefcase"],
                   claim_ids=list(story["graphs"]), asset_ids=list(story["graphs"])+["benchmark-table"]),
              dict(section_id="price", title="標準単価と1件あたりの費用", source_ids=["fable-spec","fable-previous"]),
              dict(section_id="next-sol", title="次のSolへの期待", source_ids=["sol-launch","openai-models"],
                   claim_ids=["sol-hope"], asset_ids=["sol-docs"]),
          ]))
    state = cli("get", project_id=PROJECT)
    write(OUT/"workspace-state-v01.json", state)
    print(json.dumps(dict(project=PROJECT, revision=state["project"]["revision"],
                          phase=state["project"]["phase"], assets=len(state["project"]["assets"])), ensure_ascii=False))


if __name__ == "__main__":
    main()
