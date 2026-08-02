from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from distributed_log_intelligence.analyzer import analyze_files, compare_reports
from distributed_log_intelligence.operations import trace_correlation, validate_files
from distributed_log_intelligence.reports import (
    export_report,
    infer_report_format,
    render_html,
    render_junit,
    render_markdown,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("report.json", "json"),
        ("report.md", "markdown"),
        ("report.html", "html"),
        ("report.xml", "junit"),
    ],
)
def test_infer_report_format(name: str, expected: str) -> None:
    assert infer_report_format(Path(name)) == expected


def test_infer_report_format_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="cannot infer"):
        infer_report_format(Path("report.txt"))


def test_export_json_is_typed_report(plain_log: Path, tmp_path: Path) -> None:
    report = analyze_files([plain_log])
    output = tmp_path / "report.json"
    export_report(report, output)
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["parsed_lines"] == 3


def test_markdown_escapes_table_separator(plain_log: Path) -> None:
    report = analyze_files([plain_log])
    report.top_errors[0].normalized_message = "left | right"
    assert "left \\| right" in render_markdown(report)


def test_html_escapes_payload(plain_log: Path) -> None:
    report = analyze_files([plain_log])
    report.files = ["<script>alert(1)</script>"]
    content = render_html(report)
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_junit_marks_malformed_analysis_as_failure(plain_log: Path) -> None:
    root = ET.fromstring(render_junit(analyze_files([plain_log])))
    assert root.attrib["failures"] == "1"
    assert root.find("testcase/failure") is not None


def test_comparison_markdown(plain_log: Path, jsonl_log: Path) -> None:
    comparison = compare_reports(analyze_files([plain_log]), analyze_files([jsonl_log]))
    assert "Log Period Comparison" in render_markdown(comparison)


def test_trace_markdown(plain_log: Path) -> None:
    trace = trace_correlation([plain_log], "req-1")
    content = render_markdown(trace)
    assert "gateway → orders → payments" in content


def test_validation_junit_has_file_case(plain_log: Path) -> None:
    root = ET.fromstring(render_junit(validate_files([plain_log])))
    assert root.attrib["tests"] == "1"


def test_explicit_report_format_overrides_suffix(plain_log: Path, tmp_path: Path) -> None:
    output = tmp_path / "report.data"
    export_report(analyze_files([plain_log]), output, "markdown")
    assert output.read_text(encoding="utf-8").startswith("# Distributed")


def test_export_rejects_unknown_format(plain_log: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        export_report(analyze_files([plain_log]), tmp_path / "report.data", "pdf")
