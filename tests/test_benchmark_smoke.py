import asyncio
import gzip
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from citeprobe.benchmark_smoke import Capture, run, verify

SNAPSHOT = Path("artifacts/empirical-pilot-immediate-001/a-frozen-001")


@pytest.mark.parametrize("status", [200, 301, 401, 429, 503])
def test_capture_and_stop(tmp_path: Path, status: int) -> None:
    calls = []
    bodies = [b'{ "results": [] }\n', b'{"status":"ok","message":{"items":[]}}']

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = bodies[len(calls) - 1] if status == 200 else b"<html>provider error\x00</html>"
        return httpx.Response(
            status, headers={"location": "https://example.org/"}, stream=httpx.ByteStream(body)
        )

    out = tmp_path / "run"
    assert asyncio.run(run(SNAPSHOT, out, transport=httpx.MockTransport(handler))) == (
        status == 200
    )
    assert len(calls) == (2 if status == 200 else 1)
    expected = bodies[0] if status == 200 else b"<html>provider error\x00</html>"
    assert (out / "attempt-001/body.bin").read_bytes() == expected
    assert "2611.07721" not in str(calls[0].url)
    assert "10.48550" not in str(calls[0].url)
    verify(out)
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    verify(out)
    assert all(p.read_bytes() == b for p, b in before.items())
    (out / "attempt-001/body.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        verify(out)


@pytest.mark.parametrize("failure", ["network", "partial", "length", "malformed", "limit"])
def test_failed_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    calls = []

    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"prefix"
            raise httpx.ReadError("private error details")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "network":
            raise httpx.ConnectError("private error details")
        if failure == "partial":
            return httpx.Response(200, stream=Broken())
        if failure == "limit":
            monkeypatch.setattr("citeprobe.benchmark_smoke.LIMIT", 3)
        return httpx.Response(
            200,
            headers={"content-length": "100"} if failure == "length" else {},
            stream=httpx.ByteStream(b"not-json"),
        )

    out = tmp_path / "run"
    assert not asyncio.run(run(SNAPSHOT, out, transport=httpx.MockTransport(handler)))
    assert len(calls) == 1
    record = json.loads((out / "attempt-001/record.json").read_bytes())
    assert record["complete"] == (failure == "malformed")
    assert b"private error details" not in (out / "attempt-001/record.json").read_bytes()
    if failure == "partial":
        assert (out / "attempt-001/body.bin").read_bytes() == b"prefix"
    verify(out)


def test_budget_and_inventory(tmp_path: Path) -> None:
    capture = Capture(
        httpx.MockTransport(lambda r: httpx.Response(200)),
        tmp_path,
        ["https://example.org/", "https://example.org/"],
    )
    with pytest.raises(ValueError, match="inventory"):
        asyncio.run(capture.handle_async_request(httpx.Request("GET", "https://other.org")))
    capture.count = 2
    with pytest.raises(ValueError, match="budget"):
        asyncio.run(capture.handle_async_request(httpx.Request("GET", "https://example.org/")))


def test_leak_rejected_before_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citeprobe.providers import ProviderRequest

    monkeypatch.setattr(
        "citeprobe.benchmark_smoke.OpenAlex.request",
        lambda *args: ProviderRequest("https://api.openalex.org/works", {"search": "2611.07721"}),
    )
    with pytest.raises(ValueError, match="leakage"):
        asyncio.run(
            run(
                SNAPSHOT,
                tmp_path / "run",
                transport=httpx.MockTransport(lambda r: httpx.Response(200)),
            )
        )
    assert not (tmp_path / "run").exists()


def test_encoded_candidates_credentials_and_output_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", "synthetic-secret-token")
    body = gzip.compress(
        b'{"results":[{"id":"https://openalex.org/W1","title":"Synthetic","publication_year":2026}]}',
        mtime=0,
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            assert request.headers["authorization"] == "Bearer synthetic-secret-token"
            return httpx.Response(
                200,
                headers={
                    "content-encoding": "gzip",
                    "content-length": str(len(body)),
                    "set-cookie": "private",
                },
                stream=httpx.ByteStream(body),
            )
        return httpx.Response(503, stream=httpx.ByteStream(b"unavailable"))

    out = tmp_path / "run"
    assert not asyncio.run(run(SNAPSHOT, out, transport=httpx.MockTransport(handler)))
    assert len(calls) == 2
    assert (out / "attempt-001/body.bin").read_bytes() == body
    verify(out)
    for p in out.rglob("*.json"):
        assert b"synthetic-secret-token" not in p.read_bytes()
        assert b"set-cookie" not in p.read_bytes()
    bundle = json.loads((out / "openalex-lookups.json").read_bytes())
    assert bundle["results"][0]["candidates"][0]["provider_rank"] == 1
    with pytest.raises(FileExistsError):
        asyncio.run(run(SNAPSHOT, out, transport=httpx.MockTransport(handler)))
    assert len(calls) == 2
