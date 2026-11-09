import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from citeprobe.benchmark_key_continuation import prepare, run, verify_output

ROOT = Path("artifacts/empirical-pilot-immediate-001")
SNAPSHOT = ROOT / "a-frozen-001"
PRIOR = ROOT / "a-benchmark-smoke-002"
STOPPED = ROOT / "a-benchmark-remaining-001"
KEY = "synthetic-secret-key-only-for-tests"


@pytest.fixture
def plan() -> dict[str, Any]:
    return prepare(SNAPSHOT, PRIOR, STOPPED)


@pytest.mark.parametrize("stop_at", [None, 1, 2, 8])
def test_key_scope_budget_replay_and_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any], stop_at: int | None
) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    monkeypatch.delenv("CROSSREF_API_KEY", raising=False)
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)

    async def no_wait(_: float) -> None:
        pass

    monkeypatch.setattr("citeprobe.benchmark_key_continuation.asyncio.sleep", no_wait)
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host or "", request.url.params.get("api_key", "")))
        assert "authorization" not in request.headers
        assert seen[-1][1] == (KEY if request.url.host == "api.openalex.org" else "")
        body = (
            b'{"results":[]}'
            if request.url.host == "api.openalex.org"
            else b'{"status":"ok","message":{"items":[]}}'
        )
        if len(seen) == stop_at:
            return httpx.Response(429, stream=httpx.ByteStream(b"rate limited"))
        return httpx.Response(200, stream=httpx.ByteStream(body))

    output = tmp_path / "output"
    assert asyncio.run(
        run(SNAPSHOT, PRIOR, plan, output, STOPPED, transport=httpx.MockTransport(handler))
    ) is (stop_at is None)
    assert len(seen) == (14 if stop_at is None else stop_at)
    verify_output(output)
    receipt = json.loads((output / "receipt.json").read_bytes())
    assert (
        receipt["origin"] == "simulated" and receipt["openalex_access"] == "api_key_query_parameter"
    )
    for path in output.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(
            run(SNAPSHOT, PRIOR, plan, output, STOPPED, transport=httpx.MockTransport(handler))
        )
    body = next(output.glob("paper-*/attempt-*/body.bin"))
    body.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        verify_output(output)


def test_no_key_or_invalid_plan_never_calls_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any]
) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    with pytest.raises(ValueError, match="key required"):
        asyncio.run(run(SNAPSHOT, PRIOR, plan, tmp_path / "out", STOPPED))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("failure", ["partial", "network", "redirect", "header_echo"])
def test_failure_capture_and_no_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any], failure: str
) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    monkeypatch.delenv("CROSSREF_API_KEY", raising=False)
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    calls: list[str] = []

    class Partial(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"partial"
            raise httpx.ReadError(KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        if failure == "network":
            raise httpx.ConnectError(KEY)
        if failure == "partial":
            return httpx.Response(200, stream=Partial())
        if failure == "redirect":
            return httpx.Response(
                302,
                headers={"location": "https://example.org/"},
                stream=httpx.ByteStream(b"redirect"),
            )
        return httpx.Response(
            429, headers={"retry-after": KEY}, stream=httpx.ByteStream(b"limited")
        )

    output = tmp_path / "out"
    assert not asyncio.run(
        run(SNAPSHOT, PRIOR, plan, output, STOPPED, transport=httpx.MockTransport(handler))
    )
    assert len(calls) == 1
    record = json.loads((output / "paper-01/attempt-001/record.json").read_bytes())
    if failure == "partial":
        assert not record["complete"]
        assert (output / "paper-01/attempt-001/body.bin").read_bytes() == b"partial"
    for path in output.rglob("*.json"):
        assert KEY.encode() not in path.read_bytes()
    verify_output(output)
