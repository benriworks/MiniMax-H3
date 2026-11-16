# 納品検査｜2026年11月17日

| 成果物 | フレーム・尺・サイズ | 最終音量 | SHA-256 |
| --- | --- | --- | --- |
| short v02 | 1,498・62.417秒・6,391,691 bytes | −15.05 LUFS／−1.32 dBTP | `319aad21d7ce1bfc4794c9ebb57436770a7e352c705a744517a45f54f219aa99` |
| short v01 | 1,325・55.208秒・6,380,003 bytes | −15.05 LUFS／−1.50 dBTP | `95ba40adff0553b6a835f53d9f6d9c7a80cefdc49bbed2662ad9dd084c693f7d` |
| full v02 | 4,954・206.417秒・20,374,087 bytes | −15.05 LUFS／−1.26 dBTP | `92006ed6e6493dac76d40b06e856e387505ad8ac37912e39a6f90477caa32523` |
| article v01 | 画像4点、ZIP 15項目、135,731 bytes | 該当なし | `4b726bc5fb7f5e3e6d9d84dfb64ad18c406f26cceb99eb6f2c4585b176ed83bc` |

- 両動画のH.264／AAC、1080×1920と1920×1080、24fps、BT.709、全編デコード、Fast start、字幕13状態と51状態を確認。最終フレームは素材に相当する字幕と比較。
- フルv02はAWSの原本を変更。v01/v02のAACストリームのハッシュとSRTのハッシュを照合し、同一。v01は20,065,320 bytes、SHA-256 `273bcc558175e512810ed7e454abac5e324cf90b6ff387546caa40b9d3bfdbf3`。
- ミックスの部分サンプルをFaster Whisperで検査。冒頭でClaudeの利用指数・121・32と、フルで担当・次回の日付・原文確認の語を認識。一部の固有語や漢字、語尾に置換が生じた。人による聞き取りと全台詞は未検査。
- Studio・記事・字幕・BGMの既存テスト42件が成功。PythonとPowerShellの構文を確認。記事ZIPは全15項目を照合。1280pxと390pxのブラウザーで画像4枚、実演の2リンク、横スクロールの有無を確認。
- レビュー用Driveのファイル名、バイト数、親フォルダーと非共有設定を照合。受領書は `outputs/content-projects/CONTENT_20261117_japan_ai_usage/_private/drive-receipt-v01.json`。スマホ再生、通し試聴、採用、公開は確認待ち。

## ショートv02

- `outputs/content-projects/CONTENT_20261117_japan_ai_usage/release/v02/short/` にMP4、SRT、`timeline.json`、`qc.json`、復号した確認フレームを保存。H.264／AAC、1080×1920、24fps、BT.709、Fast start、全編デコード、字幕15状態、図版と人物の読める位置を確認。
- 最初の851フレームの復号MD5と最初の3章の字幕・時刻はv01と全件一致。既存7台詞のWAVを照合。別ファイルで保管するshort v01とfull v02のMP4は、上の表のSHA-256と一致。
- 最終ミックスの38.25秒以降をFaster Whisperで照合。自社テンプレート、お客様の要件、エージェント、1拠点、最後は人が確認して仕上げる、締めの質問を認識した。提案書と見積金額などの漢字表記には置換があった。結果は `_private/asr-short-v02.json`。
- 案件コードのPython構文、共通字幕と会話音声のユニットテスト12件を確認。
- 前回のレビュー用Driveフォルダーでv02のファイル名、6,391,691 bytes、親フォルダー、非共有設定を照合。ローカル受領書は `_private/drive-receipt-short-v02.json`。スマホ再生、通し試聴、採用、公開は確認待ち。
