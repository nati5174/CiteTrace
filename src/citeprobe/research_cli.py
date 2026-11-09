"""Offline dataset-ledger CLI; never constructs an HTTP client."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from citeprobe.dataset import load_dataset
from citeprobe.models import MutationBatch
from citeprobe.research import sample_dataset, validate_research
from citeprobe.research_io import freeze, verify, write_json
from citeprobe.research_models import ResearchManifest
from citeprobe.resolution_cli import check_output
from citeprobe.resolution_models import LookupBundle


def add_research_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("dataset-validate", "dataset-sample", "dataset-freeze"):
        command = commands.add_parser(name, help="Offline research dataset infrastructure")
        command.add_argument("dataset", type=Path)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "dataset-validate":
            command.add_argument("--mutations", type=Path)
            command.add_argument("--lookup-bundles", nargs="*", type=Path, default=[])
        else:
            command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("dataset-verify", help="Verify a frozen research snapshot")
    command.add_argument("snapshot", type=Path)
    command.add_argument("--integrity-sha256")


def run_research(args: argparse.Namespace) -> int:
    if args.command == "dataset-verify":
        plan = verify(args.snapshot, expected_integrity_sha256=args.integrity_sha256)
        print(f"Snapshot verified: {plan.plan_fingerprint}; origin={plan.origin}")
        return 0
    dataset = load_dataset(args.dataset)
    manifest = ResearchManifest.model_validate_json(args.manifest.read_bytes())
    if args.command == "dataset-validate":
        mutations = (
            MutationBatch.model_validate_json(args.mutations.read_bytes())
            if args.mutations
            else None
        )
        bundles = tuple(
            LookupBundle.model_validate_json(p.read_bytes()) for p in args.lookup_bundles
        )
        warnings = validate_research(dataset, manifest, mutations=mutations, bundles=bundles)
        print(f"Valid research ledger; origin={manifest.origin}; {len(warnings)} warnings")
        for warning in warnings:
            print(warning)
    elif args.command == "dataset-sample":
        check_output(args.output, [args.dataset, args.manifest])
        plan = sample_dataset(dataset, manifest)
        write_json(args.output, plan.model_dump_json(indent=2))
        print(f"Sampled offline; origin={plan.origin}; shortfalls={plan.shortfalls}")
    else:
        check_output(args.output, [args.dataset, args.manifest])
        freeze(dataset, manifest, args.output)
        print("Frozen source frame and selection; no retrieval collection authorized")
        print(
            "Retain this external integrity anchor: "
            + hashlib.sha256((args.output / "integrity.json").read_bytes()).hexdigest()
        )
    return 0
