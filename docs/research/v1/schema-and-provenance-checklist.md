# Dataset schema and provenance checklist 1.0

Milestone 3B revision 1.1: research pre-collection manifests are distinct from
post-collection StudyManifest records. Preserve planned windows separately from
actual observations. Record explicit origin on evidence, separate possible and
verified duplicate decisions, and distinguish authoritative baseline aliases from
new mappings requiring two independent approvals. Translations are not accepted
automatically as SAME_WORK. See identity-policy revision 1.1.

This checklist describes current support and required preflight work; it does not
assert that a research dataset or sampling frame already exists.

| Requirement | Existing contract | Additional record or gate |
|---|---|---|
| Canonical metadata, DOI or arXiv, verification | Citation, Provenance, Dataset | Verify every recorded field, not only schema acceptance; freeze dataset version/hash |
| Verified first-public date and precision | PreprintDate | Preserve authoritative public-announcement evidence; distinguish v1 submission/revision |
| Cohorts and UTC timing | StudyManifest, AnalysisConfig | Reference date must equal UTC collection-end date; record planned versus actual timing |
| Sampling method and source inventory | StudyManifest has free-text sampling_method and citation_ids | Typed, versioned sampling/screening ledger for frame snapshot, ranking, reserves and exclusions |
| Canonical/mutated isolation | LookupTask, SearchMetadata, request metadata | Offline preflight checks exact query payloads, strategy and absence of identifiers/internal IDs |
| Deterministic mutation values/skips | Mutation, MutationBatch | Algorithm 1, seed 0; reconcile full inventory, both year directions and applicability |
| Outcomes, ranks, attempts and response evidence | LookupBundle | Preserve timestamps, status, scores, response projection/hash and no secrets; full-body hash alone is not independent attestation |
| Explicit identity equivalence/distinctness | IdentityMappings | Multi-source evidence/reviewer/disagreement ledger, conflicts gate and policy version |
| Candidate ambiguity | CandidateJudgment | Keep pending assertions outside verified mappings; unresolved cases stay in denominator bounds |
| Grouping and source dependence | EvaluatedLookup, AnalysisPanel, Comparison | Preserve original source identity, strata and condition inventory in sidecar; verify matched sources |
| Origin and reproducibility | EvaluationConfig/Output, AnalysisOutput | Observed label is a curator assertion; retain acquisition evidence and hashes; never pool simulated/unknown |
| Report provenance | StudyManifest, evaluation and analysis fingerprints | Bind dataset, bundle, mappings, policy, source ledgers and protocol IDs in a run manifest |

## Mandatory evidence fields

For each source: stable citation ID, scholarly-source identity, verified title,
ordered complete authors, bibliographic year and identifier(s); any optional
volume/issue must be verified. Keep source URL, record identifier, actual
retrieval/verification time and status. Different sources may verify different
fields: the current Citation has one provenance object, so supplementary field
evidence belongs in the sidecar ledger. No invented PDFs, dates or IDs.

For A, also record first-public date, precision, optional UTC timestamp, source
field/excerpt and proof that it is public release rather than submission or
revision. Record the frame snapshot's acquisition time separately. Unverified
dates are pending and ineligible for age cohorts; retain exclusion accounting.

For selection: frame release/snapshot hash, source system, language/category/year
rules, source inventory hash, eligibility flags/reasons, stratum, deterministic
sampling key, selection ordinal, reserve/replacement history and target/actual
sample sizes. Include source-level alias deduplication evidence and any unresolved
duplication. Do not expose selection or evaluation identifiers to providers.

For adjudication: candidate ID/rank, target ID, evidence sources/hashes, relation
assertion versus established conclusion, retrieval/review times, reviewer IDs,
agreement/disagreement, policy version and rationale. Store snippets needed to
reproduce the decision without full webpage/PDF archives. A missing verification
timestamp stays missing; recording a timestamp does not prove the claim.

For each run: immutable protocol/configuration IDs, code/schema versions, origin,
dataset and source fingerprints, finite request/attempt budgets, approved endpoint
classes, provider settings, exact submitted metadata, timing, outcome and budget
ledger. Mark post-retrieval evidence enrichment separately from retrieval inputs.
Keep provider authentication configurable and out of saved artifacts. Confirm
current provider access requirements only during a separately authorized readiness
check; this offline document does not assert future authentication requirements.

## Minimal Milestone 3B implementation scope

Parts 1–4 models should remain compatible. Add a small Pydantic sidecar design
ledger and an offline preflight validator rather than inserting research-only
fields into frozen canonical/lookup schemas. The ledger should represent the
sampling frame, selected/reserve/excluded IDs, source field evidence, adjudication
and policy/protocol hashes. A future schema may separate sampling from evidence
records if that keeps modules small.

Validate the ledger against existing Dataset, StudyManifest, MutationBatch,
IdentityMappings and configured run inventory. Reject incomplete public-date
evidence, invalid replacements, conflicting identity assertions, missing required
reviews and identifier leakage. Material candidate conflicts that the current
evaluator cannot express safely must block that evaluation until adjudicated;
do not implement an implicit candidate override. Persist the conflict inventory.

The current CLI can limit a dataset prefix but does not directly schedule a
stratified selection, interleaved canonical/mutation conditions or provider-order
balancing. A minimal future planner should produce an explicit offline schedule
and approved request budget, preserving the original dataset and consistent task
references. Connect execution to that plan only after separate approval and
mocked integration tests. No collector is implemented in Milestone 3A.

Existing grouping supports cohort, provider, mutation type, source and strategy,
but arbitrary identifier strata and year-shift direction are not first-class
analysis dimensions. Keep those labels in the ledger. For initial research use
separate compatible panels/views with explicit inventories; extending grouping
requires a small reviewed change and tests, not silently overloading cohort.

## Release checklist

- Schema validation and bibliographic fact verification both complete.
- Dataset version/hash and mapping/evidence/policy/protocol hashes fixed.
- Frame source, sampling population and shortfalls disclosed.
- No outcome-conditioned sampling, replacement or verification.
- All selected source identities verified; candidate ambiguity remains allowed.
- Both providers receive the same intended metadata condition, without identifiers.
- Timing and budget preflight complete; output paths are fresh and protected.
- Deterministic offline fixture pipeline passes, with origin isolation.
- Existing metrics/null semantics and original ranks preserved.
- Full pytest, Ruff lint/format and mypy pass after any implementation changes.
- Explicit authorization for frame acquisition, verification and retrieval stages.
