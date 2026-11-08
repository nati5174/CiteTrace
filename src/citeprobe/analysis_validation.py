"""Validate Part 3 evidence without re-running identity matching or any HTTP requests."""

from dataclasses import dataclass
from datetime import UTC

from citeprobe.analysis_models import AnalysisConfig, LookupTiming, StudyManifest
from citeprobe.evaluation import METRIC_DEFINITIONS, aggregate, retrieval_state
from citeprobe.evaluation_models import EvaluatedLookup, EvaluationInput, EvaluationOutput
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.resolution_models import LookupBundle


@dataclass(frozen=True)
class AnalysisEvidence:
    evaluations: tuple[EvaluationOutput, ...]
    warnings: tuple[str, ...]
    provenance_complete: bool
    timings: dict[str, LookupTiming]


def validate_evaluations(
    evaluations: tuple[EvaluationOutput, ...],
    config: AnalysisConfig,
    *,
    dataset: Dataset | None = None,
    bundles: tuple[LookupBundle, ...] = (),
    manifest: StudyManifest | None = None,
) -> AnalysisEvidence:
    if not evaluations:
        raise ValueError("At least one evaluation artifact is required")
    if config.experiment == "recent-preprints" and (
        manifest is None or manifest.reference_date is None
    ):
        raise ValueError("Experiment A requires a study manifest with a UTC reference date")
    first = evaluations[0]
    dataset_hash = first.dataset_fingerprint
    warnings: list[str] = []
    seen_evaluations: set[str] = set()
    seen_lookups: set[str] = set()
    observations: set[tuple[str, str, str, str]] = set()
    input_refs: dict[str, EvaluationInput] = {}
    rows_by_id: dict[str, EvaluatedLookup] = {}
    cohort_assignments: dict[tuple[str, str], str | None] = {}
    for evaluation in evaluations:
        if evaluation.evaluation_id in seen_evaluations:
            raise ValueError("Duplicate evaluation artifact")
        seen_evaluations.add(evaluation.evaluation_id)
        payload = evaluation.model_dump(
            mode="json", exclude={"schema_version", "evaluator_version", "evaluation_id"}
        )
        if fingerprint(payload) != evaluation.evaluation_id:
            raise ValueError("Evaluation ID/fingerprint mismatch")
        if (
            evaluation.dataset_fingerprint != dataset_hash
            or evaluation.dataset_version != first.dataset_version
            or evaluation.code_fingerprint != first.code_fingerprint
            or evaluation.identity_mappings_fingerprint != first.identity_mappings_fingerprint
        ):
            raise ValueError("Incompatible evaluation datasets, code or identity evidence")
        if evaluation.metric_definitions != METRIC_DEFINITIONS:
            raise ValueError("Unsupported or changed metric definitions")
        if (
            fingerprint(evaluation.identity_mappings.model_dump(mode="json"))
            != evaluation.identity_mappings_fingerprint
            or evaluation.identity_mappings.dataset_version != evaluation.dataset_version
        ):
            raise ValueError("Identity mapping fingerprint/version mismatch")
        local_inputs = {item.bundle_id: item for item in evaluation.inputs}
        if len(local_inputs) != len(evaluation.inputs):
            raise ValueError("Duplicate evaluation input references")
        if set(evaluation.config.input_labels) - local_inputs.keys():
            raise ValueError("Evaluation labels reference unknown input bundles")
        for item in evaluation.inputs:
            if item.data_label != evaluation.config.input_labels.get(
                item.bundle_id, evaluation.config.default_data_label
            ):
                raise ValueError("Evaluation input origin conflicts with its configuration")
            if item.bundle_id in input_refs and input_refs[item.bundle_id] != item:
                raise ValueError("Inconsistent input bundle provenance")
            input_refs[item.bundle_id] = item
        for row in evaluation.lookups:
            if row.cohort != evaluation.config.cohorts.get(row.original_citation_id):
                raise ValueError("Lookup cohort differs from evaluation configuration")
            cohort_key = (row.data_label, row.original_citation_id)
            if cohort_key in cohort_assignments and cohort_assignments[cohort_key] != row.cohort:
                raise ValueError("Inconsistent source cohort assignments")
            cohort_assignments[cohort_key] = row.cohort
            if row.lookup_id in seen_lookups:
                raise ValueError("Duplicate lookup across evaluation artifacts")
            seen_lookups.add(row.lookup_id)
            observation = (row.source_kind, row.source_id, row.provider, row.strategy)
            if observation in observations:
                raise ValueError("Repeated lookup observation")
            observations.add(observation)
            ref = local_inputs.get(row.input_bundle_id)
            if ref is None or ref.data_label != row.data_label:
                raise ValueError("Missing source reference or conflicting data origin")
            eligible = row.outcome in {"FOUND", "NOT_FOUND"}
            if row.retrieval_eligible != eligible:
                raise ValueError("Invalid retrieval denominator eligibility")
            ranks = [j.candidate.provider_rank for j in row.candidates]
            if ranks != sorted(set(ranks)) or any(rank > 5 for rank in ranks):
                raise ValueError("Invalid provider ranking")
            if row.source_kind == "canonical" and (
                row.original_citation_id != row.source_id or row.mutation_type
            ):
                raise ValueError("Invalid canonical source reference")
            if row.source_kind == "mutation" and (
                row.mutation_type is None or row.strategy != "metadata"
            ):
                raise ValueError("Invalid mutation source/strategy")
            if eligible:
                if row.outcome == "FOUND" and not row.candidates:
                    raise ValueError("FOUND without candidates")
                if row.outcome == "NOT_FOUND" and (
                    row.candidates or row.unavailable_provider_ranks
                ):
                    raise ValueError("Invalid NOT_FOUND evidence")
                for k in (1, 5):
                    if getattr(row, f"recall_at_{k}") != retrieval_state(
                        row.candidates, row.unavailable_provider_ranks, k
                    ):
                        raise ValueError("Retrieval state inconsistent with saved judgments")
                top = next(
                    (j.judgment for j in row.candidates if j.candidate.provider_rank == 1), None
                )
                if 1 in row.unavailable_provider_ranks:
                    top = "UNDETERMINED"
                if row.rank_one_judgment != top:
                    raise ValueError("Rank-one judgment inconsistent with saved evidence")
            elif (
                row.candidates
                or row.rank_one_judgment
                or row.recall_at_1 != "EXCLUDED"
                or row.recall_at_5 != "EXCLUDED"
            ):
                raise ValueError("Operational failure included in retrieval metrics")
            rows_by_id[row.lookup_id] = row
        group_keys: set[str] = set()
        for group in evaluation.groups:
            if not {"provider", "strategy", "data_label"} <= group.dimensions.keys():
                raise ValueError("Analysis groups must separate provider, strategy and origin")
            if set(group.dimensions) - {
                "provider",
                "strategy",
                "data_label",
                "source_kind",
                "mutation_type",
                "cohort",
                "original_citation_id",
            }:
                raise ValueError("Unknown evaluation grouping dimension")
            key = fingerprint(group.dimensions)
            if key in group_keys:
                raise ValueError("Duplicate evaluation aggregate group")
            group_keys.add(key)
            subset = [
                row
                for row in evaluation.lookups
                if all(getattr(row, k) == v for k, v in group.dimensions.items())
            ]
            if aggregate(group.dimensions, subset) != group:
                raise ValueError(
                    "Evaluation aggregate counts/bounds disagree with saved lookup judgments"
                )
        for row in evaluation.lookups:
            if (
                fingerprint(
                    {
                        "provider": row.provider,
                        "strategy": row.strategy,
                        "data_label": row.data_label,
                    }
                )
                not in group_keys
            ):
                raise ValueError("Missing base evaluation aggregate")
    if dataset:
        if fingerprint(dataset.model_dump(mode="json")) != dataset_hash:
            raise ValueError("Supplied dataset fingerprint mismatch")
        originals = {c.citation_id: c for c in dataset.citations}
        for row in rows_by_id.values():
            original = originals.get(row.original_citation_id)
            if original is None or original.provenance.verification_status != "verified":
                raise ValueError("Report references unknown or unverified ground truth")
    else:
        warnings.append(
            "Source dataset not supplied; canonical verification provenance cannot be "
            "checked locally."
        )
    bundle_map = {fingerprint(bundle.model_dump(mode="json")): bundle for bundle in bundles}
    if len(bundle_map) != len(bundles) or set(bundle_map) - input_refs.keys():
        raise ValueError("Duplicate or unreferenced supplied lookup bundles")
    timings: dict[str, LookupTiming] = {}
    resolver_configs: set[str] = set()
    for bundle_id, bundle in bundle_map.items():
        ref = input_refs[bundle_id]
        if (
            bundle.dataset_fingerprint != dataset_hash
            or bundle.input_fingerprint != ref.input_fingerprint
            or bundle.config_fingerprint != ref.config_fingerprint
            or bundle.engine_version != ref.engine_version
        ):
            raise ValueError("Lookup bundle provenance mismatch")
        resolver_configs.add(fingerprint(bundle.config.model_dump(mode="json")))
        for result in bundle.results:
            recorded_row = rows_by_id.get(result.lookup_id)
            if recorded_row is None or recorded_row.input_bundle_id != bundle_id:
                raise ValueError("Lookup bundle inventory differs from evaluation")
            if (
                result.source_id,
                result.original_citation_id,
                result.provider,
                result.strategy,
                result.outcome,
            ) != (
                recorded_row.source_id,
                recorded_row.original_citation_id,
                recorded_row.provider,
                recorded_row.strategy,
                recorded_row.outcome,
            ) or result.candidates != tuple(j.candidate for j in recorded_row.candidates):
                raise ValueError("Lookup source/candidates differ from saved evaluation")
            if result.started_at > result.finished_at:
                raise ValueError("Invalid original lookup timestamps")
            timings[result.lookup_id] = LookupTiming(
                lookup_id=result.lookup_id,
                started_at=result.started_at,
                finished_at=result.finished_at,
            )
        if {result.lookup_id for result in bundle.results} != {
            row.lookup_id for row in rows_by_id.values() if row.input_bundle_id == bundle_id
        }:
            raise ValueError("Lookup bundle inventory is incomplete")
    if len(resolver_configs) > 1:
        raise ValueError("Incompatible resolver configurations; report runs separately")
    complete = bool(dataset and manifest and set(bundle_map) == set(input_refs))
    if set(bundle_map) != set(input_refs):
        warnings.append(
            "Original lookup bundles incomplete; actual collection timing/settings are not "
            "fully verified."
        )
    if manifest:
        if manifest.dataset_fingerprint != dataset_hash:
            raise ValueError("Study manifest dataset fingerprint mismatch")
        if set(manifest.lookup_bundle_ids) != set(input_refs):
            raise ValueError("Study lookup references differ from evaluated inputs")
        if dataset and set(manifest.citation_ids) - {c.citation_id for c in dataset.citations}:
            raise ValueError("Study inventory references unknown citations")
        if (
            config.experiment == "recent-preprints"
            and manifest.reference_date != manifest.collection_finished_at.astimezone(UTC).date()
        ):
            raise ValueError("Experiment A reference date must be the UTC collection-end date")
        for timing in timings.values():
            if (
                timing.started_at < manifest.collection_started_at
                or timing.finished_at > manifest.collection_finished_at
            ):
                raise ValueError(
                    "Actual lookup timestamps fall outside the declared collection window"
                )
        hours = (
            manifest.collection_finished_at - manifest.collection_started_at
        ).total_seconds() / 3600
        if config.experiment == "recent-preprints" and hours > config.max_collection_hours:
            warnings.append(
                f"Collection window {hours:g} hours exceeds configured "
                f"{config.max_collection_hours:g}-hour limit; "
                "observations are retained as diagnostics. Explicitly override the limit "
                "for empirical eligibility."
            )
            complete = False
        if hours > 24:
            warnings.append(
                f"Collection spans {hours:g} hours; this is not a simultaneous snapshot "
                "and paper ages may differ at actual lookup time."
            )
    else:
        warnings.append(
            "Study sampling/verification/collection manifest not supplied; empirical "
            "reporting is unavailable."
        )
    return AnalysisEvidence(
        tuple(sorted(evaluations, key=lambda e: e.evaluation_id)),
        tuple(warnings),
        complete,
        timings,
    )
