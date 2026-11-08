"""Synthetic fixtures only: identifiers and verification events are not empirical claims."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from citeprobe.lookup_inputs import canonical_tasks, fingerprint
from citeprobe.models import Dataset
from citeprobe.resolution_models import LookupBundle, LookupTask, ProviderName, ResolverConfig
from citeprobe.resolver import Resolver


def synthetic_dataset(count: int = 6) -> Dataset:
    return Dataset.model_validate(
        {
            "dataset_version": "synthetic-test-only-1",
            "citations": [
                {
                    "citation_id": f"fixture-{i}",
                    "title": f"Synthetic paper number {i}",
                    "authors": [{"given": "Test", "family": "Author"}],
                    "year": 2020,
                    "doi": f"10.1234/fixture-{i}",
                    "provenance": {
                        "source_url": "https://example.org/test-fixtures",
                        "record_identifier": f"fixture-{i}",
                        "verification_status": "verified",
                        "verified_at": "2020-01-01T00:00:00Z",
                    },
                }
                for i in range(count)
            ],
        }
    )


def work(
    doi: str | None = None, *, identifier: str = "W123", arxiv: str | None = None
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": f"https://openalex.org/{identifier}",
        "title": "Synthetic response title",
        "doi": doi,
        "publication_year": 2020,
        "relevance_score": 1.25,
    }
    if arxiv:
        record["locations"] = [{"landing_page_url": "https://arxiv.org/abs/" + arxiv}]
    return record


def lookup_bundle(
    dataset: Dataset,
    responses: list[Any],
    *,
    tasks: tuple[LookupTask, ...] | None = None,
    provider: ProviderName = "openalex",
    input_hash: str | None = None,
) -> LookupBundle:
    elapsed = 0.0
    iterator = iter(responses)

    async def sleep(delay: float) -> None:
        nonlocal elapsed
        elapsed += delay

    def handler(request: httpx.Request) -> httpx.Response:
        payload = next(iterator)
        if isinstance(payload, httpx.Response):
            return payload
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(200, json=payload)

    dataset_hash = fingerprint(dataset.model_dump(mode="json"))
    resolver = Resolver(
        ResolverConfig(max_attempts=1),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        clock=lambda: elapsed,
        now=lambda: datetime(2020, 1, 1, tzinfo=UTC) + timedelta(seconds=elapsed),
    )
    return asyncio.run(
        resolver.resolve(
            canonical_tasks(dataset)[: len(responses)] if tasks is None else tasks,
            [provider],
            dataset_version=dataset.dataset_version,
            dataset_fingerprint=dataset_hash,
            input_fingerprint=input_hash or dataset_hash,
        )
    )
