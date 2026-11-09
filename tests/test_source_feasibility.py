"""Mocked feasibility batch only; no remote sources contacted."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest


def module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "source_feasibility", "scripts/source_feasibility.py"
    )
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize(
    "mode", ["success", "redirect", "timeout", "rate", "server", "connect", "malformed"]
)
def test_budget_and_no_followups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    batch = module()
    monkeypatch.setattr(batch, "sleep", lambda _: None)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if mode == "connect":
            raise httpx.ConnectError("simulated", request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout("simulated", request=request)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.org/"})
        if mode == "rate":
            return httpx.Response(429, headers={"Retry-After": "60"})
        if mode == "server":
            return httpx.Response(503)
        if str(request.url) == batch.URLS[2]:
            return httpx.Response(
                200,
                text="broken"
                if mode == "malformed"
                else '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>not-retained</id>'
                "<published>2025-01-01T00:00:00Z</published></entry></feed>",
            )
        return httpx.Response(
            200, text="<html><p>Published is not necessarily an announcement date.</p></html>"
        )

    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False) as client:
        batch.collect(client, tmp_path, origin="simulated")
    assert calls == list(batch.URLS[:1] if mode == "connect" else batch.URLS)
    for f in tmp_path.glob("*.json"):
        assert json.loads(f.read_bytes())["origin"] == "simulated"


def test_only_metadata_summary_not_candidate_acquisition() -> None:
    batch = module()
    body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>secret-id</id><title>not-collected</title><published>2025-01-01</published></entry></feed>'
    result = batch.evidence(batch.URLS[2], body)
    assert result["entry_count"] == 1
    assert "secret-id" not in json.dumps(result) and "not-collected" not in json.dumps(result)
