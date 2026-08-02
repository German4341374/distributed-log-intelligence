## Summary

Describe the operational problem and the focused change.

## Validation

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy src benchmarks`
- [ ] `uv run pytest`
- [ ] `uv build`
- [ ] Streaming and masking behavior remain covered by tests
- [ ] No production logs, credentials, personal data, or unmeasured benchmark claims are included

## Risk and rollback

Describe parser compatibility, memory, privacy, and output-format risks plus the rollback path.

