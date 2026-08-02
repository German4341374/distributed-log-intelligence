"""Bounded-memory streaming analysis and period comparison."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from distributed_log_intelligence.models import (
    AnalysisReport,
    AnalyzeOptions,
    Anomaly,
    ComparisonReport,
    ErrorGroup,
    LogEvent,
    LogFormat,
    ParseIssue,
    PeriodSummary,
    WindowStat,
    path_strings,
)
from distributed_log_intelligence.normalization import fingerprint_message
from distributed_log_intelligence.parsers import detect_format, iter_records
from distributed_log_intelligence.privacy import mask_text


@dataclass(slots=True)
class _MutableErrorGroup:
    fingerprint: str
    normalized_message: str
    count: int
    examples: list[str]
    services: Counter[str]
    first_seen: datetime
    last_seen: datetime


@dataclass(slots=True)
class _Window:
    total: int = 0
    errors: int = 0


@dataclass(slots=True)
class _State:
    total_lines: int = 0
    parsed_lines: int = 0
    malformed_lines: int = 0
    error_count: int = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    levels: Counter[str] = field(default_factory=Counter)
    service_errors: Counter[str] = field(default_factory=Counter)
    correlations: Counter[str] = field(default_factory=Counter)
    groups: dict[str, _MutableErrorGroup] = field(default_factory=dict)
    windows: dict[datetime, _Window] = field(default_factory=dict)
    dropped_error_groups: int = 0
    dropped_windows: int = 0
    issues: list[ParseIssue] = field(default_factory=list)


def analyze_files(paths: list[Path], options: AnalyzeOptions | None = None) -> AnalysisReport:
    if not paths:
        raise ValueError("at least one input file is required")
    selected = options or AnalyzeOptions()
    formats: dict[str, LogFormat] = {str(path): detect_format(path) for path in paths}
    state = _State()

    for path in paths:
        for record in iter_records(
            path, default_timezone=selected.default_timezone, log_format=formats[str(path)]
        ):
            state.total_lines += 1
            if record.issue is not None:
                _record_issue(state, record.issue, selected.issue_sample_limit)
                continue
            if record.event is None:
                continue
            _consume_event(state, record.event, selected)

    window_stats = _window_stats(state.windows)
    bursts = _detect_bursts(window_stats, selected.burst_threshold)
    anomalies = _detect_anomalies(window_stats, selected.anomaly_zscore)
    return AnalysisReport(
        generated_at=datetime.now(UTC),
        files=path_strings(paths),
        formats=formats,
        total_lines=state.total_lines,
        parsed_lines=state.parsed_lines,
        malformed_lines=state.malformed_lines,
        error_count=state.error_count,
        error_rate=_ratio(state.error_count, state.parsed_lines),
        first_timestamp=state.first_timestamp,
        last_timestamp=state.last_timestamp,
        levels=dict(state.levels.most_common()),
        errors_by_service=dict(state.service_errors.most_common(selected.top)),
        top_errors=_top_error_groups(state.groups, selected.top),
        top_correlations=dict(state.correlations.most_common(selected.top)),
        windows=window_stats,
        bursts=bursts,
        anomalies=anomalies,
        dropped_error_groups=state.dropped_error_groups,
        dropped_windows=state.dropped_windows,
        issue_samples=state.issues,
    )


def compare_reports(baseline: AnalysisReport, current: AnalysisReport) -> ComparisonReport:
    baseline_fingerprints = [item.fingerprint for item in baseline.top_errors]
    current_fingerprints = [item.fingerprint for item in current.top_errors]
    all_services = set(baseline.errors_by_service) | set(current.errors_by_service)
    service_deltas = {
        service: current.errors_by_service.get(service, 0)
        - baseline.errors_by_service.get(service, 0)
        for service in sorted(all_services)
    }
    return ComparisonReport(
        generated_at=datetime.now(UTC),
        baseline=_period_summary(baseline),
        current=_period_summary(current),
        total_delta=current.parsed_lines - baseline.parsed_lines,
        error_delta=current.error_count - baseline.error_count,
        error_rate_delta=round(current.error_rate - baseline.error_rate, 6),
        new_error_fingerprints=sorted(set(current_fingerprints) - set(baseline_fingerprints)),
        resolved_error_fingerprints=sorted(set(baseline_fingerprints) - set(current_fingerprints)),
        service_error_deltas=service_deltas,
    )


def _consume_event(state: _State, event: LogEvent, options: AnalyzeOptions) -> None:
    state.parsed_lines += 1
    state.levels[event.level.value] += 1
    state.first_timestamp = (
        event.timestamp
        if state.first_timestamp is None
        else min(state.first_timestamp, event.timestamp)
    )
    state.last_timestamp = (
        event.timestamp
        if state.last_timestamp is None
        else max(state.last_timestamp, event.timestamp)
    )

    bucket = _floor_timestamp(event.timestamp, options.window_minutes)
    if bucket in state.windows:
        state.windows[bucket].total += 1
    elif len(state.windows) < options.max_windows:
        state.windows[bucket] = _Window(total=1)
    else:
        state.dropped_windows += 1

    if event.correlation_id:
        _increment_bounded(state.correlations, event.correlation_id, options.max_correlations)

    if not event.level.is_error:
        return

    state.error_count += 1
    _increment_bounded(state.service_errors, event.service, options.max_services)
    if bucket in state.windows:
        state.windows[bucket].errors += 1

    fingerprint, normalized = fingerprint_message(event.message)
    group = state.groups.get(fingerprint)
    if group is not None:
        group.count += 1
        group.services[event.service] += 1
        group.first_seen = min(group.first_seen, event.timestamp)
        group.last_seen = max(group.last_seen, event.timestamp)
        masked_example = mask_text(event.message)
        if masked_example not in group.examples and len(group.examples) < 3:
            group.examples.append(masked_example)
    elif len(state.groups) < options.max_error_groups:
        state.groups[fingerprint] = _MutableErrorGroup(
            fingerprint=fingerprint,
            normalized_message=normalized,
            count=1,
            examples=[mask_text(event.message)],
            services=Counter({event.service: 1}),
            first_seen=event.timestamp,
            last_seen=event.timestamp,
        )
    else:
        state.dropped_error_groups += 1


def _record_issue(state: _State, issue: ParseIssue, limit: int) -> None:
    state.malformed_lines += 1
    if len(state.issues) < limit:
        issue.preview = mask_text(issue.preview)
        state.issues.append(issue)


def _increment_bounded(counter: Counter[str], key: str, capacity: int) -> None:
    if key in counter or len(counter) < capacity:
        counter[key] += 1


def _floor_timestamp(timestamp: datetime, minutes: int) -> datetime:
    utc_timestamp = timestamp.astimezone(UTC)
    discarded = timedelta(
        minutes=utc_timestamp.minute % minutes,
        seconds=utc_timestamp.second,
        microseconds=utc_timestamp.microsecond,
    )
    return utc_timestamp - discarded


def _window_stats(windows: dict[datetime, _Window]) -> list[WindowStat]:
    return [
        WindowStat(
            start=start,
            total=value.total,
            errors=value.errors,
            error_rate=_ratio(value.errors, value.total),
        )
        for start, value in sorted(windows.items())
    ]


def _detect_bursts(windows: list[WindowStat], threshold: int) -> list[Anomaly]:
    return [
        Anomaly(
            start=window.start,
            errors=window.errors,
            score=float(window.errors),
            reason=f"error count reached configured threshold ({threshold})",
        )
        for window in windows
        if window.errors >= threshold
    ]


def _detect_anomalies(windows: list[WindowStat], threshold: float) -> list[Anomaly]:
    if len(windows) < 6:
        return []
    values = [window.errors for window in windows]
    mean = statistics.fmean(values)
    deviation = statistics.pstdev(values)
    if math.isclose(deviation, 0.0):
        return []
    detected: list[Anomaly] = []
    for window in windows:
        score = (window.errors - mean) / deviation
        if score >= threshold:
            detected.append(
                Anomaly(
                    start=window.start,
                    errors=window.errors,
                    score=round(score, 3),
                    reason=f"error count is {score:.2f} standard deviations above the mean",
                )
            )
    return detected


def _top_error_groups(groups: dict[str, _MutableErrorGroup], limit: int) -> list[ErrorGroup]:
    selected = sorted(groups.values(), key=lambda item: (-item.count, item.fingerprint))[:limit]
    return [
        ErrorGroup(
            fingerprint=item.fingerprint,
            normalized_message=item.normalized_message,
            count=item.count,
            examples=item.examples,
            services=dict(item.services.most_common()),
            first_seen=item.first_seen,
            last_seen=item.last_seen,
        )
        for item in selected
    ]


def _period_summary(report: AnalysisReport) -> PeriodSummary:
    return PeriodSummary(
        files=report.files,
        total=report.parsed_lines,
        errors=report.error_count,
        error_rate=report.error_rate,
        top_error_fingerprints=[item.fingerprint for item in report.top_errors],
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
