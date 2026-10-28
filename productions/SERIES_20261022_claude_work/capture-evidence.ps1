param(
  [Parameter(Mandatory=$true)][int]$WindowHandle,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]+$')][string]$Name,
  [string]$Product = 'Claude',
  [string]$Viewer = 'Claude Desktop'
)
$ErrorActionPreference = 'Stop'
$captureRoot = Join-Path $PSScriptRoot '..\..\outputs\evidence\claude-work-20261022\_private'
$captureRoot = [IO.Path]::GetFullPath($captureRoot)
$capturePath = Join-Path $captureRoot ($Name + '.png')
$metadataPath = Join-Path $captureRoot ($Name + '.json')
if ((Test-Path -LiteralPath $capturePath) -or (Test-Path -LiteralPath $metadataPath)) { throw 'Evidence name already exists; choose a new version.' }
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class EvidenceCaptureDpi { [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value); }'
[EvidenceCaptureDpi]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null
& 'C:\Users\mono_\.codex\skills\screenshot\scripts\take_screenshot.ps1' -WindowHandle $WindowHandle -Path $capturePath
$capturedImage = [Drawing.Image]::FromFile($capturePath)
try {
  $metadata = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    source = 'Screenshot skill; DPI-aware native PNG; no pixel resampling or content editing'
    product = $Product
    viewer = $Viewer
    fictional_materials_only = $true
    width = $capturedImage.Width
    height = $capturedImage.Height
    format = 'PNG'
    sha256 = (Get-FileHash -LiteralPath $capturePath -Algorithm SHA256).Hash
    public = $false
  }
  $metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metadataPath -Encoding utf8
} finally { $capturedImage.Dispose() }
