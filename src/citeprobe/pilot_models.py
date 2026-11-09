"""Pilot-specific contracts; submission age never overloads first-public dates."""

from datetime import date
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.acquisition_models import AcquiredCandidate
from citeprobe.evaluation_models import DataLabel
from citeprobe.evidence_models import EvidenceRequest
from citeprobe.models import CitationValues, Model, Text
from citeprobe.research_models import Digest, DuplicateRecord, IdentityClaim, SourceEvidence


class ACLRevision(Model):
    schema_version: Literal["1.0"] = "1.0"
    repository: Literal["https://github.com/acl-org/acl-anthology"] = (
        "https://github.com/acl-org/acl-anthology"
    )
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    origin: DataLabel
    curator_id: Text
    reviewed_at: AwareDatetime
    proof_kind: Literal["local_git", "upstream_http"]
    proof_location: Text
    proof_fingerprint: Digest
    revision_fingerprint: Digest


class PilotRequest(Model):
    key: Text
    request: EvidenceRequest
    group: Text
    offset: Literal[0, 100] | None = None
    collection: str | None = None
    volume_filter: str | None = None
    source_day: date | None = None
    source_ids: tuple[str, ...] = ()
    conditional: bool = False


class PilotPlan(Model):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: Digest
    stage: Literal[
        "a_enumeration", "b_enumeration", "id_batch", "v1_verification", "acl_resolution"
    ]
    experiment: Literal["submission-age-pilot", "mutation-robustness-pilot"]
    date_basis: Literal["first_arxiv_submission", "canonical_bibliographic_year"]
    origin: DataLabel
    reference_date: date | None = None
    planned_started_at: AwareDatetime
    planned_finished_at: AwareDatetime
    seed: Literal[0] = 0
    revision: ACLRevision | None = None
    parent_frame_id: Digest | None = None
    source_ids: tuple[str, ...] = ()
    maximum_requests: int = Field(strict=True, ge=1, le=24)
    requests: tuple[PilotRequest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.planned_started_at > self.planned_finished_at:
            raise ValueError("Reversed pilot window")
        if self.maximum_requests != len(self.requests):
            raise ValueError("Pilot request budget must equal its exact conditional inventory")
        if len({r.key for r in self.requests}) != len(self.requests):
            raise ValueError("Duplicate request keys")
        expected = (
            "first_arxiv_submission"
            if self.experiment == "submission-age-pilot"
            else "canonical_bibliographic_year"
        )
        if self.date_basis != expected:
            raise ValueError("Pilot date basis cannot be confused with announcement age")
        if self.experiment == "submission-age-pilot" and self.reference_date is None:
            raise ValueError("A-S1 requires an explicit fixed reference date")
        return self


class Attempt(Model):
    key: Text
    disposition: Literal["captured", "not_required"]
    evidence_directory: str | None


class PilotRun(Model):
    schema_version: Literal["1.0"] = "1.0"
    run_id: Digest
    plan: PilotPlan
    attempts: tuple[Attempt, ...]
    stopped_reason: str | None = None


class PilotItem(Model):
    source_id: Text
    group: Text
    candidate: AcquiredCandidate
    run_request_key: Text
    possible_duplicates: tuple[str, ...] = ()


class PilotFrame(Model):
    schema_version: Literal["1.0"] = "1.0"
    frame_id: Digest
    run_id: Digest
    plan_id: Digest
    experiment: Literal["submission-age-pilot", "mutation-robustness-pilot"]
    origin: DataLabel
    reference_date: date | None
    complete: Literal[True] = True
    items: tuple[PilotItem, ...]
    panel_ids: tuple[str, ...]
    exclusions: dict[str, str]
    panel_shortfalls: dict[str, int]


class PilotDecision(Model):
    source_id: Text
    disposition: Literal["include", "exclude", "pending"]
    reason: Text
    reviewer_id: Text
    reviewed_at: AwareDatetime
    canonical: CitationValues | None = None
    language: Literal["en", "other", "unknown"] = "unknown"
    metadata_verified: bool = False
    identity_verified: bool = False
    v1_evidence_directory: str | None = None
    v1_submitted_at: AwareDatetime | None = None
    v1_verified: bool = False
    exclusion_kind: Literal["eligibility", "unverified_evidence", "verified_duplicate"] | None = (
        None
    )


class PilotReview(Model):
    schema_version: Literal["1.0"] = "1.0"
    frame_id: Digest
    origin: DataLabel
    identifier_inspection_protocol: Text | None = None
    decisions: tuple[PilotDecision, ...]
    sources: tuple[SourceEvidence, ...] = ()
    claims: tuple[IdentityClaim, ...] = ()
    duplicates: tuple[DuplicateRecord, ...] = ()
