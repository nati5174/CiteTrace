"""Offline research ledgers; deliberately separate from historical dataset contracts."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.analysis_models import Experiment, PreprintDate
from citeprobe.evaluation_models import DataLabel, IdentityIdentifier
from citeprobe.models import Model, Provenance, Text

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SourceEvidence(Model):
    evidence_id: Text
    provenance: Provenance
    origin: DataLabel
    authority: Literal["original_repository", "original_publisher", "registry", "other"]
    retrieved_at: AwareDatetime
    evidence_sha256: Digest
    excerpt: Text
    supports: tuple[Text, ...] = Field(min_length=1)


class Review(Model):
    reviewer_id: Text
    decision: Literal["approve", "reject", "pending"]
    reviewed_at: AwareDatetime


class IdentityClaim(Model):
    claim_id: Text
    citation_id: Text
    identifiers: tuple[IdentityIdentifier, ...] = Field(min_length=1)
    basis: Literal["source_declared", "new_mapping"]
    relation: Literal["same_work", "different_work", "undetermined"]
    expression: Literal["original", "same_language_version", "translation", "derivative", "unclear"]
    evidence_ids: tuple[Text, ...] = Field(min_length=1)
    rationale: Text
    reviews: tuple[Review, ...] = ()
    conflict: bool = False


class PaperRecord(Model):
    citation_id: Text
    evidence_ids: tuple[Text, ...] = Field(min_length=1)
    # Explicit field-level assertions; source evidence must support each assertion.
    verified_fields: tuple[Text, ...]
    decision: Literal["include", "exclude"]
    reason: Text
    exclusion_kind: Literal["eligibility", "verified_duplicate"] | None = None
    public_date: PreprintDate | None = None
    public_date_basis: Literal["public_announcement", "submission", "revision", "unknown"] = (
        "unknown"
    )
    cohort: str | None = None
    identifier_stratum: Literal["doi_only", "arxiv_only", "dual"] | None = None


class DuplicateRecord(Model):
    duplicate_id: Text
    category: Literal["VERIFIED_DUPLICATE", "POSSIBLE_DUPLICATE"]
    citation_ids: tuple[Text, ...] = Field(min_length=2)
    claim_ids: tuple[Text, ...] = ()
    representative_id: str | None = None
    reason: Text


class ResearchManifest(Model):
    schema_version: Literal["1.0"] = "1.0"
    manifest_version: Text
    manifest_fingerprint: Digest
    dataset_version: Text
    dataset_fingerprint: Digest
    experiment: Experiment
    origin: DataLabel
    policy_version: Literal["1.1"] = "1.1"
    protocol_sha256: Digest
    frame_source: Provenance
    frame_evidence_id: Text
    frame_snapshot_sha256: Digest
    frame_definition: Text
    sampling_method: Literal["sha256-v1"] = "sha256-v1"
    seed: int = Field(strict=True, default=0)
    target_per_group: dict[str, Annotated[int, Field(strict=True, ge=0)]]
    reference_date: date | None = None
    planned_started_at: AwareDatetime
    planned_finished_at: AwareDatetime
    stage: Literal["pre_collection", "post_collection"] = "pre_collection"
    actual_started_at: AwareDatetime | None = None
    actual_finished_at: AwareDatetime | None = None
    observation_bundle_ids: tuple[Digest, ...] = ()
    sources: tuple[SourceEvidence, ...]
    papers: tuple[PaperRecord, ...]
    identity_claims: tuple[IdentityClaim, ...] = ()
    duplicates: tuple[DuplicateRecord, ...] = ()

    @model_validator(mode="after")
    def windows(self) -> Self:
        if self.planned_started_at > self.planned_finished_at:
            raise ValueError("Planned window is reversed")
        if self.stage == "pre_collection":
            if self.actual_started_at or self.actual_finished_at or self.observation_bundle_ids:
                raise ValueError("Pre-collection plans cannot contain actual observations")
        elif (
            not self.actual_started_at
            or not self.actual_finished_at
            or not self.observation_bundle_ids
        ):
            raise ValueError("Post-collection times require original observation bundles")
        elif self.actual_started_at > self.actual_finished_at:
            raise ValueError("Actual window is reversed")
        if not self.target_per_group or any(
            type(n) is not int or n < 0 for n in self.target_per_group.values()
        ):
            raise ValueError("Sampling targets must be nonnegative integers")
        return self


class SampleRow(Model):
    citation_id: Text
    group: str | None
    disposition: Literal["selected", "reserve", "excluded"]
    reason: Text
    sampling_key: Digest | None
    ordinal: int | None = Field(default=None, ge=1)


class SamplingPlan(Model):
    schema_version: Literal["1.0"] = "1.0"
    plan_fingerprint: Digest
    manifest_fingerprint: Digest
    dataset_fingerprint: Digest
    seed: int = Field(strict=True)
    origin: DataLabel
    rows: tuple[SampleRow, ...]
    shortfalls: dict[str, int]
    warnings: tuple[str, ...]
