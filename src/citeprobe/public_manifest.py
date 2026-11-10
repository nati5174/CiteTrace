"""Strict contracts for sanitized historical search provenance, never raw captures."""

import re
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.models import Model

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RecordedTime = AwareDatetime | Literal["not_recorded"]


class ArtifactReference(Model):
    artifact_id: Annotated[str, Field(pattern=r"^urn:citeprobe:[a-z0-9:-]+$")]
    sha256: Digest


class HistoricalSearch(Model):
    search_id: str
    source_paper_id: str
    provider: Literal["openalex", "crossref"]
    method: Literal["GET"]
    endpoint: str
    parameters: dict[str, str]
    authentication_mode: Literal["anonymous", "api_key_query_parameter"]
    request_started_at: RecordedTime
    response_capture_finished_at: RecordedTime
    response_headers_received_at: Literal["not_recorded"] = "not_recorded"
    response_server_date_header: str
    http_status: Literal[200]
    outcome: Literal["FOUND", "NOT_FOUND"]
    retrieval_limit: Literal[5]
    candidate_ranks: tuple[int, ...] = Field(max_length=5)
    lookup_engine_version: Literal["1"]
    parsing_warning_count: Literal[0]
    sources: tuple[ArtifactReference, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def check_request(self) -> Self:
        expected = {
            "openalex": ("https://api.openalex.org/works", "search", "per_page"),
            "crossref": ("https://api.crossref.org/works", "query.bibliographic", "rows"),
        }
        endpoint, query, limit = expected[self.provider]
        if self.endpoint != endpoint or set(self.parameters) != {query, limit}:
            raise ValueError("Unexpected endpoint or non-public request parameter")
        if self.parameters[limit] != "5" or not self.parameters[query].strip():
            raise ValueError("Invalid recorded query or retrieval limit")
        if self.provider == "crossref" and self.authentication_mode != "anonymous":
            raise ValueError("Unexpected Crossref access mode")
        ranks = self.candidate_ranks
        if tuple(sorted(set(ranks))) != ranks or any(r < 1 or r > 5 for r in ranks):
            raise ValueError("Invalid provider ranks")
        if (self.outcome == "FOUND") != bool(ranks):
            raise ValueError("Outcome and candidate inventory disagree")
        if not re.fullmatch(r"\d{4}\.\d{4,5}", self.source_paper_id):
            raise ValueError("Unexpected source identity")
        start, finish = self.request_started_at, self.response_capture_finished_at
        if start != "not_recorded" and finish != "not_recorded" and finish < start:
            raise ValueError("Capture finish precedes request start")
        return self


class ExperimentManifest(Model):
    schema_version: Literal["1.0"] = "1.0"
    study_kind: Literal["exploratory_citation_retrieval_pilot"]
    dataset_version: str
    evaluation_id: Digest
    dataset_sha256: Digest
    evaluation_sha256: Digest
    public_data_sha256_lf: Digest
    evaluation_code_fingerprint: Digest
    historical_execution_revision: Literal["not_recorded"] = "not_recorded"
    inspected_adapter_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    inspected_adapter_sha256: Digest
    manifest_builder_version: Literal["1"] = "1"
    manifest_builder_sha256: Digest
    source_paper_ids: tuple[str, ...] = Field(min_length=8, max_length=8)
    searches: tuple[HistoricalSearch, ...] = Field(min_length=16, max_length=16)
    excluded_operational_attempts: Literal[2]
    excluded_operational_status: Literal[429]
    pagination: Literal[False]
    retries_per_evaluated_search: Literal[0]
    provider_ranking_algorithm: Literal["not_recorded"] = "not_recorded"
    raw_response_availability: Literal["not_public"] = "not_public"
    request_headers: Literal["not_recorded"] = "not_recorded"
    extraction_rules: tuple[str, ...]
    normalization_rules: tuple[str, ...]
    provenance_limits: tuple[str, ...]

    @model_validator(mode="after")
    def check_inventory(self) -> Self:
        pairs = {(r.source_paper_id, r.provider) for r in self.searches}
        expected = {
            (p, provider) for p in self.source_paper_ids for provider in ("openalex", "crossref")
        }
        if len(set(self.source_paper_ids)) != 8 or pairs != expected or len(pairs) != 16:
            raise ValueError("Expected eight source papers with two searches each")
        if len({r.search_id for r in self.searches}) != 16:
            raise ValueError("Duplicate search identity")
        if sum(len(r.candidate_ranks) for r in self.searches) != 41:
            raise ValueError("Expected 41 recorded candidate entries")
        modes = [r.authentication_mode for r in self.searches if r.provider == "openalex"]
        if modes.count("anonymous") != 1 or modes.count("api_key_query_parameter") != 7:
            raise ValueError("Recorded OpenAlex access inventory changed")
        return self
