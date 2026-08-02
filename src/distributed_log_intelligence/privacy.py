"""Best-effort PII and credential masking without external data transfer."""

from __future__ import annotations

import re

MASK_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "bearer_token",
        re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"),
        r"\1 [REDACTED_TOKEN]",
    ),
    (
        "api_key",
        re.compile(
            r"(?i)\b(api[-_ ]?key|access[-_ ]?token|secret)\b(\s*[:=]\s*)[\"']?"
            r"[A-Za-z0-9._~+/=-]{6,}[\"']?"
        ),
        r"\1\2[REDACTED_SECRET]",
    ),
    (
        "email",
        re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])"),
        "[REDACTED_EMAIL]",
    ),
    (
        "ipv4",
        re.compile(
            r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)"
            r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
        ),
        "[REDACTED_IP]",
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){9,15}(?!\w)"),
        "[REDACTED_PHONE]",
    ),
)


def mask_text(text: str) -> str:
    masked = text
    for _, pattern, replacement in MASK_RULES:
        masked = pattern.sub(replacement, masked)
    return masked


def find_sensitive_types(text: str) -> set[str]:
    return {name for name, pattern, _ in MASK_RULES if pattern.search(text)}
