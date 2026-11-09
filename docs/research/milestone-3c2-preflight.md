# Milestone 3C-2: local execution handoff

The user authorized one arXiv API request returning at most five candidates.
This sandbox is network-restricted. No HTTP request, DNS probe, remote documentation
fetch or attempt to bypass that restriction was made during this preflight.
Actual HTTP status, returned records and live parsing remain pending local results.

Run once in your ordinary Windows PowerShell terminal:

```powershell
Set-Location C:\Users\netha\yc\CiteTrace
.\scripts\run_milestone3c2.ps1
```

The script prepares the existing CLI plan offline using the local execution's
current UTC date R, then executes the authorized single request. There is no
additional confirmation requirement: this handoff uses the explicit Milestone
3C-2 authorization. The plan is hashed before execution and preserved.

Checked request specification:

```text
GET https://export.arxiv.org/api/query
search_query = cat:cs.CL AND submittedDate:[(R-60 days)0000 TO R2359]
start = 0
max_results = 5
sortBy = submittedDate
sortOrder = ascending
```

The range matches the documented bounded discovery slice, not a complete
public-announcement sampling frame. Primary category/language require review.
Submission timestamps cannot establish first-public dates or cohort membership.
No canonical, mutation, OpenAlex, Crossref, secondary or pagination requests run.

The inspected CLI has HTTPX transport retries=0, follow_redirects=False,
trust_env=False, timeout=20 seconds, a single pooled connection and User-Agent
`CiteProbe/0.1 bounded-discovery-pilot`. It has one client.stream GET call.
The wrapper refuses to start if artifacts/milestone-3c2 already exists and
refuses overwriting any output. Preserve partial errors; do not rerun the script
for a failed/empty/partial response. No production implementation changes were
required for this handoff.

Return all of artifacts/milestone-3c2, including:

- plan-001.json: original approved-scope plan and its actual UTC reference date.
- run-001/plan.json: preserved execution plan.
- run-001/response.json: observed request, HTTP status/error, actual collection
  timestamps, raw response hash and sanitized metadata projection/hash.
- run-001/audit.json: parsed pending candidates, source IDs, author/year/submission
  metadata and duplicate/conflict/incomplete-enumeration review flags.
- run-001/replay-check.json: offline replay, checked byte-identical by the script.

The wrapper checks the canonical pilot dataset hash before/after. Existing frozen
datasets are never inputs to these commands. Saved origin is observed for the
real acquisition; candidates remain pending. Only a single compatibility test is
authorized. Full dataset acquisition remains NO-GO pending inspection of actual
results, source-frame completeness/date evidence, curator review and new approval.

Local preparation checks: PowerShell parser syntax passed; source request model
and five-record/single-request/zero-offset assertions passed without constructing
an HTTP client. The live wrapper was not executed in the sandbox.
