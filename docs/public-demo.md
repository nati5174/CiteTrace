# CiteProbe public exploratory pilot

Status: **public exploratory pilot**. The site is hosted at https://citeprobe.vercel.app/. `public-demo/` is the only directory intended for Vercel publication. The site uses no API key and makes no provider API requests. Its selected metadata comes from the frozen dataset and verified offline evaluation; raw captures remain excluded. Publication metadata uses `owner_approved`; this does not certify canonical identities or change research evidence. Historical repair notes below describe earlier states.

## Security review

The previously flagged `api_key=` marker occurs in the `meta.notice` text of the saved **anonymous** OpenAlex response. Its value is a recognizable documentation placeholder; it is not a captured request credential. The raw body remains excluded from the site. The actual OpenAlex key was unavailable to the automated review, so its absence from evidence cannot be certified.

On your own Windows terminal, from the repository root, run:

```powershell
.\.venv\Scripts\python.exe scripts\audit_demo_key.py
```

The scanner reads `OPENALEX_API_KEY` from the local `.env` file without printing it. If `.env` does not exist, it uses a hidden prompt. It checks raw and decompressed evidence, draft outputs, and the site for exact and URL-encoded forms. It prints only counts and matching file paths, not the key, and writes no files. A clean result does not detect every possible encoding or other secret; review the proposed upload files and author/candidate metadata independently. If a match appears, do not share that file; protect or rotate the credential as appropriate. Never paste the key into chat or a shell command.

The static site uses only five files (`index.html`, `methodology.html`, `style.css`, `app.js`, `data.json`); no raw bodies, lookup bundles, personal email addresses or affiliation fields are intentionally exported. External fonts, analytics and tracking are not loaded. The data file includes scholarly author names and candidate DOI identifiers by design. Review these before approving publication. Pattern scans and tests do not establish legal clearance, author consent or the absence of all sensitive data.

## Local preview

```powershell
.\.venv\Scripts\python.exe -m http.server 4173 --directory public-demo --bind 127.0.0.1
```

Open `http://127.0.0.1:4173/` in your browser. Stop the server with Ctrl+C. Use an HTTP server because browser `fetch()` generally cannot load the data reliably from `file://` URLs.

## Deployment after owner review and explicit authorization

### Missing-data repair (2026-11-09)

The production `/data.json` endpoint returned HTTP 404 with `X-Vercel-Error:
NOT_FOUND`. Vercel reported production commit `4ea31f1`; that commit contains the
four site assets but omits the locally generated `public-demo/data.json`. Neither
the repository `.gitignore` nor a `.vercelignore` excludes the export (there is no
`.vercelignore`). The validated export is now staged for inclusion in the next
commit. No commit, push, deployment, or production setting change was performed.

The authoritative inputs are
`artifacts/empirical-pilot-immediate-001/a-frozen-001/dataset.json` and
`artifacts/empirical-pilot-immediate-001/a-empirical-evaluation-001/evaluation.json`.
The exporter checks their SHA-256 digests against the existing frozen integrity
and evaluation reproducibility records before validating their Pydantic schemas.
The existing public JSON exactly matches the export; no research was rerun.
Candidate order, metadata, identity decisions and recall evidence are retained.
Only explicitly selected public fields are exported; raw responses stay outside
the site. The research artifacts are local and untracked, so regeneration and
artifact-comparison tests require the owner's existing artifact workspace.

With the supplied Root Directory `public-demo`, Other/static framework, no build
command, and the root itself as output, the five files can be served directly.
Python and private research artifacts are not needed on Vercel. Do not add a
deployment-time export step. The read-only Vercel tools confirmed the deployment
and commit but did not expose the root/build/output settings; those settings were
not independently verified or changed. Include `data.json` in the eventual commit,
then verify `/data.json` returns JSON after an explicitly authorized deployment.

The regression tests check static HTTP delivery, Git inclusion, schema-compatible
rendering, evidence bounds, candidate inspection, and cohort transitions both
before data arrives and after failed requests. Failed loads retain an error and
`DATA UNAVAILABLE`; they never become an empty-cohort finding.

### Mobile release repair

The main navigation now remains visible below 800px as a wrapping row of native
links in the existing labeled navigation landmark. Tab, Enter, visible focus and
normal anchor behavior work without a menu script. The desktop navigation and
two-column hero remain in place. Reduced-motion preferences disable smooth scroll.

The 320px overflow originated in the hero grid's intrinsic minimum width: the
diagram's icon, text and unbroken status tag forced the hero children wider than
their available column. The hero now uses zero-minimum grid tracks, its children
can shrink, and diagram rows wrap at mobile widths. Filters wrap into rows rather
than requiring horizontal scrolling. Below 600px, paper titles span the row above
two provider results, each with a visible provider name. Long titles and candidate
identifiers wrap inside the dialog. There is no global overflow-hiding rule.

Research metadata, statuses and candidate labels use at least 12px text. Muted
greens were darkened while retaining the existing backgrounds and visual identity.
The browser checks calculate unrounded sRGB contrast and require at least 4.5:1
for visible alphanumeric text on the homepage, candidate dialog, standalone
methodology page and data-error state. This verifies the requested text contrast,
not every WCAG success criterion or every assistive-technology/browser combination.
See [WCAG contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

`tests/test_public_demo_browser.py` and `tests/public_demo_browser.cjs` provide
real Chromium regression checks at 320, 390, 768 and 1440 CSS pixels using the
browser's debugging protocol and Node's built-in WebSocket (Node 22+). They check
static delivery from `public-demo`, navigation with real Tab/Enter events, eight
papers and 41 candidate records, preserved displayed ranks/identity judgments,
dialog open/close and Escape/focus restoration, all cohort filters, readable text,
page/dialog overflow, methodology access, delayed/failed requests, and JavaScript
console/runtime errors. The intentionally failed HTTP request is expected.
Screenshots stay under the ignored pytest temporary directory.

Run the complete suite, including browser tests, from the repository root:

```powershell
$env:CITEPROBE_BROWSER = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
.\.venv\Scripts\python -m pytest -q --basetemp=.pytest-tmp-release -o cache_dir=.pytest-tmp-release-cache
.\.venv\Scripts\python -m ruff check scripts/export_public_demo.py tests/test_public_demo.py tests/test_public_demo_browser.py
.\.venv\Scripts\python -m ruff format --check scripts/export_public_demo.py tests/test_public_demo.py tests/test_public_demo_browser.py
.\.venv\Scripts\python -m mypy
node --check public-demo/app.js
node --check tests/public_demo_browser.cjs
git diff --check
git diff --cached --check
```

An installed Chrome or Edge executable can be supplied; no browser automation
dependency is added. Without `CITEPROBE_BROWSER`, the four browser cases are
explicitly reported as skipped, so that mode alone is insufficient for release.
The artifact-comparison tests still need the existing private frozen artifacts;
those artifacts are not part of the release or Vercel upload.

The release scope is exactly eight files: `public-demo/data.json`,
`public-demo/app.js`, `public-demo/style.css`, `scripts/export_public_demo.py`,
`tests/test_public_demo.py`, `tests/test_public_demo_browser.py`,
`tests/public_demo_browser.cjs`, and this document. Stage these explicit paths
only. Internal artifacts, credentials, ZIPs and browser profiles stay excluded.
The validated public JSON and frozen research artifacts are unchanged by the
mobile repair. Committing, pushing, deploying and changing Vercel settings are
separate actions requiring owner authorization.

Install and authenticate the Vercel CLI locally according to Vercel's instructions. In Vercel, create a new project with `public-demo` as its root and select static/other framework with no build command. Verify the project root is **only** `public-demo`; do not upload the repository or `artifacts/`. After reviewing that directory and authorizing publication:

```powershell
Set-Location public-demo
vercel deploy --prod
```

This command publishes a production deployment. Do not run it until the owner has approved the secret and privacy review and deployment. Any preview deployment also uploads files to Vercel and requires approval; it is not necessarily private. See https://vercel.com/docs/cli/deploy.

The page is an exploratory eight-paper pilot, not a general performance claim. Provider access conditions differ: the first OpenAlex lookup was anonymous; the following seven used an API key; Crossref was anonymous. The data shows retrieval outcomes and verified-identity uncertainty separately. The seed, frozen dataset, evidence and approved evaluation were not changed.

## Public-release wording and publication metadata

Empty provider responses display “No candidates returned” in rows and dialogs.
The serialized `NOT_FOUND` outcome is retained. An empty search does not establish
absence from the provider database. Scientific limitations, verified identity
criteria, candidate rankings, judgments, recall bounds and denominators are unchanged.

The public banners read “PUBLIC EXPLORATORY PILOT”; pending-review copy is removed
from the public pages. The JSON, exporter, frontend validator and regression tests
use `review_status: owner_approved` together. This is publication metadata, not a
research outcome. Do not infer new verification or empirical findings from it.
Frozen dataset/evaluation checksums remain enforced; the public JSON differs from
the prior export only in `review_status`. No raw captures are published.
