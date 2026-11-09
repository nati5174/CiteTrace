# Offline-prepared only. Run once only after separate authorization of this exact plan.
$ErrorActionPreference = 'Stop'
$root = 'artifacts/empirical-pilot-immediate-001'
$snapshot = "$root/a-frozen-001"
$prior = "$root/a-benchmark-smoke-002"
$stopped = "$root/a-benchmark-remaining-001"
$plan = "$root/a-benchmark-key-preflight-001/request-manifest.json"
$output = "$root/a-benchmark-key-continuation-001"
$planHash = '6d7596d74b16f8d9901f66cc632e7c39344c270ccff029a227374125de745043'
if (Test-Path -LiteralPath $output) { throw 'Output already exists. Preserve it; do not repeat.' }
if (-not $env:OPENALEX_API_KEY) { throw 'OPENALEX_API_KEY is required; do not paste it into chat.' }
if ($env:CROSSREF_API_KEY -or $env:CROSSREF_MAILTO) { throw 'Crossref credentials/contact are not authorized.' }
$expected = @{
    'src/citeprobe/benchmark_key_continuation.py' = '0fffe2265a57984e91b811cbfd29c42d5cd037a5afe4e43363f7ec6075c0b1d9'
    'src/citeprobe/benchmark_remaining.py' = 'a70a43d20dac1bc262067593fd8032b01e7fc98760cf488312acd58da7df2734'
    'src/citeprobe/benchmark_smoke.py' = '39dac74f49d3139e6284837e48c476f56bd2c3215dd456cc703d7b8d436d5c10'
    'src/citeprobe/resolver.py' = 'cc39d6219dc347a6cf880dc38fc509557192397f26c7e89c117bf30d041e0945'
    'src/citeprobe/providers.py' = '988ecfc9e4221253acf3786adf89d830aba0fa5178495a082bd29e7ff2ca5651'
}
foreach ($entry in $expected.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Runner changed: $($entry.Key)" }
}
if ((Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $planHash) { throw 'Plan hash mismatch.' }
if ((Get-FileHash -LiteralPath "$stopped/integrity.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c4c1e49cc7f50d2ffd402efec3d4e5e605f5eafb4b04611c4fa76458b90ea3c3') { throw 'Stopped evidence anchor mismatch.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_remaining --verify $stopped
if ($LASTEXITCODE -ne 0) { throw 'Stopped evidence verification failed.' }
$record = Get-Content -Raw -LiteralPath "$stopped/paper-01/attempt-001/record.json" | ConvertFrom-Json
if ($record.status -ne 429 -or $record.headers.'retry-after' -ne '12') { throw 'Unexpected stopped response.' }
if ([DateTimeOffset]::UtcNow -lt ([DateTimeOffset]::Parse($record.finished_at)).AddSeconds(12)) { throw 'Retry-After has not elapsed.' }
.\.venv\Scripts\python.exe -m citeprobe.cli pilot-verify $snapshot --integrity-sha256 25472018fe08a2a5c61d564f6246f233fcc019b5554677487c2c20ad953ad5ac
if ($LASTEXITCODE -ne 0) { throw 'Frozen snapshot verification failed.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_key_continuation --snapshot $snapshot --prior $prior --stopped $stopped --plan $plan --plan-sha256 $planHash --output $output --authorize-live
if ($LASTEXITCODE -ne 0) { throw 'STOP: preserve evidence; do not retry or resume.' }
.\.venv\Scripts\python.exe -m citeprobe.benchmark_key_continuation --verify $output
if ($LASTEXITCODE -ne 0) { throw 'STOP: offline evidence verification failed; do not retry.' }
Write-Output 'Preserve this manifest hash externally. Inspect raw evidence for sensitive data before sharing.'
Get-FileHash -LiteralPath "$output/integrity.json" -Algorithm SHA256
