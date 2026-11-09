"""Versioned acquisition evidence and review contracts, independent of retrieval."""

from datetime import date
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.analysis_models import Experiment
from citeprobe.evaluation_models import DataLabel
from citeprobe.models import Model, Text
from citeprobe.research_models import Digest


class AcquisitionPlan(Model):
    schema_version: Literal["1.0"] = "1.0"
    source: Literal["arxiv_atom", "acl_xml"]
    experiment: Experiment
    reference_date: date | None = None
    planned_started_at: AwareDatetime
    planned_finished_at: AwareDatetime
    max_records: int = Field(default=5, strict=True, ge=1, le=10)
    acl_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    acl_volume: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.-]+$")
    seed: int = Field(default=0, strict=True)
    maximum_requests: Literal[1] = 1

    @model_validator(mode="after")
    def configuration(self) -> Self:
        if self.planned_started_at > self.planned_finished_at:
            raise ValueError("Planned acquisition window is reversed")
        if self.experiment == "recent-preprints" and (
            self.reference_date is None or self.source != "arxiv_atom"
        ):
            raise ValueError("Recent-preprint discovery requires arXiv and a reference date")
        if self.source == "acl_xml":
            if not self.acl_commit or not self.acl_volume:
                raise ValueError("ACL XML requires a pinned repository commit and volume")
        elif self.acl_commit or self.acl_volume:
            raise ValueError("ACL settings cannot be used for arXiv")
        return self


class AcquisitionRequest(Model):
    endpoint: Text
    params: dict[str, str]


class AcquiredCandidate(Model):
    source_record_id: Text
    source_url: Text
    title: Text
    authors: tuple[Text, ...] = Field(min_length=1)
    year: int = Field(strict=True, ge=1, le=9999)
    doi: str | None = None
    arxiv_id: str | None = None
    submitted_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    primary_category: str | None = None
    venue: str | None = None
    volume: str | None = None
    issue: str | None = None
    # Discovery records do not establish a verified first-public date.
    first_public_date: None = None
    verification_status: Literal["pending"] = "pending"


class AcquisitionResponse(Model):
    schema_version: Literal["1.0"] = "1.0"
    origin: DataLabel
    plan: AcquisitionPlan
    request: AcquisitionRequest
    started_at: AwareDatetime
    finished_at: AwareDatetime
    http_status: int | None = Field(default=None, ge=100, le=599)
    exception_type: str | None = None
    response_body_sha256: Digest | None = None
    metadata_xml: str | None = None
    metadata_sha256: Digest | None = None
    retry_after: str | None = None
    latency_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    authorization_reference: str | None = None

    @model_validator(mode="after")
    def chronology(self) -> Self:
        if self.started_at > self.finished_at:
            raise ValueError("Actual acquisition window is reversed")
        if (self.metadata_xml is None) != (self.metadata_sha256 is None):
            raise ValueError("Metadata projection requires its hash")
        if self.metadata_xml is not None and (
            self.http_status != 200 or self.exception_type or not self.response_body_sha256
        ):
            raise ValueError("Metadata evidence requires a successful hashed source response")
        return self


class AcquisitionReviewItem(Model):
    item_id: Digest
    ordinal: int = Field(ge=1)
    candidate: AcquiredCandidate | None
    issues: tuple[str, ...]


class AcquisitionAudit(Model):
    schema_version: Literal["1.0"] = "1.0"
    audit_id: Digest
    response: AcquisitionResponse
    outcome: Literal["READY_FOR_REVIEW", "PARTIAL", "EMPTY", "API_ERROR", "TIMEOUT", "RATE_LIMITED"]
    items: tuple[AcquisitionReviewItem, ...]
    warnings: tuple[str, ...]
    source_total: int | None = Field(default=None, ge=0)
    frame_complete: Literal[False] = False


class CuratorDecision(Model):
    item_id: Digest
    disposition: Literal["include", "exclude", "pending"]
    citation_id: str | None = None
    reason: Text
    reviewer_id: Text
    reviewed_at: AwareDatetime
