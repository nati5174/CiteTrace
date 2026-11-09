# CiteProbe local public-demo draft

Status: **owner security and publication review pending**. Nothing has been deployed. `public-demo/` is a static-only site and is the only directory intended for Vercel upload; raw evidence is outside it. The site makes no OpenAlex or Crossref requests and uses no API key. The draft export was generated from the frozen dataset and the approved offline evaluation, retaining only citation titles, author names, identifiers, cohort, candidate metadata and identity judgments. Scholarly author names remain personal information and require your publication review.

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

Install and authenticate the Vercel CLI locally according to Vercel's instructions. In Vercel, create a new project with `public-demo` as its root and select static/other framework with no build command. Verify the project root is **only** `public-demo`; do not upload the repository or `artifacts/`. After reviewing that directory and authorizing publication:

```powershell
Set-Location public-demo
vercel deploy --prod
```

This command publishes a production deployment. Do not run it until the owner has approved the secret and privacy review and deployment. Any preview deployment also uploads files to Vercel and requires approval; it is not necessarily private. See https://vercel.com/docs/cli/deploy.

The page is an exploratory eight-paper pilot, not a general performance claim. Provider access conditions differ: the first OpenAlex lookup was anonymous; the following seven used an API key; Crossref was anonymous. The data shows retrieval outcomes and verified-identity uncertainty separately. The seed, frozen dataset, evidence and approved evaluation were not changed.
