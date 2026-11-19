# Microsoft 365障害動画の制作構成

## フルv03とショートv01の再編集

素材基点はメインcloneの `outputs/content-projects/CONTENT_20261119_m365_outage/`。制作コード、入力のハッシュ、実フレーム確認結果は本worktreeにある。[新旧の構成図](ARCHITECTURE_DIAGRAM.md) ／ [入力・出力の検証台帳](verification-pair.json) ／ [編集内容と保存場所](PAIR_REVIEW_JA.md)。Python 3.12、FFmpeg、Noto Sans JPの同一フォント、Pillow、BudouX、NumPy、SciPyを使用。入力照合には台帳の各ファイルのbytes・SHA-256を使う。

1. Windows版Chromeで `capture_pair.py <素材基点>` が公開ページを開き、1440×900 CSS px・倍率1.5で撮影する。元画面、PDF、URL、確認時刻は `_private/revision-03/official/`。公開範囲の原本上の座標は同フォルダーの台帳。保存済み原本から切り直すときは `--recrop`。
2. 既存の思案・納得は `CONTENT_20261103_model_race/assets` の男女各2本。新規の驚きは `CONTENT_20261030_chatgpt_pro_usage_news/characters` の承認済み男女参照画を使用。参照画の全幅を使い、上端を高さの20％として正方形を切り出し、768角のLanczos・JPEG品質96で保存した。案件の男女別I2VAプロンプトと、ドラマ案件の `generate_h3_shot.py` にこの画を渡し各5秒を生成。原本・受付・使用量は `motion/revision-03-{male,female}-surprise/`。再編集には保存済みのMP4を使う。
3. `pair_cast.py <素材基点> <既存人物MP4のフォルダー>` が6素材を12fpsの動きに整える。音声はフルの先頭22台詞が `voice/selected-v02`、追加の7台詞は `voice/pair-v03`、ショートの入試台詞のみ `voice/pair-exam-02`。表示原稿と読みは `dialogue-pair.json` に分けた。選択音声の作成は `pair_narration.py`。既存原本から編集する場合は生成APIへの新規依頼は不要。
4. 両版とも案件フォルダーで `python render_pair.py preview full <素材基点>`、続いて `python render_pair.py render full <素材基点>`。短尺では `full` を `short` に替える。編集リストは `pair_edit.py`、横・縦の描画は `pair_frames.py`。組み立ては検証済みのPCMの長さ、共通字幕の実測幅、カット内の人物表示を使う。書き出し済みMP4は上書きしない。新規改訂では別の版名を設定する。
5. `incident_score.py` が曲をフルと短尺のカットに合わせて作り、声に合わせた音量制御と二段の音量正規化を経てAACへ変換。両版とも全編デコードし、字幕・長さ・音量を確認する。
6. 記事はバンドルPythonで `package_article.py <素材基点> --pair`。元の3ページと追補を新しい4ページ版へ組み、HTML・MDX・寸法つき画像とZIPを `article/v02/` に作る。最後に `verify_pair.py <素材基点>` で書き出し後の標本・縦カバー・検証台帳を生成し、`record_project.py <素材基点> --pair` で返答原文・公式画像・2本の構成・記事版を共通CLIへ保存する。

## フルv01・v02

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
