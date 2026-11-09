"""Offline empirical-pilot safeguards, using exclusively simulated HTTP."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pilot_helpers import (
    END,
    REFERENCE,
    START,
    a_frame,
    a_review,
    acl,
    atom,
    b_plan,
    b_review,
    response,
    source_handler,
)

from citeprobe.cli import main
from citeprobe.evidence_io import json_bytes, verify_batch
from citeprobe.lookup_inputs import fingerprint
from citeprobe.pilot_models import PilotFrame, PilotPlan
from citeprobe.pilot_pin import COLLECTIONS, verify_revision
from citeprobe.pilot_plans import make_plan, seal_plan, validate_plan
from citeprobe.pilot_review import freeze_pilot, select_pilot, v1_date, verify_pilot
from citeprobe.pilot_run import build_frame, execute, load_run, validate_selected
from citeprobe.research_models import Review


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)


def test_a_complete_pipeline_and_freeze(tmp_path: Path) -> None:
    source = tmp_path / "enumeration"
    frame = a_frame(source)
    assert len(frame.items) == len(frame.panel_ids) == 24
    assert build_frame(source) == frame
    assert frame.origin == "simulated"
    run = load_run(source)
    assert sum(a.disposition == "captured" for a in run.attempts) == 4
    assert sum(a.disposition == "not_required" for a in run.attempts) == 4
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    review = a_review(tmp_path, frame)
    first = select_pilot(source, frame, review)
    assert first["ready_to_freeze"] is True
    assert first["date_basis"] == "first_arxiv_submission"
    assert first["origin"] == "simulated"
    assert isinstance(first["selected_source_ids"], list)
    assert len(first["selected_source_ids"]) == 8
    assert json_bytes(first) == json_bytes(select_pilot(source, frame, review))
    frozen = tmp_path / "frozen"
    freeze_pilot(frozen, source, frame, review)
    verify_pilot(frozen)
    assert main(["validate", str(frozen / "dataset.json")]) == 0
    anchor = hashlib.sha256((frozen / "integrity.json").read_bytes()).hexdigest()
    verify_pilot(frozen, anchor=anchor)
    with pytest.raises(ValueError, match="anchor"):
        verify_pilot(frozen, anchor="0" * 64)
    assert all(p.read_bytes() == content for p, content in before.items())
    with pytest.raises(FileExistsError):
        freeze_pilot(frozen, source, frame, review)
    with (frozen / "selection.json").open("ab") as output:
        output.write(b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_pilot(frozen)


@pytest.mark.parametrize("total", [0, 1, 100, 101, 200])
def test_complete_pagination(tmp_path: Path, total: int) -> None:
    plan = make_plan(
        "a_enumeration", "submission-age-pilot", START, END, reference=REFERENCE, origin="simulated"
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        params = parse_qs(urlsplit(str(request.url)).query)
        day = datetime.strptime(params["search_query"][0].split("[")[1][:8], "%Y%m%d").date()
        return response(atom(day, total, int(params["start"][0])))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(plan, tmp_path / "run", client, "synthetic-only")
    assert not result.stopped_reason
    frame = build_frame(tmp_path / "run")
    assert len(frame.items) == total * 4
    assert len(calls) == (8 if total > 100 else 4)


@pytest.mark.parametrize(
    "failure", ["cap", "overlap", "changed", "500", "429", "redirect", "timeout"]
)
def test_failure_stops_without_retry(tmp_path: Path, failure: str) -> None:
    plan = make_plan(
        "a_enumeration", "submission-age-pilot", START, END, reference=REFERENCE, origin="simulated"
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if failure == "timeout":
            raise httpx.ConnectTimeout("synthetic", request=request)
        if failure in {"500", "429", "redirect"}:
            return response(
                b"synthetic failure", status={"500": 500, "429": 429, "redirect": 302}[failure]
            )
        day = plan.requests[0].source_day
        assert day
        total = 201 if failure == "cap" else 101
        offset = 100 if len(calls) == 2 else 0
        data = atom(day, 102 if failure == "changed" and offset else total, offset)
        if failure == "overlap" and offset:
            data = data.replace(
                f"{day.day * 1000 + 100:05d}".encode(), f"{day.day * 1000:05d}".encode()
            )
        return response(data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(plan, tmp_path / "run", client, "synthetic-only")
    assert result.stopped_reason
    assert len(calls) == (2 if failure in {"overlap", "changed"} else 1)
    with pytest.raises(ValueError, match="complete successful"):
        build_frame(tmp_path / "run")
    verify_batch(tmp_path / "run/attempt-001")


def test_primary_category_filter_and_possible_duplicates(tmp_path: Path) -> None:
    plan = make_plan(
        "a_enumeration", "submission-age-pilot", START, END, reference=REFERENCE, origin="simulated"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        original = source_handler(request)
        data = original.read().replace(b'term="cs.CL"', b'term="cs.AI"', 1)
        # Two nonconclusive duplicate titles/authors remain in the frame.
        import re

        data = re.sub(b"<title>[^<]+</title>", b"<title>Synthetic identical title</title>", data)
        return response(data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        execute(plan, tmp_path / "run", client, "synthetic-only")
    frame = build_frame(tmp_path / "run")
    assert len(frame.exclusions) == 4
    assert len(frame.panel_ids) == 20
    assert all(i.possible_duplicates for i in frame.items)
    assert len(frame.items) == 24


def test_plan_tampering_and_day_boundaries() -> None:
    plan = make_plan(
        "a_enumeration", "submission-age-pilot", START, END, reference=REFERENCE, origin="simulated"
    )
    validate_plan(plan)
    assert len(plan.requests) == 8
    assert [
        (REFERENCE - r.source_day).days for r in plan.requests if not r.conditional and r.source_day
    ] == [4, 11, 22, 45]
    with pytest.raises(ValueError, match="fingerprint"):
        validate_plan(plan.model_copy(update={"seed": 1}))
    bad = seal_plan(
        plan.model_copy(update={"planned_started_at": datetime(2024, 11, 1, tzinfo=UTC)})
    )
    with pytest.raises(ValueError, match="closed"):
        validate_plan(bad)
    with pytest.raises(ValueError, match="genuine"):
        make_plan("b_enumeration", "mutation-robustness-pilot", START, END)


def test_followup_exact_ids_and_batches(tmp_path: Path) -> None:
    frame = a_frame(tmp_path / "run")
    plan = make_plan("id_batch", frame.experiment, START, END, frame=frame)
    validate_plan(plan)
    assert [len(r.source_ids) for r in plan.requests] == [10, 10, 4]
    assert plan.parent_frame_id == frame.frame_id
    for row in plan.requests:
        params = parse_qs(urlsplit(row.request.url).query)
        assert "search_query" not in params
        assert params["id_list"][0].split(",") == list(row.source_ids)
    verification = make_plan("v1_verification", frame.experiment, START, END, frame=frame)
    assert verification.maximum_requests == 24
    with pytest.raises(ValueError, match="fingerprint"):
        make_plan(
            "id_batch",
            frame.experiment,
            START,
            END,
            frame=frame.model_copy(update={"origin": "observed"}),
        )
    row = plan.requests[0]
    with pytest.raises(ValueError, match="missing/duplicate/unrequested"):
        validate_selected(atom(REFERENCE).decode(), row)


def test_b_complete_collections_and_authentic_pin(tmp_path: Path) -> None:
    plan = b_plan(tmp_path / "pin")
    assert plan.revision
    verify_revision(plan.revision)
    assert plan.maximum_requests == 18
    assert plan.origin == "simulated"
    assert all(plan.revision.commit in r.request.url for r in plan.requests[:6])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "raw.githubusercontent.com":
            collection = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
            volume = dict(COLLECTIONS)[collection]
            year = int("20" + collection[1:]) if collection.startswith("P") else int(collection[:4])
            return response(acl(collection, volume, year), "application/xml")
        return source_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(plan, tmp_path / "run", client, "synthetic-only")
    assert not result.stopped_reason
    frame = build_frame(tmp_path / "run")
    assert len(frame.items) == 72 + 36  # Includes every paper, not a ten-record preview.
    assert len(frame.panel_ids) == 18
    assert frame == build_frame(tmp_path / "run")
    selected = make_plan("id_batch", frame.experiment, START, END, frame=frame)
    assert len(selected.source_ids) == 6 and selected.maximum_requests == 1


@pytest.mark.parametrize(
    "problem",
    [
        "pending",
        "missing",
        "origin",
        "metadata",
        "api_only",
        "contradiction",
        "duplicate_exclusion",
    ],
)
def test_curation_fail_closed(tmp_path: Path, problem: str) -> None:
    source = tmp_path / "run"
    frame = a_frame(source)
    review = a_review(tmp_path, frame)
    decision = review.decisions[0]
    if problem == "missing":
        review = review.model_copy(update={"decisions": review.decisions[1:]})
    elif problem == "origin":
        review = review.model_copy(update={"origin": "observed"})
    else:
        changes: dict[str, dict[str, object]] = {
            "pending": {"disposition": "pending"},
            "metadata": {"metadata_verified": False},
            "api_only": {"v1_evidence_directory": None},
            "contradiction": {"v1_submitted_at": END},
            "duplicate_exclusion": {
                "disposition": "exclude",
                "exclusion_kind": "verified_duplicate",
            },
        }
        updates = changes[problem]
        review = review.model_copy(
            update={"decisions": (decision.model_copy(update=updates), *review.decisions[1:])}
        )
    with pytest.raises(ValueError):
        select_pilot(source, frame, review)


def test_cli_offline_inventory_replay_and_output_protection(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    args = [
        "pilot-plan-a",
        "--reference-date",
        REFERENCE.isoformat(),
        "--planned-start",
        START.isoformat(),
        "--planned-end",
        END.isoformat(),
        "--origin",
        "simulated",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    plan = PilotPlan.model_validate_json(output.read_bytes())
    assert plan.maximum_requests == 8
    assert main(args) != 0
    assert (
        main(
            [
                "pilot-run",
                str(output),
                "--authorization-reference",
                "not-authorized",
                "--plan-sha256",
                hashlib.sha256(output.read_bytes()).hexdigest(),
                "--output-dir",
                str(tmp_path / "live"),
            ]
        )
        != 0
    )
    assert not (tmp_path / "live").exists()
    frame = a_frame(tmp_path / "source")
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    for out in (one, two):
        assert main(["pilot-replay", str(tmp_path / "source"), "--output", str(out)]) == 0
    assert one.read_bytes() == two.read_bytes() == json_bytes(frame.model_dump(mode="json"))
    assert (
        main(
            [
                "pilot-frame",
                str(tmp_path / "source"),
                "--output",
                str(tmp_path / "source/unsafe.json"),
            ]
        )
        != 0
    )


def test_v1_identity_and_missing_evidence(tmp_path: Path) -> None:
    frame = a_frame(tmp_path / "source")
    review = a_review(tmp_path, frame)
    first = review.decisions[0]
    assert first.v1_evidence_directory
    directory = Path(first.v1_evidence_directory)
    timestamp, _ = v1_date(directory, first.source_id.removeprefix("arxiv:"), "simulated")
    assert timestamp == first.v1_submitted_at
    with pytest.raises(ValueError, match="exact authoritative"):
        v1_date(directory, "2401.12345", "simulated")
    assert (
        json.loads((directory / "request-001/extracted.json").read_bytes())["payload"][
            "verification_status"
        ]
        == "pending_curator"
    )


def test_frame_fingerprint_rejects_mutation(tmp_path: Path) -> None:
    frame = a_frame(tmp_path / "source")
    assert frame.frame_id == fingerprint(frame.model_dump(mode="json", exclude={"frame_id"}))
    altered = PilotFrame.model_validate({**frame.model_dump(), "panel_ids": frame.panel_ids[:-1]})
    with pytest.raises(ValueError, match="fingerprint"):
        make_plan("id_batch", altered.experiment, START, END, frame=altered)


def test_b_strata_and_selected_mapping_compatibility(tmp_path: Path) -> None:
    from citeprobe.evaluation_models import IdentityMappings
    from citeprobe.identity import IdentityIndex
    from citeprobe.models import Dataset

    source = tmp_path / "run"
    frame, review = b_review(source, tmp_path / "pin")
    result = select_pilot(source, frame, review)
    assert result["ready_to_freeze"] is True
    selected = result["selected_source_ids"]
    assert isinstance(selected, list) and len(selected) == 6
    groups = result["groups"]
    assert isinstance(groups, dict)
    assert {
        group: sum(groups[key] == group for key in selected)
        for group in ("dual", "arxiv_only", "doi_only")
    } == {"dual": 2, "arxiv_only": 2, "doi_only": 2}
    dataset = Dataset.model_validate(result["dataset"])
    mappings = IdentityMappings.model_validate(result["identity_mappings"])
    IdentityIndex(dataset, mappings)
    assert len(mappings.mappings) == 2
    for group in ("dual", "arxiv_only", "doi_only"):
        ordered = sorted(
            (key for key in groups if groups[key] == group),
            key=lambda key: (
                hashlib.sha256(("citeprobe-B-v1|seed=0|" + key).encode()).hexdigest(),
                key,
            ),
        )
        assert [key for key in selected if groups[key] == group] == ordered[:2]
    freeze_pilot(tmp_path / "frozen", source, frame, review)
    verify_pilot(tmp_path / "frozen")


@pytest.mark.parametrize(
    "problem",
    ["one_reviewer", "same_reviewer", "translation", "conflict", "unverified", "invented_alias"],
)
def test_identity_approval_safeguards(tmp_path: Path, problem: str) -> None:
    source = tmp_path / "run"
    frame, review = b_review(source, tmp_path / "pin")
    claim = review.claims[0]
    if problem == "one_reviewer":
        claim = claim.model_copy(
            update={
                "basis": "new_mapping",
                "reviews": (Review(reviewer_id="one", decision="approve", reviewed_at=END),),
            }
        )
    elif problem == "same_reviewer":
        approval = Review(reviewer_id="one", decision="approve", reviewed_at=END)
        claim = claim.model_copy(update={"basis": "new_mapping", "reviews": (approval, approval)})
    elif problem == "translation":
        claim = claim.model_copy(update={"expression": "translation"})
    elif problem == "conflict":
        claim = claim.model_copy(update={"conflict": True})
    elif problem == "unverified":
        proof = review.sources[0]
        review = review.model_copy(
            update={
                "sources": (
                    proof.model_copy(
                        update={
                            "provenance": proof.provenance.model_copy(
                                update={"verification_status": "pending", "verified_at": None}
                            )
                        }
                    ),
                    *review.sources[1:],
                )
            }
        )
    else:
        from citeprobe.evaluation_models import IdentityIdentifier

        claim = claim.model_copy(
            update={
                "identifiers": (
                    *claim.identifiers,
                    IdentityIdentifier(namespace="doi", value="10.1234/not-in-raw-source"),
                )
            }
        )
    review = review.model_copy(update={"claims": (claim, *review.claims[1:])})
    with pytest.raises(ValueError):
        select_pilot(source, frame, review)


def test_two_independent_reviewers_accepted(tmp_path: Path) -> None:
    source = tmp_path / "run"
    frame, review = b_review(source, tmp_path / "pin")
    claim = review.claims[0].model_copy(
        update={
            "basis": "new_mapping",
            "reviews": tuple(
                Review(reviewer_id=name, decision="approve", reviewed_at=END)
                for name in ("one", "two")
            ),
        }
    )
    review = review.model_copy(update={"claims": (claim, *review.claims[1:])})
    assert select_pilot(source, frame, review)["ready_to_freeze"] is True


def test_unavailable_v1_explicit_exclusion_and_zero_selection(tmp_path: Path) -> None:
    from pilot_helpers import capture

    from citeprobe.evidence_models import EvidenceRequest

    source = tmp_path / "run"
    frame = a_frame(source)
    review = a_review(tmp_path, frame)
    first = review.decisions[0]
    proof = tmp_path / "missing-v1"
    identifier = first.source_id.removeprefix("arxiv:")
    capture(
        proof,
        EvidenceRequest(url="https://arxiv.org/abs/" + identifier, source_kind="arxiv_abstract"),
        f'<html><meta name="citation_arxiv_id" content="{identifier}"></html>'.encode(),
        "text/html",
    )
    decision = first.model_copy(
        update={
            "disposition": "exclude",
            "exclusion_kind": "unverified_evidence",
            "v1_verified": False,
            "v1_submitted_at": None,
            "v1_evidence_directory": str(proof),
        }
    )
    review = review.model_copy(update={"decisions": (decision, *review.decisions[1:])})
    assert select_pilot(source, frame, review)["ready_to_freeze"] is True
    review = review.model_copy(
        update={
            "decisions": tuple(
                d.model_copy(
                    update={"disposition": "exclude", "exclusion_kind": "unverified_evidence"}
                )
                for d in review.decisions
            )
        }
    )
    result = select_pilot(source, frame, review)
    assert result["ready_to_freeze"] is False and result["dataset"] is None
    with pytest.raises(ValueError, match="shortfall"):
        freeze_pilot(tmp_path / "must-not-exist", source, frame, review)
    assert not (tmp_path / "must-not-exist").exists()


def test_actual_v1_contradiction_stops_even_excluded(tmp_path: Path) -> None:
    from pilot_helpers import capture

    from citeprobe.evidence_models import EvidenceRequest

    source = tmp_path / "run"
    frame = a_frame(source)
    review = a_review(tmp_path, frame)
    first = review.decisions[0]
    proof = tmp_path / "contradictory-v1"
    identifier = first.source_id.removeprefix("arxiv:")
    capture(
        proof,
        EvidenceRequest(url="https://arxiv.org/abs/" + identifier, source_kind="arxiv_abstract"),
        (
            f'<html><meta name="citation_arxiv_id" content="{identifier}">'
            '<div class="submission-history">[v1] Mon, 01 Jan 2024 00:00:00 UTC</div></html>'
        ).encode(),
        "text/html",
    )
    decision = first.model_copy(
        update={
            "disposition": "exclude",
            "exclusion_kind": "eligibility",
            "v1_submitted_at": datetime(2024, 1, 1, tzinfo=UTC),
            "v1_evidence_directory": str(proof),
        }
    )
    with pytest.raises(ValueError, match="API/v1 submission contradiction"):
        select_pilot(
            source,
            frame,
            review.model_copy(update={"decisions": (decision, *review.decisions[1:])}),
        )


def test_selected_id_requests_execute_and_replay(tmp_path: Path) -> None:
    from xml.etree import ElementTree as ET

    from citeprobe.acquisition_sources import ATOM, ArxivAtom

    source = tmp_path / "source"
    frame = a_frame(source)
    entries = {}
    for attempt in load_run(source).attempts:
        if attempt.evidence_directory:
            body = (source / attempt.evidence_directory / "request-001/body.bin").read_text()
            records, _ = ArxivAtom().records(body)
            for record in records:
                entries[ArxivAtom().candidate(record).arxiv_id] = record
    plan = make_plan("id_batch", frame.experiment, START, END, frame=frame)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(urlsplit(str(request.url)).query)
        assert "search_query" not in params
        ids = params["id_list"][0].split(",")
        calls.append(ids)
        root = ET.Element(ATOM + "feed")
        for key in reversed(ids):
            root.append(entries[key])
        return response(ET.tostring(root))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        run = execute(plan, tmp_path / "batch", client, "synthetic-only")
    assert run.stopped_reason is None and len(calls) == 3
    one, two = tmp_path / "replay1.json", tmp_path / "replay2.json"
    for output in (one, two):
        assert main(["pilot-replay", str(tmp_path / "batch"), "--output", str(output)]) == 0
    assert one.read_bytes() == two.read_bytes()


def test_missing_uniform_identifier_review_blocks_b(tmp_path: Path) -> None:
    source = tmp_path / "source"
    frame, review = b_review(source, tmp_path / "pin")
    with pytest.raises(ValueError, match="uniform"):
        select_pilot(
            source, frame, review.model_copy(update={"identifier_inspection_protocol": None})
        )
