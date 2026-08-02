# Repository guidance

- Keep source code, tests, documentation, and commit messages in English.
- Preserve streaming behavior; do not introduce whole-file reads in parsing or redaction paths.
- Use Pydantic models at module boundaries and avoid global mutable state.
- Mask examples before storing them in reports.
- Add regression tests for parsing, timezone, masking, and exit-code changes.
- Run Ruff formatting and linting, mypy, Pytest, package build, and CLI smoke tests before push.
- Publish benchmark numbers only when measured from the same committed implementation and record
  the command, environment, revision, and repeat count.
- Never commit real logs, tokens, credentials, personal data, or generated reports containing
  sensitive input.

