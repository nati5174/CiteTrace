# CiteProbe

An open-source Python benchmark for academic citation retrieval reliability.
Parts 1 through 4 implement dataset schemas, ground truth, deterministic mutations,
asynchronous OpenAlex/Crossref candidate retrieval, and offline identity evaluation
with explicit metric denominators and evidence bounds, plus offline analysis,
figures, optional source-cluster intervals and reproducible research-format reports.
No empirical provider-performance findings have been established from the current
pilot or the failed live smoke tests.

## Setup and checks

Requires Python 3.12 or later. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
.\.venv\Scripts\python -m pytest -q --basetemp=.pytest-tmp
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
.\.venv\Scripts\python -m mypy
```

The workspace-local pytest temporary directory avoids restricted system temp
directories. pytest owns and may clear the directory passed to `--basetemp`.
On other platforms use `.venv/bin/python` and `.venv/bin/citeprobe`.

## Commands

```powershell
.\.venv\Scripts\citeprobe validate data/pilot_dataset.json
.\.venv\Scripts\citeprobe mutate data/pilot_dataset.json --seed 42 --output mutations.json
```

Validation checks syntax and schema, not factual accuracy or live identifier
existence. Invalid data returns exit code 1. Validation accepts pending records
and prints how many records are verified and eligible. `benchmark_citations`
excludes pending records; mutation generation likewise excludes them and records
skip reasons. Direct mutation of a pending citation fails.

Mutation output files must not already exist. Source paths, symlink aliases, and
hard-link aliases are protected against overwriting. Canonical models are frozen,
with tuples for authors and citations. Functions build separately validated
payloads, preserving DOI/arXiv identifiers and linking to the original citation ID.
Each mutation contains complete citation values for downstream consumers, without
claiming that mutated metadata is verified canonical metadata.

## Data and provenance

`data/pilot_dataset.json` contains five arXiv preprint citations. Titles, complete
author lists, identifiers, and initial submission years were checked against the
linked arXiv abstract records on 2026-11-08 at 18:30:29 UTC (verification completion
time). Each record stores only its source URL, record identifier, verification
status, and actual verification timestamp. No PDFs or webpage snapshots are stored.

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [BERT](https://arxiv.org/abs/1810.04805)
- [Generative Adversarial Networks](https://arxiv.org/abs/1406.2661)
- [Deep Residual Learning for Image Recognition](https://arxiv.org/abs/1512.03385)
- [Auto-Encoding Variational Bayes](https://arxiv.org/abs/1312.6114)

The year represents the first arXiv submission, not a later publication year.
Authors follow the current abstract-page spelling, with given/family name splitting
recorded explicitly. These records intentionally use arXiv IDs without requiring a
DOI; DOI-only and dual-identifier records are also supported. Identifier validation
is syntactic; verified status is a curator assertion, not a lookup performed by
the CLI. Pending provenance must have a null timestamp; verified provenance must
have a timezone-aware timestamp.

This pilot is small and concentrated in machine learning. It is not representative
of academic literature. No verified volume/issue metadata was needed for these
preprints, so digit transpositions are skipped in the pilot and tested with clearly
synthetic fixtures instead.

## Mutation semantics and reproducibility

Algorithm version `1` uses SHA-256 of the seed, citation ID, and mutation type to
select positions independently of dataset iteration order. It generates independent
mutations against the original, rather than cumulative perturbations:

- Title typo: replace one ASCII letter with the next alphabetic letter, wrapping
  z to a and preserving case.
- Author initials: truncate each given-name token to its first character plus a
  period; split hyphenated given names, preserve family names and author order.
- Year shift: generate both -1 and +1, within years 1 through 9999.
- Word deletion: remove one whitespace-delimited title token, retaining at least
  one token. Interior whitespace is otherwise preserved.
- Digit transposition: swap one unequal adjacent pair of ASCII digits in either
  volume or issue, preserving the remaining text and leading zeroes.

Inapplicable operations are recorded with reasons, never emitted as unchanged
mutations. With seed 42 the pilot yields 25 mutations and five volume/issue skips.
Mutation IDs, payloads, and skip decisions are deterministic. Batch `generated_at`
records actual execution time and therefore differs across runs. Batch output also
records dataset version, seed, and algorithm version. Consumers should group repeated
mutations by `original_citation_id` when implementing future evaluation.

Tests run entirely offline, including mocked HTTP tests of Part 2.

## Resolve and replay (Part 2)

These commands make live provider requests when executed. Automated tests do not.

```powershell
.\.venv\Scripts\citeprobe resolve data/pilot_dataset.json --providers openalex crossref --output canonical-results.json
.\.venv\Scripts\citeprobe resolve-mutations mutations.json --dataset data/pilot_dataset.json --providers openalex crossref --output mutation-results.json
.\.venv\Scripts\citeprobe replay mutation-results.json --output replayed-results.json
```

`--limit N` selects the first N eligible input records, before expanding providers;
it is useful for a separately authorized small smoke test. No live smoke test was
run during implementation. Both provider adapters can be exercised with `--limit 1`.
`validate` and `mutate` retain their Part 1 interface and schemas.

Metadata-only lookup is the default for both input types. Adapters concatenate the
submitted title, all submitted author names, year, and optional volume/issue into a
text query. OpenAlex receives `search` and `per_page=5`; Crossref receives
`query.bibliographic` and `rows=5`. Author/year values are text hints, not exact
filters. Provider search semantics differ: OpenAlex searches work text, so an author
name in the query is not equivalent to an author-ID filter. This simple strategy
can be restrictive; the exact query and engine version are recorded for future
comparisons. There is no hidden fallback, query expansion, or canonical correction.

Mutation input is checked against the supplied dataset for version, original record
existence, verified eligibility, preserved identifiers, and declared changed fields.
Requests are built exclusively from `mutation.citation` bibliographic values.
The adapter interface cannot access the original record or evaluation IDs, and the
mutation task schema rejects identifier hints and identifier strategies. Canonical
identifiers retained in Part 1 mutation files remain local ground truth.

Canonical `resolve` additionally accepts `--strategy identifier`. It sends the DOI
when available, otherwise an `arXiv:` identifier. OpenAlex uses an exact DOI filter
for DOI inputs; other identifier lookups use provider text search. This is an
identifier-assisted strategy, not a guarantee of exact identity or provider arXiv
coverage. Submitted metadata is null in traces when only an identifier is sent.
This option is not available for `resolve-mutations`.

Resolution returns the first five provider-ranked records without local reranking.
Ranks are one-based positions in the original response, including gaps caused by
malformed candidates. Provider relevance/score values are retained unchanged.
Missing optional metadata is allowed; invalid individual records are skipped with
rank-specific warnings, preserving valid candidates. Malformed top-level envelopes
and non-JSON responses produce `API_ERROR`. If all returned candidates are malformed,
the outcome is also `API_ERROR`, not `NOT_FOUND`.

Outcomes are `FOUND`, `NOT_FOUND`, `TIMEOUT`, `RATE_LIMITED`, `API_ERROR`, and
`UNKNOWN` (reserved for indeterminate records). `FOUND` means candidates were returned,
not that any candidate is correct. `NOT_FOUND` means a valid empty provider search,
never that the citation is fake. Transport errors, HTTP errors, and empty search
results remain distinct. HTTP 404 on a search endpoint is an API error.

### Configuration and authentication

Only `httpx` was added as a runtime dependency. The engine shares one pooled
`AsyncClient` per run, bounds work with a fixed worker pool, and separately paces
each provider. Default global concurrency is 4; each provider has concurrency 1 and
one request per second. Configure with `--config resolver-config.json`, for example:

```json
{
  "concurrency": 4,
  "provider_concurrency": 1,
  "openalex_rps": 1,
  "crossref_rps": 1,
  "timeout_seconds": 20,
  "max_attempts": 3,
  "backoff_seconds": 0.5,
  "max_retry_wait": 30,
  "jitter_seed": 0
}
```

Timeout applies to HTTPX connect/read/write/pool phases; it is not an overall
experiment deadline. Provider limits are user-configured rather than automatically
raised from response headers. Use limits appropriate to your access tier.

Official requirements checked on 2026-11-08:

- [OpenAlex authentication](https://help.openalex.org/api/authentication/) permits
  basic requests without a key, with different budgets/rates for authenticated
  access. Set `OPENALEX_API_KEY` for a verified, activated key; it is sent only as
  an Authorization bearer header. The engine never requests or activates keys.
- [Crossref access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication)
  permits public access without credentials. Set `CROSSREF_MAILTO` for a polite
  User-Agent contact, or `CROSSREF_API_KEY` for Metadata Plus bearer authentication
  in `crossref-api-key`. Public access currently documents concurrency 1, so keep
  the default unless your access tier permits more.
- Search parameters follow the [OpenAlex search reference](https://help.openalex.org/api/searching/)
  and [Crossref REST reference](https://api.crossref.org/swagger-ui/index.html).

Credentials/contact values are read only from environment variables, never config
JSON, CLI flags, or persisted headers. `.env` is ignored by Git but is not loaded
automatically. The HTTP client disables environment proxy/netrc inheritance and
automatic redirects, avoiding accidental authentication forwarding. No proxy
configuration is implemented in this part. Provider cookies are excluded from
outgoing requests so they cannot become hidden lookup hints.

Retries cover timeouts, transport failures, 429, and HTTP 500/502/503/504. Permanent
4xx and malformed successful responses are not retried. Retry count excludes the
initial attempt. Exponential backoff uses reproducibly seeded jitter; numeric and
HTTP-date `Retry-After` values impose a minimum delay shared across provider workers.
If the requested delay exceeds `max_retry_wait`, no early retry occurs: remaining
unsent jobs for that provider receive explicit cooldown outcomes. Already in-flight
requests may complete. Other providers continue. No request exceeds the configured
attempt count.

### Saved result trace and replay

Output paths must not already exist; input aliases are rejected before networking.
The canonical dataset and mutation inputs are never rewritten. Operational CLI
errors return 1; a completed lookup run returns 0 even when individual results contain
API failures, which must be inspected through their explicit outcomes.

The versioned JSON bundle records engine/config versions, dataset/input/config
fingerprints, execution timestamp, and results in input/provider order. The bundle
also records selected source IDs and provider order, including for empty runs.
Each result records source kind, source citation or mutation ID, original citation ID, provider,
strategy, exact endpoint and query parameters, submitted bibliographic fields,
original provider ranks/scores, parsing warnings, status, timing, retry count, and
individual attempts. Evaluation identifiers are stored locally and never sent.

Each attempt preserves an allowlisted provider-response projection covering parsed
bibliographic fields and ranking. Identifier-bearing arXiv/DOI links are retained
without query strings or fragments; unrelated URLs, abstracts, affiliations,
contacts, arbitrary error prose, and authentication headers are excluded. Known
credential/contact values echoed in responses are redacted before parsing/storage.
A SHA-256 digest of the original response body records its identity, including for
non-JSON/error responses; this is not a full raw-response archive.

`replay` validates the saved schema and returns recorded results directly, without
network access, reparsing provider records, new timestamps, or reranking. Lookup IDs
depend on engine version, source identity, provider, strategy, and submitted query;
they exclude timestamps, latency, retries, and authentication. Fresh live responses
can naturally change over time; only replay guarantees the same saved candidates.
Mutation-batch fingerprints exclude its generation timestamp. Part 3 should use
source IDs and lookup IDs to compare records rather than execution timestamps.

## Offline evaluation (Part 3)

```powershell
citeprobe evaluate canonical-results.json --dataset data/pilot_dataset.json --output evaluation.json
citeprobe evaluate mutation-results.json --dataset data/pilot_dataset.json --mutations mutations.json --output mutation-evaluation.json
citeprobe evaluate canonical-results.json mutation-results.json --dataset data/pilot_dataset.json --mutations mutations.json --config evaluation-config.json --output combined-evaluation.json
```

Activate `.venv` first, or use `.\.venv\Scripts\citeprobe`. Evaluation performs no
HTTP requests. Each command creates JSON plus a sibling `.csv` file; override the
CSV location with `--csv-output`. Both outputs must be new files, distinct from each
other and all inputs, including hard-link/symlink aliases. Operational and integrity
errors return exit code 1. Failure to reserve/write both outputs cleans up files
created by that operation. Input files are never rewritten.

Original mutation files are required for mutation lookups: Part 2 stores original
citation references but not mutation types. Multiple mutation files may follow
`--mutations`. The evaluator checks input fingerprints, source references, and
reproduces each mutation from its recorded parameters before evaluation.

### Identity evidence

Canonical DOI and arXiv identifiers are the initial verified positive evidence.
Candidate identities are judged against the original canonical citation, including
for mutated lookups. Each candidate retains its provider rank and ranking values;
title or author similarity is never used as identity proof or for local reranking.

- `CORRECT`: a safely normalized identifier or verified same-work mapping matches.
- `INCORRECT`: explicit verified **different-work** evidence identifies a different
  work, with no conflicting positive or malformed evidence.
- `UNDETERMINED`: evidence is missing, incomparable, malformed, or contradictory.

Different DOIs, different arXiv IDs, or a DOI versus an arXiv ID do not themselves
prove different works. An identifier matching another dataset citation likewise
does not automatically establish distinctness. A matching title proves nothing
about identity. A candidate with both positive and negative identity evidence is
undetermined. Missing candidate identity evidence is never silently converted to
an incorrect match.

DOI normalization removes recognized `doi:`/DOI resolver wrappers, outer whitespace,
and ASCII case differences. Resolver URL paths are percent-decoded once; raw DOI
suffixes are not decoded, truncated, or stripped of punctuation. Identifier URLs
with credentials, query strings, fragments, or explicit ports are rejected. arXiv
normalization accepts recognized raw/prefixed/abstract/PDF forms, validates syntax,
and compares the base work ID without a version suffix. Original values are kept
in the candidate trace. No DOI-to-arXiv equivalence is guessed by this evaluator.

Optional `--identity-mappings mappings.json` supplies a schema-version `1.0` object
with `dataset_version` and a `mappings` array. Every mapping contains:

- `citation_id`: an existing verified canonical citation ID.
- `relation`: `same_work` or `different_work`.
- `identifiers`: objects containing `namespace` (`doi`, `arxiv`, `openalex`, or
  `crossref`) and `value`.
- `provenance`: source URL, record identifier, `verification_status: "verified"`,
  and an actual timezone-aware `verified_at` timestamp.

Crossref work IDs are interpreted as DOI identifiers. OpenAlex mappings refer to
work IDs such as `W123` or their `https://openalex.org/` form. Mapping relations are
explicit assertions about the referenced canonical work; unrelated same-work
mappings are not used to infer distinctness. Conflicting positive/negative mappings
for the same normalized identifier are rejected. No production identity mapping or
negative label is invented or populated automatically. Provenance remains a curator
assertion; offline evaluation cannot independently verify its factual accuracy.

### Metric definitions and missing evidence

For each group, `T` is the total validated lookup count, and `N` is the count with
outcome `FOUND` or `NOT_FOUND`. Provider failures and `UNKNOWN` are excluded from `N`.
An observation is a lookup, not an individual candidate.

For K=1 and K=5, a lookup is a `HIT` if a correct candidate exists at an **original**
provider rank <=K. Without a hit it is `UNDETERMINED` if an unidentified candidate or
malformed provider position within K could affect the answer; otherwise it is a
`MISS`. Valid empty retrieval is a miss. A rank-one parse failure never promotes
rank two. A confirmed hit remains a hit even if another position is undetermined.

Let `H_K` and `U_K` be hit and undetermined counts; `I_1` is the count with a confirmed
incorrect rank-one candidate, and `U_1` is also the uncertain top-one identity count.

| Metric | Confirmed numerator | Denominator | Possible numerator |
| --- | --- | --- | --- |
| Recall@1 | H_1 | N | H_1 + U_1 |
| Recall@5 | H_5 | N | H_5 + U_5 |
| Incorrect-match rate | I_1 | N | I_1 + U_1 |
| Unresolved rate | Valid NOT_FOUND count | N | Same as confirmed |
| Identity-undetermined rate | FOUND with undetermined rank-one identity | N | Same as confirmed |
| Combined provider error rate | TIMEOUT + RATE_LIMITED + API_ERROR count | T | Same as confirmed |
| Individual failure/unknown rates | Count of the named outcome | T | Same as confirmed |

Every metric includes `numerator`, `uncertain_count`, `denominator`, `value`,
`lower_bound`, `upper_bound`, and `undefined_reason`. For recall and incorrect-match
rate, an exact `value` is null whenever uncertainty can change the answer. Bounds
are confirmed numerator / denominator and possible numerator / denominator. These
are identification/evidence bounds, **not confidence intervals**. All values and
bounds are null for denominator zero. JSON uses null; CSV uses an empty numeric
cell plus the explicit undefined reason. A missing record is unresolved retrieval,
not a fake citation or an incorrect candidate.

`UNKNOWN` has its own rate and is not silently treated as a known API error.
Parsing failures with outcome `API_ERROR` are excluded from retrieval quality just
like other operational failures. Part 2's saved `ConnectError` smoke results can
be evaluated offline; they yield no eligible retrieval observations and therefore
null retrieval metrics, never zero recall or evidence of missing papers.

### Grouping, origin labels, and traceability

Evaluation defaults to `unknown` origin. Explicitly label genuinely observed input
with `--data-label observed`; use `--data-label simulated` for mocked experiments.
Labels are user assertions; the program cannot establish origin from a Part 2 file.
Only groups explicitly labeled `observed` have `empirical_data_eligible: true` for
future Part 4 use. This flag is a necessary origin condition, not a claim of study
validity or a research conclusion. Simulated and unknown data are diagnostic only.
No labels are inferred from successful statuses, verified citations, or filenames.

Optional evaluation configuration (all fields may be omitted):

```json
{
  "schema_version": "1.0",
  "default_data_label": "unknown",
  "input_labels": {},
  "cohorts": {},
  "groupings": [
    ["source_kind", "mutation_type"],
    ["original_citation_id"],
    ["cohort"]
  ]
}
```

`input_labels` maps a bundle's semantic SHA-256 ID (recorded under evaluation
`inputs[].bundle_id`) to its origin label. Per-bundle labels override the default;
`--data-label` changes only the default. `cohorts` maps canonical citation IDs to
cohort labels without modifying Part 1 data. Unknown references are rejected.
Grouping dimensions additionally support `provider` and `strategy`.

All aggregate groups always separate data label, provider, and lookup strategy;
configured dimensions add breakouts alongside the base groups. Duplicate grouping
specifications do not double-count observations. Per-lookup rows retain canonical
versus mutated origin, mutation type, cohort, and original citation ID regardless
of aggregate configuration. Both total and retrieval-eligible distinct original
citation counts are recorded. Aggregates are lookup-weighted descriptions: repeated
mutations from one original are correlated and must not be treated as independent
papers in future uncertainty estimates. No significance tests, intervals, or macro
averaging are implemented here.

Evaluation checks dataset versions/fingerprints, input and configuration fingerprints,
complete selected-source/provider inventories, lookup IDs, source eligibility,
original references, requests, ranks, final statuses, and attempt consistency.
Successful candidates/warnings are checked against the saved bibliographic response
projection using the existing parsers. Mutation requests must exactly reproduce the
recorded mutation metadata without canonical identifier or evaluation-ID hints.
Canonical identifier-assisted lookup remains supported and separately grouped.
Different resolver configurations cannot be pooled; evaluate them separately.
Duplicate lookup IDs or repeated observations are rejected even if labeled differently.

JSON output includes input bundle IDs and CLI file hashes, dataset fingerprint,
mapping provenance/fingerprint, evaluation configuration, metric definitions,
package/evaluator/schema versions, a local code fingerprint, and a deterministic
evaluation ID. It contains complete per-candidate judgments and per-lookup source
references. CSV contains grouped metric rows with the same evaluation ID and
explicit counts/bounds; the JSON file is the complete lineage artifact. Empty input
runs have null metrics and unknown strategy rather than an invented strategy label.

Identical inputs/configuration/code produce identical output bytes. Input order is
canonicalized, output paths are not persisted, and no current execution timestamps
are introduced. Input fingerprints/hashes detect mismatches, not forgery; files and
curator provenance are not cryptographically authenticated. Replay uses previously
parsed candidates and evidence only; no API availability or factual identity claim
is inferred from fixture tests.

## Offline analysis and reporting (Part 4)

Install the optional plotting dependencies and activate the environment:

```powershell
.\.venv\Scripts\python -m pip install -e '.[dev,report]'
.\.venv\Scripts\Activate.ps1
```

The `report` command reads Part 3 JSON artifacts, not CSV summaries. It does not
resolve citations, rerun identity matching, change metric definitions, or make
network requests. Multiple compatible evaluation files may precede the options.

```powershell
citeprobe report mutation-evaluation.json --experiment mutation-robustness --output-dir reports/experiment-b
citeprobe report recent-evaluation.json --experiment recent-preprints --study-manifest study.json --dataset data/recent.json --lookup-bundles recent-lookups.json --output-dir reports/experiment-a
```

Output directories must be new. Reports are built in a temporary sibling directory
and published only after successful rendering. Existing directories, input aliases,
and input-containing output paths are rejected. No inputs are rewritten. Parts 1–3
commands remain unchanged.

Each origin has its own subdirectory (`observed/`, `simulated/`, or `unknown/`) with
`report.md`, `analysis.json`, `reproducibility.json`, `tables/`, and `figures/`. The
root `reproducibility.json` indexes these separate reports; it has no pooled metrics.

### Study manifest and eligibility

Part 1 stores citation years, not verified first-public preprint dates. Part 3
stores judgments and source fingerprints, not the complete collection chronology.
A new, separate schema-version `1.0` study manifest supplies these facts explicitly:

| Field | Meaning |
| --- | --- |
| `dataset_fingerprint` | Exact Part 3 dataset fingerprint |
| `citation_ids` | Explicit, unique study citation inventory |
| `sampling_method` | Actual source selection and sampling methodology |
| `verification_method` | Actual ground-truth and date verification methodology |
| `collection_started_at`, `collection_finished_at` | Declared timezone-aware collection window |
| `lookup_bundle_ids` | Original semantic bundle IDs from Part 3 `inputs[].bundle_id` |
| `reference_date` | Explicit UTC calendar date for Experiment A, equal to the collection-end UTC date |
| `preprint_dates` | Citation ID, verified first-public date, precision, and source provenance |

Each date entry has `citation_id`, `publication_date` (`YYYY-MM-DD`), `date_kind`
(`first_public_preprint` or `revision`), `precision` (`day` or `timestamp`), optional
timezone-aware `published_at`, and Part 1-style `provenance`. Timestamp precision
requires a timestamp matching the UTC date; day precision must omit it. Month/year
information cannot be promoted to an invented date. Pending dates remain pending.

The complete, runnable example at `tests/fixtures/part4-reporting/study.json` is
**simulated only**, including its provenance timestamps. Do not use its fabricated
test dates in empirical research. No manifest with real recent-preprint dates is
provided or automatically constructed for the five-paper pilot.

Empirical report eligibility requires explicitly observed Part 3 inputs, the source
dataset with verified ground truth, a study manifest, all referenced original
lookup bundles, and usable main-experiment retrieval observations. Experiment B
also needs actual mutation observations; canonical-only data is baseline diagnostic
material. Original lookup timestamps and resolver settings are validated locally.
Manifest timestamps must contain actual lookup timestamps. Observed labels alone
do not establish provenance, representative sampling, or study validity.

Incomplete provenance produces diagnostics, not invented study methods. Simulated
origins always produce demonstration reports; unknown origins remain diagnostic.
Failure-only inputs cannot establish retrieval-performance findings. Reporting
cannot relabel data; there is no `report --data-label` option.

### Experiment A: verified retrieval coverage under the recorded search strategy

Only canonical metadata-only observations enter the main analysis. Paper age is the
UTC calendar-date difference between the explicit reference date and verified
first-public preprint date. Inclusive cohorts are 1–7, 8–14, 15–30 and 31–60 days.
Day-zero, older, future-dated, pending-date, missing-date, revision-only, and
out-of-inventory observations receive explicit exclusion reasons. They remain in
the analysis trace. Study papers without evaluated lookups are explicitly listed.
When original timestamps establish that a lookup preceded first-public availability,
it is also explicitly excluded from Experiment A, even if a later reference date
would place the paper in a recent cohort. Timestamp precision is respected; no
within-day ordering is invented for date-only publication metadata.

The default declared collection-window limit is **24 hours**. A longer declared
window retains observations and timestamps but prevents empirical report mode
unless explicitly permitted with `--max-collection-hours 72` (or configuration).
Even with an override, long-window limitations are disclosed. This option never
changes publication dates or silently drops observations. Actual timestamps are
preserved in `analysis.json` and `tables/lookup-timings.csv`.

All Experiment A metric tables and figure/report templates describe the quantity
as **verified retrieval coverage under the recorded search strategy**. `NOT_FOUND`
does not establish absence from a provider's database or a fabricated paper.
Cross-sectional age cohorts are not indexing latency, and different provider
indexing scopes limit comparisons. No longitudinal indexing claims are generated.

### Experiment B: metadata-mutation robustness

Metadata-only canonical baselines and each mutation type are analyzed separately.
Identifier-assisted canonical results appear only in `tables/identifier-assisted.csv`.
`baseline-availability.csv` records baseline presence/outcome and retrieval eligibility
for every mutation lookup. Missing baselines remain missing, never zero-performance
observations. Both total and retrieval-eligible distinct original-paper counts are
preserved.

Comparisons record shared and unmatched original citation IDs. All-source summaries
remain descriptive when source sets differ. Additional matched-source panels use
only original papers with retrieval-eligible observations on both sides, retaining
all associated observations, including other failed mutations of the same paper.
The matched table labels this selection explicitly. `paired_retrieval_sources`
describes the full-source comparison; `matched_subset_paired` describes the common
eligible-source subset. No provider/condition is given an invented paired baseline.

### Optional statistical uncertainty

Bootstrap is disabled by default. Enable with `--bootstrap`; defaults are seed 0,
2,000 replicates, 95% percentile intervals, and minimum 30 eligible distinct source
papers. Configuration can raise, but cannot lower, the 30-paper safeguard.

```powershell
citeprobe report mutation-evaluation.json --experiment mutation-robustness --bootstrap --seed 0 --bootstrap-replicates 2000 --output-dir reports/bootstrap-b
```

The resampling unit is `original_citation_id`. A draw retains every observation in
each sampled cluster, including its multiplicity. Matched comparisons with identical
source sets use identical source draws across providers and mutation conditions.
Unmatched full samples have different resampling populations/plan IDs and are not
presented as paired inference. Matched subsets are available separately. The original
Part 3 lookup-weighted ratios are retained; source resampling does not redefine them
as paper-weighted averages or averages of group percentages.

Each interval records its resampling plan, cluster count, requested, attempted,
valid and invalid replicate counts, and suppression reason. Intervals are suppressed
for small samples, exact-null metrics, any undefined replicate, or a degenerate
bootstrap distribution. Replicates are not silently discarded. Identity-evidence
bounds remain separate and are never replaced by a midpoint or a statistical CI.
The minimum cluster count is a conservative operational rule, not a guarantee of
statistical validity. Cluster independence and the study sampling design remain
assumptions. No significance tests, difference tests, or significance claims are
implemented. See [Cameron and Miller (2015)](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015.pdf).

### Tables, figures and reproducibility

Each origin-specific report has:

- `provider-comparison.csv`: estimates by provider, condition and cohort.
- `cohort-coverage.csv` for A or `mutation-robustness.csv` for B.
- `matched-source-comparison.csv`, `outcomes.csv`, `exclusions.csv`, and
  `identifier-assisted.csv`; B also has `baseline-availability.csv`.
- `lookup-timings.csv` when actual original timestamps are supplied (otherwise a
  header-only table).
- Recall-by-provider, age/mutation, operational-outcome, and identity/sample-size
  figures. Long lists are paginated rather than compressed to unreadable labels.

Metric tables retain confirmed numerators, uncertain counts, denominators, exact
nulls, evidence bounds, distinct-paper counts, statistical intervals, and suppression
diagnostics. CSV null numeric values are blank with explicit reasons. A null never
becomes zero. Part 3 aggregate semantics are reused without identity rematching.

The ten-section Markdown report contains methods, observed or demonstration results,
limitations, threats to validity, reproducibility instructions and restrained
conclusions. Narrative templates are tied to actual counts. Reports do not infer
unrecorded dates, representative sampling, missing observations, database absence,
or provider indexing latency.

Matplotlib is the only direct dependency in the optional `report` extra. SVG is the
default; `--figure-formats svg png pdf` enables other formats. A configuration with
`figure_formats: []` produces tables/Markdown/JSON without requiring Matplotlib.
Figures use bundled DejaVu Sans, fixed metadata and SVG IDs, accessible colors, and
separate visual marks for identity evidence and statistical intervals. Undefined
metrics are labeled explicitly. `report_kind` and origin appear on every figure.

Analysis configuration is a versioned JSON object passed with `--config`:

```json
{
  "schema_version": "1.0",
  "experiment": "mutation-robustness",
  "max_collection_hours": 24,
  "bootstrap": false,
  "seed": 0,
  "bootstrap_replicates": 2000,
  "confidence_level": 0.95,
  "min_cluster_count": 30,
  "figure_formats": ["svg"]
}
```

CLI experiment and configuration must agree; explicit statistical/window/figure
options override the matching fields. The reproducibility manifest records the
effective configuration, evaluation/dataset fingerprints, input/output file hashes,
analysis code fingerprint, and available Python/plotting dependency versions.
No current execution timestamps or output-path-dependent IDs are introduced.
Deterministic JSON/CSV/Markdown and SVG/PNG/PDF bytes are tested within the same
software/font environment; cross-platform figure byte identity is not promised.
Fingerprints detect content mismatches, not forgery or false curator assertions.

The six-case simulated fixture can be used without any API calls:

```powershell
citeprobe evaluate tests/fixtures/part3-final-verification/lookups.json --dataset tests/fixtures/part3-final-verification/dataset.json --identity-mappings tests/fixtures/part3-final-verification/identity-mappings.json --config tests/fixtures/part3-final-verification/config.json --output demo-evaluation.json
citeprobe report demo-evaluation.json --experiment recent-preprints --dataset tests/fixtures/part3-final-verification/dataset.json --lookup-bundles tests/fixtures/part3-final-verification/lookups.json --study-manifest tests/fixtures/part4-reporting/study.json --output-dir reports/demo-a
```

Run the complete checks with the plotting extra installed:

```powershell
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

Reuse the workspace-local `.pytest-tmp` directory; do not point `--basetemp` at an
input or report directory because pytest clears its own temporary storage.
# Milestone 3B research dataset infrastructure

[Milestone 3C-5](docs/research/milestone-3c5.md) adds raw response evidence,
source-located extraction, and offline `evidence-verify` replay. Historical
projection-only artifacts remain unchanged. No live authorization is implied.

Acquisition preparation and offline replay are documented in
[Milestone 3C-1](docs/research/milestone-3c1.md). Live acquisition requires separate
explicit authorization; no empirical data is bundled with its synthetic fixtures.

See [offline dataset infrastructure](docs/research/milestone-3b.md) for the
`dataset-validate`, `dataset-sample`, `dataset-freeze`, and `dataset-verify` commands.
They do not acquire papers or perform provider requests. Existing commands remain
available. Research collection still requires separate approval.

Milestone 3C-7 adds bounded pilot inventories, complete enumeration, exact-ID
batches, curator-reviewed selection and frozen replay. See the
[pilot acquisition commands and request budgets](docs/research/milestone-3c7.md).
The approved A-S1 pilot uses **submission age**; the original announcement-age
protocol remains separate. `pilot-plan-*`, `pilot-frame`, `pilot-replay`,
`pilot-acl-pin`, `pilot-select`, `pilot-freeze` and `pilot-verify` run offline.
`pilot-run` requires a separately authorized, hashed request inventory and window.

