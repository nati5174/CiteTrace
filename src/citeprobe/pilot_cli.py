"""Pilot preparation and offline review; the sole live path needs explicit authorization."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from citeprobe.evidence_io import json_bytes, write
from citeprobe.pilot_continuation import ACLContinuation, validate_continuation
from citeprobe.pilot_invariance import InvarianceAssessment
from citeprobe.pilot_models import ACLRevision, PilotDecision, PilotFrame, PilotPlan, PilotReview
from citeprobe.pilot_pin import pin_revision
from citeprobe.pilot_plans import make_plan, validate_plan
from citeprobe.pilot_resource_continuation import (
    ResourceACLContinuation,
    make_resource_continuation,
    validate_resource_continuation,
)
from citeprobe.pilot_review import freeze_pilot, select_pilot, verify_pilot
from citeprobe.pilot_run import build_frame, execute, load_run, response_body, validate_selected
from citeprobe.pilot_scope_continuation import (
    ScopedACLContinuation,
    make_scoped_continuation,
    validate_scoped_continuation,
)


def add_pilot_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    resource = commands.add_parser(
        "pilot-plan-resource-continuation",
        help="Prepare one-request resource exception and remaining arXiv inventory offline",
    )
    resource.add_argument("--source-run", type=Path, required=True)
    resource.add_argument("--output", type=Path, required=True)
    scoped = commands.add_parser(
        "pilot-plan-scoped-continuation", help="Prepare amended four-cache continuation offline"
    )
    scoped.add_argument("--source-run", type=Path, required=True)
    scoped.add_argument("--output", type=Path, required=True)
    for name in (
        "pilot-plan-a",
        "pilot-plan-b",
        "pilot-plan-acl-resolution",
        "pilot-plan-followup",
    ):
        command = commands.add_parser(name, help="Prepare an exact bounded inventory offline")
        command.add_argument("--planned-start", type=datetime.fromisoformat, required=True)
        command.add_argument("--planned-end", type=datetime.fromisoformat, required=True)
        command.add_argument(
            "--origin", choices=("observed", "simulated", "unknown"), default="observed"
        )
        command.add_argument("--output", type=Path, required=True)
        if name == "pilot-plan-a":
            command.add_argument("--reference-date", type=date.fromisoformat, required=True)
        if name == "pilot-plan-b":
            command.add_argument("--revision", type=Path, required=True)
        if name == "pilot-plan-followup":
            command.add_argument("--stage", choices=("id_batch", "v1_verification"), required=True)
            command.add_argument("--frame", type=Path, required=True)
            command.add_argument("--source-run", type=Path, required=True)
    pin = commands.add_parser(
        "pilot-acl-pin", help="Verify an authentic upstream pin without network"
    )
    options = pin.add_mutually_exclusive_group(required=True)
    options.add_argument("--checkout", type=Path)
    options.add_argument("--evidence", type=Path)
    pin.add_argument("--curator-id", required=True)
    pin.add_argument("--output", type=Path, required=True)
    for name in ("pilot-run", "pilot-continue"):
        run = commands.add_parser(name, help="Execute only a separately authorized pilot inventory")
        run.add_argument("plan", type=Path)
        run.add_argument("--authorize-live", action="store_true")
        run.add_argument("--authorization-reference", required=True)
        run.add_argument("--plan-sha256", required=True)
        run.add_argument("--output-dir", type=Path, required=True)
    for name in ("pilot-frame", "pilot-replay", "pilot-curation-template"):
        command = commands.add_parser(name, help="Offline enumeration/review preparation")
        command.add_argument("directory", type=Path)
        command.add_argument("--output", type=Path, required=True)
    for name in ("pilot-select", "pilot-freeze"):
        command = commands.add_parser(name, help="Offline curator-verified selection")
        command.add_argument("--source-run", type=Path, required=True)
        command.add_argument("--frame", type=Path, required=True)
        command.add_argument("--review", type=Path, required=True)
        command.add_argument("--invariance-review", type=Path)
        command.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("pilot-verify", help="Verify frozen pilot snapshot offline")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--integrity-sha256")


def run_pilot(args: argparse.Namespace) -> int:
    command = args.command
    if command == "pilot-verify":
        verify_pilot(args.directory, anchor=args.integrity_sha256)
        print("Frozen pilot hashes, source replay and curator selection verified")
        return 0
    if command in {"pilot-run", "pilot-continue"}:
        if not args.authorize_live:
            raise ValueError("No live execution without separate explicit authorization")
        content = args.plan.read_bytes()
        if hashlib.sha256(content).hexdigest() != args.plan_sha256:
            raise ValueError("Authorized plan file hash mismatch")
        reuse_from = None
        scoped_plan = None
        resource_plan = None
        if command == "pilot-continue":
            import json

            continuation_schema = json.loads(content).get("schema_version")
            if continuation_schema in {"3.0", "3.1"}:
                resource_plan = ResourceACLContinuation.model_validate_json(content)
                validate_resource_continuation(resource_plan)
                if (
                    resource_plan.schema_version == "3.1"
                    and args.authorization_reference
                    != resource_plan.proposed_authorization_reference
                ):
                    raise ValueError("Authorization reference differs from the sealed plan")
                plan = resource_plan.plan
            elif continuation_schema == "2.0":
                scoped_plan = ScopedACLContinuation.model_validate_json(content)
                validate_scoped_continuation(scoped_plan)
                plan = scoped_plan.plan
            else:
                continuation = ACLContinuation.model_validate_json(content)
                validate_continuation(continuation)
                plan = continuation.plan
                reuse_from = Path(continuation.source_run_directory)
        else:
            plan = PilotPlan.model_validate_json(content)
        validate_plan(plan)
        if (
            plan.origin != "observed"
            or not plan.planned_started_at <= datetime.now(UTC) <= plan.planned_finished_at
        ):
            raise ValueError("Not an observed authorized acquisition window")
        with httpx.Client(
            transport=httpx.HTTPTransport(retries=0),
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            result = execute(
                plan,
                args.output_dir,
                client,
                args.authorization_reference,
                reuse_from=reuse_from,
                scoped=scoped_plan,
                resource=resource_plan,
            )
        reused = (
            5
            if resource_plan is not None
            else 4
            if scoped_plan is not None
            else int(reuse_from is not None)
        )
        captured = sum(a.disposition == "captured" for a in result.attempts) - reused
        counts = (
            f"Captured {captured} new attempts; reused={reused}; "
            if reused
            else f"Captured {captured} attempts; "
        )
        print(counts + f"stop={result.stopped_reason}. No automatic retry.")
        return 1 if result.stopped_reason else 0
    output = args.output
    sources = [
        p
        for p in (
            getattr(args, name, None)
            for name in (
                "revision",
                "frame",
                "review",
                "directory",
                "source_run",
                "evidence",
                "checkout",
                "invariance_review",
            )
        )
        if p
    ]
    if output.exists() or any(
        output.resolve() == p.resolve() or p.resolve() in output.resolve().parents for p in sources
    ):
        raise ValueError("Pilot output must be new and outside its source inputs")
    if command == "pilot-plan-resource-continuation":
        recovery = make_resource_continuation(args.source_run)
        write(output, json_bytes(recovery.model_dump(mode="json")))
        print(f"Offline resource continuation: maximum {recovery.maximum_requests} new requests")
    elif command == "pilot-plan-scoped-continuation":
        amended = make_scoped_continuation(args.source_run)
        write(output, json_bytes(amended.model_dump(mode="json")))
        print(f"Offline amended continuation: maximum {amended.maximum_requests} new requests")
    elif command.startswith("pilot-plan-"):
        revision = (
            ACLRevision.model_validate_json(args.revision.read_bytes())
            if command == "pilot-plan-b"
            else None
        )
        frame = None
        if command == "pilot-plan-followup":
            frame = PilotFrame.model_validate_json(args.frame.read_bytes())
            if frame != build_frame(args.source_run):
                raise ValueError("Follow-up IDs do not come from the frozen replayed panel")
        stage = {
            "pilot-plan-a": "a_enumeration",
            "pilot-plan-b": "b_enumeration",
            "pilot-plan-acl-resolution": "acl_resolution",
        }.get(command, getattr(args, "stage", ""))
        experiment = (
            "submission-age-pilot" if command == "pilot-plan-a" else "mutation-robustness-pilot"
        )
        plan = make_plan(
            stage,
            experiment,
            args.planned_start,
            args.planned_end,
            reference=getattr(args, "reference_date", None),
            revision=revision,
            frame=frame,
            origin=args.origin,
        )
        validate_plan(plan)
        write(output, json_bytes(plan.model_dump(mode="json")))
        print(
            f"Offline inventory: at most {plan.maximum_requests} requests; SHA256="
            + hashlib.sha256(output.read_bytes()).hexdigest()
        )
    elif command == "pilot-acl-pin":
        pin = pin_revision(
            args.checkout or args.evidence, args.curator_id, local=bool(args.checkout)
        )
        write(output, json_bytes(pin.model_dump(mode="json")))
        print(f"Proven immutable ACL commit: {pin.commit}; origin={pin.origin}")
    elif command in {"pilot-frame", "pilot-curation-template", "pilot-replay"}:
        run = load_run(args.directory)
        if run.plan.stage in {"a_enumeration", "b_enumeration"}:
            frame = build_frame(args.directory)
            if command == "pilot-curation-template":
                review = PilotReview(
                    frame_id=frame.frame_id,
                    origin=frame.origin,
                    decisions=tuple(
                        PilotDecision(
                            source_id=key,
                            disposition="pending",
                            reason="Pending human verification; not eligible yet",
                            reviewer_id="UNASSIGNED",
                            reviewed_at=datetime.now(UTC),
                        )
                        for key in frame.panel_ids
                    ),
                )
                value = review.model_dump(mode="json")
            else:
                value = frame.model_dump(mode="json")
        else:
            if run.stopped_reason or len(run.attempts) != len(run.plan.requests):
                raise ValueError("Incomplete follow-up acquisition")
            for row, attempt in zip(run.plan.requests, run.attempts, strict=True):
                body, _ = response_body(
                    args.directory / str(attempt.evidence_directory), row, run.plan.origin
                )
                if run.plan.stage == "id_batch":
                    validate_selected(body, row)
            value = run.model_dump(mode="json")
        write(output, json_bytes(value))
        print("Offline source replay complete; no identity/date automatically verified")
    else:
        frame = PilotFrame.model_validate_json(args.frame.read_bytes())
        review = PilotReview.model_validate_json(args.review.read_bytes())
        invariance = (
            InvarianceAssessment.model_validate_json(args.invariance_review.read_bytes())
            if args.invariance_review
            else None
        )
        if command == "pilot-freeze":
            freeze_pilot(output, args.source_run, frame, review, invariance=invariance)
            print(
                "Frozen pilot; external integrity anchor="
                + hashlib.sha256((output / "integrity.json").read_bytes()).hexdigest()
            )
        else:
            selection = select_pilot(args.source_run, frame, review, invariance=invariance)
            write(output, json_bytes(selection))
            print(f"Verified selection shortfalls: {selection['shortfalls']}")
    return 0
