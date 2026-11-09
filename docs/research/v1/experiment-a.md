# Experiment A dataset protocol 1.0

Milestone 3B revision 1.1: use separate planned collection windows before retrieval.
Populate actual observation times only from collected records, never the plan.
Possible duplicates are warnings without automatic exclusion; authoritative
verified duplicates need an explicitly recorded representative under this protocol.
Baseline source-declared identifiers do not need two reviewers; newly asserted
cross-record equivalence does. Identity-policy revision 1.1 takes precedence.

Status: design for review; no frame acquisition, verification or collection yet.
Estimand: **Verified retrieval coverage under the recorded search strategy** for
the sampled recent-preprint frame, conditional on usable provider responses.
This is cross-sectional coverage by paper age, not indexing latency or a census
of provider database presence. NOT_FOUND is a valid empty search, not proof of
database absence or fabrication. Provider indexing scopes differ.

## Frame and selection

Use one explicitly bounded initial frame: arXiv records with primary category
cs.CL, first publicly available 1–60 UTC calendar days before reference date R.
Include English metadata for the initial protocol; record language verification
method and excluded/uncertain cases. Findings generalize only to this frame and
strategy, not all fields, languages or academic citations. Freeze repository
release/source inventory, acquisition timestamp, query/selection specification,
source hashes and frame completeness limitations before sampling. Do not define
the frame by whether OpenAlex or Crossref returns a record.

R is the planned UTC collection-end date, also required by the current report
validator to equal the actual UTC collection-end date. If collection slips to a
different date, issue a new frame/protocol run version; do not relabel previously
collected observations or silently recompute cohorts. Partial observations remain
in their original run with limitations.

Age = R minus the verified first-public-preprint UTC date, in calendar days.
Inclusive cohorts are 1–7, 8–14, 15–30 and 31–60. Day zero, older/future records,
revisions mistakenly used as first releases, missing/unverified dates and records
outside the frozen frame have explicit exclusion reasons. ArXiv v1 submission
time is not automatically its first public announcement time. Preserve both when
available; verify public release/announcement with authoritative repository
evidence. If only a submission time can be verified, mark the public date pending
and exclude from age analysis. Never substitute year, latest-version date,
Crossref deposit date or provider indexed timestamp.

One record per base arXiv scholarly source. Deduplicate known aliases using
verified identity evidence before sampling; uncertain cross-record duplication is
flagged and not silently collapsed. Keep a reproducible screening ledger for all
frame members with eligibility and reasons. Resolve eligibility before sampling
where feasible. In each cohort sort eligible base IDs lexicographically, then rank
by SHA-256 of the UTF-8 string `citeprobe-A-v1|seed=0|<base-id>` (digest then ID tie
break). Select the first n, and retain the ordered reserve list. Never replace a
paper because retrieval is poor, identifiers are absent from provider results, or
identity adjudication is difficult. Late source-verification exclusions use the
next prespecified reserve with an auditable reason; report both counts. Do not
replace provider errors or identity-uncertain returned candidates.

## Sample sizes and collection

Pilot: 40 distinct original papers, 10 per cohort. Expansion target: 200, 50 per
cohort, including pilot papers only if the same frozen run design actually permits
it; otherwise keep waves separate. These are feasibility/design choices, not
power guarantees. If fewer eligible sources exist, retain the shortfall rather
than silently broadening the category/date range. Equal cohort allocation does
not estimate frame-wide prevalence without separately approved weighting; report
cohorts separately and label any combined result as equally allocated sample
performance. No new weighting formula is introduced.

Use one frozen metadata-only canonical query per paper per provider, top five,
OpenAlex and Crossref. Preserve the current title + complete author-name sequence
+ year query construction; do not tune it to pilot outcomes. Changes require a
new strategy/run. Nominal one-attempt request budgets are 80 for the pilot and
400 for the target; frame acquisition and identity verification have separate,
explicitly approved budgets. No live authorization is granted here.

Default collection window is 24 hours; plan paired provider queries for each paper
close together using a seeded source order, fixed software/configuration, provider
limits and credentials kept out of artifacts. A longer window requires a
documented explicit override of max_collection_hours. Preserve all actual request
times, source order and failures; do not silently discard observations outside
the default window. Unoverridden overruns remain diagnostic in the current
reporter. Report reference-date cohorts and actual per-provider lookup times;
elapsed time can change exposure even when the reference cohort is fixed.

Freeze retry policy and maximum attempt budget before authorization; propose one
attempt for this design pilot. A future retry-enabled run is a new disclosed
configuration. No automatic replacement/recollection of failed observations.

## Evaluation and uncertainty

Apply identity-policy.md and unchanged Part 3 metrics. Report per cohort/provider:
Recall@1 and @5 with evidence bounds, valid empty retrievals, incorrect top-one
bounds, identity-undetermined rate, operational outcomes, all denominators and
distinct source counts. API failures are outside retrieval denominators and are
reported separately. Equal response opportunity is not guaranteed by merely
sharing source sets: retain outcome-specific paired retrieval inventories.

Observed, simulated and unknown-origin inputs are separate. Only explicitly
observed inputs with complete manifests qualify for empirical reporting.
Never turn null estimates into zero. Use descriptive results at 10 sources per
cohort. Optional source-cluster bootstrap at expansion uses the same original IDs
for paired providers; off by default, seed 0, 2,000 replicates, 95% intervals and
minimum 30 eligible distinct sources per estimate, subject to current suppression
rules. Identity evidence bounds are not confidence intervals. No significance
tests or indexing-latency conclusions.
