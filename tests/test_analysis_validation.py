"""Tampered artifacts must fail even when an editor recomputes the unsiged content hash."""

from typing import Any

import pytest
from analysis_helpers import synthetic_study
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.analysis import analyze
from citeprobe.analysis_models import AnalysisConfig, StudyManifest
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset


def resign(data: dict[str, Any]) -> EvaluationOutput:
    data["evaluation_id"] = fingerprint(
        {
            key: value
            for key, value in data.items()
            if key not in {"schema_version", "evaluator_version", "evaluation_id"}
        }
    )
    return EvaluationOutput.model_validate(data)


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "metric_definition",
        "mapping_hash",
        "origin",
        "counts",
        "bound",
        "rank",
        "state",
        "eligibility",
        "source_reference",
        "input_reference",
        "duplicate_group",
    ],
)
def test_reject_invalid_evaluation_artifacts(change: str) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": [work(dataset.citations[0].doi)]}])
    evaluation = evaluate(dataset, (bundle,))
    data = evaluation.model_dump(mode="json")
    if change == "id":
        data["evaluation_id"] = "bad"
    elif change == "metric_definition":
        data["metric_definitions"]["recall_at_1"] = "different denominator"
    elif change == "mapping_hash":
        data["identity_mappings_fingerprint"] = "bad"
    elif change == "origin":
        data["lookups"][0]["data_label"] = "observed"
    elif change == "counts":
        data["groups"][0]["retrieval_lookup_count"] = 42
    elif change == "bound":
        data["groups"][0]["metrics"]["recall_at_1"]["lower_bound"] = 0.5
    elif change == "rank":
        data["lookups"][0]["candidates"][0]["candidate"]["provider_rank"] = 6
    elif change == "state":
        data["lookups"][0]["recall_at_1"] = "MISS"
    elif change == "eligibility":
        data["lookups"][0]["retrieval_eligible"] = False
    elif change == "source_reference":
        data["lookups"][0]["original_citation_id"] = "unknown"
    elif change == "input_reference":
        data["lookups"][0]["input_bundle_id"] = "unknown"
    else:
        data["groups"].append(data["groups"][0])
    modified = EvaluationOutput.model_validate(data) if change == "id" else resign(data)
    with pytest.raises(ValueError):
        analyze((modified,), AnalysisConfig(experiment="mutation-robustness", figure_formats=()))


def test_duplicate_and_incompatible_artifacts() -> None:
    dataset = synthetic_dataset(1)
    evaluation = evaluate(dataset, (lookup_bundle(dataset, [{"results": []}]),))
    config = AnalysisConfig(experiment="mutation-robustness", figure_formats=())
    with pytest.raises(ValueError, match="Duplicate evaluation"):
        analyze((evaluation, evaluation), config)
    data = evaluation.model_dump(mode="json")
    data["code_fingerprint"] = "other code"
    with pytest.raises(ValueError, match="Incompatible"):
        analyze((evaluation, resign(data)), config)
    with pytest.raises(ValueError, match="dataset fingerprint"):
        analyze((evaluation,), config, dataset=synthetic_dataset(2))


def test_study_provenance_integrity() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    evaluation = evaluate(dataset, (bundle,))
    study = synthetic_study(dataset, (bundle,))
    config = AnalysisConfig(experiment="recent-preprints", figure_formats=())
    for change in ("hash", "references", "inventory", "window", "reference_date"):
        data = study.model_dump(mode="json")
        if change == "hash":
            data["dataset_fingerprint"] = "wrong"
        elif change == "references":
            data["lookup_bundle_ids"] = ["wrong"]
        elif change == "inventory":
            data["citation_ids"].append("unknown")
        elif change == "reference_date":
            data["reference_date"] = "2099-01-01"
        else:
            data["collection_started_at"] = "2020-01-01T00:00:01Z"
            data["collection_finished_at"] = "2020-01-01T00:00:02Z"
        with pytest.raises(ValueError):
            analyze(
                (evaluation,),
                config,
                dataset=dataset,
                bundles=(bundle,),
                manifest=StudyManifest.model_validate(data),
            )


def test_unverified_ground_truth_cannot_be_used_for_reporting() -> None:
    data = synthetic_dataset(1).model_dump(mode="json")
    data["citations"][0]["provenance"].update(verification_status="pending", verified_at=None)
    pending = Dataset.model_validate(data)
    dataset = synthetic_dataset(1)
    evaluation = evaluate(dataset, (lookup_bundle(dataset, [{"results": []}]),))
    with pytest.raises(ValueError):
        analyze(
            (evaluation,),
            AnalysisConfig(experiment="mutation-robustness", figure_formats=()),
            dataset=pending,
        )


@pytest.mark.parametrize(
    "update",
    [
        {"min_cluster_count": 1},
        {"max_collection_hours": 0},
        {"bootstrap_replicates": 0},
        {"figure_formats": ["svg", "svg"]},
        {"data_label": "observed"},
    ],
)
def test_invalid_analysis_configuration(update: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        AnalysisConfig.model_validate({"experiment": "mutation-robustness", **update})
