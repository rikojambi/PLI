"""fase4_ai

Revision ID: f4a6d8b1c3e7
Revises: c4f7a91d3e02
Create Date: 2026-11-25 15:00:00.000000

Fase 4 activates the prepared AI tables and adds school scoping, discovered
model inventory, cost-aware usage logs, idempotent tutor messages and drafts
that a teacher must approve before publication.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a6d8b1c3e7'
down_revision: Union[str, None] = 'c4f7a91d3e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Provider configuration becomes school-scoped and cost-aware.
    with op.batch_alter_table('ai_providers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('school_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('embedding_model', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('input_cost_per_million', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('output_cost_per_million', sa.Float(), nullable=False, server_default='0'))

    op.execute(
        "UPDATE ai_providers SET school_id = (SELECT id FROM schools ORDER BY created_at LIMIT 1) "
        "WHERE school_id IS NULL"
    )

    with op.batch_alter_table('ai_providers', schema=None) as batch_op:
        batch_op.alter_column('school_id', existing_type=sa.String(length=36), nullable=False)
        batch_op.create_foreign_key(
            'fk_ai_providers_school', 'schools', ['school_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.drop_index(batch_op.f('ix_ai_providers_name'))
        batch_op.create_index(batch_op.f('ix_ai_providers_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_providers_school_id'), ['school_id'], unique=False)
        batch_op.create_unique_constraint(
            'uq_ai_provider_school_name', ['school_id', 'name']
        )

    # Usage logs keep evidence of which model was used and whether cost is known.
    with op.batch_alter_table('ai_usage_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('school_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('model', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('cost_source', sa.String(length=30), nullable=False, server_default='not_configured'))
        batch_op.add_column(sa.Column('request_id', sa.String(length=80), nullable=True))
        batch_op.create_foreign_key(
            'fk_ai_usage_logs_school', 'schools', ['school_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_index(batch_op.f('ix_ai_usage_logs_school_id'), ['school_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_usage_logs_request_id'), ['request_id'], unique=False)

    op.execute(
        "UPDATE ai_usage_logs SET school_id = "
        "(SELECT users.school_id FROM users WHERE users.id = ai_usage_logs.user_id) "
        "WHERE school_id IS NULL"
    )
    op.execute(
        "UPDATE ai_usage_logs SET school_id = "
        "(SELECT id FROM schools ORDER BY created_at LIMIT 1) WHERE school_id IS NULL"
    )

    # Tutor messages become idempotent per conversation/client_id.
    with op.batch_alter_table('tutor_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_tutor_messages_client_id'), ['client_id'], unique=False)
        batch_op.create_unique_constraint(
            'uq_tutor_message_client', ['conversation_id', 'client_id']
        )

    op.create_table(
        'ai_provider_models',
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.Column('provider_id', sa.String(length=36), nullable=False),
        sa.Column('model_id', sa.String(length=150), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('capabilities_json', sa.JSON(), nullable=False),
        sa.Column('context_window', sa.Integer(), nullable=True),
        sa.Column('discovered', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['ai_providers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_id', 'model_id', name='uq_ai_provider_model'),
    )
    with op.batch_alter_table('ai_provider_models', schema=None) as batch_op:
        for column in ('created_at', 'model_id', 'provider_id', 'school_id'):
            batch_op.create_index(batch_op.f(f'ix_ai_provider_models_{column}'), [column], unique=False)

    op.create_table(
        'generated_contents',
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('reviewed_by', sa.String(length=36), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=250), nullable=False),
        sa.Column('prompt_json', sa.JSON(), nullable=False),
        sa.Column('content_json', sa.JSON(), nullable=False),
        sa.Column('sources_json', sa.JSON(), nullable=False),
        sa.Column('model_info_json', sa.JSON(), nullable=False),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('published_ref_id', sa.String(length=36), nullable=True),
        sa.Column('client_id', sa.String(length=36), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'school_id', 'created_by', 'client_id',
            name='uq_generated_school_creator_client',
        ),
    )
    with op.batch_alter_table('generated_contents', schema=None) as batch_op:
        for column in ('created_at', 'created_by', 'kind', 'school_id', 'status', 'client_id'):
            batch_op.create_index(batch_op.f(f'ix_generated_contents_{column}'), [column], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('generated_contents', schema=None) as batch_op:
        for column in ('client_id', 'status', 'kind', 'school_id', 'created_by', 'created_at'):
            batch_op.drop_index(batch_op.f(f'ix_generated_contents_{column}'))
    op.drop_table('generated_contents')

    with op.batch_alter_table('ai_provider_models', schema=None) as batch_op:
        for column in ('school_id', 'provider_id', 'model_id', 'created_at'):
            batch_op.drop_index(batch_op.f(f'ix_ai_provider_models_{column}'))
    op.drop_table('ai_provider_models')

    with op.batch_alter_table('tutor_messages', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tutor_message_client', type_='unique')
        batch_op.drop_index(batch_op.f('ix_tutor_messages_client_id'))
        batch_op.drop_column('client_id')

    with op.batch_alter_table('ai_usage_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_usage_logs_request_id'))
        batch_op.drop_index(batch_op.f('ix_ai_usage_logs_school_id'))
        batch_op.drop_constraint('fk_ai_usage_logs_school', type_='foreignkey')
        batch_op.drop_column('request_id')
        batch_op.drop_column('cost_source')
        batch_op.drop_column('cost_usd')
        batch_op.drop_column('model')
        batch_op.drop_column('school_id')

    with op.batch_alter_table('ai_providers', schema=None) as batch_op:
        batch_op.drop_constraint('uq_ai_provider_school_name', type_='unique')
        batch_op.drop_index(batch_op.f('ix_ai_providers_school_id'))
        batch_op.drop_index(batch_op.f('ix_ai_providers_name'))
        batch_op.create_index(batch_op.f('ix_ai_providers_name'), ['name'], unique=True)
        batch_op.drop_constraint('fk_ai_providers_school', type_='foreignkey')
        batch_op.drop_column('output_cost_per_million')
        batch_op.drop_column('input_cost_per_million')
        batch_op.drop_column('embedding_model')
        batch_op.drop_column('school_id')
