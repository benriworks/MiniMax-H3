[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 8765,

    [switch] $Dev,

    [ValidateRange(1, 65535)]
    [int] $FrontendPort = 5173,

    [switch] $NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$serverModulePath = Join-Path $projectRoot 'tools\studio\server.py'
$frontendRoot = Join-Path $projectRoot 'studio'
$frontendPackage = Join-Path $frontendRoot 'package.json'
$frontendDist = Join-Path $frontendRoot 'dist'
$frontendIndex = Join-Path $frontendDist 'index.html'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Get-StudioPython {
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        return [PSCustomObject]@{ FilePath = $venvPython; PrefixArguments = @() }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        return [PSCustomObject]@{ FilePath = $pythonCommand.Source; PrefixArguments = @() }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        return [PSCustomObject]@{ FilePath = $pyLauncher.Source; PrefixArguments = @('-3') }
    }

    throw 'Python 3 was not found. Run .\setup-studio.ps1 after installing Python 3.'
}

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)][int] $PortNumber,
        [Parameter(Mandatory = $true)][string] $Label
    )

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback,
            $PortNumber
        )
        $listener.Start()
    }
    catch {
        throw "$Label port $PortNumber is already in use or cannot be bound to 127.0.0.1."
    }
    finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function ConvertTo-NativeArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string] $Value)

    if ($Value.Length -eq 0) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Start-StudioBackend {
    param(
        [Parameter(Mandatory = $true)] $Python,
        [Parameter(Mandatory = $true)][string[]] $Arguments
    )

    $allArguments = @($Python.PrefixArguments) + $Arguments
    $argumentText = ($allArguments | ForEach-Object {
        ConvertTo-NativeArgument -Value ([string]$_)
    }) -join ' '

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Python.FilePath
    $startInfo.Arguments = $argumentText
    $startInfo.WorkingDirectory = $projectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $process) {
        throw 'Studio backend process could not be started.'
    }
    return $process
}

function Wait-StudioEndpoint {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process] $Process,
        [Parameter(Mandatory = $true)][int] $PortNumber,
        [ValidateRange(1, 120)][int] $TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "Studio backend exited before becoming ready (exit code $($Process.ExitCode))."
        }

        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $client.Connect([System.Net.IPAddress]::Loopback, $PortNumber)
            return
        }
        catch [System.Net.Sockets.SocketException] {
            Start-Sleep -Milliseconds 150
        }
        finally {
            $client.Dispose()
        }
    }

    throw "Studio backend did not listen on 127.0.0.1:$PortNumber within $TimeoutSeconds seconds."
}

function Stop-StudioProcessTree {
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process] $Process)

    $pending = [System.Collections.Generic.Queue[int]]::new()
    $ordered = [System.Collections.Generic.List[int]]::new()
    $pending.Enqueue($Process.Id)
    while ($pending.Count -gt 0) {
        $currentId = $pending.Dequeue()
        $ordered.Add($currentId)
        try {
            $children = Get-CimInstance Win32_Process `
                -Filter "ParentProcessId = $currentId" `
                -ErrorAction Stop
            foreach ($child in $children) {
                $pending.Enqueue([int]$child.ProcessId)
            }
        }
        catch {
            # The exact process already held by this script is still stopped below.
        }
    }

    for ($index = $ordered.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $ordered[$index] -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $serverModulePath -PathType Leaf)) {
    throw "Studio backend was not found: $serverModulePath"
}

$python = Get-StudioPython
Assert-PortAvailable -PortNumber $Port -Label 'Backend'

$backendArguments = @(
    '-B', '-m', 'tools.studio.server',
    '--host', '127.0.0.1',
    '--port', $Port.ToString()
)

if (-not $Dev) {
    if (-not (Test-Path -LiteralPath $frontendIndex -PathType Leaf)) {
        throw "Studio frontend is not built: $frontendIndex. Run .\setup-studio.ps1 first, or use -Dev."
    }
    $backendArguments += @('--static-dir', $frontendDist)
}

$backendProcess = $null
$previousApiBase = $env:VITE_STUDIO_API_BASE
$previousSessionToken = $env:MINIMAXH3_STUDIO_SESSION_TOKEN
$previousDevToken = $env:MINIMAXH3_STUDIO_DEV_TOKEN
$randomBytes = New-Object byte[] 32
$randomNumberGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomNumberGenerator.GetBytes($randomBytes)
}
finally {
    $randomNumberGenerator.Dispose()
}
$sessionToken = [Convert]::ToBase64String($randomBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$env:MINIMAXH3_STUDIO_SESSION_TOKEN = $sessionToken
try {
    if (-not $Dev) {
        $studioUrl = "http://127.0.0.1:$Port"
        Write-Host "MiniMaxH3 Studio: $studioUrl"
        Write-Host 'Press Ctrl+C to stop the local server.'
        if (-not $NoBrowser) {
            $backendArguments += '--open'
        }
        $pythonArguments = @($python.PrefixArguments) + $backendArguments
        & $python.FilePath @pythonArguments
        exit $LASTEXITCODE
    }

    $backendArguments += @('--allowed-origin', "http://127.0.0.1:$FrontendPort")
    $backendProcess = Start-StudioBackend -Python $python -Arguments $backendArguments
    Wait-StudioEndpoint -Process $backendProcess -PortNumber $Port

    if (-not (Test-Path -LiteralPath $frontendPackage -PathType Leaf)) {
        throw "Studio frontend package was not found: $frontendPackage"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules') -PathType Container)) {
        throw 'Studio frontend dependencies are missing. Run .\setup-studio.ps1 first.'
    }
    if ($FrontendPort -eq $Port) {
        throw 'FrontendPort and Port must be different in development mode.'
    }
    Assert-PortAvailable -PortNumber $FrontendPort -Label 'Frontend'

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $viteCli = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
    if ($null -eq $nodeCommand -or -not (Test-Path -LiteralPath $viteCli -PathType Leaf)) {
        throw 'Node.js or the Vite CLI is missing. Run .\setup-studio.ps1 first.'
    }

    $env:VITE_STUDIO_API_BASE = "http://127.0.0.1:$Port"
    $env:MINIMAXH3_STUDIO_DEV_TOKEN = $sessionToken
    $studioUrl = "http://127.0.0.1:$FrontendPort"
    Write-Host "Studio backend: http://127.0.0.1:$Port"
    Write-Host "Studio frontend (development): $studioUrl"
    Write-Host 'Press Ctrl+C to stop both processes.'
    if (-not $NoBrowser) {
        Start-Process $studioUrl
    }

    Push-Location $frontendRoot
    try {
        & $nodeCommand.Source $viteCli --host 127.0.0.1 --port $FrontendPort --strictPort
        $frontendExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    exit $frontendExit
}
finally {
    $env:VITE_STUDIO_API_BASE = $previousApiBase
    $env:MINIMAXH3_STUDIO_SESSION_TOKEN = $previousSessionToken
    $env:MINIMAXH3_STUDIO_DEV_TOKEN = $previousDevToken
    if ($null -ne $backendProcess -and -not $backendProcess.HasExited) {
        Stop-StudioProcessTree -Process $backendProcess
        $backendProcess.WaitForExit(5000) | Out-Null
    }
}
