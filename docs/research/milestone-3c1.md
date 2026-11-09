# Milestone 3C-1: acquisition preparation

This release implements acquisition infrastructure and offline tests only. No
live acquisition, provider searches, benchmark runs or empirical dataset expansion
were performed. No Milestone 2 evidence or existing frozen snapshot was changed.
New metadata fixtures are invented and explicitly simulated.

## Architecture and supported sources

- `acquisition_models.py`: source plans, bounded request evidence, pending
  candidates, review items, immutable audit IDs and curator decisions.
- `acquisition_sources.py`: DiscoverySource interface, arXiv Atom and commit-pinned
  ACL Anthology XML adapters, safe metadata projection and identifier parsing.
- `acquisition.py`: single-attempt collection, deterministic offline replay,
  duplicate/conflict flags and explicit review-to-research sampling integration.
- `acquisition_cli.py`: plan, replay, reviewed sampling and an explicitly gated
  future live command. Existing resolver/evaluator contracts remain unchanged.

The source interfaces are discovery only. They do not call OpenAlex or Crossref.
The arXiv source is `https://export.arxiv.org/api/query`; it requests cs.CL records
with a fixed submitted-date range, ascending submission order, offset zero and
at most five records by default (maximum ten). The canonical source URL for a
candidate is its arXiv abstract record. Submitted/updated timestamps are preserved
with timezone validation. No DOI is invented from an arXiv identifier pattern.

ACL metadata comes from the original acl-org/acl-anthology repository, pinned to
an explicit 40-character commit and collection XML filename. No moving main branch
or arbitrary URL is accepted. The parser uses the explicit paper URL/record ID,
complete author names, year, DOI, venue and volume/issue where present. It does
not infer a preprint identity from a DOI, or infer an ACL record ID from numbering.
The pin records a reproducible source revision, not proof of the truth of every
metadata field. Actual source-format compatibility is not claimed to have been
tested live. Endpoints and parser assumptions require the limited 3C-2 check.

Requests use HTTPX, one pooled connection, TLS verification, a 20-second timeout,
zero retries, redirects disabled, an identifying User-Agent and no inherited
proxy/authentication environment. One request per plan; no automatic pagination,
linked-record requests or PDF downloads. Public metadata sources are the intended
targets; a future authentication failure is an inaccessible record, not permission
to retry or add another URL. Only allowlisted metadata XML is retained, not full
webpages or PDFs. Author emails and unrelated source fields are omitted. The raw
response hash and projected-metadata hash are separate. Raw response bodies cannot
be independently rehashed later unless separately retained; projection integrity
and deterministic parsing can be verified.

## Experiment A frame and source rules

The research population remains English-metadata primary-cs.CL preprints whose
verified first public release is 1–60 UTC calendar days before an explicit
reference date, split into 1–7, 8–14, 15–30 and 31–60-day cohorts. The final reference
date and actual benchmark collection-end requirements remain those of protocol A.
Acquisition planning windows are a separate activity from benchmark collection.
Actual acquisition timestamps are always generated at collection, never copied
from planned windows. Out-of-window evidence stays in the audit with a warning.

The current arXiv query provides a bounded, deterministic candidate-discovery
slice using submittedDate; it is NOT a complete enumeration of this population.
A submission can precede public announcement and the queried range can miss a
delayed announcement. Atom published is recorded as submitted_at and is never
promoted to first_public_date. Every A item requires independent authoritative
public-announcement evidence. No first-public dates are automatically verified.

Before empirical A construction, approve an authoritative announcement inventory
or another demonstrated public-release source, its historical completeness and
enumeration/date semantics, a finite pagination budget, English/primary-category
screening and the acquisition-to-benchmark timetable. This release deliberately
does not guess RSS publication semantics or substitute a v1 submission date.
Public dates can be recorded by curators through the existing PreprintDate and
SourceEvidence contracts; `acquisition-sample` and research validation require
verified public-announcement provenance before cohort eligibility.

The source order is fixed before seeing any provider response. No evaluation
provider result is used for discovery, eligibility, replacement or date evidence.
Once a complete reviewed frame is approved, use the existing source-level hash
ranking, seed 0, cohort targets, reserves and exclusion ledger. Keep diagnostic
bounded slices separate from any later population-complete frame.

## Experiment B frame and source rules

The proposed frame remains English-metadata cs.CL scholarly works from 2018–2023,
using explicitly pinned repository/proceedings inventories. arXiv and ACL provide
complementary discovery; no single source is assumed to exhaust all three strata.
Review category/language, metadata representation, source-level duplicates and
frame completeness before sampling. No provider-success condition may be added.

Canonical papers need verified metadata and identity provenance. Strata are
doi_only, arxiv_only and dual according to the frozen verified inventory, including
verified baseline aliases. DOI presence alone never establishes an arXiv bridge.
Parsed source declarations remain pending until inspected; newly asserted
cross-record mappings need two independent approving reviewer IDs, whereas a
direct authoritative source-declared alias follows the baseline exemption.
Conflicts and translations cannot silently enter SAME_WORK.

Multiple source audits can be supplied to `acquisition-sample`. Every item needs
an explicit include/exclude decision; pending decisions block curated sampling.
No records are silently merged. Same-source duplicate entries and metadata/DOI
overlap produce POSSIBLE_DUPLICATE review flags, not automatic exclusions or
equivalence. Definitive duplicate handling remains in the research manifest.

For one audit, the frame hash is its metadata projection hash. For multiple
audits, it is the existing canonical fingerprint of a list of objects containing
audit_id and metadata_sha256, sorted by audit_id. Record aggregate frame evidence
separately, and link each paper's evidence hash and retrieval timestamp to its
own source audit. A curated source cannot be silently corrected or augmented:
additional authoritative evidence needs a new versioned acquisition/review audit.

Validate mutation applicability/skips offline with `dataset-validate --mutations`;
source volume/issue values are preserved when available. No applicability field
is fabricated to fill a panel. Existing canonical_tasks/mutation_tasks and research
preflight preserve metadata-only query isolation. This release never routes
acquired identifiers into provider search hints or executes mutation lookups.

## Human review and exclusions

1. Preserve response.json and audit.json. Replay them offline before reviewing;
   plan/request mismatches, XML hash mismatches and changed audits are rejected.
2. Review every item in source order, including malformed entries. Verify complete
   metadata, language/category/year, actual source-declared identifiers and any
   first-public date. No automatic bibliographic approval is made by the parser.
3. Record a CuratorDecision per item: item_id, include/exclude/pending, reason,
   reviewer ID, actual review time and citation_id for included items. Excluded
   invalid discovery items remain in the audit; they need not be forced into the
   canonical Dataset schema. Newly asserted identity mappings remain separate
   IdentityClaims with two approvals and authoritative evidence under policy 1.1.
4. Create the curated Dataset/ResearchManifest using the existing contracts and
   supporting SourceEvidence. All source fields must match the audited candidate;
   do not use this step to substitute unrecorded metadata or identifiers. Source
   evidence uses the projection hash and actual response finished_at as retrieval
   completion time. It is verified by the curator at the actual review time.
5. Run `acquisition-sample`, then freeze and verify through Milestone 3B commands.
   This is a reproducible reviewed selection, not independent certification of
   source truth or permission to run a benchmark. `frame_complete` remains false
   for bounded acquisition slices; do not present them as exhaustive research
   frames. Source selection/completeness requires explicit research sign-off.

Acquisition failure, malformed/partial data and empty source responses are
separate audit outcomes. Failed acquisition cannot be promoted into a reviewed
frame. Partial discovery and unprocessed-record counts remain disclosed; no
implicit retry, page fetch, replacement or budget extension occurs.

Observed/simulated/unknown origins are retained through replay and must agree
with the research ledger. The replay command has no relabeling switch. Origin
and human independence are assertions, not cryptographic attestations. Keep
review and mapping versions/hashes alongside the original immutable evidence.

## Offline commands available now

```powershell
citeprobe acquisition-replay tests/fixtures/acquisition/response-arxiv.json --output arxiv-review.json
citeprobe acquisition-replay tests/fixtures/acquisition/response-acl.json --output acl-review.json
citeprobe acquisition-sample arxiv-review.json acl-review.json --dataset curated.json --manifest research-manifest.json --decisions decisions.json --output selection.json
citeprobe dataset-freeze curated.json --manifest research-manifest.json --output frozen-curated
citeprobe dataset-verify frozen-curated --integrity-sha256 <externally-retained-hash>
```

The first two commands are usable with the supplied simulated fixtures. The
remaining commands require a real or explicitly simulated curator-completed
dataset, manifest and decisions; placeholders are not evidence. Output files and
directories must be new. Do not resolve every paper in a frozen source frame:
reserves and exclusions are not approved benchmark tasks.

## Proposed first live test: maximum ONE request

Recommend one arXiv request returning at most five candidate records, zero retries,
zero redirects, no pagination, verification pages, ACL requests or provider
queries. Its purpose is source-format/provenance compatibility only. It cannot
establish a complete frame or valid public-release cohorts. ACL needs a separately
approved pinned commit/collection and request budget after offline review.

The following local PowerShell preparation makes no network requests:

```powershell
Set-Location C:\Users\netha\yc\CiteTrace
$acqStart = [DateTimeOffset]::UtcNow
$acqEnd = $acqStart.AddHours(2)
.\.venv\Scripts\citeprobe.exe acquisition-plan --source arxiv_atom --experiment recent-preprints --reference-date $acqEnd.UtcDateTime.ToString('yyyy-MM-dd') --planned-start $acqStart.ToString('o') --planned-end $acqEnd.ToString('o') --max-records 5 --output acquisition-plan-001.json
$acqDigest = (Get-FileHash -LiteralPath acquisition-plan-001.json -Algorithm SHA256).Hash.ToLowerInvariant()
$acqDigest
```

Submit that plan and digest for approval BEFORE executing the following command.
If approval comes after the window expires, create a new plan and obtain approval
for its new digest; do not quietly alter dates. After explicit authorization for
that exact plan and window only:

```powershell
.\.venv\Scripts\citeprobe.exe acquisition-run acquisition-plan-001.json --authorize-live --authorization-reference 'Milestone-3C-2-approved-plan-001' --plan-sha256 $acqDigest --output-dir artifacts\acquisition-001
```

The artifacts parent must already exist. Return plan.json, response.json and
audit.json. A failed/partial run must not be rerun without a new explicit request
budget. The opt-in flag records intent; it is not a substitute for actual user
authorization. This milestone does not grant that authorization.

For later ACL preparation (still offline), obtain a curator-approved repository
commit and collection ID, then use `acquisition-plan --source acl_xml --experiment
mutation-robustness --acl-commit <40-hex-commit> --acl-volume <collection-id>` with
explicit planned timestamps and an output path. No commit or volume has been
silently selected for a future empirical study.

## Research decisions and go/no-go

GO for review of a one-request 3C-2 infrastructure probe, after the exact plan,
window and budget are approved. NO-GO for that request until approval arrives.
NO-GO for empirical A/B dataset construction or benchmark collection.

Remaining decisions: authoritative public-announcement source/date semantics and
completeness; exact ACL releases/collection scope; full-frame pagination budgets;
language/category screening method; independent curator assignments; handling of
ambiguous duplicates; and later acquisition/benchmark schedules. Current official
access requirements were not checked online because live HTTP is prohibited.
No new source assumption, policy exception or identity mapping was auto-approved.

## Executed verification

Final source checks:

```text
python -m pytest -q -W error --basetemp .pytest-tmp/milestone-3c1
371 passed in 12.25s
python -m ruff check .
All checks passed!
python -m ruff format --check .
81 files already formatted
python -m mypy
Success: no issues found in 49 source files
```

The 30 new acquisition tests use synthetic XML and mocked HTTP only. CLI replay
also produced simulated arXiv/ACL audits under artifacts/milestone-3c1-offline;
two arXiv replays are byte-identical. All 32 protected Milestone 2/canonical hashes
in the saved Milestone 3A baseline still match. No empirical dataset or frozen
research snapshot was modified.

Checks caught malformed-XML exception handling, optional-element typing and a
reference-date consistency gap during implementation. XML failures now produce
an explicit API_ERROR audit, and acquisition-to-research sampling rejects a
changed Experiment A reference date. No Part 3 identity or metric rules changed.
