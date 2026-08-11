[CmdletBinding()]
param(
    [ValidateSet('lowvram', 'lowvram_turbo', 'official')]
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
if ($Profile -eq 'lowvram_turbo') {
    Write-Host 'Workflow: workflows\minimax_h3_t2v_lowvram_turbo.json (Turbo LoRA, 6 steps, low_vram merge)'
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
