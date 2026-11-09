"""Only mocked requests; no verification observations are generated here."""

import importlib.util
from pathlib import Path
from typing import Any

import httpx
import pytest


def batch_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "identity_verification", Path("scripts/identity_verification.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["success", "redirect", "rate_limit", "malformed", "timeout"])
def test_six_requests_no_retries_or_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    module = batch_module()
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("simulated", request=request)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.org/not-authorized"})
        if mode == "rate_limit":
            return httpx.Response(429, headers={"Retry-After": "60"})
        if mode == "malformed":
            return httpx.Response(200, text="not JSON")
        if request.url.host == "arxiv.org":
            return httpx.Response(200, text='<meta name="citation_title" content="Fixture">')
        return httpx.Response(200, json={"message": {"DOI": "fixture"}})

    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False) as client:
        module.collect(client, tmp_path)
    assert len(calls) == 6
    assert calls[0].url == "https://arxiv.org/abs/1706.03762"
    assert all(request.url.host == "api.crossref.org" for request in calls[1:])
    assert len(list(tmp_path.glob("*.json"))) == 6


def test_projection_keeps_relations_and_omits_author_contact() -> None:
    module = batch_module()
    result = module.evidence(
        "crossref",
        b'{"message":{"relation":{"is-version-of":[{"id":"1706.03762"}]},'
        b'"author":[{"given":"A","family":"B","email":"private@example.org"}]}}',
    )
    assert result["relation"]["is-version-of"][0]["id"] == "1706.03762"
    assert result["author"] == [{"given": "A", "family": "B"}]
