"""
Initial schema for Signal Harvester

- tweets table
- cursors table
- performance indexes
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251108_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tweets table
    op.execute(
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
            tags TEXT,
            reasoning TEXT,
            salience REAL,
            notified_at TEXT,
            raw_json TEXT,
            inserted_at TEXT,
            updated_at TEXT
        );
        """
    )

    # Create cursors table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cursors (
            name TEXT PRIMARY KEY,
            since_id TEXT,
            updated_at TEXT
        );
        """
    )

    # Indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_salience ON tweets(salience);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tweets_notified ON tweets(notified_at);")



def downgrade() -> None:
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_tweets_notified;")
    op.execute("DROP INDEX IF EXISTS idx_tweets_salience;")
    op.execute("DROP INDEX IF EXISTS idx_tweets_created_at;")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS cursors;")
    op.execute("DROP TABLE IF EXISTS tweets;")
