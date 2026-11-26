"""Fase 4 endpoints: AI provider manager, router budget, RAG, tutor and drafts.

Secrets never enter this module through a request body. Provider rows only name a
server environment variable; responses expose a masked hint and a boolean. Model
ids come from provider discovery or an administrator's explicit verification.
When nothing is verified, endpoints answer honestly that AI is unavailable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core import ratelimit
from app.core.config import DATA_DIR
from app.core.deps import require_admin, require_roles
from app.db.base import utcnow
from app.db.session import get_db
from app.models.academic import Class, Competency, Subject
from app.models.ai import AIProvider, Document, GeneratedContent
from app.models.core import User
from app.schemas.ai import (
    ApproveIn,
    BudgetIn,
    DocumentOut,
    GenerateIn,
    GeneratedOut,
    ModelIn,
    ModelOut,
    ProviderIn,
    ProviderOut,
    ProviderPatchIn,
    RagAnswerOut,
    RagAskIn,
    TestOut,
    TutorChatIn,
    TutorChatOut,
    TutorConversationOut,
    UsageOut,
)
from app.schemas.common import Message, Page
from app.services import ai_client, ai_router, content_generator, provider_manager, rag, tutoring
from app.services.ai_client import AIClientError, get_ai_client
from app.services.audit import log_audit

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------- helpers

def _provider(db: DBSession, user: User, provider_id: str) -> AIProvider:
    row = db.get(AIProvider, provider_id)
    if row is None or row.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Penyedia tidak ditemukan")
    return row


def _subject(db: DBSession, user: User, subject_id: str | None) -> Subject | None:
    if not subject_id:
        return None
    row = db.get(Subject, subject_id)
    if row is None or row.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Mata pelajaran tidak ditemukan")
    return row


def _out_provider(db: DBSession, row: AIProvider) -> dict[str, Any]:
    info = provider_manager.key_info(row)
    model_count = len(provider_manager.model_rows(db, row.school_id, row.id))
    data = {
        column: getattr(row, column)
        for column in ProviderOut.model_fields
        if hasattr(row, column)
    }
    data.update(info)
    data["model_count"] = model_count
    return ProviderOut.model_validate(data).model_dump()


def _document(db: DBSession, user: User, document_id: str) -> Document:
    row = db.get(Document, document_id)
    if row is None or row.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    if user.role.name != "admin" and row.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Dokumen ini milik guru lain")
    return row


def _model_out(row: Any) -> dict[str, Any]:
    return ModelOut.model_validate(row).model_dump()


def _generated_out(row: GeneratedContent) -> dict[str, Any]:
    return GeneratedOut.model_validate(row).model_dump()


def _tutor(user: User) -> None:
    if user.role.name != "student":
        raise HTTPException(status_code=403, detail="AI Tutor hanya untuk siswa")


# ---------------------------------------------------------------- catalogue + policy

@router.get("/catalog")
def catalog(_user: User = Depends(require_admin)) -> dict[str, Any]:
    return {
        "adapters": provider_manager.catalog(),
        "note": (
            "ID model tidak pernah diasumsikan. Model harus ditemukan dari API penyedia "
            "atau diverifikasi administrator sebelum dapat dipakai."
        ),
        "defaults": provider_manager.default_budget(),
    }


@router.get("/status")
def status(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "student")),
) -> dict[str, Any]:
    active = len(ai_router._providers(db, user.school_id))
    model_count = len(provider_manager.model_rows(db, user.school_id))
    available = active > 0 and model_count > 0
    return {
        "available": available,
        "active_providers": active,
        "verified_models": model_count,
        "detail": (
            "Penyedia dan model terverifikasi siap digunakan."
            if available
            else "Belum ada penyedia aktif dengan model terverifikasi. "
                 "Minta administrator memeriksa Menu AI → Penyedia."
        ),
        "budget": ai_router.budget_status(db, user.school_id),
    }


@router.get("/budget")
def get_budget(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    return ai_router.budget_status(db, user.school_id)


@router.put("/budget")
def put_budget(
    payload: BudgetIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    values = provider_manager.save_budget(db, payload.model_dump(), user)
    log_audit(db, user, "update_ai_budget", "ai_budget", user.school_id, values, request)
    db.commit()
    return {"policy": values, "message": "Kebijakan anggaran AI diperbarui"}


# ---------------------------------------------------------------- providers

@router.get("/providers", response_model=list[ProviderOut])
def list_providers(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AIProvider)
        .where(AIProvider.school_id == user.school_id)
        .order_by(AIProvider.priority, AIProvider.created_at)
    ).all()
    return [_out_provider(db, row) for row in rows]


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(
    payload: ProviderIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    existing = db.scalar(
        select(AIProvider).where(
            AIProvider.school_id == user.school_id, AIProvider.name == payload.name
        )
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="Nama penyedia sudah digunakan")
    row = AIProvider(school_id=user.school_id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_audit(
        db, user, "create_ai_provider", "ai_provider", row.id,
        {"name": row.name, "adapter": row.adapter, "key_ref": row.api_key_env}, request,
    )
    db.commit()
    return _out_provider(db, row)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: str,
    payload: ProviderPatchIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    row = _provider(db, user, provider_id)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    db.flush()
    log_audit(
        db, user, "update_ai_provider", "ai_provider", row.id,
        {"fields": sorted(changes), "key_ref": row.api_key_env}, request,
    )
    db.commit()
    return _out_provider(db, row)


@router.post("/providers/{provider_id}/discover", response_model=list[ModelOut])
def discover(
    provider_id: str,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    row = _provider(db, user, provider_id)
    try:
        records = ai_client.discover_models(row, client)
    except AIClientError as exc:
        row.last_error = str(exc)[:500]
        db.flush()
        raise HTTPException(status_code=502, detail=str(exc)) from None
    rows, error = provider_manager.sync_models(db, row, records, client)
    if error:
        raise HTTPException(status_code=502, detail=error)
    row.last_tested_at = utcnow()
    row.last_error = None
    log_audit(
        db, user, "discover_ai_models", "ai_provider", row.id,
        {"count": len(rows)}, request,
    )
    db.commit()
    return [_model_out(item) for item in rows]


@router.get("/providers/{provider_id}/models", response_model=list[ModelOut])
def list_models(
    provider_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    row = _provider(db, user, provider_id)
    return [_model_out(item) for item in provider_manager.model_rows(db, user.school_id, row.id)]


@router.post("/providers/{provider_id}/models", response_model=ModelOut, status_code=201)
def add_model(
    provider_id: str,
    payload: ModelIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    from app.models.ai import AIModel

    row = _provider(db, user, provider_id)
    existing = db.scalar(
        select(AIModel).where(
            AIModel.provider_id == row.id, AIModel.model_id == payload.model_id
        )
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="Model ini sudah terdaftar")
    model = AIModel(
        school_id=user.school_id,
        provider_id=row.id,
        model_id=payload.model_id.strip(),
        display_name=payload.display_name or payload.model_id.strip(),
        capabilities_json={"verified_by": "administrator"},
        discovered=False,
        is_enabled=payload.is_enabled,
    )
    db.add(model)
    db.flush()
    log_audit(
        db, user, "verify_ai_model", "ai_model", model.id,
        {"provider": row.name, "model": model.model_id}, request,
    )
    db.commit()
    return _model_out(model)


@router.patch("/models/{model_id}", response_model=ModelOut)
def update_model(
    model_id: str,
    payload: dict[str, Any],
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    from app.models.ai import AIModel

    row = db.get(AIModel, model_id)
    if row is None or row.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Model tidak ditemukan")
    if "is_enabled" in payload:
        row.is_enabled = bool(payload["is_enabled"])
    if payload.get("display_name"):
        row.display_name = str(payload["display_name"])[:200]
    row.updated_at = utcnow()
    log_audit(
        db, user, "update_ai_model", "ai_model", row.id,
        {"is_enabled": row.is_enabled}, request,
    )
    db.commit()
    return _model_out(row)


@router.post("/providers/{provider_id}/test", response_model=TestOut)
def test_provider(
    provider_id: str,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    row = _provider(db, user, provider_id)
    models = provider_manager.model_rows(db, user.school_id, row.id)
    model = next((item for item in models if item.is_enabled and ai_router._capability_ok(item, "chat")), None)
    if model is None:
        row.last_error = "Belum ada model terverifikasi untuk diuji"
        db.flush()
        return {
            "ok": False, "provider": row.name, "model": None,
            "detail": row.last_error, "latency_ms": None,
        }
    try:
        result = ai_router.chat(
            db, user, "test",
            [{"role": "user", "content": "Balas tepat dengan kata OK."}],
            preferred_model=model.model_id, max_tokens=24, client=client,
        )
    except ai_router.AIUnavailable as exc:
        row.last_error = str(exc)[:500]
        row.last_tested_at = utcnow()
        db.flush()
        return {
            "ok": False, "provider": row.name, "model": model.model_id,
            "detail": str(exc), "latency_ms": None,
        }
    row.last_tested_at = utcnow()
    row.last_error = None
    db.flush()
    log_audit(
        db, user, "test_ai_provider", "ai_provider", row.id,
        {"model": result.model, "request_id": result.request_id}, request,
    )
    db.commit()
    return {
        "ok": True, "provider": row.name, "model": result.model,
        "detail": f"Penyedia merespons ({result.latency_ms} ms).",
        "latency_ms": result.latency_ms,
    }


@router.get("/usage", response_model=Page[UsageOut])
def usage_logs(
    purpose: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    from app.models.ai import AIUsageLog

    query = select(AIUsageLog).where(AIUsageLog.school_id == user.school_id)
    count_query = select(func.count(AIUsageLog.id)).where(AIUsageLog.school_id == user.school_id)
    if purpose:
        query = query.where(AIUsageLog.purpose == purpose)
        count_query = count_query.where(AIUsageLog.purpose == purpose)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(AIUsageLog.created_at.desc()).limit(limit).offset(offset)).all()
    names = {
        item.id: item.display_name
        for item in db.scalars(select(AIProvider).where(AIProvider.school_id == user.school_id)).all()
    }
    items = []
    for row in rows:
        value = UsageOut.model_validate(row).model_dump()
        value["provider_name"] = names.get(row.provider_id)
        items.append(value)
    return {"items": items, "total": int(total or 0), "limit": limit, "offset": offset}


# ---------------------------------------------------------------- documents + RAG

@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> list[Document]:
    query = select(Document).where(Document.school_id == user.school_id)
    if user.role.name != "admin":
        query = query.where(Document.teacher_id == user.id)
    return list(db.scalars(query.order_by(Document.created_at.desc()).limit(200)).all())


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(min_length=3, max_length=250),
    subject_id: str | None = Form(default=None),
    class_id: str | None = Form(default=None),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> Document:
    ratelimit.enforce(request, "ai-document-upload", 20, 60)
    subject = _subject(db, user, subject_id)
    if class_id:
        klass = db.get(Class, class_id)
        if klass is None or klass.school_id != user.school_id:
            raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    content = await file.read()
    try:
        path, _suffix = rag.save_upload(user.school_id, file.filename or "", content)
    except rag.DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    row = Document(
        school_id=user.school_id,
        subject_id=subject.id if subject else None,
        class_id=class_id,
        teacher_id=user.id,
        title=title.strip(),
        file_path=str(path),
        mime_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        status="uploaded",
        chunk_count=0,
    )
    db.add(row)
    db.flush()
    log_audit(
        db, user, "upload_ai_document", "document", row.id,
        {"title": row.title, "size": row.file_size}, request,
    )
    db.commit()
    return row


@router.post("/documents/{document_id}/index")
def index_document(
    document_id: str,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> dict[str, Any]:
    row = _document(db, user, document_id)
    try:
        result = rag.index_document(db, user, row, client)
    except (rag.DocumentError, AIClientError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    log_audit(
        db, user, "index_ai_document", "document", row.id, result, request
    )
    db.commit()
    return result


@router.delete("/documents/{document_id}", response_model=Message)
def delete_document(
    document_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> dict[str, str]:
    row = _document(db, user, document_id)
    path = Path(row.file_path)
    root = (DATA_DIR / "ai_documents").resolve()
    if root in path.resolve().parents:
        path.unlink(missing_ok=True)
    db.delete(row)
    log_audit(db, user, "delete_ai_document", "document", document_id, {}, request)
    db.commit()
    return {"message": "Dokumen dihapus"}


@router.post("/rag/ask", response_model=RagAnswerOut)
def ask_rag(
    payload: RagAskIn,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "student")),
) -> dict[str, Any]:
    ratelimit.enforce(request, "ai-rag", 20, 60)
    _subject(db, user, payload.subject_id)
    return rag.answer(
        db, user, payload.question, payload.document_id, payload.subject_id, client
    )


# ---------------------------------------------------------------- tutor

@router.get("/tutor/conversations", response_model=list[TutorConversationOut])
def tutor_conversations(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("student")),
) -> list[dict[str, Any]]:
    _tutor(user)
    return tutoring.list_conversations(db, user)


@router.get("/tutor/conversations/{conversation_id}", response_model=TutorConversationOut)
def tutor_conversation(
    conversation_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("student")),
) -> dict[str, Any]:
    _tutor(user)
    try:
        return tutoring.get_conversation(db, user, conversation_id)
    except tutoring.TutorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/tutor/chat", response_model=TutorChatOut)
def tutor_chat(
    payload: TutorChatIn,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("student")),
) -> dict[str, Any]:
    _tutor(user)
    ratelimit.enforce(request, "ai-tutor", 30, 60)
    _subject(db, user, payload.subject_id)
    try:
        result = tutoring.chat(
            db, user, payload.message, payload.conversation_id,
            payload.subject_id, payload.competency_id, payload.client_id, client,
        )
    except tutoring.TutorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    db.commit()
    return result


# ---------------------------------------------------------------- generator

@router.get("/competencies")
def ai_competencies(
    subject_id: str | None = Query(default=None),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> list[dict[str, str]]:
    """Competency options scoped to the school, for draft generation forms."""
    query = select(Competency).join(Subject).where(Subject.school_id == user.school_id)
    if subject_id:
        query = query.where(Competency.subject_id == subject_id)
    rows = db.scalars(query.order_by(Competency.order_index, Competency.code)).all()
    return [
        {"id": row.id, "subject_id": row.subject_id, "code": row.code, "name": row.name}
        for row in rows
    ]


@router.post("/generate", response_model=GeneratedOut)
def generate_content(
    payload: GenerateIn,
    request: Request,
    client: Any = Depends(get_ai_client),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> dict[str, Any]:
    ratelimit.enforce(request, "ai-generate", 10, 60)
    try:
        draft = content_generator.generate(db, user, payload, client)
    except content_generator.ContentUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Draf tidak dibuat: layanan AI tidak tersedia. "
                f"Alasan: {exc}. Periksa Penyedia AI dan kebijakan anggaran."
            ),
        ) from None
    except content_generator.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    log_audit(
        db, user, "generate_ai_draft", "generated_content", draft.id,
        {"kind": draft.kind, "topic": payload.topic}, request,
    )
    db.commit()
    return _generated_out(draft)


@router.get("/generated", response_model=list[GeneratedOut])
def list_generated(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> list[dict[str, Any]]:
    query = select(GeneratedContent).where(GeneratedContent.school_id == user.school_id)
    if user.role.name != "admin":
        query = query.where(GeneratedContent.created_by == user.id)
    rows = db.scalars(query.order_by(GeneratedContent.created_at.desc()).limit(200)).all()
    return [_generated_out(row) for row in rows]


@router.post("/generated/{draft_id}/approve")
def approve_generated(
    draft_id: str,
    payload: ApproveIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> dict[str, Any]:
    try:
        draft = content_generator.get_draft(db, user, draft_id)
        published_id = content_generator.decide(
            db, user, draft, publish=payload.publish, review_note=payload.review_note
        )
    except content_generator.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    log_audit(
        db, user, "approve_ai_draft", "generated_content", draft.id,
        {"kind": draft.kind, "publish": payload.publish, "published_ref_id": published_id}, request,
    )
    db.commit()
    return {
        "message": "Draf disetujui dan dipublikasikan" if published_id else "Draf disetujui",
        "status": draft.status,
        "published_ref_id": published_id,
    }


@router.post("/generated/{draft_id}/reject", response_model=Message)
def reject_generated(
    draft_id: str,
    payload: ApproveIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
) -> dict[str, str]:
    try:
        draft = content_generator.get_draft(db, user, draft_id)
        if draft.status != "draft":
            raise content_generator.ContentError("Draf ini sudah ditinjau")
        draft.status = "rejected"
        draft.reviewed_by = user.id
        draft.review_note = payload.review_note
        db.flush()
    except content_generator.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    log_audit(db, user, "reject_ai_draft", "generated_content", draft.id, {}, request)
    db.commit()
    return {"message": "Draf ditolak"}
