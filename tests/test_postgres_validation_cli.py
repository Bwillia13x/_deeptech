"""CLI coverage for harvest verify-postgres."""

from __future__ import annotations

from typer.testing import CliRunner

from signal_harvester.cli.core import app
from signal_harvester.postgres_validation import ValidationResult


def _cli_result(**overrides):
	result = ValidationResult(
		database_url="postgresql://example",
		connected=True,
		version_string="PostgreSQL 16.1",
		tables=[
			"accounts",
			"artifact_classifications",
			"artifact_relationships",
			"artifact_topics",
			"artifacts",
			"cursors",
			"discovery_labels",
			"entities",
			"experiment_runs",
			"experiments",
			"performance_metrics",
			"schema_version",
			"scores",
			"snapshots",
			"topic_clusters",
			"topic_evolution",
			"topic_similarity",
			"topics",
			"tweets",
		],
		missing_tables=[],
		artifacts_index_count=3,
		row_counts={"tweets": 1},
		schema_version=4,
	)
	for key, value in overrides.items():
		setattr(result, key, value)
	return result


def test_verify_postgres_command_success(monkeypatch) -> None:
	runner = CliRunner()
	monkeypatch.setattr(
		"signal_harvester.cli.core.run_postgres_validation",
		lambda url: _cli_result(),
	)

	output = runner.invoke(app, ["verify-postgres", "--database-url", "postgresql://example"]).stdout

	assert "SUCCESS" in output


def test_verify_postgres_command_missing_tables(monkeypatch) -> None:
	runner = CliRunner()
	monkeypatch.setattr(
		"signal_harvester.cli.core.run_postgres_validation",
		lambda url: _cli_result(missing_tables=["topics"], tables=["tweets"]),
	)

	result = runner.invoke(app, ["verify-postgres", "--database-url", "postgresql://example"])

	assert result.exit_code == 1
	assert "Missing tables" in result.stdout
