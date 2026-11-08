"""Deterministic offline judgments and lookup-weighted metrics with evidence bounds."""

from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

from citeprobe.evaluation_integrity import validate_inputs
from citeprobe.evaluation_models import (
    CandidateJudgment,
    EvaluatedLookup,
    EvaluationConfig,
    EvaluationInput,
    EvaluationOutput,
    IdentityMappings,
    Judgment,
    Metric,
    MetricGroup,
    RetrievalState,
)
from citeprobe.identity import IdentityIndex
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset, MutationBatch
from citeprobe.resolution_models import LookupBundle, LookupResult

METRIC_DEFINITIONS = {
    "recall_at_1": "H1/N; exact only when U1=0. Bounds H1/N to (H1+U1)/N.",
    "recall_at_5": "H5/N; exact only when U5=0. Bounds H5/N to (H5+U5)/N.",
    "incorrect_match_rate": "I1/N; exact only when U1=0. Bounds I1/N to (I1+U1)/N.",
    "unresolved_rate": "Number of valid NOT_FOUND lookups / N.",
    "identity_undetermined_rate": "FOUND lookups with undetermined original rank-one identity / N.",
    "provider_error_rate": "Number of TIMEOUT, RATE_LIMITED or API_ERROR lookups / T.",
    "timeout_rate": "Number of TIMEOUT lookups / T.",
    "rate_limited_rate": "Number of RATE_LIMITED lookups / T.",
    "api_error_rate": "Number of API_ERROR lookups / T.",
    "unknown_outcome_rate": "Number of UNKNOWN lookups / T; excluded from retrieval metrics.",
    "denominators": "T=validated verified-source lookups; N=FOUND or NOT_FOUND lookups only.",
    "recall_states": "HK=confirmed hit within original ranks <=K; UK=unresolved identity/parse gap "
    "without a confirmed hit; MK=confirmed miss. HK+UK+MK=N.",
    "uncertainty": "Evidence bounds are not confidence intervals. Zero denominator yields null. "
    "Different identifiers alone never prove INCORRECT; distinctness needs provenance.",
    "weighting": "Each lookup has equal weight. Mutations share original_citation_id; no "
    "independence, uncertainty-estimation or statistical-significance claim is made.",
    "data_labels": "Observed, simulated and unknown origins are never pooled. Only explicitly "
    "observed inputs may supply future empirical reporting; labels are user assertions.",
}


def metric(numerator: int, denominator: int, uncertain: int = 0) -> Metric:
    if not 0 <= numerator <= numerator + uncertain <= denominator:
        raise ValueError("Invalid metric counts")
    return Metric(
        numerator=numerator,
        uncertain_count=uncertain,
        denominator=denominator,
        value=numerator / denominator if denominator and not uncertain else None,
        lower_bound=numerator / denominator if denominator else None,
        upper_bound=(numerator + uncertain) / denominator if denominator else None,
        undefined_reason=(
            "zero_denominator" if not denominator else "identity_uncertainty" if uncertain else None
        ),
    )


def unavailable_ranks(result: LookupResult) -> tuple[int, ...]:
    evidence = result.attempts[-1].response
    if not isinstance(evidence, dict):
        return ()
    records = evidence.get("results")
    if result.provider == "crossref":
        message = evidence.get("message")
        records = message.get("items") if isinstance(message, dict) else None
    if not isinstance(records, list):
        return ()
    present = {candidate.provider_rank for candidate in result.candidates}
    return tuple(rank for rank in range(1, min(5, len(records)) + 1) if rank not in present)


def retrieval_state(
    judgments: tuple[CandidateJudgment, ...], missing: tuple[int, ...], k: int
) -> RetrievalState:
    within = [j for j in judgments if j.candidate.provider_rank <= k]
    if any(j.judgment == "CORRECT" for j in within):
        return "HIT"
    if any(j.judgment == "UNDETERMINED" for j in within) or any(rank <= k for rank in missing):
        return "UNDETERMINED"
    return "MISS"


def aggregate(dimensions: dict[str, str | None], rows: list[EvaluatedLookup]) -> MetricGroup:
    retrieval = [row for row in rows if row.retrieval_eligible]
    n, total = len(retrieval), len(rows)
    metrics: dict[str, Metric] = {}
    for k in (1, 5):
        states = [getattr(row, f"recall_at_{k}") for row in retrieval]
        metrics[f"recall_at_{k}"] = metric(states.count("HIT"), n, states.count("UNDETERMINED"))
    uncertain = sum(row.rank_one_judgment == "UNDETERMINED" for row in retrieval)
    metrics["incorrect_match_rate"] = metric(
        sum(row.rank_one_judgment == "INCORRECT" for row in retrieval),
        n,
        uncertain,
    )
    metrics["unresolved_rate"] = metric(sum(row.outcome == "NOT_FOUND" for row in retrieval), n)
    metrics["identity_undetermined_rate"] = metric(uncertain, n)
    metrics["provider_error_rate"] = metric(
        sum(row.outcome in {"TIMEOUT", "RATE_LIMITED", "API_ERROR"} for row in rows),
        total,
    )
    for name, outcome in (
        ("timeout_rate", "TIMEOUT"),
        ("rate_limited_rate", "RATE_LIMITED"),
        ("api_error_rate", "API_ERROR"),
        ("unknown_outcome_rate", "UNKNOWN"),
    ):
        metrics[name] = metric(sum(row.outcome == outcome for row in rows), total)
    return MetricGroup(
        dimensions=dimensions,
        empirical_data_eligible=dimensions["data_label"] == "observed",
        lookup_count=total,
        retrieval_lookup_count=n,
        original_citation_count=len({row.original_citation_id for row in rows}),
        retrieval_original_citation_count=len({row.original_citation_id for row in retrieval}),
        metrics=metrics,
    )


def code_fingerprint() -> str:
    root = Path(__file__).parent
    names = (
        "evaluation.py",
        "evaluation_models.py",
        "evaluation_integrity.py",
        "identity.py",
        "evaluation_io.py",
        "evaluation_cli.py",
        "models.py",
        "resolution_models.py",
        "lookup_inputs.py",
        "mutations.py",
        "providers.py",
        "dataset.py",
        "resolution_cli.py",
    )
    return fingerprint({name: (root / name).read_text(encoding="utf-8") for name in names})


def evaluate(
    dataset: Dataset,
    bundles: tuple[LookupBundle, ...],
    *,
    mutations: tuple[MutationBatch, ...] = (),
    mappings: IdentityMappings | None = None,
    config: EvaluationConfig | None = None,
    file_hashes: dict[str, str] | None = None,
) -> EvaluationOutput:
    config = config or EvaluationConfig()
    mappings = mappings or IdentityMappings(dataset_version=dataset.dataset_version)
    index = IdentityIndex(dataset, mappings)
    validated = validate_inputs(dataset, bundles, mutations, config)
    rows: list[EvaluatedLookup] = []
    inputs: list[EvaluationInput] = []
    group_rows: dict[str, list[EvaluatedLookup]] = defaultdict(list)
    dimensions_by_key: dict[str, dict[str, str | None]] = {}
    dimensions: dict[str, str | None]
    for item in validated:
        inputs.append(
            EvaluationInput(
                bundle_id=item.bundle_id,
                file_sha256=(file_hashes or {}).get(item.bundle_id),
                data_label=item.label,
                engine_version=item.bundle.engine_version,
                input_fingerprint=item.bundle.input_fingerprint,
                config_fingerprint=item.bundle.config_fingerprint,
            )
        )
        if not item.bundle.results:
            for provider in item.bundle.providers:
                dimensions = {"data_label": item.label, "provider": provider, "strategy": None}
                key = str(sorted(dimensions.items()))
                dimensions_by_key[key] = dimensions
                group_rows[key]  # Create an explicit undefined group for an empty run.
        for result in item.bundle.results:
            eligible = result.outcome in {"FOUND", "NOT_FOUND"}
            judgments = (
                tuple(
                    index.judge(result.original_citation_id, result.provider, candidate)
                    for candidate in result.candidates
                )
                if eligible
                else ()
            )
            missing = unavailable_ranks(result) if eligible else ()
            rank_one: Judgment | None = None
            for judgment in judgments:
                if judgment.candidate.provider_rank == 1:
                    rank_one = judgment.judgment
            if 1 in missing:
                rank_one = "UNDETERMINED"
            row = EvaluatedLookup(
                lookup_id=result.lookup_id,
                input_bundle_id=item.bundle_id,
                data_label=item.label,
                source_id=result.source_id,
                original_citation_id=result.original_citation_id,
                source_kind=result.source_kind,
                mutation_type=item.mutation_types.get(result.source_id),
                cohort=config.cohorts.get(result.original_citation_id),
                provider=result.provider,
                strategy=result.strategy,
                outcome=result.outcome,
                retrieval_eligible=eligible,
                candidates=judgments,
                recall_at_1=retrieval_state(judgments, missing, 1) if eligible else "EXCLUDED",
                recall_at_5=retrieval_state(judgments, missing, 5) if eligible else "EXCLUDED",
                rank_one_judgment=rank_one,
                parsing_warnings=result.parsing_warnings,
                unavailable_provider_ranks=missing,
            )
            rows.append(row)
            row_group_keys: set[str] = set()
            for grouping in ((), *config.groupings):
                dimensions = {
                    "data_label": item.label,
                    "provider": result.provider,
                    "strategy": result.strategy,
                }
                for dimension in grouping:
                    dimensions[dimension] = getattr(row, dimension)
                key = str(sorted(dimensions.items()))
                dimensions_by_key[key] = dimensions
                # Duplicate/redundant grouping specifications must never double weight a row.
                if key not in row_group_keys:
                    group_rows[key].append(row)
                    row_group_keys.add(key)
    payload = {
        "package_version": version("citeprobe"),
        "code_fingerprint": code_fingerprint(),
        "dataset_version": dataset.dataset_version,
        "dataset_fingerprint": fingerprint(dataset.model_dump(mode="json")),
        "identity_mappings": mappings.model_dump(mode="json"),
        "identity_mappings_fingerprint": fingerprint(mappings.model_dump(mode="json")),
        "config": config.model_dump(mode="json"),
        "metric_definitions": METRIC_DEFINITIONS,
        "inputs": [value.model_dump(mode="json") for value in inputs],
        "lookups": [
            row.model_dump(mode="json") for row in sorted(rows, key=lambda row: row.lookup_id)
        ],
        "groups": [
            aggregate(dimensions_by_key[key], group_rows[key]).model_dump(mode="json")
            for key in sorted(group_rows)
        ],
    }
    return EvaluationOutput.model_validate({**payload, "evaluation_id": fingerprint(payload)})
