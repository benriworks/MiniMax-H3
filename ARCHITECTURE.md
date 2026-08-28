# Architecture

## 目的と境界

このチェックアウトは、上流MiniMax H3のソース/モデル資料に、次の3経路を加えています。

1. Windows上のComfyUIによるローカル **H3-Base-FL2VA** 実行
2. Python標準ライブラリだけを使うMiniMax Video Generation V2 API操作
3. 制作案件、run、artifact、ログ、承認、監査export、ローカルSAPIと承認制ElevenLabsナレーション、固定workflowによるローカルComfyUI動画生成、isolated Chromiumによるloopback Web画面収録、登録済み動画のローカルFFmpegハードカット／Remotion詳細timeline、既存素材からの詳細テスト動画一括実行、HOOK／MESSAGE／CTAの告知動画recipe、音声・字幕合成、完成masterのローカルtechnical QCを扱うloopback専用 **MiniMaxH3 Studio MVP**

ローカル経路はH3-Baseの768px短辺キャンバスを対象にします。H3-Context-IRとH3-Regenerate-2Kはオープンソースreleaseに含まれないため、2K/Context-IR/Regenerateはローカル実行境界の外側で、公式API側の責務です。
[MiniMax H3公式の構成説明](https://github.com/MiniMax-AI/MiniMax-H3#model-architecture)と
[Recommended Workflow](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)が一次情報です。

処理経路の図は[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)に分離しています。

## 構成要素と責務

| 構成要素 | 責務 | 状態 |
|---|---|---|
| `setup-local.ps1` | Python 3.12 venv、固定Git commit、固定Python依存を導入。dirty repoを保護 | tracked |
| `runtime-lock.json` | ComfyUI/ComfyUI-GGUF/Turbo custom node commit、Python target、torch3種、lock fileを定義 | tracked source of truth |
| `requirements-local-lock.txt` | Windows AMD64 / CPython 3.12で確認したtorch以外のPython依存をexact pin | tracked |
| `download-models.ps1` | license確認後、固定HF revisionからprofileモデルを取得し、容量・byte数を検査 | tracked |
| `model-manifest.json` | model role、repo/revision/path、byte数、SHA-256、license/source URL | tracked source of truth |
| `run-local.ps1` | doctorをgateとしてloopback ComfyUIを起動し、VRAM modeを排他的に構成。custom nodeをprofile別allowlistへ閉じ、対応workflowの手動open先と開始・終了時system metricsを表示 | tracked |
| `tools/system_metrics.ps1` | CPU使用率/温度、RAM、NVIDIA GPU使用率/温度/VRAM/電力をbest-effort取得。保存や連続監視はしない | tracked |
| `runtime/ComfyUI/` | ComfyUI本体、custom node、モデル、Comfyの一時状態 | untracked/ignored |
| `workflows/minimax_h3_t2v_lowvram.json` | GGUF向けT2V、0.2MP、4秒指定、20 steps | tracked |
| `workflows/minimax_h3_t2v_lowvram_turbo.json` | 任意のGGUF + Turbo LoRA経路、0.2MP、5秒指定、simple / 6 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` | 品質優先のQ3 diffusion + Q4 text encoder + Turbo経路、0.4MP、5秒、simple / 8 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_official_q4.json` | 公式INT8 ConvRot diffusion + Q4 text encoder、0.4MP、5秒、simple / 20 steps | tracked / 0.6MP・5秒・20-step Emergency run確認済み。tracked 0.4MP既定は未検証 |
| `workflows/minimax_h3_t2v_official_q4_turbo.json` | 公式INT8 ConvRot + Q4 + Turbo LoRA、0.4MP、5秒、simple / 8 steps、merge | tracked / unverified on target hardware |
| `workflows/api/minimax_h3_t2v_official_q4_v1.json` | Studio API専用の公式INT8 ConvRot + Q4 text encoder、約480×864、124 frames / 24fps、20-step固定graph。prompt、seed、出力prefixだけを内部注入 | tracked source of truth |
| ComfyUI Template Library | `official` profile用の公式T2V JSON | installed Python package/runtime |
| `tools/local_doctor.py` | hardware/resource、core lock、model、profile別workflowを非破壊検査 | tracked |
| `run-api.ps1` / `tools/h3_api.py` | `.env`読込、V2 submit/status/wait/download、preflight/security gate | tracked |
| `setup-studio.ps1` | frontend依存、exact pinしたPlaywrightとRemotion `4.0.517`一式を導入し、固定revisionのChromiumをinstall／launch検査、Remotion doctor、Python backend module、frontend buildを検証 | tracked |
| `run-studio.ps1` | `127.0.0.1`限定でbackendとbuild済みUI、または開発用Viteを起動 | tracked |
| `studio/` | React / Viteによる制作一覧、案件詳細、artifact preview / A-B比較、event、cost、approval、ローカルSAPI／ElevenLabsナレーション、固定ComfyUI動画生成とprovider task復旧、Playwright画面収録、`local_pipeline`一括生成と自動継続state、既存素材向け`詳細一括`と2秒top-job監視、HOOK／MESSAGE／CTA告知recipeの保存・複製・preview・一括実行と低頻度detail照合、FFmpegハードカット編集、共通Remotion compositionを使う詳細timeline Player preview、字幕preset付き合成、technical QC UI | tracked source。`node_modules/`と`dist/`はignored |
| `tools/studio/announcement_video.py` | exactな告知recipe schema v1、3シーン／10〜20秒／見出し／ナレーション制約、250ms fadeと固定overlay位置、Detailed Test Video v1へのcompile | tracked source of truth |
| `tools/studio/` | production索引、schema v7 SQLite、artifact配信、run/approval、stage attempt、永続provider task／local video request claim／detailed-test content claim、告知recipeのevent由来immutable version／CAS／clone／execution link、default/GPU/browser/pipeline分離job lane、background再起動照合、`local_pipeline` continuation台帳／enqueue-only coordinator／cache-only動画checkpoint、Detailed Test Video v1 orchestrator／dedupe／same-run retry、Windows SAPI narration/cache、ElevenLabs `with-timestamps` contract／worker／課金gate／cache、固定ComfyUI contract／worker／cache／再起動照合、loopback-only Playwright capture contract／Chromium worker／FFmpeg MP4変換、FFmpegハードカットtimeline/cache、閉じたRemotion schema／worker／cache、字幕preset付きFFmpeg assembly/cache、FFmpeg/ffprobe technical QC/cache、`test-video`直列orchestrator、DPAPI secret、audit export API | tracked |
| `tools/studio/sapi_synthesize.ps1` | UTF-8 JSON fileからSystem.Speechへ安全に入力し、segment WAVを出力するローカルhelper | tracked |
| `outputs/studio/` | schema v7 SQLite、hash chain付きevent JSONL mirror（告知recipeのexact Base64 revision／execution linkを含む）、暗号化secret、外部送信marker、監査ZIP、run別動画生成／Playwright画面収録／ナレーション／FFmpeg timeline／Remotion timeline／詳細一括のchild lineage／合成／technical QC成果物 | untracked/ignored |
| `.env` | MiniMax／ElevenLabs API keyと任意MiniMax base | untracked/ignored secret |
| `outputs/` | `run-local.ps1`およびCLIの生成物 | untracked/ignored |

## 再現性モデル

### 既定setup

`setup-local.ps1` は `runtime-lock.json` の3つのGit SHAへdetached checkoutし、PyTorch cu130の3 exact versionと `requirements-local-lock.txt` を導入します。fresh clone、既存clean mismatch、既存dirtyを区別します。3つ目は任意profileが使うTurbo custom nodeですが、ComfyUI process内で自動importされるcodeなので、利用有無にかかわらず固定・検査します。

- fresh: 通常cloneでworking treeを展開した後、固定SHAへcheckout
- clean mismatch: 必要なcommitをfetchし、固定SHAへdetached checkout
- dirty + 固定SHA一致: repository mutationをskipしwarning
- dirty + mismatch、またはdirty treeでの`-Update`: mutationせず停止
- `-Update`: clean repositoryでだけremote HEADと未固定Python依存へ明示更新

`-Update` 後はcore lockと不一致になり得ます。doctorの `Locked core runtime matches` は、3 Git HEAD、Python 3.12、torch/vision/audioだけを照合します。`requirements-local-lock.txt` 全行とinstalled distributionの完全一致を表すものではありません。

### モデル

model downloaderは `model-manifest.json` のHF revisionとremote pathを使います。取得直後はexact byte数を検査し、full SHA-256はdoctorの `--hash` で明示実行します。モデル本体はGit管理せず、`runtime/`配下に置きます。

## ローカル生成データフロー

1. operatorがprofileを選び、licenseを確認します。
2. downloaderがHugging Faceからprofileごとの4 model artifact、またはTurboを含む5 artifactを `runtime/ComfyUI/models/` へ配置します。
3. doctorがtotal/free VRAM、total/available RAM、pagefile、disk、core lock、VAE chunked I/O、custom node、モデル、workflow wiringを検査します。
4. `run-local.ps1` が開始時system metricsを取得し、`127.0.0.1` のComfyUIをforeground起動します。`--disable-all-custom-nodes`を常に付け、通常profileは`ComfyUI-GGUF`だけ、Turbo profileは固定Turbo nodeも追加して明示allowlistします。profileは検査対象を選びますが、workflowをUIへ自動ロード・切替しません。
5. operatorがlauncherの `Open manually:` 表示に従い、lowvramではtracked GGUF workflow、lowvram_turboではQ2 Turbo workflow、lowvram_q4_turboではQ4 Turbo workflow、officialではTemplate Libraryの公式T2V、official_q4ではtracked stock 20-step、official_q4_turboではtracked Turbo 8-stepを明示的に開きます。
6. ComfyUIがtext encoder、FL2VA diffusion model、任意のTurbo adapter、video/audio VAEを読み、videoとstereo audioをMP4にmuxします。
7. ComfyUI終了後、launcherが終了時system metricsと経過時間を表示します。通常の生成物出力先は `outputs/` です。

ComfyUIの公式モデル配置とloader名は
[ComfyUI MiniMax H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)に準拠します。

## Profileとworkflowの対応

| Profile | Diffusion / text encoder | Workflow loader | 必ず使うworkflow |
|---|---|---|---|
| `lowvram` | community FL2VA Q3_K_M / Qwen Q2_K | `UnetLoaderGGUF` / `CLIPLoaderGGUF` | tracked `workflows/minimax_h3_t2v_lowvram.json` |
| `lowvram_turbo` | `lowvram` + Larryvrh v4 step600 EMA | GGUF loaders + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_lowvram_turbo.json` |
| `lowvram_q4_turbo` | community FL2VA Q3_K_M / Qwen Q4_K_M + Larryvrh v4 step600 EMA | GGUF loaders + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` |
| `official` | Comfy-Org int8 convrot / nvfp4 awq | `UNETLoader` / `CLIPLoader` | Template Library → Video → MiniMax H3 T2V |
| `official_q4` | Comfy-Org int8 convrot / community Qwen Q4_K_M | `UNETLoader` / `CLIPLoaderGGUF` | tracked `workflows/minimax_h3_t2v_official_q4.json` |
| `official_q4_turbo` | official_q4 + Larryvrh v4 step600 EMA | `UNETLoader` / `CLIPLoaderGGUF` + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_official_q4_turbo.json` |

profileとworkflowを交差させません。doctorもprofileに応じて別のworkflow contractを検査します。

Turbo workflowは `UnetLoaderGGUF → MiniMaxH3TurboLoRA → BasicScheduler / BasicGuider` と `MiniMaxH3TurboSampler → SamplerCustomAdvanced` のlinkを固定します。Q2版はstrength 1.0、`low_vram=true`、0.2MP、simple / 6 steps、Q4版は同じmerge条件で0.4MP、simple / 8 stepsです。doctorは内側loaderだけでなく、実行時に優先されるtop-level subgraphのdiffusion/text/video VAE/audio VAE overrideをexact比較し、ResolutionSelectorのwidth/height linkも検査します。作者がQ3 GGUFを対応baseとして明示していないため、両経路ともexperimentalです。non-Turbo `lowvram` とQ2 Turboをfallbackとして残し、bypassはdefaultにしません。

Q4 text encoderは [`realrebelai/MiniMax-H3_GGUFs` の固定revision](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/blob/daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7/qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf)から取得し、`CLIPLoaderGGUF` のtype `minimax` で読みます。固定[ComfyUI-GGUF loader](https://github.com/city96/ComfyUI-GGUF/blob/6ea2651e7df66d7585f6ffee804b20e92fb38b8a/loader.py)とcoreはQwen3VL text encoderとMiniMax H3の50層構成を扱えますが、generic Qwen3VL vision/mmproj対応は上流の[Issue #471](https://github.com/city96/ComfyUI-GGUF/issues/471) / [PR #473](https://github.com/city96/ComfyUI-GGUF/pull/473)で未統合です。このprofileはH3 T2V conditioningだけを対象とし、汎用I2V/mmproj対応を主張しません。

GGUF mergeではcustom nodeの汎用canaryが見るmodule `weight_function` ではなく、ComfyUI-GGUFの `GGMLTensor.weight.patches` にpatchが保持されます。このため `weight_patched=False` はQ3経路ではfalse negativeになり得ます。受入証拠はLoRA nodeのaccepted patch数/AdaLN injection、sampler完走、同seedでLoRAを外したA/B出力差を組み合わせます。

ComfyUI本体は[PR #15446](https://github.com/Comfy-Org/ComfyUI/pull/15446)のmerge commitへ固定しています。`MiniMaxH3VideoVAE.comfy_has_chunked_io`をcore VAE wrapperが認識し、video全体のpixel-space copyを保持せずtemporal chunk単位でencode/decodeします。モデルやworkflowの置換は不要です。これはpeak VRAM/RAM削減であり、sampling高速化とは別の責務です。

## VRAM mode

`run-local.ps1` は共通引数としてpreviewなし、pinned memoryなし、全custom node無効化とprofile別allowlistを設定し、VRAM modeを排他的に追加します。

| Mode | ComfyUI引数 | 意図 |
|---|---|---|
| 通常 | `--enable-dynamic-vram` | ComfyUIのDynamic VRAMを明示有効化 |
| Emergency | `--novram --cpu-vae` | Dynamic flagを外し、モデルoffloadとCPU VAEを優先 |

競合するVRAM modeを避けるため、引数配列では必ず排他にします。launcherは他アプリを終了しません。

## 開始・終了時のsystem metrics

`tools/system_metrics.ps1` はComfyUIの起動直前と終了直後だけsnapshotを標準出力へ表示します。連続polling、ファイル保存、外部送信はしません。CPU/RAMはWindows CIM、NVIDIA GPUは `nvidia-smi` のquery interfaceを使用します。

CPU package温度はWindowsが常に公開する情報ではありません。LibreHardwareMonitor/OpenHardwareMonitorのWMI sensorを優先し、なければfirmwareのACPI thermal zoneを「CPU packageではない」と明示して表示します。どちらも取得できない場合はtemperature unavailableと表示し、起動を妨げません。GPU queryを含むmetrics取得失敗もwarningへ縮退し、ComfyUIの実行可否からは分離します。

一次情報: [Microsoft thermal zone diagnostics](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/examples--requirements-and-diagnostics)、[NVIDIA nvidia-smi query fields](https://docs.nvidia.com/deploy/nvidia-smi/index.html)。

## APIデータフロー

1. CLIが `.env` を読み、base/keyをローカル検査します。
2. `submit` はprompt/media/mode/ratio/sizeをpreflightし、`--confirm-billable` を必須確認します。
3. local mediaはData URLへ変換され、Bearer付きで `POST /v2/video_generation` に送られます。
4. `status` / `wait` は `GET /v2/query/video_generation/{task_id}` をpollします。
5. success responseのMP4 URLは、Bearerなしの別download requestで取得し、temporary fileからatomic replaceします。

API contractは[MiniMax V2 Create](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)と
[V2 Query](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)です。CLIが新規課金taskを作るのは明示的な `submit --confirm-billable` だけです。

## Studio MVPデータフロー

1. `setup-studio.ps1`がfrontend依存、exact pinされたPlaywright `1.62.1`、`remotion`／`@remotion/player`／`@remotion/renderer`／`@remotion/bundler`／`@remotion/transitions`の同一version `4.0.517`を導入します。`NODE_OPTIONS`／`NODE_PATH`／任意`PLAYWRIGHT_BROWSERS_PATH`／`REMOTION_*`を外したruntime同等環境で、対応Chromium revisionのinstall／実launchとRemotion package・browser整合性をdoctorで検査してから`studio/dist/`をbuildします。HTTP request中にbrowserやpackageを自動downloadしません。
2. `run-studio.ps1`が`python -m tools.studio.server`を`127.0.0.1:8765`で起動します。通常時は同じoriginからbuild済みUIを配信し、`-Dev`時だけViteを別loopback portで起動します。
3. backendがtracked `productions/`の台帳とignored `outputs/productions/`のartifactを読み、`outputs/studio/studio.sqlite3`へ検索用索引を構築します。eventはscope別hash chainとして`outputs/studio/events/`のJSONLにも追記します。
4. UIは制作一覧、run計画/stage、artifact、event、cost、費用approvalをHTTP APIで取得し、登録済みmediaのpreviewとA/B比較、順序付きカット編集を提供します。既存のFFmpegハードカットpreviewに加え、Remotion詳細previewはbrowser内の`@remotion/player`とbackend renderで同じtracked composition／schema v1を使います。`詳細一括`は登録済みclip、SAPI台本、固定字幕／音声mix／QC選択を一画面で確定し、top jobと4 childを2秒pollingします。`告知動画`は同じDetailed経路をHOOK／MESSAGE／CTAの3シーンへ閉じ、recipeのCAS保存、immutable version、clone、消音Player preview、一括実行を提供します。実行中はJob一覧を2秒、production detailを初回と3回ごとのおおむね6秒で取得します。告知用の保存・複製・実行・照合requestはprivate `AbortSignal`をforwardして15秒で中断します。保存は同じCAS identityを1回再送します。複製はsource identityと名前からSHA-256先頭128-bitのclone IDを決定的に導出し、sourceごとの独立したversioned `localStorage` keyへID／作成時刻をPOST前に同期保存します。panel unmount／production切替／reload後も同じIDを再送し、複数tabの競合も同じbackend IDへ収束します。runtime validationとread-after-writeを通せない場合はPOSTせずfail closedにし、exactな成功応答またはimmutable版履歴のclone lineageでだけ自動消去します。timeout／network error／再送後4xxでは保持し、明示破棄はbrowser intentだけを消してserver recipeを削除しません。曖昧な実行POST応答では送信後に増えたexecution linkのexact Jobだけを受理証拠にし、なければ同じimmutable revisionを1回だけ冪等再送します。2回目のPOSTまたはfresh linkのexact Job照合が曖昧なら自動処理を止め、フォームの永久lockを避けて手動再照合へ戻します。production detailは切替時に旧controllerをabortし、request generationと選択IDが一致した応答だけをstateへ反映し、`detail.id === selectedId`だけを描画します。artifact内容は登録済みpathと許可rootの検査を通った場合だけ返します。safe redaction未対応の設定/markup、未知形式、外部archiveは415で拒否し、Studio自身が生成・検証した監査ZIPだけをdownload対象にします。
5. 再実行計画は、変更工程、再利用候補、追加費用、`execution_profile`を記録します。課金対象のrequested stageを含む通常runは正の見積額を必須とし、0以下または未指定ならfail closedにします。`local_sapi`はnarration/captions/timeline/assembly/qcだけを対象にした0円profile、`elevenlabs_tts`はnarrationを必須とする課金profile、`local_comfyui`はvideo_generationを必須とする0円profile、`local_playwright`はscreen_captureを必須とし、screen_captureとtimelineだけを実行可能とする0円profileです。`local_playwright` Runの`requested_stages`はscreen_capture／timelineだけに固定し、assembly／qcはgeneric rerun planの`affected_stages`へ影響工程として残しますが、このprofileでは実行しません。profileが許可する明示的な実行操作でattemptとjobを作成し、schema v7の`job_id`、provider task、pipeline continuation claim、detailed-test claim、hash-chain eventを永続化してからworker queueへ入れます。CPU／FFmpeg系のdefault lane、長時間GPU生成のGPU lane、Chromium収録とRemotion renderのbrowser lane、top-level orchestrationのpipeline laneは各1 workerのFIFOとして分離します。browser lane内でも収録と詳細timelineはFIFOで、Remotion render自体のconcurrencyは1です。同じリンクの再適用は冪等です。event mirrorからはattempt側の履歴Job IDと、厳密に検証できるdetailed-test Run claimを復元しますが、一時的なjobs検索表そのものは再構築せず、完了状態はattempt記録を正本にします。Studio生成artifactは完全metadataを持つ`artifact.created`または成功済みstage/job resultから候補を得て、`outputs/studio/`内の非symlink通常file、stable ID、bytes、SHA-256、既存ID/path衝突を再検証できたものだけ検索行を復元します。`local_pipeline`は固定workflowの動画生成、SAPIナレーション、生成動画1本を全尺1カットにするtimeline、assembly、QCを一つのimmutableな0円Runへ束ねます。requested stageは`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`の6段、実行stageはComfyUI動画生成→SAPI→one-clip timeline→assembly→technical QCの5段です。`POST /api/productions/{production_id}/execute-local-pipeline`は専用pipeline laneでGPU childとdefault childを協調させ、DBのcanonical pipeline keyでRun/top jobをdedupeします。詳細一括と告知動画は同じpipeline laneからbrowser／default childを協調します。告知recipeから投入する場合は、Detailed top Jobの作成／再利用とrecipe execution linkを同じSQLite transactionで確定します。
6. local narration workerは検証済みJSONをPowerShell helperへfile渡しし、Windows System.SpeechでsegmentごとのWAVを生成します。SAPI preflightと合成processはいずれもjobのcancel contextへ登録し、停止時はprocess treeを終了します。実WAV frame数から字幕時刻を求め、`narration.wav`、`captions.srt`、`timings.json`、`manifest.json`をrun/cache key配下へatomicに確定します。成功artifactのpath、bytes、SHA-256とworker metadataを再検証してから登録し、同一入力はhash検証済みcacheだけを再利用します。1 segment 32 MiB、結合WAV 128 MiB、総尺30分を上限とします。
7. external narrationは、`elevenlabs_tts` profile、narration工程、正の見積、費用上限approval、literal booleanの`confirm_billable=true`をbackendで検証した後だけcontract、secret、provider workerへ進みます。workerは固定の[ElevenLabs `with-timestamps` endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/)へ、固定`eleven_multilingual_v2`／`mp3_44100_128`、voice、全voice setting、seed、改行結合したsegmentを1回だけPOSTします。redirectを拒否し、応答size／deadlineを制限します。`audio_base64`をFFmpegでPCM WAVへ変換し、文字単位alignmentからsegment SRT/timingを作り、local narrationと同じ4成果物をatomic publishします。`request-id`と`character-cost`を記録しますが、API応答からUSD実費を確定できないため`actual_cost=null`を保持します。課金POST前にproduction/cache identityの永続markerを排他的作成し、成功成果物確定時だけ削除します。timeout、5xx、切断など送信結果が曖昧な場合は`external_submission_unknown`として、別Runからも自動再送しません。
8. local ComfyUI workerは、公開bodyを固定`workflow_preset`、prompt、0〜2^63−1のseedだけに限定し、tracked API graphへprompt／seed／出力prefixだけを注入します。新規POST前にworkflow file／canonical graph、公式INT8 diffusion、Q4 text encoder、video/audio VAE、FFprobe binary、2 lock file、ComfyUI／GGUF／Turboの固定HEADと非ignored clean状態を照合します。Windowsでは新しいPOST attemptごとに4 modelをwrite/delete共有なしのread handleで先に開き、その同じhandleからfull SHA-256を計算してpublish後の最終検証まで保持します。これにより実行中の書換え・削除・置換を拒否し、既にwriterが開いているmodelも送信前に拒否します。非Windowsだけは物理file identity付きprocess cacheを使います。同じloopback connectionの`/system_stats`で、`run-local.ps1 -Profile official_q4`（任意の`-NoBrowser`）が生成するmain.py、listen/port、output directory、ComfyUI／PyTorch／Python version、Dynamic VRAM、custom-node disable／exact GGUF allowlistを含む完全なargvを照合します。未知・重複・equals形式の引数、Emergency／Turbo／precision変更、model path redirectを拒否し、`runtime/ComfyUI/extra_model_paths.yaml`も存在またはsymlinkなら拒否します。環境proxyとredirectを無効化してからPOSTし、生成結果は送信時の出力prefixへ束縛します。MP4、fresh ffprobe、workflow、自己hash付きmanifestを`generated-video.mp4`、`workflow.json`、`ffprobe.json`、`manifest.json`としてatomic publishします。prompt本文はworkflow audit artifact以外のpublic result、event、SQLiteへ複製せず、SHA-256、文字数、exact seed decimalだけを記録します。

ComfyUIへの新規送信ではStudioがUUIDを事前発行し、schema v7の`provider_tasks` rowとfsync済みmarkerへ保存してから、同じUUIDを`POST /prompt`の`prompt_id`として渡します。公開APIの同一Run／cache key／payload digest要求は`local_video_generation_claims`をSQLite transaction内で獲得し、同じsingle-instance Studioへ届く同時requestを1つのactive job／attemptへ集約します。Studioの複数processをactive-activeで動かす設計ではなく、全公開entrypointが既存のworkspace instance lockで第二起動を先に拒否します。ComfyUI応答が完全一致しない場合や送信結果が不明な場合はmarkerを残して`ambiguous`へ止まり、自動再POSTしません。providerがterminal failureを返した場合はmarkerを`terminal_state=failed`へfsync置換してから例外化し、次回起動でも失敗を確定できます。promptを含むprovider再開payloadと、prompt／台本／字幕／音声設定を含む正規化済みpipeline継続requestは、現在のWindowsユーザーに紐づく別々のDPAPI暗号文としてSQLiteへ保存します。平文と暗号文は公開API、job、event、監査snapshotへ含めません。

HTTP serverは全responseへ`Connection: close`を付け、1 request／1 handlerへ寿命を限定します。終了時はlistening socketを閉じ、request-line／header／bodyの解析中socketだけを遮断します。解析済みでservice処理へ入ったnon-daemon handlerは応答完了までdrainし、その後にbackground provider recovery、job worker lane、SQLite interruption writerを停止します。`JobManager.shutdown()`が全threadの終了を確認した場合だけ`StudioService.close()`を完了し、最後にsystem-wide workspace lockを解放します。timeoutまたは例外でworkerが残った場合はcloseを失敗させ、再試行またはprocess終了までlockを保持します。これにより、旧processのHTTP handlerやwriterがSQLite／provider taskを更新したまま、新processが同じworkspaceを取得する重複稼働を許しません。Windowsでは既にblockした`makefile().readline()`が別threadからのsocket closeで直ちに解除されないため、未解析requestの無通信を1秒のinactivity timeoutでも有界化します。このtimeoutは解析済みservice処理の実行時間制限ではありません。

Studio起動時は外部HTTP照合をconstructorから分離したbackground coordinatorが行うため、ComfyUIが遅い場合もloopback HTTP serverのbindを待たせません。旧jobを`interrupted`、旧attemptを`failed(process_interrupted)`として保持したままprovider taskのownerを解放し、marker、payload digest、cache key、Run、固定runtime、`GET /api/jobs/{prompt_id}`を照合して同じRunへ新しいrecovery attempt/jobを追記します。provider IDが既知の復旧はpoll/cache回収だけを行い、`prepared`かつ未送信と証明できるtaskだけが最初のPOSTへ進めます。CAS claimの敗者は勝者の状態を変更しません。観測時刻は`last_observed_at`として実際のprovider照合時だけ更新し、UIの2秒polling時刻をprovider確認時刻として偽装しません。正常完了時はprovider task、job、attempt、4 artifact、eventを同じtransactionで成功確定し、暗号文を消去します。worker failure時もprovider task、job、attemptを同一transactionで閉じ、永続化callbackだけが失敗した場合は暗号文とmarkerを保持した`recovery_blocked`として再照合可能にします。明示cancelはjob=`interrupted`、attempt=`failed(process_interrupted)`、provider task=`cancel_requested`を同じSQLite transaction・同じ時刻で確定し、暗号文とmarkerを保持します。startup／manual再照合は同じUUIDへのGETとtargeted cancelだけを使い、生成用`POST /prompt`へは到達しません。未送信を永続記録から証明できる場合はlocal terminalへ確定し、running／404／一時的な照合不能は`cancel_requested`を保持して重複生成を遮断します。provider terminalをDBへ確定した後だけ所有markerと暗号文を削除します。
9. local Playwright workerは、`POST /api/runs/{run_id}/execute-local-screen-capture`のbodyを`url`、`duration_ms`、`settle_ms`、最大16件のscroll/click/pressだけに閉じます。対象は明示port付き`http://127.0.0.1`に限定し、userinfo、fragment、外部host、異なるoriginへのredirect／subresource、WebSocket、service worker、download、既存Cookie／storage、proxy、任意JavaScript／browser flag／output pathを拒否します。毎回新しいChromium contextをbrowser専用FIFO laneで起動し、1080×1920 viewportを1〜30秒収録します。生WebMを指定区間へtrimして1080×1920／24fps／H.264／yuv420p／video-only MP4へ変換し、full decodeとfresh ffprobeを通してから、MP4、生WebM、始点／終点PNG、sanitized report、ffprobe、自己hash付きmanifestの7成果物をdirectory renameでatomic publishします。URL全文、query、selector本文はSQLite、job、event、report、manifestへ保存せず、originとSHA-256だけを残します。live page stateは再現可能なcontent cacheではないため、実行ごとにnonce付きcapture keyを発行して`cache_hit=false`とします。このprofileで実行可能な工程はscreen_captureとtimelineだけです。assembly／qcは影響工程としてRun計画へ残りますが、このprofileでは実行しません。
10. local timeline workerは、`local_sapi`／`local_playwright`の両profileから明示実行でき、同じproductionの登録済み・availableな動画artifactだけをbackendでpath／bytes／SHA-256再検証し、1〜32カット、各50ms以上、合計30分以内のtrimを順序どおり連結します。入力は専用一時directoryの固定名へcopyし、任意pathやfree-form FFmpeg optionを受け付けません。出力は1080×1920、24fps、H.264／yuv420p、video-only MP4、ハードカットへ固定します。24fpsへの変換では累積時間から各カットのframe予算を割り当て、カットごとにその枚数だけをconcatして境界重複や終端カット欠落を防ぎます。`timeline-preview.mp4`、`timeline.json`、`ffprobe.json`、自己hash付き`manifest.json`をatomic publishし、cache keyには順序、artifact ID、trim、入力hash／bytes、frame-budget v2を含む固定出力policy、解決済みFFmpeg／ffprobeのversion・binary hashを含めます。画面収録とtimelineのUIはジョブ状態と進捗率を2秒pollingで表示します。
11. Remotion詳細timelineは既存ハードカットを置き換えず、`POST /api/runs/{run_id}/execute-remotion-timeline`から別の`timeline` stage attempt／browser FIFO jobとして明示実行します。jobの`kind`とattemptの`provider`は`local_remotion_timeline`です。schema v1は同じproductionの登録済み動画1〜16件、各trim、素材音量0〜100%、次カットへの`fade` 50〜2,000ms、各trim内の任意テロップ1件だけを受け付け、出力尺を最大60秒に制限します。最後のclipにtransitionは置けず、fadeは隣接する両clipより短くします。テロップは最大200文字／4行、位置`top | center | bottom`、固定style `shorts_ja_large_v1`だけです。UIの`@remotion/player`とrendererは同じtracked compositionを使い、renderはsetup済みPlaywright Chromiumを明示再利用してconcurrency 1で1080×1920／24fpsへ固定します。入力動画はprivate stagingへcopyしてhashを前後確認し、`remotion-preview.mp4`、`remotion-timeline.json`、`render-report.json`、`ffprobe.json`、自己hash付き`manifest.json`の5成果物をfull decode／fresh ffprobe後にatomic publish・一括登録します。cache key／manifestにはschema、recipe、入力bytes／SHA-256、composition・Node script・Remotion package／browser・FFmpeg／ffprobeのtool identityを含め、exact 5成果物を再検証できた場合だけ再利用します。再現用`remotion-timeline.json`にはテロップ本文を平文保存しますが、job／event／render report／manifestへは複製せず、reportのcontent policyがrecipe側の本文有無を明示します。詳細previewの素材音声はvolume設定を反映し、後続assemblyの閉じたpresetで置換または固定比率mixを選択できます。

Remotion runtimeはsetup時に、Remotion 5 packageとPlaywrightをrootとする実`node_modules`依存closureを列挙し、通常dependency、installed optional dependency、peer dependencyを含む通常fileのbytes／SHA-256をpath非公開のattestationへ集約します。symlink、junction相当の解決先変更、special fileを拒否し、通常doctorとworker開始時にinstalled treeを再計算します。closure digest／package・file・bytes数はtool identityとcache keyへ入り、renderer終了後にも同じattestationを再照合するため、実行途中のdependency変更は成果物publish前に`tool_changed`で閉じます。attestation file自体はignored `studio/node_modules/`配下で、`npm ci`後に`setup-studio.ps1`が再生成します。
12. Detailed Test Video v1は`POST /api/productions/{production_id}/execute-detailed-test-video`を、H3生成を伴う`local_pipeline`とは独立したcontrol-plane境界として実装します。public schema v1は`schema_version`、Remotionのexact `clips`、SAPIのexact `segments`と任意`voice`／`rate`／`pronunciations`、`include_captioned`、`caption_style_preset`、`audio_mix_preset`、`variant`だけを許し、任意path、URL、CSS、React component、renderer prop、free gainを拒否します。`shorts_ja_large_v1`では固定`shorts_ja_large_preflight_v1`を適用し、1〜6 segment、1 segment表示幅38単位以内、連続ASCII 20文字以内、不可視／bidi制御文字なしをqueue前に必須化します。normalized payload、source artifact bytes／SHA-256、Remotion tool cache identity、preflight policyからrequest keyを作り、schema v7の`detailed_test_video_claims`が同一production／requestを一つのimmutableな0円`local_sapi` Runへ束縛します。内部実装世代は`detailed-test-video-v2`とし、payload監査ダイジェスト追加前のローカルclaimとはrequest keyを分離します。同じqueued／running topと物理再検証済みsucceeded topは再利用し、failed／interrupted／改変検知時は同じRunへ新topを追記します。`revision.created` eventはclaim identityも保持し、event mirror復元ではprofile、0円、requested stage、Run／revision、64桁request keyを厳密照合してactive jobなしのclaimだけを再構築します。top Jobの監査payloadには、公開requestを正規化してkey順でcanonical JSON化した`request_payload_sha256`を保存します。UIがdirect POSTの応答を失った場合は、POST前に存在しなかったJobのうち、production、kind、stage、profile、request key形式、このpayloadダイジェストが完全一致し、告知専用timing fieldを持たないものだけを同一送信として採用します。既知Job、ダイジェスト欠落、告知Jobとの取り違えはfail closedにします。topはpipeline laneからWindows SAPI→Remotion→assembly→QCを順次実行し、Remotion childだけをbrowser lane、他のchildをdefault laneへ送ります。各childのexact job／attempt／production／profile／Run／stage／cache resultと、受渡しartifactのID／相対path／bytes／SHA-256を検証し、Remotion recipeとassembly／QCの尺が一致した4 child成功かつQC passの場合だけmasterと3 QC文書を公開します。cancel／timeout／failureはcurrent childをjoinしてからtopをterminalにします。UIはtopを2秒pollingし、完了時の尺はJob結果を正本として表示します。この経路はComfyUI、MiniMax API、ElevenLabs、secret、費用approvalへ到達せず、既存`local_pipeline`のschema v4／one-clip hard-cut経路を変更しません。
13. Announcement Video v1は`tools/studio/announcement_video.py`で、`shorts_ja_15s_v1`、HOOK／MESSAGE／CTAのexact 3 scene、各1〜10秒、fade overlapを差し引いた10〜20秒、必須の1行ナレーション、1〜2行のsafe headlineへ閉じます。新規UIの既定trimは5,167ms／5,167ms／5,166msで、2回の250ms overlap後を360 frame／15.000秒にします。最初の2境界は250ms fade、大見出しはtrim内125ms inset、位置は中央／上／中央、styleは`shorts_ja_large_v1`固定です。告知実行は各trimと各fadeをRemotion compilerと同じ24fpsで個別にhalf-up丸めし、frame cursorへ加減算して各sceneの出力開始を内部`announcement_scene_starts_v1` policyで導出します。SAPI結合WAVへframe単位の無音を挿入してSRTも同じ時刻へ揃え、前segmentが次scene開始を越える場合はoverlapせずfail closedにします。このprivate scheduleと開始時刻はnarration cache、Detailed request key、job／attempt監査、timing／manifestへ含め、通常の公開SAPI bodyと非告知cache identityは変えません。保存APIは`expected_revision` CASで`announcement.recipe.saved` eventへimmutable versionを追記し、exact canonical JSONをbytes／SHA-256／Base64と監査summaryで保持します。複製はexact source versionをclone lineageへ記録します。実行APIは保存済みrevisionを既存Detailed schemaへcompileし、同じcompile結果とscene timingはDetailedのcontent claimとRunを再利用します。queued／runningまたは物理再検証済みsucceeded topがあれば同じJobを返し、failed／interruptedなら同じRunへ新topを作ります。recipe名だけ異なるcloneでも、各versionの`announcement.recipe.executed` linkは別に残します。top Jobの作成／再利用とexecution linkは同じSQLite transactionで確定します。UIは曖昧な応答で、fresh execution linkのexact Job GET、続いて同一immutable revisionの1回限定冪等再送を行います。既知の成功履歴だけでは解除せず、2回目も曖昧なら手動再照合までlockします。Base64は暗号化ではなく、recipe本文はevent mirror／監査exportから読めるため、秘密を入力しません。BGM、ロゴ画像、任意renderer／CSS／React component、新規H3生成はこのcontractにありません。
14. local assembly workerは、同じproductionの登録済み動画と同じRunの成功済みlocal SAPIまたはElevenLabs narration artifactをhash再検証します。FFmpegまたはRemotionのtimeline previewも登録済み動画として使用できます。音声は閉じた`narration_only_v1`（互換既定、sourceを置換）または`source_under_narration_v1`（source 25%＋narration 100%＋固定peak limiter）だけを許し、任意gain／filter／BGM／duckingは受け付けません。mix時はsource audioがちょうど1 streamあり、source／narrationを独立decodeしたpeakがそれぞれ−60 dBを超えることを必須にし、両方を48kHz stereoへ正規化して動画尺へpad／trimします。欠落・実質無音はfail closedです。短いナレーションだけを`apad`し、250msを超える尺超過を拒否します。SRTは厳密parse後にoverride不能な固定style ASSへ変換します。互換既定`studio_default_v1`に加え、YouTube Shorts向けのYu Gothic UI 80px、bold、5px outline、左右96px／下300px余白を固定する`shorts_ja_large_v1`を選べます。任意font path、ASS filter、free-form styleは受け付けません。clean版と任意のcaptioned版をH.264 / yuv420p / AAC / MP4へencodeし、`ffprobe.json`と自己hash付きmanifestとともにatomic publishします。cache keyには入力hash、字幕preset、字幕有無、音声mix preset、音声・出力方針、解決済みFFmpeg/ffprobeのversion・binary hashを含めます。現行local pipelineのhard-cut previewはvideo-onlyなので一括生成は`narration_only_v1`固定です。
15. local technical QC workerは、選択中Runの成功済みassembly attemptからbackendが導出したcleanまたはcaptioned masterだけを受け取ります。assemblyがcontent-addressed cacheを再利用した場合に限り、同じproduction内の先行Runが実fileの所有元になり得ます。その場合もsource attempt chainを循環なしで終端まで辿り、各attemptのcache key、入力hash、artifact ID/path/bytes/SHA-256が同一であることを検証します。MP4 container、video/audio各1 stream、H.264/yuv420p、AAC 48 kHz stereo、container/video/audio各尺、期待尺、full decode、全編無音を検査し、`technical-qc.json`、`ffprobe.json`、自己hash付き`manifest.json`をatomic publishします。解析完了とpass/fail verdictを分け、fail verdictでもjobは成功として証跡を残します。tool/process failureだけをattempt失敗にし、creative、rights、public release statusは変更しません。cache hit時もmasterを再解析してreport改変を検出します。
16. runの費用上限approvalとstage attempt/eventは追記記録で、以前の判断や試行を上書きしません。technical、creative、rights、public releaseは既存台帳の独立statusとして表示します。
17. audit exportはSQLiteの単一read transactionとsnapshot一致済みevent mirror prefixを固定し、対象production/runの記録を`outputs/studio/audits/`へZIP化します。JSON/JSONLと一般textは秘密情報をredactし、安全な構造化処理を保証できない設定・markup形式は理由付きで除外します。Studio生成のSRT/timing/manifest/ffprobe/technical QC JSONは含め、WAVとMP4は`include_media=true`のときだけ含めます。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain tail、除外mirrorを記録し、ZIP閉鎖後にも全entryを検証します。ZIP全体のSHA-256は外部sidecarへ保存します。DB snapshotとartifact copyの間に元fileが変わった場合、ZIP実体には`archive_entries`のbytes/hashを使用します。SQLiteは既存tracked台帳を置き換えません。告知recipeのBase64は可逆で、一般の秘密情報redactionを保証しないため、保存前に秘密を除く必要があります。

`python -m tools.studio.cli test-video`は新しいmedia workerではなく、上記の既存service contractを順番に呼ぶcontrol-plane orchestratorです。workspace lockと索引更新の後、immutableな0円`local_sapi` Runを作成し、narration、単一登録済みvideo artifactのtimeline、assembly、QCをmain threadで直列queue／waitします。各terminal jobとattempt、cache利用、相対artifact path、bytes、SHA-256、technical verdictだけをbounded JSONへ集約します。失敗時は後続stageをqueueせず、QCは`analysis_status=succeeded`かつ`technical_verdict=pass`だけをCLI成功とします。外部provider、secret、課金gateはこのコマンドから呼びません。

Studioの階層は次です。

```text
Production
  -> Artifact / Artifact version
  -> Event hash chain
  -> Announcement recipe
    -> Immutable exact version / parent / clone source
    -> Execution link -> Detailed top Job / Run / Revision
  -> Revision
    -> Run
      -> Requested stages / Cost approval history
      -> Local video request claim
        -> Run / cache key / payload digest / active job
      -> Provider task ledger
        -> Pre-issued provider task ID / encrypted resume payload
        -> Origin attempt / current recovery attempt + job
      -> Detailed test video claim
        -> Content-addressed request / immutable Run + Revision
        -> Active top job / same-run retry lineage
      -> Stage attempt
        -> Background Job ID
        -> Provider/result metadata / Artifact set
```

revisionとrunはimmutableに扱い、修正時は新しい識別子を作ります。各local stageは入力、tool identity、policy、成果物hashからcache keyを作り、成功attemptの成果物を再検証できた場合だけ再利用します。ComfyUIの生成結果はprompt hash、seed、固定workflow、model/runtime/tool identityを束ね、明示retryでは同じRunの試行履歴を保ちます。

`local_pipeline`はcanonical pipeline keyをDB claimとして使い、同一production・同一入力のRun/top jobを原子的にdedupeします。現行schema v7のcontinuation stateは`unavailable | active | waiting_provider | ready | continuing | succeeded | recovery_blocked | cancel_requested | cancelled`です。正規化済みrequestはDPAPI暗号文だけをclaimへ保存し、provider/video childの成功transactionがsource job/attemptをcheckpointします。親topがまだactiveならstateを進めず、親がinterruptedでproviderがterminal成功した場合だけ`ready`へ移します。単一のbackground coordinatorは`ready`を走査してCAS勝者の新topをenqueueするだけで、GPU laneやtop完了を待ちません。source checkpointがある新topはvideo stageをcache-onlyに固定し、同じRun／cache／pipeline lineageと物理artifact chainを再検証します。欠損・改ざん・lineage不一致では`pipeline_recovered_video_unavailable`として停止し、provider task作成、marker操作、新しい`POST /prompt`へfallbackしません。その後のSAPI、timeline、assembly、QCは通常stage cacheを使って続行します。親jobの明示cancelは登録済みchild jobとprocessの終了を待ってからterminalへ遷移し、後からprovider成功が到着してもclaimを`cancelled`へ閉じて暗号文を消去し、自動継続しません。一方、Studio通常終了のshutdown intentは実行中のComfyUI childへ伝播してlocal pollingだけを停止し、provider taskをcancelしません。top success／failureとclaim、provider terminal／video checkpointとclaimはそれぞれ同じSQLite transactionで確定します。requested stageのうち`captions`はnarrationから導出され、実workerはvideo_generation、narration、timeline、assembly、qcの5段です。MVPの詳しい操作と未実装境界は[STUDIO_MVP_JA.md](STUDIO_MVP_JA.md)に分離しています。

artifact復元は1件2 GiB、合計16 GiB、10,000件を上限とします。旧`artifact.created`がIDとkindしか持たず、成功済みstage/job resultにも完全metadataがない成果物は推測で復元しません。物理fileの欠落・改変・symlink・path逸脱・ID/path衝突も復元対象外です。これは検索索引の安全な復元であり、失われたfile自体を再生成する機能ではありません。

worker-backed stageの正常完了は、リンク済みjobとstage attemptの両rowおよび`stage.attempt.succeeded`／`job.succeeded` eventをSQLiteの同一transactionで確定します。ComfyUIではprovider taskと検証済み4 artifactのartifact row、version、`artifact.created` eventも同じtransactionへ含め、成功前にproduction-visibleにしません。artifact衝突、terminal commit失敗、通常のworker error、リンク不一致、provider lineage欠落、または原子的completion envelopeを返さないworker resultは、provider taskを含む同じfailure transactionで閉じます。providerが失敗済みならmarkerをfsyncしてからDBを確定し、callback後のDB永続化だけが失敗した場合はtaskを破棄せず復旧可能状態へ戻します。停止との境界では、完了transactionが先なら両方success、停止transactionが先ならjobは`interrupted`、stage attemptは`failed(process_interrupted)`となり、片側だけ成功する状態を許しません。Studioの通常終了はComfyUI生成をprovider側でcancelせずローカルpollだけを停止し、次回起動へ引き継ぎます。ユーザーの明示cancelではjob／attempt中断と`cancel_requested` fenceをatomicに確定し、同じUUIDへのGETと固定`POST /api/jobs/{prompt_id}/cancel`だけで再照合します。FFmpeg／ffprobe／PowerShell subprocessは従来どおり子process treeごと停止します。DBがbusyでもprocess停止を先行・並行し、全workerとSQLite interruption writerが終了したことを確認します。異常終了後の次回起動や、event mirrorからactive attemptだけを復元した場合も同じ終端状態と失敗eventを補い、永続的なrunning状態を残しません。`local_pipeline`のtop jobは、登録済みchild jobのcancel／join完了後にだけ自身をterminalへ確定し、video_generation、narration、timeline、assembly、qcの各artifactとjob／attemptを同じ原子的completion境界で公開します。schema v7では動画child成功とsource checkpoint、provider terminalとcancel／recovery state、top terminalとcontinuation stateも同じtransactionへ含め、event追記失敗時は全rowと暗号文消去をまとめてrollbackします。Detailed Test Video topは既存childのatomic stage契約を再利用し、成功resultを4 childのexact ID／attemptと物理再hash済みartifactへ限定します。告知recipeから呼ぶ場合は、新規または再利用するDetailed top Jobと`announcement.recipe.executed` linkをjob admissionの同じtransactionへ含め、execution eventの検証・追記が失敗すればJob作成もrollbackします。

queue投入と直後のDB補償が連続失敗した場合は、当該JobManagerが観測したexact top IDだけをcoordinatorが再試行します。worker dequeueとのlock handshakeにより「未投入jobを補償する」か「実workerへcontextと未完了eventの所有権を残す」かを一意に決め、別managerのqueued rowをprivate mapからorphanと推測しません。利用者cancelが補償と競合した場合は、active topまたはexactなterminal／`ready`世代を`cancelled`へ閉じて暗号文を消去し、shutdownの継続意図ではこの破棄経路を使いません。明示cancel intentはshutdownよりstickyで、DB確定までexact job IDをworker contextとは独立してprocess内に保持します。callerとworker双方のDB書込みが一時失敗してworkerが先に退役しても、通常稼働中のcoordinatorが保留IDを公平なbounded batchで再試行し、その間は`ready`世代の自動投入を停止します。ready一覧取得後もcontinuation topのDB CAS直前に同じJobManager lock内でfenceを再確認し、cancel公開との順序を一意にします。終了writerも同じfenceを先に永続化します。shutdown進行中に到着した明示cancelは当該closeを未完了にして次writerへ渡し、DB障害が続く場合もgeneric interruptionへ進まずworkspace lockを保持します。shutdown完了は同じmanager lock内で確定し、その後の新規破棄要求は拒否します。内部childのtimeout/errorによるretireはtopの利用者cancelとして扱わず、childを停止してからtopとclaimを原子的にfailureへ閉じます。

## セキュリティと信頼境界

### Local secret boundary

- `.env` とAPI keyはGit管理外です。
- Studio CLIで登録するprovider secretは現在のWindowsユーザーへ紐づけたDPAPI暗号文として`outputs/studio/secrets/`へ保存し、平文をSQLite、ログ、Git、監査ZIPへ書きません。
- ComfyUI再開payloadと`local_pipeline`の完全な正規化requestは、用途別のDPAPI暗号文としてschema v7 SQLiteへ保存します。prompt／台本平文と暗号文はevent、job metadata、公開provider task／continuation projection、監査snapshotへ書かず、terminal成功または確定cancel時に消去します。DPAPIが使えない環境でも初回生成自体は可能ですが、continuation stateを`unavailable`または`recovery_blocked`へ止め、平文保存へfallbackしません。Detailed Test Videoは再開用台本暗号文を持たず、eventには本文ではなくsegment hash／文字数とclaim identityだけを残します。
- 告知動画は再調整と監査を優先する明示的な例外です。`announcement.recipe.saved` eventはrecipe名、大見出し、ナレーション、発音置換を含むexact canonical JSONをBase64で保持します。Base64は暗号化ではなく、SQLite、JSONL mirror、production detail API、監査exportから復号できるため、recipeへAPI key、token、password、秘密、公開不要の個人情報を入力しません。
- provider workerはprocess環境変数、workspace `.env`、DPAPI storeの順にsecretを解決し、値をUIへ返しません。ElevenLabs keyは費用gateとpayload確認を通ったcache missの実行直前だけ解決し、`xi-api-key` header以外へ入れません。
- `.env`拡張子、`.env.*`、credential/secret directory、private key形式はartifact索引から除外します。JSON/JSONLと一般text/logはbrowser配信時にも既知patternをredactします。設定・markup形式はfail closed、その他のactive documentはattachment + CSP sandboxで同一origin実行を防ぎます。redaction後も外部共有前の人による確認を信頼境界に含めます。
- Studio serverはworkspace hashから作るprocess-lifetime lockを保持し、同じworkspaceへの二重起動を拒否します。event mirrorへの追記はこのsingle-instance境界内で直列化します。
- event JSONL mirrorは全hash chainを検査し、破損時はhealth/UIをdegradedにして監査ZIPから除外します。他scopeのmirror追記は継続します。
- doctorはnetwork requestを行わず、key値を表示しません。
- error textにkeyが含まれてもredactします。
- `MINIMAX_API_BASE` はHTTPS必須です。例外は `localhost`、`127.0.0.1`、`[::1]` のHTTPだけです。

### Redirect / download boundary

Bearer付きAPI JSON requestは専用urllib openerで全HTTP redirectを拒否します。これにより、API endpointの誤設定や侵害による別originへのAuthorization転送を防ぎます。MP4 CDN downloadは別経路で、Authorizationを最初から付けません。download URLのredirectは認証情報を持たないため許可します。

ElevenLabs TTSも固定production HTTPS endpointへの`xi-api-key`付きPOSTで全redirectを拒否します。production URLの上書きは公開request contractに存在せず、内部test注入はliteral loopback originだけです。response body、MP3、alignment、WAV、metadata、総尺、HTTP／FFmpeg時間へ上限を設け、provider bodyや生HTTP errorを公開ログへ流しません。

### Local service boundary

ComfyUIとStudioは `127.0.0.1` のみにlistenします。LAN公開、reverse proxyはこのarchitectureの範囲外です。Studioの読取GETはloopback bindとHost検査、変更系POSTはさらに起動ごとのsession tokenとOrigin検査を使い、`0.0.0.0`へ変更しません。認証拒否するPOSTはJSON上限内の宣言済みbodyだけを破棄してから接続を閉じ、Windowsの未読TCP dataによるresetを避けてHTTP 403を確定します。不正・過大bodyを無制限に読みません。StudioからComfyUIへのHTTPもliteral loopbackだけを許し、環境proxyとredirectを無効化します。`/system_stats`では`official_q4`の標準Dynamic VRAM launcherが作る完全なargvだけを許し、未知引数、Emergency、Turbo、precision／model path変更、ignoredな`extra_model_paths.yaml`を拒否します。固定API graph、送信prefixとhistory outputの一致も新POST／resume前後で検証します。ComfyUI本体が`custom_nodes/`をGit ignoreする境界はGit clean検査だけに依存せず、稼働processの起動引数を閉じ、Windowsでは4 modelのshare-deny handleを生成完了まで保持することで補います。

### Supply-chain boundary

setup/downloaderはGitHub、PyTorch index、PyPI、npm、Hugging Faceからcode/binary/modelを取得します。Git SHA、Pythonのexact package version、frontend lock file、HF revision、file size/hashでdriftを抑えます。StudioのRemotion関連5 packageは同じ`4.0.517`へexact pinし、Playwrightとともに実`node_modules`依存closureのsetup-time attestation、通常doctor、render前後の照合、tool identityへ含めます。自動更新は行わず、更新時は`npm ci`とsetupを再実行し、lock file、attestation、composition、renderer、Player previewの互換性を再確認します。Turbo nodeの同梱time-conditioning gridはdoctorが固定SHA-256も検査しますが、外部artifact自体の安全性を証明するものではありません。

### Data boundary

- local workflow: prompt/mediaはloopback process内。依存取得時のnetwork accessは別途発生。
- API workflow: promptとmediaはMiniMaxへ送信。callbackを使えば指定serverにもtask情報が送信される。
- Studio MVP: production recordとartifact metadataはloopback内。`local_sapi`は本文をWindows System.Speech processへJSON file経由で渡し、`local_comfyui`はpromptとseedを同じworkspaceのattestation済みComfyUIへ渡します。`local_pipeline`も固定されたlocal-only routeでComfyUIとSAPIを使い、ElevenLabs、MiniMax API、費用承認へ到達しません。Detailed Test Videoは登録済みmediaとlocal SAPI／Remotion／FFmpegだけを使い、H3／ComfyUIと全外部providerへ到達しません。raw prompt/scriptはSQLite、event、job metadataへ平文複製せず、prompt hash、文字数、seed decimal、stage lineageと安全なcontinuation stateだけを公開記録します。詳細一括のjob／eventもsegment本文やoverlay本文を複製せず、hash／文字数とartifact／tool identityを記録します。ただし告知recipeだけは、保存・複製・再調整するproduct recordとしてexact JSONをBase64 eventへ明示保存します。これは暗号化ではありません。自動継続用の完全な正規化requestは現在のWindowsユーザー用DPAPI暗号文としてprivate DB accessorだけが読み、cache-only video checkpointの検証後に同じRunへ新topを投入します。ただし、明示的に生成する`workflow.json`、`timings`、`remotion-timeline.json`、`manifest`などのartifactにもcontentが含まれ得るため、監査exportや共有前に確認します。費用承認済み`elevenlabs_tts`を明示実行した場合だけ本文、voice、固定model/output、voice settings、seedをElevenLabsへ送ります。API key、生response、USD実費の推測は保存しません。返却MP3とalignmentはローカルでWAV/SRT/timing/manifestへ変換します。FFmpeg timeline／assembly／technical QCとRemotion詳細timelineは登録済みmediaだけをローカルworkerへ渡し、Remotion requestから任意path、URL、React component、CSS、font、browser flag、environment variable、free-form propsを受け付けません。SQLite、DPAPI暗号文、外部送信marker、監査ZIP、生成MP4/workflow/ffprobe/manifest、WAV/SRT/timing/manifest、両timeline preview、Remotion render report、clean/captioned MP4、technical QC JSONはignored `outputs/studio/`へ保存します。
- output: 著作権、肖像、privacy、適法性はoperatorが判断する。

ライセンス境界は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

Remotionは個人利用を前提に導入しています。利用主体、組織規模、用途、配布形態が変わる場合は、実行や成果物公開の前に現行のRemotion license条件を再確認します。

## 容量と制約

| 項目 | lowvram / Turbo profiles | official / API |
|---|---|---|
| model artifact合計 | base 23,203,877,000 bytes（約21.61GiB）/ Q2 Turbo 23,983,726,816 bytes（約22.34GiB）/ Q4 Turbo選択profile 30,072,736,544 bytes（約28.01GiB）/ Q2+Q4累積unique 38,560,704,704 bytes（約35.91GiB） | official 42,470,585,471 bytes（約39.55GiB）/ official Q4 41,360,420,808 bytes（約38.52GiB）/ official Q4 Turbo 42,140,270,624 bytes（約39.25GiB） |
| 同梱workflow | base: 608x352、4秒、20 steps / Q2 Turbo: 608x352、5秒、simple / 6 steps / Q4 Turbo: 864x480、5秒、simple / 8 steps。Turboはmerge | official templateはComfyUI package。official Q4: 864x480、5秒、stock 20 stepsまたはTurbo simple / 8 steps。APIは768P/2K、4〜15秒 |
| local出力上限の位置付け | H3-Base nativeは短辺768px | 2K/Context-IR/RegenerateはAPI |
| VRAM | 8GiB totalをlocal gate。空き4GiB未満はwarning | officialはさらに高いmemory圧力。成功保証なし |
| RAM | 32GiB totalをlocal gate。available 12GiB未満はwarning | offload時はRAM/pagefile負荷増大 |
| disk | missing models + 2GiB未満はerror。取得後2〜20GiBはwarning | model以外にoutput/temp余裕が必要 |

Remotion詳細timelineはStudioの短尺縦動画向けに、登録済み動画1〜16件、出力最大60秒、1080×1920／24fps、render concurrency 1へ固定しています。素材1件2 GiB、入力合計4 GiB、出力2 GiBのworker上限があり、Playwright画面収録と同じbrowser FIFO laneを使うため、両jobは並列実行されません。これは処理時間や必要disk容量の保証ではありません。

APIの入力制約は、request body 64MB以下、画像/動画/音声ごとのsize/count、video/audio durationを含みます。CLIは主要なrole/count/mode/ratioをpreflightしますが、codec、画素寸法、実durationなどすべてをローカル解析するわけではありません。最終contractは
[V2 Create content仕様](https://platform.minimax.io/docs/api-reference/video-generation-v2-create#content)です。

## 検証済み範囲

2026-08-14までの確定結果:

- lowvram_turbo 5モデル: exact bytes + full SHA-256一致（LoRAは779,849,816 bytes）
- lowvram_q4_turbo 5モデル: exact bytes + full SHA-256一致（Q4 encoderは14,576,977,888 bytes）と専用workflow contract一致
- local doctor: `Ready: yes`、`Locked core runtime matches: yes`。free VRAM逼迫はwarning
- ComfyUI/ComfyUI-GGUF/Turbo nodeの3 locked HEAD、VAE chunked I/O、Turbo grid SHA-256、4 nodeの`object_info`登録を確認
- 自動テスト: 43/43合格（VAE/Turbo/Q4/official INT8のloader・配線・override・解像度・sampling・decode contract、16:9/multiple、manifest/license identity/workflow wiring、missing-object fetch、system metricsを含む）
- 1-step Emergency E2E配線スモーク: H.264 video + AAC stereo audio MP4生成成功
- Turbo Q3 merge 4-step E2E: Dynamic VRAM、416x256、4秒指定、70.35秒でH.264 + AAC MP4生成。LoRAなし同seed A/Bとの差（平均PSNR 24.06 dB）を確認
- Q2 Turboの0.4MP / 5秒 / simple 8-step job 00010が成功。Q4 workflowはこの設定を基準にencoderだけを置換
- Q4 Turboの同prompt/seed 0.4MP / 5秒 / simple 8-step A/Bが286.087秒で成功し、H.264 864x480 + AAC stereoを生成。Q2とのPSNR 26.291812 dB / SSIM 0.814451で出力差を確認
- official_q4 INT8 + Q4、Turboなし、Emergency `--novram --cpu-vae`の416x256 / 5 frames / 1-step / audioなしsmokeが324.814秒で成功。H.264 High / yuv420p MP4の全decode成功、OOM/illegal accessなし。詳細は[検証記録](verification/int8-smoke-2026-08-13.json)
- official_q4 INT8 + Q4、Turboなし、同じEmergency条件で1056x608（0.6MP）/ 5秒 / `res_multistep`・`simple` 20 stepsが3時間31分14.964秒で成功。H.264 High / yuv420p + AAC LC 32kHz stereoの全decode成功。同prompt/seedの1例ではINT8は低ノイズ・安定した窓グリッド、Q3はより細かなtextureという観察であり、一般的な品質優越は示さない。詳細は[検証記録](verification/int8-quality-2026-08-14.json)

2026-08-23のStudio MVP確定結果:

- `setup-studio.ps1`: backend import、Vite 8に合うNode.js 20.19+の20系または22.12+ gate、`npm ci`、TypeScript / Vite production buildが成功
- `run-studio.ps1`: 通常modeの静的UI / healthと停止、Dev modeのVite proxy経由GET / session-protected POSTと停止を確認
- 実制作データ: 3 production / 3,513 available artifactを索引し、safe-format/media除外監査ZIPの10 entryを閉鎖後再読込してbytes/SHA-256一致、ZIP sidecar一致、mirror除外0件を確認
- Studio backend自動テスト: 25/25合格（従来のartifact配信、redaction、audit snapshot、event mirror、課金・approval・immutable recordに加え、`local_sapi` profile、HTTP実行、attempt/cache、job永続リンク、cache改変・metadata改変時の再生成、不正worker metadataの登録前拒否、再起動時active attemptの失敗確定、v1/v2→v3 SQLite移行、attempt/job linkのevent mirror復元を含む）
- Studio narration自動テスト: 5/5合格（WAV連結とframe基準timing、SRT/manifest/hash、発音置換、cache hit、artifact改変時の再生成、入力上限、巨大・長時間WAVの拒否を含む）
- Studio frontend契約テスト: 4/4合格（status分類、job/run正規化、duration変換、ナレーション入力の空行除去と上限を含む）
- repository Python自動テスト: 73/73合格（既存43件 + Studio backend 25件 + narration 5件）
- Windows SAPI実機確認: 日本語2 segmentを`Microsoft Haruka Desktop`で8.251秒のWAVへ生成し、WAV/SRT/timing/manifestの整合、2回目のcache hit、queue投入前のStudio job↔attempt永続リンク、artifact登録→監査ZIPまでのE2Eを確認

2026-08-24のStudio local assembly／technical QC／停止制御確定結果:

- repository Python自動テスト: 142/142合格（既存runtime/API 43件、Studio backend 40件、narration 9件、assembly 19件、technical QC 23件、job/shutdown 8件）
- Studio assembly／QC実FFmpegテスト: 42/42合格。clean/captioned、字幕焼き込み、cache改変、tool binary置換、各stream尺、full decode、短尺を含む全編無音、diagnostics上限、reader failure、timeout/cancel時のprocess tree停止を含む
- shutdown境界: process登録とcancelの競合、DB busy中のkill先行、Windows `taskkill`非0 fallback、psutil process消滅競合、callback開始境界、job/stageのatomic terminal transactionを回帰確認
- Studio frontend契約テスト: 12/12合格、production build成功、npm audit 0件
- 実サービスE2E: 一時workspaceの5秒MP4を索引し、実Windows SAPI 2.377秒→clean/captioned local assembly→technical QC 10項目pass→2回目QC cache hit→mediaなし監査ZIPまで成功。masterはH.264 / yuv420p + AAC 48 kHz stereo、5.000秒で、narration／assembly／QC 2試行のstageとjobはすべてsucceeded

2026-08-24のStudio local timeline／artifact復元確定結果:

- repository Python自動テスト: 163/163合格（既存runtime/API 43件、assembly 19件、Studio backend 47件、job/shutdown 9件、narration 9件、technical QC 23件、timeline 13件）
- Studio frontend契約テスト: 18/18合格、production build成功、npm audit 0件。空欄／非数値時刻、終了時刻の絶対上限、exact snake_case payload、clip操作、job選択を含む
- timeline実FFmpegテスト: 13/13合格。3素材のhard cut、video-only固定出力、cache改変・余分file・tool identity・unsafe cache key・cancel・fixed argv・bounded diagnosticsに加え、50ms×32カットの24fps累積丸め、赤・緑・青の50ms境界での順序と終端保持、1秒×2カットの各24frame保持を検証する回帰を含む
- 実サービスE2E: 3本の2秒sourceから各1.5秒を切り出した4.500秒timeline→実Windows SAPI 1.644秒→clean/captioned assembly→technical QC 10/10 pass→2回目timeline cache hit→mediaなし監査ZIPまで成功。timeline 2試行、narration、assembly、QCの全job／attemptがsucceeded
- SQLite再構築: 成功済みnarrationの4 artifactをevent mirrorと物理fileのbytes／SHA-256一致から復元。byte数を維持したhash改変artifactは復元せず、完全metadataのない旧`artifact.created`も安全にskipすることを確認

2026-08-24のStudio ElevenLabs external TTS確定結果:

- repository Python自動テスト: 184/184合格。外部TTS contract／adapter／費用gate／HTTP route／mock E2Eの18件、secret解決の3件を含む
- Studio frontend契約テスト: 27/27合格。固定modelとexact snake_case payload、literal課金確認、profile／工程／見積／approval gate、provider metadata、`actual_cost=null`表示、Assembly／QC導線を含む。production build成功、npm audit 0件
- mock provider E2E: `elevenlabs_tts` Run作成→正のUSD見積→上限approval→job／attempt成功→WAV/SRT/timing/manifestの4 artifact登録→同一payloadの2回目cache hit→ローカルassembly入力検証まで成功。2回目はsecret解決とprovider callを再実行せず、初回だけの1 callであることを確認
- 安全境界: approval前はexternal contract／secretへ到達しない、固定production HTTPS endpoint、redirect拒否、loopback限定test注入、応答size／総deadline、5xx／timeoutの曖昧送信停止、production/cache markerによる別Run再送防止、API key／本文のDB audit summary非保存を回帰確認
- 実ElevenLabs credentialを使うpaid smokeは意図的に実施していない。実際の日本語音質、provider account上の請求、USD実費照合は未確定

2026-08-24のStudio `test-video` CLI確定結果:

- repository Python自動テスト: 199/199合格。one-command orchestrationとCLIの15件で、工程順序、attempt引渡し、timeout／失敗時の後続停止、source変更拒否、QC fail、workspace lock、cleanup、中断、secret／path非漏洩を追加確認
- Studio frontend契約テスト: 27/27合格、production build成功、npm audit 0件
- 実制作E2E: `SHORT_20260823_claude_md_15s`の登録済み15秒clean masterを入力に、実Windows SAPI 11.104秒、1カットtimeline、captioned assembly、technical QCを1コマンドで完走。初回86.315秒、全4 job／attempt成功、QC 10/10 pass
- 完成master: `outputs/studio/runs/run_b6892f69bb6b40c8b1b1cca0edcadd9d/assembly/64AF016E65AFBCFCACDA5BE93AE0E923C721437E8B900403B0E1B1439B0ABCDF/master-captioned.mp4`、4,524,600 bytes、SHA-256 `3A4A4EDB170F2A1D826231772BD56D1F998B7B31A1DA03C6D8C6A898C1F4A92E`。1080x1920／24fps／15.000秒、H.264／yuv420p + AAC 48kHz stereo、full decode／非無音を確認
- 同一recipeの2回目は11.893秒。narration、timeline、assemblyはhash検証済みcacheを再利用し、QCは新しいassembly attemptのmasterを再解析してpass。外部通信、API key、課金処理は未使用

2026-08-25のStudio local ComfyUI／Shorts字幕preset確定結果:

- repository Python自動テスト: 247件実行、246件合格＋non-Windows専用race test 1件をWindowsでskip。内訳はruntime/API 43件、Studio backend 57件、ComfyUI contract/adapter 30件（platform skip 1件を含む）、assembly 23件、job/GPU lane/shutdown 13件、narration 9件、technical QC 23件、timeline 13件、external TTS 18件、secret 3件、test-video/CLI 15件
- Studio frontend契約テスト: 30/30合格、production build成功、npm audit 0件。固定workflowのexact body、0〜2^63−1 seedのlossless request/response、multiline prompt、再読込metadata、active jobの重複送信抑止を含む
- ComfyUI worker: 固定API graph、GPU worker内でのcache key再束縛、4 model／2 lock file／3 repositoryの来歴、完全なcanonical argv、`extra_model_paths.yaml`拒否、Windowsの毎POST full-hash＋share-deny handle、proxy無効、redirect拒否、送信prefixへの出力束縛、marker-linked resume、production-wide cache lineage、manifest/ffprobe/artifact検証を回帰確認
- GPU lane: ComfyUI jobを1 workerでFIFO直列化し、default laneと並行できること、両laneの停止／中断、無効laneの永続化前拒否を確認
- terminal transaction: ComfyUIの4 artifact row/version/eventとjob/stage successを同一transactionで確定し、通常worker error、リンク不一致、completion envelope欠落／不一致、強制rollback時にもartifact露出や片側runningを残さないことを確認
- Shorts字幕: `studio_default_v1`互換既定と`shorts_ja_large_v1`をcache／manifest／public resultへ含め、任意ASS/font/filter入力を拒否するcontractと実FFmpeg経路を確認。font familyは固定するが、OS側font binary自体はまだhash固定していない
- 実稼働ComfyUIへのread-only照合ではComfyUI 0.31.0、PyTorch 2.13.0+cu130、Python 3.12、`127.0.0.1:8188`、workspace内main/output、3 repository HEAD/clean一致を確認した。ただし現在のlistenerは安全引数導入前に起動され、完全なcanonical argvを満たさないため`invalid_comfyui_runtime`として意図どおり拒否された。生成POSTと実GPU完走はこの変更の受入では行っていない

未確定:

- tracked 20-step low-VRAM workflowの完走、品質、所要時間
- tracked Turbo既定の0.2MP / 5秒 / 6-step完走、品質、再現性とbypass経路
- Q4の一般的な品質・速度優越、複数promptでの比較、`lowvram_q4_turbo` の0.6MPへの段階的拡張
- official profileに残るNVFP4 AWQ text encoder（15,687,142,551 bytes）の導入と実生成
- official_q4 tracked 0.4MP / 5秒 / 20-step既定、official_q4_turbo、複数promptでの品質・prompt追従・時間的一貫性の比較
- 768p/2Kのこのマシンでの性能
- community量子化と公式ウェイトの品質比較
- 実ElevenLabs credentialを使う人承認付きpaid smoke、provider請求情報とのUSD実費照合、Windowsネイティブアプリ収録、実ComfyUI taskをStudio強制終了後に回収して同じpipelineを完走する復旧E2E
- 実ComfyUIを動かしたStudio process強制終了→再起動→同一task回収のGPU E2E、ComfyUI自体が再起動してtaskを失った場合の人による判断UI、旧schema由来のIDなしmarkerの手動解決

## 現行local_pipeline検証状態

2026-08-25 root最終検証では、Python全344件を実行して343件合格＋non-Windows専用race test 1件をWindowsでskipし、frontend 42/42、production buildも成功しました。fake-backed統合で`local_pipeline` request schema v4（SQLite schema v6）、`POST /api/productions/{production_id}/execute-local-pipeline`、専用pipeline lane、6 requested／5 executed stage、DB-level dedupe、same-run retry、parent-child cancellation wait、外部TTS非到達、atomic artifact確定、QC pass、Studio UIの2秒pollingを確認しました。自動継続回帰では、Studio再起動後のprovider成功から同じRunへ新topを一度だけ投入し、8件の同時再送をdedupeすること、source job/attemptを固定したcache-only動画再利用、cache欠損・改ざん・lineage不一致でprovider task／marker／ComfyUI `POST /prompt`へ進まないこと、明示cancel後は継続しないこと、暗号文改ざん、queue投入＋補償の二重失敗、enqueue後例外、worker退役中のDB一時障害、ready CAS、shutdown中のlate cancel競合を安全側に処理することを確認しました。終了・復旧回帰では、atomic `cancel_requested`、未送信／running／404／terminalの同一UUID再照合、解析済みHTTP handlerのdrain、未解析partial requestの有界遮断、`Connection: close`、終了しないworker時のworkspace lock保持と再試行、worker lane／SQLite interruption writerを残りshutdown deadline内でdrainし、期限超過時はlockを保持することを確認しました。成功topの再利用時は5 childのexact lineageと、captioned既定では全19件（clean-onlyでは18件）のartifactをDB metadata・物理bytes・SHA-256で再検証し、最終または中間artifactの欠損／改変／I/O raceを同じRunの新top jobで自己修復します。この検証ではComfyUIへ新規promptをPOSTしていないため、実GPU一括完走時間、強制終了→再起動→同一task回収からpipeline完走までの実機E2E、完成映像の目視品質は未確認です。

2026-08-26には、公式INT8 ConvRot＋Q4 text encoderの固定`official_q4`経路で実GPU `local_pipeline`を完走しました。H3 rawは480×864／24fps／124 frames／5.167秒、H.264＋AAC 32kHz stereoで、H3生成7分06秒、一括pipeline全体7分24秒でした。Windows SAPI、one-clip timeline、captioned assembly、technical QCまで同じRunのartifact／job／attemptとして残り、外部API keyと課金は未使用です。これは通常完走の実機証拠であり、Studio強制終了→再起動→同一ComfyUI task回収の実機E2Eや一般的なcreative品質を保証しません。

## 告知UIの曖昧応答と別tab同期境界

告知実行が2回目も曖昧な場合、「自動処理停止」は追加POSTと同じ候補へのexact Job GETを止めることを意味します。Jobとproduction detailのbounded pollingは継続し、後からfreshなexact execution linkが現れた場合だけ再POSTなしで復旧します。idle時のproduction detail background pollingは行わず、別tabの新revisionは手動再読込または実行／曖昧応答中のdetail再取得後に検出します。cleanかつidleなら最新版を読み込み、dirty／busyなら内容を上書きせず保存・実行を止めます。複製intent用`localStorage`をruntime検証できない場合は、安全なclone IDを保持できないため告知フォーム全体を明示破棄または環境復旧までfail closedにします。

## Playwright画面収録の検証状態

2026-08-25にPlaywright `1.62.1`／Chromium `151.0.7922.34`で実Web収録E2Eを行いました。Studio自身の`http://127.0.0.1:8765/`を描画待ち500ms、1秒時点の720px scroll、指定尺3秒で収録し、job `job_1decf170bbc341f49ff1b4f3e423819b`／attempt `attempt_7e150e65276d4471a42847f4fa100f7b`が成功しました。最終MP4は1080×1920、24fps、H.264／yuv420p、video-only、3.000秒でfull decodeとfresh ffprobeを通過し、MP4 389,197 bytes、生WebM 762,325 bytes、始点／終点PNG、sanitized report、ffprobe、manifestの7 artifactを`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/screen_capture/4021F9F3CA5A228EC8F22456234A9C80853AAA85277B9525CC85ED9C8DF1B73E/`へ登録しました。始点／終点画像を目視し、縦viewportとscroll差分も確認しています。その収録MP4をartifact `art_000a10a0154c74149153d57e0190524b`として同じRunのtimelineへ渡し、job `job_47286fd1eef8480f86e4520289632ac7`／attempt `attempt_6a0bb3b50d934d55bc9336837eebd43a`も成功しました。3.000秒の`timeline-preview.mp4`（362,527 bytes、SHA-256 `17B9FD76E1170BB88A2EC64E66ACA88FF75F0FFD777596E8FA6E4273E5B6B25C`）と3文書を`outputs/studio/runs/run_cbaa1ead33fb4d02be586dcc48cc75be/timeline/F45A9955F5A7AA8FCD4F1A2B3241E4FA1166470015C15A732C661AD9110982BB/`へatomic登録し、画面収録からカット編集までの実素材連携を確認しました。実Playwright回帰テストでは別loopback portへのsubrequest遮断、絶対path／raw URL token非漏洩、output policy改ざん拒否、publish後のcancel／検証失敗cleanup、収録・変換・検証のprogress通知も確認しています。Python全359件は358件合格＋Windows上のnon-Windows専用1件skipを確認し、その後追加したbrowser lane実行中progress可視性、DB atomic commit失敗cleanup、publish後cancel cleanupの3件も個別合格しました。関連するbackend／実ブラウザ統合123件も再実行して全件合格しています。frontend 50/50、production build、`setup-studio.ps1 -SkipBuild -SkipBrowserInstall`のbrowser doctorも成功しました。最新版serverでの再受入ではjob `job_be88c3cb938e4166aef35eb8a873ea83`が`preflight`→`recording`→`transcoding`→`verification`→`publishing`→`registration`→100%完了をAPIへ返し、7成果物を登録しました。

Run契約修正後の再受入では、run `run_c0745a922f814b67b1c45f7fbac8fd80`が`requested_stages=[screen_capture,timeline]`、rerun planの`affected_stages=[screen_capture,timeline,assembly,qc]`を返しました。同Runのjob `job_66c8ae62688044a59cb3ca0a14207aec`も2.000秒、1080×1920、24fps、H.264、video-onlyのMP4と7 artifactを登録し、manifestに絶対pathを残していません。

この受入はWeb viewport収録の証拠です。Windowsデスクトップ／ネイティブアプリ、system audio、microphone、既存ログインsession、外部Webサイト、複数page／popup、30秒超の収録は対象外です。収録MP4は既存timelineのvideo artifact候補として利用できますが、screen captureだけのRunでnarration／assemblyまで自動完走することは保証しません。
