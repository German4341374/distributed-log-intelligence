from __future__ import annotations

import json
from pathlib import Path

import pytest

from distributed_log_intelligence.models import LogFormat, LogLevel
from distributed_log_intelligence.parsers import (
    LogInputError,
    detect_format,
    iter_records,
    parse_level,
)


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [("plain_log", LogFormat.PLAIN), ("jsonl_log", LogFormat.JSONL), ("csv_log", LogFormat.CSV)],
)
def test_detect_format_by_extension(
    fixture_name: str, expected: LogFormat, request: pytest.FixtureRequest
) -> None:
    assert detect_format(request.getfixturevalue(fixture_name)) == expected


def test_detect_format_inside_gzip(gzip_jsonl: Path) -> None:
    assert detect_format(gzip_jsonl) == LogFormat.JSONL


def test_detect_jsonl_by_content(jsonl_log: Path, tmp_path: Path) -> None:
    path = tmp_path / "unknown.data"
    path.write_text(jsonl_log.read_text(encoding="utf-8"), encoding="utf-8")
    assert detect_format(path) == LogFormat.JSONL


def test_detect_csv_by_content(csv_log: Path, tmp_path: Path) -> None:
    path = tmp_path / "unknown.data"
    path.write_text(csv_log.read_text(encoding="utf-8"), encoding="utf-8")
    assert detect_format(path) == LogFormat.CSV


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(LogInputError, match="does not exist"):
        detect_format(tmp_path / "missing.log")


def test_plain_parser_yields_events_and_issue(plain_log: Path) -> None:
    records = list(iter_records(plain_log))
    assert len(records) == 4
    assert sum(record.event is not None for record in records) == 3
    assert records[1].event is not None
    assert records[1].event.service == "orders"
    assert records[1].event.correlation_id == "req-1"
    assert records[-1].issue is not None


def test_jsonl_aliases_are_mapped(jsonl_log: Path) -> None:
    records = list(iter_records(jsonl_log))
    assert records[1].event is not None
    assert records[1].event.level == LogLevel.ERROR
    assert records[1].event.service == "orders"
    assert records[1].event.correlation_id == "req-2"


def test_csv_aliases_are_mapped(csv_log: Path) -> None:
    records = list(iter_records(csv_log))
    assert len(records) == 2
    assert records[1].event is not None
    assert records[1].event.level == LogLevel.CRITICAL


def test_json_array_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    record = next(iter_records(path))
    assert record.issue is not None
    assert "must be an object" in record.issue.reason


def test_missing_required_mapping_field_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    path.write_text(json.dumps({"timestamp": "2026-01-15T08:00:00Z"}) + "\n", encoding="utf-8")
    record = next(iter_records(path))
    assert record.issue is not None
    assert "required field" in record.issue.reason


@pytest.mark.parametrize(
    ("value", "expected"),
    [("warn", LogLevel.WARNING), ("ERR", LogLevel.ERROR), ("fatal", LogLevel.CRITICAL)],
)
def test_parse_level_alias(value: str, expected: LogLevel) -> None:
    assert parse_level(value) == expected


def test_parse_level_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported log level"):
        parse_level("NOTICE")
