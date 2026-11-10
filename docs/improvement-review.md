# CiteProbe comprehensive local improvement review

Status: **implemented locally; awaiting release approval**. Nothing in this pass
was staged, committed, pushed or deployed. No experiment was rerun and no provider
API request, identity study, license, repository-visibility or Vercel setting change
was made. Production remains the prior approved release.

## Executive assessment

The prototype now introduces its research contribution directly: CiteProbe makes
the difference between retrieving a scholarly record and verifying its identity
inspectable. It consistently describes the public study as an exploratory
citation-retrieval pilot, not a validated accuracy benchmark.

The public record is unchanged: eight selected source papers, sixteen searches,
41 candidate entries, all UNDETERMINED. The improvement adds sanitized search
provenance and a standalone offline verifier, alongside a clearer frontend.

## Before and after

| Area | Before | Local implementation |
| --- | --- | --- |
| Positioning | Research question and strong headline; important qualifications deeper in the page | Headline preserved; contribution, measured scope and unresolved identities explicit in the hero |
| Findings | Large return counts with comparative progress bars | Neutral equal-treatment cards; separate return counts, identity evidence and evidence bounds; direct definitions and limitations |
| Explore | Title plus provider status; source and candidates shared similar hierarchy | Source-record panel, source link/authors, provider-level search headings, candidate-level titles/identifiers, accessible descriptions and request-manifest download |
| Reproducibility | Data download and brief methods link | Inspect/recalculate/replay boundaries, exact sanitized request manifest, three explained downloads and standalone verifier |
| Methodology | Five broad paragraphs | Ten navigable sections covering question, sample, searches, access, extraction, identity, bounds, provenance, limits and future work |
| Responsiveness | Readable fixed-pixel labels and basic focus checks | Rem-based sizing, explicit 200% text-scaling tests, visible wrapping navigation, CSS arrow icons, tested modal focus and skip links |
| Error handling | Separate loading/error states with shallow schema checks | Nested candidate/metric validation, frozen-inventory checks, bounded fetch timeout, preserved distinct loading/error/empty states |

These are verified implementation/browser observations. No timed comprehension
study or external usability study was conducted; “understandable within 30 seconds”
remains a design objective, not a measured research finding.

## Reproducibility package and evidence

The new `public-demo/experiment-manifest.json` describes all sixteen evaluated
searches, sourced from the successful smoke capture and seven two-provider
continuation captures. `scripts/export_experiment_manifest.py` validates frozen
dataset/evaluation checksums, pinned capture-inventory anchors, capture/body hashes
and the lookup-to-evaluation correspondence before exporting allowlisted fields.
The Pydantic schema is `src/citeprobe/public_manifest.py`.

The manifest contains exact decoded non-secret request values, endpoints, methods,
capture start/finish times, recorded server Date headers, HTTP status, access mode,
limit, provider ranks, engine version and logical artifact URNs/checksums. It does
not expose private paths, authentication values, header dumps or raw responses.
OpenAlex access is one anonymous and seven keyed searches; Crossref is eight
anonymous searches. Modes are supported by the recorded plan and transport code,
not independently reauthenticated request headers.

Missing provenance is explicit: historical execution revision, exact response-header
arrival times and provider ranking internals are `not_recorded`. The separately
identified adapter revision is the code inspected for this manifest, not a claim
about the historical checkout. Some remote server Date headers appear after local
capture finish: the values are preserved as different clocks, not silently repaired
or used for latency conclusions.

`public-demo/verify.py` uses only Python's standard library. With the two JSON
downloads it checks the data checksum, source/search inventory, frozen identifiers,
candidate ranks, outcomes, access counts and judgments, then recalculates return
counts, candidate counts and identity-evidence-bound counts. It makes no HTTP
requests. Public consistency is not independent capture authenticity or identity
verification. New API queries are future replication attempts, not historical replay.

## Scientific-claim audit

| Claim | Evidence/check | Interpretation |
| --- | --- | --- |
| 8 sources, 16 searches, 41 entries | Frozen dataset/evaluation, unchanged public data, manifest inventory and offline verifier | Entries contain 40 distinct DOI values; entries are not necessarily unique papers |
| OpenAlex 1/8 and Crossref 8/8 returned candidates | Recorded successful lookup outcomes and independent public calculation | Search return counts only, not accuracy scores or provider superiority |
| All 41 identities unresolved | Every frozen/public candidate judgment is UNDETERMINED | None is confirmed correct or confirmed incorrect |
| Recall@5 bounds 0–1 / 8 and 0–8 / 8 | Confirmed-hit counts plus unresolved-search counts, denominator eight per provider | Identity-evidence bounds, not confidence intervals |
| Source-verified papers | Curator provenance and frozen records | Not a claim of peer review, independent source authentication or candidate matching |
| Unequal access conditions | Saved capture records, pinned continuation plan and credential-injecting transport | Confounded with paper identity; direct comparability is limited |
| No-candidate searches | Seven recorded empty OpenAlex queries | No claim of provider database absence |
| Historical provenance | Recorded times/parameters/hashes with explicit missing fields | Not full public replay, indexing latency or known provider ranking internals |

No claim is made about AI-text detection, another product's performance, a measured
incorrect-match rate or demonstrated mutation robustness. Technical capabilities
elsewhere in the repository are distinguished from findings of this public pilot.

## Validation results

- Full automated suite with Chrome enabled: **590 passed** in 222.61 seconds.
- After adding explicit Findings assertions/screenshots, the affected browser suite
  was rerun: **4 passed** in 5.72 seconds. These are the same four cases, not four
  additional independent experiments.
- Exact Chrome CSS viewports/PNG dimensions: **320x900, 390x900, 768x900, 1440x900**,
  device scale factor 1. All checks served the working tree from local loopback.
- Actual Chrome downloads of data, manifest and verifier matched served bytes.
  The downloaded verifier ran in isolated Python and reproduced expected counts.
- Browser checks covered native Tab/Enter navigation, focus indicators, skip link,
  initial modal focus, Escape/close/focus restoration, all papers/candidate ranks,
  filters, method sections, source/candidate hierarchy, headings/landmarks, data
  loading/error states, Findings values, tested text contrast, 200% text sizing,
  viewport/dialog overflow and JavaScript console/runtime errors.
- Existing HTTP-failure tests remain mocked, including network/timeout, HTTP 404,
  429 and 500, malformed JSON/data and invalid nested candidate/metric records.
- Ruff check/format passed for `src`, `tests`, both exporters and public verifier
  (96 formatted files). Mypy passed for 90 source files with these roots explicitly
  included. JavaScript syntax and Git whitespace checks passed.
- Public data and **522 original artifact files** matched their recorded byte
  hashes. Frozen scientific payload, identifiers, ranks, judgments, counts, evidence
  bounds and source files are unchanged.

Commands and reproduction instructions are in `docs/public-demo.md`. Full-suite
screenshots/downloads are under ignored `.pytest-tmp-improvement-full/`; the final
browser rerun's screenshots and per-width JSON reports are under ignored
`.pytest-tmp-improvement-browser/`. Screenshots include home, Findings, Explore,
dialog, methodology and 200% text-sizing views. These are **local results**, not a
claim that production already contains these changes.

Accessibility verification covers relevant automated/keyboard criteria, not a full
WCAG certification or an assistive-technology user study. Safari and physical mobile
devices were not tested. New production download URLs and hosting behavior must be
checked after a separately approved deployment.

## Privacy and security

Only seven assets are intended for deployment: the original five plus the manifest
and standalone verifier. Tests enforce that inventory; no cache, log, private
capture, internal artifact or archive is included. Text is rendered through DOM
text properties, source IDs/records are validated, and external source links use
fixed HTTPS hosts and safe new-tab relationships.

Pattern scans found no credential assignments, common token/private-key patterns,
email addresses or private filesystem paths in those assets. Exact and URL-encoded
forms of the local OpenAlex key had no matches. No external fonts, analytics or
new application dependencies were added. Scholarly names and citation metadata
remain intentional public content. Scans do not establish complete legal/privacy
safety, audit every possible secret encoding, or replace owner publication review.

## Exact local file scope

Modified tracked files:
- `README.md`
- `docs/public-demo.md`
- `public-demo/app.js`
- `public-demo/index.html`
- `public-demo/methodology.html`
- `public-demo/style.css`
- `pyproject.toml`
- `tests/public_demo_browser.cjs`
- `tests/test_public_demo.py`
- `tests/test_public_demo_browser.py`

New proposed files:
- `docs/improvement-review.md` (this report)
- `public-demo/experiment-manifest.json`
- `public-demo/verify.py`
- `scripts/export_experiment_manifest.py`
- `src/citeprobe/public_manifest.py`
- `tests/test_public_manifest.py`

`public-demo/data.json` is deliberately not modified. Existing untracked research
artifacts, archives and earlier review records remain excluded from this scope.

## Recommendation and outstanding limits

**GO for owner review of this local improvement set and eventual sharing as an
exploratory research prototype. NO-GO for claiming the changes are released or for
presenting the pilot as a validated accuracy benchmark.** No local technical blocker
remains in the tested scope. Commit/push/deployment and publication of the newly
sanitized request metadata require the owner's release approval.

Scientific limits remain: selected eight-paper sample, uneven access, 41 unresolved
identities, private captures, unrecorded historical checkout/header timing/ranking
internals, and no population-level or indexing-latency inference. Future work can
include an independently reviewed identity study, matched access, a prespecified
broader sample, repeated observations or a separate mutation study. None is merged
into this frozen pilot or presented as an accomplishment already completed.
