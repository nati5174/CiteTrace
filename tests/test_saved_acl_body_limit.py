"""HTTP success and prefix integrity must never masquerade as complete source data."""

import hashlib
from collections import Counter
from pathlib import Path

import pytest

from citeprobe.acl_scope import scoped_collection
from citeprobe.evidence_io import verify_batch
from citeprobe.evidence_models import RawEvidence
from citeprobe.pilot_run import load_run, response_body

ROOT = Path("artifacts/empirical-pilot-immediate-001/b-amended-continuation-002")


def test_saved_2023_http_200_is_an_incomplete_local_bound_failure() -> None:
    run = load_run(ROOT)
    bundle = ROOT / "attempt-006"
    record = RawEvidence.model_validate_json((bundle / "request-001/record.json").read_bytes())
    body = (bundle / "request-001/body.bin").read_bytes()
    assert record.http_status == 200 and not record.body_complete
    assert record.raw_body_size == len(body) == 2_000_000
    assert int(record.response_headers["content-length"]) == 2_796_134
    assert record.exception_type == "ValueError"
    assert hashlib.sha256(body).hexdigest() == record.raw_body_sha256
    extraction = verify_batch(bundle)[0]
    assert extraction.status == "UNAVAILABLE"
    with pytest.raises(ValueError, match="Failed/incomplete"):
        response_body(bundle, run.plan.requests[5], run.plan.origin)


def test_saved_2022_remains_complete_and_reusable() -> None:
    run = load_run(ROOT)
    body, record = response_body(ROOT / "attempt-005", run.plan.requests[4], run.plan.origin)
    assert record.http_status == 200 and record.body_complete
    assert record.raw_body_size == 1_557_278
    selection = scoped_collection(body, run.plan.requests[4])
    assert dict(Counter(selection.source_record_volumes.values())) == {"long": 603, "short": 97}
    assert len(selection.items) == 700


def test_all_arxiv_pages_are_unattempted_and_failed_receipt_preserved() -> None:
    run = load_run(ROOT)
    assert len(run.attempts) == 6
    assert run.stopped_reason == "Failed/incomplete source attempt; no retry or replacement"
    remaining = run.plan.requests[len(run.attempts) :]
    assert len(remaining) == 12
    assert all(r.collection is None and r.offset in {0, 100} for r in remaining)
    assert sum(r.conditional for r in remaining) == 6
