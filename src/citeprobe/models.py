"""Explicit schemas for canonical data and independent mutation payloads."""

from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MutationType = Literal[
    "title_typo", "author_initials", "year_shift", "title_word_deletion", "digit_transposition"
]
MutableField = Literal["title", "authors", "year", "volume", "issue"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Author(Model):
    given: Text | None = None
    family: Text


class Provenance(Model):
    source_url: HttpUrl
    record_identifier: Text
    verification_status: Literal["verified", "pending"]
    verified_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def check_timestamp(self) -> Self:
        if (self.verification_status == "verified") != (self.verified_at is not None):
            raise ValueError("Only verified provenance must have a verification timestamp")
        return self


class CitationValues(Model):
    title: Text
    authors: tuple[Author, ...] = Field(min_length=1)
    year: int = Field(strict=True, ge=1, le=9999)
    doi: Annotated[str, StringConstraints(pattern=r"^10\.\d{4,9}/\S+$")] | None = None
    arxiv_id: (
        Annotated[
            str,
            StringConstraints(
                pattern=r"^(?:\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v[1-9]\d*)?$"
            ),
        ]
        | None
    ) = None
    volume: Text | None = None
    issue: Text | None = None

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if self.doi is None and self.arxiv_id is None:
            raise ValueError("At least one DOI or arXiv ID is required")
        return self


class Citation(CitationValues):
    citation_id: Text
    provenance: Provenance


class Dataset(Model):
    schema_version: Literal["1.0"] = "1.0"
    dataset_version: Text
    citations: tuple[Citation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [citation.citation_id for citation in self.citations]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate citation IDs")
        return self


class Mutation(Model):
    mutation_id: Text
    mutation_type: MutationType
    original_citation_id: Text
    mutated_fields: tuple[MutableField, ...] = Field(min_length=1)
    parameters: dict[str, int | str]
    seed: int = Field(strict=True)
    algorithm_version: Literal["1"] = "1"
    citation: CitationValues


class SkippedMutation(Model):
    original_citation_id: Text
    mutation_type: MutationType
    reason: Text


class MutationBatch(Model):
    schema_version: Literal["1.0"] = "1.0"
    dataset_version: Text
    seed: int = Field(strict=True)
    algorithm_version: Literal["1"] = "1"
    generated_at: AwareDatetime
    mutations: tuple[Mutation, ...]
    skipped: tuple[SkippedMutation, ...]
