import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from citeprobe.benchmark_remaining import prepare, run, verify_output
from citeprobe.dataset import load_dataset
from citeprobe.evaluation import evaluate
from citeprobe.evaluation_models import EvaluationConfig, IdentityMappings
from citeprobe.lookup_inputs import fingerprint
from citeprobe.resolution_models import LookupBundle

ROOT = Path("artifacts/empirical-pilot-immediate-001")
SNAPSHOT = ROOT / "a-frozen-001"
PRIOR = ROOT / "a-benchmark-smoke-002"


@pytest.fixture
def plan() -> dict[str, Any]:
    return prepare(SNAPSHOT, PRIOR)


def test_inventory(plan: dict[str, Any]) -> None:
    assert plan == prepare(SNAPSHOT, PRIOR)
    rows = plan["requests"]
    assert len(rows) == 14
    assert len({r["url"] for r in rows}) == 14
    assert len({r["source_id"] for r in rows}) == 7
    assert all(
        [r["provider"] for r in rows[i : i + 2]] == ["openalex", "crossref"]
        for i in range(0, 14, 2)
    )
    assert all(r["source_id"] not in r["url"] and "10.48550" not in r["url"].lower() for r in rows)


@pytest.mark.parametrize("stop_at", [None, 1, 2, 7, 14])
def test_mocked_sequential_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any], stop_at: int | None
) -> None:
    async def no_wait(_: float) -> None:
        pass

    monkeypatch.setattr("citeprobe.benchmark_remaining.asyncio.sleep", no_wait)
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if len(calls) == stop_at:
            return httpx.Response(429, stream=httpx.ByteStream(b"rate limited"))
        body = (
            b'{"results":[]}'
            if "openalex" in req.url.host
            else b'{"status":"ok","message":{"items":[]}}'
        )
        return httpx.Response(200, stream=httpx.ByteStream(body))

    output = tmp_path / "output"
    result = asyncio.run(run(SNAPSHOT, PRIOR, plan, output, transport=httpx.MockTransport(handler)))
    assert result is (stop_at is None)
    assert len(calls) == (14 if stop_at is None else stop_at)
    assert calls == [r["url"] for r in plan["requests"][: len(calls)]]
    verify_output(output)
    receipt = json.loads((output / "receipt.json").read_bytes())
    assert receipt["origin"] == "simulated" and receipt["requests"] == len(calls)
    if stop_at is None:
        files = list(output.glob("paper-*/*-lookups.json"))
        files.extend([PRIOR / "openalex-lookups.json", PRIOR / "crossref-lookups.json"])
        bundles = tuple(LookupBundle.model_validate_json(f.read_bytes()) for f in files)
        labels = {fingerprint(b.model_dump(mode="json")): "observed" for b in bundles[-2:]}
        cohorts = json.loads((SNAPSHOT / "selection.json").read_bytes())["groups"]
        dataset = load_dataset(SNAPSHOT / "dataset.json")
        cohorts = {c.citation_id: cohorts[c.citation_id] for c in dataset.citations}
        config = EvaluationConfig.model_validate(
            {"default_data_label": "simulated", "input_labels": labels, "cohorts": cohorts}
        )
        mappings = IdentityMappings.model_validate_json(
            (SNAPSHOT / "identity-mappings.json").read_bytes()
        )
        result_eval = evaluate(dataset, bundles, mappings=mappings, config=config)
        assert len(result_eval.lookups) == 16
        assert sum(row.data_label == "observed" for row in result_eval.lookups) == 2
        assert {g.dimensions["data_label"] for g in result_eval.groups} == {"observed", "simulated"}
    with pytest.raises(FileExistsError):
        asyncio.run(run(SNAPSHOT, PRIOR, plan, output, transport=httpx.MockTransport(handler)))
    body = next(output.glob("paper-*/attempt-*/body.bin"))
    body.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        verify_output(output)


def test_changed_plan_rejected_before_output(tmp_path: Path, plan: dict[str, Any]) -> None:
    changed = copy.deepcopy(plan)
    changed["requests"][0]["url"] += "&leak=2611.07721"
    with pytest.raises(ValueError, match="Plan differs"):
        asyncio.run(
            run(
                SNAPSHOT,
                PRIOR,
                changed,
                tmp_path / "output",
                transport=httpx.MockTransport(lambda _: httpx.Response(200)),
            )
        )
    assert not (tmp_path / "output").exists()
