# CUT PLAN — 広報×生成AI 15秒告知

## 制作メタデータ

| 項目 | 内容 |
| --- | --- |
| Production ID | `SHORT_20260828_ai_content_15s` |
| 状態 | `complete_independently_reviewed`。3 raw、音声、字幕、15秒master、技術QC、代表フレーム目視、独立映像レビューを完了。公開権利は別gate |
| テーマ | 広報×生成AI — 伝えるだけでなく、成果につなげる |
| 画面 / 尺 | 9:16。480x864 / 24fpsのI2VA rawを3本生成し、1080x1920 / 24fps / 約15秒へ編集 |
| 音声 | Windows SAPIナレーション、BGMなし。H3 source audioは最終masterで使用しない |
| 公開状態 | `blocked_pending_rights_review` |

## カット割り

| Cut | 大見出し | ナレーション | 画・動き |
| --- | --- | --- | --- |
| CUT01 / 0〜5秒 | `その発信、届いてる？` | `その発信、本当に届いていますか？` | 明るいオフィスの胸上。人物は右寄り。横方向の視線をカメラへ移し、眉をわずかに上げる。小幅のslow push-in |
| CUT02 / 5〜10秒 | `生成AIで、伝わる企画へ` | `生成AIなら、企画をすぐ形にできます。` | 同じオフィスの腰上。人物は左寄り。空いた手を一度だけ上げて右側を示す。小幅のslow truck right |
| CUT03 / 10〜15秒 | `アイデアを、成果へ。` | `アイデアを、次の成果につなげよう。` | 少し暖かな光。フォルダーを静かに閉じ、小さくうなずいて柔らかく微笑む。小幅のslow push-in |

## 固定生成条件

- 添付人物設定シートは外見参照だけに使い、氏名・年齢・居住地などのプロフィール情報を映像、prompt、ID、ログへ複製しない。
- imagegenで文字なしの9:16始点を3枚作り、480x864 RGB PNGへ正規化する。
- H3はofficial INT8 ConvRot + Q4 text encoder、no Turbo、I2VA first-frame-only、5.0秒指定、20 stepsを使う。
- 人物の顔、短いウェーブのブラウンヘア、ピンクベージュのトップス、淡いベージュのスーツ、ゴールドのフープピアスを維持する。
- H3内では発話させず唇を閉じ、人物動作を各cut一つに限定する。
- 文字、ロゴ、読める資料は生成させず、正確な日本語は編集時の大見出しと字幕で付加する。
- 最終mixは`narration_only_v1`、BGMなし。

## 合格条件

- [x] sourceを非公開成果物領域へ保存し、bytes / SHA-256 / 寸法を記録した。
- [x] 同一人物の文字なし縦型始点3枚を生成し、480x864 RGBへ正規化した。
- [x] 3 rawが480x864 / 24fps / 124 frames / 5.167秒で生成され、full decodeに通った。
- [x] 3 rawの4点contactとmasterの9点contactで、顔、髪、衣装、手指、フォルダーに重大なmorph / flickerがないことを確認した。
- [x] ナレーションと字幕のpreflightに通り、15.000秒のmasterを作成した。
- [x] 1080x1920 masterの媒体、360 frames、full decode、black / 1秒超freeze、音声、safe area QCに通った。
- [x] 独立レビューで人物同一性、顔、髪、衣装、手指、3動作、fade、見出し、字幕、safe areaを再確認した。
- [ ] 公開前に完成版を人の耳で通し試聴する。
- [ ] 公開前に人物画像、派生物、model output、YouTube公開の権利を確認する。

## 完成物

- 字幕・ナレーション付き配信用master: `outputs/productions/SHORT_20260828_ai_content_15s/03_assembly/master/SHORT_20260828_ai_content_15s_delivery_captioned_1080x1920_24fps_bt709.mp4`
- テロップ・字幕なしalternate: `outputs/productions/SHORT_20260828_ai_content_15s/03_assembly/master/SHORT_20260828_ai_content_15s_delivery_clean_1080x1920_24fps_bt709.mp4`
- 2ファイルともH.264 High / yuv420p / bt709 / 1080x1920 / 24fps / 15.000秒 + AAC-LC 48kHz stereo。BGMとH3素材音は使わず、SAPIナレーションだけを収録した。
