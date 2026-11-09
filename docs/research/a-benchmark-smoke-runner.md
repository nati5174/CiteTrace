# Experiment A bounded smoke runner

Opt-in module: `python -m citeprobe.benchmark_smoke`. Existing resolver commands and research definitions are unchanged. No requests were made during implementation.

The runner verifies the approved frozen anchor and dataset hash, selects the first canonical task in frozen order (2611.07721), and uses only title, complete authors and year. It calls the existing OpenAlex and Crossref request builders/parsers through the existing Resolver, one provider at a time. It enforces the exact two-URL inventory at the transport boundary, one attempt per provider, no redirects, no automatic retries, and no cookie hints. Authentication uses existing environment-variable support in memory; request headers are never saved. No credentials are required or assumed to be present by this runner; provider rejection stops the run.

Raw response payload bytes before content decoding are saved as `attempt-NNN/body.bin`. These are HTTP body bytes, not TLS packets or HTTP transfer framing. Safe response headers, status, UTC start/end, hash, size, completeness and exception class are retained. Partial bodies and non-JSON errors remain evidence. A 10 MB raw capture ceiling stops and marks oversized captures incomplete; it never labels the retained prefix a complete body. Unexpected local errors also stop without another request.

Each attempted provider yields its ordinary lookup bundle where possible, compatible with existing offline evaluation. `plan.json` identifies the selected source, metadata, URLs and origin; it is evaluation provenance and is not sent to providers. `receipt.json` records actual attempts and the stopping condition. `integrity.json` hashes the evidence inventory. Keep its SHA-256 outside the directory to detect replacement of both evidence and manifest. Offline verification checks hashes and reproduces provider candidates and ranks from raw responses. It does not infer identity from metadata similarity.

## Local execution

From `C:\Users\netha\yc\CiteTrace`, run exactly once:

```powershell
.\scripts\run_a_benchmark_smoke.ps1
```

Output: `artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-001/`.
Return the entire directory after success or failure. Do not rerun a failed or partial stage. The runner refuses an existing directory; deleting/renaming evidence to repeat requests is not authorized. The sandbox must not execute this script.

Offline verification can be repeated without HTTP:

```powershell
.\.venv\Scripts\python.exe -m citeprobe.benchmark_smoke --verify artifacts/empirical-pilot-immediate-001/a-benchmark-smoke-001
```

After inspecting actual results, evaluate with the frozen dataset and `identity-mappings.json` using the existing evaluator and an explicit observed label. Provider failures remain operational errors. A failed first provider means the second was not attempted, not a retrieval miss. No empirical metrics are claimed until actual captures are reviewed. This smoke budget covers two requests only; it does not authorize the remaining fourteen requests for seven papers.
