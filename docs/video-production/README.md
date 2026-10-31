# 動画・関連記事の制作索引

更新日：2026-10-31。このリポジトリの制作情報は、索引・総覧・案件ごとの再開履歴兼ノウハウの3種類を入口に管理する。チャット履歴がない別チャット・別担当者も、ここから再開する。

## 最初に読む3種類

| 順番 | 読むもの | 何を復元するか |
| --- | --- | --- |
| 1 | この索引 | 対象案件と必要な専門資料の所在 |
| 2 | [制作ノウハウ総覧](PRODUCTION_KNOWHOW_JA.md) | 共通の制作判断、失敗と改善、保存・レビューの基準 |
| 3 | 下の案件一覧にある `RESUME_AND_KNOWHOW_JA.md` | 現在地、採用範囲、最新版・素材、未完了依頼、次の作業、案件固有の学び |

運用の規定はルートの [AGENTS.md](../../AGENTS.md)。参照資料、対象案件・版、採用済み事項、次の作業を短く報告して着手する。ユーザーに過去の説明や長いフォーム入力をやり直してもらわず、助手が根拠資料から復元する。

## 参照・更新の手順

1. **着手・再開**：上の3種類を読み、必要な台本・出典・検証台帳まで確認する。コードと素材のルートを区別し、別cloneにも動画があると仮定しない。
2. **新規案件**：[ひな形](templates/PRODUCTION_RECORD_JA.md)を案件内の `RESUME_AND_KNOWHOW_JA.md` として作り、この一覧へ追加する。content-projects、人物素材、シリーズも同じ名称で管理できる。
3. **制作の節目**：再開記録の現在地・次の作業を更新し、依頼、対象版、判断、変更理由、再利用、確認範囲、残りを履歴へ追記する。旧版・未完了依頼・訂正根拠を保持する。
4. **終了・引き継ぎ**：次に何を見て何をするか、完了を示す根拠、Git同期状態まで残す。動画と記事の採用・公開は分ける。
5. **共通化**：他案件にも役立つ学びは条件と証拠を添えて総覧へ反映する。専門別冊へ実務の詳細、案件へ固有の数値・失敗例を残し、索引から結ぶ。

最新版の判断と過去の検証を分ける。過去の「未投稿」を後の公開申告より優先せず、後のユーザー申告もURL・公開範囲・実投稿日時の独立検証と混同しない。資料が読めない・素材がない場合は不足と影響を記録する。

## 案件・素材の再開入口

2026-10-30、初回に35単位の再開入口を整備し、その後Pro利用枠ニュース1件を追加した。現在の索引は36単位。シリーズは各回の原稿・台帳をまとめる親単位、人物素材は再利用元の単位としている。順序は現在の制作判断を探しやすくするためのもので、全案件が制作中・完了・採用済みという意味ではない。

各再開記録には照合元の文書をリンクする。今回の整理は文書の照合であり、媒体の再生・全decode、Driveのアクセス、公開URL、最新の製品仕様を新たに検証したものではない。別ブランチ・別cloneだけにある案件は、対象ブランチを確認してから同じ形式で追加する。

### 現在の案件

| 案件・素材 | 再開時の入口 |
| --- | --- |
| ChatGPT Pro：Work・Codex利用枠拡大ニュース（新規H3人物6本を使う48秒v03・15秒ポーズ一覧をDrive共有、試聴待ち） | [content-projects/CONTENT_20261030_chatgpt_pro_usage_news](../../productions/content-projects/CONTENT_20261030_chatgpt_pro_usage_news/RESUME_AND_KNOWHOW_JA.md) |
| dots：Excelから案件管理へ自動転記する詳細動画 | [LONG_20261026_dots_transfer_detail](../../productions/LONG_20261026_dots_transfer_detail/RESUME_AND_KNOWHOW_JA.md) |
| Claude Docs：メモから文書へ、動画と記事の共用 | [content-projects/CONTENT_20261023_claude_docs_reuse](../../productions/content-projects/CONTENT_20261023_claude_docs_reuse/RESUME_AND_KNOWHOW_JA.md) |
| PHP2Shell：概要と対策を説明するショート | [content-projects/CONTENT_20261024_php2shell_overview](../../productions/content-projects/CONTENT_20261024_php2shell_overview/RESUME_AND_KNOWHOW_JA.md) |
| dots共有デスクトップ：操作交代・Blender・自動転記の3本 | [content-projects/CONTENT_20261025_dots_shared_desktop_pilot](../../productions/content-projects/CONTENT_20261025_dots_shared_desktop_pilot/RESUME_AND_KNOWHOW_JA.md) |

### シリーズ・改訂

| 案件・素材 | 再開時の入口 |
| --- | --- |
| Docs・dots第7〜9回のメッセージ改訂 | [SERIES_20261023_editorial_revision](../../productions/SERIES_20261023_editorial_revision/RESUME_AND_KNOWHOW_JA.md) |
| dots第5〜9回：メモリ・定期実行などの最終改訂 | [SERIES_20261023_dots_final_delivery](../../productions/SERIES_20261023_dots_final_delivery/RESUME_AND_KNOWHOW_JA.md) |
| Claude：Docs・Slides・Design・部分修正・書き出しの5本 | [SERIES_20261022_claude_work](../../productions/SERIES_20261022_claude_work/RESUME_AND_KNOWHOW_JA.md) |
| dots第5〜9回：公式引用と人物動画を入れた前世代 | [SERIES_20261022_dots_finale](../../productions/SERIES_20261022_dots_finale/RESUME_AND_KNOWHOW_JA.md) |
| dots紹介全9本：シリーズの初期版 | [SERIES_20261005_dots](../../productions/SERIES_20261005_dots/RESUME_AND_KNOWHOW_JA.md) |
| Claude Duetとdotsの比較・75秒 | [COMPARE_20261022_duet_dots](../../productions/COMPARE_20261022_duet_dots/RESUME_AND_KNOWHOW_JA.md) |
| dots第2回の補足：クラウドPCの3つのメリット | [SHORT_20261021_dots_cloud_benefits](../../productions/SHORT_20261021_dots_cloud_benefits/RESUME_AND_KNOWHOW_JA.md) |
| dots第3回：アプリ連携のAoede版 | [SHORT_20261022_dots_03_aoede](../../productions/SHORT_20261022_dots_03_aoede/RESUME_AND_KNOWHOW_JA.md) |
| dots第4回：並行作業と公式画面引用 | [SHORT_20261022_dots_04_editorial](../../productions/SHORT_20261022_dots_04_editorial/RESUME_AND_KNOWHOW_JA.md) |

### 人物・企画素材

| 案件・素材 | 再開時の入口 |
| --- | --- |
| dots男女：待ち合わせ・右から走り込みの冒頭 | [CHARACTERS_20261026_dots_duo_opening](../../productions/CHARACTERS_20261026_dots_duo_opening/RESUME_AND_KNOWHOW_JA.md) |
| dots・Claude・Codexの説明人物モーション | [CHARACTERS_20261022_explainer_motion](../../productions/CHARACTERS_20261022_explainer_motion/RESUME_AND_KNOWHOW_JA.md) |
| dots系列の元となるプログラマー男女 | [characters/programmer-duo](../../productions/characters/programmer-duo/RESUME_AND_KNOWHOW_JA.md) |
| Claude・Codexの知的なビジネス案内役 | [characters/business-guides-20261022](../../productions/characters/business-guides-20261022/RESUME_AND_KNOWHOW_JA.md) |
| Claude・Codexの次シリーズ候補調査 | [PLANNING_20261022_next_series](../../productions/PLANNING_20261022_next_series/RESUME_AND_KNOWHOW_JA.md) |

### 過去の制作・比較例

| 案件・素材 | 再開時の入口 |
| --- | --- |
| Claude獲得・男性5秒 | [CATCH_20260919_claude_acquired_5s](../../productions/CATCH_20260919_claude_acquired_5s/RESUME_AND_KNOWHOW_JA.md) |
| Claude獲得・女性5秒 | [CATCH_20260920_claude_acquired_female_5s](../../productions/CATCH_20260920_claude_acquired_female_5s/RESUME_AND_KNOWHOW_JA.md) |
| 女性キャラ・明るい衣装 | [CATCH_20260921_claude_acquired_female_bright_5s](../../productions/CATCH_20260921_claude_acquired_female_bright_5s/RESUME_AND_KNOWHOW_JA.md) |
| 女性キャラ・体格調整 | [CATCH_20260930_claude_acquired_female_silhouette_5s](../../productions/CATCH_20260930_claude_acquired_female_silhouette_5s/RESUME_AND_KNOWHOW_JA.md) |
| 生成AI CM・15秒 | [CM_20260815_genai_mastery_15s](../../productions/CM_20260815_genai_mastery_15s/RESUME_AND_KNOWHOW_JA.md) |
| 完全合成人物のダンスPV・15秒 | [PV_20260815_original_jp_dance_unit_15s](../../productions/PV_20260815_original_jp_dance_unit_15s/RESUME_AND_KNOWHOW_JA.md) |
| CLAUDE.md解説・15秒 | [SHORT_20260823_claude_md_15s](../../productions/SHORT_20260823_claude_md_15s/RESUME_AND_KNOWHOW_JA.md) |
| 生成AIで企画を形にする15秒 | [SHORT_20260828_ai_content_15s](../../productions/SHORT_20260828_ai_content_15s/RESUME_AND_KNOWHOW_JA.md) |
| Claude Codeデスクトップ・15秒図案版 | [SHORT_20260905_claude_desktop_15s](../../productions/SHORT_20260905_claude_desktop_15s/RESUME_AND_KNOWHOW_JA.md) |
| Codex：依頼・実装・確認の15秒 | [SHORT_20260905_codex_15s](../../productions/SHORT_20260905_codex_15s/RESUME_AND_KNOWHOW_JA.md) |
| Claude Desktop・実画面21秒 | [SHORT_20260906_claude_desktop_real_capture](../../productions/SHORT_20260906_claude_desktop_real_capture/RESUME_AND_KNOWHOW_JA.md) |
| Claude Desktop・イラストと実画面21秒 | [SHORT_20260906_claude_illustrated](../../productions/SHORT_20260906_claude_illustrated/RESUME_AND_KNOWHOW_JA.md) |
| 編集スタイル・6秒無音レビュー | [SHORT_20260908_editorial_review](../../productions/SHORT_20260908_editorial_review/RESUME_AND_KNOWHOW_JA.md) |
| Claude Desktop・編集スタイル30秒 | [SHORT_20260909_editorial_30s](../../productions/SHORT_20260909_editorial_30s/RESUME_AND_KNOWHOW_JA.md) |
| Claude Code・3か月の進化と明るい夜景 | [SHORT_20260916_claude_code_evolution_30s](../../productions/SHORT_20260916_claude_code_evolution_30s/RESUME_AND_KNOWHOW_JA.md) |
| Claude Codeのすごさ・30秒 | [SHORT_20260926_claude_code_wow_30s](../../productions/SHORT_20260926_claude_code_wow_30s/RESUME_AND_KNOWHOW_JA.md) |
| Claude Code・共通Shorts演出サンプル | [SHORT_20260930_claude_code_creator](../../productions/SHORT_20260930_claude_code_creator/RESUME_AND_KNOWHOW_JA.md) |

## 工程ごとの詳細資料

これらは3種類から参照する専門別冊・証拠・ひな形である。既存の記録を削除したり、すべてを総覧へ複製したりしない。更新した判断は総覧・案件記録と整合させ、歴史的な数値や未完了の依頼を現在の完了へ読み替えない。

| 資料 | 用途 |
| --- | --- |
| [全工程の引き継ぎ](VIDEO_PRODUCTION_HANDOFF_JA.md) | 人物確認、構成、保存、レビュー、GitHub運用の具体的な実務 |
| [題名・結論ファースト・人物と掛け合い](EDITORIAL_PATTERNS_JA.md) | 冒頭、質問役と実務役、全面表示とPIP、編集の確認項目 |
| [ナレーションの別冊](NARRATION_HANDOFF_JA.md) | 担当者へ単体で渡せる原稿・声・読み・生成・再開・費用・試聴手順 |
| [会話とBGM](DIALOGUE_NARRATION_JA.md) | 質問→回答→実演の進行、音声実尺、返答後の間、明るい伴奏 |
| [実画面の撮影と公式引用](SCREEN_CAPTURE_AND_QUOTES_JA.md) | 撮影前の実機確認、原本と切り出し、記事解像度、来歴・出典 |
| [動画とブログの共通工程](VIDEO_TO_BLOG_WORKFLOW_JA.md) | 同時草稿・素材収集、動画→詳細記事、blog／note、記事素材の受け渡し |
| [企画ワークスペース](../../STUDIO_CONTENT_WORKSPACE_JA.md) | 助手の先行調査、本数と概要の提案、ユーザー返答、根拠・素材・絵コンテ、実装範囲 |
| [ローカル生成のプレイブック](../../PRODUCTION_PLAYBOOK_JA.md) | 低VRAMの生成方式・所要時間・失敗候補・条件付きの過去実測 |
| [方向性の検討記録](DIRECTION_REVIEW_JA.md) | 自分用の制作環境、チャット制作、動画と記事の再利用、採用と未決事項 |
| [2026-10-28のGit統合記録](GITHUB_SYNC_20261028_JA.md) | 保存境界・対象・検証の範囲と未確認事項。当時の記録であり、最新Git状態ではない |
| [外部映像APIの候補調査](research/EXTERNAL_VIDEO_API_20261028.json) | 2026-10-28時点の候補・料金前提・比較案。調査済み／未採用であり、実品質・速度・現在の利用可否は未検証 |
| [アーキテクチャ本文](../../ARCHITECTURE.md)・[Mermaid構成図](../../ARCHITECTURE_DIAGRAM.md) | 共通システムの仕組み。実装を変えた際は独立して更新 |

## Studio・撮影・生成の実装資料

ルート直下に分散していた実装資料も、ここから参照する。従来のUI操作ガイドは助手が使う詳細資料で、ユーザーがStudioを操作しなければ制作できないという意味ではない。各資料の日付と検証範囲を確認する。

| 資料 | 用途と境界 |
| --- | --- |
| [Shorts制作機能](../../SHORTS_CREATOR_JA.md) | JSON台本、実音声尺、BGM、再利用、描画・検査の共通処理 |
| [Studio MVP](../../STUDIO_MVP_JA.md) | 共通画面・API・制作経路。個別スクリプトからの実行と通常Runの違いも確認 |
| [Studio品質ガイド](../../STUDIO_CONTENT_QUALITY_GUIDE_JA.md) | 従来の制作・修正・投稿用テキストの操作手順。現在の運用入口はこの索引 |
| [画面解説テンプレート](../../STUDIO_SCREEN_EXPLAINER_JA.md) | 実画面の構図、素材取得、音声・版の再利用。ユーザー指摘と未収録素材を含む |
| [静止画ライブラリ](../../STUDIO_STILL_LIBRARY_JA.md) | 撮影、比較、採用、記事向け書き出し。撮影と採用を区別 |
| [Claude画面の準備操作](../../STUDIO_CLAUDE_CONTROL_JA.md) | 限定操作ヘルパーの条件と未検証範囲。別経路のComputer Use成功をヘルパー実機成功と扱わない |
| [製品別テーマ](../../STUDIO_TEMPLATE_BRANDING_JA.md) | 配色・文字・識別の共通compositionと、外観適用の検証範囲 |
| [画面解説の実機検証](../../STUDIO_SCREEN_EXPLAINER_VERIFICATION_20260906.md) | 2026-09-06の実測・レビュー。現在の全工程の受入結果ではない |
| [Studio品質・UXの検証](../../STUDIO_QUALITY_UX_VERIFICATION_JA.md) | 対象機能の検証記録。作品の最終採用・現在のCIと混同しない |
| [過去のパイプライン計画](../../STUDIO_COMPLETION_PLAN_JA.md) | 以前の優先順位と未完了事項。現在の方針は総覧と対象案件を照合 |
| [環境セットアップ](../../LOCAL_SETUP_JA.md)・[構築記録](../../ENVIRONMENT_SETUP_RECORD_JA.md) | 実行環境を復元するときの詳細。別cloneにモデル・素材・秘密が付属するわけではない |

## 新規作成・担当者へ渡すひな形

| ひな形 | 使い方 |
| --- | --- |
| [再開履歴兼ノウハウ](templates/PRODUCTION_RECORD_JA.md) | 案件内の `RESUME_AND_KNOWHOW_JA.md` として作る。現在地と次の作業を先頭、詳細根拠と追記履歴を後半へ |
| [人物設定](templates/CHARACTER_BIBLE_JA.md) | 外見、ペルソナ、衣装、役割、ストーリー、採用範囲 |
| [レビュー依頼](templates/REVIEW_REQUEST_JA.md) | 人物、初稿、修正版、最終確認。対象版と2〜3点の確認事項 |
| [素材台帳の記載例](templates/asset-catalog.example.json) | ID・版・親素材・相対パス・hashを整理する例。自動登録ツールではない |
| [共通企画の記載例](templates/content-project.example.json) | 動画と記事の事実・素材を結ぶ例。稼働する台帳・版管理は企画ワークスペースの仕様を参照 |

## 保存と再開の境界

- 正本のガイドと案件記録はリポジトリで管理し、相対パスで結ぶ。古い案件READMEと改訂ファイルは詳細・履歴として保持する。
- **制作した動画そのものをGitHubへ保管する必要はない。** 動画・音声・納品ZIP・撮影原本はローカルPCと必要な共有ストレージへ。`outputs/`や実行環境はcloneだけではそろわない。
- 台帳のhash・bytes・版・原本との関係で対象を確認する。署名リンクを恒久的な保存先にせず、キー・私的原本・共有受領ログをGitへ入れない。
- レビュー動画はDrive優先。S3はDriveを使えない場合、または会社へ持ち込むための指定時に使う。アップロードの照合とスマホ実機再生は別に記録する。
- 投稿先は原則 `benriworks/blog`、案件によってnote。動画と記事を同時に準備し、公開・mainへのマージは別の明示的な依頼に基づく。
- 索引を読めることと制作ルールを自動強制できることは別。新しいチャットから3種類を読み、対象版・未完了事項・次の作業を復元できるか確認する。

## 今回の整理と確認範囲

2026-10-30、Git管理下の制作フォルダー35単位と、ルート・専門ガイド・ひな形を検索した。再開記録の詳細根拠は80参照。旧記録32ファイルには案内だけを追加し、本文を保持した。3種類の文書と追加リンクのローカル参照369件、Markdown構造、案件一覧の35件網羅、差分の空白・競合マーカー・秘密情報パターンを確認した。

dots詳細編の採用v03／候補v04／未制作導入、Docsの動画v03／作業フォルダーv04、dotsの公開申告／未検証URLを文書から区別できることを確認した。実際に別チャットを起動した受入試験ではない。アプリのコード・API・モデル・動画・音声は変更せず、生成・共有・公開やランタイムテストは行っていない。ローカルの照合記録は `outputs/docs/knowledge-management-20261030/` に保存する。
