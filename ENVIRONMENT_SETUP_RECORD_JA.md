# MiniMax H3 環境構築記録

## この文書について

この文書は、2026-08-09に `C:\Users\mono_\MiniMaxH3` へMiniMax H3の実行環境を構築し、2026-08-11にVAE peak削減と任意Turbo経路、2026-08-12に品質優先Q4 profileを追加した際の作業記録です。

操作方法だけを知りたい場合は[LOCAL_SETUP_JA.md](LOCAL_SETUP_JA.md)、現在の構成と責務は[ARCHITECTURE.md](ARCHITECTURE.md)、モデルの利用条件は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。この文書では、なぜ現在の構成を選んだか、何に詰まり、どう回避したかを中心に記録します。

### 2026-08-11追補

- ComfyUIを、MiniMax H3 VAEをchunked I/O化した[PR #15446](https://github.com/Comfy-Org/ComfyUI/pull/15446)のmerge commitへ1 commitだけ進めました。上流報告では175 frames / 1344x768のdecode peak allocationが約3485MBから607MB、encodeが約5714MBから2402MBへ低下し、pixel-space outputはbitwise identical、速度はほぼ同等です。
- LarryvrhのTurbo LoRAを、既存 `lowvram` を変更しない任意の `lowvram_turbo` profileと専用workflowとして追加しました。作者の対応一覧にQ3 GGUFは明記されないため、experimentalとして扱い、通常の `lowvram` をfallbackにします。
- Turbo workflowはv4 step600 EMA、strength 1.0、simple / 6 steps、`low_vram=true` mergeです。adapterとcustom nodeは固定revision、LoRAと同梱time-conditioning gridはSHA-256で検査します。

### 2026-08-12追補

- 既存Q2 profile/workflowを変更せず、Q4 text encoderへ切り替える品質優先 `lowvram_q4_turbo` profileを追加しました。
- Q4は `realrebelai/MiniMax-H3_GGUFs@daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7` の `qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` に固定しました。14,576,977,888 bytes、SHA-256 `1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e` で、取得後のfull hash一致を確認しました。
- 専用workflowは成功済みQ2 job 00010の0.4MP / 5秒 / simple 8 steps / strength 1.0 / merge設定を基準にし、text encoderだけをQ4へ置換しました。同prompt/seedのQ4 E2Eも成功し、1例のA/B差を確認しましたが品質優越は断定しません。

## 最終的に構築したもの

次の2経路を用意しました。

1. Windows native ComfyUIでH3-Base-FL2VAを動かすローカル経路
2. ローカル性能が足りない場合にMiniMax Video Generation V2 APIを使う経路

ローカル経路はRTX 3070 Ti 8GiBでも試せるよう、コミュニティ量子化を使う `lowvram` profileを主経路にしています。Comfy-Org公式量子化を使う `official` profileも定義していますが、構築時点では固有モデル2点をダウンロードしていません。

主な成果物:

- 再現可能なWindows用Python/ComfyUIセットアップ
- profile別のモデル取得、容量検査、任意のSHA-256検査
- 8GiB VRAM向けGGUF workflow
- ハードウェア、空き資源、モデル、workflow、runtime lockを検査するdoctor
- Dynamic VRAMとEmergency CPU offloadの起動モード
- 課金前確認とAPI key保護を備えたMiniMax API CLI
- 起動時と終了時だけ表示するCPU/RAM/GPU snapshot
- 自動テスト、アーキテクチャ文書、ライセンス注意書き

## 構築前の実機監査

### ハードウェアとOS

| 項目 | 構築時に確認した値 |
|---|---|
| OS | Windows 11 Pro、build 26200、AMD64 |
| CPU | Intel Core i7-13700F、16 cores / 24 threads、AVX2 |
| 物理RAM | 約47.72GiB |
| pagefile | 60GiB、`C:\pagefile.sys` |
| GPU | NVIDIA GeForce RTX 3070 Ti、8GiB VRAM、compute capability 8.6 |
| NVIDIA driver | 610.62 |
| Cドライブ | 構築前約544GiB空き、現在約501GiB空き |

空きRAMと空きVRAMは他アプリの状態で変わります。初回監査ではVRAM空きが約3.3GiB、構築時後半のdoctorでも約3.4GiBだったため、総VRAMが8GiBあっても生成前にGPUを使うアプリを閉じる必要がありました。

### 既存ソフトウェア

- Python 3.12.2、`uv`、Git、Git LFS、Hugging Face CLIは利用可能でした。
- system PythonにはPyTorch、Transformersなどが入っていませんでした。
- 既存Conda baseにはPyTorchがありましたが、`c10.dll` 読込時に `WinError 1114` となり、再利用できない状態でした。
- 別環境にはCPU版PyTorchしかありませんでした。
- WSLは実体が未構成で、Docker、CUDA Toolkitの`nvcc`、CMake、Ninja、vLLM、SGLang、llama.cppはありませんでした。
- Ollamaは稼働していましたが、MiniMax H3はテキストLLM単体ではなく、映像と音声を生成するdiffusion pipelineなので利用対象外でした。

既存Condaを修復しながら使うより、プロジェクト内に隔離した `.venv` を作る方が、再現性とトラブル切り分けの両面で安全と判断しました。

## ランタイム選定

### 元のBF16環境を採用しなかった理由

MiniMax H3はQwen3-VL-32B系encoder、33B級のOmni Transformer、video/audio VAEを組み合わせます。公式BF16一式はこのPCの8GiB VRAM、48GiB RAMには大きすぎます。

構築時に比較した主な選択肢:

| 選択肢 | 判断 |
|---|---|
| SGLang | 公式のconsumer GPU検証例でも2枚の32GiB級GPUと約384GiBのhost RAMを使うため不採用 |
| vLLM-Omni | Windows nativeを主対象にせず、公式のoffload例も大容量host RAM前提のため不採用 |
| Diffusers + 元ウェイト | 一系統だけでも100GiBを大きく超え、H3固有の8GiB向け検証経路がないため不採用 |
| WSL | 未構成であるうえ、ComfyUI Dynamic VRAMはnative Windowsを使う方が素直なため不採用 |
| Ollama / llama.cpp | H3全体のaudio/video diffusion pipeline実装ではないため不採用 |
| Windows native ComfyUI | H3 node、公式template、量子化モデル、Dynamic VRAMが揃うため採用 |
| MiniMax API | ローカル性能不足、2K、Context-IR等の代替として採用 |

参照した一次情報:

- [MiniMax H3公式リポジトリ](https://github.com/MiniMax-AI/MiniMax-H3)
- [ComfyUI MiniMax H3公式チュートリアル](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
- [ComfyUI Dynamic VRAM](https://blog.comfy.org/p/dynamic-vram-in-comfyui-saving-local)
- [SGLang MiniMax H3 cookbook](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3)
- [vLLM-Omni MiniMax H3 recipe](https://recipes.vllm.ai/MiniMaxAI/MiniMax-H3)

## 実際に行った設定

### 0. 空フォルダへ上流sourceを取得した

作業開始時の `C:\Users\mono_\MiniMaxH3` は空で、Git repositoryでもありませんでした。上流 `https://github.com/MiniMax-AI/MiniMax-H3.git` を `blob:none` のpartial cloneとして取得し、公式sourceと履歴を土台にWindows用の補助環境を追加しました。

初期実装は `feat/minimax-h3-local-runtime` branchで作成・検査してからlocal `main` へmergeしました。上流README本文は維持し、先頭の案内だけを追加しています。本書作成時のlocal `main` は `origin/main` より3 commits進んでおり、まだpushしていません。

### 1. Python環境を隔離した

プロジェクト直下の `.venv` にCPython 3.12環境を作成しました。`setup-local.ps1` は `uv` を優先し、なければWindows Python launcherまたはPython本体へfallbackします。

既定構成は[runtime-lock.json](runtime-lock.json)に固定しています。

| コンポーネント | 固定値 |
|---|---|
| ComfyUI | `2a68ce33b4c9ea6ee4283e618a74560cefb32694` |
| ComfyUI-GGUF | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` |
| ComfyUI-MiniMax-H3-Turbo | `55fee864dd7b2976b1c4ce3c3d5f7968f181409f` |
| torch | `2.13.0+cu130` |
| torchvision | `0.28.0+cu130` |
| torchaudio | `2.11.0+cu130` |
| CUDA build | 13.0 |
| その他のPython依存 | [requirements-local-lock.txt](requirements-local-lock.txt)でexact pin |

再実行だけで上流最新版へ変わらないよう、通常setupは固定commitと固定packageを使います。最新版を試す操作は明示的な `-Update` に分離しました。

### 2. ComfyUIと固定custom nodeを配置した

`runtime/ComfyUI` にComfyUI、`runtime/ComfyUI/custom_nodes/ComfyUI-GGUF` にGGUF loader、`runtime/ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Turbo` に任意profile用nodeを配置しました。いずれもGit管理外ですが、取得元とcommitはtracked lockに記録しています。

既存runtimeがdirtyな場合は自動resetしません。

- dirtyかつ固定commit一致: 変更を保持して警告
- dirtyかつ固定commit不一致: 安全のため停止
- cleanかつ不一致: 固定commitへdetached checkout

### 3. モデルをprofile化した

[model-manifest.json](model-manifest.json)に取得元repository、revision、remote/local path、正確なbyte数、SHA-256、ライセンスURLを記録しました。

#### lowvram profile

| 役割 | モデル | 容量 |
|---|---|---:|
| FL2VA diffusion | Q3_K_M GGUF | 約8.29GiB |
| Qwen3-VL text encoder | Q2_K GGUF | 約7.91GiB |
| Video VAE | FP16 safetensors | 約4.85GiB |
| Audio VAE | FP32 safetensors | 約0.56GiB |
| 合計 |  | 約21.61GiB |

#### lowvram_turbo profile

`lowvram` の4ファイルに `minimax_h3_turbo_v4_step600_ema.safetensors` 779,849,816 bytes（約743.72MiB）を加え、合計23,983,726,816 bytes（約22.34GiB）です。adapterのsource revisionとSHA-256はmanifestへ固定しています。

#### lowvram_q4_turbo profile

Q3 diffusion、Q4_K_M text encoder、共通VAE 2点、Turbo adapterの5ファイルで、選択profile合計30,072,736,544 bytes（約28.01GiB）です。Q4 encoderはQ2より6,089,009,728 bytes（約5.67GiB）大きいため、RAM/pagefile負荷も増えます。既存Q2 Turbo環境への追加downloadはQ4全体の14,576,977,888 bytes（約13.58GiB）、Q2/Q4両profileのunique累積は38,560,704,704 bytes（約35.91GiB）です。fresh環境でQ2 fallbackも使う場合は、`download-models.ps1 -Profile lowvram_turbo -AcceptLicense` を別途実行します。

#### official profile

Comfy-OrgのFL2VA int8 convrot、Qwen3-VL nvfp4 AWQ、共通VAE 2点で約39.55GiBです。構築時には共通VAEだけがあり、official固有の約34.14GiB分は未取得です。

モデルは大きいためGitへ入れず、`runtime/ComfyUI/models/` 配下に保存します。ダウンロード時はbyte数を検査し、必要な場合だけdoctorの `--hash` で全SHA-256を検査します。

### 4. 8GiB向けworkflowを作った

[Comfy-Org公式T2V template](https://github.com/Comfy-Org/workflow_templates/blob/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_t2v.json)を基準に、[workflows/minimax_h3_t2v_lowvram.json](workflows/minimax_h3_t2v_lowvram.json)を作成しました。

変更点:

- `UNETLoader` を `UnetLoaderGGUF` へ変更
- `CLIPLoader` を `CLIPLoaderGGUF` へ変更
- 解像度を0.2MP、608x352へ縮小
- 長さを4秒へ縮小
- samplerは公式templateと同じ20 stepsを維持
- model名とloader pathをlowvram profileへ合わせた

`official` profileではこのGGUF workflowを使わず、ComfyUI Template Libraryの公式MiniMax H3 T2Vを使います。

任意の[Turbo workflow](workflows/minimax_h3_t2v_lowvram_turbo.json)はlow-VRAM workflowへTurbo LoRA / samplerを挿入し、0.2MP、5秒、simple / 6 steps、mergeを固定しました。Q3 GGUFとの組合せは作者資料で明示されないため、workflowの存在だけで公式対応とはみなしません。

[Q4 Turbo workflow](workflows/minimax_h3_t2v_lowvram_q4_turbo.json)はQ2 Turboを変更せず別ファイルとして追加し、0.4MP、5秒、simple / 8 steps、strength 1.0、mergeを固定しました。まず0.4MPで検証し、成功後に0.6MPを利用者が手動選択する段階設計です。

### 5. VRAM/RAM不足の回避策を入れた

通常起動は `--enable-dynamic-vram` を明示し、previewとpinned memoryを無効化します。

```powershell
.\run-local.ps1 -Profile lowvram
```

空きVRAMが少ないときはDynamic VRAMと競合しないよう、排他的に `--novram --cpu-vae` を使います。

```powershell
.\run-local.ps1 -Profile lowvram -EmergencyLowVram
```

48GiB RAMでもモデル全体を余裕を持って保持できるわけではないため、60GiB pagefileとComfyUIのdisk-backed/offload動作を保険にしています。ただしpagefileへ大きく退避すると非常に遅くなります。launcherは他アプリを勝手に終了しないため、VRAMが逼迫している場合は利用者がブラウザー、動画ソフト、別AI runtime等を整理します。

### 6. doctorをreadiness gateにした

`tools/local_doctor.py` で次を検査します。

- GPU total/free VRAMとdriver
- 物理RAM total/available、pagefile
- モデル取得後も残るdisk容量
- Python、PyTorch、CUDA、ComfyUI、ComfyUI-GGUF、Turbo custom node
- VAE chunked I/O code contractとTurbo time-conditioning grid hash
- 固定Git commitとcore package version
- profileごとのモデル名、容量、任意SHA-256
- workflow loader、内側とtop-level実効overrideのモデル名、ResolutionSelectorのwidth/height link、解像度、秒数、steps

total VRAMだけを見て「Ready」とすると、他アプリがVRAMを消費している状態を見逃します。そのためfree VRAMも取得し、構築時に観測した約3.4GiBのような低空き状態ならEmergency modeを提案するwarningを出します。diskはモデルが揃っていても最低2GiB未満ならerror、2〜20GiBならwarningにしました。

### 7. API fallbackを安全側に実装した

ローカル生成が難しい場合に備え、Python標準ライブラリだけの `tools/h3_api.py` とPowerShell wrapperを追加しました。

主な安全策:

- 課金対象のsubmitは `--confirm-billable` がないと送信しない
- API keyをログへ表示しない
- Bearer付きAPI requestは全redirectを拒否する
- HTTP baseはloopbackだけ許可し、それ以外はHTTPS必須
- MP4 CDN downloadにはAuthorization headerを付けない
- 参照ファイル数、audio-onlyなどを送信前に検査

API keyや残高が必要な実生成は、構築時には実施していません。

### 8. 開始・終了時の負荷表示を追加した

`tools/system_metrics.ps1` を追加し、ComfyUI起動直前と終了直後だけ次を表示します。

- CPU使用率と、取得可能ならCPU温度
- RAM使用量
- GPU使用率、温度、VRAM、消費電力
- 終了時の経過時間

このPCではWindows/firmwareがCPU package温度を公開していませんでした。値を捏造したりACPI thermal zoneをCPU温度と誤表示したりせず、`temperature unavailable` と表示します。LibreHardwareMonitor/OpenHardwareMonitorがWMI sensorを公開していれば自動利用します。

## ハマったところと対処

### 既存CondaのPyTorchが壊れていた

`torch` importで `c10.dll` の `WinError 1114` が発生しました。GPU driver、Python、DLL探索のどこが原因かを既存環境のまま追うと、H3本体の問題と混ざります。

対処: 既存Condaを使わず、プロジェクト専用 `.venv` と固定PyTorch CUDA wheelを使用しました。

### 8GiB VRAMでは公式BF16構成が成立しない

単なる `--lowvram` 追加では解決しません。モデル自体を量子化し、text encoder、DiT、VAEを適切にoffloadする必要があります。

対処: GGUF Q3/Q2、低解像度、4秒、Dynamic VRAMを組み合わせ、最後の手段としてCPU VAEを用意しました。

### 総VRAMと空きVRAMは別物だった

8GiB GPUを搭載していても、構築時は約4.6GiBが他用途で使用中でした。総容量だけのdoctorでは起動可能に見えてしまいます。

対処: `nvidia-smi memory.free` を検査へ追加し、空き不足をwarningにしました。

### GGUFと公式モデルで配置先・loaderが違った

lowvram FL2VA GGUFは `models/unet` と `UnetLoaderGGUF`、公式int8は `models/diffusion_models` と `UNETLoader` を使います。profileだけ切り替えて同じworkflowを開くとmodel未選択またはloader errorになります。

対処: manifestのlocal pathを実体に合わせ、doctorのworkflow contractをprofile別に分離しました。

### setup再実行が再現性を壊す設計になりかけた

初期案では再実行時にGitを`pull`し、Python packageを無指定`--upgrade`する経路がありました。昨日動いた構成がsetup再実行だけで変わる危険があります。

対処: Git SHA、torch3 package、その他requirementsを固定し、更新は `-Update` へ隔離しました。

### PowerShell 5.1固有の落とし穴が複数あった

- function呼出しの `-ArgumentList @(...) + $torchArguments` は、期待した配列結合にならずtorch引数が欠落しました。
- `git clone --no-checkout` 後にHEADが固定revisionと一致すると、checkoutをskipしてworking treeが展開されない場合がありました。
- helperをdot-sourceした後に同名functionをsetup本体で再定義し、修正版を上書きしたことがありました。
- native commandを `| Select-Object -First 1` へ直接pipeすると、Windows PowerShell 5.1で有効な出力があっても `$LASTEXITCODE=-1` になるケースがありました。
- 未取得commitを調べる `git cat-file -e` の正常なprobe missがstderrを出し、呼出し元の `ErrorActionPreference=Stop` によりfetch前に終端しました。

対処:

- 引数配列は先に変数へ完成させてから渡す
- 通常clone後に固定revisionへdetached checkoutする
- Git操作helperを1箇所だけに置く
- native出力を一度配列へ受け、直後にexit codeを保存してから先頭要素を選ぶ
- `cat-file` probe中だけnative stderrを非終端扱いにし、必ずexit codeでfetch要否を決める
- fresh clone、shallow cloneのmissing object、dirty repositoryを含む統合テストを追加する

### API redirectでBearerが別originへ渡る可能性があった

Python `urllib` の通常redirect処理へAuthorization header付きrequestを渡すと、redirect先へheaderが引き継がれる経路をローカル2-serverテストで再現しました。

対処: API JSON request専用openerで全redirectを拒否し、別originへrequest自体が届かない回帰テストを追加しました。さらに非loopback HTTP baseを拒否しました。

### CPU温度をWindows標準だけでは取得できなかった

`MSAcpi_ThermalZoneTemperature`、Windows thermal zone counter、LibreHardwareMonitor/OpenHardwareMonitor WMI namespaceを調べましたが、このPCでは利用可能なCPU温度がありませんでした。

対処: CPU温度だけは取得不可と明示し、GPU温度はNVIDIAの `nvidia-smi` から取得しました。任意のhardware monitorがWMIを公開した場合だけCPU温度を表示します。

### ライセンスが一般的なOSSライセンスではなかった

MiniMax H3は独自Community Licenseで、community quantization側はmetadataが不明なものもあります。単に「Hugging Faceからdownloadできる」だけでは利用判断として不十分です。

対処: pinned LICENSE、各model card、source URL、hashをmanifest/noticeへ記録し、downloadには明示的な `-AcceptLicense` を必須にしました。詳細は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に分離しています。

## 検証できたこと

構築時および本書作成時に次を確認しました。

- `lowvram_turbo` profileの5モデルが正確なbyte数とSHA-256に一致
- `lowvram_q4_turbo` profileの5モデルが正確なbyte数とSHA-256に一致し、Q4 loader / 0.4MP / 5秒 / simple 8-step / merge workflow contractも一致
- `local_doctor.py --hash` が `Ready: yes`
- 固定ComfyUI/GGUF/Turbo node commit、Python、torch3 packageがlockと一致
- ComfyUIの必須H3/Turbo/GGUF nodeと5モデルを認識
- base workflowの608x352 / 4秒 / 20 stepsと、Turbo workflowの608x352 / 5秒 / simple / 6 steps / merge wiring contractが一致
- 自動テスト38/38合格
- Mermaid architecture diagramの実レンダー成功
- Emergency相当、608x352、4秒指定、1 stepのE2E配線スモーク成功
- 出力MP4はH.264 608x352、24fps、124 framesとAAC 32kHz stereo
- 1-stepスモークの総所要時間は約15分50秒
- Turbo Q3 merge、416x256、4秒指定、4 stepsのDynamic VRAM E2Eが70.35秒で完走
- Turbo出力は605,791 bytes、H.264 24fps / 4.458秒 + AAC 32kHz stereo。同seedでLoRAなしA/Bとの差は平均PSNR 24.06 dB。[機械可読な検証記録](verification/turbo-e2e-2026-08-11.json)に条件とartifact hashを保存
- Q3では汎用canaryの `weight_patched=False` はComfyUI-GGUFの `GGMLTensor.weight.patches` を見ないfalse negative。`208 weights patched + 51 adaln injected`、完走、A/B差を併用して適用を確認
- Q2 Turbo job 00010は0.4MP / 5秒 / simple 8 steps / strength 1.0 / mergeで成功。Q4 workflowは同条件からencoderだけを置換
- Q4 Turbo A/Bは同prompt/seedで286.087秒で成功し、H.264 864x480 / 24fps / 5.167秒 + AAC 32kHz stereoを生成。Q2とのPSNR 26.291812 dB、SSIM 0.814451で出力差を確認。詳細は[検証記録](verification/q4-text-encoder-ab-2026-08-12.json)

## まだ検証していないこと

- 同梱20-step lowvram workflowの完走時間と品質
- tracked Turbo既定の0.2MP / 5秒 / 6-step完走・品質・再現性とbypass経路
- Q4の一般的な品質・速度優越、複数promptでのQ2比較、0.6MP実行
- 768p相当のローカル生成
- `official` profile固有モデル2点を使った生成
- API keyと課金を伴うMiniMax API実生成
- 長時間連続運転時の温度、SSD負荷、pagefile耐性
- community Q3/Q2と公式量子化の品質比較
- community Q4 text encoderとQ2/公式encoderの品質・指示追従比較

したがって「ローカルpipelineが最後まで配線されている」ことは確認済みですが、「このPCで実用速度・実用品質の20-step動画が得られる」とまでは確認していません。

## 再構築する場合の最短手順

```powershell
.\setup-local.ps1
.\download-models.ps1 -Profile lowvram -AcceptLicense
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --hash
.\run-local.ps1 -Profile lowvram -EmergencyLowVram
```

ComfyUIが開いたら `workflows/minimax_h3_t2v_lowvram.json` を読み込みます。空きVRAMに余裕がある場合は、最後のコマンドから `-EmergencyLowVram` を外してDynamic VRAMを使います。

## 関連commit

- `6f2cda3` — Windows MiniMax H3 runtimeの初期実装
- `9c551c9` — 初期実装をlocal `main` へmerge
- `f5f9310` — 起動・終了時system metrics表示

この記録は上記commit後のlocal `main` を基準にしています。リモートへpushしていないcommitが含まれる場合があります。
