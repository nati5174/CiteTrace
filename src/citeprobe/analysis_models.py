"""Part 4 study assertions and deterministic reporting contracts."""

from datetime import UTC, date
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from citeprobe.evaluation_models import DataLabel, EvaluatedLookup, MetricGroup
from citeprobe.models import Model, Provenance, Text

Experiment = Literal["recent-preprints", "mutation-robustness"]
FigureFormat = Literal["svg", "png", "pdf"]
COVERAGE_LABEL: Literal["Verified retrieval coverage under the recorded search strategy"] = (
    "Verified retrieval coverage under the recorded search strategy"
)
SCOPE_NOTE = (
    "NOT_FOUND means no candidates were returned by the recorded search; it does not establish "
    "absence from a provider's database or that a citation is fabricated. Cross-sectional "
    "paper-age "
    "comparisons are not indexing latency. Provider indexing scopes differ."
)


class PreprintDate(Model):
    citation_id: Text
    publication_date: date
    date_kind: Literal["first_public_preprint", "revision"] = "first_public_preprint"
    precision: Literal["day", "timestamp"] = "day"
    published_at: AwareDatetime | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def consistent_precision(self) -> Self:
        if (self.precision == "timestamp") != (self.published_at is not None):
            raise ValueError(
                "Timestamp precision requires published_at; day precision must omit it"
            )
        if self.published_at and self.published_at.astimezone(UTC).date() != self.publication_date:
            raise ValueError("Publication date differs from its UTC timestamp")
        return self


class StudyManifest(Model):
    schema_version: Literal["1.0"] = "1.0"
    dataset_fingerprint: Text
    citation_ids: tuple[Text, ...] = Field(min_length=1)
    sampling_method: Text
    verification_method: Text
    collection_started_at: AwareDatetime
    collection_finished_at: AwareDatetime
    reference_date: date | None = None
    preprint_dates: tuple[PreprintDate, ...] = ()
    lookup_bundle_ids: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def inventories(self) -> Self:
        if self.collection_started_at > self.collection_finished_at:
            raise ValueError("Collection window is reversed")
        dates = [row.citation_id for row in self.preprint_dates]
        for values in (self.citation_ids, self.lookup_bundle_ids, dates):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate study manifest references")
        if set(dates) - set(self.citation_ids):
            raise ValueError("Publication date references a citation outside study inventory")
        return self


class AnalysisConfig(Model):
    schema_version: Literal["1.0"] = "1.0"
    experiment: Experiment
    max_collection_hours: float = Field(default=24, gt=0, allow_inf_nan=False)
    bootstrap: bool = False
    seed: int = Field(default=0, strict=True)
    bootstrap_replicates: int = Field(default=2000, strict=True, ge=100, le=10000)
    confidence_level: float = Field(default=0.95, ge=0.8, lt=1, allow_inf_nan=False)
    min_cluster_count: int = Field(default=30, strict=True, ge=30)
    figure_formats: tuple[FigureFormat, ...] = ("svg",)

    @model_validator(mode="after")
    def unique_formats(self) -> Self:
        if len(self.figure_formats) != len(set(self.figure_formats)):
            raise ValueError("Duplicate figure formats")
        return self


class StatisticalInterval(Model):
    lower: float | None = None
    upper: float | None = None
    confidence_level: float
    cluster_count: int
    replicates: int
    attempted_replicates: int = 0
    valid_replicates: int = 0
    invalid_replicates: int = 0
    suppression_reason: str | None
    resampling_plan_id: str | None = None
    resampling_unit: Literal["original_citation_id"] = "original_citation_id"


class AnalysisPanel(Model):
    panel_id: Text
    scope: Literal["all", "matched", "identifier_appendix"]
    condition: Text
    cohort: str | None
    summary: MetricGroup
    lookup_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    intervals: dict[str, StatisticalInterval]


class Comparison(Model):
    comparison_id: Text
    comparison_kind: Literal["providers", "canonical_mutation"]
    left_panel_id: Text
    right_panel_id: Text
    status: Literal["paired_sources", "unmatched_sources", "no_overlap"]
    shared_source_ids: tuple[str, ...]
    left_only_source_ids: tuple[str, ...]
    right_only_source_ids: tuple[str, ...]
    matched_left_panel_id: str | None = None
    matched_right_panel_id: str | None = None
    paired_retrieval_sources: bool


class Exclusion(Model):
    citation_id: Text
    lookup_id: str | None = None
    reason: Text


class LookupTiming(Model):
    lookup_id: Text
    started_at: AwareDatetime
    finished_at: AwareDatetime


class AnalysisOutput(Model):
    schema_version: Literal["1.0"] = "1.0"
    analysis_version: Literal["1"] = "1"
    analysis_id: Text
    config: AnalysisConfig
    data_label: DataLabel
    report_kind: Literal["empirical", "demonstration", "diagnostic"]
    coverage_label: Literal["Verified retrieval coverage under the recorded search strategy"] = (
        COVERAGE_LABEL
    )
    scope_note: str = SCOPE_NOTE
    dataset_fingerprint: Text
    evaluation_ids: tuple[str, ...]
    manifest: StudyManifest | None
    warnings: tuple[str, ...]
    exclusions: tuple[Exclusion, ...]
    timings: tuple[LookupTiming, ...]
    panels: tuple[AnalysisPanel, ...]
    comparisons: tuple[Comparison, ...]
    lookups: tuple[EvaluatedLookup, ...]
