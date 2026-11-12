"""Manifest evidence, privacy, schema and public offline-calculation regressions."""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from citeprobe.public_manifest import ExperimentManifest, HistoricalSearch
from scripts.export_experiment_manifest import TARGET, export_manifest, verify_inventory


def verifier() -> Any:
    namespace: dict[str, Any] = {"__name__": "public_verify"}
    path = Path("public-demo/verify.py")
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    return namespace["verify"]


def test_manifest_matches_frozen_capture_inventory() -> None:
    recorded = ExperimentManifest.model_validate_json(TARGET.read_bytes())
    assert recorded == export_manifest()
    assert recorded.historical_execution_revision == "not_recorded"
    assert len(recorded.searches) == 16
    assert Counter((r.provider, r.authentication_mode) for r in recorded.searches) == {
        ("openalex", "anonymous"): 1,
        ("openalex", "api_key_query_parameter"): 7,
        ("crossref", "anonymous"): 8,
    }
    for row in recorded.searches:
        assert row.request_started_at != "not_recorded"
        assert row.response_capture_finished_at != "not_recorded"
        assert row.response_headers_received_at == "not_recorded"
        assert all(s.artifact_id.startswith("urn:citeprobe:") for s in row.sources)
    serialized = TARGET.read_text(encoding="utf-8")
    assert all(
        s not in serialized
        for s in ('"headers":', '"response":', '"api_key":', "C:\\\\Users", '"body":', '"email":')
    )


@pytest.mark.parametrize("change", ["credential", "endpoint", "limit", "status", "ranks", "time"])
def test_manifest_rejects_invalid_or_sensitive_search(change: str) -> None:
    row = json.loads(TARGET.read_bytes())["searches"][0]
    if change == "credential":
        row["parameters"]["api_key"] = "synthetic-private-value"
    elif change == "endpoint":
        row["endpoint"] = "https://private.invalid/"
    elif change == "limit":
        row["parameters"]["per_page"] = "100"
    elif change == "status":
        row["http_status"] = 429
    elif change == "time":
        row["request_started_at"] = "2026-11-09T00:00:00"
    else:
        row["candidate_ranks"] = [2, 1]
    with pytest.raises(ValidationError):
        HistoricalSearch.model_validate(row)


def test_manifest_rejects_duplicate_inventory() -> None:
    data = json.loads(TARGET.read_bytes())
    data["searches"][1] = data["searches"][0]
    with pytest.raises(ValidationError):
        ExperimentManifest.model_validate(data)


def test_capture_integrity_mismatch_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "record.json").write_text("{}", encoding="utf-8")
    (tmp_path / "integrity.json").write_text(
        json.dumps({"files": {"record.json": "0" * 64}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="integrity"):
        verify_inventory(tmp_path)


def test_offline_verifier_reproduces_published_bounds() -> None:
    result = verifier()(Path("public-demo/data.json"), TARGET)
    assert result["identity_judgments"] == {"UNDETERMINED": 41}
    for provider, returned, entries, upper in (("openalex", 1, 1, 1), ("crossref", 8, 40, 8)):
        summary = result["providers"][provider]
        assert summary["searches_returning_candidates"] == returned
        assert summary["candidate_entries"] == entries
        assert summary["recall_at_5_evidence_bound_counts"] == [0, upper]
        assert summary["denominator"] == 8


def test_offline_verifier_rejects_modified_data(tmp_path: Path) -> None:
    data = json.loads(Path("public-demo/data.json").read_bytes())
    data["papers"][0]["results"]["crossref"]["candidates"][0]["judgment"] = "CORRECT"
    changed = tmp_path / "data.json"
    changed.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        verifier()(changed, TARGET)


def test_offline_verifier_cli_is_standalone() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "public-demo/verify.py", "public-demo/data.json", str(TARGET)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["recorded_searches"] == 16


def test_public_assets_are_sanitized_and_self_contained() -> None:
    assets = list(Path("public-demo").iterdir())
    expected = {
        "index.html",
        "methodology.html",
        "style.css",
        "refine.css",
        "integrated.css",
        "app.js",
        "integrated.js",
        "data.json",
        "experiment-manifest.json",
        "verify.py",
        "fonts",
    }
    names = {p.name for p in assets}
    assert expected <= names
    assert names - expected <= {"replay"}
    patterns = (
        r"(?i)(?:api[_-]?key|authorization|access[_-]?token|bearer)\s*[:=]",
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)(?:C:\\\\Users|/Users/|/home/)",
        r"(?:gh[pousr]_[a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9_-]{20,}|AKIA[A-Z0-9]{16})",
    )
    for asset in assets:
        if asset.name == "replay":
            assert {p.name for p in asset.iterdir()} == {
                "index.html", "camera.js", "data.json", "evidence-layout.js",
                "evidence-map.css", "evidence-map.js", "inspector.js",
                "investigation.css", "polish.css", "replay.css", "replay.js", "tokens.css",
            }
            continue
        if asset.name == "fonts":
            assert {p.name for p in asset.iterdir()} == {
                "IBMPlexSans-Regular.woff",
                "IBMPlexSans-SemiBold.woff",
                "IBMPlexSans-Bold.woff",
                "IBMPlexMono-Regular.woff",
                "Sans-LICENSE.txt",
                "Mono-LICENSE.txt",
            }
            for font in asset.glob("*.woff"):
                assert font.read_bytes()[:4] == b"wOFF", font.name
            for license_file in asset.glob("*-LICENSE.txt"):
                assert "SIL OPEN FONT LICENSE" in license_file.read_text(encoding="utf-8")
            continue
        contents = asset.read_text(encoding="utf-8")
        assert not any(re.search(pattern, contents) for pattern in patterns), asset.name
    css = Path("public-demo/style.css").read_text()
    assert "@import" not in css and "url(http" not in css
