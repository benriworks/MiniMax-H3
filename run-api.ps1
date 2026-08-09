[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]] $ApiArgs
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$scriptPath = Join-Path $projectRoot 'tools\h3_api.py'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not $ApiArgs -or $ApiArgs.Count -eq 0) {
    $ApiArgs = @('doctor')
}

# The Python CLI loads .env itself. UTF-8 mode keeps Japanese prompts/output stable.
$env:PYTHONUTF8 = '1'

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    & $venvPython $scriptPath @ApiArgs
    exit $LASTEXITCODE
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
    & $pythonCommand.Source $scriptPath @ApiArgs
    exit $LASTEXITCODE
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $pyLauncher) {
    & $pyLauncher.Source -3 $scriptPath @ApiArgs
    exit $LASTEXITCODE
}

Write-Error 'Python 3 was not found. Install Python 3 or create .venv in this folder.'
exit 1
