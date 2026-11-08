"""Offline schema, mutation and CLI contract tests."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from citeprobe.cli import main
from citeprobe.dataset import benchmark_citations, load_dataset
from citeprobe.models import Citation, CitationValues, Dataset, MutationBatch
from citeprobe.mutations import TYPES, InapplicableMutation, generate_mutations, mutate

PILOT = Path(__file__).resolve().parents[1] / "data" / "pilot_dataset.json"


@pytest.fixture
def record() -> dict[str, Any]:
    result = load_dataset(PILOT).citations[0].model_dump(mode="json")
    result.update(volume="123", issue="21")
    return result


def test_pilot() -> None:
    dataset = load_dataset(PILOT)
    assert len(dataset.citations) == 5
    assert len(benchmark_citations(dataset)) == 5


@pytest.mark.parametrize("identifier", ["doi", "arxiv_id", "both"])
def test_identifier_options(record: dict[str, Any], identifier: str) -> None:
    record["doi"] = "10.1234/example"
    if identifier == "doi":
        record["arxiv_id"] = None
    if identifier == "arxiv_id":
        record["doi"] = None
    Citation.model_validate(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " "),
        ("authors", []),
        ("year", True),
        ("year", "2017"),
        ("year", 0),
        ("doi", "invalid"),
        ("arxiv_id", "1799.12345"),
        ("extra", 1),
        ("citation_id", ""),
    ],
)
def test_invalid(record: dict[str, Any], field: str, value: Any) -> None:
    record[field] = value
    with pytest.raises(ValidationError):
        Citation.model_validate(record)


def test_missing_identifiers(record: dict[str, Any]) -> None:
    record["arxiv_id"] = None
    with pytest.raises(ValidationError):
        Citation.model_validate(record)


@pytest.mark.parametrize(
    ("status", "timestamp"),
    [
        ("verified", None),
        ("pending", "2026-11-08T18:30:29Z"),
        ("verified", "2026-11-08T18:30:29"),
    ],
)
def test_provenance(record: dict[str, Any], status: str, timestamp: str | None) -> None:
    record["provenance"].update(verification_status=status, verified_at=timestamp)
    with pytest.raises(ValidationError):
        Citation.model_validate(record)


def test_duplicate_and_empty(record: dict[str, Any]) -> None:
    for records in ([], [record, record]):
        with pytest.raises(ValidationError):
            Dataset.model_validate(dict(dataset_version="test", citations=records))


@pytest.mark.parametrize("kind", TYPES)
def test_mutations(record: dict[str, Any], kind: Any) -> None:
    original = Citation.model_validate(record)
    before = original.model_dump_json()
    mutation = mutate(original, kind, seed=42)
    assert mutation == mutate(original, kind, seed=42)
    assert original.model_dump_json() == before
    assert mutation.citation.doi == original.doi
    assert mutation.citation.arxiv_id == original.arxiv_id
    assert mutation.original_citation_id == original.citation_id
    baseline = original.model_dump(exclude={"citation_id", "provenance"})
    changed = {k for k, v in mutation.citation.model_dump().items() if v != baseline[k]}
    assert changed == set(mutation.mutated_fields)
    CitationValues.model_validate_json(mutation.citation.model_dump_json())


def test_year_shifts(record: dict[str, Any]) -> None:
    original = Citation.model_validate(record)
    for delta in (-1, 1):
        assert (
            mutate(original, "year_shift", year_delta=delta).citation.year == original.year + delta
        )
    with pytest.raises(ValueError):
        mutate(original, "year_shift", year_delta=0)


@pytest.mark.parametrize(
    ("kind", "changes"),
    [
        ("title_word_deletion", {"title": "Single"}),
        ("title_typo", {"title": "123"}),
        ("digit_transposition", {"volume": "11", "issue": None}),
        ("author_initials", {"authors": [{"given": "A.", "family": "Smith"}]}),
        ("year_shift", {"year": 9999}),
    ],
)
def test_inapplicable(record: dict[str, Any], kind: Any, changes: dict[str, Any]) -> None:
    record.update(changes)
    with pytest.raises(InapplicableMutation):
        mutate(Citation.model_validate(record), kind)


def test_author_family_preservation(record: dict[str, Any]) -> None:
    original = Citation.model_validate(record)
    result = mutate(original, "author_initials").citation
    assert result.authors[0].given == "A."
    assert [a.family for a in result.authors] == [a.family for a in original.authors]


def test_hyphenated_given_name(record: dict[str, Any]) -> None:
    record["authors"] = [{"given": "-Jean--Paul-", "family": "Smith"}]
    result = mutate(Citation.model_validate(record), "author_initials")
    assert result.citation.authors[0].given == "J. P."


def test_invalid_mutation_arguments(record: dict[str, Any]) -> None:
    original = Citation.model_validate(record)
    for kind, seed in (("unknown", 1), ("title_typo", True)):
        with pytest.raises(ValueError):
            mutate(original, kind, seed=seed)  # type: ignore[arg-type]


def test_order_independence() -> None:
    dataset = load_dataset(PILOT)
    reordered = Dataset(
        dataset_version=dataset.dataset_version, citations=tuple(reversed(dataset.citations))
    )
    first = generate_mutations(dataset, seed=42)
    second = generate_mutations(reordered, seed=42)
    assert {m.mutation_id for m in first.mutations} == {m.mutation_id for m in second.mutations}


def test_pending(record: dict[str, Any]) -> None:
    record["provenance"].update(verification_status="pending", verified_at=None)
    dataset = Dataset.model_validate(dict(dataset_version="test", citations=[record]))
    assert not benchmark_citations(dataset)
    assert not generate_mutations(dataset).mutations
    assert len(generate_mutations(dataset).skipped) == len(TYPES)
    with pytest.raises(ValueError, match="Pending"):
        mutate(dataset.citations[0], "title_typo")


def test_batch_determinism() -> None:
    dataset = load_dataset(PILOT)
    before = dataset.model_dump_json()
    first = generate_mutations(dataset, seed=42)
    second = generate_mutations(dataset, seed=42)
    assert first.mutations == second.mutations
    assert first.skipped == second.skipped
    assert len(first.mutations) == 25
    assert len({m.mutation_id for m in first.mutations}) == 25
    assert len(first.skipped) == 5
    assert dataset.model_dump_json() == before


def test_cli(tmp_path: Path) -> None:
    source = tmp_path / "dataset.json"
    source.write_bytes(PILOT.read_bytes())
    before = source.read_bytes()
    output = tmp_path / "mutations.json"
    assert main(["validate", str(source)]) == 0
    assert main(["mutate", str(source), "--seed", "42", "--output", str(output)]) == 0
    batch = MutationBatch.model_validate_json(output.read_text())
    assert len(batch.mutations) == 25
    assert main(["mutate", str(source), "--output", str(source)]) == 1
    assert main(["mutate", str(source), "--output", str(output)]) == 1
    assert source.read_bytes() == before
    assert main(["validate", str(tmp_path / "missing.json")]) == 1
    source.write_text('{"broken":', encoding="utf-8")
    assert main(["validate", str(source)]) == 1
    source.write_text(json.dumps({"dataset_version": "x", "citations": []}))
    assert main(["validate", str(source)]) == 1
