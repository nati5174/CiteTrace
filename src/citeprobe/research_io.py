"""Exclusive snapshots with byte-level hashes and semantic replay validation."""

import hashlib
import json
from pathlib import Path

from citeprobe.models import Dataset
from citeprobe.research import sample_dataset
from citeprobe.research_models import ResearchManifest, SamplingPlan

SNAPSHOT_FILES = {"dataset.json", "manifest.json", "selection.json", "integrity.json"}


def write_json(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(value + "\n")


def freeze(dataset: Dataset, manifest: ResearchManifest, directory: Path) -> None:
    plan = sample_dataset(dataset, manifest)
    if manifest.stage != "pre_collection":
        raise ValueError("Freeze pre-collection datasets; observation evidence stays separate")
    directory.mkdir(exist_ok=False)
    for name, model in (("dataset", dataset), ("manifest", manifest), ("selection", plan)):
        write_json(directory / f"{name}.json", model.model_dump_json(indent=2))
    hashes = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in sorted(SNAPSHOT_FILES - {"integrity.json"})
    }
    write_json(
        directory / "integrity.json",
        json.dumps({"schema_version": "1.0", "files": hashes}, sort_keys=True, indent=2),
    )


def verify(directory: Path, *, expected_integrity_sha256: str | None = None) -> SamplingPlan:
    if directory.is_symlink() or any(p.is_symlink() for p in directory.iterdir()):
        raise ValueError("Snapshot symlinks are not supported")
    if {p.name for p in directory.iterdir()} != SNAPSHOT_FILES:
        raise ValueError("Frozen snapshot inventory changed")
    if (
        expected_integrity_sha256 is not None
        and hashlib.sha256((directory / "integrity.json").read_bytes()).hexdigest()
        != expected_integrity_sha256
    ):
        raise ValueError("Snapshot differs from external integrity anchor")
    record = json.loads((directory / "integrity.json").read_bytes())
    if (
        not isinstance(record, dict)
        or set(record) != {"schema_version", "files"}
        or record["schema_version"] != "1.0"
        or not isinstance(record["files"], dict)
        or set(record["files"]) != SNAPSHOT_FILES - {"integrity.json"}
    ):
        raise ValueError("Invalid snapshot integrity inventory")
    for name, digest in record["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen snapshot tampering: {name}")
    dataset = Dataset.model_validate_json((directory / "dataset.json").read_bytes())
    manifest = ResearchManifest.model_validate_json((directory / "manifest.json").read_bytes())
    plan = SamplingPlan.model_validate_json((directory / "selection.json").read_bytes())
    if sample_dataset(dataset, manifest) != plan:
        raise ValueError("Frozen sampling decisions do not reproduce")
    return plan
