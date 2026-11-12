"""Build a static V3 route with frozen outputs and no private recomputation inputs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "previews/failure-replay-003"
PUBLIC = ROOT / "public-demo"
OUTPUT = PUBLIC / "replay"
TOKENS = ROOT / "previews/design-system-003/tokens.css"
ASSETS = (
    "index.html",
    "camera.js",
    "data.json",
    "evidence-layout.js",
    "evidence-map.css",
    "evidence-map.js",
    "inspector.js",
    "investigation.css",
    "polish.css",
    "replay.css",
    "replay.js",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize(value: Any, available: set[str]) -> Any:
    if isinstance(value, list):
        return [sanitize(item, available) for item in value]
    if isinstance(value, dict):
        result = {key: sanitize(item, available) for key, item in value.items()
                  if key != "artifact_path"}
        evidence_id = value.get("evidence_id")
        if isinstance(evidence_id, str):
            result["artifact_available"] = evidence_id in available
        return result
    return value


def main() -> None:
    data = read_json(REPLAY / "data.json")
    # This release is static. Preserve recorded evidence and outputs, but never
    # advertise artifacts or counterfactuals that require the private input bundle.
    available: set[str] = set()
    data["release_capabilities"] = {
        "counterfactual_recomputation": False,
        "archived_artifacts": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        source = REPLAY / name
        if name == "data.json":
            (OUTPUT / name).write_text(
                json.dumps(sanitize(data, available), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            shutil.copyfile(source, OUTPUT / name)
    shutil.copyfile(TOKENS, OUTPUT / "tokens.css")
    replay_assets = sorted(f"replay/{path.name}" for path in OUTPUT.iterdir() if path.is_file())
    print(json.dumps({"replay_assets": replay_assets, "cases": len(recorded_ids_from(data)),
                      "counterfactual_recomputation": False, "archived_artifacts": False}))


def recorded_ids_from(data: dict[str, Any]) -> set[str]:
    return {candidate["case_id"] for scenario in data["scenarios"]
            for candidate in scenario["candidates"]}


if __name__ == "__main__":
    main()
