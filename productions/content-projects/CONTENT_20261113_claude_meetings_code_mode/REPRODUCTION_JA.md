# 再現手順 v01

コード版の基点は `fork/main` の `2881c88`。Windows 11、Python 3.12.2、PowerShell 7.6.9、System.Speech 10.0.0.14、FFmpeg 8.1.2。フォントはStudio同梱のNoto Sans JP。PythonはPillow、numpy、BudouX、markdown-it-pyを使う。

1. 公開出典と照合したPNG6点を `outputs/content-projects/CONTENT_20261113_claude_meetings_code_mode/captures/original` に置く。最初の3枚は公式サイトの原本。追加3枚は幅1600×1050の独立Chromiumで公開ページを撮影。 `sources.json` と `captures/figures/manifest.json` で入力名、元ハッシュ、寸法、注目箇所を確認する。
2. 既存人物の4 MP4を用意し、 `prepare.py --motion-source <4本のフォルダー>` を実行する。人物ファイルを変更した場合は照合で停止する。元クリップのハッシュはコードと台帳にある。
3. ローカルにある `happytime.mp3` を案件の `outputs/.../_private/` に置き、 `sources.json` のSHA-256と一致させる。元のSSDパスはローカル曲庫台帳で確認する。
4. レビュー版と同じ声は、 `narrate_local.py` をPowerShell 7のある環境で実行して声の出力・台詞の実尺を確認する。表示原稿は `story-v01.json`、読みに変換した原稿・入力とWAVのSHA-256は `voice/local-v01` に記録。既存ディレクトリーがある場合は上書きせず、検証済みWAVを使う。
5. `produce.py preview short` と `produce.py preview full` で紙面・字幕を確認し、新しい版の出力先で各 `render` を実行する。完成したMP4とSRT、タイムライン、検査結果のSHA-256と版を照合する。
6. `record_workspace.py` と `package_article.py` を順に実行し、出典と画像を受け渡す。ZIPの画像版、15メンバーのchecksumと390px・PC幅の表示を確認する。

Geminiの試行記録はローカル `voice/v01`。課金環境を回復して声を変更する場合は、新しい音声版と動画版を使う。旧版のGemini拒否記録を削除して再送しない。この制作で使ったローカル音声と `narrate.py` の当初のGemini経路を区別する。音声のOSビルド差や、別PCでの出力一致は未検証。
