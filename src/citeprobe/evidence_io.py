"""Raw HTTP evidence capture and offline verification. No request is made on import."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from citeprobe.evidence_extract import LIMIT, extract
from citeprobe.evidence_models import SAFE_HEADERS, EvidenceBudget, Extraction, RawEvidence
from citeprobe.lookup_inputs import fingerprint


def write(path: Path, body: bytes) -> None:
    with path.open("xb") as output:
        output.write(body)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def begin_batch(directory: Path, budget: EvidenceBudget) -> None:
    directory.mkdir(exist_ok=False)
    write(directory / "budget.json", json_bytes(budget.model_dump(mode="json")))


def prepare(directory: Path, budget: EvidenceBudget, ordinal: int) -> tuple[Path, httpx.Request]:
    if EvidenceBudget.model_validate_json((directory / "budget.json").read_bytes()) != budget:
        raise ValueError("Evidence authorization budget changed")
    if not 1 <= ordinal <= len(budget.requests) or ordinal > budget.maximum_requests:
        raise ValueError("Request exceeds authorized budget")
    for previous in range(1, ordinal):
        if not (directory / f"request-{previous:03d}" / "record.json").is_file():
            raise ValueError("Request budget ordinals must be sequential")
    target = directory / f"request-{ordinal:03d}"
    target.mkdir(exist_ok=False)  # An attempt cannot be overwritten or silently repeated.
    request = httpx.Request(
        "GET",
        budget.requests[ordinal - 1].url,
        headers={"User-Agent": "CiteProbe/0.1 evidence-v2", "Accept-Encoding": "identity"},
    )
    return target, request


def store(
    directory: Path,
    budget: EvidenceBudget,
    ordinal: int,
    raw: bytes,
    started: datetime,
    headers_at: datetime | None,
    finished: datetime,
    response: httpx.Response | None,
    complete: bool,
    error: str | None,
) -> RawEvidence:
    headers = {k: v for k, v in response.headers.items() if k in SAFE_HEADERS} if response else {}
    content_type = headers.get("content-type")
    charset = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type or "", re.I)
    budget_hash = fingerprint(budget.model_dump(mode="json"))
    request = budget.requests[ordinal - 1]
    record = RawEvidence(
        record_id="0" * 64,
        budget_fingerprint=budget_hash,
        request_id=fingerprint(
            {"budget": budget_hash, "ordinal": ordinal, "request": request.model_dump(mode="json")}
        ),
        request_ordinal=ordinal,
        request=request,
        origin=budget.origin,
        started_at=started,
        headers_received_at=headers_at,
        finished_at=finished,
        http_status=response.status_code if response is not None else None,
        final_url=str(response.url) if response is not None else None,
        response_headers=headers,
        content_type=content_type,
        content_encoding=headers.get("content-encoding"),
        character_encoding=charset[1] if charset else None,
        raw_body_sha256=hashlib.sha256(raw).hexdigest(),
        raw_body_size=len(raw),
        body_complete=complete,
        exception_type=error,
    )
    record = record.model_copy(
        update={"record_id": fingerprint(record.model_dump(mode="json", exclude={"record_id"}))}
    )
    write(directory / "body.bin", raw)
    write(directory / "record.json", json_bytes(record.model_dump(mode="json")))
    write(directory / "extracted.json", json_bytes(extract(record, raw).model_dump(mode="json")))
    return record


def complete_body(response: httpx.Response, body: bytes | bytearray) -> bool:
    length = response.headers.get("content-length")
    return length is None or (length.isdigit() and int(length) == len(body))


def capture_sync(
    client: httpx.Client,
    directory: Path,
    budget: EvidenceBudget,
    ordinal: int,
    *,
    raw_limit: int = LIMIT,
) -> RawEvidence:
    from citeprobe.source_limits import validate_request_limit

    if not 1 <= ordinal <= len(budget.requests):
        raise ValueError("Request exceeds authorized budget")
    validate_request_limit(budget.requests[ordinal - 1], raw_limit)
    target, request = prepare(directory, budget, ordinal)
    start = datetime.now(UTC)
    headers_at = None
    response = None
    body = bytearray()
    complete, error = False, None
    try:
        response = client.send(request, stream=True, auth=None, follow_redirects=False)
        headers_at = datetime.now(UTC)
        try:
            for chunk in response.iter_raw():
                if len(body) + len(chunk) > raw_limit:
                    body.extend(chunk[: raw_limit - len(body)])
                    raise ValueError("Response bound exceeded")
                body.extend(chunk)
            complete = complete_body(response, body)
            if not complete:
                error = "ContentLengthMismatch"
        finally:
            response.close()
    except (httpx.HTTPError, httpx.StreamError, ValueError) as exc:
        error = type(exc).__name__
    return store(
        target,
        budget,
        ordinal,
        bytes(body),
        start,
        headers_at,
        datetime.now(UTC),
        response,
        complete,
        error,
    )


async def capture_async(
    client: httpx.AsyncClient,
    directory: Path,
    budget: EvidenceBudget,
    ordinal: int,
    *,
    raw_limit: int = LIMIT,
) -> RawEvidence:
    from citeprobe.source_limits import validate_request_limit

    if not 1 <= ordinal <= len(budget.requests):
        raise ValueError("Request exceeds authorized budget")
    validate_request_limit(budget.requests[ordinal - 1], raw_limit)
    target, request = prepare(directory, budget, ordinal)
    start = datetime.now(UTC)
    headers_at = None
    response = None
    body = bytearray()
    complete, error = False, None
    try:
        response = await client.send(request, stream=True, auth=None, follow_redirects=False)
        headers_at = datetime.now(UTC)
        try:
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > raw_limit:
                    body.extend(chunk[: raw_limit - len(body)])
                    raise ValueError("Response bound exceeded")
                body.extend(chunk)
            complete = complete_body(response, body)
            if not complete:
                error = "ContentLengthMismatch"
        finally:
            await response.aclose()
    except (httpx.HTTPError, httpx.StreamError, ValueError) as exc:
        error = type(exc).__name__
    return store(
        target,
        budget,
        ordinal,
        bytes(body),
        start,
        headers_at,
        datetime.now(UTC),
        response,
        complete,
        error,
    )


def finish_batch(directory: Path) -> str:
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Evidence symlinks are unsupported")
    files = {
        str(p.relative_to(directory)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }
    budget = EvidenceBudget.model_validate_json((directory / "budget.json").read_bytes())
    attempts = len([p for p in directory.iterdir() if p.is_dir()])
    manifest = {
        "schema_version": "2.0",
        "files": files,
        "attempt_count": attempts,
        "planned_request_count": len(budget.requests),
        "plan_complete": attempts == len(budget.requests),
    }
    write(directory / "manifest.json", json_bytes(manifest))
    verify_batch(directory)
    return hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()


def verify_batch(directory: Path, *, anchor: str | None = None) -> tuple[Extraction, ...]:
    if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Evidence symlinks are unsupported")
    content = (directory / "manifest.json").read_bytes()
    if anchor and hashlib.sha256(content).hexdigest() != anchor:
        raise ValueError("External evidence anchor mismatch")
    manifest = json.loads(content)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "2.0"
        or not isinstance(manifest.get("files"), dict)
    ):
        raise ValueError("Version 2 raw evidence required; legacy projections are not raw bodies")
    if set(manifest) != {
        "schema_version",
        "files",
        "attempt_count",
        "planned_request_count",
        "plan_complete",
    }:
        raise ValueError("Unexpected evidence manifest fields")
    actual = {
        str(p.relative_to(directory)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file() and p != directory / "manifest.json"
    }
    if actual != manifest["files"]:
        raise ValueError("Evidence file inventory/hash mismatch")
    budget = EvidenceBudget.model_validate_json((directory / "budget.json").read_bytes())
    folders = sorted(p for p in directory.iterdir() if p.is_dir())
    if not folders or len(folders) > len(budget.requests):
        raise ValueError("Invalid attempt count")
    if (
        manifest.get("attempt_count") != len(folders)
        or manifest.get("planned_request_count") != len(budget.requests)
        or manifest.get("plan_complete") != (len(folders) == len(budget.requests))
    ):
        raise ValueError("Manifest attempt/plan inventory mismatch")
    expected = {"budget.json"}
    outputs = []
    for ordinal, folder in enumerate(folders, 1):
        if folder.name != f"request-{ordinal:03d}":
            raise ValueError("Request inventory/order mismatch")
        expected.update(
            f"{folder.name}/{name}" for name in ("body.bin", "record.json", "extracted.json")
        )
        record = RawEvidence.model_validate_json((folder / "record.json").read_bytes())
        raw = (folder / "body.bin").read_bytes()
        if (
            record.budget_fingerprint != fingerprint(budget.model_dump(mode="json"))
            or record.request != budget.requests[ordinal - 1]
            or record.request_ordinal != ordinal
            or record.origin != budget.origin
        ):
            raise ValueError("Request authorization budget mismatch")
        if record.record_id != fingerprint(record.model_dump(mode="json", exclude={"record_id"})):
            raise ValueError("Raw evidence record fingerprint mismatch")
        if record.request_id != fingerprint(
            {
                "budget": record.budget_fingerprint,
                "ordinal": ordinal,
                "request": record.request.model_dump(mode="json"),
            }
        ):
            raise ValueError("Request identity mismatch")
        if (
            hashlib.sha256(raw).hexdigest() != record.raw_body_sha256
            or len(raw) != record.raw_body_size
        ):
            raise ValueError("Raw body hash/size mismatch")
        length = record.response_headers.get("content-length")
        if (
            record.body_complete
            and length is not None
            and (not length.isdigit() or int(length) != len(raw))
        ):
            raise ValueError("Complete response length contradicts raw bytes")
        if record.final_url and httpx.URL(record.final_url) != httpx.URL(record.request.url):
            raise ValueError("Final URL differs despite redirects being disabled")
        for key, value in (
            ("content-type", record.content_type),
            ("content-encoding", record.content_encoding),
        ):
            if record.response_headers.get(key) != value:
                raise ValueError("Response header metadata mismatch")
        saved = Extraction.model_validate_json((folder / "extracted.json").read_bytes())
        if extract(record, raw) != saved:
            raise ValueError("Extraction provenance/version/replay mismatch")
        if (folder / "extracted.json").read_bytes() != json_bytes(saved.model_dump(mode="json")):
            raise ValueError("Extraction serialization is not canonical byte-identical replay")
        outputs.append(saved)
    if expected != set(actual):
        raise ValueError("Unexpected evidence files")
    return tuple(outputs)
