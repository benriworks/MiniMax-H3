# Architecture diagram

この図は、tracked workspace、untracked local runtime、Studio、外部配布元、MiniMax API、ElevenLabs APIの信頼境界と主要データフローを示します。責務と制約の詳細は[ARCHITECTURE.md](ARCHITECTURE.md)を参照してください。

```mermaid
flowchart LR
    Operator["Operator<br/>PowerShell / browser"]

    subgraph Workspace["Tracked workspace"]
        Setup["setup-local.ps1"]
        RuntimeLock["runtime-lock.json<br/>requirements-local-lock.txt"]
        Downloader["download-models.ps1"]
        ModelManifest["model-manifest.json"]
        Doctor["tools/local_doctor.py"]
        Launcher["run-local.ps1<br/>profile custom-node allowlist"]
        Metrics["tools/system_metrics.ps1<br/>start / end snapshot"]
        LowWorkflow["lowvram workflow<br/>GGUF / 0.2MP / 4s / 20 steps"]
        TurboWorkflow["optional Turbo workflow<br/>GGUF + LoRA / 0.2MP / 5s / 6 steps"]
        Q4TurboWorkflow["quality Q4 Turbo workflow<br/>Q3 + Q4 + LoRA / 0.4MP / 5s / 8 steps"]
        OfficialQ4Workflow["official INT8 + Q4 workflow<br/>0.4MP / 5s / stock 20 steps"]
        OfficialQ4TurboWorkflow["official INT8 + Q4 Turbo workflow<br/>0.4MP / 5s / Turbo 8 steps"]
        StudioApiWorkflow["Studio API workflow<br/>official INT8 + Q4 / portrait<br/>124 frames / 24fps / 20 steps"]
        ApiWrapper["run-api.ps1"]
        ApiCli["tools/h3_api.py"]
        ProductionLedgers["productions/&lt;id&gt;<br/>tracked ledgers / manifests"]
        StudioSetup["setup-studio.ps1"]
        StudioLauncher["run-studio.ps1"]
        StudioFrontend["studio/<br/>React / Vite source"]
        StudioBackend["tools/studio/<br/>local API / index / audit"]
        HttpLifecycle["server.py HTTP lifecycle<br/>Connection: close / parse-phase interruption<br/>parsed handler drain"]
        ShutdownGate["service.py + jobs.py shutdown gate<br/>exact-ID sticky operator-cancel fence<br/>provider recovery / worker lanes / DB writer"]
        ProviderRecovery["service.py startup recovery<br/>background scan / bounded observe"]
        PipelineContinuationCoordinator["service.py pipeline continuation<br/>exact repair + fair cancel retry<br/>manager-lock CAS fence / enqueue-only"]
        LocalPipelineContract["pipeline.py<br/>schema v4 / exact local payload / canonical key"]
        LocalPipelineOrchestrator["local_pipeline orchestrator<br/>one immutable parent / five executed stages"]
        StudioComfyContract["comfyui_execution.py<br/>fixed payload / provenance / cache contract"]
        StudioComfyWorker["comfyui.py<br/>pre-issued UUID / observe / resume / targeted cancel / cache"]
        NarrationWorker["tools/studio/narration.py<br/>validated SAPI worker / cache"]
        ExternalTtsContract["external_tts_execution.py<br/>strict payload / cache / result contract"]
        ElevenLabsWorker["elevenlabs.py<br/>bounded with-timestamps adapter / cache"]
        TimelineWorker["tools/studio/timeline.py<br/>validated hard-cut worker / cache<br/>24fps frame-budget v2"]
        AssemblyWorker["tools/studio/assembly.py<br/>validated FFmpeg worker / cache<br/>closed caption presets"]
        QcWorker["tools/studio/qc.py<br/>validated technical QC / cache"]
        SapiHelper["sapi_synthesize.ps1<br/>UTF-8 JSON IPC"]
        StudioCli["tools.studio.cli<br/>secret + local test-video control"]
        TestVideoOrchestrator["test_video.py<br/>ordered local orchestration<br/>bounded result"]
    end

    subgraph LocalSecrets["Local secret / untracked boundary"]
        Env["process env / .env<br/>MiniMax + ElevenLabs API key"]
        StudioSecrets["outputs/studio/secrets<br/>Windows DPAPI ciphertext"]
    end

    subgraph LocalRuntime["Untracked local boundary"]
        Venv[".venv<br/>Python 3.12 + locked packages"]
        Comfy["ComfyUI on 127.0.0.1<br/>native H3 nodes + chunked VAE I/O"]
        GgufNode["ComfyUI-GGUF"]
        TurboNode["MiniMax H3 Turbo node<br/>pinned custom code + time grid"]
        Models["models<br/>lowvram / Q2 Turbo / Q4 Turbo / official / official Q4"]
        OfficialWorkflow["Template Library<br/>official H3 T2V"]
        Outputs["MP4 outputs / temp"]
        HardwareMetrics["Windows CIM / sensor WMI<br/>NVIDIA nvidia-smi"]
        StudioBuild["studio/node_modules + dist"]
        StudioUi["Studio UI<br/>127.0.0.1 only"]
        StudioDb["outputs/studio/studio.sqlite3<br/>schema v6 / immutable run + job-attempt link"]
        WorkspaceLock["system-wide workspace lock<br/>held until full drain, retry, or process exit"]
        VideoClaims["local_video_generation_claims<br/>Run + cache + payload digest<br/>one active job"]
        ProviderTasks["provider_tasks ledger<br/>state + CAS owner / exact-once submission<br/>cancel_requested fence / DPAPI restart payload"]
        PipelineClaims["local_pipeline_claims<br/>continuation state + CAS<br/>DPAPI request / video checkpoint"]
        StudioEvents["outputs/studio/events<br/>hash-chained JSONL mirror"]
        ExternalSubmissionState["outputs/studio/external-submissions<br/>production/cache ambiguity marker"]
        GpuLane["Studio GPU FIFO lane<br/>single ComfyUI worker"]
        PipelineLane["Studio local_pipeline lane<br/>one top job / child coordination"]
        DefaultLane["Studio default child lane<br/>SAPI + FFmpeg FIFO"]
        VideoGenerationOutputs["outputs/studio/runs/.../video_generation<br/>MP4 / workflow / ffprobe / manifest"]
        NarrationOutputs["outputs/studio/runs/.../narration<br/>WAV / SRT / timing / manifest"]
        TimelineOutputs["outputs/studio/runs/.../timeline<br/>preview MP4 / timeline / ffprobe / manifest"]
        AssemblyOutputs["outputs/studio/runs/.../assembly<br/>clean / captioned MP4 / ffprobe / manifest"]
        QcOutputs["outputs/studio/runs/.../qc<br/>technical QC / ffprobe / manifest"]
        AuditExports["outputs/studio/audits<br/>ZIP + SHA-256 sidecar"]
        ProductionArtifacts["outputs/productions<br/>media / logs / QC"]
        WindowsSapi["Windows System.Speech<br/>installed local voices"]
        MediaTools["FFmpeg / ffprobe<br/>resolved binary identity"]
    end

    subgraph ExternalSources["External supply-chain boundary"]
        GitHub["GitHub<br/>pinned repository commits"]
        PackageIndexes["PyTorch cu130 / PyPI / npm<br/>locked or package-managed dependencies"]
        HuggingFace["Hugging Face<br/>pinned model revisions"]
    end

    subgraph MiniMaxBoundary["MiniMax service boundary"]
        MiniMaxApi["MiniMax V2 API<br/>billable submit / query"]
        OutputCdn["Output CDN<br/>MP4 URL"]
    end

    subgraph ElevenLabsBoundary["ElevenLabs service boundary"]
        ElevenLabsApi["ElevenLabs with-timestamps API<br/>billable single POST"]
    end

    Operator --> Setup
    RuntimeLock --> Setup
    GitHub --> Setup
    PackageIndexes --> Setup
    Setup --> Venv
    Setup --> Comfy
    Setup --> GgufNode
    Setup --> TurboNode

    Operator -->|"-AcceptLicense"| Downloader
    ModelManifest --> Downloader
    HuggingFace --> Downloader
    Downloader --> Models

    Operator --> Doctor
    RuntimeLock --> Doctor
    ModelManifest --> Doctor
    Doctor -->|"read-only checks"| Venv
    Doctor -->|"HEAD / nodes / resources"| Comfy
    Doctor -->|"size / optional SHA-256"| Models
    Doctor -->|"profile contract"| LowWorkflow
    Doctor -->|"Turbo wiring / merge contract"| TurboWorkflow
    Doctor -->|"Q4 loader / 0.4MP / 8-step contract"| Q4TurboWorkflow
    Doctor -->|"INT8 + Q4 / 20-step contract"| OfficialQ4Workflow
    Doctor -->|"INT8 + Q4 Turbo / 8-step contract"| OfficialQ4TurboWorkflow
    Doctor -->|"profile contract"| OfficialWorkflow

    Operator --> Launcher
    Doctor -->|"Ready gate"| Launcher
    Launcher -->|"start and end only"| Metrics
    Metrics -->|"read-only snapshot"| HardwareMetrics
    Launcher -->|"loopback + all custom nodes disabled<br/>profile exact allowlist<br/>Dynamic VRAM or emergency CPU VAE"| Comfy
    LowWorkflow -->|"lowvram only"| Comfy
    TurboWorkflow -->|"lowvram_turbo only"| Comfy
    Q4TurboWorkflow -->|"lowvram_q4_turbo only"| Comfy
    OfficialWorkflow -->|"official only"| Comfy
    OfficialQ4Workflow -->|"official_q4 only"| Comfy
    OfficialQ4TurboWorkflow -->|"official_q4_turbo only"| Comfy
    GgufNode --> Comfy
    TurboNode -->|"optional LoRA + sampler"| Comfy
    Models --> Comfy
    Comfy --> Outputs

    Operator --> ApiWrapper
    Env --> ApiCli
    ApiWrapper --> ApiCli
    ApiCli -->|"POST only with --confirm-billable<br/>Bearer, redirects rejected"| MiniMaxApi
    MiniMaxApi -->|"task id / status"| ApiCli
    MiniMaxApi -->|"completed MP4 location"| OutputCdn
    OutputCdn -->|"GET without Authorization"| ApiCli
    ApiCli --> Outputs

    Operator --> StudioSetup
    PackageIndexes -->|"npm registry"| StudioSetup
    StudioFrontend --> StudioSetup
    StudioSetup --> StudioBuild
    Operator --> StudioLauncher
    StudioLauncher -->|"python -m tools.studio.server"| HttpLifecycle
    StudioLauncher -->|"acquire before service construction"| WorkspaceLock
    HttpLifecycle -->|"parsed request"| StudioBackend
    HttpLifecycle -->|"shutdown: interrupt parse sockets<br/>drain parsed handlers"| ShutdownGate
    StudioBackend -->|"drain provider recovery<br/>worker lanes + DB interrupt writer"| ShutdownGate
    ShutdownGate -->|"all drained: release"| WorkspaceLock
    ShutdownGate -->|"timeout/failure: retain"| WorkspaceLock
    StudioBuild -->|"normal: static dist<br/>Dev: Vite"| StudioUi
    StudioUi -->|"GET: loopback Host<br/>POST: cookie/session + Origin"| HttpLifecycle
    ProductionLedgers -->|"read / refresh index"| StudioBackend
    ProductionArtifacts -->|"registered artifacts only"| StudioBackend
    StudioBackend -->|"atomic artifact + job + stage<br/>terminal transaction"| StudioDb
    StudioBackend -->|"prepared UUID / startup scan<br/>public state / manual resume"| ProviderTasks
    StudioBackend -->|"start without provider I/O"| ProviderRecovery
    ProviderRecovery -->|"bounded exact-ID observation"| ProviderTasks
    ProviderRecovery -->|"exact GET + targeted cancel<br/>never generation POST for known/cancelled task"| Comfy
    StudioBackend -->|"atomic identical-request claim"| VideoClaims
    VideoClaims -->|"single winner queues"| GpuLane
    VideoClaims --> StudioDb
    ProviderTasks -->|"same Run / append recovery attempt<br/>single CAS winner"| GpuLane
    ProviderTasks -->|"provider + job + attempt + artifacts<br/>atomic terminal state"| StudioDb
    ProviderTasks -->|"explicit cancel: job + attempt + fence<br/>one atomic timestamp"| StudioDb
    ProviderTasks -->|"terminal recovery + exact video checkpoint<br/>same transaction"| PipelineClaims
    StudioDb -->|"append"| StudioEvents
    StudioEvents -->|"verified restore<br/>revision / run / cost approval<br/>stage attempt / historical job link<br/>hash-verified Studio artifacts"| StudioDb
    StudioEvents -->|"full-chain health / degraded warning"| StudioBackend
    StudioBackend -->|"POST /api/productions/{id}/execute-local-pipeline<br/>schema v4 / immutable zero-cost Run"| LocalPipelineContract
    LocalPipelineContract -->|"canonical pipeline key / exact allowlist"| LocalPipelineOrchestrator
    LocalPipelineOrchestrator -->|"Run + top-job dedupe<br/>protected normalized request"| PipelineClaims
    PipelineClaims -->|"ready checkpoint scan"| PipelineContinuationCoordinator
    PipelineContinuationCoordinator -->|"exact failed-admission ID repair<br/>single CAS winner / enqueue only<br/>video cache-only when checkpointed"| PipelineLane
    PipelineClaims -->|"initial or explicit top"| PipelineLane
    PipelineClaims --> StudioDb
    LocalPipelineOrchestrator -->|"parent cancel waits for child jobs"| StudioDb
    PipelineLane -->|"GPU child"| GpuLane
    PipelineLane -->|"default children"| DefaultLane
    StudioBackend -->|"local_comfyui / explicit execute<br/>prompt + seed only"| StudioComfyContract
    StudioComfyContract -->|"fixed graph + runtime/model/tool identity"| GpuLane
    StudioApiWorkflow --> StudioComfyContract
    RuntimeLock --> StudioComfyContract
    ModelManifest --> StudioComfyContract
    GpuLane -->|"one job at a time"| StudioComfyWorker
    DefaultLane -->|"SAPI child"| NarrationWorker
    DefaultLane -->|"one generated clip / timeline child"| TimelineWorker
    DefaultLane -->|"assembly child"| AssemblyWorker
    DefaultLane -->|"technical QC child"| QcWorker
    StudioComfyWorker -->|"new task: POST prompt with pre-issued ID<br/>known/cancel task: exact GET + targeted cancel only<br/>proxy and redirects rejected"| Comfy
    Comfy -->|"history output bound to submitted prefix"| StudioComfyWorker
    Models -->|"Windows: every-new-POST guarded SHA-256<br/>non-Windows: physical identity cache"| StudioComfyWorker
    StudioComfyWorker -->|"ffprobe / verified MP4"| MediaTools
    StudioComfyWorker -->|"production/cache marker fsync<br/>pre-issued prompt ID before POST<br/>terminal failure fsync before DB"| ExternalSubmissionState
    StudioComfyWorker -->|"atomic publish + SHA-256"| VideoGenerationOutputs
    VideoGenerationOutputs -->|"4 artifacts registered only with terminal success"| StudioBackend
    StudioBackend -->|"local_sapi / explicit execute<br/>persist job-attempt link before queue"| NarrationWorker
    NarrationWorker -->|"validated JSON file"| SapiHelper
    SapiHelper --> WindowsSapi
    WindowsSapi -->|"segment WAV"| NarrationWorker
    NarrationWorker -->|"atomic output + SHA-256"| NarrationOutputs
    NarrationOutputs -->|"exact path / kind / MIME / hash allowlist"| StudioBackend
    StudioBackend -->|"elevenlabs_tts + narration<br/>positive estimate + approval + confirm_billable<br/>cache checked before secret"| ExternalTtsContract
    ExternalTtsContract -->|"allowlisted fixed-model payload"| ElevenLabsWorker
    StudioSecrets -->|"resolve after all gates<br/>value never returned"| ElevenLabsWorker
    Env -->|"env, then .env, then DPAPI<br/>resolve after all gates"| ElevenLabsWorker
    ElevenLabsWorker -->|"exclusive marker before POST<br/>remove only after verified publish"| ExternalSubmissionState
    ElevenLabsWorker -->|"fixed HTTPS / xi-api-key<br/>redirects rejected / bounded deadline"| ElevenLabsApi
    ElevenLabsApi -->|"audio_base64 + character alignment<br/>request-id + character-cost"| ElevenLabsWorker
    ElevenLabsWorker -->|"MP3 decode / shell=false"| MediaTools
    ElevenLabsWorker -->|"atomic WAV / SRT / timing / manifest<br/>actual_cost remains null"| NarrationOutputs
    StudioBackend -->|"local_sapi timeline / explicit execute<br/>persist job-attempt link before queue"| TimelineWorker
    ProductionArtifacts -->|"same-production registered videos<br/>bytes + SHA-256 verified"| TimelineWorker
    TimelineWorker -->|"fixed clip names / shell=false<br/>1080x1920 / 24fps / hard cuts"| MediaTools
    MediaTools -->|"H.264 video-only / fresh ffprobe"| TimelineWorker
    TimelineWorker -->|"atomic output + SHA-256"| TimelineOutputs
    TimelineOutputs -->|"exact path / kind / MIME / hash allowlist"| StudioBackend
    StudioBackend -->|"same production/run IDs<br/>persist job-attempt link before queue"| AssemblyWorker
    ProductionArtifacts -->|"registered source video"| AssemblyWorker
    TimelineOutputs -->|"registered timeline preview video"| AssemblyWorker
    NarrationOutputs -->|"verified WAV / SRT"| AssemblyWorker
    AssemblyWorker -->|"shell=false / fixed policy"| MediaTools
    MediaTools -->|"H.264 + AAC / ffprobe facts"| AssemblyWorker
    AssemblyWorker -->|"atomic output + SHA-256"| AssemblyOutputs
    AssemblyOutputs -->|"exact path / kind / MIME / hash allowlist"| StudioBackend
    StudioBackend -->|"current-run attempt + variant only<br/>verified same-production cache chain"| QcWorker
    AssemblyOutputs -->|"verified clean / captioned master<br/>content-addressed owner may be a prior run"| QcWorker
    QcWorker -->|"shell=false / fixed checks"| MediaTools
    MediaTools -->|"probe / full decode / silence facts"| QcWorker
    QcWorker -->|"atomic JSON + SHA-256"| QcOutputs
    QcOutputs -->|"exact path / kind / MIME / hash allowlist"| StudioBackend
    StudioBackend -->|"entry hashes + scope tails<br/>text redaction / media opt-in"| AuditExports
    Operator --> StudioCli
    StudioCli -->|"set / status / delete"| StudioSecrets
    StudioCli -->|"test-video / workspace lock"| TestVideoOrchestrator
    TestVideoOrchestrator -->|"refresh + immutable local_sapi run<br/>narration -> timeline -> assembly -> QC"| StudioBackend
    StudioBackend -->|"terminal IDs / cache / hashes<br/>technical verdict"| TestVideoOrchestrator
    StudioSecrets -->|"configured status only"| StudioBackend
    Env -->|"configured status only"| StudioBackend

    classDef tracked fill:#e8f1ff,stroke:#2457a7,color:#10223f;
    classDef local fill:#e9f8ee,stroke:#247a3c,color:#12351d;
    classDef external fill:#fff3df,stroke:#9a6300,color:#432b00;
    classDef secret fill:#ffe8ee,stroke:#9c284b,color:#481023;

    class Setup,RuntimeLock,Downloader,ModelManifest,Doctor,Launcher,Metrics,LowWorkflow,TurboWorkflow,Q4TurboWorkflow,OfficialQ4Workflow,OfficialQ4TurboWorkflow,StudioApiWorkflow,ApiWrapper,ApiCli,ProductionLedgers,StudioSetup,StudioLauncher,StudioFrontend,StudioBackend,HttpLifecycle,ShutdownGate,ProviderRecovery,PipelineContinuationCoordinator,LocalPipelineContract,LocalPipelineOrchestrator,StudioComfyContract,StudioComfyWorker,NarrationWorker,ExternalTtsContract,ElevenLabsWorker,TimelineWorker,AssemblyWorker,QcWorker,SapiHelper,StudioCli,TestVideoOrchestrator tracked;
    class Venv,Comfy,GgufNode,TurboNode,Models,OfficialWorkflow,Outputs,HardwareMetrics,StudioBuild,StudioUi,StudioDb,VideoClaims,ProviderTasks,PipelineClaims,StudioEvents,ExternalSubmissionState,GpuLane,PipelineLane,DefaultLane,VideoGenerationOutputs,NarrationOutputs,TimelineOutputs,AssemblyOutputs,QcOutputs,AuditExports,ProductionArtifacts,WindowsSapi,MediaTools local;
    class GitHub,PackageIndexes,HuggingFace,MiniMaxApi,OutputCdn,ElevenLabsApi external;
    class Env,StudioSecrets secret;
```

HTTP終了境界は`HttpLifecycle`と`ShutdownGate`に分けています。全responseを`Connection: close`にし、終了時は未解析socketだけを遮断して解析済みservice処理をdrainします。provider recovery、worker lane、SQLite interruption writerがすべて終了した場合だけworkspace lockを解放し、timeout／例外時は再試行またはprocess終了までlockを保持します。

明示cancelはjob／attemptの中断と`provider_tasks.cancel_requested`を同じSQLite transaction・同じ時刻で確定します。その後のstartup／manual再照合は同じUUIDへのGETとtargeted cancelだけを使い、生成用`POST /prompt`を再送しません。未送信はlocal terminalへ確定し、running／404／一時的な照合不能はfenceを保持します。

Local経路のprompt/mediaはloopback ComfyUIへ渡ります。通常の`local_comfyui`は固定graphと実行環境を照合し、default workerを占有しないGPU FIFO laneから同じComfyUIへ接続します。schema v6の`local_video_generation_claims`が同一Run／cache／payloadのactive requestを1 jobへ集約し、`provider_tasks`はComfyUI UUID、state、origin/current attempt、CAS owner、DPAPI暗号化restart payloadを保持します。UUIDはmarkerとDBへ先に永続化してから`POST /prompt`へ渡し、応答ID完全一致を要求します。terminal provider failureはmarkerへ先にfsyncします。Studio再起動はHTTP起動を妨げないbackground coordinatorが担当し、旧job/attemptを復活させず失敗履歴として残し、同じRunへ新attempt/jobを追記して`GET /api/jobs/{id}`とhistory/cacheを照合します。既知taskは再POSTせず、404、旧IDなしmarker、runtime不一致は手動確認へfail closedにします。通常終了はprovider生成を継続し、明示cancelだけが対象jobのcancel endpointを呼びます。UIは公開stateだけを2秒pollingし、実照合時刻と状態だけをstatus-only live regionで通知し、手動resumeも同じtaskへ限定します。`local_pipeline`は`POST /api/productions/{production_id}/execute-local-pipeline`でrequest schema v4の厳密なbodyを受け、6 requested stage（`video_generation`、`narration`、`captions`、`timeline`、`assembly`、`qc`）を一つのimmutableな0円Runへ束ねます。専用pipeline laneがGPU childとdefault childを協調し、ComfyUI動画生成→SAPI→one-clip timeline→assembly→QCの5 stageを実行します。schema v6の`local_pipeline_claims`はcanonical key、公開continuation state、source job/attempt、再開回数と、現在のWindowsユーザーだけが復号できる完全な正規化request暗号文を保持します。provider復旧成功と動画checkpointは同一transactionで`ready`へ確定し、単一coordinatorがCASで新topを一件だけenqueueします。新topのvideo childは指定checkpointを含む検証済みcacheだけを許可し、欠損・改ざん・lineage不一致ではprovider task作成や`POST /prompt`へ進まず停止します。SAPI以降は同じRunで通常どおり実行し、成功topとclaim、失敗topとclaimもそれぞれ同一transactionで確定します。parent cancelはchild job/processのjoin後にterminalへ確定し、復旧結果が後から成功しても`cancelled`のまま自動継続しません。raw prompt/scriptはSQLite、event、job metadataへ平文複製せず、ComfyUI再開payloadとpipeline継続requestだけをDPAPI暗号文として保存し、成功または確定cancelで消去します。明示的な`workflow.json`、`timings`、`manifest` artifactにはcontentが含まれ得ます。local pipelineはElevenLabs、MiniMax API、費用承認を使いません。API経路のprompt/mediaはMiniMaxの外部境界を越えます。Bearer key付きrequestはredirectを拒否し、MP4 CDN downloadにはkeyを付けません。Studioはsession保護されたloopback内で台帳とartifactを索引化します。`test-video` CLIは同じworkspaceをlockし、既存serviceをmain threadから順番に呼んでローカルMP4と監査IDをまとめます。費用gateとpayload確認を通った`elevenlabs_tts`だけはナレーション本文と固定設定をElevenLabsへ1回送信します。
