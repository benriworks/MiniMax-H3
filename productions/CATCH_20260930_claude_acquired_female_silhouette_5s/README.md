# 女性プログラマー：体格の調整


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

2026-09-30の利用者指定「体格が男性と全く同じなので、少し女性らしく」を反映する素材改訂。明るい服装版から顔・黒髪のボブ・アイボリーのパーカー・水色のインナーを維持し、肩幅、腕と袖の膨らみ、胴回り、座り姿勢を自然な成人女性のシルエットへ調整する。

## 素材と手順

- [画像編集の指示](prompts/FEMALE_KEYFRAME.md)で、既存の女性版始点をCodex組込み画像生成ツールにより編集する。
- 新しい始点は`outputs/claude-acquired-female-silhouette-20260930/female-keyframe.png`。編集元・指示・画像のhashは同フォルダーの`image-edit.json`に保存する。
- [動画の指示](prompts/FEMALE_H3.md)をローカルComfyUIのI2VAへ渡す。768×1376、24fps、124frames、20steps、official INT8 ConvRot＋Q4 encoder、reserve VRAM 1.5GB。従来と同じseedを使い、別UUIDで記録する。
- `generate.py`は送信前にrequestとgraphを保存し、送信後は同じUUIDを照合する。不確かな送信を自動再送しない。形式と全decodeを確認した後、体格・顔・衣装・手の動きは目視で判定する。
- 原本の目視確認後、[30秒版の台本](../SHORT_20260930_claude_code_creator/creator-story.json)の最後の素材へ接続する。最終動画内に「図解イメージ」や生成ツール名のテロップを入れない。

```powershell
.\.venv\Scripts\python.exe productions/CATCH_20260930_claude_acquired_female_silhouette_5s/generate.py
```

動画にMiniMaxの課金APIは使用しない。始点画像は組込み画像生成を使用する。旧女性版と男性の基準素材は保持する。生成・目視確認の結果と利用者の最終採否は分けて記録する。

## 原本の確認結果

生成時間1660.970秒。768×1376・24fps・124frames、原本の全decodeに合格。4fpsの場面一覧と3秒／4秒の原寸画像で、肩幅・袖・胴回り、顔と配色、二本の腕と握った手を確認した。状態は`visual_review_passed`、`user_approved: false`。[生成と目視の検証記録](../../verification/claude-acquired-female-silhouette-2026-09-30.json)と[人物素材の比較ページ](../../outputs/characters/programmer-duo-20260930/index.html)に保存している。
