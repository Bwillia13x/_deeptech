"""Validate the discovery backtest CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from signal_harvester.cli.core import app


def _write_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "settings.yaml"
    db_path = tmp_path / "discoveries.db"
    cfg_path.write_text(
        f"""
app:
  database_path: "{db_path}"
  fetch:
    max_results: 10
  llm:
    provider: dummy

queries: []
"""
    )
    return cfg_path


def test_backtest_reports_summary(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)

    seed = runner.invoke(app, ["--config", str(cfg_path), "seed-discovery-data"])
    assert seed.exit_code == 0, seed.stdout

    backtest = runner.invoke(
        app,
        ["--config", str(cfg_path), "backtest", "--days", "2", "--min-score", "0"],
    )
    assert backtest.exit_code == 0, backtest.stdout
    assert "Backtest summary" in backtest.stdout
