# Proposed amendment A-S1: eight-paper submission-age workflow pilot

Version: 1.0. Status: **PROPOSED; NOT ADOPTED; NO COLLECTION AUTHORIZATION**.
This is a separate pilot variant. It does not modify docs/research/v1/experiment-a.md,
the original announcement-age protocol, its historical outputs or metric definitions.

## Purpose and date basis

Validate the acquisition-to-evaluation workflow using eight verified papers, two
per age band, without asserting historical public-announcement coverage. The
estimand is verified retrieval coverage under the recorded metadata-only strategy
by **first arXiv submission age** in the explicitly restricted pilot frame.
It is not announcement age, publication age, database presence or indexing latency.
Eight papers do not support general performance or statistical conclusions.

Age = fixed UTC reference date R minus the UTC calendar date of the authoritative
v1 submission event. Preserve its original offset and normalized UTC timestamp,
source URL, raw evidence hash and actual verification time. News-feed published,
API published, version updated and collection time are distinct fields: never
transfer semantics between interfaces solely because element names match.

The query API's submittedDate index is a discovery selector. Before accepting
panel ages, a curator must compare the API submission-related value with the
authoritative abstract record's v1 submission history. No API timestamp is silently
promoted to verified first-public evidence. An inconsistency is a source-semantics
stop condition, not a reason to cherry-pick a replacement. An unavailable v1 date
is pending evidence and prevents that item from entering a verified-age sample.

R remains proposed as 2026-11-23 only if the user approves it and execution can
meet the approved collection window. Otherwise approve a new version/R before
enumeration. Actual timestamps are never filled from the plan. Required age bands
are 1–7, 8–14, 15–30 and 31–60 days inclusive; day zero/future dates are outside scope.

## Small, completely enumerated pilot frame

To keep the workflow pilot bounded, propose one prespecified UTC submission day
per band, at ages 4, 11, 22 and 45 days before R. For the proposed R these are:

| Band | Fixed source day | Target |
|---|---|---:|
| 1–7 | 2026-11-19 UTC | 2 |
| 8–14 | 2026-11-12 UTC | 2 |
| 15–30 | 2026-11-01 UTC | 2 |
| 31–60 | 2026-10-09 UTC | 2 |

This is an explicit pilot-only frame restriction requiring approval, NOT a
representative sample of all days in those bands or a replacement for the
40-paper research design. If a full 60-day frame is preferred, approve its larger
enumeration/screening budget instead; do not silently mix designs.

For each day enumerate the complete query API result at
https://export.arxiv.org/api/query with:

```text
search_query=cat:cs.CL AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]
sortBy=submittedDate
sortOrder=ascending
max_results=100
start=0, then 100 only if required by the saved total
```

At most two pages per day, eight enumeration attempts total. Reconcile offsets,
returned counts, totalResults, unique base IDs and expected last page. If a day
exceeds 200 records, counts change, a page is missing or ordering causes overlap,
stop and preserve the incomplete run. Do not use the first page as a complete frame
or extend the budget automatically. Freeze all response bytes and the inventory.

Filter primary category cs.CL from metadata at that frozen snapshot; a cs.CL
cross-list with another primary category does not qualify. Record that primary
category is snapshot-based, not proven historical classification. All language,
fact, identity and duplicate checks remain provider-independent.

After enumeration, rank the whole primary-category inventory within each source
day by SHA-256 of UTF-8
`citeprobe-A-submission-panel-v1|seed=0|<base-arxiv-id>` (digest then ID tie-break).
Take six per day, at most 24 items, as a fixed curation panel before English-language
and full bibliographic screening. Completely record panel decisions. This two-stage
pilot restriction also needs approval; it must not be described as random sampling
from all eligible papers in the original research population.

Verify all panel members with source-linked evidence, including full author
sequence/name segmentation, language, metadata version, v1 timestamp and declared
identifiers. New identity bridges still require policy-compliant approvals.
Possible duplicates remain warnings. Verified duplicates need an explicit
representative and logged exclusion. Pending evidence is distinct from confirmed
outside-scope. Do not replace difficult identities based on retrieval expectations.

Select two fully eligible papers per band from the frozen screened panel using
`citeprobe-A-submission-v1|seed=0|<base-arxiv-id>`. Record eligible reserves but
do not use an unapproved expansion if fewer than two qualify. Report shortages.
No OpenAlex/Crossref lookup or expected result may influence any selection.

## Proposed acquisition ceilings, requiring separate authorization

- Eight enumeration requests maximum.
- Up to three selected-panel ID batches, at most ten exact IDs per request,
  only if metadata batching is explicitly included in the approved execution plan.
  These requests must reconcile missing/duplicate IDs and cannot become searches.
- Up to 24 authoritative abstract-record verification requests, one per panel item.

Conditional acquisition ceiling: 35 attempts. Do not spend unused stage budget
on different endpoints. No retries, redirects, PDFs, provider lookups or secondary
identity-evidence URLs are included. Any extra identity verification needs an
explicit URL/budget approval. Raw/decoded limits remain two megabytes; a bound
failure stops that branch and cannot be presented as complete enumeration.

The eight-paper later benchmark would be a different authorization and inventory.
This amendment authorizes neither acquisition nor benchmark execution.

## Required implementation and compatibility

Add a typed submission-date basis and a distinct pilot/experiment label. Do not
write submission timestamps into PreprintDate.first_public_preprint or relabel
existing recent-preprint reports. Preserve the current announcement-age validation
and metric formulas. Cohort arithmetic can be reused, but date evidence and labels
must state first_submission explicitly. Require v1 provenance before inclusion.

Add bounded page plans, complete-inventory reconciliation, selected-ID batching,
and deterministic panel decisions under the existing raw-evidence and research
ledger infrastructure. Existing preview commands remain previews. Freeze reviewed
source inventories, decision logs, mappings and final selections to new directories;
retain external integrity anchors and unchanged protected input hashes.

## Interpretation and approval

Report pilot counts, verified dates, exclusions, metadata/identity uncertainty and
workflow defects. Later retrieval metrics, if authorized, retain provider ranks,
evidence bounds, nulls and provider-error exclusions. No significance claims,
confidence intervals for these tiny groups, or general provider rankings.

Approval must cover the changed question/date basis, four fixed source days,
24-item curation panel, R/window, shortfall rules and implementation. Live requests
need a concrete reviewed plan and separate budget authorization. Until then this
document is a proposal and the original announcement-age policy remains unchanged.
