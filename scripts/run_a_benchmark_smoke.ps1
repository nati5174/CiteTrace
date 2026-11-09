# Run once from the repository root, in a network-enabled local terminal.
$ErrorActionPreference = 'Stop'
$snapshot = 'artifacts/empirical-pilot-immediate-001/a-frozen-001'
$output = 'artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-001'
if (Test-Path -LiteralPath $output) { throw 'Output exists. Preserve it; do not repeat acquisition.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$snapshot/dataset.json").Hash.ToLowerInvariant() -ne 'a8ffee33582fd352fe72db5c410300ac29a92c5e0cbca94b76b1a14a5e5b156d') { throw 'Dataset hash mismatch' }
.\.venv\Scripts\python.exe -m citeprobe.cli pilot-verify $snapshot --integrity-sha256 25472018fe08a2a5c61d564f6246f233fcc019b5554677487c2c20ad953ad5ac
if ($LASTEXITCODE -ne 0) { throw 'Frozen evidence preflight failed' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --snapshot $snapshot --output $output --authorize-live
if ($LASTEXITCODE -ne 0) { throw 'STOP: preserve captured evidence and return it for review. Do not retry.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --verify $output
if ($LASTEXITCODE -ne 0) { throw 'STOP: offline evidence verification failed. Do not retry.' }
Write-Output 'Return the complete output directory, including raw bodies, for offline evaluation.'
Get-FileHash -Algorithm SHA256 -LiteralPath "$output/integrity.json"
