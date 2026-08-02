"""Deterministic streaming benchmark; results are printed, never edited into docs automatically."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path

from distributed_log_intelligence.analyzer import analyze_files
from distributed_log_intelligence.operations import generate_demo


@dataclass(frozen=True, slots=True)
class Measurement:
    lines: int
    size_mib: float
    repeats: int
    median_seconds: float
    median_lines_per_second: float
    max_peak_python_mib: float


def measure(size: int, repeats: int, directory: Path) -> Measurement:
    path = generate_demo(directory / f"benchmark-{size}.jsonl", lines=size, seed=42)
    elapsed: list[float] = []
    peaks: list[int] = []
    for _ in range(repeats):
        tracemalloc.start()
        started = time.perf_counter()
        report = analyze_files([path])
        elapsed.append(time.perf_counter() - started)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if report.parsed_lines != size:
            raise RuntimeError(f"expected {size} records, parsed {report.parsed_lines}")
        peaks.append(peak)
    median_seconds = statistics.median(elapsed)
    return Measurement(
        lines=size,
        size_mib=round(path.stat().st_size / (1024 * 1024), 3),
        repeats=repeats,
        median_seconds=round(median_seconds, 4),
        median_lines_per_second=round(size / median_seconds, 1),
        max_peak_python_mib=round(max(peaks) / (1024 * 1024), 3),
    )


def run(sizes: list[int], repeats: int) -> dict[str, object]:
    if not sizes or any(size < 1 for size in sizes):
        raise ValueError("all sizes must be positive")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    with tempfile.TemporaryDirectory(prefix="dli-benchmark-") as directory:
        results = [measure(size, repeats, Path(directory)) for size in sizes]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "not reported",
        "revision": _revision(),
        "measurements": [asdict(item) for item in results],
    }


def render_markdown(results: dict[str, object]) -> str:
    lines = [
        f"Python: `{results['python']}`",
        f"Platform: `{results['platform']}`",
        f"Processor: `{results['processor']}`",
        f"Revision: `{results['revision']}`",
        "",
        "| Lines | File MiB | Repeats | Median seconds | Median lines/s | Max peak Python MiB |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    measurements = results["measurements"]
    if not isinstance(measurements, list):
        raise TypeError("measurements must be a list")
    for measurement in measurements:
        if not isinstance(measurement, dict):
            raise TypeError("measurement must be a mapping")
        lines.append(
            "| {lines} | {size_mib} | {repeats} | {median_seconds} | "
            "{median_lines_per_second} | {max_peak_python_mib} |".format(**measurement)
        )
    return "\n".join(lines)


def _revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unavailable"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[10_000, 50_000, 200_000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args()
    results = run(arguments.sizes, arguments.repeats)
    if arguments.as_json:
        print(json.dumps(results, indent=2))
    else:
        print(render_markdown(results))


if __name__ == "__main__":
    main()
