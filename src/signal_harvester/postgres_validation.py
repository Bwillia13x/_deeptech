"""Utilities for validating PostgreSQL schema deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Dict, List
from urllib.parse import urlsplit, urlunsplit

from rich.console import Console
from sqlalchemy import create_engine, inspect, text

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/signal_harvester"
EXPECTED_TABLES: List[str] = [
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
]
ROW_COUNT_TABLES = ("tweets", "artifacts", "experiments")
ARTIFACT_TYPE_EXPECTATIONS = {
    "id": "BIGINT",
    "source": "TEXT",
    "external_id": "VARCHAR",
    "metadata_json": "JSONB",
    "published_at": "TEXT",
    "created_at": "TEXT",
}


@dataclass
class ValidationResult:
    """Structured output for PostgreSQL validation."""

    database_url: str
    connected: bool = False
    version_string: str | None = None
    tables: List[str] = field(default_factory=list)
    missing_tables: List[str] = field(default_factory=list)
    artifacts_index_count: int = 0
    type_mismatches: List[str] = field(default_factory=list)
    row_counts: Dict[str, int] = field(default_factory=dict)
    schema_version: int | None = None
    error: str | None = None


def run_postgres_validation(database_url: str) -> ValidationResult:
    """Collect schema information from PostgreSQL without emitting console output."""

    result = ValidationResult(database_url=database_url)
    try:
        engine = create_engine(database_url, echo=False, future=True)
        inspector = inspect(engine)
        result.tables = sorted(inspector.get_table_names())
        result.missing_tables = [table for table in EXPECTED_TABLES if table not in result.tables]

        with engine.connect() as conn:
            version_row = conn.execute(text("SELECT version()"))
            fetched = version_row.fetchone()
            if fetched:
                result.version_string = str(fetched[0])

            if "artifacts" in result.tables:
                result.artifacts_index_count = len(inspector.get_indexes("artifacts"))
                columns = inspector.get_columns("artifacts")
                column_map = {col["name"]: str(col["type"]).upper() for col in columns}
                for column, expected in ARTIFACT_TYPE_EXPECTATIONS.items():
                    actual = column_map.get(column)
                    if actual and expected not in actual:
                        result.type_mismatches.append(f"{column}: {actual} (expected {expected})")

            for table in ROW_COUNT_TABLES:
                if table in result.tables:
                    count_row = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    row_value = count_row.fetchone()
                    if row_value is not None:
                        result.row_counts[table] = int(row_value[0])

            if "schema_version" in result.tables:
                version_result = conn.execute(text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"))
                schema_row = version_result.fetchone()
                if schema_row:
                    result.schema_version = int(schema_row[0])

        result.connected = True
    except Exception as exc:  # pragma: no cover - exercised via CLI/script tests
        result.error = str(exc)

    return result


def validate_postgresql(
    database_url: str | None = None,
    *,
    console: Console | None = None,
    show_row_counts: bool = True,
) -> bool:
    """Validate PostgreSQL schema and emit a human-readable report."""

    console = console or Console()
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    console.print(f"Connecting to {obfuscate_password(url)}")

    result = run_postgres_validation(url)
    if result.error:
        console.print(f"[red]✗ Validation failed:[/red] {result.error}")
        return False

    if result.version_string:
        console.print(f"✓ Connected to PostgreSQL: {result.version_string[:50]}...")

    console.print(f"\n✓ Found {len(result.tables)} tables:")
    for table in result.tables:
        console.print(f"  - {table}")

    if result.missing_tables:
        console.print(f"\n[red]✗ Missing tables:[/red] {result.missing_tables}")
        return False

    if result.type_mismatches:
        console.print("\n[red]✗ Column type mismatches detected:[/red]")
        for mismatch in result.type_mismatches:
            console.print(f"  - {mismatch}")
        return False

    console.print(f"\n✓ Found {result.artifacts_index_count} indexes on artifacts table")

    if show_row_counts and result.row_counts:
        console.print("\nRow counts:")
        for table in ROW_COUNT_TABLES:
            if table in result.row_counts:
                console.print(f"  - {table}: {result.row_counts[table]} rows")

    if result.schema_version is None:
        console.print("\n[red]✗ schema_version table is empty or missing[/red]")
        return False

    console.print(f"\n✓ Schema version: {result.schema_version}")
    console.rule("PostgreSQL Migration Validation: SUCCESS")
    return True


def obfuscate_password(database_url: str) -> str:
    """Mask the password portion of a database URL."""

    parsed = urlsplit(database_url)
    if "@" not in parsed.netloc:
        return database_url

    creds, host = parsed.netloc.split("@", 1)
    if ":" in creds:
        username, _password = creds.split(":", 1)
        creds = f"{username}:***"
    else:
        creds = f"{creds}:***"

    obfuscated = parsed._replace(netloc=f"{creds}@{host}")
    return urlunsplit(obfuscated)


__all__ = [
    "ARTIFACT_TYPE_EXPECTATIONS",
    "DEFAULT_DATABASE_URL",
    "EXPECTED_TABLES",
    "ValidationResult",
    "obfuscate_password",
    "run_postgres_validation",
    "validate_postgresql",
]
