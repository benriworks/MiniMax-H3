$ErrorActionPreference='Stop'
$TaskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$TaskRuntimeRoot='C:\Users\mono_\MiniMaxH3'
$TaskOutput=Join-Path $TaskRoot 'outputs\content-projects\CONTENT_20261106_ai_bert_gpt_history\motions\v03-q2'
$TaskInput=Join-Path $TaskOutput 'input'
$TaskUser=Join-Path $TaskOutput 'comfy-user'
New-Item -ItemType Directory -Force -Path $TaskOutput,$TaskInput,$TaskUser | Out-Null
if(Get-NetTCPConnection -LocalPort 8192 -State Listen -ErrorAction SilentlyContinue){throw '8192 is occupied; inspect ownership instead of restarting it'}
$TaskDoctorText=& (Join-Path $TaskRuntimeRoot '.venv\Scripts\python.exe') -B (Join-Path $TaskRuntimeRoot 'tools\local_doctor.py') --profile lowvram_turbo --json
if($LASTEXITCODE -ne 0){throw 'Runtime preflight failed'}
$TaskDoctor=$TaskDoctorText|ConvertFrom-Json
if(-not $TaskDoctor.ready -or -not $TaskDoctor.locked_core_runtime_matches){throw 'Runtime readiness mismatch'}
$TaskDoctorText|Set-Content -LiteralPath (Join-Path $TaskOutput 'runtime-preflight.json') -Encoding utf8
$TaskArgs=@((Join-Path $TaskRuntimeRoot 'runtime\ComfyUI\main.py'),'--listen','127.0.0.1','--port','8192','--preview-method','none','--disable-pinned-memory','--output-directory',$TaskOutput,'--input-directory',$TaskInput,'--user-directory',$TaskUser,'--database-url',('sqlite:///'+(Join-Path $TaskUser 'comfyui.db').Replace('\','/')),'--disable-all-custom-nodes','--whitelist-custom-nodes','ComfyUI-GGUF','ComfyUI-MiniMax-H3-Turbo','--enable-dynamic-vram','--reserve-vram','2.0','--disable-auto-launch','--disable-api-nodes')
$TaskArgs+=@('--cache-none','--disable-smart-memory')
$TaskProcess=Start-Process -FilePath (Join-Path $TaskRuntimeRoot '.venv\Scripts\python.exe') -ArgumentList $TaskArgs -WorkingDirectory $TaskRuntimeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TaskOutput 'comfy-stdout.log') -RedirectStandardError (Join-Path $TaskOutput 'comfy-stderr.log')
@{launcher_pid=$TaskProcess.Id;port=8192;output=$TaskOutput;input=$TaskInput;user=$TaskUser;profile='lowvram_turbo';started_at=(Get-Date).ToUniversalTime().ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $TaskOutput 'service.json') -Encoding utf8
for($TaskAttempt=0;$TaskAttempt -lt 40;$TaskAttempt++){
    try{
        $TaskStats=Invoke-RestMethod -Uri 'http://127.0.0.1:8192/system_stats' -TimeoutSec 2
        if($TaskStats.system.argv -contains $TaskOutput){
            $TaskListener=Get-NetTCPConnection -LocalPort 8192 -State Listen
            @{launcher_pid=$TaskProcess.Id;serving_pid=$TaskListener.OwningProcess;port=8192;ready=$true;output=$TaskOutput}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $TaskOutput 'service-ready.json') -Encoding utf8
            Write-Output 'Dedicated local H3 Q4 Turbo service is ready on 8192';exit 0
        }
    }catch{}
    Start-Sleep -Seconds 1
}
throw 'Service is not ready; inspect startup logs. No generation was submitted.'
