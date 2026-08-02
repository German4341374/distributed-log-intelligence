# Benchmark results

These measurements were produced by the repository benchmark on revision `4ecee70`. The input
generator and analyzer ran locally; no numbers are estimated or copied from another environment.

```bash
uv run python benchmarks/run_benchmark.py --sizes 10000 50000 200000 --repeats 3
```

Environment:

- Python: `3.14.4`
- Platform: `Windows-10-10.0.19045-SP0`
- Processor: `Intel64 Family 6 Model 151 Stepping 5, GenuineIntel`
- Revision: `4ecee70`

| Lines | File MiB | Repeats | Median seconds | Median lines/s | Max peak Python MiB |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 1.375 | 3 | 0.4346 | 23,008.6 | 0.314 |
| 50,000 | 6.874 | 3 | 2.1086 | 23,712.6 | 0.451 |
| 200,000 | 27.504 | 3 | 8.3790 | 23,869.3 | 1.503 |

`Median seconds` is wall-clock analysis time. `Max peak Python MiB` is the largest peak reported
by `tracemalloc` across the repeats; it measures Python-managed allocations, not total process
RSS, interpreter memory, filesystem cache, or temporary disk usage. The benchmark includes
timestamp parsing, Pydantic validation, masking, grouping, and report-model construction. File
generation is excluded from the timed section.

These results demonstrate near-linear processing for this deterministic data set. They are not a
service-level objective: hardware, filesystem, compression, record size, distinct-cardinality
limits, and message complexity materially affect throughput and memory.
