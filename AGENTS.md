# CiteProbe — Engineering Instructions

CiteProbe is a reproducible Python benchmark for evaluating academic citation retrieval coverage and robustness to metadata mutations.

## Engineering Principles

- Prioritize correctness, reproducibility, simplicity, and maintainability over feature count.
- Use Python 3.12+, type hints, Pydantic, pytest, and Ruff.
- Keep modules small and responsibilities clearly separated.
- Avoid unnecessary databases, web frontends, authentication, and microservices.
- Do not add dependencies unless justified.

## Testing Requirements

- Write automated tests for each implemented component.
- Mock external HTTP services in automated tests.
- Test successful responses, empty results, malformed data, timeouts, HTTP errors, and rate limits.
- Add regression tests for every bug fixed.
- Run tests and lint checks after each meaningful change.
- Do not claim tests passed unless they were actually executed.

## API Reliability

- Reuse asynchronous HTTP sessions.
- Use bounded concurrency, provider-aware rate limits, timeouts, and limited retries with exponential backoff and jitter.
- Respect Retry-After headers when provided.
- Never classify network failures as missing citations.
- Preserve provider responses and lookup metadata for reproducibility.

## Data Integrity

- Validate datasets and experiment configurations with explicit schemas.
- Preserve canonical ground-truth identifiers.
- Ensure mutations never overwrite original citation records.
- Use deterministic random seeds where randomness is involved.
- Record timestamps, provider identifiers, dataset versions, and experiment configuration.

## Evaluation Integrity

- Distinguish retrieval success from string similarity.
- Match retrieved candidates against verified canonical identities.
- Treat unresolved, unavailable, and incorrect matches as different outcomes.
- Never invent benchmark results, ground-truth labels, or experimental observations.
- Account for repeated mutations derived from the same source citation.
- Document limitations and uncertainty in reports.

## Development Workflow

For each task:

1. Inspect the relevant existing code and tests.
2. Describe the smallest implementation needed.
3. Implement the change without unrelated refactoring.
4. Add or update automated tests.
5. Run relevant tests, linting, and type checks.
6. Report changed files, commands executed, results, and remaining limitations.

Do not silently skip failing tests, suppress errors, or introduce placeholder results presented as real findings.