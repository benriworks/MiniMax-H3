# dots第3弾：アプリ連携・Aoedeナレーション版

2026年10月22日、利用者よりYouTube公開済みとの申告あり。以下の完成候補・未確認状態の記載は初回納品時点の記録。次の第4弾は[公式画面引用版](../SHORT_20261022_dots_04_editorial/README.md)として独立して改訂する。

## 完成候補（2026-10-22）

- [再生ページ](../../outputs/productions/SHORT_20261022_dots_03_aoede/20261022T075051150042Z/release/index.html)
- [完成MP4](../../outputs/productions/SHORT_20261022_dots_03_aoede/20261022T075051150042Z/release/dots-03-apps-aoede.mp4)
- [字幕・カバー・見出し・説明欄・出典を含む納品ZIP](../../outputs/productions/SHORT_20261022_dots_03_aoede/20261022T075051150042Z/dots-03-apps-aoede.zip)
- [検証記録](../../outputs/productions/SHORT_20261022_dots_03_aoede/20261022T075051150042Z/verification.json)

30.000秒・1080×1920・24fps・720frames・H.264/AAC。完成音量-16.02 LUFS、true peak -2.96 dBFS。全decode、描画中の全frame文字領域検査、完成8場面の360px幅とコンタクトシートのAI補助目視に合格。関連unittestは21件成功。ZIPのCRCと全ファイルhashを照合し、旧9本と45秒補足編のMP4は変更なし。S3upのHEAD・全体GET・サイズ・SHA-256照合も成功した。署名URLは制作ファイルへ保存しない。

状態は`verified_candidate_awaiting_user_review`。Aoedeの選択は利用者確認済みであり、この第3弾全体の最終試聴・採用とYouTube投稿は未確認。

公開済みの「【ChatGPT】PCを閉じても仕事が進む？dotsクラウドPCの3つのメリット」に続く30秒版。公開状況は利用者の申告として`publication-status.json`に記録し、次の第3弾はYouTubeへ投稿しない。

Aoedeを基本の声として採用し、原稿と発音辞書を8場面別にGemini 2.5 Flash TTSへ送る。既存の男女キャラクターを再利用する。公式資料を2026年10月22日に確認し、今回確認できない「4,000以上」の数値を接続方法の説明へ更新した。独自図解・架空人物の紹介であり、実機操作の実証ではない。[公式出典](SOURCES_JA.md)。

`produce.py generate`は各場面を1回ずつ生成し、実WAV・要求・生成証跡・usageを日時別の`voice-generations`へ保存する。キーは環境変数のみ使用する。既に`state.json`がある場合は再送しない。拒否・成否不明時は自動再試行しない。表示・字幕の修正では保存済み音声を使用する。

`prepare`は検証済み音声のsampleを照合して場面と字幕を再配置し、`render`は共通RemotionとBGMの発話時減音、全decode・音量・peak検査を実行する。完成画像を確認してから`review --note`を記録し、`package`でMP4・カバー・字幕・見出し・説明欄・出典・検証結果をZIPへまとめ、CRCと全member hashを読み戻す。`state.json`が作業先、`delivery.json`が完成候補を指す。

旧9本と公開済み45秒補足編のMP4は上書きせず、生成前後でhashを照合する。最小文字54px・安全域・生成ツール名を画面に入れない方針を維持。Aoedeの選択と、この完成版の利用者による最終試聴・採用は区別する。アプリ全体の設計は独立したルートの`ARCHITECTURE.md`と`ARCHITECTURE_DIAGRAM.md`に記載する。
