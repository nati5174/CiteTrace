"""Offline validation and mutation generation commands."""

import argparse
import os
import sys
from pathlib import Path

from citeprobe.acquisition_cli import add_acquisition_commands, run_acquisition
from citeprobe.dataset import benchmark_citations, load_dataset
from citeprobe.evaluation_cli import add_evaluation_command, run_evaluation
from citeprobe.evidence_cli import add_evidence_command, run_evidence
from citeprobe.mutations import generate_mutations
from citeprobe.pilot_cli import add_pilot_commands, run_pilot
from citeprobe.report_cli import add_report_command, run_report
from citeprobe.research_cli import add_research_commands, run_research
from citeprobe.resolution_cli import add_commands, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citeprobe")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("dataset", type=Path)
    mutate = commands.add_parser("mutate")
    mutate.add_argument("dataset", type=Path)
    mutate.add_argument("--seed", type=int, default=0)
    mutate.add_argument("--output", type=Path, required=True)
    add_commands(commands)
    add_evaluation_command(commands)
    add_report_command(commands)
    add_research_commands(commands)
    add_acquisition_commands(commands)
    add_evidence_command(commands)
    add_pilot_commands(commands)
    args = parser.parse_args(argv)
    try:
        if args.command.startswith("pilot-"):
            return run_pilot(args)
        if args.command == "evidence-verify":
            return run_evidence(args)
        if args.command.startswith("acquisition-"):
            return run_acquisition(args)
        if args.command.startswith("dataset-"):
            return run_research(args)
        if args.command == "report":
            return run_report(args)
        if args.command == "evaluate":
            return run_evaluation(args)
        if args.command in ("resolve", "resolve-mutations", "replay"):
            return run(args)
        dataset = load_dataset(args.dataset)
        if args.command == "validate":
            print(
                f"Valid: {len(dataset.citations)} citations; "
                f"{len(benchmark_citations(dataset))} verified and eligible"
            )
        else:
            if args.output.resolve() == args.dataset.resolve() or (
                args.output.exists() and os.path.samefile(args.output, args.dataset)
            ):
                raise ValueError("Output must not overwrite the source dataset")
            batch = generate_mutations(dataset, seed=args.seed)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(batch.model_dump_json(indent=2) + "\n")
            print(f"Generated {len(batch.mutations)} mutations; {len(batch.skipped)} skipped")
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
