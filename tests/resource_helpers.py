"""Explicitly simulated size-limit failure; never relabel synthetic data observed."""

from pathlib import Path

import httpx
import pytest
from pilot_helpers import END, START, capture
from test_scoped_acl_continuation import xml

from citeprobe.evidence_models import EvidenceRequest
from citeprobe.pilot_continuation import OLD_STOP
from citeprobe.pilot_pin import COMMIT_URL, pin_revision
from citeprobe.pilot_plans import make_plan
from citeprobe.pilot_run import execute
from citeprobe.pilot_scope_continuation import make_scoped_continuation


def streamed(body: bytes, *, encoding: str | None = None) -> httpx.Response:
    headers = {"content-type": "text/plain; charset=utf-8", "content-length": str(len(body))}
    if encoding:
        headers["content-encoding"] = encoding
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


def large_xml(size: int = 2_100_000) -> bytes:
    base = xml("2023.acl", ("long", "short"))
    return base + b"<!--" + b"x" * (size - len(base) - 7) + b"-->"


def resource_failure(directory: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, bytes]:
    monkeypatch.setattr("time.sleep", lambda _: None)
    proof = directory / "pin"
    # The approved URL is exercised against MockTransport; the evidence origin is simulated.
    capture(
        proof,
        EvidenceRequest(url=COMMIT_URL, source_kind="upstream_json"),
        b'[{"sha":"032cc14d4a17181e8754f33512c22ff53d9cbbc6"}]',
        "application/json",
    )
    pin = pin_revision(proof, "synthetic-only")
    plan = make_plan(
        "b_enumeration", "mutation-robustness-pilot", START, END, revision=pin, origin="simulated"
    )
    original = directory / "original"

    def old_parser(*args: object) -> None:
        raise ValueError(OLD_STOP)

    with monkeypatch.context() as context:
        context.setattr("citeprobe.pilot_run.collection_items", old_parser)
        with httpx.Client(
            transport=httpx.MockTransport(lambda _: streamed(xml("P18", ("1",))))
        ) as client:
            execute(plan, original, client, "synthetic-original")

    def scope_handler(request: httpx.Request) -> httpx.Response:
        collection = request.url.path.rsplit("/", 1)[1].removesuffix(".xml")
        names = {"P19": ("1",), "2020.acl": ("main",), "2021.acl": ("long", "short")}[collection]
        return streamed(xml(collection, names))

    failed_scope = directory / "scope-failed"
    with httpx.Client(transport=httpx.MockTransport(scope_handler)) as client:
        execute(plan, failed_scope, client, "synthetic-scope", reuse_from=original)
    scoped = make_scoped_continuation(failed_scope)
    body = large_xml()

    def size_handler(request: httpx.Request) -> httpx.Response:
        return streamed(
            body
            if request.url.path.endswith("/2023.acl.xml")
            else xml("2022.acl", ("long", "short"))
        )

    failed = directory / "size-failed"
    with httpx.Client(transport=httpx.MockTransport(size_handler)) as client:
        run = execute(plan, failed, client, "synthetic-size-stage", scoped=scoped)
    assert run.stopped_reason and len(run.attempts) == 6
    return failed, body
