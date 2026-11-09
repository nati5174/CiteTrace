# Milestone 3C-3: empirical pilot acquisition plan 1.0

Status: proposed for approval, NOT authorization to acquire or collect. This is a
workflow-validation pilot targeting A=8 and B=6 verified papers. Neither panel
supports statistical findings, full-frame coverage claims or indexing latency.
No HTTP requests, dataset creation or benchmark lookups were performed to prepare
this plan. Identity policy revision 1.1 and existing metric definitions apply.

## 1. Fixed reference and study scope

Propose R=2026-11-23 UTC as the Experiment A reference date. A later benchmark,
if separately authorized, would finish on that UTC date, nominally within
12:00–20:00 UTC, inside the default 24-hour window. This plan does not authorize
that benchmark. Planned acquisition/review: 2026-11-16 through 2026-11-22 UTC,
with exact approved request windows fixed in the execution manifest. Actual
request/verification times are populated only from execution and review.

If feasibility, software or review is not ready, do not roll dates silently.
Approve a new plan version/reference/window and regenerate the relevant frame.
Preserve partial acquisitions as their original versions. Cohort calendar dates:

| Age, inclusive | Verified first-public-announcement date |
|---|---|
| 1–7 | 2026-11-16 through 2026-11-22 |
| 8–14 | 2026-11-09 through 2026-11-15 |
| 15–30 | 2026-10-24 through 2026-11-08 |
| 31–60 | 2026-09-24 through 2026-10-23 |

Age is R minus verified public date in UTC calendar days. Day zero, revisions,
future dates and ages above 60 are outside A. Submission dates, latest-version
dates, feed-generation times and registry deposit times cannot substitute.

### Proposed pilot-only amendments requiring approval

To keep human verification finite while retaining complete, reproducible source
enumeration, propose two-stage pilot frames:

- A: enumerate the complete authoritative announcement inventory for all 60 days,
  then deterministically preselect six records per cohort (24 total) BEFORE
  English-language and bibliographic screening. Completely screen that fixed
  panel, then select two eligible papers per cohort. The final pilot frame is the
  eligible subset of this predeclared panel, not the entire 60-day population.
- B: enumerate the fixed repositories described below, deterministically select
  a fixed 18-record curation panel before identity-stratum screening, completely
  verify it, then select two papers per verified stratum if available.

These are explicit narrower workflow frames, not silent modifications of the
40/60-paper protocols. Approval is needed. No reserve beyond these fixed panels
is used in this pilot; an undersubscribed cohort/stratum is a reported shortfall
and does not trigger outcome-driven or unbudgeted expansion. If the amendments
are rejected, the full-frame screening burden and budget need a new plan.

## 2. Authoritative first-public-announcement verification: blocking gate

The current submittedDate query is NOT an authoritative public-date frame.
Neither the arXiv v1 submission timestamp nor an abstract page's submission
history proves the first public announcement. RSS availability alone is not
proof of a complete historical archive or the semantics of its dates.

Propose an initial source-feasibility stage of at most THREE requests, separately
authorized before any empirical frame enumeration:

1. GET `https://info.arxiv.org/help/api/user-manual.html`
2. GET `https://info.arxiv.org/help/rss.html`
3. GET `https://rss.arxiv.org/atom/cs.CL`

No redirects, retries or links followed. These are proposed exact URLs, not a
claim that they were fetched or their current formats verified in this task.
Record inaccessible/redirected pages and stop that branch. Documentation access
is also a live request and requires authorization. A rolling feed cannot by
itself satisfy the 60-day historical requirement.

The feasibility deliverable must establish: an official dated historical source
or repository-supplied historical export; explicit meaning of its announcement
date/time; complete new-versus-cross-list/replacement semantics; primary-category
evidence; UTC conversion or documented day precision; historical retention; exact
archive/export endpoint templates, pagination, and terminal/completeness markers.
The historical archive URL is presently UNRESOLVED. No invented URL template,
assumed weekday release schedule or inferred announcement lag is accepted.

If official available evidence cannot establish those facts, A is NO-GO under the
current policy. Ask for a repository-supported export or propose a future
prospective capture design in a separate approved amendment; do not relabel a
submission-date study as first-public coverage. Do not contact repository staff
without explicit authorization either.

Once established, archive evidence must explicitly associate each base arXiv ID
with its earliest NEW public announcement. A later cross-list or replacement is
not first public availability. If cs.CL is a later classification, a cs.CL listing
date is insufficient: establish the original release or keep the paper pending.
Define primary-cs.CL at the frozen metadata snapshot, disclose that timing, and
exclude cross-list-only cs.CR etc. from A. Language is determined from actual
metadata by a curator; uncertain language is not automatically English.

For each accepted public date retain the actual authoritative source URL, record
ID, dated section/field, new-announcement type, precision/timezone, concise evidence
excerpt, response/projection hash, collection and review times. A direct source
fact does not need two identity reviewers, but the responsible curator must
document the verification. Conflicting dates remain pending. Two reviewers are
still required for newly asserted cross-record identity bridges.

## 3. Experiment A complete enumeration and selection

After the feasibility gate and exact endpoint approval, enumerate every archive
page/record needed for R-60 through R-1, retaining new/cross-list/replacement
distinctions, rather than simply taking the first eight API results. Proposed cap:
120 historical archive requests total, at most 100 records/page; no more than
12,000 entries before normalization. Endpoint/page-size support must first be
verified. The cap is a stopping limit, not a promise of completeness.

Validate first/last dates, page offsets or opaque cursor chain, stated totals,
terminal pages, duplicated/missing pages and time consistency. Deduplicate repeated
listings by the same verified base ID with a recorded listing-history decision.
Different IDs/DOIs are not automatically the same work. Retain possible duplicates
as review flags. If any required archive is absent, any total fails reconciliation,
or the cap is exhausted, stop WITHOUT sampling. A truncated inventory is diagnostic.
Freeze inventory bytes/projections, hashes, source revision/acquisition cutoff and
enumeration log before using a seed. Dynamic-source changes require a new version,
not a quiet refresh of selected pages.

Within each proven public-age cohort rank the complete primary-cs.CL announcement
inventory by SHA-256 of UTF-8 `citeprobe-A-pilot-panel-v1|seed=0|<base-id>`, digest
then ID tie-break. Take the first six. If fewer exist, record the shortfall. Do
not use provider results, title popularity, DOI availability or likely success.

Retrieve canonical Atom metadata for at most 24 panel IDs in batches of ten:
`https://export.arxiv.org/api/query` with `id_list=<comma-separated-frozen-IDs>`,
`start=0`, `max_results=<batch-size <=10>`. Maximum THREE requests, no pages or
fallback queries. Inspect missing/duplicate returned IDs and reconcile against the
exact requested inventory; API ordering need not equal requested order. This
id_list adapter is proposed future preparation work, not supported by the current
submittedDate-only CLI. These are discovery/ground-truth requests, not evaluation
provider queries; their identifiers must never enter benchmark lookup hints.

Allow up to 24 individual GETs to `https://arxiv.org/abs/<base-id>` for panel
metadata/alias verification. Such pages are not automatically announcement proof.
Reuse frozen announcement evidence for dates; do not fetch PDFs or follow links.
Screen ALL panel members with include/exclude/pending and reasons. Do not replace
unverifiable public dates with submission dates. Unfinished verification leaves
the frame unready; it is not silently converted to a definitive eligibility fact.

Freeze the completely screened eligible panel. Final within-cohort selection uses
the existing `citeprobe-A-v1|seed=0|<base-id>` ranking and target two per cohort.
Record the remaining eligible panel members as reserves but do not automatically
request replacements. New verified duplicate decisions select one explicit
representative; possible duplicates never automatically merge or exclude.

## 4. Experiment B complete source inventory and panel

Propose a bounded pilot union, independent of provider results:

- ACL Annual Meeting metadata collections at ONE curator-approved 40-hex commit:
  `P18.xml` (volume 1), `P19.xml` (volume 1), `2020.acl.xml`, `2021.acl.xml`,
  `2022.acl.xml`, `2023.acl.xml` (volume main). Exact current repository filenames
  and volume semantics must be confirmed from the approved pinned inventory.
  The 2018/2019 long-paper restriction and later main-volume scope must be
  disclosed; this is not all cs.CL publications. Do not silently substitute files.
- arXiv primary-cs.CL records submitted on June 15 UTC in each year 2018–2023,
  English metadata after screening. This explicit six-day restriction is a pilot
  frame amendment, not the full 2018–2023 arXiv population.

Exact ACL URL template:
`https://raw.githubusercontent.com/acl-org/acl-anthology/<approved-40-hex-commit>/data/xml/<collection>.xml`.
The commit is an explicit approval prerequisite, not an invented release pin.
Six GETs maximum, no redirects/retries. Parse the entire relevant volume inventory
before selecting; the existing ten-record preview is not sufficient.

Exact arXiv endpoint: `https://export.arxiv.org/api/query`. For each YYYY in
2018..2023 use `search_query=cat:cs.CL AND submittedDate:[YYYY06150000 TO YYYY06152359]`,
`sortBy=submittedDate`, `sortOrder=ascending`, `max_results=100`, with starts 0
and, only if required, 100. Maximum TWO pages per day, TWELVE requests total.
Reconcile totalResults/startIndex/itemsPerPage and unique base IDs; if more than
200 records/day or source inconsistency remains, stop and report the exceeded
bound. Complete enumeration must precede any panel selection. Apply primary
category and canonical representation/year rules with a recorded decision.

The canonical representation's bibliographic year must fall in 2018–2023; source
submission and publication years are retained separately where they differ.
Do not infer that a source release/revision date is the publication year. Preserve
complete source metadata, author order and explicit identifiers.

Make a fixed provider-independent curation panel: hash-rank each ACL year's
inventory using `citeprobe-B-pilot-panel-v1|seed=0|acl|<record-id>` and take two;
hash-rank each arXiv day's inventory using the same prefix with `arxiv` and take
one. Total at most 18 source records. Keep shortages instead of widening dates.
Review all panel records, including known repeated versions. Source-record count
is not scholarly-work count. Verified duplicates get an explicit representative
and exclusion; nonconclusive similarities remain flags.

Allow up to 18 verification requests to the canonical authoritative panel URLs,
`https://arxiv.org/abs/<base-id>` or `https://aclanthology.org/<explicit-record-id>/`.
Do not construct record IDs from numbering or assume linked pages were fetched.
Source XML already acquired can serve as evidence without another request if it
supports the fact. No Crossref/OpenAlex discovery requests are allowed.

Operational strata after complete panel verification:

| Stratum | Required evidence |
|---|---|
| doi_only | Authoritative DOI and canonical facts verified; no arXiv ID in the frozen verified inventory |
| arxiv_only | Authoritative arXiv base ID and canonical facts verified; no DOI in the frozen verified inventory |
| dual | Both identifiers verified AND an authoritative source-declared or approved cross-record bridge |

Only/dual describe verified inventory, not proof that another identifier does not
exist anywhere. In particular, an arXiv-issued DOI alias makes a verified inventory
dual; do not call it arxiv_only just because no publisher DOI is known. Apply a
uniform fixed evidence inspection procedure to every panel record, document missing
fields and verification reach, and freeze that procedure before assigning strata.
Do not selectively search harder to fill a deficient stratum. If source-declared
aliases make arxiv_only empty, report that operational issue instead of hiding
aliases or changing the definition to publisher-DOI-only.

Reserve up to 12 additional authoritative identity-evidence page requests for the
whole A/B pilot, only after an explicit URL list is approved. No arbitrary DOI
redirect chains. New cross-record mappings require two independent approvals;
matching metadata or a DOI-version cluster alone is insufficient. Pending,
conflicting or derivative relationships do not establish dual membership. Pending
decisions must be resolved or explicitly recorded as missing evidence before the
panel can be frozen as screened; no unsupported binary identity is forced.

Final B selection uses existing `citeprobe-B-v1|seed=0|<source-id>` order within
the eligible verified stratum, target two each. Canonical source IDs and verified
representatives are frozen before ranking. If two per stratum are unavailable,
report the shortfall and STOP expansion pending a revised approved plan.

Mutation algorithm 1 and seed 0 remain unchanged. Record applicability for all
five categories, including separate year -1/+1 mutations and explicit skips for
missing volume/issue or no-change cases. Mutations are independent changes from
canonical values, never compound mutations. No real mutation generation or
provider lookup occurs in this acquisition-only milestone. All future benchmark
requests must pass identifier-isolation checks and use only intended metadata.

## 5. Finite budgets and request discipline

| Stage | Upper bound | Prerequisite |
|---|---:|---|
| Official source/date feasibility | 3 | Separate approval of three listed URLs |
| A historical announcement pages | 120 | Historical endpoint/date semantics and enumeration approved |
| A panel metadata batches | 3 | Frozen 24-ID panel; id_list adapter verified offline |
| A panel abstract pages | 24 | Frozen panel and exact URL list |
| B pinned ACL collections | 6 | Actual commit and collection inventory approved |
| B six-day arXiv enumeration | 12 | Explicit date queries/page bounds approved |
| B panel verification pages | 18 | Frozen 18-record panel and URL list |
| Additional identity evidence | 12 | Exact authoritative URLs approved separately |
| **Conditional total ceiling** | **198** | Not a blanket authorization |

No retries, redirects, secondary URLs or benchmark queries are included. Every
actual HTTP attempt, including failure and documentation access, consumes budget.
Use serial requests, at least three seconds between arXiv requests, HTTPX pooling,
20-second timeouts, two-megabyte response cap as current default, sanitized evidence
and identifying User-Agent. If a complete source file exceeds the cap, STOP; do
not silently raise it, truncate it into a complete frame or fetch extra pages.
Respect Retry-After by stopping/scheduling only under a new approved request;
there is no automatic retry. Disclose source-mandated access limits when verified.

The large ceiling reflects enumeration and verification, not permission to gather
198 arbitrary papers. Unused stage budget cannot move to another stage. Stop at
any failed gate rather than spending later-stage budget. A smaller pilot does
not make complete-frame enumeration free. Full 40/60-paper scaling requires its
own frame, review workload and budget approval.

## 6. Curator checklist, outputs and stopping rules

For every source attempt record planned request, actual UTC start/end, source URL,
status/error, byte/projection hash, origin observed, item count and budget debit.
Capture only necessary public metadata/excerpts. Keep simulated fixtures and
unknown-origin inputs in separate outputs, never as empirical observations.

Curators must reconcile the entire frame and panel inventories; check identifiers,
primary category, language, complete author order/name segmentation, metadata
representation/year, first-public evidence for A, aliases/bridges, duplicate flags,
derivative status, and every inclusion/exclusion/pending reason. Record responsible
reviewer IDs and actual review times. New identity mappings need two approvals;
direct authoritative baseline declarations are exempt, not exempt from conflicts.
Provider performance remains unavailable during sampling/review.

Expected fresh artifact directory after separate authorization:

```text
artifacts/empirical-pilot-v1/
  approval.json                    # exact source plans, budgets, digests, windows
  requests.jsonl                   # append-only attempts, failures, budget counters
  sources/                        # safe metadata evidence, hashes, actual times
  enumeration/                    # all page/cursor/count checks and terminal proof
  frame-a.json                    # complete announcement inventory + decisions
  frame-b.json                    # complete pinned/six-day inventories + decisions
  panel-a.json                    # 24-ID preselection, seed/hash rank/shortfalls
  panel-b.json                    # 18-record preselection, before stratum screening
  review/                         # dates, facts, aliases, approvals, disagreements
  screened/                       # complete panel decisions and eligible inventories
  selection-a.json                 # target 2 per cohort, recorded reserves
  selection-b.json                 # target 2 per stratum, recorded reserves
  frozen-a/                       # new Dataset/ResearchManifest/selection/integrity
  frozen-b/                       # same, with external integrity anchors
  readiness.json                  # remaining evidence gaps; no benchmark results
```

The inventory names describe the proposed batch workflow, not files already
created or commands already implemented. Freeze original inputs, never modify
canonical pilot_dataset.json, Milestone 2 evidence or a prior snapshot. Compare
all 32 protected baseline hashes before/after and retain input/output digests.
Preserve existing versions rather than overwriting or resuming partial runs by
editing them. A new run needs explicit approval of remaining/new attempts.

Stop on uncertain first-public semantics, unavailable historical coverage,
inconsistent totals, missing pages, byte/budget cap, inaccessible source, request
outside approved window, hash mismatch, undisclosed source changes, review
disagreement, missing required identity approval or proposed unsupported
equivalence. Keep diagnostic evidence. Do not make a failed query an exclusion
from the scholarly population. For frame/panel eligibility, record missing evidence
separately from confirmed outside-scope. Provider errors or retrieval identity
uncertainty must never determine replacements. No significance/coverage conclusions
follow from these 8/6 workflow targets.

## 7. Execution commands and implementation boundary

Current software supports single-page arXiv submittedDate discovery and bounded
ACL previews. It DOES NOT yet implement a historical announcement adapter,
complete multi-page enumeration, id_list metadata acquisition or this two-stage
panel workflow. Do not run repeated preview commands to imitate a complete frame.
No fictional batch command is supplied as executable software.

Immediately usable offline commands, requiring completed curator files:

```powershell
Set-Location C:\Users\netha\yc\CiteTrace
.\.venv\Scripts\citeprobe.exe dataset-validate curated-a.json --manifest manifest-a.json
.\.venv\Scripts\citeprobe.exe dataset-sample curated-a.json --manifest manifest-a.json --output selection-a.json
.\.venv\Scripts\citeprobe.exe dataset-freeze curated-a.json --manifest manifest-a.json --output frozen-a
.\.venv\Scripts\citeprobe.exe dataset-verify frozen-a --integrity-sha256 <retained-hash>
```

Repeat with B files after reviewed-source linkage using acquisition-sample. These
commands do not acquire empirical papers and must not use fabricated placeholders
as actual inputs. Sample targets are 2 per approved group in the research manifest.

Exact future syntax for an individually authorized EXISTING single-page command:

```powershell
.\.venv\Scripts\citeprobe.exe acquisition-run <approved-plan.json> --authorize-live --authorization-reference '<approval-ID>' --plan-sha256 <approved-file-hash> --output-dir <fresh-run-directory>
```

This is NOT the full empirical pilot runner. The three source-feasibility URLs
and historical stages cannot be executed through that CLI today. Therefore exact
executable commands for the COMPLETE acquisition batch cannot honestly be provided
yet. Before live authorization, approve a minimal offline implementation that
adds the validated source-specific endpoints, enumeration/terminal checks,
stage-specific counters, deterministic panel selection and replay fixtures. It
must reject arbitrary URLs, retries/redirects, missing budgets and schema conflicts,
pass full pytest/Ruff/mypy, and produce a concrete dry-run request inventory.
Publish exact PowerShell commands against that implemented/approved inventory
before executing. Implementing or running that extension is outside this plan.

## 8. Approval questions and readiness

Approve or adjust: R/window; the 24/18 fixed-panel amendments and no unbudgeted
reserves; primary category at metadata-freeze time; the B pinned-ACL/six-day union
and year/track restrictions; inventory-based DOI-only/arXiv-only definitions
(including arXiv-issued DOI aliases); budgets and byte limits; reviewer assignments;
and the minimal source-feasibility/enumeration software work.

NO-GO now for empirical acquisition. The historical first-public source endpoint
and semantics remain unresolved, the ACL pin is not selected, and the required
complete-frame runner is unimplemented. The plan deliberately does not invent
those facts or claim policy feasibility from a successful API request.

GO now for plan review and proposing the bounded source-feasibility preparation.
After exact historical endpoints, semantics, frame/panel amendments, software,
provenance/reviewer procedures, budget inventories and protected snapshots pass
review, request explicit stage-specific live authorization. Approval of this
document alone does not authorize HTTP requests or benchmark execution.
