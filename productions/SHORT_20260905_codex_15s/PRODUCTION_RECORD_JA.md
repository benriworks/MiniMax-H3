# Codex 15秒動画 — 制作記録

制作日: 2026-09-05

## 意図と方式

技術の詳細を早口で詰め込む説明ではなく、Codexを使う「依頼 → 実装 → 確認」を伝える非公式紹介ショート。人物映像やリップシンクは使わず、大きな日本語タイポグラフィとUIの図案を中心にした。

元となるアプリの品質・UX整備は `6910c43` でコミット、`a2bde0a` でmainへマージした。その後、案件専用ソースを追加して制作。main統合後のfrontend試験も169件合格した。公式・個人フォークのどちらにもpushしていない。

制作に新しいH3推論、画像生成、外部TTS API、BGM、YouTube投稿は使っていない。図案は実画面収録と区別し、音声はローカルのMicrosoft Haruka Desktopによる合成。

## 再生成

```powershell
node productions/SHORT_20260905_codex_15s/render.mjs --stills
node productions/SHORT_20260905_codex_15s/render.mjs --videos
.venv\Scripts\python.exe productions/SHORT_20260905_codex_15s/assemble.py
```

Studioが同じworkspaceを使用している場合、先に終了する。assembleは既存のsingle-writer lockを取得する。新しい実行にはtimestamp付き成果物ディレクトリを割り当て、過去の完成ファイルを上書きしない。同じ媒体・台本・設定のworker cacheは検証して再利用する。

このコマンドは標準Quick Createではない。案件専用に既存SAPI / Remotion / FFmpeg / QC workerを呼び、実ファイルをStudioへ登録する。標準pipelineのJobやRunが成功したという虚偽の状態は作らず、`studio_run_id: null` と独立worker実行IDをmanifestへ残す。Studioの素材・成果物で参照できるが、標準成功Jobを必要とする納品ZIPパネルとは別経路となる。

## 台本とタイミング

| カット | 完成尺 | 見出し | ナレーション |
| --- | --- | --- | --- |
| 1 | 0〜5秒 | 作りたい。を、言葉に。 | 作りたいものを、言葉で伝える。 |
| 2 | 5〜10秒 | 実装から、テストまで。 | Codexが、実装やテストを手伝う。 |
| 3 | 10〜15秒 | 確かめて、次の一歩へ。 | 成果を確かめて、次の一歩へ。 |

3素材の尺は126 / 126 / 120 frames。24fps、2箇所各6 framesのfadeを引いて360 frames＝15秒とする。素材の大見出しを残し、追加のtimeline overlayはnull。

読み上げ字幕は6文に分割。開始時刻は0.200 / 2.100 / 5.100 / 6.950 / 10.200 / 12.350秒。rate=0、`Codex` → `コーデックス`の読み替えを使用。事前WAV計測による各文長は1.819 / 1.948 / 1.714 / 2.394 / 2.064 / 1.739秒で、最後は14.089秒に終了する。声を切らずに、約0.9秒を結びの画面に残す。

## 出力・確認

状態: **technical / independent visual PASS**。人による最終試聴・公開は未実施。

| 項目 | 結果 |
| --- | --- |
| 読み上げ字幕あり | `outputs/productions/SHORT_20260905_codex_15s/Codex_15s_captioned.mp4`、1,229,812 bytes |
| 読み上げ字幕なし | `outputs/productions/SHORT_20260905_codex_15s/Codex_15s_clean.mp4`、1,183,374 bytes |
| 尺・映像 | 15.000秒、1080×1920、24fps、360 frames、H.264 / yuv420p |
| 音声 | AAC、48kHz、stereo。元SAPIは22.05kHz monoで、48kHz化が音質向上を意味するわけではない |
| 音声計測 | Integrated -18.8 LUFS、true peak -4.7 dBFS。意図した区切りの無音あり、全編無音・clippingなし |
| 全フレームdecode | 両マスターで成功 |
| 黒画面・静止判定 | 0.5秒以上の黒区間0、-60dB基準の1秒以上の静止区間0 |
| 目視 | 1秒ごとの15枚、最長字幕の8秒、CTAの13・14秒を主担当／別担当で確認。文字切れ・重なりなし |
| Chrome再生 | 字幕版を0〜15秒まで再生しended=true、media errorなし、dropped frames=0、console error / warning=0。ブラウザーはミュートで検査し、聴取済みとはしない |
| 機械処理時間 | 3素材描画の合計86.822秒＋音声・timeline・合成・QC・取込228.235秒。台本・実装・目視時間を除く |
| Studio | `production_f2bd026db5c153669db88bc491004a5f`。正規取込でsourceと完成動画を登録、中間成果物と独立実行eventを保持 |
| 投稿用テキスト | `PUBLICATION_JA.txt`がtracked原本、outputs内`publication.txt`が手元の投稿用コピー |

マスターSHA-256:

- captioned: `1507AB4945BC823C07C9CB8AD1583B9743A6498BC220AFA8A792BA18376C5D3A`
- clean: `879F8BF4670ABB4D70843667498EED73255394CE1577939D86A8DA6E3ACC5E05`

独立worker cache ID: `run_6949cc936d5ae57c3d58b2b829111380`。実行manifest / WAV / SRT / JSON / eventsは `outputs/productions/SHORT_20260905_codex_15s/executions/6949CC936D5AE57C3D58B2B8291113809487D2E9140B1048A31AB840E0C01109/20260905T034055196526Z/` に保存。字幕版QCの詳細は `outputs/studio/runs/run_6949cc936d5ae57c3d58b2b829111380/qc/F25A56D5E43F810EB98D710406BA6D33F8A9353C1A6EDF1587F47B93901AC5D6/technical-qc.json`。

1秒ごとの画像は `outputs/productions/SHORT_20260905_codex_15s/contact-sheet.jpg`、独立確認画像は `qc-independent-08s.png` / `qc-independent-14s.png`。今回の確認は公式YouTubeの表示状態や投稿受付の試験ではなく、Shorts想定のレイアウトとローカル実ファイルの検証である。

大見出しのある素材3枚は主担当と別担当が実画像を確認し、主要文字の切れ・重なりがないことを確認した。下部の読み上げ字幕領域を空け、右端160pxに重要情報を置かない。画面最下部の英語フッターと番号は装飾で、投稿サービスのUIに隠れても要旨は失われない。

自然さ・発音の最終試聴、公開判断は利用者に残す。SAPIの入力・読み替え・WAVタイミングを検証しても、人が実際に聴いたという証拠にはしない。参考出典と素材の境界は[ASSET_PROVENANCE_JA.md](ASSET_PROVENANCE_JA.md)を参照。
