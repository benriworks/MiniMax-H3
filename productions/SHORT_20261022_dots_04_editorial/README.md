# dots第4弾：並行作業・公式画面引用版

## 完成候補（2026-10-22）

- [再生ページ](../../outputs/productions/SHORT_20261022_dots_04_editorial/20261022T084349480702Z/release/index.html)
- [動画のみのMP4](../../outputs/productions/SHORT_20261022_dots_04_editorial/20261022T084349480702Z/release/dots-04-parallel-official.mp4)
- [字幕・カバー・見出し・説明欄・出典を含むZIP](../../outputs/productions/SHORT_20261022_dots_04_editorial/20261022T084349480702Z/dots-04-parallel-official.zip)
- [検証記録](../../outputs/productions/SHORT_20261022_dots_04_editorial/20261022T084349480702Z/verification.json)

30.000秒・1080×1920・24fps・720frames・H.264/AAC。完成音量-16.02 LUFS、true peak -2.53 dBFS。全decodeと全frameの文字領域検査、完成7場面の360px幅と30秒コンタクトシートのAI補助目視に合格。画像3箇所の英文・出典表示と原本を照合した。関連unittest25件とTypeScript検査が成功。ZIPのCRCと全member hash、旧9本・補足編・第3弾Aoede版のMP4が変わっていないことを確認した。

S3は再生用とスマホからの添付ダウンロード用を分けて検証済み。URLを制作ファイルへ保存しない。完成版の最終試聴・採用、YouTube投稿は利用者確認用。第5〜9弾の動画はこの成果物に含めていない。

第3弾「アプリ連携」までYouTube公開済みとの利用者申告を受け、次の30秒版を改訂する。人物素材を繰り返さず、導入の大きな文字、公式資料の実際の画面、架空の作業例のアニメーション、会話中の追加指示、進行状況と成果物の確認を7場面で構成する。Aoedeと112 BPMのBGMを使用する。

公式資料を実際にブラウザーで開き、2026年10月22日に3箇所を撮影した。ページの説明用UIから作業リンク、Recent activity、Outputsの部分だけを引用する。英文の合計は19語。引用画面に出典ドメインとOpenAI公式資料であることを表示し、説明欄にはURLを記載する。日本語の解説と架空の作業例は引用画面の外に配置し、公式UIを書き換えない。

原画面と切出し座標、撮影日時、URL、PNG寸法とhashは制作記録へ保存する。公開用ZIPへ原画面や内部証跡を含めない。公式の画面例を引用した紹介であり、実アカウントで作業完了を実証した録画ではない。[出典と引用範囲](SOURCES_JA.md)。

`produce.py generate`はAoedeを各場面1回ずつ生成する。拒否・不明応答は自動再送しない。`prepare`は音声sampleと画像の撮影証跡を照合し、`render`は共通Remotionで全frameの文字・安全域を検査する。完成画像を確認してから`review --note`を記録し、`package`が動画・字幕・カバー・見出し・説明欄・出典・検証結果を梱包してCRCと全hashを読み戻す。既存9本・45秒補足編・公開済みAoede版のMP4は保持する。

アプリ全体の設計はルートの独立した`ARCHITECTURE.md`と`ARCHITECTURE_DIAGRAM.md`へ反映する。利用者の公開報告、Aoedeの選択、今回の完成候補の最終試聴・採用とYouTube投稿は別に記録する。
