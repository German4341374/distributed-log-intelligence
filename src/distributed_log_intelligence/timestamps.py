"""Timestamp recognition and UTC normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

KNOWN_FORMATS = (
    "%Y-%m-%d %H:%M:%S,%f",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d/%b/%Y:%H:%M:%S %z",
)


class TimestampError(ValueError):
    """Raised when a timestamp cannot be parsed or normalized."""


def parse_timestamp(value: Any, default_timezone: str = "UTC") -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if abs(seconds) > 100_000_000_000:
            seconds /= 1000
        try:
            parsed = datetime.fromtimestamp(seconds, tz=UTC)
        except (OSError, OverflowError, ValueError) as exc:
            raise TimestampError(f"invalid epoch timestamp: {value}") from exc
    elif isinstance(value, str):
        parsed = _parse_text(value.strip())
    else:
        raise TimestampError(f"unsupported timestamp value: {value!r}")

    if parsed.tzinfo is None:
        if default_timezone.upper() == "UTC":
            return parsed.replace(tzinfo=UTC)
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(default_timezone))
        except ZoneInfoNotFoundError as exc:
            raise TimestampError(f"unknown default timezone: {default_timezone}") from exc
    return parsed.astimezone(UTC)


def _parse_text(value: str) -> datetime:
    if not value:
        raise TimestampError("timestamp is empty")

    candidate = value
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass

    if value.isdigit() or _is_float(value):
        return parse_timestamp(float(value))

    for timestamp_format in KNOWN_FORMATS:
        try:
            return datetime.strptime(value, timestamp_format)
        except ValueError:
            continue
    raise TimestampError(f"unrecognized timestamp: {value!r}")


def _is_float(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
