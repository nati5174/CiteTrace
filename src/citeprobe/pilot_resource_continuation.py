"""Version 3: five complete caches and one explicit, larger-bound ACL 2023 attempt."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from citeprobe.acl_scope import POLICY_PATH, scoped_collection
from citeprobe.evidence_extract import decoded_body
from citeprobe.evidence_io import json_bytes
from citeprobe.evidence_models import RawEvidence
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Model, Text
from citeprobe.pilot_models import PilotPlan, PilotRequest, PilotRun
from citeprobe.pilot_run import load_run, response_body
from citeprobe.pilot_scope_continuation import ScopedCache
from citeprobe.research_models import Digest
from citeprobe.source_limits import (
    ACL_2023_LIMIT,
    ACL_2023_URL,
    DEFAULT_LIMIT,
    RESOURCE_POLICY_PATH,
    recovery_limit,
)

PROPOSED_AUTHORIZATION_REFERENCE = "A-S1-immediate-v1-B-resource-limit-v1"


class RequestLimits(Model):
    request_key: Text
    url: Text
    capture_bytes: Literal[2000000, 4000000]
    decoded_bytes: Literal[2000000, 4000000]
    xml_bytes: Literal[2000000, 4000000]


class TruncatedCapture(Model):
    record_id: Digest
    prefix_sha256: Digest
    manifest_sha256: Digest
    prefix_bytes: Literal[2000000] = 2000000
    advertised_bytes: int = Field(strict=True, gt=2000000, le=4000000)


class ResourceACLContinuation(Model):
    schema_version: Literal["3.0", "3.1"] = "3.1"
    proposed_authorization_reference: Literal["A-S1-immediate-v1-B-resource-limit-v1"] | None = None
    continuation_id: Digest
    source_run_directory: Text
    source_run_id: Digest
    source_run_file_sha256: Digest
    scope_policy: Literal["B-ACL-S1-v1"] = "B-ACL-S1-v1"
    scope_amendment_sha256: Digest
    resource_policy: Literal["B-ACL-R1-v1"] = "B-ACL-R1-v1"
    resource_amendment_sha256: Digest
    cached_responses: tuple[ScopedCache, ...] = Field(min_length=5, max_length=5)
    failed_capture: TruncatedCapture
    plan: PilotPlan
    maximum_requests: Literal[13] = 13
    maximum_exception_url_attempts: Literal[1] = 1
    requests: tuple[PilotRequest, ...] = Field(min_length=13, max_length=13)
    per_request_limits: tuple[RequestLimits, ...] = Field(min_length=13, max_length=13)


def make_resource_continuation(source: Path) -> ResourceACLContinuation:
    if (source / "resource-continuation.json").exists():
        raise ValueError("The one-time exception cannot resume or repeat a version 3 stage")
    if not (source / "scope-continuation.json").exists():
        raise ValueError("Resource recovery requires the preserved version 2 failure")
    parent = load_run(source)
    if (
        len(parent.attempts) != 6
        or parent.plan.stage != "b_enumeration"
        or parent.stopped_reason != "Failed/incomplete source attempt; no retry or replacement"
        or len(parent.plan.requests) != 18
        or parent.plan.requests[5].request.url != ACL_2023_URL
    ):
        raise ValueError("Resource recovery source is not the approved six-attempt ACL failure")
    resource_doc = Path(RESOURCE_POLICY_PATH).read_bytes()
    policy = json.loads(resource_doc)
    if (
        policy.get("policy_id") != "B-ACL-R1-v1"
        or policy.get("exception_url") != ACL_2023_URL
        or any(
            policy.get(k) != ACL_2023_LIMIT
            for k in ("maximum_capture_bytes", "maximum_decoded_bytes", "maximum_xml_bytes")
        )
        or policy.get("default_other_request_limits") != DEFAULT_LIMIT
        or policy.get("maximum_new_attempts_for_exception_url") != 1
    ):
        raise ValueError("Resource amendment does not match the narrowly implemented exception")
    cached = []
    for row, attempt in zip(parent.plan.requests[:5], parent.attempts[:5], strict=True):
        if attempt.disposition != "captured" or not attempt.evidence_directory:
            raise ValueError("Five complete ACL caches are required")
        bundle = source / attempt.evidence_directory
        body, record = response_body(bundle, row, parent.plan.origin)
        if (
            not parent.plan.planned_started_at
            <= record.started_at
            <= record.finished_at
            <= parent.plan.planned_finished_at
        ):
            raise ValueError("Cache collection time outside the approved window")
        selection = scoped_collection(body, row)
        cached.append(
            ScopedCache(
                request_key=row.key,
                record_id=record.record_id,
                raw_body_sha256=record.raw_body_sha256,
                manifest_sha256=hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(),
                selected_volume_ids=selection.selected_volume_ids,
                parsed_source_records=len(selection.items),
            )
        )
    failed_bundle = source / "attempt-006"
    failed = RawEvidence.model_validate_json(
        (failed_bundle / "request-001/record.json").read_bytes()
    )
    length = failed.response_headers.get("content-length", "")
    if (
        failed.request != parent.plan.requests[5].request
        or failed.http_status != 200
        or failed.body_complete
        or failed.exception_type != "ValueError"
        or failed.raw_body_size != DEFAULT_LIMIT
        or not length.isdigit()
        or failed.content_encoding not in {None, "identity"}
        or not parent.plan.planned_started_at
        <= failed.started_at
        <= failed.finished_at
        <= parent.plan.planned_finished_at
    ):
        raise ValueError("Preserved attempt is not the known identity-encoded local-cap failure")
    truncated = TruncatedCapture(
        record_id=failed.record_id,
        prefix_sha256=failed.raw_body_sha256,
        manifest_sha256=hashlib.sha256((failed_bundle / "manifest.json").read_bytes()).hexdigest(),
        advertised_bytes=int(length),
    )
    requests = parent.plan.requests[5:]
    limits = tuple(
        RequestLimits(
            request_key=r.key,
            url=r.request.url,
            capture_bytes=recovery_limit(r.request),
            decoded_bytes=recovery_limit(r.request),
            xml_bytes=recovery_limit(r.request),
        )
        for r in requests
    )
    value = ResourceACLContinuation(
        schema_version="3.1",
        proposed_authorization_reference=PROPOSED_AUTHORIZATION_REFERENCE,
        continuation_id="0" * 64,
        source_run_directory=str(source.resolve()),
        source_run_id=parent.run_id,
        source_run_file_sha256=hashlib.sha256((source / "run.json").read_bytes()).hexdigest(),
        scope_amendment_sha256=hashlib.sha256(Path(POLICY_PATH).read_bytes()).hexdigest(),
        resource_amendment_sha256=hashlib.sha256(resource_doc).hexdigest(),
        cached_responses=tuple(cached),
        failed_capture=truncated,
        plan=parent.plan,
        requests=requests,
        per_request_limits=limits,
    )
    return value.model_copy(
        update={
            "continuation_id": fingerprint(
                value.model_dump(mode="json", exclude={"continuation_id"})
            )
        }
    )


def validate_resource_continuation(value: ResourceACLContinuation) -> None:
    expected = make_resource_continuation(Path(value.source_run_directory))
    if value.schema_version == "3.0":
        legacy = expected.model_copy(
            update={"schema_version": "3.0", "proposed_authorization_reference": None}
        )
        expected = legacy.model_copy(
            update={
                "continuation_id": fingerprint(
                    legacy.model_dump(
                        mode="json",
                        exclude={"continuation_id", "proposed_authorization_reference"},
                    )
                )
            }
        )
    if value != expected:
        raise ValueError(
            "Resource continuation cache, failure evidence, policy, limit or inventory mismatch"
        )


def validate_recovered_body(bundle: Path, value: ResourceACLContinuation) -> None:
    record = RawEvidence.model_validate_json((bundle / "request-001/record.json").read_bytes())
    if record.request.url != ACL_2023_URL or not record.body_complete or record.exception_type:
        raise ValueError("New ACL 2023 response is not complete")
    data = decoded_body(
        record, (bundle / "request-001/body.bin").read_bytes(), limit=ACL_2023_LIMIT
    )
    if (
        len(data) != value.failed_capture.advertised_bytes
        or hashlib.sha256(data[: value.failed_capture.prefix_bytes]).hexdigest()
        != value.failed_capture.prefix_sha256
    ):
        raise ValueError(
            "Recovered ACL 2023 representation disagrees with the preserved prefix/length"
        )


def resource_volume_manifest(
    directory: Path, run: PilotRun, value: ResourceACLContinuation
) -> dict[str, object]:
    collections: dict[str, dict[str, object]] = {}
    for row, attempt in zip(run.plan.requests, run.attempts, strict=False):
        if not row.collection or not attempt.evidence_directory:
            continue
        bundle = directory / attempt.evidence_directory
        try:
            limit = recovery_limit(row.request)
            body, _ = response_body(bundle, row, run.plan.origin, decoded_limit=limit)
            if row.request.url == ACL_2023_URL:
                validate_recovered_body(bundle, value)
            selection = scoped_collection(body, row, limit=limit)
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
                "processing_bound_bytes": limit,
            }
    return {
        "schema_version": "3.0",
        "scope_policy": value.scope_policy,
        "resource_policy": value.resource_policy,
        "collections": collections,
    }


def verify_resource_run(directory: Path, run: PilotRun) -> None:
    value = ResourceACLContinuation.model_validate_json(
        (directory / "resource-continuation.json").read_bytes()
    )
    validate_resource_continuation(value)
    if (
        run.plan != value.plan
        or len(run.attempts) < 5
        or any(
            (directory / name).exists() for name in ("scope-continuation.json", "continuation.json")
        )
    ):
        raise ValueError("Resource receipt/lineage mismatch")
    source = Path(value.source_run_directory)
    for index in range(5):
        relative = f"attempt-{index + 1:03d}"
        original, copied = source / relative, directory / relative
        files = {p.relative_to(original) for p in original.rglob("*") if p.is_file()}
        if files != {p.relative_to(copied) for p in copied.rglob("*") if p.is_file()} or any(
            (original / p).read_bytes() != (copied / p).read_bytes() for p in files
        ):
            raise ValueError("Resource cache differs from its original complete capture")
    if sum(a.disposition == "captured" for a in run.attempts[5:]) > value.maximum_requests:
        raise ValueError("Resource continuation exceeded its new request ceiling")
    if (directory / "scope-volumes.json").read_bytes() != json_bytes(
        resource_volume_manifest(directory, run, value)
    ):
        raise ValueError("Resource-aware source volume manifest does not reproduce")
