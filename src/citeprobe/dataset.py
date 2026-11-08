"""Dataset loading and benchmark eligibility."""

from pathlib import Path

from citeprobe.models import Citation, Dataset


def load_dataset(path: Path) -> Dataset:
    return Dataset.model_validate_json(path.read_text(encoding="utf-8"))


def benchmark_citations(dataset: Dataset) -> tuple[Citation, ...]:
    """Return only explicitly verified records for downstream benchmark consumers."""
    return tuple(c for c in dataset.citations if c.provenance.verification_status == "verified")
