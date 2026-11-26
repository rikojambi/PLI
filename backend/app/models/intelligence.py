"""Personal learning engine state: mastery, BKT history, recommendations, remedial."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin, utcnow


class StudentCompetencyMastery(IDMixin, TimestampMixin, Base):
    __tablename__ = "student_competency_mastery"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id", ondelete="CASCADE"), index=True)
    mastery_probability: Mapped[float] = mapped_column(default=0.0)
    practice_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="not_started", index=True)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("student_id", "competency_id", name="uq_mastery_student_competency"),
    )


class BktHistory(IDMixin, Base):
    __tablename__ = "bkt_history"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id", ondelete="CASCADE"), index=True)
    mastery_id: Mapped[str | None] = mapped_column(
        ForeignKey("student_competency_mastery.id", ondelete="SET NULL")
    )
    prior_probability: Mapped[float] = mapped_column()
    posterior_probability: Mapped[float] = mapped_column()
    observed_correct: Mapped[bool] = mapped_column(Boolean)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str | None] = mapped_column(String(40))
    # `evidence_id` points to student_answers.id or adaptive_practices.id. It
    # makes a full BKT replay deterministic and traceable to a real observation.
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    __table_args__ = (
        UniqueConstraint("student_id", "competency_id", "evidence_id", name="uq_bkt_evidence"),
    )


class LearningRecommendation(IDMixin, TimestampMixin, Base):
    __tablename__ = "learning_recommendations"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"), index=True)
    competency_id: Mapped[str | None] = mapped_column(ForeignKey("competencies.id", ondelete="SET NULL"))
    rec_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(250))
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RemedialRecord(IDMixin, TimestampMixin, Base):
    __tablename__ = "remedial_records"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    before_mastery: Mapped[float | None] = mapped_column()
    after_mastery: Mapped[float | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    notes: Mapped[str | None] = mapped_column(Text)


class StudentNote(IDMixin, TimestampMixin, Base):
    """Teacher warning/encouragement note. Never an automated disciplinary verdict."""
    __tablename__ = "student_notes"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"), index=True)
    note_type: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class AdaptivePractice(IDMixin, TimestampMixin, Base):
    """A real answer to a question selected by the adaptive engine."""

    __tablename__ = "adaptive_practices"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str | None] = mapped_column(
        ForeignKey("competencies.id", ondelete="SET NULL"), index=True
    )
    answer_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    points_earned: Mapped[float] = mapped_column(default=0.0)
    difficulty_at_time: Mapped[str] = mapped_column(String(20), default="medium")
    context_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    __table_args__ = (
        UniqueConstraint("student_id", "client_id", name="uq_adaptive_student_client"),
    )


class EngineConfig(IDMixin, TimestampMixin, Base):
    """Server-side engine parameters. Never supplied by the browser at runtime."""

    __tablename__ = "engine_configs"
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


Index("ix_bkt_student_competency_time", BktHistory.student_id, BktHistory.competency_id, BktHistory.occurred_at)
