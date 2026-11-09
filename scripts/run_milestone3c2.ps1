# Run once in the normal local Windows terminal, outside the restricted sandbox.
$ErrorActionPreference = 'Stop'
$acqRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $acqRepository
$acqCli = Join-Path $acqRepository '.venv/Scripts/citeprobe.exe'
$acqRoot = Join-Path $acqRepository 'artifacts/milestone-3c2'
if (-not (Test-Path -LiteralPath $acqCli)) { throw 'Installed .venv CiteProbe CLI is required.' }
if (Test-Path -LiteralPath $acqRoot) {
    throw 'Milestone 3C-2 directory already exists. Do not rerun; return its files for review.'
}
New-Item -ItemType Directory -Path $acqRoot -ErrorAction Stop | Out-Null
$acqPlan = Join-Path $acqRoot 'plan-001.json'
$acqRun = Join-Path $acqRoot 'run-001'
$acqStart = [DateTimeOffset]::UtcNow
$acqEnd = $acqStart.AddHours(2)
$acqReference = $acqStart.UtcDateTime.ToString('yyyy-MM-dd')
$acqCanonical = Join-Path $acqRepository 'data/pilot_dataset.json'
$acqHashBefore = (Get-FileHash -LiteralPath $acqCanonical -Algorithm SHA256).Hash

# Offline preparation only. Fixes the source, offset, order, date range and five-record cap.
& $acqCli acquisition-plan --source arxiv_atom --experiment recent-preprints --reference-date $acqReference --planned-start $acqStart.ToString('o') --planned-end $acqEnd.ToString('o') --max-records 5 --output $acqPlan
if ($LASTEXITCODE -ne 0) { throw 'Offline plan failed. No requests were made; do not rerun.' }
$acqDigest = (Get-FileHash -LiteralPath $acqPlan -Algorithm SHA256).Hash.ToLowerInvariant()

# ONLY live operation: existing CLI, one request, no retries/redirects/pagination.
& $acqCli acquisition-run $acqPlan --authorize-live --authorization-reference 'User-authorized Milestone 3C-2: one arXiv request, maximum five records' --plan-sha256 $acqDigest --output-dir $acqRun
if ($LASTEXITCODE -ne 0) { throw 'Acquisition failed. Return partial files and error; do not rerun.' }
$acqHashAfter = (Get-FileHash -LiteralPath $acqCanonical -Algorithm SHA256).Hash
if ($acqHashBefore -ne $acqHashAfter) { throw 'Canonical dataset hash changed. Stop; do not rerun.' }

# Offline replay only; this command has no network operation.
& $acqCli acquisition-replay (Join-Path $acqRun 'response.json') --output (Join-Path $acqRun 'replay-check.json')
if ($LASTEXITCODE -ne 0) { throw 'Offline replay failed. Return files and error; do not rerun.' }
$acqOriginalAudit = (Get-FileHash -LiteralPath (Join-Path $acqRun 'audit.json') -Algorithm SHA256).Hash
$acqReplayAudit = (Get-FileHash -LiteralPath (Join-Path $acqRun 'replay-check.json') -Algorithm SHA256).Hash
if ($acqOriginalAudit -ne $acqReplayAudit) { throw 'Replay differs. Return files; do not rerun.' }
Write-Output 'Offline replay is byte-identical; canonical dataset hash is unchanged.'
Write-Output 'Return artifacts/milestone-3c2 in full. HTTP outcome and candidate identities require review.'
Write-Output 'Do not rerun for an HTTP error, empty result, partial result or parsing error.'
