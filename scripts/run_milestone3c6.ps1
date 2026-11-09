# One authorized local request. Never execute inside the restricted sandbox.
$ErrorActionPreference = 'Stop'
$specRepository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $specRepository
$specPython = Join-Path $specRepository '.venv/Scripts/python.exe'
$specCli = Join-Path $specRepository '.venv/Scripts/citeprobe.exe'
$specPlan = Join-Path $specRepository 'docs/research/3c6-atom-budget.json'
$specRoot = Join-Path $specRepository 'artifacts/milestone-3c6'
$specBundle = Join-Path $specRoot 'run-001'
if (Test-Path -LiteralPath $specRoot) {
    throw 'Milestone 3C-6 already exists. Return its files; do not rerun.'
}

# Offline preflight proves the budget is one exact officially linked URL.
@'
import hashlib, json
from pathlib import Path
from citeprobe.evidence_models import EvidenceBudget
url = 'https://info.arxiv.org/help/atom_specifications.html'
budget = EvidenceBudget.model_validate_json(Path('docs/research/3c6-atom-budget.json').read_bytes())
assert budget.maximum_requests == 1 and len(budget.requests) == 1
assert budget.origin == 'observed' and budget.requests[0].url == url
assert budget.requests[0].source_kind == 'arxiv_rss_doc'
record = json.loads(Path('artifacts/milestone-3c4/02-source.json').read_bytes())
assert url in record['evidence']['official_links_not_fetched']
assert hashlib.sha256(json.dumps(record['evidence'],sort_keys=True,ensure_ascii=False).encode()).hexdigest() == record['evidence_sha256']
print('Offline preflight passed: one officially linked specification URL, no follow-ups.')
'@ | & $specPython -
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. No request was made.' }
New-Item -ItemType Directory -Path $specRoot -ErrorAction Stop | Out-Null
$specDigest = (Get-FileHash -LiteralPath $specPlan -Algorithm SHA256).Hash.ToLowerInvariant()

# ONLY network operation: version 2 raw capture, one request and no retry/redirect.
& $specPython scripts/source_feasibility_v2.py $specPlan --execute-authorized-batch --authorization-reference 'User-approved Milestone 3C-6: one official Atom specification request only' --plan-sha256 $specDigest --output-dir $specBundle
if ($LASTEXITCODE -ne 0) { throw 'Return partial files/error; do not rerun.' }

# Offline verification and replay only.
& $specCli evidence-verify $specBundle --replay-output (Join-Path $specRoot 'replay.json')
if ($LASTEXITCODE -ne 0) { throw 'Evidence verification failed. Return files; do not rerun.' }
& $specCli evidence-verify $specBundle --replay-output (Join-Path $specRoot 'replay-check.json')
if ($LASTEXITCODE -ne 0) { throw 'Second offline verification failed. Return files; do not rerun.' }
if ((Get-FileHash -LiteralPath (Join-Path $specRoot 'replay.json')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $specRoot 'replay-check.json')).Hash) {
    throw 'Offline replay differs. Return files; do not rerun.'
}
Write-Output 'Return artifacts/milestone-3c6 in full, including body.bin. No source conclusion is automatic.'
Write-Output 'Do not retry errors, redirects, incomplete captures or inconclusive evidence.'
