"""fase6_operations

Revision ID: b6d1f7a9c2e4
Revises: f4a6d8b1c3e7
Create Date: 2026-11-26 08:00:00.000000

Fase 6 keeps durable evidence for sync conflicts, student data erasure and
server-side secret rotation. No raw secret is stored in the database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6d1f7a9c2e4'
down_revision: Union[str, None] = 'f4a6d8b1c3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_conflicts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=True),
        sa.Column('attempt_id', sa.String(length=36), nullable=True),
        sa.Column('question_id', sa.String(length=36), nullable=True),
        sa.Column('client_id', sa.String(length=36), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('server_snapshot_json', sa.JSON(), nullable=False),
        sa.Column('client_snapshot_json', sa.JSON(), nullable=False),
        sa.Column('resolution', sa.String(length=20), nullable=True),
        sa.Column('resolved_by', sa.String(length=36), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['attempt_id'], ['student_attempts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_sync_conflicts_created_at', 'sync_conflicts', ['created_at'])
    op.create_index('ix_sync_conflicts_school_id', 'sync_conflicts', ['school_id'])
    op.create_index('ix_sync_conflicts_student_id', 'sync_conflicts', ['student_id'])
    op.create_index('ix_sync_conflicts_attempt_id', 'sync_conflicts', ['attempt_id'])
    op.create_index('ix_sync_conflicts_question_id', 'sync_conflicts', ['question_id'])
    op.create_index('ix_sync_conflicts_client_id', 'sync_conflicts', ['client_id'])
    op.create_index('ix_sync_conflicts_resolution', 'sync_conflicts', ['resolution'])
    op.create_index('ix_sync_conflict_student_status', 'sync_conflicts', ['student_id', 'resolution'])

    op.create_table(
        'deletion_requests',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=True),
        sa.Column('requested_by', sa.String(length=36), nullable=False),
        sa.Column('processed_by', sa.String(length=36), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('certificate_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['processed_by'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_deletion_requests_created_at', 'deletion_requests', ['created_at'])
    op.create_index('ix_deletion_requests_school_id', 'deletion_requests', ['school_id'])
    op.create_index('ix_deletion_requests_student_id', 'deletion_requests', ['student_id'])
    op.create_index('ix_deletion_requests_requested_by', 'deletion_requests', ['requested_by'])
    op.create_index('ix_deletion_requests_processed_by', 'deletion_requests', ['processed_by'])
    op.create_index('ix_deletion_requests_status', 'deletion_requests', ['status'])
    op.create_index('ix_deletion_requests_due_at', 'deletion_requests', ['due_at'])
    op.create_index('ix_deletion_request_school_status', 'deletion_requests', ['school_id', 'status'])

    op.create_table(
        'secret_rotations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('performed_by', sa.String(length=36), nullable=False),
        sa.Column('key_hint', sa.String(length=80), nullable=False),
        sa.Column('previous_key_hint', sa.String(length=80), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_secret_rotations_performed_by', 'secret_rotations', ['performed_by'])
    op.create_index('ix_secret_rotations_created_at', 'secret_rotations', ['created_at'])


def downgrade() -> None:
    op.drop_table('secret_rotations')
    op.drop_table('deletion_requests')
    op.drop_table('sync_conflicts')
