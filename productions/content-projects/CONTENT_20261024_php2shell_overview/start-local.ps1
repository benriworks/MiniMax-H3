$ErrorActionPreference = 'Stop'
$TaskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$TaskOutput = Join-Path $TaskRoot 'outputs\content-projects\CONTENT_20261024_php2shell_overview\motion\v01'
New-Item -ItemType Directory -Force -Path $TaskOutput | Out-Null
if (Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue) { throw '8189 is occupied; inspect ownership.' }
$TaskDoctorText = & (Join-Path $TaskRoot '.venv\Scripts\python.exe') -B (Join-Path $TaskRoot 'tools\local_doctor.py') --profile official_q4 --json
if ($LASTEXITCODE -ne 0) { throw 'Runtime preflight failed' }
$TaskDoctor = $TaskDoctorText | ConvertFrom-Json
if (-not $TaskDoctor.ready -or -not $TaskDoctor.locked_core_runtime_matches) { throw 'Runtime readiness mismatch' }
$TaskDoctorText | Set-Content -LiteralPath (Join-Path $TaskOutput 'runtime-preflight.json') -Encoding utf8
$TaskArgs = @((Join-Path $TaskRoot 'runtime\ComfyUI\main.py'), '--listen', '127.0.0.1', '--port', '8189', '--preview-method', 'none', '--disable-pinned-memory', '--output-directory', $TaskOutput, '--disable-all-custom-nodes', '--whitelist-custom-nodes', 'ComfyUI-GGUF', '--enable-dynamic-vram', '--reserve-vram', '2.0', '--disable-auto-launch', '--disable-api-nodes')
$TaskProcess = Start-Process -FilePath (Join-Path $TaskRoot '.venv\Scripts\python.exe') -ArgumentList $TaskArgs -WorkingDirectory $TaskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TaskOutput 'comfy-stdout.log') -RedirectStandardError (Join-Path $TaskOutput 'comfy-stderr.log')
@{pid=$TaskProcess.Id;started_at=(Get-Date).ToUniversalTime().ToString('o');port=8189;output=$TaskOutput;arguments=$TaskArgs;scope='Dedicated PHP2Shell production only'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $TaskOutput 'service.json') -Encoding utf8
Write-Output ('Dedicated H3 service PID ' + $TaskProcess.Id)
