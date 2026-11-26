"""Pedagogical tutor grounded in the student's own mastery profile and documents."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models.academic import Competency, Subject
from app.models.ai import TutorConversation, TutorMessage
from app.models.core import User
from app.models.intelligence import LearningRecommendation, StudentCompetencyMastery
from app.services import ai_router, rag


class TutorError(Exception):
    """Conversation is not accessible."""


def _conversation(db: DBSession, user: User, conversation_id: str | None) -> TutorConversation:
    if conversation_id:
        row = db.get(TutorConversation, conversation_id)
        if row is None or row.student_id != user.id:
            raise TutorError("Percakapan tidak ditemukan")
        return row
    row = TutorConversation(student_id=user.id, title="Percakapan baru")
    db.add(row)
    db.flush()
    return row


def _existing_reply(db: DBSession, user: User, client_id: str | None) -> TutorMessage | None:
    if not client_id:
        return None
    return db.scalar(
        select(TutorMessage)
        .join(TutorConversation, TutorConversation.id == TutorMessage.conversation_id)
        .where(
            TutorConversation.student_id == user.id,
            TutorMessage.role == "assistant",
            TutorMessage.client_id == client_id,
        )
    )


def conversation_out(db: DBSession, row: TutorConversation, with_messages: bool = True) -> dict[str, Any]:
    messages = []
    if with_messages:
        messages = list(
            db.scalars(
                select(TutorMessage)
                .where(TutorMessage.conversation_id == row.id)
                .order_by(TutorMessage.created_at, TutorMessage.id)
            ).all()
        )
    return {
        "id": row.id,
        "title": row.title,
        "subject_id": row.subject_id,
        "competency_id": row.competency_id,
        "updated_at": row.updated_at,
        "messages": [
            {
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "sources_json": item.sources_json,
                "created_at": item.created_at,
            }
            for item in messages
        ],
    }


def list_conversations(db: DBSession, user: User) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(TutorConversation)
        .where(TutorConversation.student_id == user.id)
        .order_by(TutorConversation.updated_at.desc())
        .limit(50)
    ).all()
    return [conversation_out(db, row, with_messages=False) for row in rows]


def get_conversation(db: DBSession, user: User, conversation_id: str) -> dict[str, Any]:
    row = db.get(TutorConversation, conversation_id)
    if row is None or row.student_id != user.id:
        raise TutorError("Percakapan tidak ditemukan")
    return conversation_out(db, row)


def _profile_context(db: DBSession, user: User, subject_id: str | None, competency_id: str | None) -> str:
    query = (
        select(StudentCompetencyMastery, Competency, Subject)
        .join(Competency, Competency.id == StudentCompetencyMastery.competency_id)
        .join(Subject, Subject.id == Competency.subject_id)
        .where(
            StudentCompetencyMastery.student_id == user.id,
            Subject.school_id == user.school_id,
        )
    )
    if subject_id:
        query = query.where(Subject.id == subject_id)
    if competency_id:
        query = query.where(Competency.id == competency_id)
    rows = db.execute(query.order_by(StudentCompetencyMastery.mastery_probability).limit(8)).all()
    lines = []
    for mastery, competency, subject in rows:
        lines.append(
            f"- {subject.name} / {competency.name}: "
            f"probabilitas {mastery.mastery_probability:.0%}, status {mastery.status}, "
            f"{mastery.correct_count}/{mastery.practice_count} jawaban benar"
        )
    recs = db.scalars(
        select(LearningRecommendation)
        .where(LearningRecommendation.student_id == user.id, LearningRecommendation.is_completed.is_(False))
        .order_by(LearningRecommendation.priority.desc())
        .limit(5)
    ).all()
    for rec in recs:
        lines.append(f"- Rekomendasi: {rec.title} — {rec.reason}")
    if not lines:
        return "Belum ada bukti penguasaan atau rekomendasi untuk siswa ini."
    return "\n".join(lines)


def chat(
    db: DBSession,
    user: User,
    message: str,
    conversation_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    client_id: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    replay = _existing_reply(db, user, client_id)
    if replay is not None:
        return {
            "idempotent": True,
            "conversation_id": replay.conversation_id,
            "message": {
                "id": replay.id,
                "role": replay.role,
                "content": replay.content,
                "sources_json": replay.sources_json,
                "created_at": replay.created_at,
            },
            "available": True,
            "evidence": {"note": "Pesan ini sudah tercatat sebelumnya."},
        }

    conversation = _conversation(db, user, conversation_id)
    if conversation.title == "Percakapan baru":
        conversation.title = message[:60]
        if subject_id:
            conversation.subject_id = subject_id
        if competency_id:
            conversation.competency_id = competency_id

    db.add(
        TutorMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            sources_json=[],
        )
    )
    db.flush()

    profile = _profile_context(db, user, conversation.subject_id, conversation.competency_id)
    retrieved = rag.retrieve(db, user, message, subject_id=conversation.subject_id, client=client)
    sources = rag.citations(retrieved)
    context = "\n\n".join(item["content"] for item in retrieved["chunks"])
    system = (
        "Kamu adalah tutor pedagogis untuk siswa sekolah menengah. Gunakan Bahasa Indonesia, "
        "jelaskan langkah secara sabar, ajukan satu pertanyaan pemahaman di akhir, dan jangan "
        "memberi vonis atau label negatif. Berdasarkan profil penguasaan berikut, sesuaikan "
        "penjelasan. Jika informasi tidak ada, katakan 'Data tidak tersedia'. "
        f"PROFIL SISWA:\n{profile}"
    )
    user_prompt = message
    if context:
        user_prompt += f"\n\nKONTEKS DOKUMEN:\n{context}"

    available = True
    try:
        result = ai_router.chat(
            db, user, "tutor",
            [{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
            client=client,
        )
        answer = result.text
        evidence = {
            "provider": result.provider_name,
            "model": result.model,
            "request_id": result.request_id,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "cost_source": result.cost_source,
            "retrieval_method": retrieved["method"],
            "profile_based": True,
        }
    except ai_router.AIUnavailable as exc:
        available = False
        answer = (
            "Layanan tutor AI belum tersedia. Profil penguasaan siswa tetap dapat dilihat pada "
            "halaman Penguasaan. Minta administrator memverifikasi penyedia dan model terlebih dahulu."
        )
        evidence = {"reason": str(exc), "profile_based": True, "retrieval_method": retrieved["method"]}

    reply = TutorMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        sources_json=sources,
        client_id=client_id,
    )
    db.add(reply)
    db.flush()
    return {
        "idempotent": False,
        "conversation_id": conversation.id,
        "message": {
            "id": reply.id,
            "role": reply.role,
            "content": reply.content,
            "sources_json": reply.sources_json,
            "created_at": reply.created_at,
        },
        "available": available,
        "evidence": evidence,
    }
