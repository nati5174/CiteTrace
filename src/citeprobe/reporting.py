"""Auditable Markdown, machine-readable tables and reproducibility manifests."""

import csv
import hashlib
import io
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from citeprobe.analysis_models import COVERAGE_LABEL, SCOPE_NOTE, AnalysisOutput
from citeprobe.evaluation import METRIC_DEFINITIONS
from citeprobe.figures import render_figures
from citeprobe.lookup_inputs import fingerprint


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def csv_document(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def software_versions() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for package in ("citeprobe", "pydantic", "matplotlib", "numpy", "pillow", "fonttools"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not installed"
    return result


def analysis_code_fingerprint() -> str:
    root = Path(__file__).parent
    files = (
        "analysis_models.py",
        "analysis_validation.py",
        "analysis.py",
        "uncertainty.py",
        "figures.py",
        "reporting.py",
        "report_cli.py",
        "evaluation.py",
    )
    return fingerprint({name: (root / name).read_text(encoding="utf-8") for name in files})


def table_documents(output: AnalysisOutput) -> dict[str, str]:
    measurement = (
        COVERAGE_LABEL
        if output.config.experiment == "recent-preprints"
        else "Metadata-mutation retrieval robustness"
    )
    fields = (
        "analysis_id",
        "data_label",
        "measurement",
        "scope_note",
        "panel_id",
        "scope",
        "provider",
        "strategy",
        "condition",
        "cohort",
        "lookup_count",
        "retrieval_lookup_count",
        "original_citation_count",
        "retrieval_original_citation_count",
        "metric",
        "numerator",
        "uncertain_count",
        "denominator",
        "value",
        "lower_bound",
        "upper_bound",
        "undefined_reason",
        "statistical_ci_lower",
        "statistical_ci_upper",
        "confidence_level",
        "cluster_count",
        "replicates",
        "invalid_replicates",
        "attempted_replicates",
        "valid_replicates",
        "ci_suppression_reason",
        "resampling_plan_id",
    )
    rows: list[dict[str, Any]] = []
    for panel in output.panels:
        group = panel.summary
        for name, metric in sorted(group.metrics.items()):
            interval = panel.intervals[name]
            rows.append(
                {
                    "analysis_id": output.analysis_id,
                    "data_label": output.data_label,
                    "measurement": measurement,
                    "scope_note": SCOPE_NOTE,
                    "panel_id": panel.panel_id,
                    "scope": panel.scope,
                    "provider": group.dimensions["provider"],
                    "strategy": group.dimensions["strategy"],
                    "condition": panel.condition,
                    "cohort": panel.cohort,
                    "lookup_count": group.lookup_count,
                    "retrieval_lookup_count": group.retrieval_lookup_count,
                    "original_citation_count": group.original_citation_count,
                    "retrieval_original_citation_count": group.retrieval_original_citation_count,
                    "metric": name,
                    **metric.model_dump(),
                    "statistical_ci_lower": interval.lower,
                    "statistical_ci_upper": interval.upper,
                    "confidence_level": interval.confidence_level,
                    "cluster_count": interval.cluster_count,
                    "replicates": interval.replicates,
                    "invalid_replicates": interval.invalid_replicates,
                    "attempted_replicates": interval.attempted_replicates,
                    "valid_replicates": interval.valid_replicates,
                    "ci_suppression_reason": interval.suppression_reason,
                    "resampling_plan_id": interval.resampling_plan_id,
                }
            )
    documents = {
        "provider-comparison.csv": csv_document(
            [row for row in rows if row["scope"] == "all"], fields
        ),
        "identifier-assisted.csv": csv_document(
            [row for row in rows if row["scope"] == "identifier_appendix"], fields
        ),
        "outcomes.csv": csv_document(
            [row for row in rows if row["metric"] not in {"recall_at_1", "recall_at_5"}], fields
        ),
    }
    if output.config.experiment == "recent-preprints":
        documents["cohort-coverage.csv"] = csv_document(
            [row for row in rows if row["scope"] == "all"], fields
        )
    else:
        documents["mutation-robustness.csv"] = csv_document(
            [row for row in rows if row["scope"] != "identifier_appendix"], fields
        )
    panels = {panel.panel_id: panel for panel in output.panels}
    comparisons: list[dict[str, Any]] = []
    for comparison in output.comparisons:
        left = panels[comparison.matched_left_panel_id or comparison.left_panel_id]
        right = panels[comparison.matched_right_panel_id or comparison.right_panel_id]
        for name in sorted(left.summary.metrics):
            record = {
                "analysis_id": output.analysis_id,
                "data_label": output.data_label,
                "measurement": measurement,
                "scope_note": SCOPE_NOTE,
                "comparison_id": comparison.comparison_id,
                "kind": comparison.comparison_kind,
                "full_sample_status": comparison.status,
                "paired_retrieval_sources": comparison.paired_retrieval_sources,
                "scope": "matched_eligible_source_subset"
                if comparison.matched_left_panel_id
                else "unmatched_descriptive",
                "shared_source_count": len(comparison.shared_source_ids),
                "matched_subset_paired": comparison.matched_left_panel_id is not None,
                "matched_source_count": len(left.source_ids)
                if comparison.matched_left_panel_id
                else 0,
                "left_only_source_count": len(comparison.left_only_source_ids),
                "right_only_source_count": len(comparison.right_only_source_ids),
                "metric": name,
            }
            for side, panel in (("left", left), ("right", right)):
                metric = panel.summary.metrics[name]
                record.update(
                    {
                        f"{side}_panel_id": panel.panel_id,
                        f"{side}_provider": panel.summary.dimensions["provider"],
                        f"{side}_condition": panel.condition,
                        f"{side}_lookup_count": panel.summary.lookup_count,
                        f"{side}_original_citation_count": panel.summary.original_citation_count,
                        **{f"{side}_{key}": value for key, value in metric.model_dump().items()},
                        f"{side}_resampling_plan_id": panel.intervals[name].resampling_plan_id,
                        f"{side}_statistical_ci_lower": panel.intervals[name].lower,
                        f"{side}_statistical_ci_upper": panel.intervals[name].upper,
                        f"{side}_ci_suppression_reason": panel.intervals[name].suppression_reason,
                    }
                )
            comparisons.append(record)
    comparison_fields = (
        "analysis_id",
        "data_label",
        "measurement",
        "scope_note",
        "comparison_id",
        "kind",
        "full_sample_status",
        "paired_retrieval_sources",
        "scope",
        "shared_source_count",
        "matched_subset_paired",
        "matched_source_count",
        "left_only_source_count",
        "right_only_source_count",
        "metric",
    )
    side_fields = tuple(
        f"{side}_{name}"
        for side in ("left", "right")
        for name in (
            "panel_id",
            "provider",
            "condition",
            "lookup_count",
            "original_citation_count",
            "numerator",
            "uncertain_count",
            "denominator",
            "value",
            "lower_bound",
            "upper_bound",
            "undefined_reason",
            "resampling_plan_id",
            "statistical_ci_lower",
            "statistical_ci_upper",
            "ci_suppression_reason",
        )
    )
    documents["matched-source-comparison.csv"] = csv_document(
        comparisons, comparison_fields + side_fields
    )
    exclusions = [
        {"data_label": output.data_label, **item.model_dump()} for item in output.exclusions
    ]
    documents["exclusions.csv"] = csv_document(
        exclusions, ("data_label", "citation_id", "lookup_id", "reason")
    )
    documents["lookup-timings.csv"] = csv_document(
        [
            {
                "data_label": output.data_label,
                "lookup_id": timing.lookup_id,
                "started_at": timing.started_at.isoformat(),
                "finished_at": timing.finished_at.isoformat(),
            }
            for timing in output.timings
        ],
        ("data_label", "lookup_id", "started_at", "finished_at"),
    )
    if output.config.experiment == "mutation-robustness":
        canonical = {
            (row.original_citation_id, row.provider): row
            for row in output.lookups
            if row.source_kind == "canonical" and row.strategy == "metadata"
        }
        main_ids = {
            lookup for panel in output.panels if panel.scope == "all" for lookup in panel.lookup_ids
        }
        baseline_rows = []
        for row in output.lookups:
            if row.source_kind != "mutation":
                continue
            baseline = canonical.get((row.original_citation_id, row.provider))
            baseline_rows.append(
                {
                    "data_label": output.data_label,
                    "provider": row.provider,
                    "original_citation_id": row.original_citation_id,
                    "mutation_type": row.mutation_type,
                    "mutation_lookup_id": row.lookup_id,
                    "included_main": row.lookup_id in main_ids,
                    "mutation_retrieval_eligible": row.retrieval_eligible,
                    "baseline_lookup_id": baseline.lookup_id if baseline else None,
                    "baseline_outcome": baseline.outcome if baseline else "missing",
                    "baseline_included_main": bool(baseline and baseline.lookup_id in main_ids),
                    "baseline_retrieval_eligible": bool(baseline and baseline.retrieval_eligible),
                }
            )
        documents["baseline-availability.csv"] = csv_document(
            baseline_rows,
            (
                "data_label",
                "provider",
                "original_citation_id",
                "mutation_type",
                "mutation_lookup_id",
                "included_main",
                "mutation_retrieval_eligible",
                "baseline_lookup_id",
                "baseline_outcome",
                "baseline_included_main",
                "baseline_retrieval_eligible",
            ),
        )
    return documents


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def markdown_report(output: AnalysisOutput, figure_paths: list[Path]) -> str:
    title = (
        COVERAGE_LABEL
        if output.config.experiment == "recent-preprints"
        else "Metadata-mutation retrieval robustness"
    )
    label = f"{output.data_label.upper()} — {output.report_kind.upper()}"
    main = [panel for panel in output.panels if panel.scope == "all"]
    retained_ids = {identifier for panel in main for identifier in panel.lookup_ids}
    eligible_count = sum(
        row.retrieval_eligible for row in output.lookups if row.lookup_id in retained_ids
    )
    sections = [
        f"# {title}\n\n**{label}**\n",
        "## Abstract\n\n"
        + (
            "This empirical descriptive analysis summarizes explicitly observed, "
            "provenance-checked lookup results. "
            if output.report_kind == "empirical"
            else "This demonstration/diagnostic artifact does not establish empirical "
            "provider-performance findings. "
        )
        + f"The selected main experiment contains {len(retained_ids)} recorded lookups "
        f"and {eligible_count} retrieval-eligible lookups.\n\n" + SCOPE_NOTE,
        "## Research questions\n\n"
        + (
            "How does verified retrieval coverage under the recorded search strategy vary "
            "across verified first-public preprint age cohorts?"
            if output.config.experiment == "recent-preprints"
            else "How do recorded metadata-only retrieval outcomes vary across controlled "
            "mutation types and available canonical baselines?"
        ),
        "## Dataset construction and verification methodology\n\n"
        f"Dataset fingerprint: `{output.dataset_fingerprint}`. "
        f"Data origin: **{output.data_label}**. "
        "Identity judgments and ground-truth references are inherited from Part 3; no "
        "identity rematching is performed. "
        "Provenance and origin labels are curator assertions, not cryptographic authentication.",
    ]
    if output.manifest:
        sections[-1] += (
            f"\n\nSampling: {markdown_cell(output.manifest.sampling_method)}"
            f"\n\nVerification: {markdown_cell(output.manifest.verification_method)}"
        )
    else:
        sections[-1] += (
            "\n\nSampling/verification study metadata was not supplied; empirical "
            "interpretation is unavailable."
        )
    sections.append(
        "## Provider resolution methodology\n\n"
        "Main comparisons use the recorded metadata-only strategy and original provider rankings. "
        "Identifier-assisted canonical lookups, if any, appear only in "
        "`tables/identifier-assisted.csv`. "
        "Lookup configuration fingerprints and actual source timestamps are retained in "
        "the input lineage and `analysis.json`."
    )
    if output.manifest:
        hours = (
            output.manifest.collection_finished_at - output.manifest.collection_started_at
        ).total_seconds() / 3600
        sections[-1] += (
            f"\n\nDeclared collection: {output.manifest.collection_started_at.isoformat()} to "
            f"{output.manifest.collection_finished_at.isoformat()} ({hours:g} hours). "
            f"Configured Experiment A limit: {output.config.max_collection_hours:g} hours. "
            f"UTC cohort reference date: {output.manifest.reference_date or 'not applicable'}. "
            "Actual per-lookup timestamps are preserved separately. No timestamps are "
            "inferred from citation years."
        )
    sections.append(
        "## Metric definitions\n\n"
        + "\n".join(
            f"- **{name}**: {definition}" for name, definition in METRIC_DEFINITIONS.items()
        )
        + "\n\nUndefined metrics remain null. "
        "Evidence bounds are not statistical confidence intervals."
    )
    lines = [
        "## Experimental results",
        "",
        title,
        "",
        "| Provider | Condition | Cohort | T | N | Papers / eligible papers | Metric | "
        "Confirmed / denominator | Uncertain | Exact | Evidence bounds |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |",
    ]
    for panel in main:
        group = panel.summary
        for name in (
            "recall_at_1",
            "recall_at_5",
            "incorrect_match_rate",
            "unresolved_rate",
            "identity_undetermined_rate",
            "api_error_rate",
        ):
            metric = group.metrics[name]
            exact = (
                f"{metric.value:.3f}"
                if metric.value is not None
                else f"undefined ({metric.undefined_reason})"
            )
            bounds = (
                f"[{metric.lower_bound:.3f}, {metric.upper_bound:.3f}]"
                if metric.lower_bound is not None
                else "undefined"
            )
            cells = [
                str(group.dimensions["provider"]),
                panel.condition,
                panel.cohort or "not assigned",
                str(group.lookup_count),
                str(group.retrieval_lookup_count),
                f"{group.original_citation_count} / {group.retrieval_original_citation_count}",
                name,
                f"{metric.numerator}/{metric.denominator}",
                str(metric.uncertain_count),
                exact,
                bounds,
            ]
            lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")
    lines += [
        "",
        "All-source and matched-source subsets are distinct. "
        "`tables/matched-source-comparison.csv` records "
        "shared/unmatched paper inventories; no paired inference is implied for differing "
        "source sets.",
    ]
    for figure in figure_paths:
        lines += ["", f"![{markdown_cell(title)} — {output.data_label}](figures/{figure.name})"]
    sections.append("\n".join(lines))
    sections.append(
        "## Uncertainty and limitations\n\n"
        f"Source-cluster bootstrap {'enabled' if output.config.bootstrap else 'disabled'}; "
        f"seed={output.config.seed}, replicates={output.config.bootstrap_replicates}, "
        f"confidence={output.config.confidence_level:g}, "
        f"minimum eligible source clusters={output.config.min_cluster_count}. "
        "The unit is original_citation_id. Sampled clusters retain all associated "
        "observations and multiplicity; "
        "identical matched source sets share draws across providers and conditions. "
        "Unmatched full samples are descriptive comparisons. "
        "Intervals are suppressed for small samples, undefined exact metrics, undefined "
        "replicates, and degenerate distributions. "
        "See analysis.json and table CI fields for every suppression reason. The cluster "
        "threshold is an operational safeguard, not a validity guarantee. "
        "No identity-bound midpoint is imputed. No significance tests are performed.\n\n"
        + (
            "\n".join(f"- {warning}" for warning in output.warnings)
            or "- No additional input-provenance limitations detected."
        )
    )
    sections.append(
        "## Threats to validity\n\n"
        "Convenience sampling, provider scope differences, metadata search semantics, "
        "incomplete identity evidence, "
        "API availability, collection-window width, and unequal mutation counts can affect "
        "results. "
        "Source clusters are assumed independent; repeated mutations within a paper are "
        "not independent observations. "
        "Bootstrap intervals do not repair selection bias or correlated papers sharing "
        "different canonical IDs. " + SCOPE_NOTE
    )
    sections.append(
        "## Reproducibility instructions\n\n"
        f"Analysis ID: `{output.analysis_id}`. Run `citeprobe report <evaluation.json> "
        f"--experiment {output.config.experiment} "
        "--output-dir <new-directory>` with the study/dataset/lookup/config inputs listed "
        "by hash in reproducibility.json. "
        "That manifest records the complete analysis configuration, software versions, and "
        "artifact hashes. "
        "Identical inputs/configuration and plotting environment produce deterministic "
        "outputs; cross-platform figure byte identity is not promised. "
        "The command performs no live requests. For cluster methodology see "
        "[Cameron and Miller "
        "(2015)](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015.pdf)."
    )
    sections.append(
        "## Conclusions\n\n"
        + (
            "The tables describe the supplied observed retrieval outcomes under the "
            "recorded study design. "
            "They establish neither database absence, indexing latency, fabricated "
            "citations, nor statistical significance."
            if output.report_kind == "empirical"
            else "No empirical provider-performance conclusion is supported by this "
            "demonstration/diagnostic report. "
            "If inputs contain only operational failures, retrieval performance could not "
            "be assessed."
        )
    )
    return "\n\n".join(sections) + "\n"


def write_report(output: AnalysisOutput, directory: Path, input_hashes: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "tables").mkdir()
    (directory / "analysis.json").write_text(
        stable_json(output.model_dump(mode="json")), encoding="utf-8", newline=""
    )
    for name, content in table_documents(output).items():
        (directory / "tables" / name).write_text(content, encoding="utf-8", newline="")
    figure_paths = render_figures(output, directory / "figures")
    (directory / "report.md").write_text(
        markdown_report(output, figure_paths), encoding="utf-8", newline=""
    )
    hashes = {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    metadata = {
        "schema_version": "1.0",
        "analysis_version": "1",
        "analysis_id": output.analysis_id,
        "data_label": output.data_label,
        "report_kind": output.report_kind,
        "analysis_config": output.config.model_dump(mode="json"),
        "input_file_hashes": input_hashes,
        "evaluation_ids": output.evaluation_ids,
        "dataset_fingerprint": output.dataset_fingerprint,
        "analysis_code_fingerprint": analysis_code_fingerprint(),
        "software_versions": software_versions(),
        "font": "DejaVu Sans (Matplotlib bundled)",
        "output_file_hashes": hashes,
        "resampling_unit": "original_citation_id",
        "no_significance_tests": True,
    }
    (directory / "reproducibility.json").write_text(
        stable_json(metadata), encoding="utf-8", newline=""
    )
