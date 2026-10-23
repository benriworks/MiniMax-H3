# dots 第5〜9回の最終改訂アーキテクチャ

`produce.py`は第5回を30秒、第7回を45秒へ改訂し、既存のStudio共通Shorts処理を呼ぶ専用ドライバー。UI・API・DBの変更はない。第6・8・9回は完成済み動画をhash照合して再利用する。

前シリーズのrender_story、voice-source、完成MP4を検証してから独立した新IDの台本を固定する。読み上げ済みの正確な発音置換後原稿が一致する発話だけを再利用し、変更分を既存Geminiアダプターで生成する。モデルはgemini-2.5-flash-preview-tts、声はAoede。既存の22秒間隔・共有ロック・送信前markerを使う。不明な送信を自動再試行しない。

音声WAVのsample数と場面原稿・request・SHA-256を照合し、尺に収まることを確認する。prepareから共通Remotion renderer、finishへ渡す。人物は旧dotsシリーズの男女MiniMax動画を全面で使い、公式引用画像は元の撮影証跡を照合して再利用する。旧作のstate・MP4・ZIPを変更しない。

独立出力には動画、台本、字幕、見出し・説明欄、画面確認と音声由来の記録を保存する。Google Driveへのアップロードは接続ツールによる個別操作で、Studioが自動送信する実装ではない。readbackは名前・容量・親フォルダー・権限の確認であり、人によるモバイル試聴の代わりではない。動画と音声はGitHub保管対象外。
