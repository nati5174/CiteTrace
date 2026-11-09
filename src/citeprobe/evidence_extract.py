"""Deterministic source-located extraction. Missing evidence is never a negative claim."""

import gzip
import io
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin

from citeprobe.acquisition_sources import xml_root
from citeprobe.evidence_models import Extraction, RawEvidence, public_url

LIMIT = 2_000_000
WORDS = {
    "arxiv_api_doc": (
        "publish",
        "submit",
        "date",
        "pagin",
        "start",
        "max_results",
        "version",
        "updat",
    ),
    "arxiv_rss_doc": (
        "feed",
        "midnight",
        "retention",
        "coverage",
        "histor",
        "announc",
        "categor",
        "updat",
        "date",
        "publish",
        "submit",
        "replac",
        "cross-list",
    ),
}


def decoded_body(record: RawEvidence, raw: bytes, *, limit: int = LIMIT) -> bytes:
    from citeprobe.source_limits import validate_request_limit

    validate_request_limit(record.request, limit)
    encoding = (record.content_encoding or "identity").lower().strip()
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
            result = zipped.read(limit + 1)
    elif encoding == "deflate":
        decoder = zlib.decompressobj()
        result = decoder.decompress(raw, limit + 1)
        if not decoder.eof:
            raise ValueError("Incomplete or excessive deflate stream")
    elif encoding in {"identity", ""}:
        result = raw
    else:
        raise ValueError("Unsupported content encoding")
    if len(result) > limit:
        raise ValueError("Decoded body exceeds extraction bound")
    return result


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None]
    path: str
    line: int
    children: list["Node | str"] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(
            " ".join(c.text() if isinstance(c, Node) else c for c in self.children).split()
        )


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, "/document", 1)
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self.stack[-1]
        ordinal = 1 + sum(isinstance(c, Node) and c.tag == tag for c in parent.children)
        node = Node(tag, dict(attrs), f"{parent.path}/{tag}[{ordinal}]", self.getpos()[0])
        parent.children.append(node)
        if tag not in {"meta", "link", "br", "img", "hr", "input", "source", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def nodes(node: Node) -> list[Node]:
    classes = (node.attrs.get("class") or "").lower().split()
    if (
        node.tag in {"nav", "header", "footer", "aside", "script", "style"}
        or node.attrs.get("role") == "navigation"
        or any(c in {"toc", "sidebar", "md-nav", "table-of-contents"} for c in classes)
    ):
        return []
    return [node, *(n for c in node.children if isinstance(c, Node) for n in nodes(c))]


def documentation(text: str, url: str, kind: str) -> tuple[dict[str, Any], list[str]]:
    parser = Document()
    parser.feed(text)
    all_nodes = nodes(parser.root)
    roots = [n for n in all_nodes if n.tag == "main"] or [
        n for n in all_nodes if n.tag == "article"
    ]
    selected = [n for root in roots for n in nodes(root)] if roots else all_nodes
    statements: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    heading = ""
    anchor: str | None = None
    for node in selected:
        if re.fullmatch(r"h[1-6]", node.tag):
            heading, anchor = node.text(), node.attrs.get("id")
        words = node.text()
        location = {
            "dom_path": node.path,
            "line": node.line,
            "section": heading or None,
            "anchor": node.attrs.get("id") or anchor,
        }
        ref = url + ("#" + quote(str(location["anchor"])) if location["anchor"] else "")
        if node.tag in {"p", "li", "dd", "pre", "tr"} and any(
            word in (heading + " " + words).casefold() for word in WORDS[kind]
        ):
            statements.append(
                {
                    "text": words[:3000],
                    "text_truncated": len(words) > 3000,
                    "source_url": ref,
                    "location": location,
                }
            )
        if node.tag == "a" and node.attrs.get("href"):
            href = urljoin(url, str(node.attrs["href"]))
            # Fragments are source locations, not extra requests. Never follow any links.
            try:
                public_url(href.split("#", 1)[0])
            except ValueError:
                continue
            if any(
                w in (words + " " + href).casefold()
                for w in (
                    "specification",
                    "atom",
                    "rss",
                    "histor",
                    "archive",
                    "availability",
                    "date",
                )
            ):
                links.append({"url_not_fetched": href, "text": words, "location": location})
    warnings = []
    if not roots:
        warnings.append("No main/article element; used navigation-filtered document")
    if not statements:
        warnings.append("No relevant statements extracted; not proof documentation is absent")
    if len(statements) > 80 or len(links) > 40:
        warnings.append("Extraction count bound reached; raw bytes retain omitted content")
    return {"statements": statements[:80], "relevant_links_not_fetched": links[:40]}, warnings


def atom(text: str) -> tuple[dict[str, Any], list[str]]:
    root = xml_root(text)
    if root.tag.rsplit("}", 1)[-1] != "feed":
        raise ValueError("Expected Atom feed")
    warnings: list[str] = []
    if not root.tag.startswith("{http://www.w3.org/2005/Atom}"):
        warnings.append("Nonstandard Atom namespace; local field names retained")

    def fields(node: Any, path: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        counters: dict[str, int] = {}
        for child in node:
            name = child.tag.rsplit("}", 1)[-1]
            counters[name] = counters.get(name, 0) + 1
            locator = f"{path}/{name}[{counters[name]}]"
            if name not in {
                "id",
                "title",
                "published",
                "updated",
                "subtitle",
                "status",
                "error",
                "category",
                "primary_category",
                "announce_type",
                "link",
                "generator",
            }:
                continue
            value = "".join(child.itertext()).strip()
            item: dict[str, Any] = {"raw": value, "xml_path": locator, "expanded_tag": child.tag}
            if name in {"category", "primary_category", "link"}:
                item["attributes"] = {
                    k: v
                    for k, v in child.attrib.items()
                    if k in {"term", "scheme", "label", "href", "rel", "type"}
                }
            if name in {"published", "updated"}:
                item["utc"] = None
                try:
                    timestamp = datetime.fromisoformat(value)
                    if timestamp.tzinfo is None:
                        raise ValueError("No timezone")
                    item["utc"] = timestamp.astimezone(UTC).isoformat()
                except ValueError:
                    warnings.append(f"Missing/malformed/timezone-free timestamp: {locator}")
            result.setdefault(name, []).append(item)
        return result

    entries = [n for n in root if n.tag.rsplit("}", 1)[-1] == "entry"]
    payload: dict[str, Any] = {
        "root_tag": root.tag,
        "feed": fields(root, "/feed"),
        "entry_count": len(entries),
        "empty_feed": not entries,
        "entries": [fields(entry, f"/feed/entry[{i}]") for i, entry in enumerate(entries, 1)],
    }
    if "updated" not in payload["feed"]:
        warnings.append("Feed updated timestamp not supplied")
    for i, entry in enumerate(payload["entries"], 1):
        for name in ("id", "published", "updated"):
            if name not in entry:
                warnings.append(f"Missing entry field: /feed/entry[{i}]/{name}")
    return payload, warnings


def abstract_v1(text: str) -> tuple[dict[str, Any], list[str]]:
    document = Document()
    document.feed(text)
    declared_ids = [
        n.attrs.get("content")
        for n in nodes(document.root)
        if n.tag == "meta" and n.attrs.get("name") == "citation_arxiv_id"
    ]
    histories = [
        n
        for n in nodes(document.root)
        if "submission-history" in (n.attrs.get("class") or "").split()
    ]
    matches = []
    for node in histories:
        found = re.search(
            r"\[v1\]\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+"
            r"[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+UTC)",
            node.text(),
        )
        if found:
            timestamp = parsedate_to_datetime(found[1])
            if timestamp.tzinfo is None:
                raise ValueError("Unqualified v1 timezone")
            matches.append(
                {
                    "raw": found[1],
                    "utc": timestamp.astimezone(UTC).isoformat(),
                    "dom_path": node.path,
                    "line": node.line,
                }
            )
    if len(matches) != 1:
        return {
            "v1_submission": None,
            "arxiv_id": declared_ids[0] if len(declared_ids) == 1 else None,
        }, ["Unique authoritative v1 submission history not extracted"]
    return {
        "v1_submission": matches[0],
        "arxiv_id": declared_ids[0] if len(declared_ids) == 1 else None,
        "date_basis": "first_arxiv_submission",
        "verification_status": "pending_curator",
    }, []


def extract(record: RawEvidence, raw: bytes) -> Extraction:
    warnings: list[str] = []
    payload: dict[str, Any] = {}
    status = "UNAVAILABLE"
    if not record.body_complete:
        warnings.append("Incomplete response; hash refers to retained bytes only")
    elif record.http_status != 200 or record.exception_type:
        warnings.append("No complete successful source response")
    else:
        try:
            kind = record.request.source_kind
            media = (record.content_type or "").split(";", 1)[0].strip().lower()
            expected = (
                {"text/html", "application/xhtml+xml"}
                if kind.endswith("doc") or kind == "arxiv_abstract"
                else {"application/json"}
                if kind == "upstream_json"
                else {"application/atom+xml", "application/xml", "text/xml"}
            )
            if media and media not in expected:
                raise ValueError("Unexpected content type")
            if not media:
                warnings.append(
                    "Content type missing; parser choice comes from recorded source kind"
                )
            body = decoded_body(record, raw)
            encoding = record.character_encoding or "utf-8-sig"
            text = body.decode(encoding, errors="strict")
            url = record.final_url or record.request.url
            if kind.endswith("doc"):
                payload, extra = documentation(text, url, kind)
            elif kind == "arxiv_abstract":
                payload, extra = abstract_v1(text)
            elif kind == "upstream_json":
                value = json.loads(text)
                payload, extra = (
                    {
                        "commit_sha_values": [v.get("sha") for v in value if isinstance(v, dict)]
                        if isinstance(value, list)
                        else []
                    },
                    [],
                )
            elif kind == "arxiv_atom":
                payload, extra = atom(text)
            else:
                root = xml_root(text)
                payload, extra = {"root_tag": root.tag, "note": "Raw acquisition XML retained"}, []
            warnings.extend(extra)
            status = "EXTRACTED"
        except (ValueError, LookupError, OSError, EOFError, zlib.error):
            warnings.append("Extraction failed; source content/semantics not proven absent")
    return Extraction(
        record_id=record.record_id,
        source_url=record.final_url or record.request.url,
        raw_body_sha256=record.raw_body_sha256,
        status=status,
        payload=payload,
        warnings=tuple(warnings),
    )
