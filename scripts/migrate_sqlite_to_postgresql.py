#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Script

This script migrates all data from the SQLite database to PostgreSQL,
handling data type conversions, timestamp formatting, and JSON transformations.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
    python scripts/migrate_sqlite_to_postgresql.py --sqlite-path var/app.db
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Register JSON adapter for psycopg2
try:
    import psycopg2.extras
    psycopg2.extras.register_default_jsonb()
except ImportError:
    pass


# Table migration order (respects foreign key constraints)
MIGRATION_ORDER = [
    "alembic_version",
    "beta_users",
    "schema_version",
    "performance_metrics",
    "entities",
    "accounts",
    "topics",
    "artifacts",
    "artifact_topics",
    "tweets",
    "cursors",
    "scores",
    "topic_evolution",
    "topic_similarity",
    "topic_clusters",
    "artifact_classifications",
    "artifact_scores",
    "artifact_relationships",
    "snapshots",
    "experiments",
    "experiment_runs",
    "discovery_labels",
]


def parse_timestamp(value: Any) -> Optional[str]:
    """Parse timestamp from various formats to ISO 8601."""
    if value is None:
        return None
    if isinstance(value, str):
        # Already a string, try to parse and reformat
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.isoformat()
        except ValueError:
            # Try other common formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
            return value  # Return as-is if can't parse
    if isinstance(value, (int, float)):
        # Unix timestamp
        dt = datetime.fromtimestamp(value)
        return dt.isoformat()
    return str(value)


def transform_row(table_name: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Transform row data for PostgreSQL compatibility."""
    transformed = {}
    for key, value in row.items():
        # Handle timestamp fields
        if key.endswith("_at") or key in ["created_at", "updated_at", "published_date"]:
            transformed[key] = parse_timestamp(value)
        # Handle JSON fields (convert to JSON string for psycopg2)
        elif key.endswith("_json") or key in ["metadata", "config", "search_params"]:
            if value is None:
                transformed[key] = None
            elif isinstance(value, str):
                # Already a JSON string, validate it
                try:
                    json.loads(value)
                    transformed[key] = value
                except json.JSONDecodeError:
                    transformed[key] = json.dumps(value)
            elif isinstance(value, (dict, list)):
                # Convert dict/list to JSON string
                transformed[key] = json.dumps(value)
            else:
                transformed[key] = json.dumps(value)
        else:
            transformed[key] = value
    return transformed


def get_table_columns(engine: Engine, table_name: str) -> List[str]:
    """Get list of columns for a table."""
    inspector = sa.inspect(engine)
    if not inspector.has_table(table_name):
        return []
    columns = inspector.get_columns(table_name)
    return [col["name"] for col in columns]


def migrate_table(
    sqlite_engine: Engine,
    pg_engine: Engine,
    table_name: str,
    batch_size: int = 100,
) -> int:
    """Migrate a single table from SQLite to PostgreSQL."""
    print(f"  Migrating table: {table_name}...", end=" ", flush=True)

    # Check if table exists in both databases
    sqlite_cols = get_table_columns(sqlite_engine, table_name)
    pg_cols = get_table_columns(pg_engine, table_name)

    if not sqlite_cols:
        print(f"⚠️  Table does not exist in SQLite, skipping")
        return 0

    if not pg_cols:
        print(f"⚠️  Table does not exist in PostgreSQL, skipping")
        return 0

    # Get common columns
    common_cols = set(sqlite_cols) & set(pg_cols)
    if not common_cols:
        print(f"⚠️  No common columns found, skipping")
        return 0

    column_list = sorted(common_cols)

    # Count rows in SQLite
    with sqlite_engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        total_rows = result.scalar()

    if total_rows == 0:
        print("✓ (0 rows)")
        return 0

    # Read all rows from SQLite
    rows_migrated = 0
    with sqlite_engine.connect() as sqlite_conn:
        # Build query with only common columns
        query = f"SELECT {', '.join(column_list)} FROM {table_name}"
        result = sqlite_conn.execute(text(query))

        batch = []
        for row in result:
            row_dict = dict(zip(column_list, row))
            transformed = transform_row(table_name, row_dict)
            batch.append(transformed)

            if len(batch) >= batch_size:
                # Insert batch into PostgreSQL
                with pg_engine.connect() as pg_conn:
                    _insert_batch(pg_conn, table_name, column_list, batch)
                    pg_conn.commit()
                rows_migrated += len(batch)
                batch = []

        # Insert remaining rows
        if batch:
            with pg_engine.connect() as pg_conn:
                _insert_batch(pg_conn, table_name, column_list, batch)
                pg_conn.commit()
            rows_migrated += len(batch)

    print(f"✓ ({rows_migrated} rows)")
    return rows_migrated


def _insert_batch(
    conn: sa.Connection, table_name: str, columns: List[str], batch: List[Dict[str, Any]]
) -> None:
    """Insert a batch of rows into PostgreSQL."""
    if not batch:
        return

    # Special handling for alembic_version (skip if exists)
    if table_name == "alembic_version":
        print(f"⚠️  Skipping alembic_version (already exists)")
        return

    # Build INSERT query with placeholders
    placeholders = ", ".join([f":{col}" for col in columns])
    query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

    try:
        conn.execute(text(query), batch)
    except Exception as e:
        # If it's a unique constraint violation, try one by one with ON CONFLICT
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            print(f"\n  ⚠️  Duplicate keys detected, using UPSERT...")
            _upsert_batch(conn, table_name, columns, batch)
        else:
            print(f"\n  ❌ Error inserting batch into {table_name}: {e}")
            print(f"  First row: {batch[0]}")
            raise


def _upsert_batch(
    conn: sa.Connection, table_name: str, columns: List[str], batch: List[Dict[str, Any]]
) -> None:
    """Insert batch using ON CONFLICT DO NOTHING for duplicate handling."""
    placeholders = ", ".join([f":{col}" for col in columns])
    query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    for row in batch:
        try:
            conn.execute(text(query), [row])
        except Exception as e:
            print(f"\n  ⚠️  Skipping row due to error: {e}")


def validate_migration(sqlite_engine: Engine, pg_engine: Engine) -> bool:
    """Validate that row counts match between SQLite and PostgreSQL."""
    print("\n📊 Validating migration...")

    all_valid = True
    for table_name in MIGRATION_ORDER:
        sqlite_cols = get_table_columns(sqlite_engine, table_name)
        pg_cols = get_table_columns(pg_engine, table_name)

        if not sqlite_cols or not pg_cols:
            continue

        with sqlite_engine.connect() as sqlite_conn:
            result = sqlite_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            sqlite_count = result.scalar()

        with pg_engine.connect() as pg_conn:
            result = pg_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            pg_count = result.scalar()

        if sqlite_count == pg_count:
            if sqlite_count > 0:
                print(f"  ✓ {table_name}: {pg_count} rows")
        else:
            print(f"  ❌ {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
            all_valid = False

    return all_valid


def main() -> int:
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default="var/app.db",
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL connection URL (or set DATABASE_URL env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of rows to insert per batch",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip post-migration validation",
    )
    args = parser.parse_args()

    # Get database URLs
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"❌ SQLite database not found: {sqlite_path}")
        return 1

    import os

    pg_url = args.database_url or os.environ.get("DATABASE_URL")
    if not pg_url:
        print("❌ PostgreSQL DATABASE_URL not set")
        return 1

    print("🔄 Starting SQLite to PostgreSQL migration...")
    print(f"  Source: {sqlite_path}")
    print(f"  Target: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")

    # Create engines
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    pg_engine = create_engine(pg_url)

    # Migrate tables
    total_rows = 0
    for table_name in MIGRATION_ORDER:
        rows = migrate_table(sqlite_engine, pg_engine, table_name, args.batch_size)
        total_rows += rows

    print(f"\n✅ Migration complete: {total_rows} total rows migrated")

    # Validate
    if not args.skip_validation:
        if validate_migration(sqlite_engine, pg_engine):
            print("\n✅ Validation passed: All row counts match")
        else:
            print("\n❌ Validation failed: Row count mismatches detected")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
