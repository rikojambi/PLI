"""Schemas untuk modul Intelligence Engine Fase 3."""
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BktParamsIn(BaseModel):
    p_init: float | None = Field(default=None, ge=0, le=1)
    p_transit: float | None = Field(default=None, ge=0, le=1)
    p_slip: float | None = Field(default=None, ge=0, le=1)
    p_guess: float | None = Field(default=None, ge=0, le=1)
    mastery_threshold: float | None = Field(default=None, ge=0, le=1)
    recompute: bool = True


class AdaptiveAnswerIn(BaseModel):
    question_id: str
    answer: dict[str, Any] = Field(default_factory=dict)
    client_id: str | None = Field(default=None, min_length=8, max_length=36)


class RecommendationOut(ORMModel):
    id: str
    student_id: str
    competency_id: str | None
    rec_type: str
    title: str
    reason: str
    payload_json: dict[str, Any]
    priority: int
    is_completed: bool
    evidence_json: dict[str, Any]
