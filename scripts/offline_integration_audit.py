"""Exercise every CLI stage using only deterministic synthetic/mocked observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from citeprobe.cli import main as citeprobe
from citeprobe.dataset import load_dataset
from citeprobe.evaluation_models import EvaluationConfig, EvaluationOutput
from citeprobe.lookup_inputs import fingerprint
from citeprobe.resolution_models import LookupBundle, ResolverConfig


def audit(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/part3-final-verification"
    original_inputs = (
        fixture / "dataset.json",
        fixture / "lookups.json",
        Path("data/pilot_dataset.json"),
    )
    repository = Path(__file__).resolve().parents[1]
    before = {
        path.resolve().relative_to(repository).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in original_inputs
    }
    dataset_path = output / "dataset.json"
    dataset_path.write_bytes((fixture / "dataset.json").read_bytes())
    dataset = load_dataset(dataset_path)
    commands: list[dict[str, Any]] = []

    def run(arguments: list[str]) -> None:
        code = citeprobe(arguments)
        commands.append({"command": arguments[0], "exit_code": code})
        if code != 0:
            raise AssertionError(f"Offline command failed: {arguments[0]}")

    run(["validate", str(dataset_path)])
    run(["validate", "data/pilot_dataset.json"])
    mutations = output / "mutations.json"
    repeated_mutations = output / "mutations-repeat.json"
    run(["mutate", str(dataset_path), "--seed", "42", "--output", str(mutations)])
    run(["mutate", str(dataset_path), "--seed", "42", "--output", str(repeated_mutations)])
    left = json.loads(mutations.read_text(encoding="utf-8"))
    right = json.loads(repeated_mutations.read_text(encoding="utf-8"))
    left.pop("generated_at")
    right.pop("generated_at")
    assert left == right
    config = output / "resolver-config.json"
    config.write_text(
        ResolverConfig(max_attempts=1, openalex_rps=100, crossref_rps=100).model_dump_json(),
        encoding="utf-8",
    )
    original_client = httpx.AsyncClient
    submitted: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        query = params.get("search") or params["query.bibliographic"]
        assert "10.1234/" not in query and "fixture-" not in query
        assert "cookie" not in request.headers
        match = re.search(r"\b([0-5])\b", query)
        paper = int(match[1]) if match else 0
        is_openalex = request.url.host == "api.openalex.org"
        submitted.append(
            {
                "provider": "openalex" if is_openalex else "crossref",
                "parameter_names": sorted(params),
                "identifier_hints_absent": True,
            }
        )
        if paper == 5:
            raise httpx.ConnectError("SIMULATED offline connection failure", request=request)
        doi = f"10.1234/fixture-{paper}" if paper != 2 else "10.1234/unmapped"
        records = (
            []
            if paper == 1
            else (
                [
                    {
                        "id": f"https://openalex.org/W{100 + paper}",
                        "title": "SIMULATED candidate",
                        "doi": doi,
                        "relevance_score": 4.0,
                    }
                ]
                if is_openalex
                else [{"DOI": doi, "title": ["SIMULATED candidate"], "score": 4.0}]
            )
        )
        payload = (
            {"results": records} if is_openalex else {"status": "ok", "message": {"items": records}}
        )
        return httpx.Response(200, json=payload)

    def mock_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    canonical = output / "canonical-lookups.json"
    mutated = output / "mutated-lookups.json"
    with patch("httpx.AsyncClient", mock_client):
        run(["resolve", str(dataset_path), "--config", str(config), "--output", str(canonical)])
        run(
            [
                "resolve-mutations",
                str(mutations),
                "--dataset",
                str(dataset_path),
                "--config",
                str(config),
                "--output",
                str(mutated),
            ]
        )
    replayed = output / "replayed.json"
    with patch("httpx.AsyncClient", side_effect=AssertionError("Offline stage constructed client")):
        run(["replay", str(mutated), "--output", str(replayed)])
        assert replayed.read_bytes() == mutated.read_bytes()
        evaluation = output / "evaluation.json"
        run(
            [
                "evaluate",
                str(canonical),
                str(mutated),
                "--dataset",
                str(dataset_path),
                "--mutations",
                str(mutations),
                "--data-label",
                "simulated",
                "--output",
                str(evaluation),
            ]
        )
        evaluated = EvaluationOutput.model_validate_json(evaluation.read_bytes())
        assert all(row.data_label == "simulated" for row in evaluated.lookups)
        assert not any(group.empirical_data_eligible for group in evaluated.groups)
        report = output / "report"
        run(
            [
                "report",
                str(evaluation),
                "--experiment",
                "mutation-robustness",
                "--output-dir",
                str(report),
            ]
        )
        assert (report / "simulated/report.md").exists()
        assert not (report / "observed").exists()

        # Verify mixed origins remain in separate reports, without reclassifying any observations.
        mixed_config = output / "mixed-evaluation-config.json"
        canonical_bundle = LookupBundle.model_validate_json(canonical.read_bytes())
        mixed_config.write_text(
            EvaluationConfig(
                default_data_label="simulated",
                input_labels={
                    fingerprint(canonical_bundle.model_dump(mode="json")): "unknown",
                },
            ).model_dump_json(),
            encoding="utf-8",
        )
        mixed = output / "mixed-evaluation.json"
        run(
            [
                "evaluate",
                str(canonical),
                str(mutated),
                "--dataset",
                str(dataset_path),
                "--mutations",
                str(mutations),
                "--config",
                str(mixed_config),
                "--output",
                str(mixed),
            ]
        )
        mixed_report = output / "mixed-report"
        run(
            [
                "report",
                str(mixed),
                "--experiment",
                "mutation-robustness",
                "--output-dir",
                str(mixed_report),
            ]
        )
        assert (mixed_report / "simulated/report.md").exists()
        assert (mixed_report / "unknown/report.md").exists()
        assert not (mixed_report / "observed").exists()

        # Experiment A uses explicitly constructed dates and original mock collection timestamps.
        bundles = [
            LookupBundle.model_validate_json(path.read_bytes()) for path in (canonical, mutated)
        ]
        end = max(row.finished_at for bundle in bundles for row in bundle.results)
        reference = end.astimezone(UTC).date()
        study = output / "study.json"
        study.write_text(
            json.dumps(
                {
                    "dataset_fingerprint": fingerprint(dataset.model_dump(mode="json")),
                    "citation_ids": [c.citation_id for c in dataset.citations],
                    "sampling_method": "SIMULATED software integration audit; "
                    "not an empirical sample",
                    "verification_method": "SIMULATED dates and verification events",
                    "collection_started_at": (end - timedelta(hours=1)).isoformat(),
                    "collection_finished_at": end.isoformat(),
                    "reference_date": reference.isoformat(),
                    "lookup_bundle_ids": [
                        fingerprint(bundle.model_dump(mode="json")) for bundle in bundles
                    ],
                    "preprint_dates": [
                        {
                            "citation_id": c.citation_id,
                            "publication_date": (reference - timedelta(days=age)).isoformat(),
                            "provenance": c.provenance.model_dump(mode="json"),
                        }
                        for c, age in zip(dataset.citations, (3, 10, 25, 45, 0, 61), strict=True)
                    ],
                }
            ),
            encoding="utf-8",
        )
        run(
            [
                "report",
                str(evaluation),
                "--experiment",
                "recent-preprints",
                "--study-manifest",
                str(study),
                "--dataset",
                str(dataset_path),
                "--lookup-bundles",
                str(canonical),
                str(mutated),
                "--output-dir",
                str(output / "recent-report"),
            ]
        )
    after = {
        path.resolve().relative_to(repository).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in original_inputs
    }
    assert before == after
    assert dataset_path.read_bytes() == (fixture / "dataset.json").read_bytes()
    assert canonical.read_bytes() != b"" and mutated.read_bytes() == replayed.read_bytes()
    return {
        "data_label": "simulated",
        "commands": commands,
        "mutation_values_deterministic": True,
        "replay_byte_identical": True,
        "input_hashes_before": before,
        "input_hashes_after": after,
        "inputs_unchanged": True,
        "mocked_http_attempts": len(submitted),
        "live_http_requests": 0,
        "identifier_hints_absent": all(row["identifier_hints_absent"] for row in submitted),
        "evaluated_lookup_count": len(evaluated.lookups),
        "origin_isolation_passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output_dir)
    (args.output_dir / "audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
