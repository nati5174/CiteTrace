"""Explicitly invoked, at most one no-retry HTTP request per provider. Never a benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import ssl
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import certifi
import httpx

from citeprobe.resolution_models import ProviderName, ResolverConfig
from citeprobe.resolver import Resolver


def environment_snapshot() -> dict[str, Any]:
    names = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "OPENALEX_API_KEY",
        "CROSSREF_API_KEY",
        "CROSSREF_MAILTO",
    )
    result: dict[str, Any] = {
        "environment_presence_only": {
            name: bool(os.environ.get(name) or os.environ.get(name.lower())) for name in names
        },
        "proxy_schemes_discovered": sorted(
            key for key in urllib.request.getproxies() if key != "no"
        ),
        "httpx_version": httpx.__version__,
        "openssl_version": ssl.OPENSSL_VERSION,
    }
    dns: dict[str, Any] = {}
    for host in ("api.openalex.org", "api.crossref.org"):
        try:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            dns[host] = {
                "resolved": True,
                "address_count": len({row[4][0] for row in addresses}),
                "families": sorted({row[0].name for row in addresses}),
            }
        except OSError as error:
            dns[host] = {
                "resolved": False,
                "exception_type": type(error).__name__,
                "errno": error.errno,
                "winerror": getattr(error, "winerror", None),
            }
    result["dns"] = dns
    result["tls_contexts"] = {}
    factories: tuple[tuple[str, Callable[[], ssl.SSLContext]], ...] = (
        ("system", ssl.create_default_context),
        ("httpx_certifi", lambda: ssl.create_default_context(cafile=certifi.where())),
    )
    for label, factory in factories:
        try:
            context = factory()
            result["tls_contexts"][label] = {
                "loaded": True,
                "hostname_check": context.check_hostname,
                "verify_required": context.verify_mode == ssl.CERT_REQUIRED,
                "store_counts": context.cert_store_stats(),
            }
        except (OSError, ssl.SSLError) as error:
            result["tls_contexts"][label] = {
                "loaded": False,
                "exception_type": type(error).__name__,
            }
    return result


def exception_details(error: BaseException) -> dict[str, Any]:
    """Inspect causes locally; never persist exception messages that might echo credentials."""
    nodes: list[dict[str, Any]] = []
    seen: set[int] = set()
    queue = [error]
    permission_denied = False
    certificate_failed = False
    while queue and len(nodes) < 16:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        text = str(current)  # Used for classification only, never printed or saved.
        permission_denied |= bool(re.search(r"\b10013\b", text)) or getattr(
            current, "errno", None
        ) in {1, 13}
        certificate_failed |= isinstance(current, ssl.SSLCertVerificationError)
        nodes.append(
            {
                "exception_type": type(current).__name__,
                "module": type(current).__module__,
                "errno": getattr(current, "errno", None),
                "winerror": getattr(current, "winerror", None),
            }
        )
        for child in (current.__cause__, current.__context__):
            if child is not None:
                queue.append(child)
        if isinstance(current, BaseExceptionGroup):
            queue.extend(current.exceptions)
    return {
        "exception_type": type(error).__name__,
        "causes": nodes,
        "socket_permission_denied_detected": permission_denied,
        "certificate_verification_failure_detected": certificate_failed,
    }


async def diagnose() -> dict[str, Any]:
    result: dict[str, Any] = {
        "purpose": "Milestone 1 connectivity diagnostic, not a paper retrieval pilot",
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": environment_snapshot(),
        "retry_count": 0,
        "redirects_followed": False,
        "trust_env": False,
        "maximum_http_requests": 2,
        "requests": [],
    }
    engine = Resolver(ResolverConfig(max_attempts=1))
    requests: tuple[tuple[ProviderName, str, dict[str, str]], ...] = (
        (
            "openalex",
            "https://api.openalex.org/works",
            {"search": "Attention Is All You Need", "per_page": "1", "select": "id,title,doi"},
        ),
        (
            "crossref",
            "https://api.crossref.org/works",
            {
                "query.bibliographic": "Attention Is All You Need",
                "rows": "1",
                "select": "DOI,title",
            },
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(10, connect=8),
    ) as client:
        for provider, endpoint, params in requests:
            headers = engine.headers(provider)
            headers["User-Agent"] += (
                " (Milestone-1 connectivity diagnostic; one request; no retries)"
            )
            record: dict[str, Any] = {
                "provider": provider,
                "endpoint": endpoint,
                "parameter_names": sorted(params),
                "maximum_records_requested": 1,
                "credential_configured": bool(engine.keys[provider]),
                "http_status": None,
                "exception_type": None,
                "request_attempts": 1,
            }
            start = time.perf_counter()
            try:
                async with client.stream(
                    "GET", endpoint, params=params, headers=headers
                ) as response:
                    record["http_status"] = response.status_code
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received >= 65536:
                            break
                    record["bytes_read"] = received
                    record["response_body_not_persisted"] = True
            except httpx.HTTPError as error:
                record.update(exception_details(error))
            finally:
                record["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
            result["requests"].append(record)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-live",
        action="store_true",
        required=True,
        help="Explicitly authorize one HTTP request per provider",
    )
    args = parser.parse_args()
    # Reserve output before any requests so accidental reruns cannot consume a second budget.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        result = asyncio.run(diagnose())
        serialized = json.dumps(result, indent=2) + "\n"
        stream.write(serialized)
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
