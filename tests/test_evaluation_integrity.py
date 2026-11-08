"""Reject incompatible or misleading experiments before computing metrics."""

from typing import Any

import pytest
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.evaluation import evaluate
from citeprobe.evaluation_models import EvaluationConfig
from citeprobe.lookup_inputs import fingerprint, mutation_tasks
from citeprobe.models import Dataset, MutationBatch
from citeprobe.mutations import generate_mutations
from citeprobe.resolution_models import LookupBundle


@pytest.mark.parametrize(
    "change",
    [
        "dataset_version",
        "dataset_fingerprint",
        "input_fingerprint",
        "config_fingerprint",
        "unknown_source",
        "duplicate_source",
        "providers",
        "inventory",
        "original_source",
        "source_kind",
        "lookup_id",
        "request_identifier",
        "hidden_query",
        "metadata",
        "duplicate_rank",
        "reordered_rank",
        "out_of_range_rank",
        "candidate_edit",
        "warnings",
        "attempts",
        "status",
        "outcome",
        "retry_count",
        "timestamps",
    ],
)
def test_reject_tampered_bundles(change: str) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(
        dataset, [{"results": [work("10.1234/fixture-0"), work("10.1234/other")]}]
    )
    data = bundle.model_dump(mode="json")
    result = data["results"][0]
    if change in {
        "dataset_version",
        "dataset_fingerprint",
        "input_fingerprint",
        "config_fingerprint",
    }:
        data[change] = "incompatible"
    elif change == "unknown_source":
        data["selected_source_ids"] = ["unknown"]
    elif change == "duplicate_source":
        data["selected_source_ids"] *= 2
    elif change == "providers":
        data["providers"] *= 2
    elif change == "inventory":
        data["results"] = []
    elif change == "original_source":
        result["original_citation_id"] = "wrong"
    elif change == "source_kind":
        result["source_kind"] = "mutation"
    elif change == "lookup_id":
        result["lookup_id"] = "tampered"
    elif change == "request_identifier":
        result["request"]["submitted_identifier"] = dataset.citations[0].doi
    elif change == "hidden_query":
        result["request"]["params"]["filter"] = "doi:10.1234/fixture-0"
    elif change == "metadata":
        result["request"]["submitted_metadata"]["year"] += 1
    elif change == "duplicate_rank":
        result["candidates"][1]["provider_rank"] = 1
    elif change == "reordered_rank":
        result["candidates"].reverse()
    elif change == "out_of_range_rank":
        result["candidates"][1]["provider_rank"] = 6
    elif change == "candidate_edit":
        result["candidates"][0]["doi"] = "10.1234/changed"
    elif change == "warnings":
        result["parsing_warnings"] = ["synthetic extra warning"]
    elif change == "attempts":
        result["attempts"] = []
    elif change == "status":
        result["response_status"] = 503
    elif change == "outcome":
        result["outcome"] = "NOT_FOUND"
        result["attempts"][-1]["outcome"] = "NOT_FOUND"
    elif change == "retry_count":
        result["retry_count"] = 5
    else:
        result["started_at"] = "2100-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        evaluate(dataset, (LookupBundle.model_validate(data),))


def test_duplicate_runs_are_not_double_counted() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    with pytest.raises(ValueError, match="Duplicate lookup"):
        evaluate(dataset, (bundle, bundle))
    data = bundle.model_dump(mode="json")
    data["generated_at"] = "2021-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="Duplicate lookup"):
        evaluate(dataset, (bundle, LookupBundle.model_validate(data)))


def test_incompatible_configs() -> None:
    dataset = synthetic_dataset(2)
    first = lookup_bundle(dataset, [{"results": []}])
    second = first.model_dump(mode="json")
    second["config"]["timeout_seconds"] = 12
    with pytest.raises(ValueError, match="configurations"):
        evaluate(dataset, (first, LookupBundle.model_validate(second)))


def test_pending_ground_truth_rejected() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    data = dataset.model_dump(mode="json")
    data["citations"][0]["provenance"].update(verification_status="pending", verified_at=None)
    pending = Dataset.model_validate(data)
    recorded = bundle.model_dump(mode="json")
    pending_hash = fingerprint(pending.model_dump(mode="json"))
    recorded.update(dataset_fingerprint=pending_hash, input_fingerprint=pending_hash)
    with pytest.raises(ValueError, match="unverified"):
        evaluate(pending, (LookupBundle.model_validate(recorded),))


def mutation_fixture() -> tuple[Dataset, MutationBatch, LookupBundle]:
    dataset = synthetic_dataset(1)
    batch = generate_mutations(dataset)
    tasks = mutation_tasks(dataset, batch)[:1]
    bundle = lookup_bundle(
        dataset,
        [{"results": []}],
        tasks=tasks,
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    return dataset, batch, bundle


def test_mutation_file_required() -> None:
    dataset, batch, bundle = mutation_fixture()
    with pytest.raises(ValueError, match="mutation batch"):
        evaluate(dataset, (bundle,))
    assert evaluate(dataset, (bundle,), mutations=(batch,)).lookups[0].mutation_type == "title_typo"


@pytest.mark.parametrize(
    "change", ["version", "source", "payload", "seed", "parameters", "duplicate"]
)
def test_invalid_mutation_batches(change: str) -> None:
    dataset, batch, bundle = mutation_fixture()
    data = batch.model_dump(mode="json")
    row = data["mutations"][0]
    if change == "version":
        data["dataset_version"] = "wrong"
    elif change == "source":
        row["original_citation_id"] = "unknown"
    elif change == "payload":
        row["citation"]["title"] = "Some other metadata"
    elif change == "seed":
        row["seed"] += 1
    elif change == "parameters":
        row["parameters"]["replacement"] = "invalid"
    else:
        data["mutations"].append(row)
    with pytest.raises(ValueError):
        evaluate(dataset, (bundle,), mutations=(MutationBatch.model_validate(data),))


@pytest.mark.parametrize("change", ["identifier_strategy", "original_metadata", "identifier_hint"])
def test_mutation_ground_truth_leakage_rejected(change: str) -> None:
    dataset, batch, bundle = mutation_fixture()
    data = bundle.model_dump(mode="json")
    row = data["results"][0]
    if change == "identifier_strategy":
        row["strategy"] = "identifier"
    elif change == "original_metadata":
        row["request"]["submitted_metadata"]["title"] = dataset.citations[0].title
    else:
        row["request"]["params"]["search"] += " " + str(dataset.citations[0].doi)
    with pytest.raises(ValueError):
        evaluate(dataset, (LookupBundle.model_validate(data),), mutations=(batch,))


@pytest.mark.parametrize(
    "config", [{"cohorts": {"unknown": "toy"}}, {"input_labels": {"unknown": "observed"}}]
)
def test_unknown_config_references(config: dict[str, Any]) -> None:
    dataset = synthetic_dataset(1)
    with pytest.raises(ValueError):
        evaluate(
            dataset,
            (lookup_bundle(dataset, [{"results": []}]),),
            config=EvaluationConfig.model_validate(config),
        )


def test_no_input() -> None:
    with pytest.raises(ValueError, match="At least one"):
        evaluate(synthetic_dataset(), ())
