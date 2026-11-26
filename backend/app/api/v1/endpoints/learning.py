"""Fase 2 endpoints: materials, question bank, assessments, grading, notes, import.

Every write goes through the CSRF-protected `get_current_user` dependency.
Teachers are limited to classes in `teacher_classes`; students to their own
attempts/results. Anomaly indicators are advisory only and never auto-fail a student.
"""
from __future__ import annotations

import csv
import io
import random
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import DATA_DIR, settings
from app.core.deps import assert_school_scope, require_roles, teacher_class_ids
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models.academic import (
    Class,
    ClassMember,
    Competency,
    LearningMaterial,
    Subject,
    TeacherClass,
)
from app.models.assessment import (
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
    Question,
    QuestionOption,
    StudentAnswer,
    StudentAttempt,
)
from app.models.core import Role, User
from app.models.intelligence import StudentNote
from app.models.operations import SyncConflict
from app.schemas.common import Message
from app.schemas.learning import (
    AnswerOut,
    AssessmentIn,
    AssessmentOut,
    AttemptOut,
    GradeIn,
    ImportResult,
    MaterialOut,
    NoteIn,
    NoteOut,
    QuestionIn,
    QuestionOptionOut,
    QuestionOut,
    ResultOut,
    SubmitOut,
    SyncPayload,
)
from app.services.audit import log_audit
from app.services.grading import MANUAL_TYPES, grade_objective
from app.services.intelligence import rebuild_mastery

router = APIRouter(prefix="/learning", tags=["learning"])

PASSING_SCORE = 70.0
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".webp"}


# ---------------------------------------------------------------- helpers

def _naive(value: datetime) -> datetime:
    """Strip timezone info after converting to UTC, matching SQLite storage."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _teacher_class_ids(db: DBSession, user: User) -> list[str]:
    if user.role.name == "admin":
        return list(db.scalars(select(Class.id).where(Class.school_id == user.school_id)).all())
    return teacher_class_ids(db, user)


def _assert_class_access(db: DBSession, user: User, class_id: str) -> Class:
    klass = db.get(Class, class_id)
    if klass is None:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(user, klass.school_id)
    if user.role.name != "admin" and class_id not in _teacher_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Anda tidak mengampu kelas ini")
    return klass


def _get_subject(db: DBSession, user: User, subject_id: str) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Mata pelajaran tidak ditemukan")
    assert_school_scope(user, subject.school_id)
    return subject


def _student_class_ids(db: DBSession, student: User) -> list[str]:
    return list(db.scalars(select(ClassMember.class_id).where(ClassMember.user_id == student.id)).all())


def _material_out(row: LearningMaterial) -> MaterialOut:
    data = MaterialOut.model_validate(row)
    # file_name is derived from the stored path, never trusted as a path itself.
    data.file_name = row.file_path.split("/")[-1] if row.file_path else None
    return data


def _question_out(db: DBSession, row: Question, include_keys: bool = True) -> QuestionOut:
    data = QuestionOut.model_validate(row)
    options = db.scalars(
        select(QuestionOption).where(QuestionOption.question_id == row.id).order_by(QuestionOption.position)
    ).all()
    data.options = [
        QuestionOptionOut.model_validate(o) if include_keys else QuestionOptionOut(
            id=o.id, label=o.label, content=o.content, position=o.position
        )
        for o in options
    ]
    if not include_keys:
        data.rubric_json = {}  # hide `expected` from students
        data.explanation = None  # revealed only after submission
    return data


def _assessment_out(db: DBSession, row: Assessment, viewer: User | None = None) -> AssessmentOut:
    links = db.scalars(
        select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == row.id)
    ).all()
    max_points = sum(
        (link.points_override if link.points_override is not None else db.get(Question, link.question_id).points)
        for link in links
        if db.get(Question, link.question_id) is not None
    )
    count = db.scalar(
        select(func.count(StudentAttempt.id)).where(StudentAttempt.assessment_id == row.id)
    ) or 0
    data = AssessmentOut.model_validate(row)
    data.question_ids = [link.question_id for link in sorted(links, key=lambda link: link.position)]
    data.question_count = len(links)
    data.max_points = round(float(max_points), 2)
    data.attempt_count = count
    if viewer is not None and viewer.role.name == "student":
        data.already_started = bool(db.scalar(
            select(func.count(StudentAttempt.id)).where(
                StudentAttempt.assessment_id == row.id, StudentAttempt.student_id == viewer.id
            )
        ) or 0)
    return data


def _attempt_for_student(db: DBSession, user: User, attempt_id: str) -> StudentAttempt:
    attempt = db.get(StudentAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Upaya tidak ditemukan")
    if user.role.name == "student" and attempt.student_id != user.id:
        raise HTTPException(status_code=403, detail="Upaya ini bukan milik Anda")
    if user.role.name == "teacher":
        assessment = db.get(Assessment, attempt.assessment_id)
        _assert_class_access(db, user, assessment.class_id)
    return attempt


# ---------------------------------------------------------------- materials

@router.get("/materials", response_model=list[MaterialOut])
def list_materials(
    subject_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    query = select(LearningMaterial).join(Subject).where(Subject.school_id == user.school_id)
    if subject_id:
        query = query.where(LearningMaterial.subject_id == subject_id)
    if user.role.name == "student":
        query = query.where(LearningMaterial.is_published.is_(True))
    elif user.role.name == "teacher":
        allowed = _teacher_class_ids(db, user)
        # Teachers see their own materials plus published ones in their school.
        query = query.where(
            (LearningMaterial.teacher_id == user.id)
            | (LearningMaterial.is_published.is_(True) & LearningMaterial.subject_id.in_(
                select(TeacherClass.subject_id).where(TeacherClass.teacher_id == user.id)
            ))
        )
        if not allowed:
            query = query.where(LearningMaterial.teacher_id == user.id)
    return [_material_out(row) for row in db.scalars(query.order_by(LearningMaterial.created_at.desc())).all()]


@router.post("/materials", response_model=MaterialOut, status_code=201)
def create_material(
    payload: dict,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    subject = _get_subject(db, user, payload.get("subject_id", ""))
    title = str(payload.get("title", "")).strip()
    if len(title) < 3:
        raise HTTPException(status_code=422, detail="Judul materi minimal 3 karakter")
    row = LearningMaterial(
        subject_id=subject.id,
        competency_id=payload.get("competency_id") or None,
        teacher_id=user.id,
        title=title,
        content=payload.get("content"),
        material_type=payload.get("material_type", "text"),
        file_path=payload.get("file_path"),
        is_published=bool(payload.get("is_published", False)),
    )
    db.add(row)
    log_audit(db, user, "create_material", "material", row.id, {"title": title}, request)
    db.commit()
    return _material_out(row)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def update_material(
    material_id: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    row = db.get(LearningMaterial, material_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Materi tidak ditemukan")
    if row.teacher_id != user.id and user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Hanya pembuat materi yang dapat mengubahnya")
    for field in ("title", "content", "material_type", "file_path", "is_published", "competency_id"):
        if field in payload:
            setattr(row, field, payload[field])
    log_audit(db, user, "update_material", "material", row.id, {}, request)
    db.commit()
    return _material_out(row)


@router.delete("/materials/{material_id}", response_model=Message)
def delete_material(
    material_id: str,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    row = db.get(LearningMaterial, material_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Materi tidak ditemukan")
    if row.teacher_id != user.id and user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Hanya pembuat materi yang dapat menghapusnya")
    db.delete(row)
    log_audit(db, user, "delete_material", "material", material_id, {}, request)
    db.commit()
    return Message(message="Materi dihapus")


@router.post("/uploads", response_model=dict)
async def upload_material_file(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    """Validate then store a material attachment outside the web root."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Jenis berkas tidak didukung. Gunakan PDF, TXT, MD, DOCX, PPTX, PNG, JPG, atau WEBP.",
        )
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="Berkas kosong")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Berkas melebihi batas {settings.max_upload_mb} MB")

    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (upload_dir / stored_name).write_bytes(content)
    log_audit(db, user, "upload_material_file", "upload", stored_name, {"bytes": len(content)}, request)
    db.commit()
    return {
        "file_path": f"/api/v1/learning/files/{stored_name}",
        "file_name": file.filename,
        "size_bytes": len(content),
    }


@router.get("/files/{stored_name}")
def download_material_file(
    stored_name: str,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|txt|md|docx|pptx|png|jpg|jpeg|webp)", stored_name):
        raise HTTPException(status_code=400, detail="Nama berkas tidak valid")
    path = DATA_DIR / "uploads" / stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Berkas tidak ditemukan")
    reference = db.scalar(
        select(LearningMaterial)
        .join(Subject)
        .where(
            LearningMaterial.file_path.contains(stored_name),
            Subject.school_id == user.school_id,
        )
    )
    if reference is None:
        # A teacher may still fetch a file they uploaded before attaching it
        # to a material. Ownership is proven by the audit entry.
        from app.models.core import AuditLog

        own_upload = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "upload_material_file",
                AuditLog.entity_id == stored_name,
                AuditLog.actor_id == user.id,
            )
        )
        if not own_upload:
            raise HTTPException(status_code=403, detail="Berkas tidak dapat diakses")
    elif user.role.name == "student" and not reference.is_published:
        raise HTTPException(status_code=403, detail="Materi belum dipublikasikan")
    return FileResponse(path, filename=stored_name)


# ---------------------------------------------------------------- questions

@router.get("/questions", response_model=list[QuestionOut])
def list_questions(
    subject_id: str | None = None,
    question_type: str | None = None,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    query = select(Question).join(Subject).where(Subject.school_id == user.school_id)
    if user.role.name == "teacher":
        query = query.where((Question.teacher_id == user.id) | Question.is_published.is_(True))
    if subject_id:
        query = query.where(Question.subject_id == subject_id)
    if question_type:
        query = query.where(Question.question_type == question_type)
    rows = db.scalars(query.order_by(Question.created_at.desc()).limit(300)).all()
    return [_question_out(db, row) for row in rows]


@router.post("/questions", response_model=QuestionOut, status_code=201)
def create_question(
    payload: QuestionIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    _get_subject(db, user, payload.subject_id)
    if payload.competency_id:
        competency = db.get(Competency, payload.competency_id)
        if competency is None or competency.subject_id != payload.subject_id:
            raise HTTPException(status_code=400, detail="Kompetensi tidak sesuai mata pelajaran")
    row = Question(
        teacher_id=user.id,
        **payload.model_dump(exclude={"options"}),
    )
    db.add(row)
    db.flush()
    for option in payload.options:
        db.add(QuestionOption(question_id=row.id, **option.model_dump()))
    log_audit(db, user, "create_question", "question", row.id, {"type": row.question_type}, request)
    db.commit()
    return _question_out(db, row)


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: str,
    payload: QuestionIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    row = db.get(Question, question_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan")
    if row.teacher_id != user.id and user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Hanya pembuat soal yang dapat mengubahnya")
    _get_subject(db, user, payload.subject_id)
    for field, value in payload.model_dump(exclude={"options"}).items():
        setattr(row, field, value)
    db.query(QuestionOption).filter(QuestionOption.question_id == row.id).delete()
    for option in payload.options:
        db.add(QuestionOption(question_id=row.id, **option.model_dump()))
    log_audit(db, user, "update_question", "question", row.id, {}, request)
    db.commit()
    return _question_out(db, row)


@router.delete("/questions/{question_id}", response_model=Message)
def delete_question(
    question_id: str,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    row = db.get(Question, question_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan")
    if row.teacher_id != user.id and user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Hanya pembuat soal yang dapat menghapusnya")
    in_use = db.scalar(
        select(func.count(AssessmentQuestion.id)).where(AssessmentQuestion.question_id == question_id)
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Soal masih digunakan dalam asesmen")
    db.delete(row)
    log_audit(db, user, "delete_question", "question", question_id, {}, request)
    db.commit()
    return Message(message="Soal dihapus")


# ---------------------------------------------------------------- assessments

@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(
    class_id: str | None = None,
    subject_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    query = select(Assessment).join(Class).where(Class.school_id == user.school_id)
    if user.role.name == "teacher":
        query = query.where(Assessment.teacher_id == user.id)
        if class_id:
            _assert_class_access(db, user, class_id)
    elif user.role.name == "student":
        query = query.where(
            Assessment.is_published.is_(True),
            Assessment.class_id.in_(_student_class_ids(db, user)),
        )
    if class_id:
        query = query.where(Assessment.class_id == class_id)
    if subject_id:
        query = query.where(Assessment.subject_id == subject_id)
    rows = db.scalars(query.order_by(Assessment.created_at.desc()).limit(200)).all()
    return [_assessment_out(db, row, user) for row in rows]


@router.post("/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(
    payload: AssessmentIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    klass = _assert_class_access(db, user, payload.class_id)
    _get_subject(db, user, payload.subject_id)
    unique_ids = list(dict.fromkeys(payload.question_ids))
    questions = db.scalars(select(Question).where(Question.id.in_(unique_ids))).all() if unique_ids else []
    if len(questions) != len(unique_ids):
        raise HTTPException(status_code=400, detail="Sebagian soal tidak ditemukan")
    for question in questions:
        subject = db.get(Subject, question.subject_id)
        if subject.school_id != klass.school_id:
            raise HTTPException(status_code=400, detail="Soal dari sekolah lain tidak dapat dipakai")

    row = Assessment(
        teacher_id=user.id,
        **payload.model_dump(exclude={"question_ids"}),
    )
    db.add(row)
    db.flush()
    for position, question_id in enumerate(unique_ids):
        db.add(AssessmentQuestion(assessment_id=row.id, question_id=question_id, position=position))
    log_audit(db, user, "create_assessment", "assessment", row.id, {"title": row.title}, request)
    db.commit()
    return _assessment_out(db, row)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentOut)
def update_assessment(
    assessment_id: str,
    payload: AssessmentIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    row = db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asesmen tidak ditemukan")
    if row.teacher_id != user.id and user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Hanya pembuat asesmen yang dapat mengubahnya")
    _assert_class_access(db, user, payload.class_id)
    started = db.scalar(
        select(func.count(StudentAttempt.id)).where(StudentAttempt.assessment_id == row.id)
    )
    if started and payload.question_ids:
        raise HTTPException(status_code=409, detail="Susunan soal tidak dapat diubah setelah ada siswa yang mulai")
    for field, value in payload.model_dump(exclude={"question_ids"}).items():
        setattr(row, field, value)
    if not started and payload.question_ids:
        db.query(AssessmentQuestion).filter(AssessmentQuestion.assessment_id == row.id).delete()
        for position, question_id in enumerate(dict.fromkeys(payload.question_ids)):
            db.add(AssessmentQuestion(assessment_id=row.id, question_id=question_id, position=position))
    log_audit(db, user, "update_assessment", "assessment", row.id, {}, request)
    db.commit()
    return _assessment_out(db, row)


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: str,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    row = db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asesmen tidak ditemukan")
    klass = db.get(Class, row.class_id)
    assert_school_scope(user, klass.school_id)
    if user.role.name == "student":
        if not row.is_published or row.class_id not in _student_class_ids(db, user):
            raise HTTPException(status_code=403, detail="Asesmen tidak tersedia untuk Anda")
    elif user.role.name == "teacher" and row.teacher_id != user.id:
        _assert_class_access(db, user, row.class_id)
    return _assessment_out(db, row, user)


# ---------------------------------------------------------------- student flow

@router.post("/assessments/{assessment_id}/start", response_model=AttemptOut, status_code=201)
def start_attempt(
    assessment_id: str,
    request: Request,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not assessment.is_published:
        raise HTTPException(status_code=404, detail="Asesmen tidak tersedia")
    klass = db.get(Class, assessment.class_id)
    if klass.school_id != user.school_id or assessment.class_id not in _student_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Anda tidak terdaftar di kelas ini")
    now = utcnow()
    if assessment.start_at and now < _naive(assessment.start_at):
        raise HTTPException(status_code=403, detail="Asesmen belum dimulai")
    if assessment.end_at and now > _naive(assessment.end_at):
        raise HTTPException(status_code=403, detail="Waktu asesmen sudah berakhir")

    existing = db.scalar(
        select(StudentAttempt).where(
            StudentAttempt.assessment_id == assessment_id, StudentAttempt.student_id == user.id
        )
    )
    if existing:
        if existing.status == "submitted" or not assessment.allow_resume:
            raise HTTPException(status_code=409, detail="Upaya sudah dibuat atau tidak dapat dilanjutkan")
        return _attempt_with_questions(db, existing, include_keys=False)

    links = db.scalars(
        select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id).order_by(AssessmentQuestion.position)
    ).all()
    if not links:
        raise HTTPException(status_code=409, detail="Asesmen belum memiliki soal")
    order = [link.question_id for link in links]
    if assessment.shuffle_questions:
        random.SystemRandom().shuffle(order)

    attempt = StudentAttempt(
        assessment_id=assessment_id,
        student_id=user.id,
        status="in_progress",
        question_order_json=order,
        anomaly_flags=[],
        sync_status="synced",
    )
    db.add(attempt)
    log_audit(db, user, "start_attempt", "assessment", assessment_id, {}, request)
    db.commit()
    return _attempt_with_questions(db, attempt, include_keys=False)


def _attempt_with_questions(db: DBSession, attempt: StudentAttempt, include_keys: bool) -> AttemptOut:
    data = AttemptOut.model_validate(attempt)
    question_ids = attempt.question_order_json or []
    questions = []
    for qid in question_ids:
        question = db.get(Question, qid)
        if question:
            questions.append(_question_out(db, question, include_keys=include_keys))
    data.questions = questions
    answers = db.scalars(select(StudentAnswer).where(StudentAnswer.attempt_id == attempt.id)).all()
    data.answers = [AnswerOut.model_validate(a) for a in answers]
    assessment = db.get(Assessment, attempt.assessment_id)
    data.assessment = {
        "id": assessment.id,
        "title": assessment.title,
        "description": assessment.description,
        "duration_min": assessment.duration_min,
        "shuffle_options": assessment.shuffle_options,
        "allow_offline": assessment.allow_offline,
        "allow_resume": assessment.allow_resume,
        "started_at": attempt.started_at.isoformat() + "Z",
    }
    return data


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(
    attempt_id: str,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    attempt = _attempt_for_student(db, user, attempt_id)
    submitted = attempt.status == "submitted"
    data = _attempt_with_questions(db, attempt, include_keys=submitted)
    if not submitted and user.role.name == "student":
        for question in data.questions:
            if question.explanation:
                question.explanation = None
    return data


@router.put("/attempts/{attempt_id}/sync", response_model=dict)
def sync_answers(
    attempt_id: str,
    payload: SyncPayload,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    """Autosave answers.

    Idempotent by `client_id`. When two edits have different timestamps the
    newer `client_updated_at` wins, and every overwrite is reported in
    `conflicts` so the UI can tell the student instead of silently replacing.
    """
    attempt = _attempt_for_student(db, user, attempt_id)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=409, detail="Upaya sudah selesai")
    assessment = db.get(Assessment, attempt.assessment_id)
    if not assessment.allow_offline:
        # Server cannot see the client's connection state; this flag is
        # enforced in the UI. It is recorded here for audit clarity.
        pass

    saved = 0
    conflicts: list[dict[str, Any]] = []

    def record_conflict(
        question_id: str,
        reason: str,
        incoming: Any,
        server: dict[str, Any] | None = None,
    ) -> None:
        """Persist a conflict so it cannot disappear with a toast."""
        duplicate = db.scalar(
            select(SyncConflict).where(
                SyncConflict.student_id == user.id,
                SyncConflict.attempt_id == attempt.id,
                SyncConflict.question_id == question_id,
                SyncConflict.client_id == getattr(incoming, "client_id", None),
                SyncConflict.reason == reason,
                SyncConflict.resolution.is_(None),
            )
        )
        if duplicate is None:
            db.add(SyncConflict(
                school_id=user.school_id,
                student_id=user.id,
                attempt_id=attempt.id,
                question_id=question_id,
                client_id=getattr(incoming, "client_id", None),
                reason=reason,
                server_snapshot_json=server or {},
                client_snapshot_json=incoming.model_dump(mode="json"),
            ))

    for item in payload.answers:
        if item.question_id not in (attempt.question_order_json or []):
            raise HTTPException(status_code=400, detail="Soal tidak termasuk dalam upaya ini")
        incoming_at = _naive(item.client_updated_at)
        existing = db.scalar(
            select(StudentAnswer).where(StudentAnswer.attempt_id == attempt.id, StudentAnswer.question_id == item.question_id)
        )
        replay = db.scalar(
            select(StudentAnswer).where(
                StudentAnswer.attempt_id == attempt.id, StudentAnswer.client_id == item.client_id
            )
        )
        if replay and replay.question_id == item.question_id and replay.client_updated_at == incoming_at:
            saved += 1  # exact replay, idempotent acknowledgement
            continue
        if existing is None:
            if replay is not None:
                # Same client_id reused for a different question: reject,
                # do not silently create a duplicate.
                conflicts.append({
                    "question_id": item.question_id,
                    "reason": "client_id sudah dipakai untuk soal lain dalam upaya ini",
                    "server_updated_at": replay.updated_at.isoformat() + "Z" if replay.updated_at else None,
                    "client_updated_at": incoming_at.isoformat() + "Z",
                })
                record_conflict(
                    item.question_id,
                    "client_id sudah dipakai untuk soal lain dalam upaya ini",
                    item,
                    {
                        "question_id": replay.question_id,
                        "updated_at": replay.updated_at.isoformat() + "Z" if replay.updated_at else None,
                    },
                )
                continue
            db.add(StudentAnswer(
                attempt_id=attempt.id,
                question_id=item.question_id,
                client_id=item.client_id,
                answer_json=item.answer,
                time_spent_sec=item.time_spent_sec,
                changed_count=item.changed_count,
                client_updated_at=incoming_at,
                answered_at=utcnow(),
                updated_at=utcnow(),
                synced_at=utcnow(),
            ))
            saved += 1
            continue
        server_at = existing.client_updated_at or existing.updated_at or existing.answered_at or utcnow()
        if incoming_at > server_at:
            existing.answer_json = item.answer
            existing.time_spent_sec = item.time_spent_sec
            existing.changed_count = item.changed_count
            existing.client_updated_at = incoming_at
            existing.updated_at = utcnow()
            existing.synced_at = utcnow()
            saved += 1
        else:
            conflicts.append({
                "question_id": item.question_id,
                "reason": "Jawaban di perangkat lain lebih lama atau sama; versi server dipertahankan",
                "server_updated_at": server_at.isoformat() + "Z",
                "client_updated_at": incoming_at.isoformat() + "Z",
            })
            record_conflict(
                item.question_id,
                "Jawaban di perangkat lain lebih lama atau sama; versi server dipertahankan",
                item,
                {
                    "answer": existing.answer_json,
                    "updated_at": server_at.isoformat() + "Z",
                },
            )

    attempt.focus_loss_count += payload.focus_loss_count
    attempt.page_hidden_count += payload.page_hidden_count
    flags = list(attempt.anomaly_flags or [])
    if attempt.focus_loss_count >= 5 and "focus_loss_review" not in flags:
        flags.append("focus_loss_review")
    if attempt.page_hidden_count >= 3 and "page_hidden_review" not in flags:
        flags.append("page_hidden_review")
    attempt.anomaly_flags = flags
    attempt.sync_status = "synced" if not conflicts else "conflict"
    db.commit()
    return {
        "saved": saved,
        "conflicts": conflicts,
        "anomaly_flags": flags,
        "note": "Indikator hanya untuk ditinjau guru, bukan penilaian otomatis.",
    }


@router.post("/attempts/{attempt_id}/submit", response_model=SubmitOut)
def submit_attempt(
    attempt_id: str,
    request: Request,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    attempt = _attempt_for_student(db, user, attempt_id)
    if attempt.status == "submitted":
        raise HTTPException(status_code=409, detail="Upaya sudah dikumpulkan")
    answer_rows = db.scalars(select(StudentAnswer).where(StudentAnswer.attempt_id == attempt.id)).all()
    answer_map = {row.question_id: row for row in answer_rows}

    total = 0.0
    max_points = 0.0
    auto_graded = 0
    pending = 0
    for question_id in attempt.question_order_json or []:
        question = db.get(Question, question_id)
        if question is None:
            continue
        link = db.scalar(
            select(AssessmentQuestion).where(
                AssessmentQuestion.assessment_id == attempt.assessment_id,
                AssessmentQuestion.question_id == question_id,
            )
        )
        q_points = float(link.points_override) if link and link.points_override is not None else float(question.points)
        max_points += q_points
        answer_row = answer_map.get(question_id)
        if answer_row is None:
            continue
        if question.question_type in MANUAL_TYPES:
            answer_row.is_correct = None
            answer_row.points_earned = None
            pending += 1
        else:
            is_correct, earned = grade_objective(db, question, answer_row.answer_json or {})
            answer_row.is_correct = is_correct
            answer_row.points_earned = min(earned, q_points)
            total += float(answer_row.points_earned)
            auto_graded += 1
        answer_row.answered_at = answer_row.answered_at or utcnow()
        answer_row.synced_at = utcnow()

    score = round(total / max_points * 100, 2) if max_points else 0.0
    attempt.status = "submitted"
    attempt.submitted_at = utcnow()
    attempt.total_points = round(total, 2)
    attempt.max_points = round(max_points, 2)
    attempt.sync_status = "synced"

    # The BKT replay reads graded answers through a fresh SELECT, so persist
    # the in-memory grading changes first (autoflush must not be assumed).
    db.flush()
    existing_result = db.scalar(select(AssessmentResult).where(AssessmentResult.attempt_id == attempt.id))
    # Fase 3: turn the real graded answers into a BKT-backed competency profile.
    competency_ids: set[str] = set()
    for question_id in attempt.question_order_json or []:
        graded_question = db.get(Question, question_id)
        if graded_question and graded_question.competency_id:
            competency_ids.add(graded_question.competency_id)
    profiles = rebuild_mastery(db, user.id, sorted(competency_ids)) if competency_ids else []
    # Raw score and mastery are different signals; the latter comes from BKT.
    mastery_percent = (
        round(sum(float(row.mastery_probability) for row in profiles) / len(profiles) * 100, 2)
        if profiles else score
    )
    if existing_result is None:
        db.add(AssessmentResult(
            attempt_id=attempt.id,
            student_id=user.id,
            assessment_id=attempt.assessment_id,
            score=score,
            mastery_percent=mastery_percent,
        ))
    else:
        existing_result.score = score
        existing_result.mastery_percent = mastery_percent
    log_audit(db, user, "submit_attempt", "attempt", attempt.id, {"score": score}, request)
    db.commit()
    return SubmitOut(
        attempt_id=attempt.id,
        status="graded" if pending == 0 else "pending_manual",
        total_points=round(total, 2),
        max_points=round(max_points, 2),
        score_percent=score,
        graded_automatically=auto_graded,
        pending_manual=pending,
        anomaly_flags=list(attempt.anomaly_flags or []),
    )


# ---------------------------------------------------------------- results & grading

@router.get("/results", response_model=list[ResultOut])
def list_results(
    class_id: str | None = None,
    assessment_id: str | None = None,
    student_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    query = select(AssessmentResult).join(Assessment).join(Class).where(Class.school_id == user.school_id)
    if user.role.name == "student":
        query = query.where(AssessmentResult.student_id == user.id)
    elif user.role.name == "teacher":
        allowed = _teacher_class_ids(db, user)
        query = query.where(Assessment.class_id.in_(allowed))
        if class_id and class_id not in allowed:
            raise HTTPException(status_code=403, detail="Anda tidak mengampu kelas ini")
    if class_id:
        query = query.where(Assessment.class_id == class_id)
    if assessment_id:
        query = query.where(AssessmentResult.assessment_id == assessment_id)
    if student_id:
        if user.role.name == "student" and student_id != user.id:
            raise HTTPException(status_code=403, detail="Akses ditolak")
        query = query.where(AssessmentResult.student_id == student_id)
    rows = db.scalars(query.order_by(AssessmentResult.graded_at.desc()).limit(500)).all()
    result = []
    for row in rows:
        data = ResultOut.model_validate(row)
        assessment = db.get(Assessment, row.assessment_id)
        student = db.get(User, row.student_id)
        data.assessment_title = assessment.title if assessment else None
        data.student_name = student.full_name if student else None
        result.append(data)
    return result


@router.patch("/answers/{answer_id}/grade", response_model=AnswerOut)
def grade_answer(
    answer_id: str,
    payload: GradeIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    answer = db.get(StudentAnswer, answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Jawaban tidak ditemukan")
    attempt = db.get(StudentAttempt, answer.attempt_id)
    assessment = db.get(Assessment, attempt.assessment_id)
    _assert_class_access(db, user, assessment.class_id)
    question = db.get(Question, answer.question_id)
    if question.question_type not in MANUAL_TYPES:
        raise HTTPException(status_code=400, detail="Hanya jawaban uraian yang dinilai manual")
    link = db.scalar(
        select(AssessmentQuestion).where(
            AssessmentQuestion.assessment_id == assessment.id,
            AssessmentQuestion.question_id == question.id,
        )
    )
    cap = float(link.points_override) if link and link.points_override is not None else float(question.points)
    if payload.points_earned > cap:
        raise HTTPException(status_code=422, detail=f"Nilai tidak boleh melebihi {cap}")
    answer.points_earned = payload.points_earned
    answer.is_correct = payload.points_earned >= cap * 0.7
    if payload.feedback:
        feedback = dict(answer.answer_json or {})
        feedback["teacher_feedback"] = payload.feedback
        answer.answer_json = feedback
    answer.synced_at = utcnow()
    # The BKT replay reads graded answers through a fresh SELECT, so persist
    # the in-memory grading changes first (autoflush must not be assumed).
    db.flush()

    # Recalculate the attempt and result from all graded answers.
    total = 0.0
    max_points = 0.0
    pending = 0
    for qid in attempt.question_order_json or []:
        q = db.get(Question, qid)
        if q is None:
            continue
        a_link = db.scalar(
            select(AssessmentQuestion).where(
                AssessmentQuestion.assessment_id == assessment.id, AssessmentQuestion.question_id == qid
            )
        )
        q_cap = float(a_link.points_override) if a_link and a_link.points_override is not None else float(q.points)
        max_points += q_cap
        ans = db.scalar(select(StudentAnswer).where(StudentAnswer.attempt_id == attempt.id, StudentAnswer.question_id == qid))
        if ans is None or ans.points_earned is None:
            pending += 1
        else:
            total += float(ans.points_earned)
    attempt.total_points = round(total, 2)
    attempt.max_points = round(max_points, 2)
    # Fase 3: regrade changes the observation, so replay BKT from scratch.
    competency_ids: set[str] = set()
    for question_id in attempt.question_order_json or []:
        graded_question = db.get(Question, question_id)
        if graded_question and graded_question.competency_id:
            competency_ids.add(graded_question.competency_id)
    profiles = rebuild_mastery(db, attempt.student_id, sorted(competency_ids)) if competency_ids else []
    mastery_percent = (
        round(sum(float(row.mastery_probability) for row in profiles) / len(profiles) * 100, 2)
        if profiles else (round(total / max_points * 100, 2) if max_points else 0.0)
    )
    result = db.scalar(select(AssessmentResult).where(AssessmentResult.attempt_id == attempt.id))
    if result:
        result.score = round(total / max_points * 100, 2) if max_points else 0.0
        result.mastery_percent = mastery_percent
        result.graded_by = user.id
        result.graded_at = utcnow()
    if pending == 0:
        attempt.status = "submitted"
    log_audit(db, user, "grade_answer", "answer", answer.id, {"points": payload.points_earned}, request)
    db.commit()
    return AnswerOut.model_validate(answer)


@router.get("/attempts/{attempt_id}/answers", response_model=list[AnswerOut])
def list_answers(
    attempt_id: str,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    attempt = _attempt_for_student(db, user, attempt_id)
    return [AnswerOut.model_validate(row) for row in db.scalars(
        select(StudentAnswer).where(StudentAnswer.attempt_id == attempt.id)
    ).all()]


# ---------------------------------------------------------------- teacher notes

@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    student_id: str | None = None,
    class_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    query = select(StudentNote).join(User, StudentNote.student_id == User.id).where(User.school_id == user.school_id)
    if user.role.name == "student":
        query = query.where(StudentNote.student_id == user.id)
    elif user.role.name == "teacher":
        query = query.where(StudentNote.teacher_id == user.id)
    if student_id:
        if user.role.name == "student" and student_id != user.id:
            raise HTTPException(status_code=403, detail="Akses ditolak")
        query = query.where(StudentNote.student_id == student_id)
    if class_id:
        _assert_class_access(db, user, class_id)
        query = query.where(StudentNote.class_id == class_id)
    return [NoteOut.model_validate(row) for row in db.scalars(query.order_by(StudentNote.created_at.desc()).limit(200)).all()]


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(
    payload: NoteIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    student = db.get(User, payload.student_id)
    if student is None or student.school_id != user.school_id or student.role.name != "student":
        raise HTTPException(status_code=400, detail="Siswa tidak valid")
    if payload.class_id:
        klass = _assert_class_access(db, user, payload.class_id)
        member = db.scalar(
            select(ClassMember).where(ClassMember.class_id == klass.id, ClassMember.user_id == student.id)
        )
        if member is None:
            raise HTTPException(status_code=400, detail="Siswa tidak terdaftar di kelas ini")
    row = StudentNote(teacher_id=user.id, **payload.model_dump())
    db.add(row)
    log_audit(db, user, "create_note", "student_note", row.id, {"student_id": student.id}, request)
    db.commit()
    return NoteOut.model_validate(row)


@router.patch("/notes/{note_id}/read", response_model=NoteOut)
def mark_note_read(
    note_id: str,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    row = db.get(StudentNote, note_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if row.student_id != user.id:
        raise HTTPException(status_code=403, detail="Catatan ini bukan untuk Anda")
    row.is_read = True
    db.commit()
    return NoteOut.model_validate(row)


# ---------------------------------------------------------------- analytics & import

@router.get("/analytics", response_model=dict)
def analytics(
    class_id: str | None = None,
    subject_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    allowed = _teacher_class_ids(db, user)
    if class_id:
        _assert_class_access(db, user, class_id)
    query = (
        select(AssessmentResult)
        .join(Assessment)
        .join(Class)
        .where(Class.school_id == user.school_id, Assessment.class_id.in_(allowed))
    )
    if class_id:
        query = query.where(Assessment.class_id == class_id)
    if subject_id:
        query = query.where(Assessment.subject_id == subject_id)
    rows = db.scalars(query).all()
    scores = [float(r.score) for r in rows]
    average = round(sum(scores) / len(scores), 2) if scores else 0.0

    student_count = 0
    if class_id:
        student_count = db.scalar(select(func.count(ClassMember.id)).where(ClassMember.class_id == class_id)) or 0
    elif allowed:
        student_count = db.scalar(
            select(func.count(func.distinct(ClassMember.user_id))).where(ClassMember.class_id.in_(allowed))
        ) or 0

    # Hardest competencies are derived only from real graded objective answers.
    competency_stats: dict[str, dict[str, Any]] = {}
    for result in rows:
        for answer in db.scalars(
            select(StudentAnswer).where(StudentAnswer.attempt_id == result.attempt_id)
        ).all():
            question = db.get(Question, answer.question_id)
            if question is None or question.competency_id is None or answer.is_correct is None:
                continue
            stat = competency_stats.setdefault(question.competency_id, {"correct": 0, "total": 0})
            stat["total"] += 1
            stat["correct"] += 1 if answer.is_correct else 0
    hardest = []
    for comp_id, stat in competency_stats.items():
        competency = db.get(Competency, comp_id)
        hardest.append({
            "competency_id": comp_id,
            "name": competency.name if competency else "-",
            "code": competency.code if competency else "-",
            "correct": stat["correct"],
            "total": stat["total"],
            "accuracy_percent": round(stat["correct"] / stat["total"] * 100, 2),
        })
    hardest.sort(key=lambda item: item["accuracy_percent"])

    by_student: dict[str, list[float]] = {}
    for result in rows:
        by_student.setdefault(result.student_id, []).append(float(result.score))
    needing_help = []
    for student_id, student_scores in by_student.items():
        avg = sum(student_scores) / len(student_scores)
        if avg < PASSING_SCORE:
            student = db.get(User, student_id)
            needing_help.append({
                "student_id": student_id,
                "name": student.full_name if student else "-",
                "average_score": round(avg, 2),
                "attempts": len(student_scores),
            })
    needing_help.sort(key=lambda item: item["average_score"])

    return {
        "class_id": class_id,
        "subject_id": subject_id,
        "student_count": student_count,
        "attempt_count": len(rows),
        "average_score": average,
        "passing_count": sum(1 for score in scores if score >= PASSING_SCORE),
        "hardest_competencies": hardest[:10],
        "students_needing_help": needing_help,
        "evidence": {
            "source": "assessment_results + student_answers",
            "passing_threshold": PASSING_SCORE,
            "computed_at": utcnow().isoformat() + "Z",
            "note": "Indikator untuk ditinjau guru, bukan vonis otomatis.",
        },
    }


@router.post("/import-students", response_model=ImportResult)
async def import_students(
    request: Request,
    file: UploadFile = File(...),
    class_id: str = Query(...),
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    """Import students from .csv or .xlsx. Required columns: username, full_name, password.

    Optional: email, student_number. Duplicate usernames in the school are skipped,
    never overwritten. Passwords are hashed; accounts must change on first login.
    """
    klass = _assert_class_access(db, user, class_id)
    filename = (file.filename or "").lower()
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Berkas terlalu besar (maksimal 5 MB)")

    rows: list[dict[str, str]] = []
    try:
        if filename.endswith(".csv"):
            text = content.decode("utf-8-sig")
            for item in csv.DictReader(io.StringIO(text)):
                rows.append({str(k).strip(): str(v or "").strip() for k, v in item.items()})
        elif filename.endswith(".xlsx"):
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            headers = [str(cell.value or "").strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
            for values in sheet.iter_rows(min_row=2, values_only=True):
                rows.append({headers[i]: str(value or "").strip() for i, value in enumerate(values) if i < len(headers)})
            workbook.close()
        else:
            raise HTTPException(status_code=400, detail="Format harus .csv atau .xlsx")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gagal membaca berkas: {exc}")

    role = db.scalar(select(Role).where(Role.name == "student"))
    if role is None:
        raise HTTPException(status_code=500, detail="Peran siswa tidak ditemukan")
    created = updated = skipped = 0
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        username = row.get("username", "").lower()
        full_name = row.get("full_name", "")
        password = row.get("password", "")
        if not username or len(full_name) < 2 or len(password) < 10:
            skipped += 1
            errors.append(f"Baris {index}: username, nama, atau password tidak valid")
            continue
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            if existing.school_id != user.school_id or existing.role.name != "student":
                skipped += 1
                errors.append(f"Baris {index}: username sudah dipakai oleh akun lain")
                continue
            membership = db.scalar(
                select(ClassMember).where(ClassMember.class_id == klass.id, ClassMember.user_id == existing.id)
            )
            if membership is None:
                db.add(ClassMember(class_id=klass.id, user_id=existing.id, student_number=row.get("student_number")))
                updated += 1
            else:
                skipped += 1
            continue
        db.add(User(
            school_id=user.school_id,
            role_id=role.id,
            username=username,
            full_name=full_name,
            email=row.get("email") or None,
            student_number=row.get("student_number") or None,
            password_hash=hash_password(password),
            must_change_password=True,
        ))
        db.flush()
        student = db.scalar(select(User).where(User.username == username))
        db.add(ClassMember(class_id=klass.id, user_id=student.id))
        created += 1
    log_audit(db, user, "import_students", "class", class_id, {"created": created, "updated": updated}, request)
    db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors[:20])
