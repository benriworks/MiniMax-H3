$ErrorActionPreference = 'Stop'
$productionRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$mediaRoot = 'C:\Users\mono_\MiniMaxH3'
$motionRoot = Join-Path $repoRoot 'outputs/content-projects/CONTENT_20261101_tibo_28day_full/motions/v03'
$inputRoot = Join-Path $motionRoot 'input'
if (Get-NetTCPConnection -LocalPort 8192 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8192 is already in use; inspect, do not replace it.' }
New-Item -ItemType Directory -Force -Path $motionRoot,$inputRoot | Out-Null
$runtimeArgs = @('main.py','--listen','127.0.0.1','--port','8192','--preview-method','none','--disable-pinned-memory','--output-directory',('"'+$motionRoot+'"'),'--input-directory',('"'+$inputRoot+'"'),'--disable-all-custom-nodes','--whitelist-custom-nodes','ComfyUI-GGUF','ComfyUI-MiniMax-H3-Turbo','--enable-dynamic-vram','--reserve-vram','2.0','--disable-auto-launch','--disable-api-nodes')
$process = Start-Process -FilePath (Join-Path $mediaRoot '.venv/Scripts/python.exe') -ArgumentList $runtimeArgs -WorkingDirectory (Join-Path $mediaRoot 'runtime/ComfyUI') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $motionRoot 'service.stdout.log') -RedirectStandardError (Join-Path $motionRoot 'service.stderr.log') -PassThru
@{pid=$process.Id;port=8192;output=$motionRoot;input=$inputRoot;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $motionRoot 'service.json') -Encoding utf8
Write-Output "Dedicated local H3 started: PID $($process.Id), port 8192"
