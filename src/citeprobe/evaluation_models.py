"""Versioned offline evaluation contracts; no changes to lookup/ground-truth schemas."""

from typing import Literal

from pydantic import Field

from citeprobe.models import Model, MutationType, Provenance, Text
from citeprobe.resolution_models import Candidate, Outcome, ProviderName, Strategy

DataLabel = Literal["observed", "simulated", "unknown"]
Judgment = Literal["CORRECT", "INCORRECT", "UNDETERMINED"]
RetrievalState = Literal["HIT", "MISS", "UNDETERMINED", "EXCLUDED"]
Dimension = Literal[
    "provider", "strategy", "source_kind", "mutation_type", "original_citation_id", "cohort"
]


class IdentityIdentifier(Model):
    namespace: Literal["doi", "arxiv", "openalex", "crossref"]
    value: Text


class IdentityMapping(Model):
    citation_id: Text
    relation: Literal["same_work", "different_work"]
    identifiers: tuple[IdentityIdentifier, ...] = Field(min_length=1)
    provenance: Provenance


class IdentityMappings(Model):
    schema_version: Literal["1.0"] = "1.0"
    dataset_version: Text
    mappings: tuple[IdentityMapping, ...] = ()


class EvaluationConfig(Model):
    schema_version: Literal["1.0"] = "1.0"
    default_data_label: DataLabel = "unknown"
    input_labels: dict[str, DataLabel] = Field(default_factory=dict)
    cohorts: dict[str, Text] = Field(default_factory=dict)
    # Provider, strategy and data label are always separate; these add breakouts.
    groupings: tuple[tuple[Dimension, ...], ...] = (
        ("source_kind", "mutation_type"),
        ("original_citation_id",),
        ("cohort",),
    )


class CandidateJudgment(Model):
    candidate: Candidate
    judgment: Judgment
    reason: Text
    normalized_identifiers: tuple[str, ...]
    matching_evidence: tuple[str, ...] = ()
    distinct_evidence: tuple[str, ...] = ()


class EvaluatedLookup(Model):
    lookup_id: Text
    input_bundle_id: Text
    data_label: DataLabel
    source_id: Text
    original_citation_id: Text
    source_kind: Literal["canonical", "mutation"]
    mutation_type: MutationType | None
    cohort: str | None
    provider: ProviderName
    strategy: Strategy
    outcome: Outcome
    retrieval_eligible: bool
    candidates: tuple[CandidateJudgment, ...]
    recall_at_1: RetrievalState
    recall_at_5: RetrievalState
    rank_one_judgment: Judgment | None
    parsing_warnings: tuple[str, ...]
    unavailable_provider_ranks: tuple[int, ...]


class Metric(Model):
    numerator: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None
    lower_bound: float | None
    upper_bound: float | None
    undefined_reason: Literal["zero_denominator", "identity_uncertainty"] | None


class MetricGroup(Model):
    dimensions: dict[str, str | None]
    # Only explicitly observed groups may supply future empirical reporting.
    empirical_data_eligible: bool
    lookup_count: int
    retrieval_lookup_count: int
    original_citation_count: int
    retrieval_original_citation_count: int
    metrics: dict[str, Metric]


class EvaluationInput(Model):
    bundle_id: Text
    file_sha256: str | None = None
    data_label: DataLabel
    engine_version: Text
    input_fingerprint: Text
    config_fingerprint: Text


class EvaluationOutput(Model):
    schema_version: Literal["1.0"] = "1.0"
    evaluator_version: Literal["1"] = "1"
    package_version: Text
    code_fingerprint: Text
    evaluation_id: Text
    dataset_version: Text
    dataset_fingerprint: Text
    identity_mappings: IdentityMappings
    identity_mappings_fingerprint: Text
    config: EvaluationConfig
    metric_definitions: dict[str, str]
    inputs: tuple[EvaluationInput, ...]
    lookups: tuple[EvaluatedLookup, ...]
    groups: tuple[MetricGroup, ...]
