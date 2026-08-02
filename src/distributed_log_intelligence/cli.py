"""Typer command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.markup import escape

from distributed_log_intelligence import __version__
from distributed_log_intelligence.analyzer import analyze_files, compare_reports
from distributed_log_intelligence.models import AnalyzeOptions
from distributed_log_intelligence.operations import (
    generate_demo as generate_demo_file,
)
from distributed_log_intelligence.operations import (
    redact_file,
    trace_correlation,
    validate_files,
)
from distributed_log_intelligence.parsers import LogInputError
from distributed_log_intelligence.reports import export_report, render_console
from distributed_log_intelligence.timestamps import TimestampError

app = typer.Typer(
    name="distributed-log-intelligence",
    help="Stream, analyze, compare, trace, and redact distributed application logs.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
console = Console()

PathArguments = Annotated[list[Path], typer.Argument(help="One or more log files")]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Local-first log intelligence without sending data to external services."""


@app.command()
def analyze(
    files: PathArguments,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Report output path.")
    ] = None,
    report_format: Annotated[
        str | None,
        typer.Option("--report-format", help="json, markdown, html, or junit."),
    ] = None,
    window_minutes: Annotated[int, typer.Option("--window-minutes", min=1, max=1440)] = 5,
    top: Annotated[int, typer.Option("--top", min=1, max=100)] = 10,
    burst_threshold: Annotated[int, typer.Option("--burst-threshold", min=1)] = 10,
    anomaly_zscore: Annotated[float, typer.Option("--anomaly-zscore", min=0.1)] = 3.0,
    default_timezone: Annotated[str, typer.Option("--default-timezone")] = "UTC",
    fail_on_malformed: Annotated[bool, typer.Option("--fail-on-malformed")] = False,
    fail_on_anomaly: Annotated[bool, typer.Option("--fail-on-anomaly")] = False,
) -> None:
    """Analyze one or more logs in a single streaming pass."""
    try:
        options = AnalyzeOptions(
            window_minutes=window_minutes,
            top=top,
            burst_threshold=burst_threshold,
            anomaly_zscore=anomaly_zscore,
            default_timezone=default_timezone,
        )
        report = analyze_files(files, options)
        render_console(report, console)
        _export_if_requested(report, output, report_format)
        if (fail_on_malformed and report.malformed_lines) or (fail_on_anomaly and report.anomalies):
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (LogInputError, TimestampError, ValidationError, ValueError) as exc:
        _fail(exc)


@app.command()
def compare(
    baseline: PathArguments,
    current: Annotated[
        list[Path],
        typer.Option("--current", "-c", help="Current-period file; repeat for multiple files."),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    report_format: Annotated[str | None, typer.Option("--report-format")] = None,
    window_minutes: Annotated[int, typer.Option("--window-minutes", min=1, max=1440)] = 5,
    default_timezone: Annotated[str, typer.Option("--default-timezone")] = "UTC",
) -> None:
    """Compare error volume and fingerprints between two periods."""
    try:
        if not current:
            raise ValueError("provide at least one --current file")
        options = AnalyzeOptions(window_minutes=window_minutes, default_timezone=default_timezone)
        report = compare_reports(analyze_files(baseline, options), analyze_files(current, options))
        render_console(report, console)
        _export_if_requested(report, output, report_format)
    except (LogInputError, TimestampError, ValidationError, ValueError) as exc:
        _fail(exc)


@app.command()
def trace(
    correlation_id: Annotated[str, typer.Argument(help="Exact correlation ID to trace")],
    files: PathArguments,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    report_format: Annotated[str | None, typer.Option("--report-format")] = None,
    default_timezone: Annotated[str, typer.Option("--default-timezone")] = "UTC",
    max_events: Annotated[int, typer.Option("--max-events", min=1, max=100_000)] = 1_000,
) -> None:
    """Reconstruct a time-ordered cross-service chain for a correlation ID."""
    try:
        report = trace_correlation(
            files,
            correlation_id,
            default_timezone=default_timezone,
            max_events=max_events,
        )
        render_console(report, console)
        _export_if_requested(report, output, report_format)
        if not report.matched_events:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (LogInputError, TimestampError, ValueError) as exc:
        _fail(exc)


@app.command()
def redact(
    source: Annotated[Path, typer.Argument(help="Source log, including .gz")],
    destination: Annotated[Path, typer.Argument(help="Redacted output path")],
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output.")
    ] = False,
) -> None:
    """Mask PII and credentials while streaming a log to a new file."""
    try:
        lines = redact_file(source, destination, overwrite=overwrite)
        console.print(
            f"Redacted [bold]{lines}[/bold] lines to [green]{escape(str(destination))}[/green]"
        )
    except (LogInputError, OSError, ValueError) as exc:
        _fail(exc)


@app.command("validate")
def validate_command(
    files: PathArguments,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    report_format: Annotated[str | None, typer.Option("--report-format")] = None,
    default_timezone: Annotated[str, typer.Option("--default-timezone")] = "UTC",
) -> None:
    """Validate formats and fields; exit 1 when malformed records are found."""
    try:
        report = validate_files(files, default_timezone=default_timezone)
        render_console(report, console)
        _export_if_requested(report, output, report_format)
        if not report.is_valid:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (LogInputError, TimestampError, ValueError) as exc:
        _fail(exc)


@app.command("generate-demo")
def generate_demo_command(
    destination: Annotated[Path, typer.Argument(help="Destination file")],
    lines: Annotated[int, typer.Option("--lines", min=1)] = 1_000,
    log_format: Annotated[str, typer.Option("--format", help="plain, jsonl, or csv")] = "jsonl",
    seed: Annotated[int, typer.Option("--seed")] = 42,
    gzip_output: Annotated[bool, typer.Option("--gzip")] = False,
) -> None:
    """Generate deterministic, synthetic logs with a planted error burst."""
    try:
        output = generate_demo_file(
            destination,
            lines=lines,
            log_format=log_format,
            seed=seed,
            gzip_output=gzip_output,
        )
        console.print(
            "Generated "
            f"[bold]{lines}[/bold] synthetic records at [green]{escape(str(output))}[/green]"
        )
    except (OSError, ValueError) as exc:
        _fail(exc)


def _export_if_requested(report: BaseModel, output: Path | None, report_format: str | None) -> None:
    if output is None:
        if report_format:
            raise ValueError("--report-format requires --output")
        return
    export_report(report, output, report_format)
    console.print(f"Report written to [green]{escape(str(output))}[/green]")


def _fail(error: Exception) -> None:
    console.print(f"[red]Error:[/red] {escape(str(error))}", highlight=False)
    raise typer.Exit(code=2) from error
