# 再開履歴兼ノウハウ：Ultra・スマホ2アカウントのニュース2本

更新：2026-10-31。案件ID：`CONTENT_20261031_ai_news_ultra_accounts`。

[索引](../../../docs/video-production/README.md) → [総覧](../../../docs/video-production/PRODUCTION_KNOWHOW_JA.md) → この記録。

## 現在地と次の作業

ユーザーが具体的な2題材と切り口を示し、動画2本を作るよう依頼。[企画・表示原稿・読み原稿](plan.json)へ助手が転記した。約45秒は編集上の目安で、音声実尺を優先する。Claudeは認証済みUltraの5時間制限撤廃と残る週上限、ChatGPTはスマホの2アカウント切替とデータ・契約の分離を扱う。新しい主張や別ニュースを足して件数を増やさない。

- 人物：Claude編は既存の佐伯栞、ChatGPT編は前作Proニュースの男女を継承。既存MiniMax動画のhashを照合して再利用し、新しい人物・衣装・新規生成は追加しない。声は採用済みAoede、BGMは今回採用された共通 `explanation_v1`。
- 実画面：Claudeデスクトップとログイン済みWebを確認し、Webの設定→使用量を撮影。観察したアカウントはMax表示でセッション欄が残っており、Ultraの適用・認証・移行完了を実証していない。私的原本は `_private/captures/`。公表用には個人の残量・支払い・アカウント情報を使わない。
- スマホ：Computer Useのアプリ一覧に端末ミラーは見つからず、Android SDKのadbで接続端末0。実機の日本への反映・実切替・通知からの切替は未検証。公式が掲載する架空2アカウントの画面例と、短い設定手順の引用を使う。PC画面をスマホの実演と呼ばない。
- 公式：Claudeプラン説明と料金表、OpenAIリリースノートとスマホ対応の新URLを直接確認。検索には旧URLの「モバイル未対応」も出たが、新しい公式本文と10/30のリリースノートを優先。Claudeの10/30告知原投稿の直接取得・全対象への反映完了は未検証なので日付を断定しない。
- 最新動画：Claude v01（47.042秒、4,021,492 bytes）とChatGPT v02（48.292秒、4,390,544 bytes）。全編decode・音量実測・各9点の実MP4画像をAI補助確認し、Driveへ保存。名前・MIME・容量・親・所有者権限をreadback照合。このPCのDriveプレーヤーが読み込みから進まなかったため、動画2本だけS3へ代替送信し、CLIの完全GETとhash照合を確認。最終試聴・実スマホ再生・完成物採用・公開は未確認。[検査記録](VERIFICATION_JA.md)。
- 記事：草稿2本と公式抜粋5点、説明図3枚（PNGとSVG）のZIPをDrive共有。記事はblog未配置、写真・共通人物バナー未作成。記事公開・MDX検査は未実施。共通台帳revision 27。
- 次：Driveで2本の内容と音声・BGMのバランスをユーザーが確認する。記事草稿・図版も確認可能。実スマホ反映は未検証のまま保持し、公開依頼がなければ投稿やblog mainへのマージをしない。

## 保存・再利用

- 制作コード・出典・表示原稿・読み原稿：このフォルダー。
- 原本・派生・音声・版付き動画・検査・共有受領：`outputs/content-projects/CONTENT_20261031_ai_news_ultra_accounts/`。
- `captures/` は公式画面、`_private/captures/` はユーザー環境の原本。原本は保持し、別の `assets/` へ必要範囲を切り出す。記事向け素材は `blog-handoff/`。
- 別cloneのignored素材はhash照合してコピーする。動画・音声・ZIP・共有識別子はGitへ入れない。元のMiniMaxH3や前作の完成品は変更しない。

## 最新版の場所

- `claude-ultra/release/v01/claude-ultra-v01.mp4`
- `chatgpt-accounts/release/v02/chatgpt-accounts-v02.mp4`。v01は余白が大きかった初回として保持。v02は構図だけの変更でAAC bitstream一致。
- 各版の `verification.json`、`timeline.json`、`audio-plan.json`、`qc/`、`drive-upload.json` で原本・時刻・検査・共有を追う。
- 記事素材は `blog-handoff/v01/` と `blog-handoff/AI-news-20261031-blog-review-v01.zip`。17メンバー、368,705 bytes、全メンバーhashとCRCを照合。
- 独立した[設計本文](ARCHITECTURE.md)、[Mermaid図](ARCHITECTURE_DIAGRAM.md)、[出典](SOURCES_JA.md)、[投稿タイトルと説明欄](YOUTUBE_METADATA_JA.md)を参照。

## この案件のノウハウ

- 同じ記事IDでも旧slugの検索結果に旧仕様が残る。新しい公式URLの本文・更新日とリリースノートを照合し、検索断片だけで新機能を否定しない。
- 実アカウントにMaxが表示されたことは、Ultraの全世界未提供や自動移行失敗の根拠にならない。仕様の説明と個別反映実験を分ける。
- スマホの公式例を引用するときは「公式掲載の画面例」と明記し、自分の端末で切替実証したと説明しない。

## 再開履歴

| 日付 | 作業・判断 | 検証範囲・残り |
| --- | --- | --- |
| 2026-10-31 | 2本の制作依頼を受領。公式4ページ・実画面撮影経路・端末接続を確認し、企画を保存 | 仕様確認と撮影確認済み。音声生成・本編・記事素材・共有は制作中 |

| 2026-10-31 | Aoede12件を生成し、Claude v01とChatGPT v01を制作。人物の空間配分を点検しChatGPT v02へ寄りを修正 | 音声原本再利用、v01/v02 AAC一致。追加人物生成0 |
| 2026-10-31 | 動画2本と記事用ZIPをDrive保存しreadback照合、共通台帳revision 27へ根拠と草稿を保存 | 全編decode・最終AAC音量・実MP4各9フレーム・ZIP全メンバーhash確認。人の試聴、実機、採用、公開は未確認 |

| 2026-10-31 | Drive再読込でも読み込み中のため、既存の代替指定に従いS3予備を2本作成 | dry-runとStatus=verified、inline・完全GET・hash照合。署名URL等は文書へ保存しない。Gitは個人forkのcodex/ai-news-ultra-accounts-20261031、Draft PR #9（baseは先行制作ブランチ）、main未マージ |
