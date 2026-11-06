# 再開履歴兼ノウハウ：Tiboの28日間チャレンジ

更新日：2026-11-01。案件ID：CONTENT_20261101_tibo_28day_recap。

## 現在地と次の作業

- ユーザー依頼：28日間チャレンジをショートにし、リセットの日にボタンを押す動画、バンクの日に保管するリセットを表す動画、公式サイトとTibo本人の投稿画像を挿入する。
- 制作対象は1本。最新レビュー候補は **v07、84.125秒、1080×1920/24fps**。v04の「大枠は大丈夫」という返答を継承し、1行ボタン中央揃え・称賛と金色のきらめきに加え、明るい8小節ループとreset/bank/improvementの3種SEを追加。v07全体は採用前。
- 前作から既存の男女、検証済みMiniMax人物動画、Gemini Aoede、BGM `explanation_v1` を継承。新しい人物の作成・採用はなし。
- 調査時点：2026-10-31 19:23 UTC＝11/1 04:23 JST＝10/31 12:23 PDT。Day 27進行中、Day 28は未来。Day 26投稿の予告を配布完了に書き換えない。
- コードと素材：このworktreeの `productions/content-projects/CONTENT_20261101_tibo_28day_recap/` と `outputs/content-projects/CONTENT_20261101_tibo_28day_recap/`。動画・音声・撮影原本はignoredでcloneに含まれない。
- v06の52画像と文字配置6テストを保持。v07はvideo streamとナレーションWAVの一致、ループ境界、全decode・最終AAC音量・全編AI音声点検を完了。記事v02のZIPは全hash/CRCを照合。v04大枠への肯定はあるが、v07の最終採用、モバイル実機再生、公開は未確認。
- Driveへv04と記事素材ZIPを保存し、名前・MIME・容量・本人所有をreadback確認。PCブラウザでは再生操作後も読み込みが継続したため、既定の代替としてv04だけをS3へ送り、exit 0・Status=verified・完全GET・hash・inlineを確認した。スマホ実機再生とは区別する。
- Driveへv07も保存してreadback照合。ブラウザは再生処理中のため、S3up previewでv07の再生用リンクを追加し、exit0・verifiedと完全GETのhash一致を確認。署名URLは保存しない。
- 次：v07の明るい曲・3種SEの違い・声の聞き取り、中央揃えと最後8秒をユーザーにレビューしてもらう。Day28追補は一次情報を再取得する。記事の媒体適用・公開は別依頼。
- Git：専用ブランチ `codex/tibo-28day-recap-20261101`、制作コード・文書の初回保存 `d480bb8`、[Draft PR #10](https://github.com/benriworks/MiniMax-H3/pull/10)。先行PR #9のブランチをbaseにした個人forkへの保存。main未マージ。媒体・音声・署名URLはGit対象外。

## 撮影・出典

- Chromeのログイン済みXで開始宣言とDay 26原投稿を開けた。通常のWeb取得は403だったため、Computer Useによる実表示を確認して撮影。
- ChatGPT Webの設定→使用状況を実際に開き、「利用上限のリセット」「完全リセット」の入口と説明を確認。実際のリセット使用・購入・権限変更は行わない。
- 原本は `outputs/content-projects/CONTENT_20261101_tibo_28day_recap/_private/captures/`。アカウント、残量、Xの他人の返信・閲覧者の操作状態を含む原本は返却ZIPにもGitにも入れない。
- 公開用は説明に必要な短い引用のみ別切出し。出典と照合状況は [SOURCES_JA.md](SOURCES_JA.md) を参照。

## 最新版と再開の入口

`outputs/content-projects/CONTENT_20261101_tibo_28day_recap/` 以下：

- **最新**：`tibo-recap/release/v07/tibo-recap-v07.mp4`。`music-loop.wav`、`music.wav`、`effects.wav`、`cue-reset.wav` / `cue-bank.wav` / `cue-improvement.wav`、`narration.wav`、`mix.wav`、`audio-plan.json`、`verification.json`、`loop-check.json`。映像はv06を再圧縮せず継承。

- `tibo-recap/release/v06/tibo-recap-v06.mp4`、`verification.json`、`timeline.json`、`audio-plan.json`、`render-inputs.json`、`label-layout-audit.json`、`qc/`。v04とv05も保持。
- `motion-graphics/v03/reset-button-press.mp4` と `banked-reset-store.mp4`。各3秒。中央揃えへ更新した自作2Dモーション。旧v02も保持。
- `tibo-recap/voice/v01/` と冒頭のみ `voice/v02/`。成功音声11件。追加はscene-09の称賛1件で、既存原本を保持。
- `blog-handoff/v02/` と `blog-handoff/Tibo-28days-blog-review-v02.zip`。草稿・日別表・引用7候補・自作図2組・出典・投稿文。旧v01も保持。
- `_private/captures/`、`_private/x-evidence.json`、`_private/ai-listening-v03/` と `ai-listening-v04/` は原本・調査・AI点検用。公開素材やGitへ入れない。
- [設計本文](ARCHITECTURE.md)、[Mermaid図](ARCHITECTURE_DIAGRAM.md)、[音の設計](audio-design-v07.json)、[検査](VERIFICATION_JA.md)、[投稿タイトルと説明欄](UPLOAD_TEXT_JA.md)を参照。共通台帳revision 40。

## この案件のノウハウ

| 課題 | 対応 | 限界 |
| --- | --- | --- |
| 日本時間の「11/1」を最終日完了と誤解する | UTC・JST・Pacificを同時に保存しDay27/28は予告と明示 | 後続の公式発表で更新が必要 |
| バンクの受取と使用を混同する | 券を保管→後日使う動き、受取だけでゲージを回復させない | 実アカウントで配布経緯は実証しない |
| Pro全員全枠2倍という過度の要約 | Pro200の従来高枠は据置、Work/CodexとChatを分ける | 個別反映と絶対容量は未測定 |
| キャッシュと永続記憶の混同 | 再利用改善という短い表現と明示的注意 | 記憶保証や無期限会話保持と言わない |
| 文字がボタンの上側へ寄る | 実ラスタのinkから1行を上下左右中央、明示複数行は上寄せ | 送り幅の余白を除き、実フォントの6テストと実MP4で確認。共通text_layoutへ反映 |
| 最後を明るく称えたい | 既存男女・追加Aoede1件・顔や文字を避ける金色の星 | Day27/28の予告を完結に読み替えず、称賛は編集上の感想として保存 |

## 初回と修正の履歴

| 日付・版 | 判断と根拠 | 検証・残り |
| --- | --- | --- |
| 2026-11-01 v01制作開始 | ユーザーの28日一覧を参考に、一次投稿・公式Helpの条件を優先 | 一次取得、制作と記事を進行中。完結とは扱わない |
| 2026-11-01 v01〜v03 | 初稿を保持し、接触・人物構図、未完結の冒頭、Day18/20の予告表記を修正 | Aoede10件、追加MiniMax0件。Day9の編集済み原投稿も照合 |
| 2026-11-01 v04 | 日別の余分な待ちを詰めて76.125秒へ。リセット種別の切替を字幕に同期 | 追加TTS0件。全decode、音量、49画像、AI全編音声点検を完了。人の試聴と採用は別 |
| 2026-11-01 記事・共有 | 記事草稿と日別表、引用候補、自作図を19メンバーのZIPにし、Driveへ保存 | ZIP全hash・CRC、Driveのサイズ・MIME・所有者を照合。記事公開とスマホ実機は未確認 |
| 2026-11-01 再生の代替 | Driveのプレーヤーが読み込みを続けたため、v04だけをS3up previewで共有 | dry-run後にexit0・verified、サイズ・SHA-256一致、video/mp4・inline、HEAD/全体GETを確認。署名URLとObjectKeyは文書・自作ログ・Gitへ保存しない |
| 2026-11-01 Git保存 | 個人forkへコード・原稿・出典・検査要約と3種類の入口をpushし、Draft PR #10を作成 | main、先行PR、記事公開、YouTube公開は変更していない。最後の共有記録とCLIの既定版も追記 |
| 2026-11-01 v05〜v06 | ユーザーのv04大枠への肯定と2点の修正を反映。1行は中央、複数行は上寄せ、最後8秒に称賛・きらめき | v05の配置試作を保持し、v06で英数字の送り幅の余白も除去。6テスト、52画像、全decode・音量・AI音声点検を完了。追加TTS1件、追加人物生成0件 |
| 2026-11-01 記事v02 | 称賛の締めを草稿と投稿文へ反映。既存の引用・図はhash照合して再利用し、旧ZIPとフォルダーを保持 | 19メンバー、349,515 bytes、全hash/CRCを確認。共通台帳revision38へ返答・新絵コンテ・草稿を保存 |
| 2026-11-01 v07 | 「今回は明るめのループと分類別SE」の追加依頼を反映。124 BPM・Dメジャー8小節を新作し、押下と回復・保管・改善の3音を配置 | 映像stream copy・声WAV一致、追加TTS0。全decode・-15.82 LUFS/-1.30 dBTP、ループ境界、AI音声点検を確認。SE30配置は実施回数の意味ではない。曲の全体既定は変更しない |
