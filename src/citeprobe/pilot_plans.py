"""Exact bounded request inventories, with approved conditional page slots."""

from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from citeprobe.evidence_models import EvidenceRequest
from citeprobe.identity import normalize_arxiv
from citeprobe.lookup_inputs import fingerprint
from citeprobe.pilot_models import ACLRevision, PilotFrame, PilotPlan, PilotRequest
from citeprobe.pilot_pin import COLLECTIONS, COMMIT_URL, verify_revision

AGE_DAYS = {"1-7": 4, "8-14": 11, "15-30": 22, "31-60": 45}


def api_url(params: dict[str, str]) -> str:
    return "https://export.arxiv.org/api/query?" + urlencode(params)


def inventory(plan: PilotPlan) -> tuple[PilotRequest, ...]:
    rows: list[PilotRequest] = []
    if plan.stage == "acl_resolution":
        return (
            PilotRequest(
                key="acl-upstream-commit",
                group="acl-pin",
                request=EvidenceRequest(url=COMMIT_URL, source_kind="upstream_json"),
            ),
        )
    if plan.stage in {"a_enumeration", "b_enumeration"}:
        days: list[tuple[str, date]] = []
        if plan.stage == "a_enumeration":
            if plan.experiment != "submission-age-pilot" or plan.reference_date is None:
                raise ValueError("A-S1 enumeration requires its own date basis and reference")
            days = [
                (group, plan.reference_date - timedelta(days=age))
                for group, age in AGE_DAYS.items()
            ]
        else:
            if plan.experiment != "mutation-robustness-pilot" or plan.revision is None:
                raise ValueError("B enumeration requires a genuine proven ACL pin")
            verify_revision(plan.revision)
            if plan.origin != plan.revision.origin:
                raise ValueError("ACL evidence and plan origin differ")
            for collection, volume in COLLECTIONS:
                rows.append(
                    PilotRequest(
                        key="acl-" + collection,
                        group="acl-" + collection,
                        collection=collection,
                        volume_filter=volume,
                        request=EvidenceRequest(
                            source_kind="acquisition_xml",
                            url=(
                                "https://raw.githubusercontent.com/acl-org/acl-anthology/"
                                f"{plan.revision.commit}/data/xml/{collection}.xml"
                            ),
                        ),
                    )
                )
            days = [(str(year), date(year, 6, 15)) for year in range(2018, 2024)]
        for group, day in days:
            for offset in (0, 100):
                value = day.strftime("%Y%m%d")
                params = {
                    "search_query": f"cat:cs.CL AND submittedDate:[{value}0000 TO {value}2359]",
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                    "max_results": "100",
                    "start": str(offset),
                }
                rows.append(
                    PilotRequest(
                        key=f"arxiv-{group}-{offset}",
                        group=group,
                        source_day=day,
                        offset=offset,
                        conditional=offset == 100,
                        request=EvidenceRequest(url=api_url(params), source_kind="arxiv_atom"),
                    )
                )
    elif plan.stage in {"id_batch", "v1_verification"}:
        if not plan.parent_frame_id or len(set(plan.source_ids)) != len(plan.source_ids):
            raise ValueError("Exact-ID stage requires a verified parent frame and unique IDs")
        limit = 24 if plan.experiment == "submission-age-pilot" else 18
        if not plan.source_ids or len(plan.source_ids) > limit:
            raise ValueError("Selected-ID inventory exceeds approved panel cap")
        if any(normalize_arxiv(value) != value for value in plan.source_ids):
            raise ValueError("Selected-ID requests require exact normalized arXiv base IDs")
        for index in range(0, len(plan.source_ids), 10 if plan.stage == "id_batch" else 1):
            ids = plan.source_ids[index : index + (10 if plan.stage == "id_batch" else 1)]
            url = (
                api_url({"id_list": ",".join(ids), "start": "0", "max_results": str(len(ids))})
                if plan.stage == "id_batch"
                else "https://arxiv.org/abs/" + ids[0]
            )
            rows.append(
                PilotRequest(
                    key=f"{plan.stage}-{index}",
                    group=plan.stage,
                    source_ids=ids,
                    request=EvidenceRequest(
                        url=url,
                        source_kind="arxiv_atom" if plan.stage == "id_batch" else "arxiv_abstract",
                    ),
                )
            )
    return tuple(rows)


def seal_plan(plan: PilotPlan) -> PilotPlan:
    return plan.model_copy(
        update={"plan_id": fingerprint(plan.model_dump(mode="json", exclude={"plan_id"}))}
    )


def make_plan(
    stage: str,
    experiment: str,
    start: datetime,
    finish: datetime,
    *,
    reference: date | None = None,
    revision: ACLRevision | None = None,
    frame: PilotFrame | None = None,
    origin: str = "observed",
) -> PilotPlan:
    if frame:
        if frame.frame_id != fingerprint(frame.model_dump(mode="json", exclude={"frame_id"})):
            raise ValueError("Parent frame fingerprint mismatch")
        experiment, reference, origin = frame.experiment, frame.reference_date, frame.origin
    ids = (
        tuple(
            sorted(
                item.candidate.arxiv_id
                for item in frame.items
                if item.source_id in frame.panel_ids and item.candidate.arxiv_id
            )
        )
        if frame
        else ()
    )
    # Construct a valid placeholder inventory, then replace it with canonical derived requests.
    provisional = PilotPlan.model_validate(
        {
            "plan_id": "0" * 64,
            "stage": stage,
            "experiment": experiment,
            "date_basis": "first_arxiv_submission"
            if experiment == "submission-age-pilot"
            else "canonical_bibliographic_year",
            "origin": origin,
            "reference_date": reference,
            "planned_started_at": start,
            "planned_finished_at": finish,
            "revision": revision,
            "parent_frame_id": frame.frame_id if frame else None,
            "source_ids": ids,
            "maximum_requests": 1,
            "requests": [
                {
                    "key": "placeholder",
                    "group": "placeholder",
                    "request": {
                        "url": "https://example.org/placeholder",
                        "source_kind": "arxiv_atom",
                    },
                }
            ],
        }
    )
    rows = inventory(provisional)
    plan = PilotPlan.model_validate(
        {**provisional.model_dump(), "requests": rows, "maximum_requests": len(rows)}
    )
    return seal_plan(plan)


def validate_plan(plan: PilotPlan) -> None:
    if plan.plan_id != seal_plan(plan).plan_id or plan.requests != inventory(plan):
        raise ValueError("Pilot plan fingerprint/request inventory mismatch")
    if any(
        r.source_day and r.source_day >= plan.planned_started_at.astimezone(UTC).date()
        for r in plan.requests
    ):
        raise ValueError("Source UTC day must be closed before planned acquisition")
