"""Classes, subjects, competencies and teaching materials."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin


class Subject(IDMixin, TimestampMixin, Base):
    __tablename__ = "subjects"
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("school_id", "code", name="uq_subject_school_code"),)


class Class(IDMixin, TimestampMixin, Base):
    __tablename__ = "classes"
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    academic_year_id: Mapped[str] = mapped_column(ForeignKey("academic_years.id", ondelete="RESTRICT"))
    semester_id: Mapped[str] = mapped_column(ForeignKey("semesters.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    grade_level: Mapped[str | None] = mapped_column(String(30))
    homeroom_teacher_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("school_id", "academic_year_id", "semester_id", "name", name="uq_class_unique"),
    )


class ClassMember(IDMixin, TimestampMixin, Base):
    __tablename__ = "class_members"
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_number: Mapped[str | None] = mapped_column(String(40))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_member"),)


class TeacherClass(IDMixin, TimestampMixin, Base):
    """Teacher -> class assignment, optionally limited to one subject."""
    __tablename__ = "teacher_classes"
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("class_id", "teacher_id", "subject_id", name="uq_teacher_class"),)


class Competency(IDMixin, TimestampMixin, Base):
    __tablename__ = "competencies"
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("competencies.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    grade_level: Mapped[str | None] = mapped_column(String(30))
    prerequisite_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("subject_id", "code", name="uq_competency_subject_code"),)


class LearningObjective(IDMixin, TimestampMixin, Base):
    __tablename__ = "learning_objectives"
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("competency_id", "code", name="uq_objective_competency_code"),)


class LearningMaterial(IDMixin, TimestampMixin, Base):
    __tablename__ = "learning_materials"
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str | None] = mapped_column(ForeignKey("competencies.id", ondelete="SET NULL"))
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(250))
    content: Mapped[str | None] = mapped_column(Text)
    material_type: Mapped[str] = mapped_column(String(30), default="text")
    file_path: Mapped[str | None] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


Index("ix_class_school_active", Class.school_id, Class.is_active)
Index("ix_competency_subject_order", Competency.subject_id, Competency.order_index)
