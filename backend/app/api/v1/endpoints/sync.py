"""Fase 6 two-way offline sync: durable conflicts and server-change pull.

Writes remain idempotent by client_id. Conflicts are persisted when a client
sends stale data, and only an authorised teacher/admin may choose the client
version. Students can read their own conflicts and pull server changes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_roles
from app.db.base import utcnow
from app.db.session import get_db
from app.models.assessment import StudentAnswer, StudentAttempt
from app.models.core import User
from app.models.operations import SyncConflict
from app.schemas.sync import ConflictResolutionIn
from app.services.audit import log_audit
from app.services.dashboard import resolve_students

router = APIRouter(prefix="/sync", tags=["sync"])


def _parse_since(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Format cursor tidak dikenal") from None


def _serialize(conflict: SyncConflict) -> dict[str, Any]:
    return {
        "id": conflict.id,
        "student_id": conflict.student_id,
        "attempt_id": conflict.attempt_id,
        "question_id": conflict.question_id,
        "client_id": conflict.client_id,
        "reason": conflict.reason,
        "server_snapshot": conflict.server_snapshot_json,
        "client_snapshot": conflict.client_snapshot_json,
        "resolution": conflict.resolution,
        "resolved_at": conflict.resolved_at.isoformat() + "Z" if conflict.resolved_at else None,
        "created_at": conflict.created_at.isoformat() + "Z",
    }


@router.get("/conflicts", response_model=dict)
def list_conflicts(
    student_id: str | None = None,
    class_id: str | None = None,
    resolved: bool | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    students, _ = resolve_students(db, user, class_id, student_id)
    query = select(SyncConflict).where(SyncConflict.student_id.in_([item.id for item in students]))
    if resolved is not None:
        query = query.where(SyncConflict.resolution.isnot(None) == resolved)
    rows = db.scalars(query.order_by(SyncConflict.created_at.desc()).limit(200)).all()
    return {
        "items": [_serialize(row) for row in rows],
        "total": len(rows),
        "strategy": "Versi dengan client_updated_at terbaru menang; konflik dicatat dan guru dapat memilih versi klien sebelum upaya dikumpulkan.",
    }


@router.post("/conflicts/{conflict_id}/resolve", response_model=dict)
def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolutionIn,
    request: Request,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    conflict = db.get(SyncConflict, conflict_id)
    if not conflict or conflict.school_id != user.school_id:
        raise HTTPException(status_code=404, detail="Konflik tidak ditemukan")
    students, _ = resolve_students(db, user, None, conflict.student_id)
    if not students:
        raise HTTPException(status_code=404, detail="Konflik di luar cakupan kelas Anda")
    if conflict.resolution:
        raise HTTPException(status_code=409, detail="Konflik sudah diselesaikan")

    applied = False
    if payload.resolution == "client":
        attempt = db.get(StudentAttempt, conflict.attempt_id) if conflict.attempt_id else None
        if not attempt or attempt.status != "in_progress":
            raise HTTPException(status_code=409, detail="Versi klien hanya dapat diterapkan sebelum upaya dikumpulkan")
        snapshot = conflict.client_snapshot_json or {}
        question_id = snapshot.get("question_id") or conflict.question_id
        if question_id not in (attempt.question_order_json or []):
            raise HTTPException(status_code=400, detail="Soal tidak termasuk dalam upaya ini")
        client_id = snapshot.get("client_id")
        if client_id:
            other = db.scalar(
                select(StudentAnswer).where(
                    StudentAnswer.attempt_id == attempt.id,
                    StudentAnswer.client_id == client_id,
                    StudentAnswer.question_id != question_id,
                )
            )
            if other:
                raise HTTPException(status_code=409, detail="client_id sudah dipakai untuk soal lain")
        existing = db.scalar(
            select(StudentAnswer).where(
                StudentAnswer.attempt_id == attempt.id,
                StudentAnswer.question_id == question_id,
            )
        )
        raw_at = snapshot.get("client_updated_at")
        try:
            client_at = datetime.fromisoformat(str(raw_at).replace("Z", "")) if raw_at else utcnow()
        except ValueError:
            client_at = utcnow()
        if existing is None:
            db.add(StudentAnswer(
                attempt_id=attempt.id,
                question_id=question_id,
                client_id=client_id,
                answer_json=snapshot.get("answer") or {},
                time_spent_sec=int(snapshot.get("time_spent_sec") or 0),
                changed_count=int(snapshot.get("changed_count") or 0),
                client_updated_at=client_at,
                answered_at=utcnow(),
                updated_at=utcnow(),
                synced_at=utcnow(),
            ))
        else:
            # The chosen device becomes the authoritative source of this answer.
            existing.client_id = client_id
            existing.answer_json = snapshot.get("answer") or {}
            existing.time_spent_sec = int(snapshot.get("time_spent_sec") or 0)
            existing.changed_count = int(snapshot.get("changed_count") or 0)
            existing.client_updated_at = client_at
            existing.updated_at = utcnow()
            existing.synced_at = utcnow()
        applied = True

    conflict.resolution = payload.resolution
    conflict.resolved_by = user.id
    conflict.resolved_at = utcnow()
    log_audit(
        db,
        user,
        "sync_conflict_resolved",
        "sync_conflict",
        conflict.id,
        {"resolution": payload.resolution, "client_applied": applied, "note": payload.note},
        request,
    )
    db.commit()
    return {
        "id": conflict.id,
        "resolution": conflict.resolution,
        "client_applied": applied,
        "resolved_at": conflict.resolved_at.isoformat() + "Z",
        "note": "Konflik dan keputusan guru tersimpan di log audit.",
    }


@router.get("/pull", response_model=dict)
def pull_changes(
    since: str | None = None,
    user: User = Depends(require_roles("student")),
    db: DBSession = Depends(get_db),
):
    """Server-to-client delta. Cursor is the newest `updated_at` returned."""
    cursor = _parse_since(since)
    rows = db.execute(
        select(StudentAnswer, StudentAttempt)
        .join(StudentAttempt, StudentAnswer.attempt_id == StudentAttempt.id)
        .where(StudentAttempt.student_id == user.id)
        .order_by(StudentAnswer.updated_at, StudentAnswer.id)
    ).all()
    answers = []
    newest = cursor
    for answer, attempt in rows:
        changed_at = answer.synced_at or answer.updated_at or answer.answered_at
        if not changed_at or changed_at <= cursor:
            continue
        answers.append({
            "attempt_id": attempt.id,
            "question_id": answer.question_id,
            "answer": answer.answer_json,
            "client_id": answer.client_id,
            "client_updated_at": answer.client_updated_at.isoformat() + "Z" if answer.client_updated_at else None,
            "changed_at": changed_at.isoformat() + "Z",
        })
        if changed_at > newest:
            newest = changed_at
    conflicts = db.scalars(
        select(SyncConflict).where(
            SyncConflict.student_id == user.id,
            SyncConflict.resolution.is_(None),
        ).order_by(SyncConflict.created_at.desc()).limit(50)
    ).all()
    return {
        "answers": answers,
        "conflicts": [_serialize(row) for row in conflicts],
        "cursor": newest.isoformat() + "Z" if newest != datetime.min else None,
        "note": "Simpan cursor di perangkat dan kirimkan pada permintaan berikutnya.",
    }
