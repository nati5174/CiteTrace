"""Versioned resolution contracts, separate from verified ground truth."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from citeprobe.models import Author, Model, Text

ProviderName = Literal["openalex", "crossref"]
Strategy = Literal["metadata", "identifier"]
Outcome = Literal["FOUND", "NOT_FOUND", "TIMEOUT", "RATE_LIMITED", "API_ERROR", "UNKNOWN"]


class SearchMetadata(Model):
    """The entire metadata visible to an adapter. No evaluation identifiers."""

    title: Text
    authors: tuple[Author, ...]
    year: int = Field(strict=True, ge=1, le=9999)
    volume: Text | None = None
    issue: Text | None = None


class LookupTask(Model):
    source_id: Text
    source_kind: Literal["canonical", "mutation"]
    original_citation_id: Text
    metadata: SearchMetadata
    strategy: Strategy = "metadata"
    # These may be populated only for an explicit canonical identifier strategy.
    identifier: Text | None = None

    @model_validator(mode="after")
    def isolate_identifiers(self) -> Self:
        if self.source_kind == "mutation" and (self.identifier or self.strategy != "metadata"):
            raise ValueError("Mutation tasks must be metadata-only")
        if (self.strategy == "identifier") != (self.identifier is not None):
            raise ValueError("Identifier hints require an explicit identifier strategy")
        return self


class Candidate(Model):
    provider_record_id: Text
    title: Text | None = None
    authors: tuple[str, ...] = ()
    year: int | None = Field(default=None, strict=True, ge=1, le=9999)
    doi: Text | None = None
    arxiv_id: Text | None = None
    provider_rank: int = Field(ge=1)
    ranking: dict[str, JsonValue] = Field(default_factory=dict)


class RequestMetadata(Model):
    method: Literal["GET"] = "GET"
    endpoint: Text
    params: dict[str, str]
    submitted_metadata: SearchMetadata | None
    submitted_identifier: str | None = None


class Attempt(Model):
    request_sent: bool = True
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: float = Field(ge=0)
    response_status: int | None
    outcome: Outcome
    retry_after: str | None = None
    retry_delay_seconds: float | None = Field(default=None, ge=0)
    response: JsonValue = None
    response_body_sha256: str | None = None
    diagnostic: str | None = None


class LookupResult(Model):
    lookup_id: Text
    source_id: Text
    source_kind: Literal["canonical", "mutation"]
    original_citation_id: Text
    provider: ProviderName
    strategy: Strategy
    request: RequestMetadata
    outcome: Outcome
    candidates: tuple[Candidate, ...] = Field(max_length=5)
    parsing_warnings: tuple[str, ...] = ()
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: float = Field(ge=0)
    retry_count: int = Field(ge=0)
    response_status: int | None
    attempts: tuple[Attempt, ...]


class ResolverConfig(Model):
    concurrency: int = Field(default=4, strict=True, ge=1, le=100)
    provider_concurrency: int = Field(default=1, strict=True, ge=1, le=100)
    openalex_rps: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)
    crossref_rps: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)
    timeout_seconds: float = Field(default=20, gt=0, allow_inf_nan=False)
    max_attempts: int = Field(default=3, strict=True, ge=1, le=10)
    backoff_seconds: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    max_retry_wait: float = Field(default=30, ge=0, le=60, allow_inf_nan=False)
    jitter_seed: int = Field(default=0, strict=True)


class LookupBundle(Model):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: Literal["1"] = "1"
    dataset_version: Text
    dataset_fingerprint: Text
    input_fingerprint: Text
    config_fingerprint: Text
    config: ResolverConfig
    providers: tuple[ProviderName, ...]
    selected_source_ids: tuple[Text, ...]
    generated_at: AwareDatetime
    results: tuple[LookupResult, ...]
