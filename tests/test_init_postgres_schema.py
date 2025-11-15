from __future__ import annotations

import types

import pytest

from scripts import init_postgres_schema


class DummyConnection:
    def __init__(self, bucket: list[str]):
        self.bucket = bucket
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 - match DB API signature
        return False

    def execute(self, sql: str):
        self.bucket.append(sql)
        return types.SimpleNamespace(fetchone=lambda: (1,))

    def close(self):
        self.closed = True


def test_init_postgres_schema_runs_migrations(monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []
    connection = DummyConnection(executed)
    captured_version: dict[str, int] = {}

    monkeypatch.setattr(init_postgres_schema.db_module, "connect", lambda url: connection)
    monkeypatch.setattr(init_postgres_schema.db_module, "run_migrations", lambda url: captured_version.setdefault("ran", 1))
    monkeypatch.setattr(init_postgres_schema.db_module, "get_schema_version", lambda url: 7)

    init_postgres_schema.init_postgres_schema("postgresql://user:pass@localhost/db")

    assert executed == ["SELECT 1;"]
    assert connection.closed is True
    assert captured_version["ran"] == 1


def test_init_postgres_schema_dry_run_skips_migrations(monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []
    connection = DummyConnection(executed)

    monkeypatch.setattr(init_postgres_schema.db_module, "connect", lambda url: connection)

    run_called: dict[str, bool] = {"ran": False}

    def _run_migrations(_url: str) -> None:
        run_called["ran"] = True

    monkeypatch.setattr(init_postgres_schema.db_module, "run_migrations", _run_migrations)

    init_postgres_schema.init_postgres_schema("postgresql://host/db", dry_run=True)

    assert executed == ["SELECT 1;"]
    assert run_called["ran"] is False


def test_init_postgres_schema_rejects_sqlite():
    with pytest.raises(ValueError):
        init_postgres_schema.init_postgres_schema("sqlite:///var/test.db")
