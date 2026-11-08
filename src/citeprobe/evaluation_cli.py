"""Offline evaluate command; no resolver/client is constructed."""

from __future__ import annotations

import argparse
import hashlib

from citeprobe.dataset import load_dataset
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_io import check_outputs, write_evaluation
from citeprobe.evaluation_models import EvaluationConfig, IdentityMappings
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import MutationBatch
from citeprobe.resolution_models import LookupBundle


def add_evaluation_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from pathlib import Path

    command = commands.add_parser("evaluate", help="Evaluate saved lookups offline")
    command.add_argument("inputs", nargs="+", type=Path)
    command.add_argument("--dataset", required=True, type=Path)
    command.add_argument("--mutations", nargs="+", type=Path, default=[])
    command.add_argument("--identity-mappings", type=Path)
    command.add_argument("--config", type=Path)
    command.add_argument("--data-label", choices=("observed", "simulated", "unknown"))
    command.add_argument("--output", required=True, type=Path)
    command.add_argument("--csv-output", type=Path)


def run_evaluation(args: argparse.Namespace) -> int:
    csv_path = args.csv_output or args.output.with_suffix(".csv")
    sources = [*args.inputs, args.dataset, *args.mutations]
    sources.extend(path for path in (args.config, args.identity_mappings) if path)
    check_outputs(args.output, csv_path, sources)
    dataset = load_dataset(args.dataset)
    config = (
        EvaluationConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.config
        else EvaluationConfig()
    )
    if args.data_label:
        config = EvaluationConfig.model_validate(
            {
                **config.model_dump(),
                "default_data_label": args.data_label,
            }
        )
    mappings = (
        IdentityMappings.model_validate_json(args.identity_mappings.read_text(encoding="utf-8"))
        if args.identity_mappings
        else None
    )
    mutations = tuple(
        MutationBatch.model_validate_json(path.read_text(encoding="utf-8"))
        for path in args.mutations
    )
    bundles: list[LookupBundle] = []
    file_hashes: dict[str, str] = {}
    for path in args.inputs:
        content = path.read_bytes()
        bundle = LookupBundle.model_validate_json(content)
        bundles.append(bundle)
        file_hashes[fingerprint(bundle.model_dump(mode="json"))] = hashlib.sha256(
            content
        ).hexdigest()
    output = evaluate(
        dataset,
        tuple(bundles),
        mutations=mutations,
        mappings=mappings,
        config=config,
        file_hashes=file_hashes,
    )
    write_evaluation(output, args.output, csv_path, sources)
    print(
        f"Evaluated {len(output.lookups)} recorded lookups offline; wrote JSON and CSV. "
        "Origin labels are retained; no empirical reporting is performed."
    )
    return 0
