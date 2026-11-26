"""AI provider configuration, routing evidence, tutor conversations and RAG documents."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin, utcnow


class AIProvider(IDMixin, TimestampMixin, Base):
    """A school-owned provider configuration. Secrets are only env references."""

    __tablename__ = "ai_providers"
    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_ai_provider_school_name"),
    )
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    display_name: Mapped[str] = mapped_column(String(150))
    adapter: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str | None] = mapped_column(String(150))
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    api_key_env: Mapped[str | None] = mapped_column(String(100))
    # Legacy column kept for compatibility. Fase 4 intentionally uses env-only
    # secrets and never writes a plaintext or encrypted key through the API.
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    timeout_sec: Mapped[int] = mapped_column(Integer, default=30)
    requests_per_hour: Mapped[int] = mapped_column(Integer, default=60)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=200000)
    input_cost_per_million: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_per_million: Mapped[float] = mapped_column(Float, default=0.0)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class AIModel(IDMixin, TimestampMixin, Base):
    """Model ids discovered from a provider or explicitly verified by an admin."""

    __tablename__ = "ai_provider_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_ai_provider_model"),
    )
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(String(150), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer)
    discovered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AIUsageLog(IDMixin, Base):
    """One real provider call. Cost is recorded only when pricing is configured."""

    __tablename__ = "ai_usage_logs"
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"), index=True)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    model: Mapped[str | None] = mapped_column(String(150))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_source: Mapped[str] = mapped_column(String(30), default="not_configured")
    request_id: Mapped[str | None] = mapped_column(String(80), index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class TutorConversation(IDMixin, TimestampMixin, Base):
    __tablename__ = "tutor_conversations"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    competency_id: Mapped[str | None] = mapped_column(ForeignKey("competencies.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(250), default="Percakapan baru")


class TutorMessage(IDMixin, Base):
    __tablename__ = "tutor_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_id", name="uq_tutor_message_client"),
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("tutor_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Document(IDMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(250))
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(150))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)


class DocumentChunk(IDMixin, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[list | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),)


class GeneratedContent(IDMixin, TimestampMixin, Base):
    """AI-created draft that stays unpublished until a teacher reviews it."""

    __tablename__ = "generated_contents"
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    title: Mapped[str] = mapped_column(String(250))
    prompt_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sources_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model_info_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    published_ref_id: Mapped[str | None] = mapped_column(String(36))
    client_id: Mapped[str | None] = mapped_column(String(36), index=True)
    __table_args__ = (
        UniqueConstraint("school_id", "created_by", "client_id", name="uq_generated_school_creator_client"),
    )


Index("ix_usage_provider_time", AIUsageLog.provider_id, AIUsageLog.created_at)
Index("ix_generated_school_status", GeneratedContent.school_id, GeneratedContent.status)
