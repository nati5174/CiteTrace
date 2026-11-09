"""Raw evidence regression fixtures and HTTP mocks only. No live requests."""

import asyncio
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from citeprobe.cli import main
from citeprobe.evidence_extract import extract
from citeprobe.evidence_io import (
    begin_batch,
    capture_async,
    capture_sync,
    finish_batch,
    json_bytes,
    verify_batch,
)
from citeprobe.evidence_models import EvidenceBudget, EvidenceRequest, RawEvidence, SourceKind

ROOT = Path("tests/fixtures/evidence-v2")


def budget(kind: SourceKind = "arxiv_api_doc", count: int = 1) -> EvidenceBudget:
    return EvidenceBudget(
        budget_id="synthetic-budget-1",
        authorization_reference="synthetic-test-only",
        origin="simulated",
        maximum_requests=count,
        requests=tuple(
            EvidenceRequest(url=f"https://example.org/source-{i}", source_kind=kind)
            for i in range(count)
        ),
    )


def captured(
    tmp_path: Path,
    filename: str = "api.html",
    *,
    kind: SourceKind = "arxiv_api_doc",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    status: int = 200,
) -> tuple[Path, RawEvidence, bytes]:
    raw = body if body is not None else (ROOT / filename).read_bytes()
    directory = tmp_path / "batch"
    plan = budget(kind)
    begin_batch(directory, plan)
    meta = {
        "content-type": "text/html; charset=utf-8"
        if kind.endswith("doc")
        else "application/atom+xml",
        "content-length": str(len(raw)),
        **(headers or {}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(status, headers=meta, stream=httpx.ByteStream(raw))

    with httpx.Client(
        transport=httpx.MockTransport(handler), auth=("private", "credential")
    ) as client:
        record = capture_sync(client, directory, plan, 1)
    finish_batch(directory)
    return directory, record, raw


def payload(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "request-001/extracted.json").read_bytes())["payload"]
    assert isinstance(value, dict)
    return value


def test_navigation_does_not_hide_body_definitions(tmp_path: Path) -> None:
    directory, record, raw = captured(tmp_path)
    data = payload(directory)
    statements = data["statements"]
    joined = " ".join(s["text"] for s in statements)
    assert "submission event" in joined and "most recent version" in joined
    assert "max_results" in joined and "revisions" in joined
    assert "navigation bait" not in joined and "contents bait" not in joined
    assert all(s["location"]["line"] > 0 and s["location"]["dom_path"] for s in statements)
    assert any(s["source_url"].endswith("#entry-dates") for s in statements)
    assert data["relevant_links_not_fetched"][0]["url_not_fetched"].endswith(
        "atom_specifications.html"
    )
    assert (directory / "request-001/body.bin").read_bytes() == raw
    assert record.raw_body_sha256 == hashlib.sha256(raw).hexdigest()
    assert (
        record.http_status == 200
        and record.body_complete
        and record.final_url == record.request.url
    )
    assert (
        record.headers_received_at
        and record.started_at <= record.headers_received_at <= record.finished_at
    )


def test_rss_statements_preserved_without_invented_retention(tmp_path: Path) -> None:
    directory, _, _ = captured(tmp_path, "rss.html", kind="arxiv_rss_doc")
    text = " ".join(s["text"] for s in payload(directory)["statements"])
    assert "does not specify historical" in text and "timezone" in text
    assert "navigation bait" not in text


def test_empty_feed_preserves_feed_metadata(tmp_path: Path) -> None:
    directory, _, _ = captured(tmp_path, "empty.atom", kind="arxiv_atom")
    data = payload(directory)
    assert data["empty_feed"] is True and data["entry_count"] == 0
    assert data["feed"]["updated"][0]["utc"] == "2025-01-02T00:00:00+00:00"
    assert data["feed"]["subtitle"][0]["raw"] == "No entries in this synthetic snapshot"


@pytest.mark.parametrize("namespace", ["prefixed", "default", "none"])
def test_entries_namespace_and_source_locations(tmp_path: Path, namespace: str) -> None:
    body = (ROOT / "nonempty.atom").read_bytes()
    if namespace == "default":
        body = body.replace(b"xmlns:a=", b"xmlns=").replace(b"a:", b"")
    if namespace == "none":
        body = body.replace(b' xmlns:a="http://www.w3.org/2005/Atom"', b"").replace(b"a:", b"")
    directory, _, _ = captured(tmp_path, body=body, kind="arxiv_atom")
    data = payload(directory)
    assert data["entry_count"] == 1 and not data["empty_feed"]
    entry = data["entries"][0]
    assert entry["id"][0]["raw"] == "synthetic-entry"
    assert entry["published"][0]["xml_path"] == "/feed/entry[1]/published[1]"
    assert entry["primary_category"][0]["attributes"]["term"] == "cs.CL"
    assert entry["announce_type"][0]["raw"] == "new"


@pytest.mark.parametrize("value", ["not-a-date", "2025-01-01T00:00:00", ""])
def test_malformed_dates_not_invented(tmp_path: Path, value: str) -> None:
    body = (ROOT / "nonempty.atom").read_text().replace("2025-01-01T00:00:00Z", value).encode()
    directory, record, raw = captured(tmp_path, body=body, kind="arxiv_atom")
    assert payload(directory)["entries"][0]["published"][0]["utc"] is None
    assert any("timestamp" in w for w in extract(record, raw).warnings)


@pytest.mark.parametrize(
    "case", ["type", "malformed", "length", "missing_metadata", "no_content_type"]
)
def test_missing_and_unexpected_evidence(tmp_path: Path, case: str) -> None:
    body = (ROOT / "nonempty.atom").read_bytes()
    headers = {}
    if case == "type":
        headers = {"content-type": "application/json"}
    if case == "malformed":
        body = b"<feed"
    if case == "length":
        headers = {"content-length": str(len(body) + 20)}
    if case == "missing_metadata":
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'
    if case == "no_content_type":
        headers = {"content-type": ""}
    directory, record, raw = captured(tmp_path, body=body, kind="arxiv_atom", headers=headers)
    result = extract(record, raw)
    if case in {"type", "malformed", "length"}:
        assert result.status == "UNAVAILABLE"
    else:
        assert result.status == "EXTRACTED" and result.warnings
    if case == "length":
        assert not record.body_complete
    assert verify_batch(directory)[0] == result


def test_encoded_bytes_are_raw_and_sensitive_headers_omitted(tmp_path: Path) -> None:
    compressed = gzip.compress((ROOT / "api.html").read_bytes(), mtime=0)
    directory, record, raw = captured(
        tmp_path,
        body=compressed,
        headers={
            "content-encoding": "gzip",
            "set-cookie": "session=private",
            "authorization": "secret",
            "x-api-key": "hidden",
        },
    )
    assert raw == compressed and (directory / "request-001/body.bin").read_bytes() == compressed
    assert "submission event" in str(payload(directory))
    saved = (directory / "request-001/record.json").read_text()
    assert "session=private" not in saved and "hidden" not in saved and "secret" not in saved
    assert record.content_encoding == "gzip"


@pytest.mark.parametrize("name", ["body.bin", "record.json", "extracted.json"])
def test_tampering_detected(tmp_path: Path, name: str) -> None:
    directory, _, _ = captured(tmp_path)
    (directory / "request-001" / name).write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_batch(directory)


def test_replay_and_external_anchor_and_output_protection(tmp_path: Path) -> None:
    directory, record, raw = captured(tmp_path)
    assert (
        json_bytes(extract(record, raw).model_dump(mode="json"))
        == (directory / "request-001/extracted.json").read_bytes()
    )
    anchor = hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
    verify_batch(directory, anchor=anchor)
    with pytest.raises(ValueError):
        verify_batch(directory, anchor="0" * 64)
    for name in ("replay1.json", "replay2.json"):
        assert (
            main(
                [
                    "evidence-verify",
                    str(directory),
                    "--manifest-sha256",
                    anchor,
                    "--replay-output",
                    str(tmp_path / name),
                ]
            )
            == 0
        )
    assert (tmp_path / "replay1.json").read_bytes() == (tmp_path / "replay2.json").read_bytes()
    assert (
        main(
            [
                "evidence-verify",
                str(directory),
                "--replay-output",
                str(directory / "overwrite.json"),
            ]
        )
        == 1
    )


def test_budget_guards_credentials_and_async_capture(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EvidenceRequest(url="https://example.org/?api_key=secret", source_kind="arxiv_atom")
    with pytest.raises(ValueError):
        EvidenceRequest(url="https://user:pass@example.org/", source_kind="arxiv_atom")
    plan = budget("arxiv_atom")
    directory = tmp_path / "async"
    begin_batch(directory, plan)
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/atom+xml"},
            stream=httpx.ByteStream((ROOT / "empty.atom").read_bytes()),
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            await capture_async(client, directory, plan, 1)
            with pytest.raises(FileExistsError):
                await capture_async(client, directory, plan, 1)
            with pytest.raises(ValueError):
                await capture_async(client, directory, plan, 2)

    asyncio.run(run())
    finish_batch(directory)
    assert len(calls) == 1 and verify_batch(directory)[0].status == "EXTRACTED"


@pytest.mark.parametrize("mode", ["timeout", "connect", "oversized", "short_stream", "redirect"])
def test_failed_and_partial_raw_evidence_is_honest(tmp_path: Path, mode: str) -> None:
    from collections.abc import Iterator

    class Broken(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"partial-prefix"
            raise httpx.ReadError("Synthetic truncated response")

    plan = budget()
    directory = tmp_path / "failure"
    begin_batch(directory, plan)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        if mode == "connect":
            raise httpx.ConnectError("Synthetic connection failure")
        if mode == "short_stream":
            return httpx.Response(200, stream=Broken())
        if mode == "redirect":
            return httpx.Response(
                302,
                headers={"location": "https://example.org/other"},
                stream=httpx.ByteStream(b"redirect-body"),
            )
        return httpx.Response(200, stream=httpx.ByteStream(b"x" * 2_000_001))

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        record = capture_sync(client, directory, plan, 1)
    finish_batch(directory)
    assert len(calls) == 1 and verify_batch(directory)[0].status == "UNAVAILABLE"
    if mode == "short_stream":
        assert (directory / "request-001/body.bin").read_bytes() == b"partial-prefix"
    if mode != "redirect":
        assert not record.body_complete
    assert (
        record.raw_body_sha256
        == hashlib.sha256((directory / "request-001/body.bin").read_bytes()).hexdigest()
    )


def test_empty_extraction_does_not_prove_missing_documentation(tmp_path: Path) -> None:
    directory, _, _ = captured(tmp_path, body=b"<main><p>Only synthetic cats here.</p></main>")
    assert payload(directory)["statements"] == []
    result = verify_batch(directory)[0]
    assert result.status == "EXTRACTED"
    assert any("not proof" in warning for warning in result.warnings)


def test_manifest_and_provenance_tampering_even_after_file_rehash(tmp_path: Path) -> None:
    directory, _, _ = captured(tmp_path)
    file = directory / "request-001/extracted.json"
    saved = json.loads(file.read_bytes())
    saved["source_url"] = "https://example.org/false-source"
    file.write_bytes(json_bytes(saved))
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["request-001/extracted.json"] = hashlib.sha256(file.read_bytes()).hexdigest()
    manifest_path.write_bytes(json_bytes(manifest))
    with pytest.raises(ValueError, match="provenance"):
        verify_batch(directory)


def test_future_acquisition_cli_keeps_raw_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_acquisition import plan

    from citeprobe.acquisition import replay_acquisition
    from citeprobe.acquisition_cli import live

    body = Path("tests/fixtures/acquisition/arxiv.xml").read_bytes()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, headers={"content-type": "application/atom+xml"}, stream=httpx.ByteStream(body)
        )

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(handler))
    response = asyncio.run(
        live(plan(), "synthetic-approval", tmp_path / "http-evidence", origin="simulated")
    )
    assert len(calls) == 1 and response.origin == "simulated"
    assert len(replay_acquisition(response).items) == 2
    assert (tmp_path / "http-evidence/request-001/body.bin").read_bytes() == body
    assert verify_batch(tmp_path / "http-evidence")[0].status == "EXTRACTED"


def test_legacy_projection_cannot_be_promoted_to_raw_evidence(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": "1.0", "urls": []}))
    with pytest.raises(ValueError, match="legacy projections"):
        verify_batch(tmp_path)


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_truncated_compression_is_not_successful_extraction(tmp_path: Path, encoding: str) -> None:
    import zlib

    body = (ROOT / "api.html").read_bytes()
    compressed = gzip.compress(body, mtime=0) if encoding == "gzip" else zlib.compress(body)
    directory, record, raw = captured(
        tmp_path, body=compressed[:-4], headers={"content-encoding": encoding}
    )
    assert record.body_complete  # Complete transport bytes, but invalid encoded content.
    assert extract(record, raw).status == "UNAVAILABLE"
    assert verify_batch(directory)[0].status == "UNAVAILABLE"


def test_empty_completed_subset_is_not_claimed_as_complete_plan(tmp_path: Path) -> None:
    plan = budget(count=2)
    begin_batch(tmp_path / "subset", plan)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, stream=httpx.ByteStream(b"unavailable"))
        )
    ) as client:
        capture_sync(client, tmp_path / "subset", plan, 1)
    finish_batch(tmp_path / "subset")
    data = json.loads((tmp_path / "subset/manifest.json").read_bytes())
    assert data["attempt_count"] == 1 and data["planned_request_count"] == 2
    assert data["plan_complete"] is False
    assert len(verify_batch(tmp_path / "subset")) == 1


def test_declared_character_encoding_is_preserved(tmp_path: Path) -> None:
    raw = "<main><p>Published date for Caf\u00e9 is not supplied here.</p></main>".encode(
        "iso-8859-1"
    )
    directory, record, _ = captured(
        tmp_path, body=raw, headers={"content-type": "text/html; charset=iso-8859-1"}
    )
    assert record.character_encoding == "iso-8859-1"
    assert "Caf\u00e9" in payload(directory)["statements"][0]["text"]
    data = record.model_dump(mode="json")
    data["character_encoding"] = "utf-8"
    with pytest.raises(ValueError, match="encoding contradicts"):
        RawEvidence.model_validate(data)


@pytest.mark.parametrize("value", [[], None, False])
def test_malformed_manifest_is_rejected(tmp_path: Path, value: Any) -> None:
    (tmp_path / "manifest.json").write_bytes(json_bytes(value))
    with pytest.raises(ValueError):
        verify_batch(tmp_path)
