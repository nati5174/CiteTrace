"""Build provider-safe inputs without exposing the canonical record to adapters."""

import hashlib
import json

from citeprobe.dataset import benchmark_citations
from citeprobe.models import CitationValues, Dataset, MutationBatch
from citeprobe.resolution_models import LookupTask, SearchMetadata, Strategy


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def metadata(values: CitationValues) -> SearchMetadata:
    return SearchMetadata(
        title=values.title,
        authors=values.authors,
        year=values.year,
        volume=values.volume,
        issue=values.issue,
    )


def canonical_tasks(dataset: Dataset, strategy: Strategy = "metadata") -> tuple[LookupTask, ...]:
    return tuple(
        LookupTask(
            source_id=c.citation_id,
            source_kind="canonical",
            original_citation_id=c.citation_id,
            metadata=metadata(c),
            strategy=strategy,
            identifier=(c.doi or f"arXiv:{c.arxiv_id}") if strategy == "identifier" else None,
        )
        for c in benchmark_citations(dataset)
    )


def mutation_tasks(dataset: Dataset, batch: MutationBatch) -> tuple[LookupTask, ...]:
    if batch.dataset_version != dataset.dataset_version:
        raise ValueError("Mutation dataset version does not match")
    originals = {c.citation_id: c for c in dataset.citations}
    seen: set[str] = set()
    tasks: list[LookupTask] = []
    for mutation in batch.mutations:
        if mutation.mutation_id in seen:
            raise ValueError("Duplicate mutation IDs")
        seen.add(mutation.mutation_id)
        original = originals.get(mutation.original_citation_id)
        if original is None:
            raise ValueError("Mutation references an unknown canonical citation")
        if original.provenance.verification_status != "verified":
            raise ValueError("Mutation references a pending-verification citation")
        if (mutation.citation.doi, mutation.citation.arxiv_id) != (original.doi, original.arxiv_id):
            raise ValueError("Mutation canonical identifiers do not match source")
        changed = {
            k for k, v in mutation.citation.model_dump().items() if v != original.model_dump()[k]
        }
        if changed != set(mutation.mutated_fields):
            raise ValueError("Mutation changed fields do not match declaration")
        # Only mutation values cross this boundary. Original metadata is never substituted.
        tasks.append(
            LookupTask(
                source_id=mutation.mutation_id,
                source_kind="mutation",
                original_citation_id=mutation.original_citation_id,
                metadata=metadata(mutation.citation),
            )
        )
    return tuple(tasks)
