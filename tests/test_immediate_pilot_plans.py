"""Offline checks of the versioned date amendment; never execute acquisition."""

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from citeprobe.pilot_models import PilotPlan
from citeprobe.pilot_plans import validate_plan

ROOT = Path("artifacts/milestone-3c7-immediate-001")


def test_immediate_dates_and_file_and_content_fingerprints() -> None:
    inventory = json.loads((ROOT / "request-inventory.json").read_bytes())
    prepared = datetime.fromisoformat(inventory["prepared_at_utc"])
    assert inventory["reference_date"] == prepared.date().isoformat() == "2026-11-09"
    assert inventory["live_requests_authorized"] == inventory["live_requests_executed"] == 0
    assert inventory["followup_requests_authorized"] == 0
    for filename, expected in inventory["new_plans"].items():
        content = (ROOT / filename).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected["file_sha256"]
        plan = PilotPlan.model_validate_json(content)
        validate_plan(plan)
        assert plan.plan_id == expected["plan_id"]
        assert plan.planned_started_at == prepared
        assert plan.planned_finished_at - plan.planned_started_at == timedelta(hours=24)
        assert plan.maximum_requests == expected["maximum_requests"]
        assert [r.model_dump(mode="json") for r in plan.requests] == expected["requests"]
        assert all(r.source_day is None or r.source_day < prepared.date() for r in plan.requests)


def test_immediate_inventory_exact_source_days_and_request_bounds() -> None:
    plan = PilotPlan.model_validate_json((ROOT / "a-enumeration-plan.json").read_bytes())
    assert plan.reference_date == date(2026, 11, 9)
    assert plan.date_basis == "first_arxiv_submission"
    assert plan.maximum_requests == len(plan.requests) == 8
    expected = {
        "1-7": date(2026, 11, 5),
        "8-14": date(2026, 10, 29),
        "15-30": date(2026, 10, 18),
        "31-60": date(2026, 9, 25),
    }
    for row in plan.requests:
        day = expected[row.group]
        assert row.source_day == day
        assert row.offset in {0, 100}
        assert row.conditional == (row.offset == 100)
        url = urlsplit(row.request.url)
        assert row.request.method == "GET"
        assert url.scheme == "https" and url.netloc == "export.arxiv.org"
        assert url.path == "/api/query"
        assert parse_qs(url.query) == {
            "search_query": [f"cat:cs.CL AND submittedDate:[{day:%Y%m%d}0000 TO {day:%Y%m%d}2359]"],
            "start": [str(row.offset)],
            "max_results": ["100"],
            "sortBy": ["submittedDate"],
            "sortOrder": ["ascending"],
        }
    acl = PilotPlan.model_validate_json((ROOT / "acl-resolution-plan.json").read_bytes())
    assert acl.maximum_requests == len(acl.requests) == 1
    assert acl.revision is None  # No observed commit has been fabricated.
    assert acl.requests[0].request.url == (
        "https://api.github.com/repos/acl-org/acl-anthology/commits?per_page=1"
    )


def test_original_plans_and_protocols_preserved() -> None:
    preserved = json.loads((ROOT / "preserved-inputs.json").read_bytes())["files_sha256"]
    for filename, expected in preserved.items():
        assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected, filename
    old = PilotPlan.model_validate_json(
        Path("artifacts/milestone-3c7-offline/a-enumeration-plan.json").read_bytes()
    )
    assert old.reference_date == date(2026, 11, 23)
