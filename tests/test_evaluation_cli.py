"""CLI and serialization tests operate on labeled synthetic files and block networking."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.cli import main
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_io import csv_text, write_evaluation
from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.lookup_inputs import fingerprint, mutation_tasks
from citeprobe.mutations import generate_mutations


def test_cli_json_csv_are_deterministic_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": [work("10.1234/fixture-0")]}])
    source = tmp_path / "dataset.json"
    saved = tmp_path / "lookups.json"
    source.write_text(dataset.model_dump_json(), encoding="utf-8")
    saved.write_text(bundle.model_dump_json(), encoding="utf-8")
    before = source.read_bytes(), saved.read_bytes()

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Offline evaluation must not construct network clients")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    for filename in ("first.json", "second.json"):
        assert (
            main(
                [
                    "evaluate",
                    str(saved),
                    "--dataset",
                    str(source),
                    "--data-label",
                    "simulated",
                    "--output",
                    str(tmp_path / filename),
                ]
            )
            == 0
        )
    first = tmp_path / "first.json"
    output = EvaluationOutput.model_validate_json(first.read_text())
    assert output.lookups[0].data_label == "simulated"
    assert not any(group.empirical_data_eligible for group in output.groups)
    assert first.read_bytes() == (tmp_path / "second.json").read_bytes()
    assert first.with_suffix(".csv").read_bytes() == (tmp_path / "second.csv").read_bytes()
    assert output.inputs[0].file_sha256 is not None
    rows = list(csv.DictReader(io.StringIO(first.with_suffix(".csv").read_text())))
    assert rows and all(row["data_label"] == "simulated" for row in rows)
    assert all(row["evaluation_id"] == output.evaluation_id for row in rows)
    assert (source.read_bytes(), saved.read_bytes()) == before
    assert main(["evaluate", str(saved), "--dataset", str(source), "--output", str(first)]) == 1
    assert main(["evaluate", str(saved), "--dataset", str(source), "--output", str(source)]) == 1
    assert (
        main(
            [
                "evaluate",
                str(saved),
                "--dataset",
                str(source),
                "--output",
                str(tmp_path / "bad.json"),
                "--csv-output",
                str(saved),
            ]
        )
        == 1
    )
    bad = tmp_path / "malformed.json"
    bad.write_text("{}")
    assert (
        main(
            [
                "evaluate",
                str(bad),
                "--dataset",
                str(source),
                "--output",
                str(tmp_path / "invalid.json"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "invalid.json").exists()


def test_mutation_cli_and_explicit_labels(tmp_path: Path) -> None:
    dataset = synthetic_dataset(1)
    batch = generate_mutations(dataset)
    bundle = lookup_bundle(
        dataset,
        [{"results": []}],
        tasks=mutation_tasks(dataset, batch)[:1],
        input_hash=fingerprint(batch.model_dump(mode="json", exclude={"generated_at"})),
    )
    source, mutation_file, saved = [
        tmp_path / name for name in ("data.json", "mutations.json", "lookups.json")
    ]
    for path, model in ((source, dataset), (mutation_file, batch), (saved, bundle)):
        path.write_text(model.model_dump_json())
    output = tmp_path / "evaluation.json"
    assert main(["evaluate", str(saved), "--dataset", str(source), "--output", str(output)]) == 1
    assert (
        main(
            [
                "evaluate",
                str(saved),
                "--dataset",
                str(source),
                "--mutations",
                str(mutation_file),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        EvaluationOutput.model_validate_json(output.read_text()).lookups[0].data_label == "unknown"
    )


def test_csv_null_values_and_output_alias(tmp_path: Path) -> None:
    dataset = synthetic_dataset(1)
    output = evaluate(dataset, (lookup_bundle(dataset, [{"results": [work()]}]),))
    rows = list(csv.DictReader(io.StringIO(csv_text(output))))
    recall = next(row for row in rows if row["metric"] == "recall_at_1")
    assert recall["value"] == "" and recall["undefined_reason"] == "identity_uncertainty"
    target = tmp_path / "evaluation.json"
    with pytest.raises(ValueError):
        write_evaluation(output, target, target, [])
    assert not target.exists()
    source = tmp_path / "source.json"
    source.write_text("original")
    alias = tmp_path / "alias.json"
    alias.hardlink_to(source)
    with pytest.raises(ValueError):
        write_evaluation(output, alias, tmp_path / "result.csv", [source])
    assert source.read_text() == "original"


def test_explicit_observed_label_switch_is_required(tmp_path: Path) -> None:
    """Exercise label assertions with synthetic files; this is not an observed experiment."""
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    source, saved, output = [tmp_path / name for name in ("data.json", "bundle.json", "eval.json")]
    source.write_text(dataset.model_dump_json())
    saved.write_text(bundle.model_dump_json())
    assert (
        main(
            [
                "evaluate",
                str(saved),
                "--dataset",
                str(source),
                "--data-label",
                "observed",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    recorded = EvaluationOutput.model_validate_json(output.read_text())
    assert all(
        group.dimensions["data_label"] == "observed" and group.empirical_data_eligible
        for group in recorded.groups
    )


def test_failed_second_output_reservation_cleans_only_its_own_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = synthetic_dataset(1)
    output = evaluate(dataset, (lookup_bundle(dataset, [{"results": []}]),))
    json_path, csv_path = tmp_path / "output.json", tmp_path / "output.csv"
    original_open = Path.open

    def fail_csv(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == csv_path:
            raise PermissionError("Synthetic write error")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_csv)
    with pytest.raises(PermissionError):
        write_evaluation(output, json_path, csv_path, [])
    assert not json_path.exists() and not csv_path.exists()


def test_cli_loads_configuration_and_verified_identity_mappings(tmp_path: Path) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": [work("10.1234/alias")]}])
    sources = {
        "data.json": dataset.model_dump(mode="json"),
        "bundle.json": bundle.model_dump(mode="json"),
        "config.json": {"default_data_label": "simulated", "cohorts": {"fixture-0": "toy"}},
        "mappings.json": {
            "dataset_version": dataset.dataset_version,
            "mappings": [
                {
                    "citation_id": "fixture-0",
                    "relation": "same_work",
                    "identifiers": [{"namespace": "doi", "value": "10.1234/alias"}],
                    "provenance": dataset.citations[0].provenance.model_dump(mode="json"),
                }
            ],
        },
    }
    for filename, data in sources.items():
        (tmp_path / filename).write_text(json.dumps(data), encoding="utf-8")
    assert (
        main(
            [
                "evaluate",
                str(tmp_path / "bundle.json"),
                "--dataset",
                str(tmp_path / "data.json"),
                "--config",
                str(tmp_path / "config.json"),
                "--identity-mappings",
                str(tmp_path / "mappings.json"),
                "--output",
                str(tmp_path / "evaluation.json"),
            ]
        )
        == 0
    )
    output = EvaluationOutput.model_validate_json((tmp_path / "evaluation.json").read_text())
    assert output.lookups[0].rank_one_judgment == "CORRECT"
    assert output.lookups[0].data_label == "simulated" and output.lookups[0].cohort == "toy"


def test_json_canonicalizes_dictionary_order(tmp_path: Path) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    output = evaluate(dataset, (bundle,))
    data = output.model_dump(mode="json")
    data["metric_definitions"] = dict(reversed(list(data["metric_definitions"].items())))
    reordered = EvaluationOutput.model_validate(data)
    write_evaluation(output, tmp_path / "one.json", tmp_path / "one.csv", [])
    write_evaluation(reordered, tmp_path / "two.json", tmp_path / "two.csv", [])
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
