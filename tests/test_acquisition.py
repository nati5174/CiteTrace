"""Synthetic source metadata and mocked HTTP only; no live collection."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from research_helpers import fixture_payloads, seal

from citeprobe.acquisition import collect, replay_acquisition, reviewed_sample
from citeprobe.acquisition_models import AcquisitionPlan, AcquisitionResponse, CuratorDecision
from citeprobe.acquisition_sources import metadata_projection, source
from citeprobe.cli import main
from citeprobe.research_io import freeze, verify

ROOT = Path("tests/fixtures/acquisition")


def plan(source_name: Literal["arxiv_atom", "acl_xml"] = "arxiv_atom") -> AcquisitionPlan:
    return AcquisitionPlan(
        source=source_name,
        experiment="mutation-robustness",
        planned_started_at=datetime(2025, 1, 1, tzinfo=UTC),
        planned_finished_at=datetime(2025, 1, 2, tzinfo=UTC),
        acl_commit="a" * 40 if source_name == "acl_xml" else None,
        acl_volume="synthetic" if source_name == "acl_xml" else None,
    )


def recorded(
    body: str | None = None,
    source_name: Literal["arxiv_atom", "acl_xml"] = "arxiv_atom",
    **changes: Any,
) -> AcquisitionResponse:
    p = plan(source_name)
    xml = metadata_projection(body if body is not None else (ROOT / "arxiv.xml").read_text())
    payload = {
        "origin": "simulated",
        "plan": p,
        "request": source(p).request(p),
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:00:00Z",
        "http_status": 200,
        "metadata_xml": xml,
        "metadata_sha256": hashlib.sha256(xml.encode()).hexdigest(),
        "response_body_sha256": hashlib.sha256((body or xml).encode()).hexdigest(),
    }
    return AcquisitionResponse.model_validate({**payload, **changes})


def curated_inputs() -> tuple[Any, Any, Any, tuple[CuratorDecision, ...]]:
    audit = replay_acquisition(recorded())
    raw, ledger = fixture_payloads("mutation-robustness")
    for i, c in enumerate(raw["citations"], 1):
        c.update(year=2020, arxiv_id=f"2001.0000{i}")
    ledger["frame_snapshot_sha256"] = audit.response.metadata_sha256
    ledger["sources"][0]["evidence_sha256"] = audit.response.metadata_sha256
    dataset, manifest = seal(raw, ledger)
    decisions = tuple(
        CuratorDecision(
            item_id=item.item_id,
            disposition="include",
            citation_id=f"synthetic-{item.ordinal}",
            reason="Synthetic curator assertion",
            reviewer_id="synthetic-reviewer",
            reviewed_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        for item in audit.items
    )
    return audit, dataset, manifest, decisions


def test_arxiv_replay_pending_dates_and_no_personal_contact() -> None:
    response = recorded()
    audit = replay_acquisition(response)
    assert audit == replay_acquisition(response)
    assert audit.outcome == "READY_FOR_REVIEW" and not audit.frame_complete
    assert len(audit.items) == 2
    candidate = audit.items[0].candidate
    assert candidate and candidate.authors == ("Invented Fixture",)
    assert candidate.first_public_date is None and candidate.verification_status == "pending"
    assert candidate.submitted_at and candidate.submitted_at.tzinfo
    assert response.metadata_xml and "not-retained@example.org" not in response.metadata_xml
    assert response.origin == "simulated"


def test_acl_parser_explicit_doi_and_pinned_source() -> None:
    response = recorded((ROOT / "acl.xml").read_text(), "acl_xml")
    audit = replay_acquisition(response)
    candidate = audit.items[0].candidate
    assert candidate and candidate.doi == "10.1234/synthetic-acl"
    assert candidate.arxiv_id is None
    assert candidate.year == 2020 and candidate.venue == "Synthetic Proceedings"
    assert candidate.volume == "12" and candidate.issue == "21"
    assert "/" + "a" * 40 + "/" in response.request.endpoint


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "empty",
        "malformed",
        "timeout",
        "connect",
        "rate",
        "server",
        "redirect",
        "oversized",
    ],
)
def test_http_failures_are_audited_without_retry(mode: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic", request=request)
        if mode == "connect":
            raise httpx.ConnectError("synthetic", request=request)
        if mode == "rate":
            return httpx.Response(429, headers={"Retry-After": "2"})
        if mode == "server":
            return httpx.Response(503)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.org/"})
        body = (ROOT / "arxiv.xml").read_text()
        if mode == "empty":
            body = '<feed xmlns="http://www.w3.org/2005/Atom"/>'
        if mode == "malformed":
            body = "<not-valid"
        if mode == "oversized":
            body = "x" * 2_000_001
        return httpx.Response(200, text=body)

    async def run() -> AcquisitionResponse:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ) as client:
            return await collect(
                plan(), client, origin="simulated", authorization_reference="test-only"
            )

    response = asyncio.run(run())
    audit = replay_acquisition(response)
    expected = {
        "success": "READY_FOR_REVIEW",
        "empty": "EMPTY",
        "timeout": "TIMEOUT",
        "rate": "RATE_LIMITED",
    }.get(mode, "API_ERROR")
    assert audit.outcome == expected
    assert len(calls) == 1 and response.origin == "simulated"
    assert calls[0].url.host == "export.arxiv.org"


def test_invalid_records_duplicates_conflicts_and_incomplete_slice() -> None:
    body = (ROOT / "arxiv.xml").read_text()
    body = body.replace("2001.00002v1", "2001.00001v2")
    audit = replay_acquisition(recorded(body))
    assert len(audit.items) == 2
    assert all("POSSIBLE_DUPLICATE_review_only" in item.issues for item in audit.items)
    broken = body.replace("Synthetic test work 2", "")
    assert replay_acquisition(recorded(broken)).outcome == "PARTIAL"
    xml = (
        (ROOT / "arxiv.xml")
        .read_text()
        .replace(
            "<arxiv:primary_category",
            "<arxiv:doi>10.1234/common</arxiv:doi><arxiv:primary_category",
        )
    )
    audit = replay_acquisition(recorded(xml))
    assert all(
        "conflicting_identifier_assertions_require_adjudication" in item.issues
        for item in audit.items
    )
    response = recorded()
    smaller = response.plan.model_copy(update={"max_records": 1})
    sliced = response.model_copy(
        update={"plan": smaller, "request": source(smaller).request(smaller)}
    )
    assert replay_acquisition(sliced).outcome == "PARTIAL"


def test_unsafe_xml_and_timestamp_and_hash_rejections() -> None:
    with pytest.raises(ValueError):
        metadata_projection('<!DOCTYPE a [<!ENTITY b "bad">]><feed/>')
    with pytest.raises(ValueError):
        recorded(started_at="2025-01-01T00:00:00")
    with pytest.raises(ValueError):
        recorded(finished_at="2024-12-31T23:59:00Z")
    with pytest.raises(ValueError):
        replay_acquisition(recorded(metadata_sha256="f" * 64))
    response = recorded()
    with pytest.raises(ValueError):
        replay_acquisition(
            response.model_copy(
                update={
                    "request": response.request.model_copy(
                        update={"endpoint": "https://api.openalex.org/works"}
                    )
                }
            )
        )
    error = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad</id></entry></feed>'
    assert replay_acquisition(recorded(error)).outcome == "API_ERROR"


def test_reviewed_sampling_and_frozen_integrity(tmp_path: Path) -> None:
    audit, dataset, manifest, decisions = curated_inputs()
    result = reviewed_sample(audit, dataset, manifest, decisions)
    assert result == reviewed_sample(audit, dataset, manifest, decisions)
    assert result.origin == "simulated"
    freeze(dataset, manifest, tmp_path / "frozen")
    assert verify(tmp_path / "frozen") == result
    (tmp_path / "frozen/dataset.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        verify(tmp_path / "frozen")


@pytest.mark.parametrize("change", ["pending", "missing", "merge", "origin", "bridge", "leak"])
def test_curated_sampling_rejects_unreviewed_or_unlinked_inputs(change: str) -> None:
    audit, dataset, manifest, decisions = curated_inputs()
    if change == "pending":
        decisions = (decisions[0].model_copy(update={"disposition": "pending"}), decisions[1])
    if change == "missing":
        decisions = decisions[:1]
    if change == "merge":
        decisions = (decisions[0], decisions[1].model_copy(update={"citation_id": "synthetic-1"}))
    if change == "origin":
        manifest = manifest.model_copy(update={"origin": "observed"})
    if change == "bridge":
        claim = {
            "claim_id": "unreviewed",
            "citation_id": "synthetic-1",
            "basis": "new_mapping",
            "relation": "same_work",
            "expression": "original",
            "evidence_ids": ["source"],
            "rationale": "Not approved",
            "identifiers": [{"namespace": "doi", "value": "10.1234/new"}],
        }
        raw = dataset.model_dump(mode="json")
        payload = manifest.model_dump(mode="json")
        payload["identity_claims"] = [claim]
        dataset, manifest = seal(raw, payload)
    if change == "leak":
        # Curated source metadata cannot be replaced by ground-truth hints.
        payload = dataset.model_dump(mode="json")
        payload["citations"][0]["title"] += " 2001.00001"
        dataset, manifest = seal(payload, manifest.model_dump(mode="json"))
    with pytest.raises(ValueError):
        reviewed_sample(audit, dataset, manifest, decisions)


def test_offline_cli_and_network_gate(tmp_path: Path) -> None:
    response = recorded()
    saved = tmp_path / "response.json"
    saved.write_text(response.model_dump_json(), encoding="utf-8")
    for name in ("audit.json", "audit-again.json"):
        assert main(["acquisition-replay", str(saved), "--output", str(tmp_path / name)]) == 0
    assert (tmp_path / "audit.json").read_bytes() == (tmp_path / "audit-again.json").read_bytes()
    assert (
        main(
            [
                "acquisition-run",
                str(saved),
                "--authorization-reference",
                "not-authorized",
                "--plan-sha256",
                "0" * 64,
                "--output-dir",
                str(tmp_path / "blocked"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "blocked").exists()
    assert (
        main(
            [
                "acquisition-plan",
                "--source",
                "arxiv_atom",
                "--experiment",
                "recent-preprints",
                "--reference-date",
                "2025-01-02",
                "--planned-start",
                "2025-01-01T00:00:00Z",
                "--planned-end",
                "2025-01-02T00:00:00Z",
                "--output",
                str(tmp_path / "plan.json"),
            ]
        )
        == 0
    )
    data = json.loads((tmp_path / "plan.json").read_bytes())
    assert data["maximum_requests"] == 1 and "actual_started_at" not in data


def test_recent_preprints_require_independent_public_date_evidence() -> None:
    from datetime import date

    response = recorded()
    recent = AcquisitionPlan(
        source="arxiv_atom",
        experiment="recent-preprints",
        reference_date=date(2025, 1, 2),
        planned_started_at=datetime(2025, 1, 1, tzinfo=UTC),
        planned_finished_at=datetime(2025, 1, 2, tzinfo=UTC),
    )
    response = response.model_copy(
        update={"plan": recent, "request": source(recent).request(recent)}
    )
    audit = replay_acquisition(response)
    assert all("authoritative_first_public_date_required" in item.issues for item in audit.items)
    assert all(item.candidate and item.candidate.first_public_date is None for item in audit.items)
    assert audit.frame_complete is False


def test_conflicting_dois_and_naive_source_dates_quarantine_records() -> None:
    body = (ROOT / "arxiv.xml").read_text()
    duplicate = "<arxiv:doi>10.1234/a</arxiv:doi><arxiv:doi>10.1234/b</arxiv:doi>"
    body = body.replace("<arxiv:primary_category", duplicate + "<arxiv:primary_category", 1)
    assert replay_acquisition(recorded(body)).items[0].candidate is None
    body = (ROOT / "arxiv.xml").read_text().replace("2020-01-01T12:00:00Z", "2020-01-01T12:00:00")
    assert replay_acquisition(recorded(body)).items[0].candidate is None


def test_multiple_audits_preserve_origin_and_do_not_silently_merge() -> None:
    audit, dataset, manifest, decisions = curated_inputs()
    with pytest.raises(ValueError, match="duplicate acquisition"):
        reviewed_sample((audit, audit), dataset, manifest, decisions)
    second = replay_acquisition(recorded(origin="unknown"))
    with pytest.raises(ValueError, match="origins"):
        reviewed_sample((audit, second), dataset, manifest, decisions)


@pytest.mark.parametrize("name", ["response-arxiv.json", "response-acl.json"])
def test_saved_synthetic_responses_replay_without_relabeling(name: str, tmp_path: Path) -> None:
    response = AcquisitionResponse.model_validate_json((ROOT / name).read_bytes())
    assert response.origin == "simulated"
    audit = replay_acquisition(response)
    assert audit.outcome == "READY_FOR_REVIEW"
    assert all(
        item.candidate and item.candidate.verification_status == "pending" for item in audit.items
    )
    assert (
        main(["acquisition-replay", str(ROOT / name), "--output", str(tmp_path / "audit.json")])
        == 0
    )


def test_reviewed_source_metadata_cannot_leak_identifiers_into_queries() -> None:
    audit, dataset, manifest, decisions = curated_inputs()
    xml = (
        (ROOT / "arxiv.xml")
        .read_text()
        .replace("Synthetic test work 1", "Synthetic test work 1 2001.00001")
    )
    audit = replay_acquisition(recorded(xml))
    raw = dataset.model_dump(mode="json")
    raw["citations"][0]["title"] += " 2001.00001"
    payload = manifest.model_dump(mode="json")
    payload["frame_snapshot_sha256"] = audit.response.metadata_sha256
    payload["sources"][0]["evidence_sha256"] = audit.response.metadata_sha256
    dataset, manifest = seal(raw, payload)
    decisions = tuple(
        decision.model_copy(update={"item_id": item.item_id})
        for decision, item in zip(decisions, audit.items, strict=True)
    )
    with pytest.raises(ValueError, match="leakage"):
        reviewed_sample(audit, dataset, manifest, decisions)


def test_live_cli_bad_hash_and_expired_window_do_not_send_requests(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(plan().model_dump_json(), encoding="utf-8")
    base = [
        "acquisition-run",
        str(path),
        "--authorize-live",
        "--authorization-reference",
        "test",
        "--output-dir",
        str(tmp_path / "blocked"),
    ]
    assert main([*base, "--plan-sha256", "0" * 64]) == 1
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert main([*base, "--plan-sha256", digest]) == 1
    assert not (tmp_path / "blocked").exists()


def test_cli_sampling_after_explicit_curator_review(tmp_path: Path) -> None:
    audit, dataset, manifest, decisions = curated_inputs()
    for name, model in [("audit", audit), ("dataset", dataset), ("manifest", manifest)]:
        (tmp_path / (name + ".json")).write_text(model.model_dump_json(), encoding="utf-8")
    (tmp_path / "decisions.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in decisions]), encoding="utf-8"
    )
    assert (
        main(
            [
                "acquisition-sample",
                str(tmp_path / "audit.json"),
                "--dataset",
                str(tmp_path / "dataset.json"),
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--decisions",
                str(tmp_path / "decisions.json"),
                "--output",
                str(tmp_path / "sample.json"),
            ]
        )
        == 0
    )


def test_recent_frame_reference_date_cannot_shift_after_discovery() -> None:
    from datetime import date

    audit, dataset, _, decisions = curated_inputs()
    response = audit.response
    recent = AcquisitionPlan(
        source="arxiv_atom",
        experiment="recent-preprints",
        reference_date=date(2025, 1, 2),
        planned_started_at=datetime(2025, 1, 1, tzinfo=UTC),
        planned_finished_at=datetime(2025, 1, 2, tzinfo=UTC),
    )
    audit = replay_acquisition(
        response.model_copy(update={"plan": recent, "request": source(recent).request(recent)})
    )
    _, ledger = fixture_payloads()
    ledger["frame_snapshot_sha256"] = audit.response.metadata_sha256
    ledger["sources"][0]["evidence_sha256"] = audit.response.metadata_sha256
    dataset, manifest = seal(dataset.model_dump(mode="json"), ledger)
    decisions = tuple(
        d.model_copy(update={"item_id": item.item_id})
        for d, item in zip(decisions, audit.items, strict=True)
    )
    with pytest.raises(ValueError, match="reference dates differ"):
        reviewed_sample(audit, dataset, manifest, decisions)
