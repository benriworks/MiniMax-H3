# Architecture

## 目的と境界

このチェックアウトは、上流MiniMax H3のソース/モデル資料に、次の2経路を加えています。

1. Windows上のComfyUIによるローカル **H3-Base-FL2VA** 実行
2. Python標準ライブラリだけを使うMiniMax Video Generation V2 API操作

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
| `run-local.ps1` | doctorをgateとしてloopback ComfyUIを起動し、VRAM modeを排他的に構成。開始・終了時だけsystem metricsを表示 | tracked |
| `tools/system_metrics.ps1` | CPU使用率/温度、RAM、NVIDIA GPU使用率/温度/VRAM/電力をbest-effort取得。保存や連続監視はしない | tracked |
| `runtime/ComfyUI/` | ComfyUI本体、custom node、モデル、Comfyの一時状態 | untracked/ignored |
| `workflows/minimax_h3_t2v_lowvram.json` | GGUF向けT2V、0.2MP、4秒指定、20 steps | tracked |
| `workflows/minimax_h3_t2v_lowvram_turbo.json` | 任意のGGUF + Turbo LoRA経路、0.2MP、5秒指定、simple / 6 steps、merge | tracked / experimental |
| ComfyUI Template Library | `official` profile用の公式T2V JSON | installed Python package/runtime |
| `tools/local_doctor.py` | hardware/resource、core lock、model、profile別workflowを非破壊検査 | tracked |
| `run-api.ps1` / `tools/h3_api.py` | `.env`読込、V2 submit/status/wait/download、preflight/security gate | tracked |
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
4. `run-local.ps1` が開始時system metricsを取得し、`127.0.0.1` のComfyUIをforeground起動します。
5. lowvramではtracked GGUF workflow、lowvram_turboでは専用Turbo workflow、officialではTemplate Libraryの公式T2Vを使用します。
6. ComfyUIがtext encoder、FL2VA diffusion model、任意のTurbo adapter、video/audio VAEを読み、videoとstereo audioをMP4にmuxします。
7. ComfyUI終了後、launcherが終了時system metricsと経過時間を表示します。通常の生成物出力先は `outputs/` です。

ComfyUIの公式モデル配置とloader名は
[ComfyUI MiniMax H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)に準拠します。

## Profileとworkflowの対応

| Profile | Diffusion / text encoder | Workflow loader | 必ず使うworkflow |
|---|---|---|---|
| `lowvram` | community FL2VA Q3_K_M / Qwen Q2_K | `UnetLoaderGGUF` / `CLIPLoaderGGUF` | tracked `workflows/minimax_h3_t2v_lowvram.json` |
| `lowvram_turbo` | `lowvram` + Larryvrh v4 step600 EMA | GGUF loaders + `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` | tracked `workflows/minimax_h3_t2v_lowvram_turbo.json` |
| `official` | Comfy-Org int8 convrot / nvfp4 awq | `UNETLoader` / `CLIPLoader` | Template Library → Video → MiniMax H3 T2V |

profileとworkflowを交差させません。doctorもprofileに応じて別のworkflow contractを検査します。

Turbo workflowは `UnetLoaderGGUF → MiniMaxH3TurboLoRA → BasicScheduler / BasicGuider` と `MiniMaxH3TurboSampler → SamplerCustomAdvanced` のlinkを固定し、strength 1.0、`low_vram=true`、simple / 6 stepsを検査します。作者がQ3 GGUFを対応baseとして明示していないため、この経路はexperimentalです。non-Turbo `lowvram` がstock fallbackです。bypassはdefaultにしません。

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

## セキュリティと信頼境界

### Local secret boundary

- `.env` とAPI keyはGit管理外です。
- doctorはnetwork requestを行わず、key値を表示しません。
- error textにkeyが含まれてもredactします。
- `MINIMAX_API_BASE` はHTTPS必須です。例外は `localhost`、`127.0.0.1`、`[::1]` のHTTPだけです。

### Redirect / download boundary

Bearer付きAPI JSON requestは専用urllib openerで全HTTP redirectを拒否します。これにより、API endpointの誤設定や侵害による別originへのAuthorization転送を防ぎます。MP4 CDN downloadは別経路で、Authorizationを最初から付けません。download URLのredirectは認証情報を持たないため許可します。

### Local service boundary

ComfyUIは `127.0.0.1` のみにlistenします。LAN公開、認証、reverse proxyはこのarchitectureの範囲外です。`runtime/ComfyUI/custom_nodes/` のPython codeはローカルprocess内で実行されるため、固定commitとsourceを信頼する境界です。

### Supply-chain boundary

setup/downloaderはGitHub、PyTorch index、PyPI、Hugging Faceからcode/binary/modelを取得します。Git SHA、exact package version、HF revision、file size/hashでdriftを抑えます。Turbo nodeの同梱time-conditioning gridはdoctorが固定SHA-256も検査しますが、外部artifact自体の安全性を証明するものではありません。

### Data boundary

- local workflow: prompt/mediaはloopback process内。依存取得時のnetwork accessは別途発生。
- API workflow: promptとmediaはMiniMaxへ送信。callbackを使えば指定serverにもtask情報が送信される。
- output: 著作権、肖像、privacy、適法性はoperatorが判断する。

ライセンス境界は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

## 容量と制約

| 項目 | lowvram / lowvram_turbo | official / API |
|---|---|---|
| model artifact合計 | base 23,203,877,000 bytes（約21.61GiB）/ Turbo 23,983,726,816 bytes（約22.34GiB） | official 42,470,585,471 bytes（約39.55GiB） |
| 同梱workflow | base: 608x352、4秒、20 steps / Turbo: 608x352、5秒、simple / 6 steps、merge | official templateはComfyUI package。APIは768P/2K、4〜15秒 |
| local出力上限の位置付け | H3-Base nativeは短辺768px | 2K/Context-IR/RegenerateはAPI |
| VRAM | 8GiB totalをlocal gate。空き4GiB未満はwarning | officialはさらに高いmemory圧力。成功保証なし |
| RAM | 32GiB totalをlocal gate。available 12GiB未満はwarning | offload時はRAM/pagefile負荷増大 |
| disk | missing models + 2GiB未満はerror。取得後2〜20GiBはwarning | model以外にoutput/temp余裕が必要 |

APIの入力制約は、request body 64MB以下、画像/動画/音声ごとのsize/count、video/audio durationを含みます。CLIは主要なrole/count/mode/ratioをpreflightしますが、codec、画素寸法、実durationなどすべてをローカル解析するわけではありません。最終contractは
[V2 Create content仕様](https://platform.minimax.io/docs/api-reference/video-generation-v2-create#content)です。

## 検証済み範囲

2026-08-11の確定結果:

- lowvram_turbo 5モデル: exact bytes + full SHA-256一致（LoRAは779,849,816 bytes）
- local doctor: `Ready: yes`、`Locked core runtime matches: yes`。free VRAM逼迫はwarning
- ComfyUI/ComfyUI-GGUF/Turbo nodeの3 locked HEAD、VAE chunked I/O、Turbo grid SHA-256、4 nodeの`object_info`登録を確認
- 自動テスト: 34/34合格（VAE/Turbo contract、manifest/workflow wiring、missing-object fetch、system metricsを含む）
- 1-step Emergency E2E配線スモーク: H.264 video + AAC stereo audio MP4生成成功
- Turbo Q3 merge 4-step E2E: Dynamic VRAM、416x256、4秒指定、70.35秒でH.264 + AAC MP4生成。LoRAなし同seed A/Bとの差（平均PSNR 24.06 dB）を確認

未確定:

- tracked 20-step low-VRAM workflowの完走、品質、所要時間
- tracked Turbo既定の0.2MP / 5秒 / 6-step完走、品質、再現性とbypass経路
- official profile固有2モデルの導入と実生成
- 768p/2Kのこのマシンでの性能
- community量子化と公式ウェイトの品質比較
