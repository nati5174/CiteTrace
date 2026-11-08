"""Conservative work identity. Identifier inequality alone is never a negative label."""

import re
from urllib.parse import unquote, urlsplit

from citeprobe.evaluation_models import CandidateJudgment, IdentityIdentifier, IdentityMappings
from citeprobe.models import Citation, Dataset
from citeprobe.resolution_models import Candidate, ProviderName

DOI = re.compile(r"10\.\d{4,9}/\S+", re.ASCII)
ARXIV = re.compile(
    r"(?P<base>\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v[1-9]\d*)?",
    re.IGNORECASE | re.ASCII,
)
ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def normalize_doi(value: str) -> str | None:
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    if value.lower().startswith(("http://", "https://")):
        try:
            url = urlsplit(value)
            if (
                url.hostname not in {"doi.org", "dx.doi.org"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.port is not None
            ):
                return None
            value = unquote(url.path.removeprefix("/"), errors="strict")
        except (ValueError, UnicodeError):
            return None
    return value.translate(ASCII_LOWER) if DOI.fullmatch(value) else None


def normalize_arxiv(value: str) -> str | None:
    value = value.strip()
    if value.lower().startswith("arxiv:"):
        value = value[6:].strip()
    if value.lower().startswith(("http://", "https://")):
        try:
            url = urlsplit(value)
            if (
                url.hostname not in {"arxiv.org", "www.arxiv.org"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.port is not None
            ):
                return None
            if url.path.startswith("/abs/"):
                value = url.path[5:]
            elif url.path.startswith("/pdf/"):
                value = url.path[5:].removesuffix(".pdf")
            else:
                return None
        except ValueError:
            return None
    match = ARXIV.fullmatch(value)
    return match["base"].translate(ASCII_LOWER) if match else None


def normalize_identifier(identifier: IdentityIdentifier) -> str | None:
    namespace, value = identifier.namespace, identifier.value
    if namespace in {"doi", "crossref"}:
        normalized = normalize_doi(value)
    elif namespace == "arxiv":
        normalized = normalize_arxiv(value)
    else:
        normalized = value.strip()
        if normalized.startswith(("https://openalex.org/", "http://openalex.org/")):
            normalized = normalized.rsplit("/", 1)[-1]
        normalized = normalized.upper()
        if not re.fullmatch(r"W[1-9]\d*", normalized, flags=re.ASCII):
            return None
    return f"{namespace}:{normalized}" if normalized else None


def citation_identifiers(citation: Citation) -> set[str]:
    result: set[str] = set()
    for namespace, value in (("doi", citation.doi), ("arxiv", citation.arxiv_id)):
        if value is not None:
            key = normalize_identifier(IdentityIdentifier(namespace=namespace, value=value))
            if key is None:
                raise ValueError("Ground-truth identifier cannot be normalized safely")
            result.add(key)
    return result


class IdentityIndex:
    def __init__(self, dataset: Dataset, mappings: IdentityMappings) -> None:
        if mappings.dataset_version != dataset.dataset_version:
            raise ValueError("Identity mapping dataset version mismatch")
        originals = {c.citation_id: c for c in dataset.citations}
        self.same = {c.citation_id: citation_identifiers(c) for c in dataset.citations}
        self.different: dict[str, set[str]] = {key: set() for key in originals}
        for mapping in mappings.mappings:
            original = originals.get(mapping.citation_id)
            if original is None or original.provenance.verification_status != "verified":
                raise ValueError("Identity mapping must reference verified ground truth")
            if mapping.provenance.verification_status != "verified":
                raise ValueError("Identity mappings require verified provenance")
            for identifier in mapping.identifiers:
                key = normalize_identifier(identifier)
                if key is None:
                    raise ValueError("Invalid identity mapping identifier")
                target = self.same if mapping.relation == "same_work" else self.different
                target[mapping.citation_id].add(key)
                # Crossref work record IDs are DOIs, not an independent identity namespace.
                if key.startswith("crossref:"):
                    target[mapping.citation_id].add("doi:" + key.removeprefix("crossref:"))
                if key.startswith("doi:"):
                    target[mapping.citation_id].add("crossref:" + key.removeprefix("doi:"))
        for citation_id in originals:
            if self.same[citation_id] & self.different[citation_id]:
                raise ValueError("Conflicting same-work and different-work identity mappings")

    def judge(
        self, citation_id: str, provider: ProviderName, candidate: Candidate
    ) -> CandidateJudgment:
        identifiers = [IdentityIdentifier(namespace=provider, value=candidate.provider_record_id)]
        if candidate.doi is not None:
            identifiers.append(IdentityIdentifier(namespace="doi", value=candidate.doi))
        if candidate.arxiv_id is not None:
            identifiers.append(IdentityIdentifier(namespace="arxiv", value=candidate.arxiv_id))
        keys: set[str] = set()
        malformed = False
        for identifier in identifiers:
            key = normalize_identifier(identifier)
            if key:
                keys.add(key)
                if key.startswith("crossref:"):
                    keys.add("doi:" + key.removeprefix("crossref:"))
            else:
                malformed = True
        positive = keys & self.same[citation_id]
        negative = keys & self.different[citation_id]
        if malformed or (positive and negative):
            judgment, reason = "UNDETERMINED", "Malformed or conflicting identity evidence"
        elif positive:
            judgment, reason = "CORRECT", "Verified identifier or same-work mapping match"
        elif negative:
            judgment, reason = "INCORRECT", "Explicit verified different-work mapping"
        else:
            judgment, reason = "UNDETERMINED", "No verified evidence of identity or distinctness"
        return CandidateJudgment(
            candidate=candidate,
            judgment=judgment,
            reason=reason,
            normalized_identifiers=tuple(sorted(keys)),
            matching_evidence=tuple(sorted(positive)),
            distinct_evidence=tuple(sorted(negative)),
        )
