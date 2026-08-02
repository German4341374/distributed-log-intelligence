# Confidential log safety

## Privacy model

The program has no HTTP client, analytics SDK, telemetry, or upload integration. All parsing,
temporary indexing, aggregation, and report generation happen on the local machine.

The masker covers emails, IPv4 addresses, phone-like numbers, bearer tokens, and common API key,
access token, and secret assignments. It is applied to:

- error examples;
- trace messages;
- malformed-line previews;
- every raw line processed by `redact`.

## Operational guidance

- Treat raw logs and generated reports as confidential even after masking.
- Work on an encrypted disk and use a restricted temporary directory.
- Mount logs read-only in Docker and consider `--network none`.
- Do not paste production reports into public issues.
- Delete temporary reports according to the incident retention policy.
- Review masking results against organization-specific identifiers before sharing.

## Residual risk

Regex masking cannot identify all personal or secret data. Free-form names, addresses, proprietary
IDs, stack variables, encoded secrets, IPv6 addresses, and novel credential formats may remain.
Service names, error structure, timing, volumes, and filenames can also be sensitive metadata.

For regulated data, use an approved DLP process and manual review in addition to this tool.

