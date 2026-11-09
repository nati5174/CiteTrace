"""Narrow approved resource override; default evidence semantics stay unchanged."""

from citeprobe.evidence_models import EvidenceRequest

DEFAULT_LIMIT = 2_000_000
ACL_2023_LIMIT = 4_000_000
ACL_2023_URL = (
    "https://raw.githubusercontent.com/acl-org/acl-anthology/"
    "032cc14d4a17181e8754f33512c22ff53d9cbbc6/data/xml/2023.acl.xml"
)
RESOURCE_POLICY_PATH = "docs/research/amendments/b-acl-resource-v1.json"


def validate_request_limit(request: EvidenceRequest, limit: int) -> None:
    if type(limit) is not int or limit not in {DEFAULT_LIMIT, ACL_2023_LIMIT}:
        raise ValueError("Unsupported per-request resource limit")
    if limit != DEFAULT_LIMIT and (
        request.url != ACL_2023_URL or request.source_kind != "acquisition_xml"
    ):
        raise ValueError("4 MB exception applies only to the exact pinned ACL 2023 XML request")


def recovery_limit(request: EvidenceRequest) -> int:
    result = ACL_2023_LIMIT if request.url == ACL_2023_URL else DEFAULT_LIMIT
    validate_request_limit(request, result)
    return result
