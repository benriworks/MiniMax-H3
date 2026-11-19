# PHP比較解説の制作構成

`capture.py`はPHP・IPAの公開ページをローカルChromeで撮影し、元画面と文字範囲を対応付ける。開発元の告知APIからは公開日、CVE、深刻度、URLのみを記録する。`media_inputs.py`は冬服v02の4素材とローカルBGMのSHA-256を照合する。

`story-v01.json`は媒体別の章・画面、表示文と読み原稿、話者を保持する。`voice.py`は同じ台詞を1回だけ生成し、`tools.studio.dialogue_narration`の受付・音声キャッシュを使う。`produce.py`は24kHzの実サンプル数から24fpsの時刻表を作り、共通の文節字幕へ渡す。`layout.py`は縦横別の配置で比較表、保存の例、原文の抜粋、人物の反応を描画する。

書き出しと音量合わせは[日本のClaude利用案件のエンコーダー](../CONTENT_20261117_japan_ai_usage/render.py)と[ミックス関数](../CONTENT_20261117_japan_ai_usage/mix_audio.py)を再利用する。ファイル名、画面サンプリング、音源の明示指定を受け取れる。省略時は従来の案件の呼び出しと同じ設定が入る。今回の作業用フォルダーを検証後に確定名へ移す。字幕・時刻表・全編デコード・AAC測定値・実フレームを各MP4の隣に置く。

Studioの共通CLIには調査・撮影・企画・依頼原文・記事を登録する。共有は認証済みの個人用Driveでファイルを読み戻す。生成媒体・受付・共有レシートはGit外。[Mermaid図](ARCHITECTURE_DIAGRAM.md)／[再現手順](REPRODUCTION_JA.md)
