"""Commit remaining source work in phase order; keep private artifacts local."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def phase(path: str) -> int | None:
    if path.startswith(("artifacts/", "public-demo/data.json")) or path.endswith(".zip"):
        return None
    if path in {"README.md", "src/citeprobe/cli.py"}:
        return 7
    if path.startswith("docs/") and path != "docs/public-demo.md":
        return 5
    if path.startswith("public-demo/") or path in {
        "scripts/audit_demo_key.py", "scripts/export_public_demo.py",
        "scripts/commit_remaining_phases.py", "tests/test_public_demo.py", "docs/public-demo.md",
    }:
        return 6
    if not path.startswith(("src/", "tests/", "scripts/")):
        return None
    name = Path(path).name
    if "benchmark" in name:
        return 4
    if any(s in path for s in ("pilot", "acl_", "resource", "source_limits", "saved_acl", "scoped_acl", "run_milestone")):
        return 3
    if any(s in path for s in ("evidence", "source_feasibility", "identity_verification")):
        return 2
    if "acquisition" in path:
        return 1
    if "research" in path:
        return 0
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    if git("diff", "--cached", "--name-only"):
        raise SystemExit("Index already contains staged changes; review them first.")
    titles = [
        "feat: add research dataset manifests and validation",
        "feat: add offline scholarly acquisition and provenance",
        "feat: retain and verify raw source evidence",
        "feat: add bounded pilot acquisition and curator selection",
        "feat: add audited benchmark capture and key continuation",
        "docs: record versioned research protocols and milestone decisions",
        "feat: add local CiteProbe demo and private secret audit",
        "feat: integrate research and pilot commands with CiteProbe CLI",
    ]
    paths = set(git("ls-files", "--others", "--exclude-standard").splitlines())
    paths.update(git("diff", "--name-only").splitlines())
    for number, title in enumerate(titles):
        selected = sorted(p for p in paths if phase(p) == number)
        if not selected:
            continue
        git("add", "--", *selected)
        print(git("commit", "-m", title))
    if args.push:
        branch = git("branch", "--show-current")
        if not branch:
            raise SystemExit("Detached HEAD: commits created; choose a branch before pushing.")
        print(git("push", "-u", "origin", branch))
    print("Private artifacts and draft public data remain local. No history was rewritten.")


if __name__ == "__main__":
    main()
