# CiteProbe ? Milestone 1 software and connectivity audit

This is a software/configuration audit, not empirical bibliographic research. No full
benchmark or single-paper live retrieval pilot was run. Two application-level HTTP
request attempts were made: one per provider, without retries or redirects. Neither
received an HTTP response. All end-to-end retrieval observations below are simulated.

## 1. Repository and Git status

HEAD: `30380a7c36a062907ce24172b8439d9bd553b0c8`. The only existing commit is:

`30380a7 feat: implement citation schemas and deterministic mutations`

The four modified tracked files are `.gitignore`, `README.md`, `pyproject.toml`, and
`src/citeprobe/cli.py`. Parts 2?4 code, tests, fixtures and artifacts remain untracked
in this working tree. They are integrated locally but are not reproducible from the
committed Git history alone. See `repository.json` for the status snapshot. No files
were staged or committed during this milestone. Git's inaccessible global ignore
file warning is an execution-account issue; the repository-local ignore file exists.

## 2. End-to-end offline integration

All seven CLI command families passed real argument parsing and execution through
`citeprobe.cli.main`; all seven installed console command help invocations also
returned zero. The flow used existing deterministic synthetic fixture metadata and
HTTPX MockTransport, not live providers:

- `validate`: six-record synthetic fixture and five-record pilot both accepted.
- `mutate`: 30 independent mutations, six explicit volume/issue skips. Repeated seed
  42 produced identical mutation values/IDs after excluding generation time.
- `resolve`: 12 simulated canonical lookups across the two existing providers.
- `resolve-mutations`: 60 simulated mutation lookups.
- `replay`: saved results reproduced byte-for-byte with client construction blocked.
- `evaluate`: 72 simulated records, including empty retrieval, insufficient identity
  evidence and simulated connection failures; API failures remain distinct.
- `report`: Experiment B demonstration, separate simulated/unknown report bundles,
  and an Experiment A demonstration with explicitly constructed publication dates.

All 72 lookup attempts in this integration flow used
mocked HTTP. There were zero live requests in this step. Mutation queries contained
no canonical identifier or internal evaluation-ID hints. Canonical dataset copies,
the real pilot, original saved fixtures, and generated lookup files remained
unchanged. Original/evaluator-recorded and final file hashes are in
`offline-pipeline/audit.json`.

Observed/simulated/unknown origins are not pooled by evaluation or reporting. Reports
cannot relabel artifacts. Default origin is unknown, and empirical eligibility
requires explicit observed labels plus the required provenance. These labels and
verification assertions are still supplied by operators/curators: the software cannot
prove that deliberately or mistakenly mislabeled source data is genuinely observed.
No authenticity guarantee is claimed.

## 3. Quality checks

- Full pytest suite: **271 passed**, with `-W error` (20.64 seconds in the final run).
- Ruff lint: passed.
- Ruff formatting check: passed.
- Default strict mypy: passed (37 source files).
- Extended mypy including audit scripts: passed (40 source files).

The original 268 tests passed before adding three mocked audit-utility regression
checks. Those checks verify request-count limits, exception/credential redaction,
and rejection of an existing diagnostic output before any client is constructed.
They do not consume live requests. Complete command output and exit codes are saved
in `quality-checks.json`; exact software versions and source hashes are also saved.

Tests used a writable, ignored local Matplotlib cache rather than the sandbox's
unwritable global font-cache location. This was an execution setting, not a
production code or metric change.

## 4. Sanitized live connectivity diagnostic

Documented search endpoints: `https://api.openalex.org/works` and
`https://api.crossref.org/works`. Each request asked for one record and only small
identifier/title fields, with an identifying CiteProbe User-Agent, a 10-second HTTPX
timeout (8-second connect timeout), no application/transport retries and no redirects.
No response bodies, auth headers, credentials or private environment values were saved.

| Provider | HTTP status | Exception | Attempt latency | Deep cause |
| --- | --- | --- | --- | --- |
| openalex | None | ConnectError | 86.285 ms | PermissionError; errno 13; Windows error 5 |
| crossref | None | ConnectError | 6.053 ms | PermissionError; errno 13; Windows error 5 |

DNS resolved both provider hosts. OpenAlex returned IPv4/IPv6 address families;
Crossref returned IPv4 addresses. System and HTTPX/certifi CA contexts loaded with
certificate verification and hostname checking enabled. No proxy, proxy-bypass,
custom CA, API-key or contact-email environment variables were configured, and no
OS/environment proxy schemes were discovered.

The minimal HTTPX diagnostic reproduced the failure without provider parsing or
candidate evaluation. Both exception chains contain socket/transport access-denied
errors. This strongly identifies a restriction of this execution context, rather
than a CiteProbe parsing, identity, or missing-citation result. The precise policy
component (sandbox/account restriction versus another local access-control layer)
is not independently identified. It is not evidence that either provider is down.

No usable HTTP response was received, so provider authentication acceptance, actual
TLS negotiation, and successful live API parsing remain unverified. ConnectError is
not automatically attributed to missing credentials. This diagnostic used the basic
public-access configuration documented in the repository's README and official
references linked there. Those pages were not fetched again, to avoid additional
provider requests. If an eventual authorized local attempt returns 401/403, investigate
current authentication/authorization requirements; 429 indicates rate limiting;
404 means the server was reached but the requested resource was not found.

## 5. Defects, limitations and changes

No new production integration defect was reproduced, and no Parts 1?4 production
implementation or metric definition was changed during this milestone.

Changes are audit-only: two explicitly invoked utilities in `scripts/`, their package
marker, three mocked regression tests, and these audit artifacts. The diagnostic
utility now explicitly disables environment inheritance on both its client and its
transport. The actual diagnostic ran with all relevant environment variables absent;
this hardening does not change its evidence, and no live request was repeated.

Known gaps and assumptions:

- Parts 2?4 remain outside committed Git history. Preserve the tested state before
  empirical work.
- Dependencies have bounded ranges, not a locked research environment. Versions are
  recorded here, but a fresh installation can differ.
- The resolver intentionally sets `trust_env=False` and has no CLI proxy/custom-CA
  configuration. This is a documented portability limitation on proxy-dependent or
  enterprise-CA networks; no such configuration was found here, so it does not explain
  away the observed OS permission denial.
- No `py.typed` marker is shipped. Local strict type checks pass; external installed
  consumers do not automatically receive the package's typing declarations.
- Origin/provenance assertions, representative sampling and independence of canonical
  source-paper IDs still require researcher judgment. Passing software tests is not
  proof of empirical validity or provider coverage.

## 6. Recommended next steps

1. Review and commit the integrated code/tests and suitable explicitly labeled
   fixtures/artifacts; create an identifiable research-software revision/tag.
2. Preserve an exact dependency environment using the recorded versions, avoiding
   credential-bearing installation URLs in any shared lock/export.
3. After separate authorization, run the bounded diagnostic from a network-enabled
   local terminal under the ordinary user account, from this repository root:

   ```powershell
   .\.venv\Scripts\python scripts/connectivity_diagnostic.py --allow-live --output artifacts/milestone-1-local-connectivity.json
   ```

   Use a new output path; the utility refuses overwrite before issuing requests.
   Do not run extra diagnostics from this restricted session: its two authorized
   live attempts are already exhausted. Do not disable TLS verification.
4. If the local network requires a proxy or custom CA, establish that requirement
   explicitly and plan a tested configuration change rather than silently enabling
   environment inheritance or attributing failures to credentials.
5. Review the local diagnostic result, then request approval for the single-paper
   live pilot. Do not begin full empirical collection from this audit.

Milestone 1 stops here. No empirical retrieval-performance findings are claimed.
