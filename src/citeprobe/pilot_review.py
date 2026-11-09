"""Curator-verified v1 dates and identity-safe pilot selection; never benchmark lookups."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from citeprobe.evaluation_models import IdentityMapping, IdentityMappings
from citeprobe.evidence_extract import decoded_body
from citeprobe.evidence_io import json_bytes, verify_batch, write
from citeprobe.evidence_models import RawEvidence
from citeprobe.identity import IdentityIndex, citation_identifiers, normalize_identifier
from citeprobe.lookup_inputs import canonical_tasks, fingerprint
from citeprobe.models import Citation, Dataset, Provenance
from citeprobe.pilot_invariance import InvarianceAssessment, certificate, validate_assessment
from citeprobe.pilot_models import PilotFrame, PilotReview
from citeprobe.pilot_run import build_frame, load_run, response_body
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.research import cohort


def v1_date(bundle: Path, arxiv_id: str, origin: str) -> tuple[datetime | None, RawEvidence]:
    extracted = verify_batch(bundle)
    record = RawEvidence.model_validate_json((bundle / "request-001/record.json").read_bytes())
    if (
        len(extracted) != 1
        or record.origin != origin
        or record.request.url != "https://arxiv.org/abs/" + arxiv_id
        or record.request.source_kind != "arxiv_abstract"
    ):
        raise ValueError("v1 verification requires the exact authoritative abstract record")
    declared = extracted[0].payload.get("arxiv_id")
    if declared is not None and declared != arxiv_id:
        raise ValueError("Authoritative abstract declares a different arXiv identifier")
    value = extracted[0].payload.get("v1_submission")
    if (
        record.http_status != 200
        or not record.body_complete
        or declared is None
        or not isinstance(value, dict)
        or not isinstance(value.get("utc"), str)
    ):
        return None, record
    return datetime.fromisoformat(value["utc"]), record


def select_pilot(
    directory: Path,
    frame: PilotFrame,
    review: PilotReview,
    *,
    invariance: InvarianceAssessment | None = None,
) -> dict[str, object]:
    if (
        frame != build_frame(directory)
        or frame.frame_id != review.frame_id
        or frame.origin != review.origin
    ):
        raise ValueError("Review/frame/source fingerprint or origin mismatch")
    decisions = {d.source_id: d for d in review.decisions}
    if (
        frame.experiment == "mutation-robustness-pilot"
        and not review.identifier_inspection_protocol
    ):
        raise ValueError("B requires a uniform, recorded identifier-inspection procedure")
    if len(decisions) != len(review.decisions) or set(decisions) != set(frame.panel_ids):
        raise ValueError("Every fixed-panel member requires exactly one curator decision")
    if invariance is not None:
        validate_assessment(invariance, frame, review)
    run = load_run(directory)
    by_key = {r.key: (r, a) for r, a in zip(run.plan.requests, run.attempts, strict=True)}
    items = {i.source_id: i for i in frame.items}
    approved: list[Citation] = []
    groups: dict[str, str] = {}
    known_raw: dict[str, RawEvidence] = {}
    known_bodies: dict[str, str] = {}
    for source_id, decision in decisions.items():
        item = items[source_id]
        row, attempt = by_key[item.run_request_key]
        limit = 2_000_000
        if (directory / "resource-continuation.json").exists():
            from citeprobe.source_limits import recovery_limit

            limit = recovery_limit(row.request)
        source_body, record = response_body(
            directory / str(attempt.evidence_directory), row, frame.origin, decoded_limit=limit
        )
        known_raw[record.raw_body_sha256] = record
        known_bodies[record.raw_body_sha256] = source_body.casefold()
        if decision.reviewed_at < record.finished_at:
            raise ValueError("Curator review predates source collection")
        if decision.disposition == "pending" and invariance is None:
            raise ValueError("Pending verification cannot silently become eligible or excluded")
        if decision.v1_evidence_directory:
            if not item.candidate.arxiv_id:
                raise ValueError("v1 evidence attached to a non-arXiv record")
            timestamp, proof = v1_date(
                Path(decision.v1_evidence_directory), item.candidate.arxiv_id, frame.origin
            )
            known_raw[proof.raw_body_sha256] = proof
            known_bodies[proof.raw_body_sha256] = (
                decoded_body(
                    proof,
                    (Path(decision.v1_evidence_directory) / "request-001/body.bin").read_bytes(),
                )
                .decode(proof.character_encoding or "utf-8-sig")
                .casefold()
            )
            if decision.reviewed_at < proof.finished_at:
                raise ValueError("v1 review precedes raw evidence")
            if timestamp is None and (
                decision.disposition != "exclude"
                or decision.exclusion_kind != "unverified_evidence"
                or decision.v1_verified
                or decision.v1_submitted_at is not None
            ):
                raise ValueError("Unavailable v1 evidence must remain explicitly unverified")
            if timestamp is not None and timestamp != item.candidate.submitted_at:
                raise ValueError("API/v1 submission contradiction: stop, do not replace the paper")
            if timestamp is not None and decision.v1_submitted_at != timestamp:
                raise ValueError("Curator v1 date differs from retained authoritative evidence")
        if decision.disposition == "pending":
            if (
                not decision.v1_evidence_directory
                or decision.v1_submitted_at is None
                or decision.identity_verified
                or decision.exclusion_kind is not None
            ):
                raise ValueError(
                    "Pending reserve needs corroborated v1 evidence and no identity approval"
                )
            assert frame.reference_date is not None
            group = cohort(frame.reference_date, decision.v1_submitted_at.astimezone(UTC).date())
            if group != item.group:
                raise ValueError("Pending reserve cohort differs from authoritative v1 evidence")
            groups[source_id] = group
            continue
        if decision.disposition == "exclude":
            if decision.exclusion_kind is None:
                raise ValueError(
                    "Exclusion needs an explicit eligibility/evidence/duplicate reason"
                )
            continue
        c = decision.canonical
        source = item.candidate
        if (
            not c
            or decision.language != "en"
            or not decision.metadata_verified
            or not decision.identity_verified
            or decision.exclusion_kind
        ):
            raise ValueError(
                "Included canonical facts, language and identity require curator approval"
            )
        if (
            c.title,
            tuple(" ".join(filter(None, (a.given, a.family))) for a in c.authors),
            c.year,
            c.volume,
            c.issue,
        ) != (source.title, source.authors, source.year, source.volume, source.issue):
            raise ValueError(
                "Canonical metadata differs from frozen source; retain evidence in a new version"
            )
        if (source.arxiv_id and c.arxiv_id != source.arxiv_id) or (
            source.doi and c.doi != source.doi
        ):
            raise ValueError("Canonical source identifiers cannot be changed")
        if frame.experiment == "submission-age-pilot":
            if (
                not decision.v1_verified
                or not decision.v1_evidence_directory
                or not decision.v1_submitted_at
            ):
                raise ValueError(
                    "A-S1 requires curator-verified authoritative v1 evidence, never API-only dates"
                )
            assert frame.reference_date is not None
            group = cohort(frame.reference_date, decision.v1_submitted_at.astimezone(UTC).date())
            if group != item.group:
                raise ValueError("Verified v1 date contradicts the prespecified cohort/day")
            groups[source_id] = group
        approved.append(
            Citation(
                **c.model_dump(),
                citation_id=source_id,
                provenance=Provenance(
                    source_url=record.final_url or record.request.url,
                    record_identifier=source.source_record_id,
                    verification_status="verified",
                    verified_at=decision.reviewed_at,
                ),
            )
        )
    if not approved:
        if invariance is not None:
            raise ValueError("Invariance cannot replace curator approvals")
        if review.claims or review.sources or review.duplicates:
            raise ValueError("No included paper can support identity/duplicate assertions")
        names = (
            ("1-7", "8-14", "15-30", "31-60")
            if frame.experiment == ("submission-age-pilot")
            else ("doi_only", "arxiv_only", "dual")
        )
        return {
            "schema_version": "1.0",
            "experiment": frame.experiment,
            "date_basis": run.plan.date_basis,
            "origin": frame.origin,
            "frame_id": frame.frame_id,
            "review_fingerprint": fingerprint(review.model_dump(mode="json")),
            "selected_source_ids": [],
            "groups": {},
            "shortfalls": dict.fromkeys(names, 2),
            "ready_to_freeze": False,
            "dataset": None,
            "identity_mappings": None,
        }
    dataset = Dataset(
        dataset_version="pilot-reviewed-" + frame.frame_id[:16], citations=tuple(approved)
    )
    evidence = {s.evidence_id: s for s in review.sources}
    if len(evidence) != len(review.sources):
        raise ValueError("Duplicate identity-evidence records")
    if len({c.claim_id for c in review.claims}) != len(review.claims):
        raise ValueError("Duplicate identity claim IDs")
    for evidence_source in review.sources:
        raw = known_raw.get(evidence_source.evidence_sha256)
        if (
            raw is None
            or evidence_source.origin != frame.origin
            or evidence_source.retrieved_at != raw.finished_at
            or str(evidence_source.provenance.source_url) != raw.final_url
            or evidence_source.provenance.verified_at is None
            or evidence_source.provenance.verified_at < raw.finished_at
        ):
            raise ValueError("Identity evidence is not linked to this retained source inventory")
    mappings = []
    for claim in review.claims:
        if claim.citation_id not in {c.citation_id for c in approved}:
            raise ValueError("Identity claim must target an included, verified paper")
        if claim.conflict:
            raise ValueError("Identity conflict needs adjudication")
        if claim.relation == "undetermined":
            continue
        proofs = [evidence[k] for k in claim.evidence_ids if k in evidence]
        if len(proofs) != len(claim.evidence_ids) or not proofs:
            raise ValueError("Missing identity provenance")
        if any(p.provenance.verification_status != "verified" for p in proofs) or not any(
            p.authority in {"original_repository", "original_publisher"} for p in proofs
        ):
            raise ValueError("Unverified or nonauthoritative identity mapping")
        if claim.relation == "same_work" and claim.expression in {
            "translation",
            "derivative",
            "unclear",
        }:
            raise ValueError("Unsupported translation/derivative equivalence")
        if claim.basis == "source_declared":
            if claim.relation != "same_work" or not any(
                "declared_identifiers" in p.supports for p in proofs
            ):
                raise ValueError("Baseline alias must be an explicit authoritative declaration")
            # An assertion in a review is insufficient when the frozen source never declares it.
            declarations = [known_bodies[p.evidence_sha256] for p in proofs]
            if any(
                not any(i.value.casefold() in body for body in declarations)
                for i in claim.identifiers
            ):
                raise ValueError(
                    "Source-declared alias is absent from retained authoritative bytes"
                )
            original = items[claim.citation_id].candidate
            allowed = set()
            if original.doi:
                allowed.add("doi:" + original.doi.lower())
            if original.arxiv_id:
                allowed.add("arxiv:" + original.arxiv_id)
                alias = "10.48550/arxiv." + original.arxiv_id
                if any(
                    known_raw[p.evidence_sha256].request.url
                    == "https://arxiv.org/abs/" + original.arxiv_id
                    and alias in known_bodies[p.evidence_sha256]
                    for p in proofs
                ):
                    allowed.add("doi:" + alias)
            if not {normalize_identifier(i) for i in claim.identifiers} <= allowed:
                raise ValueError("Baseline identity is not declared by this source record")
        elif (
            len({r.reviewer_id for r in claim.reviews}) < 2
            or len({r.reviewer_id for r in claim.reviews}) != len(claim.reviews)
            or any(
                r.decision != "approve" or r.reviewed_at < max(p.retrieved_at for p in proofs)
                for r in claim.reviews
            )
        ):
            raise ValueError("New identity mapping requires two independent approving reviewers")
        mappings.append(
            IdentityMapping(
                citation_id=claim.citation_id,
                relation=claim.relation,
                identifiers=claim.identifiers,
                provenance=proofs[0].provenance,
            )
        )
    identities = IdentityMappings(dataset_version=dataset.dataset_version, mappings=tuple(mappings))
    index = IdentityIndex(dataset, identities)
    for citation in dataset.citations:
        original = items[citation.citation_id].candidate
        keys = set()
        for namespace, value in (("arxiv", original.arxiv_id), ("doi", original.doi)):
            if value:
                from citeprobe.evaluation_models import IdentityIdentifier

                key = normalize_identifier(IdentityIdentifier(namespace=namespace, value=value))
                if key:
                    keys.add(key)
        canonical = citation_identifiers(citation)
        if len(canonical) > 1 and not any(
            claim.citation_id == citation.citation_id
            and claim.relation == "same_work"
            and canonical <= {normalize_identifier(i) for i in claim.identifiers}
            for claim in review.claims
        ):
            raise ValueError("Dual canonical identifiers need an explicit verified bridge")
        if canonical - keys and not any(
            claim.citation_id == citation.citation_id
            and claim.relation == "same_work"
            and keys | canonical <= {normalize_identifier(i) for i in claim.identifiers}
            for claim in review.claims
        ):
            raise ValueError("Added source identifier lacks a verified bridge")
    for left in dataset.citations:
        for right in dataset.citations:
            if (
                left.citation_id < right.citation_id
                and index.same[left.citation_id] & index.same[right.citation_id]
            ):
                raise ValueError("Duplicate scholarly works cannot both remain included")
    covered_duplicates = set()
    for duplicate in review.duplicates:
        members = set(duplicate.citation_ids)
        if not members <= set(frame.panel_ids) or len(members) != len(duplicate.citation_ids):
            raise ValueError("Invalid duplicate review inventory")
        if duplicate.category == "POSSIBLE_DUPLICATE":
            if duplicate.representative_id:
                raise ValueError("Possible duplicates cannot automatically merge")
            continue
        representative = duplicate.representative_id
        if representative not in index.same:
            raise ValueError("Verified duplicate representative must remain included")
        for member in members - {representative}:
            decision = decisions[member]
            original_duplicate = items[member].candidate
            raw_keys = (
                {f"arxiv:{original_duplicate.arxiv_id}"} if original_duplicate.arxiv_id else set()
            )
            if original_duplicate.doi:
                raw_keys.add("doi:" + original_duplicate.doi.lower())
            if (
                not index.same[representative] & raw_keys
                or not decision.identity_verified
                or decision.disposition != "exclude"
                or decision.exclusion_kind != "verified_duplicate"
            ):
                raise ValueError("Duplicate exclusion lacks verified identity and explicit review")
            covered_duplicates.add(member)
    if any(
        d.exclusion_kind == "verified_duplicate" and d.source_id not in covered_duplicates
        for d in review.decisions
    ):
        raise ValueError("Possible/unrecorded duplicate cannot be excluded as verified")
    if frame.experiment == "mutation-robustness-pilot":
        for c in dataset.citations:
            keys = index.same[c.citation_id]
            doi = any(k.startswith("doi:") for k in keys)
            arxiv = any(k.startswith("arxiv:") for k in keys)
            groups[c.citation_id] = "dual" if doi and arxiv else "doi_only" if doi else "arxiv_only"
    selected = []
    shortfalls = {}
    group_names = (
        ("1-7", "8-14", "15-30", "31-60")
        if frame.experiment == "submission-age-pilot"
        else ("doi_only", "arxiv_only", "dual")
    )
    for group in group_names:
        prefix = (
            "citeprobe-A-submission-v1|seed=0|"
            if frame.experiment == "submission-age-pilot"
            else "citeprobe-B-v1|seed=0|"
        )
        ordered = sorted(
            (c.citation_id for c in dataset.citations if groups[c.citation_id] == group),
            key=lambda key: (
                hashlib.sha256(
                    (
                        prefix
                        + (
                            key.removeprefix("arxiv:")
                            if frame.experiment == "submission-age-pilot"
                            else key
                        )
                    ).encode()
                ).hexdigest(),
                key,
            ),
        )
        selected.extend(ordered[:2])
        shortfalls[group] = max(0, 2 - len(ordered))
    secrets = {v for c in dataset.citations for v in (c.citation_id, c.doi, c.arxiv_id) if v}
    secrets.update(i.value for claim in review.claims for i in claim.identifiers)
    for task in canonical_tasks(dataset):
        for adapter in (OpenAlex(), Crossref()):
            query = " ".join(adapter.request(task.metadata, None).params.values()).casefold()
            if any(secret.casefold() in query for secret in secrets):
                raise ValueError("Ground-truth identifier leakage in metadata-only query")
    invariance_proof = (
        certificate(invariance, frame, review, groups, selected, index) if invariance else None
    )
    chosen = Dataset(
        dataset_version=dataset.dataset_version,
        citations=tuple(c for c in dataset.citations if c.citation_id in selected),
    )
    return {
        "schema_version": "1.1" if invariance else "1.0",
        **({"selection_invariance": invariance_proof} if invariance else {}),
        "experiment": frame.experiment,
        "date_basis": run.plan.date_basis,
        "origin": frame.origin,
        "frame_id": frame.frame_id,
        "review_fingerprint": fingerprint(review.model_dump(mode="json")),
        "selected_source_ids": selected,
        "groups": groups,
        "shortfalls": shortfalls,
        "ready_to_freeze": not any(shortfalls.values()),
        "dataset": chosen.model_dump(mode="json"),
        "identity_mappings": identities.model_copy(
            update={"mappings": tuple(m for m in identities.mappings if m.citation_id in selected)}
        ).model_dump(mode="json"),
    }


def freeze_pilot(
    directory: Path,
    source_run: Path,
    frame: PilotFrame,
    review: PilotReview,
    *,
    invariance: InvarianceAssessment | None = None,
) -> None:
    result = select_pilot(source_run, frame, review, invariance=invariance)
    if not result["ready_to_freeze"]:
        raise ValueError(
            "Pilot target shortfall: preserve selection report; no automatic expansion"
        )
    directory.mkdir(exist_ok=False)
    for name, value in (
        ("selection", result),
        ("frame", frame.model_dump(mode="json")),
        ("review", review.model_dump(mode="json")),
        ("dataset", result["dataset"]),
        ("identity-mappings", result["identity_mappings"]),
    ):
        write(directory / f"{name}.json", json_bytes(value))
    if invariance is not None:
        write(
            directory / "selection-invariance.json", json_bytes(invariance.model_dump(mode="json"))
        )
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    write(
        directory / "integrity.json",
        json_bytes(
            {"schema_version": "1.0", "files": files, "source_run": str(source_run.resolve())}
        ),
    )


def verify_pilot(directory: Path, *, anchor: str | None = None) -> None:
    if anchor and hashlib.sha256((directory / "integrity.json").read_bytes()).hexdigest() != anchor:
        raise ValueError("External pilot integrity anchor mismatch")
    integrity = json.loads((directory / "integrity.json").read_bytes())
    extra = (
        {"selection-invariance.json"}
        if (directory / "selection-invariance.json").exists()
        else set()
    )
    if (
        set(p.name for p in directory.iterdir())
        != {
            "frame.json",
            "review.json",
            "selection.json",
            "integrity.json",
            "dataset.json",
            "identity-mappings.json",
        }
        | extra
    ):
        raise ValueError("Frozen pilot inventory changed")
    for name in ("frame", "review", "selection", "dataset", "identity-mappings"):
        filename = name + ".json"
        if (
            hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            != integrity["files"][filename]
        ):
            raise ValueError("Frozen pilot hash mismatch")
    frame = PilotFrame.model_validate_json((directory / "frame.json").read_bytes())
    review = PilotReview.model_validate_json((directory / "review.json").read_bytes())
    invariance = None
    if extra:
        content = (directory / "selection-invariance.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != integrity["files"]["selection-invariance.json"]:
            raise ValueError("Frozen invariance assessment hash mismatch")
        invariance = InvarianceAssessment.model_validate_json(content)
    result = select_pilot(Path(integrity["source_run"]), frame, review, invariance=invariance)
    if (directory / "selection.json").read_bytes() != json_bytes(result):
        raise ValueError("Frozen pilot no longer reproduces")
    for filename, key in (
        ("dataset.json", "dataset"),
        ("identity-mappings.json", "identity_mappings"),
    ):
        if (directory / filename).read_bytes() != json_bytes(result[key]):
            raise ValueError("Frozen Part 1/evaluator export differs from verified selection")
