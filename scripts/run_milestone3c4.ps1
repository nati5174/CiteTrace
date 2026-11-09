# Run once locally. No sandbox execution or network bypass.
$ErrorActionPreference = 'Stop'
$sourceRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $sourceRepository
$sourcePython = Join-Path $sourceRepository '.venv/Scripts/python.exe'
$sourceOutput = Join-Path $sourceRepository 'artifacts/milestone-3c4'
if (Test-Path -LiteralPath $sourceOutput) {
    throw 'Milestone 3C-4 already exists. Return existing files; do not rerun.'
}
& $sourcePython scripts/source_feasibility.py --execute-authorized-batch --output-dir $sourceOutput
if ($LASTEXITCODE -ne 0) { throw 'Return partial files and error; do not rerun.' }
Write-Output 'Return artifacts/milestone-3c4 in full. Source feasibility is not yet established.'
Write-Output 'Do not retry missing, redirected, failed or inconclusive evidence.'
