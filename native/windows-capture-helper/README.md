# Windows Capture Helper

`windows-capture-helper` は、Studio が Windows のプライマリ画面と system audio を収録するための小さな native helper です。画面は取得せず、既定の **render/console endpoint** の WASAPI loopback だけを担当します。

## 現在の機能

```powershell
dotnet build .\native\windows-capture-helper\windows-capture-helper.csproj -c Release
& .\native\windows-capture-helper\bin\Release\net8.0-windows\windows-capture-helper.exe doctor --json
```

`doctor --json` は Core Audio COM の `IMMDeviceEnumerator` で既定の render/console endpoint だけを取得し、次を確認します。

- endpoint が active か
- `48,000 Hz / stereo / signed 16-bit little-endian PCM` を共有モードの WASAPI loopback として初期化できるか
- `AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM` と `AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY` により、Windows Audio Engine がその固定形式へ変換できるか
- DPI-aware なプライマリ画面の物理解像度を取得できるか
- 収録を開始していないこと (`recordingStarted: false`)

成功時は top-level の `captureAvailable` が `true` になり、`display` は `{target:"primary_display",width,height}` だけを返します。これは固定PCMと画面入力の事前条件を示すもので、実収録の成功を意味しません。

doctor は `IAudioClient.Start`、`IAudioClient.GetService`、`IAudioCaptureClient.GetBuffer`を呼びません。マイク列挙、任意の device ID／device name取得、任意パスへの書き込み、shell実行も行いません。stdoutは単一のJSON行だけです。

## Loopback capture CLI

実行worker専用のCLIは次のexact formです。

```text
capture-loopback --duration-ms N --start-gated
```

`N` は `1000`〜`30000` の10進整数だけを受け付けます。helperはCore Audioを初期化した後、まだ`IAudioClient.Start`を呼ばずにstderrへ`ready`を出します。workerがhelperとFFmpegの両方をkill-on-close Windows Job Objectへ割り当て終えてから、stdinへ1 byteの`S`とEOFを送った場合だけ収録を開始します。それ以外のbyte列、15秒以内に完結しないgate、`--start-gated`の欠落はfail closedです。stdoutはheaderを持たない固定形式のbinary audioだけです。

- encoding: `s16le`
- sample rate: `48000`
- channels: `2`
- bits per sample: `16`
- frame count: exactly `N * 48`
- byte count: exactly `N * 192`

各packetのWASAPI `devicePosition`と100ns単位QPC timestampを検証します。先頭packetの`devicePosition`はdriverが非zeroのabsolute originを返す場合があるため後続deltaの基準としてだけ使い、`IAudioClient.Start`完了から先頭packetまでのbounded QPC intervalをinitial zero frame数へ変換します。以後の位置の小さなgapも、その位置へzero frameを挿入して時間軸を維持します。`IAudioClient.Start`直後の先頭packetだけは、stream state transitionとして付くことがある単一の`AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY`を監査counterへ記録したうえで、既存のstart offset／device position delta／QPC上限検証を通します。2 packet目以降のdata discontinuity、timestamp error、位置の逆行、QPC drift、500msを超える位置gap、250msを超える末尾不足、packet timestampを検証できない無packet収録はfail closedです。`AUDCLNT_BUFFERFLAGS_SILENT`はzero frameとして出力し、上限を超えるpacketはexact frame capで切ります。正常終了時だけ上記のframe／byte数を保証します。失敗または取消時のpartial stdoutはcallerが破棄しなければなりません。

stderrは固定NDJSON eventだけです。任意の例外message、path、device ID／nameは含みません。

- `ready`: `schemaVersion, operation, event, ok, durationMs, format, recordingStarted:false`
- `started`: readyと同じkeyで`recordingStarted:true`
- `completed`: startedのkeyに `framesWritten, bytesWritten, paddedFrames, silentFrames, discontinuityCount, timestampErrorCount, firstPacketOffsetFrames, gapFrames, tailPaddedFrames, firstPacketQpcOffset100ns, qpcSpan100ns, maxQpcDrift100ns, startCallDuration100ns` を追加
- `failed`: `schemaVersion, operation, event, ok, durationMs, format, recordingStarted, error`（不正引数では`durationMs`なし、Core Audio HRESULTがある場合だけ`error.hResult`あり）

`format` は常に `{encoding:"s16le",samplesPerSecond:48000,channels:2,bitsPerSample:16,bytesPerFrame:4}` です。成功時の`recordingStarted:true`は、当該operationで`IAudioClient.Start`が成功した監査事実を示します。`completed`は`Stop`完了後に出るため、streamがまだactiveという意味ではありません。capture commandの不正引数ではstdoutを空のままにし、stderrへ`failed`を1行だけ出します。

captureは既定render endpointのglobal mixを取得するため、他アプリの再生音や通知音も含み得ます。外部path、device selector、window title、HWND、マイク、任意FFmpeg引数は受け付けません。`IAudioCaptureClient.GetBuffer`／`ReleaseBuffer`と`GetService`／COM releaseは同じSTA threadで行い、`Start`成功後は成功・失敗のどちらでも`Stop`をfinally相当の経路で呼びます。失敗eventの`recordingStarted`は、当該operationで`Start`が一度でも成功したかを正確に引き継ぎます。binary writerはcapture threadから分離し、queue総量を最大5,760,000 bytesに制限します。`Stop`後のstdout drainは最大10秒で打ち切ります。workerはhelperとFFmpegをsuspendedで作成し、Job Object割当後にだけprimary threadを再開します。Studio異常終了時はJob Object handleのOS closeにより両processを終了し、partial outputは公開しません。

## ビルドと終了コード

外部 NuGet パッケージはありません。Windows 上で次を実行します。

```powershell
dotnet build .\native\windows-capture-helper\windows-capture-helper.csproj -c Release
```

- `0`: doctor成功、またはcaptureがexact frame数で完了
- `1`: Windows/Core Audio、capture packet、stdoutのいずれかで失敗
- `2`: command／durationが固定contract外

doctor失敗時はstdoutのJSON schemaを維持します。capture失敗時はbinary stdoutへJSONを混ぜず、stderrの固定`failed` eventだけを確認してください。

## キャプチャ機能について

Studioの`local_windows_capture` profileは、このhelperの固定PCM stdoutを匿名pipeでFFmpegへ渡し、プライマリ画面の`gdigrab`映像と組み合わせます。`gdigrab`のwallclock PTSは`-copyts -start_at_zero`で0起点へ移し、headerを持たない固定PCMはhelperの先頭sampleをPTS 0として生成します。raw PCM入力へwallclockを強制するとinput start timeを取得できずabsolute epochが残るため、`-isync`には依存しません。workerはmasterと最終combined MP4をそれぞれffprobeし、video/audioの`start_time`、duration、frame／sample境界を必須検証します。Matroska masterのPCM sample境界は、millisecond time baseのpacket duration丸めではなく、非圧縮packet payload byte総数がhelperのexact sample数と一致することで検証します。内部masterの尺は0起点へ正規化された全packetの最初のPTSから最後のPTS終端までで検証し、最終MP4では通常のstream／container durationも検証します。開始差が50msを超える場合、timestamp／durationが欠落する場合、またはWASAPI packet QPC検証が通らない場合は成果物を公開しません。絶対QPC値は保存せず、相対offset／span／driftだけを`capture-report.json`とmanifestへ記録します。

この検証範囲はcontainer timestamp／durationとWASAPI packet clockの構造検証です。`gdigrab`の最初の**実映像内容**とWASAPIの最初の**実音声内容**を同じQPC観測点で直接測定していないため、相互の実内容同期を証明しません。report／manifestと公開Job resultは必ず`structural_timing_verified:true`、`content_sync_verified:false`、`live_validation_required:true`、`validation_scope:"container_timestamps_durations_and_wasapi_packet_clock_v1"`を分けて記録し、公開利用は`blocked_pending_live_av_sync_validation`のままにします。ここで`content_sync_verified:false`は同期不良を検出した意味ではなく、実内容による検証をまだ実施していない意味です。

実行routeは画面収録とsystem audio収録を別々に明示確認し、path、window、device ID、マイク、任意FFmpeg引数を受け付けません。通常の自動検証はbuild、`doctor --json`、不正引数、mock-backed統合だけに限定し、`capture-loopback`のlive testは両方を明示承認した場合だけ実行します。gdigrabのwallclockから0起点へ移した映像PTSとraw PCMの0起点PTSは構造検証できますが、両方の最初の実内容を同一clockで直接観測していません。実内容同期はmockだけでは証明できないため、公開利用前には既知の視聴覚同期マーカーを使った承認済み実機試験を別ゲートとして通す必要があります。

2026-08-30の承認済み実機smokeでは実装v4が6秒収録と8成果物登録まで完走し、exact PCM、full decode、構造timingを確認しました。既知flash／toneのmarker開始差は約27〜111ms、loopback音量は低めで、automation pointer overlayも映像へ含まれました。このため実内容同期／音量／cursorの公開gateは解除せず、device切替と親強制終了も残課題です。

backendは確認済みintentから60秒有効・単回使用のexecute tokenを発行して録画開始時に原子的消費し、raw tokenをDB・job payload・監査成果物へ保存しません。
