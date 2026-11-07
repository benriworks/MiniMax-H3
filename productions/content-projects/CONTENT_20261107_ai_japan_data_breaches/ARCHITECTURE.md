# 国内情報漏えい解説の制作構成

2026-11-07。最新は公表件数順へ改訂したフルv03、ショートv03、記事草稿v03。図は独立した[Mermaid図](ARCHITECTURE_DIAGRAM.md)。共通Studioの実装は既存の機能を利用し、案件専用コードを案件フォルダーに置く。

## 事実と採用の管理

[事件台帳](incidents-v01.json)は数量単位・確度・内数と関連区分・公表原因・出典IDを保持する。[出典台帳](sources-v01.json)はURL・確認日・原本のhashと取得失敗を保持する。`build_research.py` は数量と重み、出典IDを照合し、比較表を再計算する。元資料が変わった場合は依存する企画・記事・台本を再確認する。

v03の `rank_volume.py` は主たる公表件数で並べ、別種の保管数や指定除外を適用する。人口は公式の同一基準日の公表値から比較だけを計算する。v02の重み付き表は履歴として残す。[v03の件数表](ranking-volume-v03.json)

企画v02は既存ContentWorkspaceの `feedback` と `accept` で記録した。公式資料、前作の白衣人物、場面台帳、最終MP4、記事草稿を `record_workspace.py` で登録する。企画の採用と、書き出した動画の検査、人の採用、公開は状態を分ける。

## 画面と音声

`capture_sources.py` はEdgeの画面と元の公式PDFを保存し、`refine_captures.py` は引用箇所を選び直す。記事の原表と動画での拡大は別の派生とする。`generate_voices.py` はGeminiの台詞単位PCMと受領を保存し、同じ受領があれば再利用する。表示文と読み文は独立させ、ショートの修正は1行の版を残す。

`visuals.py` は実尺台本と、保存済みMiniMaxの人物フレーム・公式引用・自作図を縦横別のレイアウトへ割り当てる。`produce.py` はPCMから台詞時刻を求め、共通 `editorial_captions` で字幕を割り付ける。固定フレームレートで書き出し、共通合成BGMを穏やかにミックスし、最終MP4を全decodeする。

`build_article.py` は同じ出典から記事草稿、引用、自作図をローカルHTML・PDF・受け渡しパックへ変換する。Gitは軽量な正本、原資料・素材・媒体・私的なDrive受領はoutputsに保持する。[再現手順](REPRODUCTION_JA.md)と[検査記録](PRODUCTION_QC_V02_JA.md)。

v03の `capture_v03.py` は第一興商の初報・続報、佐川急便と公式の人口資料を追加撮影する。`visuals_v03.py` はケースごとの対象項目、比較バー、送り状の図を既存の字幕・人物・出力処理に渡す。新規と再利用の台詞は個別の受領へ結び、`record_v03.py` で新旧の版を共通台帳へ記録する。[改訂と検査](REVISION_V03_JA.md)
