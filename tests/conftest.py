from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pytest


@pytest.fixture
def plain_log(tmp_path: Path) -> Path:
    path = tmp_path / "app.log"
    path.write_text(
        "\n".join(
            [
                "2026-01-15T08:00:00Z INFO service=gateway correlation_id=req-1 request accepted",
                "2026-01-15T08:00:01+00:00 ERROR service=orders "
                "correlation_id=req-1 database timeout id=123",
                "2026-01-15 08:00:02 WARNING service=payments correlation_id=req-1 retry scheduled",
                "broken line",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def jsonl_log(tmp_path: Path) -> Path:
    path = tmp_path / "app.jsonl"
    records = [
        {
            "timestamp": "2026-01-15T10:00:00+02:00",
            "level": "INFO",
            "service": "gateway",
            "message": "request accepted",
            "correlation_id": "req-2",
        },
        {
            "@timestamp": "2026-01-15T08:00:01Z",
            "severity": "ERROR",
            "component": "orders",
            "msg": "database timeout id=456",
            "trace_id": "req-2",
        },
    ]
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def csv_log(tmp_path: Path) -> Path:
    path = tmp_path / "app.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "log_level", "application", "request_id", "text"])
        writer.writerow(["2026-01-15T08:00:00Z", "INFO", "api", "req-3", "request accepted"])
        writer.writerow(["2026-01-15T08:00:01Z", "FATAL", "database", "req-3", "out of memory"])
    return path


@pytest.fixture
def gzip_jsonl(jsonl_log: Path, tmp_path: Path) -> Path:
    path = tmp_path / "app.jsonl.gz"
    with (
        jsonl_log.open("rt", encoding="utf-8") as source,
        gzip.open(path, "wt", encoding="utf-8") as destination,
    ):
        destination.write(source.read())
    return path
