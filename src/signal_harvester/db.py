from __future__ import annotations

import os
import sqlite3
from typing import Any

from .logger import get_logger
from .utils import utc_now_iso

log = get_logger(__name__)


def ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def connect(db_path: str) -> sqlite3.Connection:
    ensure_dir(db_path)
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                source TEXT DEFAULT 'x',
                query_names TEXT,
                text TEXT,
                author_id TEXT,
                author_username TEXT,
                created_at TEXT,
                lang TEXT,
                like_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                quote_count INTEGER DEFAULT 0,
                category TEXT,
                sentiment TEXT,
                urgency INTEGER,
                tags TEXT, -- JSON array
                reasoning TEXT,
                salience REAL,
                notified_at TEXT,
                raw_json TEXT,
                inserted_at TEXT,
                updated_at TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_salience ON tweets(salience);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_notified ON tweets(notified_at);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cursors (
                name TEXT PRIMARY KEY,
                since_id TEXT,
                updated_at TEXT
            );
            """
        )
    conn.close()
    log.info("Database initialized at %s", db_path)


def get_cursor(db_path: str, name: str) -> str | None:
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT since_id FROM cursors WHERE name = ?;", (name,))
        row = cur.fetchone()
        return row["since_id"] if row else None
    finally:
        conn.close()


def set_cursor(db_path: str, name: str, since_id: str | None) -> None:
    if not since_id:
        return
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO cursors (name, since_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  since_id=excluded.since_id,
                  updated_at=excluded.updated_at;
                """,
                (name, since_id, now),
            )
    finally:
        conn.close()


def _merge_query_name(existing: str | None, new_name: str | None) -> str:
    existing = (existing or "").strip()
    new_name = (new_name or "").strip()
    if not new_name:
        return existing
    if not existing:
        return new_name
    names = {n.strip() for n in existing.split(",") if n.strip()}
    names.add(new_name)
    return ",".join(sorted(names))


def upsert_tweet(db_path: str, row: dict[str, Any], query_name: str | None = None) -> bool:
    """
    Insert or update a tweet record. Returns True if inserted, False if updated.
    row keys expected:
      tweet_id, text, author_id, author_username, created_at, lang,
      like_count, retweet_count, reply_count, quote_count, raw_json
    """
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        inserted = False
        # Try insert or ignore to detect "new"
        with conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO tweets (
                    tweet_id, source, query_names, text, author_id, author_username, created_at, lang,
                    like_count, retweet_count, reply_count, quote_count, raw_json, inserted_at, updated_at
                ) VALUES (?, 'x', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    row.get("tweet_id"),
                    (query_name or None),
                    row.get("text"),
                    row.get("author_id"),
                    row.get("author_username"),
                    row.get("created_at"),
                    row.get("lang"),
                    int(row.get("like_count") or 0),
                    int(row.get("retweet_count") or 0),
                    int(row.get("reply_count") or 0),
                    int(row.get("quote_count") or 0),
                    row.get("raw_json"),
                    now,
                    now,
                ),
            )
            inserted = cur.rowcount == 1

            # Update metrics and query_names regardless
            existing_names = None
            cur2 = conn.execute("SELECT query_names FROM tweets WHERE tweet_id = ?;", (row.get("tweet_id"),))
            r = cur2.fetchone()
            if r:
                existing_names = r["query_names"]

            merged_names = _merge_query_name(existing_names, query_name)

            conn.execute(
                """
                UPDATE tweets SET
                  text=COALESCE(?, text),
                  author_id=COALESCE(?, author_id),
                  author_username=COALESCE(?, author_username),
                  created_at=COALESCE(?, created_at),
                  lang=COALESCE(?, lang),
                  like_count=MAX(?, like_count),
                  retweet_count=MAX(?, retweet_count),
                  reply_count=MAX(?, reply_count),
                  quote_count=MAX(?, quote_count),
                  raw_json=COALESCE(?, raw_json),
                  query_names=?,
                  updated_at=?
                WHERE tweet_id=?;
                """,
                (
                    row.get("text"),
                    row.get("author_id"),
                    row.get("author_username"),
                    row.get("created_at"),
                    row.get("lang"),
                    int(row.get("like_count") or 0),
                    int(row.get("retweet_count") or 0),
                    int(row.get("reply_count") or 0),
                    int(row.get("quote_count") or 0),
                    row.get("raw_json"),
                    merged_names,
                    now,
                    row.get("tweet_id"),
                ),
            )
        return inserted
    finally:
        conn.close()


def list_unanalyzed(db_path: str, limit: int = 200) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT * FROM tweets
            WHERE category IS NULL OR sentiment IS NULL OR urgency IS NULL
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (int(limit or 200),),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_analysis(
    db_path: str,
    tweet_id: str,
    category: str,
    sentiment: str,
    urgency: int,
    tags_json: str,
    reasoning: str,
) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE tweets
                SET category=?, sentiment=?, urgency=?, tags=?, reasoning=?, updated_at=?
                WHERE tweet_id=?;
                """,
                (category, sentiment, int(urgency or 0), tags_json, reasoning, now, tweet_id),
            )
    finally:
        conn.close()


def list_unscored(db_path: str, limit: int = 500) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT * FROM tweets
            WHERE salience IS NULL AND category IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (int(limit or 500),),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_salience(db_path: str, tweet_id: str, salience: float) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE tweets SET salience=?, updated_at=? WHERE tweet_id=?;",
                (float(salience), now, tweet_id)
            )
    finally:
        conn.close()


def list_for_notification(
    db_path: str,
    threshold: float = 80.0,
    limit: int = 10,
    hours: int | None = None,
) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        params: list[Any] = [float(threshold)]
        where = "salience >= ? AND notified_at IS NULL"
        if hours and hours > 0:
            # Since created_at stored ISO, string comparison works for UTC ISO timestamps
            from datetime import datetime, timedelta, timezone

            cutoff = (
            (datetime.now(tz=timezone.utc) - timedelta(hours=hours))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
            where += " AND created_at >= ?"
            params.append(cutoff)
        sql = f"""
            SELECT * FROM tweets
            WHERE {where}
            ORDER BY salience DESC, created_at DESC
            LIMIT ?;
        """
        params.append(int(limit or 10))
        cur = conn.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_notified(db_path: str, tweet_id: str) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE tweets SET notified_at=? WHERE tweet_id=?;", (now, tweet_id))
    finally:
        conn.close()


def list_top(
    db_path: str,
    limit: int = 50,
    min_salience: float = 0.0,
    hours: int | None = None,
) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        params: list[Any] = [float(min_salience)]
        where = "salience >= ?"
        if hours and hours > 0:
            from datetime import datetime, timedelta, timezone

            cutoff = (
            (datetime.now(tz=timezone.utc) - timedelta(hours=hours))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
            where += " AND created_at >= ?"
            params.append(cutoff)
        sql = f"""
            SELECT * FROM tweets
            WHERE {where}
            ORDER BY salience DESC, created_at DESC
            LIMIT ?;
        """
        params.append(int(limit or 50))
        cur = conn.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_tweet(db_path: str, tweet_id: str) -> dict[str, Any] | None:
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM tweets WHERE tweet_id = ?;", (tweet_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_db_metadata() -> None:
    """Return SQLAlchemy metadata for alembic migrations.
    
    Since we use raw SQLite, we return None and use manual migrations.
    """
    return None


def get_schema_version(db_path: str) -> int:
    """Get current schema version."""
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;")
        row = cur.fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist, version 0
        return 0
    finally:
        conn.close()


def set_schema_version(db_path: str, version: int) -> None:
    """Set schema version."""
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?);",
                (version, utc_now_iso())
            )
    finally:
        conn.close()


def run_migrations(db_path: str) -> None:
    """Run database migrations."""
    current_version = get_schema_version(db_path)
    log.info("Current database schema version: %d", current_version)
    
    # Migration 1: Add indexes for performance
    if current_version < 1:
        log.info("Applying migration 1: Adding performance indexes")
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_category ON tweets(category);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_sentiment ON tweets(sentiment);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author_username);")
            set_schema_version(db_path, 1)
            log.info("Migration 1 applied successfully")
        finally:
            conn.close()
    
    # Migration 2: Add performance metrics table
    if current_version < 2:
        log.info("Applying migration 2: Adding performance metrics table")
        conn = connect(db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        recorded_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON performance_metrics(metric_name);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_recorded ON performance_metrics(recorded_at);")
            set_schema_version(db_path, 2)
            log.info("Migration 2 applied successfully")
        finally:
            conn.close()
    
    log.info("Database migrations complete. Schema version: %d", get_schema_version(db_path))
