"""Versioned per-request limits, replay and the one explicit exception. No live HTTP."""

import asyncio
import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pilot_helpers import END, source_handler
from resource_helpers import large_xml, resource_failure, streamed

from citeprobe.acl_scope import scoped_collection
from citeprobe.acquisition_sources import xml_root
from citeprobe.cli import main
from citeprobe.evidence_extract import decoded_body
from citeprobe.evidence_io import (
    begin_batch,
    capture_async,
    capture_sync,
    finish_batch,
    json_bytes,
    verify_batch,
)
from citeprobe.evidence_models import EvidenceBudget, EvidenceRequest
from citeprobe.models import Author, CitationValues
from citeprobe.pilot_models import PilotDecision, PilotRequest, PilotReview
from citeprobe.pilot_resource_continuation import (
    PROPOSED_AUTHORIZATION_REFERENCE,
    make_resource_continuation,
    validate_resource_continuation,
)
from citeprobe.pilot_review import select_pilot
from citeprobe.pilot_run import build_frame, execute, load_run
from citeprobe.source_limits import ACL_2023_URL


def budget(url: str = ACL_2023_URL) -> EvidenceBudget:
    return EvidenceBudget(
        budget_id="synthetic",
        authorization_reference="mock-only",
        origin="simulated",
        maximum_requests=1,
        requests=(EvidenceRequest(url=url, source_kind="acquisition_xml"),),
    )


def test_recovery_reuses_five_and_preserves_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, body = resource_failure(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    plan = make_resource_continuation(source)
    validate_resource_continuation(plan)
    assert plan.schema_version == "3.1"
    assert plan.proposed_authorization_reference == PROPOSED_AUTHORIZATION_REFERENCE
    assert len(plan.cached_responses) == 5 and len(plan.requests) == plan.maximum_requests == 13
    assert [p.capture_bytes for p in plan.per_request_limits] == [4_000_000] + [2_000_000] * 12
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "raw.githubusercontent.com":
            assert str(request.url) == ACL_2023_URL
            return streamed(body)
        return source_handler(request)

    output = tmp_path / "recovered"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(plan.plan, output, client, "synthetic-approved-exception", resource=plan)
    assert result.stopped_reason is None and len(calls) == 7
    assert calls.count(ACL_2023_URL) == 1
    assert load_run(output) == result
    frame = build_frame(output)
    assert frame == build_frame(output) and frame.origin == "simulated"
    assert len(frame.items) == 54 and len(frame.panel_ids) == 18
    review = PilotReview(
        frame_id=frame.frame_id,
        origin="simulated",
        identifier_inspection_protocol="Synthetic fixed source inventory",
        decisions=tuple(
            PilotDecision(
                source_id=i.source_id,
                disposition="include",
                reason="Synthetic test approval only",
                reviewer_id="synthetic-reviewer",
                reviewed_at=END,
                language="en",
                metadata_verified=True,
                identity_verified=True,
                canonical=CitationValues(
                    title=i.candidate.title,
                    authors=(Author(given="Invented", family="Fixture"),),
                    year=i.candidate.year,
                    doi=i.candidate.doi,
                    arxiv_id=i.candidate.arxiv_id,
                ),
            )
            for i in frame.items
            if i.source_id in frame.panel_ids
        ),
    )
    selected = select_pilot(output, frame, review)
    assert selected["shortfalls"] == {"doi_only": 0, "arxiv_only": 0, "dual": 2}
    assert all(p.read_bytes() == value for p, value in before.items())
    assert load_run(source).stopped_reason is not None
    assert (source / "attempt-006/request-001/body.bin").stat().st_size == 2_000_000
    volumes = json.loads((output / "scope-volumes.json").read_bytes())
    assert volumes["collections"]["acl-2023.acl"]["processing_bound_bytes"] == 4_000_000
    assert volumes["collections"]["acl-2023.acl"]["selected_source_volume_ids"] == ["long", "short"]
    replay = tmp_path / "replay.json"
    assert main(["pilot-replay", str(output), "--output", str(replay)]) == 0
    assert replay.read_bytes() == json_bytes(frame.model_dump(mode="json"))
    with pytest.raises(ValueError, match="one-time exception"):
        make_resource_continuation(output)


@pytest.mark.parametrize(
    "url",
    [
        ACL_2023_URL.replace("2023.acl", "2022.acl"),
        ACL_2023_URL.replace("032cc14d4a17181e8754f33512c22ff53d9cbbc6", "a" * 40),
        ACL_2023_URL + "?extra=1",
    ],
)
def test_four_mb_cannot_leak_to_other_requests(tmp_path: Path, url: str) -> None:
    plan = budget(url)
    directory = tmp_path / "batch"
    begin_batch(directory, plan)
    calls = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("Disallowed override reached HTTP transport")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(ValueError, match="exact pinned"):
            capture_sync(client, directory, plan, 1, raw_limit=4_000_000)
    assert not calls and not (directory / "request-001").exists()


def test_default_cap_and_explicit_override_and_decoded_xml_bounds(tmp_path: Path) -> None:
    data = large_xml()
    plan = budget()
    for name, limit, complete in [("old", 2_000_000, False), ("new", 4_000_000, True)]:
        directory = tmp_path / name
        begin_batch(directory, plan)
        with httpx.Client(transport=httpx.MockTransport(lambda _: streamed(data))) as client:
            record = capture_sync(client, directory, plan, 1, raw_limit=limit)
        finish_batch(directory)
        verify_batch(directory)
        assert record.body_complete == complete
        assert (directory / "request-001/body.bin").stat().st_size == min(len(data), limit)
        if complete:
            with pytest.raises(ValueError, match="Decoded"):
                decoded_body(record, data)
            assert decoded_body(record, data, limit=4_000_000) == data
            with pytest.raises(ValueError):
                xml_root(data.decode())
            xml_root(data.decode(), limit=4_000_000)
            row = PilotRequest(
                key="acl-2023.acl",
                group="acl-2023.acl",
                collection="2023.acl",
                request=plan.requests[0],
            )
            assert len(scoped_collection(data.decode(), row, limit=4_000_000).items) == 4


def test_decoded_compression_bomb_is_bounded(tmp_path: Path) -> None:
    data = gzip.compress(b"x" * 4_000_001)
    plan = budget()
    directory = tmp_path / "gzip"
    begin_batch(directory, plan)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: streamed(data, encoding="gzip"))
    ) as client:
        record = capture_sync(client, directory, plan, 1, raw_limit=4_000_000)
    finish_batch(directory)
    assert record.body_complete
    with pytest.raises(ValueError, match="Decoded"):
        decoded_body(record, data, limit=4_000_000)


@pytest.mark.parametrize("failure", ["prefix_change", "oversize"])
def test_recovery_error_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source, body = resource_failure(tmp_path, monkeypatch)
    plan = make_resource_continuation(source)
    data = (
        body.replace(b"Synthetic", b"synthetic", 1)
        if failure == "prefix_change"
        else large_xml(4_000_001)
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return streamed(data)

    output = tmp_path / "stopped"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        run = execute(plan.plan, output, client, "synthetic-exception", resource=plan)
    assert len(calls) == 1 and run.stopped_reason
    assert load_run(output) == run
    with pytest.raises(ValueError):
        build_frame(output)


def test_async_explicit_limit_and_raw_replay(tmp_path: Path) -> None:
    data = large_xml()
    plan = budget()
    directory = tmp_path / "async"
    begin_batch(directory, plan)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: streamed(data))
        ) as client:
            record = await capture_async(client, directory, plan, 1, raw_limit=4_000_000)
            assert record.body_complete

    asyncio.run(run())
    finish_batch(directory)
    verify_batch(directory)


def test_limit_tampering_and_live_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, _ = resource_failure(tmp_path, monkeypatch)
    plan = make_resource_continuation(source)
    limits = list(plan.per_request_limits)
    limits[1] = limits[1].model_copy(update={"capture_bytes": 4_000_000})
    with pytest.raises(ValueError):
        validate_resource_continuation(
            plan.model_copy(update={"per_request_limits": tuple(limits)})
        )
    path = tmp_path / "plan.json"
    assert (
        main(
            ["pilot-plan-resource-continuation", "--source-run", str(source), "--output", str(path)]
        )
        == 0
    )
    assert (
        main(
            [
                "pilot-continue",
                str(path),
                "--authorization-reference",
                "not-approved",
                "--plan-sha256",
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "--output-dir",
                str(tmp_path / "no-network"),
            ]
        )
        != 0
    )
    assert not (tmp_path / "no-network").exists()
    assert (
        main(
            [
                "pilot-continue",
                str(path),
                "--authorize-live",
                "--authorization-reference",
                "wrong-reference",
                "--plan-sha256",
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "--output-dir",
                str(tmp_path / "wrong-authorization"),
            ]
        )
        != 0
    )
    assert not (tmp_path / "wrong-authorization").exists()
