"""Identifier judgments use explicit evidence, never title or identifier inequality."""

from typing import Any

import pytest
from evaluation_helpers import synthetic_dataset

from citeprobe.evaluation_models import IdentityMappings
from citeprobe.identity import IdentityIndex, normalize_arxiv, normalize_doi
from citeprobe.models import Dataset
from citeprobe.resolution_models import Candidate


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" DOI:10.1234/ABC ", "10.1234/abc"),
        ("https://doi.org/10.1234/Some%28X%29", "10.1234/some(x)"),
        ("http://dx.doi.org/10.1234/ABC", "10.1234/abc"),
        ("10.1234/abc.", "10.1234/abc."),
        ("10.1234/abc%2Fdef", "10.1234/abc%2fdef"),
        ("https://evil.example/10.1234/abc", None),
        ("https://doi.org/10.1234/abc?tracking=x", None),
        ("https://user@doi.org/10.1234/abc", None),
        ("https://doi.org:123/10.1234/abc", None),
        ("10.1234/white space", None),
        ("not-a-doi", None),
    ],
)
def test_doi_normalization(value: str, expected: str | None) -> None:
    assert normalize_doi(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" arXiv:1706.03762v3 ", "1706.03762"),
        ("https://arxiv.org/pdf/1706.03762v2.pdf", "1706.03762"),
        ("https://arxiv.org/abs/math.GT/0301234v1", "math.gt/0301234"),
        ("1706.03762v0", None),
        ("1799.12345", None),
        ("https://evil.example/abs/1706.03762", None),
        ("https://arxiv.org/abs/1706.03762?x=y", None),
        ("1706.03762.pdf", None),
    ],
)
def test_arxiv_normalization(value: str, expected: str | None) -> None:
    assert normalize_arxiv(value) == expected


def mapping(dataset: Dataset, relation: str, namespace: str, value: str) -> dict[str, Any]:
    return {
        "citation_id": dataset.citations[0].citation_id,
        "relation": relation,
        "identifiers": [{"namespace": namespace, "value": value}],
        "provenance": dataset.citations[0].provenance.model_dump(mode="json"),
    }


def test_doi_identity_ignores_title() -> None:
    dataset = synthetic_dataset()
    index = IdentityIndex(dataset, IdentityMappings(dataset_version=dataset.dataset_version))
    candidate = Candidate(
        provider_record_id="W123",
        title="Completely different title",
        doi="https://doi.org/10.1234/FIXTURE-0",
        provider_rank=1,
    )
    judgment = index.judge("fixture-0", "openalex", candidate)
    assert judgment.judgment == "CORRECT"
    assert judgment.matching_evidence == ("doi:10.1234/fixture-0",)


def test_arxiv_only_and_version_matching() -> None:
    data = synthetic_dataset(1).model_dump(mode="json")
    data["citations"][0].update(doi=None, arxiv_id="1706.03762v1")
    dataset = Dataset.model_validate(data)
    index = IdentityIndex(dataset, IdentityMappings(dataset_version=dataset.dataset_version))
    candidate = Candidate(provider_record_id="W123", arxiv_id="1706.03762v9", provider_rank=1)
    assert index.judge("fixture-0", "openalex", candidate).judgment == "CORRECT"
    candidate = candidate.model_copy(update={"arxiv_id": None, "doi": "10.1234/other"})
    assert index.judge("fixture-0", "openalex", candidate).judgment == "UNDETERMINED"


@pytest.mark.parametrize("identifier", [None, "10.1234/other", "bad DOI"])
def test_mismatch_or_identical_title_does_not_prove_identity(identifier: str | None) -> None:
    dataset = synthetic_dataset()
    index = IdentityIndex(dataset, IdentityMappings(dataset_version=dataset.dataset_version))
    candidate = Candidate(
        provider_record_id="W123", title=dataset.citations[0].title, doi=identifier, provider_rank=1
    )
    assert index.judge("fixture-0", "openalex", candidate).judgment == "UNDETERMINED"


@pytest.mark.parametrize(
    ("namespace", "value", "candidate_values", "expected"),
    [
        ("openalex", "https://openalex.org/W123", {}, "CORRECT"),
        ("doi", "10.1234/alias", {"doi": "10.1234/ALIAS"}, "CORRECT"),
        ("arxiv", "1706.03762", {"arxiv_id": "1706.03762v2"}, "CORRECT"),
        ("doi", "10.1234/other", {"doi": "10.1234/other"}, "INCORRECT"),
    ],
)
def test_verified_mapping(
    namespace: str, value: str, candidate_values: dict[str, Any], expected: str
) -> None:
    dataset = synthetic_dataset()
    relation = "different_work" if expected == "INCORRECT" else "same_work"
    mappings = IdentityMappings.model_validate(
        {
            "dataset_version": dataset.dataset_version,
            "mappings": [mapping(dataset, relation, namespace, value)],
        }
    )
    index = IdentityIndex(dataset, mappings)
    candidate = Candidate(provider_record_id="W123", provider_rank=1, **candidate_values)
    assert index.judge("fixture-0", "openalex", candidate).judgment == expected


def test_candidate_conflicting_evidence_is_undetermined() -> None:
    dataset = synthetic_dataset()
    mappings = IdentityMappings.model_validate(
        {
            "dataset_version": dataset.dataset_version,
            "mappings": [mapping(dataset, "different_work", "openalex", "W123")],
        }
    )
    candidate = Candidate(provider_record_id="W123", doi="10.1234/fixture-0", provider_rank=1)
    assert (
        IdentityIndex(dataset, mappings).judge("fixture-0", "openalex", candidate).judgment
        == "UNDETERMINED"
    )


@pytest.mark.parametrize("change", ["pending", "unknown_source", "version", "conflict", "bad_id"])
def test_invalid_mapping(change: str) -> None:
    dataset = synthetic_dataset()
    row = mapping(dataset, "same_work", "doi", "10.1234/alias")
    data: dict[str, Any] = {"dataset_version": dataset.dataset_version, "mappings": [row]}
    if change == "pending":
        row["provenance"].update(verification_status="pending", verified_at=None)
    elif change == "unknown_source":
        row["citation_id"] = "unknown"
    elif change == "version":
        data["dataset_version"] = "wrong"
    elif change == "bad_id":
        row["identifiers"][0]["value"] = "bad"
    else:
        data["mappings"].append(mapping(dataset, "different_work", "doi", "10.1234/alias"))
    with pytest.raises(ValueError):
        IdentityIndex(dataset, IdentityMappings.model_validate(data))


def test_other_canonical_identifier_is_not_automatically_incorrect() -> None:
    dataset = synthetic_dataset()
    index = IdentityIndex(dataset, IdentityMappings(dataset_version=dataset.dataset_version))
    candidate = Candidate(provider_record_id="10.1234/fixture-1", provider_rank=1)
    assert index.judge("fixture-0", "crossref", candidate).judgment == "UNDETERMINED"
