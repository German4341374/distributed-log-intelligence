from __future__ import annotations

from datetime import UTC, datetime

import pytest

from distributed_log_intelligence.timestamps import TimestampError, parse_timestamp


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-15T08:00:00Z", datetime(2026, 1, 15, 8, tzinfo=UTC)),
        ("2026-01-15T10:00:00+02:00", datetime(2026, 1, 15, 8, tzinfo=UTC)),
        ("2026-01-15 08:00:00,123", datetime(2026, 1, 15, 8, 0, 0, 123000, tzinfo=UTC)),
        (1768464000, datetime(2026, 1, 15, 8, tzinfo=UTC)),
        (1768464000000, datetime(2026, 1, 15, 8, tzinfo=UTC)),
    ],
)
def test_parse_timestamp_normalizes_to_utc(value: object, expected: datetime) -> None:
    assert parse_timestamp(value) == expected


def test_parse_naive_timestamp_uses_named_timezone() -> None:
    parsed = parse_timestamp("2026-01-15T10:00:00", "Europe/Berlin")
    assert parsed == datetime(2026, 1, 15, 9, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", "not-a-date", None, True, 10**30])
def test_invalid_timestamp_raises(value: object) -> None:
    with pytest.raises(TimestampError):
        parse_timestamp(value)


def test_unknown_timezone_raises() -> None:
    with pytest.raises(TimestampError, match="unknown default timezone"):
        parse_timestamp("2026-01-15T08:00:00", "Mars/Olympus")
