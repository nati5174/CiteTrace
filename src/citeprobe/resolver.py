"""Bounded asynchronous lookups, retries, response provenance, and offline replay."""

import asyncio
import hashlib
import math
import os
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from citeprobe.lookup_inputs import fingerprint
from citeprobe.providers import Crossref, OpenAlex, Provider, response_evidence
from citeprobe.resolution_models import (
    Attempt,
    Candidate,
    LookupBundle,
    LookupResult,
    LookupTask,
    Outcome,
    ProviderName,
    RequestMetadata,
    ResolverConfig,
)


def retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, seconds) if math.isfinite(seconds) else None


class ProviderGate:
    """Serialize request starts and share Retry-After cooldown across workers."""

    def __init__(
        self,
        rps: float,
        concurrency: int,
        sleep: Callable[[float], Awaitable[None]],
        clock: Callable[[], float],
    ) -> None:
        self.interval = 1 / rps
        self.slots = asyncio.Semaphore(concurrency)
        self.lock = asyncio.Lock()
        self.next_start = 0.0
        self.sleep = sleep
        self.clock = clock
        self.blocked = False

    async def wait(self) -> bool:
        async with self.lock:
            while True:
                if self.blocked:
                    return False
                delay = self.next_start - self.clock()
                if delay <= 0:
                    break
                # Another in-flight response may extend cooldown during this await.
                await self.sleep(delay)
            self.next_start = self.clock() + self.interval
            return True

    def defer(self, delay: float) -> None:
        self.next_start = max(self.next_start, self.clock() + delay)


class Resolver:
    def __init__(
        self,
        config: ResolverConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        providers: Sequence[Provider] | None = None,
    ) -> None:
        self.config = config or ResolverConfig()
        self.transport = transport
        self.sleep, self.clock, self.now = sleep, clock, now
        self.providers = {p.name: p for p in (providers or (OpenAlex(), Crossref()))}
        # Credentials live only in memory and are never included in saved configuration.
        self.keys = {
            "openalex": os.environ.get("OPENALEX_API_KEY", ""),
            "crossref": os.environ.get("CROSSREF_API_KEY", ""),
        }
        self.contact = os.environ.get("CROSSREF_MAILTO", "")
        for value in (*self.keys.values(), self.contact):
            if not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Credential/contact environment variables must contain safe ASCII")

    def headers(self, provider: ProviderName) -> dict[str, str]:
        headers = {"User-Agent": "CiteProbe/0.1", "Accept": "application/json"}
        if self.keys[provider]:
            name = "Authorization" if provider == "openalex" else "crossref-api-key"
            headers[name] = "Bearer " + self.keys[provider]
        if provider == "crossref" and self.contact:
            headers["User-Agent"] += f" (mailto:{self.contact})"
        return headers

    async def resolve(
        self,
        tasks: Sequence[LookupTask],
        providers: Sequence[ProviderName],
        *,
        dataset_version: str,
        dataset_fingerprint: str,
        input_fingerprint: str,
    ) -> LookupBundle:
        names = tuple(dict.fromkeys(providers))
        if not names or any(name not in self.providers for name in names):
            raise ValueError("Select at least one supported provider")
        gates = {
            name: ProviderGate(
                getattr(self.config, f"{name}_rps"),
                self.config.provider_concurrency,
                self.sleep,
                self.clock,
            )
            for name in names
        }
        # A fixed worker pool bounds both active requests and queued coroutine tasks.
        jobs = [(task, name) for task in tasks for name in names]
        results: list[LookupResult | None] = [None] * len(jobs)
        job_iterator = iter(enumerate(jobs))
        limits = httpx.Limits(
            max_connections=self.config.concurrency,
            max_keepalive_connections=self.config.concurrency,
        )
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            limits=limits,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            async def worker() -> None:
                for index, (task, name) in job_iterator:
                    results[index] = await self._lookup(
                        client, task, self.providers[name], gates[name]
                    )

            await asyncio.gather(
                *(worker() for _ in range(min(len(jobs), self.config.concurrency)))
            )
        config_data = self.config.model_dump(mode="json")
        if any(result is None for result in results):
            raise RuntimeError("Resolver did not complete its lookup plan")
        return LookupBundle(
            dataset_version=dataset_version,
            dataset_fingerprint=dataset_fingerprint,
            input_fingerprint=input_fingerprint,
            config_fingerprint=fingerprint(
                {
                    "engine_version": "1",
                    "config": config_data,
                    "providers": names,
                    "selection": [(task.source_id, task.strategy) for task in tasks],
                }
            ),
            config=self.config,
            providers=names,
            selected_source_ids=tuple(task.source_id for task in tasks),
            generated_at=self.now(),
            results=tuple(result for result in results if result is not None),
        )

    async def _lookup(
        self, client: httpx.AsyncClient, task: LookupTask, provider: Provider, gate: ProviderGate
    ) -> LookupResult:
        request = provider.request(task.metadata, task.identifier)
        submitted = RequestMetadata(
            endpoint=request.endpoint,
            params=request.params,
            submitted_metadata=task.metadata if task.strategy == "metadata" else None,
            submitted_identifier=task.identifier,
        )
        lookup_id = fingerprint(
            {
                "engine_version": "1",
                "provider": provider.name,
                "source_kind": task.source_kind,
                "source_id": task.source_id,
                "strategy": task.strategy,
                "request": submitted.model_dump(),
            }
        )
        rng = random.Random(f"{self.config.jitter_seed}:{lookup_id}")
        started_at, started = self.now(), self.clock()
        attempts: list[Attempt] = []
        candidates: tuple[Candidate, ...] = ()
        warnings: tuple[str, ...] = ()
        outcome: Outcome = "UNKNOWN"
        secrets = tuple(filter(None, (*self.keys.values(), self.contact)))
        for number in range(self.config.max_attempts):
            retry = False
            response_status = None
            retry_after = None
            evidence = None
            response_hash = None
            diagnostic = None
            async with gate.slots:
                allowed = await gate.wait()
                attempt_at, tick = self.now(), self.clock()
                try:
                    if not allowed:
                        # A long provider cooldown prevents further requests in this run.
                        attempts.append(
                            Attempt(
                                started_at=attempt_at,
                                finished_at=self.now(),
                                latency_ms=0,
                                response_status=None,
                                outcome="RATE_LIMITED",
                                diagnostic="Provider cooldown exceeds configured retry wait",
                                request_sent=False,
                            )
                        )
                        outcome = "RATE_LIMITED"
                        break
                    outgoing = client.build_request(
                        "GET",
                        request.endpoint,
                        params=request.params,
                        headers=self.headers(provider.name),
                    )
                    # Reuse connections, but never allow provider cookies to become hidden hints.
                    outgoing.headers.pop("cookie", None)
                    response = await client.send(outgoing)
                    response_status = response.status_code
                    retry_after = response.headers.get("Retry-After")
                    response_hash = hashlib.sha256(response.content).hexdigest()
                    raw: Any = None
                    try:
                        raw = redact(response.json(), secrets)
                        evidence = response_evidence(raw, secrets)
                    except ValueError:
                        pass  # Non-JSON response retained as a hash, never arbitrary body text.
                    if response_status == 429:
                        outcome, retry = "RATE_LIMITED", True
                    elif response_status in (500, 502, 503, 504):
                        outcome, retry = "API_ERROR", True
                    elif not 200 <= response_status < 300:
                        outcome = "API_ERROR"
                    else:
                        try:
                            candidates, warnings = provider.parse(raw)
                            outcome = (
                                "FOUND"
                                if candidates
                                else ("API_ERROR" if warnings else "NOT_FOUND")
                            )
                        except (ValueError, TypeError):
                            outcome, diagnostic = "API_ERROR", "Malformed provider response"
                except httpx.TimeoutException:
                    outcome, retry, diagnostic = "TIMEOUT", True, "Request timed out"
                except httpx.TransportError:
                    outcome, retry, diagnostic = "API_ERROR", True, "Transport failure"
                delay = None
                if retry:
                    requested = retry_after_seconds(retry_after, self.now())
                    delay = max(
                        requested or 0,
                        min(
                            self.config.max_retry_wait,
                            self.config.backoff_seconds * 2**number * rng.uniform(0.5, 1.5),
                        ),
                    )
                    gate.defer(delay)
                    if delay > self.config.max_retry_wait:
                        gate.blocked = True
                attempts.append(
                    Attempt(
                        started_at=attempt_at,
                        finished_at=self.now(),
                        latency_ms=max(0, (self.clock() - tick) * 1000),
                        response_status=response_status,
                        outcome=outcome,
                        retry_after=redact(retry_after, secrets),
                        retry_delay_seconds=delay,
                        response=evidence,
                        response_body_sha256=response_hash,
                        diagnostic=diagnostic,
                    )
                )
            if not retry or number + 1 >= self.config.max_attempts:
                break
            if delay is not None and delay > self.config.max_retry_wait:
                break  # Never retry earlier than a provider's long Retry-After.
            # The shared gate applies the delay, including to other lookup workers.
        return LookupResult(
            lookup_id=lookup_id,
            source_id=task.source_id,
            source_kind=task.source_kind,
            original_citation_id=task.original_citation_id,
            provider=provider.name,
            strategy=task.strategy,
            request=submitted,
            outcome=outcome,
            candidates=candidates,
            parsing_warnings=warnings,
            started_at=started_at,
            finished_at=self.now(),
            latency_ms=max(0, (self.clock() - started) * 1000),
            retry_count=max(0, sum(attempt.request_sent for attempt in attempts) - 1),
            response_status=attempts[-1].response_status,
            attempts=tuple(attempts),
        )


def redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    return value


def replay(path: Path) -> LookupBundle:
    """Load recorded outcomes verbatim. No network, re-ranking, or new timestamps."""
    return LookupBundle.model_validate_json(path.read_text(encoding="utf-8"))


def save_results(bundle: LookupBundle, path: Path) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(bundle.model_dump_json(indent=2) + "\n")
