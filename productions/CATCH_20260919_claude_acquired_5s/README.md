# Claudeを手に入れた！ 5秒キャッチ


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

2026-09-20、利用者がこのキャラクターを今後の基本にしたいと指定した。[共通のキャラクター基準](../characters/programmer-duo/README.md)へ参照画像と外観を保存し、女性版は別案件で試作する。これはキャラクター外観の採用であり、公開操作は含まない。

日本人の架空の成人プログラマーが、レアアイテムを獲得したように喜ぶゲーム風の映像。利用者の「ゲーム風：レアアイテム獲得のように派手に喜ぶ」という指定に基づく。30秒のモデル進化動画とは独立した挿入候補で、既存の夜景版は保持する。

## 制作内容

- MiniMax H3のT2VAで、成人プログラマー・琥珀色のクリスタル・ガッツポーズ・金色の光を生成する。
- ローカルのofficial INT8 ConvRot + Q4 text encoder、Dynamic VRAM、20 steps、768×1376、24fps、5秒指定。出力124framesのうち最初の120framesを使う。課金APIは利用しない。
- Remotionで1080×1920へ描画し、金色のLEGENDARYバッジと正確な「Claudeを／手に入れた！」の文字を後付けする。文字は54px以上（360px表示時18px以上）。顔とアイテムが見える中央を空ける。
- Windows SAPIのMicrosoft Sayaka、rate 1。表示のClaudeはそのまま、「クロードを、手に入れた！」と発音する。開始1.700秒、実測終了4.168秒。
- 元の生成音声は使用せず、独自合成の短い上昇チャイムを重ねる。声あり版と効果音のみの版は同じ映像を使う。

## 再現手順

1. [prompt](prompts/PROGRAMMER_H3.md)を固定T2VA graphへ設定してローカルH3を実行し、graph・submission・history・原本のhashを`verification/claude-acquired-2026-09-19.json`へ保存する。既存の送信IDを再照合し、重複送信しない。
2. 原本の顔・腕・獲得動作を確認し、生成記録を`visual_review_passed`へ更新する。
3. `.venv\Scripts\python.exe productions/CATCH_20260919_claude_acquired_5s/produce.py prepare`
4. `node productions/CATCH_20260919_claude_acquired_5s/render.mjs <prepareで表示された出力フォルダー>`
5. `.venv\Scripts\python.exe productions/CATCH_20260919_claude_acquired_5s/produce.py finish <同じ出力フォルダー>`
6. 完成画像を360px幅で確認し、技術検証と利用者の採否を分けて記録する。

`prepare`は既存StudioのSAPI workerを呼び、実WAVが5秒枠へ収まるかを確認する。`render`は原本と生成経緯のhashを照合し、120framesをH.264 CRF 12で描画する。`finish`は映像を再圧縮せず音声をAAC 48kHzで合成し、両版の5秒・120frames・解像度・全decode・音声peakと映像packetの一致を確認する。完成版に表示字幕を別途重ねず、取得メッセージ自体を台詞の文字表示として使う。

## 確認用出力

- [ナレーションありのMP4](../../outputs/productions/CATCH_20260919_claude_acquired_5s/20260919T104749422759Z/claude-acquired.mp4)
- [効果音のみのMP4](../../outputs/productions/CATCH_20260919_claude_acquired_5s/20260919T104749422759Z/claude-acquired-sfx-only.mp4)
- [原本と制作記録を含むZIP](../../outputs/productions/CATCH_20260919_claude_acquired_5s/20260919T104749422759Z/claude-acquired-review.zip)
- [完成品の検証記録](../../outputs/productions/CATCH_20260919_claude_acquired_5s/20260919T104749422759Z/verification.json)
- [MiniMax生成記録](../../verification/claude-acquired-2026-09-19.json)

2026-09-19にローカルH3の生成が1501.551秒で完了した。原本は768×1376／24fps／124frames。4fpsの20枚の一覧と2秒・4秒の原寸画像で、人物の同一性、両腕、クリスタルの出現、ガッツポーズ、紙吹雪を確認した。仕上げ時は掲げた拳を隠さないよう、LEGENDARYバッジを上へ移した。

両完成版は5.000秒／120frames／1080×1920／24fps／H.264＋AAC 48kHz。全decode成功、映像packetは同一。復号後の音声sample peakは声あり約0.683、効果音のみ約0.175で、無音・クリッピング検査を通過した。0・1・3・4秒の360px幅完成画像と4.5秒の原寸描画を目視し、文字の可読性と顔・拳・アイテムとの非重複を確認した。音声の聴感評価は利用者確認待ちであり、波形検査とは区別する。

確認用候補として制作完了。利用者による採用とYouTube投稿は未実施。`story.json`の`review_status`は準備時の初期状態で、現在の判定は完成品の`verification.json`を参照する。
