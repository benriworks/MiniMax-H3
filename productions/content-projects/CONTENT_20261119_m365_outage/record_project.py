"""Record the research, editorial scope and article handoff in the common Studio ledger."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PROJECT=HERE.name
DATE="2026-11-19"
REQUEST="次に、新しい動画の制作をお願いします。 先日起きたマイクロソフトの大規模障害の原因を、詳しく教えて下さい。なぜ起きたのかを結論ファーストで述べつつ、人々の困り具合、感想なども交えてください、公式の発表も詳しく引用して下さい。"


def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def record(media):
    workspace=media.parents[2];operations=media/"workspace-operations";operations.mkdir(exist_ok=True)
    def run(operation,body=None,**flags):
        args=[sys.executable,"-X","utf8","-m","tools.studio.content_workspace",operation,"--workspace",str(workspace)]
        for k,val in flags.items():args.extend(["--"+k.replace("_","-"),val])
        if body:
            f=operations/(body["operation_id"]+".json")
            write(f,body);args.extend(["--input",str(f)])
        res=subprocess.run(args,cwd=workspace,capture_output=True,encoding="utf-8")
        if res.returncode: raise ValueError((res.stdout or res.stderr)[-1200:])
        return json.loads(res.stdout)

    rows=run("list")["items"]
    if any(x["content_project_id"]==PROJECT for x in rows):
        state=run("get",project_id=PROJECT)
    else:
        state=run("create",dict(content_project_id=PROJECT,operation_id="m365-create",title="Microsoft 365 障害の原因と利用現場",topic=REQUEST,audience="OutlookやTeamsを仕事、学校で利用する人",format="full"))
    def apply(action,id,**data):
        nonlocal state
        op=f"m365-{action}-{id}"
        receipt=operations/(op+"-applied.json")
        if receipt.exists():return
        pending=operations/(op+".json")
        body=json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else dict(operation_id=op,expected_revision=state["project"]["revision"],data=data)
        state=run("apply",body,project_id=PROJECT,action=action);write(receipt,{"revision":state["project"]["revision"]})

    sources=json.loads((HERE/"sources.json").read_text(encoding="utf-8"))
    apply("research","first",research_id="november-report",checked_at=DATE,summary="11月15日付暫定PIR、Microsoft経過通知、大学の告知、仏紙の当事者取材を照合。",sources=[dict(source_id=k.lower(),title=row[0],url=row[1],kind=row[2],checked_at=DATE) for k,row in sources.items()])
    samples=[("meiji","meiji","入試の緊急連絡を電話で受け付ける案内"),("rits","rits","予約を再度行う必要はないという案内"),("osaka","osaka","講義URLをOutlook復旧後に送る案内"),("report-lock-0","pir","接続処理のロック競合の短い原文")]
    for name,source,alt in samples:
        asset=media/"captures"/(name+".png")
        apply("asset",name,asset_id=name,path=asset.relative_to(workspace).as_posix(),kind="official_capture",visibility="public",
              privacy_review="passed",blog_usage_review="passed",user_approved_for_blog=False,source_url=sources[source.upper()][1],source_checked_at=DATE,alt=alt,caption=alt)
    apply("capture","archived",inspection_id="archived-status",target_feature="過去の障害の管理者記録を確認する",status="blocked",checked_at=DATE,
          app="Windows / Chrome",login_state="テナント管理者向けURLはサインイン要求",feature_entry="サービス正常性の障害ID",
          route="公開ステータス→管理者向け障害詳細を直接確認",display_result="公開ステータスは表示、管理者用詳細はサインイン画面",result="当日の障害画面の実演には使用しない",
          save_result="公開ステータスの調査用原本と、第三者公開のMicrosoft原文・大学告知の公開用切り出しを保存",legibility="使用した資料の抜粋を実フレームで確認",shots=[])
    apply("proposal","full",proposal_id="full-v01",count_reason="三要因、連鎖、生活への影響、復旧を追える詳しい横動画1本。",episodes=[dict(episode_id="full",title="なぜOutlookの受信箱が開かなかった？",overview="現場の事例と公式の原因、復旧時間",intended_message="三要因が重なり入口の応答停止が連鎖した。",demo_idea="公式文書の抜粋、大学告知、二つの通信経路の図",article_role="出典リンク、時刻表、各大学の案内",duration_seconds=304,capture_inspection_id="archived-status")])
    apply("feedback","request",feedback_id="actual-request",proposal_id="full-v01",kind="comment",text=REQUEST,interpretation="結論先行と原因・実際の声・公式引用を指定。成果物採用の返答は未受領。")
    claims=[("causes","三条件が重なって障害が拡大した。",["pir","evp"],["report-lock-0"]),("school","国内の大学が電話窓口、申し込みの扱いを案内した。",["meiji","rits"],["meiji","rits"]),("time","公式の影響区間は日本時間11月13日01:20から14日01:10。",["pir","feed"],[])]
    for id,claim,refs,assets in claims:
        apply("claim",id,claim_id=id,text=claim,basis="official",checked_at=DATE,source_ids=refs,asset_ids=assets)
    sections=[dict(section_id=i,title=t,source_ids=r,asset_ids=a,claim_ids=[i]) for i,t,r,a in claims]
    sections.append(dict(section_id="paris",title="パリの広報担当者の経験",source_ids=["lemonde"],asset_ids=[],claim_ids=[]))
    apply("article","outline",version="v01",destination="benriworks/blog",slug="microsoft-365-outage-november-2026",published=False,sections=sections)
    write(media/"workspace-state-v01.json",state)
    print(PROJECT,"revision",state["project"]["revision"],"research",len(state["project"]["research"][0]["sources"]), "claims",len(state["project"]["claims"]))


if __name__=="__main__":
    arg=argparse.ArgumentParser();arg.add_argument("media",type=Path);record(arg.parse_args().media.resolve())
