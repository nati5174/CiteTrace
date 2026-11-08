"""Six-case acceptance fixture. Every identity/provenance event is simulated."""

import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.cli import main
from citeprobe.evaluation_models import EvaluationConfig, EvaluationOutput, IdentityMappings
from citeprobe.models import Dataset
from citeprobe.resolution_models import LookupBundle

# Independent hand calculation, fixed before running the evaluator:
# T=6; N=5. H1=1, M1=3, U1=1. H5=2, M5=2, U5=1.
# I1=2 (the rank-three case's first candidate and the incorrect-only case).
# Empty=1; undetermined top-one identity=1; connection failures=1.
EXPECTED: dict[str, Any] = {
    "data_label": "simulated",
    "total_lookups": 6,
    "retrieval_lookups": 5,
    "metrics": {
        "recall_at_1": {
            "numerator": 1,
            "uncertain_count": 1,
            "denominator": 5,
            "value": None,
            "lower_bound": 0.2,
            "upper_bound": 0.4,
        },
        "recall_at_5": {
            "numerator": 2,
            "uncertain_count": 1,
            "denominator": 5,
            "value": None,
            "lower_bound": 0.4,
            "upper_bound": 0.6,
        },
        "incorrect_match_rate": {
            "numerator": 2,
            "uncertain_count": 1,
            "denominator": 5,
            "value": None,
            "lower_bound": 0.4,
            "upper_bound": 0.6,
        },
        "unresolved_rate": {
            "numerator": 1,
            "uncertain_count": 0,
            "denominator": 5,
            "value": 0.2,
            "lower_bound": 0.2,
            "upper_bound": 0.2,
        },
        "identity_undetermined_rate": {
            "numerator": 1,
            "uncertain_count": 0,
            "denominator": 5,
            "value": 0.2,
            "lower_bound": 0.2,
            "upper_bound": 0.2,
        },
        "api_error_rate": {
            "numerator": 1,
            "uncertain_count": 0,
            "denominator": 6,
            "value": 1 / 6,
            "lower_bound": 1 / 6,
            "upper_bound": 1 / 6,
        },
        "provider_error_rate": {
            "numerator": 1,
            "uncertain_count": 0,
            "denominator": 6,
            "value": 1 / 6,
            "lower_bound": 1 / 6,
            "upper_bound": 1 / 6,
        },
    },
    "cases": {
        "fixture-0": {
            "description": "Correct at rank one",
            "outcome": "FOUND",
            "recall_at_1": "HIT",
            "recall_at_5": "HIT",
            "judgments": ["CORRECT"],
            "ranks": [1],
        },
        "fixture-1": {
            "description": "Correct at rank three, confirmed incorrect at ranks one/two",
            "outcome": "FOUND",
            "recall_at_1": "MISS",
            "recall_at_5": "HIT",
            "judgments": ["INCORRECT", "INCORRECT", "CORRECT"],
            "ranks": [1, 2, 3],
        },
        "fixture-2": {
            "description": "Confirmed incorrect at rank one",
            "outcome": "FOUND",
            "recall_at_1": "MISS",
            "recall_at_5": "MISS",
            "judgments": ["INCORRECT"],
            "ranks": [1],
        },
        "fixture-3": {
            "description": "Undetermined identity",
            "outcome": "FOUND",
            "recall_at_1": "UNDETERMINED",
            "recall_at_5": "UNDETERMINED",
            "judgments": ["UNDETERMINED"],
            "ranks": [1],
        },
        "fixture-4": {
            "description": "Valid empty retrieval",
            "outcome": "NOT_FOUND",
            "recall_at_1": "MISS",
            "recall_at_5": "MISS",
            "judgments": [],
            "ranks": [],
        },
        "fixture-5": {
            "description": "Simulated connection failure",
            "outcome": "API_ERROR",
            "recall_at_1": "EXCLUDED",
            "recall_at_5": "EXCLUDED",
            "judgments": [],
            "ranks": [],
        },
    },
}


def write_fixture(directory: Path) -> None:
    """Construct deterministic valid Part 1/2 files through the existing mock transport."""
    directory.mkdir(parents=True, exist_ok=True)
    # Expectations are written before generating any lookup/evaluation result.
    (directory / "expected.json").write_text(
        json.dumps(EXPECTED, indent=2) + "\n", encoding="utf-8"
    )
    dataset = synthetic_dataset(6)
    mappings = IdentityMappings.model_validate(
        {
            "dataset_version": dataset.dataset_version,
            "mappings": [
                {
                    "citation_id": citation_id,
                    "relation": "different_work",
                    "identifiers": [{"namespace": "doi", "value": doi} for doi in identifiers],
                    "provenance": dataset.citations[int(citation_id[-1])].provenance.model_dump(
                        mode="json"
                    ),
                }
                for citation_id, identifiers in (
                    ("fixture-1", ("10.1234/negative-a", "10.1234/negative-b")),
                    ("fixture-2", ("10.1234/negative-c",)),
                )
            ],
        }
    )
    responses: list[Any] = [
        {"results": [work("10.1234/fixture-0", identifier="W101")]},
        {
            "results": [
                work("10.1234/negative-a", identifier="W201"),
                work("10.1234/negative-b", identifier="W202"),
                work("10.1234/fixture-1", identifier="W203"),
            ]
        },
        {"results": [work("10.1234/negative-c", identifier="W301")]},
        {"results": [work(identifier="W401")]},
        {"results": []},
        httpx.ConnectError("Simulated connection failure; no live request"),
    ]
    # Deliberately nonmonotonic scores detect accidental local reranking.
    responses[1]["results"][0]["relevance_score"] = 1.0
    responses[1]["results"][1]["relevance_score"] = 99.0
    responses[1]["results"][2]["relevance_score"] = 7.0
    bundle = lookup_bundle(dataset, responses)
    config = EvaluationConfig(default_data_label="simulated")
    for filename, model in (
        ("dataset.json", dataset),
        ("identity-mappings.json", mappings),
        ("lookups.json", bundle),
        ("config.json", config),
    ):
        (directory / filename).write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def verify_fixture(directory: Path, output_directory: Path) -> dict[str, Any]:
    """Exercise CLI validation unchanged and compare every case/count/CSV field."""
    output_directory.mkdir(parents=True, exist_ok=True)
    expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    inputs = [
        directory / name
        for name in (
            "dataset.json",
            "identity-mappings.json",
            "lookups.json",
            "config.json",
            "expected.json",
        )
    ]
    before = {path: path.read_bytes() for path in inputs}
    Dataset.model_validate_json(inputs[0].read_bytes())
    IdentityMappings.model_validate_json(inputs[1].read_bytes())
    bundle = LookupBundle.model_validate_json(inputs[2].read_bytes())
    assert (
        EvaluationConfig.model_validate_json(inputs[3].read_bytes()).default_data_label
        == "simulated"
    )
    outputs = [output_directory / name for name in ("evaluation-a.json", "evaluation-b.json")]
    for output_path in outputs:
        assert (
            main(
                [
                    "evaluate",
                    str(directory / "lookups.json"),
                    "--dataset",
                    str(directory / "dataset.json"),
                    "--identity-mappings",
                    str(directory / "identity-mappings.json"),
                    "--config",
                    str(directory / "config.json"),
                    "--output",
                    str(output_path),
                ]
            )
            == 0
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert (
        outputs[0].with_suffix(".csv").read_bytes() == outputs[1].with_suffix(".csv").read_bytes()
    )
    output = EvaluationOutput.model_validate_json(outputs[0].read_bytes())
    group = next(
        group
        for group in output.groups
        if group.dimensions
        == {
            "data_label": "simulated",
            "provider": "openalex",
            "strategy": "metadata",
        }
    )
    assert group.lookup_count == expected["total_lookups"]
    assert group.retrieval_lookup_count == expected["retrieval_lookups"]
    actual_metrics: dict[str, Any] = {}
    for name, fields in expected["metrics"].items():
        actual = group.metrics[name].model_dump()
        for key, value in fields.items():
            assert actual[key] == value, (name, key, actual[key], value)
        reason = "identity_uncertainty" if fields["uncertain_count"] else None
        assert actual["undefined_reason"] == reason
        actual_metrics[name] = actual
    by_source = {row.source_id: row for row in output.lookups}
    original_results = {row.source_id: row for row in bundle.results}
    for source_id, case in expected["cases"].items():
        row = by_source[source_id]
        assert row.outcome == case["outcome"]
        assert row.recall_at_1 == case["recall_at_1"]
        assert row.recall_at_5 == case["recall_at_5"]
        assert [j.judgment for j in row.candidates] == case["judgments"]
        assert [j.candidate.provider_rank for j in row.candidates] == case["ranks"]
        assert tuple(j.candidate for j in row.candidates) == original_results[source_id].candidates
        assert row.retrieval_eligible == (source_id != "fixture-5")
    assert [j.candidate.ranking["relevance_score"] for j in by_source["fixture-1"].candidates] == [
        1,
        99,
        7,
    ]
    failure = original_results["fixture-5"]
    assert failure.response_status is None and failure.attempts[0].diagnostic == "Transport failure"
    assert not by_source["fixture-4"].candidates and not by_source["fixture-5"].candidates
    assert all(row.data_label == "simulated" for row in output.lookups)
    assert all(item.data_label == "simulated" for item in output.inputs)
    assert all(
        group.dimensions["data_label"] == "simulated" and not group.empirical_data_eligible
        for group in output.groups
    )
    with outputs[0].with_suffix(".csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    for csv_row in csv_rows:
        assert (
            csv_row["data_label"] == "simulated" and csv_row["empirical_data_eligible"] == "False"
        )
    base_rows = {
        row["metric"]: row for row in csv_rows if row["grouping"] == "data_label,provider,strategy"
    }
    for name, fields in expected["metrics"].items():
        csv_row = base_rows[name]
        for key, value in fields.items():
            assert csv_row[key] == ("" if value is None else str(value)), (name, key)
    assert all(path.read_bytes() == content for path, content in before.items())
    return {
        "data_label": "simulated",
        "cases_passed": 6,
        "deterministic_json": True,
        "deterministic_csv": True,
        "inputs_unchanged": True,
        "actual_metrics": actual_metrics,
    }


def test_six_case_final_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Fixture creation uses MockTransport; evaluation itself may not even create a client.
    directory = tmp_path / "fixture"
    write_fixture(directory)
    committed = Path(__file__).parent / "fixtures" / "part3-final-verification"
    for path in directory.iterdir():
        assert path.read_bytes() == (committed / path.name).read_bytes()

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Final evaluation must be offline")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    result = verify_fixture(committed, tmp_path / "evaluation")
    assert result["cases_passed"] == 6
