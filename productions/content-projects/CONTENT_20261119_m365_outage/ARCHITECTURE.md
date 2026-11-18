# Microsoft 365障害動画の制作構成

公開情報の調査資料、版を固定した台本、検証済み音声の三つを別々に管理する。案件のコードを置くworktreeと、大きな素材を置くローカルルートを分ける。[図](ARCHITECTURE_DIAGRAM.md) と [入力ハッシュ](input-manifest-v02.json) を併用する。

|工程|入力と出力|
|---|---|
|公開資料の確認|[capture_sources.py](capture_sources.py) がWindowsのChromeで公開告知・ステータスを開く。画面の文字の領域と実際のスクリーンショットを同じ表示条件で切り出す。短い英語の原文は公開写しPDFの文字座標を基に画像化。元画面・PDFはローカルの `_private/capture`。|
|ナレーション|[narrate.py](narrate.py) が表示原稿と別の読み原稿で共通のGemini TTSを呼ぶ。[v02の変更](revision-v02.json)は一言。元録音と受付記録を保存し、残り21台詞は再利用。|
|画面と音|[frames.py](frames.py) の実測枠、人物、図、原文を [produce.py](produce.py) がPCMの尺へ配置する。既存の日本語文節処理、音声配置とBGMミックスを使用。別版フォルダーへMP4・字幕・時系列・検証台帳を書き出す。|
|記事と台帳|[package_article.py](package_article.py) が原稿と経路の図から図入りPDF、HTML、ブログ用MDX、ZIPを生成。[record_project.py](record_project.py) は共通CLIに依頼原文・出典・判断を保存し、ユーザー承認を追加しない。|

## 同じPCでの再開

1. 素材ルート `outputs/content-projects/CONTENT_20261119_m365_outage/` を確認。人物は統合作業コピーに保存した `outputs/content-projects/CONTENT_20261103_model_race/assets/` の3本。入力名・バイト数・SHA-256、フォント、FFmpegの版は入力台帳にある。
2. 通常の再編集は保存済みの `captures/`、`motion/`、`voice/selected-v02/` を使う。原音は24kHz・モノラル。外部資料が更新された場合は情報の新しい版を作り、以前の撮影原本を旧版用に保持する。
3. 以下は案件ディレクトリからの実行例。素材ルートは実在する絶対パスを渡す。再生成検証をするときは別の素材ツリーに入力だけを複製して実行する。既存の `release/v02` へ上書きしない。

```powershell
python produce.py preview <素材ルート> --version v02
python produce.py render <素材ルート> --version v02
python record_project.py <素材ルート>
```

資料を改めて取得する時は `capture_sources.py` を新しい撮影先に使う。人物の派生の再作成は `produce.py motion <素材ルート> --motion-source <人物素材ルート>`。新しい台詞を作る場合だけ `narrate.py` を使う。選択済みの音声からの再編集にTTSの新規呼び出しは不要。

記事はReportLab・MarkdownIt・PillowのあるバンドルPythonで `package_article.py <素材ルート>`。PDFの日本語は印刷・プレビュー用にWindowsのBIZ UDPゴシックを埋め込む。出力PDFは文字とリンクを確認し、Popplerで各ページを画像化して確認した。人による全編確認と他PCでの再現は未実施。
