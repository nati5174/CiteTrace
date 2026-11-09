"""A new bounded stage reuses one raw prefix; it never repeats the failed request."""

import hashlib
from pathlib import Path

import httpx
import pytest
from pilot_helpers import acl, b_plan, response, source_handler

from citeprobe.cli import main
from citeprobe.evidence_io import json_bytes
from citeprobe.pilot_continuation import OLD_STOP, make_continuation, validate_continuation
from citeprobe.pilot_run import build_frame, execute, load_run


def failed_prefix(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = b_plan(directory.parent / "pin")
    body = (
        acl("P18", "1", 2018)
        .replace(b"<url>", b"<!-- https://aclanthology.org/")
        .replace(b"</url>", b"/ -->")
    )

    def legacy_parser(*args: object) -> None:
        raise ValueError(OLD_STOP)

    with monkeypatch.context() as context:
        context.setattr("citeprobe.pilot_run.collection_items", legacy_parser)
        with httpx.Client(
            transport=httpx.MockTransport(lambda _: response(body, "application/xml"))
        ) as client:
            run = execute(plan, directory, client, "synthetic-original")
    assert run.stopped_reason == OLD_STOP and len(run.attempts) == 1


def test_cached_prefix_and_complete_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    source = tmp_path / "failed"
    failed_prefix(source, monkeypatch)
    original = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    plan = make_continuation(source)
    validate_continuation(plan)
    assert plan.maximum_requests == len(plan.requests) == 17
    assert all(r.collection != "P18" for r in plan.requests)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert not request.url.path.endswith("/P18.xml")
        if request.url.host == "raw.githubusercontent.com":
            name = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
            year = 2019 if name == "P19" else int(name[:4])
            return response(acl(name, "1" if year == 2019 else "main", year), "application/xml")
        return source_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute(
            plan.plan, tmp_path / "continued", client, "synthetic-continuation", reuse_from=source
        )
    assert result.stopped_reason is None
    assert len(calls) == 11  # Five ACL files plus six initial API pages; second pages unnecessary.
    assert load_run(tmp_path / "continued") == result
    frame = build_frame(tmp_path / "continued")
    assert len(frame.items) == 108 and len(frame.panel_ids) == 18
    assert frame == build_frame(tmp_path / "continued")
    assert all(p.read_bytes() == content for p, content in original.items())
    assert load_run(source).stopped_reason == OLD_STOP
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="outside the original"):
            execute(plan.plan, source / "unsafe-child", client, "synthetic", reuse_from=source)
    assert not (source / "unsafe-child").exists()
    output = tmp_path / "replay.json"
    assert main(["pilot-replay", str(tmp_path / "continued"), "--output", str(output)]) == 0
    assert output.read_bytes() == json_bytes(frame.model_dump(mode="json"))


@pytest.mark.parametrize("change", ["requests", "maximum_requests", "cached_body_sha256"])
def test_continuation_inventory_cannot_expand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    failed_prefix(tmp_path / "failed", monkeypatch)
    plan = make_continuation(tmp_path / "failed")
    values = {
        "requests": plan.plan.requests,
        "maximum_requests": 18,
        "cached_body_sha256": "0" * 64,
    }
    with pytest.raises(ValueError):
        validate_continuation(plan.model_copy(update={change: values[change]}))


def test_continuation_cli_requires_new_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_prefix(tmp_path / "failed", monkeypatch)
    plan = make_continuation(tmp_path / "failed")
    path = tmp_path / "continuation.json"
    path.write_bytes(json_bytes(plan.model_dump(mode="json")))
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
                str(tmp_path / "not-created"),
            ]
        )
        != 0
    )
    assert not (tmp_path / "not-created").exists()
