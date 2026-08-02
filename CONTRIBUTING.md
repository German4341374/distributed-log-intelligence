# Contributing

## Workflow

1. Open an issue describing the behavior and operational use case.
2. Create a focused branch from `main`.
3. Run `make setup`, `make lint`, and `make test`.
4. Add tests for parser, privacy, output, or memory-model changes.
5. Open a pull request using the repository template.

Use [Conventional Commits](https://www.conventionalcommits.org/), for example:

```text
feat(parser): support a vendor timestamp alias
fix(masking): preserve separators around redacted tokens
docs(benchmark): record measurements for release 0.2.0
```

Do not submit production logs, personal data, credentials, or benchmark claims that were not
measured from the committed implementation.

