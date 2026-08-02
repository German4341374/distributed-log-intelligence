"""Message normalization used for stable, privacy-aware error grouping."""

from __future__ import annotations

import hashlib
import re

from distributed_log_intelligence.privacy import mask_text

UUID_RE = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
    re.IGNORECASE,
)
HEX_RE = re.compile(r"(?i)\b(?:0x)?[0-9a-f]{16,}\b")
KEYED_ID_RE = re.compile(r"(?i)\b([a-z_]*(?:id|count|code|port))\s*[=:]\s*\d+\b")
NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    normalized = mask_text(message).lower()
    normalized = UUID_RE.sub("<uuid>", normalized)
    normalized = ISO_TIMESTAMP_RE.sub("<timestamp>", normalized)
    normalized = HEX_RE.sub("<hex>", normalized)
    normalized = KEYED_ID_RE.sub(lambda match: f"{match.group(1)}=<id>", normalized)
    normalized = NUMBER_RE.sub("<number>", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized or "<empty>"


def fingerprint_message(message: str) -> tuple[str, str]:
    normalized = normalize_message(message)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return digest, normalized
