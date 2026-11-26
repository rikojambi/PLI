"""Fase 6 privacy operations: retention, erasure and secret rotation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.core import User
from app.models.operations import DeletionRequest
from app.schemas.privacy import ConfirmIn, RotateSecretIn
from app.services import retention
from app.services.audit import log_audit
from app.services.secrets import rotate_secret

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/retention/preview", response_model=dict)
def retention_preview(
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    return retention.retention_preview(db, user)


@router.post("/retention/purge", response_model=dict)
def retention_purge(
    payload: ConfirmIn,
    request: Request,
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    return retention.purge_expired(db, user, confirm=payload.confirm)


@router.post("/students/{student_id}/delete-request", response_model=dict)
def create_deletion_request(
    student_id: str,
    payload: ConfirmIn,
    request: Request,
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    if not payload.confirm:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Konfirmasi diperlukan untuk permintaan penghapusan")
    return retention.request_deletion(db, user, student_id, payload.reason)


@router.post("/students/{student_id}/delete", response_model=dict)
def execute_deletion(
    student_id: str,
    payload: ConfirmIn,
    request: Request,
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    return retention.execute_deletion(
        db,
        user,
        student_id,
        reason=payload.reason,
        confirm=payload.confirm,
    )


@router.get("/deletion-requests", response_model=dict)
def deletion_requests(
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    from sqlalchemy import select

    rows = db.scalars(
        select(DeletionRequest)
        .where(DeletionRequest.school_id == user.school_id)
        .order_by(DeletionRequest.created_at.desc())
        .limit(100)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "student_id": row.student_id,
                "status": row.status,
                "reason": row.reason,
                "due_at": row.due_at.isoformat() + "Z" if row.due_at else None,
                "processed_at": row.processed_at.isoformat() + "Z" if row.processed_at else None,
                "certificate": row.certificate_json,
            }
            for row in rows
        ]
    }


@router.post("/secret/rotate", response_model=dict)
def rotate_session_secret(
    payload: RotateSecretIn,
    request: Request,
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    if not payload.confirm:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Konfirmasi diperlukan untuk rotasi kunci")
    result = rotate_secret(db, user.id, note=payload.note)
    log_audit(
        db,
        user,
        "secret_rotated",
        "server",
        None,
        {"key_hint": result["key_hint"], "previous_key_hint": result["previous_key_hint"]},
        request,
    )
    db.commit()
    return result
