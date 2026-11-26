"""fase3_intelligence

Revision ID: c4f7a91d3e02
Revises: e1c9acd1e994
Create Date: 2026-11-25 13:10:00.000000

Fase 3 adds traceable BKT observations, adaptive practice answers, server-side
engine configuration and a teacher-assigned gap category on questions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4f7a91d3e02'
down_revision: Union[str, None] = 'e1c9acd1e994'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bkt_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('evidence_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_bkt_history_evidence_id'), ['evidence_id'], unique=False)
        batch_op.create_unique_constraint('uq_bkt_evidence', ['student_id', 'competency_id', 'evidence_id'])

    op.create_table(
        'adaptive_practices',
        sa.Column('student_id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('competency_id', sa.String(length=36), nullable=True),
        sa.Column('answer_json', sa.JSON(), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('points_earned', sa.Float(), nullable=False),
        sa.Column('difficulty_at_time', sa.String(length=20), nullable=False),
        sa.Column('context_json', sa.JSON(), nullable=False),
        sa.Column('client_id', sa.String(length=36), nullable=True),
        sa.Column('answered_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'client_id', name='uq_adaptive_student_client'),
    )
    with op.batch_alter_table('adaptive_practices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_adaptive_practices_answered_at'), ['answered_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_adaptive_practices_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_adaptive_practices_competency_id'), ['competency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_adaptive_practices_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_adaptive_practices_question_id'), ['question_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_adaptive_practices_student_id'), ['student_id'], unique=False)

    op.create_table(
        'engine_configs',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value_json', sa.JSON(), nullable=False),
        sa.Column('updated_by', sa.String(length=36), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    with op.batch_alter_table('engine_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_engine_configs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_engine_configs_key'), ['key'], unique=True)

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('gap_category', sa.String(length=30), nullable=False, server_default='konsep')
        )
        batch_op.create_index(batch_op.f('ix_questions_gap_category'), ['gap_category'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_questions_gap_category'))
        batch_op.drop_column('gap_category')

    with op.batch_alter_table('engine_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_engine_configs_key'))
        batch_op.drop_index(batch_op.f('ix_engine_configs_created_at'))
    op.drop_table('engine_configs')

    with op.batch_alter_table('adaptive_practices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_student_id'))
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_question_id'))
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_created_at'))
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_competency_id'))
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_client_id'))
        batch_op.drop_index(batch_op.f('ix_adaptive_practices_answered_at'))
    op.drop_table('adaptive_practices')

    with op.batch_alter_table('bkt_history', schema=None) as batch_op:
        batch_op.drop_constraint('uq_bkt_evidence', type_='unique')
        batch_op.drop_index(batch_op.f('ix_bkt_history_evidence_id'))
        batch_op.drop_column('evidence_id')
