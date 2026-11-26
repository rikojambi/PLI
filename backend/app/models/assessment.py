"""Question bank, assessments, attempts and results."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin, utcnow


class Question(IDMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str | None] = mapped_column(ForeignKey("competencies.id", ondelete="SET NULL"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    question_type: Mapped[str] = mapped_column(String(40), index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    content: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500))
    points: Mapped[float] = mapped_column(default=1.0)
    time_limit_sec: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)
    rubric_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Teacher-assigned learning gap category used by Fase 3 gap analysis.
    gap_category: Mapped[str] = mapped_column(String(30), default="konsep", index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestionOption(IDMixin, Base):
    __tablename__ = "question_options"
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    match_key: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Assessment(IDMixin, TimestampMixin, Base):
    __tablename__ = "assessments"
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(Integer, default=45)
    start_at: Mapped[datetime | None] = mapped_column(DateTime)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_resume: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class AssessmentQuestion(IDMixin, Base):
    __tablename__ = "assessment_questions"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    points_override: Mapped[float | None] = mapped_column()


class StudentAttempt(IDMixin, Base):
    __tablename__ = "student_attempts"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    total_points: Mapped[float | None] = mapped_column()
    max_points: Mapped[float | None] = mapped_column()
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")
    question_order_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    focus_loss_count: Mapped[int] = mapped_column(Integer, default=0)
    page_hidden_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_attempt_assessment_student"),
    )


class StudentAnswer(IDMixin, Base):
    __tablename__ = "student_answers"
    attempt_id: Mapped[str] = mapped_column(ForeignKey("student_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    answer_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_earned: Mapped[float | None] = mapped_column()
    time_spent_sec: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    client_id: Mapped[str | None] = mapped_column(String(36), index=True)
    client_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_answer_attempt_question"),
        UniqueConstraint("attempt_id", "client_id", name="uq_answer_attempt_client"),
    )


class AssessmentResult(IDMixin, Base):
    __tablename__ = "assessment_results"
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("student_attempts.id", ondelete="CASCADE"), unique=True, index=True
    )
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column()
    mastery_percent: Mapped[float | None] = mapped_column()
    graded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    graded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)


Index("ix_result_student_assessment", AssessmentResult.student_id, AssessmentResult.assessment_id)
