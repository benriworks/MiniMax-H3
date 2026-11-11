# 制作アーキテクチャ

対象は `CONTENT_20261112_claude_artifacts_apps`。Windowsの日本語Web版から採録した試食会の実演を中心に、縦と横のレビュー動画および記事草稿を作る。

- `PROPOSAL_JA.md` はユーザー原文とv01の制作方針を保持する。`SOURCES_JA.md` は公式資料と実操作の範囲を記録する。
- `prepare.py` は元画像から撮影範囲を切り出し、元画像と切り出しの寸法・ハッシュを記録する。Excel出力のOOXMLから式と保存値を読み、入力値から独立に計算する。既存の人物クリップはSHA-256を確認してフレームを展開する。
- `narrate.py` は `story-v01.json` から話者別の音声を用意する。StudioのGemini音声と検証済みPCMを再利用する。受信済みの不完全な応答は保持し、別テイクを明示的に選べる。
- `produce.py` はStudioの台詞配置、字幕分割、BGMを使う。字幕と写真を縦横別にレイアウトし、H.264とAACのMP4、SRT、タイムライン、検査結果を出力する。
- `package_article.py` は共通Markdown、HTMLプレビュー、撮影図版、参照元、検証用ファイルをレビューZIPにまとめる。`record_workspace.py` は出典、制作依頼、企画、撮影範囲、記事をStudio CLIに登録する。
- 動画、音声、撮影原本、非公開リンクはローカル成果物または限定のDriveに置く。Gitには再現方法、台本、編集判断、出典、検証記録を保持する。

図は [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) に記す。
