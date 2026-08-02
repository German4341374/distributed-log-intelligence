from __future__ import annotations

import pytest

from distributed_log_intelligence.normalization import fingerprint_message, normalize_message
from distributed_log_intelligence.privacy import find_sensitive_types, mask_text


@pytest.mark.parametrize(
    ("raw", "marker"),
    [
        ("contact demo.user@example.test", "[REDACTED_EMAIL]"),
        ("client 192.0.2.44 failed", "[REDACTED_IP]"),
        ("Authorization: Bearer abcdefghijklmnop", "[REDACTED_TOKEN]"),
        ("api_key=abcdef123456", "[REDACTED_SECRET]"),
        ("call +1 (202) 555-0142", "[REDACTED_PHONE]"),
    ],
)
def test_mask_text(raw: str, marker: str) -> None:
    assert marker in mask_text(raw)


def test_mask_text_does_not_change_unrelated_message() -> None:
    assert mask_text("database timeout") == "database timeout"


def test_find_sensitive_types_returns_all_matches() -> None:
    found = find_sensitive_types("demo.user@example.test from 192.0.2.1")
    assert found == {"email", "ipv4"}


def test_normalization_groups_volatile_values() -> None:
    first = "Order 123 failed for 550e8400-e29b-41d4-a716-446655440000 from 192.0.2.1"
    second = "Order 456 failed for 550e8400-e29b-41d4-a716-446655440001 from 198.51.100.2"
    assert normalize_message(first) == normalize_message(second)
    assert fingerprint_message(first)[0] == fingerprint_message(second)[0]


def test_normalization_replaces_keyed_id_and_timestamp() -> None:
    normalized = normalize_message("request_id=456 failed at 2026-01-15T08:00:00Z")
    assert "request_id=<id>" in normalized
    assert "<timestamp>" in normalized


def test_normalization_handles_empty_message() -> None:
    assert normalize_message("  \t ") == "<empty>"


def test_fingerprint_is_stable_and_short() -> None:
    fingerprint, normalized = fingerprint_message("Database timeout 42")
    assert len(fingerprint) == 16
    assert normalized == "database timeout <number>"
