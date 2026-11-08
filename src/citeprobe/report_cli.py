"""Offline report orchestration with a new output directory and origin-isolated bundles."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from citeprobe.analysis import analyze
from citeprobe.analysis_models import AnalysisConfig, StudyManifest
from citeprobe.dataset import load_dataset
from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.figures import plot_modules
from citeprobe.lookup_inputs import fingerprint
from citeprobe.reporting import (
    analysis_code_fingerprint,
    software_versions,
    stable_json,
    write_report,
)
from citeprobe.resolution_models import LookupBundle


def add_report_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    command = commands.add_parser(
        "report", help="Analyze Part 3 artifacts and write research/demonstration reports offline"
    )
    command.add_argument("evaluations", nargs="+", type=Path)
    command.add_argument(
        "--experiment", required=True, choices=("recent-preprints", "mutation-robustness")
    )
    command.add_argument("--study-manifest", type=Path)
    command.add_argument("--dataset", type=Path)
    command.add_argument("--lookup-bundles", nargs="+", type=Path, default=[])
    command.add_argument("--config", type=Path)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--max-collection-hours", type=float)
    command.add_argument("--bootstrap", action="store_true", default=None)
    command.add_argument("--seed", type=int)
    command.add_argument("--bootstrap-replicates", type=int)
    command.add_argument("--figure-formats", nargs="+", choices=("svg", "png", "pdf"))


def run_report(args: argparse.Namespace) -> int:
    sources = [*args.evaluations, *args.lookup_bundles]
    sources.extend(path for path in (args.config, args.dataset, args.study_manifest) if path)
    output = args.output_dir.resolve()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise ValueError("Report output directory must be new")
    if any(output == source.resolve() or output in source.resolve().parents for source in sources):
        raise ValueError("Report output must not contain or replace input files")
    data = (
        AnalysisConfig.model_validate_json(args.config.read_text(encoding="utf-8")).model_dump()
        if args.config
        else {}
    )
    if data and data["experiment"] != args.experiment:
        raise ValueError("CLI experiment conflicts with analysis configuration")
    data["experiment"] = args.experiment
    for key in (
        "max_collection_hours",
        "bootstrap",
        "seed",
        "bootstrap_replicates",
        "figure_formats",
    ):
        value = getattr(args, key)
        if value is not None:
            data[key] = value
    config = AnalysisConfig.model_validate(data)
    if config.figure_formats:
        plot_modules()  # Fail before creating any output if the optional dependency is missing.
    evaluations = tuple(
        EvaluationOutput.model_validate_json(path.read_bytes()) for path in args.evaluations
    )
    bundles = tuple(
        LookupBundle.model_validate_json(path.read_bytes()) for path in args.lookup_bundles
    )
    refs = {ref.bundle_id: ref for evaluation in evaluations for ref in evaluation.inputs}
    for path, bundle in zip(args.lookup_bundles, bundles, strict=True):
        ref = refs.get(fingerprint(bundle.model_dump(mode="json")))
        if (
            ref
            and ref.file_sha256
            and ref.file_sha256 != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError("Original lookup file bytes differ from Part 3 provenance")
    dataset = load_dataset(args.dataset) if args.dataset else None
    manifest = (
        StudyManifest.model_validate_json(args.study_manifest.read_bytes())
        if args.study_manifest
        else None
    )
    reports = analyze(evaluations, config, dataset=dataset, bundles=bundles, manifest=manifest)
    if not reports:
        raise ValueError("Evaluation artifacts contain no origin-labeled input bundles")
    input_hashes = {
        f"evaluation:{evaluation.evaluation_id}": hashlib.sha256(path.read_bytes()).hexdigest()
        for path, evaluation in zip(args.evaluations, evaluations, strict=True)
    }
    for path, bundle in zip(args.lookup_bundles, bundles, strict=True):
        input_hashes[f"lookup_bundle:{fingerprint(bundle.model_dump(mode='json'))}"] = (
            hashlib.sha256(path.read_bytes()).hexdigest()
        )
    for role, path in (
        ("dataset", args.dataset),
        ("study_manifest", args.study_manifest),
        ("analysis_config_source", args.config),
    ):
        if path:
            input_hashes[role] = hashlib.sha256(path.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".citeprobe-report-", dir=output.parent) as temporary:
        stage = Path(temporary)
        for report in reports:
            write_report(report, stage / report.data_label, input_hashes)
        index = {
            "schema_version": "1.0",
            "analysis_config": config.model_dump(mode="json"),
            "analysis_code_fingerprint": analysis_code_fingerprint(),
            "software_versions": software_versions(),
            "input_file_hashes": input_hashes,
            "reports": [
                {
                    "data_label": report.data_label,
                    "report_kind": report.report_kind,
                    "analysis_id": report.analysis_id,
                    "report_path": f"{report.data_label}/report.md",
                }
                for report in reports
            ],
            "origin_policy": "Observed, simulated and unknown data are never pooled or relabeled.",
        }
        (stage / "reproducibility.json").write_text(
            stable_json(index), encoding="utf-8", newline=""
        )
        if output.exists() or args.output_dir.is_symlink():
            raise ValueError("Report output directory was created concurrently; refusing overwrite")
        stage.rename(output)
    for report in reports:
        print(
            f"{report.data_label}: {report.report_kind} report at "
            f"{args.output_dir / report.data_label / 'report.md'}"
        )
    return 0
