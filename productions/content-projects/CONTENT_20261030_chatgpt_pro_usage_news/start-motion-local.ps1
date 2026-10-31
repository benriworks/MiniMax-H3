$ErrorActionPreference='Stop'
$TaskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$TaskRuntimeRoot='C:\Users\mono_\MiniMaxH3'
$TaskOutput=Join-Path $TaskRoot 'outputs\content-projects\CONTENT_20261030_chatgpt_pro_usage_news\motions\v01'
$TaskInput=Join-Path $TaskOutput 'input'
$TaskUser=Join-Path $TaskOutput 'comfy-user'
New-Item -ItemType Directory -Force -Path $TaskOutput,$TaskInput,$TaskUser | Out-Null
if(Get-NetTCPConnection -LocalPort 8191 -State Listen -ErrorAction SilentlyContinue){throw '8191 is occupied; inspect ownership, do not restart it'}
$TaskDoctorText=& (Join-Path $TaskRuntimeRoot '.venv\Scripts\python.exe') -B (Join-Path $TaskRuntimeRoot 'tools\local_doctor.py') --profile official_q4 --json
if($LASTEXITCODE -ne 0){throw 'Runtime preflight failed'}
$TaskDoctor=$TaskDoctorText|ConvertFrom-Json
if(-not $TaskDoctor.ready -or -not $TaskDoctor.locked_core_runtime_matches){throw 'Runtime readiness mismatch'}
$TaskDoctorText | Set-Content -LiteralPath (Join-Path $TaskOutput 'runtime-preflight.json') -Encoding utf8
$TaskArgs=@((Join-Path $TaskRuntimeRoot 'runtime\ComfyUI\main.py'),'--listen','127.0.0.1','--port','8191','--preview-method','none','--disable-pinned-memory','--output-directory',$TaskOutput,'--input-directory',$TaskInput,'--user-directory',$TaskUser,'--database-url',('sqlite:///'+(Join-Path $TaskUser 'comfyui.db').Replace('\','/')),'--disable-all-custom-nodes','--whitelist-custom-nodes','ComfyUI-GGUF','--enable-dynamic-vram','--reserve-vram','2.0','--disable-auto-launch','--disable-api-nodes')
$TaskProcess=Start-Process -FilePath (Join-Path $TaskRuntimeRoot '.venv\Scripts\python.exe') -ArgumentList $TaskArgs -WorkingDirectory $TaskRuntimeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TaskOutput 'comfy-stdout.log') -RedirectStandardError (Join-Path $TaskOutput 'comfy-stderr.log')
@{pid=$TaskProcess.Id;port=8191;output=$TaskOutput;input=$TaskInput;started_at=(Get-Date).ToUniversalTime().ToString('o');scope='Only this dedicated H3 service. No changes to existing productions or model settings.'}|ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path $TaskOutput 'service.json') -Encoding utf8
Write-Output ('Dedicated reaction H3 service PID '+$TaskProcess.Id)
$TaskReady=$false
for($TaskAttempt=0;$TaskAttempt -lt 30;$TaskAttempt++){
    try{
        $TaskStats=Invoke-RestMethod -Uri 'http://127.0.0.1:8191/system_stats' -TimeoutSec 2
        if($TaskStats.system.argv -contains $TaskOutput){$TaskReady=$true;break}
    }catch{}
    Start-Sleep -Seconds 1
}
if(-not $TaskReady){throw 'Service is not ready; inspect the startup log. No generation was submitted.'}
$TaskListener=Get-NetTCPConnection -LocalPort 8191 -State Listen
@{launcher_pid=$TaskProcess.Id;serving_pid=$TaskListener.OwningProcess;port=8191;output=$TaskOutput;input=$TaskInput;user_directory=$TaskUser;ready=$true}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $TaskOutput 'service-ready.json') -Encoding utf8
