"""Invented metadata for offline infrastructure tests only; never observed evidence."""

from typing import Any

from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.research_models import ResearchManifest


def fixture_payloads(experiment: str = "recent-preprints") -> tuple[dict[str, Any], dict[str, Any]]:
    provenance = {
        "source_url": "https://example.org/synthetic/source",
        "record_identifier": "synthetic",
        "verification_status": "verified",
        "verified_at": "2025-01-01T00:00:00Z",
    }
    dataset: dict[str, Any] = {
        "dataset_version": "synthetic-research-1",
        "citations": [
            {
                "citation_id": f"synthetic-{i}",
                "title": f"Synthetic test work {i}",
                "authors": [{"given": "Invented", "family": "Fixture"}],
                "year": 2024,
                "arxiv_id": f"2401.0000{i}",
                "provenance": provenance,
            }
            for i in (1, 2)
        ],
    }
    source = {
        "evidence_id": "source",
        "provenance": provenance,
        "origin": "simulated",
        "authority": "original_repository",
        "retrieved_at": "2025-01-01T00:00:00Z",
        "evidence_sha256": "1" * 64,
        "excerpt": "Synthetic assertion, not real evidence",
        "supports": [
            "title",
            "authors",
            "year",
            "arxiv_id",
            "doi",
            "volume",
            "issue",
            "first_public_date",
            "declared_identifiers",
        ],
    }
    papers: list[dict[str, Any]] = []
    for c in dataset["citations"]:
        paper: dict[str, Any] = {
            "citation_id": c["citation_id"],
            "evidence_ids": ["source"],
            "verified_fields": ["title", "authors", "year", "arxiv_id"],
            "decision": "include",
            "reason": "Synthetic eligible fixture",
        }
        if experiment == "recent-preprints":
            paper.update(
                {
                    "public_date": {
                        "citation_id": c["citation_id"],
                        "publication_date": "2025-01-30",
                        "provenance": provenance,
                    },
                    "public_date_basis": "public_announcement",
                    "cohort": "1-7",
                }
            )
        else:
            paper["identifier_stratum"] = "arxiv_only"
        papers.append(paper)
    manifest: dict[str, Any] = {
        "manifest_version": "synthetic-1",
        "manifest_fingerprint": "0" * 64,
        "dataset_version": dataset["dataset_version"],
        "dataset_fingerprint": "0" * 64,
        "experiment": experiment,
        "origin": "simulated",
        "protocol_sha256": "2" * 64,
        "frame_source": provenance,
        "frame_evidence_id": "source",
        "frame_snapshot_sha256": "1" * 64,
        "frame_definition": "Synthetic cs.CL English frame",
        "seed": 0,
        "target_per_group": {"1-7": 1, "8-14": 1, "15-30": 1, "31-60": 1}
        if experiment == "recent-preprints"
        else {"doi_only": 1, "arxiv_only": 1, "dual": 1},
        "planned_started_at": "2025-01-31T00:00:00Z",
        "planned_finished_at": "2025-01-31T23:59:00Z",
        "sources": [source],
        "papers": papers,
    }
    if experiment == "recent-preprints":
        manifest["reference_date"] = "2025-01-31"
    return dataset, manifest


def seal(dataset: dict[str, Any], manifest: dict[str, Any]) -> tuple[Dataset, ResearchManifest]:
    d = Dataset.model_validate(dataset)
    manifest["dataset_fingerprint"] = fingerprint(d.model_dump(mode="json"))
    m = ResearchManifest.model_validate(manifest)
    manifest["manifest_fingerprint"] = fingerprint(
        m.model_dump(mode="json", exclude={"manifest_fingerprint"})
    )
    return d, ResearchManifest.model_validate(manifest)


def claim(basis: str = "new_mapping") -> dict[str, Any]:
    return {
        "claim_id": "alias",
        "citation_id": "synthetic-1",
        "basis": basis,
        "relation": "same_work",
        "expression": "original",
        "identifiers": [
            {"namespace": "doi", "value": "10.1234/synthetic"},
            {"namespace": "arxiv", "value": "2401.00001"},
        ],
        "evidence_ids": ["source"],
        "rationale": "Synthetic explicit bridge",
        "reviews": [
            {"reviewer_id": name, "decision": "approve", "reviewed_at": "2025-01-01T00:00:00Z"}
            for name in ("a", "b")
        ],
    }
