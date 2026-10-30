# Claudeを手に入れた！ 女性プログラマー版


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

男性キャラクターを今後の基本にしたいという利用者の指定を受け、同じ系列の女性版を試作する。アニメ調のゲーム映像、黒髪、濃いグレーのパーカーと青いインナー、金色の獲得アイテムを共通にする。[キャラクター基準](../characters/programmer-duo/README.md)を参照。

## 制作経路

1. 男性版の冒頭フレームを参照し、Codexの組込み画像生成ツールで成人女性の始点画像を作成。[画像用prompt](prompts/FEMALE_KEYFRAME.md)。
2. ローカルComfyUIの`MiniMaxH3ImageToVideo.first_frame`へ画像を接続し、official INT8 ConvRot + Q4／Dynamic VRAM／20 steps／768×1376でI2VA生成する。[動画用prompt](prompts/FEMALE_H3.md)。
3. 原本を目視確認後、男性版と同じ文字デザインをRemotionで1080×1920／24fps／120framesへ描画する。
4. 男性版のSAPI音声4成果物と独自チャイムをhash照合して再利用する。Sayaka rate 1、「クロードを、手に入れた！」、1.700〜4.168秒。
5. 同じ映像にナレーション＋効果音、または効果音のみを合成する。全decode、形式、音声peak、360px幅の文字と人物を確認する。

動画にMiniMaxの課金APIは利用しない。始点画像はCodexの画像生成ツールによるものなので、制作全体を「すべてローカル生成」とは扱わない。

## 実行

ComfyUIが空queueで`127.0.0.1:8188`に起動し、始点画像が`runtime/ComfyUI/input/claude-acquired-female-20260920/female-keyframe.png`にある状態で実行する。今回のI2VAでは、起動引数に`--reserve-vram 1.5`を追加してGPUメモリへ余裕を持たせる。OSや他アプリの設定を変更するものではなく、このComfyUIプロセスだけの設定である。

今回と同じComfyUI起動設定（リポジトリのルートから実行）：

```powershell
.\.venv\Scripts\python.exe runtime/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --preview-method none --disable-pinned-memory --output-directory C:/Users/mono_/MiniMaxH3/outputs --disable-all-custom-nodes --whitelist-custom-nodes ComfyUI-GGUF --enable-dynamic-vram --disable-auto-launch --reserve-vram 1.5
```

別の端末から制作処理を実行する：

```powershell
.\.venv\Scripts\python.exe productions/CATCH_20260920_claude_acquired_female_5s/generate.py --headroom
.\.venv\Scripts\python.exe productions/CATCH_20260920_claude_acquired_female_5s/produce.py prepare
node productions/CATCH_20260920_claude_acquired_female_5s/render.mjs <prepareが表示するフォルダー>
.\.venv\Scripts\python.exe productions/CATCH_20260920_claude_acquired_female_5s/produce.py finish <同じフォルダー>
```

`generate.py`はrequestのUUIDを送信前に保存する。正常に送信済みなら、再実行時も同じIDをGETで照合し、再送しない。応答が不確かな状態では保存済みIDの確認を要求する。生成記録の`visual_review_passed`がなければrendererは実行しない。この案件のI2VAは、Studioの標準T2VA APIや画面へ機能を追加するものではない。`--headroom`は保存先と記録を選ぶ指定であり、ComfyUIの起動設定自体は変更しない。

最初の試行`2681cee1-5f68-45b0-84c7-6b36ebdbd77e`は、既定のWindows用メモリ余裕では1段階目183秒、2段階目まで累計487秒と遅くなり、同一IDのtargeted interruptで中断した。graph・historyを元フォルダーへ保持し、同じ画像・prompt・seed・解像度・20 stepsで、メモリ余裕だけを増やした別IDへ再送した。最初の試行から完成素材は得ていない。

## 現在の状態

女性版の5秒候補を作成し、技術検証と目視確認を完了した。女性版の利用者による採否は未確認。

- [女性版・ナレーションあり](../../outputs/productions/CATCH_20260920_claude_acquired_female_5s/20260920T052154805826Z/claude-acquired-female.mp4)
- [女性版・効果音のみ](../../outputs/productions/CATCH_20260920_claude_acquired_female_5s/20260920T052154805826Z/claude-acquired-female-sfx-only.mp4)
- [男性版と並べて再生する比較ページ](../../outputs/characters/programmer-duo-20260920/index.html)
- [始点画像・原本・制作記録を含むZIP](../../outputs/productions/CATCH_20260920_claude_acquired_female_5s/20260920T052154805826Z/claude-acquired-female-review.zip)
- [完成品の検証記録](../../outputs/productions/CATCH_20260920_claude_acquired_female_5s/20260920T052154805826Z/verification.json)／[H3の生成記録](../../verification/claude-acquired-female-2026-09-20.json)

メモリ余裕を増やしたI2VAの生成は1596.363秒で完了し、samplingは約74.7秒／段階で安定した。原本は768×1376／24fps／124frames。20枚の動作一覧と4秒の原寸画像で、女性の顔と髪型、両腕、獲得動作を確認した。金色の光輪は途中で額を横切り、顔に光を落とすが、クリスタル本体は右側に留まる。

完成版はどちらも5.000秒／120frames／1080×1920／24fps／H.264＋AAC 48kHz。全decodeと音声peak検査を通過した。男性版と女性版の完成AAC packetのSHA-256は同じで、声・速さ・読み方・効果音を維持している。

0・1・3・4秒を360px幅、3秒・4.5秒を原寸で目視確認した。高く上げた拳と重ならないよう女性版のLEGENDARYバッジを右へ移し、最低54pxの文字と顔・拳・アイテムを確認できる配置にした。変更前の確認用描画は別フォルダーへ保持し、完成品のリンクには使用していない。
