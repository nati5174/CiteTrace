"""Export allowlisted historical request metadata offline; never issue HTTP requests."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from citeprobe.evaluation_models import EvaluationOutput
from citeprobe.models import Dataset
from citeprobe.public_manifest import ArtifactReference, ExperimentManifest, HistoricalSearch
from citeprobe.resolution_models import LookupBundle
from scripts.export_public_demo import DATASET, EVAL, ROOT, export

TARGET = Path("public-demo/experiment-manifest.json")
INSPECTED_ADAPTER_REVISION = "11e6609423cb6f38ac738db43fd4493c8999f58d"
INSPECTED_ADAPTER_SHA256_LF = "988ecfc9e4221253acf3786adf89d830aba0fa5178495a082bd29e7ff2ca5651"
CAPTURE_ANCHORS = {
    "a-benchmark-smoke-002": "56427baa74dd454399db9d4b6644d40a62746330e7c56868d1879a6fe92adc35",
    "a-benchmark-key-continuation-001": (
        "64cf4b11b964245519a199137f3b9ba823ce51994f4368b66eaa73581f86e5e0"
    ),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_inventory(directory: Path) -> None:
    expected = CAPTURE_ANCHORS.get(directory.name)
    if expected and sha(directory / "integrity.json") != expected:
        raise ValueError("Frozen capture inventory anchor changed")
    inventory = json.loads((directory / "integrity.json").read_bytes())["files"]
    for name, digest in inventory.items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or sha(path) != digest:
            raise ValueError("Historical capture integrity mismatch")


def reference(path: Path, label: str) -> ArtifactReference:
    return ArtifactReference(artifact_id="urn:citeprobe:" + label, sha256=sha(path))


def build_search(
    directory: Path,
    label: str,
    provider: str,
    source_id: str,
    authentication: str,
    evaluated: Any,
    plan: Path,
) -> HistoricalSearch:
    number = 1 if provider == "openalex" else 2
    capture = directory / f"attempt-{number:03d}/record.json"
    record = json.loads(capture.read_bytes())
    bundle_path = directory / f"{provider}-lookups.json"
    bundle = LookupBundle.model_validate_json(bundle_path.read_bytes())
    if len(bundle.results) != 1:
        raise ValueError("Unexpected historical lookup count")
    row = bundle.results[0]
    if (
        row.source_id != source_id
        or row.provider != provider
        or row.lookup_id != evaluated.lookup_id
        or row.strategy != "metadata"
        or row.request.submitted_identifier is not None
        or row.candidates != tuple(c.candidate for c in evaluated.candidates)
        or row.outcome != evaluated.outcome
        or row.parsing_warnings
        or row.retry_count != 0
        or len(row.attempts) != 1
        or not record["complete"]
        or record["exception_type"] is not None
        or record["status"] != 200
        or record["provider"] != provider
    ):
        raise ValueError("Historical lookup does not match frozen evaluation")
    parts = urlsplit(record["url"])
    parameters = dict(parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True))
    if parameters != row.request.params or len(parse_qsl(parts.query)) != len(parameters):
        raise ValueError("Capture and lookup request parameters disagree")
    body = directory / f"attempt-{number:03d}/body.bin"
    if sha(body) != record["sha256"]:
        raise ValueError("Historical response checksum mismatch")
    payload = {
        "search_id": row.lookup_id,
        "source_paper_id": source_id.removeprefix("arxiv:"),
        "provider": provider,
        "method": record["method"],
        "endpoint": parts.scheme + "://" + parts.netloc + parts.path,
        "parameters": parameters,
        "authentication_mode": authentication,
        "request_started_at": record.get("started_at", "not_recorded"),
        "response_capture_finished_at": record.get("finished_at", "not_recorded"),
        "response_server_date_header": record.get("headers", {}).get("date", "not_recorded"),
        "http_status": record["status"],
        "outcome": row.outcome,
        "retrieval_limit": 5,
        "candidate_ranks": [c.provider_rank for c in row.candidates],
        "lookup_engine_version": bundle.engine_version,
        "parsing_warning_count": 0,
        "sources": [
            reference(capture, label + f":capture-{number:02d}"),
            reference(bundle_path, label + ":" + provider + ":lookup"),
            reference(plan, label.split(":paper-")[0] + ":plan"),
        ],
    }
    return HistoricalSearch.model_validate(payload)


def export_manifest() -> ExperimentManifest:
    public = export()  # Validates both frozen anchors before reading private provenance.
    if json.loads(Path("public-demo/data.json").read_bytes()) != public:
        raise ValueError("Public export differs from frozen evaluation")
    dataset = Dataset.model_validate_json(DATASET.read_bytes())
    evaluation = EvaluationOutput.model_validate_json(EVAL.read_bytes())
    smoke = ROOT / "a-benchmark-smoke-002"
    continuation = ROOT / "a-benchmark-key-continuation-001"
    verify_inventory(smoke)
    verify_inventory(continuation)
    plan = json.loads((continuation / "plan.json").read_bytes())
    if (
        plan["openalex_access"] != "api_key_query_parameter"
        or plan["crossref_access"] != "anonymous"
        or plan["pagination"] is not False
        or plan["retries"] != 0
    ):
        raise ValueError("Unexpected recorded access conditions")
    audit = json.loads((EVAL.parent / "integrity-audit.json").read_bytes())
    if audit["prior_429_attempts"] != 2 or not audit["excluded_from_retrieval_evaluation"]:
        raise ValueError("Operational attempt inventory changed")
    searches = []
    for index, citation in enumerate(dataset.citations):
        directory = smoke if index == 0 else continuation / f"paper-{index:02d}"
        label = "smoke-002" if index == 0 else f"key-continuation-001:paper-{index:02d}"
        source_plan = (smoke if index == 0 else continuation) / "plan.json"
        for provider in ("openalex", "crossref"):
            row = next(
                r
                for r in evaluation.lookups
                if r.source_id == citation.citation_id and r.provider == provider
            )
            searches.append(
                build_search(
                    directory,
                    label,
                    provider,
                    citation.citation_id,
                    "api_key_query_parameter" if index and provider == "openalex" else "anonymous",
                    row,
                    source_plan,
                )
            )
    adapter = Path("src/citeprobe/providers.py")
    if code_sha(adapter) != INSPECTED_ADAPTER_SHA256_LF:
        raise ValueError("Inspected adapter changed; review extraction descriptions before export")
    result = ExperimentManifest(
        study_kind="exploratory_citation_retrieval_pilot",
        dataset_version=dataset.dataset_version,
        evaluation_id=evaluation.evaluation_id,
        dataset_sha256=sha(DATASET),
        evaluation_sha256=sha(EVAL),
        public_data_sha256_lf=hashlib.sha256(
            Path("public-demo/data.json").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        evaluation_code_fingerprint=evaluation.code_fingerprint,
        inspected_adapter_revision=INSPECTED_ADAPTER_REVISION,
        inspected_adapter_sha256=code_sha(adapter),
        manifest_builder_sha256=code_sha(Path(__file__)),
        source_paper_ids=tuple(p["id"] for p in public["papers"]),
        searches=tuple(searches),
        excluded_operational_attempts=2,
        excluded_operational_status=429,
        pagination=False,
        retries_per_evaluated_search=0,
        extraction_rules=(
            "Inspect the first five provider response entries; retain original one-based ranks.",
            "No local re-ranking. Unparseable entries are skipped with a warning; "
            "these 16 lookups have no parsing warnings.",
            "OpenAlex: results array, title, authorship display names, "
            "publication_year and identifiers.",
            "Crossref: message.items, first title, author name or given/family; year from "
            "published, published-print, published-online, then issued.",
        ),
        normalization_rules=(
            "Recorded query parameter values are copied verbatim after URL decoding, "
            "not reconstructed.",
            "Version-1 query construction joins title, author names and year with spaces; "
            "canonical identifiers are withheld.",
            "Inspected adapter strips DOI URL prefixes; arXiv IDs are extracted from "
            "recognized arXiv/DOI URLs; candidate text fields trim surrounding whitespace.",
            "Timestamps are ISO 8601; capture finish is after body capture, "
            "not a precise header-arrival timestamp.",
            "Server Date headers use a remote clock. Local/server clock differences "
            "are retained and must not be interpreted as precise event ordering.",
            "Code and public-data checksums use LF-normalized bytes "
            "to accommodate Git line-ending conversion.",
        ),
        provenance_limits=(
            "The historical Git checkout is not recorded; inspected_adapter_revision "
            "identifies code reviewed for this manifest, not the historical execution checkout.",
            "Extraction/normalization descriptions come from the inspected version-1 "
            "adapter and saved lookup records; provider ranking internals are not recorded.",
            "Capture metadata precedes transport credential injection. Keyed access is "
            "supported by the recorded continuation plan and transport implementation; "
            "credentials and headers are excluded.",
            "Raw historical responses are private. Public artifacts support deterministic "
            "calculations, not independent replay of private captures.",
            "New API calls are replication attempts under potentially changed conditions, "
            "not replay of this frozen experiment.",
        ),
    )
    encoded = result.model_dump_json()
    if re.search(r"(?i)(?:api[_-]?key|authorization|access[_-]?token|bearer)\s*[:=]", encoded):
        raise ValueError("Credential-shaped data in public manifest")
    return result


if __name__ == "__main__":
    TARGET.write_text(export_manifest().model_dump_json(indent=2) + "\n", encoding="utf-8")
