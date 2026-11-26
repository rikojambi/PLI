"""Objective answer grading shared by assessments and the adaptive engine.

Keeping this in a service (rather than inside an endpoint module) lets both
Fase 2 assessment submissions and Fase 3 adaptive practice use exactly the
same rules, so a BKT observation always reflects the same definition of
"correct".
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models.assessment import Question, QuestionOption

MANUAL_TYPES = {"essay", "stepped_essay", "project"}
OBJECTIVE_TYPES = {
    "multiple_choice", "multiple_response", "true_false", "matching",
    "short_answer", "fill_blank", "image_based",
}


def normalize(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def grade_objective(
    db: DBSession, question: Question, answer: dict[str, Any]
) -> tuple[bool | None, float]:
    """Return ``(is_correct, points_earned)``. Manual types return ``(None, 0)``."""
    if question.question_type in MANUAL_TYPES:
        return None, 0.0

    options = db.scalars(
        select(QuestionOption).where(QuestionOption.question_id == question.id)
    ).all()
    qtype = question.question_type
    points = float(question.points)

    if qtype in {"multiple_choice", "true_false", "image_based"}:
        selected = answer.get("selected")
        correct = next((option for option in options if option.is_correct), None)
        matched = correct is not None and selected == correct.id
        return matched, (points if matched else 0.0)

    if qtype == "multiple_response":
        selected = set(answer.get("selected") or [])
        correct_ids = {option.id for option in options if option.is_correct}
        if not selected or not correct_ids:
            return False, 0.0
        correct = selected == correct_ids
        partial = len(selected & correct_ids) / len(correct_ids | selected)
        return correct, round(points * partial, 2)

    if qtype == "matching":
        pairs = answer.get("matches") or {}
        expected = {option.id: option.match_key for option in options if option.match_key}
        if not expected:
            return False, 0.0
        correct = all(pairs.get(key) == value for key, value in expected.items())
        return correct, points if correct else 0.0

    if qtype in {"short_answer", "fill_blank"}:
        expected = question.rubric_json.get("expected") or []
        if isinstance(expected, str):
            expected = [expected]
        expected_norm = {normalize(item) for item in expected}
        given = normalize(answer.get("text") or "")
        correct = given in expected_norm
        return correct, points if correct else 0.0

    return False, 0.0
