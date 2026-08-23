# Architecture

## 目的と境界

このチェックアウトは、上流MiniMax H3のソース/モデル資料に、次の3経路を加えています。

1. Windows上のComfyUIによるローカル **H3-Base-FL2VA** 実行
2. Python標準ライブラリだけを使うMiniMax Video Generation V2 API操作
3. 制作案件、run、artifact、ログ、承認、監査exportとローカルSAPIナレーションを扱うloopback専用 **MiniMaxH3 Studio MVP**

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
| `run-local.ps1` | doctorをgateとしてloopback ComfyUIを起動し、VRAM modeを排他的に構成。対応workflowの手動open先と開始・終了時system metricsを表示 | tracked |
| `tools/system_metrics.ps1` | CPU使用率/温度、RAM、NVIDIA GPU使用率/温度/VRAM/電力をbest-effort取得。保存や連続監視はしない | tracked |
| `runtime/ComfyUI/` | ComfyUI本体、custom node、モデル、Comfyの一時状態 | untracked/ignored |
| `workflows/minimax_h3_t2v_lowvram.json` | GGUF向けT2V、0.2MP、4秒指定、20 steps | tracked |
| `workflows/minimax_h3_t2v_lowvram_turbo.json` | 任意のGGUF + Turbo LoRA経路、0.2MP、5秒指定、simple / 6 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` | 品質優先のQ3 diffusion + Q4 text encoder + Turbo経路、0.4MP、5秒、simple / 8 steps、merge | tracked / experimental |
| `workflows/minimax_h3_t2v_official_q4.json` | 公式INT8 ConvRot diffusion + Q4 text encoder、0.4MP、5秒、simple / 20 steps | tracked / 0.6MP・5秒・20-step Emergency run確認済み。tracked 0.4MP既定は未検証 |
| `workflows/minimax_h3_t2v_official_q4_turbo.json` | 公式INT8 ConvRot + Q4 + Turbo LoRA、0.4MP、5秒、simple / 8 steps、merge | tracked / unverified on target hardware |
| ComfyUI Template Library | `official` profile用の公式T2V JSON | installed Python package/runtime |
| `tools/local_doctor.py` | hardware/resource、core lock、model、profile別workflowを非破壊検査 | tracked |
| `run-api.ps1` / `tools/h3_api.py` | `.env`読込、V2 submit/status/wait/download、preflight/security gate | tracked |
| `setup-studio.ps1` | frontend依存を導入してbuildし、Python backend moduleを検査 | tracked |
| `run-studio.ps1` | `127.0.0.1`限定でbackendとbuild済みUI、または開発用Viteを起動 | tracked |
| `studio/` | React / Viteによる制作一覧、案件詳細、artifact preview / A-B比較、event、cost、approval、ローカルナレーションUI | tracked source。`node_modules/`と`dist/`はignored |
| `tools/studio/` | production索引、SQLite、artifact配信、run/approval、stage attempt、Windows SAPI narration/cache、DPAPI secret、audit export API | tracked |
| `tools/studio/sapi_synthesize.ps1` | UTF-8 JSON fileからSystem.Speechへ安全に入力し、segment WAVを出力するローカルhelper | tracked |
| `outputs/studio/` | SQLite、hash chain付きevent JSONL mirror、暗号化secret、監査ZIP、run別ナレーション成果物 | untracked/ignored |
| `.env` | MiniMax API keyと任意base | untracked/ignored secret |
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
4. `run-local.ps1` が開始時system metricsを取得し、`127.0.0.1` のComfyUIをforeground起動します。profileは検査対象を選びますが、workflowをUIへ自動ロード・切替しません。
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

`run-local.ps1` は共通引数としてpreviewなし、pinned memoryなしを設定し、VRAM modeを排他的に追加します。

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

1. `setup-studio.ps1`がfrontend依存を導入し、`studio/dist/`をbuildします。
2. `run-studio.ps1`が`python -m tools.studio.server`を`127.0.0.1:8765`で起動します。通常時は同じoriginからbuild済みUIを配信し、`-Dev`時だけViteを別loopback portで起動します。
3. backendがtracked `productions/`の台帳とignored `outputs/productions/`のartifactを読み、`outputs/studio/studio.sqlite3`へ検索用索引を構築します。eventはscope別hash chainとして`outputs/studio/events/`のJSONLにも追記します。
4. UIは制作一覧、run計画/stage、artifact、event、cost、費用approvalをHTTP APIで取得し、登録済みmediaのpreviewとA/B比較を提供します。artifact内容は登録済みpathと許可rootの検査を通った場合だけ返します。safe redaction未対応の設定/markup、未知形式、外部archiveは415で拒否し、Studio自身が生成・検証した監査ZIPだけをdownload対象にします。
5. 再実行計画は、変更工程、再利用候補、追加費用、`execution_profile`を記録します。課金対象のrequested stageを含む通常runは正の見積額を必須とし、0以下または未指定ならfail closedにします。`local_sapi`はnarration/captions/assembly/qcだけを対象にした0円profileです。明示的な実行操作でnarration attemptとjobを作成し、schema v3の`job_id`とhash-chain eventを永続化してからworker queueへ入れます。同じリンクの再適用は冪等です。event mirrorからはattempt側の履歴Job IDを復元しますが、一時的なjobs検索表そのものは再構築せず、完了状態と成果物はattempt記録を正本にします。
6. local narration workerは検証済みJSONをPowerShell helperへfile渡しし、Windows System.SpeechでsegmentごとのWAVを生成します。実WAV frame数から字幕時刻を求め、`narration.wav`、`captions.srt`、`timings.json`、`manifest.json`をrun/cache key配下へatomicに確定します。成功artifactのpath、bytes、SHA-256とworker metadataを再検証してから登録し、同一入力はhash検証済みcacheだけを再利用します。1 segment 32 MiB、結合WAV 128 MiB、総尺30分を上限とします。
7. runの費用上限approvalとstage attempt/eventは追記記録で、以前の判断や試行を上書きしません。technical、creative、rights、public releaseは既存台帳の独立statusとして表示します。
8. audit exportはSQLiteの単一read transactionとsnapshot一致済みevent mirror prefixを固定し、対象production/runの記録を`outputs/studio/audits/`へZIP化します。JSON/JSONLと一般textは秘密情報をredactし、安全な構造化処理を保証できない設定・markup形式は理由付きで除外します。Studio生成のSRT/timing/manifestは含め、WAVは`include_media=true`のときだけ含めます。package manifest自身を除く格納entryごとの実bytes/SHA-256、scope別event chain tail、除外mirrorを記録し、ZIP閉鎖後にも全entryを検証します。ZIP全体のSHA-256は外部sidecarへ保存します。DB snapshotとartifact copyの間に元fileが変わった場合、ZIP実体には`archive_entries`のbytes/hashを使用します。SQLiteは既存tracked台帳を置き換えません。

Studioの階層は次です。

```text
Production
  -> Artifact / Artifact version
  -> Event hash chain
  -> Revision
    -> Run
      -> Requested stages / Cost approval history
      -> Stage attempt
        -> Background Job ID
        -> Provider/result metadata / Artifact set
```

revisionとrunはimmutableに扱い、修正時は新しい識別子を作ります。ローカルnarrationは工程種別、正規化入力、voice、rate、発音置換、Windows SAPIに固定した実装versionからcache keyを作り、成功試行と4成果物のhashが一致するときだけ再利用します。他のrequested stageはまだ計画のみです。MVPの詳しい操作と未実装境界は[STUDIO_MVP_JA.md](STUDIO_MVP_JA.md)に分離しています。

プロセス停止時にactiveだったjobとstage attemptは、次回起動時にそれぞれ`interrupted`と`failed(process_interrupted)`へ確定します。event mirrorからactive attemptだけが復元された場合も同じ失敗eventを追記し、永続的なrunning状態を残しません。

## セキュリティと信頼境界

### Local secret boundary

- `.env` とAPI keyはGit管理外です。
- Studio CLIで登録するprovider secretは現在のWindowsユーザーへ紐づけたDPAPI暗号文として`outputs/studio/secrets/`へ保存し、平文をSQLite、ログ、Git、監査ZIPへ書きません。
- `.env`拡張子、`.env.*`、credential/secret directory、private key形式はartifact索引から除外します。JSON/JSONLと一般text/logはbrowser配信時にも既知patternをredactします。設定・markup形式はfail closed、その他のactive documentはattachment + CSP sandboxで同一origin実行を防ぎます。redaction後も外部共有前の人による確認を信頼境界に含めます。
- Studio serverはworkspace hashから作るprocess-lifetime lockを保持し、同じworkspaceへの二重起動を拒否します。event mirrorへの追記はこのsingle-instance境界内で直列化します。
- event JSONL mirrorは全hash chainを検査し、破損時はhealth/UIをdegradedにして監査ZIPから除外します。他scopeのmirror追記は継続します。
- doctorはnetwork requestを行わず、key値を表示しません。
- error textにkeyが含まれてもredactします。
- `MINIMAX_API_BASE` はHTTPS必須です。例外は `localhost`、`127.0.0.1`、`[::1]` のHTTPだけです。

### Redirect / download boundary

Bearer付きAPI JSON requestは専用urllib openerで全HTTP redirectを拒否します。これにより、API endpointの誤設定や侵害による別originへのAuthorization転送を防ぎます。MP4 CDN downloadは別経路で、Authorizationを最初から付けません。download URLのredirectは認証情報を持たないため許可します。

### Local service boundary

ComfyUIとStudioは `127.0.0.1` のみにlistenします。LAN公開、reverse proxyはこのarchitectureの範囲外です。Studioの読取GETはloopback bindとHost検査、変更系POSTはさらに起動ごとのsession tokenとOrigin検査を使い、`0.0.0.0`へ変更しません。認証拒否するPOSTはJSON上限内の宣言済みbodyだけを破棄してから接続を閉じ、Windowsの未読TCP dataによるresetを避けてHTTP 403を確定します。不正・過大bodyを無制限に読みません。`runtime/ComfyUI/custom_nodes/` のPython codeはローカルprocess内で実行されるため、固定commitとsourceを信頼する境界です。

### Supply-chain boundary

setup/downloaderはGitHub、PyTorch index、PyPI、npm、Hugging Faceからcode/binary/modelを取得します。Git SHA、Pythonのexact package version、frontend lock file、HF revision、file size/hashでdriftを抑えます。Turbo nodeの同梱time-conditioning gridはdoctorが固定SHA-256も検査しますが、外部artifact自体の安全性を証明するものではありません。

### Data boundary

- local workflow: prompt/mediaはloopback process内。依存取得時のnetwork accessは別途発生。
- API workflow: promptとmediaはMiniMaxへ送信。callbackを使えば指定serverにもtask情報が送信される。
- Studio MVP: production recordとartifact metadataはloopback内。外部providerを呼ばず、local narrationだけWindows System.Speech processへJSON file経由で渡す。SQLite、DPAPI暗号文、監査ZIP、WAV/SRT/timing/manifestはignored `outputs/studio/`へ保存する。
- output: 著作権、肖像、privacy、適法性はoperatorが判断する。

ライセンス境界は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

## 容量と制約

| 項目 | lowvram / Turbo profiles | official / API |
|---|---|---|
| model artifact合計 | base 23,203,877,000 bytes（約21.61GiB）/ Q2 Turbo 23,983,726,816 bytes（約22.34GiB）/ Q4 Turbo選択profile 30,072,736,544 bytes（約28.01GiB）/ Q2+Q4累積unique 38,560,704,704 bytes（約35.91GiB） | official 42,470,585,471 bytes（約39.55GiB）/ official Q4 41,360,420,808 bytes（約38.52GiB）/ official Q4 Turbo 42,140,270,624 bytes（約39.25GiB） |
| 同梱workflow | base: 608x352、4秒、20 steps / Q2 Turbo: 608x352、5秒、simple / 6 steps / Q4 Turbo: 864x480、5秒、simple / 8 steps。Turboはmerge | official templateはComfyUI package。official Q4: 864x480、5秒、stock 20 stepsまたはTurbo simple / 8 steps。APIは768P/2K、4〜15秒 |
| local出力上限の位置付け | H3-Base nativeは短辺768px | 2K/Context-IR/RegenerateはAPI |
| VRAM | 8GiB totalをlocal gate。空き4GiB未満はwarning | officialはさらに高いmemory圧力。成功保証なし |
| RAM | 32GiB totalをlocal gate。available 12GiB未満はwarning | offload時はRAM/pagefile負荷増大 |
| disk | missing models + 2GiB未満はerror。取得後2〜20GiBはwarning | model以外にoutput/temp余裕が必要 |

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

未確定:

- tracked 20-step low-VRAM workflowの完走、品質、所要時間
- tracked Turbo既定の0.2MP / 5秒 / 6-step完走、品質、再現性とbypass経路
- Q4の一般的な品質・速度優越、複数promptでの比較、`lowvram_q4_turbo` の0.6MPへの段階的拡張
- official profileに残るNVFP4 AWQ text encoder（15,687,142,551 bytes）の導入と実生成
- official_q4 tracked 0.4MP / 5秒 / 20-step既定、official_q4_turbo、複数promptでの品質・prompt追従・時間的一貫性の比較
- 768p/2Kのこのマシンでの性能
- community量子化と公式ウェイトの品質比較
- 外部有料TTS、画面収録、Remotion、H3/API provider worker、動画assembly/QC、課金実費記録を接続したStudio制作E2E
