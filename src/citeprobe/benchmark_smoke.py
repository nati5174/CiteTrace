"""Opt-in, two-request smoke capture using the existing resolver and adapters."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from citeprobe.dataset import load_dataset
from citeprobe.evidence_io import json_bytes
from citeprobe.lookup_inputs import canonical_tasks, fingerprint
from citeprobe.pilot_review import verify_pilot
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.resolution_models import LookupBundle, ResolverConfig
from citeprobe.resolver import Resolver, save_results

DATASET_HASH = "a8ffee33582fd352fe72db5c410300ac29a92c5e0cbca94b76b1a14a5e5b156d"
ANCHOR = "25472018fe08a2a5c61d564f6246f233fcc019b5554677487c2c20ad953ad5ac"
SAFE_HEADERS = {"content-type", "content-encoding", "content-length", "retry-after", "date"}
LIMIT = 10_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Capture(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, output: Path, urls: list[str]) -> None:
        self.inner, self.output, self.urls = inner, output, urls
        self.count = 0
        self.failed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.failed or self.count >= 2 or str(request.url) != self.urls[self.count]:
            raise ValueError("Request inventory/budget violation")
        self.count += 1
        directory = self.output / f"attempt-{self.count:03d}"
        directory.mkdir()
        raw = bytearray()
        response = None
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "request_number": self.count,
            "provider": ("openalex", "crossref")[self.count - 1],
            "method": "GET",
            "url": str(request.url),
            "started_at": datetime.now(UTC).isoformat(),
            "status": None,
            "headers": {},
            "complete": False,
            "exception_type": None,
        }
        try:
            response = await self.inner.handle_async_request(request)
            record["status"] = response.status_code
            record["headers"] = {k: v for k, v in response.headers.items() if k in SAFE_HEADERS}
            async for chunk in response.aiter_raw():
                remaining = LIMIT - len(raw)
                raw.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    raise httpx.ReadError("Capture limit exceeded")
            length = response.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) != len(raw)):
                raise httpx.ReadError("Incomplete response length")
            record["complete"] = True
            self.failed = not 200 <= response.status_code < 300
        except Exception as exc:
            self.failed = True
            record["exception_type"] = type(exc).__name__
            raise
        finally:
            record["finished_at"] = datetime.now(UTC).isoformat()
            record["size"] = len(raw)
            record["sha256"] = digest(bytes(raw))
            (directory / "body.bin").write_bytes(raw)
            (directory / "record.json").write_bytes(json_bytes(record))
            if response is not None:
                await response.aclose()
        assert response is not None
        return httpx.Response(response.status_code, headers=response.headers, content=bytes(raw))


def verify(directory: Path) -> None:
    manifest = json.loads((directory / "integrity.json").read_bytes())
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"integrity.json"}:
        raise ValueError("Evidence inventory mismatch")
    for name, expected in manifest["files"].items():
        if digest((directory / name).read_bytes()) != expected:
            raise ValueError("Evidence hash mismatch")
    for folder in sorted(directory.glob("attempt-*")):
        record = json.loads((folder / "record.json").read_bytes())
        raw = (folder / "body.bin").read_bytes()
        if digest(raw) != record["sha256"] or len(raw) != record["size"]:
            raise ValueError("Raw body hash/size mismatch")
        bundle_path = directory / (record["provider"] + "-lookups.json")
        if not bundle_path.exists():
            continue  # Unexpected local exception is retained in the stop receipt.
        bundle = LookupBundle.model_validate_json(bundle_path.read_bytes())
        result = bundle.results[0]
        if record["complete"] and record["status"] is not None:
            response = httpx.Response(record["status"], headers=record["headers"], content=raw)
            if digest(response.content) != result.attempts[0].response_body_sha256:
                raise ValueError("Resolver response hash differs from captured bytes")
            if result.outcome in {"FOUND", "NOT_FOUND"}:
                adapter = OpenAlex() if result.provider == "openalex" else Crossref()
                candidates, warnings = adapter.parse(response.json())
                if candidates != result.candidates or warnings != result.parsing_warnings:
                    raise ValueError("Candidate replay mismatch")


async def run(
    snapshot: Path, output: Path, *, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    verify_pilot(snapshot, anchor=ANCHOR)
    if digest((snapshot / "dataset.json").read_bytes()) != DATASET_HASH:
        raise ValueError("Unapproved dataset")
    dataset = load_dataset(snapshot / "dataset.json")
    task = canonical_tasks(dataset)[0]
    if task.source_id != "arxiv:2611.07721" or task.identifier is not None:
        raise ValueError("Unapproved smoke paper/strategy")
    task = task.model_copy(
        update={"metadata": task.metadata.model_copy(update={"volume": None, "issue": None})}
    )
    adapters = (OpenAlex(), Crossref())
    urls = []
    secrets = [v for c in dataset.citations for v in (c.citation_id, c.arxiv_id, c.doi) if v]
    mappings = json.loads((snapshot / "identity-mappings.json").read_bytes())
    secrets.extend(i["value"] for m in mappings["mappings"] for i in m["identifiers"])
    for adapter in adapters:
        req = adapter.request(task.metadata, None)
        if any(s.casefold() in json.dumps(req.params).casefold() for s in secrets):
            raise ValueError("Identifier leakage")
        urls.append(str(httpx.Request("GET", req.endpoint, params=req.params).url))
    output.mkdir(exist_ok=False)
    (output / "plan.json").write_bytes(
        json_bytes(
            {
                "schema_version": "1.0",
                "origin": "observed" if transport is None else "simulated",
                "dataset_sha256": DATASET_HASH,
                "source_id": task.source_id,
                "metadata": task.metadata.model_dump(mode="json"),
                "urls": urls,
                "maximum_requests": 2,
                "retries": 0,
                "redirects": False,
                "capture_limit": LIMIT,
            }
        )
    )
    inner = transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    capture = Capture(inner, output, urls)
    stop = None
    try:
        for adapter in adapters:
            resolver = Resolver(
                ResolverConfig(max_attempts=1, concurrency=1, timeout_seconds=30), transport=capture
            )
            bundle = await resolver.resolve(
                [task],
                [adapter.name],
                dataset_version=dataset.dataset_version,
                dataset_fingerprint=fingerprint(dataset.model_dump(mode="json")),
                input_fingerprint=fingerprint(dataset.model_dump(mode="json")),
            )
            save_results(bundle, output / (adapter.name + "-lookups.json"))
            result = bundle.results[0]
            if (
                capture.failed
                or result.outcome not in {"FOUND", "NOT_FOUND"}
                or result.parsing_warnings
            ):
                stop = "Provider error, incomplete capture or parsing warning; do not retry"
                break
            folder = output / f"attempt-{capture.count:03d}"
            record = json.loads((folder / "record.json").read_bytes())
            if digest((folder / "body.bin").read_bytes()) != record["sha256"]:
                raise ValueError("Capture integrity failure")
    except Exception as exc:
        stop = type(exc).__name__  # Never persist exception text that may contain secrets.
    finally:
        await inner.aclose()
        (output / "receipt.json").write_bytes(json_bytes({"requests": capture.count, "stop": stop}))
        files = {
            p.relative_to(output).as_posix(): digest(p.read_bytes())
            for p in output.rglob("*")
            if p.is_file()
        }
        (output / "integrity.json").write_bytes(
            json_bytes({"schema_version": "1.0", "files": files})
        )
    verify(output)
    return stop is None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorize-live", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
        print("Offline raw hashes and candidate replay verified")
    else:
        if not args.authorize_live or not args.snapshot or not args.output:
            parser.error("Live execution requires --authorize-live --snapshot --output")
        success = asyncio.run(run(args.snapshot, args.output))
        print("Complete" if success else "STOP: evidence retained; do not retry")
        raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
