"""add_phase2_7_tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-23 18:35:00.000000

Adds:
  - domain_stability
  - disinfo_signals
  - policy_briefs
  - predictions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── domain_stability ──────────────────────────────────────────────────────
    op.create_table(
        'domain_stability',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('components', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('staleness_penalty', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('data_age_hours', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_domain_stability_domain', 'domain_stability', ['domain'])
    op.create_index('ix_domain_stability_computed_at', 'domain_stability', ['computed_at'])

    # ── disinfo_signals ───────────────────────────────────────────────────────
    op.create_table(
        'disinfo_signals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('signal_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=8), nullable=False, server_default='medium'),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('actor_attribution', sa.String(length=128), nullable=True),
        sa.Column('target_entity', sa.String(length=256), nullable=True),
        sa.Column('target_domain', sa.String(length=64), nullable=True),
        sa.Column('cluster_id', sa.String(length=64), nullable=True),
        sa.Column('narrative_summary', sa.Text(), nullable=True),
        sa.Column('coordination_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('evidence_articles', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('flagged_sources', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_disinfo_signals_signal_type', 'disinfo_signals', ['signal_type'])
    op.create_index('ix_disinfo_signals_target_entity', 'disinfo_signals', ['target_entity'])
    op.create_index('ix_disinfo_signals_detected_at', 'disinfo_signals', ['detected_at'])

    # ── policy_briefs ─────────────────────────────────────────────────────────
    op.create_table(
        'policy_briefs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('brief_type', sa.String(length=32), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=True),
        sa.Column('topic', sa.String(length=256), nullable=True),
        sa.Column('content', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('markdown_content', sa.Text(), nullable=True),
        sa.Column('sources', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('entities', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('period_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_to', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_policy_briefs_brief_type', 'policy_briefs', ['brief_type'])
    op.create_index('ix_policy_briefs_domain', 'policy_briefs', ['domain'])
    op.create_index('ix_policy_briefs_created_at', 'policy_briefs', ['created_at'])

    # ── predictions ───────────────────────────────────────────────────────────
    op.create_table(
        'predictions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prediction_text', sa.Text(), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=True),
        sa.Column('horizon', sa.String(length=32), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('confidence_components', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('source_articles', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('reasoning_chain', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('graph_path', sa.Text(), nullable=True),
        sa.Column('entities', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=16), nullable=True),
        sa.Column('outcome_notes', sa.Text(), nullable=True),
        sa.Column('outcome_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_predictions_domain', 'predictions', ['domain'])
    op.create_index('ix_predictions_created_at', 'predictions', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_predictions_created_at', table_name='predictions')
    op.drop_index('ix_predictions_domain', table_name='predictions')
    op.drop_table('predictions')

    op.drop_index('ix_policy_briefs_created_at', table_name='policy_briefs')
    op.drop_index('ix_policy_briefs_domain', table_name='policy_briefs')
    op.drop_index('ix_policy_briefs_brief_type', table_name='policy_briefs')
    op.drop_table('policy_briefs')

    op.drop_index('ix_disinfo_signals_detected_at', table_name='disinfo_signals')
    op.drop_index('ix_disinfo_signals_target_entity', table_name='disinfo_signals')
    op.drop_index('ix_disinfo_signals_signal_type', table_name='disinfo_signals')
    op.drop_table('disinfo_signals')

    op.drop_index('ix_domain_stability_computed_at', table_name='domain_stability')
    op.drop_index('ix_domain_stability_domain', table_name='domain_stability')
    op.drop_table('domain_stability')
