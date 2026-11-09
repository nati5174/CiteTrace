# Authorized attempt 002: run once, locally, from the repository root.
$ErrorActionPreference = 'Stop'
$snapshot = 'artifacts/empirical-pilot-immediate-001/a-frozen-001'
$prior = 'artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-001'
$output = 'artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-002'
if (Test-Path -LiteralPath $output) { throw 'Attempt 002 already exists. Preserve it; do not retry.' }
if ($env:OPENALEX_API_KEY -or $env:CROSSREF_API_KEY -or $env:CROSSREF_MAILTO) { throw 'Unexpected provider credentials/contact configuration; stop without sending requests.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$prior/integrity.json").Hash.ToLowerInvariant() -ne 'c592ae4a6669947a398348513b49473170f9809d432cb93b831ef11b8ea8aeaa') { throw 'Attempt 001 integrity anchor mismatch.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --verify $prior
if ($LASTEXITCODE -ne 0) { throw 'Attempt 001 evidence verification failed.' }
$record = Get-Content -Raw -LiteralPath "$prior/attempt-001/record.json" | ConvertFrom-Json
if ($record.status -ne 429 -or $record.headers.'retry-after' -ne '35') { throw 'Unexpected prior rate-limit evidence.' }
$retryAt = ([DateTimeOffset]::Parse($record.finished_at)).AddSeconds(35)
if ([DateTimeOffset]::UtcNow -lt $retryAt) { throw 'Retry-After has not elapsed.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$snapshot/dataset.json").Hash.ToLowerInvariant() -ne 'a8ffee33582fd352fe72db5c410300ac29a92c5e0cbca94b76b1a14a5e5b156d') { throw 'Dataset hash mismatch.' }
.\.venv\Scripts\python.exe -m citeprobe.cli pilot-verify $snapshot --integrity-sha256 25472018fe08a2a5c61d564f6246f233fcc019b5554677487c2c20ad953ad5ac
if ($LASTEXITCODE -ne 0) { throw 'Frozen snapshot verification failed.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --snapshot $snapshot --output $output --authorize-live
if ($LASTEXITCODE -ne 0) { throw 'STOP: preserve attempt 002 and return it for review; do not retry.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --verify $output
if ($LASTEXITCODE -ne 0) { throw 'STOP: evidence verification failed; do not retry.' }
Write-Output 'Return the complete attempt 002 directory for offline review.'
Get-FileHash -Algorithm SHA256 -LiteralPath "$output/integrity.json"
