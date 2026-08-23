# MiniMaxH3 Studio MVP

## 目的

MiniMaxH3 Studioは、制作案件、ログ、中間成果物、費用、承認履歴を1か所で確認するためのローカルWebアプリです。チャットは企画と監督の窓口、Studioは実行状態と証跡を保持する制御盤として分離します。

このMVPはPowerDirectorのような汎用ノンリニア編集ソフトではありません。既存の`productions/`と`outputs/productions/`を読み込み、制作記録の閲覧、再実行計画、承認、監査exportを扱う土台です。Windows SAPIによるローカルナレーションworker、FFmpegによる1本の映像への音声・字幕合成worker、完成masterのローカルtechnical QC workerまでを実装済みで、画面収録、複数cutのタイムライン編集、H3、外部有料APIの実行workerは後続段階です。

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
- 同じproductionの登録済み動画と、同じRunの成功済みナレーションattemptを選び、source audioを置換した`master-clean.mp4`をローカル生成する。
- 任意で、SRTを制御タグ不能な固定style ASSへ変換し、`master-captioned.mp4`を追加生成する。
- `ffprobe.json`と自己hash付き`manifest.json`へ入力hash、FFmpeg/ffprobeの実体・version・binary hash、音声方針、出力方針を記録する。
- 同じRunの成功済みassembly attemptからcleanまたはcaptioned masterを選び、MP4 container、stream構成、H.264／yuv420p、AAC 48 kHz stereo、尺、full decode、全編無音をローカル検査する。
- QC解析結果を`technical-qc.json`、`ffprobe.json`、自己hash付き`manifest.json`として保存し、解析完了とtechnical verdictのpass／failを分けて表示する。
- stage attemptと実行jobの永続リンク、queued/running/succeeded/failed、所要時間、cache hit、provider、task ID、実費、timing source、成果物hashをUIと監査記録で追跡する。
- 同一入力の成功cacheをhash検証後に再利用し、改変・欠落時は再生成する。

MVPが行わないこと:

- 外部有料処理または外部TTSの自動実行
- 画面収録、動画生成、複数cutのタイムライン編集
- ブラウザから任意ローカルpathを読むこと
- creativeまたは公開権利を自動承認すること

「run作成」は監査可能な実行計画を保存する操作で、それだけではworkerや課金APIを開始しません。`local_sapi` runでは、作成後にナレーション、編集・合成、品質検査の各画面または対応する専用APIで明示したときだけローカルworkerを開始します。合成は同じRunの成功済みナレーションを、QCは同じRunの成功済みassembly attemptを必須とします。
通常の課金対象requested stageを含むrunには正の見積額が必須です。0以下または未指定の見積はfail closedで拒否し、runを残しません。`local_sapi`はnarration、captions、assembly、qcだけを対象にする0円profileで、映像生成などへ転用できません。

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

登録値は現在のWindowsユーザーに紐づくDPAPIで暗号化し、`outputs/studio/secrets/<provider>.dpapi`へ保存します。平文値は再表示せず、SQLite、ログ、監査ZIP、Gitへ含めません。MVPでsecretを登録しても外部APIは実行されません。

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
  runs/<run>/narration/<cache>/ narration.wav / captions.srt / timings.json / manifest.json
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

MVPは変更種別から`requested_stages`と再利用工程を計画します。ローカルnarrationのcache keyは正規化segment、voice、rate、発音置換、Windows SAPIに固定した実装versionから作り、成功attemptと4成果物のpath、bytes、SHA-256がすべて一致するときだけ再利用します。ローカルassemblyはsource動画、WAV、SRT、字幕有無、音声・出力方針、FFmpeg/ffprobeの実体versionとbinary SHA-256からcache keyを作り、manifest自己hash、登録済みartifact、実fileを再検証します。ローカルQCはassembly attempt、選択variant、masterのhash／bytes、期待尺、QC policy、FFmpeg/ffprobeの実体identityからcache keyを作ります。cache再利用時もmasterを再解析し、登録済み3成果物と自己hash付きmanifestの整合を確認します。字幕だけを変更した場合は映像とナレーションを再利用し、合成とQCだけを新runで実行できる土台です。

## ログ、成果物、監査

Studioでは次を別々に扱います。

| 種類 | 記録例 |
|---|---|
| event | 索引、revision/run、job、費用承認の時刻、状態、hash chain |
| artifact | path、bytes、MIME、origin、version、取得できた場合のSHA-256 |
| run cost | 見積、通貨、承認上限、承認／却下履歴 |
| stage attempt | stage、attempt番号、cache key、状態、所要時間、provider、task ID、実費、timing source |
| status / approval | 台帳由来のtechnical・creative・public status、run費用上限の承認／却下と理由 |

ローカルSAPI attemptは`provider=windows_sapi`、`provider_task_id=null`、`actual_cost=0`、`timing_source=wav_frames`として記録します。ローカルassembly attemptは`provider=local_ffmpeg`、ローカルQC attemptは`provider=local_ffmpeg_qc`として、ともに`provider_task_id=null`、`actual_cost=0`、`timing_source=ffprobe`を記録します。QCは解析不能なtool/process failureだけをjob失敗とし、解析が完了して検査に不合格ならjob／attempt成功と`technical_verdict=fail`を併記します。外部providerのtask ID、redaction済みrequest/response、実費は各adapterを接続した段階で同じevent/artifactモデルへ追加し、存在しない外部実行ログを作ったようには表示しません。

監査exportは、SQLiteを1つのread transactionで固定した時点の記録をZIPへまとめる派生成果物です。event mirrorもそのsnapshotと一致する検証済みprefixをmemoryへ固定してから格納します。一般テキスト副生成物はZIP格納前に既知の秘密情報patternをredactし、変更対象をpackage manifestの`redacted_text_files`へ記録します。安全な構造化処理を保証できないYAML/YML、INI/CFG/CONF、TOML、CSV/TSV、XML、HTML/XHTML、SVGは`structured_text_requires_local_review`として除外します。未知形式と外部archiveも`unsupported_artifact_kind`として除外します。Studio生成のSRT、timings、manifestは既定で含め、WAVは他のaudio/video/imageと同様に`include_media=true`のときだけ含めます。監査ZIP自身は再帰的に含めません。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain末尾、検証できず除外したmirrorを記録し、ZIP閉鎖後に全entryを再検証します。ZIP全体のSHA-256は隣接sidecarへ保存します。DB snapshot後に元artifactが更新された場合、artifact metadataの時点とcopy時点は異なり得るため、ZIP内実体については`archive_entries`のbytes/hashを正本とします。監査ZIPが存在するだけで公開権利や人の通し試聴が確認済みになったとは扱いません。

## セキュリティ境界

- HTTPは`127.0.0.1`だけにbindします。
- 変更系POSTは起動ごとのsession tokenとloopback Originで保護し、tokenを永続ログへ保存しません。認証拒否時は上限内の宣言済みrequest bodyだけを破棄してから接続を閉じ、WindowsでもHTTP 403を安定して返します。長さ不正・上限超過bodyは読み込まずfail closedにします。読取GETはloopback bindとHost検査を境界とします。
- 同じworkspaceへ2つのStudio serverを起動しません。serverはworkspace単位のprocess-lifetime lockを保持し、2台目を起動時に拒否してevent mirrorの多重writerを防ぎます。
- frontendへAPIキーを返すendpointはありません。
- `.env`拡張子、`.env.*`、credential/secret key file、DPAPI secretは索引対象外です。JSON/JSONLは構造化redactionし、一般テキストはAuthorization、Basic/Bearer、Cookie、API key、署名値など既知patternをbest-effortでredactします。
- artifact配信は登録済みかつ許可されたroot内のfileだけを対象にします。
- narration workerは文字列をPowerShell commandへ展開せず、run配下の専用一時directoryにUTF-8 JSONとして渡します。一時fileは同じWindowsユーザー／workspace ACLを信頼境界とし、処理後に削除します。SAPI preflightと合成PowerShellはどちらもjobのprocess registryへ登録し、preflightは100ms周期でcancelを確認します。tracked helperだけを起動し、戻り値はprovider、task ID、実費、cache key、exact artifact path/name/kind/MIME/bytes/SHA-256のallowlistで検証してから登録します。
- assembly workerは登録済みartifact IDからbackendが解決したworkspace内の通常fileだけを受け取り、`subprocess`を`shell=False`で起動します。SRTは厳密にparseし、ASCII brace/backslashを全角化した固定style ASSへ変換してoverride tagを無効化します。source audioはナレーションへ置換し、短い音声だけを無音paddingします。映像より250msを超えて長い音声は暗黙にtrimせず拒否します。
- assembly入力は2 GiBの動画、128 MiBのWAV、8 MiBのSRT、30分、最大16,384px／64メガpixelを上限とします。出力はH.264 / yuv420p / AAC / MP4へ固定し、source timingを再encode時に保持します。`master-clean.mp4`、任意の`master-captioned.mp4`、`ffprobe.json`、`manifest.json`を一時directoryからatomic publishします。
- QC request bodyは`assembly_attempt_id`と`variant`だけを許可します。指定attempt自身は選択中Runの成功済みassemblyに限定します。content-addressed assembly cacheの実fileが同じproduction内の先行Runにある場合は、その`cache_source_attempt_id` chainを循環なしで終端まで辿り、全attemptのcache key、入力hash、artifact ID/path/bytes/SHA-256が一致したときだけ意図的なcross-run再利用として許可します。backendが対象artifactと期待尺を導出し、workspace内通常file、symlink不使用、bytes／SHA-256一致を検証してから、固定argv・`shell=False`のFFmpeg/ffprobeへ渡します。
- QCはprobe成功、MP4、video 1本＋audio 1本、H.264／yuv420p、AAC 48 kHz stereo、container/video/audio各尺、期待尺、full decode、全編無音ではないことを独立checkとして記録します。短尺mediaでは無音検出windowを媒体尺に合わせて1msまで縮めます。codec不一致や壊れたmediaは解析完了の`technical_verdict=fail`であり、creative、rights、public release statusを自動変更しません。tool timeoutなど解析自体が完了しない場合だけattempt／jobを失敗にします。
- QC cacheは登録済みartifact、実file、manifest自己hashだけでなく、対象masterの再解析結果も再照合します。改変したreportを自己hashごと作り直してもpassへ偽装できません。
- attemptとbackground jobはjobをworker queueへ入れる前に同一ID関係を永続化し、`stage.attempt.job_linked` eventとしてmirrorへ残します。同じリンクの再適用はeventを重複させません。schema v1/v2の既存DBは起動時にschema v3へ移行し、event mirrorから再構築してもattempt側の履歴Job IDを復元します。jobs検索表そのものは再構築対象ではないため、DB再構築後の完了状態・成果物はattempt記録を正本として表示します。
- cache hit時も各stageのmanifest自己hash、期待される全成果物のhash、DBに記録済みbytes/hashを再検証します。QCでは対象masterのfresh解析も行います。欠落、symlink、path逸脱、改変、worker契約違反は再利用または成功扱いにしません。
- 異常出力によるメモリ圧迫を抑えるため、1 segmentのWAVは32 MiB、結合WAVは128 MiB、総尺は30分を上限としてfail closedにします。これは短尺制作向けの安全上限で、長尺音声配信を保証する値ではありません。
- worker-backed stageの成功時は、jobとリンク済みstage attemptおよび両success eventを同じSQLite transactionで確定します。停止との競合は「両方success」または「job=`interrupted`かつstage attempt=`failed(process_interrupted)`」のどちらかに限定し、片側だけ成功させません。Studio停止時はjobごとのcancel eventをprocess登録と同じlockで先に通知し、登録済みFFmpeg／ffprobe／PowerShell subprocessを子process treeごと停止します。DBがbusyでもprocess停止を先行・並行し、workerをbounded joinします。異常終了後の再起動時も同じ状態を補い、永続的な実行中表示や孤児processを残しません。
- browser内でinline表示するのはraster image、audio、videoだけです。対応済み`.json`、`.jsonl`、`.log`、`.md`、`.txt`、`.srt`、`.ass`、`.vtt`は`attachment`とCSP sandboxを付け、redact済み内容だけを返します。不正JSON/JSONL、その他の設定・source code・markup・未知形式・外部archiveはMVPではHTTP 415で拒否します。Studio自身が生成・検証した監査ZIPだけはdownloadできます。
- 監査ZIPへ含める対応済みdocument、log、subtitleは秘密情報をredactし、変更対象と格納後hashをmanifestへ記録します。redactionは秘密がないことの証明ではないため、外部共有前に人がpackage manifestと内容を確認してください。
- request/response、Authorization、署名付きURL、Cookieは将来のprovider adapterで保存前にredactします。
- API契約後もキーをチャット、Git、SQLite、コマンドライン引数へ貼りません。
- 現在も課金対象工程のrunには正の見積額を必須とします。課金worker導入後は、対象素材、provider/model、最大額も先に固定し、明示承認なしではfail closedにします。

Studioは個人用loopbackツールです。LANからの攻撃面を作らないため、`0.0.0.0`やLANへ公開しないでください。

## チャットとの分担

1. ユーザーがチャットで制作や修正を依頼する。
2. CodexがStudioのローカルAPIまたはCLIを通して新しいrevision/runを作る。
3. Studioが索引・監査job、ローカルnarration attempt、成果物、費用計画、ログを保持する。後続workerも同じ台帳へ保持する。
4. ユーザーはStudioで候補や中間成果物を確認する。
5. Codexは完了、失敗、承認待ちなど節目だけを確認する。
6. ローカルnarrationを明示実行し、成功後に登録済み動画を選んでローカルassemblyを明示実行する。assembly成功後はcleanまたはcaptioned masterを選んでローカルtechnical QCを明示実行する。各工程でcache可否と成果物hashを記録する。未接続工程は修正影響と再利用候補だけを新runへ記録する。

現MVPは索引・監査jobに加えてローカルnarration、assembly、technical QCもバックグラウンド実行します。dashboard全体のhealth/job一覧は15秒間隔、実行中のnarration／assembly／QC jobは2秒間隔で取得し、terminal状態を検出した時点でproduction detailを再読込します。チャットは節目だけを確認することで監視トークンを抑えられます。Studioへ記録済みの状態はチャットを閉じてもローカルに残ります。

ナレーション画面は操作性のため1行2,000文字・合計50,000文字を先に警告します。backendの正本上限は1 segment 4,000文字・合計100,000文字・100 segmentで、UIを迂回したrequestにも必ず適用します。

## 次段階

実装済み: Windows SAPI adapter、segment字幕timing、発音置換、FFmpeg clean／captioned master、codec／stream／duration／full-decode／全編無音のローカルtechnical QC、ffprobe／manifest、stage attempt/cache、provider/task/実費欄の記録。

1. 外部有料TTS provider adapter、単語単位alignment、provider別の実費・task記録と課金承認gate
2. Remotionによる複数cutのpreview／timeline編集
3. PlaywrightとWindows画面収録
4. ComfyUIとMiniMax APIのtask永続化、再開、二重課金防止
5. 音量、黒画面、長時間静止、字幕safe areaなどtechnical QC policyの追加
6. frame/timecode精度の連動比較、指定cutだけの再実行、cut/timecode単位コメントとcreative／rights human review UI
7. provider adapter接続時のrequest保存前redaction、外部送信素材の秘密情報検査、監査bundle署名

実装済み範囲を超える工程はRun計画内の未実行項目として表示し、`running`や`complete`とは記録しません。
