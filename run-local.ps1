[CmdletBinding()]
param(
    [ValidateSet('lowvram', 'lowvram_turbo', 'lowvram_q4_turbo', 'official', 'official_q4', 'official_q4_turbo')]
    [string] $Profile = 'lowvram',

    [ValidateRange(1, 65535)]
    [int] $Port = 8188,

    [switch] $EmergencyLowVram,

    [switch] $NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$comfyRoot = Join-Path $projectRoot 'runtime\ComfyUI'
$comfyMain = Join-Path $comfyRoot 'main.py'
$doctor = Join-Path $projectRoot 'tools\local_doctor.py'
$metricsHelper = Join-Path $projectRoot 'tools\system_metrics.ps1'
$outputRoot = Join-Path $projectRoot 'outputs'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Virtual environment not found. Run: .\setup-local.ps1"
}
if (-not (Test-Path -LiteralPath $comfyMain -PathType Leaf)) {
    throw "ComfyUI not found. Run: .\setup-local.ps1"
}
if (-not (Test-Path -LiteralPath $doctor -PathType Leaf)) {
    throw "Local doctor not found: $doctor"
}
if (-not (Test-Path -LiteralPath $metricsHelper -PathType Leaf)) {
    throw "System metrics helper not found: $metricsHelper"
}

. $metricsHelper

& $venvPython -B $doctor --root $projectRoot --profile $Profile
$doctorExit = $LASTEXITCODE
if ($doctorExit -ne 0) {
    Write-Error "Local prerequisites failed. Install/repair models with: .\download-models.ps1 -Profile $Profile -AcceptLicense"
    exit $doctorExit
}

$existingListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($null -ne $existingListener) {
    throw "Port $Port is already in use. Choose another port with -Port."
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$comfyArguments = @(
    $comfyMain,
    '--listen', '127.0.0.1',
    '--port', $Port.ToString(),
    '--preview-method', 'none',
    '--disable-pinned-memory',
    '--output-directory', $outputRoot
)

# ComfyUI imports every top-level custom_nodes entry by default. Keep the
# executable plugin set closed so Studio can attest the live process before a
# GPU submission. Turbo profiles opt into their one additional pinned node.
$allowedCustomNodes = @('ComfyUI-GGUF')
if ($Profile -in @('lowvram_turbo', 'lowvram_q4_turbo', 'official_q4_turbo')) {
    $allowedCustomNodes += 'ComfyUI-MiniMax-H3-Turbo'
}
$comfyArguments += '--disable-all-custom-nodes'
$comfyArguments += '--whitelist-custom-nodes'
$comfyArguments += $allowedCustomNodes

if ($EmergencyLowVram) {
    $comfyArguments += @('--novram', '--cpu-vae')
}
else {
    $comfyArguments += '--enable-dynamic-vram'
}
if ($NoBrowser) {
    $comfyArguments += '--disable-auto-launch'
}
else {
    $comfyArguments += '--auto-launch'
}

Write-Host "Starting ComfyUI at http://127.0.0.1:$Port"
Write-Host "Profile: $Profile"
Write-Host "Custom nodes: $($allowedCustomNodes -join ', ') (all others disabled)"
Write-Host 'Profile selection validates prerequisites; it does not auto-load or switch the ComfyUI workflow.'
if ($Profile -eq 'lowvram_turbo') {
    Write-Host 'Open manually: workflows\minimax_h3_t2v_lowvram_turbo.json (Turbo LoRA, 6 steps, low_vram merge)'
}
elseif ($Profile -eq 'lowvram_q4_turbo') {
    Write-Host 'Open manually: workflows\minimax_h3_t2v_lowvram_q4_turbo.json (Q4 text encoder + Turbo LoRA, 0.4 MP, 8 steps, low_vram merge)'
}
elseif ($Profile -eq 'official_q4') {
    Write-Host 'Open manually: workflows\minimax_h3_t2v_official_q4.json (official INT8 diffusion + Q4 text encoder, 0.4 MP, 20 steps)'
}
elseif ($Profile -eq 'official_q4_turbo') {
    Write-Host 'Open manually: workflows\minimax_h3_t2v_official_q4_turbo.json (official INT8 diffusion + Q4 text encoder + Turbo LoRA, 0.4 MP, 8 steps, low_vram merge)'
}
elseif ($Profile -eq 'lowvram') {
    Write-Host 'Open manually: workflows\minimax_h3_t2v_lowvram.json (base GGUF, 0.2 MP, 20 steps)'
}
else {
    Write-Host 'Open manually: Template Library -> Video -> MiniMax H3 official T2V (do not use the tracked GGUF workflows)'
}
if ($EmergencyLowVram) {
    Write-Warning 'Emergency --novram --cpu-vae mode is enabled; generation will be substantially slower.'
}
else {
    Write-Host 'VRAM mode: Dynamic VRAM (no --lowvram flag)'
}

$startedAt = Get-Date
Show-SystemMetrics -Phase START -StartedAt $startedAt
$comfyExit = 1
$locationPushed = $false
try {
    Push-Location $comfyRoot
    $locationPushed = $true
    & $venvPython @comfyArguments
    $comfyExit = $LASTEXITCODE
}
finally {
    if ($locationPushed) {
        Pop-Location
    }
    Show-SystemMetrics -Phase END -StartedAt $startedAt
}
exit $comfyExit
