"""Schemas untuk modul pembelajaran Fase 2."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel

QUESTION_TYPES = {
    "multiple_choice", "multiple_response", "true_false", "matching",
    "short_answer", "fill_blank", "essay", "stepped_essay", "image_based", "project",
}
DIFFICULTIES = {"easy", "medium", "hard"}
GAP_CATEGORIES = {"konsep", "prosedur", "hitungan", "membaca_soal", "aplikasi"}


class MaterialOut(ORMModel):
    id: str
    subject_id: str
    competency_id: str | None
    teacher_id: str
    title: str
    content: str | None
    material_type: str
    file_path: str | None
    file_name: str | None = None
    is_published: bool
    created_at: datetime


class QuestionOptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=10)
    content: str = Field(min_length=1)
    is_correct: bool | None = None
    match_key: str | None = Field(default=None, max_length=60)
    position: int = Field(default=0, ge=0)


class QuestionOptionOut(ORMModel):
    id: str
    label: str
    content: str
    is_correct: bool | None = None
    match_key: str | None = None
    position: int


class QuestionIn(BaseModel):
    subject_id: str
    competency_id: str | None = None
    question_type: str
    difficulty: str = "medium"
    content: str = Field(min_length=3)
    image_path: str | None = None
    points: float = Field(default=1.0, gt=0, le=100)
    time_limit_sec: int | None = Field(default=None, ge=10, le=3600)
    explanation: str | None = None
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    gap_category: str = "konsep"
    options: list[QuestionOptionIn] = Field(default_factory=list)
    is_published: bool = True

    @model_validator(mode="before")
    @classmethod
    def drop_unused_options(cls, values: Any) -> Any:
        """Tipe uraian/isian tidak memakai pilihan jawaban; jangan validasi sisa draft UI."""
        if isinstance(values, dict) and values.get("question_type") not in {
            "multiple_choice", "multiple_response", "true_false", "matching", "image_based",
        }:
            return {**values, "options": []}
        return values

    @field_validator("question_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        if value not in QUESTION_TYPES:
            raise ValueError(f"Tipe soal tidak dikenal: {value}")
        return value

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        if value not in DIFFICULTIES:
            raise ValueError("Kesulitan harus easy, medium, atau hard")
        return value

    @field_validator("gap_category")
    @classmethod
    def valid_gap_category(cls, value: str) -> str:
        if value not in GAP_CATEGORIES:
            raise ValueError("Kategori celah belajar tidak dikenal")
        return value

    @model_validator(mode="after")
    def check_options(self):
        objective = {
            "multiple_choice", "multiple_response", "true_false", "matching", "image_based",
        }
        if self.question_type in objective and len(self.options) < 2:
            raise ValueError("Tipe soal objektif memerlukan minimal dua pilihan")
        if self.question_type == "multiple_choice":
            if sum(1 for option in self.options if option.is_correct) != 1:
                raise ValueError("Pilihan ganda harus memiliki tepat satu kunci jawaban")
        if self.question_type == "multiple_response":
            if sum(1 for option in self.options if option.is_correct) < 1:
                raise ValueError("Pilihan ganda kompleks minimal memiliki satu kunci jawaban")
        if self.question_type in ("short_answer", "fill_blank"):
            if not self.rubric_json.get("expected"):
                raise ValueError("Isian singkat/memelengkapi memerlukan rubric_json.expected")
        return self


class QuestionOut(ORMModel):
    id: str
    subject_id: str
    competency_id: str | None
    question_type: str
    difficulty: str
    content: str
    image_path: str | None
    points: float
    time_limit_sec: int | None
    explanation: str | None
    rubric_json: dict[str, Any]
    gap_category: str = "konsep"
    is_published: bool
    options: list[QuestionOptionOut] = []


class AssessmentIn(BaseModel):
    subject_id: str
    class_id: str
    title: str = Field(min_length=3, max_length=250)
    description: str | None = None
    duration_min: int = Field(default=45, ge=1, le=480)
    start_at: datetime | None = None
    end_at: datetime | None = None
    shuffle_questions: bool = False
    shuffle_options: bool = False
    allow_resume: bool = True
    allow_offline: bool = False
    is_published: bool = False
    question_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_window(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("Waktu selesai harus setelah waktu mulai")
        return self


class AssessmentOut(ORMModel):
    id: str
    subject_id: str
    class_id: str
    teacher_id: str
    title: str
    description: str | None
    duration_min: int
    start_at: datetime | None
    end_at: datetime | None
    shuffle_questions: bool
    shuffle_options: bool
    allow_resume: bool
    allow_offline: bool
    is_published: bool
    question_ids: list[str] = []
    question_count: int = 0
    max_points: float = 0
    attempt_count: int = 0
    already_started: bool = False


class StudentQuestionOut(QuestionOut):
    """Options are hidden from the student only when shuffle needs reordering on client."""
    pass


class AnswerIn(BaseModel):
    question_id: str
    client_id: str = Field(min_length=8, max_length=36)
    answer: dict[str, Any] = Field(default_factory=dict)
    time_spent_sec: int = Field(default=0, ge=0, le=86400)
    changed_count: int = Field(default=0, ge=0, le=10000)
    client_updated_at: datetime


class SyncPayload(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list, max_length=200)
    focus_loss_count: int = Field(default=0, ge=0, le=10000)
    page_hidden_count: int = Field(default=0, ge=0, le=10000)


class AnswerOut(ORMModel):
    id: str
    question_id: str
    client_id: str | None
    answer_json: dict[str, Any]
    is_correct: bool | None
    points_earned: float | None
    time_spent_sec: int
    changed_count: int
    updated_at: datetime | None
    synced_at: datetime | None


class AttemptOut(ORMModel):
    id: str
    assessment_id: str
    student_id: str
    started_at: datetime
    submitted_at: datetime | None
    status: str
    total_points: float | None
    max_points: float | None
    sync_status: str
    anomaly_flags: list[str]
    answers: list[AnswerOut] = []
    questions: list[QuestionOut] = []
    assessment: dict[str, Any] | None = None


class SubmitOut(ORMModel):
    attempt_id: str
    status: str
    total_points: float
    max_points: float
    score_percent: float
    graded_automatically: int
    pending_manual: int
    anomaly_flags: list[str]


class ResultOut(ORMModel):
    id: str
    attempt_id: str
    assessment_id: str
    student_id: str
    score: float
    mastery_percent: float | None
    graded_by: str | None
    graded_at: datetime
    notes: str | None
    assessment_title: str | None = None
    student_name: str | None = None


class GradeIn(BaseModel):
    points_earned: float = Field(ge=0)
    feedback: str | None = Field(default=None, max_length=2000)


class NoteIn(BaseModel):
    student_id: str
    class_id: str | None = None
    note_type: str = Field(default="info", pattern="^(info|warning|encouragement)$")
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=3, max_length=2000)


class NoteOut(ORMModel):
    id: str
    student_id: str
    teacher_id: str
    class_id: str | None
    note_type: str
    title: str
    content: str
    is_read: bool
    created_at: datetime


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


class AnalyticsOut(BaseModel):
    class_id: str | None
    subject_id: str | None
    student_count: int
    attempt_count: int
    average_score: float
    passing_count: int
    hardest_competencies: list[dict[str, Any]]
    students_needing_help: list[dict[str, Any]]
    evidence: dict[str, Any]
