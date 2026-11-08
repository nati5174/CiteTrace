"""Validate recorded experiments against local inputs without performing HTTP requests."""

from dataclasses import dataclass

from citeprobe.evaluation_models import DataLabel, EvaluationConfig
from citeprobe.lookup_inputs import canonical_tasks, fingerprint, mutation_tasks
from citeprobe.models import Dataset, MutationBatch, MutationType
from citeprobe.mutations import mutate
from citeprobe.providers import Crossref, OpenAlex
from citeprobe.resolution_models import LookupBundle, LookupTask, RequestMetadata, Strategy


@dataclass(frozen=True)
class ValidatedInput:
    bundle: LookupBundle
    bundle_id: str
    label: DataLabel
    mutation_types: dict[str, MutationType]


def validate_inputs(
    dataset: Dataset,
    bundles: tuple[LookupBundle, ...],
    mutations: tuple[MutationBatch, ...],
    config: EvaluationConfig,
) -> tuple[ValidatedInput, ...]:
    if not bundles:
        raise ValueError("At least one lookup bundle is required")
    dataset_hash = fingerprint(dataset.model_dump(mode="json"))
    originals = {c.citation_id: c for c in dataset.citations}
    if set(config.cohorts) - originals.keys():
        raise ValueError("Cohort references an unknown citation")
    batches: dict[str, tuple[dict[str, LookupTask], dict[str, MutationType]]] = {}
    for batch in mutations:
        tasks = mutation_tasks(dataset, batch)
        for mutation in batch.mutations:
            if mutation.seed != batch.seed:
                raise ValueError("Mutation seed differs from its batch")
            delta = mutation.parameters.get("delta", 1)
            if not isinstance(delta, int):
                raise ValueError("Invalid year mutation parameter")
            expected = mutate(
                originals[mutation.original_citation_id],
                mutation.mutation_type,
                seed=mutation.seed,
                year_delta=delta,
            )
            if expected != mutation:
                raise ValueError("Mutation does not reproduce from its recorded parameters")
        batch_hash = fingerprint(batch.model_dump(mode="json", exclude={"generated_at"}))
        if batch_hash in batches:
            raise ValueError("Duplicate mutation input batches")
        batches[batch_hash] = (
            {task.source_id: task for task in tasks},
            {mutation.mutation_id: mutation.mutation_type for mutation in batch.mutations},
        )
    validated: list[ValidatedInput] = []
    seen_ids: set[str] = set()
    seen_bundles: set[str] = set()
    seen_observations: set[tuple[str, str, str, str]] = set()
    for bundle in bundles:
        bundle_id = fingerprint(bundle.model_dump(mode="json"))
        if bundle_id in seen_bundles:
            raise ValueError("Duplicate lookup input bundle")
        seen_bundles.add(bundle_id)
        if (
            bundle.dataset_version != dataset.dataset_version
            or bundle.dataset_fingerprint != dataset_hash
        ):
            raise ValueError("Lookup dataset version/fingerprint mismatch")
        if bundle.config != bundles[0].config:
            raise ValueError("Incompatible resolver configurations; evaluate runs separately")
        if not bundle.providers or len(set(bundle.providers)) != len(bundle.providers):
            raise ValueError("Invalid or duplicate provider inventory")
        if len(set(bundle.selected_source_ids)) != len(bundle.selected_source_ids):
            raise ValueError("Duplicate selected source IDs")
        strategies = {r.strategy for r in bundle.results}
        if len(strategies) > 1:
            raise ValueError("Mixed lookup strategies within one input bundle")
        strategy: Strategy = next(iter(strategies)) if strategies else "metadata"
        if bundle.input_fingerprint == dataset_hash:
            source_kind = "canonical"
            tasks_by_id = {t.source_id: t for t in canonical_tasks(dataset, strategy)}
            types: dict[str, MutationType] = {}
        elif bundle.input_fingerprint in batches:
            source_kind = "mutation"
            tasks_by_id, types = batches[bundle.input_fingerprint]
            if strategy != "metadata":
                raise ValueError("Mutation lookup must be metadata-only")
        else:
            raise ValueError(
                "Unknown input fingerprint; provide the original mutation batch if needed"
            )
        if set(bundle.selected_source_ids) - tasks_by_id.keys():
            raise ValueError("Lookup references an unknown or unverified source")
        pairs = [(r.source_id, r.provider) for r in bundle.results]
        expected_pairs = [
            (source, provider)
            for source in bundle.selected_source_ids
            for provider in bundle.providers
        ]
        if pairs != expected_pairs:
            raise ValueError("Lookup inventory/order does not match selected sources and providers")
        expected_config = fingerprint(
            {
                "engine_version": bundle.engine_version,
                "config": bundle.config.model_dump(mode="json"),
                "providers": bundle.providers,
                "selection": [(source, strategy) for source in bundle.selected_source_ids],
            }
        )
        if bundle.config_fingerprint != expected_config:
            raise ValueError("Lookup configuration fingerprint mismatch")
        for result in bundle.results:
            if result.lookup_id in seen_ids:
                raise ValueError("Duplicate lookup IDs")
            seen_ids.add(result.lookup_id)
            observation = (result.source_kind, result.source_id, result.provider, result.strategy)
            if observation in seen_observations:
                raise ValueError("Duplicate lookup observation")
            seen_observations.add(observation)
            task = tasks_by_id[result.source_id]
            if (
                result.source_kind != source_kind
                or result.original_citation_id != task.original_citation_id
            ):
                raise ValueError("Lookup-to-canonical source reference mismatch")
            adapter = OpenAlex() if result.provider == "openalex" else Crossref()
            request = adapter.request(task.metadata, task.identifier)
            expected_request = RequestMetadata(
                endpoint=request.endpoint,
                params=request.params,
                submitted_metadata=task.metadata if task.strategy == "metadata" else None,
                submitted_identifier=task.identifier,
            )
            if result.request != expected_request:
                raise ValueError("Submitted request differs from source metadata/strategy")
            if source_kind == "mutation":
                original = originals[task.original_citation_id]
                text = " ".join(result.request.params.values()).casefold()
                if any(
                    value and value.casefold() in text
                    for value in (
                        original.doi,
                        original.arxiv_id,
                        original.citation_id,
                        result.source_id,
                    )
                ):
                    raise ValueError("Mutation request leaks ground-truth/evaluation identifiers")
            expected_id = fingerprint(
                {
                    "engine_version": bundle.engine_version,
                    "provider": result.provider,
                    "source_kind": result.source_kind,
                    "source_id": result.source_id,
                    "strategy": result.strategy,
                    "request": result.request.model_dump(),
                }
            )
            if result.lookup_id != expected_id:
                raise ValueError("Lookup ID does not match its source/request")
            ranks = [c.provider_rank for c in result.candidates]
            if ranks != sorted(set(ranks)) or any(rank > 5 for rank in ranks):
                raise ValueError("Invalid, duplicate or reordered provider ranks")
            if not result.attempts or len(result.attempts) > bundle.config.max_attempts:
                raise ValueError("Invalid attempt inventory")
            last = result.attempts[-1]
            if (
                last.outcome != result.outcome
                or last.response_status != result.response_status
                or result.retry_count != max(0, sum(a.request_sent for a in result.attempts) - 1)
            ):
                raise ValueError("Lookup outcome/status/retries disagree with attempts")
            if result.started_at > result.finished_at or any(
                a.started_at > a.finished_at for a in result.attempts
            ):
                raise ValueError("Invalid lookup timestamps")
            if result.outcome in {"FOUND", "NOT_FOUND"}:
                if (
                    result.response_status is None
                    or not 200 <= result.response_status < 300
                    or not last.request_sent
                ):
                    raise ValueError("Retrieval success requires a successful HTTP response")
                parsed, warnings = adapter.parse(last.response)
                if parsed != result.candidates or warnings != result.parsing_warnings:
                    raise ValueError(
                        "Candidates/ranking/warnings disagree with saved provider evidence"
                    )
                if result.outcome == "FOUND" and not result.candidates:
                    raise ValueError("FOUND requires candidates")
                if result.outcome == "NOT_FOUND" and (result.candidates or warnings):
                    raise ValueError("NOT_FOUND requires valid empty retrieval")
            elif result.candidates:
                raise ValueError("Failure/unknown outcomes must not contain candidates")
        validated.append(
            ValidatedInput(
                bundle,
                bundle_id,
                config.input_labels.get(bundle_id, config.default_data_label),
                types,
            )
        )
    if set(config.input_labels) - {item.bundle_id for item in validated}:
        raise ValueError("Data label references an unknown bundle fingerprint")
    return tuple(sorted(validated, key=lambda item: item.bundle_id))
