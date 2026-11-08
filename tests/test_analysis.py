"""Experiment design, cohort boundaries and origin isolation on synthetic evidence."""

from typing import Any

import httpx
import pytest
from analysis_helpers import synthetic_study
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.analysis import age_cohort, analyze
from citeprobe.analysis_models import AnalysisConfig, PreprintDate, StudyManifest
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_models import EvaluationConfig
from citeprobe.lookup_inputs import canonical_tasks, fingerprint, mutation_tasks
from citeprobe.mutations import generate_mutations


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-1, None),
        (0, None),
        (1, "1–7 days"),
        (7, "1–7 days"),
        (8, "8–14 days"),
        (14, "8–14 days"),
        (15, "15–30 days"),
        (30, "15–30 days"),
        (31, "31–60 days"),
        (60, "31–60 days"),
        (61, None),
    ],
)
def test_age_cohort_boundaries(days: int, expected: str | None) -> None:
    assert age_cohort(days) == expected


def test_recent_preprints_and_long_window_override_keep_all_observations() -> None:
    dataset = synthetic_dataset(4)
    bundle = lookup_bundle(dataset, [{"results": [work(c.doi)]} for c in dataset.citations])
    # The observed label is a synthetic test assertion used solely to exercise eligibility gates.
    evaluation = evaluate(
        dataset, (bundle,), config=EvaluationConfig(default_data_label="observed")
    )
    study = synthetic_study(dataset, (bundle,), ages=(3, 10, 25, 45), hours=48)
    config = AnalysisConfig(experiment="recent-preprints", figure_formats=())
    first = analyze((evaluation,), config, dataset=dataset, bundles=(bundle,), manifest=study)[0]
    assert first.report_kind == "diagnostic"
    assert sum(p.summary.lookup_count for p in first.panels if p.scope == "all") == 4
    assert any("exceeds configured" in warning for warning in first.warnings)
    assert len(first.timings) == 4 and not first.exclusions
    assert {p.cohort for p in first.panels} == {"1–7 days", "8–14 days", "15–30 days", "31–60 days"}
    override = AnalysisConfig(
        experiment="recent-preprints", max_collection_hours=72, figure_formats=()
    )
    second = analyze((evaluation,), override, dataset=dataset, bundles=(bundle,), manifest=study)[0]
    assert second.report_kind == "empirical"
    assert sum(p.summary.lookup_count for p in second.panels if p.scope == "all") == 4
    assert any("48 hours" in warning for warning in second.warnings)
    assert [(t.started_at, t.finished_at) for t in second.timings] == [
        (t.started_at, t.finished_at) for t in first.timings
    ]


@pytest.mark.parametrize("change", ["missing", "pending", "revision", "day_zero", "old", "future"])
def test_dates_are_not_invented_and_exclusions_are_explicit(change: str) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    evaluation = evaluate(
        dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated")
    )
    study = synthetic_study(dataset, (bundle,))
    data = study.model_dump(mode="json")
    row = data["preprint_dates"][0]
    if change == "missing":
        data["preprint_dates"] = []
    elif change == "pending":
        row["provenance"].update(verification_status="pending", verified_at=None)
    elif change == "revision":
        row["date_kind"] = "revision"
    else:
        study = synthetic_study(
            dataset, (bundle,), ages=({"day_zero": 0, "old": 61, "future": -1}[change],)
        )
        data = study.model_dump(mode="json")
    report = analyze(
        (evaluation,),
        AnalysisConfig(experiment="recent-preprints", figure_formats=()),
        dataset=dataset,
        bundles=(bundle,),
        manifest=StudyManifest.model_validate(data),
    )[0]
    assert len(report.lookups) == 1  # Raw rows remain traceable even when outside experiment scope.
    assert len(report.exclusions) == 1 and report.exclusions[0].reason
    assert report.panels[0].summary.retrieval_lookup_count == 0
    assert report.panels[0].summary.metrics["recall_at_1"].value is None
    assert report.report_kind == "demonstration"


def test_experiment_a_requires_manifest_and_never_treats_mutations_as_coverage() -> None:
    dataset = synthetic_dataset(1)
    batch = generate_mutations(dataset)
    task = mutation_tasks(dataset, batch)[:1]
    bundle = lookup_bundle(
        dataset,
        [{"results": [work(dataset.citations[0].doi)]}],
        tasks=task,
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    evaluation = evaluate(dataset, (bundle,), mutations=(batch,))
    config = AnalysisConfig(experiment="recent-preprints", figure_formats=())
    with pytest.raises(ValueError, match="manifest"):
        analyze((evaluation,), config)
    result = analyze(
        (evaluation,),
        config,
        dataset=dataset,
        bundles=(bundle,),
        manifest=synthetic_study(dataset, (bundle,)),
    )[0]
    assert "canonical metadata-only" in result.exclusions[0].reason


def test_mutation_baseline_pairing_and_provider_matching() -> None:
    dataset = synthetic_dataset(3)
    batch = generate_mutations(dataset)
    tasks = mutation_tasks(dataset, batch)
    mutated = lookup_bundle(
        dataset,
        [{"results": []}] * len(tasks),
        tasks=tasks,
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    baseline = lookup_bundle(dataset, [{"results": []}] * 2, tasks=canonical_tasks(dataset)[:2])
    evaluation = evaluate(
        dataset,
        (baseline, mutated),
        mutations=(batch,),
        config=EvaluationConfig(default_data_label="simulated"),
    )
    config = AnalysisConfig(
        experiment="mutation-robustness",
        bootstrap=True,
        bootstrap_replicates=100,
        figure_formats=(),
    )
    result = analyze((evaluation,), config)[0]
    comparisons = [c for c in result.comparisons if c.comparison_kind == "canonical_mutation"]
    assert len(comparisons) == 4
    panels = {p.panel_id: p for p in result.panels}
    for comparison in comparisons:
        assert comparison.status == "unmatched_sources"
        assert not comparison.paired_retrieval_sources
        assert comparison.shared_source_ids == ("fixture-0", "fixture-1")
        assert "fixture-2" in comparison.left_only_source_ids + comparison.right_only_source_ids
        assert comparison.matched_left_panel_id is not None
        assert comparison.matched_right_panel_id is not None
        left, right = (
            panels[comparison.matched_left_panel_id],
            panels[comparison.matched_right_panel_id],
        )
        assert left.source_ids == right.source_ids == ("fixture-0", "fixture-1")
        assert (
            left.intervals["recall_at_1"].resampling_plan_id
            == right.intervals["recall_at_1"].resampling_plan_id
        )
        assert left.intervals["recall_at_1"].suppression_reason == "too_few_source_clusters"


def test_missing_baseline_does_not_become_a_failure() -> None:
    dataset = synthetic_dataset(1)
    batch = generate_mutations(dataset)
    tasks = mutation_tasks(dataset, batch)[:1]
    bundle = lookup_bundle(
        dataset,
        [{"results": []}],
        tasks=tasks,
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    result = analyze(
        (evaluate(dataset, (bundle,), mutations=(batch,)),),
        AnalysisConfig(experiment="mutation-robustness", figure_formats=()),
    )[0]
    baseline = next(p for p in result.panels if p.condition == "canonical")
    assert baseline.summary.lookup_count == 0
    assert baseline.summary.metrics["unresolved_rate"].value is None
    assert result.comparisons[0].status == "no_overlap"
    import csv
    import io

    from citeprobe.reporting import table_documents

    rows = list(csv.DictReader(io.StringIO(table_documents(result)["baseline-availability.csv"])))
    assert len(rows) == 1
    assert rows[0]["baseline_outcome"] == "missing" and rows[0]["baseline_lookup_id"] == ""
    assert rows[0]["baseline_retrieval_eligible"] == "False"


def test_identifiers_stay_in_separate_appendix() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}], tasks=canonical_tasks(dataset, "identifier"))
    result = analyze(
        (evaluate(dataset, (bundle,)),),
        AnalysisConfig(experiment="mutation-robustness", figure_formats=()),
    )[0]
    appendix = next(p for p in result.panels if p.scope == "identifier_appendix")
    assert appendix.summary.lookup_count == 1
    assert all(p.summary.lookup_count == 0 for p in result.panels if p.scope == "all")


def test_origin_labels_remain_separate_and_failed_lookups_are_not_missing_papers() -> None:
    dataset = synthetic_dataset(3)
    tasks = canonical_tasks(dataset)
    bundles = tuple(
        lookup_bundle(dataset, [httpx.ConnectError("mocked")], tasks=(task,)) for task in tasks
    )
    labels = ("observed", "simulated", "unknown")
    evaluation = evaluate(
        dataset,
        bundles,
        config=EvaluationConfig(
            input_labels={
                fingerprint(bundle.model_dump(mode="json")): label
                for bundle, label in zip(bundles, labels, strict=True)
            }
        ),
    )
    reports = analyze(
        (evaluation,), AnalysisConfig(experiment="mutation-robustness", figure_formats=())
    )
    assert {r.data_label for r in reports} == set(labels)
    assert all(r.report_kind != "empirical" for r in reports)
    for report in reports:
        assert len(report.lookups) == 1
        assert all(row.data_label == report.data_label for row in report.lookups)
        summary = report.panels[0].summary
        assert summary.metrics["api_error_rate"].value == 1
        assert summary.metrics["unresolved_rate"].value is None
        assert summary.metrics["recall_at_5"].value is None


@pytest.mark.parametrize(
    "update",
    [
        {"precision": "timestamp"},
        {"published_at": "2020-01-01T00:00:00Z"},
        {"precision": "timestamp", "published_at": "2020-01-02T00:00:00Z"},
    ],
)
def test_publication_date_precision_is_explicit(update: dict[str, Any]) -> None:
    dataset = synthetic_dataset(1)
    value = {
        "citation_id": "fixture-0",
        "publication_date": "2020-01-01",
        "provenance": dataset.citations[0].provenance.model_dump(mode="json"),
        **update,
    }
    with pytest.raises(ValueError):
        PreprintDate.model_validate(value)


def test_canonical_only_observed_results_do_not_establish_mutation_robustness() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": [work(dataset.citations[0].doi)]}])
    evaluation = evaluate(
        dataset, (bundle,), config=EvaluationConfig(default_data_label="observed")
    )
    result = analyze(
        (evaluation,),
        AnalysisConfig(experiment="mutation-robustness", figure_formats=()),
        dataset=dataset,
        bundles=(bundle,),
        manifest=synthetic_study(dataset, (bundle,)),
    )[0]
    assert result.report_kind == "diagnostic"
    assert any("baseline diagnostics only" in warning for warning in result.warnings)


def test_long_window_cannot_include_lookups_made_before_preprint_publication() -> None:
    """Regression: reference-date recency alone does not establish query-time eligibility."""
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    evaluation = evaluate(
        dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated")
    )
    study = synthetic_study(dataset, (bundle,)).model_dump(mode="json")
    study.update(
        collection_started_at="2020-01-01T00:00:00Z",
        collection_finished_at="2020-01-03T00:00:00Z",
        reference_date="2020-01-03",
    )
    study["preprint_dates"][0]["publication_date"] = "2020-01-02"
    result = analyze(
        (evaluation,),
        AnalysisConfig(experiment="recent-preprints", max_collection_hours=72, figure_formats=()),
        dataset=dataset,
        bundles=(bundle,),
        manifest=StudyManifest.model_validate(study),
    )[0]
    assert len(result.lookups) == 1
    assert len(result.exclusions) == 1 and "predates" in result.exclusions[0].reason
    assert all(panel.summary.lookup_count == 0 for panel in result.panels)
