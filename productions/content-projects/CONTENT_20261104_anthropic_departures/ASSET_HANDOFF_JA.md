# ローカル保存と記事への受け渡し

2026-11-04。最新はショートv01、共通記事草稿v02。旧草稿と初回出力は保持する。

| 種類 | リポジトリからの相対パス | 状態 |
| --- | --- | --- |
| 最新動画 | outputs/content-projects/CONTENT_20261104_anthropic_departures/release/v01/short/anthropic-departures-short-v01.mp4 | 45.75秒の技術確認済みレビュー候補 |
| 台詞と読み | productions/content-projects/CONTENT_20261104_anthropic_departures/short-dialogue-v01.json | 6台詞。草稿と別保存 |
| 元の声 | 同outputsのvoice/v01/s01〜s06/ | 初回の24kHzモノラルWAV、要求・受領・検証記録 |
| 人物と引用 | 同outputsのassets/、asset-manifest-v01.json | 既存男女とMiniMax動作の再利用、短い引用と元hash |
| 実フレームと字幕 | 同outputsのrelease/v01/short/decoded-frames/、captions.srt | 字幕12状態と頭尾の計14実画像 |
| 記事草稿 | productions/content-projects/CONTENT_20261104_anthropic_departures/ARTICLE_DRAFT_V02_JA.md | blog用共通Markdown。未採用・未公開 |
| 記事用包装 | 同outputsのarticle/v02/、review/delivery-v01/anthropic-departures-article-v02.zip | 6公開画像、出典、hash、本文、見出し、字幕等。動画・音声・私的原本を含めない |
| 私的原本・共有受領 | 同outputsの_private/ | 撮影原本、AI応答、Drive受領、再生確認の制限。Gitと公開包装の対象外 |

記事画像は短い本人投稿3枚、公式PM記事見出し1枚、自作の横図2枚。引用は本文から原投稿へ戻れるようにし、本人投稿と会社公式を別の名義で示す。Xの原寸切り出しは582px幅、公式見出しは765px幅で、ページ全幅2545pxを本文の解像度と呼ばない。本文の日本語要約と出典リンクを併用し、拡大してネイティブ解像度が上がったとは扱わない。図は1920×1080。

アプリ操作は今回の退社発表を証明する実演に当たらず、公式サイトと本人投稿の実画面を準備時に確認・撮影した。今回の追加ブラウザ確認はWork設定で無効のため、新しい画面を撮ったとはしない。

blogのAGENTS.mdとトーン・ビジュアル規定を確認した。動画の男女をブログの案内役へ自動転用しない。MDX、frontmatter、媒体側カバーと案内役バナー、記事用公開パス、blog側の検査・mainマージは残作業。noteへ変える場合も共通草稿・出典・原素材を保つ。

スマホ用のレビュー入口はDriveのMP4への直接リンクを使う。保存済みの動画と記事は別の採用対象で、人の試聴・完成品採用・公開を記録する。Driveが保存できているため、S3へ二重送信しない。
