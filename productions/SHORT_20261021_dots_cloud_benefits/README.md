# dots第2話の補足：クラウドPCのメリット

## Gemini音声の試聴準備

`gemini_voice_trial.py prepare`で冒頭3場面の短い台本とWindows音声を保存し、`generate --output <準備先>`でGemini 2.5 Flash TTSのKore/Aoedeを各1回試す。キーは既存の環境変数からだけ読み、秘密値をファイルやログに記録しない。無効キーや成否不明の送信を自動再試行しない。既存45秒MP4や採用済み音声の差替えは、この試聴経路では行わない。音声の実生成・試聴・採用を、準備完了やモックテスト成功から推測しない。

公式仕様：[モデル](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-preview-tts)、[音声生成](https://ai.google.dev/gemini-api/docs/speech-generation)、[生成API](https://ai.google.dev/api/generate-content)。2026年10月21日確認。

### 実生成に成功した比較候補（2026-10-22）

ユーザー環境変数の新しいキーで認証に成功し、Kore（約9.2秒）とAoede（約8.3秒）の実音声を各1回生成した。[比較ページ](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/gemini-trials/20261022T071259Z-a6d119c9/comparison-v2/release/index.html)と[31秒の比較MP4](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/gemini-trials/20261022T071259Z-a6d119c9/comparison-v2/release/gemini-voice-comparison.mp4)は、Windows Sayaka→Gemini Kore→Gemini Aoedeの順。BGMなし、音量調整済み。原稿・原音・生成記録を保持し、表示の改訂でAPIを再実行しない。

`package_voice_trial.py --output <生成済み試聴先> --revision comparison-v2`は、形式・全decode・音量・入力hashを検査し、既存出力と別の比較版を作る。完成画像のAI補助目視後も、声の自然さ・発音・利用者の好みは試聴で確認する。現在の45秒版にはまだ差し替えていない。キーと署名URLは制作ファイルへ保存しない。

45秒・1080×1920・24fps。手元のPCで動くAI作業と比べ、クラウド側の「電源」「作業の続き」「スマホ」の便利さを説明する。図解・字幕・既存の架空プログラマー男女を使用。元の第2話と全9本は上書きしない。

新BGMは`bright_groove_v1`、112 BPMの明るいプラック、柔らかいベースとシェーカー。旧曲は`electro_pop_v1`、120 BPM。どちらもローカル数式合成で、発話時の減音と完成AACの音量検査を使用する。

公式情報と条件は[SOURCES_JA.md](SOURCES_JA.md)、見出しは[youtube-title.txt](youtube-title.txt)、説明欄は[youtube-description.txt](youtube-description.txt)。例示は実演結果と区別する。クラウド処理を初めて実現したという比較はしない。手元PCの接続・起動、別ログインと承認が必要になる条件も説明する。

```powershell
.\.venv\Scripts\python.exe -m tools.studio.shorts_creator make --story productions/SHORT_20261021_dots_cloud_benefits/creator-story.json
```

## 確認用の完成候補（2026-10-21）

- [再生ページ・BGMの試聴](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/release/index.html)
- [完成MP4](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/release/dots-02-extra-cloud-benefits.mp4)
- [新BGM単体](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/release/bgm-bright-groove.mp3)
- [動画・カバー・字幕・見出し・説明欄一式](../../outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/dots-02-extra-cloud-benefits.zip)
- [検証記録](../../verification/shorts-dots-cloud-benefits-2026-10-21.json)

完成MP4は45.000秒・1,080frames・H.264/AAC、12,027,437 bytes。SHA-256は`548648347329D3F06026D820A300F5229EF104A44ECE62641F351CC737442969`。−16.10 LUFS、true peak −1.50 dBFS。全decode、全frameの文字領域検査、10場面の360px幅のAI補助目視と45秒コンタクトシート確認に合格。関連Pythonテスト12件が成功し、既存9本のMP4照合値は変更なし。11ファイルのZIPをCRC・全member hashで読み戻した。

状態は`verified_candidate_awaiting_user_review`。利用者による聴感・内容の採用、正式な人のレビュー、YouTubeへの投稿は未確認。初回準備の尺超過と素材尺不足は別の日時フォルダーに残し、台本を短くして成功した今回の出力だけを納品する。公式原文の研究用スナップショットは`research/`へ保存し、公開用一式へは含めない。

再梱包は、実際に完成画像を確認して`verification.json`へ記録した出力先に限り、`deliver.py --output <出力先>`を使う。既存のreleaseとZIPを上書きしない。
