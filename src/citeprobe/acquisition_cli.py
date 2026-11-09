"""Acquisition preparation/replay CLI; network requires a separate explicit opt-in."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import zlib
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from citeprobe.acquisition import replay_acquisition, reviewed_sample
from citeprobe.acquisition_models import (
    AcquisitionAudit,
    AcquisitionPlan,
    AcquisitionResponse,
    CuratorDecision,
)
from citeprobe.acquisition_sources import metadata_projection, source
from citeprobe.dataset import load_dataset
from citeprobe.evaluation_models import DataLabel
from citeprobe.evidence_extract import decoded_body
from citeprobe.evidence_io import begin_batch, capture_async, finish_batch
from citeprobe.evidence_models import EvidenceBudget, EvidenceRequest
from citeprobe.research_io import write_json
from citeprobe.research_models import ResearchManifest
from citeprobe.resolution_cli import check_output


def add_acquisition_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    plan = commands.add_parser("acquisition-plan", help="Prepare one request offline")
    plan.add_argument("--source", choices=("arxiv_atom", "acl_xml"), required=True)
    plan.add_argument(
        "--experiment", choices=("recent-preprints", "mutation-robustness"), required=True
    )
    plan.add_argument("--reference-date", type=date.fromisoformat)
    plan.add_argument("--planned-start", type=datetime.fromisoformat, required=True)
    plan.add_argument("--planned-end", type=datetime.fromisoformat, required=True)
    plan.add_argument("--max-records", type=int, default=5)
    plan.add_argument("--acl-commit")
    plan.add_argument("--acl-volume")
    plan.add_argument("--seed", type=int, default=0)
    plan.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("acquisition-replay", help="Build review queue offline")
    replay.add_argument("response", type=Path)
    replay.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("acquisition-run", help="One separately authorized discovery request")
    run.add_argument("plan", type=Path)
    run.add_argument("--authorize-live", action="store_true")
    run.add_argument("--authorization-reference", required=True)
    run.add_argument("--plan-sha256", required=True)
    run.add_argument("--output-dir", required=True, type=Path)
    curated = commands.add_parser(
        "acquisition-sample", help="Validate curator decisions and sample offline"
    )
    curated.add_argument("audit", type=Path, nargs="+")
    curated.add_argument("--dataset", type=Path, required=True)
    curated.add_argument("--manifest", type=Path, required=True)
    curated.add_argument("--decisions", type=Path, required=True)
    curated.add_argument("--output", type=Path, required=True)


async def live(
    plan: AcquisitionPlan,
    authorization: str,
    evidence_directory: Path,
    *,
    origin: DataLabel = "observed",
) -> AcquisitionResponse:
    request = source(plan).request(plan)
    url = str(httpx.URL(request.endpoint, params=request.params))
    budget = EvidenceBudget(
        budget_id=hashlib.sha256(plan.model_dump_json().encode()).hexdigest(),
        authorization_reference=authorization,
        origin=origin,
        maximum_requests=1,
        requests=(
            EvidenceRequest(
                url=url,
                source_kind="arxiv_atom" if plan.source == "arxiv_atom" else "acquisition_xml",
            ),
        ),
    )
    begin_batch(evidence_directory, budget)
    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=0),
        timeout=httpx.Timeout(20),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "CiteProbe/0.1 bounded-discovery-pilot"},
    ) as client:
        record = await capture_async(client, evidence_directory, budget, 1)
    finish_batch(evidence_directory)
    projection = None
    error = record.exception_type
    try:
        if record.http_status == 200 and record.body_complete and not error:
            raw = (evidence_directory / "request-001/body.bin").read_bytes()
            projection = metadata_projection(
                decoded_body(record, raw).decode(record.character_encoding or "utf-8-sig")
            )
    except (ValueError, OSError, LookupError, zlib.error) as exc:
        error = type(exc).__name__
    return AcquisitionResponse(
        origin=origin,
        plan=plan,
        request=request,
        started_at=record.started_at,
        finished_at=record.finished_at,
        http_status=record.http_status,
        exception_type=error if record.body_complete else error or "IncompleteRawResponse",
        response_body_sha256=record.raw_body_sha256,
        metadata_xml=projection,
        metadata_sha256=hashlib.sha256(projection.encode()).hexdigest() if projection else None,
        retry_after=record.response_headers.get("retry-after"),
        latency_ms=(record.finished_at - record.started_at).total_seconds() * 1000,
        authorization_reference=authorization,
    )


def run_acquisition(args: argparse.Namespace) -> int:
    if args.command == "acquisition-plan":
        check_output(args.output, [])
        plan = AcquisitionPlan(
            source=args.source,
            experiment=args.experiment,
            reference_date=args.reference_date,
            planned_started_at=args.planned_start,
            planned_finished_at=args.planned_end,
            max_records=args.max_records,
            acl_commit=args.acl_commit,
            acl_volume=args.acl_volume,
            seed=args.seed,
        )
        write_json(args.output, plan.model_dump_json(indent=2))
        print(
            "Offline plan only; submit its SHA-256 for separate live authorization: "
            + hashlib.sha256(args.output.read_bytes()).hexdigest()
        )
    elif args.command == "acquisition-replay":
        check_output(args.output, [args.response])
        response = AcquisitionResponse.model_validate_json(args.response.read_bytes())
        audit = replay_acquisition(response)
        write_json(args.output, audit.model_dump_json(indent=2))
        print(
            f"Offline review queue: {len(audit.items)} items, {audit.outcome}; "
            f"origin={response.origin}"
        )
    elif args.command == "acquisition-sample":
        check_output(args.output, [*args.audit, args.dataset, args.manifest, args.decisions])
        raw = json.loads(args.decisions.read_bytes())
        if not isinstance(raw, list):
            raise ValueError("Curator decisions must be a JSON list")
        plan_result = reviewed_sample(
            tuple(AcquisitionAudit.model_validate_json(p.read_bytes()) for p in args.audit),
            load_dataset(args.dataset),
            ResearchManifest.model_validate_json(args.manifest.read_bytes()),
            tuple(CuratorDecision.model_validate(value) for value in raw),
        )
        write_json(args.output, plan_result.model_dump_json(indent=2))
        print("Curated sampling validated offline; not authorization to collect benchmark results")
    else:
        if not args.authorize_live:
            raise ValueError(
                "Live acquisition requires separate authorization and --authorize-live"
            )
        content = args.plan.read_bytes()
        if hashlib.sha256(content).hexdigest() != args.plan_sha256:
            raise ValueError("Acquisition plan changed since authorization")
        plan = AcquisitionPlan.model_validate_json(content)
        if not plan.planned_started_at <= datetime.now(UTC) <= plan.planned_finished_at:
            raise ValueError("Outside approved planned acquisition window; no request made")
        # Create the exclusive run directory and retain the plan before any request.
        args.output_dir.mkdir(exist_ok=False)
        write_json(args.output_dir / "plan.json", plan.model_dump_json(indent=2))
        response = asyncio.run(
            live(plan, args.authorization_reference, args.output_dir / "http-evidence")
        )
        write_json(args.output_dir / "response.json", response.model_dump_json(indent=2))
        audit = replay_acquisition(response)
        write_json(args.output_dir / "audit.json", audit.model_dump_json(indent=2))
        print(
            f"One acquisition attempt: HTTP {response.http_status}; {audit.outcome}. Do not rerun."
        )
    return 0
