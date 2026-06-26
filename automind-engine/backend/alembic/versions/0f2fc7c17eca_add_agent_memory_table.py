"""add agent_memory table

Revision ID: 0f2fc7c17eca
Revises: 16e837286122
Create Date: 2026-06-15 11:33:13.996999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0f2fc7c17eca'
down_revision: Union[str, None] = '16e837286122'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_memory',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('key_outputs', postgresql.JSONB(), server_default='{}', nullable=True),
        sa.Column('memory_type', sa.String(length=50), server_default='execution_summary', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_memory_agent_id', 'agent_memory', ['agent_id'])


def downgrade() -> None:
    op.drop_index('ix_agent_memory_agent_id', table_name='agent_memory')
    op.drop_table('agent_memory')
