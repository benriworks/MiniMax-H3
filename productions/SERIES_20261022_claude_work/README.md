# Claude 資料作成ショートシリーズ


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

架空店舗「灯台珈琲」の同じ企画を使い、Docs、Slides、Design、部分修正、書き出しを各30秒・7場面で紹介する5本です。実際の初回出力と修正を保存し、公式ページの説明と実演画面を分けます。YouTube公開は行いません。

| 回 | 見出し | 実際に示す内容 |
|---|---|---|
| 01 | 【Claude】メモから企画書へ！Docsで下書きと修正を試す | 650円・3万円の入力、初回予算欄、見出しと太字の修正 |
| 02 | 【Claude】同じ企画を5枚に！Slidesで会議資料を作る | 初回5枚の枚数、修正後の日程、提供時間と告知方法 |
| 03 | 【Claude】告知デザインを見やすく！文字と余白を整える | 価格・提供時間の拡大依頼と同倍率の前後比較 |
| 04 | 【Claude】この一文だけ直したい！選んだ場所から修正する | 目的文の修正。文意も強くなったため意図の再確認を明記 |
| 05 | 【Claude】作った資料を持ち出す！Word・PowerPointに書き出す | 本当に保存したPPTX・DOCXを実アプリで開き、数値と見た目を確認 |

## 現在の状態

2026-10-23に全5本を`packaged`まで完了しました。各30秒・1080×1920・24fps、Aoede音声・BGM・字幕付きです。親担当が完成MP4由来の全35場面と各30フレーム一覧、さらに第3回の人物素材終了後の3フレームを実際に確認しました。独立集約監査でMP4形式、ZIP各10メンバーのCRC/hash、公式5場面・実演20場面・人物10場面、旧26動画の不変を照合済みです。最新納品は本フォルダーの`delivery.json`、検証は`verification/shorts-claude-work-2026-10-23.json`です。最終試聴・ユーザー採用・YouTube公開は未実施、S3共有は別の送信記録で管理します。

最初のClaude音声リクエストは古いprocessキーにより`api_key_invalid`で明確に拒否されました。拒否履歴を保存し、ユーザー環境に保存済みの現行キーを値を表示せず読み直した後、親の明示指示で1回だけ置き換えました。第1回は検証済み7件に加えて過去拒否1件を別計上します。実際の請求額は未確認です。

## 再現手順

1. `_private`の原本PNG/JPEG、取得日時JSON、実DOCX/PPTXを変更せず保存する。
2. `prepare_native_captures.py`または固定の追加計画`audit-20261023/prepare-additional-crops.py`で矩形のみを切り出す。個人情報、内部指示、会話履歴を公開cropから除く。実画像の目視後にproofを確定する。
3. `verify_docx_exports.py`、`verify_pptx_exports.py`で読み取り専用のXML・数値・CRC検査を行う。アプリで開いた外観は別の実画面証拠で確認する。
4. `build_story_drafts.py --episodes all --media-proof outputs/characters/explainer-motion-20261022/claude-shiori/verification.json`で新しい時刻フォルダーに草稿を作る。過去の草稿は上書きしない。
5. `render_review_frames.mjs <draft-folder> <new-review-folder>`で完成サイズの静止画を確認する。仮の等間隔タイミングであり、音声同期の確認にはしない。
6. 採用した草稿を`NN/creator-story.json`、見出し・説明・出典を同じ`NN/`へ保存し、`produce.py preflight --episode N`を通す。
7. `produce.py generate --episode N`、`prepare`、`render`を順に実行する。音声は1バッチずつ、フル動画の描画も1本ずつにする。
8. 完成MP4の全7場面・遷移・字幕・30フレーム一覧を実際に確認してから`review --note ...`、`package`を実行する。利用者の採用、最終試聴、YouTube公開は別の状態として残す。
9. 全5本が`packaged`になってから`finalize.py`を実行し、現在のMP4形式、ZIP全メンバーとCRC/hash、35発話と拒否1件、公式5場面・実演20場面、人物10場面、旧成果物の保持を集約照合する。成功時だけシリーズ`delivery.json`と`verification/shorts-claude-work-2026-10-23.json`を保存する。

描画だけを改訂する場合は`refresh-prepare --episode N --note ...`で旧stateと出力全ファイルのhashを保管し、検証済み音声から新しい出力世代を準備します。台詞や音声を再生成しません。`render_prepared_review.mjs <new-review-folder> <01,02,...>`で実際の準備済みタイミングによる冒頭・締め・素材終了後の静止画を別フォルダーに出します。フル描画の標準出力とエラーは各出力世代の`render-*.log`へ保存します。

Python/Nodeはワークスペースの既存ランタイムを使用します。APIキーをファイルやコマンド出力に残しません。`generate`だけが有料音声へ送信します。最大7場面、Aoede、既存の`gemini-2.5-flash-preview-tts`、最低22秒の送信間隔です。既存の検証済み音声を再利用し、未完了・結果不明の送信は自動再試行しません。キー更新のために生成状態を消すこともしません。

## 証拠の範囲

- 公式情報は[SOURCES_JA.md](SOURCES_JA.md)。画像撮影は2026-10-22、2026-10-23の公式再読で主な説明に変更がないことを確認。英語の短い引用と出典を引用場面に併記する。
- 第2回の初回一覧は本当の初回JPEGから切り出したもの。5カードの枚数確認だけに使い、細かな本文の可読性を主張しない。後から初回画面を再現していない。
- Docsの初回・予算修正版は読み取り専用の履歴を表示して再撮影。履歴の復元や再生成をしていない。
- 部分修正は「平日午後に来店するきっかけを作る。」から「平日午後の来店を増やす。」へ変化した。単なる短縮で意味が完全に保存されたとは説明しない。
- Wordは予算修正後の`01-docs-revised.docx`。PPTXは日程修正後の`02-slides-revised.pptx`。異なる時点の成果物を同じ最終版として扱わない。
- PowerPointのbasic fontsでは明示書体がArial。日本語の実際の代替書体と外観は実アプリで確認する。未設定の来店数・売上・割引率は5枚目の発表者ノートに保持され、スライド本文に表示されるとは説明しない。
- 案内役は架空の成人「佐伯栞」。新しいMiniMax動画と元PNG・I2VAキー画像のhashで結び付ける。生成動画の音声は使用しない。

個人情報を含みうる文脈原本、API関連履歴、実入力の内部指示は公開ZIPに入れません。公開ZIPはMP4・表紙・字幕・台詞・見出し・説明・出典・品質報告・視聴ページ・全メンバーhashの10ファイルです。構成は[ARCHITECTURE.md](ARCHITECTURE.md)、処理図は[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)を参照してください。
