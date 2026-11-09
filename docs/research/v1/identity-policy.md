# CiteProbe identity policy 1.0

## Milestone 3B clarification revision 1.1

The following approved rules supersede conflicting wording below. Translations
are distinct derivative works by default and never automatically SAME_WORK.
Authoritatively documented same-language republications or versions may qualify;
unclear derivative relationships remain UNDETERMINED.

New cross-identifier/cross-record mappings require two independent reviewer
approvals. Direct identifiers explicitly declared by the original authoritative
source may be baseline verified identifiers without two reviewers; record the
source and actual verification time. Any conflicting evidence requires adjudication.

Classify duplicate evidence separately as VERIFIED_DUPLICATE (authoritative
identity evidence) or POSSIBLE_DUPLICATE (nonconclusive evidence). Possible
duplicates remain eligible and are never automatically merged or excluded.
Verified duplicates need an explicit sampling representative and recorded reason.
Pre-collection windows are planned, not observed: actual timestamps exist only
after collection and must never be filled from plans.

Status: normative policy proposed for adoption in Milestone 3A review. No empirical
collection is authorized by this document. Scope: work-level identity for the
existing Part 3 evaluator; no metric or retrieval changes.

## Decision unit and labels

Judge each returned candidate against its verified original citation, including
when the search used mutated metadata. SAME_WORK maps to evaluator CORRECT;
DIFFERENT_WORK maps to INCORRECT; UNDETERMINED remains UNDETERMINED. These are
identity judgments, not assessments of publication legitimacy, fabrication,
quality, licensing, or provider reliability.

SAME_WORK requires a safely normalized verified identifier match or an explicit,
provenance-backed identity mapping. Where material contradictory evidence exists,
do not accept a mechanical positive match until the contradiction is adjudicated.
DIFFERENT_WORK requires affirmative authoritative evidence of separate scholarly
content, not failure to prove equivalence. Missing, ambiguous, inaccessible,
malformed or conflicting evidence yields UNDETERMINED. A failed verification
request is unavailable evidence, never negative identity evidence.

Never infer SAME_WORK solely from matching titles, authors, abstracts, DOI
prefixes, search scores, topics, shared URLs, or combinations of those metadata
matches. Never infer DIFFERENT_WORK solely from different identifiers, years,
titles or author lists. Such discrepancies identify review priorities.

## Sufficient evidence

Accept a direct identifier match to independently verified ground truth unless
there is credible conflicting evidence. Otherwise require one of:

1. An authoritative repository record explicitly naming its issued DOI or linking
   its preprint identifier to the publication identifier.
2. An original publisher/proceedings record explicitly identifying the preprint
   as the same work, with the candidate publication identifier established.
3. A documented curator comparison of authoritative scholarly content establishing
   continuity of the work, supported by version history and an explicit chain of
   source identifiers. This route requires two independent reviewers and a
   recorded rationale; bibliographic similarity alone is insufficient.

A registry is authoritative about the metadata it serves, not automatically
about the truth or authorization of every depositor claim. Capture the asserted
relationship, who asserted it, and whether an original repository/publisher
corroborates the bridge. A citation/reference to a paper does not establish that
the citing record is that paper. Automated transitive closure is not evidence.

For DIFFERENT_WORK, inspect authoritative content/records identifying a distinct
contribution or derivative, and record the substantive reason. Overlapping
authors, shared data or a similar title do not prevent separate-work identity.
Do not use a different-work mapping merely to force an uncertain result negative.

## Versions, aliases, duplicates and derivatives

Preprint and published versions may be SAME_WORK when the bridge is verified and
the core contribution is continuous. Version-specific text need not be identical.
An extended sequel or materially new contribution is not automatically equivalent.
If extension versus revision cannot be resolved, retain UNDETERMINED.

Normalize DOI resolver wrappers and ASCII case, and arXiv wrappers/version suffixes
using the existing safe normalizers. Removing an arXiv version suffix establishes
the benchmark's base-record identity, not identical content at every version.
Do not synthesize DOI aliases from patterns: verify each on an authoritative
record. A DOI prefix identifies neither a scholarly work nor its legitimacy.

Treat DOI deposits as provider records. A declared is-version-of/has-version
cluster may be recorded as an asserted cluster without establishing any member's
equivalence to an external arXiv target. Verify every bridge used in an identity
mapping; do not assign a target identity to an entire cluster by metadata overlap.
Each candidate needs a supported decision, even if several share evidence.

Translations are distinct derivatives by default, even if the scientific content
is equivalent. Do not automatically map translations to SAME_WORK. Summaries,
reviews, replications and explanatory reproductions are not automatically the
original work. Explicitly documented same-language republications or versions may
qualify when authoritative evidence establishes identity. Unclear relationships
stay UNDETERMINED. Licensing/authorization remains a separate claim.
Unverified mirrored or copied metadata is UNDETERMINED, not automatically a
legitimate version, DIFFERENT_WORK, or fabricated record.

Preserve all original provider ranks and duplicate records. Two verified aliases
within top K produce one per-lookup hit; never shift ranks by deduplication. Keep
cluster assertions separate from candidate judgments and from original-paper
clusters used for statistical resampling.

## Provenance and adjudication

Maintain a versioned sidecar evidence ledger: target ID, provider candidate ID,
normalized identifiers, proposed relation, evidence URL and record ID, retrieved
UTC timestamp, review UTC timestamp, relevant excerpt/field, evidence-file hash,
reviewer pseudonymous ID, rationale, disagreement, and final disposition. Do not
store credentials, personal contact details, PDFs or unnecessary page snapshots.
Keep retrieval time distinct from verification/review time. Missing evidence is
explicitly pending and has no fabricated verified timestamp.

Freeze baseline aliases before retrieval. Apply a fixed review order to all
candidate records (provider, original source, rank), not only plausible successes.
Two reviewers independently approve newly asserted cross-identifier/cross-record
positive and negative mappings. Direct source-declared baseline identifiers are
exempt from this reviewer count, but not provenance or conflict checks. Record
single-review status if staffing is unavailable and keep such additions pending
for the primary analysis. A third adjudicator resolves disagreements; otherwise
UNDETERMINED. Reviewers should not see aggregate provider metrics while deciding.
Disclose that source metadata and provider identity may still be visible.

Record a prospective finite verification budget and an equal evidence procedure
across providers/conditions; budget exhaustion leaves unknowns. Evidence verified
after retrieval must be labeled post-retrieval ascertainment. Publish original
and enriched evaluation versions, complete unresolved inventories and mapping
fingerprints. Never edit the original lookup bundle or a prior evaluation.

Only verified same_work/different_work entries enter IdentityMappings. Pending
and disputed decisions stay in the ledger. The current schema has one provenance
object per mapping: keep multiple corroborating sources in the ledger. Before
evaluation, check conflicting mappings and candidate identifiers. If a material
conflict cannot be represented safely by existing contracts, stop that evaluation
bundle pending adjudication; do not silently drop a candidate or fabricate a
negative mapping. A future explicit conflict override requires separate approval.

Identity mappings and evidence never enter metadata-only retrieval. Resolver
adapters receive only the intended search metadata. Canonical and mutated IDs are
evaluation references only. Preserve identifier-assisted searches separately.

## Binding Milestone 2 example

The authoritative arXiv record explicitly lists 10.48550/arXiv.1706.03762; that alias
is verified. It was not retrieved and cannot count as a hit. The five Crossref
10.65215 records share title, authors, abstract, primary resource and declared
version relationships. Their external target bridge remains unverified: all five
stay UNDETERMINED. This policy does not retroactively relabel them.
