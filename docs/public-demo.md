# CiteProbe public prototype: data, provenance and release checks

CiteProbe is an **exploratory citation-retrieval pilot**, not a validated accuracy
benchmark. It makes the difference between retrieving a scholarly record and
verifying its identity inspectable. The homepage uses the Pilot Atlas to navigate
the frozen searches; individual paper inspections use the Review Register
workbench.

## Frozen scientific scope

The public pilot has eight selected arXiv source papers, two per submission-age
cohort, sixteen evaluated searches and 41 candidate entries (40 distinct DOI
values). OpenAlex returned candidates for one of eight queries; Crossref for eight
of eight. These are return counts, not accuracy scores. All 41 judgments remain
UNDETERMINED: none is confirmed correct or confirmed incorrect.

One OpenAlex search was anonymous, seven used an API key, and all eight Crossref
searches were anonymous. The access-condition change is confounded with paper
identity. The selected cs.CL sample cannot support population-level conclusions;
this cross-sectional pilot cannot estimate indexing latency. Recall@5 bounds are
identity-evidence bounds, not confidence intervals. A zero-result search does not
establish database absence. The pilot does not measure AI-text detection or product
performance, and does not establish mutation robustness.

`public-demo/data.json` remains byte-identical to the prior approved export.
Canonical identities, provider ranks, candidate metadata, judgments, explanations,
counts, evidence bounds, evaluation ID and dataset checksum are preserved. Its
`owner_approved` metadata labels the frozen export. The UI release was explicitly
approved by the project owner on 10 November 2026; neither approval independently
certifies the research or verifies any candidate identity.

## Public static assets

Only `public-demo/` is intended for site publication:

| File | Purpose |
| --- | --- |
| `index.html` | Pilot question, observations, limitations and source/candidate exploration |
| `methodology.html` | Ten sections separating recorded observations, identity evidence, limits and future work |
| `style.css`, `refine.css`, `integrated.css` | Review Register system and responsive Pilot Atlas/workbench composition |
| `app.js`, `integrated.js` | Schema checks, safe rendering, Atlas navigation, evidence path and rank jumps |
| `data.json` | Unchanged source metadata and frozen candidate/evaluation projection |
| `experiment-manifest.json` | Sanitized historical request metadata and explicit provenance gaps |
| `verify.py` | Standalone standard-library verifier for downloaded public artifacts |
| `fonts/` | Local IBM Plex Sans/Mono WOFF fonts and their SIL Open Font License notices |

## Evidence-workbench navigation

The approved Pilot Atlas and Review Register interface uses graphite source context, white ranked
records, steel-blue interactions and explicitly labeled copper identity annotations.
The homepage specimen is one real frozen record, not a representative finding.
Findings places return counts, identity-evidence bounds and recorded access together.

Open `index.html#paper=2611.07721` to inspect a paper directly. Append
`&provider=openalex` or `&provider=crossref` to select a provider. Without a provider,
the first provider with candidates is selected; controls retain OpenAlex/Crossref
order. Within each search, candidate ranking is unchanged. Empty searches remain
inspectable and do not establish absence from a provider's database.

Paper links and Previous/Next add browser-history entries. Provider selection
replaces the current paper entry, avoiding a Back step for every toggle. Browser
Back/Forward restores the paper route, and return to the overview restores focus
to its source link when visible. Cohort state is retained within the page session;
it is not encoded in shared URLs. Copy link has a manual address-bar fallback.

The homepage Atlas maps all eight sources and sixteen provider searches to their
recorded ranks. On narrow screens, two sources display at a time with keyboard
operable previous/next controls. Source and provider cells link directly to the
matching inspection route. The above-map note clarifies that rank counts are not
verified identity or accuracy, while recorded access conditions are stated below.

Desktop keeps source context beside candidates; mobile uses a compact source
reference and expandable provenance. The four-stage evidence path explains
source, provider query, ranked returns, and unresolved identity in the inspection.
Both provider names are included in source
links' accessible names at every breakpoint. The mobile matrix retains explicit
table/row/header roles while reflowing into labeled summaries. Enlarged-text,
keyboard, provider-association and history regressions run in real Chromium.
These checks do not certify complete screen-reader or touch-device accessibility.

Both public JSON files must validate before evidence is displayed. Loading errors
hide unavailable observations and expose an alert with recovery guidance. No
provider requests occur in the browser. Fonts are served locally, with no external
font-service requests. Implementation links point to the repository's origin URL.

Do not upload repository roots, internal artifacts, raw responses, `.env`, logs,
archives, browser profiles or pytest directories. The manifest exporter uses field
allowlists; it does not serialize capture records wholesale. Scholarly author names
and citation metadata are intentionally public. Scans cannot establish universal
privacy/legal clearance or detect every possible secret encoding.

## Manifest provenance and reproducibility

`scripts/export_experiment_manifest.py` reads existing files offline. It validates
the frozen dataset/evaluation anchors and both capture-inventory anchors, compares
saved lookup candidates with the frozen evaluation, and checks raw-body hashes
without copying bodies into the export. It never issues provider requests.

The selected sources are the two successful smoke lookups and the fourteen
successful key-continuation lookups. Earlier 429 attempts are explicitly excluded.
Each manifest search includes the source-paper ID, provider endpoint, exact decoded
non-secret parameters, capture start/finish, recorded server Date header, access
mode, HTTP status, retrieval limit, preserved ranks, lookup-engine version and URN
artifact references with SHA-256 digests. No absolute private paths, credentials,
request/response header dumps or raw responses are exported.

Authentication modes are supported by the saved continuation plan and the transport
that adds the OpenAlex key after key-free capture metadata is recorded. This is
retained provenance, not independent authentication of a historical request.

The historical Git checkout, precise response-header arrival time and provider-side
ranking algorithm are `not_recorded`. Request headers are not recorded publicly.
The manifest identifies the inspected adapter revision and LF-normalized code
hashes separately from the historical execution. The builder source hash records
the local builder implementation. The adapter revision is pinned, so merely making
a future release commit does not rewrite historical provenance.

Capture finish is after body capture. Server Date is a remote clock; apparent
differences from local capture times are retained. Do not treat these clocks as
precise event ordering or derive indexing latency from them.

Regenerate **only the sanitized manifest**, with the existing private evidence
available in its original workspace locations:

```powershell
.\.venv\Scripts\python -m scripts.export_experiment_manifest
```

This is not an experiment rerun. If a frozen checksum fails, stop and investigate;
do not regenerate or alter frozen inputs to make the export pass. Public schemas
are defined in `src/citeprobe/public_manifest.py`. Export/tests require the private
evidence workspace; a clean public clone can still run the standalone verifier.

With the three downloads in one folder:

```powershell
python verify.py data.json experiment-manifest.json
```

Python 3.12+ is sufficient; there are no third-party dependencies or HTTP requests.
The verifier checks the LF-normalized data checksum, frozen identifiers, source/
search inventory, original ranks, outcomes, access counts and identity judgments.
It calculates provider return counts, candidate counts and the published evidence
bounds from the unchanged public fields. Consistency is not independent capture
authenticity or candidate identity verification.

Raw responses are not public. A new API request is a replication attempt under
potentially changed conditions, not replay of frozen historical behavior. The
public package cannot reproduce undocumented provider-side ranking or perform the
identity-verification study that has not been done.

## Local preview and tests

```powershell
.\.venv\Scripts\python -m http.server 4173 --directory public-demo --bind 127.0.0.1
```

Use HTTP, not `file://`. Browser checks serve the same static root from loopback;
no provider API calls are made. With Chrome installed, run:

```powershell
$env:CITEPROBE_BROWSER = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
.\.venv\Scripts\python -m pytest -q --basetemp=.pytest-tmp-improvement-full -o cache_dir=.pytest-tmp-improvement-full-cache
.\.venv\Scripts\python -m ruff check src tests scripts/export_public_demo.py scripts/export_experiment_manifest.py public-demo/verify.py
.\.venv\Scripts\python -m ruff format --check src tests scripts/export_public_demo.py scripts/export_experiment_manifest.py public-demo/verify.py
.\.venv\Scripts\python -m mypy --no-incremental
node --check public-demo/app.js
node --check tests/public_demo_browser.cjs
git diff --check
```

Without `CITEPROBE_BROWSER`, the four browser cases are explicitly skipped; that
mode alone is insufficient for release. Chrome tests use actual 320x900, 390x900,
768x900 and 1440x900 CSS viewports, check screenshots' PNG dimensions, native
Tab/Enter navigation, Escape and focus restoration, headings/landmarks, tested text
contrast, 200% text scaling, inventory, rankings, filters and loading/error states.
They also trigger all three actual downloads, compare downloaded bytes with the
served versions and execute the downloaded verifier in isolated Python.

Screenshots, downloaded test files and JSON test reports remain in ignored pytest
directories. These checks cover relevant accessibility criteria; they do not
constitute a full WCAG certification, screen-reader audit or Safari/device test.

## Release

The existing Vercel project uses `public-demo` as its static root. No build-time
provider request, secret or private evidence is needed to serve the static files.
The Atlas and workbench render from the byte-preserved public export and manifest;
all candidate identity judgments, ranks, counts, access observations and the
reproducibility verifier remain unchanged. The deployed site should be checked at
its production domain for direct paper routes, fonts and downloads after release.
