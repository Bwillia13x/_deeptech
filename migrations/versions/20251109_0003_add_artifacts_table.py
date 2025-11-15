"""
Add artifacts table for discovery pipeline

This migration adds the artifacts table to support the discovery pipeline
features including arXiv papers, GitHub repos/releases, and Facebook posts.

Revision ID: 20251109_0003
Revises: 20251108_0002
Create Date: 2025-11-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251109_0003"
down_revision = "20251108_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'
    
    # Create artifacts table with dialect-aware syntax
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id BIGSERIAL PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                source_id VARCHAR(500) NOT NULL UNIQUE,
                title TEXT,
                text TEXT,
                url TEXT,
                published_at TIMESTAMP,
                author_entity_ids TEXT,
                raw_json JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL UNIQUE,
                title TEXT,
                text TEXT,
                url TEXT,
                published_at TEXT,
                author_entity_ids TEXT,
                raw_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    # Create indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_published_at ON artifacts(published_at);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_source_id ON artifacts(source_id);")

    # Create artifact_classifications table for discovery scoring
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_classifications (
                id BIGSERIAL PRIMARY KEY,
                artifact_id BIGINT NOT NULL,
                category VARCHAR(100),
                sentiment VARCHAR(50),
                urgency INTEGER,
                tags TEXT,
                topics TEXT,
                entities TEXT,
                reasoning TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER NOT NULL,
                category TEXT,
                sentiment TEXT,
                urgency INTEGER,
                tags TEXT,
                topics TEXT,
                entities TEXT,
                reasoning TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
            );
            """
        )

    # Create index for artifact classifications
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_class_artifact_id ON artifact_classifications(artifact_id);")

    # Create artifact_scores table for discovery scoring
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_scores (
                id BIGSERIAL PRIMARY KEY,
                artifact_id BIGINT NOT NULL,
                novelty_score REAL DEFAULT 0.0,
                emergence_score REAL DEFAULT 0.0,
                obscurity_score REAL DEFAULT 0.0,
                cross_source_score REAL DEFAULT 0.0,
                expert_signal_score REAL DEFAULT 0.0,
                discovery_score REAL DEFAULT 0.0,
                notified_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER NOT NULL,
                novelty_score REAL DEFAULT 0.0,
                emergence_score REAL DEFAULT 0.0,
                obscurity_score REAL DEFAULT 0.0,
                cross_source_score REAL DEFAULT 0.0,
                expert_signal_score REAL DEFAULT 0.0,
                discovery_score REAL DEFAULT 0.0,
                notified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
            );
            """
        )

    # Create indexes for artifact scores
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_scores_artifact_id ON artifact_scores(artifact_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_scores_discovery_score ON artifact_scores(discovery_score);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_scores_notified ON artifact_scores(notified_at);")


def downgrade() -> None:
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_artifact_scores_notified;")
    op.execute("DROP INDEX IF EXISTS idx_artifact_scores_discovery_score;")
    op.execute("DROP INDEX IF EXISTS idx_artifact_scores_artifact_id;")
    op.execute("DROP INDEX IF EXISTS idx_artifact_class_artifact_id;")
    op.execute("DROP INDEX IF EXISTS idx_artifacts_source_id;")
    op.execute("DROP INDEX IF EXISTS idx_artifacts_published_at;")
    op.execute("DROP INDEX IF EXISTS idx_artifacts_type;")
    op.execute("DROP INDEX IF EXISTS idx_artifacts_source;")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS artifact_scores;")
    op.execute("DROP TABLE IF EXISTS artifact_classifications;")
    op.execute("DROP TABLE IF EXISTS artifacts;")
