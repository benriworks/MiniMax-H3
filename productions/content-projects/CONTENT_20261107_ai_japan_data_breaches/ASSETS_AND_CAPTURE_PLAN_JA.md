# 引用・撮影と記事用素材

2026-11-07の制作結果。公表原本は案件outputsの `research/primary-v01/`。[出典台帳](sources-v01.json)で原本の取得日とhashを確認できる。

## 撮影と切り出し

- PCのMicrosoft Edgeで公開ページを撮影した。1536×1050 CSS px、DPR 2を基本とし、Cuenoteの対象表はDPR 3で再撮影。原本の状態と試した経路は `research/captures-v01/capture-manifest.json`、追加選択は `selected-excerpts-v02.json`。
- アララ、無印良品、KDDI、バーガーキングは公式PDFの該当ページを画像化。公式PDFの抽出とEdgeの実ページ撮影は区別する。佐川のページ本文はEdgeで表示。アララの告知ページでは数量の行が見つからず、公式第3報PDFを動画・記事の根拠にした。
- Cuenoteは初回に選んだ箇所を外し、件数の確度を示す見出しのある表を引用した。フルv02では右2列を拡大し、元表と要約の位置を分けた。
- NCSCは章見出しの範囲を切り出し、写真部分を除いた。IPAの本人確認書類に関する案内は必要な箇所だけ引用。タイムズカーは原表の2区分を照合し、動画では自作カードにした。
- 公開アプリの機能や実際の被害を再現する企画ではない。例の通知は架空で、実在の利用者情報とアカウントは収集していない。

## 記事の素材

| 画像 | 使う範囲 | 参照 |
| --- | --- | --- |
| アララ第3報 | 重複除外後のアドレス数の行 | [公式PDF](https://contents.xj-storage.jp/xcontents/AS71226/0d5f3847/6172/4bcc/bfab/73896dab795d/20261106211906670s.pdf) |
| Cuenote第2報 | 痕跡とおそれの列を含む対象表 | [ユミルリンク](https://www.cuenote.jp/information/news/unauthorizedaccess2.html) |
| 無印良品第2報 | アプリ・ネットストアの会員データの行 | [公式PDF](https://files.microcms-assets.io/assets/1abbce69114443b0af3672230990db72/76bbc0db48474ee1b82866248e210ddb/261104_MUJI%20app.pdf) |
| 英国NCSC | AIとサイバー脅威の章見出し | [年次報告](https://www.ncsc.gov.uk/collection/annual-review-2026/understanding-threat/ai-impact-cyber-threat) |
| 自作図 | 情報に応じた対処の入口 | [IPA](https://www.ipa.go.jp/security/anshin/attention/2026/mgdayori20261026.html) |

記事用の5点とalt・hashは `blog-handoff/v02/asset-manifest.json`。ローカルのMarkdown、HTML、PDF、素材パックを保存した。出典の引用範囲と掲載条件は媒体への公開時に確認する。元の取得結果は[調査QCv02](RESEARCH_QC_V02_JA.md)。
