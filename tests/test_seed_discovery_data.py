"""Ensure the discovery seeding CLI command populates tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from signal_harvester.cli.core import app


def test_seed_discovery_data_creates_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "discoveries.db"
    cfg_path = tmp_path / "settings.yaml"
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

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(cfg_path), "seed-discovery-data"])
    assert result.exit_code == 0, result.stdout

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM artifacts;")
        artifacts_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM topics;")
        topics_count = cur.fetchone()[0]
    finally:
        conn.close()

    assert artifacts_count >= 1
    assert topics_count >= 1
