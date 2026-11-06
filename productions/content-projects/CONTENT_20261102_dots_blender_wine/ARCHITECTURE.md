# ワインCG素材から縦横の解説動画を作る構成

Driveの提供ファイルを原本として保存し、`inspect_materials.py` が容量・hash・ZIP安全性・動画probeを記録する。展開コードは実行しない。`produce.py prepare` が公開用工程画像・比較画像・公式の短い引用・既存男女素材を分離する。

`script-v01.json` は表示原稿と読みを分ける。`voices.py` はGemini Aoede/Charonを成功済み音声のhash付きキャッシュとして保存し、`produce.py timeline` は実PCMから尺・字幕・既定BGM explanation_v1・SEを組み立てる。`render` が共通Canvas・人物アトラス・既存MiniMax動画・10秒終了画面を合成する。新しいキャラクター生成や元Blenderシーンの変更はない。

ショートは縦1080×1920、フルは1920×1080、24fps。元のCGは960×540。動きの比較は初版/v2の同時刻、比率の比較は提供された同じカメラ/フレーム画像を使う。スローは0.5倍/0.4倍を表示する。工程は実画面静止画と明示。液体は手続き型アニメーションと説明する。

音声は2-pass loudnorm後のAAC実測で確認する。`verify.py` が全編からの画像点検と独立AI音声点検を保存し、人の試聴・採用と分ける。`package.py` は記事草稿・画像・字幕・投稿文を動画本体なしのZIPへ集め、全member hashとCRCを照合する。`register_workspace.py` は共通台帳へ撮影不足・出典・2本の絵コンテ・記事を記録する。

コード/文書はGit、原本・API応答・音声・MP4・ZIPはignoredのoutputs。Drive優先共有、必要時だけS3。自動公開や新Studio UIの実装ではない。
