"""Sealed offline plan and sequential raw-evidence capture for the remaining seven papers."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from citeprobe.benchmark_smoke import ANCHOR, DATASET_HASH, LIMIT, Capture, digest, verify
from citeprobe.dataset import load_dataset
from citeprobe.evidence_io import json_bytes
from citeprobe.lookup_inputs import canonical_tasks, fingerprint
from citeprobe.pilot_review import verify_pilot
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.resolution_models import ResolverConfig
from citeprobe.resolver import Resolver, save_results

PRIOR_ANCHOR = "56427baa74dd454399db9d4b6644d40a62746330e7c56868d1879a6fe92adc35"
PROVIDERS = (OpenAlex(), Crossref())


def prepare(snapshot: Path, prior: Path) -> dict[str, Any]:
    verify_pilot(snapshot, anchor=ANCHOR)
    if digest((snapshot / "dataset.json").read_bytes()) != DATASET_HASH:
        raise ValueError("Frozen dataset hash mismatch")
    if digest((prior / "integrity.json").read_bytes()) != PRIOR_ANCHOR:
        raise ValueError("Prior attempt anchor mismatch")
    verify(prior)
    old = json.loads((prior / "plan.json").read_bytes())
    receipt = json.loads((prior / "receipt.json").read_bytes())
    if receipt != {"requests": 2, "stop": None} or old["source_id"] != "arxiv:2611.07721":
        raise ValueError("Incomplete prior smoke test")
    for provider in PROVIDERS:
        result = json.loads((prior / f"{provider.name}-lookups.json").read_bytes())["results"][0]
        if result["outcome"] not in {"FOUND", "NOT_FOUND"} or result["parsing_warnings"]:
            raise ValueError("Unsuccessful prior smoke test")
    dataset = load_dataset(snapshot / "dataset.json")
    tasks = canonical_tasks(dataset)
    if len(tasks) != 8 or tasks[0].source_id != old["source_id"]:
        raise ValueError("Unexpected frozen task order")
    mappings = json.loads((snapshot / "identity-mappings.json").read_bytes())
    secrets = [v for c in dataset.citations for v in (c.citation_id, c.arxiv_id, c.doi) if v]
    secrets.extend(i["value"] for m in mappings["mappings"] for i in m["identifiers"])
    items: list[dict[str, Any]] = []
    for task in tasks[1:]:
        metadata = task.metadata.model_copy(update={"volume": None, "issue": None})
        for provider in PROVIDERS:
            req = provider.request(metadata, None)
            url = str(httpx.Request("GET", req.endpoint, params=req.params).url)
            if any(s.casefold() in url.casefold() for s in secrets):
                raise ValueError("Ground-truth identifier leaked into request")
            items.append(
                {
                    "number": len(items) + 1,
                    "source_id": task.source_id,
                    "provider": provider.name,
                    "method": "GET",
                    "url": url,
                    "metadata": metadata.model_dump(mode="json"),
                }
            )
    if len(items) != 14 or len({x["url"] for x in items}) != 14:
        raise ValueError("Request inventory is not unique")
    return {
        "schema_version": "1.0",
        "dataset_sha256": DATASET_HASH,
        "frozen_anchor": ANCHOR,
        "prior_anchor": PRIOR_ANCHOR,
        "maximum_requests": 14,
        "retries": 0,
        "redirects": False,
        "pagination": False,
        "capture_limit": LIMIT,
        "requests": items,
    }


async def run(
    snapshot: Path,
    prior: Path,
    plan: dict[str, Any],
    output: Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    if plan != prepare(snapshot, prior):
        raise ValueError("Plan differs from frozen source inventory")
    if transport is None and any(
        os.environ.get(k) for k in ("OPENALEX_API_KEY", "CROSSREF_API_KEY", "CROSSREF_MAILTO")
    ):
        raise ValueError("Provider credentials/contact require separate approval")
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
            capture = Capture(inner, pair, [row["url"] for row in rows])
            try:
                for provider in PROVIDERS:
                    if count >= 14:
                        raise ValueError("Request budget exhausted")
                    resolver = Resolver(
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
        (args.snapshot, args.prior, args.plan, args.plan_sha256, args.output, args.authorize_live)
    ):
        parser.error("Live execution requires all plan and authorization arguments")
    content = args.plan.read_bytes()
    if digest(content) != args.plan_sha256:
        raise ValueError("Plan hash mismatch")
    ok = asyncio.run(run(args.snapshot, args.prior, json.loads(content), args.output))
    print("Completed 14 requests" if ok else "STOP: preserve evidence; no retries")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
