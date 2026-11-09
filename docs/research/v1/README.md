# Milestone 3A research design package 1.0

Design-only release for review. No live requests, sampling-frame acquisition,
dataset expansion, mutation generation or benchmark execution are authorized or
performed by this package. Identity policy is complete as a proposed normative
version; study-specific choices remain subject to adoption before collection.

## Documents

1. [Identity policy](identity-policy.md)
2. [Experiment A dataset protocol](experiment-a.md)
3. [Experiment B dataset protocol](experiment-b.md)
4. [Schema and provenance checklist](schema-and-provenance-checklist.md)

## Proposed sample and attempt budgets

| Experiment | Design pilot | Expansion target | Maximum retrieval attempts, pilot / target |
|---|---|---|---|
| A: recent-preprint retrieval coverage | 40 sources, 10 per age cohort | 200 sources, 50 per cohort | 80 / 400 |
| B: mutation robustness | 60 sources, 20 per identifier stratum | 300 sources, 100 per stratum | 840 / 4,200 |

Budgets assume two providers, one attempt per condition, no recollection. B has
at most one canonical plus six mutation conditions per source. These numbers are
design choices, not guarantees of precision, power or frame availability.
Acquisition and authoritative identity verification need separate finite budgets.
Do not pool distinct collection waves to fill a target without a revised protocol.

## What is settled and what remains unresolved

The conservative label rules, separation of retrieval and identity evidence,
candidate-level adjudication, preservation of ranks, versioned provenance,
handling of provider failures and evidence bounds can be adopted now. The
existing metric definitions need no change.

The Milestone 2 target alias 10.48550/arXiv.1706.03762 is verified from arXiv and
was not returned. Five Crossref DOI candidates form a deposited version cluster
and share metadata/abstract/resource, but their bridge to the target remains
unverified. They stay UNDETERMINED. OpenAlex candidate distinctness was not
authoritatively verified in the six-request batch. Neither issue is resolved by
adopting a policy. Do not invent conclusions to make all identities determinate.

The original integration sample is neither a recent-preprint cohort nor the
proposed research sampling frame. Successful requests are not established
retrieval identity, representative coverage or indexing latency evidence.

## Milestone 3B implementation plan

1. Adopt policy 1.0 and the source-frame, language/year/category, sample, review and
   timing choices. Fix the authoritative inventory sources/releases and public
   release-date verification rule. Assign reviewers or explicitly document the
   absence of independent review; pending new mappings stay out of primary use.
2. Implement only the small typed sidecar ledger and offline preflight described
   in the checklist. Preserve all existing dataset, lookup and metric contracts.
   Add explicit validation of identity conflicts and review/evidence completeness.
3. Implement an offline deterministic selection and schedule planner: frame
   screening, per-stratum hash order, reserve rules, immutable task inventory,
   condition/provider sequencing, maximum attempt calculation and new output
   paths. No network acquisition is bundled into this implementation approval.
4. Use simulated fixtures to test cohort boundaries and announcement/submission
   distinctions, sampling stability/shortfalls, duplicate sources, pending and
   conflicting evidence, independent review, skip reasons and both year shifts.
   Test exact mutation metadata isolation, schedule/request budget reconciliation,
   paired source grouping, origin separation, null bounds, provider-error
   exclusion, immutable inputs and deterministic JSON/CSV/report outputs.
5. Run full pytest (warnings as errors), Ruff lint and format checks, and mypy.
   Review a concrete dry-run plan and finite stage-specific request budgets.
6. Seek separate approval for authoritative frame acquisition/ground-truth
   verification, then freeze and validate the real dataset before asking for
   retrieval collection approval. Provider authentication/access requirements and
   rate policies must be checked at that authorized stage. No request is implied
   by approving offline implementation.

## Explicit go/no-go gates

**GO now:** policy/design review and, after approval, Milestone 3B offline
implementation. Current schemas provide the main data path; no metric change is
needed. Supplementary provenance and sampling validation are the minimal gaps.

**NO-GO now:** empirical acquisition, retrieval collection, expansion or research
claims. No frozen real frame, complete research ledger, public-date evidence,
approved sampling implementation or request-stage authorization exists yet.

**GO for frame acquisition only when:** design choices and endpoints/source
scope, request limits, storage rules and local execution environment are approved.
This does not authorize provider lookups.

**GO for retrieval collection only when:** selected ground-truth sources and A
public dates are verified; immutable frame/selection/evidence ledgers reconcile;
source identities and required baseline aliases are established without provider
outcome selection; task/schedule/budget/configuration are frozen; offline checks
and relevant quality gates pass; credential redaction/output protection work; and
the user explicitly approves the collection stage and budget.

Do not require every future candidate identity to become determinate before
research can proceed. UNDETERMINED with honest evidence bounds is a valid outcome.
The remaining Milestone 2 cluster is not itself a permanent veto on a new study:
the required gate is an adopted evidence policy and explicit unresolved handling,
not forced resolution of those five DOIs. Stop an affected evaluation when actual
conflicting evidence cannot be represented safely. Report sampling deficiencies
or operational failures as limitations instead of quietly selecting replacements.

**GO for empirical reporting only when:** explicitly observed artifacts pass
Part 3/4 integrity checks, compatible dataset/evidence/protocol versions are
present, actual timing is disclosed, A's collection-window override is explicit
if needed, and at least one usable retrieval denominator exists. All-failure,
simulated or unknown data remain diagnostic/demonstration material. Unknown
candidate identity does not authorize exact metrics or statistical conclusions.

## Review decisions

Please review the proposed cs.CL/English scope; A's 40/200 and B's 60/300 source
targets; B's 2018–2023 frame and equal verified-identifier allocation; one-attempt
collection pilot; seed 0 and hash-based selection; two-reviewer adjudication;
derivative/translation scope; and minimal Milestone 3B sidecar/planner work.
Approval of these documents does not authorize live requests.

## Local checks performed for this release

Reviewed AGENTS.md, relevant Milestone 2 investigation/verification/audit records,
and current citation, mutation, study, identity and evaluation contracts. No code
or source data changes were needed. Documentation links and required section
coverage are checked locally; tests/lint/type checks are not claimed to have run
for this documentation-only task. The separate integrity manifest records hashes
of Milestone 2 files and the canonical dataset and compares them with previously
saved audit hashes where available.
