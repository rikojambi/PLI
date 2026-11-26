"""Fase 5 dashboard aggregation.

All figures are derived from persisted Fase 2/Fase 3 evidence: assessment
results, submitted answers, adaptive practice and BKT history. Every public
function accepts an explicit user and applies school, class and student scope
before touching data. Students can never resolve another student's identifier.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import teacher_class_ids
from app.db.base import utcnow
from app.models.academic import Class, ClassMember, Competency, Subject, TeacherClass
from app.models.assessment import Assessment, AssessmentResult, Question, StudentAnswer, StudentAttempt
from app.models.core import Role, User
from app.models.intelligence import BktHistory, LearningRecommendation, StudentNote
from app.services.intelligence import competency_scope, mastery_snapshot

PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
PERIOD_OPTIONS = [
    {"value": "7d", "label": "7 hari terakhir"},
    {"value": "30d", "label": "30 hari terakhir"},
    {"value": "90d", "label": "90 hari terakhir"},
    {"value": "365d", "label": "Satu tahun terakhir"},
    {"value": "all", "label": "Semua data"},
    {"value": "custom", "label": "Rentang tanggal"},
]


def _parse_date(value: str, *, end: bool = False) -> datetime:
    text = value.strip().replace("Z", "")
    if len(text) == 10:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999) if end else parsed
    return datetime.fromisoformat(text)


def period_range(period: str | None, date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    """Resolve a dashboard period into naive UTC bounds."""
    period = period or "30d"
    if period == "all":
        return None, None
    if period == "custom":
        if not date_from or not date_to:
            raise HTTPException(status_code=400, detail="Rentang tanggal memerlukan tanggal mulai dan akhir")
        try:
            start, finish = _parse_date(date_from), _parse_date(date_to, end=True)
        except ValueError:
            raise HTTPException(status_code=400, detail="Format tanggal tidak dikenal") from None
        if start > finish:
            raise HTTPException(status_code=400, detail="Tanggal mulai harus sebelum tanggal akhir")
        return start, finish
    if period not in PERIOD_DAYS:
        raise HTTPException(status_code=400, detail="Periode tidak dikenal")
    finish = utcnow()
    return finish - timedelta(days=PERIOD_DAYS[period]), finish


def allowed_class_ids(db: DBSession, user: User) -> list[str]:
    if user.role.name == "admin":
        return list(db.scalars(select(Class.id).where(Class.school_id == user.school_id)).all())
    if user.role.name == "teacher":
        assigned = teacher_class_ids(db, user)
        if not assigned:
            return []
        return list(
            db.scalars(
                select(Class.id).where(
                    Class.school_id == user.school_id,
                    Class.id.in_(assigned),
                )
            ).all()
        )
    return list(
        db.scalars(
            select(ClassMember.class_id)
            .join(Class, ClassMember.class_id == Class.id)
            .where(ClassMember.user_id == user.id, Class.school_id == user.school_id)
        ).all()
    )


def _assert_class(db: DBSession, user: User, class_id: str, allowed: list[str]) -> None:
    if class_id not in allowed:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan dalam cakupan Anda")
    row = db.get(Class, class_id)
    if not row or row.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")


def resolve_students(
    db: DBSession,
    user: User,
    class_id: str | None,
    student_id: str | None,
) -> tuple[list[User], list[str]]:
    """Students visible under the requested filters, plus scoped class ids."""
    allowed = allowed_class_ids(db, user)
    if class_id:
        _assert_class(db, user, class_id, allowed)
        allowed = [class_id]

    if user.role.name == "student":
        if student_id and student_id != user.id:
            raise HTTPException(status_code=403, detail="Siswa hanya dapat melihat data dirinya sendiri")
        if not allowed:
            return [user], []
        return [user], allowed

    if student_id:
        target = db.get(User, student_id)
        role = db.get(Role, target.role_id) if target else None
        if not target or target.school_id != user.school_id or not role or role.name != "student":
            raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
        memberships = set(
            db.scalars(
                select(ClassMember.class_id).where(ClassMember.user_id == student_id)
            ).all()
        )
        if not memberships.intersection(allowed):
            raise HTTPException(status_code=404, detail="Siswa tidak berada dalam cakupan kelas Anda")
        return [target], [item for item in allowed if item in memberships]

    if not allowed:
        return [], []
    students = db.scalars(
        select(User)
        .join(ClassMember, ClassMember.user_id == User.id)
        .join(Role, Role.id == User.role_id)
        .where(
            ClassMember.class_id.in_(allowed),
            User.school_id == user.school_id,
            Role.name == "student",
        )
        .order_by(User.full_name)
    ).all()
    return list(dict.fromkeys(students)), allowed


def dashboard_filters(db: DBSession, user: User) -> dict[str, Any]:
    class_ids = allowed_class_ids(db, user)
    classes = []
    if class_ids:
        classes = [
            {"id": row.id, "name": row.name}
            for row in db.scalars(
                select(Class).where(Class.id.in_(class_ids)).order_by(Class.name)
            ).all()
        ]
    _, competencies = competency_scope(
        db,
        user.school_id,
        class_ids,
        teacher_id=user.id if user.role.name == "teacher" else None,
    )
    subject_ids = sorted({item.subject_id for item in competencies})
    subjects = []
    if subject_ids:
        subjects = [
            {"id": row.id, "name": row.name, "code": row.code}
            for row in db.scalars(select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.name)).all()
        ]
    visible_students = resolve_students(db, user, None, None)[0]
    return {
        "classes": classes,
        "subjects": subjects,
        "students": [
            {"id": item.id, "name": item.full_name}
            for item in visible_students
        ],
        "competencies": [
            {"id": item.id, "name": item.name, "code": item.code, "subject_id": item.subject_id}
            for item in competencies
        ],
        "periods": PERIOD_OPTIONS,
        "scope": "self" if user.role.name == "student" else user.role.name,
    }


def result_rows(
    db: DBSession,
    user: User,
    *,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    students, class_ids = resolve_students(db, user, class_id, student_id)
    student_ids = [item.id for item in students]
    start, finish = period_range(period, date_from, date_to)
    if not student_ids or not class_ids:
        return []

    query = (
        select(AssessmentResult, Assessment, Class, Subject, User)
        .join(Assessment, AssessmentResult.assessment_id == Assessment.id)
        .join(Class, Assessment.class_id == Class.id)
        .join(Subject, Assessment.subject_id == Subject.id)
        .join(User, AssessmentResult.student_id == User.id)
        .where(
            Class.school_id == user.school_id,
            Assessment.class_id.in_(class_ids),
            AssessmentResult.student_id.in_(student_ids),
        )
    )
    if subject_id:
        query = query.where(Assessment.subject_id == subject_id)
    if start:
        query = query.where(AssessmentResult.graded_at >= start)
    if finish:
        query = query.where(AssessmentResult.graded_at <= finish)
    if competency_id:
        query = query.where(
            select(StudentAnswer.id)
            .join(StudentAttempt, StudentAnswer.attempt_id == StudentAttempt.id)
            .join(Question, StudentAnswer.question_id == Question.id)
            .where(
                StudentAttempt.id == AssessmentResult.attempt_id,
                Question.competency_id == competency_id,
            ).exists()
        )
    rows = db.execute(query.order_by(AssessmentResult.graded_at.desc())).all()
    return [
        {
            "id": result.id,
            "date": result.graded_at.isoformat() + "Z",
            "student_id": student.id,
            "student_name": student.full_name,
            "class_name": klass.name,
            "subject_name": subject.name,
            "assessment_title": assessment.title,
            "score": round(float(result.score), 2),
            "mastery_percent": round(float(result.mastery_percent or 0.0), 2),
        }
        for result, assessment, klass, subject, student in rows
    ]


def _series_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    mastery: dict[str, list[float]] = defaultdict(list)
    for row in results:
        day = row["date"][:10]
        buckets[day].append(row["score"])
        mastery[day].append(row["mastery_percent"])
    return [
        {
            "label": day,
            "score": round(sum(values) / len(values), 2),
            "mastery_percent": round(sum(mastery[day]) / len(mastery[day]), 2),
            "attempts": len(values),
        }
        for day, values in sorted(buckets.items())
    ]


def progress(
    db: DBSession,
    user: User,
    *,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    students, class_ids = resolve_students(db, user, class_id, student_id)
    start, finish = period_range(period, date_from, date_to)
    results = result_rows(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    scores = _series_from_results(results)

    bkt_query = (
        select(BktHistory)
        .where(BktHistory.student_id.in_([item.id for item in students]))
        .order_by(BktHistory.occurred_at, BktHistory.id)
    )
    if class_ids and competency_id:
        bkt_query = bkt_query.where(BktHistory.competency_id == competency_id)
    elif class_ids and subject_id:
        comp_ids = [
            item
            for item in db.scalars(select(Competency.id).where(Competency.subject_id == subject_id)).all()
        ]
        bkt_query = bkt_query.where(BktHistory.competency_id.in_(comp_ids))
    if start:
        bkt_query = bkt_query.where(BktHistory.occurred_at >= start)
    if finish:
        bkt_query = bkt_query.where(BktHistory.occurred_at <= finish)
    history = db.scalars(bkt_query).all()
    posterior: dict[str, list[float]] = defaultdict(list)
    for row in history:
        posterior[row.occurred_at.date().isoformat()].append(float(row.posterior_probability))
    bkt_series = [
        {
            "label": day,
            "mastery_percent": round(sum(values) / len(values) * 100, 2),
            "observations": len(values),
        }
        for day, values in sorted(posterior.items())
    ]

    return {
        "scores": scores,
        "mastery": bkt_series,
        "observation_count": len(history),
        "result_count": len(results),
        "evidence": {
            "source": "assessment_results + bkt_history",
            "note": "Nilai berasal dari asesmen yang dinilai; penguasaan dari BKT atas jawaban nyata.",
        },
    }


def overview(
    db: DBSession,
    user: User,
    *,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    results = result_rows(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    students, _ = resolve_students(db, user, class_id, student_id)
    trend = progress(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    scores = [row["score"] for row in results]
    return {
        "student_count": len(students),
        "assessment_count": len({row["assessment_title"] for row in results}),
        "result_count": len(results),
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "passing_count": sum(1 for score in scores if score >= 70.0),
        "trend": trend["scores"],
        "mastery_trend": trend["mastery"],
        "evidence": trend["evidence"],
    }


def student_profile(
    db: DBSession,
    user: User,
    student_id: str,
    *,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    students, class_ids = resolve_students(db, user, class_id, student_id)
    if len(students) != 1:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    student = students[0]
    _, competencies = competency_scope(
        db,
        student.school_id,
        class_ids,
        subject_id,
        teacher_id=user.id if user.role.name == "teacher" else None,
    )
    if competency_id:
        competencies = [item for item in competencies if item.id == competency_id]
    mastery = mastery_snapshot(db, student.id, competencies)
    results = result_rows(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student.id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    recommendations = db.scalars(
        select(LearningRecommendation)
        .where(LearningRecommendation.student_id == student.id, LearningRecommendation.is_completed.is_(False))
        .order_by(LearningRecommendation.priority.desc())
        .limit(20)
    ).all()
    notes = db.scalars(
        select(StudentNote)
        .where(StudentNote.student_id == student.id)
        .order_by(StudentNote.created_at.desc())
        .limit(20)
    ).all()
    trend = progress(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student.id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    class_names = [
        row.name
        for row in db.scalars(
            select(Class).join(ClassMember, ClassMember.class_id == Class.id).where(ClassMember.user_id == student.id)
        ).all()
    ]
    return {
        "student": {
            "id": student.id,
            "full_name": student.full_name,
            "username": student.username,
            "student_number": student.student_number,
            "classes": class_names,
        },
        "mastery": mastery,
        "results": results,
        "recommendations": [
            {
                "id": item.id,
                "title": item.title,
                "reason": item.reason,
                "priority": item.priority,
                "rec_type": item.rec_type,
            }
            for item in recommendations
        ],
        "notes": [
            {
                "id": item.id,
                "title": item.title,
                "note_type": item.note_type,
                "is_read": item.is_read,
                "created_at": item.created_at.isoformat() + "Z",
            }
            for item in notes
        ],
        "trend": trend,
        "evidence": {
            "source": "student_competency_mastery + assessment_results + learning_recommendations + student_notes",
            "note": "Profil adalah ringkasan untuk guru/siswa; bukan prediksi dropout atau vonis otomatis.",
        },
    }


def export_data(
    db: DBSession,
    user: User,
    *,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    results = result_rows(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    trend = progress(
        db,
        user,
        class_id=class_id,
        subject_id=subject_id,
        competency_id=competency_id,
        student_id=student_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    students, scoped_classes = resolve_students(db, user, class_id, student_id)
    competency_rows: list[dict[str, Any]] = []
    for student in students[:100]:
        _, competencies = competency_scope(
            db,
            student.school_id,
            scoped_classes,
            subject_id,
            teacher_id=user.id if user.role.name == "teacher" else None,
        )
        if competency_id:
            competencies = [item for item in competencies if item.id == competency_id]
        for row in mastery_snapshot(db, student.id, competencies):
            competency_rows.append(
                {
                    "student_name": student.full_name,
                    "code": row["code"],
                    "competency": row["name"],
                    "mastery_percent": row["mastery_percent"],
                    "status": row["status"],
                    "practice_count": row["practice_count"],
                    "observations": row["observation_count"],
                }
            )
    return {
        "filters": {
            "class_id": class_id,
            "subject_id": subject_id,
            "competency_id": competency_id,
            "student_id": student_id,
            "period": period or "30d",
            "date_from": date_from,
            "date_to": date_to,
        },
        "results": results,
        "scores": trend["scores"],
        "mastery": trend["mastery"],
        "competencies": competency_rows,
    }
