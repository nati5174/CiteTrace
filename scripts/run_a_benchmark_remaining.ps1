# Prepared for review. Do not run without separate authorization of this inventory.
$ErrorActionPreference = 'Stop'
$snapshot = 'artifacts/empirical-pilot-immediate-001/a-frozen-001'
$prior = 'artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-002'
$plan = 'artifacts/empirical-pilot-immediate-001/a-benchmark-remaining-preflight-001/request-manifest.json'
$output = 'artifacts/empirical-pilot-immediate-001/a-benchmark-remaining-001'
$planHash = '08d50409ad07521e1d78dfe45321596e65e2ec649ef78b5e41edd1b8f5264a2b'
if (Test-Path -LiteralPath $output) { throw 'Output already exists. Preserve evidence and do not repeat.' }
if ($env:OPENALEX_API_KEY -or $env:CROSSREF_API_KEY -or $env:CROSSREF_MAILTO) { throw 'Unexpected provider credentials or contact configuration.' }
$expected = @{
    'src/citeprobe/benchmark_remaining.py' = 'a70a43d20dac1bc262067593fd8032b01e7fc98760cf488312acd58da7df2734'
    'src/citeprobe/benchmark_smoke.py' = '39dac74f49d3139e6284837e48c476f56bd2c3215dd456cc703d7b8d436d5c10'
    'src/citeprobe/resolver.py' = 'cc39d6219dc347a6cf880dc38fc509557192397f26c7e89c117bf30d041e0945'
    'src/citeprobe/providers.py' = '988ecfc9e4221253acf3786adf89d830aba0fa5178495a082bd29e7ff2ca5651'
}
foreach ($entry in $expected.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Runner file changed: $($entry.Key)" }
}
if ((Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $planHash) { throw 'Plan hash mismatch.' }
.\.venv\Scripts\python.exe -m citeprobe.cli pilot-verify $snapshot --integrity-sha256 25472018fe08a2a5c61d564f6246f233fcc019b5554677487c2c20ad953ad5ac
if ($LASTEXITCODE -ne 0) { throw 'Frozen snapshot verification failed.' }
if ((Get-FileHash -LiteralPath "$prior/integrity.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne '56427baa74dd454399db9d4b6644d40a62746330e7c56868d1879a6fe92adc35') { throw 'Smoke evidence anchor mismatch.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --verify $prior
if ($LASTEXITCODE -ne 0) { throw 'Smoke evidence verification failed.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_remaining --snapshot $snapshot --prior $prior --plan $plan --plan-sha256 $planHash --output $output --authorize-live
if ($LASTEXITCODE -ne 0) { throw 'STOP: preserve all evidence. Do not rerun; request review.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_remaining --verify $output
if ($LASTEXITCODE -ne 0) { throw 'STOP: evidence verification failed; do not rerun.' }
Get-FileHash -LiteralPath "$output/integrity.json" -Algorithm SHA256
Write-Output 'Preserve this external integrity anchor and return the full output directory for review.'
