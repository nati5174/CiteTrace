"""Bounded authorized execution and complete offline enumeration replay."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from citeprobe.acquisition_sources import SEARCH, ACLXml, ArxivAtom, text, xml_root
from citeprobe.evidence_extract import decoded_body
from citeprobe.evidence_io import (
    begin_batch,
    capture_sync,
    finish_batch,
    json_bytes,
    verify_batch,
    write,
)
from citeprobe.evidence_models import EvidenceBudget, RawEvidence
from citeprobe.lookup_inputs import fingerprint
from citeprobe.pilot_models import Attempt, PilotFrame, PilotItem, PilotPlan, PilotRequest, PilotRun
from citeprobe.pilot_plans import validate_plan

if TYPE_CHECKING:
    from citeprobe.pilot_resource_continuation import ResourceACLContinuation
    from citeprobe.pilot_scope_continuation import ScopedACLContinuation


def response_body(
    bundle: Path, row: PilotRequest, origin: str, *, decoded_limit: int = 2_000_000
) -> tuple[str, RawEvidence]:
    verify_batch(bundle)
    record = RawEvidence.model_validate_json((bundle / "request-001/record.json").read_bytes())
    if record.request != row.request or record.origin != origin:
        raise ValueError("Response request/origin differs from pilot inventory")
    if record.http_status != 200 or not record.body_complete or record.exception_type:
        raise ValueError("Failed/incomplete source attempt; no retry or replacement")
    return decoded_body(
        record, (bundle / "request-001/body.bin").read_bytes(), limit=decoded_limit
    ).decode(record.character_encoding or "utf-8-sig"), record


def page_items(body: str, row: PilotRequest) -> tuple[list[PilotItem], int]:
    adapter = ArxivAtom()
    records, total = adapter.records(body)
    root = xml_root(body)
    if total is None or total < 0 or total > 200:
        raise ValueError("Missing total or source-day page budget exceeded")
    if text(root, SEARCH + "startIndex") != str(row.offset):
        raise ValueError("Incorrect source page offset")
    expected = min(100, max(0, total - (row.offset or 0)))
    if len(records) != expected:
        raise ValueError("Source page missing records or terminal page does not reconcile")
    page_size = text(root, SEARCH + "itemsPerPage")
    if page_size not in {"100", str(expected)}:
        raise ValueError("Source itemsPerPage mismatch")
    items = []
    for record in records:
        candidate = adapter.candidate(record)
        if (
            not candidate.submitted_at
            or candidate.submitted_at.astimezone(UTC).date() != row.source_day
        ):
            raise ValueError("Source query/submission-day contradiction")
        items.append(
            PilotItem(
                source_id="arxiv:" + str(candidate.arxiv_id),
                group=row.group,
                candidate=candidate,
                run_request_key=row.key,
            )
        )
    return items, total


def collection_items(body: str, row: PilotRequest) -> list[PilotItem]:
    root = xml_root(body, preserve_comments=True)
    if root.tag != "collection" or root.get("id") != row.collection:
        raise ValueError("Pinned ACL collection identity mismatch")
    volumes = [v for v in root.findall("volume") if v.get("id") == row.volume_filter]
    if len(volumes) != 1:
        raise ValueError("Required ACL volume absent or duplicated; no silent substitution")
    filtered = type(root)("collection", root.attrib)
    filtered.append(volumes[0])
    from xml.etree import ElementTree as ET

    records, count = ACLXml().records(ET.tostring(filtered, encoding="unicode"))
    if not count:
        raise ValueError("Empty approved ACL volume")
    items = []
    for record in records:
        candidate = ACLXml().candidate(record)
        if not 2018 <= candidate.year <= 2023:
            raise ValueError("ACL canonical year outside B scope")
        items.append(
            PilotItem(
                source_id="acl:" + candidate.source_record_id,
                group=row.group,
                candidate=candidate,
                run_request_key=row.key,
            )
        )
    return items


def validate_selected(body: str, row: PilotRequest) -> None:
    records, _ = ArxivAtom().records(body)
    returned = [ArxivAtom().candidate(r).arxiv_id for r in records]
    if len(returned) != len(set(returned)) or set(returned) != set(row.source_ids):
        raise ValueError("Selected-ID batch has missing/duplicate/unrequested source IDs")


def execute(
    plan: PilotPlan,
    directory: Path,
    client: httpx.Client,
    authorization: str,
    *,
    reuse_from: Path | None = None,
    scoped: ScopedACLContinuation | None = None,
    resource: ResourceACLContinuation | None = None,
) -> PilotRun:
    validate_plan(plan)
    continuation = None
    reused_count = 0
    if resource is not None:
        from citeprobe.pilot_resource_continuation import validate_resource_continuation

        validate_resource_continuation(resource)
        if resource.plan != plan or reuse_from is not None or scoped is not None:
            raise ValueError("Resource continuation context differs from its preserved parent")
        reuse_from = Path(resource.source_run_directory)
        reused_count = 5
    elif scoped is not None:
        from citeprobe.pilot_scope_continuation import validate_scoped_continuation

        validate_scoped_continuation(scoped)
        if scoped.plan != plan or reuse_from is not None:
            raise ValueError("Amended scope context differs from its parent plan")
        reuse_from = Path(scoped.source_run_directory)
        reused_count = 4
    elif reuse_from is not None:
        if reuse_from.resolve() in directory.resolve().parents:
            raise ValueError("Continuation output must be outside the original source run")
        from citeprobe.pilot_continuation import make_continuation

        continuation = make_continuation(reuse_from)
        if continuation.plan != plan:
            raise ValueError("Cached ACL source and continuation plan differ")
        reused_count = 1
    if reuse_from is not None and reuse_from.resolve() in directory.resolve().parents:
        raise ValueError("Continuation output must be outside the original source run")
    directory.mkdir(exist_ok=False)
    write(directory / "plan.json", json_bytes(plan.model_dump(mode="json")))
    attempts: list[Attempt] = []
    if reused_count:
        assert reuse_from is not None
        for index in range(reused_count):
            relative = f"attempt-{index + 1:03d}"
            shutil.copytree(reuse_from / relative, directory / relative)
            attempts.append(
                Attempt(
                    key=plan.requests[index].key,
                    disposition="captured",
                    evidence_directory=relative,
                )
            )
    if continuation is not None:
        write(directory / "continuation.json", json_bytes(continuation.model_dump(mode="json")))
    if scoped is not None:
        write(directory / "scope-continuation.json", json_bytes(scoped.model_dump(mode="json")))
    if resource is not None:
        write(
            directory / "resource-continuation.json", json_bytes(resource.model_dump(mode="json"))
        )
    totals: dict[str, int] = {}
    identities: dict[str, set[str]] = {}
    stopped = None
    for index, row in enumerate(plan.requests):
        if index < reused_count:
            continue
        if not plan.planned_started_at <= datetime.now(UTC) <= plan.planned_finished_at:
            stopped = "Actual acquisition is outside the planned authorization window"
            break
        if row.conditional and totals.get(row.group, 0) <= 100:
            attempts.append(
                Attempt(key=row.key, disposition="not_required", evidence_directory=None)
            )
            continue
        budget = EvidenceBudget(
            budget_id=f"{plan.plan_id}:{row.key}",
            origin=plan.origin,
            authorization_reference=authorization,
            maximum_requests=1,
            requests=(row.request,),
        )
        relative = f"attempt-{index + 1:03d}"
        bundle = directory / relative
        begin_batch(bundle, budget)
        attempts.append(Attempt(key=row.key, disposition="captured", evidence_directory=relative))
        limit = 2_000_000
        if resource is not None:
            from citeprobe.source_limits import recovery_limit

            limit = recovery_limit(row.request)
        capture_sync(client, bundle, budget, 1, raw_limit=limit)
        finish_batch(bundle)
        try:
            body, _ = response_body(bundle, row, plan.origin, decoded_limit=limit)
            if resource is not None and row.collection == "2023.acl":
                from citeprobe.pilot_resource_continuation import validate_recovered_body

                validate_recovered_body(bundle, resource)
            if row.offset is not None:
                items, total = page_items(body, row)
                if row.group in totals and totals[row.group] != total:
                    raise ValueError("Source totals changed between pages")
                totals[row.group] = total
                seen = identities.setdefault(row.group, set())
                if any(i.source_id in seen for i in items) or len(
                    {i.source_id for i in items}
                ) != len(items):
                    raise ValueError("Duplicate source IDs/unstable page ordering")
                seen.update(i.source_id for i in items)
            elif row.collection:
                if scoped is not None or resource is not None:
                    from citeprobe.acl_scope import scoped_collection

                    scoped_collection(body, row, limit=limit)
                else:
                    collection_items(body, row)
            elif plan.stage == "id_batch":
                validate_selected(body, row)
        except ValueError as error:
            stopped = str(error)
            break
        if index < len(plan.requests) - 1:
            import time

            time.sleep(3)
    run = PilotRun(run_id="0" * 64, plan=plan, attempts=tuple(attempts), stopped_reason=stopped)
    run = run.model_copy(
        update={"run_id": fingerprint(run.model_dump(mode="json", exclude={"run_id"}))}
    )
    write(directory / "run.json", json_bytes(run.model_dump(mode="json")))
    if scoped is not None:
        from citeprobe.pilot_scope_continuation import volume_manifest

        write(directory / "scope-volumes.json", json_bytes(volume_manifest(directory, run)))
    if resource is not None:
        from citeprobe.pilot_resource_continuation import resource_volume_manifest

        write(
            directory / "scope-volumes.json",
            json_bytes(resource_volume_manifest(directory, run, resource)),
        )
    return run


def load_run(directory: Path) -> PilotRun:
    run = PilotRun.model_validate_json((directory / "run.json").read_bytes())
    validate_plan(run.plan)
    if run.run_id != fingerprint(run.model_dump(mode="json", exclude={"run_id"})):
        raise ValueError("Pilot receipt fingerprint mismatch")
    saved = PilotPlan.model_validate_json((directory / "plan.json").read_bytes())
    if saved != run.plan or len(run.attempts) > run.plan.maximum_requests:
        raise ValueError("Pilot receipt/plan budget mismatch")
    expected = {"plan.json", "run.json"} | {
        str(a.evidence_directory) for a in run.attempts if a.disposition == "captured"
    }
    if (directory / "continuation.json").exists():
        expected.add("continuation.json")
    if (directory / "scope-continuation.json").exists():
        expected.update({"scope-continuation.json", "scope-volumes.json"})
    if (directory / "resource-continuation.json").exists():
        expected.update({"resource-continuation.json", "scope-volumes.json"})
    if {p.name for p in directory.iterdir()} != expected:
        raise ValueError("Pilot run contains unrecorded files or attempts")
    for index, attempt in enumerate(run.attempts):
        row = run.plan.requests[index]
        if attempt.key != row.key:
            raise ValueError("Attempt inventory differs from exact plan")
        if attempt.disposition == "captured":
            if attempt.evidence_directory != f"attempt-{index + 1:03d}":
                raise ValueError("Unsafe or inconsistent evidence path")
            verify_batch(directory / attempt.evidence_directory)
            budget = EvidenceBudget.model_validate_json(
                (directory / attempt.evidence_directory / "budget.json").read_bytes()
            )
            if (
                budget.budget_id != f"{run.plan.plan_id}:{row.key}"
                or budget.requests != (row.request,)
                or budget.origin != run.plan.origin
                or budget.maximum_requests != 1
            ):
                raise ValueError("Captured request budget is inconsistent with the authorized plan")
        elif not row.conditional or attempt.evidence_directory:
            raise ValueError("Unapproved skipped request")
    if (directory / "continuation.json").exists():
        from citeprobe.pilot_continuation import verify_continued_run

        verify_continued_run(directory, run)
    if (directory / "scope-continuation.json").exists():
        from citeprobe.pilot_scope_continuation import verify_scoped_run

        verify_scoped_run(directory, run)
    if (directory / "resource-continuation.json").exists():
        from citeprobe.pilot_resource_continuation import verify_resource_run

        verify_resource_run(directory, run)
    return run


def build_frame(directory: Path) -> PilotFrame:
    run = load_run(directory)
    if run.plan.stage not in {"a_enumeration", "b_enumeration"} or run.stopped_reason:
        raise ValueError("Only complete successful enumeration becomes a sampling frame")
    if len(run.attempts) != len(run.plan.requests):
        raise ValueError("Enumeration receipt is incomplete")
    scoped = None
    resource = None
    if (directory / "scope-continuation.json").exists():
        from citeprobe.pilot_scope_continuation import ScopedACLContinuation

        scoped = ScopedACLContinuation.model_validate_json(
            (directory / "scope-continuation.json").read_bytes()
        )
    if (directory / "resource-continuation.json").exists():
        from citeprobe.pilot_resource_continuation import ResourceACLContinuation

        resource = ResourceACLContinuation.model_validate_json(
            (directory / "resource-continuation.json").read_bytes()
        )
    groups: dict[str, list[PilotItem]] = {}
    totals: dict[str, int] = {}
    all_items: list[PilotItem] = []
    for row, attempt in zip(run.plan.requests, run.attempts, strict=True):
        if attempt.disposition == "not_required":
            if row.group not in totals or totals[row.group] > 100:
                raise ValueError("Required second page was skipped")
            continue
        limit = 2_000_000
        if resource is not None:
            from citeprobe.source_limits import recovery_limit

            limit = recovery_limit(row.request)
        bundle = directory / str(attempt.evidence_directory)
        body, record = response_body(bundle, row, run.plan.origin, decoded_limit=limit)
        if resource is not None and row.collection == "2023.acl":
            from citeprobe.pilot_resource_continuation import validate_recovered_body

            validate_recovered_body(bundle, resource)
        if (
            not run.plan.planned_started_at
            <= record.started_at
            <= record.finished_at
            <= run.plan.planned_finished_at
        ):
            raise ValueError("Actual source collection lies outside approved plan window")
        if row.offset is not None:
            if row.conditional and totals.get(row.group, 0) <= 100:
                raise ValueError("Unnecessary conditional page was captured")
            items, total = page_items(body, row)
            if row.group in totals and totals[row.group] != total:
                raise ValueError("Changed source total")
            totals[row.group] = total
        else:
            if scoped is not None or resource is not None:
                from citeprobe.acl_scope import scoped_collection

                items = list(scoped_collection(body, row, limit=limit).items)
            else:
                items = collection_items(body, row)
        existing = groups.setdefault(row.group, [])
        if len({i.source_id for i in [*existing, *items]}) != len(existing) + len(items):
            raise ValueError("Duplicate source-paper records in complete inventory")
        existing.extend(items)
        all_items.extend(items)
    if any(len(groups[group]) != total for group, total in totals.items()):
        raise ValueError("Complete day enumeration totals do not reconcile")
    if len({i.source_id for i in all_items}) != len(all_items):
        raise ValueError("Duplicate source IDs across source-day/collection inventories")
    exclusions = {}
    panel: list[str] = []
    shortfalls = {}
    for group, items in groups.items():
        eligible = []
        for item in items:
            if item.source_id.startswith("arxiv:") and item.candidate.primary_category != "cs.CL":
                exclusions[item.source_id] = (
                    "missing_primary_category"
                    if not item.candidate.primary_category
                    else "primary_category_not_cs.CL"
                )
            else:
                eligible.append(item)
        a = run.plan.experiment == "submission-age-pilot"
        prefix = (
            "citeprobe-A-submission-panel-v1|seed=0|"
            if a
            else "citeprobe-B-pilot-panel-v1|seed=0|"
            + ("acl|" if group.startswith("acl-") else "arxiv|")
        )
        ordered = sorted(
            eligible,
            key=lambda i: (
                hashlib.sha256(
                    (prefix + (i.candidate.arxiv_id or i.candidate.source_record_id)).encode()
                ).hexdigest(),
                i.source_id,
            ),
        )
        count = 6 if a else 2 if group.startswith("acl-") else 1
        panel.extend(i.source_id for i in ordered[:count])
        shortfalls[group] = max(0, count - len(ordered))
    # Similarity flags never remove or merge a candidate.
    flagged = []
    for item in all_items:
        others = tuple(
            sorted(
                o.source_id
                for o in all_items
                if o.source_id != item.source_id
                and (
                    (o.candidate.title.casefold(), o.candidate.authors)
                    == (item.candidate.title.casefold(), item.candidate.authors)
                    or (item.candidate.doi and o.candidate.doi == item.candidate.doi)
                )
            )
        )
        flagged.append(item.model_copy(update={"possible_duplicates": others}))
    frame = PilotFrame(
        frame_id="0" * 64,
        run_id=run.run_id,
        plan_id=(
            resource.continuation_id
            if resource is not None
            else scoped.continuation_id
            if scoped is not None
            else run.plan.plan_id
        ),
        experiment=run.plan.experiment,
        origin=run.plan.origin,
        reference_date=run.plan.reference_date,
        items=tuple(flagged),
        panel_ids=tuple(panel),
        exclusions=exclusions,
        panel_shortfalls=shortfalls,
    )
    return frame.model_copy(
        update={"frame_id": fingerprint(frame.model_dump(mode="json", exclude={"frame_id"}))}
    )
