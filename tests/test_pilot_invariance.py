"""Synthetic A-SI-v1 regression tests; no observed approvals or live requests."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pilot_helpers import END, a_frame, a_review

from citeprobe.cli import main
from citeprobe.evaluation_models import IdentityMappings
from citeprobe.evidence_io import json_bytes
from citeprobe.identity import IdentityIndex
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.pilot_invariance import POLICY, InvarianceAssessment, certificate
from citeprobe.pilot_models import PilotFrame, PilotReview
from citeprobe.pilot_review import freeze_pilot, select_pilot, verify_pilot

Prepared = tuple[Path, PilotFrame, PilotReview, InvarianceAssessment, dict[str, Any]]


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Prepared:
    monkeypatch.setattr("time.sleep", lambda _: None)
    source = tmp_path / "source"
    frame = a_frame(source)
    full = a_review(tmp_path, frame)
    baseline = cast(dict[str, Any], select_pilot(source, frame, full))
    selected = baseline["selected_source_ids"]
    pending = tuple(sorted(set(frame.panel_ids) - set(selected))[-2:])
    decisions = tuple(
        d.model_copy(
            update={
                "disposition": "pending",
                "identity_verified": False,
                "metadata_verified": False,
                "v1_verified": False,
                "reason": "Synthetic unresolved publisher relationship",
            }
        )
        if d.source_id in pending
        else d
        for d in full.decisions
    )
    review = full.model_copy(update={"decisions": decisions})
    assessment = InvarianceAssessment(
        policy_sha256=hashlib.sha256(POLICY.read_bytes()).hexdigest(),
        frame_id=frame.frame_id,
        review_fingerprint=fingerprint(review.model_dump(mode="json")),
        pending_ids=pending,
        selected_ids=tuple(selected),
        no_selected_relationship_threat=True,
        reviewer_id="synthetic-reviewer",
        reviewed_at=END,
        rationale="Synthetic complete relationship review; no selected-paper threat",
    )
    return source, frame, review, assessment, baseline


def test_invariant_selection_retains_pending_and_replays(
    prepared: Prepared, tmp_path: Path
) -> None:
    source, frame, review, assessment, baseline = prepared
    before = review.model_dump_json()
    result = cast(dict[str, Any], select_pilot(source, frame, review, invariance=assessment))
    assert result["selected_source_ids"] == baseline["selected_source_ids"]
    assert result["ready_to_freeze"]
    assert result == select_pilot(source, frame, review, invariance=assessment)
    proof = result["selection_invariance"]
    assert len(proof["completions"]) == 4
    assert len(proof["panel_dispositions"]) == 24
    assert all(proof["panel_dispositions"][k] == "pending" for k in assessment.pending_ids)
    assert not proof["fully_adjudicated_panel"]
    assert review.model_dump_json() == before
    assert not set(assessment.pending_ids) & set(result["selected_source_ids"])
    # Only synthetic temporary fixtures are frozen to test future replay compatibility.
    frozen = tmp_path / "synthetic-frozen"
    freeze_pilot(frozen, source, frame, review, invariance=assessment)
    verify_pilot(frozen)
    saved = json.loads((frozen / "review.json").read_bytes())
    assert len(saved["decisions"]) == 24
    (frozen / "selection-invariance.json").write_text("{}")
    with pytest.raises(ValueError, match="assessment hash"):
        verify_pilot(frozen)


def test_default_still_rejects_pending(prepared: Prepared) -> None:
    source, frame, review, _, _ = prepared
    with pytest.raises(ValueError, match="Pending verification"):
        select_pilot(source, frame, review)


@pytest.mark.parametrize(
    "problem", ["fingerprint", "policy", "selected", "pending", "approval", "date", "experiment"]
)
def test_fail_closed(prepared: Prepared, problem: str) -> None:
    source, frame, review, assessment, baseline = prepared
    if problem in {"fingerprint", "policy", "selected", "pending"}:
        changes: dict[str, dict[str, Any]] = {
            "fingerprint": {"review_fingerprint": "0" * 64},
            "policy": {"policy_sha256": "0" * 64},
            "selected": {"selected_ids": (*assessment.selected_ids[:7], assessment.pending_ids[0])},
            "pending": {"pending_ids": (assessment.pending_ids[0],)},
        }
        assessment = assessment.model_copy(update=changes[problem])
    elif problem in {"approval", "date"}:
        target = assessment.selected_ids[0] if problem == "approval" else assessment.pending_ids[0]
        updates = (
            {"metadata_verified": False}
            if problem == "approval"
            else {"v1_evidence_directory": None}
        )
        review = review.model_copy(
            update={
                "decisions": tuple(
                    d.model_copy(update=updates) if d.source_id == target else d
                    for d in review.decisions
                )
            }
        )
        assessment = assessment.model_copy(
            update={"review_fingerprint": fingerprint(review.model_dump(mode="json"))}
        )
    else:
        frame = frame.model_copy(update={"experiment": "mutation-robustness-pilot"})
    with pytest.raises(ValueError):
        select_pilot(source, frame, review, invariance=assessment)


def test_pending_top_rank_changes_completion(prepared: Prepared) -> None:
    source, frame, review, assessment, baseline = prepared
    target = assessment.selected_ids[0]
    review = review.model_copy(
        update={
            "decisions": tuple(
                d.model_copy(update={"disposition": "pending", "identity_verified": False})
                if d.source_id == target
                else d.model_copy(
                    update={
                        "disposition": "include",
                        "identity_verified": True,
                        "metadata_verified": True,
                        "v1_verified": True,
                    }
                )
                if d.source_id == assessment.pending_ids[0]
                else d
                for d in review.decisions
            )
        }
    )
    remaining = [d.source_id for d in review.decisions if d.disposition == "pending"]
    groups = {i.source_id: i.group for i in frame.items}
    approved = {d.source_id for d in review.decisions if d.disposition == "include"}
    selected = []
    for group in ("1-7", "8-14", "15-30", "31-60"):
        selected.extend(
            sorted(
                (k for k in approved if groups[k] == group),
                key=lambda k: (
                    hashlib.sha256(
                        ("citeprobe-A-submission-v1|seed=0|" + k.removeprefix("arxiv:")).encode()
                    ).hexdigest(),
                    k,
                ),
            )[:2]
        )
    assessment = assessment.model_copy(
        update={
            "pending_ids": tuple(remaining),
            "selected_ids": tuple(selected),
            "review_fingerprint": fingerprint(review.model_dump(mode="json")),
        }
    )
    with pytest.raises(ValueError, match="Selection changes"):
        select_pilot(source, frame, review, invariance=assessment)


def test_duplicate_threat_cannot_be_overridden(prepared: Prepared) -> None:
    _, frame, review, assessment, baseline = prepared
    target = assessment.selected_ids[0]
    pending = assessment.pending_ids[0]
    frame = frame.model_copy(
        update={
            "items": tuple(
                i.model_copy(update={"possible_duplicates": (target,)})
                if i.source_id == pending
                else i
                for i in frame.items
            )
        }
    )
    dataset = Dataset.model_validate(baseline["dataset"])
    index = IdentityIndex(dataset, IdentityMappings.model_validate(baseline["identity_mappings"]))
    with pytest.raises(ValueError, match="duplicate/version flag"):
        certificate(
            assessment,
            frame,
            review,
            {i.source_id: i.group for i in frame.items},
            list(assessment.selected_ids),
            index,
        )


def test_cli_select_only(prepared: Prepared, tmp_path: Path) -> None:
    source, frame, review, assessment, _ = prepared
    for name, value in [("frame", frame), ("review", review), ("assessment", assessment)]:
        (tmp_path / (name + ".json")).write_bytes(json_bytes(value.model_dump(mode="json")))
    output = tmp_path / "selection.json"
    args = [
        "pilot-select",
        "--source-run",
        str(source),
        "--frame",
        str(tmp_path / "frame.json"),
        "--review",
        str(tmp_path / "review.json"),
        "--invariance-review",
        str(tmp_path / "assessment.json"),
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert json.loads(output.read_bytes())["selection_invariance"]["pending_ids"]
    assert main(args) != 0


@pytest.mark.parametrize("threat", ["shared_identifier", "review_duplicate", "identity_claim"])
def test_recorded_relationship_threats(prepared: Prepared, threat: str) -> None:
    from citeprobe.evaluation_models import IdentityIdentifier
    from citeprobe.research_models import DuplicateRecord, IdentityClaim

    _, frame, review, assessment, baseline = prepared
    selected = list(assessment.selected_ids)
    pending = assessment.pending_ids[0]
    target = selected[0]
    dataset = Dataset.model_validate(baseline["dataset"])
    index = IdentityIndex(dataset, IdentityMappings.model_validate(baseline["identity_mappings"]))
    if threat == "shared_identifier":
        frame = frame.model_copy(
            update={
                "items": tuple(
                    i.model_copy(
                        update={
                            "candidate": i.candidate.model_copy(
                                update={"arxiv_id": target.removeprefix("arxiv:")}
                            )
                        }
                    )
                    if i.source_id == pending
                    else i
                    for i in frame.items
                )
            }
        )
    elif threat == "review_duplicate":
        review = review.model_copy(
            update={
                "duplicates": (
                    DuplicateRecord(
                        duplicate_id="synthetic-possible",
                        category="POSSIBLE_DUPLICATE",
                        citation_ids=(target, pending),
                        reason="Synthetic unresolved version concern",
                    ),
                )
            }
        )
    else:
        review = review.model_copy(
            update={
                "claims": (
                    IdentityClaim(
                        claim_id="synthetic-unresolved",
                        citation_id=target,
                        identifiers=(
                            IdentityIdentifier(
                                namespace="arxiv", value=target.removeprefix("arxiv:")
                            ),
                        ),
                        basis="new_mapping",
                        relation="undetermined",
                        expression="unclear",
                        evidence_ids=("synthetic-only",),
                        rationale="Synthetic unresolved version",
                    ),
                )
            }
        )
    assessment = assessment.model_copy(
        update={"review_fingerprint": fingerprint(review.model_dump(mode="json"))}
    )
    with pytest.raises(ValueError, match="overlap|threatens"):
        certificate(
            assessment, frame, review, {i.source_id: i.group for i in frame.items}, selected, index
        )


def test_shortfall_blocks_even_if_all_completions_agree(prepared: Prepared) -> None:
    source, frame, review, assessment, _ = prepared
    first_group = {i.source_id for i in frame.items if i.group == "1-7"}
    review = review.model_copy(
        update={
            "decisions": tuple(
                d.model_copy(
                    update={
                        "disposition": "exclude",
                        "exclusion_kind": "eligibility",
                        "reason": "Synthetic eligibility failure",
                    }
                )
                if d.source_id in first_group
                else d
                for d in review.decisions
            )
        }
    )
    assessment = assessment.model_copy(
        update={"review_fingerprint": fingerprint(review.model_dump(mode="json"))}
    )
    with pytest.raises(ValueError):
        select_pilot(source, frame, review, invariance=assessment)
