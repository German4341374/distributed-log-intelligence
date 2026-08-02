# Architecture and streaming model

## Design goals

The tool prioritizes predictable local resource use, explainable results, safe output, and
automation-friendly behavior. It does not depend on an external database, log platform, or
network service.

## Processing pipeline

1. Format detection uses the logical extension (after removing `.gz`) or at most five non-empty
   sample lines.
2. A format-specific iterator reads one record at a time.
3. Field aliases are mapped into a typed `LogEvent` and Pydantic validates the result.
4. Timestamps are interpreted in the configured timezone when naive and normalized to UTC.
5. The analyzer updates counters, bounded cardinality maps, and time-window aggregates.
6. Only capped malformed samples and masked error examples are retained.
7. The final typed report is rendered to the selected output format.

## Memory model

For `N` input records, `G` retained error fingerprints, `S` services, `C` tracked correlation
IDs, and `W` observed time windows, analysis time is `O(N)` and memory is
`O(G + S + C + W)`. Default hard limits are 10,000 error groups, 10,000 services, 1,000
correlation IDs, and 100,000 windows. These limits protect the process from unbounded
high-cardinality input. Reports expose dropped group and window counts so truncation is visible.

The current correlation counter keeps the first IDs encountered until its cap. It is suitable
for diagnostics but is not an exact global top-K algorithm after the limit is reached.

`trace` has a different model. Matching events are streamed into a temporary SQLite database,
ordered by timestamp, and read back with a configurable result cap. Its RAM use is bounded by the
insert batch and returned event limit; disk use is `O(M)` for `M` matching records. The database
is removed in a `finally` block.

## Streaming strategy

- Plain and JSONL inputs are processed line by line.
- CSV uses `csv.DictReader`, which is also an iterator.
- gzip uses `gzip.open` in text mode and decompresses incrementally.
- Multiple files are processed sequentially, while global aggregates span all files.
- Redaction writes each masked line immediately to a different destination.
- Reports are assembled only after aggregation. The window list and selected error groups are the
  bounded aggregate, not a copy of the raw records.

## Message normalization

Grouping applies ordered, deterministic replacements:

1. Mask bearer tokens, API keys, secrets, emails, IPv4 addresses, and phone numbers.
2. Lowercase the message.
3. Replace UUIDs with `<uuid>`.
4. Replace ISO-like timestamps with `<timestamp>`.
5. Replace long hexadecimal values with `<hex>`.
6. Replace keyed numeric identifiers such as `request_id=123` with `request_id=<id>`.
7. Replace remaining standalone integers and decimals with `<number>`.
8. Collapse whitespace and hash the normalized value with SHA-256, retaining 16 hex characters.

This makes grouping explainable and stable. It is deliberately not machine learning: it cannot
understand whether a number is semantically important, and unrelated messages can normalize to
the same text.

## Anomaly model

The analyzer counts errors in observed UTC windows. A burst is a window whose count reaches the
configured absolute threshold. An anomaly is a window at or above the configured population
z-score, calculated from all observed windows, with at least six windows required.

Limitations:

- Empty windows are not synthesized.
- Mean and standard deviation are sensitive to multiple large bursts.
- Seasonality, deployments, traffic volume, and day-of-week effects are not modeled.
- A statistically unusual count can be operationally harmless, and a serious single error may
  not be statistically unusual.
- Comparing periods compares aggregate reports, not paired observations.

The output should guide investigation, never automate remediation by itself.

