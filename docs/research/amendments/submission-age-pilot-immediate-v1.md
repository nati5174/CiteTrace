# A-S1 immediate-start date amendment, version 1

Status: date revision and offline preparation approved by the user instruction
"Immediate Empirical Pilot Acquisition". **No live requests authorized.**
This version supersedes only the execution dates of the eight-paper A-S1 pilot.
The November 23 proposal/plans, historical artifacts and original announcement-age
Experiment A protocol remain unchanged. No approval timestamp is fabricated.

## Reference, source days and window

The actual UTC date at preparation is **2026-11-09**. R is that date, fixed for
this pilot. Preparation occurred at 2026-11-09 01:40:22 UTC. No provider outcome
or paper identity influenced these dates. Retain the original fixed offsets
4, 11, 22 and 45 days, rather than choosing days based on observed record counts.

| Cohort | Inclusive UTC submission-date interval | Prespecified source day | Age | Target |
|---|---|---|---:|---:|
| 1–7 | November 2–8, 2026 | 2026-11-05 | 4 | 2 |
| 8–14 | October 26–November 1, 2026 | 2026-10-29 | 11 | 2 |
| 15–30 | October 10–25, 2026 | 2026-10-18 | 22 | 2 |
| 31–60 | September 10–October 9, 2026 | 2026-09-25 | 45 | 2 |

Every source day was complete before preparation. The active planned window for
both bounded stages is **2026-11-09 01:40:22 UTC through
2026-11-10 01:40:22 UTC** (24 hours). This is a planned window, not an actual
observation timestamp. Collection crossing midnight does not redefine R; retain
actual HTTP times and disclose their separation from the fixed reference date.
If the window expires, stop and version a replacement; do not edit these plans.

This remains a restricted **first arXiv submission-age** workflow pilot, not
announcement age, indexing latency, database-wide presence, a representative
60-day sample, or a statistically powered study. Later reporting must describe
verified retrieval coverage under the recorded search strategy.

## Unchanged methodology and safeguards

Keep snapshot-primary cs.CL eligibility and log cross-list/missing-category
exclusions. Completely enumerate each source day before sampling. For each day:

```text
GET https://export.arxiv.org/api/query
search_query=cat:cs.CL AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]
sortBy=submittedDate
sortOrder=ascending
max_results=100
start=0; start=100 only when saved totalResults requires it
```

Maximum eight attempts: four initial pages and four conditional second pages.
No further pagination. Stop for totals over 200, changing totals, missing records,
incorrect offsets, duplicate IDs, source-day contradictions, HTTP/transport/parser
errors, incomplete evidence, response limits or an expired window. Reconcile
terminal pages and unique IDs; a partial result cannot become a complete frame.
No count or outcome may trigger unapproved date changes or frame expansion.

Retain seed 0 and the exact original SHA-256 panel and selection prefixes.
Rank all primary-category records and take up to six per day as the fixed
24-item review panel. Record every decision, then select two fully eligible
papers per cohort using the original final ranking. Report shortages; do not
silently replace difficult papers or enlarge the panel.

The API submittedDate selector and API published field remain discovery evidence,
not curator-verified v1 dates. Curators must check authoritative abstract-record
v1 submission histories, retain raw evidence and actual verification times, and
approve the dates. A contradiction stops selection; unavailable evidence remains
unverified. Preserve language, bibliographic fact, identifier and duplicate
reviews. New identity bridges require two independent approvals, except direct
authoritative source declarations under the existing policy. No provider search
may influence acquisition or identity review. No benchmark requests or freezing
are authorized here.

## Immutable inventories and new fingerprints

Directory: `artifacts/milestone-3c7-immediate-001/`.
`request-inventory.json` contains every exact URL and conditional slot.

| File | Maximum | File SHA-256 |
|---|---:|---|
| a-enumeration-plan.json | 8 | `25dcd4648d834cf4f7069d8f4fcc260c37319cb94f69602b3c169fc6f40810c8` |
| acl-resolution-plan.json | 1 | `d89676a6c00b9274f00441d27b1c687707607da1f4d4db5a4358e5346470784b` |

Canonical content `plan_id` fingerprints, distinct from file hashes:

- A: `dd4d9c6d6be6278918f1db1d174d6ab93a9c3b0d35c50ed1b8c2db3bfba5f67c`.
- ACL: `781eebdd9c1c6999b6e6487211be7679b14fc13bf2962ad53f850711454985c9`.

B resolves exactly one commit from:
`https://api.github.com/repos/acl-org/acl-anthology/commits?per_page=1`.
Require a complete HTTP 200 JSON response from the official repository containing
one valid immutable 40-hex commit SHA. A successful request alone is not a proven
pin: replay evidence and run the existing offline pin validator. No revision has
been observed or invented. No clone, collection download, pagination, linked URL
or additional commit verification request is included.

Both stages use the existing runner: HTTPX, identifying User-Agent, bounded
timeouts, zero retries, no redirects, serial requests, exact hashed inventory,
new output directory, v2 raw response bytes and independent hashes, safe headers,
request identities and actual UTC times. Preserve extraction replay and external
manifest anchors. Never substitute this planned window for observed timestamps.

## Exact local execution commands

Run these **offline preflights now** from the repository root:

```powershell
.\scripts\run_immediate_pilot_v1.ps1 -Stage A
.\scripts\run_immediate_pilot_v1.ps1 -Stage ACL
```

The script performs no HTTP unless its explicit execution switch and new
stage-specific authorization reference are both supplied. It independently checks
the hardcoded plan-file hash, schema/canonical inventory, request count, completed
source days, UTC window and absence of an existing attempt directory.

This environment's PowerShell execution policy blocks `.ps1` execution. The wrapper
was syntax-validated, not executed here. No policy change or bypass was attempted.
The Python inventory validation and protected hashes were checked independently.
Use the inline alternative below if your local policy also blocks scripts.

**Only after new explicit live approval for these exact plans**, execute each
approved stage once. These commands are provided for later use, not executed or
authorized by preparation:

```powershell
.\scripts\run_immediate_pilot_v1.ps1 -Stage A -ExecuteApprovedStage -LiveAuthorizationReference 'A-S1-immediate-v1-A-enumeration'
# Stop and return evidence on any error; never repeat an attempted stage.
.\scripts\run_immediate_pilot_v1.ps1 -Stage ACL -ExecuteApprovedStage -LiveAuthorizationReference 'A-S1-immediate-v1-ACL-resolution'
```

Equivalent **inline** PowerShell commands, also **only after explicit new live
approval** for both stages. Native executable invocation does not require loading
a `.ps1` file. Run once from the repository root; stop on any error:

```powershell
$ErrorActionPreference = 'Stop'
$cp = '.\.venv\Scripts\citeprobe.exe'
$plans = 'artifacts/milestone-3c7-immediate-001'
$outputs = 'artifacts/empirical-pilot-immediate-001'
$aHash = '25dcd4648d834cf4f7069d8f4fcc260c37319cb94f69602b3c169fc6f40810c8'
$aclHash = 'd89676a6c00b9274f00441d27b1c687707607da1f4d4db5a4358e5346470784b'
$now = [DateTimeOffset]::UtcNow
if ($now -lt [DateTimeOffset]::Parse('2026-11-09T01:40:22Z') -or
    $now -ge [DateTimeOffset]::Parse('2026-11-10T01:40:22Z')) {
    throw 'STOP: outside the immutable collection window.'
}
if ((Get-FileHash "$plans/a-enumeration-plan.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aHash -or
    (Get-FileHash "$plans/acl-resolution-plan.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aclHash) {
    throw 'STOP: plan hash mismatch.'
}
if ((Test-Path "$outputs/a-enumeration-001") -or (Test-Path "$outputs/acl-pin-resolution-001")) {
    throw 'STOP: a stage was already attempted; do not rerun.'
}
New-Item -ItemType Directory -Path $outputs -Force | Out-Null
& $cp pilot-run "$plans/a-enumeration-plan.json" --authorize-live --authorization-reference 'A-S1-immediate-v1-A-enumeration' --plan-sha256 $aHash --output-dir "$outputs/a-enumeration-001"
if ($LASTEXITCODE -ne 0) { throw 'STOP: A failed/incomplete. Preserve evidence; do not repeat.' }
& $cp pilot-run "$plans/acl-resolution-plan.json" --authorize-live --authorization-reference 'A-S1-immediate-v1-ACL-resolution' --plan-sha256 $aclHash --output-dir "$outputs/acl-pin-resolution-001"
if ($LASTEXITCODE -ne 0) { throw 'STOP: ACL failed/incomplete. Preserve evidence; do not repeat.' }
```

The CLI independently validates the exact plan and active window before creating
an HTTP client; it does not start future or expired inventories. The inline
commands and wrapper are alternative ways to execute the same inventory: never
run both for the same stage. Additional attempts need separate authorization.

Expected new outputs:

- `artifacts/empirical-pilot-immediate-001/a-enumeration-001/`
- `artifacts/empirical-pilot-immediate-001/acl-pin-resolution-001/`

Each contains plan/run receipts and per-attempt raw v2 evidence bundles; skipped
conditional A pages are recorded without issuing requests. Do not rerun a failed
stage, bypass restrictions, change hashes/windows or repurpose unused budgets.

After successful authorized runs, these commands are **offline**:

```powershell
$cp = '.\.venv\Scripts\citeprobe.exe'
& $cp pilot-frame artifacts/empirical-pilot-immediate-001/a-enumeration-001 --output artifacts/empirical-pilot-immediate-001/a-frame.json
& $cp pilot-replay artifacts/empirical-pilot-immediate-001/a-enumeration-001 --output artifacts/empirical-pilot-immediate-001/a-replay.json
& $cp pilot-replay artifacts/empirical-pilot-immediate-001/acl-pin-resolution-001 --output artifacts/empirical-pilot-immediate-001/acl-replay.json
& $cp pilot-acl-pin --evidence artifacts/empirical-pilot-immediate-001/acl-pin-resolution-001/attempt-001 --curator-id 'nati5174' --output artifacts/empirical-pilot-immediate-001/acl-revision.json
```

Return both complete run directories for evidence review. A follow-up exact-ID/v1
plans and B collection inventories must be reviewed and separately authorized;
neither previous total ceiling is approved. Curators must resolve dates, aliases,
duplicates and eligibility before any final dataset is selected/frozen. B may
have an arxiv_only shortfall after uniform DOI-alias inspection; do not conceal it.

## Decision

Offline checks actually executed for this preparation:

- `python -m pytest -q -W error --basetemp .pytest-tmp/immediate-pilot-v1`:
  **457 passed in 82.05 seconds**, including three new plan/archive regression tests.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed, 110 files already formatted.
- `python -m mypy src tests scripts/source_feasibility_v2.py`: passed, 65 files.
- Both plan schemas, exact inventories, file hashes and canonical plan IDs: passed.
- All source days complete and both collection windows active at validation:
  2026-11-09 01:44:30 UTC.
- Protected hash sets 32/32, 5/5, 5/5 and 7/7 matched; 15 captured original
  plan/protocol files also matched. The C6 external anchor and raw extraction
  replay passed. See `integrity-check.json` in the new preparation directory.
- PowerShell wrapper syntax passed. Execution-policy blocking prevented wrapper
  execution here; inline commands are provided without changing that policy.

No production implementation problem was found or production code changed.
New files are this amendment, the versioned preparation bundle, the optional
guarded PowerShell wrapper and `tests/test_immediate_pilot_plans.py`.

**GO: revised dates, offline plan preparation and validation.**
**NO-GO: live HTTP until explicit approval of these new inventories/hashes.**
Actual source acceptance, record counts and metadata have not been observed.
The next executable action is approval of A's at-most-eight enumeration requests
and ACL's separate single revision-resolution request within the active window.
