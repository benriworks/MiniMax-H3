# MiniMax H3 Windowsローカル/API環境

この文書は、このチェックアウトに追加したWindows向け補助環境の操作手順です。上流のモデル説明は
[公式README](README.md#minimax-h3)、構成上の責務は[ARCHITECTURE.md](ARCHITECTURE.md)、
処理経路は[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)、構築時の判断とトラブル記録は
[ENVIRONMENT_SETUP_RECORD_JA.md](ENVIRONMENT_SETUP_RECORD_JA.md)を参照してください。

## 最初に知っておくこと

- ローカル経路はオープンウェイトの **H3-Base-FL2VA** をComfyUIで動かす経路です。H3-Baseのネイティブキャンバスは短辺768pxです。H3-Context-IRとH3-Regenerate-2Kは現時点のオープンソース公開に含まれず、2Kを含む公式フル経路はAPIを使用します。一次情報: [MiniMax H3公式リポジトリ](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)、[ComfyUI公式H3チュートリアル](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。
- 同梱 `workflows/minimax_h3_t2v_lowvram.json` は、負荷を抑えるため **608x352（0.2MP）、4秒指定、20 steps** にしたT2V workflowです。768p品質設定ではありません。
- `lowvram` のQ3/Q2 GGUFはコミュニティ量子化で、実験的です。公式ウェイトより品質、時間的一貫性、指示追従、音声品質が低下する可能性があります。
- 任意の `lowvram_turbo` はLarryvrhのTurbo LoRAを追加し、**608x352、5秒指定、simple / 6 steps** で試す実験経路です。Q3 GGUFは作者が明示する対応baseに含まれないため、通常の `lowvram` を必ずfallbackとして残します。
- 品質優先の `lowvram_q4_turbo` は、同じQ3 diffusion/Turbo経路でtext encoderだけを **Q4_K_M** へ上げ、**0.4MP（864x480）、5秒、simple / 8 steps** を既定にします。Q2よりtext encoder単体で約5.67GiB大きく、RAM/pagefile負荷も増えます。同条件のQ2/Q4 A/Bは両方完走しましたが、1例からQ4の品質優越は断定しません。
- APIで新しい生成を始める `submit` は課金され得ます。CLIは `--confirm-billable` がない限り、送信前に停止します。
- `setup-local.ps1` と `run-local.ps1` は他のGPUアプリを自動終了しません。

## どの経路を使うか

| 目的 | 経路 | 主な特徴 |
|---|---|---|
| 8GB級GPUでまず配線を試す | `lowvram` | コミュニティQ3/Q2、約21.61GiB、同梱GGUF workflow |
| samplingを短縮して試す | `lowvram_turbo` | `lowvram` + 約743.72MiBのTurbo LoRA、約22.34GiB、専用6-step workflow。実験的 |
| text理解を優先して試す | `lowvram_q4_turbo` | Q3 diffusion + Q4 text encoder + Turbo、約28.01GiB、0.4MP / 8-step専用workflow。実験的 |
| ComfyUI公式ウェイトを使う | `official` | Comfy-Org int8/nvfp4、約39.55GiB、ComfyUI Template Libraryの公式T2Vを使用 |
| 2K、H3-Context-IR、H3-Regenerate-2K、公式ホスト実行 | MiniMax API | API利用料と外部送信が発生し得る |

MiniMaxの公開説明では、ローカルH3-Baseは768p検証、フル2K workflowはAPIとの組み合わせです。
[公式のLocal Deployment / Full 2K説明](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)を基準にしてください。

## このフォルダで確認済みの状態

2026-08-12時点で、次を確認しています。

- Windows AMD64 / CPython 3.12.2
- ComfyUI `2a68ce33b4c9ea6ee4283e618a74560cefb32694`（[PR #15446](https://github.com/Comfy-Org/ComfyUI/pull/15446)のMiniMax H3 VAE chunked I/Oを含む）
- ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`
- ComfyUI-MiniMax-H3-Turbo `55fee864dd7b2976b1c4ce3c3d5f7968f181409f`
- PyTorch `2.13.0+cu130`、torchvision `0.28.0+cu130`、torchaudio `2.11.0+cu130`
- RTX 3070 Ti 8GiB、物理RAM約47.72GiB、pagefile 60GiBの検査
- `lowvram_turbo` 5ファイル（base 4点 + LoRA 779,849,816 bytes）の正確なbyte数とfull SHA-256一致、`local_doctor.py --hash` の `Ready: yes`
- `lowvram_q4_turbo` 5ファイル（Q4 encoder 14,576,977,888 bytesを含む）の正確なbyte数とfull SHA-256一致、専用workflow contract、`Ready: yes`
- Turbo custom nodeの2 nodeがComfyUI `object_info`に登録され、同梱time-conditioning gridのSHA-256も一致
- セキュリティ・manifest・Q4を含むworkflow wiring・PowerShell・fresh/shallow clone・system metricsを含む自動テスト **38/38合格**

さらに、base `lowvram` はEmergencyモード相当の `--novram --cpu-vae`、Q3/Q2、608x352で、配線確認用の1-step E2Eスモークが成功しています。出力は726,468 bytesのMP4で、ffprobeではH.264 608x352 / 24fps / 124 framesとAAC 32kHz stereoを確認しました。総所要時間は約15分50秒でした。このスモークは品質評価ではなく、同梱20-step workflowの生成成功や所要時間を保証しません。**同梱20-step workflowはまだ実生成未検証です。**

ComfyUI PR #15446は、長いvideo全体を一度に複製せずchunk単位でvideo VAEのencode/decode I/Oを処理します。上流の175 frames / 1344x768例ではdecode peak allocationが約3485MBから607MB、encodeが約5714MBから2402MBへ下がり、pixel-space outputはbitwise identical、速度はほぼ同等と報告されています。これはpeak削減であり、高速化や8GiB環境での全設定完走を保証するものではありません。

Turboについては、Dynamic VRAM、Q3/Q2、`low_vram=true`、416x256（0.1MP）、4秒指定、4 stepsの実機スモークが70.35秒で完走しました。出力 `outputs/video/MiniMax_H3_Turbo_Smoke_00001_.mp4` は605,791 bytesで、ffprobeではH.264 416x256 / 24fps / 4.458秒とAAC 32kHz stereoを確認しました。同じseed/settingsからLoRAを外したA/Bも63.37秒で完走し、video frameの平均PSNRは24.06 dBで出力差がありました。これはTurbo適用とpipeline完走の確認であり、品質評価ではありません。実行条件とignored出力のhashは[検証記録](verification/turbo-e2e-2026-08-11.json)に残しています。**同梱workflow既定の0.2MP / 5秒 / 6 stepsはまだ実生成未検証です。**

Q2 Turbo job `MiniMax_H3_00010_.mp4` と、text encoderだけをQ4へ置換した `MiniMax_H3_Q4_AB_00001_.mp4` は、同じprompt/seed、0.4MP / 5秒 / simple 8 steps / strength 1.0 / mergeで両方成功しました。Q4は286.087秒、Q2は313.682秒で、Q4出力はH.264 864x480 / 24fps / 5.167秒 + AAC 32kHz stereoです。video A/BはPSNR 26.291812 dB、SSIM 0.814451で差があり、両方ともcity promptへ追従しました。これはQ4経路の完走と出力差の証拠であり、**1例からQ4の品質優越や一般的な速度優位は断定しません。** 詳細は[Q2/Q4 A/B検証記録](verification/q4-text-encoder-ab-2026-08-12.json)に固定しています。

`official` 固有の約34.14GiB分の2ファイルは、この確認時点では未導入です。共通VAE 2ファイルのみ導入済みです。

## 前提

- Windows 10/11 64-bit
- Git for Windows
- NVIDIA GPUと動作するNVIDIAドライバー
- `uv` またはCPython 3.12
- モデルと出力用の十分なディスク

doctorが使う32GiB RAM、8GiB total VRAM、2GiB最低disk headroomは、この補助環境の保守的なreadiness gateであり、MiniMaxが公表した一般的な最小保証値ではありません。瞬間的な空きRAM/VRAM不足はwarningとして扱います。

## 1. ランタイムをセットアップする

PowerShellでプロジェクトルートから実行します。

```powershell
.\setup-local.ps1
```

既定実行は次を固定します。

- `runtime-lock.json` に記録したComfyUI / ComfyUI-GGUF / ComfyUI-MiniMax-H3-Turbo commit
- `runtime-lock.json` に記録したPyTorch cu130 3パッケージ
- `requirements-local-lock.txt` のWindows / CPython 3.12向け依存バージョン

既存リポジトリがcleanでcommitだけ異なる場合は、固定commitへdetached checkoutします。dirtyな場合はresetせず、固定commitと一致していなければ停止します。

最新版を明示的に試す場合だけ次を使えます。

```powershell
.\setup-local.ps1 -Update
```

`-Update` はGitとPython依存を未固定の最新版へ動かす実験操作です。`runtime-lock.json` と不一致になり、再現性は保証されません。検証後にlockを意図的に更新するまでは、通常運用に使わないでください。

## 2. モデルを取得する

最初に[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)と各モデルカードを確認してください。`-AcceptLicense` は、選択profileに含まれる全ファイルについて、それらを確認・受諾したという一括の明示確認です。権利を付与したり、個別条件の確認を代替したりするものではありません。

低VRAM profile:

```powershell
.\download-models.ps1 -Profile lowvram -AcceptLicense
```

任意のTurbo profile:

```powershell
.\download-models.ps1 -Profile lowvram_turbo -AcceptLicense
```

品質優先のQ4 Turbo profile（Q4 encoderはQ2 encoderより約5.67GiB大）:

```powershell
.\download-models.ps1 -Profile lowvram_q4_turbo -AcceptLicense
```

このprofile単体は実行時に必要な5点、30,072,736,544 bytes（約28.01GiB）を取得し、Q2 encoderは含みません。fresh環境でもQ2 Turboを比較・fallbackとして使う場合は、次も別途実行します。両profileのunique artifact累積は38,560,704,704 bytes（約35.91GiB）です。既存Q2 Turbo環境へQ4を併置すると、新規downloadはQ4ファイル全体の14,576,977,888 bytes（約13.58GiB）です。

```powershell
.\download-models.ps1 -Profile lowvram_turbo -AcceptLicense
```

公式ComfyUI profile:

```powershell
.\download-models.ps1 -Profile official -AcceptLicense
```

スクリプトは `model-manifest.json` の固定revisionから取得し、既存ファイルの正確なサイズが一致すればskipします。サイズ不一致は再取得し、最低2GiBを加えた必要容量を事前検査します。ダウンロード直後の自動検査はbyte数までです。完全性を確認する場合は次のSHA-256検査を実行してください。

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --hash
```

Turboを選んだ場合は、同じコマンドのprofileを `lowvram_turbo` または `lowvram_q4_turbo` にします。

## 3. ローカルComfyUIを起動する

通常起動:

```powershell
.\run-local.ps1 -Profile lowvram
```

既定では `127.0.0.1:8188` のみにlistenし、`--enable-dynamic-vram` を使います。`--lowvram` は付けません。previewを無効化し、pinned memoryも無効化します。

`-Profile` は必要モデルと対応workflowの契約をdoctorで検査しますが、ComfyUI UIへJSONを自動ロード・切替しません。launcherが表示する `Open manually:` の対象を、起動後に利用者が明示的に開いてください。前回のworkflowがUIに残っている場合も、そのまま実行しないでください。

ComfyUIの起動直前と終了直後に、時刻、CPU使用率/温度、RAM使用量、GPU使用率/温度/VRAM/電力をコンソールへ表示します。終了時には経過時間も表示します。連続監視やファイル保存は行いません。

CPU温度はWindows/firmwareがsensorを公開していないPCでは `temperature unavailable` になります。これは起動失敗ではありません。LibreHardwareMonitorまたはOpenHardwareMonitorがWMI sensorを公開していれば自動利用し、firmware由来の値しかない場合は `ACPI thermal zone (not CPU package)` と区別します。GPU情報はNVIDIAの `nvidia-smi` から取得します。一次情報: [Microsoft thermal zone diagnostics](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/examples--requirements-and-diagnostics)、[NVIDIA nvidia-smi](https://docs.nvidia.com/deploy/nvidia-smi/index.html)。

ブラウザーを自動で開かず、別portを使う例:

```powershell
.\run-local.ps1 -Profile lowvram -Port 8189 -NoBrowser
```

GPU空きが厳しい場合のEmergencyモード:

```powershell
.\run-local.ps1 -Profile lowvram -EmergencyLowVram
```

Emergency時は `--enable-dynamic-vram` を外し、排他的に `--novram --cpu-vae` を付けます。大幅に遅くなります。

### lowvram workflow

ComfyUIで `workflows/minimax_h3_t2v_lowvram.json` を開きます。これは
[Comfy-Org公式T2V templateの固定commit](https://github.com/Comfy-Org/workflow_templates/blob/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_t2v.json)
からGGUF loaderへ変換したものです。詳細は[workflows/README.md](workflows/README.md)を参照してください。

### lowvram_turbo workflow（任意・実験的）

```powershell
.\run-local.ps1 -Profile lowvram_turbo
```

ComfyUIで `workflows/minimax_h3_t2v_lowvram_turbo.json` を開きます。固定した
[Turbo LoRA model card](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/tree/43a74557ac3f6539db8e0f2a959d03feb7a81480)と
[custom node](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/tree/55fee864dd7b2976b1c4ce3c3d5f7968f181409f)に基づき、v4 step600 EMA、strength 1.0、simple / 6 stepsを使います。

この専用workflowは `low_vram=true` のmerge経路を明示します。量子化baseではbypassより少しsoftになる代わりにpeak VRAMを抑えます。作者資料はbf16/int8_convrotとpruned int8/fp8を挙げていますが、Q3 GGUFを明示していません。Q3との組合せはこの環境固有の実験であり、エラー、音声劣化、motion smear、品質低下があれば `lowvram` profileへ戻してください。bypass経路はこの環境の受入検証対象外です。

Q3実機ログでは `[merge]: 208 weights patched + 51 adaln injected` を確認しました。一方、node内canaryの `weight_patched=False` / `is_injected=False` は、ComfyUI-GGUFが通常の `weight_function` ではなく `GGMLTensor.weight.patches` にpatchを保持するためfalse negativeになります。この2値だけでLoRA無効と断定しません。今回の受入はmerge行、4-step完走、LoRAなし同seed A/Bの出力差を組み合わせています。[open issue #17](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/issues/17)はbypassの表示・挙動に関する追加注意として参照してください。

### lowvram_q4_turbo workflow（品質優先・実験的）

```powershell
.\run-local.ps1 -Profile lowvram_q4_turbo
```

ComfyUIで `workflows/minimax_h3_t2v_lowvram_q4_turbo.json` を開きます。このworkflowは成功済みQ2 job `MiniMax_H3_00010_.mp4` の **0.4MP / 5秒 / simple 8 steps / strength 1.0 / `low_vram=true`** を基準に、text encoderだけを `qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` へ置換しています。固定revision、byte数、SHA-256は `model-manifest.json` に記録しています。

既定0.4MPのQ4 E2Eは成功済みです。次に利用者が0.6MPへ手動で上げる場合も1jobだけにし、resolution、duration、stepsを同時に上げないでください。Q4の一般的な品質優越は未確定なので、OOM、長時間化、品質悪化時は既存 `lowvram_turbo` のQ2 workflowへ戻して同じprompt/seedで比較します。fresh環境では前節のQ2 profile downloadも必要です。

### official workflow

`official` profileを取得して起動した場合、ComfyUIの **Template Library → Video → MiniMax H3 T2V** を選びます。ComfyUI公式tutorialに記載された `UNETLoader` / `CLIPLoader` と公式モデル名を使う経路です。
[公式ComfyUI H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。

`official` profileで、trackedの `workflows/minimax_h3_t2v_lowvram.json` を開かないでください。このJSONはGGUF専用です。

## 4. ローカルdoctor

高速なサイズ・構成検査:

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram
```

全モデルのSHA-256を読む完全検査:

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --hash
```

Q4 Turbo取得後はprofileを切り替え、Q4を含む5ファイルと専用workflow契約を検査します。

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram_q4_turbo --hash
```

JSON出力:

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --json
```

doctorはGPU total/free VRAM、物理RAM total/available、pagefile、disk、runtime lock、ComfyUI/torch/CUDA/GGUF/Turbo node、VAE chunked I/O、モデル、profile別workflowを非破壊で検査します。

- `Ready` は実行前提の重大エラーがないことを示します。生成品質や生成完了を保証しません。
- `Locked core runtime matches` は、ComfyUI、GGUF、Turbo nodeの3 commit、Python 3.12、torch/vision/audioの固定値が一致するかを示します。全Python依存のinstalled freeze一致を意味しません。
- total RAM/VRAM不足と、モデル取得後も2GiB未満になるdiskはerrorです。
- 瞬間的なavailable RAM、free VRAM、2〜20GiBのdisk余裕不足はwarningです。

## 5. MiniMax公式API CLI

API仕様は、[V2 Create](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) と
[V2 Query](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)を参照してください。

設定ファイルを作ります。

```powershell
Copy-Item .env.example .env
notepad .env
.\run-api.ps1 doctor
```

`.env` の `MINIMAX_API_KEY` にキーを設定します。`doctor` はネットワークアクセスを行わず、キー値も表示しません。既定baseは `https://api.minimax.io` です。HTTPのcustom baseは `localhost`、`127.0.0.1`、`[::1]` のみに制限され、それ以外はHTTPS必須です。

### 課金され得るsubmit

次のコマンドだけが新しい生成taskをPOSTします。内容、resolution、duration、課金条件をMiniMax consoleで確認してから `--confirm-billable` を付けてください。

```powershell
.\run-api.ps1 submit `
  --prompt "雨上がりの東京、静かなワンカット、環境音付き" `
  --resolution 768P `
  --duration 4 `
  --ratio 16:9 `
  --confirm-billable `
  --wait `
  --output outputs\api-h3.mp4
```

`--confirm-billable` がなければ、API keyが設定済みでもHTTP送信前に終了します。価格は変わり得るため、実行時点の[MiniMax公式Pay-as-you-go pricing](https://platform.minimax.io/docs/guides/pricing-paygo)を確認してください。

first frameをローカルData URLとして送る例:

```powershell
.\run-api.ps1 submit `
  --prompt "最初の構図を保ちながら、ゆっくりカメラが前進する" `
  --resolution 768P `
  --duration 4 `
  --image first_frame .\inputs\first.png `
  --confirm-billable `
  --wait
```

reference入力のroleは `reference_image`、`reference_video`、`reference_audio` です。安全側のpreflightとして、全reference fileは合計12個以下、reference audioは少なくとも1つのreference imageまたはvideoと併用し、audio-onlyを拒否します。first/last frame modeとreference modeは混在できません。媒体のサイズ・形式・64MB request上限は[V2 Create公式仕様](https://platform.minimax.io/docs/api-reference/video-generation-v2-create#content)を確認してください。

既存taskの照会・待機は新しい生成を作りません。

```powershell
.\run-api.ps1 status TASK_ID
.\run-api.ps1 wait TASK_ID --output outputs\TASK_ID.mp4
```

Bearer key付きAPI requestはHTTP redirectを拒否します。完了MP4のCDN downloadにはAuthorizationを付けません。

## FAQ / OOM回避

### GPUメモリが足りない

1. doctorのfree VRAMを確認します。
2. Blender、ゲーム、別の生成UIなどを自分で閉じます。スクリプトは終了させません。
3. `-EmergencyLowVram` を使います。
4. 608x352、短時間、少stepから始め、resolution・duration・stepsを同時に上げないでください。
5. 1jobずつ実行します。

TurboでOOMする場合は、専用workflowの `low_vram=true` を維持したまま `-EmergencyLowVram`、短いduration、0.2MPを組み合わせます。品質がsoftになる場合やQ3固有の不具合が疑われる場合は、Turboを外した `lowvram` workflowへ戻します。

Q4 TurboでOOMする場合は、0.6MPへ上げず既定0.4MPを維持し、まずQ2の `lowvram_turbo` へ戻します。Q4 text encoderはQ2より6,089,009,728 bytes（約5.67GiB）大きいため、VRAMだけでなくavailable RAMとpagefileもdoctorで確認してください。

### RAM commit不足やOSの停止が起きる

Windowsのpagefileを有効にし、十分な空きdiskを確保してください。モデルoffloadはVRAM不足をRAM/pagefile/disk I/Oへ移すため、処理は非常に遅くなることがあります。

### 2Kをローカルだけで生成したい

この補助環境はH3-Base経路です。公式READMEではH3-Context-IRとH3-Regenerate-2Kは未公開で、2Kフル経路はAPIです。
[公式説明](https://github.com/MiniMax-AI/MiniMax-H3#full-2k-workflow)に従ってください。

### officialをdownloadしたのにworkflowがエラーになる

tracked low-VRAM JSONではなく、ComfyUI Template Libraryの公式MiniMax H3 T2Vを使ってください。次で公式templateとモデル名を検査できます。

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile official
```

### モデルが壊れているように見える

サイズ検査だけでなく `--hash` を実行してください。不一致なら同じprofileのdownloadコマンドを再実行します。download scriptはサイズ不一致ファイルを再取得します。

## ライセンスと外部送信

モデル利用条件の日本語要約は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。要約は法律助言ではなく、必ず
[固定revisionのMiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/bfc8ed0353f5a9733be73e6b2c98ec0948195b86/LICENSE)
本文を優先してください。

ローカル経路のprompt/mediaはloopbackのComfyUI内で処理されます。API経路ではpromptと指定mediaがMiniMaxへ送信され、moderation・保存・利用条件の対象になり得ます。機密情報や第三者の権利を含む素材を送る前に、公式規約と組織の方針を確認してください。
