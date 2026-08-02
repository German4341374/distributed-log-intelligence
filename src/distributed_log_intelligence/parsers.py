"""Streaming format detection and parsing for plain, JSONL, CSV, and gzip logs."""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from distributed_log_intelligence.models import (
    LogEvent,
    LogFormat,
    LogLevel,
    ParseIssue,
    ParseRecord,
)
from distributed_log_intelligence.timestamps import TimestampError, parse_timestamp

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "@timestamp", "time", "datetime", "date"),
    "level": ("level", "severity", "loglevel", "log_level"),
    "service": ("service", "app", "application", "component", "logger"),
    "message": ("message", "msg", "event", "text"),
    "correlation_id": (
        "correlation_id",
        "correlationid",
        "correlation-id",
        "trace_id",
        "traceid",
        "request_id",
        "requestid",
    ),
}

LEVEL_ALIASES = {
    "TRACE": LogLevel.DEBUG,
    "DEBUG": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "INFORMATION": LogLevel.INFO,
    "WARN": LogLevel.WARNING,
    "WARNING": LogLevel.WARNING,
    "ERROR": LogLevel.ERROR,
    "ERR": LogLevel.ERROR,
    "FATAL": LogLevel.CRITICAL,
    "CRITICAL": LogLevel.CRITICAL,
    "CRIT": LogLevel.CRITICAL,
}

PLAIN_RE = re.compile(
    r"^\s*\[?(?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?\s+"
    r"\[?(?P<level>TRACE|DEBUG|INFO|INFORMATION|WARN(?:ING)?|ERR(?:OR)?|FATAL|CRIT(?:ICAL)?)\]?"
    r"\s+(?P<tail>.*)$",
    re.IGNORECASE,
)
KEY_VALUE_RE = re.compile(
    r"(?P<key>service|app|component|correlation[_-]?id|trace[_-]?id|request[_-]?id)"
    r"[=:](?P<value>\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)


class LogInputError(ValueError):
    """Raised for missing, unreadable, or unsupported log input."""


@contextmanager
def open_text(path: Path) -> Iterator[TextIO]:
    try:
        if path.suffix.lower() == ".gz":
            with gzip.open(
                path, mode="rt", encoding="utf-8", errors="replace", newline=""
            ) as handle:
                yield handle
        else:
            with path.open(mode="r", encoding="utf-8", errors="replace", newline="") as handle:
                yield handle
    except (OSError, gzip.BadGzipFile) as exc:
        raise LogInputError(f"cannot read {path}: {exc}") from exc


def detect_format(path: Path) -> LogFormat:
    if not path.is_file():
        raise LogInputError(f"input file does not exist: {path}")

    logical_suffix = _logical_suffix(path)
    if logical_suffix in {".jsonl", ".ndjson"}:
        return LogFormat.JSONL
    if logical_suffix == ".csv":
        return LogFormat.CSV
    if logical_suffix in {".log", ".txt"}:
        return LogFormat.PLAIN

    with open_text(path) as handle:
        sample_lines: list[str] = []
        for line in handle:
            if line.strip():
                sample_lines.append(line)
            if len(sample_lines) >= 5:
                break
    if not sample_lines:
        return LogFormat.PLAIN

    first = sample_lines[0].lstrip()
    if first.startswith("{"):
        return LogFormat.JSONL

    sample = "".join(sample_lines)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        header = next(csv.reader(io.StringIO(sample), dialect=dialect))
        normalized = {_normalized_key(value) for value in header}
        if normalized.intersection(FIELD_ALIASES["timestamp"]) and normalized.intersection(
            FIELD_ALIASES["message"]
        ):
            return LogFormat.CSV
    except csv.Error:
        pass
    return LogFormat.PLAIN


def iter_records(
    path: Path,
    *,
    default_timezone: str = "UTC",
    log_format: LogFormat | None = None,
) -> Iterator[ParseRecord]:
    selected_format = log_format or detect_format(path)
    if selected_format == LogFormat.CSV:
        yield from _iter_csv(path, default_timezone)
    else:
        yield from _iter_line_records(path, selected_format, default_timezone)


def iter_raw_lines(path: Path) -> Iterator[str]:
    with open_text(path) as handle:
        yield from handle


def _iter_line_records(
    path: Path, log_format: LogFormat, default_timezone: str
) -> Iterator[ParseRecord]:
    with open_text(path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                yield _issue(path, line_number, "empty line", line)
                continue
            try:
                if log_format == LogFormat.JSONL:
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError("JSON value must be an object")
                    event = _event_from_mapping(raw, path, line_number, default_timezone)
                else:
                    event = _event_from_plain(line, path, line_number, default_timezone)
                yield ParseRecord(event=event)
            except (json.JSONDecodeError, TimestampError, ValidationError, ValueError) as exc:
                yield _issue(path, line_number, str(exc), line)


def _iter_csv(path: Path, default_timezone: str) -> Iterator[ParseRecord]:
    with open_text(path) as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            yield _issue(path, 1, "CSV header is missing", sample[:200])
            return
        for row in reader:
            line_number = reader.line_num
            try:
                event = _event_from_mapping(row, path, line_number, default_timezone)
                yield ParseRecord(event=event)
            except (TimestampError, ValidationError, ValueError) as exc:
                preview = ", ".join(f"{key}={value}" for key, value in row.items())
                yield _issue(path, line_number, str(exc), preview)


def _event_from_mapping(
    raw: Mapping[str, Any], path: Path, line_number: int, default_timezone: str
) -> LogEvent:
    normalized = {_normalized_key(str(key)): value for key, value in raw.items() if key is not None}
    timestamp_value = _pick(normalized, "timestamp")
    level_value = _pick(normalized, "level")
    message_value = _pick(normalized, "message")
    service_value = _pick(normalized, "service", required=False) or "unknown"
    correlation_value = _pick(normalized, "correlation_id", required=False)

    known_keys = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
    extra = {key: value for key, value in normalized.items() if key not in known_keys}
    return LogEvent(
        timestamp=parse_timestamp(timestamp_value, default_timezone),
        level=parse_level(level_value),
        service=str(service_value).strip() or "unknown",
        message=str(message_value),
        correlation_id=(str(correlation_value).strip() or None)
        if correlation_value is not None
        else None,
        source=str(path),
        line_number=line_number,
        fields=extra,
    )


def _event_from_plain(line: str, path: Path, line_number: int, default_timezone: str) -> LogEvent:
    match = PLAIN_RE.match(line)
    if not match:
        raise ValueError("plain line does not match '<timestamp> <level> <message>'")

    tail = match.group("tail")
    service = "unknown"
    correlation_id: str | None = None
    spans: list[tuple[int, int]] = []
    for item in KEY_VALUE_RE.finditer(tail):
        key = _normalized_key(item.group("key"))
        value = item.group("value").strip("\"'")
        spans.append(item.span())
        if key in FIELD_ALIASES["service"]:
            service = value
        elif key in FIELD_ALIASES["correlation_id"]:
            correlation_id = value

    message = _remove_spans(tail, spans).strip(" |-:") or tail
    return LogEvent(
        timestamp=parse_timestamp(match.group("timestamp"), default_timezone),
        level=parse_level(match.group("level")),
        service=service,
        message=message,
        correlation_id=correlation_id,
        source=str(path),
        line_number=line_number,
    )


def parse_level(value: Any) -> LogLevel:
    key = str(value).strip().upper()
    try:
        return LEVEL_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported log level: {value!r}") from exc


def _pick(mapping: Mapping[str, Any], field: str, *, required: bool = True) -> Any:
    for alias in FIELD_ALIASES[field]:
        value = mapping.get(alias)
        if value is not None and str(value).strip():
            return value
    if required:
        raise ValueError(f"required field is missing: {field}")
    return None


def _normalized_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


def _logical_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    return Path(name).suffix


def _remove_spans(value: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return value
    parts: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        parts.append(value[cursor:start])
        cursor = end
    parts.append(value[cursor:])
    return " ".join(parts)


def _issue(path: Path, line_number: int, reason: str, preview: str) -> ParseRecord:
    compact_preview = preview.replace("\r", " ").replace("\n", " ")[:240]
    return ParseRecord(
        issue=ParseIssue(
            source=str(path), line_number=line_number, reason=reason, preview=compact_preview
        )
    )
