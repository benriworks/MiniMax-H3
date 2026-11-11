# Claude Codeを支えるAI：3か月の進化

## 2026-09-18：冒頭5秒を高画質化

夜景の方向性は維持し、MiniMax H3の生成サイズを480×864から768×1376へ上げた（原本画素数は約2.548倍）。同じprompt・seed・20 steps・5秒で新しく生成したため、建物の配置は前版と異なる。窓の区切り、建物の輪郭、水面の反射を1080px幅の比較画像と20点の連続contactで確認した。

- [高画質改訂版の字幕付きMP4](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T194143534675Z/master-captioned.mp4)
- [高画質改訂版の確認用ZIP](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T194143534675Z/claude-code-evolution-review.zip)
- [解像度・圧縮・音声同一性・目視の確認](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T194143534675Z/hq-revision-check.json)
- [生成記録](../../verification/night-city-hq-2026-09-18.json)／[完成版1080px幅の確認画像](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T194143534675Z/preview-full-02.png)

原本生成はローカルofficial INT8 + Q4／Dynamic VRAMで1,412.682秒、課金APIなし。原本CRF 14、Remotion中間CRF 12、字幕付きは中間から直接CRF 14／slowで1回だけ圧縮する`hq_direct_v1`を使用。字幕なし映像はstream copyで中間映像のpacket hashと一致した。ナレーションは前版のAACをそのままcopyし、両完成MP4で前版とのaudio stream hash一致を確認。字幕の共通80px preset、最低54pxの図解、台本と読み方を保持した。

生成映像ラベルは下部に統合し、ビル群の中央を見せる配置へ変更。完成版を1080px幅と360px幅で確認し、文字・字幕の非重複を確認した。冒頭以外の5場面の描画画像は前版と同じhash。両MP4は30秒・720frames・1080×1920・24fps・H.264＋AAC 48kHzで全decode成功、ZIP全10項目のCRC／payload hashも一致。Python／Node構文確認、`git diff --check`も成功した。確認用改訂版であり、利用者採用やYouTube公開は未実施。

現行版の再制作は`produce.py prepare --reuse-audio <検証済み前版の出力フォルダー>`→`render.mjs <新しい出力フォルダー>`→`produce.py finish <新しい出力フォルダー>`。HQ経路は前版の検証済み音声を必須とし、通常Studioの標準assemblyを変更しない。各世代の原本・完成版は別フォルダーに保持する。

## 2026-09-18：明るくきらめく夜景へ差し替え

利用者の依頼で、金色・白のビル照明と青・金色の水面の反射が見える夜景をMiniMax H3で新しく生成した。縦480×864・24fps・124framesの素材から冒頭5秒を使用し、暗幕の軽減、明るさと彩度の調整、文字の影、出典案内の半透明背景を加えた。最低54pxと前版のナレーションを維持している。

- [明るい夜景に差し替えた字幕付きMP4](../../outputs/studio/runs/run_d9bccab59caef5645b9b6b0db4e94ed7/assembly/05473C44AF6D1BCFCA6E3C8CB28833B5D2DF47965F9AB5ED22B5B305D828F93E/master-captioned.mp4)
- [夜景改訂版の確認用ZIP](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T190404737055Z/claude-code-evolution-review.zip)
- [音声・後半図解の一致と見た目の確認](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T190404737055Z/night-revision-check.json)
- [新規H3生成の記録](../../verification/night-city-2026-09-18.json)／[生成prompt](prompts/NIGHT_CITY_H3.md)

ローカルofficial INT8 ConvRot + Q4／Dynamic VRAM／20 stepsで369.984秒、課金APIは未使用。生成graphと実行historyの一致、原本hash、媒体形式と全decodeを検証。0／2／4秒の原本と、文字・字幕を重ねた360px幅の完成画像を目視し、照明・反射と文字の非重複を確認した。

完成版は両MP4とも30秒・720frames・1080×1920・24fps・H.264＋AAC 48kHzで全decode成功。ZIP全10項目のCRCとpayload hashも一致した。前版とナレーション4成果物および完成版AAC音声のSHA-256が同じで、冒頭以外の5場面の描画確認画像も同一だった。確認用の改訂版であり、利用者採用・YouTube投稿は未実施。前版成果物は保持し、今回起動したComfyUIは生成完了・空queue確認後に停止した。

## 2026-09-17：文字の下限とアイキャッチを更新

利用者の依頼で最低54px（360px表示では18px相当）へ拡大し、補足文も短く整理した。冒頭5秒はMiniMax H3で生成済みの夕暮れの都市映像を採用候補として配置。「MiniMax H3 生成映像」と表示し、元音声は使わない。原本と生成記録はhashを照合する。詳細は[SOURCES_JA.md](SOURCES_JA.md)の2026-09-17追補。

今回の準備は`produce.py prepare --reuse-audio <9月16日音声改訂版の出力フォルダー>`を使用する。声・速度・発音辞書・台本・発話時刻と4つの音声成果物を照合して再利用し、`render.mjs`と`produce.py finish`で新しい映像へ合成する。新規H3生成とSAPIの再合成は行わない。

### 更新版の出力と検証

- [文字拡大・MiniMaxアイキャッチ入りの字幕付きMP4](../../outputs/studio/runs/run_ed514f7625655294cd05213f17431374/assembly/464F33EA15C9401B6CC0BF68672AE258FE34D5FA7043DC5F77CF03F781699FF9/master-captioned.mp4)
- [更新版の確認用ZIP](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T100948962629Z/claude-code-evolution-review.zip)
- [文字・既存生成映像・音声同一性の確認](../../outputs/productions/SHORT_20260916_claude_code_evolution_30s/20260917T100948962629Z/visual-revision-check.json)

両MP4は30秒・720frames・1080×1920・24fps・H.264＋AAC 48kHzで、全decodeに成功。ZIPの10項目はCRCと全payload hashを読み戻して一致した。完成版の2／7／12／17／22／27秒を360×640で目視し、日付・補足・グラフ目盛りの可読性、字幕との非重複、冒頭の都市映像と生成表記を確認した。

ナレーション4成果物を前版と同じpath／hashで再利用し、完成版のAAC音声ストリームも前版と同じSHA-256（`d949b0ed57f384ca924d06c11b077447fd818ec7e0b140472b8a67e0522bd2d5`）だった。速度と小数版／整数版の読み方を保持している。これは利用者が確認するための改訂版で、採用やYouTube投稿は未実施。

## これまでの制作記録

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
