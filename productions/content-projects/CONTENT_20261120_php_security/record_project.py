"""Persist this brief, source set, official crops and article in the common Studio CLI."""
import json
from pathlib import Path
import subprocess
import sys
from capture import HERE, ROOT, OUT, write

PROJECT=HERE.name
SLUG="php-security-november-2026"
DATE="2026-11-20"
REQUEST="新たにPHPの脆弱性が公表されました。前回との違いを結論ファーストで伝えて下さい。いつもの男女キャラクターの冬バージョンでショートとフルの動画を作成して下さい"
CAPTIONS={
    "october":"PHP開発チームが10月21日に呼びかけた緊急更新。告知見出しの抜粋。",
    "conditions":"PHPセキュリティチームが11月18日に示した、Criticalの問題の成立条件。",
    "ipa":"IPAが予告時に示した「一般的ではないセットアップ」という条件の抜粋。",
    "november":"11月19日、PHP開発チームが公開した8.5.13の見出し。",
}
def read(path):return json.loads(path.read_text(encoding="utf-8"))
def cli(operation,payload=None,**options):
    cmd=[sys.executable,"-B","-X","utf8","-m","tools.studio.content_workspace",operation,"--workspace",str(ROOT)]
    for key,value in options.items():cmd.extend(["--"+key.replace("_","-"),str(value)])
    if payload is not None:
        path=OUT/"studio-operations"/(payload["operation_id"]+".json")
        write(path,payload);cmd.extend(["--input",str(path)])
    result=subprocess.run(cmd,cwd=ROOT,capture_output=True,encoding="utf-8")
    if result.returncode:raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)
def main():
    known=any(x["content_project_id"]==PROJECT for x in cli("list")["items"])
    state=cli("get",project_id=PROJECT) if known else cli("create",dict(operation_id="php-nov-create",
        content_project_id=PROJECT,title="PHPの11月更新と10月のPHP2Shell",topic=REQUEST,
        audience="PHPを使うサイトの運営者・更新を委託する担当者",format="short_and_full"))
    def apply(action,key,**data):
        nonlocal state
        op="php-nov-"+key
        receipt=OUT/"studio-operations"/(op+"-applied.json")
        if receipt.exists():return
        state=cli("apply",dict(operation_id=op,expected_revision=state["project"]["revision"],data=data),
                  project_id=PROJECT,action=action)
        write(receipt,{"revision":state["project"]["revision"]})
    sources=read(HERE/"sources.json")
    apply("research","sources",research_id="primary",checked_at=DATE,
        sources=[dict(source_id=k,kind="official",checked_at=DATE,**v) for k,v in sources.items()],
        summary="10月21日と23日、11月18日の条件、19日の公開記録、開発元17告知の公表日と深刻度を照合。")
    apply("capture","chrome",inspection_id="chrome",status="available",checked_at=DATE,
          target_feature="PHPの公式リリースとIPAの事前案内を見比べる",app="ローカルGoogle Chrome",
          login_state="公開画面",feature_entry="公式の公開アーカイブ・IPAの11月19日付ページ",
          route="Playwrightからページ本文の原文を選択",display_result="公表済みの4系列・事前案内の原文を表示",
          result="3箇所のPHP公式原文と1箇所のIPA原文を撮影",save_result="原本3000×1900と測定範囲の抜粋を保存",
          legibility="原文を別枠に拡大し和文要約を配置",shots=[])
    for row in read(OUT/"captures/manifest.json"):
        key=row["id"];path=OUT/"captures/quotes"/(key+".png")
        apply("asset","figure-"+key,asset_id=key,kind="official_capture",visibility="public",privacy_review="passed",
              blog_usage_review="passed",user_approved_for_blog=False,path=path.relative_to(ROOT).as_posix(),
              width=row["quote_pixels"][0],height=row["quote_pixels"][1],sha256=row["quote_sha256"],
              source_url=row["url"],source_checked_at=DATE,alt=CAPTIONS[key],caption=CAPTIONS[key])
    story=read(HERE/"story-v01.json")
    episodes=[dict(episode_id="php-"+k,title=story["titles"][k],overview=desc,
        intended_message="10月適用済みでも、11月分の影響条件・管理先・適用日を確認する。",
        demo_idea="実際の公式告知を撮影し、問い合わせ例と修正版の表を組み合わせる。",
        article_role="時系列、4系列の番号、告知数の根拠と問い合わせ例。",capture_inspection_id="chrome",
        duration_seconds=round(read(OUT/"release/v01"/k/"qc.json")["duration"])) for k,desc in
        (("short","結論と契約先に聞く一言"),("full","前回とのつながり、保存の例、更新元に応じた照合"))]
    apply("proposal","editions",proposal_id="php-nov-v01",episodes=episodes,
          count_reason="ユーザーが冬服の既存男女による縦ショートと横フルを明示。",production_candidate="story-v01.json")
    apply("feedback","brief",feedback_id="brief",proposal_id="php-nov-v01",kind="comment",
          text=REQUEST,interpretation="冬服で前回との差を先に示す2本。完成品採用は別途。")
    sections=[
        ("compare","10月と11月の影響条件",["oct","pre","ipa","api"],["october","conditions","ipa"],"10月は広いWeb環境、11月のCriticalには設定・構成の条件。"),
        ("example","セッションの具体例と前回の別件",["session","progress","follow","manual"],[],"10月23日予告の別件は11月19日に修正。"),
        ("versions","4系列の修正版と確認先",["release","ubuntu","changes"],["november"],"公式配布の4系列と契約先の適用は区別して照合する。")]
    for key,title,sids,aids,note in sections:
        apply("claim","claim-"+key,claim_id=key,basis="official",checked_at=DATE,text=note,source_ids=sids,asset_ids=aids)
    apply("article","draft",version="v01",slug=SLUG,destination="benriworks/blog",published=False,
          draft_path=(HERE/"article-draft-v01.md").relative_to(ROOT).as_posix(),
          sections=[dict(section_id=k,title=t,source_ids=s,asset_ids=a,claim_ids=[k]) for k,t,s,a,_ in sections])
    if not (OUT/"workspace-state-v01.json").exists():
        write(OUT/"workspace-state-v01.json",state)
    if not (OUT/"blog-handoff/v01").exists():
        cli("export-blog",project_id=PROJECT,handoff_version="v01")
    revised=OUT/"release/v02/full/qc.json"
    if revised.is_file():
        episodes[1]=dict(episodes[1],duration_seconds=round(read(revised)["duration"]))
        apply("proposal","full-v02",proposal_id="php-nov-full-v02",episodes=episodes,
              count_reason="ショートv01を維持し、フルの修正版を案内する台詞1本を明瞭化した。",
              production_candidate="full-v02.json")
        write(OUT/"workspace-state-full-v02.json",state)
    print("Studio revision",state["project"]["revision"],"article draft and figures exported")
if __name__=="__main__":main()
