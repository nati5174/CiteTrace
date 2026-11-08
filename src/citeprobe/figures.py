"""Headless deterministic figures from validated analysis panels, not new judgments."""

import importlib
import textwrap
from pathlib import Path
from typing import Any

from citeprobe.analysis_models import COVERAGE_LABEL, SCOPE_NOTE, AnalysisOutput


def plot_modules() -> tuple[Any, Any]:
    try:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        pyplot = importlib.import_module("matplotlib.pyplot")
    except ImportError as error:
        raise ValueError("Figure generation requires: pip install 'citeprobe[report]'") from error
    return matplotlib, pyplot


def render_figures(output: AnalysisOutput, directory: Path) -> list[Path]:
    if not output.config.figure_formats:
        return []
    matplotlib, plt = plot_modules()
    directory.mkdir(parents=True, exist_ok=False)
    panels = sorted(
        [p for p in output.panels if p.scope == "all"],
        key=lambda p: (p.cohort or "", str(p.summary.dimensions["provider"]), p.condition),
    )
    provider_panels = [
        panel for panel in panels if panel.condition in {"canonical", "no_observations"}
    ]
    if output.config.experiment == "recent-preprints":

        def cohort_order(panel: Any) -> tuple[int, str]:
            start = (panel.cohort or "").split("–")[0]
            return (
                int(start) if start.isdigit() else 999,
                str(panel.summary.dimensions["provider"]),
            )

        experiment_panels = sorted(panels, key=cohort_order)
    else:
        experiment_panels = [
            panel for panel in panels if panel.condition not in {"canonical", "no_observations"}
        ]
    specifications = [
        ("recall-by-provider", ("recall_at_1", "recall_at_5"), provider_panels),
        (
            "outcomes",
            (
                "unresolved_rate",
                "api_error_rate",
                "timeout_rate",
                "rate_limited_rate",
                "unknown_outcome_rate",
            ),
            panels,
        ),
        (
            "identity-and-sample-sizes",
            ("identity_undetermined_rate", "incorrect_match_rate"),
            panels,
        ),
    ]
    specifications.append(
        (
            "coverage-by-age"
            if output.config.experiment == "recent-preprints"
            else "recall-by-mutation",
            ("recall_at_1", "recall_at_5"),
            experiment_panels,
        )
    )
    created: list[Path] = []
    if output.manifest:
        hours = (
            output.manifest.collection_finished_at - output.manifest.collection_started_at
        ).total_seconds() / 3600
        window_note = (
            f"Collection window: {hours:g} hours; configured limit: "
            f"{output.config.max_collection_hours:g} hours; UTC age reference: "
            f"{output.manifest.reference_date or 'not applicable'}. "
            + ("Long window; not a simultaneous snapshot." if hours > 24 else "")
        )
    else:
        window_note = "Collection-window provenance not supplied; diagnostic/demonstration only."
    with matplotlib.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "svg.hashsalt": output.analysis_id,
            "svg.fonttype": "none",
            "pdf.compression": 0,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    ):
        for filename, metrics, selected in specifications:
            # Page long experiments rather than shrink labels to illegibility.
            pages = [selected[start : start + 12] for start in range(0, len(selected), 12)] or [[]]
            for page_number, page in enumerate(pages, 1):
                columns = min(2, len(metrics))
                row_count = (len(metrics) + columns - 1) // columns
                height = row_count * max(2.2, len(page) * 0.5 + 1) + 2.3
                fig, axes = plt.subplots(row_count, columns, figsize=(12, height), squeeze=False)
                try:
                    labels = [
                        f"{p.summary.dimensions['provider']} | {p.condition} | "
                        f"{p.cohort or 'cohort not supplied'}\n"
                        f"N={p.summary.retrieval_lookup_count}, T={p.summary.lookup_count}, "
                        f"papers={p.summary.original_citation_count}, "
                        f"eligible papers={p.summary.retrieval_original_citation_count}"
                        for p in page
                    ]
                    for metric_index, name in enumerate(metrics):
                        ax = axes.flat[metric_index]
                        for position, panel in enumerate(page):
                            metric = panel.summary.metrics[name]
                            if metric.value is not None:
                                ax.plot(metric.value, position, "o", color="#0072B2", markersize=6)
                            elif metric.lower_bound is not None and metric.upper_bound is not None:
                                ax.hlines(
                                    position,
                                    metric.lower_bound,
                                    metric.upper_bound,
                                    color="#D55E00",
                                    linewidth=4,
                                )
                                ax.text(
                                    0.98,
                                    position - 0.18,
                                    "exact undefined",
                                    ha="right",
                                    va="center",
                                    fontsize=8,
                                    transform=ax.get_yaxis_transform(),
                                )
                            else:
                                ax.text(
                                    0.02,
                                    position,
                                    "undefined (denominator=0)",
                                    va="center",
                                    fontsize=8,
                                )
                            interval = panel.intervals[name]
                            if interval.lower is not None and interval.upper is not None:
                                ax.hlines(
                                    position + 0.15,
                                    interval.lower,
                                    interval.upper,
                                    color="#009E73",
                                    linestyle="--",
                                    linewidth=2,
                                )
                        ax.set_yticks(
                            range(len(labels)),
                            labels if metric_index % columns == 0 else [""] * len(labels),
                        )
                        # Fixed row bounds also keep annotations inside single-row panels.
                        ax.set_ylim(max(1, len(labels)) - 0.5, -0.5)
                        ax.set_xlim(-0.02, 1.02)
                        ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0", "25", "50", "75", "100"])
                        ax.set_xlabel("Percent\nN: retrieval; T: operational", fontsize=8)
                        ax.set_title(name.replace("_", " "))
                        if not page:
                            ax.text(
                                0.5,
                                0.5,
                                "No eligible experiment observations",
                                transform=ax.transAxes,
                                ha="center",
                            )
                    for metric_index in range(len(metrics), row_count * columns):
                        axes.flat[metric_index].set_visible(False)
                    title = (
                        COVERAGE_LABEL
                        if output.config.experiment == "recent-preprints"
                        else "Metadata-mutation retrieval robustness"
                    )
                    fig.suptitle(
                        f"{output.data_label.upper()} — {output.report_kind.upper()}\n{title}",
                        fontsize=12,
                    )
                    footer = (
                        "Blue point: exact estimate. Orange segment: identity-evidence bounds "
                        "(not a CI). Green dashed: source-cluster statistical interval; "
                        "absent when disabled/suppressed.\n" + SCOPE_NOTE + "\n" + window_note
                    )
                    fig.text(
                        0.02,
                        0.015,
                        "\n".join(
                            textwrap.fill(line, width=int(fig.get_figwidth() * 15))
                            for line in footer.splitlines()
                        ),
                        fontsize=7,
                        va="bottom",
                        wrap=True,
                    )
                    fig.tight_layout(rect=(0, 1.3 / height, 0.98, 0.98))
                    suffix = f"-page-{page_number}" if len(pages) > 1 else ""
                    for fmt in output.config.figure_formats:
                        path = directory / f"{filename}{suffix}.{fmt}"
                        metadata: dict[str, Any] = (
                            {
                                "Date": None,
                                "Creator": "CiteProbe",
                                "Title": title + " — " + output.data_label,
                                "Description": output.analysis_id
                                + ": "
                                + SCOPE_NOTE
                                + " "
                                + window_note,
                            }
                            if fmt == "svg"
                            else {"CreationDate": None, "ModDate": None, "Creator": "CiteProbe"}
                            if fmt == "pdf"
                            else {"Software": "CiteProbe"}
                        )
                        fig.savefig(path, format=fmt, dpi=160, metadata=metadata)
                        created.append(path)
                finally:
                    plt.close(fig)
    return created
