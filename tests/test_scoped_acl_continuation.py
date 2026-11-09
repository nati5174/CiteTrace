"""Approved scope, explicit volume lineage and fourteen-slot mocked continuation."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import pytest
from pilot_helpers import b_plan, response, source_handler

from citeprobe.acl_scope import scoped_collection
from citeprobe.cli import main
from citeprobe.evidence_io import json_bytes
from citeprobe.pilot_continuation import OLD_STOP
from citeprobe.pilot_models import PilotRequest
from citeprobe.pilot_run import build_frame, execute, load_run
from citeprobe.pilot_scope_continuation import (
    SCOPE_STOP,
    make_scoped_continuation,
    validate_scoped_continuation,
)


def xml(collection: str, names: tuple[str, ...], *, title: str | None = None) -> bytes:
    root = ET.Element("collection", id=collection)
    year = "20" + collection[1:] if collection.startswith("P") else collection[:4]
    for name in (*names, "findings", "demos", "srw", "tutorials", "industry"):
        volume = ET.SubElement(root, "volume", id=name, type="proceedings")
        meta = ET.SubElement(volume, "meta")
        ET.SubElement(meta, "year").text = year
        ET.SubElement(meta, "booktitle").text = title or (
            "Proceedings of the Annual Meeting of the Association for Computational Linguistics"
        )
        for number in range(2):
            paper = ET.SubElement(volume, "paper", id=str(number))
            # Invented IDs explicitly declared by the synthetic source, never presented as observed.
            ET.SubElement(paper, "url").text = f"synthetic-{collection}-{name}.{number}"
            ET.SubElement(paper, "title").text = f"Synthetic {collection} {name} {number}"
            author = ET.SubElement(paper, "author")
            ET.SubElement(author, "first").text = "Invented"
            ET.SubElement(author, "last").text = "Fixture"
            ET.SubElement(paper, "doi").text = f"10.1234/synthetic.{collection}.{name}.{number}"
    return ET.tostring(root)


def row(collection: str) -> PilotRequest:
    return PilotRequest(
        key="acl-" + collection,
        group="acl-" + collection,
        collection=collection,
        volume_filter="main",
        request={"url": "https://example.org/synthetic.xml", "source_kind": "acquisition_xml"},
    )


@pytest.mark.parametrize("names", [("main",), ("long", "short")])
def test_prospective_main_or_split_selection(names: tuple[str, ...]) -> None:
    selection = scoped_collection(xml("2022.acl", names).decode(), row("2022.acl"))
    assert selection.selected_volume_ids == names
    assert len(selection.items) == 2 * len(names)
    assert set(selection.source_record_volumes.values()) == set(names)
    assert set(selection.excluded_volume_ids) == {
        "findings",
        "demos",
        "srw",
        "tutorials",
        "industry",
    }


@pytest.mark.parametrize(
    "names",
    [(), ("long",), ("short",), ("main", "long"), ("main", "long", "short"), ("main", "main")],
)
def test_ambiguous_volume_layout_stops(names: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        scoped_collection(xml("2023.acl", names).decode(), row("2023.acl"))


@pytest.mark.parametrize(
    "title",
    [
        "Findings of the Annual Meeting of the Association for Computational Linguistics",
        "Annual Meeting of the Association for Computational Linguistics: Industry Track",
        "Unknown proceedings",
    ],
)
def test_misleading_or_missing_main_research_metadata_stops(title: str) -> None:
    with pytest.raises(ValueError, match="metadata"):
        scoped_collection(xml("2022.acl", ("main",), title=title).decode(), row("2022.acl"))


def four_response_failure(directory: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("time.sleep", lambda _: None)
    plan = b_plan(directory / "pin")
    original = directory / "original"

    def legacy(*args: object) -> None:
        raise ValueError(OLD_STOP)

    with monkeypatch.context() as context:
        context.setattr("citeprobe.pilot_run.collection_items", legacy)
        with httpx.Client(
            transport=httpx.MockTransport(lambda _: response(xml("P18", ("1",)), "application/xml"))
        ) as client:
            execute(plan, original, client, "synthetic-original")

    def handler(request: httpx.Request) -> httpx.Response:
        collection = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
        names = {"P19": ("1",), "2020.acl": ("main",), "2021.acl": ("long", "short")}[collection]
        return response(xml(collection, names), "application/xml")

    failed = directory / "scope-failed"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        run = execute(plan, failed, client, "synthetic-first-continuation", reuse_from=original)
    assert run.stopped_reason == SCOPE_STOP and len(run.attempts) == 4
    return failed


def test_four_cache_reuse_complete_frame_and_explicit_volumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = four_response_failure(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    plan = make_scoped_continuation(source)
    validate_scoped_continuation(plan)
    assert len(plan.cached_responses) == 4 and len(plan.requests) == plan.maximum_requests == 14
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "raw.githubusercontent.com":
            collection = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
            assert collection in {"2022.acl", "2023.acl"}
            names = ("main",) if collection == "2022.acl" else ("long", "short")
            return response(xml(collection, names), "application/xml")
        return source_handler(request)

    output = tmp_path / "amended"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(plan.plan, output, client, "synthetic-amended", scoped=plan)
    assert not result.stopped_reason and len(calls) == 8
    assert load_run(output) == result
    frame = build_frame(output)
    assert frame == build_frame(output) and len(frame.items) == 52 and len(frame.panel_ids) == 18
    assert frame.origin == "simulated" and frame.plan_id == plan.continuation_id
    volumes = json.loads((output / "scope-volumes.json").read_bytes())["collections"]
    assert volumes["acl-2021.acl"]["selected_source_volume_ids"] == ["long", "short"]
    assert set(volumes["acl-2021.acl"]["source_record_volumes"].values()) == {"long", "short"}
    assert volumes["acl-2023.acl"]["selected_source_volume_ids"] == ["long", "short"]
    assert all(p.read_bytes() == value for p, value in before.items())
    replay = tmp_path / "replay.json"
    assert main(["pilot-replay", str(output), "--output", str(replay)]) == 0
    assert replay.read_bytes() == json_bytes(frame.model_dump(mode="json"))
    (output / "scope-volumes.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="manifest"):
        load_run(output)


@pytest.mark.parametrize("change", ["maximum_requests", "requests", "scope_amendment_sha256"])
def test_new_plan_tampering_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    source = four_response_failure(tmp_path, monkeypatch)
    plan = make_scoped_continuation(source)
    updates = {
        "maximum_requests": 15,
        "requests": plan.plan.requests,
        "scope_amendment_sha256": "0" * 64,
    }
    with pytest.raises(ValueError):
        validate_scoped_continuation(plan.model_copy(update={change: updates[change]}))


def test_cli_plan_and_authorization_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = four_response_failure(tmp_path, monkeypatch)
    output = tmp_path / "plan.json"
    assert (
        main(
            ["pilot-plan-scoped-continuation", "--source-run", str(source), "--output", str(output)]
        )
        == 0
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert (
        main(
            [
                "pilot-continue",
                str(output),
                "--authorization-reference",
                "not-approved",
                "--plan-sha256",
                digest,
                "--output-dir",
                str(tmp_path / "no-network"),
            ]
        )
        != 0
    )
    assert not (tmp_path / "no-network").exists()


def test_saved_four_responses_amended_counts() -> None:
    source = Path("artifacts/empirical-pilot-immediate-001/b-continuation-001")
    plan = make_scoped_continuation(source)
    validate_scoped_continuation(plan)
    assert [c.parsed_source_records for c in plan.cached_responses] == [256, 660, 778, 710]
    assert plan.cached_responses[3].selected_volume_ids == ("long", "short")


@pytest.mark.parametrize("conflict", ["venue", "year"])
def test_contradictory_selected_volume_metadata_stops(conflict: str) -> None:
    tree = ET.fromstring(xml("2022.acl", ("main",)))
    meta = tree.find("volume/meta")
    assert meta is not None
    if conflict == "venue":
        ET.SubElement(meta, "venue").text = "findings"
    else:
        year = meta.find("year")
        assert year is not None
        year.text = "2019"
    with pytest.raises(ValueError, match="metadata"):
        scoped_collection(ET.tostring(tree, encoding="unicode"), row("2022.acl"))
