# dots紹介ショート全9本


> 2026-10-30整理：現在の判断と次の作業は [再開履歴兼ノウハウ](RESUME_AND_KNOWHOW_JA.md) を先に確認する。以下の制作時点の記録は履歴・詳細根拠として保持する。

## 最新のアップロード状況（2026-10-24）

ChatGPT（dots）編はすべてYouTubeへアップロード済みとのユーザー申告を受領。[現在の記録](../SERIES_20261023_dots_final_delivery/publication-status.json)を参照。以下の未投稿・確認待ち等は各制作時点の履歴であり、現在のアップロード状況とは分けて読む。

## 第5〜9弾の人物・公式画面引用版（2026-10-22）

残り5本は[完結編の制作記録](../SERIES_20261022_dots_finale/README.md)に完成候補をまとめた。新しく作成した人物の案内役を冒頭と締めに配置し、Aoede音声、機能ごとに異なる動く解説、OpenAI公式資料の短い画面引用を使用する。各30秒・1080×1920。全35場面のスマホ幅での画面確認、完成MP4の全体デコード、各ZIP全10メンバーの照合を終えている。最新のMP4・ZIPと状態は[納品一覧](../SERIES_20261022_dots_finale/delivery.json)を参照。既存の動画は保持し、最終試聴・採否・YouTube公開は利用者確認用。

## 第4弾の公式画面引用版（2026-10-22）

第3弾までYouTube公開済みとの利用者申告を受け、[第4弾「並行作業」の改訂候補](../SHORT_20261022_dots_04_editorial/README.md)を作成した。公式ページの画面例3箇所と新しい編集演出、Aoede音声を使用する。元の9本と公開済みの第3弾Aoede版は保持する。第5〜9弾の完成候補は上記の完結編へ続く。

## 第3弾のAoede改訂版（2026-10-22）

利用者からクラウドPC補足編までYouTube公開済みとの申告あり。次の「アプリ連携」は[独立したAoede版](../SHORT_20261022_dots_03_aoede/README.md)で完成候補を作成した。公式資料を再確認し、旧数値の場面を接続方法へ更新。旧全9本のMP4とこの一覧の既存納品物は保持し、改訂版への参照は独立して管理する。以後の基本の声はAoede、Koreは必要に応じて使うという利用者の選択を制作記録へ残す。

## 確認用納品物（2026-10-06）

- [全9本の再生一覧](../../outputs/productions/SERIES_20261005_dots/20261005T153642158910Z/release/index.html)
- [公開用一式 ZIP・約103MiB](../../outputs/productions/SERIES_20261005_dots/20261005T153642158910Z/dots-shorts-series.zip)
- [第1話 MP4](../../outputs/productions/SERIES_20261005_dots/20261005T153642158910Z/release/01/dots-01.mp4)
- [検証記録](../../verification/shorts-dots-2026-10-06.json)

9本とも30秒・1080×1920・24fps。全6,480framesの描画時文字領域検査、完成MP4の全decode、各8場面の360px幅の目視確認に合格。音量は-16.13〜-15.94 LUFS、最大true peakは-1.50 dBFS。ZIPの全62ファイルを読み戻し、CRCとhashを照合。再生ページの56個の相対参照も存在を確認した。Pythonテスト8件、TypeScript検査が成功。

状態は`verified_candidate_awaiting_user_review`。技術・画面の確認と利用者の採否を分け、聴感は利用者の最終確認用。YouTubeへの投稿は実行していない。失敗した中間出力は別日時フォルダーに残し、納品物へ混ぜていない。

利用者指定：YouTubeで公開するため、OpenAI公式サイトで発表日と機能を調べ、機能別のショート動画を作る。1本30秒、全9本、計4分30秒。

`generate_stories.py`が各話の台本、字幕、発音辞書、タイトル、説明欄と場面別の出典を生成します。`series.json`は並び順、`SOURCES_JA.md`は公式の根拠と条件、`YOUTUBE_UPLOAD_JA.md`は公開用ファイルの使い方です。

```powershell
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\generate_stories.py
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\produce.py prepare
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\produce.py render --episodes 1
# 完成画像を検査後、残りを最大3本ずつ描画する
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\produce.py render --episodes 2 3 4 5 6 7 8 9 --jobs 3
# 実際の完成画像を確認した後だけ、該当するエピソードの目視記録を保存する
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\produce.py review --episodes 1 --note "実際に確認した画像と観点"
.\.venv\Scripts\python.exe productions\SERIES_20261005_dots\produce.py package
```

共通CLIのSAPI音声実測、尺検査、1080×1920のRemotion描画、BGM・効果音、音量正規化、全decode、hash照合を使用します。新規`diagram`は10種類の決められたアイコンから機能を図式化し、`stat`は日付や数値を大きく表示します。文字54px以上と右側・下側の余白を維持します。

男性と修正版女性の人物動画を既存の検証記録と照合して再利用します。新しい画像／動画生成APIは呼びません。生成ツール名や「図解イメージ」を画面に入れません。公式画面の録画と混同しないよう、説明欄に独自グラフィックスであることを記載します。

`outputs.json`は各話の作業フォルダー、`delivery.json`は最後に作成した確認用一式を指します。公開用ZIPへはMP4、カバー、SRT、台詞、YouTubeのタイトル・説明欄、要約した出典、照合用一覧のみを入れます。原文スナップショット、生成素材の内部パス、調査ログは公開用ZIPに含めません。

コード作成後のアプリ全体の設計は、独立したルートの`ARCHITECTURE.md`と`ARCHITECTURE_DIAGRAM.md`にも記載します。成果物の状態は技術検証・目視検証・利用者採否・YouTube公開を区別します。
