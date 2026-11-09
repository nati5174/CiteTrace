"""Locally compare a privately entered key against evidence without printing it."""

import getpass
import gzip
import re
import sys
import warnings
from pathlib import Path
from urllib.parse import quote, quote_plus

ROOT = Path("artifacts/empirical-pilot-immediate-001")
DIRECTORIES = (
    ROOT / "a-benchmark-smoke-001",
    ROOT / "a-benchmark-smoke-002",
    ROOT / "a-benchmark-remaining-001",
    ROOT / "a-benchmark-key-continuation-001",
    ROOT / "a-empirical-evaluation-001",
    Path("public-demo"),
)


def scan(key: str) -> tuple[int, list[str]]:
    if not key or not key.isascii() or not re.fullmatch(r"[\x21-\x7e]+", key):
        raise ValueError("The API key is empty or contains spaces or non-ASCII characters")
    if key.casefold() in {"your-key-here", "your_api_key", "your-key", "placeholder"}:
        raise ValueError("Replace the placeholder in .env with your actual API key")
    variants = {key.encode(), quote(key, safe="").encode(), quote_plus(key, safe="").encode()}
    matches = []
    count = 0
    for directory in DIRECTORIES:
        if not directory.is_dir():
            raise ValueError(f"Required evidence directory missing: {directory}")
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            contents = [raw]
            if raw.startswith(b"\x1f\x8b"):
                contents.append(gzip.decompress(raw))
            count += 1
            if any(secret in content for secret in variants for content in contents):
                matches.append(str(path))
    return count, matches


def read_env_key(path: Path) -> str:
    """Read only the named setting; never execute environment-file content."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    values = [
        line.partition("=")[2].strip() for line in lines if line.startswith("OPENALEX_API_KEY=")
    ]
    if len(values) != 1:
        raise ValueError(".env must contain exactly one OPENALEX_API_KEY= line")
    value = values[0]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


if __name__ == "__main__":
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        env_file = Path(".env")
        secret = (
            read_env_key(env_file)
            if env_file.is_file()
            else getpass.getpass("OpenAlex API key (input hidden; never printed): ")
        )
        count, matches = scan(secret)
        matches = [path.replace(secret, "[REDACTED]") for path in matches]
    except (OSError, ValueError, getpass.GetPassWarning) as error:
        print(f"Audit failed: {error}")
        sys.exit(2)
    del secret
    print(f"Scanned {count} files; exact or URL-encoded key matches: {len(matches)}")
    for path in matches:
        print(f"Sensitive file: {path}")
    if matches:
        print("Do not share matching files. Review and rotate the key as appropriate.")
        sys.exit(1)
    print("No key match found. This does not replace a privacy or complete secret review.")
