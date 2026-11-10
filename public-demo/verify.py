"""Check downloaded CiteProbe artifacts offline with Python 3.12+ (standard library only).

Usage: python verify.py data.json experiment-manifest.json
This checks public-artifact consistency, not capture authenticity or candidate identity.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def verify(data_path: Path, manifest_path: Path) -> dict[str, Any]:
    raw = data_path.read_bytes()
    data = json.loads(raw)
    manifest = json.loads(manifest_path.read_bytes())
    if data.get("schema_version") != "1.0" or manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported artifact schema")
    digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    if digest != manifest["public_data_sha256_lf"]:
        raise ValueError("Data checksum does not match the experiment manifest")
    for name in ("evaluation_id", "dataset_sha256"):
        if data[name] != manifest[name]:
            raise ValueError("Frozen research identifiers disagree")
    papers = data["papers"]
    searches = manifest["searches"]
    if len(papers) != 8 or len(searches) != 16 or len({p["id"] for p in papers}) != 8:
        raise ValueError("Expected eight unique source papers and sixteen searches")
    if set(manifest["source_paper_ids"]) != {p["id"] for p in papers}:
        raise ValueError("Source-paper inventory differs")
    pairs = {(r["source_paper_id"], r["provider"]): r for r in searches}
    if len(pairs) != 16 or len({r["search_id"] for r in searches}) != 16:
        raise ValueError("Duplicate recorded search")
    summaries = {}
    judgments: Counter[str] = Counter()
    for provider in ("openalex", "crossref"):
        results = []
        for paper in papers:
            result = paper["results"][provider]
            recorded = pairs[paper["id"], provider]
            ranks = [c["rank"] for c in result["candidates"]]
            if ranks != recorded["candidate_ranks"] or result["outcome"] != recorded["outcome"]:
                raise ValueError("Candidate order or retrieval outcome differs from manifest")
            if recorded["http_status"] != 200 or recorded["retrieval_limit"] != 5:
                raise ValueError("Unexpected recorded HTTP status or limit")
            if result["outcome"] not in {"FOUND", "NOT_FOUND"}:
                raise ValueError("An operational failure is not a valid empty search")
            if (result["outcome"] == "FOUND") != bool(ranks) or len(ranks) > 5:
                raise ValueError("Candidate inventory contradicts outcome")
            if ranks != sorted(set(ranks)) or any(r < 1 or r > 5 for r in ranks):
                raise ValueError("Invalid provider rank")
            if result["recall_at_5"] not in {"HIT", "MISS", "UNDETERMINED"}:
                raise ValueError("Invalid published recall state")
            judgments.update(c["judgment"] for c in result["candidates"])
            results.append(result)
        hits = sum(r["recall_at_5"] == "HIT" for r in results)
        unresolved = sum(r["recall_at_5"] == "UNDETERMINED" for r in results)
        summaries[provider] = {
            "searches": len(results),
            "searches_returning_candidates": sum(r["outcome"] == "FOUND" for r in results),
            "candidate_entries": sum(len(r["candidates"]) for r in results),
            "recall_at_5_evidence_bound_counts": [hits, hits + unresolved],
            "denominator": len(results),
        }
    modes = Counter((r["provider"], r["authentication_mode"]) for r in searches)
    if modes != {
        ("openalex", "anonymous"): 1,
        ("openalex", "api_key_query_parameter"): 7,
        ("crossref", "anonymous"): 8,
    }:
        raise ValueError("Recorded access conditions differ from the frozen pilot")
    if judgments != {"UNDETERMINED": 41}:
        raise ValueError("Frozen candidate judgments or count changed")
    return {
        "scope": "Public consistency and calculations; not independent identity verification",
        "source_papers": 8,
        "recorded_searches": 16,
        "candidate_entries": 41,
        "identity_judgments": dict(judgments),
        "providers": summaries,
        "public_data_sha256_lf": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.data, args.manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Artifact verification failed: {type(error).__name__}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
