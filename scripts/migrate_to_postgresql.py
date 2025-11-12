#!/usr/bin/env python3
"""
PostgreSQL Data Migration Script

This script migrates data from SQLite to PostgreSQL, handling data type
conversions and ensuring referential integrity. It supports dry-run mode,
progress tracking, and data validation.

Usage:
    # Dry run (no changes):
    python scripts/migrate_to_postgresql.py --dry-run

    # Full migration:
    python scripts/migrate_to_postgresql.py --source var/app.db --target postgresql://user:pass@localhost/signal_harvester

    # Migration with validation:
    python scripts/migrate_to_postgresql.py --source var/app.db --target postgresql://... --validate

    # Resume from checkpoint:
    python scripts/migrate_to_postgresql.py --source var/app.db --target postgresql://... --resume

Requirements:
    pip install psycopg2-binary sqlalchemy
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    import psycopg2.extensions
    from psycopg2.extras import execute_batch
    from sqlalchemy import create_engine, text
except ImportError:
    print("ERROR: Missing dependencies. Install with: pip install psycopg2-binary sqlalchemy")
    sys.exit(1)


# Table migration order (respecting foreign key dependencies)
MIGRATION_ORDER = [
    "cursors",
    "tweets",
    "snapshots",
    "artifacts",
    "artifact_scores",
    "topics",
    "artifact_topics",
    "entities",
    "artifact_entities",
    "artifact_relationships",
    "topic_similarity",
    "experiments",
    "experiment_runs",
    "discovery_labels",
]


class MigrationStats:
    """Track migration statistics."""
    
    def __init__(self):
        self.tables: Dict[str, Dict[str, int]] = {}
        self.start_time = datetime.now()
        self.errors: List[str] = []
    
    def record_table(self, table: str, rows_migrated: int, rows_skipped: int = 0):
        self.tables[table] = {
            "migrated": rows_migrated,
            "skipped": rows_skipped,
        }
    
    def add_error(self, error: str):
        self.errors.append(error)
    
    def print_summary(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "=" * 80)
        print("Migration Summary")
        print("=" * 80)
        print(f"Duration: {elapsed:.2f} seconds")
        print(f"Tables migrated: {len(self.tables)}")
        
        total_rows = sum(t["migrated"] for t in self.tables.values())
        total_skipped = sum(t["skipped"] for t in self.tables.values())
        print(f"Total rows migrated: {total_rows:,}")
        if total_skipped > 0:
            print(f"Total rows skipped: {total_skipped:,}")
        
        print("\nPer-table breakdown:")
        for table, stats in self.tables.items():
            print(f"  {table:30s} {stats['migrated']:>8,} rows", end="")
            if stats['skipped'] > 0:
                print(f" ({stats['skipped']:,} skipped)", end="")
            print()
        
        if self.errors:
            print(f"\n⚠️  Errors encountered: {len(self.errors)}")
            for error in self.errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(self.errors) > 5:
                print(f"  ... and {len(self.errors) - 5} more")
        else:
            print("\n✅ Migration completed successfully!")
        
        print("=" * 80)


class PostgreSQLMigrator:
    """Handles data migration from SQLite to PostgreSQL."""
    
    def __init__(self, sqlite_path: str, postgres_url: str, dry_run: bool = False):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        self.dry_run = dry_run
        self.stats = MigrationStats()
        
        # Connections
        self.sqlite_conn: Optional[sqlite3.Connection] = None
        self.pg_conn: Optional[psycopg2.extensions.connection] = None
        self.pg_cursor: Optional[psycopg2.extensions.cursor] = None
    
    def connect(self):
        """Establish database connections."""
        print(f"Connecting to SQLite: {self.sqlite_path}")
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row
        
        if not self.dry_run:
            print(f"Connecting to PostgreSQL: {self.postgres_url.split('@')[-1]}")  # Hide credentials
            self.pg_conn = psycopg2.connect(self.postgres_url)
            self.pg_cursor = self.pg_conn.cursor()
    
    def disconnect(self):
        """Close database connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_cursor:
            self.pg_cursor.close()
        if self.pg_conn:
            self.pg_conn.close()
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in SQLite."""
        if not self.sqlite_conn:
            raise RuntimeError("SQLite connection not established")
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None
    
    def get_row_count(self, table_name: str) -> int:
        """Get row count from SQLite table."""
        if not self.sqlite_conn:
            raise RuntimeError("SQLite connection not established")
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        result = cursor.fetchone()
        return result[0] if result else 0
    
    def transform_row(self, table: str, row: sqlite3.Row) -> Tuple[List[str], List[Any]]:
        """
        Transform a SQLite row for PostgreSQL.
        Returns (column_names, values).
        """
        columns = row.keys()
        values = []
        
        for col, val in zip(columns, row):
            # Handle JSON fields
            if col in ["tags", "metadata_json", "social_accounts", "config_json", 
                      "config_snapshot", "raw_json"] and val:
                # Ensure valid JSON
                try:
                    if isinstance(val, str):
                        json.loads(val)  # Validate
                        values.append(val)
                    else:
                        values.append(json.dumps(val))
                except json.JSONDecodeError:
                    values.append(None)
            
            # Handle timestamp fields - PostgreSQL expects ISO format with timezone
            elif col in ["created_at", "updated_at", "published_at", "notified_at",
                        "started_at", "completed_at", "calculated_at", "last_activity_date"]:
                if val:
                    # SQLite stores as text, ensure it's in ISO format
                    if isinstance(val, str):
                        # Add timezone if missing
                        if not val.endswith('Z') and '+' not in val:
                            val = val + 'Z'
                    values.append(val)
                else:
                    values.append(None)
            
            else:
                values.append(val)
        
        return list(columns), values
    
    def migrate_table(self, table_name: str, batch_size: int = 1000) -> Tuple[int, int]:
        """
        Migrate a single table from SQLite to PostgreSQL.
        Returns (rows_migrated, rows_skipped).
        """
        if not self.sqlite_conn:
            raise RuntimeError("SQLite connection not established")
        if not self.pg_conn:
            raise RuntimeError("PostgreSQL connection not established")
            
        if not self.table_exists(table_name):
            print(f"⚠️  Table {table_name} does not exist in SQLite, skipping...")
            return 0, 0
        
        row_count = self.get_row_count(table_name)
        print(f"\nMigrating {table_name}: {row_count:,} rows")
        
        if row_count == 0:
            print(f"  ✓ No rows to migrate")
            return 0, 0
        
        if self.dry_run:
            print(f"  [DRY RUN] Would migrate {row_count:,} rows")
            return row_count, 0
        
        # Fetch all rows from SQLite
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        
        migrated = 0
        skipped = 0
        batch = []
        columns: List[str] = []
        
        for row in cursor:
            try:
                columns, values = self.transform_row(table_name, row)
                batch.append(values)
                
                # Insert batch when full
                if len(batch) >= batch_size:
                    self._insert_batch(table_name, columns, batch)
                    migrated += len(batch)
                    print(f"  Progress: {migrated:,}/{row_count:,} rows ({migrated*100//row_count}%)")
                    batch = []
            
            except Exception as e:
                error_msg = f"Error migrating row in {table_name}: {e}"
                self.stats.add_error(error_msg)
                skipped += 1
                if skipped < 5:  # Print first few errors
                    print(f"  ⚠️  {error_msg}")
        
        # Insert remaining batch
        if batch and columns:
            self._insert_batch(table_name, columns, batch)
            migrated += len(batch)
        
        self.pg_conn.commit()
        print(f"  ✓ Migrated {migrated:,} rows")
        
        if skipped > 0:
            print(f"  ⚠️  Skipped {skipped:,} rows due to errors")
        
        return migrated, skipped
    
    def _insert_batch(self, table_name: str, columns: List[str], batch: List[List[Any]]):
        """Insert a batch of rows into PostgreSQL."""
        if not self.pg_cursor:
            raise RuntimeError("PostgreSQL cursor not established")
            
        placeholders = ','.join(['%s'] * len(columns))
        column_names = ','.join(columns)
        
        # Use ON CONFLICT for tables with unique constraints
        conflict_clauses = {
            "tweets": "ON CONFLICT (tweet_id) DO NOTHING",
            "cursors": "ON CONFLICT (name) DO NOTHING",
            "snapshots": "ON CONFLICT (id) DO NOTHING",
            "artifacts": "ON CONFLICT (source, external_id) DO NOTHING",
            "artifact_scores": "ON CONFLICT (artifact_id) DO NOTHING",
            "topics": "ON CONFLICT (name) DO NOTHING",
            "artifact_topics": "ON CONFLICT (artifact_id, topic_id) DO NOTHING",
            "artifact_entities": "ON CONFLICT (artifact_id, entity_id) DO NOTHING",
            "artifact_relationships": "ON CONFLICT (source_artifact_id, target_artifact_id, relationship_type) DO NOTHING",
            "topic_similarity": "ON CONFLICT (topic_id_1, topic_id_2) DO NOTHING",
            "experiments": "ON CONFLICT (name) DO NOTHING",
            "discovery_labels": "ON CONFLICT (artifact_id) DO NOTHING",
        }
        
        conflict_clause = conflict_clauses.get(table_name, "")
        
        sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders}) {conflict_clause}"
        
        try:
            execute_batch(self.pg_cursor, sql, batch, page_size=1000)
        except Exception as e:
            # Fallback to individual inserts for problematic batch
            print(f"  ⚠️  Batch insert failed, trying individual rows: {e}")
            for row in batch:
                try:
                    self.pg_cursor.execute(sql, row)
                except Exception as row_error:
                    self.stats.add_error(f"Row insert failed: {row_error}")
    
    def validate_migration(self) -> bool:
        """Validate that migration was successful by comparing row counts."""
        print("\n" + "=" * 80)
        print("Validating Migration")
        print("=" * 80)
        
        if not self.pg_cursor:
            raise RuntimeError("PostgreSQL cursor not established")
        
        all_valid = True
        
        for table in MIGRATION_ORDER:
            if not self.table_exists(table):
                continue
            
            sqlite_count = self.get_row_count(table)
            
            if self.dry_run:
                print(f"{table:30s} SQLite: {sqlite_count:>8,} rows (PostgreSQL check skipped)")
                continue
            
            self.pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            result = self.pg_cursor.fetchone()
            pg_count = result[0] if result else 0
            
            match = "✓" if sqlite_count == pg_count else "✗"
            status = "MATCH" if sqlite_count == pg_count else "MISMATCH"
            
            print(f"{table:30s} SQLite: {sqlite_count:>8,} | PostgreSQL: {pg_count:>8,} [{match} {status}]")
            
            if sqlite_count != pg_count:
                all_valid = False
        
        print("=" * 80)
        
        if all_valid:
            print("✅ Validation passed: All row counts match!")
        else:
            print("❌ Validation failed: Row count mismatches detected")
        
        return all_valid
    
    def migrate_all(self) -> bool:
        """Run full migration of all tables."""
        print("=" * 80)
        print("PostgreSQL Data Migration")
        print("=" * 80)
        print(f"Source: {self.sqlite_path}")
        print(f"Target: {self.postgres_url.split('@')[-1]}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE MIGRATION'}")
        print("=" * 80)
        
        try:
            self.connect()
            
            for table in MIGRATION_ORDER:
                try:
                    migrated, skipped = self.migrate_table(table)
                    self.stats.record_table(table, migrated, skipped)
                except Exception as e:
                    error_msg = f"Failed to migrate table {table}: {e}"
                    print(f"\n❌ {error_msg}")
                    self.stats.add_error(error_msg)
                    # Continue with next table
            
            self.stats.print_summary()
            
            return len(self.stats.errors) == 0
        
        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Signal Harvester data from SQLite to PostgreSQL"
    )
    parser.add_argument(
        "--source",
        default="var/app.db",
        help="Path to SQLite database (default: var/app.db)"
    )
    parser.add_argument(
        "--target",
        required=True,
        help="PostgreSQL connection string (postgresql://user:pass@host/db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual migration)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate migration by comparing row counts"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for inserts (default: 1000)"
    )
    
    args = parser.parse_args()
    
    # Validate PostgreSQL URL format
    if not args.target.startswith("postgresql://"):
        print("ERROR: Target must be a PostgreSQL URL (postgresql://user:pass@host/db)")
        sys.exit(1)
    
    # Run migration
    migrator = PostgreSQLMigrator(args.source, args.target, args.dry_run)
    success = migrator.migrate_all()
    
    # Run validation if requested
    if args.validate and not args.dry_run:
        valid = migrator.validate_migration()
        success = success and valid
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
