<#
Read-only WinRT voice availability diagnostic. Does not install/register voices,
change registry, invoke an external API, fall back to another voice, or play audio.
The live inventory lacked Sayaka, so this probe records that blocking condition
without a synthesis attempt. No native format or auditory result is inferred.
Run with Windows PowerShell 5.1, whose .NET Framework exposes WinRT projection.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$outputRoot = Join-Path $workspace 'outputs\studio\verification\claude-desktop-real-20260906\winrt-voice-probe'
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = Join-Path $outputRoot $runId
[IO.Directory]::CreateDirectory($runDirectory) | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)

function Write-NewText([string]$Path, [string]$Text) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = $utf8.GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
    }
    finally { $stream.Dispose() }
}

# ASCII source remains readable under Windows PowerShell 5.1 without a BOM.
$requestText = -join ([char[]]@(0x6761, 0x4ef6, 0x3092, 0x6dfb, 0x3048, 0x3066, 0x3001, 0x4e09, 0x6848, 0x307e, 0x3068, 0x3081, 0x3066, 0x4f9d, 0x983c, 0x3002))
$requestPath = Join-Path $runDirectory 'request.txt'
Write-NewText $requestPath $requestText
$report = [ordered]@{
    createdAtUtc = [DateTime]::UtcNow.ToString('o')
    purpose = 'same-voice WinRT native format feasibility; metadata-only after unavailable-voice finding'
    status = 'pending'
    host = [ordered]@{
        executable = (Get-Process -Id $PID).MainModule.FileName
        powershellVersion = $PSVersionTable.PSVersion.ToString()
        edition = $PSVersionTable.PSEdition
        clrVersion = [Environment]::Version.ToString()
        osVersion = [Environment]::OSVersion.VersionString
        process64Bit = [Environment]::Is64BitProcess
    }
    api = 'Windows.Media.SpeechSynthesis.SpeechSynthesizer'
    source = 'https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer?view=winrt-26100'
    requestedVoice = 'Microsoft Sayaka'
    requestedVoiceId = $null
    text = $requestText
    textSha256 = (Get-FileHash -LiteralPath $requestPath -Algorithm SHA256).Hash
    rate = 'default; no synthesis options were set'
    availableVoices = @()
    generationAttempts = 0
    fallback = $false
    format = $null
    audioSha256 = $null
    scriptSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    error = $null
    perceptualQuality = 'not evaluated'
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $voices = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime]::AllVoices)
    $report.availableVoices = @($voices | ForEach-Object {
        [ordered]@{ displayName = $_.DisplayName; language = $_.Language; id = $_.Id; gender = $_.Gender.ToString() }
    })
    $matches = @($voices | Where-Object { $_.DisplayName -ceq 'Microsoft Sayaka' })
    if ($matches.Count -eq 0) {
        $report.status = 'blocked_requested_voice_unavailable'
        $report.error = 'Microsoft Sayaka is absent from WinRT AllVoices. No synthesis or voice fallback was attempted; native format comparison is unavailable.'
    }
    else {
        $report.status = 'voice_available_requires_separate_generation_probe'
        $report.requestedVoiceId = @($matches | ForEach-Object { $_.Id })
        $report.error = 'Inventory differs from the initial diagnostic. This metadata-only probe does not synthesize speech.'
    }
}
catch {
    $report.status = 'blocked_winrt_enumeration_failed'
    $report.error = $_.Exception.ToString()
}

$reportPath = Join-Path $runDirectory 'probe-report.json'
Write-NewText $reportPath ($report | ConvertTo-Json -Depth 8)
[pscustomobject]@{ reportPath = $reportPath; status = $report.status; generationAttempts = 0 } | ConvertTo-Json
