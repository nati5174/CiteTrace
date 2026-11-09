"""Strictly offline raw evidence verification and deterministic extraction replay."""

from __future__ import annotations

import argparse
from pathlib import Path

from citeprobe.evidence_io import json_bytes, verify_batch, write


def add_evidence_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    command = commands.add_parser("evidence-verify", help="Verify version 2 raw evidence offline")
    command.add_argument("directory", type=Path)
    command.add_argument("--manifest-sha256")
    command.add_argument("--replay-output", type=Path)


def run_evidence(args: argparse.Namespace) -> int:
    if args.replay_output and (
        args.replay_output.exists()
        or args.directory.resolve() in args.replay_output.resolve().parents
    ):
        raise ValueError("Replay output must be new and outside the evidence bundle")
    results = verify_batch(args.directory, anchor=args.manifest_sha256)
    if args.replay_output:
        write(args.replay_output, json_bytes([r.model_dump(mode="json") for r in results]))
    print(f"Verified {len(results)} raw request records and extraction replay offline")
    return 0
