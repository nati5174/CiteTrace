# Experiment B dataset protocol 1.0

Milestone 3B revision 1.1: planned and actual collection times are separate.
Translations are distinct derivatives by default, not automatically equivalent.
Source-declared baseline aliases need provenance but not two reviewers; newly
asserted equivalences require two independent approvals. Possible duplicates are
flagged only; verified duplicates require a recorded sampling representative.
Identity-policy revision 1.1 takes precedence over earlier wording.

Status: design for review; no new dataset or observations created.
Question: how does recorded metadata-only retrieval change after independent,
small perturbations of verified canonical citations? Ground truth always remains
the original verified scholarly work under identity-policy.md.

## Source frame and sample

Propose a separate fixed-date, English-metadata cs.CL publication frame for years
2018–2023, constructed from authoritative repository/proceedings inventories.
Exact inventory releases, enumeration procedure and completeness must be frozen
before selection; do not begin collection with an unspecified frame. Include
DOI-only, arXiv-only and verified dual-identifier source strata. A dual identifier
requires a verified bridge; absence of a verified bridge is not proof none exists.
Strata describe the frozen verified identity inventory. Disclose that identifier
availability and editorial selection can bias source composition.

Pilot: 60 unique scholarly sources, 20 per identifier stratum. Expansion target:
300, 100 per stratum. Targets are logistical choices, not statistical power
guarantees. Record shortages; do not invent aliases, broaden years silently, or
condition inclusion on provider retrieval success. Confirm volume/issue
applicability within the frame; do not force preprints to have journal fields.
If a digit-transposition panel is too small, report the limitation. A later
explicitly sampled journal supplement is a separate frame/analysis, not a hidden
replacement in this cs.CL sample.

Eligibility requires verified identity and canonical title, author sequence,
publication year and any recorded volume/issue, plus source provenance. Distinct
scholarly works are the sampling units: select only one verified preprint/
publication representation per source; document the metadata representation and
version. Similarity alone cannot collapse records. Freeze and screen the full
frame, sort IDs, and select within each stratum by SHA-256 of UTF-8
`citeprobe-B-v1|seed=0|<source-id>` (digest then ID tie break). Record reserves,
screening decisions and reasoned replacements before retrieval; no performance-
based replacements. A verified identity inventory must not depend on provider
success. Retain candidate-level uncertainty during subsequent adjudication.

## Controlled conditions

Use mutation algorithm version 1 with seed 0 and its current exact semantics:

| Condition | Change and applicability |
|---|---|
| Canonical | Original verified metadata; no identifier hints |
| title_typo | One existing ASCII alphabetic character replaced by the next alphabetic character, wrapping z; skip if no eligible character |
| author_initials | Given-name tokens become initials; family names remain; skip if no actual change |
| year_shift | Separate minus-one and plus-one records; skip an out-of-range direction |
| title_word_deletion | Delete one whitespace-delimited token; require at least two tokens |
| digit_transposition | Swap one unequal adjacent ASCII digit pair in volume or issue; skip if unavailable |

The character substitution is deterministic and is not a model of real keyboard
error frequencies. Each mutation starts independently from canonical metadata;
there are no compound errors. Record selected positions, deleted token, delta,
seed, algorithm version, actual values and source IDs. Preserve skip reasons;
never replace a skipped/no-change condition with a fabricated field or count it
as a retrieval failure. Generation timestamps do not define mutation identity.

At most six mutations plus one canonical condition per paper: nominal lookup
attempt upper bounds are 840 for 60 sources and 4,200 for 300, across two
providers at one attempt per condition. Actual totals depend on applicability.
Frame acquisition/verification requests are separate. These are planning budgets,
not permission to issue requests. Freeze rate limits/timeouts/auth configuration
without storing secrets; any retries need a separately approved attempt budget.

Run canonical and mutations in one planned short wave where feasible; preserve
actual times and deterministic source/condition order. Alternate/interleave source
blocks in a prespecified order so all canonical searches do not systematically
precede all mutation searches. No outcome-driven query refinement. Search inputs
contain only the selected condition's title/authors/year/volume/issue. Preserved
DOI/arXiv identifiers, original metadata for mutations, and internal IDs must
never become hidden hints. Identifier-assisted results belong to another strategy.

## Comparison and metrics

Keep provider ranks exactly. Analyze each mutation type against its own matched
canonical source set, because applicability changes composition. Show full
descriptive panels and matched-source inventories separately. Missing canonical
baselines are missing, not assumed failures. Year-shift type panels pool the two
directions transparently (up to two lookups per source); do not equate their row
count with unique papers or silently mix direction-specific estimands. Separate
directional diagnostics require an explicit provenance-backed view, not altered
metric definitions. Do not pool all mutation categories into a supposedly equal-
source summary when applicability differs.

Use existing lookup-weighted Part 3 calculations, separately for each provider,
strategy, origin and condition. N is validated FOUND + NOT_FOUND lookups; T is all
validated verified-source lookups. For K=1,5, let H_K be confirmed hits and U_K be
identity/parse-undetermined retrievals without a confirmed hit. Recall bounds are
H_K/N to (H_K+U_K)/N, exact only if U_K=0. Incorrect top-one bounds are I_1/N to
(I_1+U_1)/N using rank-one identity uncertainty as implemented. Unresolved is
valid NOT_FOUND/N; identity-undetermined is FOUND with uncertain rank-one/N.
Provider errors (TIMEOUT, RATE_LIMITED, API_ERROR) use T and are separate; UNKNOWN
is separate and excluded from retrieval metrics. Zero denominators return null.
The evaluator's original definitions remain the authoritative contract.

Mutations and repeated conditions from a source are dependent. Retain
original_citation_id in every artifact. Optional source-cluster bootstrap uses
the identical sampled source IDs and multiplicities for paired conditions and
providers; never resample mutation rows independently. Label unmatched source
sets descriptively; common source IDs alone do not guarantee paired usable
retrievals after provider failures. Defaults and suppression rules are those in
Experiment A; no tests of significance. A 60-source pilot has only 20 per stratum,
so stratum-specific statistical intervals are suppressed at the 30-source rule.
Evidence bounds remain separate from statistical intervals.

Baseline and post-retrieval alias/adjudication ledgers are versioned separately.
Apply the same finite verification procedure to both providers and all conditions;
retain unresolved cases instead of excluding papers with difficult identities.
The old five-paper integration pilot is not the research sampling frame.
