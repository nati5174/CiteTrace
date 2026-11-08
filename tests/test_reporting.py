"""Deterministic research-format output tests; all study data here is simulated."""

import csv
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from analysis_helpers import synthetic_study
from evaluation_helpers import lookup_bundle, synthetic_dataset, work

from citeprobe.analysis import analyze
from citeprobe.analysis_models import COVERAGE_LABEL, AnalysisConfig
from citeprobe.cli import main
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_models import EvaluationConfig
from citeprobe.figures import render_figures
from citeprobe.reporting import markdown_report, stable_json, table_documents

FIXTURE = Path(__file__).parent / "fixtures" / "part3-final-verification"


def forbidden_client(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("Reporting/evaluation must never construct a network client")


def test_complete_report_is_deterministic_in_all_figure_formats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    evaluation = tmp_path / "evaluation.json"
    assert (
        main(
            [
                "evaluate",
                str(FIXTURE / "lookups.json"),
                "--dataset",
                str(FIXTURE / "dataset.json"),
                "--identity-mappings",
                str(FIXTURE / "identity-mappings.json"),
                "--config",
                str(FIXTURE / "config.json"),
                "--output",
                str(evaluation),
            ]
        )
        == 0
    )
    config = tmp_path / "analysis-config.json"
    config.write_text(
        stable_json({"experiment": "mutation-robustness", "figure_formats": ["svg", "png", "pdf"]})
    )
    inputs = {
        path: path.read_bytes()
        for path in (evaluation, config, FIXTURE / "dataset.json", FIXTURE / "lookups.json")
    }
    for name in ("report-one", "report-two"):
        assert (
            main(
                [
                    "report",
                    str(evaluation),
                    "--experiment",
                    "mutation-robustness",
                    "--config",
                    str(config),
                    "--dataset",
                    str(FIXTURE / "dataset.json"),
                    "--lookup-bundles",
                    str(FIXTURE / "lookups.json"),
                    "--output-dir",
                    str(tmp_path / name),
                ]
            )
            == 0
        )
    first, second = tmp_path / "report-one", tmp_path / "report-two"
    left = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    right = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert left == right
    assert len([name for name in left if name.endswith((".svg", ".png", ".pdf"))]) == 12
    report = (first / "simulated/report.md").read_text(encoding="utf-8")
    assert "SIMULATED" in report and "DEMONSTRATION" in report
    assert "No empirical provider-performance conclusion" in report
    assert "undefined (identity_uncertainty)" in report
    assert "1/5" in report
    assert report.count("## ") == 10
    with (first / "simulated/tables/provider-comparison.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    recall = next(row for row in rows if row["metric"] == "recall_at_1")
    assert recall["value"] == "" and recall["lower_bound"] == "0.2"
    assert all(row["data_label"] == "simulated" for row in rows)
    reproduction = json.loads((first / "simulated/reproducibility.json").read_text())
    assert reproduction["software_versions"]["matplotlib"] != "not installed"
    assert reproduction["output_file_hashes"] and reproduction["analysis_config"]["seed"] == 0
    assert all(path.read_bytes() == content for path, content in inputs.items())
    assert (
        main(
            [
                "report",
                str(evaluation),
                "--experiment",
                "mutation-robustness",
                "--output-dir",
                str(first),
            ]
        )
        == 1
    )
    assert (
        main(
            [
                "report",
                str(evaluation),
                "--experiment",
                "mutation-robustness",
                "--output-dir",
                str(evaluation),
            ]
        )
        == 1
    )


def test_recent_preprint_wording_and_window_disclosure_everywhere(tmp_path: Path) -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [{"results": []}])
    evaluation = evaluate(
        dataset, (bundle,), config=EvaluationConfig(default_data_label="simulated")
    )
    config = AnalysisConfig(
        experiment="recent-preprints", max_collection_hours=72, figure_formats=("svg",)
    )
    report = analyze(
        (evaluation,),
        config,
        dataset=dataset,
        bundles=(bundle,),
        manifest=synthetic_study(dataset, (bundle,), hours=48),
    )[0]
    paths = render_figures(report, tmp_path / "figures")
    assert len(paths) == 4
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert COVERAGE_LABEL in text
        assert "does not establish" in text and "indexing latency" in text
        assert "N=1, T=1" in text
        assert "48 hours" in text and "72 hours" in text
    tables = table_documents(report)
    assert "cohort-coverage.csv" in tables and "mutation-robustness.csv" not in tables
    assert COVERAGE_LABEL in tables["cohort-coverage.csv"]
    markdown = markdown_report(report, paths)
    assert COVERAGE_LABEL in markdown and "48 hours" in markdown
    assert "72 hours" in markdown and "not a simultaneous snapshot" in markdown
    assert len(report.timings) == 1


def test_origins_have_separate_report_directories_and_cannot_be_relabelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = synthetic_dataset(2)
    from citeprobe.lookup_inputs import canonical_tasks, fingerprint

    tasks = canonical_tasks(dataset)
    bundles = tuple(lookup_bundle(dataset, [{"results": []}], tasks=(task,)) for task in tasks)
    evaluation = evaluate(
        dataset,
        bundles,
        config=EvaluationConfig(
            input_labels={
                fingerprint(bundle.model_dump(mode="json")): label
                for bundle, label in zip(bundles, ("simulated", "unknown"), strict=True)
            }
        ),
    )
    path = tmp_path / "input.json"
    path.write_text(evaluation.model_dump_json())
    config = tmp_path / "config.json"
    config.write_text(stable_json({"experiment": "mutation-robustness", "figure_formats": []}))
    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    target = tmp_path / "reports"
    assert (
        main(
            [
                "report",
                str(path),
                "--experiment",
                "mutation-robustness",
                "--config",
                str(config),
                "--output-dir",
                str(target),
            ]
        )
        == 0
    )
    assert (target / "simulated/report.md").exists()
    assert (target / "unknown/report.md").exists()
    assert not (target / "observed").exists()
    for label in ("simulated", "unknown"):
        data = json.loads((target / label / "analysis.json").read_text())
        assert all(row["data_label"] == label for row in data["lookups"])
    with pytest.raises(SystemExit):
        main(
            [
                "report",
                str(path),
                "--experiment",
                "mutation-robustness",
                "--data-label",
                "observed",
                "--output-dir",
                str(tmp_path / "invalid"),
            ]
        )


def test_cli_rejects_bad_inputs_and_cleans_staging(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    output = tmp_path / "report"
    config = tmp_path / "config.json"
    config.write_text(stable_json({"experiment": "mutation-robustness", "figure_formats": []}))
    assert (
        main(
            [
                "report",
                str(bad),
                "--experiment",
                "mutation-robustness",
                "--config",
                str(config),
                "--output-dir",
                str(output),
            ]
        )
        == 1
    )
    assert not output.exists()
    assert not list(tmp_path.glob(".citeprobe-report-*"))


def test_failure_only_report_states_performance_not_assessed() -> None:
    dataset = synthetic_dataset(1)
    bundle = lookup_bundle(dataset, [httpx.ConnectError("synthetic")])
    output = analyze(
        (evaluate(dataset, (bundle,)),),
        AnalysisConfig(experiment="mutation-robustness", figure_formats=()),
    )[0]
    text = markdown_report(output, [])
    assert output.report_kind == "diagnostic"
    assert "retrieval performance could not be assessed" in text
    assert "undefined (zero_denominator)" in text


def test_annotation_bounding_boxes_fit_figure_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: exact-undefined annotations used to extend beyond the right figure edge."""
    import importlib

    figure_class = importlib.import_module("matplotlib.figure").Figure
    original = figure_class.savefig

    def checked_savefig(figure: Any, *args: Any, **kwargs: Any) -> Any:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        for axes in figure.axes:
            for annotation in axes.texts:
                box = annotation.get_window_extent(renderer)
                assert box.x0 >= 0 and box.x1 <= figure.bbox.width
                assert box.y0 >= 0 and box.y1 <= figure.bbox.height
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(figure_class, "savefig", checked_savefig)
    dataset = synthetic_dataset(1)
    evaluation = evaluate(dataset, (lookup_bundle(dataset, [{"results": [work()]}]),))
    output = analyze((evaluation,), AnalysisConfig(experiment="mutation-robustness"))[0]
    render_figures(output, tmp_path / "figures")
