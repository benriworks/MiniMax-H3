"""Append the November 21 viewer feedback, provider evidence and revised article to Studio."""
from copy import deepcopy
from capture import HERE, OUT, ROOT, write
from capture_providers import HAT, RED_HAT, REMI, ROOT as CAPTURES
from record_project import PROJECT, SLUG, cli, read

DAY = "2026-11-21"
FEEDBACK = "動画を見ました。著作権や商標に少し配慮しすぎかな。配布元がRedhatやRemiなら固有名詞できちんと紹介して。見た人の記憶に残るように。もっと固有名詞を例で使ったり、公式の写真引用をお願い。あと、構成を見る、などの表現は分かりにくい。設定や利用構成に依存、などにしてほしい。"
POSTING = "動画作成時はYouTubeタイトルや概要欄、サムネイル画像も作成お願いします。規約に書いてませんでしたが？"
SOURCES = {"rh-bulletin":("Red HatのPHP告知 RHSB-2026-020",RED_HAT),
    "rh-practice":("Red Hatのバックポート方針","https://access.redhat.com/security/updates/backporting"),
    "rh-hat":("Red Hatの公式写真 The hat",HAT),"remi-release":("Remiの11月19日のPHP更新記事",REMI)}
CAPTIONS={"redhat-photo":("Red Hat Summitの会場に並んだ赤いフェドーラ帽","Red Hat Summitに並ぶフェドーラ帽。Red Hat公式「The hat」からの写真引用。"),
    "redhat-notice":("Red HatのPHP告知番号と見出し","RHSB-2026-020の見出し。Red Hatが配るPHPはこの対象製品欄から確認する。"),
    "redhat-products":("RHELで配布するPHPに影響しない2件に言及するRed Hatの記述","対象7件のうち2件に関するRed Hatの判断。"),
    "remi-notice":("Remiの更新記事の見出しに8.4.28を含む4系列の番号が並ぶ","Remiが11月19日に配布を案内した4系列。")}
def main():
    base=read(OUT/"workspace-state-full-v02.json")["project"]
    state=cli("get",project_id=PROJECT)
    def apply(action,key,**fields):
        nonlocal state
        op="php-now-"+key
        receipt=OUT/"studio-operations"/(op+"-applied.json")
        if receipt.exists(): return
        state=cli("apply",dict(operation_id=op,expected_revision=state["project"]["revision"],data=fields),project_id=PROJECT,action=action)
        write(receipt,{"revision":state["project"]["revision"]})
    for key,value,meaning in (("posting",POSTING,"各動画にタイトル・概要欄・サムネイル画像を同梱する。"),("examples",FEEDBACK,"既存候補を視聴した上での改訂依頼。配布元を実名で示し、設定や利用構成に依存する意味を具体化する。")):
        apply("feedback",key,feedback_id=key,proposal_id="php-nov-full-v02",kind="comment",text=value,interpretation=meaning)
    apply("research","provider-sources",research_id="providers",checked_at=DAY,summary="Red Hatの7件中2件の判断、バックポート方針、帽子の実物写真、Remiの更新記事を各発信元で照合。",
          sources=[dict(source_id=k,kind="official",title=v[0],url=v[1],checked_at=DAY) for k,v in SOURCES.items()])
    apply("capture","provider-chrome",inspection_id="vendor-chrome",status="available",checked_at=DAY,
          target_feature="Red HatとRemiの公式配布情報とRed Hat Summitの実物写真",app="Google Chrome",
          login_state="公開ページ",feature_entry="Red Hat Customer Portal・Brand standards、Remi公式記事",
          route="ローカルChromeでページを開いて原文を測定、写真の配信元も照合",
          display_result="写真、製品告知の原文、Remiの4つの版番号を表示",result="4図取得",
          save_result="3100×2040のコンテキスト原本と抜粋、改変なしの写真を保存",legibility="動画の実フレームと記事用の縮小画面で確認",shots=[])
    for key,row in read(CAPTURES/"manifest.json")["assets"].items():
        m=row["quote"];path=OUT/m["path"];alt,caption=CAPTIONS[key]
        apply("asset","image-"+key,asset_id=key,kind="official_capture",visibility="public",privacy_review="passed",
            blog_usage_review="passed",user_approved_for_blog=False,path=path.relative_to(ROOT).as_posix(),
            width=m["pixels"][0],height=m["pixels"][1],sha256=m["sha256"],source_url=row["url"],
            source_checked_at=DAY,alt=alt,caption=caption)
    ids=list(CAPTIONS); source_ids=list(SOURCES)
    apply("claim","distribution",claim_id="distribution",basis="official",checked_at=DAY,source_ids=source_ids,asset_ids=ids,
        text="RHEL標準PHPはRed Hatの対象製品とパッケージのリリース番号、Remi由来ならRemiの更新記事を確認する。")
    kit=read(HERE/"youtube/verification-v02.json")
    episodes=deepcopy(base["proposals"][-1]["episodes"])
    for episode in episodes:
        kind=episode["episode_id"].split("-")[-1];cut=kit["cuts"][kind]
        episode.update(title=cut["title"],duration_seconds=round(cut["video"]["duration"]),capture_inspection_id="vendor-chrome",
            overview="冬服の男女で、PHPの設定による影響と実際の配布元による確認先を解説",
            demo_idea="Red Hat Summitの写真から、Red Hatの告知・Remiの更新記事へ切り替える。")
    apply("proposal","distribution-editions",proposal_id="php-distribution-v02",episodes=episodes,
        count_reason="ユーザーの改訂依頼を縦横それぞれに反映。",production_candidate="distribution-revision.json")
    sections=deepcopy(base["article"]["sections"])
    sections.insert(3,dict(section_id="distribution",title="Red HatとRemi、それぞれの確認先",source_ids=source_ids,asset_ids=ids,claim_ids=["distribution"]))
    apply("article","article-v02",version="v02",slug=SLUG,destination="benriworks/blog",published=False,
         draft_path=(HERE/"article-draft-v02.md").relative_to(ROOT).as_posix(),sections=sections)
    if not (OUT/"blog-handoff/v02").exists():cli("export-blog",project_id=PROJECT,handoff_version="v02")
    write(OUT/"workspace-state-distribution.json",state)
    print("Studio revision",state["project"]["revision"])

if __name__=="__main__": main()
