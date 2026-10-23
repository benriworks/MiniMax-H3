# dots 第5〜9回の仕上げ

2026-10-23の依頼に基づく最終改訂。第5回は会話をまたぐ独自ノート・文脈とChatGPT Memoryを区別。第7回は会話での依頼、保存確認、一覧・変更・解除とScheduledでの操作を具体化する。全5本の声はGemini Aoede。

第5回は30秒、第7回は45秒。第6・8・9回は前シリーズのGemini版を検証して再利用する。第5・7回は発音置換後の原稿が一致する発話だけを再利用し、6件と7件を新規生成した。新しい人物動画の生成は不要で、元のdots男女のMiniMax動画を使う。

## ローカル保存

- `05` / `07`：固定した初回台本、生成済み音声の参照、状態、表示改訂。`visual-v02`は人物場面の文字量調整、`visual-v03`は意味の切れ目に合わせた字幕調整。音声を作り直さずに改訂する。
- 音声：`outputs/productions/SHORT_20261023_dots_NN_final/voice-generations/v01/`。plan、送信状態、request、WAV、生成証跡、実測timingsを保存。
- 描画：同production ID下の時刻付きフォルダー。失敗したprepare、初回完成版、字幕改訂版を別世代で残す。
- 納品集約：`outputs/productions/SERIES_20261023_dots_final_delivery/`。各回のMP4、字幕、見出し、説明欄、出典、検証記録。Drive受領記録はここだけに保存し、GitHubへは入れない。

## 実行範囲

`produce.py build`、`generate`、`render`、`final-render`を使用する。generateは既存の共有ロックと22秒間隔を使い、1回ごとの結果が不明なときに自動再送しない。final-renderは字幕の意味区切りを反映する独立したprepareである。

この専用ドライバーは現行PCの前シリーズ原稿・生成証跡・人物動画・Studio共通コードを前提とする。GitHubにあるこのフォルダーだけで素材がそろうわけではない。動画・音声はGitHubに保管しない。

## 検証と受け渡し

原稿と読み、Gemini生成証跡、PCM sample数、入力hash、動画全デコード、仕様・尺・音量、完成画面を確認する。人の最終試聴・スマホ実再生・ユーザー採用・YouTube公開は別状態とし、AIによる確認で承認済みにしない。Driveへの保存後はファイル名・容量・親フォルダー・権限をreadbackで確認する。

公式引用は短い既存の撮影画像を使い、出典・撮影日・内容確認日を説明欄へ残す。定期実行の会話例は架空であり、実際のscheduleは登録しない。詳細は[SOURCES_JA.md](SOURCES_JA.md)、独立した[アーキテクチャ](ARCHITECTURE.md)と[Mermaid図](ARCHITECTURE_DIAGRAM.md)を参照。
