"""Resolution contracts verified against mocked HTTP, never live services."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from citeprobe.cli import main
from citeprobe.dataset import load_dataset
from citeprobe.lookup_inputs import canonical_tasks, mutation_tasks
from citeprobe.models import Dataset, MutationBatch
from citeprobe.mutations import generate_mutations
from citeprobe.providers import Crossref, OpenAlex, bibliographic_text
from citeprobe.resolution_models import LookupBundle, LookupTask, ProviderName, ResolverConfig
from citeprobe.resolver import ProviderGate, Resolver, replay, retry_after_seconds, save_results

PILOT = Path(__file__).resolve().parents[1] / "data" / "pilot_dataset.json"


class FakeTime:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.delays: list[float] = []

    def clock(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.elapsed)

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.elapsed += delay


def execute(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    provider: ProviderName = "openalex",
    config: ResolverConfig | None = None,
    tasks: tuple[LookupTask, ...] | None = None,
    timer: FakeTime | None = None,
) -> LookupBundle:
    timer = timer or FakeTime()
    engine = Resolver(
        config or ResolverConfig(backoff_seconds=0),
        transport=httpx.MockTransport(handler),
        sleep=timer.sleep,
        clock=timer.clock,
        now=timer.now,
    )
    return asyncio.run(
        engine.resolve(
            tasks if tasks is not None else canonical_tasks(load_dataset(PILOT))[:1],
            [provider],
            dataset_version="pilot-1",
            dataset_fingerprint="dataset",
            input_fingerprint="input",
        )
    )


def envelope(provider: ProviderName, records: list[Any]) -> dict[str, Any]:
    if provider == "openalex":
        return {"results": records}
    return {"status": "ok", "message": {"items": records}}


def candidate(provider: ProviderName) -> dict[str, Any]:
    if provider == "openalex":
        return {
            "id": "https://openalex.org/W123",
            "title": "Retrieved title",
            "publication_year": 2017,
            "doi": "https://doi.org/10.1234/test",
            "authorships": [{"author": {"display_name": "Test Author"}}],
            "relevance_score": 42.5,
            "locations": [{"landing_page_url": "https://arxiv.org/abs/1706.03762"}],
        }
    return {
        "DOI": "10.1234/test",
        "title": ["Retrieved title"],
        "author": [{"given": "Test", "family": "Author"}],
        "published": {"date-parts": [[2017, 6]]},
        "score": 42.5,
        "link": [{"URL": "https://arxiv.org/pdf/1706.03762"}],
    }


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_provider_success(provider: ProviderName) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=envelope(provider, [candidate(provider)]))

    result = execute(handler, provider=provider).results[0]
    assert result.outcome == "FOUND"
    found = result.candidates[0]
    assert found.title == "Retrieved title"
    assert found.authors == ("Test Author",)
    assert found.year == 2017
    assert found.doi == "10.1234/test"
    assert found.arxiv_id == "1706.03762"
    assert found.provider_rank == 1
    assert 42.5 in found.ranking.values()
    assert dict(seen[0].url.params) == result.request.params
    assert result.request.endpoint == str(seen[0].url).split("?")[0]
    assert result.retry_count == 0
    assert result.attempts[0].response is not None


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_empty(provider: ProviderName) -> None:
    result = execute(
        lambda r: httpx.Response(200, json=envelope(provider, [])), provider=provider
    ).results[0]
    assert result.outcome == "NOT_FOUND"
    assert not result.candidates


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
@pytest.mark.parametrize("body", [None, [], {}, {"results": None}, {"message": {"items": []}}])
def test_malformed_envelope(provider: ProviderName, body: Any) -> None:
    result = execute(lambda r: httpx.Response(200, json=body), provider=provider).results[0]
    assert result.outcome == "API_ERROR"
    assert len(result.attempts) == 1


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_partial_candidates_keep_original_ranks(provider: ProviderName) -> None:
    records = [None, candidate(provider), {"title": 42}, candidate(provider), candidate(provider)]
    result = execute(
        lambda r: httpx.Response(200, json=envelope(provider, records)), provider=provider
    ).results[0]
    assert result.outcome == "FOUND"
    assert [c.provider_rank for c in result.candidates] == [2, 4, 5]
    assert len(result.parsing_warnings) == 2


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_all_candidates_malformed(provider: ProviderName) -> None:
    result = execute(
        lambda r: httpx.Response(200, json=envelope(provider, [None, {}])), provider=provider
    ).results[0]
    assert result.outcome == "API_ERROR"
    assert len(result.parsing_warnings) == 2


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_missing_optional_fields_and_limit(provider: ProviderName) -> None:
    record = {"id": "W1"} if provider == "openalex" else {"DOI": "10.1234/test"}
    result = execute(
        lambda r: httpx.Response(200, json=envelope(provider, [record] * 8)), provider=provider
    ).results[0]
    assert len(result.candidates) == 5
    assert result.candidates[0].title is None
    assert result.candidates[0].year is None


def test_invalid_json() -> None:
    result = execute(lambda r: httpx.Response(200, text="not JSON")).results[0]
    assert result.outcome == "API_ERROR"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 501])
def test_permanent_errors_not_retried(status: int) -> None:
    result = execute(lambda r: httpx.Response(status)).results[0]
    assert result.outcome == "API_ERROR"
    assert result.response_status == status
    assert result.retry_count == 0


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retry_success(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status) if calls < 3 else httpx.Response(200, json={"results": []})

    timer = FakeTime()
    result = execute(handler, config=ResolverConfig(backoff_seconds=2), timer=timer).results[0]
    assert result.outcome == "NOT_FOUND"
    assert result.retry_count == 2
    assert len(result.attempts) == 3
    assert result.attempts[0].response_status == status
    assert 1 <= (result.attempts[0].retry_delay_seconds or 0) <= 3
    assert 2 <= (result.attempts[1].retry_delay_seconds or 0) <= 6
    assert timer.elapsed >= sum(timer.delays)


@pytest.mark.parametrize(
    ("exception", "outcome"),
    [
        (httpx.ReadTimeout, "TIMEOUT"),
        (httpx.ConnectTimeout, "TIMEOUT"),
        (httpx.ConnectError, "API_ERROR"),
        (httpx.RemoteProtocolError, "API_ERROR"),
    ],
)
def test_transport_retry_exhaustion(exception: type[httpx.TransportError], outcome: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception("sensitive exception text", request=request)

    bundle = execute(handler)
    result = bundle.results[0]
    assert result.outcome == outcome
    assert result.retry_count == 2
    assert result.response_status is None
    assert "sensitive exception text" not in bundle.model_dump_json()


@pytest.mark.parametrize(("status", "outcome"), [(429, "RATE_LIMITED"), (503, "API_ERROR")])
def test_http_retry_exhaustion(status: int, outcome: str) -> None:
    result = execute(lambda r: httpx.Response(status)).results[0]
    assert result.outcome == outcome
    assert result.retry_count == 2


@pytest.mark.parametrize("header", ["7", "Thu, 01 Jan 2026 00:00:07 GMT"])
def test_retry_after(header: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return (
            httpx.Response(429, headers={"Retry-After": header})
            if calls == 1
            else httpx.Response(200, json={"results": []})
        )

    timer = FakeTime()
    result = execute(handler, timer=timer).results[0]
    assert result.outcome == "NOT_FOUND"
    assert timer.elapsed >= 7
    assert result.attempts[0].retry_delay_seconds == 7


def test_long_retry_after_stops_entire_provider() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "3600"})

    timer = FakeTime()
    bundle = execute(handler, timer=timer, tasks=canonical_tasks(load_dataset(PILOT)))
    assert calls == 1
    assert timer.elapsed == 0
    assert all(r.outcome == "RATE_LIMITED" for r in bundle.results)


@pytest.mark.parametrize("value", ["garbage", "NaN", "inf", None])
def test_invalid_retry_after(value: str | None) -> None:
    assert retry_after_seconds(value, datetime.now(UTC)) is None


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_mutations_never_leak_identifiers_or_original_values(provider: ProviderName) -> None:
    dataset = load_dataset(PILOT)
    batch = generate_mutations(dataset, seed=42)
    tasks = mutation_tasks(dataset, batch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(provider, []))

    bundle = execute(handler, provider=provider, tasks=tasks)
    assert len(requests) == 25
    for request, task, result, mutation in zip(
        requests, tasks, bundle.results, batch.mutations, strict=True
    ):
        text = str(request.url) + request.content.decode() + str(request.headers)
        assert mutation.citation.arxiv_id is not None
        assert mutation.citation.arxiv_id not in text
        assert mutation.original_citation_id not in text
        assert mutation.mutation_id not in text
        query = request.url.params.get("search") or request.url.params["query.bibliographic"]
        assert query == bibliographic_text(task.metadata)
        assert task.metadata.title == mutation.citation.title
        assert task.metadata.authors == mutation.citation.authors
        assert task.metadata.year == mutation.citation.year
        assert result.source_id == mutation.mutation_id
        assert result.original_citation_id == mutation.original_citation_id
        assert result.request.submitted_identifier is None


def test_task_boundary_rejects_identifier_hints() -> None:
    task = canonical_tasks(load_dataset(PILOT))[0].model_dump()
    task.update(source_kind="mutation", identifier="10.1234/leak", strategy="identifier")
    with pytest.raises(ValidationError):
        LookupTask.model_validate(task)
    task.update(source_kind="canonical", strategy="metadata")
    with pytest.raises(ValidationError):
        LookupTask.model_validate(task)


def test_canonical_default_and_explicit_identifiers() -> None:
    dataset = load_dataset(PILOT)
    default = canonical_tasks(dataset)[0]
    assert default.identifier is None
    explicit = canonical_tasks(dataset, "identifier")[0]
    assert explicit.identifier == "arXiv:1706.03762"
    assert (
        OpenAlex().request(explicit.metadata, explicit.identifier).params["search"]
        == explicit.identifier
    )
    request = OpenAlex().request(default.metadata, "10.1234/test")
    assert request.params["filter"] == "doi:https://doi.org/10.1234/test"
    assert (
        Crossref().request(default.metadata, "10.1234/test").params["query.bibliographic"]
        == "10.1234/test"
    )


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_credentials_and_private_fields_not_persisted(
    provider: ProviderName,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-openalex")
    monkeypatch.setenv("CROSSREF_API_KEY", "secret-crossref")
    monkeypatch.setenv("CROSSREF_MAILTO", "private@example.org")

    def handler(request: httpx.Request) -> httpx.Response:
        key = "Authorization" if provider == "openalex" else "crossref-api-key"
        assert request.headers[key] == f"Bearer secret-{provider}"
        record = candidate(provider)
        record["abstract"] = "private@example.org"
        record["email"] = "private@example.org"
        record["title"] = (
            "secret-openalex secret-crossref"
            if provider == "openalex"
            else ["secret-openalex secret-crossref"]
        )
        return httpx.Response(200, json=envelope(provider, [record]))

    saved = execute(handler, provider=provider).model_dump_json()
    assert "secret-openalex" not in saved
    assert "secret-crossref" not in saved
    assert "private@example.org" not in saved
    assert "abstract" not in saved


def test_replay_and_stable_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    first = execute(handler)
    timer = FakeTime()
    timer.elapsed = 100
    second = execute(handler, timer=timer)
    assert first.results[0].lookup_id == second.results[0].lookup_id
    assert first.generated_at != second.generated_at
    output = tmp_path / "results.json"
    save_results(first, output)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Replay must never construct a client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    assert replay(output) == first
    assert main(["replay", str(output), "--output", str(tmp_path / "replayed.json")]) == 0
    assert replay(tmp_path / "replayed.json") == first
    with pytest.raises(FileExistsError):
        save_results(first, output)


def test_mutation_input_validation() -> None:
    dataset = load_dataset(PILOT)
    batch = generate_mutations(dataset)
    data = batch.model_dump(mode="json")
    data["dataset_version"] = "wrong"
    with pytest.raises(ValueError, match="version"):
        mutation_tasks(dataset, MutationBatch.model_validate(data))
    for field, value in (("original_citation_id", "unknown"), ("mutated_fields", ["year"])):
        data = batch.model_dump(mode="json")
        data["mutations"][0][field] = value
        with pytest.raises(ValueError):
            mutation_tasks(dataset, MutationBatch.model_validate(data))
    data = batch.model_dump(mode="json")
    data["mutations"].append(data["mutations"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        mutation_tasks(dataset, MutationBatch.model_validate(data))
    source = dataset.model_dump(mode="json")
    source["citations"][0]["provenance"].update(verification_status="pending", verified_at=None)
    pending = Dataset.model_validate(source)
    assert len(canonical_tasks(pending)) == 4
    with pytest.raises(ValueError, match="pending"):
        mutation_tasks(pending, batch)


def test_cli_mocked_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.AsyncClient
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        name: ProviderName = "openalex" if request.url.host == "api.openalex.org" else "crossref"
        return httpx.Response(200, json=envelope(name, [candidate(name)]))

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    config = tmp_path / "config.json"
    config.write_text(ResolverConfig(openalex_rps=100, crossref_rps=100).model_dump_json())
    before = PILOT.read_bytes()
    output = tmp_path / "canonical.json"
    assert (
        main(
            [
                "resolve",
                str(PILOT),
                "--limit",
                "1",
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert len(replay(output).results) == 2
    mutations = tmp_path / "mutations.json"
    mutations.write_text(generate_mutations(load_dataset(PILOT)).model_dump_json())
    mutated_output = tmp_path / "mutated.json"
    assert (
        main(
            [
                "resolve-mutations",
                str(mutations),
                "--dataset",
                str(PILOT),
                "--limit",
                "2",
                "--config",
                str(config),
                "--output",
                str(mutated_output),
            ]
        )
        == 0
    )
    assert len(replay(mutated_output).results) == 4
    count = len(seen)
    assert main(["resolve", str(PILOT), "--output", str(PILOT)]) == 1
    assert main(["resolve", str(PILOT), "--output", str(output)]) == 1
    assert len(seen) == count
    assert PILOT.read_bytes() == before


def test_config_invalid() -> None:
    for field, value in (
        ("concurrency", 0),
        ("timeout_seconds", 0),
        ("max_attempts", 0),
        ("crossref_rps", 0),
        ("openalex_rps", float("inf")),
        ("max_retry_wait", 100),
        ("api_key", "secret"),
    ):
        with pytest.raises(ValidationError):
            ResolverConfig.model_validate({field: value})


def test_bounded_concurrency_and_order() -> None:
    active = 0
    peak = 0
    provider_active: dict[str, int] = {}
    provider_peak: dict[str, int] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        host = request.url.host or ""
        active += 1
        peak = max(peak, active)
        provider_active[host] = provider_active.get(host, 0) + 1
        provider_peak[host] = max(provider_peak.get(host, 0), provider_active[host])
        await asyncio.sleep(0.02)
        active -= 1
        provider_active[host] -= 1
        name: ProviderName = "openalex" if host == "api.openalex.org" else "crossref"
        return httpx.Response(200, json=envelope(name, []))

    tasks = canonical_tasks(load_dataset(PILOT))
    engine = Resolver(
        ResolverConfig(concurrency=3, provider_concurrency=1, openalex_rps=100, crossref_rps=100),
        transport=httpx.MockTransport(handler),
    )
    bundle = asyncio.run(
        engine.resolve(
            tasks,
            ["openalex", "crossref"],
            dataset_version="test",
            dataset_fingerprint="d",
            input_fingerprint="i",
        )
    )
    assert peak <= 3
    assert all(value == 1 for value in provider_peak.values())
    assert [(r.source_id, r.provider) for r in bundle.results] == [
        (task.source_id, name) for task in tasks for name in ("openalex", "crossref")
    ]


def test_provider_specific_pacing() -> None:
    timer = FakeTime()
    calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(timer.clock())
        return httpx.Response(200, json={"results": []})

    execute(
        handler,
        timer=timer,
        config=ResolverConfig(openalex_rps=2),
        tasks=canonical_tasks(load_dataset(PILOT)),
    )
    assert all(b - a >= 0.5 for a, b in zip(calls, calls[1:], strict=False))


def test_cooldown_extended_during_pacing_wait() -> None:
    timer = FakeTime()
    sleeps = 0

    async def sleep(delay: float) -> None:
        nonlocal sleeps
        sleeps += 1
        await timer.sleep(delay)
        if sleeps == 1:
            gate.defer(7)

    gate = ProviderGate(1, 2, sleep, timer.clock)

    async def run() -> None:
        assert await gate.wait()
        assert await gate.wait()

    asyncio.run(run())
    assert timer.elapsed == 8


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_mutated_doi_is_never_submitted(provider: ProviderName) -> None:
    data = load_dataset(PILOT).model_dump(mode="json")
    data["citations"][0]["doi"] = "10.1234/canonical-secret"
    dataset = Dataset.model_validate(data)
    batch = generate_mutations(dataset)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "canonical-secret" not in str(request.url)
        return httpx.Response(200, json=envelope(provider, []))

    result = execute(handler, provider=provider, tasks=mutation_tasks(dataset, batch)).results[0]
    assert result.request.submitted_identifier is None


@pytest.mark.parametrize("name", ["openalex", "crossref"])
def test_response_evidence_supports_reparsing(name: ProviderName) -> None:
    provider = OpenAlex() if name == "openalex" else Crossref()
    bundle = execute(
        lambda r: httpx.Response(200, json=envelope(name, [candidate(name)])),
        provider=name,
    )
    result = bundle.results[0]
    parsed, warnings = provider.parse(result.attempts[0].response)
    assert parsed == result.candidates
    assert not warnings


def test_no_local_reranking() -> None:
    first, second = candidate("crossref"), candidate("crossref")
    first.update(DOI="10.1234/first", score=1)
    second.update(DOI="10.1234/second", score=999)
    result = execute(
        lambda r: httpx.Response(200, json=envelope("crossref", [first, second])),
        provider="crossref",
    ).results[0]
    assert [c.provider_record_id for c in result.candidates] == ["10.1234/first", "10.1234/second"]


def test_canonical_identifier_trace_is_exact() -> None:
    tasks = canonical_tasks(load_dataset(PILOT), "identifier")[:1]
    result = execute(lambda r: httpx.Response(200, json={"results": []}), tasks=tasks).results[0]
    assert result.request.submitted_metadata is None
    assert result.request.submitted_identifier == "arXiv:1706.03762"


def test_client_reused_and_timeout_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        assert kwargs["timeout"].read == 12
        assert kwargs["limits"].max_connections == 2
        instance = original(*args, **kwargs)
        clients.append(instance)
        return instance

    monkeypatch.setattr(httpx, "AsyncClient", client)
    execute(
        lambda r: httpx.Response(200, json={"results": []}),
        config=ResolverConfig(timeout_seconds=12, concurrency=2),
        tasks=canonical_tasks(load_dataset(PILOT)),
    )
    assert len(clients) == 1
    assert clients[0].is_closed


def test_mutation_identifier_mismatch() -> None:
    dataset = load_dataset(PILOT)
    batch = generate_mutations(dataset).model_dump(mode="json")
    batch["mutations"][0]["citation"]["arxiv_id"] = "1706.12345"
    with pytest.raises(ValueError, match="identifiers"):
        mutation_tasks(dataset, MutationBatch.model_validate(batch))


def test_output_alias_rejected_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(PILOT.read_bytes())
    alias = tmp_path / "alias.json"
    alias.hardlink_to(source)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Output checks must precede networking")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    assert main(["resolve", str(source), "--output", str(alias)]) == 1
    assert source.read_bytes() == PILOT.read_bytes()


def test_replay_rejects_unknown_schema(tmp_path: Path) -> None:
    bundle = execute(lambda r: httpx.Response(200, json={"results": []})).model_dump(mode="json")
    bundle["schema_version"] = "99"
    path = tmp_path / "unsupported.json"
    path.write_text(json.dumps(bundle))
    assert main(["replay", str(path)]) == 1


def test_provider_cookies_never_become_hidden_hints() -> None:
    tasks = canonical_tasks(load_dataset(PILOT))[:2]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "cookie" not in request.headers
        return httpx.Response(
            200, json={"results": []}, headers={"Set-Cookie": "hint=canonical-id; Path=/"}
        )

    execute(handler, tasks=tasks)


def test_authentication_does_not_affect_lookup_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    first = execute(handler)
    monkeypatch.setenv("OPENALEX_API_KEY", "another-secret")
    second = execute(handler)
    assert first.results[0].lookup_id == second.results[0].lookup_id
    assert first.config_fingerprint == second.config_fingerprint


def test_invalid_credential_does_not_echo_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", "sensitive\nvalue")
    with pytest.raises(ValueError, match="safe ASCII") as error:
        Resolver()
    assert "sensitive" not in str(error.value)
