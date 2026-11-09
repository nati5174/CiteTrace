"""Offline-validated API-key continuation; live use requires separate authorization."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from citeprobe.benchmark_remaining import prepare as original_prepare
from citeprobe.benchmark_smoke import ANCHOR, DATASET_HASH, LIMIT, Capture, digest, verify
from citeprobe.dataset import load_dataset
from citeprobe.evidence_io import json_bytes
from citeprobe.lookup_inputs import canonical_tasks, fingerprint
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.resolution_models import ResolverConfig
from citeprobe.resolver import Resolver, save_results

PRIOR_ANCHOR = "56427baa74dd454399db9d4b6644d40a62746330e7c56868d1879a6fe92adc35"
PROVIDERS = (OpenAlex(), Crossref())


STOP_ANCHOR = "c4c1e49cc7f50d2ffd402efec3d4e5e605f5eafb4b04611c4fa76458b90ea3c3"
PROPOSAL_HASH = "6bf69c52cad7ffbe2c860043081ec06fe611f4b89e8cb9161583d7ba76c055fe"


def prepare(snapshot: Path, prior: Path, stopped: Path) -> dict[str, Any]:
    original = original_prepare(snapshot, prior)
    if digest((stopped / "integrity.json").read_bytes()) != STOP_ANCHOR:
        raise ValueError("Stopped attempt anchor mismatch")
    from citeprobe.benchmark_remaining import verify_output

    verify_output(stopped)
    receipt = json.loads((stopped / "receipt.json").read_bytes())
    record = json.loads((stopped / "paper-01/attempt-001/record.json").read_bytes())
    if (
        receipt["requests"] != 1
        or record["status"] != 429
        or not record["complete"]
        or record["url"] != original["requests"][0]["url"]
    ):
        raise ValueError("Stopped evidence does not authorize this proposed inventory")
    proposal_path = stopped.parent / "a-benchmark-continuation-plan-001/key-option-proposal.json"
    content = proposal_path.read_bytes()
    if digest(content) != PROPOSAL_HASH:
        raise ValueError("Key-option proposal hash mismatch")
    proposal = json.loads(content)
    for row, old in zip(proposal["requests"], original["requests"], strict=True):
        if {k: row[k] for k in old} != old:
            raise ValueError("Proposal changed original inventory")
    return {
        "schema_version": "1.0",
        "dataset_sha256": DATASET_HASH,
        "frozen_anchor": ANCHOR,
        "prior_anchor": PRIOR_ANCHOR,
        "stopped_anchor": STOP_ANCHOR,
        "proposal_sha256": PROPOSAL_HASH,
        "maximum_requests": 14,
        "retries": 0,
        "redirects": False,
        "pagination": False,
        "capture_limit": LIMIT,
        "openalex_access": "api_key_query_parameter",
        "crossref_access": "anonymous",
        "selection_rule": (
            "successful explicit reattempt replaces failed logical lookup; "
            "retain failure separately"
        ),
        "requests": proposal["requests"],
    }


class QueryKeyTransport(httpx.AsyncBaseTransport):
    """Add the key only after Capture validates and records the key-free request."""

    def __init__(self, inner: httpx.AsyncBaseTransport, key: str) -> None:
        self.inner = inner
        self.key = key

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            request.url = request.url.copy_merge_params({"api_key": self.key})
        elif request.url.host != "api.crossref.org":
            raise ValueError("Unexpected host")
        response = await self.inner.handle_async_request(request)
        for name in tuple(response.headers):
            if self.key in response.headers[name]:
                response.headers[name] = "[REDACTED]"
        return response


class QueryKeyResolver(Resolver):
    def headers(self, provider: Any) -> dict[str, str]:
        # Resolver's legacy Bearer credential is deliberately not sent.
        return {"User-Agent": "CiteProbe/0.1", "Accept": "application/json"}


async def run(
    snapshot: Path,
    prior: Path,
    plan: dict[str, Any],
    output: Path,
    stopped: Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    if plan != prepare(snapshot, prior, stopped):
        raise ValueError("Plan differs from frozen source inventory")
    key = os.environ.get("OPENALEX_API_KEY", "")
    if (
        len(key) < 16
        or not key.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in key)
        or os.environ.get("CROSSREF_API_KEY")
        or os.environ.get("CROSSREF_MAILTO")
    ):
        raise ValueError("Valid OpenAlex key required; Crossref credentials/contact must be absent")
    if any(key in str(row["url"]) for row in plan["requests"]):
        raise ValueError("Credential overlaps a planned URL")
    output.mkdir(exist_ok=False)
    (output / "plan.json").write_bytes(json_bytes(plan))
    dataset = load_dataset(snapshot / "dataset.json")
    tasks = canonical_tasks(dataset)[1:]
    inner = transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    count = 0
    stop: str | None = None
    try:
        for index, task in enumerate(tasks):
            task = task.model_copy(
                update={
                    "metadata": task.metadata.model_copy(update={"volume": None, "issue": None})
                }
            )
            pair = output / f"paper-{index + 1:02d}"
            pair.mkdir()
            rows = plan["requests"][2 * index : 2 * index + 2]
            capture = Capture(QueryKeyTransport(inner, key), pair, [row["url"] for row in rows])
            try:
                for provider in PROVIDERS:
                    if count >= 14:
                        raise ValueError("Request budget exhausted")
                    resolver = QueryKeyResolver(
                        ResolverConfig(max_attempts=1, concurrency=1, timeout_seconds=30),
                        transport=capture,
                    )
                    bundle = await resolver.resolve(
                        [task],
                        [provider.name],
                        dataset_version=dataset.dataset_version,
                        dataset_fingerprint=fingerprint(dataset.model_dump(mode="json")),
                        input_fingerprint=fingerprint(dataset.model_dump(mode="json")),
                    )
                    save_results(bundle, pair / (provider.name + "-lookups.json"))
                    result = bundle.results[0]
                    folder = pair / f"attempt-{capture.count:03d}"
                    record = json.loads((folder / "record.json").read_bytes())
                    if (
                        digest((folder / "body.bin").read_bytes()) != record["sha256"]
                        or capture.failed
                        or result.outcome not in {"FOUND", "NOT_FOUND"}
                        or result.parsing_warnings
                    ):
                        stop = "Provider error, incomplete capture, parsing or integrity failure"
                        break
                    raw = (folder / "body.bin").read_bytes()
                    response = httpx.Response(
                        record["status"], headers=record["headers"], content=raw
                    )
                    if digest(response.content) != result.attempts[
                        0
                    ].response_body_sha256 or provider.parse(response.json()) != (
                        result.candidates,
                        result.parsing_warnings,
                    ):
                        raise ValueError("Raw response replay failed before next request")
                    # Consecutive requests to either provider are separated by >= 1 second.
                    await asyncio.sleep(1)
            finally:
                count += capture.count
                (pair / "receipt.json").write_bytes(json_bytes({"requests": capture.count}))
                files = {
                    p.relative_to(pair).as_posix(): digest(p.read_bytes())
                    for p in pair.rglob("*")
                    if p.is_file()
                }
                (pair / "integrity.json").write_bytes(json_bytes({"files": files}))
                verify(pair)
            if stop:
                break
    except Exception as exc:
        stop = type(exc).__name__
    finally:
        await inner.aclose()
        (output / "receipt.json").write_bytes(
            json_bytes(
                {
                    "requests": count,
                    "stop": stop,
                    "origin": "observed" if transport is None else "simulated",
                    "openalex_access": "api_key_query_parameter",
                    "crossref_access": "anonymous",
                }
            )
        )
        files = {
            p.relative_to(output).as_posix(): digest(p.read_bytes())
            for p in output.rglob("*")
            if p.is_file()
        }
        (output / "integrity.json").write_bytes(json_bytes({"files": files}))
    verify_output(output)
    return stop is None and count == 14


def verify_output(output: Path) -> None:
    verify(output)
    for pair in sorted(output.glob("paper-*")):
        verify(pair)
    receipt = json.loads((output / "receipt.json").read_bytes())
    attempts = sorted(output.glob("paper-*/attempt-*/record.json"))
    if len(attempts) != receipt["requests"] or len(attempts) > 14:
        raise ValueError("Attempt count mismatch")
    plan = json.loads((output / "plan.json").read_bytes())
    for record_path, row in zip(attempts, plan["requests"], strict=False):
        record = json.loads(record_path.read_bytes())
        if (record["url"], record["provider"]) != (row["url"], row["provider"]):
            raise ValueError("Captured request differs from inventory")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--stopped", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorize-live", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify_output(args.verify)
        print("Evidence inventory and offline replay verified")
        return
    if not all(
        (
            args.snapshot,
            args.prior,
            args.stopped,
            args.plan,
            args.plan_sha256,
            args.output,
            args.authorize_live,
        )
    ):
        parser.error("Live execution requires all plan and authorization arguments")
    content = args.plan.read_bytes()
    if digest(content) != args.plan_sha256:
        raise ValueError("Plan hash mismatch")
    ok = asyncio.run(run(args.snapshot, args.prior, json.loads(content), args.output, args.stopped))
    print("Completed 14 requests" if ok else "STOP: preserve evidence; no retries")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
