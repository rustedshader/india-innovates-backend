"""add_entity_states_table

Revision ID: a1b2c3d4e5f6
Revises: de3f965f4282
Create Date: 2026-03-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'de3f965f4282'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entity_states',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_name', sa.String(length=256), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('attribute', sa.String(length=128), nullable=False),
        sa.Column('value', sa.String(length=512), nullable=False),
        sa.Column('temporal_marker', sa.String(length=64), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_article_url', sa.String(length=2048), nullable=True),
        sa.Column('source_article_title', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_entity_states_entity_attr', 'entity_states', ['entity_name', 'attribute'])
    op.create_index('ix_entity_states_valid_from', 'entity_states', ['valid_from'])
    op.create_index('ix_entity_states_valid_to', 'entity_states', ['valid_to'])


def downgrade() -> None:
    op.drop_index('ix_entity_states_valid_to', table_name='entity_states')
    op.drop_index('ix_entity_states_valid_from', table_name='entity_states')
    op.drop_index('ix_entity_states_entity_attr', table_name='entity_states')
    op.drop_table('entity_states')
