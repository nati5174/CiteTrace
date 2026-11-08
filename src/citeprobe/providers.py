"""Provider request construction and parsing. No access to ground-truth records."""

import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from pydantic import JsonValue, ValidationError

from citeprobe.resolution_models import Candidate, ProviderName, SearchMetadata


@dataclass(frozen=True)
class ProviderRequest:
    endpoint: str
    params: dict[str, str]


class Provider(Protocol):
    name: ProviderName

    def request(self, metadata: SearchMetadata, identifier: str | None) -> ProviderRequest: ...
    def parse(self, response: Any) -> tuple[tuple[Candidate, ...], tuple[str, ...]]: ...


def bibliographic_text(metadata: SearchMetadata) -> str:
    authors = " ".join(" ".join(filter(None, (a.given, a.family))) for a in metadata.authors)
    return " ".join(
        filter(
            None,
            (
                metadata.title,
                authors,
                str(metadata.year),
                metadata.volume,
                metadata.issue,
            ),
        )
    )


def arxiv_from_urls(urls: list[Any]) -> str | None:
    for url in urls:
        if isinstance(url, str):
            match = re.search(
                r"(?:arxiv\.org/(?:abs|pdf)/|10\.48550/arxiv\.)"
                r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z]{2})?/\d{7}(?:v\d+)?)",
                url,
                re.IGNORECASE,
            )
            if match:
                return match[1]
    return None


def doi_value(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid DOI")
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)


class OpenAlex:
    name: ProviderName = "openalex"

    def request(self, metadata: SearchMetadata, identifier: str | None) -> ProviderRequest:
        params = {"per_page": "5"}
        if identifier and not identifier.startswith("arXiv:"):
            params["filter"] = f"doi:https://doi.org/{identifier}"
        else:
            params["search"] = identifier or bibliographic_text(metadata)
        return ProviderRequest("https://api.openalex.org/works", params)

    def parse(self, response: Any) -> tuple[tuple[Candidate, ...], tuple[str, ...]]:
        if not isinstance(response, dict) or not isinstance(response.get("results"), list):
            raise ValueError("Malformed OpenAlex results envelope")
        candidates: list[Candidate] = []
        warnings: list[str] = []
        for rank, record in enumerate(response["results"][:5], 1):
            try:
                if not isinstance(record, dict):
                    raise ValueError("Expected candidate object")
                authors = tuple(a["author"]["display_name"] for a in record.get("authorships", []))
                urls = [record.get("doi")]
                for location in record.get("locations", []):
                    urls.extend([location.get("landing_page_url"), location.get("pdf_url")])
                for name in ("primary_location", "best_oa_location"):
                    location = record.get(name)
                    if location:
                        urls.extend([location.get("landing_page_url"), location.get("pdf_url")])
                candidates.append(
                    Candidate(
                        provider_record_id=record["id"],
                        title=record.get("title"),
                        authors=authors,
                        year=record.get("publication_year"),
                        doi=doi_value(record.get("doi")),
                        arxiv_id=arxiv_from_urls(urls),
                        provider_rank=rank,
                        ranking={"relevance_score": record.get("relevance_score")},
                    )
                )
            except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
                warnings.append(f"Candidate at provider rank {rank} could not be parsed")
        return tuple(candidates), tuple(warnings)


class Crossref:
    name: ProviderName = "crossref"

    def request(self, metadata: SearchMetadata, identifier: str | None) -> ProviderRequest:
        # Bibliographic identifier search preserves provider ranking and avoids endpoint escaping.
        query = identifier or bibliographic_text(metadata)
        return ProviderRequest(
            "https://api.crossref.org/works",
            {
                "query.bibliographic": query,
                "rows": "5",
            },
        )

    def parse(self, response: Any) -> tuple[tuple[Candidate, ...], tuple[str, ...]]:
        if (
            not isinstance(response, dict)
            or response.get("status") != "ok"
            or not isinstance(response.get("message"), dict)
            or not isinstance(response["message"].get("items"), list)
        ):
            raise ValueError("Malformed Crossref results envelope")
        candidates: list[Candidate] = []
        warnings: list[str] = []
        for rank, record in enumerate(response["message"]["items"][:5], 1):
            try:
                if not isinstance(record, dict):
                    raise ValueError("Expected candidate object")
                authors = tuple(
                    a.get("name") or " ".join(filter(None, (a.get("given"), a.get("family"))))
                    for a in record.get("author", [])
                )
                title = record.get("title", [])
                if not isinstance(title, list):
                    raise ValueError("Invalid title")
                date = (
                    record.get("published")
                    or record.get("published-print")
                    or record.get("published-online")
                    or record.get("issued")
                )
                year = date["date-parts"][0][0] if date else None
                urls = [record.get("URL"), record.get("DOI")]
                urls.extend(link.get("URL") for link in record.get("link", []))
                candidates.append(
                    Candidate(
                        provider_record_id=record["DOI"],
                        title=title[0] if title else None,
                        authors=authors,
                        year=year,
                        doi=doi_value(record["DOI"]),
                        arxiv_id=arxiv_from_urls(urls),
                        provider_rank=rank,
                        ranking={"score": record.get("score")},
                    )
                )
            except (KeyError, IndexError, TypeError, ValueError, AttributeError, ValidationError):
                warnings.append(f"Candidate at provider rank {rank} could not be parsed")
        return tuple(candidates), tuple(warnings)


# Preserve the response fields used by parsing/ranking, without abstracts, affiliations,
# email addresses, request headers, tracking URLs, or arbitrary provider error text.
EVIDENCE_KEYS = frozenset(
    {
        "results",
        "message",
        "items",
        "status",
        "meta",
        "count",
        "total-results",
        "id",
        "title",
        "publication_year",
        "doi",
        "DOI",
        "authorships",
        "author",
        "display_name",
        "given",
        "family",
        "name",
        "published",
        "published-print",
        "published-online",
        "issued",
        "date-parts",
        "score",
        "relevance_score",
        "locations",
        "primary_location",
        "best_oa_location",
        "landing_page_url",
        "pdf_url",
        "link",
        "URL",
    }
)


def response_evidence(value: Any, secrets: tuple[str, ...] = ()) -> JsonValue:
    """Allowlisted response projection; never persist authentication values."""
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if key not in EVIDENCE_KEYS:
                continue
            if key in {"landing_page_url", "pdf_url", "URL"}:
                # Only retain identifier-bearing public links needed for arXiv parsing.
                if not isinstance(item, str):
                    continue
                try:
                    url = urlsplit(item)
                    if url.hostname not in {"arxiv.org", "www.arxiv.org", "doi.org"}:
                        continue
                    item = urlunsplit((url.scheme, url.hostname, url.path, "", ""))
                except ValueError:
                    continue
            if key == "message" and not isinstance(item, dict):
                continue  # Provider error prose may echo credentials or contact details.
            result[key] = response_evidence(item, secrets)
        return result
    if isinstance(value, list):
        return [response_evidence(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None
