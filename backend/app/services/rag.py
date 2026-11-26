"""RAG ingestion, retrieval and grounded answers for Fase 4.

When no embedding provider is verified, retrieval falls back to a transparent
lexical score and is labelled as such. When no relevant chunk exists, the API
answers "Data tidak tersedia" instead of asking a model to improvise.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import DATA_DIR, settings
from app.core.deps import teacher_class_ids
from app.models.academic import ClassMember
from app.models.ai import Document, DocumentChunk
from app.models.core import User
from app.services import ai_router

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".pptx"}
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
TOKEN_RE = re.compile(r"[a-z0-9]+")


class DocumentError(Exception):
    """A document cannot be ingested."""


def upload_dir(school_id: str) -> Path:
    target = DATA_DIR / "ai_documents" / school_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_upload(school_id: str, filename: str, content: bytes) -> tuple[Path, str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentError("Ekstensi tidak didukung. Gunakan PDF, DOCX, PPTX, TXT, atau MD.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentError("Berkas terlalu besar (maksimal 12 MB).")
    target = upload_dir(school_id) / f"{uuid4().hex}{suffix}"
    target.write_bytes(content)
    return target, suffix


def _extract_pdf(path: Path) -> str:
    try:
        import fitz  # pymupdf
    except ImportError:
        raise DocumentError("Pembaca PDF belum terpasang di server.") from None
    with fitz.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError:
        raise DocumentError("Pembaca DOCX belum terpasang di server.") from None
    document = DocxDocument(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_pptx(path: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError:
        raise DocumentError("Pembaca PPTX belum terpasang di server.") from None
    presentation = Presentation(str(path))
    parts: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                parts.append(shape.text_frame.text)
    return "\n".join(parts)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".docx":
        text = _extract_docx(path)
    elif suffix == ".pptx":
        text = _extract_pptx(path)
    else:
        raise DocumentError("Jenis berkas tidak dikenal.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 20:
        raise DocumentError("Teks tidak dapat diekstrak dari berkas ini.")
    return text


def chunk_text(
    text: str, size: int | None = None, overlap: int | None = None
) -> list[str]:
    size = size or settings.rag_chunk_size
    overlap = overlap or settings.rag_chunk_overlap
    if size <= overlap:
        overlap = max(0, size // 5)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        part = text[start:start + size].strip()
        if part:
            chunks.append(part)
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def index_document(
    db: DBSession, user: User, document: Document, client: Any | None = None
) -> dict[str, Any]:
    path = Path(document.file_path)
    if not path.exists():
        document.status = "error"
        document.chunk_count = 0
        db.flush()
        raise DocumentError("Berkas asal tidak ditemukan di server.")
    text = extract_text(path)
    parts = chunk_text(text)
    if not parts:
        raise DocumentError("Tidak ada bagian teks yang dapat diindeks.")

    embedded = ai_router.embeddings(db, user, parts, client)
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.flush()
    for index, content in enumerate(parts):
        vector = embedded.vectors[index] if embedded else None
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                embedding_json=vector,
                embedding_model=embedded.model if embedded else None,
            )
        )
    document.chunk_count = len(parts)
    document.status = "indexed" if embedded else "indexed_lexical"
    db.flush()
    return {
        "document_id": document.id,
        "chunks": len(parts),
        "method": "embedding" if embedded else "lexical",
        "embedding_model": embedded.model if embedded else None,
    }


def visible_documents(
    db: DBSession, user: User, document_id: str | None = None, subject_id: str | None = None
) -> list[Document]:
    query = select(Document).where(
        Document.school_id == user.school_id,
        Document.status.in_(("indexed", "indexed_lexical")),
    )
    role = user.role.name
    if role == "student":
        class_ids = list(db.scalars(
            select(ClassMember.class_id).where(ClassMember.user_id == user.id)
        ).all())
        query = query.where(
            (Document.class_id.is_(None)) | (Document.class_id.in_(class_ids))
        )
    elif role == "teacher":
        class_ids = teacher_class_ids(db, user)
        query = query.where(
            (Document.teacher_id == user.id) | (Document.class_id.in_(class_ids))
        )
    if document_id:
        query = query.where(Document.id == document_id)
    if subject_id:
        query = query.where(Document.subject_id == subject_id)
    return list(db.scalars(query.order_by(Document.created_at.desc())).all())


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _lexical_score(question: str, content: str) -> float:
    q, c = _tokens(question), _tokens(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    base = overlap / math.sqrt(len(q) * len(c))
    phrase = 0.15 if question.strip().lower() in content.lower() else 0.0
    return round(min(1.0, base + phrase), 6)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return round(dot / (na * nb), 6) if na and nb else 0.0


def retrieve(
    db: DBSession,
    user: User,
    question: str,
    document_id: str | None = None,
    subject_id: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    documents = visible_documents(db, user, document_id, subject_id)
    chunks = []
    for document in documents:
        rows = db.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        ).all()
        for row in rows:
            chunks.append((document, row))
    if not chunks:
        return {"chunks": [], "method": "no_documents", "document_count": 0}

    query_vector = None
    if all(row.embedding_json for _, row in chunks):
        embedded = ai_router.embeddings(db, user, [question], client)
        if embedded:
            query_vector = embedded.vectors[0]

    scored: list[dict[str, Any]] = []
    for document, row in chunks:
        if query_vector is not None and row.embedding_json:
            score = _cosine(query_vector, row.embedding_json)
            method = "embedding"
        else:
            score = _lexical_score(question, row.content)
            method = "lexical"
        scored.append({
            "document_id": document.id,
            "document_title": document.title,
            "chunk_id": row.id,
            "chunk_index": row.chunk_index,
            "content": row.content,
            "score": score,
        })
    threshold = 0.20 if query_vector is not None else 0.08
    scored = [item for item in scored if item["score"] >= threshold]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "chunks": scored[: settings.rag_top_k],
        "method": "embedding" if query_vector is not None else "lexical",
        "document_count": len(documents),
    }


def citations(retrieved: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "number": index,
            "document_id": item["document_id"],
            "title": item["document_title"],
            "chunk_index": item["chunk_index"],
            "score": item["score"],
        }
        for index, item in enumerate(retrieved["chunks"], start=1)
    ]


def answer(
    db: DBSession,
    user: User,
    question: str,
    document_id: str | None = None,
    subject_id: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    retrieved = retrieve(db, user, question, document_id, subject_id, client)
    sources = citations(retrieved)
    if not retrieved["chunks"]:
        return {
            "available": False,
            "status": "data_tidak_tersedia",
            "answer": "Data tidak tersedia dalam dokumen yang diizinkan untuk akun ini.",
            "citations": [],
            "evidence": {
                "method": retrieved["method"],
                "document_count": retrieved["document_count"],
                "note": "Tidak ada potongan dokumen yang relevan; model tidak dipanggil.",
            },
        }

    context = "\n\n".join(
        f"[{number}] {item['document_title']} (bagian {item['chunk_index'] + 1}): {item['content']}"
        for number, item in enumerate(retrieved["chunks"], start=1)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Jawab hanya berdasarkan KONTEKS. Jika konteks tidak cukup, katakan persis "
                "'Data tidak tersedia'. Sertakan penanda [1], [2], dst. pada kalimat yang "
                "bersumber dari konteks. Jangan mengarang kutipan. Gunakan Bahasa Indonesia."
            ),
        },
        {"role": "user", "content": f"KONTEKS:\n{context}\n\nPERTANYAAN: {question}"},
    ]
    try:
        result = ai_router.chat(db, user, "rag", messages, client=client)
    except ai_router.AIUnavailable as exc:
        return {
            "available": False,
            "status": "penyedia_tidak_tersedia",
            "answer": "Dokumen relevan ditemukan, tetapi penyedia AI belum tersedia atau belum dikonfigurasi.",
            "citations": sources,
            "evidence": {"method": retrieved["method"], "reason": str(exc)},
        }
    return {
        "available": True,
        "status": "ok",
        "answer": result.text,
        "citations": sources,
        "evidence": {
            "method": retrieved["method"],
            "provider": result.provider_name,
            "model": result.model,
            "request_id": result.request_id,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "cost_source": result.cost_source,
        },
    }
