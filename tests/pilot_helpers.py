"""Invented, explicitly simulated source responses; no authoritative claims."""

from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from citeprobe.evaluation_models import IdentityIdentifier
from citeprobe.evidence_io import begin_batch, capture_sync, finish_batch
from citeprobe.evidence_models import EvidenceBudget, EvidenceRequest, RawEvidence
from citeprobe.models import Author, CitationValues, Provenance
from citeprobe.pilot_models import PilotDecision, PilotFrame, PilotPlan, PilotReview
from citeprobe.pilot_pin import COMMIT_URL, pin_revision
from citeprobe.pilot_plans import make_plan
from citeprobe.pilot_run import build_frame, execute
from citeprobe.research_models import IdentityClaim, SourceEvidence

START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2099, 1, 1, tzinfo=UTC)
REFERENCE = date(2024, 12, 1)


def atom(day: date, total: int = 6, offset: int = 0, *, primary: str = "cs.CL") -> bytes:
    entries = []
    for index in range(offset, min(total, offset + 100)):
        identifier = f"{day:%y%m}.{day.day * 1000 + index:05d}"
        entries.append(
            f"<entry><id>https://arxiv.org/abs/{identifier}v1</id>"
            f"<title>Synthetic source day {day.isoformat()} paper {index}</title>"
            "<author><name>Invented Fixture</name></author>"
            f"<published>{day.isoformat()}T00:00:00Z</published>"
            f"<updated>{day.isoformat()}T00:00:00Z</updated>"
            f'<arxiv:primary_category term="{primary}"/></entry>'
        )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:arxiv="http://arxiv.org/schemas/atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        f"<opensearch:totalResults>{total}</opensearch:totalResults>"
        f"<opensearch:startIndex>{offset}</opensearch:startIndex>"
        "<opensearch:itemsPerPage>100</opensearch:itemsPerPage>" + "".join(entries) + "</feed>"
    ).encode()


def response(body: bytes, kind: str = "application/atom+xml", status: int = 200) -> httpx.Response:
    return httpx.Response(status, headers={"content-type": kind}, stream=httpx.ByteStream(body))


def capture(directory: Path, request: EvidenceRequest, body: bytes, kind: str) -> None:
    budget = EvidenceBudget(
        budget_id="synthetic-only",
        authorization_reference="mock HTTP only",
        origin="simulated",
        maximum_requests=1,
        requests=(request,),
    )
    begin_batch(directory, budget)
    with httpx.Client(transport=httpx.MockTransport(lambda _: response(body, kind))) as client:
        capture_sync(client, directory, budget, 1)
    finish_batch(directory)


def synthetic_pin(directory: Path) -> Path:
    capture(
        directory,
        EvidenceRequest(url=COMMIT_URL, source_kind="upstream_json"),
        b'[{"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]',
        "application/json",
    )
    return directory


def acl(collection: str, volume: str, year: int, count: int = 12) -> bytes:
    papers = "".join(
        f'<paper id="{i}"><title>Synthetic ACL {year} {i}</title>'
        "<author><first>Invented</first><last>Fixture</last></author>"
        f"<url>{collection}-{volume}.{i}</url><doi>10.1234/synthetic.{year}.{i}</doi></paper>"
        for i in range(count)
    )
    return (
        f'<collection id="{collection}"><volume id="{volume}">'
        f"<meta><year>{year}</year><booktitle>Synthetic venue</booktitle></meta>"
        f"{papers}</volume></collection>"
    ).encode()


def source_handler(request: httpx.Request) -> httpx.Response:
    params = parse_qs(urlsplit(str(request.url)).query)
    query = params["search_query"][0]
    day = datetime.strptime(query.split("[")[1][:8], "%Y%m%d").date()
    return response(atom(day, offset=int(params["start"][0])))


def a_frame(directory: Path) -> PilotFrame:
    plan = make_plan(
        "a_enumeration", "submission-age-pilot", START, END, reference=REFERENCE, origin="simulated"
    )
    with httpx.Client(transport=httpx.MockTransport(source_handler)) as client:
        run = execute(plan, directory, client, "synthetic-only")
    assert run.stopped_reason is None
    return build_frame(directory)


def a_review(directory: Path, frame: PilotFrame) -> PilotReview:
    decisions = []
    for item in frame.items:
        if item.source_id not in frame.panel_ids:
            continue
        c = item.candidate
        assert c.submitted_at and c.arxiv_id
        proof = directory / c.arxiv_id
        body = (
            f'<html><head><meta name="citation_arxiv_id" content="{c.arxiv_id}"></head>'
            '<body><div class="submission-history">[v1] '
            f"{c.submitted_at.strftime('%a, %d %b %Y %H:%M:%S UTC')}"
            "</div></body></html>"
        ).encode()
        capture(
            proof,
            EvidenceRequest(
                url="https://arxiv.org/abs/" + c.arxiv_id, source_kind="arxiv_abstract"
            ),
            body,
            "text/html",
        )
        decisions.append(
            PilotDecision(
                source_id=item.source_id,
                disposition="include",
                reason="Synthetic human approval",
                reviewer_id="synthetic-curator",
                reviewed_at=END,
                language="en",
                metadata_verified=True,
                identity_verified=True,
                v1_verified=True,
                v1_submitted_at=c.submitted_at,
                v1_evidence_directory=str(proof),
                canonical=CitationValues(
                    title=c.title,
                    authors=(Author(given="Invented", family="Fixture"),),
                    year=c.year,
                    arxiv_id=c.arxiv_id,
                ),
            )
        )
    return PilotReview(frame_id=frame.frame_id, origin="simulated", decisions=tuple(decisions))


def b_plan(directory: Path) -> PilotPlan:
    pin = pin_revision(synthetic_pin(directory), "synthetic-curator")
    return make_plan(
        "b_enumeration", "mutation-robustness-pilot", START, END, revision=pin, origin="simulated"
    )


def b_review(source: Path, pin_directory: Path) -> tuple[PilotFrame, PilotReview]:
    plan = b_plan(pin_directory)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "raw.githubusercontent.com":
            collection = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
            year = int("20" + collection[1:]) if collection.startswith("P") else int(collection[:4])
            return response(
                acl(collection, "1" if year < 2020 else "main", year), "application/xml"
            )
        params = parse_qs(urlsplit(str(request.url)).query)
        year = int(params["search_query"][0].split("[")[1][:4])
        body = source_handler(request).read()
        if year <= 2020:
            body = body.replace(
                b"</entry>", f"<arxiv:doi>10.1234/fixture.alias.{year}</arxiv:doi></entry>".encode()
            )
        return response(body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        execute(plan, source, client, "synthetic-only")
    frame = build_frame(source)
    sources, claims, decisions = [], [], []
    for item in frame.items:
        if item.source_id not in frame.panel_ids:
            continue
        c = item.candidate
        decisions.append(
            PilotDecision(
                source_id=item.source_id,
                disposition="include",
                reason="Synthetic verification",
                reviewer_id="synthetic-curator",
                reviewed_at=END,
                language="en",
                metadata_verified=True,
                identity_verified=True,
                canonical=CitationValues(
                    title=c.title,
                    authors=(Author(given="Invented", family="Fixture"),),
                    year=c.year,
                    doi=c.doi,
                    arxiv_id=c.arxiv_id,
                ),
            )
        )
        if c.doi and c.arxiv_id:
            ordinal = next(
                i + 1 for i, r in enumerate(plan.requests) if r.key == item.run_request_key
            )
            raw = RawEvidence.model_validate_json(
                (source / f"attempt-{ordinal:03d}/request-001/record.json").read_bytes()
            )
            proof = SourceEvidence(
                evidence_id=item.source_id,
                provenance=Provenance(
                    source_url=raw.final_url or raw.request.url,
                    record_identifier=c.source_record_id,
                    verification_status="verified",
                    verified_at=END,
                ),
                origin="simulated",
                authority="original_repository",
                retrieved_at=raw.finished_at,
                evidence_sha256=raw.raw_body_sha256,
                excerpt="Synthetic explicit declared identifiers",
                supports=("declared_identifiers",),
            )
            sources.append(proof)
            claims.append(
                IdentityClaim(
                    claim_id=item.source_id,
                    citation_id=item.source_id,
                    identifiers=(
                        IdentityIdentifier(namespace="doi", value=c.doi),
                        IdentityIdentifier(namespace="arxiv", value=c.arxiv_id),
                    ),
                    basis="source_declared",
                    relation="same_work",
                    expression="original",
                    evidence_ids=(proof.evidence_id,),
                    rationale="Synthetic direct source declaration",
                )
            )
    return frame, PilotReview(
        frame_id=frame.frame_id,
        origin="simulated",
        identifier_inspection_protocol="Synthetic uniform XML/API identifier inspection",
        decisions=tuple(decisions),
        sources=tuple(sources),
        claims=tuple(claims),
    )
