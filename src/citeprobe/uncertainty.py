"""Optional source-cluster bootstrap; never impute unidentified identities."""

import random
from collections import defaultdict
from collections.abc import Iterator

from citeprobe.analysis_models import AnalysisConfig, StatisticalInterval
from citeprobe.evaluation import aggregate
from citeprobe.evaluation_models import EvaluatedLookup, MetricGroup
from citeprobe.lookup_inputs import fingerprint


def cluster_draws(
    sources: tuple[str, ...], config: AnalysisConfig, context: str
) -> Iterator[tuple[str, ...]]:
    """Identical source sets/context use identical draws across providers/conditions."""
    population = tuple(sorted(set(sources)))
    rng = random.Random(
        fingerprint({"seed": config.seed, "sources": population, "context": context})
    )
    for _ in range(config.bootstrap_replicates):
        yield tuple(rng.choice(population) for _ in population)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def bootstrap_intervals(
    rows: list[EvaluatedLookup], summary: MetricGroup, config: AnalysisConfig, context: str
) -> dict[str, StatisticalInterval]:
    by_source: dict[str, list[EvaluatedLookup]] = defaultdict(list)
    for row in rows:
        by_source[row.original_citation_id].append(row)
    sources = tuple(sorted(by_source))
    eligible = {row.original_citation_id for row in rows if row.retrieval_eligible}
    plan_id = (
        fingerprint(
            {
                "sources": sources,
                "seed": config.seed,
                "context": context,
                "replicates": config.bootstrap_replicates,
            }
        )
        if config.bootstrap
        else None
    )
    result: dict[str, StatisticalInterval] = {}
    pending: dict[str, list[float]] = {}
    invalid: dict[str, int] = defaultdict(int)
    operational = {
        "provider_error_rate",
        "timeout_rate",
        "rate_limited_rate",
        "api_error_rate",
        "unknown_outcome_rate",
    }
    for name, metric in summary.metrics.items():
        count = len(sources) if name in operational else len(eligible)
        reason: str | None = (
            "bootstrap_disabled"
            if not config.bootstrap
            else metric.undefined_reason
            if metric.value is None
            else "too_few_source_clusters"
            if count < config.min_cluster_count
            else None
        )
        result[name] = StatisticalInterval(
            confidence_level=config.confidence_level,
            cluster_count=count,
            replicates=config.bootstrap_replicates if config.bootstrap else 0,
            suppression_reason=reason,
            resampling_plan_id=plan_id,
        )
        if reason is None:
            pending[name] = []
    if pending:
        for draw in cluster_draws(sources, config, context):
            # Preserve multiplicities and every associated observation in a sampled cluster.
            sample = [row for source in draw for row in by_source[source]]
            metrics = aggregate(summary.dimensions, sample).metrics
            for name, values in pending.items():
                value = metrics[name].value
                if value is None:
                    invalid[name] += 1
                else:
                    values.append(value)
        alpha = (1 - config.confidence_level) / 2
        for name, values in pending.items():
            previous = result[name]
            reason = (
                "undefined_bootstrap_replicates"
                if invalid[name]
                else ("degenerate_bootstrap_distribution" if len(set(values)) < 2 else None)
            )
            result[name] = StatisticalInterval(
                **{
                    **previous.model_dump(),
                    "suppression_reason": reason,
                    "invalid_replicates": invalid[name],
                    "attempted_replicates": len(values) + invalid[name],
                    "valid_replicates": len(values),
                    "lower": percentile(values, alpha) if reason is None else None,
                    "upper": percentile(values, 1 - alpha) if reason is None else None,
                },
            )
    return result
