"""Synthetic offline dataset infrastructure and integrity regressions."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from evaluation_helpers import lookup_bundle
from research_helpers import claim, fixture_payloads, seal

from citeprobe.cli import main
from citeprobe.lookup_inputs import fingerprint
from citeprobe.mutations import generate_mutations
from citeprobe.research import cohort, sample_dataset, validate_research
from citeprobe.research_io import freeze, verify


@pytest.mark.parametrize(
    "age,expected",
    [
        (0, None),
        (1, "1-7"),
        (7, "1-7"),
        (8, "8-14"),
        (14, "8-14"),
        (15, "15-30"),
        (30, "15-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, None),
        (-1, None),
    ],
)
def test_cohort_boundaries(age: int, expected: str | None) -> None:
    reference = date(2025, 2, 1)
    assert cohort(reference, reference - timedelta(days=age)) == expected


def test_sampling_determinism_and_reserves() -> None:
    raw, ledger = fixture_payloads()
    d, m = seal(raw, ledger)
    original = d.model_dump_json()
    plan = sample_dataset(d, m)
    assert plan == sample_dataset(d, m)
    assert sorted(row.disposition for row in plan.rows) == ["reserve", "selected"]
    assert sum(plan.shortfalls.values()) == 3
    assert d.model_dump_json() == original
    ledger["papers"].reverse()
    _, reordered = seal(raw, ledger)
    assert sample_dataset(d, reordered).rows == plan.rows
    for row in plan.rows:
        assert (
            row.sampling_key
            == hashlib.sha256(f"citeprobe-A-v1|seed=0|{row.citation_id}".encode()).hexdigest()
        )
    ledger["seed"] = 19
    d, changed = seal(raw, ledger)
    assert sample_dataset(d, changed).rows != plan.rows


@pytest.mark.parametrize(
    "change",
    [
        "missing_id",
        "pending_date",
        "submission",
        "boundary",
        "missing_paper",
        "duplicate_paper",
        "missing_evidence",
        "pending_source",
        "origin",
        "bad_origin",
        "missing_reason",
        "exclusion",
        "fingerprint",
        "manifest_hash",
        "plan_actual",
        "post_without_evidence",
        "stratum",
        "field_provenance",
        "reference",
        "duplicate_source",
        "bad_frame",
        "unknown_target",
        "translation",
        "derivative",
        "one_review",
        "same_reviewer",
        "rejected_review",
        "conflict",
        "registry_only",
        "contradiction",
        "dual_without_bridge",
        "possible_merge",
        "fake_duplicate_exclusion",
        "missing_duplicate_representative",
    ],
)
def test_validation_rejections(change: str) -> None:
    raw, ledger = fixture_payloads()
    paper = ledger["papers"][0]
    if change == "missing_id":
        raw["citations"][0].pop("arxiv_id")
    elif change == "pending_date":
        paper["public_date"]["provenance"] = {
            **ledger["frame_source"],
            "verification_status": "pending",
            "verified_at": None,
        }
    elif change == "submission":
        paper["public_date_basis"] = "submission"
    elif change == "boundary":
        paper["cohort"] = "8-14"
    elif change == "missing_paper":
        ledger["papers"].pop()
    elif change == "duplicate_paper":
        ledger["papers"].append(paper)
    elif change == "missing_evidence":
        paper["evidence_ids"] = ["absent"]
    elif change == "pending_source":
        ledger["sources"][0]["provenance"] = {
            **ledger["frame_source"],
            "verification_status": "pending",
            "verified_at": None,
        }
    elif change == "origin":
        ledger["origin"] = "observed"
    elif change == "bad_origin":
        ledger["origin"] = "real"
    elif change == "missing_reason":
        paper["reason"] = ""
    elif change == "exclusion":
        paper["decision"] = "exclude"
    elif change == "plan_actual":
        ledger["actual_started_at"] = ledger["planned_started_at"]
    elif change == "post_without_evidence":
        ledger["stage"] = "post_collection"
    elif change == "stratum":
        paper["identifier_stratum"] = "arxiv_only"
    elif change == "field_provenance":
        paper["verified_fields"] = ["title"]
    elif change == "reference":
        ledger["reference_date"] = "2025-02-01"
    elif change == "duplicate_source":
        ledger["sources"].append(ledger["sources"][0])
    elif change == "bad_frame":
        ledger["frame_evidence_id"] = "absent"
    elif change == "dual_without_bridge":
        raw["citations"][0]["doi"] = "10.1234/synthetic"
    elif change in {
        "possible_merge",
        "fake_duplicate_exclusion",
        "missing_duplicate_representative",
    }:
        ledger["duplicates"] = [
            {
                "duplicate_id": "dup",
                "category": "POSSIBLE_DUPLICATE",
                "citation_ids": ["synthetic-1", "synthetic-2"],
                "reason": "Synthetic suspicion",
            }
        ]
        if change == "possible_merge":
            ledger["duplicates"][0]["representative_id"] = "synthetic-1"
        elif change == "fake_duplicate_exclusion":
            paper.update(decision="exclude", exclusion_kind="verified_duplicate")
        else:
            ledger["duplicates"][0]["category"] = "VERIFIED_DUPLICATE"
    elif change not in {"fingerprint", "manifest_hash"}:
        entry = claim()
        ledger["identity_claims"] = [entry]
        if change == "unknown_target":
            entry["citation_id"] = "absent"
        elif change in {"translation", "derivative"}:
            entry["expression"] = change
        elif change == "one_review":
            entry["reviews"].pop()
        elif change == "same_reviewer":
            entry["reviews"][1]["reviewer_id"] = "a"
        elif change == "rejected_review":
            entry["reviews"][1]["decision"] = "reject"
        elif change == "conflict":
            entry["conflict"] = True
        elif change == "registry_only":
            ledger["sources"][0]["authority"] = "registry"
        elif change == "contradiction":
            entry["relation"] = "different_work"
    with pytest.raises(ValueError):
        d, m = seal(raw, ledger)
        if change == "fingerprint":
            m = m.model_copy(update={"dataset_fingerprint": "f" * 64})
        if change == "manifest_hash":
            m = m.model_copy(update={"manifest_fingerprint": "f" * 64})
        validate_research(d, m)


def test_baseline_alias_and_reviewed_mapping() -> None:
    for basis in ("source_declared", "new_mapping"):
        raw, ledger = fixture_payloads("mutation-robustness")
        entry = claim(basis)
        if basis == "source_declared":
            entry["reviews"] = []
        ledger["identity_claims"] = [entry]
        ledger["papers"][0]["identifier_stratum"] = "dual"
        d, m = seal(raw, ledger)
        assert validate_research(d, m) == ()


def test_possible_duplicates_not_merged() -> None:
    raw, ledger = fixture_payloads()
    raw["citations"][1]["title"] = raw["citations"][0]["title"]
    d, m = seal(raw, ledger)
    plan = sample_dataset(d, m)
    assert len(plan.rows) == 2
    assert "POSSIBLE_DUPLICATE" in plan.warnings[0]


def test_verified_duplicates_require_explicit_exclusion() -> None:
    raw, ledger = fixture_payloads()
    raw["citations"][1]["arxiv_id"] = raw["citations"][0]["arxiv_id"]
    d, m = seal(raw, ledger)
    with pytest.raises(ValueError, match="Duplicate scholarly"):
        validate_research(d, m)
    ledger["papers"][1].update(
        decision="exclude",
        exclusion_kind="verified_duplicate",
        reason="Authoritatively verified repeated identifier",
    )
    ledger["duplicates"] = [
        {
            "duplicate_id": "duplicate",
            "category": "VERIFIED_DUPLICATE",
            "citation_ids": ["synthetic-1", "synthetic-2"],
            "representative_id": "synthetic-1",
            "reason": "Verified same base identifier",
        }
    ]
    d, m = seal(raw, ledger)
    assert [r.disposition for r in sample_dataset(d, m).rows].count("excluded") == 1


def test_mutation_inventory_and_identifier_leakage() -> None:
    raw, ledger = fixture_payloads("mutation-robustness")
    d, m = seal(raw, ledger)
    batch = generate_mutations(d)
    validate_research(d, m, mutations=batch)
    with pytest.raises(ValueError, match="applicability"):
        validate_research(d, m, mutations=batch.model_copy(update={"skipped": ()}))
    raw["citations"][0]["title"] += " 2401.00001"
    d, m = seal(raw, ledger)
    with pytest.raises(ValueError, match="leakage"):
        validate_research(d, m)


@pytest.mark.parametrize(
    "filename", ["dataset.json", "manifest.json", "selection.json", "integrity.json"]
)
def test_frozen_tampering(tmp_path: Path, filename: str) -> None:
    d, m = seal(*fixture_payloads())
    directory = tmp_path / "frozen"
    freeze(d, m, directory)
    assert verify(directory) == sample_dataset(d, m)
    with pytest.raises(FileExistsError):
        freeze(d, m, directory)
    (directory / filename).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        verify(directory)


def test_rehashed_sampling_tamper_is_rejected(tmp_path: Path) -> None:
    d, m = seal(*fixture_payloads())
    directory = tmp_path / "frozen"
    freeze(d, m, directory)
    selection = directory / "selection.json"
    data = json.loads(selection.read_bytes())
    data["rows"][0]["disposition"] = "excluded"
    selection.write_text(json.dumps(data), encoding="utf-8")
    integrity = directory / "integrity.json"
    hashes = json.loads(integrity.read_bytes())
    hashes["files"]["selection.json"] = hashlib.sha256(selection.read_bytes()).hexdigest()
    integrity.write_text(json.dumps(hashes), encoding="utf-8")
    with pytest.raises(ValueError, match="reproduce"):
        verify(directory)


def test_cli_roundtrip_and_output_protection(tmp_path: Path) -> None:
    d, m = seal(*fixture_payloads())
    source, manifest = tmp_path / "dataset.json", tmp_path / "manifest.json"
    source.write_text(d.model_dump_json(), encoding="utf-8")
    manifest.write_text(m.model_dump_json(), encoding="utf-8")
    base = [str(source), "--manifest", str(manifest)]
    assert main(["dataset-validate", *base]) == 0
    assert main(["dataset-sample", *base, "--output", str(tmp_path / "sample.json")]) == 0
    assert main(["dataset-sample", *base, "--output", str(source)]) == 1
    assert main(["dataset-freeze", *base, "--output", str(tmp_path / "snapshot")]) == 0
    assert main(["dataset-verify", str(tmp_path / "snapshot")]) == 0
    assert main(["validate", str(source)]) == 0
    assert fingerprint(d.model_dump(mode="json")) == m.dataset_fingerprint


def test_actual_times_require_original_observations() -> None:
    raw, ledger = fixture_payloads("mutation-robustness")
    d, _ = seal(raw, ledger)
    bundle = lookup_bundle(d, [{"results": []}, {"results": []}])
    ledger.update(
        stage="post_collection",
        actual_started_at=bundle.results[0].started_at,
        actual_finished_at=bundle.results[-1].finished_at,
        observation_bundle_ids=[fingerprint(bundle.model_dump(mode="json"))],
    )
    d, manifest = seal(raw, ledger)
    validate_research(d, manifest, bundles=(bundle,))
    with pytest.raises(ValueError, match="inventory"):
        validate_research(d, manifest)
    ledger["actual_finished_at"] = ledger["planned_finished_at"]
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError, match="timestamps differ"):
        validate_research(d, manifest, bundles=(bundle,))


def test_frame_hash_and_provenance_failures() -> None:
    raw, ledger = fixture_payloads()
    ledger["frame_snapshot_sha256"] = "f" * 64
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError, match="Frame snapshot"):
        validate_research(d, manifest)
    ledger["frame_source"]["source_url"] = "invalid-url"
    with pytest.raises(ValueError):
        seal(raw, ledger)


def test_pending_claim_not_accepted_as_identifier_inventory() -> None:
    raw, ledger = fixture_payloads("mutation-robustness")
    entry = claim()
    entry["relation"] = "undetermined"
    ledger["identity_claims"] = [entry]
    ledger["papers"][0]["identifier_stratum"] = "dual"
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError, match="stratum"):
        validate_research(d, manifest)


def test_externally_anchored_snapshot_and_extra_files(tmp_path: Path) -> None:
    d, manifest = seal(*fixture_payloads())
    directory = tmp_path / "snapshot"
    freeze(d, manifest, directory)
    anchor = hashlib.sha256((directory / "integrity.json").read_bytes()).hexdigest()
    verify(directory, expected_integrity_sha256=anchor)
    with pytest.raises(ValueError, match="anchor"):
        verify(directory, expected_integrity_sha256="0" * 64)
    (directory / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        verify(directory)


def test_doi_only_stratum_and_unverified_mapping() -> None:
    raw, ledger = fixture_payloads("mutation-robustness")
    raw["citations"][0].pop("arxiv_id")
    raw["citations"][0]["doi"] = "10.1234/synthetic"
    ledger["papers"][0]["verified_fields"] = ["title", "authors", "year", "doi"]
    ledger["papers"][0]["identifier_stratum"] = "doi_only"
    d, manifest = seal(raw, ledger)
    validate_research(d, manifest)
    ledger["identity_claims"] = [claim()]
    ledger["sources"][0]["provenance"] = {
        **ledger["frame_source"],
        "verification_status": "pending",
        "verified_at": None,
    }
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError):
        validate_research(d, manifest)


def test_dataset_changes_and_group_target_validation() -> None:
    raw, ledger = fixture_payloads()
    d, manifest = seal(raw, ledger)
    raw["citations"][0]["title"] = "Changed synthetic title"
    changed, _ = seal(raw, ledger)
    with pytest.raises(ValueError, match="Dataset version/fingerprint"):
        validate_research(changed, manifest)
    ledger["target_per_group"].pop("8-14")
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError, match="all experiment groups"):
        validate_research(d, manifest)


def test_duplicate_representative_cannot_also_be_excluded() -> None:
    raw, ledger = fixture_payloads()
    raw["citations"][1]["arxiv_id"] = raw["citations"][0]["arxiv_id"]
    for paper in ledger["papers"]:
        paper.update(decision="exclude", exclusion_kind="verified_duplicate")
    ledger["duplicates"] = [
        {
            "duplicate_id": "duplicate",
            "category": "VERIFIED_DUPLICATE",
            "citation_ids": ["synthetic-1", "synthetic-2"],
            "representative_id": "synthetic-1",
            "reason": "Synthetic exact identifier",
        }
    ]
    d, manifest = seal(raw, ledger)
    with pytest.raises(ValueError, match="remain included"):
        validate_research(d, manifest)


def test_fixture_files_are_simulated_and_validate() -> None:
    from citeprobe.dataset import load_dataset
    from citeprobe.research_models import ResearchManifest

    root = Path("tests/fixtures/research-infrastructure")
    dataset = load_dataset(root / "dataset.json")
    for name in ("manifest-a.json", "manifest-b.json"):
        manifest = ResearchManifest.model_validate_json((root / name).read_bytes())
        assert manifest.origin == "simulated"
        validate_research(dataset, manifest)
