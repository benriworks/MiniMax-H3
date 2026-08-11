function Get-TorchInstallArguments {
    param(
        [Parameter(Mandatory = $true)][bool] $UseUv,
        [Parameter(Mandatory = $true)][string] $PythonPath,
        [Parameter(Mandatory = $true)][object] $RuntimeLock,
        [switch] $Update
    )

    $torchIndex = [string]$RuntimeLock.pytorch.index_url
    $torchPackages = $RuntimeLock.pytorch.packages
    if ($Update) {
        $packageArguments = @(
            'torch', 'torchvision', 'torchaudio', '--upgrade', '--index-url', $torchIndex
        )
    }
    else {
        $packageArguments = @(
            "torch==$([string]$torchPackages.torch)",
            "torchvision==$([string]$torchPackages.torchvision)",
            "torchaudio==$([string]$torchPackages.torchaudio)",
            '--no-deps', '--index-url', $torchIndex
        )
    }

    $prefixArguments = if ($UseUv) {
        @('pip', 'install', '--python', $PythonPath)
    }
    else {
        @('-m', 'pip', 'install')
    }
    return @($prefixArguments) + @($packageArguments)
}

function Normalize-GitRemote {
    param([Parameter(Mandatory = $true)][string] $Remote)

    $normalized = $Remote.Trim().TrimEnd('/').ToLowerInvariant()
    if ($normalized.EndsWith('.git')) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }
    return $normalized
}

function Set-GitRepositoryRevision {
    param(
        [Parameter(Mandatory = $true)][string] $Repository,
        [Parameter(Mandatory = $true)][string] $Revision,
        [Parameter(Mandatory = $true)][string] $Destination,
        [Parameter(Mandatory = $true)][string] $Label,
        [switch] $UseLatest
    )

    if (-not (Test-Path -LiteralPath $Destination)) {
        # A normal checkout is intentional: --no-checkout makes every tracked
        # file appear deleted, which is indistinguishable from a dirty tree.
        Invoke-External -FilePath 'git' -ArgumentList @(
            'clone', '--filter=blob:none', $Repository, $Destination
        ) -Description "Clone $Label"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Destination '.git') -PathType Container)) {
        throw "$Label path exists but is not a Git repository: $Destination"
    }

    $originLines = @(& git -C $Destination remote get-url origin 2>$null)
    $originExit = $LASTEXITCODE
    $origin = $originLines | Select-Object -First 1
    if ($originExit -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
        throw "$Label has no readable origin; left untouched: $Destination"
    }
    if ((Normalize-GitRemote -Remote $origin) -ne (Normalize-GitRemote -Remote $Repository)) {
        throw "$Label origin is '$origin', not '$Repository'; left untouched."
    }

    $dirty = @(& git -C $Destination status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect $Label working tree: $Destination"
    }
    $currentRevisionLines = @(& git -C $Destination rev-parse HEAD 2>$null)
    $revisionExit = $LASTEXITCODE
    $currentRevision = $currentRevisionLines | Select-Object -First 1
    if ($revisionExit -ne 0) {
        $currentRevision = ''
    }

    if ($dirty.Count -gt 0) {
        if ($UseLatest -or $currentRevision.Trim() -ne $Revision) {
            throw "$Label has local changes and is not safely updateable. No fetch, checkout, or reset was performed."
        }
        Write-Warning "$Label has local changes at the locked revision; repository mutation was skipped."
        return
    }

    if ($UseLatest) {
        Invoke-External -FilePath 'git' -ArgumentList @(
            '-C', $Destination, 'fetch', '--depth', '1', 'origin', 'HEAD'
        ) -Description "Fetch latest $Label only because -Update was specified"
        Invoke-External -FilePath 'git' -ArgumentList @(
            '-C', $Destination, 'checkout', '--detach', 'FETCH_HEAD'
        ) -Description "Check out latest fetched $Label revision"
        $updatedRevisionLines = @(& git -C $Destination rev-parse HEAD)
        $updatedRevision = $updatedRevisionLines | Select-Object -First 1
        Write-Warning "$Label now uses unpinned revision $updatedRevision; review and update runtime-lock.json before relying on reproducibility."
        return
    }

    if ($currentRevision.Trim() -eq $Revision) {
        Write-Host "LOCK $Label $Revision"
        return
    }

    # Windows PowerShell 5 can promote a native command's expected stderr to a
    # terminating ErrorRecord when the caller uses ErrorActionPreference=Stop.
    # A missing local object is a normal probe miss, so decide from the exit code.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & git -C $Destination cat-file -e "$Revision^{commit}" 2>$null
        $objectExistsExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($objectExistsExitCode -ne 0) {
        Invoke-External -FilePath 'git' -ArgumentList @(
            '-C', $Destination, 'fetch', '--depth', '1', 'origin', $Revision
        ) -Description "Fetch locked $Label revision $Revision"
    }
    Invoke-External -FilePath 'git' -ArgumentList @(
        '-C', $Destination, 'checkout', '--detach', $Revision
    ) -Description "Check out locked $Label revision $Revision"
}
