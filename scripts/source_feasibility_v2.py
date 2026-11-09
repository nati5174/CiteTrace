"""Future separately authorized evidence batch; never reuse Milestone 3C-4 approval."""

import argparse
import hashlib
import time
from pathlib import Path

import httpx

from citeprobe.evidence_io import begin_batch, capture_sync, finish_batch
from citeprobe.evidence_models import EvidenceBudget

ALLOWED = {
    "https://info.arxiv.org/help/api/user-manual.html": "arxiv_api_doc",
    "https://info.arxiv.org/help/rss.html": "arxiv_rss_doc",
    "https://info.arxiv.org/help/atom_specifications.html": "arxiv_rss_doc",
    "https://rss.arxiv.org/atom/cs.CL": "arxiv_atom",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--execute-authorized-batch", action="store_true")
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.execute_authorized_batch:
        parser.error("No requests without separately approved execution")
    content = args.plan.read_bytes()
    if hashlib.sha256(content).hexdigest() != args.plan_sha256:
        raise ValueError("Approved plan hash mismatch")
    budget = EvidenceBudget.model_validate_json(content)
    if (
        budget.origin != "observed"
        or budget.maximum_requests > 3
        or budget.authorization_reference != args.authorization_reference
    ):
        raise ValueError("Invalid new live authorization budget")
    for request in budget.requests:
        if ALLOWED.get(request.url) != request.source_kind:
            raise ValueError("Unsupported source or source-kind mismatch")
    begin_batch(args.output_dir, budget)
    with httpx.Client(
        transport=httpx.HTTPTransport(retries=0),
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for ordinal in range(1, len(budget.requests) + 1):
            record = capture_sync(client, args.output_dir, budget, ordinal)
            print(f"{ordinal}: HTTP {record.http_status}; {record.exception_type}")
            if record.exception_type == "ConnectError":
                break
            if ordinal < len(budget.requests):
                time.sleep(3)
    print("External integrity anchor: " + finish_batch(args.output_dir))


if __name__ == "__main__":
    main()
