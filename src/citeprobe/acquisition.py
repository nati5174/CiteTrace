"""Bounded evidence acquisition and deterministic offline review; no benchmark execution."""

import hashlib
from datetime import UTC, datetime
from time import monotonic

import httpx

from citeprobe.acquisition_models import (
    AcquisitionAudit,
    AcquisitionPlan,
    AcquisitionResponse,
    AcquisitionReviewItem,
    CuratorDecision,
)
from citeprobe.acquisition_sources import metadata_projection, source
from citeprobe.evaluation_models import DataLabel
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.research import sample_dataset
from citeprobe.research_models import ResearchManifest, SamplingPlan


async def collect(
    plan: AcquisitionPlan,
    client: httpx.AsyncClient,
    *,
    origin: DataLabel,
    authorization_reference: str,
) -> AcquisitionResponse:
    """One explicit request. The caller must supply a no-retry/no-redirect client."""
    if client.follow_redirects:
        raise ValueError("Acquisition redirects must be disabled")
    request = source(plan).request(plan)
    started = datetime.now(UTC)
    clock = monotonic()
    status: int | None = None
    error: str | None = None
    body_hash: str | None = None
    projection: str | None = None
    retry_after: str | None = None
    try:
        async with client.stream("GET", request.endpoint, params=request.params) as response:
            status = response.status_code
            header = response.headers.get("Retry-After")
            retry_after = header[:100] if header and header.isascii() else None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > 2_000_000:
                    raise ValueError("Source metadata exceeds acquisition bound")
                body.extend(chunk)
            body_hash = hashlib.sha256(body).hexdigest()
            if status == 200:
                projection = metadata_projection(body.decode("utf-8-sig"))
    except (httpx.HTTPError, ValueError) as exc:
        error = type(exc).__name__
    return AcquisitionResponse(
        origin=origin,
        plan=plan,
        request=request,
        started_at=started,
        finished_at=datetime.now(UTC),
        http_status=status,
        exception_type=error,
        response_body_sha256=body_hash,
        metadata_xml=projection,
        metadata_sha256=hashlib.sha256(projection.encode()).hexdigest() if projection else None,
        retry_after=retry_after,
        latency_ms=(monotonic() - clock) * 1000,
        authorization_reference=authorization_reference,
    )


def replay_acquisition(response: AcquisitionResponse) -> AcquisitionAudit:
    if response.request != source(response.plan).request(response.plan):
        raise ValueError("Acquisition request does not match its approved source plan")
    if (
        response.metadata_xml is not None
        and hashlib.sha256(response.metadata_xml.encode()).hexdigest() != response.metadata_sha256
    ):
        raise ValueError("Acquisition metadata fingerprint mismatch")
    warnings = ["Bounded discovery slice; not a verified or complete research sampling frame"]
    if (
        response.started_at < response.plan.planned_started_at
        or response.finished_at > response.plan.planned_finished_at
    ):
        warnings.append(
            "Actual acquisition is outside its planned window; times were not substituted"
        )
    items: list[AcquisitionReviewItem] = []
    total: int | None = None
    outcome = "API_ERROR"
    if response.exception_type and "Timeout" in response.exception_type:
        outcome = "TIMEOUT"
    elif response.http_status == 429:
        outcome = "RATE_LIMITED"
    elif response.http_status == 200 and not response.exception_type and response.metadata_xml:
        try:
            adapter = source(response.plan)
            records, total = adapter.records(response.metadata_xml)
            if total is not None and total < len(records):
                raise ValueError("Source count is inconsistent")
            for ordinal, record in enumerate(records[: response.plan.max_records], 1):
                issues = ["bibliographic_and_language_verification_required"]
                candidate = None
                try:
                    candidate = adapter.candidate(record)
                    if not candidate.doi and not candidate.arxiv_id:
                        issues.append("missing_persistent_identifier")
                    if response.plan.experiment == "recent-preprints":
                        issues.append("authoritative_first_public_date_required")
                    elif not 2018 <= candidate.year <= 2023:
                        issues.append("outside_experiment_B_year_frame")
                    if response.plan.source == "arxiv_atom":
                        issues.append("author_name_segmentation_requires_review")
                        if candidate.primary_category != "cs.CL":
                            issues.append("primary_category_not_verified_cs.CL")
                    if candidate.doi and candidate.arxiv_id:
                        issues.append("source_declared_identifier_bridge_requires_verification")
                except (ValueError, TypeError, KeyError):
                    issues.append("invalid_source_record")
                items.append(
                    AcquisitionReviewItem(
                        item_id=fingerprint(
                            {
                                "response": fingerprint(response.model_dump(mode="json")),
                                "ordinal": ordinal,
                            }
                        ),
                        ordinal=ordinal,
                        candidate=candidate,
                        issues=tuple(issues),
                    )
                )
            outcome = "READY_FOR_REVIEW" if items else "EMPTY"
            if any(item.candidate is None for item in items):
                outcome = "PARTIAL"
            if len(records) > response.plan.max_records or (
                total is not None and total > len(items)
            ):
                warnings.append("Source enumeration incomplete; no extra pages were requested")
                outcome = "PARTIAL"
            for i, item in enumerate(items):
                if item.candidate is None:
                    continue
                c = item.candidate
                extra: set[str] = set()
                for other in items:
                    if other.item_id == item.item_id or other.candidate is None:
                        continue
                    o = other.candidate
                    if (
                        c.source_record_id == o.source_record_id
                        or (c.title.casefold(), c.authors) == (o.title.casefold(), o.authors)
                        or (c.doi is not None and c.doi == o.doi)
                    ):
                        extra.add("POSSIBLE_DUPLICATE_review_only")
                    if c.doi and c.doi == o.doi and c.arxiv_id and o.arxiv_id != c.arxiv_id:
                        extra.add("conflicting_identifier_assertions_require_adjudication")
                if extra:
                    items[i] = item.model_copy(
                        update={"issues": tuple(sorted(set(item.issues) | extra))}
                    )
        except (ValueError, TypeError, KeyError):
            outcome = "API_ERROR"
            total = None
            items = []
            warnings.append("Malformed source envelope; not an empty bibliographic result")
    else:
        warnings.append("Acquisition failed or inaccessible; no inference about paper existence")
    payload = {
        "response": response.model_dump(mode="json"),
        "outcome": outcome,
        "items": [item.model_dump(mode="json") for item in items],
        "warnings": warnings,
        "source_total": total,
    }
    return AcquisitionAudit.model_validate({**payload, "audit_id": fingerprint(payload)})


def reviewed_sample(
    audit: AcquisitionAudit | tuple[AcquisitionAudit, ...],
    dataset: Dataset,
    manifest: ResearchManifest,
    decisions: tuple[CuratorDecision, ...],
) -> SamplingPlan:
    audits = (audit,) if isinstance(audit, AcquisitionAudit) else audit
    if not audits or len({a.audit_id for a in audits}) != len(audits):
        raise ValueError("Missing or duplicate acquisition audits")
    for entry in audits:
        if replay_acquisition(entry.response) != entry:
            raise ValueError("Acquisition audit does not reproduce")
        if entry.outcome in {"API_ERROR", "TIMEOUT", "RATE_LIMITED"}:
            raise ValueError("Failed acquisition cannot become a sampling frame")
        if entry.response.origin != manifest.origin:
            raise ValueError("Acquisition and research origins differ")
        if entry.response.plan.experiment != manifest.experiment:
            raise ValueError("Acquisition and research experiments differ")
        if (
            manifest.experiment == "recent-preprints"
            and entry.response.plan.reference_date != manifest.reference_date
        ):
            raise ValueError("Acquisition and research reference dates differ")
    frame_hash = (
        audits[0].response.metadata_sha256
        if len(audits) == 1
        else fingerprint(
            [
                {"audit_id": entry.audit_id, "metadata_sha256": entry.response.metadata_sha256}
                for entry in sorted(audits, key=lambda a: a.audit_id)
            ]
        )
    )
    if manifest.frame_snapshot_sha256 != frame_hash:
        raise ValueError("Research frame does not reference this acquisition snapshot")
    item_sources = {item.item_id: entry for entry in audits for item in entry.items}
    by_id = {d.item_id: d for d in decisions}
    if len(by_id) != len(decisions) or set(by_id) != set(item_sources):
        raise ValueError("Every acquisition item needs exactly one recorded curator decision")
    citations = {c.citation_id: c for c in dataset.citations}
    represented: set[str] = set()
    for item in (item for entry in audits for item in entry.items):
        evidence = item_sources[item.item_id]
        decision = by_id[item.item_id]
        if decision.reviewed_at < evidence.response.finished_at:
            raise ValueError("Curator review predates collection")
        if decision.disposition == "pending":
            raise ValueError("Pending decisions cannot enter a reviewed sampling frame")
        if decision.disposition == "exclude":
            if decision.citation_id:
                raise ValueError("Excluded discovery items stay in audit, not the curated frame")
            continue
        if item.candidate is None or decision.citation_id not in citations:
            raise ValueError("Invalid/unrepresented candidate cannot be included")
        if decision.citation_id in represented:
            raise ValueError("Multiple discovery items cannot silently merge into one citation")
        assert decision.citation_id is not None
        represented.add(decision.citation_id)
        c, original = citations[decision.citation_id], item.candidate
        if manifest.experiment == "mutation-robustness" and not 2018 <= original.year <= 2023:
            raise ValueError("Candidate is outside the approved publication-year frame")
        if manifest.experiment == "recent-preprints" and original.primary_category != "cs.CL":
            raise ValueError("Candidate primary category is outside the approved frame")
        if (
            c.title,
            tuple(" ".join(filter(None, (a.given, a.family))) for a in c.authors),
            c.year,
            c.doi,
            c.arxiv_id,
        ) != (original.title, original.authors, original.year, original.doi, original.arxiv_id):
            raise ValueError(
                "Curated metadata differs from source; additional evidence needs a new audit"
            )
        paper = next((p for p in manifest.papers if p.citation_id == c.citation_id), None)
        sources = {s.evidence_id: s for s in manifest.sources}
        if paper is None or not any(
            sources[key].evidence_sha256 == evidence.response.metadata_sha256
            and sources[key].retrieved_at == evidence.response.finished_at
            for key in paper.evidence_ids
            if key in sources
        ):
            raise ValueError("Curated paper lacks acquisition-linked source evidence")
    if represented != set(citations):
        raise ValueError("Curated frame contains papers outside this acquisition audit")
    return sample_dataset(dataset, manifest)
