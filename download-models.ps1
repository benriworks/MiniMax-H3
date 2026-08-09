[CmdletBinding()]
param(
    [ValidateSet('lowvram', 'official')]
    [string] $Profile = 'lowvram',

    [switch] $AcceptLicense
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$comfyRoot = Join-Path $projectRoot 'runtime\ComfyUI'
$modelsRoot = Join-Path $comfyRoot 'models'
$hfPath = Join-Path $projectRoot '.venv\Scripts\hf.exe'
$manifestPath = Join-Path $projectRoot 'model-manifest.json'
$twoGiB = [long](2 * 1024 * 1024 * 1024)

function Format-Bytes {
    param([long] $Bytes)
    return ('{0:N2} GiB' -f ($Bytes / 1GB))
}

if (-not $AcceptLicense) {
    Write-Error @'
-AcceptLicense is required. Review the licenses/model cards first:
  .\THIRD_PARTY_NOTICES.md
  https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/bfc8ed0353f5a9733be73e6b2c98ec0948195b86/LICENSE
  https://huggingface.co/Comfy-Org/MiniMax-H3
  https://huggingface.co/Abiray/MiniMax-H3-Pruned-GGUF
  https://huggingface.co/realrebelai/MiniMax-H3_GGUFs
Then rerun with -AcceptLicense to confirm acceptance.
'@
    exit 2
}

if (-not (Test-Path -LiteralPath $hfPath -PathType Leaf)) {
    throw "Hugging Face CLI was not found: $hfPath. Run .\setup-local.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $comfyRoot 'main.py') -PathType Leaf)) {
    throw "ComfyUI was not found: $comfyRoot. Run .\setup-local.ps1 first."
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Tracked model manifest was not found: $manifestPath"
}

$diffusionRoot = Join-Path $modelsRoot 'diffusion_models'
$unetRoot = Join-Path $modelsRoot 'unet'
$textEncoderRoot = Join-Path $modelsRoot 'text_encoders'
$vaeRoot = Join-Path $modelsRoot 'vae'
New-Item -ItemType Directory -Force -Path $diffusionRoot, $unetRoot, $textEncoderRoot, $vaeRoot | Out-Null

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne 1) {
    throw "Unsupported model manifest schema version: $($manifest.schema_version)"
}
$profileProperty = $manifest.profiles.PSObject.Properties | Where-Object Name -EQ $Profile | Select-Object -First 1
if ($null -eq $profileProperty) {
    throw "Profile '$Profile' is missing from $manifestPath"
}
$entries = @()
foreach ($modelId in @($profileProperty.Value)) {
    $modelProperty = $manifest.models.PSObject.Properties | Where-Object Name -EQ $modelId | Select-Object -First 1
    if ($null -eq $modelProperty) {
        throw "Model '$modelId' referenced by profile '$Profile' is missing from the manifest."
    }
    $model = $modelProperty.Value
    $localDirectory = if ($model.local_dir -eq '.') {
        $modelsRoot
    }
    else {
        Join-Path $modelsRoot ($model.local_dir -replace '/', '\')
    }
    $entries += [PSCustomObject]@{
        Repository = [string]$model.repository
        Revision = [string]$model.revision
        RemotePath = [string]$model.remote_path
        LocalDirectory = $localDirectory
        Destination = Join-Path $modelsRoot ($model.local_path -replace '/', '\')
        ExpectedBytes = [long]$model.bytes
        Sha256 = [string]$model.sha256
        SourceUrl = [string]$model.source_url
    }
}

$totalBytes = [long](($entries | Measure-Object -Property ExpectedBytes -Sum).Sum)
$missingBytes = [long]0
foreach ($entry in $entries) {
    if (Test-Path -LiteralPath $entry.Destination -PathType Leaf) {
        $actual = (Get-Item -LiteralPath $entry.Destination).Length
        if ($actual -eq $entry.ExpectedBytes) {
            continue
        }
    }
    $missingBytes += $entry.ExpectedBytes
}

$modelDrive = (Get-Item -LiteralPath $modelsRoot).PSDrive
$freeBytes = [long]$modelDrive.Free
Write-Host "Profile: $Profile"
Write-Host "Total model size: $(Format-Bytes $totalBytes)"
Write-Host "Download/repair required: $(Format-Bytes $missingBytes)"
Write-Host "Free disk space on $($modelDrive.Name): $(Format-Bytes $freeBytes)"

if ($missingBytes -gt 0 -and $freeBytes -lt ($missingBytes + $twoGiB)) {
    throw "Insufficient free space. Required download plus 2 GiB headroom: $(Format-Bytes ($missingBytes + $twoGiB))."
}

foreach ($entry in $entries) {
    $forceDownload = $false
    if (Test-Path -LiteralPath $entry.Destination -PathType Leaf) {
        $actualBytes = (Get-Item -LiteralPath $entry.Destination).Length
        if ($actualBytes -eq $entry.ExpectedBytes) {
            Write-Host "SKIP $([IO.Path]::GetFileName($entry.Destination)) ($(Format-Bytes $actualBytes))"
            continue
        }
        Write-Warning "Size mismatch for $($entry.Destination): expected $($entry.ExpectedBytes), found $actualBytes. Re-downloading."
        $forceDownload = $true
    }

    Write-Host "DOWNLOAD $($entry.Repository)/$($entry.RemotePath)"
    $downloadArguments = @(
        'download', $entry.Repository, $entry.RemotePath,
        '--revision', $entry.Revision,
        '--local-dir', $entry.LocalDirectory
    )
    if ($forceDownload) {
        $downloadArguments += '--force-download'
    }
    & $hfPath @downloadArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed for $($entry.Repository)/$($entry.RemotePath)"
    }
    if (-not (Test-Path -LiteralPath $entry.Destination -PathType Leaf)) {
        throw "Downloaded file was not found at the expected destination: $($entry.Destination)"
    }
    $downloadedBytes = (Get-Item -LiteralPath $entry.Destination).Length
    if ($downloadedBytes -ne $entry.ExpectedBytes) {
        throw "Downloaded size mismatch for $($entry.Destination): expected $($entry.ExpectedBytes), found $downloadedBytes"
    }
    Write-Host "OK   $([IO.Path]::GetFileName($entry.Destination)) ($(Format-Bytes $downloadedBytes))"
}

Write-Host ''
Write-Host "All $Profile model files passed exact-size verification."
Write-Host "Optional full integrity check: .\.venv\Scripts\python.exe tools\local_doctor.py --profile $Profile --hash"
Write-Host 'Run .\run-local.ps1 to start ComfyUI.'
