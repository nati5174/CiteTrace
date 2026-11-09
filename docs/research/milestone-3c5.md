# Milestone 3C-5: evidence extraction hardening

Implemented offline only. No HTTP requests, empirical acquisition, provider
benchmarks, protocol amendments or historical-artifact rewrites occurred.

## Version 2 raw evidence

New contracts live in evidence_models.py. EvidenceBudget binds an explicit
authorization reference, origin, maximum attempt count and exact GET inventory.
RawEvidence binds the budget fingerprint, request identity/ordinal, fixed public
request headers, UTC request/header-receipt/completion times, HTTP status/final
URL, allowlisted response headers, content type/encoding/charset, raw byte count
and SHA-256, completeness flag and extraction version. Each request is stored as:

```text
budget.json
request-001/
    body.bin
    record.json
    extracted.json
manifest.json
```

Multiple approved requests use additional numbered directories. A directory is
reserved before an attempt, so it cannot be silently overwritten/retried. The
manifest hashes the budget and all body/record/extraction files and reports
actual attempt count, planned count and whether the plan completed. Unattempted
requests after a connection failure are not presented as completed requests.

body.bin contains the exact HTTPX iter_raw/aiter_raw entity-body bytes, before
Content-Encoding decompression. HTTP transfer framing, TLS traffic and private
headers are not retained. Thus gzip-encoded bytes can be independently rehashed;
decoded text is not misrepresented as the original encoded body.

Capture and decoding each have a two-megabyte bound. On a timeout, stream error,
length mismatch or size limit, preserve only bytes actually captured, mark the
body incomplete and extraction unavailable. A retained-prefix hash is explicitly
NOT a hash of an unavailable complete response. Complete transport bytes can
still contain malformed/truncated compressed content; that remains an extraction
failure, with the exact raw bytes retained.

Requests disable inherited client auth and do not copy client cookies or private
headers. Credential-bearing URLs are rejected. Response headers are restricted
to content-type, content-encoding, content-length, date, etag, last-modified and
retry-after; Set-Cookie, Authorization and arbitrary headers are excluded.
The future source runner restricts destinations to documented public arXiv URLs.
Raw content is retained without redaction because changing bytes would invalidate
exact evidence. These tools are for public, unauthenticated source material, not
authenticated/private responses; keep raw files access-controlled and review
before sharing. Public source text is not automatically a scholarly fact.

Missing charset remains null in HTTP metadata. Extraction uses an explicitly
declared charset when present, otherwise a strict UTF-8/BOM default; unsupported
or malformed encodings produce unavailable extraction, not invented statements.
HTTP content decoding supports identity, gzip and deflate with bounded output.

## Source-specific extraction

evidence_extract.py prefers main/article content and excludes navigation,
sidebars, tables of contents, scripts and styles. It retains relevant paragraphs,
lists and tables with section titles, anchor URLs, DOM paths and source lines.
Statements are normalized source text, not generated scientific conclusions.
Relevant specification/history links are retained with context but never followed.

API documentation selection covers publication/submission definitions, query
parameters/pagination, versions and updates. RSS/Atom documentation selection
covers update schedules, retention/coverage, announcements, categories and date
semantics. Count/text bounds are disclosed; full raw bytes preserve material the
extractor omitted. No matching statements is explicitly an extraction limitation,
not proof the documentation lacks an answer.

Atom extraction preserves root metadata (including updated/subtitle/status),
entry count and explicit empty-feed status, entry IDs/titles, raw published and
updated values, valid aware timestamps normalized to UTC, category attributes,
primary categories and explicitly supplied announcement types. Namespace-expanded
tags and XML paths locate each field. Missing fields stay missing; malformed or
timezone-free timestamps retain their original text with null normalized values
and warnings. No first-public-announcement date is inferred from published,
updated, collection time or an empty feed.

## Integration and compatibility

Future acquisition-run calls now save an http-evidence companion bundle alongside
the existing plan/response/audit files. AcquisitionResponse and historical audit
schemas are unchanged; existing offline acquisition/evaluation replay remains
compatible. The legacy projection-only collect helper remains for compatibility;
the live CLI path uses raw capture. No resolver/scoring changes were made.

scripts/source_feasibility_v2.py is a new, separately gated runner requiring a
new explicit authorization reference, exact approved plan hash and fresh output
directory. It uses no retries/redirects and at most three public-source requests.
It was NOT run against any live endpoint. Old source_feasibility.py and its local
wrapper remain untouched so the historical 3C-4 manifest's script hash still
matches. Do not reuse that exhausted authorization for version 2 captures.

Old projections have no body.bin and cannot be upgraded by reserializing their
metadata. evidence-verify rejects legacy formats rather than fabricating raw
bodies. No raw bytes were retroactively attached to protected historical evidence.

## Offline verification and reproducibility

evidence_io.py verifies manifest/file inventories, hashes and raw sizes, request
identities and authorization ordinals, origins, record fingerprints, UTC chronology,
final URLs, response-header consistency and extraction version/source references.
It re-extracts from retained raw bytes and requires semantic equality and canonical
byte-identical extraction serialization. Changed locators or statements fail even
if someone recomputes a file's manifest hash without changing the underlying raw
source consistently.

Checksums are not signatures. Retain the manifest's SHA-256 externally to detect
coordinated replacement of an entire bundle; internal hashes alone cannot
authenticate a maliciously replaced source history. Origin and human authorization
remain recorded assertions, not independent transport attestations.

An explicitly simulated four-source demonstration, created using MockTransport
only, is available under artifacts/milestone-3c5-offline/evidence-demo. It contains
raw synthetic API/RSS HTML and empty/nonempty Atom fixtures. No actual source was
contacted. Verify and replay locally without network access:

```powershell
citeprobe evidence-verify artifacts/milestone-3c5-offline/evidence-demo
citeprobe evidence-verify artifacts/milestone-3c5-offline/evidence-demo --replay-output replay.json
```

The optional --manifest-sha256 argument supplies an externally retained anchor.
Replay outputs must be new and outside the bundle. Two saved demonstration
replays are byte-identical. Request bodies can also be rehashed independently
with Get-FileHash or sha256sum and compared with record.json.

## Remaining limitations and next verification proposal

HTML structure can change; section/paragraph selection is bounded and heuristic.
An EXTRACTED result is not a curator approval or proof of date semantics. Raw bytes
permit audit/re-extraction instead of silent loss. A new extraction algorithm
must use a new version and outputs, not overwrite old bundles. XML namespace
warnings and unknown timestamps must be resolved by source review. No historical
60-day source or ACL revision has been verified by this offline milestone.

Propose a minimal next source-verification stage of ONE request, only after fresh
authorization: GET https://info.arxiv.org/help/atom_specifications.html. This URL
was already observed in the saved official documentation link list. Use version 2
raw capture, an identifying User-Agent, 20-second timeout, zero retries,
redirects/pagination/secondary fetches disabled, two-megabyte bounds and a new
versioned directory. Inspect explicit published/updated/announcement definitions
and any historical coverage statements. A link to another page is a lead, not
permission for a second request. An inconclusive response means stop and report.

This proposal does not authorize that request. It does not repeat all three
3C-4 requests, authorize frame enumeration or assume a 60-day archive exists.
ACL verification still needs a separately approved concrete revision and exact
collection URL. No policy exception or sampling amendment is adopted here.

**Experiment A: NO-GO** until authoritative announcement semantics and historical
frame completeness are established, or an explicit protocol amendment is approved.
**Experiment B: NO-GO** until ACL pin/source scope, complete enumeration, reviewed
identity strata and acquisition budget gates are satisfied. The technical evidence
hardening itself is ready for review and a separately authorized targeted test.

## Executed offline checks

Final results after source changes:

```text
python -m pytest -q -W error --basetemp .pytest-tmp/milestone-3c5
415 passed in 12.26s
python -m ruff check .
All checks passed!
python -m ruff format --check .
94 files already formatted
python -m mypy src tests scripts/source_feasibility_v2.py
Success: no issues found in 56 source files
```

There are 36 new regression cases covering navigation-heavy documentation,
section provenance, empty/nonempty feeds, namespaces, malformed/missing timestamps,
unexpected content types, declared charsets, raw gzip bytes, truncated streams and
compression, response limits, secret-header omission, budget limits, async capture,
source/manifest tampering, legacy rejection and byte-identical replay. MockTransport
was used for every HTTP-shaped test and demonstration; no live request occurred.

All 32 baseline hashes, five original 3C-2 hashes and five 3C-4 ZIP/source hashes
match. The original feasibility script and research-plan hashes also still match
the historical manifest. Current demonstration verification and replay passed.
No failing tests or quality checks remain. Development checks caught and corrected
typing issues and malformed-manifest/truncated-compression handling before these
final results. No historical result was reclassified.
