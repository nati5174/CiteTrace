# Milestone 3C-7: empirical pilot acquisition implementation

Implementation and validation are offline. No papers acquired and no provider
lookups performed in this milestone. A-S1 adoption is recorded separately in
`amendments/submission-age-pilot-v1-adoption.json`; the historical proposal and
original announcement-age protocol remain unchanged.

## Implemented workflow

`pilot_models.py`, `pilot_plans.py`, `pilot_pin.py`, `pilot_run.py`,
`pilot_review.py` and `pilot_cli.py` add small pilot-specific contracts and CLI
commands. Existing dataset, evaluator and announcement-date schemas are unchanged.
The evidence extractor adds official abstract v1-history and upstream commit JSON
support; existing evidence source types replay unchanged. No dependencies added.

A uses `experiment=submission-age-pilot` and
`date_basis=first_arxiv_submission`. Submission, announcement, revision, planned
collection, actual HTTP collection and curator verification times stay distinct.
Do not pass this pilot off as an announcement-age or indexing-latency study.
Its eventual estimand is verified retrieval coverage under the recorded search
strategy in this restricted submission-age frame.

For a fixed UTC reference date R, A completely enumerates source days R-4,
R-11, R-22 and R-45. The example inventory uses R=2026-11-23 and source days
2026-11-19, 2026-11-12, 2026-11-01 and 2026-10-09. The example collection window
is a proposal for 2026-11-23 00:00 through 2026-11-24 00:00 UTC; it is not an
observation or live authorization. Approve a replacement plan if that window
cannot be met. UTC source days must be closed before collection.

Each arXiv day has a first page and an explicitly conditional second page.
Enumeration reconciles totalResults, startIndex, itemsPerPage, terminal counts,
unique base IDs and submission-day membership. Changing totals, overlap,
missing pages, more than 200 records, parser failures or transport failures stop
the run. No truncated first page becomes a sampling frame. This checks technical
enumeration consistency, not a proof of arXiv's indexing completeness.

Primary cs.CL eligibility is snapshot-based. Cross-lists and missing primary
categories receive recorded exclusions. The deterministic six-per-day A panel and
two-per-cohort final sample use the exact A-S1 SHA-256 prefixes, seed 0 and ID
tie-breaks. B uses the existing protocol's two-per-ACL-year/one-per-arXiv-year
panel and the full source ID for final hash ranking. Hash ordering is a
prespecified deterministic sampling procedure, not a statistical power claim.

B enumerates all records in the pinned P18/1, P19/1, 2020.acl/main,
2021.acl/main, 2022.acl/main and 2023.acl/main volumes, plus the six primary-cs.CL
submission-day inventories for June 15, 2018 through 2023. Other ACL volumes are
outside this fixed pilot scope. No ten-record preview truncation is used.
An invalid record stops collection for review; it is not silently discarded.

The fixed curation panels precede provider-independent language, fact, identity
and duplicate review. Every panel member needs include/exclude/pending and a
reason. Pending reviews cannot freeze. A needs retained authoritative abstract
v1 evidence, a curator-confirmed timestamp and agreement with API discovery
metadata. A contradiction stops selection even if the curator proposes an
exclusion. Missing v1 evidence can be explicitly excluded as unverified evidence;
it is not a verified date or confirmed outside-scope paper.

Exact-ID plans use only the frozen panel's base arXiv IDs, at most ten per call.
Missing, repeated or unrequested IDs fail validation; search fallback is absent.
ACL panel/final metadata are exact-ID selections from the complete pinned XML,
requiring no additional HTTP query. Already retained panel metadata covers the
final selected subset without an extra request. Curators must reconcile any newer
metadata instead of overwriting the frozen source facts.

B requires a recorded uniform identifier-inspection procedure before assigning
strata. `doi_only` and `arxiv_only` describe the verified frozen inventory, not a
proof that another identifier does not exist. Inspect source-declared arXiv DOI
aliases uniformly; an alias makes an inventory dual. A DOI/arXiv pair requires
an authoritative individual-record declaration or a two-reviewer identity bridge.
Whole-feed co-occurrence cannot establish that bridge. Source provenance must
link to retained raw hashes, source URLs, origins and actual retrieval times.
New mappings require independent approving reviewer IDs and no conflict.
Translations/derivatives cannot automatically become SAME_WORK. Possible
duplicates remain warnings; verified exclusions require an included verified
representative and explicit reviewed evidence. Shortfalls stop expansion/freezing.

Selection tests construct metadata-only provider request objects offline and
reject identifiers/evaluation IDs in their submitted search metadata. No provider
request is sent. Final datasets and selected-only mappings remain compatible with
the existing identity evaluator. Acquisition labels and actual source evidence
are retained in the enclosing pilot snapshot, not inferred from citation titles.

## Exact bounded request inventory

The fully expanded example A URLs are in
`artifacts/milestone-3c7-offline/a-enumeration-plan.json`; the one exact upstream
resolution URL is in `acl-resolution-plan.json`. Both are **unexecuted plans**.

| Stage | Endpoint and exact selection | Maximum attempts |
|---|---|---:|
| A enumeration | `https://export.arxiv.org/api/query`, four fixed days, `cat:cs.CL AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]`, ascending submittedDate, max_results=100, start=0/conditional 100 | 8 |
| A panel metadata | Same API, id_list of frozen panel IDs only, max_results=batch length, start=0; batches <=10 | 3 |
| A v1/alias evidence | `https://arxiv.org/abs/<panel-base-id>`, exactly one per panel member | 24 |
| B authentic revision resolution | `https://api.github.com/repos/acl-org/acl-anthology/commits?per_page=1` | 1 |
| B ACL enumeration | `https://raw.githubusercontent.com/acl-org/acl-anthology/<verified-commit>/data/xml/<collection>.xml`, collections P18, P19, 2020.acl, 2021.acl, 2022.acl, 2023.acl | 6 |
| B arXiv enumeration | Same API/date selector, June 15 of each year 2018–2023; start=0/conditional 100 | 12 |
| B panel arXiv metadata | Same API, six exact frozen panel IDs, one batch | 1 |
| B arXiv v1/alias evidence | `https://arxiv.org/abs/<panel-base-id>`, six records maximum | 6 |

Upper bounds: **A 35; B 26 including pin resolution; combined 61**. An existing
vetted local checkout avoids the one revision-resolution HTTP request. This is
not authorization for any of these attempts. It does not authorize the old
conditional 198-request budget. No unused slot may be reassigned.

B's exact commit-bearing URLs cannot honestly be finalized until an authentic
revision is resolved and pinned. `pilot-plan-b` refuses an unproven pin. Follow-up
URLs likewise cannot exist before complete enumeration fixes the panel IDs.
Each stage emits an exact URL inventory and file hash for approval *before* it
can run; the caps above do not allow arbitrary pagination or identity searches.
Additional publisher/identity-evidence URLs need separate explicit approval.

Every captured request retains v2 `budget.json`, raw `body.bin`, SHA-256,
status, final URL, safe headers, actual UTC timestamps and deterministic extraction
under `attempt-NNN/request-001/`. The plan/run receipts record skipped conditional
slots, errors and provenance. Response/decompressed evidence limits remain 2 MB;
oversized ACL XML fails closed rather than becoming an incomplete frame. Genuine
upstream ACL compatibility and file sizes remain untested until authorized.

The sole network CLI path uses HTTPX, an identifying User-Agent, 20-second
timeouts, no redirects, zero transport retries, serial calls and three-second
spacing. It requires `--authorize-live`, an authorization reference, the exact
plan-file SHA-256, observed origin and an active planned UTC window. Attempts
also stop when the window ends. It creates new directories and never resumes or
overwrites an existing run. Offline commands do not construct an HTTP client.

## PowerShell commands

Run from the repository root. These preparation commands perform no networking:

```powershell
$cp = '.\.venv\Scripts\citeprobe.exe'
# Choose an approved run/window; this example remains an unexecuted proposal.
$start = '2026-11-23T00:00:00+00:00'
$end = '2026-11-24T00:00:00+00:00'
& $cp pilot-plan-a --reference-date 2026-11-23 --planned-start $start --planned-end $end --output a-plan.json
& $cp pilot-plan-acl-resolution --planned-start $start --planned-end $end --output acl-pin-plan.json
Get-FileHash -Algorithm SHA256 a-plan.json, acl-pin-plan.json
```

**Do not execute this next command until the exact inventory/hash and live budget
have been explicitly approved.** Its authorization string must identify that
approval, not this offline implementation milestone:

```powershell
$plan = 'a-plan.json' # Or the separately approved acl-pin-plan.json stage.
$hash = (Get-FileHash -Algorithm SHA256 $plan).Hash.ToLowerInvariant()
& $cp pilot-run $plan --authorize-live --authorization-reference '<explicit-stage-approval>' --plan-sha256 $hash --output-dir artifacts/empirical-pilot/a-enumeration-001
```

The output parent directory must exist and the run directory must be new.
For ACL resolution use a distinct directory such as `acl-pin-resolution-001`.
After the separately authorized resolution, pin it offline and generate the B
inventory (no guessed hash, branch tip or fabricated revision is accepted):

```powershell
& $cp pilot-acl-pin --evidence artifacts/empirical-pilot/acl-pin-resolution-001/attempt-001 --curator-id '<reviewer>' --output acl-revision.json
# Alternative: use a curator-vetted, already available genuine checkout; no clone/fetch occurs.
# & $cp pilot-acl-pin --checkout '<existing-checkout>' --curator-id '<reviewer>' --output acl-revision.json
& $cp pilot-plan-b --revision acl-revision.json --planned-start $start --planned-end $end --output b-plan.json
```

A Git remote URL alone is not independent proof of upstream authenticity. The
local route verifies real Git objects and the six collection tree entries;
curators must vouch for the checkout's provenance. Prefer retained HTTPS upstream
resolution evidence when that provenance is unavailable. No ACL revision has
been acquired or pinned as an observed fact during this implementation.

After an authorized complete enumeration, use these offline commands. Set
`$run` to the corresponding A or B run; write outputs outside the source run:

```powershell
$run = 'artifacts/empirical-pilot/a-enumeration-001'
& $cp pilot-frame $run --output a-frame.json
& $cp pilot-replay $run --output a-replay.json
& $cp pilot-curation-template $run --output a-review-template.json
& $cp pilot-plan-followup --source-run $run --frame a-frame.json --stage id_batch --planned-start $start --planned-end $end --output a-id-plan.json
& $cp pilot-plan-followup --source-run $run --frame a-frame.json --stage v1_verification --planned-start $start --planned-end $end --output a-v1-plan.json
```

Approve each exact follow-up inventory separately before using `pilot-run` with
a new output directory. Use a new actual planned window when necessary; never
backfill actual timestamps from the example window. Replay ID batches with
`pilot-replay <batch-run> --output <new-replay.json>`.

Copy the review template to a new reviewed file. Humans fill canonical author
segmentation and metadata, English-language verification, eligibility/exclusion
reasons, identity evidence, and actual reviewer times. For A, point each
`v1_evidence_directory` at that item's retained `attempt-NNN` bundle, record the
actual extracted timestamp and explicitly approve it. For B, also record the
uniform `identifier_inspection_protocol` and policy-compliant alias/mapping
evidence. No template contains automatic approvals. Preserve source runs and
review evidence at their recorded locations for replay.

```powershell
& $cp pilot-select --source-run $run --frame a-frame.json --review a-reviewed.json --output a-selection.json
& $cp pilot-freeze --source-run $run --frame a-frame.json --review a-reviewed.json --output artifacts/empirical-pilot/a-frozen-001
$anchor = (Get-FileHash -Algorithm SHA256 artifacts/empirical-pilot/a-frozen-001/integrity.json).Hash.ToLowerInvariant()
# Store this anchor independently of the snapshot.
& $cp pilot-verify artifacts/empirical-pilot/a-frozen-001 --integrity-sha256 $anchor
```

Freezing is append-only through the CLI, with hash verification and deterministic
selection replay. It is not filesystem WORM storage or cryptographic reviewer
attestation. Preserve external anchors and the source evidence alongside exports.
The snapshot also exports directly usable `dataset.json` and
`identity-mappings.json`; both are hashed and checked against the reproduced
selection. `citeprobe validate <snapshot>/dataset.json` uses the existing command.
Retain the snapshot's origin/date-basis metadata with these exports for any
separately authorized benchmark.

## Tests, limitations and next action

Actual offline validation results:

- Full `python -m pytest -q -W error --basetemp .pytest-tmp/milestone-3c7-final-exports`:
  **454 passed**, including 39 new pilot tests (102.80 seconds, final export checks included).
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: 108 files already formatted.
- `python -m mypy`: passed, 63 source/test files.
- `python -m mypy src tests scripts/source_feasibility_v2.py`: passed, 64 files.
  Checking that script alone without the source tree does not resolve the editable
  package's internal types; use the combined command above.
- Protected hash sets: 32/32 baseline, 5/5 C2, 5/5 C4 and 7/7 C6 entries matched.
  The C6 external anchor and deterministic v2 extraction replay also passed.
  See `artifacts/milestone-3c7-offline/integrity-check.json`.

New-code defects caught and fixed during regression testing: B final ranking
initially removed the arXiv source prefix contrary to the specified B hash input;
typed provenance URLs were initially compared to raw strings without conversion;
reserve identity mappings initially risked referencing papers absent from the
final selected dataset. Tests now cover all three. No historical retrieval,
evaluation or research metric definitions were changed.

Synthetic tests cover complete/empty 0–200-record frames, pagination cap/overlap/
changing totals, 429/500/redirect/timeouts, primary-category exclusions, possible
duplicates, fixed panel hashes, exact-ID batches/replay, v1/source contradictions,
missing evidence, origin mismatch, review coverage, two reviewers, translation
guards, fabricated aliases, B strata, zero-selection/shortfalls, CLI protection,
selected-only evaluator mappings and frozen tampering. All new fixtures are
simulated; fake hashes and identifiers are never asserted as observed evidence.

Implemented offline readiness: **GO for preparing/reviewing the bounded A plan**
and **GO for genuine ACL-pin preparation**. Live execution: **NO-GO until separate
stage-specific authorization**. B enumeration additionally needs the authentic
revision. Both final samples need actual evidence and curator decisions. The B
arxiv_only stratum may be empty after uniform DOI-alias inspection; report that
shortfall instead of hiding aliases or widening the frame. Real HTTP acceptance,
source XML compatibility and sufficient eligible panels remain unverified.

The smallest next action is to approve the exact A enumeration inventory/hash,
R/window and maximum eight requests, and separately the one exact upstream ACL
revision-resolution request (or supply a vetted existing checkout). Then run those
bounded stages locally, replay them, approve their now-exact ID/v1 follow-ups,
curate, select and freeze. No additional planning milestone is needed. Benchmark
lookups and any larger samples remain separately authorized.
