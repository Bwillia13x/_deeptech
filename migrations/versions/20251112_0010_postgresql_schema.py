"""
PostgreSQL schema migration - Convert SQLite schema to PostgreSQL

This migration converts the existing SQLite schema to PostgreSQL-compatible DDL.
Key changes:
- TEXT PRIMARY KEY → VARCHAR with appropriate length limits
- INTEGER → BIGINT for IDs where appropriate
- REAL → DOUBLE PRECISION for floating point
- JSON validation and JSONB for better performance
- Add proper sequences for auto-increment columns
- Convert SQLite-specific pragmas to PostgreSQL equivalents
- Maintain all existing indexes and constraints

Revision ID: 20251112_0010
Revises: 20251111_0009
Create Date: 2025-11-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251112_0010"
down_revision = "20251111_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade to PostgreSQL schema.
    
    This migration should only be run when migrating from SQLite to PostgreSQL.
    It creates all tables with PostgreSQL-specific types and optimizations.
    """
    
    # Check if we're running on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print(f"Skipping PostgreSQL migration - current dialect is {bind.dialect.name}")
        return
    
    # Check if tables already exist (fresh PostgreSQL install)
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # If earlier SQLite-compatible tables exist (default after previous migrations),
    # drop them so we can recreate the optimized PostgreSQL schema in-place.
    drop_order = [
        'snapshots',
        'discovery_labels',
        'experiment_runs',
        'experiments',
        'topic_similarity',
        'artifact_relationships',
        'artifact_entities',
        'entities',
        'artifact_topics',
        'topics',
        'artifact_classifications',
        'artifact_scores',
        'artifacts',
        'beta_users',
        'cursors',
        'tweets',
    ]

    if any(table in existing_tables for table in drop_order):
        print("Detected existing SQLite-era tables; dropping before applying PostgreSQL schema")
        for table in drop_order:
            if table in existing_tables:
                op.drop_table(table)
    
    # 1. Core tweets/signals table
    op.create_table(
        'tweets',
        sa.Column('tweet_id', sa.String(64), primary_key=True),
        sa.Column('source', sa.String(32), nullable=False, server_default='x'),
        sa.Column('query_names', sa.Text, nullable=True),
        sa.Column('text', sa.Text, nullable=True),
        sa.Column('author_id', sa.String(64), nullable=True),
        sa.Column('author_username', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lang', sa.String(10), nullable=True),
        sa.Column('like_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('retweet_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('reply_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('quote_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('category', sa.String(64), nullable=True),
        sa.Column('sentiment', sa.String(32), nullable=True),
        sa.Column('urgency', sa.Integer, nullable=True),
        sa.Column('tags', postgresql.JSONB, nullable=True),
        sa.Column('reasoning', sa.Text, nullable=True),
        sa.Column('salience', sa.Double, nullable=True),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_json', postgresql.JSONB, nullable=True),
        sa.Column('inserted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_tweets_created_at', 'tweets', ['created_at'])
    op.create_index('idx_tweets_salience', 'tweets', ['salience'])
    op.create_index('idx_tweets_notified', 'tweets', ['notified_at'])
    op.create_index('idx_tweets_source', 'tweets', ['source'])
    
    # 2. Cursors table for pagination
    op.create_table(
        'cursors',
        sa.Column('name', sa.String(128), primary_key=True),
        sa.Column('since_id', sa.String(64), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # 3. Artifacts table (Phase One discoveries)
    op.create_table(
        'artifacts',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('external_id', sa.String(128), nullable=False),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('url', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_artifacts_source', 'artifacts', ['source'])
    op.create_index('idx_artifacts_external_id', 'artifacts', ['external_id'])
    op.create_index('idx_artifacts_published_at', 'artifacts', ['published_at'])
    op.create_index('idx_artifacts_source_external', 'artifacts', ['source', 'external_id'], unique=True)
    op.create_index('idx_artifacts_published_source', 'artifacts', [sa.text('published_at DESC'), 'source'])
    
    # 4. Artifact scores table
    op.create_table(
        'artifact_scores',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('discovery_score', sa.Double, nullable=False, server_default='0.0'),
        sa.Column('novelty_score', sa.Double, nullable=False, server_default='0.0'),
        sa.Column('impact_score', sa.Double, nullable=False, server_default='0.0'),
        sa.Column('credibility_score', sa.Double, nullable=False, server_default='0.0'),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_scores_artifact_id', 'artifact_scores', ['artifact_id'], unique=True)
    op.create_index('idx_scores_discovery', 'artifact_scores', [sa.text('discovery_score DESC')])
    op.create_index('idx_artifact_scores_discovery_composite', 'artifact_scores', 
                    [sa.text('discovery_score DESC'), 'artifact_id'])
    
    # 5. Topics table
    op.create_table(
        'topics',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(256), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_topics_name', 'topics', ['name'])
    
    # 6. Artifact-Topic relationship table
    op.create_table(
        'artifact_topics',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('topic_id', sa.BigInteger, sa.ForeignKey('topics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('confidence', sa.Double, nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_artifact_topics_artifact', 'artifact_topics', ['artifact_id'])
    op.create_index('idx_artifact_topics_topic', 'artifact_topics', ['topic_id'])
    op.create_index('idx_artifact_topics_unique', 'artifact_topics', ['artifact_id', 'topic_id'], unique=True)
    op.create_index('idx_artifact_topics_topic_artifact', 'artifact_topics', ['topic_id', 'artifact_id'])
    
    # 7. Entities table (researchers, organizations)
    op.create_table(
        'entities',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('entity_type', sa.String(32), nullable=False),
        sa.Column('affiliation', sa.String(256), nullable=True),
        sa.Column('domain', sa.String(128), nullable=True),
        sa.Column('social_accounts', postgresql.JSONB, nullable=True),
        sa.Column('influence_score', sa.Double, nullable=False, server_default='0.0'),
        sa.Column('last_activity_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_entities_name', 'entities', ['name'])
    op.create_index('idx_entities_type', 'entities', ['entity_type'])
    op.create_index('idx_entities_influence', 'entities', [sa.text('influence_score DESC')])
    op.create_index('idx_entities_activity_influence', 'entities', 
                    [sa.text('last_activity_date DESC'), sa.text('influence_score DESC')])
    
    # 8. Artifact-Entity relationship table
    op.create_table(
        'artifact_entities',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', sa.BigInteger, sa.ForeignKey('entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(32), nullable=True),
        sa.Column('confidence', sa.Double, nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_artifact_entities_artifact', 'artifact_entities', ['artifact_id'])
    op.create_index('idx_artifact_entities_entity', 'artifact_entities', ['entity_id'])
    op.create_index('idx_artifact_entities_unique', 'artifact_entities', ['artifact_id', 'entity_id'], unique=True)
    
    # 9. Artifact relationships table (cross-source corroboration)
    op.create_table(
        'artifact_relationships',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('source_artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relationship_type', sa.String(32), nullable=False),
        sa.Column('confidence', sa.Double, nullable=False, server_default='1.0'),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_relationships_source', 'artifact_relationships', ['source_artifact_id'])
    op.create_index('idx_relationships_target', 'artifact_relationships', ['target_artifact_id'])
    op.create_index('idx_relationships_type', 'artifact_relationships', ['relationship_type'])
    op.create_index('idx_relationships_confidence', 'artifact_relationships', [sa.text('confidence DESC')])
    op.create_index('idx_relationships_unique', 'artifact_relationships', 
                    ['source_artifact_id', 'target_artifact_id', 'relationship_type'], unique=True)
    op.create_index('idx_relationships_source_confidence', 'artifact_relationships', 
                    ['source_artifact_id', sa.text('confidence DESC')])
    op.create_index('idx_relationships_target_confidence', 'artifact_relationships', 
                    ['target_artifact_id', sa.text('confidence DESC')])
    
    # 10. Topic similarity table
    op.create_table(
        'topic_similarity',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('topic_id_1', sa.BigInteger, sa.ForeignKey('topics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('topic_id_2', sa.BigInteger, sa.ForeignKey('topics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('similarity', sa.Double, nullable=False),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_topic_similarity_pair', 'topic_similarity', ['topic_id_1', 'topic_id_2'], unique=True)
    op.create_index('idx_topic_similarity_topic1_score', 'topic_similarity', 
                    ['topic_id_1', sa.text('similarity DESC')])
    op.create_index('idx_topic_similarity_topic2_score', 'topic_similarity', 
                    ['topic_id_2', sa.text('similarity DESC')])
    
    # 11. Experiments table (backtesting framework)
    op.create_table(
        'experiments',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(256), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('config_json', postgresql.JSONB, nullable=False),
        sa.Column('baseline_id', sa.BigInteger, sa.ForeignKey('experiments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_experiments_name', 'experiments', ['name'])
    op.create_index('idx_experiments_status', 'experiments', ['status'])
    op.create_index('idx_experiments_baseline', 'experiments', ['baseline_id'])
    
    # 12. Experiment runs table
    op.create_table(
        'experiment_runs',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('experiment_id', sa.BigInteger, sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('true_positives', sa.Integer, nullable=False, server_default='0'),
        sa.Column('false_positives', sa.Integer, nullable=False, server_default='0'),
        sa.Column('true_negatives', sa.Integer, nullable=False, server_default='0'),
        sa.Column('false_negatives', sa.Integer, nullable=False, server_default='0'),
        sa.Column('precision', sa.Double, nullable=True),
        sa.Column('recall', sa.Double, nullable=True),
        sa.Column('f1_score', sa.Double, nullable=True),
        sa.Column('accuracy', sa.Double, nullable=True),
        sa.Column('config_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_experiment_runs_experiment', 'experiment_runs', ['experiment_id'])
    op.create_index('idx_experiment_runs_started', 'experiment_runs', [sa.text('started_at DESC')])
    op.create_index('idx_experiment_runs_experiment_started', 'experiment_runs', 
                    ['experiment_id', sa.text('started_at DESC')])
    
    # 13. Discovery labels table (ground truth)
    op.create_table(
        'discovery_labels',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('artifact_id', sa.BigInteger, sa.ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(32), nullable=False),
        sa.Column('confidence', sa.Double, nullable=False, server_default='1.0'),
        sa.Column('annotator', sa.String(128), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_discovery_labels_artifact', 'discovery_labels', ['artifact_id'], unique=True)
    op.create_index('idx_discovery_labels_label', 'discovery_labels', ['label'])
    op.create_index('idx_discovery_labels_confidence', 'discovery_labels', [sa.text('confidence DESC')])
    
    # 14. Snapshots table
    op.create_table(
        'snapshots',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('signal_id', sa.String(64), sa.ForeignKey('tweets.tweet_id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='processing'),
        sa.Column('size_kb', sa.Integer, nullable=True),
        sa.Column('file_path', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_snapshots_signal_id', 'snapshots', ['signal_id'])
    op.create_index('idx_snapshots_created_at', 'snapshots', ['created_at'])
    op.create_index('idx_snapshots_status', 'snapshots', ['status'])


def downgrade() -> None:
    """
    Downgrade from PostgreSQL schema.
    
    WARNING: This will drop all tables and data!
    Only use this when rolling back to SQLite in non-production environments.
    """
    
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print(f"Skipping PostgreSQL downgrade - current dialect is {bind.dialect.name}")
        return
    
    # Drop tables in reverse order of dependencies
    op.drop_table('snapshots')
    op.drop_table('discovery_labels')
    op.drop_table('experiment_runs')
    op.drop_table('experiments')
    op.drop_table('topic_similarity')
    op.drop_table('artifact_relationships')
    op.drop_table('artifact_entities')
    op.drop_table('entities')
    op.drop_table('artifact_topics')
    op.drop_table('topics')
    op.drop_table('artifact_scores')
    op.drop_table('artifacts')
    op.drop_table('cursors')
    op.drop_table('tweets')
