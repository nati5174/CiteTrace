"""Cluster resampling tests use synthetic outcomes and no live API access."""

from collections.abc import Iterator

import httpx
import pytest
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.analysis import analyze
from citeprobe.analysis_models import AnalysisConfig
from citeprobe.evaluation import aggregate, evaluate
from citeprobe.evaluation_models import EvaluationConfig
from citeprobe.uncertainty import bootstrap_intervals, cluster_draws, percentile


def test_paired_provider_resampling_uses_identical_source_draws() -> None:
    dataset = synthetic_dataset(30)
    openalex = lookup_bundle(
        dataset,
        [{"results": [work(c.doi)] if i % 2 else []} for i, c in enumerate(dataset.citations)],
    )
    crossref = lookup_bundle(
        dataset,
        [
            {"status": "ok", "message": {"items": [{"DOI": c.doi}] if i % 2 else []}}
            for i, c in enumerate(dataset.citations)
        ],
        provider="crossref",
    )
    evaluation = evaluate(
        dataset, (openalex, crossref), config=EvaluationConfig(default_data_label="simulated")
    )
    config = AnalysisConfig(
        experiment="mutation-robustness",
        bootstrap=True,
        bootstrap_replicates=100,
        figure_formats=(),
    )
    first = analyze((evaluation,), config)[0]
    second = analyze((evaluation,), config)[0]
    assert first == second
    comparison = first.comparisons[0]
    assert comparison.status == "paired_sources" and comparison.paired_retrieval_sources
    main = [p for p in first.panels if p.scope == "all"]
    left, right = [p.intervals["recall_at_1"] for p in main]
    assert left.resampling_plan_id == right.resampling_plan_id
    assert left.lower == right.lower and left.upper == right.upper
    assert left.lower is not None and left.upper is not None
    assert left.lower < 0.5 < left.upper
    assert left.cluster_count == 30 and left.invalid_replicates == 0
    assert left.attempted_replicates == left.valid_replicates == 100
    assert (
        main[0].intervals["api_error_rate"].suppression_reason
        == "degenerate_bootstrap_distribution"
    )


def test_source_cluster_multiplicity_and_dependence_are_preserved() -> None:
    dataset = synthetic_dataset(30)
    hits = lookup_bundle(dataset, [{"results": [work(c.doi)]} for c in dataset.citations])
    rows = list(evaluate(dataset, (hits,)).lookups)
    # A controlled diagnostic sample with two correlated observations per source:
    # one hit and one empty. Its ratio must remain 1/2 in every whole-cluster draw.
    paired_rows = []
    for row in rows:
        paired_rows.append(row)
        paired_rows.append(
            row.model_copy(
                update={
                    "candidates": (),
                    "rank_one_judgment": None,
                    "outcome": "NOT_FOUND",
                    "recall_at_1": "MISS",
                    "recall_at_5": "MISS",
                }
            )
        )
    summary = aggregate({"data_label": "simulated"}, paired_rows)
    config = AnalysisConfig(
        experiment="mutation-robustness",
        bootstrap=True,
        bootstrap_replicates=100,
        figure_formats=(),
    )
    result = bootstrap_intervals(paired_rows, summary, config, "synthetic-correlated")
    assert summary.metrics["recall_at_1"].value == 0.5
    assert result["recall_at_1"].suppression_reason == "degenerate_bootstrap_distribution"
    sources = tuple(sorted({r.original_citation_id for r in rows}))
    draws = list(cluster_draws(sources, config, "synthetic-correlated"))
    assert len(draws) == 100 and all(len(draw) == 30 for draw in draws)
    assert any(len(set(draw)) < len(draw) for draw in draws)
    assert draws == list(cluster_draws(tuple(reversed(sources)), config, "synthetic-correlated"))
    changed = AnalysisConfig(
        experiment="mutation-robustness",
        bootstrap=True,
        seed=8,
        bootstrap_replicates=100,
        figure_formats=(),
    )
    assert draws != list(cluster_draws(sources, changed, "synthetic-correlated"))


def test_small_and_identity_uncertain_samples_suppress_intervals() -> None:
    dataset = synthetic_dataset(1)
    for raw, reason in (
        (work(dataset.citations[0].doi), "too_few_source_clusters"),
        (work(), "identity_uncertainty"),
    ):
        evaluation = evaluate(dataset, (lookup_bundle(dataset, [{"results": [raw]}]),))
        config = AnalysisConfig(
            experiment="mutation-robustness",
            bootstrap=True,
            bootstrap_replicates=100,
            figure_formats=(),
        )
        report = analyze((evaluation,), config)[0]
        interval = report.panels[0].intervals["recall_at_1"]
        assert interval.lower is None and interval.upper is None
        assert interval.suppression_reason == reason
        assert interval.attempted_replicates == 0


def test_undefined_replicates_are_not_silently_discarded(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = synthetic_dataset(31)
    bundle = lookup_bundle(dataset, [{"results": []}] * 30 + [httpx.ConnectError("simulated")])
    rows = list(evaluate(dataset, (bundle,)).lookups)
    source = next(row.original_citation_id for row in rows if not row.retrieval_eligible)
    config = AnalysisConfig(
        experiment="mutation-robustness",
        bootstrap=True,
        bootstrap_replicates=100,
        figure_formats=(),
    )

    def undefined_draws(
        sources: tuple[str, ...], config: AnalysisConfig, context: str
    ) -> Iterator[tuple[str, ...]]:
        for _ in range(config.bootstrap_replicates):
            yield tuple(source for _ in sources)

    monkeypatch.setattr("citeprobe.uncertainty.cluster_draws", undefined_draws)
    result = bootstrap_intervals(
        rows, aggregate({"data_label": "simulated"}, rows), config, "controlled"
    )
    assert result["recall_at_1"].suppression_reason == "undefined_bootstrap_replicates"
    assert result["recall_at_1"].invalid_replicates == 100
    assert result["recall_at_1"].valid_replicates == 0
    assert result["recall_at_1"].lower is None


def test_percentile_definition() -> None:
    assert percentile([0, 1], 0.25) == 0.25
