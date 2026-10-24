# 検証記録

最新は末尾のv04（2026-10-25）。以下のv02/v03記録も保持する。最終試聴・採用・公開とは分ける。

| 状態 | 現在の証拠 |
| --- | --- |
| 企画・人物採用 | ユーザーの明示的な返答を対象提案・人物版1へ記録済み |
| 調査・撮影可否 | 一次資料7件と確認日を保存。このPCでPHP公式を表示・取得。公開用は告知見出しと日付の切り出し |
| 共通処理 | Python関連38件、TypeScriptの引用URL・50秒タイムライン2件に合格。Studioのbuild成功。bundleサイズ警告あり |
| Aoede原音声 | 9送信、9件の完了proof。原稿・hash・PCM一致。発話33.778625秒。追加の自動再送0件。実請求額は未確認 |
| 初稿v01 | 人物差し込み前の比較用。50秒・1080×1920・24fps、H.264/AAC、全decode、-16.01 LUFS、true peak -3.94 dBFS。9枚の360px幅デザイン静止画をAI確認 |
| 人物原動画 | MiniMax H3 I2VA成功。768×1376、24fps、124frame。実生成1627.1秒。全decode、0〜4秒の各フレームと2秒の拡大像をAI確認。顔・眼鏡・衣装・2本の腕に明らかな破綻なし。原本・初回拒否・修正spec・完了history・来歴を保持 |
| 人物入りv02 | 50秒・1080×1920・24fps、H.264/AAC、6,282,891 bytes。全decode成功。-16.01 LUFS、true peak -3.94 dBFS。完成MP4由来の全9場面を360px幅でAI確認。顔と字幕を分離。初稿と発話PCM完全一致 |
| Google Drive | 「動画・ブログ制作レビュー」内の案件v01フォルダーへMP4とYouTube説明欄案を保存。metadata/listの読み直しでファイル名・容量・保存先・owner権限・can_downloadを確認。非公開。スマホ実機での再生は未確認 |
| 人による最終試聴 | 未確認 |
| 最終動画のユーザー採用 | 未確認 |
| YouTube公開 | この作業では実施していない |

音声は発話ごとのPCM時間で配置し、字幕の語句内時刻は文字量から配分する。単語アラインメントや人による全編視聴の証明ではない。

初稿のMP4：`outputs/productions/SHORT_20261024_php2shell_overview/20261024T131610722057Z/shorts-creator.mp4`。hash `097953ACE5C3AF6D8348ED907AF762F79FBEAB38ACB0F9B2669052A8AFB6678C`。この初稿を完成版として共有しない。

完成候補：`outputs/productions/SHORT_20261024_php2shell_overview/20261024T133431012463Z/release/php2shell-overview-v01.mp4`。hash `83811044FA48F083952B266BD26EB22ABD4C4806CD93C978A66A4E3C257F20F1`。人物原動画hash `474F0815C24FE1F803D2C5A4745DE8847D982C50C24A7B63A7FFEDB0E4173C89`。生成元は採用画像hashと一致。

完成候補の `verification.json`、`ai-visual-review.json`、`package-verification.json` に技術・AI確認・ZIP内容の照合を保存。組み立て処理自身は人物を生成しないため、共通finishの `new_video_generation:false` は組み立て工程の範囲。案件の `delivery.json` には今回の新規MiniMax人物生成を別記している。

ローカル `file://` のブラウザー再生はブラウザーのURLポリシーで拒否された。別経路で回避していない。FFmpeg全decodeと実MP4の抽出画像による確認を実施した。人の連続再生・聞き取り・モバイル実機は上表のとおり未確認。

共有リンクとread-back受領は `outputs/content-projects/CONTENT_20261024_php2shell_overview/drive-review-v01.json`。GitHubには動画・音声・ZIP・共有受領を含めない。YouTubeへは投稿していない。

## v03・60秒候補（2026-10-25）

- 完成MP4：1080×1920、24fps、1440frame、60秒、H.264/AAC。7,338,286 bytes。hash `7FD62DF412205B75AE93080FB4B91236D9DFB3B01E8D5114C1F141A6E0281B9A`。全decode成功。音量-16.02 LUFS、true peak -2.06 dBFS。
- 音声：冒頭4場面のみAoedeで新規生成。後半8場面は元の完了proof・原稿・PCMを照合して再利用。人物も同じ採用済みMiniMax動画。今回の新規MiniMax生成0件。追加Gemini要求4件、今回までの案件内要求13件。実際の請求額は未確認。
- 図解：利用者・ブラウザー、サーバー内のWordPress等とPHP、アクセス・処理・応答を自作。完成MP4由来の全12場面と、応答の矢印が完成した時点を360px幅でAI確認。重要文字の安全域検査に合格。
- 統計：W3Techsの2026-10-24データ、Japan 92.4%。国内サーバーかつサーバー側言語が判別可能なサイトという分母、出典とデータ日を表示。公式ページはこのPCで追加撮影した。影響率や日本の全サイトの割合として説明しない。
- 共通処理：今回のPython関連13件とStudio buildに合格。Reactのhook・決定的描画・代替説明・直接import・表示の確認を実施。既存buildのbundleサイズ警告は残る。
- Drive：非公開の案件v03フォルダーにMP4、見出し・説明欄・出典のテキスト、図解PNG2枚を保存。metadataとフォルダー一覧でファイル名・容量・保存先・owner権限・ダウンロード可能を確認。スマホでの連続再生は未確認。
- 記事向け派生：`blog-assets/v03/` に828×590の図解PNGを保存。元の描画・完成MP4抽出フレーム・コード・切り出し矩形・hashを対応付けた。実演や公式スクリーンショットとして扱わない。記事への採用は未確認。
- 人の最終試聴、v03のユーザー採用、YouTube公開は未確認・未実施。ローカルfile URLのブラウザー再生は既知の制限があるため、代替経路で回避していない。

出力：`outputs/productions/SHORT_20261024_php2shell_overview/20261024T163345527432Z/`。最新の動画台帳は `delivery-v03.json`。共有受領と最新ポインターは案件のoutputs側に保存し、Gitには入れない。

## v04・人物の表情と仕草だけを改訂（2026-10-25）

- MiniMax H3 I2VA成功：新規のローカル生成1件、実生成1560.888秒。768×1376、24fps、124frame、原本2,610,554 bytes。元の採用画像hashは人物版1と一致。生成原本hash `3CD63782DF8C5E0E03AC8B9302B614A33694FBE6F3BFF87C424DF56C283F3713`。
- AI確認：0〜4秒の各フレームと2秒の拡大像を確認。同じ顔・眼鏡・衣装、軽い困り顔、緩い右拳を顎の下へ添える動作、目と口の可視性、腕と手に明らかな破綻がないことを確認した。初期の元画像の笑顔を避けてsource frame 24から91frameを使う。
- 完成MP4：60秒、1080×1920、24fps、1440frame、H.264/AAC、7,130,871 bytes。hash `2B09D0A1A9A9202DE14648A1B785D907FAC71A25E256B16B34BAEBDA2C863E29`。全decode成功。-16.02 LUFS、true peak -2.06 dBFS。
- 保持検証：変更は冒頭mediaとsource開始位置のみ。PCM・BGM・効果音・時刻・字幕SRTが元版とbyte一致。AACは再圧縮せずstream copyし、packet hash一致。後半11場面のレンダー確認画像はv03と画素一致。H.264動画のpacket全体が一致したという意味ではない。
- 完成映像のAI確認：0.25秒・1.5秒・3.3秒の360px画像で、冒頭の困り顔、拳が顎へ近づいて保持する流れ、字幕が顔と手を覆わないことを確認。人による連続再生と最終試聴は未確認。
- 追加のGemini要求0件、MiniMax有料API要求0件。人物生成用に起動した専用ComfyUIは完了・queue空・PID/出力先の一致を確認して停止した。
- Drive：別の非公開v04フォルダーへ60秒MP4、無音の人物素材約5秒、前版と同じ見出し・説明欄・出典を保存。metadataと一覧で名前・容量・保存先・owner権限・ダウンロード可能を確認。スマホ実機再生は未確認。
- v04の最終ユーザー採用とYouTube公開は未確認・未実施。人物版1の採用と、今回の動作修正の指示を完成品の採用へ拡大していない。

出力：`outputs/productions/SHORT_20261024_php2shell_overview/20261024T190421758377Z/`。保持検証は `preservation-v04.json`、AI確認は `ai-review-v04.json`、最新台帳は `delivery-v04.json`。旧v03の台帳・動画・素材を保持する。
