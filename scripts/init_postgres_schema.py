#!/usr/bin/env python3
"""Bootstrap the PostgreSQL schema using the in-repo migrations."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from signal_harvester import db as db_module  # noqa: E402


def _redact_url(url: str) -> str:
    try:
        parsed: SplitResult = urlsplit(url)
    except ValueError:
        return url
    if not parsed.password:
        return url
    redacted_netloc = parsed.netloc.replace(parsed.password, "***", 1)
    return urlunsplit(parsed._replace(netloc=redacted_netloc))


def init_postgres_schema(database_url: str, *, dry_run: bool = False) -> None:
    """Ensure the PostgreSQL schema exists and is up to date."""

    normalized = db_module._normalize_db_url(database_url)  # noqa: SLF001 - script calls private helper intentionally
    if not db_module._is_postgres_url(normalized):  # noqa: SLF001
        raise ValueError("init_postgres_schema only supports PostgreSQL URLs")

    print(f"Connecting to { _redact_url(normalized) }")
    conn = db_module.connect(normalized)
    try:
        with conn:
            conn.execute("SELECT 1;")
    finally:
        conn.close()
    print("Connection verified")

    if dry_run:
        print("(dry-run) Schema verification complete; skipping migrations.")
        return

    print("Running migrations via signal_harvester.db.run_migrations()")
    db_module.run_migrations(normalized)
    final_version = db_module.get_schema_version(normalized)
    print(f"Schema initialized (version {final_version})")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__ or "Init PostgreSQL schema")
    parser.add_argument(
        "--database-url",
        dest="database_url",
        help="PostgreSQL DSN; falls back to the DATABASE_URL environment variable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify connectivity without mutating the database",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("Provide --database-url or set the DATABASE_URL environment variable")

    try:
        init_postgres_schema(database_url, dry_run=args.dry_run)
    except Exception as exc:  # pragma: no cover - bubble up for exit code & logging
        print(f"Failed to initialize schema: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
