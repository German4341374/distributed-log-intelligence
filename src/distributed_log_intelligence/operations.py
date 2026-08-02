"""Trace, validation, redaction, and deterministic demo operations."""

from __future__ import annotations

import csv
import gzip
import json
import random
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

from distributed_log_intelligence.models import (
    FileValidation,
    ParseIssue,
    TraceEvent,
    TraceReport,
    ValidationReport,
)
from distributed_log_intelligence.parsers import detect_format, iter_raw_lines, iter_records
from distributed_log_intelligence.privacy import mask_text


def trace_correlation(
    paths: list[Path],
    correlation_id: str,
    *,
    default_timezone: str = "UTC",
    max_events: int = 1_000,
) -> TraceReport:
    if not paths:
        raise ValueError("at least one input file is required")
    if not correlation_id.strip():
        raise ValueError("correlation ID must not be empty")
    malformed = 0
    with tempfile.NamedTemporaryFile(
        prefix="dli-trace-", suffix=".sqlite3", delete=False
    ) as temp_file:
        database_path = Path(temp_file.name)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE events (
                timestamp TEXT NOT NULL,
                service TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT NOT NULL,
                line_number INTEGER NOT NULL
            )
            """
        )
        batch: list[tuple[str, str, str, str, str, int]] = []
        for path in paths:
            for record in iter_records(path, default_timezone=default_timezone):
                if record.issue is not None:
                    malformed += 1
                    continue
                event = record.event
                if event is None or event.correlation_id != correlation_id:
                    continue
                batch.append(
                    (
                        event.timestamp.isoformat(),
                        event.service,
                        event.level.value,
                        mask_text(event.message),
                        event.source,
                        event.line_number,
                    )
                )
                if len(batch) >= 1_000:
                    connection.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            connection.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", batch)
        connection.commit()
        matched = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        rows = connection.execute(
            "SELECT * FROM events ORDER BY timestamp, source, line_number LIMIT ?", (max_events,)
        ).fetchall()
    finally:
        connection.close()
        database_path.unlink(missing_ok=True)

    events = [
        TraceEvent(
            timestamp=datetime.fromisoformat(row[0]),
            service=row[1],
            level=row[2],
            message=row[3],
            source=row[4],
            line_number=row[5],
        )
        for row in rows
    ]
    service_chain: list[str] = []
    for trace_event in events:
        if not service_chain or service_chain[-1] != trace_event.service:
            service_chain.append(trace_event.service)
    return TraceReport(
        generated_at=datetime.now(UTC),
        correlation_id=correlation_id,
        matched_events=matched,
        returned_events=len(events),
        truncated=matched > len(events),
        service_chain=service_chain,
        events=events,
        malformed_lines=malformed,
    )


def validate_files(
    paths: list[Path], *, default_timezone: str = "UTC", sample_limit: int = 20
) -> ValidationReport:
    if not paths:
        raise ValueError("at least one input file is required")
    results: list[FileValidation] = []
    total_valid = 0
    total_invalid = 0
    for path in paths:
        log_format = detect_format(path)
        valid = 0
        invalid = 0
        issues: list[ParseIssue] = []
        for record in iter_records(path, default_timezone=default_timezone, log_format=log_format):
            if record.event is not None:
                valid += 1
            elif record.issue is not None:
                invalid += 1
                if len(issues) < sample_limit:
                    record.issue.preview = mask_text(record.issue.preview)
                    issues.append(record.issue)
        total_valid += valid
        total_invalid += invalid
        results.append(
            FileValidation(
                path=str(path),
                detected_format=log_format,
                valid_lines=valid,
                invalid_lines=invalid,
                issue_samples=issues,
            )
        )
    return ValidationReport(
        generated_at=datetime.now(UTC),
        files=results,
        valid_lines=total_valid,
        invalid_lines=total_invalid,
        is_valid=total_invalid == 0,
    )


def redact_file(source: Path, destination: Path, *, overwrite: bool = False) -> int:
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must be different")
    if destination.exists() and not overwrite:
        raise ValueError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    line_count = 0
    with _open_output(destination) as output:
        for line in iter_raw_lines(source):
            output.write(mask_text(line))
            line_count += 1
    return line_count


def generate_demo(
    destination: Path,
    *,
    lines: int = 1_000,
    log_format: str = "jsonl",
    seed: int = 42,
    gzip_output: bool = False,
) -> Path:
    if lines < 1:
        raise ValueError("lines must be at least 1")
    if log_format not in {"plain", "jsonl", "csv"}:
        raise ValueError("format must be plain, jsonl, or csv")
    output_path = destination
    if gzip_output and destination.suffix.lower() != ".gz":
        output_path = destination.with_name(f"{destination.name}.gz")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    start = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
    with _open_output(output_path) as output:
        writer = None
        if log_format == "csv":
            writer = csv.DictWriter(
                output,
                fieldnames=["timestamp", "level", "service", "correlation_id", "message"],
            )
            writer.writeheader()
        for index, event in enumerate(_demo_events(lines, start, rng)):
            if writer is not None:
                writer.writerow(event)
            elif log_format == "jsonl":
                output.write(json.dumps(event, separators=(",", ":")) + "\n")
            else:
                output.write(
                    f"{event['timestamp']} {event['level']} service={event['service']} "
                    f"correlation_id={event['correlation_id']} {event['message']}\n"
                )
            if index % 5_000 == 0:
                output.flush()
    return output_path


def _demo_events(lines: int, start: datetime, rng: random.Random) -> Iterator[dict[str, str]]:
    services = ("gateway", "orders", "payments", "inventory", "notifications")
    normal_messages = (
        "request completed",
        "cache entry refreshed",
        "database query completed",
        "worker heartbeat accepted",
    )
    error_messages = (
        "database timeout after 5000 ms for order id={id}",
        "connection refused by inventory node 192.0.2.44",
        "authentication failed for user demo.user@example.test",
        "upstream returned error code 502 request_id={id}",
    )
    for index in range(lines):
        timestamp = start + timedelta(seconds=index * 2)
        service = services[index % len(services)]
        correlation_id = f"demo-{index // len(services):08d}"
        burst = lines // 2 <= index < min(lines, lines // 2 + max(20, lines // 50))
        is_error = burst or rng.random() < 0.07
        if is_error:
            level = "CRITICAL" if rng.random() < 0.05 else "ERROR"
            message = rng.choice(error_messages).format(id=100_000 + index)
        else:
            level = "WARNING" if rng.random() < 0.08 else "INFO"
            message = rng.choice(normal_messages)
        yield {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "level": level,
            "service": service,
            "correlation_id": correlation_id,
            "message": message,
        }


def _open_output(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, mode="wt", encoding="utf-8", newline="")
    return path.open(mode="w", encoding="utf-8", newline="")
