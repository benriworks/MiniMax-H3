# Fable 5.2解説動画の構成

案件 `CONTENT_20261110_fable_5_2`。動画の生成と記事の素材収集は同じ出典を使い、レビュー状態を媒体ごとに管理する。

| 段階 | ファイルと契約 |
| --- | --- |
| 調査と企画 | `PROPOSAL_JA.md`、`SOURCES_JA.md`、`story-v01.json`。一次資料、単一実演、期待を別に扱う |
| 撮影 | `capture_official.py` が公式ページの全9個のSVG付き図を照合。原本、パネル切り出し、比較表、寸法とhashを保存 |
| 実演 | WindowsのClaude Codeで架空画像を1回。 `prepare_demo.py` が実行記録のモデルIDと値を照合し、抜粋を描画 |
| 人物と音声 | 既存の成人2人とMiniMax素材。 `narrate.py` がAoede／CharonをPCM化。表示原稿と固有名詞の読みを分離 |
| 編集 | `produce.py` が共通音声ミックスと字幕組版を使用。縦横別の引用配置とH.264/AACを出力 |
| BGM v02 | `remix_local.py` がローカル曲庫のhashと既存映像を照合し、音楽と既存ナレーションPCMをミックスしてAACへ差し替える |
| 音声改訂 v03 | `repair_full_voice.py` がフル版の4台詞を個別生成し、元の時間枠に合わせてPCMを差し替え、ローカル楽曲と再ミックス |
| 品質 | 完成映像を全編デコードし、図の切り出し画素、字幕安全域、音量、SHA-256を検証 |
| 受け渡し | フル・ショート、記事草稿、ブログ画像台帳、YouTube文面を版別に保存。Driveは非公開レビュー用 |

`outputs/content-projects/CONTENT_20261110_fable_5_2/` が成果物と原本のルート。API応答、動画、音声、Driveの受領記録はローカルのみに保存する。共通Studioのアプリ構成は [ルートの設計](../../../ARCHITECTURE.md) を参照。
