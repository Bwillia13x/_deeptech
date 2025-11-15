from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, List

import pytest

from signal_harvester import db


class RecordingConnection:
    """Fake database connection that records executed SQL statements."""

    def __init__(self, bucket: list[str]):
        self._bucket = bucket

    def __enter__(self) -> RecordingConnection:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # pragma: no cover - no cleanup needed
        return None

    def execute(self, sql: str, params: tuple | None = None):  # noqa: D401 - mimic sqlite interface
        normalized = " ".join(sql.split())
        self._bucket.append(normalized)
        return SimpleNamespace(rowcount=0)

    def close(self) -> None:
        return None


@pytest.fixture(name="capture_sql")
def capture_sql_fixture(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], List[str]]:
    """Return a helper that runs migrations and captures emitted SQL for a DB URL."""

    def _runner(db_url: str) -> list[str]:
        executed: list[str] = []

        def fake_connect(_db_path: str) -> RecordingConnection:
            return RecordingConnection(executed)

        monkeypatch.setattr(db, "connect", fake_connect)
        monkeypatch.setattr(db, "get_schema_version", lambda _path: 0)
        monkeypatch.setattr(db, "set_schema_version", lambda *_args, **_kwargs: None)

        db.run_migrations(db_url)
        return executed

    return _runner


def _find_create_statement(statements: list[str], table_name: str) -> str:
    needle = f"CREATE TABLE IF NOT EXISTS {table_name}"
    for sql in statements:
        if needle in sql:
            return sql
    raise AssertionError(f"No CREATE TABLE statement recorded for {table_name}")


def test_postgres_schema_promotes_foreign_keys_to_bigint(capture_sql: Callable[[str], List[str]]):
    statements = capture_sql("postgresql://example-host/signal_harvester_test")

    accounts_sql = _find_create_statement(statements, "accounts")
    assert "entity_id BIGINT NOT NULL" in accounts_sql

    artifact_topics_sql = _find_create_statement(statements, "artifact_topics")
    assert "artifact_id BIGINT NOT NULL" in artifact_topics_sql
    assert "topic_id BIGINT NOT NULL" in artifact_topics_sql

    scores_sql = _find_create_statement(statements, "scores")
    assert "artifact_id BIGINT PRIMARY KEY" in scores_sql

    relationships_sql = _find_create_statement(statements, "artifact_relationships")
    assert "source_artifact_id BIGINT NOT NULL" in relationships_sql
    assert "target_artifact_id BIGINT NOT NULL" in relationships_sql


def test_sqlite_schema_reuses_integer_foreign_keys(capture_sql: Callable[[str], List[str]]):
    statements = capture_sql("sqlite:////tmp/test.db")

    experiment_runs_sql = _find_create_statement(statements, "experiment_runs")
    assert "experiment_id INTEGER NOT NULL" in experiment_runs_sql

    discovery_labels_sql = _find_create_statement(statements, "discovery_labels")
    assert "artifact_id INTEGER NOT NULL" in discovery_labels_sql

    scores_sql = _find_create_statement(statements, "scores")
    assert "artifact_id INTEGER PRIMARY KEY" in scores_sql
