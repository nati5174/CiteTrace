"""Explicit source comments are evidence; paper numbers and DOI suffixes are not."""

from pathlib import Path

import pytest

from citeprobe.acquisition_sources import ACLXml, metadata_projection
from citeprobe.pilot_run import collection_items, load_run, response_body


def document(identifier: str) -> str:
    return (
        '<collection id="P18"><volume id="1"><meta><year>2018</year></meta>'
        "<frontmatter><!-- https://aclanthology.org/P18-1000/ --></frontmatter>"
        '<paper id="1">' + identifier + "<title>Synthetic paper</title>"
        "<author><first>Invented</first><last>Fixture</last></author>"
        "<doi>10.1234/not-an-acl-id</doi></paper></volume></collection>"
    )


def test_explicit_comment_and_projection_round_trip() -> None:
    body = document("<!-- https://aclanthology.org/P18-1001/ -->")
    original = body
    adapter = ACLXml()
    for value in (body, metadata_projection(body)):
        records, count = adapter.records(value)
        assert count == 1
        citation = adapter.candidate(records[0])
        assert citation.source_record_id == "P18-1001"
        assert citation.doi == "10.1234/not-an-acl-id"
    assert body == original


@pytest.mark.parametrize(
    "declaration",
    [
        "",
        "<!-- https://example.org/P18-1001/ -->",
        "<!-- unrelated text -->",
        "<!-- https://aclanthology.org/P18-1001/?credential=bad -->",
        "<url>P18-1002</url><!-- https://aclanthology.org/P18-1001/ -->",
        "<url>P18-1001</url><url>P18-1002</url>",
    ],
)
def test_never_infer_or_accept_conflicting_identifiers(declaration: str) -> None:
    record = ACLXml().records(document(declaration))[0][0]
    with pytest.raises(ValueError):
        ACLXml().candidate(record)


def test_saved_p18_response_parses_without_recapture() -> None:
    source = Path("artifacts/empirical-pilot-immediate-001/b-enumeration-001")
    run = load_run(source)
    assert run.stopped_reason == "Missing explicit ACL identifier; do not infer record IDs"
    body, _ = response_body(source / "attempt-001", run.plan.requests[0], "observed")
    items = collection_items(body, run.plan.requests[0])
    assert len(items) == len({i.source_id for i in items}) == 256
    assert items[0].source_id == "acl:P18-1001"
    assert items[-1].source_id == "acl:P18-1256"
    assert (source / "run.json").read_bytes().find(b"Missing explicit ACL identifier") >= 0
