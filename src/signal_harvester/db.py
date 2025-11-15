from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, cast

try:  # Optional PostgreSQL error hints for nicer fallbacks
    from psycopg2 import errors as psycopg2_errors  # type: ignore
except ImportError:  # pragma: no cover - psycopg2 not available in SQLite-only dev
    psycopg2_errors = None

INTEGRITY_ERRORS: tuple[type[Exception], ...]
if psycopg2_errors:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg2_errors.UniqueViolation)  # type: ignore[attr-defined]
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

from .config import DatabaseConfig
from .db_connection import get_database_connection
from .logger import get_logger
from .utils import utc_now_iso

log = get_logger(__name__)


def _row_to_entity(row: Any) -> dict[str, Any]:
    """Normalize entity row with parsed metadata and JSON fields."""
    entity = dict(row)

    metadata_raw = entity.pop("metadata_json", None)
    if metadata_raw:
        try:
            entity["metadata"] = json.loads(metadata_raw)
        except json.JSONDecodeError:
            entity["metadata"] = {}
    else:
        entity["metadata"] = {}

    entity_type = entity.get("entity_type") or entity.get("type")
    if entity_type:
        entity["entity_type"] = entity_type

    json_columns = (
        "impact_metrics",
        "collaboration_network",
        "research_trajectory",
        "expertise_areas",
        "platform_activity",
    )
    for column in json_columns:
        raw_value = entity.get(column)
        if isinstance(raw_value, str) and raw_value:
            try:
                entity[column] = json.loads(raw_value)
            except json.JSONDecodeError:
                continue

    return entity


def _row_to_account(row: Any) -> dict[str, Any]:
    """Normalize account row with parsed metadata fields."""
    account = dict(row)
    raw_json = account.get("raw_json")
    if raw_json:
        try:
            account["metadata"] = json.loads(raw_json)
        except json.JSONDecodeError:
            account["metadata"] = None
    else:
        account["metadata"] = None

    account.setdefault("handle", account.get("handle_or_id"))
    account.setdefault("account_id", account.get("id"))
    return account


def _ensure_lastrowid(rowid: int | None) -> int:
    if rowid is None:
        raise RuntimeError("Database insert did not return a row id")
    return rowid


def _is_missing_table_error(error: Exception) -> bool:
    message = str(error).lower()
    if "no such table" in message or "does not exist" in message:
        return True
    pgcode = getattr(error, "pgcode", None)
    return pgcode == "42P01"



def _normalize_db_url(db_path: str) -> str:
    """Normalize legacy database path to a URL understood by DatabaseConnection."""
    if not db_path:
        raise ValueError("Database path/url must be provided")

    normalized = db_path.strip()

    if normalized.startswith("postgresql://") or normalized.startswith("postgres://"):
        return normalized

    if normalized.startswith("sqlite://"):
        return normalized

    return f"sqlite:///{normalized}"


def _is_postgres_url(db_path: str) -> bool:
    url = _normalize_db_url(db_path)
    return url.startswith("postgresql://") or url.startswith("postgres://")


def _safe_add_column(conn: Any, db_path: str, table: str, column_definition: str) -> None:
    """Add a column to a table, ignoring duplicates in SQLite."""
    if _is_postgres_url(db_path):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_definition};")
        return

    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_definition};")
    except sqlite3.OperationalError as exc:  # pragma: no cover - passthrough for existing columns
        message = str(exc).lower()
        if "duplicate column name" not in message:
            raise


def _serial_primary_key_clause(db_path: str) -> str:
    """Return dialect-appropriate auto increment primary key clause."""
    if _is_postgres_url(db_path):
        return "BIGSERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def _id_column_type(db_path: str) -> str:
    """Return the integer column type compatible with the primary key dialect."""
    return "BIGINT" if _is_postgres_url(db_path) else "INTEGER"


def _insert_and_return_id(
    conn,
    db_path: str,
    sql: str,
    params: tuple[Any, ...],
    returning_column: str = "id",
) -> int:
    """Execute an INSERT and return the generated primary key for both dialects."""
    if _is_postgres_url(db_path):
        trimmed = sql.rstrip().rstrip(";")
        returning_sql = f"{trimmed} RETURNING {returning_column};"
        cur = conn.execute(returning_sql, params)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Insert did not return a row id")
        if isinstance(row, dict):
            value = row[returning_column]
        else:
            try:
                value = row[returning_column]
            except (TypeError, KeyError):
                value = row[0]
        return cast(int, value)
    cur = conn.execute(sql, params)
    return _ensure_lastrowid(cur.lastrowid)


def _topic_paths_agg_expression(db_path: str) -> str:
    """Return a dialect-aware correlated aggregation expression for topic paths."""
    if _is_postgres_url(db_path):
        expr = "string_agg(DISTINCT t.taxonomy_path, ',')"
    else:
        expr = "GROUP_CONCAT(DISTINCT t.taxonomy_path)"
    return (
        "(SELECT COALESCE("
        f"{expr}, '') "
        "FROM artifact_topics at2 "
        "JOIN topics t ON at2.topic_id = t.id "
        "WHERE at2.artifact_id = a.id) AS topic_paths"
    )


def connect(db_path: str):
    url = _normalize_db_url(db_path)
    config = DatabaseConfig(url=url)
    return get_database_connection(config)


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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'processing',
                size_kb INTEGER,
                file_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (signal_id) REFERENCES tweets(tweet_id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_signal_id ON snapshots(signal_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_status ON snapshots(status);")

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
        # Try insert with ON CONFLICT to detect "new"
        with conn:
            cur = conn.execute(
                """
                INSERT INTO tweets (
                    tweet_id, source, query_names, text, author_id, author_username, created_at, lang,
                    like_count, retweet_count, reply_count, quote_count, raw_json, inserted_at, updated_at
                ) VALUES (?, 'x', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tweet_id) DO NOTHING;
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
                  like_count=CASE WHEN ? >= COALESCE(like_count, -1) THEN ? ELSE like_count END,
                  retweet_count=CASE WHEN ? >= COALESCE(retweet_count, -1) THEN ? ELSE retweet_count END,
                  reply_count=CASE WHEN ? >= COALESCE(reply_count, -1) THEN ? ELSE reply_count END,
                  quote_count=CASE WHEN ? >= COALESCE(quote_count, -1) THEN ? ELSE quote_count END,
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
                    int(row.get("like_count") or 0),
                    int(row.get("retweet_count") or 0),
                    int(row.get("retweet_count") or 0),
                    int(row.get("reply_count") or 0),
                    int(row.get("reply_count") or 0),
                    int(row.get("quote_count") or 0),
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
    """Get current schema version for SQLite or PostgreSQL rows."""
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;")
        row = cur.fetchone()
        if not row:
            return 0
        if isinstance(row, dict):
            value = row.get("version")
            if value is not None:
                return int(value)
            # Fallback: grab first value if dict implementation differs
            return int(next(iter(row.values())))
        return int(row[0])
    except Exception as exc:  # pragma: no cover - relies on engine-specific errors
        if _is_missing_table_error(exc):
            return 0
        raise
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
                """
                INSERT INTO schema_version (version, applied_at)
                VALUES (?, ?)
                ON CONFLICT(version) DO UPDATE SET applied_at = excluded.applied_at;
                """,
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
                pk_clause = _serial_primary_key_clause(db_path)
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id {pk_clause},
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
    
    
    # Migration 3: Phase One - Deep Tech Discovery tables
    if current_version < 3:
        log.info("Applying migration 3: Phase One Deep Tech Discovery tables")
        conn = connect(db_path)
        try:
            with conn:
                pk_clause = _serial_primary_key_clause(db_path)
                id_type = _id_column_type(db_path)
                # Entities table - People, Labs, Organizations
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS entities (
                        id {pk_clause},
                        type TEXT NOT NULL, -- person, lab, org
                        name TEXT NOT NULL,
                        description TEXT,
                        homepage_url TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);")
                
                # Accounts table - Cross-platform identities
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id {pk_clause},
                        entity_id {id_type} NOT NULL,
                        platform TEXT NOT NULL, -- x, arxiv, github, crossref, semantic
                        handle_or_id TEXT NOT NULL,
                        url TEXT,
                        confidence REAL DEFAULT 0.0,
                        created_at TEXT,
                        FOREIGN KEY(entity_id) REFERENCES entities(id)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_entity ON accounts(entity_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform, handle_or_id);")
                
                # Artifacts table - Unified content from all sources
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS artifacts (
                        id {pk_clause},
                        type TEXT NOT NULL, -- preprint, paper, repo, release, tweet, post
                        source TEXT NOT NULL, -- arxiv, github, x, crossref, semantic
                        source_id TEXT NOT NULL,
                        title TEXT,
                        text TEXT,
                        url TEXT,
                        published_at TEXT,
                        author_entity_ids TEXT, -- JSON array of entity IDs
                        raw_json TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                    """
                )
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_artifacts_source ON artifacts(source, source_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(type);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_published ON artifacts(published_at);")
                
                # Topics table - Research taxonomy
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS topics (
                        id {pk_clause},
                        name TEXT NOT NULL,
                        taxonomy_path TEXT, -- e.g., "ai/ml/rl"
                        description TEXT,
                        created_at TEXT
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topics_path ON topics(taxonomy_path);")
                
                # Artifact-Topic associations
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS artifact_topics (
                        artifact_id {id_type} NOT NULL,
                        topic_id {id_type} NOT NULL,
                        confidence REAL,
                        PRIMARY KEY (artifact_id, topic_id),
                        FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
                        FOREIGN KEY(topic_id) REFERENCES topics(id)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artopics_artifact ON artifact_topics(artifact_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artopics_topic ON artifact_topics(topic_id);")
                
                # Scores table - Novelty, emergence, obscurity, discovery
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS scores (
                        artifact_id {id_type} PRIMARY KEY,
                        novelty REAL,
                        emergence REAL,
                        obscurity REAL,
                        discovery_score REAL,
                        computed_at TEXT,
                        FOREIGN KEY(artifact_id) REFERENCES artifacts(id)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_discovery ON scores(discovery_score);")
                
            set_schema_version(db_path, 3)
            log.info("Migration 3 applied successfully")
        finally:
            conn.close()
    
    # Migration 4: Phase Two - Topic Evolution tables
    if current_version < 4:
        log.info("Applying migration 4: Phase Two Topic Evolution tables")
        conn = connect(db_path)
        try:
            with conn:
                pk_clause = _serial_primary_key_clause(db_path)
                id_type = _id_column_type(db_path)
                # Topic evolution events (merges, splits, emergence, decline)
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS topic_evolution (
                        id {pk_clause},
                        topic_id {id_type} NOT NULL,
                        event_type TEXT NOT NULL,
                        related_topic_ids TEXT,
                        event_strength REAL,
                        event_date TEXT NOT NULL,
                        description TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(topic_id) REFERENCES topics(id)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_evolution_topic ON topic_evolution(topic_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_evolution_type ON topic_evolution(event_type);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_evolution_date ON topic_evolution(event_date);")
                
                # Topic similarity matrix
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS topic_similarity (
                        topic_id_1 {id_type} NOT NULL,
                        topic_id_2 {id_type} NOT NULL,
                        similarity REAL NOT NULL,
                        computed_at TEXT NOT NULL,
                        PRIMARY KEY(topic_id_1, topic_id_2),
                        FOREIGN KEY(topic_id_1) REFERENCES topics(id),
                        FOREIGN KEY(topic_id_2) REFERENCES topics(id)
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_topic_similarity_score ON topic_similarity(similarity);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_topic_similarity_computed "
                    "ON topic_similarity(computed_at);"
                )
                
                # Topic clusters for hierarchical organization
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS topic_clusters (
                        id {pk_clause},
                        name TEXT NOT NULL,
                        topic_ids TEXT NOT NULL,
                        centroid_embedding TEXT,
                        cluster_quality REAL,
                        parent_cluster_id {id_type},
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(parent_cluster_id) REFERENCES topic_clusters(id)
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_topic_clusters_quality "
                    "ON topic_clusters(cluster_quality);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_topic_clusters_parent "
                    "ON topic_clusters(parent_cluster_id);"
                )
                
            set_schema_version(db_path, 4)
            log.info("Migration 4 applied successfully")
        finally:
            conn.close()
    
    # Migration 5: Phase 2.3 - Enhanced Entity Schema for Researcher Profile Analytics
    if current_version < 5:
        log.info("Applying migration 5: Phase 2.3 Enhanced Entity Schema")
        conn = connect(db_path)
        try:
            with conn:
                # Add enhanced columns to entities table for researcher profile analytics
                conn.execute("ALTER TABLE entities ADD COLUMN impact_metrics TEXT;")
                conn.execute("ALTER TABLE entities ADD COLUMN collaboration_network TEXT;")
                conn.execute("ALTER TABLE entities ADD COLUMN research_trajectory TEXT;")
                conn.execute("ALTER TABLE entities ADD COLUMN expertise_areas TEXT;")
                conn.execute("ALTER TABLE entities ADD COLUMN influence_score REAL;")
                conn.execute("ALTER TABLE entities ADD COLUMN platform_activity TEXT;")
                conn.execute("ALTER TABLE entities ADD COLUMN last_activity_date TEXT;")
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_influence ON entities(influence_score);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_last_activity ON entities(last_activity_date);")
                
            set_schema_version(db_path, 5)
            log.info("Migration 5 applied successfully")
        finally:
            conn.close()
    
    # Migration 6: Persist artifact classifications
    if current_version < 6:
        log.info("Applying migration 6: Artifact classifications table")
        conn = connect(db_path)
        try:
            with conn:
                id_type = _id_column_type(db_path)
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS artifact_classifications (
                        artifact_id {id_type} PRIMARY KEY,
                        category TEXT,
                        sentiment TEXT,
                        urgency INTEGER,
                        tags_json TEXT,
                        reasoning TEXT,
                        raw_json TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        FOREIGN KEY(artifact_id) REFERENCES artifacts(id)
                    );
                    """
                )
            set_schema_version(db_path, 6)
            log.info("Migration 6 applied successfully")
        finally:
            conn.close()
    
    # Migration 7: Cross-Source Corroboration - Artifact Relationships
    if current_version < 7:
        log.info("Applying migration 7: Artifact relationships table for cross-source corroboration")
        conn = connect(db_path)
        try:
            with conn:
                pk_clause = _serial_primary_key_clause(db_path)
                id_type = _id_column_type(db_path)
                # Artifact relationships for citation graph
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS artifact_relationships (
                        id {pk_clause},
                        source_artifact_id {id_type} NOT NULL,
                        target_artifact_id {id_type} NOT NULL,
                        relationship_type TEXT NOT NULL,
                        confidence REAL DEFAULT 0.0,
                        detection_method TEXT,
                        metadata_json TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(source_artifact_id) REFERENCES artifacts(id),
                        FOREIGN KEY(target_artifact_id) REFERENCES artifacts(id)
                    );
                    """
                )
                
                # Indexes for efficient relationship queries
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relationships_source "
                    "ON artifact_relationships(source_artifact_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relationships_target "
                    "ON artifact_relationships(target_artifact_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relationships_type "
                    "ON artifact_relationships(relationship_type);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_relationships_confidence "
                    "ON artifact_relationships(confidence);"
                )
                
                # Unique constraint to prevent duplicate relationships
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_relationships_pair "
                    "ON artifact_relationships(source_artifact_id, target_artifact_id, relationship_type);"
                )
                
            set_schema_version(db_path, 7)
            log.info("Migration 7 applied successfully")
        finally:
            conn.close()
    
    # Migration 8: Add experiments, experiment_runs, and discovery_labels tables
    if current_version < 8:
        log.info("Applying migration 8: Add experiments tables")
        conn = connect(db_path)
        try:
            with conn:
                pk_clause = _serial_primary_key_clause(db_path)
                id_type = _id_column_type(db_path)
                # Experiments table - stores experiment configurations
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS experiments (
                        id {pk_clause},
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        config_json TEXT NOT NULL,
                        baseline_id {id_type},
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'draft',
                        FOREIGN KEY (baseline_id) REFERENCES experiments(id) ON DELETE SET NULL
                    );
                    """
                )
                
                # Experiment runs table - stores execution results
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS experiment_runs (
                        id {pk_clause},
                        experiment_id {id_type} NOT NULL,
                        artifact_count INTEGER NOT NULL DEFAULT 0,
                        true_positives INTEGER NOT NULL DEFAULT 0,
                        false_positives INTEGER NOT NULL DEFAULT 0,
                        true_negatives INTEGER NOT NULL DEFAULT 0,
                        false_negatives INTEGER NOT NULL DEFAULT 0,
                        precision REAL,
                        recall REAL,
                        f1_score REAL,
                        accuracy REAL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        status TEXT NOT NULL DEFAULT 'running',
                        error_message TEXT,
                        metadata_json TEXT,
                        FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
                    );
                    """
                )
                
                # Discovery labels table - ground truth annotations
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS discovery_labels (
                        id {pk_clause},
                        artifact_id {id_type} NOT NULL,
                        label TEXT NOT NULL,
                        confidence REAL DEFAULT 1.0,
                        annotator TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
                    );
                    """
                )
                
                # Indexes for experiments
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiments_name "
                    "ON experiments(name);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiments_status "
                    "ON experiments(status);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiments_created_at "
                    "ON experiments(created_at);"
                )

                # Indexes for experiment runs
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment_id "
                    "ON experiment_runs(experiment_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiment_runs_started_at "
                    "ON experiment_runs(started_at);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_experiment_runs_status "
                    "ON experiment_runs(status);"
                )

                # Indexes for discovery labels
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_discovery_labels_artifact_id "
                    "ON discovery_labels(artifact_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_discovery_labels_label "
                    "ON discovery_labels(label);"
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_discovery_labels_artifact "
                    "ON discovery_labels(artifact_id);"
                )
            
            set_schema_version(db_path, 8)
            log.info("Migration 8 applied successfully")
        finally:
            conn.close()
    
    # Migration 9: Add composite indexes for query performance optimization
    if current_version < 9:
        log.info("Applying migration 9: Add composite indexes for query performance")
        conn = connect(db_path)
        try:
            with conn:
                # 1. Composite index for top discoveries query (most critical)
                # Query pattern: ORDER BY discovery_score DESC, published_at DESC with JOIN
                # This enables efficient sorting without full table scan
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_scores_discovery_artifact
                    ON scores(discovery_score DESC, artifact_id);
                    """
                )
                
                # 2. Composite index for topic timeline queries
                # Query pattern: WHERE topic_id = ? ORDER BY published_at DESC with artifact JOIN
                # Critical for Phase Two topic evolution analytics
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_artifact_topics_topic_artifact
                    ON artifact_topics(topic_id, artifact_id);
                    """
                )
                
                # 3. Composite indexes for citation graph queries (cross-source corroboration)
                # Query pattern: WHERE source_artifact_id = ? AND confidence >= ? ORDER BY confidence DESC
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_relationships_source_confidence
                    ON artifact_relationships(source_artifact_id, confidence DESC);
                    """
                )
                
                # Query pattern: WHERE target_artifact_id = ? AND confidence >= ? ORDER BY confidence DESC
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_relationships_target_confidence
                    ON artifact_relationships(target_artifact_id, confidence DESC);
                    """
                )
                
                # 4. Composite index for time-filtered discovery queries
                # Query pattern: WHERE published_at >= ? AND source = ? ORDER BY published_at DESC
                # Enables efficient range scans with source filtering
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_artifacts_published_source
                    ON artifacts(published_at DESC, source);
                    """
                )
                
                # 5. Composite indexes for topic similarity queries with score filtering
                # Query pattern: WHERE topic_id_1 = ? ORDER BY similarity DESC
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_similarity_topic1_score
                    ON topic_similarity(topic_id_1, similarity DESC);
                    """
                )
                
                # Query pattern: WHERE topic_id_2 = ? ORDER BY similarity DESC (bidirectional lookup)
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_similarity_topic2_score
                    ON topic_similarity(topic_id_2, similarity DESC);
                    """
                )
                
                # 6. Composite index for entity influence scoring
                # Query pattern: WHERE last_activity_date >= ? ORDER BY influence_score DESC
                # Used for researcher ranking and profile analytics
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_entities_activity_influence
                    ON entities(last_activity_date DESC, influence_score DESC);
                    """
                )
                
                # 7. Composite index for experiment runs by experiment and date
                # Query pattern: WHERE experiment_id = ? ORDER BY started_at DESC
                # Used for backtesting and A/B testing workflows
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment_started
                    ON experiment_runs(experiment_id, started_at DESC);
                    """
                )
            
            set_schema_version(db_path, 9)
            log.info("Migration 9 applied successfully")
        finally:
            conn.close()

    # Migration 10: Entity resolution schema enhancements
    if current_version < 10:
        log.info("Applying migration 10: Entity resolution schema enhancements")
        conn = connect(db_path)
        try:
            with conn:
                is_postgres = _is_postgres_url(db_path)

                metadata_column = "metadata_json JSONB" if is_postgres else "metadata_json TEXT"
                merged_column = "merged_into_id BIGINT" if is_postgres else "merged_into_id INTEGER"
                _safe_add_column(conn, db_path, "entities", metadata_column)
                _safe_add_column(conn, db_path, "entities", merged_column)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entities_merged_into ON entities(merged_into_id);"
                )

                follower_column = "follower_count BIGINT" if is_postgres else "follower_count INTEGER"
                raw_column = "raw_json JSONB" if is_postgres else "raw_json TEXT"
                updated_column = (
                    "updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
                    if is_postgres
                    else "updated_at TEXT"
                )
                _safe_add_column(conn, db_path, "accounts", follower_column)
                _safe_add_column(conn, db_path, "accounts", raw_column)
                _safe_add_column(conn, db_path, "accounts", updated_column)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_accounts_updated ON accounts(updated_at);"
                )

                pk_clause = _serial_primary_key_clause(db_path)
                id_type = _id_column_type(db_path)
                timestamp_type = "TIMESTAMP" if is_postgres else "TEXT"
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS entity_merge_history (
                        id {pk_clause},
                        primary_entity_id {id_type} NOT NULL,
                        candidate_entity_id {id_type} NOT NULL,
                        decision TEXT NOT NULL,
                        similarity_score REAL,
                        reviewer TEXT,
                        notes TEXT,
                        created_at {timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(primary_entity_id) REFERENCES entities(id),
                        FOREIGN KEY(candidate_entity_id) REFERENCES entities(id)
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entity_merge_primary ON entity_merge_history(primary_entity_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entity_merge_candidate ON entity_merge_history(candidate_entity_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entity_merge_created_at ON entity_merge_history(created_at);"
                )

                if not is_postgres:
                    conn.execute(
                        "UPDATE accounts SET updated_at = COALESCE(updated_at, created_at);"
                    )

            set_schema_version(db_path, 10)
            log.info("Migration 10 applied successfully")
        finally:
            conn.close()
    
    log.info("Database migrations complete. Schema version: %d", get_schema_version(db_path))


# Phase One: Deep Tech Discovery database functions


def upsert_entity(
    db_path: str,
    entity_type: str,
    name: str,
    description: str | None = None,
    homepage_url: str | None = None,
) -> int:
    """Upsert an entity (person, lab, org) and return its ID."""
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        with conn:
            # Try to find existing entity by type and name
            cur = conn.execute(
                "SELECT id FROM entities WHERE type = ? AND name = ?;",
                (entity_type, name)
            )
            row = cur.fetchone()
            
            if row:
                entity_id = cast(int, row["id"])
                # Update existing entity
                conn.execute(
                    """
                    UPDATE entities SET
                      description = COALESCE(?, description),
                      homepage_url = COALESCE(?, homepage_url),
                      updated_at = ?
                    WHERE id = ?;
                    """,
                    (description, homepage_url, now, entity_id)
                )
            else:
                # Insert new entity
                entity_id = _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO entities (type, name, description, homepage_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (entity_type, name, description, homepage_url, now, now),
                )
            
            return entity_id
    finally:
        conn.close()


def upsert_account(db_path: str, entity_id: int, platform: str, handle_or_id: str, 
                   url: str | None = None, confidence: float = 0.0) -> int:
    """Upsert an account for an entity and return its ID."""
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        with conn:
            # Try to find existing account by platform and handle
            cur = conn.execute(
                "SELECT id FROM accounts WHERE platform = ? AND handle_or_id = ?;",
                (platform, handle_or_id)
            )
            row = cur.fetchone()
            
            if row:
                account_id = cast(int, row["id"])
                # Update existing account
                conn.execute(
                    """
                    UPDATE accounts SET
                      entity_id = ?,
                      url = COALESCE(?, url),
                      confidence = ?,
                      created_at = ?
                    WHERE id = ?;
                    """,
                    (entity_id, url, confidence, now, account_id)
                )
            else:
                # Insert new account
                account_id = _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO accounts (entity_id, platform, handle_or_id, url, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (entity_id, platform, handle_or_id, url, confidence, now),
                )
            
            return account_id
    finally:
        conn.close()


def upsert_artifact(db_path: str, artifact_type: str, source: str, source_id: str,
                    title: str | None = None, text: str | None = None, url: str | None = None,
                    published_at: str | None = None, author_entity_ids: list[int] | None = None,
                    raw_json: str | None = None) -> int:
    """Upsert an artifact and return its ID."""
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        author_ids_json = json.dumps(author_entity_ids) if author_entity_ids else None
        
        with conn:
            # Try to find existing artifact by source and source_id
            cur = conn.execute(
                "SELECT id FROM artifacts WHERE source = ? AND source_id = ?;",
                (source, source_id)
            )
            row = cur.fetchone()
            
            if row:
                artifact_id = cast(int, row["id"])
                # Update existing artifact
                conn.execute(
                    """
                    UPDATE artifacts SET
                      type = COALESCE(?, type),
                      title = COALESCE(?, title),
                      text = COALESCE(?, text),
                      url = COALESCE(?, url),
                      published_at = COALESCE(?, published_at),
                      author_entity_ids = COALESCE(?, author_entity_ids),
                      raw_json = COALESCE(?, raw_json),
                      updated_at = ?
                    WHERE id = ?;
                    """,
                    (artifact_type, title, text, url, published_at, author_ids_json, raw_json, now, artifact_id)
                )
            else:
                # Insert new artifact
                artifact_id = _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO artifacts (type, source, source_id, title, text, url, published_at, 
                                         author_entity_ids, raw_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        artifact_type,
                        source,
                        source_id,
                        title,
                        text,
                        url,
                        published_at,
                        author_ids_json,
                        raw_json,
                        now,
                        now,
                    ),
                )
            
            return artifact_id
    finally:
        conn.close()


def upsert_topic(db_path: str, name: str, taxonomy_path: str | None = None, 
                 description: str | None = None) -> int:
    """Upsert a topic and return its ID."""
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        with conn:
            # Try to find existing topic by name
            cur = conn.execute(
                "SELECT id FROM topics WHERE name = ?;",
                (name,)
            )
            row = cur.fetchone()
            
            if row:
                topic_id = cast(int, row["id"])
                # Update existing topic
                conn.execute(
                    """
                    UPDATE topics SET
                      taxonomy_path = COALESCE(?, taxonomy_path),
                      description = COALESCE(?, description)
                    WHERE id = ?;
                    """,
                    (taxonomy_path, description, topic_id)
                )
            else:
                # Insert new topic
                topic_id = _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO topics (name, taxonomy_path, description, created_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (name, taxonomy_path, description, now),
                )
            
            return topic_id
    finally:
        conn.close()


def link_artifact_topic(db_path: str, artifact_id: int, topic_id: int, confidence: float = 1.0) -> None:
    """Link an artifact to a topic with confidence score."""
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO artifact_topics (artifact_id, topic_id, confidence)
                VALUES (?, ?, ?)
                ON CONFLICT(artifact_id, topic_id) DO UPDATE SET
                    confidence = excluded.confidence;
                """,
                (artifact_id, topic_id, confidence)
            )
    finally:
        conn.close()


def update_discovery_scores(db_path: str, artifact_id: int, novelty: float, emergence: float, 
                           obscurity: float, discovery_score: float) -> None:
    """Update discovery scores for an artifact."""
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        with conn:
            conn.execute(
                """
                INSERT INTO scores (artifact_id, novelty, emergence, obscurity, discovery_score, computed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    novelty = excluded.novelty,
                    emergence = excluded.emergence,
                    obscurity = excluded.obscurity,
                    discovery_score = excluded.discovery_score,
                    computed_at = excluded.computed_at;
                """,
                (artifact_id, novelty, emergence, obscurity, discovery_score, now)
            )
    finally:
        conn.close()


def list_artifacts_for_analysis(db_path: str, limit: int = 200) -> list[dict[str, Any]]:
    """List artifacts that need research classification."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT a.* FROM artifacts a
            LEFT JOIN artifact_topics at ON a.id = at.artifact_id
            WHERE at.artifact_id IS NULL
            ORDER BY a.published_at DESC
            LIMIT ?;
            """,
            (int(limit or 200),)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_artifacts_for_scoring(db_path: str, limit: int = 500) -> list[dict[str, Any]]:
    """List artifacts that need discovery scoring."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT a.* FROM artifacts a
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE s.artifact_id IS NULL
            ORDER BY a.published_at DESC
            LIMIT ?;
            """,
            (int(limit or 500),)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_top_discoveries(db_path: str, min_score: float = 80.0, limit: int = 50, 
                        hours: int | None = None) -> list[dict[str, Any]]:
    """List top discoveries by discovery score."""
    conn = connect(db_path)
    try:
        params: list[Any] = [float(min_score)]
        where = "s.discovery_score >= ?"
        
        if hours and hours > 0:
            from datetime import datetime, timedelta, timezone
            cutoff = (
                (datetime.now(tz=timezone.utc) - timedelta(hours=hours))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            where += " AND a.published_at >= ?"
            params.append(cutoff)
        
        topic_paths_expr = _topic_paths_agg_expression(db_path)

        sql = f"""
            SELECT 
                a.*,
                a.id AS artifact_id,
                s.novelty,
                s.emergence,
                s.obscurity,
                s.discovery_score,
                s.computed_at,
                ac.category,
                ac.sentiment,
                ac.urgency,
                ac.tags_json,
                ac.reasoning,
                ac.raw_json as classification_json,
                {topic_paths_expr}
            FROM artifacts a
            JOIN scores s ON a.id = s.artifact_id
            LEFT JOIN artifact_classifications ac ON a.id = ac.artifact_id
            WHERE {where}
            ORDER BY s.discovery_score DESC, a.published_at DESC
            LIMIT ?;
        """
        params.append(int(limit or 50))
        
        cur = conn.execute(sql, tuple(params))
        results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            item = dict(row)
            # Parse tags JSON if present
            tags_raw = item.pop("tags_json", None)
            tags: list[str] = []
            if tags_raw:
                try:
                    parsed_tags = json.loads(tags_raw)
                    if isinstance(parsed_tags, list):
                        tags = [str(t) for t in parsed_tags if str(t).strip()]
                except (json.JSONDecodeError, TypeError):
                    tags = []
            item["tags"] = tags
            topic_paths = item.pop("topic_paths", "") or ""
            topics = [t for t in topic_paths.split(",") if t]
            item["topics"] = topics
            # Normalize urgency to int when available
            if item.get("urgency") is not None:
                try:
                    item["urgency"] = int(item["urgency"])
                except (TypeError, ValueError):
                    item["urgency"] = None
            results.append(item)
        return results
    finally:
        conn.close()


def list_top_discoveries_paginated(
    db_path: str,
    min_score: float = 80.0,
    limit: int = 50,
    hours: int | None = None,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """
    List top discoveries with cursor-based pagination.
    
    Returns:
        Tuple of (results, next_cursor, has_more)
        
    Cursor format: base64-encoded JSON with last_score and last_id
    """
    import base64
    
    conn = connect(db_path)
    try:
        params: list[Any] = [float(min_score)]
        where = "s.discovery_score >= ?"
        
        # Decode cursor if provided
        cursor_score: float | None = None
        cursor_id: int | None = None
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode('utf-8'))
                cursor_score = cursor_data.get("score")
                cursor_id = cursor_data.get("id")
            except (ValueError, KeyError, json.JSONDecodeError):
                pass  # Invalid cursor, ignore
        
        # Add cursor conditions for keyset pagination
        if cursor_score is not None and cursor_id is not None:
            where += " AND (s.discovery_score < ? OR (s.discovery_score = ? AND a.id < ?))"
            params.extend([cursor_score, cursor_score, cursor_id])
        
        if hours and hours > 0:
            from datetime import datetime, timedelta, timezone
            cutoff = (
                (datetime.now(tz=timezone.utc) - timedelta(hours=hours))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            where += " AND a.published_at >= ?"
            params.append(cutoff)
        
        # Request limit + 1 to check if there are more results
        fetch_limit = int(limit or 50) + 1
        
        topic_paths_expr = _topic_paths_agg_expression(db_path)

        sql = f"""
            SELECT 
                a.*,
                a.id AS artifact_id,
                s.novelty,
                s.emergence,
                s.obscurity,
                s.discovery_score,
                s.computed_at,
                ac.category,
                ac.sentiment,
                ac.urgency,
                ac.tags_json,
                ac.reasoning,
                ac.raw_json as classification_json,
                {topic_paths_expr}
            FROM artifacts a
            JOIN scores s ON a.id = s.artifact_id
            LEFT JOIN artifact_classifications ac ON a.id = ac.artifact_id
            WHERE {where}
            ORDER BY s.discovery_score DESC, a.id DESC
            LIMIT ?;
        """
        params.append(fetch_limit)
        
        cur = conn.execute(sql, tuple(params))
        all_results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            item = dict(row)
            # Parse tags JSON if present
            tags_raw = item.pop("tags_json", None)
            tags: list[str] = []
            if tags_raw:
                try:
                    parsed_tags = json.loads(tags_raw)
                    if isinstance(parsed_tags, list):
                        tags = [str(t) for t in parsed_tags if str(t).strip()]
                except (json.JSONDecodeError, TypeError):
                    tags = []
            item["tags"] = tags
            topic_paths = item.pop("topic_paths", "") or ""
            topics = [t for t in topic_paths.split(",") if t]
            item["topics"] = topics
            # Normalize urgency to int when available
            if item.get("urgency") is not None:
                try:
                    item["urgency"] = int(item["urgency"])
                except (TypeError, ValueError):
                    item["urgency"] = None
            all_results.append(item)
        
        # Check if there are more results
        has_more = len(all_results) > limit
        results = all_results[:limit]  # Return only requested limit
        
        # Generate next cursor from last item
        next_cursor: str | None = None
        if has_more and results:
            last_item = results[-1]
            cursor_data = {
                "score": last_item.get("discovery_score"),
                "id": last_item.get("id"),
            }
            next_cursor = base64.b64encode(
                json.dumps(cursor_data).encode('utf-8')
            ).decode('utf-8')
        
        return results, next_cursor, has_more
    finally:
        conn.close()


def upsert_artifact_classification(db_path: str, artifact_id: int, classification: dict[str, Any]) -> None:
    """Persist artifact classification details."""
    tags = classification.get("tags") or []
    tags_json = json.dumps(tags, ensure_ascii=False)
    raw_json = json.dumps(classification, ensure_ascii=False)
    category = classification.get("category")
    sentiment = classification.get("sentiment")
    urgency = classification.get("urgency")
    try:
        urgency_int = int(urgency) if urgency is not None else None
    except (TypeError, ValueError):
        urgency_int = None
    reasoning = classification.get("reasoning") or ""
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO artifact_classifications (
                    artifact_id, category, sentiment, urgency, tags_json,
                    reasoning, raw_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    category = excluded.category,
                    sentiment = excluded.sentiment,
                    urgency = excluded.urgency,
                    tags_json = excluded.tags_json,
                    reasoning = excluded.reasoning,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    int(artifact_id),
                    category,
                    sentiment,
                    urgency_int,
                    tags_json,
                    reasoning,
                    raw_json,
                    now,
                    now,
                ),
            )
    finally:
        conn.close()


def get_entity_with_accounts(db_path: str, entity_id: int) -> dict[str, Any] | None:
    """Get entity with all its accounts."""
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM entities WHERE id = ?;", (entity_id,))
        entity_row = cur.fetchone()
        if not entity_row:
            return None
        
        entity = _row_to_entity(entity_row)

        # Get accounts
        cur = conn.execute("SELECT * FROM accounts WHERE entity_id = ?;", (entity_id,))
        accounts = [_row_to_account(account_row) for account_row in cur.fetchall()]
        entity["accounts"] = accounts
        entity["account_count"] = len(accounts)
        
        return entity
    finally:
        conn.close()


def get_trending_topics(db_path: str, window_days: int = 14, limit: int = 20) -> list[dict[str, Any]]:
    """Get trending topics by artifact count in time window."""
    conn = connect(db_path)
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = (
            (datetime.now(tz=timezone.utc) - timedelta(days=window_days))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        
        cur = conn.execute(
            """
            SELECT 
                t.id,
                t.name,
                t.taxonomy_path,
                t.description,
                COUNT(DISTINCT at.artifact_id) as artifact_count,
                AVG(s.discovery_score) as avg_discovery_score
            FROM topics t
            JOIN artifact_topics at ON t.id = at.topic_id
            JOIN artifacts a ON at.artifact_id = a.id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE a.published_at >= ?
            GROUP BY t.id
            ORDER BY artifact_count DESC, avg_discovery_score DESC
            LIMIT ?;
            """,
            (cutoff, int(limit or 20))
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_trending_topics_paginated(
    db_path: str,
    window_days: int = 14,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """
    Get trending topics with cursor-based pagination.
    
    Returns:
        Tuple of (results, next_cursor, has_more)
        
    Cursor format: base64-encoded JSON with last_count and last_id
    """
    import base64
    
    conn = connect(db_path)
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = (
            (datetime.now(tz=timezone.utc) - timedelta(days=window_days))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        
        # Decode cursor if provided
        cursor_count: int | None = None
        cursor_id: int | None = None
        having_clause = ""
        params: list[Any] = [cutoff]
        
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode('utf-8'))
                cursor_count = cursor_data.get("count")
                cursor_id = cursor_data.get("id")
                if cursor_count is not None and cursor_id is not None:
                    having_clause = "HAVING (artifact_count < ? OR (artifact_count = ? AND t.id < ?))"
                    # Will add params after HAVING clause in SQL
            except (ValueError, KeyError, json.JSONDecodeError):
                pass  # Invalid cursor, ignore
        
        # Request limit + 1 to check if there are more results
        fetch_limit = int(limit or 20) + 1
        
        sql = f"""
            SELECT 
                t.id,
                t.name,
                t.taxonomy_path,
                t.description,
                COUNT(DISTINCT at.artifact_id) as artifact_count,
                AVG(s.discovery_score) as avg_discovery_score
            FROM topics t
            JOIN artifact_topics at ON t.id = at.topic_id
            JOIN artifacts a ON at.artifact_id = a.id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE a.published_at >= ?
            GROUP BY t.id
            {having_clause}
            ORDER BY artifact_count DESC, t.id DESC
            LIMIT ?;
        """
        
        # Add cursor params if HAVING clause was added
        if cursor_count is not None and cursor_id is not None:
            params.extend([cursor_count, cursor_count, cursor_id])
        params.append(fetch_limit)
        
        cur = conn.execute(sql, tuple(params))
        all_results = [dict(r) for r in cur.fetchall()]
        
        # Check if there are more results
        has_more = len(all_results) > limit
        results = all_results[:limit]  # Return only requested limit
        
        # Generate next cursor from last item
        next_cursor: str | None = None
        if has_more and results:
            last_item = results[-1]
            cursor_data = {
                "count": last_item.get("artifact_count"),
                "id": last_item.get("id"),
            }
            next_cursor = base64.b64encode(
                json.dumps(cursor_data).encode('utf-8')
            ).decode('utf-8')
        
        return results, next_cursor, has_more
    finally:
        conn.close()


def list_all_entities(db_path: str) -> list[dict[str, Any]]:
    """Get all entities with their accounts."""
    conn = connect(db_path)
    try:
        cursor = conn.execute("SELECT * FROM entities ORDER BY id;")
        entities = []
        for row in cursor.fetchall():
            entity = _row_to_entity(row)
            account_cursor = conn.execute("SELECT * FROM accounts WHERE entity_id = ?;", (entity["id"],))
            entity["accounts"] = [_row_to_account(acc) for acc in account_cursor.fetchall()]
            entities.append(entity)
        return entities
    finally:
        conn.close()


def list_all_accounts(db_path: str) -> list[dict[str, Any]]:
    """Get all accounts."""
    conn = connect(db_path)
    try:
        cursor = conn.execute("SELECT * FROM accounts ORDER BY id;")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def list_entities(
    db_path: str,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    entity_type: str | None = None,
    sort: str | None = None,
    order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """Paginated entity listing for UI surfaces."""
    conn = connect(db_path)
    try:
        where_clauses: list[str] = []
        params: list[Any] = []

        if entity_type:
            where_clauses.append("type = ?")
            params.append(entity_type)

        if search:
            where_clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
            like = f"%{search.lower()}%"
            params.extend([like, like])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        count_params = list(params)
        cur = conn.execute(f"SELECT COUNT(*) as cnt FROM entities {where_sql};", count_params)
        total = cur.fetchone()["cnt"]

        offset = max(page - 1, 0) * page_size
        query_params = list(params)
        query_params.extend([page_size, offset])

        sort_column_map = {
            "name": "LOWER(e.name)",
            "created_at": "datetime(e.created_at)",
            "updated_at": "datetime(e.updated_at)",
            "last_activity": "datetime(e.last_activity_date)",
            "influence": "e.influence_score",
            "account_count": "account_count",
            "artifact_count": "artifact_count",
        }
        order_dir = "DESC" if order.lower() == "desc" else "ASC"
        default_sort = "datetime(e.updated_at)"
        sort_expr = sort_column_map.get((sort or "updated_at").lower(), default_sort)
        order_by_sql = f"{sort_expr} {order_dir}, e.id DESC"

        query = f"""
            SELECT 
                e.*,
                (
                    SELECT COUNT(1)
                    FROM accounts a
                    WHERE a.entity_id = e.id
                ) AS account_count,
                (
                    SELECT COUNT(1)
                    FROM artifacts art
                    WHERE art.author_entity_ids LIKE '%' || e.id || '%'
                ) AS artifact_count
            FROM entities e
            {where_sql}
            ORDER BY {order_by_sql}
            LIMIT ? OFFSET ?;
        """

        cur = conn.execute(query, query_params)
        entities: list[dict[str, Any]] = []
        for row in cur.fetchall():
            entity = _row_to_entity(row)
            entity["account_count"] = row["account_count"]
            entity["artifact_count"] = row["artifact_count"]
            entities.append(entity)

        return entities, total
    finally:
        conn.close()


def record_entity_merge_history(
    db_path: str,
    primary_entity_id: int,
    candidate_entity_id: int,
    decision: str,
    similarity_score: float | None,
    reviewer: str | None = None,
    notes: str | None = None,
) -> None:
    """Persist merge/ignore decisions for auditability."""
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO entity_merge_history (
                    primary_entity_id,
                    candidate_entity_id,
                    decision,
                    similarity_score,
                    reviewer,
                    notes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    primary_entity_id,
                    candidate_entity_id,
                    decision,
                    similarity_score,
                    reviewer,
                    notes,
                    utc_now_iso(),
                ),
            )
    finally:
        conn.close()


def search_entities(
    db_path: str,
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search entities by name or description with relevance scoring.
    
    Uses SQLite FTS for efficient full-text search.
    """
    conn = connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Use LIKE for simple pattern matching (could be enhanced with FTS)
        search_pattern = f"%{query.lower()}%"
        
        sql = """
            SELECT 
                e.id,
                e.type AS entity_type,
                e.name,
                e.description,
                e.created_at,
                e.updated_at,
                COUNT(a.id) as artifact_count,
                -- Simple relevance scoring
                CASE 
                    WHEN LOWER(e.name) LIKE ? THEN 1.0
                    WHEN LOWER(e.description) LIKE ? THEN 0.5
                    ELSE 0.0
                END as relevance_score,
                CASE 
                    WHEN LOWER(e.name) LIKE ? THEN 'name_match'
                    ELSE 'description_match'
                END as match_reason
            FROM entities e
            LEFT JOIN artifacts a ON a.author_entity_ids LIKE '%' || e.id || '%'
            WHERE (LOWER(e.name) LIKE ? OR LOWER(COALESCE(e.description, '')) LIKE ?)
        """
        params = [
            search_pattern,  # name match
            search_pattern,  # desc match
            search_pattern,  # name reason
            search_pattern,  # where name
            search_pattern,  # where desc
        ]
        
        if entity_type:
            sql += " AND e.type = ?"
            params.append(entity_type)
            
        sql += """
            GROUP BY e.id, e.type, e.name, e.description, e.created_at, e.updated_at
            ORDER BY relevance_score DESC, artifact_count DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(sql, params)
        
        results = []
        for row in cursor.fetchall():
            entity = _row_to_entity(row)
            entity["artifact_count"] = row["artifact_count"]
            entity["relevance_score"] = row["relevance_score"]
            entity["match_reason"] = row["match_reason"]
            results.append(entity)
            
        return results
    finally:
        conn.close()


def get_entity_stats(
    db_path: str,
    entity_id: int,
    days: int = 30,
) -> Optional[Dict[str, Any]]:
    """Get comprehensive statistics for an entity.
    
    Returns statistics about artifacts, scores, collaboration, and activity.
    """
    conn = connect(db_path)
    try:
        cursor = conn.cursor()
        
        # First check if entity exists
        cursor.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,))
        if not cursor.fetchone():
            return None
            
        # Get basic artifact statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_artifacts,
                AVG(discovery_score) as avg_discovery_score,
                AVG(novelty) as avg_novelty,
                AVG(emergence) as avg_emergence,
                AVG(obscurity) as avg_obscurity
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
        """, (entity_id,))
        
        basic_stats = cursor.fetchone()
        
        # Get H-index proxy (number of artifacts with >= X discoveries)
        cursor.execute("""
            WITH artifact_scores AS (
                SELECT discovery_score,
                       ROW_NUMBER() OVER (ORDER BY discovery_score DESC) as rank
                FROM discoveries d
                JOIN artifacts a ON d.artifact_id = a.id
                WHERE a.author_entity_ids LIKE '%' || ? || '%'
            )
            SELECT COUNT(*) as h_index
            FROM artifact_scores
            WHERE rank <= discovery_score
        """, (entity_id,))
        
        h_index_row = cursor.fetchone()
        
        # Get active days (distinct publication days)
        cursor.execute("""
            SELECT COUNT(DISTINCT DATE(published_at))
            FROM artifacts
            WHERE author_entity_ids LIKE '%' || ? || '%'
              AND published_at IS NOT NULL
        """, (entity_id,))
        
        active_days = cursor.fetchone()[0]
        
        # Get total impact (sum of discovery scores)
        cursor.execute("""
            SELECT SUM(discovery_score)
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
        """, (entity_id,))
        
        total_impact = cursor.fetchone()[0] or 0
        
        # Get collaboration count (unique co-authors)
        cursor.execute("""
            SELECT COUNT(DISTINCT entity_id)
            FROM (
                SELECT CAST(json_each.value AS INTEGER) as entity_id
                FROM artifacts,
                     json_each(author_entity_ids)
                WHERE author_entity_ids LIKE '%' || ? || '%'
            )
            WHERE entity_id != ?
        """, (entity_id, entity_id))
        
        collaboration_count = cursor.fetchone()[0]
        
        # Get top topics
        cursor.execute("""
            SELECT t.name, COUNT(*) as count, AVG(d.discovery_score) as avg_score
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            LEFT JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN topics t ON at.topic_id = t.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
              AND t.name IS NOT NULL
            GROUP BY t.id, t.name
            ORDER BY count DESC
            LIMIT 5
        """, (entity_id,))
        
        top_topics = [
            {
                "name": row["name"],
                "count": row["count"],
                "avgScore": row["avg_score"],
            }
            for row in cursor.fetchall()
        ]
        
        # Get source breakdown
        cursor.execute("""
            SELECT a.source, COUNT(*) as count, AVG(d.discovery_score) as avg_score
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
            GROUP BY a.source
        """, (entity_id,))
        
        source_breakdown = [
            {
                "source": row["source"],
                "count": row["count"],
                "avgScore": row["avg_score"],
            }
            for row in cursor.fetchall()
        ]
        
        # Get activity timeline (last 30 days)
        cursor.execute("""
            SELECT DATE(published_at) as date, COUNT(*) as count
            FROM artifacts
            WHERE author_entity_ids LIKE '%' || ? || '%'
              AND published_at >= DATE('now', '-30 days')
            GROUP BY DATE(published_at)
            ORDER BY date DESC
        """, (entity_id,))
        
        activity_timeline = [
            {
                "date": row["date"],
                "count": row["count"],
            }
            for row in cursor.fetchall()
        ]
        
        return {
            "entityId": entity_id,
            "artifactCount": basic_stats["total_artifacts"] or 0,
            "avgDiscoveryScore": basic_stats["avg_discovery_score"] or 0,
            "totalImpact": total_impact,
            "hIndexProxy": h_index_row["h_index"] or 0,
            "activeDays": active_days or 0,
            "collaborationCount": collaboration_count or 0,
            "topTopics": top_topics,
            "sourceBreakdown": source_breakdown,
            "activityTimeline": activity_timeline,
        }
    finally:
        conn.close()


def get_entity_artifacts(
    db_path: str,
    entity_id: int,
    source: str | None = None,
    min_score: float = 0,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Get artifacts authored by an entity with pagination.
    
    Returns tuple of (artifacts_list, total_count).
    """
    conn = connect(db_path)
    try:
        cursor = conn.cursor()
        
        # First get total count
        count_sql = """
            SELECT COUNT(*)
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
        """
        count_params = [entity_id]
        
        if source:
            count_sql += " AND a.source = ?"
            count_params.append(source)
            
        if min_score > 0:
            count_sql += " AND d.discovery_score >= ?"
            count_params.append(min_score)
            
        cursor.execute(count_sql, count_params)
        total = cursor.fetchone()[0]
        
        # Get actual artifacts
        sql = """
            SELECT 
                a.id,
                a.type,
                a.source,
                a.source_id,
                a.title,
                a.text,
                a.url,
                a.published_at,
                a.author_entity_ids,
                a.raw_json,
                a.created_at,
                a.updated_at,
                d.novelty,
                d.emergence,
                d.obscurity,
                d.discovery_score,
                d.computed_at
            FROM discoveries d
            JOIN artifacts a ON d.artifact_id = a.id
            WHERE a.author_entity_ids LIKE '%' || ? || '%'
        """
        params = [entity_id]
        
        if source:
            sql += " AND a.source = ?"
            params.append(source)
            
        if min_score > 0:
            sql += " AND d.discovery_score >= ?"
            params.append(min_score)
            
        sql += """
            ORDER BY d.discovery_score DESC, a.published_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        
        artifacts = []
        for row in cursor.fetchall():
            artifacts.append({
                "id": row["id"],
                "type": row["type"],
                "source": row["source"],
                "source_id": row["source_id"],
                "title": row["title"],
                "text": row["text"],
                "url": row["url"],
                "published_at": row["published_at"],
                "author_entity_ids": row["author_entity_ids"],
                "raw_json": row["raw_json"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "novelty": row["novelty"],
                "emergence": row["emergence"],
                "obscurity": row["obscurity"],
                "discovery_score": row["discovery_score"],
                "computed_at": row["computed_at"],
            })
            
        return artifacts, total
    finally:
        conn.close()


def list_entity_merge_history(
    db_path: str,
    entity_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent merge/ignore actions."""
    conn = connect(db_path)
    try:
        params: list[Any] = []
        where_sql = ""
        if entity_id is not None:
            where_sql = "WHERE h.primary_entity_id = ? OR h.candidate_entity_id = ?"
            params.extend([entity_id, entity_id])

        params.append(limit)

        cur = conn.execute(
            f"""
            SELECT h.*, pe.name as primary_name, ce.name as candidate_name
            FROM entity_merge_history h
            LEFT JOIN entities pe ON pe.id = h.primary_entity_id
            LEFT JOIN entities ce ON ce.id = h.candidate_entity_id
            {where_sql}
            ORDER BY datetime(h.created_at) DESC, h.id DESC
            LIMIT ?;
            """,
            tuple(params),
        )
        history = []
        for row in cur.fetchall():
            item = dict(row)
            history.append(item)
        return history
    finally:
        conn.close()


def get_topic_timeline(db_path: str, topic_name: str, days: int = 14) -> list[dict[str, Any]]:
    """Get timeline data for a specific topic."""
    conn = connect(db_path)
    try:
        from datetime import datetime, timedelta, timezone
        
        # Generate date range
        end_date = datetime.now(tz=timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        cur = conn.execute(
            """
            WITH date_series AS (
                SELECT date(?, '+' || (n || ' days')) as date_point
                FROM (SELECT 0 as n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 
                      UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7
                      UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10 UNION ALL SELECT 11
                      UNION ALL SELECT 12 UNION ALL SELECT 13)
                WHERE date_point <= date(?)
            )
            SELECT 
                ds.date_point as date,
                COUNT(DISTINCT a.id) as count,
                COALESCE(AVG(s.discovery_score), 0) as avgScore
            FROM date_series ds
            LEFT JOIN artifacts a ON date(a.published_at) = ds.date_point
            LEFT JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN topics t ON at.topic_id = t.id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE (t.name = ? OR ? IS NULL)
            GROUP BY ds.date_point
            ORDER BY ds.date_point;
            """,
            (start_date.isoformat(), end_date.isoformat(), topic_name, topic_name)
        )
        
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ============================================================================
# Signal/Snapshot Database Functions (map tweets -> signals)
# ============================================================================

def list_signals(
    db_path: str,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    source: str | None = None,
    sort: str = "createdAt",
    order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """List signals (mapped from tweets) with pagination and filters.
    
    Returns: (signals_list, total_count)
    """
    conn = connect(db_path)
    try:
        # Build WHERE clause
        where_conditions: list[str] = []
        params: list[str | int] = []
        
        if search:
            where_conditions.append("(text LIKE ? OR author_username LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
        
        if status:
            # Map status to category/sentiment/notified state
            # For MVP: active = has salience, paused = no salience, error = failed analysis
            if status == "active":
                where_conditions.append("salience IS NOT NULL")
            elif status == "paused":
                where_conditions.append("salience IS NULL AND category IS NOT NULL")
            elif status == "error":
                where_conditions.append("category IS NULL AND inserted_at IS NOT NULL")
            elif status == "inactive":
                where_conditions.append("notified_at IS NOT NULL")
        
        if source:
            where_conditions.append("source = ?")
            params.append(source)
        
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
        
        # Get total count
        count_sql = f"SELECT COUNT(*) FROM tweets {where_clause};"
        cursor = conn.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        # Build ORDER BY clause
        sort_column_map = {
            "name": "author_username",
            "status": "salience",
            "lastSeenAt": "created_at",
            "createdAt": "inserted_at",
            "updatedAt": "updated_at",
        }
        sort_column = sort_column_map.get(sort, "inserted_at")
        order_dir = "DESC" if order == "desc" else "ASC"
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get paginated results
        query_sql = f"""
            SELECT * FROM tweets
            {where_clause}
            ORDER BY {sort_column} {order_dir}
            LIMIT ? OFFSET ?;
        """
        params.extend([page_size, offset])
        cursor = conn.execute(query_sql, params)
        
        signals = []
        for row in cursor.fetchall():
            signals.append(_tweet_to_signal(dict(row)))
        
        return signals, total
    finally:
        conn.close()


def _tweet_to_signal(tweet: dict[str, Any]) -> dict[str, Any]:
    """Convert a tweet database row to a Signal object."""
    # Determine status based on tweet state
    status = "active"
    if tweet.get("notified_at"):
        status = "inactive"
    elif tweet.get("salience") is None:
        if tweet.get("category") is None:
            status = "error"
        else:
            status = "paused"
    
    # Parse tags from JSON
    tags = []
    if tweet.get("tags"):
        try:
            tags = json.loads(tweet["tags"])
        except (json.JSONDecodeError, TypeError):
            tags = []
    
    return {
        "id": tweet["tweet_id"],
        "name": tweet.get("author_username") or f"User {tweet['author_id']}",
        "source": tweet.get("source") or "x",
        "status": status,
        "tags": tags if tags else None,
        "lastSeenAt": tweet.get("created_at"),
        "createdAt": tweet.get("inserted_at") or tweet.get("created_at") or utc_now_iso(),
        "updatedAt": tweet.get("updated_at") or tweet.get("inserted_at") or utc_now_iso(),
    }


def get_signal(db_path: str, signal_id: str) -> dict[str, Any] | None:
    """Get a specific signal by ID (tweet_id)."""
    tweet = get_tweet(db_path, signal_id)
    if not tweet:
        return None
    return _tweet_to_signal(dict(tweet))


def update_signal(db_path: str, signal_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update a signal (tweet).
    
    Supported updates: status, tags, name (author_username), source
    """
    conn = connect(db_path)
    try:
        # Build UPDATE statement
        set_clauses: list[str] = []
        params: list[str | None] = []
        
        if "status" in updates:
            # Map status back to database fields
            status = updates["status"]
            if status == "active":
                # Set salience if not set
                set_clauses.append("salience = COALESCE(salience, 50.0)")
            elif status == "paused":
                # Clear salience
                set_clauses.append("salience = NULL")
            elif status == "inactive":
                # Set notified_at
                set_clauses.append("notified_at = ?")
                params.append(utc_now_iso())
            elif status == "error":
                # Clear category
                set_clauses.append("category = NULL")
        
        if "tags" in updates:
            set_clauses.append("tags = ?")
            params.append(json.dumps(updates["tags"]) if updates["tags"] else None)
        
        if "name" in updates:
            set_clauses.append("author_username = ?")
            params.append(updates["name"])
        
        if "source" in updates:
            set_clauses.append("source = ?")
            params.append(updates["source"])
        
        # Always update updated_at
        set_clauses.append("updated_at = ?")
        params.append(utc_now_iso())
        
        if not set_clauses:
            # No updates provided
            return get_signal(db_path, signal_id)
        
        # Execute update
        params.append(signal_id)
        update_sql = f"""
            UPDATE tweets
            SET {', '.join(set_clauses)}
            WHERE tweet_id = ?;
        """
        
        with conn:
            conn.execute(update_sql, params)
        
        # Return updated signal
        return get_signal(db_path, signal_id)
    finally:
        conn.close()


def delete_signal(db_path: str, signal_id: str) -> bool:
    """Delete a signal (tweet) by ID.
    
    Returns: True if deleted, False if not found
    """
    conn = connect(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM tweets WHERE tweet_id = ?;", (signal_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def get_signals_stats(db_path: str) -> dict[str, int]:
    """Get signal statistics."""
    conn = connect(db_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM tweets;")
        total = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE salience IS NOT NULL;")
        active = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE salience IS NULL AND category IS NOT NULL;")
        paused = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE category IS NULL AND inserted_at IS NOT NULL;")
        error = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE notified_at IS NOT NULL;")
        inactive = cursor.fetchone()[0]
        
        return {
            "total": total,
            "active": active,
            "paused": paused,
            "error": error,
            "inactive": inactive,
        }
    finally:
        conn.close()


def create_signal(db_path: str, name: str, source: str, status: str, tags: list[str] | None = None) -> dict[str, Any]:
    """Create a new signal (tweet).
    
    For MVP, this creates a minimal tweet entry.
    """
    conn = connect(db_path)
    try:
        # Generate a unique tweet_id
        tweet_id = str(int(time.time() * 1000000))  # Microsecond timestamp as ID
        
        now = utc_now_iso()
        
        # Map status to database fields
        salience = None
        category = None
        notified_at = None
        
        if status == "active":
            salience = 50.0
            category = "feature_request"  # Default category
        elif status == "paused":
            category = "feature_request"
        elif status == "inactive":
            salience = 50.0
            category = "feature_request"
            notified_at = now
        
        tags_json = json.dumps(tags) if tags else None
        
        with conn:
            conn.execute(
                """
                INSERT INTO tweets (
                    tweet_id, source, text, author_username, author_id,
                    created_at, inserted_at, updated_at,
                    category, salience, notified_at, tags, lang
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    tweet_id,
                    source,
                    f"Signal: {name}",  # Placeholder text
                    name,
                    "signal_user",
                    now,
                    now,
                    now,
                    category,
                    salience,
                    notified_at,
                    tags_json,
                    "en",
                ),
            )
        
        return _tweet_to_signal({
            "tweet_id": tweet_id,
            "source": source,
            "text": f"Signal: {name}",
            "author_username": name,
            "author_id": "signal_user",
            "created_at": now,
            "inserted_at": now,
            "updated_at": now,
            "category": category,
            "salience": salience,
            "notified_at": notified_at,
            "tags": tags_json,
            "lang": "en",
        })
    finally:
        conn.close()


def list_snapshots(
    db_path: str,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    signal_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List snapshots with pagination and filters.
    
    Args:
        db_path: Path to SQLite database
        page: Page number (1-indexed)
        page_size: Items per page
        search: Search by signal name (author_username)
        status: Filter by snapshot status (ready/processing/failed)
        signal_id: Filter by signal ID
    
    Returns: (snapshots_list, total_count)
    """
    conn = connect(db_path)
    try:
        # Build WHERE clause
        where_parts = []
        params: list[Any] = []
        
        if status:
            where_parts.append("s.status = ?")
            params.append(status)
        
        if signal_id:
            where_parts.append("s.signal_id = ?")
            params.append(signal_id)
        
        if search:
            where_parts.append("t.author_username LIKE ?")
            params.append(f"%{search}%")
        
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        # Count total
        count_query = f"""
            SELECT COUNT(*) as cnt
            FROM snapshots s
            LEFT JOIN tweets t ON s.signal_id = t.tweet_id
            {where_clause}
        """
        cur = conn.execute(count_query, params)
        total = cur.fetchone()["cnt"]
        
        # Fetch page
        offset = (page - 1) * page_size
        list_query = f"""
            SELECT 
                s.id,
                s.signal_id,
                s.status,
                s.size_kb,
                s.file_path,
                s.created_at,
                t.author_username as signal_name
            FROM snapshots s
            LEFT JOIN tweets t ON s.signal_id = t.tweet_id
            {where_clause}
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])
        cur = conn.execute(list_query, params)
        
        snapshots = []
        for row in cur.fetchall():
            snapshots.append({
                "id": row["id"],
                "signalId": row["signal_id"],
                "signalName": row["signal_name"],
                "status": row["status"],
                "sizeKb": row["size_kb"],
                "createdAt": row["created_at"],
            })
        
        return snapshots, total
    finally:
        conn.close()


def get_snapshot(db_path: str, snapshot_id: str) -> dict[str, Any] | None:
    """Get a specific snapshot by ID.
    
    Args:
        db_path: Path to SQLite database
        snapshot_id: Snapshot ID
    
    Returns: Snapshot dict or None if not found
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT 
                s.id,
                s.signal_id,
                s.status,
                s.size_kb,
                s.file_path,
                s.created_at,
                t.author_username as signal_name
            FROM snapshots s
            LEFT JOIN tweets t ON s.signal_id = t.tweet_id
            WHERE s.id = ?
            """,
            (snapshot_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "id": row["id"],
            "signalId": row["signal_id"],
            "signalName": row["signal_name"],
            "status": row["status"],
            "sizeKb": row["size_kb"],
            "createdAt": row["created_at"],
        }
    finally:
        conn.close()


def create_snapshot(
    db_path: str,
    signal_id: str,
    file_path: str | None = None,
    size_kb: int | None = None,
) -> dict[str, Any]:
    """Create a new snapshot record.
    
    Args:
        db_path: Path to SQLite database
        signal_id: ID of the signal to snapshot
        file_path: Optional file path where snapshot is stored
        size_kb: Optional size in KB
    
    Returns: Created snapshot dict
    """
    import uuid
    
    conn = connect(db_path)
    try:
        snapshot_id = str(uuid.uuid4())
        now = utc_now_iso()
        status = "ready" if file_path else "processing"
        
        with conn:
            conn.execute(
                """
                INSERT INTO snapshots (id, signal_id, status, size_kb, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, signal_id, status, size_kb, file_path, now)
            )
        
        # Fetch signal name
        cur = conn.execute(
            "SELECT author_username FROM tweets WHERE tweet_id = ?",
            (signal_id,)
        )
        row = cur.fetchone()
        signal_name = row["author_username"] if row else None
        
        return {
            "id": snapshot_id,
            "signalId": signal_id,
            "signalName": signal_name,
            "status": status,
            "sizeKb": size_kb,
            "createdAt": now,
        }
    finally:
        conn.close()


def update_snapshot_status(
    db_path: str,
    snapshot_id: str,
    status: str,
    size_kb: int | None = None,
    file_path: str | None = None,
) -> None:
    """Update snapshot status and optional metadata.
    
    Args:
        db_path: Path to SQLite database
        snapshot_id: Snapshot ID to update
        status: New status (ready/processing/failed)
        size_kb: Optional size in KB
        file_path: Optional file path
    """
    conn = connect(db_path)
    try:
        with conn:
            updates = ["status = ?"]
            params: list[Any] = [status]
            
            if size_kb is not None:
                updates.append("size_kb = ?")
                params.append(size_kb)
            
            if file_path is not None:
                updates.append("file_path = ?")
                params.append(file_path)
            
            params.append(snapshot_id)
            
            conn.execute(
                f"UPDATE snapshots SET {', '.join(updates)} WHERE id = ?",
                params
            )
    finally:
        conn.close()


# Cross-Source Corroboration: Artifact Relationships


def create_artifact_relationship(
    db_path: str,
    source_artifact_id: int,
    target_artifact_id: int,
    relationship_type: str,
    confidence: float = 0.0,
    detection_method: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    """Create a relationship between two artifacts.
    
    Args:
        db_path: Path to SQLite database
        source_artifact_id: ID of source artifact
        target_artifact_id: ID of target artifact
        relationship_type: Type of relationship (cite, reference, discuss, implement, mention)
        confidence: Confidence score 0.0-1.0
        detection_method: Method used to detect relationship
        metadata: Additional metadata as JSON
    
    Returns:
        Relationship ID or None if duplicate
    """
    conn = connect(db_path)
    try:
        now = utc_now_iso()
        metadata_json = json.dumps(metadata) if metadata else None
        
        with conn:
            try:
                return _insert_and_return_id(
                    conn,
                    db_path,
                    """
                    INSERT INTO artifact_relationships (
                        source_artifact_id, target_artifact_id, relationship_type,
                        confidence, detection_method, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_artifact_id,
                        target_artifact_id,
                        relationship_type,
                        confidence,
                        detection_method,
                        metadata_json,
                        now,
                    ),
                )
            except INTEGRITY_ERRORS:
                # Duplicate relationship, update confidence if higher
                conn.execute(
                    """
                    UPDATE artifact_relationships
                    SET confidence = CASE
                            WHEN ? >= COALESCE(confidence, -1) THEN ?
                            ELSE confidence
                        END,
                        detection_method = COALESCE(?, detection_method),
                        metadata_json = COALESCE(?, metadata_json)
                    WHERE source_artifact_id = ? AND target_artifact_id = ? AND relationship_type = ?
                    """,
                    (
                        confidence,
                        confidence,
                        detection_method,
                        metadata_json,
                        source_artifact_id,
                        target_artifact_id,
                        relationship_type,
                    ),
                )
                return None
    finally:
        conn.close()


def get_artifact_relationships(
    db_path: str,
    artifact_id: int,
    direction: str = "both",
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """Get relationships for an artifact.
    
    Args:
        db_path: Path to SQLite database
        artifact_id: Artifact ID
        direction: "outgoing", "incoming", or "both"
        min_confidence: Minimum confidence threshold
    
    Returns:
        List of relationship dictionaries
    """
    conn = connect(db_path)
    try:
        with conn:
            if direction == "outgoing":
                query = """
                    SELECT ar.*, a.title as target_title, a.source as target_source, a.type as target_type
                    FROM artifact_relationships ar
                    JOIN artifacts a ON ar.target_artifact_id = a.id
                    WHERE ar.source_artifact_id = ? AND ar.confidence >= ?
                    ORDER BY ar.confidence DESC
                """
                params = (artifact_id, min_confidence)
            elif direction == "incoming":
                query = """
                    SELECT ar.*, a.title as source_title, a.source as source_source, a.type as source_type
                    FROM artifact_relationships ar
                    JOIN artifacts a ON ar.source_artifact_id = a.id
                    WHERE ar.target_artifact_id = ? AND ar.confidence >= ?
                    ORDER BY ar.confidence DESC
                """
                params = (artifact_id, min_confidence)
            else:  # both
                query = """
                    SELECT ar.*,
                           a_source.title as source_title,
                           a_source.source as source_source,
                           a_source.type as source_type,
                           a_target.title as target_title,
                           a_target.source as target_source,
                           a_target.type as target_type
                    FROM artifact_relationships ar
                    JOIN artifacts a_source ON ar.source_artifact_id = a_source.id
                    JOIN artifacts a_target ON ar.target_artifact_id = a_target.id
                    WHERE (ar.source_artifact_id = ? OR ar.target_artifact_id = ?)
                      AND ar.confidence >= ?
                    ORDER BY ar.confidence DESC
                """
                params = (artifact_id, artifact_id, min_confidence)
            
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            
            relationships = []
            for row in rows:
                rel = dict(row)
                # Parse metadata JSON
                if rel.get("metadata_json"):
                    try:
                        rel["metadata"] = json.loads(rel["metadata_json"])
                    except Exception:
                        rel["metadata"] = {}
                else:
                    rel["metadata"] = {}
                del rel["metadata_json"]
                
                relationships.append(rel)
            
            return relationships
    finally:
        conn.close()


def get_relationship_stats(db_path: str) -> dict[str, Any]:
    """Get statistics about artifact relationships.
    
    Returns:
        Dictionary with relationship statistics
    """
    conn = connect(db_path)
    try:
        with conn:
            # Total relationships
            cur = conn.execute("SELECT COUNT(*) as total FROM artifact_relationships")
            total = cur.fetchone()["total"]
            
            # By type
            cur = conn.execute(
                """
                SELECT relationship_type, COUNT(*) as count, AVG(confidence) as avg_confidence
                FROM artifact_relationships
                GROUP BY relationship_type
                ORDER BY count DESC
                """
            )
            by_type = [dict(row) for row in cur.fetchall()]
            
            # High confidence relationships (>= 0.8)
            cur = conn.execute(
                "SELECT COUNT(*) as count FROM artifact_relationships WHERE confidence >= 0.8"
            )
            high_confidence = cur.fetchone()["count"]
            
            # Artifacts with relationships
            cur = conn.execute(
                """
                SELECT COUNT(DISTINCT artifact_id) as count FROM (
                    SELECT source_artifact_id as artifact_id FROM artifact_relationships
                    UNION
                    SELECT target_artifact_id as artifact_id FROM artifact_relationships
                )
                """
            )
            artifacts_with_relationships = cur.fetchone()["count"]
            
            return {
                "total_relationships": total,
                "high_confidence_count": high_confidence,
                "artifacts_with_relationships": artifacts_with_relationships,
                "by_type": by_type,
            }
    finally:
        conn.close()
# ============================================================================
# Topic Evolution Database Functions
# ============================================================================


def get_topic_by_id(db_path: str, topic_id: int) -> dict[str, Any] | None:
    """Get a specific topic by ID.
    
    Args:
        db_path: Path to SQLite database
        topic_id: Topic ID
    
    Returns:
        Topic dict or None if not found
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT 
                id,
                name,
                taxonomy_path,
                description,
                created_at,
                updated_at
            FROM topics
            WHERE id = ?;
            """,
            (topic_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_topic_evolution_events(
    db_path: str,
    topic_id: int,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get evolution events for a topic.
    
    Args:
        db_path: Path to SQLite database
        topic_id: Topic ID
        event_type: Optional filter by event type
        limit: Maximum number of events to return
    
    Returns:
        List of evolution events
    """
    conn = connect(db_path)
    try:
        where_conditions = ["topic_id = ?"]
        params: list[str | int] = [topic_id]
        
        if event_type:
            where_conditions.append("event_type = ?")
            params.append(event_type)
        
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        cur = conn.execute(
            f"""
            SELECT 
                id,
                topic_id,
                event_type,
                related_topic_ids,
                event_strength,
                event_date,
                description,
                created_at
            FROM topic_evolution
            {where_clause}
            ORDER BY event_date DESC
            LIMIT ?;
            """,
            (*params, limit)
        )
        
        events = []
        for row in cur.fetchall():
            events.append(dict(row))
        
        return events
    finally:
        conn.close()


def get_topic_artifact_history(
    db_path: str,
    topic_id: int,
    days: int = 90,
) -> list[dict[str, Any]]:
    """Get historical artifact data for a topic.
    
    Returns list of daily artifact counts and average scores.
    """
    conn = connect(db_path)
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat().replace('+00:00', 'Z')
        
        cur = conn.execute(
            """
            SELECT 
                date(a.published_at) as date,
                COUNT(DISTINCT a.id) as artifact_count,
                AVG(s.discovery_score) as avg_discovery_score,
                AVG(s.novelty) as avg_novelty,
                AVG(s.emergence) as avg_emergence,
                AVG(s.obscurity) as avg_obscurity
            FROM artifacts a
            JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN scores s ON a.id = s.artifact_id
            WHERE at.topic_id = ?
              AND a.published_at >= ?
            GROUP BY date(a.published_at)
            ORDER BY date(a.published_at);
            """,
            (topic_id, cutoff)
        )
        
        return [dict(row) for row in cur.fetchall()]
        
    finally:
        conn.close()

