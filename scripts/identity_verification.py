"""Explicit local six-request identity evidence collection; never automatic adjudication."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from citeprobe.resolution_models import LookupBundle

DOIS = (
    "10.65215/pc26a033",
    "10.65215/2q58a426",
    "10.65215/r5bs2d54",
    "10.65215/nxvz2v36",
    "10.65215/mdcm8z23",
)
MAX_BYTES = 2_000_000


class ArxivMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, list[str]] = {}
        self.text: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden += 1
        name, content = fields.get("name"), fields.get("content")
        if tag == "meta" and name and content and name.startswith("citation_"):
            self.metadata.setdefault(name, []).append(content)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.text.append(data.strip())


def evidence(label: str, body: bytes) -> dict[str, Any]:
    if label == "arxiv":
        parser = ArxivMetadata()
        parser.feed(body.decode("utf-8"))
        text = "\n".join(parser.text)
        # Keep scholarly description/history; omit navigation and full HTML snapshots.
        start, stop = text.find("Abstract:"), text.find("Submission history")
        history_end = text.find("Access Paper:", stop) if stop >= 0 else -1
        return {
            "citation_metadata": parser.metadata,
            "abstract_section": text[start:stop] if 0 <= start < stop else None,
            "submission_history": text[stop:history_end] if 0 <= stop < history_end else None,
            "extraction_note": "Missing sections remain null; linked pages were not fetched.",
        }
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
        raise ValueError("Malformed Crossref record")
    record = payload["message"]
    keys = (
        "DOI",
        "title",
        "publisher",
        "container-title",
        "type",
        "abstract",
        "description",
        "created",
        "deposited",
        "indexed",
        "issued",
        "published",
        "published-print",
        "published-online",
        "relation",
        "alternative-id",
        "resource",
        "URL",
        "link",
        "reference-count",
        "is-referenced-by-count",
        "license",
    )
    result = {key: record[key] for key in keys if key in record}
    result["author"] = [
        {
            key: author[key]
            for key in ("given", "family", "name", "ORCID", "sequence")
            if key in author
        }
        for author in record.get("author", [])
        if isinstance(author, dict)
    ]
    refs = record.get("reference", [])
    result["target_related_references"] = [
        ref
        for ref in refs
        if "1706.03762" in json.dumps(ref) or "attention is all you need" in json.dumps(ref).lower()
    ]
    result["missing_fields"] = [key for key in keys if key not in record]
    return result


def collect(client: httpx.Client, output: Path) -> None:
    requests = [("arxiv", "1706.03762", "https://arxiv.org/abs/1706.03762")]
    requests.extend(
        ("crossref", doi, "https://api.crossref.org/works/" + quote(doi, safe="/")) for doi in DOIS
    )
    for number, (label, identifier, url) in enumerate(requests, 1):
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "data_origin": "observed",
            "purpose": "post-retrieval identity verification; not a retrieval observation",
            "source_url": url,
            "record_identifier": identifier,
            "started_at": datetime.now(UTC).isoformat(),
            "http_status": None,
            "exception_type": None,
            "evidence": None,
            "judgment": "UNDETERMINED",
        }
        started = time.monotonic()
        try:
            with client.stream("GET", url) as response:
                record["http_status"] = response.status_code
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise ValueError("Response exceeds evidence size limit")
                    body.extend(chunk)
                record["body_sha256"] = hashlib.sha256(body).hexdigest()
                record["body_bytes"] = len(body)
                if response.status_code == 200:
                    record["evidence"] = evidence(label, bytes(body))
                else:
                    record["missing_evidence_reason"] = "Non-200; no redirect or retry performed"
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            record["exception_type"] = type(error).__name__
            record["missing_evidence_reason"] = "Request or parsing failed; no retry performed"
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["latency_ms"] = (time.monotonic() - started) * 1000
        with (output / f"{number:02d}-{label}.json").open("x", encoding="utf-8") as target:
            json.dump(record, target, indent=2, ensure_ascii=False)
            target.write("\n")
        print(f"{number}/6 {label}: HTTP {record['http_status']}; {record['exception_type']}")
        if number < 6:
            time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = Path("artifacts/milestone-2/live-pilot/run-001/lookups.json")
    bundle = LookupBundle.model_validate_json(source.read_bytes())
    results = [r for r in bundle.results if r.provider == "crossref"]
    if (
        len(results) != 1
        or results[0].source_id != "arxiv-1706.03762"
        or tuple(c.doi for c in results[0].candidates) != DOIS
    ):
        raise ValueError("Pilot inventory differs from the six-request authorization")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "request_budget": 6,
        "retries": 0,
        "follow_redirects": False,
        "lookup_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "httpx_version": httpx.__version__,
        "note": "Evidence collection only. No verified mappings or identity decisions yet.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with httpx.Client(
        transport=httpx.HTTPTransport(retries=0),
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "CiteProbe/0.1 identity-verification-pilot"},
    ) as client:
        collect(client, args.output_dir)


if __name__ == "__main__":
    main()
