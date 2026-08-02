from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from distributed_log_intelligence.operations import (
    generate_demo,
    redact_file,
    trace_correlation,
    validate_files,
)
from distributed_log_intelligence.parsers import iter_records


def test_trace_orders_events_across_files(plain_log: Path, jsonl_log: Path) -> None:
    report = trace_correlation([jsonl_log, plain_log], "req-1")
    assert report.matched_events == 3
    assert report.service_chain == ["gateway", "orders", "payments"]
    assert [item.timestamp for item in report.events] == sorted(
        item.timestamp for item in report.events
    )


def test_trace_caps_returned_events(plain_log: Path) -> None:
    report = trace_correlation([plain_log], "req-1", max_events=2)
    assert report.matched_events == 3
    assert report.returned_events == 2
    assert report.truncated is True


def test_trace_missing_correlation_is_empty(jsonl_log: Path) -> None:
    report = trace_correlation([jsonl_log], "does-not-exist")
    assert report.matched_events == 0
    assert report.service_chain == []


def test_validate_counts_records(plain_log: Path, jsonl_log: Path) -> None:
    report = validate_files([plain_log, jsonl_log])
    assert report.valid_lines == 5
    assert report.invalid_lines == 1
    assert report.is_valid is False


def test_redact_streams_plain_file(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    target = tmp_path / "target.log"
    source.write_text("email demo.user@example.test ip 192.0.2.5\n", encoding="utf-8")
    assert redact_file(source, target) == 1
    content = target.read_text(encoding="utf-8")
    assert "example.test" not in content
    assert "192.0.2.5" not in content


def test_redact_reads_and_writes_gzip(tmp_path: Path) -> None:
    source = tmp_path / "source.log.gz"
    target = tmp_path / "target.log.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("Bearer abcdefghijklmnop\n")
    redact_file(source, target)
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        assert "abcdefghijklmnop" not in handle.read()


def test_redact_refuses_same_path_and_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    target = tmp_path / "target.log"
    source.write_text("safe\n", encoding="utf-8")
    target.write_text("existing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different"):
        redact_file(source, source)
    with pytest.raises(ValueError, match="already exists"):
        redact_file(source, target)


@pytest.mark.parametrize("log_format", ["plain", "jsonl", "csv"])
def test_generate_demo_formats_are_parseable(tmp_path: Path, log_format: str) -> None:
    path = generate_demo(tmp_path / f"demo.{log_format}", lines=25, log_format=log_format)
    records = list(iter_records(path))
    assert len(records) == 25
    assert all(record.event is not None for record in records)


def test_generate_demo_is_deterministic(tmp_path: Path) -> None:
    first = generate_demo(tmp_path / "first.jsonl", lines=20, seed=7)
    second = generate_demo(tmp_path / "second.jsonl", lines=20, seed=7)
    assert first.read_bytes() == second.read_bytes()


def test_generate_demo_gzip_suffix(tmp_path: Path) -> None:
    path = generate_demo(tmp_path / "demo.jsonl", lines=5, gzip_output=True)
    assert path.name == "demo.jsonl.gz"
    assert len(list(iter_records(path))) == 5


def test_generate_demo_rejects_invalid_arguments(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        generate_demo(tmp_path / "bad.jsonl", lines=0)
    with pytest.raises(ValueError, match="plain, jsonl, or csv"):
        generate_demo(tmp_path / "bad.xml", log_format="xml")
