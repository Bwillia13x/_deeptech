"""Add beta users table.

Revision ID: 20251108_0002
Revises: 20251108_0001
Create Date: 2024-11-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251108_0002'
down_revision = '20251108_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create beta_users table
    op.create_table(
        'beta_users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('invite_code', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('activated_at', sa.DateTime, nullable=True),
        sa.Column('metadata', sa.Text, nullable=True),
    )
    
    # Create indexes
    op.create_index('idx_beta_users_email', 'beta_users', ['email'])
    op.create_index('idx_beta_users_invite_code', 'beta_users', ['invite_code'])
    op.create_index('idx_beta_users_status', 'beta_users', ['status'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_beta_users_status')
    op.drop_index('idx_beta_users_invite_code')
    op.drop_index('idx_beta_users_email')
    
    # Drop table
    op.drop_table('beta_users')