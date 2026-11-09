"""Milestone 3C-4: fixed three-URL feasibility batch, never paper acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from citeprobe.acquisition_sources import xml_root

URLS = (
    "https://info.arxiv.org/help/api/user-manual.html",
    "https://info.arxiv.org/help/rss.html",
    "https://rss.arxiv.org/atom/cs.CL",
)
KEYWORDS = (
    "announcement",
    "announced",
    "submission",
    "submitted",
    "published",
    "historical",
    "archive",
    "retention",
    "date",
    "updated",
)


class Documentation(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.text.append(data.strip())


def evidence(url: str, body: bytes) -> dict[str, Any]:
    value = body.decode("utf-8-sig")
    if url == URLS[2]:
        root = xml_root(value)

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        if local(root.tag) not in {"feed", "rss"}:
            raise ValueError("Expected Atom/RSS source feed")
        entries = [node for node in root.iter() if local(node.tag) in {"entry", "item"}]
        fields = sorted({local(child.tag) for entry in entries for child in entry})
        types = Counter(
            (child.text or "").strip()
            for entry in entries
            for child in entry
            if local(child.tag) == "announce_type"
        )
        dates = [
            child.text
            for entry in entries
            for child in entry
            if local(child.tag) in {"published", "updated", "pubDate"} and child.text
        ]
        return {
            "format": local(root.tag),
            "entry_count": len(entries),
            "entry_field_names": fields,
            "announcement_type_counts": dict(types),
            "date_examples": dates[:5],
            "note": "No paper IDs/titles/authors retained; feed date semantics and historical "
            "completeness require review. No linked records fetched.",
        }
    parser = Documentation()
    parser.feed(value)
    text = " ".join(" ".join(parser.text).split())
    snippets: list[str] = []
    for keyword in KEYWORDS:
        start = 0
        for _ in range(2):
            position = text.casefold().find(keyword, start)
            if position < 0:
                break
            snippet = text[max(0, position - 150) : position + 450]
            if snippet not in snippets:
                snippets.append(snippet)
            start = position + len(keyword)
    links: set[str] = set()
    for link in parser.links:
        parsed = urlsplit(urljoin(url, link))
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and (parsed.hostname == "arxiv.org" or parsed.hostname.endswith(".arxiv.org"))
            and not parsed.username
            and not parsed.password
        ):
            links.add(urlunsplit((parsed.scheme, parsed.hostname, parsed.path, "", "")))
    return {
        "relevant_excerpts": snippets[:16],
        "official_links_not_fetched": sorted(links)[:40],
        "note": "Bounded excerpts only; omitted text may contain relevant qualifications. "
        "HTTP 200 does not establish protocol feasibility.",
    }


def collect(
    client: httpx.Client, directory: Path, *, origin: Literal["observed", "simulated"]
) -> None:
    if client.follow_redirects:
        raise ValueError("Redirects must be disabled")
    for index, url in enumerate(URLS, 1):
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "origin": origin,
            "source_url": url,
            "purpose": "source feasibility only; no empirical paper dataset",
            "started_at": datetime.now(UTC).isoformat(),
            "http_status": None,
            "exception_type": None,
            "evidence": None,
        }
        clock = monotonic()
        try:
            with client.stream("GET", url) as response:
                record["http_status"] = response.status_code
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 2_000_000:
                        raise ValueError("Response exceeds source-feasibility bound")
                    body.extend(chunk)
                record["response_body_sha256"] = hashlib.sha256(body).hexdigest()
                record["response_bytes"] = len(body)
                if response.status_code == 200:
                    record["evidence"] = evidence(url, bytes(body))
                else:
                    record["limitation"] = "Non-200 response; no redirect or retry"
        except (httpx.HTTPError, ValueError) as error:
            record["exception_type"] = type(error).__name__
            record["limitation"] = "Unavailable/oversized/malformed evidence; no retry"
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["latency_ms"] = (monotonic() - clock) * 1000
        projection = json.dumps(record["evidence"], sort_keys=True, ensure_ascii=False)
        record["evidence_sha256"] = hashlib.sha256(projection.encode()).hexdigest()
        with (directory / f"{index:02d}-source.json").open("x", encoding="utf-8") as target:
            json.dump(record, target, indent=2, ensure_ascii=False)
            target.write("\n")
        print(f"{index}/3 HTTP {record['http_status']}; {record['exception_type']}; {url}")
        if record["exception_type"] == "ConnectError":
            print("Connection blocked/failed: batch stopped. Do not rerun.")
            break
        if index < len(URLS):
            sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-authorized-batch", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.execute_authorized_batch:
        parser.error("Use only after explicit authorization; execution flag required")
    plan = Path("docs/research/pilot-acquisition-v1.md")
    text = plan.read_text(encoding="utf-8")
    if not all(url in text for url in URLS):
        raise ValueError("Fixed URLs differ from the documented source-feasibility plan")
    args.output_dir.mkdir(exist_ok=False)
    manifest = {
        "schema_version": "1.0",
        "maximum_requests": 3,
        "urls": URLS,
        "authorization": "User-approved Milestone 3C-4 source feasibility only",
        "retries": 0,
        "redirects": False,
        "pagination": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "httpx_version": httpx.__version__,
        "ACL_request_included": False,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with httpx.Client(
        transport=httpx.HTTPTransport(retries=0),
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "CiteProbe/0.1 source-feasibility"},
    ) as client:
        collect(client, args.output_dir, origin="observed")


if __name__ == "__main__":
    main()
