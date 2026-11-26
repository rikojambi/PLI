"""Fase 6 administrator-only detailed health snapshot."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.core import User
from app.services import health

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/status", response_model=dict)
def status(
    user: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    snapshot = health.detailed(db)
    snapshot["checked_by"] = user.username
    return snapshot
