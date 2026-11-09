# Milestone 3B: offline dataset infrastructure

Implemented without empirical acquisition, provider requests, benchmark execution
or changes to Milestone 2. Existing citation, resolution and evaluation schemas
and identity/metric semantics remain compatible. Policy clarifications are recorded
as research-policy revision 1.1 in docs/research/v1.

## Contracts

`research_models.py` adds a separate ResearchManifest with a dataset version/hash,
manifest hash, explicit origin, frame provenance/hash, protocol hash, planned
window, sampling targets/seed, full paper inventory, field evidence, claims,
reviews and duplicate decisions. Pre-collection plans cannot contain actual times
or observation IDs. Post-collection actual times must exactly match supplied
original lookup bundles; planned times are never copied into observations.

SourceEvidence records excerpts, retrieval time, verification provenance and
evidence hash. Review times are separate. Verification is a curator assertion:
schemas cannot establish that an arbitrary webpage is truthful, that two human
reviewers are genuinely independent, or that an origin label is truthful. Evidence
origins must agree throughout the ledger. A private reviewer identity registry or
authentication service is deliberately not introduced.

Included papers need verified canonical fields and supported field-level evidence.
A requires verified public-announcement dates, not submission/revision dates,
and correct 1–7/8–14/15–30/31–60 cohorts. B strata reflect the entire frozen verified
identifier inventory: a verified DOI alias can move an arXiv record to dual.
Dual canonical identifiers need an explicit verified bridge. Newly asserted
identity mappings require two distinct approving reviewer IDs and authoritative
evidence. Direct source-declared baseline aliases are exempt from two reviews.
Pending claims never augment identity inventories. Conflicts stop preflight;
translations/derivatives cannot silently become SAME_WORK.

Every frame citation needs an inclusion/exclusion reason. Possible duplicates
produce warnings; exact title/author agreement is a review signal only. Shared
verified identifiers require an explicit VERIFIED_DUPLICATE decision with a
representative and recorded duplicate exclusions. Different identifiers are never
automatically equated. Frame/source hashes are linked, but external source truth
and frame completeness still need curator review. The frame eligibility reason
records category/language/year screening; infrastructure does not infer these
facts from titles or acquire missing evidence.

`sample_dataset` uses the approved SHA-256 seed/source ranking within each group,
records selected, reserve and excluded rows, and reports shortfalls. All groups
must have explicit nonnegative integer targets. No automatic replacement workflow
exists: amend and version the screening ledger before retrieval and regenerate
the plan; never mutate a prior snapshot. Complete mutation/skip inventories can
be checked against algorithm 1, including both year directions. Query construction
is checked offline against known canonical/mapping/internal identifiers; saved
bundles additionally use existing Part 3 integrity checks. This intentionally
blocks metadata that literally embeds a known ground-truth identifier.

## CLI examples (synthetic fixtures only)

```powershell
citeprobe dataset-validate tests/fixtures/research-infrastructure/dataset.json --manifest tests/fixtures/research-infrastructure/manifest-a.json
citeprobe dataset-sample tests/fixtures/research-infrastructure/dataset.json --manifest tests/fixtures/research-infrastructure/manifest-a.json --output sample.json
citeprobe dataset-freeze tests/fixtures/research-infrastructure/dataset.json --manifest tests/fixtures/research-infrastructure/manifest-a.json --output frozen-synthetic
citeprobe dataset-verify frozen-synthetic
citeprobe dataset-verify frozen-synthetic --integrity-sha256 <externally-retained-hash>
```

Outputs must be new. `dataset-validate` optionally accepts `--mutations FILE` and
`--lookup-bundles FILE...` for provenance/mutation/request checks. A post-collection
manifest must supply the original bundles. Existing `validate` retains its old
schema-validation behavior; research safeguards require `dataset-validate`.

To author a manifest, calculate the canonical dataset fingerprint with existing
`lookup_inputs.fingerprint(dataset.model_dump(mode="json"))`. Construct the
ResearchManifest initially with a 64-zero fingerprint, then calculate
`research.manifest_digest(manifest)` and assign it using model validation. This
checksum is reproducibility metadata, not proof of source authenticity. Do not
manually invent evidence, timestamps or observed labels to satisfy validation.

## Frozen snapshots and limits

Snapshots contain the full screened frame (`dataset.json`), manifest, deterministic
selection plan and byte-level integrity inventory. The source dataset is never
rewritten. Freeze is exclusive and refuses existing directories; verify checks
inventory, hashes, source/manifest fingerprints and exact sampling replay.
Snapshots are logically immutable through these commands, not OS-enforced WORM
storage. Interrupted writes leave an invalid directory; verify rejects it and
freeze will not overwrite it. Preserve it for diagnosis instead of resuming edits.

Keep the printed integrity SHA-256 externally and pass it to verification to detect
coordinated replacement of all snapshot files. Internal checksums alone cannot
authenticate a maliciously replaced archive. There are no signatures. External
protocol hashes and evidence hashes are declarations unless their source files
are independently retained and checked. No PDFs/full webpage archives are needed.

The frame can contain reserves, exclusions and pending evidence. It is NOT a
ready-to-resolve selected dataset: do not pass snapshot dataset.json directly to
`resolve`. A collection planner/selected-task executor and stage-specific request
authorization remain Milestone 3C work. This milestone provides dataset support,
not a new research collector. Arbitrary review/adjudication overrides, network
evidence acquisition and empirical report generation are outside this change.

## Decisions still requiring approval before collection

- Exact authoritative frame releases and enumeration/announcement verification.
- Reviewer assignments and any disagreements requiring human adjudication.
- Frame shortfalls, protocol amendments or replacements, if needed.
- Provider attempt budgets, settings, collection schedule and actual execution.

Unknown returned identities are valid outcomes with evidence bounds; they do not
justify excluding otherwise eligible sampled papers. Milestone 2's unresolved
cluster remains unresolved, and its existing results are not relabeled.

## Verification results

Executed after the final source changes:

```text
python -m pytest -q -W error --basetemp .pytest-tmp/milestone-3b
341 passed in 20.66s
python -m ruff check .
All checks passed!
python -m ruff format --check .
74 files already formatted
python -m mypy
Success: no issues found in 44 source files
```

Both saved synthetic A/B manifests also passed `dataset-validate`. Tests include
sampling/reserves, cohort boundaries, provenance/origin failures, reviewer rules,
dual-identifier bridges, translations, pending claims, duplicate handling,
mutation/skip inventory, actual bundle timestamps, external integrity anchors,
tampering and CLI round trips. Existing evaluation regression tests passed as
part of the full suite. All 32 protected Milestone 2/canonical hashes in the
Milestone 3A baseline still match. No live requests or empirical collection ran.

During implementation, checks caught a runtime argparse annotation compatibility
error and type-inference/name-reuse issues; these were corrected before final
checks. No existing evaluation bug or changed identity judgment was discovered.
Duplicate validation also explicitly rejects excluding the recorded representative.

Metadata duplicate warnings currently use case-insensitive exact title plus
identical author tuples. This is intentionally nonconclusive and not an exhaustive
fuzzy duplicate detector; different spellings may need explicit review flags.
