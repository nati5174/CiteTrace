"""Deterministic, independent perturbations; never update canonical records."""

import hashlib
import json
import re
from datetime import UTC, datetime

from citeprobe.models import (
    Citation,
    CitationValues,
    Dataset,
    MutableField,
    Mutation,
    MutationBatch,
    MutationType,
    SkippedMutation,
)

TYPES: tuple[MutationType, ...] = (
    "title_typo",
    "author_initials",
    "year_shift",
    "title_word_deletion",
    "digit_transposition",
)


class InapplicableMutation(ValueError):
    """The requested perturbation cannot meaningfully change this citation."""


def mutate(
    original: Citation, kind: MutationType, *, seed: int = 0, year_delta: int = 1
) -> Mutation:
    if original.provenance.verification_status != "verified":
        raise ValueError("Pending-verification citations cannot be mutated for benchmark use")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if kind not in TYPES:
        raise ValueError(f"Unknown mutation type: {kind}")
    payload = CitationValues.model_validate(
        original.model_dump(exclude={"citation_id", "provenance"})
    ).model_dump()
    digest = hashlib.sha256(f"1:{seed}:{original.citation_id}:{kind}".encode()).digest()
    choice = int.from_bytes(digest, "big")
    parameters: dict[str, int | str] = {}
    field: MutableField
    if kind == "title_typo":
        positions = [
            i for i, char in enumerate(original.title) if char.isascii() and char.isalpha()
        ]
        if not positions:
            raise InapplicableMutation("No ASCII letters in title")
        index = positions[choice % len(positions)]
        old = original.title[index]
        new = chr((ord(old.lower()) - ord("a") + 1) % 26 + ord("a"))
        if old.isupper():
            new = new.upper()
        payload["title"] = original.title[:index] + new + original.title[index + 1 :]
        parameters = {"character_index": index, "replacement": new}
        field = "title"
    elif kind == "author_initials":
        authors = []
        for author in original.authors:
            given = author.given
            if given:
                parts = [part for part in re.split(r"[\s-]+", given) if part]
                given = " ".join(part[0] + "." for part in parts) if parts else given
            authors.append({"given": given, "family": author.family})
        payload["authors"] = authors
        field = "authors"
    elif kind == "year_shift":
        if type(year_delta) is not int or year_delta not in (-1, 1):
            raise ValueError("year_delta must be -1 or +1")
        if not 1 <= original.year + year_delta <= 9999:
            raise InapplicableMutation("Year shift exceeds supported range")
        payload["year"] = original.year + year_delta
        parameters = {"delta": year_delta}
        field = "year"
    elif kind == "title_word_deletion":
        words = list(re.finditer(r"\S+", original.title))
        if len(words) < 2:
            raise InapplicableMutation("Title has fewer than two words")
        index = choice % len(words)
        word = words[index]
        payload["title"] = (original.title[: word.start()] + original.title[word.end() :]).strip()
        parameters = {"word_index": index, "deleted_word": word.group()}
        field = "title"
    else:
        options: list[tuple[MutableField, str, int]] = []
        for name in ("volume", "issue"):
            value = getattr(original, name)
            if value:
                for i in range(len(value) - 1):
                    if value[i : i + 2].isascii() and value[i : i + 2].isdigit():
                        if value[i] != value[i + 1]:
                            options.append((name, value, i))
        if not options:
            raise InapplicableMutation("No unequal adjacent volume/issue digits")
        field, value, index = options[choice % len(options)]
        payload[field] = value[:index] + value[index + 1] + value[index] + value[index + 2 :]
        parameters = {"digit_index": index}
    citation = CitationValues.model_validate(payload)
    if citation.model_dump()[field] == original.model_dump()[field]:
        raise InapplicableMutation("Mutation would leave citation unchanged")
    identity = json.dumps(
        [original.citation_id, kind, seed, parameters, citation.model_dump()], sort_keys=True
    )
    return Mutation(
        mutation_id=hashlib.sha256(identity.encode()).hexdigest(),
        mutation_type=kind,
        original_citation_id=original.citation_id,
        mutated_fields=(field,),
        parameters=parameters,
        seed=seed,
        citation=citation,
    )


def generate_mutations(dataset: Dataset, *, seed: int = 0) -> MutationBatch:
    mutations: list[Mutation] = []
    skipped: list[SkippedMutation] = []
    for original in dataset.citations:
        for kind in TYPES:
            if original.provenance.verification_status != "verified":
                skipped.append(
                    SkippedMutation(
                        original_citation_id=original.citation_id,
                        mutation_type=kind,
                        reason="Pending verification",
                    )
                )
                continue
            for delta in (-1, 1) if kind == "year_shift" else (1,):
                try:
                    mutations.append(mutate(original, kind, seed=seed, year_delta=delta))
                except InapplicableMutation as error:
                    skipped.append(
                        SkippedMutation(
                            original_citation_id=original.citation_id,
                            mutation_type=kind,
                            reason=str(error),
                        )
                    )
    return MutationBatch(
        dataset_version=dataset.dataset_version,
        seed=seed,
        generated_at=datetime.now(UTC),
        mutations=tuple(mutations),
        skipped=tuple(skipped),
    )
