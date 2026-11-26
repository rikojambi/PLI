"""Fase 6 retention preview, expiry purge and verifiable student erasure.

Deletion is explicit: an administrator must pass `confirm=true`. Audit records
are retained because they are evidence of the operation, but they never store
raw student answers or secrets.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.db.base import utcnow
from app.models.academic import ClassMember
from app.models.ai import AIUsageLog, TutorConversation, TutorMessage
from app.models.assessment import AssessmentResult, StudentAnswer, StudentAttempt
from app.models.core import AuditLog, Role, Session, User
from app.models.intelligence import (
    AdaptivePractice,
    BktHistory,
    LearningRecommendation,
    RemedialRecord,
    StudentCompetencyMastery,
    StudentNote,
)
from app.models.operations import DeletionRequest, SyncConflict
from app.services.audit import log_audit


def _student(db: DBSession, user: User, student_id: str) -> User:
    target = db.get(User, student_id)
    role = db.get(Role, target.role_id) if target else None
    if not target or target.school_id != user.school_id or not role or role.name != "student":
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan di sekolah Anda")
    return target


def _counts(db: DBSession, user: User) -> dict[str, int]:
    now = utcnow()
    ai_cutoff = now - timedelta(days=settings.ai_log_retention_days)
    audit_cutoff = now - timedelta(days=settings.audit_log_retention_days)
    old_sessions = list(
        db.scalars(
            select(Session.id).join(User, Session.user_id == User.id).where(
                User.school_id == user.school_id,
                Session.expires_at < now,
            )
        ).all()
    )
    old_tutor_messages = list(
        db.scalars(
            select(TutorMessage.id)
            .join(TutorConversation, TutorMessage.conversation_id == TutorConversation.id)
            .join(User, TutorConversation.student_id == User.id)
            .where(User.school_id == user.school_id, TutorMessage.created_at < ai_cutoff)
        ).all()
    )
    return {
        "ai_usage_logs": int(
            db.scalar(
                select(func.count(AIUsageLog.id)).where(
                    AIUsageLog.school_id == user.school_id,
                    AIUsageLog.created_at < ai_cutoff,
                )
            ) or 0
        ),
        "tutor_messages": len(old_tutor_messages),
        "expired_sessions": len(old_sessions),
        "resolved_sync_conflicts": int(
            db.scalar(
                select(func.count(SyncConflict.id)).where(
                    SyncConflict.school_id == user.school_id,
                    SyncConflict.resolution.isnot(None),
                    SyncConflict.created_at < audit_cutoff,
                )
            ) or 0
        ),
        "audit_logs_retained": int(
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.created_at < audit_cutoff
                )
            ) or 0
        ),
    }


def retention_preview(db: DBSession, user: User) -> dict[str, Any]:
    return {
        "policy": {
            "student_data_retention_days": settings.retention_days,
            "ai_log_retention_days": settings.ai_log_retention_days,
            "audit_retention_days": settings.audit_log_retention_days,
        },
        "eligible": _counts(db, user),
        "note": "Log audit dipertahankan sebagai bukti; hanya data sementara yang dibersihkan otomatis.",
    }


def purge_expired(db: DBSession, user: User, *, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Konfirmasi diperlukan untuk membersihkan data")
    counts = _counts(db, user)
    now = utcnow()
    ai_cutoff = now - timedelta(days=settings.ai_log_retention_days)
    audit_cutoff = now - timedelta(days=settings.audit_log_retention_days)

    db.execute(
        delete(AIUsageLog).where(
            AIUsageLog.school_id == user.school_id,
            AIUsageLog.created_at < ai_cutoff,
        )
    )
    db.execute(
        delete(TutorMessage).where(
            TutorMessage.conversation_id.in_(
                select(TutorConversation.id).join(
                    User, TutorConversation.student_id == User.id
                ).where(User.school_id == user.school_id)
            ),
            TutorMessage.created_at < ai_cutoff,
        )
    )
    db.execute(
        delete(Session).where(
            Session.user_id.in_(select(User.id).where(User.school_id == user.school_id)),
            Session.expires_at < now,
        )
    )
    db.execute(
        delete(SyncConflict).where(
            SyncConflict.school_id == user.school_id,
            SyncConflict.resolution.isnot(None),
            SyncConflict.created_at < audit_cutoff,
        )
    )
    log_audit(db, user, "retention_purge", "school", user.school_id, counts)
    db.commit()
    return {"purged": counts, "note": "Log audit tidak dihapus oleh pembersihan otomatis."}


def request_deletion(db: DBSession, user: User, student_id: str, reason: str | None) -> dict[str, Any]:
    target = _student(db, user, student_id)
    request = DeletionRequest(
        school_id=user.school_id,
        student_id=target.id,
        requested_by=user.id,
        reason=reason or "Permintaan penghapusan data siswa",
        status="pending",
        due_at=utcnow() + timedelta(days=30),
        certificate_json={},
    )
    db.add(request)
    log_audit(db, user, "deletion_requested", "user", target.id, {"request_id": request.id})
    db.commit()
    return {
        "id": request.id,
        "student_id": target.id,
        "status": request.status,
        "due_at": request.due_at.isoformat() + "Z",
        "note": "Permintaan menunggu eksekusi eksplisit oleh administrator.",
    }


def _delete_where(db: DBSession, model, condition) -> int:
    count = int(db.scalar(select(func.count()).select_from(model).where(condition)) or 0)
    db.execute(delete(model).where(condition))
    return count


def execute_deletion(
    db: DBSession,
    user: User,
    student_id: str,
    *,
    reason: str | None,
    confirm: bool,
) -> dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Konfirmasi diperlukan untuk penghapusan permanen")
    target = _student(db, user, student_id)
    attempts = select(StudentAttempt.id).where(StudentAttempt.student_id == target.id)
    conversations = select(TutorConversation.id).where(TutorConversation.student_id == target.id)
    counts: dict[str, int] = {}
    steps = [
        ("answers", StudentAnswer, StudentAnswer.attempt_id.in_(attempts)),
        ("results", AssessmentResult, AssessmentResult.student_id == target.id),
        ("attempts", StudentAttempt, StudentAttempt.student_id == target.id),
        ("mastery", StudentCompetencyMastery, StudentCompetencyMastery.student_id == target.id),
        ("bkt_history", BktHistory, BktHistory.student_id == target.id),
        ("recommendations", LearningRecommendation, LearningRecommendation.student_id == target.id),
        ("adaptive_practices", AdaptivePractice, AdaptivePractice.student_id == target.id),
        ("remedial_records", RemedialRecord, RemedialRecord.student_id == target.id),
        ("notes", StudentNote, StudentNote.student_id == target.id),
        ("sync_conflicts", SyncConflict, SyncConflict.student_id == target.id),
        ("tutor_messages", TutorMessage, TutorMessage.conversation_id.in_(conversations)),
        ("tutor_conversations", TutorConversation, TutorConversation.student_id == target.id),
        ("class_memberships", ClassMember, ClassMember.user_id == target.id),
        ("sessions", Session, Session.user_id == target.id),
        ("deletion_requests", DeletionRequest, DeletionRequest.student_id == target.id),
    ]
    for label, model, condition in steps:
        counts[label] = _delete_where(db, model, condition)
        db.flush()

    certificate = {
        "student_ref": hashlib.sha256(target.id.encode("utf-8")).hexdigest()[:16],
        "deleted_at": utcnow().isoformat() + "Z",
        "reason": reason or "Penghapusan diminta administrator",
        "counts": counts,
        "method": "hard_delete_with_audit",
    }
    request = DeletionRequest(
        school_id=user.school_id,
        student_id=target.id,
        requested_by=user.id,
        processed_by=user.id,
        reason=reason or "Penghapusan diminta administrator",
        status="completed",
        processed_at=utcnow(),
        certificate_json=certificate,
    )
    db.add(request)
    log_audit(db, user, "student_erased", "user", target.id, certificate)
    db.flush()
    db.delete(target)
    db.commit()
    return certificate
