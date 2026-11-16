[CmdletBinding()]
param([string]$ManifestPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$manifest = Get-Content -Raw -Encoding utf8 -LiteralPath $ManifestPath | ConvertFrom-Json
$engine = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
  $versions=[PSCustomObject]@{powershell=$PSVersionTable.PSVersion.ToString(); assembly=[System.Speech.Synthesis.SpeechSynthesizer].Assembly.GetName().Version.ToString()}
  foreach ($line in $manifest) {
    $engine.SelectVoice($line.voice)
    if ($engine.Voice.Name -ne $line.voice) { throw 'Unexpected local voice' }
    $engine.Rate=$line.rate
    $engine.SetOutputToWaveFile($line.dest)
    $engine.Speak($line.reading)
    $engine.SetOutputToNull()
  }
  $versions | ConvertTo-Json -Compress
} finally { $engine.Dispose() }
