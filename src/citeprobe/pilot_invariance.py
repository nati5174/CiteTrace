"""A-SI-v1 sensitivity certificate; no hypothetical record becomes verified."""

import hashlib
from collections import Counter
from itertools import product
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from citeprobe.identity import IdentityIndex, normalize_identifier
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Model, Text
from citeprobe.pilot_models import PilotFrame, PilotReview
from citeprobe.research_models import Digest

POLICY = Path("docs/research/amendments/a-selection-invariance-v1.md")
COHORTS = ("1-7", "8-14", "15-30", "31-60")


class InvarianceAssessment(Model):
    schema_version: Literal["1.0"] = "1.0"
    policy: Literal["A-SI-v1"] = "A-SI-v1"
    policy_sha256: Digest
    frame_id: Digest
    review_fingerprint: Digest
    pending_ids: tuple[Text, ...] = Field(min_length=1, max_length=2)
    selected_ids: tuple[Text, ...] = Field(min_length=8, max_length=8)
    uncertainty: Literal["publisher_relationship_only"] = "publisher_relationship_only"
    no_selected_relationship_threat: Literal[True]
    reviewer_id: Text
    reviewed_at: AwareDatetime
    rationale: Text


def validate_assessment(
    assessment: InvarianceAssessment, frame: PilotFrame, review: PilotReview
) -> set[str]:
    pending = {d.source_id for d in review.decisions if d.disposition == "pending"}
    items = {i.source_id: i for i in frame.items}
    if (
        frame.experiment != "submission-age-pilot"
        or len(frame.panel_ids) != 24
        or Counter(items[k].group for k in frame.panel_ids) != dict.fromkeys(COHORTS, 6)
        or assessment.frame_id != frame.frame_id
        or assessment.review_fingerprint != fingerprint(review.model_dump(mode="json"))
        or assessment.policy_sha256 != hashlib.sha256(POLICY.read_bytes()).hexdigest()
        or len(set(assessment.pending_ids)) != len(assessment.pending_ids)
        or pending != set(assessment.pending_ids)
        or len(set(assessment.selected_ids)) != 8
        or not set(assessment.selected_ids) <= set(frame.panel_ids)
        or assessment.reviewer_id.upper() in {"UNASSIGNED", "PENDING", "UNKNOWN"}
        or assessment.reviewed_at < max(d.reviewed_at for d in review.decisions)
    ):
        raise ValueError("Invalid A invariance assessment, panel, review, policy or pending scope")
    return pending


def certificate(
    assessment: InvarianceAssessment,
    frame: PilotFrame,
    review: PilotReview,
    groups: dict[str, str],
    selected: list[str],
    identities: IdentityIndex,
) -> dict[str, object]:
    pending = validate_assessment(assessment, frame, review)
    approved = {d.source_id for d in review.decisions if d.disposition == "include"}
    if set(selected) != set(assessment.selected_ids) or not set(selected) <= approved:
        raise ValueError("Proposed eight differ from the approved selection")
    completions = []
    ordered_pending = sorted(pending)
    for mask in product((False, True), repeat=len(ordered_pending)):
        hypothetical = [k for k, included in zip(ordered_pending, mask, strict=True) if included]
        candidates = approved | set(hypothetical)
        chosen = []
        for group in COHORTS:
            ranked = sorted(
                (k for k in candidates if groups[k] == group),
                key=lambda k: (
                    hashlib.sha256(
                        ("citeprobe-A-submission-v1|seed=0|" + k.removeprefix("arxiv:")).encode()
                    ).hexdigest(),
                    k,
                ),
            )
            if len(ranked) < 2:
                raise ValueError("Eligibility completion has a cohort shortfall")
            chosen.extend(ranked[:2])
        if chosen != selected:
            raise ValueError("Selection changes under a pending eligibility completion")
        completions.append(
            {"hypothetically_eligible_pending_ids": hypothetical, "selected": chosen}
        )

    selected_set = set(selected)
    # Conservative: any recorded possible duplicate involving a selected record blocks.
    for item in frame.items:
        if item.possible_duplicates and (
            item.source_id in selected_set or selected_set.intersection(item.possible_duplicates)
        ):
            raise ValueError("Unresolved source duplicate/version flag threatens selection")
    for duplicate in review.duplicates:
        if duplicate.category == "POSSIBLE_DUPLICATE" and selected_set.intersection(
            duplicate.citation_ids
        ):
            raise ValueError(
                "Unresolved reviewed duplicate/version relationship threatens selection"
            )
    selected_keys = set().union(*(identities.same[k] for k in selected))
    for item in frame.items:
        if item.source_id not in pending:
            continue
        c = item.candidate
        keys = ({"arxiv:" + c.arxiv_id} if c.arxiv_id else set()) | (
            {"doi:" + c.doi.lower(), "crossref:" + c.doi.lower()} if c.doi else set()
        )
        if keys & selected_keys:
            raise ValueError("Pending source identifiers overlap the selected identities")
    for claim in review.claims:
        if claim.conflict or claim.relation == "undetermined":
            keys = {k for i in claim.identifiers if (k := normalize_identifier(i)) is not None}
            if claim.citation_id in selected_set or keys & selected_keys:
                raise ValueError("Unresolved identity claim threatens selection")
    return {
        "policy": assessment.policy,
        "policy_sha256": assessment.policy_sha256,
        "assessment_fingerprint": fingerprint(assessment.model_dump(mode="json")),
        "pending_ids": ordered_pending,
        "panel_dispositions": {d.source_id: d.disposition for d in review.decisions},
        "pending_reasons": {
            d.source_id: d.reason for d in review.decisions if d.source_id in pending
        },
        "completions": completions,
        "fully_adjudicated_panel": False,
        "relationship_limit": (
            "Recorded evidence plus explicit curator assessment; not exhaustive proof"
        ),
    }
