[CmdletBinding()]
param(
    [switch] $SkipBuild,
    [switch] $SkipBrowserInstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'studio'
$frontendPackage = Join-Path $frontendRoot 'package.json'
$frontendLock = Join-Path $frontendRoot 'package-lock.json'
$serverModulePath = Join-Path $projectRoot 'tools\studio\server.py'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$windowsCaptureProject = Join-Path $projectRoot 'native\windows-capture-helper\windows-capture-helper.csproj'
$windowsCaptureHelper = Join-Path $projectRoot 'native\windows-capture-helper\bin\Release\net8.0-windows\windows-capture-helper.dll'

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

if (($env:OS -eq 'Windows_NT') -and (Test-Path -LiteralPath $windowsCaptureProject -PathType Leaf)) {
    $dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($null -eq $dotnetCommand) {
        Write-Warning 'The optional Windows capture capability helper was not built because .NET 8+ SDK was not found.'
    }
    else {
        $dotnetSdkLines = @(& $dotnetCommand.Source --list-sdks 2>$null)
        $hasSupportedDotnetSdk = $LASTEXITCODE -eq 0 -and @(
            $dotnetSdkLines | Where-Object {
                $sdkVersionText = ($_ -split '\s+')[0]
                $sdkMajorText = ($sdkVersionText -split '\.')[0]
                $sdkMajor = 0
                [int]::TryParse($sdkMajorText, [ref]$sdkMajor) -and $sdkMajor -ge 8
            }
        ).Count -gt 0
        if (-not $hasSupportedDotnetSdk) {
            Write-Warning 'The optional Windows capture capability helper was not built because a .NET 8+ SDK was not found. Core Studio setup will continue.'
        }
        else {
            try {
                Invoke-External `
                    -FilePath $dotnetCommand.Source `
                    -ArgumentList @('build', $windowsCaptureProject, '--configuration', 'Release', '--nologo') `
                    -Description 'Build the non-recording Windows capture capability helper'
                if (-not (Test-Path -LiteralPath $windowsCaptureHelper -PathType Leaf)) {
                    throw "Windows capture capability helper output was not found: $windowsCaptureHelper"
                }
                Write-Host 'Windows capture capability helper built. Inspection runs only from the explicit capture-tab action.'
            }
            catch {
                Write-Warning 'The optional Windows capture capability helper could not be built. Core Studio setup will continue; the capture tab will report the capability as blocked.'
            }
        }
    }
}

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

$playwrightCli = Join-Path $frontendRoot 'node_modules\playwright\cli.js'
$playwrightDoctor = Join-Path $projectRoot 'tools\studio\playwright_doctor.mjs'
$remotionDoctor = Join-Path $projectRoot 'tools\studio\remotion_doctor.mjs'
if (-not (Test-Path -LiteralPath $playwrightCli -PathType Leaf)) {
    throw "Pinned Playwright CLI was not found after npm install: $playwrightCli"
}
if (-not (Test-Path -LiteralPath $playwrightDoctor -PathType Leaf)) {
    throw "Playwright doctor was not found: $playwrightDoctor"
}
if (-not (Test-Path -LiteralPath $remotionDoctor -PathType Leaf)) {
    throw "Remotion doctor was not found: $remotionDoctor"
}

# Capture jobs intentionally ignore Node injection and custom browser-cache
# variables. Install and diagnose Chromium under the same environment contract
# so setup cannot pass with a binary that the runtime will later refuse to use.
$playwrightEnvironmentNames = @('NODE_OPTIONS', 'NODE_PATH', 'PLAYWRIGHT_BROWSERS_PATH') + @(
    Get-ChildItem Env: | Where-Object { $_.Name -like 'REMOTION_*' } | ForEach-Object { $_.Name }
) | Select-Object -Unique
$savedPlaywrightEnvironment = @{}
foreach ($environmentName in $playwrightEnvironmentNames) {
    $environmentItem = Get-Item -LiteralPath "Env:$environmentName" -ErrorAction SilentlyContinue
    if ($null -ne $environmentItem) {
        $savedPlaywrightEnvironment[$environmentName] = $environmentItem.Value
        Remove-Item -LiteralPath "Env:$environmentName"
    }
}
try {
    if (-not $SkipBrowserInstall) {
        Invoke-External `
            -FilePath $nodeCommand.Source `
            -ArgumentList @($playwrightCli, 'install', 'chromium') `
            -Description 'Install pinned Playwright Chromium' `
            -WorkingDirectory $projectRoot
    }
    Invoke-External `
        -FilePath $nodeCommand.Source `
        -ArgumentList @($playwrightDoctor) `
        -Description 'Verify pinned Playwright Chromium' `
        -WorkingDirectory $projectRoot
    Invoke-External `
        -FilePath $nodeCommand.Source `
        -ArgumentList @($remotionDoctor, '--write-attestation') `
        -Description 'Attest installed Remotion runtime files' `
        -WorkingDirectory $projectRoot
    Invoke-External `
        -FilePath $nodeCommand.Source `
        -ArgumentList @($remotionDoctor) `
        -Description 'Verify pinned Remotion renderer dependencies' `
        -WorkingDirectory $projectRoot
}
finally {
    foreach ($environmentName in $savedPlaywrightEnvironment.Keys) {
        Set-Item -LiteralPath "Env:$environmentName" -Value $savedPlaywrightEnvironment[$environmentName]
    }
}

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
