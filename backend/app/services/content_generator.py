"""AI-assisted question and material drafts.

Nothing generated here becomes visible to students until a teacher reviews the
draft and explicitly approves publication. Every output keeps its source and
model evidence so a reviewer can judge whether it is trustworthy.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models.academic import Competency, LearningMaterial, Subject
from app.models.assessment import Question, QuestionOption
from app.models.ai import GeneratedContent
from app.models.core import User
from app.schemas.ai import GenerateIn
from app.schemas.learning import QuestionIn
from app.services import ai_router, rag


class ContentError(Exception):
    """Generation or approval could not be completed honestly."""


class ContentUnavailable(ContentError):
    """No verified provider can generate a draft; carries the router's reason."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse(text: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ContentError("Penyedia tidak mengembalikan draf berformat JSON.")
    try:
        value = json.loads(cleaned[start:end + 1])
    except (ValueError, TypeError):
        raise ContentError("Draf dari penyedia bukan JSON yang valid.") from None
    if not isinstance(value, dict):
        raise ContentError("Draf dari penyedia bukan objek JSON.")
    return value


def _existing(db: DBSession, user: User, client_id: str | None) -> GeneratedContent | None:
    if not client_id:
        return None
    return db.scalar(
        select(GeneratedContent).where(
            GeneratedContent.school_id == user.school_id,
            GeneratedContent.created_by == user.id,
            GeneratedContent.client_id == client_id,
        )
    )


def generate(
    db: DBSession, user: User, payload: GenerateIn, client: Any | None = None
) -> GeneratedContent | None:
    """Return an existing draft for a replayed client_id, otherwise create one.

    Raises :class:`ContentUnavailable` when no verified provider can produce a
    draft. The API turns that into an explicit unavailable response instead of
    a fabricated draft.
    """
    replay = _existing(db, user, payload.client_id)
    if replay is not None:
        return replay

    subject = db.get(Subject, payload.subject_id)
    if subject is None or subject.school_id != user.school_id:
        raise ContentError("Mata pelajaran tidak ditemukan")
    competency = None
    if payload.competency_id:
        competency = db.get(Competency, payload.competency_id)
        if competency is None or competency.subject_id != subject.id:
            raise ContentError("Kompetensi tidak sesuai mata pelajaran")

    retrieved = rag.retrieve(db, user, payload.topic, subject_id=subject.id, client=client)
    context = "\n\n".join(item["content"] for item in retrieved["chunks"])
    sources = rag.citations(retrieved)
    if payload.kind == "question":
        schema = (
            '{"title":"judul singkat","question_type":"multiple_choice",'
            '"difficulty":"medium","content":"teks soal","explanation":"pembahasan",'
            '"rubric_json":{},"options":[{"label":"A","content":"opsi",'
            '"is_correct":false},{"label":"B","content":"opsi","is_correct":true}]}'
        )
        rules = (
            "Buat SATU soal objektif pilihan ganda dengan tepat satu kunci jawaban. "
            "Gunakan hanya materi pada KONTEKS bila tersedia; bila tidak cukup, "
            "tetap buat soal dari topik tetapi sertakan catatan pada explanation bahwa "
            "sumber dokumen tidak tersedia."
        )
    else:
        schema = (
            '{"title":"judul materi","material_type":"text",'
            '"content":"materi lengkap dengan subjudul dan contoh"}'
        )
        rules = (
            "Buat materi pembelajaran ringkas, berurutan, dan dapat diverifikasi guru. "
            "Sertakan batasan bila KONTEKS tidak mencukupi."
        )

    system = (
        "Kamu membantu guru menyusun DRAF. Jawab HANYA dengan satu objek JSON valid "
        f"mengikuti struktur: {schema}. {rules} Gunakan Bahasa Indonesia. "
        "Jangan menambahkan teks di luar JSON."
    )
    user_prompt = (
        f"Mata pelajaran: {subject.name}\n"
        f"Kompetensi: {competency.name if competency else 'tidak ditentukan'}\n"
        f"Topik: {payload.topic}\n"
        f"Catatan guru: {payload.notes or '-'}\n\n"
        f"KONTEKS DOKUMEN:\n{context or 'Tidak ada dokumen relevan.'}"
    )
    try:
        result = ai_router.chat(
            db, user, f"generate_{payload.kind}",
            [{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
            client=client,
            json_mode=True,
        )
    except ai_router.AIUnavailable as exc:
        raise ContentUnavailable(str(exc)) from None

    content = _parse(result.text)
    if not str(content.get("title") or "").strip():
        raise ContentError("Draf dari penyedia tidak memiliki judul.")
    if not str(content.get("content") or "").strip():
        raise ContentError("Draf dari penyedia tidak memiliki isi.")
    if payload.kind == "question":
        options = content.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise ContentError("Draf soal harus memiliki minimal dua pilihan jawaban.")
        if sum(1 for item in options if isinstance(item, dict) and item.get("is_correct")) != 1:
            raise ContentError("Draf soal harus memiliki tepat satu kunci jawaban.")
    draft = GeneratedContent(
        school_id=user.school_id,
        created_by=user.id,
        kind=payload.kind,
        status="draft",
        title=str(content.get("title") or payload.topic)[:250],
        prompt_json={
            "subject_id": subject.id,
            "competency_id": competency.id if competency else None,
            "topic": payload.topic,
            "notes": payload.notes,
            "retrieval_method": retrieved["method"],
        },
        content_json=content,
        sources_json=sources,
        model_info_json={
            "provider": result.provider_name,
            "model": result.model,
            "request_id": result.request_id,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "cost_source": result.cost_source,
            "latency_ms": result.latency_ms,
            "attempts": result.attempts,
        },
        client_id=payload.client_id,
    )
    db.add(draft)
    db.flush()
    return draft


def get_draft(db: DBSession, user: User, draft_id: str) -> GeneratedContent:
    row = db.get(GeneratedContent, draft_id)
    if row is None or row.school_id != user.school_id:
        raise ContentError("Draf tidak ditemukan")
    if user.role.name != "admin" and row.created_by != user.id:
        raise ContentError("Draf ini dibuat oleh guru lain")
    return row


def _publish_material(db: DBSession, user: User, draft: GeneratedContent) -> str:
    content = draft.content_json
    title = str(content.get("title") or draft.title).strip()
    if len(title) < 3:
        raise ContentError("Judul materi tidak valid untuk dipublikasikan")
    material = LearningMaterial(
        subject_id=draft.prompt_json["subject_id"],
        competency_id=draft.prompt_json.get("competency_id"),
        teacher_id=user.id,
        title=title[:250],
        content=str(content.get("content") or ""),
        material_type=str(content.get("material_type") or "text")[:30],
        is_published=True,
    )
    db.add(material)
    db.flush()
    return material.id


def _publish_question(db: DBSession, user: User, draft: GeneratedContent) -> str:
    content = dict(draft.content_json)
    content["subject_id"] = draft.prompt_json["subject_id"]
    content["competency_id"] = draft.prompt_json.get("competency_id")
    content["is_published"] = True
    content.setdefault("gap_category", "konsep")
    content.setdefault("points", 1.0)
    try:
        validated = QuestionIn.model_validate(content)
    except ValidationError as exc:
        details = "; ".join(
            ".".join(str(part) for part in err["loc"]) + ": " + err["msg"]
            for err in exc.errors()[:3]
        )
        raise ContentError(f"Draf soal belum layak dipublikasikan ({details})") from None
    row = Question(teacher_id=user.id, **validated.model_dump(exclude={"options"}))
    db.add(row)
    db.flush()
    for option in validated.options:
        db.add(QuestionOption(question_id=row.id, **option.model_dump()))
    return row.id


def decide(
    db: DBSession,
    user: User,
    draft: GeneratedContent,
    *,
    publish: bool,
    review_note: str | None = None,
) -> str | None:
    """Approve a draft and optionally publish it; or reject it.

    Returns the published record id only when publication was requested.
    """
    if draft.status != "draft":
        raise ContentError("Draf ini sudah ditinjau")
    draft.reviewed_by = user.id
    draft.review_note = review_note
    if not publish:
        draft.status = "approved"
        db.flush()
        return None
    published_id = (
        _publish_question(db, user, draft)
        if draft.kind == "question"
        else _publish_material(db, user, draft)
    )
    draft.status = "published"
    draft.published_ref_id = published_id
    db.flush()
    return published_id
