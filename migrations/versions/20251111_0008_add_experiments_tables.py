"""
Add experiments and experiment_runs tables

This migration adds experiment tracking tables for backtesting
and A/B testing of discovery scoring algorithms.

Revision ID: 20251111_0008
Revises: 20251109_0004
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251111_0008"
down_revision = "20251109_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add experiments and experiment_runs tables."""
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'
    
    # Experiments table - stores experiment configurations
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL UNIQUE,
                description TEXT,
                config_json JSONB NOT NULL,
                baseline_id BIGINT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                FOREIGN KEY (baseline_id) REFERENCES experiments(id) ON DELETE SET NULL
            );
            """
        )
    else:
        op.execute(
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
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                id BIGSERIAL PRIMARY KEY,
                experiment_id BIGINT NOT NULL,
                artifact_count INTEGER NOT NULL DEFAULT 0,
                true_positives INTEGER NOT NULL DEFAULT 0,
                false_positives INTEGER NOT NULL DEFAULT 0,
                true_negatives INTEGER NOT NULL DEFAULT 0,
                false_negatives INTEGER NOT NULL DEFAULT 0,
                precision REAL,
                recall REAL,
                f1_score REAL,
                accuracy REAL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status VARCHAR(50) NOT NULL DEFAULT 'running',
                error_message TEXT,
                metadata_json JSONB,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
            );
            """
        )
    else:
        op.execute(
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
    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_labels (
                id BIGSERIAL PRIMARY KEY,
                artifact_id BIGINT NOT NULL,
                label VARCHAR(50) NOT NULL,
                confidence REAL DEFAULT 1.0,
                annotator VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
            );
            """
        )
    else:
        op.execute(
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiments_name ON experiments(name);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments(created_at);")
    
    # Indexes for experiment runs
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment_id ON experiment_runs(experiment_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_runs_started_at ON experiment_runs(started_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_runs_status ON experiment_runs(status);")
    
    # Indexes for discovery labels
    op.execute("CREATE INDEX IF NOT EXISTS idx_discovery_labels_artifact_id ON discovery_labels(artifact_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_discovery_labels_label ON discovery_labels(label);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_discovery_labels_artifact ON discovery_labels(artifact_id);")


def downgrade() -> None:
    """Remove experiments and experiment_runs tables."""
    op.execute("DROP TABLE IF EXISTS discovery_labels;")
    op.execute("DROP TABLE IF EXISTS experiment_runs;")
    op.execute("DROP TABLE IF EXISTS experiments;")
