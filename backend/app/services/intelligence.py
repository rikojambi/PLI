"""Fase 3 Intelligence Engine: BKT, mastery profiles, adaptive practice, gaps.

Every number produced here comes from graded answers that actually exist in the
database. The engine never invents observations and never turns an indicator
into an automated verdict. BKT parameters are server-side and can be
reconfigured by an administrator; all updates are audited.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.db.base import utcnow
from app.models.academic import (
    ClassMember,
    Competency,
    LearningMaterial,
    Subject,
    TeacherClass,
)
from app.models.assessment import (
    Assessment,
    Question,
    QuestionOption,
    StudentAnswer,
    StudentAttempt,
)
from app.models.core import User
from app.models.intelligence import (
    AdaptivePractice,
    BktHistory,
    EngineConfig,
    LearningRecommendation,
    StudentCompetencyMastery,
)
from app.schemas.learning import GAP_CATEGORIES, QuestionOptionOut, QuestionOut
from app.services.grading import OBJECTIVE_TYPES, grade_objective

ENGINE_CONFIG_KEY = "bkt"
GENERATED_REC_TYPES = ("adaptive_practice", "remedial_focus")
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
STATUS_ORDER = {"not_started": 0, "emerging": 1, "developing": 2, "proficient": 3, "mastered": 4}
# Matching questions need the answer-key side (match_key) to be answerable.
# That field is deliberately hidden from students, so adaptive practice only
# uses objective types a student can answer from the public question view.
ADAPTIVE_TYPES = OBJECTIVE_TYPES - {"matching"}


def default_params() -> dict[str, float]:
    """Environment defaults. They are never read from the browser."""
    return {
        "p_init": settings.bkt_p_init,
        "p_transit": settings.bkt_p_transit,
        "p_slip": settings.bkt_p_slip,
        "p_guess": settings.bkt_p_guess,
        "mastery_threshold": settings.bkt_mastery_threshold,
    }


def validate_params(raw: dict[str, Any]) -> dict[str, float]:
    """Validate and normalise BKT parameters.

    ``p_slip + p_guess < 1`` is required: otherwise an answer carries no
    information (or reverses the direction of the update) and the model would
    be numerically misleading.
    """
    merged = default_params()
    if not isinstance(raw, dict):
        raise ValueError("Parameter harus berupa objek")
    unknown = set(raw) - set(merged)
    if unknown:
        raise ValueError(f"Parameter tidak dikenal: {', '.join(sorted(unknown))}")
    for key, value in raw.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Parameter {key} harus berupa angka") from None
        if not math.isfinite(number):
            raise ValueError(f"Parameter {key} harus berupa angka hingga")
        merged[key] = number
    for key in ("p_init", "p_transit", "p_slip", "p_guess"):
        if not 0.0 < merged[key] < 1.0:
            raise ValueError(f"{key} harus antara 0 dan 1 (eksklusif)")
    if not 0.0 < merged["mastery_threshold"] <= 1.0:
        raise ValueError("mastery_threshold harus antara 0 dan 1")
    if merged["p_slip"] + merged["p_guess"] >= 1.0 - 1e-6:
        raise ValueError("p_slip + p_guess harus kurang dari 1 agar jawaban bermakna")
    return {key: round(value, 6) for key, value in merged.items()}


def effective_params(db: DBSession) -> dict[str, float]:
    row = db.scalar(select(EngineConfig).where(EngineConfig.key == ENGINE_CONFIG_KEY))
    raw = default_params()
    if row is not None:
        raw.update(row.value_json or {})
    return validate_params(raw)


def bkt_update(prior: float, correct: bool, params: dict[str, float]) -> float:
    """One BKT step: Bayesian evidence update, then learning transition.

    The posterior after observing the answer is calculated first; only then is
    the probability of acquiring the skill (``p_transit``) applied. This order
    is deterministic and is covered by unit tests.
    """
    p = min(max(float(prior), 0.0), 1.0)
    slip = params["p_slip"]
    guess = params["p_guess"]
    if correct:
        denominator = p * (1.0 - slip) + (1.0 - p) * guess
        posterior = p * (1.0 - slip) / denominator if denominator else p
    else:
        denominator = p * slip + (1.0 - p) * (1.0 - guess)
        posterior = p * slip / denominator if denominator else p
    posterior += (1.0 - posterior) * params["p_transit"]
    return round(min(max(posterior, 0.0), 1.0), 6)


def status_for(prob: float, practice_count: int, params: dict[str, float]) -> str:
    if practice_count == 0:
        return "not_started"
    threshold = params["mastery_threshold"]
    if prob >= threshold:
        return "mastered"
    if prob >= threshold - 0.15:
        return "proficient"
    if prob >= 0.5:
        return "developing"
    return "emerging"


def desired_difficulty(prob: float) -> str:
    if prob < 0.4:
        return "easy"
    if prob < 0.7:
        return "medium"
    return "hard"


@dataclass(frozen=True)
class Observation:
    evidence_id: str
    source: str
    competency_id: str
    correct: bool
    occurred_at: datetime
    gap_category: str


def collect_observations(
    db: DBSession, student_id: str, competency_ids: Iterable[str] | None = None
) -> list[Observation]:
    """Collect only real graded answers and adaptive practice answers."""
    allowed = set(competency_ids) if competency_ids is not None else None
    observations: list[Observation] = []
    rows = db.execute(
        select(StudentAnswer, Question, StudentAttempt)
        .join(StudentAttempt, StudentAnswer.attempt_id == StudentAttempt.id)
        .join(Question, StudentAnswer.question_id == Question.id)
        .where(
            StudentAttempt.student_id == student_id,
            StudentAttempt.status == "submitted",
            StudentAnswer.is_correct.isnot(None),
            Question.competency_id.isnot(None),
        )
    ).all()
    for answer, question, attempt in rows:
        if allowed is not None and question.competency_id not in allowed:
            continue
        occurred = answer.answered_at or answer.updated_at or attempt.submitted_at or utcnow()
        observations.append(
            Observation(
                evidence_id=answer.id,
                source="assessment",
                competency_id=question.competency_id,
                correct=bool(answer.is_correct),
                occurred_at=occurred,
                gap_category=question.gap_category or "konsep",
            )
        )
    practices = db.scalars(
        select(AdaptivePractice).where(
            AdaptivePractice.student_id == student_id,
            AdaptivePractice.competency_id.isnot(None),
        )
    ).all()
    for practice in practices:
        if allowed is not None and practice.competency_id not in allowed:
            continue
        observations.append(
            Observation(
                evidence_id=practice.id,
                source="adaptive",
                competency_id=practice.competency_id,
                correct=bool(practice.is_correct),
                occurred_at=practice.answered_at or practice.created_at,
                gap_category="konsep",
            )
        )
    observations.sort(key=lambda item: (item.occurred_at, item.source, item.evidence_id))
    return observations


def rebuild_mastery(
    db: DBSession, student_id: str, competency_ids: Iterable[str] | None = None
) -> list[StudentCompetencyMastery]:
    """Deterministically replay BKT from observations and persist the profile.

    Replaying from scratch (instead of applying deltas) makes regrading and
    repeated submissions safe: the same observations always yield the same
    mastery state, and every history row keeps a link to its evidence.
    """
    params = effective_params(db)
    ids = list(dict.fromkeys(competency_ids)) if competency_ids is not None else None
    observations = collect_observations(db, student_id, ids)
    grouped: dict[str, list[Observation]] = {}
    for observation in observations:
        grouped.setdefault(observation.competency_id, []).append(observation)

    statement = delete(BktHistory).where(BktHistory.student_id == student_id)
    if ids is not None:
        statement = statement.where(BktHistory.competency_id.in_(ids))
    db.execute(statement)
    db.flush()

    touched = set(grouped)
    if ids is not None:
        touched.update(ids)

    results: list[StudentCompetencyMastery] = []
    for competency_id in sorted(touched):
        items = grouped.get(competency_id, [])
        prior = params["p_init"]
        steps: list[tuple[Observation, float, float]] = []
        for observation in items:
            posterior = bkt_update(prior, observation.correct, params)
            steps.append((observation, prior, posterior))
            prior = posterior
        row = db.scalar(
            select(StudentCompetencyMastery).where(
                StudentCompetencyMastery.student_id == student_id,
                StudentCompetencyMastery.competency_id == competency_id,
            )
        )
        if row is None:
            row = StudentCompetencyMastery(
                student_id=student_id, competency_id=competency_id
            )
            db.add(row)
        row.mastery_probability = round(prior, 6)
        row.practice_count = len(items)
        row.correct_count = sum(1 for item in items if item.correct)
        row.status = status_for(prior, len(items), params)
        row.last_practiced_at = max((item.occurred_at for item in items), default=None)
        db.flush()
        for observation, before, after in steps:
            db.add(
                BktHistory(
                    student_id=student_id,
                    competency_id=competency_id,
                    mastery_id=row.id,
                    prior_probability=before,
                    posterior_probability=after,
                    observed_correct=observation.correct,
                    params_json=params,
                    source=observation.source,
                    evidence_id=observation.evidence_id,
                    occurred_at=observation.occurred_at,
                )
            )
        results.append(row)
    db.flush()
    return results


def rebuild_school(db: DBSession, school_id: str) -> int:
    """Recompute every student profile after an engine parameter change."""
    students = db.scalars(
        select(User).where(User.school_id == school_id, User.role.has(name="student"))
    ).all()
    for student in students:
        existing = db.scalars(
            select(StudentCompetencyMastery.competency_id).where(
                StudentCompetencyMastery.student_id == student.id
            )
        ).all()
        observed = {item.competency_id for item in collect_observations(db, student.id)}
        rebuild_mastery(db, student.id, sorted(set(existing) | observed))
    return len(students)


def competency_scope(
    db: DBSession,
    school_id: str,
    class_ids: Iterable[str],
    subject_id: str | None = None,
    teacher_id: str | None = None,
) -> tuple[list[str], list[Competency]]:
    """Subjects/competencies relevant to the requested class scope."""
    query = select(Subject.id).where(Subject.school_id == school_id, Subject.is_active.is_(True))
    if subject_id:
        query = query.where(Subject.id == subject_id)
    subject_ids = list(db.scalars(query).all())
    ids = list(class_ids)
    if ids:
        active = set(db.scalars(select(Assessment.subject_id).where(Assessment.class_id.in_(ids))).all())
        if teacher_id:
            active.update(
                db.scalars(
                    select(TeacherClass.subject_id).where(
                        TeacherClass.teacher_id == teacher_id,
                        TeacherClass.class_id.in_(ids),
                        TeacherClass.subject_id.isnot(None),
                    )
                ).all()
            )
        # Only narrow the curriculum when the class actually has evidence or
        # an explicit teaching assignment. Otherwise students would see an
        # empty profile even though `not_started` is a meaningful state.
        if active:
            subject_ids = [sid for sid in subject_ids if sid in active]
    if not subject_ids:
        return [], []
    competencies = db.scalars(
        select(Competency).where(
            Competency.subject_id.in_(subject_ids),
            Competency.is_active.is_(True),
        ).order_by(Competency.order_index, Competency.code)
    ).all()
    return subject_ids, list(competencies)


def mastery_snapshot(
    db: DBSession,
    student_id: str,
    competencies: Iterable[Competency],
    params: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    params = params or effective_params(db)
    stored = {
        row.competency_id: row
        for row in db.scalars(
            select(StudentCompetencyMastery).where(
                StudentCompetencyMastery.student_id == student_id
            )
        ).all()
    }
    result: list[dict[str, Any]] = []
    for competency in competencies:
        row = stored.get(competency.id)
        probability = row.mastery_probability if row else params["p_init"]
        count = row.practice_count if row else 0
        correct = row.correct_count if row else 0
        history = db.scalars(
            select(BktHistory)
            .where(
                BktHistory.student_id == student_id,
                BktHistory.competency_id == competency.id,
            )
            .order_by(BktHistory.occurred_at, BktHistory.id)
        ).all()
        result.append(
            {
                "competency_id": competency.id,
                "code": competency.code,
                "name": competency.name,
                "subject_id": competency.subject_id,
                "mastery_probability": round(float(probability), 6),
                "mastery_percent": round(float(probability) * 100, 2),
                "status": status_for(float(probability), count, params),
                "practice_count": count,
                "correct_count": correct,
                "accuracy_percent": round(correct / count * 100, 2) if count else 0.0,
                "last_practiced_at": row.last_practiced_at.isoformat() + "Z" if row and row.last_practiced_at else None,
                "probability_trend": [round(float(item.posterior_probability), 6) for item in history],
                "observation_count": len(history),
                "evidence": {
                    "source": "bkt_history + student_answers + adaptive_practices",
                    "params": params,
                    "note": "Probabilitas dihitung dari jawaban nyata; bukan nilai asesmen mentah.",
                },
            }
        )
    return result


def public_question(db: DBSession, question: Question) -> QuestionOut:
    """Student-safe view: no answer key, rubric, or explanation."""
    data = QuestionOut.model_validate(question)
    options = db.scalars(
        select(QuestionOption).where(QuestionOption.question_id == question.id).order_by(QuestionOption.position)
    ).all()
    data.options = [
        QuestionOptionOut(id=option.id, label=option.label, content=option.content, position=option.position)
        for option in options
    ]
    data.rubric_json = {}
    data.explanation = None
    return data


def recommend_next(
    db: DBSession,
    student: User,
    class_ids: Iterable[str],
    subject_id: str | None = None,
) -> dict[str, Any]:
    """Pick one unseen objective question at a level matching low mastery."""
    params = effective_params(db)
    _, competencies = competency_scope(db, student.school_id, class_ids, subject_id)
    competency_ids = [item.id for item in competencies]
    if not competency_ids:
        return {"question": None, "reason": "Belum ada kompetensi aktif untuk mata pelajaran ini.", "evidence": {}}

    answered = set(
        db.scalars(
            select(StudentAnswer.question_id)
            .join(StudentAttempt, StudentAnswer.attempt_id == StudentAttempt.id)
            .where(StudentAttempt.student_id == student.id)
        ).all()
    )
    practiced = set(
        db.scalars(
            select(AdaptivePractice.question_id).where(AdaptivePractice.student_id == student.id)
        ).all()
    )
    seen = answered | practiced
    candidates = [
        question
        for question in db.scalars(
            select(Question).where(
                Question.is_published.is_(True),
                Question.subject_id.in_(
                    db.scalars(select(Competency.subject_id).where(Competency.id.in_(competency_ids))).all()
                ),
                Question.competency_id.in_(competency_ids),
                Question.question_type.in_(ADAPTIVE_TYPES),
            )
        ).all()
        if question.id not in seen
    ]
    if not candidates:
        return {
            "question": None,
            "reason": "Semua soal objektif yang tersedia sudah dikerjakan.",
            "evidence": {"candidate_count": 0, "excluded_count": len(seen)},
        }

    snapshot = {row["competency_id"]: row for row in mastery_snapshot(db, student.id, competencies, params)}
    by_competency: dict[str, list[Question]] = {}
    for question in candidates:
        by_competency.setdefault(question.competency_id, []).append(question)
    target_id = min(
        by_competency,
        key=lambda cid: (
            snapshot[cid]["mastery_probability"],
            STATUS_ORDER[snapshot[cid]["status"]],
            cid,
        ),
    )
    target = snapshot[target_id]
    wanted = desired_difficulty(target["mastery_probability"])
    chosen = min(
        by_competency[target_id],
        key=lambda question: (
            0 if question.difficulty == wanted else 1,
            abs(DIFFICULTY_ORDER.get(question.difficulty, 1) - DIFFICULTY_ORDER[wanted]),
            question.id,
        ),
    )
    return {
        "question": public_question(db, chosen).model_dump(),
        "reason": (
            f"Kompetensi {target['code']} memiliki probabilitas penguasaan "
            f"{target['mastery_percent']}%, jadi soal bertingkat {wanted} dipilih."
        ),
        "evidence": {
            "competency_id": target_id,
            "competency_code": target["code"],
            "mastery_probability": target["mastery_probability"],
            "mastery_status": target["status"],
            "chosen_difficulty": chosen.difficulty,
            "requested_difficulty": wanted,
            "candidate_count": len(candidates),
            "excluded_count": len(seen),
            "gap_category": chosen.gap_category or "konsep",
            "params": params,
            "note": "Indikator untuk ditinjau guru, bukan vonis otomatis.",
        },
    }


def gap_analysis(
    db: DBSession,
    student_ids: Iterable[str],
    class_ids: Iterable[str],
    school_id: str,
    subject_id: str | None = None,
    teacher_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate real wrong-answer categories into a learning-gap report."""
    params = effective_params(db)
    _, competencies = competency_scope(db, school_id, class_ids, subject_id, teacher_id)
    ids = list(student_ids)
    observations: list[Observation] = []
    for student_id in ids:
        observations.extend(collect_observations(db, student_id, [item.id for item in competencies]))

    stats: dict[str, dict[str, Any]] = {}
    for observation in observations:
        stat = stats.setdefault(
            observation.competency_id,
            {"correct": 0, "total": 0, "categories": {category: 0 for category in GAP_CATEGORIES}},
        )
        stat["total"] += 1
        if observation.correct:
            stat["correct"] += 1
        else:
            category = observation.gap_category if observation.gap_category in GAP_CATEGORIES else "konsep"
            stat["categories"][category] += 1

    profile: dict[str, float] = {}
    for student_id in ids:
        for row in mastery_snapshot(db, student_id, competencies, params):
            cid = row["competency_id"]
            profile[cid] = profile.get(cid, 0.0) + row["mastery_probability"] / max(len(ids), 1)

    rows: list[dict[str, Any]] = []
    lookup = {item.id: item for item in competencies}
    for competency_id, stat in stats.items():
        competency = lookup.get(competency_id)
        if competency is None:
            continue
        accuracy = stat["correct"] / stat["total"] if stat["total"] else 0.0
        mastery = profile.get(competency_id, params["p_init"])
        categories = stat["categories"]
        # Deterministic tie-break: alphabetical category order.
        max_count = max(categories.values())
        tied = sorted(category for category, count in categories.items() if count == max_count)
        dominant = tied[0] if max_count else "konsep"
        rows.append(
            {
                "competency_id": competency_id,
                "code": competency.code,
                "name": competency.name,
                "subject_id": competency.subject_id,
                "accuracy_percent": round(accuracy * 100, 2),
                "mastery_probability": round(mastery, 6),
                "gap_score": round((1.0 - accuracy) * 0.6 + (1.0 - mastery) * 0.4, 4),
                "dominant_category": dominant,
                "category_counts": categories,
                "observations": stat["total"],
                "evidence": {
                    "source": "student_answers + adaptive_practices (salah dinilai)",
                    "note": "Kategori berasal dari label guru pada soal, bukan tebakan otomatis.",
                },
            }
        )
    rows.sort(key=lambda item: (-item["gap_score"], item["code"]))
    return {
        "rows": rows,
        "student_count": len(ids),
        "observation_count": len(observations),
        "evidence": {
            "categories": sorted(GAP_CATEGORIES),
            "weights": {"answer_accuracy": 0.6, "mastery": 0.4},
            "computed_at": utcnow().isoformat() + "Z",
            "note": "Indikator untuk ditinjau guru, bukan vonis otomatis.",
        },
    }


def advisory_indicators(
    db: DBSession, student_ids: Iterable[str], competencies: Iterable[Competency]
) -> list[dict[str, Any]]:
    """Non-predictive signals for teacher review. No labels, no model, no verdict."""
    params = effective_params(db)
    rows: list[dict[str, Any]] = []
    for student_id in student_ids:
        student = db.get(User, student_id)
        if student is None:
            continue
        snapshot = mastery_snapshot(db, student_id, competencies, params)
        low = [item for item in snapshot if item["status"] in ("emerging", "developing")]
        avg = sum(item["mastery_probability"] for item in snapshot) / len(snapshot) if snapshot else 0.0
        signals: list[str] = []
        if avg < 0.5:
            signals.append("rata-rata probabilitas penguasaan di bawah 50%")
        if low:
            signals.append(f"{len(low)} kompetensi masih berkembang")
        rows.append(
            {
                "student_id": student_id,
                "name": student.full_name,
                "average_mastery_percent": round(avg * 100, 2),
                "low_competency_count": len(low),
                "signals": signals,
                "is_prediction": False,
            }
        )
    rows.sort(key=lambda item: item["average_mastery_percent"])
    return rows


def refresh_recommendations(
    db: DBSession,
    student_id: str,
    class_ids: Iterable[str],
    school_id: str,
    subject_id: str | None = None,
) -> list[LearningRecommendation]:
    """Generate evidence-backed recommendations; replace only generated rows."""
    params = effective_params(db)
    _, competencies = competency_scope(db, school_id, class_ids, subject_id)
    snapshot = mastery_snapshot(db, student_id, competencies, params)
    db.query(LearningRecommendation).filter(
        LearningRecommendation.student_id == student_id,
        LearningRecommendation.rec_type.in_(GENERATED_REC_TYPES),
    ).delete(synchronize_session=False)
    db.flush()

    created: list[LearningRecommendation] = []
    for row in snapshot:
        if row["status"] not in ("not_started", "emerging", "developing"):
            continue
        has_question = db.scalar(
            select(Question).where(
                Question.competency_id == row["competency_id"],
                Question.is_published.is_(True),
                Question.question_type.in_(ADAPTIVE_TYPES),
            ).limit(1)
        )
        if has_question is None:
            continue
        level = desired_difficulty(row["mastery_probability"])
        created.append(
            LearningRecommendation(
                student_id=student_id,
                class_id=None,
                competency_id=row["competency_id"],
                rec_type="adaptive_practice",
                title=f"Latihan adaptif {row['code']}",
                reason=(
                    f"Probabilitas penguasaan {row['mastery_percent']}% "
                    f"({row['status']}); disarankan soal tingkat {level}."
                ),
                payload_json={
                    "generator": "fase3",
                    "difficulty": level,
                    "mastery_probability": row["mastery_probability"],
                    "evidence_count": row["observation_count"],
                },
                priority=100 - int(row["mastery_percent"]),
                evidence_json={
                    "source": "student_competency_mastery + bkt_history",
                    "note": "Bukan prediksi ketertinggalan.",
                },
            )
        )
    weakest = min(snapshot, key=lambda item: (item["mastery_probability"], item["code"])) if snapshot else None
    if weakest is not None:
        material = db.scalar(
            select(LearningMaterial).where(
                LearningMaterial.competency_id == weakest["competency_id"],
                LearningMaterial.is_published.is_(True),
            ).limit(1)
        )
        created.append(
            LearningRecommendation(
                student_id=student_id,
                class_id=None,
                competency_id=weakest["competency_id"],
                rec_type="remedial_focus",
                title=f"Fokus remedial {weakest['code']}",
                reason=(
                    f"Kompetensi dengan probabilitas terendah: {weakest['mastery_percent']}%."
                    + (" Materi tersedia." if material else " Belum ada materi yang ditautkan.")
                ),
                payload_json={
                    "generator": "fase3",
                    "material_id": material.id if material else None,
                    "mastery_probability": weakest["mastery_probability"],
                },
                priority=200 - int(weakest["mastery_percent"]),
                evidence_json={"source": "student_competency_mastery", "note": "Untuk ditinjau guru."},
            )
        )
    for row in created:
        db.add(row)
    db.flush()
    return created
