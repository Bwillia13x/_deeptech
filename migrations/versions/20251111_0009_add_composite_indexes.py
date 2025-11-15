"""
Add composite indexes for query performance optimization

This migration adds composite indexes to optimize common query patterns identified
in the discovery pipeline, topic evolution, and cross-source corroboration features.

Focus areas:
1. Top discoveries queries (artifact_scores.discovery_score + artifacts.published_at)
2. Topic timeline queries (artifact_topics.topic_id + artifacts.published_at)
3. Citation graph queries (artifact_relationships with confidence filtering)
4. Time-filtered discovery queries (artifacts.published_at + source)
5. Topic similarity lookups with score filtering

Revision ID: 20251111_0009
Revises: 20251111_0008
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251111_0009"
down_revision = "20251111_0008"
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Add composite indexes for query performance optimization."""
    
    bind = op.get_bind()
    
    # 1. Composite index for top discoveries query (most critical)
    # Query pattern: ORDER BY discovery_score DESC, published_at DESC with JOIN
    # This enables efficient sorting without full table scan
    if table_exists(bind, 'artifact_scores'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_artifact_scores_discovery_composite
            ON artifact_scores(discovery_score DESC, artifact_id);
            """
        )
    
    # 2. Composite index for topic timeline queries
    # Query pattern: WHERE topic_id = ? ORDER BY published_at DESC with artifact JOIN
    # Critical for Phase Two topic evolution analytics
    if table_exists(bind, 'artifact_topics'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_artifact_topics_topic_artifact
            ON artifact_topics(topic_id, artifact_id);
            """
        )
    
    # 3. Composite indexes for citation graph queries (cross-source corroboration)
    # Query pattern: WHERE source_artifact_id = ? AND confidence >= ? ORDER BY confidence DESC
    if table_exists(bind, 'artifact_relationships'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_relationships_source_confidence
            ON artifact_relationships(source_artifact_id, confidence DESC);
            """
        )
        
        # Query pattern: WHERE target_artifact_id = ? AND confidence >= ? ORDER BY confidence DESC
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_relationships_target_confidence
            ON artifact_relationships(target_artifact_id, confidence DESC);
            """
        )
    
    # 4. Composite index for time-filtered discovery queries
    # Query pattern: WHERE published_at >= ? AND source = ? ORDER BY published_at DESC
    # Enables efficient range scans with source filtering
    if table_exists(bind, 'artifacts'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_artifacts_published_source
            ON artifacts(published_at DESC, source);
            """
        )
    
    # 5. Composite indexes for topic similarity queries with score filtering
    # Query pattern: WHERE topic_id_1 = ? ORDER BY similarity DESC
    if table_exists(bind, 'topic_similarity'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_topic_similarity_topic1_score
            ON topic_similarity(topic_id_1, similarity DESC);
            """
        )
        
        # Query pattern: WHERE topic_id_2 = ? ORDER BY similarity DESC (bidirectional lookup)
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_topic_similarity_topic2_score
            ON topic_similarity(topic_id_2, similarity DESC);
            """
        )
    
    # 6. Composite index for entity influence scoring
    # Query pattern: WHERE last_activity_date >= ? ORDER BY influence_score DESC
    # Used for researcher ranking and profile analytics
    if table_exists(bind, 'entities'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_entities_activity_influence
            ON entities(last_activity_date DESC, influence_score DESC);
            """
        )
    
    # 7. Composite index for experiment runs by experiment and date
    # Query pattern: WHERE experiment_id = ? ORDER BY started_at DESC
    # Used for backtesting and A/B testing workflows
    if table_exists(bind, 'experiment_runs'):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment_started
            ON experiment_runs(experiment_id, started_at DESC);
            """
        )


def downgrade() -> None:
    """Remove composite indexes."""
    
    # Drop indexes in reverse order
    op.execute("DROP INDEX IF EXISTS idx_experiment_runs_experiment_started;")
    op.execute("DROP INDEX IF EXISTS idx_entities_activity_influence;")
    op.execute("DROP INDEX IF EXISTS idx_topic_similarity_topic2_score;")
    op.execute("DROP INDEX IF EXISTS idx_topic_similarity_topic1_score;")
    op.execute("DROP INDEX IF EXISTS idx_artifacts_published_source;")
    op.execute("DROP INDEX IF EXISTS idx_relationships_target_confidence;")
    op.execute("DROP INDEX IF EXISTS idx_relationships_source_confidence;")
    op.execute("DROP INDEX IF EXISTS idx_artifact_topics_topic_artifact;")
    op.execute("DROP INDEX IF EXISTS idx_artifact_scores_discovery_composite;")
