"""Fase 6 operational records: sync conflicts, erasure and secret rotation.

These tables keep evidence for decisions that must remain explainable: conflicts
are not silently discarded, deletions produce a certificate, and secret
rotations record who rotated which key reference without storing raw secrets.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin, utcnow


class SyncConflict(IDMixin, TimestampMixin, Base):
    __tablename__ = "sync_conflicts"

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="SET NULL"), index=True
    )
    question_id: Mapped[str | None] = mapped_column(String(36), index=True)
    client_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(Text)
    server_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    client_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(20), index=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class DeletionRequest(IDMixin, TimestampMixin, Base):
    __tablename__ = "deletion_requests"

    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    processed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    certificate_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SecretRotation(IDMixin, Base):
    __tablename__ = "secret_rotations"

    performed_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    key_hint: Mapped[str] = mapped_column(String(80))
    previous_key_hint: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


Index("ix_sync_conflict_student_status", SyncConflict.student_id, SyncConflict.resolution)
Index("ix_deletion_request_school_status", DeletionRequest.school_id, DeletionRequest.status)
