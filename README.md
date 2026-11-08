# CiteProbe

An open-source Python benchmark for academic citation retrieval reliability.
Part 1 implements dataset schemas, ground truth, and offline mutations only.
No API resolution, retrieval scoring, or reporting is implemented.

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

Tests run entirely offline. No HTTP client or provider integration exists in Part 1,
so network retry/error/rate-limit behavior is outside this implementation.
