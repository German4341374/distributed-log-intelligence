"""Console, JSON, Markdown, HTML, and JUnit XML report rendering."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.text import Text

from distributed_log_intelligence.models import (
    AnalysisReport,
    ComparisonReport,
    TraceReport,
    ValidationReport,
)

REPORT_FORMATS = {"json", "markdown", "html", "junit"}


def export_report(report: BaseModel, destination: Path, report_format: str | None = None) -> None:
    selected = report_format or infer_report_format(destination)
    if selected not in REPORT_FORMATS:
        raise ValueError(f"unsupported report format: {selected}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if selected == "json":
        content = report.model_dump_json(indent=2)
    elif selected == "markdown":
        content = render_markdown(report)
    elif selected == "html":
        content = render_html(report)
    else:
        content = render_junit(report)
    destination.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")


def infer_report_format(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".json": "json",
        ".md": "markdown",
        ".markdown": "markdown",
        ".html": "html",
        ".htm": "html",
        ".xml": "junit",
    }
    try:
        return mapping[suffix]
    except KeyError as exc:
        raise ValueError(f"cannot infer report format from extension: {path}") from exc


def render_console(report: BaseModel, console: Console | None = None) -> None:
    target = console or Console()
    if isinstance(report, AnalysisReport):
        _analysis_console(report, target)
    elif isinstance(report, ComparisonReport):
        _comparison_console(report, target)
    elif isinstance(report, TraceReport):
        _trace_console(report, target)
    elif isinstance(report, ValidationReport):
        _validation_console(report, target)
    else:
        target.print_json(report.model_dump_json())


def render_markdown(report: BaseModel) -> str:
    if isinstance(report, AnalysisReport):
        return _analysis_markdown(report)
    if isinstance(report, ComparisonReport):
        return _comparison_markdown(report)
    if isinstance(report, TraceReport):
        return _trace_markdown(report)
    if isinstance(report, ValidationReport):
        return _validation_markdown(report)
    return f"# Report\n\n```json\n{report.model_dump_json(indent=2)}\n```"


def render_html(report: BaseModel) -> str:
    title = _report_title(report)
    payload = html.escape(report.model_dump_json(indent=2))
    summary = html.escape(render_markdown(report))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 1100px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
    h1 {{ border-bottom: 3px solid #4f46e5; padding-bottom: .5rem; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; padding: 1rem; border-radius: .5rem;
           background: color-mix(in srgb, CanvasText 8%, Canvas); }}
    details {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <pre>{summary}</pre>
  <details><summary>Structured JSON</summary><pre>{payload}</pre></details>
</body>
</html>"""


def render_junit(report: BaseModel) -> str:
    suite = ET.Element("testsuite", name="distributed-log-intelligence")
    failures = 0
    tests = 0

    def add_case(name: str, failure: str | None = None) -> None:
        nonlocal failures, tests
        tests += 1
        case = ET.SubElement(suite, "testcase", name=name, classname="log-intelligence")
        if failure:
            failures += 1
            node = ET.SubElement(case, "failure", message=failure)
            node.text = failure

    if isinstance(report, AnalysisReport):
        add_case(
            "parse-quality",
            f"{report.malformed_lines} malformed lines" if report.malformed_lines else None,
        )
        add_case(
            "statistical-anomalies",
            f"{len(report.anomalies)} anomalous windows" if report.anomalies else None,
        )
    elif isinstance(report, ValidationReport):
        for item in report.files:
            add_case(
                f"validate:{item.path}",
                f"{item.invalid_lines} invalid lines" if item.invalid_lines else None,
            )
    elif isinstance(report, ComparisonReport):
        add_case(
            "error-regression",
            f"error count increased by {report.error_delta}" if report.error_delta > 0 else None,
        )
    elif isinstance(report, TraceReport):
        add_case(
            f"trace:{report.correlation_id}",
            None if report.matched_events else "correlation ID was not found",
        )
    else:
        add_case("report-generated")

    suite.set("tests", str(tests))
    suite.set("failures", str(failures))
    suite.set("errors", "0")
    suite.set("time", "0")
    ET.indent(suite)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)


def _analysis_console(report: AnalysisReport, console: Console) -> None:
    table = Table(title="Distributed Log Analysis")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    metrics = (
        ("Files", len(report.files)),
        ("Parsed lines", report.parsed_lines),
        ("Malformed lines", report.malformed_lines),
        ("Errors", report.error_count),
        ("Error rate", f"{report.error_rate:.2%}"),
        ("Bursts", len(report.bursts)),
        ("Anomalies", len(report.anomalies)),
    )
    for name, value in metrics:
        table.add_row(name, str(value))
    console.print(table)
    if report.top_errors:
        errors = Table(title="Top error groups")
        errors.add_column("Fingerprint")
        errors.add_column("Count", justify="right")
        errors.add_column("Normalized message")
        for item in report.top_errors:
            errors.add_row(item.fingerprint, str(item.count), Text(item.normalized_message))
        console.print(errors)


def _comparison_console(report: ComparisonReport, console: Console) -> None:
    table = Table(title="Period Comparison")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Delta", justify="right")
    table.add_row(
        "Parsed lines",
        str(report.baseline.total),
        str(report.current.total),
        f"{report.total_delta:+d}",
    )
    table.add_row(
        "Errors",
        str(report.baseline.errors),
        str(report.current.errors),
        f"{report.error_delta:+d}",
    )
    table.add_row(
        "Error rate",
        f"{report.baseline.error_rate:.2%}",
        f"{report.current.error_rate:.2%}",
        f"{report.error_rate_delta:+.2%}",
    )
    console.print(table)


def _trace_console(report: TraceReport, console: Console) -> None:
    heading = Text("Correlation: ", style="bold")
    heading.append(report.correlation_id)
    heading.append("  Events: ", style="bold")
    heading.append(f"{report.returned_events}/{report.matched_events}")
    console.print(heading)
    chain = Text("Service chain: ", style="bold")
    chain.append(" -> ".join(report.service_chain) or "(empty)")
    console.print(chain)
    table = Table()
    table.add_column("Timestamp")
    table.add_column("Service")
    table.add_column("Level")
    table.add_column("Message")
    for event in report.events:
        table.add_row(
            event.timestamp.isoformat(), Text(event.service), event.level.value, Text(event.message)
        )
    console.print(table)


def _validation_console(report: ValidationReport, console: Console) -> None:
    table = Table(title="Log Validation")
    table.add_column("File")
    table.add_column("Format")
    table.add_column("Valid", justify="right")
    table.add_column("Invalid", justify="right")
    for item in report.files:
        table.add_row(
            Text(item.path),
            item.detected_format.value if item.detected_format else "unknown",
            str(item.valid_lines),
            str(item.invalid_lines),
        )
    console.print(table)


def _analysis_markdown(report: AnalysisReport) -> str:
    lines = [
        "# Distributed Log Analysis",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Files | {len(report.files)} |",
        f"| Parsed lines | {report.parsed_lines} |",
        f"| Malformed lines | {report.malformed_lines} |",
        f"| Errors | {report.error_count} |",
        f"| Error rate | {report.error_rate:.2%} |",
        f"| Error bursts | {len(report.bursts)} |",
        f"| Statistical anomalies | {len(report.anomalies)} |",
        "",
        "## Top error groups",
        "",
        "| Fingerprint | Count | Normalized message |",
        "|---|---:|---|",
    ]
    lines.extend(
        f"| `{item.fingerprint}` | {item.count} | {_md(item.normalized_message)} |"
        for item in report.top_errors
    )
    if not report.top_errors:
        lines.append("| - | 0 | No errors |")
    return "\n".join(lines)


def _comparison_markdown(report: ComparisonReport) -> str:
    return "\n".join(
        [
            "# Log Period Comparison",
            "",
            "| Metric | Baseline | Current | Delta |",
            "|---|---:|---:|---:|",
            "| Parsed lines | "
            f"{report.baseline.total} | {report.current.total} | {report.total_delta:+d} |",
            "| Errors | "
            f"{report.baseline.errors} | {report.current.errors} | {report.error_delta:+d} |",
            "| Error rate | "
            f"{report.baseline.error_rate:.2%} | {report.current.error_rate:.2%} | "
            f"{report.error_rate_delta:+.2%} |",
            "",
            f"New top fingerprints: {', '.join(report.new_error_fingerprints) or 'none'}",
        ]
    )


def _trace_markdown(report: TraceReport) -> str:
    lines = [
        f"# Correlation Trace: `{_md(report.correlation_id)}`",
        "",
        f"Service chain: **{' → '.join(_md(item) for item in report.service_chain) or 'empty'}**",
        "",
        "| Timestamp | Service | Level | Message |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| {event.timestamp.isoformat()} | {_md(event.service)} | {event.level.value} | "
        f"{_md(event.message)} |"
        for event in report.events
    )
    return "\n".join(lines)


def _validation_markdown(report: ValidationReport) -> str:
    lines = [
        "# Log Validation",
        "",
        "| File | Format | Valid | Invalid |",
        "|---|---|---:|---:|",
    ]
    lines.extend(
        f"| {_md(item.path)} | "
        f"{item.detected_format.value if item.detected_format else 'unknown'} | "
        f"{item.valid_lines} | {item.invalid_lines} |"
        for item in report.files
    )
    return "\n".join(lines)


def _report_title(report: BaseModel) -> str:
    if isinstance(report, AnalysisReport):
        return "Distributed Log Analysis"
    if isinstance(report, ComparisonReport):
        return "Log Period Comparison"
    if isinstance(report, TraceReport):
        return f"Correlation Trace: {report.correlation_id}"
    if isinstance(report, ValidationReport):
        return "Log Validation"
    return "Distributed Log Intelligence Report"


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
