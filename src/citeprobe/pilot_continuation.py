"""One explicit continuation: reuse the retained first ACL response, never refetch it."""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field

from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Model, Text
from citeprobe.pilot_models import PilotPlan, PilotRequest, PilotRun
from citeprobe.pilot_run import collection_items, load_run, response_body
from citeprobe.research_models import Digest

OLD_STOP = "Missing explicit ACL identifier; do not infer record IDs"


class ACLContinuation(Model):
    schema_version: Literal["1.0"] = "1.0"
    continuation_id: Digest
    source_run_directory: Text
    source_run_id: Digest
    source_plan_sha256: Digest
    cached_body_sha256: Digest
    plan: PilotPlan
    maximum_requests: int = Field(strict=True, ge=1, le=17)
    requests: tuple[PilotRequest, ...]


def validate_reuse(plan: PilotPlan, source: Path) -> PilotRun:
    if (source / "continuation.json").exists():
        raise ValueError("Only the original single-response ACL failure may be reused")
    parent = load_run(source)
    if (
        parent.plan != plan
        or plan.stage != "b_enumeration"
        or parent.stopped_reason != OLD_STOP
        or len(parent.attempts) != 1
        or parent.attempts[0].disposition != "captured"
        or parent.attempts[0].evidence_directory != "attempt-001"
        or plan.requests[0].collection != "P18"
    ):
        raise ValueError("Continuation must reuse exactly the original failed P18 prefix")
    body, record = response_body(source / "attempt-001", plan.requests[0], plan.origin)
    if (
        not plan.planned_started_at
        <= record.started_at
        <= record.finished_at
        <= plan.planned_finished_at
    ):
        raise ValueError("Cached source collection is outside the planned window")
    collection_items(body, plan.requests[0])
    return parent


def make_continuation(source: Path) -> ACLContinuation:
    parent = load_run(source)
    validate_reuse(parent.plan, source)
    _, record = response_body(source / "attempt-001", parent.plan.requests[0], parent.plan.origin)
    value = ACLContinuation(
        continuation_id="0" * 64,
        source_run_directory=str(source.resolve()),
        source_run_id=parent.run_id,
        source_plan_sha256=hashlib.sha256((source / "plan.json").read_bytes()).hexdigest(),
        cached_body_sha256=record.raw_body_sha256,
        plan=parent.plan,
        maximum_requests=len(parent.plan.requests) - 1,
        requests=parent.plan.requests[1:],
    )
    return value.model_copy(
        update={
            "continuation_id": fingerprint(
                value.model_dump(mode="json", exclude={"continuation_id"})
            )
        }
    )


def validate_continuation(value: ACLContinuation) -> None:
    if value != make_continuation(Path(value.source_run_directory)):
        raise ValueError(
            "Continuation fingerprint, cached evidence or remaining inventory mismatch"
        )


def verify_continued_run(directory: Path, run: PilotRun) -> None:
    value = ACLContinuation.model_validate_json((directory / "continuation.json").read_bytes())
    validate_continuation(value)
    if (
        run.plan != value.plan
        or not run.attempts
        or run.attempts[0].key != run.plan.requests[0].key
    ):
        raise ValueError("Continued receipt does not match its parent inventory")
    source = Path(value.source_run_directory) / "attempt-001"
    cached = directory / "attempt-001"
    files = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}
    if files != {p.relative_to(cached) for p in cached.rglob("*") if p.is_file()} or any(
        (source / p).read_bytes() != (cached / p).read_bytes() for p in files
    ):
        raise ValueError("Reused ACL evidence differs from the original capture")
    if sum(a.disposition == "captured" for a in run.attempts[1:]) > value.maximum_requests:
        raise ValueError("Continuation exceeded its new request ceiling")
