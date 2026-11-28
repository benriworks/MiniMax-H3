"""Record the chat brief, scoped user request, observed evidence, and private article state."""
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image

HERE=Path(__file__).resolve().parent
PROJECT=HERE.name
DATE="2026-11-25"
REQUEST="チャット欄にGpt-6.2が来たので、それを解説するショートとフル動画を作成してください。いつものキャラクターの冬服バージョン、音声にはGemini3.8の使用をお願いします"
RELEASE="https://help.openai.com/en/articles/6825453-chatgpt-release-notes"
PREVIOUS="https://openai.com/index/introducing-gpt-6-2-astra-sol/"
def run(media):
    workspace=media.parents[2]
    log=media/"workspace-operations";log.mkdir(exist_ok=True)
    def cli(command,body=None,**fields):
        cmd=[sys.executable,"-X","utf8","-m","tools.studio.content_workspace",command,"--workspace",str(workspace)]
        for k,v in fields.items():cmd+=["--"+k.replace("_","-"),v]
        if body:
            file=log/(body["operation_id"]+".json")
            file.write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding="utf-8")
            cmd+=["--input",str(file)]
        p=subprocess.run(cmd,cwd=HERE.parents[2],capture_output=True,encoding="utf-8")
        if p.returncode: raise RuntimeError(p.stdout or p.stderr)
        return json.loads(p.stdout)
    if any(p["content_project_id"]==PROJECT for p in cli("list")["items"]):
        state=cli("get",project_id=PROJECT)
    else:
        state=cli("create",dict(operation_id="winter62-create",content_project_id=PROJECT,title="ChatGPTのGPT-6.2を宿の料金表で試す",topic=REQUEST,format="short_and_full"))
    def apply(action,key,**data):
        nonlocal state
        op="winter62-"+action+"-"+key
        receipt=log/(op+"-ok.json")
        if receipt.exists():return
        pending=log/(op+".json")
        body=json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else dict(operation_id=op,expected_revision=state["project"]["revision"],data=data)
        state=cli("apply",body,project_id=PROJECT,action=action)
        receipt.write_text(json.dumps({"revision":state["project"]["revision"]}),encoding="utf-8")
    apply("research","release",research_id="release",summary="11月23日のChat向けSol、画像理解と指示追従の公式評価を確認。架空の宿を実際のChatで比較した。",checked_at=DATE,
          sources=[dict(source_id=k,title=t,url=url,kind="official",checked_at=DATE) for k,t,url in [("release","11月23日 ChatGPT release notes",RELEASE),("previous","11月17日 Astra and Sol",PREVIOUS)]])
    import hashlib
    asset_rows=[("picker","picker.png","ChatタブのGPT-6.2モデル選択",False),("answer","answer.png","返信に示された朝食込み2泊の合計",False),("followup","followup.png","徒歩5分で該当なしとした実際の返信",False),("release-head","release.png","OpenAIの11月23日付の発表見出し",True)]
    for key,file,alt,official in asset_rows:
        path=media/"captures/figures"/file
        params=dict(source_url=RELEASE,source_checked_at=DATE) if official else dict(fictional_materials_only=True)
        width,height=Image.open(path).size
        apply("asset",key,asset_id=key,path=path.relative_to(workspace).as_posix(),kind="official_capture" if official else "demonstration_capture",visibility="public",
              privacy_review="passed",blog_usage_review="passed",user_approved_for_blog=False,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),width=width,height=height,alt=alt,caption=alt,**params)
    apply("capture","real-chat-v2",inspection_id="real-chat",target_feature="ChatタブでGPT-6.2を選び画像を比較",status="captured",checked_at=DATE,
          app="Chrome／ChatGPT Web版",login_state="ログイン済み",route="ホーム→Chat→現在のモード→モデル名→GPT-6.2→一時チャット",
          feature_entry="モデル選択・入力欄の添付",display_result="6.2 Instant。料金表に対する初回と追加条件への返信",result="保存した実画面を個人情報のない範囲に切り出した",
          save_result="PNG原本と公開用の切り出しを保存",legibility="選択肢と返信を画面内で個別に拡大し日本語の要点を付けた",
          asset_ids=["picker","answer","followup"],shots=[{"shot_id":"selection","asset_id":"picker","purpose":"Chatの選択肢を確認"}])
    episodes=[]
    for k,label in (("short","条件を一つ変える実演"),("full","公式発表、モデル選択、料金と条件の検算")):
        receipt=json.loads((media/"release/v01"/k/"verification.json").read_text(encoding="utf-8"))
        episodes.append(dict(episode_id=k,title=label,overview=label,intended_message="Chatに来たGPT-6.2に画像と複数の条件を渡す",demo_idea="朝食込みの宿を比較し徒歩条件を変更",article_role="計算過程・対象プラン・原図の出典",capture_inspection_id="real-chat",duration_seconds=round(receipt["seconds"])))
    apply("proposal","v01",proposal_id="winter-v01",count_reason="ショートとフルの双方を指定。短編は実演、フルは比較と提供範囲まで。",episodes=episodes)
    apply("feedback","request",feedback_id="request",proposal_id="winter-v01",kind="comment",text=REQUEST,interpretation="既存キャラクターの冬服・指定音声モデルで2本制作。完成版の採用は未確認。")
    apply("claim","image",claim_id="image",basis="official",checked_at=DATE,text="OpenAIのChatでの画像理解評価は47.4%から71.7%。",source_ids=["release"],asset_ids=["release-head"])
    apply("claim","hotel-v2",claim_id="hotel",basis="tested",checked_at=DATE,text="この架空の料金表では徒歩15分は雪灯り館、徒歩5分では該当なし。",source_ids=[],asset_ids=["answer","followup"],test_conditions="Web版6.2 Instant、一時チャットに架空の税込料金表1枚。1人2泊、朝食2回、22,000円以内。徒歩15分から5分に変更。")
    apply("article","v01",version="v01",slug="chatgpt-62-chat-hotel-image",destination="benriworks/blog",published=False,
          sections=[dict(section_id="release",title="ChatGPTの11月23日更新",source_ids=["release"],asset_ids=["release-head"],claim_ids=["image"]),
                    dict(section_id="try",title="架空の宿を画像で比較",source_ids=[],asset_ids=["picker","answer","followup"],claim_ids=["hotel"])])
    (media/"workspace-state-v01.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Studio revision",state["project"]["revision"])
if __name__=="__main__":run(Path(sys.argv[1]))
