"""All results in this module are explicitly synthetic, not benchmark observations."""

import httpx
import pytest
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.evaluation import evaluate, metric
from citeprobe.evaluation_io import csv_text
from citeprobe.evaluation_models import EvaluationConfig, IdentityMappings, MetricGroup
from citeprobe.lookup_inputs import canonical_tasks, fingerprint, mutation_tasks
from citeprobe.models import Dataset
from citeprobe.mutations import generate_mutations


def base_group(output_groups: tuple[MetricGroup, ...], label: str = "simulated") -> MetricGroup:
    return next(
        group
        for group in output_groups
        if group.dimensions
        == {
            "data_label": label,
            "provider": "openalex",
            "strategy": "metadata",
        }
    )


def distinct(dataset: Dataset, citation_id: str, doi: str) -> IdentityMappings:
    return IdentityMappings.model_validate(
        {
            "dataset_version": dataset.dataset_version,
            "mappings": [
                {
                    "citation_id": citation_id,
                    "relation": "different_work",
                    "identifiers": [{"namespace": "doi", "value": doi}],
                    "provenance": dataset.citations[0].provenance.model_dump(mode="json"),
                }
            ],
        }
    )


def test_explicit_denominators_and_uncertainty_bounds() -> None:
    dataset = synthetic_dataset()
    first_five = [work("10.1234/wrong", identifier="W999")] * 4 + [work("10.1234/fixture-1")]
    bundle = lookup_bundle(
        dataset,
        [
            {"results": [work("10.1234/fixture-0")]},
            {"results": first_five},
            {"results": [work("10.1234/unknown")]},
            {"results": []},
            httpx.ReadTimeout("synthetic timeout"),
            httpx.Response(429),
        ],
    )
    output = evaluate(
        dataset,
        (bundle,),
        mappings=distinct(dataset, "fixture-1", "10.1234/wrong"),
        config=EvaluationConfig(default_data_label="simulated"),
    )
    group = base_group(output.groups)
    assert group.lookup_count == 6
    assert group.retrieval_lookup_count == 4
    assert group.original_citation_count == 6
    assert group.retrieval_original_citation_count == 4
    metrics = group.metrics
    for name, numerator, lower, upper in (
        ("recall_at_1", 1, 0.25, 0.5),
        ("recall_at_5", 2, 0.5, 0.75),
        ("incorrect_match_rate", 1, 0.25, 0.5),
    ):
        result = metrics[name]
        assert result.numerator == numerator and result.denominator == 4
        assert result.uncertain_count == 1
        assert result.value is None
        assert result.lower_bound == lower and result.upper_bound == upper
        assert result.undefined_reason == "identity_uncertainty"
    assert metrics["unresolved_rate"].value == 0.25
    assert metrics["identity_undetermined_rate"].value == 0.25
    assert metrics["provider_error_rate"].value == 2 / 6
    assert metrics["timeout_rate"].value == 1 / 6
    assert metrics["rate_limited_rate"].value == 1 / 6
    assert metrics["api_error_rate"].value == 0
    assert all(
        row.recall_at_1 == "EXCLUDED" for row in output.lookups if not row.retrieval_eligible
    )


def test_exact_metrics_without_identity_uncertainty() -> None:
    dataset = synthetic_dataset(3)
    bundle = lookup_bundle(
        dataset,
        [
            {"results": [work("10.1234/fixture-0")]},
            {"results": [work("10.1234/wrong")]},
            {"results": []},
        ],
    )
    output = evaluate(
        dataset,
        (bundle,),
        mappings=distinct(dataset, "fixture-1", "10.1234/wrong"),
        config=EvaluationConfig(default_data_label="simulated"),
    )
    metrics = base_group(output.groups).metrics
    assert metrics["recall_at_1"].value == metrics["recall_at_5"].value == 1 / 3
    assert metrics["incorrect_match_rate"].value == 1 / 3
    assert (
        metrics["incorrect_match_rate"].lower_bound == metrics["incorrect_match_rate"].upper_bound
    )
    assert metrics["unresolved_rate"].value == 1 / 3
    assert metrics["identity_undetermined_rate"].value == 0


def test_provider_ranks_and_malformed_gaps_are_not_promoted() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(
        dataset, [{"results": [None, None, None, None, work("10.1234/fixture-0")]}]
    )
    output = evaluate(dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated"))
    row = output.lookups[0]
    assert row.candidates[0].candidate.provider_rank == 5
    assert row.candidates[0].candidate.ranking == {"relevance_score": 1.25}
    assert row.unavailable_provider_ranks == (1, 2, 3, 4)
    assert row.recall_at_1 == "UNDETERMINED"
    assert row.recall_at_5 == "HIT"
    metrics = base_group(output.groups).metrics
    assert metrics["recall_at_5"].value == 1
    assert metrics["recall_at_1"].value is None
    assert metrics["incorrect_match_rate"].value is None
    assert metrics["incorrect_match_rate"].lower_bound == 0
    assert metrics["incorrect_match_rate"].upper_bound == 1


def test_parse_gap_outside_top_one_does_not_make_top_one_uncertain() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": [work("10.1234/wrong"), None]}])
    output = evaluate(
        dataset,
        (bundle,),
        mappings=distinct(dataset, "fixture-0", "10.1234/wrong"),
        config=EvaluationConfig(default_data_label="simulated"),
    )
    metrics = base_group(output.groups).metrics
    assert metrics["recall_at_1"].value == 0
    assert metrics["recall_at_5"].value is None
    assert metrics["incorrect_match_rate"].value == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(429),
        httpx.ConnectError("synthetic"),
        httpx.ReadTimeout("synthetic"),
    ],
)
def test_error_only_group_has_undefined_retrieval_metrics(response: object) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [response])
    output = evaluate(dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated"))
    metrics = base_group(output.groups).metrics
    for name in (
        "recall_at_1",
        "recall_at_5",
        "incorrect_match_rate",
        "unresolved_rate",
        "identity_undetermined_rate",
    ):
        assert metrics[name].denominator == 0
        assert metrics[name].value is None
        assert metrics[name].lower_bound is None and metrics[name].upper_bound is None
        assert metrics[name].undefined_reason == "zero_denominator"
    assert metrics["provider_error_rate"].value == 1


def test_empty_bundle_has_null_metrics() -> None:
    dataset = synthetic_dataset(1)
    output = evaluate(dataset, (lookup_bundle(dataset, []),))
    assert len(output.groups) == 1
    assert output.groups[0].lookup_count == 0
    assert all(metric.value is None for metric in output.groups[0].metrics.values())
    assert output.groups[0].dimensions["strategy"] is None


def test_unknown_outcome_is_not_a_retrieval_miss_or_known_api_error() -> None:
    dataset = synthetic_dataset(1)
    data = lookup_bundle(dataset, [httpx.Response(503)]).model_dump(mode="json")
    data["results"][0]["outcome"] = "UNKNOWN"
    data["results"][0]["attempts"][-1]["outcome"] = "UNKNOWN"
    from citeprobe.resolution_models import LookupBundle

    output = evaluate(
        dataset,
        (LookupBundle.model_validate(data),),
        config=EvaluationConfig(default_data_label="simulated"),
    )
    metrics = base_group(output.groups).metrics
    assert metrics["unknown_outcome_rate"].value == 1
    assert metrics["provider_error_rate"].value == 0
    assert metrics["recall_at_1"].value is None


def test_mutation_to_original_identity_and_source_level_groups() -> None:
    dataset = synthetic_dataset(1)
    batch = generate_mutations(dataset, seed=42)
    tasks = mutation_tasks(dataset, batch)
    bundle = lookup_bundle(
        dataset,
        [{"results": [work("10.1234/fixture-0")]}] * len(tasks),
        tasks=tasks,
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    output = evaluate(
        dataset,
        (bundle,),
        mutations=(batch,),
        config=EvaluationConfig(default_data_label="simulated", cohorts={"fixture-0": "toy"}),
    )
    assert len(output.lookups) == 5
    assert all(
        row.original_citation_id == "fixture-0"
        and row.source_kind == "mutation"
        and row.recall_at_1 == "HIT"
        and row.mutation_type is not None
        for row in output.lookups
    )
    group = base_group(output.groups)
    assert group.lookup_count == 5 and group.original_citation_count == 1
    assert any(g.dimensions.get("cohort") == "toy" for g in output.groups)
    year_group = next(g for g in output.groups if g.dimensions.get("mutation_type") == "year_shift")
    assert year_group.lookup_count == 2


def test_data_origins_are_separate_and_never_inferred() -> None:
    dataset = synthetic_dataset(3)
    tasks = canonical_tasks(dataset)
    bundles = tuple(lookup_bundle(dataset, [{"results": []}], tasks=(task,)) for task in tasks)
    config = EvaluationConfig(
        input_labels={
            fingerprint(bundle.model_dump(mode="json")): label
            for bundle, label in zip(bundles, ("observed", "simulated", "unknown"), strict=True)
        }
    )
    output = evaluate(dataset, bundles, config=config)
    assert {row.data_label for row in output.lookups} == {"observed", "simulated", "unknown"}
    assert all(group.lookup_count == 1 for group in output.groups)
    assert all(
        group.empirical_data_eligible == (group.dimensions["data_label"] == "observed")
        for group in output.groups
    )
    default = evaluate(dataset, (bundles[0],))
    assert default.lookups[0].data_label == "unknown"
    assert not any(group.empirical_data_eligible for group in default.groups)


def test_deterministic_output_and_redundant_groupings() -> None:
    dataset = synthetic_dataset(2)
    tasks = canonical_tasks(dataset)
    bundles = tuple(lookup_bundle(dataset, [{"results": []}], tasks=(task,)) for task in tasks)
    config = EvaluationConfig(default_data_label="simulated", groupings=((), (), ("provider",)))
    before = [bundle.model_dump_json() for bundle in bundles]
    first = evaluate(dataset, bundles, config=config)
    second = evaluate(dataset, tuple(reversed(bundles)), config=config)
    assert first.model_dump_json() == second.model_dump_json()
    assert csv_text(first) == csv_text(second)
    assert len(first.groups) == 1 and first.groups[0].lookup_count == 2
    assert [bundle.model_dump_json() for bundle in bundles] == before


@pytest.mark.parametrize(
    ("numerator", "denominator", "uncertain"), [(1, 0, 0), (2, 2, 1), (-1, 1, 0)]
)
def test_invalid_metric_counts(numerator: int, denominator: int, uncertain: int) -> None:
    with pytest.raises(ValueError):
        metric(numerator, denominator, uncertain)


def test_crossref_doi_identity_and_preserved_provider_order() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(
        dataset,
        [
            {
                "status": "ok",
                "message": {
                    "items": [
                        {"DOI": "10.1234/other", "title": ["Synthetic fixture"], "score": 1},
                        {"DOI": "10.1234/FIXTURE-0", "title": ["Different title"], "score": 999},
                    ]
                },
            }
        ],
        provider="crossref",
    )
    output = evaluate(dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated"))
    assert output.lookups[0].recall_at_1 == "UNDETERMINED"
    assert output.lookups[0].recall_at_5 == "HIT"
    assert [j.candidate.provider_rank for j in output.lookups[0].candidates] == [1, 2]
    assert [j.candidate.ranking["score"] for j in output.lookups[0].candidates] == [1, 999]


def test_verified_crossref_mapping_for_arxiv_only_ground_truth() -> None:
    data = synthetic_dataset(1).model_dump(mode="json")
    data["citations"][0].update(doi=None, arxiv_id="1706.00001")
    dataset = Dataset.model_validate(data)
    bundle = lookup_bundle(
        dataset,
        [
            {
                "status": "ok",
                "message": {
                    "items": [
                        {"DOI": "10.1234/alias", "title": ["Synthetic fixture"]},
                    ]
                },
            }
        ],
        provider="crossref",
    )
    mappings = IdentityMappings.model_validate(
        {
            "dataset_version": dataset.dataset_version,
            "mappings": [
                {
                    "citation_id": "fixture-0",
                    "relation": "same_work",
                    "identifiers": [{"namespace": "crossref", "value": "10.1234/alias"}],
                    "provenance": dataset.citations[0].provenance.model_dump(mode="json"),
                }
            ],
        }
    )
    unknown = evaluate(dataset, (bundle,))
    assert unknown.lookups[0].rank_one_judgment == "UNDETERMINED"
    matched = evaluate(dataset, (bundle,), mappings=mappings)
    assert matched.lookups[0].rank_one_judgment == "CORRECT"


def test_canonical_identifier_strategy_keeps_separate_groups() -> None:
    dataset = synthetic_dataset(1)
    metadata_bundle = lookup_bundle(dataset, [{"results": []}])
    identifier_bundle = lookup_bundle(
        dataset, [{"results": []}], tasks=canonical_tasks(dataset, "identifier")
    )
    output = evaluate(dataset, (metadata_bundle, identifier_bundle))
    assert {group.dimensions["strategy"] for group in output.groups} == {"metadata", "identifier"}
    assert all(group.lookup_count == 1 for group in output.groups)
