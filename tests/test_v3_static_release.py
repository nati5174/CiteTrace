"""Clean-checkout build checks for the static V3 release package."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import build_v3_release as release


def test_clean_static_build_preserves_recorded_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean_root = tmp_path / "clean"
    replay_source = clean_root / "previews/failure-replay-003"
    replay_source.mkdir(parents=True)
    for name in release.ASSETS:
        shutil.copyfile(release.REPLAY / name, replay_source / name)
    tokens = clean_root / "previews/design-system-003/tokens.css"
    tokens.parent.mkdir(parents=True)
    shutil.copyfile(release.TOKENS, tokens)
    assert not (clean_root / "api/_v3_cases.json").exists()
    assert not (clean_root / "api/_v3_artifacts.json").exists()

    output = clean_root / "public-demo/replay"
    monkeypatch.setattr(release, "REPLAY", replay_source)
    monkeypatch.setattr(release, "TOKENS", tokens)
    monkeypatch.setattr(release, "OUTPUT", output)
    release.main()

    recorded = release.read_json(replay_source / "data.json")
    public = release.read_json(output / "data.json")
    assert public["release_capabilities"] == {
        "counterfactual_recomputation": False,
        "archived_artifacts": False,
    }
    assert len(public["scenarios"]) == len(recorded["scenarios"])
    for expected, actual in zip(recorded["scenarios"], public["scenarios"], strict=True):
        assert len(expected["candidates"]) == len(actual["candidates"])
        for source_candidate, public_candidate in zip(
            expected["candidates"], actual["candidates"], strict=True
        ):
            assert source_candidate["case_id"] == public_candidate["case_id"]
            assert source_candidate["rank"] == public_candidate["rank"]
            assert source_candidate["outputs"] == public_candidate["outputs"]
            assert release.sanitize(source_candidate["graphs"], set()) == (
                public_candidate["graphs"]
            )
            assert release.sanitize(source_candidate["evidence"], set()) == (
                public_candidate["evidence"]
            )
            assert all(not evidence.get("artifact_available", False)
                       for evidence in public_candidate["evidence"])

    assets = {path.name for path in output.iterdir()}
    assert assets == {*release.ASSETS, "tokens.css"}
    assert "artifact_path" not in json.dumps(public)
    assert "studies/" not in json.dumps(public)
    assert "does not rerun the verifier or simulate counterfactual results" in (
        (output / "inspector.js").read_text(encoding="utf-8")
    )
    assert "/methodology.html" in (output / "index.html").read_text(encoding="utf-8")
