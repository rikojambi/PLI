"""Fase 3 endpoints: mastery profiles, BKT, adaptive practice and gaps.

All reads are scoped by school and class. Students can only ever see their own
mastery, recommendations and indicators. All writes require a valid session
and CSRF token through ``get_current_user``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import assert_school_scope, require_roles, teacher_class_ids
from app.db.base import utcnow
from app.db.session import get_db
from app.models.academic import Class, ClassMember, Competency, Subject
from app.models.assessment import Question
from app.models.core import User
from app.models.intelligence import AdaptivePractice, EngineConfig, LearningRecommendation, StudentCompetencyMastery
from app.schemas.intelligence import AdaptiveAnswerIn, BktParamsIn, RecommendationOut
from app.services.audit import log_audit
from app.services.dropout import load_dropout_evaluation
from app.services.grading import grade_objective
from app.services.intelligence import (
    ADAPTIVE_TYPES,
    ENGINE_CONFIG_KEY,
    advisory_indicators,
    competency_scope,
    effective_params,
    gap_analysis,
    mastery_snapshot,
    rebuild_mastery,
    rebuild_school,
    recommend_next,
    refresh_recommendations,
    status_for,
    validate_params,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ---------------------------------------------------------------- helpers

def _class_ids(db: DBSession, user: User) -> list[str]:
    if user.role.name == "student":
        return list(db.scalars(
            select(ClassMember.class_id).where(ClassMember.user_id == user.id)
        ).all())
    if user.role.name == "admin":
        return list(db.scalars(
            select(Class.id).where(Class.school_id == user.school_id)
        ).all())
    return teacher_class_ids(db, user)


def _assert_class_access(db: DBSession, user: User, class_id: str) -> None:
    klass = db.get(Class, class_id)
    if klass is None:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(user, klass.school_id)
    if user.role.name != "admin" and class_id not in _class_ids(db, user):
        raise HTTPException(status_code=403, detail="Anda tidak mengampu kelas ini")


def _resolve_students(
    db: DBSession, user: User, class_ids: list[str], student_id: str | None
) -> list[str]:
    if user.role.name == "student":
        if student_id and student_id != user.id:
            raise HTTPException(status_code=403, detail="Data siswa lain tidak dapat diakses")
        return [user.id]
    if student_id:
        student = db.get(User, student_id)
        if student is None or student.school_id != user.school_id or student.role.name != "student":
            raise HTTPException(status_code=400, detail="Siswa tidak valid")
        if user.role.name == "teacher":
            member = db.scalar(
                select(ClassMember).where(
                    ClassMember.user_id == student_id,
                    ClassMember.class_id.in_(class_ids),
                )
            )
            if member is None:
                raise HTTPException(status_code=403, detail="Siswa tidak berada di kelas yang Andaampu")
        return [student_id]
    if not class_ids:
        return []
    return list(db.scalars(
        select(ClassMember.user_id).where(
            ClassMember.class_id.in_(class_ids),
            User.id == ClassMember.user_id,
            User.school_id == user.school_id,
            User.role.has(name="student"),
        )
    ).all())


def _scope(
    db: DBSession,
    user: User,
    class_id: str | None,
    student_id: str | None,
    subject_id: str | None,
) -> tuple[list[str], list[str]]:
    class_ids = _class_ids(db, user)
    if class_id:
        _assert_class_access(db, user, class_id)
        class_ids = [class_id]
    student_ids = _resolve_students(db, user, class_ids, student_id)
    return class_ids, student_ids


def _evidence(kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "source": kind,
        "computed_at": utcnow().isoformat() + "Z",
        "note": "Indikator untuk ditinjau guru, bukan vonis otomatis.",
        **extra,
    }


# ---------------------------------------------------------------- mastery & gaps

@router.get("/mastery", response_model=dict)
def get_mastery(
    class_id: str | None = None,
    subject_id: str | None = None,
    student_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    class_ids, student_ids = _scope(db, user, class_id, student_id, subject_id)
    params = effective_params(db)
    teacher_id = user.id if user.role.name == "teacher" else None
    _, competencies = competency_scope(db, user.school_id, class_ids, subject_id, teacher_id)
    if user.role.name == "student":
        return {
            "mode": "student",
            "student_id": user.id,
            "rows": mastery_snapshot(db, user.id, competencies, params),
            "competency_count": len(competencies),
            "evidence": _evidence("bkt_history + student_answers + adaptive_practices", params=params),
        }
    students = []
    for sid in student_ids:
        account = db.get(User, sid)
        students.append({
            "student_id": sid,
            "name": account.full_name if account else "-",
            "rows": mastery_snapshot(db, sid, competencies, params),
        })
    return {
        "mode": "class",
        "class_id": class_id,
        "subject_id": subject_id,
        "students": students,
        "competency_count": len(competencies),
        "evidence": _evidence("bkt_history + student_answers + adaptive_practices", params=params),
    }


@router.get("/gaps", response_model=dict)
def get_gaps(
    class_id: str | None = None,
    subject_id: str | None = None,
    student_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    class_ids, student_ids = _scope(db, user, class_id, student_id, subject_id)
    teacher_id = user.id if user.role.name == "teacher" else None
    report = gap_analysis(
        db, student_ids, class_ids, user.school_id, subject_id, teacher_id
    )
    report["mode"] = "student" if user.role.name == "student" else "class"
    return report


# ---------------------------------------------------------------- adaptive engine

@router.post("/adaptive/next-question", response_model=dict)
def next_adaptive_question(
    subject_id: str | None = None,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    class_ids, _ = _scope(db, user, None, None, subject_id)
    return recommend_next(db, user, class_ids, subject_id)


@router.post("/adaptive/answer", response_model=dict)
def answer_adaptive_question(
    payload: AdaptiveAnswerIn,
    request: Request,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    question = db.get(Question, payload.question_id)
    if question is None or not question.is_published:
        raise HTTPException(status_code=404, detail="Soal tidak tersedia")
    if question.question_type not in ADAPTIVE_TYPES:
        raise HTTPException(status_code=400, detail="Latihan adaptif hanya untuk soal objektif yang dapat dijawab tanpa kunci")
    if question.competency_id is None:
        raise HTTPException(status_code=400, detail="Soal belum memiliki kompetensi")
    competency = db.get(Competency, question.competency_id)
    if competency is None:
        raise HTTPException(status_code=404, detail="Kompetensi tidak ditemukan")
    assert_school_scope(user, db.get(Subject, question.subject_id).school_id)

    if payload.client_id:
        replay = db.scalar(
            select(AdaptivePractice).where(
                AdaptivePractice.student_id == user.id,
                AdaptivePractice.client_id == payload.client_id,
            )
        )
        if replay is not None:
            if replay.question_id != question.id:
                raise HTTPException(status_code=409, detail="client_id sudah dipakai untuk soal lain")
            context = replay.context_json or {}
            return {
                "idempotent": True,
                "is_correct": replay.is_correct,
                "points_earned": replay.points_earned,
                "mastery_before": context.get("mastery_before"),
                "mastery_after": context.get("mastery_after"),
                "status": context.get("status"),
                "evidence": {"note": "Jawaban ini sudah tercatat sebelumnya."},
            }

    params = effective_params(db)
    before_rows = mastery_snapshot(db, user.id, [competency], params)
    mastery_before = before_rows[0]["mastery_probability"] if before_rows else params["p_init"]
    is_correct, earned = grade_objective(db, question, payload.answer)
    if is_correct is None:
        raise HTTPException(status_code=400, detail="Soal ini tidak dapat dinilai otomatis")

    practice = AdaptivePractice(
        student_id=user.id,
        question_id=question.id,
        competency_id=competency.id,
        answer_json=payload.answer,
        is_correct=bool(is_correct),
        points_earned=round(float(earned), 2),
        difficulty_at_time=question.difficulty,
        context_json={
            "mastery_before": mastery_before,
            "params": params,
            "gap_category": question.gap_category or "konsep",
        },
        client_id=payload.client_id,
        answered_at=utcnow(),
    )
    db.add(practice)
    db.flush()
    rebuild_mastery(db, user.id, [competency.id])
    after = db.scalar(
        select(StudentCompetencyMastery).where(
            StudentCompetencyMastery.student_id == user.id,
            StudentCompetencyMastery.competency_id == competency.id,
        )
    )
    mastery_after = float(after.mastery_probability) if after else mastery_before
    status = status_for(mastery_after, after.practice_count if after else 0, params)
    practice.context_json = {
        **practice.context_json,
        "mastery_after": round(mastery_after, 6),
        "status": status,
    }
    log_audit(db, user, "answer_adaptive_practice", "adaptive_practice", practice.id, {
        "question_id": question.id, "is_correct": bool(is_correct)
    }, request)
    db.commit()
    return {
        "idempotent": False,
        "is_correct": bool(is_correct),
        "points_earned": round(float(earned), 2),
        "mastery_before": mastery_before,
        "mastery_after": round(mastery_after, 6),
        "status": status,
        "evidence": {
            "source": "adaptive_practices + bkt_history",
            "params": params,
            "gap_category": question.gap_category or "konsep",
            "computed_at": utcnow().isoformat() + "Z",
        },
    }


# ---------------------------------------------------------------- recommendations

@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(
    student_id: str | None = None,
    class_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    _, student_ids = _scope(db, user, class_id, student_id, None)
    if not student_ids:
        return []
    return db.scalars(
        select(LearningRecommendation)
        .where(LearningRecommendation.student_id.in_(student_ids))
        .order_by(LearningRecommendation.priority.desc(), LearningRecommendation.created_at.desc())
        .limit(200)
    ).all()


@router.post("/recommendations/refresh", response_model=list[RecommendationOut])
def refresh_recommendations_endpoint(
    request: Request,
    student_id: str | None = None,
    class_id: str | None = None,
    subject_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    class_ids, student_ids = _scope(db, user, class_id, student_id, subject_id)
    if len(student_ids) != 1:
        raise HTTPException(status_code=400, detail="Pilih satu siswa untuk menyegarkan rekomendasi")
    target = student_ids[0]
    rows = refresh_recommendations(db, target, class_ids, user.school_id, subject_id)
    log_audit(db, user, "refresh_recommendations", "student", target, {"generated": len(rows)}, request)
    db.commit()
    return rows


# ---------------------------------------------------------------- honest evaluation & config

@router.get("/dropout-evaluation", response_model=dict)
def dropout_evaluation(
    class_id: str | None = None,
    student_id: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    result = load_dropout_evaluation()
    class_ids, student_ids = _scope(db, user, class_id, student_id, None)
    _, competencies = competency_scope(db, user.school_id, class_ids, None)
    result["advisory_indicators"] = advisory_indicators(db, student_ids, competencies)
    return result


@router.get("/bkt-params", response_model=dict)
def get_bkt_params(
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    row = db.scalar(select(EngineConfig).where(EngineConfig.key == ENGINE_CONFIG_KEY))
    return {
        "params": effective_params(db),
        "source": "database_override" if row else "environment_defaults",
        "updated_at": row.updated_at.isoformat() + "Z" if row else None,
        "definitions": {
            "p_init": "Probabilitas penguasaan awal sebelum ada jawaban.",
            "p_transit": "Peluang akuisisi keterampilan setelah satu kesempatan belajar.",
            "p_slip": "Peluang menjawab salah meskipun sudah menguasai.",
            "p_guess": "Peluang menjawab benar hanya dengan menebak.",
            "mastery_threshold": "Ambang batas status mastered.",
        },
    }


@router.put("/bkt-params", response_model=dict)
def update_bkt_params(
    payload: BktParamsIn,
    request: Request,
    user: User = Depends(require_roles("admin")),
    db: DBSession = Depends(get_db),
):
    incoming = payload.model_dump(exclude={"recompute"}, exclude_none=True)
    try:
        params = validate_params(incoming)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    row = db.scalar(select(EngineConfig).where(EngineConfig.key == ENGINE_CONFIG_KEY))
    if row is None:
        row = EngineConfig(key=ENGINE_CONFIG_KEY, value_json=params, updated_by=user.id)
        db.add(row)
    else:
        row.value_json = params
        row.updated_by = user.id
    recomputed = 0
    if payload.recompute:
        recomputed = rebuild_school(db, user.school_id)
    log_audit(db, user, "update_bkt_params", "engine_config", ENGINE_CONFIG_KEY, {
        "params": params, "recomputed_students": recomputed
    }, request)
    db.commit()
    return {"params": params, "recomputed_students": recomputed}
