# GPT-6.2 AstraとSolの制作構成

表示原稿は `story-v01.json`、読み原稿は `tts-v01.json`。同じ結論の冒頭は両版で一つのAoede音声を再利用する。残りは台詞ごとに Aoede または Charon を使う。 `narrate.py` は既存の `dialogue_narration` へ渡し、受付、応答、PCMのhashをローカルに保存する。先頭2話者の呼び出しが通ってからバッチを進める。

`produce.py prepare` は元画面から、選択メニュー・公式作例のおのおののクロップを作る。MiniMaxで以前作成した人物動画はhashを照合して12 fpsの画像に変換する。発話側を見せる場面でも、口の音素同期は行っていない。字幕は `editorial_captions`、図とテキストの計測は `explainer_canvas`、声とBGMは `longform_audio` を共通利用。BGMはオリジナルのbright、ミックス設定は `explanation_v1`。

ショートは1080×1920、フルは1920×1080。24 fps、H.264/AAC。タイムラインは実PCMの長さから構成し、字幕時刻と表示を同じ計画から出す。検証用シートで版別に絵を確認し、完成MP4を全デコードして最終AACの音量を測る。結論・人物・画像比較・字幕は実フレームで確認する。

## 実行

Python 3.12、Pillow、NumPy、BudouX、FFmpeg、同梱Noto Sans JP。コードと素材ルートは [再開記録](RESUME_AND_KNOWHOW_JA.md) を参照。以下の `$case` はこのフォルダーのパス、`$media` は指定checkoutの `outputs/content-projects/CONTENT_20261118_gpt62_astra_sol`、`$motion` は既存人物素材の所在。

```powershell
python $case/narrate.py --media $media
python $case/produce.py prepare --media $media --motion-source $motion
python $case/produce.py preview --media $media --kind short
python $case/produce.py preview --media $media --kind full
python $case/narrate.py --media $media --short-revision v03
python $case/produce.py render --media $media --kind short --version v03
python $case/produce.py render --media $media --kind full
python $case/handoff.py record --media $media
python $case/handoff.py package --media $media
```

既存の音声受付を再利用する場合は同一原稿とSHA-256を確認する。媒体の同じ版を再書き出す場合は、既存の成果物を保管して新しい出力ルートを指定する。別PCでの同一結果は未確認。

[独立したMermaid図](ARCHITECTURE_DIAGRAM.md)
