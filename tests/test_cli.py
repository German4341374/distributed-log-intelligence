from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from distributed_log_intelligence.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_analyze_command_writes_report(jsonl_log: Path, tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = runner.invoke(app, ["analyze", str(jsonl_log), "--output", str(output)])
    assert result.exit_code == 0
    assert output.is_file()
    assert "Parsed lines" in result.stdout


def test_analyze_fail_on_malformed(plain_log: Path) -> None:
    result = runner.invoke(app, ["analyze", str(plain_log), "--fail-on-malformed"])
    assert result.exit_code == 1


def test_validate_command_exit_codes(plain_log: Path, jsonl_log: Path) -> None:
    invalid = runner.invoke(app, ["validate", str(plain_log)])
    valid = runner.invoke(app, ["validate", str(jsonl_log)])
    assert invalid.exit_code == 1
    assert valid.exit_code == 0


def test_trace_missing_returns_one(jsonl_log: Path) -> None:
    result = runner.invoke(app, ["trace", "missing", str(jsonl_log)])
    assert result.exit_code == 1


def test_generate_and_redact_commands(tmp_path: Path) -> None:
    demo = tmp_path / "demo.jsonl"
    redacted = tmp_path / "redacted.jsonl"
    generated = runner.invoke(app, ["generate-demo", str(demo), "--lines", "20"])
    masked = runner.invoke(app, ["redact", str(demo), str(redacted)])
    assert generated.exit_code == 0
    assert masked.exit_code == 0
    assert redacted.is_file()


def test_compare_requires_current(jsonl_log: Path) -> None:
    result = runner.invoke(app, ["compare", str(jsonl_log)])
    assert result.exit_code != 0


def test_input_error_uses_exit_code_two(tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(tmp_path / "missing.log")])
    assert result.exit_code == 2
    assert "Error:" in result.stdout
