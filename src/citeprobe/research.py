"""Pure offline validation and sampling; no clients, searches or identity heuristics."""

import hashlib
import itertools
from datetime import UTC, date

from citeprobe.identity import citation_identifiers, normalize_identifier
from citeprobe.lookup_inputs import canonical_tasks, fingerprint, mutation_tasks
from citeprobe.models import Dataset, MutationBatch
from citeprobe.mutations import generate_mutations
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.research_models import IdentityClaim, ResearchManifest, SampleRow, SamplingPlan
from citeprobe.resolution_models import LookupBundle

COHORTS = ("1-7", "8-14", "15-30", "31-60")
STRATA = ("doi_only", "arxiv_only", "dual")


def cohort(reference: date, publication: date) -> str | None:
    age = (reference - publication).days
    for low, high in ((1, 7), (8, 14), (15, 30), (31, 60)):
        if low <= age <= high:
            return f"{low}-{high}"
    return None


def manifest_digest(manifest: ResearchManifest) -> str:
    return fingerprint(manifest.model_dump(mode="json", exclude={"manifest_fingerprint"}))


def claim_keys(claim: IdentityClaim) -> set[str]:
    keys = {normalize_identifier(identifier) for identifier in claim.identifiers}
    if None in keys or len(keys) != len(claim.identifiers):
        raise ValueError("Invalid or duplicate claim identifiers")
    return {key.replace("crossref:", "doi:", 1) for key in keys if key is not None}


def validate_research(
    dataset: Dataset,
    manifest: ResearchManifest,
    *,
    mutations: MutationBatch | None = None,
    bundles: tuple[LookupBundle, ...] = (),
) -> tuple[str, ...]:
    if manifest.manifest_fingerprint != manifest_digest(manifest):
        raise ValueError("Manifest fingerprint mismatch")
    if (
        manifest.dataset_version != dataset.dataset_version
        or manifest.dataset_fingerprint != fingerprint(dataset.model_dump(mode="json"))
    ):
        raise ValueError("Dataset version/fingerprint mismatch")
    originals = {c.citation_id: c for c in dataset.citations}
    papers = {p.citation_id: p for p in manifest.papers}
    sources = {s.evidence_id: s for s in manifest.sources}
    claims = {c.claim_id: c for c in manifest.identity_claims}
    if (
        set(papers) != set(originals)
        or len(papers) != len(manifest.papers)
        or len(sources) != len(manifest.sources)
        or len(claims) != len(manifest.identity_claims)
    ):
        raise ValueError("Missing or duplicate paper/source/claim inventory")
    if (
        manifest.frame_evidence_id not in sources
        or sources[manifest.frame_evidence_id].provenance != manifest.frame_source
        or manifest.frame_source.verification_status != "verified"
    ):
        raise ValueError("Invalid verified frame provenance")
    if sources[manifest.frame_evidence_id].evidence_sha256 != manifest.frame_snapshot_sha256:
        raise ValueError("Frame snapshot fingerprint mismatch")
    for source in manifest.sources:
        if source.origin != manifest.origin:
            raise ValueError("Mixed evidence origins")
        if source.provenance.verified_at and source.retrieved_at > source.provenance.verified_at:
            raise ValueError("Verification precedes evidence retrieval")
    allowed_groups = COHORTS if manifest.experiment == "recent-preprints" else STRATA
    if set(manifest.target_per_group) != set(allowed_groups):
        raise ValueError("Targets must explicitly inventory all experiment groups")
    if manifest.experiment == "recent-preprints":
        if (
            manifest.reference_date is None
            or manifest.reference_date != manifest.planned_finished_at.astimezone(UTC).date()
        ):
            raise ValueError("Reference date must equal planned UTC collection-end date")
    elif manifest.reference_date is not None:
        raise ValueError("Experiment B cannot use age-cohort reference dates")
    positive = {key: citation_identifiers(c) for key, c in originals.items()}
    negative: dict[str, set[str]] = {key: set() for key in originals}
    for claim in manifest.identity_claims:
        if claim.citation_id not in originals or claim.conflict:
            raise ValueError("Unknown target or conflicting identity claim")
        if len(set(claim.evidence_ids)) != len(claim.evidence_ids):
            raise ValueError("Duplicate claim evidence")
        evidence = [sources[key] for key in claim.evidence_ids if key in sources]
        if len(evidence) != len(claim.evidence_ids):
            raise ValueError("Missing identity evidence")
        keys = claim_keys(claim)
        if claim.relation == "undetermined":
            continue  # Recorded, but never accepted into verified identity inventories.
        if any(s.provenance.verification_status != "verified" for s in evidence):
            raise ValueError("Unverified identity evidence")
        if not any(s.authority in {"original_repository", "original_publisher"} for s in evidence):
            raise ValueError("Depositor metadata alone cannot establish identity")
        if claim.relation == "same_work" and claim.expression in {
            "translation",
            "derivative",
            "unclear",
        }:
            raise ValueError("Unsupported derivative or translation equivalence")
        if claim.basis == "source_declared":
            if claim.relation != "same_work" or not any(
                "declared_identifiers" in s.supports for s in evidence
            ):
                raise ValueError("Baseline identifiers require explicit authoritative declaration")
        else:
            reviewers = [r.reviewer_id for r in claim.reviews]
            if (
                len(set(reviewers)) != len(reviewers)
                or len(reviewers) < 2
                or any(r.decision != "approve" for r in claim.reviews)
            ):
                raise ValueError("New identity mapping requires two independent approvals")
            if any(r.reviewed_at < max(s.retrieved_at for s in evidence) for r in claim.reviews):
                raise ValueError("Review precedes identity evidence")
        (positive if claim.relation == "same_work" else negative)[claim.citation_id].update(keys)
    for citation_id in originals:
        if positive[citation_id] & negative[citation_id]:
            raise ValueError("Contradictory identity identifiers")
    for paper in manifest.papers:
        c = originals[paper.citation_id]
        if len(set(paper.evidence_ids)) != len(paper.evidence_ids):
            raise ValueError("Duplicate paper evidence")
        if any(key not in sources for key in paper.evidence_ids):
            raise ValueError("Missing paper provenance")
        if paper.decision == "exclude":
            if paper.exclusion_kind is None:
                raise ValueError("Exclusion must record its kind and reason")
            continue
        if paper.exclusion_kind is not None or c.provenance.verification_status != "verified":
            raise ValueError("Included paper has exclusion or unverified ground truth")
        evidence = [sources[key] for key in paper.evidence_ids]
        if any(s.provenance.verification_status != "verified" for s in evidence):
            raise ValueError("Included source evidence is pending")
        required = {"title", "authors", "year"}
        required.update(key for key in ("doi", "arxiv_id", "volume", "issue") if getattr(c, key))
        supported = {field for s in evidence for field in s.supports}
        if not required <= set(paper.verified_fields) <= supported:
            raise ValueError("Missing verified field provenance")
        if (
            c.doi
            and c.arxiv_id
            and not any(
                claim.citation_id == c.citation_id
                and claim.relation == "same_work"
                and citation_identifiers(c) <= claim_keys(claim)
                for claim in manifest.identity_claims
            )
        ):
            raise ValueError("Dual identifiers lack verified equivalence")
        if manifest.experiment == "recent-preprints":
            d = paper.public_date
            if (
                not c.arxiv_id
                or d is None
                or d.citation_id != c.citation_id
                or d.provenance.verification_status != "verified"
                or d.date_kind != "first_public_preprint"
                or paper.public_date_basis != "public_announcement"
                or "first_public_date" not in supported
                or not any(s.provenance == d.provenance for s in evidence)
            ):
                raise ValueError("Unverified first-public date or submission/revision substitution")
            assert manifest.reference_date is not None
            expected = cohort(manifest.reference_date, d.publication_date)
            if expected is None or expected != paper.cohort or paper.identifier_stratum:
                raise ValueError("Incorrect age-cohort boundary or experiment mixing")
        else:
            doi = any(key.startswith("doi:") for key in positive[c.citation_id])
            arxiv = any(key.startswith("arxiv:") for key in positive[c.citation_id])
            expected = "dual" if doi and arxiv else "doi_only" if doi else "arxiv_only"
            if paper.identifier_stratum != expected or paper.cohort is not None:
                raise ValueError("Identifier stratum differs from verified identity inventory")
    warnings: list[str] = []
    duplicate_ids: set[str] = set()
    verified_pairs: set[frozenset[str]] = set()
    duplicate_exclusions: set[str] = set()
    for duplicate in manifest.duplicates:
        ids = set(duplicate.citation_ids)
        if (
            duplicate.duplicate_id in duplicate_ids
            or len(ids) != len(duplicate.citation_ids)
            or not ids <= originals.keys()
        ):
            raise ValueError("Invalid duplicate inventory")
        duplicate_ids.add(duplicate.duplicate_id)
        if duplicate.category == "POSSIBLE_DUPLICATE":
            if duplicate.representative_id or duplicate.claim_ids:
                raise ValueError("Possible duplicate cannot merge or assert verified equivalence")
            warnings.append(f"POSSIBLE_DUPLICATE {duplicate.duplicate_id}: review only")
            continue
        if duplicate.representative_id not in ids:
            raise ValueError("Verified duplicate needs a recorded representative")
        if papers[duplicate.representative_id].decision != "include":
            raise ValueError("Verified duplicate representative must remain included")
        for left, right in itertools.combinations(sorted(ids), 2):
            for source_id in (left, right):
                if originals[source_id].provenance.verification_status != "verified" or not any(
                    sources[key].authority in {"original_repository", "original_publisher"}
                    and sources[key].provenance.verification_status == "verified"
                    for key in papers[source_id].evidence_ids
                ):
                    raise ValueError("Verified duplicate requires authoritative source evidence")
            if not positive[left] & positive[right]:
                raise ValueError("Verified duplicates lack authoritative identity bridge")
            verified_pairs.add(frozenset((left, right)))
        for claim_id in duplicate.claim_ids:
            if claim_id not in claims or claims[claim_id].relation != "same_work":
                raise ValueError("Duplicate references an unverified claim")
        for citation_id in ids - {duplicate.representative_id}:
            paper = papers[citation_id]
            if paper.decision != "exclude" or paper.exclusion_kind != "verified_duplicate":
                raise ValueError("Verified duplicate exclusion/representative decision missing")
            duplicate_exclusions.add(citation_id)
    for paper in manifest.papers:
        if (
            paper.exclusion_kind == "verified_duplicate"
            and paper.citation_id not in duplicate_exclusions
        ):
            raise ValueError(
                "Duplicate exclusion has no verified evidence; possible duplicates stay eligible"
            )
    for left, right in itertools.combinations(sorted(originals), 2):
        if positive[left] & positive[right] and frozenset((left, right)) not in verified_pairs:
            raise ValueError(
                "Duplicate scholarly-source identifiers need an explicit verified decision"
            )
        a, other = originals[left], originals[right]
        if (a.title.casefold(), a.authors) == (other.title.casefold(), other.authors):
            warnings.append(f"POSSIBLE_DUPLICATE metadata: {left}, {right}; not merged")
    if mutations:
        expected_batch = generate_mutations(dataset, seed=mutations.seed)
        if (
            mutations.dataset_version != dataset.dataset_version
            or mutations.mutations != expected_batch.mutations
            or mutations.skipped != expected_batch.skipped
        ):
            raise ValueError("Invalid mutation applicability, parameters or skip inventory")
    tasks = list(canonical_tasks(dataset))
    if mutations:
        tasks.extend(mutation_tasks(dataset, mutations))
    secrets = {v for c in dataset.citations for v in (c.doi, c.arxiv_id, c.citation_id) if v}
    secrets.update(i.value for claim in manifest.identity_claims for i in claim.identifiers)
    secrets.update(task.source_id for task in tasks)
    for task in tasks:
        for adapter in (OpenAlex(), Crossref()):
            query = " ".join(adapter.request(task.metadata, None).params.values()).casefold()
            if any(secret.casefold() in query for secret in secrets):
                raise ValueError("Ground-truth/evaluation identifier leakage in query metadata")
    if bundles:
        from citeprobe.evaluation_integrity import validate_inputs
        from citeprobe.evaluation_models import EvaluationConfig

        validate_inputs(
            dataset,
            bundles,
            (mutations,) if mutations else (),
            EvaluationConfig(default_data_label=manifest.origin),
        )
        if any(r.strategy != "metadata" for b in bundles for r in b.results):
            raise ValueError("Research observations must be metadata-only")
        for b in bundles:
            for r in b.results:
                query = " ".join(r.request.params.values()).casefold()
                if any(secret.casefold() in query for secret in secrets):
                    raise ValueError("Saved provider request leaks identifiers")
    if manifest.stage == "post_collection":
        if set(manifest.observation_bundle_ids) != {
            fingerprint(b.model_dump(mode="json")) for b in bundles
        }:
            raise ValueError("Actual timestamps require the exact original bundle inventory")
        results = [r for b in bundles for r in b.results]
        if (
            not results
            or min(r.started_at for r in results) != manifest.actual_started_at
            or max(r.finished_at for r in results) != manifest.actual_finished_at
        ):
            raise ValueError("Actual timestamps differ from observations")
    elif bundles:
        raise ValueError("Observations cannot be attached to a pre-collection plan")
    return tuple(sorted(set(warnings)))


def sample_dataset(dataset: Dataset, manifest: ResearchManifest) -> SamplingPlan:
    warnings = validate_research(dataset, manifest)
    rows: list[SampleRow] = []
    shortfalls: dict[str, int] = {}
    prefix = "A" if manifest.experiment == "recent-preprints" else "B"
    for paper in manifest.papers:
        if paper.decision == "exclude":
            rows.append(
                SampleRow(
                    citation_id=paper.citation_id,
                    group=None,
                    disposition="excluded",
                    reason=paper.reason,
                    sampling_key=None,
                )
            )
    for group, count in sorted(manifest.target_per_group.items()):
        ranked: list[tuple[str, str]] = []
        for paper in manifest.papers:
            if paper.decision != "include" or (paper.cohort or paper.identifier_stratum) != group:
                continue
            key = hashlib.sha256(
                f"citeprobe-{prefix}-v1|seed={manifest.seed}|{paper.citation_id}".encode()
            ).hexdigest()
            ranked.append((key, paper.citation_id))
        for ordinal, (key, citation_id) in enumerate(sorted(ranked), 1):
            rows.append(
                SampleRow(
                    citation_id=citation_id,
                    group=group,
                    disposition="selected" if ordinal <= count else "reserve",
                    reason="Deterministic within-group rank",
                    sampling_key=key,
                    ordinal=ordinal,
                )
            )
        shortfalls[group] = max(0, count - len(ranked))
    plan = SamplingPlan(
        plan_fingerprint="0" * 64,
        manifest_fingerprint=manifest.manifest_fingerprint,
        dataset_fingerprint=manifest.dataset_fingerprint,
        seed=manifest.seed,
        origin=manifest.origin,
        rows=tuple(sorted(rows, key=lambda row: row.citation_id)),
        shortfalls=shortfalls,
        warnings=warnings,
    )
    return plan.model_copy(
        update={
            "plan_fingerprint": fingerprint(
                plan.model_dump(mode="json", exclude={"plan_fingerprint"})
            )
        }
    )
