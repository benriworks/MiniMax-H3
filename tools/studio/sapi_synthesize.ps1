[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$InputJsonPath,

    [Parameter(Mandatory = $false)]
    [string]$OutputWavPath,

    [switch]$Preflight
)

$ErrorActionPreference = "Stop"

try {
    Add-Type -AssemblyName System.Speech
}
catch {
    throw "System.Speech is unavailable."
}

$synthesizer = $null
try {
    $synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
    if ($Preflight) {
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($InputJsonPath) -or [string]::IsNullOrWhiteSpace($OutputWavPath)) {
        throw "InputJsonPath and OutputWavPath are required."
    }

    $inputPath = [System.IO.Path]::GetFullPath($InputJsonPath)
    $outputPath = [System.IO.Path]::GetFullPath($OutputWavPath)
    if (-not [System.IO.File]::Exists($inputPath)) {
        throw "The synthesis request file does not exist."
    }
    $parent = [System.IO.Path]::GetDirectoryName($outputPath)
    if ([string]::IsNullOrWhiteSpace($parent)) {
        throw "The synthesis output path is invalid."
    }
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null

    # The user text is read as UTF-8 JSON.  It is never interpolated into a
    # PowerShell command string.
    $request = Get-Content -LiteralPath $inputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $request.text -or $request.text -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$request.text)) {
        throw "The synthesis text is invalid."
    }
    $rate = [int]$request.rate
    if ($rate -lt -10 -or $rate -gt 10) {
        throw "The synthesis rate is outside the supported range."
    }
    if ($null -ne $request.voice -and -not [string]::IsNullOrWhiteSpace([string]$request.voice)) {
        $synthesizer.SelectVoice([string]$request.voice)
    }
    $synthesizer.Rate = $rate
    $synthesizer.SetOutputToWaveFile($outputPath)
    $synthesizer.Speak([string]$request.text)
    $synthesizer.SetOutputToNull()
    if (-not [System.IO.File]::Exists($outputPath)) {
        throw "SAPI did not create a WAV file."
    }
}
finally {
    if ($null -ne $synthesizer) {
        $synthesizer.Dispose()
    }
}
