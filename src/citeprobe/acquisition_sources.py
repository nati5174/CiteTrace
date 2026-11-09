"""Authoritative discovery adapters. No evaluation-provider searches or implicit aliases."""

import re
from datetime import datetime, timedelta
from typing import Protocol, cast
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from citeprobe.acquisition_models import AcquiredCandidate, AcquisitionPlan, AcquisitionRequest
from citeprobe.identity import normalize_arxiv, normalize_doi

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


def xml_root(body: str, *, preserve_comments: bool = False, limit: int = 2_000_000) -> ET.Element:
    if type(limit) is not int or limit not in {2_000_000, 4_000_000}:
        raise ValueError("Unsupported XML parsing resource bound")
    if len(body.encode()) > limit or re.search(r"<!\s*(DOCTYPE|ENTITY)", body, re.I):
        raise ValueError("Unsafe or oversized source XML")
    try:
        return ET.fromstring(
            body, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=preserve_comments))
        )
    except ET.ParseError as error:
        raise ValueError("Malformed source XML") from error


def metadata_projection(body: str) -> str:
    root = xml_root(body, preserve_comments=True)
    allowed = {
        "feed",
        "entry",
        "id",
        "title",
        "author",
        "name",
        "published",
        "updated",
        "category",
        "primary_category",
        "doi",
        "totalResults",
        "startIndex",
        "itemsPerPage",
        "collection",
        "volume",
        "meta",
        "paper",
        "first",
        "last",
        "year",
        "booktitle",
        "url",
        "issue",
        "month",
    }

    def copy(node: ET.Element) -> ET.Element | None:
        if not isinstance(node.tag, str):
            return None
        name = node.tag.rsplit("}", 1)[-1]
        if name not in allowed:
            return None
        result = ET.Element(node.tag, {k: v for k, v in node.attrib.items() if k in {"id", "term"}})
        if name in {"title", "name", "first", "last", "booktitle"}:
            result.text = " ".join("".join(node.itertext()).split())
        else:
            result.text = node.text
            for child in node:
                kept = copy(child)
                if kept is not None:
                    result.append(kept)
        if name == "paper":
            for child in node:
                if cast(object, child.tag) is ET.Comment:
                    value = (child.text or "").strip()
                    if value.startswith("https://aclanthology.org/"):
                        ACLXml.identifier(value)
                        declared_url = ET.Element("url")
                        declared_url.text = value
                        result.append(declared_url)
        return result

    projected = copy(root)
    if projected is None:
        raise ValueError("Unsupported source envelope")
    return ET.tostring(projected, encoding="unicode")


def text(node: ET.Element, path: str) -> str:
    value = node.find(path)
    return " ".join("".join(value.itertext()).split()) if value is not None else ""


def doi(node: ET.Element, path: str) -> str | None:
    values = [normalize_doi("".join(value.itertext())) for value in node.findall(path)]
    if any(value is None for value in values) or len(set(values)) > 1:
        raise ValueError("Invalid or conflicting declared DOI identifiers")
    return values[0] if values else None


class DiscoverySource(Protocol):
    def request(self, plan: AcquisitionPlan) -> AcquisitionRequest: ...
    def records(self, body: str) -> tuple[list[ET.Element], int | None]: ...
    def candidate(self, record: ET.Element) -> AcquiredCandidate: ...


class ArxivAtom:
    def request(self, plan: AcquisitionPlan) -> AcquisitionRequest:
        if plan.experiment == "recent-preprints":
            assert plan.reference_date is not None
            low = (plan.reference_date - timedelta(days=60)).strftime("%Y%m%d") + "0000"
            high = plan.reference_date.strftime("%Y%m%d") + "2359"
        else:
            low, high = "201801010000", "202312312359"
        return AcquisitionRequest(
            endpoint="https://export.arxiv.org/api/query",
            params={
                "search_query": f"cat:cs.CL AND submittedDate:[{low} TO {high}]",
                "start": "0",
                "max_results": str(plan.max_records),
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
            },
        )

    def records(self, body: str) -> tuple[list[ET.Element], int | None]:
        root = xml_root(body)
        if root.tag != ATOM + "feed":
            raise ValueError("Malformed arXiv Atom envelope")
        entries = root.findall(ATOM + "entry")
        if any("arxiv.org/api/errors" in text(entry, ATOM + "id") for entry in entries):
            raise ValueError("arXiv returned a source API error")
        total = text(root, SEARCH + "totalResults")
        return entries, int(total) if total else None

    def candidate(self, record: ET.Element) -> AcquiredCandidate:
        identifier = normalize_arxiv(text(record, ATOM + "id"))
        if not identifier:
            raise ValueError("Missing or invalid arXiv identifier")
        submitted = datetime.fromisoformat(text(record, ATOM + "published"))
        updated = text(record, ATOM + "updated")
        category = record.find(ARXIV + "primary_category")
        return AcquiredCandidate(
            source_record_id=identifier,
            source_url="https://arxiv.org/abs/" + identifier,
            title=text(record, ATOM + "title"),
            authors=tuple(text(a, ATOM + "name") for a in record.findall(ATOM + "author")),
            year=submitted.year,
            submitted_at=submitted,
            updated_at=datetime.fromisoformat(updated) if updated else None,
            arxiv_id=identifier,
            doi=doi(record, ARXIV + "doi"),
            primary_category=category.get("term") if category is not None else None,
        )


class ACLXml:
    def request(self, plan: AcquisitionPlan) -> AcquisitionRequest:
        return AcquisitionRequest(
            endpoint=(
                "https://raw.githubusercontent.com/acl-org/acl-anthology/"
                f"{plan.acl_commit}/data/xml/{plan.acl_volume}.xml"
            ),
            params={},
        )

    def records(
        self, body: str, *, xml_limit: int = 2_000_000
    ) -> tuple[list[ET.Element], int | None]:
        root = xml_root(body, preserve_comments=True, limit=xml_limit)
        if root.tag != "collection":
            raise ValueError("Malformed ACL Anthology collection envelope")
        records: list[ET.Element] = []
        for volume in root.findall("volume"):
            for paper in volume.findall("paper"):
                # Copy inherited bibliographic fields, without altering original XML evidence.
                record = xml_root(
                    ET.tostring(paper, encoding="unicode"), preserve_comments=True, limit=xml_limit
                )
                for field in ("year", "booktitle"):
                    inherited = volume.find("meta/" + field)
                    if record.find(field) is None and inherited is not None:
                        record.append(ET.fromstring(ET.tostring(inherited, encoding="unicode")))
                records.append(record)
        return records, len(records)

    def candidate(self, record: ET.Element) -> AcquiredCandidate:
        declared = [" ".join("".join(node.itertext()).split()) for node in record.findall("url")]
        for child in record:
            if cast(object, child.tag) is ET.Comment:
                value = (child.text or "").strip()
                if value.startswith("https://aclanthology.org/"):
                    declared.append(value)
        identifiers = {self.identifier(value) for value in declared}
        if len(identifiers) > 1:
            raise ValueError("Conflicting explicit ACL identifiers")
        identifier = next(iter(identifiers), "")
        if not identifier:
            raise ValueError("Missing explicit ACL identifier; do not infer record IDs")
        return AcquiredCandidate(
            source_record_id=identifier,
            source_url="https://aclanthology.org/" + identifier + "/",
            title=text(record, "title"),
            year=int(text(record, "year")),
            authors=tuple(
                " ".join(filter(None, (text(a, "first"), text(a, "last"))))
                for a in record.findall("author")
            ),
            doi=doi(record, "doi"),
            venue=text(record, "booktitle") or None,
            volume=text(record, "volume") or None,
            issue=text(record, "issue") or None,
        )

    @staticmethod
    def identifier(value: str) -> str:
        identifier = value
        if identifier.startswith("https://aclanthology.org/"):
            parsed = urlsplit(identifier)
            if parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError("Unsafe ACL record URL")
            identifier = parsed.path.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]+", identifier):
            raise ValueError("Missing explicit ACL identifier; do not infer record IDs")
        return identifier


def source(plan: AcquisitionPlan) -> DiscoverySource:
    return ArxivAtom() if plan.source == "arxiv_atom" else ACLXml()
