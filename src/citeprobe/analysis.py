"""Experiment selection and comparisons using unchanged Part 3 aggregates."""

from collections import defaultdict
from datetime import UTC
from itertools import combinations

from citeprobe.analysis_models import (
    AnalysisConfig,
    AnalysisOutput,
    AnalysisPanel,
    Comparison,
    Exclusion,
    StudyManifest,
)
from citeprobe.analysis_validation import validate_evaluations
from citeprobe.evaluation import aggregate
from citeprobe.evaluation_models import EvaluatedLookup, EvaluationOutput
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.resolution_models import LookupBundle
from citeprobe.uncertainty import bootstrap_intervals


class PanelBuilder:
    def __init__(self, label: str, config: AnalysisConfig) -> None:
        self.label, self.config = label, config
        self.panels: dict[str, AnalysisPanel] = {}
        self.rows: dict[str, list[EvaluatedLookup]] = {}

    def add(
        self,
        provider: str,
        condition: str,
        cohort: str | None,
        scope: str,
        subset: list[EvaluatedLookup],
    ) -> AnalysisPanel:
        dimensions = {
            "data_label": self.label,
            "provider": provider,
            "strategy": None
            if condition == "no_observations"
            else "identifier"
            if scope == "identifier_appendix"
            else "metadata",
            "condition": condition,
            "cohort": cohort,
            "scope": scope,
        }
        summary = aggregate(dimensions, subset)
        identifier = fingerprint(
            {"dimensions": dimensions, "lookups": sorted(row.lookup_id for row in subset)}
        )
        if identifier not in self.panels:
            self.panels[identifier] = AnalysisPanel(
                panel_id=identifier,
                scope=scope,
                condition=condition,
                cohort=cohort,
                summary=summary,
                lookup_ids=tuple(sorted(row.lookup_id for row in subset)),
                source_ids=tuple(sorted({row.original_citation_id for row in subset})),
                intervals=bootstrap_intervals(
                    subset, summary, self.config, f"{self.label}:{self.config.experiment}"
                ),
            )
            self.rows[identifier] = subset
        return self.panels[identifier]


def age_cohort(days: int) -> str | None:
    for lower, upper in ((1, 7), (8, 14), (15, 30), (31, 60)):
        if lower <= days <= upper:
            return f"{lower}–{upper} days"
    return None


def analyze(
    evaluations: tuple[EvaluationOutput, ...],
    config: AnalysisConfig,
    *,
    dataset: Dataset | None = None,
    bundles: tuple[LookupBundle, ...] = (),
    manifest: StudyManifest | None = None,
) -> tuple[AnalysisOutput, ...]:
    evidence = validate_evaluations(
        evaluations, config, dataset=dataset, bundles=bundles, manifest=manifest
    )
    labels = sorted({item.data_label for evaluation in evaluations for item in evaluation.inputs})
    outputs: list[AnalysisOutput] = []
    dates = {item.citation_id: item for item in manifest.preprint_dates} if manifest else {}
    for label in labels:
        rows = sorted(
            [
                row
                for evaluation in evidence.evaluations
                for row in evaluation.lookups
                if row.data_label == label
            ],
            key=lambda row: row.lookup_id,
        )
        warnings = list(evidence.warnings)
        exclusions: list[Exclusion] = []
        buckets: dict[tuple[str, str, str | None, str], list[EvaluatedLookup]] = defaultdict(list)
        retained: list[EvaluatedLookup] = []
        for row in rows:
            reason = None
            cohort = row.cohort
            if manifest and row.original_citation_id not in manifest.citation_ids:
                reason = "Outside explicit study citation inventory"
            if config.experiment == "recent-preprints":
                if row.source_kind != "canonical" or row.strategy != "metadata":
                    reason = (
                        reason
                        or "Experiment A main analysis requires canonical metadata-only searches"
                    )
                item = dates.get(row.original_citation_id)
                if item is None:
                    reason = reason or "Missing verified first-public preprint date"
                elif item.date_kind != "first_public_preprint":
                    reason = (
                        reason or "Revision date cannot substitute for first-public preprint date"
                    )
                elif item.provenance.verification_status != "verified":
                    reason = reason or "First-public preprint date verification pending"
                elif manifest and manifest.reference_date:
                    timing = evidence.timings.get(row.lookup_id)
                    if timing and (
                        timing.started_at.astimezone(UTC).date() < item.publication_date
                        or (item.published_at is not None and timing.started_at < item.published_at)
                    ):
                        reason = reason or "Lookup predates the verified first-public preprint date"
                    days = (manifest.reference_date - item.publication_date).days
                    cohort = age_cohort(days)
                    if cohort is None:
                        reason = (
                            reason
                            or f"Paper age {days} days is outside the declared 1–60-day cohorts"
                        )
            if reason:
                exclusions.append(
                    Exclusion(
                        citation_id=row.original_citation_id, lookup_id=row.lookup_id, reason=reason
                    )
                )
                continue
            retained.append(row)
            condition = "canonical" if row.source_kind == "canonical" else str(row.mutation_type)
            scope = "all" if row.strategy == "metadata" else "identifier_appendix"
            buckets[(row.provider, condition, cohort, scope)].append(row)
        if manifest:
            represented = {row.original_citation_id for row in rows}
            for source in sorted(set(manifest.citation_ids) - represented):
                exclusions.append(
                    Exclusion(
                        citation_id=source,
                        reason="Study citation has no evaluated lookup for this data origin",
                    )
                )
        builder = PanelBuilder(label, config)
        panels, panel_rows = builder.panels, builder.rows
        add_panel = builder.add

        for (provider, condition, cohort, scope), subset in sorted(
            buckets.items(), key=lambda pair: str(pair[0])
        ):
            add_panel(provider, condition, cohort, scope, subset)
        main = [panel for panel in panels.values() if panel.scope == "all"]
        if not main:
            warnings.append(
                "No main-experiment observations are eligible; no retrieval-performance "
                "finding is supported."
            )
            providers = sorted(
                {
                    str(group.dimensions["provider"])
                    for evaluation in evaluations
                    for group in evaluation.groups
                    if group.dimensions["data_label"] == label
                }
            )
            for provider in providers:
                add_panel(provider, "no_observations", None, "all", [])
        comparisons: list[Comparison] = []
        pairs: list[tuple[str, AnalysisPanel, AnalysisPanel]] = []
        for left, right in combinations(main, 2):
            same_condition = left.condition == right.condition and left.cohort == right.cohort
            same_provider = (
                left.summary.dimensions["provider"] == right.summary.dimensions["provider"]
            )
            if same_condition and not same_provider:
                pairs.append(("providers", left, right))
            elif (
                config.experiment == "mutation-robustness"
                and same_provider
                and left.cohort == right.cohort
                and "canonical" in {left.condition, right.condition}
            ):
                pairs.append(("canonical_mutation", left, right))
        if config.experiment == "mutation-robustness":
            for panel in main:
                if panel.condition != "canonical" and not any(
                    other.condition == "canonical"
                    and other.cohort == panel.cohort
                    and other.summary.dimensions["provider"] == panel.summary.dimensions["provider"]
                    for other in main
                ):
                    baseline = add_panel(
                        str(panel.summary.dimensions["provider"]),
                        "canonical",
                        panel.cohort,
                        "all",
                        [],
                    )
                    pairs.append(("canonical_mutation", baseline, panel))
                    warnings.append(
                        "Canonical metadata-only baseline missing for "
                        f"{panel.summary.dimensions['provider']} / {panel.condition}; "
                        "no paired baseline claim."
                    )
        for kind, left, right in pairs:
            left_set, right_set = set(left.source_ids), set(right.source_ids)
            shared = left_set & right_set
            left_rows, right_rows = panel_rows[left.panel_id], panel_rows[right.panel_id]
            eligible_left = {
                row.original_citation_id for row in left_rows if row.retrieval_eligible
            }
            eligible_right = {
                row.original_citation_id for row in right_rows if row.retrieval_eligible
            }
            matched_sources = eligible_left & eligible_right
            matched_left = matched_right = None
            if matched_sources:
                matched_left = add_panel(
                    str(left.summary.dimensions["provider"]),
                    left.condition,
                    left.cohort,
                    "matched",
                    [row for row in left_rows if row.original_citation_id in matched_sources],
                )
                matched_right = add_panel(
                    str(right.summary.dimensions["provider"]),
                    right.condition,
                    right.cohort,
                    "matched",
                    [row for row in right_rows if row.original_citation_id in matched_sources],
                )
            comparisons.append(
                Comparison(
                    comparison_id=fingerprint([kind, left.panel_id, right.panel_id]),
                    comparison_kind=kind,
                    left_panel_id=left.panel_id,
                    right_panel_id=right.panel_id,
                    status="paired_sources"
                    if left_set == right_set and shared
                    else "unmatched_sources"
                    if shared
                    else "no_overlap",
                    shared_source_ids=tuple(sorted(shared)),
                    left_only_source_ids=tuple(sorted(left_set - right_set)),
                    right_only_source_ids=tuple(sorted(right_set - left_set)),
                    matched_left_panel_id=matched_left.panel_id if matched_left else None,
                    matched_right_panel_id=matched_right.panel_id if matched_right else None,
                    paired_retrieval_sources=bool(
                        eligible_left and eligible_left == eligible_right and left_set == right_set
                    ),
                )
            )
        empirical = (
            label == "observed"
            and evidence.provenance_complete
            and any(
                row.retrieval_eligible
                and row.strategy == "metadata"
                and (config.experiment != "mutation-robustness" or row.source_kind == "mutation")
                for row in retained
            )
        )
        if config.experiment == "mutation-robustness" and not any(
            row.source_kind == "mutation" for row in retained
        ):
            warnings.append(
                "No mutation observations supplied; canonical results are baseline "
                "diagnostics only."
            )
        kind = (
            "empirical" if empirical else "demonstration" if label == "simulated" else "diagnostic"
        )
        if not any(row.retrieval_eligible for row in retained):
            warnings.append(
                "Retrieval performance could not be assessed; operational failures/empty "
                "experiment supply no eligible denominator."
            )
        payload = {
            "config": config.model_dump(mode="json"),
            "data_label": label,
            "report_kind": kind,
            "dataset_fingerprint": evaluations[0].dataset_fingerprint,
            "evaluation_ids": sorted(
                e.evaluation_id for e in evaluations if any(i.data_label == label for i in e.inputs)
            ),
            "manifest": manifest.model_dump(mode="json") if manifest else None,
            "warnings": sorted(set(warnings)),
            "exclusions": [
                value.model_dump(mode="json")
                for value in sorted(
                    exclusions, key=lambda e: (e.citation_id, e.lookup_id or "", e.reason)
                )
            ],
            "timings": [
                evidence.timings[row.lookup_id].model_dump(mode="json")
                for row in rows
                if row.lookup_id in evidence.timings
            ],
            "panels": [
                panel.model_dump(mode="json")
                for panel in sorted(panels.values(), key=lambda panel: panel.panel_id)
            ],
            "comparisons": [
                value.model_dump(mode="json")
                for value in sorted(comparisons, key=lambda value: value.comparison_id)
            ],
            "lookups": [row.model_dump(mode="json") for row in rows],
        }
        outputs.append(
            AnalysisOutput.model_validate({**payload, "analysis_id": fingerprint(payload)})
        )
    return tuple(outputs)
