# Claudeを手に入れた！ 女性版・明るい服装

2026-09-21の「女性版はファッションをもう少し明るいものに」という指定に対応する候補。前回の女性版の顔・黒髪のボブ・ゲーム調の画風を基に、アイボリーのパーカーと明るい水色の丸首インナーへ変更する。具体的な配色は今回の提案で、利用者の最終採用は未確認。

## 素材と制作方法

- 始点画像：[female-keyframe.png](../../outputs/claude-acquired-female-bright-20260921/female-keyframe.png)。前回女性版の始点をCodex組込み画像生成ツールで衣服の色のみ編集した。CLI/API代替は使用しない。
- 画像用の最終指示：[FEMALE_KEYFRAME.md](prompts/FEMALE_KEYFRAME.md)
- MiniMax H3用の最終指示：[FEMALE_H3.md](prompts/FEMALE_H3.md)
- 動画：ローカルComfyUIのI2VA。official INT8 ConvRot + Q4、Dynamic VRAM、20 steps、768×1376、seed 2026092007。今回用のComfyUIを最初から`--reserve-vram 1.5`で起動する。
- 編集：1080×1920、24fps、5秒。最低54pxの文字、男性版の検証済みナレーションと独自チャイムを再利用する。

元の女性版と男性版は別ファイルで保持する。MiniMaxの有料動画APIは使用しないが、画像編集にはCodex組込みツールを使用しているため、制作全体をすべてローカルとは扱わない。

## 再開と検証

ComfyUIの入力画像は`runtime/ComfyUI/input/claude-acquired-female-bright-20260921/female-keyframe.png`。空queueの`127.0.0.1:8188`に対して`generate.py`を実行する。送信前UUIDを保存し、送信後の再開は同じUUIDのGET照合だけを行う。不確かな送信を自動再送しない。

```powershell
.\.venv\Scripts\python.exe productions/CATCH_20260921_claude_acquired_female_bright_5s/generate.py
.\.venv\Scripts\python.exe productions/CATCH_20260921_claude_acquired_female_bright_5s/produce.py prepare
node productions/CATCH_20260921_claude_acquired_female_bright_5s/render.mjs <prepareの出力先>
.\.venv\Scripts\python.exe productions/CATCH_20260921_claude_acquired_female_bright_5s/produce.py finish <同じ出力先>
```

原本の目視確認が通過するまでrendererは実行しない。完成後は全decode、5秒／120frames、形式、音声peak、360px幅の文字と人物を確認する。

## 完成した候補

生成と技術・目視確認を完了。配色と動画の最終採用は利用者確認待ち。

- [明るい服装版・ナレーションあり](../../outputs/productions/CATCH_20260921_claude_acquired_female_bright_5s/20260920T171507703676Z/claude-acquired-female-bright.mp4)
- [効果音のみ](../../outputs/productions/CATCH_20260921_claude_acquired_female_bright_5s/20260920T171507703676Z/claude-acquired-female-bright-sfx-only.mp4)
- [前回の服装との比較](../../outputs/characters/programmer-duo-20260921/index.html)
- [画像・原本・指示を含む一式ZIP](../../outputs/productions/CATCH_20260921_claude_acquired_female_bright_5s/20260920T171507703676Z/claude-acquired-female-bright-review.zip)
- [完成品の検証記録](../../outputs/productions/CATCH_20260921_claude_acquired_female_bright_5s/20260920T171507703676Z/verification.json)／[MiniMax生成記録](../../verification/claude-acquired-female-bright-2026-09-21.json)

I2VAは1回の送信で1692.343秒（約28分12秒）で完了した。原本は768×1376／24fps／124frames。4fpsの20枚一覧と4秒の原寸画像を確認し、アイボリーの生地の陰影、水色の襟元、黒髪のボブ、両手のガッツポーズを確認した。光輪が額・目元を横切る演出は前回同様に残る。

完成版は1080×1920／24fps／120frames／5.000秒、H.264＋AAC 48kHz。全decode、非無音・音割れ検査に合格した。完成AAC packetは前回と同一で、声・速度・読み方・獲得音を維持。0・1・3・4秒を360px幅、4.5秒を原寸で確認し、衣装の明るさと文字・顔・拳の見え方を検証した。生成に使用した今回用ComfyUIは空queueを確認して終了済み。
