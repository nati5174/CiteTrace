"""Stable machine-readable serialization with exclusive output creation."""

import csv
import io
import json
from contextlib import ExitStack
from pathlib import Path

from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.resolution_cli import check_output

CSV_FIELDS = (
    "evaluation_id",
    "schema_version",
    "dataset_fingerprint",
    "data_label",
    "empirical_data_eligible",
    "grouping",
    "provider",
    "strategy",
    "source_kind",
    "mutation_type",
    "original_citation_id",
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
)


def csv_text(output: EvaluationOutput) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for group in output.groups:
        for name, metric in sorted(group.metrics.items()):
            writer.writerow(
                {
                    "evaluation_id": output.evaluation_id,
                    "schema_version": output.schema_version,
                    "dataset_fingerprint": output.dataset_fingerprint,
                    "empirical_data_eligible": group.empirical_data_eligible,
                    "grouping": ",".join(sorted(group.dimensions)),
                    **group.dimensions,
                    "lookup_count": group.lookup_count,
                    "retrieval_lookup_count": group.retrieval_lookup_count,
                    "original_citation_count": group.original_citation_count,
                    "retrieval_original_citation_count": group.retrieval_original_citation_count,
                    "metric": name,
                    **metric.model_dump(),
                }
            )
    return stream.getvalue()


def check_outputs(json_path: Path, csv_path: Path, sources: list[Path]) -> None:
    check_output(json_path, [*sources, csv_path])
    check_output(csv_path, [*sources, json_path])


def write_evaluation(
    output: EvaluationOutput, json_path: Path, csv_path: Path, sources: list[Path]
) -> None:
    check_outputs(json_path, csv_path, sources)
    # Serialize before creating any file; neither failures nor existing paths become fake results.
    serialized_json = (
        json.dumps(
            output.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    serialized_csv = csv_text(output)
    created: list[Path] = []
    try:
        with ExitStack() as stack:
            json_file = stack.enter_context(json_path.open("x", encoding="utf-8", newline=""))
            created.append(json_path)
            csv_file = stack.enter_context(csv_path.open("x", encoding="utf-8", newline=""))
            created.append(csv_path)
            json_file.write(serialized_json)
            csv_file.write(serialized_csv)
    except OSError:
        for path in created:
            path.unlink()
        raise
