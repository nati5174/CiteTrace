"""Saved source inspection must not silently broaden an approved sampling scope."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from citeprobe.acquisition_sources import ACLXml, xml_root
from citeprobe.pilot_run import collection_items, load_run, response_body

ROOT = Path("artifacts/empirical-pilot-immediate-001")


def test_missing_main_remains_a_stop_condition() -> None:
    directory = ROOT / "b-continuation-001"
    run = load_run(directory)
    assert len(run.attempts) == 4
    assert run.stopped_reason == "Required ACL volume absent or duplicated; no silent substitution"
    row = run.plan.requests[3]
    assert row.collection == "2021.acl" and row.volume_filter == "main"
    body, record = response_body(directory / "attempt-004", row, run.plan.origin)
    assert record.http_status == 200 and record.body_complete
    tree = xml_root(body, preserve_comments=True)
    assert tree.get("id") == "2021.acl"
    volumes = [v.get("id") for v in tree.findall("volume")]
    assert len(volumes) == len(set(volumes))
    assert "main" not in volumes and {"long", "short"} <= set(volumes)
    with pytest.raises(ValueError, match="no silent substitution"):
        collection_items(body, row)


def test_inspection_of_declared_volumes_does_not_change_plan() -> None:
    directory = ROOT / "b-continuation-001"
    run = load_run(directory)
    before = (directory / "plan.json").read_bytes()
    body, _ = response_body(directory / "attempt-004", run.plan.requests[3], run.plan.origin)
    tree = xml_root(body, preserve_comments=True)
    inspected = {}
    for volume in tree.findall("volume"):
        key = volume.get("id")
        if key not in {"long", "short"}:
            continue
        wrapper = ET.Element("collection", tree.attrib)
        wrapper.append(volume)
        records, _ = ACLXml().records(ET.tostring(wrapper, encoding="unicode"))
        citations = [ACLXml().candidate(r) for r in records]
        inspected[key] = citations
        assert len(citations) == len({c.source_record_id for c in citations})
    assert len(inspected["long"]) == 571 and len(inspected["short"]) == 139
    assert inspected["long"][0].source_url == "https://aclanthology.org/2021.acl-long.1/"
    assert inspected["short"][0].source_url == "https://aclanthology.org/2021.acl-short.1/"
    assert (directory / "plan.json").read_bytes() == before


def test_reused_p18_is_not_counted_as_an_extra_request() -> None:
    old = ROOT / "b-enumeration-001/attempt-001"
    cached = ROOT / "b-continuation-001/attempt-001"
    files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
    assert files == {p.relative_to(cached) for p in cached.rglob("*") if p.is_file()}
    assert all((old / p).read_bytes() == (cached / p).read_bytes() for p in files)
    run = load_run(ROOT / "b-continuation-001")
    assert len(run.plan.requests) - len(run.attempts) == 14
