# Malformed input and validation

Malformed data is expected in real incident work. Analysis therefore continues by default and
reports both the malformed count and a bounded set of masked samples.

A record is malformed when any of these conditions applies:

- it is empty;
- JSONL is not valid JSON or the value is not an object;
- CSV has no usable header;
- a required timestamp, level, or message is missing;
- the timestamp cannot be recognized or normalized;
- the level cannot be mapped to a supported level;
- a plain line does not start with the expected timestamp and level shape.

`analyze --fail-on-malformed` returns exit code 1 after producing the report. `validate` always
returns exit code 1 when any invalid record is found. Input, timezone, and filesystem errors use
exit code 2.

UTF-8 decoding uses replacement characters rather than terminating an entire multi-gigabyte run.
This keeps processing available during incidents, but means validation does not prove that the
original byte stream was valid UTF-8.

The issue preview is truncated to 240 characters and passed through the PII masker. The original
file and line number remain in the result for local investigation.

