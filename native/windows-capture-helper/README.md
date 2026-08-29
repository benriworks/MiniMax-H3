# Windows Capture Helper

`windows-capture-helper` は、Studio が画面収録へ進む前に Windows の既定再生デバイスを安全に検査する小さな native helper です。

## 現在の機能

```powershell
dotnet build .\native\windows-capture-helper\windows-capture-helper.csproj -c Release
& .\native\windows-capture-helper\bin\Release\net8.0-windows\windows-capture-helper.exe doctor --json
```

`doctor --json` は Core Audio COM の `IMMDeviceEnumerator` で既定の **render/console endpoint** だけを取得し、次を確認します。

- endpoint が active か
- `IAudioClient` を共有モードの WASAPI loopback として初期化できるか
- 収録を開始していないこと (`recordingStarted: false`)

`IAudioClient.Start`、`IAudioCaptureClient.GetBuffer`、マイク列挙、任意の device ID 取得、任意パスへの書き込み、shell 実行は行いません。device ID と device name は JSON に出力しません。stdout は常に単一の JSON 行です。診断用の固定コードと HRESULT 以外の例外メッセージも出力しません。

## ビルドと終了コード

外部 NuGet パッケージはありません。Windows 上で次を実行します。

```powershell
dotnet build .\native\windows-capture-helper\windows-capture-helper.csproj -c Release
```

- `0`: active な既定 render endpoint で loopback 初期化に成功
- `1`: Windows/Core Audio が利用できない、または endpoint が非 active
- `2`: コマンド形式が `doctor --json` ではない

失敗時も stdout の JSON schema は維持されます。`error.stage` と、Core Audio 呼び出しに失敗した場合の `error.hResult` だけを確認してください。

## キャプチャ機能について

この初版は capability doctor のみです。実デバイスを使う loopback WAV 収録はまだ実装していません。そのため、開発時の安全な検証は build と `doctor --json` に限定します。収録機能を追加する場合も、Studio 側から渡す固定 request schema、出力先の allowlist、時間・容量上限、明示的なユーザー操作を先に定義します。
