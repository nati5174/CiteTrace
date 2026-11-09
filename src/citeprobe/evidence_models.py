"""Version 2 evidence is separate from immutable projection-only version 1 artifacts."""

import re
from datetime import UTC
from typing import Literal, Self
from urllib.parse import parse_qsl, urlsplit

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.evaluation_models import DataLabel
from citeprobe.models import Model, Text
from citeprobe.research_models import Digest

SourceKind = Literal[
    "arxiv_api_doc",
    "arxiv_rss_doc",
    "arxiv_atom",
    "acquisition_xml",
    "upstream_json",
    "arxiv_abstract",
]
SAFE_HEADERS = {
    "content-type",
    "content-encoding",
    "content-length",
    "date",
    "etag",
    "last-modified",
    "retry-after",
}


def public_url(value: str) -> str:
    url = urlsplit(value)
    forbidden = {
        "apikey",
        "key",
        "token",
        "accesstoken",
        "mailto",
        "email",
        "secret",
        "password",
        "authorization",
        "clientsecret",
        "signature",
        "session",
    }
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.fragment
        or any(re.sub(r"[^a-z0-9]", "", k.casefold()) in forbidden for k, _ in parse_qsl(url.query))
    ):
        raise ValueError("Evidence URLs must be public HTTPS URLs without credential parameters")
    return value


class EvidenceRequest(Model):
    method: Literal["GET"] = "GET"
    url: Text
    source_kind: SourceKind

    @model_validator(mode="after")
    def safe(self) -> Self:
        public_url(self.url)
        return self


class EvidenceBudget(Model):
    schema_version: Literal["2.0"] = "2.0"
    budget_id: Text
    authorization_reference: Text
    origin: DataLabel
    maximum_requests: int = Field(strict=True, ge=1, le=20)
    requests: tuple[EvidenceRequest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if len(self.requests) > self.maximum_requests or len(set(self.requests)) != len(
            self.requests
        ):
            raise ValueError("Invalid or duplicate authorized request inventory")
        return self


class RawEvidence(Model):
    schema_version: Literal["2.0"] = "2.0"
    record_id: Digest
    budget_fingerprint: Digest
    request_id: Digest
    request_ordinal: int = Field(strict=True, ge=1)
    request: EvidenceRequest
    request_headers: dict[str, str] = Field(
        default_factory=lambda: {
            "user-agent": "CiteProbe/0.1 evidence-v2",
            "accept-encoding": "identity",
        }
    )
    origin: DataLabel
    started_at: AwareDatetime
    headers_received_at: AwareDatetime | None = None
    finished_at: AwareDatetime
    http_status: int | None = Field(default=None, ge=100, le=599)
    final_url: str | None = None
    response_headers: dict[str, str]
    content_type: str | None
    content_encoding: str | None
    character_encoding: str | None
    raw_body_file: Literal["body.bin"] = "body.bin"
    body_representation: Literal["httpx_iter_raw_content_encoded"] = (
        "httpx_iter_raw_content_encoded"
    )
    raw_body_sha256: Digest
    raw_body_size: int = Field(strict=True, ge=0)
    body_complete: bool
    exception_type: str | None = None
    extraction_version: Literal["2"] = "2"

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.request_headers != {
            "user-agent": "CiteProbe/0.1 evidence-v2",
            "accept-encoding": "identity",
        }:
            raise ValueError("Only fixed public evidence request headers may be recorded")
        if self.started_at > self.finished_at or (
            self.headers_received_at is not None
            and not self.started_at <= self.headers_received_at <= self.finished_at
        ):
            raise ValueError("Invalid response chronology")
        for timestamp in (self.started_at, self.headers_received_at, self.finished_at):
            if timestamp and timestamp.utcoffset() != UTC.utcoffset(None):
                raise ValueError("Evidence collection timestamps must be UTC")
        if self.final_url:
            public_url(self.final_url)
        if not set(self.response_headers) <= SAFE_HEADERS:
            raise ValueError("Sensitive or unsupported response headers")
        charset = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", self.content_type or "", re.I)
        if self.character_encoding != (charset[1] if charset else None):
            raise ValueError("Character encoding contradicts Content-Type")
        if self.http_status is None and (
            self.headers_received_at or self.final_url or self.body_complete
        ):
            raise ValueError("HTTP metadata without a usable response")
        if self.http_status is not None and (not self.headers_received_at or not self.final_url):
            raise ValueError("Response requires final URL and headers timestamp")
        return self


class Extraction(Model):
    schema_version: Literal["2.0"] = "2.0"
    extraction_version: Literal["2"] = "2"
    record_id: Digest
    source_url: Text
    raw_body_sha256: Digest
    status: Literal["EXTRACTED", "UNAVAILABLE"]
    # JSON payload contains verbatim statements/fields and source locators, never identity labels.
    payload: dict[str, object]
    warnings: tuple[str, ...]
