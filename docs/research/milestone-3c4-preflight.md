# Milestone 3C-4: authorized source feasibility, local handoff

State: prepared, not executed. The sandbox is network-restricted. No live request
or network-bypass attempt was made. Actual HTTP statuses and evidence findings
must await the local batch artifacts. The user's authorization is at most three
requests for source feasibility only, not the conditional 198-request budget.

## Fixed URL preflight

| Request | Exact URL | Purpose and expected evidence |
|---:|---|---|
| 1 | https://info.arxiv.org/help/api/user-manual.html | Official API field/date semantics; distinguish submission metadata from public announcement evidence |
| 2 | https://info.arxiv.org/help/rss.html | Official feed/announcement semantics, date meanings and any documented historical-retention mechanism |
| 3 | https://rss.arxiv.org/atom/cs.CL | Feed format, available date/announcement-type field names and bounded date examples; not historical completeness proof |

All three are explicitly listed in pilot-acquisition-v1.md. They can be justified
against that approved request scope without contacting another source. Current
availability/redirect behavior cannot be confirmed before using the authorized
requests; HTTP 200 alone will not certify research feasibility.

No ACL request is included: the three documented feasibility slots are arXiv,
and no actual ACL commit has been approved. The plan's ACL endpoint contains an
unresolved revision parameter. A pinned-revision feasibility check cannot honestly
be reported as complete from these requests. Do not substitute a fourth request,
a moving branch URL or an invented commit.

## Run once locally

```powershell
Set-Location C:\Users\netha\yc\CiteTrace
.\scripts\run_milestone3c4.ps1
```

No extra authorization is needed for these three fixed URLs; this uses the user's
explicit Milestone 3C-4 approval. The runner requires an execution flag internally,
refuses an existing output directory, creates its manifest before requests, and
uses HTTPX with transport retries=0, follow_redirects=False, trust_env=False,
TLS verification, 20-second timeouts and User-Agent
`CiteProbe/0.1 source-feasibility`. There is one GET site within a fixed three-URL
loop. No pagination, linked-record fetches, credentials or browser automation.
Requests are serial, separated by three seconds. Connection failure stops the
remaining batch. Redirects/errors are recorded without retry or replacement.
Decoded response size is bounded at two megabytes; oversize evidence stays
inaccessible rather than silently raising the cap.

Return all files under artifacts/milestone-3c4: manifest.json and up to three
01-source.json, 02-source.json, 03-source.json records. A stopped batch may have
fewer records. Return partial files and the terminal error; never rerun to fill
missing evidence without a new explicit budget. Do not upload credentials.

Records contain fixed sanitized URLs, actual collection UTC timestamps, HTTP
status/exception type, latency, raw-body hash and bounded evidence with its hash.
The manifest binds script and plan hashes and records request limits. Documentation
excerpts may omit qualifications; feed summaries intentionally retain no paper
identifiers/titles/authors. Original body hashes cannot independently be recomputed
from these evidence projections. No full webpages or PDFs are archived. No response
is automatically classified as proving first-public dates or historical coverage.

## Review and stop criteria

After results return, inspect whether the official sources explicitly define a
first-public announcement event, whether dates refer to submission versus feed
generation/updates, and whether a complete historical new-announcement inventory
for the proposed 60-day interval is accessible. A current feed sample is not that
inventory. An archive link is only a lead; it must not be fetched under this batch.
Missing, inaccessible or ambiguous evidence yields unresolved/NO-GO, not a guessed
release lag or silently changed date policy.

Both empirical pilots remain NO-GO pending evidence review and their separate
gates. A additionally needs historical endpoint/date semantics and complete-frame
enumeration. B needs an actual approved ACL revision/inventory, complete-frame
handling, and verified identifier strata/bridges. Provider-independent sampling
and existing review rules are structurally supported, but feasibility of real
source coverage has not been established by this preparation.

Potential subsequent work is limited to source adapters/complete enumeration and
audit counters after endpoint semantics are verified, not metric changes. If
first-public evidence is unavailable, a prospective announcement-capture design
or an explicitly renamed submission-age study would require a new policy approval.
Neither amendment is made here. No canonical dataset, frozen snapshot or earlier
evidence is edited by these scripts.
