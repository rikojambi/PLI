"""Schemas untuk modul AI Fase 4. Tidak ada schema yang menerima kunci API mentah."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

ADAPTERS = {
    "openai_compatible", "gemini", "ollama",
}
PURPOSES = {"tutor", "rag", "generate_question", "generate_material", "embedding", "test"}
GENERATED_KINDS = {"question", "material"}


class ProviderIn(BaseModel):
    name: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9_]{1,59}$")
    display_name: str = Field(min_length=2, max_length=150)
    adapter: str
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=150)
    embedding_model: str | None = Field(default=None, max_length=150)
    api_key_env: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    is_primary: bool = False
    is_fallback: bool = False
    priority: int = Field(default=100, ge=1, le=1000)
    max_tokens: int = Field(default=1024, ge=64, le=16000)
    timeout_sec: int = Field(default=30, ge=5, le=180)
    requests_per_hour: int = Field(default=60, ge=1, le=10000)
    monthly_token_limit: int = Field(default=200000, ge=1000, le=100000000)
    input_cost_per_million: float = Field(default=0.0, ge=0)
    output_cost_per_million: float = Field(default=0.0, ge=0)
    config_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("adapter")
    @classmethod
    def valid_adapter(cls, value: str) -> str:
        if value not in ADAPTERS:
            raise ValueError("Adapter tidak dikenal")
        return value

    @field_validator("api_key_env")
    @classmethod
    def valid_env_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not value.startswith("PLI_") or not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError("Nama env harus diawali PLI_ dan hanya memakai huruf/angka/garis bawah")
        return value


class ProviderPatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=150)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=150)
    embedding_model: str | None = Field(default=None, max_length=150)
    api_key_env: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    is_primary: bool | None = None
    is_fallback: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    max_tokens: int | None = Field(default=None, ge=64, le=16000)
    timeout_sec: int | None = Field(default=None, ge=5, le=180)
    requests_per_hour: int | None = Field(default=None, ge=1, le=10000)
    monthly_token_limit: int | None = Field(default=None, ge=1000, le=100000000)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)
    config_json: dict[str, Any] | None = None

    @field_validator("api_key_env")
    @classmethod
    def valid_env_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not value.startswith("PLI_") or not all(ch.isalnum() or ch == "_" for ch in value):
            raise ValueError("Nama env harus diawali PLI_ dan hanya memakai huruf/angka/garis bawah")
        return value


class ProviderOut(ORMModel):
    id: str
    name: str
    display_name: str
    adapter: str
    base_url: str | None
    model: str | None
    embedding_model: str | None
    api_key_env: str | None
    key_hint: str | None = None
    has_key: bool = False
    is_active: bool
    is_primary: bool
    is_fallback: bool
    priority: int
    max_tokens: int
    timeout_sec: int
    requests_per_hour: int
    monthly_token_limit: int
    input_cost_per_million: float
    output_cost_per_million: float
    config_json: dict[str, Any]
    last_tested_at: datetime | None
    last_error: str | None
    model_count: int = 0


class ModelOut(ORMModel):
    id: str
    provider_id: str
    model_id: str
    display_name: str | None
    capabilities_json: dict[str, Any]
    context_window: int | None
    discovered: bool
    is_enabled: bool


class ModelIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=150)
    display_name: str | None = Field(default=None, max_length=200)
    is_enabled: bool = True


class BudgetIn(BaseModel):
    daily_token_limit: int = Field(ge=0, le=100000000)
    monthly_cost_limit_usd: float = Field(ge=0, le=100000)
    max_tokens_per_request: int = Field(ge=64, le=16000)
    allow_unknown_cost: bool = False


class TutorChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    subject_id: str | None = None
    competency_id: str | None = None
    client_id: str | None = Field(default=None, min_length=8, max_length=36)


class TutorMessageOut(ORMModel):
    id: str
    role: str
    content: str
    sources_json: list[Any]
    created_at: datetime


class TutorConversationOut(ORMModel):
    id: str
    title: str
    subject_id: str | None
    competency_id: str | None
    updated_at: datetime
    messages: list[TutorMessageOut] = []


class RagAskIn(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    document_id: str | None = None
    subject_id: str | None = None


class GenerateIn(BaseModel):
    kind: Literal["question", "material"]
    subject_id: str
    competency_id: str | None = None
    topic: str = Field(min_length=3, max_length=250)
    notes: str | None = Field(default=None, max_length=2000)
    client_id: str | None = Field(default=None, min_length=8, max_length=36)


class GeneratedOut(ORMModel):
    id: str
    kind: str
    status: str
    title: str
    content_json: dict[str, Any]
    sources_json: list[Any]
    model_info_json: dict[str, Any]
    review_note: str | None
    published_ref_id: str | None
    created_at: datetime
    updated_at: datetime


class ApproveIn(BaseModel):
    review_note: str | None = Field(default=None, max_length=1000)
    publish: bool = False


class UsageOut(ORMModel):
    id: str
    provider_id: str | None
    provider_name: str | None = None
    user_id: str | None
    purpose: str
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cost_source: str
    request_id: str | None
    latency_ms: int | None
    success: bool
    error: str | None
    created_at: datetime


class DocumentOut(ORMModel):
    id: str
    subject_id: str | None
    class_id: str | None
    teacher_id: str
    title: str
    mime_type: str
    file_size: int
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class RagAnswerOut(BaseModel):
    available: bool
    status: str
    answer: str
    citations: list[dict[str, Any]]
    evidence: dict[str, Any]


class TutorChatOut(BaseModel):
    idempotent: bool
    conversation_id: str
    message: TutorMessageOut
    available: bool
    evidence: dict[str, Any]


class TestOut(BaseModel):
    ok: bool
    provider: str
    model: str | None
    detail: str
    latency_ms: int | None
