"""Version 2 continuation: approved volume policy and four immutable cached responses."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from citeprobe.acl_scope import FIXED, POLICY_ID, POLICY_PATH, scoped_collection
from citeprobe.evidence_io import json_bytes
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Model, Text
from citeprobe.pilot_models import PilotPlan, PilotRequest, PilotRun
from citeprobe.pilot_run import load_run, response_body
from citeprobe.research_models import Digest

SCOPE_STOP = "Required ACL volume absent or duplicated; no silent substitution"


class ScopedCache(Model):
    request_key: Text
    record_id: Digest
    raw_body_sha256: Digest
    manifest_sha256: Digest
    selected_volume_ids: tuple[str, ...]
    parsed_source_records: int


class ScopedACLContinuation(Model):
    schema_version: Literal["2.0"] = "2.0"
    continuation_id: Digest
    source_run_directory: Text
    source_run_id: Digest
    source_run_file_sha256: Digest
    source_plan_sha256: Digest
    scope_policy: Literal["B-ACL-S1-v1"] = "B-ACL-S1-v1"
    scope_amendment_sha256: Digest
    cached_responses: tuple[ScopedCache, ...] = Field(min_length=4, max_length=4)
    plan: PilotPlan
    maximum_requests: Literal[14] = 14
    requests: tuple[PilotRequest, ...] = Field(min_length=14, max_length=14)


def make_scoped_continuation(source: Path) -> ScopedACLContinuation:
    if (source / "scope-continuation.json").exists():
        raise ValueError("Version 2 requires the original four-response failed continuation")
    parent = load_run(source)
    if (
        parent.plan.stage != "b_enumeration"
        or parent.stopped_reason != SCOPE_STOP
        or len(parent.attempts) != 4
        or len(parent.plan.requests) != 18
        or [r.collection for r in parent.plan.requests[:4]]
        != ["P18", "P19", "2020.acl", "2021.acl"]
    ):
        raise ValueError("Version 2 cache must be exactly the four-response ACL prefix")
    document = Path(POLICY_PATH).read_bytes()
    policy = json.loads(document)
    if (
        policy.get("policy_id") != POLICY_ID
        or policy.get("fixed_volumes") != {key: list(value) for key, value in FIXED.items()}
        or policy.get("prospective_collections") != ["2022.acl", "2023.acl"]
    ):
        raise ValueError("Scope amendment and implemented version do not match")
    cached = []
    for row, attempt in zip(parent.plan.requests[:4], parent.attempts, strict=True):
        if attempt.disposition != "captured" or not attempt.evidence_directory:
            raise ValueError("Every cached ACL response must be present")
        directory = source / attempt.evidence_directory
        body, record = response_body(directory, row, parent.plan.origin)
        if (
            not parent.plan.planned_started_at
            <= record.started_at
            <= record.finished_at
            <= parent.plan.planned_finished_at
        ):
            raise ValueError("Cached response lies outside the planned collection window")
        selection = scoped_collection(body, row)
        cached.append(
            ScopedCache(
                request_key=row.key,
                record_id=record.record_id,
                raw_body_sha256=record.raw_body_sha256,
                manifest_sha256=hashlib.sha256(
                    (directory / "manifest.json").read_bytes()
                ).hexdigest(),
                selected_volume_ids=selection.selected_volume_ids,
                parsed_source_records=len(selection.items),
            )
        )
    value = ScopedACLContinuation(
        continuation_id="0" * 64,
        source_run_directory=str(source.resolve()),
        source_run_id=parent.run_id,
        source_run_file_sha256=hashlib.sha256((source / "run.json").read_bytes()).hexdigest(),
        source_plan_sha256=hashlib.sha256((source / "plan.json").read_bytes()).hexdigest(),
        scope_amendment_sha256=hashlib.sha256(document).hexdigest(),
        cached_responses=tuple(cached),
        plan=parent.plan,
        requests=parent.plan.requests[4:],
    )
    return value.model_copy(
        update={
            "continuation_id": fingerprint(
                value.model_dump(mode="json", exclude={"continuation_id"})
            )
        }
    )


def validate_scoped_continuation(value: ScopedACLContinuation) -> None:
    if value != make_scoped_continuation(Path(value.source_run_directory)):
        raise ValueError("Amended continuation scope, source evidence, hash or inventory mismatch")


def volume_manifest(directory: Path, run: PilotRun) -> dict[str, object]:
    collections: dict[str, dict[str, object]] = {}
    for row, attempt in zip(run.plan.requests, run.attempts, strict=False):
        if not row.collection or not attempt.evidence_directory:
            continue
        try:
            body, _ = response_body(directory / attempt.evidence_directory, row, run.plan.origin)
            selection = scoped_collection(body, row)
        except ValueError as error:
            collections[row.key] = {"status": "UNDETERMINED", "reason": str(error)}
        else:
            collections[row.key] = {
                "status": "PARSED",
                "collection": row.collection,
                "selected_source_volume_ids": list(selection.selected_volume_ids),
                "excluded_source_volume_ids": list(selection.excluded_volume_ids),
                "source_record_count": len(selection.items),
                "source_record_volumes": selection.source_record_volumes,
            }
    return {"schema_version": "1.0", "scope_policy": POLICY_ID, "collections": collections}


def verify_scoped_run(directory: Path, run: PilotRun) -> None:
    value = ScopedACLContinuation.model_validate_json(
        (directory / "scope-continuation.json").read_bytes()
    )
    validate_scoped_continuation(value)
    if (
        run.plan != value.plan
        or len(run.attempts) < 4
        or (directory / "continuation.json").exists()
    ):
        raise ValueError("Amended receipt/lineage mismatch")
    source = Path(value.source_run_directory)
    for index in range(4):
        relative = f"attempt-{index + 1:03d}"
        original, copied = source / relative, directory / relative
        files = {p.relative_to(original) for p in original.rglob("*") if p.is_file()}
        if files != {p.relative_to(copied) for p in copied.rglob("*") if p.is_file()} or any(
            (original / p).read_bytes() != (copied / p).read_bytes() for p in files
        ):
            raise ValueError("Amended cache differs from the original capture")
    if sum(a.disposition == "captured" for a in run.attempts[4:]) > value.maximum_requests:
        raise ValueError("Amended continuation exceeded its new request ceiling")
    if (directory / "scope-volumes.json").read_bytes() != json_bytes(
        volume_manifest(directory, run)
    ):
        raise ValueError("Explicit source-volume manifest does not reproduce")
