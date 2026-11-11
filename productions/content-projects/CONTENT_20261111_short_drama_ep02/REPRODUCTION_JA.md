# 『お父さんも、入って。』の再編集手順

別のPCやworktreeでは、先に[ドラマ制作手順](../../../docs/video-production/SHORT_DRAMA_PRODUCTION_JA.md)でコードと素材のルートを確認する。PowerShell例の保管先は実際のフォルダーに合わせる。

主cloneの `outputs/content-projects/` に次の二つの素材ルートが必要。Python 3.12.2、NumPy 1.26.4、Pillow 12.3.0、FFmpegとffprobe 8.1.2、Windows Yu Gothic Boldを使用した。

| 素材 | 所在 |
| --- | --- |
| 続編の動画原本 | `CONTENT_20261111_short_drama_ep02/shots/v01/<カットID>/source.mp4`。各フォルダーの `generation.json` に受付、使用量、原本と入力のハッシュ。 |
| 続編の基準画・記事カバー | 同案件 `plates/v01/`。 [画像プロンプト](prompts/imagegen-v01.json) |
| 台詞WAV | 同案件 `audio/v02/tts/d01-father/voice.wav` と `audio/v01/tts/d02-maho/voice.wav`。初回父音声は `audio/v01/tts/d01-father/voice.wav`。 |
| 前作の写真裏 | `CONTENT_20261108_short_drama/plates/v06/04-photo-back.png`。 |
| 前作の画像参照 | 同案件の `characters/v02/maho-reference-v02.png`、`references/workflow-v01/pier-location-sheet-v01.png` と `blog-handoff/v06/assets/photo-front.png`。 |

制作ブランチのルートで実行する。別版名を指定すると、元の出力を保ったまま同じ編集を再現できる。

```powershell
$mediaRoot = (Resolve-Path -LiteralPath (Join-Path $env:USERPROFILE 'MiniMaxH3\outputs\content-projects')).Path
$ep = Join-Path $mediaRoot 'CONTENT_20261111_short_drama_ep02'
$prev = Join-Path $mediaRoot 'CONTENT_20261108_short_drama'
python -B productions/content-projects/CONTENT_20261111_short_drama_ep02/render_episode.py $ep $prev --version v02-reproduction
```

初回の仮組みを再現する場合は `--initial --version v01-initial-reproduction`。既存原本からフレーム数、字幕、音量、全デコードを確認してMP4と `render.json` を作る。波・効果音、ピアノ、台詞は `edit/<版>/` に分離して保存する。再編集はローカルで完結する。

新規生成を行う場合は [前作のH3生成CLI](../CONTENT_20261108_short_drama/generate_h3_shot.py) に、5秒、カット別プロンプトと開始画を明示する。06だけは `--last-image` に `06-together-end.png` を指定する。受付済みのカットは既存の保存ディレクトリで同じタスクを照会する。台詞の再生成は `synthesize_dialogue.py` に新しい出力先と読み原稿、対象の台詞を指定する。初回送信にだけ `--confirm-billable` が必要。保存済みのWAVは元応答と照合できる。
