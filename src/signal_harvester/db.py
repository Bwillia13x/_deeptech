from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, cast

from .logger import get_logger
from .utils import utc_now_iso

log = get_logger(__name__)


def _ensure_lastrowid(rowid: int | None) -> int:
    if rowid is None:
        raise RuntimeError("Database insert did not return a row id")
    return rowid


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
    
    
    # Migration 3: Phase One - Deep Tech Discovery tables
    if current_version < 3:
        log.info("Applying migration 3: Phase One Deep Tech Discovery tables")
        conn = connect(db_path)
        try:
            with conn:
                # Entities table - People, Labs, Organizations
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entities (
                        id INTEGER PRIMARY KEY,
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
                    """
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY,
                        entity_id INTEGER NOT NULL,
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
                    """
                    CREATE TABLE IF NOT EXISTS artifacts (
                        id INTEGER PRIMARY KEY,
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
                    """
                    CREATE TABLE IF NOT EXISTS topics (
                        id INTEGER PRIMARY KEY,
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
                    """
                    CREATE TABLE IF NOT EXISTS artifact_topics (
                        artifact_id INTEGER NOT NULL,
                        topic_id INTEGER NOT NULL,
                        confidence REAL,
                        FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
                        FOREIGN KEY(topic_id) REFERENCES topics(id)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artopics_artifact ON artifact_topics(artifact_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_artopics_topic ON artifact_topics(topic_id);")
                
                # Scores table - Novelty, emergence, obscurity, discovery
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scores (
                        artifact_id INTEGER PRIMARY KEY,
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
                # Topic evolution events (merges, splits, emergence, decline)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS topic_evolution (
                        id INTEGER PRIMARY KEY,
                        topic_id INTEGER NOT NULL,
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
                    """
                    CREATE TABLE IF NOT EXISTS topic_similarity (
                        topic_id_1 INTEGER NOT NULL,
                        topic_id_2 INTEGER NOT NULL,
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
                    """
                    CREATE TABLE IF NOT EXISTS topic_clusters (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        topic_ids TEXT NOT NULL,
                        centroid_embedding TEXT,
                        cluster_quality REAL,
                        parent_cluster_id INTEGER,
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_classifications (
                        artifact_id INTEGER PRIMARY KEY,
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
                # Artifact relationships for citation graph
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_relationships (
                        id INTEGER PRIMARY KEY,
                        source_artifact_id INTEGER NOT NULL,
                        target_artifact_id INTEGER NOT NULL,
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
                # Experiments table - stores experiment configurations
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS experiments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        config_json TEXT NOT NULL,
                        baseline_id INTEGER,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'draft',
                        FOREIGN KEY (baseline_id) REFERENCES experiments(id) ON DELETE SET NULL
                    );
                    """
                )
                
                # Experiment runs table - stores execution results
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS experiment_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        experiment_id INTEGER NOT NULL,
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
                    """
                    CREATE TABLE IF NOT EXISTS discovery_labels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        artifact_id INTEGER NOT NULL,
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
                cur = conn.execute(
                    """
                    INSERT INTO entities (type, name, description, homepage_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (entity_type, name, description, homepage_url, now, now)
                )
                entity_id = _ensure_lastrowid(cur.lastrowid)
            
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
                cur = conn.execute(
                    """
                    INSERT INTO accounts (entity_id, platform, handle_or_id, url, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (entity_id, platform, handle_or_id, url, confidence, now)
                )
                account_id = _ensure_lastrowid(cur.lastrowid)
            
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
                cur = conn.execute(
                    """
                    INSERT INTO artifacts (type, source, source_id, title, text, url, published_at, 
                                         author_entity_ids, raw_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (artifact_type, source, source_id, title, text, url, published_at, 
                     author_ids_json, raw_json, now, now)
                )
                artifact_id = _ensure_lastrowid(cur.lastrowid)
            
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
                cur = conn.execute(
                    """
                    INSERT INTO topics (name, taxonomy_path, description, created_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (name, taxonomy_path, description, now)
                )
                topic_id = _ensure_lastrowid(cur.lastrowid)
            
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
                INSERT OR REPLACE INTO artifact_topics (artifact_id, topic_id, confidence)
                VALUES (?, ?, ?);
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
                INSERT OR REPLACE INTO scores (artifact_id, novelty, emergence, obscurity, discovery_score, computed_at)
                VALUES (?, ?, ?, ?, ?, ?);
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
                COALESCE(GROUP_CONCAT(DISTINCT t.taxonomy_path), '') AS topic_paths
            FROM artifacts a
            JOIN scores s ON a.id = s.artifact_id
            LEFT JOIN artifact_classifications ac ON a.id = ac.artifact_id
            LEFT JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN topics t ON at.topic_id = t.id
            WHERE {where}
            GROUP BY a.id
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
                COALESCE(GROUP_CONCAT(DISTINCT t.taxonomy_path), '') AS topic_paths
            FROM artifacts a
            JOIN scores s ON a.id = s.artifact_id
            LEFT JOIN artifact_classifications ac ON a.id = ac.artifact_id
            LEFT JOIN artifact_topics at ON a.id = at.artifact_id
            LEFT JOIN topics t ON at.topic_id = t.id
            WHERE {where}
            GROUP BY a.id
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
        
        entity = dict(entity_row)
        
        # Get accounts
        cur = conn.execute("SELECT * FROM accounts WHERE entity_id = ?;", (entity_id,))
        entity["accounts"] = [dict(r) for r in cur.fetchall()]
        
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
            entity = dict(row)
            # Get accounts for this entity
            account_cursor = conn.execute("SELECT * FROM accounts WHERE entity_id = ?;", (entity["id"],))
            entity["accounts"] = [dict(acc) for acc in account_cursor.fetchall()]
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
                cur = conn.execute(
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
                return _ensure_lastrowid(cur.lastrowid)
            except sqlite3.IntegrityError:
                # Duplicate relationship, update confidence if higher
                conn.execute(
                    """
                    UPDATE artifact_relationships
                    SET confidence = MAX(confidence, ?),
                        detection_method = COALESCE(?, detection_method),
                        metadata_json = COALESCE(?, metadata_json)
                    WHERE source_artifact_id = ? AND target_artifact_id = ? AND relationship_type = ?
                    """,
                    (
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
