# 制作アーキテクチャ

この案件は同じ公式資料と話題から、1080×1920のショート、1920×1080のフル、ブログ用の記事草稿を出力する。

- `sources.json` は一次資料URL、発表日、画像の取得先、原画像のSHA-256、記事向けキャプションを保持する。
- `prepare.py` は公式画像の原本を確認し、動画向けの注目部分と記事向けWebPを生成する。既存の人物クリップ4本はハッシュで照合して12fpsで展開する。
- `story-v01.json` の表示台詞と読み原稿を分ける。Gemini試行の記録は保存した。レビュー用の `narrate_local.py` はPowerShell 7からSystem.Speechを呼び、Sayaka／IchiroのWAVを検証する。
- `mix_audio.py` はローカル楽曲を照合し、共通 `explanation_v1` の発話中減音と頭尾処理でナレーションと合成する。
- `produce.py` は共通の台詞タイミングと文節字幕を使い、公式図、注目箇所、図解、人物の画面を組む。映像のデコード、音量、字幕、実フレームを確認する。
- `record_workspace.py` は依頼、一次資料、撮影記録、記事素材をStudioに保存する。`package_article.py` は書き出した画像入りのレビューZIPを作る。
- 版、検証、閲覧、採否は [案件記録](RESUME_AND_KNOWHOW_JA.md) へ記録。正本の映像、音声、原画像、レビューURLはローカルの成果物領域と限定Driveで管理する。

[Mermaid構成図](ARCHITECTURE_DIAGRAM.md)
