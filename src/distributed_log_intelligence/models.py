"""Typed domain models shared by parsers, analyzers, and reporters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LogFormat(StrEnum):
    PLAIN = "plain"
    JSONL = "jsonl"
    CSV = "csv"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @property
    def is_error(self) -> bool:
        return self in {LogLevel.ERROR, LogLevel.CRITICAL}


class LogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    level: LogLevel
    service: str = Field(min_length=1, max_length=200)
    message: str
    correlation_id: str | None = Field(default=None, max_length=500)
    source: str
    line_number: int = Field(ge=1)
    fields: dict[str, Any] = Field(default_factory=dict)


class ParseIssue(BaseModel):
    source: str
    line_number: int = Field(ge=1)
    reason: str
    preview: str


class ParseRecord(BaseModel):
    event: LogEvent | None = None
    issue: ParseIssue | None = None


class ErrorGroup(BaseModel):
    fingerprint: str
    normalized_message: str
    count: int
    examples: list[str]
    services: dict[str, int]
    first_seen: datetime
    last_seen: datetime


class WindowStat(BaseModel):
    start: datetime
    total: int
    errors: int
    error_rate: float


class Anomaly(BaseModel):
    start: datetime
    errors: int
    score: float
    reason: str


class AnalysisReport(BaseModel):
    generated_at: datetime
    files: list[str]
    formats: dict[str, LogFormat]
    total_lines: int
    parsed_lines: int
    malformed_lines: int
    error_count: int
    error_rate: float
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    levels: dict[str, int]
    errors_by_service: dict[str, int]
    top_errors: list[ErrorGroup]
    top_correlations: dict[str, int]
    windows: list[WindowStat]
    bursts: list[Anomaly]
    anomalies: list[Anomaly]
    dropped_error_groups: int
    dropped_windows: int
    issue_samples: list[ParseIssue]


class PeriodSummary(BaseModel):
    files: list[str]
    total: int
    errors: int
    error_rate: float
    top_error_fingerprints: list[str]


class ComparisonReport(BaseModel):
    generated_at: datetime
    baseline: PeriodSummary
    current: PeriodSummary
    total_delta: int
    error_delta: int
    error_rate_delta: float
    new_error_fingerprints: list[str]
    resolved_error_fingerprints: list[str]
    service_error_deltas: dict[str, int]


class TraceEvent(BaseModel):
    timestamp: datetime
    service: str
    level: LogLevel
    message: str
    source: str
    line_number: int


class TraceReport(BaseModel):
    generated_at: datetime
    correlation_id: str
    matched_events: int
    returned_events: int
    truncated: bool
    service_chain: list[str]
    events: list[TraceEvent]
    malformed_lines: int


class FileValidation(BaseModel):
    path: str
    detected_format: LogFormat | None
    valid_lines: int
    invalid_lines: int
    issue_samples: list[ParseIssue]


class ValidationReport(BaseModel):
    generated_at: datetime
    files: list[FileValidation]
    valid_lines: int
    invalid_lines: int
    is_valid: bool


class AnalyzeOptions(BaseModel):
    window_minutes: int = Field(default=5, ge=1, le=1440)
    top: int = Field(default=10, ge=1, le=100)
    burst_threshold: int = Field(default=10, ge=1)
    anomaly_zscore: float = Field(default=3.0, ge=0.1, le=20.0)
    default_timezone: str = "UTC"
    max_error_groups: int = Field(default=10_000, ge=100, le=1_000_000)
    max_windows: int = Field(default=100_000, ge=100, le=1_000_000)
    max_services: int = Field(default=10_000, ge=100, le=1_000_000)
    max_correlations: int = Field(default=1_000, ge=10, le=100_000)
    issue_sample_limit: int = Field(default=20, ge=0, le=1_000)


def path_strings(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths]
