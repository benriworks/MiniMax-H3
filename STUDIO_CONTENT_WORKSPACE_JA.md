# 動画・記事の共通企画ワークスペース

更新日：2026-10-24。実装範囲は調査・企画、撮影計画、主張と根拠、素材台帳、人物と絵コンテの5機能。

## 使い方と役割

制作の窓口はチャット。ユーザーは「この技術を紹介したい」など短い依頼と、提案への補足・修正を返せばよい。助手が調査、推奨本数と各回の概要、返答の解釈、構成変更、記録を担当する。長い入力フォームをユーザーへ渡さない。

Studioの「動画と記事の企画」は、同じ記録を確認する入口。5工程、企画の版、変更項目、根拠不足、素材の参照画像を表示する。テーマ登録・相談メモ保存・最新企画の採用も可能。ただし相談メモの保存だけでは構成を自動変更しない。チャットの助手が意図を反映して新しい企画案を登録する。

Web調査、自然文の解釈、Computer Useはチャット側で行う。ローカルStudioにチャットの接続権限を移譲したものではない。この機能自体はネット検索・撮影・MiniMax生成・音声生成・Drive送信・公開を実行しない。既存の処理や接続ツールで取得した結果を登録する。

2026-10-25の制作ルール：動画の調査・撮影・改訂と同時に、助手は記事草稿、公式HPの画面キャプチャと引用候補、記事用解像度のアプリ画面も準備する。追加の記事依頼やStudioへの入力をユーザーに求めない。動画場面と記事節を同じ主張・出典・素材IDに結び、レビュー時に草稿・素材一覧・不足を併記する。手順と寸法・可読性の基準は [動画とブログの共通工程](docs/video-production/VIDEO_TO_BLOG_WORKFLOW_JA.md) に従う。これは制作運用の追加であり、記事本文や撮影をStudioが自動生成する実装の追加ではない。

## 1. 調査と企画の流れ

1. 対象技術・ニュース・URLから案件を作る。既定は仕事でAIを使いたい人向け、ショート中心。素材・記事slugがなくても保存できる。
2. 助手が公式発表、公式ヘルプ、変更履歴、一次の実演報告、比較対象、利用条件を調べる。参考記事は論点発見に利用し、仕様の断定は一次資料で裏付ける。出典ごとに発表日・出来事の日・確認日を分け、提供地域・プラン・プレビュー・制約・情報の不一致を残す。
3. 台本や代替画像を固める前に、ユーザーPC上の機能入口と撮影可否を実際に確認する。企画案では未確認事項を明示できるが、未確認のまま絵コンテ確定へ進めない。
4. 本数は先に固定しない。1本の中心メッセージ、単独でも理解できるか、重複、実演の可否、説明量、既公開動画との関係から推奨する。推奨本数と理由、各回の見出し・概要・中心メッセージ案・尺・実演案・ブログで詳しく扱う内容をまとめて提示する。
5. ユーザーの自然な返答を原文と反映方針で記録する。「2と3をまとめたい」などの修正相談は採用ではない。新しい企画版へ反映し、変更点を示す。返答のない状態は採用にしない。
6. 対象企画版への明示的な採用返答を記録して、撮影計画・絵コンテへ進む。未反映の修正相談があれば採用を止める。既に確認した版・範囲について不要な再確認を要求しない。

## 2. 撮影・根拠・素材・人物

- 撮影状態は `uninspected / available / blocked / captured`。撮影済みには保存した実画面の素材IDが必要。アプリ、ログイン状態、入口、実表示、保存結果、可読性、試した経路、結果と確認日を記録する。
- 本数提案より前の撮影可否も保存できる。`capture` のepisode_idを省略し、inspection_idとtarget_featureを指定する。動画案にcapture_inspection_idを付ければ、採用後の撮影計画へ引き継ぐ。
- 撮影リストは入力・初回出力・修正依頼・修正後を基本とし、必要なら短い操作録画も既存処理で取得する。公式引用や図解を選ぶ場合も撮影可否を確認した理由を残す。
- 主張は `official / tested / hypothesis`。公式の断定には公式出典、実機確認には実演画像と検証条件が必要。生成画像を実機証拠にしない。実演は架空素材だけを使用する。
- 素材にはID、版、相対パス、実ファイルのSHA-256と容量、画像の実寸、派生元、媒体別確認を保存する。原本は `_private/`、公開用切り出しは別ファイル。改訂では新しいパスを使い、旧原本を上書きしない。
- 公開用画像プレビューはセッション認証、公開範囲・個人情報確認・ハッシュ・画像形式を確認する。旧版のプレビューもその版の実ファイルを使う。現在非公開の素材を旧版から再公開しない。
- 人物設定には架空の成人、参照画像、衣装、役割、口調、継続設定を保存する。ユーザーの返答・対象版・採用範囲を記録してから本番人物動画へ進む。参照画像や人物版が変われば古い確認を自動適用しない。
- MiniMax人物動画の登録には確認済み人物版と生成記録を要求する。登録が証明するのは素材の来歴・同一性であり、動画の動作品質や人の試聴合格ではない。
- 絵コンテは目的・説明音声・画面・尺・主張ID・素材ID・人物IDを持つ。人物の動き、全面表示、顔と字幕の分離を設計する。`beat` は `problem / try / insight / action / evidence / transition` を任意で指定でき、物語や尺の不足は補足表示する。

## 3. 共通CLIとAPI

ワークスペース直下から実行する。JSONファイルはUTF-8。CLIはStudioを起動せずに同じSQLiteを利用し、動作中の制作ジョブを回復・中断させない。

```powershell
python -m tools.studio.content_workspace create --input request.json
python -m tools.studio.content_workspace list
python -m tools.studio.content_workspace brief --project-id CONTENT_example
python -m tools.studio.content_workspace apply --project-id CONTENT_example --action research --input research-operation.json
python -m tools.studio.content_workspace get --project-id CONTENT_example
python -m tools.studio.content_workspace get --project-id CONTENT_example --revision 2
```

新規作成の最小入力：

```json
{"content_project_id":"CONTENT_example","title":"対象技術の紹介","topic":"調べたい技術やニュース"}
```

更新操作の共通入力：

```json
{
  "operation_id": "op_unique001",
  "expected_revision": 1,
  "data": {
    "research_id": "research_001",
    "summary": "助手が調査して整理した結果。未確認事項も明記する。",
    "checked_at": "2026-10-24",
    "sources": [{"source_id":"official_001","title":"出典のページ名","url":"https://example.com/docs","kind":"official","checked_at":"2026-10-24"}]
  }
}
```

`example.com` は形式説明用。実案件では実際に読んだ出典と日付に置き換える。`operation_id` はCLIで省略すると発行されるが、応答不明時の再送には同じID・同じ内容を使う。`expected_revision` は直前に取得した案件の版。同じ操作の再送は履歴を増やさず、内容違い・古い版は409相当で拒否する。

| 操作 | dataの主な項目 |
| --- | --- |
| `research` | research_id、summary、checked_at、sources。sourcesのkindはofficial/first_hand/secondary、日付はISO形式 |
| `proposal` | proposal_id、count_reason、episodes。各回はepisode_id/title/overview/intended_message/duration_seconds/demo_idea/article_role |
| `feedback` | feedback_id、proposal_id、text、interpretation。kindはrevision_request（既定）/comment/acceptance |
| `accept` | proposal_id、feedback_id、confirm_acceptance:true。最新企画とその版への返答を指定 |
| `capture` | episode_id、status、checked_at、route、result、app、login_state、feature_entry、display_result、save_result、legibility、shots |
| `claim` | claim_id、text、basis、checked_at、source_ids、asset_ids、test_conditions（tested時） |
| `asset` | asset_id、kind、path、visibility。公開用はprivacy_review:passed。実演はfictional_materials_only:true。公式画像はsource_url/source_checked_atも必要 |
| `character` | character_id、fictional_adult:true、name、persona、role、clothing、voice、continuity、reference_asset_id |
| `approve-character` | character_id、version、confirm_acceptance:true、user_response、scope |
| `storyboard` | episode_id、scenes。各場面はscene_id/purpose/narration/visual/duration_secondsと参照ID配列 |
| `article` | slug、sections。各節はsection_id/titleとepisode_ids/claim_ids/source_ids/asset_ids/character_ids |
| `reconcile` | scope:sceneまたはsection、対象episode_id/scene_idまたはsection_id、reason。再確認の理由を記録 |
| `link-production` | episode_id、production_id（Studio固有ID）。SHORTの参照はlegacy_refsに維持 |
| `archive` | archived:true/false。論理状態だけ変更し、素材・Drive・既存productionを削除しない |

HTTPは `GET/POST /api/content-projects`、`GET /api/content-projects/{id}`、`POST /api/content-projects/{id}/{操作}`。HTTP作成時にはoperation_idも必須。取得には任意の`?revision=N`が使える。画像は`/assets/{asset_id}?version=N`。GETもPOSTも既存のセッション認証を使う。

## 4. 保存と手戻りの制御

- 正本は `outputs/studio/studio.sqlite3` の `content_projects` と変更不能な `content_project_revisions`。schema v15。採用企画への参照が「どの構成を使うか」を示す。
- `CONTENT_...`、既存`SHORT_...`、Studioの`production_<hex>`は混同せず参照で結ぶ。
- schema1は `import --input ...` で取り込む。元JSON全体を保持し、読み込めない素材はimport_issuesへ残す。旧案件へ新しい企画・人物の承認を補わない。
- 出典変更は該当する主張と使用場面・記事節、素材変更はその使用先だけを再確認対象にする。人物変更は登場場面、中心メッセージ変更はその回を見直す。実演案が変わった回は撮影可否も再確認する。
- 統合・削減した回はretired_episodesへ残す。変更しない音声・動画・原本は再生成しない。
- `ready_for_production` は企画・準備記録の判定。素材割当待ちや想定尺などはwarningsも確認する。実製品の成功、人による最終試聴、ユーザー採用、公開の証明ではない。

## 5. 書き出しとGitHub

```powershell
python -m tools.studio.content_workspace export --project-id CONTENT_example --revision 8 --confirm-public-review
python -m tools.studio.content_workspace export-blog --project-id CONTENT_example --handoff-version v01
```

公開用記録は `outputs/content-projects/{id}/editorial/vNNNN/` へ新規保存する。公開確認後に使い、原本・生の返答・private参照・署名URL等を除外または伏せる。自動処理だけで機密除外が完全と扱わず、Git追加前に内容を確認する。

記事素材はarticle.sectionsから使用する公開画像だけを選び、既存 `content_projects.export_blog` のハッシュ・寸法・出典・記事用途確認を通して `blog-handoff/vNN/` に渡す。記事節に再確認事項があれば書き出さない。記事の公開許可は自動付与しない。

GitHubにはコード、ガイド、プロンプト、確認した出典、改善理由、検証要約を残す。動画・音声・納品ZIP・非公開原本はローカルと必要な共有先に置き、GitHubへ入れない。レビュー動画はDrive優先、S3は代替。今回の実装で共有・公開は自動化しない。

## 検証

`python -m unittest tests.test_content_workspace tests.test_content_projects` と `studio` の `npm test` / `npm run build` で契約・後方互換性を確認する。`python -m tests.content_workspace_live_server --stay-open` は別ワークスペースへ検証用Studioを起動する。実際のDocs案件があれば公開画像だけをコピーし、hash、元記録の保持、未採用状態を確認する。検証用の架空返答を実ユーザー承認と混同しない。終了はCtrl+C。


## 人物PIPの準備契約（2026-10-26）

人物のあるsceneは、従来の `presenter_layout: fullscreen` と、規則付きの `pip` を使える。顔と字幕の分離はどちらも必要。pipの `pip_policy` はtrigger（before_demonstration、emphasis、caution、closing）、出演人物IDごとのpositions（leftまたはright、重複なし）、avoid_gui_controlsとcaption_safeのtrue、speech_modeのaudio_envelope、listener_mouthのclosedを要求する。画像素材は現在の人物版のgenerated_stillとして照合する。音素同期を検証する契約ではない。

本編の実操作の間は隠し、要点専用の領域へ人物を配置する。`dialogue_avatar.py` が区間交差とPCM由来の口の開閉を扱う。今回の追加は共通準備処理と制作側の描画部品で、Studio UI/APIへ外部アカウント連携や自動配信を追加していない。入力例は `productions/LONG_20261026_dots_transfer_detail/revision-v02.json`、登録例は `register_v02.py` を参照する。
