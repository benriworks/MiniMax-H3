# MiniMaxH3 Studio MVP

## 目的

MiniMaxH3 Studioは、制作案件、ログ、中間成果物、費用、承認履歴を1か所で確認するためのローカルWebアプリです。チャットは企画と監督の窓口、Studioは実行状態と証跡を保持する制御盤として分離します。

このMVPはPowerDirectorのような汎用ノンリニア編集ソフトではありません。既存の`productions/`と`outputs/productions/`を読み込み、制作記録の閲覧、再実行計画、承認、監査exportを扱う土台です。Windows SAPIによるローカルナレーションworker、ElevenLabs Multilingual v2の文字時刻付き外部TTS worker、固定workflowによるローカルComfyUI MiniMax H3動画worker、登録済み動画をトリムして順序付きハードカットへ連結するFFmpeg timeline worker、音声・字幕合成worker、完成masterのローカルtechnical QC workerまでを実装済みです。画面収録、transition／overlayを含む詳細編集、MiniMax外部APIのStudio workerは後続段階です。

## MVPでできること

- 制作一覧と案件詳細をローカルブラウザで確認する。
- run、工程、イベント、費用、承認状態を分けて表示する。
- 動画、音声、画像、字幕、JSON、JSONL、一般テキストログなどの中間成果物を確認する。安全な構造化redactionを保証できない設定・markup形式はpathとmetadataだけを表示する。
- 動画、音声、画像のA/B比較と、対応するmedia同士の再生、停止、時刻合わせを行う。
- 変更対象から、再実行する工程と再利用候補を計画する。
- 新しいrunを既存runへ上書きせず作成する。
- existing台帳のtechnical、creative、public release statusを混同せず表示する。
- 有料工程を想定したrunの費用上限を承認または却下し、以前の判断を残す。
- manifest、記録、成果物hashを監査ZIPとしてexportする。
- SQLite索引を、ファイル上の制作台帳から更新する。
- provider secretをWindows DPAPIで暗号化して登録、状態確認、削除する。
- `local_sapi`の0円runを作り、1行1segmentの日本語ナレーションを明示実行する。
- voice、読み上げ速度、原文を保持した発音置換を指定する。
- 実WAV frameに基づく`narration.wav`、`captions.srt`、`timings.json`、`manifest.json`を生成する。
- `elevenlabs_tts`の課金runを作り、正の見積、費用承認、送信内容の最終確認をすべて満たした場合だけ、ElevenLabsへナレーションを明示送信する。
- [ElevenLabs `with-timestamps` API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/)を`eleven_multilingual_v2`と`mp3_44100_128`へ固定し、返された文字単位alignmentからsegment単位のSRTと時刻を生成する。
- providerの`request-id`、`character-cost`、`timing_source=elevenlabs_alignment`を記録する。API応答からUSD実費を確定できないため`actual_cost=null`のまま「未確定」と表示する。
- 外部TTSでも`narration.wav`、`captions.srt`、`timings.json`、`manifest.json`の4成果物へ統一し、その後のassemblyとQCをローカルで実行する。
- `local_comfyui`の0円runを作り、固定`minimax_h3_t2v_official_q4_v1` workflowへpromptとseedだけを渡して動画生成を明示実行する。
- 公式INT8 ConvRot diffusion、Q4 text encoder、video/audio VAE、20 steps、約480×864、124 frames／24fpsの固定graphから、`generated-video.mp4`、`workflow.json`、`ffprobe.json`、`manifest.json`を生成する。
- 長時間GPU生成をdefault jobから分離した1 worker FIFO laneで直列化し、prompt ID、prompt SHA-256、exact seed decimal、workflow/model/runtime/tool identity、成果物hashを追跡する。
- 同じproductionの登録済み動画を1〜32カット選び、順序変更、複製、開始／終了ミリ秒の指定からハードカットpreviewを明示実行する。
- timeline previewを1080×1920、24fps、H.264／yuv420p、video-only MP4へ固定し、`timeline-preview.mp4`、`timeline.json`、`ffprobe.json`、`manifest.json`を生成する。
- 同じproductionの登録済み動画と、同じRunの成功済みナレーションattemptを選び、source audioを置換した`master-clean.mp4`をローカル生成する。
- 任意で、SRTを制御タグ不能な固定style ASSへ変換し、`studio_default_v1`またはShorts向け大字幕`shorts_ja_large_v1`で`master-captioned.mp4`を追加生成する。
- `ffprobe.json`と自己hash付き`manifest.json`へ入力hash、FFmpeg/ffprobeの実体・version・binary hash、音声方針、出力方針を記録する。
- 同じRunの成功済みassembly attemptからcleanまたはcaptioned masterを選び、MP4 container、stream構成、H.264／yuv420p、AAC 48 kHz stereo、尺、full decode、全編無音をローカル検査する。
- QC解析結果を`technical-qc.json`、`ffprobe.json`、自己hash付き`manifest.json`として保存し、解析完了とtechnical verdictのpass／failを分けて表示する。
- stage attemptと実行jobの永続リンク、queued/running/succeeded/failed、所要時間、cache hit、provider、task ID、実費、timing source、成果物hashをUIと監査記録で追跡する。
- 同一入力の成功cacheをhash検証後に再利用し、改変・欠落時は再生成する。
- `test-video` CLIから、索引更新、0円Run作成、narration、1カットtimeline、assembly、technical QCを順番に実行し、完成MP4と監査識別子を1つのJSONで受け取る。

MVPが行わないこと:

- ElevenLabs以外の外部有料provider、MiniMax外部API、画面収録の実行
- 画面収録、transition／overlay／音量調整を含む汎用タイムライン編集
- `local_comfyui` Runからnarration、timeline、assembly、QCまでを自動で直結すること
- ブラウザから任意ローカルpathを読むこと
- creativeまたは公開権利を自動承認すること

「run作成」は監査可能な実行計画を保存する操作で、それだけではworkerや課金APIを開始しません。`local_sapi` runでは、作成後にナレーション、カット編集、編集・合成、品質検査の各画面または対応する専用APIで明示したときだけローカルworkerを開始します。`local_comfyui` runも、生成映像画面でpromptとseedを確認して実行した場合だけGPU workerを開始します。`elevenlabs_tts` runは、作成、正の費用見積、上限承認に加え、外部音声画面で送信内容を確認して`confirm_billable=true`を明示した場合だけ外部TTS workerを開始します。カット編集は同じproductionの登録済み動画artifactだけを受け付けます。合成は同じRunの成功済みナレーションを、QCは同じRunの成功済みassembly attemptを必須とします。timeline previewは通常の登録済み動画と同じ入力候補としてassemblyへ渡せます。
通常の課金対象requested stageを含むrunには正の見積額が必須です。0以下または未指定の見積はfail closedで拒否し、runを残しません。`local_sapi`はnarration、captions、timeline、assembly、qcだけを対象にする0円profileです。`elevenlabs_tts`はnarrationを必須とし、narration、captions、assembly、qcだけを対象にする課金profileです。`local_comfyui`はvideo_generationを必須とする0円profileです。動画変更から導出されるtimeline、assembly、qcは影響計画として記録しますが、このprofileの実行endpointにはまだ接続していません。生成後は同じproductionに`local_sapi`または`elevenlabs_tts` Runを作り、登録済み生成動画を後続入力として選びます。

外部ナレーションのHTTP境界は`POST /api/runs/{run_id}/execute-external-narration`です。bodyは次の形だけを受け付けます。endpoint、API key、timeout、出力path、FFmpeg optionは指定できません。

```json
{
  "provider": "elevenlabs",
  "voice_id": "<ElevenLabs voice ID>",
  "model_id": "eleven_multilingual_v2",
  "segments": [{"text": "ナレーション本文"}],
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true,
    "speed": 1.0
  },
  "seed": 0,
  "confirm_billable": true
}
```

ローカル動画生成のHTTP境界は`POST /api/runs/{run_id}/execute-local-video-generation`です。bodyは次の3 fieldだけを受け付けます。workflow graph、model path、ComfyUI endpoint、出力path、step数などは公開requestから変更できません。seedはJSON integerとして0〜9,223,372,036,854,775,807を受け付け、UIはrequestで引用符なしdecimalを送り、responseでは`seed_decimal`を優先してJavaScriptの整数丸めを避けます。

```json
{
  "workflow_preset": "minimax_h3_t2v_official_q4_v1",
  "prompt": "A calm cinematic portrait, subtle natural motion.",
  "seed": 42
}
```

prompt本文はproviderへ提出したexact graphを保全する`workflow.json`には含まれます。SQLite、job/run/eventの公開metadataには複製せず、`prompt_sha256`と`prompt_chars`だけを残します。`workflow.json`を含む監査exportや共有前には本文が含まれる前提で確認してください。

カット編集のHTTP境界は`POST /api/runs/{run_id}/execute-local-timeline`です。bodyは次の形だけを受け付け、pathやFFmpeg設定は受け付けません。

```json
{
  "clips": [
    {"video_artifact_id": "art_<32hex>", "start_ms": 0, "end_ms": 1500}
  ]
}
```

## セットアップと起動

前提:

- Windows PowerShellまたはPowerShell 7
- Python 3.10以降。既存の`.venv`があれば優先して使用
- Node.js 20.19以降の20系、または22.12以降とnpm。Node.js 21と22.0〜22.11はVite 8の対応範囲外

初回とfrontend更新後:

```powershell
.\setup-studio.ps1
```

通常起動:

```powershell
.\run-studio.ps1
```

`http://127.0.0.1:8765`だけで待ち受け、build済みの`studio/dist/`をPython backendが配信します。ポート変更とブラウザ自動起動の停止も可能です。

ローカル動画生成を使う場合は、別のPowerShellでStudio用ComfyUIを先に起動します。Studioはこのlauncherが作るmain/output/listen/port、Dynamic VRAM、全custom node無効化＋`ComfyUI-GGUF`だけのallowlistを含む完全なargvを`/system_stats`で照合します。旧引数、未知引数、Emergency mode、Turbo profileで起動中のComfyUIは生成前に拒否するため、いったん終了して次のprofileで再起動してください。

```powershell
.\run-local.ps1 -Profile official_q4 -NoBrowser
```

```powershell
.\run-studio.ps1 -Port 8876 -NoBrowser
```

frontend開発時:

```powershell
.\run-studio.ps1 -Dev
```

この場合はbackendを`127.0.0.1:8765`、Viteを`127.0.0.1:5173`で起動します。どちらもLANへ公開しません。`Ctrl+C`で終了します。

## API secretの登録

APIキーをチャットへ貼りません。PowerShellの非表示入力を使うCLIから登録します。現在登録できるprovider識別子は`minimax`、`elevenlabs`、`azure_speech`、`openai`です。

```powershell
python -m tools.studio.cli secret set minimax
python -m tools.studio.cli secret status minimax
python -m tools.studio.cli secret delete minimax
```

`python`がPATHにない場合は`py -3 -m tools.studio.cli ...`を使います。既存`.venv`を明示する場合は`.\.venv\Scripts\python.exe -m tools.studio.cli ...`でも同じです。

登録値は現在のWindowsユーザーに紐づくDPAPIで暗号化し、`outputs/studio/secrets/<provider>.dpapi`へ保存します。平文値は再表示せず、SQLite、ログ、監査ZIP、Gitへ含めません。provider workerで必要になった瞬間だけ、process環境変数、workspaceの`.env`、DPAPI storeの順に解決します。secret登録や状態確認だけでは外部APIを実行しません。費用承認済み`elevenlabs_tts` Runで外部ナレーションを明示実行した場合だけ、ナレーション本文と固定設定をElevenLabsへ送信します。

## 契約不要のテスト動画

Studio serverを停止した状態で、登録済み動画とWindows標準音声から字幕付きテストMP4を1コマンドで作成できます。同じworkspaceへの多重writerを防ぐため、serverが起動中ならworkspace lockで開始を拒否します。`--video-artifact-id`以外の入力pathや任意FFmpeg optionは受け付けません。

```powershell
.\.venv\Scripts\python.exe -m tools.studio.cli test-video `
  --production-id SHORT_20260823_claude_md_15s `
  --video-artifact-id art_3053005b9af82d88213e0726e21b631f `
  --segment 'Studioの自動動画制作テストです。' `
  --segment '音声と字幕を生成し、映像へ合成します。' `
  --segment '最後に技術検査まで実行します。' `
  --voice 'Microsoft Haruka Desktop' `
  --start-ms 0 --end-ms 15000 `
  --variant captioned --timeout-seconds 900
```

CLIは索引更新後、immutableな`local_sapi` Runを作り、`narration -> timeline -> assembly -> qc`をmain threadから順番にqueue／waitします。単一workerのcallback内で次工程を待たないため、queueの自己deadlockを作りません。途中で失敗、停止、timeoutが起きた場合は後続工程を開始せず、秘密情報や絶対pathを含まない固定errorをstderrへ返します。成功時のstdout JSONにはproduction／revision／run、各job／stage attempt、cache hit、source／timeline／masterの相対path・bytes・SHA-256、QC report artifactとtechnical verdictを含めます。exit codeは成功`0`、request／工程失敗`2`、technical QC fail`3`です。

この経路はWindows SAPI、FFmpeg、ffprobeだけを使うため、API契約、API key、課金承認は不要です。公開品質の声を比較するときだけ、ElevenLabsの契約とAPI key登録を行い、最短原稿1回の費用上限を承認してpaid smokeへ進みます。API keyはチャットへ貼りません。Remotionはこの経路へまだ導入していないため、その契約判断も現時点では不要です。

## 保存構造

```text
studio/                         React / Vite frontend source
tools/studio/                   Python backendと索引・監査処理
productions/<production-id>/    Git管理する既存の制作仕様と台帳
outputs/productions/<id>/       ignoredの画像・音声・動画・詳細QC
outputs/studio/
  studio.sqlite3                schema v3の再構築可能なSQLite検索索引とStudio記録
  events/<scope>/<id>.jsonl     hash chain付きevent mirror
  secrets/<provider>.dpapi      Windowsユーザーに紐づく暗号化secret
  external-submissions/elevenlabs/<production>/<cache>/.submission-unknown.json
                                課金POST前に作るproduction/cache単位の再送防止marker
  external-submissions/comfyui/<production>/<cache>/.submission-unknown.json
                                ComfyUI POST前に作りprompt IDを追記する再送防止marker
  runs/<run>/video_generation/<cache>/
                                generated-video.mp4 / workflow.json / ffprobe.json / manifest.json
  runs/<run>/narration/<cache>/ narration.wav / captions.srt / timings.json / manifest.json
  runs/<run>/timeline/<cache>/  timeline-preview.mp4 / timeline.json / ffprobe.json / manifest.json
  runs/<run>/assembly/<cache>/  master-clean.mp4 / master-captioned.mp4 / ffprobe.json / manifest.json
  runs/<run>/qc/<cache>/        technical-qc.json / ffprobe.json / manifest.json
  audits/<production>/<job>.zip 監査export
  audits/<production>/<job>.zip.sha256 監査ZIPの外部hash sidecar
```

`outputs/`はGit管理外です。大容量artifact、SQLite、secret、exportを誤ってcommitしません。既存制作の監査上の正本は`productions/`の台帳と、そこから参照される`outputs/productions/`のartifactです。Studioが作るrunと費用承認はimmutable row、eventはscope別hash chainとしてSQLiteへ追記し、JSONL mirrorと監査exportへ固定します。SQLiteだけを長期保全の唯一のcopyにせず、`events/`と必要な監査ZIPも保管してください。

## 記録モデル

```text
Production
  ├─ Artifact / Artifact version
  ├─ Event hash chain
  └─ Revision
       └─ Run
            ├─ Requested stages
            ├─ Cost approval history
            └─ Stage attempt
                 ├─ Background Job ID
                 └─ Provider/result metadata / Artifact set
```

- 既存revisionとrunは上書きしません。修正は新しいrunとして残します。
- artifactは相対path、byte数、media type、生成元を常時記録します。SHA-256は既存manifestから得られる場合、または小容量sidecarを索引時に実測できる場合に記録し、大容量mediaでは`null`の場合があります。監査ZIPへ実際に格納したentryは別途すべて実測hashを持ちます。
- イベントと判断は追記し、過去の採否を書き換えません。
- eventは`previous_hash`と`event_hash`を持ち、起動時と追記時にJSONL mirrorの全chainを検査します。破損時はhealthとUIをdegraded表示にし、該当mirrorを監査ZIPから除外します。これはローカル改変の検出であり、第三者に対する電子署名ではありません。
- hash chainの途中改変や不正な追記は検出しますが、正しいevent境界で末尾だけを削る操作は、外部固定済みtailがなければ単独では検出できません。重要時点の監査ZIPと`.zip.sha256`を別媒体にも保管してください。
- SQLiteはUI検索とMVP操作用です。既存のtracked台帳を置き換えません。
- Studio外で既存台帳が更新された場合は「索引を更新」で再読込します。
- SQLite再構築時、Studio生成artifactは完全metadataを持つ`artifact.created`または成功済みstage/job resultから候補を得て、`outputs/studio/`内の非symlink通常file、stable ID、bytes、SHA-256、既存ID/path衝突を再検証できたものだけ復元します。1件2 GiB、合計16 GiB、10,000件が上限です。旧イベントがIDとkindしか持たず完全metadataが他にもない場合、欠落・改変・symlink・path逸脱がある場合は推測で復元しません。

MVPは変更種別から`requested_stages`と再利用工程を計画します。ローカルnarrationのcache keyは正規化segment、voice、rate、発音置換、Windows SAPIに固定した実装versionから作り、成功attemptと4成果物のpath、bytes、SHA-256がすべて一致するときだけ再利用します。外部TTSはprovider、固定model/output、voice、全voice setting、seed、正規化segment、実装versionからcache keyを作り、同じproduction内の成功attempt chainを物理成果物のownerまで辿って4成果物とmanifest自己hashを再検証します。課金POST直前にはproduction/cache identityごとの永続markerを排他的に作り、成功成果物の確定後だけ削除します。通信結果が曖昧な失敗や中断でmarkerが残った場合は別Runを含む自動再送をfail closedで止めます。ローカルComfyUIはprompt hash、seed、固定workflow、4 model、2 runtime lock、3 repository revision、FFprobe identity、出力policyからcache keyを作ります。GPU lane内で同じproductionの成功attempt chainを物理ownerまで辿り、4成果物、manifest自己hash、fresh ffprobeを再検証します。新POST前markerへprompt IDを追記できた場合は同じRunの明示retryでhistory pollingを再開しますが、IDなしmarkerは曖昧状態として自動再送しません。provider task専用tableとStudio起動時の自動resumeは未実装です。ローカルtimelineは順序付きartifact ID、trim、入力bytes／SHA-256、固定出力policy、解決済みFFmpeg／ffprobeの実体versionとbinary SHA-256からcache keyを作り、同じproduction内の成功attempt chainと4成果物を再検証します。ローカルassemblyはsource動画、WAV、SRT、字幕preset、字幕有無、音声・出力方針、FFmpeg/ffprobeの実体versionとbinary SHA-256からcache keyを作り、manifest自己hash、登録済みartifact、実fileを再検証します。ローカルQCはassembly attempt、選択variant、masterのhash／bytes、期待尺、QC policy、FFmpeg/ffprobeの実体identityからcache keyを作ります。cache再利用時も対象mediaと成果物を再検証します。字幕だけを変更した場合は映像、timeline、ナレーションを再利用し、合成とQCだけを新runで実行できる土台です。

## ログ、成果物、監査

Studioでは次を別々に扱います。

| 種類 | 記録例 |
|---|---|
| event | 索引、revision/run、job、費用承認の時刻、状態、hash chain |
| artifact | path、bytes、MIME、origin、version、取得できた場合のSHA-256 |
| run cost | 見積、通貨、承認上限、承認／却下履歴 |
| stage attempt | stage、attempt番号、cache key、状態、所要時間、provider、task ID、実費、timing source |
| status / approval | 台帳由来のtechnical・creative・public status、run費用上限の承認／却下と理由 |

ローカルSAPI attemptは`provider=windows_sapi`、`provider_task_id=null`、`actual_cost=0`、`timing_source=wav_frames`として記録します。ローカルComfyUI attemptは`provider=comfyui`、`provider_task_id=<prompt-id>`、`actual_cost=0`、`timing_source=ffprobe`、prompt SHA-256、文字数、seed／`seed_decimal`として記録します。ElevenLabs attemptは`provider=elevenlabs`、`provider_task_id=<request-id>`、`character_cost=<header値またはnull>`、`actual_cost=null`、`timing_source=elevenlabs_alignment`として記録します。`character-cost`はproviderの課金文字量でありUSD実費ではありません。ローカルtimeline attemptは`provider=local_ffmpeg_timeline`、ローカルassembly attemptは`provider=local_ffmpeg`、ローカルQC attemptは`provider=local_ffmpeg_qc`として、いずれも`provider_task_id=null`、`actual_cost=0`、`timing_source=ffprobe`を記録します。QCは解析不能なtool/process failureだけをjob失敗とし、解析が完了して検査に不合格ならjob／attempt成功と`technical_verdict=fail`を併記します。API応答にないUSD実費を推測せず、将来のprovider請求照合で確定するまでは未確定のまま保持します。

監査exportは、SQLiteを1つのread transactionで固定した時点の記録をZIPへまとめる派生成果物です。event mirrorもそのsnapshotと一致する検証済みprefixをmemoryへ固定してから格納します。一般テキスト副生成物はZIP格納前に既知の秘密情報patternをredactし、変更対象をpackage manifestの`redacted_text_files`へ記録します。安全な構造化処理を保証できないYAML/YML、INI/CFG/CONF、TOML、CSV/TSV、XML、HTML/XHTML、SVGは`structured_text_requires_local_review`として除外します。未知形式と外部archiveも`unsupported_artifact_kind`として除外します。Studio生成のSRT、timings、manifestは既定で含め、WAVは他のaudio/video/imageと同様に`include_media=true`のときだけ含めます。監査ZIP自身は再帰的に含めません。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain末尾、検証できず除外したmirrorを記録し、ZIP閉鎖後に全entryを再検証します。ZIP全体のSHA-256は隣接sidecarへ保存します。DB snapshot後に元artifactが更新された場合、artifact metadataの時点とcopy時点は異なり得るため、ZIP内実体については`archive_entries`のbytes/hashを正本とします。監査ZIPが存在するだけで公開権利や人の通し試聴が確認済みになったとは扱いません。

## セキュリティ境界

- HTTPは`127.0.0.1`だけにbindします。
- 変更系POSTは起動ごとのsession tokenとloopback Originで保護し、tokenを永続ログへ保存しません。認証拒否時は上限内の宣言済みrequest bodyだけを破棄してから接続を閉じ、WindowsでもHTTP 403を安定して返します。長さ不正・上限超過bodyは読み込まずfail closedにします。読取GETはloopback bindとHost検査を境界とします。
- 同じworkspaceへ2つのStudio serverを起動しません。serverはworkspace単位のprocess-lifetime lockを保持し、2台目を起動時に拒否してevent mirrorの多重writerを防ぎます。
- frontendへAPIキーを返すendpointはありません。
- 外部TTSのprofile、narration工程、正の見積、費用承認、literal booleanの`confirm_billable=true`をすべて検証してから、外部contract module、秘密鍵、HTTP workerへ到達します。どれか1つでも欠ければprovider codeを読み込まずfail closedにします。
- ElevenLabsのproduction endpointは`https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps`へ固定し、redirectを拒否します。test用endpoint注入はliteral loopback originだけに限定します。API keyは`xi-api-key` header以外へ入れず、URL、cache key、manifest、例外、job payloadへ保存しません。
- provider応答、MP3、alignment、WAV、metadata、segment文字数、総文字数、総尺、timeoutへ上限を設けます。HTTP／processの生出力やprovider bodyを公開エラーへ含めません。
- 課金POST前に永続markerを作ります。providerが受理した可能性を否定できないtimeout、5xx、切断などは`external_submission_unknown`として停止し、同じproduction/cache identityを自動再送しません。これは曖昧状態で重複課金しないためのfail-closed境界です。
- ComfyUI endpointは`http://127.0.0.1:8188`へ内部固定し、公開requestから上書きできません。環境proxyを無効化し、redirect、過大応答、非loopback URLを拒否します。新POSTとmarker-linked resumeの直前に`/system_stats`を読み、`run-local.ps1 -Profile official_q4`（任意の`-NoBrowser`）が作るworkspace内main/output、listen/port、ComfyUI 0.31.0、PyTorch 2.13.0+cu130、Python 3.12、Dynamic VRAM、custom-node disable／exact GGUF allowlistを含む完全なargvを照合します。未知・重複・equals形式の引数、Emergency／Turbo／precision変更、model path redirectを拒否し、`runtime/ComfyUI/extra_model_paths.yaml`も存在またはsymlinkなら拒否します。
- ComfyUIのruntime lock 2 fileはLF byte列とSHA-256を固定し、ComfyUI、ComfyUI-GGUF、MiniMax H3 Turboの3 checkoutはexact HEADと非ignored fileを含むclean状態を要求します。Windowsでは新しいPOST attemptごとに4 modelをwrite/delete共有なしで開き、その同じhandleからfull SHA-256を計算してpublish後まで保持します。実行中の書換え・削除・置換と、既にwriterが開いているmodelを拒否します。非Windowsだけは物理file identity付きprocess cacheを使います。historyが返すMP4は送信graphへ注入した出力prefix配下の規定basenameだけを受け付け、workspace内の別MP4を生成結果として登録しません。
- `.env`拡張子、`.env.*`、credential/secret key file、DPAPI secretは索引対象外です。JSON/JSONLは構造化redactionし、一般テキストはAuthorization、Basic/Bearer、Cookie、API key、署名値など既知patternをbest-effortでredactします。
- artifact配信は登録済みかつ許可されたroot内のfileだけを対象にします。
- narration workerは文字列をPowerShell commandへ展開せず、run配下の専用一時directoryにUTF-8 JSONとして渡します。一時fileは同じWindowsユーザー／workspace ACLを信頼境界とし、処理後に削除します。SAPI preflightと合成PowerShellはどちらもjobのprocess registryへ登録し、preflightは100ms周期でcancelを確認します。tracked helperだけを起動し、戻り値はprovider、task ID、実費、cache key、exact artifact path/name/kind/MIME/bytes/SHA-256のallowlistで検証してから登録します。
- timeline requestは`clips`だけ、その各要素は`video_artifact_id`、integerの`start_ms`、`end_ms`だけを受け付けます。1〜32カット、各50ms以上、合計30分以内、各source 2 GiB以下、入力合計4 GiB以下に制限し、同じproductionの登録済み・available・video artifactだけをhash再検証します。任意path、transition、filter、codec、FFmpeg optionは受け付けません。
- timeline workerは入力を専用一時directoryの`clip-00.mp4`形式へ固定名copyして整合性を再検証し、`shell=False`、bounded stdout/stderr、cancel可能なFFmpeg／ffprobeだけを実行します。出力は1080×1920、24fps、H.264／yuv420p、video-only、ハードカットへ固定します。累積時間から各カットのframe予算を決め、その枚数だけを連結するframe-budget v2により、短いカットでも境界frameの重複と最後のカット欠落を防ぎます。4成果物をatomic publishし、cache hitでもexact artifact集合、manifest自己hash、実file hash、fresh ffprobeを再検証します。
- assembly workerは登録済みartifact IDからbackendが解決したworkspace内の通常fileだけを受け取り、`subprocess`を`shell=False`で起動します。SRTは厳密にparseし、ASCII brace/backslashを全角化した固定style ASSへ変換してoverride tagを無効化します。字幕styleは`studio_default_v1`または`shorts_ja_large_v1`の閉じたpresetだけを許し、raw ASS、font path、filter、任意styleを受け付けません。source audioはナレーションへ置換し、短い音声だけを無音paddingします。映像より250msを超えて長い音声は暗黙にtrimせず拒否します。
- assembly入力は2 GiBの動画、128 MiBのWAV、8 MiBのSRT、30分、最大16,384px／64メガpixelを上限とします。出力はH.264 / yuv420p / AAC / MP4へ固定し、source timingを再encode時に保持します。`master-clean.mp4`、任意の`master-captioned.mp4`、`ffprobe.json`、`manifest.json`を一時directoryからatomic publishします。
- QC request bodyは`assembly_attempt_id`と`variant`だけを許可します。指定attempt自身は選択中Runの成功済みassemblyに限定します。content-addressed assembly cacheの実fileが同じproduction内の先行Runにある場合は、その`cache_source_attempt_id` chainを循環なしで終端まで辿り、全attemptのcache key、入力hash、artifact ID/path/bytes/SHA-256が一致したときだけ意図的なcross-run再利用として許可します。backendが対象artifactと期待尺を導出し、workspace内通常file、symlink不使用、bytes／SHA-256一致を検証してから、固定argv・`shell=False`のFFmpeg/ffprobeへ渡します。
- QCはprobe成功、MP4、video 1本＋audio 1本、H.264／yuv420p、AAC 48 kHz stereo、container/video/audio各尺、期待尺、full decode、全編無音ではないことを独立checkとして記録します。短尺mediaでは無音検出windowを媒体尺に合わせて1msまで縮めます。codec不一致や壊れたmediaは解析完了の`technical_verdict=fail`であり、creative、rights、public release statusを自動変更しません。tool timeoutなど解析自体が完了しない場合だけattempt／jobを失敗にします。
- QC cacheは登録済みartifact、実file、manifest自己hashだけでなく、対象masterの再解析結果も再照合します。改変したreportを自己hashごと作り直してもpassへ偽装できません。
- attemptとbackground jobはjobをworker queueへ入れる前に同一ID関係を永続化し、`stage.attempt.job_linked` eventとしてmirrorへ残します。同じリンクの再適用はeventを重複させません。schema v1/v2の既存DBは起動時にschema v3へ移行し、event mirrorから再構築してもattempt側の履歴Job IDを復元します。jobs検索表そのものは再構築対象ではないため、DB再構築後の完了状態・成果物はattempt記録を正本として表示します。
- cache hit時も各stageのmanifest自己hash、期待される全成果物のhash、DBに記録済みbytes/hashを再検証します。QCでは対象masterのfresh解析も行います。欠落、symlink、path逸脱、改変、worker契約違反は再利用または成功扱いにしません。
- 異常出力によるメモリ圧迫を抑えるため、1 segmentのWAVは32 MiB、結合WAVは128 MiB、総尺は30分を上限としてfail closedにします。これは短尺制作向けの安全上限で、長尺音声配信を保証する値ではありません。
- worker-backed stageの成功時は、jobとリンク済みstage attemptおよび両success eventを同じSQLite transactionで確定します。ComfyUIでは4 artifact row、version、`artifact.created` eventも同じtransactionへ含め、terminal successより先に見せません。artifact登録、success commit、通常のworker error、job／attemptリンク不一致、原子的completion envelope欠落／不一致でもjob／attemptを同じfailure transactionで閉じます。停止との競合は「両方success」または「job=`interrupted`かつstage attempt=`failed(process_interrupted)`」のどちらかに限定し、片側だけ成功させません。Studio停止時はjobごとのcancel eventをprocess登録と同じlockで先に通知し、登録済みFFmpeg／ffprobe／PowerShell subprocessを子process treeごと停止します。DBがbusyでもprocess停止を先行・並行し、workerをbounded joinします。異常終了後の再起動時も同じ状態を補い、永続的な実行中表示や孤児processを残しません。
- browser内でinline表示するのはraster image、audio、videoだけです。対応済み`.json`、`.jsonl`、`.log`、`.md`、`.txt`、`.srt`、`.ass`、`.vtt`は`attachment`とCSP sandboxを付け、redact済み内容だけを返します。不正JSON/JSONL、その他の設定・source code・markup・未知形式・外部archiveはMVPではHTTP 415で拒否します。Studio自身が生成・検証した監査ZIPだけはdownloadできます。
- 監査ZIPへ含める対応済みdocument、log、subtitleは秘密情報をredactし、変更対象と格納後hashをmanifestへ記録します。redactionは秘密がないことの証明ではないため、外部共有前に人がpackage manifestと内容を確認してください。
- 外部TTSのaudit summaryはallowlistしたprovider/model/cache/request ID/character costと成果物metadataだけを保存し、本文、API key、Authorization、生provider responseは保存しません。後続adapterでもrequest/response、署名付きURL、Cookieは保存前にredactします。
- API契約後もキーをチャット、Git、SQLite、コマンドライン引数へ貼りません。
- 課金対象工程のrunには正の見積額を必須とし、ElevenLabsではprovider/model/送信本文/設定と上限承認を実行前に表示します。承認後にpayloadを変更しても同じ確認として扱わず、実行requestごとに明示確認を必須にします。

Studioは個人用loopbackツールです。LANからの攻撃面を作らないため、`0.0.0.0`やLANへ公開しないでください。

## チャットとの分担

1. ユーザーがチャットで制作や修正を依頼する。
2. CodexがStudioのローカルAPIまたはCLIを通して新しいrevision/runを作る。
3. Studioが索引・監査job、ローカルComfyUI動画生成、ローカル／ElevenLabs narration、timeline、assembly、QC attempt、成果物、費用計画、ログを保持する。後続workerも同じ台帳へ保持する。
4. ユーザーはStudioで候補や中間成果物を確認する。
5. Codexは完了、失敗、承認待ちなど節目だけを確認する。
6. `local_comfyui` Runではpromptとseedを確認して動画生成を明示実行する。生成後は同じproductionへ`local_sapi`または`elevenlabs_tts` Runを作り、0円のローカルSAPI、または正の見積と承認を持つElevenLabs narrationを明示実行する。複数素材を使う場合は登録済み動画からtimeline previewを明示実行し、そのpreviewと成功済みnarrationを選んでローカルassemblyを実行する。assembly成功後はcleanまたはcaptioned masterを選んでローカルtechnical QCを明示実行する。各工程でcache可否と成果物hashを記録する。未接続工程は修正影響と再利用候補だけを新runへ記録する。

現MVPは索引・監査jobに加えてローカルComfyUI動画生成、ローカル／ElevenLabs narration、timeline、assembly、technical QCもバックグラウンド実行します。dashboard全体のhealth/job一覧は15秒間隔、実行中の動画生成／narration／timeline／assembly／QC jobは2秒間隔で取得し、terminal状態を検出した時点でproduction detailを再読込します。GPU生成はdefault workerと分離した1本のFIFO laneで直列化します。チャットは節目だけを確認することで監視トークンを抑えられます。Studioへ記録済みの状態はチャットを閉じてもローカルに残ります。

ローカルナレーション画面は操作性のため1行2,000文字・合計50,000文字を先に警告します。backendの正本上限は1 segment 4,000文字・合計100,000文字・100 segmentです。外部TTSもbackendで同じsegment／総文字数上限を適用し、さらにvoice ID、全voice setting、seed、provider応答、媒体size／尺を検証します。UIを迂回したrequestにも必ず適用します。

2026-08-24時点では、ElevenLabs transportとFFmpeg境界をmockしたE2Eで、承認済みRun、job／attempt、4成果物、provider metadata、成功cache、ローカルassembly入力まで確認しています。実ElevenLabs APIへのpaid smokeは行っていません。最初の実送信は、ユーザーがAPI keyをローカル登録し、対象voiceと見積上限を確認したうえで、短い日本語原稿を1回だけ明示承認して行う検証項目です。

同日の`test-video`実制作E2Eでは、既存15秒clean masterからWindows SAPI 3 segment、1カットtimeline、captioned assembly、technical QCを86.315秒で完走しました。完成MP4は1080x1920／24fps／15.000秒、H.264／yuv420p + AAC 48kHz stereo、4,524,600 bytes、SHA-256 `3A4A4EDB170F2A1D826231772BD56D1F998B7B31A1DA03C6D8C6A898C1F4A92E`で、technical QC 10/10 passです。同じrecipeの2回目は11.893秒で、narration／timeline／assemblyをcache利用し、QCは新しいattemptとして再解析してpassしました。この結果はローカル技術経路の証拠であり、音声の自然さ、creative、人物・素材の権利、公開可否を自動承認するものではありません。

2026-08-25のローカルComfyUI受入では、Python自動テスト247件を実行し、246件合格＋non-Windows専用race test 1件をWindowsでskipしました。固定API graph、GPU workerでのcache key再束縛、完全なruntime argv、`extra_model_paths.yaml`拒否、Windowsのmodel handle保護、loopback-only transport、送信marker、production-wide cache、GPU lane、artifactとjob／attemptの原子的確定、seedの64-bit保持、Shorts字幕presetを確認しています。稼働中ComfyUIのread-only照合ではversion、path、repository状態は一致しましたが、安全引数導入前に起動された現在のlistenerは完全なcanonical argvを満たさず、`invalid_comfyui_runtime`として意図どおり拒否されました。この実装受入では新しいpromptをPOSTせず、実GPU生成と完成映像の目視確認はまだ行っていません。

## 次段階

実装済み: Windows SAPI adapter、ElevenLabs Multilingual v2 `with-timestamps` adapter、文字alignmentからのsegment字幕、費用承認＋payload確認gate、成功cache＋曖昧送信marker、provider request ID／character cost／未確定USD欄、発音置換、固定公式INT8＋Q4 ComfyUI graph、閉じたruntime argv／model／live process照合、Windows model handle保護、GPU FIFO lane、prompt ID付きmarkerからの同一Run明示resume、生成artifactの原子的登録、登録済み動画1〜32カットのtrim／並べ替え／ハードカットpreview、FFmpeg clean／captioned master、`shorts_ja_large_v1`字幕preset、codec／stream／duration／full-decode／全編無音のローカルtechnical QC、ffprobe／manifest、stage attempt/cache。

1. Remotionによるtransition、overlay、テロップ、音量、対話的previewを備えた詳細timeline編集
2. PlaywrightとWindows画面収録
3. ComfyUIとMiniMax APIの`provider_tasks`／schema v4、Studio起動時の自動照合・resume、prompt ID未確定markerの手動解決
4. ElevenLabs請求情報とのUSD実費照合と、必要に応じた別TTS provider adapter
5. 音量、黒画面、長時間静止、字幕safe areaなどtechnical QC policyの追加
6. frame/timecode精度の連動比較、指定cutだけの再実行、cut/timecode単位コメントとcreative／rights human review UI
7. 外部送信素材の秘密情報検査、監査bundle署名

実装済み範囲を超える工程はRun計画内の未実行項目として表示し、`running`や`complete`とは記録しません。
