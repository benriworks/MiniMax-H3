# 国内情報漏えい解説の制作構成

2026-11-07。現段階は調査・企画の記録。共通Studioへの新機能追加や、新動画・音声の生成は行っていない。独立した[Mermaid図](ARCHITECTURE_DIAGRAM.md)を維持する。

依頼原文・国内指定を案件に保存し、原公表の日時・数量単位・確度・対象項目・原因を同じ事件IDへ結ぶ。上流事件と利用企業の続報を照合し、候補の比較・採点方法・構成案を作る。採用後に絵コンテ、既存白衣人物、表示と読みを分離した会話、公式引用と自作図を縦横各媒体へ接続する計画。

記事草稿・出典・引用候補も同じ事実から準備する。軽量な正本はproductions、原画像・HTML・PDF・生成物と私的受領はoutputs。調査と構成の採用、撮影、生成、媒体検査、人の試聴、共有、公開の状態は分ける。[再開記録](RESUME_AND_KNOWHOW_JA.md)と[採点案](SCOPE_AND_METHOD_V01_JA.md)を参照。

`incidents-v01.json` は数量単位・確度・内数と関連区分・原因・原公表IDを保持し、`sources-v01.json` はURL・取得日・原本のhashと取得失敗を保持する。`build_research.py` はネットワークや有料APIを呼ばず、重複ID・数量と重み・出典参照を点検し、`ranking-v01.json` と `RANKING_V01_JA.md` を再計算する。Iを一件ずつ変更した感度と、規模を段階化した参考方式も出力する。原資料の真偽や採用を自動判定する処理ではない。

再計算はリポジトリルートで `python productions/content-projects/CONTENT_20261107_ai_japan_data_breaches/build_research.py`。根拠が変わった際は版を分け、企画・記事・台本の依存先を再確認する。共通ContentWorkspaceへ調査と未採用の企画を記録し、ユーザーの構成返答が来るまでは `accept` や媒体生成へ進めない。
