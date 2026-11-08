"""Audit diagnostic tests are mocked; they must never consume the live request budget."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts import connectivity_diagnostic


def test_exception_details_are_sanitized() -> None:
    private = "never-persist-this-private-value"
    denied = PermissionError(13, private)
    wrapped = httpx.ConnectError(private)
    wrapped.__cause__ = denied
    details = connectivity_diagnostic.exception_details(wrapped)
    assert details["socket_permission_denied_detected"]
    assert private not in json.dumps(details)
    assert details["causes"][-1]["errno"] == 13


def test_diagnostic_makes_only_one_attempt_each_and_never_logs_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", "private-openalex-token")
    monkeypatch.setenv("CROSSREF_API_KEY", "private-crossref-token")
    monkeypatch.setenv("CROSSREF_MAILTO", "private-contact@example.org")
    monkeypatch.setattr(
        connectivity_diagnostic, "environment_snapshot", lambda: {"origin": "simulated"}
    )
    seen: list[str] = []
    original = httpx.AsyncClient
    original_transport = httpx.AsyncHTTPTransport

    def diagnostic_transport(*args: Any, **kwargs: Any) -> httpx.AsyncHTTPTransport:
        assert kwargs["retries"] == 0 and kwargs["trust_env"] is False
        return original_transport(*args, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        seen.append(host)
        assert "Milestone-1" in request.headers["User-Agent"]
        assert request.url.params.get("per_page", request.url.params.get("rows")) == "1"
        if host == "api.openalex.org":
            raise httpx.ConnectError("private-openalex-token", request=request)
        return httpx.Response(403, text="private-crossref-token private-contact@example.org")

    def mock_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", diagnostic_transport)
    result = asyncio.run(connectivity_diagnostic.diagnose())
    assert seen == ["api.openalex.org", "api.crossref.org"]
    assert result["requests"][0]["exception_type"] == "ConnectError"
    assert result["requests"][1]["http_status"] == 403
    assert result["retry_count"] == 0
    serialized = json.dumps(result)
    assert "private-openalex-token" not in serialized
    assert "private-crossref-token" not in serialized
    assert "private-contact@example.org" not in serialized


def test_existing_diagnostic_output_prevents_accidental_live_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "existing.json"
    output.write_text("existing result")
    monkeypatch.setattr(
        sys, "argv", ["connectivity_diagnostic.py", "--allow-live", "--output", str(output)]
    )

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Existing output must be rejected before creating a client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    with pytest.raises(FileExistsError):
        connectivity_diagnostic.main()
    assert output.read_text() == "existing result"
