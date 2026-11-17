# 再現手順｜ショートv03・フルv02・記事v01

個人フォーク `3d70c39` を基点に制作。Windows 11、Python 3.12系、Pillow・numpy・BudouX・markdown-it-py、Noto Sans JP（Studio同梱）、FFmpeg 8.1系。素材先は `outputs/content-projects/CONTENT_20261117_japan_ai_usage`。

1. [出典台帳](sources.json) の版の公開CSVを `_private/aei-claude-ai.csv` に置く。Playwright CLIの独立したChromiumを幅1800×1150で使用し、Anthropic公式の Global usage と Country usage（Japan）を要素撮影。AWSは本文の要点を画面中央に移してからビューポートを撮影。原本名と切り出し座標を台帳に合わせる。
2. 11月10日のFable 5.2動画案件の `outputs/content-projects/CONTENT_20261110_fable_5_2/motion/` にある男女4クリップを確認し、`prepare.py --motion-source <前回素材のmotionフォルダー>` を実行。出力の `dataset-check.json`、`captures/figures/manifest.json` と `motion/manifest.json` に照合結果を残す。
3. ローカル曲庫から元の `happytime.mp3` を `_private/` に置き、SHA-256を照合。音声は保存済み `voice/gemini-v01` とその検証レシート、`voice/selected.json` を使う。生成が必要な新版では `narrate.py gemini`、必要に応じて `narrate.py local` で別の声として記録する。検証済みテイクはリクエストを重ねない。
4. `render.py preview short` と `render.py preview full --edition v02` を実行し、字幕の収まりと絵を確認。新しい出力ルートで `render.py render short` と `render.py render full --edition v02` を実行する。既存MP4のあるフォルダーへ上書きしない。
5. `record_workspace.py` と `package_article.py` を順に実行。ZIPをチェックサムで照合し、一時ローカルHTTPで `review.html` を表示して画像とリンクを確認する。

フルv01は最初のレビュー候補。AWSのページ上部固定ナビが公式引用に重なったため、フルv02の引用範囲と紙面を更新。v01のMP4・字幕・初回検査、旧原本を保管している。v02はv01と符号化音声・SRTが同じ。出典ファイルを変更した別PCでのバイト一致は未検証。

## ショートv02の書き出し

1. 上の1〜3の素材と、ショートv02選択記録 `voice/selected-short-v02.json`、`voice/gemini-short-v02/` のWAV・`takes.json` を照合する。記録は案件の出力ルートにある。再生成が必要なときは案件フォルダーで `python -X utf8 short_proposal_voice.py` を実行する。v01の検証済み音声を照合し、女性の変更3台詞を生成する処理。Geminiを呼ばずに再編集するときは保存済みWAVを使う。
2. `python -X utf8 render.py preview short --edition v02` で字幕と画面を確認し、`python -X utf8 render.py render short --edition v02` で `release/v02/short/` にMP4・SRT・時刻・技術検査・復号フレームを出力する。既存MP4がある場合は別の出力環境で実行する。
3. 提案書の生成を再検証する場合は Claude Code 2.1.316以降の実行環境と利用可能な認証を確認し、未使用の連番で `python -X utf8 proposal-demo-v02/run.py --attempt 4` を実行する。これは新しいモデル呼び出しになる。今回の入力・実応答・検査結果は [v02改訂記録](PROPOSAL_SHORT_REVISION_V02_JA.md)。モデルの応答のバイト一致は未検証。

## ショートv03の書き出し

ショートv02の保存済み入力素材・WAVを参照し、案件フォルダーで `python -X utf8 render.py preview short --edition v03`、`python -X utf8 render.py render short --edition v03` を実行する。出力先は `release/v03/short/`。復号フレームの `s-hook-turn-00.jpg` と `s-end-turn-01.jpg` で人物下の表示を確認し、v02とv03のAACパケット・時刻とSRTのハッシュを比較する。 [納品検査](DELIVERY_QC_JA.md#ショートv03)
