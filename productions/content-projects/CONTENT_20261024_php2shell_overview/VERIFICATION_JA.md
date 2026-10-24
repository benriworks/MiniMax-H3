# 検証記録

2026-10-24。人物入りv02を確認候補としてDriveへ保存。最終試聴・採用・公開とは分ける。

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
