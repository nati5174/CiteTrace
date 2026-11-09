"""Authenticate a source pin from retained upstream evidence or vetted local Git metadata."""

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from citeprobe.evidence_io import verify_batch
from citeprobe.evidence_models import RawEvidence
from citeprobe.lookup_inputs import fingerprint
from citeprobe.pilot_models import ACLRevision

COMMIT_URL = "https://api.github.com/repos/acl-org/acl-anthology/commits?per_page=1"
COLLECTIONS = (
    ("P18", "1"),
    ("P19", "1"),
    ("2020.acl", "main"),
    ("2021.acl", "main"),
    ("2022.acl", "main"),
    ("2023.acl", "main"),
)


def git(checkout: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, check=False
    )
    if process.returncode:
        raise ValueError("Local ACL Git metadata check failed; no fetch/clone attempted")
    return process.stdout.strip()


def local_proof(checkout: Path, commit: str | None = None) -> tuple[str, str]:
    remote = git(checkout, "remote", "get-url", "origin").removesuffix(".git")
    if remote not in {
        "https://github.com/acl-org/acl-anthology",
        "git@github.com:acl-org/acl-anthology",
    }:
        raise ValueError("Checkout is not configured for the official ACL repository")
    resolved = git(checkout, "rev-parse", "--verify", commit or "HEAD")
    if (
        not re.fullmatch("[0-9a-f]{40}", resolved)
        or git(checkout, "cat-file", "-t", resolved) != "commit"
    ):
        raise ValueError("Not an actual local Git commit")
    tree = git(
        checkout, "ls-tree", resolved, "--", *(f"data/xml/{name}.xml" for name, _ in COLLECTIONS)
    )
    if len(tree.splitlines()) != 6:
        raise ValueError("Approved ACL collection scope is absent at this revision")
    return resolved, fingerprint({"commit": resolved, "tree": tree, "official_remote": True})


def upstream_proof(directory: Path) -> tuple[str, str, str]:
    results = verify_batch(directory)
    if len(results) != 1:
        raise ValueError("Commit resolution requires one exact upstream request")
    record = RawEvidence.model_validate_json((directory / "request-001/record.json").read_bytes())
    if record.request.url != COMMIT_URL or record.http_status != 200 or not record.body_complete:
        raise ValueError("Commit lacks successful official upstream response evidence")
    from citeprobe.evidence_extract import decoded_body

    payload = json.loads(decoded_body(record, (directory / "request-001/body.bin").read_bytes()))
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("Unexpected official commit inventory")
    commit = payload[0].get("sha")
    if not isinstance(commit, str) or not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("No valid immutable upstream commit")
    return commit, record.record_id, record.origin


def pin_revision(location: Path, curator: str, *, local: bool = False) -> ACLRevision:
    if local:
        commit, proof = local_proof(location)
        origin = "observed"
    else:
        commit, proof, origin = upstream_proof(location)
    pin = ACLRevision.model_validate(
        {
            "commit": commit,
            "origin": origin,
            "curator_id": curator,
            "reviewed_at": datetime.now(UTC),
            "proof_kind": "local_git" if local else "upstream_http",
            "proof_location": str(location.resolve()),
            "proof_fingerprint": proof,
            "revision_fingerprint": "0" * 64,
        }
    )
    return pin.model_copy(
        update={
            "revision_fingerprint": fingerprint(
                pin.model_dump(mode="json", exclude={"revision_fingerprint"})
            )
        }
    )


def verify_revision(pin: ACLRevision) -> None:
    if pin.revision_fingerprint != fingerprint(
        pin.model_dump(mode="json", exclude={"revision_fingerprint"})
    ):
        raise ValueError("ACL revision fingerprint mismatch")
    location = Path(pin.proof_location)
    if pin.proof_kind == "local_git":
        commit, proof = local_proof(location, pin.commit)
        origin = "observed"
    else:
        commit, proof, origin = upstream_proof(location)
    if (commit, proof, origin) != (pin.commit, pin.proof_fingerprint, pin.origin):
        raise ValueError("ACL revision/provenance cannot be reproduced")
