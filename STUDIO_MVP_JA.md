# MiniMaxH3 Studio MVP

## 目的

MiniMaxH3 Studioは、制作案件、ログ、中間成果物、費用、承認履歴を1か所で確認するためのローカルWebアプリです。チャットは企画と監督の窓口、Studioは実行状態と証跡を保持する制御盤として分離します。`一括生成`タブからは新しいH3素材を含む固定local-only経路を、`詳細一括`タブからは登録済み素材を使うSAPI／Remotion／assembly／QC経路を、それぞれ一つのRunとして実行できます。`告知動画`タブは後者をHOOK／MESSAGE／CTAの固定3シーンへ絞り、保存・複製・一括実行できる実用テンプレートとして提供します。

このMVPはPowerDirectorのような汎用ノンリニア編集ソフトではありません。既存の`productions/`と`outputs/productions/`を読み込み、制作記録の閲覧、再実行計画、承認、監査exportを扱う土台です。Windows SAPIによるローカルナレーションworker、ElevenLabs Multilingual v2の文字時刻付き外部TTS worker、固定workflowによるローカルComfyUI MiniMax H3動画worker、isolated Chromiumでloopback Webページを縦動画へ記録するPlaywright画面収録worker、登録済み動画をトリムして順序付きハードカットへ連結するFFmpeg timeline worker、fade／素材音量／固定テロップと同一compositionのPlayer previewを備えたRemotion詳細timeline worker、既存4 workerを束ねる詳細テスト動画orchestrator、そのcontractへcompileする告知動画recipe、音声・字幕合成worker、完成masterのローカルtechnical QC workerまでを実装済みです。Windowsデスクトップ／ネイティブアプリ収録、任意track／effect／componentを扱う汎用編集、MiniMax外部APIのStudio workerは後続段階です。

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
- ComfyUI taskとpipeline continuationをschema v7へ永続化し、Studio終了時はprovider側の生成を継続する。次回起動ではHTTP serverを待たせないbackground照合を行い、旧attemptを履歴として残した同じRunの新attemptから重複POSTなしで回収する。
- 同一Run／cache key／payload digestの動画生成requestはSQLiteの永続claimで1つのactive jobへ集約し、複数画面から同時実行しても新しいComfyUI POSTを増やさない。Studioはactive-active構成ではなく、workspace単一起動lockで第二processを先に拒否する。
- `local_playwright`の0円runを作り、明示したloopback Web URLをfresh Chromium contextで1〜30秒収録する。
- 収録中の操作は時刻付き`scroll`、`click`、allowlist済み`press`だけを最大16件受け付け、任意JavaScript、cookie、storage state、header、browser flag、出力pathは受け付けない。
- 生WebMを固定1080×1920、24fps、H.264／yuv420p、video-only MP4へ変換し、`screen-capture.mp4`、`playwright-raw.webm`、始点／終点PNG、sanitized report、`ffprobe.json`、自己hash付き`manifest.json`の7成果物をatomicに登録する。
- 画面収録を専用browser laneへ分離し、job／attempt／progress／成果物previewを2秒pollingで追跡する。`local_playwright` Runの`requested_stages`と実行可能工程は`screen_capture`と`timeline`だけです。`assembly`と`qc`はgeneric rerun planの`affected_stages`に影響工程として残りますが、このprofileでは実行しません。画面収録とtimelineのジョブ状態・進捗率を2秒pollingで表示し、収録MP4は同じproductionのtimeline入力候補にできます。
- `local_pipeline`の`一括生成`タブから、固定workflowの動画、Windows SAPIナレーション、生成動画1本を全尺1カットにするtimeline、assembly、technical QCを一度に実行する。
- `local_pipeline`は`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`の6 requested stageを持つimmutableな0円Runで、実workerはComfyUI→SAPI→one-clip timeline→assembly→QCの5 stageを順次実行する。
- 専用pipeline laneがGPUのComfyUI childとdefault laneのSAPI／FFmpeg childを協調し、DB-levelのcanonical keyでRun/top jobをdedupeする。failed／interrupted後は同じRunのattemptを再試行し、親cancelはchildの終了を待ってから確定する。
- `local_pipeline`の各local stageはjob、stage attempt、artifact、eventをatomicに確定し、UIは2秒pollingと再読込race recoveryで5段の進捗、最終master artifact、technical QC verdictを表示する。
- 中断した`local_pipeline`は、DPAPI保護した正規化requestと成功済みvideo checkpointを使って同じRunへ新topを一件だけ自動投入する。checkpoint付きvideo stageは検証済みcache専用で、新しいComfyUI生成へfallbackしない。
- 同じproductionの登録済み動画を1〜32カット選び、順序変更、複製、開始／終了ミリ秒の指定からハードカットpreviewを明示実行する。
- timeline previewを1080×1920、24fps、H.264／yuv420p、video-only MP4へ固定し、`timeline-preview.mp4`、`timeline.json`、`ffprobe.json`、`manifest.json`を生成する。
- ハードカットを残したまま`Remotion詳細preview`を選び、登録済み動画1〜16カット、最大60秒のschema v1 recipeへtrim、素材音量0〜100%、50〜2,000msのfade、固定`shorts_ja_large_v1`テロップ、閉じた`preserve_v1 | h3_low_res_sharp_v1`映像補正presetを設定する。
- UIの`@remotion/player`とbackend rendererで同じtracked compositionを使い、Source Fidelity v2のPNG中間frame／CRF 16で1080×1920／24fpsの`remotion-preview.mp4`、recipe、render report、ffprobe、manifestの固定5成果物を生成する。Playerは固定FFmpeg前処理を再現しないため、鮮明化は完成artifactで確認する。
- `詳細一括`タブから、登録済み動画1〜16件とナレーション台本を一度だけ確定し、Windows SAPI→Remotion詳細timeline→assembly→technical QCを一つのimmutableな0円`local_sapi` Runで実行する。
- 詳細一括topはpipeline lane、Remotion childはbrowser lane、SAPI／assembly／QC childはdefault laneを使う。UIはtop jobを2秒pollingし、4 childのjob／attempt、cache hit、完成master、QC verdictを表示する。
- SQLite schema v7の`detailed_test_video_claims`で同一production／content-addressed requestを一つのRunとactive topへ集約し、failed／interrupted後は同じRunへ新しいtop jobを追加する。成功topの再利用前にはchild lineageと成果物bytes／SHA-256を再検証する。
- `shorts_ja_large_v1`字幕を選んだ詳細一括では、segment数、表示幅、長いASCII token、不可視／双方向制御文字をqueue前に固定policyで検査する。
- `告知動画`タブでHOOK／MESSAGE／CTAの3シーン、登録済み動画、trim、素材音量、映像補正preset、大見出し、必須ナレーションを設定し、10〜20秒（推奨15秒）の固定テンプレートとして保存・複製・一括実行する。
- 告知recipeは`expected_revision` CAS付きのimmutableなexact revisionとしてproduction eventへ追記し、clone元versionとDetailed Job／Runへのexecution linkを保持する。同じcompile結果はDetailed側でdedupeし、別recipeからの実行リンクは失わない。
- 告知動画の実行中はJobを2秒間隔、production detailを初回とおおむね6秒間隔で取得する。応答が曖昧な場合は新しいexecution linkのexact Jobを照合し、なければ同じimmutable revisionを1回だけ冪等再送する。2回目も曖昧なら自動処理を止め、手動再照合だけを許可する。
- 同じproductionの登録済み動画と、同じRunの成功済みナレーションattemptを選び、source audioを置換した`master-clean.mp4`をローカル生成する。
- 任意で、SRTを制御タグ不能な固定style ASSへ変換し、`studio_default_v1`またはShorts向け大字幕`shorts_ja_large_v1`で`master-captioned.mp4`を追加生成する。
- `ffprobe.json`と自己hash付き`manifest.json`へ入力hash、FFmpeg/ffprobeの実体・version・binary hash、音声方針、出力方針を記録する。
- 同じRunの成功済みassembly attemptからcleanまたはcaptioned masterを選び、MP4 container、stream構成、H.264／yuv420p、AAC 48 kHz stereo、尺、full decode、全編無音をローカル検査する。schema v2の固定`technical-qc-mp4-v2`ではIntegrated loudness -24.0〜-10.0 LUFS、true peak -1.0 dBFS以下、0.5秒以上の黒画面をhard checkとして追加する。
- QC解析結果を`technical-qc.json`、`ffprobe.json`、自己hash付き`manifest.json`として保存し、解析完了とtechnical verdictのpass／failを分けて表示する。1.0秒以上の長い静止区間は`media_facts.long_static.warning=true`のadvisoryとして保存し、technical verdictには影響させない。
- stage attemptと実行jobの永続リンク、queued/running/succeeded/failed、所要時間、cache hit、provider、task ID、実費、timing source、成果物hashをUIと監査記録で追跡する。
- 同一入力の成功cacheをhash検証後に再利用し、改変・欠落時は再生成する。
- `test-video` CLIから、索引更新、0円Run作成、narration、1カットtimeline、assembly、technical QCを順番に実行し、完成MP4と監査識別子を1つのJSONで受け取る。

MVPが行わないこと:

- ElevenLabs以外の外部有料provider、MiniMax外部APIの実行
- Windowsデスクトップ／ネイティブアプリ、system audio、microphone、外部Webサイト、既存ログインsessionの収録
- 複数audio track、任意transition／effect、free-form CSS／font／React component、keyframe、任意映像filter／鮮明化強度、任意resolution／fpsを含む汎用タイムライン編集
- 詳細一括からのH3／ComfyUI生成、外部provider呼出し、任意path／URL／gain指定
- 告知動画v1でのBGM、ロゴ画像、任意renderer／CSS／React component、任意のシーン構成、ナレーションなし実行
- ブラウザから任意ローカルpathを読むこと
- creativeまたは公開権利を自動承認すること

「run作成」は監査可能な実行計画を保存する操作で、それだけではworkerや課金APIを開始しません。`local_sapi` runでは、作成後にナレーション、カット編集、編集・合成、品質検査の各画面または対応する専用APIで明示したときだけローカルworkerを開始します。`local_comfyui` runも、生成映像画面でpromptとseedを確認して実行した場合だけGPU workerを開始します。`local_playwright` runは、画面収録画面でURL、尺、操作を確認して明示実行した場合だけbrowser workerを開始します。`elevenlabs_tts` runは、作成、正の費用見積、上限承認に加え、外部音声画面で送信内容を確認して`confirm_billable=true`を明示した場合だけ外部TTS workerを開始します。FFmpegハードカットとRemotion詳細timelineはいずれも同じproductionの登録済み動画artifactだけを受け付け、`timeline`をrequested stageに含む対応profileから明示実行します。合成は同じRunの成功済みナレーションを、QCは同じRunの成功済みassembly attemptを必須とします。両timeline previewは通常の登録済み動画と同じ入力候補としてassemblyへ渡せます。
通常の課金対象requested stageを含むrunには正の見積額が必須です。0以下または未指定の見積はfail closedで拒否し、runを残しません。`local_sapi`はnarration、captions、timeline、assembly、qcだけを対象にする0円profileです。詳細一括は専用endpointからこのprofileのimmutable Runを作り、4 workerを束ねます。`elevenlabs_tts`はnarrationを必須とし、narration、captions、assembly、qcだけを対象にする課金profileです。`local_comfyui`はvideo_generationを必須とし、video_generation、timeline、assembly、qcを対象にする0円profileです。`local_playwright`はscreen_captureを必須とし、screen_captureとtimelineだけを実行可能にする0円profileです。`local_playwright`のassembly／qcは影響工程としてRun計画に残りますが、このprofileでは実行しません。`local_pipeline`は専用endpointからのみ作成する、6 requested stage／5 executed stageの固定local-only 0円profileです。ElevenLabs、MiniMax API、費用approvalは詳細一括と`local_pipeline`のどちらにも到達しません。

告知recipeの保存と複製はversion eventを追記するだけで、media workerを開始しません。`execute`で保存済みexact revisionを指定した場合だけDetailed Test Videoの0円`local_sapi` Run／top Jobを作成または再利用します。告知動画からもElevenLabs、MiniMax API、ComfyUI、費用approvalへ到達しません。

## 告知動画テンプレート（Announcement Video v1）

`告知動画`タブは、汎用編集画面を開かずに既存素材から短い告知を完成させる入口です。同じproductionにavailableな動画artifactが必要です。素材はシーンごとに選び、同じartifactを複数シーンで再利用することもできます。新しいH3素材の生成は行いません。

画面上の基本操作は次のとおりです。

1. HOOK、MESSAGE、CTAの順に、動画artifact、開始／終了、素材音量、映像補正preset、大見出し、ナレーションを入力する。
2. 必要に応じてSAPI voice、読み上げ速度、発音置換、焼き込み字幕、音声mix、QC対象variantを設定する。
3. `保存`でexact revisionを残す。保存済みrevisionを元のまま残して試案を作る場合は`複製して編集`を使う。
4. 消音の3シーンpreviewで素材、trim、fade、大見出しを確認する。
5. `保存して告知動画を作る`で、必要な保存の後にそのexact revisionをDetailed Test Videoへ投入する。完成masterでナレーション、字幕、音声mix、technical QCを確認する。

HTTP境界は次の4本です。変更系は通常のStudio session token／Origin検査を通ります。

| Method / path | exact request | 役割 |
|---|---|---|
| `GET /api/productions/{production_id}/announcement-recipes` | bodyなし | 最新recipe、全immutable version、execution linkを1つのDB snapshotで返す |
| `POST /api/productions/{production_id}/announcement-recipes/{recipe_id}/save` | `schema_version`、`expected_revision`、`recipe` | 新規作成またはCAS付きrevision追記 |
| `POST /api/productions/{production_id}/announcement-recipes/{recipe_id}/duplicate` | `schema_version`、`source_revision`、`new_recipe_id`、`name` | exact source revisionを新しいrecipe identityへ複製 |
| `POST /api/productions/{production_id}/announcement-recipes/{recipe_id}/execute` | `schema_version`、`revision` | 保存済みexact revisionをcompileしてDetailed top Jobを作成または再利用 |

recipeのpublic schema v1は余分なfieldを拒否します。外形は次のとおりです。

```json
{
  "schema_version": 1,
  "name": "新機能の15秒告知",
  "template_preset": "shorts_ja_15s_v1",
  "scenes": [
    {
      "role": "hook",
      "video_artifact_id": "art_0123456789abcdef0123456789abcdef",
      "start_ms": 0,
      "end_ms": 5000,
      "volume_percent": 0,
      "visual_preset": "preserve_v1",
      "headline": "その情報、\n届いていますか？",
      "narration": "十五秒で、しっかり伝える。"
    },
    {
      "role": "message",
      "video_artifact_id": "art_1123456789abcdef0123456789abcdef",
      "start_ms": 0,
      "end_ms": 5000,
      "volume_percent": 0,
      "visual_preset": "h3_low_res_sharp_v1",
      "headline": "大切なことを\nひと目で",
      "narration": "大切な情報を、ひと目で。"
    },
    {
      "role": "cta",
      "video_artifact_id": "art_2123456789abcdef0123456789abcdef",
      "start_ms": 0,
      "end_ms": 5000,
      "volume_percent": 0,
      "visual_preset": "preserve_v1",
      "headline": "詳しくは\nプロフィールへ",
      "narration": "続きはプロフィールから。"
    }
  ],
  "voice": null,
  "rate": 0,
  "pronunciations": [],
  "include_captioned": true,
  "caption_style_preset": "shorts_ja_large_v1",
  "audio_mix_preset": "narration_only_v1",
  "variant": "captioned"
}
```

sceneは`hook`、`message`、`cta`の3件をこの順序で必須とし、各trimは1〜10秒です。2つの250ms fadeを差し引いた完成尺を10〜20秒に制限し、UIは15秒を推奨します。compile時は最初の2 clipへ固定250ms fadeを入れ、大見出しを各trimの125ms後から終了125ms前まで表示します。位置はHOOK=`center`、MESSAGE=`top`、CTA=`center`、styleは`shorts_ja_large_v1`固定です。各sceneの`visual_preset`は`preserve_v1`または`h3_low_res_sharp_v1`だけで、省略した旧recipeは`preserve_v1`として読み続けられます。見出しは1〜2行、各行20表示単位以内、連続ASCII token 20文字以内で、不可視／bidi制御文字を拒否します。各ナレーションは空でない1行、最大200文字で、3件のSAPI segmentになります。

新規フォームの既定trimは5,167ms／5,167ms／5,166msです。合計15,500msから250msのfade overlapを2回差し引き、24fpsのRemotion出力を360 frame、15.000秒にします。素材がこれより短い場合は判明しているsource尺までに抑え、保存・実行時のbackend検証を正本とします。

告知recipeからの実行に限り、内部policy `announcement_scene_starts_v1`でSAPI segment開始をRemotion出力上のscene開始へ揃えます。開始は、各trimと各250ms fadeをRemotion compilerと同じ24fpsでそれぞれhalf-up丸めし、frame cursorへ個別に加減算してからmsへ戻して導出します。raw msの累積だけでは求めません。narration WAVには必要な無音frameを挿入し、SRTも同じ実WAV frame時刻を使います。前segmentの実音声が次scene開始を越える場合は音声を重ねたり切ったりせず、`narration segment overlaps the next scheduled scene`でfail closedにします。通常の公開SAPI APIと通常cache identityは変更せず、この内部schedule、そのpolicy、開始時刻を告知のnarration／Detailed request key、job／attempt監査、timing／manifestへ含めるため、同期前の旧成果物は再利用しません。

compile結果は既存Detailed Test Video v1のexact schemaへ再検証されます。`voice`は任意、`rate`は−10〜10、発音置換は最大100件です。字幕は`studio_default_v1`または`shorts_ja_large_v1`、音声は`narration_only_v1`または固定の`source_under_narration_v1`、QC対象は`clean`または`captioned`だけです。素材音mixを選ぶ場合は少なくとも1シーンの`volume_percent`を1以上にし、後続assemblyで素材音声1 streamと素材／ナレーション双方の非無音を確認します。BGM、ロゴ画像、自由なgain／ducking、任意transition、任意overlay位置、CSS、font、React component、renderer propsはv1に存在しません。

保存時は`expected_revision`が現在版と一致する場合だけ、`announcement.recipe.saved`をproductionのhash-chain eventへ追記します。eventはrecipe ID／version ID、revision、親version、任意のclone元version、canonical JSONのbytes／SHA-256、監査用summaryに加え、完全なcanonical JSONをBase64で保持します。同じ内容へのlost-response再送はdedupeしますが、古いrevisionからの異なる内容は`announcement_recipe_conflict`で拒否します。

> [!CAUTION]
> Base64は可逆なencodingであり、暗号化でもredactionでもありません。recipe名、見出し、ナレーション、発音置換はSQLite、event JSONL mirror、production detail API、監査exportから読める平文相当の情報です。API key、token、password、秘密、公開不要の個人情報を入力しないでください。

実行ではrecipe名を除くcompile済みDetailed payload、scene由来のnarration開始時刻とpolicyが、従来の素材hash／tool identity／字幕policyを含むrequest keyへ入ります。名前だけを変えたcloneなどcompile結果とscene timingが同じ場合、queued／runningまたは物理再検証済みsucceededのDetailed top JobとRunを再利用します。一方、CTA見出し、ナレーション、trimなどを変更すれば別request keyです。各recipe versionとJobの関係は`announcement.recipe.executed`として別々に追記します。Detailed top Jobの作成または再利用決定と、このexecution linkは同じSQLite transactionで確定するため、recipeから追跡できない新規topを受理しません。

UIは実行中のJob一覧を2秒間隔で取得し、production detailは最初のpollと3回ごと、すなわちおおむね6秒間隔へ抑えます。告知用の保存・複製・実行・Job／production照合requestはprivateな`AbortSignal`を必ずforwardし、15秒でabortします。保存の応答が不明なら同じrecipe ID・`expected_revision`・canonical内容を1回だけ再送します。複製はsource identity／コピー名から128-bit clone IDを決定的に導出し、intent固有のversioned `localStorage` keyへPOST前に保存します。画面移動／再読込後も同じIDを使い、複数tabの同時操作も同じbackend recipe IDへ収束します。成功応答またはimmutable版履歴のexact clone lineageを確認した場合だけ消去し、timeout／通信／再送後4xxでは保持します。保存領域のruntime検証またはread-after-writeに失敗した場合はPOSTせず、明示破棄もbrowser intentだけを対象にします。backendのCAS／digest／clone-source lost-response dedupeと合わせ、応答消失で別revisionや別cloneを作りません。実行POST応答を受け取れなかった場合、送信前snapshotになかったexact recipe versionのexecution linkだけを受理証拠とし、そのJob IDを`GET /api/jobs/{job_id}`で取得してproduction、Run、revision、request keyまで照合します。既知の成功Jobは、今回のPOST到達や現在の成果物健全性を証明しないため、履歴表示だけに使い曖昧状態を解除しません。新しいlinkが確認できなければ、同じimmutable recipe ID／revisionを1回だけ自動再送します。この再送はDetailedのcontent claimへ直列化され、queued／runningと、全child lineage・全成果物のbytes／SHA-256を物理再検証できたsucceeded Jobだけを再利用し、欠損・改変時だけ同じRunの修復Jobを作ります。2回目のPOSTまたはfresh linkのexact Job照合がtimeout／通信／5xxで不明なら自動requestを止め、フォームの永久lockを避けて`同一revisionを再照合`を表示し、明示した場合だけ1回ずつ同じPOSTを行います。実行requestで受信済みの4xxは未受理としてlockを解除します。別tabで最新revisionが進んだ場合は、cleanかつidleなら自動同期し、編集中または実行中なら内容を上書きせず警告して保存・実行を止めます。未保存変更がある状態でrecipeを切り替える、productionを移動する、別タブへ移る操作は確認を挟み、未保存状態では複製を無効にします。productionを切り替えると旧detail requestをabortし、request generationと現在の選択IDが一致した応答だけをstateへ反映・描画します。

補足: ここでいう自動request停止は、追加POSTと同じ候補へのexact Job GETを止める境界です。2秒のJob／おおむね6秒のproduction detail照合は継続し、後からfreshなexact linkを確認できれば再POSTせず復旧します。idle時に別tabのproduction detailをbackground取得する機能はありません。別tabの新revisionは、手動再読込または実行／曖昧応答中のdetail再取得で検出した後、cleanかつidleなら読み込み、編集中または実行中なら上書きせず保存・実行を止めます。複製intent用`localStorage`が壊れているか利用できない場合は、複製だけでなく告知フォーム全体を明示破棄または環境復旧までロックします。

## 詳細一括（Detailed Test Video v1）

`詳細一括`タブは、すでに同じproductionへ登録されている動画を、ナレーション、詳細カット編集、音声・字幕合成、technical QCまで仕上げる入口です。HTTP境界は`POST /api/productions/{production_id}/execute-detailed-test-video`です。新しいH3映像は生成せず、既存の手動ナレーション／timeline／assembly／QC APIと`local_pipeline`も変更しません。

public bodyは次のsnake_case schema v1だけを受け付け、余分なfieldを拒否します。`schema_version`、`clips`、`segments`、`include_captioned`、`caption_style_preset`、`audio_mix_preset`、`variant`は必須、`voice`、`rate`、`pronunciations`は任意です。省略時はSAPIの既定voice、`rate=0`、発音置換なしへ正規化されます。各clipは従来の6 fieldをすべて持ち、任意の`visual_preset`を追加できます。transitionとoverlayを使わない場合は`null`を明示し、visual presetを省略した既存payloadは`preserve_v1`へ正規化します。

```json
{
  "schema_version": 1,
  "clips": [
    {
      "video_artifact_id": "art_0123456789abcdef0123456789abcdef",
      "start_ms": 0,
      "end_ms": 5000,
      "volume_percent": 100,
      "visual_preset": "h3_low_res_sharp_v1",
      "transition_to_next": null,
      "overlay": {
        "text": "CLAUDE.md",
        "start_ms": 200,
        "end_ms": 1800,
        "position": "top",
        "style_preset": "shorts_ja_large_v1"
      }
    }
  ],
  "segments": [{"text": "重要な設定を、毎回自動で読み込みます。"}],
  "voice": "Microsoft Haruka Desktop",
  "rate": 0,
  "pronunciations": [{"source": "AI", "target": "エーアイ"}],
  "include_captioned": true,
  "caption_style_preset": "shorts_ja_large_v1",
  "audio_mix_preset": "source_under_narration_v1",
  "variant": "captioned"
}
```

`clips`はRemotion schema v1と同じ登録済みartifact ID、trim、0〜100%の素材音量、任意の固定fade、任意の固定テロップ、任意の閉じた`visual_preset`だけを許します。動画は1〜16件、合成後最大60秒です。最後のclipの`transition_to_next`は`null`で、fadeは隣接clipより短くします。overlayは`text`、`start_ms`、`end_ms`、`position=top | center | bottom`、`style_preset=shorts_ja_large_v1`だけです。`h3_low_res_sharp_v1`は幅1080未満・高さ1920未満、両辺64px以上、幅÷高さ0.50〜0.625、cover拡大後300万画素以下の低解像度縦長素材専用で、その他の素材にはFFmpeg起動前にfail closedです。path、URL、renderer props、CSS、font、React component、FFmpeg filterや鮮明化強度はrequestに存在しません。

`include_captioned=true`かつ`caption_style_preset=shorts_ja_large_v1`では、固定`shorts_ja_large_preflight_v1`をqueue前に適用します。segmentは1〜6件、各textは表示幅38単位以内です。ASCIIと半角カナは1単位、それ以外は2単位で数え、連続ASCII tokenは20文字以内とします。zero-width／bidi isolate・override／BOMなどの不可視・双方向制御文字も拒否します。これは固定大字幕に対する保守的なcontractで、任意の自動縮小、自由な改行、font差し替えは行いません。標準字幕では既存`studio_default_v1` contractを使います。`variant=captioned`には`include_captioned=true`が必要で、字幕を作らない場合は`variant=clean`と`caption_style_preset=studio_default_v1`を指定します。

`audio_mix_preset`は`narration_only_v1`または`source_under_narration_v1`だけです。前者は素材音を置換し、後者はRemotion previewの素材音を25%、ナレーションを100%に固定してlimiterへ通します。後者は素材audio 1 streamと素材／ナレーション双方の非無音を必須にし、任意gain、BGM、duckingは受け付けません。UIも全clipが`volume_percent=0`のmix要求を事前に拒否します。

受理時は正規化payload、素材artifactのbytes／SHA-256、Remotion tool cache identity、字幕preflight policyを含むcontent-addressed request keyを作ります。正規化payload単体のcanonical SHA-256も、本文を複製しない照合用audit fieldとしてtop Jobへ保存します。SQLite schema v7の`detailed_test_video_claims`は`production_id + request_key`を主キーに、immutableな0円`local_sapi` Run／revisionとactive top jobを結びます。同じ要求のqueued／running topはそのまま返し、検証済みsucceeded topも再利用します。failed／interrupted、queue admission失敗、または成功成果物の欠落・改変時はRunを増やさず、新しい`detailed_test_video` top jobを同じRunへ追加します。`revision.created` event mirrorにはclaimのproduction／request／Run／revision identityを含め、SQLite索引再構築時は厳密なschema／profile／0円／requested-stage検証後にclaimを`active_job_id=null`で復元します。過去の一時的top jobを推測復元せず、次の明示実行で新jobへ安全にretryします。

top jobは専用pipeline laneで順序を管理し、`narration`、`timeline`、`assembly`、`qc`の4 childを既存APIへ投入します。Remotion timelineだけはPlaywright収録と共有するbrowser FIFO lane、SAPI／assembly／QCはdefault FIFO laneです。各childについてexact job ID、attempt ID、production、`execution_profile=local_sapi`、Run、stage、cache key、resultを再照合し、次工程へ渡すartifact ID／相対path／bytes／SHA-256をallowlistします。top成功条件は4 child成功、Remotion recipeとassembly／QCの期待尺一致、選択variantのmaster、QC report 3件、`technical_verdict=pass`です。top resultの`children`は`narration | timeline | assembly | qc`だけを返します。停止／timeout／失敗時は現在のchildを`cancel_and_wait`で退役させてからtopをterminalにし、後続stageをqueueしません。

UIはtop jobを2秒間隔でpollingし、narration→timeline→assembly→QCの進捗、各childのjob／attemptとcache hit、完成master、QC passを表示します。完了Jobがある場合のrecipe尺は未入力フォームではなくimmutableなJob結果を優先します。HTTP応答が曖昧な場合は、送信前snapshotになく、production、kind、stage、`local_sapi` profile、canonical payload SHA-256、request keyが一致するdirect Detailed Jobだけを受理済みとして扱います。告知専用のnarration alignment fieldが一つでもあるJob、既知Job、digest欠落・不一致Jobでは曖昧状態を解除せず、自動再送を止めます。この経路はローカルSAPI、Remotion、FFmpeg／ffprobeだけを使い、H3／ComfyUI、MiniMax API、ElevenLabs、secret、費用approvalへ到達しません。

## 一括生成（`local_pipeline`）

`一括生成`タブは、固定されたlocal-only制作を一つのRunとして実行する入口です。HTTP境界は`POST /api/productions/{production_id}/execute-local-pipeline`で、同じproductionと同じcanonical pipeline keyの要求はDB claimにより既存Run/top jobを再利用します。新しいRunを乱立させず、failed／interruptedの同じRunでは未完了stageのattemptをretryします。親jobの明示停止は登録済みchild jobとprocessの終了を待ってからterminalへ遷移します。Studio通常終了時はshutdown intentをComfyUI childへ伝えてlocal pollingだけを停止し、provider側の生成は継続します。

Runには`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`の6 requested stageを記録します。`captions`はナレーションから導出され、実行される5 stageはComfyUI動画生成→Windows SAPIナレーション→生成動画1本を全尺1カットにするtimeline→FFmpeg assembly→technical QCです。ComfyUI childはGPU lane、SAPI／timeline／assembly／QC childはdefault laneへ送られ、pipeline laneが順序と依存関係を管理します。

bodyは次のpublic fieldだけを受け付けます。workflow graph、model path、ComfyUI endpoint、output path、FFmpeg option、ElevenLabs設定は指定できません。`seed`は引用符なしのJSON integerとして0〜9,223,372,036,854,775,807を送り、UIは`seed_decimal`を優先して正確に表示します。

```json
{
  "workflow_preset": "minimax_h3_t2v_official_q4_v1",
  "prompt": "A calm cinematic portrait, subtle natural motion.",
  "seed": 0,
  "segments": [{"text": "ここにナレーション本文"}],
  "rate": 0,
  "include_captioned": true,
  "caption_style_preset": "shorts_ja_large_v1",
  "variant": "captioned"
}
```

`voice`と`pronunciations`は任意です。`local_pipeline`では有料APIを呼ばず、ElevenLabs契約、API key、cost approvalは不要です。SAPI、ComfyUI、FFmpeg、ffprobeだけを使い、最終masterとQC reportをStudio artifactとして記録します。

raw prompt/scriptはSQLite、event、job metadataへ複製しません。prompt hash、文字数、seed decimal、stage lineageだけを公開記録します。ただし、明示的に生成する`workflow.json`、`timings`、`manifest`などのartifactにはcontentが含まれ得るため、監査exportや共有前に確認してください。

実行中はUIが2秒間隔でjob／stage attempt、provider task、公開`pipeline_continuation` stateを再読込します。pipeline概要は真のtop jobに固定し、復旧用video childが古いtop表示を上書きしません。provider照合日時はbackendが実際にComfyUIを確認した`last_observed_at`だけを表示し、画面のpolling日時では代用しません。復旧したvideo generationが成功すると、schema v7台帳がsource job/attemptと同じRunを`ready`へ原子的に確定し、background coordinatorが新topを一件だけ自動投入します。video stageはそのsourceを含む物理検証済みcache chainだけを使い、欠損・改ざん・lineage不一致なら`pipeline_recovered_video_unavailable`で停止してComfyUIへ再POSTしません。SAPI、timeline、assembly、QCは通常どおり後続し、完了後はmaster artifact、clean／captioned variant、technical QC verdictを確認できます。`active`、`waiting_provider`、`ready`、`continuing`、`cancel_requested`中はフォームをロックします。

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

ローカル動画生成のHTTP境界は`POST /api/runs/{run_id}/execute-local-video-generation`です。bodyは次の3 fieldだけを受け付けます。workflow graph、model path、ComfyUI endpoint、出力path、step数などは公開requestから変更できません。seedはJSON integerとして0〜9,223,372,036,854,775,807を受け付け、UIはrequestで引用符なしdecimalを送り、responseでは`seed_decimal`を優先してJavaScriptの整数丸めを避けます。同一Run／cache key／payload digestのactive requestは同じjob／attemptを返します。復旧停止中のtaskは`POST /api/provider-tasks/{provider_task_record_id}/resume`へ厳密な空object `{}`を送り、同じ永続taskだけを再照合します。`recovery_blocked`に加え、exact markerまたは過去の提出時刻がある`ambiguous`も照合対象にできますが、新しいpromptはPOSTしません。`cancel_requested`では同じUUIDへの`GET /api/jobs/{id}`と対象cancel endpointだけを使って再照合し、生成用`POST /prompt`へは到達しません。未提出と永続記録から証明できればローカルでcancelを確定し、providerがrunningならcancelを再要求、404／一時的な照合不能なら`cancel_requested`を保持して重複送信をブロックします。terminal taskと提出証拠のない`ambiguous`はfail closedで拒否します。

```json
{
  "workflow_preset": "minimax_h3_t2v_official_q4_v1",
  "prompt": "A calm cinematic portrait, subtle natural motion.",
  "seed": 42
}
```

prompt本文はproviderへ提出したexact graphを保全する`workflow.json`には含まれます。SQLite、job/run/eventの公開metadataには複製せず、`prompt_sha256`と`prompt_chars`だけを残します。再起動に必要なexact requestだけは現在のWindowsユーザー用DPAPI暗号文として`provider_tasks`へ保存し、公開APIと監査snapshotには出しません。terminal成功／確定失敗で暗号文を消去し、callback後のDB永続化失敗や送信結果不明では暗号文とmarkerを保持します。providerがterminal failureを返した場合はmarker自体へ失敗stateをfsyncしてからDBへ反映します。DPAPIが利用できない場合は平文保存せず自動復旧を停止します。`workflow.json`を含む監査exportや共有前には本文が含まれる前提で確認してください。

ローカルWeb画面収録のHTTP境界は`POST /api/runs/{run_id}/execute-local-screen-capture`です。bodyは次の4 fieldだけを受け付けます。URLは明示的な`http://127.0.0.1:<port>/...`だけを許可し、userinfo、fragment、暗黙port、制御文字、非loopback hostを拒否します。初期navigationだけでなくredirect、subresource、WebSocket、popupも同じloopback portの境界内へ閉じます。

```json
{
  "url": "http://127.0.0.1:8765/",
  "duration_ms": 5000,
  "settle_ms": 500,
  "actions": [
    {"type": "scroll", "at_ms": 1500, "delta_y": 720}
  ]
}
```

`duration_ms`は1,000〜30,000、`settle_ms`は0〜10,000、`actions`は最大16件です。`click`ではselector、`press`ではallowlist済みkeyを指定できますが、任意JavaScript、cookie／storage state、header、download、persistent profile、browser flag、output pathは指定できません。raw URL、path、query、selectorはjob／attempt／eventへ保存せず、origin、長さ、query有無、SHA-256だけを監査metadataへ残します。raw requestはworker staging内の一時JSONだけで受け渡し、公開前に削除します。

Playwrightは毎回freshなChromium contextを使い、ページ音声を収録しません。生WebMを固定MP4へ変換してfull decodeとfresh ffprobeを行い、7成果物がすべて検証できた場合だけdirectory、job、attempt、artifact、eventを成功として確定します。screen captureだけのRunはnarration／assemblyを自動実行しません。`local_playwright` Runではtimelineを明示実行できますが、assembly／qcは影響工程として計画に残るだけで、このprofileからは実行しません。

### Windowsネイティブ収録のcapability foundation

Windowsデスクトップとsystem audioの実収録はまだ未実装です。先行する安全な基盤として、`setup-studio.ps1`は外部NuGet packageを持たない`native/windows-capture-helper`を`net8.0-windows` Release DLLへbuildします。`画面収録`タブの「収録せずに環境を確認」は、session保護された次のendpointへ厳密な空objectだけを送ります。

```http
POST /api/capabilities/windows-capture/inspect
Content-Type: application/json

{}
```

backendは固定DLLを`dotnet ... doctor --json`でshellなし・stdinなし・10秒／64KiB上限付きで起動します。helperは`IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eConsole)`で既定の再生endpointを取得し、共有modeの`IAudioClient`をloopback flagで初期化できるかだけを検査します。`IAudioClient.Start`やbuffer取得は呼ばず、device ID／device name／マイクを列挙または返しません。併せて固定FFmpegのdevice一覧から`gdigrab`だけを検査します。診断responseはtool hash、既知boolean、固定reason codeだけで、絶対path、生stderr、device情報を含みません。

この操作はRun、Job、attempt、artifact、event、DB cacheを作らず、画面・音声sampleを取得、保存、送信しません。public responseは`capture_execution_enabled=false`、`actual_capture_performed=false`を固定し、UIもこのどちらかまたはhelperの`recording_started`がtrueなら結果表示をfail closedにします。2026-08-30の開発機では`gdigrab`と既定render loopback初期化がともに利用可能でしたが、これは実収録の成功を意味しません。

将来の実収録requestは既に別のvalidatorで、`schema_version=1`、`target=primary_display`、`audio_mode=default_render_loopback`、`cursor_mode=hidden`、1,000〜30,000ms、画面とsystem audioの別々のliteral `true`確認だけへ閉じています。path、HWND、window title、device ID、マイク、任意FFmpeg引数は受け付けません。ただし実行service／HTTP route／profileは意図的に接続していないため、このvalidatorだけで収録は開始できません。

カット編集のHTTP境界は`POST /api/runs/{run_id}/execute-local-timeline`です。bodyは次の形だけを受け付け、pathやFFmpeg設定は受け付けません。

```json
{
  "clips": [
    {"video_artifact_id": "art_<32hex>", "start_ms": 0, "end_ms": 1500}
  ]
}
```

## Remotion詳細timeline

既存の`高速ハードカット`はそのまま利用できます。fade、素材音量、固定テロップ、映像補正を確認するときだけ、カット編集画面で`Remotion詳細preview`を選びます。`timeline`をrequested stageに含む`local_sapi`、`local_comfyui`、`local_playwright` Runが対象です。画面上で登録済み動画を追加し、trim、順番、音量、fade、テロップ、カットごとの映像補正presetを設定すると、`@remotion/player`がbackend renderと同じtracked compositionでbrowser previewを表示します。ただしPlayerは原素材を直接表示し、renderer前の固定FFmpeg鮮明化を再現しません。preview確認だけではrender jobを開始せず、`Remotion詳細previewをレンダー`を押したときに明示実行します。`h3_low_res_sharp_v1`の効果は完成artifactで確認してください。

HTTP境界は`POST /api/runs/{run_id}/execute-remotion-timeline`です。jobの`kind`とstage attemptの`provider`は`local_remotion_timeline`、stageは既存と同じ`timeline`です。bodyはschema v1の次のfieldだけを受け付けます。

```json
{
  "schema_version": 1,
  "clips": [
    {
      "video_artifact_id": "art_<32hex>",
      "start_ms": 0,
      "end_ms": 5000,
      "volume_percent": 100,
      "visual_preset": "h3_low_res_sharp_v1",
      "transition_to_next": {"type": "fade", "duration_ms": 500},
      "overlay": {
        "text": "生成AIを、もっと身近に。",
        "start_ms": 500,
        "end_ms": 3000,
        "position": "bottom",
        "style_preset": "shorts_ja_large_v1"
      }
    },
    {
      "video_artifact_id": "art_<32hex>",
      "start_ms": 0,
      "end_ms": 4000,
      "volume_percent": 80,
      "visual_preset": "preserve_v1",
      "transition_to_next": null,
      "overlay": null
    }
  ]
}
```

制約は登録済み動画1〜16件、各clip 50ms以上、完成尺最大60,000ms、素材音量0〜100%、fade 50〜2,000msです。fadeは隣接する両clipより短くし、最後のclipには指定できません。テロップはclipごとに0または1件、50ms以上、trim後clip内、最大200文字／4行です。位置は`top`／`center`／`bottom`、styleは`shorts_ja_large_v1`だけです。`visual_preset`は互換既定`preserve_v1`または`h3_low_res_sharp_v1`だけで、省略した旧payloadは`preserve_v1`として読めます。任意path、URL、React component、CSS、font、browser flag、environment variable、free-form Remotion props、映像filter、鮮明化強度、CRFは指定できません。

`h3_low_res_sharp_v1`は、幅1080未満・高さ1920未満、両辺64px以上、幅÷高さ0.50〜0.625、Lanczos `cover`で算出した拡大後300万画素以下の低解像度縦長素材だけに使えます。workerはこの上限をFFmpeg起動前に検証し、Remotionへ渡す前にそのclipの必要frame区間を24fpsのframe境界で切り出します。その後、Lanczos `cover`で1080×1920へ拡大・中央cropし、輝度へだけ固定5×5／0.25のunsharpを適用します。色差の鮮明化量は0です。テロップはこの後にcompositionで描くため、文字をunsharpに巻き込みません。`preserve_v1`は従来どおり原素材をprivate stagingへcopyします。鮮明化は存在しない細部を再生成する超解像ではなく、拡大時の見かけの甘さを弱く補うだけです。

renderは画面収録と同じbrowser FIFO laneに入り、setup済みPlaywright Chromiumを再利用してconcurrency 1で動きます。Source Fidelity v2ではRemotionの中間frameをPNG、H.264をCRF 16／x264 mediumへ固定します。出力は1080×1920／24fps、H.264／yuv420p、AAC 48kHz stereoで、`remotion-preview.mp4`、`remotion-timeline.json`、`render-report.json`、`ffprobe.json`、`manifest.json`の5成果物を`outputs/studio/runs/<run>/remotion_timeline/<cache>/`へ保存します。入力をprivate stagingへcopyまたは固定前処理し、元素材hashを前後に検査して、full decode、fresh ffprobe、manifest自己hash、exact artifact集合を満たした後だけdirectoryをatomic publishし、job／attempt／artifactをatomic登録します。cache keyと監査summaryにはSource Fidelity v2の出力policyと各clipのpresetを、render reportとmanifestには固定前処理policyと実際の適用計画・結果も含め、旧policyのcacheを再利用しません。同じschema、recipe、入力hash、composition、script、package、browser、FFmpeg／ffprobe identityの成功cacheだけを再利用します。

固定出力policy IDは`remotion-source-fidelity-v2`、固定前処理policy IDは`lanczos-cover-luma-unsharp-v1`です。presetと固定policyはcache、監査summary、render report、manifestへ、各clipの適用計画・結果はrender reportとmanifestへ記録します。

`h3_low_res_sharp_v1`は追加のFFmpeg pre-trim／encodeを行うため、`preserve_v1`よりCPU時間、処理時間、一時storage I/Oが増えます。特に複数clipへ指定した場合は順に前処理します。効き具合と追加時間を完成artifact／render reportで確認し、補正が不要なカットは`preserve_v1`を選んでください。

`setup-studio.ps1`は`npm ci`後、Remotion 5 packageとPlaywrightから辿れる実`node_modules` dependency closureを検査し、通常fileのbytes／SHA-256を集約したattestationをignored `studio/node_modules/`へ生成します。通常dependencyに加え、installed optional dependencyとpeer dependencyも対象です。symlink／junction相当の解決先変更／special fileは拒否します。doctorとworker開始時にinstalled treeを再計算し、pathを含まないclosure digestとpackage・file・bytes数をcache tool identityへ含め、render終了後にも再照合します。不一致時は成果物をpublishせず、setupの再実行を求めます。

`remotion-timeline.json`は再調整と監査再現のため、指定したテロップ本文をrecipe内へ平文保存します。`render-report.json`は本文を複製せず、`content_policy.raw_overlay_text_in_report=false`と`recipe_contains_overlay_text`を分けて記録します。job、event、manifestにも本文は複製しませんが、監査exportにはtimeline artifact自体が含まれ得るため、ZIPやJSONを共有する前に本文を確認してください。

重要: `volume_percent`はRemotion詳細preview内の素材音声へ反映します。assemblyでは閉じた`audio_mix_preset`を選びます。互換既定`narration_only_v1`はsource audioを選択ナレーションへ置換します。`source_under_narration_v1`はpreviewへ焼き込まれた音声をさらに25%へ下げ、ナレーション100%と混ぜて固定peak limiterを通します。後者はsource audioがちょうど1 streamあり、素材音声とナレーションがそれぞれ非無音である場合だけ実行し、欠落／全編無音は自動代替せずfail closedです。任意gain、BGM、sidechain duckingは現在の境界外です。

queue投入と直後のDB補償が連続失敗した場合も、background coordinatorは当該JobManagerが記録したexact top IDだけを次scanで補償し、DPAPI保護済み入力から同じRunを再開します。投入後例外でworkerが実際にdequeueした場合はcontextと未完了eventをworkerへ残し、cancel／shutdownから見失いません。利用者cancelが補償と競合した場合は、active topまたはexactなterminal／`ready`世代を`cancelled`へ閉じ、暗号文を消去して自動再開をfenceします。明示cancel intentはshutdownよりstickyで、DB確定までexact job IDをworker contextとは別にprocess内保持します。caller／worker双方のDB書込みが一時失敗してworkerが退役した後も、coordinatorが保留IDを公平なbounded batchで再試行し、その間は全`ready`世代の投入を安全側で停止します。ready一覧取得後も新topのDB CAS直前にJobManager lock内でfenceを再確認します。終了中に新しい明示cancelが到着した場合は当該closeを未完了にして次writerへ渡し、DBへ永続化できるまでworkspace lockを保持します。shutdown完了は同じlock内で確定し、その後の新規破棄要求は拒否します。shutdownの継続意図ではこの破棄経路に入りません。内部childのtimeout/errorは利用者cancelとは分離し、child workerを退役させてからtopをfailureへ確定します。

PNG中間frameを非並列encodeするため、必要な一時diskは尺に比例します。workerは開始前に「`duration_in_frames × 1080 × 1920 × 4 × 1.25`＋raw出力2GiB＋正規化出力2GiB＋安全余白1GiB」へ、`preserve_v1`の実source bytesまたはsharpカットごとの最大2GiBを足して検査します。source staging後は実staged bytesを計測し、残容量をframe／出力／余白分に対して再検査します。いずれかが不足すれば`insufficient_scratch_space`でNode起動前に停止します。Remotion／Chromiumの`TEMP`／`TMP`／`TMPDIR`はatomic stageの`work/scratch`へ固定し、Node自身も3値、実効tmp、空directory、symlinkなしをbundling前にattestします。stageは成功、失敗、cancelの全終了経路で再帰削除します。Windowsの一時lockにはread-only属性解除と0.15／0.30／0.60秒のbounded retryを行い、それでも残る場合は`remotion_stage_cleanup_failed`で失敗を公開します。`render-report.json`と`manifest.json`には`png-frame-scratch-v1`、実staged bytes、両検査の必要／空きbytes／判定、Node attestationを記録します。

## セットアップと起動

前提:

- Windows PowerShellまたはPowerShell 7
- Python 3.10以降。既存の`.venv`があれば優先して使用
- Node.js 20.19以降の20系、または22.12以降とnpm。Node.js 21と22.0〜22.11はVite 8の対応範囲外
- MP4変換と検証に使うFFmpeg／ffprobe

初回とfrontend更新後:

```powershell
.\setup-studio.ps1
```

setupは`studio/package-lock.json`へexact pinしたPlaywright `1.62.1`と、`remotion`／`@remotion/player`／`@remotion/renderer`／`@remotion/bundler`／`@remotion/transitions`の同一version `4.0.517`を`npm ci`で導入し、既定では対応Chromiumを取得します。browser install／doctor時はruntimeと同じく`NODE_OPTIONS`、`NODE_PATH`、任意`PLAYWRIGHT_BROWSERS_PATH`、`REMOTION_*`を外します。続けて`playwright_doctor.mjs`がpackage、browser binary、実launchを、`remotion_doctor.mjs`が5 packageのexact version、rendererが再利用するChromium executable、基本runtimeを検査します。欠落やrevision不一致ではfail closedにします。すでにbrowserを用意した検証だけは`-SkipBrowserInstall`を使えますが、doctor自体は省略しません。

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

この`test-video`経路はWindows SAPI、FFmpeg、ffprobeだけを使い、Remotion詳細timelineは呼ばないため、API契約、API key、課金承認は不要です。公開品質の声を比較するときだけ、ElevenLabsの契約とAPI key登録を行い、最短原稿1回の費用上限を承認してpaid smokeへ進みます。API keyはチャットへ貼りません。StudioのRemotion利用は個人利用を前提にしています。利用主体、組織規模、用途、配布形態が変わる場合は、詳細timelineの実行や成果物公開の前に現行licenseを確認してください。依存ごとの条件は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

## 保存構造

```text
studio/                         React / Vite frontend source
tools/studio/                   Python backendと索引・監査処理
productions/<production-id>/    Git管理する既存の制作仕様と台帳
outputs/productions/<id>/       ignoredの画像・音声・動画・詳細QC
outputs/studio/
  studio.sqlite3                schema v7のSQLite検索索引、Studio記録、provider task／pipeline／detailed-test claim台帳
  events/<scope>/<id>.jsonl     hash chain付きevent mirror
  secrets/<provider>.dpapi      Windowsユーザーに紐づく暗号化secret
  external-submissions/elevenlabs/<production>/<cache>/.submission-unknown.json
                                課金POST前に作るproduction/cache単位の再送防止marker
  external-submissions/comfyui/<production>/<cache>/.submission-unknown.json
                                事前発行prompt IDを含め、ComfyUI POST前にfsyncする再送防止marker
  runs/<run>/video_generation/<cache>/
                                generated-video.mp4 / workflow.json / ffprobe.json / manifest.json
  runs/<run>/screen_capture/<cache>/
                                screen-capture.mp4 / playwright-raw.webm / first-frame.png / last-frame.png / capture-report.json / ffprobe.json / manifest.json
  runs/<run>/narration/<cache>/ narration.wav / captions.srt / timings.json / manifest.json
  runs/<run>/timeline/<cache>/  timeline-preview.mp4 / timeline.json / ffprobe.json / manifest.json
  runs/<run>/remotion_timeline/<cache>/
                                remotion-preview.mp4 / remotion-timeline.json / render-report.json / ffprobe.json / manifest.json
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
  ├─ Announcement recipe
  │    ├─ Immutable exact version / parent / clone source
  │    └─ Execution link -> Detailed top Job / Run / Revision
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
- 告知recipeは例外的に、再調整できるexact canonical JSONを`announcement.recipe.saved` eventへBase64で保持します。Base64は暗号化ではなく、event mirrorと監査exportから復号できるため、秘密を入力しません。
- eventは`previous_hash`と`event_hash`を持ち、起動時と追記時にJSONL mirrorの全chainを検査します。破損時はhealthとUIをdegraded表示にし、該当mirrorを監査ZIPから除外します。これはローカル改変の検出であり、第三者に対する電子署名ではありません。
- hash chainの途中改変や不正な追記は検出しますが、正しいevent境界で末尾だけを削る操作は、外部固定済みtailがなければ単独では検出できません。重要時点の監査ZIPと`.zip.sha256`を別媒体にも保管してください。
- SQLiteはUI検索とMVP操作用です。既存のtracked台帳を置き換えません。
- Studio外で既存台帳が更新された場合は「索引を更新」で再読込します。
- SQLite再構築時、Studio生成artifactは完全metadataを持つ`artifact.created`または成功済みstage/job resultから候補を得て、`outputs/studio/`内の非symlink通常file、stable ID、bytes、SHA-256、既存ID/path衝突を再検証できたものだけ復元します。1件2 GiB、合計16 GiB、10,000件が上限です。旧イベントがIDとkindしか持たず完全metadataが他にもない場合、欠落・改変・symlink・path逸脱がある場合は推測で復元しません。

MVPは変更種別から`requested_stages`と再利用工程を計画します。ローカルnarrationのcache keyは正規化segment、voice、rate、発音置換、Windows SAPIに固定した実装versionから作り、成功attemptと4成果物のpath、bytes、SHA-256がすべて一致するときだけ再利用します。外部TTSはprovider、固定model/output、voice、全voice setting、seed、正規化segment、実装versionからcache keyを作り、同じproduction内の成功attempt chainを物理成果物のownerまで辿って4成果物とmanifest自己hashを再検証します。課金POST直前にはproduction/cache identityごとの永続markerを排他的に作り、成功成果物の確定後だけ削除します。通信結果が曖昧な失敗や中断でmarkerが残った場合は別Runを含む自動再送をfail closedで止めます。

ローカルComfyUIはprompt hash、seed、固定workflow、4 model、2 runtime lock、3 repository revision、FFprobe identity、出力policyからcache keyを作ります。GPU lane内で同じproductionの成功attempt chainを物理ownerまで辿り、4成果物、manifest自己hash、fresh ffprobeを再検証します。新規taskではStudioがUUIDを事前発行し、schema v7の`provider_tasks`とfsync済みmarkerへ保存した後、同じ値をComfyUIの`prompt_id`へ渡して応答完全一致を要求します。Studio再起動時は旧jobを`interrupted`、旧attemptを`failed(process_interrupted)`として保持し、ownerを解放した同じtaskへ新しいattempt/jobをCASで1件だけ追加します。marker、暗号化request、payload digest、cache key、Run、固定runtime、`GET /api/jobs/{id}`を照合し、既知taskは再POSTしません。明示cancelはprovider taskを`cancel_requested`へ移す処理とjob／attemptの中断を同じSQLite transaction・同じ時刻で確定し、暗号文とmarkerを残します。再起動または手動再照合では同じUUIDへのGETとtargeted cancelだけを行い、terminalを確認してから暗号文を消去します。IDなし旧marker、通常復旧時の404、runtime不一致、改変は`ambiguous`または`recovery_blocked`で止め、cancel照合時の404は`cancel_requested`を保持します。

ローカルPlaywright画面収録は正規化timing／actionsと、URL／selectorのhash、固定network policy、Node／Playwright／Chromium／worker script／FFmpeg／ffprobeの実体hash、固定出力policyにrequestごとのnonceを加えてcapture keyを作ります。ページ内容が同一である保証はないため、並行requestや過去の成功captureをcontent cacheとして再利用しません。成功時とartifact restore時は7成果物のexact集合、manifest自己hash、各file bytes／SHA-256、MP4のfresh ffprobeとfull decodeを再検証します。

ローカルFFmpeg timelineは順序付きartifact ID、trim、入力bytes／SHA-256、固定出力policy、解決済みFFmpeg／ffprobeの実体versionとbinary SHA-256からcache keyを作り、同じproduction内の成功attempt chainと4成果物を再検証します。Remotion詳細timelineはschema v1 recipe、入力bytes／SHA-256、Source Fidelity v2の固定出力policy（visual preset、Lanczos／luma-only unsharp policy、PNG中間frame、CRF 16を含む）、tracked composition／model／render script、Remotion package、Playwright Chromium、Node、FFmpeg／ffprobeのidentityからcache keyを作り、exact 5成果物、manifest自己hash、full decode、fresh ffprobeを再検証します。前処理policyは監査summary、render report、manifestにも記録し、旧policyのcacheと分離します。ローカルassemblyはsource動画、WAV、SRT、字幕preset、字幕有無、閉じた音声mix preset、音声・出力方針、FFmpeg/ffprobeの実体versionとbinary SHA-256からcache keyを作り、manifest自己hash、登録済みartifact、実fileを再検証します。ローカルQCはassembly attempt、選択variant、masterのhash／bytes、期待尺、QC policy、FFmpeg/ffprobeの実体identityからcache keyを作ります。cache再利用時も対象mediaと成果物を再検証します。字幕または音声mixだけを変更した場合は映像、timeline、ナレーションを再利用し、合成とQCだけを新runで実行できる土台です。

`local_pipeline`は全入力のcanonical keyをschema v7 DB claimへ束ね、同一production・同一入力のRun/top jobを再利用します。正規化requestはDPAPI暗号文だけを保持し、動画成功時はsource job/attemptをcheckpointします。shutdown／crash後にproviderまたはcheckpointが成功済みなら`ready`へ移し、単一coordinatorが同じRunへ新topをCASで一件だけ投入します。checkpoint付きvideo childは指定sourceを含むcache chainと物理artifactを検証し、再生成へfallbackしません。親cancelはchild job/processのjoinを待ち、後からproviderが成功してもclaimを`cancelled`へ閉じます。各local stage、provider terminal／video checkpoint、top terminal／claimは対応するatomic transactionで確定し、UIはstage lineage、continuation state、最終master／QCを再読込できます。

告知recipeは独立したmedia cacheを持たず、exact revisionを既存Detailed payloadへcompileします。compile済みpayloadが同一ならDetailedのcontent-addressed claimをそのまま再利用し、recipe名だけ異なるcloneからも同じRun／top Jobへ到達できます。ただし、各recipe versionとJobを結ぶ`announcement.recipe.executed` eventは別に残します。top Jobの新規作成または再利用とexecution linkを同じSQLite transactionへ入れ、片方だけがproduction historyへ現れる状態を拒否します。

queue admission補償は失敗を実際に観測したexact IDに限定し、worker dequeueとのhandshakeで正常なqueued／running jobを誤停止しません。別processの所有権はprivateな`_active` mapから推測せず、起動時のDB interruptionとworkspace単一起動lockを正本にします。

## ログ、成果物、監査

Studioでは次を別々に扱います。

| 種類 | 記録例 |
|---|---|
| event | 索引、revision/run、job、費用承認、告知recipe version／execution linkの時刻、状態、hash chain |
| artifact | path、bytes、MIME、origin、version、取得できた場合のSHA-256 |
| run cost | 見積、通貨、承認上限、承認／却下履歴 |
| stage attempt | stage、attempt番号、cache key、状態、所要時間、provider、task ID、実費、timing source |
| status / approval | 台帳由来のtechnical・creative・public status、run費用上限の承認／却下と理由 |

ローカルSAPI attemptは`provider=windows_sapi`、`provider_task_id=null`、`actual_cost=0`、`timing_source=wav_frames`として記録します。ローカルComfyUI attemptは`provider=comfyui`、`provider_task_id=<prompt-id>`、`actual_cost=0`、`timing_source=ffprobe`、prompt SHA-256、文字数、seed／`seed_decimal`として記録します。ローカルPlaywright attemptは`provider=local_playwright`、`provider_task_id=null`、`actual_cost=0`、`timing_source=ffprobe`として、originとhash化したtarget/action監査値だけを記録します。ElevenLabs attemptは`provider=elevenlabs`、`provider_task_id=<request-id>`、`character_cost=<header値またはnull>`、`actual_cost=null`、`timing_source=elevenlabs_alignment`として記録します。`character-cost`はproviderの課金文字量でありUSD実費ではありません。ハードカットtimeline attemptは`provider=local_ffmpeg_timeline`、Remotion詳細timeline attemptは`provider=local_remotion_timeline`／`timing_source=remotion_frames`、ローカルassembly attemptは`provider=local_ffmpeg`、ローカルQC attemptは`provider=local_ffmpeg_qc`として、いずれも`provider_task_id=null`、`actual_cost=0`を記録します。QCは解析不能なtool/process failureだけをjob失敗とし、解析が完了して検査に不合格ならjob／attempt成功と`technical_verdict=fail`を併記します。API応答にないUSD実費を推測せず、将来のprovider請求照合で確定するまでは未確定のまま保持します。

監査exportは、SQLiteを1つのread transactionで固定した時点の記録をZIPへまとめる派生成果物です。event mirrorもそのsnapshotと一致する検証済みprefixをmemoryへ固定してから格納します。一般テキスト副生成物はZIP格納前に既知の秘密情報patternをredactし、変更対象をpackage manifestの`redacted_text_files`へ記録します。安全な構造化処理を保証できないYAML/YML、INI/CFG/CONF、TOML、CSV/TSV、XML、HTML/XHTML、SVGは`structured_text_requires_local_review`として除外します。未知形式と外部archiveも`unsupported_artifact_kind`として除外します。Studio生成のSRT、timings、manifestは既定で含め、WAVは他のaudio/video/imageと同様に`include_media=true`のときだけ含めます。監査ZIP自身は再帰的に含めません。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain末尾、検証できず除外したmirrorを記録し、ZIP閉鎖後に全entryを再検証します。ZIP全体のSHA-256は隣接sidecarへ保存します。DB snapshot後に元artifactが更新された場合、artifact metadataの時点とcopy時点は異なり得るため、ZIP内実体については`archive_entries`のbytes/hashを正本とします。監査ZIPが存在するだけで公開権利や人の通し試聴が確認済みになったとは扱いません。

告知recipeのevent payloadには完全なcanonical JSONがBase64で入ります。構造化redactionがevent payload全体を秘密なしへ変換する保証はなく、Base64は既知の秘密情報patternを隠してしまう場合もあります。したがって「後で監査時に消す」運用にはせず、入力時点で秘密を含めないことを境界とします。

## セキュリティ境界

- HTTPは`127.0.0.1`だけにbindします。
- 変更系POSTは起動ごとのsession tokenとloopback Originで保護し、tokenを永続ログへ保存しません。認証拒否時は上限内の宣言済みrequest bodyだけを破棄してから接続を閉じ、WindowsでもHTTP 403を安定して返します。長さ不正・上限超過bodyは読み込まずfail closedにします。読取GETはloopback bindとHost検査を境界とします。
- 同じworkspaceへ2つのStudio serverを起動しません。Windowsではworkspace内lock fileを`LockFileEx`でsystem-wideに排他保持し、同一process／別process／別sessionの2台目を起動時に拒否します。全responseは`Connection: close`で1 request／1 handlerへ限定します。終了時はlistenerとrequest解析中socketだけを閉じ、解析済みnon-daemon HTTP handler、background provider recovery、job worker lane、SQLite interruption writerをdrainしてからlockを解放します。未解析requestはWindowsでも1秒のinactivity timeoutで有界化し、解析済みservice処理にはこの時間制限を適用しません。worker／writerのtimeoutまたはclose例外時は再試行またはprocess終了までlockを保持するため、旧writerと新processのSQLite多重writerを許しません。
- frontendへAPIキーを返すendpointはありません。
- 告知recipeの保存APIは大見出し、ナレーション、発音置換をexact revisionとして返し、production eventにもBase64で保持します。これはローカルの再調整・監査機能であってsecret storeではありません。秘密を入力せず、監査ZIPを外部共有する前にevent mirrorも確認します。
- 外部TTSのprofile、narration工程、正の見積、費用承認、literal booleanの`confirm_billable=true`をすべて検証してから、外部contract module、秘密鍵、HTTP workerへ到達します。どれか1つでも欠ければprovider codeを読み込まずfail closedにします。
- ElevenLabsのproduction endpointは`https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps`へ固定し、redirectを拒否します。test用endpoint注入はliteral loopback originだけに限定します。API keyは`xi-api-key` header以外へ入れず、URL、cache key、manifest、例外、job payloadへ保存しません。
- provider応答、MP3、alignment、WAV、metadata、segment文字数、総文字数、総尺、timeoutへ上限を設けます。HTTP／processの生出力やprovider bodyを公開エラーへ含めません。
- 課金POST前に永続markerを作ります。providerが受理した可能性を否定できないtimeout、5xx、切断などは`external_submission_unknown`として停止し、同じproduction/cache identityを自動再送しません。これは曖昧状態で重複課金しないためのfail-closed境界です。
- ComfyUI endpointは`http://127.0.0.1:8188`へ内部固定し、公開requestから上書きできません。環境proxyを無効化し、redirect、過大応答、非loopback URLを拒否します。新POSTとmarker-linked resumeの直前に`/system_stats`を読み、`run-local.ps1 -Profile official_q4`（任意の`-NoBrowser`）が作るworkspace内main/output、listen/port、ComfyUI 0.31.0、PyTorch 2.13.0+cu130、Python 3.12、Dynamic VRAM、custom-node disable／exact GGUF allowlistを含む完全なargvを照合します。未知・重複・equals形式の引数、Emergency／Turbo／precision変更、model path redirectを拒否し、`runtime/ComfyUI/extra_model_paths.yaml`も存在またはsymlinkなら拒否します。
- ComfyUIのruntime lock 2 fileはLF byte列とSHA-256を固定し、ComfyUI、ComfyUI-GGUF、MiniMax H3 Turboの3 checkoutはexact HEADと非ignored fileを含むclean状態を要求します。Windowsでは新しいPOST attemptごとに4 modelをwrite/delete共有なしで開き、その同じhandleからfull SHA-256を計算してpublish後まで保持します。実行中の書換え・削除・置換と、既にwriterが開いているmodelを拒否します。非Windowsだけは物理file identity付きprocess cacheを使います。historyが返すMP4は送信graphへ注入した出力prefix配下の規定basenameだけを受け付け、workspace内の別MP4を生成結果として登録しません。
- Playwright画面収録はcanonicalな`127.0.0.1` URLと明示portだけを許可し、全HTTP requestを同一scheme／host／portへroute制限します。proxy環境、`NODE_OPTIONS`、`NODE_PATH`、任意`PLAYWRIGHT_BROWSERS_PATH`をworkerへ継承せず、service worker、download、popup、WebSocket、persistent profileを無効化します。raw URLとselectorはargv、SQLite、event、manifest、公開errorへ入れず、専用staging JSONだけで渡します。browser laneのprocess treeは既存のdeadline／cancel registryで停止し、公開directoryは全検証後だけatomic renameします。
- `.env`拡張子、`.env.*`、credential/secret key file、DPAPI secretは索引対象外です。JSON/JSONLは構造化redactionし、一般テキストはAuthorization、Basic/Bearer、Cookie、API key、署名値など既知patternをbest-effortでredactします。
- artifact配信は登録済みかつ許可されたroot内のfileだけを対象にします。
- narration workerは文字列をPowerShell commandへ展開せず、run配下の専用一時directoryにUTF-8 JSONとして渡します。一時fileは同じWindowsユーザー／workspace ACLを信頼境界とし、処理後に削除します。SAPI preflightと合成PowerShellはどちらもjobのprocess registryへ登録し、preflightは100ms周期でcancelを確認します。tracked helperだけを起動し、戻り値はprovider、task ID、実費、cache key、exact artifact path/name/kind/MIME/bytes/SHA-256のallowlistで検証してから登録します。
- timeline requestは`clips`だけ、その各要素は`video_artifact_id`、integerの`start_ms`、`end_ms`だけを受け付けます。1〜32カット、各50ms以上、合計30分以内、各source 2 GiB以下、入力合計4 GiB以下に制限し、同じproductionの登録済み・available・video artifactだけをhash再検証します。任意path、transition、filter、codec、FFmpeg optionは受け付けません。
- timeline workerは入力を専用一時directoryの`clip-00.mp4`形式へ固定名copyして整合性を再検証し、`shell=False`、bounded stdout/stderr、cancel可能なFFmpeg／ffprobeだけを実行します。出力は1080×1920、24fps、H.264／yuv420p、video-only、ハードカットへ固定します。累積時間から各カットのframe予算を決め、その枚数だけを連結するframe-budget v2により、短いカットでも境界frameの重複と最後のカット欠落を防ぎます。4成果物をatomic publishし、cache hitでもexact artifact集合、manifest自己hash、実file hash、fresh ffprobeを再検証します。
- Remotion詳細timeline requestは`schema_version=1`と`clips`だけを受け、各clipのfieldを登録済みartifact ID、integer trim、0〜100の音量、nullableなfade、nullableな固定テロップ、任意の`visual_preset=preserve_v1 | h3_low_res_sharp_v1`へ閉じます。visual presetがない旧payload／詳細一括／告知recipeは`preserve_v1`へ正規化します。1〜16カット／最大60秒、fade 50〜2,000ms、テロップ最大200文字／4行、位置3種、`shorts_ja_large_v1`だけを許可します。任意path／URL、code、CSS、font、browser／environment option、free-form props、filter文字列、鮮明化強度、CRFを受け付けません。
- Remotion workerは`preserve_v1`入力をprivate stagingへ固定名copyします。`h3_low_res_sharp_v1`は幅1080未満・高さ1920未満、両辺64px以上、幅÷高さ0.50〜0.625、cover拡大後300万画素以下の低解像度縦長sourceだけを許可し、条件外はFFmpeg起動前に拒否します。必要frameへ先にtrimしてから固定Lanczos cover 1080×1920、luma-only unsharp 5×5／0.25、chroma 0をテロップ前に適用します。双方で元素材bytes／SHA-256をrender前後に確認します。exact `4.0.517` package、tracked composition／script、setup済みPlaywright Chromium、FFmpeg／ffprobe、Source Fidelity v2 policyをtool/cache identityへ含め、browser FIFO lane／render concurrency 1、PNG中間frame、CRF 16で実行します。1080×1920／24fps、H.264／yuv420p＋AAC 48kHz stereoの5成果物をfull decode／fresh ffprobe後にatomic publishし、DB登録失敗時は公開directoryと部分登録をcleanupします。PlayerはFFmpeg前処理を再現せず、鮮明化は完成artifactで確認します。この処理は欠落detailを復元せず、CPU／時間／一時I/Oを追加消費します。
- assembly workerは登録済みartifact IDからbackendが解決したworkspace内の通常fileだけを受け取り、`subprocess`を`shell=False`で起動します。SRTは厳密にparseし、ASCII brace/backslashを全角化した固定style ASSへ変換してoverride tagを無効化します。字幕styleは`studio_default_v1`または`shorts_ja_large_v1`の閉じたpresetだけを許し、raw ASS、font path、filter、任意styleを受け付けません。音声は`narration_only_v1`または`source_under_narration_v1`の閉じたpresetだけを許し、任意gain／filterを受け付けません。前者はsource audioを置換し、後者はsource 25%＋narration 100%を48kHz stereoへ揃えて固定limiterでmixします。mix時はsource audio 1 streamと両入力のpeakがそれぞれ−60 dBを超えることを独立検証します。短い音声だけを無音paddingし、映像より250msを超えて長いナレーションは暗黙にtrimせず拒否します。
- assembly入力は2 GiBの動画、128 MiBのWAV、8 MiBのSRT、30分、最大16,384px／64メガpixelを上限とします。出力はH.264 / yuv420p / AAC / MP4へ固定し、source timingを再encode時に保持します。`master-clean.mp4`、任意の`master-captioned.mp4`、`ffprobe.json`、`manifest.json`を一時directoryからatomic publishします。
- QC request bodyは`assembly_attempt_id`と`variant`だけを許可します。指定attempt自身は選択中Runの成功済みassemblyに限定します。content-addressed assembly cacheの実fileが同じproduction内の先行Runにある場合は、その`cache_source_attempt_id` chainを循環なしで終端まで辿り、全attemptのcache key、入力hash、artifact ID/path/bytes/SHA-256が一致したときだけ意図的なcross-run再利用として許可します。backendが対象artifactと期待尺を導出し、workspace内通常file、symlink不使用、bytes／SHA-256一致を検証してから、固定argv・`shell=False`のFFmpeg/ffprobeへ渡します。
- QCはprobe成功、MP4、video 1本＋audio 1本、H.264／yuv420p、AAC 48 kHz stereo、container/video/audio各尺、期待尺、full decode、全編無音ではないことを独立checkとして記録します。短尺mediaでは無音検出windowを媒体尺に合わせて1msまで縮めます。codec不一致や壊れたmediaは解析完了の`technical_verdict=fail`であり、creative、rights、public release statusを自動変更しません。tool timeoutなど解析自体が完了しない場合だけattempt／jobを失敗にします。
- QC cacheは登録済みartifact、実file、manifest自己hashだけでなく、対象masterの再解析結果も再照合します。改変したreportを自己hashごと作り直してもpassへ偽装できません。
- attemptとbackground jobはjobをworker queueへ入れる前に同一ID関係を永続化し、`stage.attempt.job_linked` eventとしてmirrorへ残します。同じリンクの再適用はeventを重複させません。schema v1〜v6の既存DBは起動時にschema v7へtransactionalに移行し、event mirrorから再構築してもattempt側の履歴Job IDを復元します。jobs検索表そのものは再構築対象ではないため、DB再構築後の完了状態・成果物はattempt記録を正本として表示します。`local_pipeline`のRun/top job claim、child lineage、公開continuation state、source job/attempt、再開回数、DPAPI暗号化済み正規化request、ComfyUIのprovider task state／CAS owner／暗号化resume payload、およびDetailed Test Videoのcontent-addressed Run/top claimをschema v7のDB transactionで管理します。
- cache hit時も各stageのmanifest自己hash、期待される全成果物のhash、DBに記録済みbytes/hashを再検証します。QCでは対象masterのfresh解析も行います。欠落、symlink、path逸脱、改変、worker契約違反は再利用または成功扱いにしません。
- 異常出力によるメモリ圧迫を抑えるため、1 segmentのWAVは32 MiB、結合WAVは128 MiB、総尺は30分を上限としてfail closedにします。これは短尺制作向けの安全上限で、長尺音声配信を保証する値ではありません。
- worker-backed stageの成功時は、jobとリンク済みstage attemptおよび両success eventを同じSQLite transactionで確定します。ComfyUIではprovider task、4 artifact row、version、`artifact.created` eventも同じtransactionへ含め、terminal successより先に見せません。artifact登録、success commit、通常worker error、job／attemptリンク不一致、provider lineage欠落、原子的completion envelope欠落／不一致でもjob／attemptを同じfailure transactionで閉じます。停止との競合は「provider task／job／attemptがsuccess」または「job=`interrupted`かつstage attempt=`failed(process_interrupted)`、provider taskは次回復旧可能」のどちらかに限定します。Studio通常終了ではComfyUI provider jobをcancelせずpollだけを停止します。ユーザーの明示cancelはjob=`interrupted`、attempt=`failed(process_interrupted)`、provider task=`cancel_requested`を同じtransaction・同じ時刻で確定し、同じUUIDへのGETとtargeted cancelだけで再照合します。FFmpeg／ffprobe／PowerShell subprocessは従来どおり子process treeごと停止します。DBがbusyでもprocess停止を先行・並行し、worker laneとSQLite interruption writerの終了を確認します。
- browser内でinline表示するのはraster image、audio、videoだけです。対応済み`.json`、`.jsonl`、`.log`、`.md`、`.txt`、`.srt`、`.ass`、`.vtt`は`attachment`とCSP sandboxを付け、redact済み内容だけを返します。不正JSON/JSONL、その他の設定・source code・markup・未知形式・外部archiveはMVPではHTTP 415で拒否します。Studio自身が生成・検証した監査ZIPだけはdownloadできます。
- 監査ZIPへ含める対応済みdocument、log、subtitleは秘密情報をredactし、変更対象と格納後hashをmanifestへ記録します。redactionは秘密がないことの証明ではないため、外部共有前に人がpackage manifestと内容を確認してください。
- 外部TTSのaudit summaryはallowlistしたprovider/model/cache/request ID/character costと成果物metadataだけを保存し、本文、API key、Authorization、生provider responseは保存しません。後続adapterでもrequest/response、署名付きURL、Cookieは保存前にredactします。
- API契約後もキーをチャット、Git、SQLite、コマンドライン引数へ貼りません。
- 課金対象工程のrunには正の見積額を必須とし、ElevenLabsではprovider/model/送信本文/設定と上限承認を実行前に表示します。承認後にpayloadを変更しても同じ確認として扱わず、実行requestごとに明示確認を必須にします。

Studioは個人用loopbackツールです。LANからの攻撃面を作らないため、`0.0.0.0`やLANへ公開しないでください。

## チャットとの分担

1. ユーザーがチャットで制作や修正を依頼する。
2. CodexがStudioのローカルAPIまたはCLIを通して新しいrevision/runを作る。
3. Studioが索引・監査job、ローカルComfyUI動画生成、Playwright画面収録、ローカル／ElevenLabs narration、FFmpeg／Remotion timeline、assembly、QC attempt、成果物、費用計画、ログを保持する。後続workerも同じ台帳へ保持する。
4. ユーザーはStudioで候補や中間成果物を確認する。
5. Codexは完了、失敗、承認待ちなど節目だけを確認する。
6. 既存素材から早く告知を作る場合は`告知動画`タブで3シーンを保存・previewし、exact revisionを一括実行する。Studioはrecipe history、Detailed child lineage、master、QCを保持する。
7. 新しいH3素材から始める場合は`local_pipeline`の`一括生成`タブでprompt、seed、script、音声、字幕preset、variantを確認して、固定local-onlyの6 requested／5 executed stageを明示実行する。StudioはComfyUI→SAPI→one-clip timeline→assembly→QCの順序、child job、cache、artifact hash、technical verdictを保持する。単独の`local_comfyui`、`local_sapi`、`elevenlabs_tts`は工程単位の再実行や比較に使い、local pipelineではElevenLabs、MiniMax API、費用approvalを使わない。

現MVPは索引・監査jobに加えてローカルComfyUI動画生成、Playwright Web画面収録、`local_pipeline`一括生成、告知動画テンプレート、ローカル／ElevenLabs narration、FFmpegハードカット／Remotion詳細timeline、assembly、technical QCもバックグラウンド実行します。profile単位では、`local_playwright`はscreen_captureとtimelineだけを実行可能とし、assembly／qcは影響工程として計画に残しますが実行しません。dashboard全体のhealth/job一覧は15秒間隔、実行中の画面収録と両timeline、pipeline top job／child、および選択RunのComfyUI provider taskとpipeline continuation stateは2秒間隔で取得し、ジョブ状態と進捗率を表示します。告知動画は軽いJob一覧を2秒間隔、production detailを初回と3回ごとのおおむね6秒間隔で取得し、曖昧な実行応答はfresh execution linkのexact Job GET、続く同一immutable revisionの1回限定冪等再送で復旧します。複製clone IDはsource identityから決定的に導出してintent固有のversioned `localStorage` keyへPOST前に保存し、画面移動／再読込／複数tabでも同じIDを再利用します。exact cloneの成功または版履歴照合まで保持し、timeout／4xxでは消さず、壊れた保存領域ではPOST前に停止します。production detailの一時取得失敗でも最後に確認できたフォームと復旧stateを保持します。専用browser laneはChromium captureとRemotion renderをdefault laneから分離し、両者をFIFOで直列実行します。専用pipeline laneはGPU childをdefault childから分離します。Studio再起動後にComfyUI生成が成功へ復旧した場合は、単一coordinatorが同じRunの新topを一度だけenqueueし、検証済み動画cacheからSAPI以降を自動継続します。チャットは節目だけを確認することで監視トークンを抑えられます。Studioへ記録済みの状態はチャットを閉じてもローカルに残ります。

ローカルナレーション画面は操作性のため1行2,000文字・合計50,000文字を先に警告します。backendの正本上限は1 segment 4,000文字・合計100,000文字・100 segmentです。外部TTSもbackendで同じsegment／総文字数上限を適用し、さらにvoice ID、全voice setting、seed、provider応答、媒体size／尺を検証します。UIを迂回したrequestにも必ず適用します。

2026-08-24時点では、ElevenLabs transportとFFmpeg境界をmockしたE2Eで、承認済みRun、job／attempt、4成果物、provider metadata、成功cache、ローカルassembly入力まで確認しています。実ElevenLabs APIへのpaid smokeは行っていません。最初の実送信は、ユーザーがAPI keyをローカル登録し、対象voiceと見積上限を確認したうえで、短い日本語原稿を1回だけ明示承認して行う検証項目です。

同日の`test-video`実制作E2Eでは、既存15秒clean masterからWindows SAPI 3 segment、1カットtimeline、captioned assembly、technical QCを86.315秒で完走しました。完成MP4は1080x1920／24fps／15.000秒、H.264／yuv420p + AAC 48kHz stereo、4,524,600 bytes、SHA-256 `3A4A4EDB170F2A1D826231772BD56D1F998B7B31A1DA03C6D8C6A898C1F4A92E`で、technical QC 10/10 passです。同じrecipeの2回目は11.893秒で、narration／timeline／assemblyをcache利用し、QCは新しいattemptとして再解析してpassしました。この結果はローカル技術経路の証拠であり、音声の自然さ、creative、人物・素材の権利、公開可否を自動承認するものではありません。

2026-08-28の告知動画実制作E2Eでは、先に5,000ms×3のmechanical baselineを生成し、technical QCはpassしたものの、目視でナレーションが先頭から連続しCTA音声がMESSAGE映像中に終わる同期不良を検出しました。この成果物は実用受入には使っていません。24fpsの個別frame丸めを含む`announcement_scene_starts_v1`導入後、同じ3素材を5,167ms／5,167ms／5,166msで再実行したjob `job_b640f88bf1fa4e5597610892002b6ecb`は約229.2秒で完走しました。完成masterは`outputs/studio/runs/run_4316184c9dae489d8f72df30a56c67d4/assembly/FB904FAEDC7FC103A6A9AA373B237A42008018057B1629F842902DC40950AFF2/master-captioned.mp4`、1080×1920／24fps／15.000秒、H.264 High／yuv420p + AAC-LC 48kHz stereo、4,469,223 bytes、SHA-256 `A7958A2D0A1D326B8C609768B0824ED1B353F6C2B25B7323DA14FF92358E609F`で、full decodeとtechnical QC passを確認しました。SRTとWAV実frame由来の3開始は0ms／4,917ms／9,833ms、終了は3,313ms／7,945ms／12,036msで、1秒／6.5秒／11秒の代表frameでもHOOK／MESSAGE／CTAと字幕の一致を目視確認しています。同じrev 2の再実行は約3.19秒で同じRun／top Job／既存execution linkへdedupeし、名前だけ異なるcloneも約3.15秒で同じRun／top Jobへdedupeしながら別execution eventを残しました。これはscene同期、再利用、媒体技術条件の証拠であり、訴求内容、人物へのテロップ重なり、音声の自然さ、権利、公開可否は引き続きhuman review対象です。

2026-08-25のローカルComfyUI受入では、Python自動テスト247件を実行し、246件合格＋non-Windows専用race test 1件をWindowsでskipしました。固定API graph、GPU workerでのcache key再束縛、完全なruntime argv、`extra_model_paths.yaml`拒否、Windowsのmodel handle保護、loopback-only transport、送信marker、production-wide cache、GPU lane、artifactとjob／attemptの原子的確定、seedの64-bit保持、Shorts字幕presetを確認しています。稼働中ComfyUIのread-only照合ではversion、path、repository状態は一致しましたが、安全引数導入前に起動された現在のlistenerは完全なcanonical argvを満たさず、`invalid_comfyui_runtime`として意図どおり拒否されました。この実装受入では新しいpromptをPOSTせず、実GPU生成と完成映像の目視確認はまだ行っていません。

## 現行local_pipeline検証状態

2026-08-25 root最終検証では、Python全344件を実行して343件合格＋non-Windows専用race test 1件をWindowsでskipし、frontend 42/42、production buildも成功しました。fake-backed統合で`local_pipeline` request schema v4（SQLite schema v6）、`POST /api/productions/{production_id}/execute-local-pipeline`、専用pipeline lane、6 requested／5 executed stage、DB-level dedupe、same-run retry、parent-child cancellation wait、外部TTS非到達、atomic artifact確定、QC pass、Studio UIの2秒pollingを確認しました。自動継続回帰では、Studio再起動後のprovider成功から同じRunへ新topを一度だけ投入し、8件の同時再送をdedupeすること、source job/attemptを固定したcache-only動画再利用、cache欠損・改ざん・lineage不一致でprovider task／marker／ComfyUI `POST /prompt`へ進まないこと、明示cancel後は継続しないこと、暗号文改ざん、queue投入＋補償の二重失敗、enqueue後例外、worker退役中のDB一時障害、ready CAS、shutdown中のlate cancel競合を安全側に処理することを確認しました。終了・復旧回帰では、atomic `cancel_requested`、未送信／running／404／terminalの同一UUID再照合、解析済みHTTP handlerのdrain、未解析partial requestの有界遮断、`Connection: close`、終了しないworker時のworkspace lock保持と再試行、worker lane／SQLite interruption writerを残りshutdown deadline内でdrainし、期限超過時はlockを保持することを確認しました。成功topの再利用時は5 childのexact lineageと、captioned既定では全19件（clean-onlyでは18件）のartifactをDB metadata・物理bytes・SHA-256で再検証し、最終または中間artifactの欠損／改変／I/O raceを同じRunの新top jobで自己修復します。この検証ではComfyUIへ新規promptをPOSTしていないため、実GPU一括完走時間、強制終了→再起動→同一task回収からpipeline完走までの実機E2E、完成映像の目視品質は未確認です。

2026-08-26には、固定`official_q4`（公式INT8 ConvRot＋Q4 text encoder）で実GPU `local_pipeline`を通常完走しました。H3 rawは480×864／24fps／124 frames／5.167秒、H.264＋AAC 32kHz stereo、H3生成7分06秒、一括pipeline全体7分24秒でした。SAPI、one-clip timeline、captioned assembly、technical QCまで同じRunに記録され、外部API key／課金は不要でした。強制終了→再起動→同一task回収の実機E2Eと、複数promptにわたるcreative品質は引き続き未確認です。

## 現行Playwright画面収録の検証状態

2026-08-25にPlaywright `1.62.1`／Chromium `151.0.7922.34`を使い、Studio自身の`http://127.0.0.1:8765/`を対象に実Web収録E2Eを行いました。描画待ち500ms、1秒時点で720px scroll、指定尺3秒のrequestから、run `run_cbaa1ead33fb4d02be586dcc48cc75be`、job `job_1decf170bbc341f49ff1b4f3e423819b`、attempt `attempt_7e150e65276d4471a42847f4fa100f7b`が成功しました。最終MP4は1080×1920、24fps、H.264／yuv420p、video-only、3.000秒、389,197 bytes、SHA-256 `B959499D011224674EE8D9746CB95FD8E8C762294482D43F53477C49F0637A07`で、full decodeとfresh ffprobeを通過しました。7成果物は`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/screen_capture/4021F9F3CA5A228EC8F22456234A9C80853AAA85277B9525CC85ED9C8DF1B73E/`へatomicに登録し、始点／終点PNGの縦viewportとscroll差分を目視確認しました。

続けて収録MP4を同じ`local_playwright` Runのtimelineへ実投入し、job `job_47286fd1eef8480f86e4520289632ac7`／attempt `attempt_6a0bb3b50d934d55bc9336837eebd43a`が成功しました。`timeline-preview.mp4`は1080×1920、24fps、video-only、3.000秒、362,527 bytes、SHA-256 `17B9FD76E1170BB88A2EC64E66ACA88FF75F0FFD777596E8FA6E4273E5B6B25C`で、4成果物を`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/timeline/F45A9955F5A7AA8FCD4F1A2B3241E4FA1166470015C15A732C661AD9110982BB/`へatomic登録しました。これにより、画面収録artifactを既存カット編集へ渡す実素材連携まで確認済みです。

自動検証はPython全359件中358件合格＋Windows上のnon-Windows専用1件skipを確認し、その後追加したbrowser lane実行中progress可視性、DB atomic commit失敗cleanup、publish後cancel cleanupの3件も個別合格しました。関連するbackend／実ブラウザ統合123件も再実行して全件合格しています。frontend 50/50、production build、`setup-studio.ps1 -SkipBuild -SkipBrowserInstall`のbrowser doctorも成功しています。実Playwright回帰テストでは別loopback portへのsubrequest遮断、絶対path／raw URL token非漏洩、output policy改ざん拒否、publish後のcancel／検証失敗cleanup、収録・変換・検証のprogress通知も確認しています。最新版serverでの再受入ではjob `job_be88c3cb938e4166aef35eb8a873ea83`が`preflight`→`recording`→`transcoding`→`verification`→`publishing`→`registration`→100%完了をAPIへ返し、7成果物を登録しました。この受入はloopback Web viewport収録の証拠であり、Windowsデスクトップ／ネイティブアプリ、system audio、microphone、外部Webサイト、既存ログインsession、30秒超の収録を保証しません。

Run契約修正後の再受入では、run `run_c0745a922f814b67b1c45f7fbac8fd80`が`requested_stages=[screen_capture,timeline]`、rerun planの`affected_stages=[screen_capture,timeline,assembly,qc]`を返すことを確認しました。同Runのjob `job_66c8ae62688044a59cb3ca0a14207aec`も2.000秒、1080×1920、24fps、H.264、video-onlyのMP4と7成果物を登録し、manifestに絶対pathを残していません。

## Source Fidelity v2の15秒実レンダー検証

2026-08-29に、既存H3実写系素材3本（各480×864）を各5,000ms、全カット`h3_low_res_sharp_v1`、日本語テロップ3件で合成する15秒の代表試験を最終コードで実施しました。実Remotion／Chromiumは360 frameを131.891秒で完走し、完成MP4は1080×1920／24fps、H.264 High／yuv420p＋AAC-LC 48kHz stereo、15.000秒、9,360,318 bytes、SHA-256 `C61E4376FE4F5F546BA360FC897DD65010CB2C76FF7C014BBBA3727C5D6ECC66`です。独立ffprobeとvideo／audio全decodeも成功しました。

`png-frame-scratch-v1`は開始前に15,543,640,064 bytes必要／459,701,411,840 bytes空き、source staging後に9,101,189,120 bytes必要／459,691,950,080 bytes空きとして両方passし、実staged sourceは9,516,039 bytes、Nodeのscratch containment attestationも`true`でした。完了後は`.remotion-*` stageが0件、公開cacheが1件で、現行validatorによる5成果物の完全再検証も`cache_hit=true`で成功しました。成果物と監査文書は`outputs/studio/runs/run_source_fidelity_15s_v2/remotion_timeline/FC152CB19676FC698114F3B2AF8076FCD56C5933E508D4DCAC51B2D47FB2A018/`にあります。この結果は15秒の代表素材に対する証拠で、最大60秒の実レンダー完走を保証しません。60秒については1,440 frameのPNG reserve `14,929,920,000` bytesと、staging後必要量 `20,298,629,120` bytesの計算境界を自動テストしています。

## 次段階

実装済み: Windows SAPI adapter、ElevenLabs Multilingual v2 `with-timestamps` adapter、文字alignmentからのsegment字幕、費用承認＋payload確認gate、成功cache＋曖昧送信marker、provider request ID／character cost／未確定USD欄、発音置換、固定公式INT8＋Q4 ComfyUI graph、閉じたruntime argv／model／live process照合、Windows model handle保護、GPU FIFO lane、pre-issued UUID、schema v7 provider task／pipeline continuation／detailed-test claim、DPAPI resume／pipeline request payload、Studio起動時の自動照合、新attempt追記、CAS重複防止、手動resume UI、復旧済み動画のcache-only自動継続、atomic `cancel_requested`＋GET-only targeted cancel再照合、provider／job／attempt／artifactの原子的確定、isolated Chromiumによるloopback Web収録、登録済み動画1〜32カットのtrim／並べ替え／ハードカットpreview、schema v1のRemotion詳細timeline、共通compositionのPlayer preview、fade／素材音量／固定テロップ、Source Fidelity v2の`preserve_v1 | h3_low_res_sharp_v1`、pre-overlay固定Lanczos／luma-only unsharp、PNG中間frame／CRF 16、cache／監査／report／manifest policy、旧recipeの`preserve_v1`互換、exact 5成果物、画面収録とRemotion renderを直列化するbrowser FIFO lane、FFmpeg clean／captioned master、`shorts_ja_large_v1`字幕preset、schema v2 / `local-ffmpeg-qc-v2` / `technical-qc-mp4-v2`のIntegrated loudness／true peak／黒画面hard checkと長い静止warningを含むローカルtechnical QC、ffprobe／manifest、stage attempt/cache。専用`local_pipeline` lane、6 requested／5 executed stage、DB-level Run/top-job dedupe、same-run failed／interrupted retry、parent-child cancellation wait、local stage artifactのatomic completion、Detailed Test Video v1のSAPI→Remotion→assembly→QC一括、固定字幕preflight、content dedupe、same-run retry、2秒UI監視、およびHOOK／MESSAGE／CTA告知recipeのCAS保存、immutable exact version、複製、Detailed compile、atomic execution link、fresh exact Job復旧と1回限定の同一revision冪等再送。HTTP／worker／SQLite writerのdrain成功時だけworkspace lockを解放する単一writer境界。

1. Windowsデスクトップ／ネイティブアプリ、system audioを扱う画面収録worker
2. 実ComfyUIでのStudio強制終了／再起動→`local_pipeline`自動継続E2E、ComfyUI自体の再起動でtaskが404になった場合と旧IDなしmarkerの手動判断・破棄UI
3. ElevenLabs請求情報とのUSD実費照合と、必要に応じた別TTS provider adapter
4. frame/timecode精度の連動比較、指定cutだけの再実行、cut/timecode単位コメントとcreative／rights human review UI
5. 外部送信素材の秘密情報検査、監査bundle署名

実装済み範囲を超える工程はRun計画内の未実行項目として表示し、`running`や`complete`とは記録しません。
