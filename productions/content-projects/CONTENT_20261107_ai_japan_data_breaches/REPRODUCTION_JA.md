# 国内情報漏えいTop10の再編集手順

作業ルートはMiniMaxH3。最新は公表件数順のv03。Gitには軽量なコード・台本・来歴を保存し、原本・生成音声・人物素材・MP4はoutputsに置く。

## v03を再編集する

最新のユーザー指示は[共通台帳の読戻し](workspace-production-v03.json)、順位と人口の式は[件数表](ranking-volume-v03.json)。原本と確認は[改訂記録](REVISION_V03_JA.md)を参照する。既存のv02引用・人物に、`capture_v03.py` の追加原本、`dialogue-display-v03.json` と `dialogue-tts-v03.json` を使用する。再利用の台詞IDは `voice-v01`、新規分は `voice-v03` の受領を照合する。

```powershell
$p = 'productions/content-projects/CONTENT_20261107_ai_japan_data_breaches'
python "$p/rank_volume.py"
python "$p/produce.py" plan short --version v03
python "$p/produce.py" audio short --version v03 --run replay-v03
python "$p/produce.py" video short --version v03 --run replay-v03
python "$p/produce.py" mux short --version v03 --run replay-v03
```

フルを再編集する際は `short` を `full` へ変更。元データが揃えば音声APIや人物生成を呼ばない。必要な台詞の新規生成は `generate_voices.py --short-version v03 --full-version v03 --only 台詞ID`。記事のパックは `build_article.py --version v03`。別版の原本と媒体を保持し、再現テストは `--run` で分ける。[v03入力照合表](reproduction-inputs-v03.json)

## v02の再編集

旧フルv02とショートv02の採用範囲は[企画の返答](acceptance-v02.json)と[案件記録](RESUME_AND_KNOWHOW_JA.md)。

## 入力と依存

- [入力照合表](reproduction-inputs-v02.json)に、原資料の出典ID、動画内の引用画像、人物入力、実使用PCM、原稿、フォントとコードのハッシュを収録。前作の人物MP4とフレームキャッシュは `outputs/content-projects/CONTENT_20261106_ai_bert_gpt_history/` の既存ファイル。前作の[再現手順](../CONTENT_20261106_ai_bert_gpt_history/REPRODUCTION_JA.md)も参照する。
- 引用画像は `outputs/content-projects/CONTENT_20261107_ai_japan_data_breaches/article-v02/assets/`。公式原本は同案件の `research/primary-v01/`。出典と原本の確認は[出典台帳](sources-v01.json)、撮影位置と選んだ範囲は `research/captures-v01/capture-manifest.json` と `selected-excerpts-v02.json` に記録。
- 音声の参照は `voice-v01/<台詞ID>/voice.wav` と `verified.json`。ショートv02のs06は `voice-v01/s06-v02/`。声のモデル、音量、受領を各版で照合する。
- Windows／Python 3.12、FFmpegとffprobe、Pillow、NumPy、BudouX。記事・引用再撮影には追加でPlaywright、Microsoft Edge、PyMuPDF、markdown-it-py。表示フォントはリポジトリ内のNoto Sans JP。

## 作業順

1. 企画の採用、集計の基準日、原公表・確度を照合する。数量台帳と順位計算を変えたら表示、読み、引用、記事も確認する。採点の比較は `build_research.py`。
2. 原本の取得・保存済みなら、既存ハッシュを照合して使う。新たな撮影は `capture_sources.py` と `refine_captures.py` を用いる。原本は分けて保持。ブラウザ撮影と原PDFの画像化を区別する。
3. 表示原稿と読み原稿の対応を確認する。音声が揃っていればAPIを呼ばず再編集できる。必要な台詞を新規生成する場合は `generate_voices.py --only 台詞ID` の対象と版を確認し、失敗や不明な受領を自動再送しない。人物は同じ白衣版の既存MiniMax素材を参照する。
4. 過去版を保存したまま出力版を分け、`produce.py plan`、`audio`、`video`、`mux` の順で実行する。対象は `full` または `short`。必要なら `--version v01` で初回の構成を参照する。再現検証は完成ファイルを上書きしない別出力で行う。

```powershell
$p = 'productions/content-projects/CONTENT_20261107_ai_japan_data_breaches'
python "$p/produce.py" plan full
python "$p/produce.py" audio full --run replay-01
python "$p/produce.py" video full --run replay-01
python "$p/produce.py" mux full --run replay-01
```

5. 全decode・フレーム数・実尺・字幕枠と最終AACを確認し、内容は[媒体QC](PRODUCTION_QC_V02_JA.md)にある実フレームと照らす。ショートv02を同じ入力から `--run frozen-input-check` へ再出力し、納品MP4とSHA-256の一致を確認した。別PCでの環境再構築は確認対象として残る。
6. 記事素材とMarkdownを `build_article.py` でHTML・PDF・素材パックにまとめる。採用後の台帳記録は `record_workspace.py`。人のレビュー、公開、リモートへの軽量な記録の保存は、それぞれの確認結果を案件記録へ追記する。
