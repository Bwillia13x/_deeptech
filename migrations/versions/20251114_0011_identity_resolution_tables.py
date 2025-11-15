"""
Add core tables for entity resolution pipeline

- entities catalog
- social/accounts linkage
- merge/audit history tracking
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251114_0011"
down_revision = "20251112_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id BIGSERIAL PRIMARY KEY,
                type VARCHAR(32) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                homepage_url TEXT,
                metadata_json JSONB,
                merged_into_id BIGINT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (type, name)
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                homepage_url TEXT,
                metadata_json TEXT,
                merged_into_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (type, name)
            );
            """
        )

    op.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_entities_merged_into ON entities(merged_into_id);")

    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id BIGSERIAL PRIMARY KEY,
                entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                platform VARCHAR(50) NOT NULL,
                handle_or_id VARCHAR(255) NOT NULL,
                url TEXT,
                follower_count BIGINT,
                raw_json JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (entity_id, platform, handle_or_id)
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                platform TEXT NOT NULL,
                handle_or_id TEXT NOT NULL,
                url TEXT,
                follower_count INTEGER,
                raw_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (entity_id, platform, handle_or_id)
            );
            """
        )

    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_entity_id ON accounts(entity_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform);")

    if is_postgresql:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_merge_history (
                id BIGSERIAL PRIMARY KEY,
                primary_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                candidate_entity_id BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                decision VARCHAR(32) NOT NULL,
                similarity_score REAL,
                reviewer VARCHAR(255),
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_merge_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                candidate_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                decision TEXT NOT NULL,
                similarity_score REAL,
                reviewer TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

    op.execute("CREATE INDEX IF NOT EXISTS idx_entity_merge_primary ON entity_merge_history(primary_entity_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_entity_merge_created_at ON entity_merge_history(created_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_entity_merge_created_at;")
    op.execute("DROP INDEX IF EXISTS idx_entity_merge_primary;")
    op.execute("DROP INDEX IF EXISTS idx_accounts_platform;")
    op.execute("DROP INDEX IF EXISTS idx_accounts_entity_id;")
    op.execute("DROP INDEX IF EXISTS idx_entities_merged_into;")
    op.execute("DROP INDEX IF EXISTS idx_entities_type;")

    op.execute("DROP TABLE IF EXISTS entity_merge_history;")
    op.execute("DROP TABLE IF EXISTS accounts;")
    op.execute("DROP TABLE IF EXISTS entities;")
