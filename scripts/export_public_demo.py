"""Build the public pilot export from the frozen, verified evaluation."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.models import Dataset

ROOT = Path("artifacts/empirical-pilot-immediate-001")
EVAL = ROOT / "a-empirical-evaluation-001/evaluation.json"
DATASET = ROOT / "a-frozen-001/dataset.json"
TARGET = Path("public-demo/data.json")
FROZEN_SHA256 = {
    DATASET: "a8ffee33582fd352fe72db5c410300ac29a92c5e0cbca94b76b1a14a5e5b156d",
    EVAL: "375e40982278ba2a068284b07052279b408f2dbdd20fdcab54c99a4ddcddde1c",
}


def export() -> dict[str, Any]:
    for path, expected in FROZEN_SHA256.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen input checksum mismatch: {path}")
    dataset = Dataset.model_validate_json(DATASET.read_bytes())
    evaluation = EvaluationOutput.model_validate_json(EVAL.read_bytes())
    if (
        evaluation.evaluation_id
        != "c5a1b3f11d8e4a60f150bba38297f5170ee238fdb8a7323ba8e61d4f9cf6eea8"
    ):
        raise ValueError("Unexpected evaluation")
    papers = []
    for citation in dataset.citations:
        lookups = [r for r in evaluation.lookups if r.source_id == citation.citation_id]
        if len(lookups) != 2 or {r.provider for r in lookups} != {"openalex", "crossref"}:
            raise ValueError("Unexpected lookup inventory")
        results = {}
        for row in lookups:
            results[row.provider] = {
                "outcome": row.outcome,
                "recall_at_1": row.recall_at_1,
                "recall_at_5": row.recall_at_5,
                "rank_one_judgment": row.rank_one_judgment,
                "candidates": [
                    {
                        "rank": c.candidate.provider_rank,
                        "title": c.candidate.title,
                        "authors": list(c.candidate.authors),
                        "year": c.candidate.year,
                        "doi": c.candidate.doi,
                        "arxiv_id": c.candidate.arxiv_id,
                        "judgment": c.judgment,
                        "reason": c.reason,
                    }
                    for c in row.candidates
                ],
            }
        papers.append(
            {
                "id": citation.arxiv_id,
                "title": citation.title,
                "authors": [" ".join(filter(None, (a.given, a.family))) for a in citation.authors],
                "cohort": lookups[0].cohort,
                "results": results,
            }
        )
    data = {
        "schema_version": "1.0",
        "review_status": "owner_approved",
        "evaluation_id": evaluation.evaluation_id,
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "papers": papers,
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if re.search(r"(?i)(?:api[_-]?key|authorization|access[_-]?token|bearer)\s*[:=]", encoded):
        raise ValueError("Credential-shaped marker in export")
    return data


if __name__ == "__main__":
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(json.dumps(export(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
