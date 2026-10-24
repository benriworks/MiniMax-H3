# 動画制作ガイド・引き継ぎ資料

更新日：2026-10-25。対象：人物キャラ、MiniMaxの人物動画、公式資料引用、実演、Geminiナレーションを組み合わせる日本語解説動画。

## 最初に読むファイル

調査から企画を始める共通機能は [動画・記事の企画ワークスペース](../../STUDIO_CONTENT_WORKSPACE_JA.md) を参照する。助手が調査し、本数と各回の概要を提案した後、ユーザーの意図を反映する。制作の窓口はチャットで、Studioへの転記をユーザーに求めない。

| ファイル | 用途 |
| --- | --- |
| [VIDEO_PRODUCTION_HANDOFF_JA.md](VIDEO_PRODUCTION_HANDOFF_JA.md) | 制作ノウハウと全工程。人物確認、ストーリー、保存、レビュー、GitHub運用を含む。別の制作担当者へ渡す総合資料 |
| [NARRATION_HANDOFF_JA.md](NARRATION_HANDOFF_JA.md) | **ナレーション担当者へ単体で渡せる別ファイル**。原稿、声、生成、速度・読み、組み込み、試聴、修正、保存の手順 |
| [SCREEN_CAPTURE_AND_QUOTES_JA.md](SCREEN_CAPTURE_AND_QUOTES_JA.md) | **撮影・編集担当者向けの別冊**。PC画面の撮り方、公式製品画像とスクリーンショットの引用、人物の効果的な使い分け |
| [DIRECTION_REVIEW_JA.md](DIRECTION_REVIEW_JA.md) | 文書整備後に検討する方向性。案と未決事項を整理し、採用済みと混同しない |
| [VIDEO_TO_BLOG_WORKFLOW_JA.md](VIDEO_TO_BLOG_WORKFLOW_JA.md) | 自分用の制作環境と、動画から詳細記事への導線。企画・実演・画像の共用、ブログへの受け渡しの設計 |
| [templates/PRODUCTION_RECORD_JA.md](templates/PRODUCTION_RECORD_JA.md) | 案件の目的、制作過程、出典、素材、修正理由、納品と検証のひな形 |
| [templates/CHARACTER_BIBLE_JA.md](templates/CHARACTER_BIBLE_JA.md) | 人物の外見・ペルソナ・成長・承認履歴のひな形 |
| [templates/REVIEW_REQUEST_JA.md](templates/REVIEW_REQUEST_JA.md) | 人物確認・初稿・修正版・最終版のレビュー依頼文と回答記録のひな形 |
| [templates/asset-catalog.example.json](templates/asset-catalog.example.json) | PC内の素材をID・版・相対パス・hashで追跡する記載例。自動登録ツールではない |
| [templates/content-project.example.json](templates/content-project.example.json) | 動画と記事を同じ企画・事実・素材に結び付ける共通台帳の記載例。未実装 |

現在の正本はこのフォルダー。低VRAM環境・生成方式の過去の実測は [PRODUCTION_PLAYBOOK_JA.md](../../PRODUCTION_PLAYBOOK_JA.md)、アプリの設計は [ARCHITECTURE.md](../../ARCHITECTURE.md) と [ARCHITECTURE_DIAGRAM.md](../../ARCHITECTURE_DIAGRAM.md) を参照する。

## 今回、規定したこと

製品解説では、まずユーザーPCで対象機能を開いて実画面の撮影・保存・可読性を確認し、その結果から台本と必要な撮影カットを決める。詳細は [撮影前の実機確認](SCREEN_CAPTURE_AND_QUOTES_JA.md) を参照。既存画像や公式引用へ置き換える前に確認する。

1. 最初に人物キャラとペルソナを作り、ユーザーに確認する。
2. 確認済みの人物をMiniMaxで動かし、ストーリーとシリーズの一貫性を持たせる。
3. 原本・初回出力・修正版・レビュー・完成品をローカルで追跡可能に保存する。
4. 文書・プロンプト・改善理由をGitHubへ継続的に残す。**制作動画本体のGitHub保管は不要**。
5. 画面確認と最終試聴、ユーザー採用とYouTube公開を分けて記録する。
6. 説明の要点を図・イラストと具体的な利用例で示し、仕組みから視聴者との関係・次の行動までつなぐ。具体と抽象を使い分ける手順は総合資料の「図で仕組みと自分との関係をつなぐ」（2026-10-25追加）を参照する。
7. 動画制作と同時に、記事草稿・公式HPのキャプチャと引用候補・記事用解像度のアプリ画面を集める。別の記事依頼を待たず、動画レビュー時に草稿と素材一覧も案内する。保存・確認基準は [動画とブログの共通工程](VIDEO_TO_BLOG_WORKFLOW_JA.md) の「動画制作と記事準備を同時に進める」を参照する。記事の公開は別の判断とする。

これらは今後の運用規定であり、既存の制作システムがすべての工程を自動強制しているという意味ではない。既存素材に承認記録がなければ、後から承認済みへ書き換えない。

## ローカル資料とGitHubの違い

`outputs/` の動画、音声、画像、レビュー用ページはローカル成果物。GitHubへcloneしただけでは取得できない。引き継ぎ時は、この文書群に加え、必要な素材・コードの版・環境情報を別途渡す。署名付き共有リンクは一時的な受け渡し手段であり、素材の恒久的な所在にはしない。

2026-10-23、ユーザーは「まず自分用に磨く」「動画から詳細ブログへつなぐ」「制作の決定事項と素材を記事にも使う」方向を提示し、「メモからDocsを作る」で制作工程を開始した。当面はチャットを窓口とし、レビュー動画はGoogle Driveを優先する。繰り返し使う処理はStudioへ随時追加する。具体化は [動画とブログの共通工程](VIDEO_TO_BLOG_WORKFLOW_JA.md)、最初の案件は [制作記録](../../productions/content-projects/CONTENT_20261023_claude_docs_reuse/README.md) を参照。公開は個別に確認する。
