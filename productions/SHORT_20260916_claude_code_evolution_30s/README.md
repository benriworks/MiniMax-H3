# Claude Codeを支えるAI：3か月の進化

2026-09-16制作。30秒・縦1080×1920・24fpsの初稿。Fable 5、Opus 5、Fable 5.1を発表順に紹介する。利用者の尺指定は未回答のため30秒を仮置き。台本と出典は[SOURCES_JA.md](SOURCES_JA.md)、制作用正本は[story.json](story.json)。

最新の音声設定：利用者指定によりSayakaのrateを0から1へ上げた。「Fable 5.1」は「フェイブルごーてんいち」、「Fable 5」と「Opus 5」は「ファイブ」。映像と表示字幕本文は維持し、字幕の終了時刻を再合成した実WAVへ合わせる。以下の初稿記録は旧版の履歴として残す。

## 制作経路

1. `produce.py prepare`が既存StudioのWindows SAPI workerで6発話を合成し、実WAVの尺と5秒単位の場面境界を検査する。
2. `render.mjs`がRemotionで独自の編集図解を描画する。日本語フォントは同梱Noto Sans JP。モデル名・日付・評価値はstory.jsonから渡す。棒グラフの軸は共通の0〜100%。
3. `produce.py finish <出力フォルダー>`が既存のassembly workerでナレーションと字幕を合成する。cleanはナレーション字幕なしで、見出しと図解は残る。
4. 両MP4の形式・30秒／720frames・全decode、音声時間枠、入力hash、ZIP全entryのCRCとhashを確認する。完成フレームは360×640にも縮小し、文字の重なりを目視する。

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe productions/SHORT_20260916_claude_code_evolution_30s/produce.py prepare
# prepareのJSONに出た実在の出力フォルダーを、以降2コマンドへ渡す
node productions/SHORT_20260916_claude_code_evolution_30s/render.mjs <出力フォルダー>
.\.venv\Scripts\python.exe productions/SHORT_20260916_claude_code_evolution_30s/produce.py finish <出力フォルダー>
```

音声だけを修正する場合、`prepare`の末尾へ検証済み前版の出力フォルダーを渡す。映像入力、描画コード、フォント、依存定義と元MP4のhashを確認し、一致すれば描画を省略して`finish`へ進める。前版の記録は上書きしない。

## 状態と範囲

- 案件用スクリプトによる初稿であり、Studio UI・DBに保存された制作／Run／Jobではない。共通の音声・合成・日本語フォントを再利用する。アプリ本体の機能拡張ではない。
- 過去作品と通常DBは保持する。外部チャット送信、Claude画面操作、画面収録、課金API、画像生成、H3生成、BGM、YouTube投稿は行わない。
- ローカルSayakaの仮音声。音質改善は保留のままで、公開品質や利用者採用を合格にしない。
- 初回2試行はSAPIの発話が5秒枠を超えて停止。時刻指定なしで6発話を実測し、長かった2文を短縮した。速度変更・途中切断はしていない。
- 採用した発話枠は0.300–3.913、5.300–9.413、10.300–14.518、15.300–19.003、20.300–24.863、25.300–29.388秒。

## 音声改訂版の出力と検証（2026-09-16）

- [速度・発音を修正した字幕付きMP4](../../outputs/studio/runs/run_c8342a634b92bc4a555dc5ef0ee51e5c/assembly/E2A86DEE7631216F70BB9CB6C2FC81DD9AB7A45C8D842D5E7679BBCB748CD378/master-captioned.mp4)
- [改訂版ZIP](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T225201850242Z/claude-code-evolution-review.zip)
- [速度・発音入力・映像一致の確認](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T225201850242Z/audio-revision-check.json)

発音が変わらない5文の実WAV尺の合計から、速度は前版の約1.112倍（発話時間は約10%短縮）。小数版の発話は「九月、フェイブルごーてんいち。」で、整数版の「ファイブ」も合成入力のhashと一致した。各発話は0.300–3.550、5.300–9.001、10.300–14.096、15.300–18.254、20.300–24.404、25.300–28.976秒。字幕終了もこの実測へ更新した。

無音映像は前版から再利用し、字幕なし完成MP4の映像ストリームも前版と同じSHA-256を確認。両MP4の30秒・720frames・1080×1920・24fps・H.264＋AAC 48kHz、全decode、ZIP全entryのCRCとhash照合が成功。17秒の360px幅の完成画像でもモデル名と字幕の非重複を確認。以前の音声ノイズ改善や公開品質の実聴判定を完了したという意味ではない。

## 初稿の出力と検証

出力：`outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T170359776543Z/`。UTCのディレクトリー日付は9月15日、制作日はJSTの9月16日。

- [音声・字幕付きMP4](../../outputs/studio/runs/run_16778de72896787eaa92202f7b85d375/assembly/2802BC505E339F1A60C1FE7CB61163BE8A690D753CDC790B67719543666943AD/master-captioned.mp4)
- [字幕なしMP4](../../outputs/studio/runs/run_16778de72896787eaa92202f7b85d375/assembly/2802BC505E339F1A60C1FE7CB61163BE8A690D753CDC790B67719543666943AD/master-clean.mp4)
- [確認用ZIP](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T170359776543Z/claude-code-evolution-review.zip)
- [投稿用テキスト](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T170359776543Z/publication.txt)
- [形式・発話時刻の検証JSON](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260915T170359776543Z/verification.json)

両MP4は30.000秒・720frames・1080×1920・24fps・H.264＋AAC 48kHz。独立したffprobeと全音映像decodeに成功。6発話は対応する5秒枠内に収まり、字幕は実WAVの境界から生成した。2／7／12／17／22／27秒を360×640へ縮小して目視し、主要文字・モデル名・グラフ値・字幕の可読性と、字幕／図解の非重複を確認した。出典や非公式表記の小さな補足文は概要欄にも記載する。30秒を通した聴感・音声ノイズの改善・公開採用は未確認。

字幕付きSHA-256：`E57D517603E90B75BA4A3F64A7D72F562A5382ED0CB6CB42A21AEA4895021F36`。字幕なし：`626AC0460CB8AFA17EA0DB361DD0D6171FA333B3F098D902AC6065B01555338E`。ZIP：`3B4174CE4F02CB15C04328CB46C0C5DEAA9BCB0F846B602E9C1B4593756A3CA1`。ZIPの10項目はCRCと全payload hashを読み戻して一致した。

`node --check render.mjs`、Pythonの構文コンパイル、`git diff --check`も成功。通常Studio UIの一気通貫試験や全アプリの回帰試験とは区別する。初稿制作完了時点ではGit commit／push・外部公開は未実施だった。

## Gitへの保存範囲

利用者の依頼により、制作コード、台本、発音設定、出典、制作記録とアーキテクチャ文書を個人フォーク`benriworks/MiniMax-H3`へ保存する。`outputs/`は既存の`.gitignore`で除外されるため、MP4・WAV・ZIP・実行ごとの検証JSONはローカル成果物。本書の`outputs/`リンクはこのPCで利用するもので、GitHubへの動画アップロードを意味しない。Gitへの保存とYouTube公開・作品の採用判断は別である。
