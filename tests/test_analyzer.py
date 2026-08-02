from __future__ import annotations

import json
from pathlib import Path

from distributed_log_intelligence.analyzer import analyze_files, compare_reports
from distributed_log_intelligence.models import AnalyzeOptions


def test_analyze_multiple_formats(plain_log: Path, jsonl_log: Path, csv_log: Path) -> None:
    report = analyze_files([plain_log, jsonl_log, csv_log])
    assert report.total_lines == 8
    assert report.parsed_lines == 7
    assert report.malformed_lines == 1
    assert report.error_count == 3
    assert set(report.formats) == {str(plain_log), str(jsonl_log), str(csv_log)}


def test_similar_errors_are_grouped(plain_log: Path, jsonl_log: Path) -> None:
    report = analyze_files([plain_log, jsonl_log])
    timeout = next(
        item for item in report.top_errors if "database timeout" in item.normalized_message
    )
    assert timeout.count == 2
    assert timeout.normalized_message.endswith("id=<id>")


def test_report_examples_are_masked(tmp_path: Path) -> None:
    path = tmp_path / "sensitive.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-15T08:00:00Z",
                "level": "ERROR",
                "service": "api",
                "message": "failed for demo.user@example.test from 192.0.2.1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    example = analyze_files([path]).top_errors[0].examples[0]
    assert "example.test" not in example
    assert "192.0.2.1" not in example


def test_burst_detection(tmp_path: Path) -> None:
    path = _window_log(tmp_path, [1, 2, 10, 1, 1, 1, 1])
    report = analyze_files([path], AnalyzeOptions(burst_threshold=8, anomaly_zscore=1.5))
    assert [item.errors for item in report.bursts] == [10]
    assert report.anomalies[0].errors == 10


def test_anomaly_requires_six_windows(tmp_path: Path) -> None:
    path = _window_log(tmp_path, [1, 1, 20, 1, 1])
    report = analyze_files([path], AnalyzeOptions(anomaly_zscore=1.0))
    assert report.anomalies == []


def test_group_cap_is_visible(tmp_path: Path) -> None:
    path = tmp_path / "many.jsonl"
    records = [
        {
            "timestamp": f"2026-01-15T08:00:{index:02d}Z",
            "level": "ERROR",
            "service": "api",
            "message": f"unique word{chr(65 + index)}",
        }
        for index in range(5)
    ]
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    options = AnalyzeOptions(max_error_groups=100)
    options.max_error_groups = 2
    report = analyze_files([path], options)
    assert len(report.top_errors) == 2
    assert report.dropped_error_groups == 3


def test_compare_reports_finds_deltas(plain_log: Path, jsonl_log: Path) -> None:
    baseline = analyze_files([plain_log])
    current = analyze_files([jsonl_log])
    comparison = compare_reports(baseline, current)
    assert comparison.total_delta == -1
    assert comparison.error_delta == 0
    assert comparison.baseline.total == 3


def test_empty_file_has_zero_rate(tmp_path: Path) -> None:
    path = tmp_path / "empty.log"
    path.write_text("", encoding="utf-8")
    report = analyze_files([path])
    assert report.error_rate == 0.0
    assert report.first_timestamp is None


def _window_log(tmp_path: Path, error_counts: list[int]) -> Path:
    path = tmp_path / "windows.jsonl"
    rows = []
    for minute, count in enumerate(error_counts):
        for second in range(count):
            rows.append(
                json.dumps(
                    {
                        "timestamp": f"2026-01-15T08:{minute * 5:02d}:{second:02d}Z",
                        "level": "ERROR",
                        "service": "api",
                        "message": "failure",
                    }
                )
            )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path
