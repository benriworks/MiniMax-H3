> [!NOTE]
> **このチェックアウトのWindows向けローカル補助資料:**
> [セットアップ](LOCAL_SETUP_JA.md)、[制作プレイブック](PRODUCTION_PLAYBOOK_JA.md)、
> [案件台帳](productions/README.md)、[アーキテクチャ](ARCHITECTURE.md)、
> [Mermaid図](ARCHITECTURE_DIAGRAM.md)、[Studio MVP](STUDIO_MVP_JA.md)を参照してください。

## ローカル制作Studio MVP

制作案件、Run計画、Studioイベント、中間成果物、費用見積、費用承認履歴を確認するloopback専用Webアプリを同梱しています。初回はfrontendをbuildし、その後1コマンドで起動します。

```powershell
.\setup-studio.ps1
.\run-studio.ps1
```

通常は`http://127.0.0.1:8765`を開きます。現在のMVPは既存制作台帳の閲覧、再実行計画、Run記録、有料工程の費用上限承認、監査exportに加え、Windows SAPIによる無課金のローカルナレーション生成、固定ComfyUIによるローカル動画生成、isolated Chromiumによるloopback Web画面収録、明示同意付きのWindowsプライマリ画面＋既定再生system audio収録、FFmpegによるハードカット、Remotionによる詳細timeline preview、clean／字幕焼き込みmasterのローカル合成、完成masterのローカルtechnical QC、検証済みローカル納品ZIPを扱えます。字幕、segment timing、発音置換、工程cache、codec／stream／duration／full-decode／全編無音の検査、Integrated loudness／true peak／黒画面のhard check、長い静止区間のwarning、ffprobe・manifestも記録します。QC policyはschema v2 / `local-ffmpeg-qc-v2` / `technical-qc-mp4-v2`で固定し、Integrated loudness -24.0〜-10.0 LUFS、true peak -1.0 dBFS以下、0.5秒以上の黒画面をtechnical verdictへ反映します。1.0秒以上の長い静止区間はwarningのみで、verdictには影響しません。ElevenLabs外部TTSは別の承認済みprofileで扱い、高品質scene alignmentは0円backend Jobまで実装済みです。YouTubeはprivate／unlisted限定backend control-planeまでで、Studio公開UIと実upload受入は未実施です。MiniMax外部APIのStudio workerは未接続です。Web収録は`127.0.0.1`の明示portだけを対象とします。Windowsネイティブ収録はプライマリ画面全体と既定render/console loopbackだけが対象で、外部サイトの制御、既存ログインsessionの注入、window指定、device指定、マイクは対象外です。詳細とセキュリティ境界は[STUDIO_MVP_JA.md](STUDIO_MVP_JA.md)を参照してください。

### M1〜M4: かんたん制作、ライブラリ、レビュー、3カットI2VA

- 上部の`かんたん制作`は、制作名、`告知／イベント案内／採用・募集`、動画1〜3本、主文、最終確認という約5判断で、制作作成からローカル音声・大字幕・technical QCのJob登録まで進めます。既存APIへ収束し、同じ保留IDで応答消失から再開します。一般素材は各scene既定trimが最大5.167秒のため、現時点では5.2秒以上を推奨します。
- 制作ライブラリは大文字小文字を区別しない検索、表示名変更、archive/unarchive、取込素材付き複製を提供します。archiveは一覧から隠すだけで、artifactを削除しません。tracked制作と制御metadataを持たない制作はread-onlyです。
- `レビュー`タブはartifact／revision／Run／cut／timecodeを固定した指摘、creative／rights／public release判定、解決履歴をappend-only eventへ保存します。`このcutの修正planを作成`は監査用計画までで、現時点では`render未実行`／M4 adapter未接続です。
- `shot-project` CLIは、Codexの画像生成スキル等で作成済みの始点画像3枚を公式MiniMax H3 V2 APIのI2VAで各6秒／768Pにし、既存Quick Createへ渡します。3件の有料task上限をrequest内で明示し、task ID、入力／出力hash、`plan.json`、`state.json`をcut別に残します。応答が失われた送信は自動再送しません。3本を5,167ms／5,167ms／5,166msへtrimし、250ms fade 2箇所を差し引いた15.000秒を組み立てます。local ComfyUI presetはT2VA-onlyなので、このI2VA CLIは公式API契約が必要です。

credentialはコマンドラインやrequest JSONへ書かず、対話入力でDPAPI保存します。

```powershell
E:\anaconda3\python.exe -m tools.studio.cli --workspace . secret set minimax
E:\anaconda3\python.exe -m tools.studio.cli --workspace . shot-project .\path\to\shot-project.json
```

request JSONと3枚の画像は同じprivate directoryに置き、画像pathはそのJSONからのrelative pathにします。各`video_prompt`は同梱`h3-prompt-writing` skillのI2VA形式、`duration_seconds=6`、`resolution="768P"`、`confirmed_billable_task_limit=3`に固定します。課金なしの自動試験では、3件送信、成功後の再実行0件、曖昧応答後の再送0件を確認しています。実API paid smokeはまだ実施していません。

### M5〜M6: 納品、収録受入、安全公開control-plane

M5のDelivery Packageは、成功済み`詳細一括`のRun／top Jobとclean master、captioned master、SRT、technical QC／ffprobe／manifestのexact lineageとhash、technical verdict `pass`を再検証します。`納品・公開`タブの`納品ZIPを作成`を押すと、上記6点、clean masterの25／50／75%から作るサムネイル3枚、title／description、production snapshot、event JSONL、自己検証manifestを決定的ZIPへまとめ、隣にSHA-256 sidecarを保存します。このJobはローカルだけで`network_used=false`／`billable=false`です。現在のタブはZIP作成とdownloadまでで、YouTube uploadを開始しません。creative／rights／public_release判定は表示しますが、確認用Deliveryの作成自体は未承認でも可能です。

高品質TTSのscene alignmentは`POST /api/runs/{run_id}/execute-voice-upgrade`まで実装されています。`elevenlabs_tts` Runの成功済みnarration attemptと登録済みWAV／timingsをbytes／mtime／SHA-256まで照合し、HOOK→MESSAGE→CTAのexact scene開始へ発話を配置してWAV／SRT／timings／manifestを新しい`voice_upgrade` Job／stage attemptとしてatomic登録します。次sceneまたは出力末尾へ発話が重なる場合は停止します。新attemptをassemblyへ指定した場合も、公開結果、source lineage、4登録artifactを厳密再検証してからWAV／SRTを入力にします。この処理はproviderを呼ばずcredentialを読まず、公開結果は`provider=local_voice_upgrade`／`actual_cost=0`です。専用execution／service／HTTP／assembly入力testと公開Job error codeは実装済みですが、Studio UIと告知／Deliveryへの自動接続はありません。

M6の`POST /api/runs/{run_id}/windows-capture-acceptance`は、成功済みnative captureの8成果物を再hashし、requestで受け取った自動測定値と人手確認を一つの監査eventへ束縛します。visible／audible marker差、loudness／peak、device切替、強制終了cleanup、5 attestの申告値は評価・保存しますが、requestのtool digestやattestだけでは独立した受入証拠になりません。登録済みcalibration Jobと、bytes／SHA-256／tool lineageをserviceが再検証できる証拠artifactが実装されるまでは、申告値が全条件を満たしても`content_sync_verified=false`、`public_release_ready=false`、`live_validation_required=true`でfail closedします。2026-08-30の実機smokeも合格証拠ではなく、実機受入は未完了です。このeventは元capture resultやreview gateを書き換えず、現YouTube bindingも自動参照しません。

過去のroadmapでM7としていたYouTube連携は、現M6の安全公開control-planeへ統合しました。previewで検証済みDelivery、clean／captioned masterの一方、metadata、OAuthで確認したchannel、creative／rights／public_releaseの3 human gateをdigestへ束縛し、executeでは同じ内容にCommunity Guidelines certificationと明示upload確認の2つのliteral `true`を追加要求します。3 gateはいずれも`approved`、未解決0件、review 1件以上が必要です。privacyは`private`／`unlisted`だけで、`public`は拒否します。OAuth credentialとresumable session URIはWindows user-scoped DPAPIで保護し、公開ledgerへtoken／signed URLを出しません。credential-bearing redirectは拒否し、Job失敗はallowlist済みcodeと有界な公開messageへ閉じます。providerが認識したbyte位置から再開できますが、session開始応答が曖昧、保護session欠損、期限切れの場合に別sessionを自動初期化しません。interactive OAuth bootstrapは未実装で、事前取得済みrefresh tokenが必要です。

実装済みなのはbackend contract、Delivery／human gate binding、durable resumable ledger、fake transport回帰です。StudioのYouTube公開UI、実Google OAuth credentialでのchannel preview、実upload、YouTube側read-backは未実施であり、公開済み／課金済みとは記録しません。一次資料はGoogle公式の[`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)、[resumable upload](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)、[OAuth 2.0 for Desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)です。

### 新しい制作、動画素材の取込、Job停止

上部の`新しい制作`から、タイトルと任意の動画素材を指定して制作を開始できます。ブラウザは`production_`に32桁の小文字hexを続けたIDを最初の送信前に固定し、作成応答が不明でもversioned `localStorage`に同じIDとタイトルを保持します。再照合ではIDとタイトルの両方が一致する制作だけを採用し、保留情報を明示破棄しない限り別IDを自動発行しません。告知動画に未保存の変更がある場合は、そのdraftが現在のproductionに紐付いているときだけ破棄確認を求めます。まだproductionを1件も選択していない初回作成で、存在しないdraftの破棄確認は表示しません。

動画は`mp4`、`m4v`、`mov`、`mkv`、`webm`、`avi`を一度に最大16件、1件あたり0より大きく2 GiB以下で選べます。UIは1件ずつ送信し、失敗した項目だけを再試行できます。backendはraw request bodyをproduction内の非公開partialへstreamし、SHA-256とffprobeのvideo stream／container検査を通した後だけ`outputs/productions/<id>/imports/`へatomic publishします。同じbytesはファイル名や対応拡張子が違っても既存artifactへ収束します。`.studio-production.json`はタイトルと取込済み相対path／SHA-256だけを保持する制御ファイルで、artifactとして公開しません。Studio再起動時は閉じた命名規則の残留partialだけを清掃し、Indexerはこの制御情報からtitleと既知hashを復元します。

実行中Jobには`停止`操作が表示されます。`POST /api/jobs/{job_id}/cancel`は`{"schema_version":1}`だけを受け、process、provider、force、timeoutをクライアントに選ばせません。responseは最新Job、`cancel_requested`、`worker_retired`を分けて返すため、停止要求の受付とworker終了確認を同一視しません。`worker_retired=false`なら、UIは同じexact Jobの停止endpointを2秒間隔・最大15回だけ再照合し、その間は二重操作を防ぎます。terminal Jobへの再送は新しい処理を起こさない冪等な照合です。同じRunの`local_pipeline`または`detailed_test_video`のtop-level Jobが稼働中／停止照合中なら、全体停止はその親だけを表示し、親のない孤立childだけは引き続き個別停止できます。

ブラウザ側も成功statusだけでは確定せず、制作作成は`201`＋exact production ID／title、動画取込は`201`＋exact production／output artifact／SHA-256、Job停止は`202`＋exact Job ID／停止状態を照合します。別identityや不完全な成功responseは表示へ採用せずfail closedにします。

`local_playwright`で実行できる工程は`screen_capture`と`timeline`です。`assembly`と`qc`は影響工程としてRun計画に残りますが、このprofileでは実行しません。画面収録とtimelineのジョブ状態・進捗率はUIが2秒pollingで再取得します。

`setup-studio.ps1`はWindows上で外部NuGet依存のない`native/windows-capture-helper`もRelease buildします。認証済み`POST /api/capabilities/windows-capture/inspect`は空objectだけを受け、固定helperのCore Audio doctor、物理プライマリ解像度、FFmpeg `gdigrab`／ffprobeを有界検査します。この診断自体は画面・音声dataの取得、保存、送信、Job／Run／artifact／event作成を行わず、ready時も`actual_capture_performed=false`です。実収録は`local_windows_capture` Runで、画面とsystem audioを別々に確認して60秒有効の単回consent intentを発行した後、同じ固定条件とtokenを`POST /api/runs/{run_id}/execute-windows-capture`へ送ります。tokenはsession／Run／条件に拘束しraw値を永続化しません。同tokenの再送は完了後も元Jobを返し、新しい録画には新しい同意が必要です。収録は1〜30秒、プライマリ画面、既定render loopback、cursor非表示へ固定し、path、window、device ID、マイク、任意FFmpeg引数は入力できません。helperとFFmpegは録画開始前にkill-on-close Windows Job Objectへ割り当て、秘密を含まないallowlist環境だけを渡します。専用capture laneは同時1件だけを許可し、raw masterは決定的partialとして起動前にも清掃します。cleanup失敗はRun配下marker、pathを含まないfsync済みfallback ledger、DBのexact cleanup-error lineageへ記録し、JobManager作成前にexact targetだけを再清掃します。ledger／DB／削除の失敗は起動をfail closedにし、一般failed Jobや別成果物へ対象を広げません。成功時はcombined MP4、video-only MP4、loopback WAV、始点／終点PNG、sanitized report、ffprobe、manifestの8成果物を原子的に登録します。masterと最終MP4のvideo/audio `start_time`／duration、frame／sample境界はfresh ffprobeで構造検証しますが、映像内容と音声内容を同一時計で直接観測してはいません。report／manifest／Job resultは`structural_timing_verified=true`と`content_sync_verified=false`／`live_validation_required=true`を分離し、UIも実機A/V同期確認まで公開利用を保留表示します。自動テストでは実録routeを呼んでおらず、A/V実内容同期・音質・収録中の既定device切替は明示承認付き実機smokeの残課題です。

2026-08-30に実装v4の明示承認付き実機smokeを実施し、6秒のプライマリ画面＋既定loopback収録、8成果物登録、full decode、fresh ffprobe、exact PCM、構造timing検証まで成功しました。既知の白flash／tone markerでは音marker開始が映像marker開始より約27〜111ms遅れ、現在のendpointでは音量も低めでした。したがって公開gateは維持し、既定device切替、親process強制終了、automation pointer overlayを使わないcursor非表示確認は未完了です。

再起動cleanupのDB候補は、削除前に全件preflightします。job／attempt／Run lineage、status／error、payload、成果物登録のいずれかが曖昧なら、先行候補も含め何も削除せずStudio起動を止めます。`available=false`の登録と同一targetの重複も停止条件です。

### Remotion詳細timeline

カット編集画面では、既存の`高速ハードカット`と`Remotion詳細preview`を切り替えられます。後者はschema v1の`POST /api/runs/{run_id}/execute-remotion-timeline`を使い、同じproductionの登録済み動画1〜16件／最大60秒へtrim、素材音量0〜100%、50〜2,000msのfade、固定`shorts_ja_large_v1`テロップと、カットごとの閉じた映像補正presetを設定します。互換既定`preserve_v1`は素材をそのまま使います。`h3_low_res_sharp_v1`は幅1080未満・高さ1920未満、両辺64px以上、幅÷高さ0.50〜0.625、cover拡大後300万画素以下の低解像度縦長素材だけを使用frameへ先にtrimし、固定Lanczos coverで1080×1920へ拡大・cropしてから、輝度だけに5×5／0.25の弱いunsharpをテロップ合成前に適用します。条件外はFFmpeg起動前に拒否します。色差は鮮明化せず、任意filter／強度／CRFは入力できません。visual presetがない既存の詳細一括・告知recipeは`preserve_v1`へ正規化して読み続けられます。

UIの`@remotion/player`とrendererは同じcompositionを使いますが、Playerは原素材を表示し、FFmpegの鮮明化前処理までは再現しません。効果は完成artifactで確認します。出力policy `remotion-source-fidelity-v2`はRemotion中間frameをPNG、動画encodeをCRF 16へ固定します。presetと固定`lanczos-cover-luma-unsharp-v1`方針はcache key、監査summary、render report、manifestへ、各clipの前処理計画・結果はrender reportとmanifestへ記録します。これは失われたディテールを生成する超解像ではなく、追加のCPU時間、一時I/O、encode時間を使う処理です。1080×1920／24fpsのMP4、recipe、render report、ffprobe、manifestの5成果物を保存します。画面収録と同じbrowser FIFO laneでconcurrency 1のため、両jobは直列です。

素材音量はまず詳細previewへ反映されます。そのpreviewをassemblyへ渡す場合は、既定の`narration_only_v1`で素材音をナレーションへ置換するか、`source_under_narration_v1`でpreview音声をさらに25%へ下げ、ナレーション100%と固定limiterで混ぜるかを選べます。mixは素材音声1 streamと素材／ナレーション双方の非無音を必須とし、不足時はfail closedです。任意gain、BGM、duckingはまだ扱いません。Remotion packageは`4.0.517`へexact pinし、setup済みPlaywright Chromiumを再利用します。利用は個人用途を前提としているため、主体・用途・配布形態が変わる場合は[第三者ライセンス](THIRD_PARTY_NOTICES.md)と現行Remotion licenseを再確認してください。

SetupはRemotion 5 packageとPlaywrightの実`node_modules` dependency closureをattestし、worker開始時とrender後に再照合します。path非公開のclosure digestはcache tool identityへ入るため、dependencyが変わった場合は成果物publish前にfail closedし、setupの再実行を求めます。

PNG中間frameは長尺ほど一時diskを消費します。開始前は「全frameのRGBA bytes×1.25＋raw出力2GiB＋正規化出力2GiB＋安全余白1GiB」に、`preserve_v1`の実source bytesまたはsharpカットごとの最大2GiBを足して検査します。source staging後に実staged bytesを記録し、残容量をframe／出力／余白分でもう一度検査します。不足時は`insufficient_scratch_space`でNode起動前に停止します。Remotion／Chromiumの`TEMP`／`TMP`／`TMPDIR`はatomic stage内へ閉じ、成功・失敗・cancelの全終了経路で削除します。Windowsの一時lockにはbounded retryを行い、残留時は`remotion_stage_cleanup_failed`として失敗を公開します。両検査値はrender report／manifestに残ります。

### `かんたん作成`（HOOK・MESSAGE・CTAテンプレート）

Studioの既定`かんたん作成`タブは、同じproductionへ登録済みの動画から縦型15秒を基準に動画を作る初心者向け入口です。`保存した内容から続ける`または`新しく作る`を選び、`動画の管理名`、`3つの場面を選ぶ`、`伝える言葉を入れる`、`内容を確認して作成する`の順に入力し、`この内容で動画を作る（<実尺>）`で保存から実行まで進めます。各場面の`読み上げる文章`は常に見えるため、大見出しと一緒に確認・調整できます。既定値は縦1080×1920、3場面、250ms fade、素材音なし、Windowsローカル音声、Shorts向け大字幕、captioned QC、ローカルのみ・API費用0円です。十分な素材尺があれば完成尺は15.000秒になり、短い素材を選んだ場合はcompile後の実尺を画面に表示します。

`かんたん作成`と`詳細設定`は同じ告知draftと実行controllerを表示方法だけ変えて共有します。Quick Create componentはAPIを直接呼ばず、既存の告知recipe保存→executeを使うため、0円`local_sapi`のRun／Job、4 child、artifact、technical QC、event／監査exportは詳細設定からの実行と同一です。新しいendpoint、worker、lane、DB schemaはありません。保存済みrecipeのtrim、素材音、映像補正、音声、字幕がかんたん作成の固定値と異なる場合は、自動的に`詳細設定`を表示して隠れた値を上書きしません。

構成はHOOK→MESSAGE→CTAの3シーン固定で、詳細設定では各シーンの素材、trim、素材音量、映像補正preset、1〜2行の大見出し、必須の1行ナレーションを指定できます。新規recipeの既定trimは5,167ms／5,167ms／5,166msで、最初の2境界の250ms fade overlapを差し引くと完成尺は15.000秒です。見出し位置はHOOK中央／MESSAGE上／CTA中央へ固定され、既存のDetailed Test Video v1へcompileしてWindows SAPI→Remotion→assembly→technical QCを実行します。告知実行では、各trimとfadeをRemotionと同じ24fpsで個別にframe丸めして求めた出力scene開始へ、各ナレーションとSRTを揃えます。前sceneの発話が次sceneへはみ出す場合は重ねずに停止します。ブラウザpreviewは素材と見出しだけの消音確認で、ナレーション、焼き込み字幕、最終音声mixは完成masterで確認します。

recipeは保存のたびにimmutableなversionをproduction eventへ追加し、`expected_revision`によるCASで古い画面からの上書きを拒否します。保存済み版は元を変更せず複製でき、かんたん作成の`この内容で動画を作る（<実尺>）`と詳細設定の`保存して告知動画を作る`は、どちらも必要なら先に保存してから、そのexact revisionを実行します。実行時のDetailed top Job作成／再利用とrecipe execution linkは同じSQLite transactionで確定します。名前だけを変えたコピーのようにcompile後の内容が同じ場合はDetailed側で同じrequest keyとなり、再利用可能なtopがあれば同じRun／Jobを使いつつ、各recipe versionからの実行リンクは別々に残します。

実行中はJob一覧を2秒間隔、重いproduction detailを初回とおおむね6秒間隔で再取得します。告知用の保存・複製・実行・Job／production照合requestは15秒でabortするため、serverが応答しない場合もフォームを永久にロックしません。保存の応答が不明なら同じrecipe ID・`expected_revision`・内容を1回だけ再送します。複製ではsource production／recipe／version／revisionとコピー名から128-bit clone IDを決定的に導出し、そのintent専用のversioned `localStorage` keyへPOST前に同期保存します。パネルのunmount、production切替、ページ再読込を挟んでも同じIDを再利用し、複数tabが同時操作しても同じbackend recipe IDへ収束します。成功応答またはimmutable版履歴のexact clone lineageを確認したときだけ保留を消し、timeout、network error、再送後の4xxでは消しません。壊れた／利用不能な保存領域は新ID発行へ読み替えずfail closedにし、明示破棄はブラウザ側の保留だけを消してserver上のrecipeを削除しません。保存内容はschema version、各ID、revision、コピー名、作成時刻だけで、media、台本、API keyは含みません。backendのlost-response dedupeと組み合わせ、別revision／別cloneを増やしません。実行応答が曖昧な場合、送信前には存在しなかったexecution linkだけを受理証拠とし、exact Job IDを`GET /api/jobs/{job_id}`で厳密に照合します。新しいlinkがなければ、同じimmutable recipe ID／revisionを1回だけ自動再送します。backendは同一content claimを使い、成功済みJobの全child lineageと全成果物のbytes／SHA-256を再検証してから再利用するため、正常なレンダーを重複作成しません。2回目のPOSTまたはfresh linkのexact Job照合がtimeoutなどで不明なら自動処理を止め、`同一revisionを再照合`を明示したときだけ同じPOSTを1回行います。既知の古い成功履歴だけで曖昧状態を解除しません。production切替時は旧detail requestをabortし、最新request generationと選択中production IDが一致した応答だけを表示します。

ここで「自動処理を止める」とは、追加POSTと同じ候補へのexact Job GETを止めることです。2秒のJob／おおむね6秒のproduction detail照合は継続し、後からfreshなexact linkを確認できれば再POSTせず復旧します。また、複製intent用`localStorage`が壊れているか利用できない場合は、安全なIDを保持できないため告知フォーム全体を明示破棄または環境復旧までロックします。

完全なcanonical recipeは再調整と監査のため`announcement.recipe.saved` eventへBase64で保存され、hash-chain JSONL mirrorと監査exportに含まれ得ます。Base64は暗号化ではなく平文相当です。API key、token、password、公開不要の個人情報はrecipe名、見出し、ナレーション、発音置換へ書かないでください。v1はBGM、ロゴ画像、任意renderer／CSS／React component、新規H3生成を扱いません。

#### Codex／CLIからのQuick Create一括実行

画面を開かずに既存の告知recipe契約を使う場合は、versioned JSONを1ファイル用意して次を実行します。

```powershell
.\.venv\Scripts\python.exe -m tools.studio.cli quick-create .\quick-create-request.json
```

requestは`schema_version`、既存`production_id`、事前発行した`recipe_id`、`expected_revision`、画面と同じexact `recipe`、任意の`timeout_seconds`（1〜3,600秒、既定600秒）だけを受けます。CLIはworkspace lockを取得し、同じtimeout budget内で索引更新、CAS保存、告知実行、2秒間隔のtop Job照合を行います。成功時はRun／Job／recipe revision、4 child、完成master、QC文書の相対path／bytes／SHA-256だけをbounded JSONで返し、recipe本文や絶対pathは返しません。終了codeは成功`0`、request／Job／timeout失敗`2`、technical QC non-pass`3`です。これは新しいrendererや課金経路ではなく、Studio UIと同じWindows SAPI→Remotion→assembly→QCを呼ぶcontrol-plane入口です。

まだproductionや取込済みartifactがない場合は、次の一括commandを使えます。

```powershell
.\.venv\Scripts\python.exe -m tools.studio.cli quick-create-project .\quick-create-project.json
```

`quick-create-project` schema v1は`production: {id, title}`、`videos: [{path}]`の1〜3件、`recipe_id`、`expected_revision`、exactな告知`recipe`、任意の`timeout_seconds`だけを受けます。`path`はrequest JSONがあるdirectory基準の相対pathで、絶対path、drive指定、`.`／`..`を拒否します。recipeの3 sceneは`video_artifact_id`の代わりに0始まりの`video_index`を持ち、選択した全video indexを1回以上参照します。CLIはproduction作成、各videoの逐次stream import、artifact IDへのcompile、既存Quick Createを一つのmonotonic deadline内で実行します。

成功出力はproductionのID／title／deduplicate結果、各videoの`source_index`／artifact ID／bytes／SHA-256／deduplicate結果、既存Quick Createのredacted結果だけを返します。source path、source filename、recipe本文は標準出力・標準エラーに含めません。後段が失敗しても、既に作成したproductionや取込済みartifactは監査可能な中間成果として削除しません。同じID／title／video bytesで再実行すると、既存の冪等作成とcontent dedupeへ収束します。

### `詳細一括`（既存素材からのテスト動画）

Studioの`詳細一括`タブは`POST /api/productions/{production_id}/execute-detailed-test-video`から、同じproductionへ登録済みの動画だけを使うテスト動画を開始します。request schema v1は`schema_version`、`clips`、`segments`、任意の`voice`／`rate`／`pronunciations`、`include_captioned`、`caption_style_preset`、`audio_mix_preset`、`variant`だけを受け付けます。immutableな0円`local_sapi` RunにWindows SAPIナレーション→Remotion詳細timeline→FFmpeg assembly→technical QCの4 childを作り、pipeline laneが順序を管理します。Remotionはbrowser lane、SAPI／assembly／QCはdefault laneで実行します。

SQLite schema v8のcontent-addressed claimは、正規化recipe、素材bytes／SHA-256、Remotion tool identity、字幕preflight policyから作るrequest keyで同じRun／top jobをdedupeします。failed／interruptedの明示再実行は同じRunへ新しいtop jobを追加し、成功topの再利用前には4 childのjob／attempt lineageと成果物実体を再検証します。UIはtop jobを2秒ごとに再取得し、工程、cache hit、最終master、QC passを表示します。POST応答が曖昧な場合は、送信前のcanonical payload SHA-256と一致するfreshなdirect Jobだけを受理証拠にし、既知Job、別内容、告知専用timing付きJobではlockを解除しません。Shorts大字幕では1〜6 segment、1 segmentあたり表示幅38単位以内、連続ASCII 20文字以内、不可視／双方向制御文字なしの固定preflightをqueue前に行います。

`audio_mix_preset`は`narration_only_v1`または`source_under_narration_v1`だけです。後者は素材25%＋ナレーション100%＋固定limiterで、任意gainやBGMは指定できません。この経路はH3／ComfyUI、MiniMax API、ElevenLabs、任意path／URL／CSS／React componentを呼びません。GPU動画を新規生成する既存`local_pipeline`の契約とone-clip hard-cut経路は変更していません。

### `一括生成`（local_pipeline）

Studioの`一括生成`タブはschema v4の`POST /api/productions/{production_id}/execute-local-pipeline`から固定local-onlyの制作を一つのimmutableな0円Runとして開始します。`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`の6 requested stageを記録し、ComfyUI動画生成→Windows SAPI→生成動画1本のone-clip timeline→assembly→technical QCの5 stageを専用pipeline laneで実行します。GPU childとdefault childを協調し、DB-levelのRun/top-job dedupe、failed／interruptedのsame-run retry、parent-child cancellation wait、local stage成果物のatomic確定を行います。

workflow preset、prompt、seed、segments、rate、字幕preset、variantなどの公開bodyは固定allowlistで検証されます。seedは0〜2^63−1のJSON integerです。ElevenLabs、MiniMax API、API key、cost approvalはこの経路で使いません。UIは2秒pollingで進捗を再取得し、最終master artifactとtechnical QC verdictを表示します。raw prompt/scriptはSQLite、event、job metadataへ複製しませんが、明示的な`workflow.json`、`timings`、`manifest` artifactにはcontentが含まれ得ます。

現行local_pipelineは2026-08-25にroot検証済みです。Python全263件は262件合格＋Windows上のnon-Windows専用1件skip、frontendは35/35合格し、production buildも成功しました。fake-backed統合では5 child stage、captioned master、QC文書3件、外部TTS非到達、全中間artifactの改変検知とsame-run自己修復を確認しています。その後、公式INT8＋Q4の実GPU一括生成も480×864／24fps／5.167秒で完走し、H3生成7分06秒、一括pipeline全体7分24秒、H.264＋AAC stereoのmasterとQC証跡を確認しました。現行one-clipハードカットtimelineはvideo-onlyなので、一括生成のassemblyは引き続き`narration_only_v1`固定です。

<div align="center">
  <img width="100%" src="assets/minimax-h3-header.gif" alt="MiniMax H3">
</div>

<p align="center">
  <a href="https://hailuoai.video" target="_blank"><img src="https://img.shields.io/badge/Hailuo%20AI-FF6C37?logo=minimax&logoColor=white" alt="Hailuo AI"></a>
  <a href="https://platform.minimax.io/docs/guides/text-generation" target="_blank"><img src="https://img.shields.io/badge/API-FF6C37?logo=minimax&logoColor=white" alt="API"></a>
  <a href="https://www.minimax.io" target="_blank"><img src="https://img.shields.io/badge/MiniMax%20Website-FF6C37?logo=minimax&logoColor=white" alt="MiniMax Website"></a>
  <a href="https://github.com/MiniMax-AI/MiniMax-H3" target="_blank"><img src="https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white" alt="GitHub"></a>
  <a href="https://huggingface.co/MiniMaxAI/MiniMax-H3" target="_blank"><img src="https://img.shields.io/badge/Hugging%20Face-FFD21E?logo=huggingface&logoColor=black" alt="Hugging Face"></a>
  <br>
  <a href="https://modelscope.cn/organization/minimax" target="_blank" rel="noopener noreferrer"><img alt="ModelScope MiniMax AI" src="https://img.shields.io/badge/ModelScope-MiniMax%20AI-white?labelColor=%23EF3D5D"></a>
  <a href="https://platform.minimaxi.com/docs/faq/contact-us" target="_blank"><img src="https://img.shields.io/badge/WeChat-07C160?logo=wechat&logoColor=white" alt="WeChat"></a>
  <a href="https://discord.com/invite/dbMxutw7tP" target="_blank"><img src="https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE"><img src="https://img.shields.io/badge/LICENSE-4CAF50?logo=creativecommons&logoColor=white" alt="LICENSE"></a>
</p>

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.ja.md"><strong>日本語</strong></a>
</p>

# MiniMax H3

## プロンプト作成スキル

このリポジトリに同梱されている 9 つのスキルの 1 つである H3 プロンプト作成スキルをインストールします:

```bash
npx skills add https://github.com/MiniMax-AI/MiniMax-H3 --skill h3-prompt-writing
```

このスキルには `skills/h3-prompt-writing/references/` 配下に 2 つのプロンプトガイドが含まれています。`base-en.txt` はテキスト/キーフレームモード用、`ref-en.txt` はフルリファレンス（Ref2VA）モード用です。

**エージェント互換性：** `h3-prompt-writing` は外部 API 呼び出しを行わない、純粋な Markdown + リファレンスファイルのスキルです。そのため、Claude Code、Claude Agent SDK、Cursor、Windsurf、OpenAI ベースのエージェント/Codex、LangChain など、`SKILL.md` とローカルファイルを読み取れるあらゆる環境で動作します。同梱されている `skills/h3-prompt-writing/agents/openai.yaml` は、[OpenAI のスキル仕様](https://learn.chatgpt.com/docs/build-skills) に基づき、ChatGPT/Codex のスキル UI 向けに任意の UI メタデータ（表示名、説明、デフォルトプロンプト）を追加するだけであり、このスキルを OpenAI エージェント専用に制限するものではありません。

残りの 8 つは、MiniMax Hub のキャンバスワークフロー（`hub_generate_video`、`hub_generate_image`、キャンバスノード、選択カードなど）向けに構築されたスタイル別の動画生成スキルであり、汎用のエージェント実行環境には移植できません:

<table align="center">
  <tr>
    <td align="center"><img src="assets/minimalist-product-ad-generator.gif" alt="minimalist-product-ad-generator" width="240"><br><a href="skills/minimalist-product-ad-generator/SKILL.md">minimalist-product-ad-generator</a></td>
    <td align="center"><img src="assets/3d-animation-short-generator.gif" alt="3d-animation-short-generator" width="240"><br><a href="skills/3d-animation-short-generator/SKILL.md">3d-animation-short-generator</a></td>
    <td align="center"><img src="assets/papercraft-stop-motion-explainer.gif" alt="papercraft-stop-motion-explainer" width="240"><br><a href="skills/papercraft-stop-motion-explainer/SKILL.md">papercraft-stop-motion-explainer</a></td>
    <td align="center"><img src="assets/brand-promo-video-generator.gif" alt="brand-promo-video-generator" width="240"><br><a href="skills/brand-promo-video-generator/SKILL.md">brand-promo-video-generator</a></td>
  </tr>
  <tr>
    <td align="center"><img src="assets/music-video-subtitle-generator.gif" alt="music-video-subtitle-generator"          width="240"><br><a href="skills/music-video-subtitle-generator/SKILL.md">music-video-subtitle-generator</a></td>
    <td align="center"><img src="assets/co-op-game-intro-generator.gif" alt="co-op-game-intro-generator" width="240"><br><a href="skills/co-op-game-intro-generator/SKILL.md">co-op-game-intro-generator</a></td>
    <td align="center"><img src="assets/paper-collage-explainer-generator.gif" alt="paper-collage-explainer-generator" width="240"><br><a href="skills/paper-collage-explainer-generator/SKILL.md">paper-collage-explainer-generator</a></td>
    <td align="center"><img src="assets/handdrawn-live-video-generator.gif" alt="handdrawn-live-video-generator" width="240"><br><a href="skills/handdrawn-live-video-generator/SKILL.md">handdrawn-live-video-generator</a></td>
  </tr>
</table>

## オンライン API
API 経由で MiniMax\-H3 を直接利用できます。
- Global: [platform\.minimax\.io](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) \| CN: [platform\.minimaxi\.com](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create)

## オンラインアプリ
アプリ経由で MiniMax\-H3 を直接利用できます。
- WebApp Global: [hailuoai\.video](https://hailuoai.video/tools/minimax-h3) \| CN: [hailuoai\.com](https://hailuoai.com/)
- Desktop Global: [hub\.minimax\.io](https://hub.minimax.io/) \| CN: [hub\.minimaxi\.com](https://hub.minimaxi.com/)


## システム概要
MiniMax H3 は汎用のオムニモーダル生成システムです。テキスト、画像、動画、音声で構成されるマルチモーダルなコンテキストを統合的に理解し、最大 2K 解像度、最大 15 秒、ネイティブステレオ音声付きの動画を生成できます。タスク汎化を重視したシステム設計により、H3 は事前学習段階ですでに幅広いマルチモーダルコンテキストの理解と生成能力を備えており、複雑なマルチモーダル指示への追従に優れた性能を発揮します。

H3 は以下の入出力仕様をサポートします:

| カテゴリ | 仕様 |
|---|---|
| 出力時間 | 4-15 秒 |
| 出力アスペクト比 | 21:9、16:9、4:3、1:1、3:4、9:16 など、幅広いアスペクト比をサポート |
| 出力解像度 | さまざまな解像度をサポートします。デフォルトでは短辺が 768 ピクセルに設定されます。H3-Regenerate-2K により 2K 生成が可能です |
| 出力フレームレート | 24 FPS |
| 出力音声 | 32 kHz ステレオ |
| 対応対話言語 | アラビア語、中国語、英語、フランス語、ドイツ語、イタリア語、日本語、韓国語、ポルトガル語、ロシア語、スペイン語の 11 言語を安定してサポートします。その他の言語も一定程度サポートされています |

### モデルバリアントと入力仕様

| モデルバリアント | 入力モード | 仕様 |
|---|---|---|
| H3-Base-FL2VA | First-and-last-frame mode | Supports zero, one, or two input images. <br><br>- No image input: Text-to-video mode <br>- One image input: First-frame-to-video or last-frame-to-video generation <br>- Two image inputs: First-and-last-frame-to-video generation |
| H3-Base-Ref2VA | Omni-reference mode | Supports multi-modal reference inputs: <br><br>- **Images:** ≤ 9 images <br>- **Videos:** ≤ 3 clips; each clip must be 2–15 seconds long; total duration ≤ 15 seconds <br>- **Audio:** ≤ 3 clips; audio must be accompanied by image or video input and cannot be used as the sole input; each clip must be 2–15 seconds long; total duration ≤ 15 seconds <br>- **Mixed inputs:** Maximum number of files across all input types is 12 |

![Image](assets/overview.png)

完全な H3 システムは以下の 3 つのモジュールで構成されます:
- H3-Context-IR: As inputs become increasingly complex, we build a dedicated system to deeply understand and refine the input multimodal instructions, then convert them into a form that H3 can readily understand—the Context Intermediate Representation—for generation. **H3-Context-IR is critical to the quality of the final output, so we strongly recommend incorporating it into your generation pipeline or following the “Prompting Guidance” to build your own context-processing system.**
- H3-Base: Generates audio and video based on the H3-Context-IR output, producing results at 768p resolution.
- H3-Regenerate-2K: Feeds the 768p result together with the original context back into H3 to regenerate the output at 2K resolution. This process leverages both H3’s powerful generative capabilities and the rich information contained in the original context, enabling it to produce high-resolution outputs with more accurate details and greater visual fidelity.

## モデルアーキテクチャ

### H3\-Context\-IR

H3\-Context\-IR は、自由形式のマルチモーダル入力向けに設計されたホスト型の前処理およびオーケストレーションシステムです。

テキスト、画像、音声、参照動画の関係、およびそれらの素材が目的の生成出力とどのように関係するかを解釈します。内部ワークフローには、指示解析、クロスモーダル関連付け、時間理解、複雑な論理推論が含まれます。

H3\-Context\-IR は、コンテキストの理解を H3\-Base が受け取れる構造化表現にシリアライズします。ユーザーの元の意図から逸脱しない範囲で、不足している、または指定が不十分な意味情報を適宜補完することもあります。

H3\-Context\-IR は多段階ワークフローと複数のホスト型モデルおよびサービスに依存するため、今回のオープンソースリリースには含まれていません。公式ワークフローの挙動を再現できる API を提供しています。また、開発者が **プロンプトガイド** に従って独自の前処理システムを構築できるよう、詳細なチュートリアルも提供しています。

詳しい使用方法は **推奨ワークフロー - 完全な 2K ワークフロー** を参照してください。

**安全ガードレール**

ユーザーが送信したテキスト、画像、動画、および拡張プロンプトは自動モデレーションの対象です。違法、ポルノ、または第三者の権利侵害が疑われるコンテンツはブロックされる場合があります。業界標準のフィルタリング手段を使用していますが、誤検知や見逃しを完全に排除することはできません。これらのガードレールは、MiniMax H3 Community License に基づくライセンシーの義務、特に合法的使用および使用制限に関する義務に影響しません。

### H3\-Base

![Image](assets/full-arch.png)

#### アーキテクチャ概要

- H3\-Base encodes different modalities using their corresponding encoders or VAEs and organizes the encoded representations into a unified packed multimodal sequence\. RoPE is used to capture the necessary spatial and temporal relationships among tokens before the entire sequence is passed to the H3\-Omni\-Transformer\.

- Specifically, text is encoded by the H3\-Encoder; visual inputs are encoded by both the H3\-Encoder and the H3\-VisualVAE; and audio is encoded solely by the H3\-AudioVAE\.

- The H3\-Omni\-Transformer jointly predicts video and audio latents, which are then decoded into video and stereo audio, respectively\.

- To reduce the computational cost of long multimodal sequences, H3 natively supports sparse\-attention training and inference\. The initial open\-source release provides inference with full attention only\. Our sparse\-attention implementation will be released in a future update\.

#### H3\-Encoder

- The H3\-Encoder uses the full pretrained weights of Qwen3\-VL\-32B and provides the hidden states from its 50th layer to the H3\-Omni\-Transformer\.

- We add several special tokens, such as `<d>`, to the tokenizer configuration\. When using H3, the tokenizer and associated configuration files provided in the H3 repository are required\.

#### H3\-VAE

H3 は、それぞれのモダリティを表現するために、視覚 latent と音声 latent を分離して使用します。

##### H3\-VisualVAE

- H3\-VisualVAE is a temporally causal video autoencoder with a spatial compression factor of 16×, a temporal compression factor of 4×, and 24 latent channels, denoted as f16t4d24\. We apply several latent\-space optimization techniques to jointly improve reconstruction quality and latent learnability\.

- Before being passed to the H3\-Omni\-Transformer, the visual latents are further patchified with a patch size of `1 × 2 × 2` along the `(time, height, width)` dimensions\. As a result, the visual tokens entering the Transformer have an effective spatial downsampling factor of 32×, while the temporal downsampling factor remains 4×\.

- The latent space of H3\-VisualVAE is optimized for both reconstruction quality and ease of learning by the generative model\. After training its encoder, we additionally train a ViT\-based decoder to reduce decoding costs and further improve reconstruction quality\.

##### H3\-AudioVAE

- H3-AudioVAE uses the same encoder and decoder for both the left and right audio channels while processing each channel independently. The decoded channels are then recombined, enabling stereo audio input and output.
- For each channel, H3-AudioVAE compresses 32 kHz audio into a sequence of latent tokens with a temporal rate of 40 Hz.
- Inspired by VA-VAE, we optimize the latent space to preserve audio reconstruction quality while making it easier for the generative model to learn.

#### H3\-Omni\-Transformer

- For scalability and generalization, we adopt a relatively simple Transformer block design\. H3\-Omni\-Transformer is a 33B\-parameter dense, single\-stream Transformer, with approximately 13B parameters residing in AdaLN\-related branches\. Because the AdaLN modulation outputs can be precomputed and cached, these parameters do not need to be loaded for inference\-only deployment\. We release the complete model weights to support further development, including fine\-tuning\.

- Neither the attention layers nor the FFN layers contain modality\-specific structures\. Modality\-specific parameters are confined to the input/output layers and the AdaLN branches\. In particular, modality\-specific AdaLN improves generation quality with relatively low additional training and inference costs\.

- The model uses three\-dimensional Multimodal Rotary Position Embeddings \(MM\-RoPE\) to represent positional relationships across the temporal and two spatial dimensions, `(t, h, w)`\.

- During the final stage of training, we introduce native sparse attention to reduce the computational cost of long sequences\. The sparse\-attention implementation is not included in the initial open\-source release and will be published separately in a future update\.

    

### H3-Regenerate-2K

- For H3's 2K\-resolution output, instead of using a conventional dedicated super\-resolution module, we use the H3 base model to regenerate its own low\-resolution result through an in\-context manner\.

- This approach provides two advantages: \(1\) the regeneration process can reuse the generative capabilities of H3 base model to the greatest extent possible; and \(2\) the in\-context format can reuse the original multimodal context when producing high\-resolution output, allowing it to recover information that conventional super\-resolution methods would otherwise have to “guess,” such as small text and fine details\.

- In\-context regeneration is also an example of task generalization\.

- **Due to the complexity of the system, this module is not yet open\-sourced\. We will release it once it is ready\.** We provide an API for validating the official results; see "Full 2K Workflow" below\.



## 推奨ワークフロー

コミュニティが MiniMax H3 を正しくデプロイできるよう、2 つの検証方法を提供しています。

完全な H3 システムは H3\-Context\-IR、H3\-Base、H3\-Regenerate\-2K の 3 つのモジュールで構成されるため、「完全な 2K ワークフロー」では Open Platform API とローカルにデプロイした H3\-Base を組み合わせ、2K 出力を検証するエンドツーエンドのパイプラインを提供します。「H3\-Base のローカルデプロイ」セクションでは、ローカルにデプロイした H3\-Base のみを使用して 768p 出力を検証する方法を提供します。

さらに、「プロンプトガイド」セクションでは、コミュニティが独自のプロンプトシステムを開発するための詳細なチュートリアルを提供します。

### H3\-Base のローカルデプロイ

MiniMax H3 は 2 つのタスク別 checkpoint として公開されています。各 checkpoint には、専用の Omni Transformer Model と、必要な processor、tokenizer、text encoder、Visual VAE、スタンドアロン Audio VAE コンポーネントが含まれます。

|Checkpoint|Supported Tasks|Input Conditions|Output|Precision|
|---|---|---|---|---|
|MiniMax\-H3 Base FL2VA|Text\-to\-Audio\-Video \(`t2va`\), First/Last\-Frame\-to\-Audio\-Video \(`fl2va`\)|Text; optional first frame, last frame, or both|Video and audio|BF16|
|MiniMax\-H3 Base Ref2VA|Reference\-to\-Audio\-Video \(`ref2va`\)|Text with reference images, videos, and/or audio|Video and audio|BF16|

公開されている checkpoint は、CFG 蒸留された Omni Transformer モデル重みです。 

各 checkpoint は、以下のコンポーネントを含む自己完結型の Hugging Face 形式リポジトリとして配布されます:

```text
<TASK>/
├── model_index.json
├── processor/
├── tokenizer/
├── text_encoder/
├── transformer/
├── visual_vae/
└── audio_vae/
```

モデルをダウンロードします。このリポジトリでは元の checkpoint（`FL2VA/`、`Ref2VA/`）と diffusers 形式を並行して提供しているため、使用するフレームワークに必要な範囲だけをダウンロードしてください:

`model_index.json` はリポジトリレベルの公開エントリです。タスクファミリー別の diffusers インデックスは `FL2VA/model_index.json` および `Ref2VA/model_index.json` 配下にあります。

```bash
# Original checkpoint, both task families (SGLang, vLLM):
hf download MiniMaxAI/MiniMax-H3 --include "model_index.json" "FL2VA/*" "Ref2VA/*" --local-dir MiniMax-H3

# Or a single task family:
hf download MiniMaxAI/MiniMax-H3 --include "model_index.json" "FL2VA/*" --local-dir MiniMax-H3
```

diffusers ユーザーは手動でダウンロードする必要はありません。`ModularPipeline.from_pretrained("MiniMaxAI/MiniMax-H3")` が必要なコンポーネントだけを取得します。読み込み方法は [diffusers documentation](https://github.com/huggingface/diffusers/blob/minimax-h3/docs/source/en/api/pipelines/minimax_h3.md) を参照してください。

モデルのサービングには以下の推論フレームワークを推奨します:

- [SGLang](https://docs.sglang.io/) \- see [cookbook](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3) 

- [vLLM](https://github.com/vllm-project/vllm) \- see [vllm recipes](https://recipes.vllm.ai/MiniMaxAI/MiniMax-H3)

- [diffusers](https://github.com/huggingface/diffusers) \- see [diffusers docs](https://github.com/huggingface/diffusers/blob/minimax-h3/docs/source/en/api/pipelines/minimax_h3.md)

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI) \- see  [Comfy tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3); use [R2V template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json) / [T2V template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_t2v.json)

#### Sglang デプロイ

ここでは sglang をデプロイ例として使用します。追加のデプロイ設定については [MiniMax\-H3 deployment guide](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3#3-serve-minimax-h3) を参照してください。

FL2VA:

```bash
sglang serve \
  --model-path MiniMaxAI/MiniMax-H3 \
  --num-gpus 4 \
  --ulysses-degree 4 \
  --performance-mode speed \
  --host 0.0.0.0 \
  --port 30010 \
  --model-variant fl2va
```

Ref2VA:

```bash
sglang serve \
  --model-path MiniMaxAI/MiniMax-H3 \
  --num-gpus 4 \
  --ulysses-degree 4 \
  --performance-mode speed \
  --host 0.0.0.0 \
  --port 30011 \
  --model-variant ref2va
```

#### 再現可能な 768p ケース

以下の 3 つのユースケース T2VA、FL2VA、Ref2VA は、MiniMax\-H3 の動画・音声生成を再現する方法を示しています。

| ユースケース | リクエスト | 結果 |
|---|---|---|
| T2VA | [スクリプトを見る](scripts/readme/reproducible-768p-t2va-request.sh) | [t2va.mp4](assets/t2va.mp4) |
| FL2VA | [スクリプトを見る](scripts/readme/reproducible-768p-fl2va-request.sh) | [fl2va.mp4](assets/fl2va.mp4) |
| Ref2VA | [スクリプトを見る](scripts/readme/reproducible-768p-ref2va-request.sh) | [ref2va.mp4](assets/ref2va.mp4) |

### 完全な 2K ワークフロー

このセクションでは、ローカルにデプロイした SGLang サービスと公式の **H3\-Context\-IR** および **H3\-Regenerate\-2K** API を組み合わせ、MiniMax API で直接生成した 2K 動画の品質を再現する方法を説明します。
開始前に、SGLang エンドポイントと MiniMax API 認証情報を設定してください:

```bash
# URL of your SGLang deployment
SGLANG_DEPLOYMENT_URL="<sglang-deployment-url>"

# MiniMax API endpoint (choose one)
# CN
MINIMAX_API_BASE="https://api.minimaxi.com"
# Global
# MINIMAX_API_BASE="https://api.minimax.io"

# API token obtained from the MiniMax platform
TOKEN="<token>"
```

MiniMax プラットフォーム:

API ドキュメント:
- Create H3-2K: use /video-generation-v2-create [EN-docs](https://platform.minimax.io/docs/api-reference/video-generation-v2-create), [CN-docs](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create)
- H3-Context-IR：use /video-generation-v2-h3-context-ir [EN-docs](https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir), [CN-docs](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-h3-context-ir)
- H3-Regenerate-2K：use /video-generation-v2-regeneration [EN-docs](https://platform.minimax.io/docs/api-reference/video-generation-v2-regeneration), [CN-docs](https://platform.minimaxi.com/docs/api-reference/video-generation-v2-regeneration)


以下の例では、ローカルの H3\-Base 出力ファイルを Base64 Data URL としてエンコードします。本番環境では、動画を公開アクセス可能な URL にアップロードし、その URL を `base_video` として渡すことを推奨します。

以下の各ケースでは、Open Platform API から直接生成した 2K および 768p の参照出力を提供しており、結果を検証しやすくしています。

#### case\-T2VA

- 種類: テキストから動画
- 長さ: 10 秒
- アスペクト比: 16:9

<table>
  <thead>
    <tr><th>段階</th><th>リクエスト</th><th>結果</th></tr>
  </thead>
  <tbody>
    <tr><td>H3-Context-IR</td><td><a href="scripts/readme/full-2k-t2va-h3-context-ir.sh">スクリプトを見る</a></td><td><pre><code class="language-json">{
  &quot;task&quot;: {
    &quot;id&quot;: &quot;&lt;task_id&gt;&quot;,
    &quot;model&quot;: &quot;MiniMax-H3&quot;,
    &quot;status&quot;: &quot;succeeded&quot;,
    &quot;created_at&quot;: &quot;&lt;created_at&gt;&quot;,
    &quot;updated_at&quot;: &quot;&lt;updated_at&gt;&quot;,
    &quot;content&quot;: {
      &quot;prompt&quot;: &quot;integrated_multimodal_description: [Shot 1] Cinematic, medium wide shot, pushing in slowly. In the cavernous, dimly lit bridge of a starship, sleek metallic consoles with glowing amber displays flank a massive, curved observation window. A female captain, in her late 40s with an athletic build and short silver-streaked black hair, stands in the center midground. She wears a structured, high-collared dark navy military tunic with silver chest insignias. Her back is to the camera, silhouetted against the cool, ambient starlight pouring through the thick glass. She stands perfectly still with her hands clasped tightly behind her back. Outside the window, a massive armada of jagged, dark grey dreadnoughts hovers in tight formation against a deep purple space nebula. The fleet&#39;s massive rear thrusters begin to glow with an intense, escalating bright blue light. [Shot 2] At 00:04.500, the camera cuts to a close-up of the captain&#39;s face and shakes strongly. The brilliant blue-white light from the fleet&#39;s gathering energy reflects vividly in her dark eyes. Suddenly, a blinding white flash floods through the window, completely washing out the background as the fleet jumps to hyperspace. The sheer spatial force violently jolts the bridge, causing the captain from Shot 1 to stagger slightly forward, her shoulders tensing as she visibly braces herself against the physical tremors. As the intense white light fades abruptly, leaving only the dim, empty expanse of the purple nebula reflected on her starkly lit skin, her jaw clenches, and she slowly closes her eyes in the newly emptied space.\noverall_soundscape: A low, resonant hum of the ship&#39;s ambient life support systems serves as the baseline, soon drowned out by an audible, escalating, high-pitched electronic whine as the fleet outside charges its hyperdrives. A massive, deafening, bass-heavy boom and sharp crackle erupts during the blinding flash, accompanied by the loud metallic creaking, rattling, and deep thuds of the bridge&#39;s bulkheads vibrating under immense physical stress. The intense roaring impact then cuts abruptly back to a hollow, echoing room tone, leaving only the faint, steady hum of the isolated bridge.\nnon_diegetic_music: Cinematic space-opera orchestral score, slow tempo, featuring a solitary, mournful French horn melody over deep, sustained string dissonances that build rapidly in volume and intensity, swelling to a massive orchestral peak before snapping immediately into silence right after the jump.&quot;
    },
    &quot;duration&quot;: 10,
    &quot;usage&quot;: {
      &quot;total_tokens&quot;: 8565,
      &quot;prompt_tokens&quot;: 5650,
      &quot;completion_tokens&quot;: 2915
    },
    &quot;ratio&quot;: &quot;16:9&quot;,
    &quot;task_type&quot;: &quot;h3_context_ir&quot;,
    &quot;modality&quot;: &quot;text&quot;
  }
}</code></pre></td></tr>
    <tr><td>H3-Base</td><td><a href="scripts/readme/full-2k-t2va-h3-base.sh">スクリプトを見る</a></td><td><a href="assets/t2va.mp4">t2va.mp4</a></td></tr>
    <tr><td>H3-Regenerate-2K</td><td><a href="scripts/readme/full-2k-t2va-h3-regenerate-2k.sh">スクリプトを見る</a></td><td><a href="assets/t2va_2k.mp4">t2va_2k.mp4</a></td></tr>
    <tr><td>Open Platform API を直接呼び出した 2K 参照結果</td><td><a href="scripts/readme/full-2k-t2va-reference-2k-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/h3_direct_2k.mp4">h3_direct_2k.mp4</a></td></tr>
    <tr><td>Open Platform API を直接呼び出した 768P 参照結果</td><td><a href="scripts/readme/full-2k-t2va-reference-768p-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/h3_direct_768p.mp4">h3_direct_768p.mp4</a><br></td></tr>
  </tbody>
</table>

#### case\-I2VA

- 種類: 先頭フレーム画像から動画
- 長さ: 8 秒
- アスペクト比: 自動

<table>
  <thead>
    <tr><th>段階</th><th>リクエスト</th><th>結果</th></tr>
  </thead>
  <tbody>
    <tr><td>H3-Context-IR</td><td><a href="scripts/readme/full-2k-i2va-h3-context-ir.sh">スクリプトを見る</a></td><td><pre><code class="language-json">{
  &quot;task&quot;: {
    &quot;id&quot;: &quot;&lt;task_id&gt;&quot;,
    &quot;model&quot;: &quot;MiniMax-H3&quot;,
    &quot;status&quot;: &quot;succeeded&quot;,
    &quot;created_at&quot;: &quot;&lt;created_at&gt;&quot;,
    &quot;updated_at&quot;: &quot;&lt;updated_at&gt;&quot;,
    &quot;content&quot;: {
      &quot;prompt&quot;: &quot;For the target video, at 0.00 seconds into the target video, &lt;Picture 1&gt; (from [Shot 1]) is fully referenced.\n\nintegrated_multimodal_description: [Shot 1] This is a live-action, cinematic shot with a shallow depth of field. The camera holds a perfectly static shot throughout the entire eight-second duration, capturing a cozy family gathering in a traditional Japanese dining room. The scene opens with a large, intricately patterned blue and white ceramic bowl of ramen in the immediate foreground, rendered in crisp, sharp focus. The bowl sits on a smooth, polished long wooden table. Inside the bowl, a rich, oily golden-brown broth surrounds yellow wavy noodles, topped with two thick, round slices of chashu pork featuring visible fat marbling and a distinct spiral meat pattern. A generous mound of freshly chopped, bright green scallions rests in the center, and a crisp, dark green rectangular sheet of nori seaweed is tucked into the right edge. To the left of the bowl, a pair of light brown wooden chopsticks rests horizontally on a small, dark rectangular chopstick rest, near a small cylindrical ceramic teacup with blue painted patterns. On the right side of the table, a spherical paper lantern with a ribbed bamboo frame sits on a black wooden base. In the background, a large family of seven is gathered around the table, initially appearing as a soft, blurred presence. Behind them, traditional Japanese sliding shoji screens with wooden lattice frames are open, revealing a bright outdoor scene with lush green trees. Early in the clip, the thick, white steam rising from the hot ramen broth immediately intensifies, billowing upwards in thick, swirling clouds that dance continuously above the bowl. As the clip progresses into the middle seconds, the camera maintains its static position while the focus begins a deliberate, smooth shift deeper into the room. The foreground ramen bowl, its vibrant ingredients, and the rising steam gradually soften into a hazy, out-of-focus blur. Simultaneously, the family members in the background come into sharp, detailed clarity. The heavy steam continues to rise from the foreground, creating a dynamic, translucent veil between the camera and the family. With the focus now firmly locked on the background, the vibrant family dinner comes alive. The man in the dark navy blue long-sleeved shirt on the left leans forward, his mouth moving animatedly in a silent exchange. The young girl in the crisp white short-sleeved t-shirt beside him smiles brightly, looking toward the center of the table. The woman on the far left, wearing a soft light blue long-sleeved blouse, turns her head slightly, smiling gently. Across the table, the woman in the light grey button-down shirt smiles broadly, her eyes crinkling, as she rests her hands near her plate. The woman in the dark grey top further back uses her wooden chopsticks to pick up a small piece of food from a central ceramic dish filled with bright red pickled vegetables. The woman in the center back in the light grey sweater smiles gently, her hands clasped softly in front of her, observing the interaction. Throughout the remainder of the clip, the family continues their lively physical interaction, their mouths moving in continuous, silent cadences of conversation, while the thick, white steam from the blurred ramen bowl in the foreground never stops rising, adding a comforting atmosphere to the warm gathering.\n\noverall_soundscape: The soundscape begins with a quiet room tone mixed with the faint, airy rustle of the thick steam billowing from the hot ramen bowl in the foreground, accompanied by the subtle, continuous hissing and bubbling of the rich broth. As the visual focus shifts deeper into the room, the physical sounds of the bustling family dinner become dominant in the foreground. The clear, sharp clinking of ceramic bowls and wooden chopsticks touching plates is clearly heard as the family members reach for food. This is followed by the faint, muffled thud of a cup being set down on the smooth wooden table, and the subtle, rhythmic rustle of cotton and wool clothing as the family members lean forward and gesture, perfectly capturing the lively, physical atmosphere of the shared meal.\n\nnon_diegetic_music: A gentle, heartwarming acoustic guitar melody plays softly in the background, accompanied by the subtle, resonant notes of a traditional Japanese koto. The music maintains a slow, comforting tempo that enhances the cozy, nostalgic, and joyful atmosphere of the family gathering.&quot;
    },
    &quot;duration&quot;: 8,
    &quot;usage&quot;: {
      &quot;total_tokens&quot;: 22822,
      &quot;prompt_tokens&quot;: 12800,
      &quot;completion_tokens&quot;: 10022
    },
    &quot;ratio&quot;: &quot;16:9&quot;,
    &quot;task_type&quot;: &quot;h3_context_ir&quot;,
    &quot;modality&quot;: &quot;text&quot;
  }
}</code></pre></td></tr>
    <tr><td>H3-Base</td><td><a href="scripts/readme/full-2k-i2va-h3-base.sh">スクリプトを見る</a></td><td><a href="assets/i2va.mp4">i2va.mp4</a></td></tr>
    <tr><td>H3-Regenerate-2K</td><td><a href="scripts/readme/full-2k-i2va-h3-regenerate-2k.sh">スクリプトを見る</a></td><td><a href="assets/i2va_2k.mp4">i2va_2k.mp4</a><br></td></tr>
    <tr><td>Open Platform API を直接呼び出した 2K 参照結果</td><td><a href="scripts/readme/full-2k-i2va-reference-2k-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/i2va_direct_2k.mp4">i2va_direct_2k.mp4</a></td></tr>
    <tr><td>Open Platform API を直接呼び出した 768P 参照結果</td><td><a href="scripts/readme/full-2k-i2va-reference-768p-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/i2va_direct_768p.mp4">i2va_direct_768p.mp4</a></td></tr>
  </tbody>
</table>

#### case\-Ref2VA

- 種類: マルチモーダル参照から動画（動画 + 音声）
- 長さ: 5 秒
- アスペクト比: 自動

<table>
  <thead>
    <tr><th>段階</th><th>リクエスト</th><th>結果</th></tr>
  </thead>
  <tbody>
    <tr><td>H3-Context-IR</td><td><a href="scripts/readme/full-2k-ref2va-h3-context-ir.sh">スクリプトを見る</a></td><td><pre><code class="language-json">{
  &quot;task&quot;: {
    &quot;id&quot;: &quot;&lt;task_id&gt;&quot;,
    &quot;model&quot;: &quot;MiniMax-H3&quot;,
    &quot;status&quot;: &quot;succeeded&quot;,
    &quot;created_at&quot;: &quot;&lt;created_at&gt;&quot;,
    &quot;updated_at&quot;: &quot;&lt;updated_at&gt;&quot;,
    &quot;content&quot;: {
      &quot;prompt&quot;: &quot;subject_definitions:\n&lt;Subject 1&gt; is the young man with short wavy blonde hair, wearing a bright pink suit jacket, matching pink trousers, an unbuttoned white shirt, and silver rings, holding a small black lamb in his arms in &lt;Video 1&gt;.\n&lt;Video 1&gt; is the source video for the editing task.\n&lt;Audio 1&gt; is the synchronized audio track of &lt;Video 1&gt;, providing the background music.\n&lt;Audio 2&gt; is the voice timbre reference for &lt;Subject 1&gt;&#39;s voice, containing a spoken male voiceover.\n\nsummary:\n[video editing + audio reference + audio reuse] The target video is an edited version of &lt;Video 1&gt;. &lt;Subject 1&gt;, wearing a bright pink suit and holding a black lamb, stands in a grassy field with other white lambs in the background. The edit animates &lt;Subject 1&gt;&#39;s face to speak the user-provided dialogue. &lt;Audio 1&gt; is partially reused as the continuous background music, while the target references the calm male voice timbre of &lt;Audio 2&gt; for &lt;Subject 1&gt;&#39;s spoken lines.\n\nretention_analysis:\n&lt;Subject 1&gt; (appears in [Shot 1]): fully_preserved - the man retains his identity, wavy blonde hair, pink suit, white shirt, accessories, and the black lamb he holds, with his mouth newly animated to speak.\n&lt;Video 1&gt; (source video editing): fully_preserved - the original camera framing, warm golden hour lighting, grassy hill setting, and background white lambs are maintained while the central character is edited.\n&lt;Audio 1&gt;: partially_copy - the atmospheric background music from &lt;Audio 1&gt; is reused in the target video, mixed beneath the newly added spoken dialogue.\n&lt;Audio 2&gt;: reference - the target audio references the male voice timbre from &lt;Audio 2&gt; to generate &lt;Subject 1&gt;&#39;s spoken dialogue.\n\ndetailed_description:\nThe target video is in realistic photographic style.\n[Shot 1] The shot begins from the source &lt;Video 1&gt;, showing &lt;Subject 1&gt;, a young man with short wavy blonde hair, wearing a bright pink suit jacket, matching pink trousers, and a casually unbuttoned white shirt. He stands confidently in a sunlit green pasture, gently holding a small black lamb securely in his arms. The warm, golden hour lighting casts soft shadows across his face and the bright pink fabric of his suit. Behind him, several white lambs stand and graze on the rolling grassy hill against a clear, pale blue sky. The atmospheric background music from &lt;Audio 1&gt; plays continuously throughout the scene. &lt;Subject 1&gt; physically speaks, his mouth movements naturally syncing to the new dialogue, with his voice timbre referencing the calm male delivery from &lt;Audio 2&gt;. Looking thoughtfully forward, &lt;Subject 1&gt; (S1) speaks softly, &lt;d&gt;[English] Follow the wind, live free.&lt;/d&gt; As he delivers the line, he subtly shifts his weight, cradling the resting black lamb while the camera slowly pushes in. &lt;Subject 1&gt; (S1) continues his thought, &lt;d&gt;[English] Leave worries behind, enjoy the moment.&lt;/d&gt; Exactly as his voice stops, his lips meet in a relaxed, peaceful smile, and his jaw ceases speaking motion. He then turns his gaze slightly away toward the horizon, gently stroking the black lamb&#39;s fleece with his fingers as the camera holds on this tranquil, sunlit state through the end of the video.\n\noverall_soundscape:\nThe soundscape consists of the continuous, atmospheric background music from &lt;Audio 1&gt;, overlaid with the clear, calm male dialogue spoken by the main character, referencing the voice timbre of &lt;Audio 2&gt;.\n\nnon_diegetic_music:\nThe atmospheric, sustained background music from &lt;Audio 1&gt; is reused as the continuous score, playing quietly beneath the spoken dialogue.&quot;
    },
    &quot;duration&quot;: 5,
    &quot;usage&quot;: {
      &quot;total_tokens&quot;: 39299,
      &quot;prompt_tokens&quot;: 33323,
      &quot;completion_tokens&quot;: 5976
    },
    &quot;ratio&quot;: &quot;16:9&quot;,
    &quot;task_type&quot;: &quot;h3_context_ir&quot;,
    &quot;modality&quot;: &quot;text&quot;
  }
}</code></pre></td></tr>
    <tr><td>H3-Base</td><td><a href="scripts/readme/full-2k-ref2va-h3-base.sh">スクリプトを見る</a></td><td><a href="assets/r2va.mp4">r2va.mp4</a><br></td></tr>
    <tr><td>Open Platform API を直接呼び出した 2K 参照結果</td><td><a href="scripts/readme/full-2k-ref2va-reference-2k-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/r2va_2k.mp4">r2va_2k.mp4</a></td></tr>
    <tr><td>参考用 Open Platform の H3 API 2K 結果</td><td><a href="scripts/readme/full-2k-ref2va-h3-api-2k-in-open-platform-for-reference.sh">スクリプトを見る</a></td><td><a href="assets/r2va_direct_2k.mp4">r2va_direct_2k.mp4</a><br></td></tr>
    <tr><td>Open Platform API を直接呼び出した 768P 参照結果</td><td><a href="scripts/readme/full-2k-ref2va-reference-768p-result-by-directly-calling-open-platform-api.sh">スクリプトを見る</a></td><td><a href="assets/r2va_direct_768p.mp4">r2va_direct_768p.mp4</a><br></td></tr>
  </tbody>
</table>

### プロンプトガイド

Markdown の構成を簡潔に保つため、Hugging Face リリースのプロンプトガイド文書はこのリポジトリにはコピーしていません。



## ライセンス

MiniMax H3 は [MiniMax H3 Community License Agreement](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) の下で公開されています。

## お問い合わせ

お問い合わせは [model@minimax.io](mailto:model@minimax.io) までお願いします。
