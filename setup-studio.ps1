[CmdletBinding()]
param(
    [switch] $SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'studio'
$frontendPackage = Join-Path $frontendRoot 'package.json'
$frontendLock = Join-Path $frontendRoot 'package-lock.json'
$serverModulePath = Join-Path $projectRoot 'tools\studio\server.py'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [Parameter(Mandatory = $true)][string[]] $ArgumentList,
        [Parameter(Mandatory = $true)][string] $Description,
        [string] $WorkingDirectory = $projectRoot
    )

    Write-Host "==> $Description"
    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$Description failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $serverModulePath -PathType Leaf)) {
    throw "Studio backend was not found: $serverModulePath"
}
if (-not (Test-Path -LiteralPath $frontendPackage -PathType Leaf)) {
    throw "Studio frontend package was not found: $frontendPackage"
}

$pythonPath = $null
$pythonArguments = @()
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonPath = $venvPython
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        $pythonPath = $pythonCommand.Source
    }
    else {
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -ne $pyLauncher) {
            $pythonPath = $pyLauncher.Source
            $pythonArguments = @('-3')
        }
    }
}
if ($null -eq $pythonPath) {
    throw 'Python 3 was not found. Install Python 3 and rerun setup-studio.ps1.'
}

Invoke-External `
    -FilePath $pythonPath `
    -ArgumentList (@($pythonArguments) + @(
        '-B', '-c',
        "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or later is required'; import tools.studio.server, tools.studio.cli"
    )) `
    -Description 'Verify the Studio backend module'

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand) {
    throw 'Node.js was not found. Install Node.js 20.19+ (20.x) or 22.12+ and rerun setup-studio.ps1.'
}
$nodeVersionText = (& $nodeCommand.Source --version | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($nodeVersionText)) {
    throw 'Could not determine the Node.js version.'
}
$nodeVersion = [version]$nodeVersionText.Trim().TrimStart('v')
$minimumNode20Version = [version]'20.19.0'
$minimumNode22Version = [version]'22.12.0'
$supportedNode = (
    ($nodeVersion.Major -eq 20 -and $nodeVersion -ge $minimumNode20Version) -or
    ($nodeVersion -ge $minimumNode22Version)
)
if (-not $supportedNode) {
    throw "Node.js 20.19+ (20.x) or 22.12+ is required; found $nodeVersion. Node.js 21 and Node.js 22.0-22.11 are not supported by Vite 8."
}
Write-Host "Node.js $nodeVersion"

$npmCommand = Get-Command npm -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    throw 'npm was not found. Install Node.js 20.19+ (20.x) or 22.12+ and rerun setup-studio.ps1.'
}

$installArguments = if (Test-Path -LiteralPath $frontendLock -PathType Leaf) {
    @('ci')
}
else {
    @('install')
}
Invoke-External `
    -FilePath $npmCommand.Source `
    -ArgumentList $installArguments `
    -Description 'Install Studio frontend dependencies' `
    -WorkingDirectory $frontendRoot

if (-not $SkipBuild) {
    Invoke-External `
        -FilePath $npmCommand.Source `
        -ArgumentList @('run', 'build') `
        -Description 'Build the Studio frontend' `
        -WorkingDirectory $frontendRoot
}

Write-Host ''
Write-Host 'MiniMaxH3 Studio setup is complete.'
if ($SkipBuild) {
    Write-Host 'Development launch: .\run-studio.ps1 -Dev'
}
else {
    Write-Host 'Launch: .\run-studio.ps1'
}
