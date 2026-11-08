"""CLI orchestration for live resolution and offline replay."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from citeprobe.dataset import load_dataset
from citeprobe.lookup_inputs import canonical_tasks, fingerprint, mutation_tasks
from citeprobe.models import MutationBatch
from citeprobe.resolution_models import ResolverConfig
from citeprobe.resolver import Resolver, replay, save_results


def add_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("resolve", "resolve-mutations"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        if name == "resolve-mutations":
            command.add_argument("--dataset", type=Path, required=True)
        else:
            command.add_argument(
                "--strategy", choices=("metadata", "identifier"), default="metadata"
            )
        command.add_argument(
            "--providers",
            nargs="+",
            choices=("openalex", "crossref"),
            default=["openalex", "crossref"],
        )
        command.add_argument("--config", type=Path)
        command.add_argument("--limit", type=int)
        command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("replay")
    command.add_argument("input", type=Path)
    command.add_argument("--output", type=Path)


def check_output(output: Path, sources: list[Path]) -> None:
    for source in sources:
        if output.resolve() == source.resolve() or (
            output.exists() and source.exists() and os.path.samefile(output, source)
        ):
            raise ValueError("Output must not overwrite an input or canonical dataset")
    if output.exists():
        raise ValueError("Output already exists")
    if not output.parent.is_dir():
        raise ValueError("Output directory does not exist")


def run(args: argparse.Namespace) -> int:
    if args.command == "replay":
        if args.output:
            check_output(args.output, [args.input])
        bundle = replay(args.input)
        if args.output:
            save_results(bundle, args.output)
    else:
        sources = [args.input]
        if args.command == "resolve-mutations":
            sources.append(args.dataset)
        if args.config:
            sources.append(args.config)
        check_output(args.output, sources)
        config = (
            ResolverConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            if args.config
            else ResolverConfig()
        )
        dataset = load_dataset(args.dataset if args.command == "resolve-mutations" else args.input)
        if args.command == "resolve-mutations":
            mutations = MutationBatch.model_validate_json(args.input.read_text(encoding="utf-8"))
            tasks = mutation_tasks(dataset, mutations)
            input_hash = fingerprint(mutations.model_dump(mode="json", exclude={"generated_at"}))
        else:
            tasks = canonical_tasks(dataset, args.strategy)
            input_hash = fingerprint(dataset.model_dump(mode="json"))
        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("Limit must be positive")
            tasks = tasks[: args.limit]
        bundle = asyncio.run(
            Resolver(config).resolve(
                tasks,
                args.providers,
                dataset_version=dataset.dataset_version,
                dataset_fingerprint=fingerprint(dataset.model_dump(mode="json")),
                input_fingerprint=input_hash,
            )
        )
        save_results(bundle, args.output)
    print(f"{len(bundle.results)} recorded lookups")
    return 0
