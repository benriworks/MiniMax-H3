[CmdletBinding()]
param(
    [switch] $Update,

    [Parameter(DontShow = $true)]
    [switch] $LoadHelpersOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvRoot = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$runtimeRoot = Join-Path $projectRoot 'runtime'
$comfyRoot = Join-Path $runtimeRoot 'ComfyUI'
$ggufRoot = Join-Path $comfyRoot 'custom_nodes\ComfyUI-GGUF'
$turboRoot = Join-Path $comfyRoot 'custom_nodes\ComfyUI-MiniMax-H3-Turbo'
$runtimeLockPath = Join-Path $projectRoot 'runtime-lock.json'
$setupHelpersPath = Join-Path $projectRoot 'tools\setup_lock_helpers.ps1'

if (-not (Test-Path -LiteralPath $setupHelpersPath -PathType Leaf)) {
    throw "Setup helper was not found: $setupHelpersPath"
}
. $setupHelpersPath

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [Parameter(Mandatory = $true)][string[]] $ArgumentList,
        [Parameter(Mandatory = $true)][string] $Description
    )

    Write-Host "==> $Description"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Get-CommandPath {
    param([Parameter(Mandatory = $true)][string] $Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

if ($LoadHelpersOnly) {
    return
}

if (-not (Test-Path -LiteralPath $runtimeLockPath -PathType Leaf)) {
    throw "Tracked runtime lock was not found: $runtimeLockPath"
}
$runtimeLock = Get-Content -LiteralPath $runtimeLockPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($runtimeLock.schema_version -ne 1) {
    throw "Unsupported runtime lock schema version: $($runtimeLock.schema_version)"
}
if ($runtimeLock.target.os -ne 'Windows' -or $runtimeLock.target.python -ne '3.12') {
    throw 'runtime-lock.json must target Windows and CPython 3.12.'
}

$requirementsLock = Join-Path $projectRoot ([string]$runtimeLock.requirements_file)
if (-not (Test-Path -LiteralPath $requirementsLock -PathType Leaf)) {
    throw "Tracked Python requirements lock was not found: $requirementsLock"
}

$gitPath = Get-CommandPath -Name 'git'
if ($null -eq $gitPath) {
    throw 'Git was not found on PATH. Install Git for Windows and rerun setup-local.ps1.'
}

$uvPath = Get-CommandPath -Name 'uv'
$pythonPath = Get-CommandPath -Name 'python'
$pyPath = Get-CommandPath -Name 'py'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if ($null -ne $uvPath) {
        Invoke-External -FilePath $uvPath -ArgumentList @(
            'venv', $venvRoot, '--python', '3.12'
        ) -Description 'Create CPython 3.12 virtual environment with uv'
    }
    elseif ($null -ne $pyPath) {
        Invoke-External -FilePath $pyPath -ArgumentList @(
            '-3.12', '-m', 'venv', $venvRoot
        ) -Description 'Create CPython 3.12 virtual environment with the Python launcher'
    }
    elseif ($null -ne $pythonPath) {
        Invoke-External -FilePath $pythonPath -ArgumentList @(
            '-m', 'venv', $venvRoot
        ) -Description 'Create virtual environment with Python'
    }
    else {
        throw 'Neither uv nor Python was found. Install uv or CPython 3.12 and retry.'
    }
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Virtual environment Python was not created: $venvPython"
}

$pythonVersionText = (& $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pythonVersionText)) {
    throw 'Could not determine the virtual environment Python version.'
}
$pythonVersion = [version]$pythonVersionText.Trim()
if ($pythonVersion.Major -ne 3 -or $pythonVersion.Minor -ne 12) {
    throw "This runtime lock targets CPython 3.12; found $pythonVersion. Recreate .venv with Python 3.12."
}
Write-Host "Python $pythonVersion (locked target: 3.12)"

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$comfySpec = $runtimeLock.repositories.comfyui
$ggufSpec = $runtimeLock.repositories.comfyui_gguf
$turboSpec = $runtimeLock.repositories.minimax_h3_turbo
Set-GitRepositoryRevision `
    -Repository ([string]$comfySpec.repository) `
    -Revision ([string]$comfySpec.revision) `
    -Destination $comfyRoot `
    -Label 'ComfyUI' `
    -UseLatest:$Update

New-Item -ItemType Directory -Force -Path (Join-Path $comfyRoot 'custom_nodes') | Out-Null
Set-GitRepositoryRevision `
    -Repository ([string]$turboSpec.repository) `
    -Revision ([string]$turboSpec.revision) `
    -Destination $turboRoot `
    -Label 'ComfyUI-MiniMax-H3-Turbo' `
    -UseLatest:$Update

Set-GitRepositoryRevision `
    -Repository ([string]$ggufSpec.repository) `
    -Revision ([string]$ggufSpec.revision) `
    -Destination $ggufRoot `
    -Label 'ComfyUI-GGUF' `
    -UseLatest:$Update

$comfyRequirements = Join-Path $comfyRoot 'requirements.txt'
$ggufRequirements = Join-Path $ggufRoot 'requirements.txt'
if (-not (Test-Path -LiteralPath $comfyRequirements -PathType Leaf)) {
    throw "ComfyUI requirements were not found: $comfyRequirements"
}
if (-not (Test-Path -LiteralPath $ggufRequirements -PathType Leaf)) {
    throw "ComfyUI-GGUF requirements were not found: $ggufRequirements"
}

$torchPackages = $runtimeLock.pytorch.packages

if ($null -ne $uvPath) {
    $torchInstallArguments = Get-TorchInstallArguments `
        -UseUv $true `
        -PythonPath $venvPython `
        -RuntimeLock $runtimeLock `
        -Update:$Update
    Invoke-External `
        -FilePath $uvPath `
        -ArgumentList $torchInstallArguments `
        -Description 'Install PyTorch CUDA 13.0 packages'
    if ($Update) {
        Invoke-External -FilePath $uvPath -ArgumentList @(
            'pip', 'install', '--python', $venvPython, '--upgrade',
            '-r', $comfyRequirements, '-r', $ggufRequirements, 'huggingface_hub'
        ) -Description 'Explicitly update unpinned runtime dependencies'
    }
    else {
        Invoke-External -FilePath $uvPath -ArgumentList @(
            'pip', 'install', '--python', $venvPython, '-r', $requirementsLock
        ) -Description 'Install exact Windows/Python 3.12 runtime dependency lock'
    }
}
else {
    $torchInstallArguments = Get-TorchInstallArguments `
        -UseUv $false `
        -PythonPath $venvPython `
        -RuntimeLock $runtimeLock `
        -Update:$Update
    Invoke-External `
        -FilePath $venvPython `
        -ArgumentList $torchInstallArguments `
        -Description 'Install PyTorch CUDA 13.0 packages'
    if ($Update) {
        Invoke-External -FilePath $venvPython -ArgumentList @(
            '-m', 'pip', 'install', '--upgrade',
            '-r', $comfyRequirements, '-r', $ggufRequirements, 'huggingface_hub'
        ) -Description 'Explicitly update unpinned runtime dependencies'
    }
    else {
        Invoke-External -FilePath $venvPython -ArgumentList @(
            '-m', 'pip', 'install', '-r', $requirementsLock
        ) -Description 'Install exact Windows/Python 3.12 runtime dependency lock'
    }
}

$torchProbeCode = (
    "import json, torch, torchvision, torchaudio; " +
    "print(json.dumps({'torch': torch.__version__, " +
    "'torchvision': torchvision.__version__, " +
    "'torchaudio': torchaudio.__version__, " +
    "'cuda': torch.version.cuda or 'none'}))"
)
$torchProbe = & $venvPython -c $torchProbeCode
if ($LASTEXITCODE -ne 0) {
    throw 'PyTorch import failed after installation.'
}
$installedTorch = $torchProbe | Select-Object -Last 1 | ConvertFrom-Json
if ($installedTorch.cuda -ne [string]$runtimeLock.pytorch.cuda_build) {
    throw "Expected CUDA build $($runtimeLock.pytorch.cuda_build), found $($installedTorch.cuda)."
}
if (-not $Update) {
    foreach ($packageName in @('torch', 'torchvision', 'torchaudio')) {
        $expectedVersion = [string]$torchPackages.$packageName
        $actualVersion = [string]$installedTorch.$packageName
        if ($actualVersion -ne $expectedVersion) {
            throw "Locked $packageName version is $expectedVersion, found $actualVersion."
        }
    }
}
Write-Host "PyTorch $($installedTorch.torch) / torchvision $($installedTorch.torchvision) / torchaudio $($installedTorch.torchaudio) / CUDA $($installedTorch.cuda)"

Write-Host ''
if ($Update) {
    Write-Warning 'Unpinned update mode completed. Re-run validation and intentionally refresh tracked locks before treating this combination as reproducible.'
}
else {
    Write-Host 'Locked local runtime setup is complete.'
}
Write-Host 'Next: .\download-models.ps1 -Profile lowvram -AcceptLicense'
Write-Host 'Then: .\run-local.ps1'
Write-Host 'Optional Turbo: .\download-models.ps1 -Profile lowvram_turbo -AcceptLicense'
