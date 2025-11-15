"""Tests for the PostgreSQL validation helpers."""

from __future__ import annotations

from rich.console import Console

from signal_harvester import postgres_validation as pv


def _build_result(**overrides):
    base = pv.ValidationResult(
        database_url="postgresql://example",
        connected=True,
        version_string="PostgreSQL 16.1",
        tables=list(pv.EXPECTED_TABLES),
        missing_tables=[],
        artifacts_index_count=4,
        row_counts={"tweets": 2, "artifacts": 5, "experiments": 1},
        schema_version=7,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_obfuscate_password_masks_secret() -> None:
    url = "postgresql://user:supersecret@example.com:5432/db"
    masked = pv.obfuscate_password(url)
    assert "supersecret" not in masked
    assert "user:***@example.com" in masked


def test_validate_postgresql_success(monkeypatch) -> None:
    console = Console(record=True, width=120)
    monkeypatch.setattr(pv, "run_postgres_validation", lambda url: _build_result())

    ok = pv.validate_postgresql("postgresql://example", console=console)

    assert ok is True
    assert "SUCCESS" in console.export_text()


def test_validate_postgresql_missing_tables(monkeypatch) -> None:
    console = Console(record=True, width=120)
    result = _build_result(missing_tables=["topics"], tables=list(pv.EXPECTED_TABLES[:-1]))
    monkeypatch.setattr(pv, "run_postgres_validation", lambda url: result)

    ok = pv.validate_postgresql("postgresql://example", console=console)

    assert ok is False
    assert "Missing tables" in console.export_text()
