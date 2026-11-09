# Milestone 3C-6: final source feasibility and pilot readiness

This is the consolidated readiness decision and authorized-request handoff, not
another empirical study or a new infrastructure phase. No live request was made
in the network-restricted sandbox. The new single request is prepared for local
execution under the user's explicit 3C-6 authorization. Its results are pending.
No empirical acquisition, provider queries, mutation generation, protocol
amendments or protected-file edits occurred.

## 1. Is the one request justified?

Exact URL: **https://info.arxiv.org/help/atom_specifications.html**.
It appears in the saved official RSS-documentation link list in
artifacts/milestone-3c4/02-source.json, and is named in milestone-3c5.md. It is on
the official info.arxiv.org host and is already in the version 2 runner allowlist.
The original 3C-4 evidence hash was checked locally; no external URL was fetched
to establish this provenance.

Research question: what events do the feed's published/updated/announcement
fields denote, and what does the specification explicitly say about entry
types and coverage? Those definitions were not retained in the previous excerpts.
The specification can therefore materially inform the choice between a valid
prospective announcement study and a separately named submission-age study.

It cannot be assumed to contain a 60-day archive, historical access endpoints,
per-paper announcement dates or proof of complete coverage. HTTP 200 or an
EXTRACTED status would establish none of those facts automatically. The raw page
can be reviewed offline even if paragraph extraction misses a relevant section.
No linked request is needed or permitted for this question.

Budget: one GET, one attempt, zero redirects/retries/pagination/linked requests,
20-second timeout, two-megabyte raw/decoded caps, identifying User-Agent, UTC
timestamps and version 2 raw bytes, hashes, headers, URL and budget provenance.
An error, redirect, truncation or inconclusive answer ends this authorization.
There is no new ACL authorization or permission to use the 198-request ceiling.

## 2. Smallest executable next step

Run once in the ordinary local Windows terminal:

```powershell
Set-Location C:\Users\netha\yc\CiteTrace
.\scripts\run_milestone3c6.ps1
```

No further confirmation is required for this exact request: the user already
authorized it. The wrapper validates the fixed one-URL plan and saved official
link, invokes the existing version 2 runner and refuses an existing run directory.
Return artifacts/milestone-3c6 in full, especially run-001/request-001/body.bin,
record.json, extracted.json, budget.json, manifest.json and both replay files.
The wrapper performs two offline verifications and checks byte-identical replay.
It never performs a second live request. Do not rerun on any failure or missing
evidence; return partial files and the terminal error.

This file and docs/research/3c6-atom-budget.json are preparation, not observed
results. The bundle directory does not exist until the local wrapper executes.
The one request is useful but not guaranteed to settle every source question.
After return, inspect raw source text and make the method decision directly;
no further generic preparatory milestone is proposed.

## 3. Experiment A: comparison and recommendation

| Approach | Scientific fit | Current feasibility | Decision |
|---|---|---|---|
| Authoritative historical announcement inventory | Closest to the original announcement-age question; permits retrospective cohorts if complete and correctly defined | No verified historical endpoint, export, earliest-NEW date chain or 60-day completeness proof | NO-GO now; retain if the requested page or supplied authoritative evidence establishes the missing facts |
| Prospective announcement capture | Preserves the question if source events really mean first public release, with complete capture and original versus cross-list/replacement handling | Needs validated date semantics, an approved acquisition schedule, gap handling and sufficient observation history; first-seen time alone is not first-public time | Defensible fallback when the original question is essential, but not an immediate retrospective 60-day pilot |
| Revised submission-age experiment | Different question: verified retrieval coverage by source submission age | Existing source query/parser supports submission-oriented discovery, but complete enumeration and final event-definition review remain required | Recommended near-term workflow-pilot amendment, explicitly subject to approval |

Recommendation: for an immediate eight-paper workflow pilot, seek approval for a
clearly labeled **submission-age retrieval-coverage** variant rather than repeatedly
trying to reconstruct an unverified historical announcement frame. Keep the same
four age bands and provider-independent sampling principles, but change the date
basis and question openly. Do not fill first_public_date with submitted_at.
If announcement age is non-negotiable, prefer prospective capture once the source
event semantics are established; adopt a new reference date and enough captured
history for the declared frame. Do not claim the November 23 retrospective design
is operational from an empty rolling feed.

Neither recommendation is automatically adopted. The approved first-public-age
protocol remains in force until the user chooses. Submission timestamps also need
an authoritative field definition; the specification request may help distinguish
fields, but if it does not answer submission semantics, do not guess them.

Any amendment must specify the date field/precision/timezone, exact bounded frame,
reference/end date, complete enumeration proof, eight-paper selection and screening
rules, and request budget. Cohort calculation is implemented; changing the
scientific date basis must be explicit in schemas/labels, not an overloaded
first-public-date field or silent relabeling of prior results. It remains
cross-sectional retrieval coverage, not indexing latency or database absence.

## 4. Experiment B: offline pin investigation and concrete scope

No verifiable ACL checkout, source archive, release manifest or real commit was
found in the workspace. The only ACL commit in saved acquisition data is
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, expressly synthetic. It is not a
candidate pin. CiteProbe's own Git revision is also not an ACL revision.
**An exact authentic ACL revision cannot be identified from the available offline
material.** This is a required input, not a problem solved by choosing a moving
branch or fabricating a plausible hash.

The shortest offline resolution is a curator-supplied vetted local ACL Anthology
checkout or an already obtained commit+metadata archive. From that checkout,
record git rev-parse HEAD and confirm the expected collection paths at that tree
with git ls-tree; retain the commit/tree and per-file SHA-256 values, source
identity and any uncommitted changes. Use immutable git show output from the
specified commit rather than uncommitted working-tree XML. Do not fetch or clone.
If no such local material is supplied, obtaining/validating the revision and
collection requires separate ACL request authorization. There is none here.

Proposed collection scope remains the explicit pilot union in pilot-acquisition-v1:
2018 P18 volume 1, 2019 P19 volume 1 and main volumes of 2020.acl through 2023.acl,
plus primary-cs.CL arXiv submissions on June 15 of each year 2018–2023. These
filenames/volume semantics must be checked at the actual pin. Track differences
and the six-day arXiv restriction remain pilot-only amendments awaiting approval.
No collection is silently substituted if a proposed file/volume is absent.

Reproducible enumeration: parse all relevant papers in each pinned XML file,
retain original explicit record IDs and volume scope, reconcile counts, hash
the immutable inventory, and log all screening decisions. For each approved
arXiv day, reconcile all budgeted pages and total/offset/unique-ID counts before
sampling; an exceeded bound means stop, not use a prefix as a complete frame.
Then use the proposed fixed 18-record curation panel and existing seed-0 hash
sampling to seek two verified sources per stratum. If amendments are rejected,
use a separately approved full frame. Provider results never enter selection.

| B stratum | Evidence rule |
|---|---|
| doi_only | Verified source-declared DOI; no arXiv identifier in the frozen verified inventory |
| arxiv_only | Verified arXiv base ID; no DOI in the frozen verified inventory |
| dual | Both identifiers verified, with an explicit authoritative baseline declaration or approved cross-record bridge |

These are inventory classes, not global nonexistence claims. An arXiv-issued DOI
alias counts as a DOI under the current rule. Uniform authoritative inspection
may leave arxiv_only underfilled; two papers per stratum are not guaranteed.
Do not hide aliases or search selectively to fill quotas. If this occurs, approve
either an explicit shortfall or a revised publisher-DOI-role stratification that
retains all aliases for identity matching. The latter is a methodological change,
not a decision made here.

All canonical facts and optional volume/issue values need provenance; pending
source facts remain pending. New cross-identifier/cross-record mappings need two
independent approvals; direct original-source declarations use the baseline
exemption. Possible duplicates are warnings, never automatic merges. Verified
duplicates need a representative and logged exclusion. Translations remain
distinct derivatives by default, with unclear relationships undetermined.

## 5. Concise readiness matrix

| Gate | Implemented functionality | A verified source state | B verified source state |
|---|---|---|---|
| Source authority | Restricted source adapters; source URLs/evidence records | API/RSS accessible; targeted official specification pending | Official repository specified; actual pin/content unverified |
| Date validity | Aware timestamps, raw date preservation, cohort arithmetic | Historical first-public dates unverified; no silent substitution | Canonical year rules supported; actual source facts unverified |
| Frame completeness | Counts, bounded preview/incomplete flags | Complete announcement inventory absent | Complete pinned/day inventories absent; preview is not enumeration |
| Deterministic sampling | Seeded hash selection, reserves, shortfalls | Ready once approved eligible frame exists | Ready once eligible panel/strata exist |
| Duplicate handling | Possible flags; explicit verified duplicate decisions | Mechanism ready; empirical review pending | Mechanism ready; cross-source review pending |
| Identity verification | Authoritative baselines; two-reviewer new mappings; conflict gates | No new identities approved | Bridges/strata/reviewer assignments pending |
| Evidence integrity | Raw bytes, headers, UTC times, budgets, hashes, replay | Version 2 implemented/tested offline; one live capture pending | Implemented; no live ACL capture |
| Request budget | Exclusive attempt directories and bounded plans | One specification request authorized; dataset requests not authorized | No ACL or empirical budget authorized |
| Curator approvals | Decisions/reasons and independent reviewer IDs | Language/category/date/panel review pending | Pin/scope/metadata/strata/duplicate review pending |

## 6. Minimal work before empirical acquisition

Use the already implemented evidence engine for the single authorized request;
do not build more generic evidence infrastructure. Review its saved raw answer
offline. In parallel obtain vetted offline ACL source material, or request a
separate tightly bounded ACL source check once an exact scope is chosen.

The only new software work justified by pilot execution is source-specific
complete-enumeration planning/reconciliation (the current CLI is a preview),
approved selected-ID metadata batching, and explicit date-basis/schema/label
support IF a submission-age amendment is adopted. Keep existing metric formulas,
provider ranking and identifier isolation unchanged. Freeze reviewed source
inventories before deterministic panel selection; incomplete runs stay diagnostic.

Exact remaining blockers: unreturned specification evidence; unapproved A method
choice/date basis; unknown authoritative historical coverage; no authentic ACL
pin; unverified B collection/stratum availability; unapproved pilot-only panels;
incomplete-enumeration execution support; curator assignments; and no empirical
request authorization. The specification request need not be repeated if it is
inconclusive: decide on the amendment or prospective design from the returned
evidence and explicit scientific priorities.

**GO now:** run the one authorized local specification request and review its raw
answer. **NO-GO now:** eight-paper A empirical acquisition under the current
announcement-age protocol, and six-paper B acquisition. The broader conditional
198-request plan remains unapproved. No additional numbered preparation milestone
is required merely to choose a method or supply the ACL revision.

## Executed offline quality and preservation checks

The one-URL EvidenceBudget and its link in the saved official RSS documentation
passed offline preflight. The PowerShell runner passed parser syntax checks and
was not executed. No live output directory was created.

```text
pytest -q -W error --basetemp .pytest-tmp/milestone-3c6
415 passed in 12.35s
ruff check .
All checks passed!
ruff format --check .
97 files already formatted
mypy src tests scripts/source_feasibility_v2.py
Success: no issues found in 56 source files
```

All 32 baseline hashes, five original 3C-2 hashes and five protected 3C-4 source/ZIP
hashes match. The version 2 simulated demonstration verifies against its external
manifest anchor and its two replay files remain byte-identical. No current test
or quality-check failures remain. These checks establish software/retention
readiness; they are not evidence that the unrequested live page answers the
scientific date question or that an authentic ACL pin has been supplied.
