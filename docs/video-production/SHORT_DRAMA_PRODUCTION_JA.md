# ショートドラマ制作の実行手順

2026-11-12。真帆の前編・続編・前後編まとめで使った、企画から再編集までの手順。作業を始めるときは、案件の`RESUME_AND_KNOWHOW_JA.md`で対象版、採用済みの人物・声・構成、今回の変更範囲を確認する。画角や演出の設計は[ドラマ編集プレイブック](SHORT_DRAMA_EDITING_PLAYBOOK_JA.md)を使う。

## 制作の進め方

1. 初めて作る回は[制作記録ひな形](templates/PRODUCTION_RECORD_JA.md)から案件を作る。人物・場所・小物の基準画を分け、カットIDごとに役割、完成上の秒数、台詞、必要な動作、前後のつながりを決める。新シリーズは人物の基準画・衣装・役割に対するユーザーの確認を記録してから本番生成へ進む。
2. 静止画と既存素材で仮編集し、動きが必要な箇所を選ぶ。基準画は顔・服・場所・小物と画角を照合し、開始画と終了画が必要なら対にして保存する。画像用のプロンプト・参照の役割・出力名はカットIDで追えるようにする。 [続編の基準画の記録例](../../productions/content-projects/CONTENT_20261111_short_drama_ep02/prompts/imagegen-v01.json)
3. 新規生成の範囲はカットまたは台詞単位で決める。既存の素材は採用区間とハッシュを確認して使う。声・BGM・環境音は別トラックで保存し、最初の一音、発話、カット境界、最後の音を仮編集で合わせる。
4. 新しい版に書き出し、尺・全編デコード・字幕・実フレーム・音量・素材との同期を確認する。人による最終試聴、スマホ再生、ユーザー採用、公開はそれぞれ確認した日と対象版を記録する。見出し、YouTube説明欄、記事草稿と画像の受け渡しも用意する。 [動画と記事の工程](VIDEO_TO_BLOG_WORKFLOW_JA.md)

新しい回を実装するときは、カット表を基に案件の編集スクリプトでカットID・採用区間・尺・音声・字幕を指定する。台詞を作る場合は台詞IDと役ごとの声を案件側で定める。真帆の `render_episode.py` と `synthesize_dialogue.py` は続編のカットと台詞を実装した例として参照する。 [続編の編集コード](../../productions/content-projects/CONTENT_20261111_short_drama_ep02/render_episode.py)

## コードとローカル素材の置き場所

GitHubから取得する制作コードと、Windowsで素材を保管している場所を作業開始時に確認する。専用worktreeから実行するときも、既存の素材ルートを引数で渡す。別PCでは、利用権限のあるバックアップなどから必要な入力を移し、相対パスの構造を再現する。

| 場所 | 保存するもの |
| --- | --- |
| `productions/content-projects/<案件ID>/` | Git管理する台本、プロンプト、再開記録、再現手順、編集スクリプト、公開可能な出典と検証要約 |
| `outputs/content-projects/<案件ID>/characters/<版>/`、`references/<版>/`、`plates/<版>/` | ローカルの人物基準、ロケーション、小物参照、カットの開始画・終了画 |
| `outputs/content-projects/<案件ID>/shots/<版>/<カットID>/` | 動画原本 `source.mp4` と生成台帳 `generation.json` |
| `outputs/content-projects/<案件ID>/audio/<版>/tts/<台詞ID>/` | 台詞原本とリクエスト・応答のローカル記録 |
| `outputs/content-projects/<案件ID>/edit/<版>/`、`qc/<版>/` | 編集カット、音声ステム、検査用フレームとログ |
| `outputs/content-projects/<案件ID>/review/<版>/`、`blog-handoff/<版>/` | レビューMP4、記事用派生素材、原本からの切り出し記録 |
| `outputs/content-projects/<案件ID>/_private/` | 配布音源、共有レシートなどローカル保管の情報 |

絶対パスは実行時に設定し、Gitの記録では素材ルートからの相対パス、版、bytes、SHA-256を使う。既存素材を入力にして、出力には未使用の版名を指定する。途中結果や旧版は調査・比較に使えるよう保全する。前編の桟橋テスト素材のように案件外の入力がある場合は、所在と用途を再現手順に記す。

次はWindowsの例。制作コードのルートで実行し、保管先が異なる場合は最初の行をそのPCの `outputs` に合わせる。別PCの作業先では、必要な素材の読込権限と新しい版の出力先を確認する。

```powershell
$localOutputRoot = (Resolve-Path -LiteralPath (Join-Path $env:USERPROFILE 'MiniMaxH3\outputs')).Path
$mediaRoot = (Resolve-Path -LiteralPath (Join-Path $localOutputRoot 'content-projects')).Path
Get-Command python, ffmpeg, ffprobe | Select-Object Name, Source
python -B -c "import numpy, PIL; print(numpy.__version__, PIL.__version__)"
ffmpeg -version | Select-Object -First 1
```

既存の真帆の編集環境はWindows、Python 3.12、NumPy 1.26.4、Pillow 12.3.0、FFmpeg／ffprobe 8.1.2、Yu Gothic Bold。再現前に該当案件の入力を `Test-Path -LiteralPath` と `Get-FileHash -Algorithm SHA256 -LiteralPath` で照合する。存在しない素材やアクセスできない保管先は、必要な版と影響を案件に記録し、素材を用意できた工程から進める。

## APIの使い方

外部APIへの送信は新しく作る素材に限る。対象、モデル、秒数・解像度、予定回数、概算、送信可能な素材を確認してから実行する。承認済みの制作範囲で必要な初回送信に `--confirm-billable` を付ける。追加料金が発生する変更は、元の依頼と費用範囲を照合する。価格と利用制限は実行時に公式情報で確認し、推計と実請求を区別して記録する。 [MiniMaxの料金](https://platform.minimax.io/docs/pricing/overview#h3-series-flagship-models) · [Geminiの料金](https://ai.google.dev/gemini-api/docs/pricing)

| 用途 | 入口と認証 | 保存する結果 |
| --- | --- | --- |
| 新規カット | [案件のH3 CLI](../../productions/content-projects/CONTENT_20261108_short_drama/generate_h3_shot.py)。実行プロセスの `MINIMAX_API_KEY` | カットID、入力画像の版とハッシュ、プロンプト、送信時刻、受付ID・使用量、MP4とハッシュ |
| 新規台詞 | [続編の台詞CLI](../../productions/content-projects/CONTENT_20261111_short_drama_ep02/synthesize_dialogue.py)。実行プロセスの `GEMINI_API_KEY`、代替は `GOOGLE_API_KEY` | 読み原稿、話者、モデル、送信記録、応答、検証済みWAV |
| 企画・制作台帳 | 既存の [ContentWorkspace CLIとローカルAPI](../../STUDIO_CONTENT_WORKSPACE_JA.md#3-共通cliとapi)。HTTPはStudioのセッション認証 | 企画、採用記録、人物・素材ID、絵コンテ、記事との参照 |

キーは許可されたアカウントで設定し、値を表示する代わりに `[bool]$env:MINIMAX_API_KEY` と `[bool]($env:GEMINI_API_KEY -or $env:GOOGLE_API_KEY)` で存在だけ確認する。汎用の `run-api.ps1 doctor` の `.env` 設定は[セットアップ](../../LOCAL_SETUP_JA.md)を使う。公開用のGit差分には台本・コード・根拠と必要な検証要約を選び、キー、認証ヘッダー、署名付きURL、非公開の原本と生応答はローカル側で管理する。

### MiniMax H3のカット

案件CLIは公式V2の `POST /v2/video_generation` で生成を開始し、`GET /v2/query/video_generation/{task_id}` で同じタスクを照会する。開始画を指定するとI2VA、終了画も指定するとFL2VA。ローカル画像のデータが送信されるため、許諾された参照だけを渡す。複数の参照素材でRef2VAを選ぶ場合は汎用API経路と公式の入力組み合わせを確認する。 [生成API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) · [タスク照会API](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)

続編で使った768P・5秒・開始と終了画の例。新しい試行には未使用のフォルダーを指定し、初回送信を1回実行する。

```powershell
$episode = Join-Path $mediaRoot 'CONTENT_20261111_short_drama_ep02'
$shot = Join-Path $episode 'shots\v02\06-together'
$h3 = 'productions/content-projects/CONTENT_20261108_short_drama/generate_h3_shot.py'
python -B $h3 $shot --prompt 'productions/content-projects/CONTENT_20261111_short_drama_ep02/prompts/06-together.txt' --image (Join-Path $episode 'plates\v01\06-together.png') --last-image (Join-Path $episode 'plates\v01\06-together-end.png') --seconds 5 --confirm-billable
```

受付後に止まったら、`python -B $h3 $shot` で同じ `generation.json` から再開する。`submission_unknown` で受付IDがない場合は、実行時刻・対象カット・利用明細を照合し、同じタスクが特定できてから回収する。汎用CLIで確定した受付を回収する場合は `.\run-api.ps1 wait $taskId --output $recoveredMp4` を使い、取得先と結果を案件台帳に戻す。同じ意図の送信を別フォルダーから重ねない。取得後は全デコードと前後の実フレームを確認し、採用した元動画の区間を編集記録に残す。

### Geminiの台詞

続編は `gemini-3.8-flash-tts` を使い、真帆はAoede、父はCharon。人物と声の組み合わせ、読みと台詞の実尺は作品ごとに照合する。1行だけ試すときは、続編のCLIに読み原稿と台詞IDを指定する。 [Geminiの音声生成仕様](https://ai.google.dev/gemini-api/docs/speech-generation) · [読み原稿と試聴の手順](NARRATION_HANDOFF_JA.md)

```powershell
$episode = Join-Path $mediaRoot 'CONTENT_20261111_short_drama_ep02'
$voiceRun = Join-Path $episode 'audio\v03\tts'
$voice = 'productions/content-projects/CONTENT_20261111_short_drama_ep02/synthesize_dialogue.py'
$reading = 'productions/content-projects/CONTENT_20261111_short_drama_ep02/dialogue-read-v02.txt'
python -B $voice $voiceRun --reading $reading --line d01-father --confirm-billable
```

応答を保存済みなら、同じフォルダー、読み原稿、台詞IDを指定し、`--confirm-billable` を外してローカルでWAVを検査する。受付や応答が不明のときは記録と利用明細を確認し、追加の送信を判断する。採用WAVの出所とタイミングを記録し、既存の声を使う編集では保存済みWAVを入力にする。

## APIを使わない再編集

| 対象 | 入力と実行手順 |
| --- | --- |
| 『日曜、海に行かない？』v06 | 前編の基準画、既存カット、比較元のv05。 [前編の再編集](../../productions/content-projects/CONTENT_20261108_short_drama/REPRODUCTION_JA.md#画角修正版v06の再編集) |
| 『お父さんも、入って。』v02 | 続編の動画・台詞原本と前編の写真裏。 [続編の再編集](../../productions/content-projects/CONTENT_20261111_short_drama_ep02/REPRODUCTION_JA.md) |
| 『また、二人で。』v02 | まとめ版v01の映像、両話の音声ステム、利用条件確認済みのピアノ原曲。 [ピアノ版の再書き出し](../../productions/content-projects/CONTENT_20261111_maho_compilation/RESUME_AND_KNOWHOW_JA.md#ピアノ版の再書き出し) |

素材から再編集する工程はPythonとFFmpegで実行する。ローカルGPUで新たに映像を生成する場合は、[ComfyUIのローカル構成](../../LOCAL_SETUP_JA.md)の対応プロファイルを確認し、GPU・モデル・ワークフローをdoctorで照合して試作1カットを検査する。案件記録には、実際に使った生成経路と完成版への採用区間を記す。

レビュー動画はDriveの確認用フォルダーへ保存し、ファイル名・容量・親フォルダー・アクセス範囲を読戻す。GitHubへは公開可能な制作資料だけをコミットする。実際のpush先を確認し、この制作環境では個人フォークの対象ブランチに反映する。納品MP4、WAV、ZIP、原本と共有レシートはローカルと許可された共有先で扱う。

## 手順の確認記録

2026-11-12、Windowsの保存済み素材から前編v06、続編v02、まとめピアノ版v02を、それぞれ `-runbook-check-20261112` を付けた別版に書き出した。3本とも元のMP4とSHA-256が一致した。H3 APIクライアントはローカルの模擬応答を用いた10件のテストに合格した。
