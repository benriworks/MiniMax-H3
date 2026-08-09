# MiniMax H3 Windowsローカル/API環境

この文書は、このチェックアウトに追加したWindows向け補助環境の操作手順です。上流のモデル説明は
[公式README](README.md#minimax-h3)、構成上の責務は[ARCHITECTURE.md](ARCHITECTURE.md)、
処理経路は[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)を参照してください。

## 最初に知っておくこと

- ローカル経路はオープンウェイトの **H3-Base-FL2VA** をComfyUIで動かす経路です。H3-Baseのネイティブキャンバスは短辺768pxです。H3-Context-IRとH3-Regenerate-2Kは現時点のオープンソース公開に含まれず、2Kを含む公式フル経路はAPIを使用します。一次情報: [MiniMax H3公式リポジトリ](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)、[ComfyUI公式H3チュートリアル](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。
- 同梱 `workflows/minimax_h3_t2v_lowvram.json` は、負荷を抑えるため **608x352（0.2MP）、4秒指定、20 steps** にしたT2V workflowです。768p品質設定ではありません。
- `lowvram` のQ3/Q2 GGUFはコミュニティ量子化で、実験的です。公式ウェイトより品質、時間的一貫性、指示追従、音声品質が低下する可能性があります。
- APIで新しい生成を始める `submit` は課金され得ます。CLIは `--confirm-billable` がない限り、送信前に停止します。
- `setup-local.ps1` と `run-local.ps1` は他のGPUアプリを自動終了しません。

## どの経路を使うか

| 目的 | 経路 | 主な特徴 |
|---|---|---|
| 8GB級GPUでまず配線を試す | `lowvram` | コミュニティQ3/Q2、約21.61GiB、同梱GGUF workflow |
| ComfyUI公式ウェイトを使う | `official` | Comfy-Org int8/nvfp4、約39.55GiB、ComfyUI Template Libraryの公式T2Vを使用 |
| 2K、H3-Context-IR、H3-Regenerate-2K、公式ホスト実行 | MiniMax API | API利用料と外部送信が発生し得る |

MiniMaxの公開説明では、ローカルH3-Baseは768p検証、フル2K workflowはAPIとの組み合わせです。
[公式のLocal Deployment / Full 2K説明](https://github.com/MiniMax-AI/MiniMax-H3#recommended-workflow)を基準にしてください。

## このフォルダで確認済みの状態

2026-08-09時点で、次を確認しています。

- Windows AMD64 / CPython 3.12.2
- ComfyUI `cbbc9dab1f03d0d9a6caa8a8be7d77a7e37e1e44`
- ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`
- PyTorch `2.13.0+cu130`、torchvision `0.28.0+cu130`、torchaudio `2.11.0+cu130`
- RTX 3070 Ti 8GiB、物理RAM約47.72GiB、pagefile 60GiBの検査
- `lowvram` 4ファイルの正確なbyte数とSHA-256一致、`local_doctor.py --hash` の `Ready: yes`
- セキュリティ・manifest・workflow・PowerShell・fresh cloneを含む自動テスト **29/29合格**

さらに、Emergencyモード相当の `--novram --cpu-vae`、Q3/Q2、608x352で、配線確認用の1-step E2Eスモークが成功しています。出力は726,468 bytesのMP4で、ffprobeではH.264 608x352 / 24fps / 124 framesとAAC 32kHz stereoを確認しました。総所要時間は約15分50秒でした。このスモークは品質評価ではなく、同梱20-step workflowの生成成功や所要時間を保証しません。**同梱20-step workflowはまだ実生成未検証です。**

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

- `runtime-lock.json` に記録したComfyUI / ComfyUI-GGUF commit
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

公式ComfyUI profile:

```powershell
.\download-models.ps1 -Profile official -AcceptLicense
```

スクリプトは `model-manifest.json` の固定revisionから取得し、既存ファイルの正確なサイズが一致すればskipします。サイズ不一致は再取得し、最低2GiBを加えた必要容量を事前検査します。ダウンロード直後の自動検査はbyte数までです。完全性を確認する場合は次のSHA-256検査を実行してください。

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --hash
```

## 3. ローカルComfyUIを起動する

通常起動:

```powershell
.\run-local.ps1 -Profile lowvram
```

既定では `127.0.0.1:8188` のみにlistenし、`--enable-dynamic-vram` を使います。`--lowvram` は付けません。previewを無効化し、pinned memoryも無効化します。

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

JSON出力:

```powershell
.\.venv\Scripts\python.exe -B tools\local_doctor.py --profile lowvram --json
```

doctorはGPU total/free VRAM、物理RAM total/available、pagefile、disk、runtime lock、ComfyUI/torch/CUDA/GGUF、モデル、profile別workflowを非破壊で検査します。

- `Ready` は実行前提の重大エラーがないことを示します。生成品質や生成完了を保証しません。
- `Locked core runtime matches` は、ComfyUIとGGUFの2 commit、Python 3.12、torch/vision/audioの固定値が一致するかを示します。全Python依存のinstalled freeze一致を意味しません。
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
