"""Offline validation and mutation generation commands."""

import argparse
import os
import sys
from pathlib import Path

from citeprobe.dataset import benchmark_citations, load_dataset
from citeprobe.mutations import generate_mutations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citeprobe")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("dataset", type=Path)
    mutate = commands.add_parser("mutate")
    mutate.add_argument("dataset", type=Path)
    mutate.add_argument("--seed", type=int, default=0)
    mutate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
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
