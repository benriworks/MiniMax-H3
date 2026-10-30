# プログラマー・キャラクターの基準


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

2026-09-20、利用者が男性版について「良いねこのキャラクターを基本にしたいね」と指定したため、今後の制作で参照する外観の基準として記録する。女性版は同じ系列の試作候補で、女性キャラクターの採否は別途確認する。

## 共通の外観

- 日本人の架空の成人プログラマー。親しみやすく、作業に集中し、成功を素直に喜ぶ。
- アニメ調の3Dゲーム映像。黒髪、暗い茶色の瞳、自然な成人の体格。
- プルオーバーパーカー、丸首インナー、青いジーンズ。男性版は濃いグレーと青、女性版は下記の明るい衣装を改訂候補とする。
- 無地の黒いノートPC、黒いゲーミングチェア、机。背景は暗い紺。左にシアン、右にマゼンタの縁取り光。
- 獲得演出は金色のクリスタル、光輪、粒子、金色の放射光、四角い紙吹雪、ガッツポーズ。
- 文字とロゴを生成画像へ混ぜず、正確な文言は編集時に加える。

## 男性版：採用された外観の基準

短い黒髪、斜めの前髪、明るい表情。元の承認対象は[CATCH_20260919の完成動画](../../CATCH_20260919_claude_acquired_5s/README.md)。

- 冒頭：[male-base-start.png](../../../outputs/characters/programmer-duo-20260920/male-base-start.png)
- 獲得ポーズ：[male-base-victory.png](../../../outputs/characters/programmer-duo-20260920/male-base-victory.png)

## 女性版：試作

2026-09-30、利用者が体格を少し女性らしくするよう指定した。[今回の始点画像](../../../outputs/characters/programmer-duo-20260930/female-silhouette-keyframe.png)では、肩幅と袖・腕の膨らみを抑え、胴回りを緩やかに絞り、膝を近づけた自然な座り姿勢へ調整した。顔・髪型とアイボリー／水色の配色は引き継いでいる。生成した動画でも形状を確認済み。[前版との比較](../../../outputs/characters/programmer-duo-20260930/index.html)と[獲得ポーズ](../../../outputs/characters/programmer-duo-20260930/female-silhouette-victory.png)、[制作記録](../../CATCH_20260930_claude_acquired_female_silhouette_5s/README.md)を参照。今後の女性版では、この体格改訂版を参照候補とする。今回の改訂の最終採用は未確認。

2026-09-21、利用者が女性版の服装を明るくするよう指定した。顔・黒髪のボブ・画風を維持し、アイボリーのパーカーと水色のインナーへ変更した[新しい始点画像](../../../outputs/claude-acquired-female-bright-20260921/female-keyframe.png)を作成した。[明るい服装版の制作記録](../../CATCH_20260921_claude_acquired_female_bright_5s/README.md)。この配色の最終採用は未確認で、前回素材も以下に保持する。

明るい服装版の5秒動画も生成と検証を完了した。[服装の比較ページ](../../../outputs/characters/programmer-duo-20260921/index.html)に今回と前回を並べ、[獲得ポーズの参照画像](../../../outputs/characters/programmer-duo-20260921/female-bright-victory.png)も保存している。今後の女性版の提案では明るい服装の参照画像を使い、採用済みとは扱わない。

20代半ばの成人女性として、黒いボブ、斜めの前髪、同じパーカーと青いインナーを指定した。男性版の冒頭画像をCodexの画像生成ツールで編集し、その画像をMiniMax H3の始点に渡す。服装・配色・机・構図を揃えることを優先する。

- 始点画像：[female-keyframe.png](../../../outputs/characters/programmer-duo-20260920/female-keyframe.png)
- 獲得ポーズ：[female-victory.png](../../../outputs/characters/programmer-duo-20260920/female-victory.png)
- 動画制作：[女性版の制作記録](../../CATCH_20260920_claude_acquired_female_5s/README.md)

女性版の5秒候補は生成と技術検証を完了した。[男性版と女性版の比較ページ](../../../outputs/characters/programmer-duo-20260920/index.html)から並べて再生できる。女性版の採否は利用者確認待ち。

生成モデルが将来の全カットで外観を完全固定するという保証ではない。毎回、この参照画像と生成結果を見比べる。これらは映像・画像の参照素材で、リグ付き3Dモデルではない。
