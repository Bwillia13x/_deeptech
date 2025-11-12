"""
Add snapshots table

This migration adds the snapshots table to track signal snapshots
with metadata including status, size, and file paths.

Revision ID: 20251109_0004
Revises: 20251109_0003
Create Date: 2025-11-09
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251109_0004"
down_revision = "20251109_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add snapshots table."""
    op.execute(
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
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_signal_id ON snapshots(signal_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_status ON snapshots(status);")


def downgrade() -> None:
    """Remove snapshots table."""
    op.execute("DROP TABLE IF EXISTS snapshots;")
